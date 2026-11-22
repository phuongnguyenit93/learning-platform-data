# Cô lập object, property, cache và event

## 1. Tenant isolation là gì?

Trong hệ thống multi-tenant, nhiều tổ chức hoặc khách hàng dùng chung một ứng dụng, hạ tầng hoặc kho dữ liệu. Tenant isolation bảo đảm mỗi tenant chỉ truy cập và tác động lên dữ liệu, tài nguyên và luồng nghiệp vụ thuộc phạm vi được cấp. Cô lập không chỉ là thêm cột tenant_id vào database. Nó phải được duy trì xuyên suốt từ lúc xác định tenant của request đến truy vấn object, đọc/ghi property, cache, hàng đợi, event, file, báo cáo và tác vụ nền.

Một API có thể xác thực người gọi đúng nhưng vẫn vi phạm cô lập nếu:

- User của tenant A đổi object ID để đọc hoặc sửa object của tenant B.
- Truy vấn lấy object theo ID mà quên lọc tenant.
- Response DTO trả field hoặc quan hệ thuộc tenant khác.
- Cache dùng chung key theo URL, khiến response của A được phục vụ cho B.
- Event consumer nhận event của A nhưng xử lý dưới tenant context của B, hoặc bỏ qua tenant context hoàn toàn.
- Background job chỉ giữ object ID mà không giữ tenant identity đáng tin cậy.
- File storage, search index, export hoặc log dùng đường dẫn/khóa không phân vùng theo tenant.

Mục tiêu là bảo đảm mọi thao tác đều có một tenant context đã được xác minh, mọi object được truy cập trong đúng phạm vi, mọi property được phép theo use case, và mọi bản sao dữ liệu vẫn giữ ranh giới tenant.

## 2. Phân biệt tenant isolation, BOLA và BOPLA

Các lớp kiểm soát có liên quan nhưng không thay thế nhau:

| Kiểm soát | Câu hỏi | Ví dụ lỗi |
|---|---|---|
| Function authorization | Tenant/user có được gọi chức năng này không? | User gọi endpoint quản trị tenant |
| Object-level authorization (BOLA) | Principal có quyền trên object cụ thể không? | User A đọc order ID của B |
| Property-level authorization (BOPLA) | Principal có quyền đọc/sửa field nào trên object? | User A đọc internalNotes hoặc sửa role |
| Tenant isolation | Dữ liệu và tài nguyên có nằm đúng ranh giới tenant trong mọi lớp không? | Cache, event hoặc file của A bị dùng bởi B |

Tenant isolation là nguyên tắc xuyên suốt, không phải một kiểm tra duy nhất tại controller. Một object có thể cùng tenant nhưng người dùng vẫn không được truy cập; ngược lại, một nhân viên hỗ trợ đa tenant có thể được phép truy cập một số object của nhiều tenant theo phạm vi công việc. Khi đó phải có chính sách delegated access rõ ràng, có lý do và audit.

## 3. Xác định tenant context đáng tin cậy

Tenant context là thông tin xác định tenant mà request hoặc tác vụ đang hoạt động thay mặt. Nó có thể được chọn qua subdomain, URL, header hoặc claim trong token, nhưng giá trị client gửi chỉ là dữ liệu đầu vào, chưa phải bằng chứng quyền.

Một luồng xác định tenant an toàn thường gồm:

1. Xác thực principal từ session hoặc access token.
2. Nhận tenant mà người dùng muốn thao tác, ví dụ từ subdomain hoặc tenant selector.
3. Kiểm tra principal có membership hoặc delegated grant còn hiệu lực với tenant đó.
4. Kiểm tra tenant đang hoạt động, chưa bị khóa và phù hợp với client/application.
5. Tạo tenant context bất biến cho request, gắn với principal, request ID và phạm vi quyền.
6. Truyền context này tới application service, repository, cache và các dependency cần biết tenant.

Không tin mù quáng X-Tenant-ID, tenantId trong JSON, query string hoặc custom header do client gửi. Không lấy tenant từ một claim chưa xác minh chữ ký, issuer, audience và thời hạn. Nếu token có tenant claim, vẫn cần hiểu claim đó đại diện cho tenant hiện tại hay chỉ là danh sách tenant mà principal có thể tham gia.

Ví dụ:

~~~text
Principal: user-42
Tenant được yêu cầu: tenant-A
Membership: user-42 thuộc tenant-A, trạng thái ACTIVE
Tenant context: tenant-A / user-42 / request-abc
~~~

Nếu cùng user-42 chuyển sang tenant-B, server phải xác minh membership B rồi tạo context mới. Không tái sử dụng context A trong request B hoặc thay tenant context giữa chừng trong cùng một transaction.

### 3.1 Subdomain, path và header

Các cách chọn tenant phổ biến:

| Cách chọn | Ví dụ | Kiểm soát cần có |
|---|---|---|
| Subdomain | tenant-a.example.com | Host allowlist, ánh xạ domain đã xác minh tới tenant và kiểm tra membership |
| URL path | /tenants/tenant-a/orders | Đối chiếu tenant trong path với principal và quyền |
| Header | X-Tenant-ID: tenant-a | Xem như tenant selector; xác minh membership phía server |
| Token claim | tenant_id=tenant-a | Xác minh token đầy đủ, audience và ngữ nghĩa claim |
| Session state | Tenant đang chọn trong session server-side | Kiểm tra lại khi membership hoặc trạng thái tenant thay đổi |

Không có phương thức nào tự động an toàn. Subdomain giúp định tuyến và trải nghiệm người dùng nhưng Host header có thể bị giả mạo nếu proxy/app không kiểm tra domain. Tenant trong path dễ quan sát nhưng client vẫn có thể thay ID. Header tiện cho API nhưng không phải nguồn tin cậy. Cần xác thực quyền sau khi phân giải tenant ở mọi trường hợp.

### 3.2 Nhân viên hỗ trợ và truy cập đa tenant

Nếu nhân viên hỗ trợ được phép truy cập nhiều tenant, không nên tạo một tài khoản super admin không giới hạn rồi bỏ qua tenant scope. Dùng quyền hỗ trợ có phạm vi:

- Chỉ tenant được chỉ định hoặc tenant thuộc queue hỗ trợ.
- Chỉ loại dữ liệu và hành động cần cho công việc.
- Thời hạn truy cập hoặc quy trình break-glass khi cần.
- Lý do truy cập và ticket/case tham chiếu.
- Audit riêng cho việc chuyển tenant và xem dữ liệu nhạy cảm.

Việc chuyển tenant phải là hành động có kiểm soát. Không cho client chỉ sửa header rồi tiếp tục sử dụng quyền cũ.

## 4. Chọn mô hình lưu trữ multi-tenant

Có ba mô hình phổ biến. Lựa chọn ảnh hưởng mức độ cô lập, chi phí vận hành, khả năng mở rộng và phạm vi sự cố.

| Mô hình | Cách tổ chức | Ưu điểm | Rủi ro/chi phí |
|---|---|---|---|
| Database riêng cho tenant | Mỗi tenant có database hoặc cluster riêng | Ranh giới dữ liệu mạnh, backup/restore và khóa có thể tách riêng | Chi phí, migration, connection và vận hành tăng |
| Schema riêng cho tenant | Chung database, mỗi tenant có schema | Có namespace riêng, có thể phân quyền theo schema | Quản lý schema/migration phức tạp; lỗi search_path hoặc quyền database có thể vượt ranh giới |
| Shared tables | Nhiều tenant dùng chung bảng, mỗi row có tenant key | Dễ mở rộng số lượng tenant, tối ưu tài nguyên và migration | Phụ thuộc mạnh vào tenant scoping, constraint, RLS và kiểm thử |

Có thể dùng mô hình lai: tenant lớn hoặc yêu cầu pháp lý đặc biệt có database riêng, tenant nhỏ dùng shared tables. Dù chọn mô hình nào, application vẫn cần authorization ở cấp object và property. Database riêng không tự bảo đảm người dùng của tenant có quyền trên mọi object trong database đó.

Với shared tables, mọi bảng chứa dữ liệu tenant cần có khóa tenant rõ ràng. Bảng quan hệ, bảng con, bảng audit và bảng lưu trạng thái cũng phải giữ tenant ownership hoặc liên kết tới một object đã có tenant scope.

## 5. Thiết kế schema và ràng buộc dữ liệu

### 5.1 Gắn tenant key vào object

Một bảng shared có thể có dạng:

~~~sql
CREATE TABLE orders (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    status TEXT NOT NULL,
    total_amount NUMERIC(18, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, order_id)
);
~~~

Khóa chính ghép (tenant_id, order_id) thể hiện object được định danh trong phạm vi tenant. Nếu order ID được bảo đảm globally unique, vẫn nên giữ tenant key trong các truy vấn và constraint để củng cố ranh giới.

### 5.2 Ngăn quan hệ chéo tenant bằng composite foreign key

Nếu customer và order đều thuộc tenant, quan hệ cần bảo đảm customer của order nằm trong cùng tenant:

~~~sql
CREATE TABLE customers (
    tenant_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    display_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, customer_id)
);

ALTER TABLE orders
ADD CONSTRAINT fk_orders_customer_same_tenant
FOREIGN KEY (tenant_id, customer_id)
REFERENCES customers (tenant_id, customer_id);
~~~

Ràng buộc này ngăn một order thuộc tenant A tham chiếu customer thuộc tenant B, kể cả khi application có bug. Không chỉ kiểm tra trong code; hãy dùng constraint của database để bảo vệ invariant có thể biểu diễn bằng dữ liệu quan hệ.

Với bảng con như order_items, documents hoặc comments, dùng khóa tenant trong foreign key tới parent. Với bảng nối many-to-many, lưu tenant key và ràng buộc cả hai phía theo cùng tenant nếu nghiệp vụ không cho phép quan hệ xuyên tenant.

### 5.3 Unique constraint và index

Nếu email hoặc slug chỉ cần duy nhất trong tenant, constraint phải bao gồm tenant:

~~~sql
CREATE UNIQUE INDEX uq_tenant_customer_email
ON customers (tenant_id, lower(email));
~~~

Nếu unique constraint chỉ đặt trên email toàn hệ thống, tenant này có thể vô tình ảnh hưởng tenant khác và làm lộ việc một email đã được đăng ký. Ngược lại, nếu nghiệp vụ yêu cầu email duy nhất toàn hệ thống, phải áp dụng constraint toàn cục một cách có chủ đích và xử lý thông báo để tránh enumeration.

Index truy vấn thường nên bắt đầu bằng tenant key khi hầu hết truy vấn được giới hạn theo tenant, ví dụ (tenant_id, status, created_at). Chọn index theo workload thực tế; index không thay thế điều kiện tenant trong query.

## 6. Tenant scoping trong truy vấn object

Mẫu lỗi phổ biến là lấy object theo ID rồi mới kiểm tra tenant hoặc quên kiểm tra hoàn toàn:

~~~java
Order order = orderRepository.findById(orderId)
    .orElseThrow(NotFoundException::new);
~~~

Trong shared tables, truy vấn nên giới hạn tenant ngay từ đầu:

~~~java
Order order = orderRepository
    .findByTenantIdAndOrderId(actor.tenantId(), orderId)
    .orElseThrow(NotFoundException::new);
~~~

Tenant ID ở đây phải lấy từ tenant context đã xác minh, không lấy trực tiếp từ request body. Sau khi tìm được object trong tenant, vẫn kiểm tra quyền người dùng trên object và hành động cần thực hiện.

### 6.1 Tenant-scoped repository

Có thể tạo repository method hoặc data access abstraction buộc truyền tenant context:

~~~java
interface OrderRepository {
    Optional<Order> findByTenantIdAndOrderId(
        TenantId tenantId,
        OrderId orderId
    );

    List<OrderSummary> findSummaries(
        TenantId tenantId,
        OrderFilter filter,
        PageRequest page
    );
}
~~~

Tránh cung cấp API truy vấn tùy ý như findById cho mọi service nghiệp vụ nếu nó dễ bị gọi mà không có tenant. Với tác vụ quản trị đa tenant, tạo abstraction riêng thể hiện quyền elevated và yêu cầu lý do/audit.

### 6.2 List, search, pagination và aggregation

Không chỉ endpoint lấy một object mới cần tenant filter. Các query sau cũng phải giới hạn:

- Danh sách, tìm kiếm và autocomplete.
- Count, sum, average, dashboard và báo cáo.
- Export, bulk update và bulk delete.
- Subquery, join, ORM relationship và lazy loading.
- Native SQL, stored procedure và query do người dùng cấu hình.
- GraphQL resolver và DataLoader.

Một trang danh sách có thể không trả record của tenant khác nhưng count tổng hoặc facet vẫn tiết lộ số lượng dữ liệu. Mọi aggregation và pagination metadata cũng phải được tính trong tenant scope.

Với pagination, cursor nên gắn với tenant hoặc query context, được ký hoặc xác thực toàn vẹn nếu client có thể sửa. Không cho cursor của tenant A tiếp tục dùng trong tenant B. Luôn áp dụng tenant filter ở server dù cursor đã chứa tenant ID.

### 6.3 Bulk operation

Với request chứa nhiều ID, không truy vấn tất cả rồi cập nhật những ID tồn tại. Hãy lọc theo tenant và xác định rõ hành vi nếu một số ID không thuộc tenant hiện tại. Tránh trả lỗi chi tiết giúp kẻ tấn công dò ID của tenant khác.

Bulk export/update nên có giới hạn số lượng, quota và audit. Không để một request chứa danh sách ID rất lớn làm lộ dữ liệu hoặc gây quá tải.

## 7. Database Row-Level Security

Row-Level Security (RLS) có thể thêm lớp bảo vệ ở database. Với PostgreSQL, policy có thể giới hạn row theo tenant context của transaction:

~~~sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders FORCE ROW LEVEL SECURITY;

CREATE POLICY orders_tenant_isolation
ON orders
USING (
    tenant_id = current_setting('app.tenant_id', true)::uuid
)
WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)::uuid
);
~~~

USING giới hạn row hiện có được đọc/cập nhật/xóa; WITH CHECK giới hạn row mới hoặc giá trị sau cập nhật. Tên biến và cách thiết lập chỉ là ví dụ, cần xử lý trường hợp context chưa được đặt hoặc không hợp lệ để mặc định từ chối.

Trong mỗi transaction, ứng dụng đặt tenant context bằng cơ chế local theo transaction, ví dụ SET LOCAL hoặc set_config:

~~~sql
SELECT set_config('app.tenant_id', :tenant_id, true);
~~~

Tham số true giới hạn giá trị trong transaction hiện tại. Điều này quan trọng khi dùng connection pool: nếu tenant context được đặt ở cấp session rồi không reset, connection tái sử dụng có thể mang context của request trước.

Các lưu ý quan trọng:

- Dùng database role không phải superuser và không có thuộc tính BYPASSRLS.
- Chủ sở hữu bảng có thể có hành vi bypass RLS tùy cấu hình; FORCE ROW LEVEL SECURITY giúp áp dụng policy với owner trong nhiều trường hợp nhưng không thay thế quản lý quyền.
- Không cho application role tự ý đổi tenant context thành giá trị client cung cấp. Chỉ set sau khi server xác minh membership.
- Đặt context và thực hiện query trong cùng transaction/connection.
- Kiểm tra context thiếu, null, sai định dạng hoặc transaction bị tái sử dụng; fail closed.
- RLS không bảo vệ các bảng không bật policy, view/function chạy với quyền đặc biệt hoặc luồng truy cập khác nếu cấu hình sai.
- Vẫn giữ tenant filter trong repository và authorization ở application; RLS là lớp phòng thủ bổ sung.

Biến cấu hình tùy chỉnh như app.tenant_id là context do ứng dụng thiết lập, không phải credential không thể giả mạo. Nếu kẻ tấn công khai thác SQL injection và có thể chạy lệnh SQL dưới cùng database role, họ có thể thử thay đổi context rồi truy vấn tenant khác. Vì vậy vẫn phải dùng parameterized query, giảm quyền database, ngăn SQL injection và kiểm thử policy với đúng role runtime. RLS giảm hậu quả của lỗi query thông thường; không nên xem nó là ranh giới chống lại một application role đã bị chiếm hoàn toàn.

RLS đặc biệt hữu ích với shared database và nhiều service cùng truy cập dữ liệu. Tuy nhiên, policy cần được kiểm thử bằng đúng database role của ứng dụng, không chỉ bằng tài khoản DBA.

## 8. Cô lập property trong tenant

Tenant scope của object không đồng nghĩa principal có thể đọc mọi property. Ví dụ, user A trong tenant A được xem hồ sơ nhân viên của tenant A, nhưng không được xem salary, disciplinaryNotes hoặc internalRiskScore nếu vai trò không cho phép.

Phân loại property:

| Nhóm | Ví dụ | Kiểm soát |
|---|---|---|
| Tenant public | Tên hiển thị của tổ chức, logo công khai | Có thể hiển thị cho người được phép xem tenant |
| Tenant internal | Cấu hình vận hành, ghi chú nội bộ | Chỉ nhóm/role phù hợp trong tenant |
| Personal | Email, địa chỉ, số điện thoại | Chủ thể hoặc người được ủy quyền |
| Highly sensitive | Salary, định danh, thông tin thanh toán | Quyền hẹp, audit và có thể xác thực tăng cường |
| System-managed | tenantId, ownerId, createdBy, plan state | Server quản lý; client không tự ghi |
| Security/admin | role, permission, policy, integration secret | Chỉ luồng quản trị được ủy quyền |

### 8.1 Response projection

Không serialize entity đầy đủ rồi hy vọng frontend ẩn field. Dùng response DTO theo use case và map các property được phép. Nếu API trả một object cho nhiều vai trò, policy phải quyết định field nào được đưa vào representation hiện tại.

Ví dụ một endpoint nhân viên:

~~~java
EmployeeResponse getEmployee(
    TenantContext tenant,
    Principal actor,
    EmployeeId employeeId
) {
    Employee employee = employees
        .findByTenantAndId(tenant.id(), employeeId)
        .orElseThrow(NotFoundException::new);

    policy.requireCanReadEmployee(actor, employee);

    return new EmployeeResponse(
        employee.id(),
        employee.displayName(),
        employee.email(),
        policy.canReadSalary(actor, employee)
            ? employee.salary()
            : null
    );
}
~~~

Ví dụ cần định nghĩa rõ semantics của field bị ẩn. Có thể dùng DTO khác nhau hoặc bỏ field khỏi response thay vì dùng null nếu null gây nhầm lẫn với dữ liệu trống. Không đưa property nhạy cảm vào cache hoặc serializer trung gian trước khi policy quyết định.

### 8.2 Request allowlist và mass assignment

Request DTO chỉ chứa field tenant member được phép sửa trong use case. Không bind trực tiếp JSON vào entity có tenantId, ownerId, role, billingPlan, creditLimit hoặc securitySettings.

Khi tạo object, server lấy tenant từ context và gán vào entity. Khi cập nhật, server tải object theo tenant rồi áp dụng domain method. Nếu client gửi tenantId khác, nên từ chối hoặc bỏ qua theo contract rõ ràng; tuyệt đối không thay ownership chỉ vì payload có field đó.

Chuyển object từ tenant này sang tenant khác là thao tác quản trị đặc biệt, cần kiểm tra quyền hai phía, kiểm tra quan hệ phụ thuộc, xử lý dữ liệu liên quan và audit. Không thực hiện bằng PATCH thông thường.

## 9. Cache isolation

Cache là một trong những nơi dễ phá vỡ tenant boundary vì cache hit có thể bỏ qua application service. Nếu cache key không phân biệt tenant, user hoặc policy ảnh hưởng response, dữ liệu của A có thể được trả cho B.

### 9.1 Thiết kế cache key

Với dữ liệu tenant-scoped, cache key tối thiểu phải phân vùng theo tenant. Tùy response, còn có thể cần user, role/policy version, locale, feature configuration và phiên bản dữ liệu:

~~~text
tenant:{tenantId}:order:{orderId}:view:{representationVersion}
tenant:{tenantId}:catalog:{locale}:{catalogVersion}
tenant:{tenantId}:dashboard:{roleScope}:{period}
~~~

Đây là ví dụ minh họa. Không thêm mọi claim vào key một cách máy móc; xác định chính xác yếu tố nào làm response khác nhau. Với response cá nhân hoặc nhạy cảm, không dùng shared cache thường an toàn và dễ kiểm soát hơn.

Không lấy tenant ID trong cache key từ header chưa xác minh. Key phải được tạo từ tenant context đáng tin cậy sau bước kiểm tra membership. Không dùng bearer token thô làm một phần cache key hoặc log.

### 9.2 Cache value và cache metadata

Tenant ID phải được gắn với cache entry hoặc metadata để phát hiện key/value mismatch. Nếu cache object theo ID toàn cục, khi đọc vẫn kiểm tra tenant của object trước khi trả. Không coi cache hit là bằng chứng object thuộc tenant hiện tại.

Với cache list/query, key cần phản ánh tenant, bộ lọc, sắp xếp, pagination và mọi policy scope ảnh hưởng kết quả. Tránh tái sử dụng cache entry từ query rộng cho query hẹp hơn nếu không có bước lọc lại an toàn.

### 9.3 Invalidation

Khi dữ liệu hoặc quyền thay đổi, invalidation cần đúng phạm vi tenant:

- Cập nhật object: xóa hoặc cập nhật key của object và các list/aggregate phụ thuộc.
- Thu hồi quyền: invalidate representation chứa dữ liệu mà principal không còn được xem.
- Xóa tenant hoặc đóng tenant: vô hiệu hóa namespace cache của tenant.
- Đổi cấu hình hoặc feature flag: invalidate các key phụ thuộc cấu hình.
- Chuyển object giữa tenant: xóa cả namespace cũ và namespace mới, xử lý cache liên quan.

TTL ngắn không thay thế invalidation khi thay đổi quyền cần có hiệu lực ngay. Với dữ liệu nhạy cảm, cân nhắc Cache-Control: private hoặc no-store và cấu hình CDN/reverse proxy tôn trọng chính sách.

## 10. Cô lập event, message và queue

Event thường được phát ra sau khi object thay đổi. Nếu payload không có tenant identity rõ ràng hoặc consumer không kiểm tra tenant, dữ liệu có thể vượt ranh giới dù API ban đầu đã kiểm soát tốt.

Một event nên có envelope rõ ràng:

~~~json
{
  "eventId": "evt-7f3a",
  "eventType": "order.updated",
  "tenantId": "tenant-A",
  "aggregateType": "order",
  "aggregateId": "order-123",
  "occurredAt": "2026-11-18T10:30:00Z",
  "schemaVersion": 2,
  "data": {
    "status": "SHIPPED"
  }
}
~~~

tenantId trong event là metadata do producer đáng tin tạo từ tenant context đã xác minh. Consumer không nên tin tenant ID từ payload như một credential; nó cần xác thực nguồn event, kiểm tra schema và dùng tenant ID để giới hạn xử lý dữ liệu tương ứng.

### 10.1 Event payload tối thiểu

Không serialize toàn bộ entity vào event. Chỉ đưa dữ liệu consumer thực sự cần. Event nội bộ có thể chứa ID và trạng thái thay đổi; consumer tải object qua tenant-scoped repository nếu cần thêm dữ liệu. Webhook gửi ra bên ngoài cần DTO riêng, không dùng payload nội bộ đầy đủ.

Không đưa password hash, token, payment secret, internal risk details hoặc dữ liệu cá nhân không cần thiết vào event. Event log và dead-letter queue thường tồn tại lâu và có nhiều người vận hành truy cập.

### 10.2 Consumer phải dựng lại tenant context

Khi xử lý message:

1. Xác thực broker/source hoặc chữ ký message theo kiến trúc.
2. Kiểm tra event schema, event ID, loại sự kiện và tenant ID.
3. Kiểm tra producer/service có quyền phát event cho loại tenant/resource đó.
4. Tạo tenant context riêng cho message, không dùng context còn sót từ thread hoặc message trước.
5. Thực hiện truy vấn và ghi dữ liệu với tenant scope.
6. Kiểm tra quyền của consumer/service và property cần xử lý.
7. Ghi idempotency/deduplication theo tenant và event ID.
8. Kết thúc transaction thì xóa context khỏi thread-local hoặc execution context.

Nếu event có thể được replay, consumer phải xử lý lặp an toàn. Không dùng eventId toàn cục thay thế tenant validation; unique key có thể là (tenant_id, event_id) tùy mô hình.

### 10.3 Queue và partition

Có thể partition topic hoặc queue theo tenant để hỗ trợ ordering, quota và vận hành. Nhưng partition key không phải cơ chế authorization: consumer vẫn phải kiểm tra tenant context. Một queue chung cần kiểm soát quyền producer/consumer, subscription filter, dead-letter queue và retention.

Với tenant có lưu lượng lớn, cân nhắc fairness và giới hạn riêng để một tenant không chiếm worker. Không cho client chọn queue hoặc routing key tùy ý để gửi message sang namespace khác.

### 10.4 Transactional outbox

Nếu application ghi database rồi publish event riêng, có thể xảy ra trạng thái database commit nhưng event không được gửi, hoặc event được gửi dù transaction rollback. Transactional outbox lưu event trong cùng transaction với dữ liệu nghiệp vụ; publisher đọc outbox rồi gửi broker.

Outbox row cần tenant ID, aggregate ID, event ID và payload đã lọc. Publisher và consumer phải hỗ trợ retry/idempotency. Khi đọc outbox, luôn phân quyền theo service và tenant; không để một publisher worker đọc nhầm namespace hoặc gửi event sang tenant khác.

## 11. Background job và tác vụ bất đồng bộ

Job thường được tạo từ request nhưng thực hiện sau đó, khi request context đã kết thúc. Nếu chỉ lưu object ID rồi worker tìm theo ID toàn cục, tenant boundary có thể bị mất.

Payload job nên chứa:

- Tenant ID được server xác minh tại thời điểm tạo.
- Actor/service identity và mục đích nghiệp vụ.
- Object ID và loại thao tác.
- Correlation ID, idempotency key và schema version.
- Các tham số đã được validate, không phải URL hoặc command tùy ý.

Worker phải xác thực nguồn job, dựng tenant context mới, kiểm tra tenant vẫn hoạt động và quyền hiện tại còn hiệu lực nếu nghiệp vụ yêu cầu. Không mặc định quyền tại lúc enqueue luôn còn hợp lệ khi job chạy. Với thao tác có side effect, dùng idempotency và kiểm tra trạng thái object trước khi thực hiện.

Không truyền tenant context qua ThreadLocal mà quên xóa khi thread pool tái sử dụng. Dùng cơ chế context propagation có kiểm soát; đặt context trong phạm vi xử lý và luôn cleanup trong finally.

## 12. File, object storage và export

Tenant isolation phải áp dụng cả file và artifact:

- Dùng bucket/container riêng hoặc prefix namespace có tenant ID do server tạo.
- Không ghép đường dẫn từ tenant ID do client tùy ý gửi.
- Kiểm tra quyền object trước khi cấp signed URL.
- Signed URL phải có thời hạn ngắn, quyền tối thiểu, đúng object và đúng method; tránh ghi URL đầy đủ vào log/referrer.
- Không cho phép đổi key/path để truy cập file của tenant khác.
- Quét virus và xử lý file trong worker có tenant context; file tạm cũng phải phân vùng.
- Export chỉ chứa property được phép; file kết quả có ACL, TTL, mã hóa và audit.
- Khi tenant bị xóa hoặc chuyển dữ liệu, xóa bản sao ở cache, object storage, backup theo chính sách retention.

Tên file hoặc UUID khó đoán không phải cơ chế phân quyền. Mọi lần download vẫn cần kiểm tra quyền hoặc dùng capability URL được cấp an toàn.

## 13. Search, analytics và dữ liệu dẫn xuất

Search index, vector database, data warehouse và dashboard thường được xây dựng bất đồng bộ từ dữ liệu gốc. Chúng có thể làm mất tenant boundary nếu document không giữ tenant ID hoặc query filter bị bỏ qua.

Nguyên tắc:

- Mọi document/record dẫn xuất phải giữ tenant identity và object ownership cần thiết.
- Search query luôn gắn tenant filter ở server; không để client tự quyết định filter duy nhất.
- Với vector search, tenant filter phải được áp dụng trước hoặc trong truy vấn theo khả năng hệ thống; không chỉ lọc kết quả sau khi đã trả dữ liệu nội bộ ra ứng dụng.
- Dashboard và aggregate phải tính trong tenant scope; count/facet cũng có thể tiết lộ thông tin.
- Export/data pipeline cần quyền service riêng, partition theo tenant và audit.
- Khi xóa hoặc chuyển object, cập nhật search index, vector store, analytics và cache liên quan.

Nếu một mô hình dữ liệu dùng chung nhiều tenant, đánh giá cả rò rỉ qua ranking, gợi ý, autocomplete và kết quả tương tự. Ngay cả khi nội dung cuối cùng bị lọc, thứ tự hoặc điểm số có thể làm lộ sự hiện diện của dữ liệu tenant khác.

## 14. Transaction, concurrency và thay đổi tenant

Tenant context phải ổn định trong suốt một transaction. Không cho phép request thay tenant sau khi đã tải object hoặc mở transaction. Nếu một thao tác thật sự cần tương tác hai tenant, hãy thiết kế như workflow cross-tenant riêng với quyền, audit, trạng thái và xử lý lỗi rõ ràng.

Một số invariant cần bảo vệ:

- Object con và object cha thuộc cùng tenant.
- Quan hệ owner/customer/project không trỏ sang tenant khác nếu không được phép.
- Cache/event/job mang tenant ID tương ứng với object.
- Khi chuyển object, cập nhật toàn bộ quan hệ, quyền, index và bản sao trong một quy trình có thể phục hồi.
- Kiểm tra quyền và ghi thay đổi trong transaction hoặc dùng version/optimistic locking để tránh race condition.

Nếu tenant membership bị thu hồi trong lúc request đang chạy, xác định điểm hiệu lực: có thể kiểm tra membership lúc bắt đầu request hoặc yêu cầu kiểm tra lại trước thao tác nhạy cảm. Với tác vụ dài, nên kiểm tra quyền hiện tại trước side effect quan trọng.

## 15. Kiểm thử tenant isolation

Kiểm thử cần có ít nhất hai tenant độc lập, mỗi tenant có user, object, property, cache entry và event riêng. Test chỉ với một tenant không thể chứng minh không có rò rỉ chéo.

| Nhóm test | Kịch bản | Kết quả mong đợi |
|---|---|---|
| Tenant selector | User A đổi header/path sang tenant B | Bị từ chối nếu không có membership/grant |
| Object read | A dùng ID object của B | Không đọc được |
| Object write | A cập nhật object của B | Không có thay đổi dữ liệu |
| List/search | A tìm kiếm hoặc aggregate khi B có dữ liệu tương tự | Không có row/count/facet của B |
| Relationship | Tạo order A tham chiếu customer B | Database constraint từ chối |
| Property | A đọc field nội bộ hoặc sửa tenantId/ownerId | Field không lộ hoặc update bị từ chối |
| Cache | A gọi trước, B gọi cùng URL/resource ID sau | B không nhận cache entry của A |
| Cache invalidation | Thu hồi quyền hoặc xóa object A | Bản sao cache đúng phạm vi được vô hiệu hóa |
| Event consumer | Gửi event tenant A rồi xử lý bằng consumer context B | Không xử lý chéo tenant |
| Queue replay | Replay job/event sau khi membership bị thu hồi | Áp dụng chính sách quyền hiện tại |
| File | B thử signed URL hoặc object key của A | Bị từ chối |
| RLS | Query bằng database role của application với context khác/thiếu | Không đọc hoặc ghi row ngoài tenant |
| Connection pool | Tái sử dụng connection sau request tenant A cho tenant B | Không còn context A |
| Bulk operation | Trộn ID của A và B trong cùng payload | Không thay đổi object ngoài phạm vi |
| Race condition | Membership hoặc tenant state đổi khi job đang chạy | Side effect tuân thủ điểm kiểm tra quyền |

### 15.1 Kiểm thử âm và fuzzing

Thử tenant ID rỗng, null, sai định dạng, tenant không tồn tại, tenant bị khóa, header trùng, path encoding, ID của tenant khác và payload có tenant ID lồng sâu. Kiểm tra cả response body, status, thời gian phản hồi, count và log để tránh side channel.

Tự động tạo test cho repository/query quan trọng: mỗi query với tenant A phải không trả row B dù ID object là hợp lệ. Test constraint bằng cách cố tạo quan hệ chéo tenant. Test cache theo thứ tự A trước B và B trước A để phát hiện lỗi phụ thuộc thứ tự.

## 16. Giám sát và audit

Theo dõi:

- Request có tenant selector không hợp lệ hoặc membership bị từ chối.
- Object lookup thất bại do tenant mismatch.
- Request cố sửa tenantId, ownerId hoặc quan hệ cross-tenant.
- Cache hit trên namespace tenant không mong đợi.
- Event/job có tenant context thiếu hoặc không khớp object.
- Consumer retry, dead-letter và lỗi schema theo tenant.
- RLS policy violation, query không có tenant context và quyền database bất thường.
- Export, file download hoặc search có lưu lượng vượt mức bình thường.

Audit event nên ghi principal/service, tenant ID, object ID, action, kết quả policy, request/event/job ID và thời điểm. Tránh log nội dung nhạy cảm hoặc token. Dùng tenant ID nội bộ trong log có kiểm soát truy cập; không đưa giá trị có cardinality lớn thành metric label nếu gây quá tải hệ thống giám sát.

Đặt cảnh báo khi một principal thử nhiều tenant selector, một cache namespace có mismatch, consumer xử lý event không có tenant context hoặc một service đọc dữ liệu từ tenant ngoài phạm vi. Khi phát hiện rò rỉ, có thể tạm dừng consumer, tắt cache route, khóa integration hoặc thu hồi credential trong phạm vi sự cố.

## 17. Các lỗi thiết kế thường gặp

1. **Tin tenant ID từ client:** người dùng tự chọn tenant khác bằng header hoặc body.
2. **Chỉ kiểm tra tenant ở controller:** service/repository khác có thể bỏ qua context.
3. **Truy vấn theo object ID đơn lẻ:** object ID không chứng minh quyền hoặc tenant ownership.
4. **Không có composite constraint:** object con có thể tham chiếu object cha của tenant khác.
5. **Chỉ lọc record nhưng quên count/facet/export:** dữ liệu tổng hợp vẫn rò rỉ.
6. **Cache key thiếu tenant:** response của tenant này được dùng cho tenant khác.
7. **Cache key lấy từ header không xác minh:** kẻ tấn công giả mạo namespace.
8. **Serialize entity hoặc event đầy đủ:** property nội bộ bị phát ra ngoài.
9. **Consumer không dựng tenant context:** xử lý message theo context còn sót hoặc mặc định.
10. **Background job chỉ chứa object ID:** mất tenant identity sau khi request kết thúc.
11. **Dùng connection pool nhưng không reset tenant context:** request sau kế thừa context trước.
12. **Coi RLS là lớp bảo vệ duy nhất:** owner, superuser hoặc bảng chưa có policy có thể bypass.
13. **Signed URL không giới hạn:** URL bị chia sẻ hoặc tồn tại quá lâu.
14. **Không cập nhật search/cache khi xóa hoặc chuyển tenant:** dữ liệu cũ vẫn xuất hiện ở bản sao.

## 18. Quy trình thiết kế cô lập cho một luồng API

Với mỗi endpoint hoặc luồng nghiệp vụ:

1. Xác định principal và cách chọn tenant; xác minh membership/delegated grant phía server.
2. Tạo tenant context bất biến và truyền qua request/service/repository.
3. Xác định object, quan hệ và property thuộc tenant; lập ma trận read/write.
4. Thiết kế schema với tenant key, composite foreign key, unique constraint và index phù hợp.
5. Bắt buộc tenant filter ở mọi query, list, search, aggregate, export và bulk operation.
6. Dùng DTO/projection allowlist và domain policy; không serialize entity.
7. Phân vùng cache key/value và quy định invalidation khi quyền/dữ liệu thay đổi.
8. Thiết kế event/job envelope có tenant identity; consumer dựng context mới và xử lý idempotent.
9. Cô lập file, search index, analytics, webhook và các bản sao dữ liệu.
10. Cân nhắc RLS như lớp bảo vệ database bổ sung; kiểm thử bằng application role và connection pool.
11. Viết test cross-tenant cho đọc, ghi, property, cache, event, queue, file và RLS.
12. Thiết lập audit/monitoring và quy trình ứng phó khi phát hiện dữ liệu vượt tenant boundary.

## 19. Checklist rà soát

- [ ] Tenant context được tạo từ principal đã xác thực và membership/grant đã kiểm tra.
- [ ] Không tin tenant ID từ header, path hoặc body nếu chưa xác minh phía server.
- [ ] Tenant context bất biến trong request/transaction và được cleanup khi kết thúc.
- [ ] Mọi object query, list, search, count, aggregate, export và bulk operation đều có tenant scope.
- [ ] Schema có tenant key và constraint ngăn quan hệ chéo tenant.
- [ ] Quyền object và property được kiểm tra riêng trong đúng tenant.
- [ ] Request/response DTO chỉ chứa property được phép; server quản lý tenantId/ownerId.
- [ ] Cache key/value phân vùng tenant và không dùng selector chưa xác minh.
- [ ] Invalidation bao phủ dữ liệu, quyền, chuyển tenant và xóa tenant.
- [ ] Event/job có tenant metadata do producer đáng tin tạo; consumer dựng context mới.
- [ ] Queue, dead-letter, webhook, file, export, search và analytics giữ tenant boundary.
- [ ] RLS nếu dùng được kiểm thử bằng role ứng dụng, transaction và connection pool thực tế.
- [ ] Có kiểm thử ít nhất hai tenant, gồm negative test và race condition.
- [ ] Audit/alert đủ để phát hiện truy cập chéo tenant mà không log bí mật.

Cô lập tenant chỉ hiệu quả khi cùng một ranh giới được duy trì trong mọi bản sao và mọi đường xử lý dữ liệu. Tenant context đáng tin cậy, truy vấn có tenant scope, constraint ở database, property policy, cache key riêng và event/job có context rõ ràng tạo thành nhiều lớp bảo vệ bổ sung. Kiểm thử chéo tenant phải bao phủ cả object, property, cache, event, file và tác vụ nền để phát hiện những đường rò rỉ mà kiểm thử endpoint đơn lẻ thường bỏ sót.

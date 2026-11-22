# Xác thực và phân quyền truy cập kho dữ liệu

Một API Java có thể sử dụng `PreparedStatement` đúng cách, mở transaction hợp lệ và ghi dữ liệu bền vững, nhưng vẫn làm lộ thông tin khách hàng nếu kết nối database dùng tài khoản quản trị có quyền đọc toàn bộ dữ liệu. Tương tự, người dùng đã đăng nhập thành công chưa chắc có quyền xem đơn hàng của người khác. Nếu hệ thống chỉ kiểm tra “đã có token” rồi truy vấn `SELECT * FROM orders WHERE id = ?`, việc đổi ID trong request có thể khiến dữ liệu của người khác bị lộ.

**Xác thực** (*authentication*) trả lời câu hỏi **“Ai đang thực hiện yêu cầu?”**. **Phân quyền** (*authorization*) trả lời **“Danh tính đã xác thực được phép làm gì trên tài nguyên nào, trong ngữ cảnh nào?”**. Ở một hệ persistence thực tế, cả người dùng cuối, ứng dụng Java, tài khoản database, job migration và công cụ backup đều có danh tính cùng quyền riêng. Không thể thay thế chính sách phân quyền bằng việc “database đã đặt mật khẩu”.

Bài học thuộc chương **An toàn dữ liệu** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Người học sẽ thiết kế ranh giới truy cập kho dữ liệu cho Java, kiểm soát credential, xây dựng vai trò tối thiểu, phân quyền theo tenant và đối tượng, bảo vệ kết nối, quản lý transaction/pool, theo dõi truy cập và kiểm thử trường hợp bị từ chối. Trọng tâm là kết hợp **tính đúng đắn của dữ liệu**, **bảo mật** và **khả năng vận hành**.

## 1. Xác thực và phân quyền là hai bước khác nhau

Ví dụ một khách hàng đăng nhập và yêu cầu xem đơn hàng `123`:

~~~http
GET /orders/123
Authorization: Bearer <access-token>
~~~

Server phải giải quyết hai vấn đề độc lập:

1. **Authentication:** kiểm tra token/chứng thực, thời hạn, chữ ký hoặc nguồn cấp, audience và các thuộc tính cần thiết để nhận diện người gửi. Nếu không xác thực được, không tiếp tục như một khách hàng hợp lệ.
2. **Authorization:** sau khi xác định khách hàng là `customer-42`, kiểm tra đơn `123` có nằm trong phạm vi khách hàng được phép xem không. Việc token hợp lệ **không** cho phép đọc mọi `order_id`.

Đồng thời, API truy cập PostgreSQL bằng một **database principal** như `shop_runtime`. Database phải xác thực principal đó và chỉ cho phép các thao tác đã cấp. Người dùng cuối thường **không kết nối trực tiếp tới database**; API đóng vai trò thực thi quyền thay mặt họ.

| Thành phần | Danh tính cần xác định | Quyền cần kiểm soát |
| --- | --- | --- |
| Người dùng cuối | User/service account đã xác thực tại API | Được xem/sửa những đơn nào? |
| Ứng dụng Java | Service/workload identity hoặc DB login | Được SELECT/INSERT/UPDATE trên bảng nào? |
| Job migration | Tài khoản vận hành riêng | Được ALTER schema, CREATE INDEX vào thời điểm nào? |
| Job báo cáo | Danh tính đọc dữ liệu được phê duyệt | Chỉ SELECT những trường/bảng nào? |
| Job backup | Tài khoản backup với quyền phù hợp | Có thể sao lưu, đọc bản sao và phục hồi vào đâu? |
| Nhà vận hành | Danh tính cá nhân có audit | Có thể truy cập production qua quy trình nào? |

Một kết nối TLS bảo vệ đường truyền và có thể hỗ trợ xác thực hai đầu, nhưng **TLS không tự quyết định khách hàng được đọc đơn nào**. Xác thực thành công cũng không phải bằng chứng phân quyền thành công.

## 2. Nhiều lớp bảo vệ trên đường truy cập dữ liệu

Một đường đi điển hình:

~~~mermaid
flowchart TD
    A[Client / người dùng] --> B[API: xác thực token]
    B --> C[Use case: phân quyền theo tài nguyên]
    C --> D[Repository / persistence adapter]
    D --> E[DB connection: xác thực principal]
    E --> F[DB roles, GRANT / RLS / constraints]
    F --> G[(Dữ liệu)]
    H[Secret manager / workload identity] --> E
    I[TLS và network policy] -. bảo vệ đường kết nối .-> E
    J[Audit / monitoring] -. theo dõi .-> C
    J -. theo dõi .-> F
~~~

Đây là mô hình **defense in depth**: mỗi lớp giải quyết một nhóm rủi ro khác nhau.

- **Network boundary**: chỉ những workload được phép mới có đường tới database; cấu hình firewall/private network và TLS.
- **Credential/identity boundary**: database chấp nhận những service principal đã được cấp quyền, không dùng một mật khẩu quản trị chung cho mọi ứng dụng.
- **Database privilege boundary**: quyền ở mức database/schema/table/view/column/function, và row-level security nếu dùng.
- **Application authorization boundary**: người dùng A được thao tác với những resource nào, trong trạng thái nghiệp vụ nào.
- **Data handling boundary**: bí mật, dữ liệu nhạy cảm, backup, log và kết quả truy vấn được giới hạn theo chính sách.

Không lớp nào tự thay toàn bộ các lớp khác. Ví dụ `GRANT SELECT ON orders` cấp quyền SELECT cho một **service role**, nhưng nếu có hàng triệu đơn hàng thuộc nhiều khách, ứng dụng vẫn phải giới hạn đúng danh tính khách hàng; một role SELECT rộng không phải quyền đọc của mọi người dùng cuối.

## 3. Mô hình đe dọa: ai có thể gây truy cập sai?

Trước khi viết policy, xác định đường lỗi và đối tượng cần bảo vệ:

| Mối đe dọa | Ví dụ | Phòng vệ chính |
| --- | --- | --- |
| Client đổi tham số ID | Đổi `/orders/123` thành `/orders/124` | Object-level authorization tại use case và truy vấn |
| API thiếu ràng buộc tenant | `WHERE id = ?` nhưng không có tenant scope | Query scoping; RLS đúng thiết kế nếu cần |
| SQL injection | Input chèn thêm điều kiện truy vấn | Parameterized query, allowlist identifier, quyền DB tối thiểu |
| Credential bị lộ | JDBC URL/mật khẩu có trong log hoặc repo | Secret manager, rotation, revocation, giới hạn quyền |
| Service bị chiếm quyền | Kẻ tấn công dùng DB account của service | Least privilege, network segmentation, audit, hạn chế dữ liệu truy cập |
| Migration sai lệnh | Chạy `DROP TABLE` hoặc xóa dữ liệu nhầm | Role riêng, review, backup/restore, staged rollout |
| Báo cáo đọc quá mức | Dashboard SELECT toàn bộ PII | Role read-only, view/projection, column privileges |
| Tenant bị trộn dữ liệu | Cache key/repository không mang tenant | Kiểm tra tenant từ principal, contract test, RLS khi phù hợp |
| Backup/snapshot rò rỉ | File backup nằm ở bucket công khai | IAM, encryption, retention, audit, kiểm tra restore |

**Phân quyền dữ liệu có hai chiều:** kiểm soát **hành động** (đọc/ghi/xóa/DDL) và kiểm soát **phạm vi đối tượng** (tenant, khách hàng, hàng dữ liệu, cột nhạy cảm). Một chính sách chỉ kiểm soát hành động nhưng bỏ phạm vi vẫn có thể dẫn đến rò rỉ dữ liệu.

## 4. Principal, role và nguyên tắc quyền tối thiểu

**Principal** là danh tính được hệ thống xác thực. **Role** là một cơ chế gom hoặc gán quyền, có thể đi kèm login tùy công nghệ. PostgreSQL dùng role cho cả danh tính và nhóm quyền; không nên suy rằng tên role luôn đồng nghĩa với một cá nhân.

Nguyên tắc **least privilege**:

> Mỗi workload chỉ được cấp đúng quyền cần thiết, trên đúng phạm vi dữ liệu, trong thời gian cần thiết; không dùng quyền rộng hơn để tránh việc phải cấu hình.

Ví dụ tách vai trò:

| Role | Công việc | Quyền nên có |
| --- | --- | --- |
| `shop_runtime` | Xử lý các use case thông thường | SELECT và các thao tác DML cần thiết trên bảng được chọn |
| `shop_readonly` | Đọc các bản tổng hợp được phê duyệt | SELECT trên view/bảng/cột phù hợp, không ghi |
| `shop_migrator` | Thay đổi lược đồ qua pipeline | DDL trong phạm vi và cửa sổ được phê duyệt |
| `shop_backup` | Sao lưu/khôi phục theo chính sách | Quyền backup cần thiết; không dùng role app thông thường |
| `shop_owner` | Sở hữu schema và object | NOLOGIN khi có thể; không dùng làm credential runtime |

Không cấp `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `BYPASSRLS`, `TRUNCATE` hoặc `CREATE` chỉ để một endpoint `GET /orders` hoạt động. Nếu service cần thêm quyền, phải xác định **use case và tài nguyên** trước khi tăng phạm vi.

**Quyền tối thiểu cần được kiểm chứng, không chỉ đặt tên:** một role tên `readonly_user` vẫn có thể ghi nếu đã được `GRANT INSERT` qua role khác. Phải xem role membership, quyền mặc định, quyền thừa kế, schema grants và object grants.

## 5. PostgreSQL: cấp quyền cụ thể thay vì dùng tài khoản quản trị

Đoạn SQL dưới đây minh họa cách tổ chức. Chạy việc tạo role/schema/GRANT bằng **migration/admin principal được ủy quyền**, không dùng chúng trong HTTP handler. Tên DB giả định là `shopdb` và bảng `app.orders` đang được tạo bởi owner thích hợp:

~~~sql
-- Bước quản trị: tạo các principal/role (credential cấu hình riêng).
CREATE ROLE shop_owner NOLOGIN;
CREATE ROLE shop_runtime LOGIN;
CREATE ROLE shop_readonly LOGIN;

-- Một role có quyền tạo schema/object thực hiện các bước phù hợp.
CREATE SCHEMA app AUTHORIZATION shop_owner;

-- DDL bảng thực thi dưới owner hoặc vai trò có quyền sở hữu.
SET ROLE shop_owner;
CREATE TABLE app.orders (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    customer_id  BIGINT NOT NULL,
    status       TEXT NOT NULL,
    total_amount NUMERIC(18, 2) NOT NULL
                 CHECK (total_amount >= 0)
);
RESET ROLE;

-- Chỉ cấp khả năng kết nối và sử dụng schema khi cần.
GRANT CONNECT ON DATABASE shopdb TO shop_runtime, shop_readonly;
GRANT USAGE ON SCHEMA app TO shop_runtime, shop_readonly;

-- API chỉ được đọc các cột phục vụ use case.
GRANT SELECT (id, tenant_id, customer_id, status, total_amount)
    ON app.orders TO shop_runtime;

-- Chỉ được tạo/sửa các cột được xác định trước.
GRANT INSERT (tenant_id, customer_id, status, total_amount)
    ON app.orders TO shop_runtime;
GRANT UPDATE (status)
    ON app.orders TO shop_runtime;

-- Job báo cáo mẫu chỉ cần đọc ID/trạng thái.
GRANT SELECT (id, status)
    ON app.orders TO shop_readonly;
~~~

**Giải thích:**

- `shop_owner` sở hữu bảng nhưng không cho phép kết nối trực tiếp bằng login. Một pipeline migration được cấp quyền quản trị phù hợp có thể tạo bảng dưới owner đó; `SET ROLE` chỉ thành công khi người thực thi được phép chuyển role.
- `shop_runtime` không sở hữu bảng và không được tự đổi schema, xóa hàng hoặc cập nhật `tenant_id`.
- `shop_readonly` không được ghi. Grant theo cột giúp hạn chế bề mặt truy cập nhưng cần cân nhắc kết quả từ **view, function, role kế thừa** và những grant khác.
- `GRANT CONNECT` không khẳng định role sẽ đăng nhập thành công: PostgreSQL còn có **cấu hình xác thực kết nối** (như `pg_hba.conf` trong triển khai tự quản hoặc cơ chế của dịch vụ managed DB) và credential phù hợp.
- Quyền column-level trong ví dụ chưa giải quyết quyền **đối với từng hàng**. Cần application scoping hoặc RLS.

### Quyền của bảng, schema và database khác nhau

Role được `GRANT SELECT ON app.orders` vẫn cần quyền sử dụng schema thích hợp. Quyền `CONNECT` vào database không mặc nhiên được phép đọc bảng. Ngược lại, quyền `USAGE ON SCHEMA app` không có nghĩa được SELECT mọi bảng trong schema.

Đặc biệt, phải kiểm tra quyền mặc định của môi trường hiện hữu: role có thể hưởng quyền qua `PUBLIC` hoặc role membership khác. Ví dụ muốn siết `CONNECT` mặc định từ `PUBLIC` phải đánh giá ảnh hưởng đến các client hiện có trước khi `REVOKE`. Không chạy lệnh revoke hàng loạt trên production mà chưa có kế hoạch khôi phục.

## 6. Quyền đối với object mới: tránh privilege drift

Một lỗi vận hành phổ biến là grant quyền trên các bảng hiện có, sau đó tạo một bảng mới mà ứng dụng không truy cập được — hoặc ngược lại, vô tình cấp quá rộng vì dùng wildcard.

PostgreSQL cung cấp **default privileges** cho những object được tạo **trong tương lai** bởi một role xác định. Ví dụ:

~~~sql
-- Chạy bởi role được phép điều chỉnh default privileges
-- của shop_owner; áp dụng khi shop_owner tạo bảng mới trong app.
ALTER DEFAULT PRIVILEGES FOR ROLE shop_owner IN SCHEMA app
    GRANT SELECT ON TABLES TO shop_readonly;
~~~

Điều cần hiểu:

- Lệnh chỉ ảnh hưởng **bảng tạo sau này** bởi role `shop_owner` trong schema được chỉ định; nó không tự sửa grants của bảng đã tồn tại.
- Nếu migration chạy bằng **role tạo object khác**, default privileges cấu hình cho `shop_owner` có thể không áp dụng.
- Grant SELECT cho **mọi bảng mới** có thể quá rộng cho dữ liệu nhạy cảm. Với môi trường yêu cầu least privilege nghiêm ngặt, có thể chọn explicit grants trong từng migration thay vì mặc định wildcard.
- Quyền với sequence, function, type và view không phải lúc nào cũng giống quyền với table. Ví dụ khi dùng `SERIAL`/sequence trực tiếp, có thể cần quyền sequence riêng; `IDENTITY` có semantics khác.

Kiểm kê quyền sau migration phải là một phần của checklist triển khai, không chỉ thao tác làm một lần khi khởi tạo hệ thống.

## 7. Phân quyền tầng ứng dụng: resource ownership, RBAC và ABAC

Database role bảo vệ phạm vi hoạt động của **ứng dụng**, còn use case phải bảo vệ phạm vi hoạt động của **người dùng**.

Những mô hình thường gặp:

- **RBAC (Role-Based Access Control):** vai trò như `CUSTOMER`, `SUPPORT`, `ADMIN` được phép thực hiện một nhóm hành động.
- **ABAC (Attribute-Based Access Control):** quyền phụ thuộc thuộc tính của principal, resource và ngữ cảnh, ví dụ tenant, quan hệ sở hữu, trạng thái đơn, nhóm hỗ trợ được phân công.
- **Object-level authorization:** kiểm tra quyền đối với chính ID tài nguyên được yêu cầu.
- **Policy-based authorization:** tập trung hóa quy tắc trong một policy service/module thay vì rải ở controller và repository.

Ví dụ chính sách:

~~~text
ALLOW viewOrder(principal, order)
  IF principal.tenantId == order.tenantId
  AND (
      principal.customerId == order.customerId
      OR principal.hasPermission("orders:support:read")
         AND principal.isAssignedTo(order)
  )
~~~

Tên role `SUPPORT` đơn thuần chưa đủ: nhân viên hỗ trợ có thể chỉ được xem đơn trong phạm vi họ xử lý. `ADMIN` cũng không nhất thiết có quyền truy xuất dữ liệu khách hàng ngoài tenant hoặc dữ liệu nhạy cảm chưa được phê duyệt.

### Tránh lỗi IDOR/BOLA

Một lỗi nguy hiểm:

~~~java
// Sai nếu người dùng được tự chọn orderId mà không kiểm tra quyền.
Order order = orders.findById(request.orderId());
return toDto(order);
~~~

Hợp đồng Repository nên cho phép phạm vi phân quyền đi cùng truy vấn, chẳng hạn:

~~~java
public interface OrderReadPort {
    Optional<OrderSummary> findVisibleForCustomer(
            long tenantId, long customerId, long orderId);
}
~~~

Một truy vấn JDBC phù hợp:

~~~sql
SELECT id, status, total_amount
FROM app.orders
WHERE id = :orderId
  AND tenant_id = :authenticatedTenantId
  AND customer_id = :authenticatedCustomerId;
~~~

`authenticatedTenantId` và `authenticatedCustomerId` **phải lấy từ principal đã xác thực/ủy quyền**, không tin trực tiếp các trường `tenantId` hoặc `customerId` trong request body.

Nếu không tìm thấy do **không tồn tại** hoặc **không đủ quyền**, API có thể chọn trả `404` để hạn chế rò rỉ sự tồn tại của tài nguyên, hoặc `403` theo chính sách sản phẩm. Việc chọn mã HTTP không thay thế kiểm tra quyền. Cần nhất quán và tránh để nội dung response vô tình tiết lộ thông tin.

## 8. Bảo vệ đường ghi: không chỉ kiểm tra quyền lúc đọc

Việc phân quyền phải áp dụng cả **SELECT, INSERT, UPDATE, DELETE và các hành động nghiệp vụ**. Ví dụ user có thể đọc đơn của mình nhưng không có quyền hủy một đơn đã giao:

~~~text
customer A
  có thể xem order 123 của A
  có thể đổi địa chỉ khi trạng thái PENDING
  không thể đổi địa chỉ khi trạng thái SHIPPED
  không thể chuyển order 123 sang REFUNDED bằng cách gửi status tùy ý
~~~

Application service cần kiểm tra:

1. Principal có quyền thực hiện **loại hành động** này không?
2. Resource thuộc tenant/customer nào và có nằm trong phạm vi được phép không?
3. Trạng thái nghiệp vụ có cho phép hành động không?
4. Ghi xuống DB có bảo vệ được **race** giữa đọc và cập nhật không?

Ví dụ lệnh cập nhật có điều kiện:

~~~sql
UPDATE app.orders
SET status = 'CANCELLED'
WHERE id = :orderId
  AND tenant_id = :tenantId
  AND customer_id = :customerId
  AND status = 'PENDING';
~~~

Kiểm tra affected row count: `1` là đã cập nhật được hàng phù hợp tại thời điểm ghi; `0` nghĩa không có hàng thỏa, có thể do không tồn tại/không đủ quyền/trạng thái đã đổi. Đừng báo thành công nếu 0 hàng bị cập nhật. Nếu nhiều cột/aggregate tham gia bất biến, cần transaction, optimistic locking hoặc cách điều phối phù hợp.

**Phân quyền và consistency liên quan nhau:** kiểm tra ownership ở một query rồi ghi theo ID ở query khác **có thể** tạo lỗ hổng nếu ownership/trạng thái có thể đổi giữa hai bước. Đặt các điều kiện bất biến thiết yếu ngay trong lệnh ghi hoặc transaction với khóa/phiên bản thích hợp.

## 9. Row-Level Security trong PostgreSQL

**Row-Level Security (RLS)** cho phép PostgreSQL áp dụng policy ở mức hàng khi một role truy cập bảng. Đây là một lớp phòng vệ bổ sung có ích trong hệ multi-tenant; không phải thay thế hoàn toàn xác thực và ủy quyền ứng dụng.

Giả định bảng `app.orders` có `tenant_id` và role `shop_runtime` **không** sở hữu bảng, không là superuser, không có `BYPASSRLS`. Một chính sách minh họa dùng tenant ID đặt trong transaction:

~~~sql
-- Chạy bằng role có quyền sửa bảng/policy.
ALTER TABLE app.orders ENABLE ROW LEVEL SECURITY;

-- Buộc policy áp dụng cho table owner trong các trường hợp thích hợp;
-- superuser và role BYPASSRLS vẫn có ngoại lệ riêng.
ALTER TABLE app.orders FORCE ROW LEVEL SECURITY;

CREATE POLICY orders_select_tenant
ON app.orders
FOR SELECT
TO shop_runtime
USING (
    tenant_id = NULLIF(
        current_setting('app.tenant_id', true), ''
    )::BIGINT
);

CREATE POLICY orders_insert_tenant
ON app.orders
FOR INSERT
TO shop_runtime
WITH CHECK (
    tenant_id = NULLIF(
        current_setting('app.tenant_id', true), ''
    )::BIGINT
);

CREATE POLICY orders_update_tenant
ON app.orders
FOR UPDATE
TO shop_runtime
USING (
    tenant_id = NULLIF(
        current_setting('app.tenant_id', true), ''
    )::BIGINT
)
WITH CHECK (
    tenant_id = NULLIF(
        current_setting('app.tenant_id', true), ''
    )::BIGINT
);
~~~

**Ý nghĩa:**

- `USING` giới hạn những hàng có thể đọc hoặc được chọn để UPDATE theo policy tương ứng.
- `WITH CHECK` kiểm tra **trạng thái hàng mới** khi INSERT/UPDATE. Nếu cho phép UPDATE `tenant_id` mà không có điều kiện phù hợp, dữ liệu có thể bị chuyển tenant sai.
- Khi `app.tenant_id` chưa được đặt, biểu thức trả `NULL`, điều kiện so sánh không trở thành true và các hàng không được phép sẽ bị lọc/ghi bị từ chối theo chính sách.
- Nếu `app.tenant_id` chứa văn bản không chuyển được sang BIGINT, truy vấn có thể lỗi; tầng ứng dụng phải xác thực đầu vào trước.
- Nếu dùng thêm chính sách khác, phải hiểu **cách PostgreSQL kết hợp nhiều policy permissive/restrictive**. Thêm một policy rộng có thể vô tình nới phạm vi truy cập.
- Vì các policy trên chỉ áp dụng cho `shop_runtime`, `shop_readonly` **không tự thấy hàng nào** khi RLS bật; báo cáo cần một chính sách đọc được review riêng hoặc mô hình truy cập khác có kiểm soát.

**Quan trọng:** RLS không tự cấp quyền trên bảng. Role vẫn cần `GRANT` phù hợp. Ngược lại, `GRANT SELECT` không tự vô hiệu hóa policy áp dụng cho role.

### Các giới hạn của RLS cần biết

1. **Superuser và role có `BYPASSRLS`** có thể vượt policy. Chủ sở hữu bảng thường có cơ chế bypass trừ khi `FORCE ROW LEVEL SECURITY` được bật; phải kiểm tra đúng semantics/ngoại lệ với phiên bản PostgreSQL sử dụng.
2. Policy phụ thuộc một **custom session variable** như `app.tenant_id` chỉ an toàn khi đường đặt biến thuộc **mã ứng dụng đáng tin**. Một role SQL có thể tự gán biến tùy chỉnh nếu có khả năng thực thi SQL; do đó **không coi giá trị GUC do app đặt là ranh giới cứng chống lại SQL injection có khả năng thực thi SQL tùy ý hoặc service bị chiếm quyền**.
3. Nếu cần **cách ly tenant mạnh trước cả một DB principal bị xâm phạm**, cân nhắc principal/role hoặc database tách theo tenant, IAM/database role binding được kiểm soát, hoặc một cơ chế định danh tenant không tùy ý thay đổi bởi principal truy vấn.
4. `SECURITY DEFINER` function, view và các cơ chế truy cập gián tiếp có thể có quy tắc thực thi quyền khác nhau; phải audit khi đưa vào hệ thống.
5. Policy không thay thế các ràng buộc miền, constraint và transaction. Nó giải quyết kiểm soát hàng, không tự chống lost update hoặc double spend.

## 10. JDBC và connection pool: tenant context phải gắn với transaction

Khi dùng một connection pool, cùng một connection vật lý có thể lần lượt phục vụ request thuộc tenant A rồi tenant B. Nếu đặt session variable một lần mà quên reset, tenant B có nguy cơ thừa hưởng ngữ cảnh của A.

Với PostgreSQL, có thể dùng `set_config(..., true)` để đặt tham số **ở phạm vi transaction hiện tại**, tương đương ý định `SET LOCAL`. Ví dụ Java:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

public final class TenantOrderReader {
    private final DataSource dataSource;

    public TenantOrderReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    // tenantId và orderId đã được xác thực/kiểm tra ở use case;
    // chỉ dùng để minh họa cách buộc context vào transaction.
    public Optional<String> findStatus(
            long authenticatedTenantId, long orderId) throws SQLException {
        if (authenticatedTenantId <= 0 || orderId <= 0) {
            throw new IllegalArgumentException("ID không hợp lệ");
        }

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                // Đặt GUC transaction-local sau khi bắt đầu transaction.
                try (PreparedStatement ps = connection.prepareStatement(
                        "SELECT set_config('app.tenant_id', ?, true)")) {
                    ps.setString(1, Long.toString(authenticatedTenantId));
                    try (ResultSet ignored = ps.executeQuery()) {
                        ignored.next();
                    }
                }

                Optional<String> result;
                try (PreparedStatement ps = connection.prepareStatement(
                        "SELECT status FROM app.orders " +
                        "WHERE id = ? AND tenant_id = ?")) {
                    ps.setLong(1, orderId);
                    ps.setLong(2, authenticatedTenantId);
                    try (ResultSet rs = ps.executeQuery()) {
                        result = rs.next()
                                ? Optional.ofNullable(rs.getString(1))
                                : Optional.empty();
                    }
                }

                connection.commit();
                return result;
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }
                throw failure;
            }
        }
    }
}
~~~

Đoạn mã là **ví dụ JDBC thuần**, giả định role runtime thực sự chịu RLS và mọi truy vấn cần bảo vệ nằm trong transaction vừa đặt biến. `try-with-resources` trả connection cho pool sau thao tác; đặt tham số ở phạm vi transaction giúp giảm rủi ro rò context sau commit/rollback.

Các điểm dễ sai:

- **Autocommit:** nếu đặt biến transaction-local trong một statement autocommit rồi chạy SELECT ở statement khác, context có thể đã hết hiệu lực. Phải chủ động định nghĩa transaction boundary.
- **Pool reuse:** tránh `SET app.tenant_id = ...` dạng session-wide nếu không có cơ chế reset được kiểm chứng; rollback không mặc nhiên reset mọi session-level setting.
- **Async/reactive:** không truyền transaction context qua thread hoặc session khác mà không có cơ chế truyền ngữ cảnh đúng framework.
- **Spring transaction:** adapter phải dùng connection đang được transaction manager bind; tự gọi `DataSource.getConnection()` rồi quản lý commit riêng có thể bỏ qua transaction của use case.
- **RLS + ứng dụng:** vẫn giữ điều kiện `tenant_id = ?` ở các truy vấn quan trọng để làm rõ ý định, tối ưu truy vấn và giảm tác động lỗi cấu hình; đừng coi một biến GUC do application set là policy không thể giả mạo.
- **Hậu quả lỗi:** nếu connection bị mất đúng lúc commit của lệnh ghi, phải xử lý kết quả chưa chắc chắn; việc rollback trong catch không chứng minh dữ liệu chưa commit.

## 11. Xác thực kết nối database: password, chứng chỉ và IAM

Các cơ chế xác thực kết nối có mô hình đe dọa và vòng đời khác nhau:

| Cơ chế | Thực hiện | Điểm cần chú ý |
| --- | --- | --- |
| **Username/password** | Database xác thực secret gắn với login | Lưu giữ, rotation, độ mạnh thuật toán/DB config |
| **Client certificate / mTLS** | Xác thực danh tính client qua chứng chỉ | CA trust, mapping danh tính, expiry/revocation |
| **Managed identity / IAM DB auth** | Service dùng workload identity hoặc token ngắn hạn phù hợp dịch vụ | IAM policy, token lifetime, pool/refresh và mapping role |
| **OS/service identity** | Ánh xạ identity của host/workload với DB theo cơ chế triển khai | Ranh giới host/pod, giả mạo identity, audit |

Không có cơ chế nào thay thế `GRANT`/RLS. Ví dụ IAM xác nhận workload “order-service” được kết nối, nhưng role trong DB vẫn phải có quyền tối thiểu trên bảng. Token có hạn dùng ngắn có thể giảm rủi ro so với mật khẩu cố định, nhưng không tự giải quyết tài khoản đã có session kết nối dài hạn.

### Bảo vệ thông tin xác thực

- Ưu tiên **secret manager** hoặc workload identity được nền tảng hỗ trợ; không hardcode password/URI chứa secret trong source code, file cấu hình được commit hay unit test log.
- Giới hạn principal có quyền **đọc secret**, không chỉ quyền ghi DB; service khác không nên lấy credential của nhau.
- Tách credential cho **dev, staging và production**. Tránh sao chép mật khẩu production xuống máy cá nhân.
- Xoay vòng và thu hồi credential khi nhân sự/workload thay đổi, có sự cố hoặc theo chính sách.
- Không ghi `SQLException` với JDBC URL chứa credential hoặc dump toàn bộ config nhạy cảm vào log.
- Với mật khẩu, cấu hình phương thức xác thực database an toàn theo phiên bản/triển khai, chẳng hạn PostgreSQL SCRAM-SHA-256 khi phù hợp; tránh cơ chế xác thực yếu hoặc quá cũ.

Nếu credential bị lộ, việc thay password nhưng **không kiểm tra session cũ, token/cert còn hiệu lực và quyền role** có thể chưa khắc phục hết đường truy cập.

## 12. TLS và mạng: không để bảo mật “dừng ở firewall”

Một kết nối nội bộ giữa Java service và database vẫn có thể đi qua nhiều host/node/proxy. Mạng private **giảm bề mặt tấn công**, nhưng không chứng minh mọi traffic đều an toàn nếu workload/host khác bị chiếm quyền.

Hướng cấu hình:

1. Dùng TLS theo khả năng của driver và DB; kiểm tra **chuỗi chứng chỉ và hostname** đúng cách.
2. Khi dùng PostgreSQL JDBC, xem cấu hình như `sslmode=verify-full` và trust roots phù hợp; không mặc định `sslmode=require` xác minh danh tính server ở mức tương đương.
3. Dùng firewall/security group/network policy để chỉ mở cổng DB cho service được cho phép; tránh public Internet nếu không có lý do và kiểm soát phù hợp.
4. Xác định ai được đi qua proxy/load balancer/database gateway, cách TLS được terminate và đoạn đường nào còn được bảo vệ.
5. Xem giới hạn truy cập quản trị và bảo mật kênh backup/replication tương tự API runtime.

Ví dụ URL PostgreSQL JDBC **chỉ minh họa cấu hình kênh kết nối**, không chứa credential:

~~~text
jdbc:postgresql://db.internal.example:5432/shopdb?sslmode=verify-full
~~~

Ứng dụng nên nhận URL, trust configuration và credential từ cấu hình triển khai/secret manager, không hardcode dữ liệu thật. Tùy driver, cần cung cấp trust root đúng và giải quyết chứng chỉ host. Biến môi trường cũng có thể bị lộ qua process diagnostics hoặc quyền host không phù hợp; cần bảo vệ cùng các secret khác.

Không tắt hostname verification, dùng `trustAll` hoặc cố tình bỏ qua chứng chỉ vì môi trường “chỉ trong nội bộ”.

## 13. SQL injection và phân quyền là hai hàng rào bổ sung

SQL injection xảy ra khi dữ liệu không đáng tin bị diễn giải thành **cấu trúc câu lệnh**. Một anti-pattern:

~~~java
String sql = "SELECT id, status FROM app.orders WHERE id = "
        + request.getParameter("orderId");
~~~

Thay bằng bind parameter:

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT id, status FROM app.orders " +
        "WHERE id = ? AND tenant_id = ?")) {
    ps.setLong(1, orderId);
    ps.setLong(2, authenticatedTenantId);
    try (ResultSet rs = ps.executeQuery()) {
        // Chuyển dữ liệu sang DTO được cho phép.
    }
}
~~~

**Phân quyền database tối thiểu không thay parameterization**: nếu role runtime được SELECT tất cả đơn, SQL injection vẫn có thể rò rỉ dữ liệu trong phạm vi role đó. Ngược lại, prepared statement không thay object-level authorization: một query `WHERE id=?` với ID đã bind vẫn có thể trả đơn người khác nếu code không kiểm tra quyền.

Không thể bind **tên bảng, tên cột, keyword ORDER BY hoặc hướng sắp xếp** như bind giá trị. Nếu API cho phép sort động, dùng **allowlist** map từ giá trị API sang identifier SQL cố định:

~~~java
String orderBy = switch (requestedSort) {
    case "createdAt" -> "created_at";
    case "total" -> "total_amount";
    default -> throw new IllegalArgumentException("Sort không được phép");
};
// Ghép CHỈ các identifier cố định đã kiểm soát; mọi giá trị dùng bind.
~~~

Đừng cấp `CREATE FUNCTION`, `TRIGGER`, `EXECUTE` hoặc DDL rộng cho runtime chỉ để “có thể chạy mọi query”. Những quyền này có thể mở đường thực thi logic hoặc truy cập gián tiếp ngoài phạm vi dự kiến.

## 14. View, function, stored procedure và quyền gián tiếp

Quyền trên bảng chưa phải toàn bộ bức tranh. Một database còn có **view, function, procedure, trigger và extension**, mỗi loại có thể thực thi theo ngữ cảnh quyền khác nhau.

Ví dụ role báo cáo không cần đọc toàn bộ dữ liệu khách hàng. Có thể tạo một view do owner quản lý để trả tổng hợp:

~~~sql
-- DDL chạy bằng owner phù hợp.
CREATE VIEW app.order_status_counts AS
SELECT tenant_id, status, COUNT(*) AS order_count
FROM app.orders
GROUP BY tenant_id, status;

GRANT SELECT ON app.order_status_counts TO shop_readonly;
~~~

**Cảnh báo:** view không tự là ranh giới tenant an toàn. Quyền và RLS nhìn qua view phụ thuộc **owner/caller semantics và thuộc tính view** trên phiên bản PostgreSQL. Ở những cấu hình thông dụng, view có thể chạy với quyền của owner; khi owner có quyền vượt RLS, người dùng view có thể thấy nhiều dữ liệu hơn mong đợi. Nếu dùng view để thực thi tenant isolation, phải kiểm chứng cả role, phiên bản PostgreSQL, chế độ `security_invoker` nếu được hỗ trợ, và policy thực tế qua integration test. Ngược lại, nếu owner thực sự chịu `FORCE ROW LEVEL SECURITY` nhưng không có policy phù hợp, view có thể không trả dữ liệu.

Đối với function:

- `SECURITY INVOKER` và `SECURITY DEFINER` có ngữ nghĩa quyền khác nhau.
- Function `SECURITY DEFINER` có thể chạy với quyền của owner, nên phải giới hạn `EXECUTE`, kiểm soát `search_path`, tránh dynamic SQL từ input không đáng tin và audit kỹ.
- Không giả định mọi function mới chỉ dành cho admin: PostgreSQL có các **default function execution privileges** cần được xem xét và thu hẹp theo chính sách.
- Trigger có thể ghi bảng khác; application role không nhìn thấy đường ghi này từ mỗi câu SQL. Đường tác động phụ phải nằm trong review phân quyền và transaction.

Nếu không cần database function, đừng tạo lớp phân quyền thông qua function phức tạp chỉ để tránh một kiểm tra quyền rõ ràng trong application service.

## 15. Phân tách runtime, migration, batch và con người vận hành

Một credential dùng cho mọi môi trường/vai trò là rủi ro lớn:

~~~text
API runtime ----\
Migration job ----> cùng một tài khoản database có quyền owner
BI dashboard ----/
Developer shell --/
~~~

Khi một workload bị xâm phạm, attacker có thể thực hiện mọi quyền mà tài khoản chung sở hữu. Audit cũng khó trả lời **ai đã thực hiện lệnh**.

Nên tách thành:

~~~mermaid
flowchart LR
    A[API runtime] --> B[shop_runtime: DML tối thiểu]
    C[Report worker] --> D[shop_readonly: SELECT giới hạn]
    E[Migration pipeline] --> F[shop_migrator / owner privileges]
    G[Operator qua approval] --> H[Admin role có giám sát]
    B --> I[(Database)]
    D --> I
    F --> I
    H --> I
~~~

Nguyên tắc vận hành:

1. Migration/DDL chỉ chạy bằng **pipeline hoặc quy trình được phép**, không qua HTTP endpoint.
2. Job backfill cần quyền theo bảng/cột phù hợp; không mặc định dùng superuser vì khối lượng dữ liệu lớn.
3. Tool báo cáo không cần `INSERT` hay `DELETE`; quyền đọc PII phải dựa trên nhu cầu thật.
4. Khả năng “break-glass” cho vận hành khẩn cấp nên được cấp có kiểm soát, audit và thu hồi theo quy trình.
5. Quyền đọc backup/snapshot là một **đường truy cập dữ liệu** cần bảo vệ tương đương database.

Đối với role owner và migration, tách quyền quản trị không có nghĩa cản trở vận hành: chính sách có thể cho phép nâng quyền **tạm thời** qua một đường kiểm soát rõ, thay vì cấp quyền owner thường trực cho mọi pod.

## 16. Credential rotation và connection pool

Một service Java thường giữ connection trong pool nhiều phút hoặc lâu hơn. Khi credential đổi, có hai trạng thái khác nhau:

- **Kết nối mới:** cần được xác thực bằng credential/token còn hợp lệ.
- **Kết nối đã tồn tại:** tùy DB/cơ chế auth, việc đổi mật khẩu có thể **không tự cắt session đã xác thực**.

Quy trình rotation thực tế cần:

1. Phát hành credential mới hoặc cập nhật mapping identity theo chính sách.
2. Cấu hình để kết nối mới dùng secret/token mới; đảm bảo app và pool thực sự tải lại.
3. Tạo/drain/recycle connection cũ có kiểm soát, tránh cắt transaction giữa chừng.
4. Thu hồi credential cũ, xử lý session cũ theo mức rủi ro và chính sách, không chỉ đổi biến môi trường.
5. Kiểm tra cả các job ít chạy, migration, backup và dịch vụ phụ có thể còn dùng credential cũ.
6. Theo dõi failed authentication, pool creation errors, connection churn và incident logs.

**Với IAM token ngắn hạn**, không cấp một token tại startup rồi dùng nó vĩnh viễn để khởi tạo connection mới: khi token hết hạn, pool cần nhận token hợp lệ ở thời điểm mở kết nối mới. Cách tích hợp phụ thuộc driver/SDK, DataSource và cơ chế cloud; không tự chế bộ lưu token mà không hiểu concurrency/expiry.

Xoay vòng secret thành công phải được **thử nghiệm bằng kết nối mới** và kiểm tra chính sách quyền đã cấp, không chỉ xác nhận secret manager báo updated.

## 17. Quan sát quyền: audit, log và tín hiệu bất thường

Một hệ thống có least privilege vẫn cần quan sát các sự kiện truy cập:

| Nhóm tín hiệu | Điều cần theo dõi | Lưu ý |
| --- | --- | --- |
| Authentication failures | Sai credential, user/role không tồn tại, token hết hạn | Không log password/token |
| Authorization denials | Lỗi permission denied, policy deny ở API | Phân biệt lỗi hệ thống với truy cập trái phép |
| DDL và privilege changes | `GRANT`, `REVOKE`, role membership, schema change | Gắn người/phương thức phê duyệt |
| Data exports/bulk reads | Lượng dữ liệu trả bất thường, full table scan từ tài khoản lạ | Thống kê dựa workload, không chỉ nhìn một SELECT |
| Tenant-scope violations | Query bị policy từ chối hoặc application phát hiện cross-tenant | Tránh log PII trong dữ liệu từ chối |
| Credential changes | Rotation, revocation, login từ workload khác | Chú ý session cũ |
| Backup access | Ai đọc/tải snapshot, thay đổi quyền bucket | Backup có thể chứa toàn bộ dữ liệu |

PostgreSQL có logging và các công cụ/extension audit tùy môi trường. Không phải mọi hoạt động đọc/ghi đều được lưu thành một audit trail chi tiết **mặc định**. Cần xác định nội dung log, retention, quyền xem log, bảo vệ log khỏi sửa/xóa và ảnh hưởng hiệu năng.

Với truy vấn chứa dữ liệu cá nhân, **không** bật log tham số thô hoặc dump response toàn bộ chỉ để điều tra lỗi. Dùng correlation ID/trace ID và audit event có cấu trúc, lưu số lượng/bằng chứng tối thiểu phù hợp.

### Không dùng HTTP success rate làm chỉ số an toàn

API có thể trả HTTP 200 liên tục mà vẫn tiết lộ dữ liệu tenant khác. Nên theo dõi **số trường hợp policy deny, truy cập khác tenant bị chặn, privilege drift và test security regression**, đồng thời có quy trình điều tra hành vi truy cập bất thường.

## 18. Kho phi quan hệ và dịch vụ lưu trữ cũng có cơ chế quyền riêng

Không phải mọi kho dữ liệu đều dùng SQL `GRANT` hoặc PostgreSQL RLS. Phải học **mô hình access control cụ thể của sản phẩm**:

| Công nghệ | Cơ chế thường gặp | Ranh giới cần kiểm tra |
| --- | --- | --- |
| MongoDB | Database roles, privilege trên database/collection, authentication/TLS | Role service có cần ghi mọi collection không? Phạm vi tenant trong filter được kiểm tra ở đâu? |
| Redis | ACL user, command category, key pattern, TLS tùy triển khai | User cache có bị cấm `FLUSHALL`/commands không cần thiết không? Key prefix không tự là isolation giữa tenant |
| Cassandra | Role/authentication, GRANT theo keyspace/table | Ai được SELECT/MODIFY những table/partition, có security khi truy cập cluster? |
| Neo4j | Authentication, role privileges theo graph/database và thao tác | Query traversal có thể đi tới dữ liệu ngoài phạm vi người dùng không? |
| OpenSearch/Elasticsearch | User/role/index privileges, document/field-level security tùy sản phẩm/phiên bản/gói | Search index có dữ liệu PII hoặc cross-tenant không? |
| Object storage (S3-compatible) | IAM, bucket policy, object policy/ACL tùy hệ, encryption | Ai có thể list/get/put/delete object? Presigned URL còn hiệu lực bao lâu? |

Những điểm chung:

- **Mỗi dịch vụ có identity riêng**, không dùng tài khoản quản trị dùng chung.
- **Giới hạn lệnh và tài nguyên**, không chỉ quyền kết nối TCP.
- **Đối tượng có thể chứa dữ liệu từ nhiều tenant**; cần scope truy vấn, key, bucket/prefix và policy phù hợp.
- **Backup, CDC, indexer và consumer** cũng là principal và cần quyền riêng.
- **SDK/driver phải xác minh TLS server** theo khả năng của sản phẩm.

Ví dụ Redis key `tenant:501:cart:42` không phải một bằng chứng về tenant isolation nếu role Redis có quyền đọc `tenant:*` và ứng dụng có thể bị điều khiển để tạo key bất kỳ. ACL command/key pattern cùng kiểm tra quyền ở application vẫn cần được cấu hình và thử nghiệm.

## 19. Rò rỉ dữ liệu qua cache, export và backup

Không phải mọi truy cập dữ liệu đều thông qua repository chính. Dữ liệu có thể bị rò tại các đường phụ:

~~~text
Database -> cache Redis -> API
         -> search index -> search API
         -> analytics/report -> export CSV
         -> backup/snapshot -> object storage
         -> logs/traces -> observability platform
~~~

Mỗi bản sao nên có:

- **Chủ sở hữu dữ liệu** và lý do tồn tại.
- **Quyền truy cập** giới hạn theo nhu cầu sử dụng.
- **Encryption in transit/at rest** theo chính sách và hệ thống cụ thể.
- **Retention**, cơ chế xóa/cập nhật và quy trình đối soát.
- **Audit** ai truy cập hoặc xuất dữ liệu.

Ví dụ một API áp dụng RLS trên PostgreSQL nhưng vẫn lưu mọi `OrderDTO` vào cache key chỉ theo `orderId`, rồi trả entry cache cho bất kỳ người dùng nào biết ID. Khi cache hit, database RLS **không được gọi**, nên **application authorization vẫn phải được áp dụng trước khi lấy/trả cache** và cache key phải tách đúng ngữ cảnh.

Tương tự, nếu export CSV dùng `shop_readonly` nhưng role có quyền đọc toàn bộ bảng, quyền ở database chưa đủ để ngăn export nhầm dữ liệu cá nhân. Phải giới hạn cả scope/report query và đối tượng được tải file.

## 20. Phân loại lỗi truy cập và vận hành an toàn

Không nên trả mọi lỗi DB thành “không tìm thấy dữ liệu” hoặc retry vô hạn:

| Tình huống | Diễn giải | Hành động nên làm |
| --- | --- | --- |
| PostgreSQL SQLSTATE `28P01` | Password authentication failed | Kiểm tra secret/rotation/auth config; không retry dồn dập |
| SQLSTATE `42501` | Insufficient privilege | Kiểm tra GRANT, schema/RLS/role; không cấp superuser để chữa nhanh |
| Query RLS trả 0 hàng | Có thể không tồn tại hoặc bị policy lọc | Ánh xạ theo API policy, không kết luận chắc đã xóa |
| Role thiếu `USAGE ON SCHEMA` | Không thể truy cập object dù có grant table | Kiểm tra schema grants và role inheritance |
| TLS certificate/hostname error | Không xác minh được endpoint an toàn | Sửa trust chain/endpoint, không tắt verify |
| Credential hết hạn khi mở connection | Token/pool refresh sai | Tái tạo connection bằng credential hợp lệ và theo dõi |
| Database connection timeout | Lỗi kết nối/tải, không mặc định là permission denied | Theo dõi pool/network/DB, retry có giới hạn nếu phù hợp |
| Cross-tenant access bị từ chối | Policy hoạt động hoặc client đã truy cập trái phạm vi | Audit có kiểm soát, không tiết lộ dữ liệu |

SQLSTATE cụ thể phụ thuộc loại lỗi và PostgreSQL/driver; bảng chỉ minh họa những mã thông dụng. Không nên parse nguyên câu tiếng Anh của exception để quyết định cấp quyền hoặc trả lỗi. JDBC cung cấp `SQLException.getSQLState()`, nhưng cần **giữ thông tin cause và correlation** để hỗ trợ điều tra.

Nếu application role bị thiếu quyền do migration mới, cách sửa là xác định **đúng object và thao tác** rồi thêm grant nhỏ nhất trong migration được review. Không khôi phục production bằng một lệnh `GRANT ALL ON ALL TABLES` thiếu đánh giá.

## 21. Kiểm thử xác thực và phân quyền theo ma trận

Kiểm thử security không chỉ xác minh khách hàng hợp lệ đọc được dữ liệu. Các test **bị từ chối** mới chứng minh hàng rào thực thi đúng.

| Kịch bản | Kết quả cần kiểm tra |
| --- | --- |
| Không có token/token hết hạn | API từ chối trước khi lộ dữ liệu |
| Token hợp lệ của tenant A, xem order tenant B | Không trả dữ liệu/không thực hiện ghi |
| Customer A xem order khác trong cùng tenant | Không được nếu không có quyền nghiệp vụ |
| User có role support nhưng không được assign | Không được đọc đơn ngoài phạm vi |
| User có quyền đọc nhưng gửi UPDATE/DELETE | Bị từ chối ở API/use case |
| Runtime DB role thử `ALTER TABLE` hoặc `DROP TABLE` | DB từ chối vì không có DDL privilege |
| Readonly DB role thử INSERT/UPDATE | DB từ chối |
| Runtime role cố đọc cột không được grant | DB từ chối nếu không có đường gián tiếp cho phép |
| RLS không có tenant context | Query không thấy hàng không thuộc quyền hoặc bị lỗi fail-closed |
| RLS tenant A và tenant B | Chỉ thấy được hàng đúng tenant trong môi trường thử |
| Pool tái sử dụng connection sau tenant A | Không mang context A sang request B |
| Input chứa ký tự SQL đặc biệt | Bind parameter không thay cấu trúc query |
| Cache hit chứa dữ liệu tenant khác | Vẫn bị application authorization từ chối |
| Credential cũ sau rotation | Kết nối mới bị chặn theo chính sách; session cũ được xử lý đúng kế hoạch |
| Tài khoản backup/export ngoài quyền | Không truy cập được dữ liệu nhạy cảm |

### Integration test trên PostgreSQL

1. Tạo hai tenant thử nghiệm và các đơn tương ứng bằng role setup.
2. Kết nối bằng **role runtime thật** trong môi trường test, không bằng owner/superuser.
3. Bật RLS và chạy cùng SQL với tenant context A/B, kiểm tra danh sách kết quả/affected rows.
4. Thử role readonly chạy `UPDATE`, thử runtime chạy `ALTER TABLE`, xác nhận bị từ chối.
5. Dùng một pool với hai request liên tiếp có tenant khác nhau, **bắt buộc transaction-local context** và xác nhận không lộ dữ liệu.
6. Kiểm tra cả read query, update query, path cache và export thay vì chỉ một controller.

Đặc biệt, một test RLS chạy bằng **table owner** hoặc superuser có thể cho kết luận sai do các trường hợp bypass. Luôn chạy test bằng đúng principal mà service production dùng.

### Kiểm thử quyền sau migration

Khi thêm bảng, view hoặc function, chạy suite xác minh grants/role membership **trên schema đã migrate**. Nếu chỉ kiểm tra production hiện tại, một bản nâng cấp có thể vô tình mở quyền mới hoặc làm service lỗi quyền ở lần chạy tiếp theo.

## 22. Bài tập thiết kế quyền cho nền tảng bán hàng

Giả sử hệ thống có ba nhóm sử dụng:

- `Order API`: tạo đơn, đọc đơn của khách hàng và chuyển trạng thái theo use case.
- `Reporting Service`: tính số đơn/tổng doanh thu theo tenant, không cần đọc địa chỉ giao hàng hoặc số điện thoại.
- `Migration Worker`: thêm cột `tax_amount` và backfill dữ liệu cũ.

Database có bảng `orders(id, tenant_id, customer_id, status, total_amount, phone, shipping_address, tax_amount)`. Hai tenant A/B cùng sử dụng một cluster PostgreSQL. API dùng connection pool.

**Hãy giải quyết:**

1. Thiết kế ít nhất ba role database. Role nào cần quyền DDL, role nào chỉ cần SELECT, role nào được UPDATE?
2. `Reporting Service` có nên được `GRANT SELECT ON orders` toàn bộ cột không? Hãy đề xuất view hoặc query/column grants phù hợp.
3. API đã xác thực một khách của tenant A. Truy vấn nào tránh đọc nhầm đơn tenant B và khách khác trong cùng tenant?
4. Nếu dùng PostgreSQL RLS với `app.tenant_id`, việc set biến trên pooled connection cần nằm trong phạm vi nào? Vì sao?
5. RLS dựa vào biến tenant do app set có chống được một SQL injection cho phép thực thi lệnh `set_config` tùy ý dưới cùng DB role không?
6. Runtime dùng credential của migration worker để tiện deploy. Rủi ro lớn nhất là gì?
7. Khi xoay vòng password mà pool vẫn có connection cũ, những việc nào cần kiểm tra?
8. Những integration test **bị từ chối** nào là bắt buộc trước khi triển khai?

**Gợi ý lời giải:**

- Tách `order_runtime`, `report_readonly` và `schema_migrator`, cùng role owner `NOLOGIN` nếu phù hợp. Chỉ migrator/owner được phép DDL theo quy trình phê duyệt.
- Reporting đọc một projection/view hoặc những cột tối thiểu; không cấp SELECT số điện thoại/địa chỉ nếu báo cáo không cần.
- Scope query theo **tenant/customer đã xác thực**, ví dụ `WHERE tenant_id = ? AND customer_id = ? AND id = ?`; kiểm tra quyền nghiệp vụ ở use case.
- Dùng `SET LOCAL` hoặc `set_config(..., true)` **trong cùng transaction** với truy vấn; tránh rò tenant context giữa các connection được tái sử dụng.
- Biến GUC có thể bị thay đổi bởi SQL thực thi dưới role tương ứng, nên không phải ranh giới cứng trước arbitrary SQL injection hoặc service compromise. Parameterization, app authorization, least privilege và thiết kế DB isolation phù hợp vẫn bắt buộc.
- Credential migration có quyền đổi schema/xóa dữ liệu; bị lộ có thể gây thiệt hại rộng hơn quyền runtime.
- Rotation phải xử lý cả connection mới/cũ, token expiry, secret loading, session revocation theo chính sách và giám sát lỗi xác thực.
- Thử cross-tenant SELECT/UPDATE, cross-customer access, readonly write, runtime DDL, SQL injection, reuse pool, cache/export và grants sau migration.

## 23. Checklist trước khi cho phép một Java service truy cập kho dữ liệu

1. **Danh tính:** biết principal của người dùng, service, migration, report và backup; không dùng credential chung thiếu audit.
2. **Xác thực:** xác minh token/identity tại API và credential kết nối tại database, có expiration/rotation.
3. **Phạm vi quyền:** xác định table/column/function và hành động cần thiết; không cấp owner/superuser cho runtime.
4. **Object authorization:** mọi thao tác đọc/ghi đều kiểm tra tenant, sở hữu tài nguyên và trạng thái nghiệp vụ.
5. **RLS:** nếu dùng, kiểm tra policy, owner bypass, quyền role, nguồn tenant context và test bằng runtime role thật.
6. **Connection pool:** transaction-local context/cleanup không gây rò dữ liệu giữa các request; connection được trả đúng phạm vi.
7. **Truy vấn:** bind mọi giá trị, allowlist identifiers, không ghép SQL/CQL/JSON/Cypher từ input không đáng tin.
8. **Đường truyền:** TLS xác minh server, network access giới hạn và chính sách proxy/replica rõ ràng.
9. **Bí mật:** secret/workload identity được bảo vệ, không nằm trong repo/log, có kế hoạch rotation/revoke.
10. **Quyền gián tiếp:** audit view, function, SECURITY DEFINER, role inheritance, default grants và quyền export.
11. **Bản sao:** cache, search, CDC, report, backup và object storage đều có chính sách truy cập/retention riêng.
12. **Dữ liệu nhạy cảm:** chỉ trả trường cần thiết; encryption/retention/ghi log tuân thủ chính sách.
13. **Giám sát:** có audit sự kiện authentication, authorization, privilege changes và truy cập bất thường.
14. **Kiểm thử:** luôn có negative tests và cross-tenant tests trên DB với role/schema gần production.
15. **Khôi phục:** thay credential, thu hồi session, sửa policy/grant sai và đối soát dữ liệu có runbook rõ ràng.

**Kết luận:** bảo mật persistence không dừng ở việc kết nối thành công bằng username/password. **Xác thực** tạo ra danh tính đáng tin ở từng tầng; **phân quyền** giới hạn hành động và phạm vi dữ liệu; **transaction, constraint và kiểm soát đồng thời** giữ cho thao tác hợp lệ vẫn đúng đắn khi nhiều request chạy song song. Với Java, cách thiết kế bền vững là dùng service identity và role tối thiểu, thực thi authorization theo tài nguyên trong application service, cấu hình database privilege/RLS theo mô hình đe dọa, bảo vệ credential/kết nối và xác minh tất cả bằng kiểm thử truy cập bị từ chối trước khi triển khai.

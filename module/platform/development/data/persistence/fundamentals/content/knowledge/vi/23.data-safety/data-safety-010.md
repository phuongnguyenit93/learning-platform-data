# Theo dõi thay đổi dữ liệu bằng nhật ký kiểm toán

Khi một đơn hàng bị đổi từ **PAID** sang **CANCELLED**, một bản ghi khách hàng bị sửa thông tin hoặc một nhân viên điều chỉnh hạn mức, dữ liệu cuối cùng trong bảng chỉ cho biết **trạng thái hiện tại**. Nó không tự trả lời: *ai đã thay đổi, thay đổi lúc nào, từ giá trị nào sang giá trị nào, do yêu cầu nào, và thao tác có thực sự được commit hay không?*

**Nhật ký kiểm toán (audit log/audit trail)** lưu bằng chứng có cấu trúc về những hành động và thay đổi đáng theo dõi để phục vụ điều tra sự cố, truy vết trách nhiệm, kiểm soát nội bộ và đối soát. Trong tầng persistence, audit trail hữu ích vì một phép cập nhật hợp lệ về mặt SQL vẫn có thể là sai về nghiệp vụ hoặc vi phạm quyền truy cập.

Bài thuộc chương **An toàn dữ liệu** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Trọng tâm là thiết kế ranh giới lưu trữ trong Java: dữ liệu được ghi qua JDBC/transaction, dấu vết gắn với danh tính đã xác thực, rollback/commit được phản ánh đúng, và nhật ký được bảo vệ khỏi truy cập trái phép hay chỉnh sửa sau sự kiện.

Các ví dụ dùng **PostgreSQL và Java JDBC**. Mục tiêu không phải hướng dẫn một quy định pháp lý cụ thể: yêu cầu retention, dữ liệu cá nhân, bảo quản bằng chứng và quyền truy cập phải được xác định theo tổ chức, hệ thống và quy định áp dụng.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích **audit trail** khác gì với **application log**, **WAL**, **CDC** và **event sourcing**.
2. Thiết kế một bản ghi audit có **actor, action, target, before/after, thời điểm và correlation/request ID**.
3. Phân biệt sự kiện **đã commit** với một thao tác **được yêu cầu nhưng bị từ chối hoặc rollback**.
4. Triển khai audit thay đổi hàng bằng **PostgreSQL trigger** và bảo đảm audit cùng transaction với dữ liệu gốc.
5. Truyền thông tin người thực hiện từ Java đến PostgreSQL bằng ngữ cảnh **transaction-local**, không làm rò context qua connection pool.
6. Nhận biết giới hạn bảo mật của trigger, vai trò **least privilege**, phân tách quyền ghi/đọc và cách tăng khả năng phát hiện sửa đổi nhật ký.
7. Đánh đổi về dung lượng, độ trễ, ghi WAL, indexing, retention và rủi ro dữ liệu nhạy cảm.
8. Xây dựng các ca kiểm thử rollback, UPDATE, DELETE, thao tác đồng thời, retry và lỗi kết nối gần COMMIT.

## 2. Nhật ký kiểm toán cần trả lời câu hỏi gì?

Một audit event hữu ích thường trả lời sáu nhóm câu hỏi:

| Câu hỏi | Trường dữ liệu gợi ý | Ví dụ |
|---|---|---|
| **Ai?** | actor_id, actor_type, service_id | user-42, system-job |
| **Làm gì?** | action/operation | UPDATE, DELETE, APPROVE |
| **Với cái gì?** | entity_type, entity_id, tenant_id | orders, 19002, tenant-7 |
| **Khi nào?** | recorded_at (UTC) | 2026-11-22T09:10:01Z |
| **Trước và sau ra sao?** | before_value, after_value, changed_fields | status: PAID → CANCELLED |
| **Liên quan yêu cầu nào?** | request_id, trace_id, reason, operation_id | req-..., adjustment-... |

Ngoài dữ liệu kỹ thuật, nhiều nghiệp vụ cần **lý do** và **quyết định đã được phê duyệt**. Chẳng hạn thay đổi hạn mức do người dùng tự thực hiện khác với quản trị viên thực hiện thay đổi theo yêu cầu hỗ trợ. Các trường lý do/phê duyệt là thông tin do ứng dụng cung cấp, phải xác thực và kiểm soát riêng; chúng **không tự trở thành bằng chứng đáng tin** chỉ vì được lưu trong một bảng có tên audit.

### 2.1. Phân biệt actor với DB user

Nếu một API dùng tài khoản database **app_runtime**, mọi câu SQL từ nhiều người dùng HTTP có thể xuất hiện dưới cùng DB role này. Vì vậy **current_user** trong PostgreSQL không cho biết nhân viên hoặc khách hàng nào đã bấm nút thay đổi.

Cần hai lớp danh tính:

- **DB identity:** role đã xác thực để mở connection và thực thi SQL.
- **Business actor:** người dùng hoặc service đã được tầng ứng dụng xác thực và được phép thực hiện nghiệp vụ.

Actor trong audit nên đến từ **security principal đáng tin của ứng dụng** sau xác thực/phân quyền, không lấy nguyên văn một HTTP header kiểu X-User-Id do client tự khai.

### 2.2. Audit sự kiện đã xảy ra hay mọi nỗ lực?

Đây là hai loại bản ghi khác nhau:

1. **Committed data-change audit:** mô tả thay đổi dữ liệu đã trở thành trạng thái được commit. Audit và dữ liệu nên cùng transaction.
2. **Security/access/attempt audit:** ghi nhận cả thao tác bị từ chối, đăng nhập thất bại, truy vấn trái phép, yêu cầu đã bị rollback hoặc hành vi đáng ngờ. Loại này thường cần kênh log/giám sát **độc lập** với transaction nghiệp vụ.

Một trigger ghi vào bảng audit cùng transaction sẽ **rollback cùng dữ liệu**, vì thế **không lưu được mọi lần thử thất bại**. Đây là hành vi đúng cho lịch sử *thay đổi đã commit*, nhưng không thay thế audit truy cập hoặc điều tra tấn công.

## 3. Audit trail khác WAL, log ứng dụng, CDC và event sourcing

| Cơ chế | Mục đích chính | Điều không tự bảo đảm |
|---|---|---|
| **Audit trail nghiệp vụ** | Truy vết actor, đối tượng, trước/sau, lý do, request | Tính không thể sửa khi DBA có quyền cao |
| **Application log** | Quan sát lỗi, luồng xử lý, latency, correlation | Tương ứng 1-1 với transaction đã commit |
| **Database WAL/redo log** | Durability, crash recovery, replication | Ai là business actor và lý do thay đổi |
| **CDC (Change Data Capture)** | Xuất luồng thay đổi dữ liệu từ database | Có actor/ý nghĩa nghiệp vụ nếu không được bổ sung |
| **Transactional outbox** | Ghi sự kiện cần phát ra trong cùng transaction với dữ liệu | Tự động xuất ra bên ngoài đúng một lần tuyệt đối |
| **Event sourcing** | Lưu chuỗi sự kiện nghiệp vụ làm nguồn trạng thái có thể tái dựng | Tự động giải quyết bảo mật/retention hoặc thay thế mọi audit access |
| **DB access/statement audit** | Ghi ai kết nối và thực thi câu SQL nào | Luôn diễn giải được thay đổi nghiệp vụ ở cấp entity |

**WAL không phải nhật ký kiểm toán nghiệp vụ.** Nó được tối ưu cho phục hồi và replication, có vòng đời và dạng dữ liệu khác với câu hỏi “ai đổi trạng thái đơn hàng?”. **CDC có thể là nguồn cấp dữ liệu audit hoặc phân tích**, nhưng một bản ghi UPDATE từ CDC không tự biết ai là người dùng cuối nếu ứng dụng không mang actor/correlation vào một nơi có thể quan sát được.

**Event sourcing khác audit trail:** event sourcing dùng sự kiện nghiệp vụ làm nguồn sự thật để tái dựng state; audit trail thường là dấu vết bổ sung cho các bảng đang lưu trạng thái hiện tại. Một hệ thống có thể dùng cả hai.

## 4. Định nghĩa “audit đúng” trước khi chọn công nghệ

Một thiết kế audit thay đổi dữ liệu thường cần các bất biến:

1. **Completeness trong phạm vi đã định:** mọi INSERT/UPDATE/DELETE trên bảng được bảo vệ đều sinh audit event tương ứng khi transaction commit.
2. **Atomicity:** dữ liệu nghiệp vụ và audit event **cùng commit hoặc cùng rollback**.
3. **Attribution:** event có actor/correlation đáng tin hoặc chính sách rõ khi actor là job hệ thống.
4. **Integrity:** tác nhân ghi dữ liệu thông thường không thể tự ý sửa/xóa audit, và các sửa đổi của người có quyền cao phải có cách phát hiện độc lập.
5. **Confidentiality:** nhật ký không tiết lộ secret, token, dữ liệu thanh toán hay PII không cần thiết.
6. **Availability:** lỗi ghi audit có hành vi đã quyết định trước: **fail closed** (không commit nghiệp vụ khi không ghi được audit) hoặc cơ chế nhất quán khác được phê duyệt.
7. **Queryability:** có thể tìm theo tenant, entity, request ID, actor và khoảng thời gian.
8. **Retention:** có thời hạn giữ, chính sách archive, pháp lý/điều tra và khả năng xóa có kiểm soát.

**Không có một cơ chế duy nhất tự bảo đảm tất cả**. Trigger trong database phù hợp với atomicity cho một database, nhưng cần thêm kiểm soát quyền, backup, lưu trữ độc lập và audit access để đáp ứng những mục tiêu khác.

## 5. Chọn mức chi tiết: snapshot, diff hay sự kiện nghiệp vụ?

Có ba cách trình bày thay đổi:

### 5.1. Snapshot trước/sau

~~~json
{
  "entity": "orders",
  "id": "19002",
  "action": "UPDATE",
  "before": {"status": "PAID", "amount": 120000},
  "after":  {"status": "CANCELLED", "amount": 120000}
}
~~~

Ưu điểm: dễ điều tra và tái dựng một số trạng thái. Nhược điểm: nhiều dữ liệu lặp, chiếm dung lượng và dễ sao chép các trường nhạy cảm vào audit.

### 5.2. Field-level diff

~~~json
{
  "entity": "orders",
  "id": "19002",
  "action": "UPDATE",
  "changes": {
    "status": {"from": "PAID", "to": "CANCELLED"}
  }
}
~~~

Ưu điểm: ít dữ liệu hơn, dễ thấy trường thay đổi. Nhược điểm: thuật toán diff phức tạp hơn với JSON/array, NULL và schema evolution; không phải lúc nào cũng đủ để tái dựng trạng thái đầy đủ.

### 5.3. Sự kiện nghiệp vụ

~~~json
{
  "event_type": "OrderCancelled",
  "order_id": "19002",
  "reason_code": "CUSTOMER_REQUEST",
  "actor_id": "support-17",
  "request_id": "req-abc"
}
~~~

Ưu điểm: thể hiện ý nghĩa quyết định. Nhược điểm: việc hủy đơn có thể sửa nhiều bảng, nên cần định nghĩa quan hệ giữa event nghiệp vụ và thay đổi vật lý. Nếu chỉ ghi sự kiện từ Java nhưng một job SQL/ETL cũng sửa bảng, những thay đổi ngoài đường ứng dụng có thể không được ghi.

**Lựa chọn thực tế:** dùng audit hàng cho các bảng quan trọng, có thể bổ sung business event/operation ID để giải thích ngữ nghĩa. Chỉ ghi những trường cần thiết theo chính sách, không mặc định lưu toàn bộ dữ liệu nhạy cảm.

## 6. Mô hình SQL minh họa: orders và audit.change_events

Giả sử ứng dụng Java quản lý đơn hàng trong một database PostgreSQL. Bảng dưới cố ý **không chứa dữ liệu cá nhân nhạy cảm**, giúp ví dụ lưu before/after dưới dạng JSONB dễ đọc. Nếu bảng thật có email, địa chỉ, số định danh hoặc secret, phải thu hẹp các trường được phép ghi vào audit.

### 6.1. Bảng nghiệp vụ

~~~sql
CREATE TABLE public.orders (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('CREATED', 'PAID', 'CANCELLED')),
    amount NUMERIC(14, 2) NOT NULL CHECK (amount >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO public.orders (id, tenant_id, status, amount)
VALUES (19002, 7, 'PAID', 120000.00);
~~~

Các constraint giúp DB bảo vệ tính đúng cơ bản; audit không thay thế constraint hay cơ chế phân quyền theo tenant.

### 6.2. Bảng audit có cấu trúc

~~~sql
CREATE SCHEMA audit;

CREATE TABLE audit.change_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    entity_table TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    tenant_id BIGINT NOT NULL,
    action TEXT NOT NULL
        CHECK (action IN ('INSERT', 'UPDATE', 'DELETE')),
    actor_id TEXT NOT NULL,
    request_id TEXT,
    old_row JSONB,
    new_row JSONB
);

CREATE INDEX change_events_target_time_idx
    ON audit.change_events (entity_table, entity_id, recorded_at DESC);

CREATE INDEX change_events_actor_time_idx
    ON audit.change_events (actor_id, recorded_at DESC);

CREATE INDEX change_events_request_idx
    ON audit.change_events (request_id)
    WHERE request_id IS NOT NULL;
~~~

**Ý nghĩa cột:**

- **event_id** định danh event; thuận tiện tham chiếu và kiểm tra các khoảng ID.
- **recorded_at** do DB cấp để ghi thời điểm trigger chạy, không nhất thiết là thời điểm transaction đã commit.
- **entity_table/entity_id** xác định bảng/hàng thay đổi; cần diễn giải khóa chính phức hợp riêng nếu có.
- **tenant_id** giúp lọc và kiểm soát truy cập theo miền dữ liệu.
- **action** phân biệt INSERT, UPDATE, DELETE.
- **actor_id/request_id** giúp nối với ngữ cảnh business và trace ứng dụng.
- **old_row/new_row** là hai snapshot được lựa chọn theo chính sách.

**Không suy từ event_id hoặc recorded_at ra thứ tự COMMIT tuyệt đối.** Sequence có thể cấp ID trước khi transaction commit, có khoảng trống khi rollback, và các transaction có thể commit theo thứ tự khác lúc lấy ID. Nếu cần chứng minh thứ tự toàn cục, phải có cơ chế thứ tự/commit metadata phù hợp với hệ thống được thiết kế.

### 6.3. Không tạo index cho mọi cột JSONB theo phản xạ

Bảng audit thường tăng nhanh. Mỗi index thêm vào sẽ làm tăng chi phí INSERT, WAL và dung lượng. Nên thiết kế các truy vấn điều tra phổ biến trước: tìm lịch sử một entity, request, actor hoặc ngày. Index thêm vào khi có bằng chứng từ workload và EXPLAIN; cân nhắc partition theo thời gian và lifecycle archive khi dung lượng lớn.

## 7. PostgreSQL trigger: ghi audit cùng transaction

Một cách đảm bảo mọi thay đổi hàng đi qua database đều được quan sát là **AFTER ROW trigger**. Khi SQL sửa orders thành công trong một transaction, trigger ghi event vào audit.change_events **trong cùng transaction**. Nếu transaction rollback, các event audit của nó cũng rollback.

Ví dụ PL/pgSQL:

~~~sql
CREATE OR REPLACE FUNCTION audit.capture_order_change()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, audit
AS $$
DECLARE
    v_actor TEXT;
    v_request TEXT;
    v_entity_id TEXT;
    v_tenant BIGINT;
    v_old JSONB := NULL;
    v_new JSONB := NULL;
BEGIN
    -- Ngữ cảnh phải được đặt bởi tầng Java/job đã xác thực.
    v_actor := NULLIF(current_setting('app.actor_id', true), '');
    v_request := NULLIF(current_setting('app.request_id', true), '');

    IF v_actor IS NULL THEN
        RAISE EXCEPTION 'Missing trusted audit actor'
            USING ERRCODE = 'P0001';
    END IF;

    IF TG_OP = 'DELETE' THEN
        v_entity_id := OLD.id::text;
        v_tenant := OLD.tenant_id;
        v_old := to_jsonb(OLD);
    ELSIF TG_OP = 'INSERT' THEN
        v_entity_id := NEW.id::text;
        v_tenant := NEW.tenant_id;
        v_new := to_jsonb(NEW);
    ELSE
        -- Bỏ qua UPDATE không làm thay đổi giá trị các cột.
        IF to_jsonb(OLD) IS NOT DISTINCT FROM to_jsonb(NEW) THEN
            RETURN NULL;
        END IF;
        v_entity_id := NEW.id::text;
        v_tenant := NEW.tenant_id;
        v_old := to_jsonb(OLD);
        v_new := to_jsonb(NEW);
    END IF;

    INSERT INTO audit.change_events
        (entity_table, entity_id, tenant_id, action,
         actor_id, request_id, old_row, new_row)
    VALUES
        (TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME,
         v_entity_id, v_tenant, TG_OP,
         v_actor, v_request, v_old, v_new);

    -- AFTER ROW trigger bỏ qua giá trị trả về.
    RETURN NULL;
END;
$$;

CREATE TRIGGER orders_change_audit
AFTER INSERT OR UPDATE OR DELETE
ON public.orders
FOR EACH ROW
EXECUTE FUNCTION audit.capture_order_change();
~~~

**Điểm thiết kế:**

1. Trigger **AFTER INSERT/UPDATE/DELETE FOR EACH ROW** thu lại thay đổi hàng; không thu SELECT hay lần truy cập bị từ chối.
2. **OLD** mô tả hàng cũ trong UPDATE/DELETE, **NEW** mô tả hàng mới trong INSERT/UPDATE. Với DELETE, new_row là NULL; với INSERT, old_row là NULL.
3. **current_setting(..., true)** đọc context do ứng dụng thiết lập trong transaction. Nếu không có actor, trigger **raise exception**, khiến ghi nghiệp vụ thất bại (*fail closed* theo phạm vi ví dụ).
4. **SECURITY DEFINER** cho phép trigger ghi vào audit bằng quyền của chủ sở hữu function, trong khi role runtime không cần quyền INSERT trực tiếp trên audit. Phải bảo vệ chủ sở hữu, quyền EXECUTE/ALTER, schema và **search_path** theo chính sách an toàn.
5. **RETURN NULL** hợp lệ với AFTER trigger vì giá trị trả về không thay đổi hàng gốc.
6. Nếu audit INSERT lỗi, statement của nghiệp vụ cũng lỗi; transaction cần được rollback/handled đúng cách.

**Giới hạn:** ví dụ lưu **to_jsonb(OLD/NEW)** của toàn bảng orders. Với bảng thực có dữ liệu cá nhân, bí mật, token, nội dung thanh toán hoặc cột dung lượng lớn, phải thay bằng phép chọn cột được audit cho phép (whitelist/masking), và kiểm tra cả dữ liệu nested trong JSONB. Không bê nguyên mẫu full-row audit sang mọi bảng.

### 7.1. Trigger không phải cơ chế chống chỉnh sửa tuyệt đối

Một database superuser, chủ sở hữu đối tượng có quyền rộng hoặc một cơ chế replication/maintenance đặc biệt có thể sửa dữ liệu audit, vô hiệu hóa trigger hoặc làm việc ngoài đường ghi thông thường. Vì vậy:

- Không cấp quyền sở hữu bảng audit/trigger cho role runtime.
- Tách người/role được thay đổi schema khỏi người xem audit.
- Theo dõi việc ALTER/DROP/DISABLE TRIGGER và thay đổi quyền bằng cơ chế **DDL/DB access audit riêng**.
- Khi cần bằng chứng chống sửa đổi, xuất event tới lưu trữ độc lập có tính **tamper-evident/immutable retention** và kiểm soát quyền/khóa thích hợp.

Cụm từ **“append-only”** của bảng audit chủ yếu là **quy tắc quyền và quy trình**; một database table bình thường không tự trở thành kho dữ liệu bất biến trước mọi đặc quyền quản trị.

### 7.2. Điều gì không được row trigger bắt?

- SELECT và việc người dùng **xem dữ liệu nhạy cảm**.
- Lần thử UPDATE bị chặn vì thiếu quyền/ràng buộc hoặc transaction rollback.
- Các sự kiện cấu trúc như CREATE TABLE, ALTER ROLE, thay đổi policy.
- Thao tác **TRUNCATE** nếu chỉ tạo row-level trigger trên INSERT/UPDATE/DELETE.
- Một số đường thay đổi dữ liệu đặc biệt trong quản trị/replication khi trigger bị vô hiệu theo cấu hình hoặc quyền.

Cần lớp **application/security audit**, DB access audit hoặc event trigger/monitoring tương ứng cho những phạm vi này. Không nên gọi một cơ chế row trigger là “đã kiểm toán toàn bộ database”.

## 8. Java JDBC: truyền actor và request ID trong cùng transaction

Nếu ứng dụng dùng connection pool, **không** đặt actor ở session bằng cấu hình tồn tại lâu rồi để connection được tái sử dụng cho người dùng khác. Ví dụ nguy hiểm là dùng **SET app.actor_id = ...** cấp session mà quên reset; request tiếp theo có thể bị ghi nhầm actor.

PostgreSQL hỗ trợ **set_config(setting_name, new_value, is_local)**. Với **is_local = true**, giá trị có hiệu lực trong transaction hiện tại. Java cần **tắt auto-commit trước**, đặt actor/request ID và thực thi SQL trên **cùng một Connection**, rồi commit/rollback.

Ví dụ Java 17:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderStatusGateway {
    private final DataSource dataSource;

    public OrderStatusGateway(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void changeStatus(
            long tenantId,
            long orderId,
            String expectedStatus,
            String newStatus,
            String authenticatedActorId,
            String requestId) throws SQLException {

        if (tenantId <= 0 || orderId <= 0
                || authenticatedActorId == null
                || authenticatedActorId.isBlank()) {
            throw new IllegalArgumentException("Ngữ cảnh audit không hợp lệ");
        }

        try (Connection connection = dataSource.getConnection()) {
            if (!connection.getAutoCommit()) {
                throw new SQLException(
                        "Ví dụ yêu cầu Connection sở hữu transaction mới");
            }

            connection.setAutoCommit(false);
            boolean commitAttempted = false;
            boolean transactionEnded = false;

            try {
                // Context ở phạm vi transaction, không tồn tại
                // sang request tiếp theo trong pool.
                String setContext = """
                        SELECT set_config('app.actor_id', ?, true),
                               set_config('app.request_id', ?, true)
                        """;

                try (PreparedStatement context =
                             connection.prepareStatement(setContext)) {
                    context.setString(1, authenticatedActorId);
                    context.setString(2,
                            requestId == null ? "" : requestId);
                    context.execute();
                }

                String updateSql = """
                        UPDATE public.orders
                        SET status = ?,
                            updated_at = clock_timestamp()
                        WHERE tenant_id = ?
                          AND id = ?
                          AND status = ?
                        """;

                try (PreparedStatement update =
                             connection.prepareStatement(updateSql)) {
                    update.setString(1, newStatus);
                    update.setLong(2, tenantId);
                    update.setLong(3, orderId);
                    update.setString(4, expectedStatus);

                    if (update.executeUpdate() != 1) {
                        throw new IllegalStateException(
                                "Không tìm thấy đơn hoặc trạng thái đã đổi");
                    }
                }

                commitAttempted = true;
                connection.commit();
                transactionEnded = true;
            } catch (SQLException | RuntimeException failure) {
                if (!commitAttempted) {
                    try {
                        connection.rollback();
                        transactionEnded = true;
                    } catch (SQLException rollbackError) {
                        failure.addSuppressed(rollbackError);
                    }
                }
                throw failure;
            } finally {
                if (transactionEnded) {
                    connection.setAutoCommit(true);
                }
                // Nếu COMMIT chưa rõ, phải để pool/driver xử lý
                // connection không đáng tin theo chính sách an toàn.
            }
        }
    }
}
~~~

**Cần đọc đúng ý nghĩa mẫu:**

- **authenticatedActorId** phải được server lấy từ principal đã xác thực, không để client tự chọn người khác.
- **requestId** giúp tương quan giữa HTTP trace và audit, **không phải idempotency key** tự bảo đảm chống ghi trùng.
- **set_config(... true)** chỉ tồn tại trong transaction; không rò actor qua pool khi dùng đúng.
- UPDATE có điều kiện **tenant_id, id, expected status**, tránh nhầm tenant và hỗ trợ kiểm soát thay đổi đồng thời dạng optimistic check.
- Trigger ghi audit trong cùng transaction với UPDATE; nếu UPDATE không ảnh hưởng hàng và ứng dụng rollback, **không có committed data-change event**.
- Mẫu trả lỗi sau khi COMMIT thất bại mà **không tuyên bố chắc đã rollback**. Đối soát trạng thái và idempotency cần được triển khai ở biên nghiệp vụ.

Ví dụ giả định connection pool bảo đảm cleanup hoặc loại bỏ connection không dùng được và có cách xử lý phù hợp với kết quả COMMIT chưa xác định. Trong sản phẩm dùng **Spring @Transactional**, không tự gọi connection.commit()/rollback() trên connection do Spring quản lý; cần dùng transaction-aware JDBC/Spring APIs để thiết lập context trên **chính connection đã enlist vào transaction**.

### 8.1. Thử truy vấn sau khi đổi trạng thái

~~~sql
SELECT event_id, recorded_at,
       entity_table, entity_id, actor_id, request_id,
       action, old_row, new_row
FROM audit.change_events
WHERE entity_table = 'public.orders'
  AND entity_id = '19002'
ORDER BY event_id;
~~~

Nếu lệnh UPDATE commit thành công và trạng thái thật sự thay đổi, event có OLD và NEW tương ứng. Nếu một transaction sửa orders rồi rollback, event do trigger tạo ra trong transaction đó **không xuất hiện trong kết quả sau rollback**.

**Không kiểm chứng bằng cách chỉ xem Java log có dòng “UPDATE sent”.** Cần kiểm tra kết quả commit và dữ liệu/audit tại nguồn có thẩm quyền.

## 9. Những thao tác thay đổi nào thực sự được ghi?

| Tình huống | Orders thay đổi sau COMMIT? | Audit trigger cùng transaction |
|---|---|---|
| INSERT một đơn mới, COMMIT thành công | Có | INSERT event với new_row |
| UPDATE trạng thái, COMMIT thành công | Có | UPDATE event với old_row và new_row |
| DELETE một đơn, COMMIT thành công | Hàng biến mất | DELETE event với old_row |
| UPDATE rồi ROLLBACK | Không | Event bị rollback cùng dữ liệu |
| UPDATE vi phạm constraint, statement lỗi | Không commit thay đổi đó | Không có committed event tương ứng |
| UPDATE không có hàng khớp điều kiện | Không | Không có row trigger event |
| UPDATE chỉ gán cùng giá trị | Có thể không đổi giá trị logic | Ví dụ trigger bỏ qua nếu OLD/NEW giống hệt |
| SELECT đọc dữ liệu | Không | Không có row trigger event |
| TRUNCATE TABLE | Có thể xóa nhiều hàng | Không được bao phủ bởi row trigger minh họa |
| DDL thay đổi bảng/trigger | Thay đổi schema | Cần DB/DDL audit riêng |

Hàng có thể được cập nhật **nhiều lần trong cùng transaction**: trigger có thể tạo nhiều event tạm thời cho từng UPDATE. Sau COMMIT, lịch sử thể hiện các bước vật lý tương ứng, không nhất thiết chỉ một business event tổng hợp. Nếu muốn **một event cho mỗi quyết định nghiệp vụ**, có thể cần mô hình ghi audit tại service/outbox thay vì phụ thuộc chỉ vào row trigger.

## 10. Đọc, lọc và điều tra từ nhật ký audit

Một điều tra thông thường bắt đầu từ **request ID hoặc entity ID**, sau đó đối chiếu actor, thao tác, thời gian và dữ liệu liên quan.

### 10.1. Lịch sử của một đơn hàng

~~~sql
SELECT event_id, recorded_at, action,
       actor_id, request_id,
       old_row ->> 'status' AS old_status,
       new_row ->> 'status' AS new_status
FROM audit.change_events
WHERE tenant_id = 7
  AND entity_table = 'public.orders'
  AND entity_id = '19002'
ORDER BY recorded_at, event_id;
~~~

Đây là cách trình bày theo thứ tự timestamp/ID **mang tính quan sát**, không phải bằng chứng về thứ tự COMMIT tuyệt đối giữa các transaction đồng thời.

### 10.2. Tìm các thay đổi theo actor

~~~sql
SELECT recorded_at, entity_table, entity_id,
       action, request_id
FROM audit.change_events
WHERE actor_id = 'support-17'
  AND recorded_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND recorded_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00'
ORDER BY recorded_at;
~~~

### 10.3. Đối chiếu một request

~~~sql
SELECT event_id, entity_table, entity_id, action,
       old_row, new_row
FROM audit.change_events
WHERE request_id = 'req-abc'
ORDER BY event_id;
~~~

Nếu không có event, có nhiều khả năng: request không thay đổi dữ liệu, cập nhật không khớp hàng, transaction rollback, truy vấn ghi lên bảng không được gắn trigger, hoặc request ID không được gắn đúng. **Không kết luận “request chưa từng xảy ra” chỉ vì không có committed data-change audit**.

### 10.4. Luồng điều tra tối thiểu

~~~text
Incident / yêu cầu hỗ trợ
         |
         v
Lấy request_id, entity_id, tenant_id
         |
         v
Tra audit event đã commit
         |
         v
Đối chiếu actor và quyền ở thời điểm thao tác
         |
         v
So sánh before/after với trạng thái hiện tại
         |
         v
Tra application log, auth/access log, trace
         |
         v
Kết luận có căn cứ + bằng chứng đã bảo quản
~~~

Khi phục vụ kiểm toán, giới hạn quyền tra cứu theo tenant, nhóm được phân công và nhu cầu công việc. Người được quyền xem lịch sử một đơn hàng không mặc nhiên được phép đọc toàn bộ old_row/new_row của mọi tenant.

## 11. Audit bằng trigger, ứng dụng, outbox hay CDC?

Không có một điểm bắt audit phù hợp mọi hệ thống. Chọn theo **đường ghi dữ liệu thực tế**, nhu cầu atomicity, khả năng chịu lỗi và yêu cầu điều tra.

| Cách làm | Điểm mạnh | Giới hạn |
|---|---|---|
| **Database row trigger** | Bao phủ các đường INSERT/UPDATE/DELETE thông thường vào cùng bảng; cùng transaction | Khó diễn đạt ý nghĩa nghiệp vụ; tăng chi phí ghi; không bắt SELECT/DDL; quyền cao có thể bypass |
| **Ứng dụng ghi audit cùng transaction** | Gắn actor, reason, operation ID và ngữ nghĩa nghiệp vụ | Mọi đường ghi phải tuân thủ; job SQL ngoài ứng dụng dễ bị bỏ sót |
| **Transactional outbox** | Ghi sự kiện cần phát đi cùng transaction rồi chuyển ra hệ khác | Cần dispatcher, retry, idempotent consumer và theo dõi backlog |
| **CDC từ WAL/binlog** | Đọc luồng thay đổi đã commit, thích hợp đồng bộ sang hệ ngoài | Không tự có actor/ý nghĩa nghiệp vụ; có offset/lag/retention |
| **DB access/statement audit** | Theo dõi login, SELECT hoặc hành động đặc quyền theo cấu hình | Có thể không có before/after theo entity |
| **Event sourcing** | Business event là nguồn trạng thái có thể tái dựng | Cần mô hình kiến trúc riêng, không tự thay thế access audit |

### 11.1. Ghi ở application service

Một service có thể sử dụng **cùng Connection và transaction**:

~~~text
BEGIN
  UPDATE orders SET status = 'CANCELLED' WHERE id = ...
  INSERT INTO audit_events (actor, reason, before, after, ...) VALUES (...)
COMMIT
~~~

Ưu điểm là biết rõ nghiệp vụ “hủy đơn theo yêu cầu khách hàng”. Nhược điểm: một script SQL quản trị hoặc batch job sửa orders ngoài service sẽ không tạo event nếu không tuân thủ hợp đồng.

**Tránh ghi trùng không có chủ đích:** nếu vừa có row trigger vừa có code service tự INSERT audit, một thay đổi có thể tạo hai event. Nếu cần cả hai, phân biệt **data-change audit** với **business-action audit** và nối chúng bằng operation/request ID.

### 11.2. Outbox giúp chuyển audit tới hệ độc lập

~~~text
Transaction của Java
    |
    +-- UPDATE orders
    +-- INSERT outbox_events(event_id, payload)
    |
  COMMIT
    |
    v
Dispatcher / CDC
    |
    v
Kho audit độc lập / Event broker
~~~

Dữ liệu và outbox row cùng commit hoặc rollback. Dispatcher có thể bị ngắt khi phát sự kiện, sau đó gửi lại; phía nhận phải **deduplicate bằng event_id** và quản lý ordering theo hợp đồng. Không được mặc định có “exactly once” end-to-end chỉ vì đã dùng outbox.

Outbox có thể dùng để đưa chứng cứ sang nơi không nằm trong quyền của DBA ứng dụng. Nhưng việc service quên ghi outbox vẫn là lỗi có thể xảy ra. Nếu yêu cầu bao phủ mọi SQL UPDATE vào một bảng, trigger hoặc một ranh giới ghi được kiểm soát nghiêm là phần cần xem xét.

### 11.3. CDC không tự mang business actor

CDC có thể phát luồng INSERT/UPDATE/DELETE đã commit. Nhưng một thay đổi hàng thường chỉ có bảng, khóa và giá trị dữ liệu, **không tự biết người dùng HTTP nào thực hiện**. Muốn truy vết actor, phải ghi actor/operation context vào bảng audit, outbox hoặc metadata có thể được connector lấy ra đáng tin.

CDC có thể gặp backlog, slot giữ WAL quá lâu, offset mất hoặc schema change không tương thích. Cần monitoring lag, khả năng restart, replay và duplicate delivery.

## 12. Bảo vệ quyền và độ tin cậy của actor

Audit chỉ đáng tin trong **mô hình đe dọa** đã xác định. Nếu cùng một role có thể UPDATE đơn hàng, UPDATE bảng audit, ALTER trigger và vô hiệu hóa pipeline, không thể tuyên bố audit bất biến.

### 12.1. Phân tách quyền

| Vai trò | Quyền gợi ý |
|---|---|
| **app_runtime** | DML trên bảng nghiệp vụ đúng phạm vi; không sửa trực tiếp bảng audit hoặc trigger |
| **audit_function_owner** | Sở hữu trigger function/quyền INSERT audit theo SECURITY DEFINER; không dùng đăng nhập thường |
| **audit_reader** | SELECT qua view/API có lọc theo tenant và masking |
| **migration_role** | DDL được phê duyệt và lưu lịch sử, không dùng cho HTTP request |
| **auditor/security role** | Truy xuất bằng chứng và kiểm tra admin actions có giám sát |
| **DBA/superuser** | Đặc quyền cao, cần tách nhiệm vụ và kênh giám sát độc lập |

Với **SECURITY DEFINER**, phải bảo vệ role sở hữu function, giới hạn quyền CREATE/ALTER/EXECUTE và cố định **search_path** an toàn; không viết dynamic SQL tùy tiện từ input. Role runtime không được có quyền trực tiếp thay đổi bảng audit.

Giá trị đọc qua **current_setting('app.actor_id', true)** chỉ là một session/transaction setting. Một kẻ có quyền chạy SQL bất kỳ dưới role ứng dụng có thể giả mạo setting. Cần **principal đã xác thực, authorization, PreparedStatement, kiểm soát kết nối và giám sát**; không gọi setting đó là chữ ký danh tính.

### 12.2. Phân quyền đọc audit

Bảng audit có thể chứa những chi tiết mà người dùng thường không được phép xem:

- Không cấp SELECT công khai lên bảng audit.
- Truy vấn qua service/view lọc tenant, role và đối tượng được phép.
- Mask các giá trị nhạy cảm ở lớp đọc khi thật sự cần, nhưng tốt nhất không ghi các secret từ đầu.
- Log việc export lớn hoặc truy cập dữ liệu nhạy cảm nếu yêu cầu.
- Không đưa payload audit thô vào HTTP response, log debug hoặc màn hình dashboard công khai.
- Không cho ứng dụng thường xóa/đổi bản ghi audit đã commit.

Người được xem lịch sử đơn hàng của tenant A không tự động được xem old_row/new_row của tenant B.

## 13. Tăng khả năng phát hiện sửa đổi

### 13.1. Append-only theo quyền

Role runtime không có UPDATE/DELETE/TRUNCATE trên audit. Trigger chỉ INSERT. Đây là bảo vệ cơ bản, **không chống được tất cả thao tác của chủ sở hữu hoặc DBA quyền cao**.

### 13.2. Lưu trữ độc lập

Có thể xuất audit đã commit sang kho khác có credentials, quyền xóa/sửa và retention độc lập, chẳng hạn hệ thống logging tập trung có tính immutable retention/WORM hoặc nền tảng audit chuyên dụng.

Cần hỏi: ai quản lý khóa mã hóa, ai có thể sửa retention policy, có thể tắt exporter mà không bị phát hiện không, khi pipeline lỗi thì có backlog/replay không, việc restore và verify được diễn tập chưa?

### 13.3. Hash chain và anchor

Một kiến trúc **tamper-evident** có thể liên kết hash của event mới với hash trước:

~~~text
event1 -> H1 = HASH(canonical(event1), anchor0)
event2 -> H2 = HASH(canonical(event2), H1)
event3 -> H3 = HASH(canonical(event3), H2)
                  |
                  v
       Xuất H3 tới nguồn tin cậy độc lập
~~~

Để có giá trị thực, phải thiết kế:

1. **Canonical serialization** thống nhất thứ tự trường, mã hóa, timezone, biểu diễn số.
2. **Thứ tự logic chính xác**; event_id từ sequence không mặc nhiên là thứ tự COMMIT.
3. **Điều phối ghi song song**, nếu muốn một hash chain đơn nhất không bị rẽ nhánh.
4. **Anchor/chữ ký nằm ngoài quyền của tác nhân có thể sửa DB**.
5. Verification định kỳ, phát hiện thiếu event và quy trình xử lý khi archive/rotate key.

Hash nằm cùng bảng và có thể tính lại bởi kẻ có toàn quyền sửa DB **không đủ chứng minh không bị chỉnh sửa**. Chuỗi hash cũng không chứng minh đã capture hết event nếu trigger có thể bị tắt không bị giám sát.

### 13.4. Replication và backup

Backup/WAL giúp recovery nhưng không tự biến bảng audit thành chứng cứ chống sửa đổi. Với asynchronous replication, một failover có thể mất một số transaction đã xác nhận trên primary cũ tùy cấu hình và thời điểm. Cần xác định **RPO/RTO của cả dữ liệu nghiệp vụ lẫn audit** và đối soát với kho ngoài khi phục hồi.

## 14. Giảm thiểu dữ liệu nhạy cảm

Audit thường lưu dữ liệu **lâu hơn** bảng nghiệp vụ, nên việc sao chép cả OLD/NEW làm tăng nguy cơ lộ PII và secret.

### 14.1. Không ghi mặc định những gì?

- Password, password hash, reset token, refresh/access token, API keys.
- Private key và credential dùng kết nối database/dịch vụ.
- Số thẻ thanh toán đầy đủ, mã xác minh thẻ hoặc thông tin xác thực nhạy cảm.
- Thông tin định danh, y tế và hồ sơ cá nhân vượt nhu cầu đã được phê duyệt.
- HTTP request/response chứa payload nhạy cảm không liên quan đến quyết định thay đổi.

Với bảng users chứa email, password_hash và reset_token, **không dùng to_jsonb(NEW) toàn hàng** làm audit mặc định.

### 14.2. Chọn trường được phép ghi

Ví dụ chỉ chọn cột phục vụ điều tra:

~~~sql
SELECT jsonb_build_object(
    'id', o.id,
    'status', o.status,
    'updated_at', o.updated_at
)
FROM public.orders AS o
WHERE o.id = 19002;
~~~

Trong trigger, dùng phép **jsonb_build_object** từ OLD/NEW theo whitelist thích hợp. Khi migration thêm cột nhạy cảm, danh sách audit đã cho phép phải được review, không tự mở rộng bằng full-row snapshot.

- **Masking** giảm chi tiết hiển thị.
- **Hash** giúp so sánh, nhưng không tự ẩn danh hoàn toàn giá trị có không gian nhỏ.
- **Encryption** bảo vệ ở trạng thái lưu/truyền, vẫn phải quản lý khóa và quyền giải mã.
- **Tokenization** giúp tách dữ liệu gốc khỏi audit khi có token vault đáng tin.

## 15. Retention, privacy và legal hold

Audit cần giữ đủ lâu cho điều tra, nhưng không nên mặc định lưu mọi PII mãi mãi. Chính sách phải xác định **theo loại sự kiện và nhu cầu được phê duyệt**:

- Thời gian lưu từng loại audit event và quyền truy xuất.
- Cách archive, export và chứng minh dữ liệu vẫn đầy đủ.
- Điều kiện **legal hold** hoặc yêu cầu điều tra kéo dài thời gian giữ.
- Khi hết hạn: xóa/ẩn danh, phê duyệt và ghi lại bằng chứng xử lý.
- Dữ liệu trong backup, replica, log tập trung và kho xuất ngoài.
- Quy trình xử lý yêu cầu của chủ thể dữ liệu khi pháp luật/chính sách có các nghĩa vụ khác nhau.

Không nên suy diễn một thời hạn lưu giữ cố định áp dụng cho mọi quốc gia, loại dữ liệu hoặc tổ chức.

### 15.1. Partition theo thời gian

Với audit khối lượng lớn, có thể tổ chức theo kỳ:

~~~text
audit.change_events
    |
    +-- change_events_2026_11
    +-- change_events_2026_12
    +-- change_events_2027_01
~~~

Đây là sơ đồ, không phải DDL có thể dùng để chuyển ngay bảng đang chạy. Partition lifecycle/archive có thể giảm chi phí xóa dữ liệu cũ, nhưng cần thiết kế đúng **khóa chính, unique constraint, index, quyền và migration/backfill** theo PostgreSQL. Chỉ archive/drop partition khi retention cho phép và đã xác minh bản sao cần giữ.

## 16. Chi phí hiệu năng của nhật ký kiểm toán

Trigger cùng transaction nằm trên **đường ghi của nghiệp vụ**: mỗi hàng thay đổi có thể thêm một INSERT audit, dữ liệu JSONB, cập nhật index và WAL.

| Nguồn overhead | Hệ quả |
|---|---|
| Row trigger chạy trên nhiều hàng | CPU tăng theo số thay đổi |
| Full OLD/NEW JSONB | Nhiều byte hơn, WAL và storage tăng |
| Index audit | Làm INSERT vào audit tốn thêm công việc |
| Transaction chứa audit write | Tăng thời gian giữ Connection và khóa |
| Truy vấn audit trên primary | Cạnh tranh I/O/cache/CPU với nghiệp vụ |
| Export qua CDC/outbox | Có lag/backlog và chi phí mạng |
| Retention không giới hạn | Bảng/index lớn, backup/vacuum tốn tài nguyên |

Không có tỷ lệ overhead chuẩn. Cần benchmark bằng workload thật và dữ liệu ẩn danh, đo:

1. Throughput INSERT/UPDATE/DELETE và latency p50/p95/p99.
2. Thời gian COMMIT, transaction duration và pool active/pending.
3. WAL bytes/s, replication lag và dung lượng bảng/index audit.
4. Hiệu năng các query điều tra theo entity/actor/request.
5. Rollback/error rate khi trigger/audit storage gặp sự cố.
6. Tác động batch update/backfill và các migration lớn.

**Không tự tắt trigger khi import/backfill để tăng tốc** nếu việc bỏ audit vi phạm yêu cầu an toàn. Cần chính sách dữ liệu và biện pháp thay thế đã được review, có khả năng chứng minh phạm vi ghi trong giai đoạn đó.

## 17. Lỗi kết nối, retry và idempotency khi ghi audit

### 17.1. Audit lỗi trong cùng transaction

Nếu trigger audit không thể INSERT do thiếu quyền, constraint, hết dung lượng hoặc lỗi DB, câu lệnh nghiệp vụ cũng thất bại. Trong thiết kế **fail closed**, hệ thống không tiếp tục COMMIT thay đổi mà thiếu bản ghi audit bắt buộc.

Ngược lại, nếu service COMMIT trước rồi gửi audit sang hệ ngoài:

~~~text
UPDATE orders -> COMMIT thành công
      |
      v
Gửi audit message -> Broker timeout
      |
      v
Dữ liệu đã đổi nhưng không có audit bên ngoài
~~~

Vì thế mẫu “COMMIT DB, sau đó gửi message trực tiếp” **không có tính nguyên tử**. Outbox transactional hoặc CDC là các lựa chọn giảm khoảng trống này, nhưng chúng vẫn cần vận hành backlog, retry và chống phát trùng.

### 17.2. COMMIT chưa rõ kết quả

Nếu Java gửi COMMIT rồi mất kết nối, transaction có thể **đã commit cùng audit event**, nhưng client không nhận phản hồi. Không được tự kết luận “chưa thay đổi” rồi retry bằng ID nghiệp vụ mới.

Cần **operation_id/idempotency key** ổn định được lưu cùng transaction nghiệp vụ, với UNIQUE hoặc cơ chế tương đương. Khi có lỗi, đối soát operation ID và trạng thái mới ở nguồn có thẩm quyền. **request_id** hỗ trợ tra cứu nhưng không tự đảm bảo idempotency nếu không có ràng buộc và quy trình lưu/trả kết quả.

### 17.3. Retry có thể tạo nhiều event

- Transaction bị PostgreSQL hủy do **40001**: audit event trong transaction cũng rollback. Retry toàn transaction thành công mới tạo event đã commit.
- Transaction đã COMMIT nhưng client mất phản hồi: chạy lại nghiệp vụ mà không có idempotency có thể tạo **thay đổi thật lần hai** và sinh audit event lần hai.
- Hai nghiệp vụ thật sự độc lập cùng đổi một hàng: có thể cần hai event và phải giữ cả hai.

Không xóa dấu vết trùng bằng cách giữ event mới nhất. Cần đối chiếu operation ID và lý do vì sao có các lần thực hiện.

## 18. Schema evolution và các đường thay đổi đặc biệt

### 18.1. Thay đổi schema ảnh hưởng cả audit

Nếu trigger dùng **to_jsonb(NEW)** toàn hàng, thêm cột nhạy cảm bằng migration sẽ tự đưa cột đó vào nhật ký. Mỗi schema migration cần kiểm tra:

1. Những trường mới có được phép audit không?
2. Masking/whitelist có cần cập nhật không?
3. Consumer của schema JSONB audit có hỗ trợ phiên bản mới không?
4. Backfill hàng loạt sẽ tạo bao nhiêu audit events và WAL?
5. Có job nào cập nhật bảng mà không đặt actor context không?
6. Query điều tra và retention có cần điều chỉnh?

### 18.2. TRUNCATE, DDL, SELECT

Row-level trigger minh họa chỉ bắt INSERT/UPDATE/DELETE, không bắt SELECT hoặc TRUNCATE, cũng không tự audit ALTER TABLE/ALTER ROLE. Để theo dõi những thao tác này cần **DB statement/access/DDL audit** hoặc kênh giám sát tương ứng; tránh coi row trigger là cơ chế audit toàn bộ hoạt động.

### 18.3. Bulk import, maintenance và replication

COPY hoặc batch import thông thường có thể kích hoạt row triggers theo cơ chế PostgreSQL, nhưng một số chế độ replication hoặc công việc quản trị có quy tắc riêng về trigger. Cần kiểm thử theo phiên bản/cấu hình, không khẳng định mọi thay đổi đều đi qua cùng trigger.

Migration/backfill được phép phải có **actor hệ thống** đã xác thực, chẳng hạn migration-job:release-123, kèm request/operation ID phù hợp. Không giả danh một người dùng cuối để che giấu đường ghi của job.

## 19. Kiểm thử tính đúng và khả năng chống sai lệch

Dùng test database tách biệt, dữ liệu giả và quyền gần với production.

| Kịch bản | Kỳ vọng |
|---|---|
| INSERT rồi COMMIT | Event INSERT với new_row đúng |
| UPDATE rồi COMMIT | Event UPDATE có old/new, actor, request ID đúng |
| DELETE rồi COMMIT | Event DELETE có old_row |
| UPDATE rồi ROLLBACK | Dữ liệu và audit cùng rollback |
| UPDATE vi phạm constraint | Không có committed data-change event cho thao tác lỗi |
| UPDATE không khớp hàng | Không sinh row trigger event |
| Không đặt actor | Trigger từ chối theo chính sách fail closed |
| Hai actor dùng lại cùng pool connection | Context không rò từ request trước sang request sau |
| Runtime role sửa/xóa audit | Bị từ chối bởi quyền DB |
| Admin disable/ALTER trigger | Hành động được giám sát bởi kênh độc lập |
| Schema thêm trường secret | Audit không ghi thêm secret |
| Batch UPDATE nhiều hàng | Số event và latency phù hợp phạm vi đã định |
| Mất phản hồi COMMIT | Không tạo nghiệp vụ trùng khi retry; có đối soát |
| CDC/outbox ngừng tạm thời | Backlog đo được, replay có dedup |
| Restore backup | Đối soát dữ liệu/audit và bản lưu độc lập |
| Hết retention hoặc legal hold | Chỉ xóa dữ liệu được phép, có log quy trình |

### 19.1. Test ROLLBACK

~~~sql
BEGIN;

SELECT set_config('app.actor_id', 'test-user', true);
SELECT set_config('app.request_id', 'test-rollback', true);

UPDATE public.orders
SET status = 'CANCELLED',
    updated_at = clock_timestamp()
WHERE id = 19002 AND tenant_id = 7;

ROLLBACK;

SELECT id, status
FROM public.orders
WHERE id = 19002 AND tenant_id = 7;

SELECT event_id
FROM audit.change_events
WHERE request_id = 'test-rollback';
~~~

**Kỳ vọng:** trạng thái orders không đổi sau ROLLBACK; không tồn tại committed event cho test-rollback. Test cần dùng request ID duy nhất/fixture độc lập để tránh nhầm với bản ghi từ lần thử khác.

### 19.2. Test COMMIT

~~~sql
BEGIN;

SELECT set_config('app.actor_id', 'test-user', true);
SELECT set_config('app.request_id', 'test-commit', true);

UPDATE public.orders
SET status = 'CANCELLED',
    updated_at = clock_timestamp()
WHERE id = 19002
  AND tenant_id = 7
  AND status = 'PAID';

COMMIT;

SELECT action, actor_id, request_id,
       old_row ->> 'status' AS old_status,
       new_row ->> 'status' AS new_status
FROM audit.change_events
WHERE request_id = 'test-commit'
ORDER BY event_id;
~~~

Nếu hàng ban đầu ở PAID và câu UPDATE ảnh hưởng đúng một hàng, kỳ vọng event mô tả **PAID → CANCELLED**. Khi test tiếp, cần reset fixture: nếu đơn đã CANCELLED, UPDATE có điều kiện không khớp nên không phát event. Không chạy các câu UPDATE demo trên production.

### 19.3. Test actor và connection pool

Một ca quan trọng với Java:

1. Request A được xác thực là Alice, thực hiện UPDATE trên Connection được pool cấp và COMMIT.
2. Request B được xác thực là Bob, sau đó có thể mượn chính physical Connection ấy và UPDATE.
3. Kiểm tra audit của A ghi Alice, audit của B ghi Bob, không có giá trị dư từ A.
4. Bỏ actor context trong một request test và xác minh trigger từ chối.
5. Mô phỏng exception và rollback giữa chừng, kiểm tra context không tồn tại trong request sau.

Test này chứng minh cơ chế transaction-local context hoạt động đúng trong điều kiện tái sử dụng Connection; không thay thế việc bảo vệ principal khỏi giả mạo ở tầng xác thực.

## 20. Triển khai, vận hành và quan sát

Một checklist triển khai cho một bảng dữ liệu nhạy về nghiệp vụ:

1. **Xác định phạm vi:** bảng, loại thao tác, trường cũ/mới cần lưu, actor, correlation.
2. **Định nghĩa tính đúng:** committed changes hay cả attempted actions, yêu cầu fail-closed/fail-open được phê duyệt.
3. **Thiết kế schema:** sự kiện, khóa tìm kiếm, JSON version, retention, tenant isolation.
4. **Phân quyền:** app runtime, trigger owner, audit readers, DBA, migration role.
5. **Cài đặt:** trigger cùng transaction hoặc audit/outbox cùng Connection theo hợp đồng rõ.
6. **Truyền principal:** actor tin cậy, transaction-local context, actor hệ thống cho background jobs.
7. **Kiểm thử:** commit/rollback, exception, pool reuse, retry, COMMIT chưa rõ, concurrent update.
8. **Đo tải:** write p95/p99, WAL, table size, replication lag, thời gian query điều tra.
9. **Xuất độc lập nếu cần:** outbox/CDC, retention bất biến, verify offset/hash/count.
10. **Đảm bảo vận hành:** cảnh báo exporter lỗi, kiểm soát truy cập, retention, backup/restore và review khi migration.

### 20.1. Metric gợi ý

- **audit_events_inserted_total**: tổng số audit events được ghi.
- **audit_write_failure_total**: số lỗi ghi audit.
- **audit_missing_actor_total**: ghi bị từ chối vì thiếu actor.
- **audit_export_backlog** và **audit_export_lag_seconds**.
- **audit_storage_bytes** theo kỳ/partition.
- **audit_query_duration_p95/p99**.
- **audit_integrity_check_failures_total**.
- **audit_access_denied_total** hoặc số lần export audit.
- **unknown_commit_outcome_total** ở tầng service.
- Tương quan giữa **business writes** và **audit events** theo operation, hiểu đúng DELETE/UPDATE no-op.

Đây là **tên metric gợi ý**, không phải tên mặc định từ PostgreSQL hoặc JDBC. Tránh gắn user_id, event_id hoặc request_id vào mọi metric label gây cardinality lớn. Chi tiết điều tra có thể nằm trong trace/log được bảo vệ quyền.

## 21. Các lỗi thiết kế thường gặp

| Sai lầm | Vấn đề | Cách sửa |
|---|---|---|
| Coi application log là audit dữ liệu | Log có thể ghi trước COMMIT hoặc thiếu đường ghi | Audit transactional, kiểm tra committed changes |
| Coi WAL là lịch sử actor nghiệp vụ | WAL phục vụ durability/replication | Audit event có actor/context riêng |
| Tin trigger audit sẽ lưu cả UPDATE rollback | Event trigger trong cùng transaction cũng rollback | Kênh attempt/security log riêng |
| Coi bảng audit là bất biến tuyệt đối | Người đặc quyền cao có thể sửa | Phân quyền và lưu/anchor độc lập |
| Dùng current_user làm user HTTP | DB role thường dùng chung | Principal đã xác thực từ app |
| Đặt actor session-wide qua pool | Rò danh tính giữa các request | Context transaction-local |
| Coi request_id là chống trùng | Không có UNIQUE/giao thức | Operation ID/idempotency |
| Dùng to_jsonb(NEW) cho mọi bảng | Vô tình lưu password hash/PII | Whitelist và masking |
| Coi event_id là thứ tự COMMIT | Sequence cấp ID trước COMMIT, có gaps | Không suy ra thứ tự nếu thiếu cơ chế commit ordering |
| Coi CDC tự biết actor cuối | CDC chủ yếu thấy row changes | Gắn actor tại nguồn/outbox |
| Gửi audit qua broker sau COMMIT trực tiếp | Broker lỗi thì audit thiếu | Transactional outbox/CDC |
| Hash lưu cùng DB là chống DBA sửa | Kẻ có quyền có thể tính lại hash | Anchor/chữ ký ngoài quyền DB |
| Lưu mọi audit vĩnh viễn | Rủi ro privacy và storage | Retention, data minimization, legal hold |
| Row trigger bắt được SELECT và DDL | Không đúng phạm vi trigger | Access/DDL audit riêng |
| Tắt trigger để backfill nhanh hơn | Mất dấu vết nếu không có thay thế | Review, đo tải và quy trình riêng |
| Khi audit lỗi thì cứ bỏ qua để API chạy | Dữ liệu thay đổi nhưng thiếu event bắt buộc | Fail-closed hoặc giao thức thay thế được phê duyệt |

## 22. Bài tập tự kiểm tra

### Bài 1 — Đã commit hay chỉ được thử?

Một service UPDATE orders rồi rollback vì bước nghiệp vụ sau thất bại. Trigger ví dụ có để lại audit event không? Làm sao ghi nhận lần thử đó?

**Gợi ý:** event cùng transaction rollback. Dùng attempt/security log riêng nếu cần theo dõi cả thao tác bị hủy.

### Bài 2 — Actor đáng tin

API mở Connection bằng app_runtime cho mọi khách hàng. Vì sao lưu current_user chưa đủ?

**Gợi ý:** DB chỉ thấy role dùng chung. Cần principal đã xác thực và context transaction-local.

### Bài 3 — Rò context pool

Request A đặt session actor là Alice rồi trả Connection. Request B mượn lại và ghi đơn. Rủi ro?

**Gợi ý:** audit của B có thể bị gắn Alice. Dùng set_config(..., true) trong transaction và test pool reuse.

### Bài 4 — Không lưu secret

Một bảng users có email, password_hash, reset_token và status. Trigger dùng to_jsonb(NEW) toàn hàng. Cần sửa gì?

**Gợi ý:** audit whitelist các trường thật sự cần, không ghi token/password hash, hạn chế PII và truy cập.

### Bài 5 — CDC thiếu thông tin

CDC phát hiện UPDATE orders. Vì sao chưa thể kết luận nhân viên nào sửa?

**Gợi ý:** thông điệp thay đổi hàng không tự mang business actor. Cần context đã ghi tại nguồn.

### Bài 6 — Thứ tự ID

Transaction A nhận event_id 100, B nhận 101, nhưng B COMMIT trước A. Có thể khẳng định 100 được commit trước 101 không?

**Gợi ý:** không. Sequence ID không phải commit order.

### Bài 7 — Chống chỉnh sửa

DB owner có thể UPDATE bảng audit và tính lại hash cùng nằm trong database. Băm có đủ chứng minh không bị sửa không?

**Gợi ý:** không. Cần anchor, chữ ký hoặc hệ độc lập theo threat model.

### Bài 8 — Gửi audit sau COMMIT

Service COMMIT đơn hàng, sau đó gửi message audit nhưng broker timeout. Hai hành động đã nguyên tử chưa?

**Gợi ý:** chưa. Cân nhắc transactional outbox/CDC.

### Bài 9 — Schema mới có PII

Migration thêm identity_document; trigger dùng full-row to_jsonb(NEW). Cần review điểm nào?

**Gợi ý:** cột mới sẽ vào audit, có thể chứa thông tin nhạy cảm; chuyển sang whitelist/masking.

### Bài 10 — COMMIT chưa rõ

Java gửi COMMIT rồi mất connection. Có thể ghi “transaction thất bại” và tạo order ID mới để retry không?

**Gợi ý:** không. Server có thể đã commit. Dùng operation ID ổn định và đối soát.

## 23. Ghi nhớ và áp dụng

**Nhật ký kiểm toán cần trả lời ai đã thay đổi gì, khi nào, từ trạng thái nào sang trạng thái nào, và theo yêu cầu nào.** Để ghi lịch sử *thay đổi dữ liệu đã commit*, audit event nên cùng commit/rollback với dữ liệu nghiệp vụ. PostgreSQL row trigger hoặc audit/outbox cùng transaction là những lựa chọn có thể áp dụng, nhưng không tự bắt mọi lần SELECT, thao tác bị từ chối, DDL hay thay đổi của người có đặc quyền cao.

Trong Java, hãy truyền actor **đã xác thực** trên đúng Connection và trong phạm vi transaction để tránh rò danh tính qua pool. Khi COMMIT chưa rõ, dùng idempotency và đối soát thay vì chạy lại mù quáng. Bảo vệ audit bằng least privilege, tối thiểu hóa dữ liệu nhạy cảm, retention, giám sát và lưu/verify độc lập khi cần chống sửa đổi.

**Audit trail tốt không chỉ ghi được nhiều dòng**: nó còn phải đúng về transaction, có attribution đáng tin, có thể tra cứu khi điều tra, không nhân đôi rủi ro riêng tư và không phá khả năng phục hồi của hệ thống persistence.

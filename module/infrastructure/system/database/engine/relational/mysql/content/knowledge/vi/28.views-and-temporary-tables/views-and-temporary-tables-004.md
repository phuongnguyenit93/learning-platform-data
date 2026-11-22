# SQL SECURITY DEFINER/INVOKER và quyền truy cập qua view

View là một đối tượng truy vấn được lưu trong schema. Ngoài việc đơn giản hóa SQL, view còn có thể tạo một giao diện truy cập dữ liệu với phạm vi cột hoặc hàng được chọn. Trong MySQL, mệnh đề SQL SECURITY quyết định quyền của tài khoản nào được dùng khi câu lệnh truy cập view chạy: tài khoản định nghĩa view (DEFINER) hay tài khoản đang gọi view (INVOKER).

Với SQL SECURITY DEFINER, người dùng có thể được cấp SELECT trên view mà không cần quyền trực tiếp trên các bảng nền. MySQL kiểm tra quyền đọc bảng nền theo tài khoản DEFINER. Cách này phù hợp để cung cấp dữ liệu đã giới hạn cho nhóm báo cáo hoặc ứng dụng. Với SQL SECURITY INVOKER, quyền truy cập bảng nền được kiểm tra theo người đang gọi view; view không tự nâng quyền cho người dùng.

Hai chế độ này là một phần của mô hình phân quyền, không chỉ là tùy chọn cú pháp. Chọn sai có thể khiến người dùng không đọc được view, hoặc khiến một view vô tình phơi bày dữ liệu mà tài khoản gọi không nên xem. Bài học này tập trung vào cách MySQL xác định security context, quyền cần có khi tạo và truy vấn view, cách cấp quyền tối thiểu và cách kiểm tra tài khoản DEFINER trong vận hành.

## 1. View và security context

View lưu một câu SELECT dưới tên đối tượng trong schema. Ví dụ:

```sql
CREATE VIEW reporting.v_order_summary AS
SELECT
    order_id,
    created_at,
    status,
    total_amount
FROM sales.orders;
```

Khi người dùng chạy:

```sql
SELECT *
FROM reporting.v_order_summary;
```

MySQL cần xác định quyền nào được dùng để đọc sales.orders. Quyết định đó dựa trên thuộc tính SQL SECURITY của view.

Hai chế độ:

- SQL SECURITY DEFINER: kiểm tra quyền truy cập đối tượng nền theo tài khoản DEFINER của view.
- SQL SECURITY INVOKER: kiểm tra quyền truy cập đối tượng nền theo tài khoản đang thực thi câu truy vấn.

Nếu không ghi SQL SECURITY, MySQL mặc định dùng DEFINER.

### 1.1. DEFINER là ai?

DEFINER là tài khoản MySQL được ghi cùng định nghĩa view. Nếu không chỉ định DEFINER = ..., tài khoản tạo view trở thành definer.

Ví dụ:

```sql
CREATE DEFINER = 'view_owner'@'localhost'
SQL SECURITY DEFINER
VIEW reporting.v_order_summary AS
SELECT order_id, status, total_amount
FROM sales.orders;
```

Trong ví dụ này, 'view_owner'@'localhost' là tài khoản dùng để kiểm tra quyền trên sales.orders khi view được gọi theo chế độ DEFINER.

Tên tài khoản gồm cả user và host. 'view_owner'@'localhost' và 'view_owner'@'10.%' là hai account khác nhau, có thể có quyền khác nhau.

### 1.2. INVOKER là ai?

INVOKER là tài khoản kết nối đang chạy câu SELECT trên view. Khi dùng SQL SECURITY INVOKER, quyền trên các bảng và cột được tham chiếu trong định nghĩa view được kiểm tra theo account này.

Ví dụ:

```sql
CREATE SQL SECURITY INVOKER
VIEW reporting.v_order_summary_invoker AS
SELECT order_id, status, total_amount
FROM sales.orders;
```

Nếu report_reader gọi view, MySQL kiểm tra quyền cần thiết của report_reader trên các cột của sales.orders. Có quyền SELECT trên view thôi chưa đủ nếu account không có quyền cần thiết trên đối tượng nền.

## 2. So sánh DEFINER và INVOKER

| Tiêu chí | SQL SECURITY DEFINER | SQL SECURITY INVOKER |
|---|---|---|
| Security context khi đọc bảng nền | Tài khoản DEFINER | Tài khoản gọi view |
| Người gọi có cần quyền trực tiếp trên bảng nền? | Không, nếu quyền qua view đã được cấp và definer có quyền cần thiết | Có, cần các quyền nền tương ứng |
| Có thể dùng view để cung cấp tập cột giới hạn? | Có, là mẫu phổ biến | Không che được quyền nền nếu người gọi đã được cấp SELECT trực tiếp trên các cột đó |
| Có thể cung cấp dữ liệu cho user không có quyền bảng nền? | Có | Không |
| Rủi ro chính | Definer có quyền quá rộng hoặc view lộ dữ liệu ngoài ý muốn | Người gọi thiếu quyền trên bảng/cột nền nên truy vấn thất bại |
| Trường hợp phù hợp | Cổng truy cập có kiểm soát cho ứng dụng/reporting | View tái sử dụng SQL nhưng vẫn giữ quyền theo từng người gọi |

Ví dụ dễ nhớ:

- DEFINER: người gọi được đọc phần mà view cho phép, trong phạm vi quyền của definer.
- INVOKER: người gọi view phải có quyền đọc dữ liệu nền mà câu truy vấn view cần.

Câu mô tả này nói về security context khi MySQL kiểm tra quyền. Nó không có nghĩa DEFINER tự động giới hạn hàng theo từng người dùng. Điều kiện WHERE trong view phải được thiết kế đúng yêu cầu dữ liệu.

## 3. Quyền cần có khi tạo view

Để tạo view, account thực hiện lệnh cần quyền CREATE VIEW trên schema đích và quyền SELECT trên các cột được tham chiếu trong câu SELECT định nghĩa view.

Ví dụ chuẩn bị schema và bảng:

```sql
CREATE DATABASE IF NOT EXISTS sales;
CREATE DATABASE IF NOT EXISTS reporting;

CREATE TABLE sales.orders (
    order_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_email VARCHAR(320) NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;
```

Tạo account dành riêng làm definer:

```sql
CREATE USER 'view_owner'@'localhost'
    IDENTIFIED BY 'replace-with-a-managed-secret';

GRANT CREATE VIEW ON reporting.*
    TO 'view_owner'@'localhost';

GRANT SELECT (
    order_id,
    tenant_id,
    status,
    total_amount,
    created_at
)
ON sales.orders
TO 'view_owner'@'localhost';
```

Sau đó kết nối bằng account view_owner và tạo view. Khi không chỉ định DEFINER, chính account này trở thành definer:

```sql
CREATE SQL SECURITY DEFINER
VIEW reporting.v_tenant_order_summary AS
SELECT
    order_id,
    tenant_id,
    status,
    total_amount,
    created_at
FROM sales.orders
WHERE status <> 'CANCELLED';
```

Việc tạo view và quyền chạy view là hai thời điểm kiểm tra khác nhau. Account tạo view cần quyền để định nghĩa câu SELECT. Khi view được gọi, MySQL tiếp tục kiểm tra quyền theo SQL SECURITY và các quyền hiện có tại thời điểm đó.

### 3.1. Chỉ định DEFINER khác tài khoản hiện tại

Có thể ghi rõ DEFINER = 'user'@'host' trong CREATE VIEW. Tuy nhiên, việc tạo object với definer khác current account chịu kiểm soát bởi các quyền quản trị đặc biệt; tên và yêu cầu quyền có thể khác theo phiên bản MySQL.

Trong các bản MySQL 8.0, các quyền liên quan đến definer đã thay đổi theo phiên bản, gồm các dynamic privilege như SET_USER_ID, SET_ANY_DEFINER và ALLOW_NONEXISTENT_DEFINER. Không cấp các quyền này rộng rãi chỉ để tạo view.

Mẫu dễ kiểm soát hơn là kết nối bằng account dịch vụ dự định làm definer, cấp cho account đó đúng quyền CREATE VIEW và SELECT cần thiết, rồi tạo view khi đăng nhập bằng account ấy.

## 4. Cấp quyền SELECT trên view cho người dùng

Sau khi view đã được tạo, quản trị viên cấp quyền trên chính view cho nhóm người đọc:

```sql
CREATE USER 'report_reader'@'10.%'
    IDENTIFIED BY 'replace-with-a-managed-secret';

GRANT SELECT
ON reporting.v_tenant_order_summary
TO 'report_reader'@'10.%';
```

Với view SQL SECURITY DEFINER, report_reader có thể đọc view mà không cần quyền SELECT trực tiếp trên sales.orders, miễn là:

- Người gọi có quyền SELECT trên view.
- Account DEFINER tồn tại và có đủ quyền trên bảng/cột nền mà view cần.
- View không phụ thuộc vào một đối tượng khác mà definer không có quyền truy cập.
- Các điều kiện bảo mật khác của ứng dụng và server được đáp ứng.

Không cấp thêm GRANT SELECT ON sales.* cho report_reader nếu mục tiêu là buộc người dùng đi qua view. Quyền trực tiếp trên bảng nền có thể cho phép họ đọc dữ liệu ngoài phạm vi view.

### 4.1. Kiểm tra quyền đã cấp

Đăng nhập bằng account đọc báo cáo và thử:

```sql
SELECT *
FROM reporting.v_tenant_order_summary
LIMIT 20;
```

Kiểm tra rằng truy cập bảng nền bị từ chối nếu account không được cấp quyền trực tiếp:

```sql
SELECT *
FROM sales.orders
LIMIT 20;
```

Kết quả mong đợi: truy vấn qua view thành công; truy vấn trực tiếp bảng nền báo lỗi quyền truy cập. Đây là cách kiểm thử quan trọng để xác nhận mô hình phân quyền hoạt động đúng như dự kiến.

Xem quyền của account:

```sql
SHOW GRANTS FOR 'report_reader'@'10.%';
SHOW GRANTS FOR 'view_owner'@'localhost';
```

SHOW GRANTS giúp kiểm tra cả quyền trên view lẫn quyền của definer. Nếu dùng roles, cần xem các role được cấp và trạng thái kích hoạt theo chính sách của account.

## 5. View có thể giới hạn cột và hàng như thế nào?

Một view DEFINER có thể chỉ công bố các cột cần thiết và thêm điều kiện lọc:

```sql
CREATE SQL SECURITY DEFINER
VIEW reporting.v_public_orders AS
SELECT
    order_id,
    tenant_id,
    status,
    total_amount,
    created_at
FROM sales.orders
WHERE status IN ('PAID', 'PENDING');
```

Cột customer_email không xuất hiện trong view. Người chỉ có SELECT trên view không thể đọc cột này qua view.

Điều kiện WHERE cũng loại các hàng có status khác. Tuy nhiên, nếu view không được thiết kế theo ngữ cảnh tenant hoặc user, điều kiện trên không tự tạo row-level security cho từng tenant.

Ví dụ nếu mọi report_reader đều có thể xem tất cả tenant, view trên chỉ lọc status chứ không giới hạn tenant. Không nên gọi đó là cách ly dữ liệu tenant.

### 5.1. Tạo view riêng theo phạm vi dữ liệu

Nếu ứng dụng cần một phạm vi tenant cố định, có thể tạo view với điều kiện tenant cụ thể và chỉ cấp view tương ứng cho nhóm người dùng đó:

```sql
CREATE SQL SECURITY DEFINER
VIEW reporting.v_tenant_42_orders AS
SELECT
    order_id,
    status,
    total_amount,
    created_at
FROM sales.orders
WHERE tenant_id = 42
  AND status <> 'CANCELLED';
```

Cách này phù hợp khi số phạm vi cố định và quyền được quản lý rõ. Nếu có hàng nghìn tenant hoặc tenant thay đổi động theo người dùng, tạo một view cho từng tenant thường khó quản lý. Cần một kiến trúc phân quyền phù hợp hơn, ví dụ service layer kiểm tra tenant, schema/database tách biệt hoặc mô hình dữ liệu có cơ chế kiểm soát riêng.

Không dùng biến session do client tự đặt làm căn cứ bảo mật duy nhất nếu client có thể tự thay đổi biến đó.

## 6. SQL SECURITY INVOKER và quyền trên bảng nền

Một view INVOKER vẫn có ích để chuẩn hóa câu truy vấn, đặt tên nghiệp vụ và tái sử dụng JOIN/filter. Nhưng nó không cho người dùng mượn quyền của người tạo view.

Ví dụ tạo view:

```sql
CREATE SQL SECURITY INVOKER
VIEW reporting.v_orders_invoker AS
SELECT
    order_id,
    status,
    total_amount
FROM sales.orders
WHERE status <> 'CANCELLED';
```

Cấp quyền cho account đọc:

```sql
GRANT SELECT
ON reporting.v_orders_invoker
TO 'report_reader'@'10.%';

GRANT SELECT (
    order_id,
    status,
    total_amount
)
ON sales.orders
TO 'report_reader'@'10.%';
```

Khi report_reader truy vấn view, MySQL kiểm tra quyền trên các cột bảng nền theo account đó. Nếu view tham chiếu thêm cột trong WHERE, JOIN, GROUP BY hoặc biểu thức, quyền cần thiết phải bao gồm các cột được dùng theo quy tắc privilege checking của MySQL.

Với ví dụ trên, người dùng cũng có thể SELECT trực tiếp ba cột đã được cấp trên sales.orders. Do đó, INVOKER phù hợp khi muốn giữ nguyên quyền của caller, không phải khi cần che bảng nền.

### 6.1. Kiểm thử thiếu quyền

Nếu account chỉ được cấp SELECT trên view mà không có SELECT trên bảng nền, câu truy vấn qua INVOKER view sẽ thất bại:

```sql
-- Chạy bằng report_reader sau khi chỉ được GRANT SELECT trên view:
SELECT *
FROM reporting.v_orders_invoker;
```

Sau đó cấp quyền cột nền như ví dụ trước và thử lại. Việc so sánh hai lần giúp thấy rõ INVOKER sử dụng quyền của người gọi.

## 7. DEFINER phải có quyền gì khi view được gọi?

Với SQL SECURITY DEFINER, MySQL dùng security context của definer để kiểm tra các đối tượng nền. Account DEFINER cần có các quyền cần thiết đối với bảng, view, routine hoặc đối tượng được tham chiếu trong định nghĩa view.

Ví dụ view_owner chỉ được cấp SELECT trên một số cột:

```sql
SHOW GRANTS FOR 'view_owner'@'localhost';
```

Nếu sau này quản trị viên thu hồi quyền cần thiết:

```sql
REVOKE SELECT (total_amount)
ON sales.orders
FROM 'view_owner'@'localhost';
```

View tham chiếu total_amount có thể không còn thực thi được vì definer thiếu quyền trên cột đó. Việc tạo view thành công trước đây không có nghĩa quyền sẽ được giữ vĩnh viễn.

Khôi phục quyền cần thiết:

```sql
GRANT SELECT (total_amount)
ON sales.orders
TO 'view_owner'@'localhost';
```

Đây là lý do cần quản lý quyền của definer như một dependency của view. Khi thay đổi quyền trên bảng nền, phải kiểm tra các view, routine và ứng dụng phụ thuộc.

## 8. Vòng đời tài khoản DEFINER

Tài khoản DEFINER là một phần của metadata view. Nếu account bị xóa, đổi tên hoặc mất quyền cần thiết, view SQL SECURITY DEFINER có thể không chạy được.

Các vấn đề thường gặp:

- Xóa account dịch vụ nhưng quên các view đang tham chiếu nó.
- Restore schema sang môi trường khác nhưng không tạo account definer.
- Migration tạo view với definer là tài khoản cá nhân của developer.
- Definer có quyền quá rộng, ví dụ quyền quản trị toàn server.
- Thay đổi quyền trên bảng nền làm view lỗi khi runtime.

### 8.1. Dùng tài khoản dịch vụ ổn định

Nên dùng account riêng cho mục đích làm definer, có tên rõ và host cụ thể:

```sql
CREATE USER 'report_view_definer'@'localhost'
    IDENTIFIED BY 'managed-outside-the-application';
```

Cấp đúng các quyền cần cho view, ví dụ SELECT trên một số cột của bảng nguồn. Không dùng root hoặc account DBA làm definer chỉ vì nó có sẵn mọi quyền.

Tài khoản definer không nhất thiết là tài khoản ứng dụng đăng nhập thường xuyên. Có thể áp dụng chính sách xác thực, network và account phù hợp để hạn chế đăng nhập trực tiếp, nhưng cần xác minh hành vi account lock và quản lý tài khoản trên phiên bản server đang dùng trước khi triển khai.

### 8.2. Kiểm tra view có definer nào

Xem định nghĩa:

```sql
SHOW CREATE VIEW reporting.v_tenant_order_summary;
```

Xem metadata của các view trong schema:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    DEFINER,
    SECURITY_TYPE,
    CHECK_OPTION,
    IS_UPDATABLE
FROM information_schema.VIEWS
WHERE TABLE_SCHEMA = 'reporting'
ORDER BY TABLE_NAME;
```

Các trường quan trọng:

| Trường | Ý nghĩa |
|---|---|
| DEFINER | Account được ghi làm definer |
| SECURITY_TYPE | DEFINER hoặc INVOKER |
| CHECK_OPTION | NONE, LOCAL hoặc CASCADED |
| IS_UPDATABLE | View có thể cập nhật theo các điều kiện của MySQL hay không |

Có thể dùng kết quả này để kiểm tra definer tồn tại và so sánh với danh sách account dịch vụ được quản lý. Việc kiểm tra account và quyền cần được thực hiện bằng tài khoản có đủ quyền xem metadata và grants.

## 9. Quyền tạo view với DEFINER khác

Một DBA có thể cần triển khai view bằng migration account nhưng muốn definer là account dịch vụ ổn định. Khi dùng mệnh đề DEFINER để chỉ định account khác current user, MySQL yêu cầu quyền quản trị phù hợp.

Ví dụ về cú pháp:

```sql
CREATE DEFINER = 'report_view_definer'@'localhost'
SQL SECURITY DEFINER
VIEW reporting.v_orders_for_reports AS
SELECT
    order_id,
    status,
    total_amount
FROM sales.orders;
```

Không cấp quyền đặc biệt cho mọi developer chỉ để chạy câu lệnh này. Hãy để quy trình triển khai có kiểm soát thực hiện thao tác, hoặc kết nối bằng account definer để tạo view.

Tên và phạm vi các dynamic privilege liên quan đến DEFINER thay đổi giữa các bản MySQL. Trước khi cấp quyền trên production, kiểm tra tài liệu đúng phiên bản và giới hạn quyền cho migration account. Đặc biệt, việc cho phép đặt definer không tồn tại có thể tạo view bị orphan, gây lỗi lúc chạy hoặc tạo rủi ro khi account được tạo lại về sau.

## 10. Quyền trên view và quyền trên bảng nền

Bảng sau tóm tắt cách kiểm tra quyền:

| Tình huống | DEFINER | INVOKER |
|---|---|---|
| Người gọi có SELECT trên view | Bắt buộc | Bắt buộc |
| Người gọi có SELECT trên bảng nền | Không bắt buộc nếu definer đủ quyền | Cần quyền phù hợp trên đối tượng nền |
| Definer có SELECT trên bảng nền | Cần | Không dùng làm security context khi gọi |
| Definer bị thu hồi quyền nền | Có thể làm view lỗi | Không ảnh hưởng quyền của caller theo cơ chế INVOKER |
| Caller bị thu hồi quyền nền | View vẫn có thể chạy nếu caller còn SELECT trên view và definer đủ quyền | View có thể lỗi |
| Caller được GRANT trực tiếp trên bảng nền | Có thể đọc ngoài view nếu quyền đó cho phép | Có thể đọc theo phạm vi quyền được cấp |

Một điểm quan trọng: GRANT SELECT trên view không tự động cấp SELECT trên bảng nền. Cũng không nên cấp SELECT trên schema nguồn cho người dùng chỉ vì họ cần chạy một view DEFINER.

## 11. GRANT, REVOKE và nguyên tắc least privilege

Mô hình phân quyền nên có ba nhóm account rõ ràng:

1. Owner/definer account: được quyền đọc đúng cột hoặc đối tượng mà view cần.
2. Reader account/role: chỉ có SELECT trên view được phép dùng.
3. Deployment/DBA account: có quyền tạo hoặc thay đổi view theo quy trình triển khai.

Ví dụ cấp quyền tối thiểu:

```sql
GRANT SELECT (
    order_id,
    tenant_id,
    status,
    total_amount,
    created_at
)
ON sales.orders
TO 'view_owner'@'localhost';

GRANT SELECT
ON reporting.v_tenant_order_summary
TO 'report_reader'@'10.%';
```

Thu hồi quyền trên view:

```sql
REVOKE SELECT
ON reporting.v_tenant_order_summary
FROM 'report_reader'@'10.%';
```

Thu hồi quyền nền của definer:

```sql
REVOKE SELECT (
    order_id,
    tenant_id,
    status,
    total_amount,
    created_at
)
ON sales.orders
FROM 'view_owner'@'localhost';
```

Hãy kiểm tra tác động trước khi REVOKE. Nếu view vẫn đang được ứng dụng sử dụng, thu hồi quyền nền có thể khiến truy vấn runtime thất bại.

### 11.1. Dùng role cho nhóm người đọc

MySQL hỗ trợ role để gom quyền:

```sql
CREATE ROLE 'orders_report_reader';

GRANT SELECT
ON reporting.v_tenant_order_summary
TO 'orders_report_reader';

GRANT 'orders_report_reader'
TO 'report_reader'@'10.%';

SET DEFAULT ROLE 'orders_report_reader'
TO 'report_reader'@'10.%';
```

Role giúp cấp cùng một tập quyền cho nhiều account. Vẫn cần kiểm tra role mặc định hoặc role đang hoạt động theo session; không giả định role đã được cấp thì mọi session đều tự kích hoạt nếu cấu hình không như mong muốn.

Không đưa quyền SELECT trên bảng nền vào role reader nếu mục tiêu là chỉ cho phép đọc qua view DEFINER.

## 12. SQL SECURITY và view lồng nhau

Một view có thể tham chiếu view khác. Khi đó, security context được xác định theo chuỗi view và thuộc tính SQL SECURITY của từng view.

Ví dụ:

```sql
CREATE SQL SECURITY DEFINER
VIEW reporting.v_order_base AS
SELECT order_id, tenant_id, status
FROM sales.orders;

CREATE SQL SECURITY INVOKER
VIEW reporting.v_order_dashboard AS
SELECT order_id, tenant_id, status
FROM reporting.v_order_base;
```

Không nên suy luận rằng view ngoài dùng DEFINER thì mọi view bên trong đều tự động có cùng definer. Hãy kiểm tra định nghĩa từng view và thử bằng account thật của ứng dụng.

Khi thiết kế nhiều tầng view:

- Giữ cấu trúc đơn giản, dễ truy vết.
- Ghi rõ security mode của từng view.
- Kiểm tra definer của từng đối tượng.
- Kiểm tra quyền nền và quyền trên view theo từng lớp.
- Kiểm thử với account reader thực tế, không chỉ DBA.
- Tránh tạo chuỗi view quá sâu khiến khó xác định quyền và hiệu năng.

## 13. SQL SECURITY không thay thế CHECK OPTION

SQL SECURITY quyết định tài khoản dùng để kiểm tra quyền. WITH CHECK OPTION là cơ chế khác, áp dụng cho view có thể cập nhật để bảo đảm hàng INSERT/UPDATE qua view vẫn thỏa điều kiện của view.

Ví dụ:

```sql
CREATE SQL SECURITY DEFINER
VIEW reporting.v_pending_orders AS
SELECT order_id, status, total_amount
FROM sales.orders
WHERE status = 'PENDING'
WITH CASCADED CHECK OPTION;
```

CHECK OPTION không cấp quyền và không thay thế GRANT/REVOKE. Nó cũng không tự biến view thành cơ chế row-level security tổng quát. Nếu người dùng chỉ có SELECT trên view thì họ không thể UPDATE qua view; nếu cấp quyền ghi, phải đánh giá updatability và CHECK OPTION riêng.

Phân biệt:

| Cơ chế | Bảo vệ điều gì? |
|---|---|
| SQL SECURITY DEFINER/INVOKER | Security context dùng để kiểm tra quyền |
| GRANT/REVOKE | Account được phép truy cập đối tượng nào |
| WHERE trong view | Hàng nào xuất hiện trong kết quả view |
| WITH CHECK OPTION | Hàng ghi qua updatable view phải thỏa điều kiện view |
| PRIMARY/UNIQUE/CHECK/FK constraint | Các quy tắc toàn vẹn dữ liệu được database hỗ trợ |

## 14. Thực nghiệm: reader chỉ được truy cập qua DEFINER view

Thực hiện trong môi trường lab với quyền DBA phù hợp.

### Bước 1: Chuẩn bị account và quyền cho definer

```sql
CREATE USER 'view_owner'@'localhost'
    IDENTIFIED BY 'replace-with-a-managed-secret';

GRANT CREATE VIEW ON reporting.*
    TO 'view_owner'@'localhost';

GRANT SELECT (
    order_id,
    tenant_id,
    status,
    total_amount,
    created_at
)
ON sales.orders
TO 'view_owner'@'localhost';
```

### Bước 2: Kết nối bằng view_owner và tạo view

```sql
CREATE SQL SECURITY DEFINER
VIEW reporting.v_safe_orders AS
SELECT
    order_id,
    tenant_id,
    status,
    total_amount,
    created_at
FROM sales.orders
WHERE status <> 'CANCELLED';
```

Vì account đang kết nối là view_owner và không ghi DEFINER riêng, account này trở thành definer.

### Bước 3: Cấp quyền trên view cho reader

```sql
CREATE USER 'view_reader'@'10.%'
    IDENTIFIED BY 'replace-with-a-managed-secret';

GRANT SELECT
ON reporting.v_safe_orders
TO 'view_reader'@'10.%';
```

Không cấp SELECT trên sales.orders cho view_reader.

### Bước 4: Kiểm tra bằng view_reader

```sql
SELECT *
FROM reporting.v_safe_orders
LIMIT 20;
```

Truy vấn phải thành công nếu account, view và quyền definer đều đúng.

Thử truy cập bảng nguồn:

```sql
SELECT *
FROM sales.orders
LIMIT 20;
```

Truy vấn này phải bị từ chối vì view_reader không có quyền trên bảng nền.

### Bước 5: Thu hồi quyền của definer để thấy dependency

Trong lab, thử thu hồi một quyền cột mà view cần:

```sql
REVOKE SELECT (total_amount)
ON sales.orders
FROM 'view_owner'@'localhost';
```

Chạy lại truy vấn view bằng view_reader. Truy vấn có thể thất bại vì definer không còn quyền cần thiết. Khôi phục quyền sau thử nghiệm:

```sql
GRANT SELECT (total_amount)
ON sales.orders
TO 'view_owner'@'localhost';
```

Thí nghiệm này cho thấy view DEFINER phụ thuộc vào quyền runtime của account definer, không chỉ quyền của người tạo view tại thời điểm DDL.

## 15. Quy trình kiểm tra khi view báo lỗi quyền

Khi ứng dụng gặp lỗi SELECT trên view, kiểm tra theo thứ tự:

1. Xác định account thực sự kết nối: CURRENT_USER() và USER().
2. Kiểm tra account có SELECT trên view không bằng SHOW GRANTS.
3. Kiểm tra SHOW CREATE VIEW để biết DEFINER và SQL SECURITY.
4. Với DEFINER, kiểm tra account definer tồn tại và có SELECT trên mọi đối tượng/cột nền cần thiết.
5. Với INVOKER, kiểm tra quyền của caller trên các bảng/cột được tham chiếu.
6. Nếu view lồng nhau, kiểm tra SQL SECURITY và DEFINER của từng view bên trong.
7. Kiểm tra schema/table/column đã đổi tên hoặc bị xóa sau migration không.
8. Kiểm thử bằng account ứng dụng thực tế, không chỉ tài khoản DBA.
9. Sau khi thay quyền, chạy lại truy vấn và xác nhận đúng phạm vi dữ liệu.
10. Ghi nhận thay đổi GRANT/REVOKE trong quy trình quản lý quyền.

Lệnh hỗ trợ:

```sql
SELECT
    USER() AS connection_identity,
    CURRENT_USER() AS privilege_identity;

SHOW CREATE VIEW reporting.v_safe_orders;

SHOW GRANTS FOR 'view_reader'@'10.%';
SHOW GRANTS FOR 'view_owner'@'localhost';
```

Trong truy vấn thông thường, USER() phản ánh danh tính kết nối, còn CURRENT_USER() phản ánh account dùng cho privilege checking. Khi chạy qua view DEFINER, security context bên trong view có thể khiến CURRENT_USER() phản ánh definer. Dùng chúng như công cụ chẩn đoán, không dùng chuỗi trả về làm cơ chế phân quyền tùy biến thiếu kiểm soát.

## 16. Những lỗi bảo mật thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng root làm DEFINER | View chạy với quyền quá rộng | Tạo account definer riêng, least privilege |
| Nghĩ GRANT SELECT trên view tự cấp quyền bảng nền | Hiểu sai cơ chế runtime | Phân biệt DEFINER và INVOKER |
| Cấp SELECT trên schema nguồn cho reader | Người dùng có thể đọc ngoài view | Chỉ cấp SELECT trên view cần thiết |
| Tạo view DEFINER với WHERE không đủ chặt | View có thể lộ hàng ngoài phạm vi | Rà soát predicate và mô hình tenant |
| Dùng INVOKER để che bảng nền | Caller vẫn cần quyền trên bảng/cột nền | Dùng DEFINER view nếu cần quyền qua view |
| Xóa account definer mà không rà soát dependency | View có thể lỗi khi runtime | Kiểm tra INFORMATION_SCHEMA.VIEWS trước migration |
| Thu hồi quyền của definer mà không kiểm thử | View đang chạy có thể lỗi | Quản lý quyền definer như dependency |
| Cho developer quyền đặt bất kỳ DEFINER | Có thể tạo object với security context ngoài ý muốn | Hạn chế dynamic privilege và kiểm soát deployment |
| Nhầm CHECK OPTION với SQL SECURITY | View không bảo đảm quy tắc như mong đợi | Hiểu rõ quyền và kiểm tra hàng ghi là hai việc khác nhau |
| Chỉ thử bằng DBA | Không phát hiện thiếu quyền của account ứng dụng | Kiểm thử bằng account thật |

## 17. Checklist thiết kế view an toàn

Trước khi tạo view:

- Xác định view dùng để tái sử dụng SQL hay làm cổng truy cập dữ liệu.
- Chọn DEFINER nếu caller cần truy cập qua view mà không có quyền bảng nền.
- Chọn INVOKER nếu caller phải chịu kiểm tra quyền nền của chính họ.
- Chỉ định account definer ổn định, không dùng tài khoản cá nhân hoặc root.
- Cấp cho definer đúng quyền SELECT trên các cột/đối tượng cần thiết.
- Chỉ công bố cột cần dùng và viết điều kiện lọc đúng nghiệp vụ.
- Xem xét view lồng nhau và SQL SECURITY của từng tầng.
- Tách quyền tạo view khỏi quyền đọc view nếu mô hình vận hành yêu cầu.

Sau khi tạo:

- Kiểm tra SHOW CREATE VIEW.
- Kiểm tra INFORMATION_SCHEMA.VIEWS.
- GRANT SELECT trên đúng view cho đúng account/role.
- Xác nhận reader không có quyền trực tiếp ngoài ý muốn trên bảng nguồn.
- Thử truy vấn bằng account ứng dụng thật.
- Kiểm tra lỗi khi definer thiếu quyền trong môi trường lab.
- Theo dõi account definer trong quy trình migration/backup/restore.
- Rà soát định kỳ view có definer không tồn tại hoặc quyền quá rộng.

## 18. Ghi nhớ

- SQL SECURITY quyết định security context khi truy cập view.
- DEFINER dùng quyền của account định nghĩa view; INVOKER dùng quyền của account đang gọi.
- Nếu không chỉ định SQL SECURITY, MySQL mặc định dùng DEFINER.
- Người gọi DEFINER view cần SELECT trên view; không cần quyền trực tiếp trên bảng nền nếu definer có đủ quyền.
- Người gọi INVOKER view cần quyền trên view và quyền nền tương ứng với các đối tượng/cột được tham chiếu.
- Tạo view cần CREATE VIEW trên schema đích và SELECT trên các cột dùng trong định nghĩa.
- DEFINER nên là account dịch vụ ổn định với quyền tối thiểu; tránh dùng root hoặc account cá nhân.
- Quyền của definer phải tiếp tục tồn tại khi view chạy; thu hồi quyền nền có thể làm view lỗi.
- GRANT SELECT trên view không đồng nghĩa cấp quyền SELECT trên bảng nguồn.
- DEFINER view có thể giới hạn cột/hàng nhưng predicate phải phản ánh đúng phạm vi bảo mật; nó không tự tạo row-level security theo tenant.
- SHOW CREATE VIEW, SHOW GRANTS và INFORMATION_SCHEMA.VIEWS giúp kiểm tra security mode, definer và quyền.
- WITH CHECK OPTION kiểm tra hàng ghi qua updatable view; nó không thay thế SQL SECURITY hoặc GRANT/REVOKE.
- View lồng nhau cần kiểm tra security context của từng lớp.
- Không cấp quyền đặc biệt đặt DEFINER rộng rãi; yêu cầu quyền cụ thể phụ thuộc phiên bản MySQL.

SQL SECURITY DEFINER/INVOKER là ranh giới quan trọng giữa quyền của view và quyền của người gọi. Hãy chọn chế độ dựa trên mục tiêu truy cập, dùng definer có quyền tối thiểu, cấp SELECT đúng view và kiểm thử bằng account thực tế để chắc chắn người dùng chỉ nhìn thấy dữ liệu được phép.

## Tài liệu tham khảo

- MySQL 8.0 Reference Manual — CREATE VIEW Statement: https://dev.mysql.com/doc/refman/8.0/en/create-view.html
- MySQL 8.0 Reference Manual — Stored Object Access Control: https://dev.mysql.com/doc/refman/8.0/en/stored-objects-security.html
- MySQL 8.0 Reference Manual — View Restrictions: https://dev.mysql.com/doc/refman/8.0/en/view-restrictions.html
- MySQL 8.0 Reference Manual — GRANT Statement: https://dev.mysql.com/doc/refman/8.0/en/grant.html
- MySQL 8.0 Reference Manual — The VIEWS Table: https://dev.mysql.com/doc/refman/8.0/en/information-schema-views-table.html


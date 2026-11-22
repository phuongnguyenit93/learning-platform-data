# Tách role quản trị, migration, sao chép và ứng dụng trong PostgreSQL

Một lỗi cấu hình quyền rất phổ biến là **dùng cùng một PostgreSQL login cho quản trị, chạy migration, sao chép dữ liệu và phục vụ ứng dụng**. Ban đầu cách này có vẻ thuận tiện: không phải xử lý `permission denied` và chỉ cần một bộ credentials. Nhưng nếu HTTP API bị SQL injection hoặc mật khẩu bị rò rỉ, kẻ tấn công có thể có năng lực thay đổi schema, đọc dữ liệu tenant khác, xóa bảng hoặc tiếp cận luồng sao chép mà ứng dụng bình thường hoàn toàn không cần.

PostgreSQL cho phép phân tách nhiệm vụ bằng **roles**, **ownership**, **GRANT/REVOKE**, **role membership**, **Row-Level Security (RLS)** và các quyền đặc biệt. Một thiết kế thực tế thường có:

- **Admin/break-glass**: quản trị cấp cluster, chỉ dùng trong điều kiện kiểm soát.
- **Migration/deployment**: thay đổi schema, index, function và grants theo quy trình triển khai.
- **Object owner**: role `NOLOGIN` sở hữu các đối tượng của ứng dụng.
- **Application runtime**: chỉ đọc/ghi đúng những bảng, cột, view hoặc function mà service cần.
- **Physical replication**: kết nối replication protocol để chuyển WAL/base backup theo phạm vi thiết kế.
- **Logical replication**: kết nối publication/subscription và đọc những dữ liệu được công bố theo cấu hình.
- **Backup/monitoring**: quyền riêng theo công cụ và mục đích, không dùng chung tài khoản ứng dụng.

Hình dung kiến trúc:

```text
                        PostgreSQL cluster
                              |
       +----------------------+----------------------+
       |                      |                      |
  Cluster admin           Deploy pipeline       Replication/backup
  (break-glass)           (migration_login)     (repl_login)
       |                      |                      |
  Chỉ thao tác đặc biệt   SET ROLE app_owner    WAL / publication
                              |
                      app_owner (NOLOGIN)
                              |
                   tạo/sở hữu schema, table
                              |
                +-------------+---------------+
                |                             |
        Quyền runtime đọc             Quyền runtime ghi
        app_read (NOLOGIN)            app_write (NOLOGIN)
                |                             |
        catalog_api_login             inventory_worker_login
                |                             |
        SELECT view/cột                UPDATE cột, INSERT hẹp
```

Điểm cốt lõi: **người dùng được phép làm việc gì phải được quyết định bằng nhiệm vụ của họ**, không bằng việc họ “thuộc cùng một ứng dụng” hay “cùng một nhóm phát triển”.

Bài học này thuộc module **Database Engine Relational PostgreSQL**, chương **Bảo mật**, với chủ đề **“Tách role quản trị, migration, sao chép và ứng dụng”**. Ta sẽ xây dựng mô hình role, đi qua các SQL grants thực tế, hiểu ranh giới physical/logical replication, thực hành một lab có thể tái tạo và đưa ra cách kiểm thử quyền trước khi triển khai production.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao phải tách role theo nhiệm vụ và khái niệm **blast radius** khi một credential bị lộ.
2. Phân biệt `role`, `login role`, `group role`, `owner`, `membership` và các quyền trên đối tượng.
3. Thiết kế ma trận quyền cho admin, migration, owner, application read/write, physical replication, logical replication, backup và monitoring.
4. Hiểu các role attributes quan trọng: `SUPERUSER`, `CREATEROLE`, `CREATEDB`, `REPLICATION`, `BYPASSRLS`, `LOGIN` và `INHERIT`.
5. Biết tại sao **owner role thường nên là `NOLOGIN`** và không nên là tài khoản trong connection pool ứng dụng.
6. Dùng `SET ROLE` để chạy migration với owner identity theo quyền được cấp, đồng thời tránh cấp khả năng chuyển sang owner cho runtime.
7. Cấp `USAGE` trên schema và `SELECT`, `INSERT`, `UPDATE`, `DELETE` ở phạm vi bảng/cột.
8. Hiểu cách quyền thừa hưởng, `PUBLIC` và `GRANT OPTION` có thể mở rộng quyền ngoài dự kiến.
9. Dùng `ALTER DEFAULT PRIVILEGES` và phân biệt quyền của đối tượng hiện có với đối tượng sẽ được tạo.
10. Biết vì sao quyền trên sequence, function và view cần xét riêng với quyền trên table.
11. Hiểu physical replication dùng WAL và đòi đặc quyền/kênh xác thực khác kết nối SQL ứng dụng.
12. Phân biệt logical publication/subscription và yêu cầu bảo mật của initial table synchronization.
13. Hiểu replication slots có thể giữ WAL, tạo rủi ro dung lượng và availability.
14. Thiết kế `pg_hba.conf`, TLS và network allowlist riêng cho replication và application.
15. Phân biệt quyền `REPLICATION` với quyền tạo/cấu hình publication hoặc subscription; không mặc định chúng là một.
16. Hiểu tác động của RLS, table-owner bypass, `FORCE ROW LEVEL SECURITY` và `BYPASSRLS` đối với các role.
17. Nhận biết rủi ro khi runtime được `EXECUTE` một `SECURITY DEFINER` function có quyền ghi.
18. Dùng catalog và các hàm `has_*_privilege` để kiểm tra quyền hiệu lực.
19. Viết **positive tests** và **negative tests** cho quyền ứng dụng và migration.
20. Lập quy trình rotate credentials, thu hồi grants, tách môi trường, chuyển ownership và xử lý incident.
21. Hiểu rằng việc tách role phải đi cùng logging, audit, resource limits, quản trị secrets và backup/restore tests.

**Phạm vi:** PostgreSQL hiện đại. Một số quy tắc role membership thay đổi ở PostgreSQL 16+, còn quyền liên quan logical replication, subscription workers và cloud-managed PostgreSQL có khác biệt theo phiên bản/nhà cung cấp. Cần kiểm tra cluster thực tế trước khi áp dụng. Các lệnh có thể thay đổi quyền cluster chỉ chạy trên môi trường được ủy quyền.

---

## 2. Bài toán thực tế: một account làm tất cả

Giả sử hệ thống có tên `ShopCore` gồm các thành phần:

- API đọc sản phẩm.
- API cập nhật giỏ hàng/đơn hàng.
- Worker điều chỉnh tồn kho.
- Job báo cáo doanh thu.
- Pipeline migration bằng Flyway/Liquibase.
- Standby để phục vụ disaster recovery.
- Logical replica phục vụ analytics.
- Hệ thống monitoring và backup.

Một cấu hình sai:

```text
SHOP_DB_USER=postgres
SHOP_DB_PASSWORD=same-secret-everywhere
```

và tất cả các thành phần dùng chung.

### 2.1. Vì sao nguy hiểm?

Nếu API đọc sản phẩm bị khai thác, tài khoản kết nối có thể có nhiều quyền hơn chức năng đọc, gồm:

- UPDATE/DELETE dữ liệu không liên quan.
- ALTER/DROP bảng.
- Đọc bảng lương, thông tin khách hàng hoặc secrets.
- Thay grants/role nếu account có quyền quản trị.
- Bỏ qua RLS nếu là superuser.
- Phá cấu hình sao chép/backup hoặc làm gián đoạn dịch vụ.

### 2.2. Blast radius

**Blast radius** là phạm vi thiệt hại có thể xảy ra khi một thành phần bị chiếm quyền.

So sánh:

| Credential bị lộ | Nếu quyền tối thiểu | Nếu dùng superuser chung |
| --- | --- | --- |
| Catalog API | Có thể đọc một số view/cột catalog | Có thể truy cập/thay đổi nhiều đối tượng |
| Inventory worker | Có thể cập nhật cột stock theo phạm vi được cấp | Có thể DROP/ALTER hoặc đọc dữ liệu khác |
| Migration pipeline | Có thể thay schema ứng dụng theo policy | Có thể thay phần lớn cluster |
| Replication service | Có thể đọc/stream dữ liệu replication theo protocol | Có thêm quyền SQL quản trị không cần thiết |
| BI dashboard | Chỉ đọc các views báo cáo | Đọc trực tiếp PII/bảng nội bộ |

### 2.3. Một credential không nên phục vụ hai trust boundaries

Internet-facing API và migration pipeline có threat model khác nhau. Dù chạy cùng repository, chúng không nên chia sẻ một login có DDL privileges.

### 2.4. Tách role không giải quyết tất cả

Một reader có SELECT quá rộng vẫn gây rò dữ liệu. Một replication login dù không là superuser vẫn có thể tiếp cận dữ liệu rất nhạy cảm. Cần thiết kế từng role theo **dữ liệu và thao tác được phép**.

---

## 3. Role trong PostgreSQL: ba lớp cần phân biệt

PostgreSQL dùng khái niệm thống nhất **role**, nhưng mọi role không giống nhau.

### 3.1. Role attributes

Ví dụ:

```sql
CREATE ROLE sample_login LOGIN;
CREATE ROLE sample_group NOLOGIN;
```

`LOGIN` cho phép role xác thực trực tiếp nếu có phương thức xác thực phù hợp. `NOLOGIN` không thể trực tiếp đăng nhập, nhưng vẫn có thể nhận grants hoặc sở hữu objects.

Các attributes khác gồm `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `REPLICATION`, `BYPASSRLS`.

### 3.2. Object privileges

Ví dụ:

```sql
GRANT SELECT ON TABLE app.orders TO app_reader;
GRANT UPDATE (stock) ON TABLE app.inventory TO inventory_writer;
```

Đây là các quyền trên đối tượng cụ thể; chúng khác hoàn toàn với thuộc tính REPLICATION hay SUPERUSER.

### 3.3. Role membership

```sql
GRANT app_read TO catalog_api_login;
```

Một role có thể dùng quyền của nhóm theo quy tắc membership/inheritance.

### 3.4. Ownership

Đối tượng có owner:

```sql
CREATE TABLE app.orders (...);
```

Role tạo bảng thông thường là owner ban đầu. Owner có năng lực thay đổi định nghĩa, drop và quản lý grants theo quy tắc PostgreSQL; đó không chỉ là “role được cấp SELECT/UPDATE”.

### 3.5. Thuộc tính quản trị không kế thừa như GRANT SELECT

Các thuộc tính đặc biệt như `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `LOGIN`, `REPLICATION` và `BYPASSRLS` **không được kế thừa như các object privileges thông thường** chỉ vì membership. Việc `SET ROLE` và các giới hạn quản trị có quy tắc riêng. Không dựa vào membership để suy ra một login đã trở thành replication account hợp lệ.

---

## 4. Ma trận quyền theo nhiệm vụ

Đây là một **mẫu khởi điểm**, không phải grants bắt buộc cho mọi hệ thống:

| Role | LOGIN | DDL / owner | CRUD | Replication | Đặc quyền cao |
| --- | --- | --- | --- | --- | --- |
| `cluster_admin` / break-glass | Có, quản lý chặt | Rất rộng khi cần | Rất rộng | Có thể quản trị | Superuser thật nếu tự quản lý |
| `migration_login` | Có | Chuyển sang `app_owner` khi được phép | Chỉ cần để migrate/backfill | Không | Không superuser mặc định |
| `app_owner` | **Không** | Sở hữu objects ứng dụng | Theo owner semantics | Không | Không superuser |
| `catalog_api_login` | Có | Không | SELECT view/cột catalog | Không | Không |
| `order_api_login` | Có | Không | INSERT/UPDATE/SELECT đúng objects | Không | Không |
| `inventory_worker_login` | Có | Không | UPDATE stock và ghi movement hẹp | Không | Không |
| `physical_repl_login` | Có | Không | Không dùng như API SQL | Có | `REPLICATION`, không SUPERUSER |
| `logical_repl_login` | Có | Không | SELECT tables published nếu cần | Có | Theo quyền logical replication cần thiết |
| `backup_login` | Tùy công cụ | Không | Đọc dữ liệu cần backup | Tùy physical backup | Không dùng chung runtime |
| `monitor_login` | Có | Không | Metrics/catal​og thích hợp | Không mặc định | Predefined monitoring role khi cần |

### 4.1. Quản trị và migration không cùng mục đích

Một pipeline cần `ALTER TABLE app.orders` không đồng nghĩa được cấp `ALTER ROLE postgres SUPERUSER`.

### 4.2. Replication không cùng mục đích với API

Physical standby cần nhận WAL, không cần chạy `UPDATE app.orders` như người dùng nghiệp vụ. Ngược lại, một API chỉ đọc catalog không nên có thuộc tính REPLICATION.

### 4.3. Read và write có thể tách

Nếu read-only service bị lộ, kẻ tấn công không nên có INSERT/UPDATE/DELETE trên dữ liệu gốc. Với write service, có thể cấp theo cột hoặc qua function hẹp.

### 4.4. Owner không nên dùng làm service login

Nếu runtime là owner, nó có thể thực hiện những hành động DDL/GRANT không cần thiết và thường bypass RLS trên bảng sở hữu.

### 4.5. Đừng gộp mọi tài khoản vào một nhóm có quyền rộng

Một group tên `all_shop_services` được GRANT ALL ON ALL TABLES dễ vô hiệu hóa tách vai trò dù login names khác nhau.

---

## 5. Role quản trị cluster: đặc quyền cao có chủ đích

Trong cluster PostgreSQL tự quản lý, một superuser thật có phạm vi quyền rất lớn. Nó có thể vượt qua kiểm tra quyền thông thường, RLS và nhiều hạn chế quản trị.

### 5.1. Công việc phù hợp

- Khởi tạo cluster hoặc một số thao tác bootstrap.
- Quản trị cấu hình nhạy cảm.
- Can thiệp incident cấp cluster.
- Provision những thuộc tính role hoặc extension đặc biệt khi cần.
- Phục hồi hệ thống trong các tình huống được ủy quyền.

### 5.2. Công việc không cần superuser

- SELECT catalog cho API.
- INSERT đơn hàng.
- UPDATE stock.
- Chạy migration thông thường của schema do ứng dụng sở hữu.
- Đọc metrics cơ bản khi có predefined monitoring roles phù hợp.

### 5.3. Không dùng account admin cho connection pool

App pool có số lượng kết nối lớn, được mở thường xuyên và nằm gần input người dùng. Đây là nơi không nên đặt credentials mạnh nhất.

### 5.4. Break-glass account

Một account dành cho trường hợp khẩn cấp nên có:

- Quy trình phê duyệt và audit.
- Credential được cất trong secret vault.
- Cơ chế kiểm soát truy cập hạ tầng, MFA tại lớp quản trị nếu có.
- Giới hạn network.
- Rotation sau khi sử dụng theo chính sách.
- Không nằm trong `application.properties`, container environment của web app hoặc CI logs.

### 5.5. Managed PostgreSQL không luôn cung cấp superuser thật

Trong cloud-managed PostgreSQL, tài khoản tên `postgres` hoặc `admin` có thể chỉ thuộc nhóm quyền quản trị do nhà cung cấp kiểm soát, chứ không có `rolsuper=true`. Không đoán quyền từ tên tài khoản.

---

## 6. Những thuộc tính role cần đánh giá

| Thuộc tính | Vai trò | Có nên cấp cho runtime thường? |
| --- | --- | --- |
| `LOGIN` | Xác thực trực tiếp | Có cho login runtime |
| `NOLOGIN` | Không đăng nhập trực tiếp | Phù hợp nhóm quyền và owner |
| `SUPERUSER` | Bỏ qua nhiều kiểm tra quyền | **Không** |
| `CREATEROLE` | Quản trị roles theo giới hạn phiên bản | **Không** |
| `CREATEDB` | Tạo databases | **Không** |
| `REPLICATION` | Kết nối/khả năng replication tương ứng | **Không** cho API |
| `BYPASSRLS` | Bỏ qua row-level security | **Không** cho API đa tenant |
| `INHERIT/NOINHERIT` | Điều khiển mặc định quyền kế thừa | Tùy mô hình membership |
| `CONNECTION LIMIT` | Giới hạn kết nối theo role | Cân nhắc vận hành |

### 6.1. CREATEROLE có thể mở rộng phạm vi quản trị

Không cấp `CREATEROLE` cho service chỉ vì migration cần tạo bảng. Quản lý role và quản lý bảng là hai nhiệm vụ khác nhau.

### 6.2. BYPASSRLS đặc biệt nguy hiểm trong multi-tenant

Nếu ứng dụng phụ thuộc RLS để giới hạn dữ liệu tenant, runtime login có BYPASSRLS có thể bỏ qua chính sách này theo cơ chế PostgreSQL.

### 6.3. REPLICATION có phạm vi nhạy cảm

Physical replication không phải “SELECT chỉ những cột được cấp”. WAL/base backup có thể mang dữ liệu trên phạm vi lớn của cluster và tạo rủi ro confidentiality/availability riêng.

### 6.4. Role name không tạo permission

Đặt tên tài khoản `readonly` không chứng minh nó read-only. Cần kiểm tra thuộc tính, membership, GRANT, RLS, functions và quyền đặc biệt.

---

## 7. Owner NOLOGIN: tách ownership khỏi credentials

Một thiết kế thông dụng:

```sql
CREATE ROLE shop_owner NOLOGIN;
```

Role này sở hữu schema, table, view và function ứng dụng, nhưng không có mật khẩu login để bị lộ từ service bình thường.

### 7.1. Lợi ích

- DDL có owner nhất quán sau nhiều lần deploy.
- Runtime không có quyền owner chỉ vì cần CRUD.
- Default privileges có thể gắn với đúng creator role.
- Dễ chuyển pipeline migration mà không đổi owner từng bảng.
- Giảm số credentials có thể sửa schema.

### 7.2. NOLOGIN không tự bảo vệ khỏi mọi đường chiếm quyền

Nếu runtime login được cấp membership cho phép `SET ROLE shop_owner`, runtime vẫn có thể sử dụng owner role. Cần **không cấp đường chuyển role đó cho runtime**.

### 7.3. Schema owner và table owner có thể khác

Role sở hữu schema không mặc định có quyền ALTER/DROP mọi bảng do role khác sở hữu trong schema. Muốn nhất quán, cần kiểm soát role thực sự tạo objects.

### 7.4. Owner không cần superuser

Phần lớn đối tượng ứng dụng có thể được tạo/sửa bằng role sở hữu schema và objects phù hợp. Nếu một extension/DDL đặc biệt cần đặc quyền cao, xử lý qua bước quản trị riêng.

---

## 8. Migration login: có quyền DDL nhưng không tự là admin cluster

Một role migration thường cần:

- Có thể đăng nhập qua cơ chế secrets riêng của pipeline.
- Có khả năng hoạt động dưới owner role theo membership được cấp.
- Tạo/đổi tables, indexes, views, functions và grants thuộc ứng dụng.
- Thực hiện backfill DML khi script được review.
- Không có REPLICATION/BYPASSRLS/SUPERUSER nếu không bắt buộc.

### 8.1. Ví dụ cấu trúc

```sql
CREATE ROLE shop_migration_login LOGIN NOINHERIT;
GRANT shop_owner TO shop_migration_login;
```

Đây là mô hình minh họa; cần thiết lập credential ngoài script và kiểm tra membership options theo phiên bản.

### 8.2. Tại sao NOINHERIT?

Với cấu hình membership phù hợp, migration login không tự dùng các quyền được cấp cho owner role khi chưa chủ động chuyển role. Mục tiêu là yêu cầu bước DDL được viết rõ:

```sql
SET ROLE shop_owner;

CREATE TABLE shop_internal.example (
    id BIGINT PRIMARY KEY
);

RESET ROLE;
```

### 8.3. PostgreSQL 16+ có membership options riêng

Trong PostgreSQL 16+, các quan hệ role membership có tùy chọn **ADMIN**, **INHERIT**, **SET**. Khả năng dùng quyền thừa hưởng ngay và khả năng `SET ROLE` là hai khái niệm cần kiểm tra.

Ví dụ kiểu cấu hình phù hợp PostgreSQL 16+ có thể là:

```sql
GRANT shop_owner TO shop_migration_login
WITH INHERIT FALSE, SET TRUE;
```

Không sao chép nguyên câu này sang phiên bản cũ nếu không hỗ trợ; cần đọc tài liệu phiên bản và kiểm tra các grants hiện có.

### 8.4. Creator role quyết định default privileges

Nếu deployment tạo table bằng `shop_migration_login` thay vì chuyển sang `shop_owner`, table có thể thuộc migration login và áp dụng default ACL của migration login. Kết quả: những table cũ/mới có owners khác nhau, app có thể bị thiếu grants.

### 8.5. Migration cũng có thể chạy DML

Backfill, tạo index, thay constraint hoặc update dữ liệu nền có thể cần quyền ghi. Quyền đó nên có phạm vi đúng objects và được cấp qua owner role trong quá trình deploy, không chuyển sang runtime credential.

### 8.6. Pipeline secrets nên tách khỏi application secrets

Không đưa `shop_migration_login` credentials vào container HTTP API hoặc public app configuration. Không dùng app credential để chạy Flyway/Liquibase vì “tránh tạo hai tài khoản”.

---

## 9. Chạy migration dưới owner identity

Một migration có thể được tổ chức:

```text
CI/CD:
  authenticate as shop_migration_login
  BEGIN
    SET LOCAL role?  (không dùng cú pháp giả định)
    SET ROLE shop_owner
    CREATE/ALTER objects
    GRANT runtime permissions
  COMMIT
  RESET ROLE / close connection
```

**Cú pháp cần dùng:** PostgreSQL hỗ trợ `SET ROLE role_name`. Trong một transaction có thể dùng `SET LOCAL ROLE role_name` theo cú pháp GUC của PostgreSQL ở những ngữ cảnh phù hợp, nhưng để tránh phụ thuộc cách tool/driver xử lý, bài học dùng ví dụ trực tiếp `SET ROLE` và quản lý transaction/lifecycle rõ ràng.

### 9.1. Một mẫu dễ đọc

```sql
BEGIN;

SET ROLE shop_owner;

-- CREATE/ALTER đối tượng của ứng dụng.
-- ALTER TABLE shop_internal.orders ADD COLUMN ...;

COMMIT;

RESET ROLE;
```

Cần bảo đảm session được phép `SET ROLE shop_owner`. Với DDL không thể chạy trong transaction ở một số trường hợp (ví dụ `CREATE INDEX CONCURRENTLY`), migration tool phải chia bước phù hợp.

### 9.2. Tránh mất quyền owner vì SET ROLE sai

Nếu migration login không có quyền chuyển sang owner, câu `SET ROLE` sẽ bị từ chối. Không thêm SUPERUSER để sửa nhanh; hãy sửa membership với nguyên tắc quyền tối thiểu.

### 9.3. Vì sao phải RESET ROLE hoặc đóng connection?

Một connection được pool/tool tái sử dụng mà vẫn mang owner identity có thể chạy các lệnh sau với quyền vượt dự kiến. Nên để migration dùng connection riêng, reset role hoặc đóng kết nối sau khi hoàn thành.

### 9.4. Ai quản lý thay đổi role membership?

Các GRANT role-to-role thuộc quy trình provisioning/admin, không phải mọi migration script có thể tự cấp quyền admin cho chính mình.

---

## 10. Role ứng dụng: phân biệt đọc, ghi và tính năng

Không nên tạo một role tên `shop_app` rồi `GRANT ALL ON ALL TABLES`.

Thay vào đó có thể có:

```text
shop_catalog_read (NOLOGIN)
         ^
         |
catalog_api_login (LOGIN)

shop_order_write (NOLOGIN)
         ^
         |
order_api_login (LOGIN)

shop_inventory_write (NOLOGIN)
         ^
         |
inventory_worker_login (LOGIN)
```

### 10.1. Đọc không cần DDL

Một catalog API thường chỉ cần:

- CONNECT database.
- USAGE đúng schema.
- SELECT các views/cột công khai.

Không cần CREATE TABLE, ALTER TABLE, DROP TABLE hoặc GRANT quyền cho role khác.

### 10.2. Ghi đơn hàng không cần sửa tất cả bảng

Order API có thể cần INSERT orders/order_items, SELECT thông tin tham chiếu và UPDATE một vài cột trạng thái theo nghiệp vụ. Nó không cần DELETE customer hoặc UPDATE unit_cost.

### 10.3. Worker tồn kho không cần đọc PII

Một worker cập nhật stock có thể chỉ cần SKU, stock, transaction ID và movement tables. Không cấp SELECT customer_email chỉ vì hai bảng nằm cùng schema.

### 10.4. Tránh cấp role writer cho reader

Một catalog API chỉ đọc mà được membership vào `shop_order_write` sẽ có đường quyền ghi dù ACL trên view catalog đã được thiết kế hẹp.

### 10.5. Quyền ứng dụng còn cần resource controls

Một role chỉ SELECT vẫn có thể chạy query rất nặng, gây tải CPU/I/O, locks hoặc đọc toàn bộ dữ liệu được cấp. Thiết kế statement timeouts, quotas và monitoring để bảo vệ availability.

---

## 11. Physical replication: vì sao là một trust boundary riêng?

PostgreSQL **physical streaming replication** sao chép WAL để standby phát lại thay đổi ở cấp storage/database cluster. Kết quả là một standby gần tương đương primary theo cách phục hồi WAL.

```text
Primary (WAL producer)
      |
      | WAL sender + replication protocol
      v
Network channel (TLS / allowlist)
      |
      v
Physical standby (WAL receiver/replay)
```

### 11.1. Role physical replication cần gì?

Thông thường, trên primary, một login có thuộc tính `REPLICATION` (hoặc superuser) được phép kết nối qua replication protocol theo cấu hình authentication/pg_hba và các điều kiện hệ thống.

Ví dụ **provisioning có đặc quyền**, không chạy trên cluster đang sử dụng nếu chưa có phê duyệt:

```sql
-- Minh họa, chỉ tạo qua quy trình DBA được ủy quyền:
-- CREATE ROLE physical_repl_login LOGIN REPLICATION;
```

Credential, quyền kết nối và certificate phải được quản lý ngoài source code.

### 11.2. REPLICATION là role attribute, không phải GRANT SELECT

Không có nghĩa chỉ cần:

```sql
GRANT SELECT ON some_table TO physical_repl_login;
```

là role đã được phép stream WAL. Ngược lại, có REPLICATION không có nghĩa nên dùng role ấy để chạy SQL ứng dụng thông thường.

### 11.3. Vì sao rất nhạy cảm?

Physical replication/WAL có thể chứa dữ liệu của nhiều database trong cluster, thông tin biến đổi và dữ liệu nhạy cảm. Phạm vi không được giới hạn bởi một view công khai hay column-level SELECT của API.

### 11.4. Không dùng chung app credentials

Nếu credential `physical_repl_login` bị lộ, cần xử lý như một security incident về đường truy cập replication, không chỉ như một API user bị lộ quyền đọc.

### 11.5. Một role không cần superuser thật nếu REPLICATION đủ

Theo tính năng hỗ trợ, dùng một role `LOGIN REPLICATION` chuyên biệt giúp tránh cấp quyền admin toàn cluster cho standby agent. Tuy nhiên, đặc quyền replication vẫn phải được xem là **đặc quyền cao**.

---

## 12. Cấu hình kết nối replication: pg_hba.conf, TLS và network

PostgreSQL kiểm soát kết nối bằng nhiều lớp:

- Network/firewall/security groups.
- `pg_hba.conf` authentication rules.
- TLS và xác thực endpoint.
- Role attributes/credentials.
- WAL sender/replication configuration.
- Quyền thao tác với replication slots/protocol.

### 12.1. Ví dụ pg_hba cho physical replication

Dòng minh họa trong `pg_hba.conf` trên primary:

```conf
# TYPE     DATABASE       USER                 ADDRESS          METHOD
hostssl    replication    physical_repl_login  10.20.30.40/32   scram-sha-256
```

Trong loại kết nối physical replication, trường DATABASE thường dùng giá trị đặc biệt `replication`.

### 12.2. Không cấp subnet quá rộng

Ví dụ cho phép từ `0.0.0.0/0` với credential nhạy cảm là một bề mặt tấn công không cần thiết. Nên giới hạn đến địa chỉ standby/nút được quản lý và xác thực server đúng cách.

### 12.3. TLS phải xác thực đúng endpoint

`hostssl` yêu cầu kết nối SSL/TLS theo cấu hình HBA, nhưng client vẫn cần cấu hình mode kiểm tra chứng chỉ/hostname phù hợp để tránh chấp nhận server giả mạo. Không xem “đã bật SSL” tự chứng minh mọi khía cạnh xác thực.

### 12.4. Cấu hình server liên quan

Physical replication thường cần các tham số phù hợp như:

```sql
SHOW wal_level;
SHOW max_wal_senders;
SHOW max_replication_slots;
```

Giá trị cần lựa chọn theo kiến trúc và workload. Không tự tăng các tham số lên mức lớn rồi cho rằng availability tốt hơn.

### 12.5. pg_hba không thay role security

Ngay cả khi một rule giới hạn IP, credential vẫn phải được bảo vệ. Nếu địa chỉ standby bị chiếm quyền, attacker có thể nằm đúng allowlist.

---

## 13. Physical standby, base backup và đặc quyền

Để khởi tạo standby, hệ thống có thể dùng các công cụ PostgreSQL như `pg_basebackup`, sau đó cấu hình kết nối streaming.

### 13.1. Physical backup không giống logical dump

Một physical base backup chứa dữ liệu vật lý ở phạm vi cluster theo cơ chế công cụ, không phải SELECT một vài bảng.

### 13.2. Role backup có thể dùng replication protocol

Tùy chiến lược, backup login có thể cần thuộc tính `REPLICATION` và các khả năng liên quan, nhưng không nhất thiết cần SUPERUSER. Phân quyền chính xác phải dựa trên công cụ, phiên bản và thao tác cần làm.

### 13.3. Không dùng standby credential để tạo table ứng dụng

Không cấp quyền DDL/CRUD chỉ vì replication agent cần kết nối. Tách kênh quản trị database và kênh replication.

### 13.4. Bảo vệ backup files và WAL archive

Bản backup và archive WAL có thể chứa dữ liệu nhạy cảm dù chúng nằm ngoài PostgreSQL. Phải có encryption, access controls, retention và audit tại object storage/file system.

### 13.5. Test restore mới chứng minh khả năng khôi phục

Một backup hoàn tất không bảo đảm restore được đúng thời điểm, đúng roles hoặc đúng grants. Cần diễn tập phục hồi và kiểm tra ownership, permissions, RLS và credentials của môi trường đích.

---

## 14. Physical replication không thay bảo mật primary

Standby là bản sao dữ liệu vật lý; nó không tự ẩn bảng nhạy cảm khỏi role quản trị standby.

### 14.1. RLS không bảo vệ luồng WAL vật lý như một SELECT

RLS giới hạn các câu query SQL phù hợp khi đọc bảng; physical WAL replication hoạt động ở một lớp khác. Không dùng RLS để làm căn cứ rằng một role physical replication chỉ nhận hàng của một tenant.

### 14.2. Replication lag là availability/freshness concern

Standby có thể trễ primary. Một ứng dụng đọc từ replica cần hợp đồng nhất quán phù hợp (đặc biệt sau khi người dùng vừa ghi đơn hàng).

### 14.3. Synchronous replication có yêu cầu khác

Trong một số cấu hình synchronous replication, transaction commit có thể phụ thuộc xác nhận từ standby theo mức cấu hình. Lỗi network/standby có thể ảnh hưởng write availability. Phân quyền replication và cấu hình HA phải được thiết kế chung.

### 14.4. Replication account không phải audit principal của người dùng

Dữ liệu ghi qua primary được sao chép; standby agent không đại diện user đã thay đổi một hàng. Cần audit user/business operation riêng trên primary hoặc pipeline phù hợp.

---

## 15. Logical replication: phạm vi dữ liệu và quyền khác physical

**Logical replication** truyền các thay đổi ở mức quan hệ/hàng theo publication/subscription. Nó thường được dùng để chuyển một tập bảng từ publisher sang subscriber.

```text
Publisher database
   |
   +-- publication: các bảng và cấu hình công bố
   |
   +-- logical decoding / replication protocol
   |
   v
Subscriber database
   |
   +-- subscription
   +-- worker áp dụng thay đổi
   +-- bảng đích đã được chuẩn bị
```

### 15.1. Logical không phải mặc định “chỉ đọc một vài cột an toàn”

Logical replication có thể công bố nhiều bảng, bao gồm PII. Một publication được tạo quá rộng có thể làm dữ liệu được sao chép sang hệ thống đích không được bảo vệ tương xứng.

### 15.2. Đối tượng publication/subscription được quản lý riêng

Quyền tạo/sửa publication và subscription, quyền sở hữu bảng được công bố, quyền role replication và quyền trên bảng đích đều cần xem theo phiên bản PostgreSQL.

Không suy luận “role có REPLICATION là có thể tự CREATE PUBLICATION trên mọi bảng” hoặc “được GRANT SELECT một bảng là có thể CREATE SUBSCRIPTION tùy ý”.

### 15.3. Khi nào nên dùng logical replication?

- Chuyển một subset bảng cho analytics.
- Đồng bộ dữ liệu giữa những PostgreSQL databases theo yêu cầu.
- Một số chiến lược nâng cấp/chuyển hệ thống.
- Tách workload phân tích khỏi OLTP.

### 15.4. Khi nào không phù hợp?

Nếu mục tiêu là bản sao vật lý toàn cluster phục vụ failover/point-in-time recovery theo mô hình physical standby, logical replication không phải thay thế trực tiếp.

### 15.5. Bảo mật cả hai đầu

Publisher cần bảo vệ quyền phát dữ liệu; subscriber cần bảo vệ dữ liệu nhận được, connection strings, schemas và apply workers.

---

## 16. Role logical replication ở publisher

Một logical subscriber thường kết nối tới publisher thông qua một login có khả năng replication phù hợp.

Ví dụ **không chạy tự động**:

```sql
-- DBA provisioning:
-- CREATE ROLE logical_repl_login LOGIN REPLICATION;
--
-- Cấp các quyền đọc bảng cần thiết cho bước initial sync
-- theo tài liệu phiên bản/công cụ đang dùng:
-- GRANT USAGE ON SCHEMA source_schema TO logical_repl_login;
-- GRANT SELECT ON TABLE source_schema.orders TO logical_repl_login;
```

### 16.1. Initial table synchronization

Khi subscription cần copy dữ liệu ban đầu, cơ chế đồng bộ có thể yêu cầu quyền đọc các bảng được publication công bố, bên cạnh đặc quyền/kết nối replication. Vì vậy chỉ cấp REPLICATION rồi bỏ qua những quyền SELECT cần thiết có thể khiến initial copy thất bại.

### 16.2. Phạm vi SELECT phải theo bảng được phép công bố

Không cấp `SELECT ON ALL TABLES IN SCHEMA internal` chỉ vì một publication hiện cần hai bảng. Nếu schema có PII hoặc secrets, quyền read rộng có thể mở thêm rủi ro ngoài scope.

### 16.3. RLS và logical replication

Logical replication có quy tắc riêng về row security, role thực thi và cách publisher đánh giá dữ liệu được công bố. Một số thiết lập/phiên bản có thể từ chối replication khi role chịu RLS để tránh sai lệch bảo mật; phải kiểm tra tài liệu tương ứng và thực nghiệm với role thật.

**Không** cấp `BYPASSRLS` bừa bãi chỉ để sửa một lỗi subscription; việc đó có thể làm mất hàng rào dữ liệu theo tenant.

### 16.4. Không dùng logical_repl_login như tài khoản ứng dụng

Đây là service identity của luồng sao chép, không phải identity của người dùng cuối.

---

## 17. Publication: kiểm soát những bảng được công bố

Ví dụ khái niệm trên publisher:

```sql
CREATE PUBLICATION shop_analytics_pub
FOR TABLE
    analytics_source.orders,
    analytics_source.order_items;
```

Lệnh này giả định schema và tables đã tồn tại và role thực thi có quyền tạo publication cho các đối tượng đó.

### 17.1. Phân biệt publication với GRANT SELECT

Publication quyết định những thay đổi logic nào sẽ được đưa vào stream; SELECT privilege dùng trong truy cập bảng và các giai đoạn đồng bộ cần thiết. Hai cơ chế không đồng nhất.

### 17.2. Chọn từng bảng thay vì “all tables” khi scope hẹp

`FOR ALL TABLES` hoặc publication có phạm vi tự mở rộng có thể công bố thêm đối tượng mới ngoài ý định khi hệ thống phát triển. Với dữ liệu nhạy cảm, chọn bảng rõ ràng và review mỗi migration.

### 17.3. Column lists và row filters

Các phiên bản PostgreSQL mới hỗ trợ một số khả năng lọc theo hàng/cột khi công bố. Tuy nhiên, chúng có những giới hạn về loại thao tác, replica identity, phiên bản và semantics. Không xem row filter publication như hệ thống authorization tương đương RLS cho mọi người gọi SQL.

### 17.4. DDL không được sao chép tự động như dữ liệu

Logical replication thông thường không tự triển khai mọi thay đổi schema sang subscriber. Migration pipeline cho subscriber cần phối hợp khi publisher thêm/đổi cột, kiểu dữ liệu hoặc tables.

### 17.5. Replica identity

Các thao tác UPDATE/DELETE có thể cần replica identity thích hợp để xác định hàng ở subscriber. Thay đổi cấu hình này có thể ảnh hưởng cả hiệu năng, WAL và dữ liệu được gửi.

---

## 18. Subscription: quyền ở phía subscriber

Trên subscriber, một subscription được tạo để kết nối publisher:

```sql
CREATE SUBSCRIPTION shop_analytics_sub
CONNECTION 'host=publisher.internal port=5432 dbname=shop user=logical_repl_login ...'
PUBLICATION shop_analytics_pub;
```

Đây là **mẫu cú pháp**, không phải lệnh chạy ngay: phải thay đường kết nối/credentials bằng cơ chế quản lý secrets phù hợp, kiểm tra privileges, TLS và bảo đảm bảng đích đã sẵn sàng. Không ghi mật khẩu thật vào file migration, lịch sử terminal hoặc mã nguồn.

### 18.1. Tạo subscription có yêu cầu quyền khác CREATE TABLE

Tùy phiên bản, việc tạo/sở hữu subscription và khả năng chạy apply worker có yêu cầu đặc quyền đặc biệt. PostgreSQL các bản mới có một số predefined roles/cơ chế liên quan subscription; không suy luận từ một phiên bản cũ hoặc managed service rằng quyền giống hệt.

### 18.2. Apply workers và quyền ghi bảng đích

Một subscription cần apply dữ liệu vào tables phía subscriber. Quyền của subscription owner, table owner và apply worker có tương tác với mô hình bảo mật; ở các phiên bản mới cơ chế kiểm tra quyền có thể thay đổi.

### 18.3. Subscription owner không nên là login web API

Web API không cần khả năng chỉnh connection string publisher, drop subscription, làm thay đổi luồng đồng bộ hoặc chiếm quyền apply.

### 18.4. Bảo vệ connection string

Thông tin kết nối dùng cho subscription có thể chứa credentials nhạy cảm và được lưu trong metadata của PostgreSQL. Cần giới hạn ai có quyền đọc/đổi subscription configuration theo tài liệu phiên bản.

### 18.5. Kiểm tra server-side RLS/triggers ở subscriber

Logical apply có hành vi đặc thù với replication origin, triggers và table security. Nếu application phía subscriber dựa vào triggers/RLS để bảo vệ dữ liệu, phải kiểm thử riêng cơ chế apply; không giả định nó đi qua chính xác cùng code path với một lệnh INSERT từ client.

---

## 19. Logical replication không phải cơ chế phân quyền tenant hoàn chỉnh

Giả sử analytics chỉ được dùng dữ liệu tenant 10.

### 19.1. Rủi ro từ publication quá rộng

Nếu publication gửi toàn bộ `orders` thuộc mọi tenant đến subscriber, việc BI user chỉ được SELECT tenant 10 trên subscriber **không có nghĩa dữ liệu tenant khác chưa từng được sao chép đến hệ thống đó**.

### 19.2. Quyền truy cập vào dữ liệu sao chép

Phải bảo vệ subscriber theo phân loại dữ liệu thực tế: disk encryption, backup, monitoring accounts, BI privileges, network và RLS khi phù hợp.

### 19.3. Row filters có giới hạn

Ngay cả khi publication lọc một tập hàng, cần kiểm tra DML semantics, initial copy, schema changes và quyền để tránh việc dựa vào filter như một boundary bảo mật duy nhất.

### 19.4. Phân biệt “copy dữ liệu” và “được phép dùng dữ liệu”

Replication chuyển dữ liệu vì mục đích kỹ thuật. Quyền của analyst đọc dữ liệu nhận được cần được cấp riêng và không nên lấy từ chính replication account.

---

## 20. Replication slots: rủi ro availability nếu role bị lạm dụng

**Replication slot** giúp PostgreSQL theo dõi vị trí WAL còn cần thiết cho consumer.

### 20.1. Physical slot

Có thể giữ WAL cần cho standby vật lý khi standby chậm hoặc ngừng kết nối.

### 20.2. Logical slot

Có thể giữ WAL cần cho logical decoding/subscriber.

### 20.3. Consumer ngừng đọc có thể giữ WAL

Nếu một slot không tiến, primary có thể giữ nhiều WAL, tăng sử dụng ổ đĩa. `max_wal_size` không phải giới hạn cứng bảo đảm mọi WAL sẽ bị xóa khi slot vẫn cần chúng.

### 20.4. Vì sao là vấn đề security?

Một credential có quyền replication bị lạm dụng có thể ảnh hưởng đến cách tiêu thụ WAL/slots, tạo rủi ro availability hoặc truy cập dữ liệu. Least privilege cần bao gồm monitoring, giới hạn cấu hình và quản trị vòng đời slots.

### 20.5. Theo dõi slots

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_catalog.pg_replication_slots
ORDER BY slot_name;
```

Các cột có thể NULL tùy loại slot hoặc trạng thái. Việc xem đầy đủ thông tin còn phụ thuộc quyền và phiên bản.

### 20.6. Không drop slot trong incident một cách mù quáng

Xóa slot có thể làm consumer mất khả năng catch up từ vị trí cũ, buộc tái đồng bộ hoặc gây mất khả năng nối lại. Cần xác định consumer owner, lag, retention và kế hoạch khôi phục trước.

---

## 21. Physical replication và logical replication: so sánh quyền

| Góc nhìn | Physical replication | Logical replication |
| --- | --- | --- |
| Đơn vị dữ liệu | WAL/storage-level changes | Relation/row-level logical changes |
| Phạm vi điển hình | Cluster/physical instance | Tập bảng theo publication |
| Tài khoản kết nối publisher | LOGIN có REPLICATION hoặc đặc quyền phù hợp | LOGIN replication phù hợp, cùng các quyền cần thiết |
| Dữ liệu nhạy cảm | Phạm vi rất rộng | Theo publication, nhưng vẫn có thể rộng |
| Cần SELECT published tables ban đầu | Không theo cách SQL table copy của logical | Initial copy có thể cần SELECT |
| Thay đổi schema | Sao chép vật lý cùng cluster | DDL thường phải phối hợp riêng |
| RLS bảo vệ stream theo user? | Không như SELECT qua RLS | Có quy tắc đặc thù, không tự là tenant authorization |
| Replication slots | Có thể sử dụng | Thường quan trọng |
| Quyền ứng dụng trên subscriber | Cấp riêng | Cấp riêng |
| Mục đích | HA/DR/physical backup | Analytics, CDC, migration/đồng bộ chọn lọc |

**Cả hai đều không nên chạy dưới login của HTTP API.**

---

## 22. Backup role và monitoring role nên tách riêng

Một kiến trúc hay quên hai vai trò:

### 22.1. Backup

Logical dump có thể cần quyền SELECT dữ liệu và quyền liên quan sequences/metadata theo công cụ, trong khi physical backup dùng cơ chế khác. Vì vậy “backup role” phải được thiết kế **theo loại backup**.

### 22.2. Monitoring

Một hệ thống monitoring chủ yếu cần các metrics:

- Số kết nối và trạng thái session.
- Replication lag.
- WAL generation/retention.
- Locks và một số thống kê tables.
- Dung lượng và hoạt động autovacuum.

Nó không mặc nhiên cần SELECT mọi bảng khách hàng hay UPDATE đơn hàng.

### 22.3. Predefined roles

Có thể cân nhắc những roles được PostgreSQL cung cấp như:

- `pg_monitor`.
- `pg_read_all_stats`.
- `pg_read_all_settings`.

Chúng có phạm vi thông tin đáng kể; phải chọn quyền nhỏ nhất phù hợp dashboard. Không cấp `pg_read_all_data` chỉ vì job muốn xem replication lag.

### 22.4. Bảo vệ dữ liệu thống kê

Một số statistics hoặc query text có thể chứa thông tin nhạy cảm. Quyền đọc monitoring cần được review cùng logging/redaction.

---

## 23. Lab an toàn: mô hình owner, migration và runtime

Phần này dùng các role `NOLOGIN` để mô phỏng luồng quyền, **không tạo bất kỳ superuser hoặc replication login**. Các câu CREATE ROLE vẫn cần quyền quản trị thích hợp, nên chỉ chạy trên cluster/database lab đã được ủy quyền.

Giả sử database lab riêng, chưa có các role và schema dưới đây.

**Mục tiêu lab:**

- Owner không đăng nhập.
- Migrator được phép dùng quyền owner để tạo object khi cần.
- Reader chỉ đọc view catalog.
- Writer chỉ đọc SKU/stock và UPDATE stock.
- Không cho reader xem unit_cost/internal_note hoặc sửa dữ liệu.
- Kiểm tra quyền hiệu lực.
- Hiểu ownership và default privileges.

### 23.1. Tạo roles

```sql
-- Chỉ trong môi trường lab có quyền quản trị roles:
CREATE ROLE sec392_owner NOLOGIN;

CREATE ROLE sec392_migrator NOLOGIN NOINHERIT;

CREATE ROLE sec392_read_group NOLOGIN;
CREATE ROLE sec392_write_group NOLOGIN;

CREATE ROLE sec392_reader NOLOGIN INHERIT;
CREATE ROLE sec392_writer NOLOGIN INHERIT;

-- Migrator được quyền chuyển sang owner theo cấu hình membership.
GRANT sec392_owner TO sec392_migrator;

-- Các vai trò ứng dụng chỉ nhận nhóm quyền phù hợp.
GRANT sec392_read_group TO sec392_reader;
GRANT sec392_write_group TO sec392_writer;
```

**Vì sao actor roles ở lab là NOLOGIN?** Ta không cần tạo credentials mới chỉ để thử SQL. Administrator được ủy quyền có thể mô phỏng bằng `SET ROLE`. Production sẽ có login roles thực và secrets được quản lý.

### 23.2. Điều kiện kiểm thử membership

Trong PostgreSQL 16+, cần kiểm tra các membership options `INHERIT`/`SET` nếu môi trường có chính sách cấp role tùy biến. Lab giả định reader/writer có thể sử dụng quyền nhóm đã cấp.

### 23.3. Tạo schema do owner sở hữu

```sql
CREATE SCHEMA sec392_lab
AUTHORIZATION sec392_owner;
```

Đây là schema riêng cho demo, không dùng `public`.

### 23.4. Tạo bảng khi làm việc dưới owner

Trong phiên quản trị có quyền phù hợp:

```sql
SET ROLE sec392_owner;

CREATE TABLE sec392_lab.products (
    sku TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    stock INTEGER NOT NULL
        CONSTRAINT sec392_products_stock_nonnegative
        CHECK (stock >= 0),
    unit_cost NUMERIC(12,2) NOT NULL
        CONSTRAINT sec392_products_cost_nonnegative
        CHECK (unit_cost >= 0),
    internal_note TEXT
);

INSERT INTO sec392_lab.products (
    sku,
    display_name,
    stock,
    unit_cost,
    internal_note
)
VALUES
    ('SKU-A', 'Bàn phím', 12, 300000.00, 'Supplier Alpha'),
    ('SKU-B', 'Chuột',    40,  95000.00, 'Supplier Beta'),
    ('SKU-C', 'Màn hình',  5, 1900000.00, NULL);

RESET ROLE;
```

### 23.5. Kết quả

Bảng `sec392_lab.products` có owner là `sec392_owner`. Reader/writer chưa có quyền đọc bảng chỉ vì bảng đã được tạo.

---

## 24. Lab: view catalog làm giao diện đọc

Catalog API chỉ cần SKU, tên sản phẩm và số lượng sẵn có, không cần giá vốn hay ghi chú nội bộ.

```sql
SET ROLE sec392_owner;

CREATE VIEW sec392_lab.v_catalog AS
SELECT
    sku,
    display_name,
    stock
FROM sec392_lab.products;

COMMENT ON VIEW sec392_lab.v_catalog
IS 'Catalog read model: public product identifiers, display names and stock; excludes unit cost and internal notes.';

RESET ROLE;
```

### 24.1. Vì sao dùng view?

- Giao diện SELECT ổn định.
- Hạn chế các cột được công bố.
- Không bắt client hiểu mọi bảng nội bộ.
- Có thể cấp SELECT view mà không cấp SELECT bảng nền theo cơ chế view mặc định thích hợp.

### 24.2. View không tự bảo đảm authorization

Nếu role còn quyền SELECT bảng nền qua đường khác, nó vẫn có thể đọc unit_cost. Vì vậy phải kiểm tra tổng hợp quyền trực tiếp, membership và PUBLIC.

### 24.3. View owner và RLS

Một view mặc định có thể dùng quyền owner khi truy cập bảng nền, ảnh hưởng RLS. Trong multi-tenant, phải quyết định có dùng `security_invoker` hay một security model khác; không mặc định view là “bảo vệ tenant tự động”.

---

## 25. Lab: cấp quyền đọc và ghi riêng

### 25.1. Schema USAGE

```sql
SET ROLE sec392_owner;

GRANT USAGE ON SCHEMA sec392_lab
TO sec392_read_group, sec392_write_group;
```

### 25.2. Reader chỉ SELECT view

```sql
GRANT SELECT ON sec392_lab.v_catalog
TO sec392_read_group;
```

### 25.3. Writer chỉ SELECT SKU/stock và UPDATE stock

```sql
GRANT SELECT (sku, stock),
      UPDATE (stock)
ON TABLE sec392_lab.products
TO sec392_write_group;

RESET ROLE;
```

### 25.4. Không grant owner role cho runtime

Ta **không** chạy:

```sql
-- Không cấp:
-- GRANT sec392_owner TO sec392_reader;
-- GRANT sec392_owner TO sec392_writer;
```

Điều này rất quan trọng. Nếu runtime có đường SET ROLE sang owner, việc tách runtime với owner sẽ mất ý nghĩa.

### 25.5. Không grant ALL TABLES theo thói quen

```sql
-- Tránh dùng như mặc định:
-- GRANT ALL ON ALL TABLES IN SCHEMA sec392_lab
-- TO sec392_read_group, sec392_write_group;
```

Grant rộng khiến scope của role tăng ngoài chức năng yêu cầu.

---

## 26. Lab: kiểm thử quyền reader

Đây là ví dụ **positive test**:

```sql
SET ROLE sec392_reader;

SELECT sku, display_name, stock
FROM sec392_lab.v_catalog
ORDER BY sku;

RESET ROLE;
```

Reader có quyền SELECT view qua nhóm sec392_read_group.

### 26.1. Negative test: không đọc unit_cost

Chạy trong một phiên thử được phép, riêng biệt:

```sql
SET ROLE sec392_reader;

-- Dự kiến permission denied:
SELECT sku, unit_cost
FROM sec392_lab.products;

RESET ROLE;
```

Nếu một câu lỗi làm transaction hiện tại bị aborted, cần ROLLBACK theo quy tắc trước khi chạy lệnh tiếp. Với script automation, dùng test connections/transactions độc lập.

### 26.2. Negative test: không UPDATE

```sql
SET ROLE sec392_reader;

-- Dự kiến permission denied:
UPDATE sec392_lab.products
SET stock = stock + 1
WHERE sku = 'SKU-A';

RESET ROLE;
```

### 26.3. Negative test: không CREATE TABLE

```sql
SET ROLE sec392_reader;

-- Dự kiến permission denied:
CREATE TABLE sec392_lab.unexpected_table (id INTEGER);

RESET ROLE;
```

Reader chỉ có USAGE schema, không CREATE.

### 26.4. Không phải vì SELECT view mà có SELECT bảng nền

Với view mặc định do owner tạo và quyền được cấp phù hợp, caller có thể đọc những cột của view mà không cần SELECT mọi cột trên base table. Đó là lý do view có thể tạo lớp read-only interface, nhưng ownership/RLS phải được review.

### 26.5. Kiểm tra dưới role thực

Chạy tất cả positive và negative tests bằng đúng role hiệu lực của application. Một superuser thường vượt được nhiều quyền nên không phù hợp để chứng minh giới hạn của runtime.

---

## 27. Lab: kiểm thử quyền writer

### 27.1. Đọc stock

```sql
SET ROLE sec392_writer;

SELECT sku, stock
FROM sec392_lab.products
ORDER BY sku;

RESET ROLE;
```

### 27.2. Conditional UPDATE có rollback

```sql
BEGIN;

SET ROLE sec392_writer;

UPDATE sec392_lab.products
SET stock = stock - 2
WHERE sku = 'SKU-A'
  AND stock >= 2
RETURNING sku, stock;

ROLLBACK;
```

Đây là ví dụ thay đổi dữ liệu trong transaction thử nghiệm. Sau ROLLBACK, stock được phục hồi về trạng thái trước câu UPDATE.

### 27.3. Vì sao cần SELECT lẫn UPDATE?

Câu lệnh đọc `stock` trong biểu thức và `sku` trong điều kiện/RETURNING, nên writer cần SELECT những cột được sử dụng theo quyền SQL phù hợp, cùng UPDATE(stock).

### 27.4. Negative test: không sửa giá vốn

```sql
SET ROLE sec392_writer;

-- Dự kiến permission denied:
UPDATE sec392_lab.products
SET unit_cost = 1
WHERE sku = 'SKU-A';

RESET ROLE;
```

### 27.5. Negative test: không DROP TABLE

```sql
SET ROLE sec392_writer;

-- Dự kiến permission denied:
DROP TABLE sec392_lab.products;

RESET ROLE;
```

Vì writer không sở hữu table và không có đặc quyền DDL tương đương.

### 27.6. Ràng buộc dữ liệu vẫn cần thiết

CHECK(stock>=0) vẫn bảo vệ những đường ghi khác. Không dùng least privilege để thay thế constraints. Cũng không để runtime ghi stock bằng công thức không atomic nếu concurrency có thể gây tồn kho âm.

---

## 28. Lab: kiểm tra metadata và quyền thực tế

### 28.1. Xem role attributes

```sql
SELECT
    rolname,
    rolcanlogin,
    rolsuper,
    rolcreatedb,
    rolcreaterole,
    rolreplication,
    rolbypassrls,
    rolinherit
FROM pg_catalog.pg_roles
WHERE rolname LIKE 'sec392_%'
ORDER BY rolname;
```

Kỳ vọng các role lab đều NOLOGIN, không SUPERUSER, không REPLICATION và không BYPASSRLS.

### 28.2. Xem schema owner

```sql
SELECT
    nspname,
    pg_catalog.pg_get_userbyid(nspowner) AS owner
FROM pg_catalog.pg_namespace
WHERE nspname = 'sec392_lab';
```

### 28.3. Xem table/view owner

```sql
SELECT
    c.relname,
    c.relkind,
    pg_catalog.pg_get_userbyid(c.relowner) AS owner
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'sec392_lab'
  AND c.relkind IN ('r','p','v','m','S')
ORDER BY c.relname;
```

### 28.4. Schema privilege

```sql
SELECT
    pg_catalog.has_schema_privilege(
        'sec392_reader', 'sec392_lab', 'USAGE'
    ) AS reader_has_schema_usage,
    pg_catalog.has_schema_privilege(
        'sec392_writer', 'sec392_lab', 'USAGE'
    ) AS writer_has_schema_usage;
```

### 28.5. Table/column privilege

```sql
SELECT
    pg_catalog.has_table_privilege(
        'sec392_reader', 'sec392_lab.v_catalog', 'SELECT'
    ) AS reader_can_select_view,
    pg_catalog.has_column_privilege(
        'sec392_writer', 'sec392_lab.products',
        'stock', 'UPDATE'
    ) AS writer_can_update_stock,
    pg_catalog.has_column_privilege(
        'sec392_writer', 'sec392_lab.products',
        'unit_cost', 'UPDATE'
    ) AS writer_can_update_cost;
```

Kỳ vọng các giá trị tương ứng là TRUE, TRUE, FALSE nếu không có grants ngoài ý muốn.

### 28.6. Metadata không thay chạy negative tests

Một role có thể có quyền qua group role hoặc PUBLIC khác; function/view có thể tạo đường quyền gián tiếp. Các hàm has_* giúp quan sát, nhưng phải chạy các hành động thật từ role đúng.

---

## 29. Role membership: đừng chỉ kiểm tra GRANT trực tiếp

Giả sử `catalog_api_login` được grant `shop_catalog_read`. Nếu nó đồng thời là thành viên của `shop_all_write` thì credential này vẫn có quyền ghi qua đường khác.

### 29.1. Query quan hệ membership

```sql
SELECT
    member.rolname AS member_role,
    parent.rolname AS granted_role,
    grantor.rolname AS grantor_role,
    m.admin_option
FROM pg_catalog.pg_auth_members AS m
JOIN pg_catalog.pg_roles AS member
  ON member.oid = m.member
JOIN pg_catalog.pg_roles AS parent
  ON parent.oid = m.roleid
JOIN pg_catalog.pg_roles AS grantor
  ON grantor.oid = m.grantor
WHERE member.rolname LIKE 'sec392_%'
ORDER BY member_role, granted_role;
```

Từ PostgreSQL 16, catalog còn chứa các membership options liên quan `INHERIT` và `SET`. Khi dùng những cột đó trong audit script, kiểm tra chúng tồn tại ở đúng phiên bản.

### 29.2. Không tự cấp owner membership cho runtime

Việc runtime có membership tới owner với khả năng SET ROLE có thể biến quyền DDL thành quyền khả dụng dù runtime không có GRANT CREATE trực tiếp.

### 29.3. Membership có thể là một chuỗi

`role A → role B → role C` có thể tạo đường quyền gián tiếp tùy options. Audit nên xem đồ thị membership, không chỉ một bậc.

### 29.4. ADMIN OPTION khác INHERIT/SET

- `ADMIN`: khả năng quản trị việc cấp membership theo quy tắc tương ứng.
- `INHERIT`: khả năng dùng quyền thừa hưởng ngay.
- `SET`: khả năng chuyển vai trò khi được phép.

Các thuộc tính này không thay thế nhau.

---

## 30. Default privileges: đừng để migration mới tạo lỗi permission denied

Một bảng mới được migration tạo ra không tự nhận các grants giống những bảng đã tạo trước.

### 30.1. GRANT cho đối tượng hiện tại

```sql
GRANT SELECT ON ALL TABLES IN SCHEMA shop_reports
TO shop_report_reader;
```

Áp dụng với những đối tượng thuộc phạm vi hỗ trợ đang tồn tại.

### 30.2. ALTER DEFAULT PRIVILEGES cho tương lai

```sql
ALTER DEFAULT PRIVILEGES
FOR ROLE shop_owner
IN SCHEMA shop_reports
GRANT SELECT ON TABLES TO shop_report_reader;
```

Tác động tới các tables/views phù hợp được tạo **sau đó** bởi shop_owner trong schema đó.

### 30.3. Role creator cực kỳ quan trọng

Nếu pipeline không `SET ROLE shop_owner` mà tạo table bằng migration login, default privileges gắn với shop_owner có thể **không** được áp dụng.

### 30.4. Không áp default GRANT SELECT mọi bảng nội bộ

Nếu một schema chứa PII hoặc secrets, `GRANT SELECT ON TABLES` có thể vô tình mở quyền vào đối tượng mới. Nên có schema riêng cho dữ liệu được phép công bố hoặc review grants từng object.

### 30.5. Default privileges cho functions/sequences

Có thể cấu hình mặc định theo loại đối tượng, nhưng cần hiểu quyền EXECUTE của functions thường được cấp cho PUBLIC theo mặc định, và sequence privileges có phạm vi riêng.

### 30.6. Default privilege không sửa ACL cũ

Khi điều chỉnh chính sách, cần rà soát cả hiện tại và tương lai; một `ALTER DEFAULT PRIVILEGES` duy nhất không hồi tố các grants đã cấp.

---

## 31. Vai trò migration trong phiên thực hành

Để thấy mối quan hệ creator/owner, hãy xét đoạn:

```sql
-- Giả định session được quyền SET ROLE sec392_owner:
SET ROLE sec392_owner;

CREATE TABLE sec392_lab.migration_marker (
    marker_id INTEGER PRIMARY KEY,
    description TEXT NOT NULL
);

RESET ROLE;
```

Khi đó owner của `migration_marker` thường là `sec392_owner` theo role tạo.

### 31.1. Nếu tạo bằng role khác?

Nếu một deploy login là current_user tại CREATE TABLE, table mới có thể thuộc role deploy, không phải owner NOLOGIN. Sau này có thể xảy ra:

- Migration chạy với owner chuẩn gặp permission denied.
- Default ACL gắn với owner chuẩn không áp dụng.
- Những views/functions do owner chuẩn tạo có quyền nền khác kỳ vọng.
- RLS/ownership semantics bị thay đổi.

### 31.2. Tại sao không cho app tự migrate khi startup?

App startup xảy ra trên nhiều instances, dùng connection pool và runtime credentials. Việc cho mỗi instance DDL privileges làm tăng rủi ro và khó kiểm soát race khi đồng thời chạy migration.

### 31.3. Job triển khai nên dùng connection riêng

Không nên giữ quyền owner trong pool sau deploy; hãy đóng migration connection và chỉ mở runtime credentials khi phục vụ traffic.

---

## 32. PUBLIC và quyền mặc định trên functions/schema

Trong PostgreSQL, `PUBLIC` biểu diễn mọi roles hiện tại và tương lai.

### 32.1. Không nhầm PUBLIC với schema public

- `PUBLIC` trong GRANT/REVOKE: pseudo-role bao phủ mọi roles.
- `public` là tên một schema.

### 32.2. Function EXECUTE mặc định

PostgreSQL thường cấp EXECUTE cho PUBLIC trên functions mới, trừ khi default privileges đã được thay đổi.

Một SECURITY DEFINER function có side effects mà còn PUBLIC EXECUTE có thể là đường quyền nghiêm trọng.

### 32.3. Transaction tạo function và khóa grants

Ví dụ khái niệm:

```sql
BEGIN;

CREATE FUNCTION shop_internal.do_sensitive_work(...)
RETURNS ...
LANGUAGE plpgsql
SECURITY DEFINER
AS $fn$
BEGIN
    -- ...
END;
$fn$;

REVOKE ALL ON FUNCTION shop_internal.do_sensitive_work(...)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION shop_internal.do_sensitive_work(...)
TO shop_authorized_worker;

COMMIT;
```

Đây là **mẫu cấu trúc**, các dấu `...` phải được thay bằng định nghĩa SQL hợp lệ. Mục đích là tránh khoảng thời gian người khác có thể gọi function nhạy cảm trước khi REVOKE. Không chạy đoạn placeholder nguyên văn.

### 32.4. public schema trong PostgreSQL 15+

Database mới từ PostgreSQL 15 thường có mặc định schema public an toàn hơn về quyền CREATE của PUBLIC. Nhưng database được upgrade/restore có thể giữ ACL cũ. Luôn kiểm tra thực tế, đặc biệt khi dùng `search_path`.

### 32.5. GRANT một quyền rộng không được xóa bằng REVOKE từ một nhánh khác

Nếu role có SELECT qua membership, REVOKE SELECT từ PUBLIC chưa chắc làm role mất SELECT. Quyền được tính qua nhiều đường hợp lệ.

---

## 33. Sequence, identity và default nextval

Application INSERT đôi khi cần quyền sequence ngoài quyền trên table.

### 33.1. SERIAL/default nextval

Ví dụ:

```sql
CREATE SEQUENCE shop_internal.order_id_seq;

CREATE TABLE shop_internal.orders (
    id BIGINT PRIMARY KEY
        DEFAULT nextval('shop_internal.order_id_seq'::REGCLASS)
);
```

Role INSERT có thể cần `USAGE` hoặc quyền phù hợp trên sequence để gọi nextval.

### 33.2. GRANT theo sequence cụ thể

```sql
GRANT USAGE ON SEQUENCE shop_internal.order_id_seq
TO shop_order_writer;
```

### 33.3. IDENTITY có semantics khác

Cột `GENERATED ... AS IDENTITY` được PostgreSQL quản lý khác một DEFAULT nextval thủ công. Không suy luận chúng cần bộ sequence grants y hệt nhau; kiểm tra phiên bản và thao tác thật.

### 33.4. Không cấp USAGE ON ALL SEQUENCES nếu không cần

Một worker chỉ ghi order không cần quyền trên sequence của mọi bảng billing/customer nếu scope không liên quan.

### 33.5. Sequence values không rollback như row data

Một số sequence operations có thể tạo gaps dù transaction rollback; không suy ra từ ID bị bỏ qua rằng dữ liệu bị mất hoặc có lỗi bảo mật.

---

## 34. Function SECURITY DEFINER: đường quyền gián tiếp

Một role không có UPDATE trực tiếp trên bảng vẫn có thể làm thay đổi dữ liệu nếu được EXECUTE function chạy dưới quyền owner.

### 34.1. Ý tưởng

```text
inventory_worker_login
         |
         | EXECUTE reserve_stock(sku, qty)
         v
SECURITY DEFINER function (owner)
         |
         +--> UPDATE inventory.stock
         +--> INSERT stock_movements
```

Đây có thể là thiết kế tốt nếu function thực hiện **đúng một nghiệp vụ hẹp**.

### 34.2. Rủi ro

Nếu function nhận tên bảng tự do rồi thực thi dynamic SQL hoặc đọc dữ liệu tenant do caller tự chọn, nó có thể mở rộng quyền ngoài dự kiến.

### 34.3. Search path an toàn

Với SECURITY DEFINER, nên:

- Schema-qualify bảng và functions quan trọng.
- Cấu hình `SET search_path` chỉ qua schemas đáng tin.
- Đặt `pg_temp` theo khuyến nghị để tránh shadowing.
- Không để schema có CREATE cho untrusted users nằm trong đường tìm kiếm trước schema tin cậy.
- Giới hạn EXECUTE đúng roles.
- Đánh giá input, error message, side effects và RLS.

### 34.4. Quyền application phải xét cả EXECUTE

Một role “read-only” nhưng được gọi một function SECURITY DEFINER chứa INSERT/UPDATE **không thực sự read-only theo toàn bộ đường truy cập**.

### 34.5. Không cố tình bỏ security để tối ưu inlining

SECURITY DEFINER có thể giới hạn SQL function inlining, nhưng đó là ranh giới bảo mật. Không bỏ nó chỉ vì EXPLAIN muốn một plan nhanh hơn mà không thay kiến trúc quyền.

---

## 35. RLS giữa owner, runtime và replication

RLS là một lớp bảo vệ theo hàng, nhưng có các ngoại lệ quan trọng.

### 35.1. Table owner mặc định thường bypass

Owner của bảng thường không chịu policy RLS như một runtime role thông thường. Vì vậy owner NOLOGIN và runtime tách riêng giúp tránh service vô tình bỏ qua RLS.

### 35.2. FORCE ROW LEVEL SECURITY

```sql
ALTER TABLE shop_internal.tenant_orders
FORCE ROW LEVEL SECURITY;
```

khi table có RLS được bật, tùy chọn này khiến owner cũng chịu RLS theo cơ chế PostgreSQL; nhưng superuser và BYPASSRLS vẫn là trường hợp đặc biệt.

### 35.3. BYPASSRLS không nên cấp cho runtime

Một service user có `BYPASSRLS` có thể truy cập hàng của tenant khác nếu table privileges cho phép. Không cấp thuộc tính này để “sửa” một query thiếu policy.

### 35.4. Replication/RLS là vấn đề riêng

Logical replication có đặc điểm bảo mật khác SELECT của ứng dụng. Physical replication hoạt động ở cấp WAL, không phải qua câu SELECT có RLS. Vì vậy phải xem xét dữ liệu có thể rời primary qua replication ngay cả khi RLS bảo vệ caller SQL.

### 35.5. Không tin tenant_id do client nhập

Nếu RLS dùng:

```sql
USING (
    tenant_id =
    current_setting('app.tenant_id')::INTEGER
)
```

thì cần bảo đảm setting được đặt từ ngữ cảnh được xác thực và client không thể giả mạo. Nếu caller có thể tự SET sang tenant khác, điều kiện này không đủ làm authorization boundary.

---

## 36. Schema segregation: giảm khả năng cấp quyền nhầm

Một ứng dụng có thể tách schemas theo chức năng:

```text
shop_internal:
    customers, orders, payments, cost_data

shop_api:
    v_catalog, v_order_summary

shop_reports:
    v_daily_paid_orders, v_revenue_by_region

shop_staging:
    import_orders, import_errors
```

### 36.1. API chỉ cần USAGE schema cần thiết

```sql
GRANT USAGE ON SCHEMA shop_api TO shop_catalog_read;
```

không cần USAGE/CREATE trên mọi schema nội bộ.

### 36.2. Reporting view không tự là data masking hoàn chỉnh

Để bảo vệ PII, cần kiểm tra output columns, ownership, SECURITY INVOKER, RLS, function execution, grants nền và các báo cáo phụ thuộc.

### 36.3. Staging chứa dữ liệu thô cần kiểm soát

ETL có thể lưu input chưa được làm sạch hoặc chứa PII. Không đặt staging cùng schema có default SELECT cho mọi reader.

### 36.4. Mỗi schema có thể có owner hoặc group quyền riêng

Tùy quy mô, dùng một app_owner cho toàn ứng dụng hoặc nhiều owner roles theo domain có thể hợp lý. Quan trọng là các trust boundaries được thể hiện rõ và migration có thể quản lý chúng.

### 36.5. Quá nhiều roles cũng có chi phí

Tách quá mức gây khó vận hành, quản lý secrets, grants và audit. Hãy nhóm theo nhiệm vụ/thông tin nhạy cảm tương đương, không nhất thiết một role cho từng câu SELECT.

---

## 37. Replication và application không nên chia sẻ network path không cần thiết

Ngay cả khi sử dụng login khác, nếu mọi role được phép kết nối từ mọi host, diện tấn công vẫn rộng.

### 37.1. App connection

```conf
# Ví dụ pg_hba.conf cho kết nối SQL ứng dụng
hostssl   shopdb   catalog_api_login      10.20.10.0/24   scram-sha-256
hostssl   shopdb   inventory_worker_login 10.20.11.0/24   scram-sha-256
```

### 37.2. Physical replication connection

```conf
hostssl   replication   physical_repl_login   10.20.30.40/32   scram-sha-256
```

### 37.3. Logical replication connection

```conf
# Logical connection thường dùng tên database thật
hostssl   shopdb   logical_repl_login   10.20.40.50/32   scram-sha-256
```

### 37.4. Không chỉ dựa vào pg_hba

Thêm firewall, TLS xác thực server, network segmentation, quản trị cert/secrets và logging kết nối.

### 37.5. Trên managed PostgreSQL

Một số cloud providers điều khiển HBA/network qua giao diện cấu hình riêng thay vì cho sửa `pg_hba.conf` trực tiếp. Phải dùng cơ chế chính thức của nhà cung cấp, không giả định có quyền chỉnh filesystem.

---

## 38. Quản lý credentials riêng cho từng thành phần

Một ví dụ cấu hình tốt hơn dùng cùng một account:

```text
Catalog API      -> catalog_api_login       (secret A)
Inventory Worker  -> inventory_worker_login  (secret B)
Migration CI      -> shop_migration_login    (secret C)
Physical Standby  -> physical_repl_login     (secret D)
Logical Subscriber-> logical_repl_login      (secret E)
Monitoring        -> shop_monitor_login      (secret F)
```

### 38.1. Vì sao tách secrets?

Nếu secret A bị lộ, có thể rotate/revoke A mà không cần đổi ngay toàn bộ hệ thống và không mở quyền của migration/replication.

### 38.2. Cùng một role ở nhiều môi trường?

Không dùng credential production trong dev/staging. Với mô hình hạ tầng khác nhau, role names có thể giống nhau để migration dễ quản lý, nhưng secrets/permissions phải tách theo từng môi trường.

### 38.3. Rotate replication credentials có tác động vận hành

Đổi password/certificate của standby có thể ngắt replication connection nếu không phối hợp cập nhật. Cần quy trình rotation có quan sát replication lag và khả năng rollback.

### 38.4. Secrets không ở source code

Không đặt mật khẩu thật trong migration SQL, repository, log CI hoặc output `SHOW` không được bảo vệ. Dùng secret manager, OS credential management hoặc service identity theo hạ tầng.

### 38.5. Credential rotation không đồng nghĩa đã cắt kết nối hiện có

Thay mật khẩu hoặc đặt `NOLOGIN` thường ảnh hưởng khả năng đăng nhập mới; các session đã xác thực có thể còn hoạt động. Trong incident, cần xử lý sessions đang mở theo thủ tục được ủy quyền.

---

## 39. Giám sát replication bằng role quan sát

Không nên cho dashboard monitoring trực tiếp dùng physical_repl_login nếu nó chỉ cần đọc metrics.

### 39.1. pg_stat_replication

Trên primary, một role được cấp quyền đọc thống kê phù hợp có thể xem:

```sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_catalog.pg_stat_replication
ORDER BY application_name;
```

Danh sách cột/visibility phụ thuộc phiên bản và quyền. Một số trường có thể NULL.

### 39.2. Replication slots

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_catalog.pg_replication_slots
ORDER BY slot_name;
```

### 39.3. Logical subscriber

Trên subscriber có thể dùng các views như `pg_stat_subscription` để xem worker và trạng thái hoạt động, theo quyền và phiên bản.

### 39.4. Chỉ số quan trọng

- Lag gửi/ghi/flush/replay.
- Slot không active.
- WAL giữ lại bởi slot.
- Số WAL senders và connection failures.
- Thời gian kể từ lần đồng bộ gần nhất.
- Dung lượng filesystem và cảnh báo growth.
- Lỗi authentication/SSL hoặc permission denied.
- Tỷ lệ apply errors/worker restarts theo cơ chế quan sát được.

### 39.5. Monitoring quyền thấp hơn replication

Một role `pg_monitor` hoặc role quan sát chuyên dụng có thể đáp ứng nhu cầu metrics mà không cần REPLICATION, tùy mức thông tin. Review predefined role vì nó vẫn có quyền xem thông tin hệ thống nhạy cảm.

---

## 40. Kiểm tra các role có đặc quyền cao

Dùng `pg_roles` để inventory:

```sql
SELECT
    rolname,
    rolcanlogin,
    rolsuper,
    rolcreatedb,
    rolcreaterole,
    rolreplication,
    rolbypassrls
FROM pg_catalog.pg_roles
WHERE rolsuper
   OR rolcreaterole
   OR rolcreatedb
   OR rolreplication
   OR rolbypassrls
ORDER BY rolname;
```

### 40.1. Câu hỏi audit

- Có runtime login nào là superuser?
- Có API login nào có CREATEROLE hoặc BYPASSRLS?
- Role replication nào còn được dùng? Role nào đã mồ côi?
- Có break-glass role nào có LOGIN nhưng không được bảo vệ đúng?
- Có account của nhân sự cũ?
- Managed roles nào do nhà cung cấp quản lý và không nên thay đổi?

### 40.2. Đặc quyền không thể suy ra từ tên

Một role tên `read_only` nhưng `rolsuper=true` vẫn có quyền superuser thật. Một role tên `admin` trên managed service có thể không phải superuser.

### 40.3. Thay quyền admin có thể ảnh hưởng cả cluster

Không tự chạy `ALTER ROLE ... NOSUPERUSER` hoặc `DROP ROLE` cho tài khoản quản trị thiết yếu nếu chưa có kế hoạch khôi phục.

---

## 41. Kiểm tra default PUBLIC grants

Hai vùng thường cần xem:

### 41.1. Function EXECUTE

```sql
SELECT
    n.nspname AS schema_name,
    p.proname AS function_name,
    p.prosecdef AS security_definer,
    pg_catalog.pg_get_userbyid(p.proowner) AS owner
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE n.nspname IN ('shop_internal','shop_api')
ORDER BY n.nspname, p.proname;
```

Cần xem ACL/function privileges thực tế với `has_function_privilege` hoặc metadata thích hợp, đặc biệt functions có `prosecdef=true`.

### 41.2. Schema public

```sql
SELECT
    pg_catalog.has_schema_privilege(
        'public', 'USAGE'
    ) AS current_role_can_use_public,
    pg_catalog.has_schema_privilege(
        'public', 'CREATE'
    ) AS current_role_can_create_in_public;
```

### 41.3. Default có thể thay đổi qua version/restore

PostgreSQL 15+ thay đổi mặc định của public schema trên database mới; những cluster nâng cấp từ phiên bản cũ có thể giữ grants cũ.

### 41.4. Đừng dùng REVOKE ngẫu nhiên trên shared production

Thu hồi quyền CONNECT/CREATE/EXECUTE rộng có thể làm các tools/ứng dụng đang chạy mất quyền. Cần inventory dependencies, làm migration có rollback và test.

---

## 42. Các lỗi triển khai thường gặp khi tách role

### 42.1. “Migration báo permission denied, cấp SUPERUSER cho nó”

Đây là cách mở rộng blast radius rất lớn. Hãy xác định đúng owner/schema/grant/membership/DDL, rồi cấp quyền theo nhiệm vụ.

### 42.2. “Runtime cần INSERT nên dùng owner role”

INSERT không yêu cầu ownership. Cấp INSERT đúng bảng/cột, quyền sequence khi cần, cùng constraints và RLS phù hợp.

### 42.3. “Standby cần chạy nên dùng admin password”

Physical standby thường có thể dùng replication login chuyên dụng; việc dùng superuser password cho replication config làm tăng rủi ro và khó rotate.

### 42.4. “Analytics chỉ nhận vài bảng nên logical replication account an toàn”

Publication có thể thay đổi scope; initial sync và subscriber vẫn chứa dữ liệu có thể nhạy cảm. Role replication không tự là role SELECT giới hạn bởi báo cáo.

### 42.5. “REVOKE SELECT từ PUBLIC là đủ”

Role có thể có SELECT qua group membership hoặc trực tiếp. Hãy kiểm tra quyền hiệu lực.

### 42.6. “Đã có RLS nên không cần tách owner”

Table owner có thể bypass RLS theo mặc định. Runtime không nên làm table owner nếu ứng dụng cần RLS giới hạn hàng.

### 42.7. “Reader không có UPDATE nên bất khả ghi”

Nó có thể EXECUTE function SECURITY DEFINER làm DML. Audit cả quyền function, membership và foreign/external access.

### 42.8. “Replication lag là lỗi permission nên cấp thêm BYPASSRLS”

Lag có thể do network, slot, CPU, write volume, apply errors, disk và nhiều nguyên nhân khác. Không thay thuộc tính bảo mật mạnh để sửa một triệu chứng chưa chẩn đoán.

---

## 43. Tách role theo topology nhiều primary và replicas

Giả sử hệ thống có:

```text
Primary shop-db
  |
  +--> Standby A (HA)
  +--> Standby B (read scaling)
  |
  +--> Logical subscriber analytics-db
  |
  +--> Backup service / WAL archive
  |
  +--> API applications
```

### 43.1. Có nên dùng một physical_repl_login chung cho mọi standby?

Có thể về mặt kỹ thuật, nhưng tách account per standby/đối tác khi quản trị cho phép có lợi cho rotation, audit và thu hồi riêng. Cân bằng số lượng credentials với khả năng vận hành.

### 43.2. Role replication không tự giới hạn “chỉ slot của nó”

Tùy giao thức và đặc quyền PostgreSQL, một role có REPLICATION có năng lực cấp replication rộng hơn một slot name trong application config. Không dựa vào việc đặt slot_name riêng để thay thế phân quyền/kênh tin cậy.

### 43.3. Physical và logical nên có credentials riêng

Chúng có lifecycle, scope và kết nối khác nhau. Sự cố logical analytics không nên buộc rotate ngay credential physical HA vì cùng dùng chung secret.

### 43.4. Backup nên tách với standby

Backup job có lịch, location, retention và đặc quyền khác. Nếu dùng replication protocol, vẫn có thể tạo identity riêng theo công cụ.

### 43.5. Monitoring không cần subscription-owner role

Nó cần đọc metrics, không cần tạo/drop subscriptions hoặc thay subscription connection strings.

---

## 44. Tách role cho ứng dụng nhiều tenant

Một SaaS đa tenant thường có:

- Login của nhiều microservices.
- Các bảng chứa tenant_id.
- RLS policies hoặc application-enforced tenant scopes.
- Một số workers cross-tenant có quyền rộng hơn.
- Báo cáo tổng hợp có quyền khác với dữ liệu từng tenant.

### 44.1. Mỗi microservice có trust boundary riêng

Billing, support và catalog có loại dữ liệu khác nhau. Một role chung `saas_runtime_all_access` dễ biến sự cố catalog thành sự cố billing.

### 44.2. Role cho cross-tenant job cần review đặc biệt

Một job tổng hợp doanh thu nhiều tenants có thể cần đọc phạm vi rộng hơn API thông thường. Không cấp BYPASSRLS một cách máy móc; thiết kế chính sách/role/view/function chuyên biệt và kiểm soát chi tiết.

### 44.3. Tenant ID phải được xác thực

Nếu dựa vào `current_setting('app.tenant_id')`, việc thiết lập context phải đến từ tầng tin cậy; không cho caller SQL tự nhận mình là tenant khác.

### 44.4. Logical analytics replica có dữ liệu đa tenant

Nếu analytics subscriber nhận dữ liệu của tất cả tenants, nó phải được bảo vệ như một kho dữ liệu nhạy cảm, kể cả khi reports chỉ công bố aggregate.

### 44.5. Negative permission tests là bắt buộc

Test không chỉ “tenant 10 đọc được tenant 10”, mà còn “tenant 10 không đọc được tenant 20” ở tất cả các đường API/SQL phù hợp.

---

## 45. Sự cố: lộ credential của catalog API

Giả sử `catalog_api_login` bị lộ.

### 45.1. Nếu đã tách role đúng

Kẻ tấn công có thể đọc phạm vi catalog mà role được phép. Họ không nên:

- UPDATE stock.
- DROP bảng.
- Đọc giá vốn/PII.
- Tạo subscription hoặc stream WAL.
- Quản trị role.
- Bỏ qua RLS.

### 45.2. Hành động phản ứng

1. Xác định credential, môi trường và tài nguyên bị ảnh hưởng.
2. Tạm khóa/rotate theo incident runbook.
3. Quản lý các session hiện có của role bị lộ bằng công cụ được ủy quyền.
4. Xác minh role attributes và membership.
5. Kiểm tra logs/queries/khả năng exfiltration.
6. Khôi phục service bằng credential mới với quyền tối thiểu.
7. Review các đường SELECT/EXECUTE/view để phát hiện quyền ngoài ý định.

### 45.3. REVOKE quyền không tự xóa dữ liệu đã bị đọc

Nếu đã lộ dữ liệu, thu hồi quyền chỉ ngăn các truy cập tiếp theo theo phạm vi cơ chế; cần xử lý incident data exposure riêng.

### 45.4. Phân biệt rotation và session termination

Thay password hoặc `ALTER ROLE ... NOLOGIN` không bảo đảm mọi session đang mở bị chấm dứt ngay. Cần kế hoạch xử lý kết nối hiện có theo quyền DBA và cân nhắc tác động availability.

### 45.5. Vai trò của tách credential

Không phải vì user thiếu trách nhiệm; đây là thiết kế giúp một sự cố có thể được cô lập và khôi phục mà không vô tình làm ngừng migration, standby và backup.

---

## 46. Sự cố: migration login bị chiếm quyền

Sự cố này có phạm vi lớn hơn runtime.

### 46.1. Quyền tiềm tàng

Nếu migration login có thể `SET ROLE app_owner`, attacker có thể thay object được owner quản lý, bao gồm schema, functions và grants liên quan.

### 46.2. Vì sao không để migration secrets trong runtime pods?

Đó là cách làm cho bề mặt tấn công của một credential mạnh tương đương web API. Chỉ CI/CD, deployment operator hoặc secret manager phù hợp được dùng nó.

### 46.3. Kiểm soát vận hành

- Pipeline approval/review.
- Thực thi từ runner được tin cậy.
- Secrets theo môi trường.
- Không log password.
- Giám sát DDL/grants.
- Bảo vệ migration artifacts.
- Có rollback/restoration plan.
- Rotation nếu nghi ngờ compromise.

### 46.4. Migration role vẫn không cần REPLICATION

Khả năng tạo/sửa bảng không phải lý do để cấp quyền stream WAL hoặc quản lý replication slots.

### 46.5. Nguyên tắc bảo mật của release

Một release đúng code nhưng cấp nhầm owner hoặc PUBLIC EXECUTE cũng là lỗi bảo mật. Audit grants/owners sau migration là một phần kiểm thử phát hành.

---

## 47. Sự cố: replication slot giữ WAL quá lâu

Giả sử logical subscriber bị ngừng nhiều giờ và slot còn giữ WAL.

### 47.1. Triệu chứng

- Disk usage tăng.
- Slot không active hoặc restart_lsn không tiến.
- Replication lag lớn.
- Cảnh báo storage gần đầy.
- Các writes trên primary bị ảnh hưởng do thiếu dung lượng.

### 47.2. Hướng kiểm tra

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_catalog.pg_replication_slots
ORDER BY slot_name;
```

Kiểm tra tiếp hệ thống consumer, network, permissions, publisher/subscriber versions, worker errors và retention settings.

### 47.3. Không cấp SUPERUSER cho replication role chỉ vì slot lag

Lỗi này thường thuộc vận hành/stream consumption. Cấp quyền quá rộng không xử lý root cause.

### 47.4. Phân quyền thao tác slot cần kiểm soát

Không để application runtime tùy ý tạo/drop/advance replication slots nếu không có nhiệm vụ tương ứng. Những thao tác này có thể ảnh hưởng WAL retention và khả năng recovery.

### 47.5. Có kế hoạch tái đồng bộ

Nếu buộc phải bỏ slot hoặc mất WAL cần thiết, cần xác định cách reinitialize consumer mà không làm sai dữ liệu ứng dụng hoặc analytics.

---

## 48. Offboarding role và thu hồi quyền

Khi một deployment tool cũ hoặc service bị loại bỏ, cần thu hồi identity an toàn.

### 48.1. Kiểm tra ownership

```sql
SELECT
    pg_catalog.pg_get_userbyid(c.relowner) AS owner,
    COUNT(*) AS relation_count
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog','information_schema')
GROUP BY owner
ORDER BY relation_count DESC;
```

### 48.2. REASSIGN OWNED

```sql
REASSIGN OWNED BY old_owner TO new_owner;
```

có thể chuyển ownership của các đối tượng thuộc role cũ theo phạm vi được hỗ trợ; cần quyền thích hợp và kiểm tra nhiều databases.

### 48.3. DROP OWNED

```sql
DROP OWNED BY old_owner;
```

có thể xóa đối tượng role sở hữu và thu hồi privileges theo semantics PostgreSQL. **Không dùng lệnh này như cách “chỉ xóa một vài GRANT”**.

### 48.4. DROP ROLE

Chỉ drop khi role không còn owners/grants/dependencies cần xử lý trong các database/phạm vi cluster liên quan. Không xóa role replication đang được standby hoặc subscription sử dụng.

### 48.5. Thu hồi role membership

Nếu một runtime login không còn cần nhóm quyền:

```sql
REVOKE shop_inventory_write FROM inventory_worker_login;
```

sau khi đánh giá impact. Còn phải kiểm tra grants trực tiếp hoặc qua những membership khác.

### 48.6. Managed roles và system roles

Không chỉnh/xóa predefined hoặc provider-managed roles tùy tiện. Dùng cơ chế chính thức của nhà cung cấp và có kế hoạch khôi phục.

---

## 49. Kiểm tra quyền bằng psql và SQL

Các meta-commands có ích:

```text
\du
\du+
\dn+
\dp shop_internal.*
\df+ shop_internal.*
```

Đây là lệnh của `psql`, không phải SQL dùng trong JDBC.

### 49.1. Role attributes

```sql
SELECT rolname, rolsuper, rolcreaterole,
       rolreplication, rolbypassrls
FROM pg_catalog.pg_roles
ORDER BY rolname;
```

### 49.2. Schema owner

```sql
SELECT nspname,
       pg_catalog.pg_get_userbyid(nspowner) AS owner
FROM pg_catalog.pg_namespace
ORDER BY nspname;
```

### 49.3. Function đặc quyền

```sql
SELECT
    n.nspname,
    p.proname,
    pg_catalog.pg_get_userbyid(p.proowner) AS owner,
    p.prosecdef
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE p.prosecdef
ORDER BY n.nspname, p.proname;
```

### 49.4. Quyền hiệu lực

```sql
SELECT
    pg_catalog.has_schema_privilege(
        'sec392_reader', 'sec392_lab', 'USAGE'
    ) AS schema_ok,
    pg_catalog.has_table_privilege(
        'sec392_reader', 'sec392_lab.v_catalog', 'SELECT'
    ) AS view_ok;
```

### 49.5. Role đang hiệu lực

```sql
SELECT session_user, current_user;
```

Dùng để biết bạn đang test dưới login nào và quyền SQL hiện tại của ai; trong SECURITY DEFINER function, current_user có semantics theo function owner.

---

## 50. Tự động hóa kiểm thử phân quyền trong CI

Một pipeline có thể kiểm tra:

### 50.1. Schema contract

- Tables thuộc đúng owner NOLOGIN.
- Migration login có thể chạy DDL cần thiết.
- Runtime login không sở hữu bảng.
- Các schemas nhạy cảm không có CREATE cho PUBLIC.
- Functions nhạy cảm không PUBLIC EXECUTE.
- View owners/security options phù hợp.

### 50.2. Positive permission tests

- Catalog API SELECT được `v_catalog`.
- Inventory writer SELECT sku/stock.
- Inventory writer UPDATE stock theo câu DML đã thiết kế.
- Report service SELECT views được phép.
- Replication connection hoạt động bằng role riêng trên staging.

### 50.3. Negative permission tests

- Catalog API không UPDATE stock.
- Catalog API không SELECT unit_cost.
- Inventory writer không ALTER/DROP table.
- Runtime không SET ROLE app_owner.
- Runtime không CREATE publication/subscription.
- Runtime không sử dụng replication protocol.
- Report service không đọc bảng PII ngoài scope.
- App tenant A không đọc/sửa hàng tenant B.

### 50.4. Test từng câu thất bại độc lập

Một permission denied có thể khiến transaction đang mở bị đánh dấu aborted. Dùng các sessions/transactions tách biệt, rollback đúng cách, không làm hỏng toàn bộ suite.

### 50.5. Test lại sau mỗi migration

Một table mới có thể thiếu GRANT cho writer hoặc thừa GRANT cho reader. Một SECURITY DEFINER function mới có thể vô tình public. Đây là drift mà CI nên phát hiện trước production.

### 50.6. Không chạy kiểm thử đặc quyền cao trên production

Những thao tác như tạo ROLE REPLICATION, ngắt standby hay DROP subscription chỉ làm trên môi trường kiểm thử được phê duyệt; production tests nên ưu tiên read-only introspection và các đường DML có rollback an toàn.

---

## 51. Triển khai theo hướng Infrastructure as Code và migrations

Quyền PostgreSQL không nên chỉ tồn tại dưới dạng một số câu GRANT từng được DBA gõ thủ công rồi không ai nhớ.

### 51.1. Thiết kế role matrix trong version control

Lưu mô tả ai được phép làm gì:

```text
service / login / role group / database / schema /
object / privilege / lý do / owner phê duyệt
```

Không lưu passwords hoặc private keys vào repository.

### 51.2. Provision role qua tool chuyên dụng

Một số tổ chức dùng Terraform, Ansible, Kubernetes operators hoặc hạ tầng cloud để quản lý role và secrets; migration SQL quản lý schema/ACL ở phạm vi ứng dụng.

### 51.3. Chỉ định owner rõ trong migration

Có thể dùng `SET ROLE app_owner` hoặc cơ chế deploy đã được kiểm soát sao cho objects được tạo bởi đúng role.

### 51.4. Kiểm soát default grants

Default privileges của đúng creator role được version hóa, không giả định một lệnh GRANT hiện tại tự mở quyền tương lai.

### 51.5. Audit drift

So sánh trạng thái role attributes, memberships, grants, owners và SECURITY DEFINER functions hiện tại với ma trận mong muốn.

### 51.6. Có rollback cho security changes

Một lần REVOKE không đúng có thể làm application mất kết nối hoặc job sao chép ngừng. Một GRANT quá rộng có thể lộ dữ liệu. Thay đổi ACL cần review, staging tests và kế hoạch phục hồi.

---

## 52. Chọn mức tách role phù hợp quy mô

### 52.1. Ứng dụng nhỏ

Có thể bắt đầu với:

```text
admin
migration_login
app_owner NOLOGIN
app_runtime_login
backup/monitoring riêng khi cần
```

Nhưng app_runtime vẫn phải chỉ có CRUD cần thiết, không owner hoặc superuser.

### 52.2. Ứng dụng tầm trung

Tách read/write, deploy, backup, physical replication, analytics replication và monitoring theo hạ tầng.

### 52.3. Hệ thống nhiều microservices

Mỗi service được cấp bộ privileges theo domain: catalog, orders, billing, inventory. Role memberships phải không tạo đường ngang sang quyền của service khác.

### 52.4. Hệ thống đa tenant

RLS và trusted identity context trở thành phần quan trọng của scope; owner BYPASS và replication data exposure cần được xem xét rõ.

### 52.5. Hệ thống tuân thủ bảo mật cao

Có thể cần temporary elevated access, approval, audit đầy đủ, separation of duties, encryption, change management và periodic attestations ngoài các SQL GRANT/REVOKE.

### 52.6. Không có “một ma trận duy nhất” cho mọi hệ thống

Tối thiểu hóa quyền phải xét khả năng phục hồi và vận hành. Nếu việc tách role quá phức tạp làm người vận hành liên tục dùng superuser để sửa lỗi, cần điều chỉnh quy trình provisioning thay vì bỏ nguyên tắc.

---

## 53. Những hiểu nhầm và phản ví dụ

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Ứng dụng cần SELECT nên dùng postgres login.” | Dùng runtime login với quyền SELECT hẹp |
| “Một credential cho mọi service dễ bảo trì nên an toàn.” | Làm blast radius lớn, khó rotate riêng |
| “Migration là ứng dụng nên dùng cùng runtime role.” | Migration cần DDL, runtime chủ yếu DML |
| “Migration phải là SUPERUSER.” | Thường có thể dùng owner/membership được giới hạn |
| “Owner chỉ là role được GRANT ALL.” | Owner có quyền điều khiển đối tượng khác grants |
| “NOLOGIN owner không có quyền.” | Có thể sở hữu và được sử dụng qua SET ROLE |
| “App runtime có membership owner cũng không sao.” | Có thể tạo đường nâng quyền qua SET ROLE |
| “CREATEROLE, CREATEDB, REPLICATION được thừa hưởng như SELECT.” | Role attributes có quy tắc riêng |
| “GRANT ROLE mặc định luôn cho kế thừa mọi thứ.” | Cần xét INHERIT/SET/ADMIN và phiên bản |
| “Application chỉ đọc không cần kiểm tra functions.” | SECURITY DEFINER function có thể ghi |
| “REPLICATION chỉ là quyền SELECT vài bảng.” | Physical WAL có phạm vi rộng |
| “Physical standby cần superuser thật.” | Replication login chuyên biệt có thể đủ |
| “Logical publication có quyền giống table SELECT.” | Publication/subscription có ownership/privileges riêng |
| “Initial logical copy không cần quyền bảng.” | Có thể cần SELECT published tables |
| “Logical replication account là analytics reader.” | Dùng account riêng; BI quyền riêng trên subscriber |
| “Publication all tables chỉ xuất dữ liệu hiện tại.” | Có thể mở phạm vi theo tables mới |
| “RLS bảo vệ dữ liệu trong WAL physical.” | Không giống SELECT qua RLS |
| “Logical row filter là tenant authorization đầy đủ.” | Có giới hạn và cần bảo vệ cả subscriber |
| “BYPASSRLS là cách sửa logical replication lỗi.” | Có thể phá ranh giới dữ liệu |
| “Slot name giới hạn toàn bộ đặc quyền replication role.” | Không phải boundary bảo mật đầy đủ |
| “max_wal_size chắc chắn chặn WAL giữ bởi slot.” | Slot có thể gây retention lớn |
| “Monitor cần REPLICATION để xem lag.” | Có thể dùng monitoring privileges phù hợp |
| “Backup giống SELECT bình thường.” | Physical/logical backup có quyền/scope khác nhau |
| “Schema USAGE tự cấp table SELECT.” | Hai lớp khác |
| “GRANT ALL TABLES không tác động cột nhạy cảm.” | Có thể mở dữ liệu rộng |
| “GRANT UPDATE(stock) cho phép UPDATE mọi cột.” | Chỉ cột được cấp, theo SQL privileges |
| “Reader không có UPDATE tức không thể ghi gián tiếp.” | Cần xem EXECUTE, membership, owner |
| “ALTER DEFAULT PRIVILEGES sửa tables cũ.” | Chỉ objects tạo về sau |
| “Default grants owner áp dụng cho deploy role bất kể creator.” | Phụ thuộc role tạo đối tượng |
| “Schema public luôn cho PUBLIC CREATE.” | Mặc định khác theo phiên bản/upgrade |
| “REVOKE FROM PUBLIC xóa mọi quyền.” | Grants trực tiếp/role memberships vẫn còn |
| “Login password đổi là kết nối cũ lập tức chết.” | Session hiện có có thể tiếp tục |
| “pg_hba hostssl đủ để xác thực server với client.” | Client cũng cần TLS certificate/hostname validation |
| “Dùng allowlist IP là đủ.” | Phải bảo vệ credentials, endpoint, firewall |
| “Managed admin luôn rolsuper=true.” | Provider có thể giới hạn |
| “Test quyền bằng superuser là đủ.” | Superuser có thể vượt policy, cần test role thật |
| “Chỉ có positive tests mới quan trọng.” | Negative tests chứng minh boundary |
| “Restore dữ liệu là restore đúng permissions.” | Owner/ACL/RLS/roles có thể khác |
| “DROP OWNED chỉ dọn một số grants.” | Có thể xóa objects phụ thuộc |
| “Số lượng role càng nhiều càng tốt.” | Phải cân bằng least privilege và khả năng vận hành |
| “Thay grants không cần staging.” | Có thể làm production mất quyền hoặc lộ data |
| “RLS based on arbitrary session variable đủ an toàn.” | Tenant context phải đáng tin |
| “Replication account có thể dùng trong web app cho tiện.” | Không đúng nhiệm vụ, blast radius lớn |

---

## 54. Bài tập thực hành

### Bài 1 — Nhận diện blast radius

Một service catalog kết nối bằng superuser. Liệt kê ít nhất năm hậu quả nếu SQL injection xảy ra; so với khi service chỉ có SELECT trên v_catalog.

### Bài 2 — Role matrix

Tạo bảng ma trận role cho admin, migration, app read, app write, physical replication, logical replication, backup và monitoring. Nêu ai được LOGIN, ai NOLOGIN và những đặc quyền bị cấm.

### Bài 3 — Owner NOLOGIN

Tạo owner NOLOGIN và schema dưới owner đó. Vì sao owner không cần password để phục vụ ứng dụng?

### Bài 4 — Runtime không sở hữu bảng

Tạo table bằng owner role, sau đó GRANT SELECT cho runtime reader. Chứng minh reader không được DROP table.

### Bài 5 — LOGIN vs NOLOGIN

Tạo một role group NOLOGIN và một login role ở môi trường lab. Giải thích vì sao group NOLOGIN vẫn có thể sở hữu đối tượng hoặc được cấp quyền.

### Bài 6 — Membership

GRANT group role cho runtime role, rồi kiểm tra các quyền hiệu lực. Nếu role runtime có membership khác, quyền có cộng dồn không?

### Bài 7 — SET ROLE

Thử chuyển một migration login được phép sang owner, sau đó RESET ROLE. Truy vấn `session_user` và `current_user` trước và sau thao tác.

### Bài 8 — Runtime không SET owner

Thiết kế negative test xác nhận runtime không thể chuyển sang owner role. Nếu test thành công trái ý, phải audit cấu hình nào?

### Bài 9 — PostgreSQL 16 membership options

Giải thích khác biệt giữa ADMIN, INHERIT và SET trong role membership. Vì sao không dùng chỉ `rolinherit` để quyết định mọi đường quyền?

### Bài 10 — Superuser

Vì sao migration tạo table bình thường không cần superuser? Khi nào công việc thực sự cần đặc quyền admin?

### Bài 11 — Role attributes

Viết query liệt kê mọi role có SUPERUSER, CREATEROLE, CREATEDB, REPLICATION hoặc BYPASSRLS. Đâu là dấu hiệu cần kiểm tra nếu thấy runtime role?

### Bài 12 — CREATEDB vs CREATE ON DATABASE

So sánh hai quyền. Vì sao không cấp cả hai cho catalog API?

### Bài 13 — BYPASSRLS

Một API đa tenant dựa vào RLS nhưng login của nó có BYPASSRLS. Nêu đường rò dữ liệu có thể xảy ra.

### Bài 14 — Owner và RLS

Tạo table có RLS trên lab. So sánh đọc bằng table owner và runtime role bị policy giới hạn; thử FORCE RLS nếu có quyền.

### Bài 15 — Schema USAGE

Cấp USAGE ON SCHEMA cho reader nhưng không cấp table SELECT. Giải thích lỗi và cách cấp tối thiểu.

### Bài 16 — Column GRANT

Chỉ cấp SELECT(sku,stock), không cấp unit_cost. Viết positive/negative SELECTs để kiểm tra.

### Bài 17 — Catalog view

Tạo v_catalog công bố sku,display_name,stock và cấp SELECT view. Vì sao vẫn phải kiểm tra grants trên bảng nền?

### Bài 18 — Writer quyền hẹp

Cấp SELECT(sku,stock), UPDATE(stock) cho writer. Thử UPDATE stock trong transaction rồi rollback, sau đó thử UPDATE unit_cost và giải thích lỗi.

### Bài 19 — GRANT ALL là quá rộng

Với inventory worker chỉ sửa stock, liệt kê các quyền bị cấp thừa khi dùng GRANT ALL ON TABLE products.

### Bài 20 — Default privileges

Cấu hình một role owner tạo table mới trong reporting schema được SELECT bởi report_reader. Vì sao các bảng đã tồn tại không tự thay ACL?

### Bài 21 — Creator drift

Migration quên SET ROLE owner và tạo table dưới migration_login. Nêu tác động tới owner, ACL và kỳ vọng của job deploy sau này.

### Bài 22 — GRANT hiện tại vs tương lai

Viết câu lệnh cấp quyền cho các bảng reporting đang tồn tại và default privileges cho bảng sẽ tạo sau, nếu chính sách business cho phép.

### Bài 23 — PUBLIC EXECUTE

Một SECURITY DEFINER function mới được tạo. Cần làm gì với quyền EXECUTE mặc định của PUBLIC?

### Bài 24 — Function quyền gián tiếp

Một role không UPDATE table nhưng có EXECUTE SECURITY DEFINER function làm UPDATE. Role có thực sự “read-only” không?

### Bài 25 — search_path

Mô tả nguy cơ name shadowing trong SECURITY DEFINER. Tại sao cần schema-qualified names và search_path tin cậy?

### Bài 26 — Physical replication

Vì sao physical standby thường cần role có REPLICATION thay vì GRANT SELECT ON ALL TABLES?

### Bài 27 — WAL confidentiality

RLS cho phép API chỉ đọc tenant 10. Physical replication role có bị RLS giới hạn dữ liệu WAL chỉ tenant 10 không? Giải thích.

### Bài 28 — pg_hba physical

Viết một rule `hostssl replication ...` chỉ cho phép standby IP cụ thể. Vì sao không dùng 0.0.0.0/0?

### Bài 29 — TLS và chứng chỉ

Giải thích vì sao hostssl vẫn cần kiểm tra certificate/hostname tại client trong hệ thống cần chống server giả mạo.

### Bài 30 — Replication parameter

Dùng SHOW wal_level, max_wal_senders, max_replication_slots. Nêu vì sao chúng liên quan cấu hình replication nhưng không thay được quyền REPLICATION.

### Bài 31 — Physical backup

Một backup job dùng pg_basebackup có thể cần năng lực nào? Vì sao không dùng web API login?

### Bài 32 — Logical publication

Thiết kế publication công bố hai bảng cho analytics. Vì sao `FOR ALL TABLES` có thể gây mở scope không mong muốn?

### Bài 33 — Logical initial sync

Logical subscriber bắt đầu copy dữ liệu nhưng permission denied trên bảng. Những quyền nào ở publisher cần kiểm tra?

### Bài 34 — Logical vs physical

So sánh hai kiểu replication theo phạm vi dữ liệu, DDL, RLS và role quyền.

### Bài 35 — Subscriber quyền riêng

Vì sao owner/cấu hình subscription trên analytics-db cần được quản lý riêng, không dùng login của HTTP app?

### Bài 36 — Connection string secret

Một migration SQL chứa mật khẩu logical replication. Nêu các đường rò secret có thể xảy ra và cách cải thiện quy trình.

### Bài 37 — Row filter và tenant

Một publication chỉ lọc một số tenant. Tại sao cần kiểm tra initial sync, UPDATE/DELETE, replica identity và bảo vệ subscriber thay vì xem filter là tenant authorization duy nhất?

### Bài 38 — Replication slot retention

Một logical slot không active nhiều ngày. Những dấu hiệu nào cần quan sát và vì sao không thể chỉ dựa vào max_wal_size như hard limit?

### Bài 39 — Không drop slot bừa bãi

Nếu xóa slot khi consumer còn cần WAL cũ, hệ quả có thể là gì? Thiết kế quyết định xử lý incident.

### Bài 40 — Monitoring quyền hẹp

Một dashboard chỉ cần replication lag. Vì sao có thể dùng role monitoring thích hợp thay vì login REPLICATION?

### Bài 41 — pg_stat_replication

Truy vấn application_name/state/sync_state/sent_lsn/write_lsn/flush_lsn/replay_lsn và giải thích ý nghĩa tổng quát từng vị trí.

### Bài 42 — pg_replication_slots

Viết query liệt kê slot_type, active, restart_lsn và confirmed_flush_lsn. Trường nào có thể NULL theo loại slot?

### Bài 43 — Audit pg_roles

Viết script đọc pg_roles và phát hiện runtime login nào có rolsuper/rolbypassrls/rolreplication không mong muốn.

### Bài 44 — Audit membership

Dùng pg_auth_members để liệt kê grants role-to-role; giải thích vì sao membership tới owner có thể nguy hiểm.

### Bài 45 — Permission helper functions

Dùng has_schema_privilege, has_table_privilege và has_column_privilege để chứng minh reader chỉ có quyền cần thiết trong lab.

### Bài 46 — Password rotation

Thiết kế kế hoạch rotate một physical replication credential mà không gây gián đoạn kéo dài cho standby. Cần giám sát chỉ số nào?

### Bài 47 — Existing sessions

Nếu ALTER ROLE app_login NOLOGIN sau khi secret bị lộ, vì sao cần xem các session hiện đang kết nối? Ai được phép terminate?

### Bài 48 — Migration bị lộ

Phân tích blast radius khi credential migration bị chiếm quyền nhưng role chỉ được SET app_owner, không SUPERUSER. Những đối tượng nào vẫn nguy hiểm?

### Bài 49 — Multi-tenant role design

Thiết kế roles cho catalog, billing, support, inventory và analytics. Mỗi service cần quyền nào? Có nên gộp chúng vào một group có SELECT mọi dữ liệu không?

### Bài 50 — RLS tenant context

Một policy dựa vào current_setting('app.tenant_id') do SQL caller tự SET được. Vì sao đây không phải bằng chứng tenant đã được xác thực?

### Bài 51 — Backup/restore ACL

Sau khi restore bằng các tùy chọn không giữ owners/grants, kiểm tra những gì trước khi ứng dụng kết nối trở lại?

### Bài 52 — Offboarding

Một role deploy cũ sở hữu nhiều views và có grants trong nhiều databases. Lập kế hoạch REASSIGN OWNED, DROP OWNED, DROP ROLE an toàn.

### Bài 53 — CI negative tests

Viết danh sách ít nhất 8 thao tác runtime phải bị từ chối: ALTER, DROP, SELECT PII, UPDATE cost, SET ROLE owner, role administration, REPLICATION và đọc cross-tenant.

### Bài 54 — Production architecture

Một nền tảng PostgreSQL có primary, hai physical standbys, logical analytics subscriber, ba microservices, migration CI, monitoring và backup. Vẽ sơ đồ role/login/privileges/secrets/network/TLS và mô tả cách kiểm thử, rotate credentials, phục hồi sau lỗi, kiểm soát schema ownership và ngăn thay đổi privilege drift.

---

## 55. Checklist triển khai tách role

| Câu hỏi | Điều cần xác nhận |
| --- | --- |
| Có ma trận vai trò? | Admin/migration/owner/app/replication/backup/monitor |
| Runtime dùng superuser? | Không |
| Runtime có CREATEROLE/CREATEDB? | Không khi không cần |
| Runtime có REPLICATION? | Không |
| Runtime có BYPASSRLS? | Không trong app đa tenant |
| Owner có NOLOGIN? | Có nếu kiến trúc cho phép |
| Migration và runtime có credentials riêng? | Có |
| Break-glass dùng thường xuyên không? | Không |
| Role membership có mở quyền owner cho runtime? | Không |
| Có xét INHERIT/SET/ADMIN options? | Theo phiên bản |
| Có kiểm tra current_user/session_user? | Có trong tests |
| Application có schema USAGE phù hợp? | Chỉ schemas cần |
| Application có CREATE schema thừa? | Không |
| Có table/column grants chính xác? | Đủ SELECT/INSERT/UPDATE/DELETE cần thiết |
| Có quyền DELETE/TRUNCATE không cần? | Thu hồi |
| Có sequence privileges? | Theo DEFAULT nextval/identity thực tế |
| Có function EXECUTE PUBLIC nhạy cảm? | Không |
| SECURITY DEFINER có review? | Owner, search_path, body, SQL injection, input, grants |
| Có RLS cho tenant data? | Theo policy thiết kế |
| Runtime là table owner? | Không khi RLS cần áp dụng |
| Có owner bypass/FORCE RLS xem xét? | Có |
| Có trusted tenant context? | Có, không do client tùy ý tự nhận |
| View owner/security_invoker đúng? | Có |
| Migration tạo object dưới đúng owner? | SET ROLE/membership kiểm chứng |
| Default privileges gắn đúng creator? | Có |
| Grant cho bảng hiện có vs tương lai? | Được quản lý riêng |
| Schema public grants an toàn? | Kiểm tra theo version/upgrade |
| Có audit role attributes? | pg_roles |
| Có audit memberships? | pg_auth_members |
| Có audit ownership? | pg_namespace/pg_class/pg_proc |
| Có permission checks? | has_*_privilege |
| Có test denied permissions? | Có, từ role runtime thật |
| Physical replication role riêng? | Có |
| Logical replication role riêng? | Có khi dùng |
| Backup account riêng? | Có theo công cụ |
| Monitoring role riêng? | Không cần REPLICATION mặc định |
| HBA physical replication giới hạn IP? | Có |
| HBA logical dùng database thật? | Đúng theo kết nối |
| TLS xác thực client/server phù hợp? | Có |
| Có bảo vệ secrets connection strings? | Không hardcode/log |
| Có kiểm tra initial logical SELECT rights? | Có |
| Publication scope được review? | Bảng/cột/hàng phù hợp |
| Subscriber tables/ACL/owner đúng? | Có |
| RLS và logical apply được test? | Có |
| Replication slots được theo dõi? | active, restart_lsn, retained WAL |
| Có cảnh báo disk/WAL growth? | Có |
| Có kế hoạch rotate replication credentials? | Có, không ngắt HA ngoài dự kiến |
| Có audit backup/WAL archive access? | Có |
| Có test restore với quyền? | Owner, grants, RLS, login |
| Có quy trình offboarding roles? | Reassign/cleanup nhiều databases |
| Có kiểm soát active sessions sau revoke? | Có |
| Có tách secrets dev/staging/prod? | Có |
| Có resource controls cho reader? | Timeouts/pool limits |
| Có migration review/approval? | Có |
| Có monitoring privilege drift? | Có |
| Có kế hoạch incident response? | Cô lập role, rotate, audit, recover |
| Có tài liệu ownership và trách nhiệm? | Người phê duyệt từng role |

---

## 56. Kết luận

**Tách role quản trị, migration, sao chép và ứng dụng** không phải hoạt động “đặt nhiều tên tài khoản cho đẹp”. Đây là cách biến nguyên tắc **quyền tối thiểu** thành những ranh giới có thể kiểm tra và có thể khôi phục khi sự cố xảy ra.

Những nguyên tắc quan trọng nhất:

1. **Quản trị cluster khác quản lý schema.** Superuser/break-glass chỉ dành cho công việc cần đặc quyền cực cao; phần lớn migrations có thể chạy dưới owner role được kiểm soát.
2. **Migration khác runtime.** Một service nhận HTTP requests không nên mang quyền ALTER/DROP hoặc credentials của CI/CD.
3. **Owner NOLOGIN là một lớp phân tách hữu ích.** Nó sở hữu đối tượng, còn login ứng dụng chỉ nhận SELECT/DML cần thiết.
4. **Membership là một đường quyền quan trọng.** Đừng cấp runtime khả năng SET ROLE sang owner; hiểu quy tắc INHERIT/SET/ADMIN theo phiên bản PostgreSQL.
5. **Ứng dụng nên được cấp theo chức năng.** Catalog read, orders write, inventory update và BI cần các phạm vi dữ liệu khác nhau.
6. **Physical replication là một đặc quyền mạnh.** Dữ liệu WAL/base backup có thể bao phủ nhiều database và không bị giới hạn như SELECT của một view.
7. **Logical replication có scope khác nhưng vẫn nhạy cảm.** Publisher, publication, initial copy, subscription, subscriber và RLS cần được đánh giá cùng nhau.
8. **Replication slots ảnh hưởng availability.** Một consumer không tiến có thể giữ WAL; phải có giám sát và quy trình xử lý, không tùy tiện xóa slot.
9. **Backup/monitoring không nên dùng credentials ứng dụng hoặc replication nếu không cần.** Dùng identities riêng theo nhiệm vụ và bộ đặc quyền phù hợp.
10. **Default privileges và creator role quyết định quyền của đối tượng mới.** Kiểm tra mỗi migration để tránh owner drift và grants quá rộng.
11. **RLS/SECURITY DEFINER không thay tách role.** Quyền cao hoặc function được cấp sai có thể vượt qua giới hạn dự kiến.
12. **Kiểm thử những điều bị từ chối quan trọng như kiểm thử điều được phép.** Không chỉ hỏi “API chạy được không?”, mà còn hỏi “API không thể làm những gì?”.
13. **Quyền phải có vòng đời.** Quản lý secrets, TLS, rotate, thu hồi session, audit, backup/restore và offboarding không thể bỏ qua.
14. **Least privilege là trạng thái được duy trì liên tục.** Vai trò, schema, publication, số service và quyền sẽ thay đổi; cần quan sát và kiểm tra drift.

Một kiến trúc PostgreSQL tốt cho phép từng thành phần hoàn thành công việc của mình, nhưng khi một thành phần gặp lỗi hoặc bị chiếm quyền, **nó không tự trở thành công cụ quản trị cluster, triển khai schema hay sao chép toàn bộ dữ liệu**. Đó là giá trị thực tế lớn nhất của việc tách role theo nhiệm vụ.

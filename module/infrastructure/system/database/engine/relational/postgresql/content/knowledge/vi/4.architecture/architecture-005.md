# Database cluster, PGDATA, tablespace và các tệp quan hệ trong PostgreSQL

## 1. Từ bảng SQL đến những tệp trên ổ đĩa

Khi bạn chạy câu lệnh:

```sql
CREATE TABLE public.orders (
    order_id bigint PRIMARY KEY,
    amount numeric(12, 2) NOT NULL
);
```

PostgreSQL tạo một **đối tượng logic** tên `public.orders`. Nhưng dữ liệu của bảng không nằm trong một “tệp `orders.sql`” hay một thư mục có tên `public`. PostgreSQL sử dụng **database cluster**, **thư mục dữ liệu `PGDATA`**, **tablespace**, **relation files** và nhiều loại tệp nội bộ để lưu dữ liệu và phục hồi sau sự cố.

Hãy hình dung hai góc nhìn về cùng một hệ thống.

**Góc nhìn SQL:**

```text
PostgreSQL instance
└── Database cluster
    ├── Database: postgres
    ├── Database: shop_db
    │   ├── Schema: public
    │   │   └── Table: orders
    │   │       ├── Row: order_id = 1001
    │   │       └── Row: order_id = 1002
    │   └── Schema: audit
    │       └── Table: events
    └── Database: analytics_db
        └── Schema: reporting
            └── Table: daily_sales
```

**Góc nhìn vật lý điển hình với tablespace mặc định:**

```text
PGDATA/
├── PG_VERSION
├── base/
│   ├── <OID của shop_db>/
│   │   ├── <relfilenode của bảng orders>
│   │   ├── <relfilenode của index>
│   │   ├── <relfilenode>_fsm
│   │   └── ...
│   └── <OID của analytics_db>/
├── global/
├── pg_tblspc/
├── pg_wal/
├── pg_xact/
├── pg_multixact/
└── ... các tệp và thư mục quản trị khác
```

Các tên như `<OID của shop_db>` và `<relfilenode>` trong sơ đồ là **ký hiệu mô tả**, không phải tên file thật. Trên đĩa, PostgreSQL thường dùng các số định danh và một cấu trúc thư mục nội bộ. Không nên tự sửa hoặc đổi tên những file này.

Bài học sẽ giải đáp năm câu hỏi:

1. **Database cluster** là gì và khác một cụm PostgreSQL nhiều máy như thế nào?
2. **`PGDATA`** chứa những gì và tại sao nó quan trọng?
3. **Tablespace** quyết định vị trí lưu trữ của đối tượng ra sao?
4. **Relation files** biểu diễn bảng, chỉ mục, TOAST và các fork/segment như thế nào?
5. Làm sao quan sát kiến trúc lưu trữ bằng **SQL an toàn**, không chỉnh sửa file nội bộ?

## 2. Database cluster: một tập database được quản lý chung

### 2.1. Ý nghĩa kỹ thuật của “database cluster”

Trong thuật ngữ PostgreSQL, **database cluster** là **tập các database do một PostgreSQL server instance quản lý**. Một cluster bao gồm dữ liệu của các database, các catalog dùng chung và trạng thái cần thiết để máy chủ hoạt động.

Ví dụ:

```text
Một PostgreSQL database cluster
├── Role: application_login
├── Role: readonly_user
├── Tablespace: pg_default
├── Tablespace: pg_global
├── Database: postgres
├── Database: shop_db
└── Database: reporting_db
```

Điểm cần nhớ:

- Một cluster chứa **nhiều database**.
- Mỗi database chứa **nhiều schema** và đối tượng.
- **Role** và thông tin về tablespace là những khái niệm có phạm vi **cluster**, không phải một schema riêng.
- PostgreSQL server instance mở và quản lý **một data directory/cluster** để phục vụ các kết nối.
- Một máy vật lý hoặc VM có thể chạy **nhiều instance PostgreSQL độc lập**, nếu mỗi instance có data directory và cấu hình tài nguyên phù hợp.

Cluster thường được **khởi tạo** bằng công cụ hệ thống `initdb`, không phải bằng `CREATE DATABASE`.

```sh
# Minh họa lệnh khởi tạo một cluster MỚI trong môi trường test.
# Chỉ chạy nếu đường dẫn chưa chứa dữ liệu và đã có quyền phù hợp.
initdb -D /path/to/new/pgdata
```

Lệnh này tạo cấu trúc ban đầu cho data directory. Nó không phải thao tác cần lặp lại mỗi khi ứng dụng muốn thêm database.

Ngược lại:

```sql
CREATE DATABASE shop_db;
```

tạo **một database bên trong cluster hiện tại**. Nó không khởi tạo một database cluster hoặc instance mới.

### 2.2. Cluster dữ liệu không đồng nghĩa HA cluster

Cụm từ “PostgreSQL cluster” có hai cách dùng phổ biến:

| Thuật ngữ | Bản chất | Có bắt buộc nhiều máy không? |
|---|---|---|
| **Database cluster theo `initdb`** | Tập database và dữ liệu do một PostgreSQL instance quản lý | **Không** |
| **HA cluster / primary–standby topology** | Nhiều PostgreSQL instances phối hợp để tăng khả năng sẵn sàng | Thường có nhiều instance/node |
| **Replication setup** | Cơ chế truyền/áp dụng thay đổi giữa các PostgreSQL instances | Có nhiều instance, nhưng không nhất thiết tự có failover |
| **Cluster orchestrator** | Thành phần quản lý chọn primary, failover, fencing… | Tùy giải pháp |

Một laptop cài PostgreSQL và chỉ có database `postgres` vẫn có **database cluster** theo thuật ngữ kỹ thuật. Nó không tự có failover hay bản sao dự phòng.

Trong hệ thống streaming replication, mỗi standby có **data directory riêng** và đồng bộ thay đổi theo cơ chế PostgreSQL; không đặt hai instance đang chạy cùng ghi vào một `PGDATA`. Việc một primary và một standby có dữ liệu tương ứng **không biến hai data directory thành một thư mục dùng chung**.

### 2.3. Những đối tượng nào thuộc cluster, đối tượng nào thuộc database?

| Đối tượng | Phạm vi chính |
|---|---|
| Danh sách role, role membership | Cluster |
| Danh sách database | Cluster |
| Danh sách tablespace | Cluster |
| Schema như `public`, `sales` | Một database |
| Bảng như `sales.orders` | Một schema trong một database |
| Index, sequence, view | Thuộc database và schema tương ứng |
| Các hàng của bảng | Bảng cụ thể |
| WAL của instance | Cơ chế lưu trữ/khôi phục của toàn instance, không phải một bảng duy nhất |

Ranh giới này giải thích vì sao cùng một role có thể kết nối nhiều database nhưng câu `SELECT` bình thường chỉ hoạt động trong **database mà session đang kết nối**.

## 3. `PGDATA` là gì?

### 3.1. `PGDATA` và `data_directory`

**`PGDATA`** thường được dùng để chỉ **data directory** của PostgreSQL: thư mục gốc chứa dữ liệu của database cluster và những file hệ thống cần thiết để instance vận hành.

Trong một số cách cài đặt, `PGDATA` là **biến môi trường** chỉ đến data directory:

```sh
# Ví dụ biến môi trường trên một hệ thống tự quản lý:
PGDATA=/var/lib/postgresql/data
```

Đây chỉ là ví dụ đường dẫn. Không phải mọi hệ điều hành, bản phân phối hay container đều có cùng đường dẫn, và biến môi trường của terminal người dùng **không chứng minh** server đang sử dụng thư mục đó.

PostgreSQL cũng có thông số cấu hình `data_directory` và có thể nhận đường dẫn khi khởi chạy (ví dụ tham số `-D`). Tùy hệ thống đóng gói, các file cấu hình còn có thể được đặt **ngoài data directory**.

Để xem data directory thực tế của **server đang kết nối**, một quản trị viên hoặc role có quyền đọc thông số phù hợp có thể chạy:

```sql
SHOW data_directory;
```

Thông số này có thể bị giới hạn với tài khoản thông thường; không nên cấp quyền quản trị rộng chỉ để xem đường dẫn vật lý. Trong hệ thống managed PostgreSQL, người dùng thậm chí có thể **không được phép** truy cập trực tiếp filesystem.

### 3.2. Vì sao PGDATA quan trọng?

`PGDATA` là một thành phần cốt lõi vì nó chứa, hoặc tham chiếu tới, những dữ liệu và metadata mà PostgreSQL cần để:

- Nhận biết phiên bản và cấu trúc cluster.
- Tìm dữ liệu các database trong tablespace mặc định.
- Truy cập catalog hệ thống dùng chung.
- Duy trì các transaction và phục hồi sau crash bằng WAL.
- Theo dõi trạng thái transaction, thông tin replication và những thành phần nội bộ khác.

**Không được coi PGDATA như thư mục tài liệu ứng dụng có thể tùy ý copy/xóa từng file.** PostgreSQL duy trì mối quan hệ phức tạp giữa dữ liệu, catalog, transaction status, WAL và các tệp quan hệ. Việc sửa một file lẻ khi server đang chạy có thể làm hỏng tính nhất quán dữ liệu.

### 3.3. Bản đồ những thư mục quan trọng trong PGDATA

Cấu trúc thực tế có thể thay đổi theo phiên bản, cấu hình và gói cài đặt. Các tên thường gặp:

| Đường dẫn trong PGDATA | Vai trò |
|---|---|
| `PG_VERSION` | Ghi thông tin phiên bản chính của cấu trúc cluster |
| `base/` | Dữ liệu các database trong **tablespace mặc định** `pg_default` |
| `global/` | Một số shared system catalogs và dữ liệu dùng chung toàn cluster |
| `pg_tblspc/` | Các liên kết từ cluster tới vị trí của **tablespace do người dùng tạo** |
| `pg_wal/` | Write-Ahead Log phục vụ durability/crash recovery và replication/PITR |
| `pg_xact/` | Thông tin trạng thái commit/abort của transaction |
| `pg_multixact/` | Thông tin phục vụ các transaction IDs phối hợp cho một số khóa/quan hệ đồng thời |
| `pg_subtrans/` | Metadata về subtransaction |
| `pg_twophase/` | Dữ liệu phục vụ prepared transactions/two-phase commit khi sử dụng |
| `pg_replslot/` | Trạng thái replication slots |
| `pg_logical/` | Metadata liên quan logical decoding/replication |
| `pg_stat/` | Một số thông tin thống kê bền vững theo cơ chế của phiên bản |
| `postgresql.auto.conf` | Các giá trị cấu hình được lưu qua cơ chế như `ALTER SYSTEM` |
| `postmaster.pid` | Thông tin quản lý instance đang chạy, thường tồn tại khi server hoạt động |

**Đừng xem bảng này là danh sách phải có mọi thư mục trên mọi phiên bản.** PostgreSQL có thể thêm, đổi hoặc bỏ những thư mục nội bộ qua các phiên bản; vị trí cấu hình/log và phần dữ liệu có thể tùy thuộc cách đóng gói.

Ví dụ các bản cài đặt Linux theo distro có thể đặt `postgresql.conf` và `pg_hba.conf` ở vị trí quản lý cấu hình riêng, thay vì bắt buộc nằm cùng PGDATA. Cách xác minh đáng tin cậy là thông số của instance và quy trình đóng gói nó đang dùng.

### 3.4. `base/` và `global/` khác nhau thế nào?

**`base/`** chứa các thư mục theo **OID của database** đối với những database sử dụng tablespace mặc định.

Ví dụ minh họa:

```text
PGDATA/base/
├── 1/
├── 4/
├── 5/
└── 16384/
    ├── 16390
    ├── 16391
    ├── 16391_fsm
    └── 16391_vm
```

Các số trên chỉ minh họa. `16384` trong đường dẫn có thể là OID của database; những tên số ở bên trong là **file identifiers của relations**, không phải mã hàng của bảng.

**`global/`** chứa các quan hệ và catalog được chia sẻ ở cấp cluster, ví dụ thông tin liên quan đến database/roles theo tổ chức lưu trữ PostgreSQL. Không có nghĩa mọi system catalog nằm trong `global/`; nhiều catalog khác thuộc từng database và nằm trong vị trí lưu trữ của database đó.

## 4. Database OID: cầu nối giữa tên database và thư mục lưu trữ

### 4.1. OID là gì?

PostgreSQL gán **Object Identifier (OID)** cho nhiều đối tượng nội bộ. Một database có **OID** trong catalog `pg_database`.

Ví dụ truy vấn an toàn:

```sql
SELECT
    oid AS database_oid,
    datname AS database_name,
    pg_get_userbyid(datdba) AS owner_name
FROM pg_database
ORDER BY datname;
```

Nếu database `shop_db` có OID 16384 và sử dụng tablespace `pg_default`, dữ liệu relation của nó thường nằm dưới đường dẫn tương đối:

```text
base/16384/
```

Không nên đoán OID theo tên database, cũng không được coi một OID ví dụ là số cố định trên mọi máy.

### 4.2. Xem OID của database đang kết nối

```sql
SELECT
    current_database() AS database_name,
    d.oid AS database_oid
FROM pg_database AS d
WHERE d.datname = current_database();
```

Điều này giúp nối thông tin **logic** từ SQL tới thư mục của database trong tablespace mặc định.

Tuy nhiên, không phải mọi relation của database đều nằm trong `base/<database_oid>`: nếu table hoặc index được đặt ở **tablespace riêng**, tệp có thể nằm ngoài PGDATA và được tham chiếu qua `pg_tblspc`.

### 4.3. Database name khác schema name và file name

Giả sử:

```text
Database: shop_db
Schema: sales
Table: orders
```

Từ góc nhìn SQL, tên đầy đủ của bảng trong database đang kết nối là:

```sql
SELECT * FROM sales.orders;
```

Nhưng dưới filesystem thường không có đường dẫn kiểu:

```text
PGDATA/shop_db/sales/orders.csv
```

Thay vào đó, hệ thống dùng database OID, tablespace và **relfilenode** để tra vị trí file. Schema là namespace logic được quản lý bằng catalog; nó không tự tương ứng với một thư mục vật lý có cùng tên.

## 5. Tablespace: lựa chọn vị trí lưu trữ vật lý cho đối tượng

### 5.1. Tablespace là gì?

**Tablespace** cho phép PostgreSQL đặt các đối tượng relation tại một **vị trí lưu trữ** do hệ thống quản lý. Nó không phải database mới, không phải schema mới và không phải một máy chủ PostgreSQL mới.

Ví dụ:

```text
PostgreSQL instance / PGDATA
├── pg_default  -> PGDATA/base/
├── pg_global   -> PGDATA/global/
└── tablespace do admin tạo
    └── fast_ts -> /srv/postgres/tablespaces/fast_ts/
```

Các đường dẫn ở đây chỉ minh họa. Hai tablespace mặc định thường gặp:

- **`pg_default`**: nơi lưu các đối tượng người dùng nếu không chọn vị trí khác, tương ứng vùng `base/`.
- **`pg_global`**: dành cho một số đối tượng lưu trữ dùng chung toàn cluster, tương ứng `global/`.

Một tablespace do quản trị viên tạo có thể nằm trên volume/đĩa khác để phục vụ yêu cầu dung lượng, quản trị hoặc hiệu năng của môi trường tự quản lý.

### 5.2. Liệt kê tablespace bằng SQL

```sql
SELECT
    oid AS tablespace_oid,
    spcname AS tablespace_name,
    pg_get_userbyid(spcowner) AS owner_name
FROM pg_tablespace
ORDER BY spcname;
```

Trong `psql`, có thể dùng meta-command:

```text
\db
```

`\db` thuộc riêng `psql`; nó không phải lệnh SQL chạy qua driver JDBC.

Để tìm tablespace mặc định của **database hiện tại**:

```sql
SELECT
    d.datname AS database_name,
    t.spcname AS default_tablespace
FROM pg_database AS d
JOIN pg_tablespace AS t
  ON t.oid = d.dattablespace
WHERE d.datname = current_database();
```

Với database thông thường chưa tùy chỉnh, `default_tablespace` sẽ là `pg_default`.

### 5.3. Vị trí thực tế của tablespace tùy chỉnh

Trên hệ thống PostgreSQL tự quản lý dùng POSIX filesystem, khi tạo một tablespace ở đường dẫn ngoài PGDATA, PostgreSQL thường tạo một **symbolic link** trong `PGDATA/pg_tblspc/` tới vị trí ngoài đó.

Sơ đồ:

```text
PGDATA/
└── pg_tblspc/
    └── 24576   -> /srv/postgres/tablespaces/fast_ts

/srv/postgres/tablespaces/fast_ts/
└── PG_<version>_<catalog_version>/
    └── <database_oid>/
        ├── <relfilenode>
        ├── <relfilenode>_fsm
        └── ...
```

Trong Windows, cơ chế filesystem link/junction có chi tiết triển khai khác. Thành phần `PG_<version>_<catalog_version>` là cấu trúc nội bộ có định dạng tùy **phiên bản PostgreSQL**, không phải một thư mục có tên bất biến cần hard-code trong ứng dụng.

Có thể tra đường dẫn tablespace bằng hàm:

```sql
SELECT
    spcname,
    pg_tablespace_location(oid) AS location
FROM pg_tablespace
ORDER BY spcname;
```

Đối với tablespace dựng sẵn như `pg_default` hoặc `pg_global`, trường location có thể là chuỗi rỗng theo cách hàm biểu diễn đối tượng nội bộ; không có nghĩa tablespace không chứa dữ liệu.

### 5.4. Tạo tablespace cần quyền quản trị và thư mục hợp lệ

Ví dụ **chỉ dành cho người quản trị của một instance test tự quản lý**:

```sql
CREATE TABLESPACE fast_ts
LOCATION '/srv/postgres/tablespaces/fast_ts';
```

Để thao tác hợp lệ, về nguyên tắc:

1. Đường dẫn trên máy PostgreSQL server phải tồn tại trước.
2. Directory phải phù hợp điều kiện trống, ownership và permission mà PostgreSQL yêu cầu; thường nó được tạo bằng quyền của hệ điều hành và sở hữu bởi user chạy PostgreSQL.
3. Role thực hiện `CREATE TABLESPACE` cần quyền **superuser** trong PostgreSQL thông thường.
4. Tablespace phải nằm trong vị trí lưu trữ có độ bền, quyền và khả năng backup phù hợp.
5. Lệnh `CREATE TABLESPACE` phải được thực thi theo quy tắc transaction của PostgreSQL, không bọc trong `BEGIN ... COMMIT`.

**Không chạy đoạn ví dụ này trên production hoặc copy nguyên đường dẫn nếu chưa được quản trị viên phê duyệt.** Với managed PostgreSQL, khả năng tạo tablespace tùy chỉnh có thể bị hạn chế hoàn toàn.

Có thể cấp quyền tạo object trong tablespace cho role khác nếu thiết kế yêu cầu:

```sql
-- Ví dụ sau khi fast_ts đã tồn tại; chạy bởi role có quyền cấp.
GRANT CREATE ON TABLESPACE fast_ts TO app_owner;
```

Điều này cho phép đối tượng sử dụng tablespace trong phạm vi phù hợp nhưng **không cấp superuser** cho role `app_owner`. Role vẫn cần quyền trên schema/database để tạo relation.

### 5.5. Chọn tablespace khi tạo bảng hoặc chỉ mục

Giả sử tablespace `fast_ts` đã được admin chuẩn bị trong lab, role thực thi có đủ quyền:

```sql
CREATE TABLE storage_lab.archive_events (
    event_id bigint PRIMARY KEY,
    payload text NOT NULL
) TABLESPACE fast_ts;
```

Bảng `archive_events` vẫn nằm trong **schema `storage_lab` của database hiện tại**, chỉ có nơi lưu dữ liệu relation được chỉ định bằng tablespace. Không cần chuyển database để truy vấn:

```sql
SELECT *
FROM storage_lab.archive_events;
```

Index có thể được chỉ định tablespace riêng:

```sql
CREATE INDEX idx_archive_events_payload_prefix
ON storage_lab.archive_events ((left(payload, 20)))
TABLESPACE fast_ts;
```

Đây là ví dụ thiết lập vị trí lưu trữ. **Không nên tạo một index trên `left(payload,20)` chỉ để học tablespace rồi giữ nó trong ứng dụng** nếu không có truy vấn cần dùng.

### 5.6. Tablespace không phải công cụ phân quyền dữ liệu

Một bảng ở `fast_ts` vẫn được bảo vệ bởi quyền `SELECT/INSERT/UPDATE/DELETE`, ownership và các chính sách khác như bảng ở `pg_default`. Việc đặt ở đĩa khác **không tự làm dữ liệu được mã hóa**, tách tenant về bảo mật hay cách ly transaction.

Tablespace cũng không tự làm truy vấn nhanh hơn. Hiệu năng phụ thuộc thiết bị lưu trữ, workload, chỉ mục, cache, latency, concurrency và cả việc đặt WAL/index/data. Nếu các tablespace cùng nằm trên một thiết bị vật lý, lợi ích tách I/O có thể rất hạn chế.

## 6. Relation: khái niệm nằm giữa bảng SQL và tệp vật lý

### 6.1. “Relation” không đồng nghĩa “một file = một bảng”

PostgreSQL dùng thuật ngữ **relation** cho nhiều đối tượng được quản lý qua hệ thống catalog, gồm:

- Ordinary tables.
- Indexes.
- Materialized views.
- Sequences và một số đối tượng vật lý khác.
- Partitioned tables và partitioned indexes dưới dạng đối tượng quản lý logic.
- Views/foreign tables ở mức metadata, dù không có local heap giống bảng thường.

Trong catalog `pg_class`, các quan hệ có `relkind` để phân biệt loại. Một bảng thông thường có thể có:

- **Một relation heap** chứa dữ liệu hàng.
- **Một hoặc nhiều relation index** chứa cấu trúc chỉ mục.
- **Một TOAST relation** và các index tương ứng nếu bảng cần cơ chế lưu giá trị lớn.
- Các **forks** và **segments** thuộc những relation đó.

Vì vậy, nếu tạo một bảng có primary key và vài index, PostgreSQL thường có **nhiều tệp vật lý**, không phải đúng một file có tên bảng.

### 6.2. OID của relation và `relfilenode`

Mỗi relation có danh tính trong catalog, thường thể hiện bằng **OID** của nó. Khi relation có lưu trữ vật lý, PostgreSQL còn xác định **filenode**: một số giúp định vị các tệp chứa dữ liệu của relation.

Hai số này phục vụ mục đích khác nhau:

| Thuộc tính | Vai trò |
|---|---|
| Relation OID | Định danh đối tượng trong catalog |
| `relfilenode`/file node | Định danh vùng tệp lưu trữ vật lý của relation khi áp dụng |
| Database OID | Xác định database, thường xuất hiện ở một cấp thư mục |
| Tablespace OID | Xác định vùng lưu trữ/tablespace |
| Schema name | Tên logic, không trực tiếp thành thư mục vật lý |
| Table name | Tên logic, không trực tiếp thành tên file |

Một relation có thể **giữ OID logic** nhưng được PostgreSQL gán **filenode mới** sau một thao tác rewrite dữ liệu như `VACUUM FULL`, `CLUSTER` hoặc một số biến đổi cấu trúc. Vì thế, không lưu relfilenode vào cấu hình ứng dụng như định danh ổn định của bảng.

Một số system catalogs còn dùng **relation mapping** thay vì lưu tên filenode thông thường trực tiếp trong `pg_class.relfilenode`. Để tìm đường dẫn thực tế, các **hàm PostgreSQL hỗ trợ** đáng tin cậy hơn việc tự ghép số từ catalog.

### 6.3. Quan sát relation bằng SQL

Sau khi đã tạo bảng `storage_lab.orders` ở phần thực hành, có thể chạy:

```sql
SELECT
    c.oid AS relation_oid,
    c.relname,
    c.relkind,
    c.relfilenode,
    c.reltablespace
FROM pg_class AS c
WHERE c.oid = 'storage_lab.orders'::regclass;
```

Với nhiều ordinary tables, `relfilenode` có giá trị khác 0. Nếu `reltablespace = 0`, điều đó thường nghĩa là relation dùng **tablespace mặc định của database**, không phải một tablespace tên “0”.

Hàm tìm đường dẫn của relation:

```sql
SELECT
    pg_relation_filenode('storage_lab.orders'::regclass)
        AS physical_filenode,
    pg_relation_filepath('storage_lab.orders'::regclass)
        AS relative_relation_path;
```

Đường dẫn từ `pg_relation_filepath()` là **đường dẫn tương đối theo data directory** trong cách PostgreSQL mô tả lưu trữ. Ví dụ:

```text
base/16384/16410
```

Đối với relation lưu trong tablespace tùy chỉnh, đường dẫn thường bắt đầu bằng `pg_tblspc/...`. Đây là thông tin dành cho quan sát/chẩn đoán, **không phải gợi ý mở file đó và chỉnh bằng editor**.

### 6.4. Không phải relation nào cũng có file local

Một **view** thông thường lưu định nghĩa truy vấn, không sở hữu heap chứa các hàng kết quả. Một **foreign table** lấy dữ liệu qua foreign data wrapper, không nhất thiết có local relation storage giống ordinary table. Một **partitioned table parent** là đối tượng định nghĩa phân vùng và thường không có heap storage riêng; từng partition mang dữ liệu vật lý của chính nó.

Do đó, `pg_relation_filepath()` có thể trả `NULL` cho đối tượng không có storage vật lý phù hợp. Không được kết luận lỗi filesystem chỉ vì hàm này trả `NULL` cho một view hoặc partitioned parent.

## 7. Tên tệp quan hệ: main fork, FSM, VM và init fork

### 7.1. Main fork: tệp chứa dữ liệu chính

Một ordinary table có **main fork**, nơi lưu các trang heap của bảng. Giả sử file node có số `16410`, bạn có thể thấy:

```text
16410
```

Đó là main fork segment đầu tiên. Chỉ số này là ví dụ, không phải tên file cố định.

Index cũng có main fork riêng. Nếu bảng `orders` có khóa chính và index trên trạng thái, có thể tồn tại các relation files riêng cho:

```text
Heap của orders       -> relfilenode A
Primary key index     -> relfilenode B
Status/date index     -> relfilenode C
```

Các tệp này có thể ở cùng hoặc khác tablespace tùy cấu hình. Việc query một bảng có thể cần đọc cả index và heap, hoặc đủ dữ liệu từ index trong một số kế hoạch.

### 7.2. Free Space Map (FSM)

**FSM fork** chứa thông tin hỗ trợ PostgreSQL biết trang nào có khoảng trống khả dụng để thêm tuple.

Ví dụ tên file:

```text
16410_fsm
```

Ý nghĩa:

- PostgreSQL có thể tận dụng những trang còn khoảng trống khi thêm/cập nhật dữ liệu.
- FSM là metadata phục vụ quản lý không gian, **không phải file chứa các hàng nghiệp vụ thay thế main fork**.
- Sự có mặt và kích thước của FSM tùy tình trạng relation; không phải relation nào vừa tạo cũng có ngay file FSM khác 0 bytes.

### 7.3. Visibility Map (VM)

**VM fork** theo dõi thông tin ở mức trang, gồm những dấu hiệu như **all-visible** và **all-frozen** hỗ trợ một số tối ưu:

- **Index-only scan** có thể giảm nhu cầu kiểm tra heap khi trang được đánh dấu all-visible thích hợp.
- **VACUUM** sử dụng visibility map trong việc xác định trang nào cần xử lý.
- Thông tin all-frozen giúp tối ưu một số công việc liên quan đến transaction ID và vacuum.

Ví dụ file:

```text
16410_vm
```

VM không chứa kết quả `SELECT` đã được tính sẵn. Nó là metadata cho khả năng nhìn thấy các phiên bản tuple theo cơ chế MVCC. Dấu hiệu all-visible có thể được cập nhật/loại bỏ khi trang có thay đổi; không phải thuộc tính vĩnh viễn của dữ liệu.

### 7.4. Initialization fork cho unlogged relation

Một số **unlogged relations** có thể có **init fork**, thường biểu diễn qua hậu tố:

```text
16410_init
```

Fork này giúp PostgreSQL thiết lập lại nội dung của unlogged relation sau các tình huống crash recovery theo cơ chế của nó.

Không nên suy luận rằng tất cả bảng đều có `_init`. Những bảng **logged** thông thường không dùng init fork theo cùng cách.

**UNLOGGED table** bỏ qua một phần việc ghi WAL cho thay đổi dữ liệu để giảm overhead, nhưng có đánh đổi rất lớn: dữ liệu unlogged table không có cùng bảo đảm crash durability và không được truyền như dữ liệu bảng thông thường qua physical WAL streaming replication. Đừng chọn unlogged chỉ để “đọc/ghi nhanh hơn” mà bỏ qua yêu cầu dữ liệu.

### 7.5. Tổng hợp các fork

| Fork | Hậu tố tệp | Vai trò |
|---|---|---|
| **Main** | Không có hậu tố | Trang dữ liệu chính của heap hoặc index |
| **FSM** | `_fsm` | Theo dõi khoảng trống của trang |
| **VM** | `_vm` | Thông tin all-visible/all-frozen, hữu ích cho vacuum và index-only scan |
| **Init** | `_init` | Hỗ trợ khởi tạo lại unlogged relation theo cơ chế PostgreSQL |

Không phải mọi loại relation đều sử dụng đủ cả bốn fork. Việc có/không có file phụ thuộc loại đối tượng và trạng thái hoạt động của nó.

## 8. Relation segments: vì sao một bảng lớn có nhiều tệp?

PostgreSQL chia storage của một relation thành **segments**. Trong bản build thông dụng, mỗi segment có kích thước tối đa khoảng **1 GiB**. Kích thước này có thể khác nếu PostgreSQL được biên dịch với cấu hình khác.

Ví dụ main fork của một relation lớn:

```text
16410          -- segment đầu tiên
16410.1        -- segment tiếp theo
16410.2        -- segment tiếp theo nữa
```

Các fork phụ cũng có thể chia segment với cách đặt tên chứa hậu tố fork và segment phù hợp, ví dụ:

```text
16410_fsm
16410_fsm.1
16410_vm
```

Không nên hiểu:

- `16410.1` là một **bảng mới**.
- `16410.1` là **dòng số 1** của bảng.
- Số trong tên file chính là giá trị primary key.
- Một table luôn có đúng một file trên đĩa.

Tất cả segment của cùng một fork là các phần của **một relation storage**.

### 8.1. Page/block là đơn vị bên trong tệp

PostgreSQL chia tệp quan hệ thành **pages**, còn gọi **blocks**. Kích thước page mặc định rất thường gặp là **8 KiB**, nhưng đó là giá trị phụ thuộc cấu hình build PostgreSQL, không phải một hằng số đúng cho mọi bản build.

Sơ đồ:

```text
Relation main fork
├── Segment 0: 16410
│   ├── Page 0
│   ├── Page 1
│   ├── Page 2
│   └── ...
├── Segment 1: 16410.1
│   ├── Page ...
│   └── ...
└── Segment 2: 16410.2
    └── ...
```

Trong heap page có phần header, các line pointers/item identifiers, dữ liệu tuple và vùng trống. PostgreSQL quản lý các page theo cấu trúc của engine; ứng dụng không nên giả định có thể mở một page bất kỳ như văn bản hoặc CSV.

### 8.2. Row không tương đương một tệp

Ở mức SQL, một **row** là bản ghi logic. Ở mức lưu trữ, PostgreSQL dùng các **tuple versions** trong heap và cơ chế **MVCC**.

Ví dụ:

```sql
UPDATE storage_lab.orders
SET status = 'PAID'
WHERE order_no = 'ARCH58-001';
```

Sau một `UPDATE`, PostgreSQL có thể tạo tuple version mới và để phiên bản cũ tồn tại một thời gian để phục vụ các transaction đang đọc snapshot cũ. Một row logic có thể được biểu diễn bởi nhiều phiên bản vật lý trong một giai đoạn.

Vì vậy:

- Đếm file trong một thư mục **không** cho biết số row.
- Kích thước relation **không** bằng tổng độ dài các giá trị hiện tại.
- Tuple version, page overhead, free space, index và TOAST đều ảnh hưởng dung lượng.
- `ctid` là vị trí vật lý của một tuple version; nó **không** phải khóa chính bền vững cho ứng dụng.

## 9. TOAST: các giá trị lớn được lưu như thế nào?

### 9.1. Tại sao cần TOAST?

Một hàng có thể chứa giá trị `text`, `jsonb` hoặc các kiểu dữ liệu lớn hơn dung lượng thuận tiện trong một heap page. PostgreSQL có cơ chế **TOAST** (*The Oversized-Attribute Storage Technique*) để nén và/hoặc di chuyển các giá trị lớn ra khỏi hàng chính khi cần và khi kiểu dữ liệu/cấu hình hỗ trợ.

Ví dụ bảng:

```sql
CREATE TABLE storage_lab.documents (
    document_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    body text NOT NULL
);
```

Nếu `body` có nội dung dài, PostgreSQL có thể:

1. Lưu giá trị trực tiếp trong heap row nếu phù hợp.
2. Nén giá trị theo thuật toán/cấu hình được hỗ trợ.
3. Lưu phần lớn giá trị trong **TOAST table** của relation rồi giữ thông tin tham chiếu cần thiết ở hàng chính.

TOAST không nhất thiết được kích hoạt cho mọi giá trị `text`; chuỗi ngắn thường nằm trực tiếp trong heap. Chuỗi dài nhưng nén tốt cũng có thể được xử lý khác chuỗi dài khó nén.

### 9.2. TOAST table cũng có các tệp quan hệ

Một ordinary table có thể liên kết với **TOAST relation** trong schema hệ thống `pg_toast`, và TOAST relation có index để định vị các mảnh giá trị.

Sơ đồ:

```text
storage_lab.documents
    ├── Heap relation
    │      └── body có thể chứa inline data hoặc reference
    ├── Index relation (PRIMARY KEY)
    └── TOAST relation nếu cần
           ├── TOAST heap
           └── TOAST index
```

Có thể quan sát liên kết TOAST trong catalog:

```sql
SELECT
    c.oid::regclass AS table_name,
    c.reltoastrelid,
    CASE
        WHEN c.reltoastrelid <> 0
        THEN c.reltoastrelid::regclass::text
        ELSE NULL
    END AS toast_relation
FROM pg_class AS c
WHERE c.oid = 'storage_lab.documents'::regclass;
```

`reltoastrelid` khác 0 cho biết relation có liên kết tới TOAST table. Điều đó **không chứng minh** bảng hiện tại đang chứa giá trị đã được chuyển ra TOAST; PostgreSQL có thể tạo hạ tầng TOAST trước khi xuất hiện giá trị đủ lớn.

**Không truy cập hoặc sửa trực tiếp file TOAST** để thay nội dung `text`. Các câu `INSERT`, `UPDATE` và `SELECT` thông thường sẽ để PostgreSQL quản lý cơ chế đó.

### 9.3. Vì sao kích thước table có thể lớn hơn heap main?

Nếu bảng có nhiều giá trị dài, tổng dung lượng bảng có thể bao gồm:

- Heap main fork.
- Các fork phụ của heap.
- TOAST heap và các fork liên quan.
- TOAST index.
- Index thông thường của bảng, nếu tính tổng dung lượng toàn bộ.

Điều này dẫn tới khác biệt giữa các hàm `pg_relation_size`, `pg_table_size` và `pg_total_relation_size` ở phần sau.

## 10. WAL và vai trò của `pg_wal/` trong kiến trúc

### 10.1. WAL khác relation file

**WAL (Write-Ahead Logging)** là cơ chế quan trọng để PostgreSQL phục hồi transaction và thay đổi dữ liệu sau crash. Khi chỉnh sửa các trang dữ liệu, PostgreSQL ghi những thông tin cần thiết vào WAL theo quy tắc write-ahead trước khi các trang dữ liệu bẩn có thể được ghi an toàn xuống nơi lưu trữ.

Nói đơn giản:

```text
Transaction thay đổi dữ liệu
     |
     +--> WAL records -> pg_wal / WAL storage
     |
     +--> Trang heap/index được cập nhật trong buffer
                          |
                          v
                    Trang bẩn được ghi xuống data files
```

WAL **không phải** file của một bảng cụ thể. Nó phục vụ nhiều quan hệ, nhiều database trong cùng instance theo cơ chế lưu trữ PostgreSQL.

Trong một số hệ thống, WAL có thể được đặt trên volume riêng bằng cách cấu hình phù hợp; đường dẫn `PGDATA/pg_wal` vẫn là một phần của cấu trúc cluster, nhưng vị trí lưu trữ vật lý có thể được cấu hình khác với heap/index.

### 10.2. WAL giúp làm gì?

- **Crash recovery:** áp dụng thông tin cần thiết để phục hồi trạng thái nhất quán khi server khởi động lại sau lỗi.
- **Physical streaming replication:** truyền WAL tới standby để replay các thay đổi trên các trang dữ liệu.
- **Point-in-time recovery (PITR):** kết hợp base backup nhất quán và WAL được lưu trữ đầy đủ để khôi phục đến một mốc.
- **Một số cơ chế logical decoding/replication:** khai thác thông tin WAL theo cấu hình phù hợp.

Điều quan trọng: **WAL không tự thay thế base backup**. Nếu mất dữ liệu gốc hoặc thiếu WAL cần thiết, việc khôi phục có thể không hoàn tất. Tương tự, chỉ giữ lại một bản sao của riêng thư mục `pg_wal` không đủ để tái tạo toàn bộ database.

### 10.3. Không dùng pg_wal như nơi lưu file người dùng

Không tự tạo file ứng dụng trong `PGDATA/pg_wal`, không xóa WAL segment bằng tay để “giải phóng ổ đĩa” và không sửa các metadata WAL trong PGDATA bằng text editor. Nếu dung lượng WAL tăng bất thường, cần tìm nguyên nhân như replication slots, archive failures, transaction dài hoặc cấu hình retention, rồi xử lý bằng công cụ quản trị PostgreSQL phù hợp.

Một lệnh nguy hiểm thường bị hiểu sai là dùng công cụ reset WAL để khắc phục mọi vấn đề startup. Những thao tác cấp thấp với WAL chỉ nên là biện pháp cuối cùng do người quản trị hiểu rõ hệ quả và có backup; chúng **không** thuộc quy trình bảo trì thường ngày của ứng dụng.

## 11. Thực hành: tạo schema, bảng và xem đường dẫn quan hệ bằng SQL

Phần này được thiết kế để chạy trên **database thực hành riêng** có sẵn, không cần quyền truy cập filesystem. Bạn cần quyền `CREATE` trên database/schema phù hợp; không cần superuser để chạy những câu truy vấn quan sát cơ bản.

### Bước 1. Xác định database hiện tại

Trong `psql` hoặc một SQL client:

```sql
SELECT
    current_database() AS database_name,
    current_user AS role_name,
    current_schema() AS active_schema;
```

Trong `psql` còn có:

```text
\conninfo
```

Hãy xác nhận đang kết nối đúng **database lab**, không phải production.

### Bước 2. Tạo schema

```sql
CREATE SCHEMA IF NOT EXISTS storage_lab;
```

Schema này chỉ là namespace trong database hiện tại; nó không tạo thêm directory vật lý tên `storage_lab` bên dưới PGDATA.

### Bước 3. Tạo bảng và chỉ mục

```sql
CREATE TABLE storage_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_no text NOT NULL UNIQUE,
    status text NOT NULL DEFAULT 'NEW',
    amount numeric(12, 2) NOT NULL CHECK (amount >= 0),
    note text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT orders_status_check
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);

CREATE INDEX idx_orders_status_created
ON storage_lab.orders (status, created_at);
```

Bảng có một heap relation và các index:

- Primary key index cho `order_id`.
- Unique index hỗ trợ ràng buộc `order_no`.
- Index `idx_orders_status_created` phục vụ truy vấn theo trạng thái/thời gian.

Đây là nhiều **quan hệ lưu trữ vật lý** dù bạn mới tạo **một table** trong schema.

### Bước 4. Chèn một ít dữ liệu

```sql
INSERT INTO storage_lab.orders
    (order_no, status, amount, note)
VALUES
    ('ARCH58-001', 'NEW', 125000.00, 'Đơn hàng thử nghiệm A'),
    ('ARCH58-002', 'PAID', 89000.00, 'Đơn hàng thử nghiệm B'),
    ('ARCH58-003', 'NEW', 175000.00, 'Đơn hàng thử nghiệm C')
RETURNING order_id, order_no, status, amount;
```

Kiểm tra:

```sql
SELECT order_id, order_no, status, amount, created_at
FROM storage_lab.orders
ORDER BY order_id;
```

Nếu cần chạy lại toàn bộ bài, hãy dùng **database/schema lab mới** hoặc quy trình reset được kiểm soát. Không tự `DROP SCHEMA ... CASCADE` trên schema có dữ liệu mà bạn chưa xác minh quyền sở hữu/phụ thuộc.

### Bước 5. Xem database OID và tablespace mặc định

```sql
SELECT
    d.oid AS database_oid,
    d.datname AS database_name,
    t.spcname AS default_tablespace
FROM pg_database AS d
JOIN pg_tablespace AS t ON t.oid = d.dattablespace
WHERE d.datname = current_database();
```

Kết quả chỉ ra database bạn đang sử dụng có OID nào và được đặt trong tablespace mặc định nào.

### Bước 6. Xem OID, filenode và đường dẫn của table

```sql
SELECT
    'storage_lab.orders'::regclass AS relation_name,
    pg_relation_filenode('storage_lab.orders'::regclass)
        AS relation_filenode,
    pg_relation_filepath('storage_lab.orders'::regclass)
        AS relative_path;
```

Ví dụ kết quả **chỉ minh họa**:

```text
relation_name       | relation_filenode | relative_path
--------------------+-------------------+------------------
storage_lab.orders  | 16410             | base/16384/16410
```

Các số thực tế do PostgreSQL cấp trên instance đang chạy. Nếu muốn tìm index:

```sql
SELECT
    pg_relation_filenode('storage_lab.idx_orders_status_created'::regclass)
        AS index_filenode,
    pg_relation_filepath('storage_lab.idx_orders_status_created'::regclass)
        AS index_path;
```

Index có file riêng, và đường dẫn chỉ ra nơi PostgreSQL lưu relation đó. Không có đường dẫn SQL logic kiểu `storage_lab/orders/rows`.

### Bước 7. Xem catalog cho tất cả relations trong schema

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    c.relkind,
    c.oid AS relation_oid,
    c.relfilenode,
    c.reltablespace,
    pg_relation_filepath(c.oid) AS relative_path
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'storage_lab'
ORDER BY c.relkind, c.relname;
```

Giải thích một số `relkind`:

| `relkind` | Loại relation |
|---|---|
| `r` | Ordinary table |
| `i` | Ordinary index |
| `S` | Sequence |
| `v` | View, không có heap lưu kết quả thông thường |
| `m` | Materialized view, lưu kết quả vật lý |
| `p` | Partitioned table parent |
| `I` | Partitioned index parent |

Identity column có thể tạo sequence liên quan xuất hiện trong catalog. Sự hiện diện của sequence không có nghĩa mỗi row là một file; sequence là đối tượng phục vụ cấp giá trị.

### Bước 8. Quan sát kích thước dữ liệu

```sql
SELECT
    pg_relation_size('storage_lab.orders'::regclass)
        AS heap_main_bytes,
    pg_table_size('storage_lab.orders'::regclass)
        AS table_with_toast_bytes,
    pg_indexes_size('storage_lab.orders'::regclass)
        AS indexes_bytes,
    pg_total_relation_size('storage_lab.orders'::regclass)
        AS total_bytes;
```

Các cột khác nhau có ý nghĩa khác nhau, không phải bốn cách tính cùng một số. Các hàm này được giải thích chi tiết ở phần tiếp theo.

Nếu muốn hiển thị dễ đọc:

```sql
SELECT
    pg_size_pretty(
        pg_total_relation_size('storage_lab.orders'::regclass)
    ) AS total_pretty_size;
```

### Bước 9. Thử UPDATE rồi quan sát kích thước

```sql
UPDATE storage_lab.orders
SET status = 'PAID'
WHERE order_no = 'ARCH58-001'
RETURNING order_no, status;

SELECT
    pg_relation_size('storage_lab.orders'::regclass) AS main_bytes,
    pg_total_relation_size('storage_lab.orders'::regclass) AS total_bytes;
```

Không nên kỳ vọng mỗi `UPDATE` nhỏ đều làm số byte tăng ngay một lượng cố định. PostgreSQL có thể tái dùng khoảng trống đã có, và các con số có thể bị làm tròn theo page/segment. Một thay đổi logic không tương đương một file mới.

**Lưu ý:** những câu SQL ở đây tạo và sửa đối tượng trong database lab, nhưng không chạm trực tiếp vào filesystem. Không dùng `COPY ... TO '/server/path'` hay file operations đặc quyền trong bài này.

## 12. Phân biệt các hàm đo kích thước PostgreSQL

### 12.1. `pg_relation_size()`: kích thước một relation/fork

```sql
SELECT
    pg_relation_size('storage_lab.orders'::regclass) AS main_bytes;
```

Mặc định hàm đo **main fork** của relation được chỉ định. Nó **không** tự tính toàn bộ các index khác của bảng.

Có thể chỉ rõ fork:

```sql
SELECT
    pg_relation_size('storage_lab.orders'::regclass, 'main')
        AS main_bytes,
    pg_relation_size('storage_lab.orders'::regclass, 'fsm')
        AS fsm_bytes,
    pg_relation_size('storage_lab.orders'::regclass, 'vm')
        AS vm_bytes;
```

Một fork chưa phát sinh file hoặc chưa có dữ liệu có thể cho kích thước 0 theo hành vi được hỗ trợ. Không ép tạo FSM/VM chỉ để nhìn thấy file trên đĩa.

### 12.2. `pg_table_size()`: kích thước phần bảng không tính index thông thường

```sql
SELECT pg_table_size('storage_lab.orders'::regclass);
```

Hàm tính dung lượng phần **table storage**, gồm heap, các fork liên quan và dữ liệu TOAST/TOAST index khi có; nó **không** tính các index thông thường của bảng.

Vì vậy, `pg_table_size` có thể lớn hơn `pg_relation_size(table)`.

### 12.3. `pg_indexes_size()`: dung lượng các index của bảng

```sql
SELECT pg_indexes_size('storage_lab.orders'::regclass);
```

Hàm ước lượng dung lượng lưu trữ của những index gắn với table, bao gồm các fork/segment thuộc các index đó theo ngữ nghĩa PostgreSQL.

Một bảng có primary key và nhiều secondary indexes có thể dành phần lớn dung lượng cho index nếu key lớn hoặc số lượng index nhiều.

### 12.4. `pg_total_relation_size()`: tổng dung lượng của bảng cùng đối tượng liên quan

```sql
SELECT pg_total_relation_size('storage_lab.orders'::regclass);
```

Hàm cho dung lượng tổng của table, bao gồm phần bảng và index liên quan. Với bảng sử dụng TOAST, phần TOAST cũng được tính theo ngữ nghĩa hàm.

Công thức khái niệm hữu ích:

```text
Total relation size
    ≈ Table size (heap/forks/TOAST)
      + Indexes size (các index thông thường)
```

Dấu `≈` ở đây biểu thị cách hiểu tổng quát; không nên lấy công thức này để suy luận chi tiết từng loại file trên mọi loại relation/phiên bản mà không xem định nghĩa hàm đang dùng.

### 12.5. `pg_database_size()` và `pg_tablespace_size()`

Khi muốn xem kích thước ở cấp rộng hơn:

```sql
SELECT
    current_database() AS database_name,
    pg_size_pretty(pg_database_size(current_database()))
        AS database_size;
```

Và khi có quyền phù hợp:

```sql
SELECT
    spcname,
    pg_size_pretty(pg_tablespace_size(oid)) AS tablespace_size
FROM pg_tablespace
ORDER BY spcname;
```

Khả năng xem kích thước tablespace của role có thể phụ thuộc quyền truy cập được PostgreSQL cho phép; nếu truy vấn báo thiếu quyền, hãy nhờ quản trị viên thay vì tự cấp superuser cho ứng dụng.

Các số này đo những phạm vi **khác nhau**:

| Hàm | Phạm vi |
|---|---|
| `pg_relation_size(relation)` | Main fork của một relation theo mặc định |
| `pg_relation_size(relation, 'fsm')` | FSM fork của relation |
| `pg_table_size(table)` | Dung lượng phần table, bao gồm TOAST và fork liên quan nhưng không gồm index thông thường của bảng |
| `pg_indexes_size(table)` | Các index thông thường của bảng |
| `pg_total_relation_size(table)` | Bảng và index liên quan |
| `pg_database_size(database)` | Dung lượng của database |
| `pg_tablespace_size(tablespace)` | Dung lượng của tablespace |

**Chênh lệch kích thước không tự chứng minh lỗi hoặc bloat.** Kết quả còn phụ thuộc phần trống trong page, tuple versions, index, TOAST, fork và các đặc điểm riêng của relation.

## 13. MVCC, VACUUM và thay đổi tệp vật lý

### 13.1. Một UPDATE có thể tạo phiên bản tuple mới

PostgreSQL thực hiện **MVCC** để hỗ trợ transaction đọc/ghi đồng thời. Một transaction có thể nhìn thấy row version khác với transaction khác dựa trên snapshot và mức cô lập.

Sơ đồ đơn giản:

```text
Row logic: order_no = ARCH58-001
    |
    ├── Version cũ: status = NEW
    │      └── Có thể còn cần thiết cho snapshot cũ
    └── Version mới: status = PAID
           └── Phiên bản được phép nhìn thấy sau commit
```

Một số cập nhật có thể tận dụng tối ưu **HOT (Heap-Only Tuple)** khi điều kiện phù hợp, đặc biệt khi không phải sửa các giá trị index liên quan và page có đủ chỗ. Trong ví dụ đổi `status`, do `status` đã nằm trong index, không nên mặc định HOT có thể xảy ra.

Chỉ quan sát các cột cuối cùng trong SQL không cho thấy mọi tuple version còn tồn tại trên page.

### 13.2. VACUUM làm gì?

Khi không còn snapshot/transaction cần dùng những tuple versions đã chết, PostgreSQL có thể thu hồi không gian để tái sử dụng thông qua **VACUUM**. Cơ chế **autovacuum** được thiết kế để làm nhiều công việc bảo trì này tự động.

Ví dụ chủ bảng/role có quyền phù hợp có thể chạy trong lab:

```sql
VACUUM (ANALYZE) storage_lab.orders;
```

- `VACUUM` giúp dọn thông tin row versions không còn cần thiết và duy trì cấu trúc cần thiết.
- `ANALYZE` cập nhật thống kê để optimizer lập kế hoạch truy vấn tốt hơn.
- VACUUM thông thường có thể tạo điều kiện tái sử dụng không gian **bên trong** file, nhưng **không mặc nhiên thu nhỏ file về đúng kích thước dữ liệu sống** ngay lập tức.

Không lấy việc kích thước file không giảm sau `VACUUM` làm kết luận rằng lệnh không hoạt động.

### 13.3. `VACUUM FULL` và rewrite relation

`VACUUM FULL` tổ chức lại dữ liệu bằng cách **viết lại relation** để thu hồi không gian vật lý chặt hơn, nhưng có chi phí I/O, cần thêm dung lượng tạm trong quá trình thực hiện và yêu cầu khóa mạnh (**ACCESS EXCLUSIVE**) trên bảng.

Ví dụ câu lệnh, **không khuyến nghị chạy trên bảng sản xuất đang phục vụ truy cập**:

```sql
VACUUM FULL storage_lab.orders;
```

Khi rewrite, PostgreSQL có thể gán **relfilenode mới**. Vì vậy, đường dẫn từ `pg_relation_filepath()` có thể thay đổi dù tên SQL `storage_lab.orders` không thay đổi.

Các thao tác khác như `CLUSTER`, `TRUNCATE` hoặc một số trường hợp `REINDEX` cũng có thể làm thay đổi file storage tương ứng. **Tên file và relfilenode không phải API ổn định để ứng dụng gắn dữ liệu nghiệp vụ vào.**

### 13.4. Quan sát chỉ số dead tuples

Một gợi ý để xem số liệu ước lượng:

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_all_tables
WHERE schemaname = 'storage_lab'
  AND relname = 'orders';
```

`n_live_tup` và `n_dead_tup` là **ước lượng thống kê**, không phải bộ đếm hoàn toàn chính xác ở từng thời điểm. Trong một bảng lab vài dòng, số liệu có thể chưa thay đổi ngay. Để điều tra bloat thực tế, cần thêm công cụ và đánh giá workload, không chỉ dựa vào một cột.

## 14. Di chuyển bảng hoặc index sang tablespace khác

### 14.1. Di chuyển có thể làm thay đổi vị trí file

Nếu một tablespace `fast_ts` đã được quản trị viên tạo, và role có đủ quyền, có thể chuyển phần storage của table:

```sql
ALTER TABLE storage_lab.orders
SET TABLESPACE fast_ts;
```

Đây là câu lệnh **minh họa có tác động lên dữ liệu vật lý**. Nó có thể phải di chuyển/rewrite lượng dữ liệu lớn và giữ khóa ảnh hưởng ứng dụng; **không chạy trên production nếu chưa có kế hoạch migration và downtime/lock budget**.

Sau đó, kiểm tra:

```sql
SELECT
    pg_relation_filepath('storage_lab.orders'::regclass)
        AS new_relative_path;
```

Khi tablespace là nơi lưu bên ngoài PGDATA, đường dẫn có thể đổi từ:

```text
base/<database_oid>/<filenode>
```

sang:

```text
pg_tblspc/<tablespace_oid>/PG_<version>_<catalog_version>/<database_oid>/<filenode>
```

### 14.2. Index có được di chuyển theo bảng không?

**Không nên mặc định tất cả index đều tự chuyển cùng khi chạy `ALTER TABLE ... SET TABLESPACE`.** PostgreSQL có cách quản lý vị trí của table storage và index storage riêng; khi cần di chuyển các index, phải lập kế hoạch thao tác tương ứng.

Ví dụ cú pháp:

```sql
ALTER INDEX storage_lab.idx_orders_status_created
SET TABLESPACE fast_ts;
```

Index khác như primary key index hoặc unique index cũng cần được xét nếu mục tiêu là chuyển toàn bộ footprint lưu trữ. Thực hiện từng lệnh không có nghĩa PostgreSQL đảm bảo thay đổi đồng thời tất cả đối tượng mà không khóa.

### 14.3. Vì sao chọn tablespace riêng?

Một số lý do vận hành có thể hợp lý:

- Dung lượng volume mặc định sắp cạn và cần phân bố đối tượng theo chính sách.
- Một nhóm bảng/index rất lớn được đặt trên lớp lưu trữ với đặc tính I/O phù hợp.
- Muốn phân bổ dữ liệu theo yêu cầu quản trị filesystem/volume.
- Một số tác vụ bảo trì hoặc sao lưu vật lý cần quản lý đường dẫn rõ ràng.

Nhưng tablespace có những giới hạn:

- Nó không tự tạo read replica.
- Không tạo transaction boundary riêng.
- Không thay thế replication, backup hoặc kiểm tra phục hồi.
- Không mã hóa dữ liệu theo cách ứng dụng có thể mặc nhiên tin cậy.
- Không tạo ranh giới role/schema/security tự động.
- Không bảo đảm query nhanh hơn nếu storage backend thực tế giống nhau.

Trong managed PostgreSQL hoặc hệ thống dùng storage trừu tượng, việc tự tạo tablespace có thể không được hỗ trợ; hãy dùng cơ chế quản lý lưu trữ chính thức của nền tảng đó.

## 15. Những trường hợp quan hệ không giống bảng thông thường

### 15.1. View và materialized view

```sql
CREATE VIEW storage_lab.paid_orders AS
SELECT order_id, order_no, amount
FROM storage_lab.orders
WHERE status = 'PAID';
```

**View thường** chủ yếu lưu định nghĩa truy vấn. Nó không có một heap riêng lưu sẵn tất cả kết quả ở mỗi thời điểm.

Ngược lại:

```sql
CREATE MATERIALIZED VIEW storage_lab.paid_orders_snapshot AS
SELECT order_id, order_no, amount
FROM storage_lab.orders
WHERE status = 'PAID';
```

**Materialized view** lưu kết quả truy vấn theo cơ chế lưu trữ vật lý; khi dữ liệu nguồn thay đổi, kết quả materialized view **không tự cập nhật tức thì**. Cần quy trình refresh thích hợp nếu muốn kết quả mới hơn.

Do đó, hai đối tượng có thể cùng trông như bảng khi `SELECT`, nhưng cách quản lý relation file khác nhau.

### 15.2. Partitioned table

Một bảng partitioned parent định nghĩa cách chia dữ liệu, còn các **partitions** lưu hàng tương ứng.

Ví dụ:

```sql
CREATE TABLE storage_lab.logs (
    log_id bigint NOT NULL,
    created_at date NOT NULL,
    message text NOT NULL
) PARTITION BY RANGE (created_at);

CREATE TABLE storage_lab.logs_2026_11
PARTITION OF storage_lab.logs
FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
```

Khi chạy:

```sql
SELECT pg_relation_filepath('storage_lab.logs'::regclass);
```

partitioned parent có thể trả `NULL` vì **nó không có heap storage riêng**. Partition `storage_lab.logs_2026_11` là đối tượng lưu dữ liệu thực tế và có relation filepath.

Không được hiểu “parent không có file” nghĩa là các dữ liệu được truy vấn qua parent đã biến mất. PostgreSQL điều phối việc đọc/ghi qua các partitions.

### 15.3. Temporary table

Temporary tables có vòng đời gắn với session hoặc transaction theo cấu hình; PostgreSQL quản lý các tệp tạm và không gian làm việc theo cơ chế riêng, có thể dùng `temp_tablespaces`.

```sql
CREATE TEMP TABLE tmp_ids (
    id bigint
) ON COMMIT DROP;
```

Một bảng tạm như trên tồn tại trong phạm vi transaction/session phù hợp và được drop theo hành vi `ON COMMIT DROP`. Không nên cố dự đoán cố định tên file tạm hoặc dùng `pg_relation_filepath()` làm cách giao tiếp dữ liệu tạm giữa những session khác nhau.

### 15.4. Sequence và identity

Cột:

```sql
order_id bigint GENERATED ALWAYS AS IDENTITY
```

có thể sử dụng một sequence do PostgreSQL quản lý. Sequence là một đối tượng có dữ liệu trạng thái riêng; giá trị nó cấp **không** đồng nghĩa với số thứ tự row trên file main fork của table. Sequence có thể có khoảng trống vì transaction rollback hoặc lỗi chèn, và không nên được dùng làm thước đo số lượng hàng.

## 16. Bảo vệ PGDATA và tablespace trong backup/restore

### 16.1. Logical backup khác physical backup

**Logical backup** như `pg_dump` xuất cấu trúc và dữ liệu ở dạng logic. Khi restore, PostgreSQL có thể tạo lại tables/index với **OID, relfilenode và đường dẫn vật lý khác**.

**Physical backup** như `pg_basebackup` làm việc ở mức cluster và các files cần thiết để tạo một bản dữ liệu vật lý nhất quán theo cơ chế PostgreSQL. Khi cluster sử dụng tablespace tùy chỉnh, quy trình physical backup/restore phải xử lý **cả các vị trí tablespace ngoài PGDATA**, không chỉ directory `base/`.

So sánh:

| Tiêu chí | Logical backup | Physical/base backup |
|---|---|---|
| Đơn vị nội dung chính | Schema, table, object và dữ liệu SQL-level | Các dữ liệu vật lý của cluster phù hợp backup |
| Có giữ nguyên relfilenode không? | Không nên kỳ vọng | Có dữ liệu vật lý trong bản backup theo quy trình, nhưng restore/vận hành có yêu cầu riêng |
| Khôi phục chọn bảng riêng lẻ | Thường thuận tiện hơn | Không phải mục tiêu chính của raw physical restore |
| Vai trò của WAL | Tùy chiến lược; dump logic không tự tạo PITR đầy đủ | Rất quan trọng cho physical consistency và PITR |
| Tablespace tùy chỉnh | Cần xử lý DDL/vị trí tương ứng khi restore | Phải tính đến các tablespace files/path mapping |
| Vai trò của quyền và role | Có thể cần backup riêng global objects | Là một phần trạng thái cluster tùy loại backup |

Đừng suy luận rằng copy bằng thao tác hệ điều hành một số tệp từ `PGDATA/base/<db_oid>` lúc PostgreSQL đang chạy là một **backup nhất quán**. Trong lúc máy chủ ghi dữ liệu, các trang, WAL và metadata có thể không đồng bộ nếu không dùng cơ chế backup được PostgreSQL hỗ trợ.

### 16.2. WAL archiving và point-in-time recovery

Muốn khôi phục tới một thời điểm chính xác sau base backup, kiến trúc thông thường cần:

1. Base backup nhất quán.
2. WAL archive/retention bao phủ khoảng thời gian cần phục hồi.
3. Thông tin mốc/restore configuration phù hợp.
4. Quy trình replay WAL và kiểm tra dữ liệu sau restore.

**Replication không thay thế backup**: một lệnh `DROP TABLE` sai ở primary có thể được replay xuống standby. Backup độc lập giúp có cơ hội trở lại mốc trước thao tác sai.

### 16.3. Bảo vệ đường dẫn vật lý

Những nguyên tắc bắt buộc:

- Không mở, chỉnh sửa, sao chép thiếu kiểm soát hoặc xóa các file relation trong PGDATA.
- Không “chuyển tablespace” bằng cách tự di chuyển file trong lúc server chạy.
- Không đặt PostgreSQL data directory/tablespace lên filesystem không phù hợp các yêu cầu của PostgreSQL mà chưa kiểm chứng.
- Duy trì ownership và permission của user hệ điều hành chạy PostgreSQL.
- Không tự xóa file WAL khi thấy ổ đĩa đầy.
- Có backup, diễn tập restore và giám sát free disk cho **mọi volume chứa dữ liệu**: PGDATA, tablespace ngoài, WAL nếu đặt riêng.
- Với môi trường container, phân biệt filesystem **bên trong container**, volume mount và đường dẫn trên host. Xóa container/volume không đúng cách có thể mất dữ liệu.

Quy trình sửa lỗi vật lý nên ưu tiên **công cụ PostgreSQL được hỗ trợ** và kế hoạch khôi phục đã được kiểm thử.

## 17. Những lỗi vận hành liên quan PGDATA và relation files

### 17.1. Server không khởi động do không truy cập PGDATA

Biểu hiện có thể liên quan đường dẫn sai, quyền filesystem hoặc data directory chưa được khởi tạo.

Hướng tiếp cận:

- Xác định đúng instance, đường dẫn và owner của PGDATA.
- Kiểm tra log của PostgreSQL và quy trình service manager/container.
- Xác nhận volume đã mount đúng và không thay đổi đường dẫn ngoài ý muốn.
- Không chạy `initdb` lên directory đang chứa cluster để “sửa” startup.

`initdb` là công cụ **khởi tạo mới**, không phải sửa chữa tự động dữ liệu đã có.

### 17.2. `No space left on device`

PostgreSQL có thể hết dung lượng ở:

- Volume PGDATA chứa `base/`.
- Volume WAL.
- Volume tablespace ngoài PGDATA.
- Vùng tệp tạm.

Cần xác định **volume nào** đầy trước khi hành động. Nếu WAL tăng, kiểm tra archiving/replication slots/retention; nếu một table quá lớn, xác định table/index/TOAST và workload. Không giải phóng chỗ bằng cách xóa một file relation hoặc WAL tùy ý.

### 17.3. `could not open file "base/...": No such file or directory`

Thông báo này cần được điều tra nghiêm túc: có thể liên quan dữ liệu bị thay đổi ngoài cơ chế PostgreSQL, vấn đề volume/mount, lỗi I/O hoặc một sự cố lưu trữ khác.

Không tự tạo file rỗng theo tên mà log nêu để “hết báo lỗi”. Cần xác định relation theo catalog và trạng thái instance, xem log và chiến lược restore từ backup nhất quán.

### 17.4. Tablespace đường dẫn biến mất

Nếu `pg_tblspc/<oid>` trỏ tới một volume bị tháo mount hoặc đường dẫn không còn hợp lệ, những relation ở tablespace đó có thể không truy cập được, dù schema và bảng vẫn tồn tại trong catalog.

Cần kiểm tra storage mount, quyền và trạng thái filesystem; không đổi symlink sang thư mục khác không chứa dữ liệu tương ứng.

### 17.5. Không tìm thấy file của một bảng

Nếu:

```sql
SELECT pg_relation_filepath('storage_lab.orders'::regclass);
```

trả đường dẫn khác so với hôm qua, điều đó chưa chắc là lỗi. Các thao tác rewrite/move/reindex có thể thay filenode; table còn có thể được chuyển tablespace. Luôn tra **catalog và hàm PostgreSQL tại thời điểm quan sát**, đừng tìm theo một filenode cũ.

### 17.6. Vì sao PostgreSQL còn có nhiều file khi bảng rỗng?

Bảng rỗng vẫn có catalog và có thể có relation storage. Index, sequence, các fork có thể tồn tại hoặc phát sinh tùy tình trạng. PostgreSQL không quy số file theo số hàng. Kể cả sau khi xóa mọi hàng bằng `DELETE`, không gian trong relation có thể vẫn dành để tái sử dụng.

### 17.7. Thiếu quyền xem PGDATA

Role application thường không có quyền xem `data_directory` hoặc đọc server filesystem. Đây là đặc điểm an toàn. Để vận hành, hãy dùng các hàm thống kê/catalog mà role được phép, hoặc yêu cầu role giám sát/quản trị có quyền phù hợp thực hiện kiểm tra. **Không cấp superuser cho ứng dụng chỉ vì muốn xem tên file.**

## 18. Những hiểu nhầm quan trọng

**“Một database tương ứng một PostgreSQL instance.”** Không. Một PostgreSQL database cluster có thể chứa nhiều database; một instance có thể phục vụ các database đó.

**“PostgreSQL database cluster nghĩa là hệ thống có ít nhất hai máy.”** Sai. Cluster theo `initdb` là tập dữ liệu quản lý chung, ngay cả khi chỉ chạy trên một host.

**“`PGDATA` chỉ chứa tệp của từng bảng.”** Không. Nó còn chứa WAL, transaction status, global catalogs, links tới tablespace và những thành phần nội bộ khác.

**“`base/` lưu tất cả mọi bảng dù đặt ở tablespace nào.”** Sai. `base/` là vùng dữ liệu của các database trong tablespace mặc định; tablespace bên ngoài PGDATA có vị trí lưu riêng.

**“Schema `sales` sẽ tương ứng thư mục `sales/`.”** Không. Schema là namespace logic được lưu trong catalog. Đường dẫn file dựa trên database OID, tablespace và filenode.

**“Tên file `16410` luôn là bảng `orders`.”** Không. Số filenode được phân bổ động và có thể thay đổi sau rewrite; không ổn định giữa các instance.

**“Một bảng có đúng một file.”** Không. Bảng có thể có main/FSM/VM forks, nhiều segments, TOAST, indexes và những cấu trúc liên quan khác.

**“`16410.1` là dòng thứ nhất của bảng.”** Sai. Đó có thể là segment tiếp theo của một relation main fork.

**“`pg_relation_size(table)` là tổng dung lượng mọi index của bảng.”** Sai. Hàm đo một relation/fork, mặc định main fork của đối tượng. Dùng `pg_table_size`, `pg_indexes_size` hoặc `pg_total_relation_size` theo phạm vi cần biết.

**“Chạy `VACUUM` xong file phải giảm dung lượng.”** Không nhất thiết. VACUUM thông thường chủ yếu tạo điều kiện tái sử dụng không gian; `VACUUM FULL` rewrite relation để thu hồi không gian vật lý nhưng có chi phí và khóa đáng kể.

**“Tablespace mới tự mang lại tốc độ cao.”** Không. Hiệu năng phụ thuộc storage backend thật, workload và nhiều yếu tố; nếu tất cả cùng một volume thì tên tablespace khác nhau không tạo ra thiết bị khác nhau.

**“WAL là backup đủ để khôi phục toàn bộ PostgreSQL.”** Không. PITR cần base backup và chuỗi WAL phù hợp cùng quy trình restore.

**“View không có filepath nghĩa là hệ thống mất dữ liệu.”** Không. View thông thường không có local heap lưu kết quả; partitioned parent và một số đối tượng logic cũng không có tệp heap riêng.

## 19. Bài tập tự luyện có lời giải

### Bài 1. Phân biệt cluster và database

Bạn chạy `initdb` một lần trên máy test, sau đó tạo `sales_db` và `analytics_db`.

**Hỏi:** đã tạo bao nhiêu database cluster và bao nhiêu database mới?

**Lời giải:** một database cluster được khởi tạo bằng `initdb`; hai database người dùng mới được tạo bên trong cluster đó (ngoài các database hệ thống có sẵn). Không cần tạo cluster thứ hai chỉ để có thêm database.

### Bài 2. Tìm đường dẫn logic từ `pg_relation_filepath`

Giả sử:

```text
current_database() = shop_db
OID của shop_db = 16384
pg_relation_filepath('sales.orders') = base/16384/16410
```

**Hỏi:** `16384` và `16410` biểu thị điều gì?

**Lời giải:** trong đường dẫn minh họa ở tablespace mặc định, `16384` là database OID; `16410` là file node/filenode của relation tại thời điểm quan sát. Chúng không phải số hàng hay khóa chính của đơn hàng.

### Bài 3. Vì sao không có thư mục theo schema?

Bạn có bảng `sales.orders` và `audit.events` trong cùng database, nhưng trong `PGDATA/base/<db_oid>` chỉ thấy nhiều file tên số.

**Lời giải:** `sales` và `audit` là schema logic lưu trong catalog; PostgreSQL lưu relation files theo số định danh và tablespace. Không có yêu cầu phải tạo hai thư mục vật lý mang tên hai schema.

### Bài 4. Phân biệt các fork

Cho các file:

```text
16410
16410_fsm
16410_vm
16410.1
```

**Hỏi:** cái nào chứa main fork, cái nào giúp tìm khoảng trống, cái nào lưu visibility metadata và cái nào là segment tiếp theo?

**Lời giải:**

- `16410`: main fork, segment đầu.
- `16410_fsm`: free space map.
- `16410_vm`: visibility map.
- `16410.1`: segment tiếp theo của main fork.

### Bài 5. Kích thước main fork và tổng size

Kết quả minh họa:

```text
pg_relation_size(orders)       = 80 MB
pg_table_size(orders)          = 105 MB
pg_indexes_size(orders)        = 45 MB
pg_total_relation_size(orders) = 150 MB
```

**Hỏi:** vì sao bốn giá trị khác nhau?

**Lời giải:** main fork chỉ là một phần heap; `pg_table_size` tính thêm các fork và TOAST; index chiếm dung lượng riêng; `pg_total_relation_size` tính bảng cùng các index liên quan. Không nên kết luận có lỗi chỉ vì total lớn hơn main fork.

### Bài 6. Tại sao `pg_relation_filepath` trả `NULL`?

Bạn gọi hàm cho một view hoặc partitioned table parent và nhận `NULL`.

**Lời giải:** các đối tượng này không có local heap storage theo cách ordinary table có. View lưu định nghĩa; partitioned parent điều phối partitions. Cần xem relation thực sự lưu dữ liệu, ví dụ từng partition hoặc materialized view, trước khi tìm file.

### Bài 7. Relation file thay đổi sau bảo trì

Bạn ghi nhận filenode của bảng là 16410. Sau `VACUUM FULL`, hàm trả filenode khác nhưng `SELECT` vẫn hoạt động.

**Lời giải:** PostgreSQL có thể rewrite relation và gán filenode mới; tên logic và catalog identity của bảng vẫn tồn tại. Không dùng số filenode để xây đường dẫn cứng trong ứng dụng hoặc backup script.

### Bài 8. Tablespace không phải schema

Một bảng được tạo:

```sql
CREATE TABLE storage_lab.archive_events (
    event_id bigint PRIMARY KEY,
    payload text
) TABLESPACE fast_ts;
```

**Hỏi:** tên SQL đầy đủ của bảng có phải `fast_ts.archive_events` không?

**Lời giải:** không. Tên SQL vẫn là `storage_lab.archive_events` trong database kết nối. `fast_ts` là tablespace kiểm soát vị trí lưu trữ, không phải schema chứa bảng.

### Bài 9. Vai trò của WAL

Bạn có bản sao của riêng thư mục `pg_wal` nhưng không có base backup hay các files dữ liệu.

**Hỏi:** liệu đủ để khôi phục mọi bảng không?

**Lời giải:** không. WAL hỗ trợ replay/khôi phục thay đổi theo cơ chế PostgreSQL, nhưng cần trạng thái dữ liệu cơ sở phù hợp cùng đủ WAL và quy trình restore. Không dùng riêng `pg_wal` thay backup.

### Bài 10. Ổ đĩa của tablespace bị đầy

Bảng `archive_events` nằm ở `fast_ts`, trong khi PGDATA chính còn trống nhiều.

**Hỏi:** ứng dụng vẫn có thể lỗi ghi bảng đó không?

**Lời giải:** có. Relation storage phụ thuộc volume chứa tablespace `fast_ts`; nếu volume ấy đầy hoặc gặp lỗi, ghi vào bảng/index tương ứng có thể thất bại dù volume chứa PGDATA còn chỗ. Cần giám sát tất cả volume, không chỉ thư mục gốc PGDATA.

## 20. Bảng ghi nhớ kiến trúc PostgreSQL

| Thuật ngữ | Câu hỏi cần trả lời | Cách quan sát hữu ích |
|---|---|---|
| Database cluster | Instance đang quản lý tập database nào? | `pg_database`, kết nối admin và cấu hình instance |
| PGDATA/data directory | Dữ liệu nền của cluster được quản lý ở đâu? | `SHOW data_directory` với quyền phù hợp |
| Database OID | Database SQL tương ứng định danh nào? | `SELECT oid, datname FROM pg_database` |
| Tablespace | Relation nằm trên vùng lưu trữ nào? | `pg_tablespace`, `pg_database.dattablespace` |
| Relation | Bảng, index hoặc đối tượng nào đang được xem? | `pg_class`, `pg_namespace` |
| Filenode | File storage hiện tại mang định danh gì? | `pg_relation_filenode()` |
| Relative filepath | Tệp relation hiện được PostgreSQL định vị ở đâu? | `pg_relation_filepath()` |
| Main fork | Trang dữ liệu chính ở đâu? | `pg_relation_size(relation)` |
| FSM | Thông tin trang còn khoảng trống | `pg_relation_size(relation, 'fsm')` |
| VM | Thông tin hiển thị/frozen của trang | `pg_relation_size(relation, 'vm')` |
| Segments | Vì sao file relation lớn bị chia phần? | Các suffix số như `.1`, theo cách lưu trữ nội bộ |
| TOAST | Giá trị lớn được nén/chuyển ra ngoài như thế nào? | `pg_class.reltoastrelid`, `pg_table_size()` |
| WAL | Hệ thống phục hồi transaction và truyền thay đổi ra sao? | Cấu hình/giám sát WAL, quy trình backup/replication |
| Total size | Bảng và index dùng bao nhiêu chỗ? | `pg_total_relation_size()` |
| MVCC/VACUUM | Vì sao có tuple phiên bản cũ và không gian tái sử dụng? | `pg_stat_all_tables`, VACUUM/autovacuum |

**Tư duy cốt lõi:** **Database cluster** là tập dữ liệu của PostgreSQL instance; **`PGDATA`** là vùng dữ liệu nền của cluster; **tablespace** xác định vị trí lưu relation; **relation files** lưu heap, index, TOAST và các cấu trúc phụ qua forks, segments và pages. Một bảng SQL là **đối tượng logic**, không phải tên file bất biến. Hãy dùng catalog và các hàm PostgreSQL như `pg_relation_filepath()`, `pg_relation_size()` và `pg_total_relation_size()` để quan sát, thay vì chỉnh sửa dữ liệu vật lý bằng tay.


# Ranh giới giữa PostgreSQL, công cụ quản trị và dịch vụ được quản lý

Khi bắt đầu học PostgreSQL, nhiều người dễ gọi chung mọi thứ liên quan đến cơ sở dữ liệu là “PostgreSQL”: cửa sổ `pgAdmin`, lệnh `psql`, máy chủ lưu dữ liệu, một instance trên đám mây hoặc thậm chí bảng điều khiển của nhà cung cấp. Cách gọi này có thể thuận tiện trong giao tiếp, nhưng khi triển khai ứng dụng hoặc xử lý sự cố, việc **phân biệt đúng vai trò và ranh giới trách nhiệm** rất quan trọng.

Có ba lớp cần tách bạch:

1. **PostgreSQL Database Server:** hệ quản trị cơ sở dữ liệu thực sự lưu trữ và xử lý dữ liệu, thực thi SQL, quản lý giao dịch, chỉ mục, quyền và cơ chế phục hồi.
2. **Công cụ quản trị và ứng dụng client:** chương trình kết nối đến PostgreSQL để gửi lệnh, xem kết quả, thực hiện backup, migration, giám sát hoặc quản lý cấu hình. Ví dụ: `psql`, `pgAdmin`, DBeaver, ứng dụng Java dùng JDBC.
3. **Dịch vụ PostgreSQL được quản lý (managed PostgreSQL):** nhà cung cấp vận hành một phần đáng kể hạ tầng và vòng đời máy chủ PostgreSQL, cung cấp cách tạo, cấu hình, backup, giám sát và nâng cấp thông qua control plane. Ví dụ: Amazon RDS for PostgreSQL, Google Cloud SQL for PostgreSQL, Azure Database for PostgreSQL.

**Điểm cốt lõi:** một công cụ quản trị không thay thế database server; một dịch vụ managed không làm ứng dụng hết trách nhiệm về schema, truy vấn và quyền dữ liệu; và cùng tên PostgreSQL không có nghĩa mọi môi trường có khả năng quản trị giống nhau.

Bài học này hướng dẫn nhận diện từng lớp, giới hạn quyền thao tác, cách phân chia công việc vận hành và lựa chọn mô hình phù hợp khi xây dựng ứng dụng quan hệ với PostgreSQL.

## 1. Sơ đồ tổng quan: ai làm việc gì?

~~~text
                         NGƯỜI DÙNG / DEV / DBA
                                   |
                 +-----------------+------------------+
                 |                 |                  |
                 v                 v                  v
              pgAdmin             psql              Ứng dụng
             (GUI tool)       (CLI client)       Java / JDBC
                 |                 |                  |
                 +-----------------+------------------+
                                   |
                   Giao thức kết nối PostgreSQL
                    (TCP/TLS hoặc Unix socket)
                                   |
                                   v
                    +-----------------------------+
                    | PostgreSQL Database Server  |
                    |-----------------------------|
                    | Parser / Planner / Executor |
                    | SQL, MVCC, Transaction      |
                    | Bảng, chỉ mục, role, schema |
                    | WAL, recovery, autovacuum   |
                    +-----------------------------+
                                   |
                                   v
                         Dữ liệu và WAL trên đĩa

         Nếu dùng managed service, nhà cung cấp vận hành
         hạ tầng/server phía sau và cung cấp control plane:
         +----------------------------------------------+
         | Tạo instance, storage, network, backup, HA,  |
         | patch/upgrade, metrics theo gói dịch vụ      |
         +----------------------------------------------+
~~~

Ở mô hình self-hosted, bạn hoặc đội vận hành sở hữu những công việc mà nhà cung cấp managed thường gánh thay. Ở mô hình managed, **SQL vẫn chạy trong database engine**; giao diện cloud chỉ là cách điều khiển và tự động hóa một số tác vụ quanh engine.

## 2. PostgreSQL Database Server thực chất là gì?

**PostgreSQL** là một hệ quản trị cơ sở dữ liệu quan hệ mã nguồn mở, có khả năng thực thi SQL và cung cấp các đặc tính giao dịch như ACID, MVCC, ràng buộc, index và cơ chế phục hồi.

Một máy chủ PostgreSQL thực hiện những công việc cốt lõi:

- Tiếp nhận kết nối của client sau khi áp dụng quy tắc xác thực và cấp quyền.
- Phân tích câu SQL, lập kế hoạch truy vấn và thực thi.
- Lưu bảng, chỉ mục và các đối tượng cơ sở dữ liệu.
- Bảo vệ tính nhất quán bằng `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY`, `CHECK` và transaction.
- Xử lý nhiều giao dịch đồng thời bằng MVCC, lock và isolation levels.
- Ghi **Write-Ahead Log (WAL)** để hỗ trợ phục hồi sau sự cố và các cơ chế replication/backup.
- Thực hiện những tác vụ nội bộ như checkpoint, autovacuum và quản lý bộ nhớ.
- Cung cấp các system catalog và view thống kê để client quan sát.

Ví dụ SQL sau được **PostgreSQL server** thực thi, bất kể lệnh được gửi từ `psql`, `pgAdmin` hay ứng dụng Java:

~~~sql
CREATE TABLE customer_account (
    account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO customer_account (email)
VALUES ('an@example.test');

SELECT account_id, email, created_at
FROM customer_account
ORDER BY account_id;
~~~

PostgreSQL server quyết định cách ghi hàng, cập nhật chỉ mục `UNIQUE`, quản lý transaction và trả kết quả. Công cụ client chỉ **gửi lệnh và trình bày kết quả**.

### 2.1. PostgreSQL không phải một giao diện quản trị đồ họa

Có thể cài PostgreSQL server và vận hành hoàn toàn bằng terminal hoặc ứng dụng mà không cần `pgAdmin`. Ngược lại, có thể cài `pgAdmin` trên laptop nhưng **không có database server trên laptop**; công cụ sẽ kết nối tới một server khác.

Bảng dữ liệu không “nằm trong pgAdmin”. Khi đóng pgAdmin, database vẫn tồn tại và server vẫn có thể phục vụ các client khác, trừ khi có hành động quản trị tác động đến server.

### 2.2. SQL không phụ thuộc vào cửa sổ gõ lệnh

`SELECT`, `INSERT`, `UPDATE` và `COMMIT` là các lệnh SQL được xử lý bởi PostgreSQL. Nếu cùng kết nối đến một database với cùng role, cùng transaction và cùng cấu hình session, một câu SQL tương đương có thể được gửi từ nhiều công cụ khác nhau.

Tuy nhiên, sự khác biệt giữa client vẫn quan trọng: mỗi công cụ có thể quản lý autocommit, transaction, encoding, biến client hoặc cách hiển thị kết quả khác nhau.

## 3. Phân biệt server, instance, database, schema và cluster

Các thuật ngữ này dễ bị dùng lẫn nhau:

| Thuật ngữ | Ý nghĩa trong ngữ cảnh PostgreSQL | Ví dụ |
|---|---|---|
| **PostgreSQL server** | Tiến trình/hệ thống máy chủ thực thi truy vấn và quản lý dữ liệu | Một server nghe kết nối tại `db.internal:5432` |
| **Instance** | Một triển khai server đang vận hành, thường gắn với cấu hình, tài nguyên và thư mục dữ liệu | Instance PostgreSQL phục vụ ứng dụng bán hàng |
| **Database** | Không gian chứa schema và đối tượng riêng trong một PostgreSQL cluster | `sales_db`, `reporting_db` |
| **Schema** | Namespace bên trong database, nhóm bảng, view, function và đối tượng | `public`, `billing`, `inventory` |
| **PostgreSQL database cluster** | Theo thuật ngữ PostgreSQL truyền thống, tập các database được quản lý bởi một server installation/data directory | Data directory được khởi tạo bằng `initdb` |
| **Cloud cluster** | Thuật ngữ sản phẩm/hạ tầng của nhà cung cấp; có thể gồm nhiều node, storage dùng chung hoặc HA | Một cụm managed có primary và standby |

**Cần chú ý từ “cluster”:** trong tài liệu PostgreSQL gốc, nó có thể chỉ một tập database trong cùng một data directory, không nhất thiết là cụm nhiều máy. Trong giao diện managed cloud, “cluster” thường mô tả cách triển khai của nhà cung cấp. Phải xem định nghĩa của hệ thống đang làm việc.

### 3.1. Một server có thể chứa nhiều database

Ví dụ trong một PostgreSQL cluster có hai database:

~~~text
PostgreSQL instance
  |
  +-- sales_db
  |     +-- public.orders
  |     +-- billing.payments
  |
  +-- analytics_db
        +-- public.daily_summary
~~~

Các schema như `public` và `billing` nằm **bên trong một database**. Một kết nối thông thường sẽ kết nối tới **một database cụ thể**; truy cập xuyên database không giống truy cập xuyên schema trong cùng database và cần cơ chế thích hợp như kết nối riêng hoặc công cụ/extension hỗ trợ.

### 3.2. Port 5432 không phải là database

PostgreSQL thường sử dụng port **5432** theo mặc định. Port là nơi client kết nối tới server, không phải tên database. Khi kết nối cần phân biệt host, port, database và role.

~~~text
host = db.example.internal
port = 5432
database = sales_db
user = app_user
~~~

Trong managed service, địa chỉ endpoint có thể đổi theo failover hoặc dùng endpoint logic; không nên tự suy rằng một IP tương ứng vĩnh viễn với một node vật lý.

## 4. Công cụ quản trị là gì?

**Công cụ quản trị** là một client hoặc bộ công cụ hỗ trợ con người và hệ thống tương tác với PostgreSQL. Chúng có thể:

- Mở kết nối và chạy SQL.
- Hiển thị cấu trúc bảng, chỉ mục và role.
- Tạo hoặc sửa đối tượng khi tài khoản có quyền.
- Xuất/nhập dữ liệu, dump hoặc restore.
- Quan sát connection, khóa, transaction và truy vấn chậm.
- Chạy migration, so sánh schema hoặc hỗ trợ vận hành.

Nhưng công cụ không tự tạo thêm quyền mà database không cấp. Một giao diện có nút “Delete Table” không có nghĩa mọi tài khoản nhấn nút đều được phép xóa bảng; PostgreSQL vẫn kiểm tra quyền và ownership khi xử lý lệnh.

## 5. psql: client dòng lệnh chính thức

`psql` là một chương trình dòng lệnh kết nối tới PostgreSQL, gửi SQL và hỗ trợ nhiều lệnh tiện ích riêng của client.

Kết nối vào database:

~~~bash
psql \
  -h db.example.internal \
  -p 5432 \
  -U app_user \
  -d sales_db
~~~

Câu lệnh trên giả định DNS, port, tài khoản và chính sách mạng đã được cấu hình phù hợp. Mật khẩu nên được cung cấp qua cơ chế an toàn như credential store hoặc prompt, không chèn thẳng vào command line có thể bị ghi trong shell history.

Bên trong `psql` có thể thực hiện:

~~~sql
SELECT
    current_database() AS database_name,
    current_user AS role_name,
    version() AS server_version;
~~~

Ngoài SQL, `psql` có các **meta-command** bắt đầu bằng dấu `\`:

~~~text
\conninfo    -- Thông tin kết nối hiện tại
\l           -- Liệt kê database
\dn          -- Liệt kê schema
\dt          -- Liệt kê bảng được hiển thị qua search_path
\d orders    -- Xem mô tả quan hệ orders
\du          -- Liệt kê role và một số thuộc tính
\q           -- Thoát psql
~~~

### 5.1. Meta-command không phải SQL

Điểm phân biệt quan trọng:

~~~text
SELECT current_database();
~~~

là SQL được gửi để server xử lý, còn:

~~~text
\dt
~~~

là lệnh do `psql` hiểu và xử lý để thu thập/hiển thị metadata, có thể thực hiện những truy vấn hệ thống ở phía sau. Nếu đưa chuỗi `\dt` vào JDBC như một câu SQL thông thường, server không hiểu đó là SQL hợp lệ.

### 5.2. Công cụ dòng lệnh không quyết định quyền

Nếu một role chỉ có quyền `SELECT` trên một bảng thì dù thao tác qua `psql`, `pgAdmin` hay ứng dụng, lệnh `DROP TABLE` cũng không được phép chỉ vì dùng công cụ “mạnh hơn”.

## 6. pgAdmin: giao diện quản trị đồ họa

`pgAdmin` là một ứng dụng giao diện giúp kết nối và quản lý PostgreSQL:

- Xem database, schema, table, view, function và role.
- Dùng Query Tool để chạy SQL.
- Hiển thị một số dashboard về hoạt động server và session.
- Hỗ trợ thao tác tạo/sửa đối tượng thông qua form.
- Cung cấp những thao tác backup/restore trong phạm vi công cụ và cấu hình hỗ trợ.

Phân biệt:

| Việc làm | Vai trò của pgAdmin | Vai trò của PostgreSQL |
|---|---|---|
| Hiển thị danh sách bảng | Giao diện truy vấn catalog và hiển thị | Cung cấp metadata |
| Chạy `SELECT` | Gửi SQL, nhận và hiển thị kết quả | Phân tích, tối ưu, thực thi SQL |
| Tạo bảng qua GUI | Sinh/gửi thao tác phù hợp | Kiểm tra quyền, tạo đối tượng |
| Xem số connection | Đọc và trực quan hóa thống kê | Quản lý connection, cung cấp view |
| Đóng ứng dụng quản trị | Kết thúc phiên client tương ứng | Database server vẫn hoạt động |

**Đóng pgAdmin không phải là dừng PostgreSQL.** Và cài pgAdmin không đồng nghĩa PostgreSQL server đã được cài cùng máy.

### 6.1. GUI không làm thao tác an toàn tuyệt đối

Một câu `DELETE` thiếu `WHERE` vẫn có thể xóa nhiều hàng dù được chạy từ một giao diện có nút xác nhận. Nên dùng quyền tối thiểu, xem câu SQL được tạo, kiểm tra môi trường và quản lý transaction phù hợp.

## 7. Những công cụ khác trong hệ sinh thái

Không phải mọi công cụ đều làm cùng một việc.

| Công cụ/nhóm | Chức năng chính | Không nên nhầm với |
|---|---|---|
| `psql` | Truy vấn SQL và quản trị qua CLI | PostgreSQL server |
| `pgAdmin` | GUI quản trị PostgreSQL | Database engine |
| DBeaver, DataGrip | IDE/client làm việc với nhiều database | Máy chủ lưu dữ liệu |
| `pg_dump` | Sao lưu logic một database hoặc phạm vi đối tượng được hỗ trợ | Sao lưu vật lý toàn cluster |
| `pg_restore` | Nạp lại dump ở định dạng phù hợp | Công cụ tự động PITR toàn instance |
| `pg_dumpall` | Xuất thông tin toàn cluster theo hình thức logic, bao gồm global objects | Bản copy vật lý của data directory |
| `pg_basebackup` | Tạo base backup vật lý qua giao thức replication | Sao lưu từng bảng bằng SQL |
| `pg_isready` | Kiểm tra phản hồi/chấp nhận kết nối theo mức của công cụ | Bài kiểm tra nghiệp vụ đầu cuối |
| `pg_ctl`, `initdb` | Khởi tạo/điều khiển server trên môi trường có quyền phù hợp | Công cụ thường được phép dùng trên managed service |
| Flyway, Liquibase | Quản lý migration schema qua lịch sử phiên bản | Công cụ vận hành HA mặc định |
| pgBackRest, Barman | Tổ chức backup, restore và WAL/PITR theo cấu hình | Bản thân database engine |
| PgBouncer | Connection pooling/proxy | Nơi lưu bảng dữ liệu chính |
| Prometheus exporter, dashboard | Thu thập/hiển thị metrics | Hệ thống quyết định commit |

Các công cụ như DBeaver và DataGrip là client có thể hỗ trợ nhiều hệ quản trị; **chúng không chuyển PostgreSQL thành một database khác**. Những công cụ backup chuyên dụng còn phụ thuộc quyền, phiên bản và môi trường triển khai.

### 7.1. Lệnh giống nhau nhưng thực hiện ở nơi khác nhau

Không phải cứ một công cụ nói “backup” thì backup được tạo ở cùng máy hay theo cùng hình thức. Có thể bản dump được ghi tại máy client, tại server quản trị, vào object storage hoặc vào hệ thống backup provider. Cần xác định chính xác **nơi file nằm, ai có quyền đọc, dữ liệu có nhất quán và đã thử restore chưa**.

## 8. Ví dụ phân biệt thao tác client và server: COPY với \copy

Đây là ví dụ thực tế về ranh giới giữa server và `psql`.

### 8.1. COPY là câu SQL do server xử lý

~~~sql
COPY public.customer_account (email)
FROM '/srv/import/customer.csv'
WITH (FORMAT csv, HEADER true);
~~~

Đường dẫn trong lệnh này là đường dẫn theo **môi trường file của PostgreSQL server**. Đọc file server-side cần quyền phù hợp và bị hạn chế để bảo vệ hệ thống. Nếu database chạy trên managed service, thường không thể tùy tiện đặt một file trên ổ đĩa nội bộ của server để chạy kiểu này.

### 8.2. \copy là tiện ích của psql

Trong `psql`:

~~~text
\copy public.customer_account(email) FROM './customer.csv' WITH (FORMAT csv, HEADER true)
~~~

`\copy` làm việc với file tại **máy chạy psql** và truyền dữ liệu qua kết nối tới PostgreSQL. Cách này phù hợp khi client có file CSV còn server ở nơi khác.

Lưu ý: cả hai cách vẫn có thể tác động dữ liệu và cần quyền INSERT phù hợp; chúng khác nhau ở **nơi xử lý file và cơ chế truyền dữ liệu**, không phải một cách bỏ qua quyền database.

## 9. Công cụ quản trị không thay thế migration

Tạo bảng bằng GUI có thể nhanh khi thử nghiệm, nhưng trong ứng dụng nhóm phát triển, thay đổi schema cần có lịch sử và quy trình triển khai có thể lặp lại.

Ví dụ migration:

~~~sql
CREATE TABLE IF NOT EXISTS inventory_item (
    item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Câu SQL có thể được thực thi bởi công cụ migration như Flyway hoặc Liquibase; bản thân PostgreSQL sẽ kiểm tra quyền và thực hiện DDL.

Một quy trình migration tốt cần biết:

- Phiên bản schema mong đợi.
- Thay đổi nào đã áp dụng trên từng môi trường.
- Điều kiện pre/post migration.
- Tác động đến ứng dụng đang chạy.
- Cách rollback/phục hồi dữ liệu khi một migration không thể đảo chiều đơn giản.

**Không nên coi lịch sử click trong pgAdmin là hệ thống version control cho schema.** Với production, migration có kiểm soát thường dễ kiểm chứng và tái lập hơn.

## 10. Dịch vụ PostgreSQL được quản lý là gì?

**Managed PostgreSQL** là mô hình dịch vụ trong đó nhà cung cấp đảm nhận một số việc triển khai và vận hành cơ sở dữ liệu như cấp phát máy, storage, backup, khả năng sẵn sàng cao, giám sát hoặc bảo trì theo hợp đồng sản phẩm.

Ví dụ về dịch vụ sử dụng PostgreSQL hoặc cung cấp môi trường PostgreSQL được quản lý:

- **Amazon RDS for PostgreSQL**.
- **Google Cloud SQL for PostgreSQL**.
- **Azure Database for PostgreSQL**.
- Những nhà cung cấp PostgreSQL managed khác, với kiến trúc và tính năng có thể khác.

Ngoài ra còn có các dịch vụ **PostgreSQL-compatible**: cung cấp giao thức hoặc một tập khả năng tương thích PostgreSQL nhưng có thể sử dụng kiến trúc lưu trữ, cơ chế mở rộng hoặc giới hạn tính năng khác với một PostgreSQL cài đặt tiêu chuẩn. Vì vậy phải đọc mô tả cụ thể của sản phẩm thay vì đồng nhất tất cả thành một server PostgreSQL self-hosted.

### 10.1. Một dịch vụ managed thường cung cấp hai mặt

**Data plane:** endpoint/database xử lý kết nối PostgreSQL, chạy SQL và trả dữ liệu.

**Control plane:** API, dashboard hoặc IaC của nhà cung cấp để tạo instance, chọn cấu hình, mở rộng storage, quản lý backup/restore, mạng, HA và lịch bảo trì.

~~~text
Ứng dụng ── JDBC / SQL ──> Managed PostgreSQL endpoint
                                 |
                                 v
                         PostgreSQL data plane
                         (SQL, transaction, data)
                                 ^
                                 |
Cloud console / API / IaC ────────+
    tạo instance, backup, restore, scaling, networking,
    maintenance theo chức năng dịch vụ
~~~

Một thay đổi qua cloud console có thể tác động đến tài nguyên server, nhưng console **không thay thế SQL engine**. Ngược lại, một câu `CREATE TABLE` có thể chạy trong managed service mà không cần có quyền tạo máy ảo trên cloud.

## 11. Shared responsibility: ai chịu trách nhiệm phần nào?

Đây là điểm quan trọng nhất khi chuyển từ tự cài PostgreSQL sang managed service. Một số nhiệm vụ do nhà cung cấp làm, một số do đội ứng dụng làm; **vùng giao thoa phụ thuộc gói dịch vụ và cấu hình**.

| Hạng mục | Self-hosted PostgreSQL | Managed PostgreSQL |
|---|---|---|
| Cấp phát host/VM/storage | Đội hạ tầng của bạn | Nhà cung cấp theo dịch vụ |
| Cài PostgreSQL server | Đội vận hành | Nhà cung cấp |
| Bảo trì OS và nền tảng | Đội vận hành | Thường do nhà cung cấp quản lý |
| Chọn bản PostgreSQL và lịch nâng cấp | Đội vận hành | Người dùng thường chọn/điều phối trong giới hạn dịch vụ |
| Backup hạ tầng | Đội vận hành tự thiết kế | Có thể do dịch vụ cung cấp, phải bật/cấu hình/kiểm chứng |
| Phục hồi/PITR | Đội vận hành xây dựng và diễn tập | Nhà cung cấp có thể cung cấp thao tác; khách hàng vẫn kiểm tra mục tiêu |
| HA/standby | Đội vận hành thiết kế | Có thể là tính năng tùy gói/cấu hình |
| Schema, table, index | Đội ứng dụng/DBA | **Vẫn là đội ứng dụng/DBA** |
| Câu SQL và hiệu năng truy vấn | Đội ứng dụng/DBA | **Vẫn là đội ứng dụng/DBA** |
| Quyền SQL, dữ liệu nhạy cảm | Đội sở hữu dữ liệu | **Vẫn là trách nhiệm của khách hàng**, phối hợp hệ thống IAM |
| Phân quyền truy cập mạng | Đội vận hành | Khách hàng cấu hình network/IAM trong cơ chế provider |
| Theo dõi lỗi nghiệp vụ | Đội ứng dụng | Đội ứng dụng |
| Kiểm tra khôi phục đầu cuối | Đội sở hữu dịch vụ | Khách hàng vẫn cần xác minh dù thao tác được cung cấp |
| Chi phí sử dụng | Máy, đĩa, công vận hành | Phí dịch vụ, tài nguyên, storage, backup, network |

Không nên đọc bảng theo nghĩa “managed service chắc chắn làm hết backup và HA”. Một tính năng có thể **không được bật mặc định**, có retention khác theo gói hoặc cần khách hàng chọn vùng/thiết lập. Quy tắc vận hành cụ thể là một phần của hợp đồng dịch vụ, không phải bản chất chung của PostgreSQL.

### 11.1. Nhà cung cấp quản lý máy, không quản lý logic nghiệp vụ

Nếu ứng dụng chạy:

~~~sql
DELETE FROM orders;
~~~

trong một phiên có quyền và không có `WHERE`, PostgreSQL sẽ thực thi theo semantics của SQL và giao dịch. Managed service **không tự hiểu** rằng người dùng chỉ muốn xóa một đơn cụ thể. Nhà cung cấp có thể có khả năng phục hồi tới một điểm trước lỗi nếu backup/PITR được cấu hình phù hợp, nhưng đó không phải thay thế cho phân quyền và kiểm soát truy vấn.

### 11.2. Dùng managed không có nghĩa hết cần DBA

Một dịch vụ managed vẫn cần người chịu trách nhiệm:

- Thiết kế schema và khóa.
- Phân tích `EXPLAIN`, index và query plan.
- Quản lý migration.
- Tối ưu transaction và giảm lock contention.
- Kiểm tra autovacuum, bloat và workload theo quyền được cung cấp.
- Quản lý role, RLS nếu có và phân quyền dữ liệu.
- Kiểm tra retention, backup và restore.
- Dự báo dung lượng, performance và chi phí.
- Thử nâng cấp trước khi đổi phiên bản.

Nhà cung cấp có thể giảm gánh nặng hạ tầng, nhưng **không thay thế kiến thức về PostgreSQL và dữ liệu**.

## 12. Phân biệt self-hosted, IaaS và DBaaS

### 12.1. Self-hosted trên máy riêng

Doanh nghiệp cài PostgreSQL trên máy chủ do mình sở hữu hoặc quản lý trực tiếp.

Ưu điểm:

- Kiểm soát sâu OS, binary, extension, filesystem và lịch bảo trì.
- Có thể tùy biến nhiều tham số hệ thống khi cần.
- Chủ động kiến trúc backup, monitoring và HA.

Đổi lại phải đảm nhận nhiều việc: OS patching, database upgrades, backup/PITR, giám sát, sự cố, dung lượng, replication và bảo mật.

### 12.2. PostgreSQL tự cài trên VM cloud

Đây là mô hình **IaaS + self-managed database**. Cloud provider cung cấp VM, volume, networking nhưng **không mặc nhiên vận hành PostgreSQL** thay bạn.

Ví dụ bạn cài PostgreSQL bằng package trên một VM, tự cấu hình `postgresql.conf` và chạy backup. Dù VM thuộc một nhà cung cấp cloud, PostgreSQL vẫn là **self-managed**.

### 12.3. PostgreSQL managed/DBaaS

Bạn dùng dịch vụ database có endpoint, giao diện tạo instance và các tính năng vận hành do nhà cung cấp cung cấp. Thường không cần đăng nhập vào host để cài gói PostgreSQL.

Điểm đánh đổi:

- Đỡ phải quản lý OS và phần lớn tác vụ hạ tầng.
- Có quy trình backup, bảo trì và HA được tích hợp tùy sản phẩm.
- Nhưng giới hạn quyền superuser, filesystem, extensions và một số tham số.
- Phụ thuộc chính sách version, downtime, SLA, khu vực và giá của dịch vụ.

### 12.4. PostgreSQL-compatible không đồng nghĩa 100% PostgreSQL

Một sản phẩm có thể tương thích SQL/giao thức của PostgreSQL nhưng khác ở:

- Storage engine hoặc kiến trúc compute–storage.
- Hỗ trợ extension.
- WAL/replication và tính năng low-level.
- Quyền quản trị.
- Chế độ backup, restore, failover.
- Hành vi hoặc giới hạn một số tính năng nâng cao.

Để chuyển ứng dụng, phải kiểm thử cả SQL, driver, transaction, extension, backup và hiệu năng; không chỉ nhìn thấy cổng 5432 rồi kết luận tương thích hoàn toàn.

## 13. Ranh giới quyền quản trị

Quyền trên managed service thường được chia thành các nhóm:

1. **Quyền cloud/control plane:** tạo/xóa instance, thay đổi storage, network, backup, maintenance.
2. **Quyền SQL trong PostgreSQL:** `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `CREATE`, `ALTER`, `GRANT` và quyền trên đối tượng.
3. **Quyền hệ điều hành/host:** đọc file trong data directory, thao tác process, cài package.
4. **Quyền giám sát và vận hành:** đọc log, metrics, trạng thái backup hoặc tham số.

Một người có quyền cloud tạo instance chưa chắc có quyền `SELECT` mọi bảng ứng dụng. Ngược lại, một role PostgreSQL có quyền sửa schema không nhất thiết có quyền thay kích thước máy qua API cloud.

### 13.1. SUPERUSER trong self-hosted và managed

Trong bản PostgreSQL tự quản lý, role `SUPERUSER` có quyền rất rộng. Nhiều dịch vụ managed **hạn chế quyền superuser thực sự** để bảo vệ hạ tầng đa khách hàng và tính ổn định của dịch vụ; tài khoản quản trị được cung cấp có thể mang một bộ quyền đặc biệt nhưng không hoàn toàn giống superuser của self-hosted.

Hệ quả:

- Không phải extension nào cũng tạo được.
- Có thể không truy cập được tệp hệ thống hoặc thư mục dữ liệu.
- Không thể sử dụng mọi lệnh cấu hình/low-level.
- Một số thao tác cần API của nhà cung cấp thay vì SQL hoặc SSH.

**Đừng thiết kế ứng dụng yêu cầu superuser để chạy hằng ngày.** Hãy tạo role ứng dụng có quyền tối thiểu và chỉ dùng tài khoản quản trị cho migration/vận hành khi cần.

## 14. Vai trò database role và phân quyền SQL

PostgreSQL sử dụng **role** để mô hình hóa người dùng và nhóm quyền.

Ví dụ minh họa trên môi trường bạn có quyền quản trị phù hợp:

~~~sql
CREATE ROLE reporting_reader LOGIN;

GRANT CONNECT ON DATABASE sales_db TO reporting_reader;

-- Thực hiện trong database sales_db:
GRANT USAGE ON SCHEMA public TO reporting_reader;

GRANT SELECT ON TABLE public.customer_account
TO reporting_reader;
~~~

Tài khoản mới cần được thiết lập phương thức xác thực/password hoặc tích hợp IAM theo cách vận hành được cho phép; ví dụ không nhúng mật khẩu vào tệp bài học.

Trong PostgreSQL, quyền trên database, schema, table, sequence và function là các phạm vi khác nhau. Có quyền `CONNECT` vào database không tự có quyền đọc mọi bảng.

Một báo cáo chỉ đọc cần role `SELECT`; ứng dụng ghi đơn cần những quyền thích hợp trên bảng/sequence mà nó sử dụng. Nhà cung cấp managed không quyết định tự động tất cả quyền này theo logic ứng dụng.

### 14.1. Gợi ý kiểm tra phiên làm việc

~~~sql
SELECT
    current_database() AS db,
    current_user AS active_role,
    session_user AS login_role;

SELECT
    has_database_privilege(
        current_user,
        current_database(),
        'CONNECT'
    ) AS can_connect;

SELECT
    has_table_privilege(
        current_user,
        'public.customer_account',
        'SELECT'
    ) AS can_read_customer_account;
~~~

Truy vấn cuối yêu cầu bảng minh họa đã được tạo trong database hiện tại. Nếu không tồn tại, cần thay bằng tên bảng thực.

## 15. Mạng và kết nối: ai mở đường cho ứng dụng?

Kết nối PostgreSQL qua TCP thường gồm:

~~~text
Ứng dụng
  |
  +-- DNS / endpoint
  +-- IP route / VPC / firewall
  +-- TLS
  +-- Authentication
  +-- Database role & privileges
  |
  v
PostgreSQL server
~~~

Một lỗi “không kết nối được” có thể do các tầng khác nhau:

| Triệu chứng | Lớp cần kiểm tra |
|---|---|
| Không phân giải được host | DNS/endpoint |
| Timeout khi mở TCP | Network, firewall, security group, routing |
| Server từ chối kết nối | Port, listener, proxy, trạng thái server |
| TLS handshake thất bại | Certificate, CA, SSL mode, cấu hình bảo mật |
| Xác thực thất bại | Username, password, auth policy, role |
| Kết nối được nhưng `SELECT` bị từ chối | Quyền SQL trên schema/table |
| Kết nối ổn nhưng truy vấn chậm | SQL, chỉ mục, lock, tài nguyên server |

Trong self-hosted, đội vận hành có thể sửa `listen_addresses` hoặc `pg_hba.conf` (theo quyền và quy trình). Trong managed service, những thành phần này thường được cung cấp qua cấu hình, network policy hoặc cơ chế của nhà cung cấp, không nhất thiết truy cập trực tiếp được file.

### 15.1. Connection string minh họa

~~~text
postgresql://app_user@db.example.internal:5432/sales_db?sslmode=verify-full
~~~

Đây là chuỗi minh họa không có password. Khi chọn `verify-full`, client cần xác minh được chứng chỉ và tên host của server bằng CA tin cậy, cấu hình theo môi trường thật.

Không tắt TLS certificate verification chỉ để giải quyết nhanh lỗi kết nối trong production. Cần phân biệt lỗi DNS, TLS, authentication và quyền database rồi sửa tại đúng lớp.

## 16. PostgreSQL có backup, nhưng ai thực hiện và kiểm chứng?

PostgreSQL cung cấp cơ chế dữ liệu/log hỗ trợ backup và recovery, nhưng “server hỗ trợ recovery” khác với “đã có hệ thống backup vận hành tốt”.

### 16.1. Sao lưu logic bằng pg_dump

Ví dụ backup một database dưới dạng custom format:

~~~bash
pg_dump \
  -h db.example.internal \
  -p 5432 \
  -U backup_user \
  -d sales_db \
  -F c \
  -f sales_db.dump
~~~

`pg_dump` là **client utility**. Nó kết nối tới server để đọc lược đồ và dữ liệu, rồi tạo file tại nơi chạy lệnh. Dùng `-F c` để tạo archive dạng custom có thể nạp bằng `pg_restore`.

Ví dụ restore vào database đích đã chuẩn bị:

~~~bash
pg_restore \
  -h restore-db.example.internal \
  -U restore_user \
  -d sales_restore \
  sales_db.dump
~~~

Cần quyền, phiên bản công cụ, phạm vi đối tượng và chiến lược restore phù hợp. `pg_dump` chủ yếu dùng cho **một database**; global objects như role/tablespace cần được xử lý bằng phương án riêng, chẳng hạn `pg_dumpall --globals-only` khi phù hợp.

### 16.2. Sao lưu vật lý và WAL

PostgreSQL sử dụng **WAL** để hỗ trợ crash recovery và các hình thức backup/replication. Trong môi trường tự quản lý, có thể dùng `pg_basebackup` hoặc công cụ chuyên dụng như pgBackRest/Barman để tổ chức base backup, lưu WAL và point-in-time recovery (PITR).

Không được coi việc sao chép trực tiếp data directory trong lúc server đang ghi là một bản backup vật lý nhất quán nếu không theo cơ chế được hỗ trợ.

### 16.3. Managed backup không thay thế restore test

Nhà cung cấp managed có thể hỗ trợ snapshot, automated backup, retention và PITR theo dịch vụ. Nhưng người sở hữu ứng dụng vẫn phải kiểm tra:

- Backup/PITR có được bật không?
- Thời gian lưu giữ và điểm khôi phục nào có sẵn?
- Có thể restore ra instance riêng không?
- Thời gian tải/khởi tạo/restoring là bao lâu?
- Mức RPO và RTO thực tế có đạt mục tiêu không?
- Sau restore, schema, role, extension và ứng dụng hoạt động đúng không?

**Một nút “Restore” trên giao diện cloud không bảo đảm rằng khôi phục sẽ đáp ứng mọi tình huống nghiệp vụ.** Cần diễn tập và đối soát dữ liệu.

## 17. High Availability, replica và failover

PostgreSQL có cơ chế replication, nhưng **tự có PostgreSQL không đồng nghĩa hệ thống đã có HA tự động**.

Một topology có thể gồm:

~~~text
Ứng dụng
   |
   v
Primary PostgreSQL
   |
   +------ WAL / replication ------> Standby A
   |
   +------ WAL / replication ------> Standby B
~~~

Trong self-hosted, nhóm vận hành phải thiết kế và cấu hình:

- Streaming replication hoặc cơ chế replication phù hợp.
- Điều phối primary/standby.
- Health checks, failover và fencing để tránh split-brain.
- Endpoint/routing sau failover.
- Monitoring replication lag.
- Backup/PITR độc lập.
- Quy trình failback và kiểm chứng dữ liệu.

Managed service có thể tự động hóa nhiều phần HA và failover **khi được cấu hình theo sản phẩm**, nhưng vẫn cần hiểu:

- Gói dịch vụ có standby hay không?
- Failover có thể ngắt kết nối bao lâu?
- Replica đồng bộ hay bất đồng bộ, và RPO thực tế?
- Ứng dụng có retry/reconnect phù hợp không?
- Endpoint có thay đổi vai trò hay không?
- Có điều kiện giới hạn nào khi mở rộng đọc?

Replica **không phải backup thay thế**. Thao tác xóa nhầm có thể được sao chép sang replica; cần bản backup với lịch sử/điểm khôi phục độc lập.

## 18. Giám sát: ai tạo metrics, ai hiểu metrics?

PostgreSQL có nhiều view hệ thống như:

- `pg_stat_activity`: thông tin session, trạng thái và truy vấn đang chạy theo phạm vi quyền.
- `pg_stat_database`: thống kê ở mức database.
- `pg_stat_user_tables`: hoạt động bảng và vacuum/analyze.
- `pg_stat_replication`: thông tin replication từ primary.
- `pg_locks`: thông tin lock.
- `pg_stat_statements`: extension thống kê câu lệnh nếu được hỗ trợ và kích hoạt.

Ví dụ:

~~~sql
SELECT
    datname,
    state,
    COUNT(*) AS so_session
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY datname, state
ORDER BY state;
~~~

Các vai trò không có quyền quan sát mở rộng có thể không nhìn được mọi chi tiết SQL hoặc thông tin của session khác.

### 18.1. pgAdmin hiển thị metrics, nhưng không tạo bản chất metrics

Một dashboard có thể vẽ số connection và query duration. Dữ liệu có thể đến từ catalog/view của PostgreSQL hoặc một hệ thống metrics bên ngoài. Khi dashboard ngắt kết nối, server vẫn đang quản lý connection thật.

### 18.2. Managed cloud có metrics riêng

Nhà cung cấp có thể cung cấp CPU, storage utilization, latency, replication lag, backup status và cảnh báo qua control plane. Nhưng cần phân biệt:

- **Chỉ số hạ tầng:** CPU, I/O, network, disk.
- **Chỉ số database:** transaction, lock, vacuum, bloat, slow query.
- **Chỉ số ứng dụng:** p95 latency, lỗi nghiệp vụ, connection pool, tỷ lệ giao dịch thành công.

Một hệ thống có CPU thấp không chứng minh truy vấn SQL đúng hoặc không có lock contention. Giám sát production cần kết hợp cả ba tầng.

## 19. Autovacuum: tính năng của engine, trách nhiệm cấu hình của ai?

PostgreSQL dựa vào MVCC để hỗ trợ giao dịch đồng thời. Các phiên bản hàng không còn cần thiết cần được dọn dẹp; autovacuum hỗ trợ việc vacuum/analyze tự động theo cấu hình.

**Autovacuum là cơ chế của PostgreSQL server**, không phải một nút của pgAdmin. Managed service thường vận hành daemon/server và cung cấp tham số cấu hình trong phạm vi cho phép. Nhưng đội ứng dụng vẫn phải quan sát nếu:

- Có bảng cập nhật/xóa liên tục.
- Dead tuples tăng, vacuum không theo kịp.
- Statistics lỗi thời làm truy vấn chậm.
- Transaction tồn tại quá lâu ảnh hưởng cleanup.
- Cấu hình hoặc workload làm tăng table/index bloat.

Ví dụ quan sát bảng:

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
~~~

Các trường như `n_live_tup` và `n_dead_tup` là **ước lượng thống kê**, không phải kết quả `COUNT(*)` chính xác. Công cụ chỉ trình bày số liệu; việc quyết định cần index, tuning hoặc điều chỉnh workload vẫn là trách nhiệm kỹ thuật.

## 20. Extension: PostgreSQL hỗ trợ mở rộng, nhưng managed có thể giới hạn

PostgreSQL có cơ chế extension, ví dụ các thành phần hỗ trợ thống kê, kiểu dữ liệu hoặc tính năng bổ sung. Tuy nhiên:

- Extension cần được cài và hỗ trợ ở server.
- Một số yêu cầu quyền cao hoặc cấu hình startup.
- Managed service có thể chỉ cho phép danh sách extension đã duyệt.
- Phiên bản extension có thể bị ràng buộc bởi phiên bản PostgreSQL và sản phẩm managed.
- Việc nâng cấp extension và database phải được lập kế hoạch tương thích.

Kiểm tra extension đã được cài trong database:

~~~sql
SELECT extname, extversion
FROM pg_extension
ORDER BY extname;
~~~

Xem những extension server báo có thể cung cấp:

~~~sql
SELECT
    name,
    default_version,
    installed_version
FROM pg_available_extensions
ORDER BY name;
~~~

Danh sách “available” không đảm bảo role hiện tại được phép chạy `CREATE EXTENSION` thành công; quyền và policy provider vẫn có thể hạn chế.

Ví dụ về `pg_stat_statements`:

~~~sql
-- Chỉ thực hiện khi extension được hỗ trợ, đủ quyền
-- và cấu hình shared_preload_libraries phù hợp.
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

Một số extension yêu cầu `shared_preload_libraries` và restart. Trên self-hosted có thể quản lý cấu hình server theo quy trình; trên managed có thể cần thay parameter group hoặc dùng control plane, tùy dịch vụ.

## 21. Tham số server và giới hạn trên managed service

Với PostgreSQL tự quản lý, nhiều tham số có thể được thiết lập qua file cấu hình, startup option hoặc `ALTER SYSTEM` khi có quyền thích hợp. Ví dụ:

~~~sql
SHOW max_connections;
SHOW shared_buffers;
SHOW work_mem;
SHOW statement_timeout;
~~~

Trong managed service:

- Một số tham số có thể thay qua API/cloud console.
- Một số tham số chỉ thay khi restart hoặc ở maintenance window.
- Có thể có giá trị tối thiểu/tối đa hoặc tham số không cho chỉnh.
- Những thành phần low-level như file hệ thống/OS không được cung cấp quyền truy cập trực tiếp.
- Thay đổi cấu hình có thể làm tăng chi phí, ảnh hưởng hiệu năng hoặc downtime.

**Không giả định có thể chạy `ALTER SYSTEM` trong managed PostgreSQL.** Hãy dùng phương thức được nhà cung cấp hỗ trợ và kiểm tra phạm vi của thay đổi.

Đối với ứng dụng, `SET LOCAL statement_timeout` trong transaction hoặc cấu hình role/database có thể được phép theo chính sách, nhưng vẫn cần xác nhận quyền và tác động. Ranh giới giữa tham số session, database, role và toàn server phải được hiểu rõ.

## 22. Mở kết nối thành công chưa đủ để đánh giá môi trường

Một cách xác định môi trường đang kết nối là chạy các câu SQL:

~~~sql
SELECT
    version() AS server_version,
    current_database() AS db_name,
    current_user AS role_name,
    inet_server_addr() AS server_ip,
    inet_server_port() AS server_port,
    pg_is_in_recovery() AS standby_mode;
~~~

Giải thích:

- `version()`: thông tin phiên bản/build server.
- `current_database()`: database của kết nối.
- `current_user`: role có hiệu lực.
- `inet_server_addr()` và `inet_server_port()`: địa chỉ/port của kết nối mạng theo cách server nhìn thấy; có thể `NULL` với Unix socket.
- `pg_is_in_recovery()`: có đang ở trạng thái recovery/standby không; không thay thế kiểm tra topology toàn hệ thống.

Lệnh trên **không tự xác định đầy đủ nhà cung cấp managed** hoặc gói dịch vụ. Một instance PostgreSQL self-hosted và managed có thể trả dữ liệu SQL rất giống nhau; phải đối chiếu endpoint, console, IaC và tài liệu vận hành của hệ thống.

## 23. Ứng dụng Java/JDBC là client, không phải server

Trong ứng dụng Java, driver PostgreSQL JDBC chuyển lời gọi JDBC thành giao thức kết nối tương ứng và gửi SQL tới PostgreSQL server.

Ví dụ:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public final class PostgreSqlDemo {
    public static void main(String[] args) throws Exception {
        String url = System.getenv("POSTGRES_JDBC_URL");
        String user = System.getenv("POSTGRES_USER");
        String password = System.getenv("POSTGRES_PASSWORD");

        try (Connection connection =
                     DriverManager.getConnection(url, user, password);
             PreparedStatement statement =
                     connection.prepareStatement(
                         "SELECT current_database(), current_user, now()")) {

            try (ResultSet rs = statement.executeQuery()) {
                if (rs.next()) {
                    System.out.println("Database: " + rs.getString(1));
                    System.out.println("Role: " + rs.getString(2));
                    System.out.println("Time: " + rs.getTimestamp(3));
                }
            }
        }
    }
}
~~~

Ví dụ giả định đã thêm PostgreSQL JDBC driver phù hợp vào classpath, thiết lập đúng biến môi trường và tài khoản. Cấu hình network, TLS, authentication và quyền SQL vẫn phải do môi trường cung cấp.

Điều cần hiểu:

- JDBC driver **không lưu bảng** và không thay PostgreSQL server.
- Connection pool quản lý/tái sử dụng kết nối client, không phải một database.
- Transaction `commit()` và `rollback()` gửi yêu cầu tới server để áp dụng trên transaction của connection.
- Nếu server tắt hoặc endpoint thay đổi, JDBC có thể cần reconnect và retry theo chính sách.
- Migrate từ self-hosted sang managed thường vẫn dùng PostgreSQL JDBC, nhưng endpoint, TLS, auth, policy, extension và hiệu năng cần được thử lại.

## 24. Ví dụ chuyển từ self-hosted sang managed

Giả sử một nhóm đang có:

~~~text
VM nội bộ:
  PostgreSQL
  pgAdmin của DBA kết nối qua mạng nội bộ
  Ứng dụng Java kết nối tới VM
  Backup bằng pg_dump + WAL lưu vào kho riêng
~~~

Họ muốn chuyển sang managed PostgreSQL để giảm công sức bảo trì OS, backup và HA.

### 24.1. Những thứ về nguyên tắc vẫn giữ

- Schema quan hệ, bảng, chỉ mục và khóa.
- SQL nghiệp vụ phù hợp với PostgreSQL phiên bản đích.
- Ứng dụng dùng JDBC.
- Vai trò client của pgAdmin/psql.
- Nhu cầu quản lý transaction, query plan và quyền.

### 24.2. Những thứ cần thay đổi hoặc kiểm tra

- Endpoint, private network, firewall, DNS và TLS.
- Phương thức authentication, tài khoản và quyền.
- Phiên bản PostgreSQL và extension được phép dùng.
- Dữ liệu và global objects được chuyển như thế nào.
- Khả năng lưu WAL/PITR/retention.
- Thời gian cắt chuyển và cách hạn chế ghi phân kỳ.
- Backup do provider cung cấp có đáp ứng RPO/RTO không.
- Công cụ giám sát và metrics có thay đổi nguồn không.
- Chi phí compute, storage, backup và network.
- Giới hạn quyền OS/superuser ảnh hưởng automation cũ.

### 24.3. Không thể chỉ đổi connection string

Nếu SQL cũ dùng extension không được managed hỗ trợ hoặc script backup tự đọc data directory, chuyển endpoint sẽ không làm những bước đó tự hoạt động. Mặt khác, nếu ứng dụng tuân thủ SQL chuẩn phù hợp và không phụ thuộc đặc tính low-level, việc đổi môi trường có thể tương đối thuận lợi.

Phải kiểm thử trên bản sao dữ liệu đại diện trước khi chuyển production.

## 25. Khi nào nên chọn từng mô hình?

| Bối cảnh | Lựa chọn nên cân nhắc | Vì sao |
|---|---|---|
| Học SQL, thử nghiệm trên laptop | PostgreSQL local + psql/pgAdmin | Chủ động thực hành, chi phí thấp |
| Ứng dụng nhóm nhỏ thiếu nhân sự DBA/SRE | Managed PostgreSQL | Giảm công việc hạ tầng nếu phù hợp ngân sách |
| Hệ thống cần extension đặc biệt hoặc quyền OS sâu | Self-managed hoặc managed hỗ trợ cụ thể | Khả năng tùy biến là yếu tố quyết định |
| Hệ thống yêu cầu HA và backup nhưng đội chưa có khả năng vận hành | Managed có HA/PITR được cấu hình và thử nghiệm | Có thể giảm công sức xây dựng |
| Môi trường bị hạn chế network/compliance | Tùy chọn triển khai được phê duyệt | Quy định dữ liệu và truy cập có thể quan trọng hơn tiện lợi |
| Database rất lớn, truy vấn nặng và chi phí nhạy cảm | Benchmark cả hai | So sánh tài nguyên, performance, storage, network và công vận hành |
| Cần PostgreSQL-compatible nhưng kiến trúc storage đặc biệt | Kiểm thử khả năng tương thích của sản phẩm | Không mặc định mọi extension/hành vi giống PostgreSQL chuẩn |

**Không có một mô hình tốt nhất cho mọi hệ thống.** Managed thường giảm việc quản lý server nhưng tăng phụ thuộc dịch vụ/giá và có thể giới hạn tùy biến; self-hosted cho quyền kiểm soát sâu nhưng đòi hỏi chuyên môn vận hành.

## 26. Chi phí và độ tin cậy không chỉ là tiền thuê máy

Khi so sánh, cần tính tổng chi phí sở hữu (TCO):

- Compute, RAM, SSD/storage.
- Backup storage, retention, network egress.
- HA/standby và read replica.
- Monitoring, log retention.
- Nhân sự cài đặt, patch, on-call, xử lý sự cố.
- Chi phí downtime khi lỗi hoặc nâng cấp.
- Khả năng mở rộng và thu hẹp tài nguyên.
- Rủi ro vendor-specific feature gây khó di chuyển.

Một PostgreSQL tự quản lý trên VM có thể trông rẻ về giá máy, nhưng nếu không có on-call và restore test, rủi ro vận hành có thể cao. Ngược lại, một dịch vụ managed không được cấu hình backup hoặc HA phù hợp vẫn có thể không đạt độ tin cậy kỳ vọng dù phí dịch vụ cao.

## 27. Những hiểu nhầm thường gặp

### Hiểu nhầm 1: “pgAdmin chính là PostgreSQL”

Không. pgAdmin là client GUI; PostgreSQL server mới là nơi thực thi SQL và lưu dữ liệu.

### Hiểu nhầm 2: “Cài psql là đã có database”

Không. `psql` chỉ là client. Cần một PostgreSQL server đang chạy ở local hoặc remote để kết nối.

### Hiểu nhầm 3: “Dùng cloud là managed PostgreSQL”

Không. PostgreSQL tự cài trên VM cloud vẫn là self-managed ở tầng database. Managed service là một sản phẩm vận hành database với phạm vi trách nhiệm được xác định.

### Hiểu nhầm 4: “Managed nghĩa là không cần quan tâm backup”

Không. Khách hàng vẫn phải chọn retention, kiểm tra điểm phục hồi, thực hiện restore test và xác nhận RPO/RTO theo sản phẩm.

### Hiểu nhầm 5: “Managed có HA nên không thể mất dữ liệu”

Không. HA giúp xử lý sự cố thành phần theo thiết kế nhưng không bảo vệ mặc định khỏi mọi thao tác xóa nhầm, lỗi nghiệp vụ, replication lag hoặc mất dữ liệu khi khôi phục.

### Hiểu nhầm 6: “Tài khoản admin cloud là PostgreSQL superuser”

Không nhất thiết. Cloud IAM và PostgreSQL roles là hai lớp quyền khác nhau; nhiều dịch vụ giới hạn superuser.

### Hiểu nhầm 7: “Dùng pgAdmin thì không cần hiểu SQL”

Không. GUI có thể sinh SQL và thao tác mạnh trên dữ liệu; hiểu SQL, giao dịch và quyền vẫn cần để đánh giá tác động.

### Hiểu nhầm 8: “Mọi extension PostgreSQL chạy được trên managed”

Không. Phụ thuộc danh sách hỗ trợ, quyền, phiên bản và cấu hình của dịch vụ.

### Hiểu nhầm 9: “Read replica chính là backup”

Không. Replica có thể áp dụng cả thay đổi sai từ primary; backup lịch sử có mục đích khác.

### Hiểu nhầm 10: “PostgreSQL-compatible nghĩa là hoàn toàn tương đương”

Không mặc nhiên. Cần test tính năng, transaction, extension, công cụ và hiệu năng trên đúng sản phẩm.

### Hiểu nhầm 11: “Lỗi kết nối luôn do database server”

Không. Có thể do DNS, network, TLS, authentication, endpoint hoặc pool phía client.

### Hiểu nhầm 12: “Công cụ admin không thể gây lỗi dữ liệu”

Không. Công cụ có thể gửi SQL nguy hiểm nếu người dùng có quyền; tính an toàn dựa vào quyền, quy trình, transaction và backup.

### Hiểu nhầm 13: “Managed provider tự tối ưu mọi truy vấn”

Không. Nhà cung cấp có thể hỗ trợ metrics hoặc tuning, nhưng thiết kế schema/index/query và logic ứng dụng vẫn thuộc người sở hữu dữ liệu.

## 28. Checklist nhận diện đúng lớp khi xử lý sự cố

Khi gặp lỗi, dùng một trình tự có hệ thống.

### Bước 1: Xác định đúng môi trường

- Endpoint đang kết nối là local, VM, managed hay proxy?
- Kết nối đang tới database và role nào?
- Có đang đi qua PgBouncer hay router không?
- Có đúng môi trường staging/production không?

### Bước 2: Xác định tầng lỗi

- Network/DNS: có đến được host và port không?
- TLS/auth: handshake và đăng nhập thành công không?
- PostgreSQL: có chấp nhận connection và chạy SQL không?
- SQL privileges: có quyền trên schema/table không?
- Application: câu truy vấn, pool và timeout có phù hợp không?

### Bước 3: Xem nơi được phép điều chỉnh

- Self-hosted: có thể cần thay config file/service theo quy trình.
- Managed: có thể cần thay network policy, parameter hoặc dùng API/console.
- SQL: có thể sửa role/schema/query với quyền phù hợp.
- Client: có thể cần sửa connection string, driver, trust store hoặc pool.

### Bước 4: Xác minh sau thay đổi

- Query đơn giản chạy thành công.
- Luồng nghiệp vụ quan trọng hoạt động.
- Metrics và log không cho thấy lỗi mới.
- Không tạo quyền quá rộng hoặc tắt xác minh TLS.
- Backup/restore vẫn có thể sử dụng.

Cách phân tầng giúp tránh xử lý nhầm, chẳng hạn sửa SQL role để khắc phục lỗi firewall hoặc tăng CPU cloud khi vấn đề là một truy vấn thiếu index.

## 29. Bài tập thực hành

### Bài 1: Phân loại thành phần

Hãy phân loại `postgres` server, `psql`, `pgAdmin`, `pg_dump`, PgBouncer, Cloud SQL PostgreSQL và một ứng dụng Java JDBC vào các nhóm: **database engine, client/tool, proxy hoặc managed service**.

**Gợi ý:** dữ liệu được thực thi/lưu tại PostgreSQL server; `pgAdmin` và `psql` là client; PgBouncer là pool/proxy; Cloud SQL là dịch vụ managed.

### Bài 2: Đọc meta-command

Người học gửi chuỗi `\dt` bằng `PreparedStatement` trong Java và nhận lỗi cú pháp. Vì sao?

**Gợi ý:** `\dt` là lệnh meta của `psql`, không phải SQL. Dùng SQL truy vấn catalog hoặc chạy trong `psql`.

### Bài 3: Backup nằm ở đâu?

Một DBA chạy `pg_dump -F c -f backup.dump` từ laptop đến một PostgreSQL remote. File backup được tạo trên máy nào?

**Gợi ý:** tại máy thực thi `pg_dump`, theo đường dẫn của tiến trình client, không tự động nằm trong data directory của server.

### Bài 4: Quyền cloud và SQL

Người dùng có quyền xem resource PostgreSQL trong cloud console nhưng chạy `SELECT` trên bảng ứng dụng bị từ chối. Có mâu thuẫn không?

**Gợi ý:** không. Quyền control plane và quyền SQL là hai lớp khác nhau. Cần kiểm tra role và grants trong PostgreSQL.

### Bài 5: Self-managed hay managed?

Doanh nghiệp tạo VM trên cloud, tự cài PostgreSQL, tự làm backup và tự nâng phiên bản. Đây có phải DBaaS không?

**Gợi ý:** không; đó là self-managed PostgreSQL chạy trên IaaS.

### Bài 6: COPY và \copy

Bạn có file CSV trên laptop, nhưng database chạy trên managed service. Vì sao `COPY FROM '/home/me/file.csv'` có thể không hoạt động?

**Gợi ý:** `COPY` đọc file phía server, không phải laptop. `\copy` của `psql` dùng file client và gửi dữ liệu qua kết nối, nếu role có quyền phù hợp.

### Bài 7: Extension

Ứng dụng cần một extension không có trong danh sách cho phép của managed service. Có thể cài bằng cách mở pgAdmin và nhấn Create Extension không?

**Gợi ý:** GUI không vượt qua giới hạn server/provider. Cần kiểm tra hỗ trợ của sản phẩm, chọn phương án tương đương hoặc thay mô hình triển khai.

### Bài 8: Backup và replica

Một DBA nói “hệ thống có hai read replica nên không cần backup”. Bạn phản biện bằng tình huống nào?

**Gợi ý:** thao tác `DROP TABLE` hoặc `DELETE` nhầm có thể được sao chép tới replica. Backup/PITR phục vụ khả năng quay về điểm dữ liệu trước lỗi.

### Bài 9: Lỗi kết nối

Ứng dụng báo timeout trước khi nhận được phản hồi PostgreSQL, trong khi DBA dùng `psql` từ mạng nội bộ vẫn truy vấn được. Nên kiểm tra nhóm nào?

**Gợi ý:** đường mạng của ứng dụng, DNS, firewall/security group, port, proxy, TLS và endpoint trước khi kết luận SQL engine hỏng.

### Bài 10: Chuyển sang managed

Một hệ thống self-hosted sử dụng `pg_hba.conf` trực tiếp, backup đọc file bằng script, extension đặc biệt và kết nối JDBC. Hãy liệt kê những phần có thể giữ lại và những phần cần thay.

**Gợi ý:** JDBC/SQL chuẩn có thể tiếp tục nếu tương thích. Cấu hình network, backup, quyền low-level, plugin/extension và thông tin kết nối cần đánh giá lại theo provider.

## 30. Tổng kết

- **PostgreSQL server** là hệ quản trị thực thi SQL, lưu dữ liệu, quản lý transaction, WAL, chỉ mục và quyền.
- **pgAdmin, psql và các IDE** là công cụ client để gửi lệnh hoặc xem thông tin; chúng không phải nơi dữ liệu được lưu trữ.
- **pg_dump/pg_restore, pg_basebackup, migration tools, proxy và monitoring tools** có các nhiệm vụ khác nhau, không được gọi chung là “database”.
- **Managed PostgreSQL** là mô hình vận hành: nhà cung cấp xử lý nhiều phần hạ tầng và lifecycle, còn đội ứng dụng vẫn sở hữu schema, SQL, bảo mật dữ liệu, cấu hình phù hợp và việc xác minh phục hồi.
- **Cloud IAM, quyền SQL và quyền host** là những lớp truy cập riêng; tài khoản quản trị managed không nhất thiết có superuser đầy đủ.
- **Managed không đồng nghĩa HA, backup và extension luôn sẵn dùng**. Khả năng thực tế phụ thuộc sản phẩm, gói, cấu hình và policy.
- **Replica không thay backup**, GUI không thay kiến thức SQL, và kết nối thành công không chứng minh ứng dụng hoạt động đúng.
- Khi chuyển môi trường, phải kiểm tra **version, extension, quyền, network/TLS, backup/PITR, performance, chi phí và failover**, không chỉ thay connection string.

Câu hỏi có giá trị nhất khi gặp một thao tác PostgreSQL là: **“Việc này được thực hiện bởi database engine, bởi công cụ client, hay bởi nền tảng managed?”**. Khi xác định được đúng lớp và đúng chủ thể chịu trách nhiệm, việc học, triển khai và vận hành PostgreSQL sẽ rõ ràng hơn, đồng thời tránh được những nhầm lẫn nguy hiểm về dữ liệu, quyền và khôi phục.

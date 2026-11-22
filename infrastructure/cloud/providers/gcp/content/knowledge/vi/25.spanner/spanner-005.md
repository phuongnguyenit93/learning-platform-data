# GoogleSQL và PostgreSQL interface trong Spanner

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **GoogleSQL dialect** và **PostgreSQL dialect/interface** của Spanner với máy chủ PostgreSQL trên Cloud SQL.
2. Chọn dialect phù hợp dựa trên cú pháp SQL, bộ công cụ Java, tính di động và tính năng của ứng dụng.
3. Viết DDL/DML cho cùng một mô hình dữ liệu theo hai dialect; sử dụng **primary key**, kiểu dữ liệu, truy vấn có tham số và transactions đúng cách.
4. Kết nối qua **Spanner client/JDBC** hoặc **PostgreSQL JDBC → PGAdapter**, hiểu cơ chế IAM/ADC và các giới hạn giao thức.
5. Tạo database lab, kiểm tra schema, phát hiện incompatibilities khi migrate từ PostgreSQL và đánh giá hiệu năng, độ tin cậy, bảo mật, chi phí.

## 1. Bối cảnh: hai ngôn ngữ SQL, một nền tảng Spanner

Trong mô-đun **CLOUD_PROVIDERS_GCP**, ứng dụng Java có thể chạy trên Compute Engine, GKE hoặc Cloud Run và cần cơ sở dữ liệu bền vững. **Spanner** là hệ quản trị dữ liệu phân tán, được quản lý, hỗ trợ giao dịch quan hệ với khả năng mở rộng ngang và các cấu hình vùng/multiregion. Spanner dùng **cùng một storage và transaction engine** cho hai dialect:

- **GoogleSQL**: ngôn ngữ SQL tích hợp chặt với Spanner và hệ sinh thái Google Cloud.
- **PostgreSQL dialect/interface**: tập con tương thích ngữ pháp, kiểu dữ liệu và giao thức của PostgreSQL, có các phần mở rộng riêng của Spanner.

Ví dụ công ty bán lẻ xây dựng **orders-api** trên Cloud Run, đọc/ghi dữ liệu đơn hàng theo giao dịch; worker trên GKE xử lý sự kiện Pub/Sub; nhóm phân tích dùng BigQuery. Đội phát triển đã biết PostgreSQL nhưng muốn khả năng mở rộng của Spanner. Câu hỏi không chỉ là “câu SQL nào chạy được?”, mà là **thư viện Java nào, migration nào, transaction semantics nào và dialect nào hợp mục tiêu dài hạn?**

~~~mermaid
flowchart TB
    APP["Java orders-api / GKE worker"] --> CHOOSE{"Lựa chọn client"}
    CHOOSE --> NATIVE["Spanner Java Client / JDBC<br/>gRPC, ADC"]
    CHOOSE --> PGJDBC["PostgreSQL JDBC / psql"]
    PGJDBC --> PGAD["PGAdapter<br/>PostgreSQL wire protocol → Spanner gRPC"]
    NATIVE --> ENGINE["Spanner distributed engine"]
    PGAD --> ENGINE
    ENGINE --> GSQL["Database A<br/>GoogleSQL dialect"]
    ENGINE --> PSQL["Database B<br/>PostgreSQL dialect"]
~~~

**Lưu ý:** một **Spanner instance có thể chứa nhiều databases**, mỗi database chọn dialect lúc tạo. **Dialect thuộc về database**, không thuộc cả instance, nhưng không thể trộn cú pháp của hai dialect tùy ý bên trong cùng database. Thay dialect cho database hiện hữu là **công việc tạo database mới và migrate**, không phải thay một setting nhỏ.

## 2. Chọn dialect bằng yêu cầu ứng dụng

| Tiêu chí | **GoogleSQL** | **PostgreSQL interface** |
|---|---|---|
| Cú pháp quen thuộc | GoogleSQL, tương đồng một phần với BigQuery | PostgreSQL SQL, kiểu dữ liệu và nhiều client PostgreSQL |
| Driver có thể dùng | Spanner Java Client/Spanner JDBC | Spanner Java Client/Spanner JDBC; hoặc PostgreSQL JDBC thông qua PGAdapter |
| Công cụ quản trị | Spanner Studio, gcloud, Spanner APIs | Cùng control plane; thêm psql/ORMs được hỗ trợ qua PGAdapter |
| Di chuyển từ PostgreSQL | Thường phải đổi DDL, queries và data types | Có thể ít sửa SQL hơn, nhưng **không phải drop-in replacement** |
| Tính di động sang PostgreSQL khác | Thường cần chuyển cú pháp | Tốt hơn nếu tránh Spanner-specific extensions |
| Tính năng phân tán Spanner | Truy cập từ SQL/API theo hỗ trợ | Truy cập với ngữ pháp PostgreSQL hoặc Spanner-specific extensions |
| Hiệu năng/độ tin cậy nền tảng | Cùng Spanner engine | **Cùng** Spanner engine; không tự nhanh/chậm hơn chỉ vì dialect |

**Quy tắc chọn:**

1. Nếu đội đã dùng **Spanner Java APIs, GoogleSQL** và cần tích hợp chặt các công cụ Google Cloud: cân nhắc GoogleSQL.
2. Nếu ứng dụng/đội đang dùng **PostgreSQL JDBC, Hibernate, psql** và ưu tiên khả năng mang SQL đi nơi khác: cân nhắc PostgreSQL dialect.
3. Nếu ứng dụng dựa vào **triggers, extensions, UDF/procedures tự viết, fine-grained PostgreSQL locks hoặc transactional DDL**: phải kiểm kê trước. Những tính năng này không mặc nhiên được PostgreSQL interface hỗ trợ.
4. Nếu quy mô nhỏ, không cần Spanner phân tán, Cloud SQL for PostgreSQL có thể ít thay đổi ứng dụng hơn. Chọn Spanner theo **SLO, tải, dữ liệu và chi phí**, không vì tên “PostgreSQL”.

## 3. Ranh giới tương thích: Spanner không chạy PostgreSQL server

**PostgreSQL interface gồm hai lớp:**

- **SQL dialect**: tập con của DQL/DML/DDL và types/functions PostgreSQL, thêm extensions cho Spanner.
- **PostgreSQL wire protocol**: dùng **PGAdapter** làm proxy dịch giao thức PostgreSQL của client thành **Spanner gRPC APIs**; PGAdapter **không chứa PostgreSQL engine**.

| Thành phần | Có thể làm | Không được suy diễn |
|---|---|---|
| **PGAdapter** | Cho PostgreSQL JDBC, psql, nhiều ORMs kết nối Spanner PostgreSQL dialect | Không biến Spanner thành server PostgreSQL đầy đủ |
| **Spanner JDBC** | Kết nối trực tiếp tới cả hai dialect bằng Spanner endpoint | Không đồng nghĩa đang sử dụng PostgreSQL JDBC wire protocol |
| **Spanner Studio** | Thực thi SQL/DDL/DML, xem schema theo database dialect | Không phải pgAdmin hoặc PostgreSQL system administrator |
| **PostgreSQL-compatible schema** | Nhiều câu CREATE TABLE, SELECT, JOIN, INSERT | Không mặc nhiên hỗ trợ mọi extension, function, catalog, lock hoặc PostgreSQL DDL |
| **Cloud IAM/FGAC** | Xác định principal và quyền trên Spanner | Không có cơ chế PostgreSQL login/password và superuser như DB tự quản trị |

### Giới hạn cần kiểm tra trước migration

- Không hỗ trợ tùy ý **PostgreSQL extensions, user-defined types/functions/operators, triggers, foreign data wrappers, transactional DDL**.
- **SAVEPOINT**, một số fine-grained concurrency/locking và danh mục **pg_catalog** không đầy đủ như PostgreSQL gốc.
- **Serial/identity:** không thể giả định mọi câu **SERIAL** cũ giữ nguyên semantics. Tài liệu cập nhật hỗ trợ các **serial aliases** khi đã đặt **spanner.default_sequence_kind=bit_reversed_positive**; các sequence/identity của Spanner có semantics riêng, không bảo đảm ID tăng đều liên tiếp như sequence truyền thống.
- **Kiểu dữ liệu có khác biệt:** trong Spanner PostgreSQL dialect, **int** là bí danh của int8 (64-bit), **timestamp without time zone** không được hỗ trợ, **numeric(18,2)** có thể dùng trong expressions nhưng **không được dùng làm type modifier trong DDL**. Không suy rằng mọi kiểu PostgreSQL map 1:1.
- **PostgreSQL administrative utilities:** không dùng pgAdmin để provision/manage Spanner như một PostgreSQL server thông thường; dùng Spanner console, gcloud, API.

Không đồng nhất “một cú pháp SQL được hỗ trợ” với “tất cả hành vi runtime/transaction/optimizer giống PostgreSQL”. Cần test ứng dụng, ORM migrations, performance và các error codes thực tế.

## 4. So sánh data types và DDL trên cùng mô hình

Giả sử bảng **orders** gồm: ID đơn hàng, ID khách hàng, tổng tiền, thời gian tạo và trạng thái. Chọn **primary key có độ phân tán tốt** thay vì dùng số tự tăng liên tục cho một bảng nhận nhiều writes.

### 4.1. Kiểu dữ liệu tương ứng

| Nhu cầu | **GoogleSQL** | **PostgreSQL dialect** |
|---|---|---|
| Số nguyên 64-bit | **INT64** | **BIGINT / INT8** |
| Chuỗi | **STRING(128)** | **VARCHAR(128) / TEXT** |
| Bytes | **BYTES(MAX)** | **BYTEA** |
| Boolean | **BOOL** | **BOOL / BOOLEAN** |
| Thời điểm tuyệt đối | **TIMESTAMP** | **TIMESTAMPTZ** |
| Ngày lịch | **DATE** | **DATE** |
| Số thập phân chính xác | **NUMERIC** | **NUMERIC / DECIMAL**; DDL không ghi precision/scale modifier |
| JSON | **JSON** | **JSONB** |
| Danh sách | `ARRAY<T>` | `T[]`, không hỗ trợ mảng đa chiều |
| UUID | **UUID** theo hỗ trợ GoogleSQL hiện hành | **UUID** |

Hãy xem kỹ giới hạn của các loại, nhất là **NUMERIC**, **JSON/JSONB**, timezone/collation và indexes. Ví dụ timestamp without time zone có thể là loại dữ liệu hợp lệ trong PostgreSQL gốc nhưng **không** được dùng trực tiếp trong schema Spanner PostgreSQL.

### 4.2. GoogleSQL: PRIMARY KEY đặt sau danh sách cột

~~~sql
CREATE TABLE Orders (
  OrderId STRING(36) NOT NULL,
  CustomerId STRING(36) NOT NULL,
  Amount NUMERIC NOT NULL,
  CreatedAt TIMESTAMP NOT NULL,
  Status STRING(32) NOT NULL
) PRIMARY KEY (OrderId);

CREATE INDEX OrdersByCustomer ON Orders (CustomerId);
~~~

### 4.3. PostgreSQL: PRIMARY KEY nằm trong ngoặc CREATE TABLE

~~~sql
CREATE TABLE orders (
  order_id VARCHAR(36) PRIMARY KEY,
  customer_id VARCHAR(36) NOT NULL,
  amount NUMERIC NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  status VARCHAR(32) NOT NULL
);

CREATE INDEX orders_by_customer ON orders (customer_id);
~~~

**Hai đoạn trên là hai lựa chọn thay thế trong hai databases riêng**, không chạy cả hai trên một database. Ví dụ sử dụng chuỗi UUID do ứng dụng sinh để dễ thấy cú pháp; trong ứng dụng mới có thể cân nhắc UUID type và các key-generation features được hỗ trợ. Cả hai dialect yêu cầu **primary key**, và điều đó giúp Spanner sắp xếp/phân vùng dữ liệu.

### 4.4. Primary key quyết định khả năng mở rộng

Spanner phân vùng key range thành **splits**. Nếu khóa chính tăng tuần tự, ví dụ OrderId = 1, 2, 3..., rất nhiều writes có thể dồn vào **đầu/cuối key range**, tạo **hotspot**, dù đã tăng processing units.

Ưu tiên ID **UUID phân tán**, khóa được băm/phân bố, hoặc **bit-reversed sequence/identity** khi thích hợp. Khi dùng **interleaved tables** (parent/child theo khóa), cân nhắc quan hệ locality, transaction load và khóa cha; đừng nhầm interleaving với PostgreSQL table inheritance/partitioning.

~~~mermaid
flowchart LR
  SEQ["Khóa tăng tuần tự<br/>1,2,3,..."] --> HOT["Ghi tập trung ở một key range<br/>hotspot"]
  UUID["UUID/khóa phân tán"] --> SPLITS["Writes phân tán vào nhiều splits"]
~~~

**Ngoại lệ:** UUID tạo ngẫu nhiên không tự giải quyết mọi hotspot nếu các **secondary indexes** vẫn có khóa dẫn đầu tăng đều như timestamp. Xem toàn bộ schema, indexes và transaction access patterns.

## 5. DML, query parameters, transactions và cú pháp Spanner

### 5.1. Insert và select: hai cách viết

Với database **GoogleSQL** đã tạo bảng **Orders**:

~~~sql
INSERT INTO Orders (OrderId, CustomerId, Amount, CreatedAt, Status)
VALUES ('ord-a1', 'cust-7', 350000, CURRENT_TIMESTAMP(), 'CREATED');

SELECT OrderId, Amount, Status
FROM Orders
WHERE CustomerId = 'cust-7'
ORDER BY OrderId;
~~~

Với database **PostgreSQL** đã tạo bảng **orders**:

~~~sql
INSERT INTO orders (order_id, customer_id, amount, created_at, status)
VALUES ('ord-a1', 'cust-7', 350000, CURRENT_TIMESTAMP, 'CREATED');

SELECT order_id, amount, status
FROM orders
WHERE customer_id = 'cust-7'
ORDER BY order_id;
~~~

Đây là lệnh lab trên hai database **khác nhau**. Trong production, dùng **prepared statements/parameters**, không ghép trực tiếp input của client vào chuỗi SQL.

### 5.2. Tham số truy vấn

| Cách truy cập | Placeholder thường dùng | Ghi chú |
|---|---|---|
| **GoogleSQL qua Spanner API** | **@customer_id** | Bind parameters của Spanner client |
| **PostgreSQL SQL/wire protocol** | **$1, $2...** | Positional parameters cho PostgreSQL protocol |
| **Java JDBC PreparedStatement** | **?** | Được JDBC driver bind; áp dụng cả Spanner JDBC và PostgreSQL JDBC |

Ví dụ SQL thuần:

~~~sql
-- GoogleSQL, chạy qua Spanner API với bind parameter @customer_id
SELECT OrderId FROM Orders WHERE CustomerId = @customer_id;

-- PostgreSQL SQL, bind $1 bằng client PostgreSQL
SELECT order_id FROM orders WHERE customer_id = $1;
~~~

Không copy đoạn có **@customer_id** vào psql rồi mong psql tự bind, cũng không đưa **$1** vào gcloud execute-sql khi chưa có cơ chế binding tương ứng. Các ví dụ gcloud dưới dùng literal lab; Java dùng JDBC PreparedStatement an toàn.

### 5.3. Transaction semantics không phải PostgreSQL mặc định

Spanner cung cấp **ACID read-write transactions**, với **serializable isolation/external consistency** theo cấu hình transaction. Spanner còn hỗ trợ các chế độ/isolation khác được tài liệu mô tả, nhưng **không tự mang toàn bộ PostgreSQL MVCC/locking semantics** vào PostgreSQL interface.

Một read-write transaction có thể bị **ABORTED** khi tranh chấp hoặc vì sự kiện tạm thời. Các Spanner client libraries và drivers có cơ chế retry, nhưng:

1. **Mã nằm trong callback transaction có thể chạy lại**; không gọi payment API/gửi email bất biến trực tiếp từ callback được retry.
2. Dùng **idempotency key** và mô hình outbox khi phát sự kiện ra Pub/Sub sau commit.
3. Giữ transaction ngắn, tránh truy vấn quá rộng hoặc khóa cùng key hotspot.
4. Test retry với traffic tranh chấp, quan sát số transaction abort/commit.

Spanner không hỗ trợ **transactional DDL** như PostgreSQL chuẩn. Khi apply DDL qua gcloud/Spanner Studio, kiểm tra long-running schema operation và hoàn tất trước khi chạy data migration phụ thuộc schema.

### 5.4. Query hints và optimizer

Hai dialect có cách viết hints khác nhau:

~~~sql
-- GoogleSQL hint syntax (minh họa hình thức)
SELECT * FROM Orders@{FORCE_INDEX=OrdersByCustomer}
WHERE CustomerId = 'cust-7';

-- PostgreSQL dialect sử dụng comment-style hints theo Spanner
SELECT * FROM orders /*@ FORCE_INDEX=orders_by_customer */
WHERE customer_id = 'cust-7';
~~~

Không áp hint vô điều kiện; hãy **EXPLAIN/query plan/Query Insights**, kiểm tra index và thống kê để xác định hint có thực sự cải thiện latency/cost hay không. Một index mới cũng tốn storage và tăng chi phí writes.

## 6. Thực hành A — Tạo instance và hai databases

Các lệnh sau **có thể tạo tài nguyên tính phí**, chỉ chạy trong project lab được phép. Giá trị ví dụ:

| Thuộc tính | Giá trị |
|---|---|
| Project | **shop-dev-001** |
| Instance | **spanner-sql-lab** |
| Config | **regional-asia-southeast1** (Singapore) |
| Database GoogleSQL | **orders-google** |
| Database PostgreSQL | **orders-pg** |
| Compute | **100 processing units** cho lab; tính phí theo tài nguyên |

### 6.1. Preflight và tạo instance

~~~bash
gcloud config get-value project
gcloud auth list
gcloud services list --enabled --project=shop-dev-001
gcloud spanner instance-configs list --project=shop-dev-001
gcloud spanner instances list --project=shop-dev-001

# Chỉ thao tác trên project lab được cấp quyền.
gcloud services enable spanner.googleapis.com \
  --project=shop-dev-001

gcloud spanner instances create spanner-sql-lab \
  --project=shop-dev-001 \
  --config=regional-asia-southeast1 \
  --description="SQL dialect learning lab" \
  --edition=STANDARD \
  --processing-units=100
~~~

**Không dùng lab instance làm production**: 100 processing units là cấu hình nhỏ. Kiểm tra trước **instance configuration, edition/quota, phí** và tính khả dụng theo region; không tạo thêm instance nếu đã tồn tại.

### 6.2. Tạo hai databases trên cùng instance

~~~bash
# GoogleSQL là mặc định nhưng vẫn ghi rõ để dễ review.
gcloud spanner databases create orders-google \
  --project=shop-dev-001 \
  --instance=spanner-sql-lab \
  --database-dialect=GOOGLE_STANDARD_SQL

gcloud spanner databases create orders-pg \
  --project=shop-dev-001 \
  --instance=spanner-sql-lab \
  --database-dialect=POSTGRESQL

gcloud spanner databases list \
  --project=shop-dev-001 \
  --instance=spanner-sql-lab
~~~

**Quan trọng:** khi **tạo PostgreSQL-dialect database**, gcloud **không hỗ trợ --ddl hoặc --ddl-file ngay trong lệnh create**. Phải **tạo database trống trước, sau đó update DDL**. GoogleSQL có thể truyền DDL lúc tạo hoặc sau đó. Chọn sai dialect lúc tạo phải thiết kế migration, không sửa đổi trực tiếp trong cùng database.

### 6.3. Thực thi schema theo từng dialect

~~~bash
# GoogleSQL: cú pháp PRIMARY KEY nằm bên ngoài dấu ngoặc.
gcloud spanner databases ddl update orders-google \
  --project=shop-dev-001 \
  --instance=spanner-sql-lab \
  --ddl='CREATE TABLE Orders (OrderId STRING(36) NOT NULL, CustomerId STRING(36) NOT NULL, Amount NUMERIC NOT NULL, CreatedAt TIMESTAMP NOT NULL, Status STRING(32) NOT NULL) PRIMARY KEY (OrderId)'

# PostgreSQL: cú pháp PRIMARY KEY nằm trong CREATE TABLE.
gcloud spanner databases ddl update orders-pg \
  --project=shop-dev-001 \
  --instance=spanner-sql-lab \
  --ddl='CREATE TABLE orders (order_id VARCHAR(36) PRIMARY KEY, customer_id VARCHAR(36) NOT NULL, amount NUMERIC NOT NULL, created_at TIMESTAMPTZ NOT NULL, status VARCHAR(32) NOT NULL)'
~~~

Với bảng lớn/migrations, dùng DDL file đã review và CI/CD workflow để tránh shell quoting lỗi. Các lệnh ví dụ **không tạo index** trong phần này; muốn chạy truy vấn có FORCE_INDEX ở mục 5.4 cần tạo index tương ứng từ mục 4 trước.

### 6.4. DML và đọc lại bằng gcloud

~~~bash
gcloud spanner databases execute-sql orders-google \
  --project=shop-dev-001 --instance=spanner-sql-lab \
  --sql="INSERT INTO Orders (OrderId,CustomerId,Amount,CreatedAt,Status) VALUES ('ord-a1','cust-7',350000,CURRENT_TIMESTAMP(),'CREATED')"

gcloud spanner databases execute-sql orders-google \
  --project=shop-dev-001 --instance=spanner-sql-lab \
  --sql="SELECT OrderId, Status FROM Orders WHERE CustomerId='cust-7'"

gcloud spanner databases execute-sql orders-pg \
  --project=shop-dev-001 --instance=spanner-sql-lab \
  --sql="INSERT INTO orders (order_id,customer_id,amount,created_at,status) VALUES ('ord-a1','cust-7',350000,CURRENT_TIMESTAMP,'CREATED')"

gcloud spanner databases execute-sql orders-pg \
  --project=shop-dev-001 --instance=spanner-sql-lab \
  --sql="SELECT order_id,status FROM orders WHERE customer_id='cust-7'"
~~~

Nếu chạy lặp INSERT cùng khóa, **ALREADY_EXISTS/unique key error** là bình thường. Không xóa data production để “cho lab chạy lại”; thay ID lab có kiểm soát.

### 6.5. Xem schema và dọn tài nguyên

~~~bash
gcloud spanner databases ddl describe orders-google \
  --project=shop-dev-001 --instance=spanner-sql-lab
gcloud spanner databases ddl describe orders-pg \
  --project=shop-dev-001 --instance=spanner-sql-lab
~~~

Sau khi hoàn thành và xác nhận không có data cần giữ, xóa **databases/instance lab** theo quy trình có phê duyệt. **Xóa database là thao tác destructive**, cần kiểm tra backup/deletion protection và billing trước khi làm; không đưa câu lệnh delete trực tiếp vào script tự chạy.

## 7. Kết nối PostgreSQL interface qua PGAdapter và psql

**PGAdapter** được triển khai như process độc lập, sidecar Cloud Run/GKE hoặc **in-process trong JVM**. Nó nhận PostgreSQL wire protocol tại localhost rồi gọi Spanner gRPC bằng principal IAM/ADC mà process có.

~~~mermaid
sequenceDiagram
  participant J as PostgreSQL JDBC / psql
  participant P as PGAdapter localhost:5432
  participant S as Spanner API
  J->>P: PostgreSQL protocol request
  P->>S: Authenticated Spanner gRPC request (ADC)
  S-->>P: SQL results
  P-->>J: PostgreSQL protocol response
~~~

### 7.1. Chạy local lab với ADC

Cài PGAdapter JAR từ tài liệu chính thức **Start PGAdapter**; máy có Java runtime. Sau khi user đăng nhập ADC cho lab:

~~~bash
# Chỉ dành cho máy phát triển; không tải JSON service account key.
gcloud auth application-default login

# Giả định pgadapter.jar đã được tải theo tài liệu và trong thư mục hiện tại.
java -jar pgadapter.jar \
  -p shop-dev-001 \
  -i spanner-sql-lab \
  -d orders-pg \
  -s 5432
~~~

Trong terminal khác:

~~~bash
psql -h 127.0.0.1 -p 5432 -d orders-pg \
  -c "SELECT order_id, status FROM orders ORDER BY order_id"
~~~

**Giới hạn bảo mật:** PGAdapter mặc định chỉ lắng nghe localhost. **Không thêm -x hoặc bind public interface** để mở proxy cho Internet; việc client có thể kết nối local socket có nghĩa nó có thể dùng quyền IAM của PGAdapter process. PostgreSQL username/password tại endpoint PGAdapter **không tự tương đương PostgreSQL server user**: quyền truy cập Spanner dựa trên **IAM principal** của PGAdapter và có thể thêm database roles theo fine-grained access control.

### 7.2. Những giới hạn của PGAdapter

- Không hỗ trợ toàn bộ PostgreSQL wire protocol hoặc tất cả lệnh **psql meta**; các ứng dụng/tool phụ thuộc tính năng quản trị server cần kiểm thử.
- **DDL transaction** không hỗ trợ như PostgreSQL server; đừng gói schema migrations bằng BEGIN/ROLLBACK rồi giả định atomic.
- Các kết nối client → PGAdapter trong ví dụ là **localhost**, không phải TLS end-to-end tới một PostgreSQL server. Kết nối PGAdapter → Spanner dùng gRPC được bảo vệ; không expose PGAdapter bên ngoài trusted boundary.
- Kiểm tra version tương thích của **PostgreSQL JDBC 42.x**, psql/ORM/Hibernate và PGAdapter; không bật một feature vì tool tự nhận dạng “PostgreSQL 14”.

### 7.3. Triển khai trên Cloud Run và GKE

Với **Cloud Run**, chạy PGAdapter **sidecar** trong cùng instance hoặc in-process Java; hai containers cùng instance chia network namespace và ứng dụng chỉ kết nối localhost. Với **GKE**, dùng PGAdapter sidecar trong cùng Pod, cấu hình **Workload Identity Federation for GKE** và IAM. Trong cả hai:

- Gắn runtime service account/identity tối thiểu có quyền sử dụng Spanner database.
- Không ghi service account JSON keys trong image, Kubernetes Secret hoặc environment nếu có thể dùng Workload Identity/ADC.
- Pin PGAdapter version/digest; thêm startup/health checks, resources và monitoring.
- Cấu hình JDBC pool hợp lý và kiểm thử transaction retry, concurrent connections.

## 8. Thực hành B — Java JDBC qua hai cách kết nối

Với Java, có **hai đường JDBC hợp lệ**:

| Driver | JDBC URL mẫu | Kết nối tới đâu? |
|---|---|---|
| **com.google.cloud:google-cloud-spanner-jdbc** | jdbc:cloudspanner:/projects/shop-dev-001/instances/spanner-sql-lab/databases/orders-google | Trực tiếp Spanner gRPC/API bằng ADC |
| **org.postgresql:postgresql** | jdbc:postgresql://127.0.0.1:5432/orders-pg | PGAdapter process/sidecar, rồi Spanner API |

**Spanner JDBC** cũng hỗ trợ **orders-pg** nếu đổi tên database trong URL, không cần PGAdapter; điều này đặc biệt hữu ích khi code Java không cần toàn bộ ORM/tooling tương thích PostgreSQL.

### 8.1. Đoạn Java dùng PreparedStatement

Ví dụ sử dụng Java 21, phụ thuộc driver tương ứng đã được thêm vào Maven/Gradle và tài khoản có IAM phù hợp. Tham số chọn **pgwire** hoặc **native**:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class SpannerDialectQuery {
    private SpannerDialectQuery() {}

    public static void main(String[] args) throws SQLException {
        boolean viaPgAdapter =
            args.length > 0 && "pgwire".equalsIgnoreCase(args[0]);

        String url = viaPgAdapter
            ? "jdbc:postgresql://127.0.0.1:5432/orders-pg"
            : "jdbc:cloudspanner:/projects/shop-dev-001"
              + "/instances/spanner-sql-lab/databases/orders-google";

        String sql = viaPgAdapter
            ? "SELECT order_id, status FROM orders WHERE customer_id = ?"
            : "SELECT OrderId, Status FROM Orders WHERE CustomerId = ?";

        try (Connection connection = DriverManager.getConnection(url);
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, "cust-7");
            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    System.out.printf("%s : %s%n",
                        rows.getString(1), rows.getString(2));
                }
            }
        }
    }
}
~~~

Đây là **một lớp chạy độc lập sau khi đã cài JDBC drivers đúng**. Nó giả định Spanner lab có dữ liệu mục 6 và PGAdapter đang chạy cho **pgwire**. Với **native**, Spanner JDBC dùng ADC trực tiếp, không cần PostgreSQL username/password.

### 8.2. Những điểm Java phải xử lý

1. **PreparedStatement dùng dấu ?** ở cả hai driver — an toàn hơn nối chuỗi từ user input.
2. Dùng **connection/session pools** theo hướng dẫn driver; không tạo PGAdapter process hoặc Spanner client mới cho từng HTTP request.
3. Cấu hình **deadlines, transaction retry, backoff**, tránh retry một thanh toán bên ngoài transaction callback có thể được chạy lại.
4. Với Cloud Run auto-scaling/GKE HPA, đo số sessions và pool size theo số instances; không đặt 400 sessions mặc định chỉ vì ví dụ cũ.
5. Khi dùng Hibernate/Spring Data, chọn dialect/driver/versions được xác nhận trong **Spanner PostgreSQL drivers and ORMs compatibility matrix**. Không giả định native PostgreSQL Hibernate dialect chạy mọi migration.
6. Log request/transaction tags và query latency **không log PII hay full query parameters nhạy cảm**.

### 8.3. Spring Boot: phân biệt cấu hình datasource

~~~properties
# Ví dụ A: Native Spanner JDBC
spring.datasource.url=jdbc:cloudspanner:/projects/shop-dev-001/instances/spanner-sql-lab/databases/orders-google

# Ví dụ B: PostgreSQL JDBC tới PGAdapter (thay thế dòng trên)
# spring.datasource.url=jdbc:postgresql://127.0.0.1:5432/orders-pg
~~~

Đây chỉ là **đường kết nối**, không phải cấu hình Spring Boot hoàn chỉnh. Cần driver classpath, pool, access permissions, health checks, schema migrations và testing. Không bỏ password PostgreSQL thật vào properties: **PGAdapter sử dụng IAM principal/ADC của chính process**, không dùng role postgres/superuser của Cloud SQL.

## 9. IAM, xác thực và kiểm soát quyền

Spanner cho cả hai dialect dùng **Google Cloud IAM** làm lớp quản lý tài nguyên và xác thực caller. Với PostgreSQL wire protocol, **PGAdapter lấy ADC/service account** của process để gửi requests. PostgreSQL username trong chuỗi JDBC không phải quyền thực thi trên Spanner.

| Identity/role | Công việc | Cảnh báo |
|---|---|---|
| **Deployer/DB operator** | Tạo instance/database và thay DDL | Không cấp roles/spanner.admin cho runtime |
| **orders-runtime@...** | Dùng Spanner database từ Cloud Run | Chỉ cấp database permissions thích hợp |
| **PGAdapter service identity** | Dùng ADC gọi Spanner gRPC | Client nào truy cập PGAdapter có thể tận dụng quyền process này |
| **Fine-grained database role** | SELECT/INSERT/UPDATE trên tables cụ thể | Cần IAM role cho FGAC và quyền dùng role |
| **Auditor/SRE** | Xem metrics/logs, query statistics | Không cần quyền chỉnh schema hoặc đọc dữ liệu nhạy cảm |

### 9.1. Resource IAM khác FGAC

Role **roles/spanner.databaseUser** cho phép đọc/ghi và **có thể cập nhật DDL**; không phải quyền chỉ đọc. Nếu ứng dụng chỉ cần SELECT trên vài tables, dùng **fine-grained access control (FGAC)**:

1. Tạo **database role** và SQL GRANT cụ thể trong dialect đang dùng.
2. Cấp **roles/spanner.fineGrainedAccessUser** cùng **roles/spanner.databaseRoleUser** với IAM Conditions chỉ định role.
3. Chỉ định database role khi client/PGAdapter thực thi.
4. Test bằng danh tính ứng dụng: read hợp lệ và negative test cho schema/DDL/other tables.

Nếu không chọn database role, quyền kiểm tra theo IAM principal (không tự phát sinh role-based restrictions). Không gán đồng thời một role resource-level rất rộng cho runtime rồi kỳ vọng database role nhỏ hạn chế được quyền đó.

### 9.2. Ví dụ IAM rộng cho lab, không dùng làm mặc định production

~~~bash
# Chỉ chạy trong project lab được cấp quyền; databaseUser khá rộng.
gcloud spanner databases add-iam-policy-binding orders-google \
  --project=shop-dev-001 \
  --instance=spanner-sql-lab \
  --member="serviceAccount:orders-runtime@shop-dev-001.iam.gserviceaccount.com" \
  --role="roles/spanner.databaseUser"

gcloud spanner databases get-iam-policy orders-google \
  --project=shop-dev-001 \
  --instance=spanner-sql-lab
~~~

**Rủi ro:** databaseUser bao gồm quyền thay DDL; production nên xem xét FGAC hoặc custom IAM role được hỗ trợ. Nếu user dùng **Cloud SQL for PostgreSQL**, cú pháp quyền **GRANT trong PostgreSQL server** sẽ khác mô hình IAM/FGAC của Spanner.

### 9.3. Bảo mật tại client boundary

- Cloud Run và GKE nên dùng **service identity/Workload Identity Federation**, tránh service account key JSON tĩnh.
- Chạy **PGAdapter tại localhost** hoặc trong trusted Pod/instance; không expose 5432 ra Internet.
- Spanner client kết nối API có TLS và IAM; PGAdapter local socket là boundary cần bảo vệ riêng. Nếu buộc có remote PGAdapter, review network và cơ chế xác thực cụ thể thay vì giả định PostgreSQL TLS/mTLS tự có.
- Theo dõi IAM changes, service account impersonation, **Database Audit Logs**, CMEK nếu cần.
- Không đưa credentials/tokens hoặc dữ liệu đơn hàng vào query tags, logs hoặc debug output.

## 10. Chuyển ứng dụng PostgreSQL sang Spanner PostgreSQL interface

**Tương thích cú pháp là điểm bắt đầu, không phải bản cam kết “chỉ đổi connection string”.** Di chuyển một ứng dụng từ Cloud SQL PostgreSQL hoặc PostgreSQL tự quản trị nên thực hiện:

| Công đoạn | Công việc | Cần kiểm tra |
|---|---|---|
| **Inventory** | Extensions, stored procedures, triggers, views, sequences, types, indexes, schema migration tools | Những tính năng không hỗ trợ/khác semantics |
| **DDL translation** | Chuyển kiểu dữ liệu, PRIMARY KEY, constraints và identity | PK bắt buộc, non-hotspot, numeric modifiers, timestamp |
| **Data migration** | Export/copy/ingest dữ liệu theo công cụ được hỗ trợ | Types/encoding, duplicates, foreign keys, row counts |
| **Client migration** | PG JDBC + PGAdapter hoặc Spanner JDBC/client | Authentication IAM, connection URL, pool, transaction retries |
| **Behavioral tests** | CRUD, transactions, ordering, time zone, JSON, locking | Semantics, không chỉ syntax |
| **Load tests** | Queries, index plans, hotspots, CPU/sessions | Latency p95/p99, throughput và cost |
| **Cutover/rollback** | Đồng bộ writes, chuyển traffic, giữ source theo retention | Schema compatibility, RPO/RTO, không dual-write mù quáng |

### 10.1. Ví dụ các khác biệt cần sửa

| PostgreSQL gốc | Cách xử lý ở Spanner PostgreSQL |
|---|---|
| Sequence/SERIAL IDs tăng tuần tự | Cân nhắc UUID hoặc bit-reversed sequence; với SERIAL aliases phải set database option trước |
| NUMERIC(12,2) trong CREATE TABLE | Dùng NUMERIC, kiểm tra ràng buộc precision/scale trong app hoặc CHECK theo hỗ trợ |
| TIMESTAMP WITHOUT TIME ZONE | Dùng TIMESTAMPTZ và chuẩn hóa UTC/zone ở app |
| Trigger cập nhật audit field | Đưa logic vào app/transaction hoặc tính năng Spanner được hỗ trợ |
| PostgreSQL user-defined PL/pgSQL functions | Refactor sang app SQL/client logic; kiểm tra system procedures được hỗ trợ |
| psql admin commands/pg_dump extensions | Dùng Spanner DDL APIs, PGAdapter import/export flow được hỗ trợ |
| Advisory locks/SAVEPOINT | Thiết kế lại transaction/idempotency, không phụ thuộc locking kiểu PostgreSQL |

### 10.2. Kiểm thử trên database clone mới

Không migrate trực tiếp production bằng một lệnh import chưa được xem xét. Phương án lab:

1. Lấy DDL schema PostgreSQL gốc và liệt kê unsupported constructs.
2. Tạo một **database Spanner PostgreSQL dialect** trống, chuẩn hóa DDL.
3. Nạp một tập dữ liệu test có dấu tiếng Việt, NULL, JSONB, timestamps và các business keys.
4. Chạy integration tests bằng **PostgreSQL JDBC + PGAdapter**, sau đó thử **Spanner JDBC** nếu muốn giản lược operational proxy.
5. Đo query plans, hotspots, transaction aborts, cost; sửa schema/key trước khi chuyển dữ liệu thật.
6. Lập cutover/rollback: giai đoạn ngừng ghi, so sánh dữ liệu, chọn thời điểm chuyển và bảo vệ các giao dịch chưa đồng bộ.

### 10.3. Di chuyển ngược trở lại PostgreSQL

PostgreSQL interface tăng khả năng **portability** nhưng các **Spanner-specific extensions** (interleaving, hints, TTL, identities hoặc các loại tính năng độc quyền) vẫn phải được thay hoặc loại bỏ. Khi di chuyển về PostgreSQL server, xuất DDL theo dialect, dữ liệu và refactor phần Spanner-specific. Tính di động không đồng nghĩa portable 100%.

## 11. Hiệu năng, độ tin cậy và chi phí đều phụ thuộc thiết kế Spanner

### 11.1. Đừng tối ưu theo dialect trước khi đo đạc

Vì hai dialect sử dụng **cùng Spanner engine**, không có quy tắc chung “PostgreSQL chậm hơn GoogleSQL”. Độ trễ phụ thuộc:

- **Key distributions và hotspots**: PK/sequential index writes, high-contention rows.
- **Indexes và query plans**: cột lọc, ORDER BY, join patterns, scan lớn.
- **Transaction size/time**: phạm vi đọc/ghi, contention, ABORTED/retry.
- **Instance config/leader locality**: regional/dual/multiregion, khoảng cách client tới leader và write quorum.
- **Capacity**: processing units/nodes, autoscaling, CPU/storage, số sessions.
- **Client**: JDBC/PGAdapter sidecar topology, pooling, gRPC deadlines và retry.

**Processing units** là đơn vị capacity: **1 node = 1000 processing units**. Node là đơn vị năng lực logic phân bổ trên hạ tầng, **không phải một máy vật lý**. Tăng capacity có thể tăng throughput, nhưng **không tự sửa hotspot** trong primary key.

### 11.2. Một regional instance cũng đã sao chép qua các zones

Spanner **regional** dùng nhiều replicas trong **các zones của cùng một region** và quorum để phục vụ giao dịch; không cần tự tạo “read replica” kiểu Cloud SQL cho high availability cơ bản. **Multi-region** tăng mức sẵn sàng và phân tán địa lý nhưng có thêm replica/quorum latency và chi phí. Cả hai dialect hưởng cùng topology.

**Không đồng nghĩa đa vùng = không cần backup:** mất dữ liệu do bug SQL hoặc thao tác xóa sai sẽ được sao chép. Thiết kế **backup/PITR, deletion protection, restore rehearsal** và IAM riêng.

### 11.3. System Insights, Query Insights và Key Visualizer

| Dấu hiệu | Xem ở đâu | Giả thuyết |
|---|---|---|
| CPU high-priority liên tục cao | Spanner **System Insights** / Cloud Monitoring | Under-provisioning, query scan lớn |
| Một vùng khóa nhận writes bất thường | **Key Visualizer** | Hotspot PK/secondary index |
| p99 query cao | **Query Insights**, query plans | Thiếu index, nhiều rows scanned, lock contention |
| ABORTED retries tăng | Transaction metrics và application logs | Giao dịch tranh chấp, truy cập cùng hot rows |
| Sessions tăng mạnh | Session metrics, Cloud Run/GKE instance count | Client/pool được tạo mỗi request hoặc scale-out |
| Query ổn nhưng chi phí tăng | Cloud Billing + Spanner compute/storage/backups | Processing units quá cao, storage/index/backup |
| Lỗi chỉ trong pgwire path | PGAdapter logs, JDBC errors, resource usage | Proxy lỗi, driver/ORM incompatibility |

Khi chuyển **GoogleSQL → PostgreSQL dialect**, hãy benchmark **cùng schema mục tiêu, cùng data distribution, cùng service locations và workload**. Thử cả **Spanner JDBC direct** lẫn PG JDBC/PGAdapter nếu client path là biến quan trọng.

### 11.4. Kiểm soát chi phí lab và production

Phí có thể gồm **instance compute capacity, lưu trữ dữ liệu/index, backups, chuyển dữ liệu/network, Data Boost khi sử dụng**, cùng các hệ thống app/observability. **Regional** thường ít costly hơn multi-region, nhưng cần chọn theo data residency và SLO.

Không tạo nhiều instances/dialects chỉ để xem bảng DDL nếu một instance dùng chung là đủ. Sau lab cần **dọn hai database và instance** có phê duyệt; **budget alert không tự tắt tài nguyên**. Giá/quotas thay đổi theo edition, instance configuration và khu vực — xem Google Cloud pricing/quotas tại thời điểm triển khai.

## 12. Troubleshooting: chẩn đoán đúng lớp

| Triệu chứng | Nguyên nhân có thể | Kiểm tra đầu tiên |
|---|---|---|
| PostgreSQL JDBC không kết nối **localhost:5432** | PGAdapter chưa chạy, sai port, startup error | Process/sidecar logs, local listener |
| PostgreSQL JDBC kết nối được nhưng SQL lỗi | DDL/type/function/extension không được hỗ trợ | PostgreSQL language reference, schema, ORM SQL |
| **PERMISSION_DENIED** qua PGAdapter | ADC identity thiếu Spanner IAM/role | Runtime service account, PGAdapter credentials, FGAC role |
| **PERMISSION_DENIED** khi chạy DDL | role thiếu **spanner.databases.updateDdl** | IAM effective permissions và DDL operation |
| Thay PostgreSQL username mà vẫn có quyền | PGAdapter dùng service account/ADC của process | Kiểm tra IAM, không nhầm login server PostgreSQL |
| ORM migration báo không hỗ trợ savepoint/trigger | PostgreSQL compatibility chỉ hỗ trợ subset | Refactor migration, bỏ unsupported constructs |
| CREATE TABLE PostgreSQL lỗi numeric(12,2) | Precision/scale modifier không được hỗ trợ trong DDL | Chuyển thành NUMERIC, thêm validation |
| CREATE TABLE thiếu PRIMARY KEY | Spanner yêu cầu PK | Chọn khóa có phân bố phù hợp |
| Writes chậm khi IDs tăng đều | Hotspot cuối key range | Key Visualizer, key strategy, secondary indexes |
| Query p99 cao dù CPU vừa phải | Lock contention, scan hoặc network locality | Query Insights, transaction metrics, leader region |
| **ABORTED** trong transaction | Tranh chấp/tạm thời, retry chưa đúng | Retry policy, short transactions, app side effects |
| DDL schema đã gửi nhưng query vẫn lỗi | Schema update chưa hoàn thành hoặc invalid | Spanner operations, DDL describe |
| SQL có chữ hoa chuyển thành chữ thường | PostgreSQL folding unquoted identifiers | Dùng lowercase thống nhất hoặc quoted identifiers có chủ đích |
| gcloud create PostgreSQL với --ddl thất bại | --ddl không hỗ trợ lúc tạo PG database | Create empty DB rồi ddl update |
| Bản SQL chạy trên Cloud SQL PG nhưng lỗi Spanner | PostgreSQL engine semantics khác | So sánh supported language và transaction behavior |
| 0% traffic vẫn tốn phí | Instance Spanner vẫn provision capacity | Instance billing/capacity; cleanup có kiểm soát |

### 12.1. Chuỗi kiểm tra tối thiểu

~~~bash
# Đọc cấu hình, không thay đổi dữ liệu:
gcloud spanner instances describe spanner-sql-lab \
  --project=shop-dev-001

gcloud spanner databases list \
  --instance=spanner-sql-lab \
  --project=shop-dev-001

gcloud spanner databases ddl describe orders-pg \
  --instance=spanner-sql-lab \
  --project=shop-dev-001

gcloud spanner databases get-iam-policy orders-pg \
  --instance=spanner-sql-lab \
  --project=shop-dev-001
~~~

**Quy trình:** xác định đúng project/instance/database/dialect → xác định client path → kiểm tra IAM → kiểm tra syntax/DDL/schema → đo session/CPU/query/index/transaction → điều chỉnh và kiểm thử âm tính.

## 13. Tình huống tổng hợp: chuyển dịch vụ đặt hàng từ Cloud SQL

Doanh nghiệp **An Phát** đang vận hành Java Spring Boot trên Cloud Run, lưu đơn hàng bằng Cloud SQL for PostgreSQL. Lưu lượng tăng, cần khả năng scale và giao dịch nhất quán trên hệ dữ liệu lớn. Đội muốn dùng Spanner nhưng vẫn duy trì Hibernate và cú pháp PostgreSQL hiện có.

### 13.1. Quyết định thiết kế

| Câu hỏi | Lựa chọn và lý do |
|---|---|
| Dùng dialect nào? | **PostgreSQL interface** nếu compatibility audit đạt và portability quan trọng |
| Chạy JDBC ra sao? | Bắt đầu với **PG JDBC + PGAdapter** để giảm thay đổi client; benchmark **Spanner JDBC direct** |
| Primary key? | **UUID hoặc phân tán** cho orders, kiểm tra indexes và join patterns |
| SQL schema? | Loại bỏ trigger/unsupported types, chuyển NUMERIC modifiers và transaction DDL |
| Auth? | Cloud Run runtime identity + Spanner IAM/FGAC; không tái sử dụng PostgreSQL superuser/password |
| Transactions? | Dùng short read-write transactions, idempotency key, xử lý ABORTED đúng cách |
| Availability? | Chọn Spanner instance config theo users/SLO/data residency; có backup và restore tests |
| Monitoring? | p95/p99, transaction aborts, CPU, Key Visualizer, PGAdapter logs |

### 13.2. Luồng cutover và rollback

~~~mermaid
flowchart TD
    INVENTORY["Khảo sát extensions/SQL/queries"] --> DDL["Chuyển schema + chọn PK"]
    DDL --> LAB["Tạo Spanner PostgreSQL lab"]
    LAB --> TEST["Integration + load + retry tests"]
    TEST --> CHECK{"Tương thích và SLO đạt?"}
    CHECK -->|Không| FIX["Chỉnh schema/ORM/client, test lại"]
    CHECK -->|Có| SYNC["Đồng bộ dữ liệu + validation"]
    SYNC --> CUT["Cutover traffic theo runbook"]
    CUT --> OBS["Theo dõi errors/latency/consistency"]
    OBS --> DR["Giữ nguồn cũ theo rollback window"]
~~~

**Tình huống thất bại có thể gặp:** model cũ dùng SERIAL tăng tuần tự làm khóa chính và một trigger tự cập nhật audit, Hibernate migration dùng SAVEPOINT. Ứng dụng **không thể chỉ thay JDBC URL rồi đưa vào production**. Cần chọn cách sinh key phân tán, chuyển trigger vào app/Spanner-supported mechanism và sửa transaction/migration logic.

### 13.3. Tiêu chí nghiệm thu

1. Tất cả CRUD, joins, order constraints và transaction rollback được kiểm thử.
2. Không có unsupported functions/schema constructs còn lại mà runtime cần.
3. p95/p99 và transaction-abort rate nằm trong ngưỡng SLO đã đặt.
4. App dùng service identity tối thiểu; negative IAM/FGAC tests đạt.
5. Migration xác nhận row counts/checksums, không mất order events; có runbook khôi phục và rollback.
6. Kiểm soát capacity/chi phí dựa trên workload thực tế, không chỉ dựa vào “số node”.

## 14. Bài tập có đáp án

### Bài tập A — Hai dialect và một instance

**Hỏi:** Có thể tạo một instance Spanner rồi có một database GoogleSQL và một database PostgreSQL không? Có thể chuyển dialect của database cũ bằng một lệnh ALTER không?

**Đáp án:** **Có** hai databases khác dialect trong cùng instance; **không** chuyển dialect của database hiện tại bằng một flag đơn giản. Muốn đổi cần tạo database đích mới rồi migrate schema/data/app.

### Bài tập B — PostgreSQL interface có phải PostgreSQL hoàn chỉnh?

Ứng dụng dùng PostGIS extension, trigger, PL/pgSQL function và pgAdmin quản trị.

**Đáp án:** Không phải drop-in. Kiểm tra compatibility; nhiều extensions/triggers/UDF và công cụ admin server truyền thống **không được hỗ trợ**. Cân nhắc refactor hoặc dùng **Cloud SQL PostgreSQL** nếu các tính năng này là bắt buộc.

### Bài tập C — Viết DDL

**Yêu cầu:** Tạo bảng products(id, name) với PK, dùng GoogleSQL và PostgreSQL dialect.

**Đáp án:**

~~~sql
-- GoogleSQL:
CREATE TABLE Products (ProductId INT64 NOT NULL, Name STRING(120))
PRIMARY KEY (ProductId);

-- PostgreSQL dialect (DB khác):
CREATE TABLE products (product_id BIGINT PRIMARY KEY, name VARCHAR(120));
~~~

### Bài tập D — DDL sai vì NUMERIC(12,2)

Database Spanner PostgreSQL báo lỗi khi tạo **price NUMERIC(12,2)**.

**Đáp án:** Precision/scale modifiers của NUMERIC **không hỗ trợ trong CREATE TABLE DDL**. Dùng **NUMERIC** và đặt validation/constraint thích hợp; test cách JDBC xử lý kiểu số và precision trước migration.

### Bài tập E — Hotspot

Hệ thống 10.000 writes/s sử dụng OrderId tăng tuần tự, CPU và latency cao dù có nhiều processing units.

**Đáp án:** Có thể tập trung writes ở cuối key range. Xem **Key Visualizer**, thiết kế UUID/khóa phân tán/bit-reversed IDs, đồng thời kiểm tra secondary index theo timestamp và contention.

### Bài tập F — JDBC và PGAdapter

Một Java service kết nối database Spanner PostgreSQL bằng PostgreSQL JDBC thông qua PGAdapter. Khi dừng PGAdapter, app không kết nối được.

**Đáp án:** PGAdapter là **thành phần cần thiết** của PostgreSQL wire path; khởi động lại sidecar/process hoặc xem xét chuyển sang **Spanner JDBC direct** nếu app/ORM phù hợp. Không hướng Java tới Spanner gRPC port rồi giả định PostgreSQL wire protocol tương thích.

### Bài tập G — IAM và database role

Runtime có **roles/spanner.databaseUser** nhưng được yêu cầu chỉ SELECT một bảng. Đã đủ least privilege chưa?

**Đáp án:** **Chưa**; databaseUser có quyền rộng gồm thay DDL. Thiết kế **FGAC database role** với SELECT cần thiết và IAM roles/conditions cho role đó; test quyền bị từ chối trên bảng khác.

### Bài tập H — Transaction retry

Trong một read-write transaction callback, app trừ số dư và gọi API thanh toán bên ngoài. Spanner trả **ABORTED**, client retry callback.

**Đáp án:** Payment API có thể bị gọi lặp. Tránh side effect bên ngoài callback tự retry; dùng **idempotency key, outbox và hành động sau commit**, test tình huống retry.

### Bài tập I — So sánh hiệu năng

Bạn thấy PG JDBC + PGAdapter p95 = 80 ms, Spanner JDBC direct p95 = 65 ms.

**Đáp án:** Chưa thể kết luận chỉ vì “PostgreSQL dialect chậm hơn”. Phải benchmark cùng database/query/index, payload, client location, pool settings, load, PGAdapter resources và transaction mode; hai dialect dùng **cùng engine**.

## 15. Tổng kết và tài liệu tham khảo

**Sáu nguyên tắc:**

1. **GoogleSQL** và **PostgreSQL interface** là hai dialect cho **cùng Spanner engine**, chọn **theo database**.
2. **PostgreSQL interface là subset có extensions**, không phải PostgreSQL server; PGAdapter dịch wire protocol sang Spanner.
3. **DDL, types và parameter syntax khác nhau**: PRIMARY KEY vị trí khác, JSON/NUMERIC/time types cần kiểm thử.
4. **PK/index design và transaction retry** quyết định scale/correctness nhiều hơn tên dialect.
5. **Spanner JDBC/client direct** phù hợp truy cập Spanner, còn **PostgreSQL JDBC + PGAdapter** giúp tận dụng công cụ PostgreSQL.
6. Luôn tính **IAM/FGAC, region/leader, latency, monitoring, backups và chi phí**, không coi portability là không cần migration.

**Tài liệu Google Cloud chính thức:**

1. [Chọn GoogleSQL hoặc PostgreSQL dialect](https://docs.cloud.google.com/spanner/docs/choose-googlesql-or-postgres).
2. [PostgreSQL interface overview và giới hạn](https://docs.cloud.google.com/spanner/docs/postgresql-interface).
3. [PostgreSQL language support](https://docs.cloud.google.com/spanner/docs/reference/postgresql/overview).
4. [PostgreSQL DDL reference](https://docs.cloud.google.com/spanner/docs/reference/postgresql/data-definition-language).
5. [PostgreSQL data types](https://docs.cloud.google.com/spanner/docs/reference/postgresql/data-types).
6. [GoogleSQL DDL reference](https://docs.cloud.google.com/spanner/docs/reference/standard-sql/data-definition-language).
7. [Tạo database qua gcloud](https://docs.cloud.google.com/spanner/docs/getting-started/gcloud).
8. [PGAdapter overview](https://docs.cloud.google.com/spanner/docs/pgadapter).
9. [Start PGAdapter](https://docs.cloud.google.com/spanner/docs/pgadapter-start).
10. [Spanner JDBC quickstart](https://docs.cloud.google.com/spanner/docs/getting-started/jdbc).
11. [Transactions](https://docs.cloud.google.com/spanner/docs/transactions).
12. [IAM roles and permissions](https://docs.cloud.google.com/iam/docs/roles-permissions/spanner).
13. [Fine-grained access control](https://docs.cloud.google.com/spanner/docs/configure-fgac).
14. [Regional/multiregion configurations](https://docs.cloud.google.com/spanner/docs/instance-configurations).
15. [System insights/monitoring](https://docs.cloud.google.com/spanner/docs/monitoring-console).
16. [Migrate PostgreSQL to Spanner](https://docs.cloud.google.com/spanner/docs/migrating-postgres-spanner).

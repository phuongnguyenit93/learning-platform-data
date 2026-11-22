# Datastream và change data capture từ cơ sở dữ liệu trên Google Cloud

> **Chương:** Pipeline và xử lý dữ liệu  
> **Mô-đun:** **CLOUD_PROVIDERS_GCP** — Khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí.

Một hệ thống Java trên Cloud Run ghi đơn hàng vào PostgreSQL, trong khi bộ phận phân tích muốn xem số liệu trong BigQuery gần thời gian thực. Chạy câu **SELECT toàn bảng mỗi phút** làm tăng tải database, truyền lại dữ liệu cũ và khó biết bản ghi nào đã bị sửa hoặc xóa. **Change Data Capture (CDC)** thay cách tiếp cận đó bằng việc đọc **dòng thay đổi từ nhật ký giao dịch** của database, sau đó đưa thay đổi tới nơi phân tích hoặc một pipeline xử lý khác.

**Datastream** là dịch vụ CDC và replication dạng serverless của Google Cloud. Datastream có thể chụp dữ liệu lịch sử (**backfill**), tiếp tục đọc các thao tác INSERT/UPDATE/DELETE sau đó và truyền tới **BigQuery**, **Cloud Storage** hoặc đích Apache Iceberg được hỗ trợ. Bài này tập trung luồng **Cloud SQL for PostgreSQL → Datastream → BigQuery**, rồi mở rộng sang file CDC trong Cloud Storage và Dataflow.

**Giới hạn an toàn:** tạo stream, bật logical replication, mở kết nối hoặc backfill trên database thật có thể tăng I/O, giữ WAL và phát sinh chi phí. Chỉ thực hành trên database/table lab do bạn sở hữu, có owner và change approval; tuyệt đối không thay flags, publication, slot hoặc xóa tài nguyên production chỉ để thử bài.

## Mục tiêu học tập

1. Phân biệt **CDC theo transaction log**, batch snapshot, streaming events và event sourcing.
2. Giải thích **connection profile, stream, stream object, event, initial backfill, continuous CDC**, checkpoint và replication lag.
3. Chuẩn bị PostgreSQL source: logical decoding, publication, replication slot, user và quyền đọc hạn chế.
4. Thiết kế đường kết nối nguồn bằng public allowlist hoặc private connectivity và quản lý danh tính Datastream.
5. Cấu hình stream tới BigQuery với **Merge/Append-only**, schema mapping và data staleness.
6. Kiểm chứng INSERT/UPDATE/DELETE, metadata, sự khác nhau giữa trạng thái hiện tại và lịch sử thay đổi.
7. Phân tích rủi ro **at-least-once, out-of-order delivery, schema evolution, khóa chính, WAL retention** và phục hồi.
8. Theo dõi data freshness, system/total latency, lỗi, áp lực lên nguồn, quota và chi phí; hoàn thành bài tập có đáp án.

## 1. Vì sao CDC khác batch ETL?

~~~mermaid
flowchart LR
    APP["Cloud Run Java app"] --> SQL[("Cloud SQL PostgreSQL\norders")]
    SQL --> WAL["Transaction log: WAL"]
    WAL --> DS["Datastream\nsource profile + stream"]
    DS --> BQ["BigQuery\nMerge / Append-only"]
    DS -. "Một stream khác nếu cần" .-> GCS["Cloud Storage\nAvro / JSON"]
    GCS --> DF["Dataflow / Spark\ncustom transforms"]
    DF --> DW["Destination / curated tables"]
    BQ --> BI["BI / BigQuery ML / analytics"]
~~~

| Phương án | Nguồn dữ liệu | Thích hợp | Rủi ro đặc trưng |
|---|---|---|---|
| **Batch full extract** | SELECT toàn bảng định kỳ | Bảng nhỏ, độ trễ tính theo giờ/ngày | Tốn scans, khó nhận DELETE, lặp dữ liệu |
| **Batch incremental** | WHERE updated_at > watermark | Bảng có watermark tin cậy | Clock skew, late commit, hard delete không thấy |
| **Log-based CDC** | WAL/binlog/redo log | Gần thời gian thực, INSERT/UPDATE/DELETE | Log retention, quyền replication, schema drift |
| **Application event** | Event do service phát hành | Nghiệp vụ có semantics rõ | Nếu không dùng outbox có thể lệch DB/event |
| **Event sourcing** | Event store là nguồn sự thật | Audit/replay theo event domain | Không tự có khi chỉ đọc CDC |

**CDC không đồng nghĩa event sourcing.** Một thay đổi bảng **status=PAID** cho biết database đổi trạng thái, chưa chắc chứa đủ ý nghĩa nghiệp vụ, người dùng hoặc lý do thanh toán. Nếu cần business events đáng tin cậy, dùng **transactional outbox** trong cùng transaction với dữ liệu nghiệp vụ rồi CDC bảng outbox, hoặc kiến trúc phù hợp.

### 1.1. Một bản ghi đi qua những bước nào?

~~~mermaid
sequenceDiagram
    participant A as Orders API
    participant P as PostgreSQL
    participant W as WAL / replication slot
    participant D as Datastream
    participant B as BigQuery
    A->>P: BEGIN; UPDATE orders; COMMIT
    P->>W: Ghi WAL khi commit
    D->>W: Đọc logical changes
    W-->>D: Row change + source metadata
    D->>B: Gửi sự kiện CDC
    B-->>D: Tiếp nhận/áp thay đổi
    Note over D,B: At-least-once và không bảo đảm event order
    Note over P,B: Gần thời gian thực, không có SLA đúng 0 ms
~~~

Datastream **không thay đổi transaction của PostgreSQL** và không đưa BigQuery vào cùng một distributed transaction với nguồn. Tại mọi thời điểm có thể tồn tại **replication lag**; truy vấn BigQuery có thể chưa thấy commit mới nhất.

## 2. Năm đối tượng Datastream cần phân biệt

| Đối tượng | Ý nghĩa | Ví dụ |
|---|---|---|
| **Private connectivity configuration** | Kết nối mạng riêng từ Datastream tới source, cấu hình nếu cần | ds-private-vpc |
| **Connection profile** | Credentials, host, port và loại nguồn/đích | orders-pg-source, analytics-bq-dest |
| **Stream** | Liên kết source + destination profiles, object filters, backfill và cách ghi | orders-cdc-lab |
| **Stream object** | Một table/collection được sao chép trong stream | public.orders_cdc_lab |
| **Event** | Một thay đổi dữ liệu/row hoặc bản ghi từ backfill | UPDATE order 1001 |

**Backfill** đọc trạng thái lịch sử có sẵn của table; **CDC** đọc thay đổi đang tiếp diễn. Datastream có thể chạy backfill và CDC cùng lúc theo cấu hình, nhưng **thứ tự sự kiện đến đích không được bảo đảm** và **có thể giao trùng**. Metadata hỗ trợ sắp lại hoặc khử trùng khi cần; **không dùng thời điểm file đến Cloud Storage làm thứ tự nghiệp vụ**.

### 2.1. Các trạng thái và định nghĩa quan trọng

- **RUNNING:** Datastream đang thực hiện replication của stream.
- **PAUSED:** stream đã tạm ngừng; trước đó có giai đoạn **DRAINING** để thoát công việc đang xử lý.
- **FAILED/ERROR:** cần kiểm tra stream details, lỗi connectivity, source logs và destination permission.
- **Backfill completed:** phạm vi dữ liệu lịch sử đã chép xong; **không** chứng minh độ trễ CDC đang bằng 0.
- **Source position:** với PostgreSQL là vị trí/tiến độ đọc WAL, không phải đơn giản một timestamp trên ứng dụng.
- **Destination write/merge lag:** đích có thể tiếp nhận event nhưng chưa áp vào trạng thái truy vấn cuối cùng.

Một **PostgreSQL logical replication slot** gắn với **một database và một luồng đọc**, nên mỗi stream CDC cần slot phù hợp; không chia sẻ tùy tiện một slot cho hai streams.

## 3. Nguồn và đích được hỗ trợ: chọn theo workload

| Source điển hình | Cách CDC cơ bản | Chú ý |
|---|---|---|
| **PostgreSQL/Cloud SQL/AlloyDB** | Logical decoding của **WAL** qua publication + slot | Kiểm tra version, privileges, replica identity, WAL retention |
| **MySQL/Cloud SQL MySQL** | Binary log hoặc GTID theo cách hỗ trợ | Binlog retention, ROW events, InnoDB, failover |
| **Oracle** | Redo logs/LogMiner cùng supplemental logging | Quyền đọc logs, LOB/DDL và license/chi phí |
| **SQL Server** | Change tables CDC hoặc transaction log method | CDC jobs, log truncation safeguards, version limits |
| **MongoDB** | Change streams và snapshot theo hỗ trợ | Sharding/change stream permissions, type mapping |
| **Spanner** | Cơ chế change stream theo nguồn được hỗ trợ | Tính năng và cấu hình khác RDBMS truyền thống |

Datastream còn hỗ trợ một số nguồn SaaS; trạng thái Preview, phiên bản và vùng hỗ trợ có thể đổi. Xem **[Sources](https://docs.cloud.google.com/datastream/docs/sources)** trước khi xây giải pháp thay vì mặc định mọi engine/edition/column type đều được đọc.

| Destination | Đầu ra | Khi nào chọn? |
|---|---|---|
| **BigQuery** | Table có trạng thái hiện tại hoặc lịch sử thay đổi | Dashboard/analytics gần thời gian thực |
| **Cloud Storage** | File sự kiện Avro/JSON và metadata | Audit, lake, pipeline tự chuyển đổi |
| **Apache Iceberg tables** | Đích Iceberg tích hợp theo điều kiện hỗ trợ | Lakehouse và công cụ xử lý truy vấn phù hợp |
| **Cloud SQL/Spanner qua Dataflow** | Đường tích hợp **Datastream → Cloud Storage → Dataflow** | Replication/transform tùy biến, **không phải direct native destination mặc định** |

### 3.1. BigQuery Merge khác Append-only

| Chế độ | Kết quả | Ví dụ INSERT → UPDATE → DELETE |
|---|---|---|
| **Merge** | Bảng phản ánh trạng thái hàng hiện tại của nguồn; cần **primary key** | Sau áp DELETE, row không còn |
| **Append-only** | Lưu chuỗi sự kiện/thay đổi, không tự gộp trạng thái hiện tại | Có events INSERT, UPDATE-INSERT, DELETE |
| **Không có primary key** | Datastream ghi theo append-only ngay cả khi stream chọn Merge | Không thể suy count destination = count source |

Với **Merge**, BigQuery sử dụng khả năng CDC qua **Storage Write API** để hợp nhất thay đổi. Với **Append-only**, metadata bao gồm thông tin như **CHANGE_TYPE** và **CHANGE_SEQUENCE_NUMBER**. Không được hiểu dữ liệu append-only là bảng snapshot có một row/đối tượng. Ở nguồn PostgreSQL, **giá trị LOB/TOAST lớn** có thể cần lookup bổ sung; một số intermediate states có thể không được chụp đầy đủ trong những tình huống UPDATE/DELETE nhanh. Kiểm tra yêu cầu replay/audit trước khi hứa giữ “mọi trạng thái trung gian”.

### 3.2. Giới hạn kích thước sự kiện

Theo tài liệu hành vi Datastream, kích thước mỗi event có giới hạn **20 MB khi tới BigQuery** và **100 MB khi tới Cloud Storage**. Đây **không** phải cam kết mọi LOB đều được sao chép; mỗi source và kiểu dữ liệu có giới hạn riêng. Dữ liệu vượt giới hạn phải được xử lý bằng kiến trúc khác, ví dụ chuyển payload lớn vào object storage rồi CDC metadata.

## 4. Lab A — Chuẩn bị PostgreSQL source chỉ cho dữ liệu giả lập

**Bối cảnh:** hệ thống Orders API Java ghi dữ liệu vào **Cloud SQL for PostgreSQL**; ta chỉ sao chép bảng **public.orders_cdc_lab** thuộc database **orders_lab** sang BigQuery. Nếu bạn không có quyền tạo database/table hoặc bật logical decoding, có thể làm các phần phân tích SQL/thiết kế mà **không** chạm database thật.

### 4.1. Preflight trên project lab (chỉ đọc)

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
REGION="asia-southeast1"
PG_INSTANCE="YOUR_CLOUD_SQL_POSTGRES_INSTANCE"
STREAM_ID="orders-cdc-lab"
BQ_DATASET="cdc_orders_lab"

gcloud auth list
gcloud config list project
gcloud sql instances describe "$PG_INSTANCE" \
  --project="$PROJECT_ID" \
  --format="yaml(name,state,region,databaseVersion,connectionName,ipAddresses,settings.databaseFlags)"
gcloud datastream streams list \
  --project="$PROJECT_ID" --location="$REGION"
gcloud datastream connection-profiles list \
  --project="$PROJECT_ID" --location="$REGION"
~~~

Lệnh **chỉ đọc** trước tiên xác minh đúng project và instance. Database **orders_lab** phải tồn tại, có PostgreSQL user được owner cấp quyền tạo bảng và định nghĩa publication/slot trong phạm vi lab. Không bật network public hoặc sửa flags production khi chưa có change window.

### 4.2. Tạo bảng thử với primary key

Chạy trong **database orders_lab** bằng role sở hữu schema/table phù hợp. SQL dưới đây **tạo và sửa dữ liệu thật**, không chạy trên database dùng chung nếu không được phép.

~~~sql
-- THAY ĐỔI DATABASE LAB.
CREATE TABLE public.orders_cdc_lab (
    order_id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    total_vnd NUMERIC(12, 2) NOT NULL
        CHECK (total_vnd >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO public.orders_cdc_lab
    (order_id, status, total_vnd)
VALUES
    (1001, 'NEW', 150000.00),
    (1002, 'NEW', 250000.00),
    (1003, 'PAID', 79000.00);
~~~

**Lưu ý:** nếu bảng đã tồn tại, **không chạy CREATE TABLE/INSERT mù quáng**; chọn bảng khác hoặc dừng lab để tránh xung đột. **PRIMARY KEY(order_id)** giúp Datastream dùng BigQuery **Merge** có ngữ nghĩa “một hàng hiện hành/khóa” sau khi các sự kiện đã được áp dụng. Nếu PK bị bỏ hoặc thay khi stream chạy, phải đánh giá khả năng sao chép lại bảng và rủi ro sai dữ liệu.

### 4.3. Bật logical decoding trên Cloud SQL

Cloud SQL for PostgreSQL dùng database flag **cloudsql.logical_decoding=on**. Thay đổi flag này **cần restart instance** nên có thể gây gián đoạn dịch vụ.

**Quy trình trong Google Cloud Console (chỉ khi được chủ sở hữu phê duyệt):**

1. **Cloud SQL → Instances → chọn instance lab → Edit**.
2. Trong **Flags**, đặt **cloudsql.logical_decoding = on**.
3. Review ảnh hưởng tới connections, replication slots, WAL và thời gian restart.
4. Lưu cấu hình và restart theo maintenance window.
5. Xác minh database thực sự ở trạng thái logical, không chỉ nhìn cấu hình.

~~~sql
-- CHỈ ĐỌC trong PostgreSQL.
SHOW wal_level;
SHOW max_replication_slots;
SHOW max_wal_senders;

-- Kiểm tra slot đã tồn tại và trạng thái của nó.
SELECT
    slot_name,
    plugin,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
~~~

**Nếu là PostgreSQL self-managed**, cơ chế bật logical replication dùng **wal_level=logical**, đồng thời điều chỉnh **max_replication_slots/max_wal_senders**, restart theo cách của máy chủ; không áp flag Cloud SQL cho PostgreSQL tự quản. Một số nền tảng nguồn như AlloyDB/RDS có quy trình riêng.

### 4.4. Publication và replication slot

Trong database **orders_lab**, người quản trị có quyền thích hợp tạo **publication chỉ cho table lab**, rồi **logical replication slot** với plugin **pgoutput**:

~~~sql
-- THAY ĐỔI DATABASE / WAL — chỉ DBA của môi trường lab.
CREATE PUBLICATION ds_orders_lab_pub
FOR TABLE public.orders_cdc_lab;

SELECT pg_create_logical_replication_slot(
    'ds_orders_lab_slot', 'pgoutput'
);
~~~

**Cần nhớ:**

- **Publication** định nghĩa tập bảng và các thay đổi sẽ xuất hiện; chỉ publish bảng cần thiết, tránh **FOR ALL TABLES** không kiểm soát.
- **Slot** ghi nhận tiến độ đã tiêu thụ WAL. Khi slot tồn tại nhưng consumer chưa đọc, PostgreSQL có thể **giữ WAL vô hạn theo cấu hình cho tới khi disk/quota cạn**, ảnh hưởng production. Không tạo slot thật rồi bỏ quên.
- **Một slot** dùng cho **một stream**; tên slot không được trùng và phải khớp tên nhập trong Datastream source configuration.
- Nếu cần nhiều streams trên cùng database, tạo publication/slot riêng khi thích hợp và đánh giá thêm tải. Đừng dùng cùng một slot cho hai consumers.
- Với bảng có UPDATE/DELETE, **replica identity/primary key** ảnh hưởng thông tin khóa; bảng demo có PK nên phù hợp.

### 4.5. Tài khoản Datastream riêng và quyền tối thiểu

Chạy bằng role quản trị database được phép:

~~~sql
-- THAY ĐỔI USER: không đưa password literal vào source/SQL history.
CREATE ROLE ds_orders_reader LOGIN REPLICATION;
GRANT CONNECT ON DATABASE orders_lab TO ds_orders_reader;
GRANT USAGE ON SCHEMA public TO ds_orders_reader;
GRANT SELECT ON TABLE public.orders_cdc_lab TO ds_orders_reader;
~~~

Sau đó **trong psql**, dùng lệnh tương tác sau để đặt mật khẩu mạnh, lưu trong hệ quản lý bí mật được phép:

~~~text
\password ds_orders_reader
~~~

Đối với các bảng thêm trong tương lai, owner tạo bảng có thể cấp **ALTER DEFAULT PRIVILEGES ... GRANT SELECT**; quyền mặc định của PostgreSQL gắn với **role tạo object**, không tự có hiệu lực cho mọi owner trong database. Đừng grant SELECT trên tất cả bảng có dữ liệu nhạy cảm chỉ để stream một bảng thử.

### 4.6. Quan sát WAL slot mỗi khi stream chưa chạy

~~~sql
-- CHỈ ĐỌC; chạy bằng tài khoản có quyền xem replication stats.
SELECT
    slot_name,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    pg_size_pretty(
      pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)
    ) AS approx_wal_retained
FROM pg_replication_slots
WHERE slot_name = 'ds_orders_lab_slot';
~~~

**Không coi đây là số byte chính xác của mọi file vật lý cần xóa.** Nó giúp nhận diện nguy cơ WAL retention khi stream đứng. Trước khi dừng quá lâu, phải có phương án theo dõi storage và xử lý slot có phê duyệt; **không drop replication slot đang được một stream hoạt động sử dụng**.

## 5. Thiết kế kết nối, tài khoản và vùng dữ liệu

### 5.1. Hai kiểu kết nối tới database nguồn

| Kết nối | Phù hợp | Điều kiện |
|---|---|---|
| **Public network + IP allowlisting** | Lab có policy cho phép | Database có địa chỉ reachable, firewall/allowlist Datastream IP, TLS/credentials phù hợp |
| **Private connectivity** | Production có VPC/private IP | Cấu hình private connectivity (ví dụ VPC peering/PSC theo lựa chọn được hỗ trợ), routes/IP ranges/DNS/firewall đúng |
| **SSH tunnel** | Source tự quản hoặc mạng riêng có bastion hỗ trợ | Bảo vệ host/key, network path và access review |

**Private connectivity không tự xuất hiện khi chọn private IP.** Đường mạng từ Datastream tới database phải thật sự hoạt động; BigQuery không phải source network client ở mô hình Datastream direct destination. Với Cloud SQL có cơ chế hỗ trợ kết nối riêng; xem [private connectivity options](https://docs.cloud.google.com/datastream/docs/network-connectivity).

### 5.2. Connection profiles và secrets

- **PostgreSQL source profile:** host/IP, port (thường 5432), username/password, database, TLS/SSL, phương thức kết nối mạng.
- **BigQuery destination profile:** project/destination BigQuery, không nhập database password.
- **Stream:** chọn source + destination profiles, publication/slot, table include/exclude, backfill và write mode.
- **Datastream service agent:** identity do Google Cloud quản lý dùng quyền trên đích; khi destination nằm ở **project khác**, cần cấp vai trò/quyền phù hợp ở nơi chứa dữ liệu.
- **Operator IAM:** chỉ người được phân quyền tạo/sửa stream, connection profile và network config. Phân quyền triển khai không đồng nghĩa được đọc toàn bộ bảng nguồn.

Không ghi database password/connection secret vào Markdown/Git hoặc shell history. Nếu phải rotate password, cần cập nhật connection profile, xác minh stream reconnect và kiểm tra không làm mất WAL/log retention window.

### 5.3. Vị trí dữ liệu, độ tin cậy và compliance

- Chọn **Datastream stream region** gần database và đích khi có thể để giảm độ trễ/egress.
- BigQuery dataset có **location** riêng; kiểm tra location được hỗ trợ và chính sách residency.
- Tách **dev/staging/prod** bằng IAM và dự án/bộ dữ liệu rõ ràng.
- Xác định dữ liệu nhạy cảm trước khi đưa lên đích; CDC có thể sao chép cột PII vô tình nếu phạm vi quá rộng.
- Áp nguyên tắc **data minimization** ở source table/object filters; Datastream không biến bản sao dữ liệu thành ẩn danh.

## 6. Lab B — Tạo stream PostgreSQL → BigQuery bằng Console

### 6.1. Chuẩn bị đích

Tạo **BigQuery dataset riêng** trong project lab, ví dụ **cdc_orders_lab**. Chọn location BigQuery hợp lệ, owner và thời hạn giữ dữ liệu. Đảm bảo **Datastream API/BigQuery API** bật và Datastream service agent có quyền cần thiết. Dataset đích không chứa dữ liệu có cùng tên table mà bạn không muốn ghi đè.

~~~bash
# CHỈ ĐỌC xem API bật và dataset đã có hay chưa.
gcloud services list --enabled --project="$PROJECT_ID" \
  --filter="NAME:(datastream.googleapis.com OR bigquery.googleapis.com)"

bq --project_id="$PROJECT_ID" ls

# THAY ĐỔI — chỉ tạo dataset LAB khi chưa tồn tại.
bq --project_id="$PROJECT_ID" --location="$REGION" mk \
  --dataset "$PROJECT_ID:$BQ_DATASET"
~~~

**Chú ý:** bq **--location** phải là BigQuery dataset location được hỗ trợ; trong ví dụ sử dụng cùng region với stream để thuận tiện, nhưng mọi tổ chức phải kiểm tra trước sự hỗ trợ của từng dịch vụ. Không dùng BigQuery multi-region US để lưu dữ liệu bị ràng buộc residency tại một region khác.

### 6.2. Các bước thiết lập trong Datastream Console

1. **Datastream → Connection profiles → Create profile** cho source **PostgreSQL**. Chọn region của Datastream, host/database/user/SSL cùng network connectivity đã chuẩn bị; **Test connection**.
2. Tạo destination profile **BigQuery** theo project và region hỗ trợ.
3. **Datastream → Streams → Create stream**; nhập tên và stream ID, region, source/destination profile.
4. Chọn **Source objects**: **chỉ database orders_lab → schema public → table orders_cdc_lab**. Kiểm tra exclude filters và DDL limitations.
5. Nhập publication **ds_orders_lab_pub** và replication slot **ds_orders_lab_slot** cho PostgreSQL source.
6. Chọn **Backfill all objects** trong phạm vi bảng lab để có ba đơn hàng đã tạo; nếu không backfill, chỉ có CDC kể từ vị trí được cấu hình.
7. **BigQuery destination dataset = cdc_orders_lab** và **Single dataset for all schemas**. Datastream tạo table tên **public_orders_cdc_lab** theo quy tắc **schema_table**.
8. Chọn **Merge** (bảng có primary key) và đặt **data staleness limit** theo nhu cầu freshness/cost.
9. **Validate stream**: kiểm tra nguồn, quyền, publication/slot, kết nối và đích. Chỉ khi PASS và được duyệt mới **Create & Start**.
10. Vào **Streams → orders-cdc-lab → Monitoring / Objects** theo dõi backfill và trạng thái CDC.

**Quan trọng:** các tên control và yêu cầu chuẩn bị có thể thay đổi theo nguồn/edition; nếu Console hỗ trợ automated Cloud SQL stream flow, vẫn cần xác nhận các quyền và tác động nguồn. **Không đánh dấu đã hoàn tất backfill ngay sau thao tác Create & Start.**

### 6.3. BigQuery Merge và data staleness

Khi dùng **Merge**, BigQuery sử dụng CDC ingestion và áp thay đổi theo cấu hình. Trong thời gian backlog hoặc merge chưa bắt kịp, kết quả truy vấn có thể chịu tác động của **max_staleness** và runtime apply. **Staleness của BigQuery khác với data freshness của Datastream**: một cái liên quan áp dữ liệu trong BigQuery, cái kia đo tiến độ Datastream đọc từ source.

Trong **Append-only**, dữ liệu là lịch sử sự kiện, không tự trở thành một bảng current-state. Chọn chế độ trước khi consumer dùng schema; **không đổi tùy tiện khi đã có downstream jobs**.

## 7. Lab C — Kiểm chứng INSERT, UPDATE và DELETE ở BigQuery

### 7.1. Đợi initial backfill hoàn tất

Vào **Datastream → Streams → orders-cdc-lab** và xác minh stream ở trạng thái chạy, đối tượng **public.orders_cdc_lab** đã hoàn thành initial backfill hoặc không còn backfill pending cho đối tượng đó. Tiếp theo mở BigQuery Studio tại project/dataset đã chọn.

~~~sql
-- CHỈ ĐỌC BigQuery MERGE mode. Thay PROJECT_ID bằng project lab thật.
SELECT
  order_id,
  status,
  total_vnd,
  updated_at,
  datastream_metadata
FROM `PROJECT_ID.cdc_orders_lab.public_orders_cdc_lab`
ORDER BY order_id;
~~~

**Kỳ vọng sau backfill và khi CDC đã bắt kịp:** có 3 rows với order_id **1001, 1002, 1003**. Nếu bảng đích chưa có hoặc chưa đủ rows, trước tiên kiểm tra stream objects/backfill state/permissions; không chạy lại INSERT vào nguồn để “ép” Datastream thành công.

### 7.2. Tạo thay đổi trên PostgreSQL nguồn

Chỉ sau khi baseline BigQuery được xác minh, chạy trong database **orders_lab**:

~~~sql
-- THAY ĐỔI DỮ LIỆU LAB.
BEGIN;
UPDATE public.orders_cdc_lab
SET status = 'PAID', updated_at = CURRENT_TIMESTAMP
WHERE order_id = 1001;

INSERT INTO public.orders_cdc_lab
    (order_id, status, total_vnd)
VALUES
    (1004, 'NEW', 329000.00);

DELETE FROM public.orders_cdc_lab
WHERE order_id = 1002;
COMMIT;
~~~

Sau khi commit, không kỳ vọng bảng BigQuery đồng bộ **ngay trong một request**. Đợi theo monitoring freshness/total latency, sau đó truy vấn **cả PostgreSQL lẫn BigQuery**, so sánh kết quả:

| order_id | Trước | Sau khi CDC và Merge hoàn tất |
|---|---|---|
| **1001** | NEW | PAID |
| **1002** | NEW | **Không còn** |
| **1003** | PAID | PAID |
| **1004** | Chưa có | NEW |

Tổng số rows sau thử vẫn là **3** (tạo 1, xóa 1). Đừng lấy COUNT bằng nhau làm bằng chứng dữ liệu đúng: có thể một row thiếu và một row khác bị trùng mà count vẫn khớp.

### 7.3. Câu SQL kiểm tra đầu ra

~~~sql
-- CHỈ ĐỌC BigQuery sau khi replication catch-up.
SELECT
  order_id,
  status,
  total_vnd,
  datastream_metadata.UUID AS event_uuid,
  datastream_metadata.SOURCE_TIMESTAMP AS source_ts_raw
FROM `PROJECT_ID.cdc_orders_lab.public_orders_cdc_lab`
ORDER BY order_id;

-- Kiểm tra chính xác kỳ vọng, không chỉ số hàng.
WITH state AS (
  SELECT order_id, status
  FROM `PROJECT_ID.cdc_orders_lab.public_orders_cdc_lab`
)
SELECT
  (SELECT COUNT(*) FROM state) AS actual_rows,
  (SELECT COUNT(*) FROM state
   WHERE order_id = 1001 AND status = 'PAID') AS updated_ok,
  (SELECT COUNT(*) FROM state
   WHERE order_id = 1002) AS deleted_remaining,
  (SELECT COUNT(*) FROM state
   WHERE order_id = 1004 AND status = 'NEW') AS inserted_ok;
~~~

**Kết quả kỳ vọng sau khi bắt kịp:** **actual_rows=3**, **updated_ok=1**, **deleted_remaining=0**, **inserted_ok=1**. Với Merge và bảng có PK, Datastream metadata thường có **UUID** và **SOURCE_TIMESTAMP**; không coi chúng là cột audit lịch sử đầy đủ, vì Merge đã hợp nhất các event.

### 7.4. Nếu chọn Append-only thay vì Merge

**Không chạy SQL ở 7.3 rồi giả định output Append-only giống nhau.** Với Append-only, mỗi event được lưu thành row, bao gồm hành động UPDATE/DELETE và metadata:

~~~sql
-- CHỈ ĐỌC; áp dụng nếu table từ stream Append-only.
SELECT
  order_id,
  datastream_metadata.CHANGE_TYPE AS change_type,
  datastream_metadata.CHANGE_SEQUENCE_NUMBER AS change_sequence_number,
  datastream_metadata.UUID AS uuid
FROM `PROJECT_ID.cdc_orders_lab.public_orders_cdc_lab`
WHERE order_id IN (1001, 1002, 1004)
ORDER BY order_id, change_sequence_number;
~~~

**Cần nhớ:**

- Các change types như **INSERT**, **UPDATE-INSERT**, **UPDATE-DELETE** và **DELETE** có ý nghĩa event, **không** phải luôn một row snapshot.
- **CHANGE_SEQUENCE_NUMBER/SORT_KEYS** dùng cùng metadata để tái dựng thứ tự theo ngữ nghĩa Datastream; không suy thứ tự bằng tên file hoặc thời điểm ingestion đơn thuần.
- At-least-once có thể sinh event trùng. Nếu cần bảng trạng thái hiện tại từ Append-only, pipeline sau đó phải có **dedup + ordering + delete handling + replay** được kiểm thử.
- Các cột metadata trong Merge và Append-only **khác nhau**; tránh dùng câu query của mode này cho mode kia.
- Với bảng nguồn không có PK, hành vi append-only cũng có thể áp dụng ngay khi stream chọn Merge.

## 8. Datastream → Cloud Storage → Dataflow khi cần biến đổi

Không phải pipeline nào cũng nên ghi trực tiếp vào BigQuery. Nếu cần **giữ sự kiện thô**, transform phức tạp hoặc đẩy tới nơi chưa phải direct destination của Datastream, chọn **Cloud Storage** và một consumer xử lý tiếp.

~~~mermaid
flowchart LR
    PG[("PostgreSQL WAL")] --> DS["Datastream"]
    DS --> GCS["Cloud Storage\nAvro / JSON CDC files"]
    GCS --> DFR["Dataflow template / custom Beam"]
    DFR --> CUR["BigQuery curated / Cloud SQL / Spanner"]
    GCS --> ARCH["Archive / replay"]
    MET["Event metadata"] -. "ordering + dedup" .-> DFR
~~~

### 8.1. Cấu hình Cloud Storage destination

Khi tạo một **stream khác** trong project lab (không thay đổi stream BigQuery đang chạy nếu còn người dùng phụ thuộc):

1. Chuẩn bị bucket Cloud Storage ở location và retention phù hợp, bật logging và IAM.
2. Cấp **Datastream service agent** quyền ghi/read bucket tối thiểu theo hướng dẫn destination; không dùng allUsers.
3. Tạo destination connection profile **Cloud Storage** và chọn bucket/prefix riêng.
4. Chọn **Avro** để có schema tự mô tả hoặc **JSON** nếu downstream xử lý text; JSON có tùy chọn ghi kèm **Unified Types schema file**.
5. Kiểm tra **gzip compression, file size/flush frequency** và ảnh hưởng tới độ trễ/chi phí file nhỏ.
6. Validate stream, chọn source objects và backfill, rồi start khi có owner approval.

Đường dẫn lưu file thường mang cấu trúc **prefix/object-name/yyyy/mm/dd/hh/mm/file**; phần thời gian dùng metadata nguồn theo định dạng Datastream. **Không** dùng thứ tự file name hoặc timestamp thư mục làm thứ tự commit tuyệt đối.

### 8.2. Một sự kiện minh họa (pseudocode, không phải payload chính xác)

~~~json
{
  "row": {
    "order_id": 1001,
    "status": "PAID"
  },
  "metadata": {
    "source": "PostgreSQL",
    "operation": "UPDATE",
    "source_position": "<WAL-position>",
    "event_id": "<unique-change-id>"
  }
}
~~~

Schema **JSON trên chỉ để giảng khái niệm**, không phải JSON response contract của Datastream. Event thật có **source-specific metadata**, **Datastream metadata**, payload với tên trường và encoding theo phiên bản/format; dùng schema tài liệu để parse. **Avro** chứa schema/type để tránh suy bằng tên file. Xem [Events and streams](https://docs.cloud.google.com/datastream/docs/events-and-streams).

### 8.3. Khi dùng Dataflow

- Dùng **Datastream to BigQuery** hoặc template tương ứng với phiên bản hỗ trợ; nếu cần đích khác, dùng **Apache Beam** pipeline phù hợp.
- Đọc cùng data + metadata, chuẩn hóa schema, xử lý **at-least-once** và khóa nghiệp vụ.
- Quyết định chế độ **current-state** hay **event history**, không trộn hai kết quả trong cùng bảng.
- Dùng checkpoint, dead-letter/quarantine riêng cho events không parse được, cảnh báo và replay theo job ID.
- Đặt **windowing/triggers** theo event-time và độ trễ có thể chấp nhận; không suy data đã hoàn tất chỉ vì một file được tạo.
- Bảo vệ dữ liệu thô trong Cloud Storage bằng bucket IAM, encryption, lifecycle và retention.

**Datastream không mặc định tạo Pub/Sub message cho từng change event.** Có thể dùng Cloud Storage notifications/Eventarc để kích hoạt consumer khi file xuất hiện, nhưng notification “file finalized” không mang ý nghĩa “một database transaction đã hoàn tất”. Consumer phải parse và xử lý nhiều events trong file.

## 9. Schema evolution và khóa chính: nơi dễ sai dữ liệu nhất

### 9.1. Thay đổi schema được hỗ trợ không đồng nghĩa mọi DDL đều an toàn

PostgreSQL source có nhiều hạn chế liên quan DDL khi stream đang chạy. Cần kiểm thử theo phiên bản/source:

| Thay đổi | Rủi ro | Chính sách đề xuất |
|---|---|---|
| Thêm cột nullable ở cuối | Thường dễ chuyển hơn nhưng vẫn phải xác minh | Migration + stream/destination schema check |
| Đổi type INT → TEXT | Có thể làm event decode/map sai | Dừng và review compatibility trước DDL |
| Đổi tên/xóa cột | Có thể gây loss/drift trên downstream | Expand/contract, không phá schema đột ngột |
| Đổi khóa chính | Có thể phá BigQuery Merge | Cutover/đối soát/rebackfill theo docs |
| Bỏ PK khỏi bảng | Bảng có thể trở thành append-only | Cấm thay mà không review |
| Thiếu replica identity với UPDATE/DELETE | Datastream có thể không capture đủ event | Primary key hoặc REPLICA IDENTITY hợp lệ |
| Bảng chứa TOAST/LOB lớn | Có thể cần lookup bổ sung, mất intermediate states | Test và giới hạn kích thước/biến động |
| Thêm bảng mới ngoài publication | Không tự được sao chép | Cập nhật publication và stream object filters |

Tùy schema/user/engine, Datastream **không phát hiện mọi thay đổi DDL**. Không biến bảng BigQuery đang chạy production thành chỗ thử ALTER TABLE; chuẩn bị migration riêng, schema compatibility checklist và khả năng phục hồi/backfill.

### 9.2. Chọn REPLICA IDENTITY

Với bảng PostgreSQL có PK như **orders_cdc_lab**, lựa chọn ưu tiên là **REPLICA IDENTITY DEFAULT**. Khi thiếu PK, có thể dùng **UNIQUE NOT NULL index** và **USING INDEX** hoặc một phương án khác được Datastream hỗ trợ, nhưng phải kiểm tra ràng buộc type/số columns của BigQuery. **REPLICA IDENTITY FULL** có overhead lớn và có thể vượt giới hạn 16 columns cho BigQuery merge; không dùng như cách chữa lỗi chung.

~~~sql
-- CHỈ ĐỌC thông tin khóa và replica identity.
SELECT
  c.relname AS table_name,
  c.relreplident AS replica_identity,
  pg_get_indexdef(i.indexrelid) AS index_definition
FROM pg_class c
LEFT JOIN pg_index i ON i.indrelid = c.oid AND i.indisprimary
WHERE c.oid = 'public.orders_cdc_lab'::regclass;
~~~

**Không sửa PK/REPLICA IDENTITY trên production** khi chưa biết stream sử dụng chúng làm logical key như thế nào.

## 10. Độ chính xác của replication: checkpoint, dedup và đối soát

### 10.1. Datastream không hứa exactly-once delivery

Datastream có **at-least-once event delivery** và không bảo đảm event arrival order. Một sự kiện có thể được gửi lại sau retry/khôi phục; event A ghi trước không chắc đến đích trước event B. **Đích hoặc consumer phải dùng metadata và logic idempotent** nếu cần current-state chính xác hoặc lịch sử không trùng.

~~~mermaid
sequenceDiagram
    participant PG as PostgreSQL
    participant DS as Datastream
    participant Q as Consumer / BigQuery
    PG->>DS: INSERT id=1001 seq=10
    PG->>DS: UPDATE id=1001 seq=11
    DS->>Q: UPDATE seq=11
    DS->>Q: INSERT seq=10 (đến sau)
    Note over Q: Không lấy 'last event arrived' làm row state
    DS->>Q: UPDATE seq=11 (gửi trùng)
    Note over Q: Dùng metadata/sequence/dedup trước áp trạng thái
~~~

**BigQuery Merge** thực hiện consolidation dựa trên nguồn có khóa theo cơ chế Datastream/BigQuery CDC. Khi xử lý sự kiện thô ở Cloud Storage hoặc custom Dataflow, bạn phải **tự** làm dedup, ordering và delete handling. Đừng hứa sự kiện được xử lý đúng một lần chỉ vì stream trạng thái RUNNING.

### 10.2. Số liệu đối soát nên dùng

| Kiểm tra | Mục tiêu | Cảnh báo |
|---|---|---|
| Source và destination **COUNT** | Phát hiện chênh lớn | Không đủ để chứng minh chính xác |
| Số **distinct primary keys** | Phát hiện duplicate keys ở current-state | Append-only không áp dụng trực tiếp |
| Sample checksum theo key range | Phát hiện sai payload | Cần normalize type/timezone |
| So sánh theo time window đã đóng | Tránh so nguồn đang ghi liên tục | Chỉ so khi CDC lag đã thấp |
| High-watermark / source position | Biết stream đã đọc tới đâu | Không tự đồng nghĩa table đã merge |
| DELETE correctness | Không còn row đã xóa ở Merge | Tránh coi tombstone là row đang tồn tại |
| Tỷ lệ unsupported events | Phát hiện loại data/DDL không được xử lý | Có thể mất thay đổi dù stream chạy |
| Backfill per-object status | Xác nhận đầy đủ dữ liệu lịch sử | Stream RUNNING chưa đủ |

### 10.3. Đối soát một bảng lab ở trạng thái tĩnh

1. Tạm dừng **writes từ ứng dụng lab** bằng cách riêng của lab, không pause production stream.
2. Ghi lại thời điểm/source checkpoint và đảm bảo **không có transaction đang chờ**.
3. Đợi Datastream **total latency** và BigQuery apply bắt kịp; dùng stream monitoring, không chỉ sleep cố định vài giây.
4. So sánh **order_id, status, total_vnd, updated_at** giữa PostgreSQL và BigQuery, chuẩn hóa timestamp/decimal.
5. Phân loại sai lệch: chưa bắt kịp, backfill thiếu, PK sai, type mismatch, DDL không tương thích, dedup/merge lỗi.
6. Lưu kết quả trong change ticket: tập keys thử, SQL checksum, metric thời điểm đo và người xác nhận.

Không dùng **MAX(updated_at)** làm source-of-truth checkpoint cho CDC trong mọi trường hợp: database có thể UPDATE không đổi timestamp, xóa row, backfill snapshot hoặc commit lệch thời gian ứng dụng.

## 11. Giám sát CDC: freshness, latency và nguy cơ WAL đầy ổ

### 11.1. Ba nhóm latency không được đánh đồng

| Tín hiệu Datastream | Đo điều gì? | Khi tăng cao cần xem |
|---|---|---|
| **Data freshness** | Khoảng trễ từ khi source commit thay đổi tới lúc Datastream đọc sự kiện đang xử lý | Source overload, WAL backlog, quyền replication, network source |
| **System latency** | Khoảng trễ Datastream xử lý từ khi đọc nguồn tới khi ghi đích | Destination quota/permissions, pipeline processing |
| **Total latency** | End-to-end source commit → Datastream ghi đích | Cả hai nhóm trên và queueing |
| **Backfill progress** | Số objects còn pending/in progress/failed | Large-table scans, source I/O và table-specific errors |
| **Unsupported events** | Sự kiện không thể xử lý | DDL/schema/data type không tương thích |
| **PostgreSQL WAL retention** | WAL bị giữ bởi replication slot | Chậm đọc source, slot inactive, disk tăng |

**Một chỉ số data freshness bằng 0 có thể đơn giản là không có sự kiện mới**, không phải chứng cứ chắc chắn tất cả các downstream tables đã áp đủ thay đổi. Xem **system/total latency**, stream errors, BigQuery query freshness và end-to-end reconciliation.

### 11.2. Bộ lệnh và bảng kiểm chỉ đọc

~~~bash
# Datastream status/config; không thay đổi resources.
gcloud datastream streams list \
  --project="$PROJECT_ID" --location="$REGION"

gcloud datastream streams describe "$STREAM_ID" \
  --project="$PROJECT_ID" --location="$REGION" \
  --format="yaml(name,state,errors,sourceConfig,destinationConfig,backfillAll)"

# Chỉ xem connection profiles; tránh in secrets vào ticket.
gcloud datastream connection-profiles list \
  --project="$PROJECT_ID" --location="$REGION"
~~~

Trong **Datastream → Streams → stream → Monitoring**, đọc graphs throughput, data freshness, system/total latency, unsupported events và backfill object states. Trong **Cloud Monitoring**, có thể tạo alert cho các metric thuộc **datastream.googleapis.com**, ví dụ **stream/freshness**, **stream/system_latencies**, **stream/total_latencies**; đối chiếu chính xác tên metrics/labels trong Metrics Explorer tại project hiện hành.

### 11.3. Theo dõi source PostgreSQL

~~~sql
-- CHỈ ĐỌC; cần quyền xem replication stats.
SELECT
  slot_name,
  active,
  restart_lsn,
  confirmed_flush_lsn,
  pg_size_pretty(
    pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)
  ) AS approx_wal_retained
FROM pg_replication_slots
WHERE slot_name = 'ds_orders_lab_slot';

-- CHỈ ĐỌC tổng số rows của bảng lab.
SELECT
  COUNT(*) AS current_rows,
  MAX(updated_at) AS latest_source_update
FROM public.orders_cdc_lab;
~~~

**Hai dữ kiện khác nhau:** logical slot có thể giữ WAL kể cả khi **không có business requests**; ngược lại business updates nhiều không tự cho biết bytes WAL bị giữ là bao nhiêu. Kiểm tra **Cloud SQL disk usage/free space**, logs và replication slot đồng thời. Nếu disk gần đầy vì slot inactive, cần liên hệ DBA/on-call và thực hiện recovery plan; **không tự drop slot** để giải phóng disk vì làm mất khả năng tiếp tục CDC từ vị trí cũ.

### 11.4. Alerts mẫu (chỉ là SLO lab)

| Điều kiện | Ngưỡng minh họa | Phản ứng |
|---|---|---|
| Stream không RUNNING | > 5 phút ngoài maintenance | Kiểm tra lỗi và owner |
| Total latency | > 5 phút trong 10 phút | Phân loại source vs destination |
| Backfill object FAILED | Bất kỳ object thuộc lab | Kiểm tra quyền/type/PK |
| Unsupported events | > 0 ở nguồn quan trọng | Tạm dừng DDL, điều tra schema |
| WAL retained bytes | Tăng liên tục theo tải, vượt ngưỡng do DBA đặt | Chẩn đoán slot, backlog, disk |
| Cloud SQL disk available | Dưới headroom được duyệt | Escalate sớm để tránh outage |
| BigQuery query failures | Tăng sau schema change | Kiểm tra mapping/destination permissions |

**Không lấy ngưỡng 5 phút thành SLA mặc định của Datastream.** SLO phải do nghiệp vụ định nghĩa: báo cáo rủi ro có thể cần 30 giây, phân tích tài chính có thể chấp nhận 15 phút và đòi tính chính xác sau reconciliation.

## 12. IAM, an toàn dữ liệu và quản trị chi phí

### 12.1. Phân quyền nhiều lớp

| Thành phần | Principal/quyền | Cảnh báo |
|---|---|---|
| **Database source** | PostgreSQL user LOGIN REPLICATION + SELECT/USAGE theo phạm vi | Không dùng postgres superuser làm kết nối thường ngày |
| **Datastream control plane** | Người vận hành có quyền create/update/validate stream/profiles | Không gán Editor toàn project khi không cần |
| **Datastream service agent** | Quyền BigQuery Storage Write/đích GCS theo scope | Là identity nền tảng, không cấp vai trò serviceAgent cho developer |
| **BigQuery dataset** | BI consumer/analyst được phép đọc | Analytics không đồng nghĩa quyền đọc PII gốc |
| **Cloud Storage** | Bucket IAM và encryption/lifecycle | Không đặt allUsers, không tạo public bucket |
| **KMS/network** | Cấu hình CMEK, peering/PSC, TLS và firewall theo chính sách | Thêm người quản trị mạng/KMS khi cần |
| **Audit** | Cloud Audit Logs, stream change records | Tránh ghi secrets/password vào logs |

**CDC có thể sao chép một cột PII ngay khi cột đó xuất hiện.** Điều này tạo bản sao dữ liệu phải được bảo vệ như source, không phải dữ liệu analytics “đã ẩn danh”. Dùng include/exclude objects/columns theo khả năng nguồn, restricted datasets, encryption và retention chính xác. Với dữ liệu nhạy cảm, thiết kế masking/tokenization riêng trong pipeline trước khi cho BI sử dụng.

### 12.2. Nhiều project hoặc mạng riêng

Nếu stream ở **project A**, source ở **project B** và BigQuery destination ở **project C**, cần ba nhóm approvals:

1. Source DB user và network path từ Datastream tới source, bao gồm Cloud SQL/VPC/Firewall/SSL.
2. Datastream service agent của stream project có quyền tương ứng trên destination project/dataset/bucket.
3. Người tạo/chạy/giám sát stream có quyền trên **project A** và quyền đọc metrics/logs cần thiết.

**Không suy từ việc operator có project Owner ở A rằng service agent đã có quyền ghi BigQuery ở C.** Kiểm tra identity thực tế và cross-project IAM.

### 12.3. Các loại phí cần ước lượng

| Phí | Điều gì ảnh hưởng? | Biện pháp |
|---|---|---|
| **Datastream** | Dung lượng dữ liệu được xử lý/chuyển tới đích, gồm backfill và CDC theo SKU | Chọn table/column cần thiết, tránh restart/backfill vô ích |
| **Cloud SQL/nguồn** | I/O backfill, WAL storage, CPU/replication overhead | Giới hạn tải, đo disk/headroom |
| **BigQuery CDC** | Storage Write/API và background merges theo pricing/reservation | Chọn Merge/Append có mục tiêu, tuning max_staleness, reservations khi phù hợp |
| **BigQuery query/storage** | Data retention, queries, BI/ML jobs | Partition/cluster, quota/cost dashboards |
| **Cloud Storage** | File size, số objects, storage, operations | Format/flush/lifecycle phù hợp |
| **Dataflow** | Worker compute, streaming time, shuffle/storage | Autoscaling và kiểm soát pipeline |
| **Network/KMS/Monitoring** | Egress, encryption, logs và metrics | Chọn region/topology và retention |

**Datastream và BigQuery tính phí riêng.** Với **BigQuery Merge**, CDC background apply cũng có thể tốn compute; **max_staleness** là đánh đổi giữa tính mới và chi phí/độ trễ truy vấn, không phải nút làm “miễn phí merge”. Không tối ưu chi phí bằng cách giữ WAL vô hạn hoặc tắt backups/observability.

### 12.4. Bài toán ước tính lưu lượng

Giả sử **200.000 rows** được backfill, mỗi row trung bình **1 KiB** dữ liệu được nhân bản:

\[
200.000 \times 1\ \mathrm{KiB}
\approx 195{,}3\ \mathrm{MiB}
\]

Nếu CDC tiếp tục ghi **50.000 thay đổi/ngày × 0,5 KiB/change**, tương đương khoảng **24,4 MiB/ngày**, chưa tính event metadata, overhead, retries, backfill read amplification, BigQuery merge/query costs. **Không nhân trực tiếp dung lượng bảng PostgreSQL với đơn giá Datastream** rồi coi là hóa đơn chính xác: giá tính theo dữ liệu được Datastream xử lý/phân loại SKU, khác dữ liệu nén trên disk.

## 13. Runbook xử lý sự cố và phục hồi

### 13.1. Chẩn đoán theo lớp

~~~mermaid
flowchart TD
    A["Dashboard: freshness hoặc errors tăng"] --> B{"Stream còn RUNNING?"}
    B -->|"Không"| C["Xem errors / connection profiles"]
    B -->|"Có"| D{"Data freshness cao?"}
    D -->|"Có"| E["Kiểm tra source WAL/slot, network, load"]
    D -->|"Không"| F{"System latency cao?"}
    F -->|"Có"| G["Kiểm tra BigQuery/GCS destination, quota/IAM"]
    F -->|"Không"| H["Kiểm tra BigQuery merge staleness và data correctness"]
    E --> R["Sửa root cause, xác minh catch-up"]
    G --> R
    C --> R
    H --> R
    R --> I["Đối soát source-destination, sign-off"]
~~~

### 13.2. Bảng lỗi thường gặp

| Lỗi/triệu chứng | Khả năng | Khắc phục có kiểm soát |
|---|---|---|
| Validate source connection failed | Sai host/port/password, firewall/PSC/peering | Kiểm tra connection profile, network routes, TLS |
| PostgreSQL permission denied | User thiếu REPLICATION/SELECT/USAGE | Cấp đúng phạm vi database/slot/table |
| Publication hoặc slot not found | Tên sai hoặc tạo ở database khác | Kiểm tra PostgreSQL database/pg_replication_slots |
| WAL tăng không ngừng | Slot inactive, Datastream bị pause/lỗi, long transactions | Kiểm tra slot, source disk, recovery plan với DBA |
| Backfill very slow | Bảng lớn, nguồn thiếu I/O, source throttling | Điều chỉnh load/window, theo dõi object status |
| Source data freshness cao | WAL tạo nhanh hơn tốc độ đọc, mạng chậm | Phân tách high-volume tables vào streams riêng khi phù hợp |
| System latency cao | Destination quota/permissions, write lag | BigQuery/GCS logs, IAM, service status |
| BigQuery table count > source | Table không có PK hoặc Append-only | Phân biệt event history và current state |
| Merge không cập nhật DELETE | Sai PK/replica identity/CDC lag | Kiểm tra source setup, stream metadata và apply lag |
| Schema changed, events fail | Drop/rename/type change không tương thích | Dừng DDL, migration plan, rebackfill có phê duyệt |
| Unsupported events tăng | Kiểu dữ liệu không hỗ trợ, lỗi decode | Khoanh vùng bảng/cột theo tài liệu nguồn |
| Quota exceeded / 429 | BigQuery API capacity/stream limits | Rate, reservation, quota ticket, backoff |
| Replication resume nhưng thiếu rows | WAL đã bị xóa, source position không còn | Recover/recreate stream và backfill theo runbook; đối soát |
| Source + destination cùng region vẫn lag | Lag có nhiều lớp và load | Xem full pipeline, không chỉ network latency |

### 13.3. Khi bị ngừng stream quá lâu

1. **Không vội xóa stream hay slot.** Ghi thời điểm outage, trạng thái slot và vị trí WAL.
2. DBA kiểm tra **disk headroom** và **log retention** trên source, ưu tiên ngăn outage database.
3. Xác định có thể **resume/recover từ vị trí còn WAL** hay phải tạo slot/stream mới và **backfill lại**.
4. Nếu thay slot, tính **khoảng thời gian mất coverage** và dữ liệu phải đối soát; không tuyên bố recovery thành công chỉ vì stream RUNNING.
5. Trong BigQuery/GCS, xử lý duplicate events và so trạng thái cuối bằng PK.
6. Kiểm tra các hàng bị DELETE và các bảng có DDL trong giai đoạn outage.
7. Chỉ khi data correctness đạt, mới đóng incident và cập nhật change record.

**Không được drop PostgreSQL replication slot đang được stream sử dụng** để chữa lỗi full disk một cách thủ công; thao tác đó có thể phá continuity của CDC. Nếu buộc phải thực hiện để cứu database, cần quyết định của DBA/on-call và kế hoạch **reseed/rebackfill** sau đó.

### 13.4. Pause, resume và thay đổi cấu hình

- **Pause** khiến stream đi qua giai đoạn draining rồi paused; **nguồn vẫn có thể phát sinh WAL/binlog** trong thời gian dừng.
- **Resume** có thể bắt lại từ vị trí hợp lệ nếu logs còn; không có bảo đảm vượt được giới hạn retention.
- Thay object filters, connection profiles, write mode, schema hoặc destination có thể cần xác minh lại backfill, quyền và contract downstream.
- Trước maintenance DB major upgrade/PK changes, phải lập kế hoạch theo hướng dẫn engine-specific; PostgreSQL major upgrade có thể cần slot mới/recovery.
- Khi cần đổi cấu hình đang production, dùng canary/staging hoặc stream riêng có kế hoạch đối soát và cutover.

## 14. Case study: cập nhật analytics đơn hàng từ ứng dụng Java

### 14.1. Bối cảnh

Một công ty thương mại điện tử dùng **Cloud Run Java/Spring Boot → Cloud SQL PostgreSQL** cho giao dịch. Đội phân tích muốn theo dõi đơn hàng theo trạng thái trong BigQuery, trong khi dịch vụ nghiệp vụ vẫn phải ưu tiên latency thấp và tính nhất quán của giao dịch.

**Mục tiêu:** dữ liệu phân tích cập nhật với **total latency p95 dưới 3 phút** trong điều kiện bình thường, không làm database nguồn thiếu WAL/disk, và xử lý đúng các trường hợp hoàn tiền, hủy đơn và sửa giá.

~~~mermaid
flowchart LR
    APP["Java Orders API"] --> PG[("Cloud SQL PostgreSQL\nOLTP")]
    PG --> WAL["Logical WAL + publication"]
    WAL --> DS["Datastream\norders-main stream"]
    DS --> BQ["BigQuery Merge\ncurrent orders"]
    BQ --> DASH["Near-real-time dashboards"]
    PG --> OUTBOX["Order events / outbox"]
    OUTBOX --> OTHER["Business events for services"]
    MON["SRE alerts\nfreshness, WAL, merge"] -. "Giám sát" .-> DS
    MON -. "Disk / slot" .-> PG
~~~

**Thiết kế:**

- **Source:** publication chỉ gồm **public.orders** và những bảng thật sự cần phân tích; user replication riêng.
- **BigQuery:** Merge cho bảng có PK; bảng append-only riêng chỉ khi thực sự cần lịch sử event.
- **Network:** private connectivity và IAM cross-project được review.
- **Backfill:** chạy trước ở thời điểm ít tải, theo dõi I/O; CDC tiếp tục xử lý commits.
- **Consumer:** BI dùng bảng curated/view tách quyền, không đọc raw PII không cần thiết.
- **Observability:** alert latency, unsupported events, PostgreSQL disk/WAL, BigQuery CDC apply failures.
- **Governance:** thay schema theo expand/contract, có migration contract và rollback.

### 14.2. Sự cố giả định

Một job hậu kiểm cập nhật hàng triệu đơn trong **một transaction lớn**. Datastream PostgreSQL dùng một replication slot theo stream, vì vậy các bảng khác trong cùng stream cũng chậm theo. Dashboard báo data freshness tăng và Cloud SQL WAL chiếm thêm dung lượng.

**Không nên làm:** xóa slot để “khởi động lại từ đầu”, tăng Cloud Run max instances hoặc bỏ kiểm tra destination vì stream vẫn RUNNING.

**Cách xử lý:**

1. Kiểm tra transaction đang/chỉ vừa commit, PostgreSQL WAL disk và Datastream metrics.
2. Xác định nguồn chậm do một transaction/tables có write volume lớn.
3. Lập kế hoạch tách **high-churn tables** sang **stream riêng** với publication/slot riêng nếu tải ổn định cao; đánh giá tác động tới source trước khi nhân số slots.
4. Nếu ngừng CDC quá lâu, thực hiện recovery/backfill có đối soát thay vì kỳ vọng mọi WAL vẫn còn.
5. Chỉ đóng incident khi dữ liệu BigQuery khớp theo **primary keys, UPDATE/DELETE và time window**, không phải chỉ COUNT.

### 14.3. Tiêu chí nghiệm thu

| Điều kiện | Chứng cứ |
|---|---|
| Backfill đầy đủ | Tất cả objects trong phạm vi được xác nhận |
| CDC hoạt động | UPDATE/DELETE có kết quả đúng tại BigQuery |
| Freshness đạt SLO | Dashboard p95 và các alert hoạt động |
| Không gây outage nguồn | WAL/storage/CPU/connection headroom đạt |
| IAM tối thiểu | Source reader, service agent, BI consumer tách quyền |
| DDL được quản trị | Migration review và compatibility tests |
| Khôi phục được | Rebackfill/reconciliation runbook thử trên staging |
| Chi phí được theo dõi | Datastream + BigQuery CDC + Cloud SQL + Logging/Billing |

## 15. Bài tập vận dụng và đáp án

### 15.1. Bài A — Phân biệt batch và CDC

Ứng dụng thay đổi trạng thái đơn **NEW → PAID → CANCELLED**, có một bước **DELETE** theo yêu cầu lưu giữ dữ liệu.

**Câu hỏi:** vì sao SELECT WHERE updated_at > last_run có thể bỏ sót thay đổi?

**Đáp án định hướng:** nếu DELETE vật lý, row không còn để query; giao dịch có thể commit muộn với updated_at cũ, đồng hồ ứng dụng lệch hoặc status thay mà không cập nhật updated_at. WAL-based CDC đọc các thay đổi đã commit theo engine, nhưng phải kiểm tra publication/replica identity và khả năng log retention.

### 15.2. Bài B — Chuẩn bị PostgreSQL

Cho table **public.orders_cdc_lab** có PK và user **ds_orders_reader**.

**Yêu cầu:** liệt kê 5 điều kiện cần để Datastream đọc được CDC.

**Đáp án:** (1) logical decoding được bật; (2) publication đúng table; (3) replication slot dùng **pgoutput** và tên không trùng; (4) login/replication/SELECT/USAGE database role phù hợp; (5) network route/TLS/credential và stream config trỏ đúng database. Cần thêm **WAL disk monitoring** trước khi production hóa.

### 15.3. Bài C — Merge so với Append-only

Nguồn có 3 rows; trong cùng một khoảng thời gian thực hiện **1 INSERT**, **1 UPDATE** và **1 DELETE** trên các keys khác nhau.

**Câu hỏi:** cả hai đích đều có số hàng cuối cùng bằng nhau không?

**Đáp án:** không. **Merge** phản ánh trạng thái hiện tại khi catch-up: có thể vẫn 3 rows (insert thêm 1 và delete 1). **Append-only** lưu nhiều events và backfill records, có thể có nhiều hơn 3 rows; cần giải mã **CHANGE_TYPE**, metadata, dedup và ordering nếu muốn reconstruct state.

### 15.4. Bài D — Event đến sai thứ tự

Consumer nhận UPDATE với sequence **12**, sau đó INSERT với sequence **11** và nhận lại UPDATE **12** thêm lần nữa.

**Câu hỏi:** thuật toán “lấy event đến sau cùng” có an toàn không?

**Đáp án:** không. Cần xác định ordering key trong **Datastream metadata** phù hợp nguồn, deduplicate bằng event ID/UUID hoặc composite key, áp tombstone/DELETE đúng và có cơ chế kiểm tra trường hợp replay. Với BigQuery Merge, dùng CDC consolidation của nền tảng; với file Cloud Storage, consumer phải xử lý.

### 15.5. Bài E — Tính độ trễ

Một thay đổi được commit vào **10:00:00**, Datastream đọc vào **10:00:40**, và ghi tới destination vào **10:01:10**. Bỏ qua phần BigQuery apply/query-time.

\[
\text{Data freshness} \approx 40\ \mathrm{s}
\]

\[
\text{System latency} \approx 30\ \mathrm{s}
\]

\[
\text{Total latency} \approx 70\ \mathrm{s}
\]

**Câu hỏi:** nếu system latency giữ 30 giây nhưng data freshness tăng lên 8 phút, ưu tiên xem lớp nào?

**Đáp án:** source/WAL/replication slot/network source và nguồn phát sinh logs quá nhanh. Không mặc định đổ lỗi BigQuery nếu Datastream chưa đọc đến source changes.

### 15.6. Bài F — Vì sao WAL đầy ổ?

PostgreSQL có logical replication slot **ds_orders_lab_slot**, stream bị tạm dừng 2 ngày, database vẫn ghi nhiều giao dịch.

**Đáp án:** slot giữ WAL cần cho consumer; không thể dọn các segments chưa được xác nhận đọc. Điều tra disk, stream state, slot active, restart_lsn và log production; chỉ DBA với change approval mới quyết định resume/recover/drop/reseed. Không drop slot đang cần continuity chỉ để lấy dung lượng.

### 15.7. Bài G — Review schema evolution

Có đề xuất **đổi tên order_id**, **bỏ primary key** và **thay type của total_vnd** trong một lần migration khi stream đang chạy.

**Đáp án:** rủi ro rất cao: BigQuery Merge dựa trên PK; DDL rename/type change có thể gây dữ liệu sai hoặc mất events. Tách migration thành các bước tương thích, thử staging, định nghĩa downstream contract, backup và backfill/recovery plan, chỉ thực hiện khi chủ sở hữu dữ liệu ký duyệt.

### 15.8. Bài H — Ước tính và tối ưu chi phí

Nguồn có backfill **5 GiB**, sau đó mỗi ngày phát sinh **500 MiB** dữ liệu change được Datastream xử lý. Trong 30 ngày đầu, dung lượng nguồn minh họa trước overhead là:

\[
5\ \mathrm{GiB} + 30 \times 500\ \mathrm{MiB}
= 5\ \mathrm{GiB} + 14{,}65\ \mathrm{GiB}
\approx 19{,}65\ \mathrm{GiB}.
\]

**Câu hỏi:** có thể dùng con số này để khẳng định toàn bộ hóa đơn pipeline không?

**Đáp án:** không. Tính phí Datastream theo pricing/SKU của nguồn và lượng dữ liệu được xử lý; còn BigQuery CDC merges, queries, tables, Cloud SQL storage/compute, network, backups, Logging và Dataflow (nếu có) tính riêng. Đọc Cloud Billing report thay vì chỉ nhân một đơn giá tổng.

### 15.9. Bài I — Biên bản lab

~~~text
PROJECT_ID / STREAM_REGION / OWNER:
SOURCE_DB / ENGINE_VERSION / PRIMARY_KEY:
PUBLICATION / REPLICATION_SLOT / REPLICA_IDENTITY:
REPLICATION_USER / PERMISSIONS:
PRIVATE_CONNECTIVITY_OR_ALLOWLIST:
SOURCE_PROFILE / DESTINATION_PROFILE:
STREAM_ID / OBJECT_FILTER / BACKFILL_STATUS:
DESTINATION_BIGQUERY_DATASET / WRITE_MODE / MAX_STALENESS:
INSERT_CHECK / UPDATE_CHECK / DELETE_CHECK:
SOURCE_ROW_COUNT / DEST_ROW_COUNT / KEY_RECONCILIATION:
DATA_FRESHNESS / SYSTEM_LATENCY / TOTAL_LATENCY:
WAL_RETAINED / DISK_HEADROOM / UNSUPPORTED_EVENTS:
IAM / ENCRYPTION / RESIDENCY / RETENTION:
COST_BREAKDOWN / CHANGE_TICKET / CLEANUP:
OPEN_ISSUES:
~~~

Chỉ đánh dấu **PASS** khi có bằng chứng từ database, Datastream và BigQuery. Nếu không có project lab được cấp quyền, ghi **NOT_EXECUTED** và trình bày đúng các bước cần làm, không tự nhận replication đã thành công.

## 16. Dọn tài nguyên và bảo toàn dữ liệu

### 16.1. Checklist trước khi dọn

1. Xác minh **source/destination/stream** chỉ phục vụ lab và không có consumer khác.
2. Ngừng mọi producer writes vào **orders_cdc_lab**, chốt kết quả đối soát.
3. Kiểm tra stream objects đã hoàn tất và có dữ liệu cần archive hay không.
4. Khi được owner đồng ý, **pause/drain/delete đúng stream lab** trong Datastream Console.
5. Chỉ sau khi stream không còn sử dụng slot, DBA mới xem xét dọn **replication slot và publication**.
6. Sau đó mới xóa bảng PostgreSQL, BigQuery table/dataset và credentials riêng của lab.
7. Giữ audit records/logs/backups theo retention policy; tránh xóa dữ liệu dùng chung.

### 16.2. Kiểm tra trước thao tác xóa

~~~bash
# CHỈ ĐỌC, không tạo/xóa cloud resources.
gcloud datastream streams describe "$STREAM_ID" \
  --location="$REGION" --project="$PROJECT_ID"

gcloud datastream streams list \
  --location="$REGION" --project="$PROJECT_ID"

bq --project_id="$PROJECT_ID" ls "$PROJECT_ID:$BQ_DATASET"
~~~

~~~sql
-- CHỈ ĐỌC PostgreSQL trước khi DBA dọn slot:
SELECT slot_name, active, restart_lsn
FROM pg_replication_slots
WHERE slot_name = 'ds_orders_lab_slot';

SELECT pubname
FROM pg_publication
WHERE pubname = 'ds_orders_lab_pub';
~~~

**Không tự chạy pg_drop_replication_slot trên production.** Khi stream còn dùng slot, thao tác drop là phá continuity; khi bỏ hẳn stream mà quên slot, WAL vẫn có thể tích tụ. Cleanup phải đi theo đúng thứ tự và được DBA kiểm chứng.

### 16.3. Nếu cần lệnh xóa cho lab có phê duyệt

Sau khi **stream đã được xóa hẳn, các consumers đã dừng và slot chắc chắn inactive**, DBA có thể thực hiện các lệnh sau **trong database lab**, sau khi kiểm tra lại tên tài nguyên:

~~~sql
-- XÓA THẬT: chỉ DBA, chỉ database lab, cần owner approval.
SELECT pg_drop_replication_slot('ds_orders_lab_slot');
DROP PUBLICATION IF EXISTS ds_orders_lab_pub;

-- Chỉ khi bảng thuộc lab và không còn dữ liệu cần giữ:
DROP TABLE IF EXISTS public.orders_cdc_lab;
~~~

**Không xóa database instance, IAM/service agent hoặc BigQuery dataset dùng chung.** Muốn dọn BigQuery table, xác minh stream đã dừng/xóa trước để tránh tự tạo lại. Bucket Cloud Storage, Dataflow jobs và KMS keys (nếu có) có lifecycle/cleanup riêng.

## 17. Tài liệu chính thức và tổng kết

**Datastream:**

- [Datastream overview](https://docs.cloud.google.com/datastream/docs/overview)
- [Key concepts and behavior](https://docs.cloud.google.com/datastream/docs/behavior-overview)
- [Events and streams](https://docs.cloud.google.com/datastream/docs/events-and-streams)
- [Sources](https://docs.cloud.google.com/datastream/docs/sources)
- [Destinations](https://docs.cloud.google.com/datastream/docs/destinations)
- [Configure Cloud SQL for PostgreSQL for CDC](https://docs.cloud.google.com/datastream/docs/configure-cloudsql-psql)
- [PostgreSQL source behavior and limitations](https://docs.cloud.google.com/datastream/docs/sources-postgresql)
- [Configure a BigQuery destination](https://docs.cloud.google.com/datastream/docs/configure-bigquery-destination)
- [BigQuery destination behavior and metadata](https://docs.cloud.google.com/datastream/docs/destination-bigquery)
- [Configure a Cloud Storage destination](https://docs.cloud.google.com/datastream/docs/destination-gcs)
- [Create a stream](https://docs.cloud.google.com/datastream/docs/create-a-stream)
- [Manage streams](https://docs.cloud.google.com/datastream/docs/manage-streams)
- [Monitor a stream](https://docs.cloud.google.com/datastream/docs/monitor-a-stream)
- [Diagnose issues](https://docs.cloud.google.com/datastream/docs/diagnose-issues)
- [General best practices](https://docs.cloud.google.com/datastream/docs/best-practices-general)
- [Datastream pricing](https://cloud.google.com/datastream/pricing)

**Liên quan:**

- [BigQuery change data capture](https://docs.cloud.google.com/bigquery/docs/change-data-capture)
- [Cloud SQL for PostgreSQL](https://docs.cloud.google.com/sql/docs/postgres)
- [Dataflow overview](https://docs.cloud.google.com/dataflow/docs/overview)
- [Cloud Monitoring metrics for Datastream](https://docs.cloud.google.com/monitoring/api/metrics_gcp_d_h)

**Ghi nhớ:** CDC là **dòng thay đổi** chứ không tự là **sự kiện nghiệp vụ**. Datastream giảm công việc vận hành pipeline, nhưng **không bảo đảm event tới đích đúng một lần hay theo đúng thứ tự**, và **không thể phục hồi WAL đã hết hạn chỉ bằng resume**. Thiết kế có **primary key/replica identity**, metadata, observability, đối soát, source log retention và runbook là điều kiện để dữ liệu phân tích đáng tin cậy.

**Kết nối với lộ trình CLOUD_PROVIDERS_GCP:** bài học liên kết **Cloud SQL/AlloyDB, IAM, VPC/private connectivity, BigQuery, Cloud Storage, Dataflow, Cloud Monitoring và Cloud Billing**. Một pipeline production tốt không chỉ chuyển dữ liệu liên tục, mà còn phải **chính xác sau INSERT/UPDATE/DELETE, an toàn cho database nguồn, có thể khôi phục và có chi phí được kiểm soát**.










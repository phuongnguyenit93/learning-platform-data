# Keyspace/table không tồn tại và schema disagreement trong Apache Cassandra

> **Chương:** Xử lý sự cố  
> **Trọng tâm:** Phân biệt lỗi **keyspace/table thật sự chưa được tạo**, tên/namespace không khớp, quyền truy cập không đủ, Java Driver dùng metadata cũ, và **schema disagreement** giữa các node Cassandra. Hướng dẫn thực hành với CQL, `cqlsh`, `nodetool`, Java Driver 4.x và Java 17. Mọi ví dụ tạo/xóa schema chỉ được chạy trên **cluster lab hoặc namespace được cấp phép**. Với production, ưu tiên đọc trạng thái, chặn rollout và sửa theo quy trình migration.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích ý nghĩa của `Keyspace ... does not exist`, `unconfigured table`, `Undefined column name` và phân biệt chúng với `Unauthorized`, `Unavailable`, timeout.
2. Xác định keyspace/table đúng bằng **tên CQL đủ namespace**, quy tắc chữ hoa/thường và quoted identifiers.
3. Kiểm tra schema bằng `system_schema.keyspaces`, `system_schema.tables`, `system_schema.columns` và các lệnh `DESCRIBE` của `cqlsh`.
4. Phân biệt **DDL đã được coordinator chấp nhận** với **schema agreement**, metadata client đã refresh, và **dữ liệu thật sự phục vụ được tại CL mong muốn**.
5. Đọc `system.local.schema_version`, thông tin peers và kết quả `nodetool describecluster` để phát hiện khác biệt schema version; nêu giới hạn của mỗi góc nhìn.
6. Khoanh vùng lỗi **một coordinator** so với lỗi đồng loạt, lỗi theo DC/rack/token và lỗi do deployment/application config.
7. Sử dụng đúng `CqlSession.checkSchemaAgreement()`, `ExecutionInfo.isSchemaInAgreement()` và `session.getMetadata()` trong Java Driver 4.x, không lạm dụng cache metadata.
8. Thiết kế migration theo **single writer, thứ tự DDL rõ, checkpoint và điều kiện retry**, tránh nhiều service pods cùng thay schema khi startup.
9. Viết integration test tạo keyspace/table, đợi agreement có deadline, chuẩn bị CQL, ghi–đọc theo CL và khẳng định dữ liệu đúng.
10. Xây dựng runbook GO/HOLD/STOP có bảo vệ dữ liệu, quyền RBAC, multi-DC, node DOWN và tình huống schema disagreement kéo dài.
11. Nhận diện trường hợp **không được dùng `DROP`/`TRUNCATE`/restart tất cả nodes** để “sửa nhanh”.
12. Thu thập bằng chứng đủ chi tiết để DBA/SRE xác minh và bàn giao mà không rò rỉ credentials/PII.

**Ngữ cảnh dịch vụ `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`:** Cassandra là wide-column database phân tán; partition key dẫn tới token/natural replicas, keyspace xác định replication strategy và RF, CL quyết định mức phản hồi đọc/ghi. Schema quyết định **cách giải nghĩa CQL** nhưng bản thân schema agreement **không thay thế repair, compaction, phục hồi dữ liệu hay kiểm thử CL**. Ví dụ Java tập trung vào Java Driver 4.x, không thay đổi dữ liệu production.

## 2. Hai nhóm sự cố phải phân biệt ngay

**Nhóm A — Đối tượng không được nhận diện:** Coordinator từ chối CQL vì keyspace/table/column/type/index/function được tham chiếu không tồn tại trong **schema mà node đó hiện thấy**, hoặc client gửi tên sai.

**Nhóm B — Schema disagreement:** Các Cassandra nodes không cùng nhìn một phiên bản schema tại một thời điểm, thường trong giai đoạn migration/DDL propagation, node chưa hội tụ hoặc có lỗi network/topology/schema processing. Một node có thể biết table mới, node khác chưa biết.

~~~text
                    Java application / cqlsh
                               |
                         Query tới node X
                               |
                   X phân giải keyspace/table?
                       /                 \
                     KHÔNG                CÓ
                       |                   |
            unconfigured / does not       Kiểm schema definition
                       |                    |
          +------------+----------+         v
          |                       |   Coordinator xử lý CQL
    Object không có         Một số node           |
    trên toàn cluster       biết, số khác         v
          |                 chưa biết      CL/replicas/data path
          v                       |         (có thể lỗi riêng)
    Sai migration,              Schema
    namespace, name             disagreement
~~~

**Điểm quan trọng:** `InvalidQueryException: unconfigured table` không tự chứng minh toàn cluster chưa có table. Nó chứng minh **coordinator trả lỗi đã không phân giải được đối tượng theo request/namespace của nó**. Phải kiểm keyspace, tên và schema view của **các node liên quan**.

### 2.1. Một lỗi giống nhau, nhiều nguyên nhân

| Triệu chứng | Nguyên nhân khả dĩ | Cách phân biệt |
|---|---|---|
| `Keyspace 'orders' does not exist` | Chưa chạy migration, sai cluster, sai tên hoa/thường | Liệt kê `system_schema.keyspaces` và cluster/DC |
| `unconfigured table orders_by_id` | Table chưa tạo, sai current keyspace, một node schema cũ | Dùng fully qualified name, đọc `system_schema.tables` ở nhiều nodes |
| `Undefined column name status` | Migration ALTER chưa lan, Java code ahead of schema, tên column sai | `system_schema.columns`, app version, DDL history |
| Query chạy cqlsh nhưng lỗi ở Java | Khác cluster/keyspace/role/DC, driver cached metadata, prepared schema mismatch | So contact points, `withKeyspace`, auth, query string, coordinator |
| Lỗi chỉ xảy ra sau deploy mới | Startup race giữa migration và app traffic | Kiểm DDL completion, schema agreement và readiness gate |
| Một số requests PASS, một số FAIL | Coordinators khác schema view, routing/caches, mixed DC | Group lỗi theo coordinator/DC và schema_version |
| `SELECT` thành công nhưng trả 0 rows | Table tồn tại nhưng dữ liệu/CL/partition khác | Data oracle, PK/RF/CL, không gọi schema disagreement |
| `Unauthorized` | Role không đủ `SELECT`/`CREATE`/`ALTER` | RBAC, không coi là “table missing” |

### 2.2. Ba câu hỏi định hướng trước khi sửa

1. **Đúng đích chưa?** Cluster, environment, contact points, local DC, keyspace, table, role và phiên bản app có đúng không?
2. **Mọi node thấy cùng schema chưa?** So schema versions/metadata từ những vantage points phù hợp, có node DOWN hoặc network partition không?
3. **Dữ liệu đã sẵn sàng chưa?** Sau khi schema đúng, read/write tại CL yêu cầu với expected key/value có thành công không?

Chỉ cần trả lời ba câu này rõ ràng đã tránh được phần lớn “sửa lỗi” nguy hiểm như chạy `DROP TABLE` rồi tạo lại chỉ vì một ứng dụng thấy `unconfigured table`.

## 3. Keyspace, table, schema và data là các tầng khác nhau

### 3.1. Keyspace quyết định namespace và replication

~~~sql
CREATE KEYSPACE IF NOT EXISTS catalog_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};
~~~

Ví dụ chỉ dành **single-node lab**. Keyspace có:

- Tên namespace được tham chiếu qua `catalog_lab.orders_by_id`.
- Replication strategy và RF; production đa DC thường dùng `NetworkTopologyStrategy`.
- Metadata của types, tables, materialized views và các định nghĩa liên quan.

Tạo keyspace không tự tạo table. Thay RF không tự chứng minh historical data đã được phân phối tới replicas mới. Schema agreement không phải repair.

### 3.2. Table định nghĩa cột và primary key

~~~sql
CREATE TABLE IF NOT EXISTS catalog_lab.orders_by_id (
  tenant_id text,
  order_id uuid,
  status text,
  revision int,
  PRIMARY KEY ((tenant_id), order_id)
);
~~~

`PRIMARY KEY ((tenant_id), order_id)` nghĩa `tenant_id` là partition key và `order_id` là clustering key. Một SELECT chỉ theo `order_id` không trở thành hợp lệ vì table tồn tại; Cassandra query model và primary-key restrictions vẫn áp dụng.

### 3.3. Ba trạng thái có thể khác nhau

~~~text
DDL committed/acknowledged?
         |
         v
Schema agreed among currently UP nodes?
         |
         v
Data migrated/restored/repaired and query at CL succeeds?
~~~

Ví dụ sau khi tạo một bảng rỗng, tất cả node có thể **schema-agreed** ngay, nhưng API kỳ vọng 10 triệu historical rows sẽ trả rỗng. Đây là **data migration/recovery problem**, không phải `schema disagreement`. Ngược lại, dữ liệu SSTables có thể còn trên disk trong khi schema không thấy table; tuyệt đối không tự tháo lắp SSTables để chữa sai metadata khi chưa có runbook backup/restore.

## 4. Tên CQL: keyspace mặc định, fully qualified và quoted identifiers

### 4.1. `USE` trong cqlsh là session context, không phải migration

~~~sql
USE catalog_lab;
SELECT status FROM orders_by_id
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Nếu chưa chọn `USE catalog_lab` hoặc session thuộc keyspace khác, `orders_by_id` có thể được phân giải ở namespace sai. Cách an toàn khi chẩn đoán:

~~~sql
SELECT status FROM catalog_lab.orders_by_id
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

**Khi viết Java Driver 4.x**, ưu tiên **fully qualified CQL** cho migrations/probes hoặc cấu hình keyspace rõ ràng bằng builder/session configuration. Tránh phát `USE` tự phát từ application pods cùng dùng connection pooling; khái niệm session context của cqlsh và driver management không giống nhau.

### 4.2. Identifiers không quote được chuẩn hóa

~~~sql
CREATE TABLE catalog_lab.OrderEvents (
  tenant_id text PRIMARY KEY,
  status text
);
~~~

Tên unquoted `OrderEvents` được chuẩn hóa thành `orderevents`. Vì vậy:

~~~sql
SELECT status FROM catalog_lab.orderevents
WHERE tenant_id = 'tenant-a';
~~~

tham chiếu đúng table. Nhưng:

~~~sql
SELECT status FROM catalog_lab."OrderEvents"
WHERE tenant_id = 'tenant-a';
~~~

tham chiếu table **phân biệt hoa/thường** có tên thực `OrderEvents`, không phải `orderevents`, và có thể báo unconfigured table.

### 4.3. Quoted names bảo toàn chữ hoa và ký tự đặc biệt

~~~sql
CREATE TABLE catalog_lab."OrderEvents" (
  "TenantId" text PRIMARY KEY,
  status text
);

SELECT status FROM catalog_lab."OrderEvents"
WHERE "TenantId" = 'tenant-a';
~~~

Với quoted identifiers, tên và case phải khớp chính xác ở **mọi** CQL/driver call. Dùng `CqlIdentifier.fromCql`/`fromInternal` phù hợp khi lookup Java metadata; không tự `toLowerCase()` tên đã quote rồi mong ra đúng table.

**Khuyến nghị:** Dùng tên lower_snake_case không quote ở schema mới để tránh lỗi và query builder phức tạp, trừ khi có lý do tương thích rõ ràng.

### 4.4. Keyspace hiện tại, keyspace lạ, cluster lạ

~~~text
staging cluster:
  catalog_lab.orders_by_id exists

production cluster:
  catalog_lab.orders_by_id absent

Application config:
  contact_points = production
  expected_keyspace = catalog_lab

Result:
  unconfigured table
~~~

Đây **không phải schema disagreement** của staging/prod; hai cluster độc lập có những schema khác nhau. So `cluster_name`, contact points, DC, credentials và deployment target trước khi chạm schema.

## 5. Schema trong Cassandra lan truyền như thế nào?

### 5.1. Không có “một master SQL schema” để sửa trực tiếp

Cassandra là hệ phân tán ngang hàng; mỗi node duy trì **schema metadata cục bộ** và trao đổi thông tin phiên bản/định nghĩa schema với các peers. CQL DDL có thể được gửi tới một coordinator bất kỳ có quyền xử lý yêu cầu, rồi schema được lan truyền để các nodes còn lại tiến tới agreement.

~~~text
                 Deployment / migration runner
                              |
                       CREATE TABLE
                              |
                              v
                      Coordinator A
                              |
                   Apply local schema change
                              |
                   Gossip/schema propagation
                         /            \
                        v              v
                     Node B          Node C
                     update          delayed
                        |              |
                  schema_version   old_version
                        \              /
                         \            /
                  SCHEMA DISAGREEMENT
                              |
                      C receives updates
                              |
                    SCHEMA AGREEMENT
~~~

Thông thường đây là **trạng thái chuyển tiếp** sau DDL; không phải mọi giây schema versions khác nhau đều là outage. Tuy vậy, nếu sau **ngân sách chờ** đã định vẫn khác, hoặc một số queries liên tục báo `unconfigured table`, đó là sự cố cần điều tra.

### 5.2. Schema version đại diện cho điều gì?

Node có một `schema_version` phản ánh schema view của nó. Khi các **nodes đang hoạt động** cùng công bố một schema version, đây là tín hiệu mạnh cho thấy schema metadata đã hội tụ. Nhưng:

- Không phải phiên bản Java Driver, Cassandra binary hay phiên bản migration file.
- Không phải commit ID của Git hoặc số lần DDL.
- Không phải checksum chứng minh từng SSTable/data row giống nhau.
- Không bảo đảm node **DOWN** đã nhận schema mới.
- Không chứng minh app đang kết nối **đúng cluster**.

**Không** sửa trực tiếp `system.local.schema_version` hay system schema tables để “làm UUID giống nhau”. Chúng do Cassandra quản lý; thao tác thủ công có thể phá metadata và khiến cứu hộ khó hơn.

### 5.3. Coordinator xử lý request trong cửa sổ chưa hội tụ

Giả sử A/B/C cùng cluster, vừa tạo `catalog_lab.orders_by_id`:

~~~text
T0    DDL sent to A
T1    A knows new table; B,C may not
T2    SELECT via A --> can resolve table
T3    SELECT via C --> unconfigured table
T4    B,C receive schema updates
T5    agreement reached
T6    SELECT via A/B/C --> schema resolution consistent
~~~

Mốc chỉ mang tính khái niệm, không phải contract “tất cả nodes đồng bộ trong X ms”. Trong một số thiết kế, driver sẽ **chờ agreement trong ngân sách** sau schema-changing request; điều này làm giảm race nhưng không bảo đảm mọi failure mode được loại trừ.

### 5.4. Node DOWN và góc nhìn agreement

~~~text
Node A UP  schema V2
Node B UP  schema V2
Node C DOWN (last known V1)

UP-node schema agreement: có thể PASS
All-nodes-ready-to-serve-new-schema: CHƯA PASS
~~~

Sau khi C quay lại, cần kiểm nó tiếp nhận schema mới và hoạt động đúng trước khi quảng bá toàn cluster ready. Nếu read/write CL vẫn phục vụ nhờ A+B, dịch vụ có thể đủ quorum, nhưng **bước kế tiếp của rolling restart** phải có gate riêng để tránh mất thêm replica.

## 6. Schema agreement khác những trạng thái nào?

| Trạng thái | Tín hiệu | Không bảo đảm |
|---|---|---|
| Process ready | Node JVM/container chạy | CQL mở; schema/data đủ |
| Native transport ready | Port `9042`/auth/handshake hoạt động | Table của app tồn tại |
| DDL request accepted | Coordinator hoàn tất lệnh DDL | Các UP nodes đã hội tụ |
| **Schema agreement** | Các UP nodes có schema version giống | Down nodes updated, historical data synced |
| Driver schema metadata updated | Client thấy keyspace/table mới | Mọi coordinator đều đã update |
| Keyspace/table queryable | Coordinator phân giải CQL | Replica đủ CL, row mong đợi tồn tại |
| Data available at CL | CQL read/write đạt CL | Dữ liệu migrate/restore hoàn chỉnh |
| Business readiness | CQL đạt CL, expected value/version và SLO | Mọi partition trên cluster được bao phủ nếu chỉ probe một key |

### 6.1. Vì sao `CREATE TABLE IF NOT EXISTS` không phải bằng chứng đúng schema?

~~~sql
CREATE TABLE IF NOT EXISTS catalog_lab.orders_by_id (
  tenant_id text,
  order_id uuid,
  status text,
  revision int,
  PRIMARY KEY ((tenant_id), order_id)
);
~~~

Nếu table đã tồn tại nhưng **khác định nghĩa** (ví dụ thiếu `revision` hoặc primary key khác), `IF NOT EXISTS` có thể khiến DDL không lỗi, **không kiểm** schema hiện hữu khớp DDL mong đợi. Sau migration, cần đọc `system_schema.columns`/driver metadata và chạy probe CQL theo contract.

### 6.2. Agreement không thay repair

Thay RF của keyspace từ 2 lên 3 có thể làm schema agreement đạt sớm, nhưng không có nghĩa dữ liệu lịch sử đã nằm đủ trên replica mới. Cần **repair/streaming và data verification** theo phiên bản/operational runbook. Tương tự, khôi phục snapshot có thể có schema hoàn toàn thống nhất nhưng thiếu một phần SSTables.

### 6.3. Agreement không biến lỗi sai CQL thành đúng

~~~sql
SELECT amount
FROM catalog_lab.orders_by_id
WHERE tenant_id = 'tenant-a';
~~~

Nếu table không có cột `amount`, request sẽ tiếp tục báo `Undefined column` cho dù toàn bộ nodes schema-agreed. **Không lặp lại retry vô hạn** cho lỗi permanent như sai cột, sai table name, thiếu permission hoặc query không có partition key.

## 7. Nguyên nhân phổ biến: migration, cấu hình, network và node

### 7.1. Application triển khai trước migration

~~~text
Release v2 Java expects column revision
                  |
                  v
Traffic shifted to v2
                  |
Migration ALTER TABLE ADD revision chưa chạy
                  |
            Undefined column
~~~

**Cách phòng:** Migration là một bước deployment có owner; chờ DDL/gate trước traffic, dùng schema changes tương thích ngược với binary cũ và mới.

### 7.2. Nhiều app pods đồng thời chạy DDL khi startup

~~~text
Pod A --- CREATE TABLE ----------> Coordinator X
Pod B --- ALTER TABLE ADD col ---> Coordinator Y
Pod C --- CREATE INDEX ----------> Coordinator Z
            |                       |
       Conflicting/overlapping schema modifications
            |
     Disagreement / validation errors / races
~~~

Cassandra schema changes là cluster operations, **không** phải một hoạt động transactional migration được cô lập cho mỗi pod. Chạy nhiều migration runners có thể phát sinh race, schema churn và retry storms. Dùng **single migration owner**, khóa/leader election đáng tin (thường ở deployment control plane), versioned migrations và gate kiểm schema + data.

### 7.3. Node DOWN, gossip/communication bị chia cắt

Khi một node không liên lạc được với peers trong giai đoạn DDL, nó có thể có schema version cũ. Sau phục hồi, Cassandra có thể hội tụ schema, nhưng nếu lỗi network persisted, sẽ có discrepancy kéo dài. Kiểm ring/gossip/network/tls internode và logs; **đừng restart cả cluster đồng loạt**.

### 7.4. Mixed Cassandra versions hoặc incompatible schema features

Khi rolling upgrade từ một phiên bản sang phiên bản khác, DDL sử dụng tính năng chỉ hỗ trợ ở phiên bản mới có thể khiến nodes cũ không thể hiểu/áp dụng đồng nhất. Ví dụ về types/indexes/compaction options cần kiểm release notes và upgrade compatibility của **đúng cặp phiên bản**; không tự coi một câu lệnh chạy trên node mới là an toàn cho cluster hỗn hợp.

### 7.5. Sai cluster, namespace hoặc quyền

Một pod dùng connection string của staging, một pod dùng production; một pod đặt `withKeyspace("catalog_lab")`, pod khác không đặt; hoặc session được dùng bằng tài khoản không có quyền đọc schema/user table. Các trường hợp này **có thể giống schema lỗi** nhưng không phải disagreement giữa nodes cùng cluster.

### 7.6. Driver metadata chậm hơn schema đã đổi

Java Driver 4.x duy trì local metadata snapshot, nhận schema-change events và refresh metadata theo cơ chế của driver. Ngay sau DDL, một snapshot **đã lấy trước đó** vẫn có thể cũ. Không dùng `Metadata oldMetadata = session.getMetadata()` rồi poll **cùng object** mãi. Lấy snapshot mới sau khi agreement/refresh đã xảy ra; phân biệt client metadata stale với server rejection.

### 7.7. Cassandra gặp lỗi khi apply schema

Khả năng khác gồm lỗi disk/GC/CPU pressure, thread-pool backlog, invalid schema mutation, internode messaging problems, hạ tầng DNS/broadcast addresses hoặc sự cố implementation/version-specific. Khi schema disagreement tồn tại kéo dài, cần **log evidence theo timestamp, coordinator và peer**, không “sửa” bằng cách sửa bảng `system_schema` thủ công.

## 8. Sơ đồ chẩn đoán từ request lỗi

~~~text
       Application báo keyspace/table not found
                        |
           Confirm query, CL, cluster, DC, role
                        |
            Dùng fully qualified CQL?
                 /               \
                NO                YES
                |                  |
       Sửa namespace/case         |
                |                  v
          Kiểm từ cqlsh      Query chạy với admin nhưng
          cùng cluster/role?  service role không?
                               /        \
                              YES        NO
                               |          |
                         RBAC issue       v
                                   Inspect system_schema
                                            |
                               Object exists on coordinator?
                                 /                \
                                NO                YES
                                |                  |
                           Migration?        Wrong columns?
                           Wrong cluster?      /       \
                             |                YES       NO
                             v                 |         |
                      Compare schema       Schema     Driver
                      versions across     migration  metadata/
                      UP peer nodes       ordering   prepared/CL
                             |
                   Versions differ/stale?
                      /           \
                     YES          NO
                      |            |
               Hold schema        Investigate
               migration,        wrong query/
               gossip/logs        schema version
                      |
               Agreement & CQL probes PASS?
                      /             \
                    YES              NO
                     |                |
              Enable canary      HOLD/ESCALATE
              after data CL      do not DROP/
              correctness       TRUNCATE/repair blindly
~~~

**Tất cả nhánh bắt đầu bằng xác nhận đang ở đúng cluster/role.** Chỉ có quyền superuser chạy `cqlsh` không chứng minh role của Java service có thể chuẩn bị statement/read dữ liệu.

## 9. Bộ lệnh CQL chẩn đoán chỉ đọc

**Quy ước:** Trong production, ưu tiên đăng nhập bằng tài khoản read-only diagnostic có quyền cần thiết, không dùng secret trong command-line history. Khi một coordinator nghi bị stale, kết nối `cqlsh` **trực tiếp tới endpoint của node đó** (nếu networking/auth cho phép) rồi thực thi cùng một nhóm truy vấn. **Không** lấy một lần đọc từ một node làm đại diện mọi node.

### 9.1. Xác định cluster/DC/node đang phục vụ CQL

~~~sql
SELECT cluster_name, data_center, host_id,
       listen_address, native_protocol_version, release_version,
       schema_version
FROM system.local;
~~~

Tập columns của `system.local` có khác biệt theo phiên bản; nếu một column không có, dùng:

~~~sql
DESCRIBE TABLE system.local;
SELECT cluster_name, data_center, host_id, schema_version
FROM system.local;
~~~

**Không** dựa duy nhất vào `cluster_name`: có thể nhiều môi trường vô tình dùng cùng tên. So địa chỉ, DC, host IDs, cert/TLS identity và registry của deployment.

### 9.2. Liệt kê keyspaces hiện thấy

~~~sql
SELECT keyspace_name, durable_writes, replication
FROM system_schema.keyspaces;

SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'catalog_lab';
~~~

Nếu keyspace không có trên node này:

- Đảm bảo tên `catalog_lab` đúng case/quote.
- Xác nhận đây là cluster đích, không phải node ở môi trường khác.
- Kiểm migration log và schema versions trên peers.
- Nếu các nodes UP khác thấy keyspace, nghi schema chưa hội tụ.
- Không tự chạy `CREATE KEYSPACE` nếu môi trường production có migration owner; escalation/hold là lựa chọn an toàn.

### 9.3. Liệt kê tables và columns

~~~sql
SELECT keyspace_name, table_name
FROM system_schema.tables
WHERE keyspace_name = 'catalog_lab';

SELECT keyspace_name, table_name, column_name,
       kind, position, type
FROM system_schema.columns
WHERE keyspace_name = 'catalog_lab'
  AND table_name = 'orders_by_id';
~~~

So bảng thực với schema contract: primary-key columns, clustering order, kiểu UUID/text/int, tùy chọn table/index/view. Không chỉ kiểm tên table có tồn tại. Nếu CQL lỗi `Unknown identifier revision` nhưng `system_schema.columns` trên node đang chọn có `revision`, kiểm **coordinator mà Java thực sự gửi query** và DDL applied timeline.

### 9.4. Kiểm UDTs, indexes và views khi liên quan

~~~sql
SELECT keyspace_name, type_name
FROM system_schema.types
WHERE keyspace_name = 'catalog_lab';

SELECT keyspace_name, table_name, index_name, kind
FROM system_schema.indexes
WHERE keyspace_name = 'catalog_lab';

SELECT keyspace_name, view_name, base_table_name
FROM system_schema.views
WHERE keyspace_name = 'catalog_lab';
~~~

Cấu trúc metadata có khác biệt theo Cassandra version và feature support; nếu nghi issue với Storage-Attached Index/SAI, kiểm hệ plugin/version và schema của index đúng kiểu, không suy “table missing” chỉ vì index query không được hỗ trợ. Với materialized views, base-table schema agreement và view build/catch-up là **những bước khác nhau**.

### 9.5. `DESCRIBE` trong cqlsh

~~~text
cqlsh> DESCRIBE KEYSPACES;
cqlsh> DESCRIBE KEYSPACE catalog_lab;
cqlsh> DESCRIBE TABLE catalog_lab.orders_by_id;
cqlsh> DESCRIBE TABLES;
~~~

`DESCRIBE` là lệnh tiện ích của **cqlsh**, không phải statement CQL chuẩn dành cho mọi Java Driver `session.execute("DESCRIBE ...")`. Với Java, dùng driver metadata hoặc truy vấn `system_schema` phù hợp. Trong production, tránh paste toàn bộ schema ra ticket công khai nếu có dữ liệu nhạy cảm trong tên/annotations.

### 9.6. So schema versions của peers

~~~sql
SELECT schema_version FROM system.local;

-- Với các phiên bản có system.peers:
SELECT peer, data_center, host_id, schema_version
FROM system.peers;
~~~

Cassandra 4.x/5.x có bảng peer metadata mới `system.peers_v2` với cột địa chỉ/port và tập columns tùy version. Trước khi truy vấn, dùng `DESCRIBE TABLE system.peers_v2;` để biết field hiện có. **Không** giả định rằng một truy vấn `system.peers` ở mọi phiên bản luôn liệt kê mọi node hoặc phản ánh chính xác tức thời góc nhìn gossip: `system.peers`/`peers_v2` là **dữ liệu peer metadata được node lưu**, còn live agreement nên đối chiếu `nodetool describecluster`, driver và các node trực tiếp.

Nếu local `schema_version` của node A khác local schema version từ node B, đó là evidence of disagreement. Nếu peers metadata ở A còn stale nhưng các local versions A/B đã giống nhau, đừng tự kết luận Cassandra vẫn disagreement chỉ từ một bảng peer.

### 9.7. Read-only business probe sau khi schema được xác nhận

~~~sql
CONSISTENCY ONE;

SELECT status, revision
FROM catalog_lab.orders_by_id
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

`ONE` chỉ phù hợp RF1 lab. Trong production phải dùng **CL của ứng dụng** (ví dụ `LOCAL_QUORUM` trên NTS RF3) và so giá trị/phiên bản mong đợi. Một query không lỗi nhưng trả 0 rows không chứng minh data migration đã hoàn tất.

## 10. `nodetool` và quan sát topology/schema

### 10.1. Bộ lệnh ban đầu

~~~bash
nodetool status
nodetool describecluster
nodetool gossipinfo
nodetool tpstats
nodetool netstats
~~~

Các lệnh giúp trả lời những câu hỏi **khác nhau**:

| Lệnh | Điều quan sát | Giới hạn |
|---|---|---|
| `status` | Up/Down + Normal/Joining/Leaving/Moving, DC/rack, tokens | `UN` không bảo đảm schema agreement |
| `describecluster` | Cluster name, snitch, schema versions của nodes theo góc nhìn nodetool | Không chứng minh dữ liệu trên disk đúng |
| `gossipinfo` | Gossip endpoint states, trong đó có thông tin schema/state theo phiên bản | Có thể nhiều dòng; không tự quyết định một coordinator có query được |
| `tpstats` | Active/pending/dropped messages per executor | Backlog có thể làm schema/requests chậm |
| `netstats` | Streaming/network activity | Streaming xong không tự xác nhận data oracle |

`nodetool` cần JMX access và quyền vận hành; nếu không truy cập được JMX từ máy app, đây là giới hạn môi trường chứ **không** chứng minh Cassandra DOWN.

### 10.2. Cách đọc `describecluster`

Ví dụ **giả lập**:

~~~text
Cluster Information:
        Name: OrdersCluster
        Snitch: org.apache.cassandra.locator.GossipingPropertyFileSnitch
        ...
Schema versions:
        11111111-1111-1111-1111-111111111111:
          /10.1.0.11
          /10.1.0.12
        22222222-2222-2222-2222-222222222222:
          /10.1.0.13
~~~

Đây là **evidence of version disagreement** từ góc nhìn node chạy nodetool. Khi một node còn version cũ, xác định nó có phải coordinator gây lỗi `unconfigured table` hay không, xem logs/connectivity và chờ **bounded agreement** nếu vừa DDL. Không “chữa” bằng cách copy UUID schema version thủ công.

### 10.3. `UN` không đồng nghĩa schema đã hội tụ

~~~text
Status:
  A UN
  B UN
  C UN

Schema versions:
  A V2
  B V2
  C V1

=> Node state OK nhưng schema agreement FAIL
~~~

**Mặt khác**, tất cả UP nodes có cùng schema version không bảo đảm node DOWN sẽ biết table mới khi lên lại, và cũng không bảo đảm replicas ở CL `LOCAL_QUORUM` có dữ liệu mong đợi. Sơ đồ trạng thái/node health và schema/data readiness phải tách nhau.

### 10.4. Khi gặp node `UJ` hoặc `DN`

`UJ` nghĩa node đang Joining; `DN` nghĩa Down/Normal theo gossip. Một rollout/migration phải cân nhắc:

- Node `UJ` có thể chưa hoàn tất bootstrap/streaming và chưa sẵn sàng phục vụ token range mới.
- Node `DN` có thể chưa được cập nhật schema; agreement giữa UP nodes vẫn có thể PASS.
- Với RF3 và CL `LOCAL_QUORUM`, một replica DOWN có thể vẫn phục vụ nếu hai replicas còn lại khỏe, nhưng **không** nên khởi động rolling restart tiếp theo khi resilience margin đã thấp.
- Không chạy decommission/removenode/repair chỉ vì thấy schema version khác, trước khi xác định topology và runbook phù hợp.

### 10.5. Logging và time correlation

Thu log Cassandra quanh DDL:

~~~text
T0 UTC - migration runner starts
T1 UTC - CREATE/ALTER dispatched to coordinator
T2 UTC - DDL completion + schema agreement observation
T3 UTC - Java PREPARE/EXECUTE fails/succeeds
T4 UTC - nodetool describecluster snapshot
T5 UTC - CQL system.local.schema_version per node
~~~

Ưu tiên tìm events liên quan **schema migration, schema pull/push, dropped gossip/internode messages, write/read failures, node joining**, nhưng exact log strings/levels thay đổi theo Cassandra version. Không chỉ `grep "ERROR"`; nhiều lần schema change bình thường có log INFO và failure do routing/app namespace không hiện trong Cassandra error logs.

## 11. Phân loại exception Java để tránh xử lý nhầm

### 11.1. Ma trận lỗi

| Loại lỗi | Nguyên nhân thường gặp | Có retry tức thời không? |
|---|---|---|
| `InvalidQueryException` | Keyspace/table/column không tồn tại hoặc query không hợp lệ | **Không** mặc định; chỉ chờ có giới hạn khi biết migration đang hội tụ |
| `SyntaxError` | CQL syntax sai | **Không**; sửa CQL |
| `UnauthorizedException` | Role thiếu quyền | **Không**; sửa RBAC/role |
| `AlreadyExistsException` | `CREATE` object đã tồn tại | Không tự sửa; so schema mong đợi |
| `UnavailableException` | Không đủ live replicas để đạt CL | Xử lý RF/CL/topology, khác schema |
| `ReadTimeoutException`/`WriteTimeoutException` | ACK/read responses không đúng hạn | Cẩn trọng idempotence, unknown write outcome |
| `DriverTimeoutException` | Deadline client hết, có thể lúc chuẩn bị/gửi/đợi response | Không suy server chưa apply |
| `AllNodesFailedException` | Tập errors từ nhiều coordinators | Đọc `getAllErrors()`, không nuốt cause |
| `NoNodeAvailableException` | Không có coordinator usable | Kiểm local DC, connections, contact points |
| Codec/serialization error | Java bind type/mapping sai | Sửa driver/codec, không chạy migration mù |

`InvalidQueryException` có nhiều nguyên nhân ngoài missing table. Phải giữ **CQL query family, keyspace/table và message đã làm sạch dữ liệu**; tránh phân loại chỉ theo “có chữ table” trong một message localized/specific version.

### 11.2. Error categories khác nhau thì hành động khác nhau

~~~text
unconfigured table          -> Validate schema/namespace/DDL timeline
Unauthorized                -> Permissions and service role
Unavailable                 -> RF/replica liveness/CL
ReadTimeout                 -> Replica read path/time budgets
WriteTimeout                -> Unknown write outcome; reconcile
DriverTimeout               -> Driver queue/network/timeout, server unknown
NoNodeAvailable             -> Driver routing/connectivity/DC
Protocol/schema mismatch    -> Driver/server version/compatibility
~~~

**Không** bắt `Exception` rồi chạy `CREATE TABLE IF NOT EXISTS`; việc đó có thể che lỗi auth/routing, tạo table sai môi trường hoặc che schema mismatch hiện hữu.

### 11.3. Server error và driver error có thể được lồng

Java Driver có thể bọc failures nhiều coordinators trong `AllNodesFailedException`. Một lần PREPARE có thể thử các nodes khác nhau; cần in sanitized root causes theo node:

~~~java
import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.metadata.Node;
import java.util.List;
import java.util.Map;

static void logCoordinatorFailures(AllNodesFailedException failure) {
    for (Map.Entry<Node, List<Throwable>> e :
            failure.getAllErrors().entrySet()) {
        String coordinator = String.valueOf(e.getKey().getHostId());
        for (Throwable cause : e.getValue()) {
            System.err.printf(
                "coordinatorHostId=%s errorType=%s%n",
                coordinator, cause.getClass().getSimpleName());
        }
    }
}
~~~

Không đưa prepared statement **bind values**, username/password/token hoặc bản ghi customer vào log. Nếu cần theo dõi yêu cầu xuyên dịch vụ, dùng correlation ID/sanitized query family.

## 12. Java Driver 4.x: schema agreement và metadata đúng cách

### 12.1. `CqlSession` là client dài hạn, không tạo cho mỗi probe

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;

try (CqlSession session = CqlSession.builder()
        .addContactPoint(
            new InetSocketAddress("127.0.0.1", 9042))
        .withLocalDatacenter("datacenter1")
        .build()) {
    // Chỉ chạy với Cassandra single-node LAB.
    // Dùng full-qualified CQL, không trông chờ USE từ cqlsh.
}
~~~

Với ứng dụng production, `CqlSession` thường **được dùng lại xuyên suốt lifecycle**. Mở/đóng session liên tục khiến metadata refresh, connections, auth/TLS và prepared caches nóng/lạnh không cần thiết; nó còn làm schema diagnostics nhiễu thêm.

### 12.2. Chọn keyspace tường minh nếu không dùng fully qualified CQL

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;

CqlSession withKeyspace = CqlSession.builder()
    .addContactPoint(
        new InetSocketAddress("127.0.0.1", 9042))
    .withLocalDatacenter("datacenter1")
    .withKeyspace(CqlIdentifier.fromCql("catalog_lab"))
    .build();
~~~

`withKeyspace` giả định keyspace đã tồn tại khi tạo session. Khi ứng dụng khởi tạo *lần đầu* và migration chưa tạo keyspace, khởi tạo một session **không chỉ định keyspace** để chạy migration (trong lab/runner), sau đó tạo session ứng dụng với keyspace hoặc dùng CQL đủ namespace. Tránh tạo session ứng dụng trước migration rồi retry connection vô hạn mà không ghi rõ root cause.

### 12.3. Driver metadata là snapshot

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.metadata.Metadata;

Metadata snapshotBefore = session.getMetadata();

// DDL có thể xảy ra ở một migration runner khác.
// snapshotBefore không phải live view để giữ/poll mãi.

Metadata snapshotAfter = session.getMetadata();
boolean keyspaceKnown = snapshotAfter
    .getKeyspace(CqlIdentifier.fromCql("catalog_lab"))
    .isPresent();

System.out.println("Keyspace visible to driver=" + keyspaceKnown);
~~~

Nhìn thấy keyspace trong snapshot **không** bảo đảm table data sẵn sàng hoặc tất cả nodes agreement. Không thấy keyspace trong snapshot **cũng chưa đủ** kết luận Cassandra thiếu keyspace: metadata refresh có thể bị tắt/cấu hình delay, hoặc driver chưa nhận event. Đối chiếu CQL `system_schema` trực tiếp từ coordinator và trạng thái DDL.

### 12.4. Kiểm một table trong Metadata

~~~java
import java.util.Optional;

Optional<KeyspaceMetadata> ks = session.getMetadata()
    .getKeyspace(CqlIdentifier.fromCql("catalog_lab"));

boolean tableKnown = ks
    .flatMap(meta ->
        meta.getTable(CqlIdentifier.fromCql("orders_by_id")))
    .isPresent();

System.out.println("Table visible in driver metadata=" + tableKnown);
~~~

Nếu `tableKnown=false`:

1. Xác nhận driver có bật schema metadata theo config.
2. Xác nhận keyspace/table được tham chiếu với **đúng case/quoted CqlIdentifier**.
3. So `system_schema.tables` qua một coordinator.
4. Nếu server thấy table nhưng driver không thấy, xem refresh/events/connectivity.
5. Nếu server cũng không thấy ở một số node, điều tra schema disagreement/DDL propagation.

### 12.5. `session.checkSchemaAgreement()` là kiểm tra tức thời

~~~java
boolean agreed = session.checkSchemaAgreement();
if (!agreed) {
    System.err.println("Schema agreement not reached among UP nodes");
}
~~~

Lệnh kiểm này trả trạng thái khi được gọi, không tự tạo lại table hay sửa schema. Trong giai đoạn DDL, hãy **poll có deadline** thay vì đợi vô hạn. Theo tài liệu Java Driver 4.x, driver schema agreement tập trung vào **UP nodes**; node DOWN có thể nhận schema sau khi phục hồi.

### 12.6. `ExecutionInfo.isSchemaInAgreement()` chỉ có ý nghĩa với DDL

~~~java
import com.datastax.oss.driver.api.core.cql.ResultSet;

ResultSet ddl = session.execute(
    "CREATE TABLE IF NOT EXISTS catalog_lab.audit_by_id (" +
    "id uuid PRIMARY KEY, event_name text)");

boolean ddlAgreement =
    ddl.getExecutionInfo().isSchemaInAgreement();

System.out.println("DDL agreement observed=" + ddlAgreement);
~~~

Với nhiều thao tác DDL, driver có thể chờ schema agreement theo cấu hình, rồi cờ này phản ánh kết quả chờ. **Không dùng** cờ của một SELECT thường để chứng minh agreement:

~~~java
ResultSet read = session.execute(
    "SELECT cluster_name FROM system.local");

// SAI nếu suy "schema ready" từ dòng này:
boolean misleading = read.getExecutionInfo().isSchemaInAgreement();
~~~

Javadoc nêu rằng với statements không phải DDL, `isSchemaInAgreement()` có thể trả `true` mặc định vì việc chờ agreement không áp dụng. Vì thế dùng `session.checkSchemaAgreement()`/metadata check khi cần một gate độc lập.

### 12.7. Prepared statements sau thay đổi schema

Prepared statement được **prepare** dựa trên CQL và schema tại thời điểm đó. Khi table thay đổi:

- Driver/server có thể cần re-prepare nếu prepared ID không còn trên node.
- Một DDL thay/loại column mà CQL đang đọc hoặc bind có thể khiến statement không hợp lệ.
- Driver tự xử lý một số phản hồi `UNPREPARED` nhưng **không thể sửa business CQL sai**.
- Việc dùng cached `PreparedStatement` không thay thế kiểm schema agreement/migration version.

Đối với changes ảnh hưởng contract, chuẩn bị statement **sau khi migration agreement/gate đạt**, kiểm result-set columns và rollback compatibility. **Đừng xoá toàn bộ prepared caches hoặc restart nodes** ngay khi một table chưa được phân giải; trước hết tìm lỗi theo coordinator.

## 13. Chờ schema agreement có deadline và phân biệt startup race

### 13.1. Bounded polling

~~~java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

static void awaitSchemaAgreement(
        CqlSession session,
        Duration budget,
        Duration interval) throws InterruptedException {

    long deadline = System.nanoTime() + budget.toNanos();
    int attempts = 0;

    while (System.nanoTime() < deadline) {
        attempts++;
        if (session.checkSchemaAgreement()) {
            return;
        }

        long remaining = deadline - System.nanoTime();
        if (remaining <= 0) {
            break;
        }

        TimeUnit.NANOSECONDS.sleep(
            Math.min(interval.toNanos(), remaining));
    }

    throw new IllegalStateException(
        "Schema not agreed after " + attempts +
        " attempts within " + budget);
}
~~~

**Đây là code dùng trong integration test/management thread**, không chạy blocking polling trong Netty I/O callback. Budget/interval ví dụ `45s`/`500ms` cần điều chỉnh theo startup và deployment; không có “giá trị mặc định đúng cho mọi cluster”.

### 13.2. Nếu `checkSchemaAgreement()` ném exception?

Helper trên **không** catch mọi exception. Điều đó có chủ đích:

- Sai credentials/permissions, no coordinator, cluster misrouting là những lỗi cần thông báo rõ.
- Trong controlled startup, một số connection/availability failures có thể **retry có phân loại** trong ngân sách chung.
- Không nuốt `InvalidQueryException`/`UnauthorizedException` rồi ngồi đợi 5 phút.

Nếu cần retry transient connectivity, viết **wrapper được kiểm thử** theo loại lỗi cụ thể, giữ last cause và metrics. Không biến mọi failure thành `false` để “chờ schema” mà không biết query tới đúng cluster chưa.

### 13.3. Đợi agreement chưa phải xong workflow

~~~text
DDL submit
     |
DDL succeeds
     |
awaitSchemaAgreement() PASS
     |
Re-read driver metadata / system_schema
     |
Validate expected table columns/PK
     |
Prepare application statements
     |
Read/write CQL probe at declared CL
     |
Verify expected data/value and latency
     |
Enable traffic
~~~

Trong multi-node production, **mỗi bước có scope**: agreement chỉ UP nodes, metadata của current driver, CQL probe chỉ đại diện những partition/token được chọn. Không dùng một probe ở ONE để tuyên bố workload LOCAL_QUORUM đã sẵn sàng.

### 13.4. DDL thành công nhưng `isSchemaInAgreement=false`

Trường hợp này **không tự đồng nghĩa DDL đã rollback**. Coordinator có thể đã apply schema; việc chờ agreement hết hạn vì peers chưa đồng bộ. Hành động đúng:

1. Ghi DDL/query family và timestamp, coordinator.
2. Đọc `system_schema` trên node A/B/C, so schema versions.
3. Đợi bounded agreement nếu có evidence đang hội tụ.
4. Nếu hết budget, HOLD rollout và điều tra gossip/network/DDL conflicts.
5. **Không bắn lại hàng trăm DDL** ở mỗi pod, ngay cả khi có `IF NOT EXISTS`.

### 13.5. Phân biệt chuẩn bị CQL và thực thi CQL

`session.prepare("SELECT ...")` cũng cần schema đủ để coordinator phân giải CQL; nếu table chưa có, PREPARE có thể thất bại trước khi INSERT/SELECT thật sự được gửi. Do vậy lỗi `unconfigured table` xuất hiện ngay lúc **startup prepare** có thể là do **migrations chưa chạy xong**, không phải do dữ liệu read bị hỏng.

## 14. Chiến lược migration an toàn cho cluster nhiều node

### 14.1. Một migration runner duy nhất

~~~text
CI/CD:
  1. Build artifact
  2. Validate backward-compatible CQL migrations
  3. Run dedicated single migration job
  4. Await DDL outcome + schema agreement (UP nodes)
  5. Validate metadata and expected CQL
  6. Deploy new app code gradually
  7. Observe CL/data oracle/error metrics

Application pods:
  DO NOT all run concurrent ALTER TABLE at startup.
~~~

Một `migration_history` table là hữu ích để ghi phiên bản migration, nhưng tự nó không là distributed lock an toàn nếu nhiều runners đồng thời INSERT không có CAS/leader control. Chọn **deployment-level serialization** hoặc một migration coordinator có idempotency/lock semantics đáng tin.

### 14.2. Expand → migrate → contract

Ví dụ đổi API từ `status` sang `payment_status` mà vẫn giữ binary cũ trong rolling deploy:

~~~text
Phase 1 EXPAND:
  ALTER TABLE ... ADD payment_status text
  Await schema agreement

Phase 2 DUAL-COMPATIBILITY:
  New writer optionally dual-writes/reads fallback
  Backfill safely with checkpoint/version
  Validate queries on old and new fields

Phase 3 CONTRACT:
  Confirm no old clients depend on status
  After retention/rollback windows, remove old dependency
  Only then consider DROP COLUMN per reviewed migration
~~~

**Không dùng `ALTER TABLE DROP status` ngay khi node đầu tiên biết `payment_status`**; pod cũ có thể vẫn chạy và prepared queries cũ có thể lỗi. Thay primary key thường cần **bảng mới** và backfill/cutover, không chỉ ALTER một column.

### 14.3. `IF NOT EXISTS` không thay schema diff

Khi DDL có `IF NOT EXISTS` mà table đã tồn tại sai cột/PK:

~~~text
Desired:
  PRIMARY KEY ((tenant_id), order_id)
  revision int

Actual:
  PRIMARY KEY ((order_id))
  revision text

CREATE TABLE IF NOT EXISTS ... returns without creating
-> schema is still incompatible.
~~~

Phải kiểm schema thực/expected và **fail migration** khi có incompatible drift, không “xanh” chỉ vì DDL không ném exception. DDL được quản lý bằng versioned files với review, không sinh từ lỗi runtime một cách vô điều kiện.

### 14.4. Giữ ứng dụng cũ tương thích trong rollout

| Thay đổi | Rủi ro với app cũ | Cách giảm |
|---|---|---|
| ADD nullable column | Thường ít, tùy SELECT * / mapping | Explicit columns, DTO tolerant |
| ADD index | Build/visibility chậm, query workload mới | Đo index build/readiness riêng |
| DROP column | Prepared/DAO cũ có thể lỗi | Chỉ sau khi ngừng toàn bộ old readers |
| Rename column | Các câu CQL cũ dùng tên cũ lỗi | Ưu tiên expand + new column + migrate |
| Đổi table primary key | Không sửa được semantics bằng ADD bình thường | New table + backfill + dual-read/write |
| Thay keyspace RF | Data placement/repair riêng | Schema agreement + repair + data probes |
| View/index creation | Có bước build và hạn chế version | Verify feature-specific readiness |

### 14.5. Nếu cần rollback DDL

Rollback **application deploy** dễ hơn rollback **schema/data mutations**. Khi một DDL gây lỗi:

- Stop/hold rollout, xác định DDL applied đến đâu.
- Không tự `DROP TABLE` vì “muốn quay lại trước migration”: có thể xóa toàn bộ dữ liệu.
- Không dùng `TRUNCATE` để “xóa dữ liệu sai”; đây là destructive operation.
- Nếu rollback bằng schema change tương thích, có migration mới được review và kiểm trên staging.
- Nếu dữ liệu đã backfill/write, cần reconciliation/restore plan riêng; schema agreement không tự undo data.

## 15. Lab A — CQL: keyspace/table tồn tại, tên sai và lỗi được kỳ vọng

### 15.1. Tiền đề và điều kiện an toàn

- Cassandra 4.1/5.0 **một node lab**, `cqlsh` kết nối được.
- Tài khoản có quyền tạo **keyspace lab riêng**; không dùng keyspace thật.
- `SimpleStrategy` RF1 và `CONSISTENCY ONE` chỉ dành cho một node.
- Lab có các truy vấn **cố tình lỗi**, phải ghi nhận lỗi mong đợi chứ không sửa cluster.
- Nếu keyspace `troubleshoot_lab` đã tồn tại và có dữ liệu không do bạn sở hữu, **không overwrite**; dùng namespace lab mới được phê duyệt.

### 15.2. Khởi tạo keyspace và table chuẩn

~~~sql
CREATE KEYSPACE IF NOT EXISTS troubleshoot_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS troubleshoot_lab.orders_by_tenant (
  tenant_id text,
  order_id uuid,
  status text,
  revision int,
  PRIMARY KEY ((tenant_id), order_id)
);

CONSISTENCY ONE;

INSERT INTO troubleshoot_lab.orders_by_tenant
  (tenant_id, order_id, status, revision)
VALUES (
  'tenant-lab',
  11111111-1111-1111-1111-111111111111,
  'CREATED',
  1
);
~~~

**Chỉ sử dụng dữ liệu giả.** Khi chạy lại lab, `INSERT` với cùng PK/values có thể cập nhật cùng row; nếu dữ liệu đã bị thay bởi test khác, xác nhận provenance trước khi viết đè.

### 15.3. Kiểm schema và row mong đợi

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'troubleshoot_lab';

SELECT table_name
FROM system_schema.tables
WHERE keyspace_name = 'troubleshoot_lab';

SELECT column_name, kind, type
FROM system_schema.columns
WHERE keyspace_name = 'troubleshoot_lab'
  AND table_name = 'orders_by_tenant';

SELECT status, revision
FROM troubleshoot_lab.orders_by_tenant
WHERE tenant_id = 'tenant-lab'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Kỳ vọng một row `status='CREATED'`, `revision=1`, và table có bốn columns. Đây là **positive control**: table và dữ liệu đúng trên coordinator lab ở `ONE`. Chưa chứng minh schema agreement trên cluster RF3 nhiều nodes.

### 15.4. Test âm 1 — Keyspace thực sự không tồn tại

~~~sql
SELECT status
FROM no_such_keyspace_999.orders_by_tenant
WHERE tenant_id = 'tenant-lab'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Kỳ vọng một **query validation error** liên quan keyspace không tồn tại. Thông điệp chính xác phụ thuộc Cassandra version; cần xác nhận `system_schema.keyspaces` không có `no_such_keyspace_999`. Đây **không phải schema disagreement** vì lab cố tình tham chiếu namespace không được tạo.

### 15.5. Test âm 2 — Table không tồn tại trong keyspace có thật

~~~sql
SELECT status
FROM troubleshoot_lab.orders_by_tenant_v999
WHERE tenant_id = 'tenant-lab'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Kỳ vọng lỗi như `unconfigured table`. Chạy lại `SELECT table_name FROM system_schema.tables ...` để phân biệt table name khác với schema chưa lan.

### 15.6. Test âm 3 — Chưa chọn keyspace

~~~sql
-- Từ cqlsh session không có USE:
SELECT status
FROM orders_by_tenant
WHERE tenant_id = 'tenant-lab'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Có thể báo **no keyspace has been specified** thay vì table missing. Sau đó:

~~~sql
USE troubleshoot_lab;
SELECT status, revision
FROM orders_by_tenant
WHERE tenant_id = 'tenant-lab'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Hai SELECTs thể hiện **namespace resolution**, không chứng minh cluster có schema disagreement. Trong app Java, ưu tiên full-qualified CQL để tránh phụ thuộc session context.

### 15.7. Test âm 4 — Column không tồn tại

~~~sql
SELECT payment_status
FROM troubleshoot_lab.orders_by_tenant
WHERE tenant_id = 'tenant-lab'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Kỳ vọng `Undefined column name payment_status` (hoặc thông báo tương đương). **Không** bắt exception này rồi tự `ALTER TABLE ADD payment_status` trong production; có thể ứng dụng v2 được deploy trước migration hoặc DTO/CQL có tên sai.

### 15.8. Test âm 5 — Case-sensitive quoted table

~~~sql
CREATE TABLE IF NOT EXISTS troubleshoot_lab."OrderEvents" (
  "TenantId" text PRIMARY KEY,
  status text
);

-- Đúng:
SELECT status
FROM troubleshoot_lab."OrderEvents"
WHERE "TenantId" = 'tenant-lab';

-- Sai (unquoted trở thành orderevents):
SELECT status
FROM troubleshoot_lab.OrderEvents
WHERE "TenantId" = 'tenant-lab';
~~~

SELECT đầu trả kết quả rỗng là **đúng** vì chưa insert row nhưng table tồn tại; SELECT sau phải báo object không tìm thấy. Đây là minh họa rất rõ: một query “trả 0 rows” và một query “unconfigured table” là **hai kết quả khác nhau**.

### 15.9. Kiểm schema version trên một node có giới hạn gì?

~~~sql
SELECT schema_version FROM system.local;
~~~

Lab một node có thể báo agreement nhưng không kiểm network propagation tới peers. Không mô phỏng disagreement bằng cách chỉnh `system.local.schema_version` hoặc can thiệp các system tables. Multi-node diagnostics dành cho staging có quyền và workflow riêng ở mục 19.

## 16. Lab B — Java 17: DDL, agreement, metadata, PREPARE, write/read

### 16.1. Dependency và setup

Ví dụ Gradle Kotlin DSL khi dùng Java Driver Apache 4.18.1:

~~~kotlin
dependencies {
    implementation("org.apache.cassandra:java-driver-core:4.18.1")
}
~~~

Với driver 4.17.x do DataStax duy trì, Maven group/version khác: `com.datastax.oss:java-driver-core:4.17.x`. Chọn một bộ driver tương thích với Cassandra version và JDK, không trộn nhiều versions. Ví dụ code dành **single-node lab trên localhost:9042**, DC giả định `datacenter1` phải thay bằng giá trị thực từ `system.local`/`nodetool status`.

### 16.2. Chương trình độc lập

~~~java
package example;

import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.metadata.schema.KeyspaceMetadata;
import com.datastax.oss.driver.api.core.servererrors.InvalidQueryException;
import java.net.InetSocketAddress;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class SchemaTroubleshootingLab {
    private SchemaTroubleshootingLab() {}

    private static final CqlIdentifier KS =
        CqlIdentifier.fromCql("troubleshoot_java_lab");
    private static final CqlIdentifier TABLE =
        CqlIdentifier.fromCql("orders_by_id");

    public static void main(String[] args) throws Exception {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .build()) {

            // Step 1: DDL trên namespace lab; không dùng trong
            // mỗi production application pod.
            ResultSet keyspaceDdl = session.execute(
                "CREATE KEYSPACE IF NOT EXISTS troubleshoot_java_lab " +
                "WITH replication = {'class':'SimpleStrategy', " +
                "'replication_factor':1}");
            System.out.println("keyspace DDL agreement=" +
                keyspaceDdl.getExecutionInfo().isSchemaInAgreement());

            ResultSet tableDdl = session.execute(
                "CREATE TABLE IF NOT EXISTS " +
                "troubleshoot_java_lab.orders_by_id (" +
                "tenant_id text, order_id uuid, " +
                "status text, revision int, " +
                "PRIMARY KEY ((tenant_id), order_id))");
            System.out.println("table DDL agreement=" +
                tableDdl.getExecutionInfo().isSchemaInAgreement());

            // Step 2: Đợi agreement và metadata bằng deadline,
            // tránh Thread.sleep(10000) cố định.
            awaitExpectedSchema(session, Duration.ofSeconds(45));

            // Step 3: chứng minh PREPARE + read/write path
            PreparedStatement insert = session.prepare(
                "INSERT INTO troubleshoot_java_lab.orders_by_id " +
                "(tenant_id, order_id, status, revision) " +
                "VALUES (?, ?, ?, ?)");

            PreparedStatement select = session.prepare(
                "SELECT status, revision " +
                "FROM troubleshoot_java_lab.orders_by_id " +
                "WHERE tenant_id = ? AND order_id = ?");

            UUID orderId = UUID.fromString(
                "22222222-2222-2222-2222-222222222222");

            BoundStatement write = insert.bind(
                    "tenant-java", orderId, "READY", 5)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setTimeout(Duration.ofSeconds(3));
            session.execute(write);

            BoundStatement read = select.bind("tenant-java", orderId)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setIdempotent(true)
                .setTimeout(Duration.ofSeconds(3));
            Row row = session.execute(read).one();
            if (row == null
                    || !"READY".equals(row.getString("status"))
                    || row.getInt("revision") != 5) {
                throw new AssertionError("Data oracle failed");
            }

            System.out.println("DDL + schema + CQL/data PASS");

            // Step 4: negative control — cố tình sai table name.
            try {
                session.execute(
                    "SELECT status FROM troubleshoot_java_lab." +
                    "missing_table_999 WHERE tenant_id='tenant-java'");
                throw new AssertionError(
                    "Expected validation error for missing table");
            } catch (InvalidQueryException expected) {
                System.out.println(
                    "Negative control PASS: " +
                    expected.getClass().getSimpleName());
            }
        }
    }

    private static void awaitExpectedSchema(
            CqlSession session, Duration budget)
            throws InterruptedException {

        long deadline = System.nanoTime() + budget.toNanos();
        while (System.nanoTime() < deadline) {
            boolean agreement = session.checkSchemaAgreement();

            boolean metadataHasTable = session.getMetadata()
                .getKeyspace(KS)
                .flatMap(ks -> ks.getTable(TABLE))
                .isPresent();

            if (agreement && metadataHasTable) {
                return;
            }
            TimeUnit.MILLISECONDS.sleep(250);
        }
        throw new AssertionError(
            "Schema agreement/driver metadata did not converge");
    }
}
~~~

### 16.3. Vì sao kiểm table metadata bên cạnh agreement?

Đoạn code đầy đủ trong mục 16.2 dùng:

~~~java
boolean metadataHasTable = session.getMetadata()
    .getKeyspace(KS)
    .flatMap(ks -> ks.getTable(TABLE))
    .isPresent();
~~~

Mục tiêu là kiểm **đúng table** trong metadata snapshot mới, không chỉ sự tồn tại của keyspace. Agreement giữa các UP nodes có thể PASS trong khi driver metadata chưa được cập nhật; ứng dụng chỉ nên chuẩn bị/query table sau khi những điều kiện đã định đều đạt. Code lab là ví dụ có thể dùng để học và kiểm thử; STEP 6/QA chuyên sâu sẽ compile/verify theo toolchain, còn STEP 4 này **không chạy Gradle**.

### 16.4. Kết quả kỳ vọng

~~~text
keyspace DDL agreement=true/false
table DDL agreement=true/false
DDL + schema + CQL/data PASS
Negative control PASS: InvalidQueryException
~~~

Hai cờ DDL có thể khác nhau trong thời điểm chưa hội tụ; helper tiếp tục chờ trong budget. Trong single-node lab thường nhanh. Test âm chỉ chứng minh table sai tên **thật sự không tồn tại** ở node lab, không tạo schema disagreement.

### 16.5. Đặt CL phù hợp với topology

Trong lab RF1:

~~~java
request.setConsistencyLevel(DefaultConsistencyLevel.ONE);
~~~

Trong production RF3 một DC, có thể dùng `LOCAL_QUORUM` sau khi có **ba full replicas đủ điều kiện** và hợp đồng dữ liệu yêu cầu. Không lấy kết quả RF1/ONE làm bằng chứng production RF3/LOCAL_QUORUM, và không hạ CL chỉ để qua schema migration gate.

## 17. Lab C — JUnit 5 chống false green

Chương trình Java ở mục 16 chạy như một ứng dụng nhỏ. Với CI, thêm **test oracle cụ thể** thay vì chỉ có log `Schema agreed`. Ví dụ JUnit 5 dưới đây dùng **single-node lab đã được tạo và seed** bởi mục 16; test này không tự tạo multi-node cluster và không chứng minh schema agreement nhiều nodes.

### 17.1. Test class đầy đủ cho môi trường lab

~~~java
package example;

import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.servererrors.InvalidQueryException;
import java.net.InetSocketAddress;
import java.util.UUID;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

final class SchemaReadinessIT {
    private static CqlSession session;

    @BeforeAll
    static void connect() {
        session = CqlSession.builder()
            .addContactPoint(
                new InetSocketAddress("127.0.0.1", 9042))
            .withLocalDatacenter("datacenter1")
            .build();
    }

    @AfterAll
    static void close() {
        if (session != null) {
            session.close();
        }
    }

    @Test
    void tableExistsAndCqlContractWorks() {
        assertTrue(session.checkSchemaAgreement(),
            "Schema not agreed among currently UP nodes");

        assertTrue(session.getMetadata()
            .getKeyspace(
                CqlIdentifier.fromCql("troubleshoot_java_lab"))
            .flatMap(ks -> ks.getTable(
                CqlIdentifier.fromCql("orders_by_id")))
            .isPresent(), "Missing table in driver metadata");

        Row row = session.execute(
            session.prepare(
                "SELECT status, revision FROM " +
                "troubleshoot_java_lab.orders_by_id " +
                "WHERE tenant_id = ? AND order_id = ?")
                .bind("tenant-java",
                    UUID.fromString(
                        "22222222-2222-2222-2222-222222222222"))
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setIdempotent(true)).one();

        assertNotNull(row, "Expected lab row missing");
        assertEquals("READY", row.getString("status"));
        assertEquals(5, row.getInt("revision"));
    }

    @Test
    void missingTableShouldProduceValidationError() {
        assertThrows(InvalidQueryException.class,
            () -> session.execute(
                "SELECT status FROM " +
                "troubleshoot_java_lab.table_not_created_999"));
    }
}
~~~

**Điều kiện:** Bắt buộc chạy bước chuẩn bị dữ liệu ở mục 16 trước. Nếu dùng Testcontainers, fixture phải khởi động Cassandra/seed trước `@BeforeAll` hoặc quản lý session trong test class. Trong CI nhiều worker, tạo keyspace/row IDs tách biệt để không dùng dữ liệu stale. **Không** viết test mà `assertTrue(checkSchemaAgreement())` trả PASS rồi coi toàn bộ CQL/data/CL cũng đã sẵn sàng.

### 17.2. Negative control phải kiểm đúng loại lỗi

`assertThrows(InvalidQueryException.class)` chứng minh CQL được gửi tới coordinator và table name không hợp lệ. `assertThrows(RuntimeException.class)` quá rộng: no connection, invalid credentials hay syntax khác có thể ném exception khiến test xanh sai.

### 17.3. Trường hợp test phải FAIL rõ

~~~text
Wrong local DC/credentials                 -> FIX CONFIG
DDL agreement timeout                     -> HOLD MIGRATION
Expected table missing in driver metadata -> INVESTIGATE REFRESH/SCHEMA
CL ONE works but production wants LQ      -> COVERAGE GAP
Expected row/revision differs             -> DATA/SCHEMA CONTRACT FAIL
~~~

Trong production, dữ liệu có thể thay đổi đồng thời, nên test sentinel cần partition/ID ổn định thuộc quyền quản lý của test và dùng đúng consistency contract.

## 18. Nhiều coordinator: tìm node nào đang thấy schema cũ

### 18.1. Một phương pháp chẩn đoán an toàn

Đối với cluster 3 nodes A/B/C:

~~~text
Target: keyspace catalog_lab, table orders_by_id
Expected: tenant_id text, order_id uuid, status text, revision int

1. cqlsh trực tiếp tới A -> system.local.schema_version
2. Đọc system_schema.tables/columns trên A
3. Lặp lại tới B/C bằng đúng read-only credentials
4. nodetool describecluster tại authorized vantage point
5. Correlate Java error time/coordinator với host_id
6. Check migration DDL logs và internode communication
7. Bounded wait; nếu vẫn disagreement -> HOLD/ESCALATE
~~~

Không cần ép driver gửi business CQL tới một node đang nghi lỗi bằng cách phá topology hoặc sửa routing production. **Direct cqlsh connection** tới từng node là phép đọc schema, giữ low rate và TLS/credentials phù hợp.

### 18.2. Bảng đối chiếu ba node

| Node | State | `schema_version` | Table thấy? | Cột `revision`? | Kết luận tạm |
|---|---|---|---|---|---|
| A | UN | V2 | Có | Có | Schema mới |
| B | UN | V2 | Có | Có | Schema mới |
| C | UN | V1 | Có | Không | Stale schema |

Tất cả `UN` không loại trừ schema disagreement. Nhưng nếu cả ba cùng V2, một Java instance vẫn lỗi, hãy xét **wrong keyspace/identifier/role, stale driver metadata hoặc old binary CQL** thay vì tự khẳng định C còn V1.

### 18.3. Quy lỗi về coordinator

Java Driver 4.x có `ExecutionInfo.getCoordinator()` trên response thành công; với lỗi, nhiều cause có thể nằm trong `AllNodesFailedException.getAllErrors()`. Một report nên ghi:

~~~text
request_id=trace-abc
query_family=orders.getById
keyspace=catalog_lab
table=orders_by_id
local_dc=dc1
coordinator_host_id=... (nếu có evidence)
exception_type=InvalidQueryException
phase=PREPARE
app_release=...
schema_version_local_A=...
schema_version_local_B=...
schema_version_local_C=...
~~~

**Lưu ý:** Với một `InvalidQueryException` đơn lẻ, coordinator ID có thể không xuất hiện trực tiếp trong API exception như trong `ExecutionInfo` thành công; cần driver tracing/server logs. Đừng tự suy đoán host_id khi không có evidence.

### 18.4. Một coordinator stale không đồng nghĩa mất dữ liệu

Nếu Node C còn schema V1, table mới trong V2 có thể không phân giải được khi query tới C. Dữ liệu ghi trước đó trên các replicas khác **không tự bị xóa** vì sự kiện này. Việc khôi phục schema cần xác định nguyên nhân propagation, **không** chạy `DROP/CREATE` làm mất SSTables hoặc tạo table với primary key sai.

### 18.5. Chờ hay escalate?

| Tình huống | Lựa chọn |
|---|---|
| Vừa chạy DDL, peers cập nhật, budget còn | **HOLD + bounded wait** |
| Một node DOWN, UP-node agreement PASS | **HOLD node promotion** tới khi kiểm schema sau recovery |
| Schema versions khác nhau kéo dài | **ESCALATE**, thu logs/versions |
| Versions giống nhau nhưng expected DDL sai | **STOP migration**, sửa definition |
| Một pod dùng wrong keyspace | **FIX CONFIG**, không sửa schema |
| Role thiếu privilege | **FIX RBAC**, không retry DDL |
| Cả cluster thiếu CL do replica failures | **Availability incident**, không gọi schema disagreement |

Không có một số giây chuẩn cho mọi topology. Budget phải theo cluster size, network và SLO triển khai; đo progress thay vì giả định.

## 19. Multi-DC, node restart và mixed-version clusters

### 19.1. Local DC là điều kiện của Java Driver

~~~text
Cluster:
  dc1: A, B, C
  dc2: D, E, F

Java service in dc1:
  local-datacenter=dc1
  session connects/routes via local nodes by policy

Java service in dc2:
  local-datacenter=dc2
  session connects/routes via local nodes by policy
~~~

Nếu chỉ kiểm schema từ dc1, không thể công bố dc2 đã ready, đặc biệt khi inter-DC network/gossip có vấn đề. Mỗi DC cần vantage point riêng theo ứng dụng. Khi RF khác nhau, `LOCAL_QUORUM` cần số full replicas khác nhau trong mỗi DC; **schema readiness** và **data availability at CL** là hai cổng tách biệt.

### 19.2. NTS là replication metadata, không tự sinh nodes

~~~sql
-- Chỉ làm ví dụ trên cluster lab THẬT có đủ hai DC:
CREATE KEYSPACE IF NOT EXISTS catalog_multidc_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3,
  'dc2': 3
};
~~~

**Không chạy đoạn này trên single-node lab** rồi mong Cassandra tự tạo sáu replicas. Một DDL có thể được chấp nhận khi chưa đủ physical replicas, nhưng read/write `LOCAL_QUORUM`/`EACH_QUORUM` sẽ không đạt nếu thiếu natural replicas. Không giảm CL để làm migration test xanh.

### 19.3. Node DOWN trong migration

~~~text
Before DDL: A/B/C schema V1; C DOWN
Migration:  A/B apply V2; UP-node agreement PASS
App deploy: Uses V2
C rejoins later, may need schema catch-up
~~~

Khi C quay lại, cần kiểm:

- Nó nhận và áp schema V2, có metadata table/columns đúng.
- CQL transport và driver node state phù hợp.
- Các writes/snapshot/data movement cần thiết đã hội tụ theo CL/repair policy.
- Không khởi động rolling restart node kế tiếp trước khi resilience margin đủ.

Agreement giữa A/B lúc C DOWN **không chứng nhận** C sẵn sàng nhận traffic V2 ngay khi nó chuyển thành `UN`.

### 19.4. Rolling upgrade và feature support

Nếu cluster mixed versions:

- Đừng phát DDL dùng syntax, index, type hay compaction option chỉ hỗ trợ ở phiên bản mới khi old nodes chưa hỗ trợ.
- Kiểm official upgrade path/release notes cho **cặp Cassandra versions** đang chạy.
- Chỉ chạy schema migrations không tương thích sau phase upgrade được phép.
- Ghi app+driver+server versions trong incident report; exception/log messages có thể khác.

### 19.5. Repair không phải công cụ sửa schema

`nodetool repair` dùng cho đồng bộ **data replicas/SSTables**, **không phải lệnh sửa schema disagreement**. Nếu `system_schema`/`schema_version` còn khác, repair có thể không giúp, thậm chí tạo tải lớn khi cluster đã yếu. `nodetool cleanup`, `compact`, `flush` cũng ảnh hưởng storage lifecycle, không thay DDL migration hoặc peer schema propagation.

## 20. Quyền truy cập và lỗi “bảng không tồn tại” giả

### 20.1. Vì sao role quan trọng?

Trong Cassandra:

- `CREATE KEYSPACE`, `CREATE TABLE` cần quyền schema phù hợp.
- `ALTER` và `DROP` cần quyền quản trị đối tượng tương ứng.
- `SELECT` và `MODIFY` cần role permissions theo keyspace/table.
- Truy cập system schema/metadata/`DESCRIBE` có thể chịu RBAC hoặc cấu hình authorizer riêng.

Nếu superuser test PASS nhưng Java service báo `UnauthorizedException`, **không** tạo keyspace/table mới; phải so account/roles/grants và auth configuration.

### 20.2. Lệnh xác minh quyền, chỉ khi được phép

~~~sql
LIST ROLES;
LIST ALL PERMISSIONS OF app_service_role;
~~~

Cú pháp/khả năng xem permissions phụ thuộc Cassandra version/authorizer. Không paste full grants chứa tên nội bộ nhạy cảm lên public ticket. Kiểm bằng **service role thật** hoặc tài khoản test tương đương thay vì dùng superuser.

### 20.3. Hai credential sets, một query

~~~text
Admin cqlsh:
  SELECT catalog_lab.orders_by_id -> PASS

Java service role:
  SELECT catalog_lab.orders_by_id -> Unauthorized

Conclusion:
  RBAC/config incident; schema vẫn có thể hoàn toàn agreed.
~~~

**Không khắc phục bằng cấp superuser cho Java application** chỉ để vượt readiness gate. Áp quyền tối thiểu theo query families, role ownership và migration service riêng.

### 20.4. Error message bị che bởi ORM/framework

Spring Data Cassandra, custom repositories hoặc application exception translators có thể bọc `InvalidQueryException` trong exception khác. Vì thế:

~~~text
HTTP 500: "repository initialization failed"
      |
Bean/DAO startup
      |
CqlSession.prepare(query)
      |
InvalidQueryException: unconfigured table catalog_lab.orders_by_id
~~~

Phân tích **root cause chain và CQL query family** trước khi kết luận lỗi dependency injection/Java object mapping. Không in nguyên CQL có bind values/PII vào public logs.

## 21. Observability: biểu đồ nào cho thấy disagreement thật?

### 21.1. Các nguồn bằng chứng cần ghép

| Lớp | Tín hiệu | Diễn giải đúng |
|---|---|---|
| CI/CD/migration runner | DDL statement ID, sequence, start/end, agreement observation | DDL đã chạy đến bước nào |
| Cassandra `system.local` | Local `schema_version` theo node | Phiên bản schema node ấy thấy |
| `nodetool describecluster` | Mapping schema versions → peers | Các peer groups chưa hội tụ theo vantage point |
| Cassandra logs | Schema change/propagation/apply failures | Nguyên nhân propagation chậm/thất bại |
| Driver schema metadata | Keyspace/table/column snapshot | Client đã thấy definition nào |
| Driver exceptions | `InvalidQuery`/`Unauthorized`/`AllNodesFailed` | Query thất bại vì schema hay vì loại khác |
| App query family | Error rate từng route/DAO/release | Phạm vi ảnh hưởng |
| Ring/topology | `UN`/`UJ`/`DN`, DC/rack, gossip | Nodes nào cần nhận schema |
| Business CL/data probes | Đúng CQL và value/version ở CL yêu cầu | Readiness sau agreement |

Một tỷ lệ `InvalidQuery` tăng **có thể** đi cùng schema disagreement, nhưng cũng có thể đến từ release Java gửi cột sai; cần **schema version evidence** trước khi gắn nhãn.

### 21.2. Alert điều kiện đơn giản

~~~text
Alert A:
  schema_versions_distinct_among_UP_nodes > 1
  continuously across configured windows
  AND migration_in_progress is known/unknown
  -> HOLD rollout, investigate propagation

Alert B:
  application_invalid_query_errors increase
  after app_release or migration
  -> inspect namespace/table/column and coordinator

Alert C:
  schema agreement PASS
  BUT business data oracle at required CL FAIL
  -> investigate data/replica/readiness separately
~~~

Các metrics trong sơ đồ là **khái niệm cần instrument**, không phải Prometheus series có sẵn tên như trên. Một exporter có thể không xuất `schema_versions_distinct` trực tiếp; khi đó dùng script/probe read-only theo chu kỳ **được giới hạn** và/hoặc operator conditions.

### 21.3. Không gây schema storm khi điều tra

Một readiness endpoint gọi `checkSchemaAgreement()` và `system_schema` hàng nghìn lần/giây từ hàng trăm pods có thể tự tạo tải metadata/network không cần thiết. Nên:

- Một migration/controller owner thực hiện agreement check tập trung.
- Poll có budget và backoff/jitter hợp lý.
- Ứng dụng giữ `CqlSession` lâu dài, không mở session mỗi request.
- Chỉ scrape/log đủ để nhận ra schema version drift/incident.
- Không tự kích hoạt DDL từ liveness probe.

### 21.4. Correlation mà không rò rỉ dữ liệu

~~~text
incident_id=inc-2026-...
app_release=orders-v2
query_family=orders.getById
phase=PREPARE
keyspace=catalog_lab
table=orders_by_id
local_dc=dc1
coordinator=host-id-or-unknown
error_type=InvalidQueryException
migration_version=V24
schema_agreement=false
last_observation_utc=...
~~~

Đừng dùng raw tenant ID/order ID, password, TLS keys hoặc full user-bind CQL trong metrics labels. Schema/table names có thể nhạy cảm trong một số môi trường; giới hạn truy cập dashboard.

### 21.5. Nếu metrics nói READY nhưng query vẫn sai

Một schema agreement boolean có thể đúng, trong khi:

- App dùng khác keyspace hoặc wrong case.
- Table hiện hữu có schema drift nhưng mọi nodes đều thống nhất **schema sai**.
- Java Driver chưa refresh snapshot.
- Role thiếu quyền.
- Dữ liệu lịch sử chưa restore/repair hoặc CL không đủ.

Vì vậy gate cuối cần **CQL execution + expected data oracle** và scope rõ, không chỉ metric agreement.

## 22. Hai mươi hai tình huống xử lý sự cố thường gặp

### Ca 1 — Vừa deploy Java v2, PREPARE báo `unconfigured table`

**Triệu chứng:** App pods mới khởi động trước migration job, startup `session.prepare()` thất bại.

**Chẩn đoán:** Kiểm deployment order, keyspace/table trong `system_schema`, schema versions và migration history. Nếu table chưa được tạo trên mọi nodes, đây là race/migration chưa chạy.

**Xử lý:** HOLD traffic app v2, chạy migration theo single owner, đợi agreement, kiểm metadata rồi mới khởi động/enable app. **Không** để mỗi app pod tự retry DDL vô hạn.

### Ca 2 — Bảng có trong cqlsh nhưng Java không thấy

**Triệu chứng:** Admin `DESCRIBE TABLE catalog_lab.orders_by_id` PASS, Java `InvalidQueryException`.

**Chẩn đoán:** So contact points/DC/cluster, credentials, full-qualified CQL và case. Sau đó kiểm driver metadata snapshot/refresh và coordinator gây lỗi.

**Xử lý:** Sửa config hoặc xử lý metadata refresh theo phiên bản; **không** `DROP/CREATE` table vì một pod thiếu context.

### Ca 3 — Một pod dùng sai keyspace mặc định

**Triệu chứng:** `SELECT ... FROM orders_by_id` trên pod A PASS, pod B báo unconfigured.

**Chẩn đoán:** Pod A có `withKeyspace(catalog_lab)`, pod B không hoặc trỏ khác namespace. Driver execution profiles cũng có thể khác.

**Xử lý:** Dùng `catalog_lab.orders_by_id` đầy đủ hoặc đồng nhất builder/config; thêm startup assertion với keyspace expected.

### Ca 4 — Quoted `"OrderEvents"` vs `OrderEvents`

**Triệu chứng:** Table tạo bằng quote và có chữ hoa; app query không quote tên.

**Chẩn đoán:** Đọc `system_schema.tables` để thấy tên thực; quy tắc identifier folding của CQL.

**Xử lý:** Sửa CQL/`CqlIdentifier` đúng quoted spelling; ưu tiên lower_snake_case ở schema mới. Không tạo một table thứ hai tên `orderevents` để che lỗi nếu chưa được review.

### Ca 5 — `IF NOT EXISTS` trả thành công nhưng column thiếu

**Triệu chứng:** Migration job báo success; app v2 báo `Undefined column revision`.

**Chẩn đoán:** Table đã tồn tại với schema khác; `IF NOT EXISTS` không so definition.

**Xử lý:** Diff expected vs actual columns/PK/types; làm migration tương thích có chủ đích, không lặp `CREATE TABLE` vô hạn.

### Ca 6 — Schema versions A/B=V2, C=V1, cả ba `UN`

**Triệu chứng:** Một tỷ lệ request qua C thất bại với unconfigured table, A/B vẫn PASS.

**Chẩn đoán:** Local schema versions, `nodetool describecluster`, internode/gossip logs, migration timestamp.

**Xử lý:** HOLD rollout, đợi bounded propagation nếu vừa DDL; nếu kéo dài, điều tra connectivity/schema apply, DBA xử lý theo runbook. **Không** chạy `UPDATE system.local`.

### Ca 7 — C DOWN khi migration, UP nodes báo agreement PASS

**Triệu chứng:** A/B đồng bộ V2, C DOWN; release gate dùng mỗi `checkSchemaAgreement` và cho mở toàn bộ traffic.

**Nguy cơ:** C chưa được xác minh schema mới khi phục hồi.

**Xử lý:** Tách agreement-UP gate và **node-rejoin gate**; kiểm local schema/CL/data sau C UP trước rolling restart khác.

### Ca 8 — `ExecutionInfo.isSchemaInAgreement()` của SELECT luôn xanh

**Triệu chứng:** Team đọc cờ này từ một `SELECT system.local` rồi báo “schema agreement success”.

**Nguyên nhân:** Cờ có ý nghĩa sau schema-changing request, không phải cách đo agreement cho arbitrary SELECT.

**Xử lý:** Dùng `session.checkSchemaAgreement()` + metadata/`nodetool describecluster` đúng ngữ cảnh. Test CQL user table và data oracle riêng.

### Ca 9 — Driver metadata từ trước migration không đổi

**Triệu chứng:** Java giữ `Metadata m = session.getMetadata()` trước DDL, poll `m.getKeyspace()` mãi thấy absent.

**Chẩn đoán:** Immutable metadata snapshot vs live server schema.

**Xử lý:** Gọi `session.getMetadata()` mới sau agreement, kiểm schema metadata config/refresh. Không ép driver reconnect liên tục để “refresh” nếu còn API/contract phù hợp.

### Ca 10 — Java PREPARE cũ lỗi sau DROP COLUMN

**Triệu chứng:** Rolling deploy còn pod v1 đọc `status`, migration v2 đã DROP `status`.

**Nguyên nhân:** Backward incompatible DDL trong khoảng old/new binaries cùng hoạt động.

**Xử lý:** STOP/drop traffic v2 nếu cần, giữ data, triển khai expand–migrate–contract; phục hồi schema qua reviewed migration chứ không tự DROP table.

### Ca 11 — Multi-DC: dc1 PASS, dc2 lỗi một phần

**Triệu chứng:** Schema versions ở dc1 đồng nhất, dc2 có một node stale hoặc app route sai local DC.

**Chẩn đoán:** `system.local.schema_version` theo DC, inter-DC connectivity, driver local DC và coordinator.

**Xử lý:** HOLD rollout dc2, kiểm riêng DC2 agreement/CL/data. Không suy kết quả dc1 đại diện toàn cluster.

### Ca 12 — Unauthorized bị chuyển thành “table missing”

**Triệu chứng:** Repository wrapper log “schema not initialized”, root cause là `UnauthorizedException`.

**Chẩn đoán:** Stack/cause chain, service role vs admin role, grants.

**Xử lý:** Sửa RBAC tối thiểu, không tạo table mù hoặc cấp superuser cho app.

### Ca 13 — `CREATE KEYSPACE` DDL timeout, migration runner retry liên tục

**Triệu chứng:** Có lúc coordinator đã apply keyspace; lần retry sau trả already exists, error counters tăng.

**Chẩn đoán:** DDL outcome có thể ambiguous nếu client timeout; xem `system_schema.keyspaces` ở peers và migration state.

**Xử lý:** Dừng retry storms, reconcile schema versions/definition trước khi replay idempotently; `IF NOT EXISTS` vẫn cần schema diff.

### Ca 14 — Schema cùng version, nhưng SELECT trả row rỗng sau restore

**Triệu chứng:** DDL/metadata đúng và agreement PASS, historical order ID mất.

**Nguyên nhân khả dĩ:** Restore/snapshot không đầy đủ, wrong partition/TTL, RF/CL, SSTables chưa load hoặc source manifest sai.

**Xử lý:** Chuyển sang **data recovery incident**, so seeded records/backup manifest, repair/restore runbook. Không sửa schema vì table tồn tại.

### Ca 15 — Nâng RF rồi thấy “schema agreement”, nhưng mới thiếu replicas

**Triệu chứng:** `ALTER KEYSPACE` thành công, mới bổ sung RF, đọc ở CL mạnh timeout/không thấy dữ liệu cũ.

**Chẩn đoán:** Đổi replication metadata không tự đồng bộ historical data.

**Xử lý:** Full repair/streaming theo phiên bản, kiểm natural replica count/token/DC và data oracle; **không** hạ CL như cách “sửa schema”.

### Ca 16 — Index mới đã hiện trong schema nhưng query vẫn lỗi/chậm

**Triệu chứng:** `CREATE INDEX`/SAI agreement đạt nhưng index build chưa hoàn tất hoặc query không tương thích pattern.

**Chẩn đoán:** Tách **index definition visibility** khỏi **index build/readiness**, version support và query restrictions.

**Xử lý:** Kiểm feature-specific metrics/logs, load/query test, chờ build theo runbook; không kết luận base table missing.

### Ca 17 — Mixed Cassandra versions, DDL mới không được node cũ hiểu

**Triệu chứng:** DDL hoạt động trên node mới, một số peers áp dụng lỗi hoặc schema versions không hội tụ.

**Chẩn đoán:** Server release versions, upgrade compatibility, unsupported types/options.

**Xử lý:** HOLD DDL, hoàn thành upgrade path được hỗ trợ trước khi phát migration không tương thích; escalation cho DBA, không ép schema version.

### Ca 18 — K8s liveness probe chạy migration mỗi lần gọi

**Triệu chứng:** Hàng chục pods gọi `CREATE TABLE IF NOT EXISTS` mỗi vài giây, schema chatter/errors tăng.

**Nguyên nhân:** DDL đặt sai nơi (health endpoint/constructor).

**Xử lý:** Loại DDL khỏi liveness, dùng migration job một owner và readiness query có rate limit. Liveness chỉ xác nhận process health; readiness kiểm dependency/CL/data theo scope.

### Ca 19 — Operator nghĩ `nodetool repair` sửa schema disagreement

**Triệu chứng:** Cluster versions khác nhau; operator bắt đầu full repair tạo I/O lớn, lỗi schema vẫn còn.

**Nguyên nhân:** Repair xử lý data replicas, không cập nhật schema version bị lệch theo mong muốn.

**Xử lý:** Không làm thêm destructive/expensive maintenance khi chưa có diagnosis. Thu versions/logs/DDL timeline, xử lý schema propagation theo version-specific runbook.

### Ca 20 — Một node còn `UJ`, migration gate vẫn cho traffic

**Triệu chứng:** Node mới join, schema/version có thể đồng nhất nhưng streaming/bootstrap chưa xong; một số queries timeout ở CL yêu cầu.

**Chẩn đoán:** `nodetool status`, `netstats`, RF/natural replica sets, CQL/data probes.

**Xử lý:** Tách node ready và service ready; không thúc traffic tới node chưa bootstrap/streaming xong. Agreement không đồng nghĩa data readiness.

### Ca 21 — Table có thật nhưng typo cột query builder Java

**Triệu chứng:** CQL do ORM sinh tham chiếu `order_status` nhưng schema có `status`.

**Chẩn đoán:** Ghi query family và CQL identifier đã sanitize, so `system_schema.columns`, app DTO mapping.

**Xử lý:** Sửa DAO/mapping và thêm integration test contract; không tạo cột dư chỉ để làm query sai có thể chạy.

### Ca 22 — CQL `USE` trong cqlsh thành công nhưng Java vẫn sai namespace

**Triệu chứng:** Một operator chạy `USE catalog_lab` rồi thử SELECT thấy PASS, Java instance khác vẫn unconfigured.

**Giải thích:** `USE` chỉ đặt context **của cqlsh session đó**.

**Xử lý:** Java dùng `withKeyspace` hoặc full-qualified CQL, kiểm đúng cluster/role. Không kỳ vọng `USE` của operator thay namespace toàn cluster.

## 23. Runbook GO / HOLD / STOP khi gặp schema error

### 23.1. Mục tiêu vận hành

Khôi phục query service **không phá hỏng dữ liệu/schema**, xác định lỗi thuộc lớp nào và đưa release về trạng thái được chứng minh. Kết quả cuối không đơn giản là “không thấy `unconfigured table` nữa”; phải kiểm:

1. **Đúng cluster, DC, role, keyspace/table**.
2. **Đúng schema definition**, không chỉ cùng tên.
3. **Schema agreement** ở các nodes đang UP, topology risk được ghi nhận.
4. **Java Driver metadata** và prepared CQL đúng phiên bản.
5. **CL + data oracle** đạt yêu cầu, p99/errors trong SLO.

### 23.2. Giai đoạn A — Khoanh vùng và ngăn lỗi lan rộng

~~~text
Incident start
    |
    v
Freeze competing DDL/migration runners
    |
Confirm cluster/DC/keyspace/table/role
    |
Identify affected app versions/query families
    |
Check if data writes are failing or unknown
    |
Decide initial blast radius and action
    |
HOLD risky rollout / preserve availability
~~~

**Lưu ý:** “Freeze competing DDL” không đồng nghĩa kill Cassandra nodes, huỷ streaming đang chạy hay rollback schema một cách bất ngờ. Nếu migration đang thực thi, chặn **những DDL mới** và phối hợp owner xem request đã commit đến đâu.

Tạo timeline với UTC: deployment, migration DDL begin/end, first `InvalidQuery`, schema_version snapshots, failures by coordinator, affected tenant/query family. Không dùng một tỷ lệ global HTTP 500 để thay nguyên nhân gốc.

### 23.3. Giai đoạn B — Thu bằng chứng chỉ đọc

~~~bash
# Commands theo phạm vi quyền, không chạy sửa đổi dữ liệu:
nodetool status
nodetool describecluster
nodetool gossipinfo
nodetool tpstats
nodetool netstats
~~~

~~~sql
-- Dùng cqlsh trực tiếp vào từng coordinator nghi vấn:
SELECT cluster_name, data_center, host_id, schema_version
FROM system.local;

SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name='catalog_lab';

SELECT table_name FROM system_schema.tables
WHERE keyspace_name='catalog_lab';

SELECT column_name, kind, type
FROM system_schema.columns
WHERE keyspace_name='catalog_lab'
  AND table_name='orders_by_id';
~~~

Khi dùng `cqlsh` từ admin node, phải ghi rõ **IP/host ID của coordinator** để tránh so lại chính một node rồi tưởng đã khảo sát ba nodes. Với multi-DC, ghi đúng DC/rack và phiên bản Cassandra của từng node.

### 23.4. Giai đoạn C — Phân loại root cause

| Kết quả | Phân loại | Hành động |
|---|---|---|
| Object absent ở mọi UP nodes, migration chưa chạy | MISSING MIGRATION | **HOLD** app release; chạy versioned migration có owner |
| Object absent ở một số nodes, versions khác | SCHEMA DISAGREEMENT | **HOLD** DDL/traffic mới; bounded wait/gossip diagnosis |
| Object present everywhere, wrong columns/PK | SCHEMA DRIFT | **STOP** incompatible rollout; reviewed migration |
| Object present, app references wrong case/keyspace | APP CONFIG/CQL | Sửa client query/config, không đổi schema |
| Object present, driver metadata cũ | CLIENT METADATA | Kiểm refresh/events/version; revalidate query |
| Admin PASS, service role unauthorized | RBAC | Sửa role/grants tối thiểu |
| Table exists, read at CL unavailable | REPLICA AVAILABILITY | Điều tra RF/CL/natural replicas, không chạy DDL |
| Table exists, expected row missing after restore | DATA RECOVERY | Manifest/SSTables/repair, không sửa schema mù |
| DDL request timeout và schema state chưa rõ | UNKNOWN DDL OUTCOME | Reconcile state trước khi retry |

### 23.5. Giai đoạn D — Hành động sửa an toàn

**Nếu migration thiếu:** Xác nhận deployment target, review DDL tương thích, chỉ **một runner** thực thi, đợi agreement có deadline, so schema diff, kiểm prepare/read/write. Giữ rollback/forward-fix plan.

**Nếu disagreement tạm:** Theo dõi versions/logs/network, đặt HOLD cho deploy mới, chờ hội tụ trong budget. Nếu qua deadline vẫn drift, DBA/SRE điều tra schema apply/gossip/protocol theo version-specific runbook. **Không** chỉnh schema version UUID/metadata system tables.

**Nếu wrong identifier/role:** Sửa Java config/CQL mapping/RBAC; không động tới Cassandra user data.

**Nếu data unready:** Chuyển sang restore/repair/replica availability runbook; schema agreement **không giải quyết** data mismatch.

### 23.6. Giai đoạn E — Gate xác minh

~~~text
G0: Correct target cluster, local DC and credentials
           |
G1: Expected keyspace/table/columns/PK verified
           |
G2: Schema agreement among currently UP nodes
           |
G3: Previously DOWN nodes handled by rejoin gate
           |
G4: Java Driver current metadata + PREPARE succeeds
           |
G5: CQL write/read at required CL and data oracle
           |
G6: Error rate, p95/p99 and retries stable
           |
         GO canary
           |
       Expand traffic with monitoring
~~~

Nếu G2 PASS nhưng G5 FAIL, **không đánh dấu resolved**. Lỗi có thể ở data/replicas/CL chứ không phải schema. Một query `SELECT system.local` hoặc một read ở `ONE` không chứng minh một service cần `LOCAL_QUORUM` đã phục hồi.

### 23.7. Bảng quyết định GO/HOLD/STOP

| Quan sát | Quyết định | Giải thích |
|---|---|---|
| DDL vừa chạy, versions đang hội tụ, no errors lớn | **HOLD** | Đợi bounded agreement |
| Node stale persist, app requests qua node đó lỗi | **HOLD + ESCALATE** | Cần DBA/network diagnosis |
| DDL bị phát đồng thời từ nhiều pods | **STOP DDL mới** | Tránh schema storm |
| Wrong app namespace/case đã sửa, metadata/CQL PASS | **GO canary** | Không cần sửa Cassandra data |
| RBAC sai, role vẫn thiếu permissions | **STOP** | Không mở traffic |
| Schema agreed nhưng table definition sai | **STOP** | Metadata thống nhất sai vẫn là lỗi |
| Read/write ở required CL và oracle PASS, p99 ổn | **GO canary** | Đạt phạm vi probe |
| Node DOWN cần cập nhật schema trước rolling restart tiếp | **HOLD topology change** | Bảo vệ resilience margin |
| `DROP/TRUNCATE` được đề xuất vì table “not found” | **STOP** | Destructive, thiếu căn cứ |
| DDL outcome client timeout, server state chưa rõ | **HOLD** | Reconcile trước khi retry |
| Data corruption/recovery mismatch | **STOP + DATA INCIDENT** | Chặn rollout, bảo toàn evidence |

### 23.8. Rollback sau migration có giới hạn

Một migration đã tạo cột/table mới có thể được giữ lại trong giai đoạn rollback Java nếu tương thích ngược. **Rollback binary trước** đôi khi an toàn hơn DROP schema mới, nhưng cần kiểm:

- Old app có hoạt động được với schema hiện tại không?
- Đã có writes dùng cột/table mới chưa?
- Có dual-write/backfill hoặc timestamp conflict chưa?
- Old clients còn query trên cột bị DROP không?
- Snapshot/restore và data reconciliation plan đã có chưa?

Khi thiếu bằng chứng, **HOLD** và phối hợp owner thay vì tự phá schema.

### 23.9. Mẫu báo cáo incident

~~~text
INCIDENT_ID:
UTC_FIRST_ERROR:
CLUSTER / ENVIRONMENT / LOCAL_DC:
CASSANDRA VERSION PER NODE:
JAVA DRIVER / APP RELEASE:
KEYSPACE / TABLE / EXPECTED SCHEMA VERSION:
QUERY FAMILY / ERROR AT PREPARE OR EXECUTE:
SERVICE ROLE / EFFECTIVE KEYSPACE:
COORDINATOR HOST IDS / SAMPLE COUNTS:
SCHEMA_VERSION BY NODE:
NODE STATUS / GOSSIP / NETWORK:
LATEST MIGRATION AND DDL OUTCOME:
SYSTEM_SCHEMA_DIFF:
CL / RF / DATA ORACLE RESULT:
ACTION: GO / HOLD / STOP / ESCALATE:
ROLLBACK/FORWARD-FIX OWNER:
UNKNOWN OUTCOMES (DDL/WRITE):
NEXT REVALIDATION UTC:
~~~

**Không** log raw credentials, private IPs vào public incident ticket nếu policy hạn chế, hoặc bind values chứa PII. Host IDs/thời gian và sanitized query family thường đủ cho internal correlation.

## 24. Checklist trước và sau sửa lỗi schema

### 24.1. Nhận diện đúng môi trường

- [ ] Đã xác nhận **đúng cluster/environment**, không chỉ cluster_name.
- [ ] Contact points, native transport, TLS/auth và local DC của Java đúng.
- [ ] Application release/version và migration version được ghi rõ.
- [ ] Dùng **fully qualified** keyspace.table khi cần.
- [ ] Kiểm identifiers unquoted/lowercase vs quoted/case-sensitive.
- [ ] Role của service và quyền schema/user-table phù hợp.
- [ ] Lỗi xảy ra ở PREPARE hay EXECUTE được xác định.
- [ ] Không nhầm `Unauthorized`/`Unavailable`/timeout với missing table.
- [ ] Không suy một node `UN` nghĩa toàn cluster có agreement.

### 24.2. Kiểm schema thực tế

- [ ] `system_schema.keyspaces` có expected keyspace/replication config.
- [ ] `system_schema.tables` có expected table name.
- [ ] `system_schema.columns` khớp types/PK/clustering layout.
- [ ] Index/view/type metadata được so nếu query dùng chúng.
- [ ] Schema versions trên những UP nodes liên quan được đối chiếu.
- [ ] Biết node DOWN/JOINING và rejoin gate cần thiết.
- [ ] `nodetool describecluster`/`gossipinfo` được đọc đúng góc nhìn.
- [ ] Driver `session.getMetadata()` là snapshot mới, không giữ stale object.
- [ ] `checkSchemaAgreement()` được dùng đúng, có timeout/budget.
- [ ] `isSchemaInAgreement()` không được lấy từ SELECT để chứng minh agreement.

### 24.3. Migrations và Java Driver

- [ ] Chỉ một migration runner chủ động phát DDL cùng lúc.
- [ ] `IF NOT EXISTS` không được xem như schema definition validation.
- [ ] DDL có source-control/review/version và plan compatibility.
- [ ] Code cũ và mới cùng tồn tại được trong rolling release.
- [ ] `DROP COLUMN`/`DROP TABLE` chỉ thực hiện khi dependency đã hết và có backup.
- [ ] Prepared CQL được kiểm sau DDL agreement và metadata refresh.
- [ ] Có bounded polling, không `Thread.sleep(30000)` mù và retry vô hạn.
- [ ] Exceptions còn root cause/coordinator; không catch-all rồi tự tạo table.
- [ ] Node với Cassandra version cũ không phải áp unsupported DDL.
- [ ] Test CQL/metadata từ app role, không chỉ superuser.

### 24.4. Sau khi sửa

- [ ] All UP nodes schema-agreed theo scope và không có drift kéo dài.
- [ ] Previously DOWN nodes được đưa qua rejoin schema gate.
- [ ] Keyspace/table/columns định nghĩa đúng, không chỉ tên tồn tại.
- [ ] `session.prepare` và production query family chạy thành công.
- [ ] WCL/RCL khớp RF/local DC và contract nghiệp vụ.
- [ ] Data oracle (expected key/value/version) PASS; migration/restore riêng nếu cần.
- [ ] Error rates, timeout/retry/p95/p99 ổn định qua các windows.
- [ ] Không phát sinh schema storms từ healthchecks/apps.
- [ ] Incident evidence/rollback plan được ghi lại và owner nhận bàn giao.
- [ ] Không dùng `DROP`/`TRUNCATE`/sửa system tables như workaround.

## 25. Những “cách sửa nhanh” nên tránh

### 25.1. `DROP TABLE` rồi `CREATE TABLE` lại

**Sai:** Một service pod báo `unconfigured table`, DBA DROP rồi CREATE để “refresh schema”.

**Tác hại:** Có thể xóa dữ liệu của table hiện hữu, làm prepared queries/cache đồng loạt lỗi, phá dấu vết restore/replica state. Tên table mới trùng tên cũ **không có nghĩa data quay lại**.

**Đúng:** Đối chiếu system_schema trên nodes, agreement/version, cluster/role, rồi dùng reviewed migration hoặc client fix; không đụng data trước khi có evidence.

### 25.2. Chỉnh `system.local` hoặc `system_schema` bằng tay

**Sai:** Nhìn schema_version UUID khác nhau và cố cập nhật system tables thủ công.

**Tác hại:** Cassandra quản lý schema internals; sửa trực tiếp có thể tạo divergence khó phục hồi, metadata mismatch và lỗi không được hỗ trợ.

**Đúng:** Điều tra gossip/schema propagation/DDL conflicts/version, escalate DBA và thực hiện **quy trình được hỗ trợ** bởi đúng phiên bản Cassandra.

### 25.3. Restart mọi node cùng lúc

**Sai:** Vừa thấy disagreement liền restart toàn cluster để “reset cache”.

**Tác hại:** Mất quorum/availability, làm startup/streaming/commitlog replay cạnh tranh và khiến bằng chứng gốc biến mất.

**Đúng:** Giữ logs/snapshots, kiểm từng node; rolling restart nếu thật sự cần phải có owner, RF/CL safety gate và rollback.

### 25.4. Đổi CL từ `LOCAL_QUORUM` xuống `ONE`

**Sai:** Sau schema migration, write/read lỗi vì thiếu replica, team đổi CL để test xanh.

**Tác hại:** Không giải quyết schema mismatch, có thể che replica outage và làm dữ liệu stale/consistency guarantee yếu đi.

**Đúng:** CL là hợp đồng nghiệp vụ. Phân biệt schema validation, replica availability và data correctness; không đổi hợp đồng chỉ để bỏ error.

### 25.5. Retry mọi `InvalidQueryException` vô hạn

**Sai:** Bất kỳ lỗi CQL nào cũng ngủ 100ms rồi retry mãi.

**Tác hại:** Typos, wrong table, missing column, Unauthorized không biến mất; retry tạo nhiều load và làm rollout treo.

**Đúng:** Retry **có điều kiện** khi đã xác minh migration đang chạy/hội tụ, trong deadline; permanent query/schema drift phải fail-fast.

### 25.6. `CREATE TABLE IF NOT EXISTS` từ mỗi HTTP request

**Sai:** Repository tự kiểm table tồn tại mỗi lần request và tạo khi thấy lỗi.

**Tác hại:** Schema chatter/DDL storm, auth side effects, race với migration, khó rollback và che mất cấu hình sai.

**Đúng:** Schema do dedicated migration runner sở hữu. App chỉ kiểm readiness/queries cần thiết với tần suất thấp.

### 25.7. Coi `Schema agreement PASS` là mọi dữ liệu đã restore

**Sai:** Tất cả nodes cùng schema version nên tuyên bố backup restoration hoàn tất.

**Tác hại:** Data có thể chưa load, SSTables thiếu, repaired state không đúng, CL chưa đạt, hoặc expected PK trả rỗng.

**Đúng:** Dùng historical seeded keys, data manifest/checksum, restore/repair runbook và CQL at required CL.

### 25.8. Đánh nhầm `NoNodeAvailable` thành keyspace missing

**Sai:** Driver không có coordinator usable, team chạy DDL để tạo lại keyspace.

**Tác hại:** Root cause là local DC/routing/auth/transport, không phải schema.

**Đúng:** Kiểm driver node metadata, contact points, local DC, TLS/auth và connectivity trước; chỉ phân loại schema khi đã có evidence query validation.

### 25.9. Chỉ kiểm bảng trong một DC

**Sai:** `system_schema` tại dc1 đúng, team cho rằng dc2 đang dùng schema mới.

**Tác hại:** Inter-DC propagation/network faults hoặc node DOWN có thể làm dc2 chậm hội tụ.

**Đúng:** Schema probes và data CL probes theo từng vùng triển khai; report coverage và DOWN-node caveat.

### 25.10. Đợi schema UUID giống rồi bỏ qua SLO/error rate

**Sai:** Versions bằng nhau và rollout GO dù app p99/timeouts vẫn xấu.

**Tác hại:** App có thể đang reprepare storm, cache cold, network lỗi hoặc replicas thiếu CL; schema agreement không đo latency.

**Đúng:** Sau agreement cần đọc/ghi đúng CL, data oracle và ổn định p95/p99/retries/errors qua cửa sổ có đủ mẫu.

## 26. Câu hỏi tự đánh giá và gợi ý đáp án

**Câu 1.** `unconfigured table` có chứng minh table không tồn tại trên mọi node không?  
**Gợi ý:** Không; nó phản ánh schema của coordinator đã trả lỗi hoặc namespace query đang dùng.

**Câu 2.** `Keyspace ... does not exist` khác `Unauthorized` thế nào?  
**Gợi ý:** Một lỗi phân giải schema/namespace, một lỗi permission; kiểm type/cause trước khi hành động.

**Câu 3.** Vì sao cần dùng tên `keyspace.table` đầy đủ khi chẩn đoán?  
**Gợi ý:** Tránh phụ thuộc current keyspace của session/`cqlsh`.

**Câu 4.** `USE catalog_lab` trong cqlsh có thay keyspace của Java service không?  
**Gợi ý:** Không; chỉ session cqlsh ấy.

**Câu 5.** Tên unquoted `OrderEvents` được Cassandra hiểu thế nào?  
**Gợi ý:** Chuẩn hóa lowercase thành `orderevents`.

**Câu 6.** `"OrderEvents"` và `orderevents` có là một table không?  
**Gợi ý:** Không; quoted identifier phân biệt hoa/thường.

**Câu 7.** Tại sao `CREATE TABLE IF NOT EXISTS` thành công chưa chứng minh schema đúng?  
**Gợi ý:** Table cũ có thể có primary key/types/columns khác.

**Câu 8.** Một keyspace tồn tại có nghĩa table bất kỳ đã tồn tại không?  
**Gợi ý:** Không; keyspace là namespace và replication metadata.

**Câu 9.** Schema agreement phản ánh những node nào?  
**Gợi ý:** Các node được xem là UP/known theo góc nhìn check; DOWN nodes không được bảo đảm.

**Câu 10.** Schema agreement có bảo đảm dữ liệu đã restore/repair xong không?  
**Gợi ý:** Không; metadata và data lifecycle riêng.

**Câu 11.** `schema_version` UUID có phải Git migration version không?  
**Gợi ý:** Không; là ID của schema state ở node.

**Câu 12.** Có nên sửa `system.local.schema_version` bằng tay để các UUID giống nhau không?  
**Gợi ý:** Không; Cassandra quản lý internals, phải xử lý propagation/root cause.

**Câu 13.** `nodetool status UN` có chứng minh schema agreement không?  
**Gợi ý:** Không; U=Up, N=Normal, không phải schema version.

**Câu 14.** Lệnh nào nhóm schema versions theo peers?  
**Gợi ý:** `nodetool describecluster` (và kiểm local schema_version theo node).

**Câu 15.** Nếu node A/B V2, C V1, mọi node UN, là tín hiệu gì?  
**Gợi ý:** Schema disagreement hoặc transient propagation từ góc nhìn đã đo.

**Câu 16.** Nếu schema versions giống nhau nhưng query column sai, nên làm gì?  
**Gợi ý:** Kiểm definition/DTO/CQL/`system_schema.columns`; agreement có thể là “cùng schema sai”.

**Câu 17.** CQL nào liệt kê keyspaces?  
**Gợi ý:** `SELECT ... FROM system_schema.keyspaces`.

**Câu 18.** CQL nào cho biết table name theo keyspace?  
**Gợi ý:** `system_schema.tables WHERE keyspace_name=?`.

**Câu 19.** CQL nào kiểm columns/types/PK kind?  
**Gợi ý:** `system_schema.columns` với keyspace và table.

**Câu 20.** `DESCRIBE TABLE` có thể gửi qua mọi Java Driver `execute` như CQL không?  
**Gợi ý:** Không; là tiện ích cqlsh, dùng metadata/system_schema trong Java.

**Câu 21.** `system.peers_v2` có giống nhau về columns ở mọi Cassandra version không?  
**Gợi ý:** Không giả định; dùng `DESCRIBE TABLE` để kiểm schema thực.

**Câu 22.** Vì sao phải kiểm local schema_version trực tiếp trên nhiều nodes?  
**Gợi ý:** Peer metadata/gossip view ở một coordinator có thể stale.

**Câu 23.** Khi DDL vừa chạy, schema versions khác nhau vài giây có là bug chắc chắn không?  
**Gợi ý:** Không; có thể là propagation transient, chờ có deadline.

**Câu 24.** Khi chờ hết deadline và versions vẫn khác, nên làm gì?  
**Gợi ý:** HOLD rollout, thu logs/network/schema apply evidence và escalate.

**Câu 25.** `session.checkSchemaAgreement()` làm gì?  
**Gợi ý:** Kiểm agreement tại thời điểm gọi; không chạy DDL và không sửa schema.

**Câu 26.** Có nên dùng `isSchemaInAgreement()` của SELECT để chứng minh agreement?  
**Gợi ý:** Không; cờ có ý nghĩa sau DDL, non-DDL có thể true mặc định.

**Câu 27.** Vì sao `session.getMetadata()` đã lấy trước DDL có thể sai sau DDL?  
**Gợi ý:** Metadata snapshot cũ, cần snapshot mới và schema refresh.

**Câu 28.** `Metadata.getKeyspace` thấy keyspace có chứng minh đủ replicas ở CL không?  
**Gợi ý:** Không; metadata visibility khác read/write availability.

**Câu 29.** Khi PREPARE lỗi vì table chưa có, đã thực thi INSERT chưa?  
**Gợi ý:** Chưa nếu lỗi xuất hiện ngay ở PREPARE của statement đó.

**Câu 30.** Driver gặp `UNPREPARED` có nghĩa table bị DROP không?  
**Gợi ý:** Không; server có thể mất prepared cache, driver reprepare; cần cause/schema.

**Câu 31.** Tại sao không để 20 Java pods cùng chạy `ALTER TABLE` lúc boot?  
**Gợi ý:** DDL races/churn, schema disagreement, rollout khó kiểm.

**Câu 32.** Một migration history table có tự khóa distributed migration không?  
**Gợi ý:** Không nếu chỉ có INSERT thường không có CAS/owner coordination.

**Câu 33.** Expand–migrate–contract có lợi gì?  
**Gợi ý:** Giữ app cũ/mới tương thích trong rolling deploy và backfill.

**Câu 34.** Có thể đổi partition key bằng một `ALTER TABLE ADD` không?  
**Gợi ý:** Không đổi semantics primary key theo cách đó; thường tạo bảng mới + backfill/cutover.

**Câu 35.** Nếu keyspace replication RF tăng và schema agreed, data chắc có ở replica mới chưa?  
**Gợi ý:** Không; cần repair/streaming và data verification riêng.

**Câu 36.** Vì sao `nodetool repair` không phải cách sửa schema disagreement?  
**Gợi ý:** Repair đồng bộ data replicas/SSTables, không là DDL/schema repair API.

**Câu 37.** Admin cqlsh PASS, service role `Unauthorized`; root cause ở đâu?  
**Gợi ý:** Permissions/role, không tự kết luận missing table.

**Câu 38.** `NoNodeAvailableException` có phải lỗi missing keyspace không?  
**Gợi ý:** Không; driver không tìm được coordinator usable, kiểm config/local DC.

**Câu 39.** `UnavailableException` có phải schema disagreement không?  
**Gợi ý:** Không; đó là replica liveness/CL availability.

**Câu 40.** DDL request timeout có chứng minh DDL chưa áp không?  
**Gợi ý:** Không; outcome có thể ambiguous, phải reconcile schema versions/definition.

**Câu 41.** Vì sao không tự `DROP TABLE` khi một Java pod báo “not found”?  
**Gợi ý:** Có thể phá dữ liệu trong khi lỗi chỉ là namespace/metadata/propagation.

**Câu 42.** Khi C DOWN và A/B agreement PASS, có thể triển khai traffic vào C ngay sau khi UP không?  
**Gợi ý:** Cần rejoin schema/data/readiness gate; chưa tự bảo đảm.

**Câu 43.** Vì sao kết quả từ dc1 không đại diện dc2?  
**Gợi ý:** Schema propagation, local DC, RF/CL và network availability riêng.

**Câu 44.** Nếu SELECT không lỗi nhưng row rỗng sau restore, nên điều tra lớp nào?  
**Gợi ý:** Data restore/TTL/partition/CL, không mặc định schema.

**Câu 45.** Một query `LOCAL_QUORUM` cần gì ngoài schema agreement?  
**Gợi ý:** Đủ full natural replicas đáp ứng CL và dữ liệu đúng/oracle/SLO.

**Câu 46.** Negative test `assertThrows(Exception.class)` có nhược điểm gì?  
**Gợi ý:** Có thể pass do network/auth/syntax khác; kiểm exception cụ thể.

**Câu 47.** Nên lưu gì vào incident ticket để xác định schema disagreement?  
**Gợi ý:** App/driver/server versions, keyspace/table/role, coordinator, schema versions per node, DDL timeline, sanitized errors, CL probes.

**Câu 48.** Khi nào có thể mở traffic sau sửa schema?  
**Gợi ý:** Sau gate đúng target/permissions, definition, UP-node agreement/rejoin, Java metadata/PREPARE, data oracle tại CL và SLO ổn định.

## 27. Tổng kết: từ “table not found” tới chẩn đoán đúng nguyên nhân

~~~text
             INVALID QUERY / MISSING KEYSPACE-TABLE
                              |
                  1. Verify target identity
                 cluster + DC + role + app release
                              |
                  2. Check CQL identifiers
               fully qualified name + case + quote
                              |
                  3. Inspect system_schema
              keyspace + table + columns + PK/types
                              |
                 4. Compare per-node schema
            schema_version + describecluster + logs
                              |
                +-------------+--------------+
                |                            |
           AGREED BUT WRONG             DIFFERENT VERSIONS
                |                            |
           App config/migration          Gossip/DDL/rejoin
           RBAC/definition drift         investigate and HOLD
                |                            |
                +-------------+--------------+
                              |
                  5. Java metadata refresh
                session.getMetadata() + PREPARE
                              |
                  6. Verify business query
            required RF/CL + expected value/revision
                              |
                   7. SLO and rollout gate
                     GO / HOLD / STOP
~~~

### 27.1. Bảy nguyên tắc cần nhớ

1. **Tên đối tượng là đầu mối chẩn đoán, không phải bằng chứng hoàn chỉnh.** `unconfigured table` có thể do namespace/case/role/migration hoặc coordinator schema stale.
2. **Schema metadata là phân tán.** Một DDL chấp nhận trên coordinator chưa nói mọi node đã biết nó. So schema versions, đặc biệt trên các nodes gây lỗi.
3. **Agreement có phạm vi.** Nó thường chỉ xác nhận các nodes đang UP, không bảo đảm node DOWN hoặc data đã restore/repair xong.
4. **Driver metadata có vòng đời riêng.** Snapshot cũ, prepared statements và keyspace configuration có thể khiến Java nhìn khác cqlsh.
5. **Migration phải có người điều phối.** Một runner, versioned DDL, expand–migrate–contract, chờ có deadline và schema diff; `IF NOT EXISTS` không thay contract validation.
6. **Không dùng thao tác phá hủy làm workaround.** `DROP`, `TRUNCATE`, chỉnh system tables, restart toàn cluster hay giảm CL có thể làm sự cố nghiêm trọng hơn.
7. **Khôi phục được chứng minh bằng truy vấn thực.** Kiểm table đúng, driver `PREPARE` chạy, read/write tại CL nghiệp vụ và data oracle đúng, sau đó theo dõi errors/p99 qua cửa sổ đủ mẫu.

**Thông điệp cốt lõi:** Khi gặp `Keyspace/table không tồn tại` trong Apache Cassandra, hãy hỏi **“đối tượng có tồn tại ở đúng cluster, đúng namespace và trong schema view của những coordinator nào?”**. Nếu schema versions chưa hội tụ, xử lý theo **schema propagation/DDL lifecycle**; nếu versions đã giống mà CQL vẫn lỗi, điều tra **identifier, schema drift, quyền hoặc Java Driver metadata**. Chỉ khi CQL at required CL và dữ liệu nghiệp vụ đã kiểm chứng đúng mới nên tuyên bố dịch vụ sẵn sàng.

### 27.2. Phạm vi thực hành và kiểm thử chuyên sâu

Các lab một node ở đây minh họa **lỗi tên sai/namespace, tạo schema và đợi agreement**, không tạo ra schema disagreement multi-node thực sự. Để kiểm inter-node propagation, phải dùng cluster **multi-node thật** với RF/DC/seed/rack/gossip đúng và chỉ inject faults theo kế hoạch staging được phép. Trong workflow tài liệu, STEP 4 hoàn thiện Markdown kỹ thuật; STEP 6 Content QA sẽ kiểm chứng sâu độ đúng và thực thi snippets bằng toolchain phù hợp. Không xem ví dụ chưa chạy là kết quả test production.

## Tài liệu tham khảo

- [Apache Cassandra — Documentation](https://cassandra.apache.org/doc/stable/) — tài liệu chính thức theo phiên bản về CQL, schema, architecture, operations.
- [Apache Cassandra — CQL and data modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html) — keyspace/table, query-first design và primary-key restrictions.
- [Apache Cassandra — Dynamo architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html) — token, coordinator, natural replicas, RF và consistency levels.
- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html) — `USE`, `DESCRIBE`, `CONSISTENCY` và CQL diagnostics.
- [Apache Cassandra — nodetool describecluster](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/describecluster.html) — schema versions và trạng thái cluster theo `nodetool`.
- [Apache Cassandra — Monitoring metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html) — server request/error metrics và tài nguyên Cassandra.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html) — phạm vi data repair, khác schema propagation.
- [Apache Java Driver 4.18 — Schema metadata](https://apache.github.io/cassandra-java-driver/4.18.0/core/metadata/schema/) — agreement, schema-change events và metadata refresh.
- [Apache Java Driver 4.18 — Metadata overview](https://apache.github.io/cassandra-java-driver/4.18.0/core/metadata/) — snapshot semantics và node/schema metadata.
- [Apache Java Driver 4.18 — Node metadata](https://apache.github.io/cassandra-java-driver/4.18.0/core/metadata/node/) — node states, local DC và driver view.
- [Apache Java Driver 4.18 — Prepared statements](https://apache.github.io/cassandra-java-driver/4.18.0/core/statements/prepared/) — `PREPARE`, caching và reprepare.
- [Apache Java Driver 4.18 — ExecutionInfo Javadoc](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/cql/ExecutionInfo.html) — ngữ nghĩa `isSchemaInAgreement` và coordinator information.
- [Apache Java Driver 4.18 — Configuration](https://apache.github.io/cassandra-java-driver/4.18.1/core/configuration/) — driver local DC, keyspace, metadata/timeout policies.
- [Apache Java Driver 4.18 — Retry policies](https://apache.github.io/cassandra-java-driver/4.18.1/core/retries/) — phân loại errors/attempts, tránh retry không idempotent.
- [JUnit 5 User Guide](https://docs.junit.org/current/user-guide/) — assertions, lifecycle test và integration setup.


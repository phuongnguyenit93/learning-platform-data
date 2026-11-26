# Đánh giá thay đổi chỉ mục, định dạng dữ liệu và kế hoạch truy vấn khi nâng cấp Neo4j

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **nâng cấp Neo4j DBMS**, **di trú database**, **đổi store format**, **tái tạo chỉ mục** và **thay đổi phiên bản Cypher**.
- Kiểm kê schema/index/constraint và đánh giá yêu cầu chuyển **BTREE** từ Neo4j 4.4 sang **RANGE, TEXT hoặc POINT** phù hợp khi lên Neo4j 5.
- Nhận biết các store format `aligned`, `block`, `standard`, `high_limit`; hiểu điều kiện hỗ trợ theo phiên bản/edition, chi phí chuyển đổi và nguy cơ thay đổi internal IDs.
- Xây dựng tập truy vấn chuẩn để so sánh `EXPLAIN`, `PROFILE`, `Rows`, `DB Hits`, index seek/scan, runtime, p95/p99 và chi phí tài nguyên trước–sau nâng cấp.
- Kiểm tra tương thích **Cypher 5** và **Cypher 25**, quản lý default language theo database và tránh thay đổi semantics ngoài ý muốn.
- Thực hiện kế hoạch dry run trên bản sao dữ liệu, xác minh index `ONLINE`, đối soát property graph, chạy hiệu năng có kiểm soát và xác định điều kiện **go/no-go**.
- Lập kế hoạch backup/restore, downtime, rollback toàn hệ thống, điều kiện cho Java Driver/Spring Data Neo4j và plugin.

Đây là bài thuộc chương **Nâng cấp và di trú** trong module **DATABASE_ENGINE_GRAPH_NEO4J**. Neo4j dùng **property graph** gồm node, relationship, label/type và các thuộc tính; Cypher khai thác index, constraint, thống kê dữ liệu và query planner để tìm quan hệ, đường đi. Một thay đổi phiên bản có thể ảnh hưởng **cả ba lớp**: cách lưu trên đĩa, cấu trúc index và cách thực thi truy vấn. Dù ứng dụng Java Driver hoặc Spring Data Neo4j không thay một dòng mã, API vẫn có thể bị thay đổi kết quả, latency hay hành vi ghi nếu không kiểm tra trước.

> **Lưu ý phiên bản:** Nội dung phân biệt Neo4j **4.4 → 5.x**, dòng **5.26 LTS** và các bản có **Calendar Versioning (2025.x/2026.x)**. Những tính năng như `block`, cú pháp Cypher 25 và chỉ mục vector mới có điều kiện theo version/edition. **Không áp dụng máy móc lệnh migrate/index cho production**. Đối chiếu hướng dẫn chính thức của cặp phiên bản đang chạy và phiên bản đích, thực hiện thử trên bản sao độc lập trước.

## 1. Nâng cấp DBMS khác với di trú database và đổi store format

Một dự án có thể nói “upgrade Neo4j”, nhưng trên thực tế có nhiều công việc:

| Khái niệm | Thay đổi gì? | Khi nào cần? |
| --- | --- | --- |
| **Upgrade DBMS** | Binary/container image, Java runtime, cấu hình server, driver/plugin tương thích | Đưa phần mềm lên bản được hỗ trợ |
| **Database migration** | Chuyển database sang DBMS/version có yêu cầu migration trên store | Chẳng hạn lộ trình **4.4 → 5** |
| **Store format migration** | Chuyển cách biểu diễn node, relationship, property trên disk | Ví dụ `aligned` → `block` |
| **Index migration/rebuild** | Đổi kiểu/provider hoặc tái tạo cấu trúc index phù hợp | Xử lý BTREE cũ, thay provider, index `FAILED` |
| **Cypher compatibility** | Chọn cú pháp/ngữ nghĩa `CYPHER 5` hay `CYPHER 25`, điều chỉnh truy vấn | Các release từ 2025.06 trở đi |
| **Application compatibility** | Driver, Spring Boot/SDN, APOC/GDS, procedure, serialization | Đảm bảo API vẫn hoạt động và nhanh |

**Không phải mọi upgrade đều đổi store format**. Theo hướng dẫn Neo4j, nhiều nâng cấp server chỉ thay binary và khởi động lại, trong khi **đổi major store format** hoặc di trú từ legacy store là bước riêng, có thể phải chạy offline.

~~~mermaid
flowchart TD
    A["Xác định source/target Neo4j"] --> B["Kiểm kê schema, store, query, plugin"]
    B --> C{"Cần di trú store hay index?"}
    C -->|Có| D["Backup + offline migration/rebuild lab"]
    C -->|Không| E["Upgrade binary trong lab"]
    D --> F["Khởi động, kiểm tra index ONLINE"]
    E --> F
    F --> G["Đối soát graph + EXPLAIN/PROFILE"]
    G --> H{"Đạt correctness + SLO?"}
    H -->|Không| I["Sửa kế hoạch hoặc rollback lab"]
    H -->|Có| J["Phê duyệt rollout có phương án khôi phục"]
~~~

Một phương án có thể **đúng chức năng nhưng thất bại hiệu năng** hoặc ngược lại. Hãy đặt hai cửa kiểm tra độc lập.

## 2. Ma trận thay đổi cần kiểm tra theo phiên bản và edition

| Phạm vi chuyển đổi | Điều phải đánh giá |
| --- | --- |
| **4.4 → 5.x** | Xử lý BTREE legacy và index-backed constraints; upgrade/migration database; schema và câu lệnh Cypher; cấu hình Log4j 2; driver/plugin |
| **5.x trước 5.22 → 5.22+** | `block` trở thành mặc định cho **database Enterprise mới** từ 5.22; **database cũ không tự được viết lại sang block** chỉ vì binary mới |
| **5.23+** | `standard` và `high_limit` bị **deprecated**; lập kế hoạch chuyển khỏi format cũ trước mốc ngừng hỗ trợ theo tài liệu |
| **5.26 LTS → 2025.x/2026.x** | Lộ trình upgrade riêng, thay đổi runtime/index provider, Java compatibility và hướng dẫn release |
| **2025.06+** | Có lựa chọn **Cypher 5 / Cypher 25**; kiểm tra ngôn ngữ mặc định của từng database và cú pháp bị thay đổi |
| **2026.02+** | File `neo4j.conf` phân phối mới đặt mặc định `CYPHER_25` cho database tạo mới; database hiện hữu giữ setting của nó |
| **Community ↔ Enterprise** | Khả năng cluster, loại store/index và quy trình quản trị khác nhau; không mặc nhiên hỗ trợ mọi format/command |
| **AuraDB managed** | Không can thiệp offline store hay filesystem server như self-managed; dùng quy trình nâng cấp/snapshot được gói hỗ trợ |

**Cần kiểm tra riêng database hiện có và database tạo mới.** Một Neo4j Enterprise mới có thể tạo database `block`, nhưng một database `aligned` đã tồn tại vẫn chạy với format cũ cho đến khi có thao tác migration được hỗ trợ.

Đọc thêm: [Upgrade and Migration Guide](https://neo4j.com/docs/upgrade-migration-guide/current/), [Store formats](https://neo4j.com/docs/operations-manual/current/database-internals/store-formats/), [Cypher default version](https://neo4j.com/docs/operations-manual/current/configuration/cypher-version-configuration/).

## 3. Chụp baseline trước khi nâng cấp

Đừng bắt đầu bằng lệnh `neo4j-admin database migrate`. Trước hết cần có **bộ dữ liệu đối chiếu** từ môi trường hiện tại.

### 3.1. Kiểm kê DBMS, database và store format

Trên môi trường có quyền thích hợp:

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

~~~cypher
// Tên cột store có trên các phiên bản hỗ trợ.
// Chạy trong ngữ cảnh quản trị phù hợp.
SHOW DATABASES
YIELD name, currentStatus, store
RETURN name, currentStatus, store
ORDER BY name;
~~~

`store` cho biết thông tin format của database theo phiên bản hỗ trợ. Nếu bản cũ không cung cấp cột đó, dùng công cụ thông tin store tương ứng với bản đích và tài liệu Operations Manual; không tự suy format từ tên database. Ghi nhận **nguồn thực tế**:

- Version đầy đủ, edition, Java runtime, OS/image và cách chạy server (standalone/cluster/Aura).
- Các database vật lý và `system`, alias, access mode, dung lượng store/index/transaction logs.
- Store format từng database, các extension/plugins và license dùng bởi ứng dụng.
- Số lượng node, relationship, label/type, các thuộc tính dùng làm business key.
- Cấu hình heap, page cache, transaction timeout, query logging/metrics và resource limits.

### 3.2. Chụp schema index và constraint

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes,
      properties, indexProvider, state,
      populationPercent, owningConstraint
RETURN name, type, entityType, labelsOrTypes,
       properties, indexProvider, state,
       populationPercent, owningConstraint
ORDER BY type, name;
~~~

~~~cypher
SHOW CONSTRAINTS;
~~~

Các cột và provider cụ thể tùy version/edition; lệnh `SHOW INDEXES YIELD *` hỗ trợ xem đầy đủ metadata khi có quyền. **`state`**, **`populationPercent`** và **`indexProvider`** rất quan trọng vì index được định nghĩa trên schema chưa chắc đã sẵn sàng dùng ngay.

Đặc biệt đánh dấu:

- Index `BTREE` và provider `native-btree-1.0` / `lucene+native-3.0` từ Neo4j 4.4.
- Các **constraint sở hữu index**; không tự `DROP INDEX` backing index của uniqueness constraint như index độc lập.
- Index cần cho lookup nghiệp vụ (`customerId`, `orderId`), range theo ngày/giá, TEXT search, POINT địa lý, full-text và vector.
- Index đã ở trạng thái `POPULATING` hoặc `FAILED` ngay từ **trước nâng cấp**.
- Index không còn được query dùng hoặc bị trùng schema; kiểm chứng trước khi xóa.

### 3.3. Chụp workload truy vấn thật

Không chỉ ghi lại kết quả của `MATCH (n) RETURN count(n)`. Một baseline tốt có:

| Nhóm query | Ví dụ | Vì sao quan trọng |
| --- | --- | --- |
| Lookup theo ID | `MATCH (c:Customer {customerId:$id}) RETURN c` | Kiểm tra index seek cho business key |
| Range + sort | Lọc `Order.createdAt`, `totalCents` | Query planner có thể chọn scan + sort khác |
| Traversal một hoặc nhiều bước | `Customer-[:PLACED]->Order-[:CONTAINS]->Product` | Fan-out và join order ảnh hưởng lớn |
| Path finding | Truy vấn đường đi có ràng buộc | Runtime/plan thay đổi có thể làm latency đột biến |
| Aggregation | `count`, `collect`, `DISTINCT`, group-by | Chi phí hàng trung gian, bộ nhớ |
| Batch write | `UNWIND`, `MERGE`, constraint | Lock contention, tx log và thông lượng ghi |
| Full-text/vector search | `SEARCH`/procedure được bản hiện hành hỗ trợ | Provider và semantics có thể thay đổi |

Cho mỗi truy vấn, lưu **text gốc có tham số**, tập tham số đại diện, kết quả kỳ vọng, data distribution, p50/p95/p99, throughput, CPU/heap/GC/page cache, và khi an toàn cả `EXPLAIN`/`PROFILE`.

## 4. Chuyển từ BTREE Neo4j 4.4 sang chỉ mục mới của Neo4j 5

**Điểm chặn kỹ thuật khi chuyển 4.4 → 5:** Neo4j 5 đã loại bỏ kiểu index **BTREE**. Theo hướng dẫn migration chính thức:

- Những index BTREE dùng provider `native-btree-1.0` hoặc `lucene+native-3.0` phải được xử lý **trước khi chuyển sang binary Neo4j 5**.
- Neo4j 5 yêu cầu có **index tương đương cùng schema** ở kiểu `RANGE`, `POINT` hoặc `TEXT` thích hợp trước khi bỏ index BTREE cũ.
- Với **index-backed constraint** legacy, phải có constraint cùng loại trên cùng schema dùng provider **`range-1.0`**, nếu không có thể chặn quá trình khởi động/migration.
- Hướng dẫn khuyến nghị tạo index/constraint thay thế **ngay khi còn ở 4.4** để giảm rủi ro trong cửa sổ nâng cấp.

Không đơn giản “đổi tên BTREE thành RANGE” vì khả năng tìm kiếm của từng index type khác nhau.

### 4.1. Chọn đúng loại index mới

| Mẫu truy vấn Cypher | Index cần cân nhắc | Ví dụ |
| --- | --- | --- |
| So sánh bằng/so sánh thứ tự trên property | **RANGE** | `o.createdAt >= $from` |
| Điều kiện tiền tố/hậu tố/chứa chuỗi phù hợp | **TEXT** | `p.name CONTAINS $term` |
| Property kiểu điểm không gian và phép lọc địa lý | **POINT** | `point.distance(...)` |
| Tìm kiếm toàn văn qua analyzer | **FULLTEXT** | Query full-text theo công cụ và bản hỗ trợ |
| ANN/độ tương đồng vector | **VECTOR** | Embedding search, provider phụ thuộc phiên bản |
| Tìm label/relationship type | **LOOKUP** | Token lookup, không thay thế index property |

Ví dụ trên **Neo4j 5+ lab**:

~~~cypher
CREATE RANGE INDEX order_created_at IF NOT EXISTS
FOR (o:Order) ON (o.createdAt);

CREATE TEXT INDEX product_name_text IF NOT EXISTS
FOR (p:Product) ON (p.name);

CREATE POINT INDEX place_location_point IF NOT EXISTS
FOR (p:Place) ON (p.location);
~~~

**Chỉ tạo index nào được workload thực sự dùng.** Index tăng chi phí ghi, dung lượng disk và công việc population; thêm ba index không có bằng chứng từ `PROFILE` có thể khiến migration chậm mà không cải thiện API.

### 4.2. Constraint gắn với index

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;
~~~

Trên phiên bản hỗ trợ, uniqueness constraint có index hậu thuẫn, giúp vừa **bảo vệ tính duy nhất** vừa hỗ trợ truy vấn equality. Khi di trú constraint cũ, phải xác định index provider/constraint tương đương và **không lỡ bỏ tính bảo vệ dữ liệu**.

**Lưu ý `IF NOT EXISTS`:** Câu lệnh idempotent không chứng minh rằng schema cũ **trùng hoàn toàn tên, loại và provider** mong muốn. Sau khi chạy, phải kiểm tra lại `SHOW CONSTRAINTS` và `SHOW INDEXES`, kể cả constraint được tạo tự động tên.

### 4.3. Khi có quá nhiều BTREE để xử lý thủ công

CLI migration có tùy chọn `--force-btree-indexes-to-range` cho trường hợp **4.4 → 5** (kiểm tra tên cờ trong bản thực tế). Nó ép chuyển các index/constraint BTREE sang RANGE khi cần, nhưng:

- **RANGE không luôn là thay thế tối ưu** cho mọi kiểu truy vấn trước đây.
- Index được tạo lại có thể **population bất đồng bộ sau lần startup**.
- Query có thể chạy theo plan kém hoặc chưa sử dụng index trong lúc chưa `ONLINE`.
- Không dùng cờ để né bước **thiết kế index phù hợp** và kiểm thử correctness/performance.

Ưu tiên đánh giá riêng từng schema quan trọng. Tùy chọn ép chuyển chỉ là phương án điều hành có điều kiện và cần kế hoạch kiểm chứng.

Nguồn: [Breaking changes 4.4 → Neo4j 5](https://neo4j.com/docs/upgrade-migration-guide/current/version-5/migration/breaking-changes/), [Migrate a database](https://neo4j.com/docs/operations-manual/current/database-administration/standard-databases/migrate-database/).

## 5. Index population, provider và trạng thái trước khi mở traffic

Sau upgrade hoặc store migration, một index có thể được khai báo đúng nhưng vẫn đang **`POPULATING`**, hoặc rơi vào `FAILED` vì lỗi dữ liệu/tài nguyên.

~~~cypher
SHOW INDEXES
YIELD name, type, state, populationPercent, indexProvider,
      labelsOrTypes, properties
RETURN name, type, state, populationPercent,
       indexProvider, labelsOrTypes, properties
ORDER BY state, name;
~~~

| Trạng thái | Ý nghĩa vận hành | Có thể mở traffic ngay? |
| --- | --- | --- |
| **`ONLINE`** | Index sẵn sàng được planner cân nhắc | Kiểm tra hiệu năng/plan tiếp |
| **`POPULATING`** | Đang xây index | Không mặc định đạt SLO cho query phụ thuộc index |
| **`FAILED`** | Xây dựng hoặc duy trì index lỗi | Xem failure cause và runbook version; chặn rollout liên quan |

Index population có thể gây **I/O, CPU, page cache pressure và thời gian khởi động database kéo dài**. Không chỉ đếm xem có đủ tên index trong catalog: **readiness của ứng dụng** cần quan sát các index trọng yếu đạt `ONLINE`.

### 5.1. Provider có thể đổi qua release

`indexProvider` cho biết implementation thực tế, ví dụ RANGE `range-1.0`; **VECTOR provider** còn có các thế hệ khác nhau, gồm `vector-2026.08` trong các bản phù hợp. Các index đã tạo trước đó có thể tiếp tục dùng provider cũ, không nhất thiết tự biến thành provider mới sau khi đổi binary.

~~~cypher
SHOW VECTOR INDEXES
YIELD name, type, indexProvider
RETURN name, type, indexProvider;
~~~

Trước khi rebuild một vector index:

- Kiểm tra **dimension**, similarity function, loại property, cấu hình vector và phiên bản provider.
- Đo **recall@k, precision@k, latency, dung lượng** thay vì chỉ xem `ONLINE`.
- Cẩn thận với thay đổi **kết quả xếp hạng gần đúng**; ANN có thể đưa ra top-k khác dù không có bug.
- Chỉ dùng syntax vector phù hợp version; không sao chép cấu hình HNSW của một release rồi áp cho release khác không kiểm tra.

Tương tự, FULLTEXT chịu ảnh hưởng analyzer và dữ liệu, TEXT/POINT/RANGE có semantics riêng. **Không lấy tên index type làm chứng minh tương đương nghiệp vụ.**

## 6. Định dạng lưu trữ: aligned, block, standard, high_limit

**Store format** là cách Neo4j mã hóa node, relationship, property và các record trên filesystem. Nó ảnh hưởng đến **disk layout, page cache I/O, giới hạn entity, tính tương thích khi nâng cấp và chi phí migration**, không chỉ là một setting tùy ý.

| Store format | Đặc điểm khái quát | Phiên bản/edition cần chú ý |
| --- | --- | --- |
| **`aligned`** | Dạng record, cải thiện sử dụng bộ nhớ so với standard; data thường qua cấu trúc record liên kết | Mặc định **Community** hiện hành, Enterprise mới trước 5.22 |
| **`block`** | Đưa dữ liệu property gần node/relationship hơn, cải thiện locality; hỗ trợ quy mô lớn | Có trong **Enterprise**, GA từ 5.16, mặc định database Enterprise mới từ 5.22 |
| **`standard`** | Format record legacy | Bị **deprecated** từ 5.23, cần chuẩn bị rời bỏ theo roadmap |
| **`high_limit`** | Format legacy cho graph có giới hạn entity lớn hơn standard | Enterprise; **deprecated** từ 5.23, lên kế hoạch sang block |

**Không kết luận** “Neo4j 5.26 nghĩa là toàn bộ database đã ở block”. Format của database hiện có có thể vẫn là `aligned`/`standard`/`high_limit`. Tài liệu Neo4j cho biết việc hỗ trợ format cũ sẽ kết thúc trong một lộ trình có mốc LTS; khi quyết định nâng cấp **bản mục tiêu**, phải kiểm tra bản đó còn đọc format cũ hay yêu cầu chuyển trước.

### 6.1. Minor store upgrade vs major format migration

- **Minor format update** trong cùng format có thể được Neo4j nâng tự động lúc startup theo phiên bản hỗ trợ.
- **Major format migration** hoặc **đổi format** giữa `aligned` và `block` cần thao tác `neo4j-admin database migrate` hoặc một quy trình chính thức tương ứng.
- Đổi `db.format=block` trong cấu hình **không tự là lệnh chuyển toàn bộ database đang tồn tại sang block**. Setting có thể ảnh hưởng database tạo mới.
- Trong Enterprise cluster, phải theo **runbook cluster**; không tùy tiện tắt một member rồi chạy migrate in-place khiến các bản sao/metadata mất tương thích.

Tài liệu chính thức: [Store formats](https://neo4j.com/docs/operations-manual/current/database-internals/store-formats/), [Migrate a database](https://neo4j.com/docs/operations-manual/current/database-administration/standard-databases/migrate-database/).

### 6.2. Đổi format là công việc I/O lớn, offline

Trong môi trường **standalone lab**, ví dụ chuyển database `graph_lab` đã được kiểm tra có hỗ trợ sang `block`:

~~~cypher
// Trong database system, chạy bằng tài khoản quản trị.
// Lệnh này làm database đích offline.
STOP DATABASE graph_lab;
~~~

~~~bash
# Trên Neo4j host/lab với binary neo4j-admin đúng version.
# Database đã dừng; có backup và dung lượng đĩa dự phòng.
neo4j-admin database migrate --to-format=block graph_lab
~~~

~~~cypher
// Chỉ sau khi migration thành công và các kiểm tra phù hợp.
START DATABASE graph_lab;
~~~

Điều kiện vận hành:

1. **Backup phục hồi được** và ghi lại trạng thái trước migration.
2. **Dừng database** theo quy trình; không chạy trên một database đang tiếp nhận WRITE.
3. Kiểm tra graph **nằm trong giới hạn entity** của format đích.
4. Có đủ disk cho dữ liệu gốc, dữ liệu sau chuyển đổi, temp files và **index rebuild**.
5. Đo thời gian store rewriting, index population và application readiness, vì **đây là downtime của database**, không chỉ thời gian chạy CLI.
6. Không mở traffic tới database chưa có index/constraint quan trọng sẵn sàng.

Lệnh là **ví dụ cho lab self-managed**; không sử dụng trực tiếp trên Aura và không áp dụng nguyên xi cho multi-server Enterprise cluster.

### 6.3. Thay đổi internal IDs khi đổi format

Khi migration đổi store format, Neo4j có thể **gán lại internal IDs của node và relationship** vì ID phụ thuộc layout vật lý. Do đó:

~~~cypher
// Chỉ dùng để chẩn đoán trong một DB ở thời điểm hiện tại.
MATCH (o:Order {orderId: $orderId})
RETURN elementId(o) AS elementIdNow,
       o.orderId AS businessId;
~~~

**Không dùng `id(n)` hay `elementId(n)` làm ID bền vững xuyên migration, export/restore hoặc API tích hợp.** Thay bằng khóa domain như `Order.orderId`, `Customer.customerId` và uniqueness constraint.

Với ứng dụng Java/Spring Data Neo4j, kiểm tra mapping `@Id`, `@GeneratedValue` và các tham chiếu ngoài database. Nếu hệ thống đã persist internal IDs ở PostgreSQL, Redis hoặc Kafka, đây là **rủi ro migration nghiêm trọng** và có thể cần sửa data model trước khi chuyển format.

## 7. Đổi store format tác động tới kế hoạch truy vấn như thế nào?

Không có quy tắc “đổi sang block là mọi query nhanh hơn”. Một format có thể cải thiện locality với truy vấn nhiều property, nhưng kết quả phụ thuộc graph, index, planner, cache, CPU, I/O và concurrency.

Ví dụ:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
      -[:PLACED]->(o:Order)
RETURN o.orderId AS orderId,
       o.status AS status,
       o.totalCents AS totalCents
ORDER BY o.orderId
LIMIT 30;
~~~

Các nguồn chi phí khác nhau:

| Nguồn chi phí | Điều ảnh hưởng | Khi đổi format cần đo |
| --- | --- | --- |
| Seek node `Customer` | Constraint/index, selectivity, statistics | Có còn `NodeUniqueIndexSeek` hoặc index seek tương tự? |
| Expand `PLACED` | Bậc node, số relationship, data locality | `Rows`, `DB Hits`, page cache faults |
| Đọc thuộc tính `Order` | Layout property, cache | DB Hits, disk I/O và latency |
| `ORDER BY` + `LIMIT` | Số hàng trước sort, index order, planner | Có `Sort` lớn không, query có thể dừng sớm không? |
| Java mapping | Số record/field, network, DTO/SDN entity graph | Bytes transferred, heap Java, response p95 |

Đặc biệt, **`LIMIT 30` ở cuối không đảm bảo Neo4j chỉ duyệt 30 relationship**. Nếu phải sắp xếp hàng chục nghìn order để chọn 30 bản đầu, format mới không sửa một kế hoạch truy vấn sai mục tiêu.

## 8. Kế hoạch truy vấn: EXPLAIN, PROFILE và những gì cần so sánh

`EXPLAIN` lập kế hoạch mà không thực thi phần truy vấn; `PROFILE` **thực thi** truy vấn và cung cấp thống kê thực tế theo toán tử.

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $customerId})
      -[:PLACED]->(o:Order)
RETURN o.orderId AS orderId
ORDER BY o.orderId
LIMIT 20;
~~~

~~~cypher
// Chỉ dùng PROFILE trên query READ khi an toàn.
PROFILE
MATCH (c:Customer {customerId: $customerId})
      -[:PLACED]->(o:Order)
RETURN o.orderId AS orderId
ORDER BY o.orderId
LIMIT 20;
~~~

**Không dùng `PROFILE` với query `DELETE`/`SET` trong production** chỉ để xem plan: nó thực sự ghi dữ liệu nếu transaction được commit.

### 8.1. Đọc plan theo nhóm toán tử

| Operator/metric | Câu hỏi cần hỏi |
| --- | --- |
| `NodeByLabelScan` / `AllNodesScan` | Vì sao planner quét node thay vì dùng index chọn lọc? |
| `NodeIndexSeek` / `NodeUniqueIndexSeek` | Query có tận dụng index theo business key không? |
| `Expand(All)` / `Expand(Into)` | Một node gốc sinh bao nhiêu cạnh/hàng trung gian? |
| `Filter` | Điều kiện lọc được đẩy sớm hay loại bỏ sau traversal lớn? |
| `Sort` / `Top` | Có sort số lượng lớn trước `LIMIT` không? |
| `NodeHashJoin` / `Apply` | Thứ tự join/subquery có gây nhân số hàng? |
| `Eager` | Có materialization lớn vì semantics đọc/ghi không? |
| **`Rows`** | Số hàng thực tế mỗi toán tử là bao nhiêu? |
| **`DB Hits`** | Bao nhiêu lượt truy cập dữ liệu? |
| **Memory/Page cache** | Còn đủ RAM, cache và I/O không? |

Một operator có thể đổi tên hoặc được tối ưu khác giữa các bản Cypher. **Không nhất thiết buộc plan text phải giống 100%**; mục tiêu là correctness, dữ liệu xử lý, độ trễ và tài nguyên nằm trong SLO.

### 8.2. So sánh plan giữa phiên bản như thế nào?

Đối với **cùng query nghiệp vụ**:

1. Dùng **cùng dataset snapshot**, kích thước và phân phối bậc node (nhất là node có hàng nghìn relationship).
2. Giữ nguyên **tham số đại diện**, các index mục tiêu và cùng các giới hạn kết quả.
3. Chụp **query text**, `EXPLAIN`, `PROFILE`, statistics, runtime và provider.
4. Tách kết quả **cold cache** và **warm cache**; chạy đủ lần để tránh một lần khởi động gây thiên lệch.
5. So sánh cả **p50/p95/p99**, throughput và tỷ lệ lỗi dưới concurrency giống nhau.
6. Nếu plan đổi mà kết quả đúng, latency tốt hơn, tải không tăng bất thường, không cần cố ép lại plan cũ.
7. Nếu regression, tìm nguyên nhân (index chưa online, statistics sai lệch, join order, Cypher language, plugin) trước khi thêm hint.

**Mẫu bảng kiểm:**

| Query ID | Chỉ số | Trước nâng cấp | Sau nâng cấp | Gate |
| --- | --- | ---: | ---: | --- |
| Q01 lookup customer | p95 (ms) | 18 | 20 | ≤ 30 |
| Q02 2-hop traversal | p95 (ms) | 140 | 310 | ≤ 200 → **FAIL** |
| Q02 2-hop traversal | DB Hits | 12.000 | 51.000 | Điều tra |
| Q03 order write | p95 (ms) | 40 | 43 | ≤ 75 |
| Q04 search | recall@10 | 0,92 | 0,91 | ≥ 0,90 |

**Các số trên chỉ là dữ liệu giả lập phục vụ bài học**; hãy thay bằng số đo thực tế và điều kiện nghiệp vụ riêng. Q02 FAIL dù database đã online và mọi constraint tồn tại.

## 9. Query plan cache, thống kê và replanning

Neo4j duy trì query plan cache để tránh lập lại plan cho cùng truy vấn. Sau restart/schema change/store migration, kế hoạch có thể cần được lập lại theo **thống kê database mới**.

Nguyên nhân plan thay đổi:

- **Index/constraint thay đổi:** planner có thêm hoặc mất access path.
- **Statistics cardinality/selectivity thay đổi:** số node, relationship, distinct values, density và skew khác snapshot cũ.
- **Cache lạnh:** query cần parse/compile/plan lần đầu sau restart.
- **Planner/runtime cập nhật:** binary mới có lựa chọn join, operator hoặc runtime khác.
- **Ngôn ngữ Cypher mặc định đổi:** semantics và khả năng cú pháp có thể khác.
- **Provider/index state đổi:** index `POPULATING` không được planner dùng như index `ONLINE`.

Theo tài liệu Neo4j, cached plan được cân nhắc replanning khi đủ thời gian và thống kê thay đổi vượt ngưỡng; không phải mọi query được lập lại đồng thời.

### 9.1. Ép lập kế hoạch lại một query trong lab

~~~cypher
// Lệnh EXPLAIN không thực hiện MATCH; chỉ tái lập plan.
CYPHER replan=force
EXPLAIN
MATCH (c:Customer {customerId: $id})
RETURN c.customerId AS id;
~~~

Trong bản Cypher hỗ trợ, `replan=force` bỏ qua cached plan hợp lệ để planner đánh giá lại. Không đồng nghĩa “force chắc chắn query chạy nhanh hơn”; nếu thống kê hoặc index chưa ổn, plan mới vẫn có thể kém.

### 9.2. Làm mới statistics/query caches theo đúng thời điểm

Neo4j có các procedure quản trị liên quan:

~~~cypher
// Xóa query cache, không tự thay đổi dữ liệu graph.
CALL db.clearQueryCaches();
~~~

~~~cypher
// Resample index/statistics theo hỗ trợ của bản đang chạy,
// rồi làm mới cache để các query tiếp theo được plan lại.
CALL db.prepareForReplanning();
~~~

**Không chạy hai lệnh này vô tội vạ trên production**. Resampling index/chuẩn bị replanning có thể tốn tài nguyên và tạo spike latency; các cached plan khác sẽ cần compile lại. Chỉ dùng khi có quyền, hiểu tác động, sau khi index đã ổn định và đã đo rằng stats/plan là nguyên nhân regression. Với 2026.x, kiểm tra procedure/signature tương ứng trước khi tự động hóa.

Nguồn: [Statistics and execution plans](https://neo4j.com/docs/operations-manual/current/performance/statistics-execution-plans/), [Query tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/query-tuning/).

## 10. Cypher 5 và Cypher 25: kiểm tra cả cú pháp lẫn kết quả

Từ Neo4j **2025.06**, người vận hành có thể chọn **Cypher 5** hoặc **Cypher 25** cho các database/truy vấn. Đổi **Neo4j server binary** không đồng nghĩa phải đổi ngay tất cả truy vấn sang Cypher 25.

### 10.1. Kiểm tra ngôn ngữ mặc định của từng database

~~~cypher
// Chỉ ở các version hỗ trợ cột defaultLanguage.
SHOW DATABASES
YIELD name, defaultLanguage
RETURN name, defaultLanguage
ORDER BY name;
~~~

Đối với môi trường self-managed, tên setting:

~~~properties
# neo4j.conf - ảnh hưởng database tạo mới theo semantics version.
db.query.default_language=CYPHER_5
# Hoặc, khi đã đủ điều kiện để chuyển:
# db.query.default_language=CYPHER_25
~~~

Từ Neo4j **2026.02**, `neo4j.conf` phân phối mới **đặt rõ `CYPHER_25`** cho database tạo mới; database đã tồn tại không tự đổi default chỉ vì file cấu hình của server mới. Nếu không khai báo setting, giá trị mặc định cấp cấu hình có thể là `CYPHER_5`. Do vậy hai database cùng máy có thể dùng **default language khác nhau**.

### 10.2. Pin Cypher version cho truy vấn cụ thể

~~~cypher
CYPHER 5
MATCH (c:Customer {customerId: $id})
RETURN c.displayName AS displayName;
~~~

~~~cypher
CYPHER 25
MATCH (c:Customer {customerId: $id})
RETURN c.displayName AS displayName;
~~~

Các ví dụ trên yêu cầu **server hỗ trợ Cypher 25**. Pin version giúp tách hai biến thử nghiệm:

1. So **cùng Cypher 5** giữa binary cũ và mới để kiểm tra planner/runtime thay đổi.
2. So **Cypher 5 với Cypher 25 trên cùng binary mới** để đánh giá migration ngôn ngữ.

Không dùng đồng thời việc **đổi binary, đổi store format, đổi index và đổi default language** rồi xem một regression là do đâu. Phân tầng phép thử cho phép quy trách nhiệm chính xác.

### 10.3. Đổi default language là thay đổi quản trị

Tại phiên bản hỗ trợ:

~~~cypher
// Chỉ minh họa trên database thử nghiệm, tài khoản quản trị thích hợp.
ALTER DATABASE graph_lab
SET DEFAULT LANGUAGE CYPHER 25;
~~~

Trước khi chuyển:

- Kiểm tra sự tương thích cú pháp và hành vi `NULL`, type coercion, tập hàm/procedure, semantics path/aggregation và kết quả order.
- Kiểm tra generated Cypher từ **Spring Data Neo4j**, APOC, GDS và custom Cypher.
- Chụp plan và đo p95/p99 trên các query quan trọng.
- Đặt rollback ngôn ngữ/đổi default trở lại **chỉ khi phiên bản hỗ trợ**, và kiểm tra ứng dụng có phụ thuộc tính năng Cypher 25 mới không.

**Không coi `CYPHER 25` là một compiler flag thuần hiệu năng**. Nó còn mang ngữ nghĩa ngôn ngữ/tính năng; thay đổi cần được QA correctness.

Nguồn: [Select Cypher version](https://neo4j.com/docs/cypher-manual/25/queries/select-version/), [Configure Cypher default version](https://neo4j.com/docs/operations-manual/current/configuration/cypher-version-configuration/).

## 11. Một bài toán thực tế: query traversal sau nâng cấp bị chậm

Giả sử `Customer` có quan hệ `PLACED` tới `Order`, và mỗi `Order` có quan hệ `CONTAINS` tới `Product`:

~~~mermaid
flowchart LR
    C["Customer<br/>customerId"] -->|PLACED| O["Order<br/>createdAt, totalCents"]
    O -->|CONTAINS| P["Product<br/>sku, name"]
~~~

Use case: liệt kê 20 sản phẩm khách hàng gần đây đã mua:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
      -[:PLACED]->(o:Order)
      -[:CONTAINS]->(p:Product)
RETURN p.sku AS sku,
       p.name AS name,
       o.createdAt AS orderTime
ORDER BY orderTime DESC, sku
LIMIT 20;
~~~

Trước upgrade, query p95 = 120 ms. Sau upgrade, p95 = 900 ms. Có thể do:

- Constraint `Customer.customerId` đang `POPULATING` nên planner scan nhiều node.
- Planner chọn join/expand khác vì statistics.
- Có nhiều customer node bậc cao; dữ liệu benchmark sau upgrade phân phối không giống trước.
- `Order.createdAt` chưa có index thích hợp cho query bắt đầu từ Customer.
- Page cache còn lạnh hoặc bị index rebuild chiếm I/O.
- Cypher language và runtime đổi.
- Java client connection pool/TLS/network thay đổi cùng lúc, **không phải DB Hits**.

### 11.1. Quy trình chẩn đoán

1. **Xác nhận correctness**: kết quả gồm đúng 20 sản phẩm/bản ghi và thứ tự hợp đồng.
2. **Xem index state**: `SHOW INDEXES`, đặc biệt constraint `Customer.customerId`.
3. **Đo plan hai phía**: `PROFILE` trên snapshot/param giống nhau, xem seek, expand, sort, DB Hits.
4. **Kiểm tra số hàng trung gian**: 1 khách hàng → 20.000 đơn → 160.000 sản phẩm? Có thể mọi bottleneck nằm ở fan-out trước `LIMIT`.
5. **Tách cache**: benchmark cold/warm; kiểm tra page cache và disk.
6. **Tách ngôn ngữ**: chạy `CYPHER 5` trên version mới trước khi thử `CYPHER 25`.
7. **Thử query shape tốt hơn trong lab**, không vội thêm index hint:

~~~cypher
// Giới hạn tập Order trước khi mở rộng sang Product.
// Ý nghĩa nghiệp vụ thay đổi thành "sản phẩm của 20 đơn mới nhất".
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WITH o
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT 20
MATCH (o)-[:CONTAINS]->(p:Product)
RETURN p.sku AS sku, p.name AS name, o.createdAt AS orderTime
ORDER BY orderTime DESC, sku;
~~~

**Cảnh báo ngữ nghĩa:** Query tối ưu ví dụ đã **đổi hợp đồng**: từ “20 hàng sản phẩm mới nhất” thành “các sản phẩm của 20 đơn mới nhất”. Chỉ được dùng nếu yêu cầu sản phẩm cho phép. Một plan nhanh hơn nhưng trả dữ liệu khác là **regression correctness**, không phải tối ưu thành công.

## 12. Lập kế hoạch thử nghiệm trước/sau: kiểm soát biến

Một kế hoạch thực tế cần tách ít nhất ba thử nghiệm:

| Pha | Server binary | Store format | Index | Cypher version | Mục đích |
| --- | --- | --- | --- | --- | --- |
| **A — Baseline** | Nguồn | Nguồn | Schema nguồn | Nguồn | Ghi correctness + hiệu năng |
| **B — Binary migration** | Đích | Giữ format nếu được hỗ trợ | Chuyển bắt buộc | Pin version tương thích | Cô lập thay đổi binary/planner |
| **C — Store migration** | Đích | Đổi sang `block` nếu phù hợp | Rebuild/populate | Giữ như B | Đo chi phí/lợi ích format |
| **D — Cypher migration** | Đích | Giữ như C | Giữ như C | Đổi sang 25 | Đo khác biệt ngôn ngữ/runtime |

Mỗi pha phải dùng dữ liệu và workload đại diện. Không thực hiện pha C nếu edition hoặc version **không hỗ trợ block**; không thực hiện D nếu ứng dụng chưa cần/chưa hỗ trợ Cypher 25.

### 12.1. Bộ dữ liệu thử nghiệm

- Bản backup/snapshot đã được **đối soát và phục hồi** độc lập.
- Giữ label, relationship type, property distribution, node degree skew, constraint/index.
- Có **high-degree nodes**, nhiều relationship nhiều bước, tập customer có 0/1/hàng nghìn đơn.
- Có các giá trị biên: `null`, thiếu property, chuỗi Unicode, timestamp/timezone, giá trị số lớn.
- Có truy vấn vector/fulltext nếu ứng dụng dùng; không bỏ chúng khỏi benchmark vì “không phải Cypher cơ bản”.

### 12.2. Đo gì?

| Nhóm | Chỉ số | Khi không đạt |
| --- | --- | --- |
| **Correctness** | Số node/relationship, các khóa nghiệp vụ, truy vấn mẫu, tính đúng đường đi | **NO-GO** nếu sai dữ liệu |
| **Schema** | Index/constraint name/type/provider/state, `ONLINE` | **NO-GO** cho query phụ thuộc index chưa sẵn sàng |
| **Performance** | p50/p95/p99, throughput READ/WRITE, DB Hits, Rows, GC, disk | Điều tra/điều chỉnh trước rollout |
| **Stability** | Error rate, timeout, transient retry, pool pending | Không chấp nhận khi vượt SLO |
| **Operations** | Startup/recovery, index rebuild duration, disk peak, backup/restore drill | Không mở traffic khi vượt downtime budget |
| **Integrations** | Java Driver, SDN, APOC/GDS, CDC, Kafka/ETL | Test contract và khả năng retry/rebuild |

**Đừng chỉ đo trung bình**: nếu p50 giữ 10 ms nhưng p99 tăng lên 3 giây, người dùng có thể gặp timeout nhiều hơn đáng kể.

## 13. Java Driver và Spring Data Neo4j trong kế hoạch migration

Một query plan mới không chỉ xuất hiện trong Neo4j Browser. Mã Java có thể phát sinh Cypher khác truy vấn viết tay:

- Spring Data Neo4j repository tạo query để map entity graph, relationship và projection.
- `Neo4jClient`, repository `@Query` và Java Driver có thể dùng các câu Cypher khác nhau cho cùng endpoint.
- Query `RETURN c` có thể map object graph rộng hơn DTO chỉ lấy `c.customerId` và `c.displayName`.
- Java Driver có transaction routing, bookmark, retry và connection pool; các thành phần này ảnh hưởng latency khi migration đổi topology/TLS.

### 13.1. Ví dụ harness kiểm tra lookup qua Java Driver

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class CustomerLookup {
    private final Driver driver;

    public CustomerLookup(Driver driver) {
        this.driver = driver;
    }

    public String findName(String database, String customerId) {
        try (Session session = driver.session(
                SessionConfig.forDatabase(database))) {
            return session.executeRead(tx -> tx.run("""
                    MATCH (c:Customer {customerId: $id})
                    RETURN c.displayName AS name
                    """, Map.of("id", customerId))
                    .single()
                    .get("name")
                    .asString());
        }
    }
}
~~~

Đo **toàn bộ `findName`** trong ứng dụng và kết quả Cypher `PROFILE` riêng. Đối với benchmark nhiều lần, **dùng chung Driver**, mở Session theo request/test case, không tạo/đóng Driver ở mỗi lần đo. Đảm bảo DB đúng tên và dữ liệu test có kết quả, vì `single()` sẽ lỗi nếu 0 hoặc nhiều hàng.

### 13.2. Giao dịch đọc/ghi và retry

Sau nâng cấp, managed transaction `executeRead`/`executeWrite` có thể retry các lỗi transient phù hợp. Trong benchmark/rollout:

- Báo cả **thời gian user chờ sau retry**, không chỉ thời gian một lần Cypher.
- Callback `executeWrite` phải dùng ID ổn định và không gọi external side effects trong callback có thể chạy lại.
- Nếu migration làm thay đổi **internal ID**, code nào lưu ID này qua phiên bản/nguồn ngoài phải được sửa trước.
- Với entity SDN, kiểm tra constructor/id mapping, custom converters, index-backed constraints và repository query.
- Với plugin APOC/GDS, kiểm tra bản JAR/license và signature procedure đúng server đích; **không giả định plugin tương thích chỉ vì ứng dụng kết nối được Bolt**.

### 13.3. Đối soát kết quả JSON/DTO

Không chỉ kiểm tra status HTTP 200. So sánh:

1. Mã khách hàng và mã đơn có đúng không.
2. Số relationship và node được trả về có thay đổi không.
3. Có mất/nhân đôi các phần tử trong danh sách do thứ tự không ổn định không.
4. `null` hoặc property mới/mất có làm Java mapping sai không.
5. Với query không có `ORDER BY`, không được dùng sự trùng thứ tự “tình cờ” làm tiêu chí correctness.

## 14. Lập kế hoạch cutover, backup, rollback và downtime

### 14.1. Tại sao cần restore từ bản trước upgrade?

Neo4j **không hỗ trợ downgrade DBMS đơn giản** bằng cách thay binary về phiên bản cũ sau khi đã nâng cấp/migrate dữ liệu. Kế hoạch rollback phải có:

- **Backup trước migration** được phép restore bằng môi trường/version cũ.
- Lưu cấu hình, secrets, chứng chỉ, plugin, schema scripts và metadata quản trị tương ứng.
- Kịch bản đưa application về endpoint nguồn cũ hoặc phục hồi từ backup vào hệ thống có quyền.
- Đối soát **những WRITE phát sinh sau mốc backup**; nếu rollback data về mốc cũ, có nguy cơ mất những transaction đó.
- RPO/RTO và thông tin truyền thông khi phải dừng hoặc chuyển traffic.

**Không ghi dữ liệu mới vào database sau migration rồi chỉ chuyển binary ngược về 4.4/5 cũ.** Đây có thể là đường đi không tương thích format và gây mất dữ liệu.

### 14.2. Mẫu trình tự cutover có kiểm soát

~~~mermaid
flowchart TD
    B["Backup trước nâng cấp + thử restore"] --> F["Freeze schema / plugin version"]
    F --> L["Migration rehearsal trên bản copy"]
    L --> G{"Đạt index + correctness + performance?"}
    G -->|Không| R["Chặn rollout, sửa schema/query"]
    G -->|Có| D["Chọn maintenance / cutover window"]
    D --> S["Quiesce writes theo runbook"]
    S --> U["Upgrade/migrate theo hướng dẫn"]
    U --> I["Index ONLINE + DB online"]
    I --> T["Smoke test + query benchmark"]
    T --> X{"Release gates đạt?"}
    X -->|Có| O["Mở traffic theo giai đoạn"]
    X -->|Không| Q["Rollback/restore theo playbook"]
~~~

**Quiesce writes** là bước quan trọng nếu cutover chuyển sang một bản copy: cần đảm bảo không bỏ sót những thay đổi đã commit khi snapshot được chụp. Với môi trường cluster, có thể có lộ trình rolling upgrade do version hỗ trợ, nhưng không tự áp dụng quy trình standalone/offline migration vào cụm. Hướng dẫn 4.4 → 5 là migration lớn, không chỉ rolling restart tất cả server.

### 14.3. Tài nguyên cần dự trù

| Tài nguyên | Vì sao cần |
| --- | --- |
| **Disk** | Giữ bản cũ và bản chuyển đổi, temp files, transaction logs và index rebuilt |
| **CPU** | Rewriting store, index population, query benchmark |
| **RAM/heap/page cache** | Migration/recovery, cache cold/warm, GDS/plugin nếu dùng |
| **Network** | Chuyển backup/copy/seed database trong cluster |
| **Downtime** | Dừng DB, migrate store, rebuild index, smoke test, rollback buffer |
| **Nhân sự** | DBA, application owner, SRE/on-call, phụ trách dữ liệu và quyết định go/no-go |

**Giá trị thời gian ước lượng từ file 100 GB nhỏ không áp dụng tuyến tính lên graph 1 TB**: index count, quan hệ bậc cao, loại storage và I/O contention đều có thể kéo dài thời gian.

## 15. Kiểm tra graph và schema sau migration

Chạy trên database **đã phục hồi/di trú**, không phải `system` nếu muốn đếm dữ liệu graph.

### 15.1. Node, relationship và các ràng buộc nghiệp vụ

~~~cypher
MATCH (c:Customer)
RETURN count(c) AS customerCount;
~~~

~~~cypher
MATCH (o:Order)
RETURN count(o) AS orderCount;
~~~

~~~cypher
MATCH (:Customer)-[r:PLACED]->(:Order)
RETURN count(r) AS placedRelationshipCount;
~~~

~~~cypher
SHOW CONSTRAINTS;
~~~

Các truy vấn đếm có thể tốn tài nguyên với graph lớn; dùng snapshot thống kê, sampling hoặc kiểm tra theo batch khi thích hợp. **Số lượng bằng nhau không đủ** chứng minh graph đúng: hai node có thể đổi relationship, thiếu property hoặc có key trùng bị che ở tổng số.

### 15.2. Đối soát theo business key và đường đi

~~~cypher
MATCH (c:Customer {customerId: $customerId})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN c.customerId AS customerId,
       count(DISTINCT o) AS orderCount;
~~~

~~~cypher
MATCH (o:Order {orderId: $orderId})
OPTIONAL MATCH (owner:Customer)-[:PLACED]->(o)
RETURN o.orderId AS orderId,
       o.status AS status,
       o.totalCents AS totalCents,
       collect(DISTINCT owner.customerId) AS ownerIds;
~~~

Kiểm tra nhiều loại key, đặc biệt:

- Node có nhiều relationship, node cô lập và những node được tạo gần thời điểm backup.
- Relationship có property và hướng được dùng để truy vấn đường đi.
- Constraint uniqueness, existence/type khi edition hỗ trợ.
- Temporal, spatial, list, large string và trường Unicode quan trọng.
- Index/các loại search và số kết quả đúng theo truy vấn nghiệp vụ.

### 15.3. Kiểm tra consistency vật lý

Neo4j cung cấp công cụ `neo4j-admin database check` và các chế độ kiểm tra phù hợp với version. Việc chạy thường cần điều kiện **database offline hoặc backup/dump artifact** tùy lệnh. Không chạy với flag tùy ý trên production đang online; đọc hướng dẫn của bản đích và chạy trên copy/backup:

~~~text
Kiểm tra 1: artifact backup có đủ chuỗi và metadata.
Kiểm tra 2: restore/copy thành công trên Neo4j test.
Kiểm tra 3: consistency checker không phát hiện hỏng store.
Kiểm tra 4: Cypher đối soát business key, index/constraint.
Kiểm tra 5: Java/Spring integration và latency đạt SLO.
~~~

Consistency checker **không thể chứng minh mọi nghiệp vụ đúng**. Một graph mất 50 cạnh `PLACED` nhưng vẫn hợp lệ về mặt cấu trúc store là ví dụ cần đối soát ở application.

## 16. Các lỗi và hướng chẩn đoán phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Neo4j 5 không khởi động database 4.4 | Index BTREE/constraint provider legacy chưa được xử lý, store migration chưa đúng | Xem log migration, `SHOW INDEXES/CONSTRAINTS` tại bản nguồn và hướng dẫn 4.4 → 5 |
| Sau upgrade lookup chậm | Index `POPULATING`/`FAILED`, planner scan, cache lạnh | `SHOW INDEXES`, `EXPLAIN/PROFILE`, page cache |
| Query dùng TEXT trước đây đổi kết quả | Index type/provider hoặc semantics search khác | Kiểm thử hành vi contains/startsWith/fulltext và dữ liệu Unicode |
| Query p99 tăng dù index `ONLINE` | Statistics, plan/join order, runtime, data skew, network | So `Rows`, `DB Hits`, client pool và cache |
| Store migration báo thiếu disk | Đổi format cần rewrite cả store và repopulate index | Capacity, backup size, temp path, disk peak |
| `elementId` khác sau migration | Nội bộ ID được gán lại khi đổi format | Chuyển sang business key, đối soát references |
| Database mới dùng Cypher 25, DB cũ dùng Cypher 5 | Setting mặc định theo database và template config mới | `SHOW DATABASES YIELD name, defaultLanguage` |
| Vector index vẫn dùng provider cũ | Provider không nhất thiết tự update cùng binary | `SHOW VECTOR INDEXES`, plan và recall@k |
| Java Driver kết nối OK nhưng repository lỗi | Generated query/driver/SDN/plugin signature không tương thích | Integration tests, logs, dependency matrix |
| Rollback bằng binary cũ thất bại | Downgrade trực tiếp không hỗ trợ | Phục hồi backup trước upgrade theo playbook |
| Index rebuild xong nhưng query vẫn scan | Predicate không phù hợp index, stats/plan hoặc label mismatch | Kiểm tra schema, tham số, `EXPLAIN` và query shape |
| Cluster sau nâng cấp không ghi được | Mất quorum, discovery/routing hoặc phiên bản server không tương thích | Cluster runbook, `SHOW SERVERS/DATABASES`, network |

### 16.1. Khi nào nên rollback thay vì tiếp tục tối ưu?

**NO-GO/rollback** nếu:

- Database không online hoặc không qua consistency check theo quy trình.
- Có sai lệch business key, relationship, property hoặc constraint quan trọng.
- Index trọng yếu vẫn `FAILED` hoặc không thể hoàn thành population trong downtime budget.
- API ghi không commit đúng, duplicate/constraint issue hoặc retry gây side effect.
- p95/p99 và error rate vượt SLO nghiêm trọng, chưa có cách xử lý an toàn.
- Chưa có bản backup/restore có thể tin cậy, hoặc cluster không đủ quorum sau rollout.

**Không** đóng sự cố chỉ vì `SHOW DATABASES` trả `online` nếu correctness và SLO chưa đạt.

## 17. Bài thực hành: đánh giá index, format và plan trước–sau nâng cấp

### 17.1. Bối cảnh

Nhóm có Neo4j **4.4 Enterprise**, database `sales_graph` chứa `Customer -[:PLACED]-> Order` và ứng dụng Spring Data Neo4j. Dự án muốn lên bản có hỗ trợ `block` và xem xét `CYPHER 25` khi phù hợp. Dự án có constraint `Customer.customerId`, index trên `Order.createdAt`, query lấy đơn gần nhất và một job `UNWIND` ghi theo batch.

**Không cần thực sự nâng cấp production trong bài tập.** Hãy sử dụng database lab hoặc bản backup phục hồi riêng để thực hành kiểm tra.

### Bước 1 — Lập danh mục thay đổi

Tạo bảng:

| Hạng mục | Baseline 4.4 | Target | Điều kiện PASS |
| --- | --- | --- | --- |
| DBMS/driver | Version cụ thể | Version đã duyệt | Kết nối/TLS/auth đúng |
| BTREE index | Tên, provider, schema | RANGE/TEXT/POINT thích hợp | Không còn legacy chặn migration |
| Uniqueness constraint | `Customer.customerId` | Constraint tương đương | Không có duplicate |
| Store format | Format hiện tại | Giữ hoặc chuyển block theo kế hoạch | Đã thử migrate và biết downtime |
| Cypher | Query cũ | Pin Cypher 5; cân nhắc 25 | Kết quả bằng nhau |
| Query plan | Rows/DB Hits, p95 | Plan/runtime mới | Không vượt performance gate |

### Bước 2 — Chụp schema và dữ liệu

~~~cypher
SHOW INDEXES;
SHOW CONSTRAINTS;
~~~

Chụp thêm số lượng node/relationship, một số `Customer` có 0, 10, 10.000 order, thông tin provider và state.

### Bước 3 — Chuyển index legacy trong lab

Xác định BTREE nào thuộc lookup equality, TEXT search, POINT geography và loại constraint được backing. Dùng hướng dẫn 4.4 để tạo index tương đương **trước migration**, xác minh online; **không** tự drop uniqueness constraint đang bảo vệ dữ liệu.

### Bước 4 — Di trú và cân nhắc format

Backup trước, chuyển sang Neo4j đích bằng quy trình chính thức. Chạy thử **một pha giữ format hiện tại** trước; nếu Enterprise/target hỗ trợ và có đủ disk/downtime, tiến hành **pha riêng** chuyển sang `block` trên bản copy bằng `neo4j-admin database migrate --to-format=block`. Ghi lại thời gian CLI, thời gian population và thời gian đến khi ứng dụng sẵn sàng.

### Bước 5 — So sánh hai query

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $id})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT 20;
~~~

~~~cypher
PROFILE
MATCH (c:Customer {customerId: $id})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT 20;
~~~

So sánh dữ liệu tương đương, tham số customer bậc thấp/cao, `Rows`/`DB Hits`, index seek/scan, `Sort`, p95/p99 dưới concurrency xác định.

### Bước 6 — Thử lựa chọn Cypher 5/25

Trên server đích **có hỗ trợ** cả hai:

~~~cypher
CYPHER 5
MATCH (o:Order {orderId: $orderId})
RETURN o.status AS status, o.totalCents AS totalCents;
~~~

~~~cypher
CYPHER 25
MATCH (o:Order {orderId: $orderId})
RETURN o.status AS status, o.totalCents AS totalCents;
~~~

Thử với cùng tham số và dataset; ghi lại kết quả và plan. Nếu đổi version ngôn ngữ làm query lỗi, giữ `CYPHER 5` cho use case đó và tạo ticket migration cú pháp trước khi đổi default database.

### Bước 7 — Tạo báo cáo go/no-go

~~~text
Target Neo4j version: ...
Edition / store format before -> after: ...
Indexes: total / ONLINE / POPULATING / FAILED
Constraints: before vs after
Data consistency: PASS / FAIL
Cypher 5 correctness: PASS / FAIL
Cypher 25 compatibility: PASS / FAIL / NOT APPLICABLE
Query p95/p99 regression: ...
Worst DB Hits / Rows increase: ...
Startup + index population + cutover time: ...
Restore drill before migration: PASS / FAIL
Go/No-Go: ...
Owner + timestamp + rollback point: ...
~~~

### Câu hỏi tự kiểm tra

**1. Chỉ đổi `db.format=block` và restart có làm mọi database Enterprise cũ thành block không?**

Không. Existing databases giữ format trừ khi có migration theo quy trình hỗ trợ; đổi format lớn thường là công việc offline.

**2. Vì sao migration từ Neo4j 4.4 sang 5 cần kiểm tra BTREE trước?**

Vì BTREE legacy bị loại bỏ và cần index/constraint tương đương theo quy định migration; nếu còn dạng không được hỗ trợ, database có thể không khởi động.

**3. Sau migration, `SHOW INDEXES` đủ tên nhưng tất cả đang `POPULATING`. Có nên mở traffic ngay không?**

Không mặc định. Các query phụ thuộc index có thể chưa đạt SLO; cần quan sát population/`ONLINE` và smoke test.

**4. `EXPLAIN` và `PROFILE` khác nhau thế nào?**

`EXPLAIN` lập kế hoạch mà không thực thi query; `PROFILE` chạy query thật để thu Rows/DB Hits và thống kê. PROFILE của lệnh ghi có tác dụng ghi nếu commit.

**5. Nếu server 2026.x chạy Cypher 25 mặc định cho DB mới, DB cũ có tự chuyển sang 25?**

Không. Cần kiểm tra default language của từng database và chính sách config; existing databases có thể giữ Cypher 5.

**6. Vì sao không nên dùng `elementId` trong API lưu ngoài Neo4j?**

Vì internal IDs có thể đổi khi chuyển store format; khóa nghiệp vụ ổn định và constraint mới phù hợp để tham chiếu lâu dài.

**7. Query plan đổi nhưng p95 thấp hơn và kết quả đúng. Có phải lỗi nâng cấp?**

Không nhất thiết. Mục tiêu là correctness, latency và tài nguyên; khác tên/operator không tự là regression.

**8. Có thể rollback bằng cách thay binary về bản cũ sau khi di trú database không?**

Không được giả định. Neo4j không hỗ trợ downgrade trực tiếp; thường cần phục hồi backup trước migration và xử lý WRITE phát sinh sau mốc.

## 18. Checklist release readiness

- [ ] Xác định **source/target version, edition, migration path** theo tài liệu Neo4j chính thức.
- [ ] Tách **binary upgrade**, **store migration**, **index migration** và **Cypher language change** thành các pha có thể đo riêng.
- [ ] Ghi baseline **SHOW DATABASES/INDEXES/CONSTRAINTS**, store format, size và các query trọng yếu.
- [ ] Đối với 4.4 → 5, xử lý **BTREE legacy và index-backed constraints** theo migration guide.
- [ ] Chọn RANGE/TEXT/POINT/FULLTEXT/VECTOR theo **predicate và semantics**, không đổi tên máy móc.
- [ ] Kiểm tra index state **ONLINE**, provider, populationPercent và failures.
- [ ] Kiểm tra format **aligned/block/standard/high_limit** của từng database, nhất là format deprecated.
- [ ] Đảm bảo đổi format có backup, đủ disk/temp, thời gian offline và thời gian repopulate index.
- [ ] Không sử dụng internal ID hoặc `elementId` như khóa bền vững xuyên migration.
- [ ] Chụp `EXPLAIN`/`PROFILE`, Rows/DB Hits, cache, CPU, GC và p95/p99 cho nhiều giá trị tham số.
- [ ] So sánh riêng **Cypher 5** và **Cypher 25**, xem default language từng database.
- [ ] Kiểm thử Java Driver, Spring Data Neo4j, plugin APOC/GDS, CDC và batch import nếu dùng.
- [ ] Có tập kiểm thử correctness về node, relationship, constraint, path, DTO và dữ liệu biên.
- [ ] Dùng snapshot đại diện, benchmark cold/warm và workload đọc/ghi đồng thời.
- [ ] Đặt **go/no-go gates** cho dữ liệu, hiệu năng, thời gian downtime và khả năng ghi.
- [ ] Backup/restore drill trên môi trường độc lập; có rollback **bằng restore**, không chỉ đổi binary.
- [ ] Trong cluster, làm theo runbook rolling/migration đúng phiên bản và đảm bảo quorum.
- [ ] Sau cutover, theo dõi p95/p99, errors, query plans, index population, replication và rollback window.

## Tài liệu tham khảo chính thức

- [Neo4j Upgrade and Migration Guide](https://neo4j.com/docs/upgrade-migration-guide/current/)
- [Breaking changes between Neo4j 4.4 and 5 — Indexes](https://neo4j.com/docs/upgrade-migration-guide/current/version-5/migration/breaking-changes/)
- [Migrate a database / neo4j-admin database migrate](https://neo4j.com/docs/operations-manual/current/database-administration/standard-databases/migrate-database/)
- [Store formats and migration paths](https://neo4j.com/docs/operations-manual/current/database-internals/store-formats/)
- [Cypher — Show indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/list-indexes/)
- [Cypher — Query tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/query-tuning/)
- [Neo4j Operations — Statistics and execution plans](https://neo4j.com/docs/operations-manual/current/performance/statistics-execution-plans/)
- [Cypher 25 — Select Cypher version](https://neo4j.com/docs/cypher-manual/25/queries/select-version/)
- [Neo4j Operations — Configure default Cypher version](https://neo4j.com/docs/operations-manual/current/configuration/cypher-version-configuration/)
- [Cypher — Vector indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-indexes/vector-indexes/)
- [Neo4j Java Driver Manual](https://neo4j.com/docs/java-manual/current/)
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/)

**Kết luận:** Nâng cấp Neo4j an toàn đòi hỏi **đánh giá đồng thời chỉ mục, định dạng lưu trữ và kế hoạch truy vấn**, không chỉ thay binary thành công. Với 4.4 → 5 phải xử lý BTREE legacy; với Enterprise hiện đại cần hiểu khi nào nên chuyển sang `block`, chi phí offline và tác động tới internal ID/index; với các bản từ 2025.06 cần kiểm tra **Cypher 5/25** và tính đúng của query. **Baseline, dry run, index ONLINE, đối soát graph, benchmark thực tế và backup có thể restore** là các điều kiện để quyết định phát hành hoặc rollback một cách có căn cứ.

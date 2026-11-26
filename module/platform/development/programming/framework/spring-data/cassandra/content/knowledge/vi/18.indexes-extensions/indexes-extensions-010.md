# Triển khai chỉ mục, chờ sẵn sàng và quan sát ảnh hưởng lên tải

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **vì sao cần chỉ mục trong Apache Cassandra**, khi nào truy vấn theo partition key là lựa chọn tốt hơn, và vì sao một index không biến Cassandra thành hệ quản trị quan hệ cho phép lọc tùy ý.
- Phân biệt **secondary index truyền thống (2i)**, **Storage-Attached Index (SAI)** và các cơ chế mở rộng theo phiên bản/nhà phân phối; không sử dụng cú pháp index ngoài khả năng của cluster.
- Lập kế hoạch triển khai chỉ mục với dữ liệu đang hoạt động: kiểm tra phiên bản, schema, selectivity, replication factor, topology, lưu lượng ghi/đọc, dung lượng đĩa và ngân sách tài nguyên.
- Hiểu ba trạng thái riêng biệt: **DDL được chấp nhận**, **schema được các node biết**, và **dữ liệu cũ đã được xây dựng vào chỉ mục và đường truy vấn sẵn sàng**.
- Viết CQL tạo/chẩn đoán index, triển khai bằng migration có kiểm soát và giữ ứng dụng **chưa chuyển lưu lượng thật** cho đến khi xác minh đầy đủ.
- Quan sát ảnh hưởng đến read latency, write latency, CPU, heap/GC, disk I/O, compaction, dung lượng index, timeouts, unavailable, tombstone và khả năng chịu tải.
- Tích hợp query indexed vào **Spring Data Cassandra repository**, **CassandraTemplate** hoặc Java Driver nhưng vẫn ràng buộc hợp đồng truy vấn, consistency, paging và retry.
- Thiết kế canary, tiêu chí dừng, rollback, tái xây dựng index khi có hướng dẫn phù hợp, và phương án thay thế bằng **bảng dữ liệu thiết kế theo truy vấn**.
- Vận dụng một runbook để triển khai index lên môi trường staging/production mà không nhầm “CREATE INDEX thành công” với “không ảnh hưởng hiệu năng”.

Bài nằm trong chương **Chỉ mục và mở rộng** của **SPRING_DATA_CASSANDRA**. Mô-đun này học truy cập Apache Cassandra bằng Spring Data Cassandra với entity mapping, repository, CassandraTemplate, CQL, partition key, consistency level, paging và kiểm soát hiệu năng trong hệ thống phân tán. Với Cassandra, chỉ mục là một công cụ cho **những đường đọc cụ thể**, không phải lối tắt thay cho thiết kế partition key, clustering key và mô hình dữ liệu theo truy vấn.

> **Nguyên tắc điều hành:** `CREATE INDEX` hoàn tất không có nghĩa cluster đã dựng xong toàn bộ index cho dữ liệu hiện hữu, và cũng không có nghĩa query mới đủ nhanh dưới tải thực. Phải kiểm chứng schema, trạng thái build trên các node liên quan, kết quả truy vấn và tác động lên hệ thống trước khi bật đường đọc mới.

## 1. Vì sao Cassandra cần suy nghĩ khác về chỉ mục?

Trong RDBMS, ứng dụng thường thiết kế bảng chuẩn hóa rồi thêm B-tree index để tối ưu những điều kiện `WHERE` / `ORDER BY`. Cassandra ưu tiên **đặt các hàng thường được đọc cùng nhau vào cùng partition** và dùng clustering columns để hỗ trợ thứ tự bên trong partition đó.

Ví dụ hệ thống sản phẩm có bảng gốc:

~~~sql
CREATE TABLE products_by_id (
    product_id uuid PRIMARY KEY,
    brand text,
    category text,
    price decimal,
    status text,
    updated_at timestamp
);
~~~

Query hiệu quả nhất của bảng là tra cứu theo `product_id`:

~~~sql
SELECT product_id, brand, category, price, status
FROM products_by_id
WHERE product_id = ?;
~~~

Nhưng nếu yêu cầu mới là:

> “Xem những sản phẩm thuộc một thương hiệu, có thể lọc thêm danh mục.”

thì query chỉ chứa `brand` không có partition key:

~~~sql
SELECT product_id, brand, category, price
FROM products_by_id
WHERE brand = ?;
~~~

Nếu không có chỉ mục/đường truy cập hỗ trợ, Cassandra thường không thực thi truy vấn như cách một hệ quan hệ với index B-tree có thể làm. Tùy cú pháp và schema, server từ chối hoặc đòi cơ chế lọc/quét phù hợp; **`ALLOW FILTERING` không phải giải pháp mặc định**.

Có hai hướng:

1. **Bảng đọc riêng:** `products_by_brand` với `brand` làm partition key (có thể bucket/shard khi thương hiệu có rất nhiều sản phẩm) và clustering theo nhu cầu UI.
2. **Chỉ mục được hỗ trợ:** thêm index trên `brand` của bảng gốc khi kiểu truy vấn, độ chọn lọc, tỷ lệ ghi/đọc và kích thước dữ liệu phù hợp.

Chọn giữa hai hướng phụ thuộc câu hỏi nghiệp vụ, SLA, lượng dữ liệu, độ chọn lọc và khả năng vận hành. Index không tự tạo thứ tự sắp xếp toàn cluster hay giảm số partition cần đọc cho mọi kiểu query.

### 1.1. Ba đường đọc, ba chiến lược

| Đường truy vấn | Bảng theo truy vấn | Index bổ sung | Nhận xét |
| --- | --- | --- | --- |
| Chi tiết sản phẩm theo `product_id` | Rất phù hợp với `products_by_id` | Không cần | Partition key trực tiếp |
| Sản phẩm theo `brand`, lượng trả có giới hạn | Có thể làm `products_by_brand` | Có thể xem xét SAI | Đo số kết quả và fan-out |
| Top 20 sản phẩm của thương hiệu theo `updated_at DESC` | Bảng partition theo thương hiệu, clustering theo thời gian | Index trên `brand` **không đủ** tạo thứ tự global | Cần access pattern với thứ tự rõ |
| Báo cáo `COUNT(*)` mọi sản phẩm theo trạng thái | Aggregate/read model riêng | Không nên suy index làm COUNT miễn phí | Có thể tốn quét dữ liệu |
| Tìm kiếm full-text có relevance ranking, typo tolerance | Search system chuyên dụng | Không suy index CQL tương đương search engine | Khả năng phụ thuộc công nghệ |

**Quy tắc:** Hãy viết query cần phục vụ trước. Nếu query là đường đọc cốt lõi với throughput cao, độ trễ thấp và thứ tự cố định, một bảng được thiết kế riêng thường là lựa chọn dễ dự báo hơn. Index hợp lý khi thực sự hỗ trợ một điều kiện lọc cụ thể mà chi phí vận hành chấp nhận được.

## 2. Các cơ chế chỉ mục: 2i, SAI và mở rộng

Cassandra có nhiều thế hệ/cơ chế chỉ mục. Tên và khả năng hỗ trợ có thể phụ thuộc **Apache Cassandra version**, distribution và cấu hình cluster. Không copy cú pháp từ tài liệu của một phiên bản khác rồi triển khai vào production.

| Cơ chế | Khái quát | Điểm cần lưu ý |
| --- | --- | --- |
| Secondary index truyền thống (2i) | Index phía node cho giá trị cột | Query liên quan nhiều partition/độ chọn lọc thấp có thể làm fan-out và chậm |
| Storage-Attached Index (SAI) | Chỉ mục gắn với mô hình lưu SSTable, được thiết kế phục vụ nhiều điều kiện tìm/lọc hiệu quả hơn trong phạm vi hỗ trợ | Cần cluster thực sự hỗ trợ, theo dõi build/compaction, footprint và concurrency |
| SASI / các extension cũ | Cơ chế mở rộng theo phiên bản, có giới hạn/trạng thái hỗ trợ khác nhau | Không chọn làm mặc định cho triển khai mới khi chưa xác minh support/lifecycle |
| Index/vector/search của distribution | Có thể bổ sung API và semantics riêng | Chỉ dùng khi đúng bản phân phối, version và workload |

Trong các phiên bản Apache Cassandra hiện đại có **SAI**, nó là ứng viên thường được xem xét cho truy vấn indexed mới. Tuy nhiên, **SAI không phải chức năng có mặt ở mọi cluster cũ**. Ví dụ trong bài sử dụng cú pháp `StorageAttachedIndex` với điều kiện môi trường hỗ trợ; cần kiểm tra document và cấu hình của bản Cassandra đang dùng.

### 2.1. 2i và SAI không phải cùng một DDL

Ví dụ secondary index thông thường:

~~~sql
-- Cơ chế secondary index truyền thống ở các phiên bản hỗ trợ:
CREATE INDEX IF NOT EXISTS product_brand_2i
ON catalog.products_by_id (brand);
~~~

Ví dụ SAI:

~~~sql
-- Chỉ chạy khi phiên bản Apache Cassandra hỗ trợ SAI:
CREATE CUSTOM INDEX IF NOT EXISTS product_brand_sai
ON catalog.products_by_id (brand)
USING 'StorageAttachedIndex';
~~~

Đây là **hai phương án minh họa thay thế nhau** cho cùng một mục tiêu, không phải hai lệnh phải chạy đồng thời lên một cột. Đặt tên index rõ ràng giúp kiểm soát migration và rollback. `IF NOT EXISTS` tránh lỗi do tên đã tồn tại trong một số trường hợp, nhưng **không chứng minh định nghĩa index hiện tại giống định nghĩa bạn muốn**: cần đối chiếu metadata.

### 2.2. Không phải mọi cột/biểu thức đều được index giống nhau

Khả năng index phụ thuộc kiểu CQL (scalar, collection, UDT, frozen, vector...), dạng điều kiện (equality, range, contains...) và phiên bản index implementation. Một index trên `brand text` không đồng nghĩa:

- Có thể lọc mọi toán tử CQL trên mọi column.
- Có `LIKE '%text%'`, full-text ranking, stemming và typo correction như search engine.
- Có global `ORDER BY price ASC` hoặc `ORDER BY updated_at DESC`.
- Có thể join bảng hoặc áp dụng aggregate tùy ý.
- Có thể đọc phần tử bất kỳ của collection/UDT mà không có cú pháp/hỗ trợ phù hợp.

Với vector search, geo search hoặc collection phức hợp, cần kiểm tra khả năng tương thích của **Cassandra server, driver, Spring Data mapping và cú pháp CQL**; không suy rằng cứ có index là query bất kỳ sẽ hợp lệ.

## 3. Lập kế hoạch trước khi CREATE INDEX

Trước khi chạy migration, lập một bảng đánh giá cho query cụ thể. Ví dụ:

~~~text
Business requirement:
  Tìm các sản phẩm theo brand trên bảng products_by_id

Current path:
  Chỉ tra cứu product_id hiệu quả

Proposed path:
  SELECT ... FROM products_by_id WHERE brand = ? LIMIT 20

Possible alternative:
  products_by_brand với partition theo brand/bucket và clustering phù hợp

Safety question:
  Tạo và build index sẽ ảnh hưởng bao nhiêu tới cluster đang ghi?
~~~

### 3.1. Thu thập những thông tin tối thiểu

| Nhóm thông tin | Câu hỏi |
| --- | --- |
| Phiên bản/phân phối | Cluster đang dùng bản Cassandra nào? Có SAI hay không? |
| Topology | Bao nhiêu DC, node, rack, RF? Node nào đang down/đang bootstrap? |
| Schema | Tên keyspace, table, cột, kiểu, primary key, index hiện có? |
| Dung lượng | Rows/SSTable/bytes, kích thước partition, TTL và lượng tombstone? |
| Độ chọn lọc | Brand phổ biến nhất khớp bao nhiêu rows? Long tail ra sao? |
| Workload | Read QPS, write QPS, p95/p99, lưu lượng giờ cao điểm? |
| Tài nguyên | Disk free, CPU, heap/GC, compaction backlog, disk throughput? |
| SLA | Query mới có latency mục tiêu nào, ảnh hưởng tối đa lên traffic cũ? |
| Migration | Ai kiểm soát schema, có cửa sổ chạy thử, feature flag và rollback không? |
| Quyền | Account migration có quyền `CREATE INDEX` trong keyspace? |

Độ chọn lọc rất quan trọng. Nếu giá trị `brand='POPULAR'` khớp hàng triệu partition, `LIMIT 20` không tự biến query thành giá rẻ trong mọi tình huống: tìm các match đầu có thể vẫn liên quan nhiều đoạn index, node/replica, hay filtering/consistency. Đặc biệt, index trên trường có ít giá trị như `status='ACTIVE'` có thể tạo kết quả rất lớn.

Ngược lại, nếu lookup theo `external_reference` gần như duy nhất, chỉ mục có thể phục vụ query hạn chế nhưng một **bảng theo reference** vẫn đáng cân nhắc nếu đó là đường đọc quan trọng ở QPS cao.

### 3.2. Lấy baseline trước thay đổi

Không chỉ đo query mới. Khi build index, ngay cả traffic cũ cũng có thể bị ảnh hưởng do tài nguyên dùng chung.

Baseline nên gồm:

- Latency p50/p95/p99 và timeout của các truy vấn **cũ**.
- Throughput đọc/ghi, mức đồng thời/in-flight của driver.
- CPU, heap, GC pauses, read/write IOPS, bandwidth của ổ đĩa.
- Compaction backlog, pending tasks, disk free, tombstone cảnh báo.
- Read/write latency ở node/coordinator, unavailable và dropped messages.
- Tài nguyên theo từng DC/node để tránh chỉ nhìn trung bình cluster.

Ghi rõ thời gian đo và cường độ tải. Không so sánh p99 giờ vắng khách trước migration với p99 giờ cao điểm sau migration rồi quy toàn bộ khác biệt cho index.

### 3.3. Cần có stop condition trước khi bắt đầu

Ví dụ nguyên tắc vận hành:

> “Nếu p99 của đường đọc quan trọng, timeout rate hoặc compaction backlog vượt ngưỡng đã được đội vận hành phê duyệt trong thời gian quan sát, không mở thêm lưu lượng indexed; dừng rollout và điều tra.”

Không bịa số ngưỡng cố định cho mọi cluster. Hạn mức CPU, disk, latency và error budget phải được xác định từ baseline, SLA và capacity thật.

## 4. Chuẩn bị schema và tạo SAI

Giả sử staging có Cassandra hỗ trợ SAI và keyspace `catalog` đã được tạo với replication phù hợp topology. Tạo bảng minh họa:

~~~sql
CREATE TABLE IF NOT EXISTS catalog.products_by_id (
    product_id uuid PRIMARY KEY,
    brand text,
    category text,
    price decimal,
    status text,
    updated_at timestamp
);
~~~

Truy vấn chi tiết theo key:

~~~sql
SELECT product_id, brand, category, price, status
FROM catalog.products_by_id
WHERE product_id = ?;
~~~

Để thử query theo `brand`, tạo SAI:

~~~sql
CREATE CUSTOM INDEX IF NOT EXISTS product_brand_sai
ON catalog.products_by_id (brand)
USING 'StorageAttachedIndex';
~~~

**Quan trọng:** DDL trên chỉ dùng khi server hỗ trợ index class `StorageAttachedIndex`. Ở môi trường không hỗ trợ, phải dừng hoặc dùng giải pháp được version đó hỗ trợ; không thay thế bằng `ALLOW FILTERING` để giữ nguyên hợp đồng hiệu năng.

### 4.1. Query cần index

~~~sql
SELECT product_id, brand, category, price, status
FROM catalog.products_by_id
WHERE brand = 'ExampleBrand'
LIMIT 20;
~~~

Khi index đã sẵn sàng, query này có thể khai thác SAI để tìm các row matching. Tuy nhiên:

- Không có bảo đảm thứ tự theo `updated_at`, `price` hay `product_id`.
- `LIMIT 20` giới hạn số row, nhưng **không** tạo trang thứ hai bằng offset.
- Hiệu năng phụ thuộc số match, phân bố dữ liệu, server/driver version và workload.
- Nếu cần nhiều filter, phải kiểm tra sự hỗ trợ, kế hoạch thực thi và selectivity của từng index; không giả định index trên một cột tự tối ưu mọi phép kết hợp.

### 4.2. Truy vấn metadata index

~~~sql
SELECT index_name, kind, options
FROM system_schema.indexes
WHERE keyspace_name = 'catalog'
  AND table_name = 'products_by_id';
~~~

`system_schema.indexes` cho biết **index được khai báo** trong schema: tên, loại và options (tùy phiên bản Cassandra). Nó **không phải** một chỉ báo phổ quát rằng build dữ liệu cũ đã hoàn tất trên mọi node.

Trong `cqlsh` có thể dùng:

~~~text
DESCRIBE TABLE catalog.products_by_id;
~~~

`DESCRIBE` là tiện ích của `cqlsh`, không phải CQL command trong prepared statement của ứng dụng. Đối chiếu kết quả với migration, đặt tên index và loại implementation dự kiến.

### 4.3. Lưu ý IF NOT EXISTS

Một migration chạy lại:

~~~sql
CREATE CUSTOM INDEX IF NOT EXISTS product_brand_sai
ON catalog.products_by_id (brand)
USING 'StorageAttachedIndex';
~~~

có thể không tạo thêm index khi tên `product_brand_sai` đã tồn tại. Nhưng điều đó **không** chứng minh index hiện tại trỏ đến đúng cột, đúng implementation hoặc có trạng thái build tốt. Vì vậy post-check phải kiểm tra **định nghĩa thực** và readiness, không chỉ bắt exception của DDL.

## 5. Các giai đoạn triển khai an toàn

Một rollout index có thể chia thành sáu giai đoạn:

~~~mermaid
flowchart TD
    A["0. Baseline & capacity"] --> B["1. Kiểm thử trên staging có dữ liệu"]
    B --> C["2. Tạo index bằng migration"]
    C --> D{"3. Schema + build readiness?"}
    D -->|Chưa| E["Quan sát logs/metrics, không mở traffic"]
    E --> D
    D -->|Đạt| F["4. Canary query với tải nhỏ"]
    F --> G{"5. SLO và correctness đạt?"}
    G -->|Không| H["Tắt feature, điều tra / rollback"]
    G -->|Có| I["6. Ramp traffic, giám sát write & read"]
~~~

### 5.1. Giai đoạn 0: baseline và capacity

- Kiểm tra cluster không đang gặp outage, disk gần đầy hoặc compaction backlog nguy hiểm.
- Xác định index sẽ được xây trên dữ liệu hiện hữu ở những node nào; data size quyết định khối lượng công việc.
- Lập tài liệu schema, CQL, query traffic dự kiến và **phương án không dùng index**.
- Chuẩn bị dashboard và truy cập log/metrics, cùng quyền tắt đường query mới.
- Đảm bảo có không gian đĩa/CPU/I/O dành cho xây và duy trì index.

### 5.2. Giai đoạn 1: staging đại diện

Test trên bảng chứa dữ liệu tương đối đại diện về:

- Số row và phân bố brand/category.
- SSTable count, độ lớn, compaction strategy, TTL và tombstone.
- Tỷ lệ write/update/delete và read.
- Những giá trị có cardinality thấp/cao và các truy vấn trả nhiều match.

Staging có 100 dòng không thể chứng minh index sẽ chạy tốt trên bảng hàng trăm triệu dòng. Nếu không có staging đủ dữ liệu, phải giảm rủi ro bằng canary hẹp và ngưỡng dừng nghiêm ngặt hơn.

### 5.3. Giai đoạn 2: tạo index, chưa bật client query

Thực thi migration trong cửa sổ được phê duyệt. Ghi lại:

- Thời điểm và version schema.
- Lệnh CQL thực tế và kết quả.
- Tên index, keyspace/table/column.
- Các node/DC đang khỏe tại thời điểm tạo.
- Trạng thái build/compaction và sự cố phát sinh.

Không bật code query theo index cùng thời điểm bắt đầu build nếu chưa có cơ chế đảm bảo sẵn sàng cho mọi node liên quan.

### 5.4. Giai đoạn 3: chờ build và xác minh readiness

Thực hiện **nhiều phép kiểm tra độc lập** ở phần 6 bên dưới. Việc schema đã lan tới các node không có nghĩa dữ liệu cũ đã được index. Khi build kéo dài, việc ưu tiên giảm tải hoặc chuyển lịch triển khai phải dựa trên metrics, không dựa vào “đã đợi được 5 phút”.

### 5.5. Giai đoạn 4: canary

Chỉ sau khi readiness PASS, bật query mới cho:

- Một lượng request nhỏ có kiểm soát.
- Các giá trị brand có độ chọn lọc khác nhau.
- Kết quả đối chiếu với nguồn đáng tin cậy/case test đã chuẩn bị.
- CL và execution profile giống (hoặc gần) production dự kiến.

Gắn feature flag hoặc routing policy để có thể tắt traffic indexed mà **không** cần xóa index ngay khi phát hiện lỗi.

### 5.6. Giai đoạn 5–6: ramp dần và giám sát lâu hơn

Sau canary, tăng phần trăm request từng bước, theo dõi p95/p99, timeout, compaction và write latency. Đừng chỉ đo vài giây đầu; cần quan sát cả chu kỳ ghi/flush/compaction và giờ cao điểm. Nếu query mới làm write path xấu đi, đánh giá lại giá trị index so với read model riêng.

## 6. Chờ index sẵn sàng: ba lớp xác minh

Điểm dễ nhầm nhất khi triển khai index trên dữ liệu đã tồn tại:

| Lớp trạng thái | Cách kiểm tra | Chưa đủ để khẳng định |
| --- | --- | --- |
| **DDL accepted** | CQL `CREATE INDEX` trả thành công | Các node đã nhận schema, build hoàn tất |
| **Schema agreement** | Metadata/schema versions của các node thống nhất | Dữ liệu cũ đã có trong index trên mỗi replica |
| **Build/query readiness** | Tín hiệu build/index từ node, query smoke tests và metrics dưới tải nhẹ | SLO vẫn đúng dưới tải production đầy đủ |

### 6.1. Lớp 1 — xác minh khai báo schema

~~~sql
SELECT index_name, kind, options
FROM system_schema.indexes
WHERE keyspace_name = 'catalog'
  AND table_name = 'products_by_id';
~~~

Kết quả cần có `product_brand_sai`, options chỉ đúng index class/cột theo version. Nếu schema chưa thấy, kiểm tra migration/permission, không lập tức gửi hàng loạt retry DDL.

### 6.2. Lớp 2 — schema agreement và node health

Các lệnh vận hành tham khảo (chỉ chạy khi được phép trên môi trường tương ứng):

~~~text
nodetool status
nodetool describecluster
~~~

`nodetool status` giúp xem node/DC, trạng thái up/down và sở hữu dữ liệu; `describecluster` có thể hỗ trợ quan sát schema versions tùy phiên bản. Chúng **không phải lệnh xác nhận SAI build hoàn tất**. Nếu cluster có schema disagreement hoặc node down, không nên vội chuyển traffic sang index mới.

### 6.3. Lớp 3 — tiến độ build thực tế

Khi tạo index trên bảng có dữ liệu cũ, implementation có thể cần xây cấu trúc cho những SSTable hiện hữu. Hãy quan sát:

- Log server của **tất cả node/replica liên quan** về tiến độ, thành công hoặc thất bại của index build.
- Chỉ số/metric/JMX tương ứng với implementation và phiên bản SAI đang chạy.
- Sự thay đổi disk footprint, CPU, I/O và compaction/backlog trong lúc build.
- Lỗi query báo index chưa có sẵn hoặc lỗi đọc/bind theo index, nếu phiên bản có.
- Sự ổn định của node trong topology: không đang bootstrap/replace hoặc quá tải.

**Không giả định có một bảng CQL hay lệnh `nodetool` duy nhất cho mọi Cassandra version để trả `ready=true`.** Các metric names, nodetool capabilities và logs khác nhau theo bản phát hành. Runbook phải chỉ rõ **version cụ thể** và tín hiệu readiness tương ứng được đội vận hành hỗ trợ.

### 6.4. Smoke test có kiểm soát

Sau khi đã thấy tín hiệu build hoàn tất, chạy query ở canary:

~~~sql
SELECT product_id, brand
FROM catalog.products_by_id
WHERE brand = 'ExampleBrand'
LIMIT 20;
~~~

Thử cả:

- Giá trị có dữ liệu từ **trước khi tạo index**.
- Giá trị sản phẩm vừa được ghi **sau khi tạo index**.
- Giá trị không có bản ghi.
- Giá trị hiếm và rất phổ biến.
- Ghi update/delete với cột được index, rồi đọc theo kỳ vọng và mức consistency đã chọn.

Kết quả đọc cần được đối chiếu với dataset/expected keys đáng tin cậy. Query trả được 20 hàng **không chứng minh toàn bộ hàng cũ được index**, vì `LIMIT 20` có thể chỉ chạm một phần dữ liệu.

### 6.5. Readiness ở cluster nhiều DC

Nếu query mới sẽ được gọi từ nhiều DC, phải kiểm tra:

- Từng DC có đủ node/replica theo RF.
- Index build và trạng thái schema phù hợp ở các node có thể phục vụ query.
- Query canary từ **mỗi vùng triển khai** với routing/local DC đúng.
- Các vấn đề ghi/đọc đồng thời và độ trễ giữa DC.

Kiểm tra một lần trên một coordinator ở DC A **không** bảo đảm mọi node của DC B đã sẵn sàng. `LOCAL_QUORUM` không tự biến index chưa build trên một số replica thành vấn đề không tồn tại; hãy xác minh trước khi rollout đa vùng.

## 7. Quan sát ảnh hưởng lên tải: không chỉ query indexed

Một index có chi phí trên cả **đường ghi, lưu trữ và vận hành**. Khi thêm index mới, hệ thống có thể phải xây dữ liệu cũ, duy trì index khi insert/update/delete, và quản lý index qua flush/compaction.

### 7.1. Các nguồn chi phí

~~~mermaid
flowchart LR
    A["INSERT / UPDATE / DELETE"] --> B["Base table"]
    A --> C["Index maintenance"]
    D["Existing SSTables"] --> E["Index build"]
    F["Flush / Compaction"] --> G["Index lifecycle work"]
    B --> H["CPU + Disk IO + Memory"]
    C --> H
    E --> H
    G --> H
    I["Indexed SELECT"] --> J["Index lookup + base row reads"]
    J --> H
~~~

Tùy index implementation/version, chi tiết cơ chế khác nhau. Tuy nhiên, cần xác định tổng tải theo **workload trước và sau**, không chỉ latency của SELECT mới.

### 7.2. Những chỉ số phải theo dõi

| Nhóm | Tín hiệu | Cần phát hiện |
| --- | --- | --- |
| Đọc cũ | p50/p95/p99, read timeouts | Index build có làm đường đọc đang ổn định bị chậm? |
| Đọc indexed | p95/p99, số results, query latency | SAI có đáp ứng SLA ở các giá trị brand khác nhau? |
| Ghi | write latency, throughput, write timeout | Maintenance/build có làm đường ghi chậm? |
| CPU/heap | CPU saturation, heap occupancy, GC pauses | Index work có gây áp lực bộ nhớ/CPU? |
| Disk | Read/write IOPS, bandwidth, free bytes | Build tạo nhiều I/O, footprint làm gần đầy disk? |
| Compaction | Pending tasks, bytes compacted, backlog | Index work ảnh hưởng chu kỳ SSTable? |
| SAI/index | Build progress, index size, failures, query metrics của version | Có node chưa build xong, lỗi index hoặc tăng chi phí? |
| Hệ phân tán | Unavailable, dropped messages, pool in-flight, retry/speculation | Tải mới gây bất ổn coordinator/replica? |
| Dữ liệu | Tombstone warnings, TTL, partition size | Query phải đọc/xử lý nhiều bản ghi chết hoặc partition nóng? |
| Ứng dụng | Error budget, HTTP p99, canary-vs-control | Tác động có nhìn thấy ở người dùng cuối? |

Không bịa ngưỡng 70% CPU/10 ms latency cho mọi hệ thống. Nên định nghĩa **baseline theo giờ**, so sánh canary với traffic control, và liên hệ tới SLA được chấp thuận.

### 7.3. Query thấp cardinality dễ đánh lừa

Giả sử bảng có 50 triệu sản phẩm, trong đó 40 triệu có `status='ACTIVE'`. Index trên `status` giúp xác định điều kiện nhưng có thể dẫn tới lượng match quá lớn; `LIMIT 20` không đảm bảo query luôn rẻ nếu cần qua nhiều node/đoạn index và lấy row phù hợp.

Do đó, khi thử index:

- Không chỉ kiểm tra giá trị rất hiếm; phải thử **hot values**.
- Không chỉ đo trung bình; p95/p99 và timeout quan trọng.
- Không chỉ thử 1 request; cần tỷ lệ đồng thời gần tải thật.
- Không chỉ đo SELECT; ghi và compaction có thể xấu đi.
- Không chỉ đo lúc chưa build; phải đo cả sau khi index đã hoạt động liên tục.

### 7.4. Compaction, TTL và tombstone

Nếu bảng thường xuyên UPDATE/DELETE hoặc sử dụng TTL, lifecycle của SSTable và index có thể phát sinh chi phí. Dữ liệu hết hạn/xóa không biến mất vật lý ngay lập tức. Khi query indexed trả nhiều row hoặc cần đọc base row, tombstone và compaction pressure vẫn có thể ảnh hưởng latency.

Lập kế hoạch quan sát sau ít nhất một số chu kỳ flush/compaction theo workload thực tế, không kết thúc kiểm thử ngay khi query canary đầu tiên đạt mục tiêu.

## 8. Indexed query không xóa giới hạn CQL

Giả sử đã tạo SAI trên `brand`. Query:

~~~sql
SELECT product_id, brand, category, price
FROM catalog.products_by_id
WHERE brand = 'ExampleBrand'
LIMIT 20;
~~~

có thể dùng index. Nhưng các yêu cầu sau vẫn cần xem xét riêng:

- “Sắp xếp tất cả sản phẩm thương hiệu theo `price ASC`.”
- “Nhảy tới trang 500.”
- “Đếm chính xác mọi sản phẩm matching theo thời gian thực.”
- “Kết hợp 20 điều kiện tùy ý do người dùng tự chọn.”
- “Tìm gần đúng theo từ khóa và xếp hạng relevance.”
- “Join sản phẩm, kho, đơn hàng bằng foreign key.”

Index không tự tạo một B-tree global order hoặc query planner RDBMS đầy đủ. Với dữ liệu phân tán, mỗi điều kiện mới còn có thể đổi fan-out, số node/replica bị truy vấn, latency và tài nguyên.

### 8.1. Có thể thêm index thứ hai, nhưng phải đo

Nếu phiên bản SAI hỗ trợ tổ hợp điều kiện cần dùng, có thể cân nhắc thêm index cho `category`:

~~~sql
-- Index thứ hai chỉ sau khi đánh giá riêng về cost/benefit:
CREATE CUSTOM INDEX IF NOT EXISTS product_category_sai
ON catalog.products_by_id (category)
USING 'StorageAttachedIndex';
~~~

Ứng dụng có thể muốn:

~~~sql
SELECT product_id, brand, category, price
FROM catalog.products_by_id
WHERE brand = 'ExampleBrand'
  AND category = 'Laptop'
LIMIT 20;
~~~

Phải xác minh cú pháp, planner/index support và hiệu năng của tổ hợp này theo phiên bản Cassandra thật. Mỗi index thêm nghĩa là **thêm chi phí duy trì khi ghi**, disk footprint và tiềm năng tải ở compaction. Không tạo hàng loạt index trên mọi field chỉ để “dự phòng tương lai”.

### 8.2. `ALLOW FILTERING` không phải fallback an toàn

Khi index chưa được tạo hoặc chưa sẵn sàng, không nên tự động chuyển query thành:

~~~sql
-- KHÔNG khuyến nghị làm fallback production:
SELECT *
FROM catalog.products_by_id
WHERE brand = 'ExampleBrand'
ALLOW FILTERING;
~~~

`ALLOW FILTERING` có thể chấp nhận một truy vấn phải lọc/đọc lượng dữ liệu không dự đoán được; khi bảng tăng, chi phí có thể bùng và đè lên toàn cluster. Fallback an toàn hơn là **giữ đường query cũ**, dùng read model đã có hoặc tạm khóa feature với thông điệp rõ.

### 8.3. Paging và LIMIT trên indexed query

`LIMIT 20` giới hạn **tổng row trả về theo CQL**, còn driver `setPageSize(20)` điều khiển mục tiêu mỗi lần fetch. Muốn trang sau, cần paging state/cursor; Cassandra không có `OFFSET 50000 LIMIT 20` tổng quát.

~~~java
PreparedStatement prepared = session.prepare(
    "SELECT product_id, brand, category, price " +
    "FROM catalog.products_by_id WHERE brand = ?"
);

BoundStatement statement = prepared.bind(brand)
    .setPageSize(20)
    .setIdempotent(true);
~~~

Nếu service chỉ cần tối đa 20 row, đưa `LIMIT 20` vào CQL hoặc API contract tương ứng. Đừng lấy toàn bộ kết quả into `List` rồi chỉ hiển thị 20: driver có thể fetch nhiều trang và gây tải lớn.

Ngoài ra, thứ tự row từ indexed query không nên được coi là thứ tự ổn định theo ý nghĩa nghiệp vụ. Nếu cần UI có thứ tự theo `price`/`updated_at`, hãy dùng bảng với clustering order hoặc một hệ tìm kiếm có sort contract thích hợp.

### 8.4. COUNT không miễn phí vì có index

~~~sql
SELECT COUNT(*)
FROM catalog.products_by_id
WHERE brand = 'ExampleBrand';
~~~

Nếu được phiên bản/query cho phép, tính tổng matching vẫn có thể phải duyệt nhiều kết quả, không tự có metadata count tức thời. Nếu UI bắt buộc “khoảng N sản phẩm”, cân nhắc aggregate có thời điểm as-of, job analytics hoặc cache, với quy tắc cập nhật và đối soát riêng.

## 9. Sử dụng index qua Spring Data Cassandra

Spring Data Cassandra giúp ánh xạ entity và query, nhưng **không bảo đảm index sẵn sàng** và cũng không tự tạo một access pattern hiệu quả nếu CQL thiếu điều kiện đúng.

### 9.1. Entity của bảng gốc

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("products_by_id")
public class ProductById {

    @PrimaryKey("product_id")
    private UUID productId;

    @Column("brand")
    private String brand;

    @Column("category")
    private String category;

    @Column("price")
    private BigDecimal price;

    @Column("status")
    private String status;

    @Column("updated_at")
    private Instant updatedAt;

    public ProductById() {
    }

    // Constructors, getters và setters...
}
~~~

Entity phải được ánh xạ đúng keyspace/table và CQL types. `@Table("products_by_id")` không tự yêu cầu Cassandra tạo SAI. Nếu Spring Boot dùng `spring.cassandra.schema-action: none`, schema/index phải được quản lý bởi migration bên ngoài.

### 9.2. CassandraTemplate query theo cột đã index

~~~java
import java.util.List;

import org.springframework.data.cassandra.core.CassandraTemplate;
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;

public class ProductSearchReader {

    private final CassandraTemplate template;

    public ProductSearchReader(CassandraTemplate template) {
        this.template = template;
    }

    public List<ProductById> findByBrand(String brand) {
        Query q = Query.query(
            Criteria.where("brand").is(brand)
        ).limit(20);

        return template.select(q, ProductById.class);
    }
}
~~~

`CassandraTemplate` sẽ sử dụng metadata entity để dựng và ánh xạ CQL. Query chỉ hoạt động theo cách dự kiến khi **index phù hợp thực sự tồn tại và sẵn sàng trên cluster**, hoặc có đường access hợp lệ khác. Template không tự đợi background index build hoàn tất.

Nếu ứng dụng cần kiểu kết quả DTO, có thể dùng fluent projection (tùy phiên bản Spring Data) hoặc CQL chọn những cột cần thiết, nhưng projection **không** sửa đường query hoặc biến query scan thành index lookup.

### 9.3. Repository với CQL rõ ràng

~~~java
import java.util.List;
import java.util.UUID;

import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductByIdRepository
        extends CassandraRepository<ProductById, UUID> {

    @Query(
        "SELECT product_id, brand, category, price, status, updated_at " +
        "FROM products_by_id " +
        "WHERE brand = :brand LIMIT 20"
    )
    List<ProductById> findFirstTwentyByBrand(
        @Param("brand") String brand
    );
}
~~~

Đây là một **đường đọc phụ thuộc SAI/secondary index**. Không bật method cho toàn bộ request chỉ vì code compile. Migration và readiness của index phải hoàn tất trước. Nếu query này được gọi trên schema không có đường index phù hợp, server có thể báo lỗi hoặc yêu cầu lọc/scan, trái dự đoán.

### 9.4. Java Driver và prepared statements

Khi cần set consistency/timeout/page size rõ ràng:

~~~java
import java.time.Duration;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.ConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

PreparedStatement prepared = session.prepare(
    "SELECT product_id, brand, price " +
    "FROM catalog.products_by_id WHERE brand = ? LIMIT 20"
);

BoundStatement statement = prepared.bind(brand)
    .setConsistencyLevel(ConsistencyLevel.LOCAL_QUORUM)
    .setTimeout(Duration.ofSeconds(2))
    .setPageSize(20)
    .setIdempotent(true);
~~~

Giá trị trên chỉ để minh họa, phải chọn theo RF/local DC/SLA thật. `setIdempotent(true)` phù hợp cho truy vấn SELECT thuần, nhưng không tự bảo đảm retry của các mutation index-related đều an toàn.

### 9.5. Quản lý schema bằng migration

Không để mỗi instance Spring Boot chạy DDL tạo index vào lúc startup không kiểm soát, đặc biệt khi có hàng chục pod:

~~~yaml
spring:
  cassandra:
    keyspace-name: catalog
    local-datacenter: dc1
    schema-action: none
~~~

Cấu hình trên minh họa ứng dụng **không tự tạo schema**; DDL index được thực thi bởi workflow migration do đội vận hành kiểm soát. Tên DC/keyspace phải khớp môi trường thật. Mỗi ứng dụng vẫn cần quyền SELECT/INSERT/UPDATE phù hợp; DDL nên thuộc quyền của pipeline migration với phân quyền tối thiểu cần thiết.

## 10. Write path, compaction và lifecycle index

Khi có index, một mutation trên bảng gốc có thể cần duy trì cấu trúc liên quan. Ảnh hưởng chính xác tùy SAI/2i và phiên bản, nhưng ba loại công việc thường cần theo dõi:

1. **Initial build:** xây index trên dữ liệu/SSTable đã tồn tại.
2. **Steady-state writes:** ghi mới, thay đổi cột indexed, xóa hoặc TTL hết hạn.
3. **SSTable lifecycle:** flush, compaction, streaming/repair và các thao tác quản trị có thể liên quan công việc index.

Index không phải một bảng denormalized do ứng dụng tự cập nhật thông qua repository khác. Với cơ chế index được Cassandra hỗ trợ, server quản lý cấu trúc index gắn với dữ liệu cơ sở. Tuy vậy, nếu một **read model nghiệp vụ khác** tồn tại (ví dụ `products_by_brand`), Spring Data không tự đồng bộ read model đó; ứng dụng phải thiết kế đường ghi riêng.

### 10.1. Cập nhật giá trị của cột indexed

Ví dụ:

~~~sql
UPDATE catalog.products_by_id
SET brand = 'NewBrand'
WHERE product_id = ?;
~~~

Một truy vấn theo `brand='OldBrand'` và query theo `brand='NewBrand'` phải được kiểm thử theo consistency và trạng thái mutation thực tế. Chỉ mục được thiết kế để phản ánh cập nhật bảng gốc, nhưng đọc trên một replica chưa bắt kịp hoặc khi có timeout/compaction có thể xuất hiện hành vi mà SLO cần đánh giá.

Nếu chuyển trạng thái nghiệp vụ qua nhiều bảng denormalized, chuyện đó vẫn tách biệt với việc cập nhật index vật lý của một bảng.

### 10.2. TTL và xóa

~~~sql
DELETE FROM catalog.products_by_id
WHERE product_id = ?;
~~~

Cassandra sử dụng tombstone để biểu thị dữ liệu bị xóa; cleanup vật lý phụ thuộc lifecycle và repair/compaction. Với bảng có nhiều TTL/xóa, cần theo dõi query latency, tombstone scanning, disk footprint và index maintenance. Không giả định xóa row làm mọi byte trong index biến mất ngay.

### 10.3. Repair và rebuild index

Khi gặp lỗi nghiêm trọng do index missing/corrupt, phải xác nhận:

- Bản Cassandra và index implementation đang dùng.
- Node/partition nào bị ảnh hưởng.
- Loại lỗi và bằng chứng từ log/metrics.
- Khả năng rebuild/recreate và chi phí I/O/disk.
- Cách tắt đường query mới trong lúc khắc phục.

Không tự chạy hàng loạt lệnh rebuild/repair/compaction trên toàn cụm chỉ vì một canary chậm. Các lệnh như `nodetool rebuild_index` (nếu bản đang dùng hỗ trợ) cần được kiểm tra đúng cú pháp/semantics theo version và có phê duyệt vận hành, bởi chúng có thể tạo tải đáng kể. Rebuild không thay thế việc phân tích nguyên nhân.

## 11. Rollback: ưu tiên tắt feature trước khi thay schema

Một rollout index nên có **hai cấp rollback**.

### 11.1. Cấp 1 — tắt đường query indexed

Nếu query mới gây timeout, ảnh hưởng đường ghi hoặc sai kết quả:

1. Tắt feature flag/routing cho truy vấn theo index.
2. Quay lại endpoint cũ, read model đã tồn tại hoặc trả thông điệp không hỗ trợ tạm thời.
3. Duy trì metrics và logs để điều tra.
4. Đảm bảo request in-flight được xử lý theo deadline/timeout an toàn.
5. Chỉ mở lại sau khi hiểu nguyên nhân và readiness/perf đạt yêu cầu.

Đây thường là cách giảm rủi ro nhanh mà không bắt buộc thay đổi schema ngay.

### 11.2. Cấp 2 — bỏ index bằng migration

Nếu kết luận index không còn đáng duy trì, có thể lên kế hoạch:

~~~sql
DROP INDEX IF EXISTS catalog.product_brand_sai;
~~~

Cú pháp/thẩm quyền DROP INDEX phải được kiểm tra theo Cassandra version và deployment. Xóa index có thể giải phóng cấu trúc lưu trữ theo lifecycle implementation, nhưng **không nên giả định disk I/O và dung lượng lập tức quay về baseline**. Cần theo dõi thao tác và xác minh sau DDL.

**Quan trọng:** Trước khi DROP, bảo đảm không còn đường query production nào phụ thuộc index. Nếu vẫn còn, truy vấn có thể thất bại hoặc chuyển sang hành vi không phù hợp. Recreate sẽ kéo theo chi phí build lại dữ liệu cũ.

### 11.3. Lưu bằng chứng để quyết định

Tài liệu rollback nên có:

- Query/feature nào bị tắt, thời gian bắt đầu/kết thúc canary.
- Dữ liệu latency/error/CPU/disk/compaction trước và sau.
- Node/DC nào build chậm hoặc phát sinh lỗi.
- Định nghĩa index và migration version.
- Giải pháp tiếp theo: tối ưu query, thay bằng read model, giữ index nhưng giới hạn QPS, hoặc bỏ hẳn.

Không đánh giá index thành công chỉ từ việc “các query chạy được”; mức ảnh hưởng lên tổng cluster mới là tiêu chí vận hành.

## 12. Ví dụ runbook triển khai từ staging đến production

Một runbook tốt có checkpoints và người chịu trách nhiệm rõ ràng. Dưới đây là mẫu có thể tùy biến.

### Bước 1 — xác nhận môi trường

~~~text
[ ] Cassandra version/distribution hỗ trợ SAI
[ ] Đã chốt keyspace/table/column/type
[ ] Đã đánh giá alternative: products_by_brand
[ ] Có baseline read/write SLA và metrics
[ ] Có disk/capacity headroom đủ cho index build
[ ] Các DC/node/replica đang healthy
[ ] Có feature flag tắt query mới
[ ] Có owner theo dõi deployment và stop condition
~~~

### Bước 2 — tạo schema trên staging

~~~sql
CREATE CUSTOM INDEX IF NOT EXISTS product_brand_sai
ON catalog.products_by_id (brand)
USING 'StorageAttachedIndex';
~~~

Đọc metadata:

~~~sql
SELECT index_name, kind, options
FROM system_schema.indexes
WHERE keyspace_name = 'catalog'
  AND table_name = 'products_by_id';
~~~

So sánh schema với định nghĩa mong muốn. Nếu index cùng tên nhưng sai cột/implementation, dừng migration để xác định xung đột; không tự coi `IF NOT EXISTS` là thành công học thuật.

### Bước 3 — theo dõi build trên các node

~~~text
[ ] Schema agreement được xác minh
[ ] Không có node liên quan đang down/không đủ RF
[ ] Logs/metrics báo build hoàn tất theo version đang dùng
[ ] Không còn lỗi build/index availability chưa xử lý
[ ] Disk, CPU, I/O, heap, compaction nằm trong ngưỡng chấp nhận
[ ] Read/write traffic cũ chưa suy giảm ngoài error budget
~~~

Không có con số thời gian chờ chung. Bảng lớn, số SSTable, topology và tải hiện tại có thể làm build khác biệt lớn giữa staging và production.

### Bước 4 — đối chiếu dữ liệu

Chuẩn bị một vài sản phẩm đã tồn tại trước CREATE INDEX, một số vừa insert và một số vừa update `brand`. Chạy:

~~~sql
SELECT product_id, brand, price
FROM catalog.products_by_id
WHERE brand = 'ExampleBrand'
LIMIT 20;
~~~

So sánh kết quả với expected keys từ test dataset đã kiểm soát. Thử cả giá trị rỗng, không tồn tại và brand có nhiều match. Kiểm chứng không chỉ query có trả row mà còn không có lỗi index build/availability trên các coordinator/replica được sử dụng.

### Bước 5 — chạy benchmark có kiểm soát

Chạy tải dần, bao gồm:

- Truy vấn trực tiếp theo `product_id` (control).
- Truy vấn mới theo `brand` (indexed).
- Mixed read/write workload ở các mức QPS đại diện.
- Insert/update/delete `brand` khi query đồng thời.
- Nhiều giá trị brand với phân bố không đều.

Ghi số liệu cùng baseline, p95/p99, tail timeout và ảnh hưởng lên write path. Nếu SLO không đạt, dừng trước khi chuyển production.

### Bước 6 — production DDL với traffic cũ

Tạo index theo migration một lần, chưa bật traffic mới. Xác nhận schema và build trên topology production, đặc biệt các DC mà app có thể dùng.

### Bước 7 — bật canary

Bật query qua feature flag cho một phần traffic nhỏ. Theo dõi dashboard; giữ khả năng tắt ngay. Không tự tăng tỉ lệ chỉ vì chưa thấy exception trong vài request.

### Bước 8 — tăng traffic và đánh giá lâu dài

Nếu canary đúng và ổn định, tăng dần; ghi tác động sau các đợt flush/compaction và trong giờ cao điểm. Đánh giá lại lợi ích index so với chi phí duy trì trước khi tuyên bố deployment hoàn tất.

## 13. Bài thực hành: quyết định dùng index hay bảng riêng

### 13.1. Yêu cầu

Một catalog có:

- 10 triệu sản phẩm.
- Query chính: tra theo `product_id`.
- Query phụ: tìm sản phẩm theo `brand`, trả tối đa 20 item.
- Query sắp ra mắt: “20 sản phẩm mới cập nhật gần nhất theo `brand`”.

Bạn cần thiết kế rollout không làm ảnh hưởng API tra cứu chi tiết.

### 13.2. Câu hỏi thiết kế

**A.** Có nên thêm index trên `brand` ngay để hỗ trợ cả hai query phụ?

Gợi ý: index có thể hỗ trợ **lọc theo brand** trong phạm vi version/query hợp lệ, nhưng không tự bảo đảm **sắp xếp toàn bộ sản phẩm của brand theo updated_at**. Query sắp xếp thường đòi bảng theo brand với clustering key/phân bucket phù hợp, hoặc một search/index system có sort semantics thích hợp.

**B.** Có thể tạo SAI xong rồi bật 100% traffic ngay không?

Không. Cần đợi schema agreement, build readiness theo node/implementation, smoke test correctness và canary performance.

**C.** Vì sao cần benchmark cả query theo `product_id` cũ?

Index build/maintenance dùng tài nguyên chung với traffic cũ. Một cải thiện ở query theo brand có thể làm p99 chi tiết sản phẩm tệ hơn; rollout chỉ thành công khi tổng hệ thống trong SLO.

**D.** Nếu `brand='PopularBrand'` trả 3 triệu hàng thì `LIMIT 20` có làm truy vấn rẻ tương đương `WHERE product_id=?` không?

Không. Query indexed và partition-key lookup khác đường truy cập; selectivity, fan-out, tải và layout index cần được đo riêng.

**E.** Nếu migration trả thành công và `system_schema.indexes` có tên index, có thể xem “ready” chưa?

Chưa. Đây mới là lớp khai báo; phải xác minh build tiến độ/hoàn tất ở các node liên quan và query smoke tests.

### 13.3. Đề xuất bảng riêng cho đường sorted feed

Nếu sản phẩm cần danh sách mới cập nhật theo brand, có thể thiết kế:

~~~sql
CREATE TABLE catalog.products_by_brand_month (
    brand text,
    month_bucket text,
    updated_at timestamp,
    product_id uuid,
    category text,
    price decimal,
    status text,
    PRIMARY KEY ((brand, month_bucket), updated_at, product_id)
) WITH CLUSTERING ORDER BY (
    updated_at DESC,
    product_id ASC
);
~~~

Truy vấn:

~~~sql
SELECT product_id, updated_at, category, price
FROM catalog.products_by_brand_month
WHERE brand = ?
  AND month_bucket = ?
LIMIT 20;
~~~

Bảng này cho phép đọc có thứ tự trong một partition theo `brand/month`. Nếu cập nhật `updated_at`, vì nó là clustering key nên cần xử lý row ở khóa cũ và khóa mới, đồng bộ dữ liệu denormalized và tombstone. `month_bucket` giúp giới hạn partition, nhưng khi đọc xuyên nhiều tháng cần cursor/merge ở tầng ứng dụng.

Đây là đánh đổi **thêm bảng và chi phí write** để đạt đường đọc có thứ tự rõ ràng. Không có lời khuyên phổ quát “index luôn tốt” hoặc “không bao giờ dùng index”; quyết định dựa trên access pattern và số đo thật.

### 13.4. Bài test tích hợp trong Spring Data

Với entity `ProductById` đã khai báo, thử các kịch bản:

| Ca test | Kỳ vọng cần xác minh |
| --- | --- |
| Query theo ID không có index | Vẫn đọc được, p99 không suy giảm đáng kể sau rollout |
| Query theo brand trên staging trước index | Không coi `ALLOW FILTERING` là fallback đáp ứng SLA |
| Query theo brand sau index và readiness | Kết quả khớp data fixture và không có lỗi |
| Insert mới với brand được index | Truy vấn theo brand phản ánh ghi theo consistency đã chọn |
| Update brand của sản phẩm | Không trả dữ liệu sai kéo dài; kiểm tra đồng bộ/index lifecycle |
| Delete sản phẩm có index | Tombstone/compaction không gây tải bất thường |
| Giá trị brand rất phổ biến | Latency, tài nguyên và timeout trong ngưỡng SLA |
| Query có thêm category filter | Chỉ bật nếu version/index support, đã đo và có migration riêng |
| Node down/multi-DC | Kiểm tra availability và trạng thái build ở từng vùng |
| Feature flag OFF | Không gửi query mới dựa trên index |
| DROP index thử nghiệm | Không còn đường query nào bị phụ thuộc |
| Recreate index | Quay lại toàn bộ bước build/readiness/benchmark |

## 14. Các lỗi phổ biến

| Dấu hiệu | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `CREATE CUSTOM INDEX` thất bại | Cluster/version không hỗ trợ SAI hoặc thiếu quyền | Kiểm tra version, index class và quyền DDL |
| DDL thành công nhưng query lỗi | Schema/chỉ mục chưa sẵn sàng, CQL không được hỗ trợ | Kiểm tra agreement, build logs/metrics, schema, query |
| `system_schema.indexes` có index nhưng canary sai | Metadata không chứng minh build đầy đủ hoặc test dataset có vấn đề | Đối chiếu build ở replica và dữ liệu nguồn |
| p99 SELECT cũ tăng mạnh sau CREATE | Build dùng CPU/I/O/compaction chung | Dừng ramp, giảm tải, kiểm tra capacity và window |
| Write latency cao khi index đã hoạt động | Maintenance index / compaction / nhiều write | So sánh baseline, đánh giá chi phí vs lợi ích |
| Disk free giảm ngoài dự kiến | Index footprint/build/lifecycle | Theo dõi index size, SSTable/compaction, capacity |
| Query brand phổ biến rất chậm | Kết quả nhiều, fan-out/selectivity thấp | Benchmark hot values, cân nhắc read model |
| `ORDER BY updated_at DESC` không chạy như mong đợi | Indexed filter không tạo global ordering | Thiết kế bảng theo brand+clustering |
| Dùng `ALLOW FILTERING` để né lỗi index | Quét/lọc không giới hạn | Tắt đường indexed, sửa schema/query thay vì ép scan |
| `LIMIT 20` vẫn p99 cao | Index lookup và dữ liệu nền có thể đắt | Xem phân bố dữ liệu, node metrics, query plan/tracing |
| Dùng một canary để kết luận multi-DC ready | Các DC/node không đồng nhất readiness | Kiểm chứng từng vùng, routing và CL |
| `IF NOT EXISTS` được xem là khớp schema | Tên tồn tại nhưng định nghĩa có thể khác | Đọc `system_schema.indexes` và so sánh |
| Drop index rồi app lỗi | Query path vẫn phụ thuộc index | Tắt feature/route trước, rồi migration |
| Mở nhiều index vì mỗi field đều có filter | Tổng chi phí write/disk/compaction tăng | Ưu tiên query có giá trị, đo và giới hạn số index |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `CREATE INDEX` trả thành công chưa đủ để bật traffic indexed?

*Gợi ý:* Schema declaration, schema agreement và index build/query readiness là các trạng thái khác nhau.

**Câu 2.** `nodetool status` có chứng minh index build hoàn tất không?

*Đáp án:* Không. Nó nói về trạng thái node/topology, không phải readiness của index trên dữ liệu cũ.

**Câu 3.** Tại sao phải đo p99 của query `WHERE product_id=?` cũ sau khi tạo SAI trên `brand`?

*Gợi ý:* Initial build, write maintenance và compaction dùng tài nguyên CPU/I/O/đĩa chung.

**Câu 4.** Index trên `brand` có bảo đảm `ORDER BY price ASC` trên toàn bộ sản phẩm matching không?

*Đáp án:* Không. Index filter không tự tạo global sort theo cột khác.

**Câu 5.** Khi không có SAI phù hợp, tại sao không mặc định thêm `ALLOW FILTERING`?

*Gợi ý:* Có thể mở đường quét/lọc nhiều partition gây timeout và tải không dự đoán được.

**Câu 6.** Hai query theo cùng brand, một trả 50 match và một trả 2 triệu match, có nên chỉ benchmark query đầu không?

*Đáp án:* Không. Cần kiểm tra các giá trị hiếm/phổ biến và phân bố thật.

**Câu 7.** `system_schema.indexes` xác minh được điều gì?

*Gợi ý:* Sự tồn tại/định nghĩa index trong schema, không phải universal readiness flag.

**Câu 8.** Vì sao SAI không tự đồng bộ bảng `products_by_brand` do ứng dụng tạo?

*Gợi ý:* Index vật lý của một bảng do Cassandra duy trì, còn read model là bảng nghiệp vụ khác cần write path riêng.

**Câu 9.** Vì sao nên tắt query bằng feature flag trước khi DROP INDEX?

*Gợi ý:* Tránh request còn phụ thuộc index thất bại; DROP/recreate còn có chi phí build.

**Câu 10.** Tại sao `LIMIT 20` và `setPageSize(20)` không giống nhau?

*Gợi ý:* LIMIT giới hạn tổng row CQL; page size chỉ mục tiêu cho mỗi lượt fetch.

**Câu 11.** Nếu production có hai data center, readiness cần được xác nhận ở đâu?

*Gợi ý:* Các node/replica/vùng thực sự phục vụ query, không chỉ một coordinator.

**Câu 12.** Khi nào nên ưu tiên bảng `products_by_brand_month` thay vì chỉ SAI trên `brand`?

*Gợi ý:* Khi business cần thứ tự `updated_at DESC` rõ ràng, throughput cao, latency ổn định và pagination theo bucket.

## 16. Checklist triển khai production

- **Version:** xác nhận Apache Cassandra/distribution hỗ trợ loại index được chọn; không sao chép DDL ngoài phiên bản.
- **Query-driven:** có CQL cụ thể và business SLA; đã so sánh lựa chọn index với bảng theo partition/clustering.
- **Selectivity:** biết phân bố giá trị, thử cả match hiếm và giá trị phổ biến/hot.
- **Schema:** kiểm tra table/cột/kiểu/primary key, index đang tồn tại và migration version.
- **Capacity:** baseline CPU, disk, heap, compaction, throughput, p95/p99 và error budget.
- **Quyền:** migration có quyền DDL phù hợp; ứng dụng runtime không cần quyền CREATE INDEX.
- **Build:** không coi DDL accepted hoặc schema agreement là index ready; quan sát logs/metrics theo version trên node liên quan.
- **Canary:** đối chiếu dữ liệu cũ/mới, query ở các vùng, CL và workload đại diện.
- **Traffic:** ramp theo feature flag, có stop condition và dashboard xác định.
- **Read + write:** quan sát latency và lỗi của query cũ, indexed query và mutations.
- **Paging:** LIMIT/page size/cursor đúng mục đích; không hứa OFFSET hoặc global ORDER BY.
- **Consistency:** xác định RF/DC, LOCAL_ONE/LOCAL_QUORUM và hợp đồng dữ liệu trễ phù hợp.
- **Lifecycle:** theo dõi index disk footprint, flush/compaction, TTL, tombstone và sự kiện node recovery.
- **Rollback:** tắt đường indexed trước, chỉ DROP khi an toàn, lưu runbook để rebuild nếu cần.
- **Bảo trì:** có owner giám sát metric, quyền truy cập logs và phương án đối soát khi kết quả bất thường.
- **Không QA STEP_6 tại đây:** bài STEP_4 là nội dung knowledge; bước kiểm thử/đánh giá học thuật chuyên sâu được thực hiện ở luồng sau.

## Tài liệu tham khảo

- [Apache Cassandra — Documentation](https://cassandra.apache.org/doc/latest/): kiểm tra tính năng SAI, secondary indexes, CQL và lệnh vận hành theo phiên bản server.
- [Apache Cassandra — CQL Reference](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/index.html): `CREATE INDEX`, `SELECT`, partition key, `LIMIT`, consistency và các ràng buộc truy vấn.
- [Spring Data Cassandra — Reference](https://docs.spring.io/spring-data/cassandra/reference/): mapping, repository, CassandraTemplate và cấu hình schema.
- [Apache Cassandra Java Driver](https://apache.github.io/cassandra-java-driver/): prepared statements, request options, paging và metrics (chọn tài liệu khớp driver version).
- [Apache Cassandra Operations](https://cassandra.apache.org/doc/latest/cassandra/managing/): nodetool, node health, logging, compaction và hướng dẫn vận hành.

## Kết luận

Triển khai chỉ mục trong Cassandra là **một thay đổi hạ tầng dữ liệu có tác động lên tải**, không chỉ là thêm một câu `CREATE INDEX`. Muốn thành công, phải chọn đúng query, index implementation và phiên bản; xác minh metadata, schema agreement **và quá trình build sẵn sàng trên các replica**; sau đó mới bật canary, tăng traffic và theo dõi đọc/ghi, CPU, đĩa, heap, compaction, timeout và consistency.

Trong **SPRING_DATA_CASSANDRA**, repository, CassandraTemplate và Java Driver giúp gọi CQL nhưng **không thay thế trách nhiệm vận hành index**. Một SAI phù hợp có thể mở ra đường lọc hữu ích, song không giải quyết tùy ý sorting, count, phân trang offset hay việc đồng bộ nhiều bảng denormalized. Với các truy vấn lõi có thứ tự và SLA cao, hãy so sánh thẳng với bảng được thiết kế theo partition/clustering key. Chỉ xem rollout hoàn tất khi dữ liệu đúng, tính sẵn sàng đã kiểm chứng và hiệu năng toàn cluster tiếp tục nằm trong mức chấp nhận được.

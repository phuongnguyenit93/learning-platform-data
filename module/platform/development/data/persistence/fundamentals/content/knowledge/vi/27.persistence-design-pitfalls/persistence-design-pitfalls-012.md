# Lựa chọn kho dữ liệu theo trào lưu thay vì yêu cầu truy cập

Một nhóm phát triển Java có thể nghe rằng **NoSQL dễ mở rộng**, **document database linh hoạt**, **vector database là tương lai AI**, hoặc **search engine trả kết quả cực nhanh**. Những nhận định này có thể đúng trong một số điều kiện, nhưng sẽ trở thành sai lầm thiết kế nếu được dùng thay cho câu hỏi quan trọng hơn: **ứng dụng thực sự đọc và ghi dữ liệu theo mẫu nào, với những bất biến nào, ở mức tải và rủi ro nào?**

Ví dụ, dịch vụ đặt hàng cần đồng thời tạo đơn, ghi các dòng hàng, giảm tồn kho và tránh ghi trùng. Chọn một kho chỉ vì có nhãn “cloud-native” hay “schema-less” có thể khiến nhóm phải tự giải quyết những vấn đề về transaction, join, uniqueness và consistency mà một RDBMS quen thuộc đã hỗ trợ tốt. Ngược lại, bắt cơ sở dữ liệu giao dịch xử lý truy vấn văn bản phức tạp hoặc phân tích trên hàng trăm tỷ sự kiện cũng có thể đẩy một công cụ vào phạm vi không phù hợp.

Bài thuộc chương **Lỗi thiết kế** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Trong bối cảnh Java persistence, mục tiêu là ra quyết định từ **mô hình dữ liệu, truy vấn, chỉ mục, giao dịch, cô lập, đồng thời, durability, bảo mật, sao lưu, tiến hóa schema và hiệu năng** thay vì từ xu hướng công nghệ hoặc kinh nghiệm rời rạc. Ví dụ dùng PostgreSQL và Java JDBC/Spring Data ở mức khái niệm. Các tính năng, giới hạn và chi phí của từng sản phẩm thay đổi theo phiên bản và dịch vụ triển khai; cần đánh giá thực nghiệm theo điều kiện cụ thể.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện lỗi **technology-first design**: chọn loại kho trước khi biết access patterns.
2. Thu thập workload từ những thao tác đọc/ghi có thể đo, không chỉ từ các danh từ như “big data”.
3. Phân biệt **OLTP, cache, search, analytics, time-series, graph, document và vector retrieval** theo mục tiêu truy cập.
4. Đánh giá **atomicity, consistency, durability, availability, latency, throughput, growth, security và recoverability** trước khi chọn.
5. So sánh ưu và nhược của **RDBMS, document store, key-value, wide-column, graph, search index, analytical warehouse và vector index** mà không mặc định công nghệ nào “tốt nhất”.
6. Dùng ví dụ SQL, index, truy vấn và ranh giới transaction để chứng minh một lựa chọn phù hợp.
7. Thiết kế thử nghiệm **proof of concept/benchmark** có tiêu chí chấp nhận, dữ liệu và tải đại diện.
8. Nhận biết chi phí **polyglot persistence**, đồng bộ hóa, dual writes, CDC/outbox, vận hành và migration.
9. Viết **decision record** giúp nhóm giải thích, đánh giá lại và thay thế lựa chọn khi workload thực tế thay đổi.

## 2. Sai lầm bắt đầu từ câu hỏi không đúng

Các cuộc thảo luận thường bắt đầu như sau:

> “Ứng dụng mới nên dùng NoSQL vì nhanh hơn SQL.”

> “Dữ liệu dạng JSON nên bỏ relational database.”

> “Sắp có AI nên phải lưu tất cả vào vector database.”

> “Hệ thống cần scale nên mọi dữ liệu phải chia shard từ ngày đầu.”

Những câu khẳng định này thiếu thông tin về **đơn vị dữ liệu**, **query**, **transaction**, **dữ liệu quan trọng**, **phân bố tải**, **tăng trưởng**, **mức độ chấp nhận mất dữ liệu** và **khả năng vận hành của nhóm**.

Một thứ được gọi là “NoSQL” không có tập đặc điểm thống nhất: key-value, document, wide-column và graph có mô hình truy cập, consistency, indexing và transaction khác nhau. Ngược lại, PostgreSQL không chỉ làm SELECT theo khóa chính; nó còn hỗ trợ index phức hợp, JSONB, full-text search, partitioning và nhiều kiểu dữ liệu. Việc so sánh chỉ bằng hai nhãn **SQL/NoSQL** là không đủ.

### 2.1. Đổi từ câu hỏi công nghệ sang câu hỏi nghiệp vụ

| Câu hỏi hấp dẫn nhưng mơ hồ | Câu hỏi có thể kiểm chứng |
|---|---|
| “NoSQL có scale tốt hơn không?” | “Dự kiến bao nhiêu thao tác/giây, kích thước bản ghi, số partition nóng và tốc độ tăng trưởng?” |
| “Document DB linh hoạt hơn chứ?” | “Các aggregate thường được đọc/ghi nguyên khối hay cần join/query nhiều quan hệ?” |
| “Redis nhanh hơn DB phải không?” | “Đang tối ưu đường đọc nào? Khi cache miss/failover, nguồn dữ liệu có thẩm quyền là gì?” |
| “Search engine có thể thay SQL không?” | “Cần ranking full-text hay transaction/unique constraint/update tức thời?” |
| “Graph DB là lựa chọn cho mọi quan hệ?” | “Truy vấn có thực sự là traversal biến thiên nhiều bước trên đồ thị lớn?” |
| “Vector index thay được mọi search?” | “Đang cần độ giống ngữ nghĩa, hay filter chính xác, phân quyền, kết quả mới nhất?” |
| “Phải shard trước khi launch?” | “Một instance có partition/index/scale-up hợp lý đã đạt SLO chưa?” |

**Nguyên tắc:** công nghệ là một giả thuyết để kiểm chứng, không phải tiền đề bất biến.

## 3. “Yêu cầu truy cập” bao gồm những gì?

**Access pattern** không chỉ là câu SQL hiện có. Nó mô tả **ai truy cập đối tượng nào, theo khóa hoặc điều kiện gì, đọc/ghi bao nhiêu, độ mới yêu cầu, dung lượng và tính nhất quán phải giữ**.

Một mô tả đủ hữu ích cần ít nhất:

- **Thao tác:** point lookup, range scan, join, update có điều kiện, bulk ingest, aggregation, traversal, full-text hoặc nearest-neighbor search.
- **Khóa truy cập:** ID, tenant_id, time range, status, foreign key, text term, graph node, vector.
- **Tần suất:** số request/giây trung bình, đỉnh, read/write ratio, burst.
- **Kích thước:** hàng, payload, kết quả trả về, lưu trữ và retention.
- **Độ trễ:** p50/p95/p99 và deadline, không chỉ trung bình.
- **Tính mới:** đọc ngay sau ghi hay chấp nhận dữ liệu trễ vài giây/phút.
- **Tính đúng:** transaction nhiều hàng/bảng, UNIQUE, FOREIGN KEY, CHECK, isolation, idempotency.
- **Vận hành:** HA, restore, RPO/RTO, monitoring, ACL, encryption, multi-region.
- **Diễn tiến:** migration, backfill, quyền truy cập mới, thay đổi query trong 6–24 tháng.
- **Chi phí:** năng lực đội ngũ, dịch vụ quản lý, network, storage, read/write amplification, khả năng di chuyển dữ liệu.

### 3.1. Mẫu bảng access-pattern inventory

| ID | Luồng | Dữ liệu | Cách truy cập | Tải mục tiêu minh họa | Tính nhất quán |
|---|---|---|---|---|---|
| AP-1 | Tạo đơn | orders + order_items | Ghi nhiều hàng, dùng operation_id | 300 đơn/s đỉnh | Atomic, không ghi trùng |
| AP-2 | Xem đơn | orders + items | Theo tenant_id + order_id | 2.000 req/s đỉnh | Read-your-writes cho khách vừa đặt |
| AP-3 | Danh sách đơn | orders | tenant + status, created_at desc | 900 req/s đỉnh | Phân trang ổn định |
| AP-4 | Tìm sản phẩm | catalog | Full-text + filter + ranking | 1.500 req/s đỉnh | Chấp nhận trễ cập nhật có kiểm soát |
| AP-5 | Sự kiện click | events | Append theo thời gian | 20.000 events/s đỉnh | Có idempotency/retention |
| AP-6 | Báo cáo tuần | orders + events | Aggregate nhiều tháng | 20 truy vấn/phút | Trễ ETL vài phút được |
| AP-7 | Gợi ý tương tự | embeddings | Similarity + quyền tenant | 100 req/s | Chấp nhận index cập nhật trễ |

**Toàn bộ con số là giả định để minh họa cách định nghĩa yêu cầu**, không phải benchmark hay khuyến nghị sản phẩm. Bảng này cho thấy một dịch vụ thương mại có **nhiều kiểu truy cập**, không nhất thiết nên đưa tất cả vào một loại storage.

### 3.2. Đừng chỉ ghi average load

Một hệ thống trung bình 50 request/giây có thể tăng lên 2.000 request/giây khi sale. Nếu chỉ benchmark tải trung bình, quyết định về index, partitioning, kết nối và số node sẽ sai.

Cần thêm:

- Peak và burst dài bao lâu.
- Tỷ lệ hàng nóng: 5% SKU chiếm 80% giao dịch có thể tạo lock contention.
- Kích thước hàng p95/p99 thay vì chỉ trung bình.
- Query distribution: 95% point lookup nhưng 5% chạy full scan lớn vẫn có thể chiếm phần lớn CPU.
- Khác biệt theo tenant: một tenant doanh nghiệp có thể lớn hơn hàng nghìn tenant nhỏ.

## 4. Từ workload đến mô hình dữ liệu

Một lựa chọn storage tốt thường bắt đầu bằng mô hình **thực thể, bất biến và đường truy cập**.

Ví dụ đặt hàng:

~~~text
Customer (id, tenant_id)
        |
        | 1-n
        v
Order (id, tenant_id, operation_id, status, created_at)
        |
        | 1-n
        v
OrderItem (order_id, sku, quantity, price)

Inventory (tenant_id, sku, available_quantity)
~~~

Nghiệp vụ có thể yêu cầu:

1. Một đơn thuộc đúng một tenant.
2. Mỗi order_item thuộc một order đã tồn tại.
3. Một operation_id chỉ được xử lý theo giao thức chống trùng đã xác định.
4. Không bán vượt tồn kho khi có nhiều transaction cạnh tranh.
5. Tạo đơn và items phải commit/rollback cùng nhau.
6. Danh sách đơn truy vấn theo tenant và thời gian, có điều kiện status.
7. Khách hàng vừa đặt đơn phải nhìn thấy đơn khi API xác nhận thành công.

Nếu **đa số thao tác phụ thuộc ràng buộc và transaction xuyên các thực thể liên quan**, RDBMS là một **ứng viên mạnh cần thử trước**, không phải vì “SQL luôn tốt” mà vì các chức năng native có thể khớp yêu cầu.

Nếu phần catalog thường được đọc thành **một tài liệu tự chứa** với cấu trúc thuộc tính thay đổi theo nhóm sản phẩm, một document store có thể là ứng viên cho **catalog read model**. Nhưng cần xác định việc cập nhật nhiều tài liệu, index và joins xảy ra thường xuyên đến mức nào.

### 4.1. Aggregate boundary khác với bảng hoặc collection

**Aggregate** là ranh giới nhất quán theo domain: những đối tượng nào cần thay đổi như một đơn vị nghiệp vụ. Nó **không tự động trùng** với một bảng SQL hoặc một document.

Ví dụ, một đơn với vài chục dòng hàng có thể phù hợp để lưu một document nếu phần lớn thao tác là đọc/ghi cả đơn; nhưng nếu có hàng triệu dòng con, update từng dòng độc lập, nhiều truy vấn lọc xuyên con và ràng buộc đối chiếu với tồn kho, việc nhúng toàn bộ có thể gây khó khăn.

Không quyết định **embed hay reference** chỉ vì “document DB ưu tiên embed”; quyết định dựa trên vòng đời, kích thước, tần suất thay đổi và tính nguyên tử thực tế.

## 5. Các loại kho dữ liệu giải quyết bài toán nào?

Bảng sau so sánh **kiểu công cụ**, không khẳng định một sản phẩm bất kỳ có hoặc thiếu tuyệt đối một tính năng. Các DBMS hiện đại thường mở rộng nhiều tính năng ngoài nhãn cơ bản.

| Kiểu kho | Phù hợp khi | Cần kiểm chứng cẩn thận |
|---|---|---|
| **Relational OLTP** | Quan hệ, joins, constraints, transaction đa hàng/bảng, truy vấn hỗn hợp | Index, lock, contention, partition, query plan và scale |
| **Document database** | Aggregate dạng tài liệu, cấu trúc linh hoạt, đọc/ghi tài liệu nguyên khối | Join, transaction đa document, tăng kích thước document, index và query cross-aggregate |
| **Key-value store** | Lookup theo key, session/cache, counter hoặc trạng thái đơn giản | Truy vấn ngoài key, TTL, eviction, durability và replication |
| **Wide-column/distributed partitioned store** | Ghi/phân vùng theo khóa ở quy mô lớn, query định hình trước, phân phối rộng | Hot partition, partition key, consistency levels, query ad hoc và read repair |
| **Search engine/index** | Full-text, ranking, faceting, filtering và search relevance | Near-real-time indexing, unique constraints, write source of truth và consistency |
| **Time-series database** | Dữ liệu theo thời gian, ingest liên tục, retention, downsampling | High cardinality, late-arriving data, update/delete và join nghiệp vụ |
| **Graph database** | Traversal nhiều bước, đường đi, quan hệ biến thiên, phát hiện cộng đồng | Đường traversal không giới hạn, super-node, scale và consistency |
| **Columnar/analytical warehouse** | Scan/aggregate dữ liệu lớn, BI/OLAP, batch queries | Point updates, low-latency OLTP, transaction trên luồng ghi nhỏ |
| **Vector index/database** | Approximate nearest neighbor, semantic retrieval | Recall, filter, freshness, quyền truy cập, embedding version, exact-match |
| **Object storage** | File, blob, snapshot, backup, dữ liệu phân tích dạng đối tượng | Transaction nhỏ, predicate query, khóa ngoại, lookup latency |

Một kho có thể hỗ trợ nhiều loại truy vấn, và một dịch vụ managed có thể kết hợp index, cache và pipeline. Do đó **loại kho cho biết hướng thử nghiệm, không thay thế benchmark**.

### 5.1. RDBMS không bị loại chỉ vì dữ liệu là JSON

PostgreSQL có **JSONB** và indexing thích hợp cho một số truy vấn. Nếu một entity cần cả khóa ngoại/transaction mạnh và vài thuộc tính mở rộng, có thể lưu thuộc tính trong JSONB bên cạnh các cột quan trọng. Tuy nhiên, JSONB không miễn việc thiết kế schema, index, validation, versioning hoặc quản lý dữ liệu nhạy cảm.

Ngược lại, dùng PostgreSQL chỉ vì nhóm đã quen SQL rồi nhồi hàng trăm tỷ sự kiện vào một bảng không partition/retention/index phù hợp cũng là **technology-first design** theo hướng ngược lại.

### 5.2. Một sản phẩm không tự đại diện cho mọi thuộc tính của một nhóm

Ví dụ:

- Document DB có thể hỗ trợ transaction đa tài liệu ở một số cấu hình, nhưng cần đo overhead và giới hạn áp dụng.
- Key-value service có thể hỗ trợ conditional write/transaction trong phạm vi nhất định, nhưng không biến nó thành cơ sở dữ liệu quan hệ với join tùy ý.
- Search engine có hỗ trợ cập nhật tài liệu và một số kiểm soát phiên bản, nhưng không vì vậy tự trở thành nguồn giao dịch chính an toàn cho mọi nghiệp vụ.
- PostgreSQL có full-text và vector extension tùy triển khai; có thể đủ cho nhu cầu search ban đầu mà chưa cần thêm một hệ thống vận hành riêng.

**Không đánh giá bằng khẩu hiệu “có” hoặc “không có transaction”**; phải xem transaction **trên những key/document/partition nào**, ở isolation nào, khi failover ra sao và giới hạn chi phí tại tải mong đợi.

## 6. Khi nào mô hình quan hệ thường hợp lý?

Một ứng dụng có nhiều **foreign keys**, uniqueness, joins theo tenant, transaction tạo/sửa nhiều thực thể và truy vấn thay đổi theo nghiệp vụ thường có lợi khi dùng relational OLTP.

Ví dụ schema PostgreSQL:

~~~sql
CREATE TABLE orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    operation_id TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('CREATED', 'PAID', 'CANCELLED')),
    total_amount NUMERIC(14, 2) NOT NULL
        CHECK (total_amount >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (tenant_id, operation_id)
);

CREATE TABLE order_items (
    order_id BIGINT NOT NULL REFERENCES orders(id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(14, 2) NOT NULL
        CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Lược đồ chứng minh một số bất biến ở mức DB:

- Một order không thể có total_amount âm.
- Một operation_id được lặp trong cùng tenant sẽ bị UNIQUE chặn.
- Order item không thể tham chiếu order không tồn tại.
- Một line_no không bị trùng trong cùng order.

Đây là các **ràng buộc của ví dụ**, không có nghĩa đã kiểm tra toàn bộ nghiệp vụ. Kiểm tra tổng tiền khớp các dòng, quyền tenant, trạng thái hợp lệ và idempotency khi retry còn phải được thiết kế.

### 6.1. Một truy vấn phải dựa trên access pattern cụ thể

Người dùng liệt kê đơn **PAID** của tenant 7, mới nhất trước:

~~~sql
SELECT id, status, total_amount, created_at
FROM orders
WHERE tenant_id = ?
  AND status = ?
ORDER BY created_at DESC, id DESC
LIMIT ?;
~~~

Với workload truy vấn này, một index ứng viên:

~~~sql
CREATE INDEX orders_tenant_status_created_id_idx
ON orders (tenant_id, status, created_at DESC, id DESC);
~~~

Index phù hợp vì điều kiện **equality trên tenant_id và status** đứng trước các cột sắp xếp. **Không phải cứ tạo index là DB chắc sử dụng**: optimizer còn phụ thuộc thống kê, phân bố dữ liệu, kích thước bảng, số row trả về và selectivity. Index cũng tăng chi phí INSERT/UPDATE và storage.

**Dấu ? là placeholder JDBC**, không phải cú pháp chạy SQL console nguyên văn. Khi chạy trực tiếp trong PostgreSQL cần bind bằng prepared statement hoặc dùng giá trị cụ thể.

### 6.2. Khi tìm theo tenant nhưng không lọc status

Index ở trên không nhất thiết tối ưu cho truy vấn:

~~~sql
SELECT id, status, total_amount, created_at
FROM orders
WHERE tenant_id = ?
ORDER BY created_at DESC, id DESC
LIMIT ?;
~~~

Vì có cột status nằm giữa tenant_id và created_at trong composite index, thứ tự các row cho nhiều status có thể không đáp ứng trực tiếp ORDER BY mong muốn. Tùy workload, có thể cần thêm index:

~~~sql
CREATE INDEX orders_tenant_created_id_idx
ON orders (tenant_id, created_at DESC, id DESC);
~~~

**Không tạo cả hai chỉ mục theo thói quen.** Đếm query thực, đo EXPLAIN/latency và chi phí ghi trước. Đây là ví dụ cho thấy **một kho dữ liệu hợp lý vẫn cần thiết kế đường truy cập**, không chỉ chọn đúng nhãn PostgreSQL.

### 6.3. Phân trang bằng keyset khi dữ liệu lớn

OFFSET lớn có thể khiến database phải xét nhiều hàng trước đó. Với sắp xếp **created_at DESC, id DESC**, ứng dụng có thể dùng keyset:

~~~sql
SELECT id, status, total_amount, created_at
FROM orders
WHERE tenant_id = ?
  AND status = ?
  AND (created_at, id) < (?, ?)
ORDER BY created_at DESC, id DESC
LIMIT ?;
~~~

Tuple comparison ở đây phù hợp với thứ tự giảm dần của cả hai cột và điều kiện seek “nhỏ hơn cursor” theo thứ tự từ điển. Cần dùng cursor từ hàng cuối trang trước, xử lý timestamp/id nhất quán và hiểu ảnh hưởng của concurrent inserts/updates tới pagination. **Keyset không tự đảm bảo snapshot nhất quán giữa các request**; nó chỉ là một lựa chọn truy cập thường tốt cho deep pagination.

## 7. Bất biến và transaction quan trọng hơn tên sản phẩm

Giả sử checkout cần:

1. Tạo order.
2. Ghi các order_items.
3. Giảm tồn kho.
4. Ghi outbox event OrderCreated.
5. Commit cùng nhau.

Nếu tất cả cùng một PostgreSQL database, có thể đặt trong **một transaction** để cùng commit/rollback. Bất biến “không bán hàng đã hết” cần câu UPDATE có điều kiện và kiểm tra số hàng ảnh hưởng.

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - ?
WHERE tenant_id = ?
  AND sku = ?
  AND available_quantity >= ?
RETURNING available_quantity;
~~~

Nếu trả về **không có hàng**, tồn kho không đủ hoặc SKU/tenant không tồn tại theo query; service cần phân biệt theo hợp đồng. Nếu cập nhật tồn kho phải commit cùng order, đừng dùng autocommit riêng cho mỗi câu.

### 7.1. Nếu dữ liệu chia nhiều kho thì sao?

Nếu orders ở relational database, inventory ở document database và outbox ở một service khác, **một JDBC transaction cục bộ không commit nguyên tử qua tất cả**. Có thể dùng saga, outbox, idempotency và giao thức bù trừ, nhưng tăng độ phức tạp và mở ra những trạng thái trung gian.

Sự phức tạp đó đôi khi đáng giá khi các domain có yêu cầu thực sự khác biệt và quy mô vận hành đủ lớn. Tuy nhiên, **không nên tạo phân tán đa kho chỉ vì mỗi dịch vụ muốn dùng một công nghệ “hot”**.

### 7.2. Tính bền vững là một ràng buộc riêng

Một cache hoặc memory-oriented store có thể có persistence/replication theo cấu hình, nhưng không được giả định nó đáp ứng RPO/RTO hoặc durability tương đương database giao dịch nếu chưa kiểm chứng cơ chế ghi, snapshot, WAL/AOF, failover và backup.

Trong mọi lựa chọn, hỏi rõ:

- Khi JVM/process crash, bản ghi nào phải còn?
- Khi database host hoặc zone bị mất, RPO bao nhiêu?
- Có cần đọc ngay sau COMMIT từ replica không?
- Làm thế nào restore một bản ghi bị xóa nhầm?
- Có backup độc lập/retention và restore drill không?

**Durability, consistency và availability có thể đánh đổi theo công cụ/cấu hình**, nhưng phải ghi rõ trade-off trước khi chọn.

## 8. Document database: linh hoạt không đồng nghĩa không cần mô hình

Document database phù hợp khi đối tượng thường được đọc/ghi dưới dạng **aggregate tự chứa**, cấu trúc có phần biến thiên và query đã biết tương đối rõ.

Ví dụ sản phẩm catalog:

~~~json
{
  "productId": "P-101",
  "tenantId": 7,
  "name": "Tai nghe Bluetooth",
  "category": "electronics",
  "attributes": {
    "color": "black",
    "batteryHours": 24,
    "bluetoothVersion": "5.3"
  }
}
~~~

Tài liệu này tiện cho truy vấn **productId → toàn bộ product**, đặc biệt khi thuộc tính biến thiên theo ngành hàng. Nhưng “có JSON” chưa đủ để chọn document database.

### 8.1. Những câu hỏi cần trả lời

- Kích thước document tối đa kỳ vọng là bao nhiêu?
- Có cần update từng phần hay thường thay toàn bộ document?
- Trường nào phải được index và truy vấn kết hợp?
- Có thường xuyên joins/aggregations qua nhiều documents không?
- Bất biến nào cần transaction xuyên documents?
- Query theo tenant, status, time và quyền được thực thi thế nào?
- Có cần version/migration document, validate và backfill không?
- Document cũ được xử lý ra sao khi thêm field?
- Database bảo đảm consistency/transaction gì ở deployment đã chọn?

**Schema-less không có nghĩa không có schema.** Java vẫn phải giải mã tài liệu, kiểm tra field bắt buộc, xử lý missing/null, migration và tương thích giữa các version.

### 8.2. Khi embedding thành nút thắt

Một document order chứa hàng triệu **shipment events** cập nhật liên tục có thể quá lớn, gây write contention hoặc vượt giới hạn document. Nếu truy vấn chính là sự kiện theo thời gian, nên cân nhắc collection/table riêng với partition/index. Ngược lại, đơn có vài dòng và luôn đọc cùng nhau có thể phù hợp để embed.

### 8.3. Benchmark phải bao phủ query thật

Benchmark chỉ lấy document theo productId dễ bỏ qua filter nhiều thuộc tính, sort, phân trang, aggregate và update con. Phải đo **tập query đại diện**, không chỉ một point lookup.

## 9. Key-value và cache: nhanh nhưng có phải nguồn sự thật?

Key-value store có thể phù hợp cho cache, session ngắn hạn, rate limiting hoặc lookup theo key. Phải phân biệt **cache** với **system of record**.

~~~text
Java API
   |
   +-- Cache GET product:123
   |      |
   |      +-- HIT -> trả theo freshness policy
   |      +-- MISS -> đọc database gốc, điền cache
   |
   +-- Authoritative database
          -> transaction, constraints, backup, restore
~~~

Cache-aside giảm tải đọc nhưng tạo thêm các vấn đề: invalidation, TTL, stale reads, cache stampede, eviction, network errors, tenant isolation và serialization.

### 9.1. Sai lầm: cập nhật cache trước khi database commit

~~~text
SET cache:inventory:SKU-1 = 0
      |
      v
UPDATE inventory trên database -> thất bại
      |
      v
Cache và database mâu thuẫn
~~~

Không xem **SET thành công trong cache** là bằng chứng transaction DB đã commit. Cần quy định invalidation, idempotency hoặc dùng outbox/CDC cho read model, với eventual consistency đã được chấp nhận rõ.

### 9.2. Khi key-value làm nguồn dữ liệu gốc

Điều này có thể hợp lý nếu thao tác chính theo key và hệ thống hỗ trợ đúng conditional writes, durability, replication, backup và consistency cần thiết. Nhưng không được mặc định một cache có TTL/eviction đã có cùng RPO/RTO với kho nghiệp vụ.

## 10. Search index: tra cứu khác giao dịch

Tìm kiếm sản phẩm có thể đòi relevance ranking, phân tích ngôn ngữ, synonyms, typo tolerance và faceting theo màu/giá/thương hiệu. Search engine phù hợp làm **read-optimized index**, nhưng thường không nên coi nó là nguồn duy nhất cho đơn hàng, tồn kho hay số dư mà chưa phân tích tính nguyên tử, uniqueness và độ mới dữ liệu.

~~~text
PostgreSQL (nguồn sự thật)
    |
    +-- Transaction tạo/cập nhật catalog
    +-- Outbox/CDC/indexer
                |
                v
          Search index
                |
          Full-text / ranking
                |
                v
             Search API
~~~

### 10.1. Trễ lập chỉ mục là một phần hợp đồng

Sản phẩm vừa cập nhật có thể chưa xuất hiện ngay trong search index. Nếu màn hình quản trị yêu cầu **read-your-writes**, API có thể đọc bản authoritative, hiển thị trạng thái đang index hoặc đợi checkpoint trong deadline.

### 10.2. Search không tự xử lý dual-write

~~~text
COMMIT PostgreSQL -> thành công
Update search index -> network timeout
~~~

Source đã commit mà index lỗi thì search có thể thiếu thay đổi. Một phương án là **transactional outbox/CDC + consumer idempotent**, theo dõi backlog và rebuild khi cần.

Với nhu cầu tìm kiếm đơn giản, thử PostgreSQL full-text/trigram trước khi vận hành search cluster riêng. Nhưng khi relevance, ngôn ngữ, filter và tải vượt SLO, engine chuyên dụng có thể đáng giá. Phải đo thay vì suy từ thương hiệu.

## 11. Time-series và event ingestion

Một hệ thống telemetry có dữ liệu:

~~~text
(device_id, timestamp, temperature, status, tenant_id)
~~~

Truy vấn thường gặp:

- Đọc mẫu trong một giờ của thiết bị.
- Aggregate min/max/average theo phút, ngày và tenant.
- Giữ raw trong 30 ngày, rollup trong một năm.
- Nhận sự kiện đến muộn hoặc gửi lặp.
- Ingest tốc độ cao với retention đã định.

Time-series DB có thể hỗ trợ partition/chunk, compression, retention/downsampling. Nhưng PostgreSQL partitioning hoặc extension phù hợp cũng có thể đáp ứng ở nhiều mức tải; phải thử với số liệu thực.

### 11.1. Câu hỏi khó

- Append-only hay cần update/delete dữ liệu cũ?
- Late events và out-of-order ingestion phổ biến không?
- Chống trùng theo event_id ở đâu?
- Cardinality labels/tags và tenants lớn thế nào?
- Có query time range sử dụng index/partition pruning được không?
- Cần join sang order/customer OLTP với tần suất nào?
- Retention và recovery raw so với rollup ra sao?

**Đừng trộn warehouse sự kiện với kho xử lý đơn chỉ vì cả hai dùng timestamp.**

### 11.2. Event streaming khác cơ sở dữ liệu point lookup

Message log như Kafka phù hợp cho truyền sự kiện, replay và decoupling, nhưng không tự đáp ứng query account balance theo khóa, foreign keys hay transaction đa bảng. Event sourcing là kiến trúc riêng với projection, ordering, idempotency và rebuild; không bắt Java service đọc lại hàng triệu messages chỉ để tìm một trạng thái.

## 12. Graph, vector và OLAP: phân biệt dữ liệu với thao tác

### 12.1. Graph database

Graph engine đáng cân nhắc khi truy vấn thực sự gồm **traversal nhiều bước**, đường đi, quan hệ nhiều loại cạnh và độ sâu thay đổi lúc thực thi. Ví dụ: phát hiện vòng gian lận, đường đi ngắn nhất, tìm cụm ảnh hưởng hoặc truy vết quan hệ.

Nhưng chỉ vì bảng có foreign key chưa đủ để chọn graph DB: RDBMS thực hiện joins tốt cho nhiều quan hệ có độ sâu cố định. Benchmark cần đo **branching factor, graph density, super-node, depth, mutation rate và memory**; traversal không giới hạn trên node có hàng triệu cạnh vẫn có thể rất đắt.

### 12.2. Vector index/database

Vector retrieval tìm các đối tượng gần nhau trong không gian embedding; phù hợp semantic search, retrieval-augmented generation và recommendation.

Nhưng **nearest neighbor không thay exact filtering và quyền truy cập**. Approximate search có **recall–latency trade-off**; model version, dimensionality, ACL và việc cập nhật/xóa tài liệu phải được quản lý.

Một kiến trúc có thể dùng PostgreSQL cho metadata/ACL, vector index cho candidate retrieval, rồi kiểm tra quyền trước khi trả kết quả. Với quy mô phù hợp, PostgreSQL cùng extension vector có thể đáp ứng cả hai. Không chọn vector database làm nguồn tiền tệ/đơn hàng chỉ vì có một index semantic search.

### 12.3. Kho phân tích columnar/OLAP

Dashboard phân tích doanh thu nhiều năm, hàng trăm triệu giao dịch có thể phù hợp một kho columnar hơn là truy vấn scan lớn trên primary OLTP.

~~~text
Order DB (OLTP)
    |
    +-- CDC / ETL / Batch có checkpoint
                |
                v
        Analytical warehouse
                |
          GROUP BY / BI / OLAP
~~~

Cần hỏi:

- Báo cáo chấp nhận trễ bao lâu?
- ETL xử lý correction, update và duplicate ra sao?
- PII được mask và bảo vệ khi sao chép chưa?
- Schema version nguồn thay đổi có làm hỏng pipeline không?
- Báo cáo nào đòi dữ liệu mới nhất theo snapshot thay vì eventual consistency?

Đừng đặt mọi báo cáo nặng lên primary chỉ để tránh công cụ thứ hai; nhưng cũng không cần thêm warehouse nếu vài COUNT/SUM nhỏ đã đạt SLO.

## 13. Polyglot persistence: thêm kho là thêm giao thức

**Polyglot persistence** có thể rất tốt khi mỗi kho giải quyết một access pattern rõ ràng, nhưng mỗi kho mới tạo thêm failure modes, monitoring, backup, quyền và pipeline đồng bộ.

~~~mermaid
flowchart LR
    API["Java Order / Catalog API"] --> DB["Relational authoritative DB"]
    DB --> OUTBOX["Transactional outbox"]
    OUTBOX --> PIPE["Dispatcher / CDC"]
    PIPE --> SEARCH["Search read index"]
    PIPE --> OLAP["Analytical warehouse"]
    API --> CACHE["Key-value cache"]
    CACHE -. "miss / invalidate" .-> DB
~~~

Mỗi mũi tên cần trả lời:

- Source commit nhưng consumer lỗi thì ai retry?
- Event trùng được nhận biết bằng ID nào?
- Ordering theo entity/tenant có được bảo đảm không?
- Có checkpoint và replay idempotent không?
- Khi index lỗi, có thể rebuild từ nguồn không?
- Thời gian stale tối đa theo hợp đồng API bao nhiêu?
- Xóa PII trên source thì các bản sao/cache/index xóa khi nào?

**Nhiều driver chạy trong cùng JVM không làm các datastore có một transaction nguyên tử.**

### 13.1. Dual-write không phải một transaction

Ví dụ:

~~~java
orderRepository.save(order);  // DB đã COMMIT.
searchClient.index(order);    // Network timeout.
~~~

Lúc này source đã đổi nhưng search index có thể chưa đổi. Nếu đảo thứ tự, search có thể hiện order mà DB sau đó rollback. Cách giải quyết thường dùng là:

1. Ghi order và **outbox event** trong cùng source transaction.
2. Dispatcher chuyển event đã commit sang search/analytics.
3. Consumer **idempotent** theo event_id, hiểu ordering và version.
4. Theo dõi lag/backlog và có quy trình rebuild.
5. Công bố consistency contract cho UI/API.

Outbox giảm khoảng trống dual-write nhưng **không tự bảo đảm exactly-once end-to-end**: consumer vẫn phải xử lý thông điệp được gửi lặp.

### 13.2. Không chuyển mọi thao tác sang queue theo trào lưu

Queue làm giảm coupling nhưng có thể khiến API chỉ trả **“đã nhận yêu cầu”** thay cho **“đã đặt hàng thành công”**. Nếu checkout cần xác nhận chắc chắn, phải thiết kế state machine, reservation, idempotency và giao thức bù trừ. Không tự thêm eventual consistency khi nghiệp vụ cần commit đồng bộ.

### 13.3. Xác định nguồn sự thật cho từng invariant

Nếu PostgreSQL và search index đều cho phép sửa trạng thái order độc lập, sẽ phát sinh xung đột khó đối soát. Quy tắc phổ biến là **một authoritative source cho mỗi invariant**, các projection có khả năng rebuild. Multi-master cũng có thể hợp lý nhưng phải định nghĩa rõ conflict resolution và failure model.

## 14. Java persistence boundary: domain không nên phụ thuộc tên DB

Định nghĩa repository theo **hợp đồng truy cập của nghiệp vụ**, không phải theo mọi thao tác tùy ý một backend tình cờ hỗ trợ.

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Optional;

public record OrderSummary(
        long id, String status, Instant createdAt) {}

public interface OrderQueryRepository {
    Optional<OrderSummary> findByTenantAndId(
            long tenantId, long orderId);

    List<OrderSummary> listRecent(
            long tenantId,
            String status,
            Instant beforeTime,
            long beforeId,
            int limit);
}
~~~

Trong Java, **JDBC/Spring JDBC** cho SQL tường minh; **JPA/Hibernate** giúp quản lý entity nhưng cần chú ý lazy loading, N+1 và flush; Spring Data/client chuyên biệt tiện thao tác kho nhưng không xóa khác biệt consistency, index hay transaction.

### 14.1. “Đổi driver là chuyển DB được” thường sai

Hai backend cùng có CRUD vẫn có thể khác:

- UNIQUE và transaction xuyên nhiều đối tượng.
- JOIN, aggregation, sort/pagination.
- Conditional updates và affected rows.
- Retryable errors, timeout, unknown commit outcome.
- Decimal, timestamp, JSON, identity mapping.
- Backup, failover, CDC, security và audit.
- Cost model, partitioning, indexing và query planner.

Abstraction giúp giảm coupling nhưng không biến các kho thành tương đương. Muốn đổi backend phải kiểm tra **repository contract**, migration dữ liệu và workload benchmark.

### 14.2. Generic repository có thể che giấu chi phí

Một phương thức **findAll()** dễ khiến Java tải hàng triệu records rồi filter trong bộ nhớ, hoặc tạo scan/fan-out trên store phân tán theo key. Thay vào đó, repository nên nói rõ **query shape, tenant predicate, projection, pagination và giới hạn kết quả**.

Đừng lựa chọn kho chỉ vì “Spring có starter”, hoặc cho rằng ORM tự tạo index đúng: repository abstraction không thay thế thiết kế access patterns.

## 15. Khả năng thay đổi truy vấn theo thời gian

Ngày đầu ứng dụng chỉ lookup bằng ID. Sau sáu tháng có thể cần lọc theo thời gian, phân quyền, phân tích, full-text hoặc báo cáo trên nhiều quan hệ. Không thể dự đoán tất cả, nhưng cần xem:

- Query ad hoc và quan hệ có tăng nhanh không?
- Optional attributes có biến động lớn không?
- OLAP có thể được tách khỏi OLTP về sau không?
- Partition key hiện tại có khiến query mới fan-out không?
- Có thể export/rebuild read model khi đổi công nghệ không?
- Java adapters có phụ thuộc API riêng của backend quá sâu không?
- Migration/index/backfill được làm dần mà không downtime không?
- Đội ngũ có đủ năng lực vận hành công nghệ mới không?

Một kho linh hoạt hơn có thể hữu ích khi access patterns chưa ổn định. Nhưng **một khả năng giả định trong tương lai không đủ để xây hệ thống phân tán phức tạp ngay ngày đầu**.

## 16. Quy trình lựa chọn kho dữ liệu theo bằng chứng

Một quy trình tốt không bắt đầu bằng slide so sánh logo công nghệ. Nó bắt đầu bằng **luồng nghiệp vụ quan trọng**, bất biến và số đo mà team sẽ phải chịu trách nhiệm sau khi deploy.

### Bước 1 — Xác định hệ thống có thẩm quyền và đối tượng dữ liệu

Liệt kê:

- Đối tượng nào đang là **source of truth**: orders, inventory, accounts, catalog, telemetry.
- Ai có quyền tạo/sửa/xóa và theo ranh giới tenant nào.
- Đơn vị nào phải commit nguyên tử.
- Khi mất dữ liệu hoặc restore nhầm mốc, hậu quả nghiệp vụ là gì.
- Những dữ liệu nào chỉ là projection/cache có thể xây lại.

Không chọn cache làm source of truth chỉ vì point lookup nhanh nếu nghiệp vụ không chấp nhận dữ liệu bị evict hoặc mất sau failover.

### Bước 2 — Ghi bảng read/write access patterns

Cho mỗi operation, ghi:

1. Query/command chính xác hoặc pseudo query.
2. Partition/shard/tenant key và predicate.
3. Payload size, result size, read/write ratio.
4. Throughput trung bình, đỉnh và burst.
5. p95/p99 SLO, deadline.
6. Freshness/consistency/durability cần thiết.
7. Growth và retention.
8. Các truy vấn mới dự kiến gần hạn.

Không dùng yêu cầu “scale 10 triệu người dùng” làm con số duy nhất: **10 triệu tài khoản không cho biết bao nhiêu giao dịch đồng thời, khóa nóng hay query nặng**.

### Bước 3 — Đặt điều kiện loại trừ bắt buộc

Một số yêu cầu **không được bù bằng điểm mạnh khác**. Ví dụ:

- Không thể chấp nhận ghi nửa giao dịch chuyển tiền.
- Cần quyền đọc phân biệt tenant và audit bắt buộc.
- RPO/RTO và restore drill phải đạt.
- Không được mất idempotency khi retry.
- Phải tuân thủ nơi lưu dữ liệu, mã hóa và retention.
- Database/driver phải được vận hành và hỗ trợ bởi đội hiện có hoặc nhà cung cấp được chấp thuận.

Đây là **gates**. Một kho rất nhanh nhưng không đáp ứng gate về transaction hoặc backup phải được loại khỏi vai trò nguồn dữ liệu chính, dù benchmark point lookup đạt 1 ms.

### Bước 4 — Chọn một số ứng viên có lý do

Đối với workload order:

- Ứng viên A: PostgreSQL relational OLTP, index theo tenant/status/time.
- Ứng viên B: document store với schema/order aggregate và chiến lược transaction.
- Ứng viên C: key-value/wide-column nếu query gần như hoàn toàn theo key và thật sự cần partition scale, với ranh giới consistency được chứng minh.

Không cần POC 20 sản phẩm. Chọn 2–3 phương án có khả năng đáp ứng yêu cầu, gồm **lựa chọn đơn giản nhất mà đội ngũ vận hành tốt**.

### Bước 5 — Benchmark có dữ liệu và failure modes đại diện

Chạy cùng business commands và queries, không chỉ so một lệnh GET hay INSERT tối giản. Gồm:

- Write transaction có parent/child và constraint.
- Truy vấn danh sách theo tenant/status/time, keyset pagination.
- Đọc ngay sau ghi, retry/duplicate ID.
- Dữ liệu nhiều tenant với skew/hot keys.
- Concurrency và peak burst.
- Backup/restore và failover phù hợp.
- Schema migration, thêm index, backfill.
- Error handling/recovery và vận hành.

### Bước 6 — Chọn với trade-off được ghi thành quyết định

Ghi rõ vì sao chọn, nhược điểm chấp nhận, tiêu chí đo lại, trách nhiệm team, phương án nếu workload tăng. Quyết định phải có thể review, không phụ thuộc một thành viên “thấy công nghệ mới hay”.

## 17. Ma trận đánh giá: đừng biến điểm số thành sự thật giả

Một ma trận có thể giúp so sánh phương án, nhưng không nên biến tính năng định tính thành con số 9.5/10 không có bằng chứng.

| Tiêu chí | Câu hỏi đánh giá | Bằng chứng nên có |
|---|---|---|
| Access fit | Truy vấn quan trọng có index/path hiệu quả không? | Query plan, latency, rows scanned |
| Atomicity | Có commit/rollback toàn đơn vị nghiệp vụ không? | Integration tests và failure injection |
| Data integrity | UNIQUE, constraints, conditional update xử lý ra sao? | Race tests, duplicate tests |
| Consistency | Read-after-write và replica freshness thế nào? | Consistency test, lag metrics |
| Scalability | Throughput đỉnh tại dữ liệu thật và skew? | Load test p95/p99, bottlenecks |
| Durability | RPO/RTO, backups, WAL, restore? | Restore drill và báo cáo |
| Security | Tenant isolation, roles, encryption, audit? | Access tests và policy review |
| Operability | Team có deploy/monitor/upgrade/recover được không? | Runbook, failure drill |
| Schema evolution | Thêm/đổi field hoặc index có gián đoạn? | Migration rehearsal |
| Cost | Tổng chi phí sở hữu khi tăng tải? | TCO model và dự báo |
| Portability | Có thể export/di chuyển mà không mất dữ liệu? | Proof of export/rebuild |
| Ecosystem Java | Driver, transaction manager, tracing? | Test integration và support policy |

### 17.1. Phân biệt gate và ưu tiên

Ví dụ:

- **Gate:** tạo order + items + inventory phải nguyên tử trong một DB, hoặc có giao thức thay thế đã phê duyệt.
- **Gate:** restore drill đạt mục tiêu RPO/RTO.
- **Ưu tiên:** p99 nhỏ hơn hoặc cost thấp hơn khi các gate đã đạt.

Nếu một phương án không đáp ứng gate, không cộng điểm tốc độ để “bù” cho rủi ro mất dữ liệu.

### 17.2. Có thể dùng trọng số nhưng phải khai báo giả định

Ví dụ nhóm chọn trọng số: correctness 35%, query fit 25%, performance 20%, operations 15%, cost 5%. Đây là **phương án tổ chức ưu tiên mang tính ví dụ**, không phải công thức chuẩn. Kết quả cần được xem lại khi workload và rủi ro đổi.

Một lựa chọn khác có thể ưu tiên latency hoặc TCO cao hơn, nhưng vẫn phải đạt các gate về an toàn dữ liệu và tuân thủ.

## 18. POC/benchmark đúng nghĩa: test workloads và consistency

### 18.1. Kịch bản ví dụ cho dịch vụ đơn hàng

Giả sử (con số **giả định**) cần:

- 300 create-order/s đỉnh, mỗi order trung bình 4 items.
- 2.000 point reads/s và 900 list queries/s.
- p99 create-order dưới 150 ms, list page dưới 120 ms.
- Tối đa 20 triệu orders hiện tại; 70% traffic thuộc 10% tenants lớn.
- Không được ghi trùng operation_id hay tạo order thiếu item.
- Cần đọc đơn vừa tạo ngay sau COMMIT trên API xác nhận.
- Backup/restore phải đáp ứng RPO/RTO do nghiệp vụ phê duyệt.

Một POC nên tạo dữ liệu có phân bố tenant/status/time giống kỳ vọng, bao gồm các **hot tenants** và đợt peak chứ không chỉ INSERT tuần tự vào bảng trống.

### 18.2. Kịch bản functional correctness

Không chỉ đo thời gian:

1. Chèn cùng operation ID từ hai request cạnh tranh.
2. Gây lỗi khi chèn item thứ hai, kiểm parent và items rollback.
3. Cập nhật tồn kho cùng SKU từ nhiều transaction, kiểm không âm.
4. Đọc ngay sau ghi từ đường route được công bố cho client.
5. Thử failover/reconnect, SQLSTATE handling và unknown COMMIT outcome.
6. Đo latency khi database đầy index, WAL nhiều và autovacuum đang hoạt động.
7. Kiểm tra backup và restore trên môi trường độc lập.

**Nếu một candidate không bảo vệ invariants theo yêu cầu, không được tuyên bố “đạt POC” chỉ vì throughput cao.**

### 18.3. Kịch bản PostgreSQL: xem plan thật

Với một fixture có quy mô và phân bố gần workload đích:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, status, total_amount, created_at
FROM orders
WHERE tenant_id = 7
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

**EXPLAIN ANALYZE thực sự thực thi truy vấn**. Ví dụ SELECT không thay đổi dữ liệu, nhưng nếu dùng trên DML, lệnh có thể làm thay đổi dữ liệu và cần transaction/test DB được kiểm soát.

Cần xem:

- Actual rows, estimated rows và chênh lệch ước lượng.
- Index scan/seq scan và nguyên nhân lựa chọn.
- Buffers read/hit, I/O, rows removed by filter.
- Planning/execution time, kích thước dữ liệu.
- Độ ổn định ở tenant nhỏ và tenant lớn.

Không so kết quả từ một bảng 20 hàng với workload 20 triệu hàng rồi chọn công nghệ dựa trên đó.

### 18.4. Thang đo có đơn vị rõ ràng

| Metric | Đo điều gì? |
|---|---|
| **orders/s** | Đơn được commit thành công mỗi giây |
| **rows written/s** | Số hàng ghi trên toàn hệ |
| **query p50/p95/p99** | Độ trễ từng đường query |
| **error/timeout rate** | Tỷ lệ lỗi và quá hạn |
| **connection/pool wait** | Chờ mượn connection |
| **lock wait/deadlock** | Tranh chấp transaction |
| **CPU/disk/network/WAL** | Tài nguyên tiêu thụ |
| **replication lag** | Khả năng phục vụ stale read/failover |
| **backup and restore duration** | RTO đo được |
| **bytes stored per business record** | Write amplification/index/storage |
| **cost per workload window** | Chi phí tại tải cụ thể |

**TPS giảm không nhất thiết có nghĩa hệ thống tệ hơn** nếu đã gom nhiều rows/transaction; **rows/s cao cũng không đủ** nếu p99 request nghiệp vụ vượt SLO hoặc ràng buộc dữ liệu bị phá.

## 19. Benchmark sai sẽ chọn nhầm database

Những lỗi phổ biến khi làm POC:

| Cách benchmark sai | Hậu quả |
|---|---|
| Chỉ đọc bằng ID | Không thấy chi phí query đa điều kiện/join |
| Chỉ INSERT vào DB trống | Không thấy index maintenance, WAL, vacuum và retention |
| Dùng payload nhỏ đồng nhất | Không bộc lộ tài liệu lớn hoặc hot partitions |
| Tải không có peak hoặc multi-tenancy | Không thấy skew, lock contention |
| So managed cluster mạnh với single node yếu | Kết luận công nghệ sai vì cấu hình không công bằng |
| Bật caching ở một phương án, tắt ở phương án khác | Đo cache thay vì database |
| Không chạy full transaction | Không đo đúng latency của nghiệp vụ |
| Không xác minh kết quả | Thông lượng cao vì ghi rơi hoặc thiếu dữ liệu |
| Không tính chi phí backup/failover | Lựa chọn rẻ giả tạo |
| Không có thời gian warm-up và lặp lại | Dễ bị ảnh hưởng cache, checkpoint, GC |
| Đo average mà bỏ p99 | Che tail latency và timeout |
| Không test schema migration | Chưa biết vận hành thay đổi dữ liệu thế nào |

**Benchmark phải công bằng về mục tiêu phục vụ**, không nhất thiết giống nhau về thông số phần cứng tuyệt đối. Điều quan trọng là chi phí/tài nguyên để mỗi phương án đáp ứng cùng nghiệp vụ và SLO.

### 19.1. Test dữ liệu lỗi và replay

Một kho phục vụ được 10.000 writes/s trong điều kiện không lỗi có thể không phù hợp nếu failover gây mất các giao dịch mà nghiệp vụ yêu cầu bền vững. Cần đo khả năng phục hồi và bất biến khi:

- Transaction timeout.
- Node restart hoặc loss of connectivity.
- Replica chậm hoặc chuyển vai trò.
- Schema version cũ/mới cùng hoạt động.
- Consumer outbox nhận lặp hoặc thiếu tạm thời.
- Restore và đối soát dữ liệu.

**Tính đúng khi gặp lỗi là một phần của kết quả POC**, không phải việc để sau khi đã chọn sản phẩm.

## 20. Case study: chọn kho cho ứng dụng thương mại Java

Giả sử nhóm có các chức năng:

- Khách đặt hàng và xem đơn theo ID.
- Nhân viên lọc đơn theo tenant/status/date.
- Catalog có thuộc tính sản phẩm linh hoạt.
- Người dùng tìm sản phẩm bằng từ khóa.
- Hệ thống thu thập click/view events để làm báo cáo.
- Có thể bổ sung semantic search trong tương lai.

Không nên quyết định “công ty làm thương mại điện tử, vậy phải dùng document DB cho tất cả”. Hãy phân tích theo từng đơn vị.

### 20.1. Orders và order_items

Yêu cầu: tạo đơn + dòng hàng nguyên tử, UNIQUE operation ID theo tenant, foreign key, transaction đồng thời, truy vấn lọc và phân trang. **Ứng viên khởi đầu hợp lý:** PostgreSQL relational OLTP với index theo access patterns và integration tests.

Đây không phải khẳng định PostgreSQL thắng mọi quy mô. Nếu workload thực tế vượt một node, có thể đánh giá partitioning, vertical scaling, read replicas, sharding hoặc hệ phân tán khác **trên bằng chứng bottleneck**, thay vì nhảy thẳng sang giải pháp đắt nhất.

### 20.2. Catalog

Yêu cầu: tìm bằng product ID, cập nhật một số optional attributes, lọc theo category và tenant. Hai phương án có thể thử:

- **PostgreSQL với cột chính + JSONB** cho optional attributes, index theo truy vấn.
- **Document database** nếu aggregate đơn giản, thay đổi cấu trúc nhiều và các truy vấn document fit tốt.

Đánh giá cả nhu cầu joins, số update đa document, tenant filtering, indexing, schema evolution và TCO. Đừng chọn document chỉ vì payload API là JSON.

### 20.3. Search

Yêu cầu: full-text, ranking, synonyms và facet. Bắt đầu kiểm thử PostgreSQL full-text nếu scope nhỏ. Khi không đạt relevance/latency SLO, bổ sung search index riêng với outbox/CDC.

Search index là **projection có thể xây lại**, không cho phép ghi trạng thái đơn hàng vào search như nguồn sự thật cạnh tranh.

### 20.4. Clickstream/analytics

Yêu cầu: append nhiều, retention ngắn cho raw, aggregate theo ngày/tenant. Có thể thu vào event pipeline, lưu raw ở object/time-series store và phân tích bằng warehouse. Cần biết ingest peak, late events, PII và độ trễ báo cáo chấp nhận được.

Không đặt báo cáo aggregate lớn trực tiếp trên transaction-critical primary khi nó gây giảm SLO đặt hàng.

### 20.5. Recommendation/semantic search

Chỉ khi có nhu cầu và dữ liệu thực, mới benchmark vector similarity, recall và ACL. Lựa chọn có thể là extension vector trong PostgreSQL hoặc index chuyên biệt. Cần quản lý embedding version và update/delete; không migrate transactional orders sang vector store.

### 20.6. Quyết định giai đoạn đầu có thể ít hệ thống hơn dự kiến

Một bản thiết kế **đơn giản nhưng có đường mở rộng**:

~~~text
                 Java Services
                      |
            +---------+---------+
            |                   |
      PostgreSQL OLTP      Optional Cache
       authoritative       read acceleration
            |
        Outbox events
            |
            +--> Search projection (khi thật sự cần)
            +--> Analytics pipeline (khi tải báo cáo cần)
            +--> Vector projection (khi feature được xác nhận)
~~~

Giai đoạn đầu chỉ cần PostgreSQL và monitoring/backup phù hợp nếu các access patterns đã đạt SLO. Các kho phụ trợ được thêm **khi có bằng chứng** và có chiến lược xây lại từ nguồn, thay vì dựa trên trào lưu.

### 20.7. Một quyết định lưu trữ không loại bỏ nhu cầu thiết kế tốt

Dù chọn PostgreSQL, vẫn có thể làm sai:

- Không index cột tenant/status/time dùng thường xuyên.
- ORM tải toàn bộ order_items theo N+1 queries.
- Transaction giữ khóa qua HTTP call.
- Thiếu unique operation ID và retry mù khi COMMIT chưa rõ.
- Không có migrations/backup/restore drills.
- Truy vấn báo cáo lâu trên primary vào giờ cao điểm.

**Chọn đúng nhóm kho chỉ là điểm bắt đầu; access path, transaction boundary và vận hành quyết định tính đúng thực tế.**

## 21. Tổng chi phí sở hữu (TCO) và vận hành

Giá niêm yết theo GB hoặc request là một phần nhỏ của quyết định. Tổng chi phí có thể bao gồm:

| Nhóm chi phí | Câu hỏi |
|---|---|
| Compute/requests | P99/peak cần bao nhiêu node/CPU/throughput? |
| Storage | Bản sao, index, WAL, snapshot, tiering, compression |
| Network | Cross-AZ/region replication, egress và ETL |
| Backup/retention | Kho độc lập, encryption, restore tests |
| Migration | Chuyển dữ liệu cũ, dual-write, backfill và downtime |
| Operations | Upgrade, failover, monitoring, incident response |
| Developer productivity | Debug query, transaction, mapping và SDK |
| Security/compliance | IAM, key rotation, audit, data residency |
| Data movement | CDC/outbox, pipelines, replay, schema versioning |
| Lock-in | Thay sản phẩm có tốn bao nhiêu thời gian/chuyển đổi? |

Một sản phẩm có giá request thấp nhưng cần thêm một đội vận hành, một ETL pipeline và ba bản sao có thể **đắt hơn** một PostgreSQL managed đáp ứng cùng SLO.

Ngược lại, một kho chuyên dụng có thể tiết kiệm đáng kể ở quy mô lớn nhờ query/retention phù hợp. Kết luận phải dựa trên **chi phí tại workload dự kiến và khả năng tăng trưởng**, không phải niềm tin chung “managed = rẻ” hay “open source = miễn phí”.

### 21.1. Tính cả chi phí khi hệ thống gặp lỗi

- Khi index cần rebuild, mất bao lâu và ai trực xử lý?
- Khi primary chết, có failover an toàn theo RPO không?
- Khi một shard nóng, có cách phân tải không gián đoạn không?
- Khi backup hỏng, restore test có phát hiện từ trước không?
- Khi cần xóa dữ liệu người dùng, có kiểm soát được các bản sao/backup/index không?

Một lựa chọn đạt latency trung bình tốt nhưng không có runbook và restore được thử nghiệm vẫn có rủi ro vận hành cao.

## 22. Kế hoạch đổi kho dữ liệu nếu quyết định ban đầu không còn phù hợp

Dù quyết định hiện tại đúng, access patterns có thể đổi. Cần tính trước **khả năng tiến hóa**, không phải sợ thay đổi tới mức chọn kiến trúc quá phức tạp từ đầu.

### 22.1. Migration không đơn giản là export rồi import

Chuyển từ PostgreSQL sang document store có thể cần:

1. Định nghĩa model document/aggregate mới và khóa truy cập.
2. Migrate dữ liệu cũ, kiểm đếm và đối soát giá trị.
3. Xây index, constraint thay thế hoặc validation ở tầng ứng dụng.
4. Cập nhật Java repository adapter và transaction boundaries.
5. Đồng bộ cập nhật phát sinh trong lúc backfill.
6. Kiểm tra tenant isolation, authorization và dữ liệu nhạy cảm.
7. Thử failover, timeout, unknown COMMIT outcome và retry.
8. Tổ chức cutover, rollback plan và cleanup.

Với nhiều backend cùng hoạt động, dual-write dễ phát sinh khác biệt; cần CDC/outbox, idempotency và reconciliation theo từng giai đoạn.

### 22.2. Mẫu migration có kiểm chứng

~~~text
Source of truth hiện tại
          |
          +-- Snapshot/backfill có checkpoint
          |
          +-- CDC/outbox theo dõi thay đổi mới
                     |
                     v
              Target datastore
                     |
               So sánh dữ liệu
                     |
               Shadow reads/queries
                     |
            Canary read traffic
                     |
            Controlled cutover
                     |
            Decommission sau rollback window
~~~

Không tự ghi song song với hai nguồn sự thật mà chưa quyết định cách xử lý xung đột. Trong quá trình canary, có thể đọc target ở chế độ shadow rồi so sánh với source mà **không dùng kết quả target để quyết định nghiệp vụ** cho tới khi đạt tiêu chí.

### 22.3. Tiêu chí dừng hoặc quay lại

- Tỷ lệ mismatch dữ liệu vượt ngưỡng.
- p99 hoặc error rate vượt SLO.
- Event backlog không bắt kịp.
- Tenant/ACL test thất bại.
- Backup/restore target chưa đạt.
- Không xử lý được retry/unknown commit outcome.
- Tổng chi phí vận hành vượt phạm vi phê duyệt.

**Rollback window phải được thiết kế trước**, nhất là khi app đã bắt đầu ghi những field mà datastore cũ chưa biểu diễn được.

## 23. Bảo mật, tenant isolation và compliance là access patterns bắt buộc

Một kho chỉ được chọn sau khi trả lời những câu hỏi này:

1. Mỗi query theo tenant có bị kiểm soát ở điểm truy cập đúng không?
2. Kho có role/policy/permission đáp ứng mô hình phân quyền không?
3. Ai có thể truy cập backup, replica và search projection?
4. Có mã hóa khi truyền, lưu, quản lý khóa và rotate không?
5. Có audit theo user/service và trace tới transaction không?
6. PII bị loại/mask trong cache, analytics, vector index và logs chưa?
7. Có dữ liệu nào phải ở một region theo quy định áp dụng không?
8. Có hỗ trợ xóa/retention nhất quán qua các bản sao theo chính sách không?

### 23.1. Search và vector index không được bỏ qua ACL

Một retrieval index có thể trả candidates thuộc nhiều tenants. Nếu service chỉ lọc quyền **sau khi** đã đưa snippet hoặc embedding metadata vào logs/response, có thể lộ dữ liệu trước khi lọc.

Cần đưa tenant/ACL filters vào query và **kiểm tra quyền trước khi trả kết quả** bằng nguồn đáng tin, tùy mô hình; đồng thời kiểm thử trường hợp index chưa nhận bản cập nhật quyền mới.

### 23.2. Phân vùng không tự bằng phân quyền

Dùng shard key = tenant_id không tự bảo đảm một tenant không đọc nhầm data của tenant khác. Java queries, authorization, connection routing, row-level security (nếu dùng) và integration tests đều phải thống nhất.

Khi một request thiếu tenant predicate hoặc route sai shard, hậu quả có thể là **data leak**, không chỉ latency tăng.

### 23.3. Backup và phục hồi là một phần lựa chọn kho

Một managed DB có backup tự động nhưng chưa biết bản backup phục hồi được hay không thì chưa đủ đánh giá durability. Cần test restore đến mốc đã cam kết, đo RPO/RTO, xem cơ chế encryption, quyền và retention. Đừng so chi phí kho chỉ theo khả năng ghi, bỏ qua recovery.

## 24. Dấu hiệu nhận biết lựa chọn công nghệ theo trào lưu

| Phát biểu/thiết kế | Vấn đề | Câu hỏi sửa |
|---|---|---|
| “Ai cũng dùng NoSQL để scale.” | Không có workload/consistency model | Query và peak load thực sự là gì? |
| “Dữ liệu JSON phải ở document store.” | Nhầm serialization với storage design | Đọc/ghi aggregate và joins như thế nào? |
| “Redis nhanh, dùng làm database chính luôn.” | Bỏ qua durability/eviction/restore | RPO/RTO và dữ liệu nào được mất? |
| “Elastic/search đủ cho orders.” | Nhầm index tra cứu với nguồn giao dịch | UNIQUE, transaction và cập nhật tức thời ở đâu? |
| “Vector DB là nơi lưu mọi tài liệu.” | Bỏ qua ACL, exact search và source of truth | Embedding index đóng vai trò nào? |
| “Có nhiều quan hệ nên tất cả phải graph.” | Không xét query traversal thật | Query có chiều sâu biến thiên không? |
| “Cứ shard trước để chuẩn bị scale.” | Tăng complexity trước khi cần | Bottleneck hiện tại và ngưỡng kích hoạt? |
| “Mỗi microservice chọn DB riêng theo sở thích.” | Nhiều semantics, dual-write và ops | Mỗi store giải quyết access pattern nào? |
| “ORM sẽ làm query nhanh.” | N+1/index/transaction không tự biến mất | EXPLAIN và query count có gì? |
| “Cloud managed sẽ xử lý tất cả backup.” | Không đo restore/RPO | Có restore drill và kiểm WAL/manifest không? |
| “Benchmark chỉ cần lấy một key thật nhanh.” | Không đại diện business workload | Các read/write paths phổ biến và critical là gì? |
| “Thêm index để chữa mọi query.” | Tăng write cost và storage | Index nào phục vụ predicate/sort cụ thể? |
| “Nếu DB không đủ nhanh, thêm cache.” | Che query/lock vấn đề và thêm stale data | Query plan/transaction bottleneck ban đầu? |
| “Read replica luôn có dữ liệu mới nhất.” | Bỏ qua replication lag | Read consistency contract là gì? |
| “Đổi DB chỉ cần đổi dependency.” | Chênh lệch semantics, schema, query | Contract tests và migration plan ở đâu? |
| “Data store nào cũng có transaction giống nhau.” | Phạm vi/level/durability khác nhau | Những key nào commit cùng nhau, dưới isolation nào? |
| “Đã có event broker thì không cần database.” | Nhầm event log với read model | Query state hiện tại được phục vụ từ đâu? |
| “Đến lúc cần mới tính vận hành.” | Backup, IAM, incidents tốn lớn | Ai chịu SLO/on-call/restore? |

Điểm chung của các sai lầm là **lấy tính năng nổi bật của sản phẩm thay cho chứng cứ về khả năng đáp ứng nghiệp vụ cụ thể**.

## 25. Bài tập tình huống

### Bài 1 — Chọn theo nhãn NoSQL

Một nhóm có 200 đơn/s ở đỉnh, cần tạo đơn + dòng hàng + giảm tồn kho nguyên tử, nhưng muốn dùng một key-value store vì đọc theo ID rất nhanh. Điều gì phải được xác minh trước khi chọn?

**Gợi ý:** đơn vị transaction, conditional writes, consistency, uniqueness, truy vấn danh sách theo tenant/status/time, recovery, và p99 toàn nghiệp vụ. Point lookup nhanh không đủ.

### Bài 2 — JSON có cần document DB?

Catalog lưu thuộc tính tùy loại sản phẩm, nhưng cũng cần join với tồn kho và pricing, lọc theo tenant, và có quan hệ rõ ràng. Có nhất thiết phải chuyển hết từ PostgreSQL sang document DB không?

**Gợi ý:** không. So sánh PostgreSQL cột + JSONB với document model, index và truy vấn thực; tách catalog read model chỉ khi có lợi ích rõ.

### Bài 3 — Redis làm nguồn chính

Ứng dụng lưu số dư ví điện tử vào cache có eviction và TTL. Một cache node bị mất khiến số dư không còn. Đây chỉ là lỗi hiệu năng hay còn là lỗi dữ liệu?

**Gợi ý:** nếu cache là nguồn duy nhất, đây là lỗi durability nghiêm trọng. Cần source of truth, transaction, backup/restore và failover theo RPO.

### Bài 4 — Search cập nhật trễ

Sau khi đổi tên sản phẩm thành công ở PostgreSQL, API search chưa thấy tên mới trong 3 giây. Lỗi này có phải lúc nào cũng sai?

**Gợi ý:** phụ thuộc freshness contract. Với search eventually consistent có thể chấp nhận; với read-your-writes ở màn quản trị cần route hoặc UX phù hợp. Đo indexing lag.

### Bài 5 — Hai kho và một nghiệp vụ

Một service ghi order ở database A và inventory ở database B, sau khi A COMMIT thì B timeout. Có thể gọi cả nghiệp vụ nguyên tử không?

**Gợi ý:** không qua một JDBC transaction cục bộ. Cần thiết kế saga, reservation, bù trừ, idempotency hoặc thay đổi ranh giới dữ liệu.

### Bài 6 — Thêm graph DB

Một bảng customers có quan hệ customer_orders và orders_items, nhưng các truy vấn chủ yếu là join cố định hai bước. Có cần graph DB?

**Gợi ý:** chưa đủ cơ sở. Đo SQL joins hiện tại; graph DB phù hợp hơn khi traversal đa bước biến thiên và dữ liệu/độ sâu thực sự yêu cầu.

### Bài 7 — Vector search và ACL

Semantic search trả tài liệu có score cao nhưng metadata tenant chưa kịp cập nhật. API có được trả snippet trước khi kiểm tra quyền không?

**Gợi ý:** không. ACL phải được thực thi theo nguồn đáng tin trước khi lộ nội dung; stale index là rủi ro bảo mật, không chỉ chất lượng search.

### Bài 8 — Chỉ benchmark inserts

Nhóm đo 100.000 INSERT/s trên database trống, tuyên bố có thể phục vụ checkout. Thiếu gì?

**Gợi ý:** transaction thật, parent/child constraints, contention, index cost, p99, select queries, backup/restore, failure/retry và dữ liệu đại diện.

### Bài 9 — Peak và tenant skew

Một DB đạt average 500 req/s, nhưng 3 tenant lớn tạo 80% tải và query theo tenant chạm partition nóng. Nên kiểm tra gì?

**Gợi ý:** phân bố key, index/partition design, hot-key contention, peak burst, p99 theo tenant; không chỉ tăng node.

### Bài 10 — Kho phân tích

Một báo cáo doanh thu quét 200 triệu rows làm API đặt hàng chậm. Có nên chuyển toàn bộ transaction sang warehouse?

**Gợi ý:** thường không; giữ nguồn giao dịch ở OLTP, thử query/index/replica phù hợp và tách analytical read model/ETL nếu cần. Kiểm freshness và đối soát.

### Bài 11 — Đổi driver

Ứng dụng chuyển sang document store bằng cách đổi implementation OrderRepository, nhưng trước đây dùng foreign keys và transaction parent/child. Unit test vẫn xanh. Đủ điều kiện deploy chưa?

**Gợi ý:** chưa. Cần contract/integration tests của invariant, transaction, query, migration, backup và xử lý lỗi theo backend mới.

### Bài 12 — Backup tự động

Managed datastore cung cấp daily snapshot, chưa ai từng thử khôi phục. Có thể coi đã đáp ứng RTO 30 phút không?

**Gợi ý:** không. RTO phải đo end-to-end bằng restore drill; còn cần xét RPO, điểm phục hồi, khóa giải mã và quyền.

### Bài 13 — Phân tích chi phí

Hai phương án có cùng p99 và correctness trên workload đại diện. A rẻ hơn tiền compute nhưng đòi đội tự vận hành cluster và CDC; B dùng managed service có phí cao hơn. Nên so thế nào?

**Gợi ý:** TCO gồm on-call, backup, migration, security, network, incident recovery, nhân lực và khả năng scale; không chỉ đơn giá compute.

### Bài 14 — Khi nào thay công nghệ?

PostgreSQL vẫn đạt SLO hiện tại, nhưng nhóm muốn chuyển ngay sang distributed database vì dự đoán một ngày có 100 triệu users. Cần yêu cầu bằng chứng nào?

**Gợi ý:** dự báo truy vấn và peak thực, giới hạn đã đo, phương án scale đơn giản hơn, cost/failure modes và tiêu chí kích hoạt thay đổi. Dự đoán user count không đủ.

### Bài 15 — Mất dữ liệu sau COMMIT chưa rõ

Java gửi COMMIT, mất mạng, đọc replica thấy chưa có order nên retry bằng operation_id mới. Có thể gây gì?

**Gợi ý:** primary có thể đã commit, replica còn trễ. Retry bằng ID mới có thể ghi trùng. Cần ID ổn định, đối soát trên nguồn có thẩm quyền, đọc đúng consistency contract.

### Bài 16 — Yêu cầu dữ liệu mới

Ứng dụng cần đọc kết quả sau ghi tức thì nhưng chọn search index eventual consistency làm nguồn trả lời. Có những phương án nào?

**Gợi ý:** đọc primary, đợi index checkpoint trong deadline, hoặc thay đổi UX/API contract. Không hứa strong consistency khi kiến trúc không cung cấp.

## 26. Mẫu bản ghi quyết định kiến trúc (ADR)

Một bản **Architecture Decision Record** giúp quyết định kho dữ liệu được xem lại sau này. Mẫu ngắn:

~~~text
ADR-007: Kho lưu trữ giao dịch cho Order Service

Trạng thái: Proposed / Accepted / Superseded
Ngày quyết định: YYYY-MM-DD
Chủ sở hữu: Nhóm Order Platform

Bối cảnh:
- 300 create-order/s peak, 2.000 point reads/s.
- Query tenant + status + time; 20 triệu orders dự kiến.
- Order + items + inventory phải bảo đảm bất biến.
- p99 create-order mục tiêu 150 ms.
- RPO/RTO, quyền tenant và audit bắt buộc theo chính sách.

Các phương án:
A. PostgreSQL relational với index và backup.
B. Document store với transaction/constraint tương ứng.
C. Distributed key-value với mô hình dữ liệu mới.

Điều kiện loại trừ:
- Không được ghi nửa đơn hàng.
- Phải xử lý operation_id trùng và COMMIT chưa rõ.
- Restore drill đạt mục tiêu.
- Tenant isolation được chứng minh qua test.

Bằng chứng:
- Workload trace/fixture và peak benchmark.
- Query plans, p95/p99, lock waits, error rates.
- Transaction/failover/restore tests.
- TCO và năng lực vận hành.

Quyết định:
- Chọn A cho order authoritative source
  NẾU các số đo thực tế đạt gates/SLO.
- Search/analytics là read projections có thể rebuild.
- Không dùng cache làm nguồn dữ liệu gốc.

Trade-offs:
- Cần quản lý index, lock contention, WAL/backup.
- Có thể phải phân vùng/shard khi workload tăng.
- Projection bất đồng bộ có indexing lag.

Triggers xem lại:
- p99 hoặc error rate vượt SLO liên tục.
- Capacity/lock hot spots không xử lý bằng index/scale.
- Workload query thay đổi đáng kể.
- RPO/RTO hoặc quy định dữ liệu thay đổi.

Kế hoạch kiểm tra:
- POC, integration tests, restore drill, canary.
- Review định kỳ sau số liệu production.
~~~

Đây là **mẫu có điều kiện**, không phải một bản quyết định đã được thông qua; các con số trong ví dụ cần thay bằng thực tế. Một ADR tốt ghi cả **những điều đã không chọn** và lý do, không chỉ chốt một tên database.

### 26.1. Checklist trước khi ký quyết định

- [ ] Có inventory các read/write operations và peak load.
- [ ] Có tính nguyên tử/nhất quán/durability bắt buộc.
- [ ] Có danh sách những candidate thỏa gates.
- [ ] Có POC dùng data skew và query đại diện.
- [ ] Có test lỗi, retry, failover, backup/restore.
- [ ] Có chi phí sở hữu và người trực vận hành.
- [ ] Có phương án schema migration và tenant security.
- [ ] Có lý do thêm từng datastore ngoài nguồn sự thật.
- [ ] Có contract dữ liệu trễ và idempotency cho projections.
- [ ] Có điều kiện xem lại quyết định và cách kiểm chứng.

Không phải mọi đội đều cần một ADR dài hàng chục trang. Điều quan trọng là **dự đoán rủi ro, tiêu chí đánh giá và bằng chứng có thể kiểm tra**.

## 27. Tổng kết

**Lựa chọn kho dữ liệu theo trào lưu** là lỗi bắt đầu từ tên công nghệ rồi cố ép domain, query và transaction vào nó. Cách tiếp cận phù hợp hơn là đi từ **access patterns → bất biến và SLO → candidate stores → POC với dữ liệu/tải đại diện → kiểm thử lỗi và restore → quyết định có trade-off rõ**.

RDBMS thường là ứng viên mạnh cho giao dịch có quan hệ, ràng buộc và truy vấn hỗn hợp; document, key-value, search, time-series, graph, vector và analytical stores đều có chỗ đứng khi **truy vấn thực tế** chứng minh lợi ích. Không có một hệ thống lưu trữ tốt nhất cho mọi dữ liệu, và cũng không có lý do bắt buộc một ứng dụng phải dùng nhiều kho chỉ để thể hiện tính hiện đại.

Với Java, hãy thiết kế **persistence boundary theo nghiệp vụ**, viết repository methods phục vụ query cụ thể, dùng transaction đúng mức, theo dõi SQL và lỗi, bảo đảm backup/restore và đánh giá tính nhất quán khi thêm projection. **Đừng để một nhãn “SQL”, “NoSQL”, “cloud-native” hoặc “AI-ready” thay thế bằng chứng về dữ liệu đúng, truy vấn đủ nhanh và hệ thống có thể phục hồi.**

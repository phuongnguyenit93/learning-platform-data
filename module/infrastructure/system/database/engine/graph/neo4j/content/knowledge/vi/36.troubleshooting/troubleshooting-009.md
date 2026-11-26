# Chỉ mục chưa sẵn sàng hoặc không được bộ lập kế hoạch lựa chọn

Một truy vấn Cypher chạy chậm không nhất thiết do Neo4j “bỏ qua index”. Có hai nhóm sự cố rất khác nhau: **index chưa thể phục vụ truy vấn** vì đang được xây dựng hoặc lỗi, và **index đã sẵn sàng nhưng query planner không chọn nó** vì ước lượng chi phí, kiểu điều kiện, dạng dữ liệu hoặc cấu trúc query. Nếu nhầm hai nhóm, đội vận hành có thể liên tục xóa/tạo lại index mà không cải thiện hiệu năng, thậm chí làm tăng tải và thời gian gián đoạn.

Bài thuộc chương **Xử lý sự cố** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Neo4j lưu node, relationship và property theo mô hình **property graph**, sử dụng Cypher để tìm quan hệ và đường đi, index/constraint để tăng tốc tra cứu và bảo vệ bất biến, và tích hợp Java Driver cùng Spring Data Neo4j trong ứng dụng. Trọng tâm ở đây là nhận diện đúng nguyên nhân, đo kế hoạch thực thi và khắc phục có kiểm chứng, không tối ưu truy vấn theo cảm tính.

Sau bài học, bạn có thể:

- Kiểm tra `SHOW INDEXES`, phân biệt trạng thái `ONLINE`, `POPULATING`, `FAILED` và thông báo lỗi.
- Đọc `EXPLAIN`/`PROFILE` để biết planner đang dùng index seek, index scan hay label scan.
- Giải thích vì sao một index đang `ONLINE` vẫn không được chọn: selectivity, composite key, function trên property, index type, parameter type, predicate và tính toán sau traversal.
- Phân biệt range, text, full-text, point, lookup, vector và relationship index ở mức sử dụng cần thiết.
- Xây runbook an toàn cho index đang tạo, index lỗi, query plan bất ngờ và hồi quy hiệu năng sau triển khai.
- Đưa kiểm tra index vào quy trình migration, giám sát và kiểm thử Java Driver/Spring Data Neo4j.

> **Phạm vi:** ví dụ hướng đến những dòng Neo4j 5.x và mới hơn có hỗ trợ cú pháp tương ứng; cột `SHOW INDEXES`, tên toán tử kế hoạch, index provider và các tính năng full-text/vector có thể khác theo phiên bản. Lệnh quản trị/schema chỉ chạy trên database thực hành hoặc sau quy trình thay đổi được phê duyệt. Bài không yêu cầu có GDS.

## 1. Bắt đầu từ triệu chứng, không bắt đầu bằng DROP INDEX

Một lỗi được báo “index không chạy” có thể mang nhiều ý nghĩa:

| Triệu chứng quan sát được | Khả năng chính | Kiểm tra đầu tiên |
| --- | --- | --- |
| Vừa tạo index nhưng query vẫn chậm. | Index đang `POPULATING` hoặc chưa sẵn sàng. | `SHOW INDEXES` và tiến độ population. |
| `SHOW INDEXES` báo `FAILED`. | Lỗi xây index hoặc lỗi tài nguyên/dữ liệu/provider. | `failureMessage`, log và disk/I/O. |
| Index `ONLINE` nhưng `PROFILE` báo label scan. | Planner chọn scan vì cost thấp hơn hoặc predicate không dùng được index. | Điều kiện `WHERE`, cardinality, type, plan. |
| Một query nhanh với tham số A, chậm với tham số B. | Phân bố giá trị lệch, fan-out, kiểu tham số hoặc query plan chưa phù hợp. | So sánh plan, Rows, DB Hits theo tập tham số đại diện. |
| Index xuất hiện trong plan nhưng query vẫn chậm. | Truy vấn tốn chi phí ở expansion, sort, aggregation, eager hoặc network. | Toàn bộ `PROFILE`, không chỉ toán tử đầu tiên. |
| Index hoạt động trên staging nhưng không ở production. | Khác dữ liệu, phiên bản, database, schema, thống kê hoặc tải. | Xác nhận database và môi trường, so baseline. |
| Sau migration có lỗi uniqueness hoặc không tạo được index. | Dữ liệu không đáp ứng constraint, thiếu tài nguyên hoặc lệnh không hợp lệ. | Thông báo lỗi cụ thể và dữ liệu trùng/thiếu. |
| Query tìm kiếm nội dung không dùng full-text index. | Full-text không được tự động chọn cho `WHERE` thông thường. | Kiểm tra API/procedure tìm kiếm tương ứng. |

**Luật an toàn:** đừng xóa các tệp index từ filesystem, không xóa constraint để “thử tốc độ”, không drop/recreate index quan trọng khi chưa ghi nhận tên, chủ sở hữu và đường khôi phục. Một uniqueness constraint có thể phụ thuộc index; thay đổi nó còn liên quan tính toàn vẹn dữ liệu.

## 2. Sơ đồ chẩn đoán tổng quát

~~~text
Query chậm hoặc nghi ngờ không dùng index
                    |
                    v
     Xác nhận database + query + parameters
                    |
                    v
        SHOW INDEXES theo tên/schema
                    |
       +------------+--------------+
       |            |              |
   POPULATING     FAILED         ONLINE
       |            |              |
       v            v              v
   Theo dõi       Kiểm tra    EXPLAIN / PROFILE
   tiến độ        nguyên nhân      |
   và tải         + khắc phục      v
                           +------+------+
                           |             |
                      Không dùng      Có dùng
                        index           index
                           |             |
                           v             v
                     Kiểm predicate   Tìm phần đắt:
                     / type / cost    expand / sort /
                     / stats          aggregate / I/O
                           |             |
                           +------+------+
                                  |
                                  v
                       Đo lại trên dữ liệu
                       đại diện + ghi baseline
~~~

Một lời giải thích có giá trị phải gắn với **bằng chứng**: tên index, trạng thái tại thời điểm đo, câu query và parameter shape, plan, Rows, DB Hits, thời gian/p95 và ảnh hưởng sau thay đổi.

## 3. Bộ dữ liệu thực hành có thể tái tạo

Ta dùng hai loại node và một loại relationship:

~~~text
(:IndexDemoUser {
  tenantId, userId, emailNorm,
  displayName, active, bio
})
        |
        | [:INDEX_DEMO_PLACED]
        v
(:IndexDemoOrder {
  tenantId, orderId, createdAt,
  status, amountMinor
})
~~~

Quy ước:

- `tenantId` tách phạm vi tổ chức.
- `userId` và `orderId` là khóa nghiệp vụ trong tenant.
- `emailNorm` là địa chỉ email đã chuẩn hóa bằng quy tắc được ứng dụng phê duyệt.
- `createdAt` là thời điểm đặt hàng.
- Cạnh `INDEX_DEMO_PLACED` có hướng **User → Order**.

Chỉ chạy các lệnh tạo dữ liệu sau trong **database test có quyền thay đổi schema**, không dùng label này cho dữ liệu sản xuất. Fixture có email thuộc miền `example.test` và tên giả định.

### 3.1. Constraint và index demo

~~~cypher
CREATE CONSTRAINT idx_demo_user_key IF NOT EXISTS
FOR (u:IndexDemoUser)
REQUIRE (u.tenantId, u.userId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT idx_demo_order_key IF NOT EXISTS
FOR (o:IndexDemoOrder)
REQUIRE (o.tenantId, o.orderId) IS UNIQUE;
~~~

~~~cypher
CREATE RANGE INDEX idx_demo_user_tenant_email IF NOT EXISTS
FOR (u:IndexDemoUser)
ON (u.tenantId, u.emailNorm);
~~~

~~~cypher
CREATE RANGE INDEX idx_demo_order_tenant_created IF NOT EXISTS
FOR (o:IndexDemoOrder)
ON (o.tenantId, o.createdAt);
~~~

Hai constraint bảo vệ uniqueness của cặp khóa khi property có giá trị. **Uniqueness thông thường không đồng nghĩa existence constraint**: ứng dụng vẫn cần kiểm tra tính có mặt của property khóa hoặc sử dụng loại constraint được edition/phiên bản hỗ trợ. Các range index dùng cho tra cứu dựa trên thuộc tính, không tự làm mọi traversal qua relationship trở nên nhanh.

### 3.2. Nạp node

~~~cypher
UNWIND [
  {
    tenantId:'T1', userId:'U01',
    emailNorm:'an@example.test',
    displayName:'An Nguyễn', active:true,
    bio:'Quan tâm đến cơ sở dữ liệu đồ thị'
  },
  {
    tenantId:'T1', userId:'U02',
    emailNorm:'binh@example.test',
    displayName:'Bình Trần', active:true,
    bio:'Tìm hiểu Cypher và Java'
  },
  {
    tenantId:'T1', userId:'U03',
    emailNorm:'chi@example.test',
    displayName:'Chi Phạm', active:false,
    bio:'Ứng dụng dữ liệu liên kết'
  },
  {
    tenantId:'T1', userId:'U04',
    emailNorm:'dung@example.test',
    displayName:'Dung Lê', active:true,
    bio:'Tìm kiếm văn bản'
  },
  {
    tenantId:'T2', userId:'U01',
    emailNorm:'another@example.test',
    displayName:'An Tổ chức khác', active:true,
    bio:'Tổ chức độc lập'
  }
] AS row
MERGE (u:IndexDemoUser {
  tenantId: row.tenantId,
  userId: row.userId
})
SET u.emailNorm = row.emailNorm,
    u.displayName = row.displayName,
    u.active = row.active,
    u.bio = row.bio;
~~~

~~~cypher
UNWIND [
  {orderId:'O01', userId:'U01',
   at:'2026-01-05T10:00:00Z', amount:125000, status:'PAID'},
  {orderId:'O02', userId:'U01',
   at:'2026-01-07T14:00:00Z', amount:34000, status:'PAID'},
  {orderId:'O03', userId:'U01',
   at:'2026-02-11T09:00:00Z', amount:99000, status:'OPEN'},
  {orderId:'O04', userId:'U02',
   at:'2026-01-22T08:00:00Z', amount:77000, status:'PAID'},
  {orderId:'O05', userId:'U02',
   at:'2026-03-01T15:00:00Z', amount:50000, status:'OPEN'},
  {orderId:'O06', userId:'U03',
   at:'2026-02-14T07:00:00Z', amount:12000, status:'CANCELLED'},
  {orderId:'O07', userId:'U04',
   at:'2026-03-12T12:00:00Z', amount:32000, status:'PAID'}
] AS row
MATCH (u:IndexDemoUser {
  tenantId:'T1',
  userId:row.userId
})
MERGE (o:IndexDemoOrder {
  tenantId:'T1',
  orderId:row.orderId
})
SET o.createdAt = datetime(row.at),
    o.amountMinor = row.amount,
    o.status = row.status
MERGE (u)-[:INDEX_DEMO_PLACED]->(o);
~~~

Kiểm tra fixture:

~~~cypher
MATCH (u:IndexDemoUser)
RETURN u.tenantId AS tenantId,
       count(u) AS userCount
ORDER BY tenantId;
~~~

~~~cypher
MATCH (u:IndexDemoUser {tenantId:'T1'})
      -[r:INDEX_DEMO_PLACED]->
      (o:IndexDemoOrder {tenantId:'T1'})
RETURN count(r) AS relationships,
       count(DISTINCT o) AS orders;
~~~

Với fixture mới, kỳ vọng **T1 có 4 user, T2 có 1 user** và **T1 có 7 relationship đến 7 order**. Trên tập nhỏ như vậy, planner có thể **chủ động chọn label scan vì rẻ hơn**; đó không phải bằng chứng index bị lỗi. Để đo hiệu năng, cần dữ liệu test lớn và phân bố bậc/thuộc tính đại diện.

## 4. Index có vòng đời: chưa sẵn sàng khác với không được chọn

Neo4j xây dựng các index theo trạng thái. Khi tạo index trên dữ liệu đã có, quá trình population có thể chưa hoàn thành ngay.

### 4.1. Truy vấn trạng thái

~~~cypher
SHOW INDEXES
YIELD name, type, entityType,
      labelsOrTypes, properties,
      state, populationPercent
RETURN name, type, entityType,
       labelsOrTypes, properties,
       state, populationPercent
ORDER BY name;
~~~

Có thể lọc theo tên cụ thể:

~~~cypher
SHOW INDEXES
YIELD name, type, state, populationPercent
WHERE name = 'idx_demo_user_tenant_email'
RETURN name, type, state, populationPercent;
~~~

| Trạng thái | Ý nghĩa thường gặp | Hành động |
| --- | --- | --- |
| **`POPULATING`** | Neo4j đang xây các entry cần thiết. | Theo dõi tiến độ, I/O, CPU, disk và lỗi; không tuyên bố index sẵn sàng. |
| **`ONLINE`** | Index đã sẵn sàng cho những truy vấn/kiểu điều kiện mà nó hỗ trợ. | Tiếp tục xem query plan; `ONLINE` không đảm bảo planner dùng index. |
| **`FAILED`** | Index không hoàn tất hoặc gặp lỗi khiến không dùng được. | Thu thập thông báo lỗi, log, phiên bản và tình trạng tài nguyên trước khi sửa. |

Một số phiên bản cho phép `SHOW INDEXES YIELD failureMessage` để xem lỗi:

~~~cypher
SHOW INDEXES
YIELD name, state, failureMessage
WHERE state = 'FAILED'
RETURN name, state, failureMessage;
~~~

Nếu bản đang dùng không hỗ trợ một cột, hãy xem kết quả `SHOW INDEXES YIELD *` và tài liệu phiên bản thay vì dựa vào tên cột được ghi nhớ. Thông báo lỗi chỉ nên được gửi tới kênh vận hành có quyền vì có thể chứa thông tin kỹ thuật hoặc dữ liệu nhạy cảm.

### 4.2. Index vừa tạo có sẵn sàng ngay không?

Không phải lúc nào cũng vậy. Trên đồ thị lớn, index có thể mất thời gian population. Nếu pipeline deployment chạy:

~~~text
CREATE INDEX
  -> Ngay lập tức chạy traffic nặng
  -> Query chậm hoặc kế hoạch truy cập chưa như kỳ vọng
~~~

thì nên thêm **bước chờ có giới hạn thời gian và xác minh `ONLINE`** trước khi bật những tính năng phụ thuộc index. Ở các phiên bản hỗ trợ, Neo4j có procedure tiện ích:

~~~cypher
CALL db.awaitIndexes(300);
~~~

Đây là ví dụ chờ tối đa khoảng 300 giây theo cách procedure được phiên bản cung cấp. Không dùng giá trị timeout đó làm SLA mặc định cho mọi index. Một index full-text/vector trên hàng triệu bản ghi có thể cần thời gian và dung lượng khác hẳn range index trên tập nhỏ.

**Điều kiện vượt gate:** index quan trọng `ONLINE` **và** query nghiệp vụ có plan/latency chấp nhận được. Chỉ đợi procedure thành công mà không kiểm tra query thật vẫn có thể bỏ sót planner không chọn index.

## 5. Runbook A — Index đang POPULATING quá lâu

### 5.1. Xác nhận đúng index và tiến trình

Ghi lại:

- Tên database và tên index.
- Loại index, label/type, property và index provider nếu có.
- Trạng thái và tỷ lệ `populationPercent` ở nhiều thời điểm.
- Thời gian đã population, tốc độ thay đổi và so sánh với lần trước.
- Dung lượng data/index, disk free, CPU, I/O latency và lượng ghi đồng thời.

Nếu tỷ lệ population tăng chậm nhưng ổn định, có thể chỉ là công việc lớn. Nếu không tăng hoặc log báo lỗi, tiếp tục điều tra **nguyên nhân**, không suy ra lỗi chỉ vì phần trăm chưa tới 100.

### 5.2. Tìm nguyên nhân theo nhóm

| Nhóm | Dấu hiệu | Hướng kiểm tra |
| --- | --- | --- |
| Data volume lớn | Cần đọc/đánh chỉ mục nhiều node hoặc relationship. | Kiểm tra số lượng dữ liệu và baseline population. |
| Disk thiếu chỗ | Free bytes thấp, I/O error, index FAILED. | Xem volume chứa database/index/temp; tăng headroom an toàn. |
| I/O saturation | Disk queue lớn, latency p95/p99 tăng. | So khớp với import, backup, job ghi và giới hạn storage. |
| CPU/memory pressure | GC, OOM, throttling hoặc bộ nhớ thiếu. | Xem memory/page cache/CPU thực, không chỉ RAM host. |
| Loại index đặc biệt | Full-text analyzer hoặc vector dimension/type cần quy tắc riêng. | Kiểm tra cú pháp, provider và property được index. |
| Concurrent writes | Import liên tục cập nhật các property đang được index. | Quan sát write rate, thông lượng index population và cửa sổ maintenance. |
| Storage/cluster | Volume/network/backend chậm, thành viên phân bố khác nhau. | Kiểm trạng thái từng server, volume và đường tới storage. |

### 5.3. Hành động an toàn

1. Đảm bảo đủ dung lượng và khả năng backup trước khi chỉnh schema.
2. Ước lượng impact của việc chờ so với tạm hoãn tính năng đang phụ thuộc index.
3. Tạm giảm job ghi/import không thiết yếu nếu đã phê duyệt và có thể làm an toàn.
4. Thu thập log để xác định index có lỗi thực sự hay chỉ chưa hoàn thành.
5. Chỉ quyết định rebuild khi đã biết nguyên nhân và có cửa sổ bảo trì.
6. Sau khi `ONLINE`, đo query plan và p95/p99 thay vì chỉ xem phần trăm.

**Không làm:** xóa trực tiếp file index, hạ retention transaction log tùy tiện, lặp `DROP/CREATE INDEX` trong khi volume đầy hoặc drop index thuộc constraint mà không hiểu hậu quả.

## 6. Runbook B — Index FAILED

Trạng thái `FAILED` cần được xử lý như một **sự cố schema có bằng chứng**, không phải một thông báo chung “database chậm”.

### 6.1. Thu thập dữ liệu trước khi thay đổi

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes,
      properties, state, failureMessage
WHERE state = 'FAILED'
RETURN name, type, entityType, labelsOrTypes,
       properties, state, failureMessage;
~~~

Kiểm tra thêm catalog constraint:

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;
~~~

Một index được tạo để hỗ trợ uniqueness/constraint không thể coi là một index phụ có thể xóa tự do. Cấu trúc index và constraint có quan hệ sở hữu/chu kỳ riêng; cần kiểm tra `owningConstraint` nếu cột được phiên bản cung cấp, hoặc đối chiếu catalog schema.

### 6.2. Phân loại lỗi

- **Lỗi tài nguyên:** hết disk, I/O error, memory pressure, quyền tệp, storage backend.
- **Lỗi xây schema/constraint:** dữ liệu trùng khi tạo uniqueness constraint, property không đáp ứng yêu cầu hoặc loại index không hỗ trợ cách dùng.
- **Lỗi provider/configuration:** cấu hình index hoặc analyzer không hợp lệ, sai tương thích phiên bản/provider/plugin, lỗi trong quá trình migration.
- **Lỗi vận hành:** process bị ngắt giữa xây index, phiên bản rollout không đồng nhất hoặc trạng thái recovery cần xử lý theo công cụ.

**Đừng đoán** nguyên nhân từ trạng thái `FAILED`. Đọc thông báo lỗi và log; nếu nghi ngờ lỗi engine/corruption, dùng quy trình hỗ trợ Neo4j và giữ bằng chứng thay vì thử thao tác file.

### 6.3. Vì sao uniqueness khác index thông thường?

Giả sử có hai node:

~~~text
(:IndexDemoUser {tenantId:'T1', userId:'U01'})
(:IndexDemoUser {tenantId:'T1', userId:'U01'})
~~~

Khi tạo:

~~~cypher
CREATE CONSTRAINT idx_demo_user_key IF NOT EXISTS
FOR (u:IndexDemoUser)
REQUIRE (u.tenantId, u.userId) IS UNIQUE;
~~~

việc tạo constraint có thể thất bại vì dữ liệu trùng. Khi đó cần **xác minh chính xác khóa, giữ dữ liệu nghiệp vụ và xử lý trùng có kiểm soát**, không đổi sang một index thông thường để che vi phạm uniqueness. Một range index không thay thế ràng buộc duy nhất.

### 6.4. Recreate có điều kiện

Đối với index thường **được xác nhận không thuộc constraint**, sau khi đã backup, kiểm tra tải và chọn cửa sổ thay đổi, có thể cân nhắc:

~~~cypher
// Ví dụ CHỈ trên database test, khi index thường này
// được xác nhận không thuộc constraint.
DROP INDEX idx_demo_user_tenant_email IF EXISTS;
~~~

~~~cypher
CREATE RANGE INDEX idx_demo_user_tenant_email IF NOT EXISTS
FOR (u:IndexDemoUser)
ON (u.tenantId, u.emailNorm);
~~~

Đây **không phải** giải pháp mặc định cho mọi trạng thái FAILED. Nếu nguyên nhân là hết đĩa, recreate có thể thất bại tương tự và tạm thời khiến truy vấn mất phương án index. Trước/sau thay đổi phải ghi lại schema, đo trạng thái, query plan và tác động.

## 7. Phân biệt “index được chọn” với “index thực sự giúp nhanh”

Planner Neo4j là **cost-based planner**: nó ước lượng số hàng, chi phí tìm điểm bắt đầu, lọc, mở rộng relationship, sort và aggregation để chọn kế hoạch có tổng chi phí dự kiến thấp. Một index có sẵn không phải mệnh lệnh buộc planner luôn sử dụng.

Ví dụ:

~~~cypher
MATCH (u:IndexDemoUser {tenantId: $tenantId})
RETURN u.userId AS userId;
~~~

Nếu gần như mọi user của database nằm trong một tenant, dùng index có thể không rẻ hơn một lần label scan rồi lọc. Với tập fixture chỉ vài node, scan càng có thể hợp lý. Ngược lại, nếu chỉ một user có `emailNorm` cụ thể trong số hàng triệu user, index seek thường đáng cân nhắc hơn.

### 7.1. Các toán tử thường gặp

| Toán tử/khuynh hướng plan | Ý nghĩa | Điều cần đọc tiếp |
| --- | --- | --- |
| `NodeIndexSeek` | Tìm node theo điều kiện property dùng index. | Số hàng trả, DB Hits, có đúng index mong muốn không. |
| `NodeUniqueIndexSeek` | Tra cứu theo index duy nhất trong tình huống phù hợp. | Có khác plan/cost với query thật sau lọc không. |
| `NodeIndexScan` | Quét phạm vi/các entry index theo chiến lược planner. | Có đang đọc phần lớn index không? |
| `NodeByLabelScan` | Quét node theo label rồi có thể lọc. | Số hàng label, độ chọn lọc, tính hợp lệ của predicate/index. |
| `AllNodesScan` | Quét tập node rộng hơn. | Có thiếu label hoặc điểm bắt đầu tốt không? |
| `RelationshipIndexSeek` | Tra cứu relationship có property qua index thích hợp. | Có phải thực sự muốn bắt đầu từ quan hệ hay không. |
| `Expand(All)` / `Expand(Into)` | Duyệt relationship từ node đã biết. | Fan-out, bậc của node và số hàng trung gian. |
| `Filter` | Kiểm tra điều kiện trên dòng dữ liệu. | Điều kiện có được đẩy xuống gần điểm bắt đầu không. |
| `Sort` / `Top` | Sắp xếp/chọn kết quả. | Có phải đọc và sort nhiều hàng trước `LIMIT` không. |
| `Eager` / `Aggregation` | Materialize/tổng hợp trong plan. | Bộ nhớ và số hàng trung gian, không chỉ index đầu vào. |

Tên toán tử và runtime có thể khác theo Neo4j version; không nên viết script phụ thuộc chính xác một chuỗi tên mà không kiểm thử. Một label scan không đương nhiên sai; một index seek cũng không bảo đảm toàn truy vấn nhanh.

## 8. Đọc EXPLAIN và PROFILE có phương pháp

### 8.1. EXPLAIN: xem kế hoạch mà không chạy truy vấn

~~~cypher
EXPLAIN
MATCH (u:IndexDemoUser)
WHERE u.tenantId = $tenantId
  AND u.emailNorm = $emailNorm
RETURN u.userId AS userId,
       u.displayName AS displayName;
~~~

Truyền các giá trị test phù hợp, ví dụ `tenantId = 'T1'` và `emailNorm = 'an@example.test'`. `EXPLAIN` có thể giúp thấy planner định bắt đầu ở index nào và ước lượng số hàng, nhưng không cung cấp **thời gian chạy hoặc Rows/DB Hits thực tế**.

### 8.2. PROFILE: chạy thật, đo thật

~~~cypher
PROFILE
MATCH (u:IndexDemoUser)
WHERE u.tenantId = $tenantId
  AND u.emailNorm = $emailNorm
RETURN u.userId AS userId,
       u.displayName AS displayName;
~~~

Với `PROFILE`, đọc ít nhất:

1. **Toán tử khởi đầu:** index seek, index scan hay label scan?
2. **Estimated Rows vs Rows:** số hàng ước lượng khác số thực tế nhiều không?
3. **DB Hits:** chi phí truy cập dữ liệu nằm ở toán tử nào?
4. **Số hàng sau mỗi `Expand`:** có supernode hoặc fan-out không?
5. **Sort, aggregation, eager:** thời gian/bộ nhớ tập trung ở đâu?
6. **Thời gian tổng, p95/p99 theo ứng dụng:** một run đơn lẻ có đại diện không?

`PROFILE` **thực thi query**, vì vậy không chạy với `DELETE`, `SET` hay mutation production chỉ để xem chi phí nếu chưa có một môi trường an toàn. Với query đọc, vẫn nên dùng database thử hoặc thời điểm phù hợp nếu thao tác có thể quét rất nhiều dữ liệu.

### 8.3. Baseline phải có cùng điều kiện

So sánh trước và sau khi thay đổi:

| Thuộc tính | Trước | Sau | Cách diễn giải |
| --- | --- | --- | --- |
| Neo4j version/database | ... | ... | Bắt buộc biết có thay runtime/schema không. |
| Index state | ... | ... | Cả hai lần nên ở trạng thái được ghi rõ. |
| Query text và shape tham số | ... | ... | Tránh so hai câu/kiểu dữ liệu khác nhau. |
| Rows/Estimated Rows | ... | ... | Kiểm độ lệch cardinality. |
| DB Hits | ... | ... | Chi phí đọc nội bộ, không bằng latency tuyệt đối. |
| Node/relationship size | ... | ... | Khác quy mô thì khác plan có thể hợp lý. |
| Thời gian p50/p95/p99 | ... | ... | Đo dưới tải tương đương. |
| CPU/page cache/disk latency | ... | ... | Tách yếu tố hạ tầng khỏi truy vấn. |
| Kết quả nghiệp vụ | ... | ... | Bảo đảm tối ưu không làm sai semantics. |

Đừng so một lần `PROFILE` đầu tiên trong cache lạnh với một lần trong cache ấm rồi tuyên bố index mới nhanh hơn nhiều. Query compilation, page cache, network và GC đều có thể tác động.

## 9. Predicate nào thích hợp với loại index nào?

Một index chỉ phục vụ những predicate và cách truy cập mà **loại index** hỗ trợ. Không thể tạo mọi index rồi mong planner tự biến bất kỳ biểu thức nào thành thao tác seek.

| Kiểu index | Ví dụ sử dụng | Lưu ý |
| --- | --- | --- |
| **LOOKUP** | Tra cứu node theo label/relationship theo type cho cơ chế tìm kiếm tương ứng. | Không thay property index khi lọc thuộc tính chọn lọc. |
| **RANGE** | Equality/range, thứ tự với property được index khi plan phù hợp. | Composite key, dữ liệu và loại biểu thức quyết định dùng seek/scan. |
| **TEXT** | Tìm chuỗi bằng `CONTAINS`/`ENDS WITH` trên property được index ở các phiên bản hỗ trợ. | Không phải full-text phân tích ngôn ngữ hoặc ranking. |
| **POINT** | Truy vấn không gian với point/spatial predicates phù hợp. | Không thay range index cho mọi property. |
| **FULLTEXT** | Tìm kiếm theo văn bản đã phân tích và relevance. | Thường truy cập bằng procedure/full-text API, không tự dùng cho `WHERE` thường. |
| **VECTOR** | Nearest-neighbor dựa trên embedding đã lưu. | Không tự tạo vector hoặc dùng cho equality/range thông thường. |

### 9.1. Equality trên property đã index

~~~cypher
MATCH (u:IndexDemoUser)
WHERE u.tenantId = $tenantId
  AND u.emailNorm = $emailNorm
RETURN u.userId AS userId;
~~~

Câu này khớp với index `idx_demo_user_tenant_email` về label và thứ tự thuộc tính. Với dữ liệu đủ lớn và tính chọn lọc cao, planner có thể chọn index seek. Trên fixture rất nhỏ, lựa chọn khác vẫn có thể đúng.

### 9.2. Range với giá trị thời gian

~~~cypher
MATCH (o:IndexDemoOrder)
WHERE o.tenantId = $tenantId
  AND o.createdAt >= $fromTime
  AND o.createdAt < $toTime
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt
ORDER BY o.createdAt ASC
LIMIT 50;
~~~

Tham số `$fromTime` và `$toTime` nên truyền dưới dạng temporal được driver Neo4j hỗ trợ, hoặc chuyển đổi có kiểm soát trong query **mà không bọc function quanh property cần index**. Nếu ứng dụng truyền chuỗi rồi so với property DateTime, phải xác minh cách chuyển kiểu và kết quả; không coi hai kiểu là tương đương.

### 9.3. Function trên property có thể cản trở index seek

Ví dụ dễ gây scan:

~~~cypher
MATCH (u:IndexDemoUser)
WHERE toLower(u.emailNorm) = $emailNorm
RETURN u.userId;
~~~

Nếu dữ liệu đã chuẩn hóa vào property `emailNorm`, ưu tiên:

~~~cypher
MATCH (u:IndexDemoUser)
WHERE u.tenantId = $tenantId
  AND u.emailNorm = $emailNorm
RETURN u.userId;
~~~

Lý do: index thường chứa giá trị property, không mặc nhiên chứa kết quả của mọi hàm như `toLower(property)`. Khi dùng hàm trên property trong predicate, planner có thể không biến nó thành seek trực tiếp. Việc chuẩn hóa khi ghi hoặc duy trì một trường tìm kiếm riêng thường đơn giản hơn với workload tra cứu lặp lại.

**Không gọi mọi function là “không thể index”:** công cụ và các kiểu index trong từng phiên bản có tối ưu riêng. Cách đúng là **kiểm plan**, so với biến thể sử dụng predicate trên property gốc và bảo đảm semantics khi chuyển đổi.

### 9.4. NULL, existence và COALESCE

~~~cypher
MATCH (u:IndexDemoUser)
WHERE coalesce(u.emailNorm, '') = $emailNorm
RETURN u.userId;
~~~

Hàm `coalesce` thay đổi biểu thức được đánh giá; planner không nhất thiết dùng seek trên index `emailNorm` như với equality trực tiếp. Nếu nghiệp vụ yêu cầu email bắt buộc, hãy validate và thiết kế existence/key constraint được hỗ trợ thay vì chèn giá trị trống vào query. Nếu email có thể thiếu, xác định semantics của null rõ ràng, rồi đo plan phù hợp.

Index và constraint có thể chỉ chứa các entry đáp ứng điều kiện giá trị nhất định; **đừng suy ra `IS NULL` luôn có thể tìm nhanh bằng property index**. Hãy kiểm tra index type và kế hoạch thực tế.

### 9.5. OR và phép phủ định

~~~cypher
MATCH (u:IndexDemoUser)
WHERE u.emailNorm = $emailNorm
   OR u.active = true
RETURN u.userId;
~~~

Điều kiện `OR` trên hai property khác nhau có thể làm planner chọn một kế hoạch rộng, dùng nhiều nhánh hoặc không dùng index mong đợi. Không tự thay mọi `OR` bằng `UNION`: việc này có thể làm thay đổi loại trùng, kế hoạch, thứ tự và tổng chi phí. Nếu thử tái cấu trúc, kiểm kết quả bằng `DISTINCT` đúng nhu cầu và benchmark trên dữ liệu thật.

## 10. Composite index: thứ tự property có ý nghĩa

Index:

~~~cypher
CREATE RANGE INDEX idx_demo_user_tenant_email IF NOT EXISTS
FOR (u:IndexDemoUser)
ON (u.tenantId, u.emailNorm);
~~~

có thứ tự **`tenantId` rồi `emailNorm`**. Đây là lựa chọn hợp lý khi workload chính tra cứu email **trong một tenant**.

| Query | Tương tác với composite index |
| --- | --- |
| `tenantId = $t AND emailNorm = $e` | Thường là mẫu phù hợp để seek theo cả hai property. |
| `tenantId = $t` | Có thể dùng tiền tố index, tùy cost planner và thống kê. |
| `emailNorm = $e`, không có tenantId | Không phải mẫu seek tiền tố lý tưởng cho index đã thiết kế; planner có thể scan/filter hoặc chọn index khác. |
| `tenantId = $t AND emailNorm STARTS WITH $p` | Có thể phù hợp range/prefix search theo khả năng version và plan. |
| `tenantId = $t AND toLower(emailNorm) = $e` | Function trên property khiến predicate thứ hai kém phù hợp với seek trực tiếp. |

Không phải mọi query chứa cả hai property đều dùng index. Ví dụ, planner vẫn có thể chọn một index khác hoặc label scan nếu ước lượng kết quả quá lớn.

### 10.1. Câu query chỉ có property đứng sau

~~~cypher
EXPLAIN
MATCH (u:IndexDemoUser)
WHERE u.emailNorm = $emailNorm
RETURN u.userId;
~~~

Nếu tra cứu email **toàn cục** là use case quan trọng và được phép (không phá vỡ tenant isolation), có thể cần một index riêng theo `emailNorm` hoặc thay query để xác định tenant trước. Tuy nhiên, tạo thêm index tăng disk và chi phí cập nhật mỗi lần ghi. **Không tạo index mới nếu dữ liệu toàn cục phải được kiểm soát theo tenant mà query đang thiếu giới hạn quyền.**

### 10.2. Composite index không tự giải quyết mọi ORDER BY

~~~cypher
MATCH (o:IndexDemoOrder)
WHERE o.tenantId = $tenantId
  AND o.createdAt >= $fromTime
RETURN o.orderId AS id,
       o.createdAt AS createdAt
ORDER BY o.createdAt DESC, o.orderId ASC
LIMIT 20;
~~~

Index `(tenantId, createdAt)` có thể giúp tìm range và một số thứ tự trên `createdAt`. Nhưng `orderId` là khóa phá hòa, **không nằm trong index này**; planner có thể còn cần xử lý sort/tie hoặc kế hoạch khác. Xác định nhu cầu phân trang và index theo order thực, không chỉ dựa vào “đã có index createdAt”.

## 11. Selectivity thấp: label scan đôi khi là lựa chọn đúng

Giả sử có 10 triệu user nhưng 9,9 triệu người có `active = true`. Thêm:

~~~cypher
CREATE RANGE INDEX idx_demo_user_active IF NOT EXISTS
FOR (u:IndexDemoUser)
ON (u.active);
~~~

không bảo đảm query sau sẽ nhanh:

~~~cypher
MATCH (u:IndexDemoUser)
WHERE u.active = true
RETURN u.userId
LIMIT 100;
~~~

Vì phần lớn bản ghi thỏa điều kiện, truy cập qua index có thể không giảm đáng kể số dòng phải xử lý. Với query chỉ cần 100 hàng và không có thứ tự, planner còn có thể dùng phương án khác để sớm lấy đủ kết quả.

Tính **độ chọn lọc** minh họa:

\[
\text{selectivity}(P)
=\frac{\text{số node đáp ứng predicate }P}
{\text{số node trong phạm vi xét}}.
\]

Nếu predicate trả gần như toàn bộ node, index theo một property ít phân biệt có thể kém hữu ích. Tuy nhiên, mức “tốt” còn phụ thuộc plan, nguồn lực và kết quả thực tế; không có ngưỡng phần trăm đúng cho mọi workload.

### 11.1. Số lượng và phân bố không đồng đều

Trong hệ thống đa tenant:

| Tenant | Số user | Tỷ lệ active |
| --- | ---: | ---: |
| T1 | 100 | 90% |
| T2 | 10.000 | 90% |
| T3 | 2.000.000 | 99% |

Cùng query `WHERE tenantId = $t AND active = true` có thể tạo số hàng khác nhau rất lớn theo tenant. Nếu dự đoán cardinality không phản ánh đúng tenant lớn, plan có thể tốt cho T1 nhưng tệ cho T3. Khi benchmark, sử dụng mẫu nhỏ, trung bình, tenant lớn và trường hợp lệch phân bố.

**Cảnh báo bảo mật:** một query “bỏ tenantId để tìm cho nhanh” có thể vừa tệ về hiệu năng vừa lộ dữ liệu. Luôn giữ điều kiện tenant/phân quyền theo ngữ cảnh xác thực.

## 12. Không nhầm index lookup với full-text và vector

### 12.1. Text index và tìm chuỗi

Với bài tập, có thể tạo:

~~~cypher
CREATE TEXT INDEX idx_demo_user_name_text IF NOT EXISTS
FOR (u:IndexDemoUser)
ON (u.displayName);
~~~

Truy vấn minh họa:

~~~cypher
MATCH (u:IndexDemoUser)
WHERE u.displayName CONTAINS $partOfName
  AND u.tenantId = $tenantId
RETURN u.userId AS id,
       u.displayName AS name
LIMIT 20;
~~~

`TEXT` index có thể hỗ trợ một số phép tìm chuỗi như `CONTAINS`/`ENDS WITH` theo phiên bản. Nhưng planner vẫn có thể chọn đường truy cập khác nếu cần lọc tenant hoặc dữ liệu quá nhỏ. **Substring search** không tự tương đương với tìm toàn văn theo token, phân tích ngôn ngữ và xếp hạng mức liên quan.

### 12.2. Full-text index thường phải gọi API riêng

~~~cypher
CREATE FULLTEXT INDEX idx_demo_user_fulltext IF NOT EXISTS
FOR (u:IndexDemoUser)
ON EACH [u.displayName, u.bio];
~~~

Trên các bản hỗ trợ procedure phù hợp:

~~~cypher
CALL db.index.fulltext.queryNodes(
  'idx_demo_user_fulltext',
  $queryText
)
YIELD node, score
WHERE node.tenantId = $tenantId
RETURN node.userId AS userId,
       node.displayName AS name,
       score
ORDER BY score DESC
LIMIT 20;
~~~

Đừng mong `MATCH ... WHERE u.bio CONTAINS $term` **tự động** sử dụng full-text index như procedure này. Full-text index có analyzer, cách tokenize và score riêng; `CONTAINS` là phép so khớp chuỗi với semantics khác.

**Giới hạn quyền:** lọc `tenantId` ở kết quả sau procedure chưa chắc giảm lượng kết quả được tìm/cần xử lý bên trong index; với yêu cầu cách ly chặt hoặc nhiều tenant lớn, cân nhắc kiến trúc tìm kiếm theo phạm vi được phép, kiểm soát index/query endpoint và đánh giá nguy cơ suy luận dữ liệu.

### 12.3. Vector index không phải index equality

Với node có property `embedding` chứa vector số đúng chiều, trên những bản Neo4j hỗ trợ vector index:

~~~cypher
CREATE VECTOR INDEX idx_demo_user_embedding IF NOT EXISTS
FOR (u:IndexDemoUser)
ON (u.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 64,
    `vector.similarity_function`: 'cosine'
  }
};
~~~

Ví dụ gọi vector index bằng procedure ở những phiên bản hỗ trợ:

~~~cypher
CALL db.index.vector.queryNodes(
  'idx_demo_user_embedding',
  20,
  $queryEmbedding
)
YIELD node, score
RETURN node.userId AS id, score
ORDER BY score DESC;
~~~

Lệnh trên giả định `$queryEmbedding` là vector phù hợp chiều, kiểu và cách chuẩn hóa với embedding đã lưu. Chỉ tạo index không tự sinh vector. Neo4j có thể cung cấp cú pháp tìm kiếm vector mới theo phiên bản; xác minh giao diện thực tế trước khi chuyển code. Không đo mức độ “planner không chọn range index” trong một truy vấn nearest-neighbor như thể đây là cùng bài toán.

### 12.4. Point index và dữ liệu không gian

Khi lọc theo khoảng cách/vùng địa lý, có thể cần `POINT` index và predicate hỗ trợ thay vì range index trên chuỗi kinh độ/vĩ độ. Dữ liệu `point` phải dùng kiểu giá trị hợp lệ và hệ tọa độ thống nhất. Index state `ONLINE` không sửa được kết quả sai vì so lẫn tọa độ địa lý và tọa độ Descartes.

## 13. Relationship property index: dùng đúng điểm bắt đầu

Neo4j có thể index **relationship properties** theo phiên bản. Ví dụ nếu cạnh mua hàng có property `source` hoặc `createdAt` và query tìm trên toàn bộ relationship:

~~~cypher
CREATE RANGE INDEX idx_demo_rel_channel IF NOT EXISTS
FOR ()-[r:INDEX_DEMO_PLACED]-()
ON (r.channel);
~~~

Fixture chưa đặt `r.channel` nên index này chưa có nhiều ý nghĩa cho việc đo plan; cần dữ liệu đúng mới benchmark được.

Một truy vấn có thể:

~~~cypher
MATCH (u:IndexDemoUser)
      -[r:INDEX_DEMO_PLACED]->
      (o:IndexDemoOrder)
WHERE r.channel = $channel
RETURN u.userId, o.orderId
LIMIT 50;
~~~

Nếu tìm tất cả cạnh theo một `channel` rất hiếm, relationship index có thể hữu ích. Nhưng nếu ứng dụng đã tìm chính xác một user nhờ khóa và user chỉ có vài order, cách **mở rộng cạnh từ user** có thể rẻ hơn tìm tất cả relationship theo channel rồi nối tới user. Cost planner có lý do để không chọn index relationship trong trường hợp đó.

**Quan trọng:** relationship index không tự biến relationship thành node hoặc thay đổi hướng vật lý của cạnh. Cypher vẫn phải dùng đúng type và mũi tên; predicate theo property của cạnh khác với predicate theo property node.

## 14. Vì sao index vẫn ONLINE nhưng không được chọn?

Đây là phần chính của nhóm lỗi thứ hai. Hãy kiểm theo thứ tự ưu tiên:

### 14.1. Index thuộc database hoặc label khác

Một index có cùng tên mong đợi trên database staging không bảo đảm nó tồn tại trên database production. Query cũng có thể dùng sai label hoặc property:

~~~cypher
// Index có trên :IndexDemoUser(emailNorm)
// nhưng query tìm vào property khác tên.
MATCH (u:IndexDemoUser)
WHERE u.email = $email
RETURN u.userId;
~~~

`email` không phải `emailNorm`. Truy vấn vẫn hợp cú pháp nhưng không thể dùng index của `emailNorm` cho predicate đó. Kiểm:

- Database được session/driver kết nối.
- Label/type trong index và trong query.
- Tên property, chữ hoa/thường và quy tắc escape.
- Index là node hay relationship index.
- Index thực sự `ONLINE` trên database đang chạy query.

### 14.2. Predicate không phù hợp index

Các pattern dễ cần kiểm tra:

- `toLower(n.property) = ...`, `trim(n.property) = ...` hoặc `coalesce(...)`.
- So sánh số với chuỗi do Java/JSON truyền sai kiểu.
- `CONTAINS`/`ENDS WITH` nhưng chỉ tạo loại index không phù hợp.
- Tìm kiếm full-text nhưng dùng Cypher `WHERE` thường.
- Phép tính trên property như `n.price * 1.1 > $x`.
- Query cần kiểm một phần tử trong list/collection theo cách index hiện tại không hỗ trợ.
- `OR`/`NOT` kết hợp nhiều property làm tập kết quả quá rộng.

Không áp dụng một quy tắc tuyệt đối “có hàm là scan” cho mọi phiên bản. Mỗi giả thuyết phải được so bằng `EXPLAIN`/`PROFILE`.

### 14.3. Tập kết quả quá rộng

Index seek không có lợi khi gần như toàn bộ node thỏa điều kiện hoặc cần đọc lượng lớn property ở store. Planner có thể chọn scan đúng đắn.

### 14.4. Cardinality, thống kê hoặc cached plan

Neo4j sử dụng ước lượng cardinality và các thống kê phục vụ planner. Sau một import rất lớn, một migration xóa/hợp nhất dữ liệu hoặc tạo index mới, thống kê/plan cache có thể chưa phản ánh tải thực tế đúng như kỳ vọng.

Một số phiên bản hỗ trợ **query replanning** khi thống kê thay đổi đủ lớn hoặc theo chính sách cache; cũng có cơ chế administrator clear query caches. **Không mặc định clear cache như bước đầu tiên**, vì làm tăng chi phí compile lại trên nhiều request và có thể gây biến động latency; cần kiểm tra version, bằng chứng và thời điểm an toàn.

### 14.5. Index có thể được chọn nhưng chi phí nằm sau đó

~~~cypher
MATCH (u:IndexDemoUser {
  tenantId:$tenantId,
  emailNorm:$emailNorm
})-[:INDEX_DEMO_PLACED]->(o:IndexDemoOrder)
RETURN o.status AS status,
       count(o) AS total
ORDER BY total DESC;
~~~

Một index có thể tìm user rất nhanh nhưng nếu user là **supernode với hàng triệu order**, việc mở rộng và tổng hợp mới là nút thắt. Thêm index email lần thứ hai không giảm số cạnh phải duyệt.

Đừng dừng phân tích ở toán tử đầu có `NodeIndexSeek`. Đọc Rows/DB Hits ở `Expand`, `Aggregation` và `Sort`, đồng thời cân nhắc mô hình dữ liệu, query giới hạn thời gian hoặc summary/materialized aggregation nếu nghiệp vụ cho phép.

## 15. Trình tự chẩn đoán query plan không mong đợi

### Bước 1 — Chốt query và tham số

Lưu query text **không chứa PII**, trường hợp dữ liệu, hình dạng/các kiểu parameter và số lượng kết quả dự kiến. Với nhiều tenant, ghi cả phân bố dữ liệu điển hình mà không ghi ID nhạy cảm lên dashboard.

### Bước 2 — Đọc catalog chính xác

~~~cypher
SHOW INDEXES
YIELD name, type, entityType,
      labelsOrTypes, properties, state
WHERE state = 'ONLINE'
RETURN name, type, entityType,
       labelsOrTypes, properties, state
ORDER BY name;
~~~

Xác nhận index có **đúng loại** và nằm trong database hiện hành.

### Bước 3 — EXPLAIN trước, PROFILE sau

So sánh các phiên bản query có cùng semantics:

~~~cypher
// Phương án A: function trên property.
EXPLAIN
MATCH (u:IndexDemoUser)
WHERE u.tenantId = $tenantId
  AND toLower(u.emailNorm) = $emailNorm
RETURN u.userId;
~~~

~~~cypher
// Phương án B: property đã được chuẩn hóa khi ghi.
EXPLAIN
MATCH (u:IndexDemoUser)
WHERE u.tenantId = $tenantId
  AND u.emailNorm = $emailNorm
RETURN u.userId;
~~~

Chỉ so hai phương án là tương đương nếu **toàn bộ dữ liệu emailNorm đã đúng quy tắc chuẩn hóa** và tham số được chuẩn hóa giống nhau. Nếu tồn tại giá trị không đồng nhất hoặc null, phương án B có thể trả khác A; cần migration và kiểm thử trước khi thay query.

### Bước 4 — Kiểm tra độ chọn lọc và fan-out

Một số câu kiểm tra trên fixture, **không được chạy count rộng liên tục trên production**:

~~~cypher
MATCH (u:IndexDemoUser {tenantId:$tenantId})
RETURN count(u) AS tenantUsers;
~~~

~~~cypher
MATCH (u:IndexDemoUser {
  tenantId:$tenantId,
  emailNorm:$emailNorm
})
RETURN count(u) AS matchingUsers;
~~~

~~~cypher
MATCH (u:IndexDemoUser {
  tenantId:$tenantId,
  userId:$userId
})-[:INDEX_DEMO_PLACED]->(o:IndexDemoOrder)
RETURN count(o) AS outgoingOrders;
~~~

Những số liệu này giúp biết liệu index tìm được ít node nhưng traversal mới tốn chi phí, hoặc query đang lọc gần toàn bộ tenant.

### Bước 5 — Thử can thiệp nhỏ nhất

Ưu tiên sửa:

1. Lỗi label/property/tenant/kiểu dữ liệu.
2. Predicate làm mất khả năng seek (nếu có biến thể tương đương về nghiệp vụ).
3. Trật tự composite index và mẫu truy vấn, sau khi đo workload.
4. Query hạn chế số node trước khi mở rộng relationship.
5. Stats/replan, index hint, tạo index mới **chỉ khi bằng chứng ủng hộ**.

### Bước 6 — Xác minh lại

So sánh plan, Rows, DB Hits, p95/p99 và kết quả nghiệp vụ. Nếu có regression ở tenant lớn, không triển khai thay đổi chỉ vì tenant test nhỏ chạy nhanh hơn.

## 16. Index hint: công cụ kiểm chứng, không phải thần dược

Neo4j Cypher hỗ trợ index hint trong những trường hợp phù hợp. Trên index range demo:

~~~cypher
MATCH (u:IndexDemoUser)
USING INDEX u:IndexDemoUser(tenantId, emailNorm)
WHERE u.tenantId = $tenantId
  AND u.emailNorm = $emailNorm
RETURN u.userId AS userId;
~~~

Đây là **hint cho planner**, không tạo một index mới, không chữa index `FAILED`, không biến predicate sai thành được index và không bảo đảm query sẽ nhanh hơn. Khi hint không thể thỏa mãn (index/type/predicate không phù hợp), câu Cypher có thể bị từ chối hoặc không ra plan mong đợi theo khả năng phiên bản.

Chỉ cân nhắc dùng lâu dài nếu:

- Index cụ thể đã `ONLINE` trên mọi môi trường mà code chạy.
- Plan tự động tệ có thể tái hiện, đã kiểm tra thống kê/dữ liệu và loại trừ khác biệt parameter.
- Plan với hint có latency và tải tốt hơn trên nhiều phân khúc dữ liệu.
- Có test khi schema thay đổi/triển khai index chưa ready.
- Có owner cập nhật hint khi sửa schema hoặc nâng cấp Neo4j.

Hint có thể **trói query vào index** trong khi phân bố dữ liệu thay đổi. Một lựa chọn cost planner hôm nay có thể tốt hơn hint năm ngoái; đừng dùng hint để che vấn đề modeling hoặc CPU/I/O.

## 17. Khi thêm index lại làm hệ thống chậm hơn

Mỗi index có chi phí:

| Chi phí | Biểu hiện |
| --- | --- |
| Dung lượng lưu trữ | Thêm index store, peak khi population/rebuild, tăng backup/restore workload. |
| Ghi dữ liệu | Neo4j cập nhật index khi property/relationship được index thay đổi. |
| Index population | Tốn CPU, I/O và thời gian; có thể cạnh tranh với workload trực tuyến. |
| Schema vận hành | Cần migration, monitor state và kế hoạch khôi phục khi lỗi. |
| Planning | Nhiều phương án access path hơn; cần đo và quản lý query plan khi thay đổi lớn. |

Ví dụ một dịch vụ tạo 12 index trên mọi property “để chắc chắn” có thể khiến giao dịch tạo node phải cập nhật nhiều cấu trúc index, tăng I/O và transaction latency, dù chỉ có một vài query thật cần chúng.

### 17.1. Checklist trước khi CREATE

- Có **query cụ thể** nào đang chậm và một predicate phù hợp không?
- Index có trùng lặp/bao hàm bởi index hoặc constraint hiện có không?
- Số bản ghi, độ chọn lọc và phân bố theo tenant có đại diện không?
- Có cần index node, relationship, text, full-text, point hay vector?
- Có đủ headroom cho population và disk backup?
- Chi phí ghi tăng bao nhiêu trong benchmark?
- Nếu index FAILED, ai xử lý và mất bao lâu để rebuild?
- Cần thêm index vào migration/alert và chờ `ONLINE` trước khi mở traffic không?

## 18. Triển khai index an toàn cùng ứng dụng Java

### 18.1. Luồng rollout có dependency

Một tính năng mới sử dụng tra cứu `emailNorm` có thể triển khai như sau:

~~~text
T0: Chuẩn hóa dữ liệu hiện có (backfill có kiểm soát)
                |
T1: Tạo index mới, không xóa index cũ
                |
T2: Theo dõi SHOW INDEXES, chờ ONLINE có timeout
                |
T3: EXPLAIN/PROFILE query với dữ liệu đại diện
                |
T4: Canary ứng dụng dùng query mới
                |
T5: Quan sát p95/p99, lỗi, DB Hits, resource
                |
T6: Phê duyệt triển khai toàn bộ
                |
T7: Chỉ drop index cũ khi đã xác minh không còn phụ thuộc
~~~

Nếu T2 thất bại, **không** mở tính năng cần index như thể đã hoàn tất. Nếu T4 có regression, rollback query/application nhưng không vội xóa index mới giữa lúc đang xử lý sự cố trừ khi có lý do an toàn và đã đánh giá impact.

### 18.2. Java Driver: đọc trạng thái index

~~~java
import java.util.List;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Record;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class IndexStateMonitor {
    private final Driver driver;

    public IndexStateMonitor(Driver driver) {
        this.driver = driver;
    }

    public List<Record> findProblematicIndexes() {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            return session.run("""
                SHOW INDEXES
                YIELD name, type, state, populationPercent
                WHERE state <> 'ONLINE'
                RETURN name, type, state, populationPercent
                ORDER BY name
                """).list();
        }
    }
}
~~~

Giả định Java Driver đã được cấu hình TLS/URI/credential đúng và tài khoản monitor có quyền đọc trạng thái schema trên database đích. Ứng dụng production nên ánh xạ về DTO, kiểm timeout, phân biệt `POPULATING` (có thể bình thường trong rollout) với `FAILED` (cần cảnh báo) và không log PII hoặc secret.

### 18.3. Java Driver: thu thập kế hoạch EXPLAIN

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.summary.ResultSummary;

public final class IndexPlanProbe {
    private final Driver driver;

    public IndexPlanProbe(Driver driver) {
        this.driver = driver;
    }

    public String rootOperator() {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            ResultSummary summary = session.run("""
                EXPLAIN
                MATCH (u:IndexDemoUser)
                WHERE u.tenantId = $tenantId
                  AND u.emailNorm = $emailNorm
                RETURN u.userId
                """, Map.of(
                "tenantId", "T1",
                "emailNorm", "an@example.test"
            )).consume();

            return summary.plan().operatorType();
        }
    }
}
~~~

Ở `EXPLAIN`, phần plan có thể được đọc từ `ResultSummary.plan()` theo API driver tương ứng. **Root operator thường là `ProduceResults`**, không phải index seek; kiểm tra cả cây plan khi muốn chứng minh một index được dùng. Đừng viết kiểm thử chỉ so `rootOperator() == "NodeIndexSeek"`.

Nếu cần đo runtime, chạy `PROFILE` với query đọc an toàn và dùng phần profile trong result summary khi driver/version hỗ trợ, rồi đối chiếu số hàng và DB Hits. API cho plan/profile khác nhau theo phiên bản; nên sử dụng thư viện thích hợp với server đã triển khai.

### 18.4. Spring Data Neo4j và query mapping

Spring Data Neo4j repository/`Neo4jClient` không tự quyết định index bằng tên method. SDN tạo/gửi Cypher; **Neo4j planner quyết định access path**. Ví dụ một service dùng `Neo4jClient`:

~~~java
import java.util.Optional;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;

@Service
public final class UserLookupService {
    private final Neo4jClient client;

    public UserLookupService(Neo4jClient client) {
        this.client = client;
    }

    public Optional<String> findIdByTenantAndEmail(
            String tenantId, String emailNorm) {
        // tenantId đã được service authorization xác minh.
        return client.query("""
                MATCH (u:IndexDemoUser)
                WHERE u.tenantId = $tenantId
                  AND u.emailNorm = $emailNorm
                RETURN u.userId AS userId
                """)
            .bind(tenantId).to("tenantId")
            .bind(emailNorm).to("emailNorm")
            .fetchAs(String.class)
            .mappedBy((typeSystem, record) ->
                record.get("userId").asString())
            .one();
    }
}
~~~

Đây là ví dụ API đọc trong module, **không phải toàn bộ hệ thống xác thực**. Không tin `tenantId` từ client nếu chưa kiểm quyền. `emailNorm` phải được chuẩn hóa thống nhất khi ghi/đọc; uniqueness của `(tenantId, userId)` không tự chứng minh `(tenantId, emailNorm)` duy nhất. Nếu nghiệp vụ kỳ vọng một kết quả, hãy thiết kế uniqueness/validation phù hợp.

Khi chậm, log tên operation/trace ID và duration theo chính sách, không log toàn bộ thông số có PII. Tách thời gian pool/driver/network khỏi thời gian Neo4j thực thi để không nhầm connection timeout với index.

## 19. Quan sát index trong vận hành

Một dashboard có thể theo dõi:

| Chỉ số | Tác dụng |
| --- | --- |
| Số index `FAILED` | Cảnh báo lỗi schema. |
| Index `POPULATING` và thời gian/tiến độ | Phát hiện population kéo dài bất thường. |
| Dung lượng index, disk free/headroom | Đánh giá khả năng build/rebuild. |
| Thời gian/DB Hits của các query quan trọng | Theo dõi planner/query regression. |
| Node/relationship count và độ lớn tenant | Biết thay đổi phân bố cardinality. |
| CPU/I/O, page cache, GC/heap | Tách giới hạn tài nguyên khỏi query plan. |
| Query errors, p50/p95/p99 | Đo ảnh hưởng với người dùng. |
| Mốc deploy/migration/index change | Liên kết sự cố với thay đổi gần đây. |
| Backup age và khả năng restore | Có đường phục hồi nếu thao tác schema thất bại nghiêm trọng. |
| Sự sống của metric collector | Không coi thiếu metric là giá trị 0. |

**Không tự bịa tên metric Prometheus chuẩn** nếu exporter/phiên bản hiện tại không cung cấp. Tạo dashboard theo các trường thực tế, gắn source, instance, database và timestamp; khi thiếu số liệu, đánh dấu **unknown**.

### 19.1. Cảnh báo nên theo ngữ cảnh

- `FAILED > 0`: cảnh báo sớm, ưu tiên index thuộc workload hoặc constraint cốt lõi.
- `POPULATING` lâu hơn baseline theo kích thước/loại: cảnh báo điều tra, tránh báo mỗi lần migration hợp lệ.
- Query latency tăng và plan chuyển từ seek sang scan cùng với DB Hits tăng: điều tra hồi quy.
- Disk free thấp trong quá trình population: cảnh báo capacity cấp cao hơn cảnh báo “index chậm”.
- Transaction failure/OOM hoặc backup lỗi cùng thời điểm: cần xem tổng thể sự cố thay vì chỉ sửa query.

Để giảm báo giả, dùng ngưỡng có **khoảng thời gian tồn tại**, dữ liệu đại diện và lịch migration. Tuy nhiên, maintenance window không nên tắt cảnh báo hết đĩa hoặc database không sẵn sàng.

## 20. Ma trận kiểm thử và tái hiện lỗi

Thực hành trong **database riêng**, không cố tình gây `FAILED` hoặc disk full trên production.

| ID | Tình huống | Kỳ vọng kiểm chứng |
| --- | --- | --- |
| I01 | CREATE range index trên fixture. | Ban đầu có thể POPULATING, sau đó ONLINE. |
| I02 | Dùng `db.awaitIndexes` khi được hỗ trợ. | Chờ có timeout; nếu quá hạn phải báo chưa ready. |
| I03 | Query equality đúng label và composite key. | Kết quả chính xác; plan được ghi lại, có thể scan trên fixture nhỏ. |
| I04 | Query dùng `toLower(property)`. | Plan có thể khác; so biến thể predicate gốc và semantics. |
| I05 | Query chỉ lọc property thứ hai trong composite index. | Đánh giá plan/chi phí, không mặc định index seek. |
| I06 | Query lọc property ít chọn lọc `active`. | Không coi label scan là lỗi nếu tổng chi phí thấp. |
| I07 | Query `CONTAINS` và TEXT index. | So đúng kiểu index và plan được hỗ trợ. |
| I08 | Full-text procedure. | Trả score theo analyzer, không đánh đồng với substring. |
| I09 | Relationship property index. | Phân biệt tìm từ edge và mở rộng từ node đã biết. |
| I10 | Kiểm tra trạng thái index sau restart. | Không kết luận ONLINE khi chưa có readback. |
| I11 | Thêm lượng dữ liệu lớn trong staging. | So plan, cardinality và DB Hits trước/sau. |
| I12 | Tenant lệch phân bố nhiều bậc. | Query đại diện cho tenant lớn không vượt SLO. |
| I13 | Planner index seek nhưng expand rất lớn. | Nhận diện fan-out nằm sau seek. |
| I14 | Index FAILED được giả lập ở lớp test/monitor. | Alert đúng index/database, không tự drop. |
| I15 | Thay query làm thiếu tenant filter. | Test quyền và kết quả thất bại theo chính sách. |
| I16 | Rollout code trước khi index ONLINE. | Deployment gate không cho bật tính năng. |
| I17 | Java Driver `EXPLAIN`. | Kế hoạch trả về, kiểm tra cả cây chứ không chỉ root. |
| I18 | Spring Data Neo4j query với parameter type sai. | Lỗi/khác kết quả được phát hiện trước production. |
| I19 | Rebuild index khi storage thiếu headroom (mô phỏng). | Runbook từ chối thao tác nguy hiểm và chuyển xử lý sang nhóm phụ trách dung lượng. |
| I20 | Collector ngừng gửi metric. | Có cảnh báo thiếu số liệu, không ghi nhận hệ thống “không lỗi”. |

### 20.1. Quy ước báo cáo test

Một báo cáo nên ghi:

~~~text
Test ID:
Neo4j version / edition / database:
Index name / type / properties:
State trước / sau:
Query text (đã lược PII):
Parameter types + data distribution:
Plan operators chính:
Rows / Estimated Rows / DB Hits:
p50 / p95 / p99:
Ảnh hưởng nghiệp vụ:
Kết luận: PASS / FAIL / INCONCLUSIVE
Biện pháp và owner:
~~~

Nếu dữ liệu chưa đủ đại diện, ghi **INCONCLUSIVE**, không tuyên bố index nhanh/chậm tuyệt đối.

## 21. Sửa lỗi sai lệch giữa staging và production

Staging thường có ít node, ít relationship, phần lớn query dùng một tenant và page cache luôn ấm. Production có thể khác hoàn toàn:

| Khía cạnh | Staging | Production |
| --- | --- | --- |
| Dữ liệu | Vài nghìn node, ít supernode. | Hàng triệu node/cạnh, phân bố skew. |
| Tenant | 1–2 tenant mẫu. | Nhiều tenant, vài tenant cực lớn. |
| Index | Mới xây, tất cả ONLINE. | Có index cũ/constraint/plan cache và các migration. |
| Tài nguyên | CPU/RAM/I/O ít tranh chấp. | Import, backup, CDC, query cao điểm cùng chạy. |
| Phiên bản | Có thể mới hơn hoặc plugin khác. | Version được pin và quy trình nâng cấp riêng. |
| Query | Dùng test parameters. | Giá trị/kiểu parameter đa dạng và có data skew. |

Khi chỉ production chậm:

1. Xác nhận index cùng tên/type/schema **trên đúng database**.
2. So fingerprint query và shape các parameter theo cách bảo vệ dữ liệu.
3. Đo plan, Rows/DB Hits trên tenant nhỏ và lớn.
4. Kiểm CPU/page cache/disk latency và contention.
5. Kiểm batch mới, thay đổi dữ liệu, deploy hoặc tạo index gần thời điểm lỗi.
6. Tái hiện trên staging **với dữ liệu tổng hợp đại diện**, không copy PII tùy tiện.
7. Chỉ triển khai hint/reindex/sửa schema sau canary và có đường rollback.

Không suy ra việc Neo4j có lỗi chỉ vì planner chọn khác giữa hai môi trường: nó có thể phản ứng hợp lý với **kích thước, cardinality và tải khác nhau**.

## 22. Runbook sự cố theo mức độ

### 22.1. Cấp 1 — Query chậm, database vẫn phục vụ

**Mục tiêu:** chẩn đoán không tạo thêm gián đoạn.

1. Ghi lại request/operation, thời điểm, p95 và query representative đã che dữ liệu.
2. Kiểm index state, database health và đợt deploy/import gần đây.
3. Chạy `EXPLAIN` trước, `PROFILE` với query đọc an toàn.
4. Xác định scan, index seek hay chi phí ở expansion/aggregation.
5. Thử chỉnh predicate hoặc query ít thay đổi semantics nhất.
6. So benchmark; triển khai canary/rollback query khi cần.

### 22.2. Cấp 2 — Index quan trọng POPULATING kéo dài hoặc FAILED

**Mục tiêu:** bảo vệ workload và đường hồi phục.

1. Kiểm disk/headroom/CPU/I/O; tránh rebuild nếu thiếu không gian.
2. Ghi lại `failureMessage` và log liên quan.
3. Xác định index thuộc constraint hay không, ứng dụng nào phụ thuộc.
4. Nếu `POPULATING`, cân nhắc hoãn traffic mới và theo dõi tiến độ.
5. Nếu `FAILED`, khắc phục đúng root cause; rebuild chỉ sau change review.
6. Xác minh `ONLINE`, plan, query correctness và độ trễ trước khi đóng sự cố.

### 22.3. Cấp 3 — Disk/transaction lỗi hoặc query không thể phục vụ

**Mục tiêu:** ưu tiên độ bền dữ liệu.

1. Escalate SRE/DBA; điều tiết writer/job không thiết yếu theo quy trình đã phê duyệt.
2. Giữ nguyên database store, index và transaction-log files; **không xóa file bằng OS**.
3. Kiểm storage/free bytes, backup và khả năng restore.
4. Khôi phục headroom, dịch vụ, quyền và trạng thái database trước khi tối ưu index.
5. Kiểm consistency, transaction, index readiness và các truy vấn nghiệp vụ.
6. Ghi incident timeline, root cause và regression test.

Một sự cố index có thể là triệu chứng của **storage đầy hoặc I/O lỗi**; việc chỉ tạo lại index khi tầng lưu trữ vẫn hỏng có thể làm tình hình xấu hơn.

## 23. Bài tập thực hành

**Bài 1 — Chẩn đoán trạng thái.** Tạo range index demo và theo dõi `SHOW INDEXES`. Giải thích ý nghĩa `POPULATING`, `ONLINE`, `FAILED`; mô tả điều kiện ứng dụng được phép sử dụng tính năng phụ thuộc index.

**Bài 2 — Composite index.** Tạo index `(tenantId, emailNorm)` và so `EXPLAIN` của ba query: chỉ tenantId; tenantId + emailNorm; chỉ emailNorm. Vì sao không thể tuyên bố một index chắc chắn được chọn trên fixture năm user?

**Bài 3 — Function và normalization.** So `toLower(u.emailNorm) = $e` với `u.emailNorm = $e`. Xây test xác nhận dữ liệu được chuẩn hóa trước khi đổi query; chứng minh không làm thay đổi kết quả khi email có chữ hoa/NULL.

**Bài 4 — Selectivity và fan-out.** Dựng dataset 100.000 user với 99% active=true, và một user có 20.000 order. Phân biệt chi phí tra user bằng index với chi phí mở rộng order; đề xuất plan/metric cần xem.

**Bài 5 — Index type.** Một hệ thống dùng `WHERE bio CONTAINS 'graph'` nhưng chỉ có full-text index cho `bio`. Hãy giải thích vì sao không nên mặc định planner dùng full-text trong query đó, và viết truy vấn dùng full-text procedure có kiểm tra tenant.

**Bài 6 — FAILED và constraint.** Có index `FAILED` trùng với tên index hỗ trợ uniqueness constraint. Viết checklist an toàn để xác định ownership, backup, nguyên nhân, quyền và hành động tiếp theo; vì sao không thể drop nó như index thường?

**Bài 7 — Query plan sau migration.** Một batch import làm số User tăng từ 10.000 lên 10 triệu, query không đổi nhưng planner chuyển từ seek sang scan. Nêu cách xác minh thay đổi cardinality, caching, type, Stats, CPU/I/O và ảnh hưởng query; không giả định planner sai.

**Bài 8 — Java Driver/SDN.** Viết một job dùng Java Driver liệt kê index không ONLINE, log trạng thái theo đúng database; sau đó dùng `Neo4jClient` query user theo tenant/email. Làm sao kiểm soát parameter type và không log giá trị email thật?

**Bài 9 — Cảnh báo.** Thiết kế alert cho index FAILED, POPULATING quá lâu, thay đổi DB Hits sau deploy và disk free thấp; giải thích vì sao không nên tắt cảnh báo disk critical trong maintenance index.

**Bài 10 — Quyết định thay đổi.** Một kỹ sư muốn dùng `USING INDEX` cho toàn bộ query vì “index ONLINE nhưng planner không chọn”. Hãy xây tiêu chí bằng chứng, benchmark theo tenant, rủi ro khi thay schema và chính sách rollback trước khi chấp thuận hint.

## 24. Checklist tổng kết

1. **Đã đúng database:** index, query, session/driver và tham số đều thuộc môi trường đang điều tra?
2. **Đã phân loại trạng thái:** `ONLINE`, `POPULATING` hay `FAILED`, có `failureMessage` và thời điểm đo?
3. **Đã phân loại index type:** range/text/full-text/point/vector/lookup/node/relationship đúng với predicate?
4. **Đã kiểm schema:** label, relationship type, property, composite order và constraint ownership đúng?
5. **Đã kiểm query:** function trên property, `OR`/`NULL`, parameter type, phép phủ định và quyền tenant?
6. **Đã đọc toàn plan:** index seek/label scan, filter, expansion, aggregation và sort, không dừng ở toán tử đầu?
7. **Đã đo dữ liệu:** cardinality, selectivity, supernode, tenant skew, volume và phân bố thực?
8. **Đã kiểm tài nguyên:** CPU, page cache, disk I/O, disk free, import/backup và long transactions?
9. **Đã xét plan cache/stats:** có nguyên nhân xác thực và cách replan có kiểm soát trước khi can thiệp?
10. **Đã cân nhắc hint:** không dùng hint để che index FAILED hoặc predicate không phù hợp?
11. **Đã giữ tính đúng:** tối ưu query không làm thay đổi kết quả, quyền hoặc quan hệ nghiệp vụ?
12. **Đã có rollout gate:** chờ index ONLINE với timeout, test plan/latency trước khi mở tính năng?
13. **Đã có đường phục hồi:** backup, change review, rollback ứng dụng/schema và owner khi migration lỗi?
14. **Đã có monitoring:** cảnh báo FAILED/POPULATING, DB Hits/p95, disk headroom và collector mất dữ liệu?
15. **Đã phân biệt vấn đề:** query chậm vì index chưa sẵn sàng, planner chọn phương án khác hay chi phí sau index?

**Kết luận:** khi Neo4j truy vấn chậm, trước tiên xác minh **index có sẵn sàng hay không**, sau đó xem **planner có chọn nó hay không**, cuối cùng tìm **chi phí thực sự phát sinh ở bước nào**. `SHOW INDEXES` cung cấp trạng thái index; `EXPLAIN`/`PROFILE` cung cấp kế hoạch và số liệu truy vấn. Một label scan có thể là lựa chọn hợp lý, còn index seek vẫn có thể dẫn tới traversal rất đắt. Khắc phục tốt là thay đổi **đúng nguyên nhân, giữ nguyên nghĩa truy vấn và quyền dữ liệu, đo trước/sau, có migration gate và runbook an toàn** — không phải tạo thêm hoặc xóa đi index một cách tự động.

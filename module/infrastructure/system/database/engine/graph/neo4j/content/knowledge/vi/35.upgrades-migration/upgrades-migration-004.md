# Kiểm tra cú pháp, thủ tục và cấu hình đã ngừng khuyến nghị

Một hệ thống Neo4j có thể chạy ổn định trong nhiều năm, nhưng khi nâng cấp database, một phần cú pháp Cypher cũ không còn hợp lệ, một procedure APOC bị đánh dấu **deprecated**, hoặc một khóa trong `neo4j.conf` đã đổi tên. Nếu chỉ thử khởi động server rồi gọi `RETURN 1`, ứng dụng vẫn có thể lỗi ở những nhánh nghiệp vụ ít dùng: import theo lô, tìm kiếm toàn văn, câu truy vấn repository sinh tự động hay các thao tác bảo trì.

Bài thuộc chương **Nâng cấp và di trú** của module `DATABASE_ENGINE_GRAPH_NEO4J`, nơi ứng dụng sử dụng property graph, Cypher, index/constraint, tối ưu truy vấn, nhập dữ liệu, Java Driver và Spring Data Neo4j (SDN). Mục tiêu là xây dựng một **quy trình rà soát những tính năng không còn được khuyến nghị** trước khi đổi phiên bản Neo4j hoặc các thư viện liên quan, thay vì chờ phát hiện lỗi sau khi đưa môi trường mới vào production.

> **Phạm vi phiên bản:** Những ví dụ di trú trong bài trải từ **Neo4j 4.4 → Neo4j 5** và từ **Cypher 5 → Cypher 25** trên họ bản Neo4j 2025/2026. Cypher 25 xuất hiện từ **Neo4j 2025.06**; trên các database thuộc thế hệ **Neo4j 2026.02+**, Cypher 25 là ngôn ngữ mặc định theo chính sách phiên bản. Cú pháp, thời điểm deprecated/removed và đặc tính APOC thay đổi liên tục. **Không coi mọi ví dụ là cú pháp chạy được trên mọi bản**; xác định phiên bản nguồn, phiên bản đích, edition và version Cypher trước khi áp dụng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **deprecated**, **removed**, **changed behavior** và **not supported**.
2. Lập danh sách Cypher, schema DDL, procedure/function và cấu hình có nguy cơ lỗi khi nâng cấp.
3. Dùng `SHOW PROCEDURES`, `SHOW FUNCTIONS`, `SHOW SETTINGS` và cảnh báo từ query execution để tìm chức năng đã deprecated khi server hỗ trợ.
4. Nhận diện những thay đổi điển hình như `exists(n.prop)`, `USING PERIODIC COMMIT`, `ON ... ASSERT`, `id(n)` và cú pháp `CALL` subquery.
5. Phân biệt APOC Core/Extended và lựa chọn Cypher thuần khi có phương án thay thế tương đương.
6. Chuyển những khóa cấu hình cũ sang nhóm mới, kiểm tra bằng `neo4j-admin server validate-config` và tránh tắt strict validation để che lỗi.
7. Lập ma trận kiểm thử, cutover/rollback, theo dõi deprecation warning và xác minh tính đúng đắn của dữ liệu sau đổi phiên bản.

## 2. Hiểu đúng vòng đời của một tính năng

Không phải mọi cảnh báo đều có nghĩa ứng dụng sẽ ngừng chạy ngay:

| Trạng thái | Ý nghĩa | Hành động phù hợp |
|---|---|---|
| **Supported** | Tính năng được hỗ trợ trên phiên bản hiện tại | Vẫn cần kiểm tra đúng ngữ nghĩa và hiệu năng |
| **Deprecated** | Vẫn có thể hoạt động, nhưng nhà phát triển khuyến nghị chuyển sang phương án mới | Lập kế hoạch thay thế, bổ sung test trước bản nâng cấp tiếp theo |
| **Removed** | Cú pháp hoặc procedure không còn được phiên bản/ngôn ngữ đích hỗ trợ | Phải đổi trước khi chuyển hoặc có phương án tương thích được hỗ trợ |
| **Behavior changed** | Vẫn chạy nhưng kết quả, mặc định, kiểu giá trị hay kế hoạch thay đổi | Test ngữ nghĩa, dữ liệu, hiệu năng và trường hợp biên |
| **Unavailable in target environment** | Bản managed/edition không có plugin, quyền hoặc cấu hình tương ứng | Chọn phương án thay thế, nâng gói hoặc đổi kiến trúc |

**Deprecated không phải là error.** Một câu query chạy thành công có thể trả **notification cảnh báo**. Ngược lại, câu query `CALL apoc.foo(...)` báo “procedure not found” có thể do plugin chưa cài hoặc thiếu quyền, không nhất thiết là thủ tục đã bị xóa khỏi phiên bản đó.

### Bốn câu hỏi trước khi thay thế

1. Tính năng bị deprecated trong **Cypher 5**, **Cypher 25** hay toàn bộ Neo4j DBMS?
2. Nó bị deprecated **từ phiên bản nào** và **removed ở phiên bản nào**, nếu đã công bố?
3. Phương án mới có **cùng kết quả, thứ tự, kiểu dữ liệu và ranh giới transaction** không?
4. Có phụ thuộc vào **APOC Core/Extended**, index provider, edition, quyền hoặc cấu hình máy chủ không?

Không chuyển mã chỉ vì hai tên API trông giống nhau. Với nhập dữ liệu và cập nhật lớn, chuyển từ một thủ tục APOC sang Cypher có thể thay đổi cách phân lô, xử lý lỗi và số transaction đã commit.

## 3. Quy trình rà soát tổng thể

~~~mermaid
flowchart TD
    A["Chốt phiên bản nguồn/đích<br/>DBMS, Cypher, APOC, Java Driver, SDN"] --> B["Lập inventory câu Cypher,<br/>schema, procedure, config"]
    B --> C["Đối chiếu changelog và<br/>cảnh báo deprecation"]
    C --> D{"Tính năng sẽ bị ảnh hưởng?"}
    D -->|"Không"| E["Giữ nguyên, tạo regression tests"]
    D -->|"Có"| F["Chọn cú pháp/API/config thay thế"]
    F --> G["Kiểm thử staging trên dữ liệu đại diện"]
    G --> H{"Kết quả, quyền và SLO đạt?"}
    H -->|"Chưa"| F
    H -->|"Đạt"| I["Canary / cutover có runbook"]
    E --> I
    I --> J["Theo dõi warning, lỗi, hiệu năng<br/>và khả năng rollback"]
~~~

Quy trình nên tạo một **compatibility register**: danh sách những chỗ có rủi ro, kèm người sở hữu, mức ưu tiên, phương án sửa và bằng chứng test. Chỉ ghi “đã nâng version thành công” là chưa đủ để biết chức năng nghiệp vụ có tiếp tục chạy đúng hay không.

## 4. Xác định chính xác môi trường trước khi audit

Cùng một query có thể chạy với **mặc định Cypher khác nhau** ở hai database, hoặc trên một instance có APOC khác instance còn lại. Tối thiểu phải ghi:

| Thông tin | Nguồn xác minh | Vì sao cần? |
|---|---|---|
| Phiên bản Neo4j DBMS | `CALL dbms.components()` hoặc inventory triển khai | Giới hạn cú pháp, procedure và công cụ quản trị |
| Edition/kiểu triển khai | Deployment manifest, console/DBMS metadata | Community/Enterprise/Aura có chức năng khác |
| Ngôn ngữ Cypher đang áp dụng | Chính sách phiên bản database và kiểm tra query | Cypher 5 khác Cypher 25 |
| Phiên bản APOC Core/Extended | Plugin inventory, danh mục procedure và tài liệu bản cài | Plugin có thể tách bộ, thay đổi thủ tục |
| Java Driver/SDN/Spring Boot | Khai báo dependency/BOM của ứng dụng | API client và câu query được sinh có thể thay đổi |
| Danh sách database, alias | Quản trị database theo quyền | Query có thể được chạy trên database khác dự kiến |
| Chính sách quyền | Vai trò/privileges và user thực chạy | Thiếu quyền có thể bị nhầm thành procedure removed |
| Cấu hình máy chủ | `neo4j.conf`, `apoc.conf`, environment, `SHOW SETTINGS` | Config có thể bị đổi tên, thay mặc định hoặc không còn hiệu lực |

Ví dụ truy vấn trên phiên bản có procedure tương ứng:

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

Đây là một cách nhận diện thành phần DBMS; trong môi trường bị hạn chế quyền hoặc dịch vụ quản lý, hãy dùng giao diện/version metadata chính thức được cung cấp.

**Đặc biệt trong cluster:** đừng suy rằng mọi member chạy cùng plugin/version/config chỉ vì một member báo đúng. Cần kiểm tra kế hoạch rolling upgrade, sự đồng nhất giữa thành viên và những khác biệt cho phép theo giai đoạn nâng cấp.

## 5. Dò cú pháp Cypher cũ trong source, query log và job vận hành

Cypher xuất hiện ở nhiều chỗ ngoài file `.cypher`:

- Chuỗi trong Java Driver: `tx.run("MATCH ...")`, `driver.executableQuery(...)`.
- `@Query` trong Spring Data Neo4j, câu query sinh từ repository method.
- Script migration tạo index/constraint, import CSV và seed dữ liệu.
- APOC `apoc.periodic.iterate` chứa Cypher bên trong hai chuỗi.
- Scheduled jobs, shell scripts, dashboards/BI và ứng dụng ETL.
- Query được log từ Neo4j server hoặc instrumentation ứng dụng.

Không tìm thấy chuỗi trong source **không chứng minh ứng dụng không sử dụng nó**: một repository method có thể sinh Cypher lúc chạy, hoặc một job khác chưa được đưa vào repo hiện tại. Để có độ bao phủ, kết hợp **đọc source**, **quan sát query thực thi** và **danh mục chức năng đang được phép gọi**.

### Bảng từ khóa rà soát ban đầu

| Từ khóa/mẫu | Nguy cơ | Cách xác minh |
|---|---|---|
| `USING PERIODIC COMMIT` | Đã bị loại trong Neo4j 5 | Xem pipeline `LOAD CSV` và đổi batching |
| `exists(n.someProperty)` | Cú pháp kiểm tra property cũ bị loại trong Neo4j 5 | Chuyển `IS NOT NULL` |
| `CREATE CONSTRAINT ... ON ... ASSERT` | DDL kiểu cũ bị loại ở Neo4j 5 | Dùng `FOR ... REQUIRE` |
| `CREATE INDEX ON :Label(prop)` | Cú pháp legacy index bị loại | Xác định loại RANGE/TEXT/POINT phù hợp |
| `CREATE BTREE INDEX` | B-tree index cũ không còn như trước | Lập chiến lược chuyển index theo truy vấn |
| `SHOW INDEXES BRIEF`/`VERBOSE` | Lệnh cũ không còn | Dùng `SHOW INDEXES`/`YIELD *` |
| `id(n)`/`id(r)` | Internal ID function đã deprecated | Xem `elementId` và khóa nghiệp vụ |
| `CALL { WITH x ... }` | Import variable kiểu cũ deprecated từ 5.23 | Dùng scope clause `CALL (x) { ... }` |
| `apoc.*` | Một số procedure/function thay thế bằng Cypher mới | Tra changelog, mode ngôn ngữ và Core/Extended |
| `db.index.vector.queryNodes` | Deprecated trong họ bản Cypher 25 từ 2026.04 | Kiểm tra `SEARCH` và phiên bản đích |
| `db.index.fulltext.queryNodes` | Deprecated từ Neo4j 2026.10 theo Cypher manual | Kiểm tra khả năng `SEARCH` của bản đích |

Đây là **danh sách gợi ý để khám phá**, không phải danh sách toàn bộ thứ đã removed. Một từ khóa có thể xuất hiện trong comment, test cho bản cũ hoặc trong tài liệu; cần đánh giá **query thực sự được chạy** và **ngôn ngữ Cypher mục tiêu** trước khi quyết định sửa.

## 6. Ví dụ 1 — Thay kiểm tra property bằng `IS NOT NULL`

Trong Neo4j 4.4, cú pháp sau từng được sử dụng:

~~~cypher
// Cú pháp legacy; KHÔNG dùng để chạy trên Neo4j 5.
MATCH (c:Customer)
WHERE exists(c.email)
RETURN c.customerId AS customerId;
~~~

Từ Neo4j 5, cách viết tương ứng:

~~~cypher
MATCH (c:Customer)
WHERE c.email IS NOT NULL
RETURN c.customerId AS customerId;
~~~

Tìm property thiếu:

~~~cypher
MATCH (c:Customer)
WHERE c.email IS NULL
RETURN c.customerId AS customerId;
~~~

**Vì sao cần test?** Property có giá trị chuỗi rỗng `''` **khác** property bị thiếu. Câu `c.email IS NOT NULL` vẫn chấp nhận chuỗi rỗng; nếu business rule cần email có nội dung, thêm validation riêng. **Không thay mọi `exists(...)`** theo từ khóa vì Cypher còn có `EXISTS { ... }` subquery để kiểm tra pattern — đó là **chức năng khác** và không phải cú pháp kiểm tra property legacy.

## 7. Ví dụ 2 — Chuyển DDL constraint và index cũ

### 7.1. Constraint `ON ... ASSERT`

Cú pháp Neo4j cũ:

~~~cypher
// LEGACY: không dùng để tạo mới trên Neo4j 5.
CREATE CONSTRAINT ON (c:Customer)
ASSERT c.customerId IS UNIQUE;
~~~

Cú pháp Neo4j 5:

~~~cypher
CREATE CONSTRAINT customer_customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

Sau đó kiểm tra schema:

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, labelsOrTypes, properties
RETURN name, type, labelsOrTypes, properties
ORDER BY name;
~~~

**Lưu ý:** `IF NOT EXISTS` giúp câu DDL tránh lỗi khi đối tượng tương đương đã tồn tại, nhưng **không chứng minh** schema đang có đúng tên/loại/property mà ứng dụng mong đợi. Khi migration, đối chiếu lại constraint thực sự được tạo, đặc biệt nếu dữ liệu nguồn đã có ID trùng khiến constraint mới không tạo được.

### 7.2. Từ index legacy sang index mới

Trước Neo4j 5, một số hệ thống dùng:

~~~cypher
// LEGACY:
CREATE INDEX ON :Customer(name);
~~~

Tùy workload, index mới có thể là:

~~~cypher
CREATE RANGE INDEX customer_name_range IF NOT EXISTS
FOR (c:Customer) ON (c.name);
~~~

Hoặc, nếu nhu cầu và kiểu truy vấn phù hợp:

~~~cypher
CREATE TEXT INDEX customer_name_text IF NOT EXISTS
FOR (c:Customer) ON (c.name);
~~~

Không có quy tắc “BTREE nào cũng chuyển thành TEXT”. **RANGE/TEXT/POINT** phục vụ tập predicate khác nhau; **FULLTEXT** và **VECTOR** có chức năng tìm kiếm riêng. Chọn loại index bằng query thực tế và kiểm chứng `EXPLAIN`/`PROFILE`.

~~~cypher
SHOW INDEXES
YIELD name, type, state, labelsOrTypes, properties
RETURN name, type, state, labelsOrTypes, properties
ORDER BY name;
~~~

Trước khi xác nhận thành công, bảo đảm index chuyển sang trạng thái `ONLINE`. Đừng chỉ kiểm tra DDL trả thành công rồi cho rằng query planner chắc chắn sử dụng nó.

## 8. Ví dụ 3 — Thay `USING PERIODIC COMMIT`

Trong Neo4j 4.4 và các tài liệu cũ, nhập CSV lớn có thể sử dụng:

~~~cypher
// LEGACY: đã removed trong Neo4j 5.
USING PERIODIC COMMIT 1000
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
CREATE (:Customer {customerId: row.customerId});
~~~

Neo4j 5 hỗ trợ phân lô qua `CALL { ... } IN TRANSACTIONS`. Với **Neo4j 5.23+**, dùng scope clause:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
CALL (row) {
    MERGE (c:Customer {customerId: row.customerId})
    SET c.name = row.name
} IN TRANSACTIONS OF 1000 ROWS;
~~~

**Điều kiện quan trọng:**

1. Truy vấn chứa `CALL ... IN TRANSACTIONS` phải chạy trong **implicit/auto-commit transaction**, không được bọc vào explicit/managed transaction bên ngoài.
2. Trong Neo4j Browser, tùy phiên bản, dùng `:auto` để chạy câu query đúng cơ chế; trong Java Driver, kiểm tra API implicit transaction phù hợp.
3. `MERGE` theo khóa ổn định nên đi kèm **uniqueness constraint** và kiểm tra dòng thiếu ID; không dùng `MERGE` một cách mù quáng với dữ liệu chưa chuẩn hóa.
4. Một số batch **đã commit** vẫn có thể tồn tại khi batch sau lỗi. Không giả định rollback toàn file CSV giống một transaction duy nhất.
5. `CALL (row) { ... }` là cú pháp scope clause mới của 5.23+; với bản Neo4j 5 sớm hơn, phải dùng cú pháp subquery tương thích hoặc lên bản hỗ trợ.

**Kiểm thử cần có:** số dòng nguồn, số ID hợp lệ, số node đích sau nhập; lỗi một batch; chạy lại cùng file; checkpoint/khóa định danh; kiểm tra không tạo node trùng và không tăng tổng tiền ngoài nghiệp vụ.

## 9. Ví dụ 4 — Scope clause mới trong `CALL` subquery

Neo4j 5.23 đã deprecated cách import biến bằng `WITH` ngay đầu subquery:

~~~cypher
// Cách cũ: vẫn có thể chạy với Cypher/version phù hợp,
// nhưng đã deprecated trên Neo4j 5.23+.
UNWIND [1, 2, 3] AS x
CALL {
    WITH x
    RETURN x * 10 AS y
}
RETURN x, y;
~~~

Thay bằng khai báo biến cần mang vào:

~~~cypher
UNWIND [1, 2, 3] AS x
CALL (x) {
    RETURN x * 10 AS y
}
RETURN x, y
ORDER BY x;
~~~

Kết quả mong đợi: `(1,10)`, `(2,20)`, `(3,30)`. Khi migration query phức tạp, phải so **số hàng**, **thứ tự**, **mức nhóm/aggregate** và **phạm vi biến**. Thay dấu ngoặc `CALL { ... }` bằng `CALL (x) { ... }` không tự đảm bảo mọi subquery cho kết quả tương đương nếu bạn quên nhập một biến.

## 10. `id()`, `elementId()` và khóa định danh nghiệp vụ

`id(node)` và `id(relationship)` đã deprecated; nên dùng `elementId()` khi cần tham chiếu một thực thể Neo4j trong phạm vi được tài liệu cho phép.

~~~cypher
MATCH (c:Customer)
RETURN elementId(c) AS elementId,
       c.customerId AS customerId
LIMIT 10;
~~~

**Nhưng không chuyển từ “lưu `id(c)` làm khóa nghiệp vụ” sang “lưu `elementId(c)` làm khóa nghiệp vụ”** rồi cho rằng đã khắc phục rủi ro. Các ID nội bộ/element ID không bảo đảm tính ổn định qua mọi transaction, xóa/tạo mới, backup/restore hoặc di trú database.

Nếu `customerId` là khóa của khách hàng, dùng nó cùng uniqueness constraint:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

MATCH (c:Customer {customerId: $customerId})
RETURN c;
~~~

Ứng dụng Java Driver/SDN nên truyền `customerId` qua tham số, không ghép ID nội bộ được lấy từ môi trường cũ thành đường dẫn REST/API. Đây là **thay đổi mô hình dữ liệu**, cần có migration dữ liệu và test mapping chứ không chỉ thay một hàm Cypher.

## 11. Rà soát procedure và function bằng `SHOW`

Trên Neo4j 5.9+ và các bản hỗ trợ cột `isDeprecated`:

~~~cypher
SHOW PROCEDURES
YIELD name, signature, isDeprecated
WHERE isDeprecated
RETURN name, signature
ORDER BY name;
~~~

~~~cypher
SHOW FUNCTIONS
YIELD name, signature, isDeprecated
WHERE isDeprecated
RETURN name, signature
ORDER BY name;
~~~

Các lệnh trả **danh sách chức năng hiện có và nhìn thấy được** ở server/tài khoản đang kết nối. Chúng **không** tìm được những tên procedure đã **removed** hoàn toàn: một thủ tục không có trong danh sách cũng có thể do chưa cài plugin, thiếu quyền hoặc khác Cypher language mode.

Ở các bản mới có cột `deprecatedBy`, có thể xem gợi ý thay thế:

~~~cypher
SHOW PROCEDURES
YIELD name, isDeprecated, deprecatedBy
WHERE isDeprecated
RETURN name, deprecatedBy
ORDER BY name;
~~~

~~~cypher
SHOW FUNCTIONS
YIELD name, isDeprecated, deprecatedBy
WHERE isDeprecated
RETURN name, deprecatedBy
ORDER BY name;
~~~

`deprecatedBy` có thể bằng `null` dù một function deprecated; vì không phải tính năng nào cũng có replacement dạng một tên duy nhất. Trong Neo4j 5 bản cũ không hỗ trợ cột này, dùng `SHOW ... YIELD *` để kiểm tra schema output thực tế trước khi chạy query trên.

### Dò đúng nhóm thư viện

~~~cypher
SHOW PROCEDURES
YIELD name, signature
WHERE name STARTS WITH 'apoc.'
   OR name STARTS WITH 'gds.'
RETURN name, signature
ORDER BY name;
~~~

~~~cypher
SHOW FUNCTIONS
YIELD name, signature
WHERE name STARTS WITH 'apoc.'
   OR name STARTS WITH 'gds.'
RETURN name, signature
ORDER BY name;
~~~

Không có `gds.*` không tự động nghĩa GDS bị removed: Graph Data Science có thể chưa được triển khai trên môi trường đó. Với Neo4j Aura, Core/Extended và GDS còn phụ thuộc **sản phẩm/gói**.

**Quy trình kiểm tra procedure đáng tin:**

1. Thu được **tên đầy đủ và signature** từ ứng dụng/job đang dùng.
2. Tra tài liệu bản nguồn để biết chức năng và kết quả.
3. Kiểm tra bản đích **có cài và cho phép gọi** đúng procedure/function không.
4. Kiểm tra **deprecated/removed** trong release notes đúng phiên bản Cypher.
5. Chạy test so kết quả và side effect bằng user application thật; không chỉ test bằng admin.

## 12. APOC Core, APOC Extended và Cypher 25

Từ Neo4j 5, APOC được chia thành **APOC Core** (được Neo4j hỗ trợ chính thức) và **APOC Extended** (do cộng đồng duy trì). Một hệ thống cũ dùng “APOC Full” không thể suy rằng chỉ thêm một JAR Core trên bản mới là đủ.

Khi nâng APOC, cần rà soát **cả phiên bản Neo4j và ngôn ngữ Cypher**:

- Neo4j 2025.06 giới thiệu **Cypher 25**, đồng thời cho phép lựa chọn **Cypher 5** theo cách được hỗ trợ.
- Các thay đổi APOC kể từ thế hệ 2025.07+ được phát triển cho **Cypher 25**; chức năng APOC cho Cypher 5 đã đóng băng ở mốc tương ứng.
- Một procedure không hỗ trợ Cypher 25 có thể vẫn dùng được với `CYPHER 5` **khi môi trường hỗ trợ ngôn ngữ đó và procedure còn được cung cấp**. Đây là giải pháp tương thích có điều kiện, không phải kế hoạch migration dài hạn.
- Một số chức năng APOC có phương án **Cypher thuần** đầy đủ/đủ gần, nhưng ngữ nghĩa cần được kiểm tra từng trường hợp.

Ví dụ quan sát mode:

~~~cypher
// Chỉ có trên DBMS hỗ trợ chọn Cypher version (Neo4j 2025.06+).
CYPHER 5
RETURN randomUUID() AS requestId;
~~~

~~~cypher
CYPHER 25
RETURN randomUUID() AS requestId;
~~~

Hai truy vấn minh họa cách chọn **phiên bản ngôn ngữ cho từng query**. Không thể đặt `CYPHER 25` trên Neo4j 5.26 rồi chờ driver tự dịch; server không hỗ trợ ngôn ngữ đó.

### Những lựa chọn thay thế APOC thường gặp

| Mẫu cũ | Hướng mới/điều kiện | Lưu ý khi di trú |
|---|---|---|
| `apoc.create.uuid()` | `randomUUID()` khi cần chuỗi ID | Không thay thế cơ chế uniqueness của business ID |
| `apoc.coll.contains(list, x)` | `x IN list`; tài liệu APOC ghi deprecated trong Cypher 25 | Kiểm tra xử lý `null`/kiểu dữ liệu |
| `apoc.do.when`/`apoc.do.case` | Conditional queries trong Cypher 25 khi phiên bản hỗ trợ | Kiểm tra nhánh có ghi, kết quả và số hàng |
| `apoc.periodic.iterate` | `CALL { ... } IN TRANSACTIONS`; cân nhắc `IN CONCURRENT TRANSACTIONS` khi phiên bản Cypher 25 hỗ trợ | Khác cấu hình lô, transaction boundaries, retry, commit |
| `apoc.import.csv` | `LOAD CSV` khi có phạm vi chức năng phù hợp | Kiểm tra nguồn file/URL và các quy ước import |
| `apoc.load.json` | Có thể parse ở Java/application hoặc giữ APOC nếu môi trường cho phép | Không có một cú pháp `LOAD JSON` tương đương tổng quát trong mọi phiên bản |

Đặc biệt, `apoc.periodic.iterate` được đánh dấu deprecated trong **Cypher 25 từ APOC/Neo4j 2026.04**. Điều này **không có nghĩa** phải dừng chạy ngay một pipeline đang phục vụ production; cần kiểm tra phiên bản thực tế, nguy cơ phiên bản đích không hỗ trợ và kế hoạch di trú có kiểm thử.

### Không thay thế máy móc bằng một query nhìn giống nhau

Giả sử job cũ dùng `apoc.periodic.iterate` với `batchSize=1000`, `parallel=true`, `retries` và câu query được nội suy trong chuỗi. Khi chuyển sang Cypher:

1. Xác định **tập hàng nguồn** và cách import biến.
2. Chọn chạy tuần tự hay đồng thời theo version hỗ trợ.
3. Định nghĩa **kích thước lô**, lỗi một lô và chiến lược `ON ERROR` khi có.
4. Kiểm tra những lô **đã commit** nếu job lỗi giữa chừng.
5. Thiết kế **idempotency/checkpoint** để chạy lại không ghi trùng.
6. Đo tài nguyên/lock contention, so số node/relationship và tổng hợp nghiệp vụ.

Thay đổi cơ chế phân lô có thể thay hiệu năng lẫn **tính đúng đắn**, nên phải thử trên dữ liệu mẫu đủ lớn và các ca lỗi.

## 13. GQLSTATUS, deprecation notifications và kết quả chạy thật

Một số cú pháp deprecated vẫn được Neo4j chấp nhận và phát **notification**. Để phát hiện, cần chạy **chính query ứng dụng dùng**, không chỉ query tự viết lại để kiểm tra.

### 13.1. `EXPLAIN` là công cụ kiểm tra tương thích ban đầu

~~~cypher
EXPLAIN
MATCH (c:Customer)
WHERE c.customerId = $customerId
RETURN c.email AS email;
~~~

`EXPLAIN` biên dịch query và cho biết plan dự kiến, **không thực thi**. Nếu cú pháp không còn hợp lệ, nó có thể cho lỗi sớm; với một số cách dùng không khuyến nghị, nó có thể trả notification.

Tuy nhiên, `EXPLAIN` **không chứng minh** transaction ghi, procedure có side effect, quyền, dữ liệu thật hoặc kết quả ánh xạ về Java đều đúng. Để xác minh vận hành, cần chạy test tích hợp và kiểm tra trạng thái graph.

### 13.2. Quan sát trong Java Driver

Neo4j Java Driver cung cấp `ResultSummary`, bao gồm các notification/server status từ lần chạy. Với những bản driver cũ còn hỗ trợ API tương ứng:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

void inspectQuery(Driver driver) {
    try (Session session = driver.session(
            SessionConfig.forDatabase("neo4j"))) {
        var result = session.run("""
            EXPLAIN
            MATCH (n:Customer)
            RETURN n.email AS email
            LIMIT 10
            """);

        var summary = result.consume();
        summary.notifications().forEach(notification -> {
            System.out.println(notification.code());
            System.out.println(notification.description());
        });
    }
}
~~~

Ở các bản driver mới, `ResultSummary.gqlStatusObjects()` là hướng quan sát trạng thái theo GQL; `notifications()` có thể là API tương thích cũ/deprecated tùy version. Khi lập mã production, **pin version Java Driver**, dùng API notification tương ứng và thu thập sự kiện có cấu trúc thay vì phân tích chuỗi thông báo.

Không in dữ liệu nhạy cảm/whole query text cùng tham số vào log. Nếu CI thu deprecation warnings, nên lưu **mã, loại, vị trí, tên testcase và phiên bản môi trường**; triệt tiêu duplicate có kiểm soát, nhưng không bỏ qua warning mới.

### 13.3. Không tắt cảnh báo để được “test xanh”

Tăng ngưỡng notification severity hoặc tắt một nhóm notification có thể làm log bớt nhiễu, nhưng **không giải quyết** deprecated feature. Trong giai đoạn migration, nên thu được thông tin cảnh báo đầy đủ trong môi trường test, rồi **chuyển warning có liên quan thành công việc kỹ thuật** có owner và thời hạn.

## 14. Kiểm tra cấu hình đã đổi tên hoặc không còn tác dụng

Giữa Neo4j 4.4 và 5, nhiều khóa `neo4j.conf` được tổ chức lại vào các namespace như `server`, `dbms`, `db`, `initial`, `browser` và `client`. Đồng thời, một số mặc định hoặc kiểu giá trị thay đổi.

### Những ví dụ chuyển đổi cần nhận biết

| Khóa kiểu cũ | Ví dụ khóa trên Neo4j 5 | Mục đích |
|---|---|---|
| `dbms.memory.heap.initial_size` | `server.memory.heap.initial_size` | JVM heap ban đầu |
| `dbms.memory.heap.max_size` | `server.memory.heap.max_size` | JVM heap tối đa |
| `dbms.memory.pagecache.size` | `server.memory.pagecache.size` | Page cache |
| `dbms.connector.bolt.listen_address` | `server.bolt.listen_address` | Địa chỉ Bolt lắng nghe |
| `dbms.logs.query.enabled` | `db.logs.query.enabled` | Query logging |
| `metrics.enabled` | `server.metrics.enabled` | Hệ thống metrics theo bản hỗ trợ |
| `dbms.config.strict_validation` | `server.config.strict_validation.enabled` | Xác thực cấu hình khi khởi động; semantics/default đã đổi |

Bảng là **ví dụ định hướng** cho di trú 4.4 → 5, không phải bảng mapping đầy đủ và không áp dụng tự động cho mọi bản 2025/2026. Có khóa bị **removed**, có khóa đổi **ý nghĩa hoặc giá trị hợp lệ**, và có khóa chỉ dùng trong Enterprise. Đối chiếu chính thức tại *Changes to configuration settings in Neo4j 5* trước khi chạy migration.

### Nguyên tắc thay cấu hình

1. **Kiểm tra bản nguồn và đích**: biết chính xác file, container environment, chart values và config override nào đang được dùng.
2. **Lập diff của các khóa thực sự khai báo**, phân biệt setting mặc định với setting đã chỉnh.
3. **Map từng khóa** bằng bảng chính thức, không dùng thay thế chuỗi `dbms.` thành `server.` trên toàn file.
4. **Kiểm tra giá trị và mặc định mới**, nhất là memory, timeout, logging, clustering và security.
5. **Validate trước khi startup**, rồi kiểm tra giá trị runtime sau khởi động.
6. **Trên cluster, xác minh từng member**; một cấu hình chỉ chạy được ở node đầu không đảm bảo toàn cụm đúng.

Không chuyển các khóa thuộc namespace `internal.*` từ changelog vào production chỉ vì tên trông có vẻ thay thế. Neo4j không hỗ trợ hoặc khuyến nghị tùy biến các thiết lập nội bộ; chúng có thể đổi mà không thông báo.

## 15. Kiểm tra cấu hình runtime bằng `SHOW SETTINGS`

Khi có quyền xem settings, có thể liệt kê những setting **đã deprecated**:

~~~cypher
SHOW SETTINGS
YIELD name, value, defaultValue, isExplicitlySet, isDeprecated
WHERE isDeprecated
RETURN name, value, defaultValue, isExplicitlySet
ORDER BY name;
~~~

Hoặc tập trung vào các setting quan trọng:

~~~cypher
SHOW SETTINGS
YIELD name, value, startupValue, isExplicitlySet
WHERE name STARTS WITH 'server.memory.'
   OR name STARTS WITH 'server.bolt.'
   OR name STARTS WITH 'db.logs.query.'
RETURN name, value, startupValue, isExplicitlySet
ORDER BY name;
~~~

**Ba giới hạn quan trọng:**

- `SHOW SETTINGS` có cột `isDeprecated` từ các bản Neo4j 5 hỗ trợ (5.9+); các bản cũ hơn có thể không có cột.
- `SHOW SETTINGS` hiển thị cấu hình của **server đang xử lý query**, **không tổng hợp mọi member**. Muốn kiểm tra member cụ thể, dùng kết nối trực tiếp `bolt://` với quyền phù hợp theo hướng dẫn vận hành.
- Tính năng này **không khả dụng trên Neo4j Aura** theo tài liệu Operations hiện hành. Với Aura, cần dùng các công cụ/configuration surfaces mà dịch vụ cung cấp, không coi lỗi lệnh `SHOW SETTINGS` là DB hỏng.

`isExplicitlySet = false` có nghĩa setting theo cấu hình mặc định hiện hành, không hẳn là “giá trị bị bỏ quên”. Một thay đổi default khi nâng cấp có thể khiến hệ thống hành xử khác dù đội vận hành **không chỉnh** file.

## 16. Validate file trước khi khởi động

Trên môi trường Neo4j tự quản lý có lệnh quản trị tương ứng:

~~~bash
bin/neo4j-admin server validate-config
~~~

Để xem thêm chi tiết:

~~~bash
bin/neo4j-admin server validate-config --verbose
~~~

Lệnh kiểm tra cấu hình Neo4j và Log4j theo phạm vi hỗ trợ của bản cài đặt; nên chạy trong **image/container/host của phiên bản đích** với cùng cấu hình sẽ deploy. Kết quả “validation successful” **không chứng minh** thủ tục APOC đã được cài đúng, license hợp lệ, cluster có quorum, dữ liệu tương thích hay Java Driver chạy được. Đây là một **cổng kiểm tra cấu hình**, không phải toàn bộ migration test.

### Không vô hiệu hóa strict validation để né lỗi

Neo4j 5 bật kiểm tra cấu hình nghiêm ngặt theo mặc định:

~~~properties
# Ý nghĩa mặc định theo Neo4j 5; giữ true khi có thể.
server.config.strict_validation.enabled=true
~~~

Nếu bỏ một khóa cũ vào `neo4j.conf`, server có thể **không khởi động**. Cách sửa là chuyển sang khóa phù hợp, không phải đổi `strict_validation` thành `false` rồi coi sự cố đã xong. Trên một số loại cấu hình, strict validation bị tắt có thể khiến setting sai **bị bỏ qua âm thầm**, tạo trạng thái runtime khác ý định.

## 17. Đặc biệt: `apoc.conf` không còn đặt trong `neo4j.conf`

Từ APOC/Neo4j 5, những tùy chọn `apoc.*` được đặt trong **`apoc.conf`** (cùng thư mục cấu hình với `neo4j.conf`), hoặc bằng **biến môi trường** được APOC hỗ trợ.

**Sai trên Neo4j 5:**

~~~properties
# neo4j.conf -- legacy, KHÔNG giữ apoc.* ở đây.
apoc.import.file.enabled=true
apoc.export.file.enabled=true
~~~

**Đúng về vị trí cấu hình:**

~~~properties
# apoc.conf -- ví dụ thiết lập hạn chế mặc định.
apoc.import.file.enabled=false
apoc.export.file.enabled=false
~~~

`apoc.conf` có thể không được tạo sẵn khi cài plugin; đội triển khai phải tự quản lý file nếu có cấu hình tùy chọn. Đặt `apoc.*` trong `neo4j.conf` trên bản 5 có thể làm strict validation từ chối startup hoặc **bị bỏ qua** nếu tắt validation.

**Đừng mở `true` cho file import/export chỉ để vượt lỗi một bài thử.** Chức năng truy cập file, URL hoặc procedure mở rộng cần rà soát bảo mật. Những setting Neo4j quản lý allowlist/unrestricted procedures thuộc chính sách cấu hình Neo4j, không tự chuyển tất cả vào `apoc.conf`.

## 18. Java Driver và Spring Data Neo4j cũng cần kiểm tra

Ngay cả khi Cypher viết tay tương thích, một ứng dụng vẫn có thể gặp:

- API driver cũ bị deprecated/đổi tên khi nâng major version.
- Cơ chế transaction retry, callback và timeout khác kỳ vọng.
- Repository derived queries sinh Cypher mới.
- `@Query` dùng một procedure đã removed hoặc chỉ có trong APOC Extended.
- Entity mapping, tải relationship hoặc query custom mất một số trường trả về.
- Lớp Spring Boot/SDN mới dùng package/module và BOM dependency khác.

### Ví dụ Java Driver managed transaction

API hiện đại khuyến nghị:

~~~java
try (var session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    return session.executeRead(tx -> tx.run("""
        MATCH (c:Customer {customerId: $customerId})
        RETURN c.name AS name
        """, Map.of("customerId", customerId))
        .single().get("name").asString());
}
~~~

Nếu ứng dụng vẫn dùng API cũ như `readTransaction(...)`/`writeTransaction(...)`, hãy tra migration guide của **chính Java Driver version** đang chuyển đến; `executeRead`/`executeWrite` là lựa chọn tương ứng trong driver hiện đại. Không chỉ thay tên method rồi quên rằng callback managed transaction **có thể retry**, vì chạy lại tác vụ ghi không idempotent có thể tạo dữ liệu trùng hoặc lặp tác dụng bên ngoài.

### Với Spring Data Neo4j

1. Pin/đối chiếu bộ **Spring Boot BOM + SDN + Neo4j Java Driver + Java runtime**.
2. Chạy `@DataNeo4jTest`/integration tests trên **Neo4j phiên bản đích**.
3. Quan sát **Cypher thực tế** SDN phát đi bằng logging/query log; không suy từ tên repository method.
4. Test cả **truy vấn sinh tự động**, `@Query`, transaction read-only và mapping node/relationship.
5. So số node/relationship và các phép tổng hợp để phát hiện nhân hàng hoặc thay đổi kết quả.
6. Đối với lỗi deprecation ở server, thu notification từ lời gọi repository thực chứ không chỉ những query chạy bằng Neo4j Browser.

Nếu gói managed không cho truy cập query log/server settings, bổ sung instrumentation ở tầng ứng dụng để lấy bằng chứng tương thích mà không cố can thiệp máy chủ.

## 19. Ma trận kiểm thử migration

| Hạng mục | Test trước nâng cấp | Test ở phiên bản đích | Điều kiện PASS |
|---|---|---|---|
| Query đọc Cypher | Bộ tham số và kết quả baseline | Chạy query thật + thu notification | Cùng dữ liệu nghiệp vụ và không còn deprecated blocker |
| Query ghi | State trước/sau, khóa nghiệp vụ | Replay trên graph thử nghiệm | Không trùng node/relationship, đúng transaction |
| `CALL` subquery | Import variables, aggregation, cardinality | So old/new syntax | Cùng số hàng, kiểu, giá trị và side effect |
| Import CSV | Dòng hợp lệ/trùng/lỗi, batch checkpoint | Chạy `IN TRANSACTIONS` | Số dòng/node/edge đúng, phục hồi sau lỗi |
| Index/constraint | `SHOW INDEXES`/`SHOW CONSTRAINTS` | Tạo và kiểm tra trạng thái | Schema tương đương, index ONLINE |
| APOC/GDS | Danh sách procedure/function thực dùng | Tra presence/deprecation và chạy API | Chức năng, quyền và kết quả phù hợp |
| Config | Danh sách override và default nguồn | `validate-config` + runtime settings | Không dùng setting removed/sai ý nghĩa |
| Java Driver/SDN | Regression tests và query logs | Test trên server đích | Kết quả/mapping/retry đúng |
| Security | Role, procedure privilege, TLS | Positive/negative authorization tests | Không cấp quyền dư và không lộ dữ liệu |
| Hiệu năng | p50/p95/p99, DB Hits, throughput | Benchmark dữ liệu đại diện | Đạt SLO trong sai số chấp nhận |
| Recovery | Backup/restore và cutover runbook | Restore rehearsal, dry-run rollback | RPO/RTO và đối soát đạt |

**Tại sao cần cùng dữ liệu và tham số?** Một câu `MATCH` có thể đổi kế hoạch do thống kê index hoặc khác phân phối relationship. Nếu test nguồn với 100 node nhưng test đích với 10 triệu node, không thể biết latency đổi do phiên bản hay do dữ liệu.

### Ví dụ regression test với dữ liệu nhỏ

Dataset kiểm thử:

~~~cypher
CREATE CONSTRAINT mig_customer_id_unique IF NOT EXISTS
FOR (c:MigCustomer)
REQUIRE c.customerId IS UNIQUE;
~~~

~~~cypher
MERGE (a:MigCustomer {customerId: 'C01'})
SET a.email = 'an@example.test'
MERGE (b:MigCustomer {customerId: 'C02'})
SET b.email = null
MERGE (o:MigOrder {orderId: 'O01'})
SET o.amount = 120000
MERGE (a)-[:PLACED]->(o);
~~~

Kiểm tra các kết quả bất biến:

~~~cypher
MATCH (c:MigCustomer)
RETURN count(c) AS customers,
       count(c.email) AS withEmail;
// customers = 2, withEmail = 1
~~~

~~~cypher
MATCH (c:MigCustomer)-[:PLACED]->(o:MigOrder)
RETURN c.customerId AS customerId,
       o.orderId AS orderId,
       o.amount AS amount;
// C01, O01, 120000
~~~

Khi sửa syntax `exists(c.email)` thành `c.email IS NOT NULL`, kết quả tập node phải tương đương trên cả dữ liệu thiếu/rỗng/null. Khi nâng query dùng `CALL`, cần thêm test nhiều relationship, aggregation và thứ tự trả về — chỉ test một node thường bỏ sót lỗi cardinality.

## 20. Cảnh báo, mức độ ưu tiên và compatibility register

Không phải mọi deprecated feature có cùng mức rủi ro:

| Ưu tiên | Điều kiện | Ví dụ | Hành động |
|---|---|---|---|
| **P0 — Chặn nâng cấp** | Đích đã removed tính năng và luồng quan trọng đang phụ thuộc | `USING PERIODIC COMMIT` khi lên Neo4j 5 | Sửa và test trước cutover |
| **P1 — Rủi ro sớm** | Deprecated trong version đích hoặc gần đến mốc removal, ảnh hưởng dữ liệu | `apoc.periodic.iterate` trong Cypher 25 phiên bản liên quan | Có owner và ngày migration, test trước release |
| **P2 — Rủi ro vận hành** | Config cũ/default đổi, có thể gây downtime hoặc drift | `dbms.logs.query.enabled` cũ | Migrate config và validate |
| **P3 — Nợ kỹ thuật theo dõi** | Deprecated nhưng chưa có deadline/ảnh hưởng thấp | Hàm tiện ích APOC có bản Cypher thay thế | Theo dõi và tránh tạo thêm dependency mới |

Mẫu register:

| ID | Nguồn sử dụng | Feature/config | Source → Target | Nguy cơ | Replacement | Owner | Bằng chứng |
|---|---|---|---|---|---|---|---|
| MIG-001 | Import job | `USING PERIODIC COMMIT` | 4.4 → 5.26 | Removed | `CALL ... IN TRANSACTIONS` | Data team | Batch replay PASS |
| MIG-002 | Repository `@Query` | `id(n)` | 5 → 2026.x | Deprecated | Business ID / `elementId` theo phạm vi | API team | Integration test PASS |
| MIG-003 | APOC job | `apoc.periodic.iterate` | Cypher 5 → 25 | Deprecated theo release | Cypher batch + retry thiết kế mới | Platform | Load test PENDING |
| MIG-004 | Deployment config | `apoc.import.file.enabled` trong `neo4j.conf` | 4.4 → 5 | Sai nơi khai báo | `apoc.conf` | SRE | validate-config PASS |

Các trạng thái PASS/PENDING trong bảng là **ví dụ minh họa**, không phải bằng chứng hệ thống cụ thể đã được kiểm thử.

## 21. Kế hoạch nâng cấp và rollback có kiểm soát

### Bước 1 — Baseline và backup

Chụp phiên bản, schema, danh sách plugin, settings override, các warning hiện có và truy vấn quan trọng. Tạo backup theo quy trình được hỗ trợ và **diễn tập restore** trên môi trường sạch. Phải hiểu đường nâng cấp được tài liệu Neo4j hỗ trợ; **không giả định có thể hạ cấp store đã nâng phiên bản chỉ bằng thay image Docker**.

### Bước 2 — Chạy compatibility audit

Quét source/query log, dùng `SHOW` để tìm deprecation, tra changelog source/target. Đánh dấu những tính năng **removed** là blocker, đánh dấu deprecated có nguy cơ thành nhiệm vụ cụ thể. Cập nhật config mới trong một nhánh hoặc manifest có thể kiểm soát version.

### Bước 3 — Sửa và thử trên staging

Khởi tạo database staging gần dữ liệu production, chạy script schema, import và integration tests Java/SDN. Thu notification, so dữ liệu/kết quả/các quyền. Đo p95/p99, throughput, contention, locks và rollback khi có tải.

### Bước 4 — Kiểm tra canary và rollback

Tùy kiến trúc standalone/cluster/managed, chuẩn bị phương án canary hoặc rolling upgrade **đúng tài liệu topology và version**. Ghi rõ tiêu chí dừng: lỗi Cypher, mất dữ liệu, failover bất thường, tỷ lệ timeout hoặc p99 vượt ngưỡng.

Rollback cần kế hoạch cho **dữ liệu đã ghi vào phiên bản mới**. Nếu database đã thay định dạng hoặc có ghi mới, **đổi binary về version cũ** có thể không được hỗ trợ. Có thể cần restore backup sang môi trường cũ và replay/đối soát các ghi phát sinh sau cutover.

### Bước 5 — Sau cutover

- Quan sát exception và warning deprecation mới.
- Xác minh job ETL, import CSV, GDS/APOC và các scheduled jobs ít chạy.
- So dashboard query/transaction/lock với baseline.
- Kiểm tra quyền procedure và TLS, tránh mở quyền quá rộng để “chữa” lỗi nâng cấp.
- Đối chiếu dữ liệu node/relationship/index sau khi tải ổn định.
- Đóng register chỉ khi có bằng chứng tương thích, không chỉ vì deployment được gắn nhãn “success”.

## 22. Những lỗi thường gặp

| Lỗi | Vì sao nguy hiểm? | Cách tránh |
|---|---|---|
| Chỉ nâng container rồi gọi `RETURN 1` | Không kiểm tra app query, plugin, job và dữ liệu | Integration tests và compatibility inventory |
| Coi deprecated = removed ngay | Có thể sửa gấp không cần thiết hoặc bỏ cơ hội migration có kế hoạch | Đọc mốc version/changelog cụ thể |
| Coi “procedure not found” luôn là removed | Có thể do plugin chưa cài, thiếu quyền hoặc version Cypher | `SHOW PROCEDURES`, cài đặt, RBAC và docs |
| Thay mọi `id(n)` bằng `elementId(n)` cho business ID | Vẫn phụ thuộc ID do DB quản lý | Dùng khóa nghiệp vụ bền vững |
| Chuyển BTREE sang TEXT không xét query | Query filter/sort có thể không dùng index dự kiến | Chọn RANGE/TEXT/POINT theo predicate |
| Chuyển `USING PERIODIC COMMIT` nhưng bỏ qua commit từng lô | Có thể ghi dở và duplicate khi retry | Checkpoint/idempotency, test lỗi giữa job |
| Giữ `apoc.*` trong `neo4j.conf` | Startup fail hoặc setting bị bỏ qua trên Neo4j 5 | Chuyển đúng sang `apoc.conf`/env |
| Tắt strict validation | Che lỗi cấu hình và gây drift | Fix setting, dùng validate-config |
| Chỉ đọc một member khi audit cluster | Member khác có plugin/config/version khác | Kiểm tra mọi member theo topology |
| Không lưu query/notification từ SDN | Bỏ sót câu query do framework sinh | Log/test query thực |
| Chạy `PROFILE` với query ghi trên production | `PROFILE` thực thi và có side effect | Dùng staging/backup, `EXPLAIN` trước |
| Rollback chỉ bằng đổi Docker tag | Store/ghi mới có thể không tương thích ngược | Backup/restore, đối soát và runbook |

## 23. Bài tập tự luyện

### Bài 1 — Xác định cú pháp cần sửa

Hệ thống Neo4j 4.4 có query:

~~~cypher
MATCH (c:Customer)
WHERE exists(c.email)
RETURN id(c) AS id, c.email AS email;
~~~

Khi chuyển sang Neo4j 5, bạn sẽ sửa điều gì? Có nên trả `elementId(c)` thay cho `id(c)` và tiếp tục dùng làm khóa nghiệp vụ?

**Gợi ý đáp án:** Đổi `exists(c.email)` thành `c.email IS NOT NULL`; `id(c)` đã deprecated, `elementId(c)` có thể thay khi cần identifier do DB cung cấp nhưng **không nên** làm khóa lâu dài. Nên dùng `customerId` nghiệp vụ và constraint bảo đảm duy nhất.

### Bài 2 — Procedure không xuất hiện

Sau khi nâng lên môi trường mới, `CALL apoc.load.json(...)` báo “procedure not found”. Nêu ít nhất bốn khả năng và cách kiểm chứng.

**Gợi ý đáp án:** Plugin Core/Extended chưa được cài; phiên bản APOC không phù hợp Neo4j; thủ tục không hỗ trợ Cypher language mode; bị chặn bởi allowlist/quyền; hoặc đã removed thực sự ở version đích. Kiểm tra `SHOW PROCEDURES`, phiên bản, role/procedure privilege, release notes và danh sách hỗ trợ của dịch vụ quản lý.

### Bài 3 — Thay phân lô

Một job cũ dùng `USING PERIODIC COMMIT 1000`. Khi đổi sang `CALL { ... } IN TRANSACTIONS OF 1000 ROWS`, tại sao phải kiểm thử chạy lại sau lỗi ở lô thứ ba?

**Gợi ý đáp án:** Vì lô trước có thể đã commit, trong khi lô lỗi rollback; chạy lại không idempotent có thể tạo trùng hoặc cộng dồn sai. Cần khóa duy nhất, `MERGE` theo business key, checkpoint và đối chiếu số liệu sau khi resume.

### Bài 4 — Cấu hình “được bỏ qua”

Người vận hành giữ `apoc.import.file.enabled=true` trong `neo4j.conf` sau khi lên Neo4j 5, rồi tắt `server.config.strict_validation.enabled` để server chạy. Điều gì sai?

**Gợi ý đáp án:** `apoc.*` phải nằm ở `apoc.conf` hoặc env tương ứng. Tắt strict validation có thể làm setting sai bị bỏ qua; hệ thống hoạt động khác mong đợi và kém an toàn. Chuyển setting sang nơi hợp lệ và chỉ bật file import khi có chính sách quyền phù hợp.

### Bài 5 — Thực tế không có warning

Đội chạy `SHOW PROCEDURES` và thấy không có procedure nào `isDeprecated=true`. Có thể kết luận ứng dụng không còn sử dụng tính năng deprecated không?

**Gợi ý đáp án:** Không. Danh sách chỉ phản ánh thủ tục hiện có và nhìn thấy được; cú pháp Cypher deprecated có thể nằm trong query, function deprecated có bảng riêng, procedure removed có thể không xuất hiện, hoặc những job không chạy trong buổi audit. Cần inventory mã nguồn và runtime notifications từ app thực.

### Bài 6 — Thay đổi tính đúng đắn sau migration

Query viết lại từ `CALL { WITH x ... }` sang `CALL (x) { ... }` chạy không lỗi, nhưng số hàng kết quả tăng gấp ba. Có coi migration thành công không?

**Gợi ý đáp án:** Không. Cần đối chiếu các biến được import, grouping, relationship expansion và aggregate, so kết quả trên cùng dataset. Query compile được chỉ là một điều kiện; **ngữ nghĩa và kết quả nghiệp vụ** mới quyết định PASS.

### Bài 7 — Rollback sau nâng cấp

Nhóm nâng Neo4j, cho ứng dụng ghi dữ liệu trong một ngày, rồi muốn đổi binary quay về bản cũ khi có lỗi. Vì sao kế hoạch này thiếu an toàn?

**Gợi ý đáp án:** Store có thể đã được upgrade, không hỗ trợ downgrade trực tiếp; dữ liệu ghi mới không tồn tại trong backup trước cutover. Cần kế hoạch restore/failback được hỗ trợ, đồng bộ/đối soát các ghi phát sinh và kiểm tra trước khi chuyển traffic về môi trường cũ.

## 24. Tài liệu chính thức để đối chiếu phiên bản

- [Neo4j Upgrade and Migration Guide](https://neo4j.com/docs/upgrade-migration-guide/current/)
- [Breaking changes between Neo4j 4.4 and Neo4j 5](https://neo4j.com/docs/upgrade-migration-guide/current/version-5/migration/breaking-changes/)
- [Changes to configuration settings in Neo4j 5](https://neo4j.com/docs/upgrade-migration-guide/current/version-5/changelogs/configuration-settings/)
- [Cypher additions, deprecations, removals and compatibility](https://neo4j.com/docs/cypher-manual/current/deprecations-additions-removals-compatibility/)
- [Cypher — Show functions](https://neo4j.com/docs/cypher-manual/current/functions/show-functions/)
- [Neo4j Operations — Show procedures](https://neo4j.com/docs/operations-manual/current/procedures/show-procedures/)
- [Neo4j Operations — Show configuration settings](https://neo4j.com/docs/operations-manual/current/configuration/show-settings/)
- [Neo4j Operations — Validate configurations](https://neo4j.com/docs/operations-manual/current/configuration/validate-config/)
- [APOC Core — Migration Guide](https://neo4j.com/docs/apoc/current/migration-guide/)
- [APOC and Cypher versions](https://neo4j.com/docs/apoc/current/apoc-and-cypher/cypher-versions/)
- [Migrate APOC procedures/functions to Cypher](https://neo4j.com/docs/apoc/current/apoc-and-cypher/cypher-migration/)
- [Neo4j Java Driver — Result summaries and notifications](https://neo4j.com/docs/java-manual/current/result-summary/)
- [Spring Data Neo4j reference](https://docs.spring.io/spring-data/neo4j/reference/)

Các đường dẫn `current` cập nhật theo release. Khi triển khai, hãy **khóa tài liệu vào đúng phiên bản nguồn/đích**, đặc biệt ở giai đoạn Neo4j 5 → 2025/2026 và Cypher 5 → Cypher 25. Một tính năng có thể đang deprecated nhưng chưa removed, hoặc removed trong Cypher 25 nhưng vẫn tồn tại với `CYPHER 5` nếu server/APOC hỗ trợ.

## 25. Ghi nhớ

- **Deprecated là lời cảnh báo cần quản lý**, còn **removed là vấn đề tương thích phải xử lý** trước khi nâng cấp.
- **Audit cả Cypher, schema DDL, procedure/function, cấu hình, plugin và client libraries**; không chỉ kiểm tra database khởi động.
- **`SHOW PROCEDURES`, `SHOW FUNCTIONS`, `SHOW SETTINGS` và runtime notifications** hỗ trợ phát hiện deprecation nhưng không thay inventory và integration tests.
- **Cypher 5 và Cypher 25 có vòng đời khác nhau**; `CYPHER 5` là phương án tương thích có điều kiện, không phải chiến lược lâu dài để né migration.
- **APOC Core/Extended và `apoc.conf` cần rà soát độc lập** với `neo4j.conf`; không mở quyền plugin hoặc tắt strict validation chỉ để chữa lỗi.
- **Kiểm thử ngữ nghĩa và rollback** quan trọng như cú pháp: số node/relationship, dữ liệu, transaction, quyền, latency và cách phục hồi phải được xác nhận.

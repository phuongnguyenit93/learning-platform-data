# Gọi procedure, function và đọc chữ ký đầu vào–đầu ra trong Neo4j APOC

## 1. Bối cảnh và mục tiêu

Neo4j mô hình hóa dữ liệu dưới dạng **property graph**, gồm node, relationship và property; Cypher dùng `MATCH`, `WHERE`, `RETURN` cùng các biểu thức để truy vấn quan hệ hoặc đường đi. Khi cần thao tác bổ sung như xử lý danh sách, chuỗi, mở rộng đường đi có cấu hình hoặc nhập dữ liệu theo lô, hệ sinh thái Neo4j có **procedure** và **function**. Bộ phần mở rộng **APOC** (Awesome Procedures on Cypher) cung cấp nhiều tiện ích kiểu này.

Trong chương **APOC và phần mở rộng** của mô-đun `DATABASE_ENGINE_GRAPH_NEO4J`, bài học tập trung vào **cách gọi** và **cách đọc chữ ký đầu vào–đầu ra**, thay vì cố ghi nhớ danh sách hàng trăm tiện ích. Các kỹ năng áp dụng cho procedure/function tích hợp sẵn, APOC và các tiện ích do tổ chức tự triển khai.

Sau bài học, bạn có thể:

1. Phân biệt procedure với function và chọn đúng cú pháp `CALL ... YIELD` hay lời gọi trong biểu thức.
2. Dùng `SHOW PROCEDURES` và `SHOW FUNCTIONS` để xem tên, chữ ký, mô tả, chế độ truy cập và khả năng sử dụng.
3. Đọc tham số bắt buộc, tham số cấu hình, kiểu dữ liệu, cột đầu ra và xử lý `null`.
4. Kết hợp đầu ra procedure với `WITH`, `WHERE`, `RETURN` và các mẫu truy vấn node/relationship/path.
5. Chẩn đoán lỗi thiếu plugin, thiếu quyền, sai kiểu đối số, sai tên cột `YIELD` và khác biệt phiên bản.

> **Điều kiện tiên quyết:** Bạn biết node, relationship và cách chạy Cypher. Các ví dụ APOC chỉ chạy khi procedure/function tương ứng **đã được đăng ký và được cấp quyền** trong phiên bản Neo4j đang sử dụng. Không mặc định mọi cài đặt Neo4j hoặc mọi gói Aura đều có cùng tập tiện ích APOC.

## 2. Procedure và function khác nhau thế nào?

| Khía cạnh | Procedure | Function |
| --- | --- | --- |
| Vai trò | Thực hiện một thao tác, có thể tạo ra **các dòng kết quả** và, với procedure ghi, có thể sửa graph | Tính và trả về **một giá trị** trong một biểu thức |
| Cách gọi phổ biến | `CALL procedureName(arg1, arg2) YIELD column` | `functionName(arg1, arg2)` bên trong `RETURN`, `WITH`, `WHERE` hoặc `SET` khi phù hợp |
| Đầu vào | Danh sách đối số theo chữ ký | Danh sách đối số theo chữ ký |
| Đầu ra | Từ 0 đến nhiều dòng; mỗi dòng có các cột đầu ra khai báo trong chữ ký | Một giá trị với kiểu trả về, có thể là list/map/node/path tùy hàm |
| Phân quyền | Có thể cần quyền thực thi procedure và quyền đọc/ghi graph tương ứng | Có thể cần quyền thực thi function |
| Ví dụ tích hợp | `db.labels()` | `size()`, `coalesce()` |
| Ví dụ APOC | `apoc.path.expandConfig()` | `apoc.text.join()`, `apoc.coll.toSet()` |

Ví dụ dùng **function tích hợp**:

```cypher
RETURN
  size(['A', 'B', 'C']) AS itemCount,
  coalesce(null, 'unknown') AS fallback;
```

Ở đây `size(...)` và `coalesce(...)` xuất hiện **trong biểu thức** sau `RETURN`, lần lượt trả về một số và một chuỗi. Không viết `CALL size(...) YIELD ...`.

Ví dụ dùng **procedure tích hợp**:

```cypher
CALL db.labels() YIELD label
RETURN label
ORDER BY label;
```

`db.labels()` trả các dòng chứa cột `label`, là tên các nhãn node có trong cơ sở dữ liệu mà lệnh được phép xem. Trong cơ sở dữ liệu mới, có thể không có dòng nào. Ta dùng `YIELD` để lấy cột rồi tiếp tục xử lý như dữ liệu Cypher.

**Phân biệt thêm:** `CALL (x) { ... }` hoặc `CALL { ... }` cũng được gọi là *subquery*; đó **không phải** lời gọi một procedure có tên. Tương tự, `CALL { ... } IN TRANSACTIONS` là cú pháp chia giao dịch của Cypher, khác với procedure `apoc.periodic.iterate`.

## 3. Tìm chức năng hiện có thay vì đoán tên

APOC và các phần mở rộng được phát hành theo nhiều phiên bản. Một chức năng xuất hiện trong bài viết trên Internet có thể đã đổi chữ ký, bị thay thế hoặc không khả dụng ở hệ thống của bạn. Vì vậy, **cơ sở dữ liệu đang kết nối là nơi nên kiểm tra chữ ký trước tiên**.

### 3.1. Liệt kê procedure và chữ ký

```cypher
SHOW PROCEDURES
YIELD name, signature, description, mode
RETURN name, signature, description, mode
ORDER BY name
LIMIT 30;
```

Ý nghĩa các trường:

- `name`: tên để gọi, chẳng hạn `db.labels` hoặc `apoc.path.expandConfig`.
- `signature`: mô tả tham số đầu vào, kiểu đầu vào và cột đầu ra.
- `description`: công dụng, có thể cho biết hạn chế hoặc ghi chú của procedure.
- `mode`: chế độ hoạt động do hệ thống khai báo; thường phân biệt những procedure chỉ đọc và những procedure có thể ghi.

Chỉ xem các procedure APOC:

```cypher
SHOW PROCEDURES
YIELD name, signature, description, mode
WHERE name STARTS WITH 'apoc.'
RETURN name, signature, mode, description
ORDER BY name;
```

Muốn tìm đúng một procedure:

```cypher
SHOW PROCEDURES
YIELD name, signature, description
WHERE name = 'apoc.path.expandConfig'
RETURN name, signature, description;
```

Nếu truy vấn trả **0 dòng**, chưa đủ cơ sở khẳng định APOC không tồn tại: có thể chức năng đó chưa được cài, không được đăng ký trong phiên bản đang chạy hoặc tài khoản không được phép nhìn thấy/thực thi. Xem thêm phần xử lý lỗi.

### 3.2. Liệt kê function và chữ ký

```cypher
SHOW FUNCTIONS
YIELD name, signature, description
WHERE name STARTS WITH 'apoc.'
RETURN name, signature, description
ORDER BY name;
```

Tìm một function cụ thể:

```cypher
SHOW FUNCTIONS
YIELD name, signature, description
WHERE name = 'apoc.text.join'
RETURN name, signature, description;
```

`SHOW FUNCTIONS` có thể hiển thị cả hàm tích hợp và hàm mở rộng, tùy tùy chọn và quyền trên hệ thống. Không nên tìm `apoc.text.join` trong danh sách procedure: đó là **function**. Ngược lại, `apoc.path.expandConfig` là **procedure**, không phải hàm có thể đặt sau `RETURN` như một giá trị.

> **Đọc chữ ký theo đúng phiên bản:** Nếu kết quả `SHOW` khác ví dụ minh họa trong tài liệu, ưu tiên chữ ký mà hệ thống của bạn công bố, đồng thời đối chiếu tài liệu tương ứng phiên bản. Một số tên trường hay quyền truy cập trong `SHOW` có thể thay đổi theo phiên bản Neo4j.

## 4. Cách đọc chữ ký (signature)

Một chữ ký có thể được diễn đạt theo dạng khái niệm:

```text
procedureName(arg1 :: TYPE_A, arg2 :: TYPE_B)
    :: (output1 :: OUTPUT_A, output2 :: OUTPUT_B)

functionName(arg1 :: TYPE_A, arg2 :: TYPE_B)
    :: RETURN_TYPE
```

Các chữ ký trong khung trên là **sơ đồ hướng dẫn đọc**, không phải định nghĩa của một tiện ích Neo4j cụ thể.

| Thành phần | Cách hiểu |
| --- | --- |
| Tên trước `(` | Tên procedure/function cần gọi; phân biệt chính xác namespace |
| `arg1`, `arg2` | Đối số đầu vào theo thứ tự; cần truyền các biểu thức đúng kiểu |
| `:: TYPE` | Kiểu dữ liệu mà chữ ký yêu cầu hoặc trả về |
| `MAP` | Đối số dạng map, thường dùng cho cấu hình |
| `LIST<STRING>` | Danh sách các giá trị kiểu chuỗi |
| `NODE`, `RELATIONSHIP`, `PATH` | Kiểu dữ liệu property graph của Neo4j |
| `(output1 :: ..., output2 :: ...)` | Các cột đầu ra của procedure; chọn bằng `YIELD` |
| Kiểu trả về sau `::` của function | Một giá trị, nên đặt trong biểu thức như `RETURN functionName(...) AS alias` |

Đối số có thể có **giá trị mặc định** hoặc cú pháp biểu thị khả năng tùy chọn; cách thể hiện phụ thuộc chữ ký được công bố. Không suy ra rằng “đối số kiểu `MAP`” cho phép bỏ qua map: nếu đối số đó bắt buộc, vẫn cần truyền giá trị như `{}` hoặc map cấu hình hợp lệ theo tài liệu.

Ví dụ cách **diễn giải** chữ ký đơn giản (minh họa, không phải trích nguyên văn kết quả `SHOW`):

```text
demo.words(texts :: LIST<STRING>, separator :: STRING) :: STRING
```

Từ đó suy ra:

1. Cần truyền hai đối số đúng thứ tự: một danh sách chuỗi và một chuỗi phân cách.
2. `LIST<STRING>` không phải `STRING`; truyền `'A,B'` thay cho `['A','B']` có thể gây lỗi kiểu.
3. Đầu ra là một chuỗi; nếu đây là function, dùng trong biểu thức `RETURN` thay vì `YIELD`.

### 4.1. Chữ ký procedure khác lời gọi thực tế

Ví dụ minh họa một procedure trả cột `path`:

```text
... :: (path :: PATH)
```

Lời gọi có thể viết:

```cypher
MATCH (start:ApocDemoPerson {id: $startId})
CALL apoc.path.expandConfig(start, $config)
YIELD path
RETURN path;
```

Đoạn trên dùng `$startId` là **mã định danh** được truyền từ ứng dụng, `MATCH` để lấy node từ đồ thị, rồi truyền biến `start` kiểu `NODE` vào procedure. `$config` phải là map đúng định dạng và procedure cần được cấp quyền. Cách này tránh nhầm chuỗi ID với một đối số yêu cầu node.

Chữ ký cho biết **kiểu và tên cột**, còn mô tả/configuration cho biết ý nghĩa, phạm vi và mặc định của từng khóa cấu hình. Không thể hiểu đầy đủ `relationshipFilter` hoặc `uniqueness` chỉ bằng việc nhìn thấy kiểu `MAP`.

### 4.2. Null, list, map và kiểu property graph

Cypher phân biệt `null` với danh sách rỗng `[]` và map rỗng `{}`. Một procedure/function có thể cho phép, từ chối hoặc diễn giải những trường hợp ấy khác nhau.

- `null`: giá trị không tồn tại hoặc chưa xác định; kiểm tra quy tắc riêng của hàm.
- `[]`: danh sách có 0 phần tử, không phải giá trị thiếu.
- `{}`: map có 0 khóa; **không tự động** có các khóa cấu hình bắt buộc.
- `NODE`: một node của đồ thị, không phải chuỗi ID của node.
- `PATH`: đường đi gồm node và relationship, có thể xử lý tiếp bằng `nodes(p)`, `relationships(p)`, `length(p)`.

Ví dụ:

```cypher
WITH ['A', 'B'] AS labels
RETURN size(labels) AS numberOfItems,
       labels[0] AS firstItem;
```

Ở đây một biểu thức dùng list, không phải hai đối số rời. Với procedure cần hai đối số, phải truyền `procedureName(arg1, arg2)` theo chữ ký; truyền một list chứa hai phần tử sẽ **không tương đương**, trừ khi chữ ký nói rõ đầu vào là list.

## 5. Gọi APOC function trong biểu thức Cypher

APOC cung cấp các tiện ích xử lý chuỗi, danh sách, map, chuyển đổi và nhiều nhóm chức năng khác. Ví dụ **APOC Core** thường gặp là `apoc.text.join`:

```cypher
RETURN apoc.text.join(
  ['Neo4j', 'Cypher', 'APOC'],
  ' / '
) AS joinedText;
```

Khi function có mặt, kết quả:

```text
joinedText
-------------------
Neo4j / Cypher / APOC
```

Từ lời gọi có thể thấy đối số thứ nhất là **danh sách chuỗi**, đối số thứ hai là **chuỗi phân cách**, đầu ra được đặt bí danh bằng `AS joinedText`. Không cần `CALL` và không có `YIELD`.

Một ví dụ function khác, để loại giá trị trùng theo ý nghĩa của tiện ích:

```cypher
RETURN apoc.coll.toSet(['graph', 'cypher', 'graph']) AS terms;
```

Danh sách kết quả chứa các giá trị phân biệt `graph` và `cypher`. **Không phụ thuộc vào thứ tự hiển thị** của một phép xử lý có ý nghĩa như tập hợp nếu nghiệp vụ chưa quy định thứ tự; nếu cần thứ tự xác định, hãy thiết kế bước sắp xếp riêng.

### 5.1. Dùng function với dữ liệu từ node

Giả sử các node `:Article` có thuộc tính list `tags`:

```cypher
MATCH (a:Article)
WHERE a.tags IS NOT NULL
RETURN a.id AS articleId,
       apoc.text.join(a.tags, ', ') AS tagText
ORDER BY articleId
LIMIT 20;
```

Đoạn này giả định `a.tags` là **list chuỗi**; nếu người ghi dữ liệu đã lưu giá trị khác kiểu, cần chuẩn hóa trước. Truy vấn chỉ đọc: function trả giá trị trong từng dòng; nó không tự tạo relationship hay chỉnh sửa property.

### 5.2. Khi không cần APOC

Không phải tác vụ nào cũng nên phụ thuộc phần mở rộng. Với các thao tác cơ bản như `size`, `coalesce`, `toString`, `collect` hoặc `range`, Cypher đã có sẵn function tương ứng. Lựa chọn function tích hợp khi đáp ứng được nhu cầu thường giúp giảm ràng buộc plugin, quyền triển khai và khó khăn khi nâng cấp.

Trước khi dùng một APOC function trong ứng dụng:

1. Kiểm tra nó có trong `SHOW FUNCTIONS`.
2. Đọc chữ ký và thử với dữ liệu nhỏ, cả trường hợp `null`, list rỗng và sai kiểu.
3. Đánh giá chi phí nếu gọi trên hàng triệu dòng; function đặt trong `RETURN` có thể chạy cho **mỗi dòng đầu vào**.

## 6. Gọi APOC procedure, lấy cột bằng YIELD và dùng tiếp trong Cypher

Một ví dụ rõ ràng là `apoc.path.expandConfig`: procedure mở rộng đường đi từ một node xuất phát theo các lựa chọn trong map cấu hình.

### 6.1. Dữ liệu ví dụ

Chạy trong cơ sở dữ liệu thực hành:

```cypher
CREATE CONSTRAINT apoc_demo_person_id IF NOT EXISTS
FOR (p:ApocDemoPerson) REQUIRE p.id IS UNIQUE;
```

```cypher
MERGE (a:ApocDemoPerson {id: 'APOC-U1'})
MERGE (b:ApocDemoPerson {id: 'APOC-U2'})
MERGE (c:ApocDemoPerson {id: 'APOC-U3'})
MERGE (a)-[:APOC_DEMO_FOLLOWS]->(b)
MERGE (b)-[:APOC_DEMO_FOLLOWS]->(c);
```

Các node demo có ID riêng để ít ảnh hưởng đến dữ liệu thực hành khác. `MERGE` giúp giảm khả năng tạo trùng khi chạy lại trên đúng mẫu, nhưng trong môi trường dùng chung vẫn phải kiểm tra những quan hệ có sẵn. Constraint là thao tác ghi schema; hãy chạy riêng trước phần nhập dữ liệu.

### 6.2. Xem chữ ký trước khi gọi

```cypher
SHOW PROCEDURES
YIELD name, signature, description, mode
WHERE name = 'apoc.path.expandConfig'
RETURN name, signature, description, mode;
```

Nếu procedure có mặt, chữ ký cho biết các đối số đầu vào và cột trả về `path`. Phần cấu hình `config` thường là `MAP`, với các khóa như `relationshipFilter`, `minLevel`, `maxLevel` và `uniqueness`. Ý nghĩa từng khóa phải đọc ở tài liệu cụ thể, không chỉ qua tên kiểu.

### 6.3. Gọi procedure

```cypher
MATCH (start:ApocDemoPerson {id: 'APOC-U1'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  minLevel: 1,
  maxLevel: 2,
  uniqueness: 'NODE_PATH'
})
YIELD path
RETURN [n IN nodes(path) | n.id] AS nodeIds,
       length(path) AS hops
ORDER BY hops;
```

Với đúng ba node và hai relationship demo, kết quả mô tả hai đường:

| `nodeIds` | `hops` |
| --- | ---: |
| `['APOC-U1', 'APOC-U2']` | 1 |
| `['APOC-U1', 'APOC-U2', 'APOC-U3']` | 2 |

Giải thích theo ranh giới dữ liệu:

1. `MATCH` tìm **node đầu**; biến `start` có kiểu `NODE`.
2. `CALL apoc.path.expandConfig(start, {...})` truyền node và map cấu hình theo thứ tự đầu vào.
3. `YIELD path` lấy **cột đầu ra** có tên `path`, kiểu `PATH`.
4. `nodes(path)` biến đường đi thành list node để trích `id`; `length(path)` đo số relationship trên đường đi.
5. Mệnh đề `RETURN` đặt bí danh các kết quả, `ORDER BY` sắp xếp theo số bước.

Nếu có thêm những relationship cùng loại xuất phát từ các node demo, query có thể trả **nhiều đường hơn**. Không suy ra rằng `maxLevel: 2` luôn tạo đúng hai dòng; đó chỉ là kết quả của đồ thị demo đang xét.

### 6.4. YIELD có thể đổi tên cột

```cypher
MATCH (start:ApocDemoPerson {id: 'APOC-U1'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  minLevel: 1,
  maxLevel: 2
})
YIELD path AS p
WITH p
WHERE length(p) = 2
RETURN [n IN nodes(p) | n.id] AS route;
```

`YIELD path AS p` cho phép sử dụng `p` ở các clause sau. `WITH p` giữ biến đang cần; `WHERE length(p) = 2` lọc đường đi đúng hai bước. Khi đã đổi tên cột, không tiếp tục dùng tên `path` ở phía sau nếu không còn trong scope.

**Không viết** `YIELD nodeIds` chỉ vì muốn kết quả có tên đó: `nodeIds` không phải cột procedure công bố. Hãy `YIELD path` rồi tính `[n IN nodes(path) | n.id] AS nodeIds`.

## 7. Procedure ghi dữ liệu: cách đọc chữ ký và quản lý rủi ro

Một số procedure APOC có thể ghi dữ liệu, chạy nhiều giao dịch hoặc truy cập tài nguyên ngoài. Trước khi gọi:

- Kiểm tra trường `mode` và mô tả của `SHOW PROCEDURES`.
- Xác định chính xác những node, relationship, property hoặc nguồn bên ngoài sẽ bị tác động.
- Kiểm tra quyền thực thi, quyền graph và cấu hình plugin; không suy ra một procedure là an toàn chỉ vì tên bắt đầu bằng `apoc.`.
- Với tác vụ nhập hoặc cập nhật khối lượng lớn, lập kế hoạch idempotency, retry, rollback theo batch và giám sát lỗi.

Ví dụ `apoc.periodic.iterate` thường dùng hai chuỗi Cypher và một map cấu hình để xử lý dữ liệu theo từng batch. **Chỉ chạy ví dụ sau trong cơ sở dữ liệu thực hành**, sau khi xác nhận procedure có mặt và có quyền ghi:

```cypher
SHOW PROCEDURES
YIELD name, signature, mode
WHERE name = 'apoc.periodic.iterate'
RETURN name, signature, mode;
```

Sau khi đã xác nhận môi trường:

```cypher
CALL apoc.periodic.iterate(
  'MATCH (p:ApocDemoPerson) RETURN p',
  'SET p.checked = true',
  {batchSize: 2, parallel: false}
)
YIELD batches, total, failedBatches
RETURN batches, total, failedBatches;
```

Trong ví dụ:

- Đối số đầu là **chuỗi truy vấn tìm dòng**, không phải kết quả `MATCH` đã được thực thi ở phía ngoài.
- Đối số thứ hai là **chuỗi thao tác ghi** trên các dòng đó.
- Đối số thứ ba là **map cấu hình**; `batchSize` giới hạn số dòng mỗi batch, `parallel: false` không yêu cầu chạy song song.
- `YIELD batches, total, failedBatches` lấy các cột thống kê kết quả mà procedure công bố; tên và các cột còn lại phải kiểm tra chữ ký phiên bản thực tế.

Khi có đúng ba node `ApocDemoPerson`, có thể thấy `total = 3` và `batches = 2` nếu hoàn tất bình thường. Dù một lần gọi ở ngoài, các batch bên trong có thể có **ranh giới giao dịch riêng**. Không dùng số batch hoàn thành làm bằng chứng tất cả node/relationship nghiệp vụ đã đúng; cần kiểm tra dữ liệu sau khi chạy.

> Trong Neo4j, `CALL { ... } IN TRANSACTIONS` là **cú pháp Cypher khác** để xử lý giao dịch theo lô. Không coi nó đồng nghĩa với `apoc.periodic.iterate`; mỗi cách có quy tắc về transaction, đầu vào, khả năng xử lý lỗi và quyền riêng.

## 8. Khi một lời gọi tạo nhiều dòng

Giả sử `MATCH` khớp 10 node nguồn. Mỗi node lại sinh 1–5 đường từ `apoc.path.expandConfig`. Kết quả có thể nhiều hơn 10 dòng:

```cypher
MATCH (s:ApocDemoPerson)
CALL apoc.path.expandConfig(s, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  minLevel: 1,
  maxLevel: 2
})
YIELD path
RETURN s.id AS sourceId, length(path) AS hops;
```

Không được mặc định `CALL` trả **đúng một dòng** cho mỗi node `s`. Nếu procedure trả 0 dòng, node đầu vào ấy có thể **không xuất hiện** trong kết quả sau `CALL`; nếu trả nhiều dòng, node đó xuất hiện nhiều lần.

Điều này quan trọng khi:

- Dùng `LIMIT 20`: lệnh giới hạn **20 dòng**, không nhất thiết là 20 node nguồn khác nhau.
- Dùng `count(*)`: đếm số dòng sau procedure, không phải số node đầu vào.
- Dùng `SET` ở bước sau: cần xác định thao tác có bị gọi lặp vì nhiều đường đi hay không.
- Dùng `collect()`: cân nhắc có cần `DISTINCT` để tránh trùng node/path theo nghiệp vụ.

Ví dụ đếm số đường với các node có ít nhất một đường khớp:

```cypher
MATCH (s:ApocDemoPerson)
CALL apoc.path.expandConfig(s, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  minLevel: 1,
  maxLevel: 2
})
YIELD path
RETURN s.id AS sourceId, count(path) AS matchedPaths
ORDER BY sourceId;
```

Chỉ những `s` có ít nhất một đường hợp lệ được đưa vào phép nhóm sau `CALL` trong truy vấn trên. Nếu muốn giữ cả node không có đường, phải thiết kế riêng phép gọi tùy chọn hoặc phép tổng hợp trên tập node nguồn theo khả năng hỗ trợ của phiên bản, thay vì giả định mọi procedure tự sinh ra dòng `null`.

## 9. Quyền, plugin và khả năng tương thích

### 9.1. Phân biệt Neo4j tích hợp và APOC

`db.labels()` là procedure được Neo4j cung cấp sẵn. Các tên `apoc.*` thuộc tập tiện ích APOC cần được cài đặt/kích hoạt theo hình thức triển khai tương ứng:

- **Neo4j Desktop/Docker/self-managed:** kiểm tra phiên bản Neo4j, gói APOC Core/Extended thích hợp, vị trí plugin và cấu hình quyền. Hướng dẫn cài đặt thay đổi theo bản phát hành.
- **Dịch vụ quản lý như Neo4j Aura:** có thể chỉ cung cấp một tập APOC nhất định; không mặc định có thể tự chép plugin tùy ý lên máy chủ.
- **Cụm nhiều máy chủ:** bảo đảm những máy được phép thực thi truy vấn có cấu hình và khả năng cung cấp procedure nhất quán.

Không bật cấu hình **unrestricted** rộng rãi chỉ để một ví dụ chạy được. Các procedure có quyền truy cập file, mạng hoặc hệ điều hành cần được quản trị theo nguyên tắc quyền tối thiểu.

### 9.2. Ba bước kiểm tra một tiện ích

```cypher
// 1. Tên procedure có trong danh mục không?
SHOW PROCEDURES
YIELD name, signature
WHERE name = 'apoc.path.expandConfig'
RETURN name, signature;
```

```cypher
// 2. Tên function có trong danh mục không?
SHOW FUNCTIONS
YIELD name, signature
WHERE name = 'apoc.text.join'
RETURN name, signature;
```

```cypher
// 3. Nếu function có mặt, thử đầu vào nhỏ để kiểm tra quyền và kiểu.
RETURN apoc.text.join(['A', 'B'], '-') AS sample;
```

Nếu một bước không đạt, cần phân biệt lỗi **không tìm thấy tên**, **không có quyền** và **kiểu đối số sai**. Không nên chữa bằng cách đổi sang một procedure khác “gần giống” chỉ vì tên có cùng tiền tố.

### 9.3. Khác biệt khi nâng cấp phiên bản

APOC và Cypher phát triển theo phiên bản; một số tiện ích có thể được đổi tên, thay thế bởi cú pháp Cypher chuẩn hoặc bị đánh dấu không nên sử dụng cho ứng dụng mới. Đặc biệt, môi trường sử dụng **Cypher 25** có thể có khác biệt về mức hỗ trợ cho một số procedure cũ.

Khi nâng cấp:

1. Lưu danh sách procedure/function mà ứng dụng đang gọi.
2. Kiểm tra lại `SHOW PROCEDURES` / `SHOW FUNCTIONS` và mô tả/chữ ký sau nâng cấp.
3. Đối chiếu tài liệu APOC và Neo4j đúng phiên bản, nhất là default, kiểu đối số, output và quyền.
4. Chạy kiểm thử với dữ liệu nhỏ, trường hợp `null`, list/map rỗng và kết quả nhiều dòng.
5. Dùng `EXPLAIN`/`PROFILE` phù hợp để xem tác động kế hoạch truy vấn; với procedure ghi, không dùng `PROFILE` trên dữ liệu thật chỉ để thử vì lệnh có thể thực thi thay đổi.

## 10. Lỗi thường gặp và hướng xử lý

| Biểu hiện | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `Unknown function 'apoc.text.join'` | APOC chưa có/không đăng ký, sai tên hoặc không thể truy cập | Kiểm tra `SHOW FUNCTIONS`, phiên bản/plugin và quyền |
| `There is no procedure with the name ...` | Gọi sai tên hoặc procedure không được cung cấp | Kiểm tra `SHOW PROCEDURES`, gói và phiên bản |
| Truy vấn `CALL apoc.text.join(...)` lỗi | Đã dùng `CALL` cho function | Đưa lời gọi vào `RETURN`/`WITH` |
| `RETURN apoc.path.expandConfig(...)` lỗi | Đã dùng procedure như function | Dùng `CALL ... YIELD path` |
| `YIELD nodeIds` lỗi | Đó là bí danh mong muốn, không phải cột output | `YIELD path`, rồi tính `nodeIds` trong `RETURN` |
| Sai kiểu đối số | Ví dụ truyền `STRING` trong khi cần `LIST<STRING>` | Đọc `signature`, kiểm tra giá trị và kiểu |
| `YIELD` gây mất biến ở bước sau | Dùng `WITH` không truyền biến cần thiết | Kiểm tra scope, `WITH` các biến cần dùng |
| Có nhiều dòng hơn node | Procedure trả nhiều path/dòng | Phân biệt đếm dòng với đếm thực thể; gom nhóm khi cần |
| Không có dòng kết quả | Không có path phù hợp hoặc dữ liệu/điều kiện sai | Kiểm tra node đầu, config filter và mức mở rộng |
| Không đủ quyền thực thi | Vai trò tài khoản thiếu quyền hoặc cấu hình chặn | Nhờ quản trị cấp quyền tối thiểu, không bỏ qua bảo mật |
| Cú pháp hợp lệ ở máy khác nhưng lỗi tại đây | Phiên bản/gói APOC khác nhau | Kiểm tra chữ ký trên chính database đích |
| Procedure ghi thất bại một phần | Lệnh chia nhiều giao dịch hoặc ghi ngoài DB | Xem báo cáo lỗi, checkpoint, idempotency và đối soát |

## 11. Tích hợp Java Driver và Spring Data Neo4j

### 11.1. Java Driver: truyền tham số cho function

Ví dụ Java 17+, Neo4j Java Driver 5.x, giả định ứng dụng đã khởi tạo đối tượng `Driver`:

```java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class ApocTextExample {
    public static String joinNames(
        Driver driver, List<String> names, String separator
    ) {
        String cypher = """
            RETURN apoc.text.join($names, $separator) AS joined
            """;

        try (Session session =
                 driver.session(SessionConfig.forDatabase("neo4j"))) {
            return session.executeRead(tx ->
                tx.run(cypher, Map.of(
                    "names", names,
                    "separator", separator
                )).single().get("joined").asString()
            );
        }
    }
}
```

Code chỉ phù hợp nếu function có trong danh mục. `Map.of` không cho phép giá trị `null`; kiểm tra đầu vào hoặc xây map theo chính sách null của ứng dụng. Truyền parameter giúp tránh ghép chuỗi dữ liệu người dùng vào Cypher và cho phép tái sử dụng truy vấn.

### 11.2. Java Driver: đọc kết quả từ procedure

```java
String cypher = """
    MATCH (start:ApocDemoPerson {id: $startId})
    CALL apoc.path.expandConfig(start, {
      relationshipFilter: 'APOC_DEMO_FOLLOWS>',
      minLevel: 1,
      maxLevel: $maxHops
    })
    YIELD path
    RETURN length(path) AS hops
    ORDER BY hops
    """;

try (var session = driver.session()) {
    var rows = session.executeRead(tx ->
        tx.run(cypher, Map.of(
            "startId", "APOC-U1",
            "maxHops", 2
        )).list()
    );
    for (var record : rows) {
        System.out.println(record.get("hops").asLong());
    }
}
```

Ví dụ thứ hai là **đoạn mã trong một phương thức** đã có `Driver driver`; khác với phương thức đầy đủ ở trên. Nếu cần chuyển `PATH` về DTO, có thể truy cập giá trị `path` từ `Record` và ánh xạ node/relationship theo kiểu driver cung cấp. Đừng giả định một lần `CALL` chỉ trả một record.

### 11.3. Spring Data Neo4j

Với Spring Data Neo4j, có thể gọi Cypher dùng APOC thông qua `@Query` hoặc `Neo4jClient` khi tiện ích đã được cài trên Neo4j server và quyền cho phép. Cần xác nhận rằng cột `YIELD` / `RETURN` khớp với kiểu DTO hoặc entity projection mong đợi.

- Với function trả một giá trị scalar, ánh xạ thành `String`, `Long` hoặc kiểu phù hợp.
- Với procedure trả nhiều dòng hoặc nhiều path, dùng DTO/projection phù hợp thay vì giả định chỉ một node.
- Với procedure ghi, xác định ranh giới transaction thực tế của SDN và procedure. Đặc biệt, không đặt một tiện ích tự chia transaction vào transaction bao ngoài nếu phiên bản/tính năng không hỗ trợ.

## 12. Bài tập thực hành

### Bài 1: Nhận diện procedure và function

Phân loại các lời gọi sau và chọn cú pháp đúng: `db.labels()`, `size([1,2,3])`, `apoc.text.join(['x','y'], '-')` và `apoc.path.expandConfig(start, config)`.

**Gợi ý:** `db.labels` và `apoc.path.expandConfig` là procedure dùng `CALL`; hai tiện ích còn lại là function dùng trong biểu thức.

### Bài 2: Tự đọc chữ ký thay vì đoán

Hãy tra cứu chữ ký của `apoc.path.expandConfig` và `apoc.text.join` trên hệ thống thực hành, ghi lại:

1. Kiểu đầu vào và thứ tự đối số.
2. Có tham số `MAP` hay không và những khóa cấu hình cần tra tài liệu.
3. Kiểu đầu ra/cột đầu ra.
4. Chức năng có khả dụng với quyền hiện tại không?

```cypher
SHOW PROCEDURES
YIELD name, signature
WHERE name = 'apoc.path.expandConfig'
RETURN name, signature;
```

```cypher
SHOW FUNCTIONS
YIELD name, signature
WHERE name = 'apoc.text.join'
RETURN name, signature;
```

### Bài 3: Sửa lỗi YIELD

Truy vấn sau sai ở đâu?

```cypher
MATCH (s:ApocDemoPerson {id: 'APOC-U1'})
CALL apoc.path.expandConfig(s, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  maxLevel: 2
})
YIELD nodeIds
RETURN nodeIds;
```

**Gợi ý sửa:** procedure trả cột `path`, không trả cột `nodeIds`:

```cypher
MATCH (s:ApocDemoPerson {id: 'APOC-U1'})
CALL apoc.path.expandConfig(s, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  minLevel: 1,
  maxLevel: 2
})
YIELD path
RETURN [n IN nodes(path) | n.id] AS nodeIds;
```

### Bài 4: Phân biệt dòng và node

Với đồ thị demo, `apoc.path.expandConfig` từ `APOC-U1` trả hai path dài 1 và 2 bước. `count(*)` sau `CALL` là bao nhiêu? Vì sao không được kết luận có hai node xuất phát?

**Đáp án:** có hai **dòng kết quả** tương ứng hai path, nhưng chỉ có **một node xuất phát** là `APOC-U1`. Nếu graph có nhánh khác, số dòng có thể lớn hơn nữa.

### Bài 5: Quyết định cách triển khai

Ứng dụng cần ghép các chuỗi tag, mở rộng quan hệ theo bộ lọc và nhập nhiều triệu relationship. Nêu phương án có thể sử dụng cho từng yêu cầu, đồng thời trả lời: liệu cứ dùng APOC sẽ nhanh hơn Cypher chuẩn?

**Gợi ý:** ghép chuỗi có thể dùng `apoc.text.join` nếu có mặt; mở rộng đường đi có cấu hình cân nhắc `apoc.path.expandConfig`; nhập lớn cần nghiên cứu `LOAD CSV`, `UNWIND`, `CALL { ... } IN TRANSACTIONS` hoặc procedure batch tùy môi trường. Không có bảo đảm APOC luôn nhanh hơn: cần `EXPLAIN`, `PROFILE`, benchmark và kiểm tra quyền/khả năng bảo trì.

## 13. Checklist trước khi đưa APOC vào ứng dụng

- [ ] Xác định rõ tên đang gọi là **procedure** hay **function**.
- [ ] Chạy `SHOW PROCEDURES` hoặc `SHOW FUNCTIONS` trên đúng cơ sở dữ liệu.
- [ ] Đọc chữ ký, đối số bắt buộc/tùy chọn, kiểu trả về và các cột `YIELD`.
- [ ] Kiểm tra cấu hình map, `null`, list rỗng và giá trị mặc định.
- [ ] Đặt `YIELD` và `AS` đúng scope; không nhầm cột procedure với bí danh mong muốn.
- [ ] Hiểu số dòng được tạo từ procedure trước khi `LIMIT`, `count`, `collect` hoặc ghi dữ liệu.
- [ ] Kiểm tra plugin được đăng ký, quyền thực thi và tương thích Neo4j/APOC.
- [ ] Với procedure ghi, xác định transaction, retry, quyền, idempotency và đối soát.
- [ ] Với Java Driver/SDN, dùng parameter, mapping đúng kiểu và quản lý tài nguyên.
- [ ] Kiểm tra có thể thay bằng Cypher chuẩn để giảm phụ thuộc mở rộng hay không.

## Kết luận

Khi làm việc với APOC trong Neo4j, điều quan trọng không phải là nhớ tất cả tên tiện ích mà là biết **tra chữ ký** và **gọi đúng loại**. Function trả một giá trị, dùng trong biểu thức; procedure được gọi bằng `CALL`, tạo các cột và có thể sinh nhiều dòng, nên phải đọc `YIELD` cùng kiểu đầu ra. `SHOW PROCEDURES` và `SHOW FUNCTIONS` giúp xác minh tính khả dụng trên hệ thống đang chạy. Kết hợp chúng với hiểu biết về property graph, quyền, phiên bản, transaction và kế hoạch truy vấn sẽ giúp dùng APOC có kiểm soát, đúng dữ liệu và dễ bảo trì.

### Tài liệu tham khảo

- [Neo4j APOC — Documentation](https://neo4j.com/docs/apoc/current/)
- [Neo4j Cypher Manual — CALL procedure](https://neo4j.com/docs/cypher-manual/current/clauses/call/)
- [Neo4j Cypher Manual — SHOW PROCEDURES](https://neo4j.com/docs/cypher-manual/current/clauses/listing-procedures/)
- [Neo4j Cypher Manual — SHOW FUNCTIONS](https://neo4j.com/docs/cypher-manual/current/clauses/listing-functions/)
- [Neo4j Java Driver Manual](https://neo4j.com/docs/java-manual/current/)

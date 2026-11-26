# Mở rộng đường đi bằng APOC với điều kiện giới hạn rõ ràng trong Neo4j

Trong property graph Neo4j, một node có thể nối đến hàng chục, hàng nghìn hoặc hàng triệu node khác. Khi cần trả lời “Từ người A có thể đi tới ai qua tối đa ba quan hệ?”, “Có những tuyến nào dẫn tới đích B?” hay “Chỉ duyệt những quan hệ được phép và bỏ qua các node bị chặn”, chỉ viết một mẫu đường đi dài là chưa đủ. Truy vấn phải xác định **giới hạn độ sâu, hướng relationship, điều kiện dừng, quy tắc chống lặp và lượng kết quả tối đa**.

APOC (Awesome Procedures on Cypher) cung cấp các procedure bổ sung cho Neo4j. Trong chương **APOC và phần mở rộng** của module `DATABASE_ENGINE_GRAPH_NEO4J`, bài này tập trung vào `apoc.path.expandConfig()` — một công cụ duyệt đường đi với cấu hình linh hoạt. Nội dung liên quan trực tiếp đến node, relationship, Cypher, truy vấn đường đi, tối ưu và cách đưa kết quả về ứng dụng Java Driver hoặc Spring Data Neo4j.

Mục tiêu sau bài học: tự viết được một phép duyệt **có giới hạn cụ thể**, giải thích được mỗi điều kiện làm thay đổi tập đường đi ra sao, đồng thời đánh giá được rủi ro khi duyệt một graph có nhiều nhánh hoặc chu trình.

## 1. Vì sao cần giới hạn khi mở rộng đường đi?

Giả sử mỗi node có trung bình `b` quan hệ có thể đi theo. Nếu không có sự loại trừ và mỗi bước duyệt mở rộng độc lập, số đường đi tiềm năng tới độ sâu `d` tăng xấp xỉ:

\[
b + b^2 + \cdots + b^d
\]

Ví dụ, với `b = 10` và `d = 4`, mô hình nhánh đơn giản có thể tạo tới `10 + 100 + 1000 + 10000 = 11110` đường đi. Đây chỉ là minh họa; graph thực tế có node được dùng chung, chu trình, nhiều relationship giữa cùng hai node và các quy tắc uniqueness nên số đường đi thực có thể khác.

Khi chỉ cần kiểm tra một đích có thể đến được hoặc lấy vài đường đi ngắn, trả toàn bộ những đường đi này thường gây lãng phí:

- **CPU và phép duyệt:** phải xét nhiều relationship cho từng bước.
- **Bộ nhớ:** những đường đi trung gian hoặc kết quả có thể cần được giữ, đặc biệt khi thêm `collect(path)`.
- **Kích thước trả về:** `path` chứa danh sách node và relationship trên đường, lớn hơn nhiều so với chỉ trả ID hoặc số bước.
- **Độ trễ:** một graph rộng ở 2 bước đầu có thể khiến tầng thứ 3 tăng đột biến.

Vì vậy, **`maxLevel`, `relationshipFilter`, `labelFilter`, `uniqueness`, `bfs` và `limit`** phải được cân nhắc cùng nhau. Chỉ dùng `LIMIT` ở cuối Cypher không thay thế tất cả các giới hạn duyệt.

## 2. APOC và điều kiện chạy procedure

APOC gồm những procedure/function mở rộng Cypher. `apoc.path.expandConfig` thuộc nhóm chức năng duyệt graph của APOC, thường có trong **APOC Core** ở các bản Neo4j được hỗ trợ. Khả năng gọi procedure còn phụ thuộc **phiên bản APOC tương thích Neo4j**, cách cài đặt, cấu hình cho phép procedure và quyền của tài khoản.

Có thể kiểm tra procedure trên database đang kết nối:

```cypher
SHOW PROCEDURES
YIELD name
WHERE name = 'apoc.path.expandConfig'
RETURN name;
```

Nếu không có hàng kết quả, cần kiểm tra cài đặt APOC, cấu hình và quyền truy cập. Không nên giả định mọi Neo4j Aura hoặc deployment tự quản lý đều có cùng tập procedure được bật.

Cấu trúc lời gọi cơ bản:

```cypher
MATCH (start:SomeLabel {id: $startId})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'RELATED_TO>',
  minLevel: 1,
  maxLevel: 3,
  bfs: true,
  uniqueness: 'NODE_PATH',
  limit: 100
})
YIELD path
RETURN path;
```

`start` là node bắt đầu; tham số thứ hai là **map cấu hình**. Procedure có thể trả nhiều hàng, mỗi hàng chứa một `path`. Đây là *thao tác duyệt*, nên cần phân biệt đường đi được trả về với tập **node đích duy nhất**.

> **Ràng buộc vận hành:** một truy vấn chỉ là ví dụ học tập nếu chưa kiểm tra dữ liệu và môi trường chạy. Với graph lớn, đặt giới hạn độ sâu nhỏ và kiểm tra bằng `EXPLAIN`/`PROFILE` trong môi trường phù hợp trước khi mở rộng phạm vi.

## 3. Dựng graph nhỏ có nhiều nhánh và chu trình

Chạy lệnh `CREATE` sau **một lần trên database thử nghiệm**. Các label và relationship type có tiền tố `ApocDemo` để tránh nhầm với mô hình nghiệp vụ đang vận hành.

```cypher
CREATE
  (an:ApocDemoPerson {personId: 'P01', name: 'An'}),
  (binh:ApocDemoPerson:ApocDemoTrusted {personId: 'P02', name: 'Bình'}),
  (chi:ApocDemoPerson:ApocDemoTrusted {personId: 'P03', name: 'Chi'}),
  (dung:ApocDemoPerson:ApocDemoBlocked {personId: 'P04', name: 'Dũng'}),
  (em:ApocDemoPerson:ApocDemoTrusted {personId: 'P05', name: 'Em'}),
  (giang:ApocDemoPerson:ApocDemoTrusted:ApocDemoTarget
         {personId: 'P06', name: 'Giang'}),
  (han:ApocDemoPerson:ApocDemoTrusted {personId: 'P07', name: 'Hân'}),
  (an)-[:APOC_DEMO_FOLLOWS]->(binh),
  (an)-[:APOC_DEMO_FOLLOWS]->(chi),
  (binh)-[:APOC_DEMO_FOLLOWS]->(dung),
  (binh)-[:APOC_DEMO_FOLLOWS]->(em),
  (chi)-[:APOC_DEMO_FOLLOWS]->(em),
  (chi)-[:APOC_DEMO_FOLLOWS]->(han),
  (dung)-[:APOC_DEMO_FOLLOWS]->(giang),
  (em)-[:APOC_DEMO_FOLLOWS]->(giang),
  (han)-[:APOC_DEMO_FOLLOWS]->(giang),
  (giang)-[:APOC_DEMO_FOLLOWS]->(an),
  (binh)-[:APOC_DEMO_COLLABORATES_WITH]->(chi);
```

Phác họa các quan hệ `APOC_DEMO_FOLLOWS`:

```text
An (P01) ──► Bình (P02) ──► Dũng (P04, Blocked) ──► Giang (P06, Target)
     │             └─────► Em (P05) ─────────────► Giang
     └─────► Chi (P03) ──► Em (P05)
                   └─────► Hân (P07) ────────────► Giang

Giang (P06) ──► An (P01)      [cạnh tạo chu trình]
Bình (P02) ──► Chi (P03)      [COLLABORATES_WITH, type khác]
```

Trong đó:

- `An` là điểm bắt đầu (`P01`); `Giang` là đích (`P06`).
- `Dũng` có label `ApocDemoBlocked` nên sẽ được bỏ qua trong ví dụ lọc node.
- `Giang → An` là cạnh tạo chu trình; nếu duyệt quá sâu, cùng một node có thể xuất hiện trở lại trên đường.
- Quan hệ `APOC_DEMO_COLLABORATES_WITH` được thêm để thấy tác dụng của việc chọn đúng relationship type.

Có thể kiểm tra trực tiếp graph mẫu:

```cypher
MATCH (n:ApocDemoPerson)
RETURN n.personId AS id, n.name AS name, labels(n) AS labels
ORDER BY id;
```

Kỳ vọng có 7 node; `CREATE` lặp lại sẽ tạo dữ liệu trùng và làm các số đếm trong bài không còn đúng.

## 4. Mở rộng đầu tiên: độ sâu và hướng quan hệ

Lấy các đường đi từ `An` qua tối thiểu một và tối đa hai quan hệ `FOLLOWS` theo **chiều đi ra**:

```cypher
MATCH (start:ApocDemoPerson {personId: 'P01'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  minLevel: 1,
  maxLevel: 2,
  bfs: true,
  uniqueness: 'RELATIONSHIP_PATH'
})
YIELD path
RETURN length(path) AS hops,
       [n IN nodes(path) | n.personId] AS route
ORDER BY hops, route;
```

Với bộ dữ liệu gốc, có:

| Độ sâu | Đường đi theo `personId` | Số đường |
| --- | --- | ---: |
| 1 | `P01→P02`, `P01→P03` | 2 |
| 2 | `P01→P02→P04`, `P01→P02→P05`, `P01→P03→P05`, `P01→P03→P07` | 4 |
| **Tổng** | | **6** |

Hai đường `P01→P02→P05` và `P01→P03→P05` cùng kết thúc ở `Em` nhưng là **hai path khác nhau**. Đây là hành vi hợp lý khi hỏi “các tuyến”, nhưng không hợp lý nếu ứng dụng chỉ cần **một danh sách người có thể tới** mà không quan tâm tuyến.

### 4.1. Ý nghĩa minLevel và maxLevel

- `minLevel: 1`: chỉ trả đường có từ 1 relationship trở lên; không trả đường dài 0 gồm riêng node bắt đầu.
- `maxLevel: 2`: không đi xa quá 2 relationship từ start.
- `minLevel: 0`: có thể bao gồm đường đi độ dài 0, nếu bộ lọc và điều kiện đầu ra cho phép.
- Không đặt giới hạn độ sâu trên graph lớn là một quyết định có rủi ro. **Luôn chọn `maxLevel` cụ thể** cho các endpoint phục vụ người dùng, trừ khi đã có cơ chế kiểm soát công việc khác và yêu cầu nghiệp vụ thật sự cần.

`maxLevel` giới hạn **số cạnh trên từng đường đi**; nó **không** giới hạn số lượng node/path ở mỗi tầng. Một node có hàng nghìn cạnh vẫn có thể tạo ra nhiều ứng viên ngay từ độ sâu 1.

### 4.2. Hướng và loại relationship

`relationshipFilter` điều khiển loại và chiều cạnh:

| Cấu hình | Ý nghĩa |
| --- | --- |
| `'APOC_DEMO_FOLLOWS>'` | Chỉ đi theo `FOLLOWS` chiều từ node hiện tại ra ngoài |
| `'<APOC_DEMO_FOLLOWS'` | Chỉ đi theo `FOLLOWS` chiều đi vào node hiện tại |
| `'APOC_DEMO_FOLLOWS'` | Cho phép cả hai chiều của type `FOLLOWS` |
| `'APOC_DEMO_FOLLOWS>|APOC_DEMO_COLLABORATES_WITH>'` | Cho phép một trong hai loại cạnh, cùng chiều đi ra |

Các đoạn phân cách bằng `|` tạo lựa chọn loại/hướng. Thêm loại relationship thường làm **tập ứng viên mở rộng**; chẳng hạn cạnh `Bình→Chi` thuộc type `COLLABORATES_WITH` chỉ được duyệt nếu filter cho phép type đó.

Trong bài toán hướng người theo dõi, bỏ dấu `>` có thể làm một đường đi **đảo chiều quan hệ theo dõi**. Kết quả vẫn có thể hợp lệ về cú pháp nhưng sai nghĩa nghiệp vụ.

## 5. Lọc node bằng labelFilter

Nếu không được đi qua node bị chặn, dùng `labelFilter` với tiền tố `-`:

```cypher
MATCH (start:ApocDemoPerson {personId: 'P01'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  labelFilter: '-ApocDemoBlocked',
  minLevel: 1,
  maxLevel: 3,
  bfs: true,
  uniqueness: 'RELATIONSHIP_PATH'
})
YIELD path
RETURN length(path) AS hops,
       [n IN nodes(path) | n.personId] AS route
ORDER BY hops, route;
```

Tập kết quả trên graph mẫu:

| Độ sâu | Các đích theo từng đường | Số path |
| --- | --- | ---: |
| 1 | Bình, Chi | 2 |
| 2 | Em qua Bình; Em qua Chi; Hân qua Chi | 3 |
| 3 | Giang qua Bình→Em; Giang qua Chi→Em; Giang qua Chi→Hân | 3 |
| **Tổng** | | **8** |

Không có đường nào qua `Dũng`. Nếu bỏ `labelFilter`, số path độ sâu 1–3 thành **10** (bổ sung `An→Bình→Dũng` và `An→Bình→Dũng→Giang`).

### 5.1. Các toán tử lọc label

APOC hỗ trợ các tiền tố thông dụng trong `labelFilter`:

| Tiền tố | Ý nghĩa điển hình |
| --- | --- |
| `+Label` | Cho phép node có label thuộc allowlist |
| `-Label` | Loại node có label thuộc denylist |
| `>Label` | Đánh dấu node kết thúc path hợp lệ; có thể còn tiếp tục duyệt qua nó |
| `/Label` | Đánh dấu node kết thúc và **dừng mở rộng tiếp qua node đó** |

Ví dụ muốn chỉ cho phép đi qua các node đáng tin cậy và cấm các node `Blocked`:

```cypher
MATCH (start:ApocDemoPerson {personId: 'P01'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  labelFilter: '+ApocDemoTrusted|-ApocDemoBlocked',
  filterStartNode: false,
  minLevel: 1,
  maxLevel: 3,
  uniqueness: 'NODE_PATH'
})
YIELD path
RETURN [n IN nodes(path) | n.personId] AS route;
```

`An` chưa có label `ApocDemoTrusted`, nhưng `filterStartNode: false` tránh áp dụng label filter lên chính điểm bắt đầu. Các node tiếp theo phải thỏa rule allow/deny. Khi phối hợp nhiều loại filter, các nhóm quy tắc có độ ưu tiên riêng; không nên mặc định thứ tự viết các mục `+`, `-`, `>`, `/` là thứ tự thực thi.

**Lưu ý:** `labelFilter` lọc graph theo nhãn. Nó không tự thay thế kiểm soát quyền truy cập theo người dùng hoặc tenant ở tầng ứng dụng/database. Một mô hình có dữ liệu nhạy cảm phải kiểm soát quyền và điều kiện truy cập độc lập với ví dụ duyệt.

## 6. Tìm đường tới đích với endNodes và terminatorNodes

Khi câu hỏi là “từ An đi được tới Giang bằng những đường nào?”, cần giới hạn **đích**. Chỉ dùng `maxLevel: 3` sẽ trả cả những đường dẫn tới Bình, Chi, Em và Hân, dù ứng dụng không cần.

Có thể cung cấp node đích cho `endNodes` hoặc `terminatorNodes`. Hai khái niệm cần phân biệt:

- **`endNodes`:** đánh dấu những node làm điểm kết thúc hợp lệ để trả đường đi; việc duyệt có thể tiếp tục qua chúng nếu còn điều kiện cho phép.
- **`terminatorNodes`:** đánh dấu những node đích mà khi chạm tới thì nhánh duyệt dừng, tránh mở rộng vượt quá đích.

Ví dụ chỉ tìm đường kết thúc tại Giang, không qua Dũng và không đi quá ba quan hệ:

```cypher
MATCH (start:ApocDemoPerson {personId: 'P01'})
MATCH (target:ApocDemoPerson {personId: 'P06'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  labelFilter: '-ApocDemoBlocked',
  minLevel: 1,
  maxLevel: 3,
  terminatorNodes: [target],
  bfs: true,
  uniqueness: 'RELATIONSHIP_PATH',
  limit: 20
})
YIELD path
RETURN length(path) AS hops,
       [n IN nodes(path) | n.personId] AS route
ORDER BY hops, route;
```

Với data mẫu, có **3 đường đi**:

1. `P01 → P02 → P05 → P06` (An → Bình → Em → Giang).
2. `P01 → P03 → P05 → P06` (An → Chi → Em → Giang).
3. `P01 → P03 → P07 → P06` (An → Chi → Hân → Giang).

Đường qua Dũng bị lọc; nhánh `Giang→An` sẽ không được mở rộng sau khi tới đích vì đã dùng `terminatorNodes`. Trong ứng dụng khác, nếu cần tiếp tục truy vết **vượt qua** một node đích trung gian, hãy xem `endNodes` thay vì `terminatorNodes`.

Nếu yêu cầu nghiệp vụ là “tìm **một** đường tới Giang”, có thể kết hợp `bfs: true` với `limit: 1` và `terminatorNodes` để ưu tiên đường có ít bước. Tuy vậy, khi có nhiều đường cùng độ sâu, **không giả định tuyến cụ thể nào sẽ được trả** nếu chưa có quy tắc lựa chọn bổ sung.

## 7. BFS và DFS: chọn cách lấy kết quả

`bfs` xác định kiểu duyệt:

- `bfs: true` (breadth-first search): mở rộng theo từng tầng từ gần đến xa. Thích hợp khi muốn ưu tiên đường có **ít relationship** và có một giới hạn số path được trả.
- `bfs: false` (depth-first search): đi sâu theo nhánh trước khi quay lại các nhánh khác. Thích hợp cho một số kiểu thăm dò đường đi, nhưng khi kèm `limit` có thể trả kết quả sâu trước khi xét các nhánh gần.

`bfs` **không đồng nghĩa với thuật toán đường đi ngắn nhất có trọng số**. Mỗi bước được hiểu theo số relationship; nếu cạnh có trọng số thời gian, chi phí hoặc độ rủi ro thì cần bài toán/path algorithm phù hợp thay vì kết luận BFS cho tuyến rẻ nhất.

Ví dụ so sánh hai chiến lược với cùng bộ lọc:

```cypher
MATCH (start:ApocDemoPerson {personId: 'P01'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  labelFilter: '-ApocDemoBlocked',
  minLevel: 1,
  maxLevel: 3,
  bfs: true,
  limit: 4,
  uniqueness: 'RELATIONSHIP_PATH'
})
YIELD path
RETURN length(path) AS hops,
       [n IN nodes(path) | n.personId] AS route;
```

Thay `bfs: true` bằng `bfs: false` để thử DFS. **`limit: 4` giới hạn số path procedure trả**, không có nghĩa duyệt đúng 4 node/relationship. Kết quả được giữ lại có thể khác nhau do thứ tự thăm dò. Nếu cần thứ tự trình bày ổn định, dùng `ORDER BY` sau khi trả path; nhưng sắp xếp sau đó không thay đổi những ứng viên đã bị loại vì `limit` của procedure.

## 8. Uniqueness: một node có thể xuất hiện bao nhiêu lần?

Cùng một node đích có thể được tới qua nhiều đường. APOC cho phép cấu hình chiến lược `uniqueness`, ảnh hưởng mạnh đến số path và lượng công việc.

| Chiến lược | Ý nghĩa | Ảnh hưởng khi duyệt |
| --- | --- | --- |
| `RELATIONSHIP_PATH` | Một relationship không được lặp lại **trên cùng một path** | Có thể đi lại node cũ bằng relationship khác; có thể có nhiều path tới cùng đích |
| `NODE_PATH` | Một node không được lặp lại **trên cùng một path** | Tránh chu trình quay lại cùng node trong path, vẫn giữ nhiều path khác nhau đến cùng đích |
| `NODE_GLOBAL` | Không thăm lại cùng node khi nó đã được thấy trên phạm vi toàn phép duyệt theo chiến lược này | Giảm lặp node nhưng có thể bỏ các tuyến thay thế |
| `RELATIONSHIP_GLOBAL` | Kiểm soát tái sử dụng relationship trên phạm vi phép duyệt | Có thể cắt những tuyến thay thế dùng lại cạnh |

### 8.1. Ví dụ chu trình Giang → An

Đồ thị có đường `An→Chi→Hân→Giang→An` dài 4. Với `RELATIONSHIP_PATH`, không relationship nào bị lặp, nên tuyến quay lại An có thể xuất hiện:

```cypher
MATCH (start:ApocDemoPerson {personId: 'P01'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  labelFilter: '-ApocDemoBlocked',
  minLevel: 4,
  maxLevel: 4,
  uniqueness: 'RELATIONSHIP_PATH'
})
YIELD path
RETURN [n IN nodes(path) | n.personId] AS route;
```

Nếu thay `uniqueness` thành `'NODE_PATH'`, **không** có path dài 4 kiểu trên được trả, vì node `An` sẽ phải xuất hiện lần thứ hai. Đây là khác biệt **về tập kết quả**, không chỉ khác hiệu năng.

### 8.2. Chọn uniqueness theo mục tiêu

- Nếu bài toán cần **tất cả các tuyến hợp lệ** trong một phạm vi nhỏ, `RELATIONSHIP_PATH` hoặc `NODE_PATH` thường thích hợp hơn việc cấm node trên toàn bộ phép duyệt.
- Nếu chỉ cần xác định **tập node có thể tới** và chấp nhận không giữ tất cả đường đi thay thế, có thể cân nhắc `NODE_GLOBAL` hoặc procedure duyệt subgraph phù hợp.
- Nếu đòi “mọi cách đi đến Giang”, không chọn `NODE_GLOBAL` một cách tùy tiện: một đường đi đến Em có thể khiến đường khác tới Em bị loại, kéo theo số tuyến tới Giang giảm.

Một số chiến lược uniqueness có đặc điểm riêng khi kết hợp BFS/DFS. Cần kiểm thử số path thực tế trên bộ dữ liệu nhỏ đại diện trước khi xem chúng là phương án tối ưu mặc định.

## 9. Giới hạn kết quả không đồng nghĩa với giới hạn công việc

Xét hai nơi đặt giới hạn:

```cypher
// Giới hạn ngay trong procedure
MATCH (start:ApocDemoPerson {personId: 'P01'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  minLevel: 1,
  maxLevel: 3,
  limit: 5
})
YIELD path
RETURN path;
```

```cypher
// Giới hạn sau khi procedure đã trả path vào luồng Cypher
MATCH (start:ApocDemoPerson {personId: 'P01'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  minLevel: 1,
  maxLevel: 3
})
YIELD path
WITH path
ORDER BY length(path)
LIMIT 5
RETURN path;
```

Câu thứ nhất yêu cầu procedure trả tối đa 5 path; câu thứ hai áp giới hạn **sau bước sắp xếp theo độ dài** nên có thể phải cân nhắc nhiều path trước khi chọn 5. Trong một số kế hoạch, Cypher có thể tận dụng việc tiêu thụ kết quả theo luồng, nhưng `ORDER BY` và các toán tử chặn khác thường làm tăng lượng công việc trước `LIMIT`.

Tuy nhiên, **cả hai cách đều chưa phải một hạn mức CPU hoặc số relationship được truy cập tuyệt đối**:

- `maxLevel` hạn chế độ sâu của từng path, nhưng một tầng có thể rất rộng.
- `limit` của APOC hạn chế **đường đi được trả**, không nhất thiết giới hạn chính xác số node/relationship đã được xem xét để tìm được các đường phù hợp.
- `ORDER BY` ngoài procedure sắp xếp kết quả được nhận, không tác động tới thứ tự duyệt bên trong.
- `collect(path)` sau cùng có thể giữ nhiều path rất lớn nếu không thu hẹp kết quả.

Đối với API public hoặc truy vấn người dùng tự đặt phạm vi, nên **kiểm soát maxDepth, maxPaths và loại relationship hợp lệ ở tầng ứng dụng**, ngoài các giới hạn về thời gian/tài nguyên mà hệ thống triển khai hỗ trợ.

## 10. Đếm node đích và trả kết quả gọn

Nếu giao diện chỉ muốn **danh sách người có thể tới** trong ba bước, trả toàn bộ `path` sẽ tạo nhiều bản sao cùng một đích. Ví dụ Em và Giang có thể xuất hiện trong nhiều path.

```cypher
MATCH (start:ApocDemoPerson {personId: 'P01'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  labelFilter: '-ApocDemoBlocked',
  minLevel: 1,
  maxLevel: 3,
  uniqueness: 'RELATIONSHIP_PATH'
})
YIELD path
WITH last(nodes(path)) AS person
RETURN DISTINCT person.personId AS personId,
       person.name AS name
ORDER BY personId;
```

Trên dữ liệu mẫu, kết quả có **5 node đích khác nhau**: P02 (Bình), P03 (Chi), P05 (Em), P06 (Giang), P07 (Hân). `DISTINCT` khử kết quả trùng, nhưng nếu procedure đã tạo nhiều path thì chi phí duyệt **không tự biến mất**.

Nếu chỉ cần số đích:

```cypher
MATCH (start:ApocDemoPerson {personId: 'P01'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  labelFilter: '-ApocDemoBlocked',
  minLevel: 1,
  maxLevel: 3,
  uniqueness: 'RELATIONSHIP_PATH'
})
YIELD path
RETURN count(DISTINCT last(nodes(path))) AS reachablePeople;
```

Kết quả là **5**, khác với **8** path. Khi mục tiêu là reachability của node chứ không phải liệt kê tuyến, có thể xem xét các procedure chuyên dụng như `apoc.path.subgraphNodes` với điều kiện giới hạn tương ứng. Dù dùng procedure nào cũng cần đo trên graph thực; không nên khẳng định một cách gọi luôn nhanh hơn.

Để giảm payload trả về Java Driver, dùng projection gồm `personId`, `name`, `hops` hoặc danh sách ID thay vì trả toàn bộ node và relationship, trừ khi ứng dụng thực sự phải hiển thị đường đi chi tiết.

## 11. Truy vấn parameter hóa cho ứng dụng Java

Một API thường nhận ID xuất phát và quy định độ sâu tối đa, số tuyến tối đa. Truyền các **giá trị** bằng tham số Cypher, không ghép trực tiếp chuỗi người dùng vào truy vấn.

```cypher
MATCH (start:ApocDemoPerson {personId: $startId})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  labelFilter: '-ApocDemoBlocked',
  minLevel: 1,
  maxLevel: $maxDepth,
  bfs: true,
  uniqueness: 'NODE_PATH',
  limit: $maxPaths
})
YIELD path
RETURN length(path) AS hops,
       [n IN nodes(path) | n.personId] AS route;
```

Tầng ứng dụng cần **xác thực và áp trần** trước khi truyền:

| Tham số | Quy tắc API ví dụ |
| --- | --- |
| `$startId` | Phải thuộc đối tượng người gọi được phép truy cập |
| `$maxDepth` | Số nguyên trong khoảng `1..3` cho endpoint minh họa |
| `$maxPaths` | Số nguyên trong khoảng `1..100` cho endpoint minh họa |
| `relationshipFilter` | Hard-code/allowlist theo nghiệp vụ; không mở tùy ý mọi relationship |
| `labelFilter` | Điều kiện mô hình được kiểm soát bởi server; không nhận cấu hình lọc thô từ client |

Các giới hạn `1..3` và `1..100` là **ví dụ chính sách API**, không phải giới hạn kỹ thuật do Neo4j áp cho mọi graph. Chúng phải được đo và điều chỉnh theo độ phân nhánh, tài nguyên, yêu cầu người dùng và mục tiêu độ trễ thực tế.

Trong Neo4j Java Driver, có thể thực thi câu Cypher ở trên trong read transaction với tham số `Map.of("startId", "P01", "maxDepth", 3, "maxPaths", 100)`, sau đó đọc các trường `route` và `hops`. Với Spring Data Neo4j, có thể dùng truy vấn Cypher tùy chỉnh và projection DTO phù hợp; không nên ánh xạ một `path` lớn thành toàn bộ entity graph nếu chỉ cần danh sách ID.

**Không dùng APOC như lớp phân quyền độc lập.** Cho phép người dùng đặt `maxDepth` rất lớn hoặc truyền trực tiếp `relationshipFilter` tùy ý có thể khiến API khám phá các loại cạnh không mong muốn, ngay cả khi cú pháp Cypher được parameter hóa. Phải áp chính sách truy cập dữ liệu trước/sau duyệt theo mô hình bảo mật đã triển khai.

## 12. So sánh với đường đi Cypher thuần và các thuật toán khác

Nếu chỉ cần một mẫu đơn giản “đi từ A theo đúng type quan hệ, tối đa ba bước”, Cypher thuần thường đủ:

```cypher
MATCH path = (a:ApocDemoPerson {personId: 'P01'})
             -[:APOC_DEMO_FOLLOWS*1..3]->
             (b:ApocDemoPerson)
WHERE NONE (n IN nodes(path) WHERE n:ApocDemoBlocked)
RETURN [n IN nodes(path) | n.personId] AS route,
       length(path) AS hops
ORDER BY hops, route;
```

Ví dụ này dùng cú pháp variable-length relationship quen thuộc ở Cypher 5. Với Cypher 25 và các phiên bản mới, xem cú pháp quantified path/quantified relationships tương ứng. Kết quả và hiệu năng giữa hai cách có thể khác do semantics của uniqueness và cách planner/procedure thực thi; **không so sánh tốc độ nếu chưa kiểm tra chúng trả cùng tập đường đi mong muốn**.

| Nhu cầu | Công cụ nên cân nhắc |
| --- | --- |
| Ghép mẫu đường đi ngắn, ít điều kiện đặc biệt | Cypher `MATCH`, quantified path pattern thích hợp |
| Duyệt với nhiều điều kiện kiểu quan hệ, label, danh sách end/terminator, chiến lược uniqueness | `apoc.path.expandConfig` |
| Chỉ cần node thuộc subgraph có thể tới | `apoc.path.subgraphNodes` hoặc cách truy vấn reachability tương ứng |
| Tìm đường ngắn nhất về **số bước** với ràng buộc cụ thể | Cypher shortest-path hoặc thuật toán phù hợp |
| Tìm đường tốt nhất theo **trọng số** cạnh | Các thuật toán đồ thị có hỗ trợ trọng số, ví dụ Graph Data Science nếu hệ thống có và được cấp phép/cài đặt |

APOC là **bộ procedure thực dụng**, không phải lựa chọn bắt buộc cho mọi truy vấn đường đi; một số bài toán có thể được Cypher planner tối ưu tốt hơn khi thể hiện toàn bộ bằng mẫu truy vấn.

## 13. Đọc EXPLAIN và PROFILE đúng cách khi dùng APOC

Có thể bắt đầu bằng `EXPLAIN`:

```cypher
EXPLAIN
MATCH (start:ApocDemoPerson {personId: 'P01'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  labelFilter: '-ApocDemoBlocked',
  minLevel: 1,
  maxLevel: 3,
  bfs: true,
  uniqueness: 'NODE_PATH',
  limit: 100
})
YIELD path
RETURN length(path) AS hops;
```

`EXPLAIN` lập kế hoạch mà không thực thi truy vấn. Plan có thể hiển thị `ProcedureCall`, nhưng **không nhất thiết giải thích chi tiết mọi bước duyệt nội bộ của APOC**. Khi cần đo, dùng `PROFILE` cho phép duyệt chỉ đọc trên graph thử nghiệm:

```cypher
PROFILE
MATCH (start:ApocDemoPerson {personId: 'P01'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  labelFilter: '-ApocDemoBlocked',
  minLevel: 1,
  maxLevel: 3,
  bfs: true,
  uniqueness: 'NODE_PATH',
  limit: 100
})
YIELD path
RETURN length(path) AS hops;
```

Cần quan sát:

1. **Số hàng đầu vào:** từ `MATCH start` có đúng một node xuất phát không? Nếu dùng `MATCH` không chọn lọc, procedure sẽ bị gọi cho nhiều start và chi phí nhân lên.
2. **Số hàng đầu ra procedure:** có nhiều path hơn mong đợi không? Một node đích có thể xuất hiện trên nhiều path.
3. **Độ dài path:** có vượt `maxLevel` hoặc có path không đúng type/hướng quan hệ không?
4. **Độ trễ và bộ nhớ thực tế:** các con số ở `PROFILE`/logs/metric ứng dụng có đủ để khẳng định endpoint an toàn ở tải dự kiến không?
5. **Payload:** cần path đầy đủ hay chỉ ID node đích? Kích thước response có tăng quá nhiều theo độ sâu không?

**Giới hạn đo:** `PROFILE` cho thấy thông tin thực thi mà Neo4j cung cấp, nhưng không nhất thiết đo tường minh số cạnh được xem xét bên trong mọi procedure APOC. Kết quả “8 path” không có nghĩa procedure chỉ đọc đúng 8 relationship.

## 14. Những lỗi thiết kế thường gặp

| Sai lầm | Rủi ro | Cách sửa |
| --- | --- | --- |
| Bỏ `maxLevel` khi graph có nhiều nhánh và chu trình | Độ sâu duyệt không được giới hạn theo nghiệp vụ; lượng công việc khó dự tính | Đặt `maxLevel` nhỏ và có thể cấu hình trong trần được kiểm soát |
| Chỉ thêm `RETURN ... LIMIT 10` | Không bảo đảm procedure chỉ duyệt 10 đường | Dùng `limit` trong procedure và đo thực tế; giảm chiều sâu/độ rộng |
| Để `relationshipFilter` quá rộng hoặc không đặt | Duyệt type/hướng không mong muốn | Chỉ rõ loại và chiều quan hệ được phép |
| Nhầm `endNodes` với `terminatorNodes` | Có thể duyệt tiếp sau node đích | Chọn đúng “được kết thúc” hay “phải dừng” |
| Dùng `NODE_GLOBAL` khi cần mọi tuyến | Mất các đường thay thế đến cùng node | Dùng uniqueness theo path phù hợp và phạm vi nhỏ |
| Dùng `RELATIONSHIP_PATH` rồi cho rằng node không thể lặp | Node có thể xuất hiện lại qua cạnh khác | Dùng `NODE_PATH` khi không muốn lặp node |
| Chỉ đếm `count(*)` để biết số người có thể tới | Đếm số path, có thể đếm trùng người | `count(DISTINCT last(nodes(path)))` |
| Trả `collect(path)` không giới hạn | Giữ list path lớn và tăng payload | Chỉ trả trường cần thiết, giới hạn đầu ra |
| Lấy start bằng query quét rộng | Procedure được gọi cho nhiều điểm bắt đầu | Dùng khóa nghiệp vụ/index và kiểm soát số start |
| Tin rằng BFS là “đường rẻ nhất” | Nhầm số bước với tổng chi phí cạnh | Chọn thuật toán hỗ trợ trọng số nếu cần |
| Dùng labelFilter làm toàn bộ phân quyền | Điều kiện nhãn không bao phủ mọi quy tắc truy cập | Kiểm soát quyền và điều kiện tenant/người dùng độc lập |

## 15. Quy trình triển khai an toàn

Khi xây dựng chức năng “khám phá quan hệ” cho dữ liệu thật:

1. **Định nghĩa câu hỏi:** cần mọi path, một path, tập node đích hay chỉ kiểm tra có đường đi?
2. **Chọn start bằng khóa ổn định:** giới hạn số node đầu vào; tạo index/constraint nếu phù hợp.
3. **Chốt relationshipFilter và chiều:** chỉ duyệt đúng loại quan hệ thể hiện nghiệp vụ.
4. **Chốt phạm vi node hợp lệ:** labelFilter, allowlist/denylist và quyền truy cập theo tổ chức/tenant.
5. **Chốt giới hạn độ sâu:** minLevel, maxLevel và quy tắc kết thúc/terminator.
6. **Chọn uniqueness:** NODE_PATH khi cấm quay lại node trên một tuyến; RELATIONSHIP_PATH khi cần nhiều tuyến khác nhau; NODE_GLOBAL khi chỉ cần duyệt node trong phạm vi toàn cục.
7. **Chọn BFS/DFS và limit:** xác định muốn ưu tiên đường gần hay thăm dò nhánh; giới hạn số đường trả.
8. **Giảm dữ liệu đầu ra:** projection ID, tên, hops thay cho toàn bộ path khi không cần.
9. **Đo trên graph đại diện:** số path, số node đích, độ trễ, CPU/bộ nhớ và kích thước response; kiểm tra trường hợp graph nhiều nhánh hoặc có chu trình.
10. **Áp trần ở API:** không cho người dùng tự nới vô hạn maxDepth, maxPaths hoặc mở các quan hệ nhạy cảm.

### Bài tự kiểm tra

**Câu 1.** Tại sao `maxLevel: 3` không đảm bảo truy vấn chỉ truy cập ba relationship?

**Câu 2.** Với data mẫu, `minLevel: 1`, `maxLevel: 3`, `relationshipFilter: 'APOC_DEMO_FOLLOWS>'` và `labelFilter: '-ApocDemoBlocked'` trả bao nhiêu path, bao nhiêu node đích khác nhau?

**Câu 3.** Nếu chỉ cần đi đến `Giang` rồi dừng, vì sao `terminatorNodes: [target]` thích hợp?

**Câu 4.** Vì sao `NODE_GLOBAL` có thể không phù hợp khi yêu cầu liệt kê mọi đường đi tới `Giang`?

**Câu 5.** Nếu `Giang→An` tạo chu trình, `NODE_PATH` và `RELATIONSHIP_PATH` khác nhau ra sao?

**Câu 6.** `bfs: true` có chứng minh tuyến tối ưu theo chi phí vận chuyển hoặc rủi ro trên relationship không?

**Đáp án gợi ý:** (1) Đây là độ sâu **mỗi path**, một node có thể có nhiều cạnh để xem xét. (2) **8 path**, **5 đích**. (3) Nhánh duyệt không cần đi tiếp sau đích. (4) Node đã được thăm có thể khiến các tuyến khác bị cắt. (5) NODE_PATH chặn lặp node, RELATIONSHIP_PATH chỉ chặn lặp relationship trên cùng path. (6) Không, BFS ưu tiên số bước, không tối ưu tổng trọng số tùy ý.

## 16. Tài liệu tham khảo

- [Neo4j APOC — apoc.path.expandConfig](https://neo4j.com/docs/apoc/current/overview/apoc.path/apoc.path.expandConfig/): map cấu hình, các ví dụ và lựa chọn giới hạn.
- [Neo4j APOC — Path expanding procedures](https://neo4j.com/docs/apoc/current/graph-querying/expand-paths/): ý nghĩa relationship/label filters, end và terminator nodes.
- [Neo4j Cypher Manual — Variable-length patterns](https://neo4j.com/docs/cypher-manual/current/patterns/variable-length-patterns/): cách diễn đạt đường đi trong Cypher.
- [Neo4j Cypher Manual — Execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/): phân biệt EXPLAIN, PROFILE và đọc kế hoạch thực thi.
- [Neo4j Java Driver Manual](https://neo4j.com/docs/java-manual/current/): parameter binding, đọc result và quản lý read transaction.

**Ghi nhớ:** một phép mở rộng đường đi hữu ích cần **giới hạn cả loại/chiều relationship, nhãn node, độ sâu, quy tắc lặp và số kết quả**. `apoc.path.expandConfig` cho phép biểu đạt các giới hạn này trong một lời gọi, nhưng hiệu năng và tính đúng đắn vẫn phụ thuộc cấu trúc graph, phiên bản APOC và cách ứng dụng sử dụng kết quả.

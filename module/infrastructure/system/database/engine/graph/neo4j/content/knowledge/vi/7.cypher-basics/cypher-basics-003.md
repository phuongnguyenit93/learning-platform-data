# Đọc và viết mẫu đồ thị bằng dấu ngoặc, mũi tên và nhãn trong Cypher

> **Chương:** Nền tảng Cypher  
> **Ngữ cảnh:** Neo4j là cơ sở dữ liệu *property graph*, lưu node, relationship và thuộc tính của chúng. Cypher dùng những mẫu ký hiệu ngắn gọn để mô tả kết nối cần tìm hoặc cần tạo. Bài này giúp bạn **đọc đúng và tự viết được các mẫu đồ thị** trước khi học truy vấn đường đi, tối ưu truy vấn, Java Driver hoặc Spring Data Neo4j.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt node, relationship, label, relationship type và property qua ký hiệu trong Cypher.
2. Đọc được chiều của mũi tên và phân biệt mẫu có hướng với mẫu không yêu cầu hướng.
3. Viết mẫu một node, một quan hệ, nhiều quan hệ nối tiếp hoặc nhiều nhánh nối từ một node.
4. Kết hợp mẫu với `MATCH`, `WHERE`, `OPTIONAL MATCH`, `CREATE` và `MERGE` theo đúng mục đích.
5. Chuyển qua lại giữa một sơ đồ đồ thị, câu mô tả tiếng Việt và đoạn Cypher.
6. Nhận ra lỗi cú pháp hoặc sai nghĩa thường gặp khi đặt dấu ngoặc, dấu hai chấm, mũi tên và nhãn.

## 2. Mẫu đồ thị (*graph pattern*) là gì?

Trong một *property graph*:

- **Node** biểu diễn thực thể như người, dự án, nhóm hoặc máy chủ; node có thể có nhiều **label**.
- **Relationship** nối hai node, có **type** và **hướng lưu trữ**; relationship cũng có thể có thuộc tính.
- **Property** lưu cặp khóa–giá trị trên node hoặc relationship, chẳng hạn `name`, `id`, `since`.

Ví dụ nghiệp vụ: “An đang tham gia dự án Graph API với vai trò lead”.

```text
(An:Person) ──[:WORKS_ON {role: 'lead'}]──> (Graph API:Project)
```

Mẫu tương ứng trong Cypher:

```cypher
(a:Person {name: 'An'})-[work:WORKS_ON {role: 'lead'}]->(pr:Project {name: 'Graph API'})
```

Đây mới là **mẫu**, chưa phải một câu truy vấn độc lập. Ta đặt nó trong mệnh đề:

```cypher
MATCH (a:Person {name: 'An'})-[work:WORKS_ON {role: 'lead'}]->(pr:Project {name: 'Graph API'})
RETURN a.name AS nhanSu, work.role AS vaiTro, pr.name AS duAn;
```

`MATCH` dùng mẫu để tìm dữ liệu đã tồn tại. Còn `CREATE`, `MERGE` dùng mẫu trong thao tác ghi, nhưng ý nghĩa của chúng khác nhau; phần 10 sẽ làm rõ.

## 3. Bảng ký hiệu cần nhớ

| Cú pháp | Cách đọc | Ý nghĩa |
|---|---|---|
| `()` | Một node bất kỳ | Chưa đặt tên biến, chưa yêu cầu label hay thuộc tính. |
| `(p)` | Node có biến `p` | Có thể tham chiếu `p` ở phần khác của truy vấn. |
| `(p:Person)` | Node `p` có label `Person` | Dấu `:` trước tên label. |
| `(p:Person {id: 'p1'})` | Node `Person` có `id` bằng `p1` | Ngoặc nhọn là **property map**. |
| `(p:Person:Employee)` | Node có cả hai label | Dạng nhiều label được hỗ trợ trong mẫu truyền thống. |
| `--` | Một relationship, không yêu cầu hướng | Dùng trong mẫu đọc, không nêu type. |
| `-->` | Một relationship đi theo chiều từ trái sang phải | Không nêu type. |
| `<--` | Một relationship đi theo chiều từ phải sang trái | Không nêu type. |
| `-[r]->` | Một relationship có biến `r` | Không ràng buộc type. |
| `-[:KNOWS]->` | Một relationship có type `KNOWS` | Hướng từ trái sang phải. |
| `-[r:KNOWS]->` | Relationship `r` với type `KNOWS` | Có thể truy cập `r.since`. |
| `-[r:KNOWS {since: 2021}]->` | Relationship có type và điều kiện thuộc tính | Kết hợp biến, type, property map. |
| `<-[:KNOWS]-` | Một relationship `KNOWS` hướng từ phải sang trái | Đọc theo mũi tên. |
| `-[:KNOWS]-` | Một relationship `KNOWS` theo bất kỳ hướng nào | Dùng khi chỉ quan tâm liên kết. |
| `path = (a)-[:KNOWS]->(b)` | Đặt tên `path` cho đường đi | Giá trị path chứa cả node và relationship. |

**Quy tắc trực quan:** ngoặc tròn `(...)` bao node; ngoặc vuông `[...]` bao relationship; dấu hai chấm `:` giới thiệu label hoặc relationship type; ngoặc nhọn `{...}` bao thuộc tính; dấu gạch và mũi tên thể hiện kết nối/hướng.

### 3.1. Đọc từ trái qua phải, nhưng luôn nhìn mũi tên

```text
(a)-[:FOLLOWS]->(b)   a theo dõi b
(a)<-[:FOLLOWS]-(b)   b theo dõi a
(a)-[:FOLLOWS]-(b)    a và b có quan hệ FOLLOWS theo một trong hai hướng
```

Với mẫu thứ hai, dù `a` đứng bên trái, **hướng relationship vẫn là từ `b` đến `a`**. Không suy hướng bằng vị trí chữ hoặc thói quen đọc từ trái sang phải; hãy nhìn đầu mũi tên.

## 4. Tạo một đồ thị mẫu để thực hành

Chạy dữ liệu dưới đây trong **cơ sở dữ liệu thực hành**. Các ID bắt đầu bằng `cypher003-` để bạn dễ phân biệt với dữ liệu khác. Ví dụ dùng `MERGE` cho node và relationship để lần chạy lại thông thường không sinh thêm phần tử khớp cùng mẫu.

```cypher
MERGE (an:Person {id: 'cypher003-an'})
SET an.name = 'An', an.city = 'Hà Nội'
SET an:Engineer

MERGE (binh:Person {id: 'cypher003-binh'})
SET binh.name = 'Bình', binh.city = 'Đà Nẵng'

MERGE (chi:Person {id: 'cypher003-chi'})
SET chi.name = 'Chi', chi.city = 'Hà Nội'

MERGE (api:Project {id: 'cypher003-api'})
SET api.name = 'Graph API', api.status = 'active'

MERGE (team:Team {id: 'cypher003-platform'})
SET team.name = 'Platform'

MERGE (an)-[knowsBinh:KNOWS]->(binh)
SET knowsBinh.since = 2021

MERGE (binh)-[knowsChi:KNOWS]->(chi)
SET knowsChi.since = 2023

MERGE (an)-[works:WORKS_ON]->(api)
SET works.role = 'lead'

MERGE (binh)-[helps:WORKS_ON]->(api)
SET helps.role = 'developer'

MERGE (an)-[:MEMBER_OF]->(team);
```

Sơ đồ tương ứng:

```text
     [Person, Engineer]                        [Team]
           An ────────────[:MEMBER_OF]─────────> Platform
            │
            ├─────────────[:KNOWS {since:2021}]──────> Bình:Person
            │                                             │
            │                                             └─[:KNOWS {since:2023}]──> Chi:Person
            │
            └─────────────[:WORKS_ON {role:'lead'}]─┐
                                                    v
                                               Graph API:Project
                                                    ^
                         Bình ─[:WORKS_ON {role:'developer'}]─┘
```

**Lưu ý về kết quả:** các số dòng minh họa dưới đây giả định các node/relationship liên quan chỉ gồm dữ liệu mẫu vừa tạo. Nếu chạy trong database có dữ liệu khác, hãy lọc theo `id` để tránh lẫn mẫu. Nếu database có sẵn nhiều node trùng `id`, `MERGE` không thay thế một uniqueness constraint.

## 5. Đọc và viết mẫu node bằng `(...)`

### 5.1. Chỉ node, chưa có label

```cypher
MATCH (n)
RETURN n
LIMIT 5;
```

`(n)` là **một node bất kỳ**, được gán biến `n`. Nó có thể là `Person`, `Project`, `Team` hoặc node của label khác. `()` cũng là một node bất kỳ, nhưng không gán tên:

```cypher
MATCH ()-[:MEMBER_OF]->(t:Team {id: 'cypher003-platform'})
RETURN t.name AS nhom;
```

Trong ví dụ thứ hai, node bên trái không cần đặt biến vì ta chỉ cần thông tin của nhóm. Việc bỏ biến không làm node biến mất khỏi mẫu.

### 5.2. Label dùng dấu hai chấm

```cypher
MATCH (p:Person {id: 'cypher003-an'})
RETURN p.name AS ten, labels(p) AS cacNhan;
```

`Person` là **label**, `p` là **biến**. Tại node An, `labels(p)` chứa `Person` và `Engineer` (thứ tự label trong danh sách không nên được giả định).

Node có thể có nhiều label. Mẫu:

```cypher
MATCH (p:Person:Engineer)
WHERE p.id = 'cypher003-an'
RETURN p.name AS kySu;
```

chỉ khớp node có **cả hai label** `Person` và `Engineer`. Tên label phân biệt hoa/thường: `Person` và `person` không đồng nhất.

**Lỗi dễ nhầm:**

```cypher
MATCH (Person)
RETURN Person;
```

Trong câu trên, `Person` là **biến tên Person**, không phải label, vì thiếu dấu `:`. Để lọc label hãy viết `(p:Person)` hoặc `(:Person)`.

### 5.3. Thuộc tính nằm trong `{...}`

```cypher
MATCH (p:Person {id: 'cypher003-binh', city: 'Đà Nẵng'})
RETURN p.name AS ten;
```

Property map sau label có ý nghĩa: tìm node có các thuộc tính tương ứng thỏa giá trị đã cho. Bạn cũng có thể tách điều kiện:

```cypher
MATCH (p:Person)
WHERE p.id = 'cypher003-binh' AND p.city = 'Đà Nẵng'
RETURN p.name AS ten;
```

Nếu ứng dụng truyền ID từ Java Driver hoặc Spring Data Neo4j, hãy dùng **tham số** thay cho ghép giá trị vào chuỗi truy vấn:

```cypher
MATCH (p:Person {id: $personId})
RETURN p.name AS ten;
```

Trong đoạn này, `p` là biến của mẫu, còn `$personId` là giá trị tham số do bên gọi cung cấp, ví dụ `'cypher003-binh'`.

## 6. Đọc và viết mẫu relationship bằng `-[]-` và mũi tên

### 6.1. Một cạnh có type và chiều từ trái sang phải

```cypher
MATCH (a:Person {id: 'cypher003-an'})-[:KNOWS]->(b:Person)
RETURN a.name AS nguoiA, b.name AS nguoiB;
```

Đọc: “Từ node An, đi theo **một** relationship `KNOWS` hướng ra ngoài đến một node `Person` khác”. Kết quả dữ liệu mẫu: **An → Bình**.

Mẫu `-[:KNOWS]->` gồm:

1. `-` nối node đầu với relationship.
2. `[ ... ]` bọc thông tin relationship.
3. `:KNOWS` yêu cầu type `KNOWS`.
4. `->` chỉ chiều từ node trái đến node phải.

`KNOWS` là type, không phải tên biến. Nếu không cần tham chiếu relationship sau này, không phải đặt biến cho nó.

### 6.2. Quan hệ hướng từ phải sang trái

```cypher
MATCH (chi:Person {id: 'cypher003-chi'})<-[:KNOWS]-(other:Person)
RETURN other.name AS nguoiBietChi;
```

Đọc: “Ai có relationship `KNOWS` **đi tới** Chi?”. Kết quả: **Bình**.

Cùng một connection có thể được viết thành hai mẫu tương đương về chiều:

```text
(binh)-[:KNOWS]->(chi)
(chi)<-[:KNOWS]-(binh)
```

Đổi vị trí hai node và đổi cách vẽ mũi tên **không đảo hướng dữ liệu đã lưu**.

### 6.3. Không yêu cầu chiều

```cypher
MATCH (binh:Person {id: 'cypher003-binh'})-[:KNOWS]-(other:Person)
RETURN other.name AS ketNoi
ORDER BY ketNoi;
```

`-[:KNOWS]-` cho phép match relationship theo **cả hai hướng**. Vì Bình nhận cạnh từ An và đi ra cạnh tới Chi, kết quả có **An** và **Chi**.

Điều này **không có nghĩa relationship trong database trở thành vô hướng**. Relationship vẫn có hướng lưu trữ; mẫu chỉ yêu cầu có kết nối theo một trong hai chiều.

### 6.4. Bỏ ngoặc vuông khi không lọc type

```cypher
MATCH (an:Person {id: 'cypher003-an'})-->(destination)
RETURN labels(destination) AS nhanDich,
       destination.name AS tenDich;
```

`-->` yêu cầu có một relationship đi ra nhưng **không chỉ định type**. Trong đồ thị mẫu, đích có thể là Bình, Graph API hoặc Platform vì An có ba loại relationship đi ra. Tương tự:

```cypher
MATCH (an:Person {id: 'cypher003-an'})--(other)
RETURN other.name AS ketNoi;
```

`--` không lọc type hoặc hướng. Khi cần chính xác mối quan hệ nghiệp vụ, hãy đưa type vào ngoặc vuông, ví dụ `-[:WORKS_ON]->`.

### 6.5. Gắn biến và điều kiện thuộc tính vào relationship

```cypher
MATCH (a:Person {id: 'cypher003-an'})
      -[r:KNOWS {since: 2021}]->(b:Person)
RETURN b.name AS ban,
       r.since AS quenTu,
       type(r) AS loaiQuanHe;
```

`r` là biến relationship, `KNOWS` là type, `{since: 2021}` lọc theo thuộc tính trên **relationship**. Trong kết quả, `r.since = 2021` và `type(r) = 'KNOWS'`.

Nếu chỉ có `-[r]->`, query vẫn có biến `r` nhưng **không lọc type**:

```cypher
MATCH (a:Person {id: 'cypher003-an'})-[r]->(b)
RETURN type(r) AS loai, b.name AS dich;
```

Hãy phân biệt thật rõ `-[KNOWS]->` với `-[:KNOWS]->`: biểu thức đầu đặt biến **tên KNOWS** nhưng không yêu cầu type `KNOWS`; biểu thức thứ hai mới lọc đúng type.

## 7. Ghép nhiều node và relationship thành mẫu lớn hơn

### 7.1. Chuỗi nối tiếp hai cạnh

Để tìm “An biết một người, người đó biết tiếp một người khác”, viết:

```cypher
MATCH (an:Person {id: 'cypher003-an'})
      -[:KNOWS]->(middle:Person)
      -[:KNOWS]->(last:Person)
RETURN an.name AS batDau, middle.name AS trungGian, last.name AS ketThuc;
```

Trong đồ thị mẫu: **An → Bình → Chi**. Hai lần `-[:KNOWS]->` có nghĩa là **hai cạnh nối tiếp**, không phải một cạnh có hai type.

Bạn có thể đặt tên toàn bộ đường đi để quan sát mẫu:

```cypher
MATCH route = (an:Person {id: 'cypher003-an'})
              -[:KNOWS]->(:Person)
              -[:KNOWS]->(last:Person)
RETURN last.name AS dich,
       length(route) AS soCanh,
       [n IN nodes(route) | n.name] AS cacNode;
```

`length(route)` đếm **relationship**, nên trả `2`; `nodes(route)` trả ba node trong đường đi. Chi tiết về khai báo biến cho node, relationship và path là một chủ đề riêng; ở đây hãy tập trung vào **hình dạng mẫu**.

### 7.2. Nhiều nhánh cùng xuất phát từ một node

Yêu cầu: “Người vừa quen một người khác, vừa tham gia một dự án”.

```cypher
MATCH (p:Person {id: 'cypher003-an'})-[:KNOWS]->(friend:Person),
      (p)-[:WORKS_ON]->(pr:Project)
RETURN p.name AS nhanSu, friend.name AS ban, pr.name AS duAn;
```

Hai mẫu cùng dùng **biến `p`**, nên cùng xuất phát từ node An. Kết quả: **An – Bình – Graph API**.

Nếu thay bằng hai biến độc lập `p` và `x`, Neo4j có thể ghép từng kết quả của hai mẫu thành **tích Descartes**. Khi muốn biểu diễn hai nhánh của cùng một node, hãy dùng lại đúng tên biến.

### 7.3. Nhiều label, nhiều loại quan hệ

Mẫu có nhiều label là điều kiện **đồng thời**:

```cypher
MATCH (p:Person:Engineer {id: 'cypher003-an'})
RETURN p.name AS nguoiCoHaiNhan;
```

Nếu chấp nhận **một trong nhiều type**, Cypher cho phép biểu thức lựa chọn type trong mẫu đọc:

```cypher
MATCH (p:Person {id: 'cypher003-an'})-[r:KNOWS|WORKS_ON]->(other)
RETURN type(r) AS loai, other.name AS dich
ORDER BY loai;
```

Truy vấn này có thể trả `KNOWS – Bình` và `WORKS_ON – Graph API`; `MEMBER_OF` không thỏa lựa chọn type. Đừng nhầm `|` trong lựa chọn type với phép yêu cầu một node mang đồng thời nhiều label.

### 7.4. Số bước cố định và số bước biến thiên

Hai cạnh nối tiếp như ở mục 7.1 là mẫu **đúng hai bước**. Trong Neo4j/Cypher phiên bản hỗ trợ *quantified relationships* (Neo4j 5.9 trở lên), có thể dùng:

```cypher
MATCH route = (an:Person {id: 'cypher003-an'})
              -[:KNOWS]->{1,2}
              (end:Person)
RETURN end.name AS dich, length(route) AS soBuoc
ORDER BY soBuoc;
```

`{1,2}` cho phép đi một hoặc hai cạnh `KNOWS`. Với mẫu, đích lần lượt là Bình (1 bước), Chi (2 bước). Ở các phiên bản hoặc chế độ Cypher cũ hơn, bạn có thể gặp cú pháp `-[:KNOWS*1..2]->`; hãy dùng cú pháp phù hợp phiên bản đang chạy.

## 8. Đọc mẫu trong `MATCH` và `OPTIONAL MATCH`

### 8.1. `MATCH` bắt buộc khớp đủ mẫu

```cypher
MATCH (p:Person {id: 'cypher003-chi'})-[:WORKS_ON]->(pr:Project)
RETURN p.name AS nguoi, pr.name AS duAn;
```

Chi không có quan hệ `WORKS_ON` trong dữ liệu mẫu nên truy vấn trả **0 dòng**, dù node Chi vẫn tồn tại. Đó là vì **toàn bộ mẫu** phải khớp.

### 8.2. `OPTIONAL MATCH` giữ node khi thiếu cạnh

```cypher
MATCH (p:Person {id: 'cypher003-chi'})
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
RETURN p.name AS nguoi, pr.name AS duAn;
```

Kết quả có **một dòng**: `nguoi = 'Chi'` và `duAn = null`. `OPTIONAL MATCH` hữu ích khi vẽ báo cáo gồm cả node chưa có liên kết.

### 8.3. Vị trí `WHERE` với mẫu tùy chọn

```cypher
MATCH (p:Person)
WHERE p.id IN ['cypher003-an', 'cypher003-binh', 'cypher003-chi']
OPTIONAL MATCH (p)-[w:WORKS_ON]->(pr:Project)
WHERE w.role = 'lead'
RETURN p.name AS nguoi, pr.name AS duAnLead
ORDER BY nguoi;
```

`WHERE` sau `OPTIONAL MATCH` là điều kiện **của phần tùy chọn**: An khớp dự án Graph API, Bình và Chi vẫn được giữ nhưng cột `duAnLead` là `null`.

Nếu chuyển điều kiện `w.role = 'lead'` sang `WHERE` **sau một `WITH`**, các dòng chứa `null` có thể bị loại. Vị trí điều kiện vì thế ảnh hưởng trực tiếp đến cách diễn giải mẫu đồ thị.

## 9. Phân biệt mẫu với câu lệnh hoàn chỉnh

Mẫu:

```cypher
(p:Person)-[:KNOWS]->(q:Person)
```

không tự trả kết quả. Muốn truy vấn, thêm mệnh đề phù hợp:

```cypher
MATCH (p:Person {id: 'cypher003-an'})-[:KNOWS]->(q:Person)
RETURN q.name AS ban;
```

Đối chiếu các mục đích:

| Mục đích | Mệnh đề gắn với mẫu | Ghi chú |
|---|---|---|
| Tìm node, relationship đã có | `MATCH` | Không tạo dữ liệu mới. |
| Tìm nếu có, giữ dòng khi thiếu | `OPTIONAL MATCH` | Biến mới không khớp nhận `null`. |
| Tạo node/relationship mới | `CREATE` | Có thể tạo trùng khi chạy lại. |
| Tìm hoặc tạo theo một mẫu | `MERGE` | Nên kèm constraint phù hợp nếu cần duy nhất. |
| Sửa thuộc tính hoặc thêm label | `SET` | Thường đi sau `MATCH`/`MERGE` để chọn đúng đối tượng. |
| Trả node, thuộc tính hoặc path | `RETURN` | Xác định thông tin đầu ra. |

Mẫu có thể được nối với `WHERE`, `WITH` hoặc các mệnh đề khác để tiếp tục lọc và biến đổi kết quả. Cách tổ chức các mệnh đề được học chi tiết ở bài về cấu trúc truy vấn Cypher.

## 10. Viết đồ thị bằng `CREATE` và `MERGE`

Ký hiệu node và relationship giống nhau khi đọc và khi ghi, nhưng **mệnh đề** quyết định tác dụng. Đặc biệt, trong thao tác tạo relationship, hãy chỉ rõ chiều đi và type để cấu trúc lưu trữ đúng nghiệp vụ.

### 10.1. `CREATE` tạo mới

```cypher
CREATE (d:Department {id: 'cypher003-dept', name: 'Engineering'})
RETURN d.name AS tenPhong;
```

Nếu chạy lại đoạn `CREATE` trên, một node `Department` mới có cùng thuộc tính lại được tạo. Trong ứng dụng thực, hành vi này có thể gây trùng bản ghi nếu ý định chỉ là “một Department cho mỗi ID”.

Tạo relationship giữa **hai node đã được tìm thấy**:

```cypher
MATCH (an:Person {id: 'cypher003-an'})
MATCH (binh:Person {id: 'cypher003-binh'})
CREATE (an)-[:MENTORS {since: 2024}]->(binh);
```

Đoạn này **cố ý tạo** một cạnh `MENTORS` mới mỗi lần chạy, kể cả khi cạnh như vậy đã tồn tại. Chỉ chạy khi thực sự muốn tạo thêm relationship.

### 10.2. `MERGE` tìm hoặc tạo

```cypher
MERGE (d:Department {id: 'cypher003-dept'})
ON CREATE SET d.name = 'Engineering'
RETURN d.id AS id, d.name AS tenPhong;
```

`MERGE` cố gắng tìm mẫu node phù hợp, nếu không có thì tạo. `ON CREATE SET` chỉ cập nhật khi nhánh tạo được sử dụng. Với relationship, trước tiên nên ràng buộc hai node đích:

```cypher
MATCH (an:Person {id: 'cypher003-an'})
MATCH (binh:Person {id: 'cypher003-binh'})
MERGE (an)-[r:MENTORS]->(binh)
ON CREATE SET r.since = 2024
RETURN type(r) AS loai, r.since AS tuNam;
```

`MERGE` kiểm tra mẫu `(an)-[:MENTORS]->(binh)` trước khi tạo. Vì hai node đã ràng buộc bằng `MATCH`, truy vấn tránh việc vô tình tạo các node `Person` mới như khi ghép một mẫu node–relationship lớn mà chưa chỉ ra node nào là đối tượng có sẵn.

**Về tính duy nhất:** `MERGE` không thay thế tính duy nhất ở mức schema khi có nhiều giao dịch đồng thời. Đối với thuộc tính định danh như `Person.id`, nên thiết kế **uniqueness constraint** phù hợp cho hệ thống thật.

### 10.3. `SET` cập nhật thuộc tính/label đã được chọn

```cypher
MATCH (p:Person {id: 'cypher003-binh'})
SET p.city = 'Đà Nẵng'
SET p:Engineer
RETURN p.name AS ten, labels(p) AS nhan;
```

Trong ví dụ, `SET p.city` cập nhật property, còn `SET p:Engineer` bổ sung label `Engineer` vào node; không cần tạo lại node. Nhớ phân biệt property map trong mẫu `{city: 'Đà Nẵng'}` với phép gán `p.city = 'Đà Nẵng'` trong `SET`.

## 11. Đổi câu mô tả thành mẫu Cypher

| Mô tả yêu cầu | Mẫu Cypher | Điểm cần chú ý |
|---|---|---|
| Một người bất kỳ | `(p:Person)` | Label sau dấu `:`. |
| Người có ID xác định | `(p:Person {id: $id})` | Thuộc tính lọc trong ngoặc nhọn. |
| Người A biết người B | `(a:Person)-[:KNOWS]->(b:Person)` | Mũi tên từ A sang B. |
| Người A được người B biết | `(a:Person)<-[:KNOWS]-(b:Person)` | Chiều lưu trữ từ B sang A. |
| Hai người có quan hệ KNOWS theo chiều bất kỳ | `(a:Person)-[:KNOWS]-(b:Person)` | Mẫu không ràng buộc hướng. |
| Người tham gia dự án với vai trò lead | `(p:Person)-[:WORKS_ON {role: 'lead'}]->(pr:Project)` | Property đặt trên relationship. |
| Người biết bạn của bạn | `(p:Person)-[:KNOWS]->(:Person)-[:KNOWS]->(q:Person)` | Hai relationship nối tiếp. |
| Một kỹ sư đồng thời là người | `(p:Person:Engineer)` | Node thỏa cả hai label. |
| Người thuộc một nhóm | `(p:Person)-[:MEMBER_OF]->(t:Team)` | Type phân biệt với `WORKS_ON`. |

Khi tự viết mẫu, hãy làm theo bốn câu hỏi:

1. **Thực thể nào?** Đặt node bằng `(...)`, thêm label và thuộc tính nếu biết.
2. **Liên kết gì?** Đưa relationship vào giữa hai node và đặt `:TYPE` nếu cần.
3. **Theo chiều nào?** Kiểm tra mũi tên dựa vào cách lưu trữ quan hệ.
4. **Đọc hay ghi?** Chọn `MATCH`, `OPTIONAL MATCH`, `CREATE` hoặc `MERGE` phù hợp.

## 12. Lỗi thường gặp khi đọc mẫu đồ thị

| Cú pháp hoặc kết quả gây nhầm | Nguyên nhân | Cách sửa |
|---|---|---|
| `MATCH (Person)` trả nhiều label khác nhau | `Person` là biến, thiếu dấu `:`. | `MATCH (p:Person)`. |
| `-[KNOWS]->` trả nhiều loại relationship | `KNOWS` là **biến**, chưa có type. | `-[:KNOWS]->` hoặc `-[r:KNOWS]->`. |
| `(a)-[:KNOWS]->(b)` không có kết quả | Dữ liệu chỉ lưu quan hệ từ `b` đến `a`. | Đổi thành `(a)<-[:KNOWS]-(b)` hoặc dùng mẫu không yêu cầu hướng nếu hợp bài toán. |
| `(a)-->(b)` trả cả các quan hệ khác loại | Mẫu không có `:TYPE`. | Bổ sung đúng relationship type. |
| Truy vấn thiếu người chưa có dự án | `MATCH` yêu cầu cả cạnh phải tồn tại. | Dùng `OPTIONAL MATCH` nếu cần giữ người không khớp. |
| Chạy `CREATE` nhiều lần thấy node/edge tăng | `CREATE` luôn tạo mới. | Dùng `MERGE` nếu nghiệp vụ cần tìm-hoặc-tạo và thiết kế constraint phù hợp. |
| Kết quả bị nhân nhiều dòng | Một node có nhiều cạnh phù hợp hoặc ghép mẫu không có biến chung. | Kiểm tra số kết nối, biến chung, `DISTINCT`/gom nhóm theo nhu cầu. |
| Nhầm `:Person` với `:WORKS_ON` | Cùng dấu hai chấm nhưng nằm ở **node** hay **relationship**. | Label trong `(...)`, type trong `[...]`. |
| Dùng `length(path)` để đếm node | `length` đếm relationship. | Dùng `size(nodes(path))` khi muốn số node trên path. |
| Tưởng `-[:KNOWS]-` tạo quan hệ vô hướng | Mẫu đọc không yêu cầu chiều, nhưng dữ liệu vẫn có hướng. | Chỉ rõ mũi tên khi ghi hoặc khi ý nghĩa nghiệp vụ cần chiều. |

Một trường hợp khác cần lưu ý: nếu `(a)-[:KNOWS]->(b)` khớp ba quan hệ, kết quả có thể có **ba dòng** cho cùng một node `a`. Mẫu là điều kiện ghép, không mặc định gom một dòng cho mỗi người. Hãy dùng `RETURN DISTINCT a` hoặc tổng hợp khi thật sự muốn loại trùng.

## 13. Bài tập thực hành

Thực hiện trên đồ thị mẫu ở mục 4. Với bài có ID, hãy giữ đúng tiền tố `cypher003-`.

### Bài 1. Từ sơ đồ sang câu truy vấn

Viết câu truy vấn tìm người mà An có relationship `KNOWS` đi đến; trả tên người đích.

<details>
<summary>Đáp án gợi ý</summary>

```cypher
MATCH (an:Person {id: 'cypher003-an'})-[:KNOWS]->(friend:Person)
RETURN friend.name AS ban;
```

Kết quả: **Bình**.

</details>

### Bài 2. Đảo vị trí node nhưng giữ nguyên hướng

Tìm người **có relationship KNOWS đi tới Chi**. Hãy đặt node Chi ở **bên trái** của mẫu.

<details>
<summary>Đáp án gợi ý</summary>

```cypher
MATCH (chi:Person {id: 'cypher003-chi'})<-[:KNOWS]-(p:Person)
RETURN p.name AS nguoiBietChi;
```

Kết quả: **Bình**.

</details>

### Bài 3. Đọc thuộc tính của relationship

Tìm vai trò của An trong dự án Graph API. Trả tên dự án và thuộc tính `role` từ relationship.

<details>
<summary>Đáp án gợi ý</summary>

```cypher
MATCH (an:Person {id: 'cypher003-an'})
      -[w:WORKS_ON]->(pr:Project {id: 'cypher003-api'})
RETURN pr.name AS duAn, w.role AS vaiTro;
```

Kết quả: **Graph API – lead**.

</details>

### Bài 4. Hai bước liên tiếp

Tìm người có thể đến từ An qua **đúng hai** cạnh `KNOWS`. Trả tên đích và số cạnh của path.

<details>
<summary>Đáp án gợi ý</summary>

```cypher
MATCH journey = (an:Person {id: 'cypher003-an'})
                -[:KNOWS]->(:Person)
                -[:KNOWS]->(destination:Person)
RETURN destination.name AS dich, length(journey) AS soCanh;
```

Kết quả: **Chi – 2**.

</details>

### Bài 5. Quan hệ không tồn tại

Chi không tham gia dự án nào trong đồ thị mẫu. Viết câu truy vấn trả **vẫn một dòng cho Chi** và tên dự án bằng `null`.

<details>
<summary>Đáp án gợi ý</summary>

```cypher
MATCH (chi:Person {id: 'cypher003-chi'})
OPTIONAL MATCH (chi)-[:WORKS_ON]->(pr:Project)
RETURN chi.name AS ten, pr.name AS duAn;
```

Kết quả: **Chi – null**.

</details>

### Bài 6. Tìm hoặc tạo quan hệ có hướng

Viết câu truy vấn bảo đảm có quan hệ `COLLABORATES_WITH` **từ Chi đến An**, nhưng không cố ý tạo thêm cạnh trùng mỗi lần chạy.

<details>
<summary>Đáp án gợi ý</summary>

```cypher
MATCH (chi:Person {id: 'cypher003-chi'})
MATCH (an:Person {id: 'cypher003-an'})
MERGE (chi)-[:COLLABORATES_WITH]->(an);
```

Hai node được tìm trước, sau đó `MERGE` kiểm tra hoặc tạo relationship có type và hướng được yêu cầu.

</details>

## 14. Tóm tắt kiến thức

Để đọc mẫu Neo4j/Cypher, hãy tách cấu trúc thành ba lớp:

- `(p:Person {id: '...'})` nói về **node**: biến, label và thuộc tính.
- `-[r:KNOWS {since: 2021}]->` nói về **relationship**: biến, type, thuộc tính và chiều.
- Việc lặp các cặp `(...)` và `-[...]->` diễn tả **hình dạng kết nối**: một cạnh, chuỗi nhiều cạnh hoặc các nhánh chung node.

Sơ đồ đọc và câu Cypher luôn phải giữ đúng quan hệ nghiệp vụ. `MATCH` tìm những mẫu đang có; `OPTIONAL MATCH` cho phép thiếu một phần kết nối; `CREATE` tạo mới; `MERGE` tìm hoặc tạo theo mẫu. Khi đã tự đọc và viết đúng các dấu ngoặc, mũi tên và nhãn, bạn có nền tảng để truy vấn quan hệ nhiều bước, đánh giá số dòng kết quả, xây index/constraint và kết nối Neo4j với ứng dụng Java.

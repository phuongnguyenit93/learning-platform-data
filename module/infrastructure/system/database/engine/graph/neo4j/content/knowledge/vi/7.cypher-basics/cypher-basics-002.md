# Khai báo biến cho nút, quan hệ và đường đi trong Cypher

> **Chương:** Nền tảng Cypher  
> **Phạm vi:** Neo4j sử dụng mô hình *property graph*: các nút (*node*) có label và thuộc tính; các quan hệ (*relationship*) có hướng, type và thuộc tính. Bài này giải thích cách **đặt tên, ràng buộc và sử dụng biến** trong câu truy vấn Cypher để truy cập nút, quan hệ và toàn bộ đường đi.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Khai báo và dùng biến cho node, relationship và path trong các mẫu Cypher.
- Phân biệt **tên biến** với **label**, **relationship type** và **tên thuộc tính**.
- Truy cập thuộc tính nút và quan hệ, cũng như thao tác trên đường đi bằng các hàm Cypher.
- Hiểu biến được ràng buộc theo **từng dòng kết quả**, khác với biến kiểu gán giá trị trong ngôn ngữ lập trình thông thường.
- Kiểm soát phạm vi biến giữa `MATCH`, `OPTIONAL MATCH`, `WITH` và `RETURN`.
- Tránh các lỗi phổ biến khi sử dụng lại biến, đặt tên biến, duyệt nhiều quan hệ và xử lý `null`.

## 2. Biến trong Cypher là gì?

Trong Java, ta thường thấy cách khai báo `Person person = ...`. Trong Cypher, không có câu lệnh `var person` tương ứng cho các thực thể đồ thị. **Biến được giới thiệu khi mẫu truy vấn hoặc mệnh đề ràng buộc nó với một giá trị**.

Ví dụ:

```cypher
MATCH (person:Person)
RETURN person;
```

`person` là **biến** biểu diễn một nút `Person` ở mỗi dòng khớp; `Person` là **label** được lưu trên nút. Mỗi dòng có thể chứa một nút `person` khác nhau.

Một mẫu đầy đủ:

```cypher
MATCH route = (person:Person)-[link:KNOWS]->(friend:Person)
RETURN person, link, friend, route;
```

| Thành phần | Loại | Vai trò |
|---|---|---|
| `person` | Biến node | Tham chiếu đến nút bắt đầu của mẫu. |
| `Person` | Label | Điều kiện về nhãn của nút; không phải tên biến. |
| `link` | Biến relationship | Tham chiếu đến quan hệ đang nối hai nút. |
| `KNOWS` | Relationship type | Điều kiện về loại quan hệ; không phải tên biến. |
| `friend` | Biến node | Tham chiếu đến nút đích theo chiều mũi tên. |
| `route` | Biến path | Tham chiếu đến **toàn bộ đường đi đã khớp**, gồm các node và relationship theo thứ tự. |

```text
route = toàn bộ đường đi
  ┌────────────────────────────────────────────┐
  │                                            │
  (person:Person)-[link:KNOWS]->(friend:Person)
       nút             quan hệ         nút
  └────────────────────────────────────────────┘
```

Trong lời giải thích dưới đây, **ràng buộc biến** nghĩa là tìm được thực thể hoặc giá trị ứng với tên biến ở một dòng kết quả. Biến giúp các mệnh đề sau tham chiếu lại đúng thực thể đó.

## 3. Dựng đồ thị mẫu để thực hành

Chạy dữ liệu mẫu trong **database thực hành riêng**. Nhờ `MERGE`, chạy lại cùng khối lệnh sẽ tìm các nút và quan hệ phù hợp trước khi tạo thêm; dữ liệu mẫu giả định chưa có các thực thể trùng ID và các quan hệ tương ứng.

```cypher
MERGE (an:Person {id: 'p1'})
SET an.name = 'An', an.city = 'Hà Nội'

MERGE (binh:Person {id: 'p2'})
SET binh.name = 'Bình', binh.city = 'Hà Nội'

MERGE (chi:Person {id: 'p3'})
SET chi.name = 'Chi', chi.city = 'TP. Hồ Chí Minh'

MERGE (dung:Person {id: 'p4'})
SET dung.name = 'Dũng', dung.city = 'Đà Nẵng'

MERGE (api:Project {id: 'pr1'})
SET api.name = 'Graph API'

MERGE (an)-[anBinh:KNOWS]->(binh)
SET anBinh.since = 2021

MERGE (binh)-[binhChi:KNOWS]->(chi)
SET binhChi.since = 2023

MERGE (an)-[anApi:WORKS_ON]->(api)
SET anApi.role = 'lead';
```

Đồ thị dùng trong các ví dụ:

```text
(An:Person {id:'p1'})
   │
   ├──[KNOWS {since:2021}]──> (Bình:Person {id:'p2'})
   │                                  │
   │                                  └──[KNOWS {since:2023}]──> (Chi:Person {id:'p3'})
   │
   └──[WORKS_ON {role:'lead'}]──> (Graph API:Project {id:'pr1'})

(Dũng:Person {id:'p4'})  -- không có quan hệ trong mẫu
```

Các bảng kết quả trong bài giả định chỉ có đồ thị mẫu này. Nếu database đã chứa thêm node hoặc relationship, kết quả của truy vấn không lọc ID có thể khác.

## 4. Khai báo và dùng biến cho nút (node)

Một biến node nằm trong cặp ngoặc tròn `(...)`:

```cypher
MATCH (p:Person {id: 'p1'})
RETURN p;
```

Ở đây `p` được ràng buộc vào nút có label `Person`, thuộc tính `id = 'p1'`. `RETURN p` trả về **nút**, bao gồm định danh đồ thị, label và các thuộc tính mà công cụ hiển thị có thể dùng để trực quan hóa.

Để lấy **giá trị thuộc tính**, dùng dấu chấm:

```cypher
MATCH (p:Person {id: 'p1'})
RETURN p.name AS ten, p.city AS thanhPho;
```

Kết quả là `An` và `Hà Nội`. Tên `p` do người viết truy vấn đặt, còn `name` và `city` là tên các thuộc tính có trên nút. Một node không có thuộc tính được yêu cầu sẽ cho giá trị `null` khi truy cập thuộc tính đó.

### 4.1. Label không phải biến

Hai mẫu sau có ý nghĩa khác nhau:

```cypher
MATCH (member:Person)
RETURN member.name AS ten;
```

```cypher
MATCH (Person)
RETURN Person;
```

- Trong ví dụ đầu, `member` là biến, `Person` là label.
- Trong ví dụ sau, `Person` **chỉ là tên biến** vì không có dấu hai chấm; mẫu này không giới hạn node theo label và có thể khớp cả các node `Project`.

Vì vậy hãy dùng `(p:Person)` khi muốn lọc theo label `Person`. Với node không cần tham chiếu về sau, có thể bỏ tên biến:

```cypher
MATCH (:Person)-[:WORKS_ON]->(pr:Project)
RETURN pr.name AS duAn;
```

`(:Person)` là nút có label `Person` nhưng **không đặt tên biến** cho nút đó; `pr` vẫn là biến node để trả kết quả.

### 4.2. Một biến được dùng lại là cùng một nút trong một dòng

```cypher
MATCH (p:Person {id: 'p1'})
MATCH (p)-[:KNOWS]->(f:Person)
RETURN p.name AS nguoi, f.name AS ban;
```

Ở `MATCH` thứ hai, `p` đã được ràng buộc từ `MATCH` thứ nhất. Nó vẫn chỉ đến **nút An**, không trở thành một biến mới hay một node tùy ý. Biến `f` là node đích của quan hệ `KNOWS`.

Kết quả: **An – Bình**.

Nếu cần làm việc với **hai người độc lập**, dùng hai biến khác nhau và diễn đạt rõ điều kiện liên hệ:

```cypher
MATCH (a:Person {id: 'p1'}), (b:Person {id: 'p2'})
RETURN a.name AS nguoiA, b.name AS nguoiB;
```

Với ID xác định, ví dụ chỉ có một cặp. Tuy nhiên, khi viết `MATCH (a:Person), (b:Person)` mà không có điều kiện nối, Neo4j có thể tạo tích Descartes, số dòng tăng rất nhanh.

## 5. Khai báo và dùng biến cho quan hệ (relationship)

Biến relationship nằm trong cặp ngoặc vuông `[...]`:

```cypher
MATCH (a:Person {id: 'p1'})-[r:KNOWS]->(b:Person)
RETURN a.name AS nguoi,
       b.name AS ban,
       r.since AS quenTuNam;
```

Trong mẫu `-[r:KNOWS]->`:

- `r` là **biến relationship**.
- `KNOWS` là **relationship type**.
- Mũi tên `->` yêu cầu mẫu đi từ `a` đến `b` theo chiều lưu trữ của quan hệ.
- `r.since` đọc thuộc tính `since` trên quan hệ, tương tự `a.name` đọc thuộc tính nút.

Kết quả: **An – Bình – 2021**.

Bạn có thể trả về chính relationship và khai thác thông tin của nó:

```cypher
MATCH (a:Person {id: 'p1'})-[rel:KNOWS]->(b:Person)
RETURN rel,
       type(rel) AS loaiQuanHe,
       properties(rel) AS thuocTinh,
       startNode(rel).name AS nutDau,
       endNode(rel).name AS nutCuoi;
```

Các hàm trên lần lượt trả relationship, type, bản đồ thuộc tính, nút bắt đầu và nút kết thúc **theo chiều được lưu trên relationship**.

### 5.1. Hướng quan hệ và cách đặt tên biến

```cypher
// Đi theo chiều lưu trữ: An -> Bình
MATCH (a:Person {id: 'p1'})-[r:KNOWS]->(b:Person)
RETURN a.name, b.name;
```

```cypher
// Đi ngược lại chiều lưu trữ: tìm ai biết Chi
MATCH (target:Person {id: 'p3'})<-[r:KNOWS]-(source:Person)
RETURN source.name AS nguoiBietChi, target.name AS chi;
```

```cypher
// Khớp quan hệ theo cả hai hướng
MATCH (a:Person {id: 'p2'})-[r:KNOWS]-(other:Person)
RETURN other.name AS nguoiLienQuan, type(r) AS loai;
```

Ví dụ thứ ba có thể trả **An** và **Chi**, bởi Bình là đích của một quan hệ `KNOWS` và là nguồn của quan hệ `KNOWS` khác. Cú pháp `-[r:KNOWS]-` không yêu cầu một hướng cụ thể; **biến `r` vẫn chỉ đúng relationship đã khớp**, với hướng lưu trữ của nó.

### 5.2. Không cần dùng biến cho mọi quan hệ

Nếu chỉ muốn kiểm tra sự tồn tại và lấy tên người:

```cypher
MATCH (a:Person {id: 'p1'})-[:KNOWS]->(b:Person)
RETURN b.name AS ban;
```

Không có biến relationship vì truy vấn không dùng lại đối tượng quan hệ. Khi cần đọc thuộc tính, type, node đầu/cuối của relationship hay giữ quan hệ ở giai đoạn tiếp theo, hãy đặt một biến như `r`.

### 5.3. Một mẫu có thể khớp nhiều quan hệ

```cypher
MATCH (a:Person)-[r:KNOWS]->(b:Person)
RETURN a.name AS nguoi, b.name AS ban, r.since AS tuNam
ORDER BY tuNam;
```

Đồ thị mẫu có hai quan hệ `KNOWS` nên trả **hai dòng**: An – Bình – 2021 và Bình – Chi – 2023. Biến `a`, `r` và `b` là các giá trị **theo từng dòng**, không phải một biến toàn cục chỉ lưu quan hệ cuối cùng.

## 6. Khai báo và dùng biến cho đường đi (path)

Một **đường đi** là chuỗi node và relationship nối nhau. Để đặt tên cho toàn bộ đường đi, dùng dạng:

```cypher
MATCH pathVariable = (startNode)-[relationship]->(endNode)
RETURN pathVariable;
```

Trong một truy vấn thật, ta có thể đặt tên `route`:

```cypher
MATCH route = (an:Person {id: 'p1'})
              -[r1:KNOWS]->(binh:Person)
              -[r2:KNOWS]->(chi:Person)
RETURN route;
```

`route` đại diện cho toàn bộ đoạn **An → Bình → Chi**, còn `an`, `binh`, `chi` là các biến node; `r1` và `r2` là các biến relationship. Đặt biến đường đi không tạo thêm node hay relationship trong database; nó chỉ gắn tên cho **kết quả khớp của mẫu**.

### 6.1. Các hàm thường dùng với path

| Biểu thức | Kết quả | Trong ví dụ An → Bình → Chi |
|---|---|---|
| `route` | Giá trị đường đi, gồm node và relationship. | Đường đi An → Bình → Chi. |
| `nodes(route)` | Danh sách các node theo thứ tự đường đi. | Node An, Bình, Chi. |
| `relationships(route)` | Danh sách các relationship theo thứ tự đường đi. | Quan hệ An→Bình, Bình→Chi. |
| `length(route)` | Độ dài đường đi tính bằng **số relationship**. | `2`. |
| `[n IN nodes(route) \| n.name]` | Danh sách tên node theo thứ tự. | `['An', 'Bình', 'Chi']`. |
| `[r IN relationships(route) \| r.since]` | Danh sách giá trị `since` của từng quan hệ. | `[2021, 2023]`. |

Ví dụ chạy được:

```cypher
MATCH route = (a:Person {id: 'p1'})
              -[:KNOWS]->(:Person)
              -[:KNOWS]->(c:Person)
RETURN length(route) AS soCanh,
       [n IN nodes(route) | n.name] AS cacNut,
       [r IN relationships(route) | type(r)] AS cacLoaiQuanHe,
       [r IN relationships(route) | r.since] AS cacNamBatDau,
       c.name AS nutCuoi;
```

Kết quả:

| soCanh | cacNut | cacLoaiQuanHe | cacNamBatDau | nutCuoi |
|---:|---|---|---|---|
| 2 | `['An', 'Bình', 'Chi']` | `['KNOWS', 'KNOWS']` | `[2021, 2023]` | Chi |

Lưu ý: `length(route)` đếm số cạnh, không đếm số nút. Với đường đi hai cạnh ở ví dụ, `nodes(route)` có ba phần tử.

### 6.2. Đường đi có số bước thay đổi

Đường đi không nhất thiết có số cạnh cố định. Trên các phiên bản Neo4j hỗ trợ **quantified relationships** (từ Cypher/Neo4j 5.9), có thể viết:

```cypher
MATCH route = (start:Person {id: 'p1'})
              -[:KNOWS]->{1,2}
              (destination:Person)
RETURN destination.name AS dich,
       length(route) AS soBuoc,
       [n IN nodes(route) | n.name] AS cacNut
ORDER BY soBuoc;
```

`{1,2}` yêu cầu đi theo từ một đến hai quan hệ `KNOWS`. Với đồ thị mẫu, ta nhận:

| dich | soBuoc | cacNut |
|---|---:|---|
| Bình | 1 | `['An', 'Bình']` |
| Chi | 2 | `['An', 'Bình', 'Chi']` |

Trong các tài liệu Cypher cũ, bạn có thể thấy cú pháp độ dài thay đổi như `-[:KNOWS*1..2]->`. Cú pháp định lượng và kiểu biến nhóm có thay đổi theo phiên bản, vì vậy hãy kiểm tra phiên bản Neo4j đang sử dụng trước khi sao chép các truy vấn duyệt nhiều bước. Với mệnh đề trên, `route` vẫn là một **path**, còn `destination` là node đích của từng kết quả.

### 6.3. Path không giống relationship

`r` trong `-[r:KNOWS]->` luôn trỏ tới **một relationship đã khớp** ở mẫu một bước. Trong khi đó, `route` có thể bao gồm **nhiều relationship và nhiều node**.

Ví dụ, `type(r)` nhận relationship, không nhận toàn bộ path. Muốn lấy type của mọi cạnh trên path, dùng:

```cypher
MATCH route = (a:Person {id: 'p1'})-[:KNOWS]->(:Person)-[:KNOWS]->(:Person)
RETURN [r IN relationships(route) | type(r)] AS cacType;
```

Các hàm `nodes(route)` và `relationships(route)` trả về **list**. Từ đó có thể dùng list comprehension, `UNWIND` hoặc các hàm trên list để tiếp tục xử lý dữ liệu.

## 7. Phạm vi biến: từ `MATCH` qua `WITH` đến `RETURN`

Biến chỉ tồn tại trong **phạm vi truy vấn** nơi nó đã được ràng buộc và còn được chuyển tiếp. Trong cùng một phần truy vấn, `MATCH` sau có thể dùng biến đã biết:

```cypher
MATCH (an:Person {id: 'p1'})
MATCH (an)-[friendship:KNOWS]->(friend:Person)
MATCH (an)-[assignment:WORKS_ON]->(project:Project)
RETURN an.name AS nguoi,
       friend.name AS ban,
       project.name AS duAn,
       friendship.since AS quenTu,
       assignment.role AS vaiTro;
```

Ở mỗi `MATCH` sau, `an` vẫn chỉ An. Các biến `friendship`, `friend`, `assignment` và `project` được ràng buộc thêm. Nếu An có nhiều bạn và nhiều dự án, ghép các kết quả có thể tạo **nhiều tổ hợp dòng**, nên cần cân nhắc việc gom nhóm hoặc tách giai đoạn.

### 7.1. `WITH` chuyển tiếp biến đã chọn

```cypher
MATCH route = (a:Person {id: 'p1'})-[r:KNOWS]->(b:Person)
WITH b, route
RETURN b.name AS ban,
       length(route) AS soCanh,
       [n IN nodes(route) | n.name] AS cacNut;
```

Sau `WITH b, route`, chỉ `b` và `route` còn trong phạm vi tiếp theo. Các biến `a` và `r` không được chuyển tiếp. Tuy nhiên, ta vẫn có thể truy cập các node và relationship **thông qua giá trị `route`** bằng `nodes(route)` và `relationships(route)`.

Ví dụ **không hợp lệ**:

```cypher
// Lỗi: rel đã ra khỏi phạm vi sau WITH
MATCH (a:Person {id: 'p1'})-[rel:KNOWS]->(b:Person)
WITH b
RETURN rel.since AS quenTu;
```

Phiên bản đúng:

```cypher
MATCH (a:Person {id: 'p1'})-[rel:KNOWS]->(b:Person)
WITH b, rel
RETURN b.name AS ban, rel.since AS quenTu;
```

### 7.2. Đặt bí danh có thể thay đổi tên biến được dùng tiếp

```cypher
MATCH (p:Person {id: 'p1'})
WITH p AS person
RETURN person.name AS ten;
```

Ở giai đoạn `RETURN`, tên `person` có hiệu lực; tên `p` không còn được đưa qua `WITH`. Tương tự, bạn có thể chuyển **giá trị thuộc tính**:

```cypher
MATCH (p:Person {id: 'p1'})
WITH p.name AS ten, p.city AS thanhPho
RETURN ten, thanhPho;
```

Trong truy vấn này, `ten` và `thanhPho` là các giá trị scalar (chuỗi), **không phải biến node**. Vì vậy viết `ten.city` sẽ không có nghĩa là truy cập thuộc tính của nút `Person`.

### 7.3. Biến của đường đi qua nhiều giai đoạn

```cypher
MATCH route = (a:Person {id: 'p1'})-[:KNOWS]->(b:Person)-[:KNOWS]->(c:Person)
WITH route, c
WHERE length(route) >= 2
RETURN c.name AS dich,
       [n IN nodes(route) | n.name] AS cacNut;
```

`route` được giữ qua `WITH` và vẫn có thể dùng trong `WHERE`/`RETURN`. Ngược lại, nếu viết `WITH c`, biến `route` sẽ không còn khả dụng cho các mệnh đề kế tiếp.

## 8. `OPTIONAL MATCH` và biến có giá trị `null`

`MATCH` bắt buộc mẫu phải khớp. `OPTIONAL MATCH` cho phép giữ dòng đầu vào kể cả khi không có quan hệ tương ứng; các biến **mới** từ mẫu không khớp nhận `null`.

```cypher
MATCH (p:Person)
OPTIONAL MATCH route = (p)-[work:WORKS_ON]->(project:Project)
RETURN p.name AS nhanSu,
       project.name AS duAn,
       work.role AS vaiTro,
       coalesce(length(route), 0) AS soCanh
ORDER BY nhanSu;
```

Trong đồ thị mẫu:

| nhanSu | duAn | vaiTro | soCanh |
|---|---|---|---:|
| An | Graph API | lead | 1 |
| Bình | `null` | `null` | 0 |
| Chi | `null` | `null` | 0 |
| Dũng | `null` | `null` | 0 |

`p` vẫn có giá trị vì đã được `MATCH` ràng buộc từ trước. Nhưng nếu không có quan hệ `WORKS_ON`, các biến mới `work`, `project` và `route` nhận `null`. Hàm `coalesce` trả về biểu thức khác `null` đầu tiên, nên `coalesce(length(route), 0)` biểu diễn trường hợp không có đường đi bằng 0.

Một lỗi dễ gặp là yêu cầu `work.role = 'lead'` ở `WHERE` sau `WITH` rồi vô tình loại các nhân sự không tham gia dự án. Nếu mục đích là **giữ mọi người và chỉ tìm quan hệ có vai trò lead**, gắn điều kiện cho `OPTIONAL MATCH`:

```cypher
MATCH (p:Person)
OPTIONAL MATCH (p)-[work:WORKS_ON]->(project:Project)
WHERE work.role = 'lead'
RETURN p.name AS nhanSu, project.name AS duAnLead
ORDER BY nhanSu;
```

Trong trường hợp đó mọi `p` vẫn có dòng; `project` là `null` khi không tìm thấy quan hệ có `role = 'lead'`.

## 9. Quy tắc đặt tên biến và cách đọc cú pháp

### 9.1. Quy tắc thực tế

- Dùng tên có nghĩa: `person`, `colleague`, `worksOn`, `route`; khi truy vấn ngắn, `p`, `r`, `path` cũng phù hợp.
- Tên biến **phân biệt chữ hoa và chữ thường**: `person` và `Person` là hai tên khác nhau.
- Tên đơn giản nên bắt đầu bằng chữ cái, sau đó dùng chữ cái, chữ số hoặc dấu gạch dưới; không dùng khoảng trắng hay ký tự đặc biệt khi không cần thiết.
- Cypher hỗ trợ tên được bao bằng dấu backtick nếu cần ký tự đặc biệt, nhưng tên dễ đọc và nhất quán thường thuận tiện hơn.
- Không dùng cùng một tên để cố gắng biểu diễn những đối tượng khác loại trong cùng một phạm vi; hãy dùng `p` cho node, `r` cho relationship, `route` cho path nếu muốn dễ quan sát.

Ví dụ:

```cypher
MATCH (staffMember:Person)-[knowsRelationship:KNOWS]->(knownPerson:Person)
RETURN staffMember.name AS nguoi,
       knownPerson.name AS nguoiDuocBiet,
       knowsRelationship.since AS tuNam;
```

### 9.2. Phân biệt các thành phần dễ nhầm

| Cú pháp | Ý nghĩa |
|---|---|
| `(p)` | Node gán biến `p`, chưa lọc theo label. |
| `(p:Person)` | Node `p` bắt buộc có label `Person`. |
| `(:Person)` | Node có label `Person`, không tạo biến node. |
| `(p {id: 'p1'})` | Node gán biến `p`, lọc thuộc tính `id`. |
| `[r]` | Relationship gán biến `r`, chưa lọc type. |
| `[r:KNOWS]` | Relationship `r` phải có type `KNOWS`. |
| `[:KNOWS]` | Relationship có type `KNOWS`, không tạo biến relationship. |
| `route = (...)-->(...)` | Gán tên `route` cho path khớp mẫu. |
| `p.name` | Truy cập thuộc tính `name` của node/giá trị đồ thị `p`. |
| `$personId` | Tham số do bên gọi truyền vào, không phải biến node/relationship/path. |

### 9.3. Biến và tham số là hai khái niệm khác nhau

```cypher
MATCH (p:Person)
WHERE p.id = $personId
RETURN p.name AS ten;
```

`p` là biến node gắn với các nút khớp; `$personId` là **tham số đầu vào**, chẳng hạn chuỗi `'p1'` do Neo4j Browser, Java Driver hoặc Spring Data Neo4j truyền khi chạy truy vấn. Tham số phù hợp để truyền **giá trị dữ liệu** và giúp tránh ghép chuỗi truy vấn từ đầu vào người dùng.

Để chạy ví dụ mà không cần thiết lập tham số, có thể thay `$personId` bằng chuỗi `'p1'`. Trong ứng dụng, hãy ưu tiên truyền giá trị qua tham số.

Tên biến hoặc cấu trúc mẫu đồ thị không tự động được thay thế bằng một tham số chứa chuỗi như `'p'` hoặc `'KNOWS'`. Khi cần chọn label, type hay cấu trúc mẫu linh hoạt, phải dùng cú pháp được phiên bản Cypher hỗ trợ và thiết kế việc xác thực đầu vào phù hợp.

## 10. Biến, số dòng kết quả và sự trùng lặp

Đặt tên biến giúp truy vấn tham chiếu đến thực thể nhưng **không tự làm kết quả trở nên duy nhất**. Ví dụ:

```cypher
MATCH (p:Person)-[r:KNOWS]->(friend:Person)
RETURN p.name AS nguoi, friend.name AS ban;
```

Đồ thị có hai quan hệ `KNOWS` nên có hai dòng; biến `p` và `friend` có thể mang giá trị khác nhau trên từng dòng.

Nếu một node có ba quan hệ `KNOWS` đi ra, truy vấn mở rộng từ node đó có thể tạo ba dòng cho cùng một biến node `p`. Muốn trả **danh sách người không lặp**:

```cypher
MATCH (p:Person)-[:KNOWS]->(:Person)
RETURN DISTINCT p.name AS nguoi;
```

Muốn đếm quan hệ thay vì đếm tên node:

```cypher
MATCH (p:Person)
OPTIONAL MATCH (p)-[r:KNOWS]->(:Person)
RETURN p.name AS nguoi, count(r) AS soQuanHeDiRa
ORDER BY nguoi;
```

Kết quả trong đồ thị mẫu là An 1, Bình 1, Chi 0 và Dũng 0. `count(r)` bỏ qua `null` do `OPTIONAL MATCH` tạo ra; `count(*)` sẽ đếm cả dòng được giữ khi không khớp quan hệ.

Đối với số node hay relationship duy nhất sau các lần mở rộng, có thể dùng `count(DISTINCT p)` hoặc `count(DISTINCT r)` phù hợp mục đích. Không nên dùng `DISTINCT` chỉ để che đi truy vấn nối mẫu sai.

## 11. Một truy vấn tổng hợp: node, relationship và path cùng phối hợp

Yêu cầu: **Từ An, tìm người quen thông qua đúng hai quan hệ `KNOWS`, trả tên người đầu/giữa/cuối, năm bắt đầu của từng quan hệ và độ dài đường đi.**

```cypher
MATCH route = (source:Person {id: 'p1'})
              -[firstLink:KNOWS]->(middle:Person)
              -[secondLink:KNOWS]->(destination:Person)
WITH source, middle, destination, firstLink, secondLink, route
RETURN source.name AS batDau,
       middle.name AS trungGian,
       destination.name AS ketThuc,
       firstLink.since AS canhDauTuNam,
       secondLink.since AS canhSauTuNam,
       length(route) AS soBuoc,
       [n IN nodes(route) | n.name] AS thuTuNut;
```

| batDau | trungGian | ketThuc | canhDauTuNam | canhSauTuNam | soBuoc | thuTuNut |
|---|---|---|---:|---:|---:|---|
| An | Bình | Chi | 2021 | 2023 | 2 | `['An', 'Bình', 'Chi']` |

Cách đọc truy vấn:

1. `source` được ràng buộc với nút An nhờ điều kiện `id = 'p1'`.
2. `firstLink` là quan hệ `KNOWS` từ An đến `middle` (Bình).
3. `secondLink` là quan hệ `KNOWS` từ Bình đến `destination` (Chi).
4. `route` là **một path** chứa cả ba node và hai relationship.
5. `WITH` chủ động chuyển tiếp các biến cần thiết.
6. `RETURN` lấy thuộc tính của các node/relationship và tính độ dài của path.

Đây là nền tảng để mở rộng sang truy vấn đường đi nhiều bước, phân tích phụ thuộc, gợi ý kết nối hoặc tìm thành phần liên quan trong hệ thống dữ liệu liên kết.

## 12. Các lỗi thường gặp

| Vấn đề | Ví dụ/Nguyên nhân | Cách xử lý |
|---|---|---|
| Nhầm label thành tên biến | `MATCH (Person)` chỉ đặt tên biến `Person`. | Viết `MATCH (p:Person)` để lọc label. |
| Nhầm type thành tên biến | `-[KNOWS]->` đặt tên biến `KNOWS`, không lọc type. | Viết `-[:KNOWS]->` hoặc `-[r:KNOWS]->`. |
| Sử dụng biến chưa khai báo | `RETURN r.since` nhưng mẫu không gán `r`. | Khai báo `[r:KNOWS]` hoặc dùng đúng biến đã có. |
| Biến bị mất sau `WITH` | `WITH p` rồi `RETURN r`. | Thêm `r` vào `WITH` nếu còn cần. |
| Đọc path như relationship | Gọi `type(route)` khi `route` là path. | Dùng `relationships(route)`, rồi duyệt từng relationship. |
| Sai số bước đường đi | Xem `length(route)` là số nút. | Đếm cạnh; node được lấy bằng `nodes(route)`. |
| Bỏ sót đối tượng chưa có liên kết | Dùng `MATCH` để truy vấn quan hệ bắt buộc. | Dùng `OPTIONAL MATCH` nếu cần giữ đối tượng không khớp. |
| Lặp dòng hoặc tăng đột biến | Một node khớp nhiều cạnh hoặc hai mẫu không liên hệ bị nhân tổ hợp. | Xem lại pattern, số nhánh khớp, `DISTINCT` và phép gom nhóm. |
| Đặt sai hướng | Chỉ viết `->` khi dữ liệu lưu quan hệ theo chiều ngược. | Dùng `<-` hoặc mẫu vô hướng `-[]-` nếu phù hợp yêu cầu. |
| Nhầm biến với tham số | Dùng `$p` với ý định trỏ tới node đã khớp. | Dùng `p` cho biến trong truy vấn; dùng `$id` cho giá trị truyền vào. |

## 13. Bài tập tự luyện

### Bài 1. Biến node và thuộc tính

Tìm nút có `id = 'p2'`, đặt biến `person` và trả tên cùng thành phố.

<details>
<summary>Đáp án tham khảo</summary>

```cypher
MATCH (person:Person {id: 'p2'})
RETURN person.name AS ten, person.city AS thanhPho;
```

Kết quả: **Bình – Hà Nội**.

</details>

### Bài 2. Biến relationship và hướng

Tìm người có quan hệ `KNOWS` đi tới Chi; trả tên người đó và thuộc tính `since` của relationship.

<details>
<summary>Đáp án tham khảo</summary>

```cypher
MATCH (chi:Person {id: 'p3'})<-[relation:KNOWS]-(p:Person)
RETURN p.name AS nguoiBietChi, relation.since AS tuNam;
```

Kết quả: **Bình – 2023**.

</details>

### Bài 3. Biến path và danh sách node

Từ An, tìm đường đi đúng hai quan hệ `KNOWS`, đặt biến `journey` và trả độ dài đường đi cùng danh sách tên các node.

<details>
<summary>Đáp án tham khảo</summary>

```cypher
MATCH journey = (p:Person {id: 'p1'})
                -[:KNOWS]->(:Person)
                -[:KNOWS]->(destination:Person)
RETURN destination.name AS dich,
       length(journey) AS soBuoc,
       [n IN nodes(journey) | n.name] AS cacNut;
```

Kết quả: **Chi**, độ dài **2**, danh sách `['An', 'Bình', 'Chi']`.

</details>

### Bài 4. Phạm vi biến sau `WITH`

Vì sao câu truy vấn sau lỗi? Hãy sửa để trả tên và năm quen biết.

```cypher
// Truy vấn cố ý có lỗi
MATCH (a:Person {id: 'p1'})-[r:KNOWS]->(b:Person)
WITH b
RETURN b.name AS ban, r.since AS tuNam;
```

<details>
<summary>Đáp án tham khảo</summary>

`r` không được truyền qua `WITH` nên nằm ngoài phạm vi ở `RETURN`.

```cypher
MATCH (a:Person {id: 'p1'})-[r:KNOWS]->(b:Person)
WITH b, r
RETURN b.name AS ban, r.since AS tuNam;
```

</details>

## 14. Ghi nhớ

Biến trong Cypher dùng để **đặt tên và tham chiếu đến dữ liệu đã khớp của từng dòng**:

- `(p:Person)`: `p` là **node**, `Person` là **label**.
- `-[r:KNOWS]->`: `r` là **relationship**, `KNOWS` là **type**.
- `MATCH route = (...)-->(...)`: `route` là **path**, có thể xem node và relationship theo thứ tự bằng `nodes(route)`, `relationships(route)` và `length(route)`.
- `WITH` quyết định biến nào còn dùng được ở phần truy vấn tiếp theo.
- `OPTIONAL MATCH` có thể gán `null` cho biến mới khi không khớp, vì vậy cần xét kỹ các hàm và điều kiện lọc.

Hiểu rõ cách ràng buộc và truyền biến là tiền đề để viết các truy vấn Cypher phức tạp, duyệt đường đi, kiểm soát số dòng trung gian và tiếp tục học tối ưu truy vấn Neo4j, Java Driver hoặc Spring Data Neo4j.

# Theo dõi số hàng khi mở rộng danh sách và ghép nhiều mẫu trong Cypher

Trong Neo4j, một truy vấn Cypher xử lý **luồng hàng** (row stream). Mỗi hàng chứa các biến đang được ràng buộc, chẳng hạn `p`, `skill`, `project` và `tag`. Khi dùng `UNWIND` để mở rộng danh sách hoặc `MATCH` để ghép thêm mẫu đồ thị, **một hàng đầu vào có thể tạo nhiều hàng đầu ra, một hàng hoặc không hàng nào**. Hiểu sự thay đổi này giúp truy vấn đúng nghĩa, tránh đếm trùng và kiểm soát chi phí thực thi.

Bài học thuộc chương **Danh sách và luồng dữ liệu**, tập trung vào việc theo dõi *cardinality* (số hàng trung gian) khi truy vấn các node, relationship và đường liên kết trong property graph Neo4j. Các ví dụ sử dụng Cypher, phù hợp cả khi về sau đọc kết quả bằng Neo4j Java Driver hoặc Spring Data Neo4j.

## 1. Phân biệt số hàng với số thực thể

Một hàng Cypher là **một tổ hợp các giá trị của những biến trong phạm vi hiện tại**, không nhất thiết tương ứng với một node riêng biệt. Cùng một node `Person` có thể xuất hiện trên nhiều hàng khi người đó có nhiều kỹ năng, tham gia nhiều dự án hoặc dự án mang nhiều nhãn phân loại.

Ví dụ, nếu một người có 2 kỹ năng và 3 dự án, truy vấn mở rộng cả hai chiều có thể tạo `2 × 3 = 6` hàng cho riêng người đó. Sáu hàng ấy không có nghĩa là tồn tại sáu người hay sáu dự án.

| Thành phần | Tác động điển hình lên số hàng |
| --- | --- |
| `MATCH` | Giữ các tổ hợp khớp mẫu; có thể loại hàng không khớp hoặc nhân hàng khi có nhiều kết quả khớp. |
| `OPTIONAL MATCH` | Nếu không khớp thì giữ một hàng với biến mới bằng `null`; nếu có nhiều kết quả thì vẫn nhân hàng. |
| `UNWIND list AS x` | Biến mỗi phần tử danh sách thành một hàng; danh sách rỗng tạo **0 hàng**. |
| `WHERE` | Loại những hàng không thỏa điều kiện. |
| `WITH` / `RETURN` chỉ chiếu cột | Thông thường giữ số hàng, trừ khi kết hợp lọc, `DISTINCT`, tổng hợp, `LIMIT`, v.v. |
| `DISTINCT` | Gộp các hàng trùng trên **bộ biểu thức được chọn**. |
| `count()`, `collect()` và các hàm tổng hợp | Gom các hàng theo khóa nhóm; số hàng đầu ra bằng số nhóm (hoặc một hàng tổng hợp nếu không có khóa nhóm). |

> **Quy tắc quan sát:** sau mỗi thao tác, hỏi “Một hàng đầu vào có thể khớp bao nhiêu kết quả?” rồi tính số hàng trên *từng* hàng đầu vào. Không mặc định mọi `MATCH` hay `UNWIND` đều nhân cùng một hệ số.

## 2. Tạo bộ dữ liệu nhỏ để kiểm chứng

Chạy lệnh sau **một lần trên cơ sở dữ liệu thử nghiệm**. Các label `DemoPerson`, `DemoProject`, `DemoTag` giúp phân biệt dữ liệu minh họa với dữ liệu ứng dụng. Nếu chạy lại `CREATE`, bạn sẽ sinh thêm node/relationship và các số đếm phía dưới không còn đúng.

```cypher
CREATE
  (an:DemoPerson {name: 'An', skills: ['Cypher', 'Java']}),
  (binh:DemoPerson {name: 'Bình', skills: ['Cypher']}),
  (chi:DemoPerson {name: 'Chi', skills: []}),
  (atlas:DemoProject {name: 'Atlas'}),
  (boreal:DemoProject {name: 'Boreal'}),
  (graph:DemoTag {name: 'Graph'}),
  (backend:DemoTag {name: 'Backend'}),
  (an)-[:WORKS_ON]->(atlas),
  (an)-[:WORKS_ON]->(boreal),
  (binh)-[:WORKS_ON]->(boreal),
  (atlas)-[:HAS_TAG]->(graph),
  (atlas)-[:HAS_TAG]->(backend),
  (boreal)-[:HAS_TAG]->(backend);
```

Cấu trúc mẫu:

```text
An ──WORKS_ON──► Atlas ──HAS_TAG──► Graph
 │                   └──HAS_TAG──► Backend
 └──WORKS_ON──► Boreal ─HAS_TAG──► Backend
 Bình ─WORKS_ON──► Boreal
 Chi  (không tham gia dự án; skills = [])

skills: An = [Cypher, Java], Bình = [Cypher], Chi = []
```

Ta có 3 người; An có 2 kỹ năng, 2 dự án; Bình có 1 kỹ năng, 1 dự án; Chi có danh sách kỹ năng rỗng và không có dự án. Atlas có 2 tag, Boreal có 1 tag.

## 3. Đếm số hàng qua từng bước của pipeline

Xét truy vấn mở rộng kỹ năng, sau đó nối người với dự án và nối dự án với tag:

```cypher
MATCH (p:DemoPerson)
UNWIND p.skills AS skill
MATCH (p)-[:WORKS_ON]->(project:DemoProject)
MATCH (project)-[:HAS_TAG]->(tag:DemoTag)
RETURN p.name AS person, skill,
       project.name AS project, tag.name AS tag
ORDER BY person, skill, project, tag;
```

Theo dõi từng chặng:

| Sau thao tác | An | Bình | Chi | Tổng hàng |
| --- | ---: | ---: | ---: | ---: |
| `MATCH (p:DemoPerson)` | 1 | 1 | 1 | **3** |
| `UNWIND p.skills AS skill` | 2 | 1 | 0 | **3** |
| `MATCH (p)-[:WORKS_ON]->(project)` | 2 × 2 = 4 | 1 × 1 = 1 | 0 | **5** |
| `MATCH (project)-[:HAS_TAG]->(tag)` | 2 × (2 + 1) = 6 | 1 × 1 = 1 | 0 | **7** |

Kết quả cuối cùng có 7 hàng:

| person | skill | project | tag |
| --- | --- | --- | --- |
| An | Cypher | Atlas | Backend |
| An | Cypher | Atlas | Graph |
| An | Cypher | Boreal | Backend |
| An | Java | Atlas | Backend |
| An | Java | Atlas | Graph |
| An | Java | Boreal | Backend |
| Bình | Cypher | Boreal | Backend |

Có thể xác nhận từng mốc bằng cách **dừng truy vấn tại vị trí muốn đo** và dùng `count(*)`:

```cypher
// Mốc 1: 3 hàng
MATCH (p:DemoPerson)
RETURN count(*) AS rows;

// Mốc 2: 3 hàng (An: 2, Bình: 1, Chi: 0)
MATCH (p:DemoPerson)
UNWIND p.skills AS skill
RETURN count(*) AS rows;

// Mốc 3: 5 hàng
MATCH (p:DemoPerson)
UNWIND p.skills AS skill
MATCH (p)-[:WORKS_ON]->(project:DemoProject)
RETURN count(*) AS rows;

// Mốc 4: 7 hàng
MATCH (p:DemoPerson)
UNWIND p.skills AS skill
MATCH (p)-[:WORKS_ON]->(project:DemoProject)
MATCH (project)-[:HAS_TAG]->(tag:DemoTag)
RETURN count(*) AS rows;
```

Hệ số mở rộng phụ thuộc vào **từng nhánh dữ liệu**. Với chuỗi `UNWIND` → dự án → tag như trên, số hàng được tính theo:

\[
N = \sum_{p \in P} |\operatorname{skills}(p)|
    \times \sum_{q \in \operatorname{projects}(p)} |\operatorname{tags}(q)|
\]

Ở dữ liệu mẫu: `N = 2 × (2 + 1) + 1 × 1 + 0 = 7`. Công thức giả định mỗi quan hệ trong ví dụ là một lần khớp; với dữ liệu có nhiều relationship song song, cần đếm **lượt khớp mẫu**, không chỉ số node đích khác nhau.

## 4. Hiểu đúng `UNWIND`, danh sách rỗng và `null`

`UNWIND` mở rộng **mỗi phần tử** của danh sách trong từng hàng đầu vào:

```cypher
UNWIND ['Cypher', 'Java'] AS skill
RETURN skill;
// 2 hàng: Cypher, Java

UNWIND [] AS skill
RETURN skill;
// 0 hàng

UNWIND [null] AS skill
RETURN skill;
// 1 hàng: skill = null
```

Vì `Chi.skills = []`, người này **biến mất khỏi luồng** ngay sau `UNWIND p.skills`. Một `OPTIONAL MATCH` đặt *sau* bước đó không thể khôi phục hàng đã mất.

Nếu nghiệp vụ yêu cầu giữ cả người không có kỹ năng, hãy thay danh sách rỗng hoặc `null` bằng danh sách chứa một `null` **trước khi mở rộng**:

```cypher
MATCH (p:DemoPerson)
UNWIND CASE
  WHEN p.skills IS NULL OR size(p.skills) = 0 THEN [null]
  ELSE p.skills
END AS skill
RETURN p.name AS person, skill
ORDER BY person, skill;
```

Kết quả có **4 hàng**: An 2, Bình 1, Chi 1 (với `skill = null`). Cách này thích hợp khi cần hiển thị một dòng cho đối tượng không có phần tử; nếu mục đích là thống kê đúng số kỹ năng, hãy dùng `count(skill)` để không tính hàng `null` giả lập.

`coalesce(p.skills, [])` chỉ thay thế `null`; nó **không** bảo toàn hàng khi danh sách rỗng. Ngược lại, viết `coalesce(p.skills, [null])` cũng không xử lý được `[]`. Cần phân biệt hai trường hợp.

Hai lần `UNWIND` liên tiếp có thể tạo **tích Descartes** giữa các danh sách của cùng một hàng:

```cypher
WITH ['An', 'Bình'] AS people, ['Graph', 'Backend', 'Java'] AS topics
UNWIND people AS person
UNWIND topics AS topic
RETURN person, topic;
// 2 × 3 = 6 hàng, không phải 2 hay 3 hàng
```

Nếu hai danh sách biểu diễn các cặp phần tử cùng vị trí, không nên `UNWIND` độc lập cả hai; thay vào đó, mở rộng một danh sách chỉ số và truy cập phần tử tương ứng.

## 5. Ghép nhiều mẫu `MATCH`: lọc, nhân hàng và tích Descartes

Một `MATCH` là phép ghép mẫu dựa trên các biến đã có. Với mỗi hàng đầu vào:

- Không có kết quả khớp: hàng bị loại.
- Có một kết quả khớp: sinh một hàng.
- Có nhiều kết quả khớp: sinh nhiều hàng, kể cả khi các hàng chứa cùng node ở một số cột.

Ví dụ bỏ bước kỹ năng, chỉ ghép hai loại relationship:

```cypher
MATCH (p:DemoPerson)-[:WORKS_ON]->(project:DemoProject)
MATCH (project)-[:HAS_TAG]->(tag:DemoTag)
RETURN p.name AS person, project.name AS project,
       tag.name AS tag
ORDER BY person, project, tag;
// 4 hàng: An–Atlas–Graph, An–Atlas–Backend,
//         An–Boreal–Backend, Bình–Boreal–Backend
```

Hai mẫu trên **có biến chung** `project`, vì thế chỉ nối được tag thuộc dự án đã khớp. Ngược lại, nếu hai mẫu độc lập, Neo4j phải xét mọi tổ hợp:

```cypher
MATCH (p:DemoPerson)
MATCH (tag:DemoTag)
RETURN count(*) AS rows;
// 3 người × 2 tag = 6 hàng
```

Đây là **tích Descartes** vì giữa `p` và `tag` không có điều kiện liên kết. Trong truy vấn lớn, ghép các mẫu độc lập có thể khiến số hàng tăng đột biến. Khi cần liên kết thực sự, hãy viết đường quan hệ hoặc điều kiện ghép phù hợp; khi thật sự muốn mọi tổ hợp, hãy thể hiện rõ ý định và dự tính cardinality.

### `OPTIONAL MATCH` giữ hàng khi không khớp, nhưng vẫn có thể mở rộng

```cypher
MATCH (p:DemoPerson)
OPTIONAL MATCH (p)-[:WORKS_ON]->(project:DemoProject)
RETURN p.name AS person, project.name AS project
ORDER BY person, project;
```

Ở đây có **4 hàng**: An–Atlas, An–Boreal, Bình–Boreal và Chi–`null`. Với An, `OPTIONAL MATCH` vẫn nhân thành 2 hàng; với Chi, nó giữ 1 hàng chứa `null`. Nếu ghép tiếp một `OPTIONAL MATCH` lấy tag, các hàng của Atlas lại tăng thành 2, còn hàng của Chi được giữ với tag `null`.

Lưu ý phạm vi điều kiện: `WHERE` gắn trực tiếp với `OPTIONAL MATCH` là một phần của phép khớp tùy chọn. Một bước lọc `WHERE` ở `WITH` phía sau có thể loại hàng mang `null`, làm mất tác dụng giữ hàng của `OPTIONAL MATCH`:

```cypher
MATCH (p:DemoPerson)
OPTIONAL MATCH (p)-[:WORKS_ON]->(project:DemoProject)
WITH p, project
WHERE project.name = 'Atlas'
RETURN p.name AS person;
// Chỉ còn An; Chi và Bình bị lọc khỏi luồng
```

## 6. Đếm, khử trùng lặp và gom nhóm đúng nghĩa

Phải xác định trước **đơn vị đang đếm**: hàng kết quả, người, dự án, tag hay quan hệ.

```cypher
MATCH (p:DemoPerson)
UNWIND p.skills AS skill
MATCH (p)-[:WORKS_ON]->(project:DemoProject)
MATCH (project)-[:HAS_TAG]->(tag:DemoTag)
RETURN
  count(*) AS resultRows,
  count(DISTINCT p) AS uniquePeople,
  count(DISTINCT project) AS uniqueProjects,
  count(DISTINCT tag) AS uniqueTags;
// resultRows = 7, uniquePeople = 2,
// uniqueProjects = 2, uniqueTags = 2
```

- `count(*)` đếm mọi hàng, kể cả hàng có một số cột `null`.
- `count(x)` chỉ đếm hàng có `x` khác `null`.
- `count(DISTINCT x)` đếm giá trị `x` khác `null` không trùng.
- `WITH DISTINCT p` đưa luồng về một hàng cho mỗi người `p`, **nhưng cũng làm mất các tổ hợp kỹ năng/dự án/tag** nếu không giữ hoặc gom chúng trước đó.

Nếu mục tiêu là **một hàng cho mỗi người** với danh sách dự án và tag, gom nhóm trước khi trả kết quả:

```cypher
MATCH (p:DemoPerson)
OPTIONAL MATCH (p)-[:WORKS_ON]->(project:DemoProject)
OPTIONAL MATCH (project)-[:HAS_TAG]->(tag:DemoTag)
WITH p,
     collect(DISTINCT project.name) AS projects,
     collect(DISTINCT tag.name) AS tags
RETURN p.name AS person, p.skills AS skills, projects, tags
ORDER BY person;
```

Kết quả có **3 hàng**, mỗi người một hàng. An có dự án `Atlas`, `Boreal` và tag `Graph`, `Backend`; Bình có `Boreal` và `Backend`; Chi có `projects = []`, `tags = []`. Thứ tự phần tử trong các danh sách từ `collect()` không được bảo đảm nếu không thiết lập thứ tự thích hợp trước khi tổng hợp; hãy so sánh theo tập phần tử khi kiểm thử ví dụ này. Các giá trị `null` không được đưa vào danh sách bởi `collect()`.

Khi chỉ cần **số dự án** của mỗi người, không cần nhân thêm theo tag:

```cypher
MATCH (p:DemoPerson)
OPTIONAL MATCH (p)-[:WORKS_ON]->(project:DemoProject)
WITH p, count(DISTINCT project) AS projectCount
RETURN p.name AS person, projectCount
ORDER BY person;
// An: 2, Bình: 1, Chi: 0
```

`count(DISTINCT project)` ở đây đếm số node dự án khác nhau. Nếu cần đếm **quan hệ `WORKS_ON`** (kể cả nhiều quan hệ cùng nối đến một dự án), phải ràng buộc biến relationship và đếm chính biến đó.

## 7. Giảm nhân hàng khi chỉ cần kiểm tra sự tồn tại

Không phải truy vấn nào cũng cần trả ra mọi tổ hợp node và relationship. Nếu nghiệp vụ chỉ yêu cầu “người nào tham gia ít nhất một dự án gắn tag Graph”, dùng `EXISTS` để kiểm tra điều kiện:

```cypher
MATCH (p:DemoPerson)
WHERE EXISTS {
  MATCH (p)-[:WORKS_ON]->(:DemoProject)-[:HAS_TAG]->(:DemoTag {name: 'Graph'})
}
RETURN p.name AS person;
// Một hàng: An
```

Cách này diễn đạt đúng câu hỏi tồn tại và giữ một hàng cho mỗi `p` thỏa điều kiện, thay vì mở rộng tất cả các dự án và tag rồi dùng `DISTINCT` để khử bản sao.

Khi cần nhiều tập kết quả khác nhau (ví dụ danh sách kỹ năng, dự án, tag) trên **một đối tượng gốc**, hãy cân nhắc tổng hợp từng nhánh trước khi ghép, hoặc dùng subquery có phạm vi rõ ràng. Nếu mở rộng đồng thời các nhánh độc lập rồi mới `collect()`, số hàng trung gian có thể tăng mạnh dù bảng kết quả cuối chỉ có vài dòng.

## 8. Đọc cardinality trong execution plan

`EXPLAIN` cho biết kế hoạch và **ước lượng** số hàng mà không chạy truy vấn; `PROFILE` thực thi truy vấn rồi hiển thị **số hàng thực tế** tại các operator (cùng các chỉ số chi phí, tùy phiên bản Neo4j và giao diện). Với ví dụ chỉ đọc:

```cypher
PROFILE
MATCH (p:DemoPerson)
UNWIND p.skills AS skill
MATCH (p)-[:WORKS_ON]->(project:DemoProject)
MATCH (project)-[:HAS_TAG]->(tag:DemoTag)
RETURN p.name AS person, skill, project.name AS project, tag.name AS tag;
```

Khi xem plan, chú ý các operator thường gặp như `Unwind`, `Expand(All)`, `Filter`, `Aggregation`, `Distinct` và số **Rows** đầu ra của chúng. Một dấu hiệu cần kiểm tra là số Rows tăng mạnh sau bước mở rộng relationship hoặc `UNWIND`, rồi giảm đột ngột ở `Distinct`/`Aggregation`: truy vấn có thể đang tạo nhiều tổ hợp trung gian mà kết quả cuối không sử dụng.

**Không nên suy từ thứ tự trình bày Cypher rằng thứ tự thực thi vật lý luôn giống hệt.** Bộ tối ưu có thể đổi thứ tự duyệt mẫu hoặc áp bộ lọc sớm. Bảng 3 → 3 → 5 → 7 ở trên mô tả ngữ nghĩa của các chặng truy vấn; muốn quan sát operator thực tế phải đọc execution plan trên môi trường đang chạy. Chỉ dùng `PROFILE` trực tiếp với lệnh ghi khi bạn thực sự muốn nó **thực thi thao tác ghi**.

## 9. Tình huống thực tế và checklist kiểm soát

Giả sử một hệ thống gợi ý học tập lưu người học, chủ đề quan tâm, khóa học và các tag kỹ năng. Câu hỏi “có bao nhiêu người học quan tâm tới Graph?” khác hẳn “có bao nhiêu tổ hợp người học–khóa học–tag Graph?”. Truy vấn thứ hai có thể trả nhiều hàng cho cùng một người học nếu người đó đăng ký nhiều khóa học phù hợp. Nếu ứng dụng Java Driver ánh xạ một hàng thành một DTO người học, giao diện có thể hiển thị người học lặp; nếu hệ thống dùng `count(*)` để phân trang người học, tổng trang cũng sai theo ý nghĩa nghiệp vụ.

Trước khi hoàn tất truy vấn có `UNWIND` hoặc nhiều `MATCH`, tự kiểm tra:

1. **Đơn vị đầu ra là gì?** Một hàng trên người, một hàng trên dự án hay một hàng trên tổ hợp các mẫu?
2. **Danh sách có thể rỗng/`null` không?** Có chấp nhận mất hàng khi `UNWIND` không?
3. **Mỗi nhánh có bao nhiêu lượt khớp?** Ước tính theo từng đối tượng thay vì nhân một hệ số trung bình cho toàn bảng.
4. **Các mẫu có biến chung hoặc điều kiện nối không?** Có phát sinh tích Descartes ngoài ý muốn không?
5. **Có cần giữ đối tượng không khớp?** Dùng `OPTIONAL MATCH` đúng vị trí và lưu ý bước lọc tiếp theo.
6. **Cần đếm hàng, giá trị khác `null` hay node/relationship khác nhau?** Chọn `count(*)`, `count(x)` hoặc `count(DISTINCT x)` phù hợp.
7. **Có chỉ cần kiểm tra tồn tại hoặc gom nhóm sớm không?** Giảm số hàng trung gian bằng `EXISTS`, tổng hợp hoặc tách nhánh truy vấn.
8. **Số hàng quan sát có khớp dự đoán không?** Đếm từng chặng bằng `RETURN count(*)`, sau đó kiểm tra `EXPLAIN`/`PROFILE` khi cần tối ưu.

**Ghi nhớ:** cardinality là đặc tính của **luồng kết quả**, không phải số node trong Neo4j. Nắm rõ cách `UNWIND`, `MATCH`, `OPTIONAL MATCH`, `DISTINCT` và aggregation thay đổi luồng sẽ giúp viết Cypher chính xác hơn, nhất là khi mô hình đồ thị có nhiều mối quan hệ một–nhiều đan xen.

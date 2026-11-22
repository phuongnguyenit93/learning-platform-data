# Duyệt đồ thị, khớp mẫu và giới hạn độ sâu

Trong mô hình NoSQL **đồ thị (graph database)**, các thực thể được biểu diễn thành **đỉnh (node)**, còn những quan hệ giữa chúng được biểu diễn thành **cạnh (relationship/edge)**. Khi cần tìm người quen của người quen, tác giả của bài viết mà bạn bè đang theo dõi, tuyến liên hệ giữa hai người hoặc những đối tượng liên quan trong một chuỗi giao dịch, câu hỏi cốt lõi không còn là chỉ lấy một bản ghi theo khóa. Hệ thống phải **đi qua các cạnh** theo một quy tắc.

Ba kỹ năng quan trọng để truy vấn đồ thị hiệu quả là:

1. **Duyệt đồ thị (traversal):** bắt đầu từ một hoặc nhiều node và đi qua những cạnh được phép, có thể qua nhiều bước.
2. **Khớp mẫu (pattern matching):** mô tả hình dạng quan hệ cần tìm bằng các node, nhãn, kiểu cạnh, hướng cạnh và điều kiện thuộc tính.
3. **Giới hạn độ sâu (depth limiting):** kiểm soát tối đa bao nhiêu cạnh được đi qua, tránh truy vấn mở rộng quá mức và giữ đúng ý nghĩa nghiệp vụ.

Bài học dùng một mạng cộng tác nhỏ làm ví dụ, với cú pháp **Cypher theo phong cách Neo4j**. Các khái niệm áp dụng rộng rãi cho property graph, nhưng cú pháp truy vấn, cách tránh lặp đường đi và thuật toán tối ưu khác nhau giữa Neo4j, Gremlin, các hệ hỗ trợ openCypher và những sản phẩm đồ thị khác. Khi áp dụng trên phiên bản cụ thể, cần kiểm tra ngữ nghĩa và tính năng tương ứng.

## 1. Hiểu các thành phần của một đồ thị

Một **property graph** thường gồm:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Node** | Một thực thể có định danh, nhãn và thuộc tính | \`(:Person {id: 'u1', name: 'An'})\` |
| **Label** | Phân loại node | \`Person\`, \`Post\` |
| **Relationship** | Cạnh nối hai node, thường có hướng và kiểu | \`(An)-[:FOLLOWS]->(Bình)\` |
| **Relationship type** | Ý nghĩa nghiệp vụ của cạnh | \`FOLLOWS\`, \`AUTHORED\` |
| **Property** | Dữ liệu trên node hoặc cạnh | \`name\`, \`createdAt\`, \`since\` |
| **Path** | Chuỗi node và relationship nối tiếp nhau | An → Chi → Dũng |
| **Hop / depth** | Số cạnh được đi qua từ node bắt đầu | An → Chi là 1 hop, An → Chi → Dũng là 2 hop |

Trong bài này, \`FOLLOWS\` là quan hệ **có hướng**: An theo dõi Bình không nhất thiết nghĩa là Bình theo dõi An. Bỏ qua hướng cạnh có thể tạo kết quả khác hoàn toàn yêu cầu nghiệp vụ.

### 1.1. Đồ thị ví dụ

Giả sử có bảy thành viên và ba bài viết:

~~~mermaid
flowchart LR
    An["An (u1)"] -->|FOLLOWS| Binh["Bình (u2)"]
    An -->|FOLLOWS| Chi["Chi (u3)"]
    Binh -->|FOLLOWS| Dung["Dũng (u4)"]
    Chi -->|FOLLOWS| Dung
    Chi -->|FOLLOWS| Em["Em (u5)"]
    Dung -->|FOLLOWS| Giang["Giang (u6)"]
    Em -->|FOLLOWS| Giang
    Giang -->|FOLLOWS| An
    Ha["Hà (u7)"] -->|FOLLOWS| Chi
~~~

Ngoài quan hệ theo dõi, ba người có viết bài:

~~~text
Giang (u6) -[:AUTHORED]-> "NoSQL căn bản" (p1)
Dũng  (u4) -[:AUTHORED]-> "Đồ thị thực hành" (p2)
Em    (u5) -[:AUTHORED]-> "Chỉ mục truy vấn" (p3)
~~~

Sơ đồ trên có ba điểm cần chú ý:

- Từ An đến Dũng có **hai đường đi dài 2**: An → Bình → Dũng và An → Chi → Dũng.
- Từ An đến Giang có **đường đi dài 3**, qua Dũng hoặc Em.
- Có **chu trình (cycle)** Giang → An → Chi → Dũng → Giang; nếu liên tục đi theo các cạnh mà không đặt giới hạn, đường đi có thể quay lại các node trước đó.

Các tình huống này sẽ giúp phân biệt **số đường đi**, **số node đích duy nhất** và **độ sâu của quá trình duyệt**.

## 2. Khởi tạo dữ liệu mẫu bằng Cypher

Bạn có thể thực hành trong một database Neo4j thử nghiệm có hỗ trợ Cypher. Những lệnh dưới đây tạo node theo ID nghiệp vụ và dùng \`MERGE\` để không tạo trùng quan hệ khi chạy lại cùng dữ liệu.

### 2.1. Khai báo tính duy nhất cho định danh

~~~cypher
CREATE CONSTRAINT person_id IF NOT EXISTS
FOR (p:Person) REQUIRE p.id IS UNIQUE;

CREATE CONSTRAINT post_id IF NOT EXISTS
FOR (p:Post) REQUIRE p.id IS UNIQUE;
~~~

Các lệnh này minh họa cú pháp constraint trong Neo4j hiện đại. Nếu sản phẩm hoặc phiên bản đang dùng có cú pháp khác, cần điều chỉnh tương ứng. Các ID như \`u1\` và \`p1\` là **định danh nghiệp vụ**; không nên phụ thuộc vào định danh node nội bộ của engine để liên kết dữ liệu lâu dài.

### 2.2. Tạo các node thành viên

~~~cypher
UNWIND [
  {id: 'u1', name: 'An'},
  {id: 'u2', name: 'Bình'},
  {id: 'u3', name: 'Chi'},
  {id: 'u4', name: 'Dũng'},
  {id: 'u5', name: 'Em'},
  {id: 'u6', name: 'Giang'},
  {id: 'u7', name: 'Hà'}
] AS item
MERGE (p:Person {id: item.id})
SET p.name = item.name;
~~~

### 2.3. Tạo các quan hệ theo dõi

~~~cypher
UNWIND [
  {from: 'u1', to: 'u2'},
  {from: 'u1', to: 'u3'},
  {from: 'u2', to: 'u4'},
  {from: 'u3', to: 'u4'},
  {from: 'u3', to: 'u5'},
  {from: 'u4', to: 'u6'},
  {from: 'u5', to: 'u6'},
  {from: 'u6', to: 'u1'},
  {from: 'u7', to: 'u3'}
] AS link
MATCH (a:Person {id: link.from})
MATCH (b:Person {id: link.to})
MERGE (a)-[:FOLLOWS]->(b);
~~~

Vì cạnh có hướng, \`(a)-[:FOLLOWS]->(b)\` và \`(b)-[:FOLLOWS]->(a)\` là hai quan hệ khác nhau. \`MERGE\` ở đây tránh tạo lặp cạnh cùng mẫu trong phạm vi dữ liệu mẫu, nhưng với một hệ thống thật phải định nghĩa rõ có cho phép nhiều cạnh cùng loại giữa hai node hay không, chẳng hạn khi cạnh có thời gian hiệu lực hoặc lịch sử thay đổi.

### 2.4. Tạo bài viết và liên kết tác giả

~~~cypher
UNWIND [
  {id: 'p1', title: 'NoSQL căn bản', authorId: 'u6'},
  {id: 'p2', title: 'Đồ thị thực hành', authorId: 'u4'},
  {id: 'p3', title: 'Chỉ mục truy vấn', authorId: 'u5'}
] AS item
MERGE (post:Post {id: item.id})
SET post.title = item.title
WITH item, post
MATCH (author:Person {id: item.authorId})
MERGE (author)-[:AUTHORED]->(post);
~~~

Sau khi chạy, dữ liệu đáp ứng một tập truy vấn vừa đủ để quan sát cách đồ thị mở rộng theo số bước:

| Câu hỏi | Truy vấn cần thực hiện |
| --- | --- |
| Ai được An theo dõi trực tiếp? | 1 cạnh \`FOLLOWS\` |
| Ai được người mà An theo dõi tiếp tục theo dõi? | 2 cạnh \`FOLLOWS\` |
| Những ai nằm trong tối đa 3 bước từ An? | Duyệt đường có độ dài thay đổi |
| Những bài viết do người có thể tiếp cận trong 3 bước tạo ra? | Khớp mẫu \`FOLLOWS\` rồi \`AUTHORED\` |
| Đường liên hệ ngắn nhất từ An tới Giang? | Tìm đường đi theo số hop |

## 3. Khớp mẫu: cách đọc cú pháp MATCH

Cypher biểu diễn một mẫu đồ thị bằng hình dạng gần giống sơ đồ:

~~~cypher
MATCH (a:Person {id: 'u1'})-[:FOLLOWS]->(b:Person)
RETURN b.id, b.name;
~~~

Đọc theo từng phần:

- \`(a:Person {id: 'u1'})\`: tìm node có label \`Person\` và ID \`u1\`, gán biến \`a\`.
- \`-[:FOLLOWS]->\`: đi theo **một cạnh FOLLOWS chiều đi ra** từ \`a\`.
- \`(b:Person)\`: node đích phải có label \`Person\`, gán vào biến \`b\`.
- \`RETURN\`: chọn các trường cần trả về.

Với dữ liệu mẫu, kết quả là **Bình và Chi**.

### 3.1. Hướng cạnh làm thay đổi câu hỏi

Ba mẫu sau không tương đương:

~~~cypher
// Ai được An theo dõi?
MATCH (:Person {id: 'u1'})-[:FOLLOWS]->(p:Person)
RETURN p.name;
~~~

~~~cypher
// Ai đang theo dõi An?
MATCH (:Person {id: 'u1'})<-[:FOLLOWS]-(p:Person)
RETURN p.name;
~~~

~~~cypher
// Ai có bất kỳ cạnh FOLLOWS nối với An, bất kể hướng?
MATCH (:Person {id: 'u1'})-[:FOLLOWS]-(p:Person)
RETURN DISTINCT p.name;
~~~

Trong dữ liệu hiện tại, người theo dõi An là **Giang**; An theo dõi **Bình và Chi**. Câu thứ ba lấy các node kề với An theo cả hai chiều, nên có thể trả cả ba người.

**Không bỏ hướng cạnh chỉ để truy vấn trả nhiều kết quả hơn.** Trong hệ phân quyền, thanh toán hoặc chuỗi phê duyệt, đảo hướng có thể làm sai hoàn toàn ý nghĩa quan hệ.

### 3.2. Mẫu nhiều quan hệ cố định

Để tìm người được **người mà An theo dõi** tiếp tục theo dõi:

~~~cypher
MATCH (an:Person {id: 'u1'})-[:FOLLOWS]->(middle:Person)
      -[:FOLLOWS]->(candidate:Person)
RETURN candidate.id AS id,
       candidate.name AS name,
       count(DISTINCT middle) AS viaPeople
ORDER BY id;
~~~

Kết quả kỳ vọng:

| id | name | viaPeople |
| --- | --- | ---: |
| u4 | Dũng | 2 |
| u5 | Em | 1 |

Dũng xuất hiện qua hai node trung gian là Bình và Chi; \`count(DISTINCT middle)\` cho biết số người trung gian khác nhau. **Một node đích có thể khớp cùng mẫu bằng nhiều đường**.

### 3.3. Khớp mẫu kết hợp thuộc tính

Ta có thể thêm điều kiện vào node:

~~~cypher
MATCH (an:Person {id: 'u1'})-[:FOLLOWS]->(p:Person)
WHERE p.name STARTS WITH 'B'
RETURN p.id, p.name;
~~~

Kết quả là Bình. Điều kiện thuộc tính có thể giúp lọc kết quả, nhưng chi phí thực tế phụ thuộc **vị trí điều kiện được áp dụng trong kế hoạch thực thi**, selectivity và chỉ mục. Không mặc định mọi \`WHERE\` đặt sau một mẫu dài sẽ giảm được lượng duyệt từ đầu.

### 3.4. Mẫu cần đồng thời nhiều quan hệ

Giả sử cần những người vừa được An theo dõi, vừa là tác giả của một bài viết:

~~~cypher
MATCH (an:Person {id: 'u1'})-[:FOLLOWS]->(author:Person)
MATCH (author)-[:AUTHORED]->(post:Post)
RETURN author.name, post.title;
~~~

Với bộ dữ liệu mẫu, An theo dõi trực tiếp Bình và Chi; cả hai chưa có bài viết nên câu truy vấn không trả hàng nào. Đây là **kết quả đúng theo mẫu**, không phải lỗi. Nếu yêu cầu là “bài viết của người có thể tiếp cận trong ba bước”, phải thay đổi phần duyệt, như các mục tiếp theo.

## 4. Duyệt đồ thị là gì?

Một truy vấn **duyệt** bắt đầu từ một node đã biết, xét các cạnh hợp lệ đi ra hoặc đi vào, rồi mở rộng sang những node mới. Mỗi lần đi qua một cạnh tính là **một hop**.

Từ An trong đồ thị ví dụ:

~~~text
Độ sâu 0: An
Độ sâu 1: Bình, Chi
Độ sâu 2: Dũng, Em
Độ sâu 3: Giang
Độ sâu 4: Có thể quay lại An do cạnh Giang -> An
~~~

Đây là danh sách **node duy nhất theo khoảng cách hop nhỏ nhất**. Nếu đếm **mọi đường đi**, Dũng có hai đường dài 2, Giang có nhiều đường dài 3 và số kết quả có thể lớn hơn nhiều.

### 4.1. BFS: duyệt theo chiều rộng

**Breadth-first search (BFS)** duyệt những node cách điểm bắt đầu 1 hop trước, rồi mới 2 hop, 3 hop... Với đồ thị không trọng số, BFS thích hợp để tìm **số cạnh tối thiểu** từ một node tới node khác.

~~~text
Queue ban đầu: [An]
Xử lý An:       thêm Bình, Chi (depth=1)
Xử lý Bình:     thêm Dũng (depth=2)
Xử lý Chi:      thêm Em; Dũng đã được biết
Xử lý Dũng:     thêm Giang (depth=3)
Xử lý Em:       Giang đã được biết
Xử lý Giang:    An đã được biết; không mở rộng lại
~~~

Nếu dùng tập \`visited\` toàn cục, mỗi node chỉ được đưa vào hàng đợi ở lần khám phá đầu tiên. Với BFS chuẩn, lần đầu ấy cho khoảng cách tính theo hop ngắn nhất trong đồ thị không trọng số.

### 4.2. DFS: duyệt theo chiều sâu

**Depth-first search (DFS)** đi tiếp theo một nhánh cho tới giới hạn hoặc khi không còn cạnh phù hợp, sau đó quay lui sang nhánh khác.

Ví dụ một thứ tự có thể là:

~~~text
An -> Bình -> Dũng -> Giang
               quay lui
An -> Chi -> Em -> Giang
~~~

Thứ tự DFS phụ thuộc cách duyệt các cạnh và không đảm bảo đường đầu tiên tìm thấy là đường **ít hop nhất**. DFS phù hợp cho bài toán tìm tính liên thông, phát hiện chu trình hoặc duyệt có quay lui; với yêu cầu shortest hop, BFS thường là ý tưởng ban đầu hợp lý hơn.

### 4.3. Không phải mọi Cypher MATCH đều “chạy BFS” hoặc “chạy DFS”

Khi viết Cypher, ta thường mô tả **kết quả cần khớp**, còn engine chọn cách thực thi dựa trên kế hoạch truy vấn. Một pattern nhiều cạnh không bắt buộc engine phải dùng BFS hoặc DFS đơn giản như chương trình tự cài đặt.

Phân biệt:

- **Mô hình thuật toán:** BFS/DFS giải thích cách mở rộng và quản lý visited.
- **Ngôn ngữ truy vấn:** \`MATCH\` mô tả node/cạnh/đường cần tìm.
- **Engine:** chọn index seek, node expansion, join, filter hoặc các toán tử đường đi cụ thể.

Muốn biết engine thực sự làm gì, sử dụng **EXPLAIN** và **PROFILE** trên truy vấn và dữ liệu phù hợp.

## 5. Khớp đường đi có độ dài thay đổi

Trong bài toán thực tế, ta thường không biết trước cần đi qua chính xác mấy cạnh. Chẳng hạn “tìm những người An có thể tiếp cận qua tối đa ba lần theo dõi”.

Một cách viết Cypher quen thuộc:

~~~cypher
MATCH path = (an:Person {id: 'u1'})-[:FOLLOWS*1..3]->(p:Person)
WHERE p <> an
RETURN p.id AS id, p.name AS name,
       min(length(path)) AS minHops
ORDER BY minHops, id;
~~~

\`*1..3\` biểu diễn **đường có từ 1 đến 3 cạnh \`FOLLOWS\`** theo hướng đi từ An. \`length(path)\` là số cạnh của đường được khớp; \`min(...)\` gom những đường có cùng node đích để lấy số hop nhỏ nhất.

Kết quả theo dữ liệu mẫu:

| id | name | minHops |
| --- | --- | ---: |
| u2 | Bình | 1 |
| u3 | Chi | 1 |
| u4 | Dũng | 2 |
| u5 | Em | 2 |
| u6 | Giang | 3 |

### 5.1. So sánh các khoảng độ dài

| Cú pháp minh họa | Ý nghĩa |
| --- | --- |
| \`-[:FOLLOWS]->\` | Chính xác 1 cạnh |
| \`-[:FOLLOWS*2..2]->\` | Chính xác 2 cạnh |
| \`-[:FOLLOWS*1..3]->\` | Từ 1 đến 3 cạnh |
| \`-[:FOLLOWS*0..3]->\` | Từ 0 đến 3 cạnh, có thể gồm node bắt đầu |
| \`-[:FOLLOWS*..3]->\` | Tới 3 cạnh theo ngữ nghĩa phiên bản Cypher |

Một số phiên bản mới của Cypher còn cung cấp **quantified path patterns** và **quantified relationships** với cú pháp khác. Các ví dụ ở đây cố ý dùng dạng variable-length truyền thống để người học nhìn rõ ý nghĩa min/max hop; khi dùng sản phẩm cụ thể, hãy kiểm tra cú pháp được hỗ trợ.

**Đường dài 0** là trường hợp đặc biệt: không cần đi qua cạnh nào, nên node bắt đầu có thể cũng là node kết thúc. Nếu nghiệp vụ yêu cầu “người khác An”, cần loại trừ An bằng điều kiện rõ ràng.

### 5.2. Đường đi khác node đích

Truy vấn:

~~~cypher
MATCH path = (an:Person {id: 'u1'})-[:FOLLOWS*2..2]->(p:Person)
RETURN p.id AS id,
       [n IN nodes(path) | n.name] AS route
ORDER BY id, route;
~~~

Trả về những **đường đi**, không chỉ danh sách người:

~~~text
u4 | ["An", "Bình", "Dũng"]
u4 | ["An", "Chi", "Dũng"]
u5 | ["An", "Chi", "Em"]
~~~

Nếu chỉ muốn **người đích duy nhất**, dùng:

~~~cypher
MATCH (:Person {id: 'u1'})-[:FOLLOWS*2..2]->(p:Person)
RETURN DISTINCT p.id, p.name;
~~~

Nếu muốn **đếm số đường đi**, dùng \`count(path)\` nhưng phải biết chính xác định nghĩa đường hợp lệ của engine: có cho phép quay lại node cũ, lặp relationship, lặp cạnh song song hay không. Đếm đường đi không nhất thiết bằng đếm node, và hai khái niệm phục vụ hai mục tiêu khác nhau.

### 5.3. Giới hạn độ sâu là điều kiện nghiệp vụ

Giả sử ứng dụng định nghĩa “người quen” là người trong **tối đa hai bước** từ An. Khi đó Giang (ở 3 bước) **không phải kết quả hợp lệ**, dù vẫn có đường liên hệ tồn tại.

Vì thế:

~~~cypher
MATCH (:Person {id: 'u1'})-[:FOLLOWS*1..2]->(p:Person)
RETURN DISTINCT p.id, p.name;
~~~

không thể bị thay vô điều kiện bằng truy vấn 1–5 bước và \`LIMIT 5\`. **Depth bound** giới hạn độ dài mỗi đường; **LIMIT** giới hạn số hàng kết quả sau những bước xử lý tương ứng. Chúng có mục đích khác nhau.

## 6. Kết hợp duyệt với khớp mẫu: gợi ý bài viết

Nghiệp vụ: “Tìm bài viết do những người mà An tiếp cận được qua tối đa ba cạnh \`FOLLOWS\` tạo ra”.

Mẫu gồm hai phần:

~~~text
(An)-[:FOLLOWS*1..3]->(Tác giả)-[:AUTHORED]->(Bài viết)
~~~

Truy vấn:

~~~cypher
MATCH (an:Person {id: 'u1'})-[:FOLLOWS*1..3]->(author:Person)
MATCH (author)-[:AUTHORED]->(post:Post)
WHERE author <> an
RETURN DISTINCT post.id AS postId,
       post.title AS title,
       author.name AS author
ORDER BY postId;
~~~

Với dữ liệu mẫu, kết quả gồm:

| postId | title | author |
| --- | --- | --- |
| p1 | NoSQL căn bản | Giang |
| p2 | Đồ thị thực hành | Dũng |
| p3 | Chỉ mục truy vấn | Em |

Giang có thể được tiếp cận theo nhiều đường 3 hop. Nếu không dùng \`DISTINCT\`, một bài viết của Giang có thể xuất hiện nhiều lần, do nhiều đường khớp đến cùng tác giả.

### 6.1. Tại sao cần quan tâm chiều đi của cạnh?

\`(an)-[:FOLLOWS*1..3]->(author)\` có nghĩa **An theo dõi trực tiếp hoặc gián tiếp tác giả** qua chuỗi người được theo dõi.

Nếu dùng:

~~~cypher
MATCH (an:Person {id: 'u1'})-[:FOLLOWS*1..3]-(author:Person)
~~~

thì truy vấn có thể đi cả chiều xuôi và ngược, vô tình đưa vào những người theo dõi An hoặc những mối quan hệ không cùng ý nghĩa. Đây có thể là yêu cầu đúng cho bài toán “kết nối xã hội không phân hướng”, nhưng sai với bài toán “mạng theo dõi”.

### 6.2. Lọc sớm và neo truy vấn ở node cụ thể

Hai nguyên tắc thường có ích:

1. **Bắt đầu từ node có selectivity cao**, ví dụ \`Person{id:'u1'}\` với constraint/index phù hợp.
2. **Đặt điều kiện trên loại cạnh, nhãn và thuộc tính** càng cụ thể càng tốt với mẫu truy vấn đang phục vụ.

So sánh:

~~~cypher
// Bắt đầu từ một người đã biết.
MATCH (an:Person {id: 'u1'})-[:FOLLOWS*1..3]->(p:Person)
RETURN DISTINCT p.id;
~~~

với:

~~~cypher
// Không có điểm neo cụ thể: có thể phải xét rất nhiều điểm bắt đầu.
MATCH (a:Person)-[:FOLLOWS*1..3]->(b:Person)
RETURN DISTINCT a.id, b.id;
~~~

Truy vấn thứ hai phục vụ câu hỏi khác: tìm **mọi cặp** người liên hệ trong 1–3 hop. Nó có thể tạo tập kết quả trung gian lớn hơn rất nhiều, dù độ sâu tối đa giống nhau.

## 7. Đường đi ngắn nhất và giới hạn chiều dài

Một bài toán thường gặp là: “An có kết nối được tới Giang không, và cần ít nhất bao nhiêu bước theo dõi?”.

Với graph **không trọng số**, đường đi ngắn nhất là đường có **ít cạnh nhất**. Trong ví dụ, các đường sau đều dài ba:

~~~text
An -> Bình -> Dũng -> Giang
An -> Chi  -> Dũng -> Giang
An -> Chi  -> Em   -> Giang
~~~

Một truy vấn minh họa:

~~~cypher
MATCH (an:Person {id: 'u1'})
MATCH (giang:Person {id: 'u6'})
MATCH path = shortestPath((an)-[:FOLLOWS*..4]->(giang))
RETURN [n IN nodes(path) | n.name] AS people,
       length(path) AS hops;
~~~

\`shortestPath\` trong cú pháp truyền thống tìm **một đường đi có số hop tối thiểu** theo điều kiện. Nếu có nhiều đường ngắn nhất cùng độ dài, không nên kỳ vọng nó luôn chọn cùng một đường trong mọi lần chạy hay mọi kế hoạch thực thi.

Nếu nghiệp vụ cần **tất cả đường ngắn nhất** (và phiên bản Cypher đang dùng hỗ trợ cú pháp tương ứng), có thể cân nhắc:

~~~cypher
MATCH (a:Person {id: 'u1'})
MATCH (b:Person {id: 'u6'})
MATCH path = allShortestPaths((a)-[:FOLLOWS*..4]->(b))
RETURN [n IN nodes(path) | n.id] AS route, length(path) AS hops;
~~~

Trong thực tế, số lượng đường ngắn nhất có thể nhiều. Việc trả về “tất cả” cần giới hạn theo mục đích ứng dụng; một số bài toán chỉ cần **khoảng cách** hoặc **một tuyến giải thích**.

### 7.1. Giới hạn chiều dài và không tìm thấy đường

Nếu tìm đường An → Giang với giới hạn **tối đa 2 hop**, kết quả rỗng. Điều đó **không chứng minh hai người không liên hệ trong toàn đồ thị**; chỉ chứng minh không tìm được đường đáp ứng điều kiện trong giới hạn được xét.

Trong API, nên phân biệt:

- \`FOUND\`: tìm được đường trong phạm vi truy vấn.
- \`NOT_FOUND_WITHIN_LIMIT\`: không có đường thỏa điều kiện và giới hạn đã định.
- \`TIMED_OUT\` hoặc \`RESOURCE_LIMIT\`: truy vấn không hoàn tất nên chưa biết câu trả lời.

Nhầm timeout với “không tồn tại đường” có thể làm sai kết quả phân quyền, gợi ý hoặc phân tích rủi ro.

### 7.2. Đường ít hop không phải đường ít chi phí

Nếu cạnh có trọng số \`cost\`, \`distance\`, \`risk\` hoặc \`travelTime\`, đường ít hop có thể khác đường có **tổng trọng số thấp nhất**.

Ví dụ:

~~~text
A -> B -> D      2 hop, tổng cost = 100
A -> C -> E -> D 3 hop, tổng cost = 15
~~~

Để tìm đường có **trọng số nhỏ nhất**, cần thuật toán phù hợp như Dijkstra (với trọng số không âm) hoặc thư viện thuật toán đồ thị của sản phẩm, thay vì chỉ dùng shortest hop. Độ sâu vẫn có thể là ràng buộc độc lập: “chi phí tối thiểu trong tối đa 4 bước” khác với “ít bước nhất”.

## 8. Chu trình và ngữ nghĩa lặp trong đường đi

Đồ thị mẫu có chu trình:

~~~text
An -> Chi -> Dũng -> Giang -> An
~~~

Nếu tiếp tục mở rộng từ An mà không có giới hạn, ta có thể đi quanh chu trình nhiều lần về mặt khái niệm. Trên dữ liệu lớn, một mạng quan hệ dày có thể tạo số đường đi cực kỳ lớn.

### 8.1. Node và relationship không phải cùng quy tắc “đã đi qua”

Có ba cách hiểu phổ biến về đường đi:

| Quy tắc | Ý nghĩa | Hệ quả |
| --- | --- | --- |
| **Walk** | Có thể đi lại node hoặc cạnh theo định nghĩa toán học | Số walk không giới hạn trên đồ thị có chu trình |
| **Trail** | Không lặp lại cùng relationship trong một đường đi | Có thể quay lại node cũ qua cạnh khác |
| **Simple path** | Không lặp lại node trong đường đi | Loại bỏ đường quay lại node cũ |

Trong Cypher, ngữ nghĩa tránh lặp relationship của một phép khớp đường đi phụ thuộc cú pháp và chế độ được hỗ trợ; **không được mặc định một pattern độ dài thay đổi có nghĩa là chỉ cho phép node duy nhất**.

Ví dụ tìm chu trình độ dài 4 từ An:

~~~cypher
MATCH path = (start:Person {id: 'u1'})
             -[:FOLLOWS*4..4]->
             (finish:Person {id: 'u1'})
RETURN [n IN nodes(path) | n.name] AS route;
~~~

Có thể tìm đường An → Bình → Dũng → Giang → An và An → Chi → Dũng → Giang → An; chúng quay về **cùng node An**, dù không cần dùng lại relationship nào.

### 8.2. Khi nào phải tránh quay lại node?

Nếu bài toán là “gợi ý người chưa được gặp trong mạng kết nối”, việc quay lại An không có nghĩa. Có thể loại node bắt đầu khỏi kết quả:

~~~cypher
MATCH (an:Person {id: 'u1'})-[:FOLLOWS*1..4]->(candidate:Person)
WHERE candidate <> an
RETURN DISTINCT candidate.id, candidate.name;
~~~

Điều kiện trên chỉ loại **node kết thúc là An**, chứ **không bảo đảm mọi node trung gian trên đường đều khác nhau**.

Nếu yêu cầu đích thực là đường đơn (*simple path*), một cách biểu đạt trong một số phiên bản Cypher là ràng buộc node của đường:

~~~cypher
MATCH path = (a:Person {id: 'u1'})-[:FOLLOWS*1..4]->(b:Person)
WITH path, nodes(path) AS ns
WHERE all(n IN ns WHERE single(m IN ns WHERE m = n))
RETURN [n IN ns | n.id] AS route;
~~~

Điều kiện minh họa yêu cầu **mỗi node trong danh sách xuất hiện đúng một lần**. Tuy nhiên, nếu engine đã tạo rất nhiều đường ứng viên rồi mới lọc, chi phí có thể cao. Với traversal phức tạp, cân nhắc khả năng hỗ trợ **uniqueness policy** ngay trong quá trình mở rộng của công cụ hoặc thuật toán được dùng.

### 8.3. Visited set trong thuật toán ứng dụng

Nếu chỉ cần biết **những node nào có thể đến trong 3 hop** hoặc **khoảng cách nhỏ nhất**, visited set giúp tránh duyệt lại cùng node. Nhưng nếu mục tiêu là **liệt kê tất cả đường đi**, một visited set toàn cục có thể loại bỏ những đường hợp lệ dẫn tới cùng node qua trung gian khác.

Ví dụ:

~~~text
An -> Bình -> Dũng
An -> Chi  -> Dũng
~~~

Nếu DFS đánh dấu Dũng là “đã thăm” toàn cục sau đường thứ nhất, nó có thể bỏ qua đường thứ hai. Đó là lựa chọn đúng khi chỉ cần **node đích duy nhất**, nhưng sai khi cần **đếm số tuyến có thể đi**.

## 9. Vì sao phải giới hạn độ sâu?

Giả sử trung bình một node có **10 cạnh đi ra**. Trong trường hợp đơn giản chưa xét trùng node và mọi cạnh đều mở ra node mới:

| Độ sâu | Số node mới có thể xét tại tầng đó | Tổng node từ tầng 0 đến tầng đó |
| ---: | ---: | ---: |
| 0 | 1 | 1 |
| 1 | 10 | 11 |
| 2 | 100 | 111 |
| 3 | 1.000 | 1.111 |
| 4 | 10.000 | 11.111 |
| 5 | 100.000 | 111.111 |

Với hệ số phân nhánh trung bình \`b\` và độ sâu \`d\`, số đường ứng viên theo cấu trúc cây có thể tăng xấp xỉ theo \`b^d\`. Đây là phép **ước lượng minh họa để hình dung bùng nổ tổ hợp**, không phải công thức chính xác của mọi đồ thị: cạnh hội tụ, chu trình, lọc và quy tắc uniqueness làm thay đổi số lượng thực tế.

### 9.1. Độ sâu lớn gây ra điều gì?

- **Mở rộng số lượng lớn cạnh:** mất nhiều CPU, bộ nhớ và truy cập storage.
- **Trùng kết quả:** nhiều đường dẫn tới cùng node, cần \`DISTINCT\` hoặc tổng hợp.
- **Node bậc cao (supernode):** một tài khoản hoặc đối tượng có hàng triệu cạnh có thể làm một bước duyệt đã rất nặng.
- **Độ trễ khó dự đoán:** hai node bắt đầu có cùng depth limit nhưng số cạnh khác nhau dẫn tới chi phí rất khác.
- **Kết quả khó diễn giải:** liên kết cách nhau 8–10 hop có thể không còn giá trị cho một gợi ý xã hội, dù truy vấn trả về hàng triệu đối tượng.

**Giới hạn độ sâu vừa là quyết định kỹ thuật vừa là quyết định nghiệp vụ.** Tùy bài toán, 2 hop có thể đủ cho bạn của bạn, 3–4 hop có thể phù hợp để gợi ý kết nối, nhưng không có một ngưỡng mặc định áp dụng cho mọi đồ thị.

### 9.2. Độ sâu, số kết quả và thời gian thực thi

Đây là ba giới hạn khác nhau:

| Giới hạn | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Depth / hop limit** | Mỗi đường được dài tối đa bao nhiêu? | \`*1..3\` |
| **Result limit** | Client cần nhận bao nhiêu hàng kết quả? | \`LIMIT 20\` |
| **Execution budget** | Truy vấn được dùng bao nhiêu thời gian/tài nguyên? | Timeout, quota, memory cap |

Nếu viết:

~~~cypher
MATCH (a:Person {id: 'u1'})-[:FOLLOWS*1..10]->(p:Person)
RETURN DISTINCT p.id
LIMIT 20;
~~~

thì **\`LIMIT 20\` không phải hàng rào bảo đảm traversal chỉ đi qua 20 node hay 20 cạnh**. Truy vấn có thể phải tạo/xét nhiều kết quả trung gian, nhất là khi lọc, \`DISTINCT\`, sort hoặc aggregation tham gia.

Khi cần an toàn ở production, kết hợp giới hạn độ sâu hợp lý với điểm bắt đầu có selectivity cao, lọc cạnh/node, giới hạn đầu ra và ngân sách thực thi theo khả năng hệ quản trị.

## 10. Duyệt theo chiều rộng bằng Java: hiểu visited và maxDepth

Một thuật toán BFS nhỏ giúp nhìn rõ ý tưởng mà không phụ thuộc engine:

~~~java
import java.util.*;

public class GraphTraversalDemo {
    public static Map<String, Integer> reachableWithin(
            Map<String, List<String>> adjacency,
            String start,
            int maxDepth) {

        if (maxDepth < 0) {
            throw new IllegalArgumentException("maxDepth must be >= 0");
        }

        Map<String, Integer> distance = new LinkedHashMap<>();
        Queue<String> queue = new ArrayDeque<>();

        distance.put(start, 0);
        queue.add(start);

        while (!queue.isEmpty()) {
            String current = queue.remove();
            int depth = distance.get(current);
            if (depth >= maxDepth) {
                continue;
            }

            for (String next : adjacency.getOrDefault(current, List.of())) {
                if (!distance.containsKey(next)) {
                    distance.put(next, depth + 1);
                    queue.add(next);
                }
            }
        }

        // Chỉ trả người khác start; đổi nếu cần cả depth=0.
        distance.remove(start);
        return distance;
    }

    public static void main(String[] args) {
        Map<String, List<String>> graph = Map.of(
            "u1", List.of("u2", "u3"),
            "u2", List.of("u4"),
            "u3", List.of("u4", "u5"),
            "u4", List.of("u6"),
            "u5", List.of("u6"),
            "u6", List.of("u1"),
            "u7", List.of("u3")
        );

        System.out.println(reachableWithin(graph, "u1", 3));
    }
}
~~~

Kết quả kỳ vọng theo khoảng cách BFS:

~~~text
{u2=1, u3=1, u4=2, u5=2, u6=3}
~~~

Chương trình dùng \`distance\` làm cả bảng khoảng cách và **visited set**. Một node được thêm vào hàng đợi lần đầu tại số hop nhỏ nhất; sau đó không được mở rộng lại qua tuyến dài hơn.

### 10.1. Vì sao có điều kiện \`depth >= maxDepth\`?

Ở độ sâu \`maxDepth\`, ta **vẫn nhận node hiện tại là kết quả hợp lệ**, nhưng **không đi tiếp ra cạnh mới**. Nếu kiểm tra độ sâu sau khi thêm hàng xóm mà không cẩn thận, chương trình có thể đưa vào những node cách xa hơn giới hạn.

### 10.2. Độ phức tạp

Với BFS tiêu chuẩn trên đồ thị lưu dưới dạng adjacency list, nếu duyệt toàn bộ phần đồ thị có thể tiếp cận:

\[
O(V + E)
\]

với \`V\` là số node được xét và \`E\` là số cạnh liên quan. Khi có \`maxDepth\`, thuật toán chỉ mở rộng trong phạm vi giới hạn; chi phí phụ thuộc số node/cạnh thực sự được thăm, không nhất thiết bằng toàn bộ đồ thị.

Với truy vấn **liệt kê mọi đường đi**, chi phí có thể lớn hơn nhiều vì cùng node được chạm qua nhiều đường khác nhau. Do đó không được áp dụng máy móc độ phức tạp BFS node-unique cho mọi truy vấn Cypher variable-length.

### 10.3. Mở rộng theo node hay theo trạng thái?

Thuật toán trên chỉ theo dõi \`nodeId\`. Nếu bài toán đòi hỏi:

- Chỉ đi qua tối đa hai cạnh \`FOLLOWS\`, sau đó một cạnh \`AUTHORED\`.
- Mỗi đường không được dùng lại cùng một quan hệ.
- Chỉ đi qua node chưa bị cấm và chưa từng xuất hiện **trong chính đường đó**.
- Giới hạn tổng trọng số hoặc một bộ quy tắc chuyển trạng thái.

thì trạng thái duyệt có thể phải gồm **node + số bước + kiểu cạnh đã đi + chi phí + lịch sử đường**. Visited set theo node đơn thuần đôi khi loại bỏ nhánh hợp lệ và không còn đủ để mô tả chính xác bài toán.

## 11. So sánh pattern matching với traversal thủ công

| Khía cạnh | Mô tả bằng Cypher MATCH | Tự duyệt trong ứng dụng |
| --- | --- | --- |
| Cách diễn đạt | Nêu mẫu node/cạnh và điều kiện cần khớp | Viết vòng lặp, queue/stack, visited và lọc |
| Điểm mạnh | Diễn đạt quan hệ rõ; engine có thể tối ưu theo index và storage | Linh hoạt với luật tùy biến, cơ chế dừng và trạng thái đặc biệt |
| Rủi ro | Mẫu quá rộng có thể mở rộng số đường lớn; phụ thuộc cú pháp/engine | Nhiều round trip nếu lấy từng node/cạnh qua API; dễ tự tạo lỗi đồng thời hoặc chu kỳ |
| Độ sâu | Biểu diễn trực tiếp trong variable-length/quantified pattern | Kiểm tra bằng trường \`depth\` |
| Node trùng | Dùng \`DISTINCT\`, aggregation hoặc ngữ nghĩa path phù hợp | Dùng visited set khi bài toán cần node duy nhất |
| Kiểm tra hiệu năng | \`EXPLAIN\`, \`PROFILE\`, metric của DB | Tracing, số query, cache và profiling ứng dụng |

Nếu đã dùng graph database để phục vụ traversal, việc tải toàn bộ hàng triệu cạnh về Java rồi mới duyệt thường gây chi phí truyền dữ liệu lớn. Ngược lại, có trường hợp thuật toán chuyên dụng hoặc xử lý theo batch ở ứng dụng là hợp lý. Quyết định phụ thuộc kiểu truy vấn và khả năng engine.

## 12. Khớp mẫu nâng cao: nhiều điều kiện và quan hệ kết hợp

### 12.1. Tìm tác giả của bài viết, rồi người theo dõi tác giả

~~~cypher
MATCH (author:Person)-[:AUTHORED]->(post:Post {id: 'p2'})
MATCH (follower:Person)-[:FOLLOWS]->(author)
RETURN follower.name AS followerName,
       author.name AS authorName,
       post.title AS postTitle;
~~~

Theo dữ liệu mẫu, bài \`p2\` do Dũng viết; người theo dõi Dũng là Bình và Chi. Truy vấn này có điểm bắt đầu là **postId cụ thể**, rồi lần ngược theo tác giả và quan hệ theo dõi.

Nếu bắt đầu không có điều kiện \`Post{id:'p2'}\` mà cố khớp mọi bài viết và mọi người theo dõi, truy vấn trả lời một câu hỏi khác với phạm vi lớn hơn.

### 12.2. Đòi hỏi đồng thời hai nhánh quan hệ

Ví dụ “người được cả Bình và Chi theo dõi”:

~~~cypher
MATCH (binh:Person {id: 'u2'})-[:FOLLOWS]->(p:Person)
MATCH (chi:Person {id: 'u3'})-[:FOLLOWS]->(p)
RETURN DISTINCT p.id, p.name;
~~~

Kết quả là Dũng. Trong trường hợp này, \`p\` là **cùng một biến node** xuất hiện trong hai mẫu; do đó nó phải thỏa cả hai quan hệ, tương tự phép giao hai tập láng giềng.

### 12.3. Khi nào dùng OPTIONAL MATCH?

Nếu muốn trả về mọi người được An theo dõi, **kể cả người chưa viết bài**, một pattern bắt buộc nối tới bài viết sẽ loại những người không có post.

~~~cypher
MATCH (an:Person {id: 'u1'})-[:FOLLOWS]->(p:Person)
OPTIONAL MATCH (p)-[:AUTHORED]->(post:Post)
RETURN p.name, collect(post.title) AS titles
ORDER BY p.name;
~~~

\`OPTIONAL MATCH\` cho phép giữ người đã tìm được, dù không có node Post khớp, tương tự ý tưởng phép nối trái. Cần chú ý rằng cách đặt \`WHERE\` bên trong hay sau mẫu optional có thể ảnh hưởng ngữ nghĩa giữ lại các hàng không có kết quả.

### 12.4. Không thể thay pattern nghiệp vụ bằng tìm đường bất kỳ

Giả sử phân quyền tài liệu theo:

~~~text
(User)-[:MEMBER_OF]->(Team)-[:CAN_READ]->(Document)
~~~

Đây là **mẫu cố định hai loại cạnh theo đúng thứ tự**. Không nên thay bằng:

~~~text
(User)-[*1..5]-(Document)
~~~

vì một đường nối bất kỳ qua các loại quan hệ khác không có nghĩa là người dùng được phép đọc tài liệu. Dù hai node có nối được trong đồ thị, quyền truy cập phải được xác định bởi **quy tắc quan hệ được phép, hướng, thời điểm hiệu lực và trạng thái chính sách**. Giới hạn độ sâu không thay thế kiểm tra phân quyền.

## 13. Cách kiểm soát truy vấn trên đồ thị lớn

### 13.1. Neo bằng một ID có chỉ mục

Khi API nhận \`userId = u1\`, một query bắt đầu từ \`(:Person {id:'u1'})\` thường có điểm neo tốt hơn query bắt đầu từ mọi Person. Đặt constraint/index thích hợp trên ID giúp engine xác định node nguồn.

~~~cypher
EXPLAIN
MATCH (an:Person {id: 'u1'})-[:FOLLOWS*1..3]->(p:Person)
RETURN DISTINCT p.id;
~~~

\`EXPLAIN\` cung cấp kế hoạch dự kiến mà không cần thực thi truy vấn theo cách \`PROFILE\` thực thi. Cú pháp hiển thị, tên toán tử và chi tiết metric có thể khác theo phiên bản Neo4j.

### 13.2. Dùng PROFILE để quan sát số lượng mở rộng

~~~cypher
PROFILE
MATCH (an:Person {id: 'u1'})-[:FOLLOWS*1..3]->(p:Person)
RETURN DISTINCT p.id;
~~~

Khi phân tích:

- Có được **seek đến Person theo ID** hay đang scan nhiều node?
- Mỗi bước expand tạo bao nhiêu hàng trung gian?
- Số **DB hits** và lượng bộ nhớ trung gian tăng thế nào khi depth từ 2 lên 3?
- \`DISTINCT\` hoặc aggregation có phải xử lý rất nhiều đường trùng?
- Truy vấn mất thời gian ở bước tìm node bắt đầu, mở rộng quan hệ hay sort/aggregate?

Không dùng một thời gian chạy trên dữ liệu mẫu bảy người để kết luận latency của hệ thống có hàng triệu node và hàng tỷ cạnh.

### 13.3. Chọn hướng và kiểu cạnh cụ thể

Nếu nghiệp vụ chỉ đi theo \`FOLLOWS\`, nên nêu rõ:

~~~cypher
-[:FOLLOWS*1..3]->
~~~

thay vì:

~~~cypher
rel_1_to_3 = -[*1..3]-
~~~

Dòng thứ hai chỉ là cách minh họa một đường duyệt không giới hạn kiểu cạnh, không phải mã Cypher hoàn chỉnh. Nó có thể mở sang nhiều loại quan hệ như \`AUTHORED\`, \`LIKED\`, \`MEMBER_OF\`, làm tăng không gian tìm kiếm và khiến kết quả sai ý nghĩa.

### 13.4. Tránh supernode

Một node đại diện tài khoản nổi tiếng có thể có hàng triệu người theo dõi. Traversal theo chiều **đi vào** node đó có thể rất lớn, ngay cả khi giới hạn chỉ **một hop**.

Các hướng xử lý tùy nghiệp vụ:

- Lọc theo nhãn, loại cạnh, trạng thái hoặc điều kiện đủ sớm.
- Không mở rộng qua các loại quan hệ không phục vụ câu hỏi.
- Giới hạn số kết quả và có cơ chế pagination phù hợp.
- Tính trước số liệu hoặc nhóm đề xuất nếu truy vấn nóng và lặp lại.
- Dùng thuật toán chuyên biệt khi cần phân tích mạng rất lớn.
- Đo phân bố **degree** theo node, không chỉ lấy degree trung bình.

**Depth = 2** chưa chắc nhẹ nếu node đầu tiên có 2 triệu cạnh. Độ sâu chỉ là một trong nhiều yếu tố quyết định chi phí.

### 13.5. Phân trang và tính ổn định của kết quả

\`LIMIT\` có thể chặn số hàng trả về, nhưng để phân trang ổn định thường cần thêm **thứ tự rõ ràng**:

~~~cypher
MATCH (an:Person {id: 'u1'})-[:FOLLOWS*1..3]->(p:Person)
WHERE p <> an
RETURN DISTINCT p.id AS id, p.name AS name
ORDER BY id
LIMIT 20;
~~~

Với danh sách lớn, offset pagination (\`SKIP\`/\`LIMIT\`) có thể càng tốn kém về sau và còn có nguy cơ bị trùng/bỏ sót nếu đồ thị thay đổi giữa các trang. Có thể xem xét cursor dựa trên khóa sắp xếp, thuật toán gợi ý có checkpoint, hoặc tập kết quả đã tính trước theo yêu cầu nhất quán của API.

## 14. Nhầm lẫn thường gặp khi truy vấn đồ thị

| Nhận định dễ sai | Điều cần hiểu chính xác |
| --- | --- |
| “Có đường nối nghĩa là có quyền truy cập.” | Chỉ đường đúng kiểu cạnh, hướng và chính sách mới tạo quyền hợp lệ. |
| “Mỗi người chỉ xuất hiện một lần khi MATCH.” | Một người có thể xuất hiện nhiều hàng qua nhiều đường khác nhau. |
| “\`LIMIT 10\` nghĩa là chỉ duyệt 10 cạnh.” | LIMIT thường khống chế kết quả, không bảo đảm giới hạn mọi mở rộng trung gian. |
| “\`*1..3\` chỉ trả đường dài đúng 3.” | Nó cho phép đường dài 1, 2 hoặc 3. |
| “\`*0..3\` không thể trả node bắt đầu.” | Đường dài 0 có thể trả chính node nguồn. |
| “Node đã từng xuất hiện thì luôn bị cấm trong path.” | Chính sách uniqueness phụ thuộc loại đường đi và ngữ nghĩa truy vấn. |
| “Đường đi ngắn nhất luôn có chi phí thấp nhất.” | Ít hop chỉ tương đương tối ưu trọng số khi phù hợp, chẳng hạn mọi cạnh có trọng số bằng nhau. |
| “BFS và DFS luôn trả kết quả giống nhau khi bị giới hạn thời gian.” | Nếu dừng sớm, thứ tự khám phá và kết quả tạm thời có thể khác; DFS không bảo đảm shortest hop. |
| “Tăng maxDepth chỉ tăng thời gian tuyến tính.” | Số nhánh và đường đi có thể tăng rất nhanh theo depth. |
| “Có index trên mọi thuộc tính sẽ tăng tốc mọi traversal.” | Index giúp định vị/lọc theo điều kiện; chi phí mở rộng quan hệ còn phụ thuộc degree và mẫu đường đi. |

## 15. Thực hành tự kiểm chứng trên đồ thị mẫu

### Thực hành 1 — Một bước, hai bước và ba bước

Chạy lần lượt:

~~~cypher
MATCH (:Person {id: 'u1'})-[:FOLLOWS*1..1]->(p:Person)
RETURN DISTINCT p.name ORDER BY p.name;
~~~

~~~cypher
MATCH (:Person {id: 'u1'})-[:FOLLOWS*2..2]->(p:Person)
RETURN DISTINCT p.name ORDER BY p.name;
~~~

~~~cypher
MATCH (:Person {id: 'u1'})-[:FOLLOWS*1..3]->(p:Person)
RETURN DISTINCT p.name ORDER BY p.name;
~~~

Kỳ vọng:

- **1 hop:** Bình, Chi.
- **2 hop:** Dũng, Em.
- **1–3 hop:** Bình, Chi, Dũng, Em, Giang.

Hãy giải thích vì sao \`1..3\` lấy hợp của nhiều độ sâu và vì sao \`DISTINCT\` cần thiết khi có hai đường đến Dũng hoặc Giang.

### Thực hành 2 — Đếm các đường dài đúng 3

~~~cypher
MATCH path = (:Person {id: 'u1'})
             -[:FOLLOWS*3..3]->
             (:Person {id: 'u6'})
RETURN [n IN nodes(path) | n.id] AS route;
~~~

Vẽ từng tuyến đi qua Bình, Chi, Dũng và Em. Đếm số **đường đi**, không nhầm với số node đích; tất cả đều dẫn đến Giang nhưng qua trung gian khác nhau.

### Thực hành 3 — Thử đổi hướng cạnh

~~~cypher
MATCH (:Person {id: 'u1'})<-[:FOLLOWS]-(p:Person)
RETURN p.name;
~~~

Giải thích vì sao kết quả khác với truy vấn \`-[:FOLLOWS]->\`. Hãy thử bỏ mũi tên để xem hàng xóm theo cả hai hướng.

### Thực hành 4 — Tìm chu trình

~~~cypher
MATCH path = (start:Person {id: 'u1'})
             -[:FOLLOWS*4..4]->
             (finish:Person {id: 'u1'})
RETURN [n IN nodes(path) | n.id] AS route;
~~~

Tìm các tuyến quay lại An sau đúng bốn bước. Thử \`*1..3\` và lý giải vì sao không có đường quay lại An trong giới hạn đó.

### Thực hành 5 — Thêm một node có nhiều cạnh

Tạo một thành viên mới và cho người này theo dõi nhiều node (hoặc thêm nhiều node nhỏ trong dữ liệu thử nghiệm). Quan sát thời gian và số hàng trung gian của truy vấn depth 1, 2, 3 bằng \`PROFILE\`. Không cần dùng dữ liệu khổng lồ; mục tiêu là thấy **số hàng trung gian tăng theo số cạnh và độ sâu**.

### Thực hành 6 — Tự thiết kế mẫu khớp

Đặt yêu cầu:

> “Tìm những bài viết của người được Chi theo dõi trực tiếp hoặc qua tối đa một người trung gian; không liệt kê trùng bài viết.”

Viết pattern \`(Chi)-[:FOLLOWS*1..2]->(Tác giả)-[:AUTHORED]->(Post)\`, thêm \`DISTINCT\`, rồi giải thích điều kiện lọc nào khiến kết quả thay đổi. Nếu muốn chỉ lấy bài có chủ đề NoSQL, hãy bổ sung thuộc tính hoặc quan hệ chủ đề trong dữ liệu mẫu, thay vì dựa vào tên tiêu đề một cách ngầm định.

## 16. Bài toán nâng cao: giới hạn theo nhiều quy tắc cùng lúc

Giả sử nền tảng cộng tác có yêu cầu:

> “Gợi ý tối đa 10 người có thể tiếp cận từ An trong không quá 3 bước theo dõi, chưa được An theo dõi trực tiếp, ưu tiên ít hop hơn.”

Đây là một yêu cầu gồm nhiều ràng buộc:

1. Điểm bắt đầu là \`Person{id:'u1'}\`.
2. Chỉ đi theo cạnh **\`FOLLOWS\` có hướng đi ra**.
3. Độ sâu nằm trong \`2..3\`, bởi người được theo dõi trực tiếp ở độ sâu 1 không thuộc nhóm đề xuất.
4. Kết quả chỉ gồm node khác An.
5. Một người xuất hiện một lần, ưu tiên số hop nhỏ nhất.
6. Trả tối đa 10 người.

Một truy vấn minh họa:

~~~cypher
MATCH path = (an:Person {id: 'u1'})-[:FOLLOWS*2..3]->(p:Person)
WHERE p <> an
WITH p, min(length(path)) AS distance
RETURN p.id AS id, p.name AS name, distance
ORDER BY distance ASC, id ASC
LIMIT 10;
~~~

Theo dữ liệu mẫu, Dũng và Em đứng ở khoảng cách 2, Giang ở khoảng cách 3. Đây là đúng ý nghĩa “người chưa được theo dõi trực tiếp” trong đồ thị mẫu. Tuy nhiên, với dữ liệu thực có **cạnh trực tiếp và đồng thời có đường dài 2–3 tới cùng một người**, truy vấn trên vẫn có thể trả người đó vì nó chỉ xét các đường dài 2–3.

Để thực sự **loại mọi người đã được An theo dõi trực tiếp**, phải thêm điều kiện về sự tồn tại của cạnh trực tiếp:

~~~cypher
MATCH path = (an:Person {id: 'u1'})-[:FOLLOWS*2..3]->(p:Person)
WHERE p <> an
  AND NOT EXISTS {
    MATCH (an)-[:FOLLOWS]->(p)
  }
WITH p, min(length(path)) AS distance
RETURN p.id AS id, p.name AS name, distance
ORDER BY distance ASC, id ASC
LIMIT 10;
~~~

Đây là một ví dụ điển hình về khác biệt giữa **giới hạn độ sâu của path được khớp** và **điều kiện loại một quan hệ tồn tại trong toàn đồ thị**. Một giới hạn độ sâu được viết đúng cú pháp vẫn có thể chưa đủ để mô tả đúng mọi điều kiện nghiệp vụ.

### 16.1. Khi dữ liệu thay đổi liên tục

Nếu Bình bỏ theo dõi Dũng đúng lúc truy vấn đang chạy, kết quả có phản ánh trước hay sau thay đổi phụ thuộc ngữ nghĩa transaction/isolation của database. Một truy vấn nhanh có thể phục vụ gợi ý tốt, nhưng những quyết định như phân quyền hoặc chuyển tiền cần ranh giới kiểm tra trạng thái nghiêm ngặt hơn.

Đối với gợi ý xã hội, có thể chấp nhận kết quả được cập nhật chậm hoặc tính trước. Đối với kiểm soát quyền, cần xem xét chính sách nhất quán, thu hồi quyền và kiểm tra lại ở thời điểm thực hiện hành động.

## 17. Quy trình thiết kế truy vấn traversal trong dự án

Khi xuất hiện một yêu cầu liên quan đến đồ thị, có thể đi theo quy trình:

1. **Viết câu hỏi bằng ngôn ngữ nghiệp vụ:** tìm ai, từ đâu, qua loại quan hệ nào, trong phạm vi mấy bước?
2. **Xác định điểm neo:** userId, documentId, productId hoặc node đã biết. Kiểm tra constraint/index cần thiết.
3. **Vẽ mẫu đồ thị:** node bắt đầu, node trung gian, node đích, kiểu cạnh và hướng cụ thể.
4. **Quy định đường hợp lệ:** cho phép lặp node/cạnh không; một node đích hay mọi path; đúng N hop hay tối đa N hop?
5. **Đặt giới hạn:** depth, kiểu node/cạnh, số kết quả, timeout và ngân sách tài nguyên.
6. **Xác định tiêu chí sắp xếp:** ít hop nhất, số quan hệ chung, độ mới, điểm gợi ý hay trọng số.
7. **Chạy trên dữ liệu ví dụ có hội tụ và chu trình:** kiểm chứng các trường hợp dẫn tới node trùng hoặc quay lại node nguồn.
8. **Quan sát trên tải thực:** dùng kế hoạch truy vấn và metric cho số hàng mở rộng, latency, memory và những supernode.
9. **Xử lý biến động dữ liệu:** phân trang, transaction, độ mới và cơ chế phát hiện thay đổi theo yêu cầu nghiệp vụ.

Sơ đồ quyết định ngắn:

~~~mermaid
flowchart TD
    A["Cần tìm gì trong graph?"] --> B{"Chỉ một cạnh hay nhiều cạnh?"}
    B -->|Một cạnh| C["MATCH theo loại và hướng cụ thể"]
    B -->|Nhiều cạnh| D{"Biết chính xác số bước?"}
    D -->|Có| E["Pattern có số cạnh cố định"]
    D -->|Không| F["Path độ dài thay đổi + maxDepth"]
    E --> G{"Cần node hay tất cả đường?"}
    F --> G
    G -->|Node duy nhất| H["DISTINCT / BFS / nhóm theo node"]
    G -->|Đường đi| I["Quy tắc path uniqueness và giới hạn kết quả"]
    H --> J["EXPLAIN, PROFILE và đo trên tải thật"]
    I --> J
    C --> J
~~~

## Kết luận

**Duyệt đồ thị** cho biết cách đi từ node bắt đầu tới những node liên quan. **Khớp mẫu** xác định chính xác loại thực thể, hướng và chuỗi quan hệ được phép. **Giới hạn độ sâu** giữ đường đi trong phạm vi có ý nghĩa nghiệp vụ và ngăn mở rộng không kiểm soát.

Để thiết kế truy vấn graph NoSQL đúng và có thể vận hành:

- Xác định **node bắt đầu có ID/index**, kiểu cạnh và hướng rõ ràng.
- Phân biệt **node đích duy nhất** với **mọi đường đi**, vì một node có thể được tiếp cận qua nhiều tuyến.
- Dùng **hop limit** để giới hạn chiều dài đường, đồng thời kiểm soát số kết quả và ngân sách thực thi.
- Hiểu **chu trình, node trùng và quy tắc visited/uniqueness** trước khi diễn giải kết quả.
- Dùng **shortest hop** khi cần ít cạnh nhất; dùng thuật toán trọng số nếu “ngắn nhất” nghĩa là chi phí thấp nhất.
- Kiểm chứng bằng dữ liệu có **đường hội tụ, chu trình và node bậc cao**, rồi đo kế hoạch truy vấn trên tải thực.

Một truy vấn đồ thị có giá trị khi nó trả lời đúng **mẫu quan hệ mà nghiệp vụ định nghĩa**, trong phạm vi **độ sâu và tài nguyên được kiểm soát**.

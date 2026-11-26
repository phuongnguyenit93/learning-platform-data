# Lưu truy vấn mẫu, quản lý tập lệnh và tái tạo bộ dữ liệu thực hành với Neo4j

Khi học Neo4j, việc chạy một vài câu Cypher trong Neo4j Browser giúp khám phá đồ thị rất nhanh. Tuy nhiên, lịch sử câu lệnh trong một phiên làm việc không đủ để chia sẻ bài tập, xem lại thay đổi hoặc dựng lại dữ liệu sau khi thử nghiệm. Một môi trường thực hành đáng tin cậy cần có **truy vấn mẫu được lưu thành tệp**, **tập lệnh có thứ tự chạy rõ ràng** và **bộ dữ liệu có thể tái tạo từ trạng thái xác định**.

Bài này thuộc phần **Công cụ làm việc** của mô-đun **DATABASE_ENGINE_GRAPH_NEO4J**. Ví dụ sử dụng property graph của Neo4j: node và relationship mang thuộc tính, truy vấn bằng Cypher, ràng buộc và index hỗ trợ toàn vẹn dữ liệu. Quy trình có thể áp dụng khi học Cypher, kiểm tra truy vấn đường đi, thử Java Driver hoặc chuẩn bị dữ liệu cho Spring Data Neo4j.

## 1. Mục tiêu và nguyên tắc

Sau bài học, bạn có thể:

1. Lưu và đặt tên truy vấn Cypher để tra cứu, chạy lại và đưa vào quản lý phiên bản.
2. Chia tập lệnh thành các bước tạo constraint, nạp dữ liệu, truy vấn, kiểm tra và dọn dữ liệu.
3. Tạo một bộ dữ liệu mẫu bằng `MERGE` để chạy lặp lại mà không sinh node hoặc relationship trùng theo khóa định danh.
4. Phân biệt **nạp lại** dữ liệu với **khôi phục đúng dữ liệu ban đầu**, và xác minh kết quả bằng số lượng node, relationship và câu truy vấn nghiệp vụ.
5. Biết khi nào dùng `LOAD CSV`, cách truyền tham số và cách xem kế hoạch thực thi của truy vấn.

| Thứ cần lưu | Nội dung | Lợi ích |
| --- | --- | --- |
| Truy vấn mẫu | Các câu `MATCH`, `WHERE`, `RETURN`, `EXPLAIN`, `PROFILE` | Dễ học lại, tái hiện lỗi, so sánh cách viết truy vấn |
| Tập lệnh khởi tạo | Constraint/index và dữ liệu mẫu | Thiết lập môi trường thực hành nhất quán |
| Tập lệnh kiểm tra | Các truy vấn xác nhận cấu trúc và dữ liệu | Phát hiện thiếu dữ liệu hoặc quan hệ |
| Tập lệnh đặt lại | Xóa riêng dữ liệu thí nghiệm | Bắt đầu bài tập từ trạng thái sạch |
| README và tệp CSV | Điều kiện chạy, thứ tự chạy, dữ liệu đầu vào | Người khác có thể lặp lại cùng bài thực hành |

> Nguyên tắc cốt lõi: **mỗi lần thực hành phải biết đã chạy phiên bản tập lệnh nào, với bộ dữ liệu nào và kỳ vọng kết quả ra sao**.

## 2. Tổ chức thư mục tập lệnh

Đặt những tệp dưới đây trong một thư mục thực hành có thể đưa vào Git. Đây là **cấu trúc đề xuất**; các đoạn code trong bài sẽ là nội dung của những tệp tương ứng khi bạn tự tạo dự án thực hành.

~~~text
neo4j-lab/
├── README.md
├── cypher/
│   ├── 00_constraints.cypher
│   ├── 10_seed.cypher
│   ├── 20_examples.cypher
│   ├── 30_verify.cypher
│   └── 90_reset.cypher
└── data/
    └── courses.csv
~~~

Quy ước tên `00_`, `10_`, `20_` thể hiện thứ tự xử lý. Tách `90_reset.cypher` khỏi các bước nạp để tránh xóa dữ liệu ngoài ý muốn. Lưu mỗi câu lệnh Cypher hoàn chỉnh, có dấu `;` kết thúc. Ghi rõ **mục đích, đầu vào, kết quả kỳ vọng và lưu ý phiên bản** ở đầu tệp hoặc trong `README.md`.

Một tệp `.cypher` có thể chứa nhiều câu lệnh, nhưng không nên giả định toàn bộ tệp tự động trở thành một giao dịch duy nhất. Khi cần tính nguyên tử hoặc phục hồi sau lỗi, hãy thiết kế giao dịch và cách xử lý lỗi phù hợp với công cụ chạy, phiên bản Neo4j và yêu cầu thực tế.

## 3. Thiết kế bộ dữ liệu mẫu có thể tái tạo

Ta xây dựng bài toán đơn giản: học viên đăng ký khóa học; mỗi khóa học bao gồm nhiều chủ đề.

~~~mermaid
flowchart LR
    A["DemoLearner<br/>learnerId, name"] -->|ENROLLED_IN<br/>enrolledAt| B["DemoCourse<br/>code, title"]
    B -->|COVERS| C["DemoTopic<br/>slug, title"]
~~~

Ba loại node đều mang thêm nhãn `LabPractice` để có thể nhận diện dữ liệu của riêng bài thực hành. Các khóa định danh ổn định là `learnerId`, `code` và `slug`; không dùng mã nội bộ do cơ sở dữ liệu cấp làm khóa nghiệp vụ.

| Nhãn node | Mẫu dữ liệu | Số lượng kỳ vọng |
| --- | --- | ---: |
| `DemoLearner` | L001/An, L002/Bình, L003/Chi | 3 |
| `DemoCourse` | C001/Neo4j căn bản, C002/Cypher tối ưu, C003/Spring Data Neo4j | 3 |
| `DemoTopic` | property-graph, cypher, java-driver | 3 |
| `ENROLLED_IN` | L001→C001, L001→C002, L002→C001, L003→C003 | 4 |
| `COVERS` | C001→property-graph, C001→cypher, C002→cypher, C003→java-driver | 4 |

Khi hoàn thành, đồ thị có **9 node** và **8 relationship** thuộc bộ dữ liệu thực hành. Những con số này tạo ra một mốc kiểm chứng cụ thể.

### Bước 1 — Khai báo constraint

Nội dung tệp `cypher/00_constraints.cypher`:

~~~cypher
CREATE CONSTRAINT demo_learner_id IF NOT EXISTS
FOR (l:DemoLearner)
REQUIRE l.learnerId IS UNIQUE;

CREATE CONSTRAINT demo_course_code IF NOT EXISTS
FOR (c:DemoCourse)
REQUIRE c.code IS UNIQUE;

CREATE CONSTRAINT demo_topic_slug IF NOT EXISTS
FOR (t:DemoTopic)
REQUIRE t.slug IS UNIQUE;
~~~

Constraint duy nhất đảm bảo không thể có hai node cùng nhãn `DemoLearner` trùng `learnerId` (tương tự với hai nhãn còn lại). Trong Neo4j, unique constraint cũng tạo index phục vụ tra cứu theo thuộc tính được ràng buộc; vì vậy không cần tạo thêm range index trùng trên chính các khóa này. Cú pháp trên phù hợp với dòng Neo4j 5.x; khi làm việc với phiên bản khác, kiểm tra cú pháp DDL tương ứng.

### Bước 2 — Nạp dữ liệu bằng MERGE

Nội dung tệp `cypher/10_seed.cypher`:

~~~cypher
// 1. Học viên
MERGE (l:DemoLearner:LabPractice {learnerId: 'L001'})
SET l.name = 'An';

MERGE (l:DemoLearner:LabPractice {learnerId: 'L002'})
SET l.name = 'Bình';

MERGE (l:DemoLearner:LabPractice {learnerId: 'L003'})
SET l.name = 'Chi';

// 2. Khóa học
MERGE (c:DemoCourse:LabPractice {code: 'C001'})
SET c.title = 'Neo4j căn bản';

MERGE (c:DemoCourse:LabPractice {code: 'C002'})
SET c.title = 'Cypher tối ưu';

MERGE (c:DemoCourse:LabPractice {code: 'C003'})
SET c.title = 'Spring Data Neo4j';

// 3. Chủ đề
MERGE (t:DemoTopic:LabPractice {slug: 'property-graph'})
SET t.title = 'Property graph';

MERGE (t:DemoTopic:LabPractice {slug: 'cypher'})
SET t.title = 'Truy vấn Cypher';

MERGE (t:DemoTopic:LabPractice {slug: 'java-driver'})
SET t.title = 'Neo4j Java Driver';

// 4. Quan hệ ghi danh: tìm hai đầu mút theo khóa, sau đó MERGE quan hệ
MATCH (l:DemoLearner {learnerId: 'L001'})
MATCH (c:DemoCourse {code: 'C001'})
MERGE (l)-[r:ENROLLED_IN]->(c)
SET r.enrolledAt = date('2026-01-10');

MATCH (l:DemoLearner {learnerId: 'L001'})
MATCH (c:DemoCourse {code: 'C002'})
MERGE (l)-[r:ENROLLED_IN]->(c)
SET r.enrolledAt = date('2026-01-11');

MATCH (l:DemoLearner {learnerId: 'L002'})
MATCH (c:DemoCourse {code: 'C001'})
MERGE (l)-[r:ENROLLED_IN]->(c)
SET r.enrolledAt = date('2026-01-12');

MATCH (l:DemoLearner {learnerId: 'L003'})
MATCH (c:DemoCourse {code: 'C003'})
MERGE (l)-[r:ENROLLED_IN]->(c)
SET r.enrolledAt = date('2026-01-13');

// 5. Quan hệ khóa học bao gồm chủ đề
MATCH (c:DemoCourse {code: 'C001'})
MATCH (t:DemoTopic {slug: 'property-graph'})
MERGE (c)-[:COVERS]->(t);

MATCH (c:DemoCourse {code: 'C001'})
MATCH (t:DemoTopic {slug: 'cypher'})
MERGE (c)-[:COVERS]->(t);

MATCH (c:DemoCourse {code: 'C002'})
MATCH (t:DemoTopic {slug: 'cypher'})
MERGE (c)-[:COVERS]->(t);

MATCH (c:DemoCourse {code: 'C003'})
MATCH (t:DemoTopic {slug: 'java-driver'})
MERGE (c)-[:COVERS]->(t);
~~~

**Vì sao chọn `MERGE`?** `CREATE` luôn tạo phần tử mới, còn `MERGE` tìm mẫu tương ứng trước khi tạo. Với node, hãy đặt trong `MERGE` khóa định danh ổn định và cập nhật thuộc tính mô tả bằng `SET`. Với relationship, trước hết `MATCH` hai node đã có, rồi `MERGE` relationship giữa đúng hai đầu mút; đây là cách tránh tạo node ngoài dự kiến khi liên kết. Constraint bảo vệ khóa node, còn quy tắc duy nhất của từng loại relationship vẫn cần được thiết kế và kiểm chứng theo nghiệp vụ.

Chạy lại tập lệnh này với dữ liệu đầu vào không đổi sẽ giữ nguyên 9 node và 8 relationship. Nhưng lưu ý: **`MERGE` không xóa dữ liệu dư** đã được thêm bằng những lần thử nghiệm khác. Muốn trở về một mốc dữ liệu *chính xác*, hãy dùng bước reset có kiểm soát rồi seed lại.

## 4. Lưu và sử dụng truy vấn mẫu

Nội dung tệp `cypher/20_examples.cypher` có thể gồm các truy vấn độc lập sau:

~~~cypher
// Q01: Học viên đang đăng ký những khóa nào?
MATCH (l:DemoLearner:LabPractice)-[:ENROLLED_IN]->(c:DemoCourse:LabPractice)
RETURN l.learnerId AS learnerId,
       l.name AS learner,
       collect(c.title) AS enrolledCourses
ORDER BY learnerId;

// Q02: Hai bước từ học viên đến chủ đề qua khóa học
MATCH (l:DemoLearner:LabPractice {learnerId: 'L001'})
      -[:ENROLLED_IN]->
      (c:DemoCourse:LabPractice)
      -[:COVERS]->
      (t:DemoTopic:LabPractice)
RETURN c.code AS courseCode,
       t.slug AS topicSlug
ORDER BY courseCode, topicSlug;

// Q03: Số học viên theo khóa học (kể cả khóa chưa có lượt đăng ký)
MATCH (c:DemoCourse:LabPractice)
OPTIONAL MATCH (l:DemoLearner:LabPractice)-[:ENROLLED_IN]->(c)
RETURN c.code AS courseCode, count(l) AS learnerCount
ORDER BY courseCode;
~~~

Các kết quả quan trọng để tự đối chiếu: Q01 trả về ba học viên; Q02 trả về ba hàng (hai chủ đề của C001 và một chủ đề của C002); Q03 lần lượt trả về `C001: 2`, `C002: 1`, `C003: 1`. Danh sách do `collect()` tạo ra không nên được giả định có thứ tự cố định nếu truy vấn không chủ động sắp xếp trước bước gom nhóm.

Khi lưu truy vấn, nên ghi chú **câu hỏi nghiệp vụ**, **tham số cần truyền**, **hình dạng đầu ra** và **điểm cần chú ý về hiệu năng**. Ví dụ, nếu muốn lọc học viên linh hoạt, dùng tham số thay cho việc ghép chuỗi truy vấn:

~~~cypher
MATCH (l:DemoLearner:LabPractice {learnerId: $learnerId})
      -[:ENROLLED_IN]->(c:DemoCourse:LabPractice)
RETURN l.name AS learner, c.code AS courseCode
ORDER BY courseCode;
~~~

Trong Neo4j Browser, có thể khai báo tham số riêng bằng lệnh Browser `:param learnerId => 'L001'`, sau đó chạy câu Cypher phía trên. Lệnh `:param` là lệnh của công cụ, không phải câu lệnh Cypher thuần; không trộn tùy tiện lệnh riêng của Browser vào tập lệnh `.cypher` dùng để chạy tự động. Trong Java Driver hoặc Spring Data Neo4j, truyền tham số bằng API của thư viện thay vì nối giá trị người dùng vào chuỗi Cypher.

Khi tìm hiểu hiệu năng, chạy một truy vấn với `EXPLAIN` để xem kế hoạch dự kiến hoặc `PROFILE` để thực thi và xem số liệu thực tế:

~~~cypher
EXPLAIN
MATCH (l:DemoLearner {learnerId: 'L001'})
      -[:ENROLLED_IN]->(c:DemoCourse)
RETURN c.code;
~~~

Có thể kiểm tra kế hoạch dùng index/constraint khi tra cứu theo `learnerId`. Tuy nhiên, bộ dữ liệu chỉ có vài node nên số liệu thời gian trên ví dụ này **không đủ** để kết luận một thiết kế index hay truy vấn sẽ nhanh hơn trên dữ liệu lớn.

## 5. Kiểm tra rằng bộ dữ liệu đã được tạo đúng

Nội dung tệp `cypher/30_verify.cypher`:

~~~cypher
// V01: Tổng node của riêng bài thực hành: mong đợi 9
MATCH (n:LabPractice)
RETURN count(n) AS nodeCount;

// V02: Số node theo loại: mỗi loại 3
MATCH (n:LabPractice)
RETURN labels(n) AS nodeLabels, count(*) AS total
ORDER BY nodeLabels;

// V03: Tổng relationship nối giữa hai node thực hành: mong đợi 8
MATCH (a:LabPractice)-[r]->(b:LabPractice)
RETURN count(r) AS relationshipCount;

// V04: Phân loại relationship: COVERS = 4, ENROLLED_IN = 4
MATCH (a:LabPractice)-[r]->(b:LabPractice)
RETURN type(r) AS relationshipType, count(r) AS total
ORDER BY relationshipType;

// V05: Mỗi khóa học có bao nhiêu học viên?
MATCH (c:DemoCourse:LabPractice)
OPTIONAL MATCH (l:DemoLearner:LabPractice)-[:ENROLLED_IN]->(c)
RETURN c.code AS courseCode, count(l) AS learnerCount
ORDER BY courseCode;
~~~

| Kiểm tra | Kết quả mong đợi |
| --- | --- |
| V01 | `nodeCount = 9` |
| V02 | 3 node `DemoLearner`, 3 node `DemoCourse`, 3 node `DemoTopic` (mỗi node đồng thời có nhãn `LabPractice`) |
| V03 | `relationshipCount = 8` |
| V04 | `COVERS = 4`, `ENROLLED_IN = 4` |
| V05 | `C001 = 2`, `C002 = 1`, `C003 = 1` |

Đây là các truy vấn **báo cáo kết quả để đối chiếu**, chưa phải bộ kiểm thử tự động tự phát sinh lỗi khi số lượng sai. Trong dự án thực, có thể thêm assertion trong bài kiểm thử tích hợp (ví dụ chạy Cypher bằng Java Driver, sau đó so sánh kết quả với giá trị kỳ vọng) để quy trình CI phát hiện dữ liệu không khớp.

## 6. Chạy tập lệnh bằng Neo4j Browser và cypher-shell

Bạn cần một Neo4j đang chạy, tài khoản có quyền tạo schema và ghi dữ liệu trong một **database thực hành riêng**, và công cụ `cypher-shell` nếu chạy từ terminal.

**Cách thủ công:** Mở Neo4j Browser, kết nối vào đúng database, dán và thực thi nội dung các tệp theo thứ tự `00_constraints.cypher` → `10_seed.cypher` → `20_examples.cypher` → `30_verify.cypher`. Cách này phù hợp khi học từng câu và quan sát graph trực tiếp.

**Cách qua terminal:** Từ thư mục `neo4j-lab`, lần lượt chạy:

~~~powershell
cypher-shell -a bolt://localhost:7687 -u neo4j -d neo4j -f cypher/00_constraints.cypher
cypher-shell -a bolt://localhost:7687 -u neo4j -d neo4j -f cypher/10_seed.cypher
cypher-shell -a bolt://localhost:7687 -u neo4j -d neo4j -f cypher/20_examples.cypher
cypher-shell -a bolt://localhost:7687 -u neo4j -d neo4j -f cypher/30_verify.cypher
~~~

Đổi địa chỉ, tài khoản và tên database theo môi trường của bạn; công cụ có thể yêu cầu nhập mật khẩu. **Không đưa mật khẩu thật vào tệp tập lệnh, README hoặc Git.** Khi tự động hóa, lấy thông tin đăng nhập từ secret của môi trường chạy và dừng quy trình nếu một bước thất bại. Không chuyển sang bước kiểm tra và công bố thành công khi bước tạo dữ liệu bị lỗi.

Với mỗi lần sửa script, lưu phiên bản trong Git cùng thông điệp mô tả thay đổi; khi thay đổi cấu trúc dữ liệu hoặc giá trị mẫu, cập nhật cả phần **kết quả mong đợi**. Các tệp seed phục vụ thực hành khác với migration schema của hệ thống sản xuất: không dùng reset dữ liệu thực tế để thay cho migration.

## 7. Tái tạo bộ dữ liệu từ một trạng thái sạch

Nội dung tệp `cypher/90_reset.cypher`:

~~~cypher
// CHỈ chạy trên database thực hành dành riêng cho bộ dữ liệu này.
MATCH (n:LabPractice)
DETACH DELETE n;
~~~

Lệnh trên xóa node mang nhãn `LabPractice` **và mọi relationship nối với các node ấy**. Vì vậy, nhãn thực hành phải chỉ được dùng trong dữ liệu mà bạn chủ động quản lý; tốt nhất dành một database riêng để thử nghiệm. Đây là lệnh xóa dữ liệu có chủ đích, không đưa vào chuỗi nạp dữ liệu mặc định.

Khi muốn lặp lại bài học từ đúng bộ dữ liệu ban đầu:

1. Chọn đúng database thí nghiệm, kiểm tra đây không phải môi trường đang chứa dữ liệu cần giữ.
2. Chạy `90_reset.cypher` một lần để loại bỏ dữ liệu thực hành cũ.
3. Chạy `00_constraints.cypher` (an toàn khi constraint đã tồn tại với cùng định nghĩa).
4. Chạy `10_seed.cypher` và sau đó `30_verify.cypher`.
5. Chỉ bắt đầu bài tập hoặc kiểm thử sau khi kết quả kiểm tra khớp các số lượng kỳ vọng.

Constraint vẫn tồn tại sau khi xóa node. Nếu cần tái hiện hoàn toàn cả schema, phiên bản DB và cấu hình, hãy dựng một database thí nghiệm mới bằng quy trình tạo môi trường được tài liệu hóa; không tự động xóa constraint dùng chung. Tính tái tạo còn phụ thuộc vào **phiên bản Neo4j, cấu hình, dữ liệu nguồn và thứ tự chạy tập lệnh**.

## 8. Mở rộng: quản lý dữ liệu đầu vào bằng CSV

Khi bộ dữ liệu lớn hơn, lưu dữ liệu gốc trong CSV giúp người học và nhóm phát triển có thể kiểm tra sự thay đổi của fixture. Ví dụ `data/courses.csv`:

~~~csv
code,title
C001,Neo4j căn bản
C002,Cypher tối ưu
C003,Spring Data Neo4j
~~~

Sau khi bố trí tệp CSV trong vị trí import mà **máy chủ Neo4j** được phép đọc, có thể nạp bằng:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///courses.csv' AS row
WITH row
WHERE row.code IS NOT NULL AND trim(row.code) <> ''
MERGE (c:DemoCourse:LabPractice {code: trim(row.code)})
SET c.title = trim(row.title);
~~~

`file:///courses.csv` được Neo4j giải quyết từ thư mục import được cấu hình ở **phía server**, không phải tự động từ thư mục terminal đang đứng. Khi dùng Docker, cần mount dữ liệu và kiểm tra quyền đọc trong container; khi dùng dịch vụ Neo4j được quản lý, chính sách đọc file cục bộ/URL có thể khác. Lệnh CSV trên là một **phương án nạp node khóa học thay cho phần tương ứng trong seed**, không cần chạy cả hai nếu muốn giữ quy trình đơn giản.

Với CSV chứa các quan hệ, nên nạp node trước, sau đó nạp relationship bằng cách `MATCH` hai đầu mút theo khóa, rồi `MERGE` cạnh. Chuẩn hóa định dạng ngày, mã định danh và giá trị rỗng trước khi nạp; nếu nguồn có thể thay đổi, lưu phiên bản hoặc checksum của fixture để xác định chính xác dữ liệu đã dùng.

Đối với tập dữ liệu lớn, cần xem xét cách chia giao dịch, giới hạn bộ nhớ và loại index trước khi import. Ví dụ trong bài chỉ có chín node nên không cần tối ưu nạp hàng loạt.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Chạy seed lần hai làm tăng số node | Dùng `CREATE` thay `MERGE`, hoặc khóa định danh không ổn định | Dùng khóa nghiệp vụ cố định, `MERGE` và unique constraint |
| Node không trùng nhưng relationship tăng | Tạo cạnh bằng `CREATE` trong mỗi lần nạp | `MATCH` hai đầu mút, `MERGE` cạnh với đúng định danh nghiệp vụ |
| `MERGE` thành công nhưng dữ liệu kiểm tra vẫn thừa | Seed không tự xóa bản ghi cũ | Reset phạm vi lab rồi seed lại trong database thực hành riêng |
| `LOAD CSV` không tìm thấy file | Tệp ở máy client, không nằm trong thư mục import của server | Kiểm tra import directory, mount Docker và quyền đọc |
| Truy vấn mẫu lỗi vì thiếu tham số | Chưa khai báo hoặc chưa truyền giá trị `$learnerId` | Cấu hình tham số ở công cụ/ứng dụng trước khi chạy |
| Kết quả giữa hai máy khác nhau | Khác fixture, thứ tự script, cấu hình hoặc phiên bản Neo4j | Ghi các điều kiện tái hiện trong README và kiểm tra sau seed |
| Truy vấn trả về đúng dữ liệu nhưng chậm | Dữ liệu lớn, mẫu MATCH rộng, index chưa hợp lý | Dùng `EXPLAIN`/`PROFILE`, kiểm tra các điều kiện lọc và kế hoạch thực thi |

## 10. Checklist và bài luyện tập

Trước khi chia sẻ bộ bài thực hành, hãy tự xác nhận:

- [ ] Từng tệp `.cypher` có tên rõ nghĩa, lệnh hoàn chỉnh và thứ tự chạy được mô tả.
- [ ] Có constraint cho khóa định danh dùng trong `MERGE`.
- [ ] Seed chạy lại không làm tăng số node hoặc relationship kỳ vọng.
- [ ] Có dữ liệu mẫu đủ để kiểm tra truy vấn một cạnh, nhiều cạnh và tổng hợp.
- [ ] Có truy vấn xác minh số lượng và kết quả nghiệp vụ.
- [ ] Reset chỉ tác động đến nhãn/dữ liệu của bài thực hành và dùng trên database phù hợp.
- [ ] README ghi phiên bản Neo4j, cách kết nối, cách import và các kết quả mong đợi.
- [ ] Mật khẩu và các bí mật môi trường không nằm trong các tệp được commit.

**Bài tập thực hành:**

1. Chạy `00_constraints`, `10_seed`, `30_verify` hai lần. Ghi lại số node và relationship sau mỗi lần để xác nhận tính lặp lại.
2. Thêm học viên `L004` cùng quan hệ ghi danh vào `C002`. Chỉnh truy vấn Q03 để thấy số lượng thay đổi, sau đó reset và seed để quay về dữ liệu ban đầu.
3. Viết một truy vấn tìm những học viên cùng đăng ký ít nhất một khóa, trả về cặp học viên và mã khóa chung; tránh trả lại cùng một cặp theo hai thứ tự ngược nhau.
4. Tách khóa học ra CSV, chạy `LOAD CSV` và so sánh kết quả kiểm tra với cách seed trực tiếp.
5. Thay giá trị cố định của `learnerId` bằng tham số, thử `EXPLAIN` và giải thích tác dụng của unique constraint trong bước tìm node ban đầu.

Khi toàn bộ script, fixture và kết quả mong đợi được quản lý cùng nhau, bạn có thể chuyển một bài thực hành Neo4j từ máy cá nhân sang máy của đồng đội, chạy lại các truy vấn và truy tìm nguyên nhân khi dữ liệu hoặc kết quả thay đổi.

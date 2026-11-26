# Hàm điều kiện trên danh sách: all, any, none và single trong Neo4j Cypher

Khi truy vấn một **property graph** bằng Neo4j, ta thường cần kiểm tra **nhiều phần tử cùng lúc**: tất cả điểm số có đạt chuẩn không, có khóa học nào chưa hoàn thành không, danh sách quyền có chứa giá trị bị cấm không, hay đúng một bước trong đường đi có đặc tính cần tìm không. Cypher cung cấp bốn hàm điều kiện trên danh sách: `all()`, `any()`, `none()` và `single()`.

Bài học thuộc chương **Biểu thức và hàm** của mô-đun **DATABASE_ENGINE_GRAPH_NEO4J**. Kiến thức này áp dụng cho danh sách thuộc tính của node/relationship, danh sách thu thập từ các quan hệ, cũng như danh sách node và relationship trên một đường đi. Nó hỗ trợ các tác vụ mô hình hóa dữ liệu liên kết và truy vấn quan hệ/đường đi bằng Cypher; khi phối hợp với index, constraint, Java Driver hoặc Spring Data Neo4j, cần hiểu rõ cả tính đúng đắn của điều kiện lẫn tác động của `null`.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Đọc và viết đúng cú pháp bốn hàm, hiểu biến phần tử và điều kiện `WHERE`.
2. Phân biệt “mọi”, “có ít nhất một”, “không có phần tử nào” và “đúng một phần tử” thỏa điều kiện.
3. Dự đoán kết quả khi danh sách **rỗng**, **`null`** hoặc chứa phần tử khiến điều kiện trả về `null`.
4. Kết hợp hàm với `MATCH`, `OPTIONAL MATCH`, `collect()`, `nodes(path)` và `relationships(path)`.
5. Tránh các lỗi logic thường gặp khi kiểm tra dữ liệu thiếu, danh sách có phần tử trùng và điều kiện chạy trên nhiều dòng dữ liệu.

## 2. Cú pháp và ý nghĩa

Cả bốn hàm đều nhận **một danh sách đầu vào**, một **biến đại diện cho từng phần tử** và một **biểu thức điều kiện**:

~~~cypher
all(x IN listExpression WHERE predicate)
any(x IN listExpression WHERE predicate)
none(x IN listExpression WHERE predicate)
single(x IN listExpression WHERE predicate)
~~~

Trong đó:

- `listExpression` trả về danh sách, chẳng hạn `[1, 2, 3]`, thuộc tính danh sách `p.scores`, `collect(c)`, `nodes(path)` hoặc `relationships(path)`.
- `x` là biến cục bộ cho từng phần tử được xét; có thể đổi tên phù hợp ngữ cảnh như `score`, `course`, `node`, `rel`.
- `predicate` là biểu thức logic, ví dụ `score >= 7`, `course.published = true` hoặc `rel.active = true`.
- Kết quả của mỗi hàm là **một giá trị logic**: `true`, `false` hoặc `null`, không phải một danh sách các phần tử.

| Hàm | Ý nghĩa trực quan | Điều kiện để trả về `true` khi không có `null` |
| --- | --- | --- |
| `all(x IN xs WHERE P(x))` | Tất cả phần tử đều thỏa `P` | Mọi phần tử thỏa `P` |
| `any(x IN xs WHERE P(x))` | Có ít nhất một phần tử thỏa `P` | Tồn tại ít nhất một phần tử thỏa `P` |
| `none(x IN xs WHERE P(x))` | Không phần tử nào thỏa `P` | Không có phần tử thỏa `P` |
| `single(x IN xs WHERE P(x))` | Đúng một phần tử thỏa `P` | Có chính xác một phần tử thỏa `P` |

Ví dụ có thể chạy trực tiếp trong Neo4j Browser:

~~~cypher
WITH [2, 4, 7, 9] AS numbers
RETURN
  all(n IN numbers WHERE n > 0) AS allPositive,
  any(n IN numbers WHERE n % 2 <> 0) AS hasOdd,
  none(n IN numbers WHERE n < 0) AS noNegative,
  single(n IN numbers WHERE n = 7) AS exactlyOneSeven;
~~~

**Kết quả:** cả bốn cột là `true`. Tất cả số đều dương; có số lẻ; không số nào âm; và có đúng một phần tử bằng 7.

Hai trường hợp dễ nhầm:

~~~cypher
WITH [4, 4, 9] AS numbers
RETURN
  any(n IN numbers WHERE n = 4) AS atLeastOneFour,
  single(n IN numbers WHERE n = 4) AS exactlyOneFour;
~~~

`atLeastOneFour = true` nhưng `exactlyOneFour = false` vì **hai vị trí** trong danh sách cùng thỏa `n = 4`. `single()` đếm phần tử thỏa điều kiện theo vị trí, không đếm số **giá trị phân biệt**.

> `all()`, `any()`, `none()` và `single()` là **hàm điều kiện trên danh sách** (list predicate functions), không phải hàm tổng hợp như `count()`. Chúng đánh giá từng phần tử của *danh sách trong một dòng*; để gom phần tử từ nhiều dòng trước, thường cần `collect()`.

## 3. Thực hành trên một danh sách điểm số

Hãy xét danh sách các bản ghi học viên. Đoạn Cypher dưới đây là **ví dụ độc lập**, không cần tạo node hoặc sửa cơ sở dữ liệu:

~~~cypher
WITH [
  {id: 'L01', scores: [8, 9, 10]},
  {id: 'L02', scores: [6, 8]},
  {id: 'L03', scores: []},
  {id: 'L04', scores: [7, null]}
] AS learners
UNWIND learners AS learner
RETURN
  learner.id AS learnerId,
  all(s IN learner.scores WHERE s >= 7) AS allPassing,
  any(s IN learner.scores WHERE s >= 9) AS hasExcellentScore,
  none(s IN learner.scores WHERE s < 5) AS noFailingScore,
  single(s IN learner.scores WHERE s >= 8) AS exactlyOneHighScore
ORDER BY learnerId;
~~~

Kết quả mong đợi:

| Học viên | `allPassing` | `hasExcellentScore` | `noFailingScore` | `exactlyOneHighScore` |
| --- | --- | --- | --- | --- |
| L01: `[8, 9, 10]` | `true` | `true` | `true` | `false` |
| L02: `[6, 8]` | `false` | `false` | `true` | `true` |
| L03: `[]` | `true` | `false` | `true` | `false` |
| L04: `[7, null]` | `null` | `null` | `null` | `null` |

Phân tích:

- **L01:** cả ba điểm đạt từ 7; có điểm 9 hoặc 10; không có điểm dưới 5; có **ba** điểm từ 8 trở lên nên `single()` trả về `false`.
- **L02:** có điểm 6 khiến `allPassing` sai; không có điểm từ 9; không điểm nào dưới 5; có đúng một điểm từ 8 trở lên.
- **L03:** với danh sách rỗng, “mọi phần tử thỏa” đúng theo quy tắc logic, “không phần tử nào thỏa” cũng đúng; nhưng không có phần tử nào làm `any()` hoặc `single()` đúng.
- **L04:** không biết điểm thứ hai nên chưa thể xác định có phải toàn bộ điểm đạt 7, có điểm đạt 9, có điểm dưới 5 hoặc có đúng một điểm đạt 8 hay không. Các kết quả là `null`.

Đây là lý do cần xác định **ý nghĩa nghiệp vụ của danh sách rỗng và điểm chưa biết** trước khi dùng các hàm này trong điều kiện lọc.

## 4. Bảng kết quả với danh sách rỗng và `null`

Cypher dùng logic ba giá trị: `true`, `false` và `null` (không biết/không có giá trị). Nếu một phần tử làm `P(x)` trở thành `null`, kết quả tổng thể tùy vào việc các phần tử khác có đủ quyết định kết quả hay không.

Bảng sau diễn giải đầu vào theo **kết quả của `P(x)` trên từng phần tử**, không phải giá trị phần tử:

| Kết quả `P(x)` theo thứ tự | `all` | `any` | `none` | `single` |
| --- | --- | --- | --- | --- |
| Danh sách rỗng `[]` | `true` | `false` | `true` | `false` |
| `[true, true]` | `true` | `true` | `false` | `false` |
| `[true, false]` | `false` | `true` | `false` | `true` |
| `[false, false]` | `false` | `false` | `true` | `false` |
| `[true, null]` | `null` | `true` | `false` | `null` |
| `[false, null]` | `false` | `null` | `null` | `null` |
| `[true, true, null]` | `null` | `true` | `false` | `false` |
| `[null]` | `null` | `null` | `null` | `null` |

Cách suy luận:

- `all()`: chỉ cần **một kết quả false** là `false`; nếu không có false nhưng có null thì `null`; nếu mọi kết quả đều true (kể cả không có phần tử) thì `true`.
- `any()`: chỉ cần **một kết quả true** là `true`; nếu không có true nhưng có null thì `null`; nếu tất cả false hoặc rỗng thì `false`.
- `none()`: có bất kỳ true nào thì `false`; không có true nhưng có null thì `null`; tất cả false hoặc rỗng thì `true`.
- `single()`: có **ít nhất hai true** thì chắc chắn `false`; có đúng một true và các phần tử khác đều false thì `true`; chưa biết có đúng một true vì có null thì `null`; không có true và không có null thì `false`.

Bạn có thể kiểm chứng bảng bằng đoạn Cypher này:

~~~cypher
WITH [true, null] AS values
RETURN
  all(x IN values WHERE x = true) AS resultAll,
  any(x IN values WHERE x = true) AS resultAny,
  none(x IN values WHERE x = true) AS resultNone,
  single(x IN values WHERE x = true) AS resultSingle;
~~~

Lưu ý: `null = true` trả về `null`, không phải `false`.

### 4.1. Danh sách rỗng khác với danh sách không tồn tại

Danh sách rỗng `[]` chứa **0 phần tử**; `null` có nghĩa là **không có danh sách để xét**:

~~~cypher
WITH [] AS emptyList, null AS missingList
RETURN
  all(x IN emptyList WHERE x > 0) AS allEmpty,
  all(x IN missingList WHERE x > 0) AS allMissing,
  none(x IN emptyList WHERE x < 0) AS noneEmpty,
  any(x IN missingList WHERE x < 0) AS anyMissing;
~~~

Kết quả lần lượt là `true`, `null`, `true`, `null`.

Vì `all()` và `none()` trên danh sách rỗng trả về `true`, câu hỏi “tất cả điểm đều đạt chuẩn” có thể cho kết quả đúng dù chưa có điểm nào. Khi nghiệp vụ yêu cầu ít nhất một điểm, hãy kiểm tra số lượng phần tử:

~~~cypher
WITH [] AS scores
RETURN
  size(scores) > 0
  AND all(s IN scores WHERE s >= 7) AS hasScoresAndAllPass;
~~~

Kết quả: `false`. Cách kết hợp này dùng được cho danh sách điểm, danh sách quyền và tập quan hệ đã được thu thập.

### 4.2. Có thể nhận diện `null` một cách tường minh

Nếu muốn coi điểm thiếu là **không đạt**, có thể chuyển giá trị logic không biết thành false ngay trong điều kiện:

~~~cypher
WITH [7, null] AS scores
RETURN
  all(s IN scores WHERE coalesce(s >= 7, false)) AS allPassStrict,
  all(s IN scores WHERE s IS NOT NULL AND s >= 7) AS allPassExplicit;
~~~

Hai biểu thức đều trả về `false`, trong khi `all(s IN scores WHERE s >= 7)` tự nhiên trả về `null`.

Ngược lại, nếu cần **phân biệt thiếu dữ liệu với điểm không đạt**, đừng chuyển mọi `null` thành `false`. Có thể dùng `CASE`:

~~~cypher
WITH [7, null] AS scores
RETURN CASE
  WHEN scores IS NULL THEN 'missing-list'
  WHEN size(scores) = 0 THEN 'empty-list'
  WHEN any(s IN scores WHERE s IS NULL) THEN 'contains-unknown'
  WHEN all(s IN scores WHERE s >= 7) THEN 'passed'
  ELSE 'failed'
END AS assessment;
~~~

Kết quả: `contains-unknown`. Ở đây `s IS NULL` cho kết quả logic xác định (`true` hoặc `false`) ngay cả khi `s` là `null`.

> `coalesce(listProperty, [])` là lựa chọn có ý thức: nó **đổi danh sách không tồn tại thành danh sách rỗng**. Điều này khiến `all()` và `none()` có thể trả về `true`, nên không phải lúc nào cũng phù hợp.

## 5. Áp dụng trên property graph

Ngoài danh sách hằng, các hàm còn hữu ích với **thuộc tính dạng list của node** và các danh sách được tạo từ **relationship** hoặc **path**.

### 5.1. Kiểm tra thuộc tính danh sách của node

Giả sử mỗi học viên được lưu thành node `:Learner` với thuộc tính `scores` là danh sách điểm:

~~~cypher
MATCH (l:Learner)
WHERE l.scores IS NOT NULL
  AND size(l.scores) > 0
  AND all(score IN l.scores WHERE score >= 7)
RETURN l.id AS learnerId, l.scores AS scores
ORDER BY learnerId;
~~~

Truy vấn chỉ chọn học viên có danh sách điểm **tồn tại, không rỗng và tất cả điểm từ 7 trở lên**. Nếu có điểm `null` và không có điểm nào làm điều kiện chắc chắn sai, `all()` trả về `null`; `WHERE` chỉ giữ những dòng có điều kiện là `true`.

Thay `all()` bằng `any()` khi yêu cầu chỉ cần **một** điểm đạt 7:

~~~cypher
MATCH (l:Learner)
WHERE any(score IN l.scores WHERE score >= 7)
RETURN l.id, l.scores;
~~~

Dùng `none()` để lọc danh sách không chứa mã bị cấm:

~~~cypher
MATCH (u:User)
WHERE u.roles IS NOT NULL
  AND none(role IN u.roles WHERE role IN ['BANNED', 'SUSPENDED'])
RETURN u.id, u.roles;
~~~

Điều kiện trên chỉ chọn node không có vai trò bị cấm **và** có thuộc tính `roles`. Nếu hệ thống quy ước thiếu `roles` là “không có quyền”, có thể xử lý danh sách thiếu theo quy tắc nghiệp vụ riêng.

### 5.2. Thu thập các node liên kết bằng `collect()`

Mô hình quan hệ:

~~~mermaid
flowchart LR
    L["Learner"] -->|ENROLLED_IN| C["Course"]
    C -->|COVERS| T["Topic"]
~~~

Nếu một học viên có thể đăng ký nhiều khóa học, muốn tìm học viên có **mọi khóa đã đăng ký đều xuất bản**, trước hết thu các node `Course` liên quan thành một danh sách:

~~~cypher
MATCH (l:Learner)
OPTIONAL MATCH (l)-[:ENROLLED_IN]->(c:Course)
WITH l, collect(c) AS courses
WHERE size(courses) > 0
  AND all(course IN courses WHERE course.published = true)
RETURN l.id AS learnerId,
       [course IN courses | course.code] AS courseCodes
ORDER BY learnerId;
~~~

Cần chú ý:

1. `OPTIONAL MATCH` giữ học viên chưa có khóa học; với trường hợp không khớp, `c` có thể là `null`.
2. `collect(c)` **bỏ qua các giá trị null**, nên một học viên không có khóa học liên kết sẽ có danh sách khóa học rỗng.
3. `size(courses) > 0` ngăn học viên chưa đăng ký khóa nào lọt vào kết quả chỉ vì `all()` trên `[]` trả về `true`.
4. Nếu `course.published` bị thiếu, biểu thức `course.published = true` là `null`. Khi không có phần tử nào khiến `all()` chắc chắn sai, dòng đó sẽ không vượt qua `WHERE`.

Để tìm học viên có **ít nhất một khóa chưa xuất bản**:

~~~cypher
MATCH (l:Learner)-[:ENROLLED_IN]->(c:Course)
WITH l, collect(c) AS courses
WHERE any(course IN courses WHERE course.published = false)
RETURN l.id AS learnerId;
~~~

Truy vấn này không coi `published = null` là `false`. Nếu muốn xem “chưa rõ trạng thái” cũng là trường hợp cần xử lý, hãy viết điều kiện tường minh:

~~~cypher
MATCH (l:Learner)-[:ENROLLED_IN]->(c:Course)
WITH l, collect(c) AS courses
WHERE any(course IN courses
          WHERE course.published IS NULL OR course.published = false)
RETURN l.id AS learnerId;
~~~

### 5.3. Kiểm tra đường đi bằng `nodes(path)` và `relationships(path)`

Đối với truy vấn đường đi, `nodes(p)` trả về danh sách node trên đường đi và `relationships(p)` trả về danh sách relationship theo thứ tự của đường đi đó. Ta có thể đánh giá từng bước mà không cần tự tách đường đi thành những truy vấn riêng.

Ví dụ tìm các đường phụ thuộc dài từ 1 đến 4 bước chỉ đi qua những relationship đang hoạt động:

~~~cypher
MATCH p = (source:Service {id: $sourceId})
          -[:DEPENDS_ON*1..4]->
          (target:Service)
WHERE all(rel IN relationships(p) WHERE rel.active = true)
RETURN p;
~~~

Đoạn trên dùng cú pháp đường đi độ dài biến thiên truyền thống của Neo4j Cypher; cú pháp, cách lập kế hoạch và khả năng tối ưu đường đi có thể thay đổi tùy phiên bản. Quan trọng ở đây là **`relationships(p)` trả về một list** dùng được với `all()`.

Nếu cần đường đi có **ít nhất một** dịch vụ quan trọng:

~~~cypher
MATCH p = (source:Service {id: $sourceId})
          -[:DEPENDS_ON*1..4]->
          (target:Service)
WHERE any(n IN nodes(p) WHERE n.critical = true)
RETURN p;
~~~

Nếu yêu cầu **không bước nào** có độ trễ vượt ngưỡng:

~~~cypher
MATCH p = (source:Service {id: $sourceId})
          -[:DEPENDS_ON*1..4]->
          (target:Service)
WHERE none(rel IN relationships(p) WHERE rel.latencyMs > 200)
RETURN p;
~~~

Nếu yêu cầu **đúng một** node trên đường đi là điểm kiểm tra:

~~~cypher
MATCH p = (source:Service {id: $sourceId})
          -[:DEPENDS_ON*1..4]->
          (target:Service)
WHERE single(n IN nodes(p) WHERE n.checkpoint = true)
RETURN p;
~~~

Lưu ý rằng `nodes(p)` bao gồm **cả node đầu và cuối**. Nếu thuộc tính `active`, `latencyMs` hoặc `checkpoint` có thể bị thiếu, hãy xác định rõ chúng phải khiến đường đi bị loại, được giữ hay cần kiểm tra dữ liệu bổ sung.

## 6. Lỗi thường gặp

| Nhầm lẫn | Hệ quả | Cách viết/diễn giải phù hợp |
| --- | --- | --- |
| Dùng `all()` để yêu cầu “có ít nhất một phần tử” | Danh sách rỗng vẫn cho `true` | Thêm `size(xs) > 0` |
| Nghĩ `single()` tương đương `any()` | Danh sách có hai phần tử phù hợp bị `single()` loại | Chọn `any()` cho “ít nhất một”, `single()` cho “đúng một” |
| Cho rằng `null` luôn tương đương `false` | Có thể hiểu sai kết quả ba giá trị | Kiểm tra dữ liệu thiếu; dùng `IS NULL` hoặc `coalesce()` nếu nghiệp vụ yêu cầu |
| Dùng `coalesce(xs, [])` không xem xét ngữ nghĩa | Dữ liệu chưa ghi có thể được coi như danh sách rỗng hợp lệ | Phân biệt “không có dữ liệu” và “danh sách được xác nhận rỗng” |
| Dùng `collect()` rồi cho rằng luôn có phần tử | `collect(null)` không thêm phần tử | Kiểm tra `size(xs)`; phân biệt `count(*)` và `count(variable)` khi cần |
| Nghĩ `single()` đếm giá trị khác nhau | `[4, 4]` có hai phần tử phù hợp | Dùng danh sách đã loại trùng nếu nghiệp vụ dựa trên giá trị phân biệt |
| Gọi hàm trên từng dòng rồi tưởng đã xét toàn bộ quan hệ | Mỗi lần gọi chỉ xét danh sách ở dòng hiện tại | `WITH key, collect(value) AS xs` rồi mới gọi hàm |
| Gọi `none()` với điều kiện ngược sai | “Không có điểm dưới 5” khác “tất cả điểm trên 5” khi có điểm bằng 5 | Viết đúng bất đẳng thức; kiểm tra riêng trường hợp `null` |

### 6.1. Khác biệt giữa phủ định và đổi lượng từ

Với điều kiện chỉ có `true` và `false`, có thể hình dung:

- `none(x IN xs WHERE P(x))` tương ứng với “không tồn tại `x` thỏa `P(x)`”.
- `all(x IN xs WHERE P(x))` tương ứng với “không có `x` khiến `P(x)` sai”.
- `single(x IN xs WHERE P(x))` đòi hỏi số phần tử làm `P(x)` đúng bằng một.

Nhưng trong Cypher, phải xét thêm giá trị **`null`** và việc biểu thức phủ định `NOT` xử lý `null` cũng trả về `null`. Không thể tùy tiện thay điều kiện `P(x)` bằng điều kiện “ngược nghĩa” nếu có giá trị thiếu.

Ví dụ, `none(n IN xs WHERE n < 5)` khi `xs = [null]` cho `null`, chứ không chứng minh được “mọi điểm đều lớn hơn hoặc bằng 5”.

### 6.2. Phạm vi biến và nhiều dòng

Biến phần tử do hàm khai báo chỉ phục vụ biểu thức bên trong hàm. Đặt tên rõ nghĩa để tránh nhầm với biến của `MATCH` hoặc `WITH`:

~~~cypher
MATCH (l:Learner)-[:ENROLLED_IN]->(course:Course)
WITH l, collect(course) AS enrolledCourses
WHERE single(c IN enrolledCourses WHERE c.level = 'ADVANCED')
RETURN l.id AS learnerId;
~~~

Truy vấn xét **đúng một khóa cấp độ ADVANCED trên mỗi học viên**. Nếu muốn “đúng một khóa học phân biệt” nhưng đồ thị có thể có nhiều relationship đăng ký dẫn đến cùng node, hãy cân nhắc `collect(DISTINCT course)` để loại bản ghi trùng khi gom nhóm.

## 7. Hiệu năng và cách kiểm tra

Bốn hàm không tự tạo index. Chúng đánh giá biểu thức đối với các phần tử của một danh sách đã có trong dòng truy vấn. Khi dữ liệu lớn:

- Dùng điều kiện `MATCH` và `WHERE` trên khóa định danh để thu hẹp node/relationship trước khi xây dựng các danh sách lớn; tận dụng index hoặc constraint phù hợp khi tìm node gốc.
- Tránh `collect()` mọi relationship trong toàn đồ thị khi chỉ quan tâm một học viên hoặc một đường đi. Danh sách lớn gây tốn bộ nhớ và làm nhiều phần tử phải được đánh giá.
- Truyền tham số (như `$sourceId`) qua Java Driver, Spring Data Neo4j hoặc công cụ chạy Cypher; không ghép giá trị đầu vào trực tiếp vào chuỗi truy vấn.
- Dùng `EXPLAIN` để xem kế hoạch dự kiến và `PROFILE` để xem thực thi thực tế. Kiểm tra số dòng được tạo ra trước bước gom nhóm, dung lượng dữ liệu và số phép duyệt đồ thị.

Ví dụ xem kế hoạch cho một truy vấn lọc thuộc tính danh sách:

~~~cypher
EXPLAIN
MATCH (l:Learner {id: $learnerId})
WHERE any(score IN l.scores WHERE score >= 9)
RETURN l.id;
~~~

Index trên `:Learner(id)` có thể giúp tìm node, nhưng **không đồng nghĩa** Neo4j dùng index để kiểm tra từng phần tử của `l.scores`. Muốn kết luận về hiệu năng, cần đo trên dữ liệu và phiên bản Neo4j thực tế.

## 8. Bài luyện tập có đáp án gợi ý

Hãy tự thử trước khi xem kết quả bên dưới. Các truy vấn độc lập và không sửa database.

**Bài 1 — Đọc đúng số lượng phần tử thỏa điều kiện.** Với `xs = [3, 6, 9]` và `P(x) := x % 3 = 0`, hãy dự đoán bốn hàm.

~~~cypher
WITH [3, 6, 9] AS xs
RETURN
  all(x IN xs WHERE x % 3 = 0) AS a,
  any(x IN xs WHERE x % 3 = 0) AS b,
  none(x IN xs WHERE x % 3 = 0) AS c,
  single(x IN xs WHERE x % 3 = 0) AS d;
~~~

**Đáp án:** `a = true`, `b = true`, `c = false`, `d = false` vì có ba phần tử thỏa điều kiện.

**Bài 2 — Danh sách rỗng.** Sửa truy vấn sao cho chỉ được chấp nhận khi có ít nhất một khóa học và tất cả khóa đều hoàn tất:

~~~cypher
WITH [] AS completionFlags
RETURN size(completionFlags) > 0
   AND all(done IN completionFlags WHERE done = true) AS validCompletion;
~~~

**Đáp án:** `validCompletion = false`. Nếu bỏ `size(completionFlags) > 0`, kết quả sẽ là `true`.

**Bài 3 — Phân biệt `false` và `null`.** Dự đoán:

~~~cypher
WITH [false, null] AS flags
RETURN
  any(f IN flags WHERE f = true) AS hasTrue,
  none(f IN flags WHERE f = true) AS hasNoTrue,
  single(f IN flags WHERE f = true) AS exactlyOneTrue;
~~~

**Đáp án:** cả ba là `null`: phần tử chưa biết có thể khiến điều kiện về sự tồn tại hoặc số lượng phần tử thỏa thay đổi.

**Bài 4 — Đường đi.** Viết điều kiện để giữ đường đi có **đúng một** relationship mang `rel.priority = 'HIGH'`. Gợi ý:

~~~cypher
MATCH p = (a:Service)-[:DEPENDS_ON*1..3]->(b:Service)
WHERE single(rel IN relationships(p) WHERE rel.priority = 'HIGH')
RETURN p;
~~~

Thử đổi `single()` thành `any()` và giải thích sự khác biệt khi một đường đi có hai relationship cùng mức ưu tiên HIGH.

**Bài 5 — Nghiệp vụ dữ liệu thiếu.** Cho `scores = [8, null]`, hãy viết hai biểu thức: một biểu thức giữ ý nghĩa “chưa đủ dữ liệu”, một biểu thức coi điểm thiếu là không đạt.

~~~cypher
WITH [8, null] AS scores
RETURN
  all(s IN scores WHERE s >= 7) AS unknownAllowed,
  all(s IN scores WHERE coalesce(s >= 7, false)) AS missingIsFailure;
~~~

**Đáp án:** `unknownAllowed = null`, `missingIsFailure = false`.

## 9. Checklist khi áp dụng vào truy vấn thực tế

- [ ] Xác định đúng lượng từ: **tất cả**, **ít nhất một**, **không có**, hay **đúng một**.
- [ ] Xác định danh sách có thể rỗng hoặc `null` hay không; mô tả cách xử lý trước khi viết điều kiện.
- [ ] Xác định có phần tử trùng hay có trường hợp thuộc tính của phần tử bằng `null` không.
- [ ] Nếu dùng `collect()`, kiểm tra cách nhóm theo `WITH`, null bị bỏ qua và nhu cầu `DISTINCT`.
- [ ] Với đường đi, xác định cần xét node, relationship hay cả hai, và có tính node đầu/cuối không.
- [ ] Dùng dữ liệu nhỏ để kiểm tra kết quả với các trường hợp đúng, sai, rỗng và không xác định.
- [ ] Với dữ liệu lớn, dùng `EXPLAIN`/`PROFILE` để kiểm tra kế hoạch truy vấn thay vì dự đoán tốc độ chỉ từ cách viết.

Bốn hàm `all()`, `any()`, `none()` và `single()` giúp chuyển những yêu cầu nghiệp vụ về **số lượng phần tử thỏa điều kiện** thành Cypher ngắn gọn. Để kết quả chính xác, luôn xét **danh sách rỗng, dữ liệu thiếu và các phần tử trùng** cùng với cấu trúc node–relationship của đồ thị.

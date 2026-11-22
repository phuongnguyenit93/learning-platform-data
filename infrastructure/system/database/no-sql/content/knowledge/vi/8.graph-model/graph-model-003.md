# Biểu diễn quan hệ có hướng, nhiều cạnh và thuộc tính của quan hệ

## 1. Bối cảnh và mục tiêu bài học

Trong cơ sở dữ liệu NoSQL mô hình đồ thị, **nút (node)** mô tả đối tượng và **cạnh (edge/relationship)** mô tả cách các đối tượng liên hệ với nhau. Khi bài toán chủ yếu hỏi “A liên hệ với B theo cách nào?”, “A đã tương tác với B bao nhiêu lần?” hoặc “Mối quan hệ còn hiệu lực hay không?”, phần quan trọng nhất thường nằm ở **hướng, số lượng và thuộc tính của cạnh**.

Hãy xét một nền tảng học trực tuyến:

- Người học An **theo dõi** Bình; việc này không tự có nghĩa Bình theo dõi An.
- An vừa **theo dõi** vừa **hướng dẫn** Bình; hai mối liên hệ có ý nghĩa khác nhau dù nối cùng hai người.
- An đăng ký khóa “NoSQL căn bản” trong kỳ học đầu năm, sau đó đăng ký lại vào kỳ cuối năm. Hai lần đăng ký có ngày bắt đầu, trạng thái và kết quả riêng.
- Một khóa học **yêu cầu** một khóa khác làm điều kiện tiên quyết; hướng của quan hệ giúp phân biệt “phụ thuộc vào” và “được phụ thuộc bởi”.

Trong những ví dụ này, mô hình chỉ có cặp định danh nút sẽ không mô tả đủ ý nghĩa nghiệp vụ. Ta cần một **property graph** hỗ trợ cạnh có kiểu, hướng và thuộc tính; tùy cơ sở dữ liệu, có thể cho phép **nhiều cạnh song song** nối cùng một cặp nút.

Sau bài học, bạn có thể:

1. Biểu diễn quan hệ có hướng và đọc đúng chiều xuất phát/đích.
2. Phân biệt quan hệ ngược chiều, quan hệ khác kiểu và nhiều cạnh cùng kiểu giữa hai nút.
3. Đặt thuộc tính đúng trên cạnh và nhận diện khi nào quan hệ nên trở thành nút nghiệp vụ riêng.
4. Viết mẫu truy vấn để lấy một cạnh, tất cả các cạnh, quan hệ hai chiều và lịch sử quan hệ.
5. Thiết kế định danh, quy tắc chống trùng, vòng đời và ràng buộc của quan hệ trong môi trường NoSQL.

**Phạm vi kỹ thuật:** Các ví dụ dùng **property graph** và cú pháp **Cypher kiểu Neo4j** để minh họa. Một số cơ sở dữ liệu đồ thị hoặc phiên bản sản phẩm có cú pháp, giới hạn thuộc tính và cơ chế ràng buộc khác nhau. Khái niệm hướng cạnh và nhiều quan hệ không phụ thuộc vào cú pháp của một hãng.

## 2. Quan hệ có hướng (directed relationship)

### 2.1. Cạnh có điểm đầu, điểm cuối và kiểu quan hệ

Trong một đồ thị có hướng, cạnh có thể được mô tả bằng bộ:

\[
e = (u,\ t,\ v)
\]

Trong đó **u** là nút nguồn, **v** là nút đích, **t** là kiểu cạnh. Ví dụ:

~~~text
(An:Learner) -[:FOLLOWS]-> (Bình:Learner)
~~~

Cạnh trên có nghĩa **An theo dõi Bình**. Không thể từ đó suy ra **Bình theo dõi An**.

Một phát biểu khác:

~~~text
(Khóa Graph:Course) -[:REQUIRES]-> (Khóa NoSQL:Course)
~~~

có nghĩa “Khóa Graph yêu cầu kiến thức từ Khóa NoSQL”. Nếu muốn tìm các khóa bị ảnh hưởng khi Khóa NoSQL thay đổi, ta phải đi **ngược hướng REQUIRES** từ Khóa NoSQL tới những khóa phụ thuộc.

### 2.2. Hướng lưu dữ liệu và hướng duyệt phải được phân biệt

Trong cú pháp Cypher minh họa:

~~~cypher
// Các cạnh FOLLOWS đi ra khỏi An.
MATCH (an:Learner {learnerId: 'L001'})
      -[:FOLLOWS]->(followed:Learner)
RETURN followed.learnerId, followed.name;
~~~

~~~cypher
// Những người có cạnh FOLLOWS đi vào An.
MATCH (follower:Learner)
      -[:FOLLOWS]->(an:Learner {learnerId: 'L001'})
RETURN follower.learnerId, follower.name;
~~~

~~~cypher
// Tìm người nối với An bằng FOLLOWS theo một trong hai hướng.
MATCH (an:Learner {learnerId: 'L001'})
      -[:FOLLOWS]-(related:Learner)
RETURN DISTINCT related.learnerId, related.name;
~~~

Dấu nối không có mũi tên ở truy vấn cuối **cho phép khớp cạnh theo cả hai hướng**; nó không biến dữ liệu FOLLOWS thành quan hệ vô hướng, cũng không chứng minh hai người thực sự theo dõi lẫn nhau.

### 2.3. Quan hệ hai chiều khác hai chiều của phép duyệt

Nếu nghiệp vụ yêu cầu “An và Bình theo dõi nhau”, dữ liệu cần có **hai cạnh**:

~~~text
(An)   -[:FOLLOWS]-> (Bình)
(Bình) -[:FOLLOWS]-> (An)
~~~

Khi truy vấn quan hệ tương hỗ:

~~~cypher
MATCH (an:Learner {learnerId: 'L001'})
      -[:FOLLOWS]->(other:Learner)
      -[:FOLLOWS]->(an)
RETURN DISTINCT other.learnerId, other.name;
~~~

Mẫu hai cạnh có hướng ngược nhau kiểm tra **cả hai bên có theo dõi**, chứ không chỉ có một cạnh theo bất kỳ hướng nào.

Nếu nghiệp vụ có quan hệ thực sự đối xứng như “là thành viên cùng một nhóm”, có nhiều cách biểu diễn:

- Lưu một cạnh có hướng quy ước, ví dụ từ mã nút nhỏ hơn sang mã nút lớn hơn; luôn duyệt không xét hướng khi câu hỏi coi quan hệ là đối xứng.
- Lưu hai cạnh ngược chiều và quy định cập nhật/xóa đồng bộ.
- Tạo một nút trung gian biểu diễn nhóm hoặc tư cách thành viên nếu bản thân nhóm có danh tính và vòng đời.

Không có một lựa chọn áp dụng cho mọi tình huống. Quan trọng là **hướng trên dữ liệu, tên loại cạnh và quy tắc đọc phải nhất quán với nhau**.

### 2.4. Quan hệ đảo ngược không đồng nghĩa dữ liệu được nhân đôi

Ví dụ:

~~~text
(Graph)-[:REQUIRES]->(NoSQL)
~~~

Một hệ hỗ trợ truy vấn cạnh ngược hướng có thể tìm:

~~~cypher
MATCH (dependency:Course)-[:REQUIRES]->(target:Course {courseId:'C002'})
RETURN dependency.courseId, dependency.title;
~~~

Ta không bắt buộc tạo thêm một cạnh có nghĩa IS_PREREQUISITE_OF đi ngược chiều chỉ để trả lời câu hỏi này. Lưu cả hai hướng như hai kiểu quan hệ diễn đạt cùng một sự thật có thể dẫn đến sai lệch nếu một cạnh bị xóa còn cạnh kia không được cập nhật.

## 3. Nhiều cạnh nối cùng cặp nút

### 3.1. Thế nào là multigraph?

Trong toán học, **multigraph** là đồ thị cho phép nhiều cạnh nối cùng một cặp đỉnh. Khi có hướng, ta có thể phân biệt những cạnh song song cùng nguồn/đích với những cạnh ngược chiều.

Ví dụ người học An và Bình có quan hệ:

~~~text
(An)-[:FOLLOWS]->(Bình)
(An)-[:MENTORS]->(Bình)
(Bình)-[:FOLLOWS]->(An)
~~~

Đây là **ba cạnh**:

- FOLLOWS từ An đến Bình.
- MENTORS từ An đến Bình.
- FOLLOWS từ Bình đến An.

Hai cạnh đầu **cùng chiều nhưng khác kiểu**. Cạnh thứ ba **ngược chiều** với cạnh FOLLOWS đầu.

Ngoài ra, An có thể đăng ký lại cùng một khóa hai lần:

~~~text
(An)-[:ENROLLED_IN {enrollmentId:'ENR-101', term:'2026-Q1'}]->(NoSQL)
(An)-[:ENROLLED_IN {enrollmentId:'ENR-205', term:'2026-Q4'}]->(NoSQL)
~~~

Đây là **hai cạnh song song cùng kiểu, cùng hướng, cùng nút đầu và nút cuối**, nhưng đại diện cho **hai lần đăng ký nghiệp vụ khác nhau**.

### 3.2. Các trường hợp “nhiều cạnh” không giống nhau

| Hiện tượng | Ví dụ | Cách hiểu |
|---|---|---|
| Cùng cặp nút, **khác loại cạnh** | An FOLLOWS Bình; An MENTORS Bình | Hai sự thật nghiệp vụ độc lập |
| Cùng loại, **ngược hướng** | An FOLLOWS Bình; Bình FOLLOWS An | Hai quyết định theo dõi độc lập |
| Cùng loại, **cùng hướng, nhiều lần** | An ENROLLED_IN NoSQL ở hai kỳ | Hai lần tương tác/hồ sơ khác nhau |
| Nhiều cạnh từ một nút tới nhiều nút | An FOLLOWS Bình và Chi | Một loại quan hệ 1:N hoặc N:M |
| Cạnh từ một nút về chính nó | A -[:RELATED_TO]-> A | Self-loop; tùy nghiệp vụ có thể hợp lệ hoặc bị cấm |
| Hai cạnh có dữ liệu y hệt nhưng **không có ý nghĩa riêng** | Hai FOLLOWS An → Bình trùng nhau | Có khả năng là lỗi ghi trùng cần ngăn |

Một số cơ sở dữ liệu property graph cho phép nhiều cạnh có cùng kiểu giữa cùng hai nút, một số mô hình hoặc API hạn chế điều đó. Vì vậy **“có thể chứa nhiều cạnh”** cần được xác nhận theo hệ quản trị sử dụng; đừng mặc định mọi loại graph database xử lý đa cạnh giống nhau.

### 3.3. Nhiều cạnh hợp lệ khác với dữ liệu bị trùng

Xét:

~~~text
ENR-101: An đăng ký NoSQL kỳ Q1
ENR-205: An đăng ký NoSQL kỳ Q4
~~~

Nếu hệ thống cho phép học lại, hai quan hệ là hợp lệ. Ngược lại, nếu ứng dụng chỉ cho phép **một quan hệ FOLLOWS hiện hành cho mỗi cặp người**, việc tạo hai cạnh:

~~~text
An -[:FOLLOWS {since:'2026-10-01'}]-> Bình
An -[:FOLLOWS {since:'2026-10-01'}]-> Bình
~~~

có thể là lỗi phát sinh khi client retry hoặc khi hai request đồng thời tạo quan hệ.

**Quy tắc nghiệp vụ quyết định tính trùng**, không phải việc hai cạnh có cùng source, type và target. Với đăng ký khóa, khóa nhận diện có thể là **enrollmentId**; với FOLLOWS hiện hành, một quy tắc có thể là **(followerId, followedId)** chỉ có tối đa một quan hệ hiện hành.

### 3.4. Minh họa đồ thị có nhiều cạnh

~~~mermaid
flowchart LR
    A["An :Learner"]
    B["Bình :Learner"]
    N["NoSQL căn bản :Course"]

    A -->|FOLLOWS| B
    A -->|MENTORS| B
    B -->|FOLLOWS| A
    A -->|ENROLLED_IN · ENR-101| N
    A -->|ENROLLED_IN · ENR-205| N
~~~

Trong sơ đồ này, mỗi mũi tên là **một cạnh riêng**. Không nên gộp hai lần ENROLLED_IN thành một cạnh duy nhất nếu nghiệp vụ yêu cầu lưu lịch sử hai lần tham gia.

## 4. Thuộc tính của cạnh: dữ liệu thuộc về mối liên hệ

### 4.1. Thuộc tính cạnh là gì?

Trong property graph, cạnh có thể chứa những cặp **tên thuộc tính – giá trị**. Ví dụ:

~~~text
(An)-[:ENROLLED_IN {
    enrollmentId: 'ENR-205',
    term: '2026-Q4',
    enrolledAt: '2026-10-01',
    status: 'ACTIVE',
    progress: 0.25
}]->(NoSQL)
~~~

Ở đây:

- **enrollmentId** phân biệt từng lượt đăng ký.
- **term** cho biết kỳ học.
- **enrolledAt** cho biết thời điểm bắt đầu tham gia.
- **status** mô tả trạng thái của lần đăng ký.
- **progress** là tiến độ của An **trong lần đăng ký này**.

Các trường đó không phải thuộc tính chỉ của An, vì An có thể học nhiều khóa hoặc cùng khóa ở nhiều kỳ. Chúng cũng không phải thuộc tính của riêng khóa NoSQL, vì mỗi người có tiến độ khác nhau.

### 4.2. Quy tắc đặt thuộc tính ở nút hay cạnh

| Dữ liệu | Nên gắn vào | Lý do |
|---|---|---|
| learnerId, name | Nút Learner | Mô tả người học |
| courseId, title, difficulty | Nút Course | Mô tả khóa học |
| progress của An với NoSQL kỳ Q4 | Cạnh ENROLLED_IN | Phụ thuộc vào đúng người, khóa và lượt đăng ký |
| since của An theo dõi Bình | Cạnh FOLLOWS | Thời điểm hình thành quan hệ |
| mentorRole của An đối với Bình | Cạnh MENTORS | Vai trò trong mối quan hệ cụ thể |
| mandatory trên quan hệ tiền quyết | Cạnh REQUIRES | Một khóa có thể có nhiều điều kiện với mức bắt buộc khác nhau |
| số tiền và mã giao dịch của một lần chuyển tiền | Cạnh TRANSFERRED_TO **hoặc** nút Transfer | Tùy nhu cầu truy vết, lịch sử và các liên kết khác |

Thuộc tính cạnh giúp biểu diễn “**A có quan hệ R với B trong bối cảnh nào?**” mà không biến từng thuộc tính phụ thuộc thành dữ liệu toàn cục của một nút.

### 4.3. Trọng số và độ tin cậy của quan hệ

Một số bài toán gán **weight** hoặc **score** lên cạnh:

~~~text
(Skill A)-[:RELATED_TO {weight: 0.80}]->(Skill B)
(User A)-[:TRUSTS {score: 0.65}]->(User B)
~~~

Trước khi dùng trọng số trong thuật toán, phải xác định:

- Weight lớn có nghĩa **gần hơn**, **mạnh hơn**, **đắt hơn** hay **rủi ro hơn**?
- Đơn vị đo là gì? Khoảng giá trị hợp lệ là bao nhiêu?
- Trọng số có thể âm không?
- Ai tạo giá trị này, bao giờ cập nhật?
- Dùng **đường ít cạnh nhất** hay **đường có tổng trọng số nhỏ nhất**?

Một quan hệ có score = 0.8 không tự nói rằng “chi phí đường đi” là 0.8. Nếu muốn thuật toán tối ưu tổng chi phí, các trọng số phải mang ý nghĩa chi phí phù hợp với thuật toán được chọn.

### 4.4. Kiểu dữ liệu và giá trị phức tạp

Tùy hệ quản trị, thuộc tính có thể là chuỗi, số, boolean, ngày/giờ, danh sách hoặc các kiểu đặc biệt được hỗ trợ. Đừng mặc định mọi property graph cho phép ghi nguyên một JSON lồng nhiều cấp trực tiếp lên cạnh.

Ví dụ trong Cypher:

~~~cypher
SET r.enrolledAt = date('2026-10-01'),
    r.progress = 0.25,
    r.status = 'ACTIVE';
~~~

Các thuộc tính mang cấu trúc phức tạp như danh sách bài thi, lịch sử điểm số, file chứng nhận hoặc chứng từ thanh toán có thể cần một **nút nghiệp vụ riêng** hoặc hệ lưu trữ khác. Một cạnh không nhất thiết là nơi lưu toàn bộ lịch sử hoạt động liên quan.

## 5. Ví dụ xuyên suốt: quan hệ trong nền tảng học tập

### 5.1. Mô hình nút và cạnh

Ta sử dụng:

**Nút:**

- Learner: learnerId, name.
- Course: courseId, title.

**Cạnh:**

- FOLLOWS: Learner → Learner, có since.
- MENTORS: Learner → Learner, có since và topic.
- ENROLLED_IN: Learner → Course, có enrollmentId, term, enrolledAt, status, progress.
- REQUIRES: Course → Course, có mandatory hoặc minimumLevel nếu cần.

**Quy tắc minh họa:**

1. Mỗi Learner có định danh learnerId duy nhất.
2. Mỗi Course có courseId duy nhất.
3. Một Learner có thể theo dõi nhiều người và được nhiều người theo dõi.
4. Một cặp Learner có tối đa một cạnh FOLLOWS **hiện hành** theo một hướng.
5. Một Learner có thể có nhiều cạnh ENROLLED_IN tới cùng Course nếu thuộc những lần đăng ký khác nhau.
6. enrollmentId xác định một lần đăng ký nghiệp vụ; retry cùng lần đăng ký phải giữ nguyên ID.
7. Một khóa học không được tự là điều kiện tiên quyết của chính nó, và chương trình có thể cấm chu trình tiên quyết.

Những quy tắc 4–7 là **bất biến nghiệp vụ cần được triển khai**, không tự được bảo đảm chỉ bằng cách đặt tên nhãn và loại cạnh.

### 5.2. Tạo nút bằng Cypher

Ví dụ dùng MERGE để tìm hoặc tạo theo định danh nghiệp vụ:

~~~cypher
MERGE (an:Learner {learnerId: 'L001'})
SET an.name = 'An';

MERGE (binh:Learner {learnerId: 'L002'})
SET binh.name = 'Bình';

MERGE (chi:Learner {learnerId: 'L003'})
SET chi.name = 'Chi';

MERGE (nosql:Course {courseId: 'C002'})
SET nosql.title = 'NoSQL căn bản';

MERGE (graph:Course {courseId: 'C003'})
SET graph.title = 'Mô hình đồ thị';
~~~

Trước khi chạy trên dữ liệu thực tế, nên thiết lập ràng buộc duy nhất phù hợp. Ví dụ Cypher hỗ trợ ở các phiên bản Neo4j hiện đại:

~~~cypher
CREATE CONSTRAINT learner_business_id IF NOT EXISTS
FOR (n:Learner)
REQUIRE n.learnerId IS UNIQUE;

CREATE CONSTRAINT course_business_id IF NOT EXISTS
FOR (n:Course)
REQUIRE n.courseId IS UNIQUE;
~~~

Việc dùng MERGE **không tự thay thế mọi ràng buộc duy nhất dưới cạnh tranh ghi**. Tính duy nhất do cơ sở dữ liệu cưỡng chế và giao dịch/cơ chế ghi cụ thể hỗ trợ cần được thiết kế riêng.

### 5.3. Tạo quan hệ có hướng và có thuộc tính

~~~cypher
MATCH (an:Learner {learnerId: 'L001'})
MATCH (binh:Learner {learnerId: 'L002'})
MERGE (an)-[follow:FOLLOWS]->(binh)
ON CREATE SET follow.since = date('2026-09-15');
~~~

Câu lệnh minh họa ý định **một cạnh FOLLOWS từ An tới Bình**: khi không có mẫu quan hệ phù hợp, MERGE tạo cạnh; nếu đã tồn tại thì khớp quan hệ hiện có. Nhưng nếu dữ liệu vốn đã có **nhiều cạnh trùng**, MERGE không tự dọn các cạnh đó. Khi nhiều yêu cầu cạnh tranh tạo quan hệ, cần đánh giá ràng buộc và phối hợp thực tế của hệ quản trị.

Thêm một kiểu quan hệ khác cùng chiều:

~~~cypher
MATCH (an:Learner {learnerId: 'L001'})
MATCH (binh:Learner {learnerId: 'L002'})
MERGE (an)-[mentors:MENTORS]->(binh)
ON CREATE SET
    mentors.since = date('2026-09-20'),
    mentors.topic = 'NoSQL';
~~~

Một cặp nút giờ có **hai loại cạnh khác nhau**. Khi hỏi “Ai được An theo dõi?” chỉ dùng FOLLOWS; khi hỏi “Ai được An hướng dẫn?” chỉ dùng MENTORS.

Thêm quan hệ theo dõi ở chiều ngược lại:

~~~cypher
MATCH (an:Learner {learnerId: 'L001'})
MATCH (binh:Learner {learnerId: 'L002'})
MERGE (binh)-[follow:FOLLOWS]->(an)
ON CREATE SET follow.since = date('2026-10-01');
~~~

Đây là một cạnh FOLLOWS độc lập: Bình theo dõi An kể từ thời điểm riêng của Bình.

### 5.4. Tạo hai cạnh ENROLLED_IN song song

Ví dụ dùng enrollmentId khác nhau để biểu diễn hai lần học:

~~~cypher
MATCH (an:Learner {learnerId: 'L001'})
MATCH (nosql:Course {courseId: 'C002'})
MERGE (an)-[e1:ENROLLED_IN {enrollmentId:'ENR-101'}]->(nosql)
ON CREATE SET
    e1.term = '2026-Q1',
    e1.enrolledAt = date('2026-01-10'),
    e1.status = 'COMPLETED',
    e1.progress = 1.0;

MATCH (an:Learner {learnerId: 'L001'})
MATCH (nosql:Course {courseId: 'C002'})
MERGE (an)-[e2:ENROLLED_IN {enrollmentId:'ENR-205'}]->(nosql)
ON CREATE SET
    e2.term = '2026-Q4',
    e2.enrolledAt = date('2026-10-01'),
    e2.status = 'ACTIVE',
    e2.progress = 0.25;
~~~

Hai lệnh có cùng nút đầu, cùng nút cuối và cùng kiểu cạnh, nhưng **enrollmentId khác nhau**, nên chúng có thể tạo hai cạnh khác nhau trong một property graph cho phép cạnh song song.

**Giới hạn cần lưu ý:** MERGE tìm hoặc tạo một **mẫu quan hệ với hai nút đã được ràng buộc**, không mặc định bảo đảm enrollmentId duy nhất ở mọi cặp nút trên toàn đồ thị. Nếu enrollmentId phải duy nhất toàn hệ thống, cần ràng buộc/cơ chế ghi thích hợp; nếu không có hỗ trợ trực tiếp thì cân nhắc tạo nút Enrollment với định danh nghiệp vụ duy nhất.

Thêm phụ thuộc khóa học:

~~~cypher
MATCH (graph:Course {courseId:'C003'})
MATCH (nosql:Course {courseId:'C002'})
MERGE (graph)-[r:REQUIRES]->(nosql)
ON CREATE SET r.mandatory = true;
~~~

Việc tạo cạnh REQUIRES không tự kiểm tra chu trình. Nếu cấm chu trình tiên quyết, ứng dụng cần kiểm tra thêm trước khi ghi và kiểm soát cạnh tranh phù hợp.

## 6. Truy vấn có hướng và đa cạnh bằng Cypher

### 6.1. Chỉ tìm đúng một loại cạnh

~~~cypher
MATCH (an:Learner {learnerId:'L001'})
      -[:FOLLOWS]->(other:Learner)
RETURN other.learnerId AS learnerId,
       other.name AS name;
~~~

Truy vấn này không lấy quan hệ MENTORS. Muốn đọc cả hai kiểu:

~~~cypher
MATCH (an:Learner {learnerId:'L001'})
      -[r:FOLLOWS|MENTORS]->(other:Learner)
RETURN other.learnerId AS learnerId,
       type(r) AS relationshipType;
~~~

Nếu An vừa theo dõi vừa hướng dẫn Bình, truy vấn thứ hai có thể trả **hai hàng** cho Bình, một hàng cho mỗi cạnh. Đó là kết quả đúng nếu cần liệt kê **các quan hệ**.

Nếu chỉ muốn một danh sách người duy nhất:

~~~cypher
MATCH (an:Learner {learnerId:'L001'})
      -[:FOLLOWS|MENTORS]->(other:Learner)
RETURN DISTINCT other.learnerId AS learnerId,
                other.name AS name;
~~~

**DISTINCT** loại các hàng trùng ở kết quả; nó không xóa hay gộp cạnh trong cơ sở dữ liệu.

### 6.2. Truy xuất thuộc tính của từng cạnh

~~~cypher
MATCH (an:Learner {learnerId:'L001'})
      -[enrollment:ENROLLED_IN]->(course:Course {courseId:'C002'})
RETURN enrollment.enrollmentId AS enrollmentId,
       enrollment.term AS term,
       enrollment.enrolledAt AS enrolledAt,
       enrollment.status AS status,
       enrollment.progress AS progress
ORDER BY enrollment.enrolledAt DESC;
~~~

Với dữ liệu mẫu, câu hỏi “An học NoSQL mấy lần?” nhận được hai cạnh ENR-101 và ENR-205. Nếu chỉ lấy courseId mà không giữ biến quan hệ, có thể mất ý nghĩa “hai lần đăng ký”.

### 6.3. Đếm số cạnh và số nút không giống nhau

Ví dụ An đăng ký hai lần vào một khóa:

~~~cypher
MATCH (an:Learner {learnerId:'L001'})
      -[r:ENROLLED_IN]->(course:Course)
RETURN count(r) AS enrollmentCount,
       count(DISTINCT course) AS distinctCourseCount;
~~~

Với hai quan hệ ENROLLED_IN An → NoSQL trong dữ liệu mẫu:

| enrollmentCount | distinctCourseCount |
|---:|---:|
| 2 | 1 |

**count(r)** đếm số kết quả khớp theo quan hệ; **count(DISTINCT course)** đếm số nút khóa học khác nhau. Khi có nhiều mẫu MATCH ghép với nhau, số hàng trung gian có thể nhân lên, vì vậy cần kiểm soát đúng đơn vị đếm hoặc dùng subquery.

Nếu muốn đếm số người duy nhất đang học khóa C002:

~~~cypher
MATCH (learner:Learner)-[r:ENROLLED_IN]->(course:Course {courseId:'C002'})
WHERE r.status = 'ACTIVE'
RETURN count(DISTINCT learner) AS activeLearnerCount;
~~~

Truy vấn này đếm **người duy nhất**, không phải số lượt đăng ký đang hoạt động. Nếu một người có hai lượt ACTIVE do dữ liệu lỗi, count(DISTINCT learner) vẫn trả một người; quy tắc dữ liệu cần được kiểm soát riêng.

### 6.4. Lọc theo thuộc tính quan hệ

~~~cypher
MATCH (learner:Learner {learnerId:'L001'})
      -[r:ENROLLED_IN]->(course:Course)
WHERE r.status = 'ACTIVE'
  AND r.enrolledAt >= date('2026-09-01')
RETURN course.courseId, course.title,
       r.enrollmentId, r.enrolledAt
ORDER BY r.enrolledAt DESC;
~~~

Đây là truy vấn phụ thuộc **thuộc tính của cạnh**. Nếu status được đặt sai trên nút Course, việc lọc “khóa đang học của riêng L001” sẽ trở nên sai về ý nghĩa.

### 6.5. Duyệt cạnh theo chiều ngược để tìm tác động

~~~cypher
MATCH (dependent:Course)-[r:REQUIRES]->
      (required:Course {courseId:'C002'})
RETURN dependent.courseId, dependent.title,
       r.mandatory;
~~~

Mẫu này tìm các khóa có cạnh REQUIRES **hướng tới** khóa C002. Nếu cần phụ thuộc gián tiếp nhiều tầng, mới mở rộng quan hệ sang độ dài nhiều hop kèm giới hạn và quy tắc duyệt; bản thân một cạnh có hướng đã đủ cho câu hỏi trực tiếp.

### 6.6. Tìm người vừa theo dõi nhau vừa có quan hệ hướng dẫn

~~~cypher
MATCH (a:Learner {learnerId:'L001'})
      -[:FOLLOWS]->(b:Learner)
      -[:FOLLOWS]->(a)
MATCH (a)-[mentor:MENTORS]->(b)
RETURN DISTINCT b.learnerId, b.name,
                mentor.since AS mentorSince;
~~~

Truy vấn yêu cầu **hai cạnh FOLLOWS đối hướng** và **một cạnh MENTORS từ An tới đối tác**. Đây là một ví dụ quan hệ kết hợp: điều kiện không thể diễn đạt chính xác bằng một trường “related = true”.

### 6.7. Quan hệ không hướng trong truy vấn vẫn có thuộc tính

~~~cypher
MATCH (a:Learner {learnerId:'L001'})
      -[r:FOLLOWS]-(other:Learner)
RETURN other.learnerId AS relatedLearner,
       r.since AS since;
~~~

Nếu có cả An → Bình và Bình → An, truy vấn có thể khớp cả hai cạnh. Muốn biết **ai là người theo dõi**, phải giữ thông tin hướng thực tế thay vì coi hai cạnh như một quan hệ đối xứng. Trong các hệ Cypher hỗ trợ, có thể kiểm tra nút đầu và cuối của cạnh thông qua hàm truy xuất nút nguồn/đích theo API tương ứng.

## 7. Quan hệ có thời gian và trạng thái

### 7.1. “Hiện đang theo dõi” khác “đã từng theo dõi”

Có ít nhất hai cách lưu FOLLOWS:

**Cách A: Chỉ lưu quan hệ hiện hành**

~~~text
An bắt đầu theo dõi Bình  -> tạo cạnh FOLLOWS
An bỏ theo dõi Bình       -> xóa cạnh FOLLOWS
~~~

Ưu điểm là truy vấn hiện tại đơn giản. Nhược điểm: không còn lịch sử An từng theo dõi Bình vào thời gian nào.

**Cách B: Lưu quan hệ theo thời gian hiệu lực**

~~~text
(An)-[:FOLLOWS {
    relationId: 'F-101',
    validFrom: 2026-01-01,
    validTo: 2026-05-01
}]->(Bình)

(An)-[:FOLLOWS {
    relationId: 'F-205',
    validFrom: 2026-09-01,
    validTo: null
}]->(Bình)
~~~

Hai cạnh cùng kiểu này có thể hợp lệ vì mô tả **hai giai đoạn theo dõi khác nhau**, nhưng truy vấn “An đang theo dõi ai?” phải lọc đúng thời gian hiệu lực.

Ví dụ sử dụng trường ngày:

~~~cypher
MATCH (an:Learner {learnerId:'L001'})
      -[r:FOLLOWS]->(other:Learner)
WHERE r.validFrom <= date()
  AND (r.validTo IS NULL OR r.validTo > date())
RETURN DISTINCT other.learnerId, other.name;
~~~

Quy ước thời gian trong ví dụ là **[validFrom, validTo)**: bao gồm ngày bắt đầu và không bao gồm ngày kết thúc. Doanh nghiệp phải quyết định rõ dùng thời điểm hay ngày, múi giờ và ý nghĩa của giá trị null.

### 7.2. Ngăn hai giai đoạn hiệu lực chồng lấp

Nếu nghiệp vụ cấm hai quan hệ FOLLOWS cùng lúc giữa một cặp người, không chỉ cần kiểm tra cùng relationId. Còn phải ngăn hai khoảng thời gian chồng lấp:

~~~text
F-101: [2026-01-01, 2026-06-01)
F-205: [2026-05-01, 2026-12-01)  -> chồng lấp trong tháng 5
~~~

Việc phát hiện chồng lấp phải xét các khoảng hiện có và **tranh chấp ghi đồng thời**. Kiểm tra ở ứng dụng rồi CREATE không đủ nếu hai yêu cầu có thể cùng thấy “chưa có” trước khi ghi. Cần giao dịch, khóa phối hợp, ràng buộc hoặc thiết kế nút trung gian phù hợp với cơ sở dữ liệu được chọn.

### 7.3. Thời điểm nghiệp vụ và thời điểm hệ thống ghi nhận

Một quan hệ có thể cần nhiều mốc:

- **occurredAt:** Khi sự kiện xảy ra ngoài đời.
- **recordedAt:** Khi hệ thống nhận được thông tin.
- **validFrom/validTo:** Khoảng thời gian quan hệ có hiệu lực.
- **updatedAt:** Khi thông tin lưu trữ được sửa gần nhất.

Ví dụ một thông báo “hủy theo dõi” phát sinh lúc 08:00 nhưng mạng chậm, tới hệ thống lúc 08:05. Nếu chỉ lưu recordedAt, truy vấn lịch sử theo thời điểm xảy ra thực tế có thể sai. Vì vậy phải chốt loại thời gian mà câu hỏi nghiệp vụ sử dụng.

## 8. Khi nào nên biến quan hệ thành một nút?

### 8.1. Giữ dữ liệu trên cạnh khi mối liên hệ đủ đơn giản

Cạnh có thuộc tính phù hợp khi:

- Đầu vào và đầu ra là hai nút rõ ràng.
- Dữ liệu chủ yếu mô tả liên kết giữa hai nút.
- Quan hệ có số thuộc tính và vòng đời tương đối đơn giản.
- Truy vấn chủ yếu đi qua liên kết A → B hoặc B → A.

Ví dụ **FOLLOWS {since}** hoặc **REQUIRES {mandatory}** thường dễ hiểu nếu là cạnh.

### 8.2. Dùng nút nghiệp vụ khi mối liên hệ có vòng đời riêng

Một lượt đăng ký có thể chứa:

- Mã enrollmentId cần tra cứu độc lập.
- Hóa đơn hoặc thanh toán riêng.
- Danh sách bài kiểm tra.
- Giảng viên phụ trách.
- Nhiều lần gia hạn hoặc thay đổi trạng thái.
- Tài liệu chứng nhận, lịch sử đối soát.

Khi đó, một nút Enrollment có thể thích hợp:

~~~mermaid
flowchart LR
    A["An :Learner"]
    E1["ENR-101 :Enrollment"]
    E2["ENR-205 :Enrollment"]
    C["NoSQL :Course"]
    P["PAY-9 :Payment"]
    A -->|HAS_ENROLLMENT| E1
    A -->|HAS_ENROLLMENT| E2
    E1 -->|FOR_COURSE| C
    E2 -->|FOR_COURSE| C
    P -->|PAYS_FOR| E2
~~~

Trong mô hình này, Enrollment trở thành **thực thể có danh tính riêng**. Thay vì một cạnh ENROLLED_IN mang nhiều thuộc tính, ta có các cạnh HAS_ENROLLMENT và FOR_COURSE nối nút Enrollment với Learner/Course.

### 8.3. So sánh hai cách mô hình hóa

| Tiêu chí | Cạnh ENROLLED_IN có thuộc tính | Nút Enrollment riêng |
|---|---|---|
| Đọc “ai đang học khóa nào” | Đi một cạnh | Đi qua nút trung gian |
| Nhiều lần đăng ký một khóa | Có thể dùng nhiều cạnh nếu hệ hỗ trợ | Tạo nhiều nút Enrollment có ID riêng |
| Thanh toán liên quan lần đăng ký | Khó gắn thêm quan hệ trực tiếp tới một cạnh trong nhiều mô hình | Dễ nối Payment → Enrollment |
| Lịch sử thay đổi phức tạp | Cần quy tắc phiên bản hoặc sự kiện bổ sung | Có thể nối Enrollment với các sự kiện con |
| Chi phí mô hình | Ít nút và cạnh hơn | Thêm nút, cạnh và bước duyệt |
| Định danh nghiệp vụ độc lập | Phải quản lý trên thuộc tính cạnh hoặc cơ chế sản phẩm | Quản lý trên thuộc tính nút và ràng buộc phù hợp |

**Tiêu chí quyết định:** Đặt quan hệ thành nút khi nó có **danh tính và vòng đời độc lập**, nhiều đối tượng khác cần tham chiếu tới nó hoặc lịch sử chi tiết cần quản lý. Không cần tạo nút trung gian chỉ vì một cạnh có hai, ba thuộc tính đơn giản.

### 8.4. Ví dụ thanh toán: đa cạnh hay nút giao dịch?

Một ví điện tử ghi nhiều lần chuyển tiền:

~~~text
(Ví A)-[:TRANSFERRED_TO {transactionId:'TX1', amount:100000}]->(Ví B)
(Ví A)-[:TRANSFERRED_TO {transactionId:'TX2', amount:50000}]->(Ví B)
~~~

Hai cạnh là hai giao dịch riêng. Nhưng nếu mỗi giao dịch liên kết với ngân hàng, phương thức thanh toán, trạng thái đối soát, các khoản hoàn tiền và chứng từ, việc tạo nút **Transfer** có transactionId riêng thường giúp thể hiện nghiệp vụ đầy đủ hơn. Cần cân nhắc khối lượng cạnh, quy tắc bất biến của sổ cái và yêu cầu kiểm toán.

## 9. Định danh và kiểm soát nhiều cạnh

### 9.1. Cạnh cũng cần được nhận diện theo nghiệp vụ

Khi hệ thống cho phép cạnh song song, chỉ biết (source, type, target) có thể không đủ để chọn đúng cạnh cần sửa:

~~~text
An -[:ENROLLED_IN {enrollmentId:'ENR-101'}]-> NoSQL
An -[:ENROLLED_IN {enrollmentId:'ENR-205'}]-> NoSQL
~~~

Yêu cầu “Cập nhật tiến độ cho ENR-205” cần chọn theo **enrollmentId**, không chỉ theo nút An và khóa NoSQL.

~~~cypher
MATCH (an:Learner {learnerId:'L001'})
      -[r:ENROLLED_IN {enrollmentId:'ENR-205'}]->
      (course:Course {courseId:'C002'})
SET r.progress = 0.50
RETURN r.enrollmentId, r.progress;
~~~

Nếu truy vấn UPDATE không đủ điều kiện và khớp cả hai cạnh, ứng dụng có thể cập nhật nhầm nhiều lượt học.

### 9.2. Định danh nội bộ và định danh nghiệp vụ

Một graph database có thể cấp **định danh nội bộ** cho nút/cạnh, hữu ích cho xử lý trong hệ thống. Nhưng ứng dụng tích hợp nên cân nhắc **ID nghiệp vụ ổn định** như enrollmentId hoặc transactionId để truy vết và đồng bộ.

Không nên mặc định ID nội bộ:

- Giữ nguyên qua mọi lần import/export hoặc tái tạo dữ liệu.
- Là duy nhất ngoài phạm vi cơ sở dữ liệu đang dùng.
- Có thể được dùng lâu dài làm khóa liên kết giữa các dịch vụ.

Định danh nghiệp vụ nên có phạm vi rõ (toàn hệ thống, theo tenant, theo khóa học...) và quy tắc chống tạo trùng.

### 9.3. MERGE, CREATE và ràng buộc duy nhất

Trong Cypher, **CREATE** tạo quan hệ mới mỗi lần chạy. Vì vậy:

~~~cypher
MATCH (a:Learner {learnerId:'L001'})
MATCH (b:Learner {learnerId:'L002'})
CREATE (a)-[:FOLLOWS]->(b);
~~~

Nếu chạy lại không có bảo vệ phù hợp, đoạn trên có thể tạo thêm cạnh FOLLOWS trùng nghiệp vụ.

**MERGE** dùng để khớp hoặc tạo **mẫu quan hệ được chỉ rõ**, có ích khi muốn một mẫu được tái dùng. Nhưng MERGE không phải một công cụ tự động phát hiện mọi trường hợp trùng nghiệp vụ trên toàn hệ thống. Nó cũng không tự xóa các cạnh đã trùng tồn tại từ trước.

Với các cạnh có identity riêng như ENROLLED_IN, cần quyết định:

1. Khóa nghiệp vụ nào nhận diện **một lần đăng ký**?
2. Dữ liệu nào tạo được nhiều lần hợp lệ giữa cùng hai nút?
3. Có cho phép trạng thái ACTIVE của hai enrollment cùng lúc không?
4. Khi retry, ID có ổn định không?
5. Có ràng buộc duy nhất trên thuộc tính quan hệ hoặc nút trung gian không?

Khả năng tạo **uniqueness constraint trên relationship properties** tùy sản phẩm, phiên bản và tính năng. Nếu muốn bảo đảm chặt chẽ dưới ghi đồng thời, phải kiểm tra hỗ trợ thực tế; dùng logic “MATCH trước rồi CREATE” thuần ứng dụng có thể gặp lỗi TOCTOU.

### 9.4. Xóa một cạnh trong nhiều cạnh song song

Muốn bỏ **một** lần đăng ký cụ thể:

~~~cypher
MATCH (learner:Learner {learnerId:'L001'})
      -[r:ENROLLED_IN {enrollmentId:'ENR-205'}]->
      (course:Course {courseId:'C002'})
DELETE r;
~~~

Nếu nghiệp vụ cần giữ lịch sử, việc xóa cứng có thể không phù hợp. Thay vào đó cập nhật status = 'CANCELLED' hoặc một trạng thái ngừng hiệu lực theo chính sách. Còn khi thực sự cần xóa, **chọn đúng relationship identity** để không vô tình xóa tất cả cạnh ENROLLED_IN giữa cùng hai nút.

Ví dụ câu lệnh quá rộng:

~~~cypher
MATCH (learner:Learner {learnerId:'L001'})
      -[r:ENROLLED_IN]->
      (course:Course {courseId:'C002'})
DELETE r;
~~~

Câu này sẽ khớp và xóa **mọi cạnh ENROLLED_IN** giữa hai nút được chỉ định trong phạm vi dữ liệu khớp. Nó chỉ đúng nếu yêu cầu nghiệp vụ thật sự là xóa mọi lần liên kết.

## 10. Tránh nhân bản kết quả khi ghép nhiều quan hệ

### 10.1. Hiện tượng nhân hàng

Giả sử An có:

- 2 cạnh ENROLLED_IN tới NoSQL.
- 3 cạnh HAS_BADGE tới các huy hiệu.

Truy vấn ghép hai kiểu cạnh từ An:

~~~cypher
MATCH (an:Learner {learnerId:'L001'})
      -[e:ENROLLED_IN]->(course:Course)
MATCH (an)-[b:HAS_BADGE]->(badge:Badge)
RETURN an.name, course.title, badge.name;
~~~

có thể tạo **2 × 3 = 6 hàng** cho một cặp tập dữ liệu nhỏ. Nếu sau đó dùng count(e) không cẩn thận, số lượt đăng ký có thể bị nhân lên theo số badge.

Đây là hệ quả của việc **ghép hai tập kết quả quan hệ**, không phải cơ sở dữ liệu tự tạo thêm cạnh.

### 10.2. Đếm từng loại quan hệ riêng

Một cách tránh sai lệch là dùng các truy vấn con hoặc tách phần thống kê:

~~~cypher
MATCH (an:Learner {learnerId:'L001'})
CALL {
  WITH an
  MATCH (an)-[e:ENROLLED_IN]->(:Course)
  RETURN count(e) AS enrollmentCount
}
CALL {
  WITH an
  MATCH (an)-[b:HAS_BADGE]->(:Badge)
  RETURN count(b) AS badgeCount
}
RETURN an.learnerId, enrollmentCount, badgeCount;
~~~

Ví dụ trên dùng cú pháp subquery quen thuộc trong một số phiên bản Neo4j; cú pháp truyền biến vào subquery có thể khác ở các phiên bản mới. Ý chính là **tính số lượng trên từng tập quan hệ trước khi ghép kết quả**.

Nếu chỉ cần số đối tượng liên kết khác nhau, có thể dùng count(DISTINCT node) theo đúng ngữ nghĩa. Không dùng DISTINCT tùy tiện khi chính số cạnh song song là thông tin cần giữ.

## 11. Thiết kế truy vấn và hiệu năng

### 11.1. Bắt đầu từ nút được xác định chính xác

Truy vấn:

~~~cypher
MATCH (learner:Learner {learnerId:'L001'})
      -[r:ENROLLED_IN]->(course:Course)
RETURN course.title, r.status;
~~~

có điểm xuất phát rõ learnerId. Một ràng buộc/chỉ mục phù hợp trên learnerId giúp tìm nút đầu; sau đó cơ sở dữ liệu duyệt cạnh ENROLLED_IN liên quan.

Ngược lại, truy vấn tìm **mọi** cạnh ENROLLED_IN trạng thái ACTIVE trên toàn đồ thị mà không có điều kiện xuất phát có thể cần xem lượng cạnh rất lớn, dù chỉ lọc một thuộc tính.

### 11.2. Nút có bậc rất cao

Một tài khoản nổi tiếng có thể có hàng triệu cạnh FOLLOWED_BY/FOLLOWS liên quan; một khóa học phổ biến có hàng triệu cạnh ENROLLED_IN đi vào. Các vấn đề có thể gặp:

- Duyệt hàng xóm sinh nhiều kết quả trung gian.
- Đếm hoặc sắp xếp theo thuộc tính cạnh có chi phí lớn.
- Lưu lịch sử vô hạn bằng cạnh song song làm nút gắn quá nhiều cạnh.
- Truy vấn nhiều hop qua một nút nổi bật có thể mở rộng số lượng ứng viên rất nhanh.

Giải pháp tùy yêu cầu gồm giới hạn số hop, lọc loại cạnh, phân trang, dùng thuộc tính và chỉ mục thích hợp, tiền tính toán thống kê, hoặc dùng nút sự kiện và hệ lưu lịch sử chuyên biệt.

### 11.3. Không mở rộng mọi cạnh khi chỉ cần một loại

Ví dụ gợi ý khóa học từ người An theo dõi:

~~~cypher
MATCH (an:Learner {learnerId:'L001'})
      -[:FOLLOWS]->(other:Learner)
      -[e:ENROLLED_IN]->(course:Course)
WHERE e.status = 'ACTIVE'
RETURN course.courseId, count(DISTINCT other) AS followingLearners
ORDER BY followingLearners DESC;
~~~

Truy vấn chỉ duyệt FOLLOWS rồi ENROLLED_IN, không lẫn MENTORS hoặc REQUIRES. Khi có nhiều ENROLLED_IN song song giữa cùng người và khóa, **count(DISTINCT other)** tránh đếm một người nhiều lần trong chỉ số số người theo dõi đang học khóa đó.

Nếu mục tiêu là đếm **số lần đăng ký**, cần đổi phép đếm. Quyết định đếm cạnh hay đếm nút là quyết định nghiệp vụ.

### 11.4. Thuộc tính cạnh có phải luôn có chỉ mục?

Không. Việc gắn enrolledAt hoặc status lên cạnh không mặc nhiên có nghĩa truy vấn lọc trường đó sẽ nhanh ở mọi graph database. Khả năng lập chỉ mục trên relationship properties, cách dùng chỉ mục và chi phí cập nhật khác theo sản phẩm/phiên bản.

Với nhu cầu tìm kiếm toàn cục theo thời gian, đôi khi mô hình nút Enrollment với chỉ mục trên enrolledAt có thể phù hợp hơn. Hãy dùng kế hoạch truy vấn, khối lượng dữ liệu dự kiến và những mẫu truy cập thật để quyết định.

### 11.5. Các câu hỏi giúp thiết kế đúng

| Câu hỏi | Tác động thiết kế |
|---|---|
| Có cần biết hướng ngược không? | Quyết định kiểu cạnh và cách duyệt |
| Có thể có nhiều cạnh giữa cùng hai nút không? | Cần identity cho từng quan hệ |
| Nhiều cạnh có hợp lệ hay là lỗi ghi trùng? | Quy tắc unique và idempotency |
| Thuộc tính thuộc về người, khóa hay lần tham gia? | Nơi đặt property |
| Cạnh có vòng đời, lịch sử hoặc sự kiện con không? | Cạnh đơn giản hay nút Enrollment |
| Có truy vấn toàn cục theo thuộc tính quan hệ không? | Chỉ mục hoặc mô hình đọc bổ sung |
| Một nút có thể có bao nhiêu cạnh? | Đánh giá độ lớn, nút nóng và phân trang |
| Cần đúng tại thời điểm nào? | validFrom/validTo, recordedAt và nhất quán |
| Có ghi đồng thời hoặc retry không? | Cơ chế nguyên tử và chống trùng |

## 12. Bất biến và mức bảo đảm trong hệ NoSQL đồ thị

Một mô hình đẹp chưa tự bảo đảm dữ liệu đúng. Nên viết ra những **bất biến** mà ứng dụng cần giữ.

### 12.1. Bất biến về hướng

Với REQUIRES, quy tắc có thể là:

~~~text
Course A REQUIRES Course B
=> A phụ thuộc vào B.
=> Không được tự tạo cạnh ngược B REQUIRES A chỉ vì cần truy vấn chiều ngược.
~~~

Nếu nghiệp vụ cấm phụ thuộc vòng, cần phát hiện chu trình trước khi thêm cạnh và đảm bảo kiểm tra/ghi phù hợp khi có nhiều tác nhân chỉnh sửa đồng thời. Việc tìm “hiện chưa có đường từ B tới A” rồi tạo A → B có thể gặp race nếu người khác đang tạo liên kết.

### 12.2. Bất biến về số cạnh

Quy tắc ví dụ:

~~~text
FOLLOWS hiện hành:
  tối đa 1 cạnh theo mỗi (followerId, followedId)

ENROLLED_IN:
  nhiều cạnh theo mỗi (learnerId, courseId) được phép,
  nhưng mỗi enrollmentId chỉ được đại diện cho một lần đăng ký
~~~

Mức bảo đảm thực tế phụ thuộc vào ràng buộc được hỗ trợ, giao dịch và cách mọi đường ghi được triển khai. Nếu không có unique constraint thích hợp và có ghi đồng thời, một lần kiểm tra MATCH rồi CREATE có thể cho cả hai yêu cầu cùng tạo cạnh.

### 12.3. Bất biến về trạng thái

Một lượt đăng ký có thể chuyển:

~~~text
PENDING -> ACTIVE -> COMPLETED
                  -> CANCELLED
~~~

Ứng dụng có thể cấm chuyển từ COMPLETED về PENDING. Nếu hai tiến trình cập nhật progress/status đồng thời, cần điều kiện trên trạng thái hoặc version, giao dịch hay cơ chế optimistic concurrency phù hợp; không chỉ đọc rồi ghi đè vô điều kiện.

### 12.4. Xóa nút và quan hệ liên quan

Nếu xóa một nút Course, những quan hệ ENROLLED_IN và REQUIRES liên quan phải được xử lý. Một số hệ có cơ chế xóa nút kèm cạnh liên quan; ví dụ Neo4j có cú pháp DETACH DELETE. Nhưng xóa kỹ thuật không thay thế chính sách nghiệp vụ: có cần giữ lịch sử học, chứng chỉ hoặc dữ liệu kiểm toán không?

Với các thực thể có lịch sử quan trọng, **ngừng hiệu lực hoặc lưu trữ lịch sử** có thể phù hợp hơn xóa cứng. Cần phân biệt dữ liệu hiện hành với dữ liệu lịch sử.

## 13. Phân biệt property graph với RDF và các mô hình khác

Trong **property graph**, ta thường có:

~~~text
(An:Learner)-[:FOLLOWS {since: date}]->(Bình:Learner)
~~~

Quan hệ là một đối tượng cạnh có kiểu và có thể chứa thuộc tính. Tùy hệ, nhiều cạnh có thể nối cùng cặp nút.

Trong **RDF**, dữ liệu được diễn đạt qua những bộ ba **subject – predicate – object**:

~~~text
An   follows   Binh
~~~

RDF có các cách biểu diễn metadata về phát biểu/quan hệ, nhưng không đồng nhất với việc gắn property trực tiếp lên một edge như trong property graph. Trong một mô hình RDF cơ bản, việc diễn đạt nhiều lần “An theo dõi Bình vào các giai đoạn khác nhau” thường cần tài nguyên sự kiện hoặc cấu trúc bổ sung để phân biệt các lần.

Điều này quan trọng khi chuyển dữ liệu giữa các hệ: không thể tự động giả định **một cạnh có thuộc tính và định danh** sẽ ánh xạ nguyên vẹn thành **một bộ ba RDF**, hay ngược lại.

## 14. Các lỗi mô hình hóa thường gặp

| Sai lầm | Hậu quả | Cách tiếp cận |
|---|---|---|
| Đọc An FOLLOWS Bình như quan hệ hai chiều | Đề xuất người theo dõi sai | Giữ đúng nguồn, đích và hướng |
| Duyệt FOLLOWS không xét hướng rồi kết luận theo dõi lẫn nhau | Nhầm quan hệ một chiều với quan hệ tương hỗ | Kiểm tra cả hai cạnh đối hướng |
| Gộp FOLLOWS và MENTORS thành một cạnh “RELATED” | Mất ngữ nghĩa mỗi loại quan hệ | Dùng kiểu cạnh rõ nghĩa |
| Gộp hai lần đăng ký cùng khóa thành một cạnh | Mất lịch sử và trạng thái từng lần | Dùng nhiều cạnh có enrollmentId hoặc nút Enrollment |
| Tạo nhiều cạnh FOLLOWS giống nhau do retry | Đếm nhầm và duyệt lặp | Thiết kế tính duy nhất và idempotency |
| Đặt progress lên nút Course | Mọi người dùng chung tiến độ sai | Đặt trên ENROLLED_IN/Enrollment |
| Ghi đè cạnh không chỉ rõ enrollmentId | Cập nhật hoặc xóa nhầm nhiều lần đăng ký | Chọn đúng identity của quan hệ |
| Đếm count(r) rồi hiểu là số người | Một người nhiều cạnh bị đếm nhiều lần | Chọn count(DISTINCT learner) khi cần người duy nhất |
| Dùng DISTINCT khi cần số lượt giao dịch | Làm mất thông tin multiplicity | Đếm cạnh/ID theo yêu cầu thật |
| Chỉ lưu trạng thái hiện tại khi cần lịch sử | Không trả lời được truy vấn “tại thời điểm T” | Lưu khoảng hiệu lực hoặc sự kiện lịch sử |
| Kiểm tra MATCH rồi CREATE và tin rằng không thể trùng | Race condition dưới ghi đồng thời | Dùng ràng buộc/giao dịch hoặc điểm phối hợp |
| Gắn mọi lịch sử thanh toán lên cạnh | Cạnh quá phức tạp, khó kết nối thực thể khác | Dùng nút giao dịch/hồ sơ riêng khi cần |
| Giả định mọi property graph có cùng kiểu thuộc tính và unique constraint | Cú pháp hoặc bảo đảm không phù hợp | Kiểm tra tính năng phiên bản sản phẩm |

## 15. Bài tập thực hành: quan hệ giữa người dùng và khóa học

### Bài 1. Nhận diện loại đa cạnh

Cho dữ liệu:

~~~text
(An)-[:FOLLOWS]->(Bình)
(An)-[:MENTORS]->(Bình)
(Bình)-[:FOLLOWS]->(An)
(An)-[:ENROLLED_IN {enrollmentId:'E1'}]->(NoSQL)
(An)-[:ENROLLED_IN {enrollmentId:'E2'}]->(NoSQL)
~~~

Hãy:

1. Đếm số cạnh giữa An và Bình, chỉ ra những cặp khác kiểu/cặp ngược hướng.
2. Đếm số cạnh giữa An và NoSQL và giải thích vì sao chúng có thể hợp lệ.
3. Viết cách diễn đạt nghiệp vụ cho từng cạnh, không làm mất thông tin hướng.
4. Nếu E1 và E2 có cùng nội dung nhưng hai mã khác nhau do retry, cần thay đổi thiết kế ra sao?

**Gợi ý:** Có ba cạnh giữa An và Bình; có hai cạnh song song từ An tới NoSQL. E1/E2 là hợp lệ nếu đại diện cho hai lần đăng ký thật sự. Nếu là một yêu cầu bị gửi lại, cần dùng định danh thao tác/lần đăng ký ổn định và cơ chế chống trùng tại điểm ghi.

### Bài 2. Phân biệt đếm người và đếm lượt

Một khóa có dữ liệu:

~~~text
An   -[:ENROLLED_IN {id:'E1', status:'COMPLETED'}]-> NoSQL
An   -[:ENROLLED_IN {id:'E2', status:'ACTIVE'}]-> NoSQL
Bình -[:ENROLLED_IN {id:'E3', status:'ACTIVE'}]-> NoSQL
Chi  -[:ENROLLED_IN {id:'E4', status:'ACTIVE'}]-> NoSQL
~~~

Hỏi:

1. Có bao nhiêu **lượt đăng ký** tất cả?
2. Có bao nhiêu **người khác nhau** từng đăng ký?
3. Có bao nhiêu **người khác nhau** đang có lượt ACTIVE?
4. Viết truy vấn Cypher minh họa cho từng cách đếm.

**Gợi ý:** Tổng số lượt là 4, số người khác nhau từng đăng ký là 3, số người có lượt ACTIVE là 3. Để đếm người duy nhất, dùng DISTINCT trên nút người học. Để đếm lượt, đếm quan hệ hoặc enrollmentId theo thiết kế.

### Bài 3. Thiết kế quan hệ có thời gian

An theo dõi Bình từ tháng 1 đến tháng 4, bỏ theo dõi, rồi theo dõi lại từ tháng 9.

1. Biểu diễn bằng một cạnh hiện hành và lịch sử sự kiện **hoặc** hai cạnh có validFrom/validTo.
2. Viết quy tắc xác định “đang theo dõi tại ngày T”.
3. Xác định trường hợp hai khoảng thời gian bị chồng lấp.
4. Giải thích vì sao “kiểm tra chưa có cạnh ACTIVE rồi CREATE” không đủ dưới nhiều worker ghi đồng thời.

### Bài 4. Cạnh có thuộc tính hay nút Transfer?

Trong một ứng dụng thanh toán, một tài khoản có thể chuyển tiền tới cùng tài khoản khác nhiều lần. Một giao dịch có:

~~~text
transactionId, amount, currency, createdAt,
status, bankReference, refundIds, evidenceUrl
~~~

Hãy thiết kế hai phương án:

- Nhiều cạnh TRANSFERRED_TO nối trực tiếp hai tài khoản và mang thuộc tính.
- Nút Transfer được nối với tài khoản gửi, tài khoản nhận và các sự kiện hoàn tiền.

So sánh cách truy vấn lịch sử, định danh, đối soát, xóa/ẩn thông tin và mối liên hệ với hoàn tiền. Nêu lý do lựa chọn cho hệ thống cần kiểm toán.

**Gợi ý:** Khi giao dịch có ID, vòng đời và nhiều đối tượng khác liên kết tới, nút Transfer thường giúp quản lý các mối quan hệ chi tiết. Cạnh trực tiếp vẫn có thể thích hợp cho đường duyệt đơn giản hoặc mô hình phân tích quan hệ đã được chuẩn bị.

### Bài 5. Đọc và sửa truy vấn

Giả sử An có hai cạnh ENROLLED_IN tới NoSQL. Xét truy vấn:

~~~cypher
MATCH (an:Learner {learnerId:'L001'})
      -[r:ENROLLED_IN]->(course:Course {courseId:'C002'})
SET r.status = 'CANCELLED';
~~~

1. Truy vấn có thể cập nhật mấy cạnh?
2. Nếu chỉ muốn hủy E2, cần thêm điều kiện nào?
3. Nếu không được xóa lịch sử, có nên dùng DELETE không?

**Gợi ý:** Truy vấn có thể cập nhật tất cả cạnh phù hợp giữa An và NoSQL. Để hủy riêng E2, lọc theo enrollmentId = 'E2'. Nếu cần lưu lịch sử, cập nhật status và thời gian hiệu lực theo quy tắc nghiệp vụ thay vì xóa cứng.

## 16. Kết quả cần đạt khi thiết kế quan hệ

Sau khi phân tích một đồ thị nghiệp vụ, nên ghi được bảng đặc tả cho từng loại quan hệ:

| Trường đặc tả | Ví dụ |
|---|---|
| Tên và phát biểu | ENROLLED_IN: Learner tham gia Course |
| Hướng | Learner → Course |
| Nút nguồn/đích hợp lệ | Learner, Course |
| Có cho phép nhiều cạnh cùng cặp? | Có, nếu enrollmentId khác và là hai lần học khác nhau |
| Định danh cạnh | enrollmentId |
| Thuộc tính bắt buộc | enrolledAt, status |
| Thuộc tính tùy chọn | term, progress, completionAt |
| Quy tắc duy nhất | enrollmentId không được tái sử dụng sai phạm vi |
| Quy tắc thời gian | Lưu lịch sử, xác định trạng thái hiệu lực |
| Quy tắc xóa | Hủy trạng thái thay cho xóa cứng nếu cần kiểm toán |
| Truy vấn chủ đạo | Học phần đang học, lịch sử các lần học, số người/lượt |
| Cạnh tranh khi ghi | Có cơ chế ngăn retry tạo trùng và ghi đè trạng thái cũ |

**Điểm cần nhớ:** Một cạnh đồ thị không chỉ là “đường nối”. **Hướng** thể hiện ai tác động lên ai; **kiểu cạnh** thể hiện hành động hoặc mối liên hệ gì; **số lượng cạnh** thể hiện có bao nhiêu quan hệ độc lập; còn **thuộc tính cạnh** ghi nhận bối cảnh, trạng thái và lịch sử của từng quan hệ. Khi bốn yếu tố này được mô hình hóa theo quy tắc nghiệp vụ và được bảo vệ đúng ở thời điểm ghi, các truy vấn đồ thị mới trả lời chính xác cả “ai liên quan đến ai” lẫn “liên quan như thế nào, bao nhiêu lần và khi nào”.

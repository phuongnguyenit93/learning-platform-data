# Đồ thị: nút, cạnh, thuộc tính và phép duyệt quan hệ

## 1. Mô hình dữ liệu đồ thị giải quyết vấn đề gì?

Khi thiết kế một cơ sở dữ liệu NoSQL, ta có nhiều cách biểu diễn cùng một miền nghiệp vụ. Dữ liệu khách hàng và đơn hàng có thể phù hợp với mô hình tài liệu; dữ liệu tra cứu theo khóa có thể phù hợp với mô hình key–value. Nhưng nếu nhu cầu nổi bật là **khám phá các mối liên hệ nối tiếp nhau qua nhiều đối tượng**, mô hình **đồ thị (graph data model)** đáng được xem xét.

Ví dụ, một nền tảng học trực tuyến cần trả lời:

- Người học A đang theo dõi những người học nào?
- Những người được A theo dõi đang học khóa nào mà A chưa học?
- Một khóa học yêu cầu những kiến thức tiên quyết nào, kể cả các điều kiện tiên quyết gián tiếp?
- Nếu điều chỉnh một kỹ năng trong chương trình, những khóa học nào có thể bị ảnh hưởng qua chuỗi quan hệ phụ thuộc?
- Hai người học được kết nối qua những ai, tối đa bao nhiêu bước?

Trong các câu hỏi này, **mối quan hệ và đường đi giữa các đối tượng** quan trọng không kém nội dung của từng đối tượng. Thay vì chỉ lưu một tập bản ghi độc lập, mô hình đồ thị biểu diễn đối tượng thành **nút (node)**, mối liên hệ thành **cạnh (edge/relationship)** và dữ liệu mô tả thành **thuộc tính (property)**. Thao tác đi từ nút này sang các nút liên quan qua một hoặc nhiều cạnh gọi là **phép duyệt đồ thị (graph traversal)**.

Sau bài học, bạn có thể nhận diện nút, cạnh và thuộc tính từ yêu cầu nghiệp vụ; mô tả hướng và kiểu quan hệ; phân biệt duyệt theo độ rộng với duyệt theo độ sâu; viết các mẫu truy vấn quan hệ; và nhận biết các quyết định thiết kế cần cân nhắc khi dùng cơ sở dữ liệu đồ thị.

> **Phạm vi:** Bài tập trung vào **property graph** (đồ thị thuộc tính), một mô hình phổ biến trong hệ sinh thái graph database. Các ví dụ truy vấn sử dụng cú pháp **Cypher minh họa**, thường gặp ở Neo4j. Một số đặc điểm và cú pháp cụ thể phụ thuộc hệ quản trị và phiên bản; các khái niệm nút, cạnh, thuộc tính và phép duyệt không phụ thuộc vào một sản phẩm riêng.

## 2. Đồ thị gồm những thành phần nào?

Một đồ thị toán học được mô tả bằng tập đỉnh và tập cạnh: **G = (V, E)**. Khi triển khai dữ liệu nghiệp vụ, ta thường thêm nhãn, kiểu cạnh, thuộc tính và ràng buộc.

### 2.1. Nút (node/vertex): một đối tượng có thể nhận diện

Nút biểu diễn một đối tượng như người học, khóa học, kỹ năng, sản phẩm, địa điểm hoặc tài khoản.

Ví dụ nút người học:

~~~text
(L001: Learner)
  learnerId = "L001"
  name      = "An"
  joinedAt  = "2026-09-01"
~~~

Một nút thường có:

- **Định danh nghiệp vụ:** Chẳng hạn learnerId. Định danh này nên ổn định và được kiểm tra duy nhất trong phạm vi cần thiết.
- **Nhãn (label):** Chẳng hạn Learner, Course, Skill để mô tả loại đối tượng. Một số cơ sở dữ liệu cho phép một nút có nhiều nhãn.
- **Thuộc tính:** Những cặp khóa–giá trị như name, level, createdAt.

Nhãn không phải định danh. Hai nút cùng nhãn Learner vẫn là hai người học khác nhau. Định danh nội bộ do hệ quản trị cấp cũng không nhất thiết thay thế được định danh nghiệp vụ khi tích hợp hoặc nạp lại dữ liệu.

### 2.2. Cạnh (edge/relationship): một quan hệ giữa các nút

Cạnh nối hai nút, diễn đạt một sự thật hoặc liên kết nghiệp vụ. Trong property graph, cạnh thường có:

- **Nút bắt đầu** và **nút kết thúc**.
- **Kiểu quan hệ (relationship type):** FOLLOWS, ENROLLED_IN, REQUIRES, COVERS.
- **Hướng:** A theo dõi B không đồng nghĩa B theo dõi A.
- **Thuộc tính riêng:** Ví dụ enrolledAt, status hoặc progress trên quan hệ đăng ký khóa học.

Một cạnh có thể được hình dung như:

~~~text
(An:Learner)-[:ENROLLED_IN {
    enrolledAt: "2026-10-01",
    progress: 0.65
}]->(NoSQL:Course)
~~~

Ở đây, **progress = 0.65** mô tả tiến độ của **An đối với khóa NoSQL**, chứ không phải thuộc tính cố hữu của An hay của khóa học.

Một số hệ cơ sở dữ liệu cho phép **nhiều cạnh cùng kiểu giữa cùng một cặp nút**. Việc cho phép hoặc ngăn những cạnh đó là quyết định theo yêu cầu nghiệp vụ và cơ chế ràng buộc của sản phẩm.

### 2.3. Thuộc tính (property): dữ liệu gắn với nút hoặc cạnh

Thuộc tính thường biểu diễn cặp khóa–giá trị. Trong ví dụ:

| Vị trí | Thuộc tính | Ý nghĩa |
|---|---|---|
| Nút Learner | learnerId | Định danh người học |
| Nút Learner | name | Tên hiển thị |
| Nút Course | courseId, title, level | Định danh, tên và độ khó khóa học |
| Nút Skill | skillCode, name | Mã kỹ năng và tên kỹ năng |
| Cạnh ENROLLED_IN | enrolledAt, progress | Thời điểm đăng ký và tiến độ của một người trong một khóa |
| Cạnh REQUIRES | mandatory | Điều kiện tiên quyết là bắt buộc hay khuyến nghị |
| Cạnh FOLLOWS | since | Thời điểm bắt đầu theo dõi |

Thuộc tính cần được đặt nơi phản ánh **đúng chủ sở hữu nghiệp vụ**. Đặt progress vào nút Course là sai nếu mỗi người học có một tiến độ khác nhau. Trong thực tế, một quan hệ có vòng đời hoặc lịch sử phức tạp (nhiều lần đăng ký, hủy rồi đăng ký lại, cấp chứng chỉ...) đôi khi phù hợp hơn khi được biểu diễn thành **nút sự kiện/đăng ký riêng**, thay vì dồn mọi dữ liệu vào một cạnh.

### 2.4. Nút, cạnh và thuộc tính khác nhau ra sao?

| Tiêu chí | Nút | Cạnh | Thuộc tính |
|---|---|---|---|
| Chức năng | Biểu diễn thực thể hoặc sự kiện | Biểu diễn liên kết giữa hai nút | Mô tả nút hoặc cạnh |
| Có liên kết đầu–cuối? | Không cần | Có | Không |
| Có thể được truy vấn độc lập? | Thường có | Có thể tìm theo kiểu/hướng/thuộc tính | Thường qua nút hoặc cạnh chủ sở hữu |
| Ví dụ | Khóa học NoSQL | An ENROLLED_IN NoSQL | progress = 0.65 |
| Quyết định cần cân nhắc | Danh tính, nhãn, vòng đời | Hướng, kiểu, lực lượng, lịch sử | Kiểu dữ liệu, tính bắt buộc, nơi lưu |

## 3. Ví dụ xuyên suốt: Đồ thị nền tảng học tập

Giả sử hệ thống có bốn người học An, Bình, Chi, Dũng; ba khóa học Java cơ bản, NoSQL căn bản và Graph Database; và một số kỹ năng.

Các loại quan hệ:

- **FOLLOWS:** Người học theo dõi người học.
- **ENROLLED_IN:** Người học tham gia khóa học.
- **REQUIRES:** Khóa học cần hoàn thành hoặc nắm kiến thức của khóa học khác trước.
- **COVERS:** Khóa học giảng dạy kỹ năng.

Sơ đồ minh họa:

~~~mermaid
flowchart LR
    A["An · Learner"]
    B["Bình · Learner"]
    C["Chi · Learner"]
    J["Java cơ bản · Course"]
    N["NoSQL căn bản · Course"]
    G["Graph Database · Course"]
    S["Duyệt đồ thị · Skill"]

    A -->|FOLLOWS| B
    B -->|FOLLOWS| C
    A -->|ENROLLED_IN| J
    B -->|ENROLLED_IN| N
    C -->|ENROLLED_IN| G
    G -->|REQUIRES| N
    G -->|COVERS| S
~~~

Từ sơ đồ có thể đọc được:

1. An theo dõi Bình; Bình theo dõi Chi. Do đó Chi có thể là người được An tiếp cận **qua hai bước theo dõi**, nhưng không có nghĩa An trực tiếp theo dõi Chi.
2. Bình đang học NoSQL căn bản; An chưa học khóa đó trong dữ liệu minh họa. Đây có thể là **ứng viên gợi ý** khi đề xuất khóa từ người An theo dõi.
3. Graph Database yêu cầu NoSQL căn bản. Muốn kiểm tra các điều kiện tiên quyết của Graph Database, ta phải duyệt **cạnh REQUIRES**, có thể qua nhiều cấp.
4. Kỹ năng Duyệt đồ thị được Graph Database bao phủ. Nếu cần tìm các khóa dạy kỹ năng này, có thể duyệt **ngược chiều cạnh COVERS** từ nút Skill tới Course.

Sơ đồ chỉ có các cạnh minh họa, không khẳng định rằng những người hoặc khóa khác không tồn tại. Trong hệ thống thật, sự vắng mặt của một cạnh có thể có nghĩa là quan hệ không có, chưa được đồng bộ, chưa được phép xem hoặc dữ liệu chưa đủ.

### 3.1. Lực lượng và quy tắc quan hệ

Đồ thị vẫn cần những quy tắc nghiệp vụ tương tự khi phân tích mô hình quan hệ:

| Quan hệ | Lực lượng ví dụ | Quy tắc |
|---|---|---|
| Learner FOLLOWS Learner | Nhiều–nhiều | Chọn có cho phép tự theo dõi không; có cần tránh tạo trùng không |
| Learner ENROLLED_IN Course | Nhiều–nhiều | Có thể cần trạng thái ACTIVE, COMPLETED, CANCELLED |
| Course REQUIRES Course | Nhiều–nhiều | Cần phát hiện chu trình phụ thuộc nếu chương trình cấm vòng lặp |
| Course COVERS Skill | Nhiều–nhiều | Một khóa dạy nhiều kỹ năng; một kỹ năng có thể xuất hiện trong nhiều khóa |

Tính chất **nhiều–nhiều** không có nghĩa phải tạo một bảng nối như trong hệ quan hệ. Bản thân các cạnh có thể biểu diễn mối liên hệ đó. Tuy nhiên, nếu mối liên hệ có nhiều sự kiện con hoặc được truy cập như một đối tượng độc lập, vẫn có lý do để dùng nút trung gian.

## 4. Hướng cạnh, kiểu cạnh và ý nghĩa quan hệ

### 4.1. Hướng cạnh không thể bị bỏ qua

Quan hệ có hướng được biểu diễn:

~~~text
(An)-[:FOLLOWS]->(Bình)
~~~

Phát biểu đúng là **An theo dõi Bình**. Phát biểu **Bình theo dõi An** không được suy ra từ cạnh này.

Một số mối quan hệ về mặt nghiệp vụ có tính đối xứng, chẳng hạn “là bạn của nhau”. Có thể biểu diễn bằng một loại quan hệ đã thống nhất hướng quy ước, bằng hai cạnh có hướng ngược nhau, hoặc bằng thiết kế khác phù hợp khả năng truy vấn. Quan trọng nhất là **quy tắc dữ liệu nhất quán**, đặc biệt khi nhập, cập nhật và xóa quan hệ.

### 4.2. Kiểu cạnh là ngữ nghĩa, không phải chỉ là một đường nối

Giữa cùng hai đối tượng có thể có nhiều quan hệ khác nhau:

~~~text
(An)-[:FOLLOWS]->(Bình)
(An)-[:MENTORS]->(Bình)
~~~

Đường đi trên cạnh FOLLOWS không tự động thỏa câu hỏi về MENTORS. Khi thiết kế phép duyệt, cần xác định **tập kiểu cạnh được phép đi qua**, thay vì chỉ lấy mọi hàng xóm trong đồ thị.

### 4.3. Một chiều truy vấn và một chiều lưu dữ liệu

Nếu cạnh lưu dưới dạng:

~~~text
(GraphDatabase)-[:REQUIRES]->(NoSQL)
~~~

thì:

- Đi **xuôi chiều REQUIRES** từ GraphDatabase tới NoSQL để tìm điều kiện tiên quyết.
- Đi **ngược chiều REQUIRES** từ NoSQL tới GraphDatabase để tìm các khóa học phụ thuộc vào NoSQL.

Không nhất thiết phải ghi thêm một cạnh IS_PREREQUISITE_OF có ý nghĩa trùng lặp nếu hệ quản trị hỗ trợ truy vấn ngược chiều cạnh. Sao chép cả hai hướng có thể làm phát sinh rủi ro không đồng bộ nếu không có cơ chế quản lý.

## 5. Phép duyệt quan hệ (graph traversal) là gì?

**Duyệt đồ thị** là quá trình bắt đầu từ một hoặc nhiều nút, đi qua những cạnh thỏa điều kiện để tìm nút, cạnh hoặc đường đi cần thiết.

Một phép duyệt thường được xác định bằng:

1. **Điểm bắt đầu (start node):** Ví dụ Learner có learnerId = L001.
2. **Chiều đi:** Theo chiều cạnh, ngược chiều hay chấp nhận cả hai.
3. **Loại cạnh:** FOLLOWS, ENROLLED_IN, REQUIRES...
4. **Độ dài đường đi:** Một bước, hai bước, hoặc trong khoảng 1–3 bước.
5. **Bộ lọc:** Chỉ khóa ACTIVE, chỉ cạnh tạo sau một thời điểm, chỉ nút mà người dùng được phép xem.
6. **Quy tắc lặp:** Có cho phép gặp lại nút/cạnh đã đi qua không?
7. **Kết quả và thứ tự:** Trả về nút, toàn bộ đường đi, khoảng cách, top N hoặc tập không trùng lặp.

### 5.1. Một bước, nhiều bước và vùng lân cận

Một nút **hàng xóm** là nút được nối trực tiếp qua một cạnh thích hợp. Duyệt:

~~~text
An --FOLLOWS--> Bình --FOLLOWS--> Chi
~~~

- 1 bước (1 hop) từ An: Bình.
- 2 bước theo FOLLOWS: Chi.
- Trong tối đa 2 bước: Bình và Chi.

Kết quả có thể khác nếu tính **đúng hai bước** so với **tối đa hai bước**, hoặc nếu không cho phép quay lại nút xuất phát. Hai người có thể được nối qua nhiều đường đi khác nhau, nên cần quyết định trả về mỗi người một lần hay tất cả đường đi.

### 5.2. Đường đi (path), chu trình (cycle) và độ dài

**Đường đi** là một chuỗi nút nối bằng các cạnh hợp lệ. **Độ dài đường đi theo hop** là số cạnh trên chuỗi, không phải số nút. Đường đi An → Bình → Chi có độ dài 2.

**Chu trình** xuất hiện khi một đường đi quay lại nút đã gặp. Ví dụ:

~~~text
An -> Bình -> Chi -> An
~~~

Nếu truy vấn cho phép đi qua những chu trình vô hạn, số khả năng có thể tăng rất lớn. Vì vậy, khi duyệt quan hệ có chu trình, cần xác định giới hạn độ sâu và quy tắc không lặp nút/cạnh. Các hệ quản trị có thể áp dụng quy tắc “đường đi hợp lệ” khác nhau: không lặp cạnh, không lặp nút hoặc cho phép lặp trong những trường hợp cụ thể.

### 5.3. Bậc nút và nút có nhiều kết nối

**Bậc (degree)** của một nút là số cạnh liên quan. Với đồ thị có hướng:

- **In-degree:** Số cạnh đi vào nút.
- **Out-degree:** Số cạnh đi ra từ nút.

Ví dụ, một người học nổi tiếng có thể nhận hàng trăm nghìn cạnh FOLLOWS; đây là nút có bậc rất cao. Những nút như vậy thường làm phép duyệt sinh nhiều ứng viên và tiêu thụ tài nguyên. Khi thiết kế truy vấn, không nên giả định mỗi nút có ít hàng xóm.

## 6. Hai chiến lược duyệt phổ biến: BFS và DFS

### 6.1. Duyệt theo chiều rộng (Breadth-First Search, BFS)

BFS khám phá các nút ở khoảng cách 1 trước, rồi khoảng cách 2, khoảng cách 3... so với điểm bắt đầu. Cấu trúc dữ liệu thường dùng là **hàng đợi (queue)**.

Xét đồ thị:

~~~text
          B ---- D
         /        \
        A          F
         \        /
          C ---- E
~~~

Nếu bắt đầu từ A và duyệt theo thứ tự láng giềng B trước C, một thứ tự BFS có thể là:

~~~text
A, B, C, D, E, F
~~~

Thứ tự chính xác giữa các nút cùng tầng phụ thuộc thứ tự lấy hàng xóm và cách triển khai. BFS có đặc tính quan trọng: **trong đồ thị không trọng số, BFS tìm được số bước ít nhất từ nút bắt đầu đến các nút có thể tới**, nếu các cạnh đều được tính là một bước và phép duyệt tuân đúng điều kiện của bài toán.

Giả mã:

~~~text
function BFS(start):
    queue = [(start, 0)]
    visited = {start}

    while queue is not empty:
        (current, depth) = pop_front(queue)
        process(current, depth)

        for next in outgoing_neighbors(current):
            if next not in visited:
                visited.add(next)
                push_back(queue, (next, depth + 1))
~~~

Phù hợp để tìm người ở tối đa 2 bậc kết nối, tính khoảng cách theo số cạnh hoặc mở rộng từ gần tới xa.

### 6.2. Duyệt theo chiều sâu (Depth-First Search, DFS)

DFS đi sâu theo một nhánh trước khi quay lại thử nhánh khác. Cấu trúc thường dùng là **ngăn xếp (stack)** hoặc lời gọi đệ quy.

Với cùng đồ thị, một thứ tự DFS khả dĩ là:

~~~text
A, B, D, F, E, C
~~~

Giả mã:

~~~text
function DFS(start):
    stack = [start]
    visited = {}

    while stack is not empty:
        current = pop(stack)

        if current in visited:
            continue

        visited.add(current)
        process(current)

        for next in outgoing_neighbors(current):
            if next not in visited:
                push(stack, next)
~~~

DFS thường hữu ích khi cần khám phá thành phần liên thông, phát hiện chu trình (với trạng thái duyệt thích hợp), duyệt phụ thuộc hoặc tìm một đường đi thỏa điều kiện. **DFS thuần không đảm bảo tìm đường có ít cạnh nhất**.

### 6.3. So sánh BFS và DFS

| Tiêu chí | BFS | DFS |
|---|---|---|
| Chiến lược | Khám phá lần lượt theo độ sâu tăng dần | Đi sâu rồi quay lui |
| Cấu trúc thường dùng | Hàng đợi | Ngăn xếp hoặc đệ quy |
| Đường đi ít hop nhất trong đồ thị không trọng số | Có, khi triển khai đúng | Không đảm bảo |
| Bộ nhớ trong thực tế | Có thể lớn nếu một tầng rất rộng | Thường phụ thuộc chiều sâu và nhánh đang xét; vẫn có thể lớn |
| Ứng dụng phổ biến | Khoảng cách xã hội, k-hop neighborhood | Phát hiện chu trình, khảo sát phụ thuộc, tìm đường |

Nếu biểu diễn đồ thị bằng danh sách kề và duyệt toàn bộ phần liên thông, cả BFS và DFS thường có độ phức tạp thời gian **O(|V| + |E|)**, với |V| là số nút và |E| là số cạnh được xét. Bộ nhớ theo cách triển khai có thể ở mức **O(|V|)**. Đây là kết quả thuật toán cơ bản; hiệu năng truy vấn trong cơ sở dữ liệu còn chịu ảnh hưởng của bộ lọc, chỉ mục, chi phí truy xuất lưu trữ, song song hóa và số kết quả trả về.

### 6.4. Đường đi ngắn nhất có trọng số khác gì?

Nếu mỗi cạnh có **trọng số** như chi phí, khoảng cách hoặc thời gian, “ít cạnh nhất” chưa chắc là “rẻ nhất”.

~~~text
A --(10)--> B
A --(2)--> C --(2)--> B
~~~

Đường A → B có một cạnh nhưng tổng trọng số 10. Đường A → C → B có hai cạnh nhưng tổng trọng số 4.

- **BFS** phù hợp khi mọi cạnh có cùng chi phí, hoặc chỉ quan tâm số bước.
- **Dijkstra** có thể dùng để tìm đường đi tổng trọng số nhỏ nhất khi các trọng số không âm.
- Với trọng số âm hoặc ràng buộc đặc biệt, cần chọn thuật toán khác phù hợp; không mặc định Dijkstra có thể xử lý mọi trường hợp.

Trước khi tìm “đường ngắn nhất”, phải nói rõ **ngắn nhất theo số cạnh, tổng chi phí, tổng thời gian hay tiêu chí nào khác**.

## 7. Biểu diễn và truy vấn bằng Cypher minh họa

Cypher là ngôn ngữ truy vấn theo mẫu đồ thị. Các ví dụ dưới đây dùng cú pháp quen thuộc với Neo4j để thể hiện cách nghĩ từ yêu cầu nghiệp vụ sang mẫu liên kết. Chúng là ví dụ độc lập, sử dụng tập dữ liệu nhỏ và có thể cần điều chỉnh theo phiên bản đang dùng.

### 7.1. Tạo nút và cạnh

Đầu tiên tạo các nút người học và khóa học; dùng MERGE theo khóa nghiệp vụ để có thể chạy lại mà không cố ý tạo thêm nút cho cùng khóa.

~~~cypher
MERGE (an:Learner {learnerId: 'L001'})
SET an.name = 'An';

MERGE (binh:Learner {learnerId: 'L002'})
SET binh.name = 'Bình';

MERGE (chi:Learner {learnerId: 'L003'})
SET chi.name = 'Chi';

MERGE (java:Course {courseId: 'C001'})
SET java.title = 'Java cơ bản';

MERGE (nosql:Course {courseId: 'C002'})
SET nosql.title = 'NoSQL căn bản';

MERGE (graph:Course {courseId: 'C003'})
SET graph.title = 'Graph Database';
~~~

Tạo các quan hệ:

~~~cypher
MATCH (an:Learner {learnerId: 'L001'})
MATCH (binh:Learner {learnerId: 'L002'})
MERGE (an)-[follow:FOLLOWS]->(binh)
SET follow.since = date('2026-09-15');

MATCH (binh:Learner {learnerId: 'L002'})
MATCH (chi:Learner {learnerId: 'L003'})
MERGE (binh)-[:FOLLOWS]->(chi);

MATCH (an:Learner {learnerId: 'L001'})
MATCH (java:Course {courseId: 'C001'})
MERGE (an)-[e:ENROLLED_IN]->(java)
SET e.enrolledAt = date('2026-10-01'),
    e.progress = 0.65;

MATCH (binh:Learner {learnerId: 'L002'})
MATCH (nosql:Course {courseId: 'C002'})
MERGE (binh)-[e:ENROLLED_IN]->(nosql)
SET e.enrolledAt = date('2026-10-03'),
    e.progress = 0.30;

MATCH (graph:Course {courseId: 'C003'})
MATCH (nosql:Course {courseId: 'C002'})
MERGE (graph)-[:REQUIRES]->(nosql);
~~~

Trong Cypher:

- **(n:Label)** biểu diễn nút có nhãn Label.
- **-[:TYPE]->** biểu diễn quan hệ có kiểu TYPE và hướng từ trái sang phải.
- **MATCH** tìm mẫu; **MERGE** tìm hoặc tạo mẫu phù hợp; **SET** cập nhật thuộc tính.
- Điều kiện **{learnerId: 'L001'}** dùng để xác định nút bắt đầu. Trong môi trường thực tế, sử dụng tham số truy vấn để truyền dữ liệu từ ứng dụng thay vì nối chuỗi đầu vào.

**Lưu ý về tính duy nhất:** MERGE không thay thế hoàn toàn cho ràng buộc duy nhất ở mức cơ sở dữ liệu trong tình huống nhiều yêu cầu chạy đồng thời. Nếu learnerId hay courseId bắt buộc là duy nhất, cần định nghĩa ràng buộc hoặc cơ chế tương đương mà hệ quản trị hỗ trợ.

Ví dụ ràng buộc Cypher trong Neo4j:

~~~cypher
CREATE CONSTRAINT learner_id_unique IF NOT EXISTS
FOR (l:Learner)
REQUIRE l.learnerId IS UNIQUE;
~~~

Tương tự, có thể định nghĩa ràng buộc duy nhất cho courseId. Trước khi thêm ràng buộc lên dữ liệu đã tồn tại, cần xử lý các bản ghi trùng.

### 7.2. Tìm quan hệ trực tiếp: một hop

“An đang theo dõi những ai?”

~~~cypher
MATCH (an:Learner {learnerId: 'L001'})-[:FOLLOWS]->(other:Learner)
RETURN other.learnerId AS learnerId, other.name AS name
ORDER BY name;
~~~

Mẫu **-[:FOLLOWS]->** quy định chỉ đi theo cạnh FOLLOWS hướng từ An tới người được theo dõi. Nếu yêu cầu là tìm “ai đang theo dõi An”, cần đổi hướng mũi tên:

~~~cypher
MATCH (follower:Learner)-[:FOLLOWS]->(an:Learner {learnerId: 'L001'})
RETURN follower.learnerId, follower.name;
~~~

### 7.3. Duyệt hai hop: người được theo dõi của người được theo dõi

~~~cypher
MATCH (an:Learner {learnerId: 'L001'})
      -[:FOLLOWS]->(:Learner)
      -[:FOLLOWS]->(candidate:Learner)
WHERE candidate <> an
RETURN DISTINCT candidate.learnerId AS learnerId,
                candidate.name AS name;
~~~

**DISTINCT** loại kết quả lặp nếu cùng một người có thể đi tới qua nhiều đường. Điều kiện candidate <> an tránh đề xuất chính người dùng hiện tại trong trường hợp dữ liệu có chu trình.

Để chỉ đề xuất người chưa được An theo dõi, thêm điều kiện loại trừ cạnh trực tiếp:

~~~cypher
MATCH (an:Learner {learnerId: 'L001'})
      -[:FOLLOWS]->(:Learner)
      -[:FOLLOWS]->(candidate:Learner)
WHERE candidate <> an
  AND NOT EXISTS {
      MATCH (an)-[:FOLLOWS]->(candidate)
  }
RETURN DISTINCT candidate.learnerId, candidate.name;
~~~

### 7.4. Duyệt qua nhiều kiểu quan hệ: đề xuất khóa học

“Những người An theo dõi đang học khóa nào mà An chưa đăng ký?”

~~~cypher
MATCH (an:Learner {learnerId: 'L001'})
      -[:FOLLOWS]->(friend:Learner)
      -[:ENROLLED_IN]->(course:Course)
WHERE NOT EXISTS {
    MATCH (an)-[:ENROLLED_IN]->(course)
}
RETURN course.courseId AS courseId,
       course.title AS title,
       count(DISTINCT friend) AS followingCount
ORDER BY followingCount DESC, title
LIMIT 10;
~~~

Phép duyệt dùng chuỗi **FOLLOWS → ENROLLED_IN**, chứ không duyệt mọi cạnh. Phép đếm biểu thị **số người An theo dõi đang tham gia khóa đó** trong dữ liệu. Đó chỉ là tín hiệu đề xuất ban đầu; không đồng nghĩa chất lượng khóa học hoặc việc người dùng chắc chắn muốn học khóa.

Nếu chỉ tính đăng ký còn hoạt động, mô hình cần có thuộc tính trạng thái của cạnh ENROLLED_IN và thêm bộ lọc tương ứng.

### 7.5. Quan hệ độ dài biến thiên: nhiều cấp tiên quyết

“Khóa Graph Database có những điều kiện tiên quyết nào, trực tiếp hoặc gián tiếp, tối đa năm cấp?”

~~~cypher
MATCH (graph:Course {courseId: 'C003'})
      -[:REQUIRES*1..5]->(prerequisite:Course)
RETURN DISTINCT prerequisite.courseId,
                prerequisite.title;
~~~

Trong cú pháp độ dài biến thiên này, **\*1..5** nghĩa là đi qua từ một đến năm cạnh REQUIRES. Đây là cách viết phổ biến của Cypher truyền thống; các phiên bản hoặc chuẩn truy vấn mới có thể có cú pháp khác.

Nếu muốn biết **đường quan hệ cụ thể** thay vì chỉ tập khóa tiên quyết:

~~~cypher
MATCH path = (graph:Course {courseId: 'C003'})
             -[:REQUIRES*1..5]->(prerequisite:Course)
RETURN path
LIMIT 20;
~~~

Chú ý: một nút có thể xuất hiện ở cuối nhiều đường khác nhau. Số **đường đi** có thể tăng nhanh hơn số **nút kết quả**, đặc biệt khi có nhiều nhánh và quan hệ vòng.

### 7.6. Đường ngắn nhất theo số hop

“An và Chi liên hệ với nhau qua bao nhiêu quan hệ FOLLOWS, cho phép đi cả hai hướng, giới hạn tối đa sáu cạnh?”

~~~cypher
MATCH (an:Learner {learnerId: 'L001'})
MATCH (chi:Learner {learnerId: 'L003'})
MATCH p = shortestPath((an)-[:FOLLOWS*..6]-(chi))
RETURN p, length(p) AS hops;
~~~

Đây là ví dụ **đường ngắn nhất theo số cạnh** trên quan hệ FOLLOWS, cho phép đi cả hai hướng. Nếu nghiệp vụ yêu cầu “người A theo dõi qua chuỗi hướng ra ngoài” thì không được tự ý bỏ hướng cạnh.

Hàm, cú pháp độ dài và giới hạn của truy vấn đường ngắn nhất tùy hệ quản trị, phiên bản và bộ điều kiện. Với đồ thị có trọng số, cần thuật toán có xét trọng số như đã trình bày ở mục 6.4.

## 8. Mô hình hóa nghiệp vụ thành đồ thị

Để xác định nút, cạnh và thuộc tính, hãy xuất phát từ **câu hỏi nghiệp vụ và quy tắc quan hệ**, không xuất phát từ tên bảng hay khả năng vẽ sơ đồ.

### 8.1. Quy trình chuyển yêu cầu thành mô hình

Giả sử nhận yêu cầu: “Quản trị viên muốn biết khóa học nào bị ảnh hưởng nếu nội dung khóa NoSQL căn bản thay đổi.”

**Bước 1 – Tìm đối tượng:** Khóa học là nút Course có định danh courseId.

**Bước 2 – Tìm quan hệ:** Khóa học A **REQUIRES** khóa học B nếu A phụ thuộc vào kiến thức của B.

**Bước 3 – Chốt hướng:** A → B là “A yêu cầu B”; muốn tìm các khóa bị ảnh hưởng bởi B, phải đi **ngược chiều REQUIRES** từ B tới các khóa phụ thuộc.

**Bước 4 – Chốt số bước:** Phải xét cả phụ thuộc trực tiếp và gián tiếp, vì A có thể yêu cầu B, còn B yêu cầu C.

**Bước 5 – Chốt kết quả:** Danh sách courseId duy nhất, tiêu đề, khoảng cách phụ thuộc và có thể đường dẫn lý do ảnh hưởng.

**Bước 6 – Chốt điều kiện:** Có xét khóa đã lưu trữ không? Quan hệ tiên quyết mang tính bắt buộc hay gợi ý? Có giới hạn độ sâu để tránh kết quả quá lớn không?

Đầu ra có thể trở thành truy vấn dạng:

~~~cypher
MATCH (changed:Course {courseId: 'C002'})
MATCH (affected:Course)-[:REQUIRES*1..5]->(changed)
RETURN DISTINCT affected.courseId, affected.title;
~~~

Ở đây ta đã sử dụng **hướng ngược với cách đọc “tìm tiên quyết”**, dù cả hai đều dựa trên một loại cạnh REQUIRES.

### 8.2. Khi nào một quan hệ nên là cạnh có thuộc tính?

Sử dụng cạnh có thuộc tính khi dữ liệu mô tả chính liên kết đó. Ví dụ:

~~~text
(An)-[:ENROLLED_IN {
  enrolledAt: 2026-10-01,
  progress: 0.65,
  status: "ACTIVE"
}]->(Java)
~~~

Điểm mạnh là các câu hỏi “An học gì?” hoặc “Ai học Java?” đi thẳng theo cạnh. Nhưng cần xem lại nếu quan hệ có nhiều phiên bản lịch sử hoặc nhiều thực thể con liên quan.

Ví dụ một người có thể đăng ký cùng khóa ba lần ở ba kỳ khác nhau, mỗi lần có học phí, chứng chỉ, bài kiểm tra, trạng thái và nhật ký riêng. Lúc đó một **nút Enrollment** với khóa enrollmentId có thể phản ánh nghiệp vụ rõ hơn:

~~~text
(An)-[:HAS_ENROLLMENT]->(Enrollment E01)-[:FOR_COURSE]->(Java)
(An)-[:HAS_ENROLLMENT]->(Enrollment E02)-[:FOR_COURSE]->(Java)
~~~

Vì E01 và E02 là hai lần đăng ký khác nhau, mô hình này giúp tránh nhầm lẫn “quan hệ hiện tại” với “lịch sử các lần đăng ký”.

### 8.3. Có nên biến mọi thuộc tính thành nút?

Không. Chẳng hạn tên khóa học, ngày phát hành và trạng thái hiển thị thường có thể là thuộc tính của nút Course. Nhưng **Skill** có thể xứng đáng là một nút vì:

- Nhiều khóa dùng chung một kỹ năng.
- Người dùng cần tìm mọi khóa liên quan đến kỹ năng đó.
- Kỹ năng có các quan hệ riêng như PREREQUISITE_SKILL hoặc RELATED_TO.
- Kỹ năng có vòng đời và thông tin quản lý độc lập.

Một quy tắc hữu ích: nếu thông tin có **danh tính, quan hệ và nhu cầu duyệt độc lập**, cân nhắc thành nút; nếu chỉ mô tả đối tượng khác và không có quan hệ riêng đáng kể, cân nhắc giữ làm thuộc tính.

### 8.4. Quan hệ có thời gian hiệu lực

Quan hệ “đã theo dõi”, “đang làm việc tại”, “đang thuê” hoặc “đã đăng ký” có thể thay đổi theo thời gian. Nếu chỉ lưu cạnh hiện hành, truy vấn “Ở ngày X, ai theo dõi ai?” có thể không trả lời được.

Các lựa chọn tùy nghiệp vụ:

- Lưu **validFrom** và **validTo** trên cạnh phiên bản nếu công nghệ và quy tắc dữ liệu cho phép.
- Lưu sự kiện thay đổi quan hệ thành nút/bản ghi riêng.
- Lưu cả đồ thị trạng thái hiện hành và lịch sử sự kiện, có quy tắc đồng bộ.

Phải phân biệt **thời điểm sự kiện xảy ra**, **thời điểm hệ thống ghi nhận**, và **thời gian hiệu lực nghiệp vụ** nếu hệ thống cần truy vấn lịch sử chính xác. Tính lịch sử không tự có chỉ vì dữ liệu được lưu dưới dạng đồ thị.

## 9. Tư duy thiết kế truy vấn trước khi thiết kế lưu trữ

### 9.1. Ma trận câu hỏi và phép duyệt

| Câu hỏi nghiệp vụ | Nút bắt đầu | Cạnh và hướng | Độ sâu | Đầu ra |
|---|---|---|---|---|
| An theo dõi ai? | Learner An | FOLLOWS → | 1 | Danh sách Learner |
| Ai theo dõi An? | Learner An | ← FOLLOWS | 1 | Danh sách Learner |
| Gợi ý người quen qua người theo dõi | Learner An | FOLLOWS → FOLLOWS → | 2 | Learner duy nhất, chưa theo dõi |
| Gợi ý khóa qua người An theo dõi | Learner An | FOLLOWS → ENROLLED_IN → | 2 | Khóa học và số người liên quan |
| Điều kiện tiên quyết của khóa C | Course C | REQUIRES → | 1..K | Danh sách Course tiên quyết |
| Khóa nào phụ thuộc C | Course C | ← REQUIRES | 1..K | Danh sách Course bị ảnh hưởng |
| Khóa dạy kỹ năng S | Skill S | ← COVERS | 1 | Danh sách Course |
| Tìm đường liên hệ giữa A và B | Learner A, Learner B | FOLLOWS theo chiều đã chốt | Có giới hạn | Đường đi và số hop |

Ma trận giúp phát hiện thiếu cạnh hoặc thiếu thông tin. Ví dụ nếu muốn loại gợi ý từ các khóa đã hoàn tất, cần biết trạng thái của ENROLLED_IN. Nếu cần tính “đề xuất theo bạn bè có độ tin cậy cao”, phải định nghĩa độ tin cậy và nguồn của nó thay vì tự suy từ số cạnh.

### 9.2. Đọc và ghi cần được xét cùng nhau

Đồ thị mạnh ở các truy vấn quan hệ, nhưng mỗi quyết định tổ chức cạnh cũng ảnh hưởng việc ghi:

- Một người học có thể theo dõi/bỏ theo dõi thường xuyên. Cần tránh cạnh trùng và quy định xóa cạnh hay đánh dấu ngừng hiệu lực.
- Một khóa được sửa điều kiện tiên quyết có thể ảnh hưởng tới nhiều phép duyệt khác. Cần xác định kiểm soát chu trình và tác động thay đổi.
- Một người hủy đăng ký rồi đăng ký lại có thể cần giữ lịch sử; xóa cạnh hiện hành có thể làm mất dữ liệu kiểm toán.
- Khi xóa nút, cần xác định các cạnh liên quan sẽ được xử lý ra sao theo chính sách và chức năng của hệ quản trị.

Không có mô hình nào giúp tránh hoàn toàn việc cân bằng giữa đơn giản khi đọc, chi phí cập nhật và bảo đảm toàn vẹn.

## 10. Hiệu năng và những giới hạn khi duyệt đồ thị

### 10.1. Vì sao truy vấn nhiều hop dễ bùng nổ?

Giả sử trung bình mỗi nút có b cạnh phù hợp và ta duyệt độ sâu k. Trong trường hợp phân nhánh mạnh, số ứng viên theo từng mức có thể xấp xỉ b, b², ..., bᵏ trước khi loại trùng và lọc. Với b = 20 và k = 4, riêng số tổ hợp ở mức cuối có thể lên tới **160.000**, ngay cả khi số nút duy nhất thực tế ít hơn.

Đó là lý do truy vấn “tìm mọi đường đi với mọi loại quan hệ, không giới hạn độ sâu” thường rủi ro về hiệu năng hoặc không rõ ý nghĩa nghiệp vụ.

### 10.2. Những kỹ thuật kiểm soát duyệt

1. **Chọn nút xuất phát chính xác:** Dùng định danh nghiệp vụ và chỉ mục/ràng buộc phù hợp để tìm start node nhanh.
2. **Chỉ duyệt loại cạnh cần thiết:** FOLLOWS, REQUIRES, v.v. Thêm bộ lọc trên trạng thái hoặc thời gian nếu có.
3. **Giới hạn số hop:** Đặt khoảng 1..2 hoặc 1..5 theo yêu cầu thực thay vì mở rộng vô hạn.
4. **Quy định tính duy nhất của nút/đường đi:** DISTINCT chỉ làm sạch kết quả; không nhất thiết giảm được chi phí duyệt trước đó. Khi phù hợp, dùng cơ chế tránh lặp ngay trong quá trình mở rộng.
5. **Giới hạn kết quả và phân trang:** LIMIT hữu ích cho số bản ghi trả về, nhưng không phải lúc nào cũng ngăn được khối lượng công việc trước khi sắp xếp hoặc tổng hợp.
6. **Quan tâm nút có bậc rất cao:** Một “người nổi tiếng” hoặc “danh mục chung” có thể dẫn tới hàng triệu cạnh. Cần đo số quan hệ thực tế và có chiến lược cho trường hợp này.
7. **Đo kế hoạch truy vấn:** Dùng công cụ EXPLAIN/PROFILE hoặc công cụ tương đương của hệ quản trị để hiểu số hàng trung gian, số lần mở rộng cạnh và chi phí.
8. **Cân nhắc tiền tính toán:** Với câu hỏi lặp đi lặp lại ở quy mô lớn, có thể lưu kết quả đề xuất hoặc các chỉ số tổng hợp, kèm thời gian làm mới.

### 10.3. Phân biệt tìm hàng xóm với thống kê toàn đồ thị

“Tìm các khóa liên quan tới khóa C trong tối đa ba bước” là truy vấn cục bộ quanh một nút. “Tính mức độ trung tâm của mọi người dùng” hay “Tìm các cộng đồng lớn trong toàn đồ thị” là bài toán phân tích toàn đồ thị, có thể cần thuật toán và môi trường xử lý riêng.

Không nên suy ra rằng một cơ sở dữ liệu đồ thị có thể thực hiện mọi phép phân tích lớn nhanh chỉ vì nó hỗ trợ traversal tốt. Hiệu quả phụ thuộc thuật toán, dữ liệu, phần cứng, tính phân tán và cách chạy.

## 11. Đồ thị so với các mô hình dữ liệu NoSQL khác

| Mô hình | Cách tổ chức nổi bật | Truy vấn thường thuận lợi | Khi quan hệ nhiều hop trở nên quan trọng |
|---|---|---|---|
| Key–value | Khóa → giá trị | Lấy/cập nhật trực tiếp theo khóa | Ứng dụng phải tự theo dõi và nối dữ liệu qua nhiều khóa nếu không có chức năng bổ sung |
| Document | Tài liệu với trường và cấu trúc lồng | Lấy đối tượng và các dữ liệu thường đọc cùng nhau | Có thể cần tham chiếu, nhiều lần truy vấn hoặc chức năng graph riêng |
| Wide-column | Hàng/phân vùng được tổ chức theo khóa truy cập | Truy vấn được thiết kế quanh khóa phân vùng và thứ tự dữ liệu | Cần cân nhắc đường duyệt và phân vùng vì quan hệ có thể trải nhiều nơi |
| Graph | Nút, cạnh, thuộc tính | Tìm hàng xóm, mẫu liên kết và đường đi | Là trọng tâm mô hình hóa |

Ví dụ nếu nghiệp vụ chính chỉ là “Lấy cấu hình theo userId”, cơ sở dữ liệu key–value có thể đơn giản hơn. Nếu cần “Tìm các tài khoản liên quan qua 2–5 lớp thiết bị dùng chung, địa chỉ và chuyển tiền”, mô hình đồ thị có thể phản ánh trực tiếp bài toán hơn.

Trong thực tế, một ứng dụng có thể dùng nhiều hệ dữ liệu: cơ sở dữ liệu giao dịch lưu đơn hàng, cơ sở dữ liệu đồ thị phục vụ khám phá liên kết và hệ phân tích lưu số liệu tổng hợp. Đó là quyết định kiến trúc dựa vào yêu cầu, không phải quy luật mọi hệ thống phải áp dụng.

### 11.1. Property graph và RDF graph khác nhau như thế nào?

Ngoài property graph, còn có mô hình **RDF** để biểu diễn dữ liệu dưới dạng các bộ ba **subject – predicate – object**. Ví dụ:

~~~text
An       follows       Binh
Course3  requires      Course2
~~~

Trong RDF, predicate thể hiện quan hệ hoặc thuộc tính, object có thể là một tài nguyên hoặc giá trị literal. RDF thường đi cùng URI/IRI, ontology và ngôn ngữ truy vấn SPARQL. Property graph thường cho phép gắn thuộc tính trực tiếp lên nút và cạnh, với ngôn ngữ truy vấn kiểu mẫu hoặc phép duyệt như Cypher/Gremlin. Cách biểu diễn thuộc tính của chính một quan hệ trong RDF cần cấu trúc bổ sung tùy trường hợp.

Hai mô hình có mục tiêu và hệ sinh thái khác nhau, nhưng cùng mang ý tưởng cốt lõi: **quan hệ là phần dữ liệu được mô hình hóa và truy vấn tường minh**.

## 12. Nạp dữ liệu và giữ tính nhất quán quan hệ

Khi chuyển dữ liệu từ CSV, SQL hoặc dịch vụ khác sang graph database, thứ tự và cách đối chiếu định danh là yếu tố quan trọng.

### 12.1. Ví dụ cấu trúc dữ liệu nguồn

Tệp learners.csv:

~~~csv
learnerId,name
L001,An
L002,Binh
L003,Chi
~~~

Tệp follows.csv:

~~~csv
fromLearnerId,toLearnerId,since
L001,L002,2026-09-15
L002,L003,2026-09-20
~~~

Tệp courses.csv:

~~~csv
courseId,title
C001,Java co ban
C002,NoSQL can ban
C003,Graph Database
~~~

Tệp requires.csv:

~~~csv
courseId,requiredCourseId
C003,C002
~~~

### 12.2. Quy trình nạp gợi ý

1. **Chuẩn hóa định danh:** Xác định learnerId, courseId có giá trị, không trùng và ổn định. Không nối dữ liệu bằng tên hiển thị.
2. **Nạp hoặc đồng bộ nút:** Tạo Learner, Course theo khóa nghiệp vụ, với ràng buộc duy nhất khi phù hợp.
3. **Nạp cạnh theo hai đầu mút:** Tìm chính xác nút nguồn và đích từ fromLearnerId/toLearnerId hay courseId/requiredCourseId.
4. **Xử lý đầu mút thiếu:** Quy định tạm giữ, từ chối hay đưa vào danh sách lỗi khi cạnh tham chiếu nút chưa tồn tại; không âm thầm tạo sai nút nếu không có quy tắc.
5. **Chống nạp trùng:** Dùng khóa quan hệ hoặc quy tắc định danh phù hợp. Với các lần đăng ký nhiều phiên bản, khóa cần phân biệt enrollmentId hoặc thời kỳ, không chỉ cặp người–khóa.
6. **Kiểm tra số lượng kỹ thuật:** Ghi số bản ghi nguồn, số nút và cạnh được tạo/cập nhật, số lỗi tham chiếu, số bản ghi lặp.
7. **Đồng bộ cập nhật/xóa:** Xác định cách xử lý sự kiện đến muộn, thay đổi hai đầu quan hệ, xóa mềm và lịch sử.

**Chú ý:** Ràng buộc đồ thị chỉ đảm bảo những điều mà cơ sở dữ liệu thực sự hỗ trợ và đã cấu hình. Ví dụ, “một khóa không được là điều kiện tiên quyết của chính nó hoặc tạo chu trình” thường đòi hỏi quy tắc ứng dụng, giao dịch hoặc kiểm tra đồ thị bổ sung; không nên mặc định tự được bảo đảm bởi nhãn REQUIRES.

## 13. Sai lầm thường gặp

| Sai lầm | Vì sao gây vấn đề | Hướng xử lý |
|---|---|---|
| Xem nút như bảng và cạnh như JOIN nhưng không phân tích truy vấn | Mô hình có thể trở nên rời rạc, nhiều quan hệ không cần thiết | Xác định câu hỏi traversal trước, sau đó tạo nhãn/kiểu cạnh có ý nghĩa |
| Đảo hướng FOLLOWS hoặc REQUIRES | Trả về tập đối tượng ngược với ý nghĩa nghiệp vụ | Đặt tên cạnh như một phát biểu rõ nghĩa “A REQUIRES B” |
| Gắn progress của người học vào nút Course | Mọi người dùng chung một tiến độ không đúng | Gắn lên ENROLLED_IN hoặc nút Enrollment |
| Dùng một cạnh duy nhất cho các lần đăng ký lặp | Mất lịch sử khi cần phân biệt nhiều lần | Mô hình hóa từng lần đăng ký như thực thể/sự kiện |
| Duyệt mọi loại cạnh không giới hạn độ sâu | Kết quả khó giải thích và có thể tăng bùng nổ | Hạn chế kiểu cạnh, hướng, số hop và điều kiện lọc |
| Quên xử lý chu trình | Có thể lặp hoặc sinh rất nhiều đường đi | Đặt quy tắc không lặp, giới hạn độ sâu, phát hiện chu trình khi cần |
| Dùng DFS để khẳng định đường ít hop nhất | DFS không đảm bảo tối ưu về số cạnh | Dùng BFS hoặc giải thuật đường ngắn nhất phù hợp |
| Dùng BFS cho mạng có trọng số không đồng nhất | Ít cạnh không đồng nghĩa tổng chi phí nhỏ | Dùng thuật toán xét trọng số phù hợp |
| Dùng DISTINCT và LIMIT như lời đảm bảo truy vấn rẻ | Có thể đã sinh nhiều hàng trung gian trước khi lọc | Kiểm tra kế hoạch thực thi, giảm mở rộng ngay từ đầu |
| Không xử lý cạnh tham chiếu nút thiếu hoặc dữ liệu trùng | Kết quả truy vấn không đầy đủ hoặc sai lệch | Định nghĩa khóa, ràng buộc và chiến lược nạp idempotent |
| Xóa nút/cạnh mà không xét lịch sử | Mất thông tin cần đối soát hoặc truy vết | Tách trạng thái hiện hành khỏi lịch sử nếu nghiệp vụ cần |

## 14. Bài tập thực hành

### Đề bài: Mạng lưới cộng tác trong một công ty

Một công ty có nhân viên, dự án và kỹ năng:

- Nhân viên có thể **làm việc cùng** nhiều nhân viên khác.
- Nhân viên có thể **tham gia** nhiều dự án, mỗi lần tham gia có vai trò và ngày bắt đầu.
- Mỗi dự án **yêu cầu** nhiều kỹ năng.
- Mỗi nhân viên **sở hữu** nhiều kỹ năng ở những mức độ khác nhau.

Người quản lý muốn:

1. Tìm các nhân viên cộng tác trực tiếp với nhân viên E001.
2. Tìm những nhân viên có thể tiếp cận qua tối đa hai mức quan hệ cộng tác, không lặp E001.
3. Tìm dự án có kỹ năng mà E001 đã sở hữu.
4. Tìm danh sách nhân viên có thể phù hợp cho một dự án theo các kỹ năng yêu cầu, nhưng không lấy kết quả làm quyết định tuyển chọn tự động.

**Yêu cầu thực hiện:**

1. Đề xuất các nhãn nút và kiểu cạnh kèm hướng.
2. Chỉ ra hai thuộc tính nên gắn vào cạnh, giải thích vì sao.
3. Vẽ một đồ thị nhỏ ít nhất năm nút có thể trả lời câu hỏi 1–2.
4. Viết mô tả mẫu truy vấn cho câu hỏi 2: điểm bắt đầu, loại cạnh, hướng, số hop, điều kiện loại trùng.
5. Nêu một lý do khiến truy vấn hai hop có thể chậm khi dữ liệu tăng và một biện pháp giảm chi phí.

### Gợi ý giải

Một phương án:

~~~text
(:Employee {employeeId, name})
(:Project  {projectId, title})
(:Skill    {skillCode, name})

(Employee)-[:COLLABORATES_WITH]->(Employee)
(Employee)-[:WORKS_ON {role, since}]->(Project)
(Project)-[:REQUIRES_SKILL]->(Skill)
(Employee)-[:HAS_SKILL {level, verifiedAt}]->(Skill)
~~~

- **role** thuộc cạnh WORKS_ON vì cùng một người có thể là kỹ sư ở dự án A nhưng trưởng nhóm ở dự án B.
- **level** thuộc cạnh HAS_SKILL vì độ thành thạo là mức của **một người đối với một kỹ năng**.
- Nếu COLLABORATES_WITH mang ý nghĩa đối xứng, phải thống nhất cách lưu và cách truy vấn hai chiều. Một phương án là chọn một hướng quy ước theo thứ tự employeeId và luôn duyệt không xét hướng khi tìm người cộng tác; phương án khác là lưu cặp cạnh hai chiều có cơ chế đồng bộ rõ ràng.

Ví dụ biểu diễn giả sử các cạnh COLLABORATES_WITH được coi là quan hệ đối xứng:

~~~mermaid
graph LR
    E1["E001"] --- E2["E002"]
    E1 --- E3["E003"]
    E2 --- E4["E004"]
    E3 --- E5["E005"]
~~~

Các nhân viên ở một bước từ E001 là E002 và E003. Các nhân viên đạt được trong tối đa hai bước là E002, E003, E004 và E005, nếu chỉ đi qua COLLABORATES_WITH và loại E001.

Ví dụ Cypher để trả về các nút trong khoảng 1–2 hop trên quan hệ cộng tác, không xét hướng:

~~~cypher
MATCH (me:Employee {employeeId: 'E001'})
      -[:COLLABORATES_WITH*1..2]-(other:Employee)
WHERE other <> me
RETURN DISTINCT other.employeeId AS employeeId,
                other.name AS name
ORDER BY employeeId;
~~~

Với câu hỏi 3, cần làm rõ “dự án có kỹ năng mà E001 đã sở hữu” nghĩa là có **ít nhất một kỹ năng trùng**, hay **đủ toàn bộ kỹ năng bắt buộc**. Hai cách hiểu tạo ra truy vấn và kết quả khác nhau. Một kết quả phù hợp còn có thể phụ thuộc năng lực hiện tại, quyền truy cập, lịch công tác và sự đồng ý của nhân viên.

Khi số nhân viên cộng tác lớn, truy vấn hai hop có thể lan qua một nút có hàng nghìn mối quan hệ, tạo nhiều kết quả trung gian. Các biện pháp là lọc kiểu cạnh, giới hạn số hop, tránh lặp, sử dụng tiêu chí nghiệp vụ thích hợp và đo kế hoạch thực thi.

## 15. Tổng kết kiến thức và đầu ra cần có

Mô hình đồ thị biểu diễn **thực thể bằng nút**, **mối liên hệ bằng cạnh** và **dữ liệu mô tả bằng thuộc tính**. Nó đặc biệt hữu ích khi câu hỏi nghiệp vụ yêu cầu đi qua nhiều mức quan hệ, kiểm tra phụ thuộc hoặc tìm đường nối giữa các đối tượng.

Khi thiết kế một mô hình đồ thị cho hệ thống NoSQL, hãy chuẩn bị:

1. **Danh mục nút:** Nhãn, khóa định danh và các thuộc tính cốt lõi.
2. **Danh mục cạnh:** Kiểu, hướng, lực lượng, thuộc tính, quy tắc tồn tại và vòng đời.
3. **Sơ đồ quan hệ:** Ví dụ đủ rõ để người nghiệp vụ xác nhận ý nghĩa từng cạnh.
4. **Ma trận phép duyệt:** Nút bắt đầu, các kiểu cạnh/hướng, độ sâu, bộ lọc và kết quả mong muốn.
5. **Quy tắc toàn vẹn và nạp dữ liệu:** Định danh duy nhất, chống lặp, xử lý nút thiếu, lịch sử và chu trình.
6. **Yêu cầu hiệu năng:** Quy mô nút/cạnh, bậc nút, độ dài đường đi, tần suất truy vấn và giới hạn kết quả.

Điểm cốt lõi là **mô hình hóa đúng ý nghĩa của quan hệ trước khi viết truy vấn**. Khi biết rõ đường đi nào có giá trị nghiệp vụ, việc lựa chọn cấu trúc đồ thị, thuật toán duyệt và giải pháp lưu trữ sẽ có cơ sở để đánh giá và kiểm chứng.

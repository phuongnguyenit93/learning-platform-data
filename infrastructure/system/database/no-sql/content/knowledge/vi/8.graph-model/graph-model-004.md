# Chọn nút hay thuộc tính dựa trên nhu cầu truy vấn trong mô hình đồ thị

## 1. Bài toán thiết kế: cùng một dữ liệu có thể được biểu diễn theo nhiều cách

Trong cơ sở dữ liệu đồ thị (**graph database**), chúng ta thường biểu diễn thực thể bằng **nút (node)**, liên kết giữa các thực thể bằng **cạnh/quan hệ (relationship)**, và thông tin mô tả bằng **thuộc tính (property)**. Tuy nhiên, khi chuyển dữ liệu nghiệp vụ sang đồ thị, nhiều khái niệm có thể được lưu theo hai cách:

- Một khách hàng có thuộc tính `city: "Hà Nội"`, hoặc được nối tới nút `City` biểu diễn Hà Nội.
- Một học viên có mảng thuộc tính `skills: ["JAVA", "SQL"]`, hoặc được nối tới hai nút `Skill`.
- Một khóa học có thuộc tính `level: "BEGINNER"`, hoặc được nối tới nút `Level`.
- Một sản phẩm có thuộc tính `categoryCode: "BOOK"`, hoặc được nối tới nút `Category`.

Cả hai cách có thể lưu giữ thông tin. **Cách nào hợp lý phụ thuộc vào câu hỏi mà ứng dụng thực sự cần trả lời**: chỉ đọc/lọc một giá trị, hay đi từ giá trị đó tới các thực thể khác, quản lý danh tính riêng và duyệt nhiều bước quan hệ?

Ví dụ, nếu màn hình chỉ hiển thị thành phố của học viên thì `cityCode` là một thuộc tính dễ sử dụng. Nếu ứng dụng phải đi từ học viên đến thành phố, từ thành phố đến vùng địa lý, rồi tìm những khóa học tổ chức trong vùng đó, một nút `City` cùng các cạnh liên quan có thể phản ánh yêu cầu truy vấn tốt hơn.

Bài này dùng **labeled property graph** và cú pháp **Cypher của Neo4j** để minh họa. Nguyên tắc thiết kế có thể vận dụng cho hệ đồ thị khác, nhưng cú pháp, kiểu property, chỉ mục và ràng buộc cụ thể phải theo hệ quản trị được sử dụng.

## 2. Phân biệt nút, thuộc tính và quan hệ

Trong một *property graph*:

- **Nút (node)** đại diện cho một đối tượng hoặc khái niệm có thể có danh tính riêng, ví dụ `Student`, `Course`, `Skill`.
- **Thuộc tính (property)** là giá trị mô tả nút hoặc quan hệ, ví dụ `name`, `createdAt`, `level`, `progressPercent`.
- **Quan hệ (relationship)** nối hai nút, có loại và hướng, ví dụ `ENROLLED_IN`, `HAS_SKILL`, `REQUIRES_SKILL`.

Một ví dụ tổng quát:

```text
(Student S01)
    | name = "Lan"
    | cityCode = "HN"
    |
    +----[:HAS_SKILL {since: 2026-01-01}]----> (Skill JAVA)
    |
    +----[:ENROLLED_IN {progressPercent: 70}]----> (Course C01)
                                                   | title = "Java cơ bản"
                                                   | level = "BEGINNER"
                                                   |
                                                   +--[:REQUIRES_SKILL]--> (Skill JAVA)
```

Trong sơ đồ, `name` và `level` là thuộc tính; `Student`, `Course`, `Skill` là nhãn của nút; còn `HAS_SKILL` và `ENROLLED_IN` là các quan hệ. Nếu một thực thể `Skill` được nhiều sinh viên và khóa học cùng tham chiếu, việc có nút `Skill` giúp chúng ta đi từ một phía của quan hệ sang phía khác.

Một **nút** không được nhận diện chỉ bằng nhãn; nhiều nút đều có thể mang nhãn `Student`. Khi cần định danh ổn định, dùng thuộc tính ID nghiệp vụ như `studentId` hoặc `skillCode` và khai báo ràng buộc duy nhất phù hợp.

## 3. Bắt đầu từ câu hỏi truy vấn, không bắt đầu từ hình vẽ đồ thị

Giả sử nền tảng học tập lưu học viên, khóa học và kỹ năng. Nhóm sản phẩm đưa ra sáu yêu cầu:

| Yêu cầu truy vấn | Điểm xuất phát | Dữ liệu hoặc quan hệ cần truy cập |
|---|---|---|
| Hiển thị hồ sơ một học viên | `studentId` | Tên, ngày tham gia, thành phố |
| Liệt kê học viên tại Hà Nội | Mã thành phố | Lọc các học viên có cùng mã |
| Tìm học viên có kỹ năng Java | Kỹ năng Java | Các học viên sở hữu kỹ năng đó |
| Tìm học viên cùng kỹ năng với S01 | Học viên S01 | Đi qua kỹ năng để tới học viên khác |
| Tìm khóa học yêu cầu kỹ năng Java | Kỹ năng Java | Các khóa học liên kết với kỹ năng |
| Theo dõi từng lần đăng ký học, chứng nhận | Lần đăng ký | Trạng thái, tiến độ, khóa học, chứng nhận, lịch sử |

Ba truy vấn đầu có thể đáp ứng bằng thuộc tính trong một số trường hợp. Nhưng các truy vấn **đi qua kỹ năng**, tìm kết nối giữa học viên và khóa học, hoặc quản lý từng lần đăng ký khiến nhu cầu về nút và quan hệ trở nên rõ hơn.

Khi thiết kế, hãy viết cho mỗi access pattern:

1. **Biết trước điều gì?** Một ID, tên kỹ năng, mã thành phố hay mã khóa học?
2. **Trả về điều gì?** Một giá trị, nhiều thực thể, tập láng giềng hay đường đi nhiều bước?
3. **Lọc/sắp xếp ra sao?** Lọc trên một property hay kiểm tra các liên kết?
4. **Tần suất và quy mô thế nào?** Vài lần mỗi ngày hay hàng nghìn request/giây?
5. **Dữ liệu thay đổi thế nào?** Thay tên, đổi nhãn, thêm quan hệ, cần giữ lịch sử?
6. **Có cần định danh/kiểm soát riêng không?** Phần tử đó có chủ sở hữu, trạng thái, quyền, hay vòng đời riêng?

Mô hình có thể được điều chỉnh khi access pattern thay đổi, nhưng các truy vấn quan trọng phải là đầu vào của quyết định ban đầu.

## 4. Trường hợp nên giữ là thuộc tính

Một giá trị thường phù hợp làm **property** khi nó chủ yếu để hiển thị, lọc, sắp xếp hoặc tính toán và **không cần một danh tính hay các mối quan hệ độc lập**.

Ví dụ:

```cypher
CREATE (s:Student {
  studentId: 'S01',
  name: 'Lan',
  cityCode: 'HN',
  joinedAt: date('2026-01-10'),
  active: true
});
```

### 4.1. Thuộc tính phục vụ màn hình chi tiết

```cypher
MATCH (s:Student {studentId: 'S01'})
RETURN s.studentId, s.name, s.cityCode, s.joinedAt;
```

Nếu mục đích chỉ lấy tên, ngày tham gia và mã thành phố khi mở hồ sơ, **không cần tạo nút riêng cho tên hoặc ngày**. Nút `Student` đã chứa đủ dữ liệu để trả lời.

### 4.2. Thuộc tính phục vụ lọc và sắp xếp

```cypher
MATCH (s:Student {cityCode: 'HN'})
WHERE s.active = true
RETURN s.studentId, s.name
ORDER BY s.name
LIMIT 20;
```

Nếu ứng dụng thường lọc theo mã thành phố, có thể tạo index trên property:

```cypher
CREATE INDEX student_city_code IF NOT EXISTS
FOR (s:Student) ON (s.cityCode);
```

Với truy vấn như trên, một property có thể đáp ứng yêu cầu mà không tạo thêm nút và quan hệ. **Không có quy tắc rằng giá trị được nhiều nút cùng sử dụng thì bắt buộc phải tách thành nút.** Các giá trị enum như `PENDING`, `ACTIVE`, `BEGINNER` thường vẫn đơn giản hơn khi được lưu trực tiếp.

### 4.3. Thuộc tính cho phép tính toán hoặc so sánh khoảng

Ví dụ `priceVnd`, `progressPercent`, `joinedAt`, `createdAt` thường được dùng trong phép so sánh, lọc khoảng thời gian hoặc tính tổng. Đây là những ứng viên tự nhiên cho property:

```cypher
MATCH (s:Student)
WHERE s.joinedAt >= date('2026-01-01')
  AND s.joinedAt < date('2027-01-01')
RETURN s.studentId, s.joinedAt
ORDER BY s.joinedAt;
```

Biến mỗi ngày thành một nút `Date` rồi nối tất cả học viên vào đó có thể tạo thêm cạnh và bước duyệt không cần thiết nếu ứng dụng chỉ lọc khoảng ngày. Mô hình hóa thời gian thành nút chỉ hợp lý khi cần các quan hệ hoặc phép suy luận thời gian vượt ra ngoài những phép lọc đơn giản.

### 4.4. Mảng các giá trị đơn giản

Nếu chỉ hiển thị vài nhãn của học viên, có thể lưu:

```cypher
CREATE (:Student {
  studentId: 'S02',
  name: 'Minh',
  interests: ['programming', 'music']
});
```

Trong Neo4j, property có thể lưu **mảng giá trị đơn giản thuộc kiểu được hỗ trợ**. Không nên mặc định có thể lưu một danh sách object lồng nhau tùy ý như một document JSON. Khi từng phần tử cần ID, quan hệ hay các trường động phức tạp, hãy cân nhắc cấu trúc nút và cạnh.

## 5. Trường hợp nên tách thành nút

Một giá trị trở thành ứng viên **node** khi ứng dụng cần quản lý nó như một thực thể có danh tính riêng hoặc dùng nó làm điểm trung gian để duyệt quan hệ.

### 5.1. Nhiều thực thể cùng tham chiếu tới một khái niệm

Ví dụ nhiều học viên có kỹ năng Java; nhiều khóa học cũng yêu cầu kỹ năng Java. Ta có thể tạo **một nút Skill JAVA** và nối tới các phía liên quan:

```text
(Student S01) --HAS_SKILL--> (Skill JAVA) <--REQUIRES_SKILL-- (Course C01)
(Student S02) --HAS_SKILL-->      |
(Student S03) --HAS_SKILL-->      +--<-REQUIRES_SKILL-- (Course C02)
```

Đây là mô hình hợp lý khi `Skill` là một khái niệm được chuẩn hóa và chia sẻ, có `skillCode` ổn định. Từ nút `Skill` có thể tìm những học viên, khóa học hoặc chứng nhận có liên quan bằng đường đi trong graph.

### 5.2. Cần duyệt từ thực thể này sang thực thể khác

Truy vấn “tìm học viên có cùng kỹ năng với Lan” có thể đi qua:

```text
(Student Lan) --> (Skill JAVA) <-- (Student Minh)
             \-> (Skill SQL)  <-- (Student Bình)
```

Đây là access pattern **Student → Skill → Student**. Nếu mọi kỹ năng chỉ nằm trong mảng chuỗi của từng học viên, hệ thống cần so sánh danh sách kỹ năng giữa nhiều học viên; biểu diễn bằng nút Skill tạo đường liên kết trực tiếp để duyệt.

### 5.3. Khái niệm có thuộc tính và vòng đời riêng

Một kỹ năng có thể có:

```text
(:Skill {
  code: 'JAVA',
  displayName: 'Java',
  category: 'PROGRAMMING',
  active: true
})
```

Nếu nền tảng cần đổi tên hiển thị từ “Java Programming” sang “Java”, quản lý các phiên bản hoặc liên kết kỹ năng với tài liệu học, việc quản lý một nút duy nhất thường rõ hơn việc cập nhật chuỗi `"Java Programming"` lặp lại trong rất nhiều mảng.

Tuy nhiên, tên hiển thị **không nên làm khóa định danh** nếu tên có thể đổi. Có thể dùng mã `JAVA` hoặc ID riêng để mọi liên kết giữ nguyên qua những lần đổi tên.

### 5.4. Cần quan hệ giữa chính những giá trị

Ví dụ:

```text
(Skill SPRING_BOOT) -[:BUILDS_ON]-> (Skill JAVA)
(Skill JAVA)        -[:RELATED_TO]-> (Skill OOP)
```

Nếu ứng dụng cần tìm **các kỹ năng tiên quyết**, chuỗi phụ thuộc hoặc gợi ý lộ trình học, những giá trị đó rõ ràng có quan hệ đáng truy vấn. Chuyển `Skill` thành nút cho phép lưu `BUILDS_ON` và duyệt nhiều bước.

Tương tự, `City` hoặc `Region` thường đáng là node nếu cần quan hệ địa lý như `BELONGS_TO`, `NEAR`, `CONNECTED_TO`, thay vì chỉ hiển thị tên thành phố.

### 5.5. Cần quyền, trạng thái hoặc lịch sử độc lập

Giả sử một `Certification` có ID, ngày cấp, người cấp, điều kiện thu hồi và liên kết tới học viên cùng kỹ năng. Đây là thực thể có danh tính và vòng đời riêng:

```text
(Student S01)-[:HOLDS]->(Certification CERT-77)-[:VALIDATES]->(Skill JAVA)
```

Tạo một node `Certification` giúp truy xuất, thu hồi và theo dõi từng chứng nhận chính xác hơn so với việc lưu chuỗi `"Java certified"` trong mảng của học viên.

## 6. Khi nào nên dùng cạnh có thuộc tính thay vì nút mới?

Khi đã tách một khái niệm thành node, cần xác định **dữ liệu nào thuộc về bản thân thực thể** và **dữ liệu nào thuộc về quan hệ**.

Ví dụ:

```text
(Student S01)
   |
   +--[:ENROLLED_IN {
          enrolledAt: 2026-02-01,
          progressPercent: 70
      }]-----------------------> (Course C01)
```

`progressPercent` là tiến độ **của học viên S01 trong khóa C01**. Nó không phải thuộc tính chung của Student vì mỗi học viên có thể học nhiều khóa; cũng không phải thuộc tính chung của Course vì từng học viên có tiến độ khác nhau.

Trong Neo4j, có thể đặt property trên cạnh:

```cypher
MATCH (s:Student {studentId: 'S01'})
MATCH (c:Course {courseId: 'C01'})
MERGE (s)-[e:ENROLLED_IN]->(c)
ON CREATE SET
  e.enrolledAt = date('2026-02-01'),
  e.progressPercent = 70;
```

Nhưng nếu “lần đăng ký” có **ID riêng**, có thể bị hủy/đăng ký lại, có thanh toán, chứng chỉ, yêu cầu hoàn phí hay lịch sử sự kiện liên kết vào chính nó, thì chỉ đặt thuộc tính lên cạnh có thể làm mô hình khó quản lý.

Khi đó cân nhắc tạo node trung gian:

```text
(Student S01) --HAS_ENROLLMENT--> (Enrollment E100) --FOR_COURSE--> (Course C01)
                                          |
                                          +-- enrolledAt: 2026-02-01
                                          +-- progressPercent: 70
                                          +-- status: ACTIVE
                                          |
                                          +--HAS_CERTIFICATE--> (Certificate CERT-9)
```

| Nhu cầu | Cạnh `ENROLLED_IN` có thuộc tính | Nút `Enrollment` |
|---|---|---|
| Chỉ cần biết ai đang học khóa nào | Đơn giản, trực tiếp | Có thêm một bước duyệt |
| Lưu `enrolledAt` và tiến độ hiện tại | Phù hợp | Cũng phù hợp |
| Một học viên đăng ký cùng khóa nhiều lần | Cần ID/qui tắc phân biệt các cạnh | Mỗi lần đăng ký có `enrollmentId` |
| Thanh toán, chứng chỉ gắn riêng từng lần đăng ký | Khó liên kết vào chính quan hệ | Dễ nối với nút Enrollment |
| Cần cập nhật/hủy/kiểm toán từng lần riêng | Cần nhận diện quan hệ chính xác | Có định danh nghiệp vụ rõ |

**Quyết định “node hay property” đôi khi mở rộng thành “relationship property hay một node riêng”.** Cùng một thông tin có thể đổi cấu trúc khi nghiệp vụ bắt đầu quản lý nó như một thực thể độc lập.

## 7. Ví dụ 1: thành phố là thuộc tính hay nút?

### Phương án A — thuộc tính trên Student

```text
(Student S01 {cityCode: "HN"})
(Student S02 {cityCode: "HN"})
(Student S03 {cityCode: "DN"})
```

Truy vấn tìm học viên tại Hà Nội:

```cypher
MATCH (s:Student {cityCode: 'HN'})
RETURN s.studentId, s.name;
```

Ưu điểm: ít nút, ít cạnh, đọc và cập nhật `cityCode` trực tiếp. Nếu chỉ cần **lọc theo mã thành phố**, đây thường là cấu trúc đủ dùng. Có thể tạo index trên `Student.cityCode` khi số lượng học viên lớn và tần suất truy vấn phù hợp.

Hạn chế: thông tin mô tả thành phố (tên địa phương, mã vùng, quan hệ hành chính, vùng lân cận) không có một nơi chia sẻ tự nhiên. Nếu code thành phố bị thay đổi, ứng dụng cần quy tắc cập nhật và đồng bộ tương ứng.

### Phương án B — thành phố là node

```text
(Student S01) --LIVES_IN--> (City HN {name: "Hà Nội"})
(Student S02) --LIVES_IN-->     |
                              +--PART_OF--> (Region NORTH)
(Student S03) --LIVES_IN--> (City DN {name: "Đà Nẵng"})
```

Truy vấn tất cả học viên thuộc vùng `NORTH`:

```cypher
MATCH (s:Student)-[:LIVES_IN]->(:City)-[:PART_OF]->(r:Region {code: 'NORTH'})
RETURN s.studentId, s.name;
```

Ưu điểm: vùng, thành phố và học viên có các quan hệ riêng; có thể truy vấn theo vùng, theo thành phố và duy trì danh mục thành phố tập trung. Hạn chế: thêm node/edge, thêm bước duyệt, phải quản lý tính đúng đắn của các quan hệ và mã địa lý.

**Không phải cứ có hàng nghìn học viên cùng thành phố thì bắt buộc tạo node City.** Quyết định phụ thuộc vào việc ứng dụng cần câu hỏi về **thành phố như một thực thể có quan hệ** hay chỉ cần một giá trị dùng để lọc. Với phép lọc đơn giản, một index trên property có thể hoàn toàn đáp ứng.

## 8. Ví dụ 2: kỹ năng là mảng thuộc tính hay node Skill?

### Phương án A — danh sách chuỗi trên Student

```cypher
CREATE (:Student {
  studentId: 'S10',
  name: 'Lan',
  skills: ['JAVA', 'SQL']
});
```

Truy vấn tìm học viên có `JAVA`:

```cypher
MATCH (s:Student)
WHERE 'JAVA' IN s.skills
RETURN s.studentId, s.name;
```

Cách này dễ hiểu nếu chỉ cần lưu vài kỹ năng để hiển thị hoặc lọc đơn giản. Tuy nhiên, với số lượng lớn, cần xem **kế hoạch thực thi của hệ quản trị**: không nên mặc định kiểm tra phần tử trong list property luôn được index hiệu quả như một truy vấn bắt đầu từ nút `Skill`.

Việc lưu chuỗi trong từng mảng cũng đặt ra câu hỏi: `JAVA`, `Java` và `Java SE` có được coi là một kỹ năng không? Ai duy trì danh mục chuẩn hóa? Khi có quan hệ kỹ năng tiên quyết, mảng chuỗi trở nên bất tiện.

### Phương án B — kỹ năng là node có định danh

```text
(Student S10) --HAS_SKILL--> (Skill JAVA)
                                |
                                +--BUILDS_ON--> (Skill OOP)
(Student S11) --HAS_SKILL--/

(Course C10) --REQUIRES_SKILL--> (Skill JAVA)
```

Truy vấn học viên có Java:

```cypher
MATCH (k:Skill {code: 'JAVA'})<-[:HAS_SKILL]-(s:Student)
RETURN s.studentId, s.name;
```

Truy vấn khóa học yêu cầu Java:

```cypher
MATCH (k:Skill {code: 'JAVA'})<-[:REQUIRES_SKILL]-(c:Course)
RETURN c.courseId, c.title;
```

Truy vấn hai bước “ai có chung kỹ năng với S10?”:

```cypher
MATCH (source:Student {studentId: 'S10'})-[:HAS_SKILL]->(k:Skill)
      <-[:HAS_SKILL]-(other:Student)
WHERE other.studentId <> source.studentId
RETURN other.studentId AS studentId,
       count(DISTINCT k) AS sharedSkillCount
ORDER BY sharedSkillCount DESC, studentId;
```

Ở phương án node, `Skill` trở thành **điểm neo (traversal starting point)** và một thực thể được chia sẻ trong nhiều quan hệ. Đổi lại phải quản lý node Skill, cạnh, ràng buộc ID, dữ liệu trùng và các truy vấn duyệt.

### Chọn theo nhu cầu

| Yêu cầu | Mảng `skills` | Node `Skill` và cạnh |
|---|---|---|
| Hiển thị vài kỹ năng trong hồ sơ | Phù hợp | Cần duyệt để lấy danh sách |
| Lọc học viên có một mã kỹ năng | Có thể dùng, cần xem hiệu năng | Có thể bắt đầu từ node Skill |
| Dùng danh mục kỹ năng chung, đổi tên một nơi | Phải đồng bộ dữ liệu lặp | Quản lý tập trung |
| Tìm học viên có kỹ năng chung | Phải xử lý so sánh giá trị | Mẫu `Student → Skill → Student` rõ ràng |
| Gợi ý khóa học theo kỹ năng, tiên quyết | Khó biểu diễn quan hệ sâu | Quan hệ `REQUIRES_SKILL`, `BUILDS_ON` |
| Mỗi học viên có ít tag tĩnh, không truy vấn graph | Ít cấu trúc, đơn giản | Có thể là mô hình quá mức |

## 9. Ví dụ Neo4j tự chứa: chuyển từ thuộc tính sang node có chủ đích

Giả sử sản phẩm ban đầu lưu `skills` như một mảng nhưng sau đó cần câu hỏi “học viên và khóa học nào dùng cùng một kỹ năng?”. Ta có thể thiết kế graph mới trong một **database thử nghiệm**. Các truy vấn dùng cú pháp Cypher của Neo4j phiên bản hỗ trợ `CREATE CONSTRAINT ... IF NOT EXISTS`.

### 9.1. Ràng buộc định danh trước khi tạo dữ liệu

```cypher
CREATE CONSTRAINT student_id_unique IF NOT EXISTS
FOR (s:Student)
REQUIRE s.studentId IS UNIQUE;

CREATE CONSTRAINT skill_code_unique IF NOT EXISTS
FOR (k:Skill)
REQUIRE k.code IS UNIQUE;

CREATE CONSTRAINT course_id_unique IF NOT EXISTS
FOR (c:Course)
REQUIRE c.courseId IS UNIQUE;
```

Ràng buộc unique đảm bảo không có hai node cùng nhãn với **cùng giá trị khóa** được chỉ định. Nó không tự đảm bảo mọi node đều bắt buộc có thuộc tính đó; nếu cần ràng buộc tồn tại hoặc node key, phải chọn tính năng tương ứng mà phiên bản/edition hỗ trợ hoặc kiểm tra ở tầng nghiệp vụ.

### 9.2. Tạo các nút độc lập theo ID ổn định

```cypher
MERGE (s1:Student {studentId: 'S01'})
ON CREATE SET s1.name = 'Lan', s1.cityCode = 'HN';

MERGE (s2:Student {studentId: 'S02'})
ON CREATE SET s2.name = 'Minh', s2.cityCode = 'DN';

MERGE (s3:Student {studentId: 'S03'})
ON CREATE SET s3.name = 'Bình', s3.cityCode = 'HN';

MERGE (java:Skill {code: 'JAVA'})
ON CREATE SET java.displayName = 'Java';

MERGE (sql:Skill {code: 'SQL'})
ON CREATE SET sql.displayName = 'SQL';

MERGE (c:Course {courseId: 'C01'})
ON CREATE SET c.title = 'Java Web';
```

`MERGE` tìm mẫu đã có hoặc tạo mới theo khóa chỉ định. `ON CREATE SET` chỉ gán thuộc tính trong lần tạo; việc cập nhật tên sau này phải có quy tắc riêng. Nên dùng ID ổn định để `MERGE`, không đưa `name` hoặc `displayName` vốn có thể thay đổi vào mẫu nhận diện.

### 9.3. Nối học viên với kỹ năng và khóa học với kỹ năng

```cypher
MATCH (s:Student {studentId: 'S01'}), (k:Skill {code: 'JAVA'})
MERGE (s)-[:HAS_SKILL]->(k);

MATCH (s:Student {studentId: 'S01'}), (k:Skill {code: 'SQL'})
MERGE (s)-[:HAS_SKILL]->(k);

MATCH (s:Student {studentId: 'S02'}), (k:Skill {code: 'JAVA'})
MERGE (s)-[:HAS_SKILL]->(k);

MATCH (s:Student {studentId: 'S03'}), (k:Skill {code: 'SQL'})
MERGE (s)-[:HAS_SKILL]->(k);

MATCH (c:Course {courseId: 'C01'}), (k:Skill {code: 'JAVA'})
MERGE (c)-[:REQUIRES_SKILL]->(k);
```

Trong ví dụ này, mỗi cặp Student–Skill chỉ có **một quan hệ logic `HAS_SKILL`**. Nếu nghiệp vụ cần quản lý nhiều lần đánh giá kỹ năng, cấp độ tại từng lần thi và kết quả chứng nhận có ID riêng, nên bổ sung mô hình sự kiện/đánh giá độc lập. `MERGE` trên mẫu quan hệ không thay thế mọi biện pháp ngăn trùng ở kịch bản ghi đồng thời.

### 9.4. Các truy vấn cho thấy lợi ích của node

Liệt kê những học viên có Java:

```cypher
MATCH (k:Skill {code: 'JAVA'})<-[:HAS_SKILL]-(s:Student)
RETURN s.studentId, s.name
ORDER BY s.studentId;
```

Với dữ liệu mẫu, kết quả gồm `S01` và `S02`. Liệt kê những kỹ năng mà khóa `C01` yêu cầu:

```cypher
MATCH (c:Course {courseId: 'C01'})-[:REQUIRES_SKILL]->(k:Skill)
RETURN c.courseId, k.code, k.displayName
ORDER BY k.code;
```

Với dữ liệu mẫu, kết quả có `JAVA`. Tìm học viên có chung kỹ năng với `S01`:

```cypher
MATCH (source:Student {studentId: 'S01'})-[:HAS_SKILL]->(k:Skill)
      <-[:HAS_SKILL]-(other:Student)
WHERE other.studentId <> source.studentId
RETURN other.studentId AS studentId,
       collect(DISTINCT k.code) AS sharedSkills
ORDER BY studentId;
```

Kết quả dự kiến là `S02` chung `JAVA`, `S03` chung `SQL`. Vì `Skill` có định danh riêng, nền tảng có thể bổ sung các quan hệ phân cấp hoặc tiên quyết về sau mà không phải tạo nhiều bản sao của danh mục kỹ năng.

## 10. Định danh là điều kiện để một giá trị thực sự trở thành thực thể

Nếu tách kỹ năng thành node nhưng dùng tên làm khóa:

```text
(:Skill {name: "Java"})
(:Skill {name: "JAVA"})
(:Skill {name: "Java programming"})
```

ba node có thể vô tình biểu diễn cùng một khái niệm. Nếu các học viên và khóa học nối đến những node khác nhau, kết quả duyệt quan hệ bị phân mảnh.

Vì vậy cần:

- Chọn khóa ổn định như `code: "JAVA"` hoặc `skillId`.
- Định nghĩa phạm vi duy nhất: toàn hệ thống hay theo tenant.
- Khai báo unique constraint khi hệ hỗ trợ.
- Chuẩn hóa ánh xạ từ dữ liệu đầu vào (tên gọi, bí danh) sang mã kỹ năng.
- Tách tên hiển thị khỏi ID, để đổi tên không phá liên kết.

Một nút có ID không tự giải quyết mọi vấn đề quản trị dữ liệu: nếu nhiều tên đồng nghĩa, cần danh mục chuẩn hóa và chính sách hợp nhất; nếu mã không còn dùng, cần quy tắc vô hiệu hóa thay vì xóa tùy ý.

Tương tự, khi `City` thành node, mã thành phố nên đủ ổn định và có phạm vi rõ ràng. Không nên dùng mỗi tên `"Springfield"` hoặc `"Hà Nội"` làm định danh duy nhất toàn thế giới.

## 11. Cân nhắc số lượng phần tử và chi phí duyệt

Tách một property thành node làm thay đổi **đường truy cập dữ liệu** và chi phí lưu trữ:

| Khía cạnh | Dùng property | Dùng node và relationship |
|---|---|---|
| Số phần tử cần lưu | Giá trị nằm trên nút hiện có | Thêm nút và cạnh |
| Đọc chi tiết một Student | Có thể đọc luôn giá trị trong một nút | Có thể phải duyệt quan hệ để lấy danh sách |
| Lọc theo giá trị | Query theo property, dùng index khi phù hợp | Có thể tìm node giá trị rồi duyệt cạnh |
| Duyệt sang thực thể khác cùng giá trị | Cần so khớp các giá trị qua truy vấn | Có đường `Student → Value → Student` |
| Danh mục và metadata dùng chung | Dễ lặp dữ liệu mô tả | Có thể quản lý tập trung trên node |
| Ghi/cập nhật | Sửa property của node | Có thể thêm/xóa cạnh, đổi node, xử lý tính duy nhất |
| Quan hệ phân cấp/tiên quyết giữa các giá trị | Khó biểu diễn trực tiếp | Có thể bổ sung cạnh giữa các node |

### 11.1. Nút có bậc rất lớn

Một node `Skill {code: 'JAVA'}` có thể có hàng triệu cạnh `HAS_SKILL`. Đó là một **node bậc cao (high-degree node)**. Việc có node dùng chung không tự động khiến mọi truy vấn nhanh: nếu bắt đầu từ Skill JAVA rồi mở toàn bộ cạnh để trả hàng triệu học viên, truy vấn vẫn rất nặng.

Khi đó cần:

- Giới hạn kết quả và phân trang phù hợp.
- Kết hợp thêm điều kiện trên học viên hoặc quan hệ.
- Tránh phép duyệt nhiều bước không giới hạn.
- Đo số lượng relationship được mở rộng và độ trễ thực tế.
- Cân nhắc các cấu trúc truy cập bổ sung nếu khối lượng và access pattern đòi hỏi.

Ngược lại, nếu chỉ cần tìm một Student qua `studentId` rồi xem vài property, việc chuyển từng giá trị thành node có thể tăng chi phí mà không đem lại lợi ích nghiệp vụ tương xứng.

### 11.2. Index vẫn quan trọng

Trong Neo4j, truy vấn thường có hai pha khái niệm:

```text
Tìm điểm bắt đầu                 Duyệt theo quan hệ
(:Skill {code: "JAVA"})  ----->  <-[:HAS_SKILL]-(:Student)
        ^
        |
  index/constraint
```

Ví dụ constraint unique trên `Skill.code` hỗ trợ nhận diện nhanh node kỹ năng khi dữ liệu đủ lớn. Tuy nhiên, index chỉ hỗ trợ **tìm node bắt đầu**; nó không bảo đảm việc duyệt hàng triệu quan hệ tiếp theo trở nên rẻ.

Với cách lưu property, chỉ mục `Student.cityCode` có thể giúp lọc học viên theo thành phố. **Đừng so sánh “node nhanh hơn property” khi chưa xác định truy vấn và số lượng quan hệ/dữ liệu được đọc.**

### 11.3. Truy vấn cần nhiều bước

Mô hình graph phát huy tác dụng khi câu hỏi phải đi qua các quan hệ:

```text
Student --HAS_SKILL--> Skill <--REQUIRES_SKILL-- Course
Course --TAUGHT_BY--> Instructor
Instructor --MEMBER_OF--> Team
```

Nhưng với mỗi hop, tập kết quả có thể tăng. Phải tính đến **fan-out**, độ sâu và các điều kiện lọc. Một thiết kế node chính xác về mặt ngữ nghĩa vẫn có thể cần tối ưu khi tăng quy mô.

## 12. Sự thay đổi của dữ liệu theo thời gian

Một tiêu chí quan trọng nhưng dễ bỏ quên là **lịch sử và vòng đời**.

### 12.1. Giá trị hiện tại đơn giản: property

Nếu chỉ quan tâm tình trạng hiện tại của học viên:

```text
(:Student {studentId: "S01", status: "ACTIVE"})
```

Khi trạng thái thay đổi sang `SUSPENDED`, ứng dụng cập nhật property. Không cần tạo nút `ActiveStatus`, `SuspendedStatus` nếu không có quan hệ hay quy tắc nghiệp vụ phức tạp cần duyệt.

### 12.2. Lịch sử quan hệ: property trên cạnh

Nếu một học viên từng có kỹ năng ở các cấp độ khác nhau theo thời gian, có thể đặt `since` hoặc `level` trên quan hệ hiện tại:

```text
(Student S01)-[:HAS_SKILL {since: 2026-01-10, level: 3}]->(Skill JAVA)
```

Cách này mô tả **trạng thái hiện tại của quan hệ**. Nếu mỗi lần đánh giá cần lưu lịch sử độc lập, ghi đè `level` sẽ mất thông tin lần trước.

### 12.3. Lịch sử là thực thể: tạo nút sự kiện

Một mô hình rõ hơn khi cần truy vết:

```text
(Student S01)-[:TOOK]->(Assessment A101)-[:FOR_SKILL]->(Skill JAVA)
                              | takenAt: 2026-01-10
                              | score: 75

(Student S01)-[:TOOK]->(Assessment A205)-[:FOR_SKILL]->(Skill JAVA)
                              | takenAt: 2026-04-15
                              | score: 92
```

Hai lần đánh giá có `assessmentId` riêng, có thể gắn tài liệu, giảng viên chấm, chứng chỉ hoặc khiếu nại. Khi “một giá trị” trở thành **sự kiện có thể truy xuất và liên kết độc lập**, node sẽ có ý nghĩa hơn.

## 13. Tránh hai cực đoan: đồ thị quá phẳng và đồ thị quá rời rạc

### 13.1. Mọi quan hệ đều là chuỗi property

```text
Student {
  studentId: "S01",
  skillCodes: ["JAVA", "SQL"],
  courseIds: ["C01", "C02"],
  instructorIds: ["I01"]
}
```

Nếu nhu cầu chỉ là trình bày hồ sơ, cấu trúc có thể đáp ứng. Nhưng với truy vấn “tìm giáo viên của khóa học yêu cầu kỹ năng học viên đã có”, ứng dụng phải tự kết hợp nhiều tập ID. Dữ liệu đã chứa các liên hệ nhưng chưa biểu diễn chúng thành cạnh để đồ thị hỗ trợ duyệt trực tiếp.

### 13.2. Mọi giá trị đều trở thành node

```text
(Student S01)-[:HAS_NAME]->(Name "Lan")
             -[:HAS_STATUS]->(Status "ACTIVE")
             -[:JOINED_ON]->(Date "2026-01-10")
             -[:LIVES_IN]->(City "Hà Nội")
```

Nếu ứng dụng chỉ hiển thị tên, trạng thái và ngày tham gia, ba node đầu không có ích rõ ràng nhưng thêm cạnh, constraint, thao tác ghi và bước duyệt. Cách mô hình này dễ khiến truy vấn đơn giản bị phức tạp hóa.

**Thiết kế tốt thường kết hợp cả hai:** những giá trị mô tả đơn giản là property; những đối tượng chia sẻ, có danh tính hoặc có quan hệ riêng là node; dữ liệu mô tả tương tác nằm trên relationship hoặc một node sự kiện khi cần.

## 14. Ma trận quyết định cho các tình huống thực tế

| Thông tin | Ưu tiên ban đầu | Khi nào chuyển thành node? |
|---|---|---|
| Tên hiển thị, tuổi, ngày tạo | Property trên thực thể | Hiếm khi cần node riêng; chỉ khi nó thực sự là một thực thể miền độc lập |
| Trạng thái `ACTIVE`, `PENDING` | Property / enum | Khi trạng thái có quy tắc chuyển đổi, metadata hoặc quan hệ đặc biệt cần quản lý như một khái niệm riêng |
| Mã thành phố | Property `cityCode` | Khi cần quan hệ vùng, địa danh, kết nối, danh mục chung |
| Kỹ năng học viên | Mảng đơn giản nếu chỉ hiển thị | Khi cần chia sẻ danh mục, nối khóa học, duyệt kỹ năng chung/tiên quyết |
| Danh mục sản phẩm | Property nếu mã tĩnh và chỉ lọc | Khi danh mục có phân cấp, thuộc tính riêng, nhiều quan hệ |
| Ngôn ngữ của khóa học | Property `languageCode` | Khi ngôn ngữ là đối tượng quản trị và có liên kết riêng; không tự động cần node |
| Ngày đăng ký một khóa | Property trên quan hệ `ENROLLED_IN` | Khi từng lần đăng ký có ID, sự kiện, thanh toán hay chứng nhận riêng thì cân nhắc node `Enrollment` |
| Điểm đánh giá theo lần thi | Property nếu chỉ giữ kết quả hiện tại | Node `Assessment` nếu từng lần thi cần lịch sử, ID và quan hệ riêng |
| Quyền/vai trò truy cập | Property khi chỉ có một cờ đơn giản | Node `Role`/`Permission` khi cần kiểm tra quyền kế thừa, nhóm và quan hệ phức tạp |
| Lượt xem hoặc tổng số click | Property/counter nếu là chỉ số đơn giản | Node `ViewEvent`/`ClickEvent` chỉ khi cần truy vấn từng sự kiện, truy vết và quan hệ riêng |

Ma trận này là **định hướng**, không phải luật cứng. Nếu hệ thống chủ yếu xử lý thống kê khổng lồ theo thời gian, việc tạo một nút cho từng click có thể tăng số phần tử đồ thị quá lớn; có thể lưu sự kiện trong hệ chuyên xử lý log rồi chỉ đưa các quan hệ cần thiết vào graph.

## 15. Quy trình ra quyết định cho một thuộc tính cụ thể

Xét một thông tin `X` đang được lưu trên nút `A`. Có thể quyết định theo các bước:

1. **Liệt kê truy vấn hiện tại và dự kiến gần:** người dùng chỉ hiển thị/lọc X, hay tìm các đối tượng khác thông qua X?
2. **Kiểm tra tính độc lập:** X có cần ID riêng, mô tả riêng, cập nhật riêng, cấp quyền hoặc lịch sử độc lập không?
3. **Kiểm tra quan hệ:** X có kết nối với các nút loại khác không; các liên kết đó có được truy vấn thường xuyên không?
4. **Xem số lượng và số lần thay đổi:** X là một giá trị đơn hay nhiều phần tử; thuộc danh mục tĩnh hay phát sinh không giới hạn?
5. **Xác định mô hình:** nếu chỉ mô tả A và lọc theo giá trị, giữ X là property. Nếu X là thực thể chia sẻ/điểm duyệt, tạo node X và quan hệ A–X. Nếu X mô tả một tương tác A–B, cân nhắc property trên cạnh; nếu tương tác có danh tính, cân nhắc node trung gian.
6. **Đặt khóa và ràng buộc:** mỗi node mới cần cách tìm duy nhất, tránh tạo các bản sao cùng nghĩa bằng `CREATE` tùy tiện.
7. **Đánh giá truy vấn mới:** xác định điểm bắt đầu, index, số hop, fan-out và số kết quả.
8. **Quy định đường cập nhật:** khi thay tên, chuyển trạng thái hoặc xóa một quan hệ, những dữ liệu nào cần được đồng bộ?

Ví dụ quyết định cho `Student.cityCode`:

```text
Chỉ lọc theo mã thành phố?
  └─ Có -> property cityCode + index khi cần

Cần hỏi những vùng chứa thành phố hoặc thành phố lân cận?
  └─ Có -> City node + PART_OF / NEAR relationships

Cần lưu địa chỉ tại từng lần đăng ký học?
  └─ Có -> kiểm tra liệu địa chỉ thuộc Enrollment,
           Student hiện tại hay một snapshot lịch sử
```

Lưu ý rằng dữ liệu hiện tại và dữ liệu lịch sử có thể khác nhau: nếu một học viên chuyển nơi ở, thành phố hiện tại trên `Student` không thể tự thay thế địa chỉ tại thời điểm đăng ký một khóa trước đó.

## 16. Đo hiệu năng theo query, không suy ra từ số nút

Để xác định mô hình đang phục vụ tốt access pattern, có thể dùng `EXPLAIN` hoặc `PROFILE` trong Neo4j.

Ví dụ với city là property:

```cypher
PROFILE
MATCH (s:Student {cityCode: 'HN'})
RETURN s.studentId, s.name
LIMIT 20;
```

Ví dụ với Skill là node:

```cypher
PROFILE
MATCH (k:Skill {code: 'JAVA'})<-[:HAS_SKILL]-(s:Student)
RETURN s.studentId, s.name
LIMIT 20;
```

Khi phân tích kế hoạch, chú ý cách tìm node ban đầu, loại index được dùng, số row trung gian, số quan hệ được mở rộng, chi phí đọc dữ liệu và độ trễ thực tế. `LIMIT` giảm số kết quả yêu cầu nhưng không phải lúc nào cũng làm biến mất chi phí của mọi bước sắp xếp, tính toán hoặc mở rộng quan hệ trước đó.

Để đánh giá thiết kế cần dữ liệu gần thực tế về **số Student, số Skill, số quan hệ mỗi Skill và tần suất truy vấn**. Mô hình nhanh với 10 học viên chưa chứng minh sẽ nhanh khi một kỹ năng có hàng triệu học viên.

## 17. Bài tập thực hành

### Bài 1 — Thành phố là node hay property?

Ứng dụng A chỉ cần hiển thị thành phố và lọc danh sách nhân viên theo thành phố. Ứng dụng B cần tìm nhân viên thuộc các thành phố nằm trong cùng vùng, tìm các chi nhánh nối với thành phố và truy vấn tuyến di chuyển giữa các địa điểm.

Hãy đề xuất mô hình cho từng ứng dụng.

*Gợi ý:* A có thể dùng `Employee.cityCode` và index; B có lý do tạo `City`/`Region` làm node và lưu các cạnh địa lý. Không nên chọn node cho A chỉ vì tất cả nhân viên đều có thành phố.

### Bài 2 — Chọn vị trí đặt tiến độ học

Một học viên đăng ký ba khóa và có tiến độ 20%, 70%, 100% tương ứng. Có nên đặt `progressPercent` lên node `Student`, `Course`, hay cạnh `ENROLLED_IN`?

*Gợi ý:* đây là thuộc tính của **quan hệ giữa một học viên và một khóa cụ thể**, nên đặt trên `ENROLLED_IN` khi mỗi cặp chỉ có một đăng ký hiện tại; nếu có nhiều lần đăng ký và chứng chỉ liên kết, xem xét node `Enrollment`.

### Bài 3 — Viết truy vấn kỹ năng dùng chung

Cho đồ thị sau:

```text
S01 --HAS_SKILL--> JAVA <--HAS_SKILL-- S02
S01 --HAS_SKILL--> SQL  <--HAS_SKILL-- S03
C01 --REQUIRES_SKILL--> JAVA
```

Viết truy vấn trả về học viên cùng kỹ năng với `S01` và danh sách kỹ năng chung. Có thể tham khảo:

```cypher
MATCH (s:Student {studentId: 'S01'})-[:HAS_SKILL]->(k:Skill)
      <-[:HAS_SKILL]-(other:Student)
WHERE other.studentId <> s.studentId
RETURN other.studentId, collect(DISTINCT k.code) AS commonSkills
ORDER BY other.studentId;
```

### Bài 4 — Khi nào cần một node sự kiện?

Một học viên thi Java ba lần với điểm lần lượt 55, 70 và 90. Hệ thống cần cấp chứng nhận dựa vào lần thi đạt ngưỡng, lưu người chấm và cho phép khiếu nại riêng một lần thi.

Hãy so sánh cách lưu `currentScore` trên Student–Skill với việc tạo ba nút `Assessment` có ID độc lập. Cách nào giữ đầy đủ lịch sử và cho phép nối `Complaint` đến đúng lần thi?

### Bài 5 — Phát hiện thiết kế thừa

Một đồ thị có các nút `Name`, `Age`, `ActiveStatus` cho mỗi học viên, nhưng toàn bộ truy vấn chỉ đọc hồ sơ theo `studentId` và lọc người đang hoạt động. Không truy vấn nào duyệt từ Name/Age/Status sang phần tử khác.

Hãy viết lại mô hình đơn giản hơn, nêu những property cần giữ trên Student và một truy vấn lọc `active = true`.

## 18. Kết luận

Việc chọn **nút hay thuộc tính** trong NoSQL dạng đồ thị là quyết định về **đường truy cập và ý nghĩa nghiệp vụ**, không chỉ về cách trình bày dữ liệu. Thuộc tính phù hợp cho các giá trị mô tả, lọc, sắp xếp và tính toán trực tiếp trên một thực thể. Nút phù hợp khi một khái niệm có danh tính, được nhiều thực thể tham chiếu, có quan hệ riêng hoặc đóng vai trò trung gian trong những phép duyệt quan trọng. Thuộc tính của một lần tương tác thường nằm trên cạnh, còn tương tác có ID và vòng đời độc lập có thể được nâng thành node.

Một mô hình cân bằng không cố tạo node cho mọi giá trị, cũng không giữ mọi liên hệ trong những danh sách ID hay chuỗi property. Hãy **viết các câu hỏi ứng dụng cần trả lời, xác định điểm bắt đầu và đường duyệt, rồi kiểm chứng bằng truy vấn và dữ liệu thực tế**. Đó là cơ sở để quyết định đặt thông tin ở đâu trong đồ thị.

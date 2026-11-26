# Kiểu giá trị trong Cypher và kiểu có thể lưu làm thuộc tính

Trong Neo4j, dữ liệu được tổ chức theo **property graph**: node và relationship có thể mang các thuộc tính dạng cặp `key: value`. Cypher là ngôn ngữ dùng để tạo, đọc và biến đổi đồ thị đó. Khi viết Cypher, cần phân biệt hai phạm vi:

- **Giá trị dùng trong biểu thức và kết quả truy vấn**: có thể là số, chuỗi, ngày giờ, danh sách, map, node, relationship, path hoặc `null`.
- **Giá trị được lưu bền vững thành thuộc tính** của node/relationship: chỉ thuộc tập kiểu được Neo4j hỗ trợ cho property, không bao gồm mọi giá trị mà Cypher có thể tính ra.

Sự phân biệt này quan trọng khi mô hình hóa dữ liệu liên kết, thiết kế API, nhập dữ liệu và chuyển đổi kiểu từ ứng dụng Java sang Neo4j.

## 1. Bức tranh tổng quan về kiểu giá trị

| Nhóm | Kiểu/giá trị Cypher | Ví dụ | Lưu trực tiếp làm property? |
| --- | --- | --- | --- |
| Logic | `BOOLEAN` | `true`, `false` | Có |
| Số nguyên | `INTEGER` | `42`, `-7` | Có |
| Số thực | `FLOAT` | `3.14`, `1.0` | Có |
| Văn bản | `STRING` | `'Neo4j'`, `'Hà Nội'` | Có |
| Ngày | `DATE` | `date('2026-11-25')` | Có |
| Giờ có múi giờ/độ lệch | `ZONED TIME` | `time('09:30:00+07:00')` | Có |
| Giờ địa phương | `LOCAL TIME` | `localtime('09:30:00')` | Có |
| Ngày giờ có múi giờ/độ lệch | `ZONED DATETIME` | `datetime('2026-11-25T09:30:00+07:00')` | Có |
| Ngày giờ địa phương | `LOCAL DATETIME` | `localdatetime('2026-11-25T09:30:00')` | Có |
| Khoảng thời gian | `DURATION` | `duration('P2DT3H')` | Có |
| Tọa độ không gian | `POINT` | `point({latitude: 10.77, longitude: 106.70})` | Có |
| Danh sách | `LIST` | `['java', 'neo4j']` | Có, khi phần tử đáp ứng quy tắc property list |
| Bản đồ key–value | `MAP` | `{city: 'Đà Nẵng', level: 2}` | Không lưu nguyên map vào một property |
| Thực thể đồ thị | `NODE`, `RELATIONSHIP`, `PATH` | `p`, `r`, `path` trong `MATCH` | Không |
| Không có giá trị | `null` | `null` hoặc truy cập thuộc tính vắng mặt | Không: gán `null` là xóa thuộc tính |

> **Quy tắc nền tảng:** một giá trị *có thể xuất hiện trong truy vấn Cypher* chưa chắc *có thể được lưu làm thuộc tính*. Node và relationship đều chịu cùng quy tắc về kiểu của giá trị property.

## 2. Các kiểu vô hướng: logic, số và chuỗi

### BOOLEAN

`BOOLEAN` chỉ có hai giá trị khác `null` là `true` và `false`. Nó thích hợp cho cờ trạng thái như `isActive`, `verified`, `isPublic`:

```cypher
CREATE (u:User {
  username: 'lan',
  isActive: true,
  verified: false
})
RETURN u.username, u.isActive, u.verified;
```

`false` là một giá trị được lưu thực sự. Nó khác với `null`, vốn biểu thị không có giá trị tại thời điểm đánh giá biểu thức.

### INTEGER và FLOAT

- `INTEGER` biểu diễn số nguyên có dấu 64 bit, dùng cho tuổi, số lượng, số thứ tự hoặc bộ đếm trong phạm vi cho phép.
- `FLOAT` biểu diễn số thực dấu phẩy động 64 bit theo chuẩn IEEE 754; phù hợp cho phép đo và dữ liệu có phần thập phân khi chấp nhận sai số biểu diễn.
- `42` và `42.0` là hai literal mang hai kiểu khác nhau; cần nhất quán kiểu dữ liệu khi nhập và cập nhật.

```cypher
RETURN
  42 AS soNguyen,
  42.0 AS soThuc,
  toInteger('42') AS epSangSoNguyen,
  toFloat('3.14') AS epSangSoThuc;
```

Không giả định `FLOAT` biểu diễn chính xác mọi số thập phân. Với tiền tệ cần độ chính xác tuyệt đối, thường lưu số nguyên theo đơn vị nhỏ nhất (ví dụ số đồng, số xu) hoặc dùng mô hình biểu diễn phù hợp với yêu cầu nghiệp vụ.

### STRING

`STRING` là chuỗi Unicode, dùng cho tên, mã nghiệp vụ, email, mô tả và nhãn hiển thị. Chuỗi rỗng `''` vẫn là một giá trị; nó không đồng nghĩa với `null` hoặc việc không tồn tại property.

```cypher
RETURN
  'Neo4j' AS sanPham,
  'Đồ thị tri thức' AS tieuDe,
  toString(2026) AS namDangChuoi;
```

Mã định danh có số 0 ở đầu, chẳng hạn `'00125'`, nên giữ ở dạng `STRING` nếu các số 0 đó có ý nghĩa. Không chuyển thành `INTEGER` chỉ vì các ký tự đều là chữ số.

## 3. Kiểu ngày, giờ và khoảng thời gian

Cypher phân biệt *ngày*, *giờ trong ngày*, *ngày giờ* và *độ dài khoảng thời gian*:

| Kiểu | Ý nghĩa | Trường hợp dùng |
| --- | --- | --- |
| `DATE` | Ngày lịch, không chứa giờ | Ngày sinh, ngày phát hành |
| `LOCAL TIME` | Giờ trong ngày, không gắn múi giờ/UTC offset | Giờ cửa hàng mở cửa theo lịch địa phương |
| `ZONED TIME` | Giờ trong ngày có thông tin độ lệch múi giờ | Giờ hẹn kèm offset |
| `LOCAL DATETIME` | Ngày và giờ không mang thông tin múi giờ | Lịch biểu địa phương khi zone do ứng dụng quản lý |
| `ZONED DATETIME` | Ngày và giờ có thông tin múi giờ/offset | Thời điểm phát sinh sự kiện |
| `DURATION` | Độ dài hoặc khoảng thời gian | Thời gian xử lý, thời hạn |

Ví dụ lưu các kiểu thời gian:

```cypher
CREATE (e:Event {
  eventId: 'EV-001',
  eventDate: date('2026-11-25'),
  localStart: localtime('09:00:00'),
  occurredAt: datetime('2026-11-25T09:00:00+07:00'),
  plannedLength: duration('PT1H30M')
})
RETURN
  e.eventDate,
  e.localStart,
  e.occurredAt,
  e.plannedLength;
```

**Lưu ý về ngữ nghĩa:**

- `date('2026-11-25')` không đại diện một thời điểm chính xác trong ngày.
- `localdatetime('2026-11-25T09:00:00')` không tự cho biết 09:00 thuộc múi giờ nào; không nên dùng nó làm thời điểm toàn cục nếu dữ liệu đi qua nhiều múi giờ.
- `datetime('2026-11-25T09:00:00+07:00')` mang thông tin offset, phù hợp hơn cho thời điểm ghi nhận giao dịch hoặc log.
- `duration('P1M')` mang ý nghĩa một tháng lịch; không được mặc định xem nó luôn bằng một số ngày hoặc giây cố định.

Định dạng ngày giờ tại giao diện có thể khác nhau, nhưng nên chuẩn hóa dữ liệu trước khi đưa vào Neo4j và dùng kiểu thời gian thực thay vì lưu mọi ngày giờ dưới dạng chuỗi.

## 4. Kiểu không gian POINT

`POINT` biểu diễn điểm trong một hệ tọa độ. Với tọa độ kinh độ/vĩ độ trên Trái Đất, dùng các trường `longitude` và `latitude`; với tọa độ phẳng, có thể dùng `x` và `y` theo hệ tọa độ tương ứng.

```cypher
CREATE (s:Store {
  storeId: 'S-001',
  name: 'Cửa hàng trung tâm',
  location: point({
    latitude: 10.7769,
    longitude: 106.7009
  })
})
RETURN s.name, s.location;
```

Từ property dạng `POINT` có thể tính khoảng cách không gian:

```cypher
WITH point({latitude: 10.7769, longitude: 106.7009}) AS center
MATCH (s:Store)
WHERE s.location IS NOT NULL
RETURN
  s.name,
  point.distance(s.location, center) AS distanceMeters
ORDER BY distanceMeters;
```

Ví dụ này giả định các giá trị `s.location` đều là `POINT` và có hệ tọa độ tương thích với `center`. Cần kiểm soát nhất quán cách lưu tọa độ khi tích hợp dữ liệu bản đồ.

## 5. Danh sách LIST: dùng trong truy vấn và dùng làm property

`LIST` là một dãy phần tử có thứ tự. Trong **biểu thức Cypher**, danh sách có thể chứa nhiều kiểu, `null`, map hoặc các danh sách lồng nhau. Nhưng khi lưu thành **một property**, Neo4j chỉ nhận các danh sách có phần tử thuộc những kiểu giá trị property được hỗ trợ và tương thích về kiểu; không lưu danh sách chứa `null`, map, node hoặc danh sách lồng nhau dưới dạng property.

```cypher
// Danh sách sử dụng trong biểu thức truy vấn:
RETURN
  [1, 'A', true] AS mixedValues,
  [1, null, 3] AS valuesWithNull,
  [{code: 'A'}, {code: 'B'}] AS mapsInQuery;
```

Các giá trị trên dùng được ở kết quả truy vấn nhưng **không nên gán nguyên dạng vào một property**.

Ví dụ property list hợp lệ:

```cypher
CREATE (p:Person {
  personId: 'P-001',
  name: 'Lan',
  skills: ['Cypher', 'Java', 'Spring'],
  scores: [8, 9, 10],
  activeDays: [date('2026-11-23'), date('2026-11-25')]
})
RETURN p.name, p.skills, p.scores, p.activeDays;
```

Một số nguyên tắc thực hành:

- `['Cypher', 'Java']` là danh sách chuỗi có thể lưu; `[8, 9, 10]` là danh sách số nguyên có thể lưu.
- `[]` có thể biểu thị danh sách rỗng, vẫn khác với property bị thiếu.
- `[1, 'A']`, `[1, null, 3]`, `[[1, 2], [3, 4]]` và `[{key: 'value'}]` không phù hợp để lưu trực tiếp làm property list.
- Một danh sách tag đơn giản có thể để trong property. Nếu mỗi tag có thuộc tính riêng, cần truy vấn sâu hoặc quan hệ với các node khác, hãy cân nhắc mô hình hóa thành node và relationship.

Có thể truy xuất và xử lý list bằng chỉ số, toán tử `IN` và `UNWIND`:

```cypher
MATCH (p:Person {personId: 'P-001'})
RETURN
  p.skills[0] AS firstSkill,
  'Cypher' IN p.skills AS knowsCypher,
  size(p.skills) AS skillCount;
```

```cypher
MATCH (p:Person {personId: 'P-001'})
UNWIND p.skills AS skill
RETURN p.name, skill
ORDER BY skill;
```

`UNWIND` biến phần tử của list thành các dòng kết quả để xử lý tiếp; nó không tự sinh node hay relationship.

## 6. MAP, NODE, RELATIONSHIP và PATH: giá trị của truy vấn, không phải property

### MAP

`MAP` là tập các cặp key–value có tên, hữu ích để đóng gói kết quả, truyền tham số hoặc xây dựng dữ liệu trước khi ghi.

```cypher
WITH {
  name: 'Minh',
  address: {city: 'Hà Nội', district: 'Cầu Giấy'},
  skills: ['Neo4j', 'Java']
} AS profile
RETURN profile.name AS name, profile.address.city AS city;
```

Trong ví dụ trên, `profile` là một map hợp lệ **trong truy vấn**. Tuy nhiên, thao tác kiểu sau không hợp lệ vì một property không chứa nguyên map:

```cypher
// Minh họa thao tác SAI: Neo4j không nhận MAP làm property.
CREATE (:Person {
  name: 'Minh',
  address: {city: 'Hà Nội'}
});
```

Có hai cách thiết kế thay thế, tùy nhu cầu:

1. **Làm phẳng dữ liệu** khi trường con ít và cố định: `addressCity: 'Hà Nội'`, `addressDistrict: 'Cầu Giấy'`.
2. **Tách thành node liên kết** khi địa chỉ có nhiều trường, có lịch sử, được dùng chung hoặc cần truy vấn như một thực thể:

```cypher
CREATE
  (p:Person {personId: 'P-002', name: 'Minh'}),
  (a:Address {city: 'Hà Nội', district: 'Cầu Giấy'})
CREATE (p)-[:HAS_ADDRESS]->(a)
RETURN p.name, a.city;
```

Một map chỉ chứa các giá trị property hợp lệ có thể dùng để **thiết lập từng property** bằng `SET +=`:

```cypher
MATCH (p:Person {personId: 'P-002'})
SET p += {active: true, yearJoined: 2024}
RETURN properties(p) AS storedProperties;
```

Lệnh này thêm/cập nhật `active` và `yearJoined` riêng rẽ; nó không lưu map dưới một key. Nếu map có giá trị lồng nhau không được phép, phải chuyển đổi trước khi ghi.

### NODE, RELATIONSHIP và PATH

Cypher có thể trả về đối tượng node, relationship và path để ứng dụng xử lý hoặc để thực hiện các phép duyệt đồ thị:

```cypher
MATCH path = (p:Person)-[r:HAS_ADDRESS]->(a:Address)
RETURN
  p AS personNode,
  r AS addressRelationship,
  a AS addressNode,
  path AS matchedPath,
  nodes(path) AS nodeList,
  relationships(path) AS relationshipList;
```

Ở đây, `p` là `NODE`; `r` là `RELATIONSHIP`; `path` là `PATH`. Các giá trị đó **không thể gán trực tiếp vào property** như `p.addressNode = a` hoặc `p.savedPath = path`. Để lưu liên kết giữa các thực thể, sử dụng relationship thực; để lưu thông tin mô tả, trích các giá trị nguyên thủy cần thiết.

Danh sách `nodes(path)` hay `collect(p)` là list chứa thực thể đồ thị; nó có thể được trả về trong kết quả nhưng không trở thành một property list hợp lệ.

## 7. NULL và property không tồn tại

`null` nghĩa là không có giá trị xác định trong biểu thức. Khi đọc property chưa tồn tại, Cypher thường trả về `null`. Neo4j không lưu một property với giá trị `null` như một ô dữ liệu riêng biệt: **gán `null` cho property tương đương xóa property đó**.

```cypher
CREATE (p:Person {
  personId: 'P-003',
  name: 'Hoa',
  nickname: 'H'
})
SET p.nickname = null
RETURN
  p.nickname AS nickname,
  p.nickname IS NULL AS isMissing;
```

Kết quả `nickname` là `null` và `isMissing` là `true`. Property `nickname` đã được xóa khỏi node.

Khi kiểm tra thiếu dữ liệu, dùng `IS NULL` hoặc `IS NOT NULL`, không dùng `= null`:

```cypher
MATCH (p:Person)
WHERE p.nickname IS NULL
RETURN p.personId, p.name;
```

Trong logic ba giá trị của Cypher, một phép so sánh có `null` có thể cho kết quả `null` (không phải `true` hay `false`). Ví dụ, `null = null` không khẳng định hai giá trị bằng nhau. Hàm `coalesce` giúp chọn giá trị đầu tiên khác `null`:

```cypher
MATCH (p:Person)
RETURN
  p.name,
  coalesce(p.nickname, '(chưa có biệt danh)') AS displayedNickname;
```

Phân biệt ba trường hợp sau trong mô hình nghiệp vụ:

| Trường hợp | Ý nghĩa |
| --- | --- |
| `isActive: false` | Đã biết rõ trạng thái là không hoạt động |
| `nickname: ''` | Property có tồn tại nhưng chứa chuỗi rỗng |
| Không có `nickname` | Chưa có giá trị; đọc sẽ nhận `null` |

Nếu hệ thống cần phân biệt “chưa cung cấp”, “không áp dụng” và “đã xóa”, hãy thiết kế thêm trạng thái nghiệp vụ phù hợp; một mình `null` không biểu đạt hết các ý nghĩa đó.

## 8. Ví dụ hoàn chỉnh: chọn kiểu khi mô hình hóa một đồ thị

Giả sử xây dựng đồ thị khóa học gồm `Learner`, `Course` và quan hệ `ENROLLED_IN`.

```cypher
CREATE
  (l:Learner {
    learnerId: 'L-001',
    fullName: 'Nguyễn An',
    age: 24,
    active: true,
    interests: ['graph', 'backend'],
    joinedAt: datetime('2026-11-01T08:30:00+07:00')
  }),
  (c:Course {
    courseId: 'C-NEO4J',
    title: 'Cypher căn bản',
    hours: 12.5,
    publishedOn: date('2026-10-20')
  })
CREATE (l)-[:ENROLLED_IN {
  enrolledOn: date('2026-11-10'),
  progressPercent: 45.0
}]->(c)
RETURN l, c;
```

Ở mô hình này:

- `learnerId` và `courseId` là `STRING` vì đóng vai trò mã nghiệp vụ, không dùng để tính toán số học.
- `age` là `INTEGER`, `active` là `BOOLEAN`.
- `interests` là property list chuỗi đồng nhất.
- `joinedAt` là `ZONED DATETIME` để giữ thông tin thời điểm kèm offset.
- `publishedOn` và `enrolledOn` là `DATE` vì nghiệp vụ chỉ cần ngày.
- `hours` và `progressPercent` là `FLOAT` do chứa phần thập phân.
- Quan hệ `ENROLLED_IN` có property riêng, đồng thời biểu diễn đúng ngữ nghĩa “người học đăng ký khóa học”.

Truy vấn đọc dữ liệu và xuất kết quả dạng map cho API:

```cypher
MATCH (l:Learner)-[enrollment:ENROLLED_IN]->(c:Course)
WHERE l.active = true
RETURN {
  learnerId: l.learnerId,
  learnerName: l.fullName,
  courseTitle: c.title,
  progressPercent: enrollment.progressPercent,
  enrolledOn: enrollment.enrolledOn
} AS enrollmentView;
```

`enrollmentView` là map kết quả truy vấn, **không phải một property đã được lưu trên đồ thị**. Các node và relationship vẫn được lưu theo mô hình đồ thị.

## 9. Chuyển đổi kiểu và kiểm soát dữ liệu nhập

Trong dữ liệu CSV, JSON hoặc tham số từ ứng dụng Java, một giá trị có thể được chuyển dưới dạng chuỗi dù nghiệp vụ yêu cầu kiểu số, ngày hoặc logic. Cần kiểm tra và chuyển sang kiểu đích trước khi ghi.

```cypher
WITH {
  ageText: '29',
  scoreText: '8.5',
  activeText: 'true',
  joinedDateText: '2026-11-01'
} AS raw
RETURN
  toInteger(raw.ageText) AS age,
  toFloat(raw.scoreText) AS score,
  toBoolean(raw.activeText) AS isActive,
  date(raw.joinedDateText) AS joinedDate;
```

Các nguyên tắc cần giữ:

1. **Xác định ý nghĩa trước khi ép kiểu**: mã đơn hàng `'00042'` nên là chuỗi; số lượng `42` mới là số nguyên.
2. **Không lưu ngày tháng dạng chuỗi nếu cần thao tác thời gian**: dùng `DATE` hoặc nhóm `DATETIME` thích hợp.
3. **Không kỳ vọng mọi chuyển đổi đều thành công**: đầu vào không hợp lệ có thể dẫn tới `null` hoặc lỗi tùy hàm và ngữ cảnh. Kiểm tra dữ liệu trước khi ghi và xử lý trường thiếu.
4. **Chuẩn hóa kiểu trên cùng một thuộc tính**: tránh có node lưu `age` dạng `INTEGER`, node khác lại lưu `age` dạng `STRING`; sự không nhất quán làm điều kiện lọc, tổng hợp và tích hợp API khó dự đoán.
5. **Dùng tham số Cypher cho dữ liệu từ ứng dụng**: tham số có thể truyền số, chuỗi, ngày giờ, danh sách hoặc map để cập nhật các property hợp lệ. Không nối trực tiếp dữ liệu đầu vào vào câu truy vấn.

Ví dụ câu truy vấn tham số hóa:

```cypher
CREATE (p:Person {
  personId: $personId,
  name: $name,
  age: $age,
  skills: $skills
})
RETURN p;
```

Phía Java Driver cần truyền `$age` như số nguyên và `$skills` như danh sách chuỗi nếu đó là kiểu nghiệp vụ đã định. Nếu thay `$skills` bằng list chứa các map, thao tác ghi property sẽ không hợp lệ. Neo4j cho phép linh hoạt về schema, nhưng ứng dụng vẫn cần hợp đồng dữ liệu nhất quán; với hệ thống phù hợp có thể bổ sung ràng buộc kiểu thuộc tính và các ràng buộc khác mà phiên bản/edition đang dùng hỗ trợ.

Có thể xem kiểu giá trị hiện tại bằng hàm `valueType()` trên các phiên bản Neo4j/Cypher có hỗ trợ hàm này:

```cypher
MATCH (p:Person)
RETURN
  p.personId,
  valueType(p.age) AS ageType,
  valueType(p.skills) AS skillsType;
```

Hàm này hữu ích khi điều tra dữ liệu nhập không đồng nhất; kiểm tra tài liệu của phiên bản Neo4j đang vận hành để đối chiếu tên kiểu và khả năng hỗ trợ.

## 10. Lỗi thường gặp và cách sửa

| Tình huống | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Gán `p.address = {city: 'Huế'}` | `MAP` không phải giá trị property hợp lệ | Làm phẳng thành `p.addressCity` hoặc tạo node `Address` |
| Gán `p.tags = ['graph', null]` | Property list không lưu phần tử `null` | Lọc phần tử thiếu trước khi ghi |
| Gán `p.items = [[1, 2], [3, 4]]` | Property list không hỗ trợ list lồng nhau | Đổi mô hình hoặc tách thành các thực thể |
| Gán `p.friend = otherNode` | `NODE` không lưu trong property | Tạo relationship giữa các node |
| `WHERE p.field = null` | So sánh với `null` không cho điều kiện đúng mong muốn | Dùng `p.field IS NULL` |
| Lưu `price = 0.1 + 0.2` rồi so sánh tuyệt đối | Số thực dấu phẩy động có sai số | Dùng số nguyên đơn vị nhỏ nhất khi cần độ chính xác |
| Lưu `createdAt: '25/11/2026'` | Chuỗi không tự có ngữ nghĩa ngày giờ | Chuyển và ghi kiểu `DATE`/`DATETIME` |
| Lưu mọi thuộc tính `age` ở nhiều kiểu | Không nhất quán do nhập dữ liệu | Chuẩn hóa, xác thực đầu vào; cân nhắc ràng buộc kiểu |

## 11. Tự kiểm tra

**Câu 1.** `RETURN {name: 'Lan', age: 29} AS profile` hợp lệ. Có thể gán nguyên giá trị `profile` cho `p.profile` không?

*Đáp án:* Không. `MAP` hợp lệ trong biểu thức/kết quả, nhưng không phải kiểu property; cần gán từng trường hoặc chuyển thành node/relationship phù hợp.

**Câu 2.** `['Cypher', 'Java']` và `['Cypher', null]` khác nhau thế nào khi dùng làm property?

*Đáp án:* Danh sách thứ nhất là list chuỗi có thể lưu; danh sách thứ hai chứa `null` nên không dùng trực tiếp làm property list.

**Câu 3.** Điều gì xảy ra khi chạy `SET p.nickname = null`?

*Đáp án:* Property `nickname` bị loại khỏi node; truy cập `p.nickname` sau đó trả về `null`.

**Câu 4.** Với `startAt` là thời điểm ghi nhận giao dịch từ nhiều múi giờ, nên ưu tiên `LOCAL DATETIME` hay `ZONED DATETIME`?

*Đáp án:* Ưu tiên `ZONED DATETIME` có offset/zone rõ ràng để tránh mất thông tin thời điểm.

**Câu 5.** Vì sao `MATCH (a)-[r]->(b) RETURN r` hợp lệ, còn `SET a.savedRelationship = r` không hợp lệ?

*Đáp án:* `r` là giá trị `RELATIONSHIP` dùng được trong truy vấn; muốn lưu liên kết giữa thực thể thì dùng relationship trong đồ thị, không lưu đối tượng relationship vào property.

---

**Ghi nhớ:** Cypher thao tác trên một hệ kiểu phong phú hơn tập kiểu lưu trữ property. Hãy chọn giá trị vô hướng hoặc danh sách property hợp lệ cho thuộc tính; dùng map, node, relationship và path để xây dựng kết quả và mô hình liên kết; xử lý `null` và chuẩn hóa kiểu đầu vào trước khi ghi dữ liệu.

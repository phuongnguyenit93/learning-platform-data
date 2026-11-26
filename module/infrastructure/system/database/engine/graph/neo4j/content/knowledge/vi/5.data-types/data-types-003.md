# Giá trị null, thuộc tính không tồn tại và logic ba giá trị trong Cypher

Trong mô hình **property graph** của Neo4j, node và relationship có thể mang các thuộc tính như `name`, `email`, `active` hoặc `registeredAt`. Khi đọc một thuộc tính chưa được lưu, Cypher thường trả về `null`. Giá trị này ảnh hưởng trực tiếp đến phép so sánh, điều kiện `WHERE`, phép toán logic, truy vấn quan hệ tùy chọn và cập nhật dữ liệu.

Bài học thuộc chương **Kiểu dữ liệu** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Nắm chắc ngữ nghĩa của `null` giúp bạn mô hình hóa dữ liệu liên kết nhất quán, tránh bỏ sót kết quả khi truy vấn bằng Cypher và xử lý trường thiếu thông tin chính xác trong ứng dụng Java Driver hoặc Spring Data Neo4j.

## 1. null biểu thị điều gì?

`null` biểu thị **không có giá trị xác định** ở thời điểm đánh giá một biểu thức. Nó không đồng nghĩa với số 0, chuỗi rỗng hay giá trị luận lý `false`.

| Biểu thức | Ý nghĩa | Có phải `null`? |
| --- | --- | --- |
| `0` | Giá trị số bằng không | Không |
| `''` | Chuỗi có độ dài bằng không | Không |
| `false` | Trạng thái luận lý sai | Không |
| `[]` | Danh sách rỗng trong biểu thức | Không |
| `null` | Chưa có/không xác định giá trị | Có |
| `n.nickname` khi node không có property `nickname` | Truy cập thuộc tính vắng mặt | Kết quả là `null` |

Ví dụ không cần tạo dữ liệu:

```cypher
RETURN
  0 IS NULL AS zeroIsNull,
  '' IS NULL AS emptyStringIsNull,
  false IS NULL AS falseIsNull,
  [] IS NULL AS emptyListIsNull,
  null IS NULL AS nullIsNull;
```

Kết quả lần lượt là `false`, `false`, `false`, `false` và `true`.

**Điểm cốt lõi:** Cypher dùng `null` như trạng thái thiếu giá trị trong biểu thức; Neo4j **không lưu một property có giá trị null** như một cặp key–value độc lập trên node hoặc relationship. Điều này làm cho khái niệm `null` và khái niệm *thuộc tính không tồn tại* gắn chặt với nhau khi thao tác với property.

## 2. Thuộc tính không tồn tại trên node và relationship

### 2.1. Tạo dữ liệu minh họa

Chạy đoạn sau một lần trong môi trường thực hành để có ba node với các trường khác nhau:

```cypher
CREATE
  (:LearnerNullDemo {
    learnerId: 'N-001',
    name: 'An',
    active: true,
    nickname: 'Annie'
  }),
  (:LearnerNullDemo {
    learnerId: 'N-002',
    name: 'Bình',
    active: false,
    nickname: ''
  }),
  (:LearnerNullDemo {
    learnerId: 'N-003',
    name: 'Chi'
  });
```

Đây là các node dùng riêng để thực hành; việc chạy lại `CREATE` sẽ tạo thêm node trùng dữ liệu minh họa.

Với các node trên:

- An có `active = true` và `nickname = 'Annie'`.
- Bình có `active = false` và `nickname = ''`; cả hai property **đều tồn tại**.
- Chi chưa có `active` hoặc `nickname`; khi đọc hai property này, Cypher trả về `null`.

Truy vấn kiểm tra:

```cypher
MATCH (p:LearnerNullDemo)
RETURN
  p.learnerId AS id,
  p.name AS name,
  p.active AS active,
  p.nickname AS nickname,
  p.nickname IS NULL AS nicknameIsMissing,
  'nickname' IN keys(p) AS hasNicknameKey
ORDER BY id;
```

| `id` | `active` | `nickname` | `nicknameIsMissing` | `hasNicknameKey` |
| --- | --- | --- | --- | --- |
| N-001 | `true` | `'Annie'` | `false` | `true` |
| N-002 | `false` | `''` | `false` | `true` |
| N-003 | `null` | `null` | `true` | `false` |

Hàm `keys(p)` trả về các key thuộc tính hiện được lưu trên node `p`. Hàm `properties(p)` cho phép xem map các property đó:

```cypher
MATCH (p:LearnerNullDemo {learnerId: 'N-003'})
RETURN keys(p) AS storedKeys, properties(p) AS storedProperties;
```

Ở đây, `storedKeys` chỉ chứa những property thực sự được lưu; nó không tự bổ sung `active` hay `nickname` với giá trị `null`.

### 2.2. Node/relationship khác map trung gian

Trong biểu thức Cypher, **map trung gian** có thể chứa key ánh xạ đến `null`:

```cypher
WITH {nickname: null, active: false} AS payload
RETURN
  payload.nickname IS NULL AS declaredNull,
  payload.unknown IS NULL AS absentKey,
  keys(payload) AS mapKeys;
```

Cả `payload.nickname` lẫn `payload.unknown` đều trả về `null` khi đọc. Tuy nhiên `keys(payload)` có `nickname` và `active`, còn không có `unknown`.

Đây là khác biệt quan trọng:

- Với **map trong bộ nhớ truy vấn**, có thể phân biệt *key có mặt nhưng giá trị null* với *key vắng mặt* bằng cách xem danh sách key.
- Với **property của node/relationship**, key có giá trị `null` không được lưu; property đó trở thành vắng mặt.

Nếu API cần phân biệt “người dùng không gửi trường” với “người dùng gửi trường để xóa”, phải giữ thông tin đó tại tầng ứng dụng hoặc trong dữ liệu đầu vào trước khi chuyển thành property của Neo4j.

## 3. Tạo, cập nhật và xóa property khi gặp null

### 3.1. Gán null xóa property

Trong Cypher, gán `null` cho property có tác dụng **xóa property** trên node hoặc relationship:

```cypher
MATCH (p:LearnerNullDemo {learnerId: 'N-001'})
SET p.nickname = null
RETURN
  p.nickname AS nicknameAfterUpdate,
  'nickname' IN keys(p) AS hasNicknameKey;
```

Kết quả: `nicknameAfterUpdate` là `null` và `hasNicknameKey` là `false`. Câu lệnh đã loại bỏ property `nickname`, không tạo một property với giá trị null.

Có thể xóa property trực tiếp bằng `REMOVE`:

```cypher
MATCH (p:LearnerNullDemo {learnerId: 'N-002'})
REMOVE p.nickname
RETURN keys(p) AS remainingKeys;
```

`REMOVE p.nickname` diễn đạt rõ ý định xóa trường; `SET p.nickname = null` cho kết quả lưu trữ tương đương. Hai câu lệnh minh họa trên **thay đổi dữ liệu thực hành** nên chỉ chạy khi muốn kiểm tra cơ chế cập nhật.

### 3.2. Khi tạo property bằng giá trị null

Neo4j bỏ qua property có giá trị `null` trong dữ liệu cần ghi. Trong ví dụ sau, `middleName` không trở thành property được lưu:

```cypher
CREATE (p:PersonNullExample {
  personId: 'P-NULL-001',
  name: 'Minh',
  middleName: null
})
RETURN keys(p) AS keysAfterCreate, p.middleName AS middleName;
```

Do đó, không thể dùng việc “lưu property null” làm dấu hiệu nhận biết một cột đã được gửi nhưng để trống.

### 3.3. SET với map chứa null

Cú pháp `SET n += map` có thể thêm và cập nhật property theo từng key. Nếu map chứa key nhận giá trị `null`, property tương ứng sẽ bị xóa:

```cypher
MATCH (p:PersonNullExample {personId: 'P-NULL-001'})
SET p += {
  city: 'Hà Nội',
  name: 'Minh Anh',
  middleName: null
}
RETURN properties(p) AS propertiesAfterUpdate;
```

Trường `city` được thêm, `name` được cập nhật, còn `middleName` không tồn tại. Hãy kiểm tra các giá trị `null` trong map đầu vào trước khi sử dụng `SET +=` nếu một bản cập nhật không được phép xóa dữ liệu cũ.

### 3.4. Trường khóa không được null trong MERGE

`MERGE` dùng để tìm hoặc tạo pattern theo các property khóa. Một property khóa có giá trị `null` có thể khiến `MERGE` thất bại:

```cypher
// Ví dụ KHÔNG NÊN CHẠY khi $email = null:
// MERGE (u:User {email: $email})
```

Hãy xác thực key trước khi thực hiện:

```cypher
WITH $email AS email
WHERE email IS NOT NULL
MERGE (u:User {email: email})
RETURN u;
```

Nếu `$email` là `null`, đoạn truy vấn đã kiểm tra sẽ không có dòng nào đi tới `MERGE`. Trong ứng dụng thật, cần báo lỗi đầu vào hoặc bỏ qua bản ghi có chủ đích, đồng thời cân nhắc unique constraint cho khóa nghiệp vụ khi thiết kế mô hình.

## 4. Logic ba giá trị: true, false và null

Đối với phép toán logic, Cypher sử dụng ba khả năng: **`true`, `false` và `null`** (không xác định). `null` không tự bị ép thành `false`.

### 4.1. Bảng chân trị AND và OR

| `a` | `b` | `a AND b` | `a OR b` |
| --- | --- | --- | --- |
| `true` | `true` | `true` | `true` |
| `true` | `false` | `false` | `true` |
| `true` | `null` | `null` | `true` |
| `false` | `true` | `false` | `true` |
| `false` | `false` | `false` | `false` |
| `false` | `null` | `false` | `null` |
| `null` | `true` | `null` | `true` |
| `null` | `false` | `false` | `null` |
| `null` | `null` | `null` | `null` |

Giải thích:

- `false AND null` là `false` vì đã biết một vế sai, không cần biết vế còn lại.
- `true OR null` là `true` vì đã biết một vế đúng.
- `true AND null` là `null`, vì kết quả phụ thuộc vào dữ liệu chưa biết.
- `false OR null` là `null`, cũng vì còn phụ thuộc vào giá trị chưa biết.

Có thể tự tạo bảng chân trị bằng Cypher:

```cypher
WITH [true, false, null] AS values
UNWIND values AS a
UNWIND values AS b
RETURN a, b, a AND b AS andResult, a OR b AS orResult;
```

### 4.2. NOT và XOR

| Biểu thức | Kết quả |
| --- | --- |
| `NOT true` | `false` |
| `NOT false` | `true` |
| `NOT null` | `null` |
| `true XOR false` | `true` |
| `true XOR true` | `false` |
| `false XOR false` | `false` |
| `true XOR null` | `null` |

`NOT null` vẫn là `null`: phủ định một điều chưa biết không biến điều đó thành `true`.

### 4.3. So sánh với null

Phép so sánh thông thường với `null` không cho kết quả `true` hay `false` chắc chắn; ví dụ:

```cypher
RETURN
  null = null AS equalityOfNulls,
  5 = null AS equalityWithNull,
  5 <> null AS inequalityWithNull,
  5 > null AS greaterThanNull,
  null IS NULL AS explicitNullCheck,
  null IS NOT NULL AS explicitNotNullCheck;
```

Bốn biểu thức so sánh đầu trả về `null`; hai phép kiểm tra `IS NULL` và `IS NOT NULL` lần lượt cho `true` và `false`.

**Không dùng `n.property = null` hoặc `n.property <> null` để kiểm tra giá trị thiếu.** Hãy sử dụng `IS NULL` và `IS NOT NULL`.

## 5. WHERE xử lý điều kiện null như thế nào?

Mệnh đề `WHERE` chỉ giữ các dòng mà điều kiện đánh giá thành **`true`**. Dòng có kết quả `false` hoặc `null` đều không được giữ.

Ví dụ dưới đây trả về các node có `active = true`:

```cypher
MATCH (p:LearnerNullDemo)
WHERE p.active = true
RETURN p.learnerId, p.name;
```

Với bộ dữ liệu minh họa ban đầu, An được trả về. Bình có `active = false` nên bị loại; Chi không có `active`, điều kiện `null = true` trả về `null` nên cũng bị loại.

Tương tự, phép phủ định không tự đưa node thiếu thuộc tính vào kết quả:

```cypher
MATCH (p:LearnerNullDemo)
WHERE NOT p.active
RETURN p.learnerId, p.name;
```

Truy vấn trên trả về Bình khi `active = false`, nhưng không trả về Chi vì `NOT null` là `null`.

Nếu mục tiêu là tìm cả người dùng không hoạt động **hoặc** chưa có trạng thái, viết rõ hai trường hợp:

```cypher
MATCH (p:LearnerNullDemo)
WHERE p.active = false OR p.active IS NULL
RETURN p.learnerId, p.name, p.active;
```

Nếu chỉ tìm trường đang thiếu:

```cypher
MATCH (p:LearnerNullDemo)
WHERE p.active IS NULL
RETURN p.learnerId, p.name;
```

Nếu chỉ tìm trường đã có giá trị:

```cypher
MATCH (p:LearnerNullDemo)
WHERE p.active IS NOT NULL
RETURN p.learnerId, p.name;
```

**Lưu ý:** với property thực của node/relationship, `IS NULL` kiểm tra hiệu quả tình huống property không tồn tại. Nhưng nếu biểu thức là phép tính hoặc biến từ `OPTIONAL MATCH`, `IS NULL` còn có thể xuất phát từ nguyên nhân khác.

## 6. Tính toán và hàm với null

Nhiều biểu thức số học hoặc thao tác chuỗi sẽ cho `null` khi toán hạng cần thiết bị thiếu:

```cypher
RETURN
  10 + null AS missingAddition,
  100 * null AS missingMultiplication,
  'Cypher' + null AS missingConcatenation,
  size(null) AS missingSize;
```

Việc một phép tính trả về `null` có thể hữu ích: kết quả không bị hiểu lầm là 0 khi đầu vào còn thiếu. Khi cần giá trị mặc định, sử dụng `coalesce()`.

### 6.1. coalesce chọn giá trị đầu tiên khác null

```cypher
RETURN
  coalesce(null, 'Ẩn danh') AS defaultName,
  coalesce(0, 10) AS zeroIsRetained,
  coalesce(false, true) AS falseIsRetained,
  coalesce('', 'Mặc định') AS emptyStringIsRetained;
```

`coalesce()` **không thay thế** số 0, `false` hoặc chuỗi rỗng, vì cả ba đều là các giá trị khác `null`.

Ví dụ xuất thông tin hiển thị:

```cypher
MATCH (p:LearnerNullDemo)
RETURN
  p.name,
  coalesce(p.nickname, '(chưa có biệt danh)') AS displayNickname;
```

Trong trường hợp của Bình, nếu `nickname = ''` thì kết quả vẫn là chuỗi rỗng. Nếu ứng dụng muốn hiển thị mặc định cho cả chuỗi rỗng, cần xử lý riêng theo quy tắc nghiệp vụ.

### 6.2. CASE phân loại rõ trạng thái thiếu

`CASE` cho phép biểu diễn nhiều trạng thái mà vẫn giữ khác biệt giữa `false` và `null`:

```cypher
MATCH (p:LearnerNullDemo)
RETURN
  p.name,
  CASE
    WHEN p.active = true THEN 'Đang hoạt động'
    WHEN p.active = false THEN 'Đã tạm ngừng'
    ELSE 'Chưa có trạng thái'
  END AS accountStatus;
```

Với dữ liệu minh họa ban đầu, kết quả lần lượt là “Đang hoạt động”, “Đã tạm ngừng”, “Chưa có trạng thái”. Nhánh `ELSE` bao gồm trường hợp không có giá trị `active`.

Một ví dụ khác xử lý số thiếu trong phép tính:

```cypher
WITH 150000 AS price, null AS discountPercent
RETURN
  CASE
    WHEN discountPercent IS NULL THEN null
    ELSE price * (1.0 - discountPercent / 100.0)
  END AS finalPrice;
```

Trả `null` ở đây thể hiện “chưa tính được giá cuối vì thiếu tỷ lệ giảm giá”. Đặt mặc định 0% giảm giá chỉ đúng khi nghiệp vụ cho phép.

## 7. OPTIONAL MATCH tạo giá trị null khi không có quan hệ phù hợp

`OPTIONAL MATCH` rất quan trọng trong Neo4j vì ứng dụng thường cần lấy node ngay cả khi một relationship hoặc node liên quan chưa tồn tại.

Tạo thêm khóa học minh họa và chỉ liên kết với An:

```cypher
CREATE (:CourseNullDemo {courseId: 'C-001', title: 'Cypher cơ bản'});
```

```cypher
MATCH (p:LearnerNullDemo {learnerId: 'N-001'})
MATCH (c:CourseNullDemo {courseId: 'C-001'})
CREATE (p)-[:ENROLLED_IN]->(c);
```

Sau đó truy vấn:

```cypher
MATCH (p:LearnerNullDemo)
OPTIONAL MATCH (p)-[r:ENROLLED_IN]->(c:CourseNullDemo)
RETURN
  p.learnerId AS learnerId,
  p.name AS learnerName,
  c.title AS courseTitle,
  r IS NULL AS enrollmentMissing
ORDER BY learnerId;
```

Nếu mỗi node trong ví dụ chỉ có tối đa một relationship `ENROLLED_IN`, kết quả minh họa:

| `learnerId` | `courseTitle` | `enrollmentMissing` |
| --- | --- | --- |
| N-001 | `'Cypher cơ bản'` | `false` |
| N-002 | `null` | `true` |
| N-003 | `null` | `true` |

`MATCH` thường yêu cầu pattern phù hợp để giữ dòng; `OPTIONAL MATCH` vẫn giữ dòng từ `p` và gán `null` cho phần pattern không khớp. `c.title IS NULL` trong trường hợp này có thể do biến `c` không được bind, dù không liên quan đến property `title` của một node tồn tại.

### 7.1. Vị trí WHERE thay đổi ý nghĩa

Trong ví dụ này, `WHERE` thuộc chính `OPTIONAL MATCH`:

```cypher
MATCH (p:LearnerNullDemo)
OPTIONAL MATCH (p)-[:ENROLLED_IN]->(c:CourseNullDemo)
WHERE c.title = 'Cypher cơ bản'
RETURN p.name, c.title;
```

Khi không tìm được quan hệ khóa học phù hợp, dòng `p` vẫn được giữ và `c` là `null`.

Ngược lại:

```cypher
MATCH (p:LearnerNullDemo)
OPTIONAL MATCH (p)-[:ENROLLED_IN]->(c:CourseNullDemo)
WITH p, c
WHERE c.title = 'Cypher cơ bản'
RETURN p.name, c.title;
```

Ở đây, `WHERE` lọc kết quả **sau** bước ghép tùy chọn. Với node không có khóa học, `c.title` là `null`; điều kiện không phải `true` nên node đó bị loại.

Đây là nguyên nhân thường gặp khiến truy vấn tưởng đã dùng `OPTIONAL MATCH` nhưng vẫn mất các node không có relationship.

### 7.2. Kiểm tra sự tồn tại của relationship bằng EXISTS

Nếu cần kiểm tra *có hay không* một quan hệ, có thể dùng biểu thức `EXISTS { ... }` thay vì lấy dữ liệu rồi so sánh với `null`:

```cypher
MATCH (p:LearnerNullDemo)
RETURN
  p.name,
  EXISTS {
    MATCH (p)-[:ENROLLED_IN]->(:CourseNullDemo)
  } AS hasEnrollment;
```

Truy vấn này trả giá trị luận lý cho sự tồn tại của pattern. Khi chỉ cần biết có liên kết hay không, biểu diễn này thường rõ ý định hơn so với một `OPTIONAL MATCH` chỉ để tạo cờ.

## 8. null trong danh sách, IN và phép tổng hợp

### 8.1. Danh sách trong biểu thức có thể chứa null

```cypher
RETURN
  [1, null, 3] AS valuesInQuery,
  size([1, null, 3]) AS numberOfElements;
```

Danh sách trên có ba phần tử trong **biểu thức Cypher**. Tuy nhiên, một property dạng danh sách của node/relationship không thể lưu trực tiếp phần tử `null`. Nếu cần lưu list thành property, phải làm sạch phần tử thiếu hoặc thay đổi mô hình dữ liệu trước khi `SET`.

Ví dụ lọc `null` khỏi danh sách:

```cypher
WITH [1, null, 3, null, 5] AS rawNumbers
RETURN [x IN rawNumbers WHERE x IS NOT NULL] AS cleanNumbers;
```

Kết quả `cleanNumbers` là `[1, 3, 5]`.

`UNWIND` có thể tạo dòng với giá trị `null`; lọc bằng `WHERE` nếu không cần dòng đó:

```cypher
UNWIND [1, null, 3] AS number
WITH number
WHERE number IS NOT NULL
RETURN number
ORDER BY number;
```

### 8.2. Toán tử IN khi danh sách có null

Với danh sách chứa `null`, kết quả `IN` đôi khi không xác định:

```cypher
RETURN
  5 IN [5, null] AS definitelyPresent,
  5 IN [3, null] AS cannotConfirmAbsent,
  5 IN [3, 4] AS definitelyAbsent;
```

Kết quả là `true`, `null` và `false`. Trong trường hợp thứ hai, không có phần tử đã biết bằng 5, nhưng vẫn có một phần tử chưa biết, nên không thể khẳng định `false`.

Nếu danh sách dùng để kiểm tra tập mã định danh, cần chủ động xử lý phần tử null trước khi kiểm tra điều kiện tồn tại.

### 8.3. count(*) khác count(expression)

Các hàm tổng hợp phân biệt số dòng với số giá trị không null:

```cypher
MATCH (p:LearnerNullDemo)
RETURN
  count(*) AS learnerRows,
  count(p.active) AS learnersWithActive,
  count(p.nickname) AS learnersWithNickname;
```

Với ba node ban đầu, `learnerRows` bằng 3; `learnersWithActive` bằng 2; `learnersWithNickname` bằng 2. Nếu đã chạy các đoạn `SET ... = null` hoặc `REMOVE` ở phần trước thì các con số đếm property sẽ thay đổi tương ứng.

- `count(*)` đếm **dòng kết quả**, kể cả khi một số cột trên dòng là null.
- `count(p.active)` chỉ đếm dòng có `p.active` khác `null`. Giá trị `false` vẫn được tính.
- `count(p.nickname)` tính cả chuỗi rỗng `''` vì chuỗi rỗng không phải `null`.

Hàm `collect(expression)` bỏ qua giá trị `null`, do đó danh sách tổng hợp có thể có ít phần tử hơn số dòng:

```cypher
MATCH (p:LearnerNullDemo)
RETURN
  count(*) AS totalRows,
  collect(p.nickname) AS availableNicknames;
```

Khi tính trung bình hoặc tổng trên các thuộc tính có thể thiếu, hãy cân nhắc số lượng giá trị tham gia phép tính và mục đích nghiệp vụ: “không biết điểm” khác với “điểm bằng 0”.

### 8.4. Đếm relationship với OPTIONAL MATCH

```cypher
MATCH (p:LearnerNullDemo)
OPTIONAL MATCH (p)-[r:ENROLLED_IN]->(:CourseNullDemo)
RETURN
  p.learnerId AS id,
  count(r) AS enrollmentCount
ORDER BY id;
```

`count(r)` đếm relationship thực sự khớp, nên node chưa ghi danh có kết quả `0`. Nếu thay bằng `count(*)`, dòng do `OPTIONAL MATCH` giữ lại cũng được tính; khi không có relationship, mỗi learner vẫn đóng góp một dòng. Lựa chọn biểu thức đếm cần khớp với câu hỏi nghiệp vụ.

## 9. null trong tham số Java Driver và Spring Data Neo4j

Một API cập nhật người dùng có thể nhận yêu cầu gồm `nickname` hoặc không có trường này. Tại tầng ứng dụng, thường cần phân biệt ba ý nghĩa:

| Trạng thái đầu vào | Ý nghĩa nghiệp vụ ví dụ | Hành vi đề xuất |
| --- | --- | --- |
| Không gửi trường `nickname` | Giữ nguyên thông tin cũ | Không cập nhật property |
| Gửi `nickname: null` | Xóa biệt danh | Xóa property có chủ đích |
| Gửi `nickname: ''` | Đặt biệt danh thành chuỗi rỗng | Lưu chuỗi rỗng nếu hợp lệ |

Neo4j chỉ thấy giá trị của tham số được truyền vào truy vấn; nếu ứng dụng đã gộp cả hai trường hợp đầu thành `null`, Cypher không thể tự biết người dùng muốn “giữ” hay “xóa”.

Ví dụ truy vấn:

```cypher
MATCH (p:User {userId: $userId})
SET p.nickname = $nickname
RETURN p.userId, p.nickname;
```

Khi Java Driver truyền `$nickname = null`, câu `SET` xóa property biệt danh. Nếu tham số `$nickname` **không được truyền** dù câu truy vấn có tham chiếu tới nó, Neo4j sẽ báo thiếu tham số; đây không phải cách thể hiện “không cập nhật”.

Nếu nghiệp vụ quy định giá trị `null` có nghĩa “giữ nguyên”, có thể sử dụng:

```cypher
MATCH (p:User {userId: $userId})
SET p.nickname = coalesce($nickname, p.nickname)
RETURN p.userId, p.nickname;
```

Cách này giữ property cũ khi `$nickname` là `null` nhưng **không cho phép người gọi dùng null để xóa**. Nếu API cần phân biệt giữ và xóa, nên chuyển trạng thái cập nhật thành hành động rõ ràng từ tầng Java, ví dụ chỉ thêm `SET` khi có thay đổi và dùng `REMOVE` khi cần xóa.

Với Java Driver, khi đọc giá trị trả về, có thể kiểm tra `Value.isNull()` trước khi lấy giá trị Java. Trong Spring Data Neo4j, cần xác định quy ước mapping trường thiếu sang thuộc tính của entity và thiết kế DTO cập nhật sao cho phân biệt được “vắng mặt” với “null được gửi có chủ đích” nếu nghiệp vụ yêu cầu.

**Đặc biệt với MERGE:** kiểm tra các khóa định danh/khóa dùng để ghép trước khi chạy Cypher. Một map chứa `null` trong khóa có thể tạo lỗi hoặc làm pipeline nhập dữ liệu bị gián đoạn.

## 10. Lỗi thường gặp và cách khắc phục

| Tình huống | Vì sao sai hoặc bất ngờ? | Cách xử lý |
| --- | --- | --- |
| `WHERE n.email = null` | `= null` tạo kết quả `null` | Dùng `n.email IS NULL` |
| `WHERE n.email <> null` | Không kiểm tra được “đã có email” | Dùng `n.email IS NOT NULL` |
| `WHERE NOT n.active` để lấy cả người chưa có trạng thái | `NOT null` vẫn là `null` | Bổ sung `OR n.active IS NULL` nếu nghiệp vụ cần |
| `SET n.email = $email` với `$email = null` | Xóa property đang có | Kiểm tra ý định cập nhật trước khi `SET` |
| `SET n += $patch` với key mang null | Key đó xóa property | Lọc/diễn giải dữ liệu patch tại tầng ứng dụng |
| `MERGE (n:User {email: $email})` với email null | Không thể dùng null làm giá trị property khóa của `MERGE` | Xác thực key trước khi ghép |
| `OPTIONAL MATCH` rồi `WHERE matched.value = ...` ở bước sau | Lọc bỏ dòng có biến matched bằng null | Đặt điều kiện đúng chỗ hoặc xử lý `IS NULL` |
| `count(*)` được hiểu là số quan hệ tồn tại | Đếm cả dòng rỗng từ `OPTIONAL MATCH` | Dùng `count(r)` nếu cần đếm quan hệ |
| `coalesce(n.score, 0)` được dùng mà không xét nghiệp vụ | Biến “chưa có điểm” thành “điểm 0” | Chỉ mặc định 0 nếu có quy định |
| Lưu `[1, null, 3]` thành property list | Property list không chứa phần tử null | Lọc dữ liệu hoặc đổi mô hình |

## 11. Thực hành có lời giải

### Bài 1 — Phân biệt null với giá trị cụ thể

Dự đoán kết quả của truy vấn:

```cypher
RETURN
  false IS NULL AS a,
  0 IS NULL AS b,
  '' IS NULL AS c,
  null IS NULL AS d;
```

**Đáp án:** `a = false`, `b = false`, `c = false`, `d = true`. Giá trị luận lý sai, số 0 và chuỗi rỗng đều là những giá trị hợp lệ.

### Bài 2 — Đọc bảng chân trị

Tính `true AND null`, `false AND null`, `true OR null` và `NOT null`.

**Đáp án:** lần lượt `null`, `false`, `true`, `null`. Dù thiếu một toán hạng, `AND` và `OR` đôi khi vẫn xác định được kết quả từ toán hạng còn lại.

### Bài 3 — Tìm người chưa có trạng thái xác minh

Node `User` có property `verified` mang `true`, `false` hoặc không tồn tại. Hãy tìm đúng các node chưa có property `verified`.

**Đáp án:**

```cypher
MATCH (u:User)
WHERE u.verified IS NULL
RETURN u.userId;
```

Không dùng `u.verified = false` vì điều kiện đó chỉ áp dụng cho trạng thái đã biết là sai.

### Bài 4 — Giữ cả người học chưa đăng ký khóa nào

Trả về tên người học, tên khóa học nếu có và hiển thị chuỗi `'(chưa đăng ký)'` nếu không có quan hệ đăng ký.

**Đáp án:**

```cypher
MATCH (p:LearnerNullDemo)
OPTIONAL MATCH (p)-[:ENROLLED_IN]->(c:CourseNullDemo)
RETURN
  p.name AS learnerName,
  coalesce(c.title, '(chưa đăng ký)') AS courseName;
```

Vì `OPTIONAL MATCH` giữ dòng người học, `coalesce()` có thể thay tên khóa học vắng mặt bằng thông báo hiển thị.

### Bài 5 — Đếm các quan hệ có thật

Một người học có thể có 0, 1 hoặc nhiều relationship `ENROLLED_IN`. Hãy đếm số quan hệ cho từng người, kể cả người chưa đăng ký.

**Đáp án:**

```cypher
MATCH (p:LearnerNullDemo)
OPTIONAL MATCH (p)-[r:ENROLLED_IN]->(:CourseNullDemo)
RETURN
  p.name,
  count(r) AS numberOfEnrollments
ORDER BY p.name;
```

Khi không khớp relationship, `r` là `null` và không được tính bởi `count(r)`.

### Bài 6 — Dự đoán tác động của cập nhật

Ban đầu node có `nickname = 'Annie'`. Điều gì xảy ra sau `SET p.nickname = null`? Liệu `p.nickname IS NULL` có trả `true` không?

**Đáp án:** property `nickname` bị xóa, việc đọc `p.nickname` sau đó trả `null` và `p.nickname IS NULL` cho `true`.

## 12. Checklist áp dụng trong dự án Neo4j

Trước khi triển khai truy vấn Cypher hoặc cập nhật qua Java Driver/Spring Data Neo4j, hãy tự kiểm tra:

1. Trường dữ liệu thiếu có thực sự khác với `false`, `0` hoặc chuỗi rỗng không?
2. Điều kiện lọc có dùng `IS NULL`/`IS NOT NULL` thay vì `= null` không?
3. Phép `AND`, `OR`, `NOT` có thể tạo `null` và khiến `WHERE` loại dòng không?
4. `OPTIONAL MATCH` có đang bị một điều kiện `WHERE` về sau vô tình biến thành phép lọc bắt buộc không?
5. `count(*)` hay `count(expression)` mới đúng với đại lượng cần đếm?
6. Có nguy cơ gán `null` làm mất property cũ khi xử lý tham số hoặc map cập nhật không?
7. Khóa dùng trong `MERGE` có được xác thực là khác null không?
8. API có cần phân biệt “không gửi trường”, “gửi null để xóa” và “gửi giá trị rỗng” không?
9. Có cần lưu dấu hiệu nghiệp vụ bổ sung như `verificationStatus` để phân biệt nhiều loại “chưa biết” hay không?

---

**Ghi nhớ:** `null` là trạng thái không có giá trị xác định trong biểu thức; trên node và relationship, property mang `null` không được lưu và phép gán `null` sẽ xóa property. Logic ba giá trị khiến phép so sánh hoặc phủ định dữ liệu thiếu thường vẫn tạo `null`. Dùng `IS NULL`, `IS NOT NULL`, `OPTIONAL MATCH`, `CASE` và `coalesce()` theo đúng mục tiêu nghiệp vụ, đồng thời kiểm soát tham số cập nhật để tránh vô tình đánh mất dữ liệu.

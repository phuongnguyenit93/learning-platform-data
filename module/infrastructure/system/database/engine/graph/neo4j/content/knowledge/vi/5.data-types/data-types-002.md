# Chuỗi, số, giá trị luận lý và chuyển đổi kiểu dữ liệu trong Cypher

Khi mô hình hóa dữ liệu bằng **Neo4j**, node và relationship thường mang các thuộc tính như mã định danh, tên, giá, số lượt đăng ký và trạng thái hoạt động. Cypher cho phép thao tác với các thuộc tính đó bằng các kiểu **`STRING`, `INTEGER`, `FLOAT` và `BOOLEAN`**, đồng thời cung cấp hàm chuyển đổi kiểu để xử lý dữ liệu từ ứng dụng, CSV hoặc API.

Bài học tập trung vào cách **biểu diễn, tính toán, so sánh, lọc và chuyển đổi** bốn nhóm giá trị trên. Đây là nền tảng để viết truy vấn Cypher chính xác, xây dựng pipeline nhập dữ liệu và trao đổi tham số với Java Driver hoặc Spring Data Neo4j.

## 1. Nhận biết kiểu giá trị trong Cypher

| Kiểu | Giá trị ví dụ | Tình huống thường gặp | Ghi chú |
| --- | --- | --- | --- |
| `STRING` | `'Neo4j'`, `'SP-001'`, `''` | Tên, mã nghiệp vụ, email, nhãn | Chuỗi rỗng vẫn là giá trị |
| `INTEGER` | `0`, `-8`, `150000` | Tuổi, số lượng, bộ đếm, số tiền ở đơn vị nhỏ nhất | Số nguyên có dấu 64 bit |
| `FLOAT` | `2.5`, `-0.75`, `1.0e3` | Điểm đo, tỷ lệ, số liệu liên tục | Dấu phẩy động 64 bit, có thể có sai số |
| `BOOLEAN` | `true`, `false` | Kích hoạt, xác nhận, công khai | Không tự đồng nghĩa với `'true'` và `'false'` |
| `null` | `null` | Dữ liệu thiếu hoặc biểu thức không có giá trị | Không phải `false`, `0` hoặc `''` |

**Nhận xét quan trọng:** dấu nháy ảnh hưởng đến kiểu dữ liệu. `25` là số nguyên, `25.0` là số thực, còn `'25'` là chuỗi. Tương tự, `true` là giá trị luận lý, nhưng `'true'` là chuỗi ký tự.

```cypher
RETURN
  25 AS integerValue,
  25.0 AS floatValue,
  '25' AS stringValue,
  true AS booleanValue,
  'true' AS textValue;
```

Trong môi trường Neo4j/Cypher có hỗ trợ hàm `valueType()`, có thể kiểm tra kiểu khi điều tra dữ liệu:

```cypher
RETURN
  valueType(25) AS integerType,
  valueType(25.0) AS floatType,
  valueType('25') AS stringType,
  valueType(true) AS booleanType;
```

Tên kiểu trong kết quả `valueType()` có thể phản ánh chi tiết hệ kiểu của phiên bản Cypher. Khi làm việc với hệ thống thực, hãy đối chiếu tài liệu của phiên bản Neo4j đang sử dụng.

## 2. Chuỗi STRING: biểu diễn và thao tác văn bản

### 2.1. Literal chuỗi và ký tự đặc biệt

Cypher cho phép sử dụng dấu nháy đơn hoặc nháy kép để biểu diễn chuỗi. Trong ví dụ thông thường, có thể dùng nháy đơn để tránh nhầm với tên thuộc tính.

```cypher
RETURN
  'Neo4j' AS productName,
  "Cypher" AS queryLanguage,
  'Nguyễn Minh Anh' AS fullName,
  '' AS emptyString;
```

Chuỗi được lưu theo Unicode, vì vậy nội dung tiếng Việt có dấu có thể xuất hiện trong giá trị property:

```cypher
CREATE (b:Book {
  bookCode: 'SACH-001',
  title: 'Nhập môn cơ sở dữ liệu đồ thị',
  author: 'Trần Hà'
})
RETURN b.title, b.author;
```

Để đặt dấu nháy bên trong chuỗi, dùng dấu nháy bao ngoài phù hợp hoặc escape dấu nháy:

```cypher
RETURN
  "O'Reilly" AS publisher,
  'Câu lệnh: "MATCH (n) RETURN n"' AS example,
  'It\'s a graph' AS escapedApostrophe,
  'Dòng 1\nDòng 2' AS multilineContent;
```

Trong đoạn Cypher trên, `\'` tạo dấu nháy đơn bên trong chuỗi nháy đơn và `\n` biểu diễn ký tự xuống dòng.

### 2.2. Các thao tác chuỗi thông dụng

| Biểu thức | Kết quả kỳ vọng | Mục đích |
| --- | --- | --- |
| `toUpper('Neo4j')` | `'NEO4J'` | Đổi sang chữ hoa |
| `toLower('Cypher')` | `'cypher'` | Đổi sang chữ thường |
| `trim('  Lan  ')` | `'Lan'` | Bỏ khoảng trắng ở hai đầu |
| `substring('Neo4j', 0, 3)` | `'Neo'` | Lấy chuỗi con; chỉ số bắt đầu từ 0 |
| `replace('graph-db', '-', ' ')` | `'graph db'` | Thay thế đoạn văn bản |
| `split('java,cypher', ',')` | `['java', 'cypher']` | Tách chuỗi thành danh sách |
| `'Neo' + '4j'` | `'Neo4j'` | Nối chuỗi theo cú pháp được hỗ trợ |

Ví dụ sử dụng các hàm chuỗi trong truy vấn:

```cypher
WITH '  Graph Database  ' AS rawTitle
RETURN
  trim(rawTitle) AS cleanTitle,
  toLower(trim(rawTitle)) AS normalizedTitle,
  replace(trim(rawTitle), ' ', '-') AS slugCandidate;
```

Chuỗi ghép bằng dấu `+` là cú pháp quen thuộc trong Cypher; các phiên bản hiện đại cũng có toán tử nối chuỗi `||`. Khi lựa chọn cú pháp cho dự án, nên thống nhất theo phiên bản Neo4j và quy ước trong mã nguồn.

### 2.3. So sánh và tìm kiếm chuỗi

Các toán tử thường dùng:

- `=` và `<>` để kiểm tra bằng/khác.
- `STARTS WITH` để kiểm tra tiền tố.
- `ENDS WITH` để kiểm tra hậu tố.
- `CONTAINS` để kiểm tra chuỗi con.
- `=~` để đối chiếu với biểu thức chính quy.

```cypher
MATCH (b:Book)
WHERE b.title CONTAINS 'đồ thị'
RETURN b.bookCode, b.title;
```

```cypher
MATCH (b:Book)
WHERE b.bookCode STARTS WITH 'SACH-'
RETURN b.bookCode, b.title;
```

So sánh chuỗi theo giá trị ký tự; đừng mặc định hệ thống tự bỏ dấu tiếng Việt, bỏ khoảng trắng hoặc không phân biệt hoa/thường. Nếu nghiệp vụ cần tìm kiếm không phân biệt chữ hoa/chữ thường, có thể chuẩn hóa hai phía cho truy vấn đơn giản:

```cypher
MATCH (b:Book)
WHERE toLower(b.title) CONTAINS toLower($keyword)
RETURN b.title;
```

**Lưu ý hiệu năng:** việc bọc property trong hàm như `toLower(b.title)` có thể khiến một số index thông thường không hỗ trợ truy vấn theo cách mong muốn. Với nhu cầu tìm kiếm lớn, hãy cân nhắc thuộc tính đã chuẩn hóa, text/full-text index phù hợp và kiểm tra bằng `EXPLAIN` hoặc `PROFILE`. Các chiến lược tìm kiếm nâng cao thuộc phần index và tối ưu truy vấn.

### 2.4. Chuỗi không phải số, ngày hoặc boolean

`'00128'` là lựa chọn đúng cho mã nghiệp vụ có số 0 đầu; chuyển thành `INTEGER` sẽ làm mất số 0 đó. `'2026-11-25'` cũng vẫn là chuỗi cho đến khi được chuyển sang `DATE` nếu nghiệp vụ cần tính ngày. Khi đưa dữ liệu vào Neo4j, kiểu cần được quyết định theo **ngữ nghĩa** của trường dữ liệu chứ không chỉ theo hình thức ký tự.

## 3. Số INTEGER và FLOAT

### 3.1. Biểu diễn số và chọn kiểu

`INTEGER` dùng cho giá trị nguyên nằm trong miền số nguyên 64 bit có dấu:

- Giá trị nhỏ nhất: `-9223372036854775808`.
- Giá trị lớn nhất: `9223372036854775807`.

`FLOAT` là số thực dấu phẩy động 64 bit theo IEEE 754. Kiểu này phù hợp cho nhiều phép đo và tỷ lệ, nhưng **không thể biểu diễn chính xác mọi số thập phân**.

```cypher
RETURN
  120 AS quantity,
  -15 AS adjustment,
  19.5 AS rating,
  1.0e3 AS scientificNotation;
```

Chọn kiểu dựa trên nhu cầu nghiệp vụ:

| Dữ liệu | Kiểu khuyến nghị | Lý do |
| --- | --- | --- |
| Số lượt đăng nhập | `INTEGER` | Đếm giá trị nguyên |
| Giá bán bằng VND nguyên đồng | `INTEGER` | Tránh sai số số thực nếu đơn vị nghiệp vụ là đồng |
| Tỷ lệ hoàn thành 87.5% | `FLOAT` | Có phần thập phân |
| Nhiệt độ 26.4 °C | `FLOAT` | Đại lượng đo liên tục |
| Mã hóa đơn `'000001'` | `STRING` | Mã không dùng tính toán, cần giữ số 0 |

Với đơn vị tiền có phần lẻ, thường lưu thành `INTEGER` theo đơn vị nhỏ nhất của đồng tiền (ví dụ số xu) và chuyển đổi khi hiển thị. Phải xác định rõ quy ước đơn vị để tránh nhầm lẫn.

### 3.2. Phép toán số học

Cypher hỗ trợ các toán tử số học cơ bản:

```cypher
RETURN
  8 + 3 AS addition,
  8 - 3 AS subtraction,
  8 * 3 AS multiplication,
  8 / 3 AS integerDivision,
  8 / 3.0 AS floatingDivision,
  8 % 3 AS remainder;
```

Khi hai toán hạng là `INTEGER`, phép chia `/` cho kết quả chia nguyên. Chỉ cần một toán hạng là `FLOAT` thì phép chia được xử lý theo số thực.

| Biểu thức | Kết quả | Giải thích |
| --- | --- | --- |
| `7 / 2` | `3` | Chia nguyên |
| `7 / 2.0` | `3.5` | Chia số thực |
| `7 % 2` | `1` | Số dư |
| `3 + 2 * 4` | `11` | Nhân trước cộng |
| `(3 + 2) * 4` | `20` | Ngoặc quyết định thứ tự |

Không chia cho 0. Khi một toán hạng có thể thiếu hoặc mẫu số có thể bằng 0, cần xác thực hoặc xử lý trường hợp đó trước khi thực hiện.

Ví dụ tính tỷ lệ hoàn thành dưới dạng phần trăm:

```cypher
WITH 7 AS completed, 10 AS total
RETURN
  100.0 * completed / total AS percentCompleted;
```

Nhân với `100.0` giữ phép tính theo số thực. Khi đưa vào báo cáo, có thể làm tròn ở bước hiển thị theo nhu cầu.

### 3.3. So sánh số và điều kiện lọc

```cypher
MATCH (p:Product)
WHERE p.priceVnd >= 100000
  AND p.stockQuantity > 0
RETURN p.productCode, p.priceVnd, p.stockQuantity
ORDER BY p.priceVnd DESC;
```

Đối với dữ liệu nhập không ổn định, phải chắc chắn `priceVnd` và `stockQuantity` đang được lưu dưới kiểu số. Chuỗi `'100000'` nhìn giống số nhưng không tự động mang ý nghĩa số học trong mọi biểu thức. Tránh trộn kiểu chuỗi và số trong cùng một property.

### 3.4. Sai số số thực

Không nên xem phép so sánh bằng tuyệt đối giữa hai phép tính `FLOAT` là an toàn trong mọi trường hợp. Một số giá trị thập phân như `0.1` không được biểu diễn chính xác bằng nhị phân, nên kết quả tính toán có thể sai khác rất nhỏ so với giá trị mong muốn.

```cypher
WITH 0.1 + 0.2 AS calculated, 0.3 AS expected
RETURN
  calculated,
  expected,
  abs(calculated - expected) AS difference,
  abs(calculated - expected) < 0.000001 AS approximatelyEqual;
```

Ngưỡng sai số phải dựa trên phạm vi, đơn vị đo và yêu cầu nghiệp vụ. Với các phép tính tài chính cần chính xác tuyệt đối, sử dụng mô hình số nguyên theo đơn vị nhỏ nhất hoặc cơ chế tính toán số thập phân chính xác ở tầng phù hợp.

## 4. BOOLEAN: logic đúng, sai và điều kiện lọc

`BOOLEAN` có hai giá trị xác định: `true` và `false`. Trong truy vấn, biểu thức điều kiện có thể nhận thêm `null` khi thiếu thông tin.

```cypher
CREATE (u:User {
  userId: 'U-001',
  displayName: 'Mai',
  active: true,
  emailVerified: false
})
RETURN u.userId, u.active, u.emailVerified;
```

Các biểu thức so sánh `=`, `<>`, `<`, `<=`, `>`, `>=` đối với các kiểu phù hợp có thể tạo giá trị luận lý. Để kết hợp điều kiện, dùng `AND`, `OR` và `NOT`:

```cypher
MATCH (u:User)
WHERE u.active = true
  AND u.emailVerified = false
RETURN u.userId, u.displayName;
```

Có thể viết `WHERE u.active` khi chắc chắn `u.active` là thuộc tính boolean. Cú pháp tường minh `u.active = true` thường dễ đọc hơn trong tài liệu nhập môn.

### 4.1. Bảng chân trị cơ bản

| `a` | `b` | `a AND b` | `a OR b` |
| --- | --- | --- | --- |
| `true` | `true` | `true` | `true` |
| `true` | `false` | `false` | `true` |
| `false` | `true` | `false` | `true` |
| `false` | `false` | `false` | `false` |

`NOT true` cho `false`; `NOT false` cho `true`. Dùng ngoặc khi điều kiện kết hợp nhiều `AND` và `OR`, giúp thể hiện rõ ý định và tránh phụ thuộc vào việc người đọc nhớ thứ tự ưu tiên toán tử.

```cypher
MATCH (u:User)
WHERE u.active = true
  AND (u.emailVerified = true OR u.displayName STARTS WITH 'M')
RETURN u.userId, u.displayName;
```

### 4.2. Logic ba giá trị khi gặp NULL

`null` không đồng nghĩa với `false`. Khi thiếu giá trị, nhiều phép logic trả về `null` (không xác định).

| Biểu thức | Kết quả |
| --- | --- |
| `true AND null` | `null` |
| `false AND null` | `false` |
| `true OR null` | `true` |
| `false OR null` | `null` |
| `NOT null` | `null` |
| `null = null` | `null` |

Mệnh đề `WHERE` giữ lại các dòng có điều kiện là `true`. Điều kiện ra `false` hoặc `null` đều không được giữ lại.

```cypher
MATCH (u:User)
WHERE u.emailVerified IS NULL
RETURN u.userId, u.displayName;
```

Nếu cần coi giá trị thiếu là `false` theo quy tắc nghiệp vụ, dùng `coalesce()`:

```cypher
MATCH (u:User)
WHERE coalesce(u.emailVerified, false) = false
RETURN u.userId, u.displayName;
```

Câu truy vấn trên lấy cả người dùng `emailVerified = false` **và** người dùng không có property `emailVerified`. Chỉ áp dụng cách này khi hai trạng thái có thể được xem tương đương về mặt nghiệp vụ.

### 4.3. Dùng CASE để tạo nhãn hiển thị

`CASE` giúp ánh xạ biểu thức logic sang kết quả dễ hiểu:

```cypher
MATCH (u:User)
RETURN
  u.userId,
  CASE
    WHEN u.active = true THEN 'Đang hoạt động'
    WHEN u.active = false THEN 'Đã tạm ngừng'
    ELSE 'Chưa có thông tin'
  END AS accountStatus;
```

Nhánh `ELSE` ở ví dụ này xử lý giá trị thiếu; việc phân biệt ba trạng thái giúp tránh báo nhầm dữ liệu chưa biết thành trạng thái không hoạt động.

## 5. Chuyển đổi kiểu: tại sao và khi nào cần

Dữ liệu đi vào Neo4j có thể đến từ CSV, JSON, HTTP request hoặc tham số Java Driver. CSV thường đưa giá trị cột vào dưới dạng chuỗi; JSON và Java có thể phân biệt số, boolean và chuỗi nhưng vẫn có nguy cơ truyền sai kiểu.

Ví dụ đầu vào dạng chuỗi:

```cypher
WITH {
  age: '29',
  rating: '4.5',
  active: 'true'
} AS raw
RETURN
  raw.age AS ageText,
  raw.rating AS ratingText,
  raw.active AS activeText;
```

Muốn tính tuổi, so sánh điểm hoặc dùng trạng thái trong `WHERE`, cần chuyển đổi sang kiểu phù hợp trước khi ghi và truy vấn. Cypher **không nên bị coi là sẽ tự ép chuỗi sang số hoặc boolean theo ý người dùng**.

## 6. Các hàm chuyển đổi kiểu phổ biến

| Hàm | Ví dụ | Kết quả hoặc ý nghĩa |
| --- | --- | --- |
| `toString(value)` | `toString(25)` | Chuỗi `'25'` |
| `toString(value)` | `toString(true)` | Chuỗi `'true'` |
| `toInteger(value)` | `toInteger('25')` | Số nguyên `25` |
| `toInteger(value)` | `toInteger(3.9)` | Số nguyên `3` |
| `toFloat(value)` | `toFloat('3.9')` | Số thực `3.9` |
| `toFloat(value)` | `toFloat(7)` | Số thực `7.0` |
| `toBoolean(value)` | `toBoolean('true')` | Giá trị `true` |
| `toBoolean(value)` | `toBoolean('false')` | Giá trị `false` |
| `toIntegerOrNull(value)` | `toIntegerOrNull('abc')` | `null` nếu không đổi được |
| `toFloatOrNull(value)` | `toFloatOrNull('abc')` | `null` nếu không đổi được |
| `toBooleanOrNull(value)` | `toBooleanOrNull('unknown')` | `null` nếu không đổi được |

Các hàm `...OrNull` giúp xử lý đầu vào có khả năng không hợp lệ; sự khác biệt chính là chúng cho phép kết quả `null` trong các trường hợp chuyển đổi không thành công. Cần nhớ `null` vẫn phải được xử lý tiếp, đặc biệt trước thao tác `SET`.

### 6.1. Chuyển chuỗi sang số

```cypher
RETURN
  toInteger('120') AS quantity,
  toFloat('120.5') AS amount,
  toInteger(12.9) AS truncatedInteger,
  toIntegerOrNull('không phải số') AS invalidInteger,
  toFloatOrNull('không phải số') AS invalidFloat;
```

`toInteger(12.9)` bỏ phần thập phân khi chuyển thành số nguyên, không phải phép làm tròn thông thường. Không dùng phép chuyển đổi này nếu nghiệp vụ yêu cầu làm tròn theo một quy tắc khác.

Trước khi chuyển, hãy quyết định có cho phép số âm, phần thập phân, khoảng trắng, ký hiệu tiền tệ hay dấu phân cách hàng nghìn trong đầu vào không. Ví dụ `'1,200'` không nên được mặc nhiên hiểu là số 1200 nếu chưa chuẩn hóa định dạng.

### 6.2. Chuyển chuỗi sang BOOLEAN

```cypher
RETURN
  toBoolean('true') AS enabled,
  toBoolean('false') AS disabled,
  toBooleanOrNull('không rõ') AS unknownStatus;
```

Nếu nguồn dữ liệu dùng `'Y'`/`'N'`, `'yes'`/`'no'` hoặc `'1'`/`'0'`, nên **quy định phép ánh xạ nghiệp vụ rõ ràng**, không giả định `toBoolean()` tự hiểu mọi quy ước:

```cypher
WITH 'Y' AS sourceFlag
RETURN
  CASE toUpper(sourceFlag)
    WHEN 'Y' THEN true
    WHEN 'N' THEN false
    ELSE null
  END AS active;
```

Với cột nguồn có giá trị trống, cần xác định trống có nghĩa là “không xác định”, “không kích hoạt” hay “dữ liệu lỗi” để quyết định nên trả `null`, `false` hoặc từ chối bản ghi.

### 6.3. Chuyển sang STRING

```cypher
RETURN
  toString(2026) AS yearAsText,
  toString(4.5) AS ratingAsText,
  toString(false) AS falseAsText;
```

`toString()` hữu ích khi tạo nội dung hiển thị, nhãn hoặc dữ liệu xuất. Tuy nhiên, **không nên chuyển số sang chuỗi chỉ để lưu mọi property cùng một kiểu**. Làm vậy sẽ khiến phép tính số học và so sánh số khó kiểm soát hơn.

### 6.4. NULL khi chuyển đổi

```cypher
RETURN
  toIntegerOrNull(null) AS missingInteger,
  toFloatOrNull('invalid') AS invalidMeasurement,
  coalesce(toIntegerOrNull('invalid'), 0) AS quantityWithDefault;
```

`coalesce()` chọn giá trị đầu tiên khác `null`, nhưng mặc định `0` có thể **che giấu dữ liệu đầu vào sai**. Chỉ dùng giá trị mặc định nếu nghiệp vụ thực sự định nghĩa trường hợp thiếu hoặc lỗi như vậy; với dữ liệu cần kiểm soát chất lượng, nên loại, ghi nhận hoặc báo lỗi thay vì lặng lẽ thay bằng 0.

## 7. Chuẩn hóa và kiểm tra trước khi ghi property

Giả sử một ứng dụng nhập danh sách sản phẩm với giá và trạng thái ở dạng chuỗi. Ví dụ sau chuyển kiểu, loại dữ liệu sai rồi mới ghi vào Neo4j.

```cypher
WITH [
  {code: 'SP-001', price: '125000', active: 'true'},
  {code: 'SP-002', price: 'not-a-number', active: 'false'},
  {code: 'SP-003', price: '89000', active: 'false'}
] AS rows
UNWIND rows AS row

WITH
  row,
  toIntegerOrNull(row.price) AS parsedPrice,
  toBooleanOrNull(row.active) AS parsedActive

WHERE parsedPrice IS NOT NULL
  AND parsedPrice >= 0
  AND parsedActive IS NOT NULL

MERGE (p:Product {productCode: row.code})
SET
  p.priceVnd = parsedPrice,
  p.active = parsedActive
RETURN p.productCode, p.priceVnd, p.active
ORDER BY p.productCode;
```

Kết quả mong đợi: hai sản phẩm hợp lệ `SP-001` và `SP-003` được ghi; `SP-002` bị bỏ qua do giá không chuyển được sang số nguyên. Lưu ý ví dụ **không ghi log cho hàng bị loại**; trong hệ thống nhập dữ liệu thực cần có cơ chế thống kê và báo cáo bản ghi lỗi.

Vì sao không thực hiện ngay `SET p.priceVnd = toIntegerOrNull(row.price)`? Nếu giá trị chuyển đổi thành `null`, Neo4j sẽ xóa property tương ứng. Việc kiểm tra `IS NOT NULL` trước khi ghi tránh tác dụng phụ đó.

### 7.1. Kiểm tra bằng biểu thức chính quy

Với một chuỗi số nguyên dương chỉ cho phép chữ số ASCII, có thể kiểm tra trước:

```cypher
WITH '0042' AS rawCount
RETURN
  rawCount =~ '^[0-9]+$' AS validDigits,
  toIntegerOrNull(rawCount) AS parsedCount;
```

Biểu thức chính quy ở đây kiểm tra **hình thức chuỗi**, chưa chứng minh rằng số nằm trong phạm vi `INTEGER` 64 bit. Cần thêm kiểm soát miền giá trị và ngữ nghĩa; chuỗi `'0042'` có thể vẫn cần giữ nguyên nếu nó là mã định danh.

### 7.2. Chuẩn hóa dữ liệu chuỗi trước khi so sánh

```cypher
WITH '  Lan@Example.Com  ' AS rawEmail
RETURN toLower(trim(rawEmail)) AS normalizedEmail;
```

Việc đưa email về chữ thường trong ví dụ là quy ước đơn giản cho tìm kiếm hoặc khớp tài khoản; hệ thống thực cần xác định chính sách chuẩn hóa theo nghiệp vụ. Cũng cần thống nhất cách xử lý Unicode, khoảng trắng và dấu tiếng Việt nếu dữ liệu nguồn đa dạng.

## 8. Dùng kiểu dữ liệu đúng khi truyền tham số

Trong truy vấn tham số hóa, `$age`, `$active` và `$name` là các giá trị do ứng dụng truyền, không phải chuỗi được ghép thẳng vào câu Cypher.

```cypher
CREATE (u:User {
  userId: $userId,
  name: $name,
  age: $age,
  active: $active
})
RETURN u.userId, u.name, u.age, u.active;
```

Tham số mong đợi:

| Tên tham số | Giá trị minh họa | Kiểu cần truyền |
| --- | --- | --- |
| `userId` | `'U-015'` | `STRING` |
| `name` | `'Ngọc'` | `STRING` |
| `age` | `24` | `INTEGER` |
| `active` | `true` | `BOOLEAN` |

Với **Java Driver**, sử dụng kiểu Java tương ứng khi đưa giá trị vào map tham số (ví dụ `String`, `long`/`Long`, `double`/`Double`, `boolean`/`Boolean`). Với **Spring Data Neo4j**, định nghĩa kiểu trường entity theo ý nghĩa dữ liệu và kiểm tra mapping khi đọc/ghi. Nếu đầu vào HTTP cung cấp `"24"` hay `"true"` dưới dạng chuỗi, nên xác thực/chuyển đổi ở tầng ứng dụng hoặc Cypher một cách rõ ràng.

Ví dụ lọc với tham số số và luận lý:

```cypher
MATCH (p:Product)
WHERE p.priceVnd >= $minimumPrice
  AND p.active = $activeOnly
RETURN p.productCode, p.priceVnd
ORDER BY p.priceVnd;
```

Nếu muốn lấy cả sản phẩm chưa kích hoạt thì cần định nghĩa rõ ý nghĩa tham số lọc thay vì dùng `$activeOnly = false` như một tín hiệu tự động bỏ qua điều kiện. Tách biệt “chỉ sản phẩm đang hoạt động” và “lọc theo trạng thái false” sẽ tránh sai lệch kết quả.

## 9. Những nhầm lẫn thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `'10'` cộng với số gây lỗi hoặc không ra phép tính mong muốn | `'10'` là chuỗi | Chuyển bằng `toIntegerOrNull()` / `toFloatOrNull()` trước phép toán |
| Giá `'90'` và `'100'` được so sánh như văn bản | Dữ liệu lưu nhầm `STRING` | Chuẩn hóa thuộc tính thành kiểu số |
| `'true'` được dùng như `BOOLEAN` | Chuỗi và giá trị luận lý khác kiểu | Truyền `true` hoặc chuyển đổi rõ ràng |
| Kết quả chia `7 / 2` là `3` | Hai toán hạng đều là số nguyên | Dùng `7 / 2.0` nếu cần kết quả thập phân |
| `0.1 + 0.2` sai khác rất nhỏ với `0.3` | Sai số dấu phẩy động | So sánh có dung sai hoặc dùng số nguyên theo đơn vị phù hợp |
| `WHERE n.flag = null` không tìm dữ liệu thiếu | So sánh với `null` không ra `true` | Dùng `n.flag IS NULL` |
| Dùng `coalesce(toIntegerOrNull(text), 0)` làm mọi lỗi trở thành 0 | Giá trị mặc định che giấu lỗi nhập liệu | Kiểm tra, ghi nhận hoặc loại bản ghi sai |
| `SET n.count = toIntegerOrNull('bad')` làm mất thuộc tính cũ | Gán `null` xóa property | Kiểm tra chuyển đổi thành công trước khi `SET` |
| Mã `'0007'` biến thành `7` | Chuyển mã định danh sang `INTEGER` | Lưu mã dạng `STRING` |
| Tìm kiếm chuỗi hoa/thường cho kết quả khác mong đợi | Chưa thống nhất quy tắc chuẩn hóa | Chuẩn hóa trường nhập và thiết kế tìm kiếm phù hợp |

## 10. Bài tập thực hành

### Bài tập 1 — Nhận biết literal

Xác định kiểu của các giá trị: `'42'`, `42`, `42.0`, `false`, `'false'`, `''` và `null`.

**Gợi ý:** đặt các giá trị vào câu `RETURN`, đối chiếu bằng `valueType()` nếu phiên bản hỗ trợ; nhớ `null` biểu thị không có giá trị xác định.

### Bài tập 2 — Xử lý giá trị nhập từ API

Cho đầu vào:

```cypher
WITH {
  name: '  Khoa  ',
  age: '31',
  score: '8.75',
  subscribed: 'true'
} AS request
RETURN request;
```

Hãy trả về bốn trường đã chuẩn hóa: `name` bỏ khoảng trắng thừa, `age` dạng số nguyên, `score` dạng số thực và `subscribed` dạng boolean.

**Đáp án tham khảo:**

```cypher
WITH {
  name: '  Khoa  ',
  age: '31',
  score: '8.75',
  subscribed: 'true'
} AS request
RETURN
  trim(request.name) AS name,
  toIntegerOrNull(request.age) AS age,
  toFloatOrNull(request.score) AS score,
  toBooleanOrNull(request.subscribed) AS subscribed;
```

### Bài tập 3 — Tính phần trăm đúng kiểu

Với `completed = 13` và `total = 20`, trả về tỷ lệ hoàn thành dưới dạng phần trăm số thực.

**Đáp án tham khảo:**

```cypher
WITH 13 AS completed, 20 AS total
RETURN 100.0 * completed / total AS percentCompleted;
```

Kết quả là `65.0`. Với dữ liệu tổng quát, phải xử lý `total = 0` trước khi chia.

### Bài tập 4 — Phân biệt thiếu trạng thái và trạng thái false

Một node `User` có thể có `emailVerified = true`, `emailVerified = false` hoặc không có property `emailVerified`. Hãy trả về nhãn `'Đã xác minh'`, `'Chưa xác minh'` hoặc `'Không rõ'`.

**Đáp án tham khảo:**

```cypher
MATCH (u:User)
RETURN
  u.userId,
  CASE
    WHEN u.emailVerified = true THEN 'Đã xác minh'
    WHEN u.emailVerified = false THEN 'Chưa xác minh'
    ELSE 'Không rõ'
  END AS verificationLabel;
```

## 11. Checklist khi dùng STRING, INTEGER, FLOAT và BOOLEAN

Trước khi lưu dữ liệu vào Neo4j, tự trả lời:

1. Thuộc tính là mã định danh hay đại lượng tính toán? Có cần giữ số 0 đầu không?
2. Số có phần thập phân hay không? Có yêu cầu chính xác tuyệt đối như tiền tệ không?
3. Trạng thái có đúng hai giá trị hay cần phân biệt cả “chưa biết”?
4. Dữ liệu đầu vào đang là chuỗi hay đã được Java/JSON truyền đúng kiểu?
5. Chuyển đổi thất bại sẽ bị loại, ghi log, báo lỗi hay nhận giá trị mặc định?
6. Dùng `SET` với kết quả chuyển đổi có thể là `null` liệu có vô tình xóa property cũ?
7. Điều kiện so sánh chuỗi đã quy định cách xử lý chữ hoa/thường và Unicode chưa?
8. Đã dùng tham số hóa và kiểm tra kết quả query khi tích hợp Java Driver/Spring Data Neo4j chưa?

---

**Ghi nhớ:** trong Cypher, `'42'`, `42` và `42.0` là các giá trị khác kiểu; `'false'` cũng khác `false`. Hãy chọn kiểu theo ý nghĩa nghiệp vụ, sử dụng hàm chuyển đổi rõ ràng, kiểm tra giá trị `null` trước khi ghi, và thống nhất kiểu dữ liệu giữa Neo4j với ứng dụng gọi truy vấn.

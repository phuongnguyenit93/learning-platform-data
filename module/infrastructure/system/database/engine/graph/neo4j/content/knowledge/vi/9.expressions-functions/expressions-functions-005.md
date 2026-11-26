# Hàm số, làm tròn và chuyển đổi giữa các kiểu dữ liệu trong Cypher

Trong **property graph** của Neo4j, mỗi node và relationship có thể chứa các property kiểu số, chuỗi, Boolean hoặc thời gian. Một ứng dụng quản lý bán hàng có thể lưu đơn giá dưới dạng số nguyên, điểm đánh giá dưới dạng số thực, còn dữ liệu đọc từ CSV lại đến dưới dạng chuỗi. Khi truy vấn bằng **Cypher**, việc tính toán, làm tròn và chuyển đổi kiểu quyết định cả độ chính xác của kết quả lẫn khả năng lọc dữ liệu bằng index.

Bài học thuộc chương **Biểu thức và hàm** trong mô-đun **DATABASE_ENGINE_GRAPH_NEO4J**. Trọng tâm là các hàm số, quy tắc làm tròn, chuyển đổi giá trị giữa những kiểu thông dụng và cách áp dụng trên node, relationship. Những ví dụ cũng minh họa cách truyền tham số từ Java Driver, dùng kết quả trong Spring Data Neo4j và lưu ý khi xử lý dữ liệu nhập.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt kiểu `INTEGER` và `FLOAT` trong Cypher; nhận biết tác động của kiểu số đến phép chia và độ chính xác.
- Sử dụng `abs()`, `ceil()`, `floor()`, `round()`, `sign()`, `sqrt()` và các hàm toán học phù hợp.
- Giải thích vì sao **làm tròn**, **cắt phần thập phân** và **đổi kiểu sang số nguyên** là ba thao tác cần phân biệt.
- Chuyển đổi giữa số, chuỗi và Boolean bằng `toInteger()`, `toFloat()`, `toString()`, `toBoolean()`, đồng thời xử lý dữ liệu thiếu hoặc không hợp lệ.
- Kết hợp `CASE`, `coalesce()`, `IS NULL` với phép tính có thể gặp `null` hoặc mẫu số 0.
- Tính giá trị từ property của node và relationship, làm báo cáo tổng hợp và kiểm tra dữ liệu nhập từ CSV.
- Viết truy vấn có tham số, ánh xạ kết quả trong Java Driver và cân nhắc chiến lược lưu trữ tiền tệ, làm tròn và tối ưu index.

## 2. Chuẩn bị dữ liệu đồ thị thực hành

Các ví dụ bắt đầu bằng `RETURN` hoặc `WITH` có thể chạy riêng. Để thực hành những truy vấn có `MATCH`, hãy khởi tạo đồ thị trong **database dành cho học tập**, không sử dụng dữ liệu sản xuất.

~~~cypher
MERGE (an:NumericDemoCustomer {customerId: 'NC-001'})
SET an.name = 'An', an.active = true

MERGE (binh:NumericDemoCustomer {customerId: 'NC-002'})
SET binh.name = 'Bình', binh.active = false

MERGE (chi:NumericDemoCustomer {customerId: 'NC-003'})
SET chi.name = 'Chi', chi.active = true

MERGE (book:NumericDemoProduct {sku: 'NP-001'})
SET book.name = 'Sách Cypher',
    book.priceVnd = 320000,
    book.stock = 12,
    book.rating = 4.37

MERGE (course:NumericDemoProduct {sku: 'NP-002'})
SET course.name = 'Khóa học Neo4j',
    course.priceVnd = 850000,
    course.stock = 4,
    course.rating = 4.85

MERGE (mouse:NumericDemoProduct {sku: 'NP-003'})
SET mouse.name = 'Chuột máy tính',
    mouse.priceVnd = 199000,
    mouse.stock = 0
REMOVE mouse.rating

MERGE (an)-[purchase1:NUMERIC_DEMO_BOUGHT]->(book)
SET purchase1.quantity = 2,
    purchase1.discountPercent = 10

MERGE (binh)-[purchase2:NUMERIC_DEMO_BOUGHT]->(course)
SET purchase2.quantity = 1
REMOVE purchase2.discountPercent;
~~~

Mô hình dữ liệu:

~~~mermaid
flowchart LR
    A["An:NumericDemoCustomer"] -->|"BOUGHT: quantity=2, discountPercent=10"| P1["Sách Cypher:NumericDemoProduct"]
    B["Bình:NumericDemoCustomer"] -->|"BOUGHT: quantity=1"| P2["Khóa học Neo4j:NumericDemoProduct"]
    C["Chi:NumericDemoCustomer"] 
    P3["Chuột máy tính:NumericDemoProduct"]
~~~

| Sản phẩm | `priceVnd` (INTEGER) | `stock` (INTEGER) | `rating` (FLOAT) |
| --- | ---: | ---: | ---: |
| Sách Cypher | 320.000 | 12 | 4,37 |
| Khóa học Neo4j | 850.000 | 4 | 4,85 |
| Chuột máy tính | 199.000 | 0 | *Không có property* |

Relationship `NUMERIC_DEMO_BOUGHT` chứa số lượng và phần trăm giảm giá. Giao dịch của Bình không có `discountPercent`, còn Chi không có relationship mua hàng. Hai trường hợp này sẽ giúp kiểm tra việc xử lý `null`.

## 3. Kiểu số trong Cypher và các toán tử cơ bản

### 3.1. INTEGER và FLOAT

Cypher phân biệt hai kiểu số quan trọng:

| Kiểu | Bản chất | Ví dụ | Ứng dụng |
| --- | --- | --- | --- |
| `INTEGER` | Số nguyên có dấu, thường được biểu diễn bằng 64 bit | `42`, `-7`, `320000` | Số lượng, mã số tăng dần, số tiền theo đơn vị nhỏ nhất |
| `FLOAT` | Số dấu phẩy động độ chính xác kép | `3.14`, `-0.25`, `4.85` | Tỉ lệ, đo lường, điểm đánh giá, phép tính có phần thập phân |

Một số phép toán minh họa:

~~~cypher
RETURN
  8 + 3 AS total,
  8 - 3 AS difference,
  8 * 3 AS product,
  8 / 3 AS integerDivision,
  8 / 3.0 AS floatingDivision,
  8 % 3 AS remainder,
  2 ^ 3 AS power;
~~~

Ở đây `integerDivision = 2`, `floatingDivision` xấp xỉ `2.6666666666666665`, còn `remainder = 2`. Khi cả hai toán hạng là số nguyên, phép chia số nguyên loại phần thập phân. Nếu muốn kết quả `FLOAT`, hãy dùng số thực ở ít nhất một vế hoặc chuyển kiểu tường minh.

~~~cypher
RETURN
  7 / 2 AS resultA,
  7 / 2.0 AS resultB,
  toFloat(7) / 2 AS resultC;
~~~

Kết quả là `3`, `3.5`, `3.5`.

### 3.2. Thứ tự ưu tiên và dấu ngoặc

~~~cypher
RETURN
  2 + 3 * 4 AS withoutParentheses,
  (2 + 3) * 4 AS withParentheses,
  100 * (1 - 0.15) AS afterDiscount;
~~~

Các kết quả tương ứng là `14`, `20` và khoảng `85.0`. Trong công thức nghiệp vụ, dấu ngoặc thường quan trọng hơn việc ghi nhớ mọi mức ưu tiên toán tử.

Hãy ưu tiên công thức có thể đọc ngay:

~~~cypher
WITH 320000 AS price, 2 AS quantity, 10 AS discountPercent
RETURN
  price * quantity AS subtotal,
  price * quantity * (100 - discountPercent) / 100 AS payableVnd;
~~~

Theo quy tắc làm tròn của phép chia nguyên, `payableVnd = 576000`. Với bài toán thanh toán thực tế, cần quy định rõ điều gì xảy ra khi phép chia không tạo ra số nguyên và đánh giá nguy cơ tràn số trong biểu thức trung gian.

### 3.3. Giới hạn kiểu số và độ chính xác

`INTEGER` 64 bit có miền hữu hạn. Tích `price * quantity * rate` có thể vượt miền số nguyên dù giá trị cuối cùng sau chia vẫn nhỏ. `FLOAT` có phạm vi giá trị rộng hơn nhưng không lưu chính xác mọi số thập phân; phép tính kiểu `0.1 + 0.2` không nên được dùng làm phép kiểm tra bằng tuyệt đối với `0.3`.

~~~cypher
RETURN
  0.1 + 0.2 AS computed,
  0.3 AS expected,
  abs((0.1 + 0.2) - 0.3) AS difference;
~~~

Với phép đo, có thể so sánh độ chênh lệch với sai số cho phép. Với dữ liệu tiền tệ, hãy chọn **đơn vị lưu trữ** và **quy tắc làm tròn** phù hợp trước khi thiết kế công thức.

## 4. Các hàm toán học thường dùng

### 4.1. Hàm trị tuyệt đối và dấu

| Hàm | Tác dụng | Ví dụ | Kết quả |
| --- | --- | --- | --- |
| `abs(x)` | Trị tuyệt đối | `abs(-12)` | `12` |
| `sign(x)` | Dấu của số: âm, 0 hoặc dương | `sign(-3.5)` | `-1` |

~~~cypher
RETURN
  abs(-120) AS distanceFromZero,
  sign(-8) AS negativeSign,
  sign(0) AS zeroSign,
  sign(8) AS positiveSign;
~~~

Kết quả lần lượt là `120`, `-1`, `0`, `1`. Trong nghiệp vụ, `abs` có thể dùng đo mức chênh lệch giữa tồn kho thực tế và dự kiến; `sign` giúp phân loại chênh lệch tăng, giảm hay không đổi.

### 4.2. Căn bậc hai, lũy thừa và logarit

| Biểu thức | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `sqrt(x)` | Căn bậc hai | `sqrt(81)` → `9.0` |
| `x ^ y` | Lũy thừa | `2 ^ 4` → `16.0` hoặc một giá trị số tương đương theo cách hiển thị |
| `log(x)` | Logarit tự nhiên | `log(1)` → `0.0` |
| `log10(x)` | Logarit cơ số 10 | `log10(1000)` → `3.0` |
| `exp(x)` | Hàm mũ cơ số `e` | `exp(0)` → `1.0` |

~~~cypher
RETURN
  sqrt(144) AS root,
  2 ^ 5 AS power,
  log10(100) AS baseTenLog,
  exp(0) AS expZero;
~~~

Những hàm này hữu ích trong tính toán trọng số, phân tích số liệu và mô hình chấm điểm trên đồ thị. Chú ý **miền xác định**: căn bậc hai của số âm hay logarit của số không dương không phải kết quả thực hợp lệ cho công thức nghiệp vụ. Nên kiểm tra điều kiện đầu vào bằng `CASE` và xử lý các giá trị đặc biệt theo chính sách ứng dụng.

### 4.3. Số ngẫu nhiên và các hàm lượng giác

`rand()` sinh một giá trị `FLOAT` giả ngẫu nhiên trong khoảng từ 0 (bao gồm) đến 1 (không bao gồm):

~~~cypher
RETURN rand() AS randomValue;
~~~

Kết quả thay đổi giữa những lần thực thi. Có thể dùng để tạo dữ liệu minh họa, nhưng không phù hợp làm khóa định danh ổn định hay nguồn ngẫu nhiên cho yêu cầu bảo mật.

Cypher còn có các hàm lượng giác, ví dụ `sin()` và `cos()`, khi xử lý dữ liệu góc hoặc tính toán khoa học:

~~~cypher
RETURN
  sin(0.0) AS sineZero,
  cos(0.0) AS cosineZero;
~~~

Hai kết quả là `0.0` và `1.0`. Với bài toán tính đường đi trên bản đồ hoặc khoảng cách không gian, nên cân nhắc kiểu point và các hàm không gian của Neo4j thay vì tự thay thế bằng công thức lượng giác đơn giản.

## 5. Làm tròn và kiểm soát chữ số thập phân

### 5.1. ceil(), floor(), round() khác nhau thế nào?

| Biểu thức | Ý nghĩa | Kết quả |
| --- | --- | --- |
| `ceil(3.2)` | Số nguyên nhỏ nhất không nhỏ hơn 3.2 | `4.0` |
| `floor(3.8)` | Số nguyên lớn nhất không lớn hơn 3.8 | `3.0` |
| `round(3.8)` | Làm tròn đến số nguyên gần nhất | `4.0` |
| `ceil(-3.2)` | Làm tròn theo hướng dương vô cực | `-3.0` |
| `floor(-3.2)` | Làm tròn theo hướng âm vô cực | `-4.0` |

Đặc biệt với số âm, `ceil` và `floor` không tương đương với thao tác “bỏ phần thập phân”:

~~~cypher
RETURN
  ceil(-3.8) AS roundedUp,
  floor(-3.8) AS roundedDown,
  toInteger(-3.8) AS truncated;
~~~

Kết quả: `roundedUp = -3.0`, `roundedDown = -4.0`, `truncated = -3`. `toInteger(-3.8)` cắt phần thập phân về phía 0, còn `floor(-3.8)` đi về phía âm vô cực.

### 5.2. round() với số chữ số thập phân

`round(number)` làm tròn về số nguyên gần nhất dưới dạng giá trị số; `round(number, precision)` cho phép chỉ định số chữ số sau dấu thập phân.

~~~cypher
RETURN
  round(4.376) AS zeroDecimalPlaces,
  round(4.376, 1) AS oneDecimalPlace,
  round(4.376, 2) AS twoDecimalPlaces;
~~~

Kết quả lần lượt là `4.0`, `4.4`, `4.38`.

Áp dụng trên điểm đánh giá:

~~~cypher
MATCH (p:NumericDemoProduct)
RETURN
  p.sku,
  p.name,
  p.rating AS exactStoredRating,
  round(p.rating, 1) AS displayedRating
ORDER BY p.sku;
~~~

Sách Cypher có `displayedRating = 4.4`, Khóa học Neo4j có `displayedRating` xấp xỉ `4.9` theo quy tắc làm tròn và biểu diễn số thực, còn Chuột máy tính có `null` do thiếu property `rating`.

**Lưu ý về dữ liệu chính xác ở biên:** các giá trị có chữ số thập phân `5` ở vị trí cần cắt có thể chịu ảnh hưởng của *rounding mode* và cách biểu diễn `FLOAT`. Không nên suy diễn quy tắc làm tròn số tiền từ các ví dụ không nằm ở biên.

### 5.3. Chế độ làm tròn (rounding mode)

Các phiên bản Cypher hiện đại hỗ trợ dạng `round(value, precision, mode)` để chỉ định chế độ xử lý, chẳng hạn `HALF_UP` hoặc `HALF_EVEN` dưới dạng giá trị chuỗi. Ví dụ:

~~~cypher
RETURN
  round(2.5, 0, 'HALF_UP') AS halfUp,
  round(2.5, 0, 'HALF_EVEN') AS halfEven;
~~~

Trong trường hợp này, `HALF_UP` cho kết quả `3.0` và `HALF_EVEN` cho kết quả `2.0`. `HALF_EVEN` ưu tiên chữ số chẵn ở vị trí được làm tròn khi nằm đúng giữa hai giá trị; đây là quy tắc thường dùng để giảm sai lệch tích lũy trong một số phép thống kê.

Không có một quy tắc phù hợp cho mọi nghiệp vụ. Hệ thống tính thuế, ngân hàng, kế toán hoặc điểm học tập có thể yêu cầu quy tắc khác nhau. Hãy xác định quy tắc trước, kiểm thử giá trị nằm đúng tại điểm giữa và đối chiếu chức năng với **phiên bản Neo4j đang sử dụng**.

### 5.4. Làm tròn không đồng nghĩa với đổi kiểu

~~~cypher
RETURN
  toInteger(3.9) AS truncatePositive,
  toInteger(-3.9) AS truncateNegative,
  round(3.9) AS roundPositive,
  floor(3.9) AS floorPositive,
  ceil(3.1) AS ceilPositive;
~~~

Kết quả: `3`, `-3`, `4.0`, `3.0`, `4.0`.

- `toInteger(x)` lấy phần nguyên theo hướng 0 đối với giá trị số thực thông thường.
- `round(x)` lấy giá trị gần nhất theo quy tắc làm tròn.
- `floor(x)` luôn theo hướng âm vô cực.
- `ceil(x)` luôn theo hướng dương vô cực.

Nếu API yêu cầu **INTEGER sau khi làm tròn**, có thể viết `toInteger(round(x, 0))`; cần bảo đảm kết quả sau làm tròn vẫn thuộc miền kiểu số nguyên.

### 5.5. Ví dụ thực tế: số hộp cần dùng

Giả sử một thùng chứa tối đa 6 sản phẩm. Để xếp hết 17 sản phẩm:

~~~cypher
WITH 17 AS itemCount, 6 AS capacity
RETURN
  toFloat(itemCount) / capacity AS rawBoxes,
  toInteger(ceil(toFloat(itemCount) / capacity)) AS requiredBoxes;
~~~

Kết quả khoảng `2.8333333333333335` thùng và **3 thùng** phải chuẩn bị. `ceil` phù hợp khi không được thiếu sức chứa. Nếu số lượng hoặc sức chứa có thể bằng 0/không có, hãy bổ sung kiểm tra điều kiện trước phép chia.

### 5.6. Phân biệt dữ liệu lưu trữ và dữ liệu trình bày

Nếu `rating = 4.376`, hiển thị `round(rating, 1) = 4.4` là hợp lý cho giao diện. Tuy nhiên, việc **ghi đè** `rating` thành `4.4` sẽ làm mất thông tin cần thiết cho những phép tổng hợp chính xác hơn.

Nên:

~~~cypher
MATCH (p:NumericDemoProduct)
RETURN
  p.name,
  p.rating AS storedRating,
  round(p.rating, 1) AS ratingForDisplay;
~~~

Chỉ cập nhật property đã làm tròn khi nghiệp vụ thực sự yêu cầu thay đổi dữ liệu lưu trữ.

## 6. Chuyển đổi giữa các kiểu dữ liệu

### 6.1. Các hàm chuyển đổi thường gặp

| Hàm | Chuyển sang | Ví dụ | Kết quả |
| --- | --- | --- | --- |
| `toInteger(x)` | `INTEGER` | `toInteger('42')` | `42` |
| `toFloat(x)` | `FLOAT` | `toFloat('3.75')` | `3.75` |
| `toString(x)` | `STRING` | `toString(42)` | `'42'` |
| `toBoolean(x)` | `BOOLEAN` | `toBoolean('true')` | `true` |

~~~cypher
RETURN
  toInteger('120') AS quantity,
  toFloat('4.25') AS score,
  toString(320000) AS priceText,
  toBoolean('false') AS disabled;
~~~

Kết quả có các kiểu tương ứng: `INTEGER`, `FLOAT`, `STRING` và `BOOLEAN`. Với dữ liệu nhập từ CSV, đây là các hàm đặc biệt quan trọng vì giá trị cột đầu vào thường được đọc dưới dạng chuỗi.

### 6.2. Chuyển từ chuỗi sang số

~~~cypher
RETURN
  toInteger('320000') AS priceVnd,
  toFloat('4.85') AS rating,
  toInteger('007') AS sequenceNumber,
  toFloat('2') AS decimalNumber;
~~~

Kết quả lần lượt là `320000`, `4.85`, `7` và `2.0`. Chuyển mã `'007'` sang số làm mất số 0 đầu; nếu `'007'` là **mã định danh** thay vì số lượng, hãy lưu dưới dạng `STRING`.

Chuỗi số thập phân nên dùng dấu **chấm** theo dạng số mà trình phân tích của Cypher chấp nhận. Không được giả định `'1,25'` hoặc `'1.250,00'` được hiểu theo mọi quy ước ngôn ngữ; nên chuẩn hóa và xác thực trước.

Ví dụ có khoảng trắng thừa:

~~~cypher
WITH '   320000   ' AS rawPrice
RETURN
  toInteger(trim(rawPrice)) AS normalizedPriceVnd;
~~~

Kết quả `320000`. `trim()` xử lý khoảng trắng đầu/cuối; nếu dữ liệu có dấu phân tách hàng nghìn hoặc ký hiệu tiền tệ, cần thêm quy tắc xử lý phù hợp.

### 6.3. Chuyển từ FLOAT sang INTEGER

~~~cypher
RETURN
  toInteger(3.9) AS positive,
  toInteger(-3.9) AS negative,
  toInteger(round(3.9)) AS roundThenConvert;
~~~

Kết quả `positive = 3`, `negative = -3` và `roundThenConvert = 4`. Tránh dùng `toInteger()` để “làm tròn” một khoản thanh toán: nó thực hiện chuyển kiểu với quy tắc khác `round()`.

### 6.4. Chuyển thành chuỗi cho giao diện và API

~~~cypher
WITH 320000 AS priceVnd, 12 AS stock
RETURN
  'Giá: ' || toString(priceVnd) || ' VND' AS priceLabel,
  'Tồn kho: ' || toString(stock) AS stockLabel;
~~~

Kết quả `Giá: 320000 VND` và `Tồn kho: 12`. `toString()` **không phải bộ định dạng tiền tệ theo locale**; việc chèn dấu phân tách hàng nghìn, đơn vị tiền hoặc định dạng cho từng ngôn ngữ nên được triển khai nhất quán ở tầng hiển thị.

Khi ứng dụng cần cả giá trị để tính và chuỗi để hiển thị, nên trả hai cột riêng thay vì biến property số thành chuỗi rồi dùng lại cho phép tính:

~~~cypher
MATCH (p:NumericDemoProduct)
RETURN
  p.sku,
  p.priceVnd AS numericPrice,
  toString(p.priceVnd) AS priceText
ORDER BY p.sku;
~~~

### 6.5. Chuyển chuỗi sang Boolean

~~~cypher
RETURN
  toBoolean('true') AS enabled,
  toBoolean('false') AS disabled;
~~~

Kết quả `true` và `false`. Nếu trường đầu vào dùng các giá trị như `'yes'`, `'no'`, `'1'` hoặc `'0'`, đừng mặc định rằng hàm `toBoolean()` sẽ hiểu đúng quy tắc nghiệp vụ. Hãy ánh xạ tường minh:

~~~cypher
WITH 'yes' AS rawFlag
WITH toLower(trim(rawFlag)) AS normalized
RETURN
  CASE
    WHEN normalized IN ['true', 'yes', '1'] THEN true
    WHEN normalized IN ['false', 'no', '0'] THEN false
    ELSE null
  END AS activeFlag;
~~~

Với `rawFlag = 'yes'`, kết quả là `true`. Trường hợp không nhận diện được trả `null` để tầng ứng dụng có thể báo lỗi dữ liệu hoặc yêu cầu bổ sung.

### 6.6. Những hàm chuyển đổi “OrNull”

Cypher có các hàm như `toIntegerOrNull()`, `toFloatOrNull()`, `toStringOrNull()` và `toBooleanOrNull()` để chuyển đổi theo cách trả `null` khi dữ liệu không thể chuyển thành kiểu đích, thay vì để một kiểu đầu vào không tương thích làm hỏng toàn bộ phép tính.

~~~cypher
RETURN
  toIntegerOrNull('120') AS validInteger,
  toIntegerOrNull('không phải số') AS invalidInteger,
  toFloatOrNull('4.25') AS validFloat,
  toFloatOrNull('không hợp lệ') AS invalidFloat;
~~~

Kết quả: `validInteger = 120`, `invalidInteger = null`, `validFloat = 4.25`, `invalidFloat = null`. Hàm chuyển đổi thông thường cũng có thể trả `null` cho **một số** chuỗi không hợp lệ; lợi ích của hậu tố `OrNull` nằm ở cách xử lý nhất quán hơn đối với các loại đầu vào không thể ép kiểu. Khi triển khai thực tế, hãy kiểm tra chữ ký và khả năng hỗ trợ của phiên bản Neo4j đang dùng.

**Không đánh đồng “chuyển đổi thất bại” với “giá trị không được cung cấp”.** Cả hai có thể dẫn đến `null`, nhưng ý nghĩa nghiệp vụ khác nhau. Có thể giữ chuỗi gốc và trả thêm nhãn lỗi để theo dõi chất lượng dữ liệu.

### 6.7. Null và phép chuyển kiểu

~~~cypher
RETURN
  toInteger(null) AS a,
  toFloat(null) AS b,
  toString(null) AS c,
  coalesce(toIntegerOrNull(null), 0) AS d;
~~~

Ba cột đầu là `null`, cột `d = 0`. Chỉ dùng `coalesce(..., 0)` nếu thiếu dữ liệu thực sự được phép diễn giải là số không. Trong trường hợp thiếu giá, **“chưa có giá”** không phải **“giá bằng 0”**.

### 6.8. Chuyển đổi sang kiểu thời gian

“Chuyển đổi kiểu” không chỉ giới hạn ở số và chuỗi. Nếu dữ liệu chứa thời gian ở dạng ISO 8601, Cypher còn có các hàm tạo giá trị thời gian:

~~~cypher
RETURN
  date('2026-11-25') AS orderDate,
  datetime('2026-11-25T09:00:00+07:00') AS orderTime,
  duration('P2D') AS shippingDuration;
~~~

`date(...)` tạo `DATE`, `datetime(...)` tạo giá trị ngày giờ có vùng giờ hoặc độ lệch giờ khi được cung cấp, còn `duration(...)` tạo khoảng thời gian. Đây là phép **phân tích dữ liệu theo kiểu đích**, không phải việc dùng `toInteger()` để xử lý chuỗi ngày. Dữ liệu thời gian thực tế cần thống nhất múi giờ và định dạng đầu vào.

## 7. Xử lý null, kiểu thiếu và phép tính không hợp lệ

### 7.1. Property không tồn tại tạo giá trị null

~~~cypher
MATCH (p:NumericDemoProduct)
RETURN
  p.sku,
  p.rating AS rating,
  round(p.rating, 1) AS roundedRating,
  coalesce(round(p.rating, 1), 0.0) AS ratingOrZero
ORDER BY p.sku;
~~~

Với Chuột máy tính, `rating` và `roundedRating` là `null`. `ratingOrZero` bằng `0.0` theo quy tắc dự phòng trong truy vấn, nhưng điều đó **không chứng minh** sản phẩm thực sự được đánh giá 0 sao. Khi cần phân biệt hai trường hợp, nên trả thêm `p.rating IS NULL AS missingRating`.

### 7.2. CASE để tránh chia cho 0

Một phép tính trung bình có thể có mẫu số 0 hoặc `null`:

~~~cypher
WITH 1000.0 AS total, 0 AS countItems
RETURN
  CASE
    WHEN countItems IS NULL OR countItems = 0 THEN null
    ELSE total / countItems
  END AS averagePerItem;
~~~

Truy vấn trả `null` theo quy tắc “chưa xác định được trung bình”. Việc ghi điều kiện bảo vệ trực tiếp trong `CASE` rõ ràng hơn so với giả định rằng một biểu thức `AND` sẽ luôn được đánh giá theo thứ tự nhất định.

### 7.3. CASE kiểm soát giá trị không hợp lệ trước căn bậc hai

~~~cypher
UNWIND [9.0, 0.0, -4.0, null] AS value
RETURN
  value,
  CASE
    WHEN value IS NULL OR value < 0 THEN null
    ELSE sqrt(value)
  END AS validRoot;
~~~

Kết quả: `sqrt(9) = 3.0`, `sqrt(0) = 0.0`; các đầu vào `-4.0` và `null` được trả `null` theo quy tắc do truy vấn xác định. Bạn có thể thay `null` bằng cột trạng thái riêng nếu cần giải thích lý do dữ liệu không hợp lệ cho người dùng.

### 7.4. Kiểm tra kiểu và dữ liệu bẩn

Một thuộc tính có thể bị ghi sai kiểu khi dữ liệu đến từ nhiều nguồn. Ví dụ, ứng dụng mong `priceVnd` là số nhưng dữ liệu nhập lại có chuỗi `'320000'`. Truy vấn như `WHERE p.priceVnd > 200000` không nên dựa vào việc Neo4j tự động đổi kiểu.

Hướng xử lý tốt là:

1. Kiểm tra và chuyển đổi giá trị trong quy trình nhập dữ liệu.
2. Lưu property số bằng kiểu số thật.
3. Dùng tham số với kiểu phù hợp khi truy vấn.
4. Duy trì ràng buộc hoặc quy tắc xác thực dữ liệu trong hệ thống.

Kiểu của property nên được thống nhất để truy vấn nhanh, kết quả dễ dự đoán và Java Driver/SDN ánh xạ ổn định.

## 8. Ví dụ tính toán trên node và relationship

### 8.1. Tính tổng tiền theo quantity và discountPercent

Giá sản phẩm nằm trên node `NumericDemoProduct`, còn số lượng và phần trăm giảm giá nằm trên relationship `NUMERIC_DEMO_BOUGHT`:

~~~cypher
MATCH (c:NumericDemoCustomer)-[r:NUMERIC_DEMO_BOUGHT]->(p:NumericDemoProduct)
WITH
  c, p, r,
  p.priceVnd * r.quantity AS subtotalVnd,
  coalesce(r.discountPercent, 0) AS discountPercent
RETURN
  c.name AS customer,
  p.name AS product,
  subtotalVnd,
  discountPercent,
  subtotalVnd * (100 - discountPercent) / 100 AS payableVnd
ORDER BY customer;
~~~

Kết quả mong đợi:

| Khách hàng | Thành tiền trước giảm giá | Giảm giá | Tiền phải trả |
| --- | ---: | ---: | ---: |
| An | 640.000 VND | 10% | 576.000 VND |
| Bình | 850.000 VND | 0% (mặc định theo quy tắc ví dụ) | 850.000 VND |

Nếu muốn tính bằng số thực rồi làm tròn đến VND nguyên, có thể dùng:

~~~cypher
MATCH (c:NumericDemoCustomer)-[r:NUMERIC_DEMO_BOUGHT]->(p:NumericDemoProduct)
WITH
  c, p,
  toFloat(p.priceVnd) * r.quantity *
    (1.0 - coalesce(r.discountPercent, 0) / 100.0) AS rawPayable
RETURN
  c.name AS customer,
  p.name AS product,
  rawPayable,
  toInteger(round(rawPayable, 0)) AS roundedPayableVnd
ORDER BY customer;
~~~

Trong ví dụ này, tiền được làm tròn đến đơn vị VND. **Khi áp dụng vào hệ thống thật**, yêu cầu kế toán có thể đòi hỏi quy tắc khác; dùng số thực dấu phẩy động và `round` không thay thế mô hình tính tiền chính xác. Nên lưu tiền theo đơn vị nhỏ nhất dạng số nguyên và áp dụng quy tắc tính toán/làm tròn thống nhất; với phép tính cần độ chính xác thập phân cao, có thể xử lý ở tầng Java bằng `BigDecimal`.

### 8.2. Làm tròn điểm đánh giá để trình bày

~~~cypher
MATCH (p:NumericDemoProduct)
WHERE p.rating IS NOT NULL
RETURN
  p.sku,
  p.name,
  p.rating AS rawRating,
  round(p.rating, 1) AS ratingOneDecimal
ORDER BY p.sku;
~~~

Chỉ trả về hai sản phẩm đã có điểm. Việc lọc bằng `IS NOT NULL` giúp dashboard tránh nhầm “không có đánh giá” với “điểm 0”.

### 8.3. OPTIONAL MATCH và số lượng giao dịch

~~~cypher
MATCH (c:NumericDemoCustomer)
OPTIONAL MATCH (c)-[r:NUMERIC_DEMO_BOUGHT]->(:NumericDemoProduct)
WITH
  c,
  count(r) AS purchaseRelations,
  sum(coalesce(r.quantity, 0)) AS purchasedUnits
RETURN
  c.name AS customer,
  purchaseRelations,
  purchasedUnits,
  CASE
    WHEN purchaseRelations = 0 THEN 'Chưa mua hàng'
    ELSE 'Đã mua hàng'
  END AS purchaseStatus
ORDER BY customer;
~~~

Chi có `purchaseRelations = 0` và `purchasedUnits = 0`. `count(r)` bỏ qua giá trị `null` của relationship không khớp; `coalesce(r.quantity, 0)` cho phép tổng hợp số lượng theo quy tắc minh họa.

**Phân biệt:** nếu một relationship tồn tại nhưng thiếu `quantity`, cách viết trên cũng tính số lượng của relationship đó là 0. Khi cần đánh giá chất lượng dữ liệu, trả thêm `sum(CASE WHEN r IS NOT NULL AND r.quantity IS NULL THEN 1 ELSE 0 END)` để đếm giao dịch thiếu số lượng.

## 9. Hàm tổng hợp và việc làm tròn kết quả

Các hàm tổng hợp `sum()`, `avg()`, `min()`, `max()` và `count()` thường đi cùng biểu thức số học trong báo cáo.

~~~cypher
MATCH (p:NumericDemoProduct)
RETURN
  count(*) AS productCount,
  sum(p.stock) AS totalStock,
  min(p.priceVnd) AS lowestPrice,
  max(p.priceVnd) AS highestPrice,
  round(avg(p.priceVnd), 2) AS averagePrice;
~~~

Kết quả mẫu: `productCount = 3`, `totalStock = 16`, `lowestPrice = 199000`, `highestPrice = 850000` và `averagePrice = 456333.33`.

### 9.1. Hàm tổng hợp và null

Đối với các tổng hợp trên biểu thức, dữ liệu `null` thường bị bỏ qua:

~~~cypher
UNWIND [4.0, 5.0, null] AS score
RETURN
  count(*) AS totalRows,
  count(score) AS recordedScores,
  avg(score) AS averageRecorded,
  avg(coalesce(score, 0.0)) AS averageMissingAsZero;
~~~

Kết quả:

- `totalRows = 3` vì có ba dòng;
- `recordedScores = 2` vì chỉ có hai điểm khác `null`;
- `averageRecorded = 4.5`;
- `averageMissingAsZero = 3.0`.

Vì vậy, không nên dùng `coalesce(score, 0)` trước `avg()` chỉ để tránh kết quả `null`: nó làm thay đổi mẫu số và ý nghĩa thống kê.

### 9.2. Thời điểm làm tròn có thể làm thay đổi tổng

Tính toán trên từng dòng rồi làm tròn **trước khi cộng** có thể khác với cộng tất cả giá trị rồi mới làm tròn:

~~~cypher
UNWIND [1.26, 1.26, 1.26] AS amount
RETURN
  sum(round(amount, 1)) AS sumOfRounded,
  round(sum(amount), 1) AS roundedSum;
~~~

Kết quả theo mục đích làm tròn một chữ số: `sumOfRounded = 3.9`, `roundedSum = 3.8` (các giá trị `FLOAT` có thể có biểu diễn dấu phẩy động gần các số này). Điều khác biệt phản ánh **thời điểm áp dụng quy tắc**.

Trong thanh toán hoặc báo cáo, cần quyết định việc làm tròn diễn ra theo **đơn vị giao dịch**, **dòng hàng** hay **tổng hóa đơn**. Hai phương án có thể tạo sai lệch tích lũy khi số lượng dòng lớn.

## 10. Nhập dữ liệu từ CSV và xác thực số

### 10.1. Vì sao dữ liệu CSV cần chuyển kiểu?

Khi dùng `LOAD CSV WITH HEADERS`, giá trị của các ô thường được đọc như **chuỗi**. Nếu lưu trực tiếp `row.price` vào property `priceVnd`, ứng dụng có nguy cơ nhận chuỗi `'320000'` thay cho số nguyên `320000`.

Ví dụ cấu trúc nhập (cần thay đường dẫn bằng CSV thực tế của môi trường):

~~~cypher
LOAD CSV WITH HEADERS FROM $csvUrl AS row
WITH
  trim(row.sku) AS sku,
  toIntegerOrNull(trim(row.priceVnd)) AS priceVnd
WHERE sku IS NOT NULL AND sku <> '' AND priceVnd IS NOT NULL
MERGE (p:NumericDemoProduct {sku: sku})
SET p.priceVnd = priceVnd
RETURN count(p) AS processedRows;
~~~

Trong truy vấn mẫu này, `$csvUrl` là tham số đường dẫn đã được môi trường Neo4j cho phép truy cập. Để dùng trong sản xuất, cần thêm chính sách xử lý dòng lỗi, kiểm soát đầu vào và quyền truy cập tệp/URL. Không nên im lặng bỏ mọi dòng có số không hợp lệ mà không ghi nhận để điều tra.

### 10.2. Phân loại chuỗi hợp lệ và không hợp lệ trước khi nhập

~~~cypher
UNWIND [
  {code: 'A', rawPrice: '320000'},
  {code: 'B', rawPrice: '850000'},
  {code: 'C', rawPrice: 'không rõ'},
  {code: 'D', rawPrice: ''}
] AS row
WITH row, trim(row.rawPrice) AS cleanText
WITH row,
     CASE
       WHEN cleanText = '' THEN null
       WHEN cleanText =~ '[0-9]+' THEN toIntegerOrNull(cleanText)
       ELSE null
     END AS parsedPrice
RETURN
  row.code AS code,
  row.rawPrice AS original,
  parsedPrice,
  CASE
    WHEN parsedPrice IS NULL THEN 'Cần xử lý'
    ELSE 'Hợp lệ'
  END AS dataStatus
ORDER BY code;
~~~

Kết quả `A` và `B` hợp lệ, `C` và `D` cần xử lý. Regex `[0-9]+` trong ví dụ chỉ chấp nhận **số nguyên không âm**, không chấp nhận dấu âm, dấu phân cách hàng nghìn, số thập phân hoặc ký hiệu tiền tệ. Nếu nghiệp vụ cho phép những dạng khác, hãy thay đổi quy tắc xác thực theo tài liệu định dạng đầu vào.

### 10.3. Phân biệt số 0 với giá trị thiếu

~~~cypher
UNWIND ['0', '', '15'] AS input
RETURN
  input,
  CASE
    WHEN trim(input) = '' THEN null
    ELSE toIntegerOrNull(trim(input))
  END AS quantity;
~~~

Kết quả `'0' → 0`, `'' → null` và `'15' → 15`. Khi báo cáo tồn kho, **không có số lượng** và **số lượng bằng 0** là hai trạng thái khác nhau.

## 11. Tích hợp với Java Driver và Spring Data Neo4j

### 11.1. Truyền tham số đúng kiểu

Ví dụ truy vấn dùng số nguyên VND, số thực giảm giá và mức giá tối thiểu:

~~~cypher
MATCH (p:NumericDemoProduct)
WHERE p.priceVnd >= $minPriceVnd
RETURN
  p.sku AS sku,
  p.priceVnd AS originalPriceVnd,
  toInteger(
    round(p.priceVnd * (1.0 - $discountRate), 0)
  ) AS discountedPriceVnd
ORDER BY sku;
~~~

Ở đây `$minPriceVnd` nên là số nguyên và `$discountRate` là số thực trong đoạn từ 0 đến 1. Ví dụ `minPriceVnd = 200000` và `discountRate = 0.1` sẽ chọn Sách Cypher và Khóa học Neo4j.

Truyền `'200000'` dưới dạng chuỗi có thể không phù hợp với điều kiện số `p.priceVnd >= $minPriceVnd`. Hãy chuyển dữ liệu về kiểu đúng **trước khi** gọi driver thay vì phụ thuộc ép kiểu ngầm.

### 11.2. Ví dụ Java Driver

Đoạn mã sau minh họa phần truy vấn và ánh xạ; giả sử đối tượng `Driver driver` đã được cấu hình và quản lý vòng đời ở lớp hạ tầng:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.Values;
import java.util.List;

record PriceQuote(String sku, long originalVnd, long discountedVnd) {}

try (Session session = driver.session()) {
    List<PriceQuote> prices = session.executeRead(tx ->
        tx.run(
            """
            MATCH (p:NumericDemoProduct)
            WHERE p.priceVnd >= $minPriceVnd
            RETURN
              p.sku AS sku,
              p.priceVnd AS originalVnd,
              toInteger(
                round(p.priceVnd * (1.0 - $discountRate), 0)
              ) AS discountedVnd
            ORDER BY sku
            """,
            Values.parameters(
                "minPriceVnd", 200000L,
                "discountRate", 0.10
            )
        ).list(row -> new PriceQuote(
            row.get("sku").asString(),
            row.get("originalVnd").asLong(),
            row.get("discountedVnd").asLong()
        ))
    );

    prices.forEach(System.out::println);
}
~~~

Đối tượng Java kiểu `long` phù hợp để truyền số nguyên 64 bit, còn `double` phù hợp cho số thực. Với trường có thể `null`, cần kiểm tra `Value.isNull()` trước khi gọi `asLong()` hoặc `asDouble()` và dùng kiểu Java có khả năng biểu diễn null khi cần.

Ví dụ trên minh họa kỹ thuật truy vấn, không thiết lập quy tắc kế toán chính thức. Nếu hệ thống tài chính phải tính chính xác đến đơn vị nhỏ nhất, hãy thiết kế phép tính với `BigDecimal` và quy tắc làm tròn xác định tại tầng nghiệp vụ; sau đó lưu giá trị kết quả đã kiểm tra dưới dạng `INTEGER` nếu phù hợp miền giá trị.

### 11.3. Lưu ý khi dùng Spring Data Neo4j

Trong Spring Data Neo4j, một entity có thể ánh xạ:

- `Long` / `long` đến property số nguyên, tùy yêu cầu nullable;
- `Double` / `double` đến property số thực;
- `String` đến property chuỗi;
- `Boolean` / `boolean` đến property Boolean.

Khi property có thể thiếu, nên cân nhắc kiểu hộp (ví dụ `Long`, `Double`, `Boolean`) thay vì kiểu nguyên thủy không thể biểu diễn `null`.

Với các phép tính sinh alias trong `RETURN`, nên định nghĩa projection/DTO với tên cột và kiểu thống nhất. Không nên để cùng một alias trả `INTEGER` ở nhánh này nhưng `STRING` ở nhánh khác nếu API mong kiểu cố định.

## 12. Tối ưu truy vấn và dữ liệu số

### 12.1. Lọc trên property số gốc

Khi tìm sản phẩm từ một mức giá tối thiểu, điều kiện trực tiếp trên property thường dễ được tối ưu bằng **range index** hơn một điều kiện bọc property trong phép tính:

~~~cypher
MATCH (p:NumericDemoProduct)
WHERE p.priceVnd >= $minPriceVnd
RETURN p.sku, p.name, p.priceVnd
ORDER BY p.priceVnd;
~~~

So sánh với điều kiện:

~~~cypher
MATCH (p:NumericDemoProduct)
WHERE round(toFloat(p.priceVnd) * 0.9, 0) >= $minPriceVnd
RETURN p.sku, p.name;
~~~

Điều kiện thứ hai yêu cầu tính biểu thức dựa trên property khi lọc, và khả năng dùng index có thể khác. Đây không phải lý do để bỏ phép tính cần thiết; thay vào đó, hãy thiết kế truy vấn và schema sao cho bộ tối ưu có cơ hội lọc sớm theo các điều kiện đơn giản.

### 12.2. Kiểm tra kế hoạch thực tế

Có thể tạo index phục vụ bài thực hành trong môi trường phù hợp:

~~~cypher
CREATE RANGE INDEX numeric_demo_price IF NOT EXISTS
FOR (p:NumericDemoProduct) ON (p.priceVnd);
~~~

Sau đó dùng `EXPLAIN` để xem kế hoạch dự kiến:

~~~cypher
EXPLAIN
MATCH (p:NumericDemoProduct)
WHERE p.priceVnd >= $minPriceVnd
RETURN p.sku, p.name, p.priceVnd;
~~~

`PROFILE` thực thi truy vấn và cung cấp thông tin như số dòng xử lý, số lần truy cập dữ liệu và thao tác index. Bộ tối ưu có thể chọn cách quét phù hợp cho một tập dữ liệu chỉ ba sản phẩm; cần thử trên dữ liệu đủ lớn và tham số đại diện trước khi kết luận.

### 12.3. Số liệu cần chuẩn hóa từ lúc nhập

Nếu `priceVnd` có lúc là `INTEGER` và có lúc là chuỗi, mỗi truy vấn phải xử lý chuyển kiểu và khó bảo đảm hiệu năng. Nếu có giá trị `FLOAT` được trộn vào một property vốn dùng số nguyên, kết quả tổng hợp hoặc điều kiện lọc cũng dễ bị hiểu sai.

Vì vậy, nên:

1. Xác định kiểu và đơn vị cho mỗi property trước khi nhập dữ liệu.
2. Chuyển kiểu và xác thực ở lớp ETL hoặc tầng ứng dụng.
3. Bảo vệ khóa định danh bằng constraint phù hợp; không dùng số đã làm tròn làm khóa duy nhất nếu có nguy cơ trùng.
4. Giữ giá trị gốc cần thiết và chỉ tạo cột đã làm tròn cho báo cáo.
5. Quan sát kế hoạch bằng `EXPLAIN` và `PROFILE` khi có vấn đề thực tế về hiệu năng.

## 13. Những lỗi thường gặp

| Lỗi / hiểu nhầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Tính `7 / 2` và mong nhận `3.5` | Phép chia nguyên không có phần thập phân | Dùng `7 / 2.0` hoặc `toFloat(7) / 2` |
| Dùng `toInteger(3.9)` để làm tròn | Kết quả là `3` | Dùng `round()`, rồi chuyển kiểu nếu cần |
| Nghĩ `ceil(-3.8) = -4` | Nhầm hướng làm tròn | `ceil(-3.8) = -3.0` |
| Làm tròn điểm đánh giá rồi ghi đè giá trị gốc | Mất độ chi tiết cần thiết để tính tiếp | Làm tròn trong `RETURN` để hiển thị |
| Dùng `coalesce(price, 0)` khi thiếu giá | Đánh đồng “chưa có giá” với “miễn phí” | Trả cột trạng thái hoặc giữ `null` |
| Cộng các số thực rồi kiểm tra `=` tuyệt đối | Sai số biểu diễn `FLOAT` | So sánh có dung sai nếu phù hợp; tính tiền bằng quy tắc chính xác |
| Chuyển `'007'` sang số để làm mã định danh | Mất các số 0 đầu | Giữ mã định danh dạng `STRING` |
| Truyền `'200000'` là chuỗi cho tham số số | Lọc sai hoặc không đúng kiểu | Truyền giá trị số từ ứng dụng |
| Xem `'1,25'` là số thực theo mọi môi trường | Không hợp lệ hoặc bị hiểu sai | Chuẩn hóa định dạng đầu vào và xác thực |
| Dùng `round(sum(x))` thay `sum(round(x))` không có chủ ý | Hai tổng có thể khác nhau | Xác định bước làm tròn theo nghiệp vụ |
| Không kiểm tra mẫu số 0 | Phép tính không có giá trị nghiệp vụ | Dùng `CASE` bảo vệ phép chia |
| Dùng `rand()` tạo mã khóa chính | Giá trị thay đổi, có thể trùng | Dùng phương pháp tạo định danh phù hợp |
| Không xử lý property thiếu trong Java | Chuyển `null` sang kiểu Java không nullable có thể lỗi | Kiểm tra `Value.isNull()` và hợp đồng DTO |
| Bọc property số trong nhiều hàm ở `WHERE` | Có thể giảm khả năng dùng index | Lọc trực tiếp trên property khi phù hợp |

## 14. Bài tập thực hành có đáp án

### Bài 1. Phép chia số nguyên và số thực

**Yêu cầu:** Cho `23` sản phẩm chia vào `5` hộp. Hãy tính số hộp cần thiết nếu một hộp tối đa 5 sản phẩm:

~~~cypher
WITH 23 AS totalItems, 5 AS capacity
RETURN
  totalItems / capacity AS integerQuotient,
  toFloat(totalItems) / capacity AS exactRatio,
  toInteger(ceil(toFloat(totalItems) / capacity)) AS boxesNeeded;
~~~

**Đáp án:** `integerQuotient = 4`, `exactRatio = 4.6`, `boxesNeeded = 5`. Để đủ sức chứa, dùng `ceil()` thay vì `floor()`.

### Bài 2. Phân biệt floor, ceil và toInteger với số âm

~~~cypher
RETURN
  floor(-4.2) AS a,
  ceil(-4.2) AS b,
  toInteger(-4.2) AS c;
~~~

**Đáp án:** `a = -5.0`, `b = -4.0`, `c = -4`. `floor` và `ceil` làm tròn theo trục số; `toInteger` cắt phần thập phân của số thực thông thường.

### Bài 3. Làm tròn điểm đánh giá

**Yêu cầu:** Trả về SKU, điểm đánh giá gốc và điểm đã làm tròn một chữ số. Chỉ lấy sản phẩm có điểm đánh giá:

~~~cypher
MATCH (p:NumericDemoProduct)
WHERE p.rating IS NOT NULL
RETURN
  p.sku,
  p.rating AS rawRating,
  round(p.rating, 1) AS displayRating
ORDER BY p.sku;
~~~

**Đáp án:** `NP-001` hiển thị khoảng `4.4`; `NP-002` hiển thị khoảng `4.9`; `NP-003` bị loại vì chưa có điểm.

### Bài 4. Kiểm tra số đầu vào

**Yêu cầu:** Chuyển chuỗi giá thành số nguyên, nhưng nếu chuỗi không hợp lệ thì trả `null` và nhãn lỗi:

~~~cypher
UNWIND ['320000', 'abc', '199000'] AS raw
WITH raw, toIntegerOrNull(raw) AS price
RETURN
  raw,
  price,
  CASE
    WHEN price IS NULL THEN 'Không hợp lệ'
    ELSE 'Hợp lệ'
  END AS status;
~~~

**Đáp án:** `'320000'` → `320000`, `'abc'` → `null`, `'199000'` → `199000`. Chuỗi không hợp lệ cần được theo dõi trong quy trình nhập thay vì tự đổi thành 0.

### Bài 5. Tính tiền sau giảm giá

**Yêu cầu:** Dùng node sản phẩm và relationship mua hàng. Với giao dịch thiếu phần trăm giảm giá, quy ước giảm giá bằng 0; trả kết quả VND nguyên:

~~~cypher
MATCH (c:NumericDemoCustomer)-[r:NUMERIC_DEMO_BOUGHT]->(p:NumericDemoProduct)
WITH
  c, p,
  toFloat(p.priceVnd) * r.quantity *
    (1.0 - coalesce(r.discountPercent, 0) / 100.0) AS amount
RETURN
  c.name AS customer,
  p.name AS product,
  toInteger(round(amount, 0)) AS payableVnd
ORDER BY customer;
~~~

**Đáp án:** An → `576000 VND`; Bình → `850000 VND`. Đây là công thức minh họa; khi triển khai thanh toán thật, cần thống nhất đơn vị, cách lưu tiền và quy tắc làm tròn.

### Bài 6. Phân biệt null với 0 trong tổng hợp

~~~cypher
UNWIND [2, 0, null, 5] AS quantity
RETURN
  count(*) AS rows,
  count(quantity) AS recordedValues,
  sum(quantity) AS totalQuantity,
  avg(quantity) AS averageRecorded;
~~~

**Đáp án:** `rows = 4`, `recordedValues = 3`, `totalQuantity = 7`, `averageRecorded` xấp xỉ `2.3333333333333335`. Số 0 được tính là giá trị hợp lệ; `null` không được tính vào `count(quantity)` và `avg(quantity)`.

### Bài 7. Báo cáo giá sản phẩm

**Yêu cầu:** Lấy giá thấp nhất, cao nhất và giá trung bình đã làm tròn đến VND nguyên:

~~~cypher
MATCH (p:NumericDemoProduct)
RETURN
  min(p.priceVnd) AS minimumVnd,
  max(p.priceVnd) AS maximumVnd,
  toInteger(round(avg(p.priceVnd), 0)) AS roundedAverageVnd;
~~~

**Đáp án:** `minimumVnd = 199000`, `maximumVnd = 850000` và `roundedAverageVnd = 456333`.

### Bài 8. Thiết kế giá trị trả về cho ứng dụng Java

**Yêu cầu:** API cần giá VND nguyên và điểm đánh giá một chữ số. Điểm chưa có phải trả kèm cờ xác định dữ liệu thiếu.

~~~cypher
MATCH (p:NumericDemoProduct)
RETURN
  p.sku AS sku,
  p.priceVnd AS priceVnd,
  round(p.rating, 1) AS rating,
  p.rating IS NULL AS ratingMissing
ORDER BY sku;
~~~

**Gợi ý đáp án:** Trong Java, ánh xạ `priceVnd` thành `long`/`Long`, `rating` thành `Double` nếu có thể `null` và `ratingMissing` thành `boolean`/`Boolean`. Không gán mặc định `rating = 0` chỉ để chuyển sang kiểu nguyên thủy.

### Bài 9. Chuyển cờ trạng thái từ dữ liệu nhập

**Yêu cầu:** Chuẩn hóa ba đầu vào `'YES'`, `'no'` và `'unknown'` sang Boolean:

~~~cypher
UNWIND ['YES', 'no', 'unknown'] AS raw
WITH raw, toLower(trim(raw)) AS flag
RETURN
  raw,
  CASE
    WHEN flag IN ['true', 'yes', '1'] THEN true
    WHEN flag IN ['false', 'no', '0'] THEN false
    ELSE null
  END AS active;
~~~

**Đáp án:** `YES → true`, `no → false`, `unknown → null`. Giá trị không nhận diện được được giữ ở trạng thái thiếu/không hợp lệ để xử lý theo quy trình.

## 15. Ghi nhớ

- `INTEGER` phù hợp số lượng và tiền theo đơn vị nhỏ nhất; `FLOAT` phù hợp phép đo và tỉ lệ nhưng có sai số biểu diễn, đặc biệt quan trọng với phép tính tài chính.
- `abs()`, `sign()`, `sqrt()` và các hàm toán học giúp tạo biểu thức trên property của node và relationship.
- `ceil()`, `floor()`, `round()` và `toInteger()` có ý nghĩa khác nhau. Với số âm và các giá trị nằm ở biên làm tròn, phải kiểm tra quy tắc chính xác.
- `toInteger()`, `toFloat()`, `toString()`, `toBoolean()` cùng các biến thể `OrNull` giúp chuyển kiểu; không nên nhầm dữ liệu chuyển đổi thất bại với số 0.
- `null` phải được xử lý tường minh bằng `IS NULL`, `CASE` hoặc `coalesce()` khi nghiệp vụ cho phép. Không tự động quy đổi điểm thiếu, giá thiếu hoặc số lượng thiếu về 0.
- Khi tổng hợp, **làm tròn từng dòng** và **làm tròn sau tổng** có thể cho kết quả khác nhau; hãy xác định bước làm tròn trước khi viết báo cáo.
- Từ Java Driver hoặc Spring Data Neo4j, truyền tham số đúng kiểu, kiểm tra kết quả nullable và giữ hợp đồng DTO ổn định.
- Để truy vấn đồ thị hiệu quả, lưu property số đúng kiểu, thiết kế index phù hợp và dùng `EXPLAIN` / `PROFILE` để kiểm chứng kế hoạch thực thi.

Nắm vững hàm số, làm tròn và chuyển đổi kiểu sẽ giúp bạn xây dựng truy vấn Cypher đúng ngữ nghĩa, nhất quán trên dữ liệu liên kết và dễ tích hợp vào ứng dụng Neo4j sử dụng Java.

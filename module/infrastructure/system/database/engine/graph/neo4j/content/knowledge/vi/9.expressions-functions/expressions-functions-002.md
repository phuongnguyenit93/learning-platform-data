# Xử lý null bằng kiểm tra tường minh và hàm coalesce trong Cypher

Trong Neo4j, một node có thể có property `email` nhưng node khác cùng label lại không có property đó. Một relationship có thể tồn tại nhưng chưa ghi `quantity`; cũng có trường hợp bản thân relationship không được tìm thấy. Những tình huống này rất phổ biến trong **property graph**, đặc biệt khi tích hợp dữ liệu từ nhiều nguồn, nhập CSV, truy vấn đường đi không bắt buộc và xây dựng ứng dụng bằng Java Driver hoặc Spring Data Neo4j.

Bài học thuộc chương **Biểu thức và hàm** của mô-đun **DATABASE_ENGINE_GRAPH_NEO4J**. Chủ đề chính là cách nhận biết giá trị thiếu trong Cypher bằng `IS NULL` / `IS NOT NULL`, cách áp dụng `coalesce()` để dùng giá trị dự phòng, và cách tránh những sai lệch nghiệp vụ do nhầm lẫn giữa `null`, `false`, `0` và chuỗi rỗng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích ý nghĩa `null` trong kết quả truy vấn Cypher và mối liên hệ với property không tồn tại trong đồ thị.
- Kiểm tra giá trị thiếu một cách tường minh bằng `IS NULL` và `IS NOT NULL`.
- Dự đoán tác động của `null` đến phép so sánh, phép toán số học và điều kiện `WHERE`.
- Sử dụng `coalesce(expression1, expression2, ...)` để lấy giá trị đầu tiên khác `null`.
- Phân biệt trường hợp cần giá trị mặc định với trường hợp phải bảo toàn trạng thái “chưa biết”.
- Kết hợp `OPTIONAL MATCH`, `CASE`, hàm tổng hợp và tham số truy vấn để xử lý dữ liệu thiếu an toàn.
- Tránh lỗi khi nhập dữ liệu, cập nhật property hoặc xử lý giá trị từ Neo4j trong ứng dụng Java.

## 2. Hiểu đúng về null trong property graph

### 2.1. Null là gì?

`null` biểu diễn trạng thái **không có giá trị** hoặc **không xác định**. Trong Cypher, chúng ta thường gặp `null` khi:

1. Truy cập property không tồn tại, ví dụ `c.email` trên node chưa có email.
2. Một `OPTIONAL MATCH` không tìm được node hoặc relationship phù hợp.
3. Một biểu thức phụ thuộc vào giá trị `null` và không thể tính được kết quả xác định.
4. Truy vấn hoặc dữ liệu đầu vào chủ động biểu diễn giá trị chưa có bằng `null`.

Ví dụ chạy độc lập:

~~~cypher
RETURN
  null AS missing,
  null + 5 AS unknownSum,
  'Neo4j' || null AS unknownText,
  null = 10 AS unknownComparison;
~~~

Cả bốn cột đều có giá trị `null`. Không nên xem `null` là một “số đặc biệt”, một chuỗi trống hoặc một giá trị Boolean mặc định.

**Đặc điểm lưu trữ của Neo4j:** property trên node/relationship không lưu giá trị `null` như một giá trị property thông thường. Gán `SET n.email = null` tương đương với việc xóa property `email` khỏi node `n`. Khi đọc một property không tồn tại, Cypher trả về `null`.

### 2.2. Phân biệt null, chuỗi rỗng, số không và false

| Giá trị | Ý nghĩa thường gặp | Có được `coalesce` thay thế không? |
| --- | --- | --- |
| `null` | Thiếu thông tin, không xác định | Có |
| `''` | Chuỗi có độ dài bằng 0 | Không |
| `'   '` | Chuỗi chỉ chứa khoảng trắng | Không |
| `0` | Giá trị số không | Không |
| `false` | Giá trị luận lý sai | Không |
| `[]` | Danh sách rỗng | Không |

Thử trực tiếp:

~~~cypher
RETURN
  coalesce(null, 'Dự phòng') AS a,
  coalesce('', 'Dự phòng') AS b,
  coalesce(0, 99) AS c,
  coalesce(false, true) AS d,
  coalesce([], ['x']) AS e;
~~~

Kết quả lần lượt là `'Dự phòng'`, `''`, `0`, `false` và `[]`. Hàm `coalesce` xử lý **giá trị `null`**, không kiểm tra giá trị rỗng theo nghĩa nghiệp vụ.

### 2.3. Dữ liệu đồ thị mẫu

Các truy vấn với `RETURN` và `UNWIND` trong bài có thể chạy độc lập. Để thực hành các truy vấn có `MATCH`, hãy tạo dữ liệu trong một **database thực hành riêng** bằng đoạn Cypher sau:

~~~cypher
MERGE (an:NullDemoCustomer {demoId: 'N-001'})
SET an.name = 'An',
    an.email = 'an@example.com',
    an.isVip = true

MERGE (binh:NullDemoCustomer {demoId: 'N-002'})
SET binh.name = 'Bình',
    binh.nickname = '',
    binh.isVip = false
REMOVE binh.email

MERGE (chi:NullDemoCustomer {demoId: 'N-003'})
SET chi.name = 'Chi'
REMOVE chi.email, chi.isVip

MERGE (book:NullDemoProduct {demoSku: 'N-P01'})
SET book.name = 'Sách Cypher', book.price = 320000
MERGE (course:NullDemoProduct {demoSku: 'N-P02'})
SET course.name = 'Khóa học Neo4j', course.price = 850000

MERGE (an)-[aOrder:NULL_DEMO_BOUGHT]->(book)
SET aOrder.quantity = 2
MERGE (binh)-[bOrder:NULL_DEMO_BOUGHT]->(course)
SET bOrder.quantity = 1;
~~~

Bộ dữ liệu dùng label/relationship riêng để dễ nhận diện:

| Khách hàng | `email` | `isVip` | Sản phẩm đã mua |
| --- | --- | --- | --- |
| An | `'an@example.com'` | `true` | Sách Cypher |
| Bình | Không có property | `false` | Khóa học Neo4j |
| Chi | Không có property | Không có property | Chưa mua |

Ngoài ra, `nickname` của Bình là `''`, tức property **có tồn tại** với giá trị chuỗi rỗng. Điều này khác với email của Bình và Chi, vốn không có property.

## 3. Kiểm tra tường minh bằng IS NULL và IS NOT NULL

### 3.1. Cú pháp

- `expression IS NULL` trả về `true` khi biểu thức có giá trị `null`.
- `expression IS NOT NULL` trả về `true` khi biểu thức có giá trị khác `null`.

~~~cypher
RETURN
  null IS NULL AS a,
  null IS NOT NULL AS b,
  0 IS NULL AS c,
  '' IS NOT NULL AS d,
  false IS NOT NULL AS e;
~~~

Kết quả: `a = true`, `b = false`, `c = false`, `d = true`, `e = true`.

Đây là cách kiểm tra giá trị thiếu đúng và trực tiếp. Đừng dùng phép so sánh thông thường như `= null` hay `<> null` để thay thế.

### 3.2. Tìm node thiếu hoặc có property

Tìm khách hàng chưa có email:

~~~cypher
MATCH (c:NullDemoCustomer)
WHERE c.email IS NULL
RETURN c.demoId, c.name
ORDER BY c.demoId;
~~~

Kết quả mẫu gồm Bình và Chi. Tìm khách hàng **có** email:

~~~cypher
MATCH (c:NullDemoCustomer)
WHERE c.email IS NOT NULL
RETURN c.demoId, c.name, c.email;
~~~

Kết quả mẫu là An. Nếu mục đích là kiểm tra **sự hiện diện** của property trong Cypher hiện đại, cách diễn đạt `c.email IS NOT NULL` dễ đọc và đúng mục tiêu.

Bạn cũng có thể kiểm tra một biểu thức thay vì một property đơn lẻ:

~~~cypher
MATCH (c:NullDemoCustomer)
WHERE trim(c.email) IS NOT NULL
RETURN c.name, c.email;
~~~

Tuy nhiên, nếu chỉ cần xác định property `email` có hay không, kiểm tra trực tiếp `c.email IS NOT NULL` sẽ rõ ý định hơn.

### 3.3. Không dùng = null hoặc <> null

Xét:

~~~cypher
RETURN
  null = null AS equality,
  null <> null AS inequality,
  5 = null AS compareWithNull,
  null IS NULL AS explicitCheck;
~~~

Ba cột đầu có kết quả `null`; chỉ `explicitCheck` là `true`. Đây là **logic ba giá trị**: khi không biết giá trị, phép so sánh bằng hoặc khác không thể khẳng định là đúng hay sai.

Vì thế, truy vấn sau không tìm được khách hàng thiếu email:

~~~cypher
// Sai mục đích: điều kiện không bao giờ trở thành true khi email là null.
MATCH (c:NullDemoCustomer)
WHERE c.email = null
RETURN c.name;
~~~

Hãy sửa thành `WHERE c.email IS NULL`.

### 3.4. Kiểm tra null trong mệnh đề WHERE

`WHERE` chỉ giữ dòng nếu điều kiện tính ra **`true`**. Dòng có điều kiện `false` hoặc `null` đều bị loại. Ví dụ:

~~~cypher
MATCH (c:NullDemoCustomer)
WHERE c.email <> 'blocked@example.com'
RETURN c.name, c.email;
~~~

Chỉ An được giữ lại. Bình và Chi không xuất hiện vì `null <> 'blocked@example.com'` là `null`, không phải `true`. Nếu yêu cầu nghiệp vụ là “email khác địa chỉ chặn **hoặc chưa có email**”, phải viết rõ:

~~~cypher
MATCH (c:NullDemoCustomer)
WHERE c.email IS NULL
   OR c.email <> 'blocked@example.com'
RETURN c.name, c.email
ORDER BY c.name;
~~~

Lúc này cả ba khách hàng đều thỏa. Dấu ngoặc có ý nghĩa khi bạn kết hợp thêm nhiều điều kiện `AND` / `OR`.

## 4. Logic ba giá trị và các biểu thức chịu ảnh hưởng của null

### 4.1. Tại sao không thể coi null là false?

| Biểu thức | Kết quả | Lý do |
| --- | --- | --- |
| `true AND null` | `null` | Chưa biết vế còn lại |
| `false AND null` | `false` | Đã có một vế sai |
| `true OR null` | `true` | Đã có một vế đúng |
| `false OR null` | `null` | Chưa biết có vế nào đúng hay không |
| `NOT null` | `null` | Phủ định điều chưa biết vẫn chưa biết |
| `null = null` | `null` | Không thể kết luận hai giá trị chưa biết bằng nhau |

~~~cypher
RETURN
  false AND null AS a,
  true AND null AS b,
  true OR null AS c,
  false OR null AS d,
  NOT null AS e;
~~~

Kết quả `a = false`, `b = null`, `c = true`, `d = null`, `e = null`.

Giả sử `c.isVip` chưa được ghi: điều kiện `WHERE NOT c.isVip` **không** mặc nhiên tìm thấy khách hàng đó, vì `NOT null` vẫn là `null`. Nếu muốn tìm người chắc chắn không phải VIP:

~~~cypher
MATCH (c:NullDemoCustomer)
WHERE c.isVip = false
RETURN c.name;
~~~

Kết quả chỉ có Bình. Nếu yêu cầu là “không phải VIP **hoặc chưa phân loại**”, hãy diễn đạt:

~~~cypher
MATCH (c:NullDemoCustomer)
WHERE c.isVip = false OR c.isVip IS NULL
RETURN c.name
ORDER BY c.name;
~~~

Kết quả là Bình và Chi. Việc gộp “không phải VIP” và “chưa rõ” là một lựa chọn nghiệp vụ; hai trạng thái vẫn có thể cần phân biệt để phân tích dữ liệu.

### 4.2. Tác động đến phép tính và nối chuỗi

Nếu thiếu một toán hạng, nhiều biểu thức sẽ trả `null`:

~~~cypher
RETURN
  100 + null AS total,
  100 * null AS amount,
  'Khách: ' || null AS label,
  100 > null AS comparison;
~~~

Muốn tính tổng tiền, hãy xác định *vì sao* giá trị bị thiếu. Ví dụ, phí vận chuyển không được ghi có thể có nghĩa “miễn phí” hoặc “chưa tính phí”, tùy thiết kế dữ liệu. Chỉ trong trường hợp đầu mới nên thay bằng `0`.

## 5. Hàm coalesce: chọn giá trị khác null đầu tiên

### 5.1. Cú pháp và cách hoạt động

`coalesce` nhận nhiều biểu thức và trả về **giá trị đầu tiên khác `null`**, xét từ trái sang phải:

~~~cypher
coalesce(expression1, expression2, ..., expressionN)
~~~

Ví dụ:

~~~cypher
RETURN
  coalesce(null, 'Email dự phòng') AS example1,
  coalesce(null, null, 'Chưa cung cấp') AS example2,
  coalesce(0, 99) AS example3,
  coalesce(false, true) AS example4,
  coalesce(null, null) AS example5;
~~~

Kết quả lần lượt là `'Email dự phòng'`, `'Chưa cung cấp'`, `0`, `false` và `null`.

Nếu **tất cả** đối số là `null`, kết quả vẫn là `null`. `coalesce` không tự tạo được giá trị có nghĩa nếu bạn không cung cấp giá trị dự phòng thích hợp.

### 5.2. Hiển thị thông tin mặc định

~~~cypher
MATCH (c:NullDemoCustomer)
RETURN
  c.name AS customer,
  c.email AS originalEmail,
  coalesce(c.email, 'Chưa cung cấp email') AS displayEmail
ORDER BY c.demoId;
~~~

| Khách hàng | `originalEmail` | `displayEmail` |
| --- | --- | --- |
| An | `'an@example.com'` | `'an@example.com'` |
| Bình | `null` | `'Chưa cung cấp email'` |
| Chi | `null` | `'Chưa cung cấp email'` |

Trong truy vấn này, `coalesce` chỉ biến đổi **giá trị trả về**, không tạo hay ghi property `email` trên node. Đây là cách tốt để định dạng dữ liệu cho giao diện mà vẫn bảo toàn thông tin gốc.

### 5.3. Nhiều nguồn thay thế theo thứ tự ưu tiên

Giả sử người dùng có `nickname`, `name` và mã `demoId`. Quy tắc hiển thị là: lấy nickname nếu có; nếu không, dùng tên; cuối cùng mới dùng mã.

~~~cypher
MATCH (c:NullDemoCustomer)
RETURN
  c.demoId,
  coalesce(c.nickname, c.name, c.demoId, 'Khách ẩn danh')
    AS displayName
ORDER BY c.demoId;
~~~

An được hiển thị là `An`, Chi là `Chi`, còn Bình được hiển thị thành **chuỗi rỗng** do `nickname = ''`. Đây là một trường hợp quan trọng: `coalesce` không đánh giá độ hữu dụng của dữ liệu, nó chỉ xem giá trị có phải `null` hay không.

Muốn coi nickname rỗng hoặc chỉ chứa khoảng trắng là chưa cung cấp, bạn có thể dùng `CASE`:

~~~cypher
MATCH (c:NullDemoCustomer)
RETURN
  c.demoId,
  CASE
    WHEN c.nickname IS NULL OR trim(c.nickname) = ''
      THEN coalesce(c.name, c.demoId)
    ELSE c.nickname
  END AS displayName
ORDER BY c.demoId;
~~~

Kết quả cả ba đều hiển thị tên An, Bình, Chi. Việc coi chuỗi rỗng là thiếu dữ liệu là **quy ước nghiệp vụ**, không phải hành vi mặc định của `coalesce`.

### 5.4. Coalesce với số và Boolean

~~~cypher
MATCH (c:NullDemoCustomer)
RETURN
  c.name,
  c.isVip AS rawVip,
  coalesce(c.isVip, false) AS vipAssumingMissingIsFalse
ORDER BY c.demoId;
~~~

Chi có `rawVip = null` nhưng `vipAssumingMissingIsFalse = false`. Chỉ áp dụng quy tắc này khi nghiệp vụ đã quy định “chưa phân loại = không VIP”. Nếu dữ liệu thiếu phải được điều tra, hãy giữ `null` và biểu diễn bằng nhãn “Chưa xác định”.

Với số, `coalesce(score, 0)` rất tiện cho một số phép cộng, nhưng có thể làm sai giá trị trung bình, số liệu thống kê hoặc thứ hạng nếu “chưa có điểm” khác “điểm bằng 0”.

Nên dùng các đối số dự phòng có kiểu dữ liệu nhất quán với nhau. Chẳng hạn, cột `price` dùng số thì giá trị dự phòng cũng nên là số; nếu muốn hiển thị chữ “Chưa có giá”, hãy tạo cột trình bày riêng.

### 5.5. Khi cần phân nhánh phức tạp, dùng CASE

`coalesce` phù hợp với câu hỏi “giá trị khác null đầu tiên là gì?”. `CASE` phù hợp khi cần phân loại nhiều trạng thái:

~~~cypher
MATCH (c:NullDemoCustomer)
RETURN
  c.name,
  CASE
    WHEN c.isVip IS NULL THEN 'Chưa phân loại'
    WHEN c.isVip = true THEN 'VIP'
    ELSE 'Thông thường'
  END AS customerType
ORDER BY c.demoId;
~~~

Kết quả: An → VIP; Bình → Thông thường; Chi → Chưa phân loại.

Đối với phép chia có mẫu số chưa biết hoặc bằng 0, một biểu thức `CASE` cũng thể hiện rõ chính sách xử lý:

~~~cypher
WITH 100.0 AS total, null AS itemCount
RETURN
  CASE
    WHEN itemCount IS NULL OR itemCount = 0 THEN null
    ELSE total / itemCount
  END AS averagePerItem;
~~~

Không tự động dùng `coalesce(itemCount, 0)` rồi thực hiện phép chia: nó vẫn có nguy cơ tạo mẫu số 0 và che giấu lý do dữ liệu thiếu.

## 6. Null sinh ra từ OPTIONAL MATCH

### 6.1. Mẫu quan hệ không bắt buộc

`MATCH` thông thường chỉ trả về các dòng khớp đồ thị. `OPTIONAL MATCH` cho phép giữ lại dòng từ phần truy vấn trước ngay cả khi mẫu quan hệ bổ sung không tồn tại; trong trường hợp đó, các biến chưa khớp sẽ có giá trị `null`.

~~~cypher
MATCH (c:NullDemoCustomer)
OPTIONAL MATCH (c)-[r:NULL_DEMO_BOUGHT]->(p:NullDemoProduct)
RETURN
  c.name AS customer,
  p.name AS rawProduct,
  coalesce(p.name, 'Chưa mua sản phẩm') AS displayProduct,
  r.quantity AS rawQuantity
ORDER BY c.demoId;
~~~

Với dữ liệu mẫu:

| Khách hàng | `rawProduct` | `displayProduct` | `rawQuantity` |
| --- | --- | --- | --- |
| An | `Sách Cypher` | `Sách Cypher` | `2` |
| Bình | `Khóa học Neo4j` | `Khóa học Neo4j` | `1` |
| Chi | `null` | `Chưa mua sản phẩm` | `null` |

Nếu chỉ dùng `MATCH (c)-[:NULL_DEMO_BOUGHT]->(p)`, Chi sẽ biến mất khỏi kết quả vì không có relationship phù hợp.

### 6.2. Phân biệt relationship không tồn tại và property thiếu

Hai trường hợp sau không tương đương:

1. `r IS NULL`: không tìm thấy relationship nào cho mẫu `OPTIONAL MATCH`.
2. `r.quantity IS NULL`: có thể không tìm thấy relationship, **hoặc** tìm thấy nhưng relationship thiếu property `quantity`.

Khi cần xác định một khách hàng chưa mua hàng, nên kiểm tra biến relationship:

~~~cypher
MATCH (c:NullDemoCustomer)
OPTIONAL MATCH (c)-[r:NULL_DEMO_BOUGHT]->(:NullDemoProduct)
WITH c, r
WHERE r IS NULL
RETURN c.demoId, c.name;
~~~

Kết quả là Chi. Còn dùng `WHERE r.quantity IS NULL` có thể tính cả quan hệ mua hàng tồn tại nhưng chưa điền số lượng.

### 6.3. Vị trí của WHERE có ảnh hưởng đến kết quả

So sánh hai truy vấn gần giống nhau:

~~~cypher
// Điều kiện là một phần của OPTIONAL MATCH:
// giữ đủ ba khách hàng, nhưng p chỉ được khớp nếu giá > 500000.
MATCH (c:NullDemoCustomer)
OPTIONAL MATCH (c)-[:NULL_DEMO_BOUGHT]->(p:NullDemoProduct)
WHERE p.price > 500000
RETURN c.name, coalesce(p.name, 'Không có sản phẩm giá cao') AS product
ORDER BY c.demoId;
~~~

An và Chi có `product = 'Không có sản phẩm giá cao'`, Bình có `product = 'Khóa học Neo4j'`.

~~~cypher
// Điều kiện được áp dụng SAU khi đã hoàn thành OPTIONAL MATCH:
// chỉ giữ dòng có p.price > 500000.
MATCH (c:NullDemoCustomer)
OPTIONAL MATCH (c)-[:NULL_DEMO_BOUGHT]->(p:NullDemoProduct)
WITH c, p
WHERE p.price > 500000
RETURN c.name, p.name;
~~~

Lần này chỉ còn Bình. Lý do: `p.price > 500000` cho `null` khi `p` không được ghép, nên dòng bị loại bởi `WHERE`.

Vì vậy cần quyết định rõ bạn muốn **giữ mọi khách hàng với thông tin tùy chọn** hay **chỉ giữ khách hàng thỏa điều kiện ở quan hệ tùy chọn**.

### 6.4. Tránh che giấu thiếu quan hệ bằng giá trị số 0

~~~cypher
MATCH (c:NullDemoCustomer)
OPTIONAL MATCH (c)-[r:NULL_DEMO_BOUGHT]->(:NullDemoProduct)
RETURN
  c.name,
  r.quantity AS recordedQuantity,
  coalesce(r.quantity, 0) AS quantityOrZero
ORDER BY c.demoId;
~~~

Đối với Chi, `quantityOrZero = 0` có thể là cách hiển thị phù hợp cho bảng “số lượng đã mua”. Nhưng giá trị đó cũng bằng 0 nếu **có** relationship mua hàng mà property `quantity` bị thiếu. Khi cần kiểm toán chất lượng dữ liệu, hãy giữ thêm `r IS NULL AS noPurchaseRelationship` để phân biệt hai nguồn gốc.

## 7. Null trong hàm tổng hợp và báo cáo

### 7.1. Đếm dòng và đếm giá trị hiện diện

`count(*)` đếm số dòng được chuyển đến phép tổng hợp. `count(expression)` chỉ đếm những dòng có biểu thức **khác `null`**.

~~~cypher
UNWIND [
  {score: 10},
  {score: 20},
  {}
] AS row
RETURN
  count(*) AS numberOfRows,
  count(row.score) AS numberOfRecordedScores;
~~~

Kết quả: `numberOfRows = 3`, `numberOfRecordedScores = 2`. Bản ghi thứ ba có mặt nhưng không có property `score`.

Đối với `OPTIONAL MATCH`, khác biệt này đặc biệt rõ:

~~~cypher
MATCH (c:NullDemoCustomer)
OPTIONAL MATCH (c)-[r:NULL_DEMO_BOUGHT]->(:NullDemoProduct)
RETURN
  c.name AS customer,
  count(*) AS preservedRows,
  count(r) AS purchaseRelationships
ORDER BY customer;
~~~

Chi có `preservedRows = 1` nhưng `purchaseRelationships = 0`: `OPTIONAL MATCH` giữ dòng của Chi với `r = null`. Khi báo cáo số lượng mối quan hệ thực có, `count(r)` mới phản ánh đúng ý nghĩa.

### 7.2. Coalesce có thể làm thay đổi mẫu số trung bình

~~~cypher
UNWIND [
  {score: 10},
  {score: 20},
  {}
] AS row
RETURN
  avg(row.score) AS averageOfRecorded,
  avg(coalesce(row.score, 0)) AS averageIncludingZero;
~~~

Kết quả tương ứng là `15.0` và `10.0`.

- `avg(row.score)` bỏ qua điểm thiếu: chỉ có hai điểm 10 và 20.
- `avg(coalesce(row.score, 0))` coi điểm thiếu là điểm 0: trung bình của ba điểm 10, 20 và 0.

Cả hai công thức đều có thể đúng trong những bài toán khác nhau. Cần quy định “không có điểm” có nghĩa “chưa chấm” hay “được 0 điểm” trước khi dùng `coalesce` trong thống kê.

Hàm tổng hợp `collect(expression)` cũng bỏ qua giá trị `null`. Nếu cần bảo toàn thông tin “có một dòng nhưng thiếu property”, hãy biểu diễn trạng thái đó thành một giá trị khác hoặc một cấu trúc map phù hợp trước khi tổng hợp.

## 8. Cập nhật dữ liệu và nhập dữ liệu thiếu

### 8.1. SET property = null sẽ xóa property

Đoạn sau minh họa cơ chế trên node thực hành:

~~~cypher
MATCH (c:NullDemoCustomer {demoId: 'N-001'})
SET c.email = null
RETURN c.name, c.email IS NULL AS emailMissing;
~~~

Kết quả `emailMissing = true`, bởi property `email` đã bị xóa khỏi An. **Nếu muốn giữ nguyên dữ liệu mẫu ban đầu cho các bài tập khác, đừng chạy đoạn cập nhật này**; hoặc khôi phục bằng:

~~~cypher
MATCH (c:NullDemoCustomer {demoId: 'N-001'})
SET c.email = 'an@example.com'
RETURN c.name, c.email;
~~~

Trong nghiệp vụ, cần phân biệt thao tác “xóa email đã lưu” với “không nhận được email mới nên không cập nhật gì”. Hai tình huống này không được tự động xử lý giống nhau.

### 8.2. Không dùng null làm khóa định danh trong MERGE

`MERGE` cần một mẫu node hoặc relationship có thể xác định được. Giá trị `null` trong property của mẫu `MERGE` gây lỗi vì không thể dùng nó để tìm hoặc tạo một thực thể có khóa phù hợp:

~~~cypher
// KHÔNG NÊN CHẠY: tham số $email = null sẽ khiến MERGE lỗi.
MERGE (c:NullDemoCustomer {email: $email})
RETURN c;
~~~

Thay vào đó, dùng khóa định danh **không null** và xử lý property tùy chọn riêng:

~~~cypher
MERGE (c:NullDemoCustomer {demoId: $demoId})
SET c.email = $email
RETURN c.demoId, c.email;
~~~

Truy vấn trên có thể **xóa** `email` nếu tham số `$email` mang giá trị `null`. Nếu `null` trong yêu cầu có nghĩa là “không cập nhật email”, cần quy tắc cập nhật khác, ví dụ:

~~~cypher
MATCH (c:NullDemoCustomer {demoId: $demoId})
SET c.email = coalesce($email, c.email)
RETURN c.demoId, c.email;
~~~

Biểu thức này giữ email hiện có khi `$email` là `null`. Tuy nhiên, khi ứng dụng cần cho phép **xóa email chủ động**, phải tách lệnh xóa khỏi lệnh bỏ qua cập nhật; không thể chỉ dùng một giá trị `null` cho cả hai ý định.

### 8.3. Chuỗi rỗng khi nhập CSV không nhất thiết là null

Các nguồn dữ liệu khác nhau có thể biểu diễn giá trị thiếu bằng chuỗi rỗng hoặc khoảng trắng. Khi nhập dữ liệu, cần chuẩn hóa theo quy tắc:

~~~cypher
WITH {email: '   '} AS row
WITH
  CASE
    WHEN row.email IS NULL OR trim(row.email) = ''
      THEN null
    ELSE trim(row.email)
  END AS normalizedEmail
RETURN normalizedEmail, normalizedEmail IS NULL AS isMissing;
~~~

Kết quả: `normalizedEmail = null` và `isMissing = true`.

Với `LOAD CSV WITH HEADERS`, giá trị từ cột dữ liệu là chuỗi; khi một ô bị bỏ trống, cần kiểm tra và chuẩn hóa thay vì mặc định nó luôn là `null`. Nếu ứng dụng yêu cầu phân biệt “ô trống” với “không có trường”, quy tắc chuyển đổi phải được quyết định trước khi nhập.

## 9. Sử dụng null và coalesce trong ứng dụng Java

### 9.1. Viết Cypher với tham số

Trong Java Driver hoặc câu truy vấn tùy chỉnh của Spring Data Neo4j, nên truyền giá trị bằng tham số:

~~~cypher
MATCH (c:NullDemoCustomer {demoId: $demoId})
RETURN
  c.email AS rawEmail,
  coalesce(c.email, $fallbackEmail) AS displayEmail,
  c.email IS NULL AS missingEmail;
~~~

Nếu `$demoId = 'N-002'` và `$fallbackEmail = 'Chưa cung cấp'`, kết quả có:

- `rawEmail = null`.
- `displayEmail = 'Chưa cung cấp'`.
- `missingEmail = true`.

Cách này giữ cả thông tin thô và giá trị dùng để hiển thị. Không nên để thông báo giao diện như `'Chưa cung cấp'` thay thế property thật trong cơ sở dữ liệu, vì về sau khó phân biệt dữ liệu nhập và chuỗi trình bày.

### 9.2. Xử lý giá trị nullable trong Neo4j Java Driver

Đoạn Java minh họa phần xử lý kết quả; giả sử đối tượng `Driver driver` đã được cấu hình và dữ liệu mẫu còn nguyên:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.Values;

// driver được khởi tạo và quản lý vòng đời ở tầng cấu hình ứng dụng.
try (Session session = driver.session()) {
    var row = session.executeRead(tx ->
        tx.run(
            """
            MATCH (c:NullDemoCustomer {demoId: $demoId})
            RETURN
              c.email AS rawEmail,
              coalesce(c.email, $fallback) AS displayEmail
            """,
            Values.parameters(
                "demoId", "N-002",
                "fallback", "Chưa cung cấp"
            )
        ).single()
    );

    boolean emailMissing = row.get("rawEmail").isNull();
    String label = row.get("displayEmail").asString();

    System.out.println(emailMissing); // true
    System.out.println(label);        // Chưa cung cấp
}
~~~

Khi trường trả về có thể `null`, hãy kiểm tra bằng `Value.isNull()` trước khi chuyển sang kiểu Java cụ thể. `coalesce` giúp tạo cột chuỗi dự phòng khi bạn đã xác định hợp lệ quy tắc thay thế. Ví dụ trên dùng `single()` vì truy vấn dự kiến trả đúng một dòng; nếu không tìm thấy hoặc trả nhiều dòng, ứng dụng cần xử lý theo hợp đồng truy vấn.

Với Spring Data Neo4j, nguyên tắc tương tự: cân nhắc field thực sự có thể thiếu, phép ánh xạ kiểu dữ liệu trong entity/projection, và sử dụng tham số thay vì ghép dữ liệu người dùng trực tiếp vào Cypher.

## 10. Hiệu năng, tính đúng đắn và cách chọn biểu thức

### 10.1. Ưu tiên diễn đạt đúng ý định

Khi cần tìm node có email cụ thể:

~~~cypher
MATCH (c:NullDemoCustomer)
WHERE c.email = $email
RETURN c.demoId, c.name;
~~~

Điều kiện trực tiếp trên property thường dễ phân tích và có thể phù hợp với index hơn điều kiện dùng hàm:

~~~cypher
MATCH (c:NullDemoCustomer)
WHERE coalesce(c.email, '') = $email
RETURN c.demoId, c.name;
~~~

Hai truy vấn cũng không nhất thiết tương đương: truy vấn thứ hai coi email thiếu như chuỗi rỗng. Nếu giá trị `$email = ''`, nó có thể trả cả node không có email, trong khi truy vấn thứ nhất chỉ khớp với node thực sự lưu chuỗi rỗng.

Kế hoạch thực tế phụ thuộc phiên bản Neo4j, loại index, thống kê và dữ liệu. Bạn có thể kiểm tra bằng `EXPLAIN` hoặc `PROFILE`, ví dụ:

~~~cypher
EXPLAIN
MATCH (c:NullDemoCustomer)
WHERE c.email IS NOT NULL
RETURN c.demoId, c.email;
~~~

Đừng đổi ngữ nghĩa của giá trị thiếu chỉ nhằm làm một truy vấn ngắn hơn hoặc có vẻ chạy nhanh hơn.

### 10.2. Quy tắc chọn kỹ thuật

| Yêu cầu nghiệp vụ | Cách diễn đạt gợi ý | Lý do |
| --- | --- | --- |
| Tìm property bị thiếu | `n.x IS NULL` | Kiểm tra tường minh |
| Tìm property đã có | `n.x IS NOT NULL` | Tránh nhầm với chuỗi rỗng |
| Hiển thị nhãn khi dữ liệu thiếu | `coalesce(n.x, 'Chưa cung cấp')` | Tạo giá trị trình bày |
| Chọn nhiều nguồn theo thứ tự | `coalesce(n.nickname, n.name, n.id)` | Lấy giá trị đầu tiên khác null |
| Phân biệt nhiều trạng thái thiếu/đúng/sai | `CASE WHEN n.flag IS NULL THEN ...` | Bảo toàn ý nghĩa nghiệp vụ |
| Không có relationship tùy chọn | `OPTIONAL MATCH ... WHERE r IS NULL` sau `WITH` | Phát hiện quan hệ không tồn tại |
| Đếm bản ghi thực có property | `count(n.x)` | Bỏ qua giá trị null |
| Đếm mọi dòng đầu vào | `count(*)` | Không bỏ qua dòng có property null |
| Trung bình chỉ trên giá trị được ghi | `avg(n.score)` | Không mặc định điểm thiếu bằng 0 |
| Cập nhật property tùy chọn | `SET n.x = $x` hoặc quy tắc `CASE/coalesce` | Chọn rõ xóa, giữ hay gán mới |

## 11. Bài tập thực hành và đáp án

### Bài 1. Dự đoán kết quả coalesce

Không chạy ngay, hãy tự dự đoán:

~~~cypher
RETURN
  coalesce(null, 0, 10) AS a,
  coalesce(false, true) AS b,
  coalesce('', 'unknown') AS c,
  coalesce(null, null) AS d;
~~~

**Đáp án:** `a = 0`, `b = false`, `c = ''`, `d = null`. Mỗi trường hợp cho thấy `coalesce` chỉ chọn theo điều kiện khác `null`.

### Bài 2. Phân loại tình trạng email

Yêu cầu: phân biệt **chưa có email**, **email là chuỗi rỗng**, và **email hợp lệ ở mức không rỗng**.

~~~cypher
MATCH (c:NullDemoCustomer)
RETURN
  c.name,
  CASE
    WHEN c.email IS NULL THEN 'Thiếu email'
    WHEN trim(c.email) = '' THEN 'Email rỗng'
    ELSE 'Có email'
  END AS emailStatus
ORDER BY c.demoId;
~~~

**Đáp án với dữ liệu mẫu:** An → Có email; Bình → Thiếu email; Chi → Thiếu email. Phân loại “Có email” chỉ xác nhận chuỗi không rỗng, chưa khẳng định cú pháp email đúng.

### Bài 3. Tìm khách hàng chưa mua sản phẩm

Yêu cầu: dùng `OPTIONAL MATCH` và kiểm tra tường minh:

~~~cypher
MATCH (c:NullDemoCustomer)
OPTIONAL MATCH (c)-[r:NULL_DEMO_BOUGHT]->(:NullDemoProduct)
WITH c, r
WHERE r IS NULL
RETURN c.demoId, c.name;
~~~

**Đáp án:** Chi. Nếu một khách hàng có nhiều quan hệ mua hàng, truy vấn chỉ giữ khách hàng không khớp quan hệ nào; người đã mua ít nhất một lần sẽ không được trả về.

### Bài 4. Trung bình điểm có hay không có giá trị mặc định

~~~cypher
UNWIND [10, null, 20] AS score
RETURN
  count(*) AS total,
  count(score) AS recorded,
  avg(score) AS averageRecorded,
  avg(coalesce(score, 0)) AS averageWithMissingAsZero;
~~~

**Đáp án:** `total = 3`, `recorded = 2`, `averageRecorded = 15.0`, `averageWithMissingAsZero = 10.0`. Hãy giải thích vì sao hai giá trị trung bình khác nhau trước khi chọn công thức dùng cho báo cáo thật.

### Bài 5. Thiết kế truy vấn cho API

API hiển thị tất cả khách hàng, cần trả cả email gốc và chuỗi thay thế để giao diện sử dụng. Một cách giải:

~~~cypher
MATCH (c:NullDemoCustomer)
RETURN
  c.demoId AS id,
  c.name AS name,
  c.email AS email,
  c.email IS NULL AS emailMissing,
  coalesce(c.email, 'Chưa cung cấp') AS emailLabel
ORDER BY id;
~~~

Truy vấn tạo cột hiển thị mà không làm mất khả năng phân biệt email bị thiếu. Nếu giao diện muốn xử lý cả chuỗi rỗng, hãy mở rộng bằng `CASE` theo quy tắc thiết kế UI.

## 12. Tổng kết

Trong Cypher, `null` là một trạng thái có ý nghĩa, đặc biệt ở property không tồn tại và kết quả từ `OPTIONAL MATCH`. Ba nguyên tắc cần ghi nhớ:

1. **Kiểm tra tường minh** bằng `IS NULL` và `IS NOT NULL`; phép so sánh `= null` không cho kết quả Boolean đúng.
2. **Chỉ thay giá trị khi nghiệp vụ cho phép:** `coalesce` lấy giá trị đầu tiên khác `null`, nhưng không coi `0`, `false`, chuỗi rỗng hay danh sách rỗng là thiếu.
3. **Giữ nguyên ý nghĩa dữ liệu:** chú ý `WHERE` chỉ giữ `true`; `OPTIONAL MATCH` có thể tạo biến null; `count(expression)`, `avg(expression)` và các phép tổng hợp có cách xử lý null ảnh hưởng trực tiếp đến báo cáo.

Khi mô hình hóa property graph bằng Neo4j, việc dùng nhất quán các quy tắc trên giúp viết Cypher dễ đọc, giảm sai sót khi nhập và cập nhật dữ liệu, đồng thời hỗ trợ ánh xạ kết quả rõ ràng trong Java Driver và Spring Data Neo4j.

# Biểu thức số học, so sánh, chuỗi và giá trị luận lý trong Cypher

Trong Neo4j, dữ liệu được tổ chức theo **property graph**: node biểu diễn thực thể, relationship biểu diễn mối liên hệ, còn property lưu thông tin của cả hai. Khi truy vấn bằng **Cypher**, chúng ta thường không chỉ tìm node và relationship mà còn phải tính toán giá tiền, so sánh thuộc tính, lọc tên theo từ khóa và kết hợp nhiều điều kiện. Những công việc đó dựa trên **biểu thức** (*expression*).

Bài học thuộc chương **Biểu thức và hàm** của mô-đun **DATABASE_ENGINE_GRAPH_NEO4J**. Trọng tâm là cách viết, kết hợp và kiểm soát biểu thức số học, so sánh, chuỗi và luận lý khi truy vấn dữ liệu liên kết trong Neo4j. Các ví dụ cũng chuẩn bị nền tảng cho việc sử dụng Cypher với Java Driver và Spring Data Neo4j.

## 1. Mục tiêu và kiến thức nền

Sau bài này, bạn có thể:

- Phân biệt biểu thức với mệnh đề truy vấn và nhận diện kiểu dữ liệu mà biểu thức tạo ra.
- Tính toán với số nguyên, số thực; dùng dấu ngoặc để kiểm soát thứ tự thực hiện phép tính.
- So sánh property của node và relationship, kiểm tra giá trị thiếu bằng `IS NULL`.
- Ghép, chuẩn hóa và tìm kiếm chuỗi bằng toán tử và hàm của Cypher.
- Kết hợp `AND`, `OR`, `NOT`, `XOR`; hiểu tác động của `null` lên kết quả lọc.
- Viết truy vấn thực tế có tham số, biểu thức tính toán và điều kiện phù hợp với khả năng tối ưu của cơ sở dữ liệu.

### 1.1. Biểu thức xuất hiện ở đâu?

Biểu thức là thành phần được đánh giá để cho ra một giá trị. Ví dụ, `p.price` đọc một property, `p.price * 2` tính ra một số, `p.price > 100000` tạo ra một giá trị luận lý, và `toLower(p.name)` tạo ra chuỗi đã chuyển về chữ thường.

Biểu thức có mặt trong nhiều mệnh đề:

| Vị trí | Ví dụ | Mục đích |
| --- | --- | --- |
| `RETURN` | `RETURN p.price * 2 AS doublePrice` | Tạo cột kết quả từ một phép tính |
| `WHERE` | `WHERE p.price <= 500000` | Lọc node theo điều kiện |
| `WITH` | `WITH p, p.price * 0.9 AS salePrice` | Đặt tên và chuyển tiếp giá trị trung gian |
| `SET` | `SET p.stock = p.stock + 1` | Cập nhật property từ biểu thức |
| `ORDER BY` | `ORDER BY p.price DESC` | Sắp xếp theo giá trị biểu thức |

Trong bài, `INTEGER` biểu diễn số nguyên, `FLOAT` biểu diễn số thực, `STRING` biểu diễn chuỗi, `BOOLEAN` biểu diễn `true` hoặc `false`. Ngoài ra, `null` thể hiện **không có giá trị** hoặc **không xác định**; cần xử lý riêng khi tính toán và lọc.

### 1.2. Dữ liệu mẫu để thực hành

Hầu hết ví dụ số học, chuỗi và luận lý có thể chạy độc lập bằng `RETURN`. Với các truy vấn `MATCH`, bạn có thể tạo một bộ dữ liệu nhỏ trong một cơ sở dữ liệu thực hành. Không chạy đoạn khởi tạo này trong dữ liệu nghiệp vụ đang dùng.

~~~cypher
MERGE (an:Customer {customerId: 'C001'})
SET an.name = 'An', an.active = true
MERGE (binh:Customer {customerId: 'C002'})
SET binh.name = 'Bình', binh.active = false
MERGE (chi:Customer {customerId: 'C003'})
SET chi.name = 'Chi', chi.active = true

MERGE (book:Product {sku: 'P001'})
SET book.name = 'Sách Cypher',
    book.price = 320000, book.stock = 12, book.active = true
MERGE (course:Product {sku: 'P002'})
SET course.name = 'Khóa học Neo4j',
    course.price = 850000, course.stock = 4, course.active = true
MERGE (note:Product {sku: 'P003'})
SET note.name = 'Sổ tay',
    note.price = 95000, note.stock = 0, note.active = false

MERGE (an)-[purchase1:BOUGHT]->(book)
SET purchase1.quantity = 2, purchase1.discount = 0.1
MERGE (binh)-[purchase2:BOUGHT]->(course)
SET purchase2.quantity = 1, purchase2.discount = 0.0;
~~~

Đồ thị mẫu có ba `Customer`, ba `Product` và hai relationship `BOUGHT`. Property `discount` trên relationship là tỉ lệ giảm giá từ 0 đến 1. Khách hàng Chi chưa có giao dịch, giúp minh họa `OPTIONAL MATCH` và `null`.

## 2. Biểu thức số học

### 2.1. Các toán tử số học

| Toán tử | Ý nghĩa | Ví dụ | Kết quả |
| --- | --- | --- | --- |
| `+` | Cộng | `8 + 3` | `11` |
| `-` | Trừ | `8 - 3` | `5` |
| `*` | Nhân | `8 * 3` | `24` |
| `/` | Chia | `8 / 2` | `4` |
| `%` | Chia lấy phần dư | `8 % 3` | `2` |
| `^` | Lũy thừa | `2 ^ 3` | `8` |
| `-` đơn ngôi | Đổi dấu | `-8` | `-8` |

Có thể thử nhiều biểu thức trong cùng một truy vấn:

~~~cypher
RETURN
  2 + 3 * 4 AS defaultOrder,
  (2 + 3) * 4 AS groupedOrder,
  10 / 4 AS integerDivision,
  10 / 4.0 AS decimalDivision,
  10 % 4 AS remainder,
  2 ^ 3 AS power;
~~~

Kết quả lần lượt là `14`, `20`, `2`, `2.5`, `2` và `8`. Điểm cần nhớ: khi **cả hai toán hạng là số nguyên**, phép chia thông thường cho kết quả số nguyên, phần lẻ bị bỏ; muốn chia ra số thực, hãy để ít nhất một toán hạng là `FLOAT`, chẳng hạn `4.0` hoặc chuyển kiểu bằng `toFloat(...)`.

Thứ tự ưu tiên thông dụng là lũy thừa, các phép nhân/chia/chia dư, rồi cộng/trừ. **Dấu ngoặc đơn** cho thấy ý định rõ nhất, nhất là với công thức chiết khấu hoặc các biểu thức dài.

### 2.2. Tính toán trên property của đồ thị

Giả sử tổng tiền phải trả là đơn giá nhân số lượng rồi trừ phần chiết khấu ghi trên relationship:

~~~cypher
MATCH (c:Customer)-[r:BOUGHT]->(p:Product)
RETURN
  c.name AS customer,
  p.name AS product,
  p.price AS unitPrice,
  r.quantity AS quantity,
  p.price * r.quantity AS subtotal,
  p.price * r.quantity * (1 - r.discount) AS finalAmount
ORDER BY customer;
~~~

Với giao dịch của An, thành tiền trước giảm giá là `320000 * 2 = 640000`, giảm 10% còn khoảng `576000`. Kết quả có thể được biểu diễn ở kiểu `FLOAT` do `r.discount` là số thực.

Đối với khoản tiền cần độ chính xác tuyệt đối, nên thống nhất đơn vị lưu trữ trước khi tính. Ví dụ, số tiền VND nguyên có thể được lưu bằng `INTEGER`; nếu dùng tỉ lệ chiết khấu dạng `FLOAT`, cần quy định rõ bước làm tròn trước khi ghi sổ. Không nên mặc định mọi phép tính số thực đều chính xác tuyệt đối vì chúng dùng biểu diễn dấu phẩy động.

### 2.3. Hàm số học và chuyển kiểu

| Hàm | Tác dụng | Ví dụ |
| --- | --- | --- |
| `abs(x)` | Giá trị tuyệt đối | `abs(-12)` → `12` |
| `ceil(x)` | Làm tròn lên | `ceil(4.1)` → `5.0` |
| `floor(x)` | Làm tròn xuống | `floor(4.9)` → `4.0` |
| `round(x, n)` | Làm tròn đến `n` chữ số thập phân | `round(3.14159, 2)` → `3.14` |
| `sqrt(x)` | Căn bậc hai | `sqrt(81)` → `9.0` |
| `toFloat(x)` | Chuyển giá trị phù hợp thành số thực | `toFloat(7)` → `7.0` |
| `toInteger(x)` | Chuyển giá trị phù hợp thành số nguyên | `toInteger('42')` → `42` |

~~~cypher
WITH 7 AS items, 2 AS boxes
RETURN
  items / boxes AS integerResult,
  toFloat(items) / boxes AS decimalResult,
  ceil(toFloat(items) / boxes) AS boxesNeeded;
~~~

Kết quả tương ứng là `3`, `3.5` và `4.0`: cần bốn hộp nếu mỗi hộp chứa được hai món. Phải chủ động chuyển kiểu khi dữ liệu đến từ tham số hoặc property có kiểu khác với dự kiến; không nên dựa vào việc cơ sở dữ liệu tự chuyển số từ chuỗi.

**Chú ý:** phép chia cho 0 và các chuyển kiểu không hợp lệ không phải công thức nghiệp vụ có ý nghĩa. Hãy kiểm tra đầu vào hoặc dùng `CASE` để xác định cách xử lý, thay vì kỳ vọng một kết quả số hợp lệ.

## 3. Biểu thức so sánh

### 3.1. Các toán tử so sánh thường dùng

| Toán tử | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `=` | Bằng | `p.sku = 'P001'` |
| `<>` | Khác | `p.sku <> 'P001'` |
| `>` | Lớn hơn | `p.price > 300000` |
| `>=` | Lớn hơn hoặc bằng | `p.stock >= 1` |
| `<` | Nhỏ hơn | `p.price < 500000` |
| `<=` | Nhỏ hơn hoặc bằng | `p.price <= 500000` |
| `IS NULL` | Không có giá trị | `p.description IS NULL` |
| `IS NOT NULL` | Có giá trị | `p.price IS NOT NULL` |

~~~cypher
MATCH (p:Product)
WHERE p.price >= 100000
  AND p.price <= 500000
RETURN p.sku, p.name, p.price
ORDER BY p.price;
~~~

Với bộ dữ liệu mẫu, chỉ có `P001` thỏa dải giá này. Cypher dùng **`=`** cho phép so sánh bằng; **`==`** không phải cú pháp so sánh cần dùng ở đây. Khi kiểm tra khác nhau, dùng `<>`.

### 3.2. So sánh chuỗi và kiểu dữ liệu

So sánh chuỗi có xét đến chữ hoa/chữ thường. Chẳng hạn:

~~~cypher
RETURN
  'Neo4j' = 'Neo4j' AS sameText,
  'Neo4j' = 'neo4j' AS differentCase,
  10 > 3 AS greaterThan;
~~~

Ba kết quả là `true`, `false`, `true`. Nếu yêu cầu tìm kiếm không phân biệt chữ hoa/chữ thường, hãy chuẩn hóa hai vế bằng các hàm xử lý chuỗi trước khi so sánh. Việc đổi chữ hoa/chữ thường **không đồng nghĩa** với bỏ dấu tiếng Việt hoặc chuẩn hóa mọi biến thể Unicode.

Nên so sánh các giá trị có kiểu phù hợp với nhau. Chẳng hạn, property `price` là số nên tham số `$minPrice` cũng cần được truyền như số; đừng truyền chuỗi `'300000'` rồi mong việc so sánh số hoạt động như ý.

### 3.3. Vì sao không thể dùng dấu bằng để kiểm tra null?

Property chưa tồn tại trên node thường được đọc ra là `null`. Trong logic ba giá trị của Cypher, `null` nghĩa là chưa xác định, vì vậy:

~~~cypher
RETURN
  null = null AS equalityUnknown,
  null <> 5 AS inequalityUnknown,
  null IS NULL AS missingValue,
  5 IS NOT NULL AS presentValue;
~~~

Kết quả là `null`, `null`, `true`, `true`. Muốn tìm sản phẩm chưa có mô tả:

~~~cypher
MATCH (p:Product)
WHERE p.description IS NULL
RETURN p.sku, p.name;
~~~

Đừng viết `WHERE p.description = null`: biểu thức đó tạo ra `null` và không thỏa điều kiện lọc.

## 4. Biểu thức chuỗi

### 4.1. Chuỗi và phép nối chuỗi

Chuỗi Cypher được đặt trong dấu nháy đơn hoặc nháy kép; trong các ví dụ này, ta dùng nháy đơn để thống nhất. Có thể nối chuỗi bằng `||`; để ghép số với chữ, nên chuyển số thành chuỗi tường minh.

~~~cypher
RETURN
  'Neo' || '4j' AS databaseName,
  'Số lượng: ' || toString(12) AS quantityLabel;
~~~

Kết quả là `'Neo4j'` và `'Số lượng: 12'`. Cypher cũng hỗ trợ `+` trong các trường hợp nối chuỗi, nhưng `||` giúp thể hiện rõ mục đích nối văn bản và tránh nhầm lẫn với phép cộng số.

Khi property có thể vắng mặt, dùng `coalesce` để chọn chuỗi dự phòng:

~~~cypher
MATCH (p:Product)
RETURN
  p.sku,
  p.name || ' - ' || coalesce(p.description, 'Chưa có mô tả') AS displayName;
~~~

Nếu không xử lý `null`, biểu thức ghép chuỗi có toán hạng `null` cũng có thể cho kết quả `null`.

### 4.2. Các toán tử kiểm tra chuỗi

| Toán tử | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `STARTS WITH` | Chuỗi bắt đầu bằng một tiền tố | `p.name STARTS WITH 'Sách'` |
| `ENDS WITH` | Chuỗi kết thúc bằng một hậu tố | `p.name ENDS WITH 'Neo4j'` |
| `CONTAINS` | Chuỗi chứa đoạn con | `p.name CONTAINS 'Cypher'` |
| `=~` | Chuỗi khớp biểu thức chính quy (regex) | `p.name =~ '(?i).*neo4j.*'` |

~~~cypher
MATCH (p:Product)
WHERE p.name CONTAINS 'Cypher'
RETURN p.sku, p.name;
~~~

Kết quả mẫu: `P001` – `Sách Cypher`. Các phép kiểm tra chuỗi thông thường có phân biệt chữ hoa/chữ thường.

Khi dùng `=~`, regex được đối chiếu với **toàn bộ chuỗi**. Vì vậy, để tìm từ khóa nằm bên trong tên, dùng `.*` ở hai phía. Cờ `(?i)` cho phép đối chiếu không phân biệt chữ hoa/chữ thường:

~~~cypher
MATCH (p:Product)
WHERE p.name =~ '(?i).*neo4j.*'
RETURN p.sku, p.name;
~~~

Kết quả mẫu: `P002` – `Khóa học Neo4j`. Với đầu vào do người dùng cung cấp, không nên tự lắp ghép tùy tiện nội dung đó thành regex: các ký tự như `.`, `*`, `[` có ý nghĩa đặc biệt. Nếu chỉ cần tìm đoạn con, hãy ưu tiên `CONTAINS` với tham số.

### 4.3. Các hàm chuỗi quan trọng

| Hàm | Công dụng | Ví dụ |
| --- | --- | --- |
| `toLower(s)` | Chuyển về chữ thường | `toLower('Neo4j')` → `'neo4j'` |
| `toUpper(s)` | Chuyển về chữ hoa | `toUpper('neo4j')` → `'NEO4J'` |
| `trim(s)` | Xóa khoảng trắng ở đầu và cuối | `trim('  Neo4j  ')` → `'Neo4j'` |
| `substring(s, start, length)` | Lấy chuỗi con, vị trí bắt đầu từ 0 | `substring('Cypher', 0, 3)` → `'Cyp'` |
| `replace(s, old, new)` | Thay đoạn chuỗi | `replace('Neo-4j', '-', '')` → `'Neo4j'` |
| `split(s, delimiter)` | Chia thành danh sách chuỗi | `split('a,b', ',')` → `['a', 'b']` |
| `size(s)` | Số ký tự trong chuỗi | `size('Neo4j')` → `5` |
| `toString(x)` | Chuyển giá trị thích hợp thành chuỗi | `toString(120)` → `'120'` |

Ví dụ chuẩn hóa chuỗi nhập vào để lọc:

~~~cypher
WITH '   cYpHeR   ' AS rawKeyword
WITH toLower(trim(rawKeyword)) AS keyword
MATCH (p:Product)
WHERE toLower(p.name) CONTAINS keyword
RETURN p.sku, p.name;
~~~

Kết quả có sản phẩm `Sách Cypher`. Vì áp dụng `toLower` trực tiếp lên property, bộ tối ưu có thể không sử dụng cách tìm kiếm theo index như một điều kiện trên property gốc. Với hệ thống lớn, cần cân nhắc chuẩn hóa dữ liệu khi nhập, dùng index thích hợp hoặc giải pháp tìm kiếm văn bản cho trường hợp cụ thể.

## 5. Biểu thức luận lý: true, false và null

### 5.1. Toán tử luận lý và dấu ngoặc

| Toán tử | Diễn giải | Ví dụ | Kết quả |
| --- | --- | --- | --- |
| `NOT` | Phủ định | `NOT true` | `false` |
| `AND` | Cả hai điều kiện đúng | `true AND false` | `false` |
| `OR` | Ít nhất một điều kiện đúng | `true OR false` | `true` |
| `XOR` | Đúng khi hai vế khác nhau về giá trị luận lý | `true XOR false` | `true` |

~~~cypher
MATCH (p:Product)
WHERE p.active = true
  AND (p.price < 500000 OR p.stock >= 10)
RETURN p.sku, p.name, p.price, p.stock;
~~~

Kết quả mẫu chỉ có `P001`. Dấu ngoặc rất quan trọng: **`AND` được ưu tiên hơn `OR`**. Viết `a AND (b OR c)` không tương đương với `(a AND b) OR c`.

Cypher yêu cầu điều kiện luận lý là biểu thức Boolean thích hợp. Không nên dùng số `1`, `0` hoặc chuỗi `'true'` để thay cho Boolean thực.

### 5.2. Logic ba giá trị

Cypher sử dụng ba khả năng đối với phép lọc: `true`, `false` và `null` (không xác định). Khi có `null`, phép toán luận lý không luôn cho ra `null`:

| Biểu thức | Kết quả | Giải thích |
| --- | --- | --- |
| `true AND null` | `null` | Chưa biết vế còn lại đúng hay sai |
| `false AND null` | `false` | Một vế sai nên cả biểu thức sai |
| `true OR null` | `true` | Một vế đúng nên cả biểu thức đúng |
| `false OR null` | `null` | Kết quả phụ thuộc vế chưa biết |
| `NOT null` | `null` | Phủ định giá trị chưa biết vẫn chưa biết |
| `true XOR null` | `null` | Chưa thể xác định hai vế có khác nhau |

~~~cypher
RETURN
  true AND null AS andUnknown,
  false AND null AS andFalse,
  true OR null AS orTrue,
  false OR null AS orUnknown,
  NOT null AS notUnknown;
~~~

Ở `WHERE`, **chỉ những bản ghi mà biểu thức điều kiện cho ra `true` mới được giữ lại**. Bản ghi có điều kiện `false` hoặc `null` đều không xuất hiện trong kết quả. Điều này đặc biệt quan trọng với các thuộc tính tùy chọn.

### 5.3. Giá trị thiếu trong OPTIONAL MATCH

`OPTIONAL MATCH` vẫn giữ lại dòng kết quả kể cả khi mẫu đồ thị không có quan hệ phù hợp; các biến chưa ghép được sẽ mang giá trị `null`.

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:BOUGHT]->(p:Product)
RETURN
  c.name AS customer,
  p.name AS product,
  p.price > 300000 AS isExpensive,
  coalesce(p.price > 300000, false) AS isExpensiveOrFalse
ORDER BY customer;
~~~

Với Chi, `product` và `isExpensive` là `null` vì Chi chưa mua hàng; `isExpensiveOrFalse` là `false`. Đây là hai ý nghĩa nghiệp vụ khác nhau:

- `null`: chưa đủ thông tin để kết luận sản phẩm đắt hay rẻ.
- `false`: ứng dụng quy ước rằng không có sản phẩm thì điều kiện “đắt hơn 300000” được coi là sai.

Không nên lạm dụng `coalesce` để thay tất cả giá trị thiếu bằng `false` hoặc `0`; chỉ chọn giá trị mặc định khi nó phản ánh đúng yêu cầu nghiệp vụ.

### 5.4. CASE: rẽ nhánh theo điều kiện

`CASE` là **biểu thức** có thể được dùng trong `RETURN`, `WITH` hoặc các vị trí nhận biểu thức:

~~~cypher
MATCH (p:Product)
RETURN
  p.name AS product,
  p.stock AS stock,
  CASE
    WHEN p.stock = 0 THEN 'Hết hàng'
    WHEN p.stock < 5 THEN 'Sắp hết'
    ELSE 'Còn hàng'
  END AS stockStatus
ORDER BY p.sku;
~~~

Theo dữ liệu mẫu, `Sổ tay` là “Hết hàng”, `Khóa học Neo4j` là “Sắp hết”, `Sách Cypher` là “Còn hàng”. Các nhánh `WHEN` được xét theo thứ tự và chọn nhánh đầu tiên có điều kiện `true`; nếu không có nhánh phù hợp thì `ELSE` được dùng. Nếu bỏ `ELSE`, kết quả có thể là `null`.

`CASE` còn hữu ích để biểu diễn quy tắc chia an toàn:

~~~cypher
WITH 100.0 AS total, 0 AS count
RETURN
  CASE
    WHEN count = 0 THEN null
    ELSE total / count
  END AS average;
~~~

Không nên chỉ dựa vào việc viết `count <> 0 AND total / count > 5` để bảo vệ mọi phép chia: bộ tối ưu có thể thay đổi thứ tự xử lý biểu thức. Khi điều kiện bảo vệ phép tính là bắt buộc, hãy biểu đạt trực tiếp bằng `CASE`.

## 6. Kết hợp các loại biểu thức trong một truy vấn đồ thị

Một truy vấn nghiệp vụ thường phối hợp cả bốn nhóm:

~~~cypher
MATCH (c:Customer)-[r:BOUGHT]->(p:Product)
WHERE c.active = true
  AND p.active = true
  AND toLower(p.name) CONTAINS 'cypher'
WITH
  c, p, r,
  p.price * r.quantity *
    (1 - coalesce(r.discount, 0.0)) AS amount
RETURN
  c.name AS customer,
  p.name AS product,
  r.quantity AS quantity,
  round(amount, 0) AS amount,
  CASE
    WHEN amount >= 500000 THEN 'Đơn giá trị cao'
    ELSE 'Đơn thông thường'
  END AS orderGroup
ORDER BY amount DESC;
~~~

Truy vấn này hoạt động theo trình tự:

1. `MATCH` tìm các đường đi `(:Customer)-[:BOUGHT]->(:Product)`.
2. `WHERE` kiểm tra trạng thái hoạt động và lọc tên sản phẩm bằng biểu thức chuỗi.
3. `WITH` tính tiền dựa vào property trên node và relationship; `coalesce` xử lý trường hợp không ghi chiết khấu.
4. `RETURN` đặt bí danh, làm tròn số tiền để hiển thị và phân loại bằng `CASE`.

Với dữ liệu mẫu, An mua `Sách Cypher` với số lượng 2, giá trị tính ra khoảng 576000 và được xếp vào nhóm “Đơn giá trị cao”. Thử đổi ngưỡng hoặc từ khóa để thấy điều kiện luận lý ảnh hưởng đến tập kết quả.

Lưu ý: `WITH` tách truy vấn thành các bước xử lý; chỉ những biến được khai báo/chuyển tiếp sau `WITH` mới dùng được ở mệnh đề tiếp theo. Biểu thức `amount` là tên mới cho phép tính, giúp tránh lặp công thức dài.

## 7. Tham số truy vấn và hiệu năng

### 7.1. Truyền giá trị bằng tham số

Trong ứng dụng Java Driver hoặc Spring Data Neo4j, các giá trị thay đổi theo yêu cầu người dùng nên được truyền dưới dạng **tham số**, chẳng hạn `$minPrice` và `$prefix`:

~~~cypher
MATCH (p:Product)
WHERE p.price >= $minPrice
  AND p.name STARTS WITH $prefix
  AND p.active = true
RETURN p.sku, p.name, p.price
ORDER BY p.price;
~~~

Ví dụ, ứng dụng truyền `minPrice = 200000` và `prefix = 'Sách'` sẽ nhận sản phẩm `P001`. Tham số giúp tách dữ liệu khỏi câu truy vấn, thuận tiện tái sử dụng và tránh việc ghép chuỗi đầu vào thành cú pháp Cypher. Hãy giữ đúng kiểu dữ liệu của từng tham số, đặc biệt `INTEGER`, `FLOAT`, `STRING` và `BOOLEAN`.

### 7.2. Viết biểu thức để bộ tối ưu có thể tận dụng index

Điều kiện trên property gốc thường dễ khai thác index hơn điều kiện bọc property trong một hàm. Chẳng hạn:

~~~cypher
// Thường dễ tối ưu khi có index thích hợp trên :Product(sku)
MATCH (p:Product)
WHERE p.sku = $sku
RETURN p.name, p.price;
~~~

~~~cypher
// Cần đánh giá kế hoạch truy vấn, nhất là trên tập dữ liệu lớn
MATCH (p:Product)
WHERE toLower(p.name) = toLower($name)
RETURN p.sku, p.name;
~~~

Neo4j có nhiều loại index, phù hợp với các mẫu tìm kiếm khác nhau. Việc có dùng được index hay không còn tùy loại index, thống kê dữ liệu, kiểu điều kiện và phiên bản Neo4j. Đừng kết luận chỉ dựa vào cú pháp; hãy dùng `EXPLAIN` để xem kế hoạch dự kiến và `PROFILE` để xem thao tác thực tế, chẳng hạn:

~~~cypher
PROFILE
MATCH (p:Product)
WHERE p.sku = $sku
RETURN p.name;
~~~

Khi đọc kế hoạch, tìm các thao tác truy cập như `NodeIndexSeek` hoặc quét nhãn và so sánh số lần truy cập dữ liệu (`DB Hits`). Để kiểm chứng công bằng, cần truyền tham số hợp lệ và đánh giá trên bộ dữ liệu đại diện. Chỉ tạo index/constraint theo quy định của môi trường, vì chúng là thay đổi schema chứ không phải phép tính đơn thuần.

## 8. Lỗi thường gặp và cách tránh

| Tình huống | Cách hiểu đúng hoặc cách sửa |
| --- | --- |
| Viết `p.price == 100000` | Dùng `p.price = 100000`. |
| Viết `p.description = null` | Dùng `p.description IS NULL`. |
| Viết `7 / 2` nhưng chờ `3.5` | Dùng `7 / 2.0` hoặc `toFloat(7) / 2`. |
| Ghép chuỗi với property thiếu | Dùng `coalesce(property, 'Giá trị dự phòng')` nếu phù hợp nghiệp vụ. |
| Lọc `WHERE NOT p.active` và tưởng property thiếu sẽ được giữ lại | `NOT null` vẫn là `null`; cần xác định rõ cách xử lý giá trị thiếu. |
| Viết `a OR b AND c` nhưng muốn `(a OR b) AND c` | Thêm ngoặc để diễn đạt chính xác logic. |
| Dùng `CONTAINS` và mong bỏ qua chữ hoa/chữ thường | Chuẩn hóa chuỗi hoặc dùng cơ chế tìm kiếm thích hợp. |
| So sánh giá số với tham số chuỗi | Truyền tham số với kiểu số nhất quán. |
| Kỳ vọng mọi phép tính `FLOAT` đều chính xác tuyệt đối | Thiết kế đơn vị lưu trữ và quy tắc làm tròn cho dữ liệu tài chính. |
| Dùng regex để tìm chuỗi con nhưng bỏ `.*` | `=~` đối chiếu toàn bộ chuỗi; dùng `CONTAINS` nếu không cần regex. |

## 9. Bài thực hành tự kiểm tra

**Bài 1 – Thứ tự phép toán.** Dự đoán ba cột kết quả:

~~~cypher
RETURN
  3 + 2 * 5 AS a,
  (3 + 2) * 5 AS b,
  9 / 2.0 AS c;
~~~

Đáp án: `a = 13`, `b = 25`, `c = 4.5`. Dấu ngoặc làm thay đổi thứ tự; số thực ở mẫu số cho kết quả chia thực.

**Bài 2 – Lọc sản phẩm còn bán.** Viết truy vấn chỉ lấy sản phẩm có `active = true`, `stock > 0`, `price <= 400000`. Một cách giải:

~~~cypher
MATCH (p:Product)
WHERE p.active = true
  AND p.stock > 0
  AND p.price <= 400000
RETURN p.sku, p.name, p.price, p.stock;
~~~

Với bộ dữ liệu mẫu, kết quả là `P001`.

**Bài 3 – Tìm kiếm không phân biệt chữ hoa/chữ thường.** Tìm sản phẩm có tên chứa `'NEO4J'` dù dữ liệu viết khác kiểu chữ:

~~~cypher
WITH 'NEO4J' AS keyword
MATCH (p:Product)
WHERE toLower(p.name) CONTAINS toLower(keyword)
RETURN p.sku, p.name;
~~~

Kết quả mẫu là `P002`. Có thể cải thiện thiết kế tìm kiếm cho dữ liệu lớn bằng cách chọn cách lưu trữ/index phù hợp.

**Bài 4 – Khách hàng chưa mua hàng.** Sử dụng `OPTIONAL MATCH` và phép kiểm tra `IS NULL`:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[r:BOUGHT]->(:Product)
WITH c, count(r) AS purchaseCount
WHERE purchaseCount = 0
RETURN c.customerId, c.name;
~~~

Kết quả mẫu là khách hàng Chi. `count(r)` đếm relationship khác `null`, nên trả về 0 cho khách hàng chưa có relationship `BOUGHT`. Đây là cách diễn đạt rõ ràng khi cần phân biệt “không có giao dịch” với “có giao dịch nhưng property thiếu”.

## 10. Ghi nhớ

- Biểu thức số học cho phép tính trên property của cả node và relationship; chú ý kiểu số và ngoặc.
- Biểu thức so sánh dùng `=`, `<>`, `<`, `>`, `<=`, `>=`; dùng `IS NULL` hoặc `IS NOT NULL` để kiểm tra giá trị thiếu.
- Biểu thức chuỗi dùng `||`, `STARTS WITH`, `ENDS WITH`, `CONTAINS`, `=~` và các hàm chuẩn hóa/chuyển đổi phù hợp.
- Biểu thức luận lý có ba trạng thái `true`, `false`, `null`; trong `WHERE`, chỉ `true` giữ lại dòng kết quả.
- Dùng `coalesce` khi có quy tắc mặc định rõ ràng, `CASE` khi cần rẽ nhánh, và tham số `$name` khi truy vấn được gọi từ ứng dụng.
- Với dữ liệu đồ thị lớn, xem kế hoạch bằng `EXPLAIN`/`PROFILE` để hiểu tác động của biểu thức lên việc sử dụng index.

Nắm vững các quy tắc này giúp viết truy vấn Cypher rõ ràng, xử lý an toàn các thuộc tính tùy chọn và tính toán đáng tin cậy trên dữ liệu liên kết của Neo4j.

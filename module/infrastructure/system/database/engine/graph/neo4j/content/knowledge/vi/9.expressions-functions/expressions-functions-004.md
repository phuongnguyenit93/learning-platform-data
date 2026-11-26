# Hàm chuỗi, biểu thức chính quy và chuẩn hóa văn bản trong Cypher

Trong mô hình **property graph**, thông tin văn bản xuất hiện ở nhiều nơi: tên người dùng trên node, mã sản phẩm, tiêu đề tài liệu, nhãn phân loại, nội dung đánh giá trên relationship và dữ liệu nhập từ CSV. Những trường này thường cần được ghép, cắt, chuyển chữ hoa/chữ thường, tìm kiếm theo từ khóa, kiểm tra định dạng hoặc chuẩn hóa Unicode trước khi sử dụng.

Bài học thuộc chương **Biểu thức và hàm** của mô-đun **DATABASE_ENGINE_GRAPH_NEO4J**. Mô-đun hướng đến việc dùng Neo4j để mô hình hóa dữ liệu liên kết, truy vấn quan hệ và đường đi bằng Cypher, đồng thời tích hợp với Java Driver và Spring Data Neo4j. Vì vậy, bài không chỉ giới thiệu cú pháp mà còn chỉ ra cách xử lý văn bản đúng về mặt dữ liệu và cách lựa chọn truy vấn có thể tối ưu bằng index.

## 1. Mục tiêu học tập

Sau khi hoàn thành, bạn có thể:

- Dùng các hàm chuỗi thông dụng như `trim()`, `toLower()`, `toUpper()`, `substring()`, `left()`, `right()`, `replace()`, `split()`, `size()` và `toString()`.
- Phân biệt nối chuỗi, xử lý `null` và các phép kiểm tra `STARTS WITH`, `ENDS WITH`, `CONTAINS`.
- Viết biểu thức chính quy với toán tử `=~`, dùng nhóm ký tự, lượng từ, mốc đầu/cuối và cờ không phân biệt chữ hoa/chữ thường.
- Hiểu sự khác biệt giữa **chuẩn hóa Unicode** với **đổi chữ thường**, **xóa dấu tiếng Việt** và **tìm kiếm gần đúng**.
- Dùng `normalize()` và `IS NORMALIZED` khi phiên bản Neo4j hỗ trợ.
- Thiết kế luồng làm sạch dữ liệu có tham số, chỉ mục tìm kiếm và xử lý văn bản từ ứng dụng Java.
- Tránh các lỗi thường gặp khi tìm kiếm tên, mã định danh và property tùy chọn trên node hoặc relationship.

## 2. Dữ liệu mẫu cho bài thực hành

Những ví dụ bắt đầu bằng `RETURN` hoặc `WITH` có thể chạy riêng. Để chạy các ví dụ `MATCH`, hãy khởi tạo bộ dữ liệu sau trong một **database thực hành**, tránh chạy trên dữ liệu nghiệp vụ thật.

~~~cypher
MERGE (book:StringDemoProduct {sku: 'STR-001'})
SET book.name = 'Sách Cypher',
    book.category = 'Sách',
    book.price = 320000,
    book.description = 'Tìm hiểu truy vấn đồ thị bằng Cypher'

MERGE (course:StringDemoProduct {sku: 'STR-002'})
SET course.name = '  Khóa học Neo4j  ',
    course.category = 'Khóa học',
    course.price = 850000,
    course.description = 'Giới thiệu NEO4J và mô hình property graph'

MERGE (coffee:StringDemoProduct {sku: 'STR-003'})
SET coffee.name = 'Cà phê dữ liệu',
    coffee.category = 'Đồ uống',
    coffee.price = 95000,
    coffee.description = 'Sản phẩm dùng để thử Unicode tiếng Việt'

MERGE (guide:StringDemoProduct {sku: 'STR-004'})
SET guide.name = 'Hướng dẫn Java',
    guide.category = 'Sách',
    guide.price = 180000
REMOVE guide.description

MERGE (an:StringDemoCustomer {customerId: 'CUS-001'})
SET an.name = 'An', an.email = 'AN@example.com'

MERGE (binh:StringDemoCustomer {customerId: 'CUS-002'})
SET binh.name = 'Bình'
REMOVE binh.email

MERGE (an)-[review:STRING_DEMO_REVIEWED]->(book)
SET review.comment = '  Nội dung rất hữu ích!  ',
    review.rating = 5;
~~~

Đồ thị có bốn sản phẩm, hai khách hàng và một quan hệ đánh giá. Dữ liệu được thiết kế có chủ đích:

| Property | Dữ liệu đặc biệt | Mục đích |
| --- | --- | --- |
| `course.name` | Có khoảng trắng ở đầu và cuối | Thử `trim()` |
| `course.description` | Có chữ `NEO4J` viết hoa | Thử tìm kiếm không phân biệt hoa/thường |
| `coffee.name` | Có dấu tiếng Việt | Thử Unicode |
| `guide.description` | Property không tồn tại | Thử xử lý `null` |
| `an.email` | `AN@example.com` | Thử chuẩn hóa email và regex |
| `review.comment` | Có khoảng trắng bao quanh | Thử hàm chuỗi trên relationship |

**Lưu ý:** tất cả ví dụ dựa trên label `StringDemoProduct`, `StringDemoCustomer` và relationship `STRING_DEMO_REVIEWED`, vì vậy có thể tách biệt với những bài thực hành đồ thị khác.

## 3. Kiểu STRING, chuỗi literal và phép nối chuỗi

### 3.1. Chuỗi trong Cypher

`STRING` là kiểu biểu diễn văn bản. Bạn có thể viết literal chuỗi bằng dấu nháy đơn hoặc nháy kép:

~~~cypher
RETURN
  'Neo4j' AS singleQuoted,
  "Cypher" AS doubleQuoted,
  '' AS emptyString;
~~~

Chuỗi rỗng `''` có độ dài 0 nhưng **khác `null`**. `null` biểu diễn giá trị thiếu/không xác định. Khi property không tồn tại, truy cập property đó thường cho kết quả `null`.

Để biểu diễn dấu nháy nằm trong chuỗi, dùng cách escape phù hợp với literal Cypher:

~~~cypher
RETURN 'Neo4j là một cơ sở dữ liệu \"graph\"' AS description;
~~~

Ở đoạn trên, dấu nháy kép là một phần nội dung văn bản. Nếu dùng ký tự có ý nghĩa đặc biệt như dấu nháy hoặc dấu gạch chéo ngược trong regex, cần phân biệt hai lớp cú pháp: **chuỗi Cypher** và **mẫu regex** bên trong chuỗi.

### 3.2. Nối chuỗi bằng ||

Cypher hỗ trợ toán tử nối chuỗi `||`; toán tử `+` cũng có thể nối chuỗi, nhưng `||` diễn đạt ý định rõ ràng hơn:

~~~cypher
RETURN
  'Neo' || '4j' AS productName,
  'Mã: ' || 'STR-001' AS skuLabel,
  'Giá: ' || toString(320000) AS priceLabel;
~~~

Kết quả tương ứng là `Neo4j`, `Mã: STR-001`, `Giá: 320000`. Khi nối số với chuỗi, nên chuyển số tường minh bằng `toString()`.

Để hiển thị thông tin từ đồ thị:

~~~cypher
MATCH (p:StringDemoProduct)
RETURN
  p.sku,
  trim(p.name) || ' (' || p.sku || ')' AS displayName
ORDER BY p.sku;
~~~

Đối với `STR-002`, kết quả `displayName` là `Khóa học Neo4j (STR-002)` vì khoảng trắng dư đã được cắt bỏ.

### 3.3. Null trong các hàm và phép nối

Các biểu thức chuỗi thường lan truyền `null`:

~~~cypher
RETURN
  toLower(null) AS a,
  trim(null) AS b,
  'Giá trị: ' || null AS c,
  coalesce(null, 'Chưa cung cấp') AS d;
~~~

Ba cột đầu nhận `null`; cột `d` nhận `Chưa cung cấp`. Nếu muốn hiển thị mô tả cho cả sản phẩm không có property `description`:

~~~cypher
MATCH (p:StringDemoProduct)
RETURN
  p.sku,
  coalesce(p.description, 'Chưa có mô tả') AS description
ORDER BY p.sku;
~~~

Với `STR-004`, cột mô tả hiển thị `Chưa có mô tả`. Đây là **giá trị trong kết quả truy vấn**, không ghi đè property đang thiếu trên node.

## 4. Các hàm xử lý chuỗi thông dụng

### 4.1. Bảng tra cứu nhanh

| Hàm | Ý nghĩa | Ví dụ | Kết quả |
| --- | --- | --- | --- |
| `trim(s)` | Xóa khoảng trắng đầu và cuối | `trim('  Neo4j  ')` | `'Neo4j'` |
| `ltrim(s)` | Xóa khoảng trắng đầu chuỗi | `ltrim('  Neo4j')` | `'Neo4j'` |
| `rtrim(s)` | Xóa khoảng trắng cuối chuỗi | `rtrim('Neo4j  ')` | `'Neo4j'` |
| `toLower(s)` | Chuyển thành chữ thường | `toLower('Neo4j')` | `'neo4j'` |
| `toUpper(s)` | Chuyển thành chữ hoa | `toUpper('Neo4j')` | `'NEO4J'` |
| `left(s, n)` | Lấy `n` ký tự đầu | `left('Cypher', 3)` | `'Cyp'` |
| `right(s, n)` | Lấy `n` ký tự cuối | `right('Cypher', 3)` | `'her'` |
| `substring(s, start, len)` | Cắt từ vị trí `start` (bắt đầu 0) | `substring('Cypher', 1, 3)` | `'yph'` |
| `replace(s, old, new)` | Thay mọi đoạn con `old` bằng `new` | `replace('a-b-c', '-', '/')` | `'a/b/c'` |
| `split(s, separator)` | Tách chuỗi thành danh sách | `split('a,b', ',')` | `['a','b']` |
| `reverse(s)` | Đảo thứ tự ký tự | `reverse('abc')` | `'cba'` |
| `size(s)` | Độ dài chuỗi theo đơn vị ký tự | `size('Cypher')` | `6` |
| `toString(x)` | Chuyển giá trị có thể chuyển thành chuỗi | `toString(42)` | `'42'` |

Một số hàm có đối số hoặc dạng cú pháp mở rộng tùy phiên bản. Ví dụ, với `trim` có thể chỉ định vị trí và ký tự cần loại bỏ. Trong phạm vi bài này, cách gọi đơn giản dùng để làm sạch khoảng trắng thông dụng nhất.

### 4.2. trim, ltrim, rtrim

~~~cypher
RETURN
  trim('  Neo4j  ') AS bothSides,
  ltrim('  Neo4j  ') AS leftSide,
  rtrim('  Neo4j  ') AS rightSide;
~~~

Kết quả:

- `bothSides = 'Neo4j'`;
- `leftSide = 'Neo4j  '`;
- `rightSide = '  Neo4j'`.

Ví dụ có property:

~~~cypher
MATCH (p:StringDemoProduct {sku: 'STR-002'})
RETURN
  p.name AS rawName,
  trim(p.name) AS cleanedName,
  size(p.name) AS rawLength,
  size(trim(p.name)) AS cleanedLength;
~~~

Tên gốc có khoảng trắng thừa, vì thế `cleanedLength` nhỏ hơn `rawLength` bốn đơn vị (hai khoảng trắng mỗi phía). Nếu chuỗi là `null`, `trim(null)` vẫn là `null`; nếu chuỗi chỉ chứa khoảng trắng thì `trim(...)` trả chuỗi rỗng.

### 4.3. toLower và toUpper

~~~cypher
RETURN
  toLower('Neo4j CYPHER') AS lowerName,
  toUpper('neo4j cypher') AS upperName;
~~~

Kết quả: `neo4j cypher` và `NEO4J CYPHER`.

Hai hàm hữu ích khi so sánh văn bản không phân biệt chữ hoa/chữ thường:

~~~cypher
MATCH (p:StringDemoProduct)
WHERE toLower(p.description) CONTAINS 'neo4j'
RETURN p.sku, p.name, p.description;
~~~

Kết quả gồm `STR-002`. Tuy nhiên, việc áp dụng hàm lên property khi lọc có thể làm thay đổi khả năng dùng index. Phần cuối bài sẽ hướng dẫn một cách thiết kế khác cho dữ liệu lớn.

**Phân biệt:** chuyển chữ hoa/chữ thường không đồng nghĩa với xóa dấu tiếng Việt, chuyển chữ có dấu thành chữ không dấu hoặc chuẩn hóa mọi dạng Unicode tương đương.

### 4.4. left, right và substring

~~~cypher
RETURN
  left('STR-001', 3) AS prefix,
  right('STR-001', 3) AS suffix,
  substring('STR-001', 4, 3) AS numericPart,
  substring('Cypher', 3) AS fromIndex3;
~~~

Kết quả: `STR`, `001`, `001` và `her`. Vị trí bắt đầu của `substring` tính từ **0**. Số lượng ký tự cần lấy là đối số thứ ba; có thể bỏ qua đối số này để lấy đến hết chuỗi.

Các hàm cắt chuỗi hữu ích với mã định danh có định dạng rõ ràng. Dù vậy, với dữ liệu thực, nên kiểm tra độ dài trước nếu quy tắc nghiệp vụ đòi hỏi mã phải đủ số ký tự:

~~~cypher
MATCH (p:StringDemoProduct)
WHERE p.sku IS NOT NULL AND size(p.sku) >= 7
RETURN p.sku, substring(p.sku, 4, 3) AS sequenceCode;
~~~

Đừng dùng vị trí ký tự cố định để tách các dữ liệu có định dạng không ổn định, chẳng hạn tên người dùng hoặc địa chỉ tự do.

### 4.5. replace: thay đoạn chuỗi theo đúng nghĩa đen

~~~cypher
RETURN
  replace('Neo 4j', ' ', '') AS withoutSpace,
  replace('db.graph.neo4j', '.', '-') AS dashed,
  replace('a-b-c', '-', '_') AS underscored;
~~~

Kết quả: `Neo4j`, `db-graph-neo4j`, `a_b_c`. `replace()` thay thế **chuỗi con**, không diễn giải đối số tìm kiếm thành regex. Chẳng hạn `replace(s, '.', '')` chỉ loại dấu chấm thật sự, không loại mọi ký tự.

Nếu cần thay thế theo biểu thức chính quy, phải dùng giải pháp tương thích phiên bản (xử lý tại Java/ETL hoặc hàm dành riêng cho regex trong phiên bản có hỗ trợ). Không nên nhầm `replace()` với một hàm regex-replace phổ quát.

### 4.6. split: tách thành danh sách

~~~cypher
RETURN
  split('Neo4j,Cypher,Graph', ',') AS topics,
  split('STR-001', '-') AS skuParts;
~~~

Kết quả lần lượt là `['Neo4j', 'Cypher', 'Graph']` và `['STR', '001']`.

Có thể phối hợp với `UNWIND` để mỗi phần tử danh sách trở thành một dòng:

~~~cypher
WITH 'graph,neo4j,cypher' AS rawTags
UNWIND split(rawTags, ',') AS tag
RETURN toUpper(trim(tag)) AS tag
ORDER BY tag;
~~~

Kết quả là ba dòng `CYPHER`, `GRAPH`, `NEO4J`. Khi cần tách dữ liệu có nhiều dấu phân cách, hãy xác định quy tắc định dạng trước; một dấu phẩy nằm trong nội dung được trích dẫn có thể khiến việc tách đơn giản bằng `split` không phù hợp cho CSV đầy đủ.

### 4.7. size và việc kiểm tra dữ liệu rỗng

~~~cypher
RETURN
  size('Neo4j') AS a,
  size('') AS b,
  size(trim('   ')) AS c,
  size(null) AS d;
~~~

Kết quả `a = 5`, `b = 0`, `c = 0`, `d = null`. Cần phân biệt độ dài **chuỗi** với số **byte UTF-8**. Trong văn bản Unicode, ký tự có dấu có thể sử dụng nhiều byte; các dạng biểu diễn Unicode khác nhau cũng có thể cho số đơn vị ký tự khác nhau trước khi chuẩn hóa.

Để phát hiện trường mô tả không có nội dung hữu ích:

~~~cypher
MATCH (p:StringDemoProduct)
WHERE p.description IS NULL
   OR trim(p.description) = ''
RETURN p.sku, p.name;
~~~

Kết quả có `STR-004` vì thiếu `description`. Điều kiện thứ hai còn phát hiện mô tả chỉ chứa khoảng trắng nếu có trong tương lai.

## 5. Toán tử tìm kiếm chuỗi

### 5.1. STARTS WITH, ENDS WITH, CONTAINS

Ba toán tử trả biểu thức Boolean (`true`, `false` hoặc `null`) và thường được dùng trong `WHERE`:

| Toán tử | Cách đọc | Ví dụ |
| --- | --- | --- |
| `STARTS WITH` | Bắt đầu bằng | `p.sku STARTS WITH 'STR-'` |
| `ENDS WITH` | Kết thúc bằng | `p.name ENDS WITH 'Java'` |
| `CONTAINS` | Có chứa đoạn con | `p.name CONTAINS 'Cypher'` |

~~~cypher
MATCH (p:StringDemoProduct)
WHERE p.sku STARTS WITH 'STR-'
  AND trim(p.name) ENDS WITH 'Java'
RETURN p.sku, p.name;
~~~

Kết quả là `STR-004`.

~~~cypher
MATCH (p:StringDemoProduct)
WHERE p.description CONTAINS 'property graph'
RETURN p.sku, p.description;
~~~

Kết quả là `STR-002`. Với property không tồn tại, kết quả của phép so khớp thường là `null`; dòng đó không vượt qua `WHERE`.

### 5.2. Toán tử chuỗi phân biệt hoa/thường

~~~cypher
RETURN
  'Neo4j' CONTAINS 'neo' AS a,
  'Neo4j' CONTAINS 'Neo' AS b,
  'Neo4j' STARTS WITH 'Neo' AS c;
~~~

Kết quả: `a = false`, `b = true`, `c = true`. Vì vậy, muốn tìm chuỗi không phân biệt chữ hoa/thường cần chuẩn hóa hai vế theo cùng quy tắc:

~~~cypher
WITH 'neo4j' AS keyword
MATCH (p:StringDemoProduct)
WHERE toLower(p.description) CONTAINS toLower(keyword)
RETURN p.sku, p.description;
~~~

Kết quả là `STR-002`. Lưu ý rằng cùng đổi sang chữ thường vẫn **không** giúp so khớp `'cafe'` với `'cà phê'`.

### 5.3. Tham số không sử dụng dấu % như SQL LIKE

Khi tìm theo từ khóa nhận từ Java Driver:

~~~cypher
MATCH (p:StringDemoProduct)
WHERE p.name CONTAINS $keyword
RETURN p.sku, p.name;
~~~

Tham số `$keyword` phải là một chuỗi, ví dụ `'Cypher'`. Không cần ghép ký tự `%` hoặc `*` vào hai đầu như cú pháp `LIKE` của SQL; `CONTAINS` tự kiểm tra đoạn con. Nếu người dùng nhập ký tự `%` hoặc `*`, chúng được xem là ký tự thông thường trong so khớp `CONTAINS`.

## 6. Biểu thức chính quy (regex) với toán tử =~

### 6.1. Regex là gì và khi nào cần?

Regex mô tả một **mẫu ký tự**, hữu ích khi kiểm tra cấu trúc chuỗi hoặc nhận diện nhiều biến thể cùng một dạng. Trong Cypher, toán tử `=~` đối chiếu một chuỗi với mẫu regex theo cú pháp **Java regular expressions**:

~~~cypher
RETURN
  'STR-001' =~ 'STR-[0-9]{3}' AS validSku,
  'STR-12' =~ 'STR-[0-9]{3}' AS invalidSku,
  'Neo4j' =~ '(?i)neo4j' AS caseInsensitiveMatch;
~~~

Kết quả: `true`, `false`, `true`.

Với `=~`, mẫu được dùng để so khớp **toàn bộ chuỗi**. Nếu chỉ muốn nhận diện một đoạn nằm giữa chuỗi, thêm `.*` hai phía hoặc dùng `CONTAINS` khi không cần sức mạnh của regex.

### 6.2. Các thành phần regex cần nhớ

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `.` | Một ký tự bất kỳ (trừ một số ký tự xuống dòng theo mặc định) | `a.b` |
| `*` | Lặp 0 hoặc nhiều lần | `ab*` |
| `+` | Lặp 1 hoặc nhiều lần | `ab+` |
| `?` | Phần tử trước có thể có hoặc không | `colou?r` |
| `{n}` | Lặp đúng `n` lần | `[0-9]{3}` |
| `[0-9]` | Một chữ số từ 0 đến 9 | `[0-9]+` |
| `[A-Z]` | Một chữ hoa Latin từ A đến Z | `[A-Z]+` |
| `(a\|b)` | Chọn một trong hai mẫu | `(Neo4j\|Cypher)` |
| `^` | Mốc đầu chuỗi | `^STR-` |
| `$` | Mốc cuối chuỗi | `[0-9]$` |
| `(?i)` | Cờ so khớp không phân biệt hoa/thường | `(?i)neo4j` |

Các mốc `^` và `$` vẫn hữu ích khi xây dựng mẫu để người đọc thấy rõ cấu trúc đầu/cuối, dù `=~` vốn yêu cầu khớp toàn bộ chuỗi.

Ví dụ kiểm tra mã sản phẩm có tiền tố `STR-` và đúng ba chữ số:

~~~cypher
MATCH (p:StringDemoProduct)
WHERE p.sku =~ 'STR-[0-9]{3}'
RETURN p.sku, trim(p.name) AS name
ORDER BY p.sku;
~~~

Bốn sản phẩm mẫu đều thỏa. Nếu một sản phẩm có mã `STR-12X` hoặc `STR-1234`, nó không khớp mẫu.

### 6.3. Kiểm tra tiền tố và hậu tố bằng regex

~~~cypher
RETURN
  'STR-001' =~ '^STR-.*' AS startsWithStr,
  'STR-001' =~ '.*[0-9]$' AS endsInDigit,
  'Khóa học Neo4j' =~ '(?i).*neo4j.*' AS containsNeo4j;
~~~

Kết quả cả ba đều `true`. Nhưng khi chỉ kiểm tra tiền tố, hậu tố hay đoạn con cố định, các toán tử `STARTS WITH`, `ENDS WITH` và `CONTAINS` thường dễ đọc hơn, đồng thời có thể tận dụng loại index thích hợp.

### 6.4. Cờ regex: (?i), (?m), (?s)

Regex Java hỗ trợ các cờ như:

- `(?i)`: so khớp không phân biệt chữ hoa/thường.
- `(?m)`: chế độ nhiều dòng, thay đổi ý nghĩa mốc `^` và `$` trong chuỗi có xuống dòng.
- `(?s)`: chế độ dotall, cho phép `.` khớp cả ký tự xuống dòng.

~~~cypher
RETURN
  'neo4j' =~ '(?i)NEO4J' AS ignoreCase,
  'Neo4j' =~ '(?i)neo4j' AS ignoreCaseAgain;
~~~

Kết quả đều `true`. Đối với văn bản đa ngôn ngữ, phải chú ý khác biệt giữa case-insensitive matching và quy tắc so khớp Unicode. Đừng mặc định rằng một cờ regex sẽ đồng thời bỏ dấu, phiên âm hoặc xử lý tất cả kiểu viết tiếng Việt.

### 6.5. Escape regex có hai tầng

Trong regex, dấu chấm `.` là ký tự đại diện, không phải dấu chấm literal. Để khớp địa chỉ tên miền kết thúc bằng `.com`, cần escape dấu chấm theo cú pháp regex. Vì mẫu được viết trong **literal chuỗi Cypher**, ký tự `\` có thể cần escape thêm:

~~~cypher
RETURN
  'an@example.com' =~ '.*\\.com' AS correctDomain,
  'an@exampleXcom' =~ '.*.com' AS overlyBroadPattern;
~~~

Hai biểu thức có thể đều trả `true`: biểu thức thứ hai khớp cả ký tự `X` vì dấu chấm chưa được escape trong regex. Trong chuỗi Cypher, `'\\.'` truyền một `\.` cho bộ máy regex.

Một cách tránh nhầm lẫn khi kiểm tra hậu tố literal là:

~~~cypher
RETURN
  'an@example.com' ENDS WITH '.com' AS expected,
  'an@exampleXcom' ENDS WITH '.com' AS rejected;
~~~

Kết quả `expected = true` và `rejected = false`.

Khi dùng các mẫu như `\d`, `\s`, `\b` hay `\p{L}`, cần tính đến cả quy tắc escape của chuỗi Cypher và regex. Trong những ví dụ đơn giản, `[0-9]` giúp tránh lớp escape phức tạp.

### 6.6. Regex cho dữ liệu quan hệ

Text có thể nằm trên relationship chứ không chỉ trên node:

~~~cypher
MATCH (c:StringDemoCustomer)-[r:STRING_DEMO_REVIEWED]->(p:StringDemoProduct)
WHERE trim(r.comment) =~ '(?i).*hữu ích.*'
RETURN
  c.name AS reviewer,
  trim(p.name) AS product,
  trim(r.comment) AS comment;
~~~

Kết quả có đánh giá của An cho `Sách Cypher`. Cypher đọc property `comment` từ quan hệ `r`, rồi áp dụng `trim` và regex trước khi trả về.

### 6.7. Regex không phải bộ kiểm tra dữ liệu hoàn chỉnh

Một regex đơn giản như:

~~~cypher
RETURN
  'an@example.com' =~ '[^@ ]+@[^@ ]+\\.[^@ ]+' AS emailLike;
~~~

có thể nhận diện **một số** chuỗi trông giống email, nhưng không đảm bảo địa chỉ email tồn tại, hợp lệ theo mọi quy tắc hoặc có thể nhận thư. Tương tự, regex kiểm tra định dạng mã không đảm bảo mã là duy nhất; tính duy nhất nên được bảo vệ bằng constraint phù hợp khi mô hình dữ liệu yêu cầu.

Với văn bản nhập từ người dùng, đừng tùy tiện ghép chuỗi đầu vào thành biểu thức Cypher. Dùng **tham số** để tách dữ liệu khỏi câu truy vấn:

~~~cypher
MATCH (p:StringDemoProduct)
WHERE p.sku =~ $skuPattern
RETURN p.sku, p.name;
~~~

Nếu `$skuPattern = 'STR-[0-9]{3}'`, truy vấn có kết quả như ví dụ ở trên. Tuy nhiên, **regex do người dùng tùy ý cung cấp vẫn có rủi ro về ý nghĩa mẫu và chi phí xử lý**. Cần kiểm soát độ dài/độ phức tạp regex hoặc giới hạn mẫu được phép; nếu chỉ tìm chuỗi con, ưu tiên `CONTAINS $keyword`.

## 7. Chuẩn hóa văn bản: những khái niệm dễ nhầm

### 7.1. Vì sao văn bản nhìn giống nhau vẫn có thể khác nhau?

Unicode có thể biểu diễn một ký tự có dấu theo các cách tương đương. Chẳng hạn, ký tự `é` có thể xuất hiện dưới dạng:

- Một code point đã ghép sẵn: `U+00E9`.
- Chữ `e` (`U+0065`) cộng dấu sắc kết hợp (`U+0301`).

Hai cách có thể **hiển thị giống nhau** nhưng chuỗi bên dưới khác về dãy code point. Điều này ảnh hưởng đến việc so sánh tên, từ khóa và khóa đồng nhất nếu dữ liệu đến từ nhiều hệ thống.

### 7.2. Các dạng chuẩn hóa Unicode

| Dạng | Ý nghĩa chính | Trường hợp dùng |
| --- | --- | --- |
| **NFC** | Chuẩn hóa tương đương chính tắc, ưu tiên dạng ghép | Lưu trữ và so sánh văn bản thông thường |
| **NFD** | Tách thành các thành phần chính tắc | Phân tích dấu kết hợp hoặc tiền xử lý văn bản |
| **NFKC** | Chuẩn hóa tương thích rồi ghép | Hợp nhất một số ký tự tương thích có hình thức khác nhau |
| **NFKD** | Chuẩn hóa tương thích rồi tách | Tiền xử lý chuyên biệt theo chính sách ứng dụng |

NFC và NFD duy trì quan hệ **tương đương chính tắc**. NFKC và NFKD còn áp dụng **tương đương tương thích**, có thể làm mất một số khác biệt trình bày hoặc ý nghĩa mà ứng dụng muốn giữ lại. Vì thế, không nên mặc định dùng NFKC/NFKD cho mọi trường dữ liệu như tên riêng hoặc nội dung pháp lý.

### 7.3. normalize() và IS NORMALIZED

Các phiên bản Neo4j hỗ trợ tính năng này (hàm `normalize()` và toán tử `IS NORMALIZED` được bổ sung từ **Neo4j 5.17**) cho phép chuẩn hóa Unicode ngay trong Cypher:

~~~cypher
RETURN
  '\u0065\u0301' = '\u00E9' AS equalBefore,
  normalize('\u0065\u0301', NFC) = '\u00E9' AS equalAfter,
  '\u0065\u0301' IS NORMALIZED AS normalizedBefore,
  normalize('\u0065\u0301') IS NORMALIZED AS normalizedAfter;
~~~

Với môi trường hỗ trợ, kết quả là:

| Cột | Kết quả |
| --- | --- |
| `equalBefore` | `false` |
| `equalAfter` | `true` |
| `normalizedBefore` | `false` |
| `normalizedAfter` | `true` |

Hai biểu thức `'\u0065\u0301'` và `'\u00E9'` lần lượt là cách viết tách và ghép của ký tự `é`. `normalize(input)` mặc định dùng **NFC**; có thể viết tường minh `normalize(input, NFC)`. Đối số `NFC`, `NFD`, `NFKC` hoặc `NFKD` là **từ khóa chuẩn hóa**, không phải chuỗi dữ liệu thông thường.

Có thể kiểm tra một dạng chuẩn hóa khác:

~~~cypher
RETURN
  '\u00E9' IS NFC NORMALIZED AS isNfc,
  '\u00E9' IS NFD NORMALIZED AS isNfd,
  normalize('\u00E9', NFD) IS NFD NORMALIZED AS afterNfd;
~~~

Kết quả là `true`, `false`, `true`. Nếu triển khai trên Neo4j cũ hơn 5.17, hãy chuẩn hóa văn bản tại tầng nhập dữ liệu hoặc ứng dụng trước khi gửi truy vấn.

### 7.4. NFC không có nghĩa là bỏ dấu tiếng Việt

~~~cypher
RETURN
  normalize('Cà phê', NFC) AS preservedAccent,
  normalize('Cà phê', NFC) = 'Ca phe' AS sameAsUnaccented;
~~~

`preservedAccent` vẫn là `Cà phê`; `sameAsUnaccented` là `false`. Chuẩn hóa Unicode bảo toàn dấu theo quan hệ tương đương chính tắc, chứ không chuyển nội dung tiếng Việt thành không dấu.

Nếu ứng dụng cần tìm `'Ca phe'` để khớp với `'Cà phê'`, cần thiết kế **quy trình tìm kiếm không dấu** riêng, chẳng hạn tại Java/ETL: chuẩn hóa NFD, xử lý các dấu kết hợp và quy tắc riêng cho `đ/Đ`, sau đó chuyển về chữ thường. Đây là một lựa chọn nghiệp vụ, không nên áp dụng phá hủy dữ liệu hiển thị gốc.

### 7.5. Ba tầng chuẩn hóa thường gặp

Một pipeline xử lý từ khóa có thể gồm:

1. **Làm sạch hình thức:** loại khoảng trắng thừa ở đầu/cuối bằng `trim()`.
2. **Thống nhất hoa/thường:** `toLower()` theo chính sách tra cứu.
3. **Thống nhất Unicode:** `normalize(..., NFC)`.

~~~cypher
WITH '  NEO4J  ' AS rawKeyword
RETURN
  rawKeyword,
  trim(rawKeyword) AS trimmed,
  toLower(trim(rawKeyword)) AS lowercase,
  normalize(toLower(trim(rawKeyword)), NFC) AS normalized;
~~~

Kết quả cuối là `'neo4j'`. Đây là pipeline hữu ích cho **so khớp không phân biệt hoa/thường và khác biệt mã hóa Unicode chính tắc**, nhưng chưa loại bỏ dấu, chưa gom nhiều khoảng trắng nằm **giữa** chuỗi và chưa sửa lỗi chính tả.

### 7.6. Không áp dụng chuyển đổi mất mát lên dữ liệu gốc khi chưa cần

Với tên người, địa danh và nội dung tiếng Việt, giữ bản gốc là điều quan trọng. Ví dụ `'Lê'` và `'Le'` có thể là những tên khác nhau. Một trường tìm kiếm đã bỏ dấu chỉ nên dùng để **gợi ý ứng viên khớp**, thay vì làm khóa duy nhất để đồng nhất hoặc gộp hai thực thể.

Trong property graph có nhiều nguồn tích hợp, bạn có thể lưu riêng:

| Property | Nội dung | Cách dùng |
| --- | --- | --- |
| `p.name` | Tên gốc có dấu, đúng nội dung hiển thị | UI, báo cáo, kiểm tra thủ công |
| `p.searchName` | Tên đã chuẩn hóa theo chính sách | Tìm kiếm, lọc |
| `p.sku` | Mã định danh nghiệp vụ | Đối chiếu chính xác và constraint nếu cần |

Đừng tự thay `p.name` bằng chuỗi không dấu chỉ để truy vấn `CONTAINS` trở nên dễ viết.

## 8. Quy trình chuẩn hóa tìm kiếm trên đồ thị

### 8.1. Tạo property tìm kiếm riêng

Giả sử hệ thống chọn chính sách: bỏ khoảng trắng ở hai đầu, chuyển thành chữ thường và chuẩn hóa NFC. Trong database thực hành có Neo4j 5.17+, có thể chạy:

~~~cypher
MATCH (p:StringDemoProduct)
WHERE p.name IS NOT NULL
SET p.searchName = normalize(toLower(trim(p.name)), NFC)
RETURN p.sku, p.name, p.searchName
ORDER BY p.sku;
~~~

Ví dụ `STR-002.searchName` thành `'khóa học neo4j'`. `STR-003.searchName` thành `'cà phê dữ liệu'`: dấu tiếng Việt được giữ nguyên.

**Cảnh báo thực hành:** đoạn `SET` này **ghi thêm property**. Nếu dữ liệu gốc thay đổi, ứng dụng cũng phải cập nhật `searchName` theo cùng quy tắc, nếu không trường phục vụ tìm kiếm sẽ bị cũ.

### 8.2. Tìm kiếm bằng từ khóa đã áp dụng cùng chính sách

~~~cypher
WITH normalize(toLower(trim($keyword)), NFC) AS keyword
MATCH (p:StringDemoProduct)
WHERE p.searchName CONTAINS keyword
RETURN p.sku, p.name, p.searchName
ORDER BY p.sku;
~~~

Với `$keyword = '  NEO4J '`, kết quả là `STR-002`. Truy vấn chỉ chuẩn hóa từ khóa tham số, còn property đã được chuẩn hóa **từ trước**. Đây là cách làm tốt khi nhiều truy vấn phải dùng cùng quy tắc.

Chú ý: nếu `$keyword` bằng `null`, các hàm chuỗi sẽ trả `null` và điều kiện `WHERE` không giữ dòng nào. Ứng dụng nên quyết định rõ liệu từ khóa trống có nghĩa là “xem tất cả”, “không trả kết quả” hay “dữ liệu yêu cầu không hợp lệ”.

### 8.3. Chuẩn hóa khoảng trắng giữa các từ

`trim()` chỉ xử lý khoảng trắng ở đầu/cuối. Với chuỗi `'Neo4j    Cypher'`, các khoảng trắng giữa hai từ vẫn tồn tại:

~~~cypher
RETURN
  trim('  Neo4j    Cypher  ') AS trimmed,
  replace('Neo4j    Cypher', '    ', ' ') AS simpleReplacement;
~~~

`replace` ở trên chỉ thay **đúng bốn** khoảng trắng liên tiếp; nó không giải quyết mọi chuỗi khoảng trắng dài khác nhau. Nếu cần quy tắc thay mọi dãy whitespace thành một dấu cách, nên xử lý tại ETL/Java hoặc dùng hàm thay thế regex nếu phiên bản Neo4j tương ứng hỗ trợ.

Đối với các hệ thống cần tìm kiếm tự do, việc chuẩn hóa nên được kiểm thử bằng dữ liệu tiếng Việt có khoảng trắng, dấu câu, ký tự xuống dòng và trường hợp `null`.

## 9. Tìm kiếm có index và lựa chọn loại truy vấn

### 9.1. Vì sao cách viết biểu thức ảnh hưởng tới index?

So sánh:

~~~cypher
// Hàm chạy trực tiếp trên property trong điều kiện WHERE.
MATCH (p:StringDemoProduct)
WHERE toLower(p.name) CONTAINS 'neo4j'
RETURN p.sku, p.name;
~~~

với:

~~~cypher
// Lọc trên property đã chuẩn hóa từ trước.
MATCH (p:StringDemoProduct)
WHERE p.searchName CONTAINS 'neo4j'
RETURN p.sku, p.name;
~~~

Với dữ liệu được chuẩn bị đúng, cả hai có thể cho cùng kết quả. Tuy nhiên, cách thứ hai dùng điều kiện trực tiếp trên property `searchName`, giúp bộ tối ưu có cơ hội tận dụng index phù hợp nếu có. Điều kiện bọc `p.name` trong hàm không đồng nghĩa với việc Neo4j có sẵn một index cho biểu thức đó.

### 9.2. Range index, text index và full-text index

| Nhu cầu | Lựa chọn thường phù hợp | Điểm cần nhớ |
| --- | --- | --- |
| Tìm mã chính xác `sku = $sku` | Range index hoặc constraint duy nhất trên mã | Ưu tiên khóa định danh ổn định |
| Tìm tên bắt đầu với tiền tố | Điều kiện `STARTS WITH` và index phù hợp | Kiểm tra kế hoạch thực tế |
| Tìm đoạn con / hậu tố | Text index hỗ trợ `CONTAINS`, `ENDS WITH` | Có thể dùng index tùy kế hoạch |
| Tìm tài liệu theo từ khóa, xếp hạng mức liên quan | Full-text index | Cơ chế phân tích văn bản khác so với so khớp chuỗi literal |
| Lọc bằng regex phức tạp | `=~` | Có thể tốn chi phí lớn; đừng giả định sử dụng index |

Ví dụ tạo text index trong database thực hành:

~~~cypher
CREATE TEXT INDEX string_demo_search_name IF NOT EXISTS
FOR (p:StringDemoProduct) ON (p.searchName);
~~~

Sau khi tạo index, hãy kiểm tra bằng `EXPLAIN` hoặc `PROFILE` với tập dữ liệu đủ đại diện:

~~~cypher
EXPLAIN
MATCH (p:StringDemoProduct)
WHERE p.searchName CONTAINS $keyword
RETURN p.sku, p.name;
~~~

Trong kế hoạch, các thao tác truy cập qua index có thể mang tên như `NodeIndexContainsScan`. Bộ tối ưu quyết định dùng index dựa trên loại index, thống kê, kích thước dữ liệu và câu truy vấn. Với bộ dữ liệu chỉ bốn node, quét node cũng có thể hợp lý.

Đừng mặc định text index tương đương full-text index: text index phục vụ các điều kiện chuỗi cụ thể; full-text index được thiết kế cho tra cứu từ ngữ và có thể có analyzer, cách tách token và điểm liên quan riêng.

### 9.3. Một phương án tăng tốc tìm kiếm không dấu

Nếu cần tìm `'ca phe'` để trả `'Cà phê dữ liệu'`, hãy tạo giá trị `searchNameAscii` ở tầng nhập dữ liệu hoặc ứng dụng Java theo quy tắc bỏ dấu đã chọn. Sau đó truy vấn:

~~~cypher
MATCH (p:StringDemoProduct)
WHERE p.searchNameAscii CONTAINS $normalizedKeyword
RETURN p.sku, p.name;
~~~

**Điều kiện tiên quyết:** các node đã có `searchNameAscii` và tham số `$normalizedKeyword` được chuẩn hóa bằng **cùng** thuật toán. Truy vấn không thể trả kết quả như mong đợi nếu chưa tạo dữ liệu tìm kiếm. Việc chọn tên property `searchNameAscii` chỉ là ví dụ triển khai, không phải tính năng built-in tự sinh của Neo4j.

## 10. Kết hợp văn bản với node và relationship

### 10.1. Định dạng kết quả truy vấn đồ thị

~~~cypher
MATCH (c:StringDemoCustomer)-[r:STRING_DEMO_REVIEWED]->(p:StringDemoProduct)
RETURN
  c.name AS customer,
  trim(p.name) AS product,
  toUpper(p.category) AS category,
  trim(r.comment) AS cleanedComment,
  c.name || ' đánh giá ' || trim(p.name) AS summary;
~~~

Với dữ liệu mẫu, `summary` là `An đánh giá Sách Cypher`. Phép nối dùng property từ **hai node** và `trim()` dùng cho property trên **relationship**.

### 10.2. Tìm các quan hệ có nhận xét chứa từ khóa

~~~cypher
WITH 'HỮU ÍCH' AS rawTerm
WITH toLower(trim(rawTerm)) AS term
MATCH (c:StringDemoCustomer)-[r:STRING_DEMO_REVIEWED]->(p:StringDemoProduct)
WHERE toLower(r.comment) CONTAINS term
RETURN c.name, p.name, trim(r.comment) AS comment;
~~~

Kết quả có đánh giá của An. Trong ví dụ này, `toLower()` giúp so sánh chữ hoa/chữ thường, còn dấu trong `'hữu ích'` vẫn được giữ.

### 10.3. OPTIONAL MATCH và văn bản có thể thiếu

~~~cypher
MATCH (c:StringDemoCustomer)
OPTIONAL MATCH (c)-[r:STRING_DEMO_REVIEWED]->(p:StringDemoProduct)
RETURN
  c.name AS customer,
  coalesce(trim(r.comment), 'Chưa có đánh giá') AS commentLabel,
  coalesce(trim(p.name), 'Chưa có sản phẩm') AS productLabel
ORDER BY c.name;
~~~

An có đánh giá, còn Bình nhận giá trị dự phòng. `OPTIONAL MATCH` giúp giữ Bình dù không có relationship `STRING_DEMO_REVIEWED`. Nếu dùng `MATCH` bắt buộc cho quan hệ, Bình sẽ không có trong kết quả.

## 11. Tích hợp xử lý văn bản với Java Driver và Spring Data Neo4j

### 11.1. Truy vấn có tham số từ Java Driver

Trong ứng dụng Java, nên dùng tham số cho từ khóa, mẫu mã sản phẩm và giá trị tên. Ví dụ minh họa phần sử dụng `Driver driver` đã được cấu hình sẵn:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.Values;
import java.util.List;

String keyword = "neo4j";

try (Session session = driver.session()) {
    List<String> names = session.executeRead(tx ->
        tx.run(
            """
            MATCH (p:StringDemoProduct)
            WHERE toLower(trim(p.name)) CONTAINS toLower($keyword)
            RETURN trim(p.name) AS name
            ORDER BY name
            """,
            Values.parameters("keyword", keyword)
        ).list(row -> row.get("name").asString())
    );

    names.forEach(System.out::println);
}
~~~

Kết quả in ra `Khóa học Neo4j`. Ví dụ trên cố ý chỉ dùng `toLower()` và `trim()` để tương thích rộng với các môi trường Neo4j thông dụng. Với hệ thống lớn có property tìm kiếm đã chuẩn hóa, thay điều kiện bằng `p.searchName CONTAINS $keyword` và bảo đảm biến `keyword` được chuẩn hóa đúng từ trước.

Khi dùng Spring Data Neo4j với truy vấn `@Query`, nguyên tắc tương tự: truyền giá trị qua tham số, đặt alias rõ ràng cho kết quả, và ánh xạ `null` đúng với kiểu nullable của DTO/projection.

### 11.2. Chuẩn hóa Unicode và tìm kiếm không dấu trong Java

Java cung cấp `java.text.Normalizer` để thực hiện các dạng chuẩn hóa Unicode. Ví dụ hàm chuẩn hóa tìm kiếm **không dấu** theo một chính sách cụ thể:

~~~java
import java.text.Normalizer;
import java.util.Locale;

public final class SearchText {
    private SearchText() {}

    public static String withoutVietnameseAccents(String input) {
        if (input == null) {
            return null;
        }

        String decomposed = Normalizer.normalize(
            input.strip().toLowerCase(Locale.ROOT),
            Normalizer.Form.NFD
        );

        return decomposed
            .replaceAll("\\p{M}+", "")  // Xóa các dấu kết hợp.
            .replace('đ', 'd')            // NFD không tự chuyển đ.
            .replaceAll("\\s+", " ");   // Gom khoảng trắng.
    }
}
~~~

~~~java
System.out.println(
    SearchText.withoutVietnameseAccents("  Cà  phê dữ liệu ")
);
// ca phe du lieu
~~~

Hàm này **làm mất thông tin dấu** theo chủ ý, vì vậy chỉ nên dùng cho **trường phục vụ tìm kiếm**. Không nên thay thế tên gốc hiển thị bằng kết quả của hàm. Với sản phẩm thật, cần bổ sung kiểm thử Unicode, dấu câu, ký tự đặc biệt, tên riêng và những trường hợp nhiều ngôn ngữ.

### 11.3. Chuẩn hóa dữ liệu nhập trước khi ghi vào graph

Một luồng nhập dữ liệu điển hình:

~~~mermaid
flowchart LR
    A[Dữ liệu nhập: CSV hoặc API] --> B[Kiểm tra null và độ dài]
    B --> C[Trim và chuẩn hóa Unicode]
    C --> D[Tạo trường tìm kiếm theo chính sách]
    D --> E[MERGE node bằng khóa ổn định]
    E --> F[Lưu name gốc và searchName]
    F --> G[Query với tham số và index]
~~~

Điểm quan trọng là **MERGE theo khóa định danh** (chẳng hạn SKU), không MERGE theo tên đã loại dấu nếu thuật toán có thể gom hai tên thực sự khác nhau thành một chuỗi. Với mô hình đồ thị, việc gộp nhầm node còn ảnh hưởng đến tất cả relationship nối với node đó.

## 12. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Cho rằng `CONTAINS` không phân biệt chữ hoa/chữ thường | Không tìm được `NEO4J` khi nhập `neo4j` | Thống nhất chính sách `toLower()` hoặc trường tìm kiếm |
| Cho rằng `normalize()` xóa dấu tiếng Việt | `Cà phê` vẫn khác `Ca phe` | Tách thuật toán bỏ dấu nếu thật sự cần |
| Dùng `replace(s, '.*', '')` như regex replace | Không thay mọi ký tự | `replace()` là thay chuỗi literal |
| Dùng `=~ 'neo4j'` để tìm từ nằm giữa chuỗi | Không khớp `Khóa học Neo4j` | Viết `'(?i).*neo4j.*'` hoặc dùng `CONTAINS` |
| Quên escape dấu chấm trong regex | `.` khớp cả ký tự không phải dấu chấm | Escape regex và chuỗi Cypher đúng hai lớp |
| Truyền nguyên input thành cấu trúc regex phức tạp | Mẫu khó kiểm soát, có thể gây tốn tài nguyên | Hạn chế regex, dùng tham số và giới hạn mẫu |
| Dùng `trim()` để xóa mọi khoảng trắng trong chuỗi | Khoảng trắng ở giữa vẫn còn | Quy định thêm bước gom khoảng trắng |
| Dùng `size()` như số byte UTF-8 | Tính sai giới hạn byte của hệ thống khác | Phân biệt ký tự Unicode và byte |
| Bỏ qua `null` trước khi ghép chuỗi | Kết quả hiển thị thành `null` | Dùng `coalesce` theo quy tắc nghiệp vụ |
| Ghi đè tên gốc bằng tên đã bỏ dấu | Mất khả năng hiển thị chính xác, có thể gây trùng | Lưu riêng property phục vụ tìm kiếm |
| Tưởng regex luôn dùng được text index | Truy vấn có thể phải kiểm tra nhiều bản ghi | Dùng `EXPLAIN` / `PROFILE` và chọn toán tử |
| Chuẩn hóa dữ liệu lưu nhưng không chuẩn hóa đầu vào tìm kiếm | Cùng tên vẫn có thể không khớp | Dùng cùng thuật toán hai phía |
| Dùng tên chuẩn hóa làm khóa duy nhất | Có thể gộp hai thực thể khác nhau | Dùng mã định danh nghiệp vụ và constraint phù hợp |

## 13. Bài tập thực hành có đáp án

### Bài 1. Làm sạch văn bản đầu vào

Cho chuỗi `'   NEO4J Cypher   '`. Hãy lấy chuỗi không có khoảng trắng đầu/cuối và chuyển về chữ thường.

~~~cypher
WITH '   NEO4J Cypher   ' AS rawText
RETURN toLower(trim(rawText)) AS cleaned;
~~~

**Đáp án:** `cleaned = 'neo4j cypher'`.

### Bài 2. Tách mã SKU thành hai phần

Cho chuỗi `STR-001`. Hãy tạo hai cột `prefix` và `sequence`.

~~~cypher
WITH 'STR-001' AS sku
RETURN
  split(sku, '-')[0] AS prefix,
  split(sku, '-')[1] AS sequence;
~~~

**Đáp án:** `prefix = 'STR'`, `sequence = '001'`. Cách này giả định SKU luôn đúng dạng `prefix-sequence`; nếu dữ liệu thực có định dạng khác, cần kiểm tra trước khi truy cập phần tử danh sách.

### Bài 3. Dùng regex kiểm tra định dạng mã

Yêu cầu mã phải bắt đầu bằng `STR-` và có đúng ba chữ số. Hãy lọc các mã hợp lệ:

~~~cypher
UNWIND ['STR-001', 'STR-09', 'STR-ABC', 'STR-100'] AS sku
WITH sku
WHERE sku =~ 'STR-[0-9]{3}'
RETURN sku
ORDER BY sku;
~~~

**Đáp án:** `STR-001` và `STR-100`.

### Bài 4. So sánh Unicode trước và sau chuẩn hóa

Yêu cầu kiểm tra hai cách viết ký tự `é` có tương đương sau khi chuẩn hóa hay không:

~~~cypher
RETURN
  '\u0065\u0301' = '\u00E9' AS rawEqual,
  normalize('\u0065\u0301', NFC) =
    normalize('\u00E9', NFC) AS normalizedEqual;
~~~

**Đáp án trên Neo4j 5.17+:** `rawEqual = false` và `normalizedEqual = true`. Kết quả phản ánh tương đương Unicode chính tắc; nó không chứng minh rằng hai tên riêng viết khác dấu phải được coi là một.

### Bài 5. Tìm tên có tiền tố sau khi làm sạch

Yêu cầu: tìm sản phẩm có tên bắt đầu bằng `Khóa học`, dù dữ liệu có khoảng trắng dư:

~~~cypher
MATCH (p:StringDemoProduct)
WHERE trim(p.name) STARTS WITH 'Khóa học'
RETURN p.sku, trim(p.name) AS name;
~~~

**Đáp án:** `STR-002`. Trên tập dữ liệu lớn, có thể lưu tên đã làm sạch sẵn để tránh gọi `trim(p.name)` trong điều kiện tìm kiếm ở mỗi truy vấn.

### Bài 6. Tìm mô tả với từ khóa không phân biệt hoa/thường

~~~cypher
WITH '   neo4j  ' AS input
WITH toLower(trim(input)) AS keyword
MATCH (p:StringDemoProduct)
WHERE toLower(p.description) CONTAINS keyword
RETURN p.sku, trim(p.name) AS name;
~~~

**Đáp án:** `STR-002`. Sản phẩm `STR-004` không có mô tả, nên phép kiểm tra trên `p.description` không trả `true`.

### Bài 7. Đếm sản phẩm chưa có mô tả hữu ích

~~~cypher
MATCH (p:StringDemoProduct)
RETURN
  count(*) AS totalProducts,
  sum(
    CASE
      WHEN p.description IS NULL OR trim(p.description) = ''
      THEN 1
      ELSE 0
    END
  ) AS missingDescription;
~~~

**Đáp án:** `totalProducts = 4` và `missingDescription = 1`. Dữ liệu thiếu được phân biệt với mô tả không rỗng.

### Bài 8. Thiết kế tìm kiếm không dấu

Yêu cầu: cho phép người dùng gõ `ca phe` để tìm `Cà phê dữ liệu` trong đồ thị. Hãy mô tả giải pháp đủ an toàn cho dữ liệu gốc.

**Gợi ý đáp án:** Giữ `p.name = 'Cà phê dữ liệu'`. Ở tầng Java/ETL, sinh `p.searchNameAscii = 'ca phe du lieu'` bằng quy tắc chuẩn hóa đã thống nhất. Chuẩn hóa từ khóa người dùng theo **cùng** quy tắc rồi gọi:

~~~cypher
MATCH (p:StringDemoProduct)
WHERE p.searchNameAscii CONTAINS $keyword
RETURN p.sku, p.name;
~~~

Với tham số `$keyword = 'ca phe'`, kết quả dự kiến là `STR-003`, **sau khi** đã cập nhật `searchNameAscii` cho sản phẩm. Chỉ số hóa trường tìm kiếm theo nhu cầu truy vấn; không thay tên gốc bằng chuỗi không dấu và không dùng tên chuẩn hóa để gộp node.

## 14. Tổng kết và ghi nhớ

- Các hàm `trim()`, `toLower()`, `toUpper()`, `left()`, `right()`, `substring()`, `replace()`, `split()` và `size()` giúp làm sạch và xử lý văn bản trên cả node lẫn relationship.
- `STARTS WITH`, `ENDS WITH` và `CONTAINS` phù hợp với kiểm tra tiền tố, hậu tố, đoạn con; theo mặc định chúng phân biệt hoa/thường.
- Toán tử `=~` dùng regex theo quy tắc Java, khớp toàn bộ chuỗi; hãy kiểm soát cờ, ký tự đặc biệt và escape ở cả lớp chuỗi Cypher lẫn regex.
- `normalize()` và `IS NORMALIZED` hỗ trợ chuẩn hóa Unicode trên Neo4j từ 5.17. **NFC không xóa dấu tiếng Việt** và không thay thế cơ chế tìm kiếm gần đúng.
- Dữ liệu `null` khác chuỗi rỗng; dùng `IS NULL`, `coalesce()` và quy tắc nghiệp vụ rõ ràng trước khi nối chuỗi hoặc hiển thị.
- Với dữ liệu lớn, cân nhắc lưu **trường tìm kiếm riêng**, chọn text/full-text index phù hợp và quan sát `EXPLAIN` hoặc `PROFILE`.
- Khi dùng Java Driver hoặc Spring Data Neo4j, truyền dữ liệu bằng tham số, thống nhất thuật toán chuẩn hóa giữa dữ liệu lưu và từ khóa, đồng thời giữ nguyên tên gốc có dấu để hiển thị chính xác.

Việc xử lý chuỗi đúng giúp truy vấn Cypher tìm được dữ liệu liên kết đáng tin cậy, tránh đồng nhất sai thực thể khi nhập dữ liệu và làm nền tảng cho các tính năng tìm kiếm trên hệ thống đồ thị Neo4j.

### Tham khảo chính thức

- [Neo4j Cypher Manual – String functions](https://neo4j.com/docs/cypher-manual/current/functions/string/)
- [Neo4j Cypher Manual – String operators và regular expressions](https://neo4j.com/docs/cypher-manual/current/expressions/predicates/string-operators/)
- [Neo4j Cypher Manual – Search performance indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-performance-indexes/)
- [Neo4j Cypher Manual – Parameters](https://neo4j.com/docs/cypher-manual/current/syntax/parameters/)

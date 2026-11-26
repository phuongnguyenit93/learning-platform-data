# CASE để biểu diễn rẽ nhánh trong kết quả truy vấn Cypher

Khi làm việc với **property graph** trong Neo4j, dữ liệu thô thường chưa đủ để đưa trực tiếp lên giao diện hoặc báo cáo. Từ các thuộc tính của node và relationship, ứng dụng còn cần suy ra những giá trị như “Sắp hết hàng”, “Khách VIP”, “Đơn hàng giá trị cao” hoặc “Chưa có giao dịch”. Cypher cung cấp biểu thức `CASE` để chọn **một kết quả dựa trên điều kiện** ngay trong câu truy vấn.

Bài học thuộc chương **Biểu thức và hàm** của mô-đun **DATABASE_ENGINE_GRAPH_NEO4J**. Nội dung tập trung vào hai dạng `CASE` cơ bản, thứ tự xét nhánh, cách xử lý `null`, cách kết hợp với `MATCH`, `OPTIONAL MATCH`, `WITH`, `RETURN`, `ORDER BY` và những lưu ý khi đưa kết quả vào ứng dụng Java Driver hoặc Spring Data Neo4j.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao `CASE` là **biểu thức trả về giá trị**, khác với các mệnh đề điều khiển luồng trong ngôn ngữ lập trình.
- Viết dạng `CASE expression WHEN value THEN result ... ELSE ... END` để ánh xạ một giá trị sang nhãn.
- Viết dạng `CASE WHEN condition THEN result ... ELSE ... END` để biểu diễn điều kiện phức hợp hoặc khoảng giá trị.
- Hiểu thứ tự ưu tiên nhánh, nhánh `ELSE` và tác động của `null`.
- Kết hợp `CASE` với property của node, relationship, truy vấn không bắt buộc và phép tổng hợp.
- Thiết kế cột kết quả có kiểu ổn định, dễ ánh xạ khi truy vấn qua Java Driver hoặc Spring Data Neo4j.
- Nhận diện khi nên dùng `CASE`, `coalesce()`, `WHERE` hay xử lý dữ liệu ở tầng ứng dụng.

## 2. CASE là biểu thức, không phải câu lệnh điều khiển

### 2.1. Kết quả của CASE dùng được ở đâu?

Trong Cypher, `CASE ... END` tạo ra **một giá trị**. Giá trị đó có thể được đặt tên bằng `AS`, dùng để sắp xếp hoặc chuyển tiếp qua `WITH`:

~~~cypher
RETURN
  CASE
    WHEN 8 >= 5 THEN 'Đạt'
    ELSE 'Chưa đạt'
  END AS assessment;
~~~

Kết quả là một cột `assessment` với giá trị `'Đạt'`. Truy vấn không chạy một khối lệnh `THEN` như trong Java; nó **đánh giá biểu thức và chọn giá trị trả về**.

| Vị trí | Ví dụ sử dụng | Mục tiêu |
| --- | --- | --- |
| `RETURN` | `RETURN CASE WHEN p.stock = 0 THEN 'Hết' ELSE 'Còn' END AS label` | Hiển thị nhãn được tính |
| `WITH` | `WITH p, CASE WHEN p.price >= 500000 THEN 'Cao' ELSE 'Thấp' END AS priceGroup` | Tạo giá trị trung gian để dùng tiếp |
| `ORDER BY` | `ORDER BY CASE WHEN p.active = false THEN 1 ELSE 0 END` | Sắp xếp theo thứ tự nghiệp vụ |
| `SET` | `SET p.stockStatus = CASE WHEN p.stock = 0 THEN 'Hết' ELSE 'Còn' END` | Ghi một property từ biểu thức |
| Phép tổng hợp | `sum(CASE WHEN p.active = true THEN 1 ELSE 0 END)` | Đếm có điều kiện |

`CASE` không tự loại bỏ dòng khỏi tập kết quả. Khi cần lọc dòng, `WHERE` thường diễn đạt trực tiếp hơn; `CASE` chủ yếu quyết định **giá trị của một biểu thức**.

### 2.2. Hai dạng CASE cơ bản

**Dạng đơn giản (simple CASE)** so sánh một biểu thức với các giá trị được liệt kê:

~~~cypher
CASE expression
  WHEN value1 THEN result1
  WHEN value2 THEN result2
  ELSE fallback
END
~~~

**Dạng có điều kiện (generic CASE, hay searched CASE)** đánh giá từng điều kiện Boolean:

~~~cypher
CASE
  WHEN condition1 THEN result1
  WHEN condition2 THEN result2
  ELSE fallback
END
~~~

Cả hai đều lần lượt xét các nhánh `WHEN` và lấy kết quả của **nhánh phù hợp đầu tiên**. Nếu không có nhánh phù hợp, dùng `ELSE`. Nếu không khai báo `ELSE`, kết quả là `null`.

| Tiêu chí | Simple CASE | Generic CASE |
| --- | --- | --- |
| Cách kiểm tra | So sánh một giá trị chung với từng giá trị `WHEN` | Mỗi `WHEN` là điều kiện Boolean độc lập |
| Phù hợp | Ánh xạ mã trạng thái, hạng khách hàng, loại sự kiện | Ngưỡng số, kết hợp `AND`/`OR`, kiểm tra `IS NULL` |
| Ví dụ | `CASE c.tier WHEN 'GOLD' THEN ... END` | `CASE WHEN c.score >= 80 THEN ... END` |
| Xử lý `null` | Phải chủ động dùng phương án phù hợp; `WHEN null` không kiểm tra thiếu giá trị theo cách mong muốn | Có thể dùng `WHEN c.tier IS NULL THEN ...` |
| Khả năng biểu đạt | Ngắn gọn khi so khớp với giá trị cố định | Linh hoạt nhất khi mỗi nhánh có quy tắc riêng |

**Quy ước trong bài:** tập trung vào hai dạng thông dụng có thể áp dụng rộng rãi. Một số phiên bản Neo4j hỗ trợ thêm các biến thể cú pháp `CASE`; khi sử dụng tính năng đặc thù phiên bản, hãy kiểm tra tài liệu Cypher tương ứng với hệ thống đang chạy.

## 3. Chuẩn bị dữ liệu đồ thị mẫu

Các ví dụ chỉ dùng `RETURN` có thể chạy độc lập. Để thử các truy vấn `MATCH`, hãy tạo dữ liệu minh họa dưới đây trong một **database thực hành**. Đoạn này cố ý dùng các label và relationship type có tiền tố `CaseDemo` để dễ phân biệt với dữ liệu nghiệp vụ.

~~~cypher
// Ba khách hàng, trong đó Chi chưa được gán hạng và trạng thái xác minh.
MERGE (an:CaseDemoCustomer {code: 'C001'})
SET an.name = 'An', an.tier = 'GOLD', an.verified = true

MERGE (binh:CaseDemoCustomer {code: 'C002'})
SET binh.name = 'Bình', binh.tier = 'SILVER', binh.verified = false

MERGE (chi:CaseDemoCustomer {code: 'C003'})
SET chi.name = 'Chi'
REMOVE chi.tier, chi.verified

// Bốn sản phẩm có nhiều trạng thái tồn kho.
MERGE (book:CaseDemoProduct {sku: 'P001'})
SET book.name = 'Sách Cypher',
    book.price = 320000,
    book.stock = 12,
    book.active = true

MERGE (course:CaseDemoProduct {sku: 'P002'})
SET course.name = 'Khóa học Neo4j',
    course.price = 850000,
    course.stock = 2,
    course.active = true

MERGE (notebook:CaseDemoProduct {sku: 'P003'})
SET notebook.name = 'Sổ tay',
    notebook.price = 90000,
    notebook.stock = 0,
    notebook.active = false

MERGE (gift:CaseDemoProduct {sku: 'P004'})
SET gift.name = 'Thẻ quà tặng',
    gift.price = 150000,
    gift.active = true
REMOVE gift.stock

// Hai quan hệ mua hàng; đơn của Bình chưa lưu discount.
MERGE (an)-[r1:CASE_DEMO_BUYS]->(book)
SET r1.quantity = 2, r1.discount = 0.1

MERGE (binh)-[r2:CASE_DEMO_BUYS]->(course)
SET r2.quantity = 1
REMOVE r2.discount;
~~~

Đồ thị có dạng:

~~~text
(An:CaseDemoCustomer {tier:'GOLD'})
      └──[:CASE_DEMO_BUYS {quantity:2, discount:0.1}]──>
                                           (Sách Cypher:CaseDemoProduct)

(Bình:CaseDemoCustomer {tier:'SILVER'})
      └──[:CASE_DEMO_BUYS {quantity:1}]──────────────────>
                                           (Khóa học Neo4j:CaseDemoProduct)

(Chi:CaseDemoCustomer {tier: <thiếu>})    (không có quan hệ mua)
~~~

Thông tin quan trọng cho các ví dụ:

| Sản phẩm | Giá (VND) | `stock` | `active` |
| --- | ---: | ---: | --- |
| Sách Cypher (`P001`) | 320.000 | 12 | `true` |
| Khóa học Neo4j (`P002`) | 850.000 | 2 | `true` |
| Sổ tay (`P003`) | 90.000 | 0 | `false` |
| Thẻ quà tặng (`P004`) | 150.000 | Không có property | `true` |

Đặc biệt, `P004.stock` cho ra `null` vì property không tồn tại. Điều này **khác** với số lượng tồn kho bằng `0`.

## 4. Simple CASE: ánh xạ một giá trị sang nhãn

### 4.1. Cú pháp và ví dụ tối giản

~~~cypher
RETURN
  CASE 'GOLD'
    WHEN 'GOLD' THEN 'Ưu tiên cao'
    WHEN 'SILVER' THEN 'Ưu tiên'
    WHEN 'BRONZE' THEN 'Tiêu chuẩn'
    ELSE 'Chưa phân hạng'
  END AS customerTier;
~~~

Kết quả: `customerTier = 'Ưu tiên cao'`.

Giá trị `'GOLD'` đứng sau `CASE` được so sánh lần lượt với mỗi giá trị sau `WHEN`. Khi tìm thấy giá trị bằng nhau, Cypher trả về biểu thức sau `THEN` và không chọn các nhánh còn lại.

### 4.2. Ánh xạ property của node

~~~cypher
MATCH (c:CaseDemoCustomer)
RETURN
  c.code AS customerCode,
  c.name AS customer,
  c.tier AS rawTier,
  CASE c.tier
    WHEN 'GOLD' THEN 'Khách vàng'
    WHEN 'SILVER' THEN 'Khách bạc'
    WHEN 'BRONZE' THEN 'Khách đồng'
    ELSE 'Chưa có hạng'
  END AS tierLabel
ORDER BY customerCode;
~~~

Kết quả mẫu:

| `customer` | `rawTier` | `tierLabel` |
| --- | --- | --- |
| An | `GOLD` | Khách vàng |
| Bình | `SILVER` | Khách bạc |
| Chi | `null` | Chưa có hạng |

Với Chi, không nhánh nào khớp vì `tier` vắng mặt, nên kết quả đi vào `ELSE`. Simple `CASE` rất phù hợp khi hệ thống lưu trạng thái bằng mã ngắn và giao diện cần một nhãn dễ đọc.

### 4.3. ELSE là phương án dự phòng

~~~cypher
RETURN
  CASE 'PLATINUM'
    WHEN 'GOLD' THEN 'Khách vàng'
    WHEN 'SILVER' THEN 'Khách bạc'
    ELSE 'Hạng khác hoặc chưa xác định'
  END AS tierLabel;
~~~

Kết quả là `'Hạng khác hoặc chưa xác định'`. Trong ví dụ này, `ELSE` gộp cả **mã mới không có trong bảng ánh xạ** và **giá trị thiếu**. Đó có thể là lựa chọn hợp lý cho nhãn giao diện, nhưng chưa đủ nếu cần phân tích chất lượng dữ liệu.

Nếu không viết `ELSE`:

~~~cypher
RETURN
  CASE 'PLATINUM'
    WHEN 'GOLD' THEN 'Khách vàng'
    WHEN 'SILVER' THEN 'Khách bạc'
  END AS tierLabel;
~~~

Giá trị trả về là `null`. Quy tắc này được áp dụng cho cả simple CASE lẫn generic CASE.

### 4.4. Vì sao WHEN null không phải phép kiểm tra thiếu dữ liệu?

~~~cypher
RETURN
  CASE null
    WHEN null THEN 'Giá trị thiếu'
    ELSE 'Không khớp'
  END AS result;
~~~

Kết quả là `'Không khớp'`. Với simple CASE thông thường, việc kiểm tra các giá trị dựa vào phép so sánh bằng; trong logic ba giá trị của Cypher, `null = null` cho kết quả `null` chứ không phải `true`. Do đó nhánh `WHEN null` không được chọn theo cách nhiều người kỳ vọng.

Nếu muốn phân biệt giá trị thiếu, hãy dùng **generic CASE** và điều kiện `IS NULL`, hoặc xác định quy tắc dự phòng ngay trước khi thực hiện simple CASE.

## 5. Generic CASE: đánh giá điều kiện Boolean

### 5.1. Một nhánh có thể chứa biểu thức so sánh

~~~cypher
RETURN
  CASE
    WHEN 9 >= 8 THEN 'Giỏi'
    WHEN 9 >= 5 THEN 'Đạt'
    ELSE 'Chưa đạt'
  END AS result;
~~~

Kết quả là `'Giỏi'`. Hai điều kiện đầu tiên đều đúng, nhưng chỉ kết quả của **điều kiện đúng đầu tiên** được chọn. Đây là cơ sở để triển khai các thang phân loại có ngưỡng.

Ví dụ với tham số điểm `$score`:

~~~cypher
WITH $score AS score
RETURN
  score,
  CASE
    WHEN score IS NULL THEN 'Chưa có điểm'
    WHEN score >= 8.0 THEN 'Giỏi'
    WHEN score >= 6.5 THEN 'Khá'
    WHEN score >= 5.0 THEN 'Trung bình'
    ELSE 'Chưa đạt'
  END AS classification;
~~~

Với `score = 7.0`, kết quả là `'Khá'`; với `score = null`, kết quả là `'Chưa có điểm'`. Biểu thức bắt đầu bằng điều kiện xử lý `null`, sau đó xếp các ngưỡng **từ cao xuống thấp**.

### 5.2. Thứ tự nhánh làm thay đổi kết quả

Hai truy vấn sau không tương đương:

~~~cypher
RETURN
  CASE
    WHEN 9 >= 5 THEN 'Đạt'
    WHEN 9 >= 8 THEN 'Giỏi'
    ELSE 'Chưa đạt'
  END AS classification;
~~~

Kết quả là `'Đạt'`. Nhánh `9 >= 8` sẽ không được chọn vì điều kiện `9 >= 5` đã đúng trước đó.

Khi viết thang ngưỡng lồng nhau như `>= 5`, `>= 8`, hãy xét ngưỡng nghiêm ngặt hơn trước. Nếu các điều kiện thực sự loại trừ nhau, thứ tự ít ảnh hưởng hơn, nhưng vẫn nên giữ quy tắc nhất quán để người đọc dễ kiểm tra.

### 5.3. Kết hợp AND, OR, NOT trong WHEN

Điều kiện `WHEN` có thể chứa toàn bộ biểu thức Boolean hợp lệ:

~~~cypher
MATCH (p:CaseDemoProduct)
RETURN
  p.name AS product,
  CASE
    WHEN p.active = false THEN 'Ngừng kinh doanh'
    WHEN p.stock IS NULL THEN 'Chưa cập nhật tồn kho'
    WHEN p.stock = 0 THEN 'Hết hàng'
    WHEN p.stock > 0 AND p.stock <= 3 THEN 'Sắp hết hàng'
    ELSE 'Có thể bán'
  END AS stockStatus
ORDER BY p.sku;
~~~

Kết quả mong đợi:

| Sản phẩm | `stockStatus` | Lý do |
| --- | --- | --- |
| Sách Cypher | Có thể bán | Đang hoạt động, còn 12 |
| Khóa học Neo4j | Sắp hết hàng | Đang hoạt động, còn 2 |
| Sổ tay | Ngừng kinh doanh | `active = false` được ưu tiên |
| Thẻ quà tặng | Chưa cập nhật tồn kho | `stock` không tồn tại |

Điểm quan trọng: Sổ tay vừa có `stock = 0` vừa có `active = false`. Vì nhánh “Ngừng kinh doanh” đứng trước, nó được chọn. Nếu doanh nghiệp muốn ưu tiên nhãn “Hết hàng”, phải đổi thứ tự hoặc thiết kế quy tắc khác.

### 5.4. Phân loại theo nhiều property

Trên node khách hàng, trạng thái `verified` và `tier` có thể được kết hợp:

~~~cypher
MATCH (c:CaseDemoCustomer)
RETURN
  c.name AS customer,
  CASE
    WHEN c.verified IS NULL THEN 'Chưa xác minh'
    WHEN c.verified = false THEN 'Cần xác minh'
    WHEN c.verified = true AND c.tier = 'GOLD' THEN 'VIP đã xác minh'
    ELSE 'Đã xác minh'
  END AS customerStatus
ORDER BY c.code;
~~~

Theo dữ liệu mẫu, An là “VIP đã xác minh”, Bình là “Cần xác minh”, Chi là “Chưa xác minh”. Với trường hợp nhiều trạng thái cần ưu tiên, hãy xác định chính sách nghiệp vụ trước khi sắp xếp các nhánh `WHEN`.

## 6. CASE và logic ba giá trị của Cypher

### 6.1. Điều kiện WHEN phải là true

Trong generic CASE, một nhánh chỉ được chọn khi điều kiện `WHEN` đánh giá ra **`true`**. Điều kiện ra `false` hoặc `null` đều không chọn nhánh đó.

~~~cypher
RETURN
  CASE
    WHEN null = null THEN 'Bằng nhau'
    WHEN null IS NULL THEN 'Thiếu giá trị'
    ELSE 'Không xác định'
  END AS result;
~~~

Kết quả là `'Thiếu giá trị'`. Điều kiện `null = null` tạo ra `null`, không phải `true`, nên Cypher tiếp tục xét `WHEN` tiếp theo.

Một ví dụ khác:

~~~cypher
RETURN
  CASE
    WHEN null > 10 THEN 'Lớn'
    WHEN null <= 10 THEN 'Nhỏ hoặc bằng'
    ELSE 'Không có số liệu'
  END AS result;
~~~

Kết quả là `'Không có số liệu'` vì cả hai phép so sánh với `null` đều không trả về `true`.

### 6.2. Null khác false, 0 và chuỗi rỗng

~~~cypher
UNWIND [
  {value: null},
  {value: false},
  {value: 0},
  {value: ''}
] AS row
RETURN
  row.value AS originalValue,
  CASE
    WHEN row.value IS NULL THEN 'Thiếu'
    WHEN row.value = false THEN 'Giá trị sai'
    WHEN row.value = 0 THEN 'Số không'
    WHEN row.value = '' THEN 'Chuỗi rỗng'
    ELSE 'Giá trị khác'
  END AS description;
~~~

Hãy dùng ví dụ này như bài luyện tập về kiểu dữ liệu: `null`, `false`, `0` và `''` đều mang thông tin khác nhau. Khi muốn phân loại dữ liệu có thể thuộc nhiều kiểu, hãy kiểm tra chính sách kiểu của dữ liệu và cân nhắc dùng các điều kiện theo kiểu. Trong ứng dụng thực tế, nên giữ **kiểu nhất quán cho một property** thay vì trộn Boolean, số và chuỗi trên cùng tên property.

### 6.3. CASE với coalesce

Hai cấu trúc này phục vụ hai mục đích:

| Cách viết | Phù hợp khi | Ví dụ |
| --- | --- | --- |
| `coalesce(x, fallback)` | Chỉ cần lấy giá trị khác null đầu tiên | `coalesce(c.tier, 'UNKNOWN')` |
| `CASE WHEN x IS NULL THEN ... ELSE ... END` | Phân biệt thiếu và có giá trị | `CASE WHEN c.tier IS NULL THEN 'Chưa phân hạng' ELSE c.tier END` |
| `CASE WHEN ... THEN ... WHEN ... THEN ... END` | Rẽ nhánh theo nhiều quy tắc | `CASE WHEN p.active = false THEN ... WHEN p.stock = 0 THEN ... END` |

Có thể kết hợp cả hai khi muốn giữ simple CASE gọn:

~~~cypher
MATCH (c:CaseDemoCustomer)
RETURN
  c.name,
  CASE coalesce(c.tier, 'UNKNOWN')
    WHEN 'GOLD' THEN 'Khách vàng'
    WHEN 'SILVER' THEN 'Khách bạc'
    WHEN 'UNKNOWN' THEN 'Chưa phân hạng'
    ELSE 'Hạng khác'
  END AS tierLabel
ORDER BY c.code;
~~~

Cách này hợp lý nếu `'UNKNOWN'` **không thể** là mã hạng hợp lệ trong dữ liệu. Nếu đó có thể là một giá trị thật, dùng generic CASE với `c.tier IS NULL` để tránh đánh đồng hai trường hợp.

### 6.4. CASE bảo vệ phép tính có mẫu số không hợp lệ

Ví dụ tính doanh thu trung bình trên mỗi sản phẩm; số sản phẩm có thể là 0 hoặc thiếu:

~~~cypher
WITH 125000.0 AS revenue, 0 AS itemCount
RETURN
  CASE
    WHEN itemCount IS NULL OR itemCount = 0 THEN null
    ELSE revenue / itemCount
  END AS averageRevenue;
~~~

Kết quả là `null`, thể hiện “không có giá trị trung bình xác định”. Nếu muốn trình bày cho người dùng, có thể thêm một cột trạng thái, chẳng hạn `'Không có sản phẩm'`.

Quy tắc xử lý này làm rõ ý nghĩa nghiệp vụ hơn việc tự thay mẫu số thiếu bằng 1, hoặc viết phép chia mà không xử lý trường hợp số lượng bằng 0.

## 7. CASE trong truy vấn quan hệ và đường đi

### 7.1. Đọc thuộc tính của relationship

Relationship trong Neo4j có thể mang các property như `quantity`, `discount`, `createdAt`. Chúng có thể tham gia biểu thức `CASE` giống property của node:

~~~cypher
MATCH (c:CaseDemoCustomer)-[r:CASE_DEMO_BUYS]->(p:CaseDemoProduct)
RETURN
  c.name AS customer,
  p.name AS product,
  r.quantity AS quantity,
  CASE
    WHEN r.quantity IS NULL THEN 'Thiếu số lượng'
    WHEN r.quantity >= 2 THEN 'Mua nhiều'
    ELSE 'Mua lẻ'
  END AS purchaseGroup
ORDER BY c.code;
~~~

Với dữ liệu mẫu, An được phân loại “Mua nhiều” và Bình là “Mua lẻ”. Các điều kiện ở đây dựa vào **property của relationship** `r`, không phải property của sản phẩm `p`.

### 7.2. OPTIONAL MATCH: phân biệt chưa có quan hệ và thiếu property

`OPTIONAL MATCH` giữ lại khách hàng không có giao dịch. Khi không có relationship phù hợp, biến `r` và node `p` được ghép thêm sẽ là `null`:

~~~cypher
MATCH (c:CaseDemoCustomer)
OPTIONAL MATCH (c)-[r:CASE_DEMO_BUYS]->(p:CaseDemoProduct)
RETURN
  c.name AS customer,
  CASE
    WHEN r IS NULL THEN 'Chưa từng mua'
    WHEN r.quantity IS NULL THEN 'Giao dịch thiếu số lượng'
    WHEN r.quantity >= 2 THEN 'Đã mua nhiều'
    ELSE 'Đã mua'
  END AS relationshipStatus,
  coalesce(p.name, 'Chưa có sản phẩm') AS productLabel
ORDER BY c.code;
~~~

Kết quả: An → “Đã mua nhiều”; Bình → “Đã mua”; Chi → “Chưa từng mua”.

**Điểm cần phân biệt:** `r IS NULL` là **không tìm thấy relationship**. Còn `r.quantity IS NULL` có thể do relationship không tồn tại *hoặc* property `quantity` trên một relationship có thật chưa được ghi. Đặt kiểm tra `r IS NULL` trước giúp nhãn diễn đạt đúng nguyên nhân.

Nếu một khách hàng có nhiều giao dịch, `OPTIONAL MATCH` sẽ tạo nhiều dòng cho khách hàng đó và `CASE` được đánh giá **riêng từng dòng**. Muốn một nhãn tổng hợp cho mỗi khách hàng, phải tổng hợp theo khách hàng trước khi phân loại.

### 7.3. Phân loại sau bước tổng hợp

~~~cypher
MATCH (c:CaseDemoCustomer)
OPTIONAL MATCH (c)-[r:CASE_DEMO_BUYS]->(:CaseDemoProduct)
WITH c, count(r) AS purchaseCount
RETURN
  c.name AS customer,
  purchaseCount,
  CASE
    WHEN purchaseCount = 0 THEN 'Chưa mua'
    WHEN purchaseCount = 1 THEN 'Mua một lần'
    ELSE 'Mua nhiều lần'
  END AS frequencyGroup
ORDER BY c.code;
~~~

Kết quả mẫu: An = 1, Bình = 1, Chi = 0. `count(r)` không đếm giá trị `null` từ phần `OPTIONAL MATCH`, vì vậy Chi có `purchaseCount = 0`.

Lưu ý: truy vấn trên đếm **relationship** `CASE_DEMO_BUYS`, không nhất thiết đếm đơn hàng trong mọi thiết kế đồ thị. Nếu mô hình gom nhiều sản phẩm trong một đơn hàng hoặc một relationship đại diện nhiều lần mua, cần chọn đơn vị đếm phù hợp.

## 8. CASE kết hợp WITH và biểu thức tính toán

### 8.1. Tạo cột trung gian để tránh lặp công thức

Giả sử cần tính giá trị thanh toán theo đơn giá, số lượng và tỉ lệ giảm giá trên relationship. `discount` có thể thiếu nên ta quy ước **không giảm giá** trong bài thực hành bằng `coalesce(r.discount, 0.0)`:

~~~cypher
MATCH (c:CaseDemoCustomer)-[r:CASE_DEMO_BUYS]->(p:CaseDemoProduct)
WITH
  c, p, r,
  p.price * r.quantity *
    (1 - coalesce(r.discount, 0.0)) AS amount
RETURN
  c.name AS customer,
  p.name AS product,
  amount,
  CASE
    WHEN amount IS NULL THEN 'Thiếu thông tin giá trị'
    WHEN amount >= 800000 THEN 'Đơn giá trị rất cao'
    WHEN amount >= 500000 THEN 'Đơn giá trị cao'
    ELSE 'Đơn thông thường'
  END AS orderType
ORDER BY c.code;
~~~

Với dữ liệu mẫu, An có `amount` xấp xỉ `576000` nên vào nhóm “Đơn giá trị cao”; Bình có `amount = 850000` nên vào nhóm “Đơn giá trị rất cao”.

`WITH` cho phép tính và đặt bí danh `amount` trước, sau đó sử dụng bí danh trong `CASE` tại `RETURN`. Phép tính với tỉ lệ `FLOAT` có thể có sai số biểu diễn nhỏ; với tiền tệ thực tế, nên có quy ước lưu trữ và làm tròn thích hợp.

### 8.2. Kiểm soát giá trị null trước khi phân loại

Giả sử một sản phẩm chưa ghi `price`:

~~~cypher
WITH {name: 'Sản phẩm mẫu', price: null} AS p
RETURN
  p.name,
  CASE
    WHEN p.price IS NULL THEN 'Chưa có giá'
    WHEN p.price >= 500000 THEN 'Giá cao'
    ELSE 'Giá thông thường'
  END AS priceLabel;
~~~

Kết quả là `'Chưa có giá'`. Nếu bỏ nhánh kiểm tra null, truy vấn sẽ đi tới `ELSE` và gán nhãn “Giá thông thường”, từ đó diễn giải sai dữ liệu thiếu thành dữ liệu giá thấp.

### 8.3. CASE và điều kiện WHERE có vai trò khác nhau

**Phân loại nhưng giữ mọi dòng:**

~~~cypher
MATCH (p:CaseDemoProduct)
RETURN
  p.name,
  CASE
    WHEN p.active = true THEN 'Đang bán'
    ELSE 'Không bán'
  END AS saleStatus;
~~~

Truy vấn trả đủ bốn sản phẩm. **Chỉ lấy sản phẩm đang bán:**

~~~cypher
MATCH (p:CaseDemoProduct)
WHERE p.active = true
RETURN p.name;
~~~

Truy vấn sau trả ba sản phẩm đang hoạt động. Hãy chọn `WHERE` khi mục tiêu là giảm số dòng, và `CASE` khi mục tiêu là tạo giá trị phân loại trong dòng kết quả.

## 9. CASE trong phép tổng hợp và báo cáo

### 9.1. Đếm có điều kiện

Biểu thức `CASE` có thể trả về 1 hoặc 0 cho mỗi dòng, sau đó `sum()` tính tổng:

~~~cypher
MATCH (p:CaseDemoProduct)
RETURN
  count(*) AS totalProducts,
  sum(CASE WHEN p.active = true THEN 1 ELSE 0 END) AS activeProducts,
  sum(CASE WHEN p.active = false THEN 1 ELSE 0 END) AS inactiveProducts,
  sum(CASE WHEN p.stock IS NULL THEN 1 ELSE 0 END) AS missingStockProducts;
~~~

Kết quả mẫu là `totalProducts = 4`, `activeProducts = 3`, `inactiveProducts = 1` và `missingStockProducts = 1`.

Nếu một trong những property có thể mang `null`, nên quyết định có tính bản ghi đó vào nhóm “khác/chưa rõ” hay không. Việc chỉ đếm `active = true` và `active = false` sẽ **không tự động bao gồm** những node thiếu `active`.

### 9.2. Gom nhóm theo biểu thức CASE

~~~cypher
MATCH (p:CaseDemoProduct)
WITH
  CASE
    WHEN p.active = false THEN 'Ngừng bán'
    WHEN p.stock IS NULL THEN 'Chưa rõ tồn kho'
    WHEN p.stock = 0 THEN 'Hết hàng'
    WHEN p.stock <= 3 THEN 'Sắp hết'
    ELSE 'Còn hàng'
  END AS stockGroup
RETURN stockGroup, count(*) AS numberOfProducts
ORDER BY stockGroup;
~~~

Kết quả có bốn nhóm, mỗi nhóm một sản phẩm:

| `stockGroup` | `numberOfProducts` |
| --- | ---: |
| Còn hàng | 1 |
| Chưa rõ tồn kho | 1 |
| Ngừng bán | 1 |
| Sắp hết | 1 |

Trong truy vấn này, các bản ghi được nhóm theo **kết quả của biểu thức CASE**, không trực tiếp theo giá trị gốc của `stock` hoặc `active`. Điều này hữu ích cho dashboard và báo cáo tổng hợp.

### 9.3. Giữ kiểu kết quả nhất quán

`CASE` có thể trả về giá trị từ các biểu thức khác nhau. Tuy nhiên, để dễ xử lý trong ứng dụng và tránh phát sinh lỗi chuyển kiểu, nên cho các nhánh trả cùng **kiểu ý nghĩa**, ví dụ đều là `STRING` cho nhãn hoặc đều là `INTEGER` cho mức ưu tiên.

Nên viết:

~~~cypher
RETURN
  CASE
    WHEN 7 >= 8 THEN 'Giỏi'
    WHEN 7 >= 5 THEN 'Đạt'
    ELSE 'Chưa đạt'
  END AS gradeLabel;
~~~

Tránh tạo một cột mà nhánh này trả `'Đạt'` còn nhánh khác trả `0` nếu hợp đồng API yêu cầu chuỗi. Khi cần cả mã và nhãn, hãy trả **hai cột riêng**, chẳng hạn `gradeCode` và `gradeLabel`.

## 10. Sắp xếp theo quy tắc nghiệp vụ với CASE

Thứ tự chữ cái của tên trạng thái không nhất thiết trùng thứ tự ưu tiên trong công việc. Bạn có thể tạo **khóa sắp xếp bằng số**:

~~~cypher
MATCH (p:CaseDemoProduct)
WITH
  p,
  CASE
    WHEN p.active = false THEN 4
    WHEN p.stock IS NULL THEN 3
    WHEN p.stock = 0 THEN 2
    WHEN p.stock <= 3 THEN 1
    ELSE 0
  END AS statusPriority
RETURN
  p.name AS product,
  p.stock AS stock,
  statusPriority
ORDER BY statusPriority ASC, product ASC;
~~~

Theo quy tắc ví dụ, sản phẩm còn nhiều hàng (mức 0) đứng trước sản phẩm sắp hết (mức 1), sau đó đến chưa cập nhật tồn kho (mức 3) và ngừng bán (mức 4).

Hai điểm cần lưu ý:

1. Mức độ ưu tiên là lựa chọn của hệ thống. Nếu cần ưu tiên sản phẩm hết hàng để bổ sung tồn kho, bạn có thể đưa nhóm này lên đầu.
2. `CASE` trong `WITH` tạo ra tên `statusPriority` để vừa trả ra màn hình vừa sắp xếp. Đây là cách rõ ràng hơn so với lặp lại một biểu thức dài ở nhiều vị trí.

## 11. Dùng CASE để cập nhật property có điều kiện

Trong Cypher, giá trị của biểu thức `CASE` có thể được gán vào một property bằng `SET`. Ví dụ sau **có thay đổi dữ liệu** trong database thực hành:

~~~cypher
MATCH (p:CaseDemoProduct)
SET p.stockLabel =
  CASE
    WHEN p.active = false THEN 'Ngừng bán'
    WHEN p.stock IS NULL THEN 'Chưa rõ tồn kho'
    WHEN p.stock = 0 THEN 'Hết hàng'
    WHEN p.stock <= 3 THEN 'Sắp hết'
    ELSE 'Còn hàng'
  END
RETURN p.sku, p.name, p.stockLabel
ORDER BY p.sku;
~~~

Các node `CaseDemoProduct` được thêm property `stockLabel`. Trước khi lưu một giá trị suy diễn vào đồ thị thật, cần cân nhắc: khi `stock` hoặc `active` thay đổi, ứng dụng có cơ chế cập nhật `stockLabel` để tránh dữ liệu bị lệch hay không?

Với trạng thái được tính trực tiếp từ property, nhiều hệ thống chọn tính trong `RETURN` để không phải đồng bộ thêm property. Nếu bài tập cần quay về trạng thái trước, có thể xóa property minh họa:

~~~cypher
MATCH (p:CaseDemoProduct)
REMOVE p.stockLabel
RETURN count(p) AS cleanedProducts;
~~~

Không nhầm `SET p.stockLabel = CASE ... END` với thao tác rẽ nhánh để thực hiện hai mệnh đề `SET` khác nhau. `CASE` tạo ra **giá trị dùng cho phép gán**.

## 12. CASE trong Java Driver và Spring Data Neo4j

### 12.1. Trả kết quả đã phân loại bằng tham số

Khi một ứng dụng Java gọi Neo4j, nên truyền dữ liệu thay đổi bằng tham số, chẳng hạn `$sku` và `$lowStockThreshold`:

~~~cypher
MATCH (p:CaseDemoProduct {sku: $sku})
RETURN
  p.sku AS sku,
  p.name AS name,
  CASE
    WHEN p.active = false THEN 'INACTIVE'
    WHEN p.stock IS NULL THEN 'UNKNOWN'
    WHEN p.stock = 0 THEN 'OUT_OF_STOCK'
    WHEN p.stock <= $lowStockThreshold THEN 'LOW_STOCK'
    ELSE 'AVAILABLE'
  END AS stockStatus;
~~~

Với `sku = 'P002'` và `lowStockThreshold = 3`, `stockStatus` là `'LOW_STOCK'`. Nhóm kết quả có mã ổn định như `LOW_STOCK` thường thuận lợi hơn cho API hoặc logic ứng dụng; giao diện có thể tự dịch mã đó sang ngôn ngữ mong muốn.

### 12.2. Ví dụ Java Driver

Đoạn mã dưới đây minh họa phần truy vấn và ánh xạ; giả sử biến `Driver driver` đã được khởi tạo bởi tầng cấu hình ứng dụng:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.Values;

// Biến driver do cấu hình ứng dụng cung cấp.
try (Session session = driver.session()) {
    var result = session.executeRead(tx ->
        tx.run(
            """
            MATCH (p:CaseDemoProduct {sku: $sku})
            RETURN
              p.name AS name,
              CASE
                WHEN p.active = false THEN 'INACTIVE'
                WHEN p.stock IS NULL THEN 'UNKNOWN'
                WHEN p.stock = 0 THEN 'OUT_OF_STOCK'
                WHEN p.stock <= $threshold THEN 'LOW_STOCK'
                ELSE 'AVAILABLE'
              END AS stockStatus
            """,
            Values.parameters("sku", "P002", "threshold", 3)
        ).single()
    );

    String name = result.get("name").asString();
    String status = result.get("stockStatus").asString();
    System.out.println(name + " -> " + status);
    // Khóa học Neo4j -> LOW_STOCK
}
~~~

Những giá trị trả về sau `CASE` trong ví dụ đều là `STRING` và luôn có nhánh `ELSE`, vì vậy có thể chuyển sang `String` sau khi truy vấn trả về đúng một bản ghi. Nếu bỏ `ELSE` hoặc có nhánh trả `null`, cần kiểm tra `Value.isNull()` trước khi gọi `asString()`.

Trong Spring Data Neo4j, truy vấn `@Query` cũng có thể dùng biểu thức `CASE` để tạo cột projection/DTO. Cần ánh xạ đúng tên alias, kiểu dữ liệu của kết quả và quy định xử lý trường hợp truy vấn không trả dòng.

### 12.3. Đặt logic phân loại ở đâu?

Có hai thiết kế thường gặp:

| Vị trí xử lý | Ưu điểm | Điều cần xem xét |
| --- | --- | --- |
| Trong Cypher bằng `CASE` | Dùng chung quy tắc khi truy vấn; giảm bước biến đổi sau khi lấy dữ liệu | Quy tắc nghiệp vụ có thể nằm trong nhiều câu truy vấn nếu không quản lý thống nhất |
| Trong Java sau khi đọc property gốc | Dễ đóng gói, tái sử dụng, kiểm thử trong mã ứng dụng | Phải chuyển đủ property gốc và xử lý `null` nhất quán |

Không có lựa chọn đúng cho mọi hệ thống. Với truy vấn báo cáo hoặc projection đã được định nghĩa rõ, `CASE` thường tiện lợi; với quy tắc nghiệp vụ phức tạp và thay đổi nhiều, cân nhắc quản lý nhất quán ở tầng ứng dụng hoặc tại lớp truy vấn dùng chung.

## 13. Hiệu năng và tính dễ bảo trì

### 13.1. Ưu tiên điều kiện lọc đơn giản khi có index

Neo4j có thể tối ưu truy cập node theo index khi điều kiện `WHERE` phù hợp với thuộc tính và loại index. Ví dụ:

~~~cypher
EXPLAIN
MATCH (p:CaseDemoProduct)
WHERE p.sku = $sku
RETURN
  p.name,
  CASE
    WHEN p.stock <= 3 THEN 'Sắp hết'
    ELSE 'Khác'
  END AS stockStatus;
~~~

Ở đây, `WHERE p.sku = $sku` thể hiện trực tiếp điều kiện lọc; `CASE` chỉ phân loại những dòng được tìm thấy. Khi chuyển toàn bộ logic lọc vào biểu thức phức tạp hoặc bọc property cần tìm trong nhiều hàm, khả năng tận dụng index có thể thay đổi. Nếu hiệu năng quan trọng, dùng `EXPLAIN` hoặc `PROFILE` với dữ liệu và tham số đại diện để kiểm tra kế hoạch.

### 13.2. Tránh lặp lại CASE dài

Nếu nhiều cột hoặc bước xử lý cần chung một phân loại, hãy tính một lần trong `WITH`:

~~~cypher
MATCH (p:CaseDemoProduct)
WITH
  p,
  CASE
    WHEN p.active = false THEN 'INACTIVE'
    WHEN p.stock IS NULL THEN 'UNKNOWN'
    WHEN p.stock <= 3 THEN 'LOW'
    ELSE 'OK'
  END AS stockCode
RETURN
  p.sku AS sku,
  p.name AS product,
  stockCode,
  CASE stockCode
    WHEN 'INACTIVE' THEN 'Ngừng bán'
    WHEN 'UNKNOWN' THEN 'Chưa có dữ liệu kho'
    WHEN 'LOW' THEN 'Cần bổ sung hàng'
    ELSE 'Đang bán'
  END AS stockLabel
ORDER BY stockCode, sku;
~~~

Truy vấn này minh họa việc kết hợp generic CASE để tính mã và simple CASE để ánh xạ mã sang nhãn. Với dữ liệu `P003.stock = 0` nhưng `active = false`, mã là `INACTIVE` vì nhánh đó được ưu tiên.

Trong một ứng dụng lớn, nên đặt tên cột theo đúng ý nghĩa và thống nhất quy tắc phân loại. Nếu “hết hàng” cần khác với “sắp hết” thì cần bổ sung nhánh `stock = 0` trước `stock <= 3`.

### 13.3. Ranh giới của CASE

`CASE` biểu diễn **lựa chọn giá trị**, nhưng không tự:

- Đổi kiểu quan hệ trong `MATCH` bằng cách viết hai mẫu Cypher khác nhau trong `THEN`.
- Tự chạy hai chuỗi mệnh đề `CREATE`/`DELETE` khác nhau.
- Bảo đảm rằng dữ liệu gốc thỏa các ràng buộc nghiệp vụ.
- Tạo index hoặc constraint; đó là nhiệm vụ của lệnh quản lý schema.

Nếu bài toán yêu cầu nhiều nhánh cập nhật phức tạp, hãy thiết kế các bước cập nhật phù hợp hoặc xử lý luồng quyết định ở tầng ứng dụng thay vì cố nhét mọi thao tác vào một biểu thức `CASE`.

## 14. Lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| Dùng `CASE x WHEN null THEN ...` để kiểm tra giá trị thiếu | `null = null` không tạo `true` | Dùng generic `CASE WHEN x IS NULL THEN ...` |
| Bỏ `ELSE` và mong nhận chuỗi rỗng | Không có nhánh khớp thì trả `null` | Viết `ELSE ''` nếu nghiệp vụ thật sự muốn chuỗi rỗng |
| Đặt `WHEN score >= 5` trước `WHEN score >= 8` | Nhánh ngưỡng thấp luôn khớp trước với điểm cao | Xếp điều kiện từ cụ thể/nghiêm ngặt đến tổng quát |
| Gắn nhãn “Giá thấp” cho `price = null` | So sánh với null không đúng; `ELSE` được chọn | Kiểm tra `price IS NULL` trước |
| Kiểm tra `r.quantity IS NULL` để khẳng định không có quan hệ | Quan hệ có thể tồn tại nhưng thiếu property | Kiểm tra `r IS NULL` khi cần xác định không có quan hệ |
| Tưởng `CASE` làm giảm số dòng như `WHERE` | `CASE` chỉ tạo một giá trị trên mỗi dòng | Dùng `WHERE` nếu cần lọc |
| Trộn kiểu `STRING` và `INTEGER` ở các nhánh của cùng cột | Kết quả khó ánh xạ vào DTO/API có kiểu cố định | Chuẩn hóa kiểu hoặc trả hai cột |
| Dùng `coalesce(x, 0)` trước `CASE` khi 0 khác “không biết” | Đánh đồng giá trị thiếu với số 0 | Giữ nhánh `WHEN x IS NULL` riêng |
| Lưu nhãn suy diễn bằng `SET` mà không cập nhật khi dữ liệu gốc đổi | Nhãn có thể cũ so với `stock`, `active` | Cân nhắc tính tại thời điểm truy vấn hoặc đồng bộ rõ ràng |
| Dùng mã trạng thái hiển thị thay cho mã nghiệp vụ ở API | Khó quốc tế hóa hoặc thay đổi nội dung nhãn | Trả mã ổn định, dịch thành nhãn ở tầng hiển thị khi phù hợp |

## 15. Bài tập tự luyện có lời giải

### Bài 1. Dự đoán thứ tự chọn nhánh

~~~cypher
RETURN
  CASE
    WHEN 10 >= 5 THEN 'Đạt'
    WHEN 10 >= 8 THEN 'Giỏi'
    ELSE 'Chưa đạt'
  END AS result;
~~~

**Đáp án:** `'Đạt'` vì điều kiện đầu tiên đã đúng. Muốn kết quả `'Giỏi'`, hãy đặt điều kiện `10 >= 8` trước `10 >= 5`.

### Bài 2. So sánh simple CASE và generic CASE

Yêu cầu: gán nhãn khách hàng theo `tier`, nhưng khi thiếu `tier` phải trả `'Thiếu hạng'`, còn mã không được hỗ trợ trả `'Hạng khác'`.

~~~cypher
MATCH (c:CaseDemoCustomer)
RETURN
  c.name AS customer,
  CASE
    WHEN c.tier IS NULL THEN 'Thiếu hạng'
    WHEN c.tier = 'GOLD' THEN 'Khách vàng'
    WHEN c.tier = 'SILVER' THEN 'Khách bạc'
    ELSE 'Hạng khác'
  END AS tierLabel
ORDER BY c.code;
~~~

**Đáp án:** An → Khách vàng; Bình → Khách bạc; Chi → Thiếu hạng. Generic CASE phù hợp vì có nhánh `IS NULL` cần tách khỏi mã hạng khác.

### Bài 3. Phân loại tồn kho

Yêu cầu: ưu tiên “Ngừng bán” nếu `active = false`; tiếp theo “Chưa có số liệu” khi `stock IS NULL`; “Hết hàng” khi `stock = 0`; “Sắp hết” nếu `stock` từ 1 đến 5; còn lại “Còn hàng”.

~~~cypher
MATCH (p:CaseDemoProduct)
RETURN
  p.sku, p.name,
  CASE
    WHEN p.active = false THEN 'Ngừng bán'
    WHEN p.stock IS NULL THEN 'Chưa có số liệu'
    WHEN p.stock = 0 THEN 'Hết hàng'
    WHEN p.stock >= 1 AND p.stock <= 5 THEN 'Sắp hết'
    ELSE 'Còn hàng'
  END AS stockLabel
ORDER BY p.sku;
~~~

**Đáp án:** `P001` → Còn hàng, `P002` → Sắp hết, `P003` → Ngừng bán, `P004` → Chưa có số liệu.

### Bài 4. Đếm sản phẩm theo ngưỡng giá

Yêu cầu: đếm sản phẩm có `price >= 500000` và sản phẩm còn lại bằng một truy vấn duy nhất.

~~~cypher
MATCH (p:CaseDemoProduct)
RETURN
  sum(CASE WHEN p.price >= 500000 THEN 1 ELSE 0 END) AS highPrice,
  sum(CASE WHEN p.price < 500000 THEN 1 ELSE 0 END) AS lowerPrice,
  sum(CASE WHEN p.price IS NULL THEN 1 ELSE 0 END) AS missingPrice;
~~~

**Đáp án:** `highPrice = 1`, `lowerPrice = 3`, `missingPrice = 0`. Việc đếm thêm nhóm thiếu giá giúp bảng báo cáo không bỏ sót dữ liệu thiếu trong tương lai.

### Bài 5. Phân loại giao dịch sau OPTIONAL MATCH

Yêu cầu: giữ tất cả khách hàng, trả nhãn “Chưa mua” cho người không có quan hệ, nhãn “Thiếu số lượng” cho quan hệ không có `quantity`, còn lại là “Có mua”.

~~~cypher
MATCH (c:CaseDemoCustomer)
OPTIONAL MATCH (c)-[r:CASE_DEMO_BUYS]->(:CaseDemoProduct)
RETURN
  c.name,
  CASE
    WHEN r IS NULL THEN 'Chưa mua'
    WHEN r.quantity IS NULL THEN 'Thiếu số lượng'
    ELSE 'Có mua'
  END AS purchaseLabel
ORDER BY c.code;
~~~

**Đáp án:** An và Bình → Có mua; Chi → Chưa mua. Điều kiện `r IS NULL` đứng trước `r.quantity IS NULL` để tách rõ hai nguyên nhân.

### Bài 6. Chọn điều kiện lọc hay biểu thức phân loại?

Yêu cầu: API chỉ được trả về **sản phẩm đang bán**, đồng thời mỗi dòng có cột `stockStatus`.

~~~cypher
MATCH (p:CaseDemoProduct)
WHERE p.active = true
RETURN
  p.sku, p.name,
  CASE
    WHEN p.stock IS NULL THEN 'UNKNOWN'
    WHEN p.stock = 0 THEN 'OUT'
    WHEN p.stock <= 3 THEN 'LOW'
    ELSE 'OK'
  END AS stockStatus
ORDER BY p.sku;
~~~

**Đáp án:** Chỉ còn `P001`, `P002` và `P004`; lần lượt có mã `OK`, `LOW`, `UNKNOWN`. `WHERE` thực hiện lọc, `CASE` thực hiện phân loại trên các dòng còn lại.

## 16. Tổng kết và ghi nhớ

- `CASE ... END` là **biểu thức chọn một giá trị** trong Cypher. Nó rất hữu ích khi chuyển property của node và relationship thành nhãn, mã trạng thái, mức ưu tiên hoặc nhóm báo cáo.
- **Simple CASE** phù hợp khi ánh xạ một property sang các giá trị cố định; **generic CASE** phù hợp khi kiểm tra khoảng giá trị, nhiều property, điều kiện Boolean hoặc `IS NULL`.
- Nhánh được chọn là **nhánh phù hợp đầu tiên**. Vì vậy, thứ tự `WHEN` phải phản ánh mức ưu tiên nghiệp vụ; thiếu `ELSE` thì kết quả có thể là `null`.
- `null` không tương đương với `false` hay `0`; để phát hiện giá trị thiếu, dùng `IS NULL`. Với `OPTIONAL MATCH`, cần phân biệt relationship không tồn tại và relationship có property bị thiếu.
- `CASE` dùng tốt trong `RETURN`, `WITH`, `ORDER BY`, phép tổng hợp và biểu thức gán trong `SET`. Khi cần **lọc dòng**, dùng `WHERE`.
- Nên chuẩn hóa kiểu của các nhánh và cân nhắc trả **mã trạng thái ổn định** khi dữ liệu được sử dụng trong Java Driver, Spring Data Neo4j hoặc API.

Biểu thức `CASE` giúp những truy vấn property graph không chỉ tìm quan hệ và đường đi, mà còn chuyển dữ liệu liên kết thành kết quả có ý nghĩa đối với nghiệp vụ một cách rõ ràng, nhất quán và dễ kiểm tra.

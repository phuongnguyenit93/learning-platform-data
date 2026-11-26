# Range index và điều kiện lọc hoặc sắp xếp phù hợp

Trong Neo4j, **property graph** lưu dữ liệu bằng node, relationship và thuộc tính. Cypher có thể tìm các node theo nhãn, mở rộng quan hệ và lọc theo thuộc tính. Khi số lượng node lớn, việc duyệt mọi node mang nhãn rồi kiểm tra từng thuộc tính có thể tốn nhiều chi phí. **Range index** là chỉ mục thuộc tính giúp bộ lập kế hoạch truy vấn tìm nhanh các giá trị phù hợp và, trong một số kế hoạch, đọc kết quả theo thứ tự sẵn có của chỉ mục.

Bài học thuộc chương **Chỉ mục tra cứu** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Trọng tâm là chọn **điều kiện `WHERE`** và **`ORDER BY`** phù hợp với range index, đọc kế hoạch `EXPLAIN`/`PROFILE` và tránh hiểu nhầm rằng cứ tạo index là truy vấn chắc chắn sử dụng. Các ví dụ áp dụng cho Neo4j 5 với cú pháp `CREATE RANGE INDEX`; ở phiên bản khác, hãy đối chiếu cú pháp và tính năng được hỗ trợ.

## 1. Mục tiêu

Sau khi học, bạn có thể:

1. Phân biệt **range index** với **token lookup index**, **text index** và **point index** theo nhu cầu truy vấn.
2. Viết truy vấn Cypher có điều kiện bằng, phạm vi, tiền tố chuỗi và kiểm tra tồn tại thuộc tính có khả năng hưởng lợi từ range index.
3. Giải thích khi nào `ORDER BY` có thể tận dụng thứ tự chỉ mục và khi nào vẫn cần phép sắp xếp bổ sung.
4. Thiết kế range index đơn thuộc tính hoặc nhiều thuộc tính cho truy vấn thường gặp.
5. Dùng `SHOW INDEXES`, `EXPLAIN` và `PROFILE` để kiểm chứng cách Neo4j thực sự thực thi truy vấn.

## 2. Range index phục vụ thao tác nào?

Range index tổ chức các **giá trị thuộc tính** của một nhãn node hoặc một loại relationship, cho phép tra cứu theo giá trị hoặc khoảng giá trị. Ví dụ, các node `:Product` có `price` là số có thể được tìm bằng điều kiện `p.price >= 100000 AND p.price < 500000`.

Trong Neo4j 5, ta có thể tạo:

~~~cypher
CREATE RANGE INDEX product_price_idx IF NOT EXISTS
FOR (p:Product) ON (p.price);
~~~

Câu lệnh trên tạo chỉ mục cho thuộc tính `price` của các node có nhãn `Product`. Nó **không** tạo thuộc tính bị thiếu và **không** biến giá trị chuỗi thành số. Hãy phân biệt các loại index liên quan:

| Loại chỉ mục | Đối tượng và tình huống phù hợp | Ví dụ |
|---|---|---|
| **Token lookup index** | Tìm node theo **label** hoặc relationship theo **type**, không tra cứu giá trị thuộc tính | `MATCH (p:Product)` |
| **Range index** | Lọc thuộc tính bằng giá trị, khoảng giá trị, tiền tố; có thể hỗ trợ thứ tự | `WHERE p.price >= 100000` |
| **Text index** | Tối ưu tìm kiếm văn bản với `CONTAINS`, `ENDS WITH` và các mẫu chuỗi được hỗ trợ | `WHERE p.name CONTAINS 'sách'` |
| **Point index** | Truy vấn không gian với tọa độ/điểm, phạm vi địa lý hoặc khoảng cách | `point.distance(...)` |
| **Full-text index** | Tìm kiếm văn bản theo từ, phân tích ngôn ngữ và độ liên quan | Tra cứu qua thủ tục full-text |

Không nên coi các loại chỉ mục trên là tương đương: token lookup index không thể thay range index cho lọc `price`; range index cũng không phải công cụ chuyên dụng cho tìm kiếm từ khóa phức tạp hay bán kính địa lý.

### Những dạng điều kiện thường phù hợp

| Dạng điều kiện trên thuộc tính đã lập range index | Ví dụ Cypher | Ý nghĩa |
|---|---|---|
| Bằng một giá trị | `p.price = 120000` | Tìm đúng giá trị |
| Nhiều giá trị | `p.category IN ['Books', 'Home']` | Tìm theo tập giá trị |
| So sánh phạm vi | `p.price >= 100000 AND p.price < 500000` | Khoảng có cận |
| So sánh thời gian | `p.createdAt >= date('2026-01-01')` | Các bản ghi từ một ngày |
| Tiền tố chuỗi | `p.name STARTS WITH 'Ca'` | Tìm chuỗi bắt đầu bằng tiền tố |
| Thuộc tính tồn tại | `p.price IS NOT NULL` | Quét các entry có giá trị được lập chỉ mục |

Đây là **các dạng có thể sử dụng** index, không phải lời hứa rằng Neo4j luôn chọn index. Bộ tối ưu tính toán chi phí dựa vào dữ liệu, thống kê, số hàng ước lượng, các điều kiện khác và thứ tự kết quả cần trả.

## 3. Chuẩn bị dữ liệu minh họa

Trên **database thực hành**, tạo một tập sản phẩm nhỏ. Các giá trị `price` là **số nguyên biểu diễn VND**, `createdAt` dùng kiểu `DATE`, không phải chuỗi ngày:

~~~cypher
UNWIND [
  {sku: 'B001', name: 'Cẩm nang Cypher', category: 'Books',
   price: 120000, createdAt: date('2026-01-10')},
  {sku: 'B002', name: 'Cấu trúc dữ liệu', category: 'Books',
   price: 150000, createdAt: date('2026-03-05')},
  {sku: 'B003', name: 'Nhập môn đồ thị', category: 'Books',
   price: 90000, createdAt: date('2026-02-20')},
  {sku: 'E001', name: 'Chuột máy tính', category: 'Electronics',
   price: 350000, createdAt: date('2026-04-12')},
  {sku: 'E002', name: 'Bàn phím', category: 'Electronics',
   price: 950000, createdAt: date('2026-05-10')},
  {sku: 'H001', name: 'Đèn đọc sách', category: 'Home',
   price: 150000, createdAt: date('2026-06-01')}
] AS row
MERGE (p:Product {sku: row.sku})
SET p.name = row.name,
    p.category = row.category,
    p.price = row.price,
    p.createdAt = row.createdAt;
~~~

Với cơ sở dữ liệu khác, `MERGE` dựa trên `sku` có thể khớp các sản phẩm sẵn có. Ví dụ nên được chạy trên database tách biệt; nếu cần tính duy nhất tuyệt đối của `sku`, hãy thiết kế **uniqueness constraint** phù hợp cho dữ liệu thực tế.

Tạo các chỉ mục phục vụ những truy vấn trong bài:

~~~cypher
CREATE RANGE INDEX product_price_idx IF NOT EXISTS
FOR (p:Product) ON (p.price);

CREATE RANGE INDEX product_name_idx IF NOT EXISTS
FOR (p:Product) ON (p.name);

CREATE RANGE INDEX product_created_at_idx IF NOT EXISTS
FOR (p:Product) ON (p.createdAt);
~~~

`IF NOT EXISTS` giúp không báo lỗi khi đã có một index hoặc constraint tương đương theo ngữ nghĩa được Neo4j nhận diện; tuy nhiên, hãy kiểm tra index thực tế thay vì suy đoán trạng thái chỉ từ kết quả lệnh tạo.

Kiểm tra metadata và đợi các index vừa tạo có trạng thái `ONLINE` trước khi dùng để đo hiệu năng:

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes, properties, state
WHERE type = 'RANGE'
RETURN name, entityType, labelsOrTypes, properties, state
ORDER BY name;
~~~

Index mới có thể ở trạng thái `POPULATING` trong khi Neo4j xây dựng dữ liệu. Nếu thất bại có thể thấy `FAILED`; khi đó cần kiểm tra thông tin lỗi và cấu hình vận hành trước khi kỳ vọng truy vấn tận dụng index.

## 4. Viết điều kiện lọc có khả năng tận dụng range index

### 4.1. Bằng và khoảng giá trị số

~~~cypher
// Lọc các sản phẩm từ 100.000 đến dưới 500.000 VND.
MATCH (p:Product)
WHERE p.price >= 100000 AND p.price < 500000
RETURN p.sku AS sku, p.name AS product, p.price AS price
ORDER BY p.price ASC;
~~~

Với dữ liệu minh họa, các sản phẩm thỏa điều kiện là `B001` (120.000), `B002` (150.000), `H001` (150.000) và `E001` (350.000). Hai sản phẩm cùng giá 150.000 có thể đổi chỗ cho nhau khi chỉ sắp theo `price`.

Điều kiện trên nêu trực tiếp `p.price` với toán tử so sánh và các hằng số có cùng kiểu số, thuận lợi cho bộ lập kế hoạch dựng phép tìm kiếm theo phạm vi. Nếu muốn sử dụng giá trị đầu vào từ ứng dụng, hãy dùng **tham số Cypher**:

~~~cypher
MATCH (p:Product)
WHERE p.price >= $minPrice AND p.price < $maxPrice
RETURN p.sku AS sku, p.name AS product, p.price AS price
ORDER BY p.price ASC
LIMIT 20;
~~~

Ví dụ, ứng dụng Java Driver hoặc Spring Data Neo4j có thể truyền `minPrice = 100000` và `maxPrice = 500000` ở dạng số. Truyền tham số giúp tái sử dụng câu truy vấn và tránh nối giá trị đầu vào trực tiếp vào chuỗi Cypher. Khả năng sử dụng index vẫn phụ thuộc điều kiện thực tế và kế hoạch đã chọn.

### 4.2. Lọc khoảng thời gian

~~~cypher
MATCH (p:Product)
WHERE p.createdAt >= date('2026-03-01')
  AND p.createdAt < date('2026-06-01')
RETURN p.sku AS sku, p.createdAt AS createdAt
ORDER BY p.createdAt;
~~~

Điều kiện dùng giá trị `DATE` đúng kiểu của `p.createdAt`. Với dữ liệu mẫu, các mã thỏa điều kiện là `B002`, `E001` và `E002`; `H001` có ngày 01/06 nên **không** nằm trong cận trên mở. Cách viết khoảng `[đầu, cuối)` rất hữu ích khi lọc ngày, giờ và phân trang theo thời gian.

### 4.3. Lọc tiền tố chuỗi

~~~cypher
MATCH (p:Product)
WHERE p.name STARTS WITH 'C'
RETURN p.sku AS sku, p.name AS product
ORDER BY p.name;
~~~

Nếu có range index trên `p.name`, phép tìm kiếm bằng **tiền tố** là một tình huống thích hợp để đánh giá việc dùng index. `STARTS WITH` phân biệt chữ hoa và chữ thường theo ngữ nghĩa so khớp của Cypher; `'C'` và `'c'` không được mặc nhiên coi là một tiền tố.

Ngược lại, `CONTAINS`, `ENDS WITH` hoặc tìm kiếm theo ngôn ngữ tự nhiên có đặc điểm khác. Nên đánh giá **text index** hay **full-text index** dựa trên dạng tìm kiếm; không giả định range index trên `name` là lựa chọn tốt nhất cho mọi truy vấn chuỗi.

### 4.4. Tồn tại thuộc tính

~~~cypher
MATCH (p:Product)
WHERE p.price IS NOT NULL
RETURN p.sku AS sku, p.price AS price
ORDER BY p.price ASC
LIMIT 10;
~~~

`IS NOT NULL` là cách diễn đạt rằng chỉ lấy sản phẩm thực sự có `price`. Vì range index lưu các giá trị thuộc tính hiện hữu, Neo4j có thể dùng **index scan có thứ tự** khi phù hợp. Ngược lại, `WHERE p.price IS NULL` tìm các node **thiếu hoặc có giá trị null**, nên không thể tìm trực tiếp những node đó chỉ qua entry của index `price`.

## 5. Range index và `ORDER BY`: khi nào có thể tránh `Sort`?

Range index có trật tự theo giá trị được lập chỉ mục. Khi yêu cầu sắp xếp **tương thích với thứ tự có thể đọc từ index**, Neo4j đôi khi trả các hàng đã được sắp xếp từ thao tác index và tránh bước `Sort` riêng.

~~~cypher
EXPLAIN
MATCH (p:Product)
WHERE p.price >= 100000
RETURN p.sku AS sku, p.price AS price
ORDER BY p.price ASC
LIMIT 20;
~~~

Nếu kế hoạch dùng range index và truyền được thứ tự `p.price ASC` qua các toán tử tiếp theo, bước sắp xếp có thể được loại bỏ. Bộ lập kế hoạch cũng có thể chọn cách khác do chi phí ước tính; chỉ **đọc kế hoạch thực tế** mới kết luận được.

Các tình huống thường cần cân nhắc:

| Truy vấn | Khả năng tận dụng thứ tự index |
|---|---|
| `WHERE p.price >= 100000 ORDER BY p.price` | Có thể rất phù hợp với range index trên `price` |
| `WHERE p.price IS NOT NULL ORDER BY p.price DESC` | Có thể đọc index theo chiều phù hợp |
| `ORDER BY p.price` nhưng **không lọc node thiếu giá** | Không thể chỉ lấy entry index nếu còn phải trả cả các node không có `price` |
| `ORDER BY toString(p.price)` | Thứ tự biểu thức chuỗi khác thứ tự số, không mặc nhiên dùng thứ tự của index số |
| `ORDER BY p.price, p.sku` với index chỉ có `price` | Index chỉ bảo đảm trật tự theo `price`; có thể vẫn cần sắp thêm theo `sku` |
| `ORDER BY p.category, p.price` với index chỉ có `price` | Không trùng thứ tự khóa index; có thể cần `Sort` |

**Vấn đề giá trị bằng nhau:** khi hai node cùng `price`, `ORDER BY p.price` không xác định thứ tự giữa chúng. Để phân trang ổn định, có thể sắp xếp thêm định danh duy nhất:

~~~cypher
MATCH (p:Product)
WHERE p.price IS NOT NULL
RETURN p.sku AS sku, p.price AS price
ORDER BY price ASC, sku ASC
LIMIT 20;
~~~

Truy vấn này cho thứ tự kết quả rõ hơn **nếu `sku` là duy nhất**. Nó cũng có thể cần bước sắp xếp bổ sung. Không nên đánh đổi tính đúng đắn của phân trang lấy giả định rằng `LIMIT` cùng một chỉ mục sẽ luôn sinh thứ tự ổn định giữa các giá trị trùng.

## 6. Range index nhiều thuộc tính (composite range index)

Giả sử truy vấn nghiệp vụ thường lọc **danh mục chính xác**, tiếp tục lọc theo **khoảng giá**, rồi sắp xếp theo giá:

~~~cypher
MATCH (p:Product)
WHERE p.category = 'Books'
  AND p.price >= 100000
RETURN p.sku AS sku, p.price AS price
ORDER BY p.price ASC
LIMIT 20;
~~~

Một composite range index có thể phù hợp hơn hai index đơn thuộc tính:

~~~cypher
CREATE RANGE INDEX product_category_price_idx IF NOT EXISTS
FOR (p:Product) ON (p.category, p.price);
~~~

**Thứ tự thuộc tính trong index có ý nghĩa.** Với khóa `(category, price)`, các entry được tổ chức theo `category` trước rồi theo `price` trong từng nhóm. Điều kiện `p.category = 'Books'` thu hẹp về một nhóm danh mục, sau đó điều kiện khoảng giá có thể khai thác thứ tự `price` trong nhóm đó. Điều này cũng tạo cơ hội tránh `Sort` khi `ORDER BY p.price`.

### Chọn thứ tự thuộc tính theo mẫu truy vấn

| Mẫu truy vấn | Mức phù hợp của `(category, price)` |
|---|---|
| `category = 'Books' AND price >= 100000` | Rất đáng cân nhắc: bằng khóa đầu, khoảng ở khóa sau |
| `category = 'Books' ORDER BY price` | Có thể tận dụng thứ tự giá trong cùng category |
| `price >= 100000`, không có điều kiện category | Không nên kỳ vọng tìm kiếm theo price hiệu quả như index đơn `(price)` |
| `category STARTS WITH 'B' AND price >= 100000` | Khóa đầu đã là phạm vi; khả năng tận dụng khóa sau hạn chế hơn so với bằng chính xác |
| `category = 'Books' AND price = 150000` | Hai điều kiện bằng là mẫu phù hợp |

Quy tắc thực hành: khi thiết kế composite index, ưu tiên các thuộc tính thường được lọc **bằng chính xác** ở đầu, sau đó mới đến thuộc tính lọc **phạm vi** hoặc dùng trong sắp xếp. Neo4j có những tối ưu riêng theo phiên bản và thống kê, vì vậy quy tắc này chỉ là điểm khởi đầu cần kiểm chứng bằng `PROFILE`.

Không nên tạo mọi hoán vị thuộc tính chỉ để “phủ hết truy vấn”. Mỗi index có chi phí lưu trữ, xây dựng và cập nhật khi node thay đổi.

## 7. Range index cho thuộc tính relationship

Range index không chỉ áp dụng cho node. Khi nghiệp vụ lưu thời điểm mua hàng trên relationship `:PURCHASED`, có thể lập chỉ mục cho thuộc tính của relationship đó:

~~~cypher
CREATE RANGE INDEX purchased_at_idx IF NOT EXISTS
FOR ()-[r:PURCHASED]-() ON (r.purchasedAt);
~~~

Truy vấn tương ứng:

~~~cypher
MATCH ()-[r:PURCHASED]->()
WHERE r.purchasedAt >= datetime('2026-01-01T00:00:00Z')
  AND r.purchasedAt < datetime('2027-01-01T00:00:00Z')
RETURN r.purchasedAt AS purchasedAt
ORDER BY purchasedAt DESC
LIMIT 30;
~~~

Điều kiện này phù hợp **nếu `purchasedAt` thực sự được lưu kiểu `DATETIME`**. Nếu quan hệ dùng `DATE`, cần dùng `date(...)` cho đúng kiểu. Khi truy vấn còn ràng buộc node đầu/cuối, bộ tối ưu có thể thấy mở rộng từ một node được chọn sẵn rẻ hơn quét index của relationship; hãy đo theo truy vấn thật.

## 8. Những cách viết làm giảm khả năng dùng index

### 8.1. Dùng sai kiểu thuộc tính

Nếu `p.price` được lưu bằng chuỗi như `'90000'` và `'120000'`, việc so sánh/sắp xếp có thể tuân theo thứ tự **chuỗi**, khác thứ tự số. Chẳng hạn thứ tự từ điển đặt `'120000'` trước `'90000'`. Đừng chỉ tạo range index để chữa dữ liệu sai kiểu: hãy chuẩn hóa giá thành **INTEGER** hoặc kiểu số phù hợp ngay trong mô hình dữ liệu.

Với ngày giờ cũng vậy, giá trị `date('2026-03-05')` khác chuỗi `'2026-03-05'`. Dùng kiểu temporal của Neo4j giúp truy vấn so sánh ngày giờ đúng nghĩa.

### 8.2. Bọc thuộc tính trong phép biến đổi ở `WHERE`

~~~cypher
// Có thể khó dùng trực tiếp range index trên p.price:
MATCH (p:Product)
WHERE toInteger(p.price) >= 100000
RETURN p.sku, p.price;
~~~

Chỉ mục lưu `p.price`, không lưu mặc định kết quả biểu thức `toInteger(p.price)`. Nếu `price` đã là số, điều kiện nên viết:

~~~cypher
MATCH (p:Product)
WHERE p.price >= 100000
RETURN p.sku, p.price;
~~~

Tương tự, `toLower(p.name) STARTS WITH 'c'` và `coalesce(p.price, 0) >= 100000` đặt phép biến đổi lên thuộc tính được lập chỉ mục. Tùy kế hoạch và phiên bản, bộ tối ưu không nhất thiết chuyển chúng thành một lần tìm kiếm index trực tiếp. Hãy chuẩn hóa dữ liệu hoặc thiết kế thuộc tính dành riêng cho truy vấn có nhu cầu xử lý chữ hoa/thường.

### 8.3. Chỉ mục không khớp label, relationship type hoặc thuộc tính

~~~cypher
CREATE RANGE INDEX product_price_idx IF NOT EXISTS
FOR (p:Product) ON (p.price);
~~~

Index này gắn với `:Product(price)`. Nó không phục vụ trực tiếp các mẫu `(o:Order) WHERE o.price > 0` hoặc `(p:Product) WHERE p.cost > 0` vì label/thuộc tính khác. Index tương ứng phải được xác định từ **mẫu truy vấn thật**, không chỉ theo tên cột có ý nghĩa gần giống.

### 8.4. Bộ lọc có chọn lọc thấp

Điều kiện như `p.price > 0` có thể trả hầu hết sản phẩm. Nếu Neo4j dự đoán số lượng hàng quá lớn, sử dụng index không nhất thiết rẻ hơn cách duyệt khác. Tương tự, index trên một thuộc tính chỉ có vài giá trị lặp lại nhiều lần có thể ít ích lợi với những truy vấn không thu hẹp tập kết quả.

### 8.5. `OR` và nhiều đường lọc

~~~cypher
MATCH (p:Product)
WHERE p.price >= 500000 OR p.category = 'Books'
RETURN p.sku AS sku, p.price AS price;
~~~

Hai vế `OR` dựa trên **hai thuộc tính khác nhau**. Bộ tối ưu có thể cần kết hợp nhiều cách truy cập hoặc lọc bổ sung, phụ thuộc phiên bản và chi phí; không thể kết luận chỉ từ việc đã có index `price`. Khi truy vấn này quan trọng, hãy xem `EXPLAIN`/`PROFILE` trước khi cân nhắc viết lại thành các nhánh riêng và loại trùng theo định danh.

## 9. Xác nhận bằng `EXPLAIN` và `PROFILE`

Không nên đoán index có được dùng chỉ bằng thời gian chạy trên vài node thử nghiệm. Cách kiểm tra:

1. Chạy `SHOW INDEXES` để chắc chắn index **đúng label/type, thuộc tính** và ở trạng thái `ONLINE`.
2. Dùng `EXPLAIN` để xem **kế hoạch dự kiến** mà không thực thi truy vấn.
3. Dùng `PROFILE` cho **truy vấn đọc** trên dữ liệu thử/đại diện để xem lượng hàng (`Rows`), lượt truy cập dữ liệu (`DB Hits`), ước lượng và chi phí thực thi.
4. Kiểm tra có toán tử truy cập index thích hợp hay không; quan sát có `Sort` khi cần sắp xếp và liệu nhiều hàng trung gian có bị tạo không cần thiết.
5. So sánh trên dữ liệu đủ lớn, cùng tham số, cùng trạng thái index; tránh khẳng định một tối ưu hiệu quả chỉ vì truy vấn mẫu 6 hàng chạy nhanh.

Ví dụ:

~~~cypher
EXPLAIN
MATCH (p:Product)
WHERE p.category = 'Books' AND p.price >= 100000
RETURN p.sku AS sku, p.price AS price
ORDER BY price ASC
LIMIT 10;
~~~

~~~cypher
PROFILE
MATCH (p:Product)
WHERE p.category = 'Books' AND p.price >= 100000
RETURN p.sku AS sku, p.price AS price
ORDER BY price ASC
LIMIT 10;
~~~

Tùy phiên bản Neo4j, kế hoạch có thể thể hiện các toán tử như `NodeIndexSeek`, `NodeIndexScan`, `Filter`, `Sort`, `Top`, `Projection` hoặc toán tử khác. **Tên toán tử và hình dạng kế hoạch có thể thay đổi**, do đó hãy đọc cả thông tin về index đã chọn, thuộc tính đang lọc và số hàng thực tế, thay vì tìm đúng một chuỗi tên toán tử.

Truy vấn có `LIMIT` cũng chưa chắc tận dụng được việc đọc index theo thứ tự: nếu kế hoạch phải tính một biểu thức hoặc sắp theo khóa không nằm trong thứ tự index, Neo4j có thể cần thêm bước `Top`/`Sort` trước khi trả N hàng.

### Có nên ép dùng index bằng `USING INDEX`?

Neo4j hỗ trợ **index hint** trong Cypher, ví dụ:

~~~cypher
MATCH (p:Product)
USING INDEX p:Product(price)
WHERE p.price >= $minPrice
RETURN p.sku AS sku, p.price AS price;
~~~

Hint là công cụ điều tra/điều chỉnh khi đã có bằng chứng rằng lựa chọn tự động không phù hợp, **không phải bước bắt buộc** sau khi tạo index. Nó có thể hạn chế lựa chọn tốt hơn của bộ tối ưu khi phân bố dữ liệu hoặc truy vấn thay đổi. Với các bài toán vận hành, hãy đo cả phiên bản có và không có hint trước khi quyết định sử dụng.

## 10. Thiết kế và vận hành range index hợp lý

Index là cấu trúc bổ sung cần được duy trì. Tạo thêm index có thể cải thiện truy vấn đọc nhưng làm tăng nhu cầu lưu trữ và chi phí khi thêm/cập nhật/xóa dữ liệu. Với hệ thống sử dụng Java Driver hoặc Spring Data Neo4j, hiệu năng cần được đánh giá bằng chính các câu Cypher có tham số mà ứng dụng thực thi.

Các nguyên tắc hữu ích:

- **Bắt đầu từ mẫu truy vấn:** label/type, các thuộc tính trong `WHERE`, thứ tự `ORDER BY`, số hàng dự kiến và `LIMIT`.
- **Thiết kế đúng kiểu dữ liệu:** số cho giá, temporal cho ngày giờ, point cho tọa độ. Không sửa kiểu bằng biểu thức lặp lại tại thời điểm đọc nếu có thể chuẩn hóa lúc ghi.
- **Đặt thứ tự composite index có chủ đích:** các điều kiện bằng trước điều kiện phạm vi; kiểm tra khi truy vấn thiếu khóa đầu.
- **Cân nhắc tính duy nhất:** nếu thuộc tính `sku` phải duy nhất, một **uniqueness constraint** phù hợp là quy tắc toàn vẹn dữ liệu, và có thể tạo index nền tương ứng. Tránh tạo index trùng chức năng mà không kiểm tra schema hiện có.
- **Theo dõi trạng thái index:** index cần `ONLINE` để phục vụ truy vấn; các lỗi tạo/populate index phải được xử lý trước khi benchmarking.
- **Kiểm tra cả sắp xếp và phân trang:** index trên giá không tự bảo đảm thứ tự ổn định khi nhiều sản phẩm cùng giá; thiết kế khóa phụ nếu cần.
- **Chỉ tạo index đem lại lợi ích đo được:** ưu tiên truy vấn thường xuyên hoặc tốn chi phí; xem lại index không còn được sử dụng.

### Quy trình quyết định nhanh

~~~mermaid
flowchart TD
    A["Xác định mẫu MATCH và WHERE / ORDER BY"] --> B{"Lọc thuộc tính kiểu gì?"}
    B -->|"Bằng, khoảng, STARTS WITH"| C["Đánh giá RANGE index"]
    B -->|"CONTAINS / ENDS WITH"| D["Đánh giá TEXT index"]
    B -->|"Khoảng cách / vùng không gian"| E["Đánh giá POINT index"]
    B -->|"Chỉ label / relationship type"| F["Đánh giá token lookup index"]
    C --> G{"Có nhiều thuộc tính lọc?"}
    G -->|"Có"| H["Thử composite index phù hợp thứ tự điều kiện"]
    G -->|"Không"| I["Thử index đơn thuộc tính"]
    H --> J["SHOW INDEXES, EXPLAIN, PROFILE"]
    I --> J
    D --> J
    E --> J
    F --> J
    J --> K["So sánh Rows, DB Hits, Sort và thời gian trên dữ liệu đại diện"]
~~~

## 11. Bài tập áp dụng

### Bài 1 — Chọn index

Hệ thống có node `:Book` với thuộc tính `genre`, `publishedAt` kiểu `DATE` và `rating` kiểu số. Truy vấn thường xuyên là:

~~~cypher
MATCH (b:Book)
WHERE b.genre = $genre
  AND b.publishedAt >= $fromDate
RETURN b.title, b.publishedAt
ORDER BY b.publishedAt DESC
LIMIT 30;
~~~

Hãy đề xuất một index, giải thích thứ tự thuộc tính và nêu cách xác minh hiệu quả.

**Gợi ý lời giải:**

~~~cypher
CREATE RANGE INDEX book_genre_published_at_idx IF NOT EXISTS
FOR (b:Book) ON (b.genre, b.publishedAt);
~~~

`genre` được lọc bằng chính xác; `publishedAt` là phạm vi và khóa sắp xếp trong nhóm `genre`. Kiểm tra trạng thái index bằng `SHOW INDEXES` rồi dùng `EXPLAIN`/`PROFILE` với tham số thực tế. Nếu truy vấn chủ yếu lọc ngày mà không có `genre`, cân nhắc index khác phù hợp.

### Bài 2 — Dự đoán kết quả và thứ tự

Với dữ liệu sản phẩm ở mục 3, truy vấn:

~~~cypher
MATCH (p:Product)
WHERE p.price >= 120000 AND p.price < 350000
RETURN p.sku AS sku, p.price AS price
ORDER BY p.price ASC;
~~~

**Đáp án:** `B001` (120.000), `B002` (150.000) và `H001` (150.000). Hai sản phẩm 150.000 không có thứ tự tương đối được bảo đảm. `E001` (350.000) bị loại vì điều kiện cận trên là `< 350000`.

### Bài 3 — Sửa truy vấn khó dùng index

Giả sử `:Order.totalAmount` đã lưu số. Đâu là vấn đề với truy vấn dưới đây nếu đã có range index trên `totalAmount`?

~~~cypher
MATCH (o:Order)
WHERE toInteger(o.totalAmount) > 500000
RETURN o;
~~~

**Gợi ý lời giải:** Biểu thức `toInteger(o.totalAmount)` là phép biến đổi trên thuộc tính. Nếu thuộc tính đã là số, viết `WHERE o.totalAmount > 500000` để bộ tối ưu có khả năng dùng range index trực tiếp. Xác minh bằng `EXPLAIN`/`PROFILE`; không nên suy ra từ cú pháp rằng mọi trường hợp sẽ chọn index.

### Bài 4 — Kiểm tra sắp xếp

Đã có index `(category, price)`. Truy vấn lọc `category = 'Books'` rồi `ORDER BY price`. Hãy quan sát kế hoạch để xác định có `Sort` hay không; sau đó thêm `ORDER BY price, sku` và so sánh kế hoạch. Giải thích vì sao phải có `sku` nếu người dùng yêu cầu phân trang ổn định khi nhiều sản phẩm đồng giá.

## 12. Tổng kết

- **Range index** là lựa chọn thường phù hợp với tra cứu thuộc tính bằng, khoảng, tiền tố chuỗi và kiểm tra thuộc tính hiện hữu trên node hoặc relationship.
- **`ORDER BY` có thể hưởng lợi từ thứ tự index**, nhất là khi điều kiện `WHERE` và thứ tự khóa index tương thích; không có bảo đảm tuyệt đối rằng mọi kế hoạch đều bỏ `Sort`.
- **Composite range index cần đúng thứ tự thuộc tính**: mẫu phổ biến là bằng chính xác ở khóa đầu, phạm vi/sắp xếp ở khóa sau.
- **Kiểu dữ liệu và biểu thức truy vấn rất quan trọng**: lưu số thành chuỗi hoặc bọc thuộc tính bằng hàm có thể làm sai thứ tự hoặc giảm khả năng tìm kiếm bằng index.
- **Kiểm chứng, không đoán**: dùng `SHOW INDEXES`, `EXPLAIN` và `PROFILE` trên truy vấn và dữ liệu đại diện, đồng thời cân đối chi phí index khi ghi dữ liệu.

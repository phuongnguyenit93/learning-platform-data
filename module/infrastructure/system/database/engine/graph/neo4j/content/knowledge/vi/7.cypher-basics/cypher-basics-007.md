# Đặt bí danh, chú thích và định dạng truy vấn dễ bảo trì

> **Chương:** Nền tảng Cypher  
> **Module:** `DATABASE_ENGINE_GRAPH_NEO4J`

Trong Neo4j, dữ liệu được mô hình hóa bằng **property graph**: node biểu diễn thực thể, relationship biểu diễn liên kết và cả hai có thể chứa property. Cypher dùng các mẫu đồ thị để truy vấn quan hệ và đường đi. Khi một truy vấn phải phục vụ báo cáo, API Java hoặc ứng dụng Spring Data Neo4j trong thời gian dài, **tên biến rõ nghĩa, bí danh đầu ra ổn định, chú thích đúng chỗ và cách trình bày nhất quán** giúp nhóm phát triển đọc, sửa và kiểm tra truy vấn an toàn hơn.

Bài này tập trung vào ba kỹ năng của nền tảng Cypher: **đặt bí danh với `AS`**, **viết chú thích**, và **định dạng truy vấn để dễ bảo trì**. Các ví dụ cũng cho thấy cách `WITH` tạo ranh giới phạm vi biến và thay đổi luồng dữ liệu giữa các mệnh đề.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Phân biệt **biến mẫu đồ thị** trong `MATCH` với **bí danh cột kết quả** tạo bởi `AS`.
2. Dùng `AS` trong `RETURN` và `WITH`, hiểu biến nào còn được sử dụng sau `WITH`.
3. Viết chú thích một dòng (`//`) và nhiều dòng (`/* ... */`) để giải thích ý định xử lý.
4. Định dạng `MATCH`, `WHERE`, `WITH`, `RETURN`, `ORDER BY` và `LIMIT` nhất quán.
5. Chỉnh sửa một truy vấn khó đọc thành truy vấn có tên và cấu trúc dễ kiểm tra, đồng thời giữ nguyên ý nghĩa kết quả.

## 2. Đồ thị mẫu dùng xuyên suốt bài

Giả sử hệ thống bán hàng quản lý khách hàng và đơn hàng theo mẫu:

~~~text
(:Customer)-[:PLACED]->(:Order)

Customer {customerId, name}
Order    {orderId, placedAt, totalAmount}
~~~

Một khách hàng có thể đặt nhiều đơn hàng. Để chạy các truy vấn trong bài trên một **cơ sở dữ liệu thử nghiệm trống**, tạo ba đơn hàng như sau:

~~~cypher
CREATE
  (an:Customer {
    customerId: 'C001',
    name: 'An'
  }),
  (binh:Customer {
    customerId: 'C002',
    name: 'Bình'
  }),
  (order101:Order {
    orderId: 'O101',
    placedAt: date('2026-01-03'),
    totalAmount: 500000
  }),
  (order102:Order {
    orderId: 'O102',
    placedAt: date('2026-01-12'),
    totalAmount: 150000
  }),
  (order103:Order {
    orderId: 'O103',
    placedAt: date('2026-02-01'),
    totalAmount: 700000
  })
CREATE
  (an)-[:PLACED]->(order101),
  (an)-[:PLACED]->(order102),
  (binh)-[:PLACED]->(order103);
~~~

Đoạn `CREATE` dùng để minh họa, nên **chỉ chạy một lần trên dữ liệu thử nghiệm**; chạy lặp lại sẽ tạo thêm node/relationship trùng về mặt nghiệp vụ. Mọi truy vấn bên dưới giả định `Order.placedAt` có kiểu `DATE`, `Order.totalAmount` là số nguyên và dữ liệu không chứa bản ghi trùng.

## 3. Biến trong mẫu đồ thị và bí danh `AS`

### 3.1. Biến không đồng nghĩa với label hay relationship type

Xét truy vấn:

~~~cypher
MATCH (customer:Customer)-[placement:PLACED]->(purchase:Order)
RETURN
  customer.name AS customerName,
  purchase.orderId AS orderId,
  type(placement) AS relationshipType
ORDER BY customerName ASC, orderId ASC;
~~~

Các thành phần có vai trò khác nhau:

| Thành phần | Vai trò | Ý nghĩa |
|---|---|---|
| `customer` | Biến node | Tham chiếu từng node `Customer` được ghép trong mẫu |
| `Customer` | Label | Phân loại node khách hàng |
| `placement` | Biến relationship | Tham chiếu cạnh nối khách hàng với đơn hàng |
| `PLACED` | Relationship type | Phân loại quan hệ “đã đặt” |
| `purchase` | Biến node | Tham chiếu node `Order` khớp mẫu |
| `customer.name` | Biểu thức property | Lấy tên từ node đang gắn với `customer` |
| `AS customerName` | Bí danh đầu ra | Đặt tên cột trả về là `customerName` |

`customer` và `purchase` được **khai báo ngay trong mẫu `MATCH`**; chúng không cần `AS`. Ngược lại, `AS` đặt tên cho giá trị mà một mệnh đề chiếu ra, ví dụ `customer.name AS customerName` hoặc `count(purchase) AS orderCount`.

Các cột truy vấn trên mang tên `customerName`, `orderId` và `relationshipType`. Điều này hữu ích khi Java Driver đọc kết quả bằng tên cột, chẳng hạn `record.get("customerName")`. Đổi bí danh đầu ra có thể yêu cầu sửa mã Java hoặc cấu trúc DTO phụ thuộc vào tên đó.

### 3.2. Đặt bí danh cho biểu thức, không chỉ property

`AS` áp dụng cho nhiều loại biểu thức:

~~~cypher
MATCH (customer:Customer)-[:PLACED]->(purchase:Order)
RETURN
  customer.customerId AS customerId,
  coalesce(customer.name, 'Chưa có tên') AS customerName,
  purchase.totalAmount * 1.1 AS amountWithTax
ORDER BY customerId ASC;
~~~

Ở đây `coalesce(...)` tạo tên hiển thị dự phòng; biểu thức nhân tạo giá trị tính toán. `AS` không đổi tên property thật trên node và không ghi dữ liệu xuống cơ sở dữ liệu: nó chỉ đặt tên cho cột kết quả trong lần truy vấn này.

Tên bí danh nên thể hiện nội dung hoặc đơn vị khi cần: `orderCount`, `totalAmount`, `averageAmount`, `customerName`. Tránh các tên `a`, `b`, `x1` hoặc `data` nếu người đọc phải đoán ý nghĩa.

### 3.3. `WITH`: đặt bí danh trung gian và chuyển phạm vi biến

`RETURN` thường là điểm xuất kết quả cuối cùng; `WITH` chuyển dữ liệu sang phần kế tiếp của truy vấn. `WITH` cũng có thể gom nhóm, tính toán và đặt bí danh cho kết quả trung gian:

~~~cypher
MATCH (customer:Customer)-[:PLACED]->(purchase:Order)
WITH
  customer,
  count(purchase) AS orderCount
WHERE orderCount >= 2
RETURN
  customer.customerId AS customerId,
  customer.name AS customerName,
  orderCount
ORDER BY customerName ASC;
~~~

Luồng thực thi ở mức ý nghĩa:

1. `MATCH` tìm từng cặp khách hàng–đơn hàng.
2. `WITH customer, count(purchase) AS orderCount` gom theo `customer` và tính số đơn.
3. `WHERE orderCount >= 2` lọc **sau khi** đã tính `orderCount`.
4. `RETURN` chọn các cột đầu ra cho ứng dụng.

Với dữ liệu mẫu, kết quả chỉ có khách hàng **An**, `customerId = 'C001'` và `orderCount = 2`.

**Quy tắc phạm vi:** sau `WITH`, chỉ những biến hoặc bí danh đã được chuyển tiếp mới khả dụng ở các mệnh đề sau. Ví dụ dưới đây **sai** vì `customer` bị loại khỏi phạm vi:

~~~cypher
// Ví dụ lỗi: customer không còn trong phạm vi sau WITH.
MATCH (customer:Customer)
WITH customer.name AS customerName
RETURN customer.customerId AS customerId;
~~~

Cách viết đúng là chuyển tiếp cả biến cần dùng:

~~~cypher
MATCH (customer:Customer)
WITH
  customer,
  customer.name AS customerName
RETURN
  customer.customerId AS customerId,
  customerName;
~~~

Có thể đổi tên một biến với `WITH customer AS buyer` rồi dùng `buyer` ở phần sau. Tuy nhiên nên thực hiện khi tên mới giúp làm rõ vai trò ở giai đoạn tiếp theo, tránh đổi tên tùy tiện giữa truy vấn.

**Lưu ý khi gom nhóm:** mọi biểu thức không tổng hợp được đưa vào `WITH` là khóa nhóm tương ứng. Ví dụ `WITH customer, purchase, count(purchase) AS orderCount` nhóm theo cả `customer` và `purchase`, vì vậy không còn tính tổng số đơn *theo từng khách hàng* như mong đợi. Chỉ chuyển tiếp những biến thật sự cần thiết; dùng `WITH *` quá rộng có thể khiến truy vấn khó theo dõi và vô tình thay đổi mức độ gom nhóm.

### 3.4. Quy ước tên dễ bảo trì

| Đối tượng | Quy ước gợi ý | Ví dụ |
|---|---|---|
| Biến node/relationship | `lowerCamelCase`, tên theo vai trò | `customer`, `purchase`, `placedRelationship` |
| Bí danh kết quả | `lowerCamelCase`, mang ý nghĩa nghiệp vụ | `customerName`, `orderCount`, `totalSpent` |
| Label | `UpperCamelCase` | `Customer`, `Order` |
| Relationship type | `UPPER_SNAKE_CASE` | `PLACED`, `BELONGS_TO` |
| Property | Theo schema có sẵn, thường là `lowerCamelCase` | `customerId`, `placedAt` |
| Tham số | Tên rõ nghĩa, có tiền tố `$` khi truy vấn | `$fromDate`, `$minOrders`, `$limit` |

Neo4j phân biệt chữ hoa–chữ thường ở các tên như label, relationship type và property. Vì vậy, **định dạng và chuẩn hóa cách đặt tên không được tự ý đổi tên schema hiện hữu**. Với tên chứa khoảng trắng hoặc ký tự đặc biệt, Cypher hỗ trợ bao identifier bằng dấu backtick (ví dụ `` `customer name` ``); tuy nhiên tên ổn định, không dấu cách thường dễ ánh xạ sang mã Java hơn.

## 4. Chú thích trong Cypher

Cypher hỗ trợ hai kiểu chú thích thông dụng:

- `//`: chú thích từ vị trí dấu này đến hết dòng.
- `/* ... */`: chú thích khối, có thể trải trên nhiều dòng.

~~~cypher
// Báo cáo doanh thu của các đơn kể từ ngày bắt đầu.
MATCH (customer:Customer)-[:PLACED]->(purchase:Order)
WHERE purchase.placedAt >= date($fromDate)

/*
  Gom theo khách hàng trước khi trả kết quả.
  Nhờ vậy mỗi khách hàng xuất hiện một hàng trong báo cáo.
*/
WITH
  customer,
  sum(purchase.totalAmount) AS totalSpent
RETURN
  customer.name AS customerName,
  totalSpent
ORDER BY totalSpent DESC;
~~~

Chú thích không tham gia vào logic khớp mẫu hoặc tính tổng. Một dấu `//` đặt giữa dòng sẽ khiến phần còn lại của dòng đó được coi là chú thích; khi tắt tạm một dòng truy vấn, cần kiểm tra các dấu phẩy, mệnh đề và biểu thức còn lại vẫn hợp lệ.

### 4.1. Viết chú thích về *lý do*, không lặp lại cú pháp

Ví dụ thiếu thông tin:

~~~cypher
// Đếm đơn hàng
WITH customer, count(purchase) AS orderCount
~~~

Ví dụ có ích hơn:

~~~cypher
// Gom theo khách hàng tại đây để lọc các khách có từ hai đơn,
// tránh lọc nhầm trước bước tổng hợp.
WITH customer, count(purchase) AS orderCount
WHERE orderCount >= 2
~~~

Ưu tiên giải thích điều kiện nghiệp vụ, giả định kiểu dữ liệu, hoặc quyết định dễ gây hiểu nhầm. Những điểm tên biến và cú pháp đã thể hiện rõ không cần chú thích thêm.

### 4.2. Lưu ý về nội dung và vị trí chú thích

- Giữ chú thích sát đoạn truy vấn mà nó giải thích; cập nhật chú thích khi logic thay đổi.
- Không để mật khẩu, token, dữ liệu khách hàng nhạy cảm hoặc thông tin kết nối trong chú thích.
- Tránh chú thích che phủ cả khối mã không còn sử dụng trong bản chính; dùng lịch sử quản lý phiên bản để xem lại mã cũ.
- `//` và `/* ... */` nằm **bên trong chuỗi ký tự** là nội dung chuỗi, không phải chú thích.
- Không dùng cú pháp `--` của SQL để thay cho `//` trong Cypher.

## 5. Định dạng truy vấn để đọc theo từng giai đoạn

Một truy vấn dễ bảo trì cho phép người đọc nhanh chóng nhận ra: **đang tìm mẫu nào**, **lọc điều kiện gì**, **tổng hợp ở đâu**, và **trả những cột nào**.

Một phong cách gợi ý, có thể thống nhất thành quy ước của dự án:

| Thành phần | Cách trình bày |
|---|---|
| Mệnh đề Cypher | Viết hoa `MATCH`, `WHERE`, `WITH`, `RETURN`, `ORDER BY`, `LIMIT`; bắt đầu mệnh đề trên dòng mới |
| Mẫu đồ thị | Giữ node và relationship liên quan gần nhau; chọn biến rõ nghĩa |
| Danh sách dài trong `WITH` / `RETURN` | Mỗi biểu thức một dòng, thụt vào hai dấu cách, đặt dấu phẩy cuối dòng trừ dòng cuối |
| Điều kiện phức hợp | Tách các điều kiện `AND` / `OR` dễ đọc; dùng ngoặc khi có nhiều mức ưu tiên |
| Sắp xếp | Ghi rõ tiêu chí và chiều `ASC` / `DESC`, nhất là với báo cáo |
| Tham số | Dùng `$paramName` cho giá trị từ ứng dụng, tránh ghép trực tiếp chuỗi truy vấn |
| Chú thích | Nêu lý do nghiệp vụ hoặc giả định ảnh hưởng đến kết quả, đặt gần mã liên quan |

### 5.1. Trước và sau khi định dạng

Truy vấn sau hợp lệ nhưng khó đọc, với biến và bí danh chưa diễn đạt mục đích:

~~~cypher
MATCH(c:Customer)-[:PLACED]->(o:Order) WHERE o.placedAt>=date($fromDate) WITH c,count(o) AS n,sum(o.totalAmount) AS s WHERE n >= $minOrders RETURN c.customerId AS id,c.name AS name,n,s ORDER BY s DESC LIMIT $limit;
~~~

Phiên bản dễ bảo trì:

~~~cypher
MATCH (customer:Customer)-[:PLACED]->(purchase:Order)
WHERE purchase.placedAt >= date($fromDate)
WITH
  customer,
  count(purchase) AS orderCount,
  sum(purchase.totalAmount) AS totalSpent
WHERE orderCount >= $minOrders
RETURN
  customer.customerId AS customerId,
  customer.name AS customerName,
  orderCount,
  totalSpent
ORDER BY
  totalSpent DESC,
  customerName ASC
LIMIT $limit;
~~~

Phiên bản sau làm rõ ba giai đoạn: lấy những đơn trong khoảng thời gian, tổng hợp theo khách hàng, rồi trả báo cáo đã sắp xếp. Ngoài định dạng, phiên bản sau thêm tiêu chí phụ `customerName ASC` để thứ tự dễ dự đoán khi hai khách có cùng `totalSpent`; nếu cần thứ tự **duy nhất** trong mọi trường hợp, có thể sắp xếp thêm `customerId ASC`.

### 5.2. Thứ tự mệnh đề thể hiện ý nghĩa

Với báo cáo tổng hợp, trình tự thường gặp là:

~~~text
MATCH ...       Tìm các mẫu node/relationship
WHERE ...       Lọc các hàng trước tổng hợp
WITH ...        Nhóm, tính toán, đặt bí danh trung gian
WHERE ...       Lọc theo giá trị đã tổng hợp
RETURN ...      Chọn và đặt tên cột kết quả
ORDER BY ...    Sắp xếp
LIMIT ...       Giới hạn số hàng trả về
~~~

Ví dụ, cần lọc khách có ít nhất hai đơn thì điều kiện `orderCount >= 2` thuộc sau `WITH` tạo ra `orderCount`. Đặt điều kiện đó trong `WHERE` ngay sau `MATCH` là sai phạm vi vì bí danh chưa tồn tại.

Khi truy vấn dài hoặc có nhiều giai đoạn `WITH`, nên đặt tên biến khác biệt theo nghĩa (`customer`, `purchase`, `orderCount`) và chỉ giữ các biến cần dùng tiếp. Việc này đồng thời giúp tìm lỗi khi mở rộng truy vấn.

### 5.3. Phân biệt dễ đọc với tối ưu hiệu năng

Viết hoa keyword, thụt lề hay đổi bí danh thường giúp con người đọc mã; **chúng không tự tạo index hoặc làm đường đi ngắn hơn**. Ngược lại, vị trí `WHERE`, biến trong `WITH` và số lượng hàng qua từng giai đoạn có thể ảnh hưởng đến ý nghĩa và hiệu năng thực thi.

Dùng `EXPLAIN` để xem kế hoạch dự kiến, và `PROFILE` để xem thống kê thực thi khi cần điều tra truy vấn chậm. `PROFILE` **thực sự chạy truy vấn**, vì vậy chỉ áp dụng với câu lệnh ghi khi bạn có chủ đích thực hiện thay đổi dữ liệu.

## 6. Ví dụ hoàn chỉnh: báo cáo khách hàng và tổng giá trị đơn

**Yêu cầu nghiệp vụ:** liệt kê những khách hàng có từ một số lượng đơn tối thiểu kể từ ngày bắt đầu; hiển thị mã khách hàng, tên, số đơn, tổng số tiền, ưu tiên khách có tổng giá trị đơn lớn hơn.

**Tham số do ứng dụng truyền vào:**

~~~json
{
  "fromDate": "2026-01-01",
  "minOrders": 1,
  "limit": 10
}
~~~

**Truy vấn Cypher:**

~~~cypher
// Báo cáo chi tiêu theo khách hàng trong khoảng thời gian cần xét.
MATCH (customer:Customer)-[:PLACED]->(purchase:Order)
WHERE purchase.placedAt >= date($fromDate)

/*
  Tổng hợp theo khách hàng trước khi áp điều kiện số đơn tối thiểu.
  purchase.placedAt trong dữ liệu mẫu có kiểu DATE.
*/
WITH
  customer,
  count(purchase) AS orderCount,
  sum(purchase.totalAmount) AS totalSpent
WHERE orderCount >= $minOrders

RETURN
  customer.customerId AS customerId,
  customer.name AS customerName,
  orderCount,
  totalSpent
ORDER BY
  totalSpent DESC,
  customerName ASC,
  customerId ASC
LIMIT $limit;
~~~

Với dữ liệu mẫu và bộ tham số trên, kết quả là:

| customerId | customerName | orderCount | totalSpent |
|---|---|---:|---:|
| C002 | Bình | 1 | 700000 |
| C001 | An | 2 | 650000 |

**Cách đọc kết quả:**

- `MATCH` tạo một hàng cho mỗi quan hệ `PLACED` phù hợp. Ở dữ liệu mẫu có ba hàng.
- `WHERE` trước `WITH` chỉ giữ đơn từ ngày `2026-01-01` trở đi.
- `WITH customer, count(...), sum(...)` tạo một hàng cho mỗi khách hàng và đặt tên hai giá trị tổng hợp.
- `WHERE` tiếp theo áp bộ lọc `$minOrders` lên số đơn đã tổng hợp.
- `RETURN` công bố bốn tên cột ổn định, thuận tiện cho ứng dụng đọc theo tên.
- `ORDER BY` và `LIMIT` quyết định thứ tự và số hàng báo cáo gửi về.

Nếu thay `minOrders` thành `2`, chỉ còn hàng của **An**. Nếu thay `fromDate` thành `2026-02-01` và giữ `minOrders = 1`, chỉ còn hàng của **Bình**.

Bí danh `orderCount` và `totalSpent` ở đây không đại diện cho property thật của node `Customer`: chúng là giá trị được tính trong kết quả truy vấn. Khi viết Java Driver, cần truyền `fromDate`, `minOrders`, `limit` bằng cơ chế parameter của driver rồi đọc cột theo đúng tên đã khai báo trong `RETURN`. Cách này giúp tránh phụ thuộc vào văn bản hiển thị mặc định của biểu thức Cypher.

## 7. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân phổ biến | Hướng xử lý |
|---|---|---|
| `Variable ... not defined` sau `WITH` | Biến không được chuyển tiếp | Bổ sung biến cần thiết trong danh sách `WITH` hoặc sử dụng đúng bí danh mới |
| Không lọc được theo `orderCount` tại `MATCH` | `orderCount` chỉ xuất hiện sau bước tổng hợp | Chuyển bộ lọc sang `WHERE` sau `WITH ... AS orderCount` |
| Số đơn đếm ra là `1` cho nhiều hàng của cùng một khách | Vô tình đưa `purchase` vào khóa nhóm của `WITH` | Chỉ nhóm theo `customer` nếu muốn một hàng trên mỗi khách |
| Ứng dụng không đọc được cột `customerName` | Bí danh `RETURN` bị đổi hoặc viết khác chữ hoa–thường | Thống nhất tên cột như một phần của hợp đồng giữa truy vấn và ứng dụng |
| Một phần truy vấn “biến mất” khi thêm `//` | `//` chú thích toàn bộ phần còn lại của dòng | Chuyển mệnh đề sang dòng mới; kiểm tra dấu phẩy và ngoặc |
| Truy vấn có nhiều tên `a`, `b`, `cnt` | Tên không thể hiện vai trò nghiệp vụ | Đổi thành `customer`, `purchase`, `orderCount` |
| Thứ tự hai hàng bằng điểm xếp hạng thay đổi | `ORDER BY` chưa đủ tiêu chí phân định | Thêm khóa ổn định, ví dụ `customerId ASC` |

Một quy trình rà soát nhanh trước khi đưa truy vấn vào ứng dụng:

1. **Mẫu:** mỗi biến có tên theo vai trò? Label, relationship type, property có khớp schema?
2. **Phạm vi:** mọi biến dùng sau `WITH` có được chuyển tiếp? Bí danh được tạo trước khi sử dụng?
3. **Tổng hợp:** `WITH` có giữ đúng khóa nhóm? Số lượng hàng sau tổng hợp có đúng mục tiêu?
4. **Kết quả:** tên cột `RETURN` ổn định, không trùng nghĩa và phù hợp với mã Java/DTO?
5. **Trình bày:** các mệnh đề, điều kiện, danh sách cột và tiêu chí sắp xếp có thể đọc theo từng giai đoạn?
6. **Chú thích:** ghi rõ ý định quan trọng, không chứa bí mật và còn đúng với logic hiện tại?
7. **Kiểm chứng:** chạy trên dữ liệu mẫu có kết quả đã dự đoán; nếu cần tối ưu, xem kế hoạch bằng `EXPLAIN`.

## 8. Bài tập thực hành có đáp án

### Bài 1 — Đặt tên cột rõ nghĩa

**Yêu cầu:** lấy mã và tên khách hàng; tên cột đầu ra phải là `customerId` và `customerName`; sắp xếp theo mã tăng dần.

~~~cypher
MATCH (customer:Customer)
RETURN
  customer.customerId AS customerId,
  customer.name AS customerName
ORDER BY customerId ASC;
~~~

### Bài 2 — Giữ đúng phạm vi và nhóm

**Yêu cầu:** tìm khách hàng có ít nhất hai đơn, trả về `customerName` và `orderCount`. Dùng `WITH` để tính tổng số đơn và lọc kết quả.

~~~cypher
MATCH (customer:Customer)-[:PLACED]->(purchase:Order)
WITH
  customer,
  count(purchase) AS orderCount
WHERE orderCount >= 2
RETURN
  customer.name AS customerName,
  orderCount
ORDER BY customerName ASC;
~~~

**Tự kiểm tra:** trên dữ liệu mẫu chỉ có `An` với `orderCount = 2`. Hãy thử bỏ `customer` khỏi `WITH` rồi xác định vì sao `customer.name` không thể dùng ở `RETURN` nữa.

### Bài 3 — Thêm chú thích có mục đích

**Yêu cầu:** báo cáo số đơn từ ngày do người dùng truyền vào, một hàng trên mỗi khách hàng; giải thích bằng chú thích lý do đặt điều kiện ngày trước bước tổng hợp.

~~~cypher
// Lọc theo ngày trước khi nhóm để chỉ đếm đơn trong kỳ báo cáo.
MATCH (customer:Customer)-[:PLACED]->(purchase:Order)
WHERE purchase.placedAt >= date($fromDate)
WITH
  customer,
  count(purchase) AS orderCount
RETURN
  customer.name AS customerName,
  orderCount
ORDER BY orderCount DESC, customerName ASC;
~~~

## 9. Ghi nhớ

- **Biến trong mẫu** (`customer`, `purchase`) giúp tham chiếu node và relationship; **`AS`** đặt tên cho cột hoặc giá trị trung gian.
- **`WITH` tạo phạm vi tiếp theo**: biến bị bỏ khỏi `WITH` không còn dùng được phía sau; các biểu thức không tổng hợp trong `WITH` là khóa nhóm.
- **Chú thích** dùng `//` hoặc `/* ... */` để giải thích quyết định nghiệp vụ và giả định quan trọng.
- **Định dạng nhất quán** giúp nhìn rõ luồng `MATCH → WHERE → WITH → RETURN → ORDER BY → LIMIT` và nhận ra sai sót sớm.
- **Tên cột ổn định** đặc biệt quan trọng khi Cypher là phần truy vấn dữ liệu cho Java Driver, Spring Data Neo4j hoặc API phía trên.

Sau khi viết rõ ý định và kết quả mong muốn, hãy kiểm tra bằng dữ liệu nhỏ trước, rồi dùng `EXPLAIN`/`PROFILE` khi cần nghiên cứu kế hoạch thực thi hoặc hiệu năng trên dữ liệu thực tế.

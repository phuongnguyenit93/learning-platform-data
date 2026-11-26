# Cô lập bước tổng hợp để tránh nhân số hàng ngoài ý muốn

Trong Neo4j, dữ liệu được mô hình hóa bằng **node**, **relationship** và các thuộc tính của chúng (property graph). Cypher truy vấn các mẫu liên kết rất tự nhiên; tuy nhiên, một câu lệnh `MATCH` có thể sinh **nhiều hàng kết quả trung gian cho cùng một node**. Nếu mở rộng hai nhánh quan hệ độc lập rồi mới dùng `count()`, `sum()` hoặc `avg()`, số hàng có thể bị nhân lên và làm sai số liệu.

Bài này thuộc phần **Truy vấn con** và tập trung vào kỹ thuật **tổng hợp riêng từng nhánh bằng subquery `CALL`**. Ví dụ dùng Neo4j/Cypher để tính số đơn hàng, doanh thu và số đánh giá của khách hàng; các nguyên tắc tương tự áp dụng cho người dùng–bài viết–bình luận, sản phẩm–đơn hàng–thẻ phân loại, hay bất kỳ node nào có nhiều mối quan hệ một-nhiều.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao việc ghép nhiều nhánh `MATCH` tạo ra số hàng dạng `m × n` ngay cả khi truy vấn không viết `CROSS JOIN`.
2. Nhận ra kết quả tổng hợp sai do số hàng tăng, đặc biệt với `count()`, `sum()` và các phép tính có trọng số.
3. Dùng `CALL (biến) { ... }` để cô lập phép tổng hợp, trả về đúng một hàng chỉ số cho mỗi node đầu vào.
4. Phân biệt cách dùng `DISTINCT`, `WITH`, `OPTIONAL MATCH` và subquery, cũng như lựa chọn giải pháp phù hợp.
5. Kiểm tra số hàng trung gian và kế hoạch thực thi bằng `EXPLAIN`/`PROFILE`.

## 2. Hiểu đúng số hàng trong Cypher

Hãy xem đồ thị sau:

~~~text
                     ┌─[:PLACED]─> (O01:Order {amount: 120})
(C01:Customer {name: Mai})
                     ├─[:PLACED]─> (O02:Order {amount: 180})
                     ├─[:WROTE]──> (R01:Review)
                     ├─[:WROTE]──> (R02:Review)
                     └─[:WROTE]──> (R03:Review)
~~~

Khách hàng `C01` có **2 đơn hàng** và **3 đánh giá**. Hai nhánh `PLACED` và `WROTE` độc lập: mỗi đánh giá không tương ứng riêng với một đơn hàng.

Bạn có thể tạo dữ liệu thử trên một cơ sở dữ liệu **dành riêng cho thực hành**:

~~~cypher
// Chạy một lần trên database thử nghiệm; CREATE sẽ tạo thêm dữ liệu khi chạy lại.
CREATE (c:Customer {customerId: 'C01', name: 'Mai'})
CREATE (o1:Order {orderId: 'O01', amount: 120}),
       (o2:Order {orderId: 'O02', amount: 180}),
       (r1:Review {reviewId: 'R01'}),
       (r2:Review {reviewId: 'R02'}),
       (r3:Review {reviewId: 'R03'})
CREATE (c)-[:PLACED]->(o1),
       (c)-[:PLACED]->(o2),
       (c)-[:WROTE]->(r1),
       (c)-[:WROTE]->(r2),
       (c)-[:WROTE]->(r3)
RETURN c.customerId AS createdCustomer;
~~~

Truy vấn sau mở rộng **cả hai nhánh** trước khi trả kết quả:

~~~cypher
MATCH (c:Customer {customerId: 'C01'})
MATCH (c)-[:PLACED]->(o:Order)
MATCH (c)-[:WROTE]->(r:Review)
RETURN o.orderId AS orderId, r.reviewId AS reviewId
ORDER BY orderId, reviewId;
~~~

| Đơn hàng | Đánh giá |
|---|---|
| O01 | R01 |
| O01 | R02 |
| O01 | R03 |
| O02 | R01 |
| O02 | R02 |
| O02 | R03 |

Nhánh đơn hàng sinh 2 hàng ứng với `C01`. Với **mỗi** hàng đó, `MATCH` tiếp theo tìm ra 3 đánh giá; kết quả là `2 × 3 = 6` hàng. Đây là phép nhân độ lớn tập kết quả giữa hai nhánh độc lập, không phải Neo4j tự tạo thêm đơn hàng hoặc đánh giá.

| Giai đoạn | Số hàng ứng với C01 |
|---|---:|
| `MATCH` khách hàng | 1 |
| Mở rộng nhánh `PLACED` | 2 |
| Mở rộng thêm nhánh `WROTE` | 6 |
| Tổng hợp với `RETURN` | 1 hàng, **nhưng giá trị có thể sai** |

Điểm mấu chốt: **Cypher tổng hợp các hàng hiện có tại vị trí phép tổng hợp**, không tự khôi phục số node/relationship ban đầu.

## 3. Sai lầm thường gặp: tổng hợp sau khi mở rộng nhiều nhánh

~~~cypher
MATCH (c:Customer {customerId: 'C01'})
MATCH (c)-[:PLACED]->(o:Order)
MATCH (c)-[:WROTE]->(r:Review)
RETURN c.customerId AS customerId,
       count(o) AS orderCount,
       count(r) AS reviewCount,
       sum(o.amount) AS totalAmount;
~~~

**Kết quả từ dữ liệu minh họa:**

| Chỉ số | Kết quả sai | Kết quả đúng |
|---|---:|---:|
| `orderCount` | 6 | 2 |
| `reviewCount` | 6 | 3 |
| `totalAmount` | 900 | 300 |

`count(o)` đếm 6 lần xuất hiện của biến `o` trong 6 hàng; mỗi đơn hàng được đếm 3 lần. `count(r)` cũng đếm 6 lần; mỗi đánh giá xuất hiện 2 lần. `sum(o.amount)` cộng `120` ba lần và `180` ba lần nên thành `900`, thay vì `120 + 180 = 300`.

Khi có `m` đơn hàng và `n` đánh giá của cùng một khách hàng (đều lớn hơn 0), hai nhánh sẽ tạo `m × n` hàng. Doanh thu theo đơn hàng có thể bị nhân `n` lần. Thêm nhánh độc lập thứ ba với `k` kết quả có thể làm số hàng tăng đến `m × n × k`.

**Lưu ý với `OPTIONAL MATCH`:** thay `MATCH` bằng hai `OPTIONAL MATCH` liên tiếp giúp giữ khách hàng khi thiếu một nhánh, nhưng **không giải quyết việc nhân hàng** khi cả hai nhánh đều có nhiều bản ghi.

~~~cypher
MATCH (c:Customer {customerId: 'C01'})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
OPTIONAL MATCH (c)-[:WROTE]->(r:Review)
RETURN c.customerId AS customerId,
       count(o) AS orderCount,
       count(r) AS reviewCount;
// Với C01 vẫn trả 6 và 6.
~~~

## 4. Giải pháp chính: cô lập từng phép tổng hợp bằng `CALL`

Với **Neo4j 5.23 trở lên**, dùng cú pháp subquery có danh sách biến nhập `CALL (c) { ... }`:

~~~cypher
MATCH (c:Customer {customerId: 'C01'})
CALL (c) {
    MATCH (c)-[:PLACED]->(o:Order)
    RETURN count(o) AS orderCount,
           coalesce(sum(o.amount), 0) AS totalAmount
}
CALL (c) {
    MATCH (c)-[:WROTE]->(r:Review)
    RETURN count(r) AS reviewCount
}
RETURN c.customerId AS customerId,
       orderCount,
       reviewCount,
       totalAmount;
~~~

Kết quả mong đợi: `C01 | 2 | 3 | 300`.

Diễn biến của truy vấn:

1. `MATCH` ngoài cùng chọn khách hàng `c`.
2. Subquery thứ nhất chỉ duyệt `PLACED` và tính `orderCount`, `totalAmount`. Do `RETURN` chỉ chứa phép tổng hợp, subquery trả **một hàng** cho mỗi `c`.
3. Subquery thứ hai chỉ duyệt `WROTE` và tính `reviewCount`, cũng trả **một hàng** cho mỗi `c`.
4. Truy vấn ngoài ghép các **kết quả đã tổng hợp**, không ghép từng đơn hàng với từng đánh giá.

~~~text
                          ┌─ CALL (c): PLACED ──> {orderCount: 2, totalAmount: 300} ─┐
(Customer C01) ───────────┤                                                      ├─> 1 hàng kết quả
                          └─ CALL (c): WROTE  ──> {reviewCount: 3} ───────────────┘
~~~

Subquery ở đây **tương quan (correlated subquery)** vì truy cập node `c` từ truy vấn ngoài. `CALL (c)` khai báo rõ biến được đưa vào từng subquery. Các alias `orderCount`, `reviewCount` và `totalAmount` được trả ra truy vấn ngoài và phải không trùng với tên biến đang được định nghĩa ở cùng phạm vi.

Nếu sử dụng phiên bản Neo4j hỗ trợ `CALL { ... }` nhưng **chưa hỗ trợ `CALL (c)`**, có thể dùng cú pháp nhập biến cũ:

~~~cypher
MATCH (c:Customer {customerId: 'C01'})
CALL {
    WITH c
    MATCH (c)-[:PLACED]->(o:Order)
    RETURN count(o) AS orderCount,
           coalesce(sum(o.amount), 0) AS totalAmount
}
CALL {
    WITH c
    MATCH (c)-[:WROTE]->(r:Review)
    RETURN count(r) AS reviewCount
}
RETURN c.customerId AS customerId,
       orderCount, reviewCount, totalAmount;
~~~

Cú pháp `WITH c` ở đầu subquery là cách nhập biến của các phiên bản cũ; ở Neo4j 5.23+ nên ưu tiên danh sách biến nhập `CALL (c)`. Kiểm tra phiên bản Cypher/Neo4j đang chạy trước khi sao chép cú pháp vào ứng dụng.

### Vì sao subquery tổng hợp vẫn giữ khách hàng không có dữ liệu?

Khi `MATCH` bên trong subquery không tìm được đơn hàng, phép tổng hợp `count(o)` **không có khóa nhóm** vẫn tạo ra một hàng với giá trị `0`. `coalesce(sum(o.amount), 0)` giúp diễn đạt rõ rằng doanh thu không có đơn hàng được coi là `0`. Do đó, các khách hàng không có đơn hàng hoặc không có đánh giá vẫn có thể xuất hiện trong kết quả bên ngoài.

Ngược lại, subquery chỉ trả các hàng khớp quan hệ, **không có phép tổng hợp đảm bảo một hàng**, có thể trả 0 hoặc nhiều hàng và làm mất hoặc nhân hàng của `c`:

~~~cypher
MATCH (c:Customer)
CALL (c) {
    MATCH (c)-[:PLACED]->(o:Order)
    RETURN o
}
RETURN c.customerId, o.orderId;
// Mỗi đơn hàng tạo một hàng; khách hàng không có đơn hàng bị loại.
~~~

Muốn bảo toàn một hàng đầu ra cho mỗi khách hàng, cần kiểm soát **cardinality** của subquery, không chỉ đặt một `CALL` quanh bất kỳ câu lệnh nào.

## 5. Tổng hợp lần lượt bằng `WITH`: một lựa chọn khác

Với hai nhánh đơn giản, có thể tổng hợp nhánh thứ nhất **trước khi** mở rộng nhánh thứ hai:

~~~cypher
MATCH (c:Customer {customerId: 'C01'})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c,
     count(o) AS orderCount,
     coalesce(sum(o.amount), 0) AS totalAmount
OPTIONAL MATCH (c)-[:WROTE]->(r:Review)
RETURN c.customerId AS customerId,
       orderCount,
       totalAmount,
       count(r) AS reviewCount;
~~~

`WITH c, count(o), sum(o.amount)` gom dữ liệu đơn hàng về **một hàng cho mỗi `c`** trước khi truy vấn mở rộng đánh giá. Kết quả vẫn là `C01 | 2 | 300 | 3` theo thứ tự cột của truy vấn.

| Tiêu chí | `WITH` tổng hợp sớm | Subquery `CALL` độc lập |
|---|---|---|
| Phân tách từng nhánh | Theo thứ tự các mệnh đề trong một pipeline | Mỗi nhánh nằm trong một khối riêng |
| Phụ thuộc vào thứ tự | Có: phải tổng hợp nhánh trước khi mở nhánh tiếp | Ít hơn: mỗi nhánh tự tổng hợp |
| Bổ sung nhiều nhánh | Cần quản lý các `WITH` và khóa nhóm | Có thể thêm từng khối `CALL` |
| Khả năng mở rộng mã | Gọn với ít nhánh | Dễ đọc hơn khi nhiều phép tính khác nhau |
| Yêu cầu quan trọng | Giữ đúng khóa nhóm, như `c` | Mỗi subquery trả đúng số hàng mong muốn |

Cả hai cách đều hợp lệ. `CALL` đặc biệt hữu ích khi mỗi nhánh có bộ lọc, cách tính hoặc cấp nhóm riêng, chẳng hạn chỉ tính đơn đã thanh toán nhưng đếm tất cả đánh giá.

## 6. Vì sao `DISTINCT` không phải cách chữa chung?

Có thể sửa **riêng hai phép đếm node** trong ví dụ bằng:

~~~cypher
MATCH (c:Customer {customerId: 'C01'})
MATCH (c)-[:PLACED]->(o:Order)
MATCH (c)-[:WROTE]->(r:Review)
RETURN count(DISTINCT o) AS orderCount,
       count(DISTINCT r) AS reviewCount,
       sum(o.amount) AS totalAmount;
// orderCount = 2, reviewCount = 3, nhưng totalAmount = 900 (vẫn sai).
~~~

`count(DISTINCT o)` chỉ đếm mỗi **node `o` khác nhau** một lần. Nó không xóa các hàng trùng trước khi `sum(o.amount)` thực hiện. Một cách vá khác là `sum(DISTINCT o.amount)`, nhưng cách đó cũng dễ sai:

- Giả sử hai đơn hàng khác nhau cùng có `amount = 120`.
- Tổng đúng là `120 + 120 = 240`.
- `sum(DISTINCT o.amount)` chỉ cộng **một giá trị 120**, trả `120`.

`DISTINCT` áp dụng cho **giá trị hoặc biểu thức được chỉ định**, không hiểu quy tắc nghiệp vụ “mỗi đơn hàng tính đúng một lần”. Nếu dữ liệu có thể chứa nhiều relationship đến cùng một đơn hàng, hãy khử trùng theo **định danh đơn hàng** *bên trong nhánh độc lập*, rồi mới tổng hợp:

~~~cypher
MATCH (c:Customer {customerId: 'C01'})
CALL (c) {
    MATCH (c)-[:PLACED]->(o:Order)
    WITH DISTINCT o
    RETURN count(o) AS orderCount,
           coalesce(sum(o.amount), 0) AS totalAmount
}
RETURN c.customerId AS customerId, orderCount, totalAmount;
~~~

Kỹ thuật `WITH DISTINCT o` có ý nghĩa khi một đơn hàng có thể xuất hiện qua nhiều đường khớp mà nghiệp vụ chỉ muốn tính **một lần theo node Order**. Nếu mục tiêu là đếm các **relationship** thực tế hoặc số lượt phát sinh, không nên tự ý khử trùng chúng.

## 7. Trường hợp thực tế và các bẫy về số hàng

### 7.1. Lọc riêng trong từng subquery

Ví dụ: đếm tất cả đơn hàng, tính doanh thu các đơn đã thanh toán, và chỉ đếm đánh giá đã công khai. Giả sử các node có thêm thuộc tính `status`, `isPublic`:

~~~cypher
MATCH (c:Customer)
CALL (c) {
    MATCH (c)-[:PLACED]->(o:Order)
    RETURN count(o) AS allOrders
}
CALL (c) {
    MATCH (c)-[:PLACED]->(o:Order)
    WHERE o.status = 'PAID'
    RETURN coalesce(sum(o.amount), 0) AS paidRevenue
}
CALL (c) {
    MATCH (c)-[:WROTE]->(r:Review)
    WHERE r.isPublic = true
    RETURN count(r) AS publicReviews
}
RETURN c.customerId AS customerId,
       allOrders, paidRevenue, publicReviews
ORDER BY customerId;
~~~

Mỗi bộ lọc chỉ chi phối nhánh của nó. Đây là ưu điểm quan trọng khi các quan hệ có điều kiện nghiệp vụ không giống nhau.

### 7.2. Đầu vào đã bị nhân hàng trước khi gọi `CALL`

`CALL` được thực hiện trên các hàng đầu vào của truy vấn ngoài. Nếu `c` đã xuất hiện nhiều lần từ một `MATCH` trước đó, subquery có thể bị gọi lặp lại cho cùng một khách hàng và kết quả ngoài cùng vẫn có nhiều hàng:

~~~cypher
// Có thể tạo nhiều hàng / khách hàng nếu họ có nhiều tài khoản.
MATCH (c:Customer)-[:OWNS]->(a:Account)
WITH DISTINCT c
CALL (c) {
    MATCH (c)-[:PLACED]->(o:Order)
    RETURN count(o) AS orderCount
}
RETURN c.customerId AS customerId, orderCount;
~~~

`WITH DISTINCT c` chủ động xác lập **một hàng cho mỗi khách hàng** trước các phép tổng hợp độc lập. Dùng cách này chỉ khi nghiệp vụ thật sự muốn thống kê **theo khách hàng**; nếu phải thống kê theo **khách hàng và tài khoản**, khóa nhóm cần bao gồm cả `c` lẫn `a` và điều kiện trong subquery phải phản ánh đúng quan hệ đó.

### 7.3. Tổng hợp nhiều cấp quan hệ

Nếu doanh thu nằm trên `OrderLine` thay vì `Order`, có thể tổng hợp tất cả dòng hàng **trong cùng một subquery**, rồi trả một con số ra ngoài:

~~~cypher
MATCH (c:Customer)
CALL (c) {
    MATCH (c)-[:PLACED]->(:Order)-[:HAS_LINE]->(line:OrderLine)
    RETURN coalesce(
        sum(line.quantity * line.unitPrice),
        0
    ) AS grossAmount
}
CALL (c) {
    MATCH (c)-[:WROTE]->(r:Review)
    RETURN count(r) AS reviewCount
}
RETURN c.customerId AS customerId, grossAmount, reviewCount;
~~~

Ở đây phạm vi cộng là **dòng hàng**. Nếu cùng một `OrderLine` được khớp bởi nhiều đường đi và phải tính một lần theo dòng, cần khử trùng **dòng hàng** trước phép cộng. Không có cách khử trùng mặc định đúng cho mọi mô hình dữ liệu.

### 7.4. `COUNT { ... }` cho nhu cầu chỉ đếm

Trong các phiên bản Neo4j 5 hỗ trợ **count subquery**, cú pháp `COUNT { ... }` phù hợp khi chỉ cần đếm số lần khớp mẫu:

~~~cypher
MATCH (c:Customer)
RETURN c.customerId AS customerId,
       COUNT { (c)-[:PLACED]->(:Order) } AS orderCount,
       COUNT { (c)-[:WROTE]->(:Review) } AS reviewCount;
~~~

Hai biểu thức đếm được đánh giá độc lập theo từng `c`, nên không tự tạo tích `Orders × Reviews`. Tuy nhiên, `COUNT { ... }` đếm các **mẫu quan hệ khớp**; với nhiều relationship song song, số lần khớp có thể khác số node đích duy nhất. Với phép tính như `sum(amount)` hoặc nhiều chỉ số cùng nhánh, `CALL` tổng hợp thường linh hoạt hơn.

## 8. Kiểm tra và tối ưu truy vấn

**Kiểm tra logic trước, rồi mới tối ưu tốc độ.** Một truy vấn trả ra một hàng rất nhanh vẫn có thể chứa các số liệu đã bị nhân.

1. **Viết truy vấn chi tiết chưa tổng hợp:** trả các khóa như `o.orderId`, `r.reviewId` để quan sát số tổ hợp và tìm nơi bắt đầu nhân hàng.
2. **Xác định đơn vị cần đếm/cộng:** node Order, relationship PLACED, OrderLine hay một cặp khách hàng–đơn hàng? Đây là cơ sở để quyết định có cần `DISTINCT`.
3. **Thử các ca cạnh:** khách hàng có `0`/`1`/nhiều đơn và `0`/`1`/nhiều đánh giá; hai đơn có cùng số tiền; dữ liệu có đường đi trùng; đầu vào đã chứa khách hàng lặp.
4. **Kiểm tra kết quả với dữ liệu đã biết:** ví dụ trên phải ra `orderCount = 2`, `reviewCount = 3` và `totalAmount = 300`.
5. **Đo kế hoạch thực thi:** dùng `EXPLAIN` để xem kế hoạch dự kiến và `PROFILE` để xem số `Rows` thực chạy, `DB Hits` và các toán tử mở rộng/tổng hợp.

Ví dụ phân tích truy vấn có nguy cơ nhân hàng:

~~~cypher
PROFILE
MATCH (c:Customer {customerId: 'C01'})
MATCH (c)-[:PLACED]->(o:Order)
MATCH (c)-[:WROTE]->(r:Review)
RETURN count(o) AS orders, sum(o.amount) AS amount;
~~~

Trong bảng kế hoạch của Neo4j Browser, chú ý số hàng đi qua các toán tử mở rộng: từ 2 kết quả đơn hàng sang 6 tổ hợp sau khi mở đánh giá. **Không nhất thiết phải xuất hiện toán tử tên `CartesianProduct`** mới có hiện tượng nhân hàng; nhiều nhánh cùng dùng biến `c` cũng có thể nhân số tổ hợp.

Sau đó so sánh với phiên bản `CALL`:

~~~cypher
PROFILE
MATCH (c:Customer {customerId: 'C01'})
CALL (c) {
    MATCH (c)-[:PLACED]->(o:Order)
    RETURN count(o) AS orderCount,
           coalesce(sum(o.amount), 0) AS totalAmount
}
CALL (c) {
    MATCH (c)-[:WROTE]->(r:Review)
    RETURN count(r) AS reviewCount
}
RETURN orderCount, totalAmount, reviewCount;
~~~

Subquery tránh tạo **tích chéo hai tập kết quả trung gian**, nhưng không mặc nhiên đảm bảo mọi truy vấn sẽ nhanh hơn. Tổng thời gian còn phụ thuộc số khách hàng đầu vào, độ phân nhánh, chỉ mục trên thuộc tính tìm khách hàng, cách mô hình hóa quan hệ và kế hoạch của trình tối ưu. Khi truy vấn toàn bộ tập khách hàng lớn, nên đo trên dữ liệu có quy mô đại diện và chỉ trả các cột cần thiết.

## 9. Bảng chọn giải pháp nhanh

| Tình huống | Cách xử lý phù hợp |
|---|---|
| Hai nhánh một-nhiều độc lập, cần nhiều chỉ số ở mỗi nhánh | Tổng hợp riêng từng nhánh bằng `CALL (c) { ... }` |
| Ít nhánh, phép tính đơn giản, muốn một pipeline ngắn | `WITH` tổng hợp nhánh trước khi `MATCH` nhánh tiếp theo |
| Chỉ cần đếm lần khớp một mẫu | `COUNT { ... }` (nếu phiên bản hỗ trợ) |
| Cần đếm số node đích khác nhau | `count(DISTINCT node)`, hoặc `WITH DISTINCT node` trước khi tổng hợp |
| Cần tổng tiền theo từng đơn nhưng nhiều hàng trùng | Khử trùng **theo đơn hàng** trong nhánh rồi `sum()`; tránh `sum(DISTINCT amount)` |
| Cần giữ khách hàng dù không có dữ liệu liên kết | Subquery chỉ có tổng hợp không khóa nhóm, hoặc `OPTIONAL MATCH` kết hợp `WITH` đúng chỗ |
| Đầu vào có thể lặp một khách hàng | Chuẩn hóa khóa hàng bằng `WITH DISTINCT c` trước subquery nếu cần thống kê theo khách hàng |

## 10. Bài luyện tập

**Bài 1 — Dự đoán số liệu:** Một tác giả có 4 bài viết và 5 người theo dõi. Truy vấn mở cả hai nhánh rồi `RETURN count(post), count(follower)`. Kết quả là gì? Khi nào `count(DISTINCT post)` có thể hữu ích?

<details>
<summary>Gợi ý đáp án</summary>

Nếu mỗi bài và mỗi người theo dõi chỉ tạo một lần khớp, có `4 × 5 = 20` hàng nên cả hai `count(...)` đều là `20`. `count(DISTINCT post)` đưa phép đếm bài về `4`; để tránh nhân hàng ngay từ đầu, hãy tổng hợp hai nhánh độc lập.

</details>

**Bài 2 — Sửa truy vấn:** Hãy viết lại câu lệnh tính tổng tiền đơn hàng và số lượt đăng nhập của người dùng, biết mẫu dữ liệu là `(u:User)-[:BOUGHT]->(o:Order)` và `(u)-[:LOGGED_IN]->(s:Session)`. Yêu cầu luôn có một hàng theo `u` kể cả khi người dùng chưa đặt đơn hoặc chưa đăng nhập.

<details>
<summary>Lời giải tham khảo</summary>

~~~cypher
MATCH (u:User)
CALL (u) {
    MATCH (u)-[:BOUGHT]->(o:Order)
    RETURN count(o) AS orderCount,
           coalesce(sum(o.amount), 0) AS spent
}
CALL (u) {
    MATCH (u)-[:LOGGED_IN]->(s:Session)
    RETURN count(s) AS sessionCount
}
RETURN u, orderCount, spent, sessionCount;
~~~

Mỗi `CALL` trả một hàng tổng hợp không khóa nhóm nên giữ các `u` không có quan hệ tương ứng. Cần điều chỉnh quy tắc đếm nếu nhiều relationship có thể trỏ đến cùng một node đích.

</details>

**Bài 3 — Phân tích sai lầm:** Hai đơn hàng đều có `amount = 200`. Vì sao `sum(DISTINCT o.amount)` có thể trả `200` thay vì `400`? Hãy mô tả cách dùng `WITH DISTINCT o` bên trong subquery để cộng theo định danh đơn hàng.

## 11. Ghi nhớ

- **Nhân hàng xảy ra trước tổng hợp.** Hai nhánh một-nhiều độc lập cùng gắn vào một node có thể tạo `m × n` tổ hợp.
- **Phải xác định đúng đơn vị thống kê.** Đếm số node, số relationship và số dòng giao dịch là ba mục tiêu có thể khác nhau.
- **Cô lập phép tổng hợp bằng subquery `CALL`** giúp mỗi nhánh trả số liệu đã gói gọn và giữ kết quả của nhánh khác không bị nhân lên.
- **`DISTINCT` không thay thế mô hình tổng hợp đúng**, đặc biệt đối với phép cộng các giá trị bằng nhau.
- **Quan sát `Rows` bằng `PROFILE`** để phát hiện lỗi số hàng và đánh giá chi phí truy vấn trên dữ liệu thực tế.

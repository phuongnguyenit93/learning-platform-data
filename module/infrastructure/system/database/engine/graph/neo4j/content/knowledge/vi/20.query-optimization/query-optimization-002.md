# Đẩy điều kiện lọc đến vị trí có ngữ nghĩa đúng và giảm số hàng

## 1. Vì sao vị trí lọc quyết định cả tốc độ lẫn kết quả?

Khi truy vấn **property graph** bằng **Cypher**, một dòng kết quả có thể được nhân lên qua mỗi lần mở rộng relationship. Ví dụ, một khách hàng có 200 đơn hàng, mỗi đơn có trung bình 8 dòng sản phẩm. Nếu truy vấn mở rộng tất cả các đơn và sản phẩm trước khi chọn những đơn cần thiết, kết quả trung gian có thể lên tới khoảng **1.600 dòng**. Nếu nghiệp vụ chỉ cần 10 đơn đã thanh toán, việc lọc đúng chỗ có thể giảm đáng kể số hàng đi qua những bước tiếp theo.

Nhưng “đưa **WHERE** lên sớm” không phải một quy tắc máy móc. Vị trí lọc còn quyết định câu truy vấn đang trả lời câu hỏi nào:

- Lọc đơn hàng **trước LIMIT**: lấy 10 đơn đã thanh toán mới nhất.
- Lấy 10 đơn mới nhất **trước khi lọc**: trong 10 đơn mới nhất, chỉ giữ những đơn đã thanh toán; kết quả có thể ít hơn 10.
- Lọc bên trong **OPTIONAL MATCH**: vẫn giữ khách hàng dù không có đơn phù hợp.
- Lọc hàng có giá trị **null** sau OPTIONAL MATCH: có thể loại khách hàng khỏi kết quả.

Mục tiêu của bài này là viết truy vấn **đúng ngữ nghĩa** trước, sau đó tổ chức phép lọc, mở rộng graph, tổng hợp và phân trang để **hạn chế số hàng phải xử lý**. Neo4j có bộ tối ưu truy vấn (*query planner*) có thể tự đẩy một số predicate xuống vị trí thực thi phù hợp; vì vậy cần kiểm chứng bằng **EXPLAIN** và **PROFILE**, không kết luận chỉ từ thứ tự các dòng Cypher.

## 2. Ví dụ xuyên suốt: Customer, Order và Product

Giả sử ứng dụng có graph:

~~~text
(c:Customer {customerId, name})
    |
    +--[:PLACED]-->(o:Order {orderId, status, createdAt, totalInCents})
                        |
                        +--[line:HAS_ITEM {quantity}]-->(p:Product {productId, category, active})
~~~

Một khách hàng có thể đặt nhiều đơn; một đơn có thể có nhiều relationship **HAS_ITEM** tới các sản phẩm. Các yêu cầu đọc thường gặp gồm:

1. Liệt kê **20 đơn PAID mới nhất** của một khách hàng.
2. Hiển thị khách hàng kèm **số đơn PAID**, kể cả khách hàng chưa có đơn phù hợp.
3. Chỉ lấy những đơn **chứa ít nhất một sản phẩm** thuộc danh mục cần tìm.
4. Phân trang **theo đơn hàng** nhưng trả thêm danh sách dòng sản phẩm của từng đơn.

Giả định dữ liệu minh họa: **Customer.customerId** và **Order.orderId** là khóa nghiệp vụ duy nhất; **Order.createdAt** có kiểu thời gian nhất quán; một đơn có một relationship PLACED từ khách hàng tương ứng. Nếu dữ liệu thực tế có nhiều relationship PLACED trùng giữa cùng một cặp, cần xử lý vấn đề mô hình hoặc cân nhắc DISTINCT ở đúng vị trí.

Trong các ví dụ có tham số, ứng dụng phải truyền **$customerId**, **$pageSize**, **$category**... theo kiểu phù hợp; **$pageSize** cần được kiểm tra giới hạn trước khi gửi tới Neo4j.

## 3. Hiểu “số hàng” sau mỗi bước MATCH

Xem truy vấn:

~~~cypher
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
MATCH (o)-[line:HAS_ITEM]->(p:Product)
RETURN c.customerId AS customerId,
       o.orderId AS orderId,
       p.productId AS productId,
       line.quantity AS quantity;
~~~

Nếu khách hàng có 200 đơn, mỗi đơn có 8 dòng hàng:

| Bước logic | Số hàng minh họa |
|---|---:|
| Tìm một Customer theo customerId | 1 |
| Mở rộng PLACED đến 200 Order | 200 |
| Mở rộng HAS_ITEM từ mỗi Order | 1.600 |
| RETURN bốn cột | 1.600 |

Con số trên chỉ là minh họa; graph thật có số bậc và điều kiện khác. Mỗi hàng kết quả của MATCH biểu diễn một **tổ hợp biến khớp mẫu**. Một Order được lặp lại ở nhiều hàng nếu có nhiều quan hệ HAS_ITEM.

Nếu API chỉ hiển thị mã và trạng thái đơn hàng, việc mở rộng tới Product hoàn toàn không cần thiết. Viết truy vấn theo hợp đồng dữ liệu:

~~~cypher
MATCH (:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN o.orderId AS orderId,
       o.status AS status
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $pageSize;
~~~

Truy vấn không mở rộng HAS_ITEM nên tránh nhân hàng theo số dòng sản phẩm. Điều quan trọng là xác định rõ **một hàng ứng với một thực thể gì**, rồi chỉ tạo những tổ hợp cần thiết.

## 4. Đặt WHERE cùng mẫu MATCH mà nó ràng buộc

### 4.1. Lọc trực tiếp Customer và Order

~~~cypher
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
  AND o.createdAt >= $fromDate
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt,
       o.totalInCents AS totalInCents;
~~~

Truy vấn biểu đạt ba điều kiện:

- Tìm đúng Customer theo khóa **customerId**.
- Chỉ đi qua relationship **PLACED** để lấy Order của khách hàng đó.
- Giữ những Order có **status = PAID** và **createdAt** từ ngày cần tìm.

Đặt điều kiện gần mẫu MATCH giúp người đọc nhận ra điều kiện đó áp dụng cho **đơn hàng được khớp**, đồng thời giúp trình tối ưu có cơ hội tận dụng predicate ở nơi có lợi.

Có thể viết một dạng tương đương về mặt tập kết quả khi không có ranh giới tổng hợp, phân trang hoặc phép nối tùy chọn:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, o
WHERE c.customerId = $customerId
  AND o.status = 'PAID'
  AND o.createdAt >= $fromDate
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt,
       o.totalInCents AS totalInCents;
~~~

**Không nên khẳng định** dạng thứ hai luôn bắt đầu bằng cách mở rộng toàn bộ graph. Neo4j thường có thể di chuyển predicate an toàn trong kế hoạch thực thi. Dạng đầu diễn đạt điểm xuất phát và phạm vi dễ đọc hơn; muốn biết dạng nào nhanh hơn trên dữ liệu thực, phải xem plan và đo.

### 4.2. Lọc thuộc tính relationship

Nếu cần tìm dòng hàng có số lượng ít nhất 3 và sản phẩm thuộc một danh mục:

~~~cypher
MATCH (o:Order {orderId: $orderId})
      -[line:HAS_ITEM]->
      (p:Product)
WHERE line.quantity >= $minQuantity
  AND p.category = $category
RETURN p.productId AS productId,
       line.quantity AS quantity;
~~~

**line.quantity** là property của relationship **HAS_ITEM**; **p.category** là property của node Product. Cả hai đều là predicate trên mẫu đang khớp. Một phép lọc đặt sai biến có thể làm truy vấn trả dữ liệu không đúng dù vẫn chạy thành công.

### 4.3. Chọn điểm bắt đầu có tính chọn lọc

Hai hình thức sau diễn đạt điều kiện trên Customer:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
RETURN c.name AS name;
~~~

~~~cypher
MATCH (c:Customer)
WHERE c.customerId = $customerId
RETURN c.name AS name;
~~~

Với cùng điều kiện đẳng thức và nhãn, hai cách này thường tương đương về ngữ nghĩa; planner có thể chọn cách tra cứu gần giống nhau. Khi **Customer.customerId** là khóa duy nhất, constraint/index thích hợp giúp Neo4j tìm node mục tiêu mà không phải quét mọi Customer.

Ví dụ constraint triển khai bởi migration schema, **không** chạy trong mỗi request đọc:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

Đặt WHERE vào vị trí dễ hiểu chưa đủ để tối ưu. Tốc độ còn phụ thuộc nhãn, chỉ mục, thống kê, độ chọn lọc, chiều đi graph và số hàng phát sinh sau mỗi Expand.

## 5. OPTIONAL MATCH: vị trí WHERE làm thay đổi tập kết quả

Đây là trường hợp quan trọng nhất khi bàn về **đúng ngữ nghĩa**.

Giả sử cần hiển thị một Customer **dù họ không có đơn PAID**, kèm số đơn PAID nếu có.

### 5.1. Đúng: lọc ngay trong OPTIONAL MATCH

~~~cypher
MATCH (c:Customer {customerId: $customerId})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN c.customerId AS customerId,
       count(o) AS paidOrders;
~~~

**WHERE** gắn với **OPTIONAL MATCH**. Neo4j chỉ coi các đơn PAID là các bản ghi khớp ở phần tùy chọn. Nếu không có đơn PAID, hàng Customer vẫn được giữ, còn biến **o** nhận **null**.

Khi đó, **count(o)** bằng 0 vì nó không đếm giá trị null. Đây là hành vi phù hợp với màn hình thống kê cần hiển thị cả khách hàng chưa có đơn PAID.

### 5.2. Khác nghĩa: lọc sau khi đã đưa kết quả tùy chọn qua WITH

~~~cypher
MATCH (c:Customer {customerId: $customerId})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, o
WHERE o.status = 'PAID'
RETURN c.customerId AS customerId,
       count(o) AS paidOrders;
~~~

Trong câu này, WHERE lọc **các hàng sau OPTIONAL MATCH**. Nếu khách hàng không có đơn, hoặc chỉ có đơn khác trạng thái PAID, biểu thức **o.status = 'PAID'** không đúng với bất kỳ hàng nào. Kết quả **không còn hàng Customer** để trả về.

Bảng so sánh:

| Dữ liệu Customer | WHERE trong OPTIONAL MATCH | WHERE sau WITH |
|---|---|---|
| Có 3 đơn PAID | Customer, paidOrders = 3 | Customer, paidOrders = 3 |
| Có 2 đơn NEW, không có PAID | Customer, paidOrders = 0 | Không có hàng |
| Chưa có đơn nào | Customer, paidOrders = 0 | Không có hàng |

Vì thế, “đẩy WHERE lên trước” không thể được hiểu là tự do đưa điều kiện qua ranh giới **OPTIONAL MATCH**. Phải chọn rõ nghiệp vụ là **lọc đối tượng liên kết tùy chọn** hay **lọc cả hàng cha**.

### 5.3. Phân biệt count(o) và count(*)

~~~cypher
MATCH (c:Customer {customerId: $customerId})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN count(o) AS paidOrders,
       count(*) AS rowsAfterOptional;
~~~

Nếu Customer tồn tại nhưng không có đơn PAID, **count(o) = 0**, còn **count(*) = 1** vì vẫn có một hàng chứa Customer và biến o bằng null. Muốn đếm đối tượng tùy chọn khớp thật sự, thường dùng **count(o)** hoặc **count(DISTINCT o)** theo mô hình dữ liệu.

### 5.4. Khi nào cần loại bỏ Customer không có đơn PAID?

Nếu yêu cầu là “chỉ trả các Customer **có ít nhất một** đơn PAID”, MATCH bắt buộc hoặc điều kiện EXISTS có thể phù hợp hơn:

~~~cypher
MATCH (c:Customer)
WHERE EXISTS {
    MATCH (c)-[:PLACED]->(o:Order)
    WHERE o.status = 'PAID'
}
RETURN c.customerId AS customerId,
       c.name AS name;
~~~

EXISTS kiểm tra **sự tồn tại** và không buộc tạo một hàng kết quả cho mỗi Order khớp. Đây là cách hữu ích khi chỉ cần biết có tồn tại quan hệ phù hợp, thay vì trả tất cả các Order.

## 6. WHERE phải đứng trước hay sau LIMIT?

### 6.1. “20 đơn PAID mới nhất” — lọc trước phân trang

~~~cypher
MATCH (:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt
ORDER BY createdAt DESC, orderId DESC
LIMIT $pageSize;
~~~

Đầu tiên, tập ứng viên được giới hạn về **đơn PAID**; sau đó sắp xếp và chọn tối đa **pageSize** hàng. Nếu khách hàng có đủ đơn PAID, kết quả có thể có đúng số hàng yêu cầu.

### 6.2. “Trong 20 đơn mới nhất, lấy những đơn PAID” — lọc sau phân trang

~~~cypher
MATCH (:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WITH o
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $pageSize
WITH o
WHERE o.status = 'PAID'
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt
ORDER BY createdAt DESC, orderId DESC;
~~~

Truy vấn này lấy tối đa **pageSize** đơn mới nhất **bất kể trạng thái**, sau đó bỏ các đơn không PAID. Nếu trong 20 đơn mới nhất chỉ có 6 đơn PAID, kết quả có 6 hàng, dù vẫn còn các đơn PAID cũ hơn.

Hai câu đều có thể đúng, nhưng trả lời **hai câu hỏi khác nhau**. Chọn theo yêu cầu sản phẩm; không di chuyển WHERE qua LIMIT chỉ với lý do “lọc sớm nhanh hơn”.

### 6.3. Phân trang ổn định cần ORDER BY

Cypher không bảo đảm thứ tự hàng khi thiếu ORDER BY. Nếu nhiều đơn có cùng **createdAt**, dùng thêm khóa phân biệt như **orderId** để có thứ tự xác định:

~~~cypher
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $pageSize
~~~

**LIMIT** khống chế số hàng trả về, nhưng vẫn có thể cần duyệt và sắp xếp nhiều hàng để xác định top N. Nó không bảo đảm chi phí xử lý tương ứng chỉ N bản ghi. Index thích hợp và điểm bắt đầu truy vấn vẫn quan trọng.

## 7. Lọc và LIMIT trước khi mở rộng relationship nhiều nhánh

Một API yêu cầu **20 đơn PAID mới nhất**, mỗi đơn kèm danh sách sản phẩm. Truy vấn sau gây sai đơn vị phân trang:

~~~cypher
MATCH (:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
MATCH (o)-[line:HAS_ITEM]->(p:Product)
WHERE o.status = 'PAID'
RETURN o.orderId AS orderId,
       p.productId AS productId,
       line.quantity AS quantity
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $pageSize;
~~~

Vì một Order có nhiều dòng sản phẩm, LIMIT giới hạn **số hàng order–item**. Ví dụ đơn mới nhất có 15 dòng hàng thì có thể chiếm 15/20 hàng; đơn không có item còn bị bỏ hoàn toàn bởi MATCH bắt buộc. Truy vấn này không đáp ứng “20 đơn, mỗi đơn có toàn bộ item”.

### 7.1. Cách viết giữ đúng đơn vị trang

~~~cypher
MATCH (:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
WITH DISTINCT o
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $pageSize

OPTIONAL MATCH (o)-[line:HAS_ITEM]->(p:Product)
WITH o,
     collect(
         CASE
             WHEN p IS NULL THEN null
             ELSE {
                 productId: p.productId,
                 category: p.category,
                 quantity: line.quantity
             }
         END
     ) AS items
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt,
       o.status AS status,
       items
ORDER BY createdAt DESC, orderId DESC;
~~~

Cách tổ chức:

1. MATCH Customer và Order, chỉ giữ trạng thái PAID.
2. **WITH DISTINCT o** chọn một hàng theo Order trước khi phân trang. DISTINCT có ý nghĩa nếu mô hình hoặc mẫu đường đi có thể đưa cùng Order vào nhiều hàng; với một PLACED duy nhất trên mỗi Order, có thể không cần nó.
3. **ORDER BY + LIMIT** chọn trang theo **Order**.
4. **OPTIONAL MATCH** mở rộng danh sách item sau khi đã chọn trang.
5. **collect(...)** gom nhiều hàng item về một danh sách cho mỗi Order. **collect(null)** không thêm phần tử null, nên Order không có item nhận danh sách rỗng.
6. ORDER BY cuối cùng phục hồi thứ tự đầu ra; thứ tự từ một WITH trước đó không nên được ngầm coi là thứ tự mọi hàng cuối cùng sau các bước mở rộng và tổng hợp.

Mẫu này vẫn phải duyệt những Order cần thiết để xác định top N; giá trị lớn nhất của nó là tránh mở rộng item trên **mọi** Order trước khi quyết định lấy trang nào.

### 7.2. Không đưa điều kiện trên Product vào sai chỗ

Nếu yêu cầu là “20 đơn PAID mới nhất **có chứa** Product thuộc category X”, không được lấy 20 đơn trước rồi mới lọc sản phẩm nếu mong muốn đủ 20 đơn **thỏa điều kiện**. Trước phân trang phải kiểm tra sự tồn tại của Product phù hợp:

~~~cypher
MATCH (:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
  AND EXISTS {
      MATCH (o)-[:HAS_ITEM]->(p:Product)
      WHERE p.category = $category
  }
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt
ORDER BY createdAt DESC, orderId DESC
LIMIT $pageSize;
~~~

EXISTS phù hợp vì API chỉ cần biết đơn có **ít nhất một** sản phẩm thuộc danh mục. Nếu dùng MATCH mở rộng Product, cùng một đơn có thể tạo nhiều hàng và làm sai trang nếu không gom/deduplicate trước.

## 8. WHERE sau WITH và phép tổng hợp: khác với lọc hàng gốc

Một yêu cầu: “Tìm Customer có **ít nhất 5 đơn PAID**”.

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
WITH c, count(DISTINCT o) AS paidOrders
WHERE paidOrders >= $minPaidOrders
RETURN c.customerId AS customerId,
       paidOrders
ORDER BY paidOrders DESC;
~~~

Có hai loại WHERE với vai trò khác nhau:

- **WHERE o.status = 'PAID'** trước WITH: loại các hàng Order không thỏa điều kiện **trước khi đếm**.
- **WHERE paidOrders >= $minPaidOrders** sau WITH: loại các **nhóm Customer** có kết quả tổng hợp không đạt yêu cầu.

Không thể đơn giản đẩy điều kiện **paidOrders >= ...** lên trước khi biến **paidOrders** được tính. Neo4j không dùng cú pháp HAVING của SQL; WHERE trên kết quả aggregation thường được viết sau WITH.

### 8.1. Lọc item trước SUM làm thay đổi đại lượng được cộng

Giả sử cần tính **tổng quantity của mọi dòng hàng** cho mỗi Order, nhưng chỉ trả Order có tổng ít nhất 10:

~~~cypher
MATCH (o:Order {orderId: $orderId})-[line:HAS_ITEM]->(:Product)
WITH o, sum(line.quantity) AS totalQuantity
WHERE totalQuantity >= 10
RETURN o.orderId AS orderId,
       totalQuantity;
~~~

Nếu đưa điều kiện **line.quantity >= 10** vào MATCH trước SUM, bạn đang tính tổng **chỉ những dòng hàng có quantity >= 10**, và bỏ những dòng hàng nhỏ. Kết quả không còn tương đương: một đơn có 6 + 4 sản phẩm sẽ có tổng 10, nhưng không có dòng nào đạt ngưỡng 10.

Đây là khác biệt giữa **điều kiện trên từng hàng** và **điều kiện trên kết quả tổng hợp**.

### 8.2. DISTINCT có làm giảm số hàng hợp lý không?

~~~cypher
MATCH (o:Order)-[:HAS_ITEM]->(p:Product)
RETURN DISTINCT o.orderId AS orderId,
                p.category AS category;
~~~

DISTINCT ở đây khử trùng lặp **cặp (orderId, category)**, không biến toàn bộ kết quả thành **một hàng mỗi Order**. Nếu API cần số loại sản phẩm theo Order, hãy tổng hợp có chủ đích:

~~~cypher
MATCH (o:Order)-[:HAS_ITEM]->(p:Product)
WITH o, count(DISTINCT p.category) AS categoryCount
RETURN o.orderId AS orderId,
       categoryCount;
~~~

Không lạm dụng DISTINCT như cách chữa mọi vấn đề số hàng. Trước tiên xác định khóa nhóm và trường nào thực sự cần giữ.

## 9. Lọc qua EXISTS để tránh nhân hàng không cần thiết

Khi chỉ kiểm tra **có hay không** một quan hệ, phép mở rộng thường tạo thêm hàng mà ứng dụng không sử dụng.

### 9.1. Cách có thể làm nhân hàng

~~~cypher
MATCH (o:Order)-[:HAS_ITEM]->(p:Product)
WHERE p.category = $category
RETURN o.orderId AS orderId;
~~~

Một Order chứa ba Product thuộc cùng category có thể xuất hiện ba lần. Muốn loại trùng, bạn phải dùng DISTINCT hoặc một phép tổng hợp khác.

### 9.2. Diễn đạt trực tiếp sự tồn tại

~~~cypher
MATCH (o:Order)
WHERE EXISTS {
    MATCH (o)-[:HAS_ITEM]->(p:Product)
    WHERE p.category = $category
}
RETURN o.orderId AS orderId;
~~~

Đây là câu hỏi **“Order có ít nhất một Product thuộc category không?”**. EXISTS không cần xuất nhiều hàng ứng với nhiều Product phù hợp. Planner có thể chọn kế hoạch thích hợp với kiểm tra tồn tại.

Không mặc định EXISTS luôn nhanh hơn DISTINCT. Độ chọn lọc của Order, Product, số relationship và index có thể làm thay đổi kế hoạch tối ưu. Chọn EXISTS trước vì **đúng mục đích**, sau đó kiểm chứng hiệu năng.

## 10. NULL và logic ba giá trị trong WHERE

Trong Cypher, biểu thức so sánh với giá trị **null** thường cho kết quả null; WHERE chỉ giữ các hàng mà biểu thức đánh giá thành **true**.

~~~cypher
MATCH (o:Order)
WHERE o.status <> 'CANCELLED'
RETURN o.orderId AS orderId;
~~~

Truy vấn này **không** trả các Order thiếu property status, vì biểu thức **null <> 'CANCELLED'** không phải true. Nếu nghiệp vụ muốn giữ cả những đơn chưa có status:

~~~cypher
MATCH (o:Order)
WHERE o.status IS NULL
   OR o.status <> 'CANCELLED'
RETURN o.orderId AS orderId;
~~~

Tương tự, khi OPTIONAL MATCH tạo biến null, predicate trên biến đó có thể xóa hàng ở các bước lọc sau. Trước khi di chuyển WHERE, luôn kiểm tra những trường hợp **biến không tồn tại, property vắng mặt hoặc không có relationship khớp**.

**Không nhầm tính đúng với việc ép dùng coalesce.** Chuyển null thành một trạng thái mặc định có thể che khuất lỗi dữ liệu; quy tắc xử lý null phải xuất phát từ hợp đồng nghiệp vụ.

## 11. Không làm mất biến cần dùng khi WITH cắt phạm vi

WITH vừa là phép chiếu chọn biến, vừa cho phép lọc, phân trang, tổng hợp hoặc chia pipeline truy vấn. Các biến không được truyền qua WITH sẽ không còn trong phạm vi tiếp theo.

Ví dụ hợp lệ:

~~~cypher
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
WITH c.customerId AS customerId, o
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $pageSize
RETURN customerId,
       o.orderId AS orderId,
       o.createdAt AS createdAt;
~~~

Nếu WITH chỉ giữ **o**, phần sau không còn quyền tham chiếu biến **c** đã khai báo trước đó. Khi di chuyển điều kiện tới sau WITH, phải bảo đảm biến dùng trong điều kiện còn được truyền tiếp. Đây là vấn đề **scope của Cypher**, độc lập với hiệu năng.

Đồng thời cần phân biệt:

- **WITH o WHERE o.status = ...**: lọc từng hàng o.
- **WITH c, count(o) AS n WHERE n >= 5**: lọc nhóm sau aggregation.
- **WITH o ORDER BY ... LIMIT 20**: xác định một tập con có thứ tự trước bước tiếp theo.

Các ranh giới này có thể thay đổi **ngữ nghĩa** nếu di chuyển điều kiện qua chúng.

## 12. Tránh Cartesian product khi muốn lọc theo quan hệ

Truy vấn dưới đây không biểu diễn đúng “đơn hàng của một Customer”:

~~~cypher
MATCH (c:Customer), (o:Order)
WHERE c.customerId = $customerId
  AND o.status = 'PAID'
RETURN c.customerId AS customerId,
       o.orderId AS orderId;
~~~

Hai mẫu **(c:Customer)** và **(o:Order)** chưa được nối bằng relationship; chúng có thể kết hợp mỗi Customer khớp với mọi Order PAID trong database. Dù thêm WHERE, kết quả vẫn có thể gồm các đơn **không thuộc** Customer đó.

Khi nghiệp vụ cần quan hệ sở hữu:

~~~cypher
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN c.customerId AS customerId,
       o.orderId AS orderId;
~~~

Cypher cần thể hiện đúng **mối liên hệ dữ liệu**, không chỉ lọc cho số lượng hàng ít đi. Một Cartesian product có chủ đích đôi khi hợp lệ, nhưng phải xuất phát từ yêu cầu tạo tất cả tổ hợp, không phải sơ suất bỏ mẫu relationship.

## 13. Planner có thể đẩy predicate: đọc plan thay vì đoán

Neo4j dùng query planner để chọn thứ tự truy cập node, sử dụng index và thực hiện Filter/Expand/Sort/Aggregation. **Thứ tự văn bản** không nhất thiết chính là thứ tự toán tử vật lý.

### 13.1. EXPLAIN xem kế hoạch, không chạy truy vấn

~~~cypher
EXPLAIN
MATCH (:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt
ORDER BY createdAt DESC, orderId DESC
LIMIT $pageSize;
~~~

Trong plan, cần quan sát:

- **NodeIndexSeek / NodeUniqueIndexSeek** nếu truy vấn tận dụng index/constraint tương ứng.
- **NodeByLabelScan** khi phải quét một tập node theo nhãn.
- **Filter** nằm tại đâu so với bước **Expand**; predicate có thể được kết hợp vào một operator khác.
- **Estimated Rows**, các bước **Sort/Top**, **Aggregation** và số lượng hàng dự kiến.
- Thứ tự kế hoạch chọn truy cập điểm bắt đầu và mở rộng relationship.

Tên toán tử cụ thể khác nhau giữa các phiên bản Neo4j và runtime; không nên dựa vào một tên operator cố định để kết luận.

### 13.2. PROFILE đo khi thực thi

~~~cypher
PROFILE
MATCH (:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt
ORDER BY createdAt DESC, orderId DESC
LIMIT $pageSize;
~~~

PROFILE **thực thi** truy vấn rồi trả số liệu thực tế, có thể bao gồm **Rows**, **DB Hits**, thống kê bộ nhớ và operator đã chạy. Truy vấn trên chỉ đọc; nếu PROFILE một truy vấn **CREATE/SET/DELETE**, thao tác ghi cũng được thực thi, nên không dùng PROFILE như một cách xem thử an toàn đối với dữ liệu quan trọng.

Để so sánh hai cách viết:

1. Dùng **cùng database, dữ liệu, tham số và giới hạn trang**.
2. Xác nhận hai truy vấn trả kết quả **tương đương theo yêu cầu nghiệp vụ** trước khi so hiệu năng.
3. So **Rows** sau mỗi toán tử Expand/Filter, DB Hits và chi phí Sort/Aggregation.
4. Đo thêm payload truyền về, thời gian đọc qua Java Driver và thời gian dựng DTO/JSON nếu API có nhiều dữ liệu.
5. Lặp phép đo hợp lý trên dữ liệu đại diện; bộ đệm nóng/lạnh và tải đồng thời có thể làm thời gian thay đổi.

Số cột trả về ít hơn không nhất thiết làm server nhanh hơn nếu truy vấn vẫn quét nhiều node và sort nhiều hàng. Ngược lại, chọn đúng trang trước khi mở rộng các quan hệ con có thể giảm đáng kể số hàng trung gian.

### 13.3. Chỉ mục và ràng buộc hỗ trợ chọn lọc

Đây là các ví dụ schema có thể cân nhắc cho truy vấn trên, tùy mô hình:

~~~cypher
CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;
~~~

~~~cypher
CREATE INDEX order_status_created_at IF NOT EXISTS
FOR (o:Order)
ON (o.status, o.createdAt);
~~~

Không nên tạo index cho mọi property có mặt trong WHERE. Index có chi phí lưu trữ, ghi và bảo trì; mức hữu ích tùy độ chọn lọc của property và cách truy vấn bắt đầu từ Customer rồi mở rộng Order. Một index trên Order có thể ít giúp ích cho một kế hoạch vốn đã tìm được rất ít Order bằng relationship từ Customer.

Việc xem query plan là cách đánh giá thực tế index nào được dùng. Cần tạo schema qua quy trình migration thích hợp và kiểm tra dữ liệu trước khi thêm uniqueness constraint.

## 14. Gắn truy vấn hẹp vào Java Driver

API chỉ cần danh sách **OrderSummary**, nên Cypher trả các cột đúng với DTO; tránh trả cả node Order cùng các relationship rồi lọc ở Java.

~~~java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class OrderReadService {
    public record OrderSummary(
        String orderId,
        String status,
        String createdAt
    ) {}

    private final Driver driver;

    public OrderReadService(Driver driver) {
        this.driver = driver;
    }

    public List<OrderSummary> recentPaidOrders(
            String customerId, int requestedPageSize) {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("customerId is required");
        }
        int pageSize = Math.max(1, Math.min(requestedPageSize, 100));

        String cypher = """
            MATCH (:Customer {customerId: $customerId})
                  -[:PLACED]->(o:Order)
            WHERE o.status = 'PAID'
            RETURN o.orderId AS orderId,
                   o.status AS status,
                   toString(o.createdAt) AS createdAt
            ORDER BY o.createdAt DESC, o.orderId DESC
            LIMIT $pageSize
            """;

        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            return session.executeRead(tx ->
                tx.run(cypher, Map.of(
                    "customerId", customerId,
                    "pageSize", pageSize
                )).list(row -> new OrderSummary(
                    row.get("orderId").asString(),
                    row.get("status").asString(),
                    row.get("createdAt").asString()
                ))
            );
        }
    }
}
~~~

Đoạn ví dụ giả định **Order.createdAt** có giá trị hợp lệ và **Order.orderId, Order.status** không null. Nếu dữ liệu cho phép thiếu property, cần khai báo DTO và quy tắc mapping tương ứng. **Driver** được tái sử dụng trong ứng dụng; mỗi **Session** có vòng đời ngắn. **executeRead** dùng managed transaction cho thao tác đọc và có cơ chế retry cho những lỗi transient được driver nhận diện.

Với **Spring Data Neo4j**, ý tưởng tương tự: định nghĩa DTO/projection cho endpoint, dùng Cypher chỉ trả các trường cần thiết và kiểm tra mapping. Không mặc định phải nạp một aggregate entity cùng các quan hệ chỉ để trả danh sách tóm tắt.

Tối ưu vị trí WHERE và số hàng tại Neo4j giúp giảm đầu việc của Driver, nhưng vẫn cần đo thời gian truy vấn, lượng record materialize và kích thước JSON ở phía ứng dụng.

## 15. Thực hành: nhận diện đúng ngữ nghĩa và số hàng

### Bài 1 — Lọc trạng thái trước LIMIT

Yêu cầu: “Lấy tối đa 10 đơn PAID mới nhất của Customer X”. Chọn giữa hai cách:

~~~cypher
// Cách A
MATCH (:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN o.orderId AS orderId
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT 10;
~~~

~~~cypher
// Cách B
MATCH (:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WITH o ORDER BY o.createdAt DESC, o.orderId DESC LIMIT 10
WITH o WHERE o.status = 'PAID'
RETURN o.orderId AS orderId;
~~~

**Đáp án:** Cách A đúng yêu cầu vì lọc PAID trước khi chọn top 10. Cách B trả những đơn PAID nằm trong 10 đơn mới nhất bất kể trạng thái; kết quả có thể ít hơn 10.

### Bài 2 — Giữ khách hàng dù không có đơn

Yêu cầu: “Trả Customer và số đơn CANCELLED, kể cả khi bằng 0”. Câu truy vấn:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, o
WHERE o.status = 'CANCELLED'
RETURN c.customerId AS customerId, count(o) AS cancelledOrders;
~~~

**Vấn đề:** WHERE ở sau WITH lọc mất hàng Customer khi không có đơn CANCELLED.

**Sửa:**

~~~cypher
MATCH (c:Customer {customerId: $customerId})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WHERE o.status = 'CANCELLED'
RETURN c.customerId AS customerId, count(o) AS cancelledOrders;
~~~

### Bài 3 — Phân trang Order hay Order–Product?

Một Order có 12 item. Truy vấn MATCH Order, MATCH HAS_ITEM rồi LIMIT 10 cuối cùng có thể trả đủ 10 Order không?

**Đáp án:** Không. Nó giới hạn 10 **hàng Order–Item**, có thể chỉ chứa một phần của cùng một Order. Phải phân trang trên Order trước khi mở rộng HAS_ITEM và tổng hợp item nếu hợp đồng cần một hàng theo Order.

### Bài 4 — WHERE với kết quả aggregation

Yêu cầu: “Chỉ lấy những Order có tổng quantity từ các dòng sản phẩm ít nhất 20”. Lọc **line.quantity >= 20** trước SUM có đúng không?

**Đáp án:** Không. Điều đó bỏ các dòng nhỏ có đóng góp vào tổng. Cần tính **sum(line.quantity)** theo Order, rồi dùng **WHERE** trên biến tổng đã tính trong WITH.

### Bài 5 — Hỏi về sự tồn tại

Yêu cầu: “Chỉ lấy mã Order có ít nhất một Product với category = 'BOOK'”. Nếu MATCH HAS_ITEM trực tiếp, một Order có 5 sách xuất hiện mấy lần?

**Đáp án:** Có thể 5 lần, một hàng cho mỗi Product khớp. Có thể dùng **WHERE EXISTS { MATCH ... }** để diễn đạt việc tồn tại và tránh tạo 5 hàng chỉ để trả cùng một Order.

## 16. Checklist tư duy khi viết truy vấn

Trước khi quyết định đẩy WHERE hoặc thêm WITH, hãy tự trả lời:

1. **Một hàng đầu ra đại diện cho gì?** Customer, Order, một cặp Order–Product hay một nhóm sau aggregation?
2. **Lọc đối tượng nào?** Node gốc, relationship, node hàng xóm hay cả hàng kết quả?
3. **Có OPTIONAL MATCH không?** Nếu có, phải giữ hàng cha khi không có hàng con phù hợp hay phải loại luôn hàng cha?
4. **Có giới hạn phân trang không?** Điều kiện được áp dụng **trước** hay **sau** việc chọn N bản ghi, theo đúng yêu cầu nghiệp vụ?
5. **Có aggregation không?** Điều kiện áp dụng cho **hàng gốc** hay **số liệu đã tổng hợp**?
6. **Có nguy cơ nhân hàng không?** Một node có nhiều relationship có làm sai số lượng, phép đếm hoặc thứ tự trang không?
7. **Có đường đi thực sự giữa các nhãn không?** Tránh kết hợp Cartesian do quên relationship.
8. **Planner đang làm gì?** Dùng EXPLAIN/PROFILE để xác nhận index, rows, expand, filter và sort trước khi kết luận về hiệu năng.

## 17. Ghi nhớ

**Đẩy điều kiện lọc đến vị trí có ngữ nghĩa đúng** nghĩa là giới hạn dữ liệu ngay khi có thể **mà vẫn giữ nguyên câu hỏi nghiệp vụ**. Lọc sớm trước mở rộng relationship có thể giảm số hàng; lọc trước LIMIT có thể giúp chọn đủ số bản ghi phù hợp; lọc trong OPTIONAL MATCH giữ hàng cha khi không có liên kết; lọc sau WITH cho phép làm việc với kết quả tổng hợp. Những vị trí này **không tự do hoán đổi** cho nhau.

Khi tối ưu Cypher trong Neo4j, hãy bắt đầu từ **đúng mẫu graph, đúng hàng kết quả và đúng quy tắc null/phân trang**, rồi đo bằng **EXPLAIN**, **PROFILE** và chỉ số phía Java Driver hoặc Spring Data Neo4j. Một truy vấn tốt vừa trả đúng dữ liệu ứng dụng cần, vừa hạn chế số hàng trung gian và chi phí mở rộng đồ thị.

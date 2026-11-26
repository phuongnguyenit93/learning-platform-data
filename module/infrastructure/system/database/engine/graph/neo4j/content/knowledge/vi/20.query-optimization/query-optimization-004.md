# Tránh tích Descartes và tổng hợp trên dữ liệu đã bị nhân hàng

Khi viết Cypher trong Neo4j, một câu truy vấn có thể **trả đúng các loại node và relationship cần tìm nhưng sai số liệu tổng hợp**. Nguyên nhân thường gặp là số hàng trung gian tăng ngoài dự kiến: hai mẫu độc lập tạo **tích Descartes** (*Cartesian product*), hoặc hai nhánh quan hệ cùng nối vào một thực thể làm các hàng bị **nhân lên** (*row multiplication / fan-out*). Nếu sau đó dùng `count()`, `sum()` hay `collect()` mà không xét lại đơn vị dữ liệu, báo cáo có thể đếm và cộng tiền nhiều lần.

Bài thuộc chương **Tối ưu truy vấn** của module **DATABASE_ENGINE_GRAPH_NEO4J**. Trong bối cảnh sử dụng Neo4j để mô hình hóa property graph và truy vấn các node, relationship, đường đi bằng Cypher, bài này nối kết **tính đúng ngữ nghĩa** với **hiệu năng**: nhận diện số hàng bị nhân, chọn cách tách các phép tổng hợp, kiểm tra bằng `EXPLAIN` / `PROFILE`, và áp dụng trong Java Driver hoặc Spring Data Neo4j.

## 1. Trước hết, phân biệt “hàng” với “thực thể”

Mỗi `MATCH` trong Cypher có thể tạo **nhiều hàng kết quả**, dù một biến node xuất hiện lặp đi lặp lại giữa các hàng. Một hàng là một tổ hợp các giá trị biến đang được xét, không đồng nghĩa với một node/relationship duy nhất.

Ví dụ một khách hàng có hai đơn hàng và ba phiếu hỗ trợ:

```text
                         (Order O1, amount=100)
                       /
(Customer C1) --PLACED
                       \
                         (Order O2, amount=100)

(Customer C1) --OPENED--> (Ticket T1)
              --OPENED--> (Ticket T2)
              --OPENED--> (Ticket T3)
```

Giả sử mục tiêu là trả về:

| Khách hàng | Số đơn hàng | Tổng tiền đơn hàng | Số phiếu hỗ trợ |
| --- | ---: | ---: | ---: |
| C1 | 2 | 200 | 3 |

Một truy vấn ghép cùng lúc hai nhánh đơn hàng và hỗ trợ có thể tạo **2 × 3 = 6 hàng**, từ đó khiến `count(o)` thành 6 và `sum(o.amount)` thành 600.

**Nguyên tắc:** trước mỗi phép tổng hợp, phải trả lời rõ **“một hàng hiện tại đại diện cho cái gì?”**. Là một khách hàng, một đơn hàng, một quan hệ, hay một tổ hợp giữa đơn hàng và phiếu hỗ trợ?

## 2. Tích Descartes xuất hiện như thế nào?

### 2.1. Hai mẫu không có biến chung

Trong Cypher, dấu phẩy giữa các mẫu của `MATCH` không tự tạo quan hệ giữa chúng:

```cypher
MATCH (o:DemoOrder), (t:DemoTicket)
RETURN o.orderId AS orderId, t.ticketId AS ticketId;
```

Nếu toàn bộ database có `m` node `:DemoOrder` và `n` node `:DemoTicket`, số hàng tối đa từ hai mẫu độc lập là:

\[
\text{Số hàng} = m \times n
\]

Ví dụ có 2 đơn và 3 phiếu thì nhận 6 tổ hợp:

| orderId | ticketId |
| --- | --- |
| O1 | T1 |
| O1 | T2 |
| O1 | T3 |
| O2 | T1 |
| O2 | T2 |
| O2 | T3 |

Nếu có 100.000 đơn và 50.000 phiếu, phép ghép không có điều kiện sẽ tạo cơ sở cho **5 tỷ tổ hợp**. Truy vấn có thể tốn rất nhiều CPU, RAM, thời gian hoặc bị giới hạn tài nguyên trước khi người dùng nhận được kết quả.

Không phải mọi tích Descartes đều là lỗi. Một màn hình lập **tất cả cặp ứng viên** có thể cần tích Descartes có chủ đích. Vấn đề nằm ở việc tạo tổ hợp ngoài mục tiêu và không giới hạn kích thước đầu vào.

### 2.2. Ghép hai thực thể độc lập để tạo quan hệ

Có những tình huống hai mẫu độc lập được dùng để tìm **hai đầu mút** của một quan hệ:

```cypher
MATCH (from:Person {personId: $fromId})
MATCH (to:Person {personId: $toId})
MERGE (from)-[:KNOWS]->(to);
```

Khi `personId` có **uniqueness constraint**, mỗi phép tìm đúng tối đa một node: ghép `1 × 1` không đáng ngại. Nếu bỏ điều kiện định danh hoặc định danh không duy nhất, truy vấn có nguy cơ tạo quan hệ cho **mọi tổ hợp** giữa hai tập node.

Vì vậy không thể kết luận “thấy `CartesianProduct` là truy vấn chắc chắn sai”. Cần xem **số hàng hai phía**, mục tiêu của phép ghép và ràng buộc duy nhất của các thực thể.

## 3. Nhân hàng dù các mẫu có chung node

Đây là lỗi khó thấy hơn: tất cả phần của truy vấn đều đi qua **cùng một khách hàng**, nhưng mỗi nhánh có nhiều kết quả.

```cypher
MATCH (c:DemoCustomer {customerId: 'C1'})
MATCH (c)-[:PLACED]->(o:DemoOrder)
MATCH (c)-[:OPENED]->(t:DemoTicket)
RETURN c.customerId, o.orderId, t.ticketId;
```

Vì `c` có 2 đơn hàng và 3 phiếu hỗ trợ, các hàng của một khách hàng chứa mọi kết hợp giữa `o` và `t`. Đây là **phép nhân số hàng theo nhánh quan hệ**, dù không phải lúc nào kế hoạch thực thi cũng hiển thị operator `CartesianProduct`.

Với nhiều khách hàng, số hàng trung gian thường xấp xỉ:

\[
\sum_{c \in \text{Customers}} O_c \times T_c
\]

Trong đó `O_c` là số đơn, `T_c` là số phiếu liên quan đến khách hàng `c`, với trường hợp các nhánh đều có kết quả. Với `OPTIONAL MATCH`, mỗi nhánh không có kết quả vẫn có thể tạo một dòng chứa biến `null`; số hàng cần xét theo cách kết hợp của các mẫu tùy chọn.

Phân biệt:

| Tình huống | Ví dụ | Nguy cơ |
| --- | --- | --- |
| **Tích Descartes độc lập** | `MATCH (a:Author), (p:Product)` | Ghép mọi tác giả với mọi sản phẩm |
| **Nhân hàng theo nhánh** | `MATCH (c)-[:PLACED]->(o) MATCH (c)-[:OPENED]->(t)` | Mỗi đơn lặp theo số phiếu và ngược lại |
| **Nhân hàng do nhiều đường đi** | `MATCH p=(a)-[:KNOWS*1..3]->(b)` | Cùng đích có thể xuất hiện qua nhiều path |
| **Nhân hàng qua `UNWIND`** | `UNWIND a AS x UNWIND b AS y` | Hai danh sách tạo tổ hợp nhiều hàng |
| **Nhân hàng vì quan hệ song song** | Hai relationship khác nhau cùng nối tới một node | `count(node)` có thể lớn hơn số node phân biệt |

Ở mọi trường hợp, tác hại đến `sum()` xuất hiện khi **một giá trị nghiệp vụ bị lặp trên các hàng trung gian**.

## 4. Dựng dữ liệu mẫu để quan sát lỗi

Chạy ví dụ sau **một lần trong database thực hành riêng**. Các label `:DemoCustomer`, `:DemoOrder` và `:DemoTicket` giúp tránh nhầm với đối tượng của hệ thống nghiệp vụ thực tế:

```cypher
CREATE
  (c:DemoCustomer {customerId: 'C1'}),
  (o1:DemoOrder {orderId: 'O1', amount: 100}),
  (o2:DemoOrder {orderId: 'O2', amount: 100}),
  (t1:DemoTicket {ticketId: 'T1'}),
  (t2:DemoTicket {ticketId: 'T2'}),
  (t3:DemoTicket {ticketId: 'T3'}),
  (c)-[:PLACED]->(o1),
  (c)-[:PLACED]->(o2),
  (c)-[:OPENED]->(t1),
  (c)-[:OPENED]->(t2),
  (c)-[:OPENED]->(t3);
```

Hai đơn hàng **cố tình có cùng giá trị tiền** `100`. Chi tiết này rất quan trọng: nó giúp phát hiện lỗi khi cố dùng `sum(DISTINCT o.amount)` để chữa phép tổng hợp bị lặp.

Đầu tiên, quan sát số hàng thực tế:

```cypher
MATCH (c:DemoCustomer {customerId: 'C1'})
MATCH (c)-[:PLACED]->(o:DemoOrder)
MATCH (c)-[:OPENED]->(t:DemoTicket)
RETURN c.customerId AS customer,
       o.orderId AS orderId,
       o.amount AS amount,
       t.ticketId AS ticketId
ORDER BY orderId, ticketId;
```

Kết quả có 6 dòng; giá trị `amount=100` xuất hiện **6 lần**. Việc nhân hàng xảy ra trước `RETURN`, vì vậy cùng một node `o1` được sử dụng trong nhiều dòng.

### 4.1. Truy vấn tổng hợp sai

```cypher
MATCH (c:DemoCustomer {customerId: 'C1'})
OPTIONAL MATCH (c)-[:PLACED]->(o:DemoOrder)
OPTIONAL MATCH (c)-[:OPENED]->(t:DemoTicket)
RETURN c.customerId AS customer,
       count(o) AS orderCount,
       sum(o.amount) AS totalAmount,
       count(t) AS ticketCount;
```

Kết quả trên dữ liệu mẫu:

| customer | orderCount | totalAmount | ticketCount |
| --- | ---: | ---: | ---: |
| C1 | 6 | 600 | 6 |

Cả ba phép tổng hợp đều tính trên **6 hàng ghép**. Trong mỗi dòng, cùng một đơn hoặc phiếu vẫn là node cũ nhưng xuất hiện lặp với các biến ở nhánh khác.

### 4.2. Vì sao `DISTINCT` không luôn cứu được phép `sum`?

Người viết truy vấn có thể thử:

```cypher
MATCH (c:DemoCustomer {customerId: 'C1'})
OPTIONAL MATCH (c)-[:PLACED]->(o:DemoOrder)
OPTIONAL MATCH (c)-[:OPENED]->(t:DemoTicket)
RETURN count(DISTINCT o) AS orderCount,
       sum(DISTINCT o.amount) AS totalAmount,
       count(DISTINCT t) AS ticketCount;
```

Kết quả:

| orderCount | totalAmount | ticketCount |
| ---: | ---: | ---: |
| 2 | 100 | 3 |

`count(DISTINCT o)` và `count(DISTINCT t)` đếm **node duy nhất**, nên ra 2 và 3. Nhưng `sum(DISTINCT o.amount)` chỉ cộng **các giá trị tiền phân biệt**, nên hai đơn cùng `100` bị gộp thành **một giá trị 100**. Tổng đúng phải là `100 + 100 = 200`.

**Đơn vị cần khử trùng là đơn hàng, không phải số tiền.** Điều này áp dụng tương tự với `avg(DISTINCT price)`, `collect(DISTINCT property)` hoặc bất kỳ phép tổng hợp nào dùng giá trị thuộc tính làm khóa phân biệt trong khi nghiệp vụ tính theo thực thể.

## 5. Cách 1: tổng hợp từng nhánh trước khi nối nhánh tiếp theo

Một giải pháp thuần Cypher là kết thúc nhánh đơn hàng bằng `WITH`, trả mỗi khách hàng về **một dòng** rồi mới xử lý nhánh phiếu hỗ trợ.

```cypher
MATCH (c:DemoCustomer {customerId: 'C1'})
OPTIONAL MATCH (c)-[:PLACED]->(o:DemoOrder)
WITH DISTINCT c, o
WITH c,
     count(o) AS orderCount,
     sum(o.amount) AS totalAmount
OPTIONAL MATCH (c)-[:OPENED]->(t:DemoTicket)
RETURN c.customerId AS customer,
       orderCount,
       totalAmount,
       count(DISTINCT t) AS ticketCount;
```

Kết quả đúng trên dữ liệu mẫu:

| customer | orderCount | totalAmount | ticketCount |
| --- | ---: | ---: | ---: |
| C1 | 2 | 200 | 3 |

Phân tích theo từng bước:

1. `MATCH (c...)` chọn khách hàng gốc.
2. `OPTIONAL MATCH` lấy đơn hàng; nếu không có đơn thì biến `o` bằng `null`.
3. `WITH DISTINCT c, o` bảo đảm mỗi cặp **khách hàng–đơn hàng** chỉ còn một dòng. Bước này đặc biệt hữu ích nếu cùng một đơn có thể được tới qua nhiều quan hệ hoặc nhiều đường đi nhưng nghiệp vụ chỉ muốn tính đơn một lần.
4. `WITH c, count(o), sum(o.amount)` tạo đúng **một hàng tổng hợp trên mỗi khách hàng**. Không giữ biến `o` trong các bước tiếp theo.
5. `OPTIONAL MATCH` nhánh phiếu hỗ trợ chỉ nhân các **giá trị tổng hợp đã cố định**; `count(DISTINCT t)` đếm phiếu duy nhất. Không cộng `totalAmount` thêm lần nữa.

**Cảnh báo:** nếu đưa `o` vào cùng `WITH` đang tổng hợp theo khách hàng, ví dụ `WITH c, o, sum(o.amount) AS total`, thì `o` trở thành **khóa nhóm**. Kết quả lại có nhiều hàng cho cùng khách hàng; số hàng không được thu về một dòng.

### Dùng khóa nhóm đúng cách

```cypher
MATCH (c:DemoCustomer)-[:PLACED]->(o:DemoOrder)
RETURN c.customerId AS customer,
       sum(o.amount) AS totalAmount;
```

Ở đây `c.customerId` là khóa nhóm. Nếu dữ liệu có hai node khách hàng khác nhau nhưng cùng `customerId`, chúng bị gộp vào một dòng: điều đó chỉ đúng nếu định danh phải duy nhất về mặt nghiệp vụ. Với khóa phân nhóm là biến node `c` hoặc ID duy nhất đã được ràng buộc, ý nghĩa trở nên rõ hơn.

## 6. Cách 2: dùng subquery để cách ly các phép tổng hợp

Khi có nhiều nhánh dữ liệu, việc xếp nhiều `WITH` nối tiếp có thể khó đọc và dễ vô tình giữ lại biến làm tăng số hàng. Subquery `CALL { ... }` cho phép **mỗi nhánh tính riêng** rồi trả kết quả gọn về dòng khách hàng gốc.

Với Neo4j 5.23 trở lên, nên dùng cú pháp nhập biến `CALL (c) { ... }`:

```cypher
MATCH (c:DemoCustomer {customerId: 'C1'})
CALL (c) {
  OPTIONAL MATCH (c)-[:PLACED]->(o:DemoOrder)
  WITH DISTINCT o
  RETURN count(o) AS orderCount,
         sum(o.amount) AS totalAmount
}
CALL (c) {
  OPTIONAL MATCH (c)-[:OPENED]->(t:DemoTicket)
  RETURN count(DISTINCT t) AS ticketCount
}
RETURN c.customerId AS customer,
       orderCount,
       totalAmount,
       ticketCount;
```

Mỗi subquery chạy theo từng khách hàng `c` được truyền vào. Subquery thứ nhất trả đúng một dòng với `orderCount` và `totalAmount`; subquery thứ hai trả đúng một dòng với `ticketCount`. Vì vậy, hai tập đơn/phiếu không bị ghép thành 6 tổ hợp.

Trong một số bản Neo4j 5 cũ hơn, có thể sử dụng cú pháp nhập biến truyền thống, hiện đã được đánh dấu deprecated trên các bản mới:

```cypher
MATCH (c:DemoCustomer {customerId: 'C1'})
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:PLACED]->(o:DemoOrder)
  WITH DISTINCT o
  RETURN count(o) AS orderCount,
         sum(o.amount) AS totalAmount
}
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:OPENED]->(t:DemoTicket)
  RETURN count(DISTINCT t) AS ticketCount
}
RETURN c.customerId AS customer,
       orderCount,
       totalAmount,
       ticketCount;
```

Hai cách minh họa cùng mục tiêu; dùng đúng cú pháp với phiên bản/Cypher version đang chạy. Một subquery **không có kết quả đầu ra** có thể loại bỏ dòng bên ngoài; nhờ `OPTIONAL MATCH` và phép tổng hợp không có khóa nhóm, ví dụ này vẫn trả một dòng cho khách hàng chưa có đơn hoặc phiếu.

**Lợi ích:** mỗi phép tổng hợp có phạm vi và đơn vị dữ liệu được xác định riêng. Khi thêm nhánh thứ ba như `(:Customer)-[:HAS]->(:Address)`, không cần trộn đơn hàng, phiếu hỗ trợ và địa chỉ trong một bảng hàng trung gian.

**Giới hạn:** subquery không tự sửa truy vấn kém hiệu quả. Nếu mỗi subquery tìm hàng triệu quan hệ do thiếu bộ lọc hoặc index, chi phí vẫn lớn. Mục tiêu là vừa **đúng cardinality**, vừa hạn chế các lần mở rộng đồ thị không cần thiết.

## 7. Cách 3: chỉ kiểm tra sự tồn tại thì dùng `EXISTS`

Đôi khi yêu cầu không cần danh sách phiếu hỗ trợ mà chỉ cần biết **khách hàng có ít nhất một phiếu hay không**. Ghép toàn bộ phiếu vào bảng hàng rồi `DISTINCT` là quá nhiều công việc.

Dùng biểu thức tồn tại:

```cypher
MATCH (c:DemoCustomer)
WHERE EXISTS {
  MATCH (c)-[:OPENED]->(:DemoTicket)
}
RETURN c.customerId AS customer;
```

Truy vấn này trả mỗi khách hàng phù hợp theo dữ liệu đầu vào của `MATCH`, **không cần tạo một hàng cho từng phiếu**. Có thể dùng biểu thức `EXISTS` trong `RETURN` để trả cờ boolean thay vì lọc:

```cypher
MATCH (c:DemoCustomer)
RETURN c.customerId AS customer,
       EXISTS {
         MATCH (c)-[:OPENED]->(:DemoTicket)
       } AS hasTickets;
```

Khi bài toán yêu cầu đếm số mẫu quan hệ, Cypher hiện đại còn có `COUNT { ... }` subquery:

```cypher
MATCH (c:DemoCustomer)
RETURN c.customerId AS customer,
       COUNT {
         MATCH (c)-[:OPENED]->(:DemoTicket)
       } AS ticketRelationships;
```

Lưu ý: cách đếm này phản ánh **số mẫu/quan hệ khớp**, nên nếu có hai relationship khác nhau từ cùng khách hàng tới một phiếu, số đếm có thể là 2. Nếu nghiệp vụ muốn đếm **số node phiếu duy nhất**, hãy dùng `count(DISTINCT t)` trong nhánh riêng. Cần phân biệt **đơn vị đếm là quan hệ, node hay path**.

## 8. `OPTIONAL MATCH` và giá trị `null` có thể gây hiểu nhầm

`OPTIONAL MATCH` giữ lại dòng nguồn và gán `null` cho biến không khớp. Điều này giúp báo cáo vẫn có khách hàng chưa có đơn, nhưng cũng tạo khác biệt giữa `count(*)` và `count(o)`.

```cypher
MATCH (c:DemoCustomer)
OPTIONAL MATCH (c)-[:PLACED]->(o:DemoOrder)
RETURN c.customerId AS customer,
       count(*) AS rowsAfterOptional,
       count(o) AS orders;
```

Nếu một khách hàng **không có đơn**, `count(*)` có thể là **1** (dòng khách hàng vẫn còn), trong khi `count(o)` bằng **0** (bỏ qua `null`).

Tương tự, đặt điều kiện `WHERE` sai chỗ có thể biến một truy vấn “tùy chọn” thành lọc mất khách hàng:

```cypher
// Giữ khách hàng, chỉ chọn đơn hàng có trạng thái PAID.
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN c.customerId, count(o);
```

Trong trường hợp này, `WHERE` gắn với chính `OPTIONAL MATCH`. Nếu chuyển điều kiện thành `WITH c, o WHERE o.status = 'PAID'`, những khách hàng chỉ có đơn không hợp lệ hoặc không có đơn có thể bị **loại khỏi dòng đầu vào**. Khi viết báo cáo, xác định rõ cần giữ các đối tượng có số lượng bằng 0 hay chỉ lấy đối tượng có khớp.

Ngoài ra, `sum(o.amount)` bỏ qua giá trị `null`. Nếu đơn hàng tồn tại nhưng thiếu `amount`, một tổng tiền trông hợp lệ có thể che giấu dữ liệu chưa hoàn chỉnh. Có thể báo cáo thêm `count(o.amount)`, số đơn có giá và kiểm tra chất lượng đầu vào trước khi tính tổng tài chính.

## 9. Vì sao một `DISTINCT` ở cuối thường quá muộn?

Xét truy vấn:

```cypher
MATCH (c:DemoCustomer {customerId: 'C1'})
MATCH (c)-[:PLACED]->(o:DemoOrder)
MATCH (c)-[:OPENED]->(t:DemoTicket)
RETURN DISTINCT c.customerId AS customer;
```

Kết quả chỉ còn một dòng `C1`, nhưng **sáu hàng trung gian vẫn có thể đã được sinh ra** trước khi `DISTINCT` khử trùng. Nếu có hàng triệu hàng giữa các bước, thời gian và bộ nhớ đã bị tiêu hao.

Tương tự, nếu cộng tổng tiền **trước** khi khử trùng:

```cypher
MATCH (c:DemoCustomer {customerId: 'C1'})
MATCH (c)-[:PLACED]->(o:DemoOrder)
MATCH (c)-[:OPENED]->(t:DemoTicket)
WITH c, sum(o.amount) AS totalAmount
RETURN DISTINCT c.customerId AS customer, totalAmount;
```

`totalAmount` vẫn là **600**. `DISTINCT` cuối cùng chỉ loại bỏ dòng kết quả giống nhau; nó **không đảo ngược** phép `sum` đã tính sai.

Có hai nguyên tắc tối ưu quan trọng:

1. **Giảm số hàng sớm:** lọc theo khóa/index, giới hạn phạm vi mẫu, tổng hợp mỗi nhánh trước khi mở rộng nhánh tiếp theo.
2. **Khử trùng đúng đối tượng:** `DISTINCT o` nếu nghiệp vụ cần mỗi đơn một lần; `DISTINCT r` nếu cần mỗi relationship một lần; đừng tự động dùng `DISTINCT o.amount`.

Một `WITH DISTINCT` đúng vị trí thường hiệu quả hơn việc trả tất cả hàng rồi mới `RETURN DISTINCT`, nhưng bản thân khử trùng cũng có chi phí và cần đo theo execution plan thực tế.

## 10. Đọc execution plan để tìm nguyên nhân nhân hàng

Cypher có hai công cụ chính:

- `EXPLAIN`: hiển thị **kế hoạch dự kiến**, không chạy công việc truy vấn.
- `PROFILE`: **thực thi truy vấn** và ghi lại thông tin như số hàng, DB hits, bộ nhớ/timing tùy runtime.

Dùng `EXPLAIN` khi muốn kiểm tra hướng tiếp cận mà chưa chạy truy vấn:

```cypher
EXPLAIN
MATCH (o:DemoOrder), (t:DemoTicket)
RETURN o.orderId, t.ticketId;
```

Với mẫu độc lập, một kế hoạch có thể hiển thị operator `CartesianProduct`. Theo mô tả của Neo4j, operator này kết hợp **mỗi hàng bên trái với mọi hàng bên phải**. Trên dữ liệu thực, planner có thể chọn kế hoạch và operator khác tùy cấu trúc truy vấn, phiên bản và thống kê; đừng suy luận chỉ từ việc có/không nhìn thấy một tên operator.

Đối với ví dụ hai nhánh cùng khách hàng:

```cypher
PROFILE
MATCH (c:DemoCustomer {customerId: 'C1'})
OPTIONAL MATCH (c)-[:PLACED]->(o:DemoOrder)
OPTIONAL MATCH (c)-[:OPENED]->(t:DemoTicket)
RETURN c.customerId, count(o), sum(o.amount), count(t);
```

Khi xem kế hoạch, tập trung vào:

| Thông tin trong plan | Câu hỏi cần trả lời |
| --- | --- |
| `Rows` | Sau operator nào số hàng tăng đột biến? |
| `Estimated Rows` | Ước lượng của planner lệch thực tế bao nhiêu? |
| `DB Hits` | Truy vấn đang đọc dữ liệu nhiều ở đâu? |
| `CartesianProduct` | Có đang ghép hai tập độc lập ngoài mục tiêu? |
| `Expand` / `OptionalExpand` / `Apply` | Nhánh nào đang mở rộng từ 1 hàng thành nhiều hàng? |
| `EagerAggregation` / `OrderedAggregation` | Tổng hợp xuất hiện trước hay sau khi hàng bị nhân? |
| `NodeByLabelScan`, `NodeIndexSeek` | Cách định vị điểm xuất phát có hợp lý không? |
| `Memory (Bytes)` | Operator nào tốn nhiều bộ nhớ trong runtime hỗ trợ thông tin này? |

**Cách đọc một dấu hiệu điển hình:** từ 1 node khách hàng → 2 hàng đơn → 6 hàng sau mở rộng phiếu. Nếu phép `Aggregation` nhận 6 hàng và cộng `o.amount`, tổng tiền bị nhân đúng ở vị trí đó.

Để so sánh, `PROFILE` lại phiên bản tách subquery hoặc tổng hợp sớm và xem số hàng đầu vào của mỗi phép tổng hợp. Đừng đánh giá chỉ bằng một thời gian chạy rất ngắn trên đồ thị nhỏ; dùng workload đại diện để so sánh lượng DB hits, rows, memory và độ trễ.

**Cảnh báo:** `PROFILE` chạy thật. Nếu áp dụng lên truy vấn `CREATE` / `MERGE` / `SET` / `DELETE`, nó **có thể thay đổi dữ liệu**. Với truy vấn ghi, bắt đầu bằng `EXPLAIN` và thử nghiệm trong môi trường an toàn.

## 11. Kết hợp index, ràng buộc và lọc sớm

Tích Descartes 1 × 1 giữa hai node định danh duy nhất thường không đáng ngại; điều nguy hiểm là một phía trả hàng nghìn node do thiếu điều kiện. Vì vậy index và constraint đóng vai trò quan trọng.

Ví dụ trong mô hình khách hàng:

```cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;
```

Khi truy vấn:

```cypher
MATCH (c:Customer {customerId: $customerId})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN c.customerId AS customer,
       count(DISTINCT o) AS orderCount;
```

Planner có cơ hội dùng index hỗ trợ uniqueness để định vị một khách hàng. Cùng lúc, điều kiện `$customerId` được truyền qua tham số từ ứng dụng giúp truy vấn có điểm bắt đầu rõ ràng.

Tuy nhiên, index **không** tự ngăn lỗi nhân hàng giữa hai nhánh `:PLACED` và `:OPENED`. Nó làm giảm chi phí định vị node, còn tính đúng của phép tổng hợp phụ thuộc **cấu trúc truy vấn**.

Khi cả hai đầu quan hệ đều được truy vấn bằng khóa:

```cypher
MATCH (a:Person {personId: $sourceId})
MATCH (b:Person {personId: $targetId})
MERGE (a)-[:FOLLOWS]->(b);
```

Cần bảo đảm mỗi khóa là duy nhất theo đặc tả; nếu không, `MERGE` có thể hoạt động trên nhiều cặp node không mong muốn. Với thao tác ghi, hậu quả của số hàng tăng không chỉ là sai báo cáo mà còn là **số lượng thay đổi trên graph**.

## 12. Vấn đề lặp hàng khi phân tích đường đi

Mẫu đường đi biến độ dài có thể tạo **nhiều path tới cùng một node**:

```cypher
MATCH (p:Person {personId: $startId})
MATCH path = (p)-[:KNOWS*1..3]->(friend:Person)
RETURN friend.personId AS friendId,
       length(path) AS hops;
```

Nếu hai con đường khác nhau dẫn tới cùng `friend`, node đó xuất hiện trong nhiều hàng. Câu hỏi nghiệp vụ là:

- “Có **bao nhiêu path** dài tối đa 3 bước?” → đếm `path`.
- “Có **bao nhiêu người duy nhất** có thể tới được?” → đếm `DISTINCT friend`.
- “Có **bao nhiêu mối quan hệ** trên các tuyến?” → cần quy tắc đếm relationship có thể lặp giữa các path.
- “Tổng giá trị giao dịch của những người có thể tới được?” → **khử trùng người hoặc giao dịch** theo đơn vị tiền trước khi cộng.

Ví dụ:

```cypher
MATCH (p:Person {personId: $startId})
MATCH (p)-[:KNOWS*1..3]->(friend:Person)
RETURN count(DISTINCT friend) AS distinctReachablePeople;
```

Trong trường hợp này, `count(DISTINCT friend)` là đúng nếu cần số **node khác nhau**, còn `count(*)` đếm số hàng từ các đường phù hợp. Nhưng với một truy vấn duyệt sâu, việc tạo rất nhiều path để rồi khử trùng vẫn có thể đắt đỏ; cân nhắc thuật toán duyệt hoặc mô hình truy vấn khác nếu bài toán yêu cầu khả năng tiếp cận trên mạng lớn.

## 13. Cẩn thận với `UNWIND` và truy vấn ghi

Nhân hàng có thể xuất hiện không cần `MATCH`:

```cypher
WITH ['A', 'B'] AS warehouses,
     ['P1', 'P2', 'P3'] AS products
UNWIND warehouses AS warehouse
UNWIND products AS product
RETURN warehouse, product;
```

Hai `UNWIND` liên tiếp tạo 6 tổ hợp. Nếu phía sau có `MERGE` hoặc `CREATE`, truy vấn có thể tạo ra **6 quan hệ hoặc node** tùy mẫu. Đây có thể là chủ ý (mọi kho chứa mọi sản phẩm) hoặc lỗi logic (đáng lẽ cần ghép từng cặp tương ứng).

Với danh sách các cặp đã xác định sẵn, nên truyền từng cặp như một phần tử dữ liệu:

```cypher
UNWIND $pairs AS pair
MATCH (w:Warehouse {code: pair.warehouseCode})
MATCH (p:Product {sku: pair.productSku})
MERGE (w)-[:STOCKS]->(p);
```

Nếu `$pairs` chứa ba cặp, mỗi hàng ứng với một cặp. Vẫn cần uniqueness constraint cho `Warehouse.code` và `Product.sku`, kiểm tra payload trùng lặp và quy tắc `MERGE` thích hợp để không tạo quan hệ sai.

Không nên sử dụng `collect()` để “chữa” mọi vấn đề nhân hàng trong công việc ghi. Việc gom nhiều triệu node vào một danh sách có thể tăng bộ nhớ transaction. Chọn luồng dữ liệu theo từng đơn vị nghiệp vụ, giới hạn batch và chỉ gom danh sách khi thực sự cần.

## 14. Áp dụng trong Java Driver và Spring Data Neo4j

Tầng ứng dụng thường đọc kết quả tổng hợp và chuyển thành DTO. Nếu truy vấn đã cộng trùng tiền, Java sẽ nhận **một số hoàn toàn hợp lệ về kiểu** nhưng sai nghiệp vụ. Vì vậy phải sửa ở Cypher, không nên “chia ngược” tổng tiền theo số ticket trong Java: số nhánh và tình trạng quan hệ thay đổi sẽ khiến công thức đó hỏng.

Ví dụ Java Driver sử dụng truy vấn tách phép tổng hợp:

```java
String query = """
    MATCH (c:Customer {customerId: $customerId})
    CALL (c) {
      OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
      WITH DISTINCT o
      RETURN count(o) AS orderCount,
             sum(o.amount) AS totalAmount
    }
    CALL (c) {
      OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
      RETURN count(DISTINCT t) AS ticketCount
    }
    RETURN c.customerId AS customerId,
           orderCount, totalAmount, ticketCount
    """;

try (var session = driver.session()) {
    var summary = session.executeRead(tx -> {
        var record = tx.run(
            query,
            java.util.Map.of("customerId", "C1")
        ).single();

        return java.util.Map.of(
            "customerId", record.get("customerId").asString(),
            "orderCount", record.get("orderCount").asLong(),
            "totalAmount", record.get("totalAmount").asLong(),
            "ticketCount", record.get("ticketCount").asLong()
        );
    });
    System.out.println(summary);
}
```

Đoạn mã giả định mọi `Order.amount` có kiểu số nguyên (đơn vị tiền nhỏ nhất) và không thiếu; trong dữ liệu thực tế cần kiểm tra quy tắc tiền tệ, kiểu `INTEGER` hoặc `FLOAT`, và khả năng không có khách hàng (khi đó `single()` thất bại). Cú pháp `CALL (c)` cần phiên bản hỗ trợ.

Trong **Spring Data Neo4j**, có thể đặt một truy vấn Cypher tùy biến ở repository/service và ánh xạ `orderCount`, `totalAmount`, `ticketCount` sang DTO. Điểm quan trọng là **không tải toàn bộ hai collection quan hệ rồi tính tổng trên tập kết quả bị nhân**, nhất là khi dữ liệu có nhiều phần tử; điều đó gây thêm truyền dữ liệu, bộ nhớ ứng dụng và khả năng đếm sai.

Với API báo cáo theo nhiều khách hàng, tránh mẫu gọi một truy vấn riêng cho từng khách hàng nếu điều đó dẫn tới vấn đề **N+1 queries**. Một câu Cypher tổng hợp cho tập khách hàng được lọc trước, hoặc chiến lược batch hợp lý, thường dễ quản lý hơn. Tuy nhiên, mọi subquery theo mỗi khách hàng vẫn cần quan sát tổng chi phí trên số lượng khách hàng lớn.

## 15. Quy trình rà soát một truy vấn có số liệu bất thường

Khi một báo cáo Cypher trả “tổng doanh thu gấp ba lần dự kiến”, hãy kiểm tra có hệ thống:

1. **Xác định đơn vị nghiệp vụ**: doanh thu là tổng theo **đơn hàng duy nhất** hay theo các dòng chi tiết trong đơn? Khách hàng là node duy nhất hay một hàng cho mỗi quan hệ?
2. **Kiểm tra các `MATCH` độc lập**: hai mẫu có biến chung hoặc điều kiện nối rõ ràng chưa? Nếu không, kích thước tập đầu vào là bao nhiêu?
3. **Đếm hàng tại từng giai đoạn**: chạy các phiên bản read-only tạm thời chỉ `RETURN count(*)`/`count(DISTINCT ...)` để xem bước nào số hàng tăng.
4. **Nhận diện fan-out**: một khách hàng có bao nhiêu đơn, bao nhiêu ticket, bao nhiêu path? Những nhánh này có bị ghép vào cùng một bảng hàng không?
5. **Xác định phép tổng hợp**: `sum(amount)` đang thấy mỗi đơn một lần hay nhiều lần? `sum(DISTINCT amount)` có sai khi hai đơn cùng số tiền không?
6. **Tách phép tổng hợp sớm**: dùng `WITH` theo khóa nhóm đúng hoặc subquery từng nhánh; dùng `EXISTS` nếu chỉ cần sự tồn tại.
7. **Đọc `EXPLAIN`/`PROFILE`**: so sánh `Rows`, `DB Hits`, các phép `Expand` và operator tổng hợp trước/sau sửa.
8. **Kiểm thử ca biên**: khách hàng không có đơn, có nhiều đơn bằng tiền, nhiều relationship tới cùng node, dữ liệu `null`, nhiều đường tới một đích.
9. **Kiểm tra trong ứng dụng**: thông số gửi qua Java Driver, ánh xạ DTO và giới hạn kết quả phải giữ đúng tiêu chí tổng hợp đã xác định.

### Bảng quyết định nhanh

| Nhu cầu | Gợi ý triển khai | Tránh |
| --- | --- | --- |
| Ghép hai node định danh duy nhất | Hai lần định vị bằng index/constraint rồi `MERGE` quan hệ | Chọn hai tập lớn mà không có điều kiện |
| Chỉ biết có liên kết hay không | `EXISTS { MATCH ... }` | Ghép toàn bộ quan hệ rồi `DISTINCT` |
| Đếm node khác nhau sau nhiều path | `count(DISTINCT node)` | `count(*)` nếu mục tiêu là số node |
| Tổng tiền đơn hàng và đếm ticket | Tách từng nhánh bằng `WITH` hoặc `CALL` subquery | `sum(order.amount)` trên hàng đơn × ticket |
| Hai đơn có cùng số tiền | Khử trùng theo **đơn** trước `sum` | `sum(DISTINCT amount)` |
| Ghi theo danh sách cặp nguồn–đích | `UNWIND $pairs` với khóa duy nhất | Hai `UNWIND` tạo mọi tổ hợp ngoài ý muốn |
| Truy vấn path rất sâu | Giới hạn mục tiêu, độ sâu, điều kiện và cân nhắc thuật toán | Tạo mọi path rồi mới lọc/khử trùng ở cuối |

## 16. Bài tập tự kiểm tra

**Bài 1 — Giải thích sai số.** Một khách hàng có 4 đơn hàng, mỗi đơn 50 đồng, và 5 ticket. Câu truy vấn ghép hai nhánh rồi `sum(o.amount)` sẽ trả bao nhiêu nếu không khử trùng? Số đúng là bao nhiêu? Vì sao?

**Bài 2 — Bẫy của `DISTINCT`.** Hai đơn hàng khác nhau có giá trị `200` và `200`. Vì sao `sum(DISTINCT o.amount)` sai? Viết truy vấn khử trùng theo đơn trước khi tổng hợp.

**Bài 3 — Phân biệt Cartesian và fan-out.** Cho hai câu truy vấn:

```cypher
MATCH (a:Author), (b:Book)
RETURN a, b;

MATCH (a:Author)-[:WROTE]->(b:Book)
MATCH (a)-[:LIVES_IN]->(city:City)
RETURN a, b, city;
```

Câu nào có mẫu độc lập? Câu nào cùng một tác giả nhưng có thể nhân hàng theo hai nhánh? Nếu một tác giả viết 3 sách và sống ở 2 thành phố theo dữ liệu, sẽ có bao nhiêu tổ hợp cho tác giả đó?

**Bài 4 — Đọc kế hoạch.** Một kế hoạch `PROFILE` có lần lượt 100 hàng node, 1.000 hàng sau mở rộng quan hệ và 20.000 hàng sau nhánh thứ hai. Hãy chỉ ra nơi số hàng tăng mạnh, phép tính tổng nào dễ sai và nên đặt bước tổng hợp ở đâu.

**Bài 5 — Tồn tại và số lượng.** Viết truy vấn trả danh sách khách hàng có ít nhất một ticket bằng `EXISTS`. Sau đó viết biến thể trả số ticket **duy nhất** trên mỗi khách hàng. Trình bày sự khác nhau nếu nhiều quan hệ cùng nối tới một ticket.

**Bài 6 — API thực tế.** Một Spring Data Neo4j service trả `customerId`, `orderCount`, `revenue` và `followerCount`. Thiết kế cách tách các phép tổng hợp để một khách hàng có 20 đơn và 50 người theo dõi không khiến doanh thu bị nhân 50 lần.

## 17. Tài liệu đối chiếu

Để kiểm tra các cú pháp Cypher và đặc điểm của execution plan trên đúng phiên bản Neo4j đang chạy:

- [Cypher Manual — Query tuning / Operators in detail](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/operators/operators-detail/): mô tả `CartesianProduct`, operator mở rộng và phép tổng hợp.
- [Cypher Manual — CALL subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/call-subquery/): nhập biến `CALL (variable)`, hoạt động và ảnh hưởng đến số hàng.
- [Cypher Manual — Aggregating functions](https://neo4j.com/docs/cypher-manual/current/functions/aggregating/): `count()`, `sum()`, `DISTINCT` và khóa nhóm.
- [Cypher Manual — EXPLAIN and PROFILE](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/query-tuning/): kiểm tra kế hoạch và số hàng thực tế.
- [Cypher Manual — Subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/): các dạng subquery và điều kiện sử dụng.

**Ghi nhớ:** một truy vấn Cypher có thể nhân hàng **mà không hiện chữ `CartesianProduct` trong plan**. Trước khi tính tổng hay đếm, hãy xác định **đơn vị dữ liệu được tổng hợp**, giảm cardinality ngay ở nhánh tạo dữ liệu và kiểm tra kế hoạch thực thi. `count(DISTINCT entity)` thường hữu ích để đếm thực thể, nhưng `sum(DISTINCT property)` không thay thế việc **tổng hợp đúng một lần trên mỗi thực thể nghiệp vụ**.

# Lọc dữ liệu trong DSL truy vấn

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích vai trò của thao tác lọc dữ liệu trong DSL truy vấn.
- Phân biệt lọc hàng (row filtering), lọc cột (projection), lọc nhóm (group filtering) và lọc phần tử trong collection.
- Viết predicate bằng toán tử so sánh, logic, kiểm tra null, chuỗi, số, ngày giờ và tập hợp.
- Hiểu precedence, short-circuit và logic ba giá trị khi dữ liệu có null.
- Kết hợp điều kiện bằng AND, OR, NOT, EXISTS và các phép kiểm tra membership.
- Sử dụng parameter để tạo truy vấn an toàn và có thể tái sử dụng.
- Hiểu vị trí của WHERE, ON, HAVING, FILTER và điều kiện trong truy vấn lồng nhau.
- Nhận biết ảnh hưởng của kiểu dữ liệu, ép kiểu, collation, timezone và precision.
- Đọc kế hoạch thực thi cơ bản và hiểu cách index hỗ trợ lọc.
- Thiết kế bộ lọc phân trang, truy vấn streaming và bộ lọc trên dữ liệu lớn.
- Kiểm thử kết quả lọc với dữ liệu biên, null, dữ liệu không hợp lệ và điều kiện kết hợp.

## 1. Lọc dữ liệu là gì?

Lọc dữ liệu (data filtering) là thao tác xác định bản ghi hoặc phần tử nào thỏa một hay nhiều điều kiện. Trong DSL truy vấn, điều kiện lọc thường được biểu diễn bằng một biểu thức logic gọi là predicate.

Ví dụ, một hệ thống quản lý đơn hàng có thể cần tìm các đơn đã thanh toán có tổng tiền lớn hơn 500.000:

~~~text
from orders
where status == "PAID" and total > 500000
select id, customerId, total
~~~

Điều kiện sau từ khóa where quyết định hàng nào được giữ lại. Các hàng không thỏa điều kiện bị loại khỏi kết quả truy vấn.

Một truy vấn có thể đọc hàng triệu bản ghi nhưng chỉ trả về vài chục bản ghi sau khi lọc. Vì vậy, lọc dữ liệu vừa là thao tác mô tả ý định nghiệp vụ, vừa có ảnh hưởng lớn đến hiệu năng và tài nguyên của hệ thống.

Trong một DSL truy vấn, người dùng nên mô tả điều kiện ở mức miền dữ liệu, còn engine chịu trách nhiệm chuyển điều kiện đó thành cách thực thi phù hợp với nguồn dữ liệu.

## 2. Vị trí của lọc dữ liệu trong query pipeline

Một truy vấn thường gồm nhiều bước. Thứ tự cú pháp người dùng viết không nhất thiết giống thứ tự engine thực thi.

Một pipeline khái niệm:

~~~text
Nguồn dữ liệu
    |
    v
Đọc / Scan
    |
    v
Lọc hàng (WHERE)
    |
    v
Kết hợp dữ liệu (JOIN)
    |
    v
Nhóm dữ liệu (GROUP BY)
    |
    v
Lọc nhóm (HAVING)
    |
    v
Chiếu cột (SELECT)
    |
    v
Sắp xếp (ORDER BY)
    |
    v
Phân trang (LIMIT / OFFSET)
    |
    v
Kết quả
~~~

Pipeline thực tế có thể thay đổi do optimizer. Ví dụ, engine có thể đẩy điều kiện lọc xuống gần nguồn dữ liệu hơn để giảm số hàng phải đọc. Một số hệ thống cũng có thể thực hiện join trước hoặc sau các phép lọc tùy semantics và khả năng tối ưu.

### 2.1. WHERE: lọc hàng

WHERE lọc từng hàng dựa trên các cột hoặc biểu thức thuộc hàng đó:

~~~text
from customers
where active == true
select id, name
~~~

Mỗi customer được kiểm tra độc lập. Hàng thỏa predicate được giữ lại.

### 2.2. HAVING: lọc nhóm

HAVING áp dụng sau khi dữ liệu được nhóm hoặc tổng hợp:

~~~text
from orders
group by customerId
having sum(total) > 1000000
select customerId, sum(total) as revenue
~~~

Ở đây, điều kiện kiểm tra tổng doanh thu của mỗi nhóm khách hàng, không phải tổng tiền của từng đơn hàng riêng lẻ.

### 2.3. ON: điều kiện ghép dữ liệu

ON xác định cặp hàng nào được ghép trong JOIN:

~~~text
from orders
join customers
    on orders.customerId == customers.id
where customers.active == true
select orders.id, customers.name
~~~

Điều kiện ON và WHERE có vai trò khác nhau, đặc biệt với outer join. Đưa điều kiện từ ON sang WHERE có thể thay đổi kết quả.

### 2.4. FILTER trong aggregate

Một số DSL cho phép lọc dữ liệu riêng cho từng phép tổng hợp:

~~~text
from orders
group by customerId
select
    customerId,
    count(*) as allOrders,
    count(*) filter (where status == "PAID") as paidOrders
~~~

Cách viết cụ thể tùy DSL, nhưng ý nghĩa là aggregate chỉ tính những hàng thỏa điều kiện riêng của nó.

### 2.5. Lọc và chiếu cột

Lọc hàng quyết định bản ghi nào còn lại. Projection (select) quyết định trường nào xuất hiện trong kết quả. Hai thao tác độc lập:

~~~text
from products
where category == "BOOK"
select id, title, price
~~~

Truy vấn chỉ giữ sản phẩm thuộc category BOOK, rồi trả về ba trường id, title và price.

## 3. Predicate và biểu thức điều kiện

Predicate là biểu thức được đánh giá để quyết định một đối tượng có thỏa điều kiện hay không. Trong logic hai giá trị, predicate trả về true hoặc false. Trong hệ thống có null, predicate có thể trả thêm unknown.

Ví dụ predicate đơn giản:

~~~text
price > 100
status == "ACTIVE"
quantity >= minimumQuantity
~~~

Predicate có thể được kết hợp:

~~~text
status == "PAID" and total > 500000
~~~

### 3.1. Predicate trên một hàng

Một predicate trong WHERE thường được đánh giá với một row context. Tên cột được phân giải thành giá trị trong hàng hiện tại.

Ví dụ:

~~~text
where customer.age >= 18
~~~

Với mỗi hàng, engine đọc customer.age rồi đánh giá phép so sánh.

### 3.2. Predicate có thể chứa hàm

~~~text
where lower(email) endsWith "@example.com"
~~~

Hàm trong predicate cần có semantics rõ ràng. Hàm thuần (pure function) dễ tối ưu hơn hàm có tác dụng phụ hoặc phụ thuộc thời gian hệ thống.

### 3.3. Predicate có thể chứa subquery

~~~text
where customerId in (
    from vipCustomers
    select id
)
~~~

Subquery trả tập giá trị để predicate membership kiểm tra. Optimizer có thể chuyển dạng này thành semi-join hoặc chiến lược khác.

### 3.4. Predicate có thể phụ thuộc parameter

~~~text
from orders
where status == :status
  and createdAt >= :fromDate
select id, total
~~~

Parameter giúp cùng một cấu trúc truy vấn được dùng với nhiều giá trị đầu vào.

## 4. Toán tử so sánh

Các toán tử so sánh là nền tảng của lọc dữ liệu.

| Toán tử | Ý nghĩa | Ví dụ |
|---|---|---|
| == | Bằng | status == "PAID" |
| != | Khác | status != "CANCELLED" |
| < | Nhỏ hơn | age < 18 |
| <= | Nhỏ hơn hoặc bằng | score <= 10 |
| > | Lớn hơn | total > 500000 |
| >= | Lớn hơn hoặc bằng | quantity >= 3 |

DSL có thể dùng = thay cho ==, hoặc dùng keyword như equals. Điều quan trọng là semantics phải nhất quán.

### 4.1. So sánh số

~~~text
where price >= 100 and price < 500
~~~

Khoảng giá trên bao gồm 100 nhưng không bao gồm 500.

Với số thập phân, cần xác định kiểu decimal có precision/scale hay kiểu floating point. Không nên giả định mọi phép so sánh số thực đều chính xác tuyệt đối.

### 4.2. So sánh chuỗi

~~~text
where country == "VN"
~~~

So sánh chuỗi có thể phân biệt chữ hoa/chữ thường hoặc không, tùy collation. Ví dụ, "Lan" và "lan" có thể được xem là bằng nhau trong một cấu hình và khác nhau trong cấu hình khác.

### 4.3. So sánh ngày giờ

~~~text
where createdAt >= :startTime
  and createdAt < :endTime
~~~

Nên xác định timezone và kiểu thời gian của parameter. So sánh timestamp có timezone với local datetime không có timezone có thể gây kết quả không mong muốn nếu engine tự chọn timezone mặc định.

### 4.4. So sánh giá trị khác kiểu

~~~text
where order.total > "1000"
~~~

Biểu thức trên có thể là lỗi kiểu nếu total là số và literal là chuỗi. Một DSL nghiêm ngặt nên báo lỗi thay vì tự chuyển kiểu theo quy tắc không rõ ràng.

### 4.5. So sánh null

Không nên dùng phép bằng thông thường để kiểm tra null nếu ngôn ngữ áp dụng SQL-style three-valued logic. Thường cần cú pháp riêng:

~~~text
where shippedAt is null
where cancelledAt is not null
~~~

## 5. Kết hợp điều kiện bằng AND, OR và NOT

Một truy vấn thực tế thường có nhiều điều kiện.

### 5.1. AND

AND chỉ đúng khi tất cả điều kiện đều đúng:

~~~text
where status == "PAID"
  and total >= 500000
~~~

### 5.2. OR

OR đúng khi ít nhất một điều kiện đúng:

~~~text
where status == "NEW"
   or status == "PROCESSING"
~~~

### 5.3. NOT

NOT đảo giá trị logic theo semantics của DSL:

~~~text
where not isArchived
~~~

Với logic ba giá trị, NOT UNKNOWN vẫn là UNKNOWN, không trở thành TRUE.

### 5.4. Dấu ngoặc và precedence

Thông thường NOT có precedence cao hơn AND, còn AND cao hơn OR:

~~~text
where active == true
  and (role == "ADMIN" or role == "OWNER")
~~~

Không nên phụ thuộc vào trí nhớ về precedence khi biểu thức phức tạp. Dấu ngoặc giúp ý định rõ ràng và tránh hiểu sai.

### 5.5. De Morgan

Có thể biến đổi:

~~~text
not (A and B)
~~~

thành:

~~~text
(not A) or (not B)
~~~

và:

~~~text
not (A or B)
~~~

thành:

~~~text
(not A) and (not B)
~~~

Các quy tắc này đúng trong logic Boolean hai giá trị và cũng có dạng tương ứng trong logic ba giá trị, nhưng khi tối ưu cần giữ semantics null và thứ tự đánh giá mà DSL công bố.

### 5.6. Short-circuit

Một DSL có thể đánh giá AND theo kiểu short-circuit: nếu vế trái đã false thì không cần đánh giá vế phải. Với OR, nếu vế trái true thì có thể bỏ qua vế phải.

Trong query engine, predicate thường được tối ưu và thực thi theo vector hoặc kế hoạch dữ liệu, nên không nên dựa vào side effect trong biểu thức lọc. Tốt nhất, hàm dùng trong predicate nên thuần và không phụ thuộc việc có được đánh giá hay không.

## 6. Logic ba giá trị và NULL

Dữ liệu thực tế thường thiếu giá trị. SQL-style query language dùng ba giá trị logic:

- TRUE
- FALSE
- UNKNOWN

UNKNOWN thường xuất hiện khi so sánh với NULL.

Ví dụ:

~~~text
NULL == 5
NULL != 5
NULL > 5
~~~

Các biểu thức này thường trả UNKNOWN thay vì TRUE hoặc FALSE.

### 6.1. Truth table cơ bản

| A | B | A AND B | A OR B |
|---|---|---|---|
| TRUE | TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE | TRUE |
| TRUE | UNKNOWN | UNKNOWN | TRUE |
| FALSE | FALSE | FALSE | FALSE |
| FALSE | UNKNOWN | FALSE | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

NOT có quy tắc:

| A | NOT A |
|---|---|
| TRUE | FALSE |
| FALSE | TRUE |
| UNKNOWN | UNKNOWN |

### 6.2. WHERE xử lý UNKNOWN như thế nào?

Trong SQL-style semantics, WHERE chỉ giữ hàng khi predicate là TRUE. Hàng có kết quả FALSE hoặc UNKNOWN đều bị loại.

Ví dụ:

~~~text
from customers
where age >= 18
~~~

Nếu age là NULL, phép so sánh age >= 18 trả UNKNOWN, vì vậy hàng không xuất hiện.

### 6.3. IS NULL

Để tìm giá trị thiếu:

~~~text
where phone is null
~~~

Để tìm giá trị đã có:

~~~text
where phone is not null
~~~

Hai phép kiểm tra này trả TRUE hoặc FALSE, không trả UNKNOWN chỉ vì giá trị được kiểm tra là NULL.

### 6.4. COALESCE

COALESCE chọn giá trị đầu tiên không null:

~~~text
where coalesce(country, "UNKNOWN") == "VN"
~~~

Cần xem xét kiểu dữ liệu của các đối số. Các giá trị trong cùng lời gọi phải có kiểu tương thích hoặc có quy tắc suy luận kiểu rõ ràng.

### 6.5. NOT IN và NULL

Một trường hợp dễ gây nhầm:

~~~text
where customerId not in (10, 20, null)
~~~

Trong SQL-style logic, sự hiện diện của NULL trong tập có thể khiến phép NOT IN trả UNKNOWN cho nhiều giá trị, dẫn đến kết quả rỗng hoặc thiếu hàng.

Nếu muốn kiểm tra không thuộc một tập hợp có thể chứa null, hãy lọc null khỏi tập hoặc dùng NOT EXISTS với điều kiện tương đương đã được xác định rõ.

## 7. Lọc theo khoảng giá trị

BETWEEN thường biểu diễn khoảng có hai đầu mút bao gồm:

~~~text
where price between 100 and 500
~~~

Tương đương về ý nghĩa với:

~~~text
where price >= 100 and price <= 500
~~~

### 7.1. Khoảng đóng và khoảng nửa mở

Khoảng đóng [a, b] bao gồm cả hai đầu. Khoảng nửa mở [a, b) bao gồm a nhưng không bao gồm b.

Với thời gian, khoảng nửa mở thường thuận tiện:

~~~text
where createdAt >= :start
  and createdAt < :nextDay
~~~

Nếu truy vấn dữ liệu của ngày 15, cách dùng từ đầu ngày 15 đến trước đầu ngày 16 tránh phải đoán độ chính xác của timestamp như millisecond hoặc microsecond.

### 7.2. Khoảng bị đảo ngược

Nếu lowerBound lớn hơn upperBound, hệ thống nên có hành vi rõ:
- Trả kết quả rỗng.
- Báo lỗi parameter.
- Hoặc chấp nhận nếu DSL có semantics riêng.

Không nên âm thầm hoán đổi hai đầu mút trừ khi đặc tả nói rõ.

### 7.3. Khoảng trên dữ liệu nullable

Nếu giá trị là null, so sánh với hai đầu khoảng có thể trả UNKNOWN. Nếu muốn giữ hàng thiếu giá trị, cần viết điều kiện bổ sung.

## 8. Lọc chuỗi và mẫu văn bản

DSL truy vấn thường cần lọc theo chuỗi, tiền tố, hậu tố hoặc mẫu.

### 8.1. LIKE và wildcard

Ví dụ cú pháp kiểu SQL:

~~~text
where name like "An%"
~~~

Trong đó:
- % đại diện cho không hoặc nhiều ký tự.
- _ đại diện cho một ký tự.

Một DSL có thể dùng startsWith, contains hoặc matches thay cho LIKE.

### 8.2. Prefix và suffix

~~~text
where email startsWith "support@"
where filename endsWith ".dsl"
~~~

Các phép này thường có thể tối ưu bằng index hoặc prefix scan tùy engine.

### 8.3. Contains

~~~text
where description contains "parser"
~~~

Tìm chuỗi con thường khó tận dụng B-tree index thông thường. Có thể cần full-text index hoặc inverted index.

### 8.4. Regex

~~~text
where email matches "^[^@]+@example\\.com$"
~~~

Regex mạnh nhưng có thể tốn tài nguyên. DSL cần giới hạn độ dài pattern, thời gian thực thi hoặc dùng engine có khả năng tránh catastrophic backtracking.

### 8.5. Case sensitivity và collation

Cần xác định:
- So sánh có phân biệt hoa thường không?
- Có chuẩn hóa Unicode không?
- Có bỏ dấu hay không?
- Quy tắc locale nào được dùng?
- Thứ tự sắp xếp chuỗi có cùng collation với phép so sánh không?

Không nên để kết quả lọc thay đổi theo locale mặc định của máy chủ mà không có quy định.

### 8.6. Escape wildcard

Nếu người dùng muốn tìm ký tự % theo nghĩa literal, cần có escape syntax:

~~~text
where code like "PROMO\\_%"
~~~

Cú pháp escape cụ thể phụ thuộc DSL. Parameter binding không tự động escape wildcard theo ý nghĩa tìm kiếm; nó chỉ tách dữ liệu khỏi cú pháp truy vấn.

## 9. Lọc theo tập hợp và membership

Membership kiểm tra một giá trị có nằm trong một tập hay không.

### 9.1. IN

~~~text
where status in ["NEW", "PAID", "SHIPPED"]
~~~

Có thể tương đương với nhiều phép OR:

~~~text
where status == "NEW"
   or status == "PAID"
   or status == "SHIPPED"
~~~

### 9.2. NOT IN

~~~text
where status not in ["CANCELLED", "REJECTED"]
~~~

Cần lưu ý null trong giá trị được so sánh hoặc trong tập membership.

### 9.3. Tập parameter

Một query có thể nhận một danh sách parameter:

~~~text
from products
where categoryId in :categoryIds
select id, title
~~~

Engine cần xử lý danh sách rỗng theo semantics đã công bố. Một lựa chọn thường gặp là IN với danh sách rỗng luôn false, nhưng một số API có thể bỏ điều kiện khi list rỗng. Hai hành vi này khác nhau đáng kể.

### 9.4. EXISTS

EXISTS kiểm tra subquery có trả ít nhất một hàng:

~~~text
from customers
where exists (
    from orders
    where orders.customerId == customers.id
      and orders.status == "PAID"
)
select customers.id, customers.name
~~~

EXISTS phù hợp với câu hỏi “có ít nhất một bản ghi liên quan hay không” mà không cần trả dữ liệu của bản ghi con.

### 9.5. NOT EXISTS

~~~text
from customers
where not exists (
    from orders
    where orders.customerId == customers.id
)
select id, name
~~~

Truy vấn tìm khách hàng chưa có đơn hàng. NOT EXISTS thường tránh một số vấn đề null mà NOT IN có thể gặp.

## 10. Lọc collection và dữ liệu lồng nhau

Không phải mọi nguồn dữ liệu đều là bảng phẳng. DSL có thể lọc danh sách, mảng, object lồng nhau hoặc document.

### 10.1. Filter trên collection

~~~text
let activeItems = items.filter(item => item.active)
~~~

Mỗi phần tử được kiểm tra bằng predicate. Kết quả là collection mới chứa các phần tử thỏa điều kiện.

### 10.2. Any

ANY kiểm tra có ít nhất một phần tử thỏa:

~~~text
where any(order.items, item => item.quantity > 10)
~~~

### 10.3. All

ALL kiểm tra mọi phần tử thỏa:

~~~text
where all(order.items, item => item.isAvailable)
~~~

Cần xác định semantics của collection rỗng. Theo logic phổ biến, ALL trên collection rỗng là true, còn ANY trên collection rỗng là false.

### 10.4. None

NONE kiểm tra không có phần tử nào thỏa:

~~~text
where none(order.items, item => item.isBackordered)
~~~

Có thể tương đương NOT ANY, nhưng null trong predicate cần được xử lý theo semantics đã định.

### 10.5. Flatten và nested filter

Một document có thể chứa danh sách lồng:

~~~text
from customers
where any(
    customer.orders,
    order => order.total > 1000000
)
select customer.id
~~~

Predicate được đánh giá trong context của từng order con. Cần phân biệt biến customer bên ngoài với order bên trong để tránh shadowing và nhầm scope.

## 11. Lọc khi JOIN dữ liệu

JOIN kết hợp hàng từ nhiều nguồn. Điều kiện lọc có thể nằm trong ON hoặc WHERE.

### 11.1. INNER JOIN

~~~text
from orders
join customers
    on orders.customerId == customers.id
where customers.active == true
select orders.id, customers.name
~~~

INNER JOIN chỉ giữ cặp hàng có điều kiện ON đúng. WHERE tiếp tục lọc kết quả sau join.

### 11.2. LEFT JOIN và điều kiện WHERE

~~~text
from customers
left join orders
    on orders.customerId == customers.id
where orders.status == "PAID"
~~~

Nếu không có order, các cột phía orders là null. Điều kiện WHERE có thể loại các hàng này, khiến kết quả gần giống INNER JOIN.

### 11.3. Điều kiện trong ON

~~~text
from customers
left join orders
    on orders.customerId == customers.id
   and orders.status == "PAID"
select customers.id, orders.id
~~~

Cách viết này giữ customer kể cả khi không có order PAID. Các trường orders sẽ null.

### 11.4. Predicate pushdown qua join

Optimizer có thể đẩy điều kiện xuống trước join nếu phép biến đổi bảo toàn kết quả. Với outer join, việc di chuyển điều kiện giữa ON và WHERE có thể thay đổi semantics, nên không thể áp dụng như một luật cơ học.

### 11.5. Semi-join và anti-join

- Semi-join trả hàng bên trái có ít nhất một hàng khớp bên phải.
- Anti-join trả hàng bên trái không có hàng khớp bên phải.

EXISTS và NOT EXISTS thường được optimizer chuyển thành các dạng này.

## 12. Lọc dữ liệu sau GROUP BY

GROUP BY tạo các nhóm. HAVING lọc nhóm dựa trên aggregate.

Ví dụ:

~~~text
from orders
group by customerId
having count(*) >= 3
   and sum(total) > 1000000
select customerId, count(*), sum(total)
~~~

### 12.1. WHERE trước GROUP BY

WHERE loại hàng trước khi nhóm:

~~~text
from orders
where status == "PAID"
group by customerId
select customerId, sum(total)
~~~

Chỉ đơn đã thanh toán được đưa vào aggregate.

### 12.2. HAVING sau GROUP BY

~~~text
from orders
group by customerId
having sum(total) > 1000000
select customerId
~~~

Mọi đơn được đưa vào nhóm, sau đó nhóm có tổng tiền đủ lớn mới được giữ.

### 12.3. Lọc theo aggregate

Không thể luôn thay điều kiện HAVING bằng WHERE. Ví dụ, sum(total) > 1000000 là điều kiện trên nhóm, không phải predicate của một hàng.

### 12.4. Aggregate có filter riêng

Một truy vấn có thể tính nhiều aggregate trên các tập con khác nhau:

~~~text
from orders
group by customerId
select
    customerId,
    count(*) as totalOrders,
    count(*) filter (where status == "PAID") as paidOrders,
    sum(total) filter (where status == "PAID") as paidRevenue
~~~

Điều này tránh phải chạy nhiều truy vấn riêng cho cùng một nhóm.

## 13. Lọc theo ngày giờ và khoảng thời gian

Lọc thời gian thường xuất hiện trong báo cáo, nhật ký, giao dịch và dữ liệu sự kiện.

### 13.1. Khoảng ngày

~~~text
from events
where occurredAt >= :start
  and occurredAt < :end
select id, occurredAt, type
~~~

Dùng khoảng nửa mở giúp các khoảng liền kề không chồng lấn.

### 13.2. Ngày lịch và timezone

Một ngày lịch như 2026-11-15 phụ thuộc timezone khi chuyển thành khoảng timestamp. Ngày ở timezone UTC có thể không cùng khoảng với ngày ở timezone Asia/Ho_Chi_Minh.

Ứng dụng nên tạo start và end theo timezone nghiệp vụ rồi truyền parameter rõ kiểu.

### 13.3. Tránh chuyển đổi cột trong predicate nếu cần index

Ví dụ:

~~~text
where date(createdAt) == :day
~~~

có thể khiến index trên createdAt khó được dùng nếu engine không có functional index hoặc phép biến đổi tương đương.

Một dạng thường thân thiện hơn với index:

~~~text
where createdAt >= :dayStart
  and createdAt < :nextDayStart
~~~

### 13.4. Khoảng thời gian tương đối

DSL có thể hỗ trợ:

~~~text
where createdAt >= now() - duration("7 days")
~~~

Nếu now() được đánh giá nhiều lần hoặc ở nhiều node, cần quy định có dùng cùng một clock snapshot cho toàn truy vấn hay không.

### 13.5. Timestamp và precision

Nguồn dữ liệu có thể lưu millisecond, microsecond hoặc nanosecond. Khi chuyển đổi parameter, engine cần xác định cách làm tròn và so sánh để tránh bỏ sót hoặc trùng bản ghi ở ranh giới.

## 14. Kiểu dữ liệu, ép kiểu và semantics của predicate

Điều kiện lọc chỉ đáng tin cậy khi kiểu dữ liệu được xác định rõ.

### 14.1. Type checking

~~~text
where total > "500"
~~~

Nếu total là Decimal còn "500" là String, type checker nên báo lỗi hoặc yêu cầu conversion tường minh.

### 14.2. Implicit coercion

Một số DSL cho phép ép kiểu ngầm. Ví dụ Integer có thể được chuyển sang Decimal khi so sánh. Quy tắc cần xác định:
- Kiểu đích.
- Có mất precision không.
- Có overflow không.
- Có phụ thuộc locale không.
- Null được xử lý thế nào.

### 14.3. Decimal và floating point

Số tiền nên dùng kiểu decimal có precision xác định thay vì binary floating point nếu nghiệp vụ yêu cầu so sánh chính xác. Sai số biểu diễn có thể khiến giá trị ở ranh giới không được lọc như mong muốn.

### 14.4. Enum

~~~text
where status == OrderStatus.PAID
~~~

Enum nên được kiểm tra tại compile time nếu có thể. Truy vấn với một giá trị enum không tồn tại cần được báo lỗi rõ ràng.

### 14.5. Duration và unit

~~~text
where responseTime < 2 seconds
~~~

Nếu hai giá trị có đơn vị khác nhau, DSL cần quy tắc chuyển đổi. Không nên so sánh 2 seconds với 500 milliseconds như hai con số thuần mà bỏ qua đơn vị.

### 14.6. Collation và locale

So sánh chuỗi có thể phụ thuộc collation của database. Nếu DSL cho phép chọn collation, nó cần được thể hiện rõ trong query model để kết quả không phụ thuộc cấu hình ẩn.

## 15. Parameter hóa và an toàn truy vấn

Giá trị lọc thường đến từ người dùng hoặc ứng dụng. Ghép chuỗi trực tiếp vào query có thể dẫn đến injection.

Không an toàn:

~~~text
query = "from users where name == '" + userInput + "'"
~~~

Nếu userInput chứa ký tự đóng chuỗi hoặc cú pháp DSL, nó có thể làm thay đổi cấu trúc truy vấn.

An toàn hơn:

~~~text
from users
where name == :name
~~~

Và truyền parameter riêng:

~~~text
parameters = {
    name: userInput
}
~~~

### 15.1. Parameter binding

Parameter binding giữ query structure tách biệt với dữ liệu. Engine kiểm tra kiểu và chuyển giá trị sang backend phù hợp.

### 15.2. Identifier không phải value parameter

Parameter thường dùng cho giá trị, không thay thế tên bảng, tên cột hoặc keyword. Nếu cần chọn cột động, hãy dùng whitelist symbol đã được phân giải thay vì ghép chuỗi tùy ý.

### 15.3. Kiểm tra quyền truy cập

Một query hợp lệ về cú pháp vẫn có thể truy cập dữ liệu người dùng không được phép xem. Authorization cần được áp dụng ở tầng query engine hoặc data service, không chỉ dựa vào predicate do client gửi.

### 15.4. Row-level security

Một hệ thống có thể thêm predicate bảo mật tự động, ví dụ tenantId == currentTenant. Cần đảm bảo user không thể ghi đè hoặc loại bỏ điều kiện bảo mật bằng cách tạo OR ở cấp cao hơn.

Một cách an toàn là engine kết hợp predicate người dùng và predicate bảo mật trong AST:

~~~text
AND(
    userPredicate,
    tenantPredicate
)
~~~

Không nên nối chuỗi điều kiện bằng cách đặt thêm một đoạn văn bản ở cuối query mà không kiểm soát precedence.

### 15.5. Giới hạn query

Có thể giới hạn:
- Số lượng parameter.
- Kích thước danh sách IN.
- Độ sâu subquery.
- Số lượng join.
- Thời gian thực thi.
- Số hàng trả về.
- Độ phức tạp regex.

## 16. Tối ưu hóa điều kiện lọc

Một query engine có thể biến predicate thành kế hoạch thực thi khác nhau. Người viết DSL mô tả điều kiện; optimizer chọn cách thực hiện.

### 16.1. Predicate pushdown

Đẩy điều kiện xuống gần nguồn dữ liệu giúp giảm số hàng phải chuyển qua các bước sau.

Ví dụ:

~~~text
from orders
join customers on orders.customerId == customers.id
where orders.status == "PAID"
select orders.id, customers.name
~~~

Nếu an toàn, engine có thể lọc orders trước khi join.

### 16.2. Index scan và table scan

Table scan đọc nhiều hoặc toàn bộ hàng. Index scan dùng cấu trúc chỉ mục để tìm vùng dữ liệu phù hợp.

Điều kiện:

~~~text
where customerId == :id
~~~

có thể dùng index trên customerId nếu có và nếu optimizer thấy có lợi.

### 16.3. Range scan

Index có thể hỗ trợ khoảng:

~~~text
where createdAt >= :start
  and createdAt < :end
~~~

Engine có thể đọc một đoạn liên tục trong index thay vì quét toàn bộ bảng.

### 16.4. Composite index

Một index ghép trên (status, createdAt) có thể hữu ích cho truy vấn lọc status bằng equality và createdAt bằng range.

Thứ tự cột trong composite index ảnh hưởng khả năng sử dụng. Không phải mọi thứ tự predicate trong query đều quyết định index; optimizer xem xét cấu trúc index và selectivity.

### 16.5. Selectivity

Selectivity cho biết điều kiện giữ lại tỷ lệ bao nhiêu hàng. Điều kiện rất chọn lọc (ví dụ ID duy nhất) thường giảm dữ liệu nhiều hơn điều kiện ít chọn lọc (ví dụ active = true nếu hầu hết hàng đều active).

### 16.6. Sắp xếp điều kiện

Trong logic thuần, A AND B có thể tương đương B AND A. Nhưng engine không nhất thiết đánh giá theo thứ tự văn bản. Nếu DSL cho phép function có side effect hoặc có thể ném lỗi, việc sắp xếp điều kiện có thể thay đổi hành vi. Vì vậy, predicate dùng cho query nên ưu tiên pure và total function.

### 16.7. SARGable predicate

Predicate có thể tận dụng index thường được gọi là SARGable. Ví dụ so sánh cột trực tiếp với parameter thường dễ tối ưu hơn áp dụng hàm lên cột.

Có index trên email:
~~~text
where email == :email
~~~

Có thể khó dùng index thường:
~~~text
where lower(email) == lower(:email)
~~~

Có thể cần functional index hoặc cột normalized riêng.

### 16.8. Explain plan

Workbench hoặc query tool có thể hiển thị kế hoạch:
- Scan type.
- Index được chọn.
- Số hàng ước tính.
- Số hàng thực tế.
- Filter node.
- Join strategy.
- Cost và thời gian.

Kế hoạch giúp hiểu vì sao một predicate chậm và index có thực sự được sử dụng không.

## 17. Lọc dữ liệu trong truy vấn lồng và subquery

Subquery là truy vấn nằm trong truy vấn khác. Predicate bên trong có thể tham chiếu giá trị từ truy vấn ngoài, tạo correlated subquery.

### 17.1. Subquery không tương quan

~~~text
from orders
where customerId in (
    from vipCustomers
    select id
)
select id, total
~~~

Subquery vipCustomers có thể được tính độc lập tùy optimizer.

### 17.2. Correlated subquery

~~~text
from customers
where exists (
    from orders
    where orders.customerId == customers.id
      and orders.total > 1000000
)
select id, name
~~~

Subquery tham chiếu customers.id của hàng ngoài.

### 17.3. Scope của tên

DSL cần quy định:
- Tên nào thuộc query trong.
- Tên nào được capture từ query ngoài.
- Cách xử lý tên trùng.
- Alias có bắt buộc không.
- Có thể tham chiếu nhiều cấp query lồng nhau không.

### 17.4. Decorrelate

Optimizer có thể chuyển correlated subquery thành join hoặc semi-join nếu tương đương. Việc này cần bảo toàn null semantics và multiplicity.

## 18. Lọc dữ liệu phân trang

Ứng dụng thường không muốn tải toàn bộ kết quả. Pagination kết hợp lọc và sắp xếp để trả một phần dữ liệu.

### 18.1. Limit và offset

~~~text
from products
where category == :category
order by name
limit 20
offset 40
~~~

Truy vấn trả 20 hàng bắt đầu từ vị trí 40 trong thứ tự kết quả.

### 18.2. ORDER BY là cần thiết

Nếu không có thứ tự ổn định, trang 1 và trang 2 có thể trùng hoặc thiếu hàng khi nguồn dữ liệu thay đổi. Pagination nên có ORDER BY với khóa phân biệt đủ để xác định thứ tự.

### 18.3. Keyset pagination

Thay vì offset, có thể dùng giá trị khóa cuối trang trước:

~~~text
from products
where category == :category
  and (name, id) > (:lastName, :lastId)
order by name, id
limit 20
~~~

Cú pháp tuple comparison tùy DSL. Keyset pagination thường ổn định và hiệu quả hơn offset trên dữ liệu lớn, nếu có index phù hợp.

### 18.4. Lọc trước pagination

Predicate lọc phải được áp dụng theo semantics truy vấn trước khi chọn trang. Nếu phân trang trước rồi mới lọc ở client, trang có thể thiếu dữ liệu và số trang không chính xác.

### 18.5. Count query

UI có thể cần tổng số hàng thỏa predicate. Count nên dùng cùng điều kiện lọc và cùng quyền truy cập để tránh hiển thị số lượng không khớp với danh sách.

## 19. Lọc trên dữ liệu streaming và sự kiện

Không phải nguồn dữ liệu nào cũng là bảng có thể quét lại. Với event stream, dữ liệu đến liên tục.

### 19.1. Filter operator

~~~text
events
    .filter(event => event.type == "PAYMENT")
    .filter(event => event.amount > 100000)
~~~

Mỗi event được kiểm tra khi đến. Event không thỏa điều kiện có thể bị loại ngay.

### 19.2. Event time và processing time

- Event time: thời điểm sự kiện thực sự xảy ra.
- Processing time: thời điểm hệ thống nhận hoặc xử lý sự kiện.

Lọc theo event time phù hợp khi dữ liệu có thể đến trễ. Lọc theo processing time phù hợp với một số chính sách vận hành nhưng kết quả có thể phụ thuộc tốc độ hệ thống.

### 19.3. Windowed filtering

Có thể lọc trong cửa sổ thời gian:

~~~text
from events
window tumbling(5 minutes)
where severity >= 3
group by source
select source, count(*)
~~~

Window xác định nhóm sự kiện được xử lý cùng nhau. Predicate có thể áp dụng trước hoặc sau window tùy mục tiêu.

### 19.4. Late events

Sự kiện đến trễ có thể thuộc window đã đóng. Engine cần quy định watermark, allowed lateness và cách cập nhật kết quả đã phát.

### 19.5. Backpressure

Nếu nguồn phát nhanh hơn khả năng lọc, hệ thống cần backpressure, buffering hoặc drop policy. Lọc không làm giảm tải nếu mọi event vẫn phải deserialize hoặc tính toán phức tạp trước khi bị loại.

## 20. Lọc dữ liệu trong document và JSON DSL

Với dữ liệu JSON hoặc document, predicate có thể truy cập trường lồng nhau và phần tử mảng.

Ví dụ:

~~~text
from products
where document.category == "BOOK"
  and document.attributes.language == "vi"
select document.title
~~~

### 20.1. Field tồn tại và field null

Cần phân biệt:
- Field không tồn tại.
- Field tồn tại với null.
- Field tồn tại với giá trị rỗng.
- Field tồn tại nhưng sai kiểu.

Một DSL có thể cung cấp exists(field), isMissing(field) hoặc isNull(field).

### 20.2. Mảng

~~~text
where any(document.tags, tag => tag == "dsl")
~~~

Cần quy định nếu tags bị thiếu hoặc null thì ANY trả false, unknown hay lỗi.

### 20.3. Path expression

Một path như document.customer.address.city cần quy định hành vi khi một phần tử trung gian không tồn tại hoặc null.

### 20.4. Schema validation

Nếu document có schema, query analyzer có thể kiểm tra field path và kiểu trước khi chạy. Nếu dữ liệu schema-less, engine có thể phải xử lý runtime type error hoặc missing value.

## 21. Lọc dữ liệu và bảo mật

Lọc dữ liệu thường là một phần của chính sách truy cập. Predicate có thể giới hạn hàng mà một người dùng được phép xem.

### 21.1. Authorization predicate

Ví dụ hệ thống đa tenant:

~~~text
where tenantId == :currentTenant
~~~

Điều kiện tenant phải được engine kiểm soát. Client không nên có khả năng xóa nó bằng cách sửa query.

### 21.2. Row-level security

Row-level security áp dụng predicate theo user, role hoặc tenant. Có thể kết hợp:
- Predicate từ người dùng.
- Predicate quyền truy cập.
- Predicate soft-delete.
- Predicate theo thời gian hiệu lực.

Các predicate hệ thống cần được nhóm bằng AST để đảm bảo precedence đúng.

### 21.3. Soft delete

~~~text
where deletedAt is null
~~~

Nếu mọi query đều phải bỏ qua bản ghi đã xóa mềm, engine có thể áp dụng điều kiện mặc định. Cần có cơ chế rõ để truy vấn audit hoặc restore được phép xem dữ liệu đã xóa.

### 21.4. Tránh rò rỉ qua error message

Nếu predicate tham chiếu field không được phép, diagnostic không nên tiết lộ tên hoặc giá trị dữ liệu bí mật ngoài phạm vi quyền.

### 21.5. Cost control

Người dùng không được phép gửi regex cực nặng, subquery quá sâu hoặc list parameter rất lớn để làm cạn tài nguyên. Query engine cần giới hạn cost và timeout.

## 22. Thiết kế AST cho điều kiện lọc

Một query DSL nên biểu diễn predicate bằng AST có kiểu, thay vì giữ toàn bộ điều kiện dưới dạng chuỗi.

Ví dụ:

~~~text
And(
    Equal(
        Column("status"),
        Parameter("status")
    ),
    GreaterThan(
        Column("total"),
        Parameter("minimumTotal")
    )
)
~~~

### 22.1. Node predicate

Một tập node có thể gồm:
- Comparison.
- LogicalAnd.
- LogicalOr.
- LogicalNot.
- IsNull.
- InList.
- Between.
- Like/Regex.
- Exists.
- FunctionPredicate.
- Parameter.
- ColumnReference.

### 22.2. Type checking

Mỗi node có thể có kiểu đầu ra Boolean hoặc NullableBoolean. Type checker xác định hai toán hạng có tương thích hay không và phép so sánh có được hỗ trợ không.

### 22.3. Constant folding

Điều kiện hằng có thể được tính trước:

~~~text
where 10 > 5 and status == "PAID"
~~~

Optimizer có thể rút gọn phần 10 > 5 thành TRUE. Nhưng cần giữ null semantics và không đánh giá sớm function phụ thuộc runtime.

### 22.4. Predicate simplification

Một số luật:
- TRUE AND P -> P
- FALSE AND P -> FALSE
- TRUE OR P -> TRUE
- FALSE OR P -> P

Với UNKNOWN, phải dùng truth table ba giá trị. Ví dụ UNKNOWN AND FALSE là FALSE, còn UNKNOWN OR TRUE là TRUE.

### 22.5. Canonical form

Engine có thể chuẩn hóa predicate để so sánh, cache hoặc tạo execution plan. Không nên thay đổi thứ tự điều kiện nếu semantics của DSL cho phép side effect hoặc exception quan sát được.

## 23. Xử lý lỗi và diagnostic của điều kiện lọc

Query analyzer nên đưa ra thông báo rõ ràng trước khi chạy nếu có thể.

Ví dụ lỗi:
- Unknown column.
- Operator không hỗ trợ cho kiểu dữ liệu.
- Parameter chưa được bind.
- So sánh Date với String.
- Aggregate xuất hiện trong WHERE khi DSL không cho phép.
- Subquery trả nhiều cột trong ngữ cảnh cần một giá trị.
- Regex không hợp lệ.

Diagnostic tốt nên có:
- Vị trí nguồn.
- Biểu thức gây lỗi.
- Kiểu mong đợi và kiểu thực tế.
- Gợi ý sửa nếu có thể.
- Mức độ lỗi.

Ví dụ:

~~~text
query.dsl:8:15: Cannot compare Decimal with String.
Expected a numeric value for parameter :minimumTotal.
~~~

Không nên trì hoãn mọi lỗi đến runtime nếu schema và kiểu đã biết ở compile time.

## 24. Kiểm thử điều kiện lọc

Kiểm thử lọc nên xác nhận cả kết quả và semantics ở các trường hợp biên.

### 24.1. Kiểm thử toán tử đơn

Tạo dữ liệu ngay dưới, đúng bằng và ngay trên ngưỡng để kiểm tra <, <=, > và >=.

Ví dụ với điều kiện total >= 100:
- 99 phải bị loại.
- 100 phải được giữ.
- 101 phải được giữ.

### 24.2. Kiểm thử logic kết hợp

Kiểm tra AND, OR, NOT với mọi tổ hợp true/false và các trường hợp null nếu hỗ trợ three-valued logic.

### 24.3. Kiểm thử NULL

Bao gồm:
- Cột null.
- Cột không tồn tại.
- Parameter null.
- NULL trong IN list.
- NOT IN có NULL.
- COALESCE.
- EXISTS trên dữ liệu thiếu.

### 24.4. Kiểm thử kiểu và precision

Kiểm tra:
- Integer và Decimal.
- Overflow.
- Floating point.
- Tiền tệ và đơn vị.
- Ngày giờ có timezone.
- String collation.
- Enum không hợp lệ.

### 24.5. Kiểm thử JOIN

So sánh kết quả của điều kiện trong ON và WHERE với INNER JOIN và LEFT JOIN. Dùng dữ liệu không có bản ghi liên quan để phát hiện thay đổi semantics.

### 24.6. Kiểm thử GROUP BY và HAVING

Tạo nhóm rỗng, nhóm có một hàng, nhóm có nhiều hàng và nhóm có aggregate null. Xác nhận WHERE lọc hàng trước khi nhóm và HAVING lọc nhóm sau aggregate.

### 24.7. Kiểm thử parameter và injection

Truyền chuỗi chứa dấu nháy, ký tự wildcard và đoạn giống cú pháp DSL. Xác nhận nó vẫn được xử lý như dữ liệu, không biến thành một phần query syntax.

### 24.8. Kiểm thử pagination

Dùng nhiều hàng có cùng sort key để xác nhận thứ tự ổn định. Thử thêm/xóa hàng giữa các trang để đánh giá offset và keyset pagination.

### 24.9. Kiểm thử hiệu năng

Đo với:
- Table scan.
- Index scan.
- Predicate có selectivity cao và thấp.
- IN list lớn.
- Subquery tương quan.
- Regex.
- Nhiều điều kiện kết hợp.
- Dataset có phân bố lệch.

### 24.10. Property-based tests

Sinh tập dữ liệu và predicate, rồi so sánh kết quả engine với một evaluator tham chiếu có cùng semantics. Điều này hữu ích để phát hiện lỗi trong null logic và optimizer rewrite.

## 25. Những lỗi thường gặp khi viết query filter

### 25.1. Dùng AND và OR mà không có ngoặc

~~~text
where status == "PAID" or status == "NEW" and total > 100
~~~

Nếu AND có precedence cao hơn OR, biểu thức không có nghĩa “một trong hai status và total > 100”. Hãy nhóm điều kiện:

~~~text
where (status == "PAID" or status == "NEW")
  and total > 100
~~~

### 25.2. So sánh với NULL bằng dấu bằng

~~~text
where deletedAt == null
~~~

Nếu DSL theo SQL semantics, biểu thức có thể trả UNKNOWN. Dùng IS NULL.

### 25.3. NOT IN chứa NULL

Một danh sách có NULL có thể làm kết quả không như dự kiến. Kiểm tra và xử lý null trước khi dùng NOT IN.

### 25.4. Đặt điều kiện outer join sai vị trí

Đưa điều kiện của bảng bên phải từ ON sang WHERE có thể loại các hàng không có bản ghi ghép, biến hiệu ứng LEFT JOIN thành INNER JOIN.

### 25.5. Chuyển đổi cột trong điều kiện

Dùng hàm lên cột có thể khiến index không được tận dụng. Xem xét range predicate hoặc functional index.

### 25.6. Lọc sau pagination ở client

Lọc sau khi lấy một trang khiến trang thiếu hàng và count sai. Hãy để query engine lọc trước khi phân trang.

### 25.7. Ghép chuỗi query từ input

Ghép input vào query text có thể dẫn đến injection. Dùng parameter binding.

### 25.8. Quên điều kiện tenant hoặc quyền

Một predicate lọc nghiệp vụ không thay thế authorization. Quyền phải được kiểm tra ở tầng có thể tin cậy.

### 25.9. Dùng hàm không xác định trong predicate

Hàm phụ thuộc thời gian, random hoặc trạng thái bên ngoài có thể làm query cho kết quả khác nhau giữa các lần chạy. Xác định snapshot hoặc truyền parameter rõ ràng.

### 25.10. Bỏ qua kế hoạch thực thi

Một predicate đúng nhưng không có index phù hợp có thể quét toàn bộ dữ liệu. Dùng explain plan và số liệu thực tế để xác định bottleneck.

## 26. Quy trình thiết kế và tối ưu bộ lọc

Một quy trình thực tế:

1. Xác định tập dữ liệu và schema.
2. Xác định chính xác hàng hoặc nhóm cần giữ.
3. Viết predicate rõ ràng, dùng ngoặc khi kết hợp nhiều điều kiện.
4. Xác định semantics NULL, missing và collection rỗng.
5. Kiểm tra kiểu dữ liệu, đơn vị, precision, timezone và collation.
6. Dùng parameter binding cho mọi giá trị từ bên ngoài.
7. Phân biệt điều kiện WHERE, ON, HAVING và aggregate FILTER.
8. Xem xét JOIN, EXISTS và subquery có phù hợp không.
9. Thêm ORDER BY ổn định trước pagination.
10. Đọc explain plan để xem scan, index và predicate pushdown.
11. Kiểm thử dữ liệu biên, null, quyền truy cập và injection.
12. Đo hiệu năng trên dữ liệu có phân bố gần với production.

## 27. Ví dụ tổng hợp: lọc đơn hàng cho báo cáo

Yêu cầu: tìm các đơn đã thanh toán trong một khoảng thời gian, thuộc một số khu vực được chọn, có tổng tiền từ ngưỡng trở lên và khách hàng đang hoạt động. Chỉ trả về các đơn mới nhất theo thời gian.

Query DSL minh họa:

~~~text
from orders
join customers
    on orders.customerId == customers.id
where orders.status == OrderStatus.PAID
  and orders.createdAt >= :startTime
  and orders.createdAt < :endTime
  and orders.region in :regions
  and orders.total >= :minimumTotal
  and customers.active == true
select
    orders.id,
    orders.customerId,
    customers.name,
    orders.createdAt,
    orders.total
order by orders.createdAt descending, orders.id descending
limit :pageSize
~~~

### 27.1. Parameter

Các parameter có thể gồm:
- startTime: thời điểm bắt đầu đã xác định timezone.
- endTime: thời điểm kết thúc.
- regions: danh sách vùng.
- minimumTotal: Decimal có đơn vị tiền tệ phù hợp.
- pageSize: số hàng tối đa được phép trả về.

### 27.2. Semantics

WHERE lọc các đơn và khách hàng. INNER JOIN chỉ giữ đơn có khách hàng tương ứng. ORDER BY tạo thứ tự ổn định nhờ thêm orders.id làm tie-breaker. LIMIT giới hạn số hàng sau khi lọc và sắp xếp.

### 27.3. Tối ưu hóa

Engine có thể:
- Dùng index trên status và createdAt.
- Dùng index phù hợp cho customerId.
- Đẩy predicate orders xuống trước join.
- Dùng semi-join hoặc chiến lược join phù hợp.
- Chỉ đọc các cột cần cho kết quả và điều kiện.

Index cụ thể phụ thuộc phân bố dữ liệu và workload. Không thể khẳng định một index duy nhất luôn tối ưu.

### 27.4. Kiểm thử

Tạo dữ liệu gồm:
- Đơn PAID và UNPAID.
- Đơn ở hai thời điểm ranh giới.
- Đơn ở vùng được chọn và ngoài vùng.
- Đơn dưới, bằng và trên minimumTotal.
- Khách hàng active và inactive.
- Hai đơn có cùng createdAt để kiểm tra tie-breaker.
- Khách hàng hoặc vùng bị thiếu nếu schema cho phép null.

## 28. Bài tập tự kiểm tra

### Bài 1: Predicate cơ bản

Viết truy vấn tìm sản phẩm còn hàng, có giá từ 100 đến dưới 500 và thuộc category BOOK. Giải thích vì sao dùng khoảng nửa mở.

### Bài 2: Kết hợp logic

Một người dùng được phép xem đơn nếu là owner hoặc là manager của khu vực, nhưng chỉ xem đơn chưa bị xóa. Viết predicate có dấu ngoặc rõ ràng.

### Bài 3: NULL semantics

Một cột shippedAt có thể null. So sánh kết quả của shippedAt == null và shippedAt is null trong DSL dùng three-valued logic.

### Bài 4: NOT IN

Một truy vấn loại trừ các customerId trong danh sách có thể chứa null. Giải thích vì sao NOT IN có thể trả kết quả bất ngờ và đề xuất cách xử lý.

### Bài 5: WHERE và HAVING

Tìm khách hàng có ít nhất ba đơn PAID và tổng doanh thu PAID vượt một triệu. Hãy xác định điều kiện nào thuộc WHERE, điều kiện nào thuộc HAVING.

### Bài 6: LEFT JOIN

Tìm mọi khách hàng cùng các đơn PAID nếu có, kể cả khách hàng không có đơn. Hãy đặt điều kiện status ở đâu và giải thích kết quả nếu đặt trong WHERE.

### Bài 7: Parameterization

Một truy vấn tìm email theo input người dùng. Hãy viết query có parameter và giải thích vì sao nối chuỗi input vào query không an toàn.

### Bài 8: Pagination

Một danh sách sản phẩm sắp xếp theo name có nhiều sản phẩm trùng tên. Hãy thiết kế ORDER BY và keyset pagination để không bỏ sót hoặc lặp hàng.

### Bài 9: Query optimization

Predicate lower(email) == lower(:email) không dùng index thông thường. Hãy đề xuất các phương án như normalized column hoặc functional index và nêu trade-off.

### Bài 10: Kiểm thử

Thiết kế dữ liệu và test cho predicate kết hợp AND/OR/NOT, null, IN, JOIN, HAVING, timezone và row-level security. Nêu các trường hợp biên quan trọng.

## Kết luận

Lọc dữ liệu là thành phần trung tâm của DSL truy vấn. Predicate mô tả hàng hoặc nhóm nào được giữ lại, còn query engine chuyển điều kiện đó thành cách thực thi phù hợp. Để truy vấn đúng, người thiết kế cần hiểu toán tử so sánh, logic kết hợp, NULL và logic ba giá trị, kiểu dữ liệu, collection, JOIN, GROUP BY và thời gian. Để truy vấn an toàn, cần parameter binding, authorization và row-level security. Để truy vấn hiệu quả, cần xem xét index, selectivity, predicate pushdown, pagination và execution plan. Việc kiểm thử dữ liệu biên, null semantics, join, parameter và hiệu năng giúp bộ lọc hoạt động đúng trong các tình huống thực tế và khi dữ liệu tăng lên.

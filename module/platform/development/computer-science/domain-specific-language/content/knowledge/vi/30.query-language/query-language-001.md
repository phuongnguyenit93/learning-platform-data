# Mục tiêu của DSL truy vấn

## 1. DSL truy vấn là gì?

DSL truy vấn (query Domain-Specific Language) là ngôn ngữ được thiết kế để mô tả việc tìm kiếm, lọc, kết hợp, nhóm, sắp xếp và biến đổi dữ liệu trong một miền cụ thể. Thay vì phải diễn đạt mọi thao tác bằng API tổng quát hoặc câu lệnh của một hệ quản trị dữ liệu, người dùng có thể dùng các cấu trúc gần với cách họ hiểu dữ liệu và câu hỏi nghiệp vụ.

Ví dụ, một DSL dành cho dữ liệu bán hàng có thể viết:

~~~text
from Orders
where status == APPROVED
  and total > money(1000000, VND)
select orderId, customerId, total
order by total descending
limit 20
~~~

Truy vấn mô tả tập đơn hàng đã được duyệt có tổng tiền lớn hơn một ngưỡng, chỉ lấy một số trường và sắp xếp theo tổng tiền. Query engine có thể chuyển biểu thức này thành SQL, truy vấn document database, truy vấn dịch vụ hoặc một execution plan khác.

Một DSL truy vấn không nhất thiết phải là một ngôn ngữ hoàn chỉnh như SQL. Nó có thể chỉ cung cấp một tập phép toán giới hạn cho một loại dữ liệu hoặc một use case, chẳng hạn lọc log, tìm kiếm sản phẩm, truy vấn graph, phân tích sự kiện hoặc đọc dữ liệu từ một API.

## 2. Mục tiêu cốt lõi của DSL truy vấn

Mục tiêu trung tâm là cho phép người dùng diễn đạt **dữ liệu họ cần và cách họ muốn biến đổi dữ liệu** bằng một mô hình rõ ràng, dễ kiểm tra và có thể thực thi hiệu quả.

Một query DSL được thiết kế tốt thường hướng tới các mục tiêu:

1. Diễn đạt câu hỏi dữ liệu bằng thuật ngữ của miền.
2. Tách ý định truy vấn khỏi chi tiết lưu trữ hoặc backend.
3. Cung cấp cú pháp nhất quán cho filter, projection, join, grouping và ordering.
4. Phát hiện lỗi tên trường, kiểu dữ liệu và phép toán trước khi chạy nếu có thể.
5. Cho phép engine tối ưu kế hoạch thực thi.
6. Kiểm soát quyền truy cập, dữ liệu nhạy cảm và chi phí truy vấn.
7. Kết hợp truy vấn nhỏ thành pipeline có thể đọc và tái sử dụng.
8. Hỗ trợ nhiều công cụ như editor, completion, diagnostics và documentation.
9. Duy trì ngữ nghĩa ổn định khi backend hoặc schema thay đổi.
10. Tạo kết quả có thể giải thích, theo dõi và kiểm thử.

Các mục tiêu này có thể xung đột. Một cú pháp rất ngắn có thể khó mở rộng; một DSL hỗ trợ quá nhiều backend có thể phải giới hạn tính năng; một truy vấn linh hoạt có thể khó kiểm soát chi phí. Thiết kế cần xác định ưu tiên theo miền sử dụng.

## 3. Diễn đạt câu hỏi bằng ngôn ngữ miền

Người dùng thường suy nghĩ theo khái niệm nghiệp vụ hơn là bảng, cột, index hoặc tên collection. Query DSL có thể đưa các khái niệm đó vào cú pháp.

Ví dụ trong miền thương mại:

~~~text
from Orders
where customer.isActive
  and orderDate during currentMonth()
select customer, total
~~~

Người viết tập trung vào Orders, customer, orderDate và total. Schema hoặc mapping layer chịu trách nhiệm xác định chúng tương ứng với bảng, cột, quan hệ hoặc API nào.

Trong miền quan sát hệ thống, một query DSL có thể dùng:

~~~text
from Logs
where severity >= WARN
  and service == "payment"
group by service
count
~~~

Người vận hành mô tả loại log cần xem và cách tổng hợp mà không cần biết dữ liệu được lưu trong partition nào.

### 3.1. Thuật ngữ có ý nghĩa nghiệp vụ

Tên trong DSL nên phản ánh vocabulary mà người dùng miền hiểu. Nếu người dùng nói "đơn hàng quá hạn", query DSL có thể cung cấp thuộc tính hoặc predicate overdue thay vì bắt họ tự viết điều kiện phức tạp trên nhiều cột thời gian.

Tuy nhiên, abstraction này phải có định nghĩa chính xác. overdue cần xác định mốc thời gian, timezone, trạng thái đơn hàng và cách xử lý dữ liệu thiếu. Tên gần với nghiệp vụ nhưng không có semantics rõ sẽ tạo cảm giác dễ dùng mà kết quả khó dự đoán.

### 3.2. Một miền có thể có nhiều góc nhìn

Người phân tích dữ liệu, developer và operator có thể dùng cùng dữ liệu nhưng đặt câu hỏi khác nhau. DSL có thể cung cấp các view hoặc entity theo vai trò:

- Analyst truy vấn metric và dimension.
- Developer truy vấn entity và quan hệ.
- Operator lọc log, event và trạng thái workflow.

Các view này có thể dùng chung query engine nhưng cung cấp vocabulary và quyền truy cập khác nhau.

## 4. Tách ý định truy vấn khỏi cách lưu trữ

Một mục tiêu quan trọng là không buộc người dùng biết mọi chi tiết của backend. Query DSL có thể định nghĩa một mô hình dữ liệu logic và ánh xạ mô hình đó tới các nguồn dữ liệu vật lý.

Ví dụ:

~~~text
from CustomerOrders
where customerId == "C-1024"
select orderId, total, status
~~~

Trong backend quan hệ, CustomerOrders có thể được triển khai bằng JOIN giữa bảng customer và orders. Trong backend document, nó có thể là một collection hoặc một aggregation pipeline. Trong service API, engine có thể gọi endpoint rồi lọc phần dữ liệu được phép.

Tách biệt này đem lại:

- Cùng một query có thể chạy trên nhiều backend nếu chúng hỗ trợ cùng semantics.
- Schema vật lý có thể thay đổi mà query source không cần đổi.
- Người dùng tập trung vào logic dữ liệu thay vì cấu trúc lưu trữ.
- Engine có thể chọn cách thực thi phù hợp với backend.

Tuy nhiên, tính độc lập backend không phải miễn phí. Một số backend không hỗ trợ cùng phép toán, kiểu dữ liệu hoặc transaction. DSL cần công bố capability và giới hạn thay vì giả vờ mọi query đều chạy giống nhau ở mọi nơi.

## 5. Khai báo điều cần lấy thay vì mô tả từng bước

Nhiều query DSL sử dụng phong cách khai báo (declarative). Người viết mô tả kết quả mong muốn, còn engine quyết định cách thực hiện.

Ví dụ:

~~~sql
SELECT customer_id, SUM(total)
FROM orders
WHERE status = 'APPROVED'
GROUP BY customer_id;
~~~

Truy vấn nói cần tổng tiền theo khách hàng cho các đơn đã duyệt. Nó không chỉ định phải đọc file nào trước, dùng index nào, chia partition ra sao hoặc thực hiện phép tổng hợp ở node nào.

Một query DSL riêng có thể biểu diễn cùng ý định:

~~~text
from Orders
where status == APPROVED
group by customerId
aggregate totalAmount = sum(total)
select customerId, totalAmount
~~~

Query optimizer có thể thay đổi thứ tự filter, chọn index hoặc đẩy phép toán xuống database miễn là kết quả quan sát được vẫn theo semantics của DSL.

### 5.1. Declarative và imperative

| Khía cạnh | Declarative query | Imperative procedure |
|---|---|---|
| Người viết mô tả | Kết quả hoặc quan hệ cần có | Các bước phải thực hiện |
| Quyền tối ưu | Engine có nhiều quyền chọn execution plan | Trình tự thường do người viết chỉ định |
| Độ dễ đọc | Thường gần với câu hỏi dữ liệu | Có thể chi tiết hơn |
| Kiểm soát bước chạy | Thấp hơn ở cấp cú pháp | Cao hơn |
| Ví dụ | Lọc đơn hàng theo trạng thái | Mở cursor, đọc từng dòng, kiểm tra và thêm vào list |

Query DSL có thể kết hợp cả hai phong cách. Một số use case cần pipeline từng bước hoặc xử lý streaming; khi đó cần phân biệt các bước biến đổi logic với các chỉ thị điều khiển runtime.

## 6. Biểu đạt các phép toán truy vấn cơ bản

Một query DSL cần chọn tập phép toán cốt lõi theo miền. Với dữ liệu dạng quan hệ hoặc collection, các phép toán thường gặp:

### 6.1. Source hoặc FROM

Chỉ định tập dữ liệu đầu vào:

~~~text
from Orders
~~~

Source có thể là bảng, collection, view, event stream, file, API endpoint hoặc một query con.

### 6.2. Filter hoặc WHERE

Chọn phần tử thỏa điều kiện:

~~~text
where status == APPROVED and total > threshold
~~~

Predicate nên có quy tắc kiểu và null rõ ràng. Không nên để giá trị thiếu tự động được coi là false hoặc true mà không có semantics được công bố.

### 6.3. Projection hoặc SELECT

Chỉ chọn các trường cần thiết:

~~~text
select orderId, customerId, total
~~~

Projection giảm dữ liệu phải truyền và làm rõ đầu ra của query. Nó cũng có thể giới hạn dữ liệu nhạy cảm nếu schema và policy hỗ trợ.

### 6.4. Ordering

Sắp xếp kết quả:

~~~text
order by createdAt descending, orderId ascending
~~~

Nếu nhiều phần tử có cùng giá trị sort key, kết quả có thể không ổn định trừ khi có tie-breaker. DSL nên cho phép chỉ định thứ tự phụ khi tính xác định quan trọng.

### 6.5. Limit và pagination

Giới hạn số kết quả:

~~~text
limit 50
~~~

Pagination có thể dùng offset hoặc cursor. Cursor pagination thường ổn định hơn trên tập dữ liệu lớn đang thay đổi, nhưng cần quy tắc ordering ổn định và cursor không thể bị sửa tùy ý.

### 6.6. Grouping và aggregation

Nhóm dữ liệu và tính toán trên từng nhóm:

~~~text
from Orders
where status == APPROVED
group by customerId
aggregate orderCount = count(),
          totalValue = sum(total)
~~~

Các hàm aggregate thường gồm count, sum, average, min và max. DSL cần định nghĩa kiểu trả về, hành vi với null và cách xử lý collection rỗng.

## 7. Kết hợp dữ liệu từ nhiều nguồn

Một query DSL có thể cần biểu diễn quan hệ giữa các tập dữ liệu:

~~~text
from Orders as o
join Customers as c on o.customerId == c.id
where c.region == "NORTH"
select o.orderId, c.name, o.total
~~~

Join cho phép kết hợp thông tin từ nhiều nguồn. Tuy nhiên, join có thể làm tăng số dòng, tạo duplicate hoặc tốn tài nguyên lớn. DSL cần phân biệt inner join, left join, semi join hoặc các phép kết hợp tương ứng nếu miền yêu cầu.

### 7.1. Quan hệ và cardinality

Nếu một khách hàng có nhiều đơn hàng, join Customer với Orders tạo nhiều kết quả cho cùng customer. Tài liệu DSL nên giải thích quan hệ một-một, một-nhiều và nhiều-nhiều.

### 7.2. Cross-source query

Một query có thể kết hợp database, search index và service API. Query engine cần xác định phép toán nào có thể push down tới từng nguồn, phép toán nào phải thực hiện ở tầng trung gian và giới hạn dữ liệu truyền giữa các nguồn.

Không phải backend nào cũng hỗ trợ transaction hoặc snapshot nhất quán. Query DSL cần mô tả consistency semantics nếu một query đọc nhiều nguồn thay đổi độc lập.

## 8. Type safety và kiểm tra trước khi thực thi

Một query DSL nên phát hiện sớm các lỗi có thể xác định từ schema:

- Tên source không tồn tại.
- Field không có trong type.
- So sánh hai kiểu không tương thích.
- Gọi hàm không tồn tại.
- Dùng aggregation trên kiểu không phù hợp.
- Kết quả projection không khớp schema đầu ra.
- Dùng phép toán không được backend hỗ trợ.

Ví dụ:

~~~text
from Orders
where total > "one million"
~~~

Nếu total có kiểu Money và chuỗi không thể so sánh với Money, compiler hoặc validator nên báo lỗi trước khi gửi query tới backend.

### 8.1. Type inference

DSL có thể suy luận kiểu của biểu thức từ schema:

~~~text
from Orders
select total * 0.1 as estimatedTax
~~~

Nếu total là Money, hệ thống cần biết phép nhân với scalar tạo ra kiểu gì, scale và rounding ra sao. Type inference không nên chỉ dựa trên kiểu số tổng quát nếu miền có kiểu chuyên biệt.

### 8.2. Nullability

Field có thể nullable hoặc optional. Ví dụ:

~~~text
where shippingAddress.city == "Hanoi"
~~~

Nếu shippingAddress có thể null, DSL cần quy định phép truy cập có trả null, tạo unknown predicate hay báo lỗi. Một lựa chọn khác là yêu cầu optional access hoặc kiểm tra tồn tại rõ ràng.

## 9. Kiểu dữ liệu miền và semantics

Query DSL thường cần hỗ trợ kiểu dữ liệu mang ý nghĩa miền:

- Money và Currency.
- Date, Time, Instant và Duration.
- Identifier như CustomerId hoặc OrderId.
- GeoPoint và Distance.
- Percentage và Quantity có đơn vị.
- Enum và trạng thái nghiệp vụ.

Ví dụ:

~~~text
where total > money(500, USD)
  and distance(customer.location, store.location) < kilometers(10)
~~~

Kiểu miền giúp tránh so sánh sai đơn vị hoặc nhầm lẫn giá trị. DSL cần định nghĩa:

- Quy tắc so sánh.
- Phép cộng, trừ, nhân, chia.
- Chuyển đổi đơn vị.
- Precision và rounding.
- Timezone và calendar semantics.
- Cách serialize literal.

Một query DSL dành cho dữ liệu tài chính không nên âm thầm so sánh tiền ở hai currency khác nhau. Nó có thể yêu cầu chuyển đổi tường minh hoặc dùng currency context đã được xác định.

## 10. Composability và tái sử dụng truy vấn

Composability là khả năng kết hợp các truy vấn hoặc phép biến đổi nhỏ thành query lớn mà vẫn giữ được cấu trúc dễ hiểu.

Ví dụ:

~~~text
let activeOrders =
    from Orders
    where status == APPROVED;

let highValueOrders =
    activeOrders
    where total > threshold;

highValueOrders
    select orderId, customerId, total
    order by total descending
~~~

Tách query thành các phần giúp:

- Tái sử dụng logic filter.
- Đặt tên cho tập dữ liệu trung gian.
- Kiểm thử từng bước.
- Giảm lặp biểu thức.
- Tổ chức query lớn theo module.

### 10.1. Query pipeline

Một DSL có thể biểu diễn các phép biến đổi theo pipeline:

~~~text
Orders
    |> filter(status == APPROVED)
    |> filter(total > threshold)
    |> groupBy(customerId)
    |> aggregate(totalValue = sum(total))
    |> sortBy(totalValue descending)
~~~

Pipeline cho thấy dữ liệu đi qua các phép biến đổi theo thứ tự. Tuy vậy, nếu DSL mang tính declarative, thứ tự viết có thể không phải thứ tự thực thi vật lý. Engine vẫn có thể tối ưu khi bảo toàn semantics.

### 10.2. Named query và module

Query thường dùng có thể được đặt tên và export:

~~~text
query approvedOrders(minimum: Money) {
    from Orders
    where status == APPROVED and total >= minimum
}
~~~

Named query có thể được gọi lại ở nhiều nơi, được tài liệu hóa và kiểm tra kiểu như một function. Cần định nghĩa parameter binding và cách tránh ghép chuỗi nguồn vào query.

## 11. Abstraction và tái sử dụng logic miền

Một mục tiêu của query DSL là đóng gói logic lặp lại thành abstraction có tên và hợp đồng rõ ràng.

Ví dụ:

~~~text
predicate isOverdue(invoice: Invoice, at: Instant) {
    invoice.dueDate < at and invoice.status != PAID
}

from Invoices
where isOverdue(invoice, now())
select invoice.id, invoice.dueDate
~~~

Predicate isOverdue gom quy tắc nghiệp vụ vào một nơi. Khi định nghĩa overdue thay đổi, các truy vấn sử dụng predicate có thể được cập nhật đồng bộ.

Abstraction có thể là:

- Named query.
- Reusable predicate.
- View hoặc derived dataset.
- Function có kiểu.
- Macro hoặc template có giới hạn.
- Schema view theo vai trò.

Mỗi abstraction cần quy định parameter, scope, visibility, dependency và semantics. Tránh tạo abstraction quá tổng quát khiến người dùng khó hiểu hoặc optimizer không thể phân tích.

## 12. Query optimization là mục tiêu của ngôn ngữ khai báo

Một query DSL có cấu trúc cho phép engine tối ưu truy vấn dựa trên ý định thay vì phải chạy đúng từng bước do người dùng viết.

Các tối ưu hóa thường gặp:

- Predicate pushdown: đẩy filter xuống gần nguồn dữ liệu.
- Projection pushdown: chỉ đọc các field cần thiết.
- Join reordering: thay đổi thứ tự join.
- Index selection: chọn index phù hợp.
- Constant folding: tính trước biểu thức hằng.
- Common subexpression elimination: dùng lại biểu thức giống nhau khi an toàn.
- Partition pruning: bỏ qua partition không liên quan.
- Aggregation pushdown: thực hiện tổng hợp ở backend.
- Limit pushdown: giới hạn dữ liệu sớm khi semantics cho phép.

Ví dụ:

~~~text
from Orders
where region == "NORTH"
  and status == APPROVED
select orderId, total
~~~

Engine có thể chọn index theo region/status và chỉ đọc orderId, total. Người viết query không cần biết index cụ thể.

### 12.1. Bảo toàn semantics khi tối ưu

Không phải phép toán nào cũng có thể đổi thứ tự. Ví dụ, limit trước sort thường khác sort trước limit:

~~~text
sortBy(total descending)
limit 10
~~~

không tương đương với limit 10 trước rồi mới sort nếu nguồn có nhiều hơn 10 phần tử.

Các hàm có side effect, random, thời gian hiện tại hoặc kết quả không xác định cũng giới hạn khả năng tối ưu. Query DSL nên ưu tiên biểu thức thuần và khai báo rõ những phép toán không thuần.

### 12.2. Explain plan

Một query DSL hữu ích có thể cung cấp lệnh hoặc API explain để xem execution plan:

~~~text
explain {
    from Orders
    where status == APPROVED
      and total > threshold
    select orderId, total
}
~~~

Plan có thể cho biết source, index, filter, projection, join và chi phí ước lượng. Đây là công cụ giúp developer hiểu vì sao query chậm và engine dự định thực thi ra sao.

## 13. Hiệu năng và khả năng dự đoán chi phí

Query DSL nên giúp người dùng nhận biết hoặc giới hạn chi phí truy vấn. Một câu lệnh ngắn vẫn có thể quét hàng tỷ bản ghi hoặc tạo một join rất lớn.

Các cơ chế có thể cung cấp:

- Limit mặc định hoặc giới hạn tối đa.
- Query timeout.
- Scan budget hoặc cost budget.
- Giới hạn số join hoặc độ sâu query lồng.
- Giới hạn kích thước kết quả.
- Giới hạn concurrency.
- Explain plan và estimated cost.
- Cảnh báo full scan hoặc thiếu filter.

Ví dụ:

~~~text
from Events
where timestamp >= startOfDay()
  and service == "checkout"
limit 1000
options {
    timeout: 5s
    maxScan: 100000
}
~~~

Các option minh họa cần được hỗ trợ bởi runtime. Không nên hiển thị cấu hình giới hạn nhưng engine không thực sự áp dụng.

### 13.1. Pagination

Offset pagination đơn giản:

~~~text
limit 50
offset 100
~~~

Nhưng khi dữ liệu thay đổi giữa các trang, record có thể bị lặp hoặc bỏ sót. Cursor pagination dùng khóa thứ tự để tiếp tục sau phần tử cuối:

~~~text
pageSize 50
after cursor
~~~

Cursor nên được tạo và xác thực bởi engine, không nên cho client tự sửa thành một vị trí tùy ý nếu nó chứa trạng thái nội bộ.

## 14. Bảo mật và kiểm soát quyền truy cập dữ liệu

Query DSL thường là ranh giới giữa người dùng và dữ liệu. Một thiết kế tốt cần kiểm soát:

- Người dùng được truy vấn source nào.
- Field nào được đọc.
- Record nào được nhìn thấy.
- Function hoặc operator nào được gọi.
- Query có được truy cập dữ liệu nhạy cảm không.
- Query tiêu tốn bao nhiêu tài nguyên.

### 14.1. Authorization

Quyền cần được kiểm tra ở phía server hoặc data service đáng tin cậy. Việc một field xuất hiện trong schema DSL không có nghĩa mọi người dùng đều được đọc field đó.

Có thể áp dụng:

- Row-level security.
- Column-level security.
- Tenant isolation.
- Role-based access control.
- Attribute-based access control.
- Capability theo nguồn dữ liệu.

Ví dụ, hai người dùng chạy cùng query nhưng nhận tập record khác nhau do policy theo tenant. Đây phải là semantics được quản lý ở backend, không phụ thuộc vào việc client tự thêm filter.

### 14.2. Parameter binding và injection

Không nên tạo query bằng cách nối chuỗi dữ liệu người dùng:

~~~text
query = "from Users where name == '" + input + "'"
~~~

Thay vào đó, dùng parameter:

~~~text
from Users
where name == :name
~~~

Runtime truyền giá trị name qua parameter binding. Điều này tách cấu trúc query khỏi dữ liệu đầu vào và giúp backend sử dụng prepared statement hoặc cơ chế tương đương.

### 14.3. Allowlist và capability

Nếu DSL cho phép function call, registry nên chỉ công bố function được phê duyệt. Không nên cho query gọi tùy ý API hoặc method nội bộ của ứng dụng chủ.

## 15. Bảo vệ dữ liệu nhạy cảm và quyền riêng tư

Query DSL có thể truy cập email, số điện thoại, địa chỉ, thông tin tài chính hoặc dữ liệu sức khỏe. Cần xác định:

- Field nhạy cảm nào được phép truy vấn.
- Ai có quyền truy cập.
- Dữ liệu nào được mask hoặc tokenize.
- Kết quả có thể được export hay không.
- Log query có lưu literal hoặc parameter nhạy cảm không.
- Kết quả có cần audit không.

Một query log nên có thể ghi query template, identity, source, duration và số dòng trả về mà không nhất thiết ghi toàn bộ parameter hoặc kết quả nhạy cảm.

Masking nên được thực hiện tại ranh giới dữ liệu đáng tin cậy. Không nên chỉ ẩn field ở UI nhưng vẫn trả toàn bộ dữ liệu nhạy cảm xuống client.

## 16. Tính di động và backend portability

Một query DSL có thể hướng tới nhiều backend, nhưng portability cần có phạm vi cụ thể.

Các khác biệt giữa backend:

- Kiểu dữ liệu và phép toán.
- Null semantics.
- Collation và so sánh chuỗi.
- Timezone và date arithmetic.
- Join và nested data.
- Transaction và consistency.
- Full-text search.
- Geospatial operation.
- Window function và aggregation.
- Giới hạn query hoặc API rate.

Có thể phân loại capability:

~~~text
Core query features:
  filter, projection, sort, limit

Optional capabilities:
  fullTextSearch
  geoDistance
  windowFunctions
  recursiveQuery
~~~

Query validator có thể kiểm tra backend mục tiêu hỗ trợ capability cần thiết trước khi thực thi.

### 16.1. Portable subset

Một DSL có thể định nghĩa một tập tính năng lõi có semantics nhất quán trên mọi backend được hỗ trợ. Các tính năng mở rộng được gắn capability hoặc dialect cụ thể.

Điều này tốt hơn việc âm thầm dịch một phép toán sang hành vi gần giống nhưng không tương đương.

### 16.2. Dialect

Dialect cho phép một backend có cú pháp hoặc tính năng riêng:

~~~text
using backend "warehouse"
  supports windowFunctions
~~~

Dialect cần được version hóa và tài liệu hóa. Nếu source phụ thuộc tính năng riêng, khả năng chuyển backend sẽ bị giới hạn và nên được thể hiện rõ.

## 17. Tính xác định và consistency

Một query có thể trả kết quả khác nhau ở hai lần chạy nếu dữ liệu thay đổi, thứ tự không được xác định hoặc query dùng hàm thời gian hiện tại.

DSL nên làm rõ:

- Có snapshot consistency hay không.
- Có đảm bảo thứ tự nếu không có order by không.
- now() được cố định theo thời điểm bắt đầu query hay gọi lại mỗi lần.
- Null và missing value được xử lý thế nào.
- Query đọc nhiều nguồn có cùng snapshot hay không.
- Kết quả có thể cache trong bao lâu.

Ví dụ:

~~~text
let evaluationTime = now();

from Invoices
where dueDate < evaluationTime
~~~

Gán thời điểm một lần giúp các phần của query dùng cùng mốc thời gian nếu semantics của DSL quy định biến này bất biến trong execution.

Không nên giả định database luôn trả kết quả theo cùng thứ tự nếu không có ordering rõ ràng.

## 18. Streaming query và truy vấn dữ liệu thời gian thực

Một số DSL truy vấn không làm việc trên tập dữ liệu tĩnh mà trên event stream:

~~~text
from PaymentEvents
window tumbling 5 minutes
group by merchantId
aggregate failedPayments = count(where status == FAILED)
where failedPayments > 20
emit alert
~~~

Streaming query cần các khái niệm:

- Event time và processing time.
- Window: tumbling, sliding hoặc session.
- Watermark và late event.
- State retention.
- Delivery guarantee.
- Checkpoint và recovery.
- Ordering và partition.

Đây là các semantics đặc thù, không thể suy ra từ query trên bảng tĩnh. DSL cần định nghĩa rõ window đóng khi nào và cách xử lý event đến muộn.

## 19. Query DSL cho các mô hình dữ liệu khác nhau

Không phải mọi truy vấn đều là quan hệ bảng-hàng.

### 19.1. Document query

Document database thường chứa object lồng nhau:

~~~text
from Customers
where address.city == "Da Nang"
select id, name, address.postalCode
~~~

DSL cần định nghĩa truy cập field lồng, array predicate và missing field.

### 19.2. Graph query

Graph query tìm đường đi hoặc quan hệ:

~~~text
from Person
match (person)-[:PURCHASED]->(product)
where product.category == "BOOK"
return person, product
~~~

Graph DSL cần định nghĩa node, edge, direction, path length và giới hạn traversal.

### 19.3. Search query

Search DSL có thể ưu tiên full-text, relevance và filter:

~~~text
search Products
text "wireless headphones"
filter available == true
sort by relevance
limit 20
~~~

Relevance score có thể phụ thuộc analyzer, ranking model và index version. Cần làm rõ những phần có thể tái lập và những phần phụ thuộc backend.

### 19.4. Event query

Event query có thể lọc theo thời gian, correlation ID và sequence. Cần định nghĩa ordering, window và event lateness.

## 20. Khả năng mở rộng và tích hợp

Query DSL có thể được nhúng trong nhiều môi trường:

- IDE hoặc workbench.
- API backend.
- Dashboard và reporting tool.
- Rule engine.
- Data pipeline.
- CLI.
- Notebook hoặc analytics environment.

Để hỗ trợ các môi trường đó, DSL nên có:

- API parse và validate.
- Query model hoặc AST có thể inspect.
- Parameter binding.
- Execution API.
- Explain plan.
- Structured diagnostics.
- Cancellation và timeout.
- Serialization nếu query được lưu hoặc truyền.

Không nên buộc mọi client tự viết parser riêng. Một compiler hoặc service dùng chung giúp giữ semantics nhất quán.

## 21. Developer experience và khả năng giải thích

Query DSL không chỉ cần tạo kết quả đúng; người dùng còn cần hiểu query đã làm gì và vì sao.

Các công cụ hỗ trợ:

- Syntax highlighting.
- Completion cho source, field và function.
- Hover mô tả kiểu.
- Diagnostics cho tên và kiểu không hợp lệ.
- Query formatting.
- Explain plan.
- Query profile.
- Preview sample result.
- Link tới schema và documentation.

Một diagnostic hữu ích:

~~~text
QUERY-012: Unknown field 'totla' on type Order.
  Did you mean 'total'?
  at sales/report.query:8:14
~~~

Một explain output có thể cho biết filter nào được push down, index nào được chọn và bước nào chiếm nhiều thời gian. Điều này giúp người dùng không phải đoán hiệu năng từ cú pháp.

## 22. Testability và khả năng tái lập

Query DSL nên dễ kiểm thử ở nhiều lớp:

### 22.1. Parse test

Kiểm tra source hợp lệ tạo AST đúng và source lỗi tạo diagnostic phù hợp.

### 22.2. Type-check test

Kiểm tra field, operator, function và aggregate có kiểu hợp lệ.

### 22.3. Semantic test

Với fixture dữ liệu cố định, chạy query và so sánh kết quả mong đợi.

### 22.4. Backend conformance test

Chạy cùng bộ query trên các backend được công bố tương thích và so sánh semantics theo contract.

### 22.5. Optimization equivalence test

So sánh kết quả trước và sau tối ưu để bảo đảm optimizer không đổi semantics.

### 22.6. Security test

Kiểm tra parameter binding, authorization, tenant isolation, field masking và resource limits.

### 22.7. Performance test

Đo latency, throughput, scan size, memory và query cost trên dữ liệu đại diện.

Với query phụ thuộc thời gian hoặc dữ liệu ngoài, nên inject clock hoặc fixture để test có thể tái lập.

## 23. Tiêu chí đánh giá một query DSL

Khi lựa chọn hoặc thiết kế query DSL, có thể đánh giá theo các nhóm:

| Tiêu chí | Câu hỏi cần trả lời |
|---|---|
| Domain fit | Cú pháp có phản ánh đúng vocabulary và câu hỏi của miền không? |
| Expressiveness | Có biểu đạt được các truy vấn cần thiết không? |
| Simplicity | Người dùng có thể học và đọc query dễ không? |
| Type safety | Lỗi field, kiểu và operator có được phát hiện sớm không? |
| Composability | Có thể tái sử dụng và kết hợp query không? |
| Optimization | Engine có thể tối ưu mà vẫn giữ semantics không? |
| Portability | Backend nào được hỗ trợ và giới hạn khác biệt ra sao? |
| Security | Quyền truy cập và chi phí truy vấn có được kiểm soát không? |
| Observability | Có explain, profile và diagnostic đủ tốt không? |
| Evolvability | Có thể mở rộng grammar và schema mà giữ tương thích không? |
| Tooling | Có editor, completion, formatter và documentation không? |
| Testability | Query có dễ kiểm thử và tái lập không? |

Không có một query DSL tối ưu cho mọi miền. Một DSL cho dashboard có thể ưu tiên khả năng khám phá và aggregation; một DSL cho policy engine có thể ưu tiên type safety, giới hạn side effect và khả năng giải thích; một DSL cho streaming cần semantics về event time và window.

## 24. Những lỗi thiết kế thường gặp

### Chỉ tạo cú pháp đẹp cho SQL

Nếu DSL chỉ đổi từ khóa SQL mà không cung cấp abstraction, validation hoặc tooling theo miền, chi phí duy trì một ngôn ngữ riêng có thể không đáng. Cần có giá trị rõ như type model, policy, portability hoặc domain vocabulary.

### Che giấu semantics backend

Một cú pháp giống nhau nhưng mỗi backend xử lý null, timezone hoặc string comparison khác nhau có thể tạo kết quả khác. Định nghĩa semantics lõi và công bố capability.

### Cho phép query không giới hạn

Một query đơn giản có thể gây full scan hoặc join khổng lồ. Áp dụng timeout, cost budget, result limit và explain plan.

### Ghép chuỗi để tạo query

Nối input vào query source tạo nguy cơ injection và lỗi escaping. Dùng parameter binding và AST construction.

### Không định nghĩa null và missing

Filter có thể trả kết quả khác nhau giữa backend. Xác định truth semantics và optional access.

### Trộn query với side effect tùy ý

Optimizer có thể đổi thứ tự đánh giá, khiến hành động phát sinh nhiều lần hoặc sai thứ tự. Giữ query expression thuần và tách action khỏi truy vấn nếu cần.

### Abstraction quá rộng

Một DSL cố hỗ trợ mọi backend và mọi mô hình dữ liệu có thể trở nên phức tạp, khó kiểm tra. Chọn portable core và extension theo capability.

### Không có explain hoặc diagnostics

Người dùng không biết query được hiểu và thực thi thế nào. Cung cấp AST view, explain plan, type information và lỗi có source location.

### Không kiểm soát schema evolution

Field đổi tên hoặc kiểu có thể làm query cũ hỏng. Kết hợp schema version, migration và diagnostics.

## 25. Quy trình xác định mục tiêu cho một DSL truy vấn

Trước khi thiết kế grammar, nhóm phát triển nên xác định:

1. **Người dùng chính.** Developer, analyst, operator hay người dùng nghiệp vụ?
2. **Câu hỏi dữ liệu.** Tìm kiếm, lọc, join, aggregation, graph traversal hay stream processing?
3. **Mô hình dữ liệu.** Quan hệ, document, graph, event hay kết hợp?
4. **Vocabulary miền.** Entity, field và predicate nào cần được biểu diễn bằng thuật ngữ nghiệp vụ?
5. **Phạm vi abstraction.** Phần nào che giấu backend, phần nào cần cho người dùng kiểm soát?
6. **Type system.** Kiểu nào được hỗ trợ và kiểm tra ra sao?
7. **Execution semantics.** Null, ordering, consistency, time và side effect hoạt động thế nào?
8. **Optimization.** Engine được phép biến đổi query đến mức nào?
9. **Security và cost.** Quyền, tenant, giới hạn và audit được áp dụng ở đâu?
10. **Portability.** Tập tính năng lõi và backend capability là gì?
11. **Tooling.** Editor, validation, explain, formatter và documentation cần có gì?
12. **Evolution.** Language version, schema version và migration được quản lý ra sao?

Kết quả của bước này nên là một tập use case đại diện, semantics được mô tả và tiêu chí đánh giá. Sau đó mới chọn cú pháp và triển khai parser, compiler hoặc query engine.

## 26. Ví dụ end-to-end: truy vấn đơn hàng giá trị cao

Giả sử người dùng muốn tìm 20 đơn hàng đã duyệt có tổng tiền cao nhất trong tháng hiện tại.

Query DSL:

~~~text
from Orders
where status == APPROVED
  and createdAt during currentMonth()
  and total >= money(10000000, VND)
select orderId, customerId, createdAt, total
order by total descending, orderId ascending
limit 20
~~~

Một query engine có thể xử lý:

1. Parse source thành query AST.
2. Resolve Orders và field theo schema.
3. Kiểm tra kiểu của status, createdAt và total.
4. Resolve currentMonth và Money literal.
5. Kiểm tra caller có quyền đọc các field.
6. Tạo logical plan gồm filter, projection, sort và limit.
7. Chọn backend và physical plan.
8. Push filter/projection xuống backend nếu có thể.
9. Thực thi với timeout và resource budget.
10. Trả kết quả cùng metadata hoặc query profile nếu được yêu cầu.

Một SQL backend có thể nhận truy vấn tương đương:

~~~sql
SELECT order_id, customer_id, created_at, total
FROM orders
WHERE status = 'APPROVED'
  AND created_at >= :month_start
  AND created_at < :next_month_start
  AND total >= :minimum_total
ORDER BY total DESC, order_id ASC
LIMIT 20;
~~~

Parameter được bind riêng thay vì nối chuỗi. Backend khác có thể dùng document aggregation hoặc API, nhưng phải giữ semantics đã định nghĩa cho khoảng thời gian, tiền tệ, ordering và limit.

## 27. Kết luận

Mục tiêu của DSL truy vấn là cung cấp một cách diễn đạt rõ ràng, an toàn và có ý nghĩa miền cho việc lấy và biến đổi dữ liệu. Một DSL tốt giúp người dùng tập trung vào câu hỏi cần trả lời, trong khi query engine xử lý phân tích, kiểm tra kiểu, tối ưu và thực thi trên backend phù hợp.

Các mục tiêu quan trọng gồm vocabulary gần với miền, semantics nhất quán, composability, type safety, portability có giới hạn rõ, tối ưu hiệu quả, kiểm soát bảo mật và chi phí, cùng tooling hỗ trợ giải thích và kiểm thử. Cú pháp dễ đọc chỉ là một phần; giá trị của DSL đến từ hợp đồng ngữ nghĩa và hệ thống thực thi đứng phía sau.

Khi thiết kế, hãy bắt đầu từ use case và mô hình dữ liệu thực tế, xác định rõ null, ordering, time, consistency và quyền truy cập, rồi mới chọn grammar. Một query DSL có phạm vi tập trung, semantics minh bạch và khả năng phát triển có kiểm soát sẽ hữu ích hơn một ngôn ngữ cố gắng biểu đạt mọi loại truy vấn mà không có ranh giới rõ ràng.

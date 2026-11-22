# Chọn và chiếu dữ liệu

Trong ngôn ngữ chuyên biệt cho lĩnh vực (Domain-Specific Language — DSL) dùng để truy vấn, người dùng thường cần lấy một tập dữ liệu từ nguồn, xác định bản ghi nào đáp ứng điều kiện và chọn những thông tin cần thiết để trả về. Hai thao tác cốt lõi trong công việc này là **chọn dữ liệu (selection)** và **chiếu dữ liệu (projection)**.

Selection xác định những phần tử hoặc bản ghi nào được giữ lại dựa trên một điều kiện. Projection xác định những trường, biểu thức hoặc cấu trúc nào được đưa vào kết quả. Trong nhiều DSL, selection được viết bằng từ khóa **where**, còn projection được viết bằng **select**. Cú pháp cụ thể có thể khác nhau, nhưng sự phân biệt về ý nghĩa vẫn quan trọng.

Ví dụ, một truy vấn đơn hàng có thể lấy các đơn đã thanh toán có tổng tiền lớn hơn một ngưỡng, rồi chỉ trả về mã đơn, thời điểm tạo và tổng tiền:

~~~text
from Order as order
where order.status == PAID
  and order.total > minimumTotal
select {
  order.id,
  order.createdAt,
  order.total
}
~~~

Where lọc tập Order theo điều kiện; select tạo hình dạng kết quả mới chỉ chứa ba thông tin được yêu cầu. Nếu đảo lẫn hai trách nhiệm này, truy vấn có thể đọc khó hiểu, trả thừa dữ liệu hoặc làm sai ý nghĩa khi kết hợp với phép toán khác.

Bài học này trình bày cách chọn bản ghi, chiếu trường và biểu thức, đặt alias, tạo kết quả có cấu trúc, xử lý null và collection, hiểu thứ tự các toán tử truy vấn, phân biệt projection với lọc, tối ưu truy vấn, kiểm soát dữ liệu nhạy cảm và kiểm thử kết quả.

## 1. Selection và projection là gì?

Selection và projection là hai phép biến đổi cơ bản trên dữ liệu.

- **Selection:** giữ lại những bản ghi thỏa mãn một predicate.
- **Projection:** tạo kết quả từ một hoặc nhiều trường hoặc biểu thức của bản ghi.

Giả sử nguồn dữ liệu có bảng Order:

| id | status | customerId | total | createdAt |
| --- | --- | --- | ---: | --- |
| O-101 | PAID | C-1 | 250000 | 2026-01-10 |
| O-102 | PENDING | C-2 | 120000 | 2026-01-11 |
| O-103 | PAID | C-3 | 90000 | 2026-01-12 |
| O-104 | CANCELLED | C-1 | 400000 | 2026-01-13 |

Selection với điều kiện status bằng PAID giữ lại O-101 và O-103.

Projection chọn id và total chỉ giữ hai trường đó của mỗi bản ghi.

Kết hợp cả hai:

~~~text
from Order
where status == PAID
select { id, total }
~~~

Kết quả:

| id | total |
| --- | ---: |
| O-101 | 250000 |
| O-103 | 90000 |

### 1.1. Selection không nhất thiết thay đổi cấu trúc bản ghi

Selection thường giữ nguyên kiểu phần tử nguồn, chỉ làm giảm số phần tử trong tập kết quả.

Nếu nguồn là List<Order>, sau selection vẫn là tập các Order, nhưng có thể ít phần tử hơn.

### 1.2. Projection thường thay đổi kiểu kết quả

Projection có thể biến Order thành một record mới chỉ gồm id và total:

~~~text
Order -> OrderSummary
~~~

Kiểu kết quả có thể là tuple, record ẩn danh, DTO, map, object hoặc một kiểu do DSL định nghĩa.

### 1.3. Hai phép toán có thể kết hợp

Một query thường có dạng:

~~~text
source
  -> selection
  -> projection
~~~

Tuy nhiên, ngữ nghĩa thực tế còn phụ thuộc grouping, ordering, distinct, pagination, join và cách runtime tối ưu pipeline.

## 2. Cú pháp truy vấn cơ bản

Một DSL truy vấn có thể cung cấp cấu trúc tổng quát:

~~~text
from Source
where Predicate
select Projection
~~~

Trong đó:

- **from** xác định nguồn dữ liệu và tên biến đại diện cho phần tử hiện tại.
- **where** chứa biểu thức Boolean để quyết định giữ hay loại phần tử.
- **select** mô tả kết quả được tạo ra từ mỗi phần tử còn lại.

Ví dụ:

~~~text
from Customer as customer
where customer.active == true
select {
  customer.id,
  customer.name
}
~~~

Nếu DSL hỗ trợ alias mặc định, có thể viết ngắn hơn:

~~~text
from Customer
where active == true
select { id, name }
~~~

Cú pháp rút gọn chỉ rõ ràng khi phạm vi tên không mơ hồ. Với query có join hoặc nhiều nguồn, nên dùng alias tường minh.

### 2.1. Query expression và query statement

Một query expression trả về một giá trị, thường là collection:

~~~text
let activeCustomers =
  from Customer
  where active == true
  select { id, name }
~~~

Một query statement có thể được dùng như câu lệnh riêng để tạo báo cáo, xuất dữ liệu hoặc đưa kết quả vào bước workflow.

Dù là expression hay statement, kiểu kết quả và thời điểm thực thi cần được đặc tả.

### 2.2. Alias nguồn

Alias đặt tên cho phần tử đang được xét:

~~~text
from Order as order
where order.total > 100000
select order.id
~~~

Alias giúp phân biệt các nguồn và làm rõ receiver khi truy cập thuộc tính.

### 2.3. Biểu thức trong projection

Projection có thể chứa trường trực tiếp, literal, phép toán, lời gọi hàm thuần hoặc biểu thức điều kiện:

~~~text
select {
  order.id,
  totalWithTax: order.total * taxRate,
  isHighValue: order.total >= threshold
}
~~~

Mỗi biểu thức cần được kiểm tra kiểu và đánh giá theo semantics của DSL.

## 3. Phân biệt selection với các thao tác truy vấn khác

Một query pipeline có thể gồm nhiều phép biến đổi. Cần hiểu đúng vai trò từng phép toán.

| Phép toán | Mục đích | Ví dụ |
| --- | --- | --- |
| Source | Chọn nguồn đầu vào | from Order |
| Selection | Lọc phần tử theo điều kiện | where total > 0 |
| Projection | Chọn hoặc tính trường đầu ra | select { id, total } |
| Ordering | Sắp xếp kết quả | order by createdAt desc |
| Distinct | Loại kết quả trùng | distinct |
| Grouping | Gom phần tử theo khóa | group by customerId |
| Pagination | Giới hạn một đoạn kết quả | limit 20 offset 40 |
| Join | Kết hợp nhiều nguồn | join Customer |

Một số DSL có thể gộp hoặc đổi tên các toán tử. Điều quan trọng là giữ ranh giới ngữ nghĩa: lọc bản ghi không giống chọn trường, và sắp xếp không giống grouping.

### 3.1. Selection không phải projection

Where trả lời câu hỏi “bản ghi nào được giữ lại?”. Select trả lời “mỗi bản ghi được biểu diễn ra sao trong kết quả?”.

Ví dụ:

~~~text
from Customer
where countryCode == "VN"
select { id, name }
~~~

Không có nghĩa chỉ chọn trường countryCode. Điều kiện countryCode chỉ quyết định bản ghi nào được giữ.

### 3.2. Projection không phải update

Projection tạo một kết quả mới; nó không nhất thiết sửa record nguồn.

~~~text
select {
  displayName: customer.firstName + " " + customer.lastName
}
~~~

displayName là trường kết quả tính ra. Nó không tự động được ghi vào Customer.

### 3.3. Selection không phải authorization

Điều kiện ownerId bằng currentUser.id có thể lọc dữ liệu theo người dùng, nhưng không nên xem đó là ranh giới bảo mật duy nhất. Hệ thống cần áp dụng authorization ở tầng truy cập dữ liệu hoặc service có thẩm quyền.

## 4. Selection predicate

Predicate là biểu thức có kết quả Boolean hoặc một kiểu điều kiện theo quy ước của DSL. Mỗi phần tử nguồn được đánh giá predicate để quyết định có giữ lại hay không.

Ví dụ:

~~~text
where order.total >= 500000
~~~

Predicate tham chiếu đến bản ghi hiện tại thông qua alias order.

### 4.1. So sánh

Các phép so sánh thường gặp:

~~~text
price > minimum
quantity >= 1
status == PAID
region != "UNKNOWN"
createdAt < cutoff
~~~

Cần định nghĩa cách so sánh theo kiểu dữ liệu. So sánh Decimal, Date, String và enum có thể có semantics khác nhau.

### 4.2. Logic Boolean

Có thể kết hợp điều kiện bằng AND, OR và NOT:

~~~text
where status == PAID
  and total >= minimum
  and not archived
~~~

Thứ tự ưu tiên và short-circuit phải được xác định. Dùng ngoặc giúp thể hiện ý định:

~~~text
where (status == PAID or status == CONFIRMED)
  and total >= minimum
~~~

### 4.3. Membership

Kiểm tra giá trị có thuộc một tập:

~~~text
where status in [PAID, CONFIRMED]
~~~

Tập bên phải có thể là literal, biến hoặc kết quả truy vấn khác. Cần quy định xử lý null và collection rỗng.

### 4.4. Range

Điều kiện trong khoảng:

~~~text
where total between 100000 and 500000
~~~

Cần định nghĩa hai đầu mút có bao gồm hay không. Một cách viết tương đương có thể là:

~~~text
where total >= 100000 and total <= 500000
~~~

### 4.5. String predicate

Một số DSL hỗ trợ:

~~~text
where name startsWith "Nguyen"
where email contains "@example.org"
where code matches "[A-Z]{3}-[0-9]+"
~~~

Các hàm chuỗi cần xác định quy tắc phân biệt hoa thường, Unicode normalization và semantics của pattern. Không nên để hành vi phụ thuộc locale của máy chạy.

### 4.6. Predicate có thể tái sử dụng

Điều kiện thường dùng có thể được đặt tên:

~~~text
predicate isActiveCustomer(customer: Customer) {
  customer.active and customer.deletedAt == null
}

from Customer as customer
where isActiveCustomer(customer)
select { customer.id, customer.name }
~~~

Predicate có tên giúp diễn đạt quy tắc miền và tránh sao chép điều kiện ở nhiều query. Cần đảm bảo predicate có semantics thuần nếu muốn dùng trong tối ưu truy vấn.

## 5. Kết hợp nhiều điều kiện và short-circuit

Một selection có thể chứa nhiều predicate:

~~~text
where order.status == PAID
  and order.total > minimumTotal
  and order.customer.active
~~~

### 5.1. Thứ tự đánh giá

Nếu các predicate thuần và không có tác động phụ, runtime có thể tối ưu thứ tự đánh giá trong giới hạn semantics. Nếu predicate có thể gọi service hoặc ném lỗi, đổi thứ tự có thể thay đổi hành vi.

Ví dụ:

~~~text
where customer != null
  and customer.active
~~~

Nếu AND dùng short-circuit từ trái sang phải, phép truy cập customer.active chỉ được thực hiện khi customer khác null.

Nếu đổi thứ tự:

~~~text
where customer.active
  and customer != null
~~~

có thể phát sinh lỗi null trước khi điều kiện thứ hai được xét.

### 5.2. Ngoặc và precedence

Không nên dựa vào trí nhớ về precedence khi biểu thức có cả AND và OR:

~~~text
where status == PAID
  or status == CONFIRMED
  and total > minimum
~~~

Nếu AND có ưu tiên cao hơn OR, biểu thức tương đương:

~~~text
where status == PAID
  or (status == CONFIRMED and total > minimum)
~~~

Nếu ý định là cả hai trạng thái đều phải thỏa total, cần viết:

~~~text
where (status == PAID or status == CONFIRMED)
  and total > minimum
~~~

### 5.3. Điều kiện có thể lỗi

Một predicate có thể phát sinh lỗi khi:
- Truy cập property trên null.
- Chuyển kiểu thất bại.
- Gọi hàm không hợp lệ.
- Chia cho zero.
- Truy cập dữ liệu không có quyền.

DSL cần quy định query dừng toàn bộ, loại bản ghi, trả diagnostic hay chuyển lỗi theo policy. Không nên âm thầm coi mọi lỗi là false vì điều đó có thể che giấu lỗi dữ liệu.

### 5.4. Null trong predicate

Một số hệ thống dùng logic ba giá trị: true, false và unknown. Ví dụ so sánh null với 5 có thể cho unknown thay vì false.

Nếu DSL dùng ba giá trị, where cần quy định chỉ true mới giữ record hay có quy tắc khác. Nếu dùng Boolean hai giá trị, semantics của null phải được mô tả rõ.

## 6. Projection chọn trường trực tiếp

Projection đơn giản nhất trả về một hoặc nhiều trường có sẵn.

~~~text
from Customer as customer
select {
  customer.id,
  customer.name,
  customer.email
}
~~~

Kết quả có thể là collection của CustomerSummary hoặc record ẩn danh với ba field.

### 6.1. Chọn một trường

~~~text
from Customer as customer
select customer.email
~~~

Kết quả là collection các email, không còn là collection Customer.

### 6.2. Chọn nhiều trường

~~~text
select {
  customer.id,
  customer.name
}
~~~

Kết quả thường là record hoặc tuple có hai thành phần.

### 6.3. Thứ tự trường

Nếu projection trả record có thứ tự, thứ tự field trong khai báo có thể ảnh hưởng serialization hoặc tuple access. Nếu kết quả là object theo tên, thứ tự có thể chỉ là thứ tự trình bày.

DSL cần xác định liệu thứ tự projection có thuộc contract hay không.

### 6.4. Trường trùng tên

Nếu hai nguồn cùng có field id, projection cần alias:

~~~text
select {
  customerId: customer.id,
  orderId: order.id
}
~~~

Không nên tự ghi đè một field bằng field khác chỉ vì chúng có cùng tên.

### 6.5. Projection rỗng

Một projection không có field có thể hữu ích cho truy vấn chỉ cần đếm hoặc kiểm tra tồn tại, nhưng không phải mọi DSL đều cho phép. Nếu không hỗ trợ, parser hoặc validator nên báo lỗi rõ.

## 7. Alias trong projection

Alias đặt tên cho trường đầu ra. Nó đặc biệt hữu ích với biểu thức tính toán, tên field trùng nhau hoặc khi muốn tạo DTO có schema ổn định.

~~~text
select {
  orderId: order.id,
  totalWithTax: order.total * taxRate
}
~~~

### 7.1. Alias cho biểu thức

Biểu thức thường không có tên tự nhiên:

~~~text
select {
  netAmount: order.total - order.discount,
  isLarge: order.total >= largeOrderThreshold
}
~~~

Alias giúp consumer truy cập kết quả bằng tên ổn định.

### 7.2. Quy tắc đặt tên alias

Alias nên:
- Là identifier hợp lệ.
- Không trùng với field khác trong cùng projection.
- Có tên ổn định theo contract.
- Không phụ thuộc vào cách format biểu thức.
- Phù hợp với quy ước serialization của target.

### 7.3. Alias và tên field nguồn

Nếu projection dùng field trực tiếp, DSL có thể tự đặt tên output theo tên field. Nhưng khi có nhiều nguồn hoặc expression, alias tường minh giúp tránh phụ thuộc vào quy tắc suy luận tên.

### 7.4. Alias không đổi tên dữ liệu nguồn

totalWithTax trong kết quả không đổi tên property total trên entity Order. Alias chỉ tồn tại trong projection result.

## 8. Projection tính toán

Projection có thể tính giá trị mới từ các field nguồn.

~~~text
from Order as order
select {
  order.id,
  subtotal: order.items.sum(item.price),
  tax: order.items.sum(item.price) * order.taxRate,
  grandTotal: order.total
}
~~~

### 8.1. Phép toán số học

Có thể dùng cộng, trừ, nhân, chia và modulo nếu kiểu hỗ trợ:

~~~text
select {
  lineTotal: item.unitPrice * item.quantity,
  discounted: item.unitPrice * (1 - item.discountRate)
}
~~~

Với Decimal, runtime cần giữ precision và scale theo semantics của DSL. Không nên để phép toán tiền tệ rơi vào floating-point không chính xác.

### 8.2. Biểu thức điều kiện

Projection có thể tạo nhãn hoặc phân loại:

~~~text
select {
  order.id,
  priority: if order.total >= 1000000 then "HIGH" else "NORMAL"
}
~~~

Kiểu của nhánh then và else cần tương thích. Nếu một nhánh trả String, nhánh còn lại trả Integer, DSL phải có quy tắc union hoặc báo lỗi kiểu.

### 8.3. Gọi hàm

Hàm thuần có thể được dùng để chuẩn hóa hoặc tính toán:

~~~text
select {
  normalizedEmail: lower(trim(customer.email)),
  displayName: formatName(customer.firstName, customer.lastName)
}
~~~

Nếu function có side effect, query engine cần quyết định có cho phép gọi trong projection hay không. Thông thường, projection nên tránh action ghi dữ liệu hoặc gọi dịch vụ không xác định để kết quả có thể dự đoán và tối ưu.

### 8.4. Literal và hằng số

Có thể thêm giá trị cố định vào từng record:

~~~text
select {
  order.id,
  source: "PORTAL",
  schemaVersion: 2
}
~~~

Literal có thể hữu ích khi tạo payload theo contract. Tuy nhiên, giá trị mặc định cho toàn bộ bản ghi thường có thể được xử lý ở tầng serializer hoặc schema nếu semantics phù hợp.

### 8.5. Date và time

Projection có thể tính ngày hoặc khoảng thời gian:

~~~text
select {
  order.id,
  orderAgeDays: daysBetween(order.createdAt, currentTime())
}
~~~

currentTime làm kết quả phụ thuộc thời điểm đánh giá. Nếu cần tái lập, nên truyền clock hoặc cutoff time vào query context.

## 9. Projection thành record hoặc object mới

Một query thường tạo kiểu kết quả riêng thay vì trả entity nguồn.

~~~text
type OrderSummary {
  id: OrderId
  customerName: String
  total: Decimal
  status: OrderStatus
}

from Order as order
join Customer as customer on customer.id == order.customerId
select OrderSummary {
  id: order.id,
  customerName: customer.name,
  total: order.total,
  status: order.status
}
~~~

### 9.1. Anonymous projection

Một số DSL cho phép record ẩn danh:

~~~text
select {
  id: order.id,
  total: order.total
}
~~~

Kiểu kết quả có thể được suy luận từ tên và kiểu field.

### 9.2. Named projection type

Một kiểu có tên giúp tái sử dụng kết quả giữa nhiều query, API và service:

~~~text
projection OrderSummary {
  id: OrderId
  total: Decimal
}
~~~

Named projection tạo contract rõ ràng và dễ kiểm tra tương thích.

### 9.3. Constructor projection

Một DSL có thể gọi constructor hoặc factory:

~~~text
select new OrderSummary(
  order.id,
  order.total
)
~~~

Cần xác định thứ tự tham số và kiểu tương ứng. Object-style assignment thường ít nhạy cảm hơn khi thêm field.

### 9.4. Immutable result

Projection result thường phù hợp với cấu trúc bất biến. Điều này giúp tránh consumer thay đổi kết quả và vô tình ảnh hưởng object nguồn nếu hai bên dùng chung reference.

### 9.5. Projection và entity identity

Projection không nhất thiết giữ identity hoặc lifecycle của entity. Một OrderSummary chỉ là dữ liệu trình bày. Không nên truyền nó vào operation yêu cầu một entity có identity và hành vi đầy đủ nếu type system không cho phép.

## 10. Projection lồng nhau

Có thể tạo object con từ các thuộc tính liên quan:

~~~text
from Order as order
select {
  id: order.id,
  customer: {
    id: order.customer.id,
    name: order.customer.name
  },
  totals: {
    subtotal: order.subtotal,
    tax: order.tax,
    grandTotal: order.total
  }
}
~~~

Kết quả có cấu trúc:

~~~json
{
  "id": "O-101",
  "customer": {
    "id": "C-1",
    "name": "An"
  },
  "totals": {
    "subtotal": 250000,
    "tax": 25000,
    "grandTotal": 275000
  }
}
~~~

### 10.1. Object lồng nhau và reference

Projection có thể nhúng toàn bộ object liên quan hoặc chỉ chọn một số field. Nhúng quá sâu có thể tạo payload lớn hoặc vòng lặp.

Nên chọn đúng mức dữ liệu cần thiết và giới hạn độ sâu.

### 10.2. Collection lồng nhau

Ví dụ, trả về các item của đơn hàng:

~~~text
select {
  id: order.id,
  items: order.items select {
    productId,
    quantity,
    unitPrice
  }
}
~~~

Cú pháp lồng có thể khác nhau. Semantics cần làm rõ projection con chạy trên collection nào và scope alias nào đang có hiệu lực.

### 10.3. Empty collection và null

Nếu order không có item, kết quả items có thể là collection rỗng. Nếu order.items là null hoặc chưa tải, hành vi có thể khác. Schema kết quả nên xác định collection có luôn tồn tại hay có thể null.

### 10.4. Projection nhiều cấp

Nhiều cấp object và collection có thể tạo cấu trúc phức tạp. Cần kiểm soát:
- Số lượng phần tử.
- Độ sâu lồng.
- Lazy loading.
- Vòng tham chiếu.
- Chi phí truy vấn.
- Quyền truy cập từng trường.

## 11. Chọn và chiếu dữ liệu từ nhiều nguồn

Query có thể kết hợp nhiều nguồn bằng join. Khi đó, selection và projection phải xác định rõ alias của từng nguồn.

~~~text
from Order as order
join Customer as customer
  on customer.id == order.customerId
where customer.active
select {
  orderId: order.id,
  customerName: customer.name,
  total: order.total
}
~~~

### 11.1. Inner join

Inner join chỉ giữ cặp bản ghi có điều kiện join khớp. Nếu một Order không có Customer tương ứng, nó không xuất hiện trong kết quả.

### 11.2. Left join

Left join giữ tất cả bản ghi bên trái, kể cả khi không có bản ghi bên phải. Field lấy từ phía phải có thể null:

~~~text
from Customer as customer
left join Order as order
  on order.customerId == customer.id
select {
  customer.id,
  customer.name,
  orderId: order.id
}
~~~

Nếu khách hàng chưa có đơn, orderId có thể là null. Type inference cần phản ánh điều đó.

### 11.3. Điều kiện lọc sau left join

Xét:

~~~text
from Customer as customer
left join Order as order
  on order.customerId == customer.id
where order.status == PAID
select { customer.id, order.id }
~~~

Predicate order.status bằng PAID loại các dòng mà order là null. Kết quả có thể tương đương inner join trong trường hợp này.

Nếu muốn giữ cả khách hàng không có đơn, điều kiện cần xử lý null:

~~~text
where order == null or order.status == PAID
~~~

### 11.4. Tên field trùng

Khi cả Order và Customer đều có id, projection cần alias riêng:

~~~text
select {
  customerId: customer.id,
  orderId: order.id
}
~~~

### 11.5. Join nhiều nguồn

Với nhiều nguồn, nên dùng alias nhất quán và qualify field khi cần:

~~~text
from Order as order
join Customer as customer on customer.id == order.customerId
join Region as region on region.id == customer.regionId
select {
  order.id,
  customer.name,
  region.code
}
~~~

Query planner có thể chọn thứ tự join khác nhau, nhưng kết quả phải giữ semantics được DSL quy định.

## 12. Selection và projection trên collection

DSL có thể truy vấn collection trong bộ nhớ thay vì database.

~~~text
let activeOrders =
  orders
    .where(order => order.status == PAID)
    .select(order => {
      id: order.id,
      total: order.total
    })
~~~

### 12.1. Eager evaluation

Eager evaluation tạo toàn bộ kết quả ngay khi query chạy. Nó đơn giản cho collection nhỏ nhưng có thể tốn bộ nhớ với dữ liệu lớn.

### 12.2. Lazy evaluation

Lazy query chỉ tính phần tử khi consumer yêu cầu. Điều này có thể giảm bộ nhớ và cho phép pipeline kết hợp nhiều phép toán.

Tuy nhiên, thời điểm phát sinh lỗi hoặc đọc dữ liệu có thể muộn hơn thời điểm khai báo query.

### 12.3. Deferred query

Một query có thể được xây dựng trước rồi thực thi sau. Nếu nguồn dữ liệu hoặc context thay đổi trước khi thực thi, kết quả có thể khác. DSL cần xác định query capture giá trị tại lúc tạo hay đọc giá trị tại lúc chạy.

### 12.4. Streaming

Với stream lớn, projection có thể chạy từng record và phát kết quả dần. Cần xác định backpressure, cancellation và cách xử lý lỗi giữa stream.

### 12.5. Materialization

Khi kết quả được materialize thành List hoặc array, runtime tiêu thụ bộ nhớ tương ứng. Người dùng nên biết query có lazy hay eager semantics, đặc biệt khi kết quả lớn.

## 13. Projection và kiểu kết quả

Type system cần suy ra hoặc kiểm tra kiểu của projection.

~~~text
select {
  id: order.id,
  total: order.total,
  paid: order.status == PAID
}
~~~

Kiểu kết quả có thể là:

~~~text
Record {
  id: OrderId,
  total: Decimal,
  paid: Boolean
}
~~~

### 13.1. Suy luận kiểu từng field

Mỗi field output lấy kiểu từ:
- Field nguồn.
- Kiểu của expression.
- Kiểu literal.
- Kiểu trả về của function.
- Kiểu nullable do join hoặc safe navigation.

### 13.2. Kiểu của conditional expression

~~~text
select {
  label: if order.total > 0 then "VALID" else "EMPTY"
}
~~~

Hai nhánh đều String, nên output label có kiểu String.

Nếu hai nhánh có kiểu khác nhau, DSL cần quy tắc common type, union type hoặc yêu cầu conversion tường minh.

### 13.3. Numeric promotion

Ví dụ Decimal kết hợp Integer:

~~~text
select {
  gross: order.net + order.tax
}
~~~

Type checker cần áp dụng numeric promotion đã định nghĩa. Không nên để host language tự quyết định.

### 13.4. Nullability propagation

Nếu field từ phía phải của left join có thể thiếu, output tương ứng có thể nullable:

~~~text
select {
  customerName: customer.name,
  lastOrderId: lastOrder.id
}
~~~

Nếu lastOrder không tồn tại, lastOrderId cần có kiểu nullable hoặc biểu diễn optional tương đương.

### 13.5. Generic và collection type

Nếu projection tạo danh sách, kiểu kết quả có thể là List<Decimal> hoặc Sequence<Decimal>, tùy semantics thực thi.

### 13.6. Named projection compatibility

Nếu projection được gán vào kiểu OrderSummary, type checker cần kiểm tra:
- Field bắt buộc có mặt.
- Field không thừa nếu schema cấm.
- Kiểu tương thích.
- Nullability.
- Default.
- Visibility hoặc access rule.

## 14. Projection, duplicate và distinct

Projection có thể làm nhiều bản ghi nguồn trở thành kết quả giống nhau.

Ví dụ, nhiều đơn hàng của cùng khách hàng:

~~~text
from Order as order
select order.customerId
~~~

Kết quả có thể có nhiều customerId trùng lặp.

### 14.1. Giữ duplicate theo mặc định

Nhiều query giữ nguyên multiplicity của nguồn. Nếu có 5 đơn hàng của một khách hàng, customerId có thể xuất hiện 5 lần.

Không nên giả định projection tự loại trùng.

### 14.2. Distinct

Nếu muốn danh sách customerId duy nhất:

~~~text
from Order
select customerId
distinct
~~~

Hoặc cú pháp:

~~~text
select distinct customerId
~~~

Vị trí toán tử và semantics phụ thuộc DSL. Cần định nghĩa distinct áp dụng trước hay sau projection.

### 14.3. Distinct trước và sau projection

Hai cách có thể khác nhau:

- Distinct trên entity trước projection loại các entity trùng theo identity.
- Projection rồi distinct loại các kết quả có cùng giá trị field được chọn.

Ví dụ hai Order khác nhau cùng customerId. Distinct trên Order không loại hai Order; distinct sau projection trên customerId có thể chỉ giữ một giá trị.

### 14.4. Equality semantics

Để distinct hoạt động, DSL cần định nghĩa equality cho:
- Scalar.
- Decimal.
- Record.
- Collection.
- Entity identity.
- Null.

Không nên dựa vào object reference của host language nếu DSL có semantics riêng.

## 15. Projection cùng grouping và aggregate

Grouping chia bản ghi thành các nhóm theo khóa; projection có thể trả về khóa nhóm và các phép tổng hợp.

~~~text
from Order as order
group by order.customerId
select {
  customerId: group.key,
  orderCount: group.count(),
  totalSpent: group.sum(order.total)
}
~~~

### 15.1. Selection trước grouping

Có thể lọc đơn hàng trước khi nhóm:

~~~text
from Order as order
where order.status == PAID
group by order.customerId
select {
  customerId: group.key,
  totalPaid: group.sum(order.total)
}
~~~

Chỉ đơn đã thanh toán được tính vào aggregate.

### 15.2. Filter sau aggregate

Điều kiện trên aggregate thường cần một bước lọc nhóm, tương tự HAVING:

~~~text
group by customerId
having group.sum(total) > 1000000
select {
  customerId: group.key,
  totalSpent: group.sum(total)
}
~~~

Không thể luôn thay having bằng where, vì where trước grouping xét từng record còn having xét cả nhóm.

### 15.3. Aggregate phổ biến

- count.
- sum.
- average.
- min.
- max.
- countDistinct.
- collect.

Cần định nghĩa xử lý null và nhóm rỗng. Ví dụ sum của collection rỗng có thể là 0 hoặc null tùy DSL.

### 15.4. Group key và output type

Kết quả sau grouping thường không còn là entity nguồn mà là record gồm group key và aggregate fields. Type checker cần phản ánh kiểu này.

### 15.5. Nhiều khóa nhóm

Có thể nhóm theo nhiều trường:

~~~text
group by {
  order.customerId,
  year(order.createdAt)
}
~~~

Projection cần trả đủ các khóa hoặc một biểu diễn group key có cấu trúc.

## 16. Ordering và pagination sau projection

Ordering xác định thứ tự kết quả. Pagination giới hạn phần kết quả được trả về.

~~~text
from Order as order
where order.status == PAID
select {
  order.id,
  order.total,
  order.createdAt
}
order by createdAt desc
limit 20
~~~

### 16.1. Sort key

Sort key có thể là field nguồn hoặc alias projection. DSL cần quy định alias có được tham chiếu trong order by không.

Nếu sort theo field không có trong projection, query engine có thể vẫn dùng field nguồn nội bộ. Nhưng nếu target database hoặc API yêu cầu, cần xác định khả năng thực thi.

### 16.2. Nhiều sort key

~~~text
order by createdAt desc, total asc
~~~

Nếu hai record bằng nhau ở sort key đầu, sort key tiếp theo quyết định thứ tự.

### 16.3. Stable ordering

Nếu tất cả sort key bằng nhau, thứ tự có thể không xác định trừ khi DSL hoặc nguồn bảo đảm stable order. Pagination cần thứ tự ổn định để tránh bản ghi xuất hiện lặp hoặc bị bỏ qua giữa các trang.

Có thể thêm tie-breaker duy nhất như id:

~~~text
order by createdAt desc, id asc
~~~

### 16.4. Offset pagination

~~~text
limit 20 offset 40
~~~

Cách này dễ hiểu nhưng offset lớn có thể tốn chi phí và dữ liệu thay đổi giữa các trang có thể làm kết quả dịch chuyển.

### 16.5. Keyset pagination

Keyset pagination dùng giá trị của sort key cuối trang trước để lấy trang tiếp theo. Ví dụ sort theo createdAt và id:

~~~text
where createdAt < lastCreatedAt
  or (createdAt == lastCreatedAt and id > lastId)
order by createdAt desc, id asc
limit 20
~~~

Điều kiện chính xác phụ thuộc hướng sort. Keyset pagination cần sort key ổn định và thường có hiệu năng tốt hơn với tập dữ liệu lớn.

### 16.6. Pagination và projection

Nếu projection bỏ mất sort key, query engine vẫn cần giữ thông tin đó trong execution plan. Không nên yêu cầu consumer nhận thêm field chỉ để phục vụ pagination nếu contract không cần.

## 17. Subquery và projection lồng query

Projection có thể chứa một query con hoặc một collection được tạo từ nguồn liên quan.

~~~text
from Customer as customer
select {
  customer.id,
  customer.name,
  paidOrders: (
    from Order as order
    where order.customerId == customer.id
      and order.status == PAID
    select {
      order.id,
      order.total
    }
  )
}
~~~

### 17.1. Correlated subquery

Query con tham chiếu đến customer từ query ngoài. Đây là correlated subquery. Scope của query con cần liên kết với outer environment theo quy tắc lexical scope.

### 17.2. Subquery trả scalar

Một subquery có thể trả một giá trị như tổng đơn hàng:

~~~text
select {
  customer.id,
  paidTotal: (
    from Order
    where customerId == customer.id and status == PAID
    select sum(total)
  )
}
~~~

Cần xác định subquery có thể trả zero, one hay many values. Nếu yêu cầu scalar nhưng kết quả có nhiều dòng, runtime phải báo lỗi hoặc có quy tắc aggregate rõ.

### 17.3. Exists

Nếu chỉ cần biết có bản ghi liên quan hay không, dùng exists thường rõ hơn materialize cả collection:

~~~text
where exists (
  from Order
  where customerId == customer.id and status == PAID
)
~~~

### 17.4. Tránh N+1 query

Nếu projection có subquery được thực thi riêng cho từng Customer, có thể tạo N+1 query. Query planner có thể chuyển thành join, batch fetch hoặc aggregate nếu semantics cho phép.

### 17.5. Giới hạn nested result

Nested projection có thể tạo payload lớn. Cần hỗ trợ giới hạn số phần tử con, chọn field cần thiết và phân trang collection lồng nhau khi cần.

## 18. Projection cho API, DTO và serialization

Projection thường là ranh giới giữa mô hình nội bộ và dữ liệu được trả cho client.

### 18.1. DTO projection

Thay vì trả entity trực tiếp:

~~~text
from Customer as customer
select CustomerResponse {
  id: customer.id,
  displayName: customer.firstName + " " + customer.lastName,
  active: customer.active
}
~~~

DTO chỉ chứa dữ liệu cần cho response.

### 18.2. Request và response projection

Request projection mô tả dữ liệu client được phép gửi. Response projection mô tả dữ liệu server được phép trả.

Hai chiều có thể khác nhau:
- ID có thể do server tạo, không xuất hiện trong request.
- Internal status có thể không xuất hiện trong response.
- Display field có thể được tính ở server.
- Secret hoặc audit metadata không được công khai.

### 18.3. Projection không thay authorization

Việc không đưa field vào projection giúp giảm dữ liệu trả về, nhưng service vẫn cần kiểm tra quyền truy cập. Một query được sửa bởi người dùng không được phép tự chọn field bí mật chỉ bằng cách thêm nó vào projection.

### 18.4. Field theo role hoặc policy

Một projection có thể phụ thuộc policy:

~~~text
select {
  customer.id,
  customer.name,
  email: if canViewEmail(currentUser, customer)
    then customer.email
    else null
}
~~~

Nếu quyền là điều kiện bảo mật, nên kiểm tra ở service hoặc query policy có thẩm quyền. Không chỉ dựa vào biểu thức UI do client điều khiển.

### 18.5. Serialization naming

Alias output có thể được ánh xạ sang JSON field, XML element hoặc tên cột. Cần quy định camelCase, snake_case, case sensitivity và escaping.

### 18.6. Schema contract

Projection có thể được kiểm tra với named schema hoặc DTO type. Điều này giúp phát hiện thiếu field bắt buộc, sai kiểu và thay đổi không tương thích trước khi trả dữ liệu.

## 19. Tối ưu selection và projection

Query engine có thể tối ưu selection và projection để giảm lượng dữ liệu đọc và tính toán.

### 19.1. Predicate pushdown

Nếu nguồn là database hoặc remote service, engine có thể đẩy điều kiện where xuống nguồn để chỉ tải bản ghi cần thiết.

~~~text
from Order
where status == PAID and total > 100000
select { id, total }
~~~

Thay vì tải toàn bộ Order rồi lọc trong memory, query provider có thể chuyển predicate thành SQL WHERE.

### 19.2. Projection pushdown

Engine có thể chỉ yêu cầu các cột cần thiết:

~~~sql
SELECT id, total
FROM Orders
WHERE status = 'PAID' AND total > 100000;
~~~

Điều này giảm I/O, băng thông và bộ nhớ.

### 19.3. Predicate và projection dependency

Nếu projection cần một biểu thức dựa trên field taxRate, dù taxRate không xuất hiện trong kết quả cuối, query engine vẫn phải đọc nó để tính output.

Optimizer cần phân tích dependency của expression để không bỏ cột cần thiết.

### 19.4. Reordering

Với các phép toán thuần và tương đương, optimizer có thể đổi thứ tự filter hoặc đẩy filter qua projection. Nhưng phải bảo toàn:
- Null semantics.
- Exception behavior.
- Side effects.
- Evaluation order khi được đặc tả.
- Cardinality và duplicate.
- Collation và comparison semantics.

### 19.5. Projection pruning

Nếu consumer chỉ dùng một số field trong projection, compiler hoặc query planner có thể loại field không cần thiết. Điều này chỉ an toàn khi field bị loại không có side effect hoặc error behavior quan sát được.

### 19.6. Index

Selection thường hiệu quả hơn nếu predicate dùng field có index. DSL có thể cung cấp query plan hoặc hint, nhưng không nên buộc người dùng phải biết mọi chi tiết vật lý trong truy vấn nghiệp vụ.

### 19.7. Query plan

Workbench có thể hiển thị plan:

~~~text
Scan Orders
  |
  v
Filter status = PAID
  |
  v
Filter total > 100000
  |
  v
Project id, total
~~~

Plan thực tế có thể dùng index scan, join hoặc aggregate. Người dùng có thể xem ước lượng và thống kê nếu provider hỗ trợ.

## 20. Selection và projection trên dữ liệu phân tán

Một DSL có thể truy vấn nhiều nguồn: database, API, file hoặc event stream.

### 20.1. Source capability

Không phải nguồn nào cũng hỗ trợ cùng toán tử. Một API có thể hỗ trợ filter theo một số field nhưng không hỗ trợ arbitrary expression. File CSV có thể cần lọc trong memory.

Provider nên khai báo capability và query planner chọn cách thực thi phù hợp.

### 20.2. Pushdown và local execution

Một phần query có thể được đẩy xuống nguồn, phần còn lại thực thi local:

~~~text
Remote Source
  -> pushed filter
  -> fetched columns
  -> local projection
  -> final result
~~~

Cần kiểm soát số record tải về và không kéo dữ liệu quá lớn chỉ vì provider thiếu capability.

### 20.3. Distributed join

Join hai nguồn có thể yêu cầu đưa dữ liệu qua mạng hoặc thực hiện tại một engine trung gian. Query planner cần cân nhắc kích thước dữ liệu, vị trí nguồn và khả năng join.

### 20.4. Consistency

Nếu hai nguồn được đọc ở thời điểm khác nhau, kết quả có thể phản ánh snapshot không đồng nhất. DSL hoặc runtime cần xác định consistency guarantee nếu nghiệp vụ yêu cầu.

### 20.5. Partial failure

Một nguồn có thể timeout hoặc không khả dụng. Query cần quy định fail toàn bộ, trả partial result hay dùng fallback. Không nên âm thầm bỏ nguồn lỗi nếu điều đó làm kết quả sai.

## 21. Bảo mật và quyền riêng tư trong projection

Projection quyết định dữ liệu nào đi ra khỏi query. Đây là điểm quan trọng để giảm rò rỉ dữ liệu.

### 21.1. Data minimization

Chỉ chọn trường cần cho mục đích sử dụng. Nếu màn hình chỉ cần id và displayName, không nên lấy toàn bộ Customer record.

### 21.2. Field-level authorization

Một số field chỉ được đọc bởi vai trò nhất định. Query engine hoặc data service cần kiểm tra quyền trước khi trả field, ngay cả khi người dùng tự viết projection.

### 21.3. Masking

Có thể cung cấp hàm hoặc policy mask:

~~~text
select {
  customer.id,
  maskedEmail: maskEmail(customer.email)
}
~~~

Masking nên được thực thi ở lớp có thẩm quyền và có semantics rõ, không dựa vào một helper mà người dùng có thể bỏ qua.

### 21.4. Sensitive field propagation

Nếu projection tạo field từ dữ liệu nhạy cảm, output vẫn có thể được xem là nhạy cảm. Ví dụ, hash hoặc một phần số định danh vẫn có thể tiết lộ thông tin.

Metadata phân loại dữ liệu nên được truyền qua expression và projection nếu hệ thống có data lineage hoặc policy enforcement.

### 21.5. Injection và dynamic query

Nếu predicate hoặc projection được tạo bằng cách nối chuỗi từ input người dùng, có thể xuất hiện injection. Hãy dùng AST, parameter binding và query builder có kiểu thay vì ghép văn bản tùy tiện.

### 21.6. Giới hạn dữ liệu

Áp dụng giới hạn:
- Số bản ghi.
- Kích thước payload.
- Độ sâu nested projection.
- Số lượng field.
- Thời gian query.
- Số nguồn được truy cập.

Các giới hạn cần được thực thi ở runtime/provider, không chỉ hiển thị trong editor.

## 22. Diagnostic và lỗi trong selection/projection

Query có thể sai cú pháp, sai tên, sai kiểu hoặc có semantics không hợp lệ.

### 22.1. Lỗi trong predicate

Ví dụ:

~~~text
where order.total > "high"
~~~

Nếu total là Decimal và high là String, type checker nên báo lỗi so sánh không hợp lệ.

### 22.2. Lỗi trong projection

Ví dụ:

~~~text
select {
  id: order.id,
  total: order.unknownField
}
~~~

Name resolver cần chỉ ra unknownField không tồn tại trên kiểu Order.

### 22.3. Alias trùng

~~~text
select {
  value: order.total,
  value: order.tax
}
~~~

Nếu output record không cho phép field trùng, validator cần báo conflict.

### 22.4. Kiểu output không phù hợp

Nếu projection được gán cho OrderSummary nhưng thiếu field required, type checker cần báo trường thiếu hoặc sai kiểu.

### 22.5. Nullability mismatch

Nếu output yêu cầu String không nullable nhưng expression có thể trả null, cần báo lỗi hoặc yêu cầu default/coalescing rõ ràng.

### 22.6. Runtime error

Các lỗi như timeout, mất kết nối nguồn, permission denied hoặc dữ liệu không đúng schema cần được phân biệt với lỗi cú pháp. Diagnostic nên có source location của toán tử hoặc field liên quan.

## 23. Debugging và quan sát query

Khi query trả kết quả không đúng, cần quan sát cả số lượng bản ghi và giá trị trung gian.

### 23.1. Đếm sau mỗi bước

Một query pipeline có thể hiển thị:

~~~text
Source Order             10,000 rows
After status filter       4,200 rows
After amount filter       1,150 rows
After projection          1,150 records
After distinct            1,020 records
~~~

Số liệu minh họa. Nó giúp xác định bước nào loại nhiều record hoặc tạo duplicate.

### 23.2. Predicate breakdown

Với một record cụ thể:

~~~text
status == PAID           true
total >= minimum         false
customer.active          true
overall predicate        false
~~~

Đây là thông tin hữu ích để giải thích vì sao record không được chọn.

### 23.3. Projection preview

Workbench có thể hiển thị một số record đầu ra, kiểu field và giá trị null. Cần mask dữ liệu nhạy cảm và giới hạn số dòng.

### 23.4. Query explain

Explain có thể trình bày kế hoạch thực thi và các thao tác pushdown. Nó giúp người dùng hiểu tại sao một query chậm hoặc tải nhiều dữ liệu.

### 23.5. Tránh debug làm thay đổi kết quả

Preview và watch nên tránh gọi function có side effect hoặc đọc nguồn theo cách khác với query thật. Dùng snapshot hoặc execution plan có kiểm soát khi cần tái hiện chính xác.

## 24. Ví dụ tổng hợp: báo cáo đơn hàng theo khách hàng

Giả sử có các kiểu:

~~~text
entity Customer {
  id: CustomerId
  name: String
  active: Boolean
}

entity Order {
  id: OrderId
  customerId: CustomerId
  status: OrderStatus
  total: Decimal
  createdAt: Instant
}
~~~

Yêu cầu: lấy các khách hàng đang hoạt động có ít nhất một đơn đã thanh toán trong khoảng thời gian xác định; trả về mã khách hàng, tên, số đơn và tổng chi tiêu.

### 24.1. Query minh họa

~~~text
from Customer as customer
where customer.active
select {
  customerId: customer.id,
  customerName: customer.name,
  paidOrders: (
    from Order as order
    where order.customerId == customer.id
      and order.status == PAID
      and order.createdAt >= periodStart
      and order.createdAt < periodEnd
    select {
      order.id,
      order.total
    }
  )
}
where paidOrders.count() > 0
select {
  customerId,
  customerName,
  orderCount: paidOrders.count(),
  totalSpent: paidOrders.sum(order => order.total)
}
~~~

Đây là cú pháp minh họa để thể hiện hai giai đoạn projection. Một DSL cụ thể có thể yêu cầu let, subquery hoặc grouping thay vì dùng alias projection trong bước lọc tiếp theo.

### 24.2. Cách hiểu từng bước

1. Nguồn là Customer.
2. Selection đầu tiên giữ khách hàng active.
3. Với mỗi khách hàng, subquery tìm các Order đã thanh toán trong khoảng thời gian.
4. Projection con chỉ giữ id và total.
5. Selection tiếp theo giữ khách hàng có ít nhất một đơn.
6. Projection cuối tạo báo cáo với số đơn và tổng chi tiêu.

### 24.3. Phiên bản dùng grouping

Nếu query engine hỗ trợ join và grouping, có thể diễn đạt trực tiếp:

~~~text
from Customer as customer
join Order as order on order.customerId == customer.id
where customer.active
  and order.status == PAID
  and order.createdAt >= periodStart
  and order.createdAt < periodEnd
group by {
  customer.id,
  customer.name
}
select {
  customerId: group.key.id,
  customerName: group.key.name,
  orderCount: group.count(),
  totalSpent: group.sum(order.total)
}
~~~

### 24.4. Kiểu kết quả

Projection cuối có thể tạo:

~~~text
CustomerSpendingReport {
  customerId: CustomerId,
  customerName: String,
  orderCount: Integer,
  totalSpent: Decimal
}
~~~

### 24.5. Các điểm cần kiểm tra

- periodStart phải nhỏ hơn periodEnd.
- Khoảng thời gian dùng quy ước timezone rõ.
- Decimal giữ precision.
- Customer active được kiểm tra theo đúng thời điểm nghiệp vụ.
- Chỉ đơn thuộc trạng thái PAID được tính.
- Khách không có đơn bị loại theo yêu cầu.
- Query có index phù hợp trên customerId, status và createdAt.
- Người dùng chỉ được xem khách hàng trong phạm vi quyền của họ.

Ví dụ này minh họa cách selection, projection, join, grouping và aggregate phối hợp để tạo kết quả theo mục đích nghiệp vụ.

## 25. Các lỗi thiết kế thường gặp

**Nhầm where với select.** Điều kiện lọc quyết định record nào được giữ; projection quyết định cấu trúc output. Tách hai vai trò giúp query dễ đọc.

**Chọn toàn bộ entity khi chỉ cần vài field.** Điều này tăng I/O và có thể làm lộ dữ liệu. Hãy projection đúng trường cần thiết.

**Không đặt alias cho field trùng tên.** Join nhiều nguồn có thể tạo tên output mơ hồ. Hãy dùng alias tường minh.

**Cho phép projection thay đổi entity nguồn.** Projection nên tạo kết quả mới trừ khi DSL có một thao tác update riêng. Tránh nhầm query đọc với lệnh ghi.

**Không định nghĩa null semantics.** Null trong predicate, left join và projection có thể tạo kết quả khó đoán. Hãy quy định Boolean logic và nullability.

**Bỏ qua thứ tự đánh giá.** Đổi thứ tự predicate có thể làm lỗi null hoặc side effect xuất hiện khác. Hãy xác định short-circuit và purity.

**Giả định projection tự loại duplicate.** Nhiều record nguồn có thể tạo output giống nhau. Chỉ dùng distinct khi yêu cầu semantics rõ.

**Dùng alias không ổn định.** Consumer có thể phụ thuộc vào tên field tự suy luận. Hãy dùng alias hoặc named projection cho contract quan trọng.

**Trả nested object quá sâu.** Payload lớn, query tốn kém và có thể tạo vòng tham chiếu. Hãy giới hạn độ sâu và chọn field cần thiết.

**Tính subquery riêng cho từng record.** Có thể tạo N+1 query. Hãy xem query plan và dùng join hoặc batch khi semantics cho phép.

**Đẩy predicate xuống nguồn mà đổi semantics.** Collation, null, timezone và function behavior của database có thể khác DSL. Provider phải chỉ pushdown biểu thức tương đương.

**Dựa vào selection để bảo mật.** Predicate do người dùng điều khiển không thay thế authorization. Kiểm tra quyền ở service hoặc data provider.

**Không kiểm thử output type.** Projection có thể tạo field thiếu, sai kiểu hoặc nullable ngoài dự kiến. Hãy type-check và validate với schema kết quả.

## 26. Quy trình thiết kế selection và projection cho DSL

Khi xây dựng query feature, có thể thực hiện theo trình tự:

### Bước 1: Xác định mô hình nguồn

Quy định from nhận entity, collection, stream, table hay query con. Xác định alias và cách resolve field.

### Bước 2: Định nghĩa semantics của predicate

Quy định kiểu Boolean, null logic, precedence, short-circuit, exception và hàm được phép dùng.

### Bước 3: Định nghĩa projection grammar

Quy định projection có thể chứa field, alias, literal, expression, nested object, collection và named type hay không.

### Bước 4: Thiết kế type inference

Suy ra kiểu của từng output field, nullability, collection và record. Kiểm tra tương thích với DTO hoặc schema đích.

### Bước 5: Xác định duplicate và ordering

Quy định multiplicity, distinct, stable ordering và cách pagination tương tác với projection.

### Bước 6: Hỗ trợ join và nested query

Xác định scope alias, correlated reference, null từ outer join và cardinality của subquery.

### Bước 7: Tạo query plan

Tách logical operators khỏi provider execution. Hỗ trợ pushdown khi semantics tương đương và provider có capability.

### Bước 8: Kiểm soát bảo mật

Áp dụng field-level authorization, masking, data minimization, parameter binding và giới hạn tài nguyên.

### Bước 9: Cung cấp diagnostics và explain

Hiển thị lỗi cú pháp, tên, kiểu, nullability và query plan. Hỗ trợ preview kết quả có giới hạn.

### Bước 10: Kiểm thử

Kiểm tra tập dữ liệu rỗng, null, duplicate, join, grouping, nested projection, pagination, provider khác nhau, security và performance.

## 27. Kết luận

Selection và projection là hai phép biến đổi cốt lõi của DSL truy vấn. Selection dùng predicate để quyết định bản ghi nào được giữ lại; projection tạo hình dạng kết quả bằng cách chọn trường, đặt alias, tính expression hoặc tạo record lồng nhau. Khi kết hợp với join, grouping, aggregate, distinct, ordering và pagination, chúng tạo nên khả năng truy vấn dữ liệu linh hoạt.

Một DSL tốt cần quy định rõ predicate semantics, null và short-circuit, scope alias, kiểu kết quả, duplicate, thứ tự và hành vi của subquery. Query planner có thể tối ưu bằng predicate pushdown, projection pushdown và projection pruning, nhưng mọi tối ưu phải giữ nguyên semantics của ngôn ngữ. Projection cũng là ranh giới quan trọng cho data minimization và field-level authorization.

Hãy chọn đúng những bản ghi cần xử lý và chỉ chiếu những thông tin cần trả về. Khi hai thao tác có ngữ nghĩa rõ, type checker và query planner hiểu được chúng, truy vấn DSL sẽ dễ đọc, an toàn, hiệu quả và dễ kiểm thử hơn.


# Kiểu kết quả trong DSL truy vấn

Ngôn ngữ đặc tả miền dùng cho truy vấn (Query DSL) cho phép mô tả dữ liệu cần lấy bằng cú pháp gần với mô hình miền. Khi một truy vấn được thực thi, hệ thống không chỉ cần biết truy vấn đọc từ đâu và lọc theo điều kiện nào; nó còn phải xác định **kết quả có kiểu gì, chứa bao nhiêu phần tử, có thể vắng mặt hay không và được biểu diễn như thế nào**.

**Kiểu kết quả** (*result type*) mô tả hình dạng và ngữ nghĩa của giá trị mà một truy vấn trả về. Một truy vấn có thể trả một số, một chuỗi, một bản ghi, một hàng dữ liệu, một tập hợp, một cây lồng nhau, một luồng phần tử hoặc một kết quả có thể thành công hay thất bại. Việc xác định kiểu kết quả giúp compiler kiểm tra biểu thức phía sau, editor gợi ý thuộc tính, runtime cấp phát đúng cấu trúc và API tuần tự hóa dữ liệu nhất quán.

Trong DSL truy vấn, kiểu kết quả thường được suy ra từ projection, nguồn dữ liệu, phép join, phép nhóm, hàm tổng hợp và các toán tử chuyển đổi. Một truy vấn lấy một trường có thể trả scalar; truy vấn chọn nhiều trường có thể trả record; truy vấn không có giới hạn số dòng có thể trả collection; truy vấn streaming có thể trả sequence được đọc dần. Những khác biệt này ảnh hưởng trực tiếp đến cách chương trình sử dụng dữ liệu.

## 1. Kiểu kết quả là gì?

### 1.1. Định nghĩa

Kiểu kết quả mô tả loại giá trị mà biểu thức truy vấn tạo ra. Nó trả lời các câu hỏi:

- Giá trị là scalar hay một cấu trúc gồm nhiều trường?
- Truy vấn trả một phần tử hay nhiều phần tử?
- Phần tử có thể không tồn tại không?
- Một trường có thể null hoặc vắng mặt không?
- Kết quả có thứ tự không?
- Kết quả được tính ngay hay đọc dần?
- Có metadata như tổng số dòng, cursor hoặc trạng thái phân trang không?
- Truy vấn có thể thất bại và lỗi được biểu diễn ra sao?

Ví dụ:

~~~text
query customerName:
    from Customer
    where id == input.customerId
    select name
~~~

Nếu name có kiểu String và truy vấn chỉ tìm tối đa một Customer, kết quả có thể là Optional<String>, Nullable<String> hoặc Result<Option<String>, QueryError>, tùy hệ kiểu và chính sách DSL.

### 1.2. Kiểu nguồn khác kiểu kết quả

Kiểu nguồn mô tả dữ liệu đầu vào của truy vấn. Kiểu kết quả mô tả dữ liệu sau khi projection và các phép toán được áp dụng.

Ví dụ:

~~~text
from Order
where status == PAID
select customer.name
~~~

Nguồn là Order. Biểu thức projection lấy thuộc tính customer.name, nên kiểu phần tử đầu ra có thể là String hoặc Optional<String>. Nếu truy vấn trả nhiều đơn hàng, kiểu toàn bộ kết quả có thể là List<String> hoặc một collection tương đương.

### 1.3. Kiểu kết quả là hợp đồng

Kiểu kết quả là hợp đồng giữa query producer và consumer:

- Query producer là compiler, runtime hoặc dịch vụ thực thi truy vấn.
- Consumer là đoạn DSL tiếp theo, ứng dụng, API hoặc giao diện sử dụng kết quả.

Nếu kiểu kết quả thay đổi, consumer có thể phải thay đổi theo. Ví dụ, đổi từ một Customer sang List<Customer> làm thay đổi cách truy cập thuộc tính, vòng lặp và xử lý trường hợp không có dữ liệu.

### 1.4. Kiểu tĩnh và kiểu động

DSL có thể xác định kiểu kết quả trước khi chạy hoặc chỉ xác định đầy đủ khi thực thi:

- Kiểu tĩnh: compiler suy ra hoặc kiểm tra kiểu từ schema và biểu thức.
- Kiểu động: runtime quyết định kiểu dựa trên dữ liệu thực tế.
- Kiểu lai: compiler biết cấu trúc tổng quát, runtime kiểm tra một số chi tiết như union tag hoặc kiểu dữ liệu từ nguồn bên ngoài.

Kiểu tĩnh giúp phát hiện lỗi sớm và hỗ trợ IDE tốt hơn. Kiểu động linh hoạt với dữ liệu không có schema cố định nhưng cần kiểm tra runtime.

## 2. Các chiều của kiểu kết quả

Không nên xem kiểu kết quả chỉ là tên một kiểu dữ liệu. Nó thường kết hợp nhiều chiều:

| Chiều | Câu hỏi | Ví dụ |
|---|---|---|
| Shape | Giá trị có hình dạng gì? | Scalar, record, tuple |
| Cardinality | Có bao nhiêu phần tử? | Exactly one, zero-or-one, many |
| Nullability | Giá trị có thể null không? | String, Nullable<String> |
| Ordering | Phần tử có thứ tự không? | List, Set |
| Evaluation | Tính ngay hay đọc dần? | Materialized list, Stream |
| Error | Lỗi được biểu diễn thế nào? | Exception, Result |
| Metadata | Có thông tin phụ nào? | Count, cursor, warnings |

Hai truy vấn có thể cùng trả Record nhưng khác cardinality. Một truy vấn trả một Record duy nhất khác truy vấn trả List<Record>. Tương tự, List<String> khác List<Nullable<String>> vì khả năng vắng mặt nằm ở cấp phần tử chứ không phải toàn collection.

## 3. Scalar result

### 3.1. Scalar là gì?

Scalar result là một giá trị đơn không được xem như một bản ghi gồm nhiều trường. Các kiểu scalar thường gặp:

- Boolean.
- Integer và Decimal.
- String.
- Date, Time và Timestamp.
- UUID hoặc định danh miền.
- Money, Duration và các kiểu giá trị miền khác.

Ví dụ:

~~~text
query paidOrderCount:
    from Order
    where status == PAID
    select count()
~~~

Kiểu kết quả có thể là Integer hoặc Long tùy miền giá trị và hợp đồng của hàm count.

### 3.2. Scalar projection

Projection chọn một biểu thức:

~~~text
from Customer
select email
~~~

Kiểu phần tử kết quả được suy ra từ email. Nếu Customer.email là String thì phần tử có kiểu String; nếu email có thể thiếu thì phần tử có thể là Optional<String> hoặc Nullable<String>.

### 3.3. Scalar query và nhiều dòng

Chọn một trường không có nghĩa truy vấn chỉ trả một giá trị. Nếu nguồn có nhiều Customer, truy vấn có thể trả nhiều String:

~~~text
List<String> names =
    from Customer
    select name
~~~

Cần phân biệt kiểu của mỗi phần tử với kiểu của toàn bộ kết quả.

### 3.4. Scalar aggregate

Các hàm như count, sum, average, min và max có thể trả scalar. Kiểu kết quả phụ thuộc vào kiểu đầu vào và quy tắc aggregate:

| Hàm | Đầu vào | Kiểu kết quả thường gặp |
|---|---|---|
| count | Collection hoặc group | Integer/Long |
| sum | Integer | Integer hoặc Long |
| sum | Decimal | Decimal |
| average | Numeric | Decimal |
| min/max | Comparable<T> | T hoặc Optional<T> |
| any/all | Boolean collection | Boolean |

Đây là các quy ước phổ biến; DSL phải định nghĩa cụ thể cách xử lý collection rỗng, null và overflow.

## 4. Record result

### 4.1. Record là gì?

Record là cấu trúc có các trường được đặt tên. Nó phù hợp khi truy vấn chọn nhiều thuộc tính:

~~~text
from Customer
select {
    id: id,
    displayName: name,
    email: email
}
~~~

Kiểu kết quả có thể được suy ra thành:

~~~text
Record<
    id: CustomerId,
    displayName: String,
    email: Optional<String>
>
~~~

Record giúp consumer truy cập trường bằng tên thay vì nhớ vị trí.

### 4.2. Record anonymous và named

Một số DSL tạo anonymous record trực tiếp từ projection. DSL khác cho phép khai báo kiểu kết quả có tên:

~~~text
type CustomerSummary = {
    id: CustomerId,
    name: String,
    orderCount: Long
}
~~~

Truy vấn có thể khai báo:

~~~text
query customerSummaries: List<CustomerSummary>
~~~

Kiểu có tên dễ tái sử dụng trong nhiều query, API và module. Anonymous record thuận tiện cho projection cục bộ.

### 4.3. Tên trường và alias

Hai nguồn có thể có trường cùng tên. Projection cần alias để tránh xung đột:

~~~text
from Order
join Customer on Order.customerId == Customer.id
select {
    orderId: Order.id,
    customerId: Customer.id,
    customerName: Customer.name
}
~~~

Nếu không đặt alias, compiler cần có quy tắc xử lý tên trùng, chẳng hạn yêu cầu alias tường minh thay vì tự đổi tên khó đoán.

### 4.4. Kiểu trường và thứ tự

Record thường được truy cập theo tên. Một số định dạng serialization vẫn giữ thứ tự trường để ổn định output hoặc hỗ trợ tương thích. Tuy nhiên, semantics của record cần quy định rõ việc thứ tự có ảnh hưởng đến equality hay không.

### 4.5. Record lồng nhau

Projection có thể tạo cấu trúc lồng:

~~~text
select {
    orderId: id,
    customer: {
        name: customer.name,
        email: customer.email
    },
    totals: {
        subtotal: subtotal,
        tax: tax
    }
}
~~~

Kiểu kết quả phản ánh cấu trúc lồng nhau. Consumer có thể truy cập result.customer.name nếu customer tồn tại.

## 5. Tuple result

### 5.1. Tuple là gì?

Tuple là một cấu trúc có số lượng phần tử cố định, truy cập theo vị trí hoặc tên tùy DSL. Ví dụ:

~~~text
select (customer.id, customer.name)
~~~

Kiểu có thể là Tuple<CustomerId, String>.

### 5.2. Tuple và record

Tuple phù hợp với một nhóm giá trị nhỏ, thường dùng cục bộ. Record phù hợp khi từng thành phần có ý nghĩa riêng và cần truy cập bằng tên.

| Đặc điểm | Tuple | Record |
|---|---|---|
| Truy cập | Theo vị trí hoặc tên | Theo tên |
| Hợp đồng | Thứ tự phần tử quan trọng nếu positional | Tên trường quan trọng |
| Tái sử dụng | Thường cục bộ | Dễ đặt tên và tái sử dụng |
| Rủi ro | Đổi thứ tự làm thay đổi ý nghĩa | Đổi tên trường ảnh hưởng consumer |

### 5.3. Tuple trong join

Một query có thể trả cặp đối tượng:

~~~text
from Order
join Customer on Order.customerId == Customer.id
select (Order, Customer)
~~~

Kiểu phần tử là Tuple<Order, Customer>. Nếu join có thể không tìm thấy Customer, thành phần thứ hai có thể là Optional<Customer>.

## 6. Row và table result

### 6.1. Row

Row thường biểu diễn một hàng trong kết quả quan hệ. Nó có thể được mô hình hóa như record có schema xác định.

~~~text
Row<
    orderId: OrderId,
    amount: Money,
    status: OrderStatus
>
~~~

### 6.2. Table

Table result là tập hợp các row có cùng schema. Ví dụ:

~~~text
Table<OrderRow>
~~~

Table có thể mang semantics gần với quan hệ dữ liệu: các row cùng cấu trúc, phép chiếu và lọc tạo table mới.

### 6.3. Row và domain entity

Row không nhất thiết là entity miền đầy đủ. Một projection có thể chỉ lấy một số trường, nên kết quả không có đầy đủ invariant hoặc hành vi của Customer hay Order.

Không nên gán một partial row vào entity đầy đủ nếu chưa có quy tắc mapping rõ.

### 6.4. Schema của table result

Schema cần mô tả:

- Tên cột.
- Kiểu dữ liệu.
- Nullability.
- Precision và scale.
- Đơn vị hoặc semantic type.
- Thứ tự cột nếu định dạng yêu cầu.
- Metadata về nguồn nếu cần.

### 6.5. Table và collection

Table thường có schema đồng nhất và có thể hỗ trợ operation quan hệ. Collection tổng quát có thể chứa object bất kỳ, có thể có semantics khác về thứ tự và uniqueness.

## 7. Collection result và cardinality

### 7.1. Collection là gì?

Collection result chứa nhiều phần tử cùng kiểu phần tử:

~~~text
List<Customer>
Set<CustomerId>
Sequence<Money>
~~~

Kiểu phần tử và kiểu collection là hai lớp riêng. Ví dụ, List<Optional<Customer>> biểu diễn nhiều vị trí, mỗi vị trí có thể không có Customer; Optional<List<Customer>> biểu diễn một collection có thể hoàn toàn vắng mặt.

### 7.2. Cardinality

Cardinality mô tả số phần tử có thể xuất hiện:

| Cardinality | Ký hiệu khái niệm | Kiểu có thể dùng |
|---|---|---|
| Chính xác một | 1 | T |
| Không hoặc một | 0..1 | Optional<T> |
| Một hoặc nhiều | 1..N | NonEmptyList<T> |
| Không hoặc nhiều | 0..N | List<T> |
| Tối đa N | 0..N | BoundedList<T> |

Tên kiểu và cách biểu diễn tùy DSL. Cardinality có thể được kiểm tra tĩnh nếu truy vấn và schema cho phép suy luận, hoặc chỉ xác nhận lúc chạy.

### 7.3. Query trả nhiều phần tử

~~~text
query activeCustomers:
    from Customer
    where active == true
    select Customer
~~~

Kết quả thường là List<Customer>, Set<Customer> hoặc QueryResult<Customer>. Việc chọn kiểu nào phụ thuộc thứ tự, uniqueness và cách thực thi.

### 7.4. Query trả tối đa một phần tử

Nếu điều kiện dựa trên khóa duy nhất:

~~~text
query customerById(id: CustomerId):
    from Customer
    where id == input.id
    select Customer
    singleOrNone
~~~

Kết quả có thể là Optional<Customer>. Nếu khóa không thực sự duy nhất, query có thể vi phạm cardinality khi dữ liệu không hợp lệ.

### 7.5. Query yêu cầu đúng một phần tử

Một query có thể yêu cầu:

~~~text
single Customer where id == input.id
~~~

Khi không có dòng hoặc có nhiều hơn một dòng, runtime cần trả lỗi cardinality. Kiểu T biểu thị một giá trị duy nhất, nhưng điều kiện đó phải được bảo đảm bởi schema hoặc kiểm tra runtime.

### 7.6. Non-empty collection

Nếu query có điều kiện bảo đảm ít nhất một phần tử, hệ kiểu có thể dùng NonEmptyList<T>. Nếu bảo đảm này chỉ dựa trên dữ liệu runtime, constructor hoặc validator cần xác nhận trước khi tạo giá trị.

## 8. List, Set, Bag và Sequence

### 8.1. List

List là collection có thứ tự, có thể chứa phần tử trùng:

~~~text
List<String>
~~~

Thứ tự có thể đến từ ORDER BY hoặc semantics của nguồn. Nếu query không có order, không nên giả định kết quả có thứ tự ổn định.

### 8.2. Set

Set biểu diễn tập hợp phần tử duy nhất. Equality và hashing của phần tử ảnh hưởng việc loại trùng.

~~~text
Set<CustomerId>
~~~

Nếu kiểu CustomerId không có equality ổn định, semantics của Set cần được định nghĩa qua key selector hoặc equality provider.

### 8.3. Bag hoặc multiset

Bag cho phép phần tử trùng nhưng không nhất thiết có thứ tự. Trong truy vấn quan hệ, kết quả thường có semantics bag vì hai row giống nhau vẫn có thể xuất hiện nhiều lần sau join.

### 8.4. Sequence

Sequence là chuỗi phần tử có thứ tự, có thể được tính lười. Nó phù hợp với pipeline biến đổi dữ liệu hoặc nguồn lớn.

### 8.5. Phân biệt kiểu collection

| Kiểu | Có thứ tự | Cho phép trùng | Có thể lazy |
|---|---|---|---|
| List | Có | Có | Tùy implementation |
| Set | Không nhất thiết | Không | Có thể |
| Bag | Không nhất thiết | Có | Có thể |
| Sequence | Có | Có | Thường có |
| Table | Theo query order nếu xác định | Thường có | Tùy engine |

DSL cần chọn semantics phù hợp thay vì dùng từ collection chung chung cho mọi trường hợp.

## 9. Optional, null và giá trị vắng mặt

### 9.1. Nullability

Một trường nullable có thể chứa giá trị hoặc null. Ví dụ:

~~~text
Customer.email: Nullable<String>
~~~

Nullability thuộc về kiểu của trường hoặc phần tử, không đồng nghĩa với việc cả truy vấn không tìm thấy dòng.

### 9.2. Optional

Optional<T> thường biểu diễn một giá trị có thể không tồn tại:

~~~text
Optional<Customer>
~~~

Nó thường phù hợp với query trả zero-or-one. Optional không nhất thiết cho phép giá trị null bên trong; nhiều hệ kiểu dùng Optional để tránh hai dạng vắng mặt chồng lấn.

### 9.3. Phân biệt không có dòng và trường null

Giả sử query tìm một customer nhưng email là null:

- Không có Customer: kết quả không có entity.
- Có Customer, email null: entity tồn tại nhưng trường email vắng mặt.

Hai tình huống này khác nhau:

~~~text
Optional<Customer>
Customer { email: Nullable<String> }
~~~

### 9.4. Optional lồng Nullable

Một kiểu như Optional<Nullable<String>> có thể biểu diễn ba trạng thái:

1. Không có record.
2. Có record nhưng trường null.
3. Có record và trường có giá trị.

Nếu DSL cho phép kiểu này, cần giải thích cách unwrap và serialize. Một số hệ thống chọn kiểu riêng như MissingOrNull<T> để làm rõ ba trạng thái.

### 9.5. SQL NULL và logic ba giá trị

Trong SQL, so sánh với NULL thường tạo UNKNOWN thay vì TRUE hoặc FALSE. DSL truy vấn ánh xạ sang SQL cần xác định có giữ semantics này hay dùng Boolean hai giá trị với Optional rõ ràng.

Ví dụ:

~~~text
email == null
~~~

Không thể giả định mọi backend sẽ xử lý giống nhau nếu DSL không định nghĩa semantics chuẩn.

### 9.6. Null propagation

Một số DSL cho phép biểu thức truy cập thuộc tính qua giá trị nullable và tự lan truyền null. DSL khác yêu cầu null-safe navigation hoặc unwrap tường minh. Quy tắc này ảnh hưởng kiểu kết quả:

~~~text
customer?.address?.city
~~~

Kết quả có thể là Optional<String> ngay cả khi city vốn là String.

## 10. Kết quả của JOIN

### 10.1. Inner join

Inner join chỉ giữ những cặp dòng có khóa khớp:

~~~text
from Order
join Customer on Order.customerId == Customer.id
select {
    orderId: Order.id,
    customerName: Customer.name
}
~~~

Mỗi kết quả chứa các trường được projection từ cả hai phía. Kiểu phần tử có thể là record gồm orderId và customerName.

### 10.2. Left outer join

Left join giữ dòng bên trái dù không có dòng bên phải. Vì vậy, các trường lấy từ phía phải có thể trở thành Optional hoặc Nullable:

~~~text
from Customer
leftJoin Order on Customer.id == Order.customerId
select {
    customer: Customer,
    order: Optional<Order>
}
~~~

Kiểu kết quả cần phản ánh rằng Order có thể vắng mặt.

### 10.3. One-to-many join

Một Customer có thể có nhiều Order. DSL có thể trả một dòng cho mỗi cặp Customer-Order hoặc gom các Order vào collection lồng nhau:

~~~text
select {
    customer: Customer,
    orders: List<Order>
}
~~~

Hai hình dạng có semantics khác nhau và ảnh hưởng số dòng cũng như kích thước kết quả.

### 10.4. Join và duplicate

Join có thể nhân số dòng. Nếu một Order khớp nhiều record ở bảng liên quan, query có thể tạo nhiều kết quả. Không nên tự loại trùng trừ khi DISTINCT hoặc semantics tương đương được yêu cầu.

### 10.5. Kiểu kết quả của join

Compiler cần suy ra:

- Kiểu của từng phía.
- Nullability từ outer join.
- Cardinality của quan hệ.
- Shape của projection.
- Có gom nhóm thành nested collection hay không.

Schema relationship như one-to-one, one-to-many và many-to-many có thể hỗ trợ suy luận cardinality.

## 11. Projection và kiểu kết quả

### 11.1. Projection là gì?

Projection xác định những giá trị được lấy ra từ mỗi phần tử nguồn. Nó quyết định shape của phần tử kết quả.

~~~text
from Order
select total
~~~

trả scalar Money cho mỗi Order.

~~~text
from Order
select {
    id: id,
    total: total
}
~~~

trả record cho mỗi Order.

### 11.2. Projection toàn đối tượng

~~~text
from Customer
select Customer
~~~

Kết quả có thể là collection của entity đầy đủ. Một số engine trả object materialized; engine khác trả proxy hoặc record dữ liệu. Kiểu công bố cần phản ánh contract thực tế.

### 11.3. Projection một phần

~~~text
from Customer
select {
    id: id,
    name: name
}
~~~

Đây là projection một phần. Không nên coi kết quả là Customer đầy đủ nếu thiếu email, tier hoặc invariant khác.

### 11.4. Projection biểu thức

Projection có thể tính giá trị:

~~~text
from Order
select {
    id: id,
    totalWithTax: total * 1.08
}
~~~

Kiểu totalWithTax được suy ra từ kiểu Money và Decimal theo quy tắc toán tử.

### 11.5. Projection lồng

Nested projection tạo cây kết quả, thường hữu ích cho API hoặc báo cáo:

~~~text
from Customer
select {
    id: id,
    profile: {
        name: name,
        contact: {
            email: email,
            phone: phone
        }
    }
}
~~~

### 11.6. Alias và kiểu trường

Alias xác định tên trường đầu ra. Kiểu của mỗi trường được suy ra từ biểu thức tương ứng, gồm nullability, precision và semantic type.

## 12. Aggregate và grouped result

### 12.1. Aggregate result

Aggregate biến nhiều phần tử thành một giá trị:

~~~text
from Order
where status == PAID
select sum(total)
~~~

Kiểu kết quả có thể là Money.

### 12.2. Aggregate theo nhóm

~~~text
from Order
groupBy customerId
select {
    customerId: key,
    orderCount: count(),
    revenue: sum(total)
}
~~~

Kết quả là collection các record nhóm. Mỗi record chứa key và các giá trị aggregate.

### 12.3. Group object

Một số DSL trả Group<K, T> để consumer có thể truy cập key và các phần tử trong nhóm. DSL khác chỉ trả projection của key và aggregate.

### 12.4. Aggregate trên collection rỗng

Hàm count thường trả 0 với collection rỗng. Sum có thể trả 0 hoặc null tùy đặc tả. Average, min và max thường không có giá trị nếu không có phần tử.

Không nên để hành vi này phụ thuộc vào database backend.

### 12.5. Kiểu numeric của aggregate

Sum trên Integer có thể trả Long để giảm nguy cơ overflow. Average thường cần Decimal dù đầu vào là Integer. Precision, scale và rounding cần được quy định.

### 12.6. Group cardinality

Số nhóm không nhất thiết bằng số phần tử đầu vào. Mỗi key khác nhau tạo một group. Nếu có filter trước groupBy, nhóm có thể không xuất hiện.

## 13. Ordering, limit và pagination

### 13.1. ORDER BY

Order by xác định thứ tự kết quả:

~~~text
from Order
orderBy createdAt descending
select Order
~~~

Nếu không có order by, không nên giả định thứ tự dòng ổn định, kể cả khi một backend thường trả theo thứ tự vật lý.

### 13.2. LIMIT và OFFSET

~~~text
from Order
orderBy createdAt descending
limit 20
offset 40
select Order
~~~

Kiểu phần tử vẫn là Order, nhưng collection chỉ chứa một trang con. Metadata có thể cần cho biết offset và page size.

### 13.3. Page result

Một kiểu Page<T> có thể chứa:

~~~text
Page<T> {
    items: List<T>,
    pageNumber: Integer,
    pageSize: Integer,
    totalElements: Optional<Long>,
    totalPages: Optional<Integer>
}
~~~

Tổng số phần tử có thể không được tính nếu query chỉ dùng cursor hoặc backend không cung cấp count hiệu quả.

### 13.4. Cursor result

Cursor pagination thường trả:

~~~text
CursorPage<T> {
    items: List<T>,
    nextCursor: Optional<String>,
    hasMore: Boolean
}
~~~

Cursor là token opaque; consumer không nên tự diễn giải nếu contract không công bố định dạng.

### 13.5. Pagination và ordering ổn định

Nếu dữ liệu thay đổi trong lúc người dùng đọc nhiều trang, offset pagination có thể bỏ sót hoặc lặp phần tử. Cursor dựa trên thứ tự ổn định có thể giảm vấn đề này.

### 13.6. Cardinality của page

Một trang có thể chứa ít hơn pageSize phần tử. Page result vẫn tồn tại ngay cả khi items rỗng. Điều này khác Optional<Page<T>>, biểu diễn trường hợp không có page result.

## 14. Streaming và lazy result

### 14.1. Streaming result

Với dữ liệu lớn, không nhất thiết tải toàn bộ kết quả vào bộ nhớ. Query có thể trả Stream<T>, Iterator<T> hoặc AsyncSequence<T>.

~~~text
stream from Event
where occurredAt >= input.start
select Event
~~~

Consumer đọc từng phần tử khi cần.

### 14.2. Eager và lazy

Eager evaluation tính và materialize kết quả trước khi trả về. Lazy evaluation trì hoãn việc đọc hoặc tính phần tử cho đến khi consumer yêu cầu.

| Đặc điểm | Eager collection | Lazy stream |
|---|---|---|
| Thời điểm đọc | Trước khi trả kết quả | Khi consumer duyệt |
| Bộ nhớ | Có thể cao | Có thể thấp hơn |
| Lỗi | Có thể xuất hiện lúc thực thi query | Có thể xuất hiện giữa lúc duyệt |
| Resource lifetime | Thường ngắn hơn | Có thể kéo dài |
| Retry | Có thể chạy lại toàn query | Cần quy tắc cursor hoặc stream |

### 14.3. Resource lifetime

Stream có thể giữ connection, cursor hoặc transaction mở. Consumer phải đóng hoặc tiêu thụ stream theo hợp đồng để tránh rò rỉ tài nguyên.

### 14.4. Backpressure

Với stream bất đồng bộ, consumer có thể xử lý chậm hơn producer. Backpressure giúp giới hạn lượng dữ liệu đang chờ và tránh làm cạn bộ nhớ.

### 14.5. Cancellation

Nếu consumer không cần kết quả nữa, cần hủy query hoặc đóng cursor. Backend nên hỗ trợ cancellation để ngừng đọc dữ liệu và giải phóng resource.

### 14.6. Streaming aggregate

Một số aggregate có thể tính tăng dần như count hoặc sum. Các phép toán cần giữ toàn bộ dữ liệu như sort toàn cục có thể cần buffer hoặc external sort.

### 14.7. Snapshot consistency

Stream dài có thể đọc dữ liệu thay đổi trong lúc duyệt. DSL cần xác định kết quả phản ánh snapshot tại thời điểm bắt đầu, read committed hay một consistency model khác.

## 15. Nested collection và hierarchical result

### 15.1. Nested result

Một query có thể trả cây dữ liệu:

~~~text
CustomerResult {
    id: CustomerId,
    orders: List<OrderSummary>
}
~~~

Đây là hình dạng phổ biến khi xây API hoặc báo cáo.

### 15.2. Flat join và nested projection

Flat join trả một dòng cho mỗi cặp liên kết. Nested projection gom nhiều dòng con vào một collection bên trong record cha.

Hai dạng có thể mang cùng thông tin nhưng khác cardinality, serialization và cách tiêu thụ.

### 15.3. Nhiều cấp lồng nhau

~~~text
Customer
  -> Orders[]
       -> Lines[]
            -> Product
~~~

Kiểu kết quả cần phản ánh nullability và cardinality ở từng cấp. Ví dụ một Customer có thể không có Order; một Order có thể có nhiều Line; Product có thể optional nếu tham chiếu không còn hợp lệ.

### 15.4. Tránh n+1 query

Nested result có thể được thực hiện bằng một query join, batch fetch hoặc nhiều query lồng nhau. Kiểu kết quả không tự quyết định kế hoạch thực thi. Query planner cần chọn chiến lược tránh quá nhiều round trip.

### 15.5. Giới hạn độ sâu

Nested projection quá sâu có thể tạo payload lớn và khó kiểm soát. DSL có thể hỗ trợ giới hạn depth, field selection hoặc expansion option.

## 16. Union và polymorphic result

### 16.1. Union type

Union type cho phép kết quả thuộc một trong nhiều kiểu:

~~~text
PaymentResult =
    CardPayment
  | BankTransfer
  | CashPayment
~~~

Query có thể trả union khi nguồn chứa nhiều subtype hoặc khi projection tạo nhiều dạng kết quả.

### 16.2. Discriminated union

Một dạng an toàn là có discriminator:

~~~text
PaymentResult {
    kind: PaymentKind,
    value: CardPayment | BankTransfer | CashPayment
}
~~~

Serializer có thể dùng kind để xác định cách giải mã.

### 16.3. Polymorphic query

~~~text
from Payment
select Payment
~~~

Nếu Payment có nhiều subtype, kiểu kết quả có thể là List<Payment> với runtime type cụ thể hoặc List<PaymentVariant>.

### 16.4. Exhaustive handling

Consumer có thể cần xử lý mọi nhánh union. Khi thêm một subtype mới, compiler có thể cảnh báo những đoạn pattern matching chưa đầy đủ.

### 16.5. Union và schema evolution

Thêm một nhánh union có thể phá consumer cũ nếu họ giả định tập nhánh đóng. API cần quy định cách xử lý unknown discriminator.

## 17. Type inference cho kết quả truy vấn

### 17.1. Suy luận từ nguồn và projection

Compiler suy ra kiểu phần tử từ biểu thức select:

~~~text
from Customer
select name
~~~

Nếu name là String, element type là String.

### 17.2. Suy luận từ cardinality

Các toán tử như first, single, firstOrNone và collect thay đổi kiểu kết quả:

| Toán tử | Kiểu kết quả khái niệm |
|---|---|
| select | Query<T> hoặc Collection<T> |
| first | T hoặc lỗi nếu rỗng |
| firstOrNone | Optional<T> |
| single | T, lỗi nếu 0 hoặc nhiều hơn 1 |
| singleOrNone | Optional<T>, lỗi nếu nhiều hơn 1 |
| collect | List<T> |
| exists | Boolean |
| count | Long |

### 17.3. Suy luận qua biểu thức

Nếu projection chứa biểu thức:

~~~text
select {
    amount: total,
    tax: total * taxRate,
    taxable: total > threshold
}
~~~

Compiler suy ra từng field từ kiểu toán tử và operand.

### 17.4. Type widening

Khi kết hợp Integer và Decimal, compiler có thể nâng kiểu kết quả lên Decimal. Khi kết hợp nhiều nhánh có kiểu khác nhau, nó có thể tìm common supertype hoặc yêu cầu chuyển đổi tường minh.

### 17.5. Inference với null

Một biểu thức có nhánh trả String và nhánh trả null có thể được suy ra thành Nullable<String> hoặc Optional<String>. Quy tắc cần nhất quán giữa compiler và runtime.

### 17.6. Inference qua join

Join ảnh hưởng kiểu do outer join tạo nullable side, còn relationship metadata có thể giúp xác định cardinality. Compiler cần kết hợp thông tin schema và kiểu biểu thức.

### 17.7. Type annotation

Người dùng có thể khai báo kiểu mong đợi:

~~~text
query activeNames: List<String> =
    from Customer
    where active
    select name
~~~

Compiler so sánh kiểu suy ra với kiểu khai báo và báo lỗi nếu không tương thích.

### 17.8. Khi inference không đủ

Nếu nguồn dữ liệu động hoặc projection phụ thuộc runtime schema, DSL có thể yêu cầu annotation, schema declaration hoặc cast có kiểm tra.

## 18. Kiểu kết quả và schema stability

### 18.1. Schema của query

Schema kết quả mô tả tên trường, kiểu, nullability, cardinality và metadata. Nó có thể được xuất ra để consumer tạo client, validate payload hoặc sinh tài liệu API.

### 18.2. Thay đổi tương thích

Một số thay đổi thường ít phá vỡ hơn:

- Thêm trường optional nếu consumer bỏ qua trường chưa biết.
- Mở rộng kiểu số nếu serialization và consumer hỗ trợ.
- Thêm metadata không bắt buộc.

Tuy nhiên, tính tương thích phụ thuộc quy tắc consumer và định dạng trao đổi.

### 18.3. Thay đổi có thể phá vỡ

- Đổi scalar thành collection.
- Đổi record field name.
- Xóa trường đang được consumer sử dụng.
- Đổi nullable thành required.
- Đổi kiểu trả về.
- Thay thứ tự hoặc uniqueness semantics.
- Thay eager result bằng stream có vòng đời resource.

### 18.4. Version hóa result schema

Nếu query result được công bố qua API hoặc được nhiều module sử dụng, schema có thể cần version riêng. Consumer nên biết version và cách xử lý trường chưa biết.

### 18.5. Contract test

Contract test xác nhận query vẫn trả shape, kiểu, cardinality và semantics mong đợi. Nó giúp phát hiện thay đổi không tương thích khi schema nguồn hoặc query DSL được nâng cấp.

## 19. Kiểu kết quả trong API và serialization

### 19.1. Serialization

Kết quả nội bộ có thể được serialize thành JSON, XML, binary format hoặc row set. Kiểu kết quả cần ánh xạ rõ sang định dạng trao đổi.

Ví dụ record:

~~~json
{
  "id": "C-102",
  "name": "An",
  "email": null
}
~~~

### 19.2. Optional và null khi serialize

Một field optional có thể:

- Bị bỏ khỏi payload khi không có giá trị.
- Xuất hiện với giá trị null.
- Dùng wrapper hoặc discriminator.

Các cách này không tương đương. Consumer cần biết field vắng mặt khác field có giá trị null như thế nào.

### 19.3. Decimal và độ chính xác

Decimal có thể được serialize thành JSON number hoặc string tùy yêu cầu độ chính xác và consumer. Với tiền tệ, dùng số dấu phẩy động nhị phân có thể gây sai số; contract cần định nghĩa biểu diễn chính xác.

### 19.4. Date, time và timezone

Kiểu ngày giờ cần quy định timezone, offset và precision. Timestamp không có timezone có thể bị hiểu khác giữa hệ thống.

### 19.5. Binary và large object

Kết quả chứa binary hoặc large object có thể được trả qua reference, stream hoặc URL tạm thay vì nhúng toàn bộ payload. Quyền truy cập và thời hạn của reference cần được kiểm soát.

### 19.6. Schema metadata

API có thể cung cấp schema hoặc content type để consumer biết kiểu kết quả. Không nên chỉ dựa vào tên trường hoặc giá trị mẫu để đoán schema.

## 20. Kết quả và lỗi truy vấn

### 20.1. Lỗi không phải là kết quả rỗng

Một query trả zero rows có thể là thành công. Query thất bại do timeout hoặc permission là một trạng thái khác.

### 20.2. Result type

Một DSL có thể biểu diễn:

~~~text
Result<QueryData<T>, QueryError>
~~~

QueryData chứa dữ liệu; QueryError chứa loại lỗi và thông tin chẩn đoán.

### 20.3. Exception-based API

Một số runtime ném exception khi query thất bại. Khi đó, kiểu trả về mô tả dữ liệu thành công, còn lỗi đi qua exception channel. Hợp đồng cần tài liệu hóa loại lỗi có thể xảy ra.

### 20.4. Error categories

Các nhóm lỗi có thể gồm:

- Syntax hoặc validation error.
- Type mismatch.
- Unknown field hoặc source.
- Permission denied.
- Connection failure.
- Timeout.
- Cardinality violation.
- Serialization error.
- Cancellation.

### 20.5. Partial result

Với streaming query, lỗi có thể xảy ra sau khi một phần dữ liệu đã được tiêu thụ. Runtime cần quy định consumer có thể giữ phần đã nhận hay toàn bộ operation được xem là thất bại.

### 20.6. Warnings và metadata

Query có thể thành công nhưng kèm warning, ví dụ kết quả bị giới hạn hoặc một nguồn dữ liệu bị bỏ qua theo policy. Warning không nên bị nhập nhằng với error.

## 21. Kiểu kết quả và query execution plan

### 21.1. Logical result type

Kiểu kết quả logic mô tả điều mà query cam kết trả về, không phụ thuộc query chạy trên database, in-memory engine hay remote service.

### 21.2. Physical representation

Backend có thể biểu diễn kết quả bằng:

- Row cursor.
- JDBC ResultSet.
- In-memory record.
- Arrow-like columnar batch.
- Stream message.
- Remote page response.

Physical representation có thể khác nhau nhưng cần ánh xạ về cùng logical result contract.

### 21.3. Materialization

Materialization chuyển kết quả backend thành object hoặc collection trong runtime. Việc này có thể tốn CPU và bộ nhớ. Query planner có thể trì hoãn materialization hoặc chỉ đọc những trường cần thiết.

### 21.4. Projection pushdown

Nếu consumer chỉ cần một vài trường, planner có thể đẩy projection xuống database để giảm dữ liệu truyền về. Kiểu kết quả vẫn phải phản ánh chính xác những trường đã chọn.

### 21.5. Aggregate pushdown

Count hoặc sum có thể được tính tại nguồn. Backend phải giữ semantics về null, overflow và kiểu numeric như DSL quy định.

### 21.6. Columnar và row-oriented result

Row-oriented result lưu các trường theo từng hàng. Columnar result lưu các giá trị theo cột, có thể hiệu quả cho phân tích. Logical schema cần độc lập với physical layout.

### 21.7. Backend equivalence

Hai backend cần trả kết quả tương đương về kiểu, cardinality, ordering, null và error semantics. Khác biệt physical representation không được làm thay đổi hợp đồng logic.

## 22. Kết quả của query composition

### 22.1. Query object

Một DSL có thể phân biệt query expression với dữ liệu đã thực thi:

~~~text
Query<T>
~~~

Query<T> là mô tả có thể thực thi; List<T> là kết quả đã materialize. Phân biệt này giúp xây dựng pipeline và trì hoãn thực thi.

### 22.2. Filter

Filter thường giữ nguyên kiểu phần tử nhưng thay đổi cardinality:

~~~text
Query<Customer> -> Query<Customer>
~~~

Số phần tử có thể giảm về zero.

### 22.3. Map hoặc select

Projection thay đổi kiểu phần tử:

~~~text
Query<Customer> -> Query<String>
~~~

### 22.4. FlatMap

FlatMap biến mỗi phần tử thành một collection rồi làm phẳng:

~~~text
Query<Customer> -> Query<Order>
~~~

Cardinality có thể tăng, giảm hoặc bằng zero tùy từng phần tử.

### 22.5. Union

Union kết hợp hai query có kiểu tương thích:

~~~text
Query<OnlineOrder> union Query<StoreOrder>
~~~

Kiểu kết quả có thể là Query<Order> nếu cả hai nhánh có common supertype Order.

### 22.6. Distinct

Distinct thường giữ kiểu phần tử nhưng thay đổi cardinality và uniqueness semantics.

### 22.7. Sort

Sort giữ kiểu phần tử và cardinality nhưng thêm ordering semantics. Nếu sort key không tạo thứ tự toàn phần, thứ tự giữa các phần tử bằng nhau có thể không ổn định.

## 23. Ví dụ tổng hợp: query báo cáo khách hàng

Giả sử schema có:

~~~text
Customer {
    id: CustomerId,
    name: String,
    email: Optional<String>
}

Order {
    id: OrderId,
    customerId: CustomerId,
    total: Money,
    status: OrderStatus
}
~~~

### 23.1. Lấy một khách hàng

~~~text
query customerById(id: CustomerId):
    from Customer
    where id == input.id
    select Customer
    singleOrNone
~~~

Kiểu kết quả:

~~~text
Optional<Customer>
~~~

### 23.2. Lấy danh sách tên

~~~text
query customerNames:
    from Customer
    orderBy name ascending
    select name
~~~

Kiểu kết quả:

~~~text
List<String>
~~~

### 23.3. Lấy record tóm tắt

~~~text
query customerSummaries:
    from Customer
    select {
        id: id,
        name: name,
        email: email
    }
~~~

Kiểu kết quả:

~~~text
List<{
    id: CustomerId,
    name: String,
    email: Optional<String>
}>
~~~

### 23.4. Đếm đơn hàng đã thanh toán

~~~text
query paidOrderCount(customerId: CustomerId):
    from Order
    where customerId == input.customerId
      and status == PAID
    select count()
~~~

Kiểu kết quả là Long hoặc Integer theo quy ước của DSL. Query trả một scalar ngay cả khi nguồn có nhiều Order.

### 23.5. Tổng doanh thu

~~~text
query paidRevenue:
    from Order
    where status == PAID
    select sum(total)
~~~

Kiểu kết quả có thể là Money. Hành vi khi không có Order cần được định nghĩa, chẳng hạn Money.zero hoặc Optional<Money>.

### 23.6. Báo cáo nhóm theo khách hàng

~~~text
query revenueByCustomer:
    from Order
    where status == PAID
    groupBy customerId
    select {
        customerId: key,
        orderCount: count(),
        revenue: sum(total)
    }
~~~

Kiểu kết quả:

~~~text
List<{
    customerId: CustomerId,
    orderCount: Long,
    revenue: Money
}>
~~~

### 23.7. Phân trang báo cáo

Nếu query có limit và cursor, kết quả có thể là CursorPage<RevenueByCustomer>. Consumer nhận items và nextCursor để lấy trang tiếp theo.

Ví dụ này cho thấy kiểu kết quả được xác định bởi projection, aggregate, grouping và pagination, chứ không chỉ bởi kiểu của bảng nguồn.

## 24. Những sai lầm thường gặp

### 24.1. Nhầm kiểu phần tử với kiểu toàn kết quả

Query chọn Customer.name có phần tử là String nhưng toàn kết quả có thể là List<String>. Cần phân biệt hai lớp kiểu.

### 24.2. Nhầm không có dòng với trường null

Optional<Customer> và Customer có email nullable biểu diễn hai tình huống khác nhau. Gộp chúng có thể làm mất thông tin nghiệp vụ.

### 24.3. Giả định query luôn có thứ tự

Nếu không có order by, thứ tự kết quả không nên được xem là hợp đồng. Dùng List không tự tạo ra ordering ổn định từ database.

### 24.4. Coi partial record là entity đầy đủ

Projection chỉ lấy vài trường không thể tự động đáp ứng invariant của entity đầy đủ. Nên dùng kiểu projection riêng.

### 24.5. Không định nghĩa aggregate trên tập rỗng

Sum, average, min và max có thể có hành vi khác nhau với dữ liệu rỗng. Quy tắc phải thống nhất giữa backend.

### 24.6. Không phản ánh nullability của outer join

Left join có thể không tìm thấy phía phải. Nếu kiểu kết quả vẫn khai báo non-null, consumer có thể gặp lỗi runtime.

### 24.7. Nhầm Page rỗng với không có Page

Page có items rỗng vẫn là một kết quả hợp lệ. Optional<Page<T>> là một khái niệm khác.

### 24.8. Không quản lý vòng đời stream

Stream có thể giữ cursor hoặc connection. Không đóng stream có thể làm cạn connection pool.

### 24.9. Bỏ qua error channel

Empty result không có nghĩa query thất bại. Timeout, permission và cardinality violation cần được biểu diễn riêng.

### 24.10. Để backend quyết định semantics

Nếu một backend trả null cho sum rỗng còn backend khác trả zero, cùng một DSL query sẽ có hành vi khác. Semantics cần thuộc DSL contract và được kiểm thử trên các backend.

## 25. Quy trình xác định kiểu kết quả

Khi thiết kế một query hoặc một query DSL, có thể áp dụng các bước:

1. Xác định kiểu nguồn và schema.
2. Phân tích projection để tìm shape của phần tử.
3. Suy ra kiểu từng trường hoặc biểu thức.
4. Xác định cardinality từ operator và constraint.
5. Tính nullability từ schema, outer join và biểu thức.
6. Xác định collection semantics: list, set, bag, table hay stream.
7. Xác định ordering và pagination metadata.
8. Quy định aggregate và hành vi trên dữ liệu rỗng.
9. Xác định error channel và cancellation.
10. Ánh xạ logical type sang physical backend representation.
11. Xác định serialization contract và schema version.
12. Viết contract test cho shape, kiểu và semantics.

## 26. Câu hỏi tự đánh giá

1. Kiểu kết quả khác kiểu nguồn như thế nào?
2. Phân biệt scalar, record, tuple, row và table result.
3. Cardinality 1, 0..1 và 0..N có thể được biểu diễn ra sao?
4. Optional<T> khác Nullable<T> như thế nào?
5. Vì sao left join làm thay đổi nullability của kiểu kết quả?
6. List, Set, Bag và Sequence có semantics gì khác nhau?
7. Projection một phần có nên được xem là entity đầy đủ không?
8. Aggregate xử lý collection rỗng như thế nào?
9. Page result khác CursorPage result ra sao?
10. Eager result khác lazy stream như thế nào?
11. Query composition làm thay đổi kiểu kết quả ra sao?
12. Vì sao logical result type cần độc lập với physical backend representation?
13. Những thay đổi nào có thể phá vỡ result schema contract?
14. Làm thế nào để kiểm thử sự tương đương giữa nhiều backend?

## Kết luận

Kiểu kết quả xác định hình dạng, kiểu dữ liệu, cardinality, nullability, ordering, cách đánh giá và error semantics của một truy vấn. Trong DSL truy vấn, kiểu kết quả được hình thành từ nguồn dữ liệu, projection, join, aggregate, grouping, pagination và các phép biến đổi. Scalar, record, tuple, row, table, collection, stream, nested result và union type phục vụ những nhu cầu khác nhau.

Một DSL truy vấn đáng tin cậy cần phân biệt kiểu phần tử với kiểu toàn kết quả, không có dòng với trường null, page rỗng với kết quả vắng mặt, và dữ liệu rỗng với lỗi thực thi. Compiler nên suy luận kiểu từ schema và biểu thức, còn runtime cần bảo toàn cardinality, ordering, precision, resource lifetime và semantics giữa các backend. Khi result type được xem như hợp đồng rõ ràng, query dễ kết hợp, API dễ tích hợp và thay đổi schema có thể được quản lý an toàn hơn.

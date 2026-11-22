# Nhóm và tổng hợp

Trong ngôn ngữ truy vấn miền chuyên biệt (Domain-Specific Language for Queries), người dùng thường cần xem dữ liệu ở mức tổng quan thay vì đọc từng bản ghi riêng lẻ. Ví dụ, thay vì liệt kê mọi đơn hàng, họ muốn biết doanh thu theo tháng, số đơn theo trạng thái, số khách hàng theo khu vực hoặc giá trị trung bình theo loại sản phẩm. **Nhóm và tổng hợp (grouping and aggregation)** là hai thao tác cốt lõi để biến tập bản ghi chi tiết thành các nhóm có ý nghĩa và tính toán một kết quả đại diện cho mỗi nhóm.

Nhóm chia các bản ghi thành những tập con có cùng giá trị ở một hoặc nhiều khóa. Tổng hợp áp dụng một hàm lên các bản ghi hoặc giá trị trong từng nhóm, chẳng hạn đếm, tính tổng, trung bình, giá trị nhỏ nhất hoặc lớn nhất. Trong DSL truy vấn, hai thao tác này thường được biểu diễn bằng các mệnh đề tương tự GROUP BY và các hàm aggregate như COUNT, SUM, AVG, MIN và MAX.

Một DSL tốt cần định nghĩa chính xác khóa nhóm, kiểu kết quả, cách xử lý null, nhóm rỗng, thứ tự kết quả, điều kiện lọc trước và sau tổng hợp, cũng như giới hạn tài nguyên. Các quy tắc này phải nhất quán giữa parser, type checker, query planner và execution engine để cùng một truy vấn luôn có ý nghĩa rõ ràng.

## 1. Nhóm và tổng hợp là gì?

Giả sử có tập đơn hàng:

| order_id | region | status | amount |
|---|---|---|---:|
| O-101 | North | paid | 120 |
| O-102 | South | paid | 80 |
| O-103 | North | pending | 50 |
| O-104 | North | paid | 30 |
| O-105 | South | paid | 40 |

Nếu truy vấn chỉ chọn từng bản ghi, kết quả vẫn có năm dòng. Nếu nhóm theo region, ta có hai nhóm: North và South. Nếu tính tổng amount trong từng nhóm, kết quả là:

| region | total_amount |
|---|---:|
| North | 200 |
| South | 120 |

Nhóm quyết định bản ghi nào thuộc cùng một tập con. Tổng hợp quyết định phép tính được thực hiện trên từng tập con.

~~~mermaid
flowchart TD
    A[Input records] --> B[Choose grouping keys]
    B --> C[Partition records into groups]
    C --> D[Apply aggregate functions]
    D --> E[Project group keys and aggregate values]
    E --> F[Grouped result]
~~~

Trong ví dụ, khóa nhóm là region và hàm tổng hợp là SUM(amount). Một truy vấn DSL minh họa:

~~~text
from orders
group by region
select {
    region: key.region,
    total_amount: sum(amount)
}
~~~

Cú pháp cụ thể phụ thuộc DSL. Điều quan trọng là người đọc có thể nhận ra ranh giới giữa nguồn dữ liệu, khóa nhóm, phép tổng hợp và cấu trúc kết quả.

## 2. Phân biệt grouping với aggregation

Hai khái niệm thường đi cùng nhau nhưng không đồng nghĩa:

- **Grouping:** phân hoạch bản ghi thành các nhóm theo khóa.
- **Aggregation:** tính một giá trị từ một tập bản ghi hoặc tập giá trị.

Có thể nhóm mà không tính tổng, ví dụ trả về mỗi khóa cùng danh sách các bản ghi thuộc nhóm. Cũng có thể tổng hợp toàn bộ tập dữ liệu mà không chia nhóm; khi đó toàn bộ đầu vào được xem là một nhóm duy nhất.

Ví dụ tổng hợp toàn cục:

~~~text
from orders
select {
    order_count: count(),
    revenue: sum(amount),
    average_order: avg(amount)
}
~~~

Kết quả có một hàng:

| order_count | revenue | average_order |
|---:|---:|---:|
| 5 | 320 | 64 |

Ví dụ nhóm nhưng giữ các phần tử:

~~~text
from orders
group by region
select {
    region: key.region,
    orders: collect(current)
}
~~~

Kết quả có một nhóm cho mỗi region, trong đó orders chứa danh sách bản ghi. Việc giữ toàn bộ bản ghi có thể tốn bộ nhớ, nên query engine cần giới hạn hoặc hỗ trợ streaming khi tập dữ liệu lớn.

## 3. Khóa nhóm (grouping key)

Khóa nhóm xác định tiêu chí để các bản ghi được xếp vào cùng một nhóm. Khóa có thể là:

- Một thuộc tính, như region.
- Nhiều thuộc tính, như region và status.
- Một biểu thức, như year(orderDate).
- Một phép chuẩn hóa, như lower(category).
- Một bucket hoặc khoảng, như nhóm doanh thu theo dải giá trị.
- Một khóa miền được tính từ quan hệ hoặc phân loại.

Ví dụ nhóm theo hai thuộc tính:

~~~text
from orders
group by region, status
select {
    region: key.region,
    status: key.status,
    order_count: count(),
    revenue: sum(amount)
}
~~~

Mỗi cặp (region, status) tạo thành một nhóm riêng. North/paid và North/pending là hai nhóm khác nhau dù có cùng region.

### 3.1. Biểu thức khóa nhóm

Có thể nhóm theo biểu thức:

~~~text
from events
group by year(timestamp), month(timestamp)
select {
    year: key.year,
    month: key.month,
    event_count: count()
}
~~~

Trong DSL thực tế, cần xác định biểu thức được đánh giá một lần cho mỗi bản ghi hay nhiều lần khi các aggregate sử dụng lại nó. Query planner có thể tính key projection trước rồi tái sử dụng.

### 3.2. Tính ổn định của khóa

Khóa nhóm cần có equality và hash semantics rõ ràng nếu engine dùng hash aggregation. Với khóa số thực, cần quy định cách so sánh NaN, -0 và +0. Với chuỗi, cần xác định có phân biệt hoa thường, chuẩn hóa Unicode hoặc dùng collation theo locale hay không.

Nếu hai giá trị được xem là bằng nhau theo quy tắc của DSL, chúng phải thuộc cùng nhóm. Nếu quy tắc này không nhất quán giữa hash và equality, engine có thể tạo nhóm trùng hoặc thất lạc bản ghi.

### 3.3. Khóa null

Nếu một thuộc tính nhóm có giá trị null, DSL phải quy định hành vi. Một lựa chọn phổ biến là xem null như một giá trị nhóm riêng, để mọi bản ghi thiếu region được gom vào nhóm null. Một lựa chọn khác là loại bỏ bản ghi null hoặc yêu cầu người dùng xử lý trước bằng coalesce/filter.

Không nên để hành vi phụ thuộc ngẫu nhiên vào implementation của map hoặc database backend.

## 4. Các hàm tổng hợp cơ bản

Một DSL truy vấn thường cung cấp một tập aggregate function chuẩn.

| Hàm | Ý nghĩa | Kết quả thường gặp |
|---|---|---|
| COUNT | Đếm bản ghi hoặc giá trị | Số nguyên |
| SUM | Tính tổng giá trị số | Kiểu số phù hợp |
| AVG | Tính trung bình | Kiểu số hoặc decimal |
| MIN | Giá trị nhỏ nhất | Kiểu đầu vào |
| MAX | Giá trị lớn nhất | Kiểu đầu vào |
| COLLECT | Thu thập giá trị thành collection | List hoặc collection |
| COUNT_DISTINCT | Đếm số giá trị khác nhau | Số nguyên |
| BOOL_AND | Tất cả giá trị đều true | Boolean |
| BOOL_OR | Có ít nhất một giá trị true | Boolean |

Ví dụ:

~~~text
from order_items
group by product_id
select {
    product_id: key.product_id,
    units_sold: sum(quantity),
    average_price: avg(unit_price),
    lowest_price: min(unit_price),
    highest_price: max(unit_price),
    line_count: count()
}
~~~

Một aggregate có thể có nhiều dạng gọi. COUNT(*) thường đếm mọi bản ghi, trong khi COUNT(field) có thể chỉ đếm giá trị field không null. DSL cần mô tả rõ khác biệt này.

## 5. COUNT và cách đếm

COUNT có ít nhất hai ý nghĩa thường gặp:

- Đếm số bản ghi trong nhóm.
- Đếm số giá trị không null của một biểu thức.

Ví dụ:

~~~text
from customers
group by region
select {
    region: key.region,
    customer_rows: count(),
    customers_with_email: count(email)
}
~~~

Nếu một nhóm có 10 khách hàng nhưng 3 người không có email, count() trả 10 còn count(email) trả 7 theo semantics bỏ qua null.

COUNT_DISTINCT(email) có thể đếm số địa chỉ email khác nhau, nhưng cần quy định null có được tính là một giá trị riêng hay không. Nhiều hệ thống bỏ qua null trong distinct count; DSL nên nêu rõ.

Đếm chính xác có thể cần bộ nhớ tăng theo số giá trị duy nhất. Với dữ liệu rất lớn, engine có thể cung cấp approximate distinct count dựa trên cấu trúc xác suất. Tên hàm hoặc option phải làm rõ kết quả là ước lượng và có sai số dự kiến.

## 6. SUM và kiểu số

SUM cộng các giá trị số trong nhóm. Cần định nghĩa kiểu kết quả để tránh tràn hoặc mất chính xác.

Ví dụ:

~~~text
from invoice_lines
group by invoice_id
select {
    invoice_id: key.invoice_id,
    total: sum(line_total)
}
~~~

Các câu hỏi về kiểu:

- SUM(Integer) trả Integer, Long hay Decimal?
- SUM(Decimal) có giữ scale không?
- Giá trị null bị bỏ qua hay làm kết quả null?
- Nhóm không có giá trị số trả 0 hay null?
- Tràn số nguyên được báo lỗi, wrap hay nâng kiểu?
- Phép cộng tiền tệ có yêu cầu cùng currency không?

Với tiền tệ, không nên dùng floating-point nhị phân nếu nghiệp vụ yêu cầu chính xác. Có thể dùng BigDecimal hoặc decimal type của query engine. Nếu cộng các khoản tiền khác currency, phải chuyển đổi theo tỷ giá và thời điểm rõ ràng hoặc từ chối tổng hợp trực tiếp.

## 7. AVG, MIN và MAX

AVG tính trung bình cộng. Một cách định nghĩa phổ biến là SUM(values) / COUNT(non-null values). Vì vậy, cần hiểu cách SUM và COUNT xử lý null.

Ví dụ:

~~~text
from measurements
group by sensor_id
select {
    sensor: key.sensor_id,
    average: avg(reading),
    min_reading: min(reading),
    max_reading: max(reading)
}
~~~

Nếu không có giá trị hợp lệ, AVG có thể trả null. Không nên tự trả 0 nếu 0 là một giá trị đo hợp lệ và có ý nghĩa khác với không có dữ liệu.

MIN và MAX có thể áp dụng cho số, ngày giờ hoặc chuỗi nếu type system định nghĩa thứ tự. Với chuỗi, thứ tự có thể phụ thuộc collation. Với kiểu miền tùy chỉnh, cần comparator hoặc ordering contract.

## 8. Tổng hợp trên tập rỗng

Tập dữ liệu rỗng là trường hợp quan trọng:

~~~text
from orders
where status = "cancelled"
select {
    order_count: count(),
    total: sum(amount),
    average: avg(amount)
}
~~~

Nếu không có đơn hàng bị hủy, truy vấn aggregate toàn cục vẫn thường trả một hàng: count là 0, còn sum và average có thể là null tùy semantics được chọn. COUNT có identity là 0; SUM thường có thể được định nghĩa trả 0, nhưng nhiều hệ thống SQL trả null cho SUM trên tập rỗng. DSL phải chọn và tài liệu hóa hành vi.

Với GROUP BY, nếu không có bản ghi đầu vào thì thường không có nhóm nào, nên kết quả là collection rỗng. Điều này khác với aggregate toàn cục không có group key, vốn có thể tạo một kết quả tổng hợp cho toàn bộ tập rỗng.

Không nên nhầm một nhóm có các giá trị null với một nhóm không có bản ghi.

## 9. Null trong aggregate

Null có thể biểu thị thiếu dữ liệu, không áp dụng hoặc không biết. Các aggregate cần có quy tắc nhất quán.

Một semantics thường gặp:

- COUNT(*) đếm mọi bản ghi.
- COUNT(expression) bỏ qua giá trị null.
- SUM/AVG/MIN/MAX bỏ qua null.
- Nếu không còn giá trị hợp lệ, aggregate trả null, trừ khi DSL quy định khác.
- COUNT_DISTINCT thường bỏ qua null hoặc coi null là một bucket riêng theo lựa chọn công bố.

Ví dụ:

| amount |
|---:|
| 10 |
| null |
| 20 |

Kết quả theo semantics bỏ qua null:

- COUNT(*) = 3
- COUNT(amount) = 2
- SUM(amount) = 30
- AVG(amount) = 15

Nếu muốn xem số bản ghi thiếu amount, có thể dùng:

~~~text
from orders
select {
    missing_amount: count_if(amount is null)
}
~~~

Hoặc filter riêng. DSL nên có hàm conditional aggregation hoặc biểu thức điều kiện tương đương để tránh phải viết nhiều truy vấn.

## 10. WHERE và HAVING

WHERE và HAVING lọc ở hai giai đoạn khác nhau:

- **WHERE:** lọc bản ghi trước khi nhóm và tổng hợp.
- **HAVING:** lọc nhóm sau khi đã tính aggregate.

Ví dụ:

~~~text
from orders
where status = "paid"
group by region
having sum(amount) > 100
select {
    region: key.region,
    revenue: sum(amount)
}
~~~

Ở đây, chỉ các đơn đã thanh toán tham gia vào nhóm. Sau đó, chỉ những vùng có tổng doanh thu lớn hơn 100 được trả về.

Bảng so sánh:

| Mệnh đề | Đầu vào | Có thể tham chiếu |
|---|---|---|
| WHERE | Từng bản ghi | Thuộc tính bản ghi và biểu thức row-level |
| GROUP BY | Tập bản ghi đã lọc | Khóa nhóm |
| HAVING | Từng nhóm | Khóa nhóm và aggregate |
| SELECT | Nhóm đã lọc | Khóa nhóm, aggregate và biểu thức được phép |

Không nên dùng aggregate trong WHERE nếu semantics của DSL quy định WHERE chạy trước grouping. Query planner có thể tối ưu một số điều kiện HAVING thành WHERE nếu chứng minh được tương đương, nhưng điều đó không thay đổi ngữ nghĩa quan sát được.

## 11. Thứ tự xử lý truy vấn

Một pipeline logic phổ biến:

~~~mermaid
flowchart TD
    A[FROM source] --> B[WHERE row filter]
    B --> C[GROUP BY keys]
    C --> D[Compute aggregates]
    D --> E[HAVING group filter]
    E --> F[SELECT projection]
    F --> G[ORDER BY]
    G --> H[LIMIT]
~~~

Đây là thứ tự ngữ nghĩa để hiểu truy vấn, không nhất thiết là thứ tự vật lý engine phải thực hiện. Query optimizer có thể đổi thứ tự các bước khi phép biến đổi bảo toàn kết quả.

Ví dụ, một filter chỉ phụ thuộc vào khóa nhóm có thể được áp dụng sớm hơn nếu planner xác định an toàn. Nhưng điều kiện phụ thuộc vào SUM(amount) chỉ có thể được đánh giá sau khi aggregate đã có.

## 12. SELECT trong truy vấn có nhóm

Sau khi grouping, mỗi hàng kết quả đại diện cho một nhóm. Vì vậy, SELECT không thể tùy ý đọc một thuộc tính của bản ghi gốc nếu thuộc tính đó không nằm trong grouping key hoặc không được tổng hợp.

Truy vấn sau thường không xác định:

~~~text
from orders
group by region
select {
    region: key.region,
    customer_name: customer_name,
    total: sum(amount)
}
~~~

Một nhóm North có thể chứa nhiều customer_name. Engine không biết nên chọn tên nào.

Có thể sửa bằng cách:

- Thêm customer_name vào khóa nhóm nếu muốn một nhóm theo từng khách hàng.
- Dùng aggregate như collect(customer_name).
- Chọn một aggregate xác định như min(customer_name), nếu đó là ý nghĩa mong muốn.
- Tách truy vấn thành hai giai đoạn.

Type checker hoặc semantic validator nên phát hiện field không được nhóm hoặc tổng hợp trước khi chạy.

## 13. Nhóm nhiều cấp và nhóm lồng nhau

Có thể cần nhóm theo nhiều cấp, ví dụ region rồi đến status, hoặc region rồi đến tháng.

Một dạng kết quả lồng:

~~~text
from orders
group by region
select {
    region: key.region,
    by_status: group current by status {
        status: key.status,
        count: count(),
        revenue: sum(amount)
    }
}
~~~

Cú pháp minh họa này thể hiện grouping lồng nhau. DSL có thể thay bằng nested query hoặc subquery.

Nhóm nhiều cấp hữu ích cho báo cáo phân cấp, nhưng cần xác định collection của nhóm con có thứ tự hay không, có thể rỗng hay không và aggregate ở cấp cha được tính trên tất cả bản ghi hay trên kết quả nhóm con.

Một lựa chọn khác là grouping theo cặp key (region, status), sau đó hiển thị kết quả dạng bảng phẳng. Dạng phẳng dễ join, sort và export; dạng lồng có thể phù hợp với API hoặc UI dạng cây.

## 14. Conditional aggregation

Conditional aggregation tính nhiều thống kê trên các tập con khác nhau của cùng một nhóm. Ví dụ đếm đơn paid và pending theo region:

~~~text
from orders
group by region
select {
    region: key.region,
    paid_count: count_if(status = "paid"),
    pending_count: count_if(status = "pending"),
    paid_revenue: sum_if(amount, status = "paid")
}
~~~

Nếu DSL không có count_if hoặc sum_if, có thể dùng biểu thức điều kiện:

~~~text
sum(case when status = "paid" then amount else 0 end)
~~~

Cần xác định null trong điều kiện được xử lý thế nào. Trong logic ba giá trị, điều kiện null không phải true; hàm conditional aggregate cần công bố cách xử lý.

Conditional aggregation giúp giảm số lần quét nguồn dữ liệu. Thay vì chạy nhiều truy vấn riêng, engine có thể tính nhiều accumulator trong cùng một lượt.

## 15. DISTINCT và loại bỏ trùng lặp

DISTINCT có thể áp dụng cho đầu vào trước khi tổng hợp hoặc cho giá trị bên trong aggregate. Hai cách này không tương đương trong mọi trường hợp.

Ví dụ:

~~~text
from orders
group by region
select {
    region: key.region,
    unique_customers: count_distinct(customer_id),
    all_orders: count()
}
~~~

COUNT_DISTINCT(customer_id) đếm khách hàng khác nhau trong nhóm. Nếu loại bỏ duplicate toàn bộ bản ghi trước khi tính count, kết quả có thể thay đổi vì hai đơn khác nhau của cùng khách hàng vẫn là hai đơn.

Cần xác định equality semantics của distinct, cách xử lý null và collation. Với object hoặc kiểu miền phức tạp, có thể chỉ cho phép distinct trên các kiểu có equality/hash semantics được định nghĩa.

## 16. ORDER BY sau grouping

Thứ tự nhóm không nên được xem là ổn định nếu truy vấn không chỉ định ORDER BY. Hash aggregation có thể tạo kết quả theo thứ tự khác nhau giữa lần chạy hoặc implementation.

Ví dụ:

~~~text
from orders
group by region
select {
    region: key.region,
    revenue: sum(amount)
}
order by revenue desc, region asc
~~~

Có thể sắp xếp theo khóa nhóm hoặc giá trị aggregate. Khi nhiều nhóm có cùng revenue, thêm khóa phụ giúp thứ tự xác định.

Nếu DSL dùng collection có thứ tự, cần phân biệt thứ tự đầu vào với thứ tự kết quả nhóm. Không nên mặc định nhóm xuất hiện theo bản ghi đầu tiên nếu engine chạy song song hoặc phân tán.

## 17. LIMIT và phân trang kết quả nhóm

LIMIT thường được áp dụng sau ORDER BY và projection theo semantics của truy vấn. Ví dụ, lấy 10 region có doanh thu cao nhất:

~~~text
from orders
group by region
select {
    region: key.region,
    revenue: sum(amount)
}
order by revenue desc
limit 10
~~~

Nếu áp dụng LIMIT trước grouping, kết quả sẽ khác. Query planner chỉ được đẩy LIMIT xuống nguồn khi có thể chứng minh phép biến đổi bảo toàn kết quả.

Phân trang nhóm cần thứ tự ổn định. Nếu chỉ sort theo revenue mà nhiều nhóm bằng nhau, trang tiếp theo có thể trùng hoặc thiếu kết quả khi dữ liệu thay đổi. Có thể dùng key nhóm làm tie-breaker hoặc snapshot consistency.

## 18. GROUPING SETS, ROLLUP và CUBE

Một số DSL truy vấn cần báo cáo ở nhiều cấp tổng hợp trong cùng một lượt.

- **ROLLUP:** tạo các cấp tổng phụ từ danh sách khóa theo thứ tự.
- **CUBE:** tạo các tổ hợp nhóm cho mọi tập con của các khóa.
- **GROUPING SETS:** chỉ định tường minh các tổ hợp khóa cần tổng hợp.

Ví dụ khái niệm:

~~~text
from sales
group by rollup(region, product)
select {
    region: key.region,
    product: key.product,
    revenue: sum(amount)
}
~~~

Kết quả có thể chứa:
- Doanh thu theo từng cặp region/product.
- Tổng doanh thu theo region.
- Tổng doanh thu toàn cục.

Khi kết quả chứa null ở khóa, cần phân biệt null vốn có trong dữ liệu với null được sinh ra để biểu thị cấp tổng hợp. Một grouping indicator có thể cho biết khóa nào bị lược khỏi grouping set.

CUBE có thể tạo số nhóm tăng theo hàm mũ theo số khóa; nếu có n khóa, số grouping set có thể lên tới 2^n. DSL nên giới hạn số khóa hoặc cảnh báo chi phí để tránh truy vấn quá lớn.

## 19. Tổng hợp theo thời gian

Dữ liệu sự kiện thường cần tổng hợp theo phút, giờ, ngày, tuần hoặc tháng. Có thể nhóm theo hàm trích xuất thời gian:

~~~text
from events
group by date_trunc("day", timestamp)
select {
    day: key.day,
    event_count: count(),
    unique_users: count_distinct(user_id)
}
order by day
~~~

Cần quy định timezone. Một ngày theo UTC có thể khác ngày theo múi giờ nghiệp vụ. Daylight saving time có thể làm một ngày có 23 hoặc 25 giờ ở một số vùng.

Với dữ liệu streaming, cửa sổ thời gian cần xác định:

- **Tumbling window:** các cửa sổ cố định, không chồng lấn.
- **Sliding window:** cửa sổ trượt, có thể chồng lấn.
- **Session window:** gom sự kiện theo khoảng không hoạt động giữa các sự kiện.

Ví dụ cửa sổ tumbling 5 phút:

~~~text
from stream events
window tumbling 5m on timestamp
group by window.start, event_type
select {
    window_start: key.window_start,
    event_type: key.event_type,
    count: count()
}
~~~

DSL cần định nghĩa event time hay processing time, watermark, late event và chính sách cập nhật kết quả khi sự kiện đến muộn.

## 20. Window aggregation khác GROUP BY

Window function tính giá trị trên một cửa sổ các hàng nhưng thường giữ lại từng hàng trong kết quả. GROUP BY gom nhiều hàng thành ít hàng hơn.

Ví dụ window:

~~~text
from orders
select {
    order_id: id,
    region: region,
    amount: amount,
    region_total: sum(amount) over partition by region
}
~~~

Mỗi order vẫn là một hàng, nhưng có thêm tổng doanh thu của region. Ngược lại, GROUP BY region chỉ trả một hàng cho mỗi region nếu projection không giữ danh sách chi tiết.

Phân biệt này quan trọng trong DSL vì người dùng thường nhầm aggregate theo nhóm với aggregate window. Type system và query planner cần mô hình hóa chúng thành hai operator khác nhau.

## 21. Kiểu dữ liệu của kết quả tổng hợp

Aggregate có kiểu đầu ra được xác định từ kiểu đầu vào và semantics của hàm.

Ví dụ quy ước:

| Biểu thức | Kiểu kết quả có thể chọn |
|---|---|
| count() | Long hoặc Integer |
| sum(Integer) | Long hoặc BigInteger |
| sum(Decimal) | Decimal |
| avg(Integer) | Decimal |
| min(Date) | Date hoặc nullable Date |
| max(String) | String theo collation |
| collect(T) | List<T> |

Các kiểu nullable cần được thể hiện rõ. AVG trên nhóm không có giá trị hợp lệ có thể trả null, vì vậy kiểu kết quả có thể là Decimal?. COUNT thường không nullable vì luôn trả số đếm.

Type checker nên kiểm tra:
- Hàm aggregate có hỗ trợ kiểu đầu vào không.
- Đơn vị và currency có tương thích không.
- Kiểu kết quả có thể gán cho trường projection không.
- Biểu thức aggregate có lồng nhau hợp lệ không.
- Trường không aggregate có thuộc grouping key không.

Không nên để lỗi kiểu chỉ xuất hiện ở runtime nếu có thể phát hiện trong semantic analysis.

## 22. Aggregate lồng nhau và nhiều giai đoạn

Một truy vấn có thể cần aggregate trên kết quả aggregate. Ví dụ tính trung bình doanh thu theo vùng rồi tính trung bình các vùng:

~~~text
from (
    from orders
    group by region
    select {
        region: key.region,
        revenue: sum(amount)
    }
) as regional
select avg(revenue)
~~~

Đây không giống AVG(amount) toàn cục nếu các vùng có số đơn khác nhau. Một vùng có một đơn và một vùng có một nghìn đơn sẽ được cân trọng số ngang nhau khi lấy trung bình của regional revenue. Nếu muốn average order amount, cần tổng amount chia cho count toàn cục.

DSL cần buộc người viết thể hiện đúng cấp aggregate. Một aggregate không nên được lồng trực tiếp trong aggregate cùng cấp nếu không có semantics rõ ràng. Thường cần subquery hoặc aggregation stage riêng.

## 23. Cách thực thi: hash aggregation và sort aggregation

Query engine có thể thực hiện grouping bằng nhiều chiến lược.

### 23.1. Hash aggregation

Engine tính key cho từng bản ghi, tìm accumulator tương ứng trong hash map rồi cập nhật các aggregate.

~~~mermaid
flowchart TD
    A[Record] --> B[Compute group key]
    B --> C[Lookup hash bucket]
    C --> D{Group exists?}
    D -->|No| E[Create accumulators]
    D -->|Yes| F[Reuse accumulators]
    E --> G[Update aggregates]
    F --> G
    G --> H[Next record]
~~~

Ưu điểm là thường không cần sắp xếp đầu vào. Hạn chế là bộ nhớ tăng theo số nhóm và kích thước trạng thái aggregate. Nếu cardinality rất cao, hash table có thể vượt memory budget.

### 23.2. Sort aggregation

Engine sắp xếp bản ghi theo grouping key, sau đó xử lý các bản ghi cùng key liên tiếp. Khi key thay đổi, nó hoàn tất nhóm trước và xuất kết quả.

Ưu điểm là có thể giữ trạng thái cho một nhóm hoặc một đoạn dữ liệu tại một thời điểm sau khi sort. Hạn chế là chi phí sort và yêu cầu thứ tự đầu vào.

### 23.3. Streaming aggregation

Nếu nguồn đã được sắp xếp theo key, engine có thể aggregate khi đọc tuần tự mà không cần giữ toàn bộ nhóm. Đây là chiến lược hiệu quả cho dữ liệu lớn, nhưng chỉ đúng khi ordering contract được bảo đảm.

## 24. Accumulator và trạng thái tổng hợp

Một aggregate thường được cài đặt bằng accumulator có ba thao tác:

- **Initialize:** tạo trạng thái ban đầu.
- **Add:** cập nhật trạng thái từ một giá trị hoặc bản ghi.
- **Finish:** chuyển trạng thái thành kết quả cuối.

Ví dụ SUM:

~~~java
final class SumLong {
    private long total;

    void add(long value) {
        total = Math.addExact(total, value);
    }

    long finish() {
        return total;
    }
}
~~~

COUNT chỉ cần một bộ đếm. AVG thường cần tổng và số lượng hợp lệ. MIN/MAX giữ giá trị tốt nhất đến thời điểm hiện tại.

Một interface khái niệm:

~~~java
interface Accumulator<Input, State, Output> {
    State create();
    State add(State state, Input value);
    State merge(State left, State right);
    Output finish(State state);
}
~~~

Phương thức merge hữu ích cho parallel/distributed aggregation: mỗi partition tính trạng thái riêng rồi engine hợp nhất chúng. Aggregate chỉ có thể được phân tán dễ dàng nếu state có phép merge đúng và kết quả tương đương với xử lý tuần tự theo semantics đã định.

## 25. Tổng hợp song song và phân tán

Với dữ liệu lớn, engine có thể chia đầu vào thành partitions. Mỗi worker tính partial aggregate, sau đó coordinator merge kết quả theo grouping key.

~~~mermaid
flowchart TD
    A[Input dataset] --> B[Partition]
    B --> C[Worker 1]
    B --> D[Worker 2]
    B --> E[Worker 3]
    C --> F[Partial groups]
    D --> F
    E --> F
    F --> G[Merge accumulators by key]
    G --> H[Final aggregate rows]
~~~

SUM và COUNT có phép merge đơn giản. AVG cần giữ cả sum và count; không thể lấy trung bình cộng đơn giản của các average partition nếu số lượng phần tử khác nhau.

COUNT_DISTINCT chính xác có thể cần hợp nhất tập giá trị duy nhất, tốn bộ nhớ. Approximate distinct có thể dùng sketch có phép merge. Một custom aggregate muốn chạy phân tán cần định nghĩa state serialization và merge semantics.

Thứ tự merge có thể khác nhau giữa các lần chạy. Với floating-point sum, phép cộng không có tính kết hợp chính xác do sai số làm tròn, nên kết quả có thể khác chút ít khi chạy song song. Nếu cần kết quả reproducible, có thể dùng decimal chính xác hoặc thuật toán summation ổn định hơn.

## 26. Bộ nhớ, cardinality và giới hạn tài nguyên

Số nhóm (group cardinality) quyết định đáng kể chi phí bộ nhớ. Nhóm theo region có thể chỉ tạo vài nhóm; nhóm theo transaction ID có thể tạo hàng triệu nhóm.

Engine cần có chính sách:

- Memory budget cho hash table và accumulator.
- Spill ra đĩa khi vượt ngưỡng nếu hỗ trợ.
- Giới hạn số nhóm hoặc từ chối truy vấn.
- Giới hạn kích thước COLLECT/LISTAGG.
- Timeout và cancellation.
- Giới hạn số grouping sets.
- Ước lượng cardinality trong query planner.

Không nên tự động collect toàn bộ bản ghi của mỗi nhóm nếu người dùng chỉ cần SUM hoặc COUNT. Giữ dữ liệu chi tiết làm tăng memory cost và có thể tạo output quá lớn.

## 27. Custom aggregate

Một DSL mở rộng có thể cho phép người dùng định nghĩa hàm tổng hợp riêng, ví dụ percentile, median hoặc thống kê miền.

Một custom aggregate cần xác định:

- Kiểu đầu vào.
- Kiểu state.
- Hàm initialize.
- Hàm add/update.
- Hàm merge nếu chạy song song.
- Hàm finish.
- Cách xử lý null.
- Tính xác định và tính kết hợp.
- Chi phí và giới hạn tài nguyên.

Median chính xác có thể cần giữ hoặc sắp xếp nhiều giá trị. Approximate percentile có thể dùng sketch để giảm bộ nhớ. Tên và semantics cần chỉ rõ kết quả chính xác hay ước lượng.

Không nên cho custom aggregate thực thi code tùy ý với quyền không giới hạn. Nó chạy trên nhiều bản ghi và có thể được gọi song song; cần kiểm soát side effect, thread safety và tài nguyên.

## 28. Tổng hợp collection và chuỗi

Ngoài số, aggregate có thể tạo collection hoặc chuỗi:

- COLLECT(value): thu thập giá trị thành list.
- ARRAY_AGG(value): tạo mảng.
- STRING_AGG(value, separator): nối chuỗi.
- FIRST(value) hoặc LAST(value): lấy phần tử đầu/cuối theo ordering xác định.
- ANY_VALUE(value): lấy một giá trị đại diện nếu semantics cho phép.

FIRST và LAST cần ORDER BY rõ ràng nếu thứ tự đầu vào không được bảo đảm. ANY_VALUE không nên được dùng khi người dùng cần một giá trị xác định; engine có thể chọn bất kỳ giá trị nào trong nhóm.

STRING_AGG cần quy định null, separator, thứ tự và giới hạn độ dài. COLLECT cần quy định có giữ duplicate hay không và collection có giữ thứ tự hay không.

## 29. GROUP BY và quan hệ dữ liệu

DSL truy vấn thường hỗ trợ join hoặc navigation qua quan hệ trước khi nhóm. Ví dụ, tính doanh thu theo tên khách hàng:

~~~text
from orders
join customers on orders.customer_id = customers.id
group by customers.region
select {
    region: key.region,
    revenue: sum(orders.amount)
}
~~~

Join có thể nhân bản bản ghi nếu quan hệ là one-to-many. Nếu query join order với order_items, COUNT(order) sau join có thể đếm số dòng item thay vì số order duy nhất. Cần hiểu cardinality và chọn COUNT_DISTINCT(order.id) hoặc aggregate ở đúng cấp trước khi join.

Query planner có thể đẩy aggregate xuống trước join trong một số trường hợp để giảm dữ liệu, nhưng phải bảo toàn semantics. Với outer join, null-extended row có thể ảnh hưởng count và sum, nên các phép biến đổi cần được chứng minh đúng.

## 30. Tổng hợp và filter theo quyền truy cập

Nếu người dùng chỉ được xem một phần dữ liệu, authorization filter phải được áp dụng trước khi aggregate để kết quả không tiết lộ thông tin từ bản ghi bị cấm.

Ví dụ, nếu người dùng chỉ được xem đơn của tenant A, tổng doanh thu không được bao gồm tenant B. Nếu filter quyền được áp dụng sau aggregation, tổng có thể tiết lộ dữ liệu của tenant khác.

Các nguyên tắc:

- Áp dụng tenant/row-level security trước GROUP BY.
- Không để aggregate function bỏ qua authorization predicate.
- Kiểm soát grouping trên trường nhạy cảm.
- Giới hạn các aggregate có thể suy ra dữ liệu cá nhân.
- Với dữ liệu thống kê nhạy cảm, có thể cần ngưỡng nhóm tối thiểu hoặc privacy mechanism.

Query DSL nên tích hợp policy vào logical plan hoặc data access layer để mọi dạng truy vấn đều tuân theo cùng quy tắc.

## 31. AST và query plan cho grouping

Parser có thể biểu diễn grouping bằng node riêng trong AST:

~~~text
Query
  Source(orders)
  Filter(status = "paid")
  GroupBy(region)
  Having(sum(amount) > 100)
  Project(
    region = GroupKey(region),
    revenue = Aggregate(SUM, amount)
  )
  OrderBy(revenue DESC)
~~~

Sau semantic analysis, compiler có thể chuyển AST thành logical plan:

~~~text
Project
  Sort
    FilterGroups(HAVING)
      Aggregate(groupKeys=[region], sums=[amount], counts=[*])
        FilterRows(status = "paid")
          Scan(orders)
~~~

Query planner sau đó chọn physical operator như HashAggregate, SortAggregate hoặc StreamingAggregate.

Type checker cần phân biệt biểu thức row-level, group-key expression và aggregate expression. Nó phải từ chối các tham chiếu mơ hồ đến field không nằm trong group key và không được tổng hợp.

## 32. Tối ưu hóa truy vấn nhóm và tổng hợp

Một số tối ưu thường gặp:

- **Predicate pushdown:** đẩy WHERE xuống gần nguồn dữ liệu.
- **Projection pruning:** chỉ đọc field cần cho key, filter và aggregate.
- **Partial aggregation:** tính aggregate cục bộ trước khi shuffle hoặc join.
- **Aggregate pushdown:** để database/backend thực hiện aggregate nếu semantics tương thích.
- **Combine aggregates:** tính nhiều hàm trên cùng một lượt quét.
- **Reuse expression:** tính group key hoặc expression dùng nhiều lần một lần.
- **Limit/order optimization:** chọn top-k thay vì sort toàn bộ khi phù hợp.
- **Cardinality estimation:** ước lượng số nhóm để chọn strategy.

Tối ưu hóa cần giữ semantics của null, overflow, collation, timezone và approximate functions. Không nên đẩy aggregate sang database nếu kiểu hoặc cách xử lý null giữa DSL và database khác nhau mà chưa có adapter điều chỉnh.

## 33. Tổng hợp gia tăng và dữ liệu thay đổi

Trong dashboard hoặc hệ thống streaming, dữ liệu có thể thay đổi liên tục. Recompute toàn bộ aggregate sau mỗi thay đổi có thể tốn kém.

Incremental aggregation cập nhật state khi có bản ghi mới, bị xóa hoặc thay đổi. Ví dụ, khi thêm order amount 20 vào nhóm North, SUM tăng 20 và COUNT tăng 1.

Đối với update hoặc delete, accumulator cần biết cách trừ hoặc loại bỏ contribution. SUM và COUNT hỗ trợ cập nhật ngược tương đối dễ. MIN/MAX khó hơn: nếu xóa giá trị đang là minimum, engine cần tìm minimum mới, có thể cần multiset hoặc cấu trúc phụ.

Cần định nghĩa:
- Event có thể đến trễ hay không.
- Có thể sửa hoặc xóa bản ghi đã aggregate không.
- State được checkpoint như thế nào.
- Làm sao khôi phục sau crash.
- Kết quả có được phát lại (replay) không.
- Watermark và retention của window.

## 34. Materialized aggregate và cache

Một kết quả nhóm/tổng hợp có thể được lưu sẵn để phục vụ truy vấn nhanh, gọi là materialized view hoặc aggregate cache.

Ví dụ lưu doanh thu theo ngày và vùng. Truy vấn dashboard có thể đọc bảng tổng hợp thay vì quét toàn bộ orders.

Cần quản lý:
- Định nghĩa truy vấn gốc.
- Source revision hoặc watermark đã xử lý.
- Refresh schedule hoặc incremental update.
- Invalidation khi schema hoặc query definition thay đổi.
- Consistency giữa dữ liệu gốc và aggregate.
- Khả năng rebuild khi cache hỏng.

Không nên coi materialized aggregate là dữ liệu gốc. Nó có thể bị stale hoặc phải tính lại. Metadata nên cho biết aggregate phản ánh dữ liệu đến thời điểm nào.

## 35. Ví dụ tổng hợp hoàn chỉnh

Giả sử có các đơn hàng gồm order ID, ngày, vùng, trạng thái và amount. Yêu cầu là tính doanh thu đã thanh toán theo vùng và tháng, chỉ hiển thị nhóm có ít nhất 100 doanh thu, sắp xếp từ cao xuống thấp.

Một truy vấn DSL:

~~~text
from orders
where status = "paid"
group by region, month(order_date)
having sum(amount) >= 100
select {
    region: key.region,
    month: key.month,
    order_count: count(),
    revenue: sum(amount),
    average_order: avg(amount)
}
order by revenue desc, region asc
~~~

Các bước ngữ nghĩa:

1. Đọc orders.
2. Lọc các bản ghi có status là paid.
3. Tính key gồm region và tháng của order_date.
4. Gom các bản ghi có cùng key.
5. Tính count, sum và average trong từng nhóm.
6. Loại nhóm có revenue dưới 100.
7. Tạo projection theo cấu trúc yêu cầu.
8. Sắp xếp theo revenue giảm dần, rồi region tăng dần.

Kết quả có một hàng cho mỗi cặp region/month thỏa điều kiện. Nếu cần tháng theo timezone nghiệp vụ, phải quy định timezone trong biểu thức month.

## 36. Kiểm thử grouping và aggregation

Kiểm thử cần bao phủ semantics, kiểu dữ liệu và chiến lược thực thi.

### 36.1. Kiểm thử grouping cơ bản

- Một khóa nhóm.
- Nhiều khóa nhóm.
- Khóa là biểu thức.
- Khóa có null.
- Khóa chuỗi phân biệt hoa thường hoặc theo collation.
- Không có bản ghi đầu vào.

### 36.2. Kiểm thử aggregate

- COUNT(*) và COUNT(field).
- SUM, AVG, MIN, MAX.
- DISTINCT.
- Conditional aggregation.
- Collection/string aggregate.
- Giá trị null và nhóm rỗng.
- Overflow và decimal precision.

### 36.3. Kiểm thử WHERE/HAVING

- WHERE chạy trước grouping.
- HAVING chạy sau aggregate.
- Aggregate không được dùng sai trong WHERE.
- Field không grouped không được chiếu tùy tiện.
- Tối ưu predicate pushdown giữ nguyên kết quả.

### 36.4. Kiểm thử ordering và pagination

- Thứ tự nhóm không xác định nếu thiếu ORDER BY.
- Tie-breaker tạo thứ tự ổn định.
- LIMIT áp dụng sau grouping.
- Phân trang không trùng/thiếu trong snapshot nhất quán.

### 36.5. Kiểm thử parallel/distributed

- Merge partial SUM/COUNT/AVG.
- COUNT_DISTINCT exact/approximate.
- Kết quả floating-point trong sai số được công bố.
- Partition rỗng.
- Worker thất bại và retry không nhân đôi aggregate.

### 36.6. Kiểm thử hiệu năng và bảo mật

- Cardinality thấp và cao.
- Spill khi vượt memory budget.
- Cancellation/timeout.
- Tenant filter được áp dụng trước aggregation.
- COLLECT hoặc STRING_AGG không vượt giới hạn.
- Query có CUBE nhiều khóa được giới hạn chi phí.

## 37. Quy trình triển khai nhóm và tổng hợp trong DSL

Có thể triển khai theo các bước:

1. **Định nghĩa semantics:** equality của key, null, empty input, ordering và kiểu aggregate.
2. **Thiết kế grammar:** biểu diễn GROUP BY, HAVING, aggregate và window nếu cần.
3. **Tạo AST node:** phân biệt row expression, group key và aggregate expression.
4. **Type checking:** kiểm tra kiểu đầu vào/đầu ra và field được phép tham chiếu.
5. **Logical plan:** biểu diễn Filter, Aggregate, Having và Project.
6. **Chọn physical strategy:** hash, sort, streaming hoặc distributed aggregation.
7. **Cài accumulator:** initialize, add, merge và finish.
8. **Quản lý tài nguyên:** cardinality, memory budget, spill, timeout và output limit.
9. **Tối ưu hóa:** predicate pushdown, projection pruning, partial aggregation và reuse.
10. **Tích hợp authorization:** áp dụng row-level policy trước grouping.
11. **Hỗ trợ incremental nếu cần:** update/delete, checkpoint, watermark và materialized view.
12. **Kiểm thử semantics và hiệu năng:** dùng fixture, property tests và dữ liệu có cardinality khác nhau.

## 38. Nguyên tắc thiết kế

- **Phân biệt nhóm và tổng hợp:** grouping tạo partition; aggregate tính kết quả từ mỗi partition.
- **Định nghĩa equality của key:** null, Unicode, collation và kiểu số phải có semantics ổn định.
- **Quy định kiểu kết quả:** đặc biệt với SUM, AVG, decimal và nullable result.
- **Phân biệt COUNT(*) với COUNT(expression):** số bản ghi và số giá trị hợp lệ không giống nhau.
- **Tách WHERE khỏi HAVING:** lọc bản ghi trước nhóm, lọc nhóm sau aggregate.
- **Kiểm tra projection:** chỉ cho phép key hoặc aggregate trong grouped query theo quy tắc rõ.
- **Không giả định thứ tự nhóm:** yêu cầu ORDER BY khi cần kết quả ổn định.
- **Xử lý tập rỗng và null tường minh:** tránh nhầm không có dữ liệu với giá trị bằng 0.
- **Kiểm soát cardinality và bộ nhớ:** không collect dữ liệu lớn ngoài giới hạn.
- **Thiết kế accumulator có merge:** hỗ trợ parallel/distributed aggregation khi cần.
- **Phân biệt GROUP BY và window aggregation:** một thao tác gom hàng, thao tác kia giữ từng hàng.
- **Bảo toàn semantics khi tối ưu:** chú ý null, precision, timezone và authorization.
- **Gắn aggregate cache với revision:** materialized result phải thể hiện mức độ mới của dữ liệu.
- **Kiểm thử cả logic lẫn chi phí:** truy vấn đúng nhưng vượt bộ nhớ vẫn không hữu ích.

Nhóm và tổng hợp biến dữ liệu chi tiết thành thông tin có thể so sánh, báo cáo và ra quyết định. Khi DSL định nghĩa rõ khóa nhóm, aggregate semantics, null, kiểu kết quả, WHERE/HAVING và thứ tự xử lý; đồng thời query engine có accumulator, chiến lược hash/sort/streaming phù hợp, giới hạn tài nguyên và tối ưu bảo toàn ngữ nghĩa, người dùng có thể viết truy vấn tổng hợp dễ hiểu và hệ thống có thể thực thi chúng chính xác ở quy mô lớn.

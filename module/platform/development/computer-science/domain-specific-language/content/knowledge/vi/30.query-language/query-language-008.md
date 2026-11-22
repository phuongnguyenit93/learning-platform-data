# Tối ưu hóa truy vấn

## Tối ưu hóa truy vấn trong DSL là gì?

Một ngôn ngữ chuyên miền dùng để truy vấn (query DSL) cho phép người dùng mô tả dữ liệu cần đọc, điều kiện lọc, phép kết hợp, nhóm, sắp xếp và giới hạn kết quả bằng cú pháp phù hợp với miền ứng dụng. DSL có thể trông giống SQL, biểu thức hướng đối tượng, API builder, truy vấn đồ thị hoặc một ngôn ngữ khai báo riêng.

Người dùng thường mô tả **muốn nhận kết quả nào**, còn hệ thống quyết định **thực hiện truy vấn bằng cách nào**. Cùng một truy vấn logic có thể được thực thi theo nhiều cách: quét toàn bộ dữ liệu, dùng index, đổi thứ tự join, đẩy bộ lọc xuống nguồn dữ liệu, dùng cache hoặc phân phối công việc cho nhiều node.

**Tối ưu hóa truy vấn (query optimization)** là quá trình biến đổi một truy vấn thành kế hoạch thực thi có chi phí phù hợp mà vẫn giữ nguyên ngữ nghĩa theo hợp đồng của DSL. Optimizer phân tích cấu trúc và metadata của truy vấn, tạo một hoặc nhiều phương án thực hiện, ước lượng chi phí rồi chọn kế hoạch dự kiến hiệu quả nhất.

Ví dụ, người dùng viết:

~~~text
FROM Orders
WHERE customerId = 42
  AND status = "PAID"
SELECT id, total, createdAt
ORDER BY createdAt DESC
LIMIT 20
~~~

Một cách thực thi đơn giản là đọc mọi order, lọc từng record, lấy ba trường, sắp xếp toàn bộ kết quả rồi lấy 20 dòng cuối. Nếu có index phù hợp trên customerId và status, hệ thống có thể tìm một tập record nhỏ hơn ngay từ đầu. Nếu index hỗ trợ thứ tự createdAt, engine có thể đọc các record theo thứ tự cần thiết và dừng sau 20 kết quả phù hợp.

Hai cách có thể trả cùng kết quả nhưng chi phí I/O, CPU và bộ nhớ rất khác nhau.

Tối ưu hóa đặc biệt quan trọng khi:

- Dữ liệu lớn hơn nhiều so với bộ nhớ.
- Truy vấn kết hợp nhiều nguồn hoặc nhiều bảng.
- DSL hỗ trợ join, aggregate, sort, subquery hoặc graph traversal.
- Người dùng không kiểm soát trực tiếp kế hoạch thực thi.
- Truy vấn được tạo tự động bởi ứng dụng.
- Cùng một DSL cần chạy trên nhiều backend.
- Workload có độ biến động lớn về số lượng dữ liệu và phân bố giá trị.
- Hệ thống cần giới hạn latency, memory hoặc chi phí tài nguyên.

Một optimizer tốt không chỉ làm truy vấn nhanh hơn. Nó còn phải giữ tính xác định, xử lý kiểu và null đúng, tôn trọng quyền truy cập, đưa ra kế hoạch có thể giải thích và tránh tiêu tốn quá nhiều thời gian để tự tối ưu.

## Phân biệt query optimization với parsing và execution

Một pipeline truy vấn thường gồm nhiều giai đoạn:

~~~text
Query DSL source
       |
       v
Lexing and parsing
       |
       v
AST / query syntax model
       |
       v
Name and type resolution
       |
       v
Logical query plan
       |
       v
Logical optimization
       |
       v
Physical plan selection
       |
       v
Physical optimization
       |
       v
Execution
       |
       v
Result
~~~

Mỗi giai đoạn có trách nhiệm riêng:

| Giai đoạn | Trách nhiệm |
|---|---|
| Parsing | Kiểm tra cú pháp và tạo cấu trúc truy vấn |
| Semantic analysis | Resolve tên, kiểu, quyền và quan hệ dữ liệu |
| Logical planning | Biểu diễn ý nghĩa truy vấn bằng operator |
| Logical optimization | Biến đổi plan nhưng giữ semantics |
| Physical planning | Chọn thuật toán và cách truy cập dữ liệu |
| Physical optimization | Chọn thứ tự, parallelism, memory strategy và runtime option |
| Execution | Thực hiện operator và tạo kết quả |

Parser không nên cố quyết định dùng index nào chỉ dựa trên token. Tại thời điểm parse, hệ thống có thể chưa biết schema, statistics, index, partition hoặc capability của backend.

Ngược lại, executor không nên phải diễn giải lại cú pháp DSL. Nó nên nhận physical plan đã được kiểm tra và có đầy đủ thông tin cần thiết.

### Tối ưu hóa không đồng nghĩa với viết lại cú pháp

Hai truy vấn có thể khác cách viết nhưng tạo cùng logical plan. Ví dụ, một DSL có thể hỗ trợ cả filter trước select và select trước filter:

~~~text
FROM Orders
WHERE status = "PAID"
SELECT id, total
~~~

~~~text
FROM Orders
SELECT id, total
FILTER status = "PAID"
~~~

Nếu grammar cho phép và semantics tương đương, compiler có thể chuẩn hóa cả hai thành cùng logical plan. Optimizer hoạt động trên mô hình đó, không cần chỉnh sửa source text.

### Tối ưu hóa không bảo đảm truy vấn luôn nhanh

Optimizer chọn kế hoạch dựa trên thông tin sẵn có và mô hình chi phí. Statistics có thể lỗi thời, dữ liệu có thể lệch phân bố hoặc backend có thể có độ trễ bất thường. Một plan tốt theo ước lượng vẫn có thể chạy kém trên dữ liệu thực tế.

Vì vậy, cần kết hợp optimizer với explain plan, runtime metrics, profiling và cơ chế cập nhật statistics.

## Logical query plan

Logical plan mô tả truy vấn bằng các phép toán có ý nghĩa, không gắn với cách lưu trữ hoặc thuật toán cụ thể.

Ví dụ truy vấn:

~~~text
FROM Orders
WHERE status = "PAID"
SELECT customerId, total
GROUP BY customerId
HAVING SUM(total) > 1000000
~~~

Có thể được biểu diễn bằng cây logical plan:

~~~text
Filter (SUM(total) > 1000000)
             |
Aggregate (group by customerId, SUM(total))
             |
Project (customerId, total)
             |
Filter (status = "PAID")
             |
Scan (Orders)
~~~

Tùy mô hình, Project có thể nằm trước hoặc sau Aggregate; điều quan trọng là mỗi operator có schema đầu vào/đầu ra và semantics được định nghĩa rõ.

### Các logical operator phổ biến

- Scan: đọc một nguồn dữ liệu.
- Filter: giữ các record thỏa predicate.
- Project: chọn hoặc tính toán các cột.
- Join: kết hợp hai input theo điều kiện.
- Aggregate: tính toán theo nhóm.
- Sort: sắp xếp theo biểu thức.
- Limit: giới hạn số kết quả.
- Distinct: loại bản ghi trùng theo semantics.
- Union: kết hợp các tập kết quả.
- Window: tính toán trên cửa sổ hàng.
- Unnest: mở rộng collection hoặc nested field.
- Apply: đánh giá biểu thức phụ thuộc vào từng record.
- Exchange: ranh giới phân phối dữ liệu trong hệ thống nhiều node.

Logical operator cần mô tả đủ thông tin để chứng minh các phép rewrite hợp lệ. Ví dụ, Filter phải biết predicate có thể trả về true, false hay unknown; Sort phải biết collation và null ordering; Aggregate phải biết hàm có associative hay không.

### Schema của từng node

Mỗi node nên có output schema gồm tên hoặc ID cột, kiểu, nullability, lineage và metadata liên quan.

Ví dụ:

~~~text
Project
  input:
    Orders(id: Int64, customerId: Int64, total: Decimal, status: String)
  output:
    customerId: Int64
    total: Decimal
~~~

Schema giúp optimizer loại cột không cần thiết, kiểm tra kiểu join, phát hiện cast và tránh truy cập dữ liệu không được yêu cầu.

### Logical plan chuẩn hóa

Trước khi tối ưu, compiler thường chuẩn hóa các biểu thức:

- Resolve identifier thành symbol hoặc column ID.
- Chuyển toán tử cú pháp thành operator chuẩn.
- Chèn cast ngầm theo type system nếu semantics cho phép.
- Gắn collation, timezone hoặc unit.
- Chuẩn hóa alias và scope.
- Biểu diễn subquery thành node rõ ràng.
- Đưa predicate về dạng dễ phân tích.

Chuẩn hóa nên giữ source location và mapping để diagnostics, explain và debug có thể truy ngược về DSL gốc.

## Physical query plan

Physical plan mô tả cách thực thi cụ thể trên storage engine hoặc backend. Một logical Join có thể được triển khai bằng hash join, merge join hoặc nested-loop join. Một logical Scan có thể là full table scan, index scan, partition scan hoặc remote scan.

Ví dụ:

~~~text
Logical:
  Join Orders with Customers on customerId
       |
       v
Physical:
  Hash Join
    Build: Hash Scan Customers
    Probe: Index Range Scan Orders
~~~

Physical plan phụ thuộc vào:

- Loại storage engine.
- Index và partition hiện có.
- Statistics và cardinality estimates.
- Khả năng đọc song song.
- Kích thước dữ liệu và giới hạn memory.
- Network và chi phí remote call.
- Capability của backend.
- Yêu cầu ordering hoặc consistency.
- Runtime configuration.

### Một logical plan có nhiều physical plan

Optimizer có thể tạo nhiều ứng viên:

| Logical operation | Physical alternatives |
|---|---|
| Scan | Table scan, index scan, partition scan, remote scan |
| Filter | Local filter, storage pushdown, vectorized filter |
| Join | Nested loop, hash join, merge join, index nested loop |
| Aggregate | Hash aggregate, sort aggregate, streaming aggregate |
| Sort | In-memory sort, external merge sort, index order |
| Distinct | Hash distinct, sort distinct |
| Union | Concatenate, merge union, distributed union |

Việc chọn thuật toán cần xem cả chi phí khởi tạo và chi phí theo số record. Index scan không phải lúc nào cũng nhanh hơn full scan; nếu truy vấn đọc phần lớn bảng, sequential scan có thể hiệu quả hơn.

### Physical properties

Physical operator có thể cung cấp hoặc yêu cầu các thuộc tính như:

- Ordering: dữ liệu đã được sắp xếp theo key nào.
- Distribution: dữ liệu được partition hoặc hash theo key nào.
- Partitioning: dữ liệu nằm trên node hoặc shard nào.
- Uniqueness: một key có duy nhất không.
- Boundedness: stream có giới hạn hay không.
- Materialization: kết quả đã được lưu trung gian chưa.

Optimizer có thể tận dụng physical property đã có để tránh sort, exchange hoặc materialization không cần thiết.

## Rule-based và cost-based optimization

Hai hướng tiếp cận chính là tối ưu theo quy tắc và tối ưu theo chi phí. Hệ thống thực tế thường kết hợp chúng.

### Rule-based optimization

Rule-based optimizer áp dụng một tập phép biến đổi được xác định trước. Mỗi rule nhận một pattern của plan và thay bằng một pattern tương đương.

Ví dụ:

~~~text
Filter(p, Filter(q, X))
              |
              v
Filter(p AND q, X)
~~~

Hoặc đẩy Filter qua Project nếu có thể ánh xạ predicate an toàn:

~~~text
Filter(p, Project(a, b, X))
                  |
                  v
Project(a, b, Filter(rewrite(p), X))
~~~

Ưu điểm:

- Dễ giải thích.
- Không phụ thuộc nhiều vào statistics.
- Kết quả có thể xác định.
- Phù hợp các rewrite có lợi ích rõ.
- Dễ kiểm thử từng rule.

Hạn chế:

- Không luôn chọn được thuật toán tốt nhất.
- Không biết kích thước dữ liệu thực tế.
- Thứ tự áp dụng rule có thể ảnh hưởng kết quả.
- Một số rewrite chỉ có lợi trong một số workload.

Rule-based thường phù hợp cho normalization và các phép rewrite mang tính đại số, trước khi cost-based planner lựa chọn physical plan.

### Cost-based optimization

Cost-based optimizer ước lượng chi phí của các plan ứng viên rồi chọn plan có cost thấp nhất theo mô hình.

Chi phí có thể gồm:

- Số lần đọc page hoặc record.
- CPU để đánh giá predicate và expression.
- Memory cho hash table, sort và intermediate result.
- Network transfer giữa node.
- Disk spill khi vượt memory.
- Số remote round trip.
- Startup latency.
- Chi phí serialization/deserialization.

Một cost model đơn giản:

~~~text
TotalCost =
    ScanCost
  + FilterCost
  + JoinCost
  + AggregateCost
  + SortCost
  + NetworkCost
  + SpillCost
~~~

Đây là mô hình khái niệm. Engine thực tế cần hiệu chỉnh trọng số theo storage, runtime, workload và mục tiêu latency/throughput.

Cost-based optimization có thể chọn plan tốt hơn khi có statistics, nhưng kết quả phụ thuộc chất lượng estimates. Nếu cardinality estimate sai nhiều, plan được chọn có thể rất tệ.

### Kết hợp hai phương pháp

Một pipeline phổ biến:

1. Chuẩn hóa logical plan.
2. Áp dụng các rewrite an toàn, có lợi ích rõ.
3. Sinh các physical alternative.
4. Ước lượng cardinality và cost.
5. Chọn plan tốt nhất.
6. Áp dụng physical refinement như parallelism hoặc memory strategy.

Không cần dùng cost search cho mọi rewrite. Một số rule chỉ làm plan gọn hơn và có thể được áp dụng trực tiếp.

## Các phép rewrite logic phổ biến

Logical rewrite biến đổi cây truy vấn mà không phụ thuộc vào thuật toán storage cụ thể. Mỗi rewrite phải bảo toàn kết quả theo semantics của DSL.

### Predicate pushdown

Predicate pushdown đưa điều kiện lọc gần nguồn dữ liệu nhất có thể:

~~~text
Before:
Project
  |
Filter(status = "PAID")
  |
Scan(Orders)

After:
Project
  |
Scan(Orders, pushedPredicate = status = "PAID")
~~~

Nếu storage engine có thể lọc dữ liệu ngay khi đọc, ít record phải đi qua các operator phía trên. Điều này giảm I/O, memory và network.

Predicate không phải lúc nào cũng pushdown được. Điều kiện có thể chứa function chỉ chạy ở application, function không deterministic, cast không được backend hỗ trợ hoặc semantics null khác nhau.

### Projection pushdown

Projection pushdown chỉ đọc những cột cần thiết:

~~~text
Before:
Scan Orders(id, customerId, total, status, note, payload, createdAt)
  |
Project(id, total)

After:
Scan Orders(id, total)
~~~

Đọc ít cột hơn có thể giảm page I/O, network transfer và memory, đặc biệt với columnar storage hoặc record có field lớn.

Optimizer cần giữ các cột phụ phục vụ filter, join, group, order và expression, kể cả khi chúng không xuất hiện trong output cuối.

### Constant folding

Biểu thức chỉ chứa hằng số có thể được tính trước:

~~~text
WHERE order.total > (100 * 10)
~~~

có thể trở thành:

~~~text
WHERE order.total > 1000
~~~

Constant folding giảm công việc lúc chạy. Tuy nhiên, cần tôn trọng overflow, precision, timezone, error semantics và function có side effect. Không được tính trước một biểu thức mà ngôn ngữ định nghĩa chỉ được đánh giá khi nhánh tương ứng được thực thi.

### Constant propagation

Nếu một predicate đã xác định giá trị của biểu thức, optimizer có thể dùng thông tin đó ở phần sau.

Ví dụ:

~~~text
WHERE status = "PAID"
  AND status = "PENDING"
~~~

Nếu equality và collation semantics cho thấy hai điều kiện mâu thuẫn, plan có thể trở thành EmptyResult. Cần thận trọng với nullable field, collation không phân biệt hoa thường hoặc phép so sánh có ba giá trị.

### Simplification predicate

Một số biểu thức có thể được rút gọn:

~~~text
WHERE isActive = true AND region = "APAC"
~~~

có thể bỏ phép so sánh với true nếu semantics boolean và null cho phép. Các quy tắc như p AND TRUE = p chỉ hợp lệ khi mô hình logic của DSL bảo đảm điều đó.

### Join elimination

Nếu một join không đóng góp cột, predicate hoặc tính chất uniqueness cần thiết, có thể loại bỏ nó. Ví dụ, join đến bảng lookup chỉ để xác nhận tồn tại có thể được thay bằng semi-join hoặc bỏ đi nếu foreign key và constraint chứng minh kết quả không đổi.

Không được loại bỏ join chỉ vì không lấy cột của bảng bên kia. Join có thể làm thay đổi số hàng khi quan hệ là one-to-many hoặc khi điều kiện lọc phụ thuộc bảng đó.

### Subquery decorrelation

Một correlated subquery có thể được chuyển thành join hoặc aggregate để tránh chạy lại subquery cho từng hàng.

Ví dụ:

~~~text
SELECT customer.id
FROM Customers customer
WHERE EXISTS (
  SELECT 1
  FROM Orders order
  WHERE order.customerId = customer.id
)
~~~

Có thể được chuyển thành semi-join:

~~~text
SemiJoin(
  Customers,
  Orders,
  Customers.id = Orders.customerId
)
~~~

Decorrelate cần bảo toàn duplicate, null và semantics của EXISTS/IN. Không phải subquery nào cũng có thể chuyển đổi đơn giản.

### Limit pushdown

Nếu semantics cho phép, LIMIT có thể được đẩy xuống gần nguồn hoặc vào sort/index operator để giảm dữ liệu cần xử lý.

Tuy nhiên, không được đẩy LIMIT qua operator có thể thay đổi thứ tự hoặc số hàng theo cách làm kết quả khác. Ví dụ, LIMIT trước ORDER BY thường không tương đương LIMIT sau ORDER BY.

### Aggregate pushdown

Nếu nguồn dữ liệu hỗ trợ aggregate, engine có thể đẩy SUM, COUNT hoặc GROUP BY xuống storage/backend để giảm dữ liệu truyền về. Với distributed aggregation, có thể tính partial aggregate tại từng partition rồi merge kết quả.

Cần biết hàm aggregate có thể kết hợp chính xác hay không. SUM và COUNT thường có thể dùng partial aggregation; median hoặc percentile có thể cần state lớn hoặc thuật toán xấp xỉ.

## Tối ưu hóa join

Join thường là phần tốn kém nhất trong truy vấn phân tích dữ liệu vì số hàng trung gian có thể tăng rất nhanh.

### Join order

Với nhiều bảng, thứ tự join ảnh hưởng mạnh đến cardinality trung gian.

Ví dụ:

~~~text
A JOIN B JOIN C
~~~

Có thể được thực hiện:

~~~text
(A JOIN B) JOIN C
~~~

hoặc:

~~~text
A JOIN (B JOIN C)
~~~

Nếu A và B tạo ra tập trung gian rất lớn trong khi B và C có điều kiện lọc mạnh, thứ tự thứ hai có thể rẻ hơn.

Optimizer dùng statistics để ước lượng kích thước từng bước và tìm join order tốt. Với N bảng, số thứ tự kết hợp có thể tăng theo cấp số nhân hoặc giai thừa tùy không gian tìm kiếm và ràng buộc.

### Cardinality của join

Số hàng đầu ra phụ thuộc:
- Số hàng mỗi input.
- Số giá trị distinct của join key.
- Phân bố key.
- Null và duplicate.
- Join type.
- Predicate bổ sung.
- Constraint như primary key và foreign key.

Ước lượng đơn giản cho equi-join có thể dùng số distinct value:

~~~text
EstimatedJoinRows ≈
  Rows(A) * Rows(B)
  / max(NDV(A.key), NDV(B.key))
~~~

Đây chỉ là heuristic. Nó giả định phân bố tương đối đồng đều và độc lập; dữ liệu skew hoặc correlation giữa các cột có thể khiến estimate sai.

### Nested-loop join

Nested-loop join duyệt một input và tìm hàng phù hợp trong input còn lại. Nó phù hợp khi một phía rất nhỏ hoặc có index lookup hiệu quả.

Chi phí có thể tăng mạnh nếu phải quét toàn bộ inner input cho từng row outer. Index nested-loop join giảm chi phí khi inner key có index.

### Hash join

Hash join xây hash table từ một input, sau đó probe bằng input còn lại. Nó thường phù hợp với equi-join khi một phía có kích thước vừa đủ để giữ trong memory.

Cần chọn build side hợp lý, thường là phía nhỏ hơn theo ước lượng. Nếu hash table vượt memory, engine có thể partition và spill ra disk, làm chi phí tăng đáng kể.

### Merge join

Merge join cần hai input được sắp xếp theo join key. Nó duyệt hai dãy theo thứ tự để tìm cặp phù hợp. Nếu dữ liệu đã có ordering phù hợp, merge join có thể hiệu quả; nếu phải sort cả hai input, tổng chi phí cần được so sánh với hash join.

### Semi-join và anti-join

Semi-join chỉ cần biết có ít nhất một hàng khớp; anti-join tìm hàng không có đối tác phù hợp. Chúng phù hợp với EXISTS, NOT EXISTS hoặc một số dạng IN.

Dùng semi-join thay cho join thông thường có thể tránh tạo duplicate không cần thiết. Nhưng NOT IN có semantics khác NOT EXISTS khi subquery chứa NULL; optimizer phải giữ đúng semantics của DSL.

## Statistics và cardinality estimation

Cost-based optimizer cần ước lượng số hàng, số giá trị distinct, phân bố và kích thước dữ liệu.

### Table statistics

Các thông tin phổ biến:

- Row count.
- Page count hoặc byte size.
- Average row width.
- Number of distinct values.
- Null fraction.
- Minimum và maximum.
- Histogram phân bố giá trị.
- Correlation giữa các cột.
- Index selectivity.

Statistics có thể được thu thập khi nạp dữ liệu, qua analyze command hoặc cập nhật định kỳ.

### Column statistics

Giả sử cột status có 100 triệu record nhưng chỉ ba giá trị. Predicate status = "PAID" có thể chọn phần lớn dữ liệu nếu PAID chiếm 90%, hoặc chỉ một phần nhỏ nếu chiếm 2%.

Chỉ biết NDV bằng 3 không đủ để ước lượng selectivity chính xác. Histogram hoặc most-common-values statistics có thể giúp.

### Correlation giữa predicate

Giả sử country và currency có quan hệ gần như xác định. Nếu optimizer giả định độc lập, xác suất country = VN AND currency = VND có thể bị ước lượng sai.

Extended statistics hoặc multi-column histogram có thể cải thiện estimate. Tuy nhiên, thu thập và lưu statistics phức tạp hơn, cần cân nhắc chi phí.

### Statistics lỗi thời

Dữ liệu thay đổi theo thời gian. Row count và histogram cũ có thể dẫn đến plan không còn phù hợp.

Hệ thống có thể:
- Refresh theo lịch.
- Refresh sau khi dữ liệu thay đổi vượt ngưỡng.
- Dùng adaptive statistics.
- Ghi nhận statistics age.
- Cảnh báo khi estimate và actual row count chênh lệch lớn.

### Ước lượng sai và hậu quả

Một estimate sai ở đầu cây có thể lan truyền đến nhiều operator. Optimizer có thể chọn nested loop cho một input lớn hoặc hash join quá lớn so với memory.

Explain Analyze nên hiển thị estimated rows và actual rows để tìm điểm lệch đầu tiên trong plan.

## Index và access path selection

Index là cấu trúc phụ giúp tìm dữ liệu mà không phải quét toàn bộ nguồn. Optimizer quyết định có dùng index hay không dựa trên selectivity, cost, ordering và coverage.

### B-tree index

B-tree phù hợp với equality và range predicate trên key được index, ví dụ:

~~~text
WHERE createdAt >= DATE("2026-01-01")
  AND createdAt < DATE("2027-01-01")
~~~

Composite index có thứ tự cột. Index trên (customerId, createdAt) có thể hỗ trợ truy vấn lọc customerId và sắp xếp createdAt, nhưng không nhất thiết hiệu quả cho truy vấn chỉ lọc createdAt nếu key prefix không phù hợp.

### Hash index

Hash index có thể phù hợp với equality lookup, nhưng thường không hỗ trợ range scan hoặc ordering như B-tree. Khả năng thực tế phụ thuộc storage engine.

### Covering index

Một covering index chứa đủ key và field cần đọc, giúp truy vấn không phải truy cập row storage cho từng kết quả.

Ví dụ truy vấn lấy customerId, createdAt, total và lọc theo status có thể được phục vụ bởi index phù hợp nếu các field cần thiết đều có trong index.

### Bitmap và specialized index

Bitmap index có thể hiệu quả cho cột có cardinality thấp trong một số hệ thống phân tích. Full-text, spatial, inverted hoặc vector index hỗ trợ loại predicate đặc thù. Optimizer cần biết capability và cost model của từng loại.

### Index không phải luôn tốt hơn scan

Nếu predicate chọn 70% bảng, index lookup có thể tạo nhiều random I/O hơn full scan. Nếu bảng nhỏ, full scan có thể rẻ hơn chi phí mở index. Optimizer cần so sánh các access path dựa trên data size và storage characteristics.

### Partition pruning

Nếu dữ liệu partition theo ngày và truy vấn có filter ngày rõ, optimizer có thể loại bỏ partition không liên quan:

~~~text
WHERE createdAt >= "2026-10-01"
  AND createdAt < "2026-11-01"
~~~

Partition pruning giảm lượng dữ liệu đọc. Predicate cần đủ rõ và có thể được chuyển thành điều kiện trên partition key. Function hoặc cast không phù hợp quanh key có thể cản trở pruning.

## Predicate ordering và evaluation

Một số hệ thống thực thi nhiều điều kiện theo thứ tự. Nếu một predicate rẻ và chọn lọc cao, đánh giá nó sớm có thể giảm số record phải đi qua predicate đắt.

Ví dụ:

~~~text
WHERE status = "PAID"
  AND expensiveRiskScore(customerId) > 0.8
~~~

Nếu status loại bỏ phần lớn record, engine có thể đánh giá expensiveRiskScore trên tập nhỏ hơn. Tuy nhiên, đổi thứ tự chỉ hợp lệ khi expression không có side effect và semantics của lỗi/short-circuit cho phép.

### Predicate selectivity

Selectivity là tỷ lệ hàng vượt qua điều kiện. Predicate có selectivity 0.01 giữ khoảng 1% dữ liệu; predicate có selectivity 0.9 giữ khoảng 90%.

Optimizer có thể ưu tiên predicate rẻ, có selectivity cao, nhưng chi phí function và khả năng pushdown cũng cần được xét. Không nên chỉ sắp xếp theo selectivity nếu việc đánh giá predicate có thể gây lỗi hoặc tác dụng phụ.

### Short-circuit semantics

Nếu DSL quy định AND dùng short-circuit, vế phải có thể không được đánh giá khi vế trái false. Reordering hai vế có thể thay đổi exception hoặc side effect.

Nếu DSL định nghĩa biểu thức truy vấn là pure và không quan sát thứ tự evaluation, optimizer có nhiều tự do hơn. Tính purity cần được xác định bởi language semantics, không suy ra từ tên function.

### Three-valued logic

Trong SQL-like DSL, predicate có thể trả về TRUE, FALSE hoặc UNKNOWN khi có NULL. Các luật Boolean hai giá trị không phải lúc nào cũng áp dụng trực tiếp.

Ví dụ:

~~~text
NULL = 5
~~~

có thể cho UNKNOWN. Filter thường chỉ giữ TRUE, nhưng NOT, IN, BETWEEN và join condition cần tuân theo cùng mô hình logic.

Optimizer phải dùng truth table phù hợp để rewrite. Không thể tùy tiện biến NOT IN thành anti-join nếu có khả năng NULL làm kết quả khác.

## Tối ưu hóa projection, sorting và aggregation

Ngoài filter và join, các operator tiêu tốn dữ liệu trung gian lớn cũng cần được tối ưu.

### Projection pruning

Optimizer loại bỏ cột không cần thiết khỏi các node phía dưới. Một cột vẫn phải được giữ nếu dùng trong predicate, join key, grouping, ordering hoặc expression được tính sau đó.

### Top-N optimization

Truy vấn:

~~~text
ORDER BY total DESC
LIMIT 10
~~~

không nhất thiết phải sort toàn bộ hàng. Engine có thể dùng top-N heap giữ 10 phần tử tốt nhất, giảm bộ nhớ từ O(N) xuống gần O(K) với K là limit, dù vẫn cần đọc các candidate liên quan.

Nếu có index theo total, engine có thể đọc theo thứ tự và dừng sớm khi đủ kết quả, tùy predicate và consistency.

### Partial aggregation

Trong hệ thống phân tán, mỗi partition có thể tính partial sum/count rồi gửi state nhỏ hơn để merge:

~~~text
Partition 1 -> Partial Aggregate --\
Partition 2 -> Partial Aggregate ---+--> Final Aggregate
Partition 3 -> Partial Aggregate --/
~~~

Cách này giảm dữ liệu truyền qua network. Cần bảo đảm aggregate state có thể kết hợp và kết quả giữ precision theo semantics.

### Streaming aggregation

Nếu input đã được sắp xếp theo group key, engine có thể tính aggregate theo từng nhóm mà không cần hash table lớn. Nếu không có ordering, hash aggregate có thể phù hợp hơn nhưng cần memory hoặc spill strategy.

### DISTINCT

DISTINCT có thể dùng hash set hoặc sort-based deduplication. Nếu input đã unique theo constraint hoặc key, optimizer có thể loại bỏ DISTINCT khi chứng minh được điều đó.

## Subquery, CTE và materialization

DSL truy vấn có thể hỗ trợ subquery hoặc common table expression (CTE) để tổ chức logic.

~~~text
WITH paidOrders AS (
  FROM Orders
  WHERE status = "PAID"
)
FROM paidOrders
WHERE total > 100000
SELECT id, total
~~~

Optimizer có thể inline CTE vào plan hoặc materialize kết quả trung gian.

### Inlining

Inlining thay reference đến CTE bằng plan của CTE. Nó có thể cho phép predicate pushdown và join reorder qua ranh giới CTE.

Nhược điểm là nếu CTE được dùng nhiều lần, inlining có thể lặp công việc hoặc làm plan phình lớn.

### Materialization

Materialization tính CTE một lần và lưu kết quả tạm để nhiều consumer dùng lại. Nó hữu ích khi CTE đắt và được tham chiếu nhiều lần, nhưng tạo chi phí ghi/đọc intermediate data và có thể ngăn một số rewrite.

### Materialization boundary

Một DSL có thể cung cấp hint hoặc keyword để yêu cầu materialization. Cần quy định đây là bắt buộc hay chỉ là gợi ý. Nếu user yêu cầu materialize để bảo đảm snapshot hoặc semantics, optimizer phải tôn trọng hợp đồng đó.

### Recursive query

Recursive CTE hoặc graph traversal có thể tạo lượng dữ liệu lớn. Optimizer cần xem termination condition, maximum depth, duplicate handling và cycle detection. Không được rewrite làm thay đổi thứ tự hoặc semantics của recursion nếu DSL quy định rõ.

## Tối ưu hóa cho backend và nguồn dữ liệu khác nhau

Một query DSL có thể chạy trên relational database, document store, search engine, data lake hoặc API. Mỗi backend hỗ trợ operator và cost khác nhau.

### Capability-aware planning

Backend có thể công bố capability:

~~~text
BackendCapabilities
  supportsFilterPushdown
  supportsProjectionPushdown
  supportsHashJoin
  supportsWindowFunctions
  supportsTransactions
  supportedFunctions
  supportedTypes
  maxInListSize
~~~

Optimizer chỉ push operator khi backend hỗ trợ semantics tương đương. Nếu backend không hỗ trợ một function, phần đó có thể được thực thi ở application layer sau khi dữ liệu được đọc về.

### Remote query pushdown

Đẩy filter, projection hoặc aggregate đến nguồn remote có thể giảm network transfer. Nhưng remote backend có thể dùng collation, timezone, null semantics hoặc decimal behavior khác DSL.

Cần có compatibility mapping cho operator và kiểu dữ liệu. Nếu semantics không tương đương, optimizer phải giữ operator ở local layer hoặc dùng adapter để chuẩn hóa.

### Federated query

Khi join nhiều nguồn, cost model cần xem:
- Chi phí truy cập từng nguồn.
- Network latency và bandwidth.
- Khả năng pushdown.
- Kích thước dữ liệu sau filter.
- Nơi đặt dữ liệu.
- Quyền và credential theo nguồn.
- Consistency giữa các nguồn.

Có thể chọn đưa tập nhỏ từ nguồn A sang nguồn B để join, hoặc lấy dữ liệu về coordinator. Lựa chọn phụ thuộc dữ liệu và capability thực tế.

### Backend-specific optimizer

Một kiến trúc tốt có thể có logical optimizer dùng chung và physical planner riêng cho từng backend:

~~~text
Query DSL
   |
Canonical Logical Plan
   |
Shared Logical Rewrites
   |
   +--> SQL Backend Planner
   +--> Search Backend Planner
   +--> Document Store Planner
   +--> In-memory Engine Planner
~~~

Cách này giữ semantics chung trong logical layer nhưng cho phép mỗi backend dùng access path và thuật toán phù hợp.

## Parameterization và prepared query

Nhiều truy vấn được thực hiện lặp lại với các giá trị khác nhau:

~~~text
FROM Orders
WHERE customerId = :customerId
  AND status = :status
SELECT id, total
~~~

Parameterization tách cấu trúc truy vấn khỏi dữ liệu cụ thể. Nó giúp tái sử dụng plan, giảm chi phí parse/plan và tránh nối chuỗi tạo query không an toàn.

### Prepared plan

Một prepared query có thể được parse và optimize một lần, sau đó bind parameter ở mỗi lần thực thi. Tuy nhiên, parameter value có thể ảnh hưởng selectivity và plan tốt nhất.

Nếu customerId thường có rất ít hàng nhưng một số customer có hàng triệu order, cùng một generic plan có thể không phù hợp cho mọi giá trị.

### Parameter-sensitive planning

Một số engine dùng parameter-sensitive plan, adaptive plan hoặc re-optimization khi giá trị parameter làm thay đổi cardinality đáng kể.

Cần cân bằng chi phí tối ưu lại với lợi ích runtime. Không nên cache plan chỉ theo query text nếu schema, statistics, role, backend hoặc parameter class có ảnh hưởng.

### Query parameter và injection

Giá trị người dùng nên được bind như parameter, không ghép vào source DSL bằng string concatenation. Với các phần cấu trúc như tên cột hoặc sort direction, cần resolve qua schema và allowlist vì chúng thường không thể bind như literal value.

## Plan cache và result cache

Cache có thể được dùng ở nhiều tầng, nhưng cần phân biệt nội dung được cache và điều kiện hợp lệ.

### Parse cache

Lưu AST hoặc normalized query model cho query text giống nhau. Cache key cần bao gồm language version, grammar version và các tùy chọn parse có ảnh hưởng.

### Plan cache

Lưu logical hoặc physical plan. Key có thể cần bao gồm:
- Normalized query shape.
- Schema version.
- Statistics epoch hoặc plan invalidation version.
- Backend capabilities.
- Security context hoặc role nếu ảnh hưởng đến plan.
- Parameter type và parameter-sensitive class.
- Session options có tác động đến semantics.

Khi index, schema hoặc statistics thay đổi, plan có thể cần invalidation hoặc revalidation.

### Result cache

Lưu kết quả truy vấn. Cache result khó hơn vì dữ liệu nguồn có thể thay đổi, quyền người dùng khác nhau và truy vấn có thể chứa function phụ thuộc thời gian.

Cần xác định:
- TTL.
- Data version hoặc invalidation event.
- Security partition.
- Parameter key.
- Determinism của function.
- Kích thước tối đa.
- Hành vi khi cache stale.

Không nên dùng result cache cho query chứa current time, random function hoặc dữ liệu nhạy cảm nếu không có semantics và policy rõ.

### Cache stampede

Nhiều request cùng miss một key có thể đồng thời thực hiện cùng truy vấn đắt. Có thể dùng single-flight, request coalescing hoặc lock có giới hạn. Cần tránh một request giữ lock quá lâu làm nghẽn các request khác.

## Tối ưu hóa truy vấn phân tán

Trong hệ thống phân tán, chi phí network, data movement và synchronization có thể lớn hơn CPU tại một node.

### Data locality

Ưu tiên thực hiện filter và aggregate gần nơi dữ liệu được lưu để giảm lượng truyền đi. Một query coordinator có thể chọn node thực thi dựa trên partition locality.

### Exchange và shuffle

Một số operator cần dữ liệu có cùng key nằm trên cùng partition. Ví dụ distributed hash join hoặc group by có thể yêu cầu shuffle.

~~~text
Input partitions
      |
      v
Hash partition by join key
      |
      v
Network exchange
      |
      v
Local join on each worker
~~~

Shuffle có thể chiếm nhiều network và disk I/O. Optimizer cần ước lượng bytes truyền, skew và số partition.

### Broadcast join

Nếu một phía rất nhỏ, engine có thể broadcast nó đến mọi worker thay vì shuffle cả hai phía. Cần giới hạn kích thước broadcast để tránh nhân bản dữ liệu lớn vào mọi node.

### Data skew

Một số key có thể xuất hiện nhiều hơn hẳn phần còn lại. Hash partition theo key khi đó tạo một partition quá lớn, gây straggler.

Có thể dùng skew detection, salting, adaptive repartition hoặc xử lý riêng hot key. Những kỹ thuật này cần giữ đúng kết quả và không tạo duplicate ngoài ý muốn.

### Adaptive query execution

Một số engine có thể quan sát cardinality thực tế khi chạy và điều chỉnh plan giữa chừng, ví dụ đổi join strategy hoặc số partition.

Adaptive execution có thể xử lý estimate sai, nhưng làm tăng độ phức tạp của runtime. Explain Analyze cần cho thấy plan ban đầu và các thay đổi thực tế để người vận hành hiểu kết quả.

## Giữ nguyên semantics khi tối ưu

Một rewrite chỉ hợp lệ nếu giữ hành vi theo semantics của DSL. Tương đương đại số không đủ nếu ngôn ngữ có side effect, lỗi quan sát được hoặc quy tắc evaluation đặc biệt.

### Null và three-valued logic

Các phép so sánh với NULL có thể trả về UNKNOWN. Filter thường chỉ giữ TRUE. Rewrite của NOT, IN, NOT IN, equality và outer join phải giữ đúng logic này.

Ví dụ, NOT IN với tập chứa NULL có thể khác NOT EXISTS. Optimizer cần mô hình hóa semantics thay vì thay pattern theo cú pháp đơn thuần.

### Duplicate và bag semantics

Một số DSL dùng set semantics, loại duplicate mặc định; số khác dùng bag semantics, giữ số lần xuất hiện. Join, union, distinct elimination và aggregation có thể khác kết quả tùy semantics.

Không được loại DISTINCT nếu chưa chứng minh input unique. Không được đổi UNION ALL thành UNION vì nó làm mất duplicate.

### Ordering

Quan hệ dữ liệu thường không có thứ tự mặc định. Nếu DSL chỉ bảo đảm ordering khi có ORDER BY, optimizer có thể thay đổi thứ tự nội bộ trước đó. Nhưng khi LIMIT, OFFSET hoặc window function liên quan đến thứ tự, cần bảo toàn đúng ordering contract.

Không được đẩy LIMIT qua một operator nếu thứ tự kết quả có thể thay đổi.

### Volatile và side-effecting functions

Function như random(), currentTimestamp(), sequenceNext() hoặc function gọi service ngoài có thể cho kết quả khác nhau giữa các lần đánh giá.

Optimizer không được tự ý:
- Tính function volatile một lần thay vì nhiều lần.
- Đánh giá expression sớm hơn.
- Đổi thứ tự evaluation nếu có side effect.
- Loại bỏ expression chỉ vì kết quả không được project ra nếu nó có side effect hoặc có thể ném lỗi theo semantics.

Function nên có metadata như deterministic, immutable, stable, volatile, pure hoặc side-effecting để optimizer biết phép rewrite nào hợp lệ.

### Error semantics và cast

Cast có thể thất bại với dữ liệu không hợp lệ. Đẩy cast qua filter hoặc đổi thứ tự có thể làm lỗi xuất hiện ở thời điểm khác hoặc trên nhiều record hơn.

Một DSL có thể hỗ trợ safe cast trả về null hoặc Result type để rewrite dễ dự đoán hơn. Dù vậy, semantics phải được định nghĩa rõ.

### Timezone, collation và numeric precision

So sánh string có thể phụ thuộc collation. Timestamp có thể phụ thuộc timezone. Decimal có precision và scale; floating-point có sai số và tính không kết hợp của phép cộng.

Optimizer không nên áp dụng luật đại số chính xác cho floating-point nếu điều đó thay đổi kết quả quan sát được và DSL yêu cầu giữ thứ tự tính toán.

### Security và row-level filtering

Một query có thể bị giới hạn bởi row-level security, tenant scope hoặc permission filter. Optimizer chỉ được di chuyển predicate nếu bảo toàn ranh giới bảo mật và không làm lộ dữ liệu qua timing, error hoặc intermediate result.

Policy filter cần được biểu diễn trong plan như một phần semantics, không phải một điều kiện tùy chọn có thể bị loại bỏ.

## Query hints và kiểm soát của người dùng

Một số DSL cho phép người dùng gợi ý optimizer:

~~~text
FROM Orders
HINT USE_INDEX("idx_orders_customer")
WHERE customerId = 42
SELECT id, total
~~~

Hint có thể yêu cầu:
- Index cụ thể.
- Join strategy.
- Join order.
- Parallelism.
- Materialization.
- Memory budget.
- Backend hoặc execution mode.

### Hint là gợi ý hay ràng buộc?

Cần phân biệt advisory hint và hard constraint.

- Advisory hint: optimizer có thể bỏ qua nếu không phù hợp.
- Hard constraint: hệ thống phải tuân thủ hoặc báo lỗi nếu không thể.

Nếu optimizer âm thầm bỏ qua hint, explain cần cho biết lý do. Nếu hard constraint làm plan không thể thực thi, cần diagnostic rõ.

### Không để hint thay thế cost model

Hint có thể giúp điều tra hoặc xử lý workload đặc biệt, nhưng nếu người dùng phải thêm hint cho mọi truy vấn, optimizer hoặc statistics có thể chưa tốt.

Nên thu thập plan và runtime evidence, cải thiện cost model hoặc schema/index trước khi biến hint thành cấu hình lâu dài.

### Hint và portability

Hint thường gắn với backend. Nếu query DSL hỗ trợ nhiều backend, cần namespace hint hoặc capability check để tránh một hint có nghĩa khác trên engine khác.

## Explain plan và phân tích hiệu năng

Người dùng và developer cần biết optimizer đã chọn plan nào và vì sao.

### EXPLAIN

EXPLAIN hiển thị plan trước khi thực thi:

~~~text
EXPLAIN
FROM Orders
WHERE customerId = 42
  AND status = "PAID"
SELECT id, total
ORDER BY createdAt DESC
LIMIT 20
~~~

Output minh họa:

~~~text
Limit 20
  |
Index Scan idx_orders_customer_created
  Index condition: customerId = 42
  Filter: status = "PAID"
  Order: createdAt DESC
~~~

EXPLAIN nên cho biết:
- Logical plan.
- Physical plan.
- Access path.
- Join strategy và join order.
- Estimated rows.
- Estimated cost.
- Predicate được pushdown.
- Sort hoặc exchange.
- Cache hoặc materialization.
- Warning về estimate hoặc unsupported operator.

### EXPLAIN ANALYZE

EXPLAIN ANALYZE thực thi truy vấn và bổ sung số liệu thực tế:

~~~text
Index Scan
  estimated rows: 1200
  actual rows: 1187
  loops: 1
  time: 8.4 ms
  buffers read: 24
~~~

Cần cảnh báo rằng EXPLAIN ANALYZE thực sự chạy query. Với query có side effect, mutation hoặc chi phí cao, cần cơ chế read-only, transaction rollback hoặc confirmation phù hợp.

### Estimated và actual

So sánh estimated rows với actual rows giúp phát hiện sai số cardinality. Nên tìm node đầu tiên có chênh lệch lớn, vì lỗi estimate ở đó có thể lan truyền xuống các node cha.

### Plan visualization

Editor có thể hiển thị plan dưới dạng cây hoặc graph, cho phép chọn node để xem:
- Operator type.
- Input/output schema.
- Estimated/actual rows.
- Time và memory.
- Predicate.
- Source location của query DSL.
- Index hoặc partition được sử dụng.

Mapping từ plan node về source span giúp người dùng biết phần DSL nào tạo ra operator đắt.

### Plan fingerprint

Một fingerprint ổn định có thể dùng để nhóm truy vấn có cùng cấu trúc plan, so sánh phiên bản hoặc phát hiện plan regression. Không nên dùng raw query text chứa literal nhạy cảm làm định danh telemetry nếu có thể chuẩn hóa thành query shape.

## Instrumentation và runtime feedback

Optimizer cần dữ liệu thực thi để kiểm chứng cost model.

Các số liệu runtime có thể gồm:

- Actual rows theo operator.
- Input/output bytes.
- CPU time.
- Wall-clock duration.
- Memory peak.
- Disk spill bytes.
- Buffer/cache hit.
- Network bytes.
- Number of loops.
- Rows filtered.
- Remote calls.
- Cancellation và timeout.

Một operator Filter có thể ghi input rows và output rows để suy ra selectivity thực tế. Join có thể ghi build rows, probe rows và output rows. Sort có thể ghi số phần tử, memory peak và spill count.

### Không làm runtime instrumentation quá đắt

Đếm từng record hoặc tạo trace span cho từng operator invocation có thể tạo overhead đáng kể. Có thể dùng counters theo batch, sampling hoặc profile mode.

### Feedback vào optimizer

Một số hệ thống dùng runtime feedback để cập nhật statistics hoặc chọn plan cho lần chạy sau. Cần tránh overfit từ một execution bất thường. Feedback nên có version, workload class và kiểm soát outlier.

### Query regression

Có thể lưu baseline cho query quan trọng:
- Plan fingerprint.
- p50/p95 duration.
- Rows scanned.
- Memory.
- Spill.
- Result cardinality.
- Backend version.

Khi plan thay đổi hoặc latency vượt ngưỡng, hệ thống có thể cảnh báo. So sánh cần cùng workload và dữ liệu tương đương.

## Tối ưu hóa trong DSL truy vấn hướng đối tượng và API builder

Không phải query DSL nào cũng dùng cú pháp văn bản. Một số DSL được xây bằng method chain hoặc object expression.

Ví dụ:

~~~java
query.from(Orders.class)
     .where(o -> o.getStatus().eq("PAID"))
     .where(o -> o.getCustomerId().eq(customerId))
     .select(o -> tuple(o.getId(), o.getTotal()));
~~~

Các API call tạo expression tree hoặc query model. Optimizer có thể áp dụng cùng logical rewrites sau khi expression được chuyển thành canonical plan.

### Expression tree thay vì thực thi ngay

Nếu mỗi method lập tức truy cập database, hệ thống khó tối ưu toàn truy vấn vì không có cái nhìn tổng thể. Một query builder thường lưu expression trước, rồi compile thành plan khi execute.

### Lambda translation

Nếu DSL nhận lambda, chỉ những expression có thể phân tích tĩnh mới được chuyển thành query operator. Một lambda chứa I/O, mutable state hoặc gọi function tùy ý có thể không dịch được.

Cần phân biệt:
- Biểu thức được translate sang backend.
- Biểu thức được evaluate tại application.
- Biểu thức không được hỗ trợ.

Không nên âm thầm chuyển một phần predicate về client nếu điều đó làm đọc quá nhiều dữ liệu hoặc thay đổi semantics.

### Reuse và parameterization

Query builder có thể tạo query shape ổn định với parameter. Điều này hỗ trợ prepared plan và tránh tạo nhiều plan chỉ vì literal khác nhau.

## Query optimization cho streaming và event data

Một số DSL truy vấn xử lý stream hoặc event liên tục thay vì bảng tĩnh. Các phép tối ưu cần xét thời gian và trạng thái.

### Windowing

Window operator gom event theo thời gian hoặc số lượng:

~~~text
FROM PaymentEvents
WINDOW TUMBLING 5 MINUTES
GROUP BY merchantId
SELECT merchantId, COUNT(*)
~~~

Optimizer cần hiểu event time, processing time, watermark, lateness và window boundary. Đổi thứ tự window với filter hoặc aggregate có thể làm thay đổi kết quả nếu predicate phụ thuộc thời gian hoặc event bị đến muộn.

### State size

Join hai stream hoặc aggregate theo key có thể giữ state lâu. Cost model cần xem:
- Tốc độ event.
- Window size.
- Key cardinality.
- Retention period.
- State backend.
- Checkpoint frequency.
- Late event handling.

### Filter pushdown và event-time predicate

Filter theo event-time có thể giúp loại event sớm, nhưng phải giữ semantics của watermark và late arrival. Predicate theo processing time có thể không tương đương khi replay.

### Backpressure

Plan streaming cần kiểm soát tốc độ producer và consumer. Metrics queue, buffer, lag và backpressure giúp phát hiện operator downstream không theo kịp.

## Tối ưu hóa truy vấn đồ thị

Một graph query DSL có thể biểu diễn node, edge, path và traversal.

Ví dụ:

~~~text
MATCH (customer:Customer)-[:PLACED]->(order:Order)
WHERE customer.region = "APAC"
RETURN customer.id, order.total
~~~

Optimizer có thể:
- Bắt đầu traversal từ tập node có predicate chọn lọc.
- Dùng index trên label hoặc property.
- Chọn hướng traversal phù hợp.
- Đẩy filter xuống node scan.
- Giới hạn độ sâu path khi semantics cho phép.
- Tránh mở rộng path không cần thiết.
- Chọn strategy cho variable-length traversal.

### Cardinality graph

Chi phí traversal phụ thuộc degree distribution. Một node có degree rất lớn có thể tạo bùng nổ số path. Average degree có thể che giấu hub node; optimizer có thể cần histogram hoặc statistics theo label/property.

### Path semantics

Một số DSL phân biệt walk, trail và simple path; có thể cho phép lặp node hoặc edge. Optimizer phải giữ đúng semantics khi loại duplicate hoặc đổi traversal order.

### Early termination

Nếu query chỉ cần EXISTS hoặc LIMIT nhỏ, engine có thể dừng traversal sớm khi tìm đủ kết quả, miễn là ordering và path semantics không yêu cầu duyệt toàn bộ graph.

## Tối ưu hóa truy vấn an toàn và có kiểm soát tài nguyên

Một query DSL có thể nhận truy vấn từ người dùng hoặc hệ thống bên ngoài. Optimizer và executor cần hỗ trợ giới hạn tài nguyên.

### Query budget

Có thể đặt giới hạn:
- Maximum execution time.
- Maximum rows scanned.
- Maximum memory.
- Maximum result size.
- Maximum join count.
- Maximum recursion depth.
- Maximum remote calls.
- Maximum concurrent queries.

Budget có thể được kiểm tra ở planner và runtime. Cost estimate có thể từ chối query quá đắt trước khi chạy, nhưng runtime guard vẫn cần thiết vì estimates không hoàn hảo.

### Query complexity limits

Parser hoặc semantic analyzer có thể giới hạn độ sâu expression, số subquery, số join và kích thước literal để tránh plan explosion hoặc resource exhaustion.

### Cancellation

Client có thể hủy request. Executor cần truyền cancellation token xuống scan, join, sort, remote connector và background task. Một operator không kiểm tra cancellation có thể tiếp tục tiêu tốn CPU sau khi kết quả không còn cần thiết.

### Tenant isolation và authorization

Optimizer không được loại bỏ row-level filter hoặc tenant predicate bắt buộc. Plan cache cũng cần phân vùng theo security context nếu plan phụ thuộc quyền.

### Resource governance

Scheduler có thể giới hạn concurrency, memory reservation và queue theo tenant hoặc workload class. Một query lớn không nên chiếm hết tài nguyên làm các thao tác tương tác nhỏ bị chậm.

## Kiểm thử optimizer và tính tương đương

Optimizer thay đổi cấu trúc thực thi, vì vậy kiểm thử cần xác nhận kết quả không đổi và plan được cải thiện trong workload mục tiêu.

### Unit test cho từng rewrite

Mỗi rule nên có:
- Input logical plan.
- Expected transformed plan.
- Điều kiện áp dụng.
- Trường hợp không được áp dụng.
- Semantics liên quan như null, duplicate và ordering.

### Result equivalence test

Chạy query gốc và query đã tối ưu trên cùng dataset rồi so sánh kết quả theo semantics của DSL. Cần so sánh cả duplicate và ordering nếu chúng được bảo đảm.

### Differential testing

Có thể chạy cùng truy vấn trên interpreter/reference engine và optimized backend. Khác biệt kết quả giúp phát hiện rewrite không bảo toàn semantics hoặc backend mapping sai.

### Property-based testing

Sinh các biểu thức và dataset ngẫu nhiên, rồi kiểm tra:
- Rewrite giữ kết quả.
- Plan luôn có schema hợp lệ.
- Predicate pushdown không thay đổi null behavior.
- Join reorder giữ duplicate semantics.
- Constant folding tương đương evaluation runtime.
- Limit/order rewrite giữ kết quả theo contract.

### Performance regression test

Benchmark cần có workload đại diện:
- Table nhỏ và lớn.
- Predicate chọn lọc cao và thấp.
- Join key skew.
- Index có và không có.
- Cold cache và warm cache.
- Statistics chính xác và lỗi thời.
- Nhiều mức concurrency.
- Query có sort, aggregate, subquery.

Không chỉ đo thời gian. Cần theo dõi rows scanned, memory, spill, network và plan shape để hiểu vì sao thay đổi nhanh hoặc chậm hơn.

### Golden plan test

Một số hệ thống lưu plan mong đợi cho query quan trọng. Golden plan hữu ích để phát hiện thay đổi optimizer ngoài dự kiến, nhưng không nên yêu cầu plan vật lý giống hệt giữa mọi backend hoặc version. Test có thể kiểm tra thuộc tính như index được dùng, không có full scan không mong muốn hoặc join strategy nằm trong tập cho phép.

## Những lỗi thiết kế thường gặp

### Tối ưu ngay trên AST cú pháp

AST phản ánh grammar, không nhất thiết là mô hình tốt cho optimizer. Hãy resolve tên và kiểu rồi chuyển sang logical plan có operator rõ.

### Gộp logical và physical plan

Nếu logical node chứa trực tiếp index name hoặc hash join, optimizer khó tái sử dụng semantics cho backend khác. Nên tách ý nghĩa truy vấn khỏi cách thực thi.

### Dựa vào statistics không đáng tin

Statistics lỗi thời hoặc thiếu thông tin có thể khiến cost model chọn plan sai. Cần theo dõi estimated/actual cardinality và cơ chế refresh.

### Giả định index luôn nhanh hơn scan

Index có thể tốn random I/O và không hiệu quả khi predicate chọn phần lớn bảng. So sánh access path bằng cost model.

### Reorder expression có side effect

Đổi thứ tự predicate hoặc tính constant trước có thể làm thay đổi exception, volatile value hoặc side effect. Function metadata và semantics phải điều khiển rewrite.

### Bỏ qua null và duplicate

Nhiều rewrite đại số chỉ đúng dưới giả định set semantics hoặc hai-valued logic. Query DSL cần định nghĩa rõ bag/set semantics và three-valued logic.

### Pushdown không kiểm tra capability

Backend có thể dùng collation, timezone hoặc numeric behavior khác. Chỉ push operator khi semantics tương đương.

### Không có EXPLAIN hữu ích

Nếu plan không giải thích access path, estimates, join strategy và predicate pushdown, người dùng khó hiểu optimizer. Cần explain và actual runtime metrics.

### Cache plan thiếu dependency

Plan có thể lỗi thời khi schema, index, statistics, backend capability hoặc security context thay đổi. Cache key và invalidation cần bao phủ các dependency đó.

### Tối ưu quá mức

Search không gian plan quá rộng có thể làm planning time lớn hơn execution time. Cần giới hạn search, memoization, heuristic pruning và timeout cho optimizer.

### Không có resource guard

Cost estimate không chính xác tuyệt đối. Runtime vẫn cần timeout, memory limit, cancellation và scan budget.

## Quy trình xây dựng và cải thiện query optimizer

Một quy trình thực tế có thể đi theo các bước:

1. **Đặc tả semantics DSL:** xác định null, duplicate, ordering, error, function purity, type, timezone và security.
2. **Xây canonical logical plan:** biểu diễn scan, filter, project, join, aggregate, sort, limit và subquery.
3. **Gắn schema và metadata:** column identity, type, nullability, source location, constraints và lineage.
4. **Triển khai rule-based rewrites:** constant folding, predicate/projection pushdown, simplification và decorrelation an toàn.
5. **Xây physical operator catalog:** access path, join algorithm, aggregate, sort và exchange.
6. **Thu thập statistics:** row count, NDV, histogram, null fraction, width và skew.
7. **Xây cost model:** CPU, I/O, memory, network, spill và startup cost.
8. **Chọn physical plan:** sinh candidate, ước lượng cardinality và tìm plan trong giới hạn.
9. **Tích hợp backend capability:** pushdown và mapping chỉ khi semantics tương đương.
10. **Thêm EXPLAIN và EXPLAIN ANALYZE:** hiển thị estimated/actual, operator, cost và source mapping.
11. **Đo runtime feedback:** latency, rows, memory, spill, cache và network.
12. **Kiểm thử correctness:** rewrite tests, differential, property-based và edge cases.
13. **Benchmark workload:** đại diện dữ liệu nhỏ/lớn, skew, cache và concurrency.
14. **Theo dõi regression:** plan fingerprint, SLO, query budget và version.
15. **Cải thiện có bằng chứng:** sửa statistics, cost model, index hoặc operator dựa trên bottleneck đã đo.

Một optimizer nên có cơ chế tắt hoặc giới hạn một nhóm rewrite khi điều tra lỗi, nhưng việc đó cần được kiểm soát theo cấu hình và có thể tái lập. Mọi quyết định optimizer quan trọng nên có dấu vết trong explain plan.

## Kết luận

Tối ưu hóa truy vấn biến logical query plan thành cách thực thi hiệu quả hơn mà vẫn giữ nguyên semantics của DSL. Quá trình thường gồm chuẩn hóa truy vấn, áp dụng logical rewrite, ước lượng cardinality, lựa chọn access path và join strategy, rồi tạo physical plan phù hợp với backend.

Các kỹ thuật như predicate pushdown, projection pruning, constant folding, join reordering, index selection, partition pruning, aggregate pushdown, top-N và subquery decorrelation có thể giảm đáng kể lượng dữ liệu và công việc phải thực hiện. Hiệu quả của chúng phụ thuộc vào statistics, physical properties, capability của backend và chất lượng cost model.

Optimizer phải bảo toàn null logic, duplicate, ordering, function volatility, error semantics, precision, timezone và security policy. EXPLAIN, EXPLAIN ANALYZE, runtime metrics, query budget và kiểm thử tương đương giúp người dùng hiểu kế hoạch và giúp nhóm phát hiện regression. Khi logical semantics được đặc tả rõ, physical planner được tách biệt và quyết định tối ưu dựa trên dữ liệu thực tế, DSL truy vấn có thể cung cấp hiệu năng tốt mà vẫn giữ trải nghiệm khai báo dễ hiểu và ổn định.

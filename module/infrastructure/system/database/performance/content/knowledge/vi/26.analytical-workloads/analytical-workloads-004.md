# Tổng hợp trên dữ liệu lớn và chi phí xáo trộn dữ liệu

## Vì sao phép tổng hợp trở nên đắt khi dữ liệu tăng?

Các truy vấn phân tích thường gom nhiều hàng thành một tập kết quả nhỏ hơn: tổng doanh thu theo tháng, số đơn theo trạng thái, số người dùng theo khu vực hoặc số sự kiện theo ngày. Trong SQL, GROUP BY cùng COUNT, SUM, AVG, MIN, MAX và các hàm tổng hợp có điều kiện là thành phần cốt lõi của workload này.

Kết quả có thể chỉ gồm vài trăm nhóm, nhưng để tạo ra chúng, hệ quản trị có thể phải đọc hàng triệu hoặc hàng tỷ hàng. Nó cần xác định hàng nào thuộc cùng nhóm, duy trì trạng thái tổng hợp cho từng nhóm, kết hợp kết quả từ các worker và có thể sắp xếp hoặc trao đổi dữ liệu giữa các vùng xử lý. Chi phí phụ thuộc số hàng đầu vào, số nhóm khác nhau, độ rộng khóa nhóm, kích thước trạng thái tổng hợp, phân bố dữ liệu và bộ nhớ có sẵn.

Một truy vấn GROUP BY chậm có thể bị chi phối bởi nhiều công việc:
- Đọc dữ liệu từ bảng hoặc chỉ mục.
- Lọc hàng trước khi tổng hợp.
- Phân nhóm bằng hash hoặc sắp xếp theo khóa nhóm.
- Trao đổi dữ liệu giữa worker để đưa các hàng cùng nhóm về cùng nơi xử lý.
- Duy trì trạng thái SUM, COUNT, AVG hoặc trạng thái của hàm phức tạp.
- Ghi dữ liệu trung gian ra vùng lưu trữ tạm khi bộ nhớ không đủ.
- Sắp xếp kết quả cuối cùng theo ORDER BY.
- Truyền kết quả qua mạng đến ứng dụng hoặc công cụ BI.

Trong tối ưu hiệu năng cơ sở dữ liệu, cần phân biệt chi phí đọc đầu vào, phân nhóm, xáo trộn, bộ nhớ và trả kết quả. Tăng RAM hoặc thêm chỉ mục chỉ giúp khi nó tác động đúng nút thắt. Một truy vấn có thể đọc dữ liệu nhanh nhưng vẫn chậm vì hash aggregate spill; truy vấn khác có thể dùng Stream Aggregate hiệu quả nhưng phải sort hàng triệu bản ghi trước đó.

Bài học này trình bày cách tổng hợp trên dữ liệu lớn, phân biệt Hash Aggregate và Sort/Stream Aggregate, hiểu chi phí shuffle trong hệ thống song song hoặc phân tán, nhận diện memory spill và data skew, rồi kiểm chứng thay đổi bằng execution plan và số liệu tải.

## Mô hình chi phí của một truy vấn tổng hợp

### Số hàng đầu vào và số nhóm đầu ra

Giả sử bảng sales có 500 triệu hàng:

~~~sql
SELECT
    region_id,
    DATE_TRUNC('month', sold_at) AS sales_month,
    SUM(net_amount) AS revenue,
    COUNT(*) AS order_count
FROM sales
WHERE sold_at >= TIMESTAMP '2026-01-01'
  AND sold_at <  TIMESTAMP '2027-01-01'
GROUP BY
    region_id,
    DATE_TRUNC('month', sold_at);
~~~

Nếu điều kiện thời gian giữ lại 80 triệu hàng và chỉ có 20 vùng nhân với 12 tháng, kết quả tối đa khoảng 240 nhóm. Hệ quản trị vẫn phải đọc và xử lý 80 triệu hàng để tính các tổng. Kích thước kết quả nhỏ không đồng nghĩa công việc nhỏ.

Hai đại lượng cần theo dõi:
- **N (input rows):** số hàng đi vào phép tổng hợp.
- **G (number of groups):** số nhóm khác nhau được tạo ra.

Tỷ lệ N/G cho biết trung bình có bao nhiêu hàng đóng góp vào một nhóm, nhưng không thể hiện phân bố lệch. Nếu một nhóm chứa 70% hàng và các nhóm còn lại rất nhỏ, trung bình có thể che giấu hot group.

Khi G nhỏ so với N, partial aggregation thường có cơ hội giảm lượng dữ liệu cần chuyển tiếp. Khi G gần N, mỗi hàng gần như tạo một nhóm riêng; trạng thái hash có thể lớn và lợi ích nén dữ liệu bằng aggregation thấp.

### Độ rộng khóa nhóm và trạng thái tổng hợp

Số nhóm không phải yếu tố duy nhất quyết định bộ nhớ. Một nhóm có thể cần giữ:
- Các giá trị khóa nhóm, chẳng hạn region_id, customer_id hoặc nhiều biểu thức.
- Bộ đếm và tổng cho mỗi hàm aggregate.
- Trạng thái của DISTINCT hoặc ordered-set aggregate.
- Con trỏ, metadata và overhead của cấu trúc hash.
- Dữ liệu trung gian để xử lý nhiều phase hoặc kết hợp partial state.

GROUP BY trên một số nguyên hẹp có thể dùng ít bộ nhớ hơn GROUP BY trên nhiều cột chuỗi dài hoặc biểu thức phức tạp. COUNT(DISTINCT user_id) có thể cần trạng thái lớn hơn COUNT(*) vì engine phải xác định các giá trị duy nhất trong từng nhóm.

Khi ước lượng memory, cần xét số nhóm, độ rộng key, số aggregate, kiểu aggregate và overhead nội bộ của engine. Không thể lấy số byte của hàng kết quả nhân với số nhóm để suy ra chính xác bộ nhớ cần thiết.

### Lọc trước khi tổng hợp

Một nguyên tắc quan trọng là giảm số hàng đi vào aggregate nếu điều kiện nghiệp vụ cho phép:

~~~sql
SELECT
    customer_id,
    SUM(amount) AS total_amount
FROM payments
WHERE payment_status = 'SETTLED'
  AND paid_at >= :from_time
  AND paid_at < :to_time
GROUP BY customer_id;
~~~

Nếu chỉ cần các khoản đã thanh toán trong khoảng thời gian, hãy áp dụng điều kiện đó trước GROUP BY. Tránh tổng hợp toàn bộ lịch sử rồi lọc kết quả nếu phép lọc có thể đẩy xuống scan một cách tương đương.

Optimizer thường có thể push predicate qua các toán tử phù hợp, nhưng biểu thức, hàm, join hoặc subquery có thể hạn chế khả năng này. Hãy xem actual plan để xác nhận số hàng thực tế đi vào aggregate thay vì chỉ nhìn SQL text.

Không đẩy điều kiện xuống nếu nó làm thay đổi ngữ nghĩa. Ví dụ, lọc hàng con trước LEFT JOIN có thể khác với lọc sau JOIN; lọc HAVING sau aggregate không phải lúc nào cũng tương đương WHERE trên hàng nguồn.

## Các loại phép tổng hợp trong execution plan

### Hash Aggregate

Hash Aggregate tạo bảng băm, dùng khóa nhóm để tìm hoặc tạo trạng thái cho từng nhóm. Khi một hàng đầu vào đến, engine tính khóa nhóm, tìm bucket tương ứng rồi cập nhật trạng thái aggregate.

~~~text
for each input row:
    key = group_key(row)
    state = hash_table.find_or_create(key)
    state.update(row)
emit all group states
~~~

Ưu điểm:
- Không cần sắp xếp toàn bộ đầu vào theo khóa nhóm trước.
- Có thể xử lý dữ liệu theo luồng khi hash table còn vừa bộ nhớ.
- Phù hợp khi số nhóm và trạng thái aggregate nằm trong ngân sách bộ nhớ.
- Có thể chạy song song bằng hash table riêng hoặc cơ chế chia partition nội bộ.

Chi phí và rủi ro:
- Bộ nhớ tăng theo số nhóm và kích thước trạng thái.
- Hash collision và phân bố hash không tốt có thể tăng công việc.
- Nếu hash table vượt bộ nhớ, engine có thể partition/spill dữ liệu trung gian ra đĩa.
- DISTINCT hoặc trạng thái phức tạp làm tăng memory footprint.
- Khi nhiều worker cùng giữ hash table, tổng bộ nhớ có thể tăng đáng kể.

Hash Aggregate thường có lợi khi không cần thứ tự đầu ra và số nhóm có thể được giữ trong bộ nhớ. Tuy nhiên, hash aggregate trên hàng trăm triệu nhóm có thể đắt hơn phương án sắp xếp hoặc chiến lược khác tùy engine.

### Sort Aggregate và Stream Aggregate

Sort Aggregate thường cần đầu vào được sắp xếp theo khóa nhóm. Khi các hàng cùng khóa nằm cạnh nhau, engine giữ trạng thái của nhóm hiện tại, xuất kết quả khi khóa thay đổi rồi chuyển sang nhóm tiếp theo.

Stream Aggregate trong SQL Server và một số tên toán tử tương đương dựa vào thứ tự đầu vào. Thứ tự đó có thể đến từ:
- Chỉ mục đã được sắp xếp theo các cột nhóm.
- Một bước Sort trước aggregate.
- Một toán tử trước đó bảo toàn thứ tự phù hợp.

Ưu điểm:
- Có thể dùng bộ nhớ nhỏ nếu đầu vào đã có thứ tự.
- Khi khóa nhóm đến liên tiếp, chỉ cần trạng thái của nhóm hiện tại.
- Có thể tận dụng thứ tự tự nhiên của index hoặc partition.
- Có thể xuất kết quả sớm theo nhóm trong một số pipeline.

Chi phí:
- Nếu chưa có thứ tự, Sort có thể phải xử lý và lưu trung gian rất nhiều hàng.
- Sort lớn có thể dùng memory grant lớn và spill ra temp storage.
- Thứ tự index có thể không phù hợp với toàn bộ filter, join và group key.
- Index chỉ để hỗ trợ aggregate có thể tăng chi phí ghi và dung lượng.

Không nên kết luận Stream Aggregate luôn tốt hơn Hash Aggregate. Nếu phải sort hàng trăm triệu hàng trước khi tổng hợp, chi phí sort có thể chi phối. Nếu index cung cấp đúng thứ tự và truy vấn đọc phần lớn dữ liệu theo thứ tự đó, Stream Aggregate có thể hiệu quả.

### So sánh hai chiến lược

| Đặc điểm | Hash Aggregate | Sort/Stream Aggregate |
|---|---|---|
| Yêu cầu đầu vào | Không cần thứ tự theo group key | Cần đầu vào có thứ tự |
| Cấu trúc chính | Hash table và trạng thái nhóm | Trạng thái nhóm hiện tại trên luồng đã sắp xếp |
| Bộ nhớ | Thường tăng theo số nhóm | Có thể thấp nếu đã có thứ tự |
| Chi phí sắp xếp | Không bắt buộc | Có thể rất lớn nếu phải Sort |
| Nguy cơ spill | Hash partition/state spill | Sort spill |
| Tính song song | Có thể hash partition hoặc partial aggregate | Có thể phân đoạn theo range/partition và merge |
| Trường hợp phù hợp | Nhiều hàng, số nhóm vừa phải, không cần thứ tự | Đầu vào đã có thứ tự hoặc index hỗ trợ tốt |

Tên toán tử, thuật toán nội bộ và điều kiện chọn plan khác nhau theo hệ quản trị. Hãy đọc tài liệu engine và actual plan thay vì giả định mọi sản phẩm triển khai giống nhau.

## Chi phí Sort và xáo trộn dữ liệu

### Sort là công việc sắp xếp cục bộ

Sort sắp xếp các hàng theo một hoặc nhiều khóa. Nó có thể xuất hiện trước Stream Aggregate, ORDER BY, window function, merge join hoặc một số bước xử lý khác.

Với tập dữ liệu nhỏ, sort trong bộ nhớ có thể rẻ. Với tập dữ liệu lớn hơn memory grant, engine có thể dùng external sort: chia dữ liệu thành các run đã sắp xếp trong bộ nhớ, ghi run ra temp storage rồi merge nhiều run để tạo thứ tự cuối cùng.

External sort làm tăng:
- CPU cho so sánh khóa và merge.
- Bộ nhớ cho các buffer và run.
- I/O tạm để ghi/đọc dữ liệu trung gian.
- Thời gian chờ và áp lực lên temp tablespace/tempdb.
- Cạnh tranh I/O với workload khác.

Nếu dữ liệu cần được sort theo nhiều bước hoặc nhiều truy vấn đồng thời cùng spill, temp storage có thể trở thành nút thắt chung.

### Shuffle trong xử lý song song hoặc phân tán

Trong hệ thống MPP hoặc distributed query engine, dữ liệu có thể được đọc ở nhiều worker hoặc node. Để tổng hợp theo một khóa, các hàng có cùng khóa thường phải được đưa về cùng worker hoặc cùng partition xử lý.

Ví dụ, dữ liệu được lưu phân tán theo event_id nhưng truy vấn GROUP BY customer_id. Một customer có thể xuất hiện trên nhiều node. Để tính tổng chính xác, hệ thống cần trao đổi dữ liệu sao cho các hàng cùng customer_id được gom lại.

Một chiến lược phổ biến là hash shuffle:

~~~text
destination_worker = HASH(group_key) MOD worker_count
~~~

Mỗi worker gửi hàng hoặc partial state đến worker đích theo hash của group key. Worker nhận dữ liệu rồi tiếp tục aggregate.

Shuffle có thể tiêu tốn:
- CPU để hash key và serialize dữ liệu.
- Băng thông mạng giữa node.
- Buffer và bộ nhớ ở sender/receiver.
- I/O tạm nếu dữ liệu trung gian bị spill.
- Thời gian chờ worker chậm nhất hoặc partition nặng nhất.
- Tài nguyên điều phối và quản lý exchange.

Shuffle khác với sort. Sort sắp thứ tự dữ liệu trong một phạm vi xử lý; shuffle di chuyển hoặc tái phân phối dữ liệu giữa các worker/partition. Một truy vấn phân tán có thể vừa shuffle vừa sort.

### Local aggregation và global aggregation

Để giảm lượng dữ liệu truyền, engine có thể thực hiện partial/local aggregation tại nơi dữ liệu được đọc trước khi shuffle. Thay vì gửi từng hàng, worker gửi trạng thái tổng hợp cục bộ cho từng nhóm.

Ví dụ, dữ liệu có 10 triệu hàng nhưng chỉ có 100 nhóm. Nếu mỗi node có thể tổng hợp 1 triệu hàng thành 100 partial states, lượng dữ liệu gửi qua mạng có thể giảm mạnh.

~~~text
Phase 1 - Local/Partial Aggregate:
  Worker A: rows -> partial states
  Worker B: rows -> partial states
  Worker C: rows -> partial states

Exchange:
  Shuffle partial states by group key

Phase 2 - Final Aggregate:
  Receiver workers merge partial states
  Emit final result
~~~

Đây là chiến lược phổ biến trong MPP và distributed engines. Một số hệ quản trị một node cũng dùng partial/final aggregate khi parallel query. Cần xem plan có các toán tử partial/final, repartition exchange hoặc gather/merge tương ứng hay không.

Partial aggregation hiệu quả khi:
- Số nhóm cục bộ nhỏ hơn nhiều số hàng đầu vào.
- Aggregate có thể kết hợp trạng thái một cách chính xác.
- Chi phí hash local thấp hơn lượng dữ liệu tiết kiệm khi truyền.
- Phân bố nhóm giữa worker đủ phù hợp.

Nếu gần như mỗi hàng có một group key duy nhất, local aggregation không giảm nhiều dữ liệu. Với một số aggregate DISTINCT hoặc ordered aggregate, cách partial combine có thể phức tạp hoặc bị giới hạn.

### Shuffle theo hash và theo range

Hash shuffle đưa cùng một group key đến cùng đích dựa trên hàm hash. Nó thường giúp phân phối nhiều khóa khác nhau tương đối đều, nhưng một khóa rất nóng vẫn chỉ đi đến một đích nếu không có chiến lược đặc biệt.

Range partitioning chia dữ liệu theo khoảng khóa. Nó có thể giữ thứ tự hoặc hỗ trợ range query, nhưng nếu giá trị tập trung trong một khoảng, một partition có thể lớn hơn nhiều partition khác. Boundary chọn không phù hợp gây skew.

Các engine có thể dùng broadcast, repartition, coalesce hoặc exchange khác tùy join/aggregate. Đối với aggregation, cần xác minh dữ liệu cùng nhóm cuối cùng có được kết hợp đúng và exchange có làm tăng network bytes hoặc tạo partition lệch không.

## Data skew và nhóm nóng

### Vì sao hash không tự giải quyết mọi skew?

Hash partitioning thường phân phối nhiều giá trị khóa khác nhau qua các worker. Nhưng nếu một giá trị chiếm 40% số hàng, tất cả hàng của giá trị đó có thể được hash về cùng worker. Worker này phải xử lý nhiều dữ liệu hơn, dùng nhiều bộ nhớ hơn và hoàn tất muộn hơn.

Ví dụ, GROUP BY customer_id trong hệ thống bán lẻ. Một khách hàng doanh nghiệp lớn có hàng chục triệu giao dịch, trong khi phần lớn khách hàng chỉ có vài trăm. Hash theo customer_id không chia một khách hàng lớn thành nhiều worker vì tất cả hàng cùng customer_id phải được tổng hợp chính xác.

Hậu quả:
- Một worker nhận nhiều bytes hoặc rows hơn.
- Hash table hoặc aggregate state của worker nóng lớn hơn.
- Worker nóng spill trong khi các worker khác đã hoàn tất.
- Thời gian truy vấn bị chi phối bởi worker chậm nhất.
- Network exchange và memory pressure mất cân bằng.

### Nhận diện skew

Không chỉ nhìn tổng thời gian query. Hãy xem:
- Rows/bytes gửi và nhận theo worker.
- Số partition và kích thước partition.
- Thời gian xử lý từng worker.
- Memory used, spill bytes và temp I/O theo worker.
- Số nhóm và số hàng mỗi nhóm.
- Top group key theo số hàng.
- Số hàng bị lọc trước/sau exchange.

Một chỉ số đơn giản để so sánh phân bố:

~~~text
skew_ratio = max(worker_input_rows) / median(worker_input_rows)
~~~

Có thể dùng bytes hoặc thời gian thay cho rows. Đây là chỉ số chẩn đoán, không có ngưỡng phổ quát cho mọi engine. Một tỷ lệ cao cần được xem cùng tổng lượng dữ liệu và độ lệch thời gian hoàn thành.

### Xử lý hot group

Một số chiến lược có thể áp dụng:
1. **Salting key:** thêm bucket phụ vào khóa ở phase đầu để chia một nhóm nóng thành nhiều partial group; sau đó loại salt và tổng hợp lần cuối theo khóa gốc.
2. **Two-stage aggregation:** tính tổng cục bộ theo group key và shard/bucket trước, sau đó merge partial result.
3. **Tách nhóm ngoại lệ:** xử lý riêng một vài key quá lớn nếu nghiệp vụ và kiến trúc cho phép.
4. **Pre-aggregate:** duy trì summary table hoặc materialized view để tránh quét dữ liệu chi tiết cho truy vấn lặp lại.
5. **Thay đổi phân phối dữ liệu:** chọn partition/shard key phù hợp với workload tổng thể, không chỉ một truy vấn.
6. **Giới hạn hoặc phân đoạn truy vấn:** chia theo khoảng thời gian hoặc nhóm khóa rồi hợp nhất kết quả nếu phép toán cho phép.

Salting không phải lúc nào cũng phù hợp. Nếu truy vấn cần DISTINCT hoặc tính toán phụ thuộc toàn bộ tập giá trị trong group, việc chia nhóm cần thuật toán merge chính xác. Với AVG, phải giữ SUM và COUNT rồi tính lại AVG ở phase cuối; không lấy trung bình của các trung bình nếu số hàng mỗi partial group khác nhau.

## Bộ nhớ, memory grant và spill

### Hash aggregate cần bộ nhớ cho từng group

Hash aggregate cần lưu khóa và trạng thái cho mỗi nhóm đang tồn tại. Khi số nhóm thực tế lớn hơn ước lượng hoặc key rộng hơn dự kiến, hash table có thể vượt ngân sách.

Optimizer thường ước lượng số nhóm dựa trên thống kê. Nếu thống kê cũ hoặc không phản ánh skew, engine có thể cấp memory quá ít hoặc quá nhiều. Memory grant quá thấp gây spill; quá cao làm giảm số truy vấn có thể chạy đồng thời.

### Sort cũng cần bộ nhớ

Sort cần buffer cho các hàng và cấu trúc sắp xếp. Nếu memory grant không đủ, engine có thể ghi các run tạm ra disk rồi merge. Một truy vấn có thể spill ở Sort trước khi vào Stream Aggregate; khi đó nhìn riêng operator Aggregate sẽ bỏ lỡ nguyên nhân.

### Spill là gì?

Spill xảy ra khi một toán tử cần nhiều dữ liệu trung gian hơn bộ nhớ được cấp và phải ghi một phần ra vùng lưu trữ tạm. Với Hash Aggregate, engine có thể chia hash table thành các partition tạm và xử lý từng phần. Với Sort, engine có thể tạo các sorted run rồi merge.

Dấu hiệu:
- Actual plan báo spill, temp read/write hoặc số pass.
- Tempdb/temp tablespace I/O tăng.
- Query elapsed cao hơn nhiều so với CPU time.
- Temp I/O tăng cùng số nhóm hoặc kích thước dữ liệu.
- Nhiều query đồng thời tranh chấp temp storage.
- Worker có phân bố lệch spill nặng hơn các worker khác.

Spill không luôn là lỗi. Một truy vấn phân tích lớn có thể cần spill để hoàn thành với giới hạn bộ nhớ có kiểm soát. Mục tiêu là đánh giá spill có gây vi phạm latency/throughput hay làm ảnh hưởng workload khác không.

### Phân biệt thiếu bộ nhớ với ước lượng sai

Nếu số nhóm thực tế lớn hơn nhiều estimated groups, cần xem thống kê và cardinality estimation. Nếu estimate gần đúng nhưng memory vẫn không đủ, có thể workload đang chạy đồng thời quá nhiều hoặc memory grant bị giới hạn.

Hãy đối chiếu:
- Estimated rows và actual rows đầu vào aggregate.
- Estimated groups và actual groups.
- Memory grant requested/granted/used nếu engine cung cấp.
- Hash/sort spill bytes và số pass.
- Concurrent queries và tổng memory pressure.
- Cấu hình giới hạn bộ nhớ của engine, workload group hoặc container.

Không tăng memory grant toàn cục chỉ vì một truy vấn spill. Cần kiểm tra liệu nó có làm truy vấn khác thiếu bộ nhớ hoặc giảm concurrency hay không.

### Cách giảm áp lực bộ nhớ

- Giảm hàng đầu vào bằng predicate pushdown đúng ngữ nghĩa.
- Giảm số cột được đọc và độ rộng hàng trung gian.
- Loại bỏ join không cần thiết trước aggregate.
- Tạo index hoặc columnstore phù hợp để giảm I/O nếu có lợi.
- Dùng partial aggregation để giảm dữ liệu chuyển tiếp.
- Chia truy vấn theo khoảng hoặc partition nếu có thể hợp nhất kết quả chính xác.
- Cập nhật thống kê để optimizer ước lượng số nhóm tốt hơn.
- Giới hạn concurrency của workload phân tích khi memory là tài nguyên chung.
- Dùng summary table/materialized view cho aggregate lặp lại và có yêu cầu freshness phù hợp.

## Tối ưu SQL cho tổng hợp dữ liệu lớn

### Chỉ đọc cột cần thiết

Tránh SELECT * trong truy vấn phân tích. Mỗi cột bổ sung làm tăng bytes đọc, buffer pressure, network transfer và độ rộng dữ liệu trung gian. Với columnstore, projection pushdown giúp đọc ít cột hơn nếu engine hỗ trợ.

### Lọc sớm và dùng khoảng nửa mở

Ví dụ lọc theo tháng:

~~~sql
WHERE sold_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND sold_at <  TIMESTAMP '2026-12-01 00:00:00'
~~~

Dạng khoảng nửa mở thường tránh phải áp dụng hàm lên cột thời gian và dễ dùng index/range partition hơn so với:

~~~sql
WHERE DATE(sold_at) = DATE '2026-11-01'
~~~

Cú pháp literal và hàm ngày khác nhau theo engine. Nếu cần chuyển timezone, xác định rõ timezone nghiệp vụ và chuyển mốc biên trước khi bind tham số.

### Tránh nhân bản hàng trước aggregate

JOIN một bảng cha với bảng con một-nhiều có thể nhân số hàng trước khi tổng hợp. Ví dụ:

~~~sql
SELECT
    c.customer_id,
    SUM(o.total_amount) AS revenue
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id
JOIN order_items i
  ON i.order_id = o.order_id
GROUP BY c.customer_id;
~~~

Nếu một đơn có nhiều order_items, total_amount của đơn sẽ bị cộng lặp theo số dòng hàng. Đây là lỗi tính đúng đắn và cũng làm aggregate xử lý nhiều hàng hơn cần thiết.

Nếu chỉ cần kiểm tra đơn có item, dùng EXISTS. Nếu cần dữ liệu con, tổng hợp bảng con trước hoặc tính tổng trên đúng grain:

~~~sql
SELECT
    customer_id,
    SUM(total_amount) AS revenue
FROM orders
WHERE created_at >= :from_time
  AND created_at < :to_time
GROUP BY customer_id;
~~~

Nếu cần kết hợp số lượng item, hãy tổng hợp order_items theo order_id trước rồi JOIN với orders, bảo đảm mỗi order chỉ xuất hiện một hàng trong phép cộng doanh thu.

### WHERE và HAVING

WHERE lọc hàng nguồn trước khi aggregate. HAVING lọc nhóm sau khi đã tổng hợp:

~~~sql
SELECT customer_id, SUM(amount) AS total_amount
FROM payments
WHERE paid_at >= :from_time
  AND paid_at < :to_time
GROUP BY customer_id
HAVING SUM(amount) >= :minimum_total;
~~~

Không thay HAVING bằng WHERE nếu điều kiện phụ thuộc giá trị tổng hợp. Ngược lại, điều kiện trên cột hàng nguồn nên đặt ở WHERE nếu tương đương về ngữ nghĩa để giảm đầu vào.

### DISTINCT aggregate

COUNT(DISTINCT user_id) cần loại trùng trong từng group. Chi phí phụ thuộc số giá trị khác nhau, độ rộng key, phân bố và chiến lược engine. Nếu truy vấn có nhiều COUNT(DISTINCT ...) trên các cột khác nhau, trạng thái trung gian có thể rất lớn.

Không thay COUNT(DISTINCT) bằng COUNT(*) hoặc phép tổng hợp gần đúng nếu nghiệp vụ yêu cầu kết quả chính xác. Với workload phân tích chấp nhận sai số, một số engine có approximate distinct như HyperLogLog hoặc hàm tương tự; phải xác định rõ sai số và semantics trước khi dùng.

### AVG và partial aggregation

AVG có thể được kết hợp từ SUM và COUNT:

~~~text
partial_state = (sum_value, count_value)
final_avg = SUM(partial_sum) / SUM(partial_count)
~~~

Không lấy AVG(partial_avg) nếu mỗi partition có số hàng khác nhau. Ví dụ một worker xử lý 10 hàng có trung bình 100 và worker khác xử lý 1.000 hàng có trung bình 10; trung bình của hai giá trị trung bình là 55, không phải trung bình đúng của toàn bộ 1.010 hàng.

Các aggregate khác cũng có trạng thái merge riêng. SUM và COUNT dễ kết hợp; MIN/MAX có thể merge bằng min/max; percentile, median và DISTINCT cần thuật toán hoặc trạng thái phức tạp hơn.

## Chỉ mục, partitioning và columnstore cho workload tổng hợp

### B-tree index

B-tree có thể hỗ trợ lọc và cung cấp thứ tự. Nếu truy vấn lọc theo tenant_id và khoảng thời gian rồi GROUP BY category_id, một index phù hợp có thể giảm số hàng đọc hoặc hỗ trợ thứ tự tùy thiết kế.

Tuy nhiên, index không tự làm phép tổng hợp miễn phí. Nếu truy vấn đọc phần lớn bảng, quét tuần tự hoặc columnstore có thể rẻ hơn nhiều lần lookup ngẫu nhiên. Index covering có thể giảm lookup nhưng làm index rộng hơn và tăng chi phí ghi.

Thiết kế index theo workload phổ biến, sau đó kiểm tra actual reads và plan. Không tạo index chỉ vì một cột xuất hiện trong GROUP BY.

### Partition pruning

Nếu bảng lớn được partition theo thời gian và truy vấn luôn lọc khoảng thời gian, partition pruning có thể bỏ qua các partition không liên quan trước khi aggregate.

~~~sql
SELECT
    tenant_id,
    COUNT(*) AS event_count
FROM events
WHERE event_time >= :from_time
  AND event_time < :to_time
GROUP BY tenant_id;
~~~

Nếu điều kiện tương thích với partition key, engine có thể chỉ đọc các partition nằm trong khoảng. Nếu truy vấn không lọc partition key, có thể phải quét nhiều partition. Kiểm tra số partition thực sự được truy cập trong plan.

### Partition-wise aggregation

Khi khóa nhóm và cách phân vùng tương thích, một số engine có thể tổng hợp độc lập trong từng partition rồi kết hợp kết quả. Điều này giảm dữ liệu cần di chuyển hoặc tập trung tại một bước cuối.

Ví dụ, bảng được partition theo tenant_id và truy vấn GROUP BY tenant_id có thể cho phép tổng hợp cục bộ theo partition. Nhưng nếu GROUP BY product_id và mỗi product xuất hiện trong nhiều partition, kết quả cần được merge giữa các partition.

Khả năng partition-wise aggregate phụ thuộc engine, partition key, join và plan. Không giả định cứ partitioned table là truy vấn tự động aggregate theo partition.

### Columnstore và lưu trữ hướng cột

Workload phân tích thường đọc một số cột từ rất nhiều hàng. Columnstore lưu hoặc mã hóa dữ liệu theo cột, có thể giảm I/O khi chỉ truy cập một phần cột và tận dụng batch/vectorized processing.

Ưu điểm có thể gồm:
- Đọc ít byte hơn khi projection hẹp.
- Nén dữ liệu tốt với các cột có phân bố phù hợp.
- Vectorized aggregate xử lý nhiều giá trị trong một batch.
- Một số engine hỗ trợ aggregate pushdown hoặc segment elimination.

Đánh đổi:
- Chi phí ghi/update có thể cao hơn hoặc cần delta store/row group maintenance.
- Truy vấn point lookup nhỏ có thể không phù hợp.
- Segment/rowgroup elimination phụ thuộc thứ tự và min/max metadata.
- Các khả năng và thuật ngữ khác nhau theo hệ quản trị.

Hãy so sánh rowstore và columnstore bằng workload đọc/ghi thực tế, không chỉ benchmark scan.

## Parallelism và mức độ mở rộng

### Parallel aggregate

Engine có thể chia scan thành nhiều phần, mỗi worker thực hiện partial aggregate rồi hợp nhất trạng thái. Khi dữ liệu lớn và phân bố tương đối đều, parallelism có thể tăng throughput.

Nhưng tăng worker không đảm bảo giảm latency tuyến tính. Overhead có thể gồm:
- Khởi tạo worker và điều phối.
- Trao đổi dữ liệu và merge trạng thái.
- Nhiều hash table hoặc sort buffer cùng lúc.
- Cạnh tranh CPU, memory bandwidth và I/O.
- Skew khiến một worker trở thành điểm chậm.
- Nhiều truy vấn phân tích cùng chạy gây oversubscription.

Một truy vấn dùng 16 worker có thể lấy nhiều CPU và memory hơn, làm các truy vấn OLTP hoặc truy vấn phân tích khác chậm đi. Cần xem workload concurrency, resource governance và mức parallelism tối đa.

### Gather và merge

Sau partial aggregation, kết quả có thể được gather về một worker để final aggregate. Nếu số partial groups lớn, bước gather vẫn có thể là nút thắt. Nếu cần thứ tự cuối cùng, hệ thống có thể cần merge hoặc sort thêm.

Kiểm tra:
- Số hàng trước và sau exchange.
- Bytes truyền giữa worker.
- Thời gian từng worker.
- Số partial groups.
- CPU và memory của final aggregate.
- Sort cuối cùng và spill nếu có.

### Mức mở rộng có giới hạn

Nếu tăng worker từ 4 lên 8 nhưng thời gian chỉ giảm rất ít, có thể truy vấn bị giới hạn bởi I/O, network, skew, final aggregate hoặc memory. Amdahl's law nhắc rằng phần công việc tuần tự và overhead giới hạn mức tăng tốc tổng thể.

Đừng tăng parallelism trước khi hiểu chi phí. Giảm dữ liệu đầu vào hoặc giảm shuffle thường hiệu quả hơn việc tăng worker khi mạng hoặc final aggregation đã bão hòa.

## Materialized view và pre-aggregation

### Khi nào nên tổng hợp trước?

Nếu cùng một phép tổng hợp được chạy lặp lại trên dữ liệu chi tiết lớn, có thể lưu kết quả trung gian hoặc summary table. Ví dụ, thay vì mỗi dashboard quét hàng tỷ event để tính tổng theo ngày và tenant, hệ thống có thể duy trì bảng daily_tenant_metrics.

Truy vấn đọc summary nhỏ hơn nhiều, nhưng cần thiết kế:
- Tần suất refresh hoặc cập nhật incremental.
- Độ trễ dữ liệu chấp nhận được.
- Cách xử lý event đến muộn.
- Cách cập nhật khi sửa/xóa dữ liệu nguồn.
- Khả năng rebuild và đối soát.
- Tính nhất quán giữa summary và bảng gốc.

Materialized view là một dạng lưu kết quả truy vấn được hệ quản trị quản lý theo khả năng riêng. Summary table do ứng dụng duy trì đòi hỏi logic cập nhật và phục hồi riêng. Không đồng nhất hai cơ chế.

### Incremental aggregation

Thay vì tính lại toàn bộ summary, hệ thống có thể cập nhật phần chênh lệch khi dữ liệu mới đến. Với SUM và COUNT, một insert có thể cộng thêm amount và tăng count. Với update/delete, cần biết giá trị cũ để điều chỉnh chính xác.

Một số aggregate khó duy trì incremental hơn:
- MIN/MAX cần biết giá trị kế tiếp khi giá trị cực trị bị xóa.
- COUNT(DISTINCT) cần theo dõi số lần xuất hiện của từng giá trị.
- Median/percentile cần cấu trúc dữ liệu hoặc thuật toán riêng.
- Các phép join nhiều bảng có thể cần xử lý thay đổi ở nhiều phía.

Cần có cơ chế đối soát summary với truy vấn tính từ dữ liệu gốc để phát hiện drift. Nếu summary sai, dashboard có thể nhanh nhưng kết quả không đáng tin.

## Đọc execution plan và đo chi phí tổng hợp

### Các câu hỏi khi đọc plan

Khi truy vấn GROUP BY chậm, hãy đi theo luồng dữ liệu:
1. Bao nhiêu hàng được đọc từ scan?
2. Predicate được áp dụng ở đâu và giảm còn bao nhiêu hàng?
3. Có join nào làm nhân bản hàng trước aggregate không?
4. Engine dùng Hash Aggregate hay Sort/Stream Aggregate?
5. Có Sort trước aggregate không? Sort có spill không?
6. Số nhóm ước lượng và thực tế là bao nhiêu?
7. Có partial/local aggregate trước exchange không?
8. Exchange/shuffle truyền bao nhiêu hàng và byte?
9. Worker có phân bố lệch về rows, bytes, memory hoặc duration không?
10. Final aggregate hoặc ORDER BY có trở thành nút thắt không?

### Chỉ số cần ghi nhận

| Nhóm | Chỉ số | Mục đích |
|---|---|---|
| Input | Rows read, rows filtered, bytes read | Đánh giá lượng dữ liệu đầu vào |
| Aggregate | Estimated/actual groups, aggregate rows | Phát hiện sai lệch cardinality |
| CPU | CPU time, operator time | Đo chi phí hash, sort và tính toán |
| Memory | Memory grant, peak memory, hash/sort memory | Kiểm tra ngân sách bộ nhớ |
| Spill | Temp bytes, spill count, passes | Đo chi phí tràn ra lưu trữ tạm |
| Exchange | Rows/bytes sent, network wait | Đo shuffle và truyền dữ liệu |
| Parallelism | Worker count, worker duration | Phát hiện skew và oversubscription |
| I/O | Logical/physical reads, temp I/O latency | Xác định nút thắt lưu trữ |
| End-to-end | Elapsed, p95/p99, throughput | Đo ảnh hưởng đến workload |

Tên counter và cách hiển thị khác nhau giữa PostgreSQL, SQL Server, MySQL và các distributed engines. Hãy dùng actual execution plan, query statistics, wait events và công cụ của đúng engine/version.

### Phân biệt CPU time và elapsed time

CPU time có thể thấp hơn elapsed time nếu truy vấn chờ I/O, network, lock, worker khác hoặc temp storage. Với parallel query, tổng CPU time của tất cả worker có thể lớn hơn elapsed time vì nhiều CPU làm việc đồng thời.

Không cộng các operator elapsed một cách máy móc nếu thời gian của chúng chồng lấp trong pipeline hoặc parallel execution. Dùng định nghĩa của công cụ đo và so sánh cùng loại metric.

## Ví dụ chẩn đoán một truy vấn GROUP BY chậm

Một báo cáo tính doanh thu theo tenant và tháng trên bảng orders 300 triệu hàng. Query chạy 45 giây, CPU time 18 giây và temp I/O tăng cao.

Execution plan cho thấy:
- Scan đọc 120 triệu hàng sau filter.
- Estimated groups là 2 triệu, actual groups là 18 triệu.
- Hash Aggregate nhận nhiều hàng và vượt memory grant.
- Hash aggregate spill nhiều partition tạm.
- Một worker nhận gần 35% dữ liệu do tenant lớn.
- Final aggregate chờ worker nóng hoàn tất.

Nhóm điều tra:
1. Thống kê cũ khiến số nhóm ước lượng thấp hơn thực tế.
2. Khóa nhóm gồm tenant_id, month và product_id, làm số group lớn.
3. Một tenant chiếm tỷ lệ giao dịch cao.
4. Truy vấn đọc cột payload không cần thiết do SELECT rộng.
5. Không có partition pruning theo thời gian vì biểu thức lọc bọc cột ngày.

Các hướng điều chỉnh có thể:
- Dùng điều kiện khoảng nửa mở trực tiếp trên cột thời gian để tăng khả năng pruning.
- Chỉ chọn cột cần cho aggregate.
- Cập nhật thống kê và kiểm tra lại estimated/actual groups.
- Tách hoặc salting tenant nóng ở phase partial nếu engine/kiến trúc hỗ trợ và phép aggregate có thể merge chính xác.
- Cân nhắc summary table theo ngày/tenant nếu báo cáo chạy lặp lại và chấp nhận freshness phù hợp.
- Kiểm tra memory grant và concurrency của workload phân tích sau khi sửa cardinality.

Sau mỗi thay đổi, đo lại rows read, groups, spill bytes, exchange bytes, CPU, elapsed và tác động đến các truy vấn khác. Không tăng memory grant trước khi kiểm tra sai lệch thống kê và số nhóm; không thêm index nếu scan toàn bộ dữ liệu vẫn là phương án rẻ nhất.

## Quy trình tối ưu một workload tổng hợp lớn

1. **Xác định workload:** query fingerprint, tần suất, khoảng thời gian, tham số, kích thước dữ liệu và mức concurrency.
2. **Lấy baseline:** elapsed, CPU, p95/p99, throughput, reads, temp I/O, memory và exchange metrics.
3. **Đọc plan từ đầu vào đến kết quả:** scan, filter, join, partial aggregate, exchange, final aggregate và sort.
4. **Đối chiếu cardinality:** estimated/actual rows và groups ở từng bước.
5. **Kiểm tra tính đúng đắn:** grain dữ liệu, fan-out do join, NULL, DISTINCT và cách tính AVG.
6. **Giảm input:** predicate pushdown, partition pruning, projection hẹp và bỏ join không cần thiết.
7. **Đánh giá thuật toán aggregate:** Hash hay Stream/Sort, có thể tận dụng index order hay không.
8. **Đánh giá shuffle và skew:** rows/bytes theo worker, hot group và final merge.
9. **Đánh giá memory:** memory grant, hash/sort spill, temp storage và concurrency.
10. **Thử chiến lược thay thế:** partial aggregate, salting, pre-aggregation, columnstore hoặc summary table nếu phù hợp.
11. **Thay đổi từng yếu tố:** giữ dữ liệu, tham số và tải tương đương để xác định tác động.
12. **Đo toàn workload:** kiểm tra báo cáo mục tiêu, workload OLTP dùng chung, storage, memory và network.
13. **Theo dõi sau triển khai:** xem lại thống kê, dữ liệu skew và xu hướng tăng trưởng theo thời gian.

## Những sai lầm thường gặp

- **Nhìn số hàng kết quả rồi đánh giá truy vấn nhẹ:** aggregate có thể đọc hàng trăm triệu hàng để tạo vài chục nhóm.
- **Cho rằng Hash Aggregate luôn nhanh hơn Sort Aggregate:** hash có thể spill hoặc cần trạng thái rất lớn.
- **Cho rằng Stream Aggregate luôn tiết kiệm:** Sort trước nó có thể chi phối toàn bộ chi phí.
- **Nhầm Sort với Shuffle:** một thao tác sắp xếp cục bộ, một thao tác tái phân phối dữ liệu giữa worker.
- **Tưởng hash partition tự chia nhỏ hot key:** một giá trị nóng vẫn có thể tập trung vào một worker.
- **Chỉ xem tổng bytes shuffle:** bỏ qua phân bố bytes và thời gian từng worker.
- **Tăng memory grant ngay khi thấy spill:** có thể gây memory pressure và giảm concurrency.
- **Bỏ qua estimated/actual groups:** sai lệch cardinality thường dẫn đến chọn plan và cấp bộ nhớ không phù hợp.
- **Dùng AVG của các AVG partial:** kết quả sai khi các partial group có số hàng khác nhau.
- **JOIN làm nhân bản dữ liệu trước aggregate:** tổng hoặc count có thể bị phóng đại.
- **Dùng COUNT(DISTINCT) không cân nhắc trạng thái lớn:** chi phí memory và shuffle có thể tăng mạnh.
- **Tăng parallelism không đo:** có thể làm network, memory và CPU contention nghiêm trọng hơn.
- **Tạo index cho mọi GROUP BY:** tăng chi phí ghi và lưu trữ mà không chắc giảm tổng chi phí.
- **Duy trì summary table không đối soát:** truy vấn nhanh nhưng kết quả có thể sai hoặc cũ.
- **Đo một lần rồi kết luận:** cache, checkpoint, concurrency và thống kê có thể làm kết quả dao động.

## Checklist tổng hợp dữ liệu lớn

- [ ] Xác định số hàng đầu vào và số nhóm thực tế.
- [ ] Kiểm tra độ rộng khóa nhóm và trạng thái aggregate.
- [ ] Xác nhận filter được áp dụng trước aggregate khi đúng ngữ nghĩa.
- [ ] Kiểm tra JOIN có làm nhân bản hàng trước khi tổng hợp không.
- [ ] Phân biệt Hash Aggregate với Sort/Stream Aggregate.
- [ ] Xác định Sort có cần thiết và có spill hay không.
- [ ] Kiểm tra partial/local aggregate trước exchange.
- [ ] Đo rows/bytes shuffle và phân bố theo worker.
- [ ] Tìm hot group, skew và worker chậm nhất.
- [ ] Đối chiếu estimated/actual rows và groups.
- [ ] Đo memory grant, peak memory, spill bytes và temp I/O.
- [ ] Xem partition pruning, index order và columnstore nếu phù hợp.
- [ ] Xác minh tính đúng đắn của DISTINCT, AVG và aggregate nhiều phase.
- [ ] Đánh giá pre-aggregation/materialized view cùng freshness và đối soát.
- [ ] Đo p95/p99, throughput và tác động đến workload khác sau thay đổi.

## Kết luận

Tổng hợp trên dữ liệu lớn là quá trình đọc và biến đổi một lượng lớn hàng thành trạng thái theo nhóm. Chi phí phụ thuộc số hàng đầu vào, số nhóm, độ rộng khóa, thuật toán aggregate, bộ nhớ, sort, shuffle và độ cân bằng giữa các worker. Hash Aggregate tránh yêu cầu sắp xếp nhưng có thể cần nhiều bộ nhớ; Sort/Stream Aggregate có thể tiết kiệm trạng thái khi đầu vào đã có thứ tự nhưng bước sort có thể rất đắt. Trong hệ thống song song hoặc phân tán, partial aggregation giúp giảm dữ liệu trao đổi, còn shuffle và data skew có thể trở thành nút thắt.

Hãy đọc execution plan theo luồng dữ liệu, đo số hàng và số nhóm thực tế, spill, temp I/O, bytes exchange và thời gian từng worker. Giảm dữ liệu đầu vào, giữ đúng grain khi JOIN, cập nhật thống kê và chọn chiến lược partial/pre-aggregation phù hợp thường đem lại lợi ích rõ hơn việc chỉ tăng memory hoặc worker. Mỗi thay đổi cần được kiểm chứng về cả kết quả tính toán, độ trễ, throughput và tác động lên workload dùng chung.

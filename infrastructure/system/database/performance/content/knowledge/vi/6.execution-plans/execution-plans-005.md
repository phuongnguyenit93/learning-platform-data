# Nhận diện phép nối, sắp xếp, tổng hợp và ghi dữ liệu tạm

Kế hoạch thực thi (execution plan) mô tả cách hệ quản trị cơ sở dữ liệu biến một câu SQL thành các thao tác truy cập, kết hợp và xử lý dữ liệu. Khi tối ưu hiệu năng, cần đọc kế hoạch để tìm ra nơi truy vấn tiêu tốn nhiều công sức: phép nối phải xử lý quá nhiều hàng, thao tác sắp xếp phải giữ tập dữ liệu lớn trong bộ nhớ, phép tổng hợp tạo nhiều nhóm hoặc dữ liệu trung gian phải tràn ra vùng lưu trữ tạm.

Trong phạm vi DATABASE_PERFORMANCE, việc nhận diện các operator này giúp nối kết số liệu đo đạc với nguyên nhân cụ thể. Một kế hoạch có thể chứa nhiều operator hợp lệ; sự xuất hiện của Hash Join, Sort hay bảng tạm không tự động chứng minh truy vấn kém. Cần xem số hàng thực tế, số vòng lặp, kích thước dữ liệu, bộ nhớ được cấp, dấu hiệu spill và thời gian của từng nhánh để xác định operator nào đang tạo nút thắt.

## 1. Cách đọc một kế hoạch thực thi

Kế hoạch thường được trình bày dưới dạng cây. Các thao tác ở phía dưới cung cấp dữ liệu cho thao tác ở phía trên. Khi đọc, hãy bắt đầu từ các nút lá nơi dữ liệu được lấy từ bảng hoặc chỉ mục, sau đó lần theo cách dữ liệu được lọc, join, sort, aggregate và trả về.

Các thông tin quan trọng gồm:

- **Operator:** thao tác đang được thực hiện, ví dụ Index Scan, Nested Loop, Hash Join, Sort hoặc Hash Aggregate.
- **Estimated rows:** số hàng mà bộ tối ưu dự đoán operator sẽ tạo ra.
- **Actual rows:** số hàng thực tế được tạo ra khi kế hoạch được thực thi, nếu công cụ hỗ trợ actual plan.
- **Loops:** số lần operator được gọi. Một operator có ít hàng mỗi lượt vẫn có thể tốn kém nếu chạy hàng nghìn lần.
- **Width hoặc kích thước hàng:** độ rộng dữ liệu trung bình mà operator phải chuyển tiếp hoặc giữ trong bộ nhớ.
- **Cost:** ước lượng chi phí nội bộ của bộ tối ưu. Cost thường dùng để so sánh các phương án trong cùng hệ quản trị và cấu hình, không phải số mili giây thực tế.
- **Actual time và thời gian chờ:** thời gian quan sát được theo cách công cụ báo cáo; cần hiểu thời gian ở nút cha có thể bao gồm thời gian của các nút con.
- **Buffers, I/O, memory grant và spill:** số trang đọc/ghi, bộ nhớ được cấp hoặc dùng, cùng dấu hiệu dữ liệu trung gian phải ghi ra đĩa.

Một trong những dấu hiệu hữu ích nhất là chênh lệch giữa số hàng ước lượng và số hàng thực tế. Nếu bộ tối ưu dự đoán 100 hàng nhưng thực tế xử lý 500.000 hàng, nó có thể chọn thuật toán join, thứ tự join hoặc cách cấp bộ nhớ không phù hợp. Nguyên nhân có thể là thống kê cũ, phân bố lệch, tương quan giữa các cột hoặc tham số truy vấn không đại diện.

Ví dụ, một node được gọi 20.000 lần và mỗi lần trả về 3 hàng có thể xử lý tổng cộng khoảng 60.000 hàng. Chỉ nhìn con số 3 ở mỗi lần sẽ đánh giá thấp chi phí. Luôn xem Actual Rows cùng Loops, và đọc theo đúng định nghĩa của công cụ vì một số giao diện hiển thị số hàng trung bình mỗi vòng lặp.

## 2. Nhận diện các phép nối

Join kết hợp hàng từ hai nguồn theo điều kiện. Bộ tối ưu có thể chọn nhiều thuật toán khác nhau tùy kích thước đầu vào, chỉ mục, thứ tự dữ liệu, thống kê, bộ nhớ và chi phí ước lượng. Ba nhóm thường gặp là Nested Loop, Hash Join và Merge Join.

### 2.1. Nested Loop Join

Nested Loop lấy từng hàng từ đầu vào ngoài (outer input), sau đó tìm các hàng tương ứng trong đầu vào trong (inner input). Với mỗi hàng outer, hệ quản trị có thể quét inner hoặc thực hiện một lần tìm kiếm qua chỉ mục.

Mẫu hoạt động:

~~~text
for each row in outer:
    find matching rows in inner
    emit joined rows
~~~

Nested Loop thường phù hợp khi đầu vào outer nhỏ và inner có đường truy cập chọn lọc, chẳng hạn Index Seek hoặc Index Lookup theo khóa join. Nó cũng có thể hiệu quả với truy vấn chỉ cần một số ít hàng đầu tiên.

Dấu hiệu cần điều tra:

- Outer input có nhiều hàng hơn ước lượng.
- Inner operator có Loops rất lớn.
- Inner thực hiện Table Scan hoặc Index Scan lặp lại thay vì tìm kiếm có chọn lọc.
- Số hàng được đọc ở inner cao hơn nhiều số hàng cuối cùng được giữ lại.
- Có Key Lookup hoặc truy cập bổ sung lặp đi lặp lại cho từng hàng outer.

Ví dụ, nếu outer có 200.000 đơn hàng và inner phải quét 1 triệu hàng cho mỗi đơn hàng, chi phí có thể tăng rất nhanh. Ngược lại, 200.000 lần Index Seek vào một chỉ mục phù hợp có thể vẫn là phương án tốt tùy độ chọn lọc, cache và chi phí I/O.

Hãy kiểm tra điều kiện join có dùng đúng kiểu dữ liệu và cột khóa hay không, chỉ mục trên phía inner có phù hợp không, và bộ lọc có thể giảm outer input trước join không. Không tạo chỉ mục chỉ vì thấy Nested Loop; hãy xác nhận operator inner thực sự tốn chi phí và chỉ mục mới có thể hỗ trợ điều kiện truy cập.

### 2.2. Hash Join

Hash Join thường xây dựng bảng băm từ một đầu vào (build input), sau đó đọc đầu vào còn lại (probe input) và tìm các hàng có khóa khớp. Thuật toán này hữu ích khi hai tập dữ liệu tương đối lớn và không có sẵn thứ tự phù hợp để Merge Join.

Các dấu hiệu trong kế hoạch:

- Operator có tên Hash Join, Hash Match (Join) hoặc tên tương đương.
- Một nhánh được dùng để xây dựng bảng băm; nhánh còn lại dùng để probe.
- Kế hoạch có thông tin số hàng, kích thước bảng băm, memory grant hoặc số batch.
- Có cảnh báo spill hoặc nhiều batch khi dữ liệu băm vượt quá bộ nhớ khả dụng.

Hash Join có thể là lựa chọn rất hiệu quả cho join lớn. Vấn đề xuất hiện khi đầu vào thực tế lớn hơn nhiều ước lượng, hàng có độ rộng lớn, khóa phân bố lệch hoặc bộ nhớ được cấp không đủ. Khi đó, hệ quản trị có thể chia dữ liệu thành nhiều partition/batch và ghi một phần dữ liệu ra vùng tạm.

Khi điều tra, xác định nhánh build, số hàng và độ rộng hàng của nhánh đó. Kiểm tra thống kê, điều kiện lọc trước join và số hàng thực tế. Nếu có spill, tìm nguyên nhân: ước lượng sai, bộ nhớ giới hạn, concurrency cao hay dữ liệu thực sự quá lớn. Tăng bộ nhớ có thể giúp một truy vấn nhưng làm nhiều truy vấn đồng thời tranh chấp RAM; cần đánh giá ở mức workload.

Với khóa có độ lệch mạnh, một số giá trị có thể tạo partition lớn hơn nhiều phần còn lại. Hãy kiểm tra phân bố khóa join và số hàng thực tế của từng nhánh khi công cụ hỗ trợ. Tối ưu thống kê hoặc thay đổi cách lọc có thể hữu ích hơn việc chỉ tăng memory grant.

### 2.3. Merge Join

Merge Join kết hợp hai đầu vào đã được sắp xếp theo khóa join. Bộ máy tiến qua hai luồng dữ liệu theo thứ tự, ghép các khóa khớp và xử lý các nhóm khóa trùng.

Merge Join có thể hiệu quả với các tập dữ liệu lớn khi cả hai đầu vào đã có thứ tự phù hợp, ví dụ nhờ index scan theo khóa join. Nó cũng hữu ích khi đầu ra cần giữ thứ tự có thể tái sử dụng ở operator tiếp theo.

Điểm cần kiểm tra:

- Hai đầu vào có được cung cấp theo đúng thứ tự khóa join không?
- Kế hoạch có thêm Sort trước Merge Join không?
- Sort đó xử lý bao nhiêu hàng và có spill ra đĩa không?
- Có nhiều hàng trùng cùng khóa khiến một nhóm phải ghép với nhiều hàng ở nhóm bên kia không?
- Thứ tự sau Merge Join có đáp ứng ORDER BY của truy vấn hay vẫn cần Sort phía trên?

Merge Join không mặc nhiên nhanh hơn Hash Join. Nếu hai đầu vào chưa có thứ tự, chi phí sắp xếp có thể lớn hơn lợi ích của việc merge. Ngược lại, khi chỉ mục đã cung cấp thứ tự và dữ liệu lớn, Merge Join có thể tránh tạo bảng băm lớn.

### 2.4. Phân biệt điều kiện join và bộ lọc sau join

Trong kế hoạch, hãy phân biệt điều kiện dùng để ghép hàng với điều kiện lọc sau khi ghép. Một join có thể dùng khóa A để tìm cặp hàng, rồi áp dụng thêm một residual predicate trên cột B. Nếu residual predicate loại bỏ phần lớn hàng sau khi join, hệ thống có thể đã xử lý nhiều dữ liệu không cần thiết.

Kiểm tra:

- Kiểu dữ liệu hai phía của điều kiện join có tương thích không?
- Có chuyển đổi kiểu trên cột được lập chỉ mục không?
- Có hàm hoặc biểu thức làm điều kiện khó tận dụng chỉ mục không?
- Có thể áp dụng điều kiện lọc sớm hơn mà vẫn giữ nguyên ngữ nghĩa không?
- Thống kê có phản ánh tương quan giữa các cột trong điều kiện không?

Không đẩy điều kiện qua outer join một cách máy móc. Chuyển một predicate từ ON sang WHERE, hoặc ngược lại, có thể thay đổi cách giữ các hàng không khớp. Mọi thay đổi SQL phải được kiểm tra lại tính đúng đắn.

## 3. Nhận diện thao tác sắp xếp

Sort sắp xếp các hàng theo một hoặc nhiều khóa. Nó thường xuất hiện khi truy vấn có ORDER BY, khi một thuật toán cần dữ liệu theo thứ tự, hoặc khi các operator phía trên yêu cầu thứ tự đầu vào.

Sort không phải lúc nào cũng là vấn đề. Một tập nhỏ có thể được sắp xếp nhanh trong bộ nhớ. Cần quan tâm khi Sort xử lý nhiều hàng, hàng rộng, chiếm bộ nhớ lớn hoặc tràn ra đĩa.

### 3.1. Đọc Sort trong kế hoạch

Khi gặp Sort, xác định:

- Số hàng đi vào và số hàng đi ra.
- Các cột và chiều sắp xếp (ASC/DESC).
- Kích thước hàng và tổng dữ liệu cần sắp xếp.
- Sort có phải xử lý toàn bộ tập dữ liệu trước khi trả kết quả không.
- Có memory grant, memory used hoặc thông tin sort method không.
- Có dấu hiệu external sort, disk sort hoặc spill không.

Nếu Sort nằm ngay trên một scan lớn, truy vấn có thể phải đọc và sắp xếp nhiều hàng dù chỉ trả về một số ít. Nếu bộ lọc có thể giảm dữ liệu trước Sort, hãy kiểm tra xem điều đó có giữ nguyên ngữ nghĩa và có được bộ tối ưu thực hiện không.

### 3.2. Sort và chỉ mục

Chỉ mục có thứ tự phù hợp đôi khi cho phép hệ quản trị đọc dữ liệu theo thứ tự cần thiết và bỏ qua một operator Sort riêng. Ví dụ, truy vấn lọc theo customer_id rồi ORDER BY created_at có thể hưởng lợi từ chỉ mục ghép có customer_id ở phần đầu và created_at tiếp theo, tùy điều kiện lọc và cách hệ quản trị dùng chỉ mục.

Trước khi tạo chỉ mục để tránh Sort, cần xác nhận:

1. Thứ tự cột của chỉ mục có phù hợp với predicate và ORDER BY không.
2. Hướng sắp xếp và khả năng quét ngược có được hỗ trợ không.
3. Truy vấn có lọc bằng phép so sánh, range hoặc biểu thức làm thay đổi khả năng tận dụng thứ tự không.
4. Chỉ mục có đủ chọn lọc để giảm số hàng phải đọc không.
5. Chi phí tăng thêm cho INSERT, UPDATE, DELETE và dung lượng lưu trữ có chấp nhận được không.

Một chỉ mục giúp bỏ Sort nhưng buộc hệ thống đọc quá nhiều trang vẫn có thể là lựa chọn kém. So sánh toàn bộ kế hoạch và số liệu thực tế thay vì chỉ đếm số operator Sort.

### 3.3. Top-N và LIMIT

Khi truy vấn dùng ORDER BY kết hợp LIMIT hoặc TOP, bộ tối ưu có thể chọn thuật toán Top-N/Top Sort để giữ các hàng có thứ hạng tốt nhất thay vì sắp xếp toàn bộ kết quả theo cách thông thường. Điều này có thể giảm bộ nhớ, nhưng hệ thống vẫn có thể phải đọc toàn bộ đầu vào để biết hàng nào thuộc top N.

Nếu có chỉ mục phù hợp cung cấp thứ tự, engine có thể dừng sớm sau khi tìm đủ hàng, tùy điều kiện lọc và kế hoạch. Nếu không, LIMIT 20 không đảm bảo chỉ có 20 hàng được đọc. Hãy xem số hàng đầu vào của Sort, số hàng thực tế và operator phía dưới.

## 4. Nhận diện phép tổng hợp

Aggregate gom nhiều hàng thành các nhóm và tính giá trị như COUNT, SUM, AVG, MIN, MAX hoặc loại trùng với DISTINCT. Phép tổng hợp thường xuất hiện trong GROUP BY, DISTINCT, một số truy vấn con và các hàm cửa sổ.

Hai nhóm operator thường gặp là Stream/Group Aggregate và Hash Aggregate.

### 4.1. Stream Aggregate hoặc Group Aggregate

Stream Aggregate xử lý các hàng theo thứ tự khóa nhóm. Khi các hàng cùng khóa nằm liền nhau, engine có thể giữ trạng thái của nhóm hiện tại, cập nhật các giá trị tổng hợp rồi phát kết quả khi chuyển sang nhóm tiếp theo.

Ưu điểm là có thể dùng ít bộ nhớ hơn Hash Aggregate khi đầu vào đã được sắp xếp phù hợp. Thứ tự có thể đến từ chỉ mục hoặc từ một Sort trước đó.

Khi đọc kế hoạch, kiểm tra:

- Đầu vào có thực sự được sắp xếp theo các cột GROUP BY không?
- Có Sort đứng trước Aggregate không?
- Số nhóm thực tế là bao nhiêu so với số hàng đầu vào?
- Có operator nào khác làm mất hoặc thay đổi thứ tự trước Aggregate không?

Nếu phải Sort hàng triệu hàng chỉ để chạy Stream Aggregate, chi phí Sort có thể trở thành nút thắt. Đừng đánh giá Aggregate riêng lẻ mà bỏ qua operator cung cấp thứ tự.

### 4.2. Hash Aggregate

Hash Aggregate tạo bảng băm theo khóa nhóm và cập nhật trạng thái tổng hợp cho từng nhóm. Nó có thể xử lý đầu vào không có thứ tự và thường hữu ích khi số nhóm vừa phải so với số hàng đầu vào.

Hash Aggregate cần bộ nhớ cho bảng băm. Nếu số nhóm thực tế lớn hơn ước lượng hoặc trạng thái mỗi nhóm lớn, bộ nhớ có thể không đủ và engine phải chia batch hoặc ghi dữ liệu trung gian ra vùng tạm.

Các dấu hiệu cần xem:

- Số hàng đầu vào và số nhóm đầu ra.
- Số nhóm ước lượng so với số nhóm thực tế.
- Kích thước hàng hoặc trạng thái aggregate.
- Memory grant, memory usage, batch count và cảnh báo spill.
- Các cột được đưa vào GROUP BY hoặc DISTINCT có cần thiết không.

Giảm số hàng trước Aggregate có thể giảm chi phí nếu điều kiện lọc được áp dụng hợp lệ. Giảm số cột không cần thiết cũng giúp giảm độ rộng dữ liệu trung gian. Tuy nhiên, không thay đổi thứ tự lọc hoặc logic join theo cách làm thay đổi kết quả tổng hợp.

### 4.3. Partial và Final Aggregate

Trong kế hoạch song song hoặc kế hoạch phân tầng, engine có thể tính tổng hợp một phần trên từng worker rồi kết hợp các kết quả thành tổng hợp cuối. Các tên operator có thể gồm Partial Aggregate, Finalize Aggregate hoặc các biến thể tương ứng.

Điều này thường giúp giảm lượng dữ liệu phải chuyển giữa worker hoặc giữa các giai đoạn. Tuy nhiên, chi phí trao đổi dữ liệu (exchange) và số lượng nhóm trung gian vẫn có thể đáng kể. Hãy kiểm tra số hàng trước và sau mỗi giai đoạn, số worker thực sự tham gia và thời gian chờ đồng bộ.

### 4.4. DISTINCT và Window Function

DISTINCT thường cần sắp xếp hoặc băm để nhận diện các giá trị trùng. Vì vậy, một truy vấn DISTINCT trên nhiều cột có thể tạo Sort hoặc Hash Aggregate lớn.

Window Function như ROW_NUMBER, RANK, SUM OVER hoặc LAG có thể yêu cầu dữ liệu được phân vùng và sắp xếp theo PARTITION BY/ORDER BY. Kế hoạch có thể chứa Sort, Window Aggregate hoặc operator tương đương. Nếu phân vùng có một nhóm rất lớn hoặc dữ liệu đầu vào rộng, bộ nhớ và dữ liệu tạm có thể tăng.

Khi thấy operator window hoặc distinct tốn kém, kiểm tra xem các cột tham gia có cần thiết, thứ tự có thể được cung cấp từ chỉ mục không và có thể giới hạn dữ liệu đầu vào trước khi xử lý hay không. Luôn xác minh kết quả, đặc biệt với các hàm phụ thuộc thứ tự hàng.

## 5. Nhận diện dữ liệu tạm và thao tác spill

Operator Sort, Hash Join hoặc Hash Aggregate có thể cần vùng làm việc tạm. Nếu bộ nhớ được cấp không đủ, một phần dữ liệu trung gian sẽ được ghi ra đĩa và đọc lại trong quá trình thực thi. Quá trình này thường gọi là spill.

Cần phân biệt ba khái niệm:

- **Vùng làm việc trong bộ nhớ:** dữ liệu trung gian được giữ trong RAM để Sort, Hash hoặc Aggregate.
- **Spill hoặc temporary I/O nội bộ:** engine ghi dữ liệu trung gian ra file hoặc vùng lưu trữ tạm khi bộ nhớ không đủ.
- **Bảng/tệp tạm do câu SQL hoặc ứng dụng tạo:** dữ liệu được lưu rõ ràng vào temporary table hoặc temporary object theo logic ứng dụng.

Ba loại này có thể cùng tiêu thụ tài nguyên nhưng ý nghĩa khác nhau. Một truy vấn tạo temporary table có chủ đích không đồng nghĩa operator bị spill. Ngược lại, truy vấn không khai báo bảng tạm vẫn có thể phát sinh nhiều I/O tạm bên trong engine.

### 5.1. Dấu hiệu trong PostgreSQL

Với PostgreSQL, EXPLAIN (ANALYZE, BUFFERS) cung cấp thời gian thực tế, số hàng, buffer hit/read và thông tin block tạm nếu phát sinh. Các dấu hiệu thường gặp:

- "temp read" và "temp written" trong phần Buffers cho biết block tạm đã được đọc/ghi.
- "Sort Method: external merge" cùng thông tin Disk cho thấy Sort đã dùng file tạm trên đĩa.
- Hash node có số Batches lớn hơn 1 có thể cho thấy phép băm phải chia nhiều batch; cần đọc thêm thông tin memory và temp buffers.
- Chênh lệch lớn giữa estimated rows và actual rows có thể khiến bộ tối ưu đánh giá thiếu nhu cầu bộ nhớ.

Ví dụ lệnh đọc kế hoạch:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT customer_id, COUNT(*), SUM(total_amount)
FROM orders
WHERE created_at >= TIMESTAMP '2026-01-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-02-01 00:00:00'
GROUP BY customer_id
ORDER BY SUM(total_amount) DESC
LIMIT 20;
~~~

Nếu kế hoạch cho thấy HashAggregate hoặc Sort ghi nhiều block tạm, hãy xác định operator gây spill và số hàng đi vào operator đó. Không diễn giải shared read thành số lần đọc trực tiếp từ thiết bị: block có thể đã nằm trong cache của hệ điều hành. EXPLAIN ANALYZE thực thi câu lệnh, do đó cần cân nhắc tải và tác động trước khi chạy trên production.

### 5.2. Dấu hiệu trong SQL Server

Trong SQL Server, Actual Execution Plan có thể hiển thị cảnh báo spill trên Sort hoặc Hash Match. Một số phiên bản cung cấp thông tin về spill level, số trang hoặc byte ghi/đọc ở tempdb, cùng memory grant requested, granted và used.

Các operator thường cần kiểm tra:

- Sort có cảnh báo spill hoặc thông tin dữ liệu tràn ra tempdb.
- Hash Match (Join/Aggregate) có cảnh báo spill, nhiều partition hoặc batch.
- Memory grant lớn bất thường hoặc nhỏ hơn nhiều nhu cầu thực tế.
- Operator nhận số hàng thực tế vượt xa ước lượng.
- Tempdb có mức đọc/ghi tăng cùng thời điểm truy vấn chạy.

Có thể kết hợp Actual Execution Plan với:

~~~sql
SET STATISTICS IO ON;
SET STATISTICS TIME ON;

-- Chạy truy vấn cần đo tại đây.

SET STATISTICS IO OFF;
SET STATISTICS TIME OFF;
~~~

STATISTICS IO/TIME cho biết một số chỉ số I/O và thời gian; Actual Plan giúp xác định operator cụ thể. Cần phân biệt I/O của bảng tạm do ứng dụng tạo với spill do engine thực hiện trong tempdb. Đồng thời, xem xét memory grant của toàn workload vì nhiều truy vấn đồng thời có thể cạnh tranh bộ nhớ.

### 5.3. Dấu hiệu trong MySQL

Trong MySQL, EXPLAIN ANALYZE (các phiên bản hỗ trợ, từ 8.0.18) cho biết thời gian và số hàng thực tế theo iterator. EXPLAIN hoặc EXPLAIN FORMAT=TREE giúp nhận diện join, sort và các bước xử lý. Một số kế hoạch dạng tabular có thể hiển thị:

- "Using temporary": truy vấn sử dụng bảng tạm nội bộ cho một phần xử lý.
- "Using filesort": MySQL thực hiện thuật toán sắp xếp bổ sung để đáp ứng thứ tự yêu cầu.

Hai thông tin này không tự động chứng minh dữ liệu đã được ghi ra đĩa. Temporary table có thể nằm trong bộ nhớ hoặc chuyển sang cơ chế lưu trữ trên đĩa tùy kích thước, loại dữ liệu và giới hạn cấu hình. Filesort có thể sử dụng bộ nhớ hoặc file tạm. Cần kết hợp Performance Schema, trạng thái temporary table, số liệu I/O và cấu hình liên quan để xác định chi phí thực tế.

MySQL thường dùng Nested Loop cho nhiều kiểu join; các phiên bản hỗ trợ Hash Join có thể thể hiện operator này trong tree plan. Hãy xem actual rows và loops ở từng iterator để nhận diện việc đọc lặp lại hoặc đầu vào lớn. Không suy ra spill chỉ từ việc có Using temporary hay Using filesort.

### 5.4. Tìm đúng operator tạo dữ liệu tạm

Khi thấy temp read/write tăng, không nên chỉ kết luận “truy vấn dùng quá nhiều temp”. Hãy lần theo kế hoạch để tìm Sort, Hash Join, Hash Aggregate hoặc Window operator nào có thể tạo spill. Nếu công cụ không gắn trực tiếp lượng I/O tạm với từng operator, hãy kết hợp cảnh báo của actual plan, thời điểm chạy, số liệu tempdb/temp file và phép đo từng operator.

Ghi lại:

- Operator và nhánh dữ liệu liên quan.
- Số hàng, số nhóm và độ rộng hàng thực tế.
- Memory grant hoặc memory limit.
- Số batch/partition, số lần spill và lượng dữ liệu tạm nếu có.
- Thời gian, I/O và mức độ ảnh hưởng đến truy vấn khác.

## 6. Ví dụ đọc kế hoạch của truy vấn báo cáo

Giả sử hệ thống cần tổng hợp doanh thu theo khu vực và ngày. Câu SQL minh họa:

~~~sql
SELECT
    c.region,
    CAST(o.created_at AS DATE) AS order_day,
    COUNT(*) AS item_count,
    SUM(oi.quantity * oi.unit_price) AS revenue
FROM orders AS o
JOIN customers AS c
    ON c.id = o.customer_id
JOIN order_items AS oi
    ON oi.order_id = o.id
WHERE o.created_at >= :from_time
  AND o.created_at < :to_time
GROUP BY
    c.region,
    CAST(o.created_at AS DATE)
ORDER BY revenue DESC;
~~~

Giả sử actual plan trong một lần chạy minh họa cho thấy:

| Khu vực kế hoạch | Estimated rows | Actual rows | Dấu hiệu |
|---|---:|---:|---|
| Lọc orders theo thời gian | 40.000 | 420.000 | Ước lượng thấp hơn thực tế hơn 10 lần |
| Join customers | 40.000 | 420.000 | Hash Join đọc lượng hàng lớn hơn dự kiến |
| Join order_items | 300.000 | 2.800.000 | Số hàng tăng do mỗi đơn có nhiều mặt hàng |
| Aggregate theo region và ngày | 5.000 nhóm | 18.000 nhóm | Hash Aggregate dùng nhiều bộ nhớ |
| Sort theo revenue | 5.000 | 18.000 | Sort phát sinh spill ra vùng tạm |

Các số liệu trên chỉ minh họa cách đọc, không phải kết quả benchmark thực tế. Từ chúng có thể đặt ra một số giả thuyết:

1. Bộ lọc ngày trên orders trả về nhiều hàng hơn ước lượng. Cần kiểm tra thống kê cột created_at, phân bố theo thời gian và kế hoạch truy cập.
2. Join order_items làm tăng số hàng vì một đơn có nhiều mặt hàng. Đây có thể là số lượng hợp lệ theo quan hệ dữ liệu, không nhất thiết là lỗi join. Cần xác minh khóa join và số mặt hàng trung bình trên mỗi đơn.
3. Aggregate tạo nhiều nhóm hơn dự đoán. Thống kê hoặc tương quan giữa region và ngày có thể chưa được mô hình hóa chính xác.
4. Sort xử lý toàn bộ số nhóm để xếp theo revenue. Nếu không có thứ tự phù hợp từ đầu vào, việc Sort là hợp lý; cần xem kích thước dữ liệu và dấu hiệu spill.

Quy trình điều tra:

1. So sánh estimated rows và actual rows ở từng operator, đặc biệt tại nhánh orders và order_items.
2. Xác nhận join key, ràng buộc quan hệ và số hàng thực tế của từng đơn. Nếu kết quả nhân bản ngoài dự kiến, kiểm tra điều kiện join trước khi tối ưu.
3. Kiểm tra chỉ mục hỗ trợ lọc khoảng thời gian trên orders và truy cập order_items theo order_id. Thứ tự cột và loại chỉ mục phải dựa trên predicate, độ chọn lọc và hệ quản trị.
4. Kiểm tra thống kê, histogram và dữ liệu lệch; cập nhật thống kê trong môi trường thử nghiệm nếu cần rồi đo lại.
5. Xem Aggregate và Sort có spill không, memory grant hoặc vùng làm việc có đủ không, và có thể giảm hàng/cột trung gian mà vẫn giữ nguyên kết quả hay không.
6. Chạy lại với cùng snapshot, tham số, cache state và concurrency; so sánh thời gian, logical/physical reads, temp I/O, số hàng và kết quả nghiệp vụ.

Không nên cố loại bỏ Sort chỉ vì nó xuất hiện cuối kế hoạch. ORDER BY revenue yêu cầu sắp xếp theo giá trị được tính từ phép tổng hợp; chỉ mục trên bảng gốc thường không thể cung cấp trực tiếp thứ tự này. Cần tập trung giảm dữ liệu đầu vào, cải thiện ước lượng, kiểm soát memory pressure và xác nhận mức chi phí của Sort trong tải thực.

## 7. Quy trình đọc join, sort, aggregate và temp I/O

Có thể áp dụng trình tự sau cho một truy vấn chậm:

1. **Xác định phạm vi:** ghi SQL, tham số, phiên bản, trạng thái cache, số phiên đồng thời và mục tiêu đo.
2. **Đọc từ các node lá:** xem scan/seek, số hàng đọc, số hàng sau filter và buffer/I/O.
3. **Đọc join:** nhận diện thuật toán, outer/inner hoặc build/probe input, số vòng lặp, số hàng trước/sau join và residual predicate.
4. **Đọc Sort:** kiểm tra sort key, số hàng, độ rộng, memory grant và spill.
5. **Đọc Aggregate:** phân biệt Stream/Group với Hash Aggregate, số nhóm, thứ tự đầu vào, số batch và spill.
6. **Theo dõi temp I/O:** xác định dữ liệu tạm do operator nội bộ hay temporary object do ứng dụng tạo; tìm operator và nhánh phát sinh.
7. **Đối chiếu ước lượng:** so sánh estimated/actual rows, thống kê và phân bố dữ liệu.
8. **Đặt giả thuyết cụ thể:** ví dụ inner scan lặp lại, Hash Join spill, Sort xử lý quá nhiều hàng hoặc Aggregate có số nhóm vượt dự kiến.
9. **Thay đổi có kiểm soát:** thử một điều chỉnh chính mỗi lần, chẳng hạn chỉ mục, predicate, thống kê hoặc cấu hình làm việc.
10. **Xác minh:** chạy cùng workload và dữ liệu, kiểm tra thời gian, tài nguyên, temp I/O và tính đúng đắn của kết quả.

## 8. Hướng tối ưu theo từng dấu hiệu

| Dấu hiệu trong kế hoạch | Câu hỏi cần trả lời | Hướng xử lý để thử nghiệm |
|---|---|---|
| Nested Loop có inner scan lặp nhiều | Outer có quá nhiều hàng? Inner có chỉ mục phù hợp? | Giảm outer hợp lệ, xem lại join key và chỉ mục inner |
| Hash Join có nhiều batch hoặc spill | Build input có lớn hơn ước lượng? Bộ nhớ có bị cạnh tranh? | Kiểm tra thống kê, giảm dữ liệu đầu vào, độ rộng hàng và memory grant |
| Merge Join có Sort ở cả hai đầu vào | Có cách cung cấp thứ tự từ chỉ mục? Sort có spill? | Đánh giá chỉ mục theo join key và thứ tự cần thiết |
| Sort lớn trước LIMIT | Engine phải đọc bao nhiêu hàng để tìm top N? | Xem chỉ mục cung cấp thứ tự, predicate và khả năng dừng sớm |
| Stream Aggregate có Sort phía trước | Có thể lấy dữ liệu theo thứ tự nhóm từ chỉ mục? | Đánh giá index order và số hàng cần sắp xếp |
| Hash Aggregate có nhiều nhóm hoặc spill | Số nhóm và độ rộng trạng thái có vượt ước lượng? | Kiểm tra thống kê, giảm hàng/cột đầu vào và memory pressure |
| Temp I/O cao nhưng không thấy rõ operator | Có spill ẩn trong plan hay temp object của ứng dụng? | Dùng actual plan, cảnh báo spill và thống kê temp của hệ quản trị |

Các hướng xử lý là giả thuyết để kiểm tra, không phải quy tắc áp dụng tự động. Chỉ mục mới có thể làm truy vấn đọc nhanh hơn nhưng tăng dung lượng và chi phí ghi. Tăng bộ nhớ có thể giảm spill cho một truy vấn nhưng làm nhiều phiên đồng thời thiếu RAM. Viết lại SQL có thể thay đổi ngữ nghĩa nếu điều kiện join, NULL, duplicate hoặc thứ tự xử lý không được giữ nguyên.

## 9. Những nhầm lẫn thường gặp

- **Thấy Hash Join là cho rằng kế hoạch xấu.** Hash Join thường phù hợp với đầu vào lớn; cần xem kích thước, ước lượng và spill.
- **Thấy Nested Loop là cho rằng phải đổi sang Hash Join.** Nested Loop có thể tốt khi outer nhỏ và inner có index lookup hiệu quả.
- **Thấy Merge Join là cho rằng không có chi phí Sort.** Hai đầu vào có thể phải được sắp xếp trước khi merge.
- **Thấy Sort là cho rằng cần thêm chỉ mục.** Sort nhỏ có thể rẻ; chỉ mục mới có thể không chọn lọc hoặc tăng chi phí ghi.
- **Thấy LIMIT nhỏ là cho rằng chỉ đọc ít hàng.** Nếu không có thứ tự từ chỉ mục, engine có thể vẫn phải xử lý nhiều hàng trước khi chọn top N.
- **Thấy Hash Aggregate là cho rằng GROUP BY có vấn đề.** Cần xem số nhóm, kích thước trạng thái và bộ nhớ.
- **Thấy Using temporary hoặc Using filesort là khẳng định đã ghi đĩa.** Các dấu hiệu của MySQL không tự chứng minh temporary data đã spill ra storage.
- **Đồng nhất temp table với spill.** Một temporary table được tạo có chủ đích khác với I/O tạm nội bộ của Sort/Hash.
- **Chỉ nhìn cost ước lượng.** Cost không phải thời gian thực tế; cần actual rows, loops, time và I/O.
- **Chỉ nhìn operator mà bỏ qua dữ liệu.** Phân bố lệch, thống kê cũ và tham số có thể là nguyên nhân gốc của kế hoạch không phù hợp.
- **Tăng memory ngay khi thấy spill.** Cần kiểm tra concurrency, memory grant và giới hạn RAM tổng thể.

## 10. Checklist đánh giá kế hoạch

- [ ] Đã lưu SQL, tham số, phiên bản và actual execution plan.
- [ ] Đã đọc kế hoạch từ node lá lên node trả kết quả.
- [ ] Đã so sánh estimated rows với actual rows tại các node quan trọng.
- [ ] Đã xem Loops và tổng số hàng thực tế qua operator lặp.
- [ ] Đã nhận diện Nested Loop, Hash Join hoặc Merge Join và hiểu hai đầu vào.
- [ ] Đã xác nhận join key, residual predicate và khả năng nhân bản hàng.
- [ ] Đã xác định Sort key, số hàng, độ rộng và yêu cầu thứ tự.
- [ ] Đã phân biệt Stream/Group Aggregate với Hash Aggregate.
- [ ] Đã xem số nhóm, memory grant, batch và dấu hiệu spill.
- [ ] Đã phân biệt temp I/O nội bộ với temporary object do ứng dụng tạo.
- [ ] Đã đối chiếu số liệu temp, buffer, I/O và tài nguyên của hệ quản trị.
- [ ] Đã kiểm tra thống kê và phân bố dữ liệu khi ước lượng sai.
- [ ] Đã đo lại dưới cùng dữ liệu, tham số, cache và concurrency.
- [ ] Đã xác nhận kết quả truy vấn giữ nguyên ngữ nghĩa nghiệp vụ.

Đọc được các phép nối, sắp xếp, tổng hợp và thao tác ghi dữ liệu tạm giúp biến execution plan thành bản đồ chẩn đoán. Khi kết hợp operator với số hàng thực tế, số vòng lặp, bộ nhớ, I/O và thống kê, ta có thể xác định đúng giai đoạn tạo chi phí, chọn thay đổi phù hợp và kiểm chứng hiệu quả trên workload đại diện.

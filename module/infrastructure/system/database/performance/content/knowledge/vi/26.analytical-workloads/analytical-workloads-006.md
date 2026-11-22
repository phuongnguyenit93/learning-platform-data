# Phân bố dữ liệu, khóa phân phối và các nhóm dữ liệu quá lớn

Trong hệ quản trị phân tích phân tán, dữ liệu thường được chia qua nhiều node, worker, shard hoặc slice để các phần của truy vấn có thể chạy song song. Cách chia dữ liệu quyết định worker nào lưu một hàng, worker nào phải đọc dữ liệu khi JOIN hoặc GROUP BY, và liệu một phần của workload có bị dồn vào một node hay không.

Nếu phân bố đều, các worker có lượng dữ liệu và công việc tương đối cân bằng. Nếu một số khóa xuất hiện áp đảo, một vài worker có thể phải xử lý nhiều hàng hơn hẳn phần còn lại. Hiện tượng này gọi là data skew. Một truy vấn chạy song song khi đó vẫn có thể chậm như chạy tuần tự, vì thời gian hoàn tất thường bị quyết định bởi worker chậm nhất. Các nhóm có số hàng rất lớn hoặc một khóa được truy cập liên tục còn có thể tạo hot partition, tăng spill, I/O, network shuffle và tranh chấp tài nguyên.

Bài học thuộc chương **Tải phân tích** của module DATABASE_PERFORMANCE. Module rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, khi thiết kế phân bố dữ liệu cho workload phân tích, cần đánh giá đồng thời tính cân bằng, khả năng co-location, kiểu truy vấn, kích thước nhóm, data movement và chi phí duy trì phân phối.

## 1. Phân bố dữ liệu trong hệ thống phân tán

Một bảng phân tán không nhất thiết nằm trên một máy. Hệ quản trị có thể chia hàng thành nhiều phần và đặt chúng trên các node hoặc worker. Khóa phân phối (distribution key, shard key hoặc partitioning key tùy nền tảng) là thuộc tính hoặc biểu thức được dùng để quyết định vị trí lưu hàng.

Ví dụ, một bảng orders có thể được phân phối theo customer_id. Các đơn hàng của cùng khách hàng được đặt cùng một shard hoặc cùng một nhóm worker. Khi truy vấn tìm đơn hàng theo customer_id, hệ thống có thể định tuyến tới đúng nơi chứa dữ liệu. Nếu truy vấn tổng hợp toàn bộ khách hàng, nhiều worker có thể xử lý các phần dữ liệu song song rồi hợp nhất kết quả.

~~~text
                    Bảng orders
                         |
                   Distribution key
                     customer_id
                         |
             +-----------+-----------+
             |           |           |
          Worker 0    Worker 1    Worker 2
          IDs A,D     IDs B,E     IDs C,F
             |           |           |
          Scan/Join   Scan/Join   Scan/Join
             +-----------+-----------+
                         |
                  Merge/aggregate
                         |
                    Kết quả
~~~

Sơ đồ chỉ minh họa nguyên tắc. Hàm hash, số bucket, cách ánh xạ bucket sang node và cơ chế di chuyển dữ liệu là chi tiết riêng của từng nền tảng.

### 1.1. Phân biệt distribution, partition và shard

Các thuật ngữ có thể khác nhau giữa sản phẩm:

| Khái niệm | Mục đích thường gặp | Phạm vi |
| --- | --- | --- |
| Distribution | Chia hàng qua các worker/node để xử lý song song | Cluster hoặc MPP database |
| Sharding | Chia dữ liệu thành các shard có thể nằm trên node khác nhau | Hệ phân tán hoặc ứng dụng |
| Partitioning | Chia một bảng thành các phần logic/vật lý, thường theo range/list/hash | Bảng hoặc database |
| Bucketing | Chia dữ liệu thành bucket theo hàm hash hoặc quy tắc định tuyến | Bảng hoặc tập dữ liệu |

Một bảng có thể vừa được partition theo ngày, vừa được distribute theo customer_id. Khi đó partition pruning chọn khoảng ngày cần đọc, còn distribution quyết định worker nào sở hữu các hàng trong partition. Không nên coi hai quyết định này là một.

## 2. Những kiểu phân phối phổ biến

### 2.1. Hash distribution

Hệ thống áp dụng hàm hash lên khóa phân phối để chọn bucket hoặc worker. Nếu khóa có nhiều giá trị và phân bố tương đối đồng đều, hash distribution thường chia dữ liệu khá cân bằng.

Ưu điểm:

- Phân tán các giá trị khóa trên nhiều worker.
- Phù hợp với truy vấn equality trên distribution key.
- Có thể giúp JOIN hai bảng khi chúng dùng cùng quy tắc phân phối trên cùng khóa.

Hạn chế:

- Khó tận dụng thứ tự dữ liệu theo range.
- Khóa có ít giá trị hoặc một giá trị chiếm đa số gây skew.
- Thay đổi số bucket hoặc node có thể cần tái phân phối dữ liệu.
- Điều kiện range trên khóa hash thường phải kiểm tra nhiều worker.

### 2.2. Range distribution

Dữ liệu được chia theo khoảng giá trị, ví dụ ngày tạo từ đầu tháng đến cuối tháng hoặc ID theo các dải.

Ưu điểm:

- Có thể định tuyến và loại bỏ các range không liên quan.
- Hữu ích cho truy vấn theo thời gian hoặc miền giá trị liên tục.
- Có thể hỗ trợ quản lý vòng đời dữ liệu theo range.

Hạn chế:

- Range có lượng dữ liệu khác nhau gây skew.
- Dữ liệu mới liên tục rơi vào range cuối có thể tạo hotspot.
- Phân bố thay đổi theo thời gian có thể khiến ranh giới cũ mất cân bằng.

### 2.3. List distribution

Một số nền tảng cho phép ánh xạ giá trị hoặc nhóm giá trị cụ thể vào partition. Cách này phù hợp khi miền giá trị nhỏ, được biết trước và mỗi nhóm có kích thước tương đối ổn định. Nếu một giá trị có khối lượng vượt trội, list partition vẫn có thể trở thành hotspot.

### 2.4. Round-robin hoặc phân phối không dựa trên khóa

Hàng được luân phiên hoặc phân bổ theo cơ chế cân bằng mà không gom các hàng cùng một giá trị khóa vào một worker.

Ưu điểm:

- Có thể tạo phân bố hàng khá đều khi nạp dữ liệu.
- Hữu ích cho staging table hoặc workload quét toàn bộ dữ liệu.

Hạn chế:

- Các hàng cần JOIN theo khóa có thể nằm rải rác trên mọi worker.
- Truy vấn lọc theo một giá trị không nhất thiết định vị được worker chứa hàng.
- Có thể phải shuffle dữ liệu khi JOIN hoặc GROUP BY.

### 2.5. Replicated hoặc broadcast

Với bảng nhỏ, hệ thống có thể sao chép bảng tới nhiều worker. Khi bảng fact được phân phối, mỗi worker có thể JOIN với bản dimension cục bộ mà không cần di chuyển dimension trong mỗi truy vấn.

Replication giảm network shuffle cho một số phép JOIN nhưng tăng dung lượng lưu trữ và chi phí cập nhật/đồng bộ. Chỉ nên dùng khi bảng đủ nhỏ, thay đổi không quá thường xuyên và cơ chế nhất quán của nền tảng đáp ứng yêu cầu.

## 3. Khóa phân phối quyết định điều gì?

Khóa phân phối ảnh hưởng đến:

- **Cân bằng dữ liệu:** số hàng và dung lượng mỗi worker có gần nhau không.
- **Cân bằng công việc:** mỗi worker phải xử lý số hàng, số nhóm và lượng I/O tương đương không.
- **Data locality:** các hàng cần JOIN hoặc GROUP BY có nằm cùng nơi không.
- **Network shuffle:** có phải gửi hàng qua mạng để đưa dữ liệu về cùng worker không.
- **Khả năng định tuyến:** điều kiện truy vấn có xác định được một phần dữ liệu không.
- **Mở rộng:** thêm node hoặc tăng số bucket có dễ tái phân phối không.
- **Vận hành:** khóa có ổn định, phân bố có thay đổi theo thời gian và có dễ quan sát không.

Một khóa có thể cân bằng số hàng nhưng làm JOIN tốn shuffle. Một khóa giúp JOIN co-located có thể lại bị lệch vì một giá trị xuất hiện quá nhiều. Cần chọn dựa trên workload tổng thể thay vì một câu SQL riêng lẻ.

## 4. Tiêu chí chọn distribution key

### 4.1. Cardinality đủ lớn

Cardinality là số giá trị phân biệt của khóa. Khóa chỉ có vài giá trị thường không đủ để chia đều lên nhiều worker. Ví dụ, phân phối bảng giao dịch theo status với ba giá trị PAID, PENDING và CANCELLED có thể chỉ tạo ra ba nhóm dữ liệu lớn, dù bảng có hàng tỷ hàng.

Cardinality cao tạo nhiều giá trị để hash phân tán, nhưng không bảo đảm cân bằng. Một khóa có hàng triệu giá trị vẫn có thể skew nếu một số giá trị chiếm phần lớn hàng.

### 4.2. Phân bố tần suất tương đối đồng đều

Hãy xem số hàng theo từng giá trị, không chỉ đếm số giá trị phân biệt. Các phân vị p50, p95, p99 và giá trị lớn nhất cho biết mức độ lệch.

Một khóa có một triệu customer_id nhưng một khách hàng chiếm 30% số đơn hàng vẫn có skew nghiêm trọng.

### 4.3. Phù hợp với JOIN thường xuyên

Nếu hai bảng lớn thường JOIN theo customer_id, phân phối cả hai theo customer_id có thể giúp dữ liệu cùng khách hàng nằm trên cùng worker. Điều kiện này chỉ đúng khi hai bảng dùng cùng quy tắc hash, cùng kiểu biểu diễn và cách ánh xạ tương thích theo nền tảng.

Nếu bảng orders phân phối theo customer_id còn bảng payments theo payment_id, JOIN theo order_id hoặc customer_id có thể cần shuffle một phía hoặc cả hai.

### 4.4. Phù hợp với điều kiện lọc

Truy vấn thường lọc theo distribution key có thể giảm số worker phải tham gia. Tuy nhiên, nếu đa số truy vấn phân tích quét toàn bảng và GROUP BY theo chiều khác, lợi ích định tuyến có thể nhỏ.

### 4.5. Ổn định và có chất lượng dữ liệu tốt

Khóa nên ít thay đổi sau khi hàng được ghi. Nếu thay đổi distribution key buộc hàng chuyển node, chi phí cập nhật và đồng bộ có thể lớn. Cần xem NULL, giá trị mặc định, dữ liệu lỗi và cách chuẩn hóa khóa.

Không nên mặc định NULL sẽ được phân phối đều. Nhiều hệ thống hash cùng giá trị NULL hoặc biểu diễn NULL theo một cách cố định, khiến hàng NULL tập trung vào một bucket. Phải kiểm tra quy tắc cụ thể của nền tảng và chất lượng dữ liệu.

## 5. Data skew và các dạng lệch phổ biến

Data skew xảy ra khi dữ liệu hoặc công việc phân bố không đều giữa các worker. Có thể phân biệt:

### 5.1. Row skew

Một worker lưu nhiều hàng hơn đáng kể so với worker khác. Điều này làm tăng dung lượng, scan và I/O trên worker đó.

### 5.2. Byte skew

Số hàng có thể gần bằng nhau nhưng kích thước hàng khác nhau. Worker chứa nhiều JSON, text hoặc payload lớn sẽ đọc và truyền nhiều byte hơn.

### 5.3. Compute skew

Các worker có số hàng tương đương nhưng lượng công việc khác nhau. Ví dụ, một số nhóm có số phần tử lớn khiến hash aggregation, sort hoặc xử lý window tốn nhiều CPU và bộ nhớ.

### 5.4. Join skew

Một khóa JOIN xuất hiện nhiều lần ở một hoặc cả hai phía. Khi hash join, hàng của một khóa nặng có thể tập trung vào một worker và tạo ra phép nối có số hàng kết quả rất lớn.

### 5.5. Hot-key hoặc access skew

Một khóa được truy cập hoặc cập nhật liên tục. Với hệ thống có thao tác ghi hoặc trạng thái dùng chung, hot key có thể gây tranh chấp và hotspot ngay cả khi tổng số hàng được lưu khá cân bằng.

### 5.6. Temporal skew

Dữ liệu mới dồn vào khoảng thời gian gần nhất. Range partition theo ngày hoặc tháng có thể làm partition hiện tại nóng hơn các partition cũ. Đây là hiện tượng thường gặp ở event, log và giao dịch mới.

## 6. Đo mức độ skew

Không nên đánh giá phân bố chỉ bằng tổng số hàng. Hãy thu thập số hàng, dung lượng, số nhóm và thời gian xử lý theo worker hoặc partition.

### 6.1. Tỷ lệ max/average

Một chỉ số đơn giản:

\[
\text{Skew ratio} = \frac{\text{Maximum worker rows}}{\text{Average worker rows}}
\]

Ví dụ, cluster có 8 worker và 120 triệu hàng:

- Trung bình: 15 triệu hàng mỗi worker.
- Worker lớn nhất: 36 triệu hàng.
- Skew ratio: \(36/15 = 2,4\).

Worker lớn nhất có lượng hàng gấp 2,4 lần mức trung bình. Đây là dấu hiệu cần điều tra, nhưng không có một ngưỡng đúng cho mọi engine. Dung lượng, row width, CPU và cách lập lịch cũng ảnh hưởng kết quả.

### 6.2. Độ lệch chuẩn và hệ số biến thiên

Với số hàng \(x_i\) trên mỗi worker, có thể tính trung bình \(\mu\), độ lệch chuẩn \(\sigma\) và hệ số biến thiên:

\[
CV = \frac{\sigma}{\mu}
\]

CV cao cho thấy mức phân tán quanh trung bình lớn. Chỉ số này bổ sung cho max/average vì max/average tập trung vào worker nặng nhất còn CV phản ánh toàn bộ phân bố.

### 6.3. Phân bố theo khóa

Với bảng fact, có thể dùng truy vấn khái niệm sau để xem các khóa nặng:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS row_count,
    SUM(amount) AS total_amount
FROM orders
GROUP BY customer_id
ORDER BY row_count DESC
FETCH FIRST 100 ROWS ONLY;
~~~

Cú pháp giới hạn hàng có thể khác theo hệ quản trị. Truy vấn này tìm các heavy hitter theo số hàng. Có thể chạy thêm theo tổng byte ước lượng, số bản ghi theo thời gian và các khóa JOIN.

Không chỉ xem top 10. Hãy xem histogram hoặc phân vị để biết phân bố đuôi dài. Một số ít khóa rất nặng có thể quyết định thời gian hoàn tất toàn bộ truy vấn.

### 6.4. Đo skew của công việc

Ghi nhận theo worker:

- Actual rows và bytes đọc.
- CPU time.
- I/O read/write và temp spill.
- Network bytes gửi/nhận.
- Số nhóm được tạo và số hàng sau JOIN.
- Thời gian bắt đầu/kết thúc operator.

Nếu một worker có thời gian xử lý cao hơn nhiều trong khi row count gần bằng nhau, có thể là compute skew, row width skew hoặc join fanout.

## 7. Các nhóm dữ liệu quá lớn (heavy groups)

Heavy group là một nhóm theo khóa có số hàng lớn vượt trội so với nhóm thông thường. Ví dụ:

- Một khách hàng doanh nghiệp chiếm 25% tổng số giao dịch.
- Một tenant lớn có lượng event gấp hàng trăm lần tenant khác.
- Một sản phẩm phổ biến xuất hiện trong phần lớn đơn hàng.
- Một status hoặc category có tỷ trọng rất cao.
- Một ngày có lượng log tăng đột biến do sự cố hoặc chiến dịch.

Khi GROUP BY theo khóa phân phối, mọi hàng của cùng khóa có thể được gom về một worker để tạo kết quả nhóm. Nếu một khóa có hàng trăm triệu hàng, worker sở hữu khóa đó phải xử lý phần lớn công việc của nhóm, dù các worker khác đã hoàn tất.

Đây là giới hạn quan trọng: phân phối hash cân bằng các khóa khác nhau không thể tự động chia một nhóm logic duy nhất thành nhiều nhóm kết quả độc lập mà vẫn giữ đúng ngữ nghĩa GROUP BY. Muốn chia nhóm lớn, cần chiến lược tính toán nhiều giai đoạn hoặc xử lý riêng heavy hitter.

## 8. Hot partition và tác động đến workload

Hot partition xuất hiện khi một partition hoặc worker nhận lượng truy cập, I/O hoặc cập nhật vượt trội. Các dấu hiệu:

- Một worker có CPU, disk I/O hoặc network cao hơn nhiều.
- Một partition tăng kích thước nhanh hơn phần còn lại.
- Query plan chạy song song nhưng thời gian hoàn tất bị kéo dài bởi một worker.
- Temp spill tập trung ở worker xử lý nhóm lớn.
- Throughput tổng không tăng khi thêm worker.
- Hàng đợi hoặc lock wait tập trung vào một khóa/partition.

Hot partition có thể đến từ lựa chọn distribution key, dữ liệu thực tế, lịch nạp, truy vấn hoặc mô hình truy cập. Thêm node không nhất thiết giúp nếu cùng khóa vẫn luôn được ánh xạ về một worker.

## 9. Ví dụ: chọn khóa phân phối cho bảng orders

Giả sử một kho dữ liệu có bảng orders với các cột:

- order_id: mã đơn hàng duy nhất.
- customer_id: khách hàng.
- created_at: thời điểm tạo.
- status: trạng thái.
- amount: giá trị đơn hàng.

Các truy vấn phổ biến:

1. Báo cáo doanh thu theo khách hàng.
2. JOIN orders với payments theo order_id.
3. Phân tích trạng thái đơn hàng theo tháng.
4. Truy vấn lịch sử đơn của một customer_id.

### Đánh giá một số khóa ứng viên

| Khóa ứng viên | Điểm mạnh | Rủi ro |
| --- | --- | --- |
| status | Dễ lọc theo trạng thái | Cardinality thấp, thường gây skew |
| created_at theo range | Hỗ trợ truy vấn theo thời gian | Ngày hiện tại có thể nóng; lượng dữ liệu theo ngày không đều |
| order_id | Cardinality cao, thường phân tán tốt | Có thể không co-locate với JOIN theo customer hoặc báo cáo nhóm khách hàng |
| customer_id | Hỗ trợ lịch sử và GROUP BY theo khách hàng | Khách hàng lớn tạo heavy group; JOIN theo order_id có thể cần shuffle |
| Hash kết hợp customer_id và order_id | Có thể chia nhỏ đơn của một khách hàng | JOIN theo customer_id không còn tự động co-located; phải cân nhắc cách join |

Không có khóa tốt nhất nếu chưa biết tỷ trọng truy vấn và phân bố thực tế. Nếu workload chủ yếu JOIN orders với payments theo order_id, phân phối hai bảng theo order_id có thể giảm shuffle. Nếu workload chủ yếu phân tích từng khách hàng, customer_id có thể tốt hơn, nhưng cần kiểm tra heavy customers.

### Thử nghiệm có kiểm soát

Tạo các bản sao thử nghiệm với những khóa ứng viên, nạp cùng một tập dữ liệu và chạy cùng workload. So sánh:

- Skew ratio và CV của số hàng/bytes.
- Thời gian JOIN và số bytes shuffle.
- Thời gian GROUP BY và worker chậm nhất.
- Partition pruning hoặc distribution pruning.
- Dung lượng và chi phí nạp/cập nhật.
- Độ trễ p95/p99 của workload quan trọng.

Chọn phương án tối ưu cho toàn bộ workload có trọng số, không chỉ truy vấn nhanh nhất.

## 10. Xử lý nhóm quá lớn bằng hai giai đoạn aggregation

Một cách phổ biến để giảm hotspot khi GROUP BY là tính tổng từng phần trước, sau đó tổng hợp các phần.

Giả sử cần tổng doanh thu theo customer_id. Nếu một khách hàng có quá nhiều hàng, có thể thêm salt để chia dữ liệu của khách hàng đó thành nhiều bucket phụ:

~~~sql
WITH partial_totals AS
(
    SELECT
        customer_id,
        MOD(HASH(order_id), 16) AS salt,
        SUM(amount) AS partial_amount,
        COUNT(*) AS partial_count
    FROM orders
    GROUP BY
        customer_id,
        MOD(HASH(order_id), 16)
)
SELECT
    customer_id,
    SUM(partial_amount) AS total_amount,
    SUM(partial_count) AS order_count
FROM partial_totals
GROUP BY customer_id;
~~~

Đây là SQL minh họa. Tên hàm HASH, kiểu số trả về và hàm MOD phụ thuộc hệ quản trị; cần dùng biểu thức hash ổn định và tránh vấn đề số âm theo quy tắc của engine.

Ở giai đoạn đầu, cùng một customer_id được tách thành tối đa 16 nhóm con theo salt. Các nhóm con có thể được phân phối trên nhiều worker nếu distribution key bao gồm customer_id và salt. Giai đoạn sau cộng các partial result để khôi phục một hàng kết quả cho mỗi customer_id.

### Điều kiện áp dụng

- Phép tổng hợp có thể kết hợp từ kết quả từng phần, ví dụ SUM và COUNT.
- Salt được tính ổn định cho cùng một hàng.
- Distribution hoặc plan thực sự phân phối các nhóm con qua nhiều worker.
- Chi phí aggregation lần hai nhỏ hơn lợi ích giảm hotspot.

### Những phép tổng hợp cần chú ý

- SUM và COUNT có thể kết hợp bằng cách tổng hợp partial result.
- AVG cần giữ cả SUM và COUNT rồi chia ở bước cuối; không lấy trung bình của các trung bình nếu kích thước nhóm con khác nhau.
- MIN và MAX có thể tổng hợp MIN/MIN hoặc MAX/MAX của kết quả từng phần.
- COUNT(DISTINCT) thường cần thuật toán hoặc cấu trúc riêng; cộng số distinct của các nhóm con có thể đếm trùng.
- Median, percentile và các phép thống kê phức tạp có thể cần state mergeable hoặc thuật toán xấp xỉ.

Salting làm tăng số nhóm trung gian và chi phí merge. Chọn số bucket quá lớn có thể tăng network, metadata và overhead; quá nhỏ thì nhóm lớn vẫn nóng. Hãy đo theo phân bố heavy hitter.

## 11. Salting cho JOIN có khóa nặng

JOIN hai bảng lớn theo một khóa có tần suất rất cao có thể tạo skew. Một chiến lược là gắn salt cho phía lớn và nhân bản các hàng dimension tương ứng theo các giá trị salt để phép JOIN vẫn khớp.

Ví dụ khái niệm:

~~~text
Fact rows:
  customer_id = C100, salt = 0..15
  customer_id = C100, các hàng được chia theo salt

Dimension rows:
  customer_id = C100, salt = 0
  customer_id = C100, salt = 1
  ...
  customer_id = C100, salt = 15

JOIN theo customer_id và salt
~~~

Kỹ thuật này tăng số hàng dimension và yêu cầu điều khiển việc tạo salt nhất quán. Nó chỉ phù hợp khi chi phí nhân bản bảng phía nhỏ thấp hơn chi phí skew của JOIN. Không nên nhân bản toàn bộ bảng dimension lớn hoặc thực hiện salting tùy tiện mà không xác minh số hàng kết quả.

Một lựa chọn khác là tách heavy hitter ra xử lý riêng: truy vấn các khóa phổ biến theo một nhánh, các khóa còn lại theo nhánh khác, sau đó UNION ALL và hợp nhất kết quả. Cách này cần danh sách heavy hitter được quản lý hoặc xác định từ thống kê cập nhật.

## 12. Replicate bảng nhỏ để giảm data movement

Nếu một bảng dimension nhỏ được dùng trong nhiều JOIN, replicate/broadcast có thể giúp mỗi worker có bản sao cục bộ. Khi đó bảng fact không cần shuffle chỉ để tìm bản ghi dimension.

Ví dụ, bảng country hoặc product_category có vài nghìn hàng có thể được replicate trong khi bảng sales có hàng tỷ hàng.

Trước khi replicate, cần kiểm tra:

- Kích thước thực tế và tốc độ tăng của dimension.
- Tần suất cập nhật và độ trễ đồng bộ cho các bản sao.
- Chi phí bộ nhớ và lưu trữ trên mỗi worker.
- Optimizer có chọn broadcast join đúng lúc không.
- Có nguy cơ replicate bảng lớn do thống kê sai không.

Replicate bảng nhỏ không giải quyết skew trong fact table nếu một khóa fact vẫn chiếm phần lớn dữ liệu.

## 13. Kết hợp distribution key với partitioning

Một bảng phân tích có thể partition theo thời gian và distribute theo một khóa nghiệp vụ. Ví dụ:

- Partition theo tháng để loại bỏ các tháng không liên quan.
- Hash distribute theo customer_id để co-locate dữ liệu khách hàng.

Truy vấn:

~~~sql
SELECT
    customer_id,
    SUM(amount) AS revenue
FROM orders
WHERE created_at >= DATE '2026-01-01'
  AND created_at <  DATE '2026-02-01'
GROUP BY customer_id;
~~~

Partition pruning có thể chỉ đọc partition tháng 1. Sau đó các worker xử lý phần dữ liệu tháng được chọn theo distribution. Tuy nhiên, nếu một customer_id chiếm phần lớn doanh thu và hàng, worker chứa khách hàng đó vẫn có thể nặng.

Khi chọn partition key, cần xem:

- Điều kiện lọc có thường xuyên dùng khóa này không?
- Số partition có hợp lý và kích thước có cân bằng không?
- Partition hiện tại có trở thành hotspot không?
- Dữ liệu đến muộn hoặc cập nhật dữ liệu cũ được xử lý ra sao?
- Có quá nhiều partition nhỏ làm tăng metadata và planning overhead không?

Khi chọn distribution key, cần xem:

- Phân bố khóa và heavy hitter.
- JOIN co-location.
- GROUP BY và các phép tổng hợp.
- Khả năng định tuyến truy vấn.
- Chi phí tái phân phối và thay đổi khóa.

## 14. Các dấu hiệu trong execution plan

Execution plan của hệ phân tán có thể hiển thị các bước di chuyển dữ liệu hoặc tổng hợp theo worker. Tên operator thay đổi theo engine, nhưng các dấu hiệu thường gặp gồm:

- Redistribute, repartition hoặc shuffle: hàng được gửi qua mạng để phân phối lại theo khóa.
- Broadcast: một tập dữ liệu được sao chép đến nhiều worker.
- Gather hoặc gather merge: kết quả từ nhiều worker được đưa về một điểm.
- Partial/final aggregate: tổng hợp từng phần rồi hợp nhất.
- Skew warning hoặc per-worker row counts: phân bố công việc không đều.
- Spill to disk: hash/sort không đủ bộ nhớ.
- Một worker có actual rows, bytes hoặc elapsed time cao vượt trội.

Khi đọc plan:

1. Xác định operator đầu tiên làm tăng network bytes.
2. Kiểm tra distribution key của hai phía JOIN.
3. So actual rows theo worker, không chỉ tổng rows.
4. Xác định GROUP BY có tập trung một khóa nặng không.
5. Kiểm tra spill và memory usage ở worker nặng nhất.
6. Đối chiếu estimated rows với actual rows và thống kê heavy hitter.

Một plan có shuffle không nhất thiết là sai. Shuffle có thể là cần thiết để bảo đảm đúng ngữ nghĩa. Câu hỏi là lượng dữ liệu phải di chuyển có quá lớn và có cách giảm chi phí mà vẫn giữ kết quả chính xác không.

## 15. Quy trình chọn và kiểm chứng distribution key

Thực hiện theo thứ tự:

1. **Thu thập workload:** truy vấn JOIN, GROUP BY, filter, sort, window và tần suất chạy.
2. **Phân tích khóa ứng viên:** cardinality, histogram, top values, NULL, giá trị mặc định và độ ổn định.
3. **Đo dữ liệu hiện tại:** rows, bytes, nhóm lớn và phân bố theo worker/partition.
4. **Đánh giá locality:** bảng nào thường JOIN cùng khóa, bảng nhỏ nào có thể replicate.
5. **Đọc execution plan:** shuffle, broadcast, gather, partial aggregate và spill.
6. **Lập phương án:** hash, range, list, round-robin hoặc kết hợp partition với distribution.
7. **Thử trên dữ liệu đại diện:** bao gồm heavy hitter, tenant lớn, ngày tải cao và phân bố lệch.
8. **Đo song song:** max/average rows, CV, bytes, CPU, I/O, network và worker elapsed time.
9. **Đo toàn workload:** thời gian JOIN/GROUP BY, p95/p99, throughput và chi phí nạp/cập nhật.
10. **Đánh giá vận hành:** tái phân phối, thêm node, dữ liệu mới, late-arriving data và khả năng phục hồi.
11. **Triển khai có kiểm soát:** chuyển đổi dữ liệu theo kế hoạch, theo dõi skew và chuẩn bị phương án quay lại.

Không chọn khóa chỉ dựa trên cardinality hoặc một truy vấn benchmark. Khóa tốt cần cân bằng dữ liệu và công việc, đồng thời giảm data movement cho các truy vấn quan trọng.

## 16. Ví dụ điều tra: báo cáo doanh thu chậm vì một khách hàng quá lớn

Một kho dữ liệu bán hàng có 500 triệu đơn hàng và 64 worker. Bảng orders được hash distribute theo customer_id. Hầu hết khách hàng có vài trăm đến vài nghìn đơn, nhưng một khách hàng doanh nghiệp có hơn 90 triệu đơn.

Truy vấn báo cáo:

~~~sql
SELECT
    customer_id,
    SUM(amount) AS revenue
FROM orders
WHERE created_at >= DATE '2026-01-01'
GROUP BY customer_id;
~~~

Triệu chứng:

- 63 worker hoàn tất scan và partial aggregation sớm.
- Một worker xử lý lượng hàng lớn hơn nhiều và hoàn tất muộn.
- CPU, I/O và temp spill của worker đó cao.
- Tổng thời gian truy vấn gần bằng thời gian worker chậm nhất.

Quy trình xử lý:

1. Xem phân bố số đơn theo customer_id và xác nhận heavy hitter.
2. So row count và byte count trên 64 worker.
3. Kiểm tra actual plan để xác định thời gian bị tiêu tốn ở scan hay aggregate.
4. Thử hai giai đoạn aggregation với salt theo order_id.
5. Kiểm tra partial result có được phân tán trên nhiều worker không.
6. Đo chi phí final aggregation và số hàng trung gian.
7. So kết quả SUM với truy vấn gốc để bảo đảm không thiếu hoặc đếm lặp.
8. Chạy lại workload có đồng thời các báo cáo khác và đo p95/p99.

Nếu scan dữ liệu theo ngày mới là phần chi phí chính, salting chỉ giảm aggregate hotspot mà không giải quyết scan. Khi đó cần xem partition pruning, filter và tổ chức lưu trữ. Phải xác định operator gây nghẽn trước khi chọn biện pháp.

## 17. Những sai lầm thường gặp

### Chọn khóa có cardinality cao nhưng phân bố lệch

Nhiều giá trị phân biệt không bảo đảm tần suất đồng đều. Luôn xem top values và phân vị số hàng.

### Chọn khóa theo một truy vấn duy nhất

Khóa tối ưu cho JOIN có thể không tốt cho GROUP BY hoặc filter. Đánh giá workload có trọng số.

### Dùng thời gian làm khóa hash mà không xét độ lệch

Nếu dữ liệu mới tập trung vào thời điểm hiện tại, một số cách partition/distribution có thể tạo hotspot. Phân biệt hash theo timestamp với range partition theo timestamp.

### Dùng khóa có ít giá trị

Status, region hoặc category có miền nhỏ có thể dồn dữ liệu vào vài worker.

### Giả định NULL được chia đều

Nhiều hàng NULL có thể tập trung vào một bucket tùy engine. Kiểm tra dữ liệu và quy tắc hash.

### Salting mọi truy vấn

Salting làm tăng số nhóm trung gian, phức tạp JOIN và cần bước hợp nhất. Chỉ áp dụng cho khóa nặng đã được xác nhận.

### Replicate bảng dimension quá lớn

Broadcast có thể biến network shuffle thành chi phí truyền và lưu nhiều bản sao. Đo kích thước và tần suất cập nhật.

### Chỉ nhìn số hàng

Hàng rộng, JSON/LOB hoặc số phép toán khác nhau có thể khiến bytes và CPU lệch dù row count tương tự.

### Không kiểm tra tính đúng của kết quả sau chia nhóm

AVG, DISTINCT, percentile và phép tổng hợp phức tạp cần state merge đúng cách. Không cộng các giá trị trung gian một cách máy móc.

## 18. Nguyên tắc cần ghi nhớ

- Distribution key quyết định nơi hàng được đặt và ảnh hưởng trực tiếp đến locality, shuffle, cân bằng và khả năng định tuyến.
- Hash, range, list, round-robin và replication có ưu/nhược điểm khác nhau; lựa chọn phụ thuộc workload.
- Cardinality cao không đồng nghĩa phân bố đều; cần xem tần suất khóa, top values và phân vị.
- Data skew có thể là row skew, byte skew, compute skew, join skew, hot-key hoặc temporal skew.
- Heavy group có thể khiến một worker quyết định thời gian hoàn tất của toàn truy vấn.
- Co-location giúp giảm data movement khi các bảng lớn JOIN theo cùng distribution key và quy tắc phân phối tương thích.
- Salting và two-stage aggregation có thể chia nhóm lớn thành các phần rồi hợp nhất, nhưng cần bảo toàn ngữ nghĩa từng phép tổng hợp.
- Replicate bảng nhỏ có thể giảm shuffle nhưng tăng dung lượng và chi phí đồng bộ.
- Partition pruning và distribution pruning giải quyết hai quyết định khác nhau; có thể kết hợp nhưng không thay thế nhau.
- Đọc actual plan theo worker, network bytes, spill và elapsed time để tìm điểm skew.
- Kiểm chứng bằng workload đại diện, bao gồm heavy hitter và tải cao điểm, đồng thời so kết quả nghiệp vụ trước/sau.

Phân bố dữ liệu tốt giúp hệ thống phân tích tận dụng song song mà không để một worker trở thành điểm nghẽn. Khi chọn distribution key dựa trên cả phân bố khóa lẫn kiểu truy vấn, đo được heavy group và đọc đúng dấu hiệu shuffle/skew trong execution plan, nhóm vận hành có thể giảm data movement và cân bằng công việc. Các kỹ thuật như salting, partial aggregation, replication và partition pruning cần được kiểm chứng trên dữ liệu lệch thực tế để bảo đảm tốc độ tăng mà kết quả vẫn chính xác.

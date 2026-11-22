# Thu thập nhật ký truy vấn chậm và thống kê theo mẫu truy vấn

Muốn tối ưu hiệu năng cơ sở dữ liệu, trước hết cần biết truy vấn nào đang chạy, chạy bao nhiêu lần, tiêu tốn tài nguyên nào và chậm trong hoàn cảnh nào. Một truy vấn có thời gian chạy rất dài nhưng chỉ xuất hiện một lần mỗi tuần có thể ít ảnh hưởng hơn một truy vấn mất vài mili giây nhưng được gọi hàng chục nghìn lần mỗi phút. Ngược lại, một nhóm truy vấn có thời gian trung bình tốt vẫn có thể tạo ra độ trễ p99 rất cao cho một số người dùng.

Trong chương **Quan sát hệ thống**, bài học này hướng dẫn thu thập nhật ký truy vấn chậm và thống kê theo mẫu truy vấn. Đây là một phần của phương pháp tối ưu hiệu năng trong module **DATABASE_PERFORMANCE**, nơi quyết định điều chỉnh phải dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Nhật ký giúp xem từng lần thực thi có vấn đề; thống kê tổng hợp giúp nhìn ra nhóm truy vấn chiếm nhiều thời gian hoặc tài nguyên trong toàn workload.

Mục tiêu không phải thu thập càng nhiều log càng tốt. Mục tiêu là tạo ra dữ liệu quan sát đủ tin cậy để tìm đúng nhóm truy vấn cần điều tra, liên kết chúng với tải và tài nguyên của hệ thống, sau đó kiểm chứng thay đổi bằng phép đo trước và sau.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt nhật ký truy vấn chậm với thống kê tổng hợp theo mẫu truy vấn và hiểu vai trò bổ sung của từng nguồn.
- Thiết lập ngưỡng ghi nhận truy vấn chậm phù hợp với mục tiêu độ trễ và tải hệ thống.
- Giải thích query fingerprint hoặc digest và cách gom các câu SQL cùng cấu trúc.
- Thu thập các chỉ số như số lần chạy, tổng thời gian, thời gian trung bình, số dòng đọc/trả về, I/O và dữ liệu tạm.
- Nhận diện truy vấn chậm theo từng lần chạy, truy vấn tiêu tốn tài nguyên tích lũy và truy vấn có độ trễ bất thường theo tham số.
- Liên kết dữ liệu truy vấn với metrics, traces, execution plan và bối cảnh tải.
- Thiết kế quy trình thu thập, bảo vệ, lưu trữ và phân tích dữ liệu quan sát an toàn.

## 1. Quan sát hiệu năng cơ sở dữ liệu cần những tín hiệu nào?

Quan sát hệ thống (observability) là khả năng hiểu trạng thái bên trong của hệ thống thông qua dữ liệu mà hệ thống phát ra. Với cơ sở dữ liệu, ba nhóm tín hiệu thường được dùng là logs, metrics và traces.

| Tín hiệu | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Logs | Sự kiện cụ thể nào đã xảy ra? | Một câu SQL chạy 2,4 giây, lỗi deadlock, timeout |
| Metrics | Hệ thống và nhóm truy vấn đang hoạt động ra sao theo thời gian? | Số lần gọi, tổng thời gian, CPU, buffer reads, connections |
| Traces | Một request ứng dụng đi qua những thành phần nào và mất thời gian ở đâu? | API chờ pool 80 ms, DB query 40 ms, serialize 10 ms |

Ba loại tín hiệu bổ sung cho nhau. Slow query log cho thấy một lần chạy cụ thể vượt ngưỡng. Thống kê theo mẫu truy vấn cho biết mẫu SQL nào tiêu tốn nhiều thời gian tổng cộng. Trace cho biết thời gian DBMS có phải phần chính trong độ trễ mà người dùng trải nghiệm hay không.

Ví dụ, một API mất 900 ms. Trace cho thấy ứng dụng chờ connection pool 650 ms, DBMS thực thi SQL 120 ms và phần còn lại dành cho mạng cùng xử lý kết quả. Chỉ xem slow query log có thể không tìm thấy truy vấn nào vượt ngưỡng 200 ms, trong khi người dùng vẫn cảm nhận API rất chậm. Vì vậy, phải xác định rõ phạm vi của từng phép đo.

### 1.1. Nhật ký truy vấn chậm

Slow query log ghi lại những lần thực thi thỏa điều kiện cấu hình, thường dựa trên thời gian chạy hoặc các tiêu chí bổ sung như số dòng được kiểm tra. Một bản ghi có thể chứa câu SQL, thời gian, người dùng, database, client, số dòng đọc hoặc trả về, cùng thông tin phiên.

Nhật ký hữu ích để:

- Tìm các lần chạy vượt ngưỡng.
- So sánh những lần chạy của cùng một mẫu SQL.
- Xem câu lệnh và tham số trong bối cảnh cụ thể nếu chính sách logging cho phép.
- Phát hiện truy vấn bất thường, lỗi, timeout hoặc thay đổi đột ngột.
- Lấy một lần chạy làm đầu mối để xem execution plan và dữ liệu liên quan.

Slow log thường là dữ liệu theo từng sự kiện. Nếu chỉ bật ngưỡng rất cao, ta có thể bỏ qua truy vấn chạy thường xuyên nhưng hơi chậm. Nếu đặt ngưỡng quá thấp, lượng log có thể tăng mạnh và chính hoạt động ghi log trở thành một phần tải đáng kể.

### 1.2. Thống kê theo mẫu truy vấn

Thống kê theo mẫu truy vấn gom nhiều câu SQL có cùng cấu trúc thành một nhóm. Các giá trị literal thường được chuẩn hóa hoặc thay bằng dấu tham số để những câu như sau được xem là cùng một mẫu:

~~~sql
SELECT status FROM orders WHERE order_id = 1001;
SELECT status FROM orders WHERE order_id = 1002;
SELECT status FROM orders WHERE order_id = 1003;
~~~

Mẫu chuẩn hóa có thể được biểu diễn như:

~~~sql
SELECT status FROM orders WHERE order_id = ?;
~~~

Tùy DBMS, cơ chế này được gọi là query fingerprint, query ID hoặc digest. Một nhóm thống kê thường có số lần gọi, tổng thời gian, thời gian trung bình, số dòng đọc/trả về, số lần dùng bảng tạm hoặc các bộ đếm I/O.

Thống kê giúp trả lời:

- Mẫu SQL nào chạy nhiều nhất?
- Mẫu nào chiếm tổng thời gian DBMS lớn nhất?
- Mẫu nào đọc nhiều dòng hơn số dòng trả về?
- Mẫu nào tạo nhiều dữ liệu tạm hoặc buffer read?
- Mẫu nào có thời gian trung bình hoặc tối đa tăng lên theo thời gian?

Thống kê tổng hợp thường không giữ lại đầy đủ từng lần chạy. Một số hệ thống chỉ cung cấp trung bình và giá trị cực đại, không cung cấp p95/p99 cho từng query digest. Khi cần phân vị, cần log theo sự kiện, tracing hoặc hệ thống metrics có histogram.

### 1.3. Vì sao cần cả hai?

Slow log và query statistics có thể cho ra thứ tự ưu tiên khác nhau.

- Một truy vấn báo cáo chạy 15 giây một lần có thể xuất hiện rõ trong slow log nhưng chỉ đóng góp ít tổng thời gian trong ngày.
- Một truy vấn tra cứu mất 4 ms nhưng chạy 50.000 lần có thể chiếm tổng thời gian lớn, dù hầu như không xuất hiện trong slow log.
- Một mẫu SQL có thời gian trung bình 5 ms nhưng đôi khi mất 2 giây có thể bị che khuất bởi giá trị trung bình.

Vì vậy, hãy dùng slow log để tìm các lần chạy đuôi dài và dùng thống kê theo mẫu để ưu tiên theo tổng tác động.

## 2. Hiểu ngưỡng ghi nhận truy vấn chậm

### 2.1. Ngưỡng thời gian

Ngưỡng slow query là thời gian mà từ đó một lần thực thi được ghi vào nhật ký. Ngưỡng nên dựa trên mục tiêu dịch vụ, độ trễ thông thường, loại workload và khả năng xử lý log.

Ví dụ minh họa:

- API tra cứu tương tác có mục tiêu p95 dưới 100 ms. Ngưỡng 500 ms có thể bỏ qua nhiều truy vấn đã ảnh hưởng rõ đến trải nghiệm.
- Tác vụ báo cáo có mục tiêu hoàn tất trong 30 giây. Ngưỡng 100 ms có thể tạo quá nhiều log không cần thiết.
- Một nhóm truy vấn nền chạy theo lô có thể cần ngưỡng riêng hoặc được quan sát bằng metrics theo job.

Không có một giá trị ngưỡng phù hợp cho mọi hệ thống. Hãy bắt đầu từ mục tiêu độ trễ và baseline, sau đó điều chỉnh theo tỷ lệ log, lượng dữ liệu phát sinh và khả năng điều tra.

### 2.2. Ngưỡng không phải SLA

Một truy vấn không xuất hiện trong slow log không có nghĩa nó luôn đáp ứng SLA. Nếu ngưỡng đặt 500 ms, mọi lần chạy 300 ms sẽ không được ghi theo điều kiện thời gian đó. Tương tự, một truy vấn có thể mất 20 ms trong DBMS nhưng request vẫn chậm do pool wait, mạng hoặc client xử lý dữ liệu.

Hãy dùng các ngưỡng khác nhau cho các mục tiêu khác nhau:

- Ngưỡng slow log để ghi nhận các lần chạy cần xem xét.
- Histogram latency để theo dõi p50/p95/p99.
- Cảnh báo dịch vụ để phát hiện vi phạm SLO.
- Ngưỡng tài nguyên để phát hiện CPU, I/O, bộ nhớ hoặc connection saturation.

### 2.3. Log theo mẫu và sampling

Một số DBMS hỗ trợ ghi log theo xác suất hoặc giới hạn mẫu, bên cạnh ngưỡng thời gian. Sampling giúp giảm lượng log trong hệ thống tải cao, nhưng có thể bỏ sót những sự kiện hiếm. Nếu dùng sampling, hãy ghi rõ tỷ lệ lấy mẫu và không diễn giải số lượng bản ghi thu được như tổng số lần chạy thực tế nếu chưa hiệu chỉnh.

Một cách tiếp cận thường dùng là giữ thống kê tổng hợp liên tục, đồng thời bật slow log ở ngưỡng có ý nghĩa. Khi điều tra sự cố, có thể tạm thời giảm ngưỡng hoặc tăng sampling trong một khoảng thời gian giới hạn, sau đó đưa cấu hình về mức vận hành đã định.

## 3. Chọn thông tin cần ghi trong slow query log

Một bản ghi hữu ích cần đủ dữ liệu để trả lời ai chạy, chạy ở đâu, mẫu truy vấn nào, khi nào và tốn bao nhiêu thời gian. Tùy DBMS, các trường có thể gồm:

| Trường | Mục đích |
|---|---|
| Timestamp | Xác định thời điểm và liên hệ với đợt tải |
| Database/schema | Xác định phạm vi dữ liệu |
| User/role | Xác định tài khoản thực thi |
| Application name/client | Phân biệt dịch vụ hoặc job gọi SQL |
| Session/process ID | Liên kết các sự kiện trong cùng phiên |
| Query ID/digest | Gom các lần chạy cùng mẫu |
| Duration/elapsed time | Đánh giá thời gian thực thi |
| Rows examined/read | Ước lượng lượng dữ liệu DBMS phải xem xét |
| Rows returned/sent | Biết lượng dữ liệu kết quả |
| Lock/wait information | Nhận diện thời gian chờ nếu DBMS cung cấp |
| Error/SQL state | Phân tích lỗi và retry |
| Plan identifier | Liên hệ với kế hoạch nếu hệ thống hỗ trợ |

Không phải DBMS nào cũng ghi tất cả trường trên. Có trường được tính ở tầng ứng dụng, có trường chỉ xuất hiện trong công cụ phân tích thống kê. Không nên giả định một định dạng log chung cho mọi sản phẩm.

### 3.1. Phân biệt thời gian thực thi và thời gian phản hồi

Elapsed time trong DBMS có thể bao gồm thời gian chờ tài nguyên mà DBMS theo dõi, nhưng thường không bao gồm thời gian ứng dụng chờ lấy connection pool trước khi gửi SQL. Nó cũng có thể khác với thời gian client đọc hết kết quả.

Khi điều tra, hãy xác định:

- Đồng hồ bắt đầu tại lúc ứng dụng gọi driver, lúc DBMS nhận câu lệnh hay lúc execution bắt đầu?
- Đồng hồ dừng khi DBMS hoàn tất, khi dòng đầu tiên được gửi hay khi client đọc hết kết quả?
- Thời gian parse/plan có được tính chung không?
- Thời gian lock wait có nằm trong elapsed time không?
- Client có tiêu thụ dữ liệu chậm làm DBMS bị backpressure không?

Định nghĩa khác nhau sẽ dẫn đến so sánh sai. Ghi rõ phạm vi đo trong dashboard và tài liệu vận hành.

### 3.2. Câu SQL và tham số

Log có thể ghi câu SQL đã chuẩn hóa hoặc câu lệnh thực tế. Câu lệnh thực tế giúp tái hiện vấn đề, nhưng giá trị literal có thể chứa email, số điện thoại, token, dữ liệu thanh toán hoặc thông tin cá nhân. Một số DBMS hoặc driver cũng có tùy chọn ghi giá trị bind parameter.

Trước khi bật ghi tham số, xác định dữ liệu nhạy cảm có thể xuất hiện và chính sách lưu trữ của tổ chức. Ưu tiên fingerprint và giá trị đã ẩn danh hoặc phân nhóm tham số khi đủ để điều tra. Không đưa mật khẩu, token hoặc dữ liệu khách hàng vào dashboard và ticket.

## 4. Gom câu SQL theo query fingerprint hoặc digest

### 4.1. Chuẩn hóa câu SQL

Query fingerprint đại diện cho cấu trúc câu lệnh thay vì từng giá trị literal. Ví dụ:

~~~sql
SELECT * FROM users WHERE email = 'a@example.test';
SELECT * FROM users WHERE email = 'b@example.test';
~~~

Có thể được gom vào cùng một mẫu:

~~~sql
SELECT * FROM users WHERE email = ?;
~~~

Tùy bộ phân tích, chuẩn hóa có thể xử lý literal, khoảng trắng, định dạng, comment hoặc cấu trúc cú pháp. Fingerprint không phải lúc nào cũng hoàn hảo: hai câu SQL có ý nghĩa hoặc kế hoạch khác nhau có thể được gom chung, trong khi hai câu tương tự có thể nhận ID khác nhau qua phiên bản DBMS.

### 4.2. Lợi ích của thống kê theo mẫu

Gom nhóm giúp tránh phải đọc hàng triệu dòng log riêng lẻ. Thay vì nhìn từng order_id, người vận hành có thể biết mẫu tra cứu đơn hàng theo khóa nào đang chạy 800.000 lần, mất tổng cộng bao nhiêu thời gian và đọc bao nhiêu trang.

Một bảng thống kê khái niệm có thể như sau:

| Fingerprint | Calls | Total time | Mean time | Rows examined | Rows returned |
|---|---:|---:|---:|---:|---:|
| Q1: lookup theo khóa | 800.000 | 3.200 s | 4 ms | 800.000 | 800.000 |
| Q2: lịch sử theo khách hàng | 40.000 | 8.000 s | 200 ms | 18 triệu | 2 triệu |
| Q3: báo cáo tổng hợp | 120 | 1.800 s | 15 s | 90 triệu | 60.000 |

Số liệu trên chỉ minh họa. Chúng cho thấy Q2 có tổng thời gian cao nhất dù thời gian trung bình thấp hơn Q3; Q1 chạy rất thường xuyên nên vẫn cần theo dõi. Rows examined lớn hơn nhiều rows returned có thể gợi ý lượng đọc dư thừa, nhưng cần xem execution plan và ngữ nghĩa truy vấn trước khi kết luận.

### 4.3. Query ID có thể thay đổi

Một số hệ thống tạo query ID từ cấu trúc nội bộ, phiên bản parser, schema hoặc thông tin khác. Query ID có thể thay đổi sau nâng cấp, thay đổi cấu trúc truy vấn hoặc thay đổi cấu hình. Khi lưu dữ liệu dài hạn, nên giữ thêm query text đã chuẩn hóa, database/schema, application name và phiên bản DBMS để có thể đối chiếu.

Không dùng query ID làm định danh nghiệp vụ vĩnh viễn. Nó là khóa nhóm hữu ích trong phạm vi cơ chế và phiên bản tạo ra nó.

### 4.4. Một fingerprint có thể che giấu khác biệt tham số

Cùng một mẫu SQL có thể chạy nhanh với khách hàng có 5 đơn hàng nhưng chậm với khách hàng có 5 triệu đơn hàng. Thống kê gộp có thể làm trung bình trông bình thường trong khi một nhóm tham số có độ trễ rất cao.

Khi cần phân tích skew, hãy lưu hoặc lấy mẫu một số đặc trưng tham số đã được ẩn danh, chẳng hạn:

- Nhóm độ chọn lọc: rất nhỏ, trung bình, rất lớn.
- Kích thước khoảng thời gian.
- Nhóm tenant hoặc phân vùng, nếu không tiết lộ danh tính.
- Số dòng ước lượng hoặc số dòng thực tế.
- Plan ID hoặc dấu hiệu kế hoạch khác nhau.

Mục tiêu là giữ đủ thông tin để phân biệt hành vi mà không lưu dữ liệu cá nhân hoặc giá trị bí mật.

## 5. Thu thập thống kê theo mẫu truy vấn

Thống kê theo mẫu thường là các bộ đếm tích lũy từ khi DBMS khởi động, từ lần reset gần nhất hoặc từ thời điểm module thống kê được bật. Cần biết rõ chu kỳ sống của số liệu trước khi so sánh.

Các chỉ số thường gặp:

| Chỉ số | Ý nghĩa | Cách sử dụng |
|---|---|---|
| Calls/count | Số lần thực thi | Tìm truy vấn tần suất cao |
| Total execution time | Tổng thời gian của các lần chạy | Tìm nhóm chiếm nhiều thời gian |
| Mean/average time | Thời gian trung bình mỗi lần | So sánh chi phí điển hình |
| Min/max time | Thời gian nhỏ nhất/lớn nhất | Nhận diện biến động, nhưng max dễ bị ảnh hưởng bởi ngoại lệ |
| Rows examined/read | Số dòng đã kiểm tra hoặc đọc | Tìm truy vấn đọc nhiều |
| Rows returned/sent | Số dòng trả về | So sánh lượng đọc với kết quả |
| Shared buffer hits/reads | Truy cập trang trong cache hoặc phải đọc vào buffer | Đánh giá áp lực bộ nhớ và I/O |
| Temp reads/writes | Đọc/ghi dữ liệu tạm | Phát hiện sort/hash spill |
| Sort rows / temp tables | Công việc sắp xếp hoặc bảng tạm | Tìm truy vấn xử lý trung gian lớn |
| Errors/retries | Lỗi và lần thử lại | Phát hiện bất ổn hoặc xung đột |

Tên trường và định nghĩa khác nhau theo DBMS. Ví dụ, rows examined của MySQL không nhất thiết tương đương chính xác với số dòng thực tế trong execution plan của PostgreSQL. Hãy đọc tài liệu phiên bản đang triển khai và giữ nhất quán cách diễn giải.

### 5.1. Calls, total time và mean time

Nếu một mẫu có calls bằng 100.000 và mean time bằng 3 ms, tổng thời gian thực thi tích lũy xấp xỉ 300 giây trong khoảng thống kê. Một mẫu khác chạy 10 lần, mỗi lần 10 giây, có tổng 100 giây. Mẫu đầu có thể là ưu tiên tối ưu cao hơn nếu tổng tài nguyên tiêu thụ là tiêu chí chính.

Công thức cơ bản:

~~~text
total execution time ≈ calls × mean execution time
mean execution time ≈ total execution time / calls
~~~

Nếu DBMS cung cấp total time trực tiếp, nên dùng số liệu đó thay vì tự tính từ mean đã làm tròn. Với truy vấn chạy song song hoặc thời gian chồng lấp, tổng thời gian truy vấn không phải thời gian đồng hồ mà cả hệ thống đã chạy; nó là lượng thời gian thực thi được cộng dồn theo cách DBMS định nghĩa.

### 5.2. Trung bình không thể thay thế phân vị

Mean time giúp so sánh chi phí trung bình, nhưng không cho biết phân bố độ trễ. Một nhóm có 99 lần chạy 2 ms và một lần chạy 2 giây có mean khoảng 22 ms; con số đó không cho biết trải nghiệm của phần lớn người dùng hay độ trễ của trường hợp xấu nhất.

Để theo dõi tail latency, dùng histogram hoặc event-level telemetry ở tầng ứng dụng/DBMS nếu có. Khi DBMS chỉ cung cấp min, max và mean theo digest, đừng suy ra p95/p99 từ những trường đó.

### 5.3. Bộ đếm tích lũy và phép đo theo khoảng

Nếu một bộ đếm tổng thời gian hiện tại là 10.000 giây, con số đó có thể tích lũy từ nhiều ngày. Để biết tốc độ tiêu thụ trong 5 phút vừa qua, cần lấy hai snapshot và tính chênh lệch:

~~~text
delta_calls = calls_snapshot_2 - calls_snapshot_1
delta_time  = total_time_snapshot_2 - total_time_snapshot_1
interval_mean = delta_time / delta_calls
~~~

Chỉ tính interval_mean khi delta_calls lớn hơn 0. Nếu DBMS reset thống kê, khởi động lại hoặc xóa đối tượng trong khoảng đo, chênh lệch có thể âm hoặc không còn so sánh được. Dashboard cần đánh dấu thời điểm reset và khoảng thời gian hợp lệ.

### 5.4. Đọc nhiều nhưng trả ít

Một mẫu truy vấn có thể đọc 200.000 dòng nhưng chỉ trả 5 dòng. Điều này gợi ý cần xem điều kiện lọc, index access, thống kê và execution plan. Với aggregation, tỷ lệ này có thể là bình thường; hãy phân biệt loại truy vấn trước khi đánh giá.

## 6. Ví dụ PostgreSQL: slow statement log và pg_stat_statements

Các ví dụ phần này dành cho PostgreSQL. Tên tham số, quyền và một số cột thống kê có thể khác theo phiên bản. Hãy kiểm tra tài liệu đúng phiên bản đang chạy trước khi áp dụng cấu hình.

### 6.1. Ghi câu lệnh vượt ngưỡng

Một cấu hình ví dụ trong postgresql.conf:

~~~conf
# Ghi những câu lệnh có thời gian thực thi vượt 250 ms.
log_min_duration_statement = 250ms

# Thêm ngữ cảnh để liên kết log với phiên và ứng dụng.
log_line_prefix = '%m [%p] db=%d user=%u app=%a '

# Tùy chọn ghi log theo mẫu ở một số phiên bản PostgreSQL.
# Cần kiểm tra tính năng và đơn vị cấu hình theo phiên bản.
# log_min_duration_sample = 500ms
# log_statement_sample_rate = 0.1
~~~

Sau khi thay đổi, một số tham số cần reload cấu hình; một số tham số khác có thể yêu cầu restart. Cần kiểm tra pg_settings và quy trình triển khai cấu hình của môi trường. Không giả định mọi thay đổi đều có hiệu lực ngay lập tức.

Có thể xem giá trị đang có hiệu lực:

~~~sql
SELECT name, setting, unit, source, pending_restart
FROM pg_settings
WHERE name IN (
  'log_min_duration_statement',
  'log_line_prefix',
  'log_min_duration_sample',
  'log_statement_sample_rate'
)
ORDER BY name;
~~~

Nếu phiên bản không hỗ trợ một tham số trong danh sách, truy vấn có thể không trả về dòng tương ứng hoặc cấu hình không hợp lệ tùy cách tham chiếu. Hãy chỉ cấu hình tham số được phiên bản đang dùng hỗ trợ.

### 6.2. Thu thập thống kê theo query ID

pg_stat_statements là extension của PostgreSQL cung cấp thống kê tổng hợp các câu lệnh đã thực thi. Extension cần được đưa vào shared_preload_libraries và được cài trong database theo hướng dẫn phiên bản. Thay đổi preload thường yêu cầu restart DBMS; không tự ý thay đổi trong giờ cao điểm khi chưa có kế hoạch vận hành.

Một truy vấn minh họa trên các phiên bản hiện đại:

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_read,
    temp_blks_written,
    query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Các cột thời gian như total_exec_time và mean_exec_time có thể khác tên ở phiên bản cũ. Một số cột hoặc hành vi thống kê cũng phụ thuộc phiên bản extension. Hãy xác nhận schema view thực tế trước khi đưa truy vấn vào dashboard.

Cách đọc:

- calls: số lần mẫu truy vấn được thực thi.
- total_exec_time: tổng thời gian thực thi được cộng dồn.
- mean_exec_time: thời gian trung bình.
- rows: số dòng kết quả cộng dồn theo cách extension ghi nhận.
- shared_blks_hit: số lần tìm thấy block trong shared buffer.
- shared_blks_read: số block phải được đọc vào shared buffer.
- temp_blks_read và temp_blks_written: hoạt động đọc/ghi block tạm.

shared_blks_read không có nghĩa chắc chắn mọi block đều phải đọc từ thiết bị vật lý; hệ điều hành hoặc tầng lưu trữ có thể có cache riêng. Hãy đối chiếu với metrics I/O của hệ thống.

### 6.3. Tính số liệu trong một khoảng

Có thể lấy snapshot định kỳ và tính delta ở hệ thống thu thập metrics. Nếu truy vấn trực tiếp hai lần, cần giữ cùng định danh thống kê và xử lý reset. Không nên xóa thống kê chỉ để làm dashboard dễ đọc vì hành động reset làm mất baseline và ảnh hưởng điều tra đang diễn ra.

Ví dụ, xem thời điểm reset và trạng thái thống kê:

~~~sql
SELECT stats_reset
FROM pg_stat_statements_info;
~~~

View thông tin và tên cột có thể thay đổi theo phiên bản. Hãy ghi nhận thời điểm reset cùng thời điểm thu thập snapshot.

### 6.4. Liên kết với execution plan

Sau khi xác định query ID có tổng thời gian hoặc số block đọc cao, lấy câu SQL đã chuẩn hóa và chọn các tham số đại diện để kiểm tra execution plan. Với PostgreSQL, EXPLAIN (ANALYZE, BUFFERS) thực sự chạy câu truy vấn; chỉ dùng khi có thể chấp nhận việc thực thi và tải phát sinh. Với câu lệnh ghi, có thể tạo thay đổi dữ liệu. Dùng môi trường thử nghiệm hoặc phương án an toàn phù hợp trước khi chạy.

## 7. Ví dụ MySQL: slow query log và Performance Schema

Các ví dụ sau dành cho MySQL. Phiên bản, quyền và cách cấu hình có thể khác nhau; cần xác minh trên môi trường triển khai.

### 7.1. Bật slow query log

Một cấu hình ví dụ trong file cấu hình MySQL:

~~~ini
[mysqld]
slow_query_log = ON
long_query_time = 0.25
log_output = FILE
min_examined_row_limit = 100
~~~

long_query_time thường được tính bằng giây. Với ví dụ này, câu lệnh vượt 0,25 giây và kiểm tra ít nhất 100 dòng mới thỏa cả hai điều kiện. Giá trị phù hợp phụ thuộc workload. Có thể dùng SHOW VARIABLES để kiểm tra cấu hình đang có hiệu lực:

~~~sql
SHOW VARIABLES
WHERE Variable_name IN (
  'slow_query_log',
  'long_query_time',
  'log_output',
  'min_examined_row_limit'
);
~~~

Một số môi trường bật log qua câu lệnh quản trị thay vì file cấu hình. Hãy tuân theo quy trình thay đổi cấu hình và quyền quản trị của tổ chức.

Tùy chọn log_queries_not_using_indexes có thể tạo ra lượng log rất lớn, vì có những truy vấn hợp lý khi scan bảng nhỏ hoặc đọc phần lớn dữ liệu. Không bật tùy chọn này một cách máy móc; nếu dùng để điều tra, hãy giới hạn thời gian và theo dõi dung lượng log.

### 7.2. Xem thống kê theo digest

MySQL Performance Schema có các bảng tổng hợp câu lệnh theo digest. Một truy vấn minh họa:

~~~sql
SELECT
    SCHEMA_NAME,
    DIGEST,
    DIGEST_TEXT,
    COUNT_STAR,
    ROUND(SUM_TIMER_WAIT / 1000000000, 2) AS total_ms,
    ROUND(AVG_TIMER_WAIT / 1000000000, 2) AS avg_ms,
    ROUND(MAX_TIMER_WAIT / 1000000000, 2) AS max_ms,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT,
    SUM_CREATED_TMP_DISK_TABLES,
    SUM_SORT_ROWS
FROM performance_schema.events_statements_summary_by_digest
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
~~~

Trong MySQL Performance Schema, timer thường được biểu diễn bằng picosecond; phép chia 1.000.000.000 chuyển picosecond sang millisecond. Cần kiểm tra định nghĩa trường của phiên bản cụ thể.

Các trường quan trọng:

- DIGEST và DIGEST_TEXT: định danh và văn bản chuẩn hóa của mẫu truy vấn.
- COUNT_STAR: số lần thực thi được tổng hợp.
- SUM_TIMER_WAIT: tổng thời gian chờ/thực thi được đo theo timer của Performance Schema.
- AVG_TIMER_WAIT, MAX_TIMER_WAIT: thời gian trung bình và lớn nhất.
- SUM_ROWS_EXAMINED, SUM_ROWS_SENT: số dòng đã kiểm tra và gửi về.
- SUM_CREATED_TMP_DISK_TABLES: số bảng tạm trên đĩa được tạo.
- SUM_SORT_ROWS: số dòng tham gia thao tác sort theo thống kê.

Tên bảng và trường có thể thay đổi giữa phiên bản hoặc cấu hình Performance Schema. Nếu bảng không có dữ liệu, kiểm tra consumer/instrument đã bật và giới hạn lưu trữ digest có phù hợp không.

### 7.3. Reset và vòng đời thống kê

Các bảng summary có thể được reset khi DBMS khởi động lại hoặc khi quản trị viên thực hiện thao tác truncate/reset theo cơ chế của Performance Schema. Trước khi reset, hãy xuất snapshot nếu cần giữ lịch sử. Không so sánh hai khoảng thời gian nếu một khoảng có reset mà không được đánh dấu.

## 8. Phân tích dữ liệu: tìm truy vấn cần ưu tiên

Khi đã có slow log và query statistics, không nên chỉ sắp xếp theo thời gian lớn nhất. Hãy dùng nhiều góc nhìn.

### 8.1. Top theo tổng thời gian

Tổng thời gian giúp tìm mẫu SQL tiêu thụ nhiều thời gian DBMS trong khoảng đo. Nó phù hợp để ưu tiên nhóm truy vấn có tác động tích lũy lớn.

Một mẫu chạy rất nhiều lần, mỗi lần chỉ vài mili giây, vẫn có thể đứng đầu. Tối ưu mẫu này có thể đem lại lợi ích tổng thể đáng kể.

### 8.2. Top theo thời gian trung bình hoặc cực đại

Mean time giúp tìm mẫu có chi phí mỗi lần cao. Max time có thể chỉ ra một lần chạy bất thường, nhưng rất nhạy với outlier. Hãy mở slow log hoặc trace tương ứng để xem thời điểm, tham số, plan và tải.

Không suy ra p95 từ max hoặc mean. Nếu cần phân vị, dùng histogram hoặc dữ liệu từng lần chạy.

### 8.3. Top theo rows examined/read và tỷ lệ đọc dư thừa

Một mẫu truy vấn có thể đọc 200.000 dòng nhưng chỉ trả 5 dòng. Điều này gợi ý cần xem điều kiện lọc và access path. Với aggregation, tỷ lệ này có thể là bình thường; hãy phân biệt loại truy vấn trước khi đánh giá.

### 8.4. Top theo I/O và dữ liệu tạm

Số block đọc, temp reads/writes, temporary tables và sort rows có thể chỉ ra truy vấn đang gây áp lực lên buffer hoặc storage. Khi thấy dữ liệu tạm lớn, xem execution plan có sort/hash operation, số dòng đầu vào và dung lượng bộ nhớ được cấp.

### 8.5. Top theo số lần chạy

Truy vấn có tần suất cao tạo chi phí lặp lại và có thể gây tải CPU, kết nối hoặc round-trip. Một truy vấn nhanh nhưng xuất hiện hàng triệu lần có thể đáng tối ưu bằng batching, cache ứng dụng hoặc giảm số lần gọi.

### 8.6. Phân tích theo application và database

Cùng một fingerprint có thể được gọi từ nhiều service hoặc job khác nhau. Hãy phân tích theo application name, database/schema, role hoặc endpoint nếu nguồn dữ liệu có hỗ trợ. Điều này giúp xác định ai tạo tải và tránh sửa nhầm phía gọi.

## 9. Quy trình vận hành thu thập và phân tích

### Bước 1: Xác định câu hỏi cần trả lời

Ví dụ: “Mẫu SQL nào chiếm nhiều thời gian DBMS nhất trong 15 phút gần đây?” hoặc “Những lần chạy p99 cao của API tra cứu có phải do DB query hay pool wait?”. Câu hỏi cụ thể giúp chọn đúng nguồn dữ liệu.

### Bước 2: Ghi nhận baseline

Trước khi thay đổi cấu hình logging, lưu lại:

- Phiên bản DBMS và cấu hình hiện tại.
- Số kết nối và mức đồng thời.
- CPU, memory, I/O, cache và wait events.
- Số liệu latency và throughput ở tầng ứng dụng.
- Thống kê query digest hiện tại và thời điểm reset.
- Dung lượng log, tốc độ phát sinh và chính sách lưu trữ.

### Bước 3: Cấu hình ngưỡng và trường log

Chọn ngưỡng dựa trên SLO, baseline và khả năng tiếp nhận log. Bổ sung thông tin định danh phiên và ứng dụng để liên kết sự kiện. Kiểm tra thay đổi có cần reload/restart và ghi lại thời điểm cấu hình có hiệu lực.

### Bước 4: Kiểm tra dữ liệu thực sự được thu thập

Chạy một truy vấn thử nghiệm có thời gian vượt ngưỡng trong môi trường phù hợp. Xác minh log có timestamp, database, application, duration và query text/fingerprint như dự kiến. Kiểm tra query statistics có tăng số calls và thời gian tương ứng.

### Bước 5: Thu snapshot định kỳ

Thu thống kê theo chu kỳ ổn định, chẳng hạn mỗi phút hoặc mỗi năm phút tùy tải và hệ thống thu thập. Lưu timestamp, thời điểm reset và các counter cần thiết. Tính delta theo từng khoảng để tránh nhầm số liệu tích lũy lâu ngày với tải hiện tại.

### Bước 6: Xếp hạng nhóm truy vấn

Xem top total time, calls, mean/max time, rows examined, buffer/I/O và temp activity. Kết hợp slow log để tìm các lần chạy cụ thể. Lọc theo database, application hoặc nhóm nghiệp vụ khi cần.

### Bước 7: Chọn mẫu đại diện và kiểm tra kế hoạch

Chọn một số lần chạy tiêu biểu, bao gồm tham số phổ biến và tham số lệch. Kiểm tra estimated rows, actual rows, access path, join, sort, I/O và wait. Nếu execution plan thay đổi theo tham số, giữ lại từng biến thể để phân tích.

### Bước 8: Đề xuất thay đổi và đo lại

Chỉ thay đổi một yếu tố có giả thuyết rõ ràng, ví dụ điều chỉnh chỉ mục, sửa SQL, cập nhật thống kê hoặc giảm số lần gọi. Đo lại cùng workload, tham số và mức đồng thời. So sánh latency phân vị, throughput, tài nguyên và tác động lên các nhóm truy vấn khác.

### Bước 9: Điều chỉnh logging và lưu trữ

Sau điều tra, đưa ngưỡng và sampling về cấu hình vận hành phù hợp. Xoay vòng log, giới hạn retention, kiểm soát quyền truy cập và xác nhận dữ liệu nhạy cảm được xử lý theo chính sách.

## 10. Liên kết slow query với metrics và traces

Một log có thể cho biết câu SQL mất 800 ms, nhưng để tìm nguyên nhân cần bối cảnh hệ thống cùng thời điểm.

Các metrics nên đối chiếu:

- CPU utilization và CPU time của DBMS.
- Memory pressure, buffer cache hit/read và temporary memory.
- Storage latency, IOPS, throughput và queue depth.
- Số connection active/idle/waiting.
- Lock waits, deadlocks và transaction duration.
- WAL/transaction log write, flush latency và replication lag.
- Throughput và latency của ứng dụng.

Trace giúp nối request ID hoặc trace ID từ API đến database call. Không phải DBMS nào cũng ghi trace ID trong slow log; ứng dụng có thể gắn application name, session attribute hoặc comment theo cơ chế phù hợp. Tránh đưa dữ liệu nhạy cảm vào SQL comment. Việc gắn correlation ID cần được thử nghiệm vì nó có thể ảnh hưởng đến query fingerprint nếu comment không được chuẩn hóa bỏ qua.

Ví dụ, tại 10:05, p99 API tăng từ 120 ms lên 1,2 giây. Slow log cho thấy một query digest tăng thời gian từ 30 ms lên 700 ms. Metrics cùng lúc ghi nhận storage latency tăng và queue depth cao. Đây là bằng chứng cho giả thuyết I/O là nguyên nhân. Nếu CPU cao và actual rows tăng đột ngột, hướng điều tra sẽ khác. Cần xem dữ liệu cùng thời điểm thay vì kết luận từ một chỉ số riêng lẻ.

## 11. Kiểm soát chi phí và rủi ro khi logging

Logging cũng tiêu tốn tài nguyên. Ghi mọi câu SQL với tham số đầy đủ có thể làm tăng I/O, CPU, dung lượng lưu trữ và chi phí xử lý log. Trước khi bật cấu hình chi tiết, cần cân nhắc:

- Tỷ lệ truy vấn vượt ngưỡng và log volume dự kiến.
- Mức overhead khi tạo, định dạng và ghi log.
- Tác động của sampling và khả năng bỏ sót sự kiện hiếm.
- Chính sách xoay vòng, retention và nén log.
- Quyền đọc log và phân quyền dashboard.
- Mã hóa khi truyền và lưu dữ liệu quan sát.
- Ẩn danh hoặc loại bỏ tham số nhạy cảm.
- Đồng bộ thời gian giữa ứng dụng, DBMS và hệ thống thu thập.
- Khả năng mất log, trễ ingest hoặc reset thống kê.

Không nên bật chế độ ghi toàn bộ câu lệnh ở hệ thống tải cao trong thời gian dài mà chưa đo overhead và dung lượng. Trong điều tra sự cố, nếu cần tăng mức log, hãy đặt khoảng thời gian và điều kiện kết thúc rõ ràng.

### 11.1. Bảo vệ dữ liệu nhạy cảm

SQL log có thể chứa literal, dữ liệu cá nhân, thông tin xác thực hoặc nội dung payload. Cần áp dụng nguyên tắc:

- Chỉ thu thập những trường cần thiết.
- Ưu tiên query fingerprint và tham số đã phân loại/ẩn danh.
- Hạn chế quyền đọc log theo vai trò.
- Đặt retention phù hợp và xóa dữ liệu hết hạn theo chính sách.
- Không gửi nguyên văn log có dữ liệu khách hàng vào kênh trao đổi không được phê duyệt.
- Kiểm tra log của proxy, driver và hệ thống APM vì chúng có thể lưu tham số độc lập với DBMS.

Ẩn tham số ở slow log không bảo đảm các lớp khác không ghi lại chúng. Cần xem toàn bộ đường đi dữ liệu quan sát.

### 11.2. Đồng bộ thời gian và chất lượng dữ liệu

Nếu đồng hồ ứng dụng và DBMS lệch nhau, sự kiện có thể bị ghép nhầm với metrics hoặc trace. Đồng bộ thời gian bằng cơ chế chuẩn của hạ tầng, giữ timezone nhất quán và lưu timestamp có múi giờ hoặc UTC.

Nếu collector bị gián đoạn, counter reset hoặc log rotation làm mất file, dashboard có thể tạo khoảng trống hoặc spike giả. Hệ thống quan sát nên ghi nhận trạng thái collector, thời điểm cuối nhận dữ liệu và cảnh báo mất ingest.

## 12. Những sai lầm thường gặp khi đọc slow log và query statistics

**Chỉ tối ưu truy vấn chậm nhất.** Truy vấn hiếm khi chạy có thể ít tác động hơn mẫu chạy thường xuyên và chiếm tổng thời gian lớn.

**Chỉ dùng mean time.** Trung bình che giấu tail latency. Cần histogram, slow log hoặc trace để xem các lần chạy bất thường.

**Cho rằng mọi câu SQL cùng fingerprint có cùng hiệu năng.** Tham số lệch, plan khác nhau và cache state có thể khiến cùng một mẫu có nhiều hành vi.

**Coi rows examined cao luôn là lỗi.** Truy vấn aggregation có thể cần đọc nhiều dòng. Phải xem loại công việc và mục tiêu nghiệp vụ.

**So sánh counter tích lũy mà quên reset.** Số liệu có thể tăng từ lúc DBMS khởi động hoặc reset gần nhất. Cần tính delta trong khoảng thời gian xác định.

**Đặt ngưỡng slow log quá cao.** Các truy vấn có độ trễ vừa phải nhưng chạy liên tục có thể không xuất hiện.

**Đặt ngưỡng quá thấp và ghi mọi câu lệnh.** Log volume và overhead có thể tăng đến mức làm hệ thống xấu đi.

**Coi EXPLAIN ANALYZE chỉ là thao tác xem.** Lệnh này thực thi truy vấn. Cần hiểu tác động, nhất là với câu lệnh ghi hoặc truy vấn nặng.

**Không liên kết log với ứng dụng.** Thiếu application name, session hoặc trace context khiến khó xác định service nào tạo tải.

**Bỏ qua dữ liệu nhạy cảm.** SQL literal và bind parameter có thể tiết lộ thông tin không nên lưu hoặc chia sẻ.

## 13. Ví dụ điều tra: API tra cứu đơn hàng tăng độ trễ

Một API lấy trạng thái đơn hàng theo order_id có p95 tăng từ 40 ms lên 350 ms. Đội vận hành thu thập slow query log với ngưỡng 200 ms và thống kê theo fingerprint trong các khoảng 5 phút.

Kết quả giả định:

| Chỉ số | Trước sự cố | Trong sự cố |
|---|---:|---:|
| Calls/5 phút | 60.000 | 61.000 |
| Mean DB time | 3 ms | 4 ms |
| Max DB time | 45 ms | 320 ms |
| Buffer reads/5 phút | 8.000 | 150.000 |
| API p95 | 40 ms | 350 ms |
| Storage read latency | 2 ms | 35 ms |

Thống kê cho thấy số lần gọi gần như không đổi và mean chỉ tăng nhẹ, nhưng max time, buffer reads, storage latency và API p95 đều tăng. Slow log cung cấp các lần chạy cụ thể vượt 200 ms. Trace giúp xác nhận phần tăng độ trễ nằm trong DB call hay ở pool/client.

Các giả thuyết cần kiểm chứng có thể gồm working set bị đẩy khỏi cache, workload scan khác cạnh tranh storage, thay đổi dữ liệu làm tăng số trang cần đọc hoặc hạ tầng storage suy giảm. Cần xem execution plan, buffer metrics và workload cùng thời điểm. Chỉ từ bảng số liệu này chưa thể kết luận nguyên nhân cuối cùng.

Sau khi xác định nguyên nhân và thực hiện điều chỉnh có kiểm soát, chạy lại cùng nhóm tham số và mức đồng thời. Kiểm tra p95/p99, total time, buffer reads, storage latency và các workload khác. Không kết luận thành công chỉ vì một lần chạy đơn lẻ nhanh hơn.

## 14. Checklist triển khai thu thập và phân tích

- [ ] Đã xác định mục tiêu quan sát và SLO liên quan chưa?
- [ ] Đã ghi nhận baseline, phiên bản DBMS và thời điểm reset thống kê chưa?
- [ ] Đã chọn ngưỡng slow log phù hợp với workload chưa?
- [ ] Đã xác định trường log cần có để liên kết query, database, user và application chưa?
- [ ] Đã kiểm tra query fingerprint/digest gom nhóm đúng chưa?
- [ ] Đã thu calls, total time, mean/max, rows read/returned và I/O chưa?
- [ ] Đã tính delta theo khoảng và phát hiện counter reset chưa?
- [ ] Đã dùng slow log để tìm lần chạy bất thường và thống kê để xếp hạng tổng tác động chưa?
- [ ] Đã xem tham số đại diện, skew và các biến thể execution plan chưa?
- [ ] Đã đối chiếu metrics, wait events và trace cùng thời điểm chưa?
- [ ] Đã đánh giá overhead, sampling, log rotation và retention chưa?
- [ ] Đã kiểm soát quyền truy cập và dữ liệu nhạy cảm trong log chưa?
- [ ] Đã đo lại workload tương đương sau thay đổi chưa?

## Kết luận

Slow query log và thống kê theo mẫu truy vấn là hai nguồn quan sát quan trọng nhưng phục vụ những câu hỏi khác nhau. Slow log ghi lại các lần thực thi vượt điều kiện để điều tra chi tiết; query fingerprint hoặc digest gom các lần chạy cùng cấu trúc để đo tần suất, tổng thời gian, thời gian trung bình, lượng dữ liệu đọc và hoạt động I/O. Kết hợp cả hai giúp tìm cả truy vấn có tail latency cao lẫn nhóm truy vấn tạo tải tích lũy lớn.

Để dữ liệu có ý nghĩa, cần chọn ngưỡng phù hợp, hiểu vòng đời counter, phân biệt mean với percentile, giữ thông tin định danh ứng dụng và liên kết log với metrics, traces cùng execution plan. Việc thu thập phải được kiểm soát về overhead, retention và dữ liệu nhạy cảm. Khi đã xác định được mẫu truy vấn cần cải thiện, hãy thay đổi có giả thuyết và đo lại trên workload đại diện để chứng minh kết quả.


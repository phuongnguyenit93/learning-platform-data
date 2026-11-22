# Nhịp tải ổn định, đột biến, theo mùa và tác vụ định kỳ

Trong tối ưu hiệu năng cơ sở dữ liệu, biết một truy vấn chạy trong bao lâu mới chỉ là một phần của bài toán. Cần hiểu truy vấn đó xuất hiện khi nào, xuất hiện bao nhiêu lần, kéo dài bao lâu, có cạnh tranh với thao tác nào và thay đổi ra sao theo giờ, ngày hoặc mùa. Cùng một câu SQL có thể chạy nhanh trong giờ thấp điểm nhưng chậm khi nhiều phiên đồng thời đọc và ghi cùng một nhóm dữ liệu.

Đặc điểm khối lượng công việc (workload characteristics) mô tả hình dạng và nhịp hoạt động của tải: tải nền ổn định, đợt tăng đột biến, chu kỳ theo giờ hoặc mùa, và các tác vụ định kỳ như tổng hợp, đồng bộ, sao lưu hay dọn dữ liệu. Nhận diện đúng những kiểu tải này giúp chọn chỉ mục, điều chỉnh SQL, lập lịch batch, bố trí tài nguyên và đặt giới hạn đồng thời phù hợp.

Mục tiêu không phải là tối ưu cho một thời điểm đo thuận lợi. Mục tiêu là để cơ sở dữ liệu đáp ứng yêu cầu nghiệp vụ trong những điều kiện tải thường gặp và cả những giai đoạn căng thẳng đã dự kiến.

## 1. Mô tả workload bằng các chiều đo

Một workload nên được mô tả bằng nhiều chiều thay vì chỉ dùng số truy vấn mỗi giây. Các chiều quan trọng gồm:

- **Tốc độ đến (arrival rate):** số yêu cầu hoặc giao dịch đến trong một đơn vị thời gian, thường biểu diễn bằng request/second hoặc transaction/second.
- **Thời gian phục vụ (service time):** thời gian cơ sở dữ liệu cần để xử lý một thao tác khi xét theo cách đo đã chọn. Cần phân biệt thời gian CPU thực sự dùng với thời gian chờ I/O, khóa hoặc tài nguyên khác.
- **Độ đồng thời (concurrency):** số yêu cầu hoặc giao dịch đang hoạt động cùng lúc. Tải có cùng arrival rate vẫn có thể tạo concurrency khác nhau nếu thời gian phục vụ khác nhau.
- **Cơ cấu thao tác:** tỷ lệ đọc, ghi, cập nhật, xóa, truy vấn tổng hợp, truy vấn nền và các thao tác quản trị.
- **Mức độ tập trung dữ liệu:** các yêu cầu có phân bố đều hay dồn vào một số khách hàng, tài khoản, sản phẩm, phân vùng hoặc hàng dữ liệu nóng.
- **Kích thước và độ phức tạp:** số hàng được đọc hoặc ghi, số bảng tham gia, lượng dữ liệu trả về, độ rộng hàng và kích thước giao dịch.
- **Tính đồng bộ theo thời gian:** các yêu cầu có đến rải đều hay cùng xuất hiện vào đầu giờ, cuối ngày, ngày chốt sổ hoặc sau một sự kiện.
- **Mức biến động dữ liệu:** dữ liệu có tăng nhanh, thay đổi thường xuyên, hay có phần lớn là lịch sử ít được truy cập.

Nên mô tả cả phân bố thời gian và phân bố truy vấn. Một workload có 80% thao tác đọc và 20% thao tác ghi có thể vẫn tạo ra nút thắt ghi nếu 20% đó cập nhật cùng một hàng hoặc buộc hệ thống flush log liên tục. Ngược lại, tỷ lệ đọc cao chưa chắc đồng nghĩa với tải nhẹ nếu mỗi lần đọc quét hàng triệu hàng.

### Bộ chỉ số tối thiểu

| Chiều đo | Chỉ số gợi ý | Câu hỏi cần trả lời |
|---|---|---|
| Tốc độ đến | Request/s, transaction/s, truy vấn/s | Tải tăng vào thời điểm nào và tăng bao nhiêu? |
| Độ trễ | p50, p95, p99, timeout | Nhóm yêu cầu chậm bị ảnh hưởng ra sao? |
| Đồng thời | Active sessions, active transactions, connection pool wait | Bao nhiêu công việc đang tranh tài nguyên? |
| Cơ cấu tải | Tỷ lệ đọc/ghi, truy vấn theo mẫu, kích thước batch | Loại công việc nào chiếm phần lớn tải? |
| CPU | CPU utilization, CPU time theo truy vấn | Tải có bị giới hạn bởi tính toán? |
| Bộ nhớ | Buffer/cache hit, memory pressure, spill | Dữ liệu nóng và vùng làm việc có vừa bộ nhớ? |
| I/O | IOPS, throughput, latency, queue depth | Lưu trữ có xử lý kịp các lần đọc/ghi? |
| Khóa và giao dịch | Lock wait, deadlock, transaction age | Các thao tác có chặn lẫn nhau? |
| Log và bản sao | Commit latency, log flush, replication lag | Đường ghi và sao chép có theo kịp? |
| Hàng đợi ứng dụng | Queue depth, oldest message age, retry | Tải đang được xử lý hay chỉ tích tụ ở phía trước DB? |

Không nên dùng một chỉ số riêng lẻ để kết luận. CPU thấp cùng độ trễ cao có thể là dấu hiệu chờ I/O, chờ khóa hoặc chờ kết nối. CPU cao có thể do truy vấn không hiệu quả, nhưng cũng có thể là workload hợp lệ đang dùng hết năng lực tính toán. Cần đối chiếu nhiều chỉ số trong cùng một khoảng thời gian.

## 2. Tải nền ổn định

Tải ổn định là workload có tốc độ đến và cơ cấu thao tác tương đối đều trong một khoảng thời gian đủ dài. Ví dụ, một hệ thống nội bộ có lượng tra cứu và cập nhật gần như giống nhau trong phần lớn giờ làm việc.

Tải ổn định giúp lập baseline và dự báo công suất. Sau khi loại bỏ thời gian khởi động hoặc làm nóng cache, có thể so sánh độ trễ, thông lượng và mức tiêu thụ tài nguyên giữa các lần triển khai.

Tuy nhiên, đường biểu diễn phẳng của tổng request/s có thể che giấu thay đổi bên trong. Ví dụ:

- Số truy vấn vẫn giữ ở 500 lần/giây nhưng tỷ lệ báo cáo tổng hợp tăng từ 5% lên 30%.
- Số giao dịch không đổi nhưng nhiều yêu cầu chuyển sang cùng cập nhật một hàng tồn kho.
- Dung lượng bảng tăng khiến cùng một truy vấn phải đọc nhiều trang hơn.
- Một chỉ mục bị phân mảnh hoặc thống kê không còn phản ánh phân bố dữ liệu.

Vì vậy, baseline nên được chia theo nhóm truy vấn hoặc loại giao dịch. Có thể nhóm theo query fingerprint (mẫu truy vấn đã chuẩn hóa), endpoint, loại nghiệp vụ hoặc job name. Tránh chỉ nhìn vào tổng số câu lệnh SQL vì một truy vấn chạy hàng nghìn lần và một truy vấn quét toàn bảng có chi phí rất khác nhau.

### Tối ưu cho tải nền

Với tải nền, các cải tiến có thể đến từ việc loại bỏ công việc lặp lại và giảm chi phí trung bình:

1. Tìm các query fingerprint chiếm nhiều tổng thời gian DB nhất, không chỉ các truy vấn có một lần chạy chậm nhất.
2. Kiểm tra kế hoạch thực thi, số hàng ước lượng và số hàng thực tế; sai lệch lớn có thể khiến bộ tối ưu chọn join hoặc đường truy cập không phù hợp.
3. Thiết kế chỉ mục theo điều kiện lọc, thứ tự sắp xếp và tần suất cập nhật của workload.
4. Giảm truy vấn N+1 và các lần đọc cùng dữ liệu lặp lại từ tầng ứng dụng.
5. Theo dõi dung lượng và tăng trưởng để nhận biết khi baseline bắt đầu trượt theo thời gian.

Một chỉ mục mới có thể làm p95 truy vấn đọc giảm nhưng đồng thời tăng thời gian ghi ở mọi giao dịch thêm hoặc sửa hàng. Do đó, sau khi điều chỉnh phải đo lại cả đọc lẫn ghi trong cùng workload.

## 3. Tải đột biến (burst) và tải tăng nhanh

Tải đột biến là giai đoạn tốc độ đến tăng mạnh trong thời gian ngắn. Ví dụ: người dùng cùng đăng nhập khi mở bán, nhiều thiết bị gửi dữ liệu sau khi mất kết nối, hoặc một thông báo đẩy khiến hàng nghìn ứng dụng cùng làm mới màn hình.

Tải đột biến có thể gây ra chuỗi phản ứng:

1. Tốc độ đến vượt tốc độ xử lý hiện tại.
2. Yêu cầu chờ trong connection pool, hàng đợi ứng dụng hoặc hàng đợi I/O.
3. Thời gian phản hồi tăng, khiến nhiều yêu cầu vẫn còn hoạt động khi yêu cầu mới tiếp tục đến.
4. Số phiên đồng thời tăng, tiêu thụ thêm bộ nhớ và tài nguyên lập lịch.
5. Timeout và retry tạo thêm yêu cầu, làm tải tăng thêm.
6. Giao dịch dài hơn giữ khóa lâu hơn, khiến các giao dịch khác phải chờ.

Đây là lý do hệ thống có thể chuyển từ trạng thái hoạt động bình thường sang quá tải rất nhanh. Khi độ trễ tăng, số yêu cầu đồng thời cũng có thể tăng dù tốc độ đến không đổi.

### Arrival rate, service time và concurrency

Trong điều kiện ổn định, định luật Little cho biết quan hệ giữa số yêu cầu trung bình đang ở trong hệ thống, tốc độ đến và thời gian lưu lại:

```text
L = λ × W
```

Trong đó:

- `L` là số yêu cầu trung bình đang nằm trong hệ thống (in-flight requests).
- `λ` là tốc độ đến trung bình.
- `W` là thời gian trung bình một yêu cầu ở trong hệ thống.

Ví dụ, nếu hệ thống nhận trung bình 200 yêu cầu/giây và mỗi yêu cầu ở trong hệ thống 0,25 giây, số yêu cầu đang hoạt động trung bình xấp xỉ 50. Nếu thời gian tăng lên 1 giây mà tốc độ đến vẫn là 200 yêu cầu/giây, con số này tăng lên khoảng 200.

Định luật Little mô tả quan hệ trung bình khi hệ thống ở trạng thái ổn định; nó không phải công thức dự báo chính xác cho một đợt burst ngắn hoặc hệ thống đang tích tụ hàng đợi. Tuy vậy, nó giúp thấy vì sao chỉ tăng số kết nối khi độ trễ tăng có thể làm tình hình tệ hơn: nhiều phiên hơn cùng tranh CPU, bộ nhớ, khóa và I/O.

### Hàng đợi và giới hạn tải

Khi tốc độ đến lớn hơn tốc độ phục vụ trong một khoảng thời gian, hàng đợi tăng. Nếu không có giới hạn, hàng đợi có thể chiếm bộ nhớ, kéo dài thời gian chờ và khiến yêu cầu hết hạn trước khi được xử lý.

Giải pháp cần phối hợp ở cả ứng dụng và cơ sở dữ liệu:

- Đặt giới hạn kết nối và số giao dịch đồng thời theo năng lực đã đo.
- Dùng hàng đợi có giới hạn và backpressure để điều tiết tốc độ đưa công việc vào DB.
- Giới hạn retry, dùng exponential backoff và jitter để các client không thử lại cùng một thời điểm.
- Cache dữ liệu đọc phổ biến nếu có quy tắc làm mới và độ trễ chấp nhận được.
- Dùng bulkhead hoặc pool riêng cho job nền để job không chiếm hết kết nối của giao dịch tương tác.
- Trả lỗi quá tải có kiểm soát hoặc trì hoãn công việc không khẩn cấp thay vì nhận vô hạn yêu cầu.

Không phải mọi burst đều cần được xử lý tức thời. Với tác vụ có thể trì hoãn, hàng đợi bền vững cho phép san phẳng tải. Nhưng cần theo dõi tuổi của công việc cũ nhất, thời gian xử lý hết backlog và khả năng hàng đợi bị tăng mãi.

### Đọc nóng và ghi nóng

Burst có thể dồn vào cùng một tập dữ liệu. Một trang sản phẩm phổ biến tạo nhiều lượt đọc vào một khóa cache; một chiến dịch bán hàng có thể khiến nhiều giao dịch cập nhật cùng bản ghi tồn kho. Hai tình huống này có đặc điểm khác nhau:

- Đọc nóng thường gây áp lực lên cache, CPU, I/O hoặc một nút đọc. Cache có thể giảm số lần truy vấn DB, nhưng cần tránh cache stampede khi một khóa hết hạn và nhiều request cùng tái tạo dữ liệu.
- Ghi nóng có thể tạo lock contention, deadlock hoặc hàng đợi log. Chia nhỏ dữ liệu, thiết kế thao tác nguyên tử, gom sự kiện hoặc phân phối cập nhật có thể hữu ích, nhưng phải giữ nguyên bất biến nghiệp vụ.

Không nên giả định tăng số read replica sẽ giải quyết được mọi burst. Replica có thể giúp phân tán đọc, nhưng không tự xử lý điểm nóng ghi trên primary; độ trễ sao chép cũng có thể khiến kết quả đọc trễ hơn.

## 4. Tải theo chu kỳ trong ngày và tuần

Nhiều hệ thống có nhịp tải lặp lại theo giờ hoặc ngày. Ví dụ:

- Nhân viên bắt đầu ca làm việc và đăng nhập vào đầu giờ.
- Khách hàng mua sắm tăng vào giờ nghỉ trưa hoặc buổi tối.
- Tác vụ đối soát chạy cuối ngày.
- Báo cáo quản trị được mở vào đầu tuần.
- Dữ liệu cảm biến được gửi dồn khi thiết bị kết nối lại.

Để nhận diện chu kỳ, cần lưu số liệu theo khoảng thời gian nhất quán, chẳng hạn mỗi phút hoặc mỗi năm phút, trong nhiều tuần. Một biểu đồ theo giờ trong một ngày có thể gợi ý mẫu hình nhưng chưa đủ để khẳng định tính lặp lại. Cần so sánh các ngày làm việc, cuối tuần, ngày lễ và thời điểm đặc biệt.

Nên giữ các chuỗi thời gian sau cùng một mốc thời gian:

- Request/s và transaction/s theo loại nghiệp vụ.
- p50, p95, p99 và tỷ lệ timeout.
- CPU, bộ nhớ, I/O và độ sâu hàng đợi.
- Số phiên hoạt động, lock wait và deadlock.
- Lịch chạy job, thời gian bắt đầu/kết thúc và lượng dữ liệu xử lý.
- Các thay đổi cấu hình, triển khai phần mềm hoặc thay đổi dữ liệu lớn.

Khi đặt các đường biểu diễn trên cùng trục thời gian, có thể phát hiện tương quan: p99 tăng ngay sau khi job báo cáo bắt đầu; I/O ghi tăng cùng lúc với tác vụ archive; hoặc connection pool wait tăng khi một endpoint bắt đầu tạo nhiều truy vấn.

Tương quan chưa chứng minh quan hệ nhân quả. Hãy xác minh bằng cách so sánh các lần job chạy, kiểm tra query fingerprint và thực hiện thử nghiệm có kiểm soát khi phù hợp.

## 5. Tải theo mùa và sự kiện nghiệp vụ

Tải theo mùa thay đổi theo chu kỳ dài hơn: cuối tháng, cuối quý, mùa mua sắm, kỳ đăng ký, mùa khai thuế hoặc thời gian có chương trình khuyến mãi. Tải mùa vụ thường khác tải đột biến ở chỗ nó có thể kéo dài nhiều giờ hoặc nhiều ngày, có lịch sử lặp lại và có thể dự báo trước.

Không nên lấy mức trung bình năm để thiết kế công suất. Nếu ngày thường có 100 giao dịch/giây nhưng cuối tháng tăng lên 600 giao dịch/giây trong nhiều giờ, hệ thống cần có kế hoạch cho khoảng tải cao đó. Cũng cần tính đến việc dữ liệu lớn hơn sau mỗi chu kỳ có thể khiến truy vấn của mùa sau tốn kém hơn mùa trước.

### Lập kế hoạch theo mùa

Một kế hoạch tốt cần:

1. Thu thập dữ liệu từ các mùa hoặc sự kiện tương tự, bao gồm đỉnh tải, thời lượng và cơ cấu truy vấn.
2. Tách tăng trưởng tự nhiên khỏi tải do chiến dịch hoặc sự kiện cụ thể.
3. Ước lượng số người dùng đồng thời, lượng dữ liệu mới và các thao tác ghi tập trung.
4. Thử tải ở mức dự kiến và mức cao hơn theo biên an toàn đã thống nhất.
5. Xác minh giới hạn kết nối, dung lượng log, IOPS, bộ nhớ và khả năng sao chép.
6. Chuẩn bị phương án giảm tải có chủ đích, chẳng hạn trì hoãn báo cáo không thiết yếu hoặc giới hạn một chức năng phụ.
7. Theo dõi sát trong sự kiện và ghi lại dữ liệu để cải thiện dự báo lần sau.

Tự động mở rộng tài nguyên có thể hữu ích, nhưng không phải lúc nào cũng theo kịp burst. Khởi tạo node, làm nóng cache, thiết lập kết nối và đồng bộ dữ liệu đều cần thời gian. Với mùa vụ đã biết trước, chuẩn bị công suất trước sự kiện thường đáng tin cậy hơn việc chờ hệ thống quá tải mới mở rộng.

## 6. Tác vụ định kỳ và tải nền theo lịch

Tác vụ định kỳ là công việc được kích hoạt theo thời gian hoặc theo lịch nghiệp vụ. Ví dụ gồm:

- Tổng hợp số liệu và tạo báo cáo.
- Đồng bộ dữ liệu từ hệ thống khác.
- Gửi hóa đơn hoặc thông báo theo lô.
- Xóa dữ liệu hết hạn, archive hoặc partition maintenance.
- Vacuum, analyze, rebuild index hoặc các tác vụ bảo trì tương ứng của hệ quản trị.
- Backup, kiểm tra backup và đồng bộ bản sao.

Những tác vụ này có thể không tạo nhiều request từ người dùng nhưng vẫn tiêu thụ CPU, RAM, I/O, băng thông và kết nối. Một job chạy lúc 02:00 có thể khiến truy vấn tương tác lúc 02:05 chậm hơn nếu job đọc toàn bảng, tạo sort lớn hoặc ghi nhiều dữ liệu.

### Tránh nhiều job dồn vào cùng một thời điểm

Nếu tất cả job đều được lập lịch lúc đầu giờ, chúng có thể tạo ra một đỉnh tải nhân tạo. Cần xem lại lịch để:

- Phân tán giờ bắt đầu (staggering) giữa các job ít phụ thuộc nhau.
- Chia batch lớn thành các lô nhỏ có thời gian nghỉ hoặc giới hạn tốc độ.
- Tránh chạy đồng thời các job cùng quét hoặc cập nhật một bảng lớn.
- Dành pool kết nối hoặc giới hạn tài nguyên riêng cho công việc nền.
- Đặt timeout, retry và checkpoint để job có thể tiếp tục sau lỗi.
- Không chạy hai phiên bản cùng một job trên cùng phạm vi dữ liệu nếu thiết kế không cho phép.

Chia batch quá nhỏ cũng có chi phí: số lần commit tăng, overhead khởi tạo truy vấn và thời gian tổng thể có thể dài hơn. Kích thước batch nên được đo bằng throughput, p95 thời gian giao dịch, lock wait, lượng log và khả năng rollback.

### Tính chất của job cần được ghi nhận

Với mỗi job, nên lưu:

| Thuộc tính | Ý nghĩa |
|---|---|
| Lịch kích hoạt | Thời điểm dự kiến, múi giờ, ngày chạy và điều kiện kích hoạt |
| Thời lượng | Thời gian chạy bình thường và thời gian ở các lần chạy chậm |
| Phạm vi dữ liệu | Bảng, phân vùng, khoảng ngày hoặc tenant được xử lý |
| Kích thước batch | Số hàng mỗi lô và tổng số hàng |
| Tài nguyên | CPU, RAM, I/O, kết nối và lượng log |
| Tính đồng thời | Job có thể chạy song song hay phải tuần tự |
| Khả năng chạy lại | Có idempotent không, checkpoint ở đâu, xử lý trùng lặp thế nào |
| Tác động nghiệp vụ | Kết quả cần hoàn tất trước thời điểm nào, có thể trì hoãn bao lâu |

Job idempotent có thể chạy lại mà không tạo ra tác dụng phụ lặp ngoài dự kiến. Đây là thuộc tính quan trọng khi dùng retry hoặc phục hồi sau lỗi. Nếu job gửi thanh toán, tạo hóa đơn hoặc phát thông báo, cần khóa idempotency hoặc bảng trạng thái xử lý phù hợp để lần chạy lại không tạo bản ghi hoặc hành động trùng.

## 7. Tương tác giữa workload tương tác và workload nền

Một cơ sở dữ liệu thường phục vụ nhiều lớp công việc cùng lúc. Giao dịch tương tác cần phản hồi nhanh; báo cáo có thể đọc nhiều hàng; job đồng bộ có thể ghi theo lô; backup cần đọc lượng dữ liệu lớn. Các loại tải này chia sẻ tài nguyên.

Ví dụ, một job tổng hợp doanh thu theo tháng có thể:

- Đọc nhiều phân vùng lịch sử, gây áp lực I/O đọc.
- Tạo hash aggregate lớn, tiêu thụ bộ nhớ và có thể spill ra đĩa.
- Giữ snapshot lâu, làm chậm quá trình dọn phiên bản cũ trong một số hệ quản trị.
- Dùng nhiều CPU, làm truy vấn tương tác phải chờ CPU.
- Chiếm connection pool nếu không có giới hạn.

Giải pháp có thể gồm chạy báo cáo trên read replica hoặc kho phân tích, giới hạn tài nguyên job, chia nhỏ phạm vi theo phân vùng và lập lịch ngoài giờ cao điểm. Tuy nhiên, replica có thể có replication lag; nếu báo cáo cần dữ liệu vừa commit, phải kiểm tra độ trễ hoặc chờ replica bắt kịp.

Phân biệt workload theo mức ưu tiên cũng hữu ích. Có thể dành phần công suất và kết nối tối thiểu cho giao dịch quan trọng, giới hạn số job nền chạy đồng thời và trì hoãn công việc có thể chờ. Việc ưu tiên cần được triển khai bằng cơ chế mà hệ thống thực sự hỗ trợ; chỉ đặt tên job là low priority không đảm bảo nó ít chiếm tài nguyên.

## 8. Hình dạng workload ảnh hưởng đến kế hoạch truy vấn và chỉ mục

Kế hoạch thực thi được chọn dựa trên thống kê và ước lượng chi phí, nhưng hiệu năng thực tế còn phụ thuộc vào cache, đồng thời và trạng thái tài nguyên tại thời điểm chạy.

Một truy vấn báo cáo có thể chạy tốt khi cache đã ấm nhưng chậm đáng kể sau khi hệ thống khởi động hoặc sau một job quét dữ liệu lớn làm thay đổi tập trang trong bộ nhớ. Một truy vấn cập nhật từng chạy nhanh có thể bị chặn trong burst nếu nhiều giao dịch cùng khóa một hàng.

Khi phân tích truy vấn, cần xem cả:

- Số lần chạy và tổng thời gian tích lũy của query fingerprint.
- Số hàng ước lượng và số hàng thực tế trong kế hoạch.
- Số trang đọc, cache hit/miss và lượng dữ liệu trung gian.
- Thời gian thực thi so với thời gian chờ khóa, I/O hoặc pool kết nối.
- Mức độ tập trung vào một số khóa hoặc phân vùng.
- Khác biệt giữa giờ cao điểm, giờ thấp điểm và lúc job chạy.

Một chỉ mục có thể có lợi cho tải đọc nền nhưng làm tăng chi phí ghi trong burst. Ví dụ, thêm chỉ mục vào cột trạng thái giúp màn hình lọc đơn hàng nhanh hơn, nhưng mỗi lần chuyển trạng thái trong đợt xử lý hàng loạt đều phải cập nhật chỉ mục. Cần đo lợi ích đọc tích lũy so với chi phí ghi phát sinh.

Thống kê cũng có thể không phản ánh đúng phân bố lệch. Nếu một trạng thái chiếm 99% hàng còn trạng thái khác chỉ chiếm 1%, ước lượng theo phân bố không đầy đủ có thể làm bộ tối ưu chọn kế hoạch không phù hợp. Cập nhật thống kê hoặc dùng thống kê mở rộng nếu hệ quản trị hỗ trợ có thể giúp, nhưng phải xác nhận bằng kế hoạch và số đo.

## 9. Cách xây dựng bộ kiểm thử tái tạo workload

Một bài kiểm thử có ích phải tái tạo được hình dạng tải quan trọng. Chỉ chạy một truy vấn lặp lại ở tốc độ cố định không mô phỏng được sự thay đổi cơ cấu giao dịch, burst hoặc job định kỳ.

### Chọn mô hình tải

- **Closed-loop:** mỗi client gửi yêu cầu tiếp theo sau khi yêu cầu trước hoàn thành. Mô hình này phù hợp để mô phỏng một số ứng dụng có số người dùng đồng thời cố định, nhưng khi hệ thống chậm, tốc độ đến cũng tự giảm.
- **Open-loop:** bộ phát tải gửi yêu cầu theo lịch độc lập với thời gian phản hồi. Mô hình này phù hợp để kiểm tra hệ thống trước một tốc độ đến mục tiêu và quan sát hàng đợi khi hệ thống không theo kịp.

Nếu chỉ dùng closed-loop, bài kiểm thử có thể che giấu quá tải vì client tự gửi ít yêu cầu hơn khi DB chậm. Với open-loop, cần kiểm soát số yêu cầu đang chờ và cách xử lý khi bộ phát tải không gửi kịp lịch, tránh tạo một bài test sai lệch do chính máy phát tải bị quá tải.

### Mẫu kịch bản

Một kịch bản kiểm thử có thể gồm:

1. Khởi động ở mức tải thấp để kiểm tra kết nối và tính đúng đắn.
2. Tăng dần lên tải nền dự kiến và giữ đủ lâu để đo trạng thái ổn định.
3. Tăng nhanh lên mức burst trong một khoảng thời gian xác định.
4. Hạ tải về nền và đo thời gian hệ thống xả hết backlog.
5. Chạy job định kỳ trong lúc tải tương tác vẫn hoạt động.
6. Lặp lại với dữ liệu lớn hơn hoặc phân bố khóa nóng hơn.
7. Thử giai đoạn cache lạnh nếu đó là điều kiện thực tế cần hỗ trợ.

Không nên chỉ ghi tổng số request gửi đi. Cần ghi số request thực sự hoàn thành, số bị timeout, số lỗi, hàng đợi còn lại và thời gian phản hồi. Khi tải đến cao hơn năng lực phục vụ, throughput hoàn thành có thể đứng yên trong khi backlog tăng nhanh.

### Ví dụ mô hình một ngày làm việc

Giả sử hệ thống đơn hàng có tải nền 120 giao dịch/giây, tăng lên 450 giao dịch/giây trong 15 phút đầu chương trình bán hàng, và chạy job tổng hợp mỗi giờ. Một bài test có thể tái tạo:

- 30 phút ở tải nền để đo baseline.
- 15 phút tăng tải lên 450 giao dịch/giây, trong đó 70% đọc đơn hàng và 30% tạo/cập nhật đơn.
- Chạy job tổng hợp ở phút thứ 10 của giai đoạn burst để kiểm tra tranh chấp tài nguyên.
- Hạ tải về nền và đo thời gian backlog trở về 0.
- So sánh p95/p99, lock wait, I/O latency, CPU, pool wait và replication lag với mục tiêu.

Các con số trong ví dụ là giả định cho bài kiểm thử. Hệ thống thực tế phải dùng số liệu quan sát được và yêu cầu SLO của chính nó.

## 10. Đọc kết quả và tìm nguyên nhân

Khi workload thay đổi, hãy tìm mối quan hệ giữa tốc độ đến, thời gian phục vụ, hàng đợi và tài nguyên:

| Quan sát | Nguyên nhân có thể | Cách kiểm tra tiếp |
|---|---|---|
| Request/s tăng, throughput DB đứng yên, queue tăng | DB hoặc tài nguyên phía trước đã chạm giới hạn | Kiểm tra CPU, I/O, connection pool, giới hạn concurrency |
| p99 tăng mạnh nhưng p50 gần như không đổi | Một nhóm truy vấn, khóa hoặc phân vùng bị nóng | Phân tích query fingerprint, lock wait và phân bố khóa |
| CPU thấp, I/O latency cao | Chờ lưu trữ hoặc đọc dữ liệu không nằm trong cache | Xem IOPS, queue depth, physical reads và kích thước working set |
| CPU cao, I/O thấp | Truy vấn tốn tính toán, sort, join hoặc xử lý dữ liệu lớn | Xem CPU time theo query và kế hoạch thực thi |
| Lock wait tăng khi burst ghi | Nhiều giao dịch cùng sửa dữ liệu hoặc giữ khóa lâu | Xem transaction age, deadlock, thứ tự cập nhật và hàng nóng |
| Độ trễ tăng đúng lúc job bắt đầu | Job nền cạnh tranh tài nguyên hoặc khóa | So sánh lịch job, query fingerprint, I/O và vùng dữ liệu bị truy cập |
| Replica lag tăng sau batch ghi | Tốc độ phát log vượt tốc độ áp dụng ở replica | Kiểm tra log generation, apply rate và giới hạn mạng/đĩa |
| Hệ thống chậm sau khi cache hết hạn | Nhiều request cùng tái tạo một giá trị hoặc cache lạnh | Kiểm tra miss rate, request coalescing và warm-up |

Một đỉnh CPU trùng thời điểm với p99 tăng là manh mối, không phải bằng chứng đầy đủ. Hãy kiểm tra cùng thời điểm truy vấn nào chạy, số hàng đọc, kế hoạch thực thi và trạng thái hàng đợi.

## 11. Ví dụ tổng hợp: hệ thống bán hàng

Một hệ thống bán hàng có bốn kiểu tải:

- **Tải nền:** người dùng xem sản phẩm, tra cứu đơn và nhân viên cập nhật trạng thái.
- **Burst:** khi bắt đầu chương trình khuyến mãi, nhiều người cùng mở trang sản phẩm và đặt hàng.
- **Theo mùa:** cuối tháng có lượng đối soát, xuất hóa đơn và báo cáo tăng cao.
- **Định kỳ:** mỗi giờ đồng bộ tồn kho từ kho vận; ban đêm archive đơn cũ và backup.

Một thiết kế chỉ tối ưu trang sản phẩm có thể không chịu được burst ghi tồn kho. Một thiết kế chỉ tối ưu batch đối soát có thể làm chậm giao dịch tương tác vào cuối tháng. Cần đánh giá từng kiểu tải và cách chúng chồng lên nhau.

### Các quyết định có thể xem xét

**Đối với tải nền:** tạo chỉ mục phù hợp cho truy vấn tra cứu đơn hàng theo khách hàng và thời gian; theo dõi query fingerprint để phát hiện mẫu truy vấn có tổng thời gian cao.

**Đối với burst đọc:** cache thông tin sản phẩm ít thay đổi, làm nóng cache trước sự kiện và dùng request coalescing để nhiều client không cùng tải lại một khóa vừa hết hạn.

**Đối với burst ghi:** cập nhật tồn kho bằng câu lệnh nguyên tử có điều kiện, giới hạn số giao dịch đồng thời trên điểm nóng và đặt retry có backoff. Không dựa vào số lượng tồn kho đã cache để quyết định giao dịch cuối cùng.

**Đối với tải cuối tháng:** thử trước với dữ liệu gần kích thước cuối tháng, tách báo cáo nặng sang replica hoặc hệ thống phân tích nếu độ trễ sao chép được chấp nhận, và phân tán các batch không cần hoàn tất cùng lúc.

**Đối với job định kỳ:** đồng bộ tồn kho theo lô có giới hạn, lưu checkpoint và bảo đảm idempotent; tránh để job archive, backup và báo cáo lớn cùng bắt đầu một lúc.

Sau mỗi thay đổi, so sánh cả độ trễ tương tác, throughput ghi, lock wait, I/O, replication lag, tuổi backlog và thời gian hoàn tất job. Nếu chỉ đo truy vấn được tối ưu, có thể bỏ sót việc job bị kéo dài hoặc giao dịch ghi bị chậm hơn.

## 12. Quy trình lập hồ sơ và quản lý workload

Có thể dùng quy trình sau để duy trì hiểu biết về workload theo thời gian:

1. **Chọn cửa sổ quan sát.** Bao phủ giờ thấp điểm, giờ cao điểm, cuối tuần và các kỳ nghiệp vụ có tải khác biệt.
2. **Gắn nhãn nguồn tải.** Phân biệt request tương tác, API, batch, báo cáo, bảo trì và sao lưu.
3. **Ghi nhận phân bố theo thời gian.** Lưu tốc độ đến, throughput hoàn thành, p50/p95/p99, concurrency và queue depth.
4. **Nhóm truy vấn.** Dùng query fingerprint và loại giao dịch để tìm mẫu có tổng chi phí lớn hoặc độ trễ cao.
5. **Ghi lịch tác vụ nền.** Lưu thời gian chạy, phạm vi dữ liệu, batch size, tài nguyên và kết quả của từng job.
6. **Xác định chồng lấn.** Tìm khoảng thời gian burst, job và giao dịch tương tác cùng sử dụng một tài nguyên.
7. **Tạo workload đại diện.** Dùng mẫu truy vấn, tỷ lệ đọc/ghi, phân bố khóa và lịch tác vụ từ dữ liệu đã quan sát.
8. **Đặt mục tiêu và ngưỡng.** Xác định SLO độ trễ, throughput tối thiểu, backlog tối đa, replication lag và thời gian hoàn tất job.
9. **Đo trước và sau thay đổi.** Giữ cùng dữ liệu, kịch bản, thời gian chạy và điều kiện cache; ghi lại thay đổi cấu hình.
10. **Cập nhật hồ sơ.** Sau khi ra mắt tính năng, thay đổi dữ liệu hoặc mùa vụ, cập nhật lại mô hình tải và giả định công suất.

Hồ sơ workload không phải tài liệu tĩnh. Khi số người dùng, dữ liệu, hành vi ứng dụng hoặc lịch nghiệp vụ thay đổi, các giả định trước đây có thể không còn đúng.

## 13. Checklist đánh giá bốn kiểu tải

| Kiểu tải | Điều cần xác định | Câu hỏi kiểm chứng |
|---|---|---|
| Ổn định | Baseline, cơ cấu truy vấn, tăng trưởng dữ liệu | Độ trễ và chi phí có trượt dần theo thời gian không? |
| Đột biến | Tốc độ tăng, thời lượng, điểm nóng, giới hạn hàng đợi | Hệ thống có backpressure và phục hồi backlog không? |
| Theo mùa | Lịch lặp, đỉnh lịch sử, thay đổi dữ liệu | Công suất đã được chuẩn bị trước và thử ở mức dự kiến chưa? |
| Định kỳ | Lịch job, batch size, tài nguyên, idempotency | Job có làm ảnh hưởng SLO tương tác hoặc chạy chồng lấn không? |

## 14. Nguyên tắc ra quyết định

Hình dạng workload quyết định cách tối ưu. Với tải ổn định, hãy giảm chi phí lặp lại và theo dõi xu hướng tăng trưởng. Với burst, hãy kiểm soát concurrency, hàng đợi, retry và điểm nóng. Với tải mùa vụ, hãy dự báo và chuẩn bị công suất trước sự kiện. Với job định kỳ, hãy phân tán lịch, giới hạn tài nguyên và bảo đảm khả năng chạy lại an toàn.

Một giải pháp chỉ được xem là phù hợp khi nó cải thiện mục tiêu đã đặt ra mà không làm hỏng yêu cầu quan trọng khác. Chỉ mục giúp đọc nhanh phải được đánh giá cùng chi phí ghi; cache phải được đánh giá cùng độ mới dữ liệu; batch nhanh phải được đánh giá cùng lock wait và backlog; replica phải được đánh giá cùng replication lag.

Hãy dựa vào số đo theo thời gian, kế hoạch thực thi, thống kê và trạng thái tài nguyên để giải thích hiệu năng. Khi đã hiểu tải nào xuất hiện, vào lúc nào và cạnh tranh với tải nào, nhóm phát triển mới có thể thiết kế cơ sở dữ liệu đáp ứng ổn định các tình huống thực tế.

# Thiết kế benchmark đại diện cho dữ liệu và hành vi thực tế

Benchmark chỉ có giá trị khi nó mô phỏng đủ gần cách hệ thống sẽ được sử dụng. Một bài thử gửi cùng một yêu cầu nhỏ liên tục có thể cho thông lượng rất cao, nhưng kết quả đó không phản ánh dịch vụ khi dữ liệu có kích thước khác nhau, người dùng gửi yêu cầu đồng thời, cache thay đổi trạng thái hoặc workload chạy trên nhiều loại máy tính đám mây.

Với hệ thống compute, kết quả còn phụ thuộc CPU, bộ nhớ, GPU, lưu trữ, mạng, runtime, container, cách đặt dữ liệu và cơ chế mở rộng. Nếu dữ liệu thử quá nhỏ, toàn bộ tập dữ liệu có thể nằm trong cache; nếu payload chỉ có một kích thước, benchmark bỏ qua các trường hợp lớn; nếu tải được tạo theo cách không phù hợp, độ trễ đo được có thể thấp hơn nhiều so với trải nghiệm thực tế.

Bài học này hướng dẫn cách thiết kế benchmark dựa trên dữ liệu và hành vi sử dụng thật, từ thu thập đặc trưng workload đến tạo dữ liệu thử, phát tải, đo lường và phân tích kết quả. Sau bài học, bạn có thể:

- Mô tả workload bằng các đặc trưng có thể đo và tái tạo.
- Chọn dữ liệu thử đại diện mà vẫn bảo vệ dữ liệu nhạy cảm.
- Mô phỏng phân phối kích thước, độ lệch truy cập, tính cục bộ và thời gian đến của yêu cầu.
- Phân biệt benchmark micro, component và end-to-end.
- Chọn mô hình tải phù hợp, đo latency, throughput, lỗi và mức sử dụng tài nguyên.
- Thiết kế lần chạy có thể lặp lại, so sánh công bằng và diễn giải kết quả có ý nghĩa.

## 1. Bắt đầu bằng câu hỏi benchmark cần trả lời

Trước khi tạo dữ liệu hoặc viết script, hãy xác định quyết định mà benchmark cần hỗ trợ. Ví dụ:

- Chọn loại máy ảo hoặc cấu hình CPU/RAM cho API xử lý ảnh.
- So sánh hai loại GPU khi suy luận mô hình với các kích thước batch khác nhau.
- Xác định giới hạn thông lượng của một worker đọc dữ liệu từ object storage.
- Kiểm tra ảnh hưởng của kích thước block và độ sâu hàng đợi tới lưu trữ.
- Đánh giá thời gian khởi động và khả năng scale-out khi tải tăng đột biến.
- Xác minh cấu hình mới có đáp ứng SLO với chi phí trên mỗi tác vụ chấp nhận được không.

Một benchmark tốt có giả thuyết và tiêu chí kết luận. Ví dụ: "Với phân phối ảnh đầu vào hiện tại và 120 yêu cầu/giây, cấu hình B phải giữ p95 dưới 250 ms, tỷ lệ lỗi dưới 0,1% và chi phí trên 1.000 ảnh thấp hơn cấu hình A". Mục tiêu này rõ hơn câu "đo xem máy nào nhanh hơn".

### Chuyển yêu cầu sản phẩm thành tiêu chí đo

| Yêu cầu | Chỉ số có thể đo |
|---|---|
| Phản hồi nhanh | p50, p95, p99 latency |
| Phục vụ nhiều yêu cầu | Throughput, requests/second hoặc tasks/second |
| Xử lý dữ liệu lớn | MB/s, GB/s, records/s, images/s hoặc tokens/s |
| Không làm mất yêu cầu | Tỷ lệ lỗi, timeout, retry và dữ liệu thất bại |
| Duy trì chất lượng | Kết quả đúng, sai số, chất lượng mô hình hoặc tỷ lệ tác vụ thành công |
| Tự mở rộng tốt | Thời gian scale-out, thời gian warm-up và capacity sau scale |
| Có hiệu quả chi phí | Chi phí trên một request, một GB, một ảnh, một job hoặc một triệu token |

Phải ghi rõ điều kiện đi kèm từng chỉ số. Thông lượng 1.000 request/giây không có nhiều ý nghĩa nếu payload chỉ 1 KB, tỷ lệ lỗi cao hoặc p99 vượt giới hạn dịch vụ.

## 2. Mô tả workload bằng dữ liệu thực tế

Workload là sự kết hợp giữa dữ liệu đầu vào, cách người dùng hoặc hệ thống tạo yêu cầu, xử lý bên trong và kết quả đầu ra. Không nên mô tả workload chỉ bằng số request trung bình hoặc tổng dung lượng dữ liệu.

Một hồ sơ workload nên có các nhóm thông tin sau:

| Nhóm | Đặc trưng cần ghi nhận | Ví dụ |
|---|---|---|
| Kích thước dữ liệu | Kích thước nhỏ/trung bình/lớn, số bản ghi, số trường, độ dài nội dung | 70% ảnh dưới 300 KB, 25% từ 300 KB đến 2 MB |
| Phân phối truy cập | Khóa phổ biến, hot key, độ lệch giữa người dùng | 10% tài khoản tạo 65% lượt đọc |
| Tính cục bộ | Dữ liệu được truy cập lặp lại theo thời gian hoặc theo vùng | Một tập file nóng được đọc nhiều lần trong 15 phút |
| Tốc độ đến | Request/second, job/second, batch theo thời gian | 40 request/giây nền, tăng lên 180 trong 2 phút |
| Đồng thời | Số phiên, số worker, số kết nối đang hoạt động | 300 phiên đồng thời, 40 worker |
| Loại thao tác | Read/write, query, inference, transform, upload/download | 85% đọc, 15% ghi |
| Tương quan thao tác | Các hành động thường xuất hiện nối tiếp nhau | Đăng nhập, truy vấn, tải file, cập nhật trạng thái |
| Thời gian xử lý | Thời gian CPU, GPU, I/O, chờ dependency | 20 ms CPU, 80 ms chờ database |
| Kết quả | Kích thước đầu ra, tỷ lệ thành công, chất lượng | 1 ảnh đầu vào tạo 3 thumbnail |
| Thời điểm | Giờ cao điểm, batch ban đêm, mùa vụ, burst | Tải tăng gấp 4 lần vào cuối ngày |

### Dùng phân phối thay vì một giá trị trung bình

Giả sử API nhận file có kích thước trung bình 500 KB. Nếu benchmark chỉ dùng file 500 KB, nó không mô phỏng trường hợp phần lớn file nhỏ nhưng một tỷ lệ nhỏ file rất lớn. Các file lớn có thể làm tăng thời gian truyền, bộ nhớ đệm, thời gian giải mã và I/O.

Hãy thu thập histogram hoặc các phân vị như p50, p90, p95, p99 cho:

- Kích thước request và response.
- Số bản ghi trả về mỗi truy vấn.
- Độ dài văn bản hoặc chuỗi token.
- Kích thước batch và thời gian chạy job.
- Số lần retry và số dependency được gọi.

Phân phối có thể chia thành các bucket để dễ tạo dữ liệu thử. Ví dụ minh họa cho API ảnh:

| Bucket | Tỷ lệ giả định | Kích thước |
|---|---:|---:|
| Nhỏ | 65% | 50–300 KB |
| Vừa | 25% | 300 KB–2 MB |
| Lớn | 9% | 2–8 MB |
| Rất lớn | 1% | 8–20 MB |

Đây là phân phối minh họa. Hãy thay bằng số liệu đo được từ workload mục tiêu và giữ lại cả đuôi phân phối nếu nó có ảnh hưởng tới SLO.

### Mô hình hóa độ lệch và hot key

Trong nhiều hệ thống, dữ liệu không được truy cập đồng đều. Một số tài khoản, sản phẩm, file hoặc partition có lượng truy cập vượt trội. Nếu benchmark chọn khóa ngẫu nhiên đồng đều, cache hit ratio và tranh chấp lock có thể khác xa production.

Hãy xác định:

- Tỷ lệ truy cập vào nhóm khóa phổ biến nhất.
- Số lượng khóa duy nhất trong cửa sổ thời gian.
- Tần suất một khóa được truy cập lặp lại.
- Mức độ phân tán giữa partition, shard, tenant hoặc vùng.
- Khả năng nhiều request cùng ghi vào một khóa nóng.

Có thể dùng Zipf-like distribution hoặc lấy mẫu theo histogram thực tế để mô phỏng độ lệch. Không cần khớp chính xác mô hình toán học nếu có thể phát lại một trace đã được ẩn danh và xử lý an toàn.

### Mô phỏng tính cục bộ và cache

Benchmark với cùng một tập dữ liệu lặp lại có thể đo chủ yếu tốc độ cache. Điều này hữu ích nếu production cũng có cache nóng tương tự, nhưng không phù hợp để đánh giá lần đọc lạnh hoặc workload có working set lớn.

Nên thiết kế riêng các kịch bản:

- **Cold cache:** dữ liệu chưa có trong cache; đo lần đọc đầu và chi phí khởi tạo.
- **Warm cache:** tập dữ liệu nóng đã được nạp; đo hành vi sau khi hệ thống ổn định.
- **Working set lớn:** tổng dữ liệu thường xuyên truy cập lớn hơn cache dự kiến.
- **Skewed access:** một phần nhỏ dữ liệu được truy cập rất thường xuyên.
- **Churn:** dữ liệu nóng thay đổi theo thời gian, khiến cache phải thay thế entry.

Không xóa cache tùy tiện giữa các lần chạy nếu mục tiêu là đo production warm state. Ghi rõ trạng thái cache và cách chuẩn bị nó trong manifest của benchmark.

## 3. Thu thập dữ liệu và bảo vệ quyền riêng tư

Nguồn dữ liệu có thể đến từ trace ứng dụng, access log, metrics, query log, hàng đợi, thống kê lưu trữ hoặc tập dữ liệu nghiệp vụ đã được phê duyệt. Dữ liệu production có giá trị vì phản ánh độ lệch và tương quan thật, nhưng có thể chứa thông tin cá nhân, bí mật, token, nội dung khách hàng hoặc dữ liệu được bảo vệ.

Trước khi dùng dữ liệu:

1. Xác định chủ sở hữu dữ liệu và mục đích benchmark.
2. Chọn tập dữ liệu tối thiểu cần thiết cho câu hỏi đo kiểm.
3. Loại bỏ hoặc biến đổi thông tin định danh, token, mật khẩu, header xác thực và bí mật.
4. Ẩn danh hoặc giả danh các khóa liên kết theo cách vẫn giữ được phân phối và quan hệ cần thử.
5. Kiểm tra chính sách lưu trữ, vị trí xử lý, thời hạn giữ và quyền truy cập.
6. Chỉ cấp dữ liệu thử cho môi trường được kiểm soát và xóa theo quy trình sau khi hoàn tất.

Ẩn danh không chỉ là thay tên người dùng. URL, địa chỉ IP, timestamp chính xác, nội dung tự do và tổ hợp trường có thể nhận diện một người hoặc tổ chức. Khi không thể dùng dữ liệu thật một cách an toàn, hãy tạo dữ liệu tổng hợp có cùng cấu trúc, phân phối, độ lệch và tương quan cần thiết.

### Tạo dữ liệu tổng hợp có kiểm soát

Dữ liệu tổng hợp nên giữ các đặc trưng ảnh hưởng tới hiệu năng:

- Kích thước và độ dài trường.
- Tỷ lệ null, trường tùy chọn và giá trị hiếm.
- Phân phối khóa, mức độ lặp lại và độ lệch truy cập.
- Cấu trúc lồng nhau, cardinality và số quan hệ.
- Mức độ nén, entropy và đặc tính mã hóa.
- Kích thước output và chi phí serialize/deserialize.

Ví dụ, một JSON có 10 trường ngắn không đại diện cho một bản ghi có nhiều trường lồng nhau, mảng dài và chuỗi văn bản lớn. Hai file có cùng dung lượng cũng có thể có mức nén và chi phí parse rất khác nhau.

Khi tạo dữ liệu, cố định seed để có thể tái tạo kết quả. Nếu cần nhiều tập dữ liệu, lưu seed, phiên bản generator, tham số phân phối và checksum của tập dữ liệu đã tạo.

Ví dụ Python tạo danh sách request có kích thước theo bucket và seed cố định:

~~~python
import random

random.seed(20261122)

def sample_payload_size():
    bucket = random.random()
    if bucket < 0.65:
        return random.randint(50_000, 300_000)
    if bucket < 0.90:
        return random.randint(300_001, 2_000_000)
    if bucket < 0.99:
        return random.randint(2_000_001, 8_000_000)
    return random.randint(8_000_001, 20_000_000)

sizes = [sample_payload_size() for _ in range(100_000)]
print("count:", len(sizes))
print("min:", min(sizes))
print("max:", max(sizes))
print("mean:", round(sum(sizes) / len(sizes)))
~~~

Đoạn mã chỉ tạo kích thước mẫu, không tạo nội dung file. Trong benchmark thực tế, generator cần tạo payload có cấu trúc và đặc tính tương ứng, đồng thời tránh để thời gian tạo dữ liệu của máy phát tải trở thành nút thắt.

## 4. Mô phỏng hành vi người dùng và hệ thống

Dữ liệu chỉ là một nửa workload. Cách yêu cầu đến, thời gian chờ giữa các thao tác và mức đồng thời có thể làm thay đổi kết quả đáng kể.

### Chuỗi hành động thay vì request đơn lẻ

Một người dùng thường thực hiện nhiều hành động có liên quan. Ví dụ:

1. Mở trang hoặc đăng nhập.
2. Truy vấn danh sách.
3. Mở chi tiết một bản ghi.
4. Tải file hoặc gửi yêu cầu xử lý.
5. Cập nhật trạng thái.
6. Đăng xuất hoặc để phiên hết hạn.

Nếu benchmark chỉ gọi endpoint truy vấn danh sách, nó bỏ qua các dependency và trạng thái phát sinh từ chuỗi thao tác. Hãy mô tả tỷ lệ người dùng đi qua từng nhánh, số lần gọi, think time giữa các thao tác và dữ liệu được truyền từ bước trước sang bước sau.

### Open model và closed model

Hai mô hình phát tải phổ biến có cách tạo tải khác nhau:

- **Closed workload model:** cố định số người dùng hoặc worker đồng thời. Khi một request chậm, worker đó gửi request tiếp theo muộn hơn. Mô hình này phù hợp với hệ thống có số worker hoặc phiên đồng thời được giới hạn.
- **Open workload model:** cố định tốc độ yêu cầu đến theo thời gian, độc lập với thời gian phản hồi. Khi hệ thống chậm, request tiếp tục đến theo lịch, phù hợp để mô phỏng lưu lượng bên ngoài như API nhận traffic.

Nếu mục tiêu là đánh giá khả năng chịu tải ở một arrival rate cố định, open model thường phản ánh tốt hơn. Closed model có thể che giấu hiện tượng quá tải vì hệ thống càng chậm thì lượng request được tạo ra càng giảm. Hiện tượng sai lệch này liên quan tới *coordinated omission*: máy phát tải không ghi nhận đầy đủ thời gian chờ mà người dùng thực sẽ gặp khi yêu cầu đến đều đặn.

Không có mô hình nào đúng cho mọi workload. Với worker xử lý hàng đợi, số consumer đồng thời có thể là biến kiểm soát chính. Với dịch vụ HTTP nhận request độc lập từ khách hàng, arrival rate thường quan trọng hơn.

### Think time và nhịp sử dụng

Người dùng không gửi request liên tục không nghỉ. Họ đọc kết quả, suy nghĩ, nhập dữ liệu và chuyển trang. Think time làm thay đổi tốc độ request trên mỗi phiên và mức đồng thời.

Hãy dùng phân phối thời gian chờ thay vì một khoảng cố định nếu dữ liệu thực cho thấy người dùng có hành vi đa dạng. Đồng thời mô phỏng:

- Phiên hoạt động ngắn và dài.
- Người dùng mới và người dùng quay lại.
- Tải nền đều và burst ngắn.
- Tác vụ đồng bộ và batch bất đồng bộ.
- Retry sau lỗi hoặc timeout theo chính sách client.

### Kịch bản tải nên có nhiều hình dạng

| Kịch bản | Cách tạo tải | Câu hỏi trả lời |
|---|---|---|
| Baseline | Tải thấp, ổn định | Hệ thống hoạt động bình thường ra sao? |
| Typical load | Tải trung bình theo phân phối thường gặp | Chi phí và độ trễ ở mức sử dụng phổ biến? |
| Peak load | Tải cao trong thời gian xác định | Có giữ SLO ở giờ cao điểm không? |
| Burst | Tăng nhanh rồi giảm | Hệ thống phản ứng với đột biến thế nào? |
| Stress | Tăng vượt tải dự kiến | Điểm bão hòa và cách suy giảm có kiểm soát? |
| Soak/endurance | Tải ổn định kéo dài | Có memory leak, queue growth hoặc suy giảm theo thời gian? |
| Recovery | Giảm tải sau khi quá tải hoặc lỗi dependency | Hệ thống hồi phục nhanh và sạch đến đâu? |
| Scale test | Thay đổi số instance/worker | Autoscaling có đủ nhanh và hiệu quả? |

Không nên dùng stress test để thay thế peak test. Mục tiêu của peak là xác minh yêu cầu đã dự kiến; stress tìm giới hạn và cách hệ thống thất bại khi vượt giới hạn.

## 5. Chọn mức benchmark phù hợp

Có thể chia benchmark thành ba mức:

### Microbenchmark

Đo một thao tác nhỏ trong điều kiện kiểm soát, ví dụ:

- Thời gian parse JSON với kích thước và cấu trúc cố định.
- Tốc độ mã hóa hoặc giải mã một khối dữ liệu.
- Throughput phép toán ma trận trên GPU.
- Latency đọc block từ volume.
- Chi phí serialize một object.

Microbenchmark giúp so sánh thành phần hoặc kiểm tra một giả thuyết cụ thể. Nó thường bỏ qua network, orchestration, queue và dependency nên không đại diện cho trải nghiệm end-to-end.

### Component benchmark

Đo một thành phần gần với cách triển khai thật, ví dụ API service cùng database test, worker đọc object storage hoặc container xử lý ảnh. Component benchmark hữu ích để xác định nút thắt trong một đoạn pipeline.

### End-to-end benchmark

Đo toàn bộ đường đi của một giao dịch hoặc job từ lúc yêu cầu đến cho tới khi có kết quả cuối cùng. End-to-end cần bao gồm các thành phần thực tế như load balancer, authentication, queue, database, object storage, network và autoscaling nếu chúng nằm trong đường xử lý.

Nên kết hợp ba mức. Microbenchmark giúp hiểu nguyên nhân, component benchmark xác nhận tương tác giữa vài thành phần, end-to-end benchmark kiểm tra hệ thống có đáp ứng mục tiêu sản phẩm hay không.

## 6. Thiết kế workload cho các loại compute

Mỗi loại tài nguyên có đặc trưng cần mô phỏng riêng.

| Loại compute | Đặc trưng dữ liệu/hành vi | Chỉ số nên đo |
|---|---|---|
| CPU-bound | Kích thước bản ghi, độ phức tạp thuật toán, phân phối nhánh, số worker | Tasks/s, CPU time, utilization, p95 latency |
| Memory-bound | Working set, locality, kích thước object, allocation và garbage collection | Memory bandwidth, RSS, cache miss, GC pause |
| Storage-bound | Kích thước block, read/write mix, random/sequential, queue depth | IOPS, MB/s, p95/p99 I/O latency |
| Network-bound | Payload, số kết nối, RTT, packet size, TLS, burst | Throughput, RTT, retransmit, connection errors |
| GPU/accelerator | Model, tensor shape, batch size, precision, sequence length | Samples/s, tokens/s, GPU utilization, VRAM, latency |
| Container platform | Image size, startup time, readiness, replica count, resource limits | Time-to-ready, throttling, restart, scale latency |
| Serverless | Invocation rate, payload, execution duration, concurrency, cold start | Duration, cold-start latency, concurrency, cost/invocation |

### CPU-bound

Dữ liệu phải đủ đa dạng để phản ánh nhánh xử lý và mức độ tính toán. Một tập đầu vào đơn giản có thể khiến compiler hoặc runtime tối ưu hóa quá mức. Hãy kiểm tra cả một luồng và nhiều luồng, mức đồng thời, context switching, CPU throttling và mức sử dụng CPU thực tế.

### Memory-bound

Kích thước working set cần được so sánh với RAM, LLC cache và các cache khác. Nếu toàn bộ dữ liệu nằm trong cache, kết quả không đại diện cho trường hợp working set lớn. Ghi lại allocation rate, garbage collection, page fault, swap và mức sử dụng bộ nhớ đỉnh.

### Storage-bound

Đừng chỉ đo tuần tự một file lớn nếu workload thật thực hiện nhiều truy cập ngẫu nhiên nhỏ. Cần mô phỏng block size, read/write ratio, queue depth, số client, filesystem, cache policy và durability setting. Nếu ứng dụng cần fsync hoặc xác nhận ghi bền vững, benchmark phải bật hành vi tương ứng.

### Network-bound

Payload lớn có thể đo thông lượng, trong khi payload nhỏ với nhiều kết nối đo chi phí per-request và packet processing. RTT, TLS handshake, connection reuse, DNS và retry đều có thể ảnh hưởng. Máy phát tải nên đặt ở vị trí mạng tương tự người dùng hoặc workload thật.

### GPU và bộ tăng tốc

Benchmark GPU cần dùng tensor shape, độ dài chuỗi, batch size và precision đại diện. Nếu suy luận mô hình, hãy phân biệt prefill và decode khi phù hợp, đo cả latency mỗi yêu cầu lẫn tokens/second. Với huấn luyện, giữ dataset, số bước, optimizer, precision và chiến lược phân tán giống nhau. Theo dõi VRAM, memory bandwidth, GPU utilization và thời gian chờ CPU/data loader.

## 7. Chuẩn bị môi trường benchmark công bằng

Kết quả chỉ có thể so sánh khi các điều kiện được kiểm soát và ghi lại. Một cấu hình benchmark nên bao gồm:

- Loại instance, số vCPU, RAM, GPU, dung lượng VRAM và topology thiết bị.
- Region/zone, loại network interface, bandwidth và vị trí máy phát tải.
- Loại volume, IOPS/throughput provisioned, filesystem và mount option.
- Hệ điều hành, kernel, driver, runtime, thư viện và container image digest.
- Phiên bản ứng dụng, cấu hình thread/worker, resource request/limit và autoscaling policy.
- Trạng thái cache, dataset version, seed và cách nạp dữ liệu.
- Phiên bản công cụ benchmark, script, cấu hình arrival rate và thời lượng chạy.

### Tránh để máy phát tải trở thành nút thắt

Máy phát tải phải có đủ CPU, RAM, network và socket để tạo lưu lượng mục tiêu. Nếu generator đạt 100% CPU, thông lượng đo được sẽ phản ánh giới hạn của generator thay vì hệ thống được thử.

Hãy theo dõi riêng:

- CPU và memory của generator.
- Network bandwidth và packet drop.
- Số kết nối và giới hạn file descriptor.
- Event loop lag hoặc thời gian tạo request.
- Tỷ lệ request được gửi đúng lịch so với arrival rate dự kiến.

Với tải lớn, có thể cần nhiều generator. Khi đó, phân chia workload có seed riêng và tổng hợp kết quả từ tất cả generator. Tránh đặt tất cả generator trên cùng host hoặc cùng network bottleneck với hệ thống đang đo nếu điều đó không phản ánh kiến trúc thật.

### Cố định phiên bản và cấu hình

Không thay đổi đồng thời instance type, kernel, ứng dụng và dataset rồi kết luận nguyên nhân từ một biến. Khi so sánh hai cấu hình, chỉ thay đổi yếu tố đang đánh giá và giữ các yếu tố còn lại tương đương. Nếu không thể giữ giống hệt, ghi rõ khác biệt và giới hạn của phép so sánh.

## 8. Quy trình chạy benchmark

Một lần chạy có thể chia thành các giai đoạn:

1. **Preflight:** xác minh môi trường, dữ liệu, quyền truy cập, dung lượng và dependency.
2. **Warm-up:** nạp ứng dụng, JIT compilation, model weights, connection pool và cache theo mục tiêu thử nghiệm.
3. **Ramp-up:** tăng tải từ từ tới mức mục tiêu, tránh tạo một burst khởi động không đại diện.
4. **Measurement:** giữ tải theo kịch bản và thu thập metrics, logs, traces.
5. **Ramp-down:** giảm tải có kiểm soát và chờ queue xử lý xong.
6. **Cooldown:** xác minh tài nguyên và dữ liệu đã trở về trạng thái mong đợi.
7. **Repeat:** chạy lại đủ số lần để đánh giá biến thiên.

Thời gian warm-up và đo phụ thuộc workload. Benchmark latency ngắn có thể cần nhiều vòng lặp; benchmark soak có thể kéo dài hàng giờ. Ghi lại chính xác cửa sổ đo để các kết quả có thể so sánh.

### Không trộn warm-up với thời gian đo

Lần chạy đầu có thể bao gồm tải image, nạp model, tạo cache, mở kết nối hoặc biên dịch JIT. Nếu mục tiêu là steady-state throughput, tách thời gian này khỏi cửa sổ đo. Nếu mục tiêu là cold start hoặc thời gian scale-out, phải đo riêng và không loại bỏ nó khỏi kết quả.

### Lặp lại và thứ tự thử nghiệm

Chạy nhiều lần và giữ nguyên điều kiện. Nếu có thể, luân phiên thứ tự cấu hình A/B để giảm ảnh hưởng từ biến động hạ tầng theo thời gian. Ghi lại lỗi và lần chạy bất thường; không âm thầm loại bỏ kết quả chỉ vì nó không phù hợp với kỳ vọng. Nếu loại một lần chạy, cần nêu lý do khách quan như generator crash hoặc thay đổi hạ tầng ngoài kế hoạch.

## 9. Thu thập và diễn giải chỉ số

### Latency và phân vị

Latency là thời gian từ mốc bắt đầu đến mốc kết thúc đã định nghĩa. Hãy thống nhất đo từ client hay server và có bao gồm queue, network, serialization, authentication hoặc retry không.

- **p50:** trải nghiệm trung vị.
- **p90/p95:** thể hiện phần đuôi mà nhiều người dùng gặp phải.
- **p99/p99.9:** giúp thấy các request chậm hiếm nhưng có thể ảnh hưởng nghiêm trọng.

Không lấy trung bình của p95 từ nhiều máy để ra p95 toàn cụm. Cần tổng hợp histogram hoặc raw sample theo cách thống kê đúng. Trung bình latency có thể che giấu tail latency.

### Throughput và tỷ lệ lỗi

Throughput phải tính trên số tác vụ hoàn thành thành công, không chỉ số request đã gửi. Ghi nhận request timeout, retry, HTTP 4xx/5xx, job thất bại, output sai và tác vụ bị bỏ.

Nếu hệ thống trả lỗi nhanh, throughput tổng có thể tăng trong khi throughput thành công giảm. Vì vậy, luôn báo cáo throughput thành công cùng tỷ lệ lỗi.

### Saturation và tài nguyên

Thu thập CPU utilization, CPU throttling, memory RSS, page fault, swap, GC pause, disk IOPS/throughput/latency, network bandwidth/retransmit, GPU utilization và VRAM. Theo dõi cả hàng đợi nội bộ và số kết nối đang chờ.

Một dịch vụ có thể chưa đạt 100% CPU nhưng vẫn bão hòa ở connection pool, disk queue hoặc giới hạn thread. Metrics cần đủ để giải thích vì sao latency tăng.

### Chi phí trên đơn vị công việc

Đối với compute cloud, hãy quy đổi chi phí sang đơn vị công việc:

**Chi phí mỗi 1.000 tác vụ = Chi phí tài nguyên trong cửa sổ đo / Số tác vụ thành công × 1.000**

Với mô hình suy luận, có thể dùng chi phí trên một triệu token; với xử lý ảnh, chi phí trên một nghìn ảnh; với batch, chi phí trên một job hoặc một triệu bản ghi. Đưa vào phép tính cả tài nguyên phụ trợ, thời gian nhàn rỗi và thời gian khởi tạo nếu chúng phát sinh trong production.

## 10. Ví dụ công cụ: k6 mô phỏng API với tải có giai đoạn

k6 có thể tạo tải HTTP và ghi nhận latency, throughput cùng tỷ lệ lỗi. Ví dụ dưới đây dùng một endpoint giả định và tăng dần số virtual users. Nó minh họa cấu trúc script; để benchmark đại diện, cần thay payload cố định bằng tập dữ liệu đã tạo theo phân phối thực tế và chọn mô hình tải phù hợp.

~~~javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '2m', target: 20 },
    { duration: '5m', target: 80 },
    { duration: '2m', target: 120 },
    { duration: '3m', target: 0 },
  ],
  thresholds: {
    http_req_failed: ['rate<0.001'],
    http_req_duration: ['p(95)<250', 'p(99)<500'],
  },
};

export default function () {
  const payload = JSON.stringify({
    customerId: 'test-customer-0042',
    operation: 'estimate',
    items: [
      { sku: 'SKU-1001', quantity: 2 },
      { sku: 'SKU-2033', quantity: 1 },
    ],
  });

  const response = http.post(
    __ENV.BASE_URL + '/api/estimate',
    payload,
    {
      headers: { 'Content-Type': 'application/json' },
      tags: { scenario: 'estimate' },
    }
  );

  check(response, {
    'status is 200': function (r) { return r.status === 200; },
  });

  sleep(1);
}
~~~

Script này dùng mô hình VU/closed workload: mỗi virtual user chờ response rồi mới thực hiện request tiếp theo và nghỉ một giây. Nó phù hợp để minh họa số phiên đồng thời, nhưng không bảo đảm arrival rate cố định khi hệ thống chậm. Nếu cần open model, hãy dùng executor theo arrival rate của k6, ví dụ constant-arrival-rate hoặc ramping-arrival-rate, và kiểm tra dropped iterations để biết generator có phát đủ tải hay không.

Không nên chạy bài thử trực tiếp trên production nếu chưa có phê duyệt, giới hạn tải và kế hoạch dừng. Một endpoint có thể tạo dữ liệu, gửi email, tính phí hoặc kích hoạt tác vụ ngoài dự kiến. Dùng môi trường thử nghiệm, tài khoản test và dữ liệu không gây tác động tới khách hàng.

## 11. Ví dụ thiết kế benchmark cho dịch vụ xử lý ảnh

Giả sử một dịch vụ nhận ảnh, tạo thumbnail và lưu kết quả vào object storage. Nhóm cần chọn giữa hai cấu hình compute:

- Cấu hình A: 4 vCPU, 16 GB RAM.
- Cấu hình B: 8 vCPU, 32 GB RAM.

Benchmark chỉ dùng ảnh 256 KB và một worker sẽ không phản ánh workload thật. Nhóm cần mô phỏng:

1. Phân phối kích thước ảnh nhỏ/vừa/lớn theo thống kê thực tế.
2. Các định dạng ảnh và tỷ lệ ảnh có metadata hoặc độ phân giải khác nhau.
3. Tỷ lệ request tạo một thumbnail so với nhiều kích thước.
4. Số tenant, khóa object và mức độ truy cập lặp lại.
5. Tải nền, peak, burst và số upload đồng thời.
6. Thời gian đọc object, decode, resize, encode và ghi object mới.

Nhóm chạy warm-up để nạp runtime và connection pool, sau đó đo 10 phút ở typical load, 10 phút ở peak và một kịch bản burst ngắn. Chạy lặp nhiều lần trên từng cấu hình, cùng dataset version và vị trí object storage.

Các chỉ số cần so sánh:

| Chỉ số | Cấu hình A | Cấu hình B |
|---|---|---|
| Ảnh xử lý thành công/giây | Đo thực tế | Đo thực tế |
| p95/p99 thời gian xử lý | Đo thực tế | Đo thực tế |
| Tỷ lệ lỗi decode/upload | Đo thực tế | Đo thực tế |
| CPU và memory peak | Đo thực tế | Đo thực tế |
| I/O và network throughput | Đo thực tế | Đo thực tế |
| Chi phí trên 1.000 ảnh thành công | Tính từ giá và throughput | Tính từ giá và throughput |

Nếu B có thông lượng cao hơn nhưng memory peak gần giới hạn, cần kiểm tra ảnh rất lớn và concurrency cao. Nếu A đạt SLO và có chi phí thấp hơn, A có thể là lựa chọn tốt hơn cho tải nền; B có thể dùng cho batch hoặc giờ cao điểm nếu cơ chế scale phù hợp.

## 12. Ví dụ thiết kế benchmark cho suy luận mô hình AI

Giả sử một API dùng GPU để suy luận mô hình ngôn ngữ. Chỉ đo số token/giây với một prompt ngắn sẽ bỏ qua khác biệt giữa prefill và decode, độ dài ngữ cảnh, số phiên đồng thời và KV cache.

Một bộ workload nên có:

- Phân phối độ dài prompt và output, bao gồm các trường hợp đuôi dài.
- Tỷ lệ request ngắn, trung bình và dài.
- Số phiên đồng thời và arrival rate.
- Batch size hoặc dynamic batching policy.
- Precision và cấu hình quantization.
- Tỷ lệ cache hit nếu có prompt cache.
- Tải cold start và warm steady-state.
- Yêu cầu chất lượng đầu ra và giới hạn lỗi.

Đo time-to-first-token (TTFT), inter-token latency, tổng latency, input/output tokens per second, throughput theo request, GPU utilization và VRAM. Nếu dùng nhiều GPU, theo dõi communication overhead và mức sử dụng network fabric.

Đối với workload interactive, p95 TTFT và inter-token latency có thể quan trọng hơn throughput trung bình. Với batch offline, tổng số token hoàn thành mỗi giờ và chi phí mỗi triệu token có thể quan trọng hơn latency từng request.

## 13. Phân tích kết quả và xác định nút thắt

Kết quả benchmark nên trả lời ba câu hỏi:

1. Hệ thống có đạt SLO ở tải mục tiêu không?
2. Khi tăng tải, thành phần nào bão hòa trước?
3. Cấu hình nào đạt mục tiêu với chi phí và độ ổn định phù hợp?

Một số dấu hiệu:

| Quan sát | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| CPU cao, throughput không tăng | CPU saturation, lock contention hoặc quá nhiều context switch | Profile CPU, thread count, parallelism |
| CPU thấp, latency cao | I/O wait, network, queue hoặc dependency chậm | Trace request, disk/network metrics, queue depth |
| RAM tăng theo thời gian | Memory leak, cache không giới hạn hoặc queue tích tụ | Heap/RSS profile, GC, object lifetime |
| GPU utilization thấp | Data loader, CPU preprocessing hoặc batch quá nhỏ | Đo pipeline input, batch và host-to-device transfer |
| GPU utilization cao nhưng tokens/s thấp | Memory bandwidth, kernel launch, sequence length hoặc communication | Profile kernel, VRAM, precision và topology |
| Disk throughput cao nhưng latency xấu | Queue depth hoặc random I/O vượt năng lực | Kiểm tra IOPS, block size và queue |
| Tỷ lệ lỗi tăng khi burst | Capacity, connection pool hoặc rate limit | Quan sát queue, autoscaling và dependency limits |
| Generator đạt CPU/network tối đa | Máy phát tải là bottleneck | Tăng generator hoặc phân tán tải |

Không tối ưu một chỉ số riêng lẻ. Ví dụ, tăng batch có thể tăng throughput nhưng cũng tăng latency và memory. Giảm số lần xác thực có thể giảm CPU nhưng làm thay đổi yêu cầu bảo mật. Mọi tối ưu cần được đo lại trên cùng workload và kiểm tra chất lượng kết quả.

## 14. Tính lặp lại và tính tin cậy thống kê

Một kết quả đơn lẻ có thể bị ảnh hưởng bởi noisy neighbor, thay đổi network, cache, autoscaling hoặc tác vụ nền. Để kết luận đáng tin cậy:

- Chạy lặp đủ số lần; với phép đo ngắn, cần nhiều mẫu hơn phép đo dài.
- Báo cáo median và các phân vị thay vì chỉ báo cáo trung bình.
- Ghi lại min/max, độ phân tán hoặc khoảng tin cậy khi phù hợp.
- Dùng cùng cửa sổ đo và cùng điều kiện warm-up.
- Ghi lại lần chạy bị ảnh hưởng bởi sự kiện ngoài dự kiến.
- So sánh mức cải thiện với độ biến thiên tự nhiên của phép đo.

Nếu cấu hình B nhanh hơn A 2% nhưng biến thiên giữa các lần chạy là 5%, chưa đủ bằng chứng để kết luận B tốt hơn. Cần tăng số lần chạy hoặc giảm nguồn nhiễu.

### Manifest benchmark

Mỗi lần chạy nên có manifest để người khác có thể tái tạo:

~~~yaml
benchmark:
  name: image-resize-api
  dataset_version: images-v3
  dataset_checksum: sha256:replace-with-real-checksum
  seed: 20261122
  scenario: peak-load
  arrival_rate_rps: 120
  duration: 10m
  warmup: 3m
target:
  instance_type: replace-with-instance-type
  region: replace-with-region
  os_image: replace-with-image-id
  application_version: replace-with-version
  container_digest: sha256:replace-with-real-digest
measurement:
  latency_percentiles: [50, 95, 99]
  collect_cpu_memory_io_network: true
  record_errors_and_retries: true
~~~

Các giá trị replace là chỗ cần điền thông tin thực. Không dùng chuỗi giả định làm kết quả báo cáo. Manifest cần lưu cùng kết quả, script, log, metrics và phiên bản dữ liệu thử.

## 15. Những sai lầm thường gặp

1. **Chỉ dùng một payload:** bỏ qua đuôi phân phối và chi phí xử lý dữ liệu lớn.
2. **Dùng dữ liệu ngẫu nhiên đồng đều:** không tái hiện hot key, tenant lớn hoặc cache locality.
3. **Chỉ đo request đơn lẻ:** bỏ qua chuỗi thao tác, think time và dependency.
4. **Dùng closed model cho mọi tình huống:** tải giảm theo latency và có thể che giấu quá tải.
5. **Không đo generator:** kết quả bị giới hạn bởi máy phát tải.
6. **Trộn warm-up với steady-state:** kết luận sai về throughput ổn định hoặc cold start.
7. **Chỉ báo cáo trung bình:** bỏ qua tail latency và lỗi hiếm.
8. **So sánh cấu hình khác nhiều yếu tố:** không biết thay đổi nào tạo ra khác biệt.
9. **Dùng dữ liệu production chưa xử lý:** có thể làm lộ thông tin cá nhân hoặc bí mật.
10. **Không lưu seed và manifest:** không thể tái tạo hoặc kiểm chứng kết quả.
11. **Chỉ tính request đã gửi:** bỏ qua request lỗi, timeout hoặc bị generator drop.
12. **Tối ưu theo benchmark tổng hợp quá đơn giản:** cải thiện điểm số nhưng làm xấu trải nghiệm workload thật.

## 16. Checklist trước khi công bố kết quả benchmark

- [ ] Câu hỏi benchmark, giả thuyết và tiêu chí đạt được xác định rõ.
- [ ] Workload mô tả dữ liệu, phân phối kích thước, độ lệch và chuỗi hành động.
- [ ] Dữ liệu được phê duyệt, ẩn danh hoặc tạo tổng hợp an toàn.
- [ ] Dataset, seed và phiên bản generator được ghi nhận.
- [ ] Mô hình tải open/closed phù hợp với cách yêu cầu đến thực tế.
- [ ] Có baseline, typical, peak và các kịch bản cần thiết khác.
- [ ] Môi trường, instance, image, driver, runtime và network được ghi nhận.
- [ ] Generator đủ năng lực và không trở thành nút thắt.
- [ ] Warm-up, ramp-up, measurement, ramp-down và cooldown được tách rõ.
- [ ] Đo latency phân vị, throughput thành công, lỗi và saturation.
- [ ] Có nhiều lần chạy và phân tích biến thiên.
- [ ] Chi phí được quy đổi theo đơn vị công việc thành công.
- [ ] Kết quả có manifest, log, metrics và giới hạn diễn giải.

## 17. Bài tập vận dụng

Một dịch vụ xử lý tài liệu nhận trung bình 50 request/giây. 80% request xử lý file dưới 200 KB, 15% xử lý file từ 200 KB đến 3 MB và 5% xử lý file lớn hơn 3 MB. Lưu lượng tăng lên 160 request/giây vào giờ cao điểm. Một nhóm muốn so sánh hai cấu hình máy compute bằng benchmark 5 phút với một file 100 KB lặp lại.

1. Vì sao benchmark hiện tại chưa đại diện cho workload?
2. Hãy đề xuất phân phối dữ liệu thử và các hành vi truy cập cần mô phỏng.
3. Nên dùng open hay closed workload model để kiểm tra khả năng chịu 160 request/giây? Vì sao?
4. Những chỉ số nào cần đo ngoài throughput?
5. Hãy đề xuất các giai đoạn của một lần chạy benchmark và thông tin cần lưu để tái tạo kết quả.

Gợi ý: giữ đúng ba bucket kích thước theo tỷ lệ đã cho và bổ sung biến thiên nội dung, số trang/trường và loại thao tác nếu chúng ảnh hưởng tới xử lý. Dùng open arrival-rate model để kiểm tra tải đến cố định 160 request/giây; theo dõi dropped iterations để biết generator có phát đủ tải không. Đo p50/p95/p99, tỷ lệ lỗi, CPU, memory, I/O, network, queue depth và chi phí trên mỗi tài liệu thành công. Chạy warm-up, ramp-up, cửa sổ peak, ramp-down và lặp lại với cùng dataset version, seed và cấu hình.

## Kết luận

Benchmark đáng tin cậy bắt đầu từ việc hiểu dữ liệu và hành vi tạo tải trong thực tế. Hãy mô tả phân phối, độ lệch, tính cục bộ, chuỗi thao tác và nhịp yêu cầu; chọn dữ liệu thử an toàn nhưng vẫn giữ đặc trưng ảnh hưởng tới hiệu năng. Kết hợp micro, component và end-to-end benchmark, chọn mô hình tải phù hợp, kiểm soát môi trường và đo cả latency phân vị, throughput thành công, lỗi, saturation cùng chi phí. Khi lưu manifest và lặp lại có kiểm soát, kết quả sẽ đủ cơ sở để chọn cấu hình compute và tối ưu hệ thống.

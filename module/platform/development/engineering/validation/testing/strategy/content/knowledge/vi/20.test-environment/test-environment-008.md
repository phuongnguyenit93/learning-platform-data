# Phân bổ năng lực cho kiểm thử tải hoặc chạy đồng thời

Kiểm thử tải và chạy nhiều bộ kiểm thử cùng lúc đều cần tài nguyên, nhưng chúng đặt ra hai bài toán khác nhau. Kiểm thử tải cần tạo ra lượng công việc có kiểm soát để đo năng lực của hệ thống được kiểm tra. Chạy đồng thời nhiều bộ kiểm thử cần phân chia tài nguyên giữa các job để chúng không vô tình làm nhiễu kết quả hoặc gây quá tải môi trường dùng chung.

Nếu chỉ tăng số người dùng ảo hoặc số job chạy song song mà không lập ngân sách tài nguyên, bộ phát tải có thể trở thành nút thắt, database có thể hết kết nối, các test suite có thể tranh CPU hoặc dữ liệu, và kết quả đo không còn phản ánh đúng mục tiêu. Vì vậy, chiến lược môi trường cần xác định **tài nguyên nào được cấp, cho workload nào, trong thời gian nào, với giới hạn và mức dự phòng ra sao**.

## 1. Phân biệt hai bài toán năng lực

### 1.1. Năng lực tạo và điều phối tải

Đây là tài nguyên cần để tạo request, phiên người dùng, sự kiện hoặc tác vụ nền theo workload đã thiết kế. Nó có thể gồm:

- Máy hoặc container chạy load generator.
- CPU, bộ nhớ, mạng và số kết nối của generator.
- Worker, thread, event loop hoặc virtual user.
- Bộ điều phối, agent phân tán và nơi lưu kết quả.
- Dữ liệu đầu vào, file và token cần cho mỗi phiên.

Nếu generator không đủ năng lực, nó có thể phát ít request hơn cấu hình, tạo độ trễ ở phía client hoặc bỏ lỡ lịch gửi. Khi đó, nhóm có thể kết luận nhầm rằng hệ thống đích còn dư năng lực.

### 1.2. Năng lực của hệ thống được kiểm tra

Đây là tài nguyên của hệ thống đích (system under test — SUT) mà bài kiểm thử muốn đánh giá:

- CPU, bộ nhớ, disk I/O và băng thông mạng.
- Instance, pod, worker và thread pool.
- Kết nối database, connection pool, lock và I/O.
- Cache, message broker, partition và consumer.
- Quota, rate limit và giới hạn của dịch vụ bên ngoài.
- Tài nguyên lưu trữ, hàng đợi và tác vụ nền.

Trong kiểm thử tải, tài nguyên của SUT là đối tượng đo. Nhóm cần ghi lại cấu hình và giới hạn của nó để hiểu kết quả. Nếu mục tiêu là đo năng lực tối đa, không nên vô tình giới hạn SUT bởi một quota ngoài dự kiến.

### 1.3. Năng lực chạy song song các bộ kiểm thử

Đây là ngân sách để nhiều test job cùng hoạt động trên runner hoặc môi trường dùng chung. Ví dụ, pipeline có thể chạy đồng thời kiểm thử API, giao diện trình duyệt, migration dữ liệu và một bài tải. Các job cạnh tranh CPU, bộ nhớ, database connection, browser instance, tài khoản thử nghiệm, hàng đợi và quota bên ngoài.

Ba lớp tài nguyên trên có liên quan nhưng cần được lập ngân sách riêng. Một hệ thống có thể có SUT đủ lớn nhưng load generator quá nhỏ; hoặc runner đủ mạnh nhưng môi trường kiểm thử dùng chung bị các job khác chiếm tài nguyên.

## 2. Xác định mục tiêu và ranh giới phân bổ

Trước khi chia tài nguyên, hãy làm rõ câu hỏi cần trả lời:

- Cần đo tải bình thường, giờ cao điểm, burst, stress hay khả năng chịu tải kéo dài?
- Cần chạy bao nhiêu test suite đồng thời?
- Các job có dùng chung database, broker, cache hoặc tài khoản không?
- Mục tiêu là đo năng lực riêng của một dịch vụ hay toàn bộ hành trình?
- Có cần tạo tranh chấp tài nguyên có chủ đích để kiểm tra hành vi đồng thời không?
- Kết quả cần phản ánh cấu hình production hay chỉ cần kiểm tra tính đúng đắn trong môi trường tích hợp?
- Có quota, chi phí cloud hoặc giới hạn nhà cung cấp nào phải tuân thủ?

Phân biệt tải có chủ đích với tranh chấp ngoài ý muốn. Khi kiểm tra race condition, nhiều thao tác phải cùng tác động lên một tài nguyên để tạo cạnh tranh. Nhưng khi đo latency của API tìm kiếm, một job UI chạy nặng trên cùng runner có thể làm méo kết quả mà không thuộc workload mục tiêu.

Ranh giới phân bổ nên xác định rõ:

1. Tài nguyên nào thuộc generator, runner và bộ điều phối?
2. Tài nguyên nào thuộc SUT và các phụ thuộc?
3. Tài nguyên nào được chia sẻ với nhóm khác?
4. Những giới hạn nào là cứng, giới hạn nào có thể điều chỉnh?
5. Ai có quyền cấp, thay đổi hoặc thu hồi tài nguyên?

## 3. Lập danh mục tài nguyên cần quản lý

Không chỉ đếm CPU và bộ nhớ. Một bài kiểm thử có thể bị giới hạn bởi nhiều loại tài nguyên khác nhau.

| Nhóm tài nguyên | Ví dụ | Dấu hiệu thiếu hoặc tranh chấp |
|---|---|---|
| CPU | vCPU, core, quota container | CPU throttling, run queue cao, generator không đạt tốc độ gửi |
| Bộ nhớ | RAM, heap, browser memory | OOM, GC kéo dài, container bị kill |
| Mạng | Băng thông, packet rate, kết nối đồng thời | Latency mạng tăng, packet drop, socket cạn |
| Lưu trữ | IOPS, throughput, dung lượng, inode | I/O wait cao, truy vấn hoặc ghi file chậm |
| Database | Connection pool, CPU, lock, transaction | Hết connection, lock wait, deadlock, truy vấn chậm |
| Cache | Dung lượng, connection, eviction rate | Cache miss tăng, eviction liên tục, hot key |
| Message broker | Partition, consumer, throughput, queue depth | Backlog tăng, consumer lag, phân phối tải không đều |
| Runtime | Thread pool, worker, event loop, file descriptor | Thread starvation, queue nội bộ, cạn handle |
| Công cụ kiểm thử | Virtual user, browser, agent, license | Không tạo đủ phiên hoặc job phải chờ license |
| Dịch vụ bên ngoài | API quota, rate limit, sandbox transaction | HTTP 429, quota cạn, dịch vụ từ chối |
| Dữ liệu và danh tính | Tài khoản, tenant, test record, token | Va chạm dữ liệu, khóa tài khoản, ghi đè trạng thái |

Mỗi tài nguyên cần có đơn vị đo, giới hạn hiện tại, nguồn cấp và người sở hữu. Ví dụ, "database có 500 kết nối" cần làm rõ đó là giới hạn toàn database hay connection pool của một dịch vụ, và bao nhiêu kết nối đã được dành cho tác vụ nền.

## 4. Ước lượng nhu cầu trước khi phân bổ

### 4.1. Với kiểm thử tải

Ước lượng dựa trên workload model:

- Arrival rate: số request hoặc sự kiện đến trong một giây/phút.
- Concurrency: số phiên hoặc công việc đang hoạt động cùng lúc.
- Think time: thời gian người dùng chờ giữa các hành động.
- Throughput mục tiêu: số giao dịch cần hoàn tất.
- Request mix: tỷ lệ giữa các endpoint hoặc hành trình.
- Payload: kích thước request/response và dữ liệu đọc/ghi.
- Thời lượng: warm-up, ramp-up, steady state, ramp-down và soak.

Không suy ra số virtual user trực tiếp từ một con số RPS mà không xét think time và thời gian phản hồi. Trong hệ thống ổn định, định luật Little cho quan hệ trung bình:

\[
L = \lambda W
\]

Trong đó \(L\) là số công việc trung bình trong hệ thống, \(\lambda\) là tốc độ công việc hoàn tất/đến trong điều kiện ổn định, và \(W\) là thời gian trung bình một công việc ở trong hệ thống. Đây là ước lượng để kiểm tra tính hợp lý, không thay thế việc đo workload thực tế.

### 4.2. Với nhiều test job chạy đồng thời

Mỗi job có hồ sơ tài nguyên riêng. Ví dụ:

- API regression thường cần CPU và kết nối dịch vụ/database.
- UI automation cần browser process, RAM, CPU và đôi khi GPU.
- Integration test cần database, broker, schema hoặc namespace riêng.
- Batch test cần CPU, I/O và dung lượng dữ liệu lớn.
- Load test cần generator đủ mạnh, ngoài tài nguyên của SUT.

Ước lượng theo mức sử dụng quan sát được từ lần chạy thử, sau đó bổ sung dự phòng cho biến động. Không nên dùng mức yêu cầu tối thiểu của công cụ làm ngân sách cho workload thực tế.

### 4.3. Tách yêu cầu tối thiểu, mục tiêu và giới hạn

Với mỗi job, ghi ba mức:

- **Request/minimum:** mức tối thiểu để job có thể chạy ổn định.
- **Target:** mức tài nguyên dự kiến cần trong workload bình thường.
- **Limit/maximum:** giới hạn cứng để job không chiếm hết tài nguyên dùng chung.

Request quá thấp có thể khiến job bị throttling; limit quá thấp có thể làm test thất bại vì môi trường; không đặt limit có thể khiến một job chiếm hết node hoặc pool. Cần kiểm tra các giá trị này bằng số liệu thực nghiệm.

## 5. Tính ngân sách tài nguyên có dự phòng

Với mỗi loại tài nguyên \(r\), có thể lập ngân sách theo nguyên tắc:

\[
B_r = C_r - O_r - H_r
\]

Trong đó:

- \(C_r\): năng lực khả dụng của pool hoặc môi trường.
- \(O_r\): phần dành cho hệ điều hành, nền tảng, agent và dịch vụ quản lý.
- \(H_r\): phần dự phòng để hấp thụ biến động và tránh chạy sát giới hạn.
- \(B_r\): phần có thể phân bổ cho workload kiểm thử.

Với các job \(i\), tổng phần phân bổ cho cùng loại tài nguyên không nên vượt ngân sách:

\[
\sum_i A_{i,r} \leq B_r
\]

Đây là mô hình lập kế hoạch đơn giản. Thực tế cần xét tài nguyên có thể co giãn, mức sử dụng theo thời gian, quota theo namespace và các giới hạn phụ thuộc lẫn nhau. Không nên dùng một tỷ lệ dự phòng cố định cho mọi môi trường; hãy xác định từ số liệu, độ biến động và mức rủi ro.

### 5.1. Phân bổ theo trọng số

Khi nhiều job cùng dùng một pool, có thể chia ngân sách theo trọng số ưu tiên:

\[
A_i = B \times \frac{w_i}{\sum_j w_j}
\]

Trong đó \(w_i\) là trọng số của job. Trọng số có thể dựa trên mức quan trọng, thời hạn, mức tài nguyên tối thiểu hoặc giá trị của kết quả. Đây là điểm khởi đầu cho việc lập kế hoạch; sau đó phải kiểm tra giới hạn tối thiểu/tối đa của từng job.

Không nên chỉ chia đều nếu các job có nhu cầu khác nhau. Một browser suite có thể tiêu thụ nhiều RAM hơn một API suite; bài tải có thể cần generator riêng; một job migration có thể cần quyền khóa tài nguyên trong một khoảng ngắn.

### 5.2. Giữ headroom

Headroom là phần năng lực chưa cấp để hấp thụ biến động, tác vụ nền, tăng tải ngắn hạn hoặc sai số ước lượng. Nếu mọi pool luôn được cấp đến 100%, một job tăng đột ngột có thể làm tất cả job khác chậm hoặc thất bại.

Headroom cần được đặt riêng cho từng tài nguyên. CPU còn dư không giúp ích nếu database connection pool đã cạn; RAM còn dư không giải quyết được quota API đã hết.

## 6. Phân bổ năng lực cho load generator

Generator phải tạo được workload đúng như cấu hình. Khi phân tán tải trên nhiều máy hoặc agent, cần xác minh tổng tốc độ thực tế, không chỉ số virtual user đã khai báo.

### 6.1. Kiểm tra nút thắt ở phía generator

Theo dõi:

- CPU và CPU throttling của generator.
- RAM, heap, GC và số browser/process.
- Network throughput, packet drop và socket.
- File descriptor, ephemeral port và số kết nối đồng thời.
- Event loop lag, thread pool và queue nội bộ.
- Tỷ lệ request gửi thực tế so với tốc độ mục tiêu.
- Lỗi phát sinh từ client và thời gian chờ trước khi request đến SUT.

Nếu generator bị bão hòa, latency phía client có thể tăng dù SUT vẫn còn khả năng xử lý. Khi đó cần tăng số agent, giảm chi phí của script, tối ưu dữ liệu hoặc phân phối workload.

### 6.2. Phân tán tải

Có thể dùng nhiều generator khi một máy không đủ khả năng tạo tải. Khi phân tán:

- Xác định tổng arrival rate và phần tải mỗi agent chịu trách nhiệm.
- Đồng bộ đồng hồ để so sánh thời điểm và latency.
- Tránh tất cả agent dùng chung một tài khoản, khóa hoặc bản ghi.
- Kiểm tra tổng băng thông và giới hạn mạng.
- Thu thập metric từng agent và tổng hợp theo cùng khoảng thời gian.
- Xác minh không có agent nào bị nghẽn hoặc gửi thiếu tải.

Không nên tăng số agent mà không đo. Nhiều generator có thể cùng tranh tài nguyên mạng hoặc tạo áp lực lên một dịch vụ phụ thuộc theo cách không có trong mục tiêu.

### 6.3. Xác minh tải thực tế

Trước bài đo chính thức, chạy pilot ở mức tải thấp rồi tăng dần. So sánh:

- Tốc độ cấu hình với tốc độ request gửi được.
- Throughput SUT hoàn tất với arrival rate.
- Latency phía client và thời gian xử lý phía server.
- CPU/RAM/network của generator và SUT.
- Số phiên, số kết nối và lỗi client.

Nếu generator không duy trì được profile đã định, không sử dụng kết quả đó để kết luận về năng lực SUT.

## 7. Phân bổ tài nguyên cho nhiều test job chạy đồng thời

### 7.1. Chọn chiến lược chia sẻ

Có một số cách phân bổ thường gặp:

| Chiến lược | Cách hoạt động | Phù hợp khi | Rủi ro cần kiểm soát |
|---|---|---|---|
| Phân vùng tĩnh | Mỗi nhóm/job có quota hoặc pool riêng | Cần kết quả ổn định, tải có thể dự đoán | Có thể để tài nguyên nhàn rỗi ở pool này trong khi pool khác thiếu |
| Chia sẻ theo trọng số | Job nhận phần tài nguyên theo mức ưu tiên hoặc nhu cầu | Workload biến động và có nhiều nhóm | Cần theo dõi fairness và giới hạn tối đa |
| Đặt lịch theo khung giờ | Job nặng chạy ở thời điểm riêng | Môi trường hoặc phụ thuộc không thể chia sẻ an toàn | Thời gian chờ và nguy cơ lịch bị dồn |
| Semaphore/lock | Giới hạn số job cùng dùng một tài nguyên hoặc chỉ cho một job truy cập | Migration, dữ liệu dùng chung, sandbox quota | Lock bị giữ lâu hoặc job bị kẹt |
| Tự động co giãn | Tăng/giảm runner theo hàng đợi và ngân sách | Nền tảng có autoscaling và quota rõ | Khởi động chậm, chi phí tăng hoặc scale không kịp |
| Kết hợp | Pool riêng cho job nặng, phần còn lại chia sẻ | Nhiều loại workload khác nhau | Cần quy tắc điều phối và quan sát rõ |

Chọn chiến lược theo độ nhạy của kết quả và mức độ chia sẻ. Một bài đo latency cần môi trường ít nhiễu hơn một bộ smoke test thông thường.

### 7.2. Xác định giới hạn đồng thời

Giới hạn số job không nên chỉ dựa vào số runner. Một runner có thể chạy nhiều process, mỗi process tạo nhiều kết nối và browser. Cần xác định giới hạn theo tài nguyên thực:

- Số job tối đa trên mỗi node.
- Tổng CPU và RAM được cấp.
- Số browser/worker đồng thời.
- Số database connection và transaction.
- Số consumer hoặc message đang xử lý.
- Số yêu cầu đến sandbox hoặc API bên ngoài.
- Số phiên dùng chung dữ liệu hoặc tài khoản.

Có thể dùng semaphore để giới hạn tài nguyên khan hiếm. Ví dụ, chỉ cho phép hai suite cùng sử dụng sandbox thanh toán, dù runner còn dư CPU.

### 7.3. Ưu tiên và fairness

Không phải job nào cũng có mức quan trọng giống nhau. Pipeline của pull request có thể cần phản hồi nhanh; soak test có thể chạy nhiều giờ; kiểm thử phát hành có thể cần ưu tiên cao trong một cửa sổ xác định.

Chính sách điều phối nên quy định:

- Mức ưu tiên theo loại job hoặc thời điểm phát hành.
- Giới hạn tài nguyên tối đa để tránh chiếm độc quyền.
- Cách xử lý job chờ lâu.
- Khi nào có thể tạm dừng hoặc hủy job ít ưu tiên.
- Cách tránh một nhóm liên tục chiếm toàn bộ pool.
- Cách thông báo khi tài nguyên không đủ hoặc lịch bị trì hoãn.

Ưu tiên cao không có nghĩa được bỏ qua giới hạn an toàn hoặc làm sai lệch kết quả của job khác.

## 8. Cô lập môi trường và dữ liệu khi chạy đồng thời

Chạy song song an toàn cần cô lập những tài nguyên có trạng thái dùng chung:

- Namespace, container hoặc project riêng.
- Database schema, database hoặc tenant riêng.
- Queue/topic và consumer group riêng khi phù hợp.
- Bucket, thư mục hoặc prefix riêng cho tệp.
- Tài khoản, token và dữ liệu riêng cho từng job.
- Port, browser profile và session riêng.
- Định danh run ID để truy vết dữ liệu và log.

Không phải lúc nào cũng cần cô lập hoàn toàn. Nếu mục tiêu là kiểm tra khả năng xử lý đồng thời trên cùng một bản ghi, dữ liệu phải được chia sẻ có chủ đích. Khi đó cần xác định số worker, thứ tự thao tác, điều kiện tranh chấp và bất biến mong đợi.

Phân biệt:

- **Chia sẻ có chủ đích:** nhiều request cùng cập nhật một tài nguyên để kiểm tra locking, isolation, idempotency hoặc race condition.
- **Chia sẻ ngoài ý muốn:** hai test suite dùng chung tài khoản hoặc bản ghi, làm một suite thay đổi dữ liệu của suite kia.

Trường hợp thứ hai thường tạo flaky test và kết quả khó tái lập. Hãy đặt quy tắc đặt tên, cấp phát và dọn dữ liệu rõ ràng.

## 9. Bảo vệ tính hợp lệ của kết quả kiểm thử

Khi nhiều job cùng chạy, cần kiểm tra xem chúng có làm thay đổi điều kiện đo hay không.

### 9.1. Tránh nhiễu từ workload không liên quan

Trong bài đo hiệu năng, các job không thuộc profile mục tiêu có thể làm tăng CPU, I/O, network hoặc tải database. Cần:

- Dùng pool riêng hoặc tạm dừng workload cạnh tranh khi cần đo chính xác.
- Ghi nhận tất cả job đang chạy trong thời gian đo.
- Theo dõi tài nguyên cả trên generator và SUT.
- Lặp lại bài đo nếu có sự kiện ngoài dự kiến.
- Không so sánh kết quả từ hai lần chạy có điều kiện môi trường khác biệt mà không nêu rõ.

### 9.2. Phân biệt tải nền dự kiến và tải gây nhiễu

Một hệ thống production có thể luôn có scheduler, consumer, backup hoặc tác vụ nền. Nếu chúng là một phần của điều kiện sử dụng thật, nên đưa chúng vào mô hình. Nếu chúng chỉ xuất hiện do một test suite khác, cần cô lập hoặc ghi nhận như yếu tố gây nhiễu.

### 9.3. Đồng bộ thời gian và truy vết

Để phân tích nhiều job:

- Dùng thời gian đồng bộ giữa runner và SUT.
- Gắn run ID, job ID và correlation ID vào log hoặc metric.
- Thu thập số liệu theo cùng khoảng thời gian.
- Ghi phiên bản ứng dụng, cấu hình và dataset.
- Lưu trạng thái trước/sau của dữ liệu quan trọng.

Nếu không thể phân biệt request của các job, nhóm khó biết workload nào gây ra latency, lỗi hoặc backlog.

## 10. Ví dụ: phân bổ năng lực cho môi trường kiểm thử thương mại điện tử

Giả sử nhóm có một pool runner dùng chung với tổng ngân sách 40 vCPU và 96 GB RAM. Nền tảng runner và agent quản lý cần 4 vCPU/8 GB; nhóm giữ 8 vCPU/16 GB làm headroom. Phần còn lại có thể phân bổ tối đa 28 vCPU/72 GB cho các job kiểm thử theo kế hoạch.

Ví dụ phân bổ ban đầu:

| Job | CPU | RAM | Mục tiêu |
|---|---:|---:|---|
| Load generator cho hành trình mua hàng | 12 vCPU | 24 GB | Tạo workload theo arrival rate đã định |
| API regression | 8 vCPU | 16 GB | Chạy kiểm thử API và hợp đồng |
| UI automation | 4 vCPU | 12 GB | Chạy browser worker giới hạn |
| Batch/import test | 4 vCPU | 8 GB | Kiểm tra xử lý dữ liệu theo lô |
| Tổng job | 28 vCPU | 60 GB | Nằm trong ngân sách workload |

Phần RAM còn lại trong ngân sách workload và headroom không tự động được cấp cho job khác; cần theo dõi tải thực tế và các giới hạn database, mạng, browser, license. Nếu load generator cần nhiều hơn 12 vCPU để đạt tốc độ mục tiêu, nhóm phải tăng pool hoặc phân tán generator sau khi kiểm chứng, không chỉ tăng số virtual user trong cấu hình.

SUT của bài tải nằm trong một môi trường riêng có cấu hình đã ghi nhận. Trong khoảng steady state, nhóm tạm dừng các bài regression và UI không thuộc workload mục tiêu trên SUT đó. Các kiểm thử API và UI có thể chạy trên môi trường tích hợp khác để không làm nhiễu phép đo. Nếu mục tiêu là kiểm tra khả năng chia sẻ tài nguyên trong điều kiện thực tế, nhóm có thể chạy đồng thời nhưng phải đưa tải nền đó vào profile và ghi nhận riêng.

### 10.1. Điều chỉnh khi có nhiều job chờ

Nếu API regression tăng thời gian chạy, nhóm không nên tự động cấp thêm CPU mà chưa kiểm tra database connection và service quota. Nếu UI suite bị OOM, có thể giảm số browser song song hoặc tăng RAM cho pool UI. Nếu load generator CPU cao nhưng SUT còn dư, cần tăng năng lực generator. Nếu SUT CPU bão hòa đúng mức tải mục tiêu, tăng generator không giải quyết được giới hạn của SUT.

### 10.2. Tiêu chí xác nhận phân bổ phù hợp

- Generator đạt tốc độ gửi đã cấu hình và không bị bão hòa.
- SUT được chạy trong cấu hình mục tiêu đã ghi.
- Các job khác không làm nhiễu steady state ngoài dự kiến.
- Database, broker, cache và quota có đủ năng lực theo profile.
- Job chạy song song không ghi đè dữ liệu của nhau.
- Metric có thể phân biệt theo job và theo dịch vụ.
- Headroom còn đủ để hấp thụ biến động.

## 11. Theo dõi và điều chỉnh trong lúc chạy

Phân bổ tài nguyên không phải quyết định một lần. Cần theo dõi và điều chỉnh theo số liệu.

### 11.1. Chỉ số phía runner và generator

- CPU usage, throttling và run queue.
- RAM, heap, GC và số process/browser.
- Network throughput, packet loss và socket.
- Tốc độ request gửi thực tế.
- Số virtual user hoạt động và lỗi phía client.
- Thời gian chờ trong queue của runner.
- Thời gian khởi động và teardown của job.

### 11.2. Chỉ số phía SUT và phụ thuộc

- Latency p50/p90/p95/p99 theo endpoint hoặc hành trình.
- Throughput hoàn tất và error rate.
- CPU, RAM, I/O và network.
- Connection pool, lock wait, deadlock và truy vấn chậm.
- Queue depth, consumer lag và thời gian xử lý nền.
- Cache hit/miss, eviction và hot key.
- Rate limit, quota và lỗi từ nhà cung cấp.
- Saturation và thời gian phục hồi sau tải.

### 11.3. Quy tắc điều chỉnh

Khi kết quả bất thường:

1. Xác định job và tài nguyên đang bão hòa.
2. Kiểm tra generator có phát đủ tải không.
3. Kiểm tra job cạnh tranh, tác vụ nền và thay đổi cấu hình.
4. Xác định nút thắt nằm ở runner, SUT hay phụ thuộc.
5. Thay đổi một yếu tố tại một thời điểm nếu mục tiêu là phân tích nguyên nhân.
6. Ghi lại cấu hình mới và chạy lại profile có thể so sánh.

Không nên thay đồng thời CPU, số worker, database pool và arrival rate rồi kết luận một thay đổi đã giải quyết vấn đề. Cần giữ lịch sử cấu hình để so sánh.

## 12. Lập lịch và điều phối kiểm thử đồng thời

Một lịch kiểm thử tốt cần xét cả mức ưu tiên và tài nguyên khan hiếm:

- Smoke test và kiểm thử pull request có thể chạy thường xuyên với giới hạn nhỏ.
- Regression lớn có thể chia shard và chạy song song nếu dữ liệu được cô lập.
- Migration hoặc test làm thay đổi schema dùng chung thường cần khóa hoặc môi trường riêng.
- Load, stress và soak test nên có cửa sổ đã đặt trước nếu chúng ảnh hưởng đến SUT hoặc dịch vụ phụ thuộc.
- Kiểm thử dùng sandbox có quota cần giới hạn số job đồng thời.
- Triển khai phiên bản mới không nên diễn ra giữa bài đo nếu không thuộc mục tiêu.

Scheduler nên kiểm tra khả năng cấp phát trước khi khởi chạy. Nếu không đủ tài nguyên, job nên chờ, chạy ở pool khác hoặc bị từ chối với lý do rõ ràng thay vì khởi động rồi thất bại ngẫu nhiên.

Với job dài, cần có quy tắc hủy an toàn, lưu trạng thái, giải phóng lock và dọn dữ liệu. Không để job bị treo giữ tài nguyên vô thời hạn.

## 13. Tiêu chí bắt đầu, dừng và kết thúc

### 13.1. Tiêu chí bắt đầu

- Ngân sách tài nguyên và pool được xác nhận.
- Runner/generator đủ năng lực theo pilot.
- SUT ở phiên bản và cấu hình đã ghi nhận.
- Dataset, tài khoản, queue và namespace đã chuẩn bị.
- Các job cạnh tranh đã được lên lịch hoặc cô lập.
- Metric và log có thể thu thập.
- Có giới hạn dừng để bảo vệ môi trường và phụ thuộc.

### 13.2. Điều kiện dừng khẩn cấp

Có thể cần dừng khi:

- Generator hoặc SUT vượt ngưỡng tài nguyên nguy hiểm.
- Error rate hoặc latency vượt giới hạn an toàn đã định.
- Database, broker hoặc dịch vụ dùng chung bị ảnh hưởng ngoài phạm vi.
- Quota hoặc chi phí cloud tiến gần giới hạn.
- Dữ liệu thật hoặc tài khoản không đúng môi trường bị tác động.
- Không thể thu thập metric cần thiết để diễn giải kết quả.

### 13.3. Tiêu chí kết thúc

- Các workload mục tiêu đã chạy đủ thời lượng và mức tải.
- Tốc độ phát tải thực tế được xác nhận.
- Dữ liệu và trạng thái sau chạy được kiểm tra.
- Metric phía generator, SUT và phụ thuộc được lưu.
- Các job đã giải phóng tài nguyên và lock.
- Kết quả, giới hạn và sai lệch môi trường được ghi nhận.
- Mọi dữ liệu tạm đã được dọn theo quy trình.

## 14. Những sai lầm thường gặp

- **Chỉ cấp tài nguyên cho SUT mà quên generator:** generator bão hòa khiến tải thực tế thấp hơn mục tiêu.
- **Dùng số virtual user làm đại diện duy nhất:** không phản ánh arrival rate, think time và request mix.
- **Chạy tất cả test suite song song:** có thể làm nhiễu phép đo, cạn database connection hoặc ghi đè dữ liệu.
- **Chia đều tài nguyên cho mọi job:** bỏ qua nhu cầu khác nhau giữa API, UI, batch và load generator.
- **Không giữ headroom:** một biến động nhỏ có thể làm cả pool mất ổn định.
- **Chỉ theo dõi CPU:** bottleneck có thể nằm ở RAM, I/O, mạng, database, broker hoặc quota.
- **Không phân biệt giới hạn runner và SUT:** tăng runner không giải quyết được SUT đã bão hòa.
- **Chia sẻ dữ liệu ngoài ý muốn:** tạo flaky test và kết quả không thể tái lập.
- **Không đo tải gửi thực tế:** tin vào cấu hình công cụ dù generator không đạt tốc độ.
- **Không có lịch và chủ sở hữu:** job nặng có thể chạy trùng thời điểm với triển khai hoặc bài đo khác.
- **Điều chỉnh nhiều biến cùng lúc:** khó xác định nguyên nhân cải thiện hoặc suy giảm.
- **Không dọn tài nguyên sau chạy:** lock, queue, browser và dữ liệu tạm ảnh hưởng lần kiểm thử tiếp theo.

## 15. Checklist phân bổ năng lực

- [ ] Mục tiêu tải hoặc chạy song song được xác định.
- [ ] Đã tách tài nguyên generator, runner và SUT.
- [ ] Có danh mục CPU, RAM, network, I/O, database, broker, cache, quota và dữ liệu.
- [ ] Nhu cầu từng workload được ước lượng từ profile và pilot.
- [ ] Request, target, limit và headroom được xác định cho tài nguyên quan trọng.
- [ ] Tổng phân bổ không vượt ngân sách khả dụng của từng loại tài nguyên.
- [ ] Generator được kiểm tra để bảo đảm tạo đủ tải.
- [ ] Giới hạn số job đồng thời dựa trên tài nguyên thực, không chỉ số runner.
- [ ] Dữ liệu, tài khoản, namespace và queue được cô lập hoặc chia sẻ có chủ đích.
- [ ] Job ưu tiên, lịch chạy, semaphore và cơ chế hủy được quy định.
- [ ] Có metric riêng cho từng job và cho SUT.
- [ ] Có điều kiện bắt đầu, dừng khẩn cấp và kết thúc.
- [ ] Kết quả không bị nhiễu bởi job ngoài profile hoặc khác biệt môi trường không được ghi nhận.
- [ ] Có quy trình giải phóng tài nguyên và dọn dữ liệu sau chạy.

## 16. Luồng phân bổ và xác minh năng lực

~~~mermaid
flowchart TD
    A["Xác định mục tiêu và workload"]
    B["Tách generator, runner, SUT và phụ thuộc"]
    C["Kiểm kê tài nguyên và giới hạn"]
    D["Ước lượng nhu cầu từng job"]
    E["Trừ overhead và giữ headroom"]
    F["Phân bổ quota, pool, lịch và mức đồng thời"]
    G["Chạy pilot và đo mức sử dụng"]
    H{"Đạt tải mục tiêu và không gây nhiễu?"}
    I["Điều chỉnh generator, quota hoặc lịch"]
    J["Chạy chính thức và thu thập bằng chứng"]
    K["Dọn tài nguyên, đánh giá và cập nhật ngân sách"]
    A --> B --> C --> D --> E --> F --> G --> H
    H -->|Không| I --> G
    H -->|Có| J --> K
    K -. "Workload hoặc nền tảng thay đổi" .-> A
~~~

Phân bổ năng lực tốt giúp bài kiểm thử tạo đúng workload, các job dùng chung không tranh chấp ngoài dự kiến và hệ thống đích được đo trong điều kiện đã xác định. Khi ngân sách được lập theo từng loại tài nguyên, có headroom, giới hạn đồng thời, cơ chế cô lập và metric theo từng job, nhóm có thể phân biệt nút thắt của generator với giới hạn của SUT, giữ kết quả có thể tái lập và sử dụng tài nguyên kiểm thử hiệu quả hơn.

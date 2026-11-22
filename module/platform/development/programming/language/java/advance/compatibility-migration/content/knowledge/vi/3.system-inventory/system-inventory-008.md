# Ghi nhận chỉ số chức năng, độ trễ và tài nguyên làm mốc so sánh

Khi khảo sát một hệ thống trước khi nâng cấp Java hoặc thay đổi phiên bản thư viện, nhóm cần biết ứng dụng đang hoạt động như thế nào trước khi thay đổi. Một bản build thành công hoặc một lần khởi động bình thường chưa cung cấp đủ thông tin để đánh giá tác động của migration. Cần ghi nhận một bộ số liệu phản ánh cả kết quả chức năng, thời gian xử lý và tài nguyên tiêu thụ trong những điều kiện có thể lặp lại.

Bộ số liệu ban đầu được gọi là **baseline** (mốc tham chiếu). Sau migration, nhóm chạy lại các kịch bản tương đương, thu thập cùng loại chỉ số và so sánh với baseline. Việc này giúp trả lời những câu hỏi cụ thể: nghiệp vụ có còn cho kết quả đúng không, request có chậm hơn không, CPU hoặc bộ nhớ có tăng không, hệ thống có chịu được cùng mức tải không và có xuất hiện lỗi mới hay không.

Baseline không phải một con số duy nhất và cũng không phải cam kết rằng hệ thống luôn hoạt động đúng. Nó là tập hợp phép đo có kèm điều kiện thực hiện, đủ rõ để người khác có thể tái lập và hiểu được mức thay đổi quan sát được.

## 1. Vì sao cần baseline trước migration?

Nếu chỉ kiểm tra hệ thống sau khi nâng cấp, ta có thể nhìn thấy một vấn đề nhưng không biết vấn đề đó đã tồn tại từ trước hay mới xuất hiện. Ví dụ, API xử lý đơn hàng có p95 latency là 900 ms sau migration. Con số này tự nó chưa cho biết migration làm hệ thống chậm đi hay hệ thống vốn đã có độ trễ như vậy.

Khi có baseline trong cùng kịch bản, nhóm có thể đối chiếu:

- Kết quả nghiệp vụ có giống trước migration không?
- Tỷ lệ thành công, tỷ lệ lỗi và số lượng giao dịch có thay đổi không?
- Thời gian phản hồi trung vị và ở nhóm request chậm có tăng không?
- CPU, heap, garbage collection, thread và connection pool có tiêu thụ nhiều hơn không?
- Ở cùng tải đầu vào, hệ thống có giữ được throughput và độ ổn định không?
- Có xuất hiện hiện tượng mới như timeout, queue tăng, memory leak hoặc lỗi chỉ xảy ra sau thời gian chạy dài không?

Baseline đặc biệt hữu ích khi nâng JDK, Spring Boot, framework, driver database, HTTP client, ORM hoặc các thư viện có ảnh hưởng tới runtime. Một thay đổi có thể không làm mã nguồn thất bại khi biên dịch nhưng vẫn làm thay đổi hiệu năng, mặc định cấu hình hoặc cách xử lý request.

Cần ghi nhận số liệu trước khi thay đổi và giữ lại thông tin về phiên bản mã nguồn, cấu hình, dữ liệu, hạ tầng và cách tạo tải. Nếu thiếu những thông tin này, phép so sánh sau migration dễ bị sai lệch.

## 2. Ba nhóm chỉ số cần ghi nhận

Một baseline có ích nên kết hợp ba nhóm chỉ số chính. Mỗi nhóm trả lời một câu hỏi khác nhau.

| Nhóm | Câu hỏi | Ví dụ chỉ số |
|---|---|---|
| Chức năng (functional) | Hệ thống có tạo ra kết quả đúng và xử lý đủ nghiệp vụ không? | Số giao dịch thành công, tỷ lệ lỗi nghiệp vụ, số bản ghi đúng, kết quả kiểm tra invariant |
| Độ trễ và tải (latency and throughput) | Hệ thống phản hồi nhanh đến đâu và xử lý được bao nhiêu công việc? | p50, p90, p95, p99 latency, throughput, error rate, queue time |
| Tài nguyên (resource utilization) | Hệ thống cần bao nhiêu tài nguyên để xử lý cùng khối lượng công việc? | CPU, heap, allocation, GC pause, thread, connection, network và disk I/O |

Không nên chỉ chọn một chỉ số đại diện cho cả nhóm. Ví dụ, CPU giảm chưa chắc là tốt nếu throughput cũng giảm mạnh. Latency trung bình không đổi chưa chắc là tốt nếu p99 tăng cao và một nhóm người dùng phải chờ lâu hơn. Số request thành công tăng cũng chưa chứng minh kết quả nghiệp vụ chính xác nếu hệ thống tạo giao dịch trùng hoặc ghi sai dữ liệu.

Hãy xác định một tập chỉ số nhỏ nhưng đại diện cho các luồng quan trọng, sau đó bổ sung chỉ số chuyên sâu khi cần điều tra.

## 3. Ghi nhận chỉ số chức năng

Chỉ số chức năng mô tả hệ thống đã thực hiện được công việc gì và kết quả có đúng hay không. Đây là lớp quan trọng nhất vì hiệu năng tốt không có ý nghĩa nếu ứng dụng trả về kết quả sai.

### 3.1. Chọn các luồng nghiệp vụ đại diện

Bắt đầu từ các luồng chính mà ứng dụng phải duy trì sau migration. Với một hệ thống bán hàng, các luồng có thể gồm:

- Đăng nhập và xác thực người dùng.
- Tìm kiếm hoặc xem thông tin sản phẩm.
- Tạo đơn hàng.
- Tính giá, chiết khấu và thuế.
- Gửi yêu cầu thanh toán.
- Ghi nhận trạng thái đơn hàng.
- Phát và nhận sự kiện giữa các dịch vụ.
- Truy vấn lịch sử hoặc báo cáo.

Với từng luồng, mô tả đầu vào, điều kiện trước, hành động, kết quả mong đợi và tác dụng phụ. Không nên chỉ ghi “API trả về HTTP 200”, bởi một response thành công về giao thức vẫn có thể chứa dữ liệu sai hoặc thiếu một bước nghiệp vụ.

### 3.2. Định nghĩa kết quả đúng

Một kịch bản cần có tiêu chí xác định thành công. Chẳng hạn:

| Luồng | Điều kiện thành công có thể đo |
|---|---|
| Tạo đơn hàng | Có đúng một đơn hàng với mã và tổng tiền mong đợi |
| Thanh toán | Trạng thái giao dịch phù hợp với kết quả từ payment provider |
| Cập nhật tồn kho | Số lượng tồn kho thay đổi đúng một lần theo quy tắc nghiệp vụ |
| Truy vấn | Tập bản ghi, thứ tự được cam kết và nội dung trường đúng |
| Phát sự kiện | Sự kiện có schema hợp lệ và consumer xử lý đúng số lần theo semantics đã thiết kế |

Các tiêu chí nên kiểm tra cả dữ liệu trả về và trạng thái được lưu. Nếu một thao tác có thể retry, hãy xác định cách kiểm tra tính idempotent để phát hiện giao dịch trùng. Nếu một luồng bất đồng bộ, hãy xác định thời gian chờ và trạng thái cuối cùng cần đạt.

### 3.3. Các chỉ số chức năng nên thu thập

- Số lượng thao tác được gửi và số lượng hoàn tất.
- Số lượng thành công, thất bại, bị từ chối theo quy tắc nghiệp vụ và bị timeout.
- Tỷ lệ thành công trên tổng số thao tác hợp lệ.
- Số bản ghi tạo mới, cập nhật hoặc xóa.
- Số giao dịch trùng, thiếu, sai trạng thái hoặc vi phạm invariant.
- Số message được publish, consume, retry hoặc đưa vào dead-letter queue.
- Số lỗi validation và lỗi phụ thuộc bên ngoài.
- Kết quả đối chiếu dữ liệu giữa đầu vào, response và database.

Cần phân biệt lỗi nghiệp vụ dự kiến với lỗi kỹ thuật. Ví dụ, một yêu cầu thanh toán bị từ chối do không đủ số dư có thể là kết quả nghiệp vụ hợp lệ; lỗi kết nối tới payment provider lại là lỗi kỹ thuật. Nếu gộp hai trường hợp vào một tỷ lệ lỗi chung, kết luận so sánh sẽ thiếu chính xác.

### 3.4. Ví dụ về bộ đếm chức năng

Giả sử kịch bản tạo đơn hàng có 10.000 yêu cầu hợp lệ. Sau khi chạy, nhóm kiểm tra:

| Kết quả | Số lượng |
|---|---:|
| Yêu cầu gửi đi | 10.000 |
| Đơn hàng tạo đúng | 9.980 |
| Lỗi nghiệp vụ được mong đợi | 10 |
| Lỗi kỹ thuật | 8 |
| Đơn hàng trùng hoặc sai dữ liệu | 2 |

Không nên gộp tất cả thành “9.990 request không lỗi”. Hai đơn hàng sai dữ liệu vẫn là lỗi chức năng nghiêm trọng dù endpoint có thể trả response thành công. Nên lưu số lượng theo từng loại kết quả và dùng truy vấn hoặc đối soát độc lập để xác nhận dữ liệu cuối cùng.

## 4. Ghi nhận độ trễ và thông lượng

Độ trễ (latency) là thời gian cần để hoàn thành một thao tác theo điểm bắt đầu và kết thúc đã định nghĩa. Thông lượng (throughput) là lượng công việc hệ thống xử lý trong một đơn vị thời gian. Hai chỉ số này phải được đọc cùng nhau.

### 4.1. Định nghĩa điểm đo

Với API, latency end-to-end thường được đo từ lúc client bắt đầu gửi request đến khi client nhận được response hoàn chỉnh. Đây là trải nghiệm mà người gọi quan sát được.

Trong hệ thống nhiều tầng, có thể đo thêm thời gian ở từng đoạn:

~~~text
Client gửi request
       |
       v
Gateway / Load balancer
       |
       v
HTTP server và filter
       |
       v
Business service
       |
       +----> Database
       |
       +----> Remote service
       |
       v
Serialize response
       |
       v
Client nhận response
~~~

Các khoảng đo ở từng tầng giúp tìm nguyên nhân, nhưng không được cộng tùy tiện nếu chúng chồng lấn hoặc chạy song song. Hãy ghi rõ timer nào đo toàn bộ request, timer nào chỉ đo một thao tác nội bộ.

Đối với job nền, cần phân biệt thời gian xử lý một message với thời gian message nằm chờ trong queue. Đối với batch, nên ghi cả thời gian hoàn thành batch và thời gian xử lý trung bình hoặc phân vị trên mỗi item.

### 4.2. Không chỉ nhìn latency trung bình

Latency thường có phân phối lệch: phần lớn request nhanh nhưng một số request rất chậm. Vì vậy, giá trị trung bình (mean) có thể che khuất trải nghiệm của nhóm request chậm.

Các phân vị thường dùng:

| Chỉ số | Cách hiểu |
|---|---|
| p50 | 50% request hoàn tất trong thời gian bằng hoặc thấp hơn giá trị này; gần với trung vị |
| p90 | 90% request hoàn tất trong thời gian bằng hoặc thấp hơn giá trị này |
| p95 | 95% request hoàn tất trong thời gian bằng hoặc thấp hơn giá trị này |
| p99 | 99% request hoàn tất trong thời gian bằng hoặc thấp hơn giá trị này |
| max | Request chậm nhất quan sát được trong khoảng đo; nhạy với outlier và thời lượng lấy mẫu |

Ví dụ, p50 là 80 ms nhưng p99 là 1.800 ms cho thấy phần lớn request phản hồi nhanh trong khi một nhóm nhỏ bị chậm đáng kể. Nếu chỉ báo cáo mean là 140 ms, vấn đề ở đuôi phân phối có thể bị bỏ qua.

Không nên chỉ ghi p99 mà bỏ qua số mẫu. Một phép đo có vài chục request không cung cấp ước lượng p99 đáng tin cậy. Cần có đủ số request trong mỗi kịch bản và khoảng thời gian để phân vị có ý nghĩa.

### 4.3. Ghi nhận throughput và error rate

Throughput có thể biểu diễn bằng request/second, transaction/second, message/second hoặc item/second tùy loại công việc. Hãy ghi rõ đơn vị và chỉ tính công việc hoàn tất theo định nghĩa đã chọn.

Một hệ thống có thể giảm latency bằng cách xử lý ít request hơn. Vì vậy, so sánh latency phải đặt trong cùng tải đầu vào và đi kèm throughput.

Error rate cần được định nghĩa rõ, ví dụ:

~~~text
error rate = số thao tác lỗi kỹ thuật / tổng số thao tác hợp lệ
~~~

Nếu hệ thống có lỗi nghiệp vụ được mong đợi, hãy theo dõi riêng để không làm sai tỷ lệ lỗi kỹ thuật. Timeout, HTTP 5xx, lỗi kết nối và lỗi xử lý message nên có phân loại phù hợp.

### 4.4. Đo queue time và thời gian phụ thuộc

Khi request chậm, nguyên nhân có thể nằm ở thời gian chờ thread, connection, queue hoặc dịch vụ bên ngoài. Nên thu thập thêm:

- Thời gian chờ trong executor hoặc message queue.
- Thời gian lấy connection từ pool.
- Thời gian thực thi truy vấn database.
- Thời gian gọi remote API.
- Số request đang xử lý và số request đang chờ.
- Timeout, retry và số lần gọi lại.

Các chỉ số này giúp phân biệt CPU xử lý chậm với hệ thống bị nghẽn do thiếu connection hoặc dịch vụ phụ thuộc phản hồi chậm.

## 5. Ghi nhận mức sử dụng tài nguyên

Tài nguyên cho biết hệ thống cần bao nhiêu năng lực tính toán để xử lý workload. Nên ghi nhận cả mức sử dụng tuyệt đối và mức sử dụng tương ứng với lượng công việc hoàn tất.

### 5.1. CPU

Các số liệu cần quan sát:

- CPU utilization của process và của container/host.
- CPU user và system nếu nền tảng cung cấp.
- CPU throttling trong container khi chạm giới hạn quota.
- Số core hoặc CPU quota được cấp.
- CPU trên mỗi request hoặc trên mỗi transaction thành công.

CPU utilization 70% trên máy 8 core không tương đương 70% trên container bị giới hạn 1 core. Do đó, phải lưu cả năng lực CPU được cấp và giới hạn thực tế.

Nếu CPU tăng sau migration, hãy đối chiếu cùng throughput. CPU tăng 10% trong khi throughput tăng 30% có thể là cải thiện hiệu suất tổng thể; CPU tăng 10% nhưng throughput không đổi lại cần điều tra.

### 5.2. Bộ nhớ JVM

Không nên chỉ ghi một con số memory tổng. Với Java, hãy phân biệt:

- Heap used, committed và maximum.
- Non-heap memory, bao gồm Metaspace và các vùng quản lý ngoài heap.
- Direct buffer và native memory khi có sử dụng.
- RSS hoặc working set của process/container.
- Allocation rate và xu hướng bộ nhớ theo thời gian.

Heap used có thể tăng tạm thời trước một lần garbage collection. Vì vậy, cần ghi nhận chuỗi thời gian hoặc các mốc sau GC, thay vì chỉ chụp một thời điểm. RSS có thể cao hơn heap do còn có thread stack, metaspace, code cache, direct buffer và native allocation.

Một lần đo memory thấp không đủ chứng minh không có memory leak. Cần quan sát sau khi workload chạy đủ lâu và so sánh xu hướng ở các khoảng thời gian tương đương.

### 5.3. Garbage collection

Các chỉ số GC hữu ích gồm:

- Số lần GC theo loại.
- Tổng thời gian và thời gian pause.
- Tỷ lệ thời gian JVM dành cho GC.
- Allocation rate.
- Heap occupancy trước và sau GC.
- Số lần Full GC và nguyên nhân nếu có.

GC có thể ảnh hưởng trực tiếp tới p95/p99 latency. Nếu migration làm thay đổi JDK hoặc thư viện tạo object, allocation rate và đặc tính GC có thể thay đổi dù logic nghiệp vụ không đổi.

Hãy lưu cấu hình GC, heap size và các JVM flags cùng với baseline. Không nên so sánh hai lần chạy có cấu hình heap hoặc collector khác nhau mà không ghi nhận đó là một biến thay đổi.

### 5.4. Thread và connection pool

Theo dõi:

- Số thread đang sống và số thread đang hoạt động.
- Số thread chờ, blocked hoặc bị treo lâu.
- Kích thước executor, queue depth và task bị từ chối.
- Số connection đang dùng, nhàn rỗi và đang chờ trong pool.
- Thời gian lấy connection và số lần pool cạn.
- Số socket, file descriptor hoặc handle nếu hệ điều hành cung cấp.

Thread tăng bất thường có thể dẫn tới memory pressure hoặc context switching. Connection pool cạn có thể khiến latency tăng dù CPU vẫn thấp. Một queue tăng liên tục cho thấy tốc độ đưa việc vào cao hơn tốc độ xử lý trong một khoảng thời gian.

### 5.5. Network, disk và tài nguyên phụ thuộc

Tùy kiến trúc, nên thu thập thêm:

- Network bytes in/out, số kết nối và lỗi kết nối.
- Disk read/write, IOPS và thời gian chờ I/O.
- Database query count, query latency, lock wait và connection utilization.
- Cache hit/miss và eviction.
- Message broker lag, queue depth và consumer throughput.
- Giới hạn CPU/memory của container và số lần container bị restart.

Chọn những chỉ số gắn với kiến trúc và luồng nghiệp vụ đang khảo sát. Không cần thu thập mọi metric có thể có nếu chúng không giúp giải thích hành vi hệ thống.

## 6. Cố định workload để phép so sánh có ý nghĩa

Số liệu chỉ có thể so sánh khi hai lần đo thực hiện công việc tương đương. Cùng một ứng dụng nhưng tải khác nhau có thể cho latency và resource utilization rất khác.

Trước khi đo, cần mô tả workload:

| Thành phần | Thông tin cần ghi |
|---|---|
| Kịch bản | Endpoint, nghiệp vụ hoặc batch đang kiểm tra |
| Dữ liệu | Kích thước dataset, phân bố dữ liệu, trạng thái database |
| Tải đầu vào | Request/second hoặc số message được phát |
| Concurrency | Số client, thread hoặc request đồng thời |
| Tỷ lệ luồng | Ví dụ 60% đọc, 30% ghi, 10% tìm kiếm |
| Thời gian | Warm-up, thời gian đo ổn định và thời gian chạy tổng |
| Hành vi client | Think time, timeout, retry và cách xử lý response |
| Kết thúc | Điều kiện dừng, số thao tác đã hoàn tất và số mẫu hợp lệ |

Nên dùng cùng dữ liệu hoặc dataset có tính chất tương đương. Nếu database ở lần chạy sau đã có cache nóng, số lượng bản ghi khác hoặc index khác, latency có thể thay đổi vì lý do ngoài migration.

### 6.1. Phân biệt closed workload và open workload

Trong closed workload, số client đồng thời được giữ cố định. Khi hệ thống phản hồi chậm, tốc độ gửi request của client cũng có thể giảm. Cách này hữu ích để quan sát một nhóm người dùng cố định nhưng có thể che khuất tình trạng quá tải.

Trong open workload, công cụ tạo tải gửi công việc theo tốc độ mục tiêu, độc lập tương đối với thời gian phản hồi. Cách này giúp kiểm tra hệ thống có duy trì được arrival rate hay không, nhưng cần kiểm soát queue và giới hạn của load generator.

Hãy ghi rõ mô hình đang dùng. Không nên so sánh kết quả từ hai mô hình tải khác nhau rồi kết luận rằng migration làm thay đổi latency.

### 6.2. Warm-up và trạng thái ổn định

JVM có JIT compilation, class loading, cache và các hoạt động khởi tạo. Những request đầu tiên có thể chậm hơn đáng kể so với giai đoạn chạy ổn định.

Một phép đo thường gồm:

1. Khởi động ứng dụng với cấu hình đã định.
2. Chạy warm-up để JIT, cache và các pool đạt trạng thái ổn định.
3. Xác nhận các chỉ số đã ổn định tương đối.
4. Bắt đầu khoảng đo chính thức.
5. Dừng tải, chờ hệ thống hoàn tất công việc còn lại và ghi nhận kết quả.

Không nên gộp thời gian startup vào latency xử lý request thông thường. Nếu startup time là yêu cầu cần đánh giá, hãy đo nó thành một kịch bản riêng và dùng cùng điều kiện khởi động ở cả hai phiên bản.

Warm-up không có một thời lượng cố định phù hợp cho mọi ứng dụng. Hãy chọn dựa trên hành vi thực tế, quan sát JIT, cache và metric. Ghi rõ thời lượng đã dùng để lần chạy sau có thể tái lập.

## 7. Thiết kế một lượt đo có thể lặp lại

Một lượt đo tốt cần có quy trình rõ ràng, dữ liệu đầu vào xác định và điều kiện kết thúc nhất quán.

### Bước 1: Chọn luồng và mục tiêu

Chọn các luồng nghiệp vụ quan trọng và xác định mục tiêu đo cho từng luồng. Ví dụ: tạo đơn hàng, tìm kiếm, truy vấn báo cáo và xử lý message nền. Đặt tiêu chí chức năng cùng chỉ số hiệu năng cần quan sát.

### Bước 2: Chuẩn bị môi trường

Ghi nhận JDK, phiên bản ứng dụng, dependency, JVM flags, OS/container, CPU, memory, database, broker, cache và cấu hình mạng. Đảm bảo không có tác vụ nền ngoài dự kiến làm nhiễu phép đo.

### Bước 3: Chuẩn bị dữ liệu

Tạo dataset có kích thước và phân bố được mô tả. Ghi lại cách khởi tạo dữ liệu, trạng thái schema, index, cache và các bước reset nếu cần. Với luồng ghi dữ liệu, dùng dữ liệu test có thể đối soát và tránh làm thay đổi dữ liệu ngoài phạm vi.

### Bước 4: Chạy thử kịch bản

Kiểm tra công cụ tạo tải, endpoint, xác thực, timeout và khả năng ghi nhận kết quả. Xác nhận tải phát ra đúng như cấu hình và load generator không trở thành nút thắt.

### Bước 5: Warm-up và đo chính thức

Chạy warm-up, sau đó thực hiện khoảng đo với workload đã định. Thu thập functional counters, latency distribution, throughput, errors và resource metrics trên cùng trục thời gian.

### Bước 6: Lặp lại

Chạy nhiều lần độc lập trong điều kiện tương đương. Ghi lại kết quả từng lần, không chỉ giữ một lần có kết quả đẹp nhất. Nếu các lần đo chênh lệch lớn, tìm nguyên nhân trước khi dùng chúng làm baseline.

### Bước 7: Đối soát và lưu kết quả

Kiểm tra số thao tác gửi, số thao tác hoàn tất, dữ liệu đầu ra, lỗi và số mẫu đo. Lưu raw results, dashboard hoặc báo cáo cùng metadata môi trường. Ghi rõ run ID và thời điểm thực hiện.

## 8. Công cụ và cách thu thập số liệu trong ứng dụng Java

Có thể kết hợp metric ở tầng ứng dụng với dữ liệu từ JVM, hệ điều hành và các dịch vụ phụ thuộc. Mỗi nguồn quan sát một phần khác nhau của hệ thống.

### 8.1. Metric ở tầng ứng dụng

Spring Boot Actuator kết hợp Micrometer có thể xuất các metric về HTTP request, JVM, process và các meter do ứng dụng tự định nghĩa, tùy dependency và cấu hình. Các metric chức năng nên được thêm tại vị trí mà ứng dụng biết thao tác đã thực sự thành công.

Ví dụ minh họa dùng Micrometer:

~~~java
@Service
public class OrderService {

    private final Counter completedOrders;
    private final Timer orderProcessingTimer;

    public OrderService(MeterRegistry registry) {
        this.completedOrders = Counter.builder("orders.completed")
                .description("Number of successfully completed orders")
                .register(registry);

        this.orderProcessingTimer = Timer.builder("orders.process")
                .description("Order processing duration")
                .publishPercentileHistogram()
                .register(registry);
    }

    public OrderResult createOrder(CreateOrderCommand command) {
        Timer.Sample sample = Timer.start();

        try {
            OrderResult result = process(command);

            if (result.isSuccessful()) {
                completedOrders.increment();
            }

            return result;
        } finally {
            sample.stop(orderProcessingTimer);
        }
    }

    private OrderResult process(CreateOrderCommand command) {
        // Thực hiện nghiệp vụ tạo đơn hàng
        return OrderResult.success();
    }
}
~~~

Đây là ví dụ về vị trí ghi nhận counter và timer; kiểu dữ liệu và cách xác định thành công cần phù hợp với ứng dụng thực tế. Không nên tăng counter ngay khi nhận request nếu thao tác còn có thể thất bại ở bước ghi database hoặc gọi dịch vụ bên ngoài.

Tên metric nên ổn định, có đơn vị rõ ràng và không chứa dữ liệu nhận diện từng người dùng hoặc từng giao dịch. Tránh đưa order ID, email, token hoặc URL có giá trị động vào label/tag vì sẽ tạo cardinality rất lớn, làm tăng bộ nhớ và chi phí của hệ thống giám sát.

### 8.2. Prometheus và dashboard

Prometheus có thể scrape metric endpoint theo chu kỳ và lưu chuỗi thời gian. Grafana hoặc công cụ tương đương giúp hiển thị latency, throughput, errors, CPU, memory và các chỉ số khác trên cùng khoảng thời gian.

Khi dùng histogram, hãy cấu hình bucket phù hợp với ngưỡng latency cần theo dõi. Percentile tính từ histogram có độ chính xác phụ thuộc vào bucket và cách truy vấn. Không nên so sánh percentile từ hai dashboard nếu cách tính hoặc cấu hình bucket khác nhau mà không ghi chú.

### 8.3. Java Flight Recorder và công cụ JVM

Java Flight Recorder (JFR) giúp quan sát hoạt động JVM như allocation, GC, thread, lock contention, class loading và một số sự kiện runtime khác.

Ví dụ có thể ghi một bản recording có thời hạn khi chạy ứng dụng:

~~~bash
java -XX:StartFlightRecording=filename=baseline.jfr,duration=2m,settings=profile -jar app.jar
~~~

Hoặc có thể dùng jcmd để điều khiển recording của JVM đang chạy. JFR phù hợp để điều tra nguyên nhân khi metric tổng quan cho thấy CPU, GC hoặc latency bất thường. Không nhất thiết phải bật mọi sự kiện chi tiết trong toàn bộ thời gian benchmark vì việc quan sát cũng có overhead.

Các công cụ như jstat, jcmd và jconsole có thể hỗ trợ xem heap, GC và hoạt động JVM. Hãy lưu phiên bản công cụ và cách thu thập nếu kết quả cần được tái lập.

### 8.4. Metric hệ điều hành và container

Dùng công cụ phù hợp với hệ điều hành để ghi CPU, memory, disk, network, process và container limits. Ví dụ trên Linux có thể dùng pidstat, vmstat, iostat hoặc dữ liệu từ cgroup/container runtime.

Cần ghi cả mức tài nguyên được cấp lẫn mức tiêu thụ thực tế. Nếu container bị giới hạn 1 CPU và 1 GiB memory, không thể diễn giải metric như thể ứng dụng đang chạy trên host có toàn bộ tài nguyên.

### 8.5. Công cụ tạo tải

Có thể dùng k6, Gatling, JMeter hoặc công cụ phù hợp với giao thức của hệ thống. Công cụ cần lưu được:

- Kịch bản và phiên bản công cụ.
- Tốc độ gửi tải, concurrency và thời gian chạy.
- Latency distribution, throughput và error.
- Dữ liệu đầu vào hoặc cách tạo dữ liệu.
- Kết quả từng request hoặc summary đủ để đối soát.

Đảm bảo máy tạo tải có đủ CPU, network và tài nguyên. Nếu load generator quá tải, số liệu đo sẽ phản ánh giới hạn của máy tạo tải thay vì giới hạn của ứng dụng.

## 9. Đồng bộ thời gian và liên kết các nguồn metric

Khi ghép metric từ ứng dụng, JVM, database và load generator, các nguồn cần có mốc thời gian có thể đối chiếu. Đồng bộ đồng hồ hệ thống bằng cơ chế phù hợp và lưu timezone hoặc quy ước timestamp.

Mỗi lượt đo nên có một run ID. Gắn run ID vào tên file kết quả, metadata hoặc nhãn ở cấp thử nghiệm để tìm đúng log, JFR recording, dashboard snapshot và output của load generator.

Không nên gắn run ID ngẫu nhiên cho từng request dưới dạng label metric nếu điều đó tạo cardinality cao. Có thể dùng log hoặc trace để liên kết request chi tiết, còn metric tổng hợp nên giữ nhãn có số lượng giá trị giới hạn.

Một timeline hữu ích có thể gồm:

~~~text
T0        T1             T2                T3
|---------|--------------|-----------------|
Startup   Warm-up        Measurement       Drain / verify
                         |                 |
                         +-- App metrics   |
                         +-- JVM metrics   |
                         +-- OS metrics    |
                         +-- Load results |
                                           +-- Functional reconciliation
~~~

Các nguồn metric phải sử dụng cùng khoảng đo chính thức. Nếu CPU được lấy trung bình trong 10 phút nhưng latency chỉ lấy trong 2 phút, việc đặt hai con số cạnh nhau có thể dẫn đến kết luận sai.

## 10. Lưu metadata để baseline có thể tái lập

Số liệu không có bối cảnh rất khó sử dụng. Với mỗi lần chạy, nên lưu một manifest hoặc báo cáo kèm những thông tin sau:

| Nhóm metadata | Nội dung |
|---|---|
| Mã nguồn | Git commit, branch/tag và trạng thái working tree |
| Java | JDK vendor, version, runtime version và class-file target |
| Build | Gradle/Maven version, build flags và artifact checksum |
| Dependency | Phiên bản framework, thư viện chính và dependency lock nếu có |
| JVM | Heap min/max, GC, JVM flags và system properties liên quan |
| Ứng dụng | Profile, cấu hình chức năng, feature flags và phiên bản build |
| Hạ tầng | CPU, memory, OS, container limit, network và vùng triển khai |
| Dịch vụ phụ thuộc | Database, schema, broker, cache và phiên bản service liên quan |
| Dataset | Kích thước, cách tạo, trạng thái ban đầu và cách reset |
| Workload | Kịch bản, concurrency, arrival rate, mix và thời lượng |
| Công cụ | Load generator, monitoring agent và phiên bản công cụ |
| Thời điểm | Timestamp bắt đầu/kết thúc, timezone và run ID |

Không lưu secret, access token, mật khẩu, dữ liệu cá nhân hoặc payload nhạy cảm trong manifest. Có thể ghi tên biến cấu hình, trạng thái đã cấu hình hoặc checksum của bản cấu hình đã loại bỏ bí mật để nhận biết thay đổi mà không làm lộ thông tin.

Ví dụ cấu trúc manifest rút gọn:

~~~yaml
run:
  id: baseline-java17-order-flow-001
  startedAt: "2026-11-01T09:00:00Z"
  duration: "10m"
source:
  commit: "abc1234"
  artifactSha256: "..."
java:
  vendor: "Example Vendor"
  runtime: "17.x"
  targetRelease: 17
environment:
  cpuLimit: "4 cores"
  memoryLimit: "4 GiB"
  database: "PostgreSQL <version>"
workload:
  scenario: "create-order"
  arrivalRate: "100 requests/second"
  concurrency: 50
  warmup: "5m"
measurement:
  latency: ["p50", "p95", "p99"]
  functional: ["success", "business-error", "technical-error"]
  resources: ["cpu", "heap", "gc", "threads", "connections"]
~~~

Các giá trị trong ví dụ chỉ minh họa cấu trúc. Manifest thực tế phải ghi đúng môi trường và workload đã chạy, không điền giá trị ước lượng thay cho dữ liệu quan sát.

## 11. So sánh kết quả trước và sau migration

Sau khi migration, chạy lại cùng kịch bản, dataset, tải và cách đo. Tạo bảng so sánh theo từng luồng hoặc nhóm metric.

Với một chỉ số dạng số, có thể tính chênh lệch tuyệt đối:

~~~text
absolute change = value_after - value_before
~~~

Và tỷ lệ thay đổi:

~~~text
relative change (%) =
    (value_after - value_before) / value_before * 100
~~~

Cần diễn giải dấu theo ý nghĩa metric. Latency tăng thường là xấu, trong khi throughput tăng thường là tốt. CPU tăng có thể tốt hoặc xấu tùy throughput và mục tiêu sử dụng tài nguyên. Với baseline bằng 0, không dùng công thức phần trăm trên; hãy báo chênh lệch tuyệt đối hoặc dùng cách biểu diễn phù hợp.

Ví dụ số liệu minh họa:

| Chỉ số | Trước migration | Sau migration | Thay đổi |
|---|---:|---:|---:|
| Tỷ lệ nghiệp vụ đúng | 100% | 100% | Không đổi |
| Tỷ lệ lỗi kỹ thuật | 0,20% | 0,20% | Không đổi |
| Throughput | 500 req/s | 510 req/s | +2,0% |
| p50 latency | 80 ms | 82 ms | +2,5% |
| p95 latency | 240 ms | 270 ms | +12,5% |
| p99 latency | 600 ms | 720 ms | +20,0% |
| CPU trung bình | 65% | 58% | -7 điểm phần trăm |
| Heap sau GC | 900 MiB | 950 MiB | +50 MiB |

Bảng này cho thấy chỉ nhìn throughput hoặc CPU có thể tạo ấn tượng tốt, trong khi p95 và p99 latency đã tăng. Nhóm cần điều tra nguyên nhân trước khi kết luận migration đạt yêu cầu. Các con số chỉ là ví dụ, không phải ngưỡng chuẩn cho mọi ứng dụng.

Khi báo cáo CPU hoặc tỷ lệ phần trăm, cần phân biệt chênh lệch điểm phần trăm với phần trăm thay đổi tương đối. Từ 65% xuống 58% là giảm 7 điểm phần trăm, tương đương giảm khoảng 10,8% so với giá trị ban đầu.

## 12. Đánh giá độ tin cậy của phép đo

Một khác biệt nhỏ giữa hai lần chạy có thể đến từ nhiễu đo, không phải từ migration. Các nguồn nhiễu thường gặp gồm:

- CPU bị chia sẻ với tiến trình khác.
- Cache nóng/lạnh khác nhau.
- JIT compilation hoặc class loading chưa ổn định.
- Database checkpoint, vacuum, backup hoặc tác vụ bảo trì.
- Network congestion hoặc dịch vụ phụ thuộc có tải bất thường.
- Khác biệt dữ liệu, số lượng request hoặc phân bố request.
- Logging, tracing hoặc profiler bật ở một lần chạy nhưng tắt ở lần khác.

Nên lặp lại các lượt đo độc lập, xem phân phối giữa các lần chạy và ghi rõ độ biến động. Không chọn riêng lượt chạy tốt nhất. Nếu kết quả giữa các lần đo chênh lệch lớn, hãy xử lý nguyên nhân nhiễu hoặc tăng số lần đo trước khi đưa ra kết luận.

Khi cần phân tích sâu, có thể dùng khoảng tin cậy hoặc phương pháp thống kê phù hợp với phân phối dữ liệu. Với latency, dữ liệu thường không tuân theo phân phối chuẩn đơn giản; không nên áp dụng máy móc trung bình và độ lệch chuẩn rồi bỏ qua phân phối gốc.

Cần đảm bảo số lượng mẫu đủ lớn cho phân vị đang báo cáo. Ví dụ, p99 cần nhiều request hơn đáng kể so với p50 để có đủ quan sát ở phần đuôi. Nếu mẫu quá ít, ghi rõ giới hạn thay vì trình bày p99 như một kết luận chắc chắn.

## 13. Các sai lầm thường gặp khi tạo baseline

### Chỉ đo một lần

Một lần chạy có thể bị ảnh hưởng bởi cache, JIT hoặc tác vụ nền. Hãy lặp lại và lưu kết quả từng lần.

### Chỉ dùng latency trung bình

Mean có thể che giấu nhóm request rất chậm. Nên theo dõi ít nhất p50, p95 và p99 khi số mẫu đủ lớn.

### So sánh workload khác nhau

Số request, concurrency, dữ liệu hoặc tỷ lệ đọc/ghi khác nhau làm kết quả mất tính tương đương. Cần cố định và lưu workload.

### Bỏ qua tính đúng đắn của nghiệp vụ

Response thành công không chứng minh dữ liệu cuối cùng đúng. Cần kiểm tra kết quả, tác dụng phụ và invariant nghiệp vụ.

### Chỉ ghi CPU và heap tại một thời điểm

Snapshot đơn lẻ không thể hiện xu hướng, peak, GC pause hoặc memory leak. Nên lưu chuỗi thời gian trong toàn bộ khoảng đo.

### Không ghi cấu hình và giới hạn hạ tầng

Cùng phần trăm CPU nhưng số core khác nhau có ý nghĩa khác nhau. Cùng heap used nhưng max heap khác nhau cũng không thể so sánh trực tiếp.

### Bật profiler hoặc tracing không nhất quán

Công cụ quan sát có thể tạo overhead. Hãy giữ cấu hình tương đương và ghi nhận công cụ đang bật ở từng lượt.

### Dùng metric có cardinality không kiểm soát

Gắn user ID, order ID hoặc giá trị URL động vào metric tag có thể làm hệ thống monitoring tốn tài nguyên và thay đổi chính hành vi đang đo. Dùng metric tổng hợp với nhãn có giới hạn; dùng log/trace cho chi tiết từng request.

### Chỉ báo cáo phần trăm thay đổi

Phần trăm có thể gây hiểu nhầm khi baseline rất nhỏ hoặc bằng 0. Luôn lưu giá trị gốc, đơn vị, chênh lệch tuyệt đối và điều kiện đo.

## 14. Xác định tiêu chí chấp nhận trước khi chạy migration

Trước khi so sánh, nhóm nên thống nhất tiêu chí chấp nhận theo yêu cầu của sản phẩm và hệ thống. Không có một ngưỡng latency, CPU hoặc memory phù hợp cho tất cả ứng dụng.

Ví dụ về cách viết tiêu chí:

| Nhóm | Tiêu chí minh họa |
|---|---|
| Chức năng | Các luồng nghiệp vụ quan trọng giữ đúng kết quả; không phát sinh giao dịch trùng hoặc mất dữ liệu |
| Độ trễ | p95 của API quan trọng không vượt ngưỡng đã thống nhất và không tăng quá mức cho phép so với baseline |
| Throughput | Duy trì được arrival rate mục tiêu mà không làm queue tăng liên tục |
| Lỗi | Không tăng tỷ lệ lỗi kỹ thuật hoặc timeout vượt ngưỡng chấp nhận |
| Tài nguyên | CPU, heap, GC pause và connection utilization nằm trong giới hạn vận hành |
| Ổn định | Không xuất hiện xu hướng tăng bộ nhớ, thread hoặc queue bất thường trong bài chạy dài |

Nếu hệ thống đã có SLO hoặc error budget, hãy dùng chúng làm cơ sở. Nếu chưa có, nhóm cần xác định ngưỡng từ yêu cầu nghiệp vụ, năng lực hạ tầng và baseline hiện tại. Không nên tự chọn ngưỡng chỉ vì nó làm cho kết quả migration trông có vẻ tốt.

Cũng cần phân biệt ngưỡng tuyệt đối và ngưỡng tương đối. Ví dụ, p95 phải dưới 300 ms là ngưỡng tuyệt đối; p95 không được tăng quá 10% so với baseline là ngưỡng tương đối. Có thể cần cả hai để tránh một baseline vốn đã chậm trở thành chuẩn chấp nhận.

## 15. Mẫu báo cáo baseline

Một báo cáo baseline có thể tổ chức theo cấu trúc sau:

### Thông tin lần đo

- Tên hệ thống và môi trường.
- Mã commit, artifact và phiên bản Java.
- Ngày giờ, run ID và người thực hiện.
- Hạ tầng, cấu hình JVM và phiên bản dịch vụ phụ thuộc.

### Kịch bản và workload

- Luồng nghiệp vụ được kiểm tra.
- Dataset và trạng thái dữ liệu ban đầu.
- Tốc độ gửi tải, concurrency và tỷ lệ từng loại request.
- Warm-up, thời gian đo và số lần lặp.

### Kết quả chức năng

- Số thao tác gửi, thành công và thất bại.
- Phân loại lỗi nghiệp vụ và lỗi kỹ thuật.
- Kết quả đối soát dữ liệu.
- Các invariant hoặc điều kiện đúng đã kiểm tra.

### Kết quả hiệu năng

- Throughput và error rate.
- p50, p90, p95, p99 latency.
- Queue time, database latency và remote call latency nếu có.

### Kết quả tài nguyên

- CPU process/container và CPU throttling.
- Heap, non-heap, RSS và allocation rate.
- GC count, pause và thời gian dành cho GC.
- Thread, executor queue và connection pool.
- Network, disk và metric dịch vụ phụ thuộc có liên quan.

### Kết luận và giới hạn

- Các chỉ số chính được dùng làm baseline.
- Mức dao động giữa các lần đo.
- Bất thường đã quan sát.
- Điều kiện hoặc giới hạn có thể ảnh hưởng đến lần so sánh sau.
- Đường dẫn tới raw data, dashboard, log và JFR recording.

Báo cáo cần giữ cả số liệu gốc và phần diễn giải. Không chỉ lưu ảnh dashboard vì ảnh thường thiếu dữ liệu chi tiết, truy vấn và metadata để tái phân tích.

## 16. Quy trình áp dụng cho Java Compatibility Migration

Trong một đợt migration, có thể áp dụng quy trình theo hai mốc rõ ràng:

**Trước migration**

1. Chọn các luồng nghiệp vụ quan trọng và định nghĩa tiêu chí đúng.
2. Cố định workload, dataset và môi trường đo.
3. Thu thập functional counters, latency, throughput và resource metrics.
4. Lặp lại phép đo, xác nhận độ ổn định và lưu manifest.
5. Lưu artifact, raw data và các báo cáo để làm mốc tham chiếu.

**Sau migration**

1. Xác nhận phiên bản Java, dependency, JVM flags và hạ tầng thực tế.
2. Chạy lại cùng dataset, workload, thời gian warm-up và khoảng đo.
3. Thu thập cùng bộ metric bằng cùng cách định nghĩa.
4. Đối soát chức năng và dữ liệu trước khi diễn giải hiệu năng.
5. So sánh giá trị tuyệt đối, phần trăm thay đổi, phân vị và độ biến động.
6. Điều tra những khác biệt vượt ngưỡng hoặc có dấu hiệu bất thường.
7. Ghi kết luận cùng điều kiện thử nghiệm và giới hạn của bằng chứng.

Nếu phải thay đổi hạ tầng cùng lúc với JDK hoặc thư viện, hãy ghi rõ các biến đã thay đổi. Khi có thể, kiểm tra từng thay đổi riêng hoặc chạy một ma trận thử nghiệm để phân biệt ảnh hưởng của runtime với ảnh hưởng của hạ tầng.

## 17. Nguyên tắc sử dụng baseline

- **Đo đúng điều cần bảo vệ:** Chọn chỉ số gắn với luồng nghiệp vụ và yêu cầu vận hành thực tế.
- **Giữ điều kiện tương đương:** Workload, dữ liệu, runtime và hạ tầng phải được mô tả đủ rõ.
- **Đo cả kết quả và chi phí:** Functional correctness, latency, throughput và resource utilization bổ sung cho nhau.
- **Quan sát phân phối:** Dùng percentile và số mẫu, không dựa riêng vào trung bình.
- **Lặp lại và lưu dữ liệu gốc:** Một kết quả có thể tái lập có giá trị hơn một con số đơn lẻ.
- **Diễn giải theo ngữ cảnh:** CPU hoặc memory tăng/giảm cần được đặt cạnh throughput, latency và giới hạn tài nguyên.
- **Báo cáo đúng mức bằng chứng:** Nếu chỉ đo một môi trường hoặc một workload, kết luận phải giới hạn trong điều kiện đó.

Ghi nhận baseline là bước chuẩn bị để đánh giá tác động của migration bằng dữ liệu. Khi nhóm biết rõ hệ thống đã xử lý đúng những nghiệp vụ nào, phản hồi trong bao lâu và tiêu thụ bao nhiêu tài nguyên dưới một workload xác định, kết quả sau nâng cấp sẽ có cơ sở so sánh cụ thể. Nếu không có mốc tham chiếu và điều kiện đo được lưu lại, những nhận xét như “ứng dụng vẫn nhanh”, “CPU tăng nhẹ” hoặc “mọi chức năng có vẻ ổn” rất khó kiểm chứng và không đủ tin cậy để ra quyết định migration.

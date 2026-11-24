# Chia sẻ tài nguyên, noisy neighbor và tác động đến workload

Trong hạ tầng đám mây, nhiều workload có thể cùng sử dụng một tập hợp máy chủ vật lý, thiết bị lưu trữ và đường truyền mạng. Cách tổ chức này giúp nhà cung cấp khai thác phần cứng hiệu quả, cung cấp năng lực linh hoạt và giảm chi phí cho khách hàng. Tuy nhiên, khi các workload cùng tranh chấp một tài nguyên có giới hạn, hiệu năng của một workload có thể bị ảnh hưởng bởi hoạt động của workload khác. Hiện tượng này thường được gọi là **noisy neighbor**.

Đối với **CLOUD_CORE_SERVICES_COMPUTE**, việc hiểu cơ chế chia sẻ tài nguyên là nền tảng để lựa chọn máy ảo, container hoặc serverless; xác định cấu hình CPU, bộ nhớ, mạng; triển khai ứng dụng có khả năng mở rộng; bảo đảm tính sẵn sàng và kiểm soát chi phí vận hành. Một cấu hình có đủ số CPU và dung lượng RAM trên giấy vẫn có thể không đáp ứng mục tiêu dịch vụ nếu tài nguyên bên dưới bị tranh chấp hoặc giới hạn sử dụng không phù hợp với workload.

## 1. Vì sao hạ tầng đám mây chia sẻ tài nguyên?

Máy chủ vật lý thường có nhiều CPU, dung lượng bộ nhớ lớn, nhiều thiết bị lưu trữ và nhiều cổng mạng. Một ứng dụng riêng lẻ hiếm khi sử dụng hết năng lực đó trong mọi thời điểm. Nếu mỗi khách hàng phải dành riêng toàn bộ một máy chủ, phần tài nguyên nhàn rỗi sẽ lớn và chi phí cung cấp dịch vụ tăng cao.

Nhà cung cấp đám mây vì vậy thường **đa thuê (multi-tenancy)**: phân chia năng lực của một hạ tầng vật lý cho nhiều máy ảo, container, dịch vụ hoặc tài khoản khách hàng. Bộ lập lịch, hypervisor, hệ điều hành máy chủ và các lớp điều khiển tài nguyên phối hợp để phân bổ CPU, bộ nhớ, lưu trữ và băng thông.

Việc chia sẻ có thể diễn ra ở nhiều lớp:

- **Lớp phần cứng:** nhiều workload cùng chạy trên CPU, bộ nhớ, bộ điều khiển lưu trữ, NIC hoặc GPU vật lý.
- **Lớp ảo hóa:** hypervisor ánh xạ CPU ảo, bộ nhớ và thiết bị ảo của máy ảo lên phần cứng dùng chung.
- **Lớp hệ điều hành:** nhiều tiến trình hoặc container cùng sử dụng kernel, CPU, bộ nhớ và thiết bị I/O của một máy chủ.
- **Lớp dịch vụ được quản lý:** nhiều khách hàng hoặc nhiều workload có thể dùng chung cụm máy chủ, storage pool, gateway hay năng lực xử lý phía sau API của nhà cung cấp.

Chia sẻ tài nguyên không đồng nghĩa với chia sẻ dữ liệu. Cơ chế cô lập bảo mật như phân quyền, ranh giới bộ nhớ, namespace và kiểm soát truy cập nhằm ngăn workload đọc hoặc sửa dữ liệu của workload khác. **Cô lập bảo mật** và **cô lập hiệu năng** là hai mục tiêu liên quan nhưng khác nhau: một nền tảng có thể bảo vệ dữ liệu tốt mà vẫn để hiệu năng dao động khi các workload tranh chấp tài nguyên vật lý.

## 2. Các loại tài nguyên có thể bị tranh chấp

Noisy neighbor không chỉ là vấn đề CPU. Một workload có thể làm tăng độ trễ của workload khác bằng cách chiếm dụng bất kỳ tài nguyên dùng chung nào.

| Tài nguyên | Cơ chế tranh chấp thường gặp | Tác động quan sát được |
| --- | --- | --- |
| CPU | Nhiều luồng cần chạy cùng lúc; CPU bị oversubscribe; quota hoặc giới hạn thời gian chạy quá chặt | Tăng thời gian chờ CPU, giảm throughput, tăng độ trễ p95/p99 |
| Bộ nhớ | Nhiều workload chiếm RAM; hệ thống phải thu hồi trang, dùng swap hoặc chấm dứt tiến trình khi chạm giới hạn | Tăng độ trễ, garbage collection kéo dài, lỗi out-of-memory (OOM) |
| Lưu trữ | Nhiều workload cùng đọc/ghi một thiết bị hoặc storage pool; IOPS, thông lượng hay hàng đợi bị bão hòa | Tăng thời gian hoàn tất I/O, truy vấn cơ sở dữ liệu chậm, batch kéo dài |
| Mạng | Các workload cùng sử dụng băng thông, hàng đợi NIC, gateway hoặc đường truyền | Tăng latency, jitter, packet drop hoặc retransmission |
| GPU/accelerator | Nhiều tác vụ dùng chung năng lực tính toán, bộ nhớ thiết bị hoặc lịch thực thi | Thời gian huấn luyện/suy luận biến động, giảm số tác vụ hoàn tất mỗi giây |

### 2.1. CPU: thời gian chạy và thời gian chờ

CPU là tài nguyên được lập lịch theo thời gian. Khi tổng nhu cầu CPU của các workload vượt năng lực CPU vật lý tại cùng một thời điểm, bộ lập lịch phải quyết định workload nào được chạy trước và workload nào phải chờ.

Trong môi trường máy ảo, nhiều vCPU có thể cùng được ánh xạ lên một số lõi vật lý. Nếu máy chủ có mức overcommit cao hoặc workload khác tăng tải đột ngột, máy ảo có thể mất thêm thời gian chờ được hypervisor cấp CPU. Một số nền tảng cung cấp chỉ số như CPU steal hoặc CPU ready để giúp nhận diện tình trạng này; tên gọi và cách đo phụ thuộc nền tảng.

Trong container, CPU thường được điều khiển bằng cơ chế như Linux cgroups. CPU request hoặc trọng số chia sẻ thể hiện mức tài nguyên mà workload được bảo đảm tương đối khi tranh chấp; CPU limit có thể đặt trần thời gian chạy. Nếu giới hạn quá thấp, container có thể bị throttling dù máy chủ vẫn còn CPU ở một thời điểm khác hoặc workload cần những đợt xử lý ngắn để đáp ứng yêu cầu latency.

### 2.2. Bộ nhớ: áp lực dung lượng và hành vi thu hồi

RAM có đặc điểm khác CPU: không thể đơn giản chia thời gian sử dụng theo cách tương tự. Khi tổng nhu cầu bộ nhớ vượt dung lượng có thể cấp, hệ điều hành hoặc nền tảng phải thu hồi cache, chuyển trang sang swap nếu được cấu hình, từ chối cấp phát hoặc kết thúc tiến trình.

Áp lực bộ nhớ có thể làm tăng thời gian truy cập dữ liệu, khiến garbage collector hoạt động thường xuyên hơn hoặc gây OOM. Với container, memory limit thường là ranh giới quan trọng: một container vượt giới hạn có thể bị hệ thống kết thúc, kể cả khi máy chủ vật lý vẫn còn một phần RAM. Vì vậy, cần theo dõi cả mức sử dụng, working set, tốc độ cấp phát, số lần OOM và dấu hiệu reclaim/swap thay vì chỉ nhìn tổng RAM của máy chủ.

### 2.3. Lưu trữ: IOPS, thông lượng và độ sâu hàng đợi

Hai workload có thể dùng các volume riêng nhưng vẫn chia sẻ thiết bị vật lý hoặc storage pool ở phía sau. Một workload quét dữ liệu lớn, tạo nhiều I/O ngẫu nhiên hoặc ghi liên tục có thể làm tăng độ sâu hàng đợi và thời gian chờ của workload khác.

Khi đánh giá lưu trữ, cần phân biệt:

- **IOPS:** số thao tác đọc/ghi mỗi giây.
- **Thông lượng:** lượng dữ liệu truyền mỗi giây.
- **Độ trễ I/O:** thời gian hoàn thành một thao tác.
- **Queue depth:** số yêu cầu đang chờ hoặc đang được xử lý.

Đạt giới hạn IOPS không nhất thiết đồng nghĩa đã đạt giới hạn thông lượng, và ngược lại. Kích thước khối I/O, tỷ lệ đọc/ghi và tính tuần tự hay ngẫu nhiên đều ảnh hưởng kết quả. Với workload nhạy độ trễ, một mức I/O trung bình có vẻ thấp vẫn có thể gây vấn đề nếu các đợt tăng tải tạo ra hàng đợi dài.

### 2.4. Mạng: băng thông không phải chỉ số duy nhất

Một đường truyền có băng thông danh nghĩa cao vẫn có thể gây chậm nếu hàng đợi bị đầy, số gói tin mỗi giây đạt giới hạn, có packet loss hoặc nhiều luồng cùng đi qua một gateway. Các ứng dụng tương tác thường nhạy với latency và jitter hơn tổng số byte truyền được.

Khi phân tích, cần xem xét cả throughput, packet rate, lỗi giao diện, retransmission, packet drop, thời gian phân giải DNS và độ trễ của các dịch vụ mạng trung gian. Nếu chỉ quan sát băng thông trung bình, những đợt nghẽn ngắn có thể bị bỏ qua.

## 3. Noisy neighbor là gì?

**Noisy neighbor** là tình huống một workload sử dụng nhiều tài nguyên dùng chung, hoặc tạo ra tải có tính đột biến, khiến workload khác bị giảm hiệu năng. Workload gây ảnh hưởng có thể là một tenant khác, một dịch vụ khác trong cùng cụm, hoặc một thành phần khác do chính đội vận hành quản lý.

Ví dụ, một máy ảo chạy tác vụ phân tích dữ liệu bắt đầu đọc lượng lớn dữ liệu từ storage pool. Các máy ảo khác dùng cùng pool có thể thấy thời gian đọc tăng lên, dù CPU và RAM của chúng vẫn còn dư. Tương tự, một container chạy tác vụ nén dữ liệu có thể tiêu thụ CPU trên node dùng chung và làm tăng latency của API.

Noisy neighbor thường có các đặc điểm:

1. Hiệu năng biến động theo thời điểm, đôi khi trùng với đợt tăng tải của workload khác.
2. Tài nguyên hoặc một tầng hạ tầng cụ thể có dấu hiệu bão hòa, trong khi các tài nguyên khác vẫn bình thường.
3. Cùng một workload có thể đạt kết quả tốt khi chạy riêng hoặc trên node khác.
4. Vấn đề có thể xuất hiện ở p95/p99 trước khi throughput trung bình giảm rõ rệt.

Hiện tượng này không tự động chứng minh nhà cung cấp có lỗi. Nguyên nhân có thể là đặc tính chia sẻ bình thường của gói dịch vụ, cấu hình quota, cách đặt workload, hoặc tải nội bộ của hệ thống. Cần có số liệu trước khi kết luận.

## 4. Tác động lên từng loại workload

Mức ảnh hưởng phụ thuộc vào cách workload sử dụng tài nguyên và mục tiêu dịch vụ. Cùng một mức tranh chấp có thể ít ảnh hưởng đến tác vụ batch có thể chạy lâu hơn, nhưng lại nghiêm trọng với API cần phản hồi trong vài chục mili giây.

| Loại workload | Đặc tính quan trọng | Tác động khi có noisy neighbor |
| --- | --- | --- |
| API và ứng dụng tương tác | Nhạy với latency, đặc biệt p95/p99; thường có giới hạn thời gian chờ | Request timeout, số lỗi tăng, trải nghiệm người dùng không ổn định |
| Batch và xử lý dữ liệu | Quan tâm throughput tổng thể và thời gian hoàn thành | Job kéo dài, trễ lịch xử lý, chi phí tính toán tăng |
| Streaming và hàng đợi | Cần tốc độ xử lý ổn định để theo kịp tốc độ dữ liệu đến | Consumer lag tăng, backlog tích lũy, dữ liệu đến đích muộn |
| Cơ sở dữ liệu | Nhạy với latency lưu trữ, bộ nhớ cache và CPU | Truy vấn chậm, lock tồn tại lâu hơn, replication lag tăng |
| AI/ML và HPC | Có thể cần CPU/GPU, bộ nhớ thiết bị và I/O thông lượng cao | Thời gian huấn luyện hoặc suy luận dao động, GPU utilization không ổn định |

Ví dụ, một dịch vụ thanh toán có SLO yêu cầu phần lớn request hoàn tất trong một khoảng thời gian ngắn. Khi CPU bị throttling hoặc storage latency tăng, một số request chậm sẽ chiếm connection và worker lâu hơn. Hàng đợi request phía sau tăng, khiến latency của cả dịch vụ tăng theo. Một tác vụ batch có thể chỉ cần chạy lâu hơn, nhưng dịch vụ thanh toán có thể vượt SLO và bắt đầu trả lỗi.

Noisy neighbor còn có thể tạo hiệu ứng dây chuyền. Một dịch vụ chậm giữ kết nối lâu hơn; hàng đợi tích lũy; autoscaler tăng số replica; các replica mới tiếp tục tranh chấp CPU, bộ nhớ hoặc kết nối với cùng dependency. Nếu không có giới hạn concurrency và backpressure, việc mở rộng có thể làm tình hình xấu hơn.

## 5. Phân biệt noisy neighbor với các nguyên nhân khác

Một biểu hiện như latency tăng hoặc throughput giảm chưa đủ để kết luận có noisy neighbor. Các nguyên nhân khác có thể tạo ra dấu hiệu tương tự:

- **Workload của chính ứng dụng tăng:** số request, kích thước dữ liệu hoặc độ phức tạp truy vấn tăng vượt dự kiến.
- **Cấu hình tài nguyên chưa phù hợp:** CPU limit quá thấp, thiếu RAM, pool kết nối nhỏ hoặc storage tier không đáp ứng yêu cầu.
- **Thay đổi phần mềm:** phiên bản mới tạo thêm truy vấn, vòng lặp tốn CPU hoặc memory leak.
- **Dependency bị chậm:** cơ sở dữ liệu, DNS, API bên ngoài hoặc dịch vụ xác thực gặp vấn đề.
- **Sự cố nền tảng:** bảo trì, lỗi mạng, suy giảm dịch vụ vùng hoặc sự cố ở control plane/data plane.

Để phân biệt, hãy đối chiếu thời điểm lỗi với tải ứng dụng, chỉ số tài nguyên bên trong workload, chỉ số của node/VM, metric của dịch vụ đám mây và sự kiện triển khai. Nếu chỉ workload trên một node bị ảnh hưởng trong khi workload tương tự ở node khác bình thường, giả thuyết tranh chấp tại node đó đáng được kiểm tra. Nếu nhiều workload ở các node khác nhau cùng lỗi khi gọi một dependency, cần kiểm tra dependency trước.

## 6. Đo lường và chẩn đoán

Chẩn đoán hiệu quả cần đi từ trải nghiệm của ứng dụng xuống các tầng hạ tầng. Không nên bắt đầu bằng việc tăng cấu hình ngay, vì điều đó có thể làm chi phí tăng mà không giải quyết đúng điểm nghẽn.

### 6.1. Xác định triệu chứng ở cấp ứng dụng

Ghi nhận latency trung bình cùng p50, p95 và p99; throughput; tỷ lệ lỗi; timeout; độ dài hàng đợi; số request đang xử lý; và thời gian chờ ở từng dependency. Các chỉ số phân vị giúp nhận diện trường hợp phần lớn request vẫn nhanh nhưng một nhóm request bị chậm đáng kể.

Đặt các chỉ số này cạnh SLI/SLO của dịch vụ. Nếu SLO bị vi phạm vào những khung giờ cố định, hãy kiểm tra xem đó có phải thời điểm workload khác chạy backup, batch, ETL hoặc tác vụ định kỳ hay không.

### 6.2. Kiểm tra tài nguyên tại đúng lớp

| Lớp quan sát | Chỉ số nên xem | Câu hỏi chẩn đoán |
| --- | --- | --- |
| Ứng dụng | p95/p99, timeout, queue depth, concurrency, thời gian chờ dependency | Người dùng bị chậm ở thao tác nào? |
| Máy ảo/host | CPU utilization, run queue, CPU steal/ready nếu nền tảng cung cấp, memory pressure, swap | Workload có phải chờ CPU hoặc bộ nhớ không? |
| Container/orchestrator | CPU usage, throttled time, memory working set, OOM event, restart, node pressure | Container có chạm request/limit hoặc bị node gây áp lực không? |
| Lưu trữ | IOPS, throughput, latency, queue depth, burst credit nếu có | Storage có bị bão hòa hoặc hết mức burst không? |
| Mạng | Throughput, packet rate, drops, retransmissions, latency, lỗi giao diện | Có nghẽn ở NIC, gateway hay đường truyền không? |
| Dịch vụ đám mây | Metric, quota, giới hạn gói dịch vụ, health event và thông báo bảo trì | Có giới hạn hoặc sự kiện nào từ nền tảng trùng thời điểm không? |

Không phải nhà cung cấp nào cũng công khai metric ở tầng host vật lý. Khi không có CPU steal, queue của storage hoặc thông tin về tenant khác, hãy dùng các metric được cung cấp, kiểm tra giới hạn dịch vụ và thu thập bằng chứng theo thời gian để trao đổi với bộ phận hỗ trợ.

### 6.3. Thực hiện kiểm tra có kiểm soát

Một quy trình thực tế có thể gồm:

1. Xác định workload, endpoint hoặc job bị ảnh hưởng và khung thời gian cụ thể.
2. So sánh với baseline ở thời điểm bình thường, cùng loại tải và cùng phiên bản ứng dụng.
3. Đối chiếu metric ứng dụng với CPU, RAM, I/O, mạng và sự kiện triển khai.
4. Kiểm tra quota, request/limit, giới hạn IOPS, băng thông và concurrency.
5. Nếu có thể, chạy cùng workload trong môi trường cô lập hoặc trên node khác với dữ liệu và cấu hình tương đương.
6. Thay đổi từng yếu tố một, ghi lại kết quả và theo dõi đủ lâu để bao phủ chu kỳ tải đại diện.

Kết quả tốt hơn khi kiểm tra được lặp lại với tải tương đương. Một lần chạy đơn lẻ có thể bị ảnh hưởng bởi cache nóng/lạnh, thời điểm backup, autoscaling hoặc biến động tự nhiên của hệ thống.

## 7. Giảm tác động của noisy neighbor

Giải pháp nên được chọn theo mức độ quan trọng của workload, bằng chứng về điểm nghẽn và chi phí chấp nhận được.

### 7.1. Điều chỉnh cách workload sử dụng tài nguyên

- Giới hạn concurrency cho các tác vụ nặng để tránh tạo đỉnh tải quá lớn.
- Dùng hàng đợi và cơ chế backpressure để điều tiết tốc độ xử lý khi hệ thống quá tải.
- Tách tác vụ batch, backup hoặc báo cáo khỏi luồng request tương tác nếu chúng tranh chấp cùng tài nguyên.
- Tối ưu truy vấn, cache, kích thước batch và I/O pattern để giảm nhu cầu tài nguyên.
- Đặt timeout, retry có exponential backoff và giới hạn retry để tránh tạo thêm tải khi dependency đang chậm.

### 7.2. Đặt request và limit hợp lý

Với container, request giúp bộ lập lịch ước lượng nhu cầu tài nguyên và đặt workload lên node phù hợp. Limit đặt giới hạn tiêu thụ. Request quá thấp có thể khiến nhiều workload được xếp chung trên một node; limit CPU quá thấp có thể gây throttling; memory limit quá thấp có thể dẫn đến OOM.

Ví dụ cấu hình Kubernetes dưới đây minh họa cách khai báo tài nguyên cho một container:

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "512Mi"
  limits:
    cpu: "1"
    memory: "1Gi"
~~~

Các giá trị trên chỉ là ví dụ cú pháp, không phải khuyến nghị sizing chung. Cần xác định request từ mức sử dụng đại diện và yêu cầu lập lịch; xác định limit từ giới hạn an toàn và hành vi tải đỉnh đã đo. Với workload nhạy latency, cần kiểm tra tác động của CPU throttling thay vì chỉ dựa vào phần trăm CPU trung bình.

Trong Kubernetes, QoS class được xác định từ cách khai báo request và limit. Pod thuộc lớp Guaranteed khi mọi container đều khai báo CPU và memory request, limit, đồng thời giá trị request bằng limit cho từng tài nguyên. Guaranteed có thể giúp ưu tiên bảo vệ workload trong một số tình huống áp lực node, nhưng không tạo ra thêm CPU vật lý và cũng không loại bỏ tranh chấp ở storage hoặc network.

### 7.3. Chọn mức cô lập phù hợp

Khi workload cần hiệu năng dự đoán được, có thể cân nhắc:

- Dùng node pool riêng hoặc nhóm máy ảo riêng cho workload quan trọng.
- Chọn loại máy ảo có đặc tính CPU, RAM, mạng và lưu trữ phù hợp với tải.
- Dùng dedicated instance, dedicated host hoặc bare metal nếu yêu cầu cô lập và tính ổn định đủ cao để biện minh cho chi phí.
- Dùng cơ chế affinity/anti-affinity hoặc placement phù hợp để tránh đặt các workload có đỉnh tải trùng nhau trên cùng node.
- Dùng dịch vụ lưu trữ có mức IOPS/thông lượng được cấp phù hợp với nhu cầu, thay vì giả định volume riêng đồng nghĩa với thiết bị vật lý riêng.

Mức cô lập phải được kiểm tra theo từng tài nguyên. Dedicated host có thể giảm tranh chấp CPU từ tenant khác trên host, nhưng mạng, storage backend hoặc dịch vụ quản lý vẫn có thể dùng chung. Hãy đọc rõ cam kết và giới hạn của từng loại dịch vụ.

### 7.4. Mở rộng và thiết kế khả năng phục hồi

Horizontal scaling giúp tăng số instance khi nhu cầu tăng, nhưng chỉ hiệu quả nếu tầng phụ trợ còn năng lực. Nếu mọi replica đều dùng chung một database hoặc storage pool đang bão hòa, tăng replica có thể làm dependency chịu tải nặng hơn.

Một thiết kế tốt cần kết hợp autoscaling với giới hạn concurrency, queue, circuit breaker, timeout và backpressure. Với workload batch, có thể xếp lịch vào giờ thấp điểm hoặc tạm dừng khi tài nguyên dùng chung có áp lực. Với workload tương tác, có thể tách nhóm instance quan trọng và dành capacity dự phòng để duy trì SLO.

## 8. Đánh đổi giữa hiệu năng, độ cô lập và chi phí

Tài nguyên chia sẻ thường có giá thấp hơn vì nhà cung cấp có thể khai thác phần năng lực nhàn rỗi của hạ tầng. Mức cô lập cao hơn thường làm tăng chi phí hoặc giảm tính linh hoạt. Vì vậy, không phải workload nào cũng cần chạy trên hạ tầng dedicated.

| Lựa chọn | Lợi ích | Đánh đổi và giới hạn |
| --- | --- | --- |
| Hạ tầng dùng chung | Chi phí thường thấp, dễ mở rộng và đa dạng cấu hình | Hiệu năng có thể biến động; mức cô lập phụ thuộc dịch vụ |
| Máy ảo hoặc node chuyên biệt | Dễ kiểm soát vị trí và cấu hình workload hơn | Chi phí cao hơn; vẫn có thể dùng chung mạng hoặc storage backend |
| Dedicated host/bare metal | Kiểm soát phần cứng và cô lập host tốt hơn | Chi phí và công sức vận hành cao; không bảo đảm mọi tầng đều riêng biệt |
| Serverless | Giảm việc quản lý máy chủ, tự động điều chỉnh theo request hoặc event | Ít quyền kiểm soát hạ tầng; vẫn có quota, giới hạn concurrency, cold start và dependency dùng chung |

Quyết định nên dựa trên SLO, mức độ nhạy latency, độ ổn định tải, yêu cầu tuân thủ, khả năng quan sát và tổng chi phí. Có thể ưu tiên hạ tầng dùng chung cho môi trường phát triển, tác vụ batch có thể trì hoãn hoặc workload không yêu cầu latency chặt. Với dịch vụ tạo doanh thu, xử lý giao dịch hoặc workload có SLA nghiêm ngặt, chi phí cho capacity dự phòng và cô lập tốt hơn có thể hợp lý.

## 9. Tình huống minh họa: API chậm trên node dùng chung

Một nhóm vận hành triển khai API trên cụm Kubernetes. Trong giờ cao điểm, p99 tăng mạnh và một số request timeout. CPU utilization trung bình của node chỉ ở mức vừa phải nên nhóm ban đầu cho rằng CPU không phải nguyên nhân.

Khi đối chiếu metric, nhóm phát hiện container API thường xuyên bị CPU throttling do limit đặt thấp hơn nhu cầu của các đợt xử lý ngắn. Cùng thời điểm, một workload batch trên node tạo tải CPU lớn. Nhóm kiểm tra thêm và thấy các pod API có request thấp, khiến bộ lập lịch đặt nhiều workload lên cùng node.

Nhóm xử lý theo từng bước:

1. Đo lại CPU usage, throttled time và p99 trong cùng khung tải.
2. Điều chỉnh request theo nhu cầu quan sát được và nâng limit phù hợp với ngân sách CPU của node.
3. Chuyển workload batch sang node pool riêng và giới hạn concurrency của job.
4. Giữ một phần capacity dự phòng cho API, đồng thời theo dõi queue và tỷ lệ timeout.
5. Chạy lại bài kiểm tra tải đại diện, so sánh p95/p99, throughput và chi phí trước/sau thay đổi.

Nếu p99 cải thiện sau khi tách workload và giảm throttling, giả thuyết tranh chấp CPU được củng cố. Nếu latency vẫn cao trong khi CPU đã ổn định, nhóm cần tiếp tục kiểm tra storage, mạng và dependency. Việc thay đổi cấu hình phải được đánh giá bằng metric của ứng dụng và chi phí vận hành, không chỉ bằng CPU utilization.

## 10. Nguyên tắc thiết kế và vận hành

Khi thiết kế workload trên hạ tầng dùng chung, hãy áp dụng các nguyên tắc sau:

1. **Thiết kế theo đặc tính workload:** xác định workload nhạy CPU, RAM, I/O, network hay latency trước khi chọn cấu hình.
2. **Đo ở nhiều tầng:** kết hợp metric ứng dụng, runtime, máy ảo/container và dịch vụ đám mây.
3. **Dùng SLO làm tiêu chí:** đánh giá ảnh hưởng qua latency phân vị, tỷ lệ lỗi và thời gian hoàn thành, không chỉ qua mức sử dụng tài nguyên trung bình.
4. **Cấp phát có căn cứ:** chọn request, limit, IOPS, băng thông và concurrency dựa trên tải thực tế cùng biên an toàn.
5. **Cô lập có chọn lọc:** dành node hoặc capacity chuyên biệt cho workload thật sự cần hiệu năng ổn định.
6. **Kiểm tra cả tầng phụ trợ:** autoscaling ứng dụng không giải quyết được điểm nghẽn ở database, storage, gateway hoặc quota.
7. **Theo dõi chi phí cùng hiệu năng:** so sánh chi phí trên mỗi request, mỗi job hoặc mỗi đơn vị dữ liệu xử lý khi thay đổi mức cô lập.
8. **Chuẩn bị phương án suy giảm có kiểm soát:** dùng queue, backpressure, timeout và giới hạn tải để bảo vệ dịch vụ khi năng lực dùng chung suy giảm.

Chia sẻ tài nguyên là nền tảng kinh tế của điện toán đám mây, còn noisy neighbor là một hệ quả hiệu năng cần được quản lý. Khi hiểu workload cần gì, đo đúng điểm tranh chấp và chọn mức cô lập tương ứng, đội kỹ thuật có thể tận dụng lợi ích của máy ảo, container và serverless mà vẫn duy trì hiệu năng, tính sẵn sàng và chi phí trong giới hạn mục tiêu.

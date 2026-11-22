# Instance family và lựa chọn cấu hình EC2

> **Chương:** Máy chủ EC2  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá hệ sinh thái AWS từ Region/AZ, IAM, VPC đến tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; học cách chọn dịch vụ, thiết kế, triển khai, giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Amazon Elastic Compute Cloud (**Amazon EC2**) cung cấp máy chủ ảo có thể cấu hình theo CPU, RAM, lưu trữ, mạng, hệ điều hành và mô hình mua năng lực tính toán. Chọn đúng **instance family** và **instance size** là quyết định quan trọng vì ảnh hưởng trực tiếp đến độ trễ, thông lượng, giới hạn tải, tính sẵn sàng và chi phí vận hành.

Sau bài này, bạn có thể:

1. Phân biệt **instance family**, **generation**, **processor variant** và **instance size** trong tên EC2.
2. Nhận diện các nhóm **general purpose**, **compute optimized**, **memory optimized**, **storage optimized** và **accelerated computing**, cùng trường hợp nên sử dụng.
3. Chọn cấu hình dựa trên CPU/vCPU, RAM, kiến trúc x86_64 hoặc arm64, EBS, instance store, mạng và độ sẵn sàng theo Region/AZ.
4. Giải thích đặc thù **burstable performance** của họ T và tác động của CPU credits.
5. So sánh On-Demand, Savings Plans, Reserved Instances, Spot Instances và các khoản chi phí ngoài giá máy ảo.
6. Dùng AWS CLI để đọc thông số và khả năng cung cấp của instance type; lập kế hoạch thử nghiệm và **right-sizing** có dữ liệu.
7. Đề xuất cấu hình ban đầu an toàn, có theo dõi, có phương án phục hồi và điều chỉnh sau khi đo tải.

## 1. EC2 instance type là gì?

Một **EC2 instance** là máy chủ ảo chạy trong một **Availability Zone (AZ)** thuộc Region. **Instance type** định nghĩa phần lớn khả năng phần cứng được cấp cho máy: số vCPU, dung lượng RAM, kiến trúc CPU, băng thông mạng, năng lực EBS và đặc tính lưu trữ hoặc tăng tốc chuyên dụng nếu có.

Ví dụ tên **`m7i.large`** có thể được phân tích như sau:

~~~text
m7i.large
│││ └── size: large
││└──── variant: i (dòng Intel của thế hệ này)
│└───── generation: 7
└────── family: m (general purpose)
~~~

Một số tên khác: **`c7i.large`**, **`r7i.large`**, **`m7g.large`**, **`t3.medium`**. Chúng là **ví dụ để học cách đọc**, không khẳng định đây là thế hệ mới nhất, rẻ nhất hoặc luôn còn capacity tại một AZ.

### 1.1. Bốn lớp cần phân biệt

| Thành phần | Ý nghĩa | Câu hỏi khi chọn |
|---|---|---|
| **Family** | Hướng tối ưu tài nguyên (M, C, R, T, I, P...) | Workload chủ yếu cần CPU, RAM, ổ đĩa hay GPU? |
| **Generation** | Thế hệ phần cứng/thiết kế của nhóm đó | Hiệu năng, tính năng và giá của thế hệ hiện có thay đổi ra sao? |
| **Variant** | Dòng processor hoặc đặc tính chuyên biệt; hậu tố không có ý nghĩa tuyệt đối cho mọi thế hệ | OS, thư viện và AMI có tương thích CPU/hardware không? |
| **Size** | Mức phân bổ tài nguyên trong một type, như small, medium, large, xlarge... | Cần bao nhiêu vCPU, GiB RAM và băng thông? |

Các tên instance family do AWS định nghĩa. Không suy luận mọi thông số chỉ từ tên; hãy đối chiếu **EC2 Instance Types documentation** hoặc API **`DescribeInstanceTypes`**. Chẳng hạn, số vCPU chưa phản ánh đầy đủ hiệu năng một luồng, mức turbo, CPU credits hay giới hạn I/O.

### 1.2. Một instance khác gì với một Auto Scaling group?

- **EC2 instance:** một máy ảo cụ thể, có instance ID, AMI, subnet, security group, IAM role và EBS volumes được gắn.
- **Launch template:** mẫu cấu hình để khởi tạo instance; lưu các thông số có thể tái sử dụng.
- **EC2 Auto Scaling group:** quản lý số lượng instance theo minimum/desired/maximum capacity, thay thế instance không khỏe và có thể phân bố nhiều AZ.
- **Elastic Load Balancing:** phân phối kết nối đến nhiều instance/target, giúp kiến trúc mở rộng theo chiều ngang.

Chọn instance type tốt **không thay thế** kiến trúc nhiều AZ, sao lưu hoặc giám sát. Một máy rất mạnh vẫn có thể thành **single point of failure**.

## 2. Tổng quan các nhóm EC2 instance family

### 2.1. Bảng so sánh trọng tâm

| Nhóm | Ví dụ họ | Hướng tối ưu | Workload tiêu biểu | Rủi ro khi chọn sai |
|---|---|---|---|---|
| **General purpose** | M | Cân bằng CPU, RAM, mạng | Web/API, ứng dụng doanh nghiệp, service hỗn hợp | Có thể lãng phí nếu thực tế chỉ cần CPU hoặc RAM |
| **Burstable general purpose** | T | CPU theo baseline + credits, phù hợp tải không liên tục | Dev/test, ứng dụng nhỏ có tải thấp và thỉnh thoảng tăng | Tải CPU cao kéo dài dẫn đến hết credits hoặc phí phát sinh theo chế độ |
| **Compute optimized** | C | CPU so với RAM | Xử lý batch, encoding, tính toán, game server phù hợp | Thiếu RAM nếu workload có heap/cache lớn |
| **Memory optimized** | R, X, một số họ chuyên dụng | RAM lớn theo vCPU | In-memory analytics, cache, database tự quản lý | Giá cao nhưng CPU nhàn rỗi nếu ước lượng RAM quá lớn |
| **Storage optimized** | I, D, H và các dòng liên quan | Lưu trữ cục bộ và I/O theo đặc tính từng loại | NoSQL cục bộ, log/search cần truy cập ổ nhanh hoặc dung lượng lớn | Rủi ro mất dữ liệu instance store khi instance kết thúc; cần nhân bản |
| **Accelerated computing** | G, P, Inf, Trn, F và các họ liên quan | GPU hoặc accelerator chuyên dụng | AI training/inference, đồ họa, xử lý song song, FPGA | Chi phí cao, yêu cầu runtime/driver tương thích |
| **HPC optimized** | Hpc và các dòng chuyên biệt | Tính toán khoa học, băng thông mạng/CPU cho HPC | Mô phỏng, tính toán song song, MPI | Phụ thuộc thiết kế cluster, EFA, placement và hỗ trợ Region |
| **High-memory / specialized** | U và các dòng dành cho workload đặc thù | RAM cực lớn, profile riêng | In-memory database quy mô lớn, ứng dụng đặc thù | Giá, quota, capacity, licensing và nhu cầu vận hành cao |

Các tên trong cột ví dụ là **mô hình phân nhóm**, không phải danh sách đầy đủ. Một số instance type có nhiều đặc tính đồng thời, chẳng hạn vừa hỗ trợ local NVMe vừa có CPU mạnh. Đánh giá thông số **của type cụ thể**, không chỉ family.

### 2.2. General purpose: điểm bắt đầu hợp lý

Họ **M** phù hợp khi chưa biết rõ tài nguyên nào là nút nghẽn: web server, ứng dụng Java/.NET thông dụng, API server hoặc worker có nhu cầu CPU và RAM tương đối cân đối.

Ví dụ triển khai:

- Một ứng dụng Spring Boot có API, cache nhỏ và kết nối tới RDS thường nên **bắt đầu đo tải** với M.
- Nếu đo thấy CPU thường xuyên chạm trần nhưng RAM còn dư, cân nhắc **C** hoặc tăng số replica.
- Nếu CPU không cao nhưng JVM heap/working set thường xuyên thiếu RAM, cân nhắc **R** hoặc chỉnh cấu hình bộ nhớ.

Tỷ lệ RAM/vCPU có thể khác theo thế hệ và biến thể. Không dùng một quy tắc như “mọi M đều đúng 4 GiB/vCPU” để chọn cấu hình mà không kiểm tra thông số thực.

### 2.3. Compute optimized: khi CPU là giới hạn

Họ **C** phù hợp khi mỗi request/job cần nhiều phép tính, trong khi yêu cầu RAM tương đối nhỏ, ví dụ:

- Xử lý ảnh/video mà công việc chủ yếu chạy trên CPU.
- Nén/giải nén, xử lý dữ liệu, biên dịch, các batch job tính toán.
- Web backend có thời gian CPU cao và working set gọn.
- Các thuật toán cần nhiều vCPU và scale theo luồng.

Cần đo **CPU utilization theo thời gian, số luồng thực sự chạy song song, độ trễ p95/p99 và bộ nhớ**. Một workload chỉ sử dụng một luồng có thể không tăng tốc khi tăng rất nhiều vCPU; hiệu năng trên mỗi core và thiết kế song song có thể quan trọng hơn số core.

### 2.4. Memory optimized: khi dữ liệu cần nằm trong RAM

Họ **R** và các loại memory optimized phù hợp với:

- Cache/in-memory store tự quản lý khi dữ liệu và overhead phải vừa trong RAM.
- Database hoặc search engine cần cache lớn.
- Ứng dụng JVM có heap lớn hoặc dữ liệu phiên lớn.
- Phân tích dữ liệu có working set lớn, chịu áp lực garbage collection hoặc swap.

Không chọn RAM bằng đúng kích thước dữ liệu thô. Cần cộng **OS, runtime, metadata/index, memory fragmentation, buffer/cache, replicas và peak load**. Một máy có 64 GiB RAM không có nghĩa ứng dụng có thể sử dụng an toàn toàn bộ 64 GiB cho JVM heap.

Nếu nhu cầu chính là database, cân nhắc **Amazon RDS/Aurora/DynamoDB/ElastiCache** thay cho tự quản lý database/cache trên EC2, tùy yêu cầu và mức độ kiểm soát cần thiết.

### 2.5. Storage optimized: phân biệt local storage với EBS

Một số họ **I/D/H** có ổ lưu trữ cục bộ theo instance, thường nhắm vào throughput, IOPS hoặc dung lượng. Tuy nhiên:

- **Instance store** gắn với host vật lý: dữ liệu **không tồn tại sau khi instance bị terminate**, và không nên coi đây là tầng lưu trữ bền vững độc lập; dữ liệu cũng có thể mất trong một số sự kiện lỗi host.
- **Amazon EBS** là block storage gắn theo AZ, có cơ chế độ bền, snapshot và cấu hình hiệu năng riêng; không đồng nhất với instance store.
- Một số instance type **không có instance store**; khi đó dùng EBS hoặc dịch vụ lưu trữ khác.
- Nếu workload dùng dữ liệu quan trọng trên instance store, phải có **replication, backup, khôi phục và kiểm tra chịu lỗi**.

Một hệ thống log/search có replica và cơ chế xây dựng lại index có thể tận dụng local NVMe. Một database duy nhất không có bản sao và chỉ lưu trên instance store là rủi ro vận hành lớn.

### 2.6. Accelerated computing và HPC

GPU/accelerator giúp workload có thư viện/phần mềm tận dụng tăng tốc. Ví dụ:

- **G/P:** hình ảnh, đồ họa hoặc AI tùy loại GPU; không giả định mọi G/P tương đương.
- **Inf/Trn:** các bộ tăng tốc AWS dành cho mục tiêu inference/training tương ứng, với SDK/runtime chuyên dụng.
- **Hpc:** workload mô phỏng khoa học yêu cầu hiệu năng tính toán và hạ tầng mạng phù hợp.

Trước khi chọn, kiểm tra **framework, driver, CUDA hoặc runtime liên quan, AMI, kiến trúc CPU, quota, AZ availability**, và so sánh với dịch vụ managed như SageMaker hoặc Batch nếu phù hợp.

## 3. vCPU, CPU architecture và burstable performance

### 3.1. vCPU không đồng nghĩa một core vật lý

**vCPU** là đơn vị xử lý logic được EC2 công bố cho instance type. Trên nhiều dòng x86 sử dụng simultaneous multithreading (SMT), vCPU có thể tương ứng hardware thread; trên nhiều dòng AWS Graviton, vCPU thường tương ứng một physical core. Vì vậy:

- **2 vCPU** của hai dòng CPU khác nhau không bảo đảm cùng số phép tính mỗi giây.
- Số luồng ứng dụng, hỗ trợ vector instructions, cache, CPU clock, kiến trúc memory và hiệu quả compiler đều ảnh hưởng.
- Khi xử lý Java, đo cả **GC pause, heap pressure, JIT warm-up và startup**; CPU utilization đơn lẻ chưa đủ.
- Sử dụng số liệu benchmark **trên workload thật** để quyết định khi giá/hiệu năng sát nhau.

Một số instance type hỗ trợ **CPU options** như điều chỉnh số core hoặc threads per core trong phạm vi AWS cho phép, phục vụ licensing hoặc workload đặc thù. Chỉ thay đổi khi hiểu tác động tới hiệu năng và chi phí giấy phép.

### 3.2. x86_64 và arm64: chọn theo chuỗi phụ thuộc

AWS cung cấp nhiều họ x86 dựa trên Intel/AMD và nhiều họ **AWS Graviton** dựa trên Arm. Ví dụ:

~~~text
m7i.large  -> một biến thể Intel x86_64 của họ M
m7g.large  -> một biến thể AWS Graviton arm64 của họ M
~~~

**Quy trình xác minh tương thích:**

1. Kiểm tra **Amazon Machine Image (AMI)** hỗ trợ đúng kiến trúc \`x86_64\` hoặc \`arm64\`.
2. Xác minh ứng dụng, runtime (Java JDK, Node.js, Python...), thư viện native/JNI, package và binary hỗ trợ kiến trúc đích.
3. Nếu dùng container, image phải có bản dựng phù hợp, hoặc manifest multi-architecture.
4. Kiểm tra agent, monitoring, security software, driver và dependencies của bên thứ ba.
5. Chạy benchmark và kiểm thử chức năng trước khi chuyển workload production.

**Lưu ý:** cùng mã Java bytecode thường có thể chạy trên JDK tương ứng nhiều kiến trúc, nhưng **native dependencies** và container images vẫn có thể không tương thích. Không “đổi” AMI x86 sang Arm chỉ bằng cách thay instance type.

### 3.3. CPU credits của họ T

Họ **T** cung cấp baseline CPU performance và cơ chế **CPU credits** để tăng tốc khi workload cần burst. Khái niệm cần nhớ:

- Khi dùng CPU dưới baseline, instance có thể **tích lũy credits** theo quy tắc của loại instance.
- Khi chạy vượt baseline, instance **tiêu credits** để có thêm năng lực CPU.
- Chế độ **Standard** (nếu type hỗ trợ) có thể bị giới hạn về mức sử dụng CPU sustained khi credits hết.
- Chế độ **Unlimited** cho phép hoạt động vượt baseline trong những điều kiện nhất định, nhưng có thể phát sinh **surplus CPU credit charges** nếu mức sử dụng vượt ngưỡng tính phí theo chính sách AWS.
- Các dòng T và thế hệ khác nhau có đặc điểm/thiết lập mặc định riêng; không suy luận tất cả T đều có cùng chế độ và cách tính phí.

Ví dụ:

~~~text
Workload A: CPU 5-10% phần lớn ngày, cao trong vài phút
  -> T có thể phù hợp nếu credit và chi phí được theo dõi.

Workload B: CPU 80-95% liên tục suốt nhiều giờ
  -> C hoặc M phù hợp có thể dễ dự đoán hiệu năng/giá hơn.
~~~

Theo dõi **`CPUUtilization`**, **`CPUCreditBalance`**, **`CPUSurplusCreditBalance`** và các metric liên quan khi instance type hỗ trợ. Nếu chỉ xem CPU trung bình tháng, có thể bỏ qua những lần hết credits và tăng độ trễ.

## 4. RAM, EBS, instance store và network capacity

### 4.1. Chọn RAM bằng working set và peak load

Một công thức tư duy cho máy chạy ứng dụng:

~~~text
RAM cần thiết
≈ RAM hệ điều hành + agent
  + RAM ứng dụng (heap/native/off-heap)
  + page cache/buffer
  + headroom cho peak và biến động
~~~

Không lấy một con số duy nhất từ máy phát triển làm cấu hình production. Đo:

- Resident set size (RSS), JVM heap và non-heap, mức swap và lỗi out-of-memory.
- Bộ nhớ theo container/pod nếu chạy Docker/ECS/EKS trên EC2.
- Các thời điểm peak, scale-out/scale-in và lần deploy ứng dụng.
- Cache hit rate, memory pressure, GC pause và tác động tới latency.

Đặt headroom để tránh swap và OOM killer. Nếu workload tăng trưởng theo dữ liệu, cần kế hoạch mở rộng dựa trên **dung lượng dữ liệu và số lượng instance**, không chỉ vCPU.

### 4.2. EBS throughput và EBS-optimized support

EBS có nhiều loại volume, chẳng hạn **gp3** dành cho SSD mục đích chung, **io2** cho IOPS cao theo đặc tính dịch vụ, và các loại khác phù hợp với workload riêng. Khi chọn EC2 cần xét cả:

- **Volume performance:** IOPS, throughput, size và những giới hạn có thể cấu hình của loại EBS volume.
- **Instance EBS bandwidth:** mỗi instance type có thông số băng thông EBS riêng, có thể giới hạn tổng lưu lượng tới nhiều volume.
- **Latency và hàng đợi I/O:** queue length, block size, tỷ lệ read/write và burst pattern.
- **AZ và lifecycle:** EBS volume được tạo trong một AZ và gắn vào EC2 tương thích trong AZ phù hợp; snapshot thường dùng để sao lưu/khôi phục theo quy trình.
- **Bảo mật:** bật mã hóa EBS theo tiêu chuẩn account; sử dụng IAM/KMS permissions tương ứng nếu cần.

**Ví dụ:** một volume có thông số throughput rất cao chưa chắc đạt được thông số đó khi instance có EBS throughput thấp hơn hoặc workload phát sinh I/O nhỏ, không song song. Đo cả hai đầu để tránh chi tiền cho storage mà máy không khai thác được.

### 4.3. Network performance và giới hạn kết nối

EC2 instance type công bố khả năng mạng (ví dụ mức network performance, hỗ trợ ENA và các đặc tính nâng cao). Nên xem:

- Throughput và packets-per-second trong thực tế.
- Chi phí và độ trễ lưu lượng **intra-AZ, inter-AZ, inter-Region** theo đường truyền.
- Số ENI/IP address/security group có thể gắn theo type/size khi thiết kế nhiều giao diện mạng.
- EC2 placement group/EFA khi dùng HPC hoặc workload cực nhạy với độ trễ.
- Kết nối tới RDS, S3, EFS, API Gateway và hệ thống on-premises theo tuyến VPC cụ thể.

**Không kết luận “up to X Gbps” là băng thông được bảo đảm liên tục**. AWS có thể áp dụng mức baseline/peak và giới hạn theo loại lưu lượng hoặc instance size. Kiểm tra tài liệu và benchmark.

### 4.4. Lưu trữ tạm và vòng đời instance

Phân biệt trạng thái:

| Tình huống | EBS root/data volume | Instance store |
|---|---|---|
| **Reboot** | Thông thường giữ dữ liệu | Thông thường giữ dữ liệu |
| **Stop → Start** trên EBS-backed instance | Dữ liệu trên EBS tiếp tục tồn tại theo cấu hình | Dữ liệu instance store **không được bảo đảm tồn tại** qua stop/start |
| **Terminate** | Root EBS thường có `DeleteOnTermination=true` theo cấu hình; data volume có thể giữ hoặc xóa | Dữ liệu instance store mất |
| **Host failure** | EBS và quy trình phục hồi có đặc điểm độ bền riêng | Local instance store có thể mất, cần bản sao/backup |

**Không giả định EBS root volume nào cũng bị xóa hoặc luôn được giữ**: kiểm tra `DeleteOnTermination` trên từng volume attachment. Snapshot cũng có chi phí và vòng đời riêng.

## 5. Region, Availability Zone, AMI và các ràng buộc triển khai

### 5.1. Region/AZ quyết định khả năng tạo máy

Một instance type có thể được liệt kê trong tài liệu nhưng:

- Chưa được cung cấp tại **Region** hoặc **AZ** bạn chọn.
- Bị hạn chế bởi **service quotas** theo loại vCPU/family và purchase option.
- Hết capacity On-Demand/Spot tại thời điểm khởi chạy.
- Có điều kiện riêng về Local Zone, Wavelength Zone, Outposts hoặc phần cứng chuyên dụng.

Đối với kiến trúc nhiều AZ, cần kiểm tra **instance type offerings** tại từng AZ và có phương án thay thế (ví dụ dùng tập instance types tương đương trong Auto Scaling group/Mixed Instances Policy).

Tên AZ như `ap-southeast-1a` có thể ánh xạ đến AZ vật lý khác nhau giữa các account. Khi phối hợp nhiều account, tham khảo **AZ ID** để đối chiếu vùng vật lý.

### 5.2. AMI và hệ điều hành

**AMI (Amazon Machine Image)** xác định OS và môi trường khởi chạy. Chọn AMI dựa trên:

1. Kiến trúc CPU đúng `x86_64` hoặc `arm64`.
2. OS, kernel, virtualization và hỗ trợ phần cứng phù hợp với instance type.
3. Driver/agent cần thiết, ví dụ ENA, NVMe hoặc công cụ quản trị.
4. Bản vá bảo mật, nguồn phát hành tin cậy, quy trình cập nhật và lịch vòng đời.
5. Loại boot mode, EBS/root volume và các tùy chọn được AWS hỗ trợ.

Đừng dùng một AMI được chọn trước cho mọi family mà không kiểm tra tính tương thích. Việc đổi CPU architecture hoặc driver có thể yêu cầu **AMI mới, container build mới và kiểm thử lại**.

### 5.3. Tenancy và licensing

EC2 hỗ trợ các lựa chọn tenancy/host tùy loại instance và Region, ví dụ shared, dedicated instances hoặc Dedicated Hosts. Việc lựa chọn chịu ảnh hưởng yêu cầu cô lập phần cứng, compliance, giấy phép phần mềm và chi phí.

Chạy Windows Server hoặc phần mềm có phí theo core/vCPU/host có thể khiến chi phí giấy phép quan trọng hơn giá compute thuần túy. Hãy kiểm tra quy định licensing hiện hành trước khi chuyển family hoặc thay số vCPU.

## 6. Quy trình chọn EC2 theo workload

### 6.1. Bắt đầu từ nhu cầu, không bắt đầu từ tên instance

~~~mermaid
flowchart TD
    A[Yêu cầu ứng dụng và SLO] --> B[Đo CPU, RAM, I/O, mạng, peak]
    B --> C{Nút nghẽn chính là gì?}
    C -->|Cân bằng| M[M / general purpose]
    C -->|CPU liên tục| C[C / compute optimized]
    C -->|RAM| R[R / memory optimized]
    C -->|Lưu trữ cục bộ / IOPS đặc thù| S[I / D / storage optimized]
    C -->|GPU / accelerator| G[G / P / Inf / Trn]
    C -->|Tải nhỏ, burst ngắn| T[T / burstable]
    M --> D[Kiểm tra kiến trúc, AMI, Region/AZ, quota]
    C --> D
    R --> D
    S --> D
    G --> D
    T --> D
    D --> E[Benchmark hiệu năng + đo chi phí]
    E --> F{Đáp ứng SLO và ngân sách?}
    F -->|Chưa| B
    F -->|Đạt| H[Triển khai với giám sát, backup, scaling]
~~~

Trước khi chọn family cần thu thập:

| Yếu tố | Câu hỏi cần trả lời | Số liệu/kết quả nên có |
|---|---|---|
| **Độ trễ** | p95/p99 cần dưới bao nhiêu ms? | SLO và biểu đồ latency |
| **Thông lượng** | Bao nhiêu request/giây hoặc job/giờ? | Trung bình và peak |
| **CPU** | CPU cao liên tục hay chỉ tăng ngắn hạn? | CPUUtilization, load, thread profile |
| **RAM** | Working set, heap, cache và peak ra sao? | RSS, memory peak, OOM/GC |
| **Lưu trữ** | Dữ liệu cần bền vững hay tái tạo được? IOPS/throughput? | GB, IOPS, block size, latency |
| **Mạng** | Gọi dịch vụ nào? Băng thông và lưu lượng liên AZ? | Gbps, connection count, flow metrics |
| **Kiến trúc** | App có binary native, driver, JDK và image arm64? | Compatibility matrix |
| **Vận hành** | Thời gian uptime, RTO/RPO, số AZ? | SLA/SLO, kế hoạch failover |
| **Chi phí** | Ngân sách tháng, tính ổn định của tải? | TCO compute + storage + network |

### 6.2. Năm tình huống chọn ban đầu

**Tình huống A — API Java/Spring Boot:** ứng dụng REST xử lý đơn hàng, dùng RDS bên ngoài EC2, peak theo giờ làm việc. **Bắt đầu từ M** với RAM đủ cho JDK, heap, OS và agent. Benchmark request load, CPU, GC và p99; nếu CPU cao, RAM còn dư, cân nhắc C. Cần HA thì dùng ≥2 AZ, Auto Scaling + load balancer.

**Tình huống B — Batch tính toán:** xử lý ảnh và xuất báo cáo bằng CPU, job được chia nhỏ, không cần RAM lớn. **Bắt đầu từ C**, kiểm tra mức song song. Nếu có thể retry, cân nhắc **Spot** hoặc AWS Batch; lưu kết quả bền vững ở S3/EBS thích hợp, không phụ thuộc một instance.

**Tình huống C — In-memory cache tự quản lý:** phần dữ liệu nóng lớn, CPU vừa phải. **Bắt đầu từ R** hoặc loại memory-optimized chuyên dụng; thiết kế replication, disk persistence nếu cần và phương án phục hồi. Cân nhắc ElastiCache khi muốn AWS quản lý vận hành.

**Tình huống D — ML inference:** mô hình cần GPU hoặc accelerator chuyên biệt và latency ổn định. **Thử G/Inf hoặc dịch vụ managed** dựa trên model, framework, throughput, batch size và runtime; so với CPU inference thực tế trước khi chọn.

**Tình huống E — Dev/test không thường xuyên:** API nhỏ được chạy trong giờ học, tải thấp và đôi lúc burst. **T** có thể thích hợp, nhưng kiểm tra CPU credits, chế độ Unlimited và phí đi kèm. Nếu chỉ chạy các job ngắn, cân nhắc Lambda, ECS Fargate hoặc tắt EC2 ngoài giờ.

Những đề xuất trên là **điểm bắt đầu thử nghiệm**, không phải đáp án cố định cho mọi workload.

## 7. So sánh giá và mô hình mua EC2

### 7.1. Purchase options

| Mô hình | Cơ chế chính | Khi phù hợp | Điều phải cân nhắc |
|---|---|---|---|
| **On-Demand** | Trả tiền theo mức sử dụng, không cần cam kết dài hạn | Lab, thử nghiệm, workload thay đổi | Giá có thể cao hơn phương án cam kết cho tải đều |
| **Savings Plans** | Cam kết mức chi tiêu compute theo kỳ hạn/điều kiện của gói | Mức sử dụng ổn định, cần tối ưu hóa | Cam kết chi phí, phạm vi linh hoạt khác nhau theo loại Savings Plan |
| **Reserved Instances (RI)** | Tùy loại RI, hưởng ưu đãi chi phí hoặc đặt trước capacity theo điều kiện cụ thể | Workload dự đoán ổn định | Cam kết, điều khoản, Region/AZ, family/size flexibility tùy loại |
| **Spot Instances** | Sử dụng capacity EC2 còn dư, giá biến động | Batch, queue workers, CI jobs, stateless nodes có thể bị gián đoạn | AWS có thể thu hồi capacity; cần checkpoint/retry/fallback |
| **Dedicated Hosts/Instances** | Tài nguyên phần cứng/tenancy chuyên dụng theo lựa chọn | Licensing hoặc compliance đặc biệt | Chi phí và quản lý capacity khác |

**Savings Plans không tự bảo đảm capacity**; giảm giá và bảo đảm capacity là hai vấn đề khác nhau. Nếu cần bảo đảm capacity tại AZ, nghiên cứu **On-Demand Capacity Reservations** theo điều kiện và chi phí riêng.

**Spot Instances** có thể bị gián đoạn khi AWS cần lại capacity; nhiều trường hợp có thông báo gián đoạn khoảng **hai phút** (tùy hành động/loại thông báo). Ứng dụng phải coi việc mất instance là sự kiện có thể xảy ra, checkpoint ra S3/EBS thích hợp hoặc dùng queue có retry. Không chạy thành phần duy nhất không thể khôi phục trên Spot.

### 7.2. Tổng chi phí thực tế

Không tính giá EC2 instance một mình. Một phép ước lượng:

~~~text
Tổng chi phí workload theo tháng
≈ số giờ instance * giá tính toán áp dụng
  + EBS volumes và snapshots
  + lưu lượng truyền dữ liệu / NAT / load balancing / public IPv4
  + CloudWatch metrics, logs, alarms, tracing
  + bản quyền phần mềm và dịch vụ hỗ trợ
  + các tài nguyên AWS khác mà ứng dụng dùng
~~~

Cụ thể:

- EBS có thể tiếp tục tính phí khi instance bị **stop**; snapshot cũng tồn tại độc lập.
- **Public IPv4 address** có thể phát sinh phí theo biểu giá AWS, kể cả khi dùng Elastic IP; không giả định public IP là miễn phí.
- Truyền dữ liệu giữa AZ, ra Internet hoặc qua NAT/Load Balancer có thể tạo chi phí đáng kể.
- Khi instance chạy không đều, lịch bật/tắt có thể tiết kiệm hơn cố chọn một family rẻ theo giờ.
- Đừng nhầm “Free Tier” với hạn mức miễn phí vô điều kiện; eligibility và điều kiện ưu đãi thay đổi theo account/chương trình/thời điểm.

Dùng **AWS Pricing Calculator**, trang EC2 pricing của Region, **Cost Explorer** và **AWS Budgets** để dự báo/giám sát. Budget cảnh báo chi tiêu, **không mặc định chặn mọi khoản phí**.

### 7.3. Tối ưu giá/hiệu năng

Mục tiêu không phải instance rẻ nhất mỗi giờ, mà là **chi phí trên một đơn vị công việc đáp ứng SLO**:

~~~text
Cost per successful request
≈ tổng chi phí workload trong kỳ
  / số request thành công trong kỳ

Cost per completed job
≈ tổng chi phí batch trong kỳ
  / số job hoàn thành hợp lệ
~~~

Ví dụ máy C giá giờ cao hơn T nhưng hoàn thành batch nhanh hơn đáng kể có thể rẻ hơn theo mỗi job. Tương tự, máy R giá cao nhưng giảm lỗi OOM/GC và giảm lượng replica có thể tốt hơn về tổng chi phí.

## 8. Bảo mật, monitoring và phục hồi sau khi chọn type

### 8.1. Cấu hình an toàn tối thiểu

Một cấu hình EC2 ban đầu nên có:

1. **IAM role qua instance profile** với least privilege; tránh nhúng access key dài hạn vào user data/AMI.
2. **Security group** chỉ mở cổng cần thiết, ưu tiên SSM Session Manager thay vì mở SSH 22/RDP 3389 cho Internet.
3. **IMDSv2** để ứng dụng/agent lấy metadata và credentials an toàn hơn; kiểm tra tương thích SDK/agent.
4. **EBS encryption** và quản trị KMS keys theo chính sách tổ chức.
5. AMI được vá, cập nhật tự động hoặc theo lịch kiểm soát, giới hạn quyền hệ điều hành.
6. VPC subnet/route table phù hợp: private subnets nếu workload không cần inbound Internet trực tiếp; cấu hình NAT/VPC endpoints theo nhu cầu truy cập dịch vụ.
7. Tag nhất quán, ví dụ **Project=aws-lab**, **Environment=dev**, **Owner=team-cloud**, **ManagedBy=iac** và **CostCenter=training**.

### 8.2. Các metric nên theo dõi

| Nhóm | Chỉ số gợi ý | Cách dùng |
|---|---|---|
| **CPU** | CloudWatch `CPUUtilization`; credit metrics cho T nếu có | Tìm sustained CPU load và rủi ro credits |
| **RAM** | Memory used/RSS/heap qua CloudWatch Agent, SSM hoặc telemetry ứng dụng | Nhận biết OOM, memory leak và áp lực GC |
| **Disk/EBS** | Queue, read/write ops/bytes, latency, available space | Tìm bottleneck EBS/instance store, tránh đầy ổ |
| **Network** | NetworkIn/NetworkOut, packet metrics và application errors | Phát hiện saturation hoặc traffic bất thường |
| **App latency** | p95/p99, throughput, error rate | Đo SLO thực tế thay vì chỉ đo máy |
| **Health** | EC2 status checks, ALB target health, instance recovery signals | Kích hoạt cảnh báo và thay thế instance có lỗi |

**CloudWatch EC2 basic monitoring** không mặc định cung cấp đầy đủ **RAM hoặc filesystem usage** của guest OS; cần cài agent/telemetry phù hợp nếu muốn giám sát. Kiểm tra tần suất lấy mẫu và chi phí logs/custom metrics.

### 8.3. Tính sẵn sàng và khôi phục

- Với stateless web/API, dùng **Auto Scaling group nhiều AZ + load balancer** để thay thế instance và chịu lỗi một máy/AZ theo thiết kế.
- Đối với stateful workload, lưu dữ liệu trên lớp bền vững thích hợp, sao lưu/snapshot và **diễn tập restore**. EBS volume thuộc một AZ; snapshot có thể phục vụ quy trình phục hồi theo khả năng AWS hỗ trợ.
- Dùng launch template/IaC và AMI phù hợp để **recreate** instance. Đừng dựa vào cấu hình thủ công chỉ có trên một máy.
- Chọn instance type thay thế cho trường hợp hết capacity trong AZ; cân nhắc **multiple instance types** trong Auto Scaling.
- Xác định **RTO** (thời gian phục hồi) và **RPO** (mức mất dữ liệu chấp nhận) để quyết định bố trí replica, backup, monitoring.

## 9. Thực hành chỉ đọc với AWS CLI: so sánh instance types

Bài thực hành bên dưới ưu tiên **không tạo tài nguyên EC2**, nhằm tránh chi phí ngoài ý muốn. Bạn cần AWS CLI v2 đã được cấu hình qua IAM Identity Center/role hoặc phiên CloudShell có quyền đọc EC2, ít nhất \`ec2:DescribeInstanceTypes\`, \`ec2:DescribeInstanceTypeOfferings\`.

### Bước 1 — Xác minh danh tính và Region

Ví dụ dùng Bash:

~~~bash
export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1

aws sts get-caller-identity --profile "$AWS_PROFILE"
aws configure list --profile "$AWS_PROFILE"
~~~

Kiểm tra \`Account\` và \`Arn\` thuộc sandbox mong muốn. Nếu dùng **CloudShell** với danh tính đăng nhập sẵn, bỏ \`export AWS_PROFILE=...\` và các \`--profile\` tương ứng khi không tồn tại profile \`aws-lab-dev\`.

### Bước 2 — Đọc thông số CPU, RAM, architecture, EBS và network

~~~bash
aws ec2 describe-instance-types \
  --instance-types t3.medium m7i.large c7i.large r7i.large m7g.large \
  --region ap-southeast-1 \
  --query "InstanceTypes[].{Type:InstanceType,vCPU:VCpuInfo.DefaultVCpus,RAM_MiB:MemoryInfo.SizeInMiB,Arch:ProcessorInfo.SupportedArchitectures,Network:NetworkInfo.NetworkPerformance,EBS:EbsInfo.EbsOptimizedSupport,LocalStorage:InstanceStorageSupported}" \
  --output table
~~~

**Đọc kết quả:**

- **RAM_MiB** là dung lượng tính bằng MiB; để đổi sang GiB, chia cho **1024**.
- **Arch** cho biết kiến trúc AMI có thể phù hợp.
- **Network** là thông tin phân loại/băng thông công bố; cần kiểm tra bandwidth baseline/peak nếu quyết định phụ thuộc mạng.
- **EBS** cho biết khả năng EBS optimization; chưa đủ để kết luận IOPS/throughput.
- **LocalStorage** giúp phân biệt instance có hỗ trợ instance store hay không.

Nếu một type không được API chấp nhận hoặc không có trong Region, tham khảo tài liệu/offerings của Region và chọn một type có cùng vai trò tương đương; không cần ép dùng đúng các tên ví dụ.

### Bước 3 — Kiểm tra type có được cung cấp tại AZ không

~~~bash
aws ec2 describe-instance-type-offerings \
  --region ap-southeast-1 \
  --location-type availability-zone \
  --filters "Name=location,Values=ap-southeast-1a" "Name=instance-type,Values=m7i.large,m7g.large,c7i.large" \
  --query "InstanceTypeOfferings[].{Type:InstanceType,AZ:Location}" \
  --output table
~~~

Kết quả liệt kê instance types được công bố tại AZ đó. **Có trong offerings không đồng nghĩa chắc chắn khởi chạy được ngay**: quota, capacity, AMI, purchasing option, subnet và giới hạn khác vẫn cần kiểm tra. Tên AZ ở tài khoản của bạn có thể khác ánh xạ vật lý của account khác.

### Bước 4 — Tạo bảng so sánh của riêng bạn

Ghi lại dữ liệu trả về theo mẫu sau (con số minh họa, phải thay bằng kết quả CLI):

| Ứng viên | Family | vCPU / RAM (kiểm tra bằng API) | Kiến trúc | Lý do thử nghiệm |
|---|---|---|---|---|
| `t3.medium` | T | Đọc từ API | x86_64 | Lab/tải biến động, theo dõi credits |
| `m7i.large` | M | Đọc từ API | x86_64 | Baseline ứng dụng cân bằng |
| `c7i.large` | C | Đọc từ API | x86_64 | Ứng viên cho CPU-heavy jobs |
| `r7i.large` | R | Đọc từ API | x86_64 | Ứng viên cho memory-heavy |
| `m7g.large` | M | Đọc từ API | arm64 | So sánh price/performance nếu tương thích |

Cùng một workload, hãy viết **giả thuyết kiểm thử**: “C sẽ giảm thời gian job vì CPU là bottleneck”, “R sẽ giảm lỗi OOM”, hoặc “Graviton giảm chi phí/request nếu thư viện hỗ trợ”. Sau đó mới đo tải bằng công cụ được phép.

### Bước 5 — Đánh giá và đưa ra quyết định

Đề xuất **scorecard** trước khi mua hoặc triển khai:

| Tiêu chí | Trọng số tham khảo | Nguồn đo |
|---|---:|---|
| Đạt p95/p99 latency và throughput | 30% | Load test / APM |
| Không thiếu RAM hoặc chịu GC/OOM | 20% | OS/JVM telemetry |
| CPU/I/O/network đủ headroom khi peak | 20% | CloudWatch + OS metrics |
| Chi phí/request hoặc job | 20% | Pricing Calculator + đo thử |
| Khả năng cung cấp và vận hành | 10% | AZ offerings, quota, AMI, HA |

Trọng số thay đổi theo bài toán; với batch, throughput/chi phí có thể quan trọng hơn p99 latency. **Không chọn theo tổng điểm nếu một yêu cầu bắt buộc như bảo mật, SLA hoặc tương thích kiến trúc chưa đạt.**

Nếu có quyền và môi trường lab cho phép chạy benchmark thực tế, chỉ tạo các instance có cấu hình và thời gian dọn được dự trù trước; kiểm tra giá, EBS, public IPv4, Region/AZ và quyền trước khi khởi chạy. Đây là lựa chọn mở rộng; phần thực hành cốt lõi ở trên không yêu cầu tạo máy.

## 10. Bài tập tình huống: chọn EC2 cho ứng dụng nhiều lớp

Một hệ thống học tập trực tuyến có:

- **Web/API** dùng Java, từ vài chục đến vài nghìn request/phút tùy giờ học.
- **Worker** tạo thumbnail/đóng gói video theo hàng đợi, có thể retry.
- **Redis/cache** chứa dữ liệu được truy cập thường xuyên.
- **RDS** lưu dữ liệu học viên (đang dùng managed database, không đặt chung trên EC2).
- **S3** chứa video/tài liệu và log xuất báo cáo.
- Yêu cầu sẵn sàng khi một instance lỗi, triển khai qua hai AZ, có cảnh báo và kiểm soát chi phí.

### 10.1. Đề xuất ban đầu

| Thành phần | Họ EC2 gợi ý ban đầu | Cách mở rộng / vận hành | Vì sao |
|---|---|---|---|
| Web/API Java | **M** (cân bằng) | Auto Scaling ≥2 AZ, ALB, đo p99/heap | Cân bằng CPU và RAM, có đường scale-out |
| Worker xử lý video CPU | **C** | Queue, retry, Spot khi chịu gián đoạn | Công việc tính toán, có thể chia nhỏ |
| Redis/cache tự quản lý | **R** hoặc dịch vụ managed | Replication, backup, failover | Working set lớn trong RAM |
| Dữ liệu nghiệp vụ | **RDS**, không bắt buộc EC2 | Multi-AZ/backups theo SLO | Giảm gánh nặng tự quản lý DB |
| Video và object | **S3**, không đặt trên instance store | IAM least privilege, lifecycle theo nhu cầu | Tách dữ liệu khỏi vòng đời instance |

Khi đo:

- Nếu API CPU cao liên tục và heap ổn định, thử **C** và đo lại.
- Nếu API thường xuyên OOM/GC pause, thử **R** hoặc điều chỉnh memory profile/số replica.
- Nếu worker GPU-accelerated giúp giảm chi phí/job, benchmark G/P so với C thay vì chọn theo nhãn.
- Nếu Redis rất quan trọng, cân nhắc **ElastiCache** thay vì một máy R duy nhất.

### 10.2. Câu hỏi thảo luận

1. Vì sao không gộp API, Redis và database vào một EC2 lớn?
2. Nếu worker có thể bị hủy giữa chừng, cần thiết kế queue/checkpoint như thế nào để dùng Spot an toàn?
3. Một máy R có RAM gấp đôi nhưng CPU sử dụng thấp có phải luôn tối ưu về giá?
4. Nếu muốn chuyển ứng dụng Java từ x86 sang Graviton, cần kiểm thử những phụ thuộc nào?
5. Phí EBS, data transfer, NAT/ALB và public IPv4 có thể ảnh hưởng phép so sánh “máy nào rẻ” ra sao?
6. Khi một AZ thiếu capacity cho type đã chọn, kiến trúc có đường dự phòng gì?

## 11. Các lỗi lựa chọn EC2 thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| CPU cao và p99 tăng mạnh dù RAM còn nhiều | Chọn M/R nhưng workload CPU-heavy hoặc không đủ replica | So sánh C, scale-out, profile CPU và thread |
| CPU thấp nhưng máy OOM hoặc swap | Thiếu RAM/heap tuning, memory leak | Đo RSS/heap/GC; cân nhắc R, sửa ứng dụng |
| Tải liên tục trên T chậm dần hoặc tăng phí | CPU credits và chế độ Unlimited | Xem CPU credit metrics, chuyển M/C nếu phù hợp |
| I/O chậm dù EBS volume rất mạnh | Băng thông EBS instance hoặc cấu trúc I/O là nút nghẽn | Đo giới hạn instance/volume, queue và block size |
| Không boot được khi chuyển sang Graviton | AMI/container/native binary chưa hỗ trợ arm64 | Chọn AMI arm64, build multi-arch và kiểm thử |
| Instance type không thể khởi chạy tại AZ | Không được hỗ trợ, thiếu quota/capacity hoặc cấu hình sai | Kiểm tra offerings, quota, AMI, AZ và type thay thế |
| Giá EC2 thấp nhưng hóa đơn cao | EBS, snapshots, data transfer, NAT, public IPv4, logging | Tính TCO, xem Cost Explorer theo service/tag |
| Sau terminate vẫn có tài nguyên tính phí | EBS data volume, snapshot, Elastic IP hoặc thành phần phụ còn tồn tại | Kiểm tra vòng đời và dọn tài nguyên theo checklist |
| Spot node biến mất, mất công việc | Không checkpoint/retry, workload stateful | Dùng queue, checkpoint, đa loại instance/On-Demand fallback |
| Ứng dụng gián đoạn khi một AZ lỗi | Chỉ chạy một instance hoặc state nằm cục bộ | Nhiều AZ, ALB/ASG, lưu trạng thái bên ngoài và thử failover |

## 12. Checklist quyết định và tự kiểm tra

Trước khi duyệt một instance type:

- [ ] Đã xác định CPU, RAM, disk, network, peak, p95/p99 và SLO.
- [ ] Đã chọn family theo **bottleneck thực tế**, không theo tên “mạnh hơn”.
- [ ] Đã xác minh **AMI/OS/driver/runtime** tương thích với x86_64 hoặc arm64.
- [ ] Đã xem **Region/AZ offerings**, service quota và khả năng thay thế type.
- [ ] Đã đánh giá **EBS throughput**, instance store và yêu cầu độ bền dữ liệu.
- [ ] Đã lựa chọn purchase option phù hợp với thời gian chạy và khả năng chịu gián đoạn.
- [ ] Đã tính EBS, public IPv4, NAT, data transfer, monitoring và phí software.
- [ ] Đã cấu hình IAM role, security group, IMDSv2, mã hóa EBS và patch management phù hợp.
- [ ] Đã có monitoring CPU/RAM/I/O/network/app, alert và kế hoạch right-sizing.
- [ ] Đã có backup, Auto Scaling/multi-AZ nếu cần, phương án phục hồi và dọn tài nguyên sau lab.

**Tự kiểm tra kiến thức:**

1. `m7i.large` biểu diễn những thành phần nào và vì sao kích thước lớn hơn chưa chắc tối ưu?
2. Khi nào T phù hợp hơn C? CPU credits có thể ảnh hưởng hiệu năng/chi phí thế nào?
3. Khi tăng EBS IOPS nhưng throughput không tăng, còn giới hạn nào ở instance phải kiểm tra?
4. Vì sao cùng 2 vCPU trên x86_64 và Arm không đồng nghĩa cùng hiệu năng?
5. Với dữ liệu cần bền vững, vì sao không nên chỉ lưu một bản trên instance store?
6. Spot, Savings Plans và Capacity Reservations phục vụ những mục tiêu khác nhau ra sao?
7. Metric nào giúp phân biệt thiếu CPU, thiếu RAM và thiếu năng lực network/disk?
8. Lý do nào khiến một EC2 instance type được liệt kê trong Region nhưng chưa chắc khởi chạy được ở AZ?
9. Vì sao chi phí thật cần tính EBS, network và public IPv4, thay vì chỉ giá EC2?
10. Làm thế nào để một ứng dụng EC2 có khả năng phục hồi khi một instance hoặc AZ ngừng hoạt động?

**Kết quả mong đợi:** bạn có thể lựa chọn **family → type/size → AMI/architecture → storage/network → purchase option**, giải thích bằng dữ liệu workload, kiểm tra bằng API/benchmark và xác định các biện pháp bảo mật, giám sát, phục hồi, tối ưu chi phí cần đi kèm.

## Tài liệu AWS chính thức

- [Amazon EC2 instance types](https://docs.aws.amazon.com/ec2/latest/instancetypes/instance-types.html)
- [Amazon EC2 instance type naming conventions](https://docs.aws.amazon.com/ec2/latest/instancetypes/instance-type-names.html)
- [Amazon EC2 user guide — Instance types](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instance-types.html)
- [Amazon EC2 burstable performance instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-performance-instances.html)
- [Amazon EBS volume types](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volume-types.html)
- [EC2 Spot Instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-spot-instances.html)
- [Amazon EC2 Auto Scaling](https://docs.aws.amazon.com/autoscaling/ec2/userguide/what-is-amazon-ec2-auto-scaling.html)
- [AWS Compute Optimizer — EC2 recommendations](https://docs.aws.amazon.com/compute-optimizer/latest/ug/view-ec2-recommendations.html)
- [AWS EC2 pricing](https://aws.amazon.com/ec2/pricing/)
- [AWS Pricing Calculator](https://calculator.aws/)
- [Amazon CloudWatch metrics for EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/viewing_metrics_with_cloudwatch.html)

> **Lưu ý áp dụng:** Instance families, generations, Region/AZ availability, giá, giới hạn EBS/network và các chương trình ưu đãi được AWS cập nhật theo thời gian. Các tên instance trong bài dùng để minh họa cách lựa chọn; khi triển khai thực tế hãy lấy thông số, khả năng cung cấp và giá **hiện hành** từ AWS, rồi kiểm thử với workload của bạn.

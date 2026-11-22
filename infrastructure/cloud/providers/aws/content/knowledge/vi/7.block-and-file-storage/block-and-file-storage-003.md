# EBS IOPS, throughput và tối ưu hiệu năng

> **Chương:** Lưu trữ block và file  
> **Module:** CLOUD_PROVIDERS_AWS — học cách thiết kế hạ tầng AWS từ Region/AZ, IAM, VPC đến tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; đưa ra quyết định dựa trên an toàn, giám sát, khả năng phục hồi và chi phí.

## Mục tiêu học tập

**Amazon Elastic Block Store (Amazon EBS)** cung cấp block storage bền vững để dùng với những workload được AWS hỗ trợ, thường là EC2. Tăng dung lượng EBS không nhất thiết tăng hiệu năng; mua thêm IOPS cũng chưa chắc làm ứng dụng nhanh hơn. Để tối ưu, người vận hành phải hiểu mối quan hệ giữa **IOPS**, **throughput**, **latency**, **I/O size**, **queue depth** và giới hạn phía **EC2 instance**.

Sau bài học, bạn có thể:

1. Tính gần đúng throughput từ IOPS và kích thước I/O; dùng Little's Law để giải thích queue depth và latency.
2. So sánh các loại EBS phổ biến: **gp3, gp2, io2, io1, st1 và sc1** theo kiểu truy cập và cách tính hiệu năng.
3. Xác định nút nghẽn nằm ở volume, EC2 instance, filesystem, ứng dụng hay mạng lưu trữ.
4. Đọc các chỉ số **CloudWatch EBS**, phân biệt trung bình, đỉnh tải, độ trễ, queue length và mức tiêu thụ burst credits.
5. Lựa chọn dung lượng, IOPS, throughput và EC2 instance thích hợp cho database, web, batch và phân tích dữ liệu.
6. Dùng AWS CLI để xem thông số, quan sát metric và kiểm thử bằng **fio** trên volume lab riêng.
7. Lập kế hoạch thay đổi cấu hình, bảo vệ dữ liệu, giám sát kết quả và kiểm soát chi phí.

## 1. Đặt EBS vào đường đi I/O của ứng dụng

EBS là **block device**: hệ điều hành nhìn thấy thiết bị khối và có thể tạo phân vùng, filesystem rồi mount. Một EC2 instance thường gắn volume EBS làm ổ hệ điều hành hoặc ổ dữ liệu. Thông thường volume EBS thuộc **một Availability Zone**, được gắn vào instance ở AZ tương ứng; volume được dịch vụ sao chép dữ liệu bên trong AZ để tăng độ bền.

~~~mermaid
flowchart LR
    A[Ứng dụng: DB / web / batch] --> B[Filesystem / page cache]
    B --> C[Block I/O: kernel + NVMe driver]
    C --> D[EC2 EBS bandwidth / IOPS limit]
    D --> E[EBS volume performance]
    E --> F[Khối dữ liệu trên EBS]
    G[CloudWatch & OS telemetry] -. Quan sát .-> A
    G -. Quan sát .-> C
    G -. Quan sát .-> D
    G -. Quan sát .-> E
~~~

Không phải tất cả I/O của ứng dụng đều trở thành EBS I/O: **page cache**, buffer, filesystem metadata, cơ chế flush và batching có thể thay đổi số lệnh truy cập thực sự. Vì vậy, số lượng request HTTP hoặc truy vấn SQL không bằng trực tiếp IOPS EBS.

**Ví dụ:** 10.000 request/giây trong API không có nghĩa ổ cần 10.000 IOPS. Nếu phần lớn dữ liệu đã nằm trong RAM cache, EBS có thể chỉ nhận một phần nhỏ truy cập. Ngược lại, một truy vấn SQL có thể đọc nhiều page và tạo hàng trăm I/O.

### 1.1. So sánh block storage, file storage và object storage

| Dịch vụ | Kiểu truy cập | Tình huống phù hợp | Điểm cần nhớ |
|---|---|---|---|
| **Amazon EBS** | Block device/volume, thường gắn EC2 | Root disk, database tự quản lý, ứng dụng cần filesystem cục bộ | Volume theo AZ; tính hiệu năng theo loại volume và giới hạn instance |
| **Amazon EFS** | File storage qua NFS | Nhiều máy Linux chia sẻ file, cấu trúc thư mục | Kiểu truy cập mạng/file, mô hình hiệu năng và chi phí khác EBS |
| **Amazon FSx** | File storage managed theo từng hệ thống file | Windows SMB, Lustre/HPC, OpenZFS, ONTAP tùy nhu cầu | Chọn theo protocol, hiệu năng và hệ sinh thái |
| **Amazon S3** | Object API | File tĩnh, backup, data lake, tài liệu, media | Không phải block device mặc định; khác cơ chế IOPS/filesystem |
| **EC2 instance store** | Ổ lưu trữ vật lý gắn host, nếu type hỗ trợ | Scratch, cache hoặc dữ liệu có bản sao | Không dùng làm bản dữ liệu bền vững duy nhất |

EBS có cơ chế **Multi-Attach** cho một số loại volume và instance được hỗ trợ, nhưng không có nghĩa các instance được phép tự do cùng ghi vào cùng filesystem thông thường. Mục tiêu bài học là EBS cho trường hợp **một workload, một hoặc nhiều volume**; Multi-Attach được đề cập trong phần giới hạn.

## 2. Bốn đại lượng quyết định hiệu năng

### 2.1. IOPS: số thao tác I/O mỗi giây

**IOPS (Input/Output Operations Per Second)** đo số thao tác đọc/ghi khối trong một giây. Đây là đại lượng đáng quan tâm với **I/O nhỏ, ngẫu nhiên**, như database đọc page 4–16 KiB, index hoặc metadata.

~~~text
IOPS thực đo = (số read operations + số write operations) / số giây
~~~

**3.000 IOPS** nghĩa là trung bình khoảng 3.000 thao tác được xử lý mỗi giây trong khoảng đo, không tự nói lên mỗi thao tác lớn bao nhiêu byte hoặc mất bao nhiêu mili giây.

Chú ý: ứng dụng, hệ điều hành và EBS có thể chia/tổng hợp I/O. **Kích thước I/O** và **điểm đo** ảnh hưởng đến số ops hiển thị; cần so sánh trên cùng đặc tính workload.

### 2.2. Throughput: dung lượng dữ liệu xử lý mỗi giây

**Throughput** thường tính bằng **MiB/s** hoặc **MB/s**. MiB sử dụng cơ số 2: **1 MiB = 1.048.576 byte**; MB thường sử dụng cơ số 10: **1 MB = 1.000.000 byte**. Khi so sánh số liệu, xác nhận đơn vị AWS dùng.

Công thức gần đúng cho I/O đồng cỡ:

~~~text
Throughput (MiB/s)
≈ IOPS × I/O size (KiB) / 1024
~~~

Ví dụ cùng **3.000 IOPS**:

| Kích thước I/O trung bình | Throughput lý thuyết từ 3.000 IOPS |
|---|---:|
| 4 KiB | 11,72 MiB/s |
| 16 KiB | 46,88 MiB/s |
| 64 KiB | 187,5 MiB/s |
| 256 KiB | 750 MiB/s |

Nếu volume đang bị giới hạn throughput **125 MiB/s**, hàng có 64 KiB hoặc 256 KiB **không thể tự động đạt** con số lý thuyết đó. IOPS, throughput và giới hạn instance cùng tác động đến tốc độ thực tế.

### 2.3. Latency: độ trễ của một I/O

**Latency** là thời gian hoàn thành một thao tác từ khi gửi đến khi nhận kết quả. Đơn vị thường là ms hoặc µs.

Một workload có 1.000 IOPS với latency vài trăm ms có thể kém trải nghiệm hơn workload 800 IOPS với latency rất thấp. Khi tối ưu database trực tuyến, ngoài throughput và IOPS cần quan sát **p95/p99 latency** ở tầng ứng dụng và độ trễ lưu trữ.

Độ trễ cao có thể đến từ:

- Queue dài ở ứng dụng, kernel hoặc thiết bị.
- EBS volume hết ngân sách IOPS/throughput.
- EC2 instance chạm giới hạn EBS bandwidth/IOPS.
- File system sync, lock contention, fsync hoặc dirty-page flush.
- I/O phải truy xuất dữ liệu snapshot chưa được chuẩn bị đầy đủ.
- Workload có pattern đọc/ghi nhỏ/ngẫu nhiên gây nhiều thao tác hoặc queue contention.

Không giả định mỗi lần tăng IOPS sẽ giảm latency; có thể bottleneck nằm ở chỗ khác.

### 2.4. Queue depth: số I/O đang chờ xử lý

**Queue depth (QD)** là số thao tác I/O đang outstanding. Để tận dụng nhiều IOPS, nhiều hệ thống cần gửi đủ I/O song song. Một quan hệ gần đúng từ **Little's Law**:

~~~text
Outstanding I/O ≈ IOPS × latency (giây)
~~~

Ví dụ: mục tiêu **5.000 IOPS** với latency trung bình **2 ms = 0,002 s** thì cần khoảng **10 I/O đồng thời** trong trạng thái ổn định. Nếu chỉ phát sinh một yêu cầu ở một thời điểm, thông lượng IOPS có thể bị giới hạn bởi thời gian chờ từng I/O.

**Quan trọng:** tăng QD quá cao có thể tăng latency và làm quá tải ứng dụng. Không cố đẩy QD lên cực đại chỉ để đạt một số IOPS đẹp khi SLO p99 đang bị ảnh hưởng.

### 2.5. Bốn đại lượng phải đọc cùng nhau

| Workload | Kích thước I/O | Chỉ số thường quan trọng | Khi nào nghi ngờ bottleneck? |
|---|---|---|---|
| Database OLTP | Nhỏ, random, mix read/write | IOPS và latency | DB wait I/O cao, queue tăng, p99 query xấu |
| Sao lưu hoặc quét dữ liệu lớn | Lớn, tuần tự | Throughput MiB/s | Throughput plateau dù tăng số worker |
| Web server có cache | I/O không đều | Latency tail và burst behavior | Deploy/log rotation gây spike |
| Search index | Mix nhỏ/ngẫu nhiên và tuần tự | IOPS, throughput, latency | Index build hoặc merge làm queue dài |
| Data pipeline/batch | Thường tuần tự, nhiều worker | Throughput và thời gian job | Volume hoặc EC2 bandwidth bão hòa |

## 3. Những giới hạn cùng quyết định tốc độ thực tế

Có thể hình dung trần throughput:

~~~text
Throughput thực tế
≤ min(
    IOPS đủ khả dụng × kích thước I/O hiệu dụng,
    trần throughput của EBS volume,
    trần EBS bandwidth của EC2 instance,
    giới hạn OS/filesystem/ứng dụng và các yếu tố khác
  )
~~~

Tương tự với IOPS, tốc độ thực tế không vượt quá khả năng của **volume**, **instance**, và nguồn phát yêu cầu I/O của ứng dụng.

~~~mermaid
flowchart TD
    A[Ứng dụng đang chậm] --> B[Đo kích thước I/O + read/write mix]
    B --> C[Đo IOPS, MiB/s, latency, queue]
    C --> D{Giới hạn nào chạm trước?}
    D -->|Volume IOPS| E[Tăng IOPS hoặc đổi loại volume]
    D -->|Volume throughput| F[Tăng throughput hoặc đổi volume]
    D -->|EC2 EBS limit| G[Chọn instance EBS bandwidth cao hơn]
    D -->|Ứng dụng / filesystem| H[Tune cache, batching, concurrency, query]
    E --> I[Benchmark lại và đo chi phí]
    F --> I
    G --> I
    H --> I
~~~

**Ví dụ số:** workload ghi I/O **256 KiB** và cần **250 MiB/s**. Mức IOPS tối thiểu lý thuyết khoảng:

~~~text
250 MiB/s × 1024 KiB/MiB ÷ 256 KiB = 1.000 IOPS
~~~

Nếu volume chỉ có throughput **125 MiB/s**, tăng từ 3.000 lên 6.000 IOPS **không giải quyết được trần throughput**. Ngược lại, workload **4 KiB** muốn đạt 250 MiB/s cần khoảng **64.000 IOPS** theo phép nhân lý thuyết; cấp 250 MiB/s trên volume có 3.000 IOPS không đủ.

## 4. Chọn loại EBS volume theo kiểu truy cập

### 4.1. Tổng quan loại volume

| EBS volume type | Nền tảng | Thiên về | Tình huống tiêu biểu | Ràng buộc đáng nhớ |
|---|---|---|---|---|
| **gp3** | SSD | Cân bằng IOPS, throughput và chi phí; đặt thông số riêng | Boot, web, ứng dụng, database vừa, phần lớn workload chung | Có baseline IOPS/throughput, phần provision thêm có tính phí |
| **gp2** | SSD | IOPS gắn với dung lượng; dùng credit/burst ở một số kích cỡ | Workload đang dùng gp2, nhu cầu burst vừa | Muốn tăng IOPS có thể phải tăng volume; credit dễ gây bất ổn |
| **io2** | SSD Provisioned IOPS | IOPS cao, latency/độ bền theo đặc tính dịch vụ | Database quan trọng, I/O ngẫu nhiên cao | Giá provisioned IOPS; cần instance hỗ trợ để đạt mức rất cao |
| **io1** | SSD Provisioned IOPS | Provision IOPS cho workload legacy | Khối lượng cũ cần loại io1 | Xem xét khả năng chuyển sang io2/gp3 theo tương thích và chi phí |
| **st1** | HDD throughput optimized | Streaming, truy cập tuần tự khối lớn | Log/data warehouse có luồng tuần tự, large scans | Không phù hợp random I/O nhỏ, không dùng boot volume |
| **sc1** | HDD cold | Dữ liệu truy cập ít, throughput thấp | Dữ liệu lạnh cần block storage | Hiệu năng thấp, không dùng boot volume |
| **standard (magnetic)** | HDD thế hệ cũ | Legacy | Hệ thống hiện hữu | Không phải lựa chọn thông dụng cho triển khai mới |

**Không có một volume type “nhanh nhất” cho mọi bài toán.** Ví dụ **io2** hỗ trợ yêu cầu chuyên biệt về IOPS và độ bền, nhưng **gp3** thường hợp lý hơn khi workload không đòi mức đó. **st1** có throughput phù hợp đọc tuần tự dài, nhưng random 4 KiB là trường hợp kém thích hợp.

### 4.2. gp3: tách IOPS và throughput khỏi dung lượng

Với gp3, mức cơ bản thường là **3.000 IOPS** và **125 MiB/s** đã bao gồm trong giá lưu trữ, bất kể dung lượng volume trong phạm vi hỗ trợ. Người dùng có thể **provision IOPS và throughput cao hơn baseline** trong giới hạn và điều kiện AWS công bố; phần vượt baseline có thể tính phí riêng.

Ví dụ (cần kiểm tra thông số/giá Region hiện hành trước khi tạo):

~~~text
Volume A: gp3, 100 GiB, 3.000 IOPS, 125 MiB/s
Volume B: gp3, 100 GiB, 6.000 IOPS, 250 MiB/s
~~~

Hai volume có dung lượng giống nhau nhưng ngân sách I/O khác nhau. Nếu workload là **random 4 KiB** và đang thực sự vượt 3.000 IOPS, B có thể cải thiện. Nếu workload chỉ dùng 100 IOPS nhưng cần băng thông lớn khi copy file, hãy tập trung vào **throughput**. Nếu workload bị giới hạn bởi EC2 instance, nâng thông số B có thể không tăng tốc đáng kể.

**Điểm khác gp2:** gp3 không cần tăng dung lượng chỉ để tăng baseline IOPS và **không dùng cơ chế burst CPU-style credits cho IOPS/throughput gp3** theo cách gp2 vận hành. Đó là lý do gp3 thường dễ dự báo hiệu năng hơn.

### 4.3. gp2: quy mô volume và burst credits

Với gp2, baseline IOPS tăng theo dung lượng, thường được mô tả theo **3 IOPS/GiB** trong các giới hạn của loại volume; một số kích cỡ nhỏ có **khả năng burst** nhờ I/O credit. Tại tải cao kéo dài, tín dụng có thể cạn dẫn đến hiệu năng giảm về baseline.

Ví dụ ý niệm:

~~~text
Volume gp2 nhỏ:
- Một lúc đạt IOPS cao nhờ burst.
- Chạy workload liên tục có thể giảm về mức baseline.
- Tăng dung lượng có thể nâng baseline nhưng tăng phí lưu trữ.
~~~

Vì vậy nếu hệ thống gp2 chạy nhanh đầu giờ rồi chậm vào cuối phiên batch, hãy kiểm tra **BurstBalance** và pattern I/O thay vì chỉ tăng số thread.

### 4.4. io2/io1: khi IOPS và độ trễ quan trọng

**Provisioned IOPS SSD** phù hợp những workload cần mức IOPS cao, độ ổn định và đặc tính độ bền chuyên biệt. **io2 Block Express** trên cấu hình hỗ trợ có thể đạt giới hạn cao hơn đáng kể so với volume SSD phổ thông, nhưng thông số tối đa phụ thuộc volume/instance và giới hạn AWS tại thời điểm sử dụng.

Khi chọn io2:

1. Xác định mục tiêu **IOPS, latency p95/p99, block size, write ratio, độ bền**.
2. Kiểm tra **EC2 instance hỗ trợ** tính năng/hiệu năng mong muốn.
3. Tính cả giá **GiB/tháng** và **provisioned IOPS**, chi phí instance và snapshot.
4. Chạy benchmark trên cấu hình tương ứng với sản xuất.
5. Xem xét EBS Multi-Attach chỉ khi ứng dụng thực sự hỗ trợ ghi phối hợp từ nhiều máy.

**Không coi io2 là giải pháp tự động** cho SQL chậm do thiếu index, lock contention hoặc connection pool. Tối ưu truy vấn có thể đem lại hiệu quả lớn hơn việc nâng storage.

### 4.5. st1/sc1: tối ưu throughput tuần tự và dữ liệu lạnh

**st1** và **sc1** là các loại HDD với mô hình hiệu năng thiên về throughput, không nên dùng cho lượng lớn I/O nhỏ/ngẫu nhiên. Chúng không hỗ trợ làm EBS boot volume. Một số mức hiệu năng của chúng dùng burst bucket; đọc/ghi tuần tự khối lớn phù hợp hơn nhiều so với database OLTP.

Nhiều workload cần file chia sẻ hoặc data lake sẽ hợp hơn với **EFS/FSx/S3** thay vì st1/sc1. Chọn theo **mẫu truy cập và giao thức**, không chỉ giá mỗi GiB.

## 5. Giới hạn EC2 EBS và cách đọc bảng thông số

### 5.1. Volume nhanh nhưng instance không đủ EBS bandwidth

Một EC2 instance type có các thông số riêng như **baseline/maximum EBS bandwidth, throughput và IOPS**. Với nhiều volume gắn cùng instance, tổng I/O vẫn phải đi qua giới hạn của instance đó. Vì vậy:

- Tăng gp3 lên 1.000 MiB/s nhưng máy chỉ đạt EBS throughput thấp hơn mức đó có thể bị chặn từ EC2.
- Dùng hai EBS volume mỗi volume 500 MiB/s không bảo đảm tổng 1.000 MiB/s nếu instance không đáp ứng.
- Mức **“up to”** thường đi kèm đặc tính baseline/burst; kiểm tra chính xác instance type cụ thể.
- Có instance dùng đường EBS chuyên dụng và có giới hạn gói I/O theo khả năng AWS/Nitro; đừng suy diễn dựa trên băng thông mạng VPC thông thường.

### 5.2. EBS-optimized và Nitro

Nhiều instance thế hệ hiện đại hỗ trợ **EBS-optimized** mặc định. Điều này giúp đường truy cập EBS được thiết kế tối ưu, nhưng **không xóa trần EBS bandwidth/IOPS** của instance. Một số khả năng giám sát chi tiết hoặc mức hiệu năng đặc biệt yêu cầu **Nitro-based instance**, phiên bản OS/driver phù hợp.

Kiểm tra instance type qua API thay vì mặc định mọi máy 2 vCPU đều có hiệu năng EBS tương đương.

### 5.3. Không cộng số lý thuyết một cách cơ học

Giả sử:

~~~text
gp3 #1: được cấu hình 250 MiB/s
gp3 #2: được cấu hình 250 MiB/s
EC2 instance: trần EBS thực tế 350 MiB/s
=> Tổng hai volume khó vượt trần 350 MiB/s.
~~~

Đây là ví dụ giới hạn đơn giản hóa: ngoài throughput còn có IOPS, I/O size, read/write mix, queue depth, sự cạnh tranh của workload và cấu trúc filesystem.

## 6. Đọc CloudWatch metrics để biết đang thiếu gì

### 6.1. Những metric thường dùng

Amazon EBS phát hành metric vào namespace **AWS/EBS** tùy loại volume và nền tảng EC2. Các metric thường gặp:

| Metric | Đơn vị / thống kê thường dùng | Ý nghĩa thực hành |
|---|---|---|
| **VolumeReadOps** | Count; Sum theo khoảng | Số read I/O do volume xử lý |
| **VolumeWriteOps** | Count; Sum theo khoảng | Số write I/O |
| **VolumeReadBytes** | Bytes; Sum | Dung lượng đọc từ volume |
| **VolumeWriteBytes** | Bytes; Sum | Dung lượng ghi vào volume |
| **VolumeTotalReadTime** | Seconds; Sum (khi được hỗ trợ) | Tổng thời gian thực hiện read I/O |
| **VolumeTotalWriteTime** | Seconds; Sum (khi được hỗ trợ) | Tổng thời gian thực hiện write I/O |
| **VolumeQueueLength** | Count; Average | Số I/O chờ xử lý theo cách metric định nghĩa |
| **BurstBalance** | Percent, ở loại volume hỗ trợ | Mức tín dụng burst còn lại, hữu ích với gp2/st1/sc1 |
| **VolumeIdleTime** | Seconds, khi được hỗ trợ | Thời gian volume không xử lý I/O |

Một số **metric hoặc statistic không khả dụng** cho mọi volume type/instance; các metric mới cũng có thể khác theo nền tảng Nitro. Hãy xem danh sách metric **thực tế hiển thị trong CloudWatch** cho volume đang học.

### 6.2. Chuyển metric thành IOPS và MiB/s

Giả sử trong **300 giây**, CloudWatch trả về:

~~~text
VolumeReadOps (Sum)  = 600.000
VolumeWriteOps (Sum) = 300.000
VolumeReadBytes (Sum)  = 62.914.560.000 bytes
VolumeWriteBytes (Sum) = 31.457.280.000 bytes
~~~

Tính:

~~~text
Read IOPS  = 600.000 / 300 = 2.000
Write IOPS = 300.000 / 300 = 1.000
Total IOPS = 3.000

Read throughput  = 62.914.560.000 / 300 / 1.048.576 = 200 MiB/s
Write throughput = 31.457.280.000 / 300 / 1.048.576 = 100 MiB/s
Total throughput = 300 MiB/s
~~~

Số liệu này có kích thước I/O hiệu dụng trung bình khoảng **102,4 KiB** (300 MiB/s ÷ 3.000 IOPS), khác xa workload 4 KiB. Đây là **số liệu giả định cho bài tập**, không đại diện một type volume bất kỳ.

**Cẩn thận với thống kê:** chia **Sum** cho độ dài khoảng để ra tốc độ; không dùng Average của một metric dạng đếm mà áp công thức tương tự nếu không hiểu ý nghĩa metric. Một khoảng 5 phút có thể che giấu spike 10 giây; với hệ thống nhạy p99, cần thêm telemetry từ OS/ứng dụng.

### 6.3. Latency trung bình từ CloudWatch

Nếu VolumeTotalReadTime có dữ liệu hợp lệ, có thể tính:

~~~text
Average read latency (ms)
≈ 1000 × VolumeTotalReadTime (Sum, seconds)
       / VolumeReadOps (Sum)
~~~

Đừng chia khi read ops = 0. Metric latency trung bình **không cho biết p99**; muốn thấy tail latency cần instrumentation ở tầng OS/ứng dụng hoặc các metric latency chi tiết được dịch vụ hỗ trợ.

### 6.4. Bổ sung dữ liệu từ Linux và ứng dụng

Các công cụ thường dùng khi có quyền trên máy:

- **iostat -x 1**: lượng I/O, await, queue và mức sử dụng thiết bị theo phiên bản công cụ.
- **lsblk**, **findmnt**, **df -h**: xác định đúng EBS block device, mount point và dung lượng.
- **pidstat -d** hoặc công cụ ứng dụng: tiến trình nào tạo I/O.
- **fio**: benchmark theo block size, read/write mix, queue depth; cần sandbox riêng.
- **APM/JVM metrics**: query latency, lock waits, heap/cache behavior, worker concurrency.

**Không dùng mỗi \`%util=100%\` từ iostat để kết luận SSD đã đạt trần IOPS**: cách diễn giải \`%util\` tùy thiết bị và khả năng song song. Kết hợp latency, throughput, IOPS, queue và giới hạn công bố.

## 7. Quy trình tối ưu hiệu năng theo thứ tự

### Bước 1 — Định nghĩa mục tiêu ứng dụng

Ví dụ API truy vấn dữ liệu phải đạt **p95 dưới 120 ms**, batch export hoàn thành dưới **20 phút**, hoặc database phải xử lý **5.000 giao dịch/giây** với tỉ lệ lỗi thấp. Đây là SLO ở tầng ứng dụng; không đặt mục tiêu “đạt tối đa IOPS” nếu không liên hệ với workload.

### Bước 2 — Ghi đặc tính I/O hiện tại

Trong giờ tải cao và thấp, thu thập:

- Read/write IOPS và MiB/s, kích thước I/O trung bình.
- Sequential/random, read/write ratio, sync/async, fsync.
- Average và p95/p99 latency (OS/app), queue depth.
- CPU/memory/cache hit rate, GC, query plans và tải network.
- Volume type, size, provisioned IOPS/throughput, EC2 instance type và giới hạn EBS.

### Bước 3 — So từng lớp giới hạn

| Quan sát | Giả thuyết | Cách kiểm chứng |
|---|---|---|
| IOPS áp sát mức provisioned, MiB/s còn thấp | Volume IOPS là bottleneck | So số liệu với thông số volume; thử tăng IOPS trong lab |
| MiB/s nằm ngang tại một mức, IOPS không cao | Volume throughput cap | So throughput provisioned và I/O size |
| Nhiều volume cùng chậm khi chạy đồng thời | Giới hạn EBS của EC2 instance | Xem instance EBS baseline/max và cộng I/O tổng |
| Latency tăng, CPU ứng dụng cao, EBS chưa bận | Bottleneck tại app/query/cache | Profile CPU, query, heap, locks |
| gp2 chậm sau thời gian chạy liên tục | Hết burst credits | Quan sát BurstBalance và so với baseline |
| EBS đã đủ nhanh nhưng job vẫn chậm | Thread, serialization, network, locks, read amplification | Đo từng bước của pipeline |
| Read latency tăng sau restore từ snapshot | Dữ liệu mới được đọc lần đầu / chưa được khởi tạo đầy đủ | Xem quy trình snapshot initialization và khả năng FSR |

### Bước 4 — Tối ưu trước khi mua thêm thông số

- Tối ưu query và index, tránh quét dữ liệu không cần thiết.
- Dùng batching, async I/O và concurrency hợp lý.
- Tăng cache hiệu quả, giảm dữ liệu ghi lặp hoặc read amplification.
- Cân nhắc nén dữ liệu, thay đổi kích thước block, nhưng xem ảnh hưởng CPU.
- Tách workload batch và OLTP nếu chúng tranh chấp I/O.
- Chỉ sau khi đo bottleneck, điều chỉnh volume hoặc instance.

### Bước 5 — Thay đổi có kiểm soát và đo lại

Thiết lập **baseline** trước thay đổi; thay từng yếu tố có thể đo được (ví dụ 3.000 → 6.000 IOPS, hoặc 125 → 250 MiB/s), giữ điều kiện workload gần tương đương và xem **latency, throughput, error rate và chi phí** sau khi áp dụng.

AWS **Elastic Volumes** có thể cho phép sửa size/type/IOPS/throughput của volume được hỗ trợ mà không cần detach trong nhiều trường hợp. Tuy vậy, thay đổi có trạng thái **modifying/optimizing/completed**, giới hạn tần suất thay đổi và những điều kiện riêng; cần kiểm tra tài liệu trước khi thao tác. Tăng dung lượng EBS có thể cần **mở rộng phân vùng/filesystem** ở OS; tăng IOPS/throughput thường không yêu cầu thao tác filesystem tương tự.

## 8. Thực hành 1 — Kiểm tra thông số EBS bằng AWS CLI (chỉ đọc)

> Phần này chỉ xem cấu hình, không tạo hoặc sửa volume. Dùng AWS CLI v2 trong **sandbox** với quyền đọc EC2/CloudWatch. Ví dụ shell sử dụng **Bash** và Region \`ap-southeast-1\`; thay profile/ID cho phù hợp.

### 8.1. Xác minh đúng account và Region

~~~bash
export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1

aws sts get-caller-identity --profile "$AWS_PROFILE"
~~~

Nếu đang dùng **CloudShell** với phiên đăng nhập có sẵn mà không có profile \`aws-lab-dev\`, bỏ dòng \`export AWS_PROFILE=...\` và những \`--profile\` tương ứng.

### 8.2. Xem volume được cấp

~~~bash
REGION=ap-southeast-1
VOL_ID=vol-0123456789abcdef0

aws ec2 describe-volumes \
  --volume-ids "$VOL_ID" \
  --region "$REGION" \
  --query 'Volumes[].{Id:VolumeId,Type:VolumeType,GiB:Size,IOPS:Iops,MiBs:Throughput,AZ:AvailabilityZone,State:State,Encrypted:Encrypted}' \
  --output table
~~~

ID trong ví dụ là **giả định**; chỉ dùng một volume bạn có quyền xem. Cột \`Throughput\` có thể rỗng với volume type không có tham số provisioned throughput riêng. Cần đọc **VolumeType** trước khi diễn giải IOPS/throughput.

### 8.3. Xem giới hạn EBS của EC2 instance type

~~~bash
aws ec2 describe-instance-types \
  --instance-types m7i.large \
  --region "$REGION" \
  --query 'InstanceTypes[].{Type:InstanceType,EBS:EbsInfo.EbsOptimizedInfo}' \
  --output json
~~~

Các thuộc tính \`BaselineBandwidthInMbps\`, \`MaximumBandwidthInMbps\`, \`BaselineThroughputInMBps\`, \`MaximumThroughputInMBps\`, \`BaselineIops\` và \`MaximumIops\` (nếu được API trả về) giúp xem khả năng EBS instance. **Mbps (megabit/s) khác MB/s (megabyte/s) và MiB/s**; không so trực tiếp các con số nếu chưa quy đổi đơn vị.

Để xem instance thực sự đang dùng type nào (nếu được cấp quyền và có instance ID):

~~~bash
INSTANCE_ID=i-0123456789abcdef0

aws ec2 describe-instances \
  --instance-ids "$INSTANCE_ID" \
  --region "$REGION" \
  --query 'Reservations[].Instances[].{Id:InstanceId,Type:InstanceType,AZ:Placement.AvailabilityZone,State:State.Name}' \
  --output table
~~~

### 8.4. Đọc CloudWatch metric theo khoảng thời gian

Ví dụ lấy \`VolumeReadOps\` trong **30 phút gần đây** trên môi trường Bash có GNU \`date\` (như AWS CloudShell Linux):

~~~bash
START_UTC=$(date -u -d '30 minutes ago' +%Y-%m-%dT%H:%M:%SZ)
END_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)

aws cloudwatch get-metric-statistics \
  --namespace AWS/EBS \
  --metric-name VolumeReadOps \
  --dimensions "Name=VolumeId,Value=$VOL_ID" \
  --start-time "$START_UTC" \
  --end-time "$END_UTC" \
  --period 300 \
  --statistics Sum \
  --region "$REGION" \
  --output table
~~~

Kết quả mỗi datapoint là **số read operations trong khoảng 300 giây** (với metric Sum), không phải trực tiếp read IOPS. Muốn tính read IOPS trung bình, lấy **Sum / 300**. Lặp lại với \`VolumeWriteOps\`, \`VolumeReadBytes\`, \`VolumeWriteBytes\`. Công cụ có thể không trả datapoint nếu volume không phát sinh I/O, thời gian chưa có dữ liệu hoặc quyền truy cập bị hạn chế.

**Bài tập nhỏ:** nếu \`VolumeReadOps=450000\` trong 300 giây, read IOPS là bao nhiêu? Nếu \`VolumeReadBytes=47.185.920.000\` byte trong cùng khoảng, throughput đọc và kích thước I/O trung bình khoảng bao nhiêu?

## 9. Thực hành 2 — Benchmark bằng fio trên volume thử nghiệm

**Chỉ làm nếu sandbox cho phép và đã có volume EBS dành riêng cho bài lab.** \`fio\` có thể ghi lượng dữ liệu lớn và làm chậm ứng dụng; **không benchmark trực tiếp raw device**, **không dùng filesystem production**, không chọn file đang chứa dữ liệu quan trọng. Mục tiêu là quan sát sự khác nhau giữa **random 4 KiB IOPS** và **sequential 256 KiB throughput**, không cố đạt tốc độ cao nhất bằng mọi giá.

### 9.1. Chuẩn bị tài nguyên thực hành

- EC2 instance tại cùng AZ với volume được phép sử dụng, đã gắn và mount volume riêng.
- Filesystem ext4/xfs (hoặc tương đương) đã được định dạng **trên volume lab** theo quy trình được duyệt; đường mount ví dụ \`/mnt/ebs-lab\`.
- Tối thiểu khoảng **2 GiB dung lượng trống** dành cho file benchmark 1 GiB, không có workload khác trên volume.
- \`fio\` được cài đặt từ nguồn hệ điều hành tin cậy.
- Quyền tạo/xóa file trong thư mục lab, giám sát chi phí EC2/EBS và thời gian chạy.

**Kiểm tra trước khi chạy:**

~~~bash
TEST_DIR=/mnt/ebs-lab
TEST_FILE="$TEST_DIR/fio-training.bin"

findmnt "$TEST_DIR"
df -h "$TEST_DIR"
lsblk -o NAME,SIZE,TYPE,MOUNTPOINTS

test ! -e "$TEST_FILE" || {
  echo "File fio-training.bin da ton tai: khong ghi de"
  exit 1
}
~~~

Nếu \`findmnt\` không cho thấy **đúng mount point của volume thử nghiệm**, dừng lại; không tạo file ở một thư mục thuộc root filesystem ngoài ý muốn.

### 9.2. Tạo file thử nghiệm

Lệnh này **ghi một file mới** tại \`/mnt/ebs-lab/fio-training.bin\`, không ghi toàn bộ block device:

~~~bash
fio \
  --name=prepare \
  --filename="$TEST_FILE" \
  --size=1G \
  --rw=write \
  --bs=1m \
  --ioengine=libaio \
  --iodepth=8 \
  --direct=1 \
  --group_reporting
~~~

Đây là phép ghi có chi phí I/O và có thể mất thời gian. Nếu mount point sai hoặc volume không đủ chỗ, không chạy tiếp. Việc ghi file trước giúp phép đo đọc không phụ thuộc vào một file chưa tồn tại.

### 9.3. Đo random read 4 KiB

~~~bash
fio \
  --name=randread-4k \
  --filename="$TEST_FILE" \
  --size=1G \
  --rw=randread \
  --bs=4k \
  --ioengine=libaio \
  --iodepth=32 \
  --direct=1 \
  --runtime=60 \
  --time_based \
  --group_reporting
~~~

Quan sát các dòng kết quả **IOPS**, **BW** và latency (\`clat\`/phân vị nếu có). Chạy lại với \`--iodepth=1\` hoặc \`--iodepth=8\` để thấy tác động của queue depth; không tăng QD tùy tiện nếu latency đã xấu.

### 9.4. Đo sequential read 256 KiB

~~~bash
fio \
  --name=seqread-256k \
  --filename="$TEST_FILE" \
  --size=1G \
  --rw=read \
  --bs=256k \
  --ioengine=libaio \
  --iodepth=16 \
  --direct=1 \
  --runtime=60 \
  --time_based \
  --group_reporting
~~~

So sánh throughput với bước random 4 KiB. Lưu ý cùng volume có thể cho **random IOPS tốt** nhưng **sequential throughput bị giới hạn ở giá trị provisioned**. Dữ liệu được lưu trong file benchmark cũng có thể đã nằm trong cache tại các tầng khác; \`--direct=1\` giúp giảm page cache của OS nhưng không loại trừ mọi hiệu ứng cache hoặc biến động workload.

### 9.5. Thu hồi tài nguyên

Sau khi xác nhận file do bạn vừa tạo và không cần nữa:

~~~bash
rm -- "$TEST_FILE"
~~~

Với tài nguyên cloud, dọn **EC2 instance và EBS volume lab** theo hướng dẫn sandbox, đồng thời kiểm tra \`DeleteOnTermination\`, snapshot, public IPv4 và chi phí còn lại. **Không xóa một volume đang được hệ thống khác sử dụng**. Nếu có yêu cầu giữ snapshot, ghi lại chủ sở hữu và thời hạn giữ để quản lý chi phí.

### 9.6. Bảng ghi kết quả

| Thử nghiệm | Block size | Queue depth | IOPS đo được | MiB/s đo được | Mean / p99 latency |
|---|---:|---:|---:|---:|---:|
| Random read | 4 KiB | 1 | Điền kết quả | Điền kết quả | Điền kết quả |
| Random read | 4 KiB | 8 | Điền kết quả | Điền kết quả | Điền kết quả |
| Random read | 4 KiB | 32 | Điền kết quả | Điền kết quả | Điền kết quả |
| Sequential read | 256 KiB | 16 | Điền kết quả | Điền kết quả | Điền kết quả |

**Thảo luận:** khi tăng QD, IOPS có tăng mãi không? Latency có biến đổi? Khi thay block size từ 4 KiB sang 256 KiB, đại lượng nào tăng nhiều hơn? Kết quả bị giới hạn bởi volume hay instance?

## 10. Thay đổi EBS volume để cải thiện hiệu năng

AWS cung cấp cơ chế **Elastic Volumes** cho phép điều chỉnh một số thuộc tính volume đang sử dụng mà không phải luôn detach. Tuy nhiên, cấu hình hỗ trợ và trạng thái xử lý khác nhau theo volume type, instance và quy tắc hiện hành.

### 10.1. Ví dụ thay cấu hình gp3 (chỉ minh họa)

Tình huống: volume lab gp3 đang có 3.000 IOPS / 125 MiB/s, workload cần 6.000 IOPS / 250 MiB/s sau khi đã đo nút nghẽn.

~~~bash
# CHI THUC HIEN neu co quyen va da phe duyet cho volume LAB
aws ec2 modify-volume \
  --volume-id vol-0123456789abcdef0 \
  --volume-type gp3 \
  --iops 6000 \
  --throughput 250 \
  --region ap-southeast-1
~~~

Lệnh minh họa **có tác động và có thể tăng chi phí**, không cần chạy để hoàn thành phần thực hành cốt lõi. Khi được phép áp dụng, theo dõi:

~~~bash
aws ec2 describe-volumes-modifications \
  --volume-ids vol-0123456789abcdef0 \
  --region ap-southeast-1
~~~

**Điều cần chuẩn bị:** snapshot/backup phù hợp, thông tin ứng dụng phụ thuộc, baseline, ngân sách, phương án rollback hoặc chuyển sang volume khác. Không tự giả định mọi thay đổi có thể đảo ngược ngay; volume có giới hạn thời gian giữa các lần sửa và tính năng rollback không giống nhau theo thuộc tính.

### 10.2. Khi nào nên tăng dung lượng, IOPS, throughput hoặc đổi EC2?

| Quan sát đã xác minh | Hành động đề xuất | Điều kiện |
|---|---|---|
| Chỉ thiếu dung lượng GB, I/O chưa bão hòa | Tăng **volume size** | Chuẩn bị mở rộng filesystem khi cần |
| gp3 đạt trần IOPS, MiB/s thấp | Tăng **provisioned IOPS** | Instance và workload đủ queue/concurrency |
| gp3 đạt trần MiB/s, IOPS thấp | Tăng **provisioned throughput** | I/O size và EC2 EBS bandwidth cho phép |
| EC2 EBS bandwidth/IOPS đạt trần | Đổi **instance type** phù hợp | Kiểm tra AMI, quota, AZ, chi phí và khả năng gián đoạn |
| gp2 thường xuyên hết burst | Cân nhắc **gp3**, tối ưu workload | So sánh chi phí và giới hạn khi chuyển loại |
| Database I/O latency yêu cầu rất thấp, gp3 không đạt | Đánh giá **io2** + instance phù hợp | Kiểm thử latency thực tế và tổng chi phí |
| Nhiều phép đọc lặp lại cùng dữ liệu | Tối ưu **cache/query/index** | Chứng minh bottleneck không phải CPU/lock |

### 10.3. RAID, striping và hệ quả

Có thể ghép nhiều EBS volumes trong OS (ví dụ RAID 0/striping) để phân phối I/O trong một số bài toán. Tuy nhiên:

- Tổng throughput vẫn bị EC2 giới hạn.
- **RAID 0 làm tăng phạm vi ảnh hưởng khi một volume gặp sự cố**; không thay thế backup.
- Snapshot nhất quán giữa nhiều volume cần cơ chế phù hợp, chẳng hạn **multi-volume snapshots** và quiesce ứng dụng theo nhu cầu.
- Với nhu cầu cơ bản, một volume gp3/io2 phù hợp và cấu hình đúng thường dễ vận hành hơn.

Không tạo RAID chỉ để “nhân đôi tốc độ” khi chưa có benchmark.

## 11. Chi phí và lựa chọn hiệu năng đủ dùng

### 11.1. Các thành phần của hóa đơn EBS

**Chi phí EBS có thể gồm**:

1. **Provisioned storage** theo dung lượng GiB và thời gian sử dụng volume.
2. **Provisioned IOPS** với một số volume type, đặc biệt io1/io2 và phần vượt baseline của gp3.
3. **Provisioned throughput** vượt baseline của gp3.
4. **EBS snapshots**, dữ liệu snapshot, lưu trữ và các tính năng như Fast Snapshot Restore nếu sử dụng.
5. **EC2 instance**, data transfer và các thành phần hỗ trợ workload.

Một phép tính chi phí ý niệm:

~~~text
Chi phí tổng tháng
≈ (GiB volume × đơn giá/GB-tháng × tỷ lệ thời gian)
  + (IOPS tính phí × đơn giá IOPS-tháng × tỷ lệ thời gian)
  + (throughput tính phí × đơn giá throughput-tháng × tỷ lệ thời gian)
  + snapshot / FSR / EC2 / network / logging liên quan
~~~

Các dòng tính phí thay đổi theo volume type và bảng giá Region. Không thay đơn giá vào công thức khi chưa xem **AWS EBS Pricing** hoặc **AWS Pricing Calculator** hiện hành.

### 11.2. Tối ưu theo chi phí trên một đơn vị công việc

Workload A đạt 1.000 job/giờ với 3.000 IOPS, workload B đạt 1.100 job/giờ với 10.000 IOPS, nhưng chi phí thêm gấp ba. Nâng IOPS chỉ có ý nghĩa khi lượng công việc tăng, độ trễ giảm hoặc SLO cần thiết được cải thiện **đủ để bù chi phí**.

~~~text
Cost per successful job
= Tổng chi phí workload trong kỳ
  / Số job hoàn thành hợp lệ

Cost per request
= Tổng chi phí workload trong kỳ
  / Số request hoàn thành đạt SLO
~~~

**Quy trình quyết định:** đo tải trước → thay cấu hình có kiểm soát → benchmark lại → tính chi phí/job hoặc request → giữ hoặc điều chỉnh. Cảnh báo AWS Budgets hữu ích nhưng không tự tạo trần chi tiêu cứng.

## 12. Bảo mật, tính bền vững và khả năng phục hồi

### 12.1. EBS mã hóa dữ liệu

- EBS hỗ trợ **encryption at rest** và tích hợp **AWS KMS**; kiểm tra chính sách mã hóa mặc định của account và quyền KMS phù hợp.
- Snapshot của volume được mã hóa và volume tạo từ snapshot cần tuân thủ quy tắc encryption/KMS tương ứng.
- **IAM policy** kiểm soát ai được tạo, gắn, sửa, snapshot và xóa volume; không nhúng access key vào script hoặc AMI.
- EBS không thay cho **mã hóa ở tầng ứng dụng**, phân quyền filesystem hoặc quản trị secrets nếu workload yêu cầu.

### 12.2. Volume theo AZ và chiến lược phục hồi

EBS volume thường ở **một AZ**, được thiết kế để bền vững trong AZ đó. Nếu ứng dụng phải hoạt động khi một AZ không khả dụng, cần thêm biện pháp ở **tầng ứng dụng/dữ liệu**:

- Replication dữ liệu giữa các AZ qua ứng dụng, database hoặc dịch vụ managed phù hợp.
- Snapshot theo chính sách RPO/RTO, kiểm tra restore thực tế.
- Chuyển phục vụ sang instance/volume mới tại AZ khác khi có phương án phục hồi dữ liệu phù hợp.
- EC2 Auto Scaling/Load Balancer cho các thành phần stateless; tránh phụ thuộc vào một volume duy nhất.
- Theo dõi snapshot retention, thời gian restore và chi phí.

**Snapshot EBS** là bản sao lưu cấp volume theo khả năng dịch vụ; tính nhất quán ở tầng ứng dụng có thể cần quiesce, flush hoặc cơ chế backup của database. Tạo snapshot không tự bảo đảm một database đang ghi được phục hồi logic hoàn hảo.

### 12.3. Multi-Attach là trường hợp đặc biệt

**EBS Multi-Attach** có trên các loại volume và EC2 instance/OS được AWS hỗ trợ (đặc biệt io1/io2 với điều kiện cụ thể), cho phép một volume được gắn nhiều instance **trong cùng AZ**. Chỉ dùng với ứng dụng/filesystem **cluster-aware**, có cơ chế phối hợp khóa và xử lý ghi đồng thời. Gắn cùng ext4/xfs thông thường rồi mount ghi từ nhiều máy **có nguy cơ hỏng dữ liệu**. Khi cần file dùng chung qua nhiều AZ, xem xét EFS hoặc FSx theo đặc thù workload.

## 13. Bài tập tình huống thiết kế

Một nền tảng học trực tuyến chạy trên AWS có ba thành phần:

- **API Java** phục vụ đọc bài học và ghi tiến trình, dùng EC2 + RDS.
- **Worker** xử lý tệp xuất báo cáo, đọc/ghi tuần tự khối lớn theo giờ.
- **Database tự quản lý** cho một thành phần legacy, random I/O nhỏ, p99 truy vấn nhạy cảm.

Giả sử hệ thống có hai AZ, yêu cầu không mất dữ liệu quan trọng và có ngân sách cố định hàng tháng.

### 13.1. Đề xuất ban đầu

| Thành phần | Lựa chọn lưu trữ ban đầu | Điều cần đo | Phương án mở rộng |
|---|---|---|---|
| API Java | **gp3** cho EBS root/data nếu dùng EBS | Latency, throughput, log I/O, GC/query | Tối ưu app/cache; nâng gp3 nếu thật sự nghẽn |
| Worker tuần tự | **gp3** hoặc **st1** nếu pattern phù hợp và không cần boot | MiB/s, block size, queue, thời gian job | Tăng throughput, đổi instance, cân nhắc S3 làm nơi lưu kết quả |
| Legacy DB random I/O | **gp3** thử nghiệm, cân nhắc **io2** khi cần | IOPS, avg/p99 latency, queue và DB waits | Cải thiện index/cache hoặc chuyển managed DB |
| Backup dữ liệu | EBS snapshot và bản sao/cơ chế khôi phục theo RPO/RTO | Thời gian restore, nhất quán DB, tuổi snapshot | Thử restore định kỳ, đa AZ theo nhu cầu |
| File dùng chung giữa nhiều EC2 | **EFS/FSx** nếu workload cần file protocol | Concurrent clients, throughput, latency | Chọn file service theo yêu cầu |

Tại sao không chọn io2 cho mọi thành phần? Vì io2 tối ưu cho các nhu cầu cụ thể, còn chi phí lưu trữ/IOPS và giới hạn EC2 có thể làm lựa chọn này không hiệu quả cho workload nhẹ. Tại sao không chọn st1 cho database? Vì random small I/O không phải điểm mạnh của HDD throughput optimized.

### 13.2. Bài tập tính toán

Một ứng dụng cần **8.000 random IOPS**, I/O size trung bình **8 KiB**, đọc 70% và ghi 30%. Hãy trả lời:

1. Throughput lý thuyết cần khoảng bao nhiêu MiB/s?
2. Nếu gp3 provisioned **8.000 IOPS / 125 MiB/s** và EC2 đáp ứng, liệu throughput có phải bottleneck theo phép nhân lý thuyết?
3. Nếu latency trung bình 2 ms, cần khoảng bao nhiêu outstanding I/O theo Little's Law?
4. Nếu chuyển sang I/O 256 KiB và vẫn muốn 8.000 IOPS, yêu cầu throughput lý thuyết là bao nhiêu?
5. Nếu tăng IOPS nhưng latency p99 API không giảm, bạn sẽ đo tiếp lớp nào?

**Gợi ý đáp án:**

~~~text
1) 8.000 × 8 / 1024 = 62,5 MiB/s.
2) 62,5 MiB/s < 125 MiB/s; throughput chưa phải trần
   nếu mọi giả định và giới hạn khác đều đáp ứng.
3) 8.000 × 0,002 = khoảng 16 outstanding I/O.
4) 8.000 × 256 / 1024 = 2.000 MiB/s.
5) Kiểm tra query plan/cache, EC2 EBS bandwidth, queue,
   filesystem, CPU, locking, network và p99 theo từng tầng.
~~~

Đây là phép tính gần đúng. Hiệu năng thực còn phụ thuộc I/O mix, điều kiện hệ thống, giới hạn volume/type và khả năng xử lý song song.

## 14. Lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Bước kiểm tra |
|---|---|---|
| Đã tăng IOPS nhưng ứng dụng không nhanh hơn | Đụng throughput cap, EC2 EBS limit hoặc bottleneck app | Đo I/O size, MiB/s, instance EBS, p95/p99 |
| Thông lượng tuần tự thấp dù provisioned IOPS cao | Throughput thấp hoặc QD, block size không phù hợp | So MiB/s provisioned, bs fio và concurrency |
| gp2 nhanh đầu phiên rồi chậm | Credit bucket cạn | Xem BurstBalance và tải nền, cân nhắc gp3 |
| Volume mới từ snapshot có read latency cao ban đầu | Khởi tạo dữ liệu snapshot khi truy cập lần đầu | Xem quy trình initialization/FSR và chi phí |
| CloudWatch có IOPS nhưng không thấy RAM/filesystem | EBS metrics khác OS metrics | Cài telemetry/agent theo chính sách, xem iostat/df |
| IOPS CloudWatch thấp nhưng request p99 cao | Cache, lock, DB waits hoặc latency khác | APM, query profile, OS metrics |
| Tăng dung lượng EBS nhưng filesystem chưa lớn | Chưa mở rộng partition/filesystem | Kiểm tra lsblk/findmnt/df và quy trình resize phù hợp |
| Không thể sửa volume như dự định | Trạng thái modification, quota, giới hạn type/instance | Xem describe-volumes-modifications và tài liệu API |
| EBS đã xóa nhưng hóa đơn vẫn cao | Snapshot, EC2, network, FSR, logs còn tồn tại | Cost Explorer và danh sách tài nguyên theo Region |
| Volume mất khả năng gắn vào EC2 khác | EC2 không cùng AZ hoặc cấu hình không tương thích | Kiểm tra AvailabilityZone, attachment và loại volume |
| Multi-Attach làm hỏng filesystem | Nhiều writer trên FS không cluster-aware | Thiết kế lại với cluster-aware FS hoặc file storage managed |

## 15. Checklist và tự kiểm tra

### Trước khi điều chỉnh hiệu năng

- [ ] Có SLO cụ thể ở tầng ứng dụng và baseline đủ đại diện cho peak load.
- [ ] Đã tính IOPS, MiB/s, I/O size, read/write mix, queue depth và latency.
- [ ] Đã xác định đúng **volume type, IOPS, throughput, size và Region/AZ**.
- [ ] Đã so với **EC2 EBS bandwidth/IOPS** và giới hạn instance.
- [ ] Đã kiểm tra CPU, RAM, filesystem, query, cache và concurrency.
- [ ] Đã dự trù chi phí volume, provisioned IOPS, throughput, snapshot và EC2.
- [ ] Đã xác định backup/restore, encryption, IAM/KMS và phạm vi ảnh hưởng.
- [ ] Có kế hoạch thay đổi có thể kiểm chứng, theo dõi và dọn tài nguyên lab.

### Tự kiểm tra kiến thức

1. IOPS và throughput khác nhau ở điểm nào? Vì sao 3.000 IOPS với I/O 4 KiB khác nhiều với 256 KiB?
2. Little's Law giải thích quan hệ giữa IOPS, latency và outstanding I/O ra sao?
3. Vì sao tăng gp3 từ 3.000 lên 10.000 IOPS chưa chắc tăng throughput tuần tự?
4. Điểm khác cơ bản giữa gp3 và gp2 về cách provision và burst là gì?
5. Trường hợp nào nên xem xét io2 thay vì gp3? Những số liệu nào chứng minh quyết định?
6. Vì sao instance EBS bandwidth có thể giới hạn tổng lưu lượng của nhiều volume?
7. CloudWatch \`VolumeReadOps\` dạng Sum được đổi thành read IOPS trung bình như thế nào?
8. Vì sao một benchmark \`fio\` trên root filesystem đang dùng có thể gây nguy hiểm cho dữ liệu và kết quả đo?
9. Nếu muốn tăng volume size, việc gì cần kiểm tra thêm trong hệ điều hành?
10. Vì sao EBS volume theo AZ chưa đủ bảo đảm ứng dụng chịu lỗi toàn AZ?
11. Khi nào phù hợp với EFS hoặc FSx hơn EBS?
12. Khi nào Multi-Attach an toàn và vì sao không nên mount ghi cùng filesystem thông thường từ nhiều instance?

**Kết quả mong đợi:** bạn có thể **chứng minh nút nghẽn bằng số liệu**, chọn volume type và thông số phù hợp với mẫu truy cập, kiểm tra khả năng EC2 đáp ứng, đánh giá chi phí/khả năng phục hồi và đo lại hiệu năng sau thay đổi.

## Tài liệu AWS chính thức

- [Amazon EBS volume types](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volume-types.html)
- [General Purpose SSD gp3 volumes](https://docs.aws.amazon.com/ebs/latest/userguide/general-purpose.html)
- [Provisioned IOPS SSD volumes](https://docs.aws.amazon.com/ebs/latest/userguide/provisioned-iops.html)
- [Monitor Amazon EBS volumes with CloudWatch](https://docs.aws.amazon.com/ebs/latest/userguide/using_cloudwatch_ebs.html)
- [Amazon EBS–optimized instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ebs-optimized.html)
- [Modify an Amazon EBS volume](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-modify-volume.html)
- [Initialize Amazon EBS volumes](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-initialize.html)
- [Amazon EBS Multi-Attach](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volumes-multi.html)
- [Amazon EBS snapshots](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-snapshots.html)
- [Amazon EBS pricing](https://aws.amazon.com/ebs/pricing/)
- [AWS Pricing Calculator](https://calculator.aws/)

> **Lưu ý:** Giới hạn IOPS/throughput, tính năng EBS, mức giá và lựa chọn EC2 thay đổi theo Region, loại volume, thế hệ instance và thời điểm. Trước khi cấu hình production, hãy xác minh các thông số hiện hành trong tài liệu và API AWS, đo workload thật và duyệt thay đổi theo quy trình quản trị của tổ chức.

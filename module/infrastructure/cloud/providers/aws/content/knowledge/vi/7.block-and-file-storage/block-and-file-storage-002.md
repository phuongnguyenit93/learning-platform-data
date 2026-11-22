# EBS volume và lựa chọn loại ổ đĩa

## Mục tiêu học tập

Sau khi học bài này, bạn có thể:

- Giải thích **Amazon Elastic Block Store (Amazon EBS)** là gì, cách volume hoạt động cùng Amazon EC2 và mối liên hệ giữa **Region, Availability Zone (AZ), volume, instance, filesystem và snapshot**.
- Phân biệt **General Purpose SSD (gp3, gp2)**, **Provisioned IOPS SSD (io2, io1)**, **Throughput Optimized HDD (st1)**, **Cold HDD (sc1)** và loại **Magnetic (standard)** thế hệ trước.
- Ước lượng **dung lượng, IOPS, throughput, I/O size, latency** và các giới hạn của instance để chọn volume vừa đủ hiệu năng, đáp ứng khả năng phục hồi và kiểm soát chi phí.
- Tạo, gắn, định dạng, mount, giám sát, thay đổi dung lượng/hiệu năng và sao lưu EBS đúng trình tự với AWS Console, AWS CLI và Linux.
- Phân biệt **EBS** với **Amazon EFS, Amazon S3 và EC2 instance store**, nhận diện khi workload cần filesystem dùng chung qua nhiều AZ thay vì một ổ block.
- Thiết kế dữ liệu bền vững và an toàn qua **mã hóa, IAM, snapshot, backup policy, phục hồi theo RPO/RTO** và quan sát bằng CloudWatch.

**Bối cảnh module:** Trong **CLOUD_PROVIDERS_AWS**, kiến thức lưu trữ gắn với hạ tầng **Region/AZ**, IAM, VPC, compute, database, khả năng phục hồi, giám sát và chi phí. Bài thuộc chương **Lưu trữ block và file**, tập trung vào **EBS volume và lựa chọn loại ổ đĩa**. Khi thiết kế ứng dụng AWS, việc chọn đúng loại EBS thường quyết định tốc độ đọc/ghi, thời gian phản hồi, chi phí duy trì và mức độ an toàn của dữ liệu.

> **Lưu ý về số liệu:** Các giới hạn dung lượng, IOPS và throughput trong bài phản ánh tài liệu AWS EBS hiện hành để học cách ra quyết định; giá, quota, hỗ trợ instance và tính năng có thể thay đổi theo Region/nền tảng. Luôn xác minh thông số trước triển khai thực tế.

## 1. EBS là gì và giải quyết bài toán nào?

**Amazon EBS** cung cấp **block storage** bền vững cho workload sử dụng Amazon EC2 và một số dịch vụ AWS tích hợp. Đối với hệ điều hành, EBS thường xuất hiện như một **block device** (tương tự ổ đĩa) sau khi gắn vào instance. Người quản trị có thể tạo partition, filesystem, định dạng và mount volume theo nhu cầu.

Một EBS volume:

- Là tài nguyên được tạo trong **một Availability Zone cụ thể**; EC2 thông thường phải ở **cùng AZ** mới có thể attach.
- Tồn tại **độc lập với vòng đời chạy/dừng của EC2**. Tuy nhiên hành vi **xóa khi terminate** phụ thuộc cờ `DeleteOnTermination` của từng block device mapping; root volume thường có chính sách riêng.
- Có thể làm **root/boot volume**, **data volume**, hoặc lưu dữ liệu được đọc/ghi thường xuyên như cơ sở dữ liệu, index, log và dữ liệu ứng dụng.
- Có thể được **điều chỉnh dung lượng hoặc hiệu năng** với **Elastic Volumes** ở các điều kiện hỗ trợ mà không nhất thiết detach/reboot instance.
- Hỗ trợ **EBS snapshot** để tạo điểm khôi phục và sao chép sang AZ khác thông qua việc tạo volume mới từ snapshot.
- Cung cấp các loại ổ SSD/HDD được tối ưu cho tải và đặc tính chi phí khác nhau.

### EBS là block storage, không tự tạo filesystem

~~~mermaid
flowchart LR
    A[Amazon EC2 instance] --> B[EBS block device]
    B --> C[Partition / filesystem: ext4, XFS, NTFS...]
    C --> D[Mount point: /data hoặc ổ D:]
    A --> E[Ứng dụng / DB]
    E --> D
    B --> F[EBS snapshot]
    F --> G[Khôi phục thành volume khác]
~~~

Ví dụ một EC2 chạy PostgreSQL có **root volume gp3** chứa hệ điều hành và **data volume gp3 hoặc io2** chứa thư mục dữ liệu DB. OS có thể thấy ổ như `/dev/nvme1n1` trên Nitro instance, sau đó mount vào `/var/lib/postgresql`. EBS không tự biết đó là PostgreSQL: database, filesystem và ứng dụng vẫn chịu trách nhiệm ghi dữ liệu nhất quán.

### EBS khác các lựa chọn lưu trữ AWS thế nào?

| Dịch vụ | Cách truy cập | Phạm vi/thế mạnh | Bài toán phù hợp |
| --- | --- | --- | --- |
| **Amazon EBS** | Block device gắn vào EC2 | Volume gắn một AZ, độ trễ thấp, random I/O; có snapshot | Root disk, database trên EC2, log/index, dữ liệu ứng dụng |
| **Amazon EFS** | Shared file system qua NFS | Chia sẻ file cho nhiều instance qua các AZ trong phạm vi cấu hình hỗ trợ | Web/content chung, home directory, workload cần POSIX NFS |
| **Amazon S3** | Object storage qua API | Object bền vững, lưu trữ và phân phối dữ liệu quy mô lớn | Ảnh, video, backup, data lake, object tĩnh |
| **EC2 instance store** | Block device cục bộ của host phần cứng | Có thể có I/O rất cao nhưng dữ liệu có tính tạm thời | Cache/scratch, dữ liệu tái tạo được, xử lý trung gian |
| **Amazon FSx** | File system quản lý theo biến thể | Chuyên biệt cho Windows, Lustre, ONTAP, OpenZFS và nhu cầu hỗ trợ | File share/doanh nghiệp, HPC, ứng dụng phụ thuộc giao thức file |

**Không chọn EBS nếu yêu cầu thực tế là nhiều container/EC2 ở nhiều AZ cùng truy cập và sửa một thư mục chung qua NFS.** Tình huống đó thường nên đánh giá EFS hoặc FSx. EBS **Multi-Attach** có hỗ trợ chia sẻ block cho các trường hợp chuyên biệt, nhưng không biến EBS thành shared filesystem thông thường và không mở rộng Multi-Attach qua nhiều AZ.

## 2. Phạm vi AZ, khả năng bền vững và vòng đời của volume

Giả sử Region là `ap-southeast-1`, gồm các AZ khác nhau. Một EBS volume ở AZ A không được gắn trực tiếp vào EC2 ở AZ B.

~~~mermaid
flowchart TB
  subgraph Region["AWS Region"]
    subgraph A["Availability Zone A"]
      EC2A[EC2 application A] --- EBS[(EBS data volume)]
    end
    subgraph B["Availability Zone B"]
      EC2B[EC2 replacement B]
      EBSB[(Volume được khôi phục từ snapshot)]
      EC2B --- EBSB
    end
    EBS -. Tạo snapshot .-> Snap[EBS snapshot trong Region]
    Snap -. Tạo volume mới ở AZ B .-> EBSB
  end
~~~

Điều này dẫn tới các kết luận thiết kế quan trọng:

1. **EBS không phải ổ đĩa truy cập trực tiếp từ mọi AZ.** Bên trong AZ, AWS đã thiết kế EBS để có tính bền vững/khả dụng phù hợp loại volume, nhưng một volume đơn lẻ vẫn thuộc một AZ.
2. **Dừng (stop) EC2 không đồng nghĩa mất EBS.** Việc terminate EC2 có thể tự xóa root volume và có thể xóa data volume nếu `DeleteOnTermination=true`.
3. **Snapshot cung cấp cơ chế khôi phục.** Snapshot được AWS lưu trên hạ tầng S3 quản lý nội bộ ở cấp Region và sao chép dữ liệu snapshot qua các AZ trong Region; người dùng không truy cập trực tiếp snapshot bằng S3 API.
4. **Khôi phục ở AZ khác** cần tạo **volume mới từ snapshot** ở AZ đích, attach vào instance trong AZ đó và xử lý consistency/application recovery.
5. **Disaster recovery liên Region** thường cần copy snapshot sang Region khác hoặc áp dụng cơ chế DR của database; bản thân EBS volume không tự sao chép đồng bộ sang Region khác.

**EBS volume có độ bền dữ liệu cao không có nghĩa toàn ứng dụng đạt High Availability.** Nếu service chỉ có một EC2 ở một AZ, AZ xảy ra sự cố vẫn có thể làm ứng dụng ngừng phục vụ. Cần thiết kế Multi-AZ, database replication/failover, health checks, bảo vệ dữ liệu và thử khôi phục dựa vào mục tiêu RTO/RPO.

## 3. Hiểu đúng ba chỉ số hiệu năng: IOPS, throughput và latency

### 3.1. IOPS: số thao tác I/O mỗi giây

**IOPS (Input/Output Operations Per Second)** đo số lần đọc/ghi trong một giây. Workload cần nhiều thao tác nhỏ, ngẫu nhiên, như OLTP database hoặc transaction log, thường quan tâm IOPS và độ trễ.

Ví dụ: 3.000 IOPS với I/O 16 KiB có lượng dữ liệu lý thuyết khoảng:

\[
3{,}000 \times 16\ \text{KiB/s} \approx 46.9\ \text{MiB/s}
\]

Nếu mỗi I/O 256 KiB và cùng 3.000 IOPS, throughput lý thuyết tăng nhiều lần, nhưng có thể bị **giới hạn throughput của EBS volume/instance** trước khi đạt mức đó.

### 3.2. Throughput: lượng dữ liệu đọc/ghi mỗi giây

**Throughput** thường đo bằng **MiB/s**. Tải xử lý file lớn, quét tuần tự, batch ETL, log pipeline và data warehouse có thể bị giới hạn bởi throughput hơn là IOPS.

Quan hệ xấp xỉ để lập kế hoạch:

\[
\text{Throughput (MiB/s)}
\approx \frac{\text{IOPS}\times\text{I/O size (KiB)}}{1{,}024}
\]

**Giới hạn thực tế** còn phụ thuộc vào loại EBS, kích thước I/O mà dịch vụ hạch toán, I/O song song, instance bandwidth, filesystem và đặc tính ứng dụng. Đây là mô hình tính sơ bộ, không phải cam kết benchmark.

### 3.3. Latency: thời gian hoàn tất một I/O

**Latency** là thời gian từ khi gửi yêu cầu I/O đến khi nhận kết quả, thường đo bằng ms hoặc µs. Database giao dịch nhạy với latency hơn các batch job không cần phản hồi tức thì.

Ngay cả khi volume được cấp 20.000 IOPS, workload gửi **từng I/O tuần tự một lần** và có độ trễ cao sẽ không tận dụng được năng lực cấp phát. Bởi vậy cần xem **queue depth/concurrency** cùng IOPS và throughput.

**Quy tắc gần đúng theo Little's Law** để hình dung I/O đang chờ:

\[
\text{Số I/O đang xử lý/chờ trung bình}
\approx \text{IOPS}\times\text{Latency (giây)}
\]

Ví dụ 10.000 IOPS ở 1 ms tương ứng khoảng 10 I/O đồng thời. Đây là phép hình dung khi hệ thống tương đối ổn định, không thay thế benchmark/đo lường.

### 3.4. Vì sao chọn ổ đĩa không chỉ nhìn IOPS tối đa?

Hiệu năng cuối cùng bị chặn bởi **mắt xích nhỏ nhất**:

~~~mermaid
flowchart LR
    APP[Ứng dụng: truy vấn / ghi file] --> FS[Filesystem & OS I/O scheduler]
    FS --> EC2[EC2 EBS bandwidth / IOPS cap]
    EC2 --> VOL[EBS volume: IOPS, throughput, latency]
    VOL --> OBS[CloudWatch metrics / benchmark]
~~~

- **Volume cap:** gp3 cấp 8.000 IOPS không tự bảo đảm mọi workload đạt 8.000.
- **Instance cap:** một instance EC2 có giới hạn tổng IOPS/throughput EBS. Gắn nhiều volume không vượt qua tổng giới hạn instance.
- **I/O pattern:** tuần tự/lớn thường ưu tiên throughput; ngẫu nhiên/nhỏ ưu tiên IOPS và latency.
- **Cache, filesystem, queue depth:** có thể gây biến động số liệu; số IOPS trên OS khác với số thao tác đã được gộp ở storage.
- **Dữ liệu khôi phục từ snapshot:** volume chưa được khởi tạo đầy đủ có thể gặp độ trễ cao hơn khi lần đầu đọc block chưa được tải; cần có kế hoạch khởi tạo dữ liệu.

## 4. Các loại EBS volume phổ biến

Bảng sau tập trung vào lựa chọn thực tế, không phải bảng giá niêm yết.

| Loại volume | Công nghệ / mục tiêu | Dung lượng được hỗ trợ | Giới hạn tối đa theo tài liệu AWS | Boot volume |
| --- | --- | --- | --- | --- |
| **gp3** | SSD đa dụng, cấp IOPS và throughput độc lập với dung lượng | **1 GiB–64 TiB** | **80.000 IOPS**, **2.000 MiB/s** với đủ điều kiện dung lượng, tỉ lệ và instance | Có |
| **gp2** | SSD đa dụng thế hệ trước; IOPS phụ thuộc kích thước volume và burst credits | **1 GiB–16 TiB** | **16.000 IOPS**, **250 MiB/s** | Có |
| **io2 Block Express** | SSD Provisioned IOPS, hiệu năng bền vững và độ trễ thấp | **4 GiB–64 TiB** | **256.000 IOPS**, **4.000 MiB/s** khi instance/cấu hình hỗ trợ | Có |
| **io1** | SSD Provisioned IOPS thế hệ trước | **4 GiB–16 TiB** | **64.000 IOPS**, **1.000 MiB/s** tùy instance/cấp phát | Có |
| **st1** | HDD tối ưu throughput cho truy cập tuần tự thường xuyên | **125 GiB–16 TiB** | **500 MiB/s** tối đa/volume, theo cơ chế throughput credits | Không |
| **sc1** | HDD chi phí thấp cho truy cập tuần tự ít thường xuyên | **125 GiB–16 TiB** | **250 MiB/s** tối đa/volume, theo cơ chế throughput credits | Không |
| **standard** | Magnetic đời cũ; chủ yếu hệ thống legacy | **1 GiB–1 TiB** | Hiệu năng thấp/biến động, không khuyến nghị cho triển khai mới | Có |

**Lưu ý về max IOPS/throughput:** Đây là **trần kỹ thuật**, không phải giá trị có sẵn cho mọi volume. Phải đáp ứng giới hạn theo dung lượng, tỉ lệ IOPS/GiB, loại EC2 (đặc biệt Nitro), EBS-optimized bandwidth, điều kiện Region và quota. Ví dụ không thể cấu hình gp3 1 GiB ở mức 80.000 IOPS chỉ vì dòng bảng ghi tối đa 80.000.

### 4.1. gp3: lựa chọn khởi đầu cho đa số workload

`gp3` thường là phương án **mặc định để khảo sát trước** cho root disk, dữ liệu ứng dụng, môi trường dev/test và database có hiệu năng từ thấp tới vừa/cao:

- **3.000 IOPS** và **125 MiB/s throughput** ở mức nền đã bao gồm trong giá dung lượng, không phụ thuộc trực tiếp vào việc tăng size.
- Có thể cấp thêm đến **80.000 IOPS** và **2.000 MiB/s** theo tỉ lệ và giới hạn kỹ thuật tương ứng; phần vượt mức nền có phí hiệu năng bổ sung.
- Không dùng cơ chế **burst credits** cho mức IOPS/throughput đã provision, giúp hiệu năng có thể duy trì ổn định hơn gp2 cùng quy mô.
- Cấu hình performance tách khỏi capacity giúp tránh mua dung lượng dư chỉ để nâng IOPS.

**Điều kiện bổ sung nên nhớ:** Phần IOPS gp3 cấp thêm tuân theo tỉ lệ tối đa **500 IOPS/GiB**; đạt 80.000 IOPS cần volume tối thiểu **160 GiB**. Throughput provisioned tối đa tuân theo tỉ lệ **0,25 MiB/s trên mỗi IOPS** và các điều kiện khác; mức 2.000 MiB/s cần tối thiểu **8.000 IOPS** và **16 GiB** dung lượng, cùng instance đủ mạnh.

Ví dụ: Cần 120 GiB dữ liệu và 6.000 IOPS/250 MiB/s. gp3 cho phép tạo 120 GiB với IOPS và throughput theo mục tiêu, thay vì tăng volume chỉ để lấy IOPS như gp2. Nhưng 6.000 IOPS/250 MiB/s **không phải cấu hình miễn phí**: phần vượt baseline sẽ được tính phí theo biểu giá áp dụng.

### 4.2. gp2: hiểu để vận hành hệ thống cũ

`gp2` dựa nhiều vào **dung lượng volume** để quyết định hiệu năng nền, với khoảng **3 IOPS/GiB** (có sàn/tối đa theo tài liệu); các volume nhỏ có thể tạm **burst lên 3.000 IOPS** nhờ I/O credit balance. Khi credit giảm, IOPS bền vững có thể thấp hơn mức đang burst.

Ví dụ gần đúng:

- gp2 **100 GiB**: baseline khoảng **300 IOPS**, có thể burst cao hơn khi còn credits.
- gp2 **1 TiB**: baseline xấp xỉ **3.072 IOPS**.
- Volume gp2 rất lớn có thể đạt **16.000 IOPS** theo giới hạn của loại.

Không nên nhìn một benchmark chạy vài phút trên gp2 nhỏ rồi kết luận có thể duy trì throughput/IOPS liên tục. Cần quan sát tải dài hơn và các metric burst balance khi áp dụng. Với workload mới, gp3 thường đơn giản hơn để dự toán và kiểm soát hiệu năng.

### 4.3. io2 Block Express và io1: hiệu năng cao, độ trễ thấp

`io2 Block Express` là lựa chọn đáng đánh giá cho database rất nhạy latency, giao dịch random I/O lớn và workload cần **sustained IOPS** cao hơn vùng khả năng phù hợp của gp3. Theo tài liệu AWS hiện hành, `io2` hiện vận hành trên hạ tầng **Block Express** đối với cả volume hiện có và volume mới.

Các đặc tính được công bố:

- Dung lượng tối đa **64 TiB**.
- IOPS provisioned lên đến **256.000**, theo tỉ lệ tối đa **1.000 IOPS/GiB** và giới hạn của instance.
- Throughput tối đa **4.000 MiB/s**.
- Độ trễ trung bình được thiết kế **dưới 500 µs** với I/O 16 KiB trong điều kiện đặc tả, thấp hơn mức thường gặp của general purpose SSD.

Những con số này yêu cầu **EC2 phù hợp (đặc biệt Nitro)**, cấu hình đủ IOPS, bandwidth và workload đủ concurrency. Cân nhắc chi phí dung lượng cộng phí IOPS trước khi chọn io2.

`io1` là loại Provisioned IOPS SSD cũ hơn, có thể xuất hiện trong hạ tầng đã triển khai. Với triển khai mới, AWS thường hướng người dùng tới `io2` vì đặc tính hiệu năng/độ bền và hỗ trợ mới; không chọn io1 chỉ vì thói quen.

### 4.4. st1 và sc1: HDD cho luồng truy cập tuần tự

`st1` và `sc1` phù hợp **throughput-oriented workloads**, nơi phần lớn I/O là đọc/ghi block tương đối lớn, tuần tự:

- **st1**: Big data, data warehouse trên EC2, log processing và batch scan với nhu cầu throughput cao.
- **sc1**: Dữ liệu ít truy cập, vẫn cần block device để xử lý tuần tự và ưu tiên chi phí dung lượng thấp.
- **Cả hai không hỗ trợ làm boot volume**.
- **Không phù hợp** database OLTP, random I/O nhỏ, yêu cầu latency thấp.
- Hiệu năng phụ thuộc **throughput credit balance**, kích thước volume và dạng truy cập; peak khác sustained throughput.

Khi dữ liệu ít truy cập nhưng không cần mount block device, **S3 với storage class/lifecycle phù hợp** có thể kinh tế và linh hoạt hơn sc1. Đừng kết luận HDD luôn rẻ nhất chỉ từ giá/GiB mà không xét thao tác, bản sao, snapshot và công quản trị.

### 4.5. standard (Magnetic): tránh triển khai mới

`standard` là loại Magnetic thuộc thế hệ trước, có hiệu năng không ổn định và không phù hợp workload hiện đại đòi hỏi độ trễ thấp. Khi gặp hệ thống cũ, cần đánh giá đường chuyển sang gp3 hoặc loại khác phù hợp, đảm bảo điều kiện boot/OS/app và thử dữ liệu/hiệu năng trước khi chuyển.

## 5. Ma trận chọn loại EBS theo workload

| Workload / yêu cầu thực | Điểm cần đo | Phương án bắt đầu khảo sát | Khi nào xem xét loại khác |
| --- | --- | --- | --- |
| Root volume Linux/Windows, công cụ CI, ứng dụng web | IOPS bình thường, thời gian boot, dung lượng | **gp3** | Nếu hiệu năng rất đặc biệt hoặc giới hạn nền tảng khác |
| MySQL/PostgreSQL trên EC2, tải giao dịch vừa | Random IOPS, p95/p99 latency, WAL/redo, throughput | **gp3** được cấu hình theo số đo | **io2** nếu cần sustained IOPS/latency vượt khả năng gp3 |
| Database giao dịch cao, latency rất nhạy | IOPS ổn định, tail latency, thời gian chờ I/O | **io2 Block Express** | gp3 nếu benchmark chứng minh đáp ứng với chi phí tốt hơn |
| Log analytics đọc tuần tự dữ liệu lớn | Throughput, block size, thời gian quét | **st1** | gp3 khi cần random I/O hay latency thấp |
| Bộ dữ liệu lạnh nhưng còn dùng block volume | Tần suất đọc, yêu cầu mount, tốc độ truy cập | **sc1** | **S3** nếu có thể chuyển từ block sang object |
| App cần NFS shared files từ nhiều AZ | File semantics, số client, latency, throughput | **EFS/FSx**, không ép vào EBS thông thường | EBS chỉ nếu dữ liệu thực sự là block riêng cho từng instance |
| Container stateful | Cách scheduler ràng buộc AZ, access mode, downtime | EBS CSI driver + **gp3** khi dữ liệu có thể gắn theo AZ | EFS/FSx hoặc DB managed nếu cần chia sẻ/multi-AZ |
| Scratch/cache có thể tái tạo | Tốc độ và mức chấp nhận mất dữ liệu | **Instance store** nếu instance phù hợp | gp3 nếu cần bền vững sau vòng đời host |
| Dữ liệu ảnh/video/tệp người dùng | API truy cập, chia sẻ rộng, lifecycle | **S3** | EBS chỉ khi phần mềm bắt buộc có filesystem cục bộ |

**Mẹo:** Với một workload không có yêu cầu rõ ràng về đĩa, bắt đầu bằng **gp3**, đặt mức nền, đo và chỉnh. Hãy chọn loại cao cấp hơn khi đã có bằng chứng về bottleneck, latency hoặc mục tiêu bền vững cụ thể.

## 6. Quy trình chọn EBS volume trong sáu bước

### Bước 1 — Mô tả dữ liệu và các ràng buộc

Thu thập:

- **Dung lượng hiện tại** (GiB/TiB), tăng trưởng/ngày hoặc tháng, tỷ lệ dùng thực, nhu cầu mở rộng.
- **Loại I/O:** random hay sequential, read/write ratio, I/O size phổ biến, số request đồng thời.
- **SLO:** p95/p99 read/write latency, thời gian hoàn thành batch, throughput tối thiểu khi cao điểm.
- **Mức bền vững và phục hồi:** RTO, RPO, yêu cầu multi-AZ hoặc multi-Region; mức độ quan trọng khi volume bị mất/corrupt.
- **Tính di động:** data có thể tái tạo không, có cần chuyển instance/AZ/Region không, có phải root disk không.
- **Bảo mật:** mã hóa, KMS, IAM, lưu trữ log, quy định backup và thời gian giữ.

### Bước 2 — Xác định thiết bị cần boot, block hay shared file

Nếu OS khởi động từ ổ đó, **loại st1/sc1 không phù hợp**. Nếu nhiều workload cần chia sẻ filesystem, trước khi nghĩ tới EBS Multi-Attach hãy xét EFS/FSx và tính nhất quán dữ liệu.

### Bước 3 — Phân biệt giới hạn theo IOPS, throughput hoặc latency

Ví dụ workload trung bình 4.000 IOPS với mỗi request 16 KiB tương đương khoảng **62,5 MiB/s** nếu I/O hoàn toàn theo mẫu này. `gp3` với 4.000 IOPS và 125 MiB/s có thể đủ ở lý thuyết, nhưng cần thử latency và burst của workload thực.

Với batch job cần **500 MiB/s** luồng tuần tự, 3.000 IOPS của gp3 có thể không phải vấn đề chính; xem throughput provisioned, I/O size và khả năng EC2 đẩy đủ bandwidth.

### Bước 4 — Kiểm tra trần hiệu năng của EC2 và AZ

- EC2 instance có hỗ trợ loại volume/tốc độ cấp phát mong muốn không?
- Tổng **EBS bandwidth và IOPS cap** của instance có đáp ứng **tổng số volume**?
- EC2 và EBS có ở **cùng AZ**?
- Quota account/Region có đủ? Có giới hạn số volume gắn với instance không?
- Nếu cần EBS Multi-Attach, instance có thuộc nhóm Nitro được hỗ trợ và ứng dụng có quản lý ghi đồng thời không?

Chỉ mua io2 100.000 IOPS rồi gắn vào instance có cap thấp hơn là một dạng lãng phí. Cần rà soát **cả instance type và storage**.

### Bước 5 — So sánh tổng chi phí

Tổng chi phí không chỉ là **GiB × giá/GiB-tháng**. Bao gồm IOPS và throughput provisioned (nếu có), snapshots/copy/khôi phục, data transfer, KMS request, giám sát và thời gian vận hành. Đo trên đúng Region và kịch bản.

### Bước 6 — Benchmark, đưa vào hoạt động và xem lại

Dùng workload thật hoặc benchmark có cùng kích thước I/O, queue depth, thời lượng. Quan sát **IOPS, throughput, latency, queue length, saturation, CPU và mức chờ I/O**. Đặt ngưỡng cảnh báo, ghi quyết định và xem lại khi workload thay đổi.

~~~mermaid
flowchart TD
  A[Đọc yêu cầu dữ liệu và SLO] --> B{Cần filesystem dùng chung nhiều AZ?}
  B -->|Có| C[Đánh giá EFS/FSx]
  B -->|Không| D{Random I/O, độ trễ thấp?}
  D -->|Có| E[Đánh giá gp3]
  E --> F{Đã đo, gp3 không đáp ứng IOPS/latency bền vững?}
  F -->|Có| G[Đánh giá io2 Block Express]
  F -->|Không| H[Giữ gp3, chỉnh IOPS/throughput theo đo đạc]
  D -->|Không, chủ yếu tuần tự| I{Truy cập nhiều hay ít?}
  I -->|Nhiều| J[Đánh giá st1 hoặc gp3]
  I -->|Ít| K[Đánh giá sc1 hoặc S3]
  G --> L[Kiểm tra EC2/AZ, chi phí, restore và benchmark]
  H --> L
  J --> L
  K --> L
~~~

## 7. Bài toán chọn volume có số liệu

### Ví dụ A — API CRUD với database PostgreSQL trên EC2

**Giả định:**

- Dữ liệu hiện tại 180 GiB, dự kiến 300 GiB trong năm đầu.
- Cao điểm 5.000 IOPS, I/O size trung bình 16 KiB.
- Mong muốn throughput tối thiểu 200 MiB/s; p95 latency cần được benchmark.
- Dữ liệu giao dịch quan trọng, có backup và quy trình phục hồi.

**Ước lượng:** `5.000 × 16 / 1.024 ≈ 78,1 MiB/s` với kích thước I/O giả định; throughput 200 MiB/s tạo dư địa cho read/write hoặc I/O lớn hơn, nhưng **không bảo đảm latency**. Bắt đầu với **gp3 300 GiB, 6.000 IOPS, 250 MiB/s** trên EC2 đủ EBS bandwidth. So với gp3 baseline, IOPS/throughput cấp thêm có tính phí.

**Chưa đủ căn cứ chọn io2** chỉ vì workload là database. Nên đo khi peak; nếu gp3 không đáp ứng tail latency hoặc sustained IOPS dù instance đã đủ, so sánh io2 Block Express.

**Phục hồi:** Backup/snapshot có điểm nhất quán DB (hoặc cơ chế của DB), giám sát tăng trưởng, thử restore. Nếu yêu cầu chịu lỗi một AZ mà thời gian khôi phục từ snapshot không đạt RTO, kiến trúc cần **DB replication/failover** thay vì trông chờ volume đơn lẻ.

### Ví dụ B — Batch phân tích 2 TiB dữ liệu log

**Giả định:** một EC2 chạy batch quét file lớn liên tục vài giờ/ngày; chủ yếu đọc tuần tự, ít random I/O, không dùng ổ làm boot.

**Gợi ý:** Khảo sát **st1** do tối ưu throughput và chi phí cho tuần tự. Cần tính sustained throughput, lịch chạy và throughput credits; nếu quét lâu khiến credit cạn thì thời gian hoàn thành có thể kéo dài. So sánh gp3 khi job cần throughput ổn định, random metadata/file nhỏ hoặc lúc cao điểm.

**Lưu ý:** Nếu log có thể chuyển sang S3 và xử lý bằng Athena, Glue, EMR hoặc kiến trúc khác, nên đánh giá lại nhu cầu có block volume tại mọi thời điểm.

### Ví dụ C — EC2 chạy Windows legacy với ổ ít được đọc

**Giả định:** ổ C: cần boot ổn định; ổ D: chứa tệp xuất báo cáo mỗi tháng, đọc tuần tự; dữ liệu phải giữ sau EC2 stop.

**Gợi ý:** C: **gp3** vì làm boot. D: có thể thử **sc1** nếu ứng dụng chịu được latency và throughput, dung lượng đạt tối thiểu; nhưng S3 có thể hợp lý hơn nếu file không cần ở dạng block device. Đặt lịch snapshot/lifecycle riêng theo mục tiêu dữ liệu.

### Ví dụ D — Dịch vụ tài chính cần random I/O lớn, latency thấp

**Giả định:** nhóm vận hành đã thử gp3 nhưng không đạt tail latency, yêu cầu sustained IOPS và số thao tác đồng thời cao, EC2 Nitro đủ mạnh.

**Gợi ý:** Đánh giá **io2 Block Express** với kích thước/IOPS đúng tỉ lệ, benchmark p95/p99 và throughput. Xem kế hoạch HA/DR và khả năng triển khai ngân sách; khả năng một volume nhanh không bảo đảm khả dụng toàn hệ thống.

## 8. Tạo, gắn và mount volume trong một lab

> **Điều kiện thực hành:** Dùng EC2 và account lab đã được cấp quyền; các ID bên dưới là minh họa. Hãy thay toàn bộ giá trị ví dụ bằng ID thật trước khi thực hiện. Lệnh `mkfs` **xóa cấu trúc dữ liệu hiện có trên thiết bị**: chỉ sử dụng khi đã xác nhận đúng một volume trắng mới tạo. Với production, cần quy trình review, snapshot/backup và kế hoạch rollback.

### 8.1. Kiểm tra Availability Zone của EC2

~~~bash
aws ec2 describe-instances \
  --instance-ids i-0123456789abcdef0 \
  --query 'Reservations[].Instances[].{Id:InstanceId,AZ:Placement.AvailabilityZone,State:State.Name}' \
  --region ap-southeast-1 \
  --profile lab
~~~

Giả sử EC2 nằm ở `ap-southeast-1a`. AZ tên `1a` là ký hiệu phụ thuộc account; muốn so sánh AZ giữa account có thể dùng **AZ ID** thay vì chỉ tên hiển thị.

### 8.2. Tạo gp3 100 GiB ở cùng AZ

~~~bash
aws ec2 create-volume \
  --availability-zone ap-southeast-1a \
  --size 100 \
  --volume-type gp3 \
  --iops 3000 \
  --throughput 125 \
  --encrypted \
  --tag-specifications 'ResourceType=volume,Tags=[{Key=Name,Value=lab-data-gp3},{Key=Environment,Value=lab}]' \
  --region ap-southeast-1 \
  --profile lab
~~~

Lệnh trả về `VolumeId` dạng `vol-...` cùng trạng thái khởi tạo. Mặc định `--encrypted` dùng cơ chế khóa EBS phù hợp cấu hình tài khoản/Region; nếu yêu cầu **customer managed KMS key**, cần chỉ định khóa và cấp quyền KMS tương ứng. Không nhúng access key/secret vào script.

Kiểm tra trạng thái:

~~~bash
aws ec2 describe-volumes \
  --volume-ids vol-0123456789abcdef0 \
  --query 'Volumes[0].{Id:VolumeId,State:State,AZ:AvailabilityZone,Type:VolumeType,Size:Size,Iops:Iops,Throughput:Throughput,Encrypted:Encrypted}' \
  --region ap-southeast-1 \
  --profile lab
~~~

### 8.3. Attach EBS vào EC2

Khi volume ở trạng thái `available`:

~~~bash
aws ec2 attach-volume \
  --volume-id vol-0123456789abcdef0 \
  --instance-id i-0123456789abcdef0 \
  --device /dev/sdf \
  --region ap-southeast-1 \
  --profile lab
~~~

Thiết bị OS thấy có thể mang **tên khác** `/dev/sdf`, đặc biệt với **EC2 Nitro/NVMe**. Kiểm tra trong instance bằng:

~~~bash
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS,MODEL
sudo blkid
~~~

Nếu có nhiều volume giống size, đối chiếu **volume ID ↔ NVMe device** bằng tiện ích AWS/NVMe phù hợp hoặc metadata của thiết bị. **Không dựa duy nhất vào tên `/dev/nvme1n1`** vì thứ tự có thể thay đổi khi reboot/attach.

### 8.4. Định dạng và mount lần đầu (chỉ volume trắng mới)

Ví dụ dưới đây giả định **đã xác minh chắc chắn** device của volume mới là `/dev/nvme1n1` và **không chứa filesystem/dữ liệu cần giữ**:

~~~bash
# Kiểm tra lần cuối trước khi thao tác phá dữ liệu
sudo file -s /dev/nvme1n1
lsblk -f /dev/nvme1n1

# CHỈ trên volume trắng mới tạo, chưa có filesystem:
sudo mkfs.ext4 /dev/nvme1n1

sudo mkdir -p /data
sudo mount /dev/nvme1n1 /data
df -h /data
~~~

Để mount bền vững qua reboot, lấy **filesystem UUID**:

~~~bash
sudo blkid /dev/nvme1n1
~~~

Với UUID thật, thêm một dòng kiểu sau vào `/etc/fstab` theo quy trình quản trị hệ điều hành:

~~~text
UUID=<filesystem-uuid-thuc-te> /data ext4 defaults,nofail 0 2
~~~

Sau đó kiểm tra cú pháp/khả năng mount và rollback trên instance lab. `nofail` giúp boot linh hoạt hơn nếu ổ phụ thiếu, nhưng ứng dụng phải xử lý tình huống mount không sẵn sàng, tránh ghi nhầm dữ liệu vào ổ root.

**Windows:** Có thể attach EBS tương tự qua AWS API, sau đó sử dụng **Disk Management** hoặc công cụ Windows để đưa disk online, khởi tạo/format khi thực sự trắng và gán drive letter. Với disk có dữ liệu, tuyệt đối không initialize/format lại.

### 8.5. Vận hành an toàn

- Tách **OS volume** khỏi **data volume** khi việc backup, resize và quyền truy cập dữ liệu cần quản trị độc lập.
- Không lưu dữ liệu duy nhất trên một volume mà không có snapshot/replication tương ứng RPO.
- Nếu detach volume đang có ghi, flush và **unmount/quiesce ứng dụng** trước, nhất là database.
- Khi thay EC2, luôn kiểm tra AZ trùng volume và chính sách `DeleteOnTermination` của từng mapping.

## 9. Tăng dung lượng và chuyển gp2 sang gp3 bằng Elastic Volumes

EBS có cơ chế **Elastic Volumes** để thay đổi dung lượng, volume type, IOPS và throughput theo loại và môi trường hỗ trợ. Trên instance hiện đại, nhiều thay đổi có thể tiến hành lúc volume đang attach và ứng dụng vẫn chạy; nhưng **không đồng nghĩa mọi thay đổi đều không ảnh hưởng hiệu năng hoặc có thể rollback ngay**.

### 9.1. Ví dụ tăng từ 100 GiB lên 200 GiB và chỉnh hiệu năng

~~~bash
aws ec2 modify-volume \
  --volume-id vol-0123456789abcdef0 \
  --volume-type gp3 \
  --size 200 \
  --iops 6000 \
  --throughput 250 \
  --region ap-southeast-1 \
  --profile lab
~~~

Kiểm tra:

~~~bash
aws ec2 describe-volumes-modifications \
  --volume-ids vol-0123456789abcdef0 \
  --region ap-southeast-1 \
  --profile lab
~~~

Các trạng thái có thể gồm `modifying`, `optimizing`, `completed`; theo dõi trạng thái và thông báo lỗi thực tế. **Không lặp modify liên tục**: AWS đặt giới hạn tần suất thay đổi và yêu cầu mỗi modification hoàn tất trước khi bắt đầu lần mới. Thay đổi có thể diễn ra trong nhiều phút hoặc nhiều giờ tùy dung lượng và điều kiện.

### 9.2. Tăng EBS không tự tăng filesystem

Sau khi AWS đã tăng block volume, hệ điều hành còn phải:

1. Nhận ra **disk size mới**.
2. Nếu filesystem nằm trên **partition**, tăng partition tương ứng.
3. **Extend filesystem** để sử dụng không gian bổ sung.

Ví dụ (đã xác minh thiết bị chính xác):

~~~bash
lsblk
df -hT /data

# Chỉ khi filesystem ext4 đặt trực tiếp trên toàn bộ block device:
sudo resize2fs /dev/nvme1n1
~~~

Nếu ext4 nằm trên partition, cần mở rộng partition bằng công cụ như `growpart` trước rồi resize filesystem trên **partition device**, không phải raw disk. Nếu là **XFS**, dùng công cụ `xfs_growfs` trên **mount point** đã mount (ví dụ `/data`), theo hướng dẫn hệ điều hành. Windows dùng Disk Management/PowerShell để Extend Volume theo điều kiện tương ứng.

**Cần kiểm tra loại filesystem, layout (LVM/RAID/partition), dung lượng block và điểm mount** trước khi chạy bất kỳ lệnh chỉnh kích thước nào. Với hệ thống có partition mã hóa, LVM hoặc RAID, còn các lớp phải resize theo thứ tự đúng.

### 9.3. Vì sao không thể giảm size trực tiếp?

Elastic Volumes cho phép **tăng**, nhưng **không giảm trực tiếp size của một EBS volume**. Nếu muốn giảm chi phí cho volume quá lớn:

1. Sao lưu và kiểm chứng khả năng phục hồi.
2. Tạo volume **nhỏ hơn** đủ chứa dữ liệu và phù hợp loại.
3. Tạo filesystem trên volume mới đúng cách.
4. Dùng công cụ file/application-aware như `rsync`, backup/restore database hoặc `robocopy` của Windows.
5. Kiểm tra dữ liệu, downtime, quyền và chuyển ứng dụng sang volume mới.
6. Chỉ dọn volume cũ sau khi xác nhận ổn định và có đường rollback.

**Một snapshot từ volume lớn không thể dùng trực tiếp để tạo volume nhỏ hơn snapshot gốc** chỉ bằng việc nhập kích thước nhỏ hơn.

### 9.4. Chuyển gp2 sang gp3 cần chú ý gì?

Giả sử volume gp2 hiện tại có 500 GiB và hiệu năng thực tế cao hơn mức gp3 baseline ở một số chỉ số. Nếu sửa sang gp3 mà **không truyền IOPS/throughput**, AWS có cơ chế giữ ít nhất một số mức hiệu năng tương đương gp2 hoặc baseline gp3; vì vậy **không nên mặc định sau migration chỉ tốn giá storage gp3 nền**.

Quy trình đúng:

- Đo IOPS/throughput thực tế ở thời điểm cao điểm, thời gian dài và burst.
- Chọn gp3 với **IOPS/throughput được khai báo chủ đích** phù hợp SLO.
- Ước lượng chi phí storage + phần performance trả thêm.
- Xác nhận loại/size/IOPS/throughput trước–sau, monitor latency và lỗi.
- Giữ snapshot/rollback theo quy trình; thay đổi không phải thao tác “undo” đơn giản.

## 10. Mã hóa EBS, IAM và khóa KMS

Amazon EBS hỗ trợ **encryption at rest** và mã hóa dữ liệu trên đường truyền trong các khả năng được hỗ trợ. Mã hóa EBS dựa vào **AWS KMS** và có thể được áp dụng tự động nếu **EBS encryption by default** đã bật ở Region/account.

**Cần phân biệt:**

- **IAM permissions:** ai được `ec2:CreateVolume`, `ec2:AttachVolume`, `ec2:ModifyVolume`, `ec2:CreateSnapshot`, xóa tài nguyên hay truy cập bản sao?
- **KMS key policy và grants:** role/identity/dịch vụ có quyền dùng key để mã hóa/giải mã ở các thao tác cần thiết không? Với customer managed key và cross-account sharing, cần quản lý quyền khóa riêng.
- **OS/application:** EBS encryption bảo vệ dữ liệu ở tầng storage; ứng dụng vẫn cần TLS, secret management và xác thực nội bộ. Không có nghĩa mọi người có quyền truy cập instance sẽ bị ngăn đọc file.
- **Backup encryption:** snapshots kế thừa/quản lý encryption theo cấu hình; copy snapshot có thể liên quan key khác, quyền KMS và chi phí.

**Không thể bật mã hóa tại chỗ bằng một nút chuyển đơn giản trên EBS volume đã tồn tại không mã hóa.** Cách phổ biến là snapshot, tạo bản sao được mã hóa phù hợp, khôi phục volume mã hóa và chuyển workload một cách có kiểm soát. Phương án cụ thể cần xét root/data volume, downtime và KMS key.

Nên ưu tiên **mã hóa mặc định**, role tạm thời cho workload qua IAM, không để static credentials trên filesystem; audit thay đổi volume/snapshot/KMS bằng CloudTrail.

## 11. Snapshot, backup và kế hoạch phục hồi

**EBS snapshot** ghi lại dữ liệu block của volume tại một thời điểm, sử dụng cơ chế **incremental** sau snapshot đầu. AWS quản lý dữ liệu snapshot trên hạ tầng S3 nội bộ; snapshot không phải một S3 object mà người dùng có thể đọc bằng S3 API.

### 11.1. Snapshot dùng để làm gì?

- Phục hồi sau xóa file/sai cấu hình/mất volume nếu có điểm khôi phục phù hợp.
- Tạo volume mới từ snapshot trong AZ khác **cùng Region**.
- Copy snapshot sang **Region khác** để hỗ trợ disaster recovery.
- Hỗ trợ tạo AMI, clone môi trường thử nghiệm hoặc di chuyển dữ liệu với quy trình thích hợp.

**AWS không tự sao lưu dữ liệu EBS theo một chính sách backup mà bạn mong muốn.** Cần cấu hình lịch snapshots với **Amazon Data Lifecycle Manager** hoặc **AWS Backup**, tùy quy trình quản trị và yêu cầu phục hồi.

### 11.2. Point-in-time không tự bảo đảm application consistency

Nếu database đang ghi liên tục, snapshot của block volume có thể đạt **crash-consistent** thay vì **application-consistent** khi không phối hợp với phần mềm. Để có dữ liệu giao dịch có thể khôi phục đúng:

- Sử dụng cơ chế backup của DB hoặc quiesce/freeze I/O theo hướng dẫn.
- Với dữ liệu trải nhiều volume, xét snapshot đồng bộ nhiều volume hoặc giải pháp backup được hỗ trợ theo workload.
- Thiết kế transaction log, point-in-time recovery và chiến lược replication tương ứng DB.
- **Thử restore** trong môi trường riêng, kiểm tra tính toàn vẹn và chạy ứng dụng chứ không chỉ nhìn trạng thái `completed`.

### 11.3. Snapshot không thay High Availability

| Mục tiêu | Công cụ/thiết kế thích hợp | Điểm cần đánh giá |
| --- | --- | --- |
| Khôi phục file bị xóa / dữ liệu hỏng | Snapshot, AWS Backup, backup ứng dụng | Tần suất backup, restore test, quyền, retention |
| Khôi phục volume ở AZ khác | Snapshot → create volume ở AZ đích | Thời gian tạo và khởi tạo volume, app restart |
| Ứng dụng chịu lỗi một AZ | Replica/DB Multi-AZ hoặc kiến trúc có failover | Data consistency, failover time, health checks |
| Phục hồi mất cả Region | Copy snapshot liên Region hoặc DR replication | RPO/RTO, IAM/KMS, DNS, routing, dữ liệu phụ thuộc |
| Ứng dụng cần RPO gần 0 | Ghi dữ liệu đồng bộ/phương án DB phù hợp | Snapshot định kỳ thường không đủ |

**RTO (Recovery Time Objective)** = thời gian ứng dụng được phép ngừng phục vụ; **RPO (Recovery Point Objective)** = lượng dữ liệu theo thời gian được phép mất. Ví dụ snapshot mỗi 24 giờ không thể tự chứng minh RPO 15 phút.

### 11.4. Restore và lần đọc đầu tiên

Volume tạo từ snapshot có thể cần **khởi tạo dữ liệu** khi block được truy cập lần đầu, làm độ trễ ban đầu cao hơn. Với workload cần phục hồi nhanh và ổn định, đánh giá:

- Chủ động initialize/warm-up volume theo quy trình, tránh benchmark dữ liệu chưa khởi tạo.
- **Fast Snapshot Restore (FSR)** khi có yêu cầu cụ thể, kiểm tra AZ được bật và chi phí.
- Tùy khả năng dịch vụ tại thời điểm triển khai, chọn **provisioned volume initialization rate** cho volume mới từ snapshot trong trường hợp được hỗ trợ.
- Đo thời gian thực từ “snapshot sẵn sàng” đến “ứng dụng phục vụ đạt SLO”, thay vì chỉ đo tốc độ API tạo volume.

## 12. Multi-Attach không biến EBS thành shared filesystem thông thường

EBS **Multi-Attach** cho phép **một số volume Provisioned IOPS SSD** (`io1`, `io2`) gắn đồng thời với nhiều Nitro-based EC2 instances **trong cùng AZ**, tối đa số instance được hỗ trợ (theo tài liệu hiện hành: **16**). Đây là khả năng chuyên biệt cho workload có cơ chế phối hợp ghi ở cấp ứng dụng/cluster.

**Rủi ro lớn:** Nhiều máy cùng mount một filesystem thông thường như ext4/XFS và cùng ghi mà **không có cơ chế cluster filesystem/locking** có thể gây hỏng dữ liệu. Multi-Attach yêu cầu ứng dụng hiểu tính đồng thời, write ordering và cơ chế **I/O fencing** thích hợp.

Những điều cần nhớ:

- Multi-Attach **không** hoạt động trên gp2/gp3, st1/sc1.
- Các instance phải **cùng AZ**, không tự bảo vệ trước outage cấp AZ.
- Không hỗ trợ Multi-Attach làm boot volume.
- Nếu cần shared file từ nhiều AZ, hãy ưu tiên đánh giá **EFS/FSx**.
- Dự án Multi-Attach cần thiết kế storage cluster, fencing, quorum và kiểm thử failure, không chỉ bấm checkbox trong Console.

## 13. CloudWatch: đo bottleneck thay vì đoán

Amazon CloudWatch cung cấp các metric EBS để theo dõi I/O và hiệu năng. Xem ở **EC2 Console → Elastic Block Store → Volumes → chọn volume → Monitoring**, hoặc CloudWatch theo resource ID.

| Metric / chỉ số | Gợi ý sử dụng | Cách đọc |
| --- | --- | --- |
| **VolumeReadOps / VolumeWriteOps** | Tổng số thao tác đọc/ghi | Chia `Sum` theo giây của chu kỳ để ra IOPS quan sát được |
| **VolumeReadBytes / VolumeWriteBytes** | Tổng byte đọc/ghi | Chia `Sum` theo thời gian rồi chuyển sang MiB/s |
| **VolumeQueueLength** | Số request I/O đang chờ hoặc trong hàng đợi | Queue tăng lâu có thể cho thấy tắc nghẽn hoặc ứng dụng tạo tải vượt khả năng |
| **VolumeTotalReadTime / VolumeTotalWriteTime** | Tổng thời gian xử lý I/O theo metric hỗ trợ | Dùng kết hợp số operations để ước lượng latency trong điều kiện áp dụng |
| **BurstBalance** | Dung lượng credit còn lại cho loại volume áp dụng | Hữu ích cho gp2/st1/sc1 theo cách tính credits; gp3 không chạy theo burst credits |
| **VolumeIdleTime** | Khoảng thời gian volume nhàn rỗi | Giúp phân biệt load thấp với nghẽn thật |
| **VolumeStalledIOCheck / VolumeIOPSExceededCheck / VolumeThroughputExceededCheck** | Metric kiểm tra vận hành hoặc vượt giới hạn ở các nền tảng hỗ trợ | Không phải mọi loại volume/instance đều cung cấp; xác minh trước khi tạo alarm |

**Ví dụ tính throughput:** Trong 60 giây, `Sum(VolumeReadBytes)=6,291,456,000` byte. Throughput trung bình `≈100 MiB/s`. Nếu volume gp3 baseline 125 MiB/s và ứng dụng liên tục cần cao hơn, có thể xem xét tăng throughput đã provision — **sau khi** xác nhận instance còn headroom.

### Kiểm tra tại hệ điều hành

Linux có thể dùng:

~~~bash
lsblk
df -hT
iostat -xz 1
# Nếu có sysstat được cài:
# theo dõi await, util, r/s, w/s, rkB/s, wkB/s
~~~

**Lưu ý:** `iostat` đo tại tầng OS, CloudWatch đo ở tầng EBS; số liệu có thể khác do caching, cách gom requests và mốc thời gian. Đừng suy ra `%util=100` chắc chắn volume đã đạt mọi giới hạn trong tất cả môi trường.

Đối với database, đo thêm thời gian đọc/ghi/đợi I/O của engine và application p95/p99. Chỉ tăng IOPS nếu bottleneck thực sự nằm ở storage, thay vì CPU, lock contention, memory, network hoặc query plan.

## 14. Tính chi phí EBS đúng cách

Những khoản phí cần ước lượng:

1. **Provisioned storage:** dung lượng GiB/TiB của volume, theo loại và thời gian sử dụng; volume `available` không attach vẫn có thể tiếp tục tính phí.
2. **Provisioned IOPS/throughput:** đặc biệt với gp3 vượt baseline hoặc io1/io2, tùy đơn giá và ngưỡng.
3. **Snapshots:** dữ liệu snapshot lưu trữ theo loại/chu kỳ, copy liên Region/account, archive/retrieval nếu sử dụng.
4. **Fast Snapshot Restore/khởi tạo cấp phát:** nếu dùng tính năng bổ sung có tính phí.
5. **Hạ tầng liên quan:** EC2 EBS-optimized throughput, bandwidth, instance cost, vận hành backup/monitoring, CloudWatch log/metrics và các khoản truyền dữ liệu liên quan.

**Công thức cấu trúc cho gp3**, bỏ qua thuế/chiết khấu và những thành phần khác:

\[
C_{\text{gp3}} \approx
S_{\text{GiB}} P_{\text{GiB-tháng}} +
\max(0, I-3000)P_{\text{IOPS-tháng}} +
\max(0, T-125)P_{\text{MiB/s-tháng}}
\]

Trong đó `S` là capacity được cấp, `I` là IOPS provisioned, `T` là throughput provisioned. Các **đơn giá P** tùy Region/thời gian, không lấy một giá USD mặc định cho mọi môi trường.

### Ví dụ so sánh không dùng giá cố định

Giả sử cần **200 GiB, 3.000 IOPS, 125 MiB/s**:

- Với **gp3**, IOPS/throughput này nằm trong mức nền, nên phí EBS volume chủ yếu theo dung lượng provisioned.
- Với **gp2**, 200 GiB có baseline khoảng 600 IOPS; mức 3.000 chỉ có thể đến từ burst credits khi điều kiện cho phép. Một bài toán tải ổn định có thể yêu cầu tăng dung lượng gp2 đáng kể để đạt mức baseline, gây lãng phí.
- Với **io2**, mục tiêu 3.000 IOPS có thể đạt, nhưng chi phí và mức năng lực dự phòng có thể không cần cho workload này.
- Nếu dữ liệu chỉ là object lưu trữ dài hạn, xem xét S3 thay vì giữ volume provisioned liên tục.

**Thao tác tối ưu chi phí:** tìm volume nhàn rỗi hoặc unattached còn phí, snapshot cũ không có retention policy, gp2 có thể chuyển gp3, gp3 cấp IOPS/throughput vượt sử dụng, và khả năng chuyển dữ liệu lạnh sang object storage. Trước khi xóa bất kỳ volume/snapshot nào, kiểm tra quyền sở hữu, phụ thuộc và kế hoạch khôi phục.

Dùng **AWS Pricing Calculator**, **AWS Cost Explorer**, **AWS Budgets** và tags theo `application`, `environment`, `owner` để theo dõi.

## 15. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Kiểm tra trước |
| --- | --- | --- |
| Attach thất bại vì AZ | EC2 và volume khác Availability Zone | Đọc `describe-instances`, `describe-volumes`, so AZ thật |
| OS không thấy block device như `/dev/sdf` | Nitro NVMe đổi tên thiết bị | `lsblk`, đối chiếu NVMe serial/volume ID |
| Mount báo wrong filesystem hoặc no superblock | Volume chưa format, nhầm device, hỏng filesystem, snapshot khác OS | `file -s`, `blkid`, log kernel; tuyệt đối không format trước khi xác định dữ liệu |
| Volume báo 200 GiB nhưng filesystem vẫn 100 GiB | Chưa mở rộng partition/filesystem | `lsblk`, `df -hT`, layout LVM/partition, growpart/resize phù hợp |
| IOPS thấp hơn provision | EC2 EBS bandwidth/IOPS cap, queue depth, I/O size, initialization, app bottleneck | Metrics EC2/EBS, benchmark đúng, `iostat`, latency |
| gp2/thruput HDD chậm dần sau khi chạy dài | Burst credits giảm hoặc workload không phù hợp | `BurstBalance`, đo sustained I/O, đánh giá gp3/st1/io2 phù hợp |
| Volume từ snapshot đọc lần đầu chậm | Chưa fully initialized | Warm-up/FSR/provisioned initialization phù hợp |
| App báo I/O error | OS device error, volume state, connectivity tầng storage, filesystem hoặc kernel | CloudWatch, system logs, EC2 status, support/runbook |
| Snapshot completed nhưng DB restore lỗi | Snapshot không nhất quán ứng dụng hoặc thiếu volume/log liên quan | DB-aware backup, quiesce, restore test |
| Không chuyển được sang st1/sc1 làm root | st1/sc1 không làm boot volume | Giữ root trên gp3/SSD, dùng HDD cho data phù hợp |
| Chi phí tăng bất ngờ sau sửa gp3 | Provisioned IOPS/throughput vượt baseline | Kiểm tra `describe-volumes`, Cost Explorer và pricing theo Region |
| Không attach đồng thời vào nhiều EC2 | Chọn loại không hỗ trợ Multi-Attach, khác AZ, instance không đủ điều kiện | Kiểm tra io1/io2, Nitro, AZ, cấu hình cluster/filesystem |
| KMS AccessDenied | Role/key policy/grant không cho thao tác với encrypted volume/snapshot | IAM policy, key policy, grants, account/Region và CloudTrail |

### Trình tự điều tra gợi ý

~~~text
1. Xác nhận EC2, volume ID, AZ, loại volume, size, IOPS, throughput, encryption.
2. Xác nhận attach state và block device trong OS (đúng volume ID).
3. Xác nhận partition/filesystem/mount point, không vội format hoặc fsck khi app đang ghi.
4. Đo I/O thực: IOPS, MiB/s, latency, queue, CPU và EC2 EBS cap.
5. Đối chiếu loại volume, tải random/sequential, burst credits, snapshot initialization.
6. Kiểm tra application logs, KMS/IAM và các thành phần compute/network khác.
7. Đề xuất thay đổi nhỏ nhất, backup, thử lại dưới tải tương đương, giám sát.
8. Ghi bằng chứng và thử restore nếu có thay đổi ảnh hưởng dữ liệu.
~~~

## 16. Thiết kế kiến trúc có EBS qua Region/AZ, IAM và VPC

Một kiến trúc tham khảo cho ứng dụng trên EC2, dữ liệu giao dịch trên database được quản lý:

~~~mermaid
flowchart TB
    U[Người dùng] --> LB[Application Load Balancer]
    LB --> A[EC2 app AZ A]
    LB --> B[EC2 app AZ B]
    A --- VA[(EBS gp3 data/cache AZ A)]
    B --- VB[(EBS gp3 data/cache AZ B)]
    A --> DB[(RDS Multi-AZ)]
    B --> DB
    VA --> SA[EBS snapshot]
    VB --> SB[EBS snapshot]
    SA --> BK[AWS Backup / lifecycle]
    SB --> BK
    A --> CW[CloudWatch + CloudTrail]
    B --> CW
    DB --> CW
~~~

Trong sơ đồ:

- **EBS của mỗi EC2** có dữ liệu riêng cùng AZ; không coi hai volume `VA` và `VB` là một shared filesystem đồng bộ.
- **Dữ liệu nghiệp vụ chính** dùng RDS Multi-AZ theo yêu cầu quan hệ và HA; nếu ứng dụng bắt buộc tự vận hành database trên EC2, cần thiết kế DB replication/failover riêng.
- **IAM roles** của EC2/AWS Backup thực hiện thao tác API với quyền tối thiểu; **KMS** bảo vệ dữ liệu EBS đã mã hóa.
- **VPC, subnet, SG** kiểm soát đường đi của ứng dụng và database; việc attach EBS không thay thế phân quyền mạng.
- **Snapshots/lifecycle** giải quyết khôi phục và retention, còn **CloudWatch** giúp nhận diện bottleneck, CloudTrail hỗ trợ audit thay đổi.
- **Region/AZ** ảnh hưởng tới vị trí attach, chiến lược phục hồi AZ, việc copy snapshot và giá.

### EC2, ECS, EKS và Lambda khác nhau khi dùng EBS thế nào?

- **EC2:** attach EBS trực tiếp làm root/data volume.
- **ECS trên EC2:** dữ liệu persistent gắn vào host EC2 và được container sử dụng cần thiết kế lifecycle, placement, mount và quyền; không mặc định mỗi container có EBS volume riêng.
- **ECS với những tính năng EBS quản lý hỗ trợ:** có thể cấp EBS cho task theo khả năng dịch vụ hiện hành; phải kiểm tra giới hạn task, AZ và lifecycle.
- **EKS:** dùng **Amazon EBS CSI driver** và PersistentVolume/PersistentVolumeClaim cho block persistent storage; scheduler, AZ và access mode phải khớp với volume.
- **Lambda:** không attach một EBS volume như ổ đĩa EC2 thông thường. Nếu cần shared filesystem, khảo sát tích hợp **EFS** của Lambda; dữ liệu tạm dùng vùng `/tmp` theo cấu hình/giới hạn riêng.

Điểm chung: **Không ép dịch vụ tính toán vào một mô hình lưu trữ không được hỗ trợ**. Xem giới hạn tài nguyên, vùng, khả năng share, autoscaling và yêu cầu phục hồi trước khi chọn.

## 17. Checklist chọn và vận hành EBS

- [ ] Xác định workload cần **block device** thực sự; đã so EBS với EFS, S3, FSx hoặc instance store.
- [ ] Đã ghi dung lượng hiện tại, tăng trưởng, cách đọc/ghi, I/O size, IOPS, MiB/s, latency và queue depth.
- [ ] Chọn loại có lý do: gp3 cho nhu cầu phổ biến; io2 khi cần sustained IOPS/latency; st1/sc1 cho HDD tuần tự phù hợp.
- [ ] Không dùng st1/sc1 làm boot volume, không dùng EBS Multi-Attach như NFS shared file.
- [ ] EC2, volume và cách triển khai qua AZ tương thích; đã xem EBS bandwidth/IOPS giới hạn của instance.
- [ ] Cấp IOPS và throughput có tính đến điều kiện volume size, loại máy/Region và chi phí vượt baseline.
- [ ] Có quyền IAM theo nguyên tắc ít đặc quyền, mã hóa/KMS đúng yêu cầu và audit bằng CloudTrail.
- [ ] Đã kiểm tra `DeleteOnTermination` và quy trình detach/terminate an toàn.
- [ ] Có backup/snapshot theo RPO; thử restore và xác minh nhất quán database/ứng dụng.
- [ ] Có phương án ứng dụng phục hồi qua AZ/Region theo RTO; không hiểu snapshot là failover tự động.
- [ ] Đã cấu hình metric/log/alert về throughput, IOPS, latency, queue, trạng thái volume và lỗi ứng dụng.
- [ ] Có kế hoạch nâng dung lượng/filesystem theo đúng OS/LVM/partition và đã kiểm tra không thể shrink volume tại chỗ.
- [ ] Đã ước lượng phí volume, IOPS/throughput, snapshots/FSR và giám sát; gắn tag owner/environment.
- [ ] Có phương án thử nghiệm trên lab trước khi chỉnh storage production.

## 18. Bài tập áp dụng

### Bài tập 1 — Chọn ổ cho ba ứng dụng

Chọn loại EBS và lý giải cho ba trường hợp:

1. Web server EC2 có root disk 40 GiB, 500–1.500 IOPS, latency bình thường.
2. EC2 xử lý log 5 TiB, quét tuần tự nhiều giờ mỗi ngày, ít random I/O và không dùng volume làm boot.
3. Database giao dịch thực đo 70.000 IOPS ở workload phù hợp, tail latency rất nghiêm ngặt, EC2 Nitro đủ EBS bandwidth.

**Gợi ý:** (1) gp3; (2) đánh giá st1 với sustained throughput và credit balance, so gp3/S3; (3) đánh giá io2 Block Express và so sánh benchmark/chi phí với gp3 đã cấu hình thích hợp. Không có kết luận cuối nếu thiếu số đo và mục tiêu chi phí.

### Bài tập 2 — Vì sao tăng size nhưng không tăng được dữ liệu chứa?

Một `gp3` volume đã tăng từ 100 lên 200 GiB trong EC2 console, nhưng `df -h` vẫn hiện 100 GiB. Hãy:

1. Nêu sự khác biệt giữa block volume, partition và filesystem.
2. Kiểm tra bằng `lsblk`, `df -hT`, `blkid`.
3. Đề xuất bước tăng partition rồi filesystem đúng cho ext4 hoặc XFS, xét có LVM không.
4. Mô tả cách backup và đảm bảo không thao tác nhầm vào root/data device.

### Bài tập 3 — Tính hiệu năng và kiểm soát chi phí

Một workload cần 10.000 IOPS với kích thước trung bình 32 KiB. Tính throughput lý thuyết:

\[
10{,}000 \times 32 / 1{,}024 = 312.5\ \text{MiB/s}
\]

Thảo luận:

- gp3 có đủ giới hạn kỹ thuật không? Cần provision IOPS và throughput bao nhiêu để có margin?
- Volume size tối thiểu để cấp 10.000 IOPS gp3 theo tỉ lệ 500 IOPS/GiB là bao nhiêu? (**20 GiB**, nhưng dung lượng thật vẫn cần theo dữ liệu và tăng trưởng.)
- Nếu EC2 chỉ có EBS bandwidth 250 MiB/s thì tại sao thay gp3 từ 250 lên 500 MiB/s không chắc tăng tốc?
- Khi workload chuyển sang random I/O 4 KiB và yêu cầu p99 rất thấp, cách chọn có cần thay đổi không?

### Bài tập 4 — Khôi phục sau mất một AZ

Ứng dụng lưu dữ liệu chỉ trên một EBS volume trong AZ A. Snapshot được tạo mỗi 12 giờ. Doanh nghiệp yêu cầu **RTO 30 phút, RPO 10 phút**.

Hãy giải thích vì sao thiết kế hiện tại khó đáp ứng hai mục tiêu, rồi đề xuất:

- Cơ chế replication hoặc kiến trúc database Multi-AZ phù hợp, thay vì chỉ snapshot mỗi 12 giờ.
- Kế hoạch khôi phục volume mới từ snapshot sang AZ B khi cần.
- Kiểm thử restoration time, dữ liệu nhất quán và chuyển DNS/route/load balancer.
- Quyền IAM/KMS, giám sát và ước lượng chi phí duy trì.

## 19. Tổng kết

**EBS là block storage gắn với EC2 trong một AZ.** Điểm quyết định lựa chọn loại volume nằm ở **mẫu I/O**, **IOPS**, **throughput**, **latency**, **dung lượng**, **giới hạn của EC2** và **mục tiêu phục hồi/chi phí**.

Với đa số ứng dụng, `gp3` là điểm khởi đầu hợp lý nhờ hiệu năng nền và khả năng chỉnh performance tách khỏi capacity. `io2 Block Express` phục vụ workload đòi hỏi độ trễ thấp và sustained IOPS rất cao. `st1/sc1` phù hợp dữ liệu tuần tự khi HDD thực sự đáp ứng tải. `gp2/io1/standard` cần hiểu để vận hành, tối ưu hoặc chuyển đổi hệ thống cũ.

Chọn đúng EBS chỉ là một phần của hệ thống AWS an toàn và đáng tin cậy. Cần kết hợp **IAM/KMS, VPC, Region/AZ, snapshots/restore, CloudWatch và AWS Budgets**. Hãy đo workload thực, tính toàn bộ chi phí, kiểm thử phục hồi và ghi lại lý do chọn trước khi đưa vào production.

### Tài liệu AWS chính thức để tra cứu

- [Amazon EBS volumes](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volumes.html)
- [Amazon EBS volume types](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volume-types.html)
- [General Purpose SSD volumes: gp3/gp2](https://docs.aws.amazon.com/ebs/latest/userguide/general-purpose.html)
- [Provisioned IOPS SSD / io2 Block Express](https://docs.aws.amazon.com/ebs/latest/userguide/provisioned-iops.html)
- [Modify an EBS volume using Elastic Volumes](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-modify-volume.html)
- [Extend the file system after resizing an EBS volume](https://docs.aws.amazon.com/ebs/latest/userguide/recognize-expanded-volume-linux.html)
- [Amazon EBS snapshots](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-snapshots.html)
- [EBS Multi-Attach](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volumes-multi.html)
- [CloudWatch metrics for Amazon EBS](https://docs.aws.amazon.com/ebs/latest/userguide/using_cloudwatch_ebs.html)
- [Amazon EBS pricing](https://aws.amazon.com/ebs/pricing/)

Thông số giới hạn, đơn giá, API và tính năng tùy Region/instance có thể thay đổi. Khi thiết kế triển khai, đối chiếu tài liệu AWS mới nhất với tài khoản và Region thực tế.

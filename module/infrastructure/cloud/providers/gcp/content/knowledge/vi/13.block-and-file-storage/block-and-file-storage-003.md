# Hyperdisk và cấu hình IOPS, throughput

Khi một ứng dụng chạy trên Compute Engine bắt đầu xử lý nhiều giao dịch hoặc đọc dữ liệu với tốc độ cao, CPU và RAM không còn là hai yếu tố duy nhất quyết định hiệu năng. Một cơ sở dữ liệu có thể chậm vì đĩa không đáp ứng đủ số thao tác đọc/ghi mỗi giây; một hệ thống phân tích có thể chậm vì đường truyền dữ liệu từ đĩa không đủ lớn, dù số thao tác I/O không cao.

**Google Cloud Hyperdisk** là họ dịch vụ lưu trữ khối (block storage) hiệu năng cao dành cho các workload và máy ảo được hỗ trợ trên Compute Engine. Khác với việc chỉ tăng dung lượng đĩa để lấy thêm hiệu năng, nhiều loại Hyperdisk cho phép cấu hình **IOPS** và/hoặc **throughput** theo nhu cầu, trong những giới hạn của loại đĩa, dung lượng, machine type và khu vực triển khai.

Trong chương **Lưu trữ khối và tệp** của module **CLOUD_PROVIDERS_GCP**, bài học này nối kiến thức về Compute Engine, project, IAM, VPC, khả dụng và chi phí với việc lựa chọn đĩa, vận hành database, tự động hóa triển khai và quan sát hiệu năng. Nội dung tập trung vào cách **thiết kế, cấu hình và đánh giá Hyperdisk** bằng những ví dụ thực tế.

Sau bài học, bạn có thể:

1. Phân biệt Hyperdisk với Persistent Disk, Filestore và Cloud Storage theo mô hình truy cập.
2. Giải thích ba chỉ số **IOPS**, **throughput** và **latency**, cùng quan hệ của chúng với kích thước I/O và mức xử lý đồng thời.
3. Chọn loại Hyperdisk phù hợp với OLTP, phân tích dữ liệu, HPC hoặc những ứng dụng cần dự phòng theo zone.
4. Cấu hình và đọc giá trị `provisioned IOPS` / `provisioned throughput` bằng Google Cloud Console và `gcloud`.
5. Đo hiệu năng thực tế, phát hiện giới hạn từ VM và workload, và điều chỉnh cấu hình theo bằng chứng.
6. Lập kế hoạch chi phí, dữ liệu, snapshot/backup và xử lý lỗi khi tạo, gắn hoặc điều chỉnh Hyperdisk.

## 1. Hyperdisk là lưu trữ khối, không phải hệ thống tệp chia sẻ mặc định

Một volume Hyperdisk xuất hiện với VM được hỗ trợ như **thiết bị lưu trữ khối**. Hệ điều hành có thể nhận diện thiết bị, tạo partition, format thành filesystem hoặc đưa vào hệ thống quản lý dữ liệu như database. Ứng dụng làm việc thông qua filesystem hoặc trực tiếp với block device tùy cách triển khai.

~~~mermaid
flowchart LR
    APP["Ứng dụng / cơ sở dữ liệu"] --> OS["Hệ điều hành + filesystem<br/>hoặc truy cập block trực tiếp"]
    OS --> VM["Compute Engine VM"]
    VM --> HD["Hyperdisk volume<br/>dung lượng + IOPS + throughput"]
    HD -. "Giới hạn thực tế" .-> CAP["Machine type, size,<br/>đặc tính I/O, quota"]
~~~

### 1.1. Chọn đúng mô hình lưu trữ

| Lựa chọn Google Cloud | Mô hình truy cập | Nhu cầu phổ biến | Câu hỏi trước khi chọn |
| --- | --- | --- | --- |
| **Hyperdisk** | Lưu trữ khối được gắn với VM hỗ trợ; một số chế độ multi-attach theo từng loại đĩa | Database, tác vụ ngẫu nhiên có IOPS cao, dữ liệu đọc/ghi băng thông cao | VM có hỗ trợ loại Hyperdisk và mức hiệu năng mong muốn không? |
| **Persistent Disk** | Block storage dành cho Compute Engine | Boot/data disk phổ biến, khi hiệu năng/chi phí phù hợp | Hiệu năng phụ thuộc loại, kích thước đĩa và machine type ra sao? |
| **Filestore** | Dịch vụ file storage được quản lý, truy cập qua NFS theo cấu hình hỗ trợ | Nhiều client cùng dùng hệ thống tệp, đường dẫn thư mục chung | Có cần POSIX/file sharing và mô hình NFS không? |
| **Cloud Storage** | Object storage, truy cập qua API và các công cụ tương ứng | File upload, ảnh, dữ liệu lớn, backup, static assets | Ứng dụng làm việc với object hay đòi hỏi block device/filesystem? |

Một ứng dụng cần nhiều VM cùng truy cập **một thư mục qua NFS** nên cân nhắc Filestore. Không nên coi việc một số Hyperdisk hỗ trợ multi-attach là tương đương với hệ thống tệp dùng chung an toàn: filesystem/ứng dụng phải xử lý đồng bộ, khóa và tính nhất quán tương ứng.

### 1.2. Các loại Hyperdisk

Google Cloud cung cấp các dòng sau; **phạm vi hỗ trợ theo region, zone, machine series và cấu hình có thể thay đổi**.

| Loại | Điểm tối ưu | Đại lượng người dùng có thể provision | Workload tiêu biểu |
| --- | --- | --- | --- |
| **Hyperdisk Balanced** | Cân bằng giá, IOPS và băng thông cho nhiều ứng dụng | **IOPS và throughput** | Database tổng quát, ứng dụng doanh nghiệp, dịch vụ giao dịch |
| **Hyperdisk Balanced High Availability** | Dữ liệu được nhân bản trong hai zone cùng region theo cơ chế sản phẩm | **IOPS và throughput** | Ứng dụng quan trọng cần lớp lưu trữ có khả năng chịu sự cố zone |
| **Hyperdisk Extreme** | IOPS cao, độ trễ thấp theo thiết kế và cấu hình được hỗ trợ | **IOPS**; throughput được dẫn xuất từ IOPS, không đặt độc lập | Database lớn, SAP HANA, những hệ thống giao dịch yêu cầu IOPS cao |
| **Hyperdisk Throughput** | Lưu lượng đọc/ghi tuần tự lớn với mức IOPS vừa phải | **Throughput**; IOPS được dẫn xuất từ throughput | Xử lý dữ liệu dung lượng lớn, phân tích và tác vụ nhạy chi phí |
| **Hyperdisk ML** | Băng thông đọc rất lớn và mô hình dùng chung đọc khi hỗ trợ | **Throughput**; IOPS được dẫn xuất từ throughput | Dữ liệu machine learning, AI/HPC và công việc đọc phân tán |

**Không phải loại nào cũng cho phép chỉnh hai nút IOPS và throughput độc lập.** Ví dụ, việc truyền `--provisioned-iops` cho Hyperdisk Throughput hoặc Hyperdisk ML không phù hợp vì hiệu năng IOPS của các loại này được tính từ throughput. Ngược lại, Hyperdisk Extreme cho phép đặt IOPS mà không đặt throughput trực tiếp.

**Hyperdisk Balanced High Availability** có mô hình nhân bản hai zone trong một region; điều đó không đồng nghĩa tự triển khai ứng dụng hoặc database sang zone dự phòng. Cần kết hợp với kiến trúc VM, ứng dụng, cơ chế failover, RTO/RPO và kiểm thử thực tế. Các chế độ multi-writer/read-only attach cũng có giới hạn riêng; không bật chia sẻ đĩa chỉ vì nhìn thấy tùy chọn.

## 2. Ba đại lượng cần hiểu: IOPS, throughput và latency

### 2.1. IOPS là số thao tác I/O mỗi giây

**IOPS (Input/Output Operations Per Second)** đo số thao tác đọc hoặc ghi mà hệ thống hoàn thành trong một giây. Workload giao dịch thường thực hiện nhiều truy cập nhỏ, ngẫu nhiên; khi đó IOPS là một chỉ số quan trọng.

Ví dụ, database thực hiện 8.000 lượt đọc trang nhỏ và 4.000 lượt ghi mỗi giây có tổng khoảng **12.000 IOPS**. IOPS không cho biết mỗi thao tác chuyển bao nhiêu byte; 12.000 IOPS với block 4 KiB và 256 KiB có thể tạo lượng dữ liệu rất khác nhau.

### 2.2. Throughput là khối lượng dữ liệu được truyền mỗi giây

**Throughput** đo dữ liệu đọc/ghi qua một đơn vị thời gian, thường biểu diễn bằng **MiB/s** ở cấu hình đĩa Google Cloud. Trong khi đó, tài liệu và ứng dụng đôi khi dùng MB/s, GiB/s hoặc Gb/s. Cần thống nhất đơn vị trước khi so sánh:

- 1 MiB = 1.048.576 byte.
- 1 MB = 1.000.000 byte.
- 1 GiB = 1.024 MiB.
- Mb/s là **megabit mỗi giây**, khác MB/s và MiB/s.

Nếu biết kích thước I/O trung bình, ước lượng:

\[
\text{Throughput (MiB/s)} \approx
\frac{\text{IOPS}\times\text{Kích thước I/O trung bình (byte)}}{1.048.576}
\]

| Mẫu tải minh họa | IOPS | I/O trung bình | Throughput xấp xỉ |
| --- | ---: | ---: | ---: |
| Giao dịch đọc/ghi nhỏ | 12.000 | 4 KiB | 46,9 MiB/s |
| API lưu tệp kích thước vừa | 8.000 | 16 KiB | 125 MiB/s |
| Quét dữ liệu theo lô | 1.000 | 256 KiB | 250 MiB/s |
| Đọc tuần tự khối lớn | 2.000 | 1 MiB | 2.000 MiB/s |

Các giá trị chỉ minh họa quan hệ toán học, **không phải kết quả benchmark**. Một workload thực có thể kết hợp nhiều kích thước I/O, read/write xen kẽ, cache hits và bước tính toán.

### 2.3. Latency là thời gian hoàn thành một thao tác

**I/O latency** là thời gian từ khi một yêu cầu đọc/ghi được gửi cho tới khi hoàn tất theo điểm đo tương ứng. Ngay cả khi đạt IOPS trung bình cao, database vẫn có thể chậm do một số request có latency p95/p99 lớn.

Trong thiết kế và đo thử, cần ghi:

- **p50** để thấy độ trễ điển hình;
- **p95/p99** để phát hiện nhóm thao tác chậm;
- **read/write latency** riêng, thay vì chỉ số trung bình trộn lẫn;
- **queue depth / outstanding I/O** để biết ứng dụng có phát đủ yêu cầu đồng thời;
- **CPU, RAM, filesystem, page cache và transaction behavior** để phân biệt nút thắt đĩa với nút thắt khác.

Một ước lượng từ định luật Little ở trạng thái ổn định:

\[
\text{Số I/O đồng thời trung bình}\approx
\text{IOPS}\times\text{Latency trung bình (giây)}
\]

Ví dụ muốn đạt 20.000 IOPS ở latency trung bình 2 ms, workload cần cỡ **40 I/O đang xử lý đồng thời**, nếu mô hình hàng đợi và phép đo phù hợp. Đây là cách kiểm tra tải tạo đủ yêu cầu hay chưa, không phải lời hứa rằng tăng queue depth luôn làm hệ thống nhanh hơn. Queue quá sâu còn có thể làm p99 tăng.

### 2.4. Bốn trường hợp thường gặp

| Tín hiệu | Khả năng giải thích | Hướng kiểm tra |
| --- | --- | --- |
| IOPS chạm ngưỡng, MiB/s còn thấp | Nhiều I/O nhỏ hoặc ngẫu nhiên | Tăng IOPS nếu phù hợp, tối ưu truy vấn và số I/O |
| Throughput chạm ngưỡng, IOPS còn thấp | Các I/O lớn hoặc quét tuần tự | Xem throughput, đường đọc dữ liệu và máy hỗ trợ |
| Cả hai dưới mức provision nhưng p99 cao | Queue, CPU, filesystem, đồng bộ ghi hoặc giới hạn khác | Đo queue depth, CPU, loại tác vụ, giới hạn VM và latency |
| Đặt hiệu năng cao nhưng đo thấp | VM không đủ giới hạn, tải không đủ, cache, test chưa đúng | Đối chiếu machine type, kích thước I/O, phương pháp benchmark |

**Nguyên tắc:** không chỉ tăng IOPS khi người dùng báo ứng dụng chậm. Trước hết phải biết workload đang bị giới hạn bởi **số thao tác**, **khối lượng dữ liệu**, **thời gian phản hồi** hay một thành phần khác.

## 3. Hiểu provisioned performance và giới hạn thực tế

**Provisioned IOPS** và **provisioned throughput** là mức hiệu năng mục tiêu được cấu hình cho Hyperdisk, **không phải thông số đo được từ ứng dụng** và cũng không phải cam kết workload luôn đạt mức đó. Một volume được đặt 20.000 IOPS có thể chỉ thực hiện 800 IOPS nếu ứng dụng không phát thêm yêu cầu; cũng có thể không đạt mức đặt nếu VM hoặc dạng I/O không hỗ trợ.

~~~mermaid
flowchart TD
    W["Workload: I/O size,<br/>random/sequential, concurrency"] --> OBS["Hiệu năng đo được"]
    D["Hyperdisk: type, size,<br/>provisioned IOPS/throughput"] --> OBS
    VM["VM: machine series,<br/>vCPU, disk limits"] --> OBS
    G["Guest OS / filesystem,<br/>cache, CPU, scheduler"] --> OBS
    OBS --> ACT["Đánh giá latency,<br/>IOPS, MiB/s và chi phí"]
~~~

### 3.1. Những giới hạn cần kiểm tra trước khi đặt số

| Lớp giới hạn | Câu hỏi cần trả lời | Hậu quả nếu bỏ qua |
| --- | --- | --- |
| **Loại Hyperdisk** | Loại này cho phép đặt IOPS, throughput hay chỉ một trong hai? | Tạo/cập nhật đĩa bị từ chối hoặc kỳ vọng cấu hình sai. |
| **Dung lượng volume** | Với size đã chọn, khoảng IOPS/throughput hợp lệ là bao nhiêu? | Không thể provision mức quá cao so với kích thước. |
| **Mối quan hệ IOPS–throughput** | Cặp giá trị có đáp ứng công thức/giới hạn của loại đĩa không? | Cặp giá trị không hợp lệ dù từng số nhìn có vẻ nằm trong giới hạn tối đa. |
| **Machine series và machine type** | VM có hỗ trợ loại đĩa, access mode và hiệu năng yêu cầu không? | Có thể không gắn được đĩa hoặc hiệu năng bị chặn bởi giới hạn VM. |
| **Giới hạn cộng gộp của VM** | Có nhiều đĩa cùng chia sẻ giới hạn IOPS/throughput của VM không? | Tổng hiệu năng các đĩa không đạt tổng các mức provision riêng. |
| **Zone/region và quota** | Tài nguyên có hỗ trợ ở vị trí triển khai, quota/capacity có đủ không? | Tạo đĩa hoặc attach thất bại. |
| **Tải thực và hệ điều hành** | Block size, queue depth, filesystem, cache và CPU đang ở mức nào? | Đặt hiệu năng cao nhưng không dùng hết hoặc làm p99 tăng. |

**Ví dụ về giới hạn loại đĩa:** tài liệu Hyperdisk Balanced hiện hành nêu mức trần **160.000 IOPS và 2.400 MiB/s trên một volume**, nhưng số provision hợp lệ còn phụ thuộc dung lượng và quan hệ giữa hai đại lượng. Hyperdisk Extreme có giới hạn IOPS khác; Hyperdisk Throughput và ML dùng quy tắc provision dựa trên throughput. Những mức trần này không phải chỉ tiêu thực tế của mọi VM.

Với những machine type có khả năng tổng IOPS hoặc throughput lớn hơn trần một Hyperdisk Balanced riêng lẻ, có thể cần **nhiều volume** và workload đủ khả năng phân phối I/O để khai thác mức VM. Ngược lại, tạo nhiều volume trên một VM nhỏ không vượt được giới hạn cộng gộp của VM.

### 3.2. Mối quan hệ của IOPS và throughput với loại I/O

Trong tài liệu hiệu năng Hyperdisk, IOPS tối đa thường được đánh giá với kích thước I/O nhỏ, ví dụ **4 KiB**, còn throughput tối đa với kích thước lớn hơn, ví dụ từ **256 KiB**, tùy loại và trường hợp. Một workload không nên mặc định cùng lúc đạt cả trần IOPS và trần throughput khi dùng chung một cỡ I/O.

Một ước lượng hữu ích khi thiết kế:

\[
\text{Throughput quan sát} \lesssim
\min\left(
\text{giới hạn throughput đĩa},
\ \text{IOPS thực}\times\text{kích thước I/O trung bình},
\ \text{giới hạn VM}
\right)
\]

Trong biểu thức trên, tích IOPS × kích thước I/O phải được đổi sang cùng đơn vị với throughput. Đây là **mô hình kiểm tra nút thắt**, không thay thế phép đo: cache, overhead, read/write mix, tính song song và latency cũng ảnh hưởng.

**Đọc + ghi cùng chia sẻ giới hạn hiệu năng** theo cơ chế half-duplex của Hyperdisk. Ví dụ, giới hạn 20.000 IOPS không có nghĩa đồng thời nhận 20.000 read IOPS **và** 20.000 write IOPS. Cần tính tổng lưu lượng đọc/ghi theo đặc tính giới hạn của dịch vụ.

### 3.3. Ví dụ chọn cặp IOPS và throughput hợp lệ

Giả sử ứng dụng cần **6.000 IOPS** và **300 MiB/s**, dung lượng dữ liệu chỉ khoảng 70 GiB nhưng dành 100 GiB để tăng trưởng. Một **Hyperdisk Balanced 100 GiB**, với cặp provision 6.000 IOPS và 300 MiB/s, là ví dụ cấu hình nằm trong dải phổ biến mà tài liệu hỗ trợ; vẫn phải kiểm tra loại VM và zone.

Đối với Hyperdisk Balanced, công thức khoảng throughput hợp lệ theo mức IOPS `P` trong tài liệu hiện hành là:

- Tối thiểu: `MAX(140, P / 256)` MiB/s;
- Tối đa: `MIN(2400, P / 4)` MiB/s;
- Đồng thời cần thỏa giới hạn theo **dung lượng** và điều kiện hỗ trợ của dịch vụ.

Với `P = 6000`, khoảng throughput theo công thức trên là từ 140 đến 1.500 MiB/s. Giá trị **300 MiB/s** nằm trong khoảng ấy, nhưng việc đạt 300 MiB/s với workload chỉ gồm I/O 4 KiB sẽ cần số IOPS cao hơn đáng kể so với 6.000. Vì vậy **cấu hình hợp lệ** và **workload đạt kỳ vọng** là hai phép kiểm tra khác nhau.

Đừng đưa công thức này sang Hyperdisk Extreme, ML hoặc Throughput; mỗi loại có cơ chế và giới hạn riêng.

### 3.4. Baseline, hiệu năng provision thêm và chi phí

Một số loại Hyperdisk có **baseline performance** được tính trong cấu hình mặc định hoặc cơ chế định giá riêng. Nếu provision cao hơn mức được bao gồm, chi phí có thể tăng. Mức baseline, cách tính phí theo dung lượng/IOPS/throughput, giá region và các thay đổi sản phẩm cần được kiểm tra trên bảng giá chính thức.

Có thể hình dung mô hình chi phí:

\[
\text{Chi phí lưu trữ} \approx
\text{dung lượng tính phí}
+ \text{hiệu năng provision tính phí}
+ \text{snapshot/backup và dịch vụ liên quan}
\]

Không được nhân trực tiếp “IOPS × số giờ” rồi coi là phí của mọi loại Hyperdisk: đơn vị tính giá, giá trị miễn/bao gồm và cách áp dụng khác nhau. Cần dùng **Google Cloud Pricing Calculator** hoặc bảng giá chính thức cho tổ hợp loại đĩa, vùng, dung lượng và mức provision cụ thể.

**Quyết định kinh tế:** nếu workload chỉ tiêu thụ 2.000 IOPS thường xuyên nhưng provision 60.000 IOPS, bạn có thể trả phí cho khả năng hiếm khi dùng. Ngược lại, đặt sát mức trung bình có thể gây nghẽn vào giờ cao điểm. Hãy dùng p95/p99, lưu lượng peak và đợt thử tải để chọn một mức phù hợp rồi giám sát.

## 4. Chọn loại Hyperdisk theo đặc tính workload

### 4.1. Cơ sở dữ liệu giao dịch (OLTP)

Ứng dụng thương mại điện tử thực hiện nhiều thao tác đọc/ghi trang nhỏ, cập nhật chỉ mục và ghi transaction log. Nhóm cần đo **IOPS, latency và tốc độ log flush**, đồng thời theo dõi các truy vấn chậm.

Một điểm khởi đầu hợp lý có thể là **Hyperdisk Balanced** vì cho phép chỉnh hai đại lượng. Khi workload thực sự yêu cầu IOPS đặc biệt cao, cần xem xét **Hyperdisk Extreme** và machine type được hỗ trợ. Mua đĩa IOPS cao không sửa được truy vấn thiếu index, khóa giao dịch quá lâu hoặc CPU bị nghẽn.

### 4.2. Quét dữ liệu tuần tự và pipeline phân tích

Tác vụ đọc các tệp lớn theo lô có thể cần **MiB/s cao** nhưng số thao tác I/O vừa phải. Khi đó nên đánh giá Hyperdisk Throughput, đồng thời xem mức hiệu năng tương ứng với **size** và khả năng đọc song song của ứng dụng. Hyperdisk ML hướng tới các bài toán đọc băng thông cực lớn và những chế độ gắn cho nhiều VM đọc cùng dữ liệu được sản phẩm hỗ trợ.

Nếu pipeline làm việc chủ yếu với object và không cần block device, **Cloud Storage** có thể là mô hình lưu trữ phù hợp hơn. Nếu nhiều máy cùng thao tác trên thư mục chuẩn NFS, cân nhắc **Filestore**.

### 4.3. Dữ liệu quan trọng cần chịu lỗi zone

Khi nghiệp vụ yêu cầu lớp dữ liệu có khả năng chịu sự cố trong region, cần xem **Hyperdisk Balanced High Availability**, trong đó dữ liệu được nhân bản giữa hai zone theo mô hình của sản phẩm. Nhưng cần trả lời thêm:

- Instance nào sẽ tiếp tục chạy hoặc nhận vai trò sau sự cố?
- Filesystem/database có hỗ trợ attach/failover và cách xử lý dữ liệu đang ghi không?
- Phương án này đạt **RTO/RPO** nào khi kiểm thử thực tế?
- Nếu **cả region** bị lỗi, backup hoặc chiến lược DR nằm ở đâu?

Không suy rằng volume HA thay thế snapshot, backup nhất quán ứng dụng hoặc cơ chế phục hồi khỏi thao tác xóa nhầm. Sao chép dữ liệu có thể sao chép luôn thao tác sai.

### 4.4. Ma trận quyết định minh họa

| Đặc tính chính | Ứng viên cần kiểm tra | Bằng chứng nên thu thập |
| --- | --- | --- |
| OLTP cân bằng, số I/O nhỏ và tăng tải thất thường | Hyperdisk Balanced | IOPS peak, write latency, p99 và chi phí provision |
| Database giao dịch IOPS rất cao | Hyperdisk Extreme | IOPS thực, giới hạn machine series, database tuning |
| Quét/ghi tuần tự dung lượng lớn | Hyperdisk Throughput | MiB/s, I/O size lớn, nhu cầu capacity |
| AI/HPC đọc dữ liệu cực lớn, nhiều reader | Hyperdisk ML | Khả năng read-only attach, throughput, máy được hỗ trợ |
| Độ sẵn sàng dữ liệu theo hai zone trong một region | Hyperdisk Balanced High Availability | Cơ chế replica, failover, tính nhất quán và RTO/RPO |
| Nhiều máy cùng mở hệ thống tệp qua NFS | Filestore | Nhu cầu file sharing, latency mạng, quyền NFS |
| Lưu ảnh, backup hoặc dữ liệu dưới dạng object | Cloud Storage | API/object semantics, lớp lưu trữ và chi phí request |

Mọi lựa chọn cuối cùng đều phải kiểm tra **sản phẩm hỗ trợ trong zone/region**, machine type, quyền IAM, loại dữ liệu, backup, độ tin cậy và tổng chi phí của kiến trúc.

## 5. Thực hành cấu hình Hyperdisk Balanced bằng gcloud

Phần này minh họa quy trình **tạo một data disk mới**, xem mức provision và thay đổi IOPS/throughput. Các lệnh là ví dụ để người học chạy **trong project lab được phê duyệt**; việc đọc bài không tự tạo tài nguyên. Disk có thể tính phí theo thời gian tồn tại kể cả khi chưa gắn VM.

### 5.1. Điều kiện và an toàn trước khi tạo

Cần chuẩn bị:

- Project có Cloud Billing account hoạt động và tài khoản có quyền phù hợp với Compute Engine Disks API.
- Một zone có hỗ trợ **Hyperdisk Balanced** và machine type được hỗ trợ nếu định gắn disk vào VM.
- Tên disk chưa được dùng trong zone, quota/capacity đủ cho dung lượng và mức provision.
- Workload/dữ liệu lab riêng; không dùng disk production để format hoặc benchmark ghi.
- Ngân sách được duyệt và kế hoạch xóa disk khi hoàn tất.

Những quyền thường liên quan gồm tạo/xem/cập nhật/xóa Compute Engine disk, quyền gắn disk vào instance và quyền quản lý VM nếu thực hiện attach. Chỉ cấp quyền IAM cần cho công việc. Với disk có CMEK, còn cần kiểm tra quyền và chính sách khóa mã hóa tương ứng.

### 5.2. Chọn project và zone

Chạy trong Bash hoặc Cloud Shell:

~~~bash
export PROJECT_ID="YOUR_LAB_PROJECT_ID"
export ZONE="YOUR_SUPPORTED_ZONE"
export DISK_NAME="hd-balanced-lab"

gcloud config set project "$PROJECT_ID"
gcloud config get-value project

# Chỉ đọc: kiểm tra loại disk hiện diện tại zone dự định
gcloud compute disk-types list \
  --zones="$ZONE" \
  --filter="name~hyperdisk"
~~~

Hãy thay các placeholder bằng project và zone đã xác minh. **Không** giả định mọi zone đều hỗ trợ mọi loại Hyperdisk hoặc mọi machine type. Nếu chưa có Compute Engine API, việc bật API phải theo quy trình và quyền của project lab.

### 5.3. Tạo Hyperdisk Balanced với mức hiệu năng minh họa

~~~bash
gcloud compute disks create "$DISK_NAME" \
  --zone="$ZONE" \
  --type=hyperdisk-balanced \
  --size=100GB \
  --provisioned-iops=6000 \
  --provisioned-throughput=300
~~~

Thông số:

| Tham số | Ý nghĩa |
| --- | --- |
| `--type=hyperdisk-balanced` | Chọn loại block volume cân bằng. |
| `--size=100GB` | Dung lượng data disk; đơn vị được gcloud diễn giải theo quy tắc disk size của Compute Engine. |
| `--provisioned-iops=6000` | Mức IOPS mục tiêu của volume. |
| `--provisioned-throughput=300` | Mức throughput mục tiêu tính bằng MiB/s. |
| `--zone` | Vị trí của **zonal** disk; VM gắn disk thường cần ở cùng zone, theo các điều kiện tương thích. |

Đối với Hyperdisk Balanced có kích thước do người dùng chỉ định, tài liệu xử lý lỗi hiện hành yêu cầu cung cấp **cả hai mức provision IOPS và throughput**. Ví dụ này khai báo đầy đủ để tránh lỗi khi chỉ định custom size nhưng bỏ một thông số.

**Lưu ý:** công cụ xác nhận cấu hình hợp lệ khi tạo disk chỉ chứng minh điều kiện sản phẩm/quota; nó chưa chứng minh VM hoặc ứng dụng sẽ đạt hiệu năng mong muốn.

### 5.4. Đọc lại dung lượng và mức hiệu năng đã provision

~~~bash
gcloud compute disks describe "$DISK_NAME" \
  --zone="$ZONE" \
  --format="yaml(name,type,sizeGb,provisionedIops,provisionedThroughput,status,users)"
~~~

Những trường cần đọc:

- `type`: loại disk, ví dụ Hyperdisk Balanced.
- `sizeGb`: dung lượng được cấu hình.
- `provisionedIops`: mức IOPS đã provision, **khác** số IOPS đang sử dụng.
- `provisionedThroughput`: mức throughput đã provision, **khác** throughput đang đo.
- `users`: những instance đang sử dụng disk theo thông tin được trả về, nếu có.

Nếu chưa attach vào VM, không có kết quả benchmark workload để so sánh. Hãy lưu lại mô tả disk như một phần bằng chứng cấu hình trước khi thay đổi.

### 5.5. Điều chỉnh hiệu năng mà không đổi dung lượng

Giả sử sau đo kiểm, nhóm quyết định tăng từ **6.000 lên 8.000 IOPS** và **300 lên 400 MiB/s**, trong phạm vi loại disk/dung lượng hỗ trợ:

~~~bash
gcloud compute disks update "$DISK_NAME" \
  --zone="$ZONE" \
  --provisioned-iops=8000 \
  --provisioned-throughput=400

gcloud compute disks describe "$DISK_NAME" \
  --zone="$ZONE" \
  --format="yaml(name,sizeGb,provisionedIops,provisionedThroughput)"
~~~

Hyperdisk hỗ trợ thay đổi mức provision trong nhiều trường hợp mà **không cần tăng dung lượng** và có thể thực hiện khi đang sử dụng tùy điều kiện sản phẩm. Tuy nhiên:

1. **Cooldown:** tài liệu hiện hành quy định đổi IOPS/throughput của đa số Hyperdisk **không thường xuyên hơn một lần trong 4 giờ** cho mỗi mức cần theo dõi; Hyperdisk ML dùng khoảng **6 giờ** với throughput. Với Balanced/Balanced HA, IOPS và throughput có thời gian chờ riêng.
2. **Thời gian có hiệu lực:** điều chỉnh thông thường có thể cần **tới khoảng 15 phút** để có hiệu lực; một số chế độ và Hyperdisk ML có thời gian khác. Không coi phản hồi CLI thành công là hiệu năng đã đổi ngay lập tức.
3. **Ràng buộc cấu hình:** không thể đặt số vượt giới hạn theo loại đĩa, dung lượng hay mối quan hệ IOPS/throughput; quota và chính sách cũng có thể chặn.
4. **Tác động chi phí:** provision thêm hiệu năng có thể làm hóa đơn tăng, kể cả khi ứng dụng chưa sử dụng hết.
5. **Phục hồi sau thay đổi:** lưu mức cũ, dữ liệu đo và người phê duyệt; nếu cần giảm mức provision, đối chiếu cooldown và thử lại trong khoảng tải đại diện.

Không nên chạy nhiều lệnh `update` liên tiếp để “thử đến khi đạt” nếu sản phẩm có cooldown. Hãy tính khoảng hợp lệ trước, chọn mức được review rồi đo sau khi thay đổi có hiệu lực.

### 5.6. Vì sao không dùng cùng bộ flag cho mọi Hyperdisk?

| Loại | Lệnh tạo cần quan tâm | Điều không được giả định |
| --- | --- | --- |
| Hyperdisk Balanced | `--type=hyperdisk-balanced`, size, IOPS, throughput | Mọi cặp IOPS/throughput đều hợp lệ. |
| Hyperdisk Extreme | Size và `--provisioned-iops` | Throughput là thông số provision độc lập. |
| Hyperdisk Throughput | Size và `--provisioned-throughput` | Có thể đặt `--provisioned-iops` trực tiếp. |
| Hyperdisk ML | Size và `--provisioned-throughput`, access mode phù hợp | IOPS là nút điều chỉnh trực tiếp hoặc có thể gắn read-write cho mọi chế độ. |
| Hyperdisk Balanced High Availability | Vị trí regional, cấu hình HA và hiệu năng theo sản phẩm | Có thể tạo/gắn như disk zonal thông thường bằng cách thay tên type. |

Đặc biệt, Hyperdisk Balanced High Availability là lựa chọn có phạm vi **regional** theo mô hình hai zone; khi tạo và quản lý phải dùng lệnh/tài nguyên phù hợp cho **regional disk**, thay vì thay thế tùy ý `--zone` trong ví dụ zonal.

## 6. Gắn Hyperdisk vào VM và kiểm tra từ hệ điều hành

Volume được tạo xong mới chỉ là tài nguyên block storage. Để ứng dụng dùng được, cần gắn nó vào **Compute Engine VM tương thích**, sau đó chuẩn bị filesystem hoặc cách truy cập block khác.

### 6.1. Chỉ thực hiện với VM lab được xác minh

~~~bash
export VM_NAME="YOUR_COMPATIBLE_LAB_VM"

# Chỉ đọc: xem máy, zone và các disk đã gắn
gcloud compute instances describe "$VM_NAME" \
  --zone="$ZONE" \
  --format="yaml(name,machineType,disks)"

# Thao tác ghi: gắn data disk do lab tạo
gcloud compute instances attach-disk "$VM_NAME" \
  --zone="$ZONE" \
  --disk="$DISK_NAME" \
  --device-name=hd-balanced-lab
~~~

Trước khi attach, phải xác nhận VM dùng **machine series hỗ trợ loại Hyperdisk** và không đang giữ một disk cùng tên hoặc khác zone. Một số chế độ attach/multi-writer chỉ hỗ trợ các loại disk và cấu hình nhất định; ví dụ trên hướng tới **data disk thông thường cho một VM**.

### 6.2. Phát hiện disk trong Linux và bảo vệ dữ liệu

Trên **VM Linux lab**, đọc trạng thái:

~~~bash
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS
ls -l /dev/disk/by-id/google-hd-balanced-lab
sudo blkid /dev/disk/by-id/google-hd-balanced-lab || true
~~~

Nếu đây là **volume vừa tạo hoàn toàn trống**, người vận hành có thể khởi tạo filesystem theo quy trình hệ điều hành. Trước khi format, bắt buộc:

- Đối chiếu serial/device name với disk vừa tạo trên Console/gcloud.
- Xác nhận đường dẫn không phải boot disk và không chứa partition/filesystem/dữ liệu cần giữ.
- Có bản sao lưu thích hợp nếu có bất kỳ nghi ngờ nào về dữ liệu.

Ví dụ **chỉ dành cho volume mới, trống**:

~~~bash
# CẢNH BÁO: định dạng sẽ xóa cấu trúc dữ liệu hiện có của thiết bị
sudo mkfs.ext4 /dev/disk/by-id/google-hd-balanced-lab

sudo mkdir -p /mnt/hyperdisk-lab
sudo mount /dev/disk/by-id/google-hd-balanced-lab /mnt/hyperdisk-lab
df -h /mnt/hyperdisk-lab
~~~

Không chạy `mkfs` trên disk production, disk có dữ liệu hoặc thiết bị không xác minh được. Sau khi mount, quyền sở hữu thư mục và cấu hình mount bền vững qua reboot (ví dụ `/etc/fstab` dựa trên UUID) phải được cấu hình theo chuẩn của hệ điều hành và ứng dụng.

### 6.3. Dung lượng disk, filesystem và hiệu năng là ba khía cạnh khác nhau

Các thao tác không tương đương:

- **Tăng dung lượng Hyperdisk:** thay thuộc tính size của volume trong phạm vi cho phép; filesystem/partition trong guest OS có thể cần mở rộng riêng.
- **Tăng provisioned IOPS/throughput:** thay cấu hình hiệu năng, không tự tăng dung lượng đã mount.
- **Thay machine type:** có thể thay giới hạn I/O tổng của VM hoặc điều kiện hỗ trợ disk; cần xem quy trình stop/start/compatibility.

Không coi `df -h` là bằng chứng về IOPS hoặc throughput: lệnh đó hiển thị dung lượng filesystem. Tương tự, provisioning thành công không bảo đảm workload đạt mức khi filesystem hoặc VM bị giới hạn.

## 7. Benchmark: chứng minh ứng dụng sử dụng được hiệu năng đã provision

Một lần chạy `fio` có thể giúp hiểu giới hạn I/O, nhưng phải tách **benchmark tổng hợp** khỏi **độ trễ thực của ứng dụng**. Fio cho phép thử nhiều kích thước I/O, random/sequential, read/write mix và queue depth. Việc đạt số đẹp trong thử nghiệm tuần tự không bảo đảm một database với truy vấn nhỏ cũng đạt cùng throughput.

### 7.1. Nguyên tắc an toàn khi thử I/O

**Chỉ benchmark trên data disk lab hoặc tệp thử nghiệm dành riêng.** Không dùng lệnh ghi vào raw device của đĩa đang chứa dữ liệu; không chọn nhầm boot disk. Các ví dụ bên dưới sử dụng **một tệp kiểm thử** trong filesystem đã mount trên Hyperdisk lab.

Trước khi chạy:

1. Xác nhận VM, machine type, disk type, size, IOPS và throughput đã provision.
2. Xác nhận đường dẫn `/mnt/hyperdisk-lab` nằm trên đúng disk test bằng `df -h`, `lsblk` và tên thiết bị.
3. Đảm bảo còn đủ dung lượng trống cho tệp tạm (ví dụ 2 GiB) và không chứa dữ liệu nghiệp vụ.
4. Chọn giờ thử không ảnh hưởng người dùng khác; benchmark có thể làm tăng I/O latency của workload cùng VM/disk.
5. Tính phí VM/disk và cài công cụ nếu cần mạng Internet/NAT; trên Linux Debian/Ubuntu có thể dùng `fio` từ package repository.

### 7.2. Chuẩn bị tệp kiểm thử an toàn

**Trên VM lab**, sau khi xác minh disk đã mount và quyền ghi đúng:

~~~bash
sudo apt-get update
sudo apt-get install -y fio

# Chỉ áp dụng cho mount point vừa tạo dành riêng cho lab
sudo chown "$(id -u)":"$(id -g)" /mnt/hyperdisk-lab

# Ghi dữ liệu mẫu vào MỘT tệp thử, không ghi trực tiếp raw block device
fio --name=prepare \
  --filename=/mnt/hyperdisk-lab/fio-scratch.bin \
  --size=2G \
  --rw=write \
  --bs=1M \
  --ioengine=libaio \
  --iodepth=8 \
  --direct=1 \
  --group_reporting
~~~

Lệnh chuẩn bị **ghi đè tệp có tên `fio-scratch.bin`** nếu đã tồn tại; hãy bảo đảm đường dẫn này không được ứng dụng dùng và không chứa dữ liệu cần giữ. Việc đặt tệp riêng hạn chế phạm vi ảnh hưởng hơn benchmark ghi trực tiếp vào thiết bị block.

### 7.3. Đo IOPS bằng 4 KiB random read

~~~bash
fio --name=randread-4k \
  --filename=/mnt/hyperdisk-lab/fio-scratch.bin \
  --size=2G \
  --rw=randread \
  --bs=4k \
  --ioengine=libaio \
  --iodepth=32 \
  --direct=1 \
  --readonly \
  --time_based \
  --runtime=60 \
  --group_reporting
~~~

Các tùy chọn đáng chú ý:

- `--rw=randread` và `--bs=4k` mô phỏng nhiều lượt đọc ngẫu nhiên nhỏ.
- `--iodepth=32` cho phép có nhiều yêu cầu đang xử lý; tăng queue depth có thể tăng IOPS đến một mức, nhưng cũng ảnh hưởng latency.
- `--direct=1` cố gắng bỏ qua page cache thường gặp để phép đo gần hơn với đường đĩa; filesystem, kernel và môi trường vẫn có thể tác động.
- `--readonly` giảm khả năng vô tình ghi trong bài thử đọc.
- `--time_based --runtime=60` đo trong khoảng 60 giây thay vì chỉ hoàn tất một lượng dữ liệu cố định.

Ghi lại **IOPS**, **BW** (MiB/s), **lat/clat**, các phân vị latency và mức CPU. Nên chạy lặp lại và so sánh trong điều kiện tương tự.

### 7.4. Đo throughput bằng đọc tuần tự 256 KiB

~~~bash
fio --name=seqread-256k \
  --filename=/mnt/hyperdisk-lab/fio-scratch.bin \
  --size=2G \
  --rw=read \
  --bs=256k \
  --ioengine=libaio \
  --iodepth=16 \
  --direct=1 \
  --readonly \
  --time_based \
  --runtime=60 \
  --group_reporting
~~~

Benchmark này nhắm tới **MiB/s** và độ trễ của những lượt đọc lớn. Không so sánh IOPS của profile 256 KiB với IOPS tối đa được mô tả cho profile 4 KiB như thể chúng là cùng một bài thử.

### 7.5. Đo tải hỗn hợp nếu phù hợp

Một dịch vụ thực có thể đọc và ghi đồng thời. Nếu cần kiểm tra tải hỗn hợp, chỉ chạy với **tệp thử riêng**:

~~~bash
# GHI lên tệp thử nghiệm; không chạy trên dữ liệu production
fio --name=mixed-4k \
  --filename=/mnt/hyperdisk-lab/fio-scratch.bin \
  --size=2G \
  --rw=randrw \
  --rwmixread=70 \
  --bs=4k \
  --ioengine=libaio \
  --iodepth=32 \
  --direct=1 \
  --time_based \
  --runtime=60 \
  --group_reporting
~~~

Tỷ lệ đọc 70% chỉ minh họa; nên dùng tỷ lệ thu được từ hệ thống thật. Workload database còn có journal, fsync, transaction log, cache, đồng bộ ghi, khóa và các yếu tố khác, nên **fio chỉ là một trong các phép đo**.

### 7.6. Hiểu kết quả, không chỉ nhìn số tối đa

| Kết quả đo | Câu hỏi cần kiểm tra | Hành động khả dĩ |
| --- | --- | --- |
| IOPS gần mức provision, p99 bắt đầu tăng | Có bị giới hạn theo số thao tác? | So sánh nhu cầu peak, tối ưu query, cân nhắc tăng IOPS |
| MiB/s gần mức provision, IOPS còn dư | Có bị giới hạn băng thông? | Điều chỉnh throughput nếu loại đĩa hỗ trợ |
| IOPS và MiB/s thấp, CPU cao | Ứng dụng hay quá trình benchmark có dùng hết CPU? | Đo CPU, vCPU, thread và machine type |
| Hiệu năng thấp trên nhiều disk cùng VM | Có bị giới hạn tổng IOPS/throughput của máy? | Kiểm tra machine limit và tải tổng |
| Random read tốt nhưng ứng dụng vẫn chậm | Database lock, network, fsync, truy vấn hoặc cache? | Đo end-to-end và các thành phần khác |
| Hiệu năng dao động sau thay đổi provision | Cấu hình mới đã có hiệu lực chưa? Tải có tương đương không? | Đối chiếu cooldown/propagation, chạy lại theo cùng profile |

Sau khi thử, có thể xóa **chỉ tệp benchmark** của lab:

~~~bash
rm -- /mnt/hyperdisk-lab/fio-scratch.bin
~~~

Không dùng dấu `*` hay lệnh dọn toàn bộ mount point nếu trong đó có dữ liệu khác. Với dữ liệu nhạy cảm, xóa file thông thường không phải cơ chế xóa an toàn bảo đảm loại bỏ tất cả bản sao.

## 8. Quan sát hiệu năng và điều chỉnh trên môi trường thật

### 8.1. Đo cả lớp đĩa và lớp ứng dụng

Khi đưa Hyperdisk vào production, xây dashboard có thể giải thích:

- **IOPS thực tế:** tổng read/write ops, riêng giờ peak và p95 theo thời gian.
- **Throughput thực tế:** đọc/ghi MiB/s; có bị chạm mức provision không.
- **Latency:** latency I/O từ guest OS và latency truy vấn/nghiệp vụ có liên quan.
- **Queue depth / pending I/O:** có nhiều yêu cầu chờ đĩa không; workload có phát đủ yêu cầu để dùng mức provision không.
- **Machine utilization:** CPU, memory, thread pool, phần tài nguyên khác có tạo giới hạn.
- **Cấu hình disk:** dung lượng, IOPS, throughput, loại đĩa, thời điểm thay đổi provision và instance đang gắn.
- **Chi phí:** chi phí tính theo loại Hyperdisk, size, provisioned performance, snapshot và dịch vụ liên quan.

Cloud Monitoring và công cụ hệ điều hành có thể cung cấp các metric từ những nguồn khác nhau. **Không nên đánh đồng số liệu disk read/write ở VM với dữ liệu hoàn toàn đi tới Hyperdisk** vì cache, tầng filesystem và cách lấy mẫu có thể làm các phép đo khác biệt.

### 8.2. Quy trình điều chỉnh dựa trên bằng chứng

~~~mermaid
flowchart TD
    S["Đo workload, SLO<br/>IOPS, throughput, latency"] --> B{"Nút thắt thật nằm ở đâu?"}
    B -->|Đĩa / volume| D["Kiểm tra giới hạn loại disk,<br/>size và mức provision"]
    B -->|VM / ứng dụng| A["Tối ưu CPU, concurrency,<br/>query, filesystem hoặc VM"]
    D --> V{"Machine type có<br/>đủ giới hạn?"}
    V -->|Không| M["Chọn VM phù hợp<br/>theo khả năng và chi phí"]
    V -->|Có| P["Thử mức provision mới<br/>trong dải hỗ trợ"]
    P --> R["Đợi thay đổi có hiệu lực,<br/>đo lại trong cùng điều kiện"]
    M --> R
    A --> R
    R --> C{"Đạt SLO và ngân sách?"}
    C -->|Chưa| S
    C -->|Có| E["Lưu quyết định,<br/>cảnh báo và kiểm tra định kỳ"]
~~~

Với các mức provision thay đổi được khi volume còn sử dụng, vẫn cần lập kế hoạch: tăng hiệu năng có thể làm chi phí cao hơn; giảm quá mạnh có thể gây tăng latency. Thay machine type, migrate dữ liệu hoặc thay loại disk còn có rủi ro gián đoạn, tính tương thích và rollback.

### 8.3. Lưu bản ghi quyết định cấu hình

Một bản ghi minh họa:

~~~yaml
workload: order-db
environment: production
storage:
  product: hyperdisk-balanced
  size_gib: 100
  provisioned_iops: 6000
  provisioned_throughput_mib_per_s: 300
requirements:
  peak_read_write_iops: 4500
  p99_io_latency_ms: "<nguong SLO duoc duyet>"
  backup_rpo: "<muc da duoc duyet>"
evidence:
  - "Benchmark doc ghi 4 KiB theo tai tuong tu production"
  - "IOPS, MiB/s, latency p95/p99 va quota VM"
  - "So sanh chi phi truoc va sau thay doi"
review_after: "<ngay review tiep theo>"
owner: "<nhom phu trach>"
~~~

Các giá trị trong dấu ngoặc là chỗ điền, không phải YAML triển khai trực tiếp. Ghi rõ kết quả đo có liên quan đến **đúng machine type và zone** để không tái sử dụng một mức provision từ VM khác một cách thiếu căn cứ.

## 9. Khả dụng, bảo vệ dữ liệu và quyền truy cập

### 9.1. Hyperdisk hiệu năng cao không thay thế backup

IOPS và throughput trả lời câu hỏi *đọc/ghi nhanh đến mức nào*, còn **backup, replication và khôi phục** trả lời câu hỏi *có phục hồi được khi dữ liệu hỏng hoặc hạ tầng ngừng hoạt động không*.

| Rủi ro | Công cụ hoặc biện pháp phù hợp cần cân nhắc | Giới hạn |
| --- | --- | --- |
| Ứng dụng xóa nhầm bảng, ghi sai dữ liệu | Snapshot, database backup, point-in-time recovery nếu sản phẩm hỗ trợ | Replica có thể sao chép cả thao tác sai. |
| Một zone ngừng hoạt động | Hyperdisk Balanced High Availability và kiến trúc VM/failover phù hợp | Zonal Hyperdisk Balanced thông thường không tự trở thành regional disk. |
| Cả region gián đoạn | Kế hoạch DR ở region khác, replication bất đồng bộ nếu loại disk hỗ trợ, backup/restore | RPO/RTO phụ thuộc cơ chế nhân bản, thời điểm sync và khả năng chuyển workload. |
| Hỏng filesystem hoặc lỗi ứng dụng | Backup nhất quán ứng dụng, kiểm tra restore, quy trình sửa lỗi được phê duyệt | Snapshot tại một thời điểm chưa chắc nhất quán ở mức giao dịch. |
| Danh tính hoặc khóa mã hóa bị lộ | IAM tối thiểu, Secret Manager, Cloud KMS/CMEK khi phù hợp | Mã hóa không thay thế kiểm soát ứng dụng và khả năng phục hồi. |

**Snapshot Hyperdisk** có thể phục vụ bảo vệ dữ liệu tại một thời điểm. Với database đang ghi, cần quan tâm đến **application-consistent snapshot**: tài liệu Google Cloud khuyến nghị phối hợp tạm dừng/quiesce ứng dụng hoặc filesystem khi cần nhất quán ứng dụng trên Hyperdisk. Việc chỉ bấm chụp snapshot lúc database đang chạy không mặc nhiên bảo đảm có thể khôi phục mọi giao dịch một cách nhất quán.

Nên thử **restore** định kỳ, xác minh tính toàn vẹn dữ liệu và đo **RPO/RTO thực tế**. Một backup chưa từng phục hồi thành công không đủ bằng chứng cho mục tiêu DR.

### 9.2. Sự khác nhau giữa zonal disk và Hyperdisk Balanced High Availability

~~~mermaid
flowchart TB
    subgraph Z["Zonal Hyperdisk Balanced"]
      VM1["VM - zone A"] --> D1["Volume tại zone A"]
    end
    subgraph HA["Hyperdisk Balanced High Availability - một region"]
      VM2["VM hoạt động ở zone A"] --> RD["Regional volume logic"]
      RD --> RA["Replica zone A"]
      RD --> RB["Replica zone B"]
      STANDBY["VM dự phòng zone B"] -. "Failover theo thiết kế" .-> RD
    end
~~~

Hyperdisk Balanced High Availability **nhân bản đồng bộ** sang hai zone trong region theo điều kiện vận hành. Những chế độ trạng thái replica (như đang đồng bộ hoặc suy giảm) và các giới hạn phục hồi cần được giám sát. Nếu một replica gặp lỗi, không nên khẳng định mọi thời điểm đều còn RPO bằng 0 mà không xét **trạng thái replica thực tế**.

Muốn ứng dụng hoạt động sau khi zone lỗi, cần thiết kế:

1. VM hoặc nhóm instance có thể chạy tại zone dự phòng;
2. Cơ chế phát hiện lỗi, chuyển dịch vụ và attach volume theo trạng thái được hỗ trợ;
3. Mạng, IAM, image, quota và secret tại điểm phục hồi;
4. Khôi phục database/filesystem và xác minh dữ liệu;
5. Chuyển traffic, giám sát SLO, diễn tập failover và failback.

**Multi-writer không đồng nghĩa multi-reader file sharing an toàn.** Khi nhiều VM cùng ghi một block volume, phải có filesystem phân cụm hoặc phần mềm điều phối phù hợp. Việc mount cùng một filesystem thông thường với quyền ghi từ nhiều VM mà không có cơ chế khóa/nhất quán có thể làm hỏng dữ liệu.

### 9.3. Mã hóa, IAM và dữ liệu nhạy cảm

Hyperdisk thuộc hạ tầng lưu trữ được Google Cloud quản lý; khi tổ chức cần kiểm soát khóa, có thể cân nhắc **Customer-Managed Encryption Keys (CMEK)** theo khả năng hỗ trợ loại volume và cấu hình. Quy trình cần tính tới quyền Cloud KMS, vòng đời khóa, khả năng restore và việc vô hiệu hóa/xóa khóa ảnh hưởng tới khả năng đọc dữ liệu.

Quản lý quyền theo nguyên tắc:

- Người **đọc metric** không nhất thiết được quyền xóa disk.
- Người **điều chỉnh provisioned IOPS/throughput** cần quyền thay đổi cấu hình disk, quy trình phê duyệt chi phí và giám sát.
- Người **gắn disk vào VM** có thể gián tiếp cho phần mềm trên VM truy cập dữ liệu; do đó cần kiểm soát cả danh tính VM, quyền OS và đường attach.
- Người **quản lý snapshot/backup** cần quyền phù hợp và bảo vệ thông tin nhạy cảm trong bản sao.
- Người vận hành **production** phải xét ràng buộc tổ chức, location của dữ liệu, log và backup trước khi chuyển disk hoặc tạo bản sao.

Một block disk có mã hóa không tự bảo đảm an toàn dữ liệu khi ứng dụng dùng tài khoản database có đặc quyền quá rộng hoặc VM bị xâm nhập.

## 10. Xử lý lỗi thường gặp khi tạo, gắn và tối ưu Hyperdisk

| Hiện tượng | Nguyên nhân khả dĩ | Cách xác minh |
| --- | --- | --- |
| Lệnh tạo trả lỗi về disk type hoặc vị trí | Zone không hỗ trợ loại Hyperdisk hoặc cấu hình đang chọn | Xem danh sách disk type/location hiện hành; kiểm tra đúng project và zone. |
| Lệnh tạo báo giá trị provision không hợp lệ | IOPS/throughput nằm ngoài dải theo size, loại disk hoặc mối quan hệ hai thông số | Tra bảng/công thức giới hạn cho đúng loại; với Balanced và size tùy chỉnh cung cấp đủ hai giá trị. |
| Không tạo/gắn được dù thông số hợp lệ | Quota, capacity, IAM hoặc Organization Policy | Đọc thông báo lỗi API, quota, danh tính và chính sách. |
| Disk đã tạo nhưng VM không attach được | VM không hỗ trợ loại disk, khác zone, sai access mode hoặc cấu hình có disk attach không tương thích | Đối chiếu machine series, zone/region, access mode và attachment limits. |
| Disk có trong Console nhưng Linux chưa thấy filesystem | Chỉ mới attach block device; chưa tạo filesystem hoặc mount | Xem `lsblk`, `blkid`, device ID; không vội format khi chưa xác minh dữ liệu. |
| Đã tăng disk size nhưng `df -h` không đổi | Partition/filesystem chưa được mở rộng trong guest OS | Kiểm tra từng lớp block device → partition → filesystem và thao tác resize phù hợp. |
| Đã tăng IOPS nhưng benchmark không tăng | VM bottleneck, I/O size/queue depth không đủ hoặc thay đổi chưa có hiệu lực | So sánh disk provision, VM limits, cooldown/propagation, benchmark profile. |
| IOPS cao nhưng throughput thấp | Workload dùng I/O nhỏ; throughput toán học tương ứng thấp | Tính IOPS × I/O size, kiểm tra đọc/ghi thực tế. |
| Throughput tốt nhưng latency database cao | Transaction, fsync, CPU, hàng đợi, cache hoặc contention | Xem p95/p99, query tracing, OS metrics và I/O wait. |
| Lệnh update bị từ chối dù mức mới hợp lệ | Thời gian chờ giữa các lần thay đổi hiệu năng chưa hết | Kiểm tra lịch sử thay đổi provision và thời gian cooldown theo loại đĩa. |
| VM chậm sau khi thêm nhiều disk | Giới hạn IOPS/throughput tổng theo máy đã chạm | Kiểm tra performance limits theo machine type; đo tổng I/O của các disk. |
| Hóa đơn tăng dù VM đã dừng | Hyperdisk vẫn được provision và tính phí theo cấu hình còn tồn tại | Xem disk chưa xóa, mức provision và Billing Reports. |
| Mất dữ liệu sau dùng multi-writer | Filesystem/ứng dụng không hỗ trợ ghi đồng thời an toàn | Kiểm tra access mode, thiết kế cluster, cơ chế fencing và backup. |

### 10.1. Quy trình điều tra một database chậm

Giả sử database trên Compute Engine báo p99 truy vấn tăng từ 80 lên 450 ms. Đừng lập tức tăng từ 6.000 lên 60.000 IOPS. Hãy:

1. **Xác định truy vấn nào chậm:** read/write, lock wait, transaction log, index scan hay bước gọi từ backend.
2. **Đo I/O tại VM:** số ops, kích thước, throughput, latency và queue depth trong khoảng lỗi.
3. **Đọc cấu hình Hyperdisk:** size, provisioned IOPS/throughput và thời điểm thay đổi gần nhất.
4. **So machine type limits:** số vCPU/machine series, tổng đĩa và mức giới hạn hiện tại.
5. **Kiểm tra CPU và RAM:** cache miss, CPU contention hoặc nhiều GC/worker có thể là nút thắt chính.
6. **Thử dưới tải đại diện:** ghi kết quả trước/sau khi thay đổi một biến có chủ đích.
7. **Xác minh chi phí và rủi ro:** mức provision mới có tương xứng với cải thiện SLO hay không; duy trì cơ chế backup và recovery.

Nếu throughput chỉ 60 MiB/s nhưng database ghi nhiều lần 4 KiB, tăng throughput lên 2.000 MiB/s mà không giải quyết IOPS hoặc truy vấn có thể không cải thiện. Nếu toàn bộ VM bị giới hạn ở mức thấp hơn mức đĩa, tăng provision của đĩa cũng không giải quyết nguyên nhân.

### 10.2. Dùng lệnh chỉ đọc để so sánh trước và sau

~~~bash
gcloud compute disks describe "$DISK_NAME" \
  --zone="$ZONE" \
  --format="yaml(name,type,sizeGb,provisionedIops,provisionedThroughput,status,users)"

gcloud compute instances describe "$VM_NAME" \
  --zone="$ZONE" \
  --format="yaml(name,machineType,disks,status)"
~~~

Trong Cloud Console, trang **Compute Engine → Storage → Disks** có thể hiển thị dung lượng và mức provision theo loại đĩa; Cloud Monitoring và dashboard ứng dụng giúp so sánh giá trị quan sát với cấu hình.

Không nên sao chép thông số từ một screenshot hoặc benchmark của VM khác mà thiếu thông tin machine type, số lượng disk, workload và thời điểm đo.

## 11. Bài tập tình huống: chọn Hyperdisk cho ba workload

Một doanh nghiệp xây dựng nền tảng học trực tuyến trên Google Cloud với ba thành phần:

1. **Order database:** lưu giao dịch đăng ký khóa học, tải đỉnh khoảng 16.000 IOPS, phần lớn I/O 8 KiB, cần p99 thấp.
2. **Batch analytics:** mỗi đêm quét tập dữ liệu lớn, đọc tuần tự 256 KiB, cần khoảng 900 MiB/s; số lượng IOPS không phải mục tiêu chính.
3. **Training data:** một tập dữ liệu lớn cần được nhiều VM dùng để đọc đồng thời phục vụ mô hình học máy, ít hoặc không ghi trong quá trình huấn luyện.

Đội vận hành đã có quota và khả năng chọn machine types được Hyperdisk hỗ trợ, nhưng ngân sách lưu trữ có giới hạn và không chấp nhận mất dữ liệu khi lỗi vận hành.

### 11.1. Bước 1 — Quy đổi tải từ IOPS sang MiB/s

Với cơ sở dữ liệu, ước lượng lượng dữ liệu chuyển ở thời điểm peak:

\[
16.000 \times 8 \ \text{KiB} \div 1.024
= 125 \ \text{MiB/s}
\]

Giá trị **125 MiB/s** không nói lên latency hoặc số lần fsync; vẫn cần đo p95/p99, mức ghi transaction log và hàng đợi. Nếu thêm các tác vụ sao lưu quét tuần tự, throughput peak có thể lớn hơn nhiều so với ước lượng chỉ dựa trên hoạt động giao dịch.

Với batch analytics, 900 MiB/s và kích thước I/O 256 KiB tương ứng:

\[
900 \ \text{MiB/s} \div 0{,}25 \ \text{MiB/I/O}
= 3.600 \ \text{IOPS}
\]

Ở đây **throughput** là tiêu chí nổi bật; mua mức IOPS rất cao chưa chắc có ích. Khi chuyển thành truy vấn data warehouse hoặc object pipeline, mô hình truy cập có thể khiến dịch vụ khác phù hợp hơn Hyperdisk.

### 11.2. Bước 2 — Lựa chọn ứng viên

| Workload | Ứng viên khởi đầu | Vì sao | Điều kiện cần chứng minh |
| --- | --- | --- | --- |
| Order database | Hyperdisk Balanced; đánh giá Extreme nếu cần IOPS lớn hơn thực sự | Nhu cầu IOPS và latency; có thể provision theo kết quả đo | Machine type, DB tuning, p99, backup, HA và chi phí |
| Batch analytics | Hyperdisk Throughput hoặc giải pháp lưu trữ phù hợp dạng dữ liệu | Nhu cầu MiB/s cao với thao tác lớn | Dung lượng tối thiểu, throughput hợp lệ theo size, CPU và hiệu năng xử lý |
| Training data | Hyperdisk ML nếu thiết kế đọc chia sẻ được hỗ trợ | Tập trung vào read throughput và những chế độ gắn đọc nhiều VM | Hỗ trợ read-only attachment, quota, máy/zone, cách phát hành data |

Nhóm vẫn phải thiết kế **backup** cho dữ liệu thay đổi và **phân loại dữ liệu** theo chính sách, bất kể dùng loại disk nào.

### 11.3. Bước 3 — Lập đề xuất cấu hình

Hãy lập bảng sau cho mỗi workload:

| Trường | Giá trị cần xác minh |
| --- | --- |
| Dung lượng lưu trữ và mức tăng trưởng | Dung lượng hiện tại, dung lượng dự trữ, giới hạn kích thước đĩa |
| Loại Hyperdisk | Balanced, Extreme, Throughput, ML hoặc Balanced HA |
| Số IOPS cần thiết | Trung bình, p95, peak, read/write mix |
| Throughput cần thiết | MiB/s ở những cỡ I/O thực tế |
| Latency/SLO | p50, p95, p99 và yêu cầu nghiệp vụ |
| Machine type | Hỗ trợ loại disk và mức I/O tổng yêu cầu |
| Vị trí | Zone/region, residency, tính sẵn sàng |
| Hiệu năng provision | Giá trị hợp lệ theo size, type và công thức sản phẩm |
| Chi phí | Dung lượng, IOPS, throughput, snapshot, tài nguyên khác |
| DR | Snapshot, backup, RPO/RTO, phương án failover |
| Phép thử | Fio profile và phép đo ứng dụng tương ứng |

Một đề xuất tốt phải nêu **bằng chứng của từng giá trị**, chứ không đơn thuần là “chọn Extreme vì nhanh nhất”.

### 11.4. Bước 4 — Đánh giá thay đổi sau một tháng

Sau một tháng, giả sử Order database chỉ sử dụng 5.000 IOPS trong hầu hết thời gian, nhưng có đỉnh 14.000 IOPS vào 30 phút cao điểm. Nhóm đã provision 50.000 IOPS.

Hãy phân tích:

- Có thể giảm provision mà vẫn giữ biên an toàn cho tải peak và p99 không?
- Có báo cáo nào cho thấy CPU hoặc lock contention mới là yếu tố giới hạn?
- Có thể phân bổ lại giờ chạy batch để tránh tranh chấp tài nguyên không?
- Chi phí tiết kiệm dự kiến có đủ lớn để đáng thử điều chỉnh không?
- Cần đo lại trong khung giờ nào sau khi thay đổi và chờ thời gian có hiệu lực?

**Đáp án định hướng:** cần lập profile tải thật, xem xu hướng và mức tăng trưởng, chọn một mức provision thấp hơn **nhưng vẫn vượt nhu cầu hợp lý ở đỉnh**, thử nghiệm có kiểm soát và quan sát. Không tự động hạ xuống đúng giá trị trung bình hoặc giữ mức cao chỉ vì đã cấu hình từ đầu.

## 12. Dọn tài nguyên lab và xác minh chi phí

Nếu bạn đã tạo disk và gắn vào VM lab theo phần thực hành:

1. Dừng mọi tiến trình đang sử dụng mount point; xóa **chỉ** tệp benchmark riêng nếu còn.
2. Unmount filesystem từ trong VM và xác nhận không còn thao tác I/O quan trọng.
3. Detach disk từ VM khi đã an toàn.
4. Xóa **đúng** volume lab đã tạo; không xóa đĩa chứa dữ liệu thật hoặc disk đã được người khác tiếp nhận.
5. Kiểm tra danh sách disk và Billing Reports sau khi xóa.

**Bên trong VM**, sau khi đã ngừng ứng dụng trên mount point:

~~~bash
sudo umount /mnt/hyperdisk-lab
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS
~~~

**Bên ngoài VM**, với gcloud ở đúng project:

~~~bash
# Xác minh ID tài nguyên và quan hệ gắn disk trước khi xóa
gcloud config get-value project
gcloud compute disks describe "$DISK_NAME" \
  --zone="$ZONE" \
  --format="yaml(name,type,sizeGb,users)"

# Chỉ tháo data disk do lab tạo, sau khi unmount an toàn
gcloud compute instances detach-disk "$VM_NAME" \
  --zone="$ZONE" \
  --disk="$DISK_NAME"

# Chỉ xóa disk của bài lab này; không xóa disk đang chứa dữ liệu cần giữ
gcloud compute disks delete "$DISK_NAME" --zone="$ZONE" --quiet

# Kiểm tra không còn volume lab
gcloud compute disks list --filter="name=$DISK_NAME"
~~~

Nếu bạn mới chỉ tạo disk mà **chưa attach**, bỏ qua bước unmount/detach, nhưng vẫn kiểm tra tên disk, zone và người sở hữu trước khi xóa.

**Dừng VM không tự xóa Hyperdisk.** Dữ liệu và mức hiệu năng đã provision trên volume còn tồn tại vẫn có thể tính phí. Phí đã phát sinh trong thời gian lab chạy có thể được ghi nhận chậm trong báo cáo Cloud Billing.

## 13. Câu hỏi tự kiểm tra

**1. Một volume provision 20.000 IOPS có chắc luôn thực hiện 20.000 IOPS không?**  
Không. Mức provision là mục tiêu; tải ứng dụng, dung lượng, loại disk, machine type, queue depth và các giới hạn khác quyết định giá trị thực.

**2. Một workload đạt 10.000 IOPS với I/O 4 KiB đang chuyển khoảng bao nhiêu MiB/s?**  
Khoảng **39,1 MiB/s**. Cần đổi từ KiB sang MiB và phân biệt IOPS với byte throughput.

**3. Có thể đặt cả provisioned IOPS và provisioned throughput cho Hyperdisk Extreme không?**  
Không theo mô hình cấu hình trực tiếp của loại đĩa này: người dùng provision IOPS, còn throughput được dẫn xuất theo quy tắc sản phẩm.

**4. Hyperdisk Throughput và Hyperdisk ML có nút provision IOPS độc lập không?**  
Không. Với những loại này, IOPS được xác định từ throughput provisioned theo công thức dịch vụ.

**5. Tại sao tăng IOPS trên disk có thể không tăng tốc database?**  
Vì workload có thể bị giới hạn ở CPU, machine type, lock, query, độ lớn I/O hoặc throughput thay vì IOPS.

**6. Vì sao không dùng một Hyperdisk Balanced zonal ở zone A để coi là đã có dự phòng zone B?**  
Vì volume zonal không tự tạo replica ở zone B. Cần xem Hyperdisk Balanced High Availability hoặc cơ chế nhân bản/phục hồi phù hợp.

**7. Có thể dùng multi-writer và mount cùng filesystem ext4 bình thường để hai VM cùng ghi an toàn không?**  
Không mặc định. Cần giải pháp quản lý ghi đồng thời và tính nhất quán được filesystem/ứng dụng hỗ trợ.

**8. Tăng dung lượng đĩa có tự mở rộng filesystem hoặc tăng throughput đã provision không?**  
Không tự động theo cách có thể dựa vào cho mọi cấu hình. Size volume, filesystem và thông số hiệu năng là những lớp cần quản lý riêng.

**9. Snapshot có tự bảo đảm phục hồi nhất quán ứng dụng khi database đang ghi không?**  
Không. Cần thiết kế và kiểm tra cơ chế snapshot nhất quán theo yêu cầu nghiệp vụ, cùng quy trình restore.

**10. Đã xóa VM nhưng giữ Hyperdisk thì có thể tiếp tục bị tính phí không?**  
Có. Volume còn tồn tại và các mức provision có thể tiếp tục tính phí theo chính sách sản phẩm.

## Tài liệu Google Cloud tham khảo

- **Google Cloud Hyperdisk overview:** https://cloud.google.com/compute/docs/disks/hyperdisks — các loại Hyperdisk, workload và tính năng.
- **Hyperdisk performance overview:** https://cloud.google.com/compute/docs/disks/hyperdisk-performance — provisioned performance, IOPS, throughput và giới hạn.
- **Hyperdisk performance limits by machine series:** https://cloud.google.com/compute/docs/disks/hyperdisk-perf-limits — giới hạn trên mỗi VM/machine type.
- **Hyperdisk Balanced:** https://cloud.google.com/compute/docs/disks/hd-types/hyperdisk-balanced — giới hạn size, IOPS và throughput.
- **Hyperdisk Extreme:** https://cloud.google.com/compute/docs/disks/hd-types/hyperdisk-extreme — cấu hình và giới hạn phù hợp cho IOPS cao.
- **Hyperdisk Throughput:** https://cloud.google.com/compute/docs/disks/hd-types/hyperdisk-throughput — công thức provision throughput và IOPS.
- **Hyperdisk ML:** https://cloud.google.com/compute/docs/disks/hd-types/hyperdisk-ml — read throughput, attachment và giới hạn.
- **Hyperdisk Balanced High Availability:** https://cloud.google.com/compute/docs/disks/hd-types/hyperdisk-balanced-ha — sao chép hai zone và khả năng phục hồi.
- **Create Hyperdisk volumes:** https://cloud.google.com/compute/docs/disks/add-hyperdisk — tùy chọn tạo và gắn đĩa.
- **Modify Hyperdisk size and performance:** https://cloud.google.com/compute/docs/disks/modify-hyperdisks — resize, thời gian chờ và điều chỉnh provision.
- **Analyze provisioned IOPS and throughput:** https://cloud.google.com/compute/docs/disks/analyze-iops-hyperdisk — đọc cấu hình và đối chiếu metric.
- **Benchmark Hyperdisk performance:** https://cloud.google.com/compute/docs/disks/benchmark-hyperdisk-performance — phương pháp kiểm thử và giới hạn đo.
- **Snapshot best practices:** https://cloud.google.com/compute/docs/disks/snapshot-best-practices — bảo vệ dữ liệu, consistency và restore.
- **Compute Engine disks pricing:** https://cloud.google.com/compute/disks-image-pricing — cấu trúc giá theo loại, dung lượng và hiệu năng.

Danh sách loại đĩa, thông số tối đa, công thức provision, machine type hỗ trợ, thời gian có hiệu lực và bảng giá có thể thay đổi. Khi dùng thật, hãy đối chiếu tài liệu tại thời điểm triển khai và chạy thử với **đúng workload, machine type, dung lượng và zone**. Chọn đúng Hyperdisk là chọn mức hiệu năng có căn cứ, đáp ứng latency/SLO và khả năng phục hồi, trong giới hạn ngân sách chấp nhận được.

# Lựa chọn dung lượng, loại đĩa và giới hạn I/O theo máy

Lưu trữ gắn với máy tính cloud ảnh hưởng trực tiếp đến thời gian khởi động, tốc độ đọc/ghi dữ liệu, độ trễ ứng dụng và chi phí vận hành. Một volume có dung lượng lớn chưa chắc có I/O nhanh; một ổ SSD có IOPS cao cũng chưa chắc giúp ứng dụng nếu instance bị giới hạn băng thông lưu trữ hoặc workload chủ yếu chờ mạng và CPU.

Khi chọn storage cho VM, cần đánh giá đồng thời **dung lượng (capacity), IOPS, throughput, latency, kiểu truy cập và giới hạn I/O của instance**. Ngoài ra phải xác định dữ liệu cần tồn tại qua vòng đời VM hay có thể tái tạo, yêu cầu độ bền, backup, mã hóa và cách mở rộng sau này. Mục tiêu là cung cấp đủ không gian và hiệu năng cho workload ở tải bình thường lẫn tải đỉnh với chi phí hợp lý.

## 1. Các chỉ số cơ bản của storage

### Dung lượng (capacity)

Capacity là lượng dữ liệu volume có thể lưu trữ, thường được biểu diễn bằng GB hoặc GiB. Khi lập kế hoạch, cần tính cả dữ liệu nghiệp vụ, index, log, file tạm, dữ liệu phát sinh khi cập nhật, dung lượng dự phòng và tốc độ tăng trưởng.

Không nên cấp volume vừa khít với dung lượng dữ liệu hiện tại. Filesystem cần không gian trống để hoạt động; database có thể cần vùng tạm cho sort, rebuild index, vacuum, compaction hoặc transaction log. Khi filesystem gần đầy, hiệu năng và khả năng ghi dữ liệu có thể suy giảm, thậm chí ứng dụng ngừng hoạt động.

### IOPS

IOPS (Input/Output Operations Per Second) là số thao tác đọc/ghi I/O hoàn thành trong một giây. IOPS thường hữu ích với workload có nhiều thao tác nhỏ và ngẫu nhiên, chẳng hạn database OLTP, metadata, queue hoặc hệ thống file có nhiều file nhỏ.

IOPS không cho biết kích thước mỗi thao tác. 10.000 IOPS với block 4 KiB tạo ra lượng dữ liệu khác rất nhiều so với 10.000 IOPS với block 256 KiB. Vì vậy, phải xem IOPS cùng block size, read/write mix và latency.

### Throughput

Throughput là lượng dữ liệu được đọc hoặc ghi trong một đơn vị thời gian, thường tính bằng MB/s hoặc MiB/s. Nó quan trọng với workload truyền các khối dữ liệu lớn và liên tục như backup, ETL, xử lý video, quét dữ liệu hoặc đọc tuần tự file lớn.

Với workload có kích thước I/O tương đối ổn định, có thể ước lượng throughput:

\[
\text{Throughput} \approx \text{IOPS} \times \text{I/O size}
\]

Ví dụ, 6.000 IOPS với block 16 KiB có throughput lý thuyết:

\[
6.000 \times 16\text{ KiB} = 96.000\text{ KiB/s}
\approx 93{,}75\text{ MiB/s}
\]

Đây là quan hệ tính toán đơn giản. Throughput thực tế còn bị giới hạn bởi volume, instance, filesystem, queue, mạng và cách workload phát I/O.

### Latency

Latency là thời gian từ khi ứng dụng gửi yêu cầu I/O đến khi thao tác được hoàn tất. Nó thường được đo bằng mili giây (ms) hoặc micro giây (µs). Database giao dịch và ứng dụng tương tác thường nhạy với latency hơn throughput tổng.

Không nên chỉ xem latency trung bình. Hãy theo dõi phân vị như p50, p95 và p99 để nhận biết các lần I/O chậm bất thường. Một hệ thống có average latency thấp nhưng p99 cao có thể vẫn gây timeout hoặc làm người dùng cảm nhận ứng dụng chậm.

### Queue depth và concurrency

Queue depth là số yêu cầu I/O đang chờ hoặc đang được xử lý đồng thời. Tăng queue depth có thể giúp thiết bị hoặc dịch vụ storage duy trì throughput cao hơn, đặc biệt với workload song song. Tuy nhiên, queue quá sâu có thể làm thời gian chờ tăng và latency xấu đi.

Ứng dụng có concurrency thấp có thể không đạt mức IOPS tối đa được quảng cáo vì không gửi đủ yêu cầu đồng thời. Ngược lại, một workload nhiều worker có thể tạo queue lớn và chạm giới hạn volume hoặc instance. Cần benchmark với queue depth và số job gần với hành vi production.

## 2. Nhận diện kiểu truy cập của workload

Thông số storage nên được chọn từ kiểu I/O mà ứng dụng thực sự tạo ra.

| Kiểu workload | Đặc điểm I/O | Chỉ số thường quan trọng |
|---|---|---|
| Database OLTP | Nhiều thao tác nhỏ, ngẫu nhiên, hỗn hợp đọc/ghi, nhạy với fsync | IOPS, p95/p99 latency, write latency và độ ổn định |
| Data warehouse / analytics | Đọc nhiều khối lớn, quét bảng và file | Throughput đọc, dung lượng và khả năng song song |
| Backup / restore | Ghi hoặc đọc tuần tự khối lớn | Throughput, thời gian hoàn thành và chi phí truyền dữ liệu |
| Log / queue | Nhiều lần ghi tuần tự hoặc append, có thể cần flush | Write throughput, latency và độ bền dữ liệu |
| Web / application server | Nhiều file nhỏ, package, log và cache | Dung lượng, latency vừa phải và IOPS ổn định |
| CI/CD và build | Đọc/ghi file nhỏ, tạo/xóa nhiều file, giải nén | IOPS, metadata performance và dung lượng tạm |
| Media processing | Đọc/ghi file lớn và dữ liệu tuần tự | Throughput, dung lượng và khả năng mở rộng |
| Cache có thể tái tạo | Đọc/ghi nhanh, dữ liệu có thể mất | Latency, IOPS và chi phí; local disk có thể phù hợp |

Một ứng dụng có thể kết hợp nhiều kiểu truy cập. Ví dụ, database có thể cần IOPS cao cho transaction log nhưng throughput cao cho backup và batch scan. Có thể tách data, log, temp và backup sang volume riêng nếu nền tảng và ứng dụng hưởng lợi từ việc cô lập I/O.

## 3. Các loại storage gắn với compute

### Persistent block storage

Persistent block volume là thiết bị block được cung cấp qua mạng hoặc fabric lưu trữ của cloud. Volume có thể được gắn vào VM như một disk và thường tồn tại độc lập với vòng đời VM nếu không bị xóa theo chính sách.

Đặc điểm thường gặp:

- Có thể detach khỏi VM này và attach vào VM khác theo giới hạn của dịch vụ.
- Có thể tăng dung lượng hoặc thay đổi hiệu năng theo khả năng nền tảng.
- Hỗ trợ snapshot, encryption và backup theo tính năng của nhà cung cấp.
- I/O đi qua hạ tầng lưu trữ và mạng nội bộ của cloud; latency và throughput phụ thuộc volume cùng instance.

Persistent block storage phù hợp với root disk, database, ứng dụng stateful và dữ liệu cần tồn tại qua stop/start hoặc thay thế VM. Tuy nhiên, không nên coi volume là backup độc lập: lỗi thao tác, xóa nhầm, mã độc hoặc lỗi ứng dụng vẫn có thể ảnh hưởng dữ liệu trên volume.

### SSD đa dụng (general-purpose SSD)

General-purpose SSD thường cân bằng giữa giá, IOPS và throughput. Một số dịch vụ tăng hiệu năng theo dung lượng đã cấp; một số cho phép đặt IOPS hoặc throughput riêng trong giới hạn nhất định.

Loại này phù hợp với boot volume, máy chủ ứng dụng, database vừa và nhỏ, môi trường phát triển và nhiều workload phổ thông. Cần kiểm tra baseline, mức tối đa, cơ chế burst và cách tính phí theo dung lượng hoặc hiệu năng.

### SSD provisioned IOPS

Provisioned IOPS SSD cho phép chọn mức IOPS được cấp trong một dải cấu hình. Nó phù hợp với database lớn, workload giao dịch hoặc ứng dụng cần hiệu năng I/O ổn định và có yêu cầu latency chặt.

Provisioned IOPS không bảo đảm workload luôn đạt đúng con số đã đặt trong mọi tình huống. Volume vẫn chịu giới hạn throughput, block size, queue, instance-level cap, filesystem và khả năng phát I/O của ứng dụng. Một số dịch vụ có tỷ lệ tối đa giữa dung lượng volume và IOPS; phải kiểm tra điều kiện cấu hình trước khi đặt mức cao.

### HDD tối ưu throughput hoặc dung lượng

HDD cloud thường có chi phí thấp hơn SSD cho mỗi đơn vị dung lượng, phù hợp với dữ liệu lớn, truy cập tuần tự, log archive hoặc workload ít nhạy với latency. Một số loại được tối ưu throughput, số khác dành cho dữ liệu lạnh hoặc ít truy cập.

HDD thường không phù hợp với database OLTP có nhiều I/O ngẫu nhiên nhỏ hoặc workload cần latency thấp. Không nên chọn chỉ dựa trên dung lượng và giá nếu ứng dụng yêu cầu nhiều IOPS.

### Local NVMe / instance store

Local NVMe là thiết bị lưu trữ gắn trực tiếp với host của instance. Nó có thể cung cấp latency thấp và throughput cao do đường I/O ngắn hơn so với volume qua mạng. Một số instance có nhiều thiết bị NVMe cục bộ có thể kết hợp để tăng dung lượng hoặc hiệu năng.

Local NVMe thường có vòng đời gắn với host hoặc instance. Dữ liệu có thể mất khi terminate, thay host, một số thao tác stop/start hoặc khi phần cứng gặp sự cố. Hành vi qua reboot hay stop/start phụ thuộc loại instance và cam kết nhà cung cấp.

Local NVMe phù hợp với cache, scratch space, dữ liệu trung gian, temporary processing và replica có thể tái tạo. Với database, chỉ dùng làm nơi lưu dữ liệu chính khi ứng dụng có replication, backup và cơ chế phục hồi phù hợp; không dựa vào local disk làm bản sao duy nhất.

### File storage và object storage

File storage cung cấp giao diện filesystem chia sẻ qua mạng, phù hợp với nhiều VM cùng truy cập một cây thư mục, thư mục home, nội dung dùng chung hoặc ứng dụng cần giao thức file. Hiệu năng phụ thuộc throughput, IOPS, số client và metadata operation.

Object storage lưu dữ liệu dưới dạng object và metadata, truy cập qua API/HTTP thay vì block device thông thường. Nó phù hợp với backup, log, artifact, media và dữ liệu lớn có tính bền vững. Object storage thường không thể mount như một block disk native mà không qua gateway hoặc filesystem adapter; cách truy cập đó có giới hạn và hành vi khác với block storage.

Không nên chọn file/object storage chỉ để thay block volume mà không xem xét semantics của ứng dụng, locking, consistency, rename, random write và latency.

### So sánh nhanh

| Loại storage | Hiệu năng điển hình | Độ bền/vòng đời | Workload phù hợp |
|---|---|---|---|
| General-purpose SSD volume | IOPS và throughput cân bằng | Persistent theo chính sách volume | Boot, ứng dụng phổ thông, database vừa |
| Provisioned IOPS SSD | IOPS cao, cấu hình hiệu năng rõ hơn | Persistent theo chính sách volume | OLTP, database và workload latency-sensitive |
| Throughput HDD | Throughput tuần tự, IOPS ngẫu nhiên thấp hơn SSD | Persistent theo chính sách volume | Backup, log lớn, scan tuần tự |
| Cold HDD | Chi phí dung lượng thấp, truy cập chậm hơn | Persistent theo chính sách volume | Dữ liệu ít truy cập |
| Local NVMe | Latency thấp, throughput cao | Phụ thuộc host/instance; có thể mất dữ liệu | Cache, scratch, dữ liệu trung gian |
| File storage | Chia sẻ file qua mạng | Theo dịch vụ file | Shared directory và ứng dụng nhiều client |
| Object storage | Truy cập qua API, tối ưu dữ liệu object | Theo dịch vụ object | Backup, archive, media, artifact |

Tên gọi và đặc tính cụ thể thay đổi theo cloud provider. Hãy dùng thông số của đúng dịch vụ và region khi thiết kế production.

## 4. Tính dung lượng cần cấp

Dung lượng nên dựa trên dữ liệu hiện tại, tốc độ tăng trưởng, vùng tạm, log, index và headroom vận hành.

Một cách ước lượng đơn giản:

\[
\text{Capacity}_{required} =
(\text{Data} + \text{Index} + \text{Logs} + \text{Temp})
\times (1 + \text{Growth})
\times (1 + \text{Headroom})
\]

Trong đó growth là mức tăng trong khoảng lập kế hoạch; headroom là phần dự phòng để tránh filesystem thường xuyên đầy. Cần điều chỉnh công thức nếu log có retention riêng, dữ liệu được nén, có replication hoặc temp được đặt trên volume khác.

### Ví dụ tính cho database

Giả sử database hiện có:

- Data: 500 GiB.
- Index: 100 GiB.
- Log và journal: 50 GiB.
- Dự kiến tăng 30% trong giai đoạn lập kế hoạch.
- Giữ thêm 20% headroom sau khi tính tăng trưởng.

Dung lượng trước dự phòng:

\[
500 + 100 + 50 = 650\text{ GiB}
\]

Sau tăng trưởng:

\[
650 \times 1{,}30 = 845\text{ GiB}
\]

Sau headroom:

\[
845 \times 1{,}20 = 1.014\text{ GiB}
\]

Có thể chọn volume khoảng 1 TiB nếu giới hạn dịch vụ và cách quy đổi đơn vị phù hợp. Trước khi chốt, cần tính riêng không gian cho backup, snapshot, transaction log retention, compaction và thao tác bảo trì. Không nhất thiết phải đặt tất cả dữ liệu trên một volume duy nhất.

### Theo dõi tốc độ tăng trưởng

Đo dung lượng sử dụng theo ngày hoặc tuần để xác định xu hướng. Với database, nên theo dõi riêng data, index, transaction log, temp, backup staging và dung lượng trống của filesystem. Dùng tốc độ tăng trung bình cùng mức đỉnh theo chu kỳ để dự báo thời điểm cần mở rộng.

Đặt cảnh báo theo cả phần trăm và dung lượng tuyệt đối. Ví dụ, volume 20 GiB ở mức 80% chỉ còn 4 GiB; volume 10 TiB ở mức 80% còn rất nhiều dung lượng tuyệt đối. Ngưỡng phù hợp phụ thuộc tốc độ ghi và thời gian cần để mở rộng volume.

## 5. Chọn IOPS và throughput theo workload

### Xác định read/write mix và block size

Trước khi chọn volume, hãy thu thập:

- Tỷ lệ đọc/ghi (ví dụ 70% read, 30% write).
- Block size phổ biến và phân bố kích thước I/O.
- Random hay sequential; synchronous hay asynchronous.
- Số worker, concurrency và queue depth.
- IOPS, throughput và latency ở tải bình thường lẫn tải đỉnh.
- Thời gian cao điểm kéo dài bao lâu và có burst hay không.

Một database OLTP có thể tạo nhiều thao tác 4 KiB hoặc 8 KiB ngẫu nhiên, trong khi backup tạo thao tác tuần tự 1 MiB. Cùng một volume có thể đạt IOPS cao trong bài test nhỏ nhưng không đạt throughput mong muốn khi block size lớn.

### Tính IOPS từ tải ứng dụng

Nếu biết số thao tác I/O trung bình trên mỗi request và số request mỗi giây, có thể ước lượng:

\[
\text{IOPS}_{required} \approx
\text{I/O operations per request}
\times \text{requests per second}
\]

Ví dụ, một dịch vụ xử lý 800 request/giây, mỗi request tạo trung bình 12 thao tác đọc/ghi block:

\[
800 \times 12 = 9.600\text{ IOPS}
\]

Nếu muốn duy trì headroom 30%, mức mục tiêu có thể vào khoảng 12.500 IOPS. Đây là ước lượng ban đầu; cache hit, write coalescing, batching, filesystem và database engine có thể thay đổi số I/O thực sự xuống volume.

### Tính throughput từ block size

Nếu workload cần 8.000 IOPS với block trung bình 32 KiB:

\[
8.000 \times 32\text{ KiB} = 256.000\text{ KiB/s}
\approx 250\text{ MiB/s}
\]

Volume phải hỗ trợ cả IOPS lẫn throughput tương ứng, và instance phải có đủ băng thông lưu trữ. Nếu một trong hai giới hạn thấp hơn, workload sẽ bị giới hạn ở mức thấp hơn.

### Đọc và ghi có thể có giới hạn khác nhau

Một số dịch vụ có hiệu năng đọc và ghi khác nhau, đặc biệt với cache, replication hoặc cơ chế ghi bền vững. Workload ghi đồng bộ có thể nhạy với write latency hơn tổng write throughput. Database dùng `fsync` hoặc flush log thường cần thời gian hoàn tất ghi bền vững ổn định.

Hãy đo riêng read IOPS, write IOPS, read throughput, write throughput và latency từng chiều nếu công cụ hỗ trợ. Tỷ lệ đọc/ghi trung bình không thể hiện đầy đủ các đợt ghi log hoặc checkpoint theo chu kỳ.

## 6. Hiểu giới hạn I/O của volume và của instance

Đây là điểm thường bị bỏ qua khi sizing. Một volume có thể được cấp 20.000 IOPS và 500 MiB/s, nhưng VM chỉ hỗ trợ tổng lưu trữ 10.000 IOPS hoặc 300 MiB/s. Khi đó, gắn volume nhanh hơn cũng không giúp workload vượt giới hạn của instance.

### Hai lớp giới hạn

**Volume-level limit** là mức tối đa hoặc baseline do loại volume, dung lượng và cấu hình IOPS/throughput quyết định. Mỗi volume có thể có giới hạn riêng về IOPS, throughput, kích thước tối đa, queue hoặc burst.

**Instance-level limit** là giới hạn tổng I/O mà instance có thể trao đổi với storage service. Nó có thể được biểu diễn bằng tổng IOPS, tổng throughput hoặc mức băng thông EBS/block storage. Tất cả volume gắn vào cùng VM có thể cùng chia sẻ giới hạn này.

Hiệu năng thực tế thường bị chặn bởi giới hạn thấp nhất trong đường I/O:

\[
\text{Effective I/O} \leq
\min(\text{Volume limit},\text{Instance limit},\text{Workload demand})
\]

Ngoài ra còn có giới hạn của filesystem, driver, network path, hypervisor và dịch vụ storage.

### Ví dụ tổng hợp nhiều volume

Giả sử VM có hai volume:

| Volume | IOPS tối đa | Throughput tối đa |
|---|---:|---:|
| Data | 8.000 | 250 MiB/s |
| Log | 6.000 | 200 MiB/s |
| Tổng theo volume | 14.000 | 450 MiB/s |

Nếu instance chỉ hỗ trợ tổng cộng 10.000 IOPS và 300 MiB/s cho storage traffic, hai volume không thể cùng đạt mức tối đa đồng thời. Tổng hiệu năng của VM bị giới hạn bởi instance. Khi thiết kế, cần kiểm tra bảng giới hạn của instance family và size cụ thể, đồng thời xem giới hạn có phụ thuộc kích thước máy hoặc chế độ burst không.

### Baseline, burst và credit

Một số volume hoặc instance cung cấp baseline I/O và cho phép burst trong một khoảng thời gian bằng credit hoặc cơ chế tương tự. Khi workload ngắn hạn, burst có thể giúp đạt hiệu năng cao; khi tải kéo dài, hiệu năng có thể giảm về baseline sau khi credit cạn.

Đối với database chạy liên tục, không nên sizing theo mức burst tối đa nếu baseline thấp hơn nhu cầu ổn định. Hãy xem credit balance, burst duration, refill rate và hành vi khi hết credit. Benchmark phải kéo dài đủ lâu để phát hiện suy giảm sau giai đoạn burst.

### Nhiều volume có tự động tăng hiệu năng không?

Gắn nhiều volume có thể tăng tổng IOPS/throughput nếu dịch vụ hỗ trợ tổng hợp hiệu năng và instance còn headroom. Tuy nhiên, nhiều volume không tự động cộng dồn vô hạn. Instance-level cap, filesystem, RAID/LVM, queue và ứng dụng đều có thể trở thành nút thắt.

Striping qua RAID 0 hoặc LVM có thể phân tán I/O trên nhiều volume để tăng throughput hoặc IOPS, nhưng làm tăng độ phức tạp và có thể khiến một volume lỗi làm hỏng toàn bộ logical volume. Chỉ sử dụng khi có benchmark, backup và kế hoạch phục hồi rõ ràng.

## 7. Tách volume theo vai trò

Tách root và data volume giúp quản lý vòng đời và phục hồi rõ ràng hơn. Một số workload có thể hưởng lợi khi tách data, transaction log, temp và backup staging để giảm tranh chấp I/O.

| Volume | Nội dung | Mục tiêu thiết kế |
|---|---|---|
| Root | OS, package và agent | Dung lượng vừa đủ, dễ thay image hoặc phục hồi OS |
| Application | Binary, artifact hoặc file ứng dụng | Tùy tốc độ deploy và kiểu truy cập |
| Data | Bảng, index hoặc dữ liệu chính | Ưu tiên độ bền, IOPS và latency theo workload |
| Transaction log | WAL, redo log hoặc journal | Ghi ổn định, latency thấp và bảo vệ dữ liệu |
| Temp / scratch | File tạm, sort, build output | Có thể dùng volume riêng hoặc local NVMe nếu tái tạo được |
| Backup staging | File backup tạm trước khi chuyển sang object storage | Throughput ghi/đọc và khả năng dọn dẹp |

Tách volume có thể cải thiện khả năng quản lý, nhưng không phải lúc nào cũng tăng hiệu năng. Nếu tất cả volume vẫn chia sẻ cùng một instance cap hoặc cùng một filesystem queue, mức tăng có thể không đáng kể. Hãy xác định mục tiêu là cô lập lỗi, quản lý backup, thay đổi vòng đời hay tăng I/O trước khi tách.

## 8. Filesystem và cấu hình guest OS

Cloud cung cấp block device; guest OS cần nhận diện thiết bị, tạo partition, filesystem và mount vào cây thư mục. Hiệu năng và độ an toàn còn phụ thuộc cấu hình bên trong VM.

### Linux

Một số lệnh kiểm tra cơ bản:

```bash
# Liệt kê disk, partition và mount point
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS

# Xem filesystem và dung lượng đã dùng
df -hT

# Xem UUID và loại filesystem
blkid

# Theo dõi IOPS, throughput, latency và queue theo thiết bị
iostat -xz 1

# Kiểm tra kernel log liên quan tới disk và filesystem
dmesg -T | grep -Ei 'nvme|scsi|virtio|I/O error|filesystem'
```

Khi mount data volume, nên dùng UUID hoặc cơ chế định danh ổn định thay vì giả định disk luôn là `/dev/sdb`. Tên thiết bị có thể thay đổi khi thêm disk, đổi instance family hoặc thay controller. Cấu hình `/etc/fstab` cần có tùy chọn phù hợp để một volume lỗi không làm máy boot bị treo ngoài dự kiến.

### Windows

Trên Windows, có thể dùng Disk Management hoặc PowerShell để xem disk, partition và filesystem:

```powershell
# Liệt kê disk và trạng thái
Get-Disk

# Xem volume, filesystem và dung lượng
Get-Volume

# Xem partition theo disk
Get-Partition
```

Performance Monitor có thể theo dõi các counter như `Disk Reads/sec`, `Disk Writes/sec`, `Disk Read Bytes/sec`, `Disk Write Bytes/sec`, `Avg. Disk sec/Read`, `Avg. Disk sec/Write` và `Current Disk Queue Length`. Cần diễn giải queue cùng loại disk, số volume và mức concurrency của workload.

### Chọn filesystem

Linux thường dùng ext4 hoặc XFS; Windows thường dùng NTFS hoặc ReFS trong các trường hợp được hỗ trợ. Việc chọn filesystem phụ thuộc OS, ứng dụng, kích thước file, số lượng file, snapshot/backup và yêu cầu vận hành. Không có filesystem nào luôn nhanh nhất cho mọi workload.

Một số điểm cần xem:

- Kích thước block và allocation unit có phù hợp với workload không.
- Metadata operation có phải nút thắt không.
- Journal hoặc write barrier có đáp ứng yêu cầu độ bền không.
- Filesystem có hỗ trợ mở rộng online theo nền tảng không.
- Công cụ backup, snapshot và khôi phục có hỗ trợ filesystem không.
- Tùy chọn discard/TRIM có được khuyến nghị cho loại volume không.

Không tắt cơ chế đảm bảo tính nhất quán hoặc durability chỉ để cải thiện benchmark nếu chưa hiểu rủi ro dữ liệu.

## 9. Mở rộng dung lượng và thay đổi hiệu năng

Nhiều cloud hỗ trợ tăng dung lượng volume khi VM đang chạy, nhưng sau khi thay đổi ở control plane, guest OS có thể vẫn cần mở rộng partition và filesystem. Quy trình cụ thể phụ thuộc OS, filesystem, loại volume và nhà cung cấp.

### Mở rộng volume

Quy trình tổng quát:

1. Kiểm tra backup/snapshot và xác nhận có thể khôi phục.
2. Kiểm tra loại volume có hỗ trợ resize online không.
3. Tăng dung lượng hoặc hiệu năng trên control plane theo hướng dẫn dịch vụ.
4. Xác minh guest OS nhận được kích thước block device mới.
5. Mở rộng partition nếu có, sau đó mở rộng filesystem theo công cụ của OS.
6. Kiểm tra `df`, `lsblk` hoặc công cụ tương đương để xác nhận dung lượng mới.
7. Theo dõi latency, IOPS và throughput sau thay đổi.

Tăng dung lượng không phải lúc nào cũng tự động tăng IOPS hoặc throughput. Với volume tính hiệu năng theo dung lượng, tăng size có thể tăng baseline; với volume provisioned IOPS, cần điều chỉnh thông số hiệu năng riêng. Đọc giới hạn và cách tính phí của dịch vụ.

### Thu nhỏ volume

Thu nhỏ thường phức tạp và có thể không được hỗ trợ trực tiếp. Một số dịch vụ chỉ cho phép tăng dung lượng. Nếu cần giảm size, thường phải tạo volume mới nhỏ hơn, sao chép dữ liệu ở mức ứng dụng hoặc filesystem, xác minh tính nhất quán rồi chuyển workload. Không cố thu nhỏ block device hoặc filesystem theo cách chưa được hỗ trợ vì có thể mất dữ liệu.

### Thay đổi IOPS và throughput

Nếu dịch vụ cho phép điều chỉnh IOPS hoặc throughput độc lập, thay đổi có thể thực hiện online nhưng có giới hạn, thời gian áp dụng và chi phí. Cần kiểm tra:

- Mức tối thiểu/tối đa và tỷ lệ IOPS trên dung lượng.
- Throughput tối đa theo volume và theo instance.
- Có giới hạn số lần thay đổi trong một khoảng thời gian không.
- Thời gian thay đổi có hiệu lực và có ảnh hưởng tạm thời không.
- Chi phí mới có được duy trì khi workload giảm không.

## 10. Đo hiệu năng storage

Không nên chọn loại volume chỉ dựa trên thông số marketing hoặc benchmark của workload khác. Cần đo với block size, read/write mix, queue depth, concurrency và thời gian chạy gần thực tế.

### Các chỉ số cần thu thập

- IOPS đọc và ghi.
- Throughput đọc và ghi.
- Latency p50, p95 và p99.
- Queue depth và thời gian chờ.
- CPU iowait và mức sử dụng CPU của ứng dụng.
- Tỷ lệ cache hit và lượng dữ liệu thực sự đi tới volume.
- Burst credit hoặc trạng thái throttling nếu dịch vụ có cơ chế này.
- Instance storage bandwidth/IOPS usage và giới hạn còn lại.

### Công cụ fio trên Linux

`fio` tạo tải I/O có thể điều chỉnh block size, read/write mix, số job và queue depth. Ví dụ sau minh họa bài test random read/write trên một file thử nghiệm đã được tạo trước trong volume kiểm thử:

```bash
fio --name=rand-mixed \
  --filename=/mnt/bench/fio-test.bin \
  --size=4G \
  --rw=randrw \
  --rwmixread=70 \
  --bs=4k \
  --iodepth=32 \
  --numjobs=4 \
  --runtime=60 \
  --time_based \
  --direct=1 \
  --group_reporting
```

Chạy bài test trên volume riêng hoặc file thử nghiệm có thể xóa, không chạy trực tiếp lên device chứa dữ liệu production. Test ghi có thể ghi đè dữ liệu; ngay cả test đọc cũng tạo tải và ảnh hưởng dịch vụ. Nên chạy trong cửa sổ kiểm thử, dùng dung lượng đủ lớn để giảm tác động của cache và lặp lại ở nhiều profile phù hợp với ứng dụng.

Với workload tuần tự, có thể thử block size lớn hơn như 256 KiB hoặc 1 MiB và `--rw=read`/`--rw=write` trên file kiểm thử riêng. Không dùng kết quả từ một profile duy nhất để kết luận cho tất cả kiểu truy cập.

### Diễn giải kết quả

Nếu IOPS thấp và latency cao, có thể volume hoặc instance đã chạm giới hạn, queue quá sâu hoặc thiết bị đang tranh chấp. Nếu throughput thấp nhưng IOPS cao, block size có thể nhỏ hoặc ứng dụng phát nhiều thao tác nhỏ. Nếu CPU iowait cao, tiến trình có thể đang chờ storage; nếu CPU thấp nhưng latency ứng dụng cao, cần kiểm tra database lock, network hoặc dịch vụ phụ thuộc.

Kết quả fio đo khả năng của đường I/O trong điều kiện thử nghiệm, không phải hiệu năng chắc chắn của database. Database còn chịu ảnh hưởng của cache, transaction, fsync, concurrency, index và cấu trúc dữ liệu.

## 11. Chi phí và độ bền dữ liệu

Chi phí storage không chỉ là giá mỗi GiB/tháng. Có thể bao gồm:

- Dung lượng volume được cấp, kể cả phần chưa sử dụng.
- IOPS hoặc throughput provisioned vượt mức đi kèm dung lượng.
- Snapshot, backup, replication và dung lượng lưu trữ bản sao.
- Data transfer hoặc truy cập liên vùng nếu dịch vụ tính phí.
- Static performance reservation hoặc volume chưa detach/xóa.
- Local NVMe có thể nằm trong giá instance nhưng làm tăng giá instance family.
- File/object request, retrieval, lifecycle transition và egress theo mô hình dịch vụ.

Khi so sánh hai cấu hình, hãy tính chi phí trên một đơn vị công việc hoàn thành, chẳng hạn chi phí mỗi transaction, mỗi GB xử lý hoặc thời gian restore. Một volume đắt hơn có thể giảm thời gian batch hoặc giảm số instance cần thiết; ngược lại, provisioned IOPS quá cao có thể tạo chi phí liên tục dù workload chỉ dùng một phần.

### Durability, availability và backup

Durability là khả năng dữ liệu không bị mất; availability là khả năng truy cập dữ liệu khi cần. Một volume persistent có thể có độ bền cao theo cam kết dịch vụ nhưng vẫn không thay thế backup độc lập. Lỗi ứng dụng, mã độc, xóa nhầm, mã hóa dữ liệu hoặc lỗi cấu hình có thể được ghi xuống volume và lan sang snapshot gần nhất nếu snapshot không được bảo vệ.

Thiết kế bảo vệ dữ liệu cần xem:

- Snapshot và backup theo lịch, retention và khả năng khôi phục.
- Backup có được lưu ở tài khoản, vùng hoặc hệ thống riêng không.
- Mã hóa at rest và in transit, quyền truy cập key và quy trình rotate.
- Application-consistent backup cho database hoặc hệ thống đang ghi.
- RPO và RTO của workload.
- Thử restore định kỳ, đo thời gian và kiểm tra dữ liệu sau phục hồi.

RAID hoặc nhiều volume có thể cải thiện hiệu năng hoặc khả năng chịu lỗi ở một lớp, nhưng không thay thế backup. Snapshot trên cùng tài khoản hoặc cùng vùng cũng có thể chịu chung một số rủi ro quản trị; cần thiết kế bản sao theo mô hình đe dọa.

## 12. Quy trình chọn dung lượng và loại đĩa

1. **Phân loại dữ liệu:** xác định root, data, log, temp, cache, backup và dữ liệu có thể tái tạo.
2. **Xác định yêu cầu:** dung lượng hiện tại, tăng trưởng, retention, RPO/RTO, độ bền và mã hóa.
3. **Đo workload:** read/write mix, block size, random/sequential, IOPS, throughput, latency và queue depth.
4. **Chọn lớp storage:** general-purpose SSD, provisioned IOPS, HDD, local NVMe, file hoặc object theo kiểu truy cập và vòng đời dữ liệu.
5. **Kiểm tra hai lớp giới hạn:** volume-level IOPS/throughput và tổng giới hạn storage của instance family/size.
6. **Tính headroom:** dự phòng tăng trưởng, burst, backup staging, compaction và thao tác bảo trì.
7. **Benchmark:** thử trên volume và instance mục tiêu với profile gần production.
8. **Tính tổng chi phí:** dung lượng, hiệu năng provisioned, snapshot, backup, network và thời gian nhàn rỗi.
9. **Thiết kế bảo vệ:** encryption, backup, restore test, monitoring và cảnh báo dung lượng/I/O.
10. **Theo dõi sau triển khai:** đánh giá lại khi dữ liệu, traffic hoặc instance family thay đổi.

### Bảng quyết định nhanh

| Nhu cầu | Loại storage nên đánh giá trước | Điểm cần xác minh |
|---|---|---|
| Root disk và ứng dụng phổ thông | General-purpose SSD | Dung lượng, baseline IOPS, boot latency và chi phí |
| Database OLTP nhiều I/O nhỏ | SSD hiệu năng cao hoặc provisioned IOPS | p95/p99 latency, write IOPS, fsync và instance cap |
| Backup hoặc scan file lớn | Throughput SSD/HDD phù hợp | Throughput tuần tự, thời gian hoàn thành và retrieval cost |
| Cache có thể tái tạo | Local NVMe hoặc SSD volume | Mất dữ liệu khi host/instance thay đổi và cách warm cache |
| Dữ liệu lạnh dung lượng lớn | Cold HDD hoặc object storage | Tần suất truy cập, thời gian retrieval và chi phí lưu giữ |
| Nhiều VM cần truy cập chung file | File storage | Concurrent client, locking, metadata IOPS và throughput |
| Artifact, log archive và backup dài hạn | Object storage | Lifecycle, versioning, retention và egress |

## 13. Ví dụ thiết kế storage cho một VM database

Giả sử một VM chạy database giao dịch với dữ liệu 500 GiB, index 100 GiB và log 50 GiB. Workload tạo khoảng 9.600 IOPS ở giờ cao điểm, chủ yếu là I/O ngẫu nhiên 4–16 KiB; yêu cầu latency p95 thấp và backup mỗi ngày.

Một phương án thiết kế để thử nghiệm:

- Root volume general-purpose SSD riêng để OS và agent không tranh chấp với data.
- Data volume SSD có IOPS đủ cho tải đọc/ghi đo được, cộng headroom.
- Log volume riêng nếu benchmark chứng minh việc cô lập ghi đồng bộ giúp latency ổn định.
- Backup chuyển sang object storage hoặc dịch vụ backup, có retention và kiểm tra restore.
- Instance được chọn có tổng IOPS và throughput lớn hơn nhu cầu đồng thời của data và log.

Trước khi triển khai production, cần kiểm chứng dung lượng sau tăng trưởng, khả năng volume đạt IOPS với block size thực tế, write latency khi fsync, tổng instance-level cap, hành vi khi snapshot và thời gian restore. Nếu log volume riêng không cải thiện hiệu năng trong benchmark, có thể giảm độ phức tạp và dùng ít volume hơn.

## 14. Các lỗi sizing thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chọn disk chỉ theo dung lượng | Đủ chỗ nhưng thiếu IOPS hoặc throughput | Đo workload và chọn theo cả capacity lẫn performance |
| Nhầm IOPS với throughput | Đạt số thao tác nhưng truyền dữ liệu không đủ nhanh | Tính IOPS × block size và kiểm tra cả hai giới hạn |
| Chỉ xem giới hạn volume | VM không đạt hiệu năng cộng gộp như kỳ vọng | Kiểm tra instance-level storage cap |
| Sizing theo burst tối đa | Hiệu năng giảm khi credit cạn | Thiết kế theo baseline hoặc tải duy trì |
| Dùng local NVMe làm bản sao duy nhất | Mất dữ liệu khi host/instance thay đổi | Dùng cho dữ liệu tái tạo hoặc có replication/backup |
| Để root và data lẫn nhau | Khó thay OS, backup và kiểm soát tăng trưởng | Tách volume theo vai trò khi có lợi ích rõ ràng |
| Benchmark trên volume production | Tạo tải và có thể ghi đè dữ liệu | Dùng volume/file thử nghiệm riêng và cửa sổ kiểm thử |
| Tăng volume nhưng không mở rộng filesystem | OS vẫn thấy dung lượng cũ | Kiểm tra block device, partition và filesystem sau resize |
| Không kiểm tra restore | Backup có nhưng không khôi phục được đúng thời gian | Thử restore định kỳ và đo RTO/RPO |

## 15. Checklist trước khi đưa volume vào production

**Dung lượng và hiệu năng:**

- [ ] Đã tính data, index, log, temp, retention và tốc độ tăng trưởng.
- [ ] Đã xác định read/write mix, block size, random/sequential và concurrency.
- [ ] Đã có mục tiêu IOPS, throughput và latency p95/p99.
- [ ] Đã kiểm tra giới hạn volume và giới hạn tổng I/O của instance.
- [ ] Đã hiểu baseline, burst, credit và điều kiện throttling.
- [ ] Đã benchmark bằng workload đại diện trên volume thử nghiệm.

**Vận hành và bảo vệ dữ liệu:**

- [ ] Đã chọn persistent hoặc ephemeral đúng theo vòng đời dữ liệu.
- [ ] Đã chọn filesystem và mount ổn định theo UUID hoặc cơ chế tương đương.
- [ ] Đã bật encryption và kiểm soát quyền truy cập phù hợp.
- [ ] Đã cấu hình snapshot/backup, retention và thử restore.
- [ ] Đã có cảnh báo dung lượng, IOPS, throughput, latency và queue.
- [ ] Đã tính chi phí volume, hiệu năng provisioned, snapshot, backup và network.

## Kết luận

Chọn storage cho VM cần cân bằng dung lượng, IOPS, throughput, latency và giới hạn I/O tổng của instance. General-purpose SSD phù hợp với nhiều workload phổ thông; provisioned IOPS dành cho workload cần hiệu năng ổn định; HDD phù hợp dữ liệu lớn và truy cập tuần tự; local NVMe phù hợp cache hoặc scratch có thể tái tạo; file và object storage đáp ứng nhu cầu chia sẻ file hoặc lưu object. Hãy đo kiểu truy cập thực tế, tính tăng trưởng và headroom, kiểm tra cả giới hạn volume lẫn instance, benchmark trên môi trường riêng và đưa backup/restore vào thiết kế ngay từ đầu.

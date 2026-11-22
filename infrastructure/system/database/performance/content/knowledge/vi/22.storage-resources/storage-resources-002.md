# Đọc tuần tự, đọc ngẫu nhiên và đặc điểm thiết bị SSD

Trong chương **Lưu trữ và tài nguyên** của module **DATABASE_PERFORMANCE**, cách dữ liệu được đọc từ thiết bị lưu trữ ảnh hưởng trực tiếp đến thời gian truy vấn, throughput và độ ổn định của database. Đọc tuần tự (*sequential read*) thường truy cập các vùng dữ liệu liền kề hoặc có thể dự đoán trước; đọc ngẫu nhiên (*random read*) truy cập các vị trí phân tán. Hai kiểu truy cập tạo ra đặc điểm I/O khác nhau, nhưng mức chênh lệch phụ thuộc vào thiết bị, giao thức, kích thước request, queue depth, cache và tải đồng thời.

SSD loại bỏ độ trễ tìm kiếm cơ học của ổ đĩa quay, nhờ đó đọc ngẫu nhiên thường nhanh hơn đáng kể so với HDD. Tuy vậy, SSD không làm cho mọi kiểu I/O có chi phí như nhau. Đọc tuần tự vẫn thường đạt throughput cao hơn nhờ request lớn, read-ahead và ít overhead trên mỗi byte; đọc ngẫu nhiên vẫn có thể tạo nhiều request nhỏ, làm tăng IOPS, metadata và độ trễ đuôi. Muốn tối ưu database, cần hiểu đường đi từ câu SQL qua buffer pool, filesystem, block layer, driver và thiết bị, rồi đo đúng điểm nghẽn.

## 1. Đọc tuần tự và đọc ngẫu nhiên

### 1.1. Đọc tuần tự

Đọc tuần tự là kiểu truy cập trong đó các request thường lấy những vùng dữ liệu liên tiếp hoặc gần nhau. Ví dụ:

- Quét toàn bộ một bảng lớn để tính tổng.
- Đọc lần lượt các block của một partition theo thời gian.
- Đọc file backup hoặc file dữ liệu lớn từ đầu tới cuối.
- Đọc các page liên tiếp trong một index range scan có tính cục bộ tốt.

Khi nhận thấy ứng dụng đang đọc theo chuỗi, hệ điều hành hoặc storage stack có thể thực hiện read-ahead: đọc thêm vùng kế tiếp trước khi ứng dụng yêu cầu. Một request lớn cũng giảm số lần gửi lệnh và chi phí quản lý so với nhiều request nhỏ.

Đọc tuần tự phù hợp với scan lớn, backup, restore, ETL và một số thao tác bảo trì. Tuy nhiên, scan tuần tự vẫn có thể gây tải lớn nếu đọc quá nhiều dữ liệu hoặc cạnh tranh băng thông với giao dịch trực tuyến.

### 1.2. Đọc ngẫu nhiên

Đọc ngẫu nhiên là kiểu truy cập trong đó các request nhắm tới những vị trí không liền kề hoặc khó dự đoán. Ví dụ:

- Tra cứu một dòng qua B-tree index rồi đọc page chứa dòng đó.
- Nested-loop join thực hiện nhiều lookup vào bảng phía trong.
- Truy vấn lấy nhiều khóa phân tán trong một bảng lớn.
- Ứng dụng đọc các đối tượng nhỏ ở nhiều file hoặc block khác nhau.

Trên HDD, đầu đọc phải di chuyển tới vị trí khác trên đĩa, tạo seek time và rotational latency. Trên SSD không có đầu đọc cơ học, nên không có seek theo nghĩa cơ học. Tuy nhiên, request ngẫu nhiên vẫn có chi phí xử lý lệnh, ánh xạ địa chỉ, quản lý queue, truy cập NAND và xử lý metadata. Một lượng lớn request nhỏ có thể đạt giới hạn IOPS hoặc tạo độ trễ đuôi cao.

### 1.3. So sánh khái quát

| Đặc điểm | Đọc tuần tự | Đọc ngẫu nhiên |
|---|---|---|
| Mẫu truy cập | Vùng liền kề hoặc có thể dự đoán | Nhiều vùng phân tán |
| Kích thước request thường gặp | Có thể lớn và gộp được | Thường nhỏ hơn, nhiều request riêng |
| Tận dụng read-ahead | Thường tốt | Khó dự đoán hơn |
| Throughput | Thường cao khi truyền lượng dữ liệu lớn | Có thể bị giới hạn bởi IOPS và overhead request |
| Độ trễ mỗi request | Có thể thấp khi request lớn và queue phù hợp | Phụ thuộc IOPS, queue, locality và thiết bị |
| Ví dụ database | Table scan, backup, sequential range | Point lookup, index lookup, random page fetch |

Đây là xu hướng chung, không phải quy luật tuyệt đối. SSD enterprise, NVMe, controller, filesystem, RAID, cloud volume và kích thước block có thể làm kết quả thay đổi đáng kể. Cần benchmark theo kích thước I/O và tỷ lệ đọc/ghi của workload thật.

## 2. Các chỉ số cần hiểu khi đánh giá storage

### 2.1. Latency

Latency là thời gian hoàn tất một yêu cầu I/O. Với database, độ trễ quan trọng ở cả mức trung bình và phân vị cao:

- **Average latency:** hữu ích để theo dõi xu hướng tổng thể, nhưng có thể che khuất một số request rất chậm.
- **p50:** độ trễ trung vị; một nửa request hoàn tất không lâu hơn giá trị này.
- **p95/p99:** phản ánh các request chậm ở phần đuôi phân bố, thường ảnh hưởng trực tiếp tới truy vấn có nhiều I/O hoặc yêu cầu SLA.
- **Maximum latency:** có thể giúp tìm spike, nhưng nhạy với outlier và thời gian đo.

Nếu một truy vấn cần đọc hàng trăm page, chỉ một số lần I/O chậm cũng có thể kéo dài thời gian hoàn tất. Vì vậy, p95/p99 của storage có thể quan trọng hơn average khi điều tra timeout hoặc latency không ổn định.

### 2.2. IOPS

IOPS (*Input/Output Operations Per Second*) là số thao tác đọc/ghi hoàn tất trong một giây. IOPS phụ thuộc:

- Kích thước mỗi request, ví dụ 4 KiB, 8 KiB hoặc 64 KiB.
- Tỷ lệ đọc/ghi.
- Random hay sequential.
- Queue depth và số worker.
- Read/write cache, controller và firmware.
- Mức song song của thiết bị và giới hạn của tầng lưu trữ.

Không thể so sánh hai con số IOPS nếu workload có block size, queue depth và read/write mix khác nhau. Thiết bị đạt IOPS cao ở random read 4 KiB có thể có kết quả khác khi chạy random write hoặc request 64 KiB.

### 2.3. Throughput

Throughput là lượng dữ liệu truyền trong một đơn vị thời gian, thường tính bằng MB/s hoặc GB/s. Có thể ước lượng:

\[
Throughput \approx IOPS \times BlockSize
\]

Ví dụ, 50.000 IOPS với block 8 KiB tương ứng khoảng 390 MiB/s theo phép nhân lý tưởng. Kết quả thực tế có thể thấp hơn do protocol overhead, queueing, filesystem, giới hạn thiết bị và cách quy đổi MB/MiB.

Đọc tuần tự thường tận dụng request lớn nên có thể đạt throughput cao mà không cần IOPS quá lớn. Đọc ngẫu nhiên request nhỏ có thể đạt IOPS cao nhưng throughput không tương ứng với một luồng truyền tuần tự.

### 2.4. Queue depth và thời gian chờ

Queue depth là số request I/O đang chờ hoặc đang được xử lý đồng thời ở một tầng. Tăng queue depth có thể giúp thiết bị khai thác song song tốt hơn, nhất là NVMe. Nhưng queue quá sâu có thể làm request chờ lâu hơn, tăng p95/p99 và gây tranh chấp với workload khác.

Định luật Little có thể giúp hình dung quan hệ giữa số request đang xử lý, throughput và latency:

\[
Q \approx IOPS \times Latency_{seconds}
\]

Ví dụ, nếu workload hoàn tất 20.000 IOPS với latency trung bình 1 ms, số request đang xử lý trung bình xấp xỉ 20. Đây chỉ là ước lượng cho hệ thống ổn định và cùng một điểm đo; không nên dùng để suy ra queue depth tối ưu một cách máy móc.

### 2.5. Kích thước I/O

Database thường đọc/ghi theo page có kích thước do engine quy định, trong khi filesystem và thiết bị có thể xử lý request theo đơn vị khác. Ví dụ, một page database 8 KiB có thể được ghép với các page liền kề thành request lớn hơn, hoặc bị tách thành nhiều thao tác ở tầng dưới.

Hãy phân biệt:

- **Database page/block:** đơn vị quản lý dữ liệu logic của engine.
- **Filesystem block:** đơn vị cấp phát hoặc truy cập của filesystem.
- **Device logical/physical sector:** đơn vị địa chỉ hóa hoặc ghi vật lý mà thiết bị công bố.
- **I/O request size:** kích thước request thực tế gửi qua storage stack.

Không giả định một page database luôn tương ứng một thao tác vật lý duy nhất. Cache, read-ahead, coalescing, splitting và controller có thể thay đổi hình dạng I/O.

## 3. Đặc điểm của SSD

SSD lưu dữ liệu trên bộ nhớ flash NAND và dùng controller để ánh xạ địa chỉ logic sang vị trí vật lý. Khác với HDD, SSD không có đĩa quay và đầu đọc cơ học. Điều này làm giảm mạnh độ trễ truy cập ngẫu nhiên, nhưng kiến trúc flash có những giới hạn riêng.

### 3.1. Page, block và chu kỳ ghi/xóa NAND

NAND flash thường đọc và lập trình dữ liệu theo page, nhưng xóa theo erase block chứa nhiều page. Khi một page đã được lập trình, thiết bị không thể tùy ý ghi đè tại chỗ như cách ứng dụng hình dung. Controller phải quản lý vị trí mới, đánh dấu dữ liệu cũ không còn hợp lệ và có thể gom các page còn hiệu lực sang block khác trước khi xóa block cũ.

Điều này dẫn tới khác biệt quan trọng:

- Đọc NAND thường không cần xóa block trước.
- Ghi mới cần lập trình page trống theo quy tắc của flash.
- Xóa diễn ra ở đơn vị block lớn hơn page.
- Cập nhật nhỏ có thể tạo công việc nội bộ lớn hơn lượng dữ liệu ứng dụng ghi.

Chi tiết page/block và cách controller thực hiện phụ thuộc loại NAND, firmware và thiết kế thiết bị.

### 3.2. Flash Translation Layer (FTL)

FTL ánh xạ địa chỉ logic mà hệ điều hành/database sử dụng sang vị trí vật lý trong NAND. Khi ứng dụng ghi vào một địa chỉ logic, controller có thể ghi dữ liệu vào vị trí flash khác, cập nhật mapping và đánh dấu page cũ là invalid.

FTL giúp thiết bị che giấu đặc tính erase-before-write và phân bổ ghi trên nhiều block. Vì ánh xạ thay đổi theo thời gian, một chuỗi ghi logic liên tiếp không nhất thiết luôn nằm ở các vị trí vật lý cố định. Controller và firmware quyết định cách gom, phân bổ và thu hồi block.

### 3.3. Garbage collection

Khi một erase block chứa cả page còn hợp lệ và page đã invalid, controller có thể phải đọc/copy các page còn hợp lệ sang nơi khác, sau đó xóa block để tái sử dụng. Quá trình này gọi là garbage collection (GC).

GC có thể làm tăng lượng I/O nội bộ và cạnh tranh với request của host. Khi thiết bị ít không gian trống, tải ghi ngẫu nhiên cao hoặc vừa trải qua workload ghi lớn, GC có thể góp phần làm tăng write latency và độ trễ đuôi.

Một số SSD có vùng dự phòng và cơ chế GC nền để giảm tác động. Tuy nhiên, benchmark ngắn trên thiết bị mới hoặc vừa xóa sạch có thể không phản ánh hiệu năng sau thời gian ghi dài. Cần thử nghiệm đủ lâu để trạng thái thiết bị gần với vận hành thực tế.

### 3.4. Wear leveling và endurance

Mỗi ô NAND có giới hạn số chu kỳ program/erase. Wear leveling phân phối công việc ghi trên nhiều block để tránh một vùng bị sử dụng quá mức. Thiết bị thường dùng over-provisioning, ECC và các cơ chế quản lý lỗi để duy trì độ bền và tính toàn vẹn.

Thông số endurance thường được biểu diễn bằng TBW (*Terabytes Written*) hoặc DWPD (*Drive Writes Per Day*). DWPD mô tả số lần ghi tương đương toàn bộ dung lượng thiết bị mỗi ngày trong thời hạn bảo hành được công bố. Đây là chỉ số định hướng lựa chọn thiết bị; workload thực tế còn phụ thuộc write amplification, nhiệt độ, firmware và điều kiện vận hành.

Database có thể tạo nhiều ghi hơn lượng dữ liệu nghiệp vụ do WAL/redo, checkpoint, index, temp file, vacuum/purge và thao tác cập nhật. Khi chọn SSD cho database, cần ước lượng tổng host writes và theo dõi SMART/NVMe health metrics theo chính sách nhà cung cấp.

## 4. Vì sao SSD vẫn phân biệt đọc tuần tự và đọc ngẫu nhiên?

SSD giảm mạnh chi phí tìm vị trí cơ học, nhưng sequential và random I/O vẫn khác nhau ở nhiều tầng:

1. **Kích thước request:** scan tuần tự thường có thể gửi request lớn hơn, còn point lookup có thể tạo nhiều request nhỏ.
2. **Read-ahead và coalescing:** hệ điều hành/database có thể gộp hoặc dự đoán request tuần tự; request ngẫu nhiên khó gộp hơn.
3. **Độ sâu queue:** nhiều request độc lập có thể khai thác song song, nhưng queue sâu cũng làm tăng thời gian chờ.
4. **Controller và FTL:** ánh xạ logic, ECC, metadata và phân bổ page vẫn tiêu tốn công việc cho từng request.
5. **Locality và cache:** dữ liệu liền kề có thể tận dụng page cache và buffer pool tốt hơn; truy cập ngẫu nhiên có thể gây cache miss phân tán.
6. **Phần mềm:** filesystem, driver, protocol và database engine có overhead trên mỗi request.

Vì vậy, SSD không khiến chỉ mục trở nên vô dụng. Index vẫn giảm số page cần đọc khi truy vấn có tính chọn lọc cao. Ngược lại, nếu truy vấn cần phần lớn bảng, sequential scan có thể nhanh hơn nhiều random lookup. Hãy so sánh số page, request size, IOPS, throughput và CPU trên workload thật.

## 5. NVMe và giao thức truy cập SSD

SATA SSD và NVMe SSD đều dùng NAND flash, nhưng giao thức và khả năng song song khác nhau.

| Đặc điểm | SATA/AHCI SSD | NVMe SSD |
|---|---|---|
| Giao tiếp phổ biến | SATA | PCI Express |
| Mô hình queue | Số queue và độ sâu giới hạn hơn | Nhiều submission/completion queue, hỗ trợ song song cao |
| Overhead giao thức | AHCI/SATA | NVMe được thiết kế cho bộ nhớ không bay hơi qua PCIe |
| Throughput tiềm năng | Bị giới hạn bởi băng thông SATA | Có thể cao hơn nhờ nhiều lane PCIe và thế hệ giao tiếp |
| Đặc điểm workload | Tốt cho nhiều workload phổ thông | Hữu ích với I/O song song, queue depth cao và throughput lớn |

Không nên chỉ nhìn nhãn NVMe để kết luận thiết bị sẽ cải thiện database. Cần xem controller, loại NAND, firmware, endurance, power-loss protection, latency ở queue depth thấp, hiệu năng sustained write và giới hạn của nền tảng. Một NVMe consumer có thể có đặc tính ghi bền vững khác đáng kể so với SSD enterprise có bảo vệ mất điện và endurance cao.

### 5.1. Queue song song của NVMe

NVMe hỗ trợ nhiều queue để nhiều CPU/core có thể gửi request đồng thời. Điều này giảm một số điểm tranh chấp trong đường I/O và giúp thiết bị khai thác song song nội bộ. Tuy nhiên, ứng dụng vẫn phải tạo đủ I/O độc lập để tận dụng khả năng đó.

Một truy vấn phụ thuộc tuần tự vào kết quả của request trước có thể không tạo đủ queue depth. Ngược lại, nhiều worker cùng scan hoặc nhiều truy vấn ngẫu nhiên có thể tạo queue sâu, tăng throughput nhưng cũng làm p99 tăng. Hãy tìm điểm cân bằng theo SLO và workload.

### 5.2. Độ trễ ở queue depth thấp

Database OLTP thường quan tâm latency của một số request nhỏ và flush log, đặc biệt khi transaction commit phải chờ durability. Một thiết bị có throughput tuần tự cao ở queue depth lớn không nhất thiết có latency thấp ở queue depth 1 hoặc 2.

Khi chọn storage cho OLTP, hãy xem latency random read/write ở queue depth thấp, p99, flush/FUA behavior, power-loss protection và độ ổn định khi thiết bị đã ghi lâu. Với data warehouse, throughput scan và khả năng xử lý nhiều request lớn có thể quan trọng hơn.

## 6. Các đặc tính SSD ảnh hưởng tới database

### 6.1. Read latency và random read

B-tree lookup có thể yêu cầu đọc một số page ở các tầng index và page dữ liệu. Nếu cache miss, mỗi lần đọc phải đi qua storage stack. SSD giúp giảm latency so với HDD, nhưng hàng loạt lookup nhỏ vẫn tiêu thụ IOPS và tạo queue.

Tối ưu bằng cách giảm số lần truy cập dữ liệu không cần thiết:

- Chọn index đúng thứ tự cột và độ chọn lọc.
- Dùng covering index khi lợi ích lớn hơn chi phí duy trì.
- Tránh nested-loop lookup lặp quá nhiều lần nếu join strategy khác phù hợp hơn.
- Giảm số cột và số dòng cần đọc.
- Giữ working set quan trọng trong buffer pool khi đủ memory.

### 6.2. Sequential scan và read-ahead

Table scan hoặc index scan lớn có thể tạo luồng đọc liên tiếp. Database engine có thể đọc ahead hoặc dùng nhiều worker để tăng throughput. SSD giúp scan nhanh nhưng scan toàn bộ bảng vẫn tiêu thụ băng thông và có thể đẩy page hữu ích khỏi cache.

Đánh giá scan bằng tổng page đọc, MB/s, CPU lọc, số worker và ảnh hưởng tới query khác. Một scan có elapsed thấp nhưng chiếm gần hết băng thông storage trong thời gian dài có thể làm OLTP chậm đi.

### 6.3. Random write và write amplification

Random write ở tầng database có thể tạo cập nhật nhiều page khác nhau: heap/data page, index page, visibility metadata, undo hoặc WAL/redo. Ở tầng SSD, FTL và GC có thể phải di chuyển dữ liệu để xóa block và tái sử dụng.

Write amplification (*WAF*) là tỷ lệ giữa lượng dữ liệu thiết bị thực sự ghi vào NAND và lượng dữ liệu host gửi xuống. Ví dụ, host gửi 100 GB nhưng thiết bị ghi 180 GB vào NAND thì WAF xấp xỉ 1,8 trong phạm vi đo tương ứng. WAF phụ thuộc workload, trạng thái thiết bị, over-provisioning và firmware; không nên dùng một con số cố định cho mọi SSD.

Để giảm lượng ghi không cần thiết:

- Tránh cập nhật cùng dòng nhiều lần nếu có thể gộp thay đổi.
- Loại bỏ index không được sử dụng nhưng vẫn phải duy trì khi ghi.
- Chọn batch size hợp lý để giảm overhead mà không tạo transaction quá lớn.
- Tránh ghi lại giá trị không thay đổi nếu semantics cho phép.
- Tách temp/scratch workload khỏi thiết bị đang chịu tải commit quan trọng khi kiến trúc hỗ trợ.
- Theo dõi WAL/redo, log flush, checkpoint và dung lượng ghi thực tế.

### 6.4. TRIM và discard

Khi database hoặc filesystem xóa dữ liệu, SSD không nhất thiết biết ngay các block logic đó không còn cần thiết. TRIM/discard cho phép tầng trên thông báo các logical block đã được giải phóng để controller có thể quản lý không gian hiệu quả hơn.

TRIM không xóa dữ liệu theo nghĩa ứng dụng có thể kiểm tra trực tiếp và cũng không phải thao tác thu hồi tức thời cho mọi block. Cách hỗ trợ phụ thuộc filesystem, driver, RAID/controller, hypervisor và storage backend. Kiểm tra cấu hình discard theo nền tảng; không bật tùy tiện trên stack không hỗ trợ đúng.

### 6.5. Power-loss protection và durability

Database thường dựa vào transaction log và thao tác flush để bảo đảm dữ liệu đã commit có thể phục hồi sau sự cố. SSD enterprise có thể có tụ điện hoặc cơ chế power-loss protection để bảo vệ dữ liệu đang nằm trong cache thiết bị khi mất điện đột ngột. SSD consumer có thể có chính sách cache và bảo vệ khác.

Không tắt `fsync`, write barrier, flush hoặc durability setting chỉ để tăng benchmark nếu database cần bảo đảm commit bền vững. Thiết bị và tầng RAID/hypervisor phải thực hiện đúng semantics flush/FUA mà hệ điều hành gửi. Một thiết bị báo hoàn tất ghi trước khi dữ liệu được bảo vệ có thể làm suy yếu bảo đảm durability.

## 7. Ảnh hưởng của SSD tới các đường I/O trong database

Database thường có nhiều loại I/O với mẫu truy cập khác nhau:

| Thành phần | Mẫu I/O thường gặp | Điều cần quan sát |
|---|---|---|
| Data page lookup | Random read khi cache miss | IOPS, latency, cache hit, số lookup |
| Table/index scan | Sequential hoặc range read, có thể song song | Throughput, read-ahead, page count, cạnh tranh băng thông |
| Transaction log/WAL/redo | Ghi tuần tự, flush theo commit hoặc group commit | Flush latency, fsync latency, log throughput |
| Checkpoint | Ghi nhiều dirty page, có thể phân tán | Write throughput, checkpoint duration, write burst |
| Temp/sort/hash spill | Đọc/ghi vùng tạm, thường có thể lớn | Temp I/O, spill size, memory grant/work_mem |
| Backup/restore | Đọc hoặc ghi tuần tự khối lượng lớn | MB/s, compression CPU, ảnh hưởng workload online |
| Vacuum/purge/rebuild | Đọc/ghi và cập nhật nhiều page/index | I/O mix, lock, thời gian bảo trì và bloat |

### 7.1. Tách log và data trên các thiết bị khác nhau

Một số hệ thống đặt transaction log và data file trên các volume khác nhau để giảm cạnh tranh. Log thường nhạy với latency flush tuần tự; data workload có thể chứa nhiều random read/write và scan. Tách volume có thể giúp nếu hai workload thực sự cạnh tranh trên cùng thiết bị hoặc queue.

Tuy nhiên, nếu hai volume nằm trên cùng một physical SSD, cùng RAID group, cùng SAN pool hoặc cùng cloud storage backend, việc tách đường dẫn không bảo đảm tách tài nguyên. Cần kiểm tra topology vật lý/ảo hóa và metric ở backend. Tách volume còn tăng chi phí vận hành, dung lượng và cấu hình backup; hãy làm khi đo đạc cho thấy có lợi.

### 7.2. Log flush và group commit

Trong workload OLTP, transaction commit có thể phải chờ log được flush bền vững. Nếu mỗi transaction gây một lần flush riêng, latency của log device ảnh hưởng trực tiếp tới commit latency. Group commit cho phép nhiều transaction cùng hưởng một lần flush trong điều kiện engine hỗ trợ.

Tối ưu cần xem:

- Log flush latency và p95/p99.
- Số lần flush trên số transaction commit.
- Kích thước log record và throughput ghi.
- Group commit, commit batching và concurrency.
- Thiết bị có power-loss protection và semantics flush chính xác không.

Không gom transaction tùy tiện nếu điều đó làm thay đổi thời điểm commit hoặc tính nguyên tử mà ứng dụng yêu cầu. Hãy đo commit latency cùng throughput và lỗi durability.

### 7.3. Checkpoint và write burst

Checkpoint ghi các dirty page xuống storage để giới hạn lượng công việc phục hồi. Nếu quá nhiều dirty page được ghi trong thời gian ngắn, storage có thể gặp write burst và latency của workload khác tăng. Một SSD có throughput ghi đỉnh cao nhưng sustained write thấp có thể thể hiện khác biệt sau khi cache ghi nội bộ đầy.

Quan sát checkpoint duration, dirty page, write throughput, log generation, flush latency và p99 của truy vấn trong cùng thời điểm. Cấu hình checkpoint cần cân bằng thời gian phục hồi, write smoothing và tài nguyên storage.

## 8. Cache, buffer pool và giới hạn của phép đo thiết bị

Một truy vấn database có thể không phát sinh I/O vật lý cho mọi lần đọc. Dữ liệu có thể đã nằm trong buffer pool của database hoặc page cache của hệ điều hành. Vì vậy, thời gian query không thể được suy ra trực tiếp từ tốc độ SSD.

### 8.1. Buffer pool

Database giữ các page được truy cập thường xuyên trong memory. Nếu buffer pool hit, truy vấn có thể đọc page mà không gửi request tới thiết bị. Một workload random read có thể chạy nhanh nếu working set nằm trong RAM; khi working set vượt memory, cache miss tăng và random I/O xuất hiện.

Hãy theo dõi buffer cache hit, physical read, page read latency và kích thước working set. Cache hit ratio cao không luôn có nghĩa hệ thống khỏe nếu truy vấn đọc quá nhiều dữ liệu hoặc chỉ số hit bị tổng hợp trên workload không đại diện.

### 8.2. Page cache của hệ điều hành

Một số engine dùng direct I/O hoặc quản lý cache riêng; engine khác có thể dựa vào filesystem/page cache. Một request database được ghi nhận là physical read ở engine chưa chắc tương ứng một lần đọc từ NAND vì dữ liệu có thể được phục vụ từ page cache của OS hoặc cache controller.

Để xác định bottleneck, cần so sánh số liệu ở database, OS và storage. Không cộng trực tiếp các bộ đếm ở nhiều tầng vì chúng có thể đếm cùng một request ở những giai đoạn khác nhau.

### 8.3. Cold cache và warm cache

Warm-cache benchmark đo workload khi dữ liệu đã được nạp vào cache; cold-cache benchmark đo khi phần lớn working set chưa có trong cache. Hai tình huống trả lời hai câu hỏi khác nhau.

Không xóa cache production để tạo cold-cache test nếu chưa có kế hoạch được kiểm soát. Có thể dùng môi trường thử nghiệm hoặc dataset lớn hơn memory. Ghi rõ cache state, thời gian warm-up và cách reset để kết quả có thể so sánh.

## 9. Storage cục bộ, SAN và cloud block storage

SSD có thể được cung cấp trực tiếp qua SATA/NVMe, qua RAID controller, SAN, hypervisor hoặc dịch vụ block storage trên cloud. Đường đi càng nhiều tầng thì càng cần đo đúng vị trí.

### 9.1. SSD cục bộ

SSD local NVMe có thể cung cấp latency thấp và throughput cao, nhưng cần xem thiết bị có dùng chung với workload khác, nhiệt độ, firmware, endurance và khả năng bảo vệ mất điện. Một số thiết bị giảm hiệu năng khi quá nóng hoặc sau khi cache ghi nội bộ đầy.

### 9.2. SAN và storage mạng

SAN có thể cung cấp nhiều lớp cache, controller, multipath và shared pool. Độ trễ không chỉ do SSD backend mà còn do network, fabric, controller queue, cache policy và mức cạnh tranh giữa host. Khi latency tăng, cần đối chiếu metric host với metric array và đường mạng.

### 9.3. Cloud block volume

Cloud volume có thể giới hạn IOPS và throughput theo loại volume, dung lượng, cấu hình provisioned hoặc cơ chế burst/credit. Một workload có thể đạt tốc độ cao lúc đầu rồi giảm khi hết burst credit hoặc chạm giới hạn throughput. Một số nền tảng còn áp dụng giới hạn ở cấp instance, volume hoặc tổng băng thông.

Khi benchmark cloud storage, ghi rõ loại volume, kích thước, provisioned IOPS/throughput, instance limit, cache, vùng triển khai và thời gian chạy. Không suy luận tốc độ chỉ từ nhãn SSD hoặc NVMe của backend.

## 10. Đo I/O trên hệ điều hành và thiết bị

### 10.1. Linux: iostat

`iostat` từ gói sysstat cung cấp số liệu hoạt động thiết bị:

```bash
iostat -x 1
```

Các trường thường cần đọc gồm:

- `r/s`, `w/s`: số request đọc/ghi mỗi giây.
- `rkB/s`, `wkB/s`: throughput đọc/ghi.
- `r_await`, `w_await`: thời gian chờ trung bình của request đọc/ghi, thường tính bằng millisecond.
- `aqu-sz`: độ dài hàng đợi trung bình theo cách công cụ định nghĩa.
- `rareq-sz`, `wareq-sz`: kích thước request đọc/ghi trung bình.
- `%util`: tỷ lệ thời gian thiết bị được coi là bận trong khoảng đo.

Với NVMe và thiết bị có nhiều queue song song, `%util` gần 100% không phải lúc nào cũng chứng minh thiết bị đã đạt giới hạn throughput hoặc IOPS. Cần đọc cùng latency, queue, throughput và giới hạn thiết bị. Trên Linux mới, tên trường hoặc đơn vị có thể thay đổi theo phiên bản sysstat.

### 10.2. Linux: thông tin NVMe

Với thiết bị NVMe và công cụ `nvme-cli`, có thể xem health log:

```bash
sudo nvme smart-log /dev/nvme0
```

Các trường có thể gồm temperature, available spare, percentage used, data units read/written, media errors và warning. Tên namespace/device cần xác định đúng trên máy. Không chạy lệnh thay đổi firmware hoặc format namespace khi chỉ cần đọc metric.

### 10.3. Windows: Performance Monitor

Trên Windows, có thể theo dõi các counter liên quan tới physical disk hoặc logical disk:

- `Avg. Disk sec/Read` và `Avg. Disk sec/Write`: thời gian phục vụ I/O trung bình.
- `Disk Reads/sec` và `Disk Writes/sec`: số thao tác mỗi giây.
- `Disk Read Bytes/sec` và `Disk Write Bytes/sec`: throughput.
- `Avg. Disk Queue Length`: số request trung bình trong hàng đợi.
- `Current Disk Queue Length`: số request đang chờ/được xử lý tại thời điểm lấy mẫu.

Đọc counter ở đúng instance volume/device và cùng khoảng thời gian với metric database. Một volume ảo có thể ánh xạ tới storage backend dùng chung; counter ở guest OS không luôn cho thấy giới hạn cuối cùng của backend.

### 10.4. Đo ở tầng database

Đối chiếu các chỉ số storage với:

- Logical reads và physical reads theo query.
- Buffer pool hit/miss và page read latency.
- Wait events liên quan I/O, log flush, checkpoint và temp file.
- Số page được scan, số lần lookup và số dòng thực tế.
- Query latency p50/p95/p99 và throughput giao dịch.

Nếu OS cho thấy thiết bị không bận nhưng database có wait I/O cao, có thể bottleneck nằm ở volume khác, network storage, filesystem, queue mapping hoặc metric chưa quan sát đúng thiết bị. Nếu thiết bị bận nhưng database query không chậm, có thể I/O đó thuộc workload khác hoặc cache đang che tác động.

## 11. Benchmark sequential và random I/O an toàn

Benchmark cần phản ánh workload thực tế. Không chạy thử trực tiếp trên block device đang chứa dữ liệu database. Công cụ như `fio` có thể ghi đè dữ liệu nếu trỏ nhầm thiết bị hoặc file đang dùng.

### 11.1. Chuẩn bị phép thử

- Dùng máy hoặc volume thử nghiệm riêng, không chạy trên volume production đang phục vụ database.
- Tạo thư mục scratch có đủ dung lượng và quyền truy cập.
- Dùng file thử nghiệm có thể xóa bỏ; không dùng tên file dữ liệu thật.
- Xác định block size, read/write mix, queue depth, số job và thời gian chạy.
- Chạy đủ lâu để thấy hiệu năng sustained, không chỉ burst cache.
- Đo trước và sau, ghi firmware, loại volume, filesystem và cache state.

### 11.2. Ví dụ fio đọc tuần tự

Ví dụ dưới đây giả định file thử nghiệm đã được tạo và chứa dữ liệu không quan trọng:

```bash
fio --name=seqread \
    --filename=/mnt/bench/disposable-test.dat \
    --size=4G \
    --rw=read \
    --bs=128k \
    --iodepth=16 \
    --numjobs=1 \
    --direct=1 \
    --runtime=60 \
    --time_based \
    --group_reporting
```

Phép thử này đo sequential read với block 128 KiB và queue depth 16 trong 60 giây, theo cấu hình fio. `direct=1` yêu cầu direct I/O khi nền tảng hỗ trợ; nó không bảo đảm mọi tầng cache của thiết bị hoặc storage backend đều bị bỏ qua.

### 11.3. Ví dụ fio đọc ngẫu nhiên

```bash
fio --name=randread \
    --filename=/mnt/bench/disposable-test.dat \
    --size=4G \
    --rw=randread \
    --bs=4k \
    --iodepth=32 \
    --numjobs=4 \
    --direct=1 \
    --runtime=60 \
    --time_based \
    --group_reporting
```

Phép thử này tạo random read 4 KiB với nhiều job và queue depth cao hơn. Kết quả sẽ khác phép sequential read vì block size, queue depth và số job đều thay đổi. Để so sánh công bằng, hãy thay từng biến một hoặc xây ma trận thử có kiểm soát.

### 11.4. Không benchmark phá hủy trên thiết bị đang dùng

Không đặt `--filename` thành `/dev/nvme0n1`, volume dữ liệu database hoặc file đang được ứng dụng sử dụng. Các chế độ ghi như `write`, `randwrite`, `rw` có thể ghi đè dữ liệu. Nếu cần benchmark write, chỉ dùng file scratch mới trên volume thử nghiệm, kiểm tra đường dẫn và quyền trước khi chạy. Không chạy lệnh format, sanitize, secure erase hoặc firmware update như một phần của phép đo thông thường.

## 12. Diễn giải kết quả benchmark

Một kết quả benchmark nên bao gồm:

| Thông tin | Vì sao cần |
|---|---|
| Workload read/write mix | Random read khác random write và mixed workload |
| Block size | 4 KiB và 128 KiB tạo IOPS/throughput khác nhau |
| Queue depth và job count | Thể hiện mức song song và tải gửi tới thiết bị |
| Runtime và trạng thái thiết bị | Phát hiện burst cache, thermal throttling và sustained behavior |
| IOPS và MB/s | Đánh giá số request và lượng dữ liệu |
| p50/p95/p99 latency | Đánh giá trải nghiệm và tail latency |
| CPU utilization | Xác định driver, protocol hoặc generator có giới hạn không |
| Cache/direct I/O | Hiểu dữ liệu được phục vụ từ đâu |
| Thiết bị/backend limit | Đối chiếu với spec và giới hạn cloud/array/instance |

### 12.1. So sánh đúng điều kiện

Không so sánh sequential 128 KiB queue depth 16 với random 4 KiB queue depth 1 rồi kết luận khác biệt chỉ do tính tuần tự/ngẫu nhiên. Hãy giữ block size, concurrency và cache state giống nhau khi cô lập một yếu tố; sau đó chạy thêm workload đại diện cho database.

### 12.2. Nhìn vào tail latency

Thiết bị có throughput trung bình cao nhưng thỉnh thoảng có request rất chậm có thể làm truy vấn nhiều page tăng p99. GC, checkpoint, cache flush, thermal throttling, firmware và tranh chấp backend có thể tạo spike. Benchmark phải đủ dài và có phân phối latency, không chỉ báo một average.

### 12.3. Tránh kết luận từ một lần chạy

Chạy lặp lại trong cùng điều kiện, ghi độ biến động và loại bỏ lần chạy bị ảnh hưởng bởi tác vụ nền không đại diện. Nếu kết quả thay đổi mạnh giữa các lần, điều tra cache, nhiệt độ, background GC, cloud burst credits và workload cạnh tranh trước khi chọn thiết bị.

## 13. Áp dụng vào tối ưu database

### 13.1. Truy vấn point lookup chậm

Nếu truy vấn tìm một dòng qua index nhưng physical read latency cao:

1. Kiểm tra buffer pool hit và số page thực sự cần đọc.
2. Xem index có phù hợp với predicate và thứ tự cột không.
3. Kiểm tra random lookup lặp trong nested loop hoặc key lookup quá nhiều.
4. Xem working set có vượt RAM hoặc cache không.
5. Đối chiếu random read IOPS và p95/p99 storage latency.
6. Đánh giá covering index, join strategy hoặc giảm số dòng truy cập.

Không thêm index ngay nếu bottleneck thực tế là CPU, lock hoặc network. SSD nhanh hơn có thể giảm thời gian I/O nhưng không sửa một plan đọc hàng triệu page không cần thiết.

### 13.2. Table scan chậm

Nếu scan lớn bị giới hạn bởi storage:

- Kiểm tra page count, read-ahead, request size và throughput.
- Xem có thể partition pruning hoặc lọc sớm để giảm vùng scan không.
- Xem query có đọc thừa cột hoặc thực hiện sort/hash spill không.
- Đánh giá parallel scan và tác động tới workload OLTP.
- Cân nhắc columnstore hoặc summary nếu truy vấn phân tích lặp lại.

Sequential throughput cao không có nghĩa scan toàn bộ luôn đúng. Giảm lượng dữ liệu phải đọc thường có lợi hơn chỉ nâng tốc độ thiết bị.

### 13.3. Commit chậm

Nếu transaction commit chậm và database chờ log flush:

- Đo write latency của volume log, đặc biệt p95/p99.
- Kiểm tra log flush frequency, group commit và kích thước log record.
- Xác minh storage có power-loss protection và thực hiện đúng flush semantics.
- Kiểm tra volume có dùng chung backend với scan/checkpoint hoặc workload khác không.
- Đo replication và log shipping nếu chúng nằm trên đường xác nhận commit.

Không tắt durability để giảm latency. Có thể tối ưu batch/transaction và thiết kế log storage phù hợp nhưng phải giữ yêu cầu phục hồi sau crash.

### 13.4. Checkpoint hoặc batch write gây spike

Nếu latency tăng theo chu kỳ checkpoint hoặc ETL:

- Đối chiếu thời điểm spike với write throughput và queue.
- Xem sustained write của SSD sau khi cache ghi đầy.
- Kiểm tra checkpoint pacing, batch size và lịch ETL.
- Giảm cạnh tranh bằng cách điều chỉnh lịch hoặc tách storage khi topology thực sự độc lập.
- Theo dõi log, dirty pages, I/O wait và p99 của truy vấn cùng thời điểm.

## 14. Quy trình điều tra bottleneck storage

1. **Xác định triệu chứng:** query chậm, commit chậm, timeout, throughput giảm hay latency đuôi tăng.
2. **Đọc execution plan:** xác định truy vấn tạo random lookup, scan lớn, sort/hash spill hoặc ghi nhiều page.
3. **Đo ở database:** logical/physical reads, buffer hit, wait events, log flush, checkpoint và temp I/O.
4. **Đo ở OS:** IOPS, MB/s, request size, read/write await, queue và device utilization.
5. **Đo ở backend:** NVMe health, SAN/controller queue hoặc cloud volume limits/credits.
6. **Phân loại mẫu I/O:** sequential/random, read/write, block size và concurrency.
7. **Kiểm tra cache:** buffer pool, OS page cache, controller cache và warm/cold state.
8. **Kiểm tra sustained behavior:** GC, thermal throttling, write cache, wear và background tasks.
9. **Đưa ra giả thuyết:** giảm page, giảm random lookup, tăng throughput scan, cải thiện log latency hoặc giảm cạnh tranh.
10. **Thử một thay đổi có kiểm soát:** giữ nguyên workload và đo trước/sau.
11. **Xác minh workload tổng thể:** p95/p99, throughput, durability, replication và chi phí vận hành.

## 15. Những sai lầm thường gặp

- **Cho rằng SSD làm random I/O miễn phí:** request nhỏ vẫn tiêu thụ IOPS và có thể tạo queue/tail latency.
- **Chỉ nhìn MB/s:** OLTP có thể bị giới hạn bởi latency và IOPS chứ không phải throughput tuần tự.
- **Chỉ nhìn IOPS:** không ghi block size, queue depth và read/write mix nên không thể so sánh công bằng.
- **Cho rằng queue depth càng cao càng tốt:** queue quá sâu có thể làm latency tăng và ảnh hưởng request khác.
- **Dùng benchmark burst làm năng lực sustained:** cache ghi, GC và thermal throttling có thể làm kết quả dài hạn khác.
- **Đồng nhất database page với physical I/O:** cache, coalescing và filesystem làm thay đổi request ở tầng dưới.
- **Coi `%util` gần 100% là bằng chứng duy nhất thiết bị bão hòa:** đặc biệt không đủ với NVMe và storage song song.
- **Tách log/data bằng hai volume nhưng cùng backend:** đường dẫn khác không đồng nghĩa tài nguyên vật lý độc lập.
- **Tắt fsync/flush để benchmark:** kết quả không còn đại diện cho durability production.
- **Chạy fio ghi lên thiết bị thật:** có thể phá hủy dữ liệu và làm gián đoạn database.
- **Nâng cấp SSD trước khi xem plan:** thiết bị nhanh hơn không bù được việc truy vấn đọc quá nhiều page không cần thiết.
- **Bỏ qua độ bền ghi:** workload database có thể tạo lượng NAND write lớn hơn host write do write amplification.

## 16. Checklist đánh giá SSD và đường I/O

- [ ] Đã xác định workload chủ yếu là sequential, random hay hỗn hợp.
- [ ] Đã ghi block size, read/write mix, IOPS, throughput và queue depth.
- [ ] Đã đo p50/p95/p99 latency ở điều kiện tải đại diện.
- [ ] Đã phân biệt database page, filesystem block, device sector và request size.
- [ ] Đã kiểm tra buffer pool, OS cache và trạng thái warm/cold cache.
- [ ] Đã đánh giá sustained write, garbage collection và thermal throttling.
- [ ] Đã xem endurance TBW/DWPD, health log và write amplification.
- [ ] Đã xác minh power-loss protection và flush semantics cho workload cần durability.
- [ ] Đã kiểm tra queue/IOPS/throughput limits ở host, controller và cloud backend.
- [ ] Đã đối chiếu log, data, temp, checkpoint và backup với storage volume thực tế.
- [ ] Đã benchmark trên file/volume scratch, không ghi trực tiếp vào thiết bị production.
- [ ] Đã đo tác động của thay đổi lên query latency, commit latency, throughput và workload khác.
- [ ] Đã giữ nguyên durability, backup và replication requirements trong phép thử.

Đọc tuần tự và đọc ngẫu nhiên tạo ra các mẫu I/O khác nhau ngay cả trên SSD. SSD giảm chi phí truy cập ngẫu nhiên so với HDD, nhưng IOPS, request size, queue depth, FTL, garbage collection, write amplification và tail latency vẫn ảnh hưởng tới database. Khi đo đồng thời ở tầng SQL, database, hệ điều hành và storage backend, nhóm vận hành có thể xác định đúng nút thắt và lựa chọn tối ưu phù hợp thay vì chỉ dựa vào thông số quảng cáo của thiết bị.

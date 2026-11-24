# IOPS, throughput, latency và queue depth của đĩa

## 1. Vì sao cần hiểu các chỉ số hiệu năng lưu trữ?

Một máy chủ có CPU mạnh và nhiều bộ nhớ vẫn có thể phản hồi chậm nếu hệ thống lưu trữ không đáp ứng kịp các yêu cầu đọc/ghi. Cơ sở dữ liệu có thể phải chờ ghi log trước khi xác nhận giao dịch; ứng dụng có thể bị chậm khi đọc nhiều tệp nhỏ; tác vụ phân tích có thể mất nhiều thời gian vì không đạt được băng thông đọc tuần tự. Trong các trường hợp này, tăng CPU hoặc bộ nhớ không giải quyết được nút thắt nằm ở đường I/O.

Khi lựa chọn đĩa hoặc dịch vụ lưu trữ cloud, bốn chỉ số thường được dùng để mô tả hiệu năng là **IOPS**, **throughput**, **latency** và **queue depth**. Chúng liên quan với nhau nhưng đo các khía cạnh khác nhau:

- IOPS cho biết số thao tác đọc/ghi hoàn thành trong một giây.
- Throughput cho biết lượng dữ liệu được truyền trong một giây.
- Latency cho biết một yêu cầu I/O mất bao lâu để hoàn tất.
- Queue depth cho biết có bao nhiêu yêu cầu I/O đang chờ hoặc đang được xử lý đồng thời.

Không có một giá trị duy nhất đủ để kết luận đĩa nhanh hay chậm. Một volume có IOPS cao có thể vẫn không đáp ứng workload đọc các khối dữ liệu lớn nếu throughput bị giới hạn. Một volume có throughput cao có thể không phù hợp với cơ sở dữ liệu giao dịch cần hoàn tất nhiều thao tác nhỏ với độ trễ thấp. Queue depth quá thấp có thể không khai thác hết khả năng của thiết bị; queue depth quá cao có thể làm tăng thời gian chờ mà không tăng thông lượng hữu ích.

Trong phạm vi **lưu trữ phục vụ compute**, các chỉ số này cần được xem xét cùng CPU, bộ nhớ, mạng, hệ điều hành, loại ứng dụng và mô hình lưu trữ. Sau bài học, người học có thể:

- Phân biệt IOPS, throughput, latency và queue depth.
- Tính mối quan hệ gần đúng giữa kích thước I/O, IOPS, throughput và số yêu cầu đang outstanding.
- Nhận diện đặc điểm I/O của database, ứng dụng tệp và tác vụ phân tích.
- Đọc giới hạn hiệu năng của volume và giới hạn của máy ảo hoặc instance.
- Đo hiệu năng bằng công cụ phù hợp và diễn giải kết quả benchmark.
- Chọn, cấu hình và tối ưu storage theo workload, độ bền dữ liệu và ngân sách.

## 2. Đường đi của một yêu cầu I/O

### 2.1. Từ ứng dụng đến thiết bị lưu trữ

Khi ứng dụng yêu cầu đọc hoặc ghi dữ liệu, thao tác thường đi qua nhiều lớp: thư viện ứng dụng, filesystem hoặc database engine, page cache của hệ điều hành, block layer, driver, đường kết nối và thiết bị lưu trữ. Với storage mạng, yêu cầu còn đi qua NIC, mạng nội bộ và dịch vụ lưu trữ ở phía nhà cung cấp.

```text
Ứng dụng / Database
        |
        v
Filesystem / Page cache
        |
        v
Block layer / I/O scheduler
        |
        v
Driver / Virtual device
        |
        +---- Local NVMe / SSD
        |
        +---- PCIe / NIC / Network fabric
                       |
                       v
                 Cloud block storage
```

Độ trễ mà ứng dụng nhìn thấy là kết quả của toàn bộ đường đi. Một volume có thông số tốt vẫn có thể cho kết quả thấp nếu instance hết băng thông block storage, CPU bị quá tải, filesystem có tranh chấp khóa, mạng bị nghẽn hoặc ứng dụng phát sinh I/O theo cách không hiệu quả.

### 2.2. Các loại lưu trữ thường gặp

| Loại lưu trữ | Cách truy cập | Đặc điểm hiệu năng | Trường hợp sử dụng |
|---|---|---|---|
| Local SSD/NVMe | Thiết bị gắn trực tiếp với máy chủ | Độ trễ thấp, throughput/IOPS cao; phụ thuộc máy vật lý và có thể là ephemeral | Cache, scratch data, dữ liệu trung gian, workload cần I/O nhanh có thể tái tạo |
| Network block storage | Volume block gắn vào VM/instance qua mạng nội bộ | Có thể điều chỉnh dung lượng và hiệu năng; chịu giới hạn volume, instance và mạng | Boot disk, database, filesystem của máy chủ, dữ liệu cần tồn tại độc lập với VM |
| File storage | Truy cập qua giao thức tệp như NFS hoặc SMB | Hỗ trợ chia sẻ giữa nhiều máy; hiệu năng phụ thuộc metadata, số client, network và dịch vụ | Shared home, content repository, thư mục dùng chung, ứng dụng nhiều node |
| Object storage | Truy cập qua API/object key | Tối ưu cho object lớn và quy mô rộng; không có ngữ nghĩa block device thông thường | Dataset, backup, log, artifact, media và dữ liệu lưu trữ dài hạn |

IOPS và queue depth của đĩa thường được nói đến nhiều nhất với block storage và thiết bị local. File storage có thể công bố IOPS, throughput hoặc giới hạn theo client và metadata operation. Object storage thường được đánh giá bằng request rate, throughput, latency API và kích thước object thay vì queue depth của block device.

### 2.3. Local storage và network storage

Local NVMe có thể cung cấp đường I/O ngắn và độ trễ thấp vì thiết bị kết nối trực tiếp qua PCIe. Tuy nhiên, dữ liệu có thể mất khi instance bị dừng, host bị thay thế hoặc máy được cấp phát lại, tùy loại dịch vụ. Vì vậy, local storage thường phù hợp với dữ liệu có thể tái tạo hoặc có bản sao ở nơi bền vững.

Network block storage tách vòng đời volume khỏi vòng đời VM, thuận tiện cho snapshot, backup, detach và attach lại. Đổi lại, yêu cầu I/O đi qua hạ tầng mạng và lớp dịch vụ lưu trữ. Nhà cung cấp có thể công bố hiệu năng tối đa theo loại volume, dung lượng, mức provisioned hoặc loại instance. Phải đọc đúng điều kiện áp dụng và kiểm tra giới hạn end-to-end.

## 3. Bốn chỉ số hiệu năng chính

### 3.1. IOPS – số thao tác I/O mỗi giây

IOPS (Input/Output Operations Per Second) là số thao tác đọc hoặc ghi hoàn thành trong một giây. Một thao tác có thể đọc hoặc ghi một block nhỏ hay lớn. Vì vậy, IOPS không cho biết trực tiếp lượng dữ liệu đã truyền.

Ví dụ:

- 8.000 IOPS với block 4 KiB tương ứng khoảng 31,25 MiB/s nếu mỗi thao tác truyền đủ 4 KiB.
- 8.000 IOPS với block 64 KiB tương ứng khoảng 500 MiB/s nếu đạt cùng số thao tác và kích thước I/O.

Hai workload có cùng IOPS có thể tạo ra lượng dữ liệu rất khác nhau. IOPS thường quan trọng với database OLTP, hệ thống thư mục nhiều tệp nhỏ, metadata operation hoặc ứng dụng thực hiện nhiều thao tác ngẫu nhiên.

Khi đọc thông số IOPS, cần kiểm tra đó là IOPS đọc, IOPS ghi hay tổng; workload có tỷ lệ read/write nào; kích thước block dùng để công bố; mức IOPS duy trì hay burst; và có điều kiện về dung lượng volume hay không.

### 3.2. Throughput – lượng dữ liệu mỗi giây

Throughput là lượng dữ liệu đọc hoặc ghi trong một giây, thường biểu diễn bằng MB/s, MiB/s, GB/s hoặc GiB/s. Throughput quan trọng với tác vụ truyền dữ liệu lớn, đọc tuần tự, backup, restore, xử lý log và phân tích dữ liệu.

Throughput phụ thuộc vào IOPS và kích thước trung bình của mỗi thao tác I/O. Nếu thiết bị đạt 20.000 IOPS với block trung bình 16 KiB, throughput lý thuyết xấp xỉ:

\[
20{,}000 \times 16\text{ KiB} = 312.5\text{ MiB/s}
\]

Giá trị thực tế có thể thấp hơn do overhead, giới hạn volume/instance, filesystem, read/write mix, queueing và cách workload phát hành yêu cầu.

Đừng nhầm throughput của volume với tốc độ mạng của instance. Nếu volume có khả năng đạt 1.000 MB/s nhưng instance chỉ được cấp tổng băng thông block storage thấp hơn, workload sẽ bị giới hạn ở mức thấp hơn. Tương tự, nhiều volume gắn vào một instance có thể cùng chia sẻ một giới hạn ở cấp máy.

### 3.3. Latency – độ trễ hoàn tất I/O

Latency là thời gian từ khi yêu cầu I/O được phát hành đến khi ứng dụng hoặc lớp gọi nhận được kết quả hoàn tất. Thông thường, đơn vị là microsecond (µs) hoặc millisecond (ms). Với một ứng dụng tương tác, độ trễ cao có thể làm tăng thời gian phản hồi ngay cả khi throughput tổng thể còn thấp.

Latency có thể bao gồm:

- Thời gian ứng dụng và hệ điều hành xếp lịch yêu cầu.
- Thời gian chờ trong queue.
- Thời gian xử lý ở thiết bị hoặc dịch vụ lưu trữ.
- Thời gian truyền qua bus hoặc mạng.
- Thời gian flush, đồng bộ hoặc xác nhận ghi bền vững.
- Thời gian filesystem/database xử lý metadata và khóa.

Không chỉ theo dõi latency trung bình. Hãy xem các percentile như p50, p95, p99 và p99.9. p50 thể hiện trải nghiệm ở giữa phân bố; p99 cho biết 1% thao tác chậm nhất có thể mất bao lâu. Một hệ thống có latency trung bình thấp nhưng p99 tăng mạnh có thể gây timeout hoặc làm hàng đợi ứng dụng tăng đột biến.

Phân biệt latency đọc và ghi, latency ngẫu nhiên và tuần tự, latency khi cache hit và cache miss, cũng như latency của thao tác flush/fsync. Với database, một lần ghi chỉ được xác nhận sau khi log bền vững có thể có độ trễ khác với một lần ghi dữ liệu đã nằm trong page cache.

### 3.4. Queue depth – số yêu cầu I/O đang outstanding

Queue depth mô tả số yêu cầu I/O đã được gửi đi nhưng chưa hoàn tất, hoặc số yêu cầu đang chờ/được xử lý tại một lớp của đường I/O. Tùy công cụ và nền tảng, chỉ số có thể thể hiện queue ở block device, driver, storage service hoặc giá trị cấu hình của benchmark.

Queue depth cao cho phép thiết bị có nhiều yêu cầu để xử lý song song. Điều này có thể tăng throughput khi thiết bị hoặc dịch vụ lưu trữ cần nhiều I/O đồng thời để đạt hiệu năng tối đa. Tuy nhiên, queue depth cao cũng có thể làm yêu cầu phải chờ lâu hơn, đặc biệt khi thiết bị đã bão hòa.

Cần phân biệt:

- **Configured queue depth:** mức outstanding tối đa mà ứng dụng hoặc benchmark cho phép.
- **Observed queue depth:** số yêu cầu thực sự đang outstanding tại một thời điểm.
- **Queue wait:** thời gian một yêu cầu chờ trước khi được xử lý.

Đặt queue depth là 64 không có nghĩa lúc nào thiết bị cũng có 64 yêu cầu. Ứng dụng có thể không phát hành đủ I/O đồng thời, hoặc thiết bị có thể bị giới hạn bởi một lớp khác. Ngược lại, queue depth tăng liên tục cùng latency tăng và throughput không tăng là dấu hiệu có thể đang quá tải.

## 4. Mối quan hệ giữa IOPS, throughput, latency và queue depth

### 4.1. Throughput từ IOPS và kích thước I/O

Với kích thước I/O trung bình tương đối ổn định, có thể ước lượng:

\[
Throughput \approx IOPS \times Average\ I/O\ Size
\]

Ví dụ, workload đạt 12.000 IOPS với block 8 KiB:

\[
12{,}000 \times 8\text{ KiB} = 93.75\text{ MiB/s}
\]

Nếu workload dùng block 128 KiB với cùng 12.000 IOPS, throughput lý thuyết tăng lên khoảng 1.500 MiB/s. Tuy nhiên, phần cứng hoặc dịch vụ có thể chạm trần throughput trước khi đạt được mức đó. Đây là lý do cần xem cả giới hạn IOPS lẫn throughput.

Khi tính, phải thống nhất đơn vị. 1 KiB bằng 1.024 byte; 1 MiB bằng 1.024 KiB. Một số bảng giá hoặc dashboard dùng MB/GB theo hệ thập phân, vì vậy không nên so trực tiếp MB/s với MiB/s mà không quy đổi.

### 4.2. Queue depth, IOPS và latency – định luật Little

Trong một hệ thống ổn định, định luật Little cho mối quan hệ gần đúng giữa số yêu cầu trung bình đang tồn tại trong hệ thống, tốc độ hoàn tất và thời gian trung bình:

\[
Average\ Queue\ Depth \approx IOPS \times Average\ Latency
\]

Latency phải đổi sang giây khi IOPS được tính theo giây. Ví dụ, nếu workload hoàn tất 10.000 IOPS với latency trung bình 2 ms:

\[
Q \approx 10{,}000 \times 0.002 = 20
\]

Trung bình có khoảng 20 yêu cầu I/O đang outstanding trên phạm vi đo tương ứng. Đây là quan hệ quan sát trong trạng thái ổn định, không phải công thức đặt queue depth tối đa cho mọi thiết bị. Phải bảo đảm IOPS và latency đo trên cùng một lớp, cùng loại thao tác và cùng khoảng thời gian.

Nếu queue depth bị giới hạn quá thấp, workload có thể không phát hành đủ yêu cầu đồng thời để đạt throughput tối đa. Nếu tăng queue depth sau khi thiết bị đã bão hòa, IOPS có thể gần như không tăng trong khi latency tăng rõ rệt. Khi đó, tăng queue depth chỉ làm nhiều request chờ lâu hơn.

### 4.3. Ví dụ so sánh hai workload

| Đặc điểm | Workload A | Workload B |
|---|---:|---:|
| IOPS | 15.000 | 3.000 |
| Kích thước I/O trung bình | 4 KiB | 128 KiB |
| Throughput ước tính | 58,6 MiB/s | 375 MiB/s |
| Mẫu truy cập | Ngẫu nhiên, nhiều thao tác nhỏ | Tuần tự, block lớn |
| Chỉ số cần chú ý | p95/p99 latency và IOPS ổn định | Throughput duy trì và thời gian hoàn tất |

Workload A có IOPS cao hơn nhưng truyền ít dữ liệu hơn. Workload B có IOPS thấp hơn nhưng throughput cao hơn. Nếu chỉ chọn volume theo IOPS, có thể chọn sai cho workload B; nếu chỉ nhìn throughput, có thể bỏ qua latency quan trọng với workload A.

### 4.4. Đường cong bão hòa

Khi tăng số yêu cầu đồng thời, IOPS và throughput thường tăng cho đến khi một giới hạn bị chạm. Sau điểm bão hòa, throughput có thể đi ngang trong khi queue depth và latency tiếp tục tăng.

```text
Throughput / IOPS
      ^
      |                  ____________
      |              ___/
      |           __/
      |        __/
      |     __/
      |____/____________________________> Queue depth
                    điểm bão hòa

Latency
      ^
      |                         /
      |                       _/
      |                    __/
      |                ___/
      |______________/
      +---------------------------------> Queue depth
```

Đây là hình minh họa khái niệm. Hình dạng thực tế phụ thuộc thiết bị, dịch vụ cloud, kích thước I/O, read/write mix và mức tranh chấp. Mục tiêu là tìm vùng queue depth cho throughput tốt trong khi latency vẫn đáp ứng SLO.

## 5. Mẫu I/O của workload

### 5.1. Random I/O và sequential I/O

**Random I/O** truy cập các vị trí dữ liệu không liên tiếp. Database OLTP, index, metadata và nhiều workload giao dịch thường tạo nhiều thao tác nhỏ, ngẫu nhiên. IOPS và latency thường quan trọng.

**Sequential I/O** đọc hoặc ghi các vùng dữ liệu liên tiếp. Backup, restore, streaming, xử lý log và phân tích tệp lớn thường có thể tạo block I/O lớn. Throughput thường quan trọng hơn IOPS cực đại.

Một ứng dụng có thể kết hợp cả hai. Ví dụ, database có thể đọc page ngẫu nhiên nhưng ghi transaction log tuần tự. Cần đo từng luồng I/O hoặc từng thiết bị nếu có thể để biết thành phần nào tạo tải.

### 5.2. Read-heavy, write-heavy và read/write mix

Tỷ lệ đọc/ghi ảnh hưởng hiệu năng. Một số loại volume có thông số đọc và ghi tương tự; loại khác có giới hạn hoặc chi phí khác nhau. Ghi đồng bộ có thể chịu ảnh hưởng bởi flush và yêu cầu độ bền dữ liệu. Ghi bất đồng bộ có thể được xác nhận sớm hơn nhưng cần hiểu rõ khi nào dữ liệu thực sự bền vững.

Hãy đo tỷ lệ đọc/ghi thực tế thay vì giả định ứng dụng là read-heavy hoặc write-heavy theo tên gọi. Cùng một database có thể có tỷ lệ khác nhau giữa giờ cao điểm, giờ batch và giai đoạn backup.

### 5.3. Kích thước block

Kích thước block ảnh hưởng trực tiếp đến lượng dữ liệu mỗi I/O. Block nhỏ tạo nhiều thao tác hơn cho cùng một lượng dữ liệu; block lớn giảm số thao tác nhưng có thể đọc/ghi nhiều dữ liệu không cần thiết.

Ví dụ, một truy vấn đọc 4 KiB ngẫu nhiên không nhất thiết được cải thiện khi cấu hình block 1 MiB. Ngược lại, đọc tệp 1 GiB tuần tự thường có thể tận dụng block lớn và batching tốt hơn. Hãy đo ở kích thước gần với ứng dụng thật.

### 5.4. Synchronous và asynchronous I/O

Synchronous I/O khiến luồng gọi thường chờ thao tác hoàn tất trước khi tiếp tục. Nếu ứng dụng chỉ có ít luồng, số I/O outstanding có thể thấp, khiến thiết bị không được khai thác hết. Asynchronous I/O cho phép ứng dụng phát hành nhiều yêu cầu và tiếp tục xử lý trong khi I/O đang chạy.

Tăng concurrency có thể cải thiện throughput nhưng cũng tăng bộ nhớ đệm, số request đang chờ và độ trễ. Đối với database, không nên thay đổi chế độ đồng bộ chỉ để đạt benchmark cao nếu điều đó làm thay đổi cam kết durability hoặc semantics của giao dịch.

### 5.5. Cache và page cache

Kết quả đo có thể bị ảnh hưởng bởi cache ở ứng dụng, hệ điều hành, hypervisor hoặc storage service. Đọc lặp lại cùng dữ liệu có thể được phục vụ từ RAM thay vì thiết bị. Khi đó, benchmark phản ánh hiệu năng cache hơn là hiệu năng storage.

Để đo thiết bị, cần hiểu cách công cụ benchmark bỏ qua hoặc kiểm soát cache. Tuy nhiên, không nên loại bỏ cache nếu workload production thực tế phụ thuộc vào cache; hãy đo cả cold-cache và warm-cache khi phù hợp.

## 6. Hiểu giới hạn hiệu năng của cloud storage

### 6.1. Giới hạn ở cấp volume

Nhà cung cấp có thể công bố các mức IOPS và throughput tối đa theo loại volume, dung lượng, mức hiệu năng provisioned hoặc cấu hình riêng. Một số volume có baseline thay đổi theo dung lượng; một số cho phép provision IOPS hoặc throughput độc lập trong giới hạn nhất định.

Hãy đọc các thuộc tính sau trong tài liệu dịch vụ:

- IOPS tối đa và IOPS baseline.
- Throughput tối đa và throughput baseline.
- Quan hệ giữa dung lượng volume và hiệu năng.
- Mức hiệu năng có được duy trì liên tục hay chỉ trong thời gian burst.
- Giới hạn kích thước I/O và read/write mix nếu có.
- Số volume tối đa có thể gắn vào một instance.
- Thời gian áp dụng thay đổi cấu hình và cách tính phí.

Không lấy con số tối đa trong trang marketing làm cam kết cho mọi kích thước volume. Một mức IOPS có thể chỉ đạt được khi volume đủ lớn, loại instance tương thích và queue depth đủ cao.

### 6.2. Burst và credit

Một số loại storage có baseline thấp hơn mức hiệu năng burst. Volume có thể tích lũy credit khi hoạt động dưới baseline rồi sử dụng credit để tăng hiệu năng trong một khoảng thời gian. Khi credit cạn, hiệu năng quay về mức baseline.

Điều này có thể khiến benchmark ngắn cho kết quả rất tốt nhưng workload chạy lâu lại chậm. Với tác vụ batch dài, database hoặc hệ thống có tải đều, cần đo sau khi burst credit giảm hoặc xác minh cơ chế duy trì hiệu năng của dịch vụ.

Không phải mọi dịch vụ đều dùng mô hình credit. Hãy xác định chính xác loại volume và xem dashboard có metric burst balance hoặc tương đương hay không.

### 6.3. Giới hạn ở cấp instance và đường kết nối

Volume không phải giới hạn duy nhất. Instance/VM có thể có trần IOPS hoặc throughput tổng cho toàn bộ storage. Nhiều volume cùng gắn vào một instance có thể chia sẻ trần đó. CPU, PCIe, NIC, network fabric và driver cũng có thể trở thành nút thắt.

Ví dụ, nếu ba volume mỗi volume có thể đạt 500 MB/s nhưng instance chỉ hỗ trợ tổng cộng 800 MB/s cho block storage, tổng throughput của ba volume không thể đạt 1.500 MB/s trên instance đó. Tăng hiệu năng từng volume không giúp vượt giới hạn instance.

Kiểm tra cả giới hạn burst của instance, loại máy, số vCPU, băng thông mạng và khả năng hỗ trợ multi-queue. Nếu CPU quá tải, xử lý interrupt hoặc checksum có thể làm giảm tốc độ I/O dù storage service còn công suất.

### 6.4. Stripe nhiều volume

Có thể ghép nhiều volume bằng RAID hoặc logical volume manager để tăng tổng IOPS/throughput hoặc dung lượng. Nếu workload và nền tảng hỗ trợ, stripe có thể phân tán I/O qua nhiều volume.

Tuy nhiên, hiệu năng tổng không phải lúc nào cũng tăng tuyến tính. Các volume vẫn có thể chia sẻ trần instance hoặc network. Stripe cũng tăng độ phức tạp vận hành và phạm vi ảnh hưởng khi một volume gặp lỗi. Với RAID 0, lỗi một thành phần có thể làm mất toàn bộ dữ liệu của tập stripe. Cần có backup và quy trình khôi phục rõ ràng; snapshot từng volume cần bảo đảm tính nhất quán của cả nhóm.

Chỉ stripe khi đã xác định giới hạn volume là nút thắt, instance còn đủ băng thông, và có lý do về hiệu năng hoặc dung lượng. Không dùng stripe để che giấu việc chọn sai loại instance hoặc storage tier.

### 6.5. Snapshot, backup và hoạt động nền

Snapshot, backup, replication, encryption và migration có thể tạo thêm I/O hoặc ảnh hưởng hiệu năng tùy dịch vụ. Một số nền tảng xử lý snapshot ở nền; một số hoạt động có thể gây burst hoặc contention trên storage path. Hãy quan sát chỉ số trong thời gian backup và kiểm tra tác động đến p95/p99 latency.

Không nên bỏ backup để giữ benchmark cao. Hãy lên lịch backup phù hợp, dùng snapshot nhất quán với ứng dụng và kiểm tra khả năng restore. Mục tiêu là hiệu năng production có thể duy trì cùng với yêu cầu bảo vệ dữ liệu.

## 7. Chọn storage theo workload

### 7.1. Database OLTP

Database OLTP thường tạo nhiều I/O nhỏ và ngẫu nhiên, đồng thời có yêu cầu độ trễ ổn định cho transaction log và thao tác đồng bộ. Các tiêu chí quan trọng thường là IOPS duy trì, p95/p99 read/write latency, queue depth trong giờ cao điểm và khả năng xử lý burst.

Nên đo riêng data file, index, transaction log và temporary file nếu kiến trúc cho phép. Transaction log có thể cần latency ghi thấp; data file có thể cần IOPS đọc cao. Đặt chúng trên các volume riêng chỉ có ích khi thực sự có thể tách giới hạn hiệu năng và quan sát độc lập.

### 7.2. Data warehouse và phân tích

Tác vụ phân tích thường đọc các vùng dữ liệu lớn, quét tuần tự và xử lý theo batch. Throughput, khả năng đọc song song, số lượng worker và băng thông giữa storage với compute thường quan trọng. Object storage có thể phù hợp cho dataset lớn, trong khi block hoặc file storage có thể phù hợp với scratch space và dữ liệu tạm.

Hãy đo throughput khi nhiều worker đọc đồng thời. Một job đơn có thể đạt tốc độ cao nhưng tổng throughput cluster có thể bị giới hạn bởi network, storage service hoặc quota.

### 7.3. File server và nội dung chia sẻ

File server có nhiều loại thao tác: đọc/ghi nội dung, tạo/xóa/đổi tên tệp, tra cứu thư mục và kiểm tra quyền. Metadata operation có thể là nút thắt ngay cả khi throughput dữ liệu lớn còn thấp. Vì vậy, chỉ đo MB/s không phản ánh đầy đủ hiệu năng.

Đo cả thao tác metadata, số client đồng thời, latency mở tệp và throughput đọc/ghi. Chọn file service theo giao thức, mô hình chia sẻ, quyền truy cập và mức độ đồng thời.

### 7.4. Cache và dữ liệu tạm

Cache, build artifact, dữ liệu trung gian và scratch data thường ưu tiên latency thấp và IOPS/throughput cao. Local NVMe có thể phù hợp nếu dữ liệu có thể tái tạo hoặc được sao lưu nơi khác. Nếu cần giữ dữ liệu sau khi VM bị thay thế, dùng storage bền vững hoặc đồng bộ dữ liệu ra dịch vụ khác.

### 7.5. Backup và lưu trữ dài hạn

Backup thường tối ưu theo chi phí, độ bền và thời gian restore. Throughput ảnh hưởng thời gian tạo và khôi phục backup; latency ngẫu nhiên có thể ít quan trọng hơn so với database OLTP. Object storage hoặc storage tier lạnh có thể giảm chi phí, nhưng cần hiểu thời gian truy xuất, phí lấy dữ liệu và giới hạn request.

## 8. Đo hiệu năng và benchmark

### 8.1. Đo workload thật trước khi benchmark tổng hợp

Bắt đầu bằng metric từ ứng dụng, database và hệ điều hành. Ghi lại IOPS đọc/ghi, throughput, latency percentile, queue depth, kích thước I/O, tỷ lệ random/sequential và read/write mix. Đo trong giờ bình thường, giờ cao điểm và khi chạy backup hoặc batch.

Benchmark tổng hợp giúp cô lập một số thuộc tính của storage, nhưng không thay thế workload thật. Nếu database dùng block 8 KiB và fsync thường xuyên, một bài benchmark sequential 1 MiB không thể chứng minh storage phù hợp.

### 8.2. Dùng fio để đo I/O

`fio` là công cụ tạo workload I/O có thể cấu hình kích thước block, kiểu truy cập, read/write mix, số job và queue depth. Ví dụ sau tạo bài kiểm tra random read với block 4 KiB và queue depth 32 trên một tệp thử nghiệm:

Trước tiên, tạo tệp thử nghiệm trên volume scratch. Lệnh này ghi dữ liệu và chỉ nên chạy trên vùng thử nghiệm được phép ghi:

```bash
fio --name=prepare \
    --filename=/mnt/test-volume/fio-test.bin \
    --size=10G \
    --rw=write \
    --bs=1m \
    --ioengine=libaio \
    --direct=1 \
    --iodepth=16 \
    --end_fsync=1 \
    --group_reporting
```

Sau khi tệp đã được tạo, có thể chạy bài random read và sequential read bên dưới.

```bash
fio --name=randread-4k \
    --filename=/mnt/test-volume/fio-test.bin \
    --size=10G \
    --rw=randread \
    --bs=4k \
    --ioengine=libaio \
    --direct=1 \
    --iodepth=32 \
    --numjobs=1 \
    --runtime=60 \
    --time_based \
    --group_reporting
```

Ví dụ đọc tuần tự với block lớn để quan sát throughput:

```bash
fio --name=seqread-1m \
    --filename=/mnt/test-volume/fio-test.bin \
    --size=10G \
    --rw=read \
    --bs=1m \
    --ioengine=libaio \
    --direct=1 \
    --iodepth=16 \
    --numjobs=1 \
    --runtime=60 \
    --time_based \
    --group_reporting
```

Đây là ví dụ cho Linux và môi trường có hỗ trợ `libaio`; cần xác minh I/O engine phù hợp với kernel và thiết bị. Tệp thử nghiệm phải nằm trên volume scratch được phép ghi. Việc chuẩn bị tệp có thể ghi dữ liệu lên volume; không chạy bài ghi hoặc tạo tệp thử trên volume production đang chứa dữ liệu quan trọng. Benchmark gây tải I/O và có thể làm chậm workload khác.

`--iodepth` là queue depth được yêu cầu cho mỗi job; `--numjobs` tạo nhiều job. Tổng số yêu cầu outstanding tiềm năng có thể tăng theo số job, nhưng mức thực tế phụ thuộc engine, ứng dụng và thiết bị. Không tăng đồng thời cả hai tham số mà không quan sát latency và mức bão hòa.

### 8.3. Đo ở các điểm tải khác nhau

Một quy trình benchmark nên thay đổi từng yếu tố:

1. Đo baseline ở tải thấp với kích thước block gần workload thật.
2. Tăng queue depth từng bước, ví dụ 1, 4, 8, 16, 32 và 64.
3. Ghi IOPS, throughput, latency p50/p95/p99 và queue depth quan sát được.
4. Lặp lại với read, write và read/write mix phù hợp.
5. Thử random và sequential với kích thước block khác nhau.
6. Chạy đủ lâu để phát hiện giới hạn burst hoặc hiệu năng suy giảm theo thời gian.
7. Đo khi backup, snapshot hoặc các workload khác hoạt động nếu đó là tình huống production.

Không nên chỉ ghi lại kết quả cao nhất. Hãy tìm điểm mà throughput tăng ít nhưng latency tăng mạnh; đó thường là dấu hiệu vượt qua vùng hiệu quả của queue depth.

### 8.4. Công cụ quan sát hệ điều hành

Trên Linux, có thể dùng:

```bash
iostat -xz 1
```

Lệnh này hiển thị thống kê I/O theo thiết bị theo từng khoảng thời gian. Tùy phiên bản sysstat và kernel, các trường có thể gồm read/write IOPS, throughput, thời gian chờ, queue và mức sử dụng thiết bị. Cần hiểu ý nghĩa trường trong phiên bản đang dùng; không dùng riêng `%util` để kết luận một thiết bị hiện đại đã đạt 100% công suất.

Một số công cụ khác:

- `pidstat -d`: quan sát I/O theo tiến trình.
- `vmstat`: quan sát trạng thái hệ thống, bao gồm chờ I/O ở mức tổng quan.
- `lsblk` và `findmnt`: kiểm tra thiết bị block và mount point.
- Công cụ database: theo dõi file latency, fsync, checkpoint và buffer/cache hit.
- Cloud monitoring: theo dõi metric volume, instance, burst balance, queue và network theo dịch vụ.

### 8.5. Đọc kết quả fio

Kết quả fio thường có các phần:

- `IOPS`: số thao tác hoàn tất mỗi giây.
- `BW`: bandwidth/throughput đo được.
- `clat`: completion latency ở phía I/O engine.
- `lat`: tổng latency theo cách fio báo cáo, có thể gồm thời gian submission và completion.
- Percentile latency: phân bố thời gian hoàn tất, ví dụ p95 và p99.
- `IO depths`: phân bố số yêu cầu outstanding quan sát được.
- `util`: mức sử dụng được báo cáo cho thiết bị theo cơ chế của công cụ.

Đọc đúng đơn vị và phần thống kê. So sánh `clat` với latency của ứng dụng cần tính đến các lớp nằm ngoài fio. Khi đo cloud block storage, cũng cần đối chiếu metric của volume và instance để phân biệt giới hạn storage với giới hạn host/network.

## 9. Diễn giải tình huống và tìm nút thắt

| Quan sát | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| IOPS thấp, throughput thấp, queue depth thấp | Ứng dụng phát hành ít I/O; cache hit; concurrency thấp | Kiểm tra số worker, async I/O, cache và cấu hình benchmark |
| IOPS cao nhưng throughput thấp | Block size nhỏ | Xem kích thước I/O và liệu workload thực có cần block lớn hơn không |
| Throughput thấp dù IOPS chưa chạm trần | Trần throughput volume/instance, mạng hoặc CPU | Kiểm tra giới hạn ở cấp volume, instance, NIC và CPU |
| Queue depth và latency cùng tăng, throughput đi ngang | Thiết bị hoặc một lớp trên đường I/O đã bão hòa | Giảm concurrency thử nghiệm, tìm giới hạn và mở rộng đúng lớp |
| p99 latency tăng mạnh nhưng trung bình ổn định | Một số request bị queue lâu, contention, flush hoặc hoạt động nền | Phân tích percentile, read/write mix, snapshot, backup và noisy neighbor |
| IOPS tốt lúc đầu rồi giảm | Burst credit cạn hoặc tải kéo dài chạm baseline | Theo dõi burst balance và chạy test đủ lâu |
| Nhiều volume nhưng tổng throughput không tăng | Trần instance hoặc network đang giới hạn | Đối chiếu metric volume với metric tổng ở instance |
| fio tốt nhưng ứng dụng chậm | Pattern benchmark khác workload; cache, filesystem, lock hoặc CPU | Đo ở cấp ứng dụng và tái tạo đúng kích thước/độ đồng thời |

Không nên kết luận storage là nút thắt chỉ vì CPU utilization thấp hoặc queue depth cao. Hãy đối chiếu nhiều chỉ số theo cùng khoảng thời gian và xác định lớp đầu tiên bị giới hạn.

## 10. Tối ưu hiệu năng lưu trữ

### 10.1. Chọn đúng loại volume và mức hiệu năng

Chọn volume theo cả IOPS, throughput, latency, dung lượng, độ bền và chi phí. Với database giao dịch, ưu tiên IOPS ổn định và latency thấp. Với sequential processing, ưu tiên throughput. Với cache có thể tái tạo, local NVMe có thể phù hợp. Với dữ liệu cần giữ độc lập với VM, chọn storage bền vững có snapshot/backup phù hợp.

### 10.2. Tối ưu kích thước I/O và batching

Gộp các thao tác nhỏ khi ứng dụng cho phép có thể giảm overhead và tăng throughput. Tuy nhiên, block lớn hơn có thể làm tăng lượng dữ liệu đọc/ghi không cần thiết và tăng latency của một thao tác. Điều chỉnh theo pattern thật, không theo một cấu hình chung.

### 10.3. Điều chỉnh concurrency và queue depth

Tăng số luồng I/O hoặc queue depth có thể giúp thiết bị tận dụng song song. Tăng dần và quan sát IOPS, throughput cùng percentile latency. Dừng tăng khi throughput gần như không cải thiện nhưng latency tiếp tục tăng.

### 10.4. Giảm I/O không cần thiết

- Dùng cache phù hợp để giảm đọc lặp lại.
- Tránh ghi log quá chi tiết hoặc flush thường xuyên ngoài yêu cầu.
- Gộp thao tác metadata và giảm số tệp nhỏ nếu ứng dụng cho phép.
- Dùng compression hoặc columnar format cho dữ liệu phân tích khi có lợi.
- Tách workload batch khỏi database latency-sensitive nếu chúng tranh chấp cùng volume.
- Đặt temporary data trên storage phù hợp, có thể tái tạo.

Không tắt durability, fsync hoặc cơ chế đồng bộ chỉ để cải thiện benchmark nếu điều đó làm thay đổi bảo đảm dữ liệu của ứng dụng.

### 10.5. Mở rộng đúng lớp

Nếu volume chạm trần IOPS nhưng instance còn dư, nâng cấp hoặc provision IOPS cho volume có thể hữu ích. Nếu throughput tổng bị giới hạn ở instance, cần loại instance có giới hạn storage cao hơn. Nếu nhiều workload tranh chấp, tách volume hoặc tách instance có thể giảm contention. Nếu bottleneck nằm ở network hoặc CPU, tăng IOPS volume không giải quyết được vấn đề.

### 10.6. Theo dõi liên tục

Thiết lập dashboard và cảnh báo cho IOPS, throughput, latency p95/p99, queue depth, burst balance, dung lượng còn trống và lỗi I/O. Cảnh báo nên dựa trên SLO và thời gian duy trì, tránh chỉ cảnh báo khi một điểm đo ngắn vượt ngưỡng.

Theo dõi dung lượng cũng quan trọng: filesystem gần đầy có thể gây lỗi ghi hoặc làm giảm hiệu năng; volume đầy có thể khiến ứng dụng ngừng hoạt động dù IOPS còn dư. Dự báo tăng trưởng để mở rộng dung lượng trước khi chạm ngưỡng.

## 11. Độ bền dữ liệu, bảo mật và chi phí

### 11.1. Hiệu năng không thay thế độ bền

Local NVMe có thể nhanh nhưng thường không nên là bản sao duy nhất của dữ liệu quan trọng. Network block volume có thể tồn tại độc lập với VM nhưng vẫn cần snapshot, backup và kế hoạch phục hồi. RAID tăng hiệu năng hoặc khả năng chịu lỗi trong một số cấu hình, nhưng không thay thế backup chống xóa nhầm, hỏng logic hoặc ransomware.

Kiểm tra chính sách durability, replication, snapshot consistency, backup retention và thời gian restore. Với database, dùng cơ chế backup hoặc snapshot nhất quán với trạng thái giao dịch.

### 11.2. Bảo mật đường I/O

Mã hóa dữ liệu at rest và in transit theo yêu cầu. Quản lý khóa bằng dịch vụ KMS hoặc cơ chế tương đương, giới hạn quyền attach/detach volume và quyền snapshot. Tách quyền quản trị storage khỏi quyền truy cập dữ liệu ứng dụng. Ghi audit log cho thao tác tạo, thay đổi, snapshot, chia sẻ và xóa volume.

Với file storage, kiểm soát danh tính và quyền ở cả lớp mạng lẫn filesystem. Với object storage, dùng policy theo bucket/object, hạn chế public access và bật log/audit phù hợp. Không đưa dữ liệu nhạy cảm vào volume benchmark hoặc tệp thử nghiệm.

### 11.3. Chi phí hiệu năng

Chi phí có thể gồm dung lượng volume, IOPS/throughput provisioned, snapshot, backup, request, network transfer và thời gian instance chạy. Một volume provisioned quá cao so với workload sẽ gây lãng phí; volume quá thấp có thể kéo dài thời gian xử lý và tăng chi phí compute do instance phải chờ I/O.

Đánh giá chi phí theo kết quả công việc, ví dụ chi phí trên một nghìn giao dịch, một TB dữ liệu xử lý hoặc một giờ hoàn tất backup. Tính cả thời gian compute bị nhàn rỗi vì chờ storage. Đối với workload biến động, so sánh chi phí baseline/burst với mức provisioned ổn định.

## 12. Ví dụ thực tế

### Ví dụ 1: Database giao dịch

Một database có nhiều truy vấn ngẫu nhiên, kích thước I/O nhỏ và ghi transaction log đồng bộ. Người dùng phản ánh thời gian phản hồi tăng vào giờ cao điểm.

**Cách phân tích:** đo read/write IOPS, block size, p95/p99 latency, queue depth và fsync latency. Đối chiếu với baseline và giới hạn provisioned của volume. Kiểm tra CPU, cache hit, backup và các workload khác dùng chung instance. Nếu queue depth tăng và latency tăng trong khi IOPS đi ngang, có thể storage path đã bão hòa. Nếu queue depth thấp, ứng dụng có thể chưa phát hành đủ I/O đồng thời hoặc bị giới hạn ở CPU/database lock.

**Hướng xử lý:** chọn volume có IOPS duy trì và latency phù hợp; tách log/data khi có lợi; giảm I/O thừa; kiểm tra instance-level storage limit; benchmark bằng read/write mix gần production.

### Ví dụ 2: Phân tích dữ liệu tuần tự

Một job đọc các tệp lớn từ storage để xử lý theo batch. IOPS không cao nhưng job hoàn tất chậm.

**Cách phân tích:** đo throughput theo từng worker, kích thước block, số luồng đọc, network throughput và giới hạn storage. Kiểm tra xem volume hoặc file service có đạt trần throughput hay không. Nếu mỗi worker đọc tuần tự nhưng tổng băng thông thấp, kiểm tra concurrency, NIC và đường truyền đến storage.

**Hướng xử lý:** dùng storage tối ưu throughput, tăng số luồng đọc có kiểm soát, chọn block size phù hợp và phân phối dữ liệu để giảm tranh chấp. Nếu dữ liệu là object lớn, cân nhắc object storage và cách đọc song song theo range hoặc partition.

### Ví dụ 3: Volume có burst performance

Một ứng dụng chạy benchmark ngắn cho kết quả tốt, nhưng sau 30 phút tải cao thì throughput giảm và latency tăng.

**Cách phân tích:** kiểm tra loại volume có burst credit hay không; theo dõi burst balance theo thời gian; so sánh hiệu năng lúc credit cao và sau khi credit giảm. Kiểm tra xem workload có vượt baseline lâu dài hay không.

**Hướng xử lý:** chọn loại volume có baseline đáp ứng tải liên tục, provision IOPS/throughput phù hợp hoặc giảm tải bằng cache/batching. Lập benchmark đủ dài để đại diện cho thời gian chạy thực tế.

## 13. Những sai lầm thường gặp

- **Chỉ nhìn IOPS:** bỏ qua kích thước block và throughput thực tế.
- **Chỉ nhìn throughput:** không phát hiện latency p99 cao với thao tác nhỏ.
- **Coi queue depth càng cao càng tốt:** queue quá sâu có thể chỉ làm tăng thời gian chờ.
- **Dùng benchmark tuần tự để đánh giá database:** mẫu I/O không giống workload thực.
- **Chạy benchmark quá ngắn:** có thể chỉ đo burst credit hoặc cache.
- **Không xét giới hạn instance:** tổng throughput nhiều volume có thể bị chặn ở VM/host.
- **Đồng nhất MB/s với MiB/s:** khác đơn vị có thể gây sai lệch khi so sánh.
- **Bỏ qua read/write mix:** hiệu năng đọc và ghi có thể khác nhau.
- **Đo trong lúc cache đang nóng mà không ghi rõ:** kết quả có thể không phản ánh cold read.
- **Dùng local SSD làm nơi lưu duy nhất cho dữ liệu quan trọng:** tốc độ cao không đồng nghĩa độ bền cao.
- **Tăng queue depth hoặc số worker mà không theo dõi latency:** có thể làm hệ thống quá tải.
- **Tắt fsync hoặc durability để đạt điểm benchmark:** làm sai hành vi bảo vệ dữ liệu của ứng dụng.

## 14. Checklist chọn và kiểm chứng storage

- [ ] Đã xác định workload random/sequential, read/write mix và kích thước I/O.
- [ ] Đã đo IOPS, throughput, latency p50/p95/p99 và queue depth.
- [ ] Đã phân biệt latency của ứng dụng với latency ở thiết bị hoặc dịch vụ cloud.
- [ ] Đã tính throughput gần đúng từ IOPS và kích thước I/O trung bình.
- [ ] Đã kiểm tra baseline, burst, provisioned performance và giới hạn volume.
- [ ] Đã kiểm tra giới hạn tổng IOPS/throughput ở cấp instance và network.
- [ ] Đã chọn loại storage phù hợp: local, block, file hoặc object.
- [ ] Đã benchmark bằng pattern gần workload thật và chạy đủ lâu.
- [ ] Đã quan sát queue depth và latency khi tăng concurrency.
- [ ] Đã kiểm tra tác động của backup, snapshot, cache và workload dùng chung.
- [ ] Đã xác định durability, backup, restore, encryption và quyền truy cập.
- [ ] Đã tính chi phí dung lượng, hiệu năng provisioned, snapshot, network và compute wait time.
- [ ] Đã đặt dashboard, cảnh báo và ngưỡng mở rộng theo SLO.

## 15. Kết luận

IOPS, throughput, latency và queue depth mô tả bốn khía cạnh bổ sung cho nhau của hiệu năng lưu trữ. IOPS đo số thao tác hoàn tất; throughput đo lượng dữ liệu; latency đo thời gian hoàn tất; queue depth phản ánh mức độ yêu cầu đang outstanding. Kích thước I/O và mức đồng thời quyết định cách các chỉ số này liên hệ với nhau.

Hãy chọn storage từ mẫu I/O thực tế, kiểm tra giới hạn ở cả cấp volume lẫn instance, đo percentile latency và benchmark đủ lâu để nhận diện burst hoặc bão hòa. Tối ưu queue depth, batching và concurrency chỉ có ích khi cải thiện throughput mà vẫn giữ latency trong SLO. Cuối cùng, cân bằng hiệu năng với độ bền, bảo mật, khả năng khôi phục và tổng chi phí vận hành.

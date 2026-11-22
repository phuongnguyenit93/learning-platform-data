# Đối chiếu chỉ số CPU, bộ nhớ, đĩa và mạng ở hệ điều hành

Hiệu năng cơ sở dữ liệu chịu ảnh hưởng trực tiếp từ tài nguyên của máy chủ đang chạy hệ quản trị. Một câu SQL có kế hoạch thực thi hợp lý vẫn có thể chậm nếu CPU phải chờ lập lịch, bộ nhớ chịu áp lực, thiết bị lưu trữ xử lý không kịp hoặc mạng có độ trễ và mất gói. Ngược lại, máy chủ có CPU sử dụng cao chưa chắc là nguyên nhân của truy vấn chậm nếu thời gian chủ yếu nằm ở chờ khóa hoặc chờ một dịch vụ khác.

Với phạm vi DATABASE_PERFORMANCE, quan sát hệ điều hành là một phần của phương pháp tối ưu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Cần đối chiếu số liệu ở ba lớp: ứng dụng, hệ quản trị cơ sở dữ liệu và hệ điều hành. Mục tiêu là tìm tài nguyên đang giới hạn công việc, xác định mối liên hệ với truy vấn hoặc giao dịch cụ thể, rồi kiểm chứng thay đổi bằng cùng điều kiện đo.

## 1. Mô hình quan sát ba lớp

Khi một yêu cầu đến ứng dụng, thời gian phản hồi có thể gồm nhiều đoạn: chờ ở hàng đợi ứng dụng, chờ lấy kết nối, gửi lệnh qua mạng, chờ cơ sở dữ liệu xử lý, chờ đọc hoặc ghi dữ liệu, rồi truyền kết quả về ứng dụng. Mỗi đoạn có thể chịu ảnh hưởng từ một lớp khác nhau.

| Lớp quan sát | Câu hỏi chính | Ví dụ dữ liệu |
|---|---|---|
| Ứng dụng | Người dùng chờ ở đâu và yêu cầu nào chậm? | p50/p95/p99, timeout, pool wait, số yêu cầu đang chờ |
| Cơ sở dữ liệu | Truy vấn, giao dịch hoặc cơ chế nội bộ nào đang chờ? | Query fingerprint, execution plan, buffer hit, lock wait, commit latency, replication lag |
| Hệ điều hành | Máy chủ đang dùng hoặc chờ tài nguyên nào? | CPU, run queue, memory pressure, swap, I/O latency, network drops và retransmits |

Không thể kết luận nguyên nhân chỉ từ một biểu đồ. CPU thấp và truy vấn chậm có thể xuất hiện khi hệ quản trị đang chờ đĩa, chờ khóa hoặc chờ phản hồi từ mạng. CPU cao có thể là dấu hiệu truy vấn tốn tính toán, nhưng cũng có thể do nhiều truy vấn hợp lệ đang chạy đồng thời. Cần ghép các số liệu có cùng mốc thời gian và cùng phạm vi máy chủ.

### Phân biệt máy chủ, tiến trình và vùng tài nguyên

Số liệu toàn máy cho biết tình trạng tổng thể, nhưng không chỉ ra tiến trình nào gây tải. Số liệu tiến trình cho biết tiến trình hệ quản trị đang tiêu thụ bao nhiêu CPU, RAM hoặc I/O. Trong môi trường container hoặc máy ảo, tiến trình còn có thể bị giới hạn bởi quota hoặc tài nguyên được cấp riêng.

Khi thu thập, hãy ghi rõ:

- Máy chủ vật lý, máy ảo hay container.
- Tên và PID của tiến trình cơ sở dữ liệu; nếu hệ quản trị dùng nhiều tiến trình con, cần biết công cụ đang tổng hợp theo tiến trình hay theo nhóm.
- CPU, RAM và I/O là số liệu toàn host, của container hay của tiến trình.
- Thiết bị chứa dữ liệu, transaction log/WAL, file tạm và backup.
- Giao diện mạng và đường truyền mà ứng dụng, replica hoặc client đang sử dụng.
- Thời điểm đo, múi giờ, khoảng lấy mẫu và phiên bản cấu hình liên quan.

Một giới hạn CPU của container có thể làm tiến trình bị throttling dù biểu đồ CPU toàn máy vẫn thấp. Một máy ảo có thể chịu CPU steal khi hypervisor chưa cấp được thời gian CPU. Nếu không biết phạm vi đo, ta có thể diễn giải sai rằng máy chủ còn dư công suất.

## 2. CPU: mức sử dụng, thời gian chờ và khả năng lập lịch

CPU thực hiện các phép tính của bộ tối ưu truy vấn, join, sort, aggregate, mã hóa, nén và nhiều công việc nền. Khi CPU là nút thắt, thời gian xử lý có thể tăng dù I/O không cao. Tuy nhiên, cần phân biệt CPU đang bận thực sự với công việc đang chờ được chạy.

### Các thành phần CPU thường gặp

Trên Linux, công cụ hệ thống thường phân tách thời gian CPU thành các nhóm:

- **user:** thời gian chạy mã ở user space, ví dụ phần lớn logic của tiến trình cơ sở dữ liệu.
- **system:** thời gian CPU chạy mã kernel thay mặt tiến trình, có thể tăng khi có nhiều system call, thao tác mạng hoặc I/O.
- **idle:** CPU không có công việc cần chạy.
- **iowait:** thời gian CPU nhàn rỗi trong khi hệ thống có I/O đang chờ hoàn tất theo cách thống kê của Linux. Đây không phải phần trăm CPU đang thực hiện đọc đĩa.
- **irq/softirq:** thời gian xử lý ngắt phần cứng và ngắt mềm; tải mạng hoặc thiết bị lớn có thể làm các giá trị này tăng.
- **steal:** thời gian máy ảo muốn chạy nhưng hypervisor cấp CPU cho máy ảo khác.

Các công cụ và hệ điều hành có thể định nghĩa hoặc trình bày chỉ số khác nhau. Không nên cộng trừ các thành phần giữa hai nền tảng như thể chúng hoàn toàn tương đương.

### CPU utilization không đủ để kết luận

Nếu tổng CPU ở mức cao trong thời gian dài, cần xem từng lõi và hàng đợi chạy. Trên máy nhiều lõi, mức sử dụng trung bình 50% có thể che giấu một lõi đã bão hòa trong khi các lõi khác còn rảnh. Một luồng truy vấn đơn có thể bị giới hạn bởi một lõi dù toàn máy còn nhiều CPU.

**Run queue** cho biết số tiến trình hoặc luồng sẵn sàng chạy nhưng chưa được cấp CPU. Khi run queue liên tục lớn hơn năng lực lõi khả dụng, công việc phải chờ lập lịch. Load average trên Linux phản ánh trung bình số tác vụ đang chạy hoặc ở trạng thái chờ không ngắt được trong các khoảng thời gian, vì vậy không đồng nghĩa trực tiếp với phần trăm CPU.

Các dấu hiệu nên đối chiếu:

| Quan sát | Ý nghĩa có thể có | Cần kiểm tra thêm |
|---|---|---|
| CPU user cao, run queue tăng | Truy vấn hoặc tiến trình đang cần nhiều tính toán | CPU time theo query, số luồng chạy, kế hoạch sort/join |
| CPU system cao | Kernel xử lý nhiều system call, mạng hoặc I/O | Context switch, interrupt, network, I/O và tiến trình gây tải |
| Một lõi cao, lõi khác thấp | Tải lệch hoặc công việc đơn luồng | Phân bố worker, affinity, giới hạn một luồng |
| CPU thấp, iowait và độ trễ truy vấn cao | Có thể đang chờ lưu trữ | I/O latency, queue depth, physical reads và wait events |
| Steal cao trong máy ảo | Máy ảo không được cấp đủ thời gian CPU | Chỉ số hypervisor và mức tranh chấp host |
| Container bị throttling | CPU quota giới hạn thời gian chạy | cpu.max, cpu.stat hoặc metric tương đương |

### Lệnh quan sát trên Linux

Các lệnh sau là ví dụ phổ biến; tên gói và quyền truy cập có thể khác giữa các bản phân phối:

```bash
# Quan sát từng lõi CPU theo chu kỳ 1 giây
mpstat -P ALL 1

# Quan sát tải, hàng đợi, bộ nhớ và I/O tổng quát
vmstat 1

# Xem tiến trình và luồng đang dùng CPU
pidstat -u -t -p <PID> 1

# Xem nhanh trạng thái hệ thống
top
```

Trong vmstat, cần bỏ qua hoặc đánh giá riêng dòng đầu tiên nếu đó là số liệu trung bình từ lúc khởi động. Các dòng sau phản ánh khoảng lấy mẫu. Trường r gần đúng số tác vụ chờ CPU hoặc đang chạy; b thể hiện tác vụ ở trạng thái chờ không ngắt được. Hãy đọc cùng mpstat, vì một con số trung bình không cho biết lõi nào đang bão hòa.

Trên Windows, có thể dùng Performance Monitor hoặc PowerShell:

```powershell
# CPU toàn hệ thống
Get-Counter '\Processor(_Total)\% Processor Time'

# CPU theo tiến trình
Get-Counter '\Process(*)\% Processor Time'
```

Tên bộ đếm và cách chuẩn hóa giá trị theo số lõi có thể khác giữa phiên bản Windows. Khi theo dõi tiến trình cơ sở dữ liệu, nên lọc đúng instance thay vì chỉ lấy giá trị tổng của mọi tiến trình.

## 3. Bộ nhớ: RAM khả dụng, cache, swap và áp lực cấp phát

Cơ sở dữ liệu dùng bộ nhớ để lưu trang dữ liệu, chỉ mục, vùng làm việc cho sort/hash, cache nội bộ và trạng thái giao dịch. Thiếu bộ nhớ có thể làm tăng đọc vật lý, khiến truy vấn tràn vùng làm việc ra đĩa, gây swap hoặc thậm chí khiến hệ điều hành kết thúc tiến trình.

### Hiểu đúng số RAM đã dùng

RAM được dùng cho nhiều mục đích: tiến trình, kernel, page cache, buffer cache và các dịch vụ khác. Trên Linux, nhìn vào cột used đơn lẻ không đủ để kết luận máy đã hết RAM. Bộ nhớ dùng làm cache của hệ điều hành có thể được thu hồi khi ứng dụng cần.

MemAvailable trong free là một ước lượng lượng bộ nhớ có thể cấp cho ứng dụng mà không cần swap đáng kể. Đây thường là chỉ số hữu ích hơn phép tính tổng RAM trừ free. Dù vậy, cần xem xu hướng theo thời gian và các giới hạn cgroup, vì host còn RAM không có nghĩa container được phép sử dụng toàn bộ số đó.

Các khái niệm quan trọng:

- **RSS (Resident Set Size):** lượng trang của tiến trình đang nằm trong RAM; một số vùng dùng chung có thể được tính trong RSS của nhiều tiến trình.
- **Virtual memory:** không gian địa chỉ ảo mà tiến trình ánh xạ; không đồng nghĩa với RAM vật lý đang dùng.
- **Page cache:** cache của hệ điều hành cho nội dung file; có thể giúp đọc dữ liệu hoặc log đã nằm trong cache nhanh hơn.
- **Swap:** vùng lưu trữ dùng làm nơi chứa trang bộ nhớ được đưa ra khỏi RAM. Swap hoạt động liên tục có thể làm độ trễ tăng mạnh.
- **Page fault:** sự kiện truy cập trang chưa có trong ánh xạ bộ nhớ hiện tại. Minor fault có thể xử lý mà không cần đọc từ đĩa; major fault thường cần I/O để nạp trang.
- **OOM (Out Of Memory):** tình trạng hệ điều hành hoặc bộ quản lý bộ nhớ trong container không thể cấp thêm bộ nhớ và có thể kết thúc một tiến trình.

### Các chỉ số cần theo dõi

| Chỉ số | Dấu hiệu cần chú ý | Tác động có thể gặp |
|---|---|---|
| MemAvailable / Available MBytes | Giảm liên tục, gần giới hạn cấp phát | Ứng dụng khó cấp thêm RAM |
| Swap in/out | Hoạt động tăng kéo dài | Truy cập bộ nhớ có thể phải chờ đĩa |
| Major page faults | Tăng cùng độ trễ | Có thể phải nạp trang từ lưu trữ |
| RSS tiến trình DB | Tăng nhanh hoặc sát giới hạn | Nguy cơ vượt quota hoặc OOM |
| Cache/buffer hit của DB | Giảm cùng physical reads tăng | Nhiều lần đọc phải đi xuống tầng lưu trữ |
| Spill to disk | Sort/hash tràn ra file tạm | Truy vấn dùng thêm I/O và thời gian |
| OOM events | Có sự kiện kill hoặc allocation failure | Tiến trình có thể bị dừng, giao dịch bị gián đoạn |

Không phải mọi hoạt động swap đều gây vấn đề. Một số trang ít được dùng có thể nằm trong swap mà không ảnh hưởng đáng kể. Điều đáng quan tâm là swap-in/swap-out tăng liên tục cùng độ trễ, major faults và áp lực bộ nhớ.

### Lệnh quan sát trên Linux

```bash
# RAM, cache và swap
free -h

# Paging, swap, run queue và I/O theo chu kỳ
vmstat 1

# Bộ nhớ và lỗi trang theo tiến trình
pidstat -r -p <PID> 1

# Các vùng nhớ và giới hạn của tiến trình (nếu được phép)
cat /proc/<PID>/status
```

Trong môi trường container dùng cgroup v2, các file như memory.current, memory.max, memory.events có thể cho biết lượng bộ nhớ đang dùng, giới hạn và sự kiện vượt ngưỡng. Đường dẫn thực tế phụ thuộc runtime và cách mount cgroup. Khi memory.events ghi nhận oom hoặc oom_kill, cần kiểm tra thời điểm đó cùng log của container và tiến trình.

Trên Windows, có thể theo dõi Memory\Available MBytes, Memory\Committed Bytes, Memory\Pages/sec, cùng working set của tiến trình bằng Performance Monitor hoặc Get-Counter. Pages/sec không tự nó chứng minh có vấn đề: cần đối chiếu với page faults, paging I/O, độ trễ ứng dụng và lượng RAM khả dụng.

### Liên hệ bộ nhớ hệ điều hành với buffer pool của DB

Hệ quản trị thường có cache riêng. Hệ điều hành cũng có page cache. Tùy cấu hình truy cập file và hệ quản trị, hai lớp cache có thể cùng tồn tại hoặc DB dùng cơ chế I/O hạn chế page cache. Vì vậy, không nên cộng RSS, kích thước buffer pool và page cache một cách máy móc rồi kết luận đó là lượng RAM duy nhất đang sử dụng.

Khi DB cache hit giảm, hãy kiểm tra cả working set, bộ nhớ dành cho sort/hash, page cache và giới hạn tiến trình. Nếu tăng buffer pool, phần RAM dành cho hệ điều hành và các tiến trình khác có thể giảm. Một cấu hình khiến DB cache tốt hơn nhưng đẩy host vào swap hoặc OOM có thể làm toàn hệ thống chậm hơn.

## 4. Đĩa và lưu trữ: IOPS, thông lượng, độ trễ và hàng đợi

Cơ sở dữ liệu thường đọc trang dữ liệu, ghi log, flush checkpoint, tạo file tạm và đọc backup. Hiệu năng lưu trữ không chỉ phụ thuộc vào dung lượng. Cần quan sát số thao tác mỗi giây, lượng dữ liệu truyền, độ trễ của từng thao tác và độ sâu hàng đợi.

### Bốn nhóm chỉ số chính

- **IOPS:** số thao tác đọc/ghi mỗi giây. Workload nhiều lần đọc nhỏ có thể cần IOPS cao dù tổng dung lượng truyền không lớn.
- **Throughput:** lượng dữ liệu đọc/ghi mỗi giây, thường là MB/s hoặc MiB/s. Quét tuần tự và backup thường tiêu thụ throughput đáng kể.
- **Latency:** thời gian hoàn thành một thao tác I/O. Độ trễ tăng có thể làm truy vấn chờ lâu, đặc biệt với truy cập ngẫu nhiên hoặc ghi đồng bộ.
- **Queue depth:** số yêu cầu I/O đang chờ hoặc đang được thiết bị xử lý. Hàng đợi tăng kéo dài có thể cho thấy thiết bị đang nhận tải vượt mức phục vụ hiệu quả.

Kích thước thao tác cũng quan trọng. 10.000 IOPS với mỗi thao tác 4 KiB có thông lượng rất khác 10.000 IOPS với mỗi thao tác 64 KiB. Cần đối chiếu cả IOPS và throughput để hiểu hình dạng tải.

### Đọc các chỉ số thiết bị

Trên Linux, iostat -xz 1 thường hiển thị các trường như:

| Trường | Ý nghĩa |
|---|---|
| r/s, w/s | Số thao tác đọc/ghi mỗi giây |
| rkB/s, wkB/s | Lượng dữ liệu đọc/ghi mỗi giây |
| r_await, w_await | Thời gian trung bình của thao tác đọc/ghi, bao gồm thời gian chờ và phục vụ theo cách đo của công cụ |
| aqu-sz | Độ sâu hàng đợi trung bình |
| %util | Tỷ lệ thời gian thiết bị có ít nhất một I/O đang hoạt động theo cách tính của công cụ |

Ví dụ:

```bash
# Theo dõi từng thiết bị khối mỗi giây
iostat -xz 1

# Theo dõi I/O theo tiến trình
pidstat -d -p <PID> 1

# Xem thiết bị, filesystem và dung lượng mount
lsblk
df -h
```

Không nên dùng %util làm tiêu chí duy nhất. Với thiết bị lưu trữ hiện đại có khả năng xử lý song song, %util gần 100% không nhất thiết đồng nghĩa thiết bị đã hết năng lực. Cần xem độ trễ, throughput, IOPS, queue depth và giới hạn của loại thiết bị hoặc volume đang dùng.

Tương tự, await là giá trị trung bình; một số thao tác có thể chậm hơn rất nhiều. Hãy so sánh với phân vị độ trễ nếu nền tảng lưu trữ hoặc hệ thống giám sát cung cấp. Nếu chỉ có số trung bình, hãy xem thêm phân bố và thời điểm spike.

### Phân biệt các đường I/O của cơ sở dữ liệu

Không phải mọi I/O đều có cùng tính chất:

- **Data file:** đọc trang cần cho truy vấn và ghi trang đã thay đổi theo cơ chế của hệ quản trị.
- **Transaction log/WAL:** ghi tuần tự và thường có yêu cầu flush khi commit. Độ trễ ghi log có thể ảnh hưởng trực tiếp đến thời gian commit.
- **Temporary files:** dùng cho sort, hash, spill hoặc truy vấn lớn. Tăng I/O file tạm có thể chỉ ra vùng làm việc không đủ hoặc truy vấn xử lý quá nhiều dữ liệu.
- **Checkpoint và background writer:** ghi các trang bẩn ra đĩa; hoạt động dồn dập có thể tạo đỉnh ghi.
- **Backup và archive:** đọc hoặc ghi lượng lớn dữ liệu, có thể cạnh tranh băng thông với workload tương tác.

Nếu data file và WAL nằm trên các volume khác nhau, cần đo riêng từng volume. Nếu nhiều volume cùng nằm trên một thiết bị vật lý hoặc cùng một lớp lưu trữ cloud, việc tách mount point không đảm bảo chúng có năng lực I/O độc lập.

Dung lượng filesystem cũng cần được kiểm tra. Đĩa còn IOPS nhưng filesystem gần đầy, hết inode hoặc log tăng nhanh vẫn có thể khiến hệ thống không ghi được. Dùng df -h để xem dung lượng và df -i để xem inode trên Linux; trên Windows, kiểm tra dung lượng volume và các giới hạn storage liên quan.

Trên Windows, Performance Monitor có thể theo dõi PhysicalDisk hoặc LogicalDisk, ví dụ Avg. Disk sec/Read, Avg. Disk sec/Write, Disk Reads/sec, Disk Writes/sec, Disk Bytes/sec và Current Disk Queue Length. Cần chọn đúng instance volume/thiết bị và đối chiếu với chỉ số storage của nền tảng ảo hóa hoặc cloud nếu có.

## 5. Mạng: thông lượng, độ trễ, mất gói và kết nối

Mạng ảnh hưởng đến kết nối từ ứng dụng đến DB, giao tiếp giữa các node, sao chép dữ liệu, backup từ xa và dịch vụ lưu trữ mạng. Một truy vấn có thể xử lý nhanh trong DB nhưng ứng dụng vẫn nhận kết quả chậm nếu đường truyền có RTT cao, retransmit hoặc băng thông bị bão hòa.

### Chỉ số mạng quan trọng

- **Throughput:** số byte hoặc bit truyền mỗi giây theo chiều nhận và gửi.
- **RTT (round-trip time):** thời gian một gói đi đến đích và phản hồi quay lại. RTT cao làm tăng chi phí của nhiều lần trao đổi tuần tự.
- **Packet loss và retransmission:** gói bị mất hoặc phải truyền lại; thường làm tăng độ trễ và giảm thông lượng hiệu dụng.
- **Errors và drops:** lỗi giao diện hoặc gói bị loại do hàng đợi, cấu hình hay giới hạn thiết bị.
- **Connection count và socket state:** số kết nối đang mở, trạng thái chờ, backlog và kết nối bất thường.
- **Bandwidth/queue saturation:** đường truyền hoặc hàng đợi mạng đạt giới hạn, khiến gói phải chờ hoặc bị loại.

Tăng số kết nối không nhất thiết tăng thông lượng. Quá nhiều kết nối đồng thời có thể tăng chi phí context switch, bộ nhớ socket, TLS handshake và số phiên DB. Pool kết nối có giới hạn thường giúp kiểm soát tải tốt hơn.

### Lệnh quan sát trên Linux

```bash
# Thông lượng và lỗi theo giao diện
sar -n DEV 1

# Bộ đếm lỗi, drop của giao diện
ip -s link

# Tóm tắt socket và kết nối
ss -s

# Thống kê TCP toàn hệ thống
nstat

# Chi tiết TCP của các socket đang hoạt động
ss -ti
```

Các bộ đếm từ ethtool -S <interface> có thể cho biết thêm lỗi driver hoặc NIC, nhưng tên trường phụ thuộc nhà cung cấp. Không nên so sánh trực tiếp các trường không cùng định nghĩa giữa những loại card mạng khác nhau.

Trên Windows, có thể theo dõi Network Interface(*)\Bytes Total/sec, Packets Received Errors, Packets Outbound Errors, cùng bộ đếm TCP retransmission trong Performance Monitor. Get-NetAdapterStatistics cũng giúp kiểm tra số gói lỗi hoặc bị loại trên adapter.

### Phân biệt độ trễ mạng với độ trễ truy vấn

Thời gian một truy vấn ở phía ứng dụng có thể bao gồm kết nối, gửi lệnh, DB xử lý, truyền kết quả và giải mã dữ liệu. Nếu DB báo execution time thấp nhưng thời gian ứng dụng cao, hãy kiểm tra:

- Thời gian chờ lấy connection từ pool.
- RTT giữa ứng dụng và DB.
- Số lần trao đổi tuần tự (round trips) của ứng dụng.
- Số hàng và kích thước dữ liệu trả về.
- Retransmission, packet drops và trạng thái interface.
- Đường mạng đến replica hoặc storage nếu truy vấn đọc/ghi qua dịch vụ đó.

Một truy vấn trả về hàng trăm nghìn bản ghi có thể tốn nhiều thời gian truyền dữ liệu ngay cả khi kế hoạch thực thi nhanh. Khi đó, giảm số cột, lọc dữ liệu gần DB hơn hoặc phân trang có thể hiệu quả hơn việc thêm chỉ mục.

## 6. Tài nguyên trong máy ảo và container

Trong môi trường ảo hóa, số liệu host và guest có thể khác nhau. Máy ảo nhìn thấy số CPU ảo và RAM được cấp, nhưng hypervisor vẫn phải chia sẻ tài nguyên vật lý. CPU steal tăng có thể cho thấy máy ảo bị tranh CPU. Storage hoặc network ảo cũng có thể bị giới hạn bởi tầng host.

Trong container, giới hạn cgroup có thể thấp hơn tài nguyên toàn máy:

- CPU quota có thể giới hạn tổng thời gian CPU mà container được sử dụng trong mỗi chu kỳ.
- CPU throttling có thể xảy ra dù CPU toàn host chưa bão hòa.
- Memory limit có thể kích hoạt OOM trong container dù host còn RAM.
- I/O controller có thể giới hạn throughput hoặc IOPS của container.

Trên Linux cgroup v2, các file thường hữu ích gồm cpu.max, cpu.stat, memory.current, memory.max, memory.events và io.stat. Tên và đường dẫn thực tế phụ thuộc cấu hình runtime. Hãy so sánh mức sử dụng với giới hạn của đúng cgroup chứa tiến trình DB.

Nếu cơ sở dữ liệu chạy trong Kubernetes, cần phân biệt request và limit của container, trạng thái throttling, memory working set và node pressure. CPU request không phải cam kết rằng container luôn được dùng riêng lượng CPU đó; CPU limit mới là giới hạn trên trong cách cấu hình phổ biến.

Một quy trình chẩn đoán container nên xem cả:

1. Metric của node.
2. Metric của pod/container.
3. Metric tiến trình DB.
4. Giới hạn CPU, RAM, I/O được cấu hình.
5. Sự kiện restart, OOMKilled, throttling hoặc eviction.

Chỉ nhìn metric node có thể bỏ sót container bị giới hạn. Chỉ nhìn container cũng có thể bỏ sót node đang thiếu tài nguyên hoặc storage dùng chung bị bão hòa.

## 7. Đối chiếu các chỉ số để tìm nút thắt

Hãy đọc các chỉ số theo cùng một khoảng thời gian, sau đó đối chiếu với trạng thái DB và ứng dụng. Bảng sau là hướng dẫn hình thành giả thuyết, không phải quy tắc kết luận tự động.

| Tổ hợp quan sát | Giả thuyết cần kiểm tra | Bằng chứng tiếp theo |
|---|---|---|
| CPU cao, run queue cao, I/O latency bình thường | Nút thắt tính toán hoặc quá nhiều công việc đồng thời | CPU time theo query, execution plan, số worker, throttling |
| CPU thấp, iowait tăng, await tăng | Lưu trữ đang phản hồi chậm | IOPS, queue depth, data/log/temp volume, DB I/O waits |
| RAM khả dụng giảm, swap-in/out và major faults tăng | Áp lực bộ nhớ | RSS, cgroup limit, OOM events, DB cache và spill |
| Disk throughput cao, độ trễ tăng theo | Quét dữ liệu lớn hoặc nhiều job ghi/đọc cạnh tranh | Query fingerprint, batch, backup, checkpoint, file tạm |
| Network retransmit/drop tăng, DB execution time thấp | Vấn đề trên đường truyền hoặc NIC | RTT, interface errors, socket, firewall và mạng trung gian |
| CPU toàn host thấp nhưng CPU container bị throttling | Giới hạn cgroup | cpu.stat, quota, limit và metric container |
| CPU steal tăng và độ trễ CPU-bound tăng | Tranh chấp tài nguyên hypervisor | Metric host/hypervisor và thời điểm spike |
| I/O ổn định nhưng lock wait tăng | Tranh chấp giao dịch | Blocking session, transaction age, deadlock và thứ tự khóa |
| Host bình thường nhưng pool wait tăng | Ứng dụng thiếu kết nối khả dụng hoặc giữ kết nối quá lâu | Pool active/idle, thời gian giữ connection, request queue |

Một điểm quan trọng: iowait cao không chỉ rõ tiến trình nào đang chờ và không phải bằng chứng duy nhất của storage bottleneck. Tương tự, disk %util cao không tự chứng minh thiết bị đã hết công suất; retransmit tăng không nhất thiết do NIC tại máy DB. Hãy dùng nhiều bằng chứng và khoanh vùng theo đường đi của yêu cầu.

## 8. Ví dụ chẩn đoán một truy vấn chậm

Giả sử người dùng báo cáo màn hình lịch sử giao dịch chậm vào buổi sáng. Ứng dụng ghi nhận p95 tăng từ 180 ms lên 1,4 giây. Truy vấn ở DB có execution time tăng, nhưng số lần chạy và tham số lọc gần như không đổi.

### Bước 1: Đối chiếu CPU

CPU toàn host khoảng 35%, run queue không tăng và CPU time của tiến trình DB không tăng đáng kể. Điều này làm giả thuyết CPU bão hòa kém thuyết phục, nhưng chưa loại trừ việc một lõi hoặc container bị giới hạn. Kiểm tra từng lõi và cgroup cho thấy không có throttling đáng kể.

### Bước 2: Đối chiếu bộ nhớ

RAM khả dụng ổn định, không có swap-in/swap-out kéo dài, major page faults không tăng và DB không ghi nhận spill mới. Áp lực bộ nhớ không phải giả thuyết ưu tiên ở thời điểm này.

### Bước 3: Đối chiếu đĩa

Trong cùng khoảng thời gian, r_await của volume chứa data file tăng rõ rệt, queue depth tăng và số physical reads của truy vấn tăng. Volume WAL không có thay đổi tương ứng. Một job báo cáo nền vừa bắt đầu quét nhiều phân vùng dữ liệu lịch sử.

### Bước 4: Đối chiếu mạng và DB

RTT, retransmit và packet drops không thay đổi. Execution plan cho thấy truy vấn đọc nhiều trang hơn dự kiến; job báo cáo đang cạnh tranh I/O trên cùng volume. Các dữ kiện phù hợp với giả thuyết lưu trữ bị tranh chấp do workload nền.

### Bước 5: Thử thay đổi và xác minh

Có thể thử phân tán lịch job, giới hạn tốc độ đọc của batch hoặc chạy báo cáo trên replica nếu độ trễ sao chép phù hợp. Sau thay đổi, chạy lại cùng workload và đo p95 truy vấn tương tác, r_await, queue depth, physical reads, thời gian hoàn tất job và replication lag.

Nếu p95 giảm nhưng job kéo dài quá thời hạn nghiệp vụ, giải pháp chưa đạt yêu cầu tổng thể. Cần tìm điểm cân bằng giữa độ trễ tương tác và thời gian hoàn tất tác vụ nền.

## 9. Quy trình thu thập và đối chiếu trong thực tế

Một lần điều tra nên có phạm vi rõ ràng để kết quả có thể lặp lại:

1. **Xác định triệu chứng.** Ghi truy vấn hoặc endpoint bị ảnh hưởng, thời điểm bắt đầu, phạm vi người dùng và mức thay đổi của p95/p99.
2. **Chọn khoảng baseline.** Lấy một khoảng trước sự cố có workload tương đương; tránh so sánh giờ thấp điểm với giờ cao điểm.
3. **Đồng bộ mốc thời gian.** Đảm bảo log ứng dụng, DB, hệ điều hành và nền tảng hạ tầng có timezone rõ ràng và đồng hồ được đồng bộ.
4. **Ghi số liệu host.** CPU theo lõi, run queue, memory available, swap, page faults, IOPS, throughput, latency, queue depth và network errors.
5. **Ghi số liệu tiến trình và giới hạn.** CPU/RSS/I/O của DB, cgroup quota, memory limit, container restart và trạng thái máy ảo.
6. **Ghi số liệu DB.** Query fingerprint, execution plan, số hàng thực tế, buffer hit, physical reads, lock waits, commit latency và replication lag.
7. **Đối chiếu sự kiện.** Kiểm tra job định kỳ, backup, checkpoint, triển khai, thay đổi cấu hình và hoạt động khác cùng thời điểm.
8. **Nêu giả thuyết có thể kiểm chứng.** Ví dụ: một job đọc lớn gây tăng queue depth trên volume dữ liệu; hoặc CPU quota khiến tiến trình DB bị throttling.
9. **Thay đổi có kiểm soát.** Chỉ thay đổi yếu tố đã chọn, giữ nguyên điều kiện tải và ghi lại cấu hình trước/sau.
10. **Xác minh toàn diện.** So sánh p95/p99, throughput, lỗi, tài nguyên host, chỉ số DB và tác động lên các workload liên quan.

Với điều tra kéo dài, nên dùng công cụ thu thập định kỳ như sar hoặc nền tảng giám sát để giữ lịch sử. Các lệnh xem trạng thái tức thời chỉ hữu ích nếu được chạy đúng lúc sự cố. Hãy giữ đủ độ phân giải để thấy spike nhưng tránh lấy mẫu quá dày gây thêm tải hoặc tạo lượng metric không cần thiết.

## 10. Xây dựng bộ lệnh kiểm tra nhanh

Ví dụ trên Linux:

```bash
# CPU theo từng lõi
mpstat -P ALL 1

# CPU và I/O theo tiến trình
pidstat -u -d -p <PID> 1

# Bộ nhớ, swap, run queue và paging
free -h
vmstat 1

# I/O theo thiết bị
iostat -xz 1

# Network interface và TCP
sar -n DEV 1
ip -s link
ss -s
nstat
```

Không nhất thiết chạy tất cả lệnh cùng lúc trên mọi máy. Hãy chọn công cụ phù hợp, kiểm tra quyền và cài đặt trước, đồng thời lưu kết quả kèm timestamp. Với Windows, dùng Performance Monitor hoặc Get-Counter để lấy CPU, memory, physical disk và network interface; Resource Monitor có thể hỗ trợ quan sát tiến trình và I/O tức thời.

Khi cần xem trạng thái tiến trình trên Linux, pidstat và /proc/<PID>/status giúp gắn số liệu với tiến trình. Nếu PID thay đổi sau restart, cần xác định lại tiến trình đúng thay vì dùng PID cũ. Một số hệ quản trị tạo nhiều tiến trình con; tổng tài nguyên của tiến trình cha có thể không bao gồm hoặc không trình bày đúng toàn bộ nhóm tiến trình theo cách mong đợi.

## 11. Những sai lầm khi diễn giải metric

- **Nhìn CPU trung bình rồi kết luận:** một lõi có thể bão hòa trong khi tổng CPU còn thấp.
- **Coi load average là CPU utilization:** load average còn tính các tác vụ chờ không ngắt được và phụ thuộc số lõi.
- **Coi RAM used là RAM hết:** page cache có thể thu hồi; cần xem available, swap và áp lực thực tế.
- **Coi swap có hoạt động là lỗi:** cần phân biệt trang ít dùng nằm trong swap với swap-in/out liên tục làm tăng độ trễ.
- **Dùng %util làm kết luận duy nhất về đĩa:** cần xem latency, IOPS, throughput và queue depth.
- **Chỉ xem tổng I/O của host:** có thể bỏ sót volume WAL, file tạm hoặc thiết bị cụ thể bị bão hòa.
- **Coi network throughput thấp là mạng tốt:** RTT cao, mất gói hoặc giới hạn kết nối vẫn có thể gây chậm.
- **Bỏ qua quota container và steal time:** host có vẻ nhàn nhưng workload thực tế vẫn bị giới hạn.
- **So sánh hai khoảng thời gian không tương đương:** số người dùng, dữ liệu, cache và job chạy khác nhau làm kết quả mất ý nghĩa.
- **Chỉ xem metric mà không xem execution plan và wait event:** dễ nhầm giữa truy vấn tốn CPU, truy vấn chờ I/O và giao dịch bị khóa.

## 12. Checklist trước khi kết luận nút thắt

| Câu hỏi | Đã kiểm tra? |
|---|---|
| Metric có cùng mốc thời gian và cùng phạm vi host/container/process không? |  |
| CPU theo lõi, run queue, steal và throttling đã được xem xét chưa? |  |
| Memory available, swap, page faults, OOM và giới hạn cgroup đã được kiểm tra chưa? |  |
| Data, WAL/log, temp và backup có được phân biệt theo volume không? |  |
| IOPS, throughput, latency, queue depth và dung lượng filesystem đã được đối chiếu chưa? |  |
| Network RTT, retransmit, drops, errors và connection pool wait đã được xem xét chưa? |  |
| Query fingerprint, execution plan, lock wait và DB wait events có cùng thời điểm không? |  |
| Job nền, backup, checkpoint hoặc thay đổi cấu hình có trùng thời điểm không? |  |
| Kết quả sau điều chỉnh có đo cả workload liên quan và kiểm tra tính đúng đắn không? |  |

## 13. Nguyên tắc ra quyết định

CPU, bộ nhớ, đĩa và mạng là các phần của cùng một đường xử lý. CPU cao có thể là kết quả của truy vấn tốn tính toán; CPU thấp cùng I/O latency cao có thể là chờ lưu trữ; bộ nhớ thiếu có thể đẩy truy vấn sang spill hoặc swap; mạng kém có thể khiến ứng dụng chờ dù DB đã hoàn tất phần xử lý. Mỗi giả thuyết phải được kiểm tra bằng số liệu ở đúng phạm vi.

Khi đã xác định tài nguyên giới hạn, hãy liên kết nó với cơ chế của cơ sở dữ liệu: truy vấn nào đọc nhiều trang, giao dịch nào giữ khóa, batch nào tạo log, hoặc kết quả nào truyền quá nhiều dữ liệu. Sau khi điều chỉnh chỉ mục, SQL, concurrency, lịch job hay cấu hình tài nguyên, đo lại trong cùng điều kiện và kiểm tra cả tác động phụ.

Một kết luận tốt chỉ rõ triệu chứng, bằng chứng, nguyên nhân có khả năng nhất, thay đổi đã thử và kết quả đo sau thay đổi. Cách làm đó biến metric hệ điều hành thành công cụ chẩn đoán hiệu năng cơ sở dữ liệu thay vì một tập biểu đồ rời rạc.

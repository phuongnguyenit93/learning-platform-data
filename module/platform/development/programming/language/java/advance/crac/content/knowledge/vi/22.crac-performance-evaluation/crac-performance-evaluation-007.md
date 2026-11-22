# Ảnh hưởng của cache hệ điều hành, page fault và tốc độ ổ đĩa

Hiệu năng của ứng dụng Java không chỉ phụ thuộc vào CPU, JIT hay thuật toán. Việc đọc và ghi dữ liệu còn chịu ảnh hưởng của page cache của hệ điều hành, page fault, bộ nhớ vật lý, swap, filesystem và tốc độ thiết bị lưu trữ. Với CRaC, các yếu tố này xuất hiện ở cả lúc tạo checkpoint, lưu checkpoint artifact, restore tiến trình và khi ứng dụng bắt đầu truy cập lại dữ liệu.

Một checkpoint có thể được tạo rất nhanh trên máy có cache nóng nhưng restore chậm trên host khác có cache lạnh. Ngược lại, một lần đo restore nhanh có thể chỉ phản ánh việc checkpoint file đã nằm sẵn trong page cache, không phải tốc độ thực của ổ đĩa. Muốn đánh giá đúng, cần tách thời gian đọc checkpoint, thời gian phục hồi trạng thái JVM, page fault trong workload và I/O nghiệp vụ sau restore.

## 1. Page cache của hệ điều hành là gì?

Page cache là vùng bộ nhớ mà kernel dùng để lưu các trang dữ liệu của file đã được đọc hoặc ghi. Khi ứng dụng đọc file, kernel có thể lấy dữ liệu từ RAM nếu trang tương ứng đã có trong cache; nếu chưa có, kernel cần lấy trang từ filesystem hoặc thiết bị lưu trữ rồi mới cung cấp cho ứng dụng.

Trên Linux, page cache thường được quản lý ở phạm vi toàn hệ thống. Nhiều process đọc cùng một file có thể dùng chung các trang cache của file đó. Page cache không phải heap Java và không thuộc riêng một object hoặc JVM.

Ví dụ:

~~~text
Ứng dụng Java đọc file
       |
       v
read() / FileChannel / memory mapping
       |
       v
Kernel tra page cache
       |
       +---- Trang đã có trong RAM
       |          |
       |          v
       |      Trả dữ liệu cho ứng dụng
       |
       +---- Trang chưa có trong cache
                  |
                  v
             Filesystem / block layer
                  |
                  v
             SSD / HDD / network storage
                  |
                  v
             Nạp trang vào RAM
                  |
                  v
             Trả dữ liệu cho ứng dụng
~~~

Nếu file được đọc nhiều lần và các trang vẫn còn trong RAM, những lần đọc sau có thể nhanh hơn đáng kể. Nếu hệ thống thiếu RAM, kernel có thể thu hồi page cache để dành bộ nhớ cho workload khác. Lần đọc kế tiếp phải lấy lại dữ liệu từ storage.

### Page cache không giống cache trong ứng dụng

Ứng dụng có thể có nhiều tầng cache:

- Cache object trong heap, ví dụ Caffeine hoặc một Map.
- Cache dữ liệu trong thư viện, HTTP client hoặc ORM.
- Buffer của Java stream hoặc NIO.
- Page cache của kernel.
- Cache của controller, SSD hoặc storage service.

Một lần đọc có thể được phục vụ từ một trong các tầng này. Nếu cache ứng dụng trả kết quả, có thể không phát sinh syscall đọc file. Nếu ứng dụng gọi read nhưng page cache đã nóng, kernel có thể không cần đọc thiết bị. Nếu page cache lạnh, dữ liệu có thể phải được đọc từ storage.

Khi đo hiệu năng, cần xác định tầng cache nào đang được kiểm tra. Chỉ thấy lần đọc thứ hai nhanh hơn chưa đủ để kết luận page cache là nguyên nhân; cache trong ứng dụng, JIT, DNS, connection pool và các trạng thái khác cũng có thể đã nóng lên.

## 2. Page fault là gì?

Page fault xảy ra khi CPU hoặc tiến trình truy cập một virtual memory page mà mapping hiện tại chưa sẵn sàng theo cách cần thiết. Kernel xử lý fault và quyết định cách cung cấp trang hoặc báo lỗi.

Page fault không mặc nhiên là lỗi ứng dụng. Nó là một phần bình thường của cơ chế virtual memory.

Các tình huống có thể gây page fault:

- Trang của file được memory-map nhưng chưa được đưa vào RAM.
- Trang anonymous memory chưa được cấp backing page vật lý.
- Một trang đã bị swap ra và cần được đọc lại.
- Một trang copy-on-write cần được tách riêng khi process ghi vào.
- Mapping không hợp lệ hoặc quyền truy cập không cho phép, dẫn tới lỗi như SIGSEGV.

### Minor page fault

Minor page fault được xử lý mà không cần đọc trang dữ liệu từ thiết bị lưu trữ. Ví dụ có thể gồm:

- Trang đã có trong page cache hoặc RAM và chỉ cần thiết lập mapping cho process.
- Kernel cấp một trang zero-filled cho anonymous memory.
- Copy-on-write tạo một bản sao trang trong RAM.
- Một mapping có thể được hoàn thiện từ trạng thái bộ nhớ đã có sẵn.

Minor fault vẫn tiêu tốn CPU và thời gian kernel. Nếu số lượng rất lớn, nó có thể ảnh hưởng latency, nhưng thường không có độ trễ I/O storage như major fault.

### Major page fault

Major page fault cần một thao tác I/O để hoàn tất fault. Ví dụ, trang file-backed chưa có trong RAM phải được đọc từ backing storage, hoặc trang anonymous đã bị swap out cần được đọc lại.

Major fault thường đắt hơn minor fault vì có thể phải chờ storage. Tuy nhiên, không nên đồng nhất major fault với một lần đọc trực tiếp từ ổ SSD cục bộ: backing storage có thể là network filesystem, volume ảo, thiết bị mã hóa hoặc một tầng storage khác.

Một số công cụ báo số lượng minor và major fault của process. Đây là tín hiệu chẩn đoán, không phải phép đo trực tiếp số byte đọc từ ổ đĩa hoặc tổng độ trễ I/O.

### Phân biệt page fault với exception trong Java

Page fault ở tầng memory management không giống Java exception như IOException, OutOfMemoryError hoặc NullPointerException.

- Minor/major page fault là sự kiện kernel xử lý virtual memory.
- IOException thường là lỗi mà API I/O Java trả về.
- OutOfMemoryError phản ánh JVM không thể đáp ứng một yêu cầu cấp phát theo điều kiện runtime.
- SIGSEGV có thể xảy ra nếu process truy cập mapping không hợp lệ hoặc vi phạm quyền bộ nhớ.

Một ứng dụng có thể phát sinh nhiều page fault mà không ném exception nào. Ngược lại, một IOException không nhất thiết có liên quan đến page fault.

## 3. Vì sao cache nóng và cache lạnh tạo ra kết quả khác nhau?

Giả sử ứng dụng đọc một file checkpoint có kích thước vài GB.

**Cache nóng:** các trang của file đã nằm trong page cache. Kernel có thể phục vụ phần lớn lần đọc từ RAM. Thời gian đo thấp hơn và mức đọc vật lý từ thiết bị có thể rất nhỏ.

**Cache lạnh:** các trang chưa nằm trong page cache. Kernel phải lấy dữ liệu từ storage. Thời gian phụ thuộc latency thiết bị, throughput, queue depth, filesystem, vị trí file và cách đọc.

**Cache bị áp lực:** một phần file còn trong cache, phần khác đã bị thu hồi. Kết quả là hỗn hợp giữa cache hit và I/O. Hiệu năng có thể biến động giữa các lần chạy.

| Trạng thái | Nguồn dữ liệu chủ yếu | Dấu hiệu thường gặp |
|---|---|---|
| Cache nóng | RAM/page cache | Ít block read, thời gian đọc thấp |
| Cache lạnh | Storage hoặc backing filesystem | Nhiều major fault hoặc block read, latency tăng |
| Cache một phần | Kết hợp RAM và storage | Hiệu năng phụ thuộc vùng dữ liệu được truy cập |
| Memory pressure | Cache bị thu hồi liên tục | I/O lặp lại, fault và latency biến động |

Đọc tuần tự một file lớn thường tận dụng readahead của kernel và có thể đạt throughput cao. Đọc ngẫu nhiên các trang rải rác có thể chịu ảnh hưởng mạnh hơn từ latency và IOPS của storage. Hai workload cùng đọc 1 GB nhưng có pattern khác nhau có thể có thời gian rất khác.

## 4. Tốc độ ổ đĩa ảnh hưởng tới checkpoint như thế nào?

Tạo và sử dụng checkpoint có thể phát sinh nhiều loại I/O:

1. Ghi dữ liệu checkpoint ra filesystem hoặc volume.
2. Flush hoặc đồng bộ dữ liệu theo yêu cầu của công cụ.
3. Đóng gói, nén, mã hóa hoặc chuyển artifact tới kho lưu trữ.
4. Đọc checkpoint artifact khi restore.
5. Nạp lại các file cấu hình, thư viện hoặc dữ liệu mà ứng dụng truy cập sau restore.

Tốc độ storage ảnh hưởng trực tiếp tới các bước có I/O đồng bộ hoặc phải đọc lượng dữ liệu lớn. Nhưng tổng thời gian checkpoint/restore còn phụ thuộc CPU, memory bandwidth, compression, engine, filesystem, network và số lượng tài nguyên cần xử lý.

### Tạo checkpoint

Checkpoint engine có thể cần ghi một lượng lớn memory state ra storage. Thời gian ghi phụ thuộc:

- Dung lượng trạng thái cần lưu.
- Tốc độ ghi tuần tự và khả năng xử lý I/O của thiết bị.
- Số file và cách engine tổ chức dữ liệu.
- Compression hoặc encryption có bật hay không.
- Filesystem, mount option và container storage driver.
- Có phải chờ flush/fsync để bảo đảm dữ liệu bền vững hay không.
- Storage có bị chia sẻ với workload khác hay không.

Một ổ có throughput tuần tự cao vẫn có thể chậm khi checkpoint tạo nhiều file nhỏ hoặc cần flush đồng bộ liên tục. IOPS và latency cũng quan trọng.

### Restore checkpoint

Restore có thể cần đọc checkpoint artifact từ filesystem hoặc volume. Nếu artifact nằm trên local NVMe, network block volume, NFS hoặc object storage được mount, độ trễ và throughput có thể khác nhau.

Đặc biệt, không nên giả định mọi CRaC runtime restore theo cùng một chiến lược đọc. Có implementation nạp dữ liệu theo cách eager; có engine hoặc cấu hình hỗ trợ demand paging/lazy restore, trong đó một phần memory page chỉ được lấy khi process truy cập. Cần kiểm tra tài liệu và hành vi của đúng JDK distribution, checkpoint engine và phiên bản đang dùng.

Nếu restore dùng demand paging, process có thể bắt đầu hoạt động trước khi mọi trang của checkpoint đã được nạp. Khi đó, lần đầu truy cập một vùng nhớ chưa được nạp có thể phát sinh page fault và phải lấy dữ liệu từ checkpoint backing storage hoặc page server. Kết quả là thời gian đến trạng thái process chạy được có thể thấp, nhưng latency của request đầu tiên vẫn cao nếu request chạm nhiều trang chưa được nạp.

Nếu restore nạp phần lớn memory trước khi báo hoàn tất, thời gian startup có thể phản ánh phần I/O này trực tiếp. Không được suy luận chiến lược restore chỉ từ việc ứng dụng có CRaC Resource.

## 5. Ảnh hưởng của ổ HDD, SSD, NVMe và network storage

Các loại storage có đặc tính khác nhau:

| Loại storage | Đặc điểm tổng quát | Ảnh hưởng có thể thấy |
|---|---|---|
| HDD | Latency truy cập ngẫu nhiên cao hơn, throughput tuần tự phụ thuộc cơ học và vùng đĩa | Random page-in và nhiều file nhỏ có thể chậm |
| SATA SSD | Latency thấp hơn HDD, throughput và queue depth có giới hạn theo thiết bị/controller | Đọc/ghi checkpoint tuần tự thường tốt hơn HDD nhưng có giới hạn IOPS |
| NVMe SSD | Độ trễ thấp, khả năng xử lý queue và IOPS cao | Có lợi cho checkpoint lớn hoặc workload nhiều I/O ngẫu nhiên |
| Network block volume | Hiệu năng phụ thuộc mạng, vùng triển khai, QoS và mức tải volume | Latency có thể biến động theo thời điểm và vị trí host |
| NFS/network filesystem | Có thêm network round trip, metadata server và cache coherence | File nhỏ, metadata và truy cập ngẫu nhiên có thể chịu độ trễ đáng kể |
| Object storage qua gateway/mount | Thường có semantics và latency khác filesystem cục bộ | Không mặc định phù hợp làm backing path cho checkpoint engine |

Đây là so sánh định tính. Không có một con số throughput chung cho mọi SSD hoặc cloud volume. Cần đo đúng thiết bị, filesystem, mount option, workload và cấu hình triển khai.

### Throughput và latency là hai chỉ số khác nhau

- **Throughput** cho biết bao nhiêu dữ liệu được truyền trong một đơn vị thời gian, ví dụ MB/s.
- **IOPS** cho biết số thao tác I/O mỗi giây.
- **Latency** cho biết một thao tác mất bao lâu.
- **Queue depth** cho biết số thao tác I/O đang chờ hoặc đang được xử lý.

Đọc một file lớn tuần tự thường quan tâm throughput. Đọc nhiều page nhỏ rải rác có thể bị giới hạn bởi latency và IOPS. Một storage có throughput cao nhưng latency random-read lớn vẫn có thể làm request đầu tiên sau restore chậm.

## 6. Page cache và memory pressure trong container

Page cache sử dụng RAM của host và có thể được tính vào memory accounting của cgroup tùy loại dữ liệu và kernel. Trong container, giới hạn memory không chỉ liên quan đến heap Java. File cache, anonymous memory, page table, native allocation và các loại kernel memory có thể ảnh hưởng tới memory pressure.

Khi cgroup tiến gần memory limit:

- Kernel có thể thu hồi file cache.
- Process có thể phải đọc lại file từ storage.
- Reclaim và compaction có thể làm tăng latency.
- Nếu cấu hình cho phép, memory có thể bị swap; nếu không, container có thể bị OOM kill.
- Một workload khác trong cùng node có thể gây áp lực lên cache dùng chung.

Vì vậy, tăng -Xmx không phải lúc nào cũng cải thiện hiệu năng. Nếu heap chiếm gần hết cgroup limit, kernel còn ít RAM để giữ page cache và các native allocation. Ngược lại, giảm heap quá nhiều có thể làm GC tăng. Cần đo tổng memory của container và JVM.

### Quan sát memory cgroup trên Linux

Với cgroup v2, có thể đọc:

~~~shell
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.stat
cat /sys/fs/cgroup/memory.events
~~~

Trong memory.stat, các trường như anon, file, file_dirty, file_writeback giúp hiểu phần memory accounting thuộc anonymous memory và file cache. Tên/trường có thể thay đổi theo kernel. Trong container có cgroup namespace riêng, đường dẫn thực tế có thể khác; hãy xác định cgroup của process trước khi đọc.

Không nên xem toàn bộ trường file là cache checkpoint. Nó có thể bao gồm nhiều file được process hoặc cgroup sử dụng. Kết hợp với số liệu block I/O và workload cụ thể để tìm nguyên nhân.

## 7. Cache hệ điều hành sau CRaC restore

Checkpoint lưu trạng thái tiến trình, còn page cache là trạng thái do kernel quản lý. Không nên mặc định rằng page cache của host tạo checkpoint sẽ được chuyển nguyên vẹn sang host restore.

Một số tình huống:

- Restore trên cùng host: các trang checkpoint file có thể vẫn còn trong page cache, nếu chưa bị thu hồi.
- Restore trên host khác: page cache của host mới thường không chứa dữ liệu file chỉ vì host cũ đã đọc nó.
- Restore sau một thời gian dài: cache có thể đã bị reclaim do memory pressure.
- Restore từ volume mạng: cache của client/host mới và cache phía storage service có thể khác nhau.
- Restore với lazy paging: trang chưa được nạp có thể chỉ được đọc khi ứng dụng truy cập.

Điều này giải thích vì sao cùng một checkpoint có thể có thời gian restore khác nhau giữa các lần chạy hoặc giữa các node. Kết quả còn phụ thuộc artifact đã được đọc trước đó hay chưa.

### JIT warmup không làm nóng page cache của checkpoint

JIT warmup làm JVM thực thi method để thu thập profile và biên dịch code. Nó không bảo đảm các trang của checkpoint artifact hoặc file nghiệp vụ đã nằm trong page cache.

Ngược lại, đọc trước một file lớn có thể làm page cache nóng nhưng không làm các method Java đạt ngưỡng JIT. Hai hoạt động có mục tiêu và chi phí khác nhau:

| Hoạt động | Làm nóng điều gì? | Công cụ/biện pháp |
|---|---|---|
| JIT warmup | Profile và mã máy của method | Chạy workload tổng hợp trên đường code cần tối ưu |
| File pre-read | Page cache cho file được đọc | Đọc file có kiểm soát trước workload |
| Application cache warmup | Object/data trong cache của ứng dụng | Nạp key hoặc dữ liệu qua API cache |
| Dependency warmup | Connection, DNS, TLS hoặc client pool | Kiểm tra và tạo dependency theo lifecycle |

Không nên đọc toàn bộ checkpoint file trong startup chỉ để làm nóng cache nếu việc đó không được runtime yêu cầu. Nó có thể tăng I/O, tranh chấp memory và làm chậm các instance khác.

## 8. Đo page fault và I/O trên Linux

Nên kết hợp nhiều công cụ vì mỗi công cụ đo một khía cạnh.

### vmstat

~~~shell
vmstat 1
~~~

Một số cột hữu ích:

- si, so: lượng memory swap in/out theo đơn vị của công cụ.
- bi, bo: block input/output.
- r: số process runnable.
- wa: thời gian CPU chờ I/O theo cách tính của vmstat.
- free, buff, cache: chỉ số memory ở mức hệ thống.

vmstat cho cái nhìn toàn host, không chỉ process Java. Dùng nó để xác định có áp lực I/O hoặc swap trong thời gian checkpoint/restore hay không.

### pidstat

~~~shell
pidstat -r -d -p 2481 1
~~~

-r hiển thị memory và page fault statistics; -d hiển thị I/O của task. Kiểm tra help của phiên bản sysstat vì trường và đơn vị có thể khác nhau.

### iostat

~~~shell
iostat -xz 1
~~~

Các trường thường hữu ích gồm:

- r/s, w/s: số thao tác đọc/ghi mỗi giây.
- rkB/s, wkB/s: throughput đọc/ghi.
- r_await, w_await: thời gian chờ trung bình của I/O.
- aqu-sz: queue size trung bình.
- %util: mức bận của thiết bị theo cách báo cáo của công cụ.

Không diễn giải %util một mình như phần trăm năng lực còn lại, đặc biệt với thiết bị NVMe hoặc storage nhiều queue. Đọc thêm latency, queue depth và giới hạn của loại thiết bị.

### perf stat

~~~shell
perf stat -p 2481 -e page-faults,minor-faults,major-faults
~~~

Lệnh này đo các sự kiện page fault của process trong thời gian perf attach. Quyền perf có thể bị giới hạn bởi kernel policy hoặc container security. Một số nền tảng không cung cấp đầy đủ event hoặc yêu cầu cấu hình riêng.

### /proc và số liệu hệ thống

~~~shell
cat /proc/2481/stat
cat /proc/2481/status
cat /proc/meminfo
cat /proc/vmstat
~~~

/proc/PID/stat có các bộ đếm minor/major fault của process; /proc/meminfo và /proc/vmstat cung cấp số liệu toàn hệ thống. Đọc đúng định dạng và đơn vị của kernel đang dùng. Các bộ đếm hệ thống tích lũy từ boot, nên cần lấy mẫu trước/sau hoặc dùng công cụ theo dõi theo khoảng thời gian.

## 9. Phân biệt page fault với block I/O

Major fault là tín hiệu rằng một page fault cần I/O, nhưng không phải một phép đếm chính xác số thao tác đọc block của thiết bị. Một major fault có thể dẫn tới nhiều I/O; một lần đọc file có thể được readahead và phục vụ nhiều page fault; I/O có thể được đáp ứng từ network filesystem hoặc tầng cache khác.

Ngược lại, block I/O có thể phát sinh mà không tương ứng trực tiếp với major fault của process:

- Writeback page cache.
- Flush hoặc fsync.
- Read-ahead do kernel chủ động.
- I/O do process khác trên cùng host.
- I/O của filesystem metadata.
- Hoạt động của storage driver hoặc container runtime.

Khi phân tích restore:

1. Đo major/minor fault của process Java.
2. Đo block read/write của host hoặc device.
3. Đo thời gian đọc checkpoint artifact.
4. Quan sát latency của thiết bị và queue depth.
5. Đối chiếu timestamp với log CRaC runtime.

Nếu major fault tăng nhưng device read không tăng tương ứng, có thể dữ liệu được đáp ứng từ tầng cache hoặc backing store khác. Nếu device read tăng nhưng major fault của JVM thấp, có thể I/O đến từ engine, helper process, readahead hoặc writeback. Cần xem process và thiết bị nào thực sự thực hiện I/O.

## 10. Benchmark ảnh hưởng của cache và storage

Benchmark cần tách các biến để tránh kết luận sai. Một quy trình có thể gồm:

### Xác định câu hỏi cần đo

Ví dụ:

- Thời gian tạo checkpoint phụ thuộc throughput ghi như thế nào?
- Restore từ cache nóng và cache lạnh chênh lệch bao nhiêu?
- Storage latency ảnh hưởng tới thời gian tới readiness hay tới latency request đầu tiên?
- Lazy restore có làm major fault tăng khi traffic bắt đầu không?
- Memory pressure có làm page cache bị reclaim và khiến restore chậm không?

Không gộp mọi mục tiêu vào một con số startup duy nhất. Đo riêng checkpoint duration, restore duration, time-to-ready và latency sau restore.

### Kiểm soát môi trường

- Dùng cùng JDK vendor/build, CRaC runtime, engine và JVM flags.
- Dùng cùng checkpoint artifact hoặc tạo artifact theo cùng quy trình.
- Ghi lại container image digest, kernel, CPU và loại storage.
- Chạy trên host không có workload cạnh tranh hoặc ghi rõ workload cạnh tranh.
- Ghi memory limit, heap size, cgroup limit và swap policy.
- Dùng cùng network/storage region nếu dùng volume mạng.
- Lặp nhiều lần và ghi nhận phân phối, không chỉ lần chạy tốt nhất.

### So sánh cache nóng và cache lạnh

Một phép đo có thể chia thành hai nhóm:

**Nhóm cache nóng:** đọc checkpoint artifact một lần trước khi đo, sau đó restore và đo lần tiếp theo. Ghi rõ bước pre-read và xác nhận file vẫn còn trong cache nếu công cụ quan sát cho phép.

**Nhóm cache lạnh:** dùng một host/VM thử nghiệm mới hoặc một file/artifact chưa được đọc trên host đó. Không nên giả định chỉ vì process mới là page cache cũng lạnh; page cache thuộc kernel và có thể còn dữ liệu từ process trước.

Trên Linux có thể gặp hướng dẫn dùng /proc/sys/vm/drop_caches để làm sạch cache. Thao tác này ảnh hưởng toàn hệ thống, có thể làm chậm các workload khác và cần quyền quản trị. Không chạy trong production hoặc host dùng chung. Ưu tiên host benchmark riêng, VM mới hoặc artifact mới chưa được cache.

### Chọn pattern I/O đại diện

- Sequential read: đọc file theo thứ tự.
- Random read: đọc các vùng rải rác.
- Sequential write: tạo checkpoint artifact lớn.
- Small-file metadata: nhiều file nhỏ và directory entry.
- Sync write: workload cần flush/fsync.

Không dùng một bài benchmark tuần tự để đại diện cho mọi loại checkpoint I/O. Cách engine ghi file và cách restore đọc file có thể khác pattern.

### Ghi lại chỉ số

| Chỉ số | Ý nghĩa |
|---|---|
| Checkpoint duration | Thời gian từ yêu cầu checkpoint tới khi artifact sẵn sàng |
| Restore duration | Thời gian runtime/engine cần để phục hồi process |
| Time-to-ready | Thời gian từ lúc bắt đầu restore tới khi instance có thể nhận traffic |
| First-request latency | Độ trễ request đầu tiên hoặc nhóm request đầu tiên |
| p50/p95/p99 latency | Phân phối latency sau restore |
| Major/minor faults | Số page fault của process |
| Device read/write throughput | Lưu lượng đọc/ghi storage |
| I/O await và queue depth | Độ trễ và hàng đợi của thiết bị |
| Memory pressure | Cgroup usage, reclaim, swap và OOM events |
| CPU utilization | Chi phí xử lý page fault, compression và runtime |

Nên ghi cả thời gian đến readiness và latency sau readiness. Một hệ thống có thể báo ready sớm nhưng những request đầu tiên vẫn phải chờ page-in, dẫn tới p99 cao.

## 11. Dùng fio và các công cụ benchmark storage

fio có thể tạo workload I/O tổng hợp để đo storage. Ví dụ đọc tuần tự:

~~~shell
fio --name=seq-read --filename=/mnt/checkpoint-bench/test.bin \
    --size=4G --rw=read --bs=1M --iodepth=16 \
    --direct=1 --runtime=60 --time_based --group_reporting
~~~

Ví dụ đọc ngẫu nhiên:

~~~shell
fio --name=rand-read --filename=/mnt/checkpoint-bench/test.bin \
    --size=4G --rw=randread --bs=4k --iodepth=32 \
    --direct=1 --runtime=60 --time_based --group_reporting
~~~

Các lệnh trên là ví dụ tạo file benchmark riêng. Chọn size, block size, queue depth và direct I/O theo thiết bị và workload thực tế. direct I/O bỏ qua page cache cho đường I/O được hỗ trợ, vì vậy kết quả không đại diện cho ứng dụng Java dùng buffered I/O hoặc memory mapping. Cần đo cả buffered I/O nếu đó là hành vi thực tế.

Không chạy fio lên file dữ liệu thật, volume production hoặc checkpoint đang được sử dụng. Workload benchmark có thể tiêu thụ IOPS, băng thông và dung lượng, ảnh hưởng các ứng dụng khác. Dùng volume/host riêng và xóa file test theo quy trình an toàn.

fio đo storage path, không đo trực tiếp CRaC restore. Sau khi có baseline storage, vẫn cần đo checkpoint/restore thật để biết engine và runtime sử dụng storage ra sao.

## 12. Đọc file checkpoint trước để làm nóng cache có nên không?

Đọc trước artifact có thể làm page cache nóng trên host hiện tại, nhưng không phải lúc nào cũng có lợi:

- Đọc toàn bộ file có thể chiếm page cache và đẩy dữ liệu nghiệp vụ khác ra ngoài.
- Nó tiêu thụ bandwidth storage trước khi restore.
- Nếu artifact lớn hơn RAM khả dụng, các trang đầu có thể bị reclaim trước khi restore dùng tới.
- Nếu restore dùng lazy paging, đọc trước toàn bộ có thể làm mất lợi ích của việc chỉ nạp trang cần thiết.
- Nếu restore diễn ra trên host khác, pre-read ở host tạo checkpoint không làm nóng cache của host đích.

Nếu runtime có cơ chế prefetch chính thức, dùng theo tài liệu của runtime. Nếu tự pre-read, cần đo tác động lên memory pressure và latency của các workload khác. Không tự động thêm bước đọc toàn bộ checkpoint file vào startup mà không có benchmark.

## 13. Tối ưu storage path cho checkpoint

Một số cách cải thiện có thể xem xét:

**Dùng storage có latency và throughput phù hợp.** Checkpoint lớn hoặc workload lazy paging nhạy với latency có thể hưởng lợi từ local NVMe hoặc volume được cấu hình phù hợp. Đo theo profile I/O thực tế.

**Tránh volume bị tranh chấp.** Nếu checkpoint artifact chia sẻ volume với log, database hoặc workload nặng, I/O có thể bị cạnh tranh. Tách volume hoặc đặt QoS khi cần.

**Kiểm tra filesystem và container layer.** Overlay filesystem, copy-up, metadata operation và nhiều file nhỏ có thể tạo overhead. Đo đúng đường dẫn mà engine thực sự dùng.

**Giảm kích thước trạng thái một cách hợp lý.** Loại bỏ cache không cần thiết hoặc object tạm trước checkpoint có thể giảm lượng memory state cần lưu. Nhưng không xóa trạng thái cần cho correctness hoặc làm tăng chi phí khởi động sau restore.

**Cân nhắc compression và encryption.** Compression giảm byte ghi/đọc nhưng tốn CPU và có thể thay đổi khả năng demand paging. Encryption bảo vệ artifact nhưng có thể thêm CPU/I/O. Chỉ chọn dựa trên số đo và chính sách bảo mật.

**Đặt checkpoint artifact gần môi trường restore.** Giảm network hop hoặc thời gian tải artifact có thể cải thiện restore. Tuy nhiên, vị trí lưu phải đáp ứng độ bền, quyền truy cập, encryption và chính sách phân phối.

**Giữ đủ memory headroom.** Nếu heap và native memory chiếm gần hết cgroup limit, page cache dễ bị reclaim và restore có thể gây memory pressure. Đánh giá -Xmx cùng tổng memory, không chỉ heap.

## 14. Ví dụ phân tích một lần restore chậm

Giả sử cùng một checkpoint có kết quả:

| Lần chạy | Restore duration | Time-to-ready | First-request p99 |
|---|---:|---:|---:|
| A: host đã đọc artifact | 1.8 s | 2.1 s | 45 ms |
| B: host cache lạnh | 7.4 s | 7.8 s | 52 ms |
| C: demand paging và traffic sớm | 2.0 s | 2.2 s | 480 ms |

Các số trên chỉ là ví dụ minh họa, không phải benchmark tham chiếu.

Có thể diễn giải:

- Lần A nhanh vì checkpoint artifact có thể đã nằm trong page cache.
- Lần B mất nhiều thời gian hơn để nạp artifact từ backing storage trước khi readiness.
- Lần C báo ready sớm nhưng request đầu tiên truy cập các trang chưa được nạp, khiến latency tăng.

Để xác nhận, cần đối chiếu log engine, page fault counters, block I/O, storage latency và request trace. Bảng thời gian một mình không chứng minh nguyên nhân.

Nếu C là hành vi của lazy restore, có thể cân nhắc prefetch các vùng thực sự cần cho đường request quan trọng hoặc trì hoãn readiness tới khi một tập trang/dependency cần thiết đã sẵn sàng. Cần dùng cơ chế chính thức của runtime; không tự đọc/ghi vào vùng nhớ nội bộ của checkpoint.

## 15. Những lỗi thường gặp khi đo

**So sánh một lần cache nóng với một lần cache lạnh nhưng không ghi trạng thái cache.**

Kết quả không thể tái lập. Ghi lại pre-read, host, page cache, memory pressure và số liệu I/O.

**Coi mọi major fault là đọc từ SSD.**

Major fault chỉ cho biết cần I/O để xử lý fault; backing storage có thể là swap, network filesystem hoặc tầng khác.

**Coi page cache là heap Java.**

Page cache thuộc kernel và có vòng đời khác heap, GC và checkpoint object graph.

**Tăng heap để giữ file cache.**

Heap lớn hơn có thể làm giảm RAM còn lại cho page cache và native memory. Cần cân bằng toàn bộ cgroup.

**Dùng drop_caches trên production để tạo cache lạnh.**

Thao tác này ảnh hưởng toàn host. Dùng môi trường benchmark riêng.

**Chỉ đo throughput storage.**

Random I/O, latency, IOPS, queue depth và fsync có thể là giới hạn thực tế.

**Dùng fio để kết luận CRaC restore nhanh hay chậm.**

fio chỉ đo storage workload tổng hợp. Cần đo restore thực tế trên đúng engine/runtime.

**Cho rằng JIT warmup sẽ làm page cache nóng.**

JIT warmup thực thi method; nó không tự đọc checkpoint artifact hoặc file dữ liệu.

**Cho rằng restore nhanh đồng nghĩa request đầu tiên nhanh.**

Với demand paging, process có thể hoạt động trước khi mọi trang cần thiết được nạp. Đo first-request và p95/p99 sau restore.

## 16. Quy trình đo và cải thiện

Một quy trình thực tế:

1. Xác định phần I/O cần đánh giá: checkpoint write, artifact transfer, restore read hay workload sau restore.
2. Ghi JDK/CRaC runtime, checkpoint engine, kernel, container digest, storage type và mount path.
3. Ghi heap size, cgroup memory limit, swap policy và mức memory pressure.
4. Tách các lượt cache nóng, cache lạnh và cache một phần; không dùng host production để drop cache.
5. Đo checkpoint duration, restore duration, time-to-ready và first-request latency.
6. Thu thập minor/major faults, block read/write, I/O latency, queue depth và cgroup memory statistics.
7. Chạy workload sequential/random và workload ứng dụng thực tế trên storage riêng để có baseline.
8. Lặp nhiều lần, so sánh p50/p95/p99 và ghi nhận biến động giữa host.
9. Thay từng yếu tố như storage class, memory headroom, compression hoặc prefetch policy rồi đo lại.
10. Chỉ áp dụng thay đổi sau khi xác nhận correctness, độ bền artifact và khả năng restore trên môi trường mục tiêu.

## 17. Kết luận

Page cache giúp kernel phục vụ file read từ RAM; page fault là cơ chế xử lý truy cập virtual memory, trong đó minor fault thường không cần I/O storage còn major fault cần I/O để hoàn tất. Tốc độ ổ đĩa, IOPS, latency, filesystem và memory pressure đều có thể ảnh hưởng thời gian tạo checkpoint, đọc artifact, restore và latency sau restore.

Với CRaC, page cache không phải trạng thái heap Java và không nên mặc định được chuyển nguyên vẹn giữa các host. Hành vi eager hay lazy restore phụ thuộc implementation cụ thể. Hãy đo riêng checkpoint duration, restore duration, time-to-ready và first-request latency; kết hợp page fault counters với block I/O, storage latency và cgroup memory statistics. Dùng môi trường benchmark riêng để so sánh cache nóng/lạnh, rồi tối ưu storage path và memory headroom theo workload thực tế.

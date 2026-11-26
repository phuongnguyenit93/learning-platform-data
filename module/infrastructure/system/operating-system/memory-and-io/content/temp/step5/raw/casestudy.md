Một tiến trình Java báo Virtual Size tăng lên 12 GB sau khi nạp thư viện native, nhưng RSS chỉ khoảng 1,4 GB và máy vẫn còn RAM; nhóm vận hành kết luận máy sắp hết bộ nhớ chỉ dựa trên vùng địa chỉ ảo đã reserve.
Một máy chủ có RAM còn trống nhưng ứng dụng tăng độ trễ sau khi số lần TLB miss tăng mạnh; nhóm cần phân biệt chi phí tra cứu địa chỉ với page fault phải đọc dữ liệu từ storage.
Một workload khởi động lạnh có hàng triệu minor page faults nhưng rất ít major faults; dashboard chỉ hiển thị tổng page faults và đội trực cho rằng ổ đĩa đang nghẽn.
Một tiến trình đọc tập dữ liệu lớn lần đầu sau khi deploy; major page faults và thời gian đọc tăng cao, nhưng lần chạy thứ hai nhanh hơn rõ rệt do các trang đã nằm trong page cache.
Một chương trình fork nhiều worker rồi mỗi worker cập nhật một phần cấu trúc dữ liệu lớn; RSS của các worker tăng nhanh sau fork vì copy-on-write tạo bản sao khi ghi, dù ban đầu các trang được chia sẻ.
Ứng dụng dùng mmap để đọc file dữ liệu 20 GB; RSS tăng dần theo số trang được truy cập nhưng nhóm hiểu nhầm toàn bộ kích thước mapping là lượng RAM đã chiếm ngay từ đầu.
Một tiến trình truy cập vùng mmap của file vừa bị truncate bởi tiến trình khác; ứng dụng nhận SIGBUS tại một địa chỉ hợp lệ trước đó và đội trực nhầm đây là lỗi truy cập con trỏ.
Máy phân tích dữ liệu giữ working set lớn hơn RAM khả dụng; page reclaim và swap-in/swap-out liên tục khiến throughput giảm mạnh dù CPU utilization không cao.
Một máy chủ có RAM gần đầy nhưng phần lớn là page cache chứa dữ liệu có thể đọc lại từ file; nhóm trực định tăng RAM chỉ từ chỉ số free memory thấp mà chưa xem available memory và reclaim.
Một dịch vụ bị chậm sau khi kernel thu hồi page cache để cấp phát anonymous memory; số lần đọc đĩa tăng vì working set file nóng phải được nạp lại sau mỗi đợt reclaim.
Swap được bật trên máy chủ cơ sở dữ liệu; khi áp lực bộ nhớ tăng, các trang ít dùng bị đẩy ra swap và truy cập lại tạo độ trễ đột biến dù swap usage tổng thể không quá lớn.
Máy chủ có swap-in và swap-out tăng liên tục trong giờ cao điểm; nhóm chỉ theo dõi phần trăm swap đã dùng nên bỏ qua tình trạng thrashing đang làm request p99 tăng.
Ứng dụng cấp phát bộ nhớ thành công nhờ memory overcommit nhưng chạm giới hạn vật lý khi chạm tới các trang đã cấp phát; OOM killer kết thúc một tiến trình quan trọng dù malloc trước đó không báo lỗi.
Container bị OOMKilled khi memory usage vượt memory.max của cgroup; node vẫn còn nhiều RAM và các workload khác khỏe mạnh, nhưng dashboard chỉ nhìn bộ nhớ toàn host.
RSS của tiến trình tăng đều qua nhiều giờ trong khi heap Java sau GC ổn định; nghi vấn chuyển sang native memory, direct buffers, thread stacks hoặc thư viện C thay vì kết luận heap leak.
Một container ghi file tạm dung lượng lớn; page cache của file được tính vào memory cgroup và làm container chạm giới hạn dù RSS của tiến trình ứng dụng gần như không đổi.
Máy chủ có lượng dirty pages tăng cao vì ứng dụng ghi file nhanh hơn tốc độ storage flush; sau đó các thread ghi bị chặn khi kernel phải writeback và latency tăng theo từng đợt.
Ứng dụng gọi write thành công nhưng dữ liệu chưa bền vững trên thiết bị; mất điện trước fsync khiến phần dữ liệu cuối cùng không tồn tại sau khi máy khởi động lại.
Database có p99 commit tăng mạnh dù câu SQL chạy nhanh; trace cho thấy thời gian nằm ở fsync WAL và storage flush thay vì CPU xử lý truy vấn.
Một workload chạy trên máy NUMA hai socket; tiến trình bị pin vào CPU node 0 nhưng phần lớn memory được cấp từ node 1, làm latency truy cập bộ nhớ tăng dù tổng RAM còn đủ.
Máy chủ bật Transparent Huge Pages ở chế độ always; độ trễ pause tăng khi kernel cố gắng compaction để tạo huge pages trong lúc workload cấp phát bộ nhớ liên tục.
Một tiến trình dùng mlock để khóa vùng nhớ nhạy cảm trong RAM; số trang không thể reclaim tăng và các tiến trình khác bắt đầu swap hoặc bị OOM dù tổng bộ nhớ cấp phát không tăng nhiều.
Container có memory.high đặt thấp hơn memory.max; khi vượt ngưỡng high, tiến trình bị chậm do reclaim và throttling trước khi xảy ra OOM, nhưng nhóm trực chỉ theo dõi trạng thái OOMKilled.
Một hệ thống có nhiều file nhỏ và số lượng slab objects tăng mạnh; RSS ứng dụng không đổi nhưng kernel memory tăng, làm host tiến gần giới hạn RAM và cần phân biệt slab reclaimable với unreclaimable.
Ứng dụng thực hiện hàng triệu lần đọc file nhỏ bằng system call riêng lẻ; CPU system time và context switches tăng, trong khi gom thao tác theo buffer lớn giúp giảm overhead mà không đổi lượng dữ liệu.
Một service ghi log bằng buffered I/O; write() trả về nhanh nhưng độ trễ xuất hiện muộn ở thread khác khi kernel flush dirty pages, khiến nhóm gán nhầm spike cho request đến đúng thời điểm flush.
Ứng dụng gọi fsync sau từng bản ghi nhỏ để đảm bảo durability; số IOPS và p99 write latency tăng cao so với gom nhiều bản ghi rồi flush theo batch.
Một tiến trình dùng O_DIRECT để tránh page cache nhưng buffer và offset không đáp ứng yêu cầu alignment của filesystem; các lần đọc/ghi thất bại hoặc phải xử lý fallback, làm benchmark sai lệch.
Benchmark đọc file lần đầu chậm hơn nhiều lần chạy sau; nhóm so sánh hai phiên bản ứng dụng mà không làm lạnh hoặc kiểm soát page cache nên kết luận sai về cải thiện hiệu năng.
Đọc file tuần tự đạt throughput cao nhờ readahead, nhưng workload chuyển sang truy cập ngẫu nhiên các block nhỏ và latency tăng; cấu hình readahead cũ không còn phù hợp mẫu truy cập.
Một dịch vụ streaming file đạt băng thông gần giới hạn thiết bị nhưng số request nhỏ mỗi giây thấp; đội trực tăng queue depth mà chưa phân biệt giới hạn throughput với IOPS và latency.
Biểu đồ iowait tăng lên 35% trong lúc máy chậm; nhóm kết luận SSD hỏng, nhưng cần đối chiếu device utilization, await, queue depth và tiến trình đang chờ để xác định CPU idle chờ I/O hay storage thực sự bão hòa.
Database ghi WAL và checkpoint cùng lúc; disk queue depth, await và write latency tăng, trong khi CPU còn thấp và query execution plan không thay đổi.
Một job backup đọc tuần tự hàng terabyte trên cùng volume với database; throughput tổng vẫn cao nhưng random read latency của database tăng mạnh do tranh chấp I/O.
Container bị giới hạn I/O bằng cgroup io.max; ứng dụng có thể ghi nhanh trong staging nhưng production bị throttling theo device, khiến latency tăng dù host storage chưa bão hòa.
NVMe có nhiều hardware queues nhưng ứng dụng chỉ phát sinh một luồng I/O tuần tự với queue depth thấp; thiết bị chưa được khai thác hết và tăng CPU không cải thiện throughput.
Filesystem còn dung lượng trống nhưng ứng dụng không tạo được file mới vì inode đã cạn; nhóm trực chỉ xem df dung lượng và bỏ qua chỉ số inode usage.
Ứng dụng không mở thêm được file dù RAM và disk còn dư; giới hạn file descriptors của process hoặc system đã chạm ngưỡng, gây EMFILE hoặc ENFILE.
Service đọc dữ liệu từ NFS bị treo ở trạng thái D khi mạng tới storage chập chờn; CPU thấp và process không phản hồi tín hiệu thông thường vì đang chờ I/O không thể ngắt.
Một ứng dụng ghi dữ liệu vào filesystem mạng; retransmission và RTT tăng trên kết nối storage làm I/O latency tăng dù thiết bị lưu trữ phía server vẫn còn công suất.
Filesystem báo lỗi I/O khi ghi dirty pages xuống thiết bị; write() ban đầu đã trả thành công nên lỗi chỉ xuất hiện ở lần fsync hoặc close sau đó.
Máy chủ có disk free thấp sau khi xóa file log lớn; dung lượng không được giải phóng vì tiến trình vẫn giữ file descriptor mở tới inode đã unlink.
Một tiến trình xử lý hàng nghìn request nhỏ đồng bộ; mỗi request gọi read, write và fsync riêng, tạo nhiều syscall và chuyển user/kernel mode hơn phương án batching.
Ứng dụng chuyển từ synchronous I/O sang non-blocking socket nhưng vẫn xử lý từng event tuần tự; một handler chậm chặn event loop và throughput không tăng dù socket không còn block theo cách cũ.
Worker dùng asynchronous I/O để ghi nhiều file song song nhưng ứng dụng không giới hạn số yêu cầu đang chờ; completion ring đầy và backlog ở hàng đợi user-space tăng khi storage chậm hơn tốc độ producer.
Một dịch vụ dùng io_uring để tăng throughput nhưng cấu hình buffer lifetime sai; ứng dụng tái sử dụng vùng nhớ trước khi completion được nhận và dữ liệu ghi ra file bị hỏng.
Ứng dụng dùng memory-mapped I/O để xử lý file lớn; page faults và writeback tạo độ trễ bất thường, nhưng dashboard chỉ đo thời gian hàm xử lý và bỏ qua chi phí paging do truy cập mapping.
Máy chủ có CPU utilization thấp, I/O wait thấp nhưng request vẫn chậm; thread dump cho thấy worker chờ lock trong ứng dụng, chứng minh không phải mọi hiện tượng latency cao đều do bộ nhớ hoặc storage.
Một đội tăng RAM để chữa OOM nhưng không xem cgroup memory events; container vẫn bị kill vì memory limit cố định và file cache cùng anonymous memory tiếp tục cạnh tranh trong cùng giới hạn.

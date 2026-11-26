Hệ điều hành giải quyết những vấn đề gì giữa ứng dụng và phần cứng của máy tính?
Bạn sẽ phân biệt vai trò của kernel, system library và user application trong một hệ thống như thế nào?
Bạn sẽ mô tả những thành phần chính của một hệ điều hành hiện đại và mối quan hệ giữa chúng ra sao?
Bạn sẽ so sánh kiến trúc monolithic kernel và microkernel theo hiệu năng, cô lập lỗi và khả năng mở rộng như thế nào?
Bạn sẽ giải thích sự khác nhau giữa kernel mode và user mode bằng một tình huống ứng dụng cần truy cập thiết bị ra sao?
Vì sao ứng dụng thông thường không được phép trực tiếp thực hiện mọi thao tác đặc quyền của CPU?
Bạn sẽ mô tả quá trình khởi động từ firmware đến bootloader, kernel và tiến trình hệ thống đầu tiên ra sao?
Bạn sẽ phân biệt kernel space với user space về quyền truy cập bộ nhớ và tài nguyên như thế nào?
Bạn sẽ giải thích vai trò của device driver trong việc kết nối kernel với thiết bị phần cứng ra sao?
Bạn sẽ xác định khi nào một chức năng nên nằm trong kernel và khi nào nên chạy ở user space theo tiêu chí nào?
Bạn sẽ phân tích ảnh hưởng của một lỗi kernel đến toàn bộ hệ thống khác với lỗi của một tiến trình ứng dụng như thế nào?
Bạn sẽ mô tả cách hệ điều hành phân bổ CPU, bộ nhớ, thiết bị và lưu trữ cho nhiều chương trình đồng thời ra sao?
Bạn sẽ phân biệt hệ điều hành đa nhiệm, đa người dùng và hệ điều hành thời gian thực theo mục tiêu thiết kế như thế nào?
Bạn sẽ giải thích interrupt giúp CPU phản hồi sự kiện từ phần cứng hoặc phần mềm như thế nào?
Bạn sẽ phân biệt interrupt, exception và trap trong luồng thực thi của CPU ra sao?
Bạn sẽ mô tả đường đi của một system call từ ứng dụng đến kernel và quay lại như thế nào?
Bạn sẽ giải thích system call khác lời gọi hàm thư viện thông thường về chuyển chế độ thực thi như thế nào?
Bạn sẽ lựa chọn những thao tác nào cần system call khi ứng dụng mở file, tạo tiến trình hoặc giao tiếp mạng ra sao?
Bạn sẽ phân tích chi phí của system call và context switch đối với một ứng dụng có nhiều thao tác I/O nhỏ như thế nào?
Bạn sẽ xác định cách xử lý khi system call bị gián đoạn bởi signal hoặc trả về lỗi như thế nào?
Bạn sẽ phân biệt mã lỗi của system call với exception do logic ứng dụng gây ra ra sao?
Bạn sẽ mô tả cách hệ điều hành dùng file descriptor hoặc handle để đại diện tài nguyên đang mở như thế nào?
Bạn sẽ giải thích vì sao một ứng dụng cần quyền phù hợp trước khi gọi các thao tác hệ thống đặc quyền ra sao?
Bạn sẽ xác định thông tin nào của kernel cần quan sát khi điều tra một tiến trình bị treo ở trạng thái kernel wait như thế nào?
Bạn sẽ phân tích vai trò của system call interface trong việc giữ ổn định giao tiếp giữa ứng dụng và kernel như thế nào?
Process là gì, và hệ điều hành quản lý vòng đời của nó qua những trạng thái nào?
Bạn sẽ mô tả các trạng thái phổ biến của process từ lúc tạo đến khi kết thúc ra sao?
Bạn sẽ phân biệt process đang chạy, sẵn sàng chạy và đang chờ I/O bằng những dấu hiệu nào?
Process control block lưu những thông tin nào để kernel có thể lập lịch và quản lý tiến trình?
Bạn sẽ mô tả quá trình tạo process mới và cách tiến trình cha nhận biết kết quả thực thi của tiến trình con ra sao?
Bạn sẽ phân biệt cơ chế tạo process mới với việc thay thế chương trình đang chạy trong cùng process như thế nào?
Bạn sẽ giải thích vì sao process kết thúc nhưng thông tin trạng thái vẫn có thể được giữ lại để tiến trình cha thu nhận ra sao?
Bạn sẽ phân biệt zombie process và orphan process theo nguyên nhân và cách hệ điều hành xử lý như thế nào?
Bạn sẽ xác định những nguyên nhân khiến một process bị treo hoặc không thể kết thúc bình thường ra sao?
Khi context switch giữa hai process, hệ điều hành cần lưu và khôi phục những trạng thái nào?
Bạn sẽ đánh giá chi phí context switch khi hệ thống có quá nhiều process hoạt động đồng thời ra sao?
Bạn sẽ phân biệt process với thread về không gian địa chỉ, tài nguyên dùng chung và chi phí quản lý như thế nào?
Bạn sẽ giải thích vì sao các thread trong cùng process có thể chia sẻ heap nhưng vẫn có stack riêng như thế nào?
Bạn sẽ mô tả cách tạo và kết thúc thread cùng những tài nguyên cần được giải phóng ra sao?
Bạn sẽ xác định khi nào nên dùng nhiều thread trong một ứng dụng và khi nào nên tách thành nhiều process như thế nào?
Bạn sẽ phân tích ưu và nhược điểm của shared memory so với giao tiếp giữa các process bằng message như thế nào?
Bạn sẽ giải thích race condition xuất hiện khi nhiều thread cùng truy cập dữ liệu chia sẻ ra sao?
Bạn sẽ thiết kế vùng critical section để bảo đảm một thao tác cập nhật trạng thái được thực hiện an toàn như thế nào?
Bạn sẽ phân biệt mutex, semaphore và condition variable theo mục đích đồng bộ như thế nào?
Bạn sẽ xác định tình huống cần semaphore đếm thay vì mutex khóa độc quyền ra sao?
Bạn sẽ mô tả deadlock và bốn điều kiện cần có để deadlock có thể xảy ra như thế nào?
Bạn sẽ phân biệt deadlock, livelock và starvation bằng một ví dụ cạnh tranh tài nguyên ra sao?
Bạn sẽ lựa chọn cách phòng tránh, né tránh hoặc phát hiện deadlock theo đặc điểm hệ thống như thế nào?
Bạn sẽ xác định một deadlock giữa nhiều thread bằng stack trace và thông tin khóa đang giữ ra sao?
Bạn sẽ thiết kế thứ tự lấy nhiều lock để giảm nguy cơ deadlock như thế nào?
Bạn sẽ giải thích memory visibility và vì sao đồng bộ hóa cần thiết ngay cả khi không có hai thread ghi cùng lúc ra sao?
Bạn sẽ phân biệt concurrency và parallelism khi chương trình chạy trên một lõi CPU và nhiều lõi CPU như thế nào?
CPU scheduler phải giải quyết những mục tiêu nào khi nhiều process cùng ở trạng thái ready?
Bạn sẽ phân biệt preemptive scheduling với cooperative scheduling theo cách CPU được thu hồi ra sao?
Bạn sẽ so sánh FCFS, shortest-job-first, priority scheduling và round-robin về thời gian chờ và độ công bằng như thế nào?
Bạn sẽ lựa chọn time slice cho round-robin dựa trên tương tác người dùng và chi phí context switch ra sao?
Bạn sẽ giải thích starvation trong priority scheduling và cách aging có thể giảm vấn đề này như thế nào?
Bạn sẽ phân biệt throughput, turnaround time, waiting time và response time khi đánh giá scheduler như thế nào?
Bạn sẽ xác định workload thiên về CPU hay I/O để dự đoán hành vi lập lịch của process như thế nào?
Bạn sẽ phân tích vì sao một process tương tác có thể cần ưu tiên phản hồi hơn một batch job dài ra sao?
Bạn sẽ mô tả cách scheduler xử lý thread trên hệ thống đa lõi và những yếu tố ảnh hưởng đến cân bằng tải như thế nào?
Bạn sẽ phân biệt affinity của thread với việc scheduler tự do di chuyển thread giữa các CPU ra sao?
Bạn sẽ đánh giá ảnh hưởng của CPU-bound tasks chạy đồng thời lên latency của các tác vụ tương tác như thế nào?
Bạn sẽ xác định khi nào context switch quá nhiều là dấu hiệu scheduler hoặc ứng dụng đang có vấn đề ra sao?
Bạn sẽ phân tích ảnh hưởng của priority inversion và cách priority inheritance có thể xử lý tình huống đó như thế nào?
Bạn sẽ giải thích vai trò của timer interrupt trong việc cho scheduler cơ hội phân bổ lại CPU ra sao?
Bạn sẽ phân biệt load average với phần trăm CPU utilization khi đọc tình trạng máy chủ như thế nào?
Bạn sẽ xác định nguyên nhân một process có CPU usage thấp nhưng vẫn phản hồi chậm bằng cách nào?
Bạn sẽ giải thích vì sao CPU utilization cao chưa chắc là dấu hiệu hệ thống hoạt động kém hiệu quả như thế nào?
Bạn sẽ mô tả không gian địa chỉ ảo của một process và cách nó được ánh xạ tới bộ nhớ vật lý ra sao?
Bạn sẽ phân biệt địa chỉ ảo với địa chỉ vật lý khi chương trình đọc hoặc ghi một biến như thế nào?
Bạn sẽ giải thích lợi ích của virtual memory đối với cô lập process và sử dụng bộ nhớ linh hoạt ra sao?
Bạn sẽ mô tả cách paging chia không gian địa chỉ thành page và bộ nhớ vật lý thành frame như thế nào?
Bạn sẽ phân biệt paging với segmentation về cách chia và quản lý không gian địa chỉ ra sao?
Bạn sẽ giải thích page table ánh xạ địa chỉ ảo sang frame vật lý như thế nào?
Bạn sẽ mô tả vai trò của TLB trong việc giảm chi phí tra cứu page table ra sao?
TLB miss diễn ra như thế nào, và khác page fault ở điểm nào?
Bạn sẽ giải thích page fault xảy ra khi nào và kernel xử lý một page fault hợp lệ theo những bước nào?
Bạn sẽ phân biệt page fault hợp lệ cần nạp dữ liệu với lỗi truy cập bộ nhớ không được phép như thế nào?
Bạn sẽ mô tả demand paging giúp chỉ nạp page khi chương trình thực sự truy cập như thế nào?
Bạn sẽ phân tích ảnh hưởng của page replacement đến hiệu năng khi RAM không đủ chứa working set ra sao?
Bạn sẽ so sánh các thuật toán FIFO, LRU và clock trong việc lựa chọn page cần thay thế như thế nào?
Bạn sẽ giải thích thrashing và những dấu hiệu cho thấy hệ thống dành quá nhiều thời gian xử lý page fault ra sao?
Bạn sẽ xác định nguyên nhân process bị chậm do thiếu RAM thay vì do CPU hoặc I/O bằng cách nào?
Bạn sẽ phân biệt internal fragmentation và external fragmentation trong quản lý bộ nhớ như thế nào?
Bạn sẽ giải thích stack, heap, data segment và code segment trong không gian địa chỉ của process ra sao?
Bạn sẽ phân tích các nguyên nhân gây memory leak và cách phân biệt chúng với bộ nhớ được cache có chủ đích như thế nào?
Bạn sẽ mô tả memory allocation và deallocation ở mức ứng dụng tương tác với allocator và kernel ra sao?
Bạn sẽ giải thích copy-on-write giúp giảm chi phí sao chép bộ nhớ khi tạo process hoặc chia sẻ page như thế nào?
Bạn sẽ phân biệt anonymous memory với file-backed memory trong một process như thế nào?
Bạn sẽ mô tả memory-mapped file và những trường hợp dùng mmap có lợi so với read/write thông thường ra sao?
Bạn sẽ giải thích vai trò của swap và những rủi ro khi hệ thống phụ thuộc quá nhiều vào swap như thế nào?
Bạn sẽ xác định khi nào kernel reclaim page cache và điều đó ảnh hưởng đến ứng dụng ra sao?
Bạn sẽ phân tích page cache giúp tăng tốc truy cập file nhưng cũng có thể làm cách đọc memory usage dễ gây hiểu nhầm như thế nào?
Bạn sẽ phân biệt virtual memory size, resident set size và shared memory khi đọc mức sử dụng RAM của process ra sao?
Bạn sẽ giải thích memory protection ngăn process truy cập vùng nhớ của process khác bằng cơ chế nào?
Bạn sẽ mô tả các cơ chế bảo vệ như NX bit, ASLR và user/kernel separation góp phần giảm rủi ro khai thác như thế nào?
Những điều kiện nào có thể khiến hệ điều hành kết thúc một process do vượt giới hạn bộ nhớ?
Bạn sẽ phân biệt OOM killer với lỗi cấp phát bộ nhớ trả về cho ứng dụng trong tình huống thiếu RAM ra sao?
Bạn sẽ giải thích vai trò của filesystem trong việc tổ chức dữ liệu lâu dài trên thiết bị lưu trữ như thế nào?
Bạn sẽ phân biệt file, directory, inode hoặc metadata tương đương và file descriptor trong quá trình truy cập như thế nào?
Bạn sẽ mô tả cách đường dẫn tuyệt đối và tương đối được phân giải qua các thư mục ra sao?
Bạn sẽ giải thích mount point cho phép kết hợp nhiều filesystem thành một cây thư mục như thế nào?
Bạn sẽ phân biệt filesystem cục bộ với network filesystem theo độ trễ, độ tin cậy và ngữ nghĩa truy cập ra sao?
Bạn sẽ mô tả vai trò của permission bits và ownership trong việc kiểm soát đọc, ghi và thực thi file như thế nào?
Bạn sẽ phân biệt quyền của file với quyền của directory khi người dùng cần truy cập một đường dẫn ra sao?
Bạn sẽ giải thích quyền truy cập theo user, group và other ảnh hưởng đến quyết định mở file như thế nào?
Bạn sẽ xác định vai trò của ACL khi quyền truy cập cần chi tiết hơn mô hình owner/group/other ra sao?
Bạn sẽ phân biệt quyền thực thi file với quyền tìm kiếm trên directory trong quá trình truy cập như thế nào?
Bạn sẽ phân tích rủi ro khi một ứng dụng chạy với quyền quản trị hoặc quyền sở hữu file quá rộng ra sao?
Bạn sẽ giải thích journaling filesystem giúp phục hồi tính nhất quán metadata sau sự cố mất điện như thế nào?
Bạn sẽ phân biệt durability của dữ liệu với tính nhất quán của metadata trong filesystem ra sao?
Bạn sẽ mô tả vai trò của page cache và write-back cache khi ứng dụng ghi dữ liệu vào file như thế nào?
Vì sao write() trả về thành công chưa bảo đảm dữ liệu đã được ghi bền vững xuống thiết bị?
Bạn sẽ xác định khi nào cần fsync hoặc cơ chế đồng bộ tương đương để bảo đảm dữ liệu quan trọng được lưu ra sao?
Bạn sẽ phân tích ảnh hưởng của file locking khi nhiều process cùng sửa một file như thế nào?
Bạn sẽ phân biệt advisory lock với mandatory lock và giới hạn của mỗi cơ chế ra sao?
Bạn sẽ mô tả cách hệ điều hành xử lý file đang được một process mở khi tên file bị xóa hoặc đổi như thế nào?
Bạn sẽ xác định nguyên nhân dung lượng đĩa vẫn chưa được giải phóng dù file đã bị xóa khỏi directory ra sao?
Bạn sẽ phân tích lỗi filesystem đầy inode khác với đầy dung lượng lưu trữ theo byte như thế nào?
Bạn sẽ lựa chọn cách tổ chức thư mục, file descriptor và quyền truy cập cho một dịch vụ ghi log dung lượng lớn ra sao?
Bạn sẽ phân biệt block device và character device về cách dữ liệu được đọc ghi như thế nào?
Bạn sẽ mô tả đường đi của một thao tác đọc file từ system call qua filesystem đến thiết bị lưu trữ ra sao?
Bạn sẽ giải thích vai trò của device driver, interrupt và DMA trong một thao tác I/O như thế nào?
Bạn sẽ phân biệt polling với interrupt-driven I/O theo mức tiêu thụ CPU và độ trễ ra sao?
DMA chuyển dữ liệu giữa thiết bị và bộ nhớ như thế nào, và CPU tham gia ở những bước nào?
Bạn sẽ giải thích buffering, caching và spooling giải quyết những vấn đề I/O khác nhau ra sao?
Bạn sẽ phân biệt synchronous I/O và asynchronous I/O về thời điểm thread được tiếp tục thực thi như thế nào?
Bạn sẽ lựa chọn buffered I/O hay direct I/O dựa trên đặc điểm workload và yêu cầu nhất quán ra sao?
Bạn sẽ mô tả queue I/O của thiết bị lưu trữ ảnh hưởng đến latency và throughput như thế nào?
Bạn sẽ phân biệt IOPS, bandwidth và latency khi đánh giá hiệu năng ổ đĩa ra sao?
Bạn sẽ phân tích vì sao một thiết bị có throughput cao vẫn có thể phục vụ các request nhỏ với latency lớn như thế nào?
Bạn sẽ xác định nguyên nhân ứng dụng chậm do I/O wait thay vì CPU saturation bằng những chỉ số nào?
Bạn sẽ giải thích cơ chế read-ahead hoặc write-back có thể cải thiện hoặc làm xấu hiệu năng tùy workload như thế nào?
Bạn sẽ mô tả cách socket cung cấp giao diện giao tiếp giữa các process trên cùng máy hoặc qua mạng như thế nào?
Bạn sẽ phân biệt pipe, named pipe, shared memory, message queue và socket theo cách trao đổi dữ liệu ra sao?
Bạn sẽ lựa chọn IPC mechanism cho hai process cần truyền lượng dữ liệu lớn với độ trễ thấp như thế nào?
Bạn sẽ phân tích ảnh hưởng của buffer socket đầy khi phía gửi nhanh hơn phía nhận như thế nào?
Bạn sẽ giải thích backpressure ở tầng I/O và cách ứng dụng có thể phản ứng để tránh tiêu thụ bộ nhớ vô hạn ra sao?
Bạn sẽ phân biệt signal dùng để thông báo sự kiện với message dùng để trao đổi dữ liệu như thế nào?
Bạn sẽ xác định cách xử lý signal an toàn khi process đang thực hiện thao tác quan trọng ra sao?
Bạn sẽ mô tả cách hệ điều hành cô lập quyền và tài nguyên giữa các user session như thế nào?
Bạn sẽ phân biệt authentication và authorization trong việc kiểm soát người dùng truy cập tài nguyên hệ điều hành ra sao?
Bạn sẽ giải thích nguyên tắc least privilege và cách áp dụng cho service account chạy ứng dụng như thế nào?
Bạn sẽ phân biệt user ID, group ID, capability và quyền quản trị toàn cục theo phạm vi đặc quyền ra sao?
Bạn sẽ đánh giá rủi ro khi một process kế thừa file descriptor hoặc environment chứa thông tin nhạy cảm từ process cha như thế nào?
Bạn sẽ mô tả cơ chế cô lập process bằng namespace và giới hạn tài nguyên bằng control group trong môi trường container ra sao?
Bạn sẽ phân biệt container với virtual machine về mức chia sẻ kernel và ranh giới cô lập như thế nào?
Hypervisor phân bổ CPU, memory và thiết bị ảo cho nhiều virtual machine theo cơ chế nào?
Bạn sẽ so sánh hypervisor type 1 và type 2 theo vị trí chạy và mục tiêu triển khai ra sao?
Bạn sẽ phân biệt hardware virtualization, paravirtualization và container isolation về cơ chế hỗ trợ như thế nào?
Bạn sẽ đánh giá ảnh hưởng của CPU overcommit và memory overcommit khi nhiều VM chạy trên cùng host ra sao?
Vì sao số CPU hoặc dung lượng bộ nhớ mà container nhìn thấy có thể khác giới hạn tài nguyên thực tế được cấp?
Bạn sẽ xác định những ranh giới bảo mật cần kiểm tra khi chạy ứng dụng không tin cậy trong container hoặc VM ra sao?
Bạn sẽ phân biệt kernel panic, process crash và service failure về phạm vi ảnh hưởng và cách điều tra như thế nào?
Bạn sẽ xây dựng quy trình điều tra khi máy chủ phản hồi chậm bằng cách kiểm tra CPU, memory, disk I/O và process state ra sao?
Bạn sẽ xác định nguyên nhân process không thể mở thêm file do giới hạn file descriptor như thế nào?
Bạn sẽ phân tích tình huống máy có RAM còn trống nhưng ứng dụng vẫn không cấp phát được bộ nhớ bằng những giả thuyết nào?
Bạn sẽ điều tra hiện tượng nhiều process ở trạng thái uninterruptible sleep và xác định dependency I/O bị nghẽn ra sao?
Bạn sẽ phân biệt CPU saturation, run queue dài và load cao do I/O wait khi chẩn đoán máy chủ như thế nào?
Bạn sẽ sử dụng log hệ thống, process table và thống kê tài nguyên để tìm nguyên nhân một service liên tục restart ra sao?
Bạn sẽ thiết kế thử nghiệm so sánh hiệu năng giữa buffered I/O và asynchronous I/O theo những chỉ số nào?
Bạn sẽ kiểm tra tác động của số thread tăng lên đối với throughput, context switch và memory usage như thế nào?
Bạn sẽ tạo kịch bản kiểm thử race condition hoặc deadlock có thể lặp lại để đánh giá cơ chế đồng bộ ra sao?
Bạn sẽ xác minh quyền truy cập file trong tình huống process chạy dưới user khác với người tạo file như thế nào?
Bạn sẽ kiểm tra độ bền dữ liệu sau khi process bị kill hoặc máy bị tắt đột ngột bằng quy trình nào?
Bạn sẽ xây dựng tiêu chí nghiệm thu về process, scheduling, memory, filesystem, I/O, security, isolation và virtualization cho một môi trường thực thi ứng dụng như thế nào?

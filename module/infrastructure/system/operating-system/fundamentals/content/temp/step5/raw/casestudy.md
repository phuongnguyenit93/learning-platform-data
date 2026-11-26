Một ứng dụng xử lý ảnh chạy trong user mode nhưng cần truy cập thiết bị camera; nhóm phát triển cố đọc trực tiếp thanh ghi phần cứng và gặp lỗi quyền, chưa hiểu vai trò kernel và system call trong việc cung cấp giao diện an toàn.
Một chương trình gọi open() thành công nhưng read() trả lỗi Permission denied; nhóm chỉ kiểm tra quyền của tiến trình mà chưa phân biệt kiểm tra quyền ở user space với quyết định truy cập của kernel.
API của ứng dụng phản hồi chậm sau khi tăng số lần gọi stat() và gettimeofday(); profiler cho thấy thời gian chuyển sang kernel mode tăng, đội phát triển cần xác định chi phí system call và cơ hội gom thao tác.
Một tiến trình ghi file bằng write() rồi báo hoàn tất, nhưng sau khi máy mất điện dữ liệu cuối cùng không có trên đĩa; nhóm nhầm lẫn giữa dữ liệu đã vào page cache và dữ liệu đã được đồng bộ bền vững.
Chương trình gọi một system call với con trỏ không hợp lệ; kernel trả lỗi thay vì để tiến trình đọc tùy ý bộ nhớ kernel, minh họa ranh giới bảo vệ giữa user mode và kernel mode.
Một tiến trình bị treo trong trạng thái uninterruptible sleep khi thiết bị lưu trữ không phản hồi; lệnh kill thông thường chưa kết thúc tiến trình và đội vận hành cần xác định nó đang chờ I/O trong kernel.
Ứng dụng tạo tiến trình con bằng fork() rồi gọi exec(); nhóm kỳ vọng exec tạo PID mới nhưng thấy PID giữ nguyên và không hiểu sự khác nhau giữa tạo tiến trình và thay image chương trình.
Tiến trình cha tạo nhiều worker nhưng không thu hồi trạng thái tiến trình con đã kết thúc; danh sách process xuất hiện nhiều zombie dù các worker không còn chạy.
Một daemon cha thoát trước khi tiến trình con kết thúc; tiến trình con được nhận bởi tiến trình init hoặc subreaper và nhóm cần giải thích vòng đời orphan process.
Một chương trình dùng fork() trước khi tạo nhiều thread rồi thực hiện thao tác khóa ở tiến trình con; tiến trình con bị deadlock vì trạng thái mutex của các thread không còn tồn tại sau fork.
Ứng dụng tạo hàng nghìn process ngắn hạn cho từng tác vụ; chi phí tạo process và chuyển ngữ cảnh cao hơn mô hình thread pool, làm throughput giảm khi tải tăng.
Một dịch vụ dùng thread pool cố định nhưng một số thread chờ I/O bên ngoài quá lâu; hàng đợi tác vụ tăng dù CPU còn nhàn, vì số worker sẵn sàng xử lý bị cạn.
Hai thread cùng tăng biến đếm dùng chung mà không đồng bộ; tổng số tác vụ hoàn tất thấp hơn số request thực tế do race condition trong vùng dữ liệu chia sẻ.
Hai thread giữ hai mutex theo thứ tự ngược nhau; mỗi thread chờ khóa mà thread kia đang giữ, khiến ứng dụng deadlock dù CPU gần như không hoạt động.
Một thread ưu tiên thấp giữ mutex trong khi thread ưu tiên cao cần mutex đó và thread ưu tiên trung bình liên tục chạy; hệ thống gặp priority inversion và tác vụ thời gian thực trễ deadline.
Một worker có mức ưu tiên thấp liên tục bị các tác vụ ưu tiên cao chiếm CPU; worker gần như không tiến triển và nhóm cần phân biệt starvation với deadlock.
Một ứng dụng đa luồng tạo quá nhiều thread so với số lõi CPU; context switching tăng và cache locality giảm khiến thời gian hoàn tất công việc dài hơn khi tăng concurrency.
Máy chủ có CPU nhiều lõi nhưng một thread xử lý request nóng bị giới hạn trên một lõi; tổng CPU toàn máy thấp trong khi một core bão hòa và latency tăng.
Một tác vụ batch chạy lâu làm tương tác desktop giật; nhóm điều tra cần hiểu scheduler chia CPU giữa process runnable và tác động của time slice, priority cùng tải hệ thống.
Tiến trình sử dụng CPU cao nhưng không có request mới; vòng lặp retry không có backoff liên tục giữ trạng thái runnable và chiếm thời gian CPU của các dịch vụ khác.
Một ứng dụng cấp phát vùng bộ nhớ ảo (virtual memory) lớn nhưng chỉ chạm vào một phần nhỏ; nhóm thấy virtual size cao và kết luận máy sắp hết RAM dù resident set size còn thấp.
Tiến trình tăng RSS dần sau mỗi yêu cầu và không giảm khi tải hạ; nhóm cần phân biệt memory leak với allocator giữ lại heap đã cấp phát để tái sử dụng.
Máy Linux còn nhiều bộ nhớ khả dụng theo cách nhìn ứng dụng nhưng một tiến trình bị OOM-kill; đội vận hành chưa xem xét cgroup memory limit và tổng mức tiêu thụ trong container.
Một ứng dụng truy cập vùng nhớ vừa được mmap nhưng gặp page fault lần đầu; nhóm tưởng page fault luôn là lỗi, chưa phân biệt minor fault với major fault cần đọc dữ liệu từ storage.
Chương trình truy cập mảng lớn theo thứ tự ngẫu nhiên và phát sinh nhiều major page fault; hiệu năng giảm mạnh do working set vượt bộ nhớ vật lý và hệ thống phải đọc trang từ swap.
Máy chủ bắt đầu swap mạnh khi nhiều tiến trình hoạt động đồng thời; CPU không cao nhưng latency tăng vì hệ thống liên tục đưa trang ra vào bộ nhớ.
Hai tiến trình fork() từ cùng một tiến trình lớn; ban đầu bộ nhớ không nhân đôi do copy-on-write, nhưng khi cả hai ghi vào nhiều trang, mức sử dụng RAM tăng nhanh.
Một ứng dụng dùng mmap để đọc file lớn nhưng giữ mapping lâu sau khi file bị truncate; truy cập vùng mapping vượt kích thước file gây SIGBUS và tiến trình kết thúc bất ngờ.
Ứng dụng ghi dữ liệu qua nhiều buffer nhưng không flush đúng thời điểm; khi crash, dữ liệu ở user-space buffer mất dù nhóm tin rằng write đã được gọi.
Nhóm dùng shared memory để trao đổi dữ liệu giữa các process nhưng không có cơ chế đồng bộ; reader quan sát cấu trúc đang được writer cập nhật và nhận trạng thái không nhất quán.
Một tiến trình mở file liên tục nhưng không đóng descriptor; sau nhiều giờ, open() thất bại với Too many open files dù dung lượng đĩa còn nhiều.
Ứng dụng xóa một file log lớn nhưng dung lượng filesystem không giảm; process khác vẫn giữ file descriptor mở tới inode đã unlink và dữ liệu chỉ được giải phóng khi descriptor cuối đóng.
Quản trị viên tạo hard link rồi xóa tên file gốc; dữ liệu vẫn tồn tại vì inode còn được tham chiếu bởi tên khác, gây nhầm lẫn khi dọn dẹp dung lượng.
Một ứng dụng dùng symlink trỏ tới thư mục cấu hình mới; sau khi đường dẫn đích bị đổi, service không khởi động được dù symlink vẫn tồn tại.
Tiến trình có quyền đọc file nhưng không thể mở file vì thiếu quyền execute trên một thư mục cha; nhóm chỉ kiểm tra permission của file đích mà bỏ qua quyền traverse trên đường dẫn.
File được tạo bởi service có mode rộng hơn dự kiến do umask không được cấu hình trong systemd unit; thông tin nội bộ bị đọc bởi tài khoản người dùng khác.
Ứng dụng chạy với quyền root để ghi một file nhưng sau đó xử lý dữ liệu do người dùng kiểm soát; lỗi path traversal cho phép ghi đè file ngoài thư mục dự kiến.
Một thư mục có ACL cho phép nhóm hỗ trợ đọc log nhưng mode bits không thể hiện đầy đủ quyền thực tế; đội vận hành kết luận sai khi chỉ xem ls -l.
Dịch vụ mở file cấu hình lúc khởi động rồi giữ descriptor; quản trị viên thay file và restart một phần hệ thống nhưng tiến trình cũ tiếp tục đọc inode cũ cho tới khi reload.
Ứng dụng tạo nhiều file nhỏ trong một filesystem có nhiều inode nhưng còn dung lượng byte; tạo file mới thất bại vì hết inode dù df vẫn hiển thị còn nhiều GB.
Một filesystem đầy do file log tăng liên tục; ứng dụng không thể ghi log và bắt đầu lỗi nghiệp vụ, trong khi đội trực chỉ theo dõi dung lượng CPU và RAM.
Máy chủ ghi tuần tự vào ổ đĩa nhanh nhưng truy vấn nhiều file nhỏ ngẫu nhiên bị chậm; nhóm cần phân biệt throughput tuần tự với IOPS và độ trễ I/O.
Ứng dụng ghi dữ liệu quan trọng rồi gọi fsync() cho từng record; độ bền tăng nhưng I/O latency và số lần flush làm throughput giảm mạnh.
Một ứng dụng ghi log với buffered I/O; khi process bị kill -9, dữ liệu chưa flush từ user-space buffer mất dù file đã tồn tại trên filesystem.
Thiết bị block có hàng đợi I/O sâu và nhiều request đồng thời; latency tăng khi queueing vượt khả năng xử lý của storage dù throughput vẫn đạt mức cao.
Driver thiết bị không phản hồi interrupt đúng cách sau một bản cập nhật kernel; tiến trình chờ I/O kéo dài và kernel log ghi nhận timeout từ thiết bị.
Một tiến trình nhận SIGTERM nhưng không xử lý graceful shutdown; supervisor chờ hết thời gian rồi gửi SIGKILL, khiến tác vụ chưa flush dữ liệu và file tạm còn dang dở.
Ứng dụng dùng pipe giữa hai process nhưng reader thoát sớm; writer nhận SIGPIPE hoặc lỗi EPIPE và nhóm cần xử lý vòng đời hai đầu của IPC.
Container giới hạn CPU bằng cgroup quota; ứng dụng có nhiều thread runnable nhưng bị throttling theo chu kỳ dù host còn CPU rảnh.
Container nhìn thấy toàn bộ RAM của host qua một metric cũ nhưng cgroup giới hạn bộ nhớ thấp hơn; ứng dụng bị OOM-kill khi vượt limit của container.
Một ứng dụng trong container dùng PID namespace nên PID hiển thị khác với PID trên host; đội trực gửi signal nhầm process khi không phân biệt namespace.
Container chia sẻ kernel host nhưng cô lập mount, PID và network namespaces; nhóm nhầm container là một máy ảo có kernel riêng và dự đoán sai ranh giới bảo mật.
Máy chủ chạy nhiều virtual machine; một VM bị CPU steal time cao khi hypervisor tranh chấp CPU vật lý, dù bên trong guest hệ điều hành chỉ thấy CPU không được cấp đủ thời gian.
Ứng dụng trong VM báo thời gian hệ thống nhảy bất thường sau khi host thay đổi clock source; timer và scheduler trong guest bị ảnh hưởng bởi đồng bộ thời gian ảo hóa.
Một VM được cấp RAM lớn nhưng hypervisor ballooning thu hồi một phần bộ nhớ; guest bắt đầu swap và latency tăng dù cấu hình RAM danh nghĩa không thay đổi.
Kernel module mới gây panic sau khi tải vào hệ thống; đội vận hành cần phân biệt lỗi ở user process với lỗi trong không gian kernel có thể làm dừng toàn máy.

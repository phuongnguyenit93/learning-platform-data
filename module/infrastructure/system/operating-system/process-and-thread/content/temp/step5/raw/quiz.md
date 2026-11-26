Câu 01. Process trong hệ điều hành thường được hiểu là gì?
A. Một luồng lệnh dùng chung bộ nhớ với mọi process.
B. Một tệp thực thi chưa được nạp vào bộ nhớ.
C. Một hàng đợi chứa các tác vụ chờ CPU.
D. Chương trình đang chạy trong vùng địa chỉ riêng.
Đáp án đúng: D

Câu 02. Thread trong cùng một process thường chia sẻ tài nguyên nào?
A. Một bộ đếm lệnh riêng cho toàn bộ process.
B. Stack, program counter và thanh ghi CPU của nhau.
C. Không gian địa chỉ và các tài nguyên của process.
D. Trạng thái chạy và ngữ cảnh CPU tại mọi thời điểm.
Đáp án đúng: C

Câu 03. Thread ở trạng thái blocked thường có đặc điểm nào?
A. Đang chiếm CPU và thực thi lệnh của ứng dụng.
B. Chờ sự kiện hoặc tài nguyên để tiếp tục chạy.
C. Đã kết thúc nhưng chưa được thu hồi tài nguyên.
D. Đang sẵn sàng chạy và chờ scheduler cấp CPU.
Đáp án đúng: B

Câu 04. Context switch giữa hai thread thường cần thực hiện việc gì?
A. Sao chép toàn bộ heap sang không gian địa chỉ mới.
B. Đóng mọi file descriptor của thread bị tạm dừng.
C. Biên dịch lại mã máy trước khi thread tiếp tục.
D. Lưu và khôi phục trạng thái thực thi của thread.
Đáp án đúng: D

Câu 05. Preemptive scheduling cho phép scheduler làm gì?
A. Chạy mọi thread đồng thời trên cùng một core.
B. Tạm dừng tác vụ để chuyển CPU sang tác vụ khác.
C. Chỉ chuyển CPU khi thread hiện tại tự nhường quyền.
D. Giữ một thread trên CPU cho tới khi process kết thúc.
Đáp án đúng: B

Câu 06. Time slice trong lập lịch CPU có ý nghĩa gì?
A. Khoảng chờ bắt buộc giữa hai lần context switch.
B. Thời gian cần để khôi phục toàn bộ address space.
C. Khoảng thời gian được cấp trước khi scheduler xét lại.
D. Thời gian tối đa một process được tồn tại trong hệ thống.
Đáp án đúng: C

Câu 07. Trên Linux, giá trị nice của tác vụ thông thường ảnh hưởng điều gì?
A. Mức ưu tiên cố định cao hơn mọi tác vụ kernel.
B. Số core mà process được phép sử dụng cùng lúc.
C. Thời gian tối đa process được phép chờ I/O.
D. Trọng số tương đối khi chia CPU cho tác vụ.
Đáp án đúng: D

Câu 08. Trên Windows, đơn vị nào thường được scheduler dispatch lên CPU?
A. Job object đại diện cho một nhóm ứng dụng.
B. Process được lập lịch như một luồng duy nhất.
C. Handle được mở bởi một process bất kỳ.
D. Thread được lập lịch bên trong process.
Đáp án đúng: D

Câu 09. Trên Linux, các thread của cùng một process có quan hệ PID/TID nào?
A. Chung thread-group ID nhưng mỗi thread có TID riêng.
B. Chung một TID nhưng mỗi thread có PID riêng.
C. Mỗi thread có PID và TID giống nhau trên toàn hệ thống.
D. Mỗi thread có PID riêng và không chia sẻ group ID.
Đáp án đúng: A

Câu 10. Sau fork() trên Linux, cơ chế copy-on-write thường có tác dụng gì?
A. Sao chép ngay toàn bộ vùng nhớ của parent sang child.
B. Chia sẻ trang nhớ cho tới khi một bên thực hiện ghi.
C. Chuyển toàn bộ heap của parent thành vùng nhớ chỉ đọc.
D. Gộp không gian địa chỉ child vào process cha.
Đáp án đúng: B

Câu 11. Một process con đã kết thúc nhưng chưa được parent thu thập trạng thái thường là gì?
A. Blocked thread đang chờ scheduler cấp CPU.
B. Orphan đang chạy độc lập sau khi parent kết thúc.
C. Daemon chờ hệ thống gửi tín hiệu khởi động.
D. Zombie chờ parent gọi wait để thu hồi entry.
Đáp án đúng: D

Câu 12. Chuyển từ user mode sang kernel mode khi gọi system call có nghĩa gì?
A. Luôn chuyển CPU sang một thread kernel khác.
B. Đổi chế độ đặc quyền, thread có thể vẫn chạy.
C. Xóa context của thread gọi trước khi vào kernel.
D. Luôn tạo process mới để thực thi system call.
Đáp án đúng: B

Câu 13. Pipe vô danh trên Unix thường phù hợp cho kiểu giao tiếp nào?
A. Truyền luồng byte giữa các process liên quan.
B. Gửi message có cấu trúc qua nhiều máy từ xa.
C. Chia sẻ trực tiếp heap object giữa hai process.
D. Phát broadcast tới mọi process trong hệ thống.
Đáp án đúng: A

Câu 14. Named pipe (FIFO) khác pipe vô danh ở điểm nào?
A. Chỉ hoạt động giữa hai host qua mạng TCP.
B. Có tên filesystem để process độc lập mở và dùng.
C. Chỉ cho phép process cha và con trao đổi dữ liệu.
D. Luôn truyền message theo ranh giới gói tin cố định.
Đáp án đúng: B

Câu 15. Ưu điểm chính của shared memory trong IPC là gì?
A. Mọi lần đọc ghi tự động được khóa nguyên tử.
B. Dữ liệu luôn được đồng bộ mà không cần primitive.
C. Kernel chuyển từng byte qua hai buffer riêng biệt.
D. Process truy cập cùng vùng nhớ, giảm sao chép.
Đáp án đúng: D

Câu 16. Message queue phù hợp khi các process cần gì?
A. Chia sẻ cùng một con trỏ heap để truy cập trực tiếp.
B. Truyền byte stream liên tục mà không có ranh giới message.
C. Gửi message riêng qua hàng đợi do hệ điều hành quản lý.
D. Gọi hàm trực tiếp trong không gian địa chỉ process khác.
Đáp án đúng: C

Câu 17. Socket có thể được dùng cho loại giao tiếp nào?
A. IPC cục bộ hoặc trao đổi dữ liệu qua mạng.
B. Chỉ đồng bộ thread qua mutex của kernel.
C. Chỉ chia sẻ bộ nhớ trong cùng một process.
D. Chỉ truyền tín hiệu bất đồng bộ không kèm payload.
Đáp án đúng: A

Câu 18. Signal trên Unix thường được dùng để làm gì?
A. Cấp phát vùng nhớ dùng chung giữa các process.
B. Đảm bảo thứ tự thực thi của nhiều thread.
C. Truyền payload lớn theo luồng byte giữa hai process.
D. Báo sự kiện bất đồng bộ cho process đích.
Đáp án đúng: D

Câu 19. Race condition xuất hiện trong trường hợp nào?
A. Hai thread chỉ đọc cùng dữ liệu bất biến trong bộ nhớ.
B. Một process chạy tuần tự trên một CPU core duy nhất.
C. Các thao tác đã được bảo vệ bằng cùng một mutex.
D. Kết quả phụ thuộc thứ tự truy cập khi thiếu đồng bộ.
Đáp án đúng: D

Câu 20. Mutex chủ yếu cung cấp cơ chế nào?
A. Một thread độc quyền vào critical section.
B. Đảm bảo một tác vụ luôn được scheduler ưu tiên.
C. Đếm số tài nguyên có thể được dùng đồng thời.
D. Gửi thông điệp giữa các process theo thứ tự FIFO.
Đáp án đúng: A

Câu 21. Counting semaphore thường biểu diễn điều gì?
A. Số lần một thread đã vào critical section.
B. Thứ tự ưu tiên của process trong run queue.
C. Số lượng permit hoặc tài nguyên có thể cấp đồng thời.
D. Danh tính thread đang sở hữu khóa hiện tại.
Đáp án đúng: C

Câu 22. Compare-and-swap (CAS) thực hiện thao tác nào?
A. Đổi hai giá trị mà không kiểm tra trạng thái ban đầu.
B. Cập nhật giá trị nếu giá trị hiện tại vẫn bằng giá trị kỳ vọng.
C. Chờ mutex được mở rồi tự động tăng bộ đếm.
D. Sao chép vùng nhớ và khóa mọi thread đang truy cập.
Đáp án đúng: B

Câu 23. Trong Java, synchronized trên cùng monitor cung cấp điều gì?
A. Loại trừ tương hỗ cùng quy tắc visibility giữa các lần khóa.
B. Chỉ khóa biến cục bộ trong stack của thread gọi.
C. Chỉ bảo đảm visibility nhưng không ngăn hai thread cùng vào.
D. Tự động tạo một thread mới cho mỗi lần gọi method.
Đáp án đúng: A

Câu 24. Java volatile bảo đảm điều gì với biến được khai báo?
A. Loại trừ tương hỗ giữa mọi thread truy cập biến.
B. Visibility và ordering theo quy tắc bộ nhớ Java.
C. Đưa biến vào heap riêng của từng thread.
D. Tính nguyên tử cho mọi chuỗi thao tác đọc rồi ghi.
Đáp án đúng: B

Câu 25. Trong Java Memory Model, happens-before có ý nghĩa nào?
A. Một cam kết thread sau luôn chạy trên cùng CPU core.
B. Một cơ chế tự động phát hiện và sửa mọi data race.
C. Một thứ tự bảo đảm visibility giữa các thao tác bộ nhớ.
D. Một thứ tự ưu tiên cố định cho các thread đang chờ.
Đáp án đúng: C

Câu 26. Bốn điều kiện Coffman cần đồng thời có để deadlock xảy ra là gì?
A. Mutual exclusion, hold-and-wait, no preemption, circular wait.
B. No preemption, thread pooling, resource sharing, starvation.
C. Mutual exclusion, preemption, fair scheduling, shared memory.
D. Hold-and-wait, lock timeout, atomic update, circular queue.
Đáp án đúng: A

Câu 27. Một cách phòng tránh deadlock khi lấy nhiều lock là gì?
A. Quy định thứ tự lấy lock thống nhất giữa các thread.
B. Giữ mọi lock cho tới khi process kết thúc hoàn toàn.
C. Tăng số thread để luôn có thread giải phóng lock.
D. Mỗi thread chọn thứ tự lock ngẫu nhiên khi chạy.
Đáp án đúng: A

Câu 28. Livelock khác deadlock ở điểm nào?
A. Các thread đều dừng và chờ tài nguyên không thể cấp.
B. Một thread chờ vô hạn vì scheduler không chọn nó.
C. Các thread vẫn hoạt động nhưng liên tục không tạo tiến triển.
D. Một process đã kết thúc nhưng parent chưa gọi wait.
Đáp án đúng: C

Câu 29. Starvation trong lập lịch hoặc đồng bộ thường là tình huống nào?
A. Process con kết thúc và giữ lại entry trong process table.
B. Hai thread giữ lock của nhau và không thể tiếp tục.
C. Một tác vụ chờ quá lâu vì liên tục không được cấp tài nguyên.
D. Các thread đổi trạng thái liên tục nhưng không có kết quả.
Đáp án đúng: C

Câu 30. Priority inversion xảy ra khi nào?
A. Scheduler đổi priority của mọi thread thành cùng một mức.
B. Thread ưu tiên cao bị chặn bởi thread ưu tiên thấp đang giữ lock.
C. Hai thread cùng ưu tiên ghi vào một biến atomic.
D. Thread ưu tiên thấp luôn chạy trước mọi thread khác.
Đáp án đúng: B

Câu 31. Thread pool giúp cải thiện ứng dụng chủ yếu bằng cách nào?
A. Tạo thread mới cho mỗi tác vụ rồi kết thúc ngay sau đó.
B. Đảm bảo mọi tác vụ chạy song song không giới hạn.
C. Loại bỏ hoàn toàn nhu cầu đồng bộ dữ liệu chia sẻ.
D. Tái sử dụng thread và kiểm soát số tác vụ chạy đồng thời.
Đáp án đúng: D

Câu 32. Vì sao executor thường cần bounded queue và rejection policy?
A. Giới hạn backlog và xử lý khi năng lực thực thi đã bão hòa.
B. Đảm bảo task được chạy theo thứ tự hoàn thành.
C. Bảo đảm mọi task luôn được xếp hàng không giới hạn.
D. Tăng số thread theo số task mà không cần giới hạn.
Đáp án đúng: A

Câu 33. Java virtual threads phù hợp nhất với loại workload nào?
A. Nhiều tác vụ đồng thời chủ yếu chờ I/O hoặc blocking.
B. Tác vụ native buộc phải dùng một kernel thread cố định.
C. Tác vụ cần khóa toàn bộ heap trong suốt vòng đời.
D. Tác vụ CPU-bound cần thêm sức mạnh tính toán mỗi core.
Đáp án đúng: A

Câu 34. Dùng ThreadLocal trong thread pool cần lưu ý điều gì?
A. ThreadLocal tự tạo thread mới và kết thúc sau mỗi task.
B. Giá trị ThreadLocal được chia sẻ giữa mọi worker thread.
C. Xóa giá trị sau tác vụ để tránh rò rỉ ngữ cảnh giữa task.
D. ThreadLocal tự đồng bộ mọi object được lưu trong đó.
Đáp án đúng: C

Câu 35. Muốn xem các thread của một process Linux, lệnh nào phù hợp?
A. Dùng mount để xem thread group trong kernel.
B. Dùng df -h để liệt kê thread đang chạy.
C. Dùng ps -L hoặc top -H để hiển thị thread.
D. Dùng ip addr để xem trạng thái thread của process.
Đáp án đúng: C

Câu 36. Trạng thái D trong cột STAT của ps trên Linux thường chỉ điều gì?
A. Stopped, process đã bị dừng bởi tín hiệu điều khiển.
B. Zombie, process đã kết thúc và chờ parent thu thập.
C. Runnable, thread sẵn sàng được scheduler chọn.
D. Uninterruptible sleep, thường liên quan chờ I/O.
Đáp án đúng: D

Câu 37. strace -f hữu ích khi điều tra process và thread Linux vì sao?
A. Đo chính xác CPU cache miss của từng thread.
B. Hiển thị flame graph từ các mẫu stack của JVM.
C. Theo dõi system call và tiếp tục theo dõi tiến trình con.
D. Đọc run queue và tự điều chỉnh nice của process.
Đáp án đúng: C

Câu 38. Trên Windows, công cụ nào hỗ trợ phân tích lịch CPU và context switch sâu?
A. Event Viewer filter theo log ứng dụng thông thường.
B. Windows Performance Recorder và Windows Performance Analyzer.
C. Disk Management và Device Manager của Windows.
D. Task Scheduler và Windows Update history.
Đáp án đúng: B

Câu 39. Muốn xem trạng thái BLOCKED, WAITING và stack của Java thread, nên dùng gì?
A. Dùng javap để xem bytecode của mọi thread đang chạy.
B. Tạo thread dump bằng jcmd Thread.print hoặc jstack.
C. Dùng jmap để liệt kê các lock đang được sở hữu.
D. Chạy jps để chỉ xem PID và tên các Java process.
Đáp án đúng: B

Câu 40. False sharing có thể làm giảm hiệu năng thế nào?
A. Các thread ghi biến khác nhau nhưng cùng cache line gây tranh chấp.
B. Các thread đọc cùng object bất biến và dùng chung một lock.
C. Một thread giữ mutex lâu khiến process khác thành zombie.
D. Các process dùng chung page nên không thể chạy song song.
Đáp án đúng: A

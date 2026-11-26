1. Vai trò chính của kernel trong hệ điều hành là gì?
A. Cung cấp giao diện đồ họa và quản lý cửa sổ cho người dùng.
B. Biên dịch mã nguồn và liên kết thư viện của ứng dụng.
C. Quản lý CPU, bộ nhớ, thiết bị và dịch vụ hệ thống.
D. Cung cấp API cấp cao và quản lý thư viện dùng chung cho ứng dụng.
Đáp án đúng: C

2. Điều gì mô tả đúng ranh giới giữa user mode và kernel mode?
A. User mode và kernel mode có cùng quyền truy cập; chỉ khác vùng bộ nhớ đang dùng.
B. User mode hạn chế lệnh đặc quyền; yêu cầu đặc quyền phải qua kernel.
C. Kernel mode chỉ chạy ứng dụng nền; user mode dành cho trình điều khiển thiết bị.
D. User mode được phép ghi thanh ghi thiết bị; kernel mode chỉ xác nhận kết quả.
Đáp án đúng: B

3. Khi một tiến trình gọi system call để đọc file, điều gì thường xảy ra?
A. Tiến trình chuyển hẳn thành kernel process và nhận PID mới.
B. CPU chuyển sang xử lý trong kernel rồi trả kết quả về tiến trình gọi.
C. Kernel sao chép toàn bộ file vào bộ nhớ riêng của tiến trình trước khi đọc.
D. Tiến trình gửi yêu cầu trực tiếp tới thiết bị mà không qua kernel.
Đáp án đúng: B

4. Khác biệt nào giữa chương trình và tiến trình là chính xác?
A. Chương trình là mã tĩnh; tiến trình là một thực thể đang chạy.
B. Chương trình luôn có PID; tiến trình chỉ tồn tại khi được lưu trên đĩa.
C. Chương trình chứa trạng thái CPU; tiến trình chỉ chứa các thư viện liên kết.
D. Chương trình là một lần thực thi; tiến trình là file mã nguồn trên đĩa.
Đáp án đúng: A

5. Trên hệ Unix, cặp fork() và exec() thường được dùng như thế nào?
A. fork() tạo process con; exec() nạp image mới vào process hiện tại.
B. fork() thay image hiện tại; exec() tạo tiến trình con với PID mới.
C. fork() tạo thread trong cùng tiến trình; exec() chỉ đổi mức ưu tiên CPU.
D. fork() mở file descriptor; exec() thu hồi tài nguyên của tiến trình cha.
Đáp án đúng: A

6. Một tiến trình đã kết thúc nhưng vẫn xuất hiện ở trạng thái zombie. Nguyên nhân thường là gì?
A. Tiến trình bị treo khi chờ thiết bị và chưa nhận được tín hiệu kết thúc.
B. Tiến trình con vẫn chạy nhưng bị scheduler tạm dừng để chờ CPU.
C. Kernel giữ toàn bộ bộ nhớ của tiến trình để tiến trình có thể tiếp tục.
D. Cha chưa gọi wait() hoặc waitpid() để thu trạng thái con.
Đáp án đúng: D

7. Orphan process trên Unix thường được xử lý ra sao?
A. Được chuyển thành zombie cho tới khi quản trị viên xóa PID.
B. Được nhận bởi init hoặc một tiến trình subreaper phù hợp.
C. Bị kernel kết thúc ngay vì không còn tiến trình cha quản lý.
D. Được gộp vào tiến trình anh em gần nhất trong cùng process group.
Đáp án đúng: B

8. Các thread thuộc cùng một process thường chia sẻ tài nguyên nào?
A. Stack riêng và bộ đếm chương trình của từng thread.
B. Trạng thái thanh ghi và lịch chạy của từng thread.
C. Instruction pointer và vùng stack của từng thread.
D. Không gian địa chỉ và bảng file descriptor của process.
Đáp án đúng: D

9. Context switch giữa hai thread trên CPU thường bao gồm thao tác nào?
A. Lưu trạng thái hiện tại rồi khôi phục trạng thái thread được chọn.
B. Biên dịch lại toàn bộ mã của thread sắp được chạy.
C. Sao chép toàn bộ heap của process sang một vùng địa chỉ mới.
D. Đóng các file descriptor đang mở rồi tạo lại khi thread tiếp tục.
Đáp án đúng: A

10. Race condition xuất hiện trong trường hợp nào?
A. Một tiến trình chờ I/O hoàn tất trước khi tiếp tục xử lý.
B. Nhiều thread chỉ đọc cùng dữ liệu bất biến trong bộ nhớ.
C. Kết quả phụ thuộc thứ tự truy cập dữ liệu chia sẻ không được đồng bộ.
D. Scheduler chuyển CPU giữa các thread theo một time slice cố định.
Đáp án đúng: C

11. Mutex thường được dùng để làm gì?
A. Bảo vệ vùng tới hạn bằng cơ chế loại trừ tương hỗ.
B. Chuyển tiến trình từ user mode sang kernel mode an toàn.
C. Tăng số thread có thể chạy đồng thời trên cùng một CPU.
D. Lưu trạng thái tiến trình khi xảy ra context switch.
Đáp án đúng: A

12. Một cách phổ biến để phòng deadlock do thứ tự lấy nhiều khóa là gì?
A. Áp dụng thứ tự lấy khóa thống nhất trên toàn bộ luồng thực thi.
B. Tăng ưu tiên cho mọi thread đang chờ một khóa.
C. Cho phép mọi thread giữ khóa vô thời hạn khi đã lấy thành công.
D. Tăng số lượng worker để mỗi thread có một khóa riêng.
Đáp án đúng: A

13. Priority inversion xảy ra khi tình huống nào xuất hiện?
A. Thread ưu tiên cao liên tục chiếm CPU, khiến thread ưu tiên thấp bị trì hoãn lâu.
B. Thread thấp giữ khóa cần cho thread cao, còn thread trung bình chiếm CPU.
C. Hai thread cùng ưu tiên chờ một tài nguyên đã được giải phóng.
D. Scheduler đổi thứ tự thread runnable sau mỗi lần hết time slice.
Đáp án đúng: B

14. Starvation của một thread mô tả hiện tượng nào?
A. Thread đã thoát nhưng tiến trình cha chưa thu thập trạng thái.
B. Hai thread giữ khóa của nhau và không thể tiếp tục thực thi.
C. Thread runnable liên tục không được cấp tài nguyên cần thiết.
D. Thread chờ thiết bị hoàn tất một thao tác I/O đang diễn ra.
Đáp án đúng: C

15. Trong preemptive scheduling, time slice chủ yếu có tác dụng gì?
A. Giới hạn thời gian một tác vụ được giữ CPU trước khi có thể bị ngắt.
B. Xác định lượng RAM tối đa mà một tiến trình được phép cấp phát.
C. Quy định thời gian chờ tối đa trước khi system call trả về.
D. Đặt thời hạn lưu dữ liệu trong page cache trước khi ghi ra đĩa.
Đáp án đúng: A

16. Khi một máy có nhiều lõi CPU chạy workload CPU-bound, điều gì giúp tăng khả năng song song?
A. Đưa mọi thread vào một hàng đợi để lần lượt chạy trên một lõi.
B. Chuyển toàn bộ thread thành process riêng để tránh dùng chung bộ nhớ.
C. Có nhiều thread runnable để scheduler phân phối trên các lõi khác nhau.
D. Tăng time slice của một thread để nó giữ CPU lâu hơn.
Đáp án đúng: C

17. Không gian địa chỉ ảo của một process có ý nghĩa gì?
A. Biểu diễn trực tiếp các sector vật lý trên ổ đĩa của máy.
B. Xác định vị trí cố định của mọi object trong RAM của host.
C. Cung cấp góc nhìn bộ nhớ riêng được ánh xạ tới bộ nhớ vật lý.
D. Lưu bảng tên file mà tiến trình đã mở trong filesystem.
Đáp án đúng: C

18. Khác biệt chính giữa minor page fault và major page fault là gì?
A. Minor luôn là lỗi truy cập; major luôn là thao tác ghi vào trang nhớ.
B. Major cần I/O nạp trang; minor thường không đọc storage.
C. Minor chỉ xảy ra trong kernel; major chỉ xảy ra trong user mode.
D. Major tạo process mới; minor tạo thread mới trong process hiện tại.
Đáp án đúng: B

19. Demand paging thường hoạt động theo nguyên tắc nào?
A. Nạp toàn bộ trang của chương trình vào RAM ngay khi process được tạo.
B. Giữ mọi trang trong swap và chỉ đưa vào CPU cache khi cần.
C. Sao chép toàn bộ không gian địa chỉ mỗi khi một thread được tạo.
D. Nạp trang vào bộ nhớ khi tiến trình lần đầu truy cập trang đó.
Đáp án đúng: D

20. Copy-on-write sau fork() giúp tiết kiệm bộ nhớ bằng cách nào?
A. Ghi ngay toàn bộ trang của tiến trình cha xuống swap trước khi fork.
B. Cấp một bản sao riêng của mọi trang cho tiến trình con ngay lập tức.
C. Cho phép hai process cùng ghi một trang vật lý mà không cần bảo vệ.
D. Chia sẻ trang ban đầu và chỉ sao chép khi một bên thực hiện ghi.
Đáp án đúng: D

21. Thrashing thường biểu hiện như thế nào?
A. CPU dành phần lớn thời gian chạy ứng dụng thay vì chuyển ngữ cảnh.
B. Hệ thống liên tục nạp và đẩy trang nhớ do working set vượt RAM.
C. Scheduler giữ một thread trên cùng CPU để tăng cache locality.
D. Filesystem liên tục cấp phát inode dù số file không thay đổi.
Đáp án đúng: B

22. mmap() cho phép chương trình thực hiện điều gì?
A. Chuyển một file thành process mới để scheduler quản lý riêng.
B. Gắn một vùng file hoặc bộ nhớ vào không gian địa chỉ của process.
C. Khóa toàn bộ dữ liệu file trong RAM cho tới khi process kết thúc.
D. Thay thế system call read() bằng thao tác ghi trực tiếp xuống thiết bị.
Đáp án đúng: B

23. Một container bị OOM-kill dù host vẫn còn RAM khả dụng. Nguyên nhân nào có thể giải thích?
A. Filesystem của container đã hết inode nên kernel thu hồi RAM.
B. Kernel luôn yêu cầu mọi container dùng hết RAM host trước.
C. Process trong container không được phép dùng bộ nhớ ảo.
D. Container đã vượt giới hạn bộ nhớ được áp dụng bởi cgroup.
Đáp án đúng: D

24. Vì sao write() thành công chưa chắc dữ liệu đã bền vững sau mất điện?
A. Kernel chỉ ghi dữ liệu khi tiến trình gọi close() đúng một lần.
B. write() chỉ cập nhật tên file và chưa chuyển byte nào vào bộ nhớ.
C. Dữ liệu có thể còn trong buffer hoặc page cache trước khi được đồng bộ.
D. write() trả về đồng nghĩa dữ liệu đã nằm bền vững trên thiết bị.
Đáp án đúng: C

25. Trong filesystem kiểu Unix, inode thường lưu thông tin nào?
A. Tên file hiển thị và đường dẫn tuyệt đối của mọi thư mục cha.
B. Tên file, quyền truy cập và đường dẫn tuyệt đối của file.
C. Danh sách tiến trình đang mở file và trạng thái file descriptor.
D. Metadata file cùng thông tin tham chiếu tới các khối dữ liệu.
Đáp án đúng: D

26. Khác biệt nào giữa hard link và symbolic link là chính xác?
A. Hard link lưu đường dẫn văn bản; symbolic link tham chiếu trực tiếp cùng inode.
B. Hard link chỉ dùng trong RAM; symbolic link chỉ tồn tại trong kernel.
C. Hard link là tên khác của cùng inode; symbolic link lưu đường dẫn đích.
D. Hard link luôn qua filesystem khác; symbolic link chỉ dùng cùng filesystem.
Đáp án đúng: C

27. Một file bị unlink khi vẫn còn process giữ file descriptor mở. Điều gì thường xảy ra?
A. File bị xóa nội dung ngay dù process vẫn đang đọc descriptor.
B. Giải phóng dữ liệu khi hết link và descriptor mở.
C. Đường dẫn file vẫn tồn tại cho tới khi descriptor cuối cùng được đóng.
D. File descriptor tự động được đóng khi unlink() thành công.
Đáp án đúng: B

28. Để mở /srv/app/config.yml, tiến trình thường cần quyền nào trên các thư mục cha?
A. Quyền execute trên từng thư mục cha để traverse đường dẫn.
B. Quyền read trên mọi thư mục cha để duyệt tới file đích.
C. Quyền write trên từng thư mục cha để tạo đường dẫn mới.
D. Quyền ownership trên mọi thư mục cha để kiểm tra file.
Đáp án đúng: A

29. Umask ảnh hưởng tới quyền file mới được tạo như thế nào?
A. Cấp thêm quyền execute cho file dựa trên nhóm sở hữu hiện tại.
B. Loại bỏ các bit quyền tương ứng khỏi mode mà ứng dụng yêu cầu.
C. Thay đổi owner và group của file sau khi tạo xong.
D. Ghi đè ACL hiện có để mọi người dùng có quyền giống nhau.
Đáp án đúng: B

30. Một process mở file và socket liên tục rồi gặp lỗi Too many open files. Nên kiểm tra gì trước?
A. Giới hạn file descriptor của process và các descriptor chưa được đóng.
B. Kích thước page cache mà kernel dành cho dữ liệu file.
C. Số lượng inode đã dùng trong filesystem chứa thư mục làm việc.
D. Số lượng thread runnable trong scheduler của hệ điều hành.
Đáp án đúng: A

31. Khác biệt nào giữa throughput và IOPS của thiết bị lưu trữ?
A. Throughput đo độ trễ một request; IOPS đếm số process đang chạy.
B. Throughput đếm số file đang mở; IOPS đo dung lượng RAM còn trống.
C. Throughput đo dữ liệu mỗi đơn vị thời gian; IOPS đếm số thao tác I/O.
D. Throughput chỉ áp dụng đọc tuần tự; IOPS chỉ áp dụng ghi tuần tự.
Đáp án đúng: C

32. Gọi fsync() sau mỗi record thường tạo ra đánh đổi nào?
A. Giảm độ bền dữ liệu để tăng số thao tác ghi đồng thời.
B. Bỏ qua page cache và khiến mọi lần ghi chỉ cập nhật metadata.
C. Thay đổi quyền truy cập file để các process khác đọc dữ liệu ngay.
D. Tăng độ bền nhưng giảm throughput do flush thường xuyên.
Đáp án đúng: D

33. Điều gì có thể xảy ra khi process ghi vào pipe sau khi mọi reader đã đóng đầu đọc?
A. Writer nhận EOF khi reader đóng đầu đọc và kết thúc ghi.
B. Kernel giữ dữ liệu trong pipe cho tới khi reader mở lại đầu đọc.
C. Writer chờ tới khi reader mở lại rồi tiếp tục ghi.
D. Writer nhận SIGPIPE hoặc lỗi EPIPE khi thực hiện thao tác ghi.
Đáp án đúng: D

34. Khác biệt nào giữa SIGTERM và SIGKILL trên Unix?
A. SIGTERM luôn kết thúc process ngay; SIGKILL cho phép xử lý cleanup.
B. SIGTERM chỉ gửi tới thread chính; SIGKILL chỉ gửi tới kernel.
C. SIGTERM có thể được xử lý; SIGKILL không thể bị bắt hoặc bỏ qua.
D. SIGTERM dùng cho process nền; SIGKILL chỉ áp dụng cho process con.
Đáp án đúng: C

35. Đặc điểm nào phân biệt container với máy ảo truyền thống?
A. Dùng namespaces và cgroups để cô lập, nhưng chia sẻ kernel host.
B. Container dùng hypervisor để khởi động một guest OS độc lập.
C. Mỗi container chạy kernel riêng và mô phỏng toàn bộ phần cứng.
D. Container luôn có filesystem và CPU riêng không chia sẻ với host.
Đáp án đúng: A

36. Trong mô hình máy ảo, hypervisor và guest operating system có quan hệ nào?
A. Hypervisor chỉ quản lý file; guest OS điều khiển trực tiếp phần cứng vật lý.
B. Guest OS dùng chung kernel host; hypervisor chỉ tạo network namespace.
C. Hypervisor chạy bên trong process ứng dụng; guest OS là một container.
D. Hypervisor cung cấp phần cứng ảo; guest OS chạy kernel riêng trên phần cứng đó.
Đáp án đúng: D

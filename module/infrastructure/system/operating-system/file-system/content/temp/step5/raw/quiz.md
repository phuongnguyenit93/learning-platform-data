VFS trong Linux chủ yếu cung cấp vai trò nào khi ứng dụng truy cập tệp?
A. Cung cấp giao diện thống nhất cho nhiều loại filesystem khác nhau.
B. Quản lý trực tiếp sector vật lý cùng lịch cấp phát của mọi thiết bị lưu trữ.
C. Thay thế cơ chế kiểm tra quyền của từng filesystem cụ thể.
D. Bảo đảm mọi lần ghi tệp được lưu bền vững ngay lập tức.
Đáp án đúng: A

Thông tin nào thường được lưu trong inode của một tệp Linux?
A. Tên tệp hiển thị trong từng thư mục chứa nó và đường dẫn cha.
B. Metadata và tham chiếu tới các block dữ liệu của tệp.
C. Đường dẫn tuyệt đối từ root tới vị trí của tệp.
D. Danh sách mọi tiến trình đang mở tệp hiện tại.
Đáp án đúng: B

Dentry cache giúp tăng tốc thao tác phân giải pathname bằng cách nào?
A. Ghi nhớ quan hệ giữa tên trong thư mục và đối tượng inode.
B. Lưu toàn bộ nội dung tệp để tránh đọc lại từ thiết bị.
C. Giữ cố định quyền truy cập của tệp sau lần kiểm tra đầu.
D. Ánh xạ mọi pathname trực tiếp thành địa chỉ block vật lý của tệp.
Đáp án đúng: A

Hai tiến trình dùng chung một open file description thường chia sẻ trạng thái nào?
A. Số file descriptor và cờ close-on-exec riêng của từng process.
B. Quyền sở hữu inode và mode của tệp trên filesystem.
C. File offset hiện tại và một số trạng thái của lần open.
D. Mount namespace và thư mục làm việc của từng tiến trình gọi open.
Đáp án đúng: C

Điều gì đúng khi tạo hard link tới một tệp thông thường?
A. Tạo inode mới rồi sao chép nội dung sang inode đó.
B. Tạo thêm một directory entry trỏ tới cùng inode.
C. Lưu pathname của tệp gốc vào nội dung liên kết mới.
D. Chuyển dữ liệu của tệp sang một filesystem khác.
Đáp án đúng: B

Symbolic link khác hard link ở đặc điểm cốt lõi nào?
A. Luôn chứa bản sao dữ liệu của tệp đích trong inode riêng.
B. Không thể trỏ tới đường dẫn nằm trên filesystem khác.
C. Lưu pathname đích và được phân giải khi truy cập.
D. Làm tăng link count của inode mà pathname chỉ tới.
Đáp án đúng: C

Điều gì xảy ra khi unlink tên cuối cùng của tệp đang được mở?
A. Kernel đóng ngay mọi file descriptor đang mở còn tham chiếu tới tệp đó.
B. Nội dung được giữ tới khi link cuối và open reference biến mất.
C. Inode bị xóa ngay cả khi tiến trình vẫn đang đọc tệp.
D. Kernel tự tạo một hard link ẩn trong thư mục gốc.
Đáp án đúng: B

Quyền execute trên một thư mục Linux cho phép người dùng thực hiện việc gì?
A. Đọc nội dung mọi tệp trong thư mục mà không cần quyền read.
B. Tạo tệp mới trong thư mục mà không cần quyền write.
C. Đổi owner của các mục con mà không cần đặc quyền.
D. Tra cứu và đi xuyên qua thư mục khi phân giải đường dẫn.
Đáp án đúng: D

ACL mask ảnh hưởng tới quyền hiệu lực của các entry nào?
A. Chỉ quyền của owner và nhóm sở hữu inode.
B. Chỉ quyền của root và tiến trình có capability phù hợp.
C. Named user, owning group và named group entries.
D. Chỉ quyền execute trên thư mục cha của pathname.
Đáp án đúng: C

Sticky bit trên thư mục dùng chung như /tmp chủ yếu hạn chế thao tác nào?
A. Ngăn người dùng khác đọc nội dung tệp trong thư mục.
B. Ngăn tạo symbolic link tới đường dẫn nằm ngoài thư mục dùng chung.
C. Bắt buộc mọi tệp mới kế thừa group của thư mục cha.
D. Hạn chế xóa hoặc đổi tên mục thuộc người khác trong thư mục.
Đáp án đúng: D

Điều gì thường xảy ra với group của tệp mới trong thư mục có setgid bit?
A. Tệp luôn thuộc primary group của tiến trình tạo tệp.
B. Tệp được gán group root bất kể user tạo tệp.
C. Tệp kế thừa group sở hữu của thư mục chứa nó.
D. Tệp nhận toàn bộ ACL của mọi thư mục tổ tiên.
Đáp án đúng: C

Mount namespace cung cấp khả năng nào cho tiến trình Linux?
A. Nhìn thấy một cây mount riêng biệt với namespace khác.
B. Dùng chung mọi mount point với tất cả container trên host.
C. Thay đổi inode number của các tệp trong filesystem.
D. Mã hóa tự động nội dung của mọi volume được mount.
Đáp án đúng: A

Bind mount thường được dùng để thực hiện thao tác nào?
A. Tạo bản sao độc lập của toàn bộ dữ liệu tại đường dẫn mới.
B. Chuyển đổi filesystem đang chứa thư mục sang định dạng khác.
C. Đồng bộ nội dung của hai thư mục theo hai chiều tự động.
D. Gắn lại cùng một cây thư mục tại một mount point khác.
Đáp án đúng: D

OverlayFS thường thực hiện copy-up trong trường hợp nào?
A. Khi đọc lần đầu tệp chỉ có ở lower layer và tạo upper copy.
B. Khi mount namespace được tạo cho container mới.
C. Khi ghi thay đổi lên đối tượng hiện chỉ có ở lower layer.
D. Khi xóa một tệp đã có sẵn trong upper layer.
Đáp án đúng: C

Điều gì xảy ra với dữ liệu nằm sẵn trong thư mục mount point sau khi mount filesystem khác lên đó?
A. Dữ liệu được tự động chuyển sang filesystem vừa mount.
B. Dữ liệu được hợp nhất vào root directory của filesystem mới.
C. Dữ liệu bị xóa khỏi thiết bị lưu trữ ngay khi mount thành công.
D. Dữ liệu cũ bị che khuất cho tới khi filesystem được unmount.
Đáp án đúng: D

Mount propagation kiểu shared có ý nghĩa gì?
A. Mọi thao tác đọc file được chia sẻ giữa các tiến trình.
B. Các sự kiện mount và unmount có thể lan giữa peer groups.
C. Dữ liệu ghi ở một mount point tự nhân bản sang mount khác.
D. Quyền truy cập của mount point được đồng bộ theo thời gian.
Đáp án đúng: B

Page cache của Linux chủ yếu giúp cải thiện loại thao tác nào?
A. Đọc và ghi dữ liệu tệp bằng cách giữ các trang trong RAM.
B. Tra cứu user ID và group ID từ cơ sở dữ liệu cục bộ của hệ thống.
C. Phân giải tên miền trước khi mở kết nối mạng.
D. Cấp phát inode mới cho mọi lần mở file descriptor.
Đáp án đúng: A

Một lần write() trả về thành công thường bảo đảm điều gì?
A. Dữ liệu đã nằm trên thiết bị lưu trữ không mất khi mất điện.
B. Metadata thư mục cha đã được ghi bền vững xuống thiết bị.
C. Dữ liệu đã được chấp nhận vào kernel, có thể còn ở cache.
D. Mọi bản sao của dữ liệu trên các thiết bị đã đồng bộ.
Đáp án đúng: C

Ứng dụng cần yêu cầu đồng bộ dữ liệu và metadata của một tệp đang mở nên dùng thao tác nào?
A. Gọi fsync() trên file descriptor của tệp đó.
B. Gọi stat() để đọc lại metadata hiện tại của tệp.
C. Gọi close() rồi giả định thiết bị đã flush hoàn toàn.
D. Gọi syncfs() trên một filesystem bất kỳ của máy.
Đáp án đúng: A

Để thay thế tệp cấu hình nguyên tử và tăng độ bền sau crash, quy trình nào phù hợp?
A. Ghi đè trực tiếp file đích rồi gọi stat() kiểm tra kích thước.
B. Xóa file đích, tạo file mới và chỉ gọi close() sau khi ghi.
C. Ghi file tạm rồi copy từng block sang file đích đang mở.
D. Ghi file tạm, fsync file, rename và đồng bộ thư mục cha.
Đáp án đúng: D

Journaling filesystem chủ yếu giúp bảo vệ điều gì sau sự cố hệ thống?
A. Bảo đảm mọi transaction nghiệp vụ của ứng dụng được commit.
B. Khôi phục tính nhất quán của metadata theo cơ chế journal.
C. Ngăn mất mọi dữ liệu vừa được ghi trước thời điểm mất điện.
D. Tự tạo bản sao dự phòng của mọi tệp đã bị xóa.
Đáp án đúng: B

Vì sao sparse file có thể có kích thước logic lớn hơn dung lượng block đã cấp phát?
A. File dùng nhiều hard link nên mọi tên cùng chia sẻ một bản dữ liệu duy nhất.
B. Filesystem nén mọi vùng zero thành metadata trong inode.
C. Page cache giữ nội dung zero thay cho việc cấp phát block.
D. Các vùng chưa ghi được biểu diễn như hole, không cần block dữ liệu.
Đáp án đúng: D

Lệnh nào phù hợp để kiểm tra filesystem Linux còn bao nhiêu inode khả dụng?
A. df -h để xem dung lượng tính theo đơn vị dễ đọc.
B. df -i để xem mức sử dụng inode của từng filesystem.
C. du -sh để cộng kích thước logic các thư mục.
D. lsblk -f để xem filesystem và UUID của thiết bị block.
Đáp án đúng: B

Vì sao df có thể báo dung lượng đã dùng cao hơn tổng du của các thư mục đang thấy?
A. File đã unlink vẫn được một tiến trình giữ mở.
B. Inode luôn chiếm toàn bộ dung lượng của partition.
C. Symbolic link làm nội dung đích được tính hai lần.
D. Page cache được tính như block dữ liệu đã cấp phát.
Đáp án đúng: A

Khi cần xem mức độ phân mảnh extent của một tệp trên Linux, công cụ nào hữu ích?
A. getfacl để đọc ACL và quyền hiệu lực của tệp.
B. findmnt để liệt kê mount point chứa đường dẫn.
C. filefrag để hiển thị thông tin extent của tệp.
D. lsof để liệt kê tiến trình đang giữ file descriptor.
Đáp án đúng: C

User quota thường giới hạn loại tài nguyên nào trên filesystem?
A. Dung lượng block và số inode mà một user được sử dụng.
B. Dung lượng block và inode của toàn bộ thành viên trong một group.
C. Dung lượng block và inode theo project ID của cây thư mục.
D. Số file descriptor và socket mà user có thể mở.
Đáp án đúng: A

Project quota thường hữu ích khi cần giới hạn dung lượng theo tiêu chí nào?
A. Theo user ID của tài khoản sở hữu các tệp.
B. Theo group ID của nhóm sở hữu các tệp trong cây thư mục.
C. Theo project ID gắn với một cây thư mục hoặc nhóm dữ liệu.
D. Theo process ID và toàn bộ các tệp mà process đó đang giữ mở.
Đáp án đúng: C

Btrfs snapshot thường tạo bản chụp nhanh nhờ cơ chế nào?
A. Sao chép vật lý toàn bộ block của subvolume sang vùng mới.
B. Dùng copy-on-write để chia sẻ extent chưa bị thay đổi.
C. Chuyển mọi file trong subvolume thành symbolic link.
D. Chỉ lưu danh sách pathname mà không giữ dữ liệu cũ.
Đáp án đúng: B

NFS client nhận lỗi stale file handle thường gợi ý tình huống nào?
A. DNS server không phân giải được hostname của NFS server.
B. Client đã hết inode cục bộ dù server vẫn còn dung lượng.
C. Quyền execute trên mount point của client không cho phép tra cứu file handle.
D. File handle tham chiếu đối tượng phía server không còn hợp lệ.
Đáp án đúng: D

Khi nhiều client cùng truy cập dữ liệu qua NFS, cách nào giúp phối hợp khóa file?
A. Chỉ dùng flock cục bộ trên từng máy client độc lập.
B. Dùng cơ chế locking được giao thức NFS hỗ trợ và cấu hình đúng.
C. Đặt noatime trên mọi client để khóa không bị thay đổi.
D. Tạo hard link riêng cho từng client để tránh xung đột khi cùng ghi file.
Đáp án đúng: B

Trước khi chạy e2fsck để sửa lỗi ext filesystem, điều kiện nào quan trọng?
A. Giữ filesystem read-write để công cụ thấy cập nhật mới nhất.
B. Chỉ dừng ứng dụng ghi file, nhưng vẫn để filesystem được mount.
C. Chạy đồng thời trên mọi replica để so sánh metadata.
D. Unmount filesystem hoặc bảo đảm nó không được sử dụng.
Đáp án đúng: D

Công cụ nào chuyên dùng để kiểm tra và sửa chữa filesystem XFS?
A. e2fsck với tùy chọn force để quét metadata XFS.
B. xfs_db để xem và phân tích metadata của filesystem.
C. xfs_repair trên filesystem đã được unmount phù hợp.
D. xfs_fsr để chống phân mảnh các file trên XFS đang mount.
Đáp án đúng: C

Filesystem tự remount read-only sau lỗi I/O; bước chẩn đoán ban đầu nào hợp lý nhất?
A. Kiểm tra kernel log và tình trạng thiết bị hoặc đường lưu trữ.
B. Chạy fsck trực tiếp trên volume đang mount để khôi phục metadata.
C. Remount read-write rồi thử lại thao tác ghi của ứng dụng.
D. Tăng timeout I/O của ứng dụng để tránh lỗi ghi lặp lại.
Đáp án đúng: A

Muốn backup database đang hoạt động với nhiều file liên quan nhất quán, cách nào phù hợp?
A. Copy lần lượt mọi file dữ liệu khi database tiếp tục ghi bình thường.
B. Chỉ sao lưu WAL vì database có thể dựng lại mọi file dữ liệu từ đó.
C. Tạo snapshot volume không quiesce rồi coi là application-consistent.
D. Dùng backup của database hoặc snapshot có bước quiesce phù hợp.
Đáp án đúng: D

fscrypt trên Linux chủ yếu cung cấp cơ chế nào?
A. Mã hóa nội dung và tên file theo policy của thư mục.
B. Mã hóa toàn bộ block device bằng một khóa duy nhất.
C. Tạo checksum cho mọi block để phát hiện lỗi phần cứng.
D. Nén dữ liệu file trước khi ghi xuống filesystem.
Đáp án đúng: A

Filesystem checksum và scrub có vai trò chính nào?
A. Tự động sửa mọi lỗi quyền truy cập và ACL trên file.
B. Phát hiện dữ liệu sai lệch và kiểm tra các block đã lưu.
C. Tăng tốc phân giải pathname bằng cách lưu dentry lâu hơn.
D. Bảo đảm ứng dụng luôn ghi dữ liệu theo thứ tự transaction.
Đáp án đúng: B

Bạn sẽ giải thích hệ thống tệp cung cấp những dịch vụ nào cho ứng dụng và nhân hệ điều hành như thế nào?
Bạn sẽ phân biệt file thường, thư mục, symbolic link, socket, FIFO và device file theo cách sử dụng ra sao?
Bạn sẽ mô tả đường đi của một thao tác mở file từ lời gọi hệ thống đến thiết bị lưu trữ qua những lớp nào?
Bạn sẽ giải thích vì sao ứng dụng truy cập nhiều loại filesystem thông qua cùng một giao diện hệ thống như thế nào?
Bạn sẽ phân biệt filesystem, partition, volume và thiết bị block khi thiết kế lưu trữ Linux ra sao?
Bạn sẽ xác định các thuộc tính cần cân nhắc khi chọn ext4, XFS hoặc Btrfs cho workload cụ thể như thế nào?
Bạn sẽ đánh giá khác biệt giữa filesystem cục bộ và filesystem mạng theo độ trễ, tính nhất quán và khả năng phục hồi ra sao?
Bạn sẽ mô tả vai trò của Virtual File System trong việc tách giao diện file chung khỏi cách lưu trữ riêng của từng filesystem như thế nào?
Bạn sẽ phân biệt VFS với filesystem driver và block layer trong kiến trúc Linux ra sao?
Bạn sẽ giải thích vai trò của superblock, inode, dentry và file object trong VFS như thế nào?
Bạn sẽ xác định trách nhiệm của các filesystem operations và inode operations khi một tiến trình truy cập file ra sao?
Bạn sẽ mô tả quan hệ giữa struct file, file descriptor và open file description như thế nào?
Bạn sẽ phân biệt file descriptor của tiến trình với đối tượng file đang được kernel quản lý ra sao?
Bạn sẽ giải thích vì sao hai tiến trình mở cùng một đường dẫn có thể có offset đọc ghi độc lập như thế nào?
Bạn sẽ phân tích điều gì xảy ra với file offset khi tiến trình gọi dup hoặc fork trên một file descriptor như thế nào?
Bạn sẽ mô tả quá trình tra cứu đường dẫn từ thư mục gốc hoặc thư mục làm việc hiện tại qua từng thành phần như thế nào?
Bạn sẽ phân biệt absolute path và relative path khi tiến trình thay đổi current working directory ra sao?
Bạn sẽ giải thích vai trò của dentry cache trong việc giảm chi phí tra cứu tên file như thế nào?
Bạn sẽ phân biệt dentry cache, inode cache và page cache theo loại thông tin được lưu ra sao?
Bạn sẽ giải thích negative dentry giúp tăng tốc tra cứu đường dẫn không tồn tại như thế nào?
Bạn sẽ xác định khi nào cache tên file cần được cập nhật sau thao tác tạo, đổi tên hoặc xóa file như thế nào?
Bạn sẽ phân tích tác động của đường dẫn có nhiều thành phần và nhiều symbolic link đến chi phí pathname lookup ra sao?
Bạn sẽ mô tả cách kernel xử lý symbolic link khi phân giải một đường dẫn lồng nhiều cấp như thế nào?
Bạn sẽ phân biệt symbolic link tương đối và tuyệt đối khi di chuyển cây thư mục ra sao?
Bạn sẽ xác định nguyên nhân symlink loop và cách công cụ namei hỗ trợ điều tra như thế nào?
Bạn sẽ giải thích giới hạn số lần kernel theo symbolic link để tránh vòng lặp đường dẫn như thế nào?
Bạn sẽ phân tích khác biệt giữa thao tác mở file bằng path và mở tương đối với directory file descriptor qua openat như thế nào?
Bạn sẽ sử dụng directory file descriptor để giảm rủi ro thay đổi current working directory trong ứng dụng đa luồng ra sao?
Bạn sẽ giải thích nguy cơ TOCTOU khi ứng dụng kiểm tra đường dẫn rồi mới mở file như thế nào?
Bạn sẽ thiết kế thao tác mở file an toàn trước symlink attack bằng các tùy chọn hoặc API phù hợp ra sao?
Bạn sẽ phân biệt inode với tên file và giải thích vì sao một inode có thể được tham chiếu bởi nhiều tên như thế nào?
Bạn sẽ liệt kê metadata thường được lưu trong inode và ý nghĩa của từng trường ra sao?
Bạn sẽ phân biệt inode number với file descriptor và xác định phạm vi duy nhất của inode number như thế nào?
Bạn sẽ giải thích directory entry liên kết tên trong thư mục với inode như thế nào?
Bạn sẽ mô tả hard link tham chiếu cùng inode và những giới hạn của hard link qua filesystem khác nhau ra sao?
Bạn sẽ phân biệt hard link và symbolic link khi file đích bị đổi tên hoặc xóa như thế nào?
Bạn sẽ giải thích link count thay đổi ra sao khi tạo hard link, xóa tên file hoặc xóa thư mục?
Bạn sẽ phân tích vì sao unlink không giải phóng dữ liệu ngay khi tiến trình vẫn giữ file descriptor đang mở như thế nào?
Bạn sẽ xác định thời điểm inode và các block dữ liệu có thể được thu hồi sau khi file bị xóa ra sao?
Bạn sẽ giải thích vì sao dung lượng đĩa chưa giảm sau khi xóa file và cách lsof giúp tìm file đã xóa nhưng còn mở như thế nào?
Bạn sẽ phân biệt atime, mtime và ctime cùng các tình huống làm từng timestamp thay đổi ra sao?
Bạn sẽ đánh giá tác động của relatime và noatime đến cập nhật metadata và hiệu năng như thế nào?
Bạn sẽ giải thích vì sao đổi tên file trong cùng filesystem thường có tính nguyên tử ở mức namespace như thế nào?
Bạn sẽ phân biệt rename trong cùng filesystem với thao tác di chuyển file qua hai filesystem về tính nguyên tử và lỗi EXDEV ra sao?
Bạn sẽ xác định điều gì xảy ra khi hai tiến trình đồng thời tạo file cùng tên bằng các cờ mở file khác nhau như thế nào?
Bạn sẽ mô tả các bước tạo file mới từ kiểm tra quyền thư mục đến cấp inode và liên kết tên ra sao?
Bạn sẽ giải thích vì sao quyền tạo hoặc xóa file chủ yếu được kiểm tra trên thư mục chứa nó như thế nào?
Bạn sẽ phân biệt quyền đọc, ghi và thực thi trên file thường với quyền trên thư mục như thế nào?
Bạn sẽ phân tích cách owner, group và other quyết định quyền truy cập một file Linux ra sao?
Bạn sẽ giải thích umask ảnh hưởng đến mode của file và thư mục mới được tạo như thế nào?
Bạn sẽ tính quyền thực tế của file mới khi ứng dụng truyền mode vào open hoặc mkdir và hệ thống áp dụng umask ra sao?
Bạn sẽ phân biệt setuid, setgid và sticky bit trên file hoặc thư mục theo tác dụng bảo mật nào?
Bạn sẽ giải thích vì sao sticky bit trên thư mục chia sẻ hạn chế việc xóa file của người dùng khác như thế nào?
Bạn sẽ đánh giá tác động của setgid trên thư mục nhóm đến group ownership của file mới ra sao?
Bạn sẽ phân biệt POSIX ACL với mode bits và extended attributes khi cần quản lý quyền cùng metadata mở rộng như thế nào?
Bạn sẽ sử dụng getfacl và setfacl để xác định quyền hiệu lực khi ACL mask giới hạn quyền như thế nào?
Bạn sẽ giải thích default ACL được kế thừa khi tạo file hoặc thư mục con ra sao?
Bạn sẽ xác định thứ tự kiểm tra owner, group, ACL và quyền root khi kernel quyết định truy cập file như thế nào?
Bạn sẽ phân biệt quyền root truyền thống với Linux capabilities khi tiến trình cần thao tác đặc quyền trên filesystem ra sao?
Bạn sẽ phân tích tác động của mount options nosuid, nodev và noexec đến bảo mật một filesystem như thế nào?
Bạn sẽ xác định vì sao chmod không thể khắc phục lỗi truy cập nếu filesystem được mount read-only hoặc chính sách khác đang chặn ra sao?
Bạn sẽ chẩn đoán lỗi Permission denied khi mode bits cho phép nhưng ACL, SELinux hoặc AppArmor có thể từ chối truy cập như thế nào?
Bạn sẽ giải thích mount gắn một filesystem vào cây thư mục thống nhất của Linux như thế nào?
Bạn sẽ phân biệt mount point với thư mục thông thường trước khi mount filesystem lên đó ra sao?
Bạn sẽ xác định điều gì xảy ra với nội dung thư mục mount point trong thời gian filesystem khác được gắn lên như thế nào?
Bạn sẽ sử dụng findmnt, mount và /proc/mounts để xác định filesystem cùng các tùy chọn đang hoạt động ra sao?
Bạn sẽ giải thích vai trò của /etc/fstab trong quá trình mount tự động khi khởi động như thế nào?
Bạn sẽ phân biệt mount theo UUID với mount theo tên thiết bị để tránh đổi thứ tự thiết bị sau reboot ra sao?
Bạn sẽ thiết kế mount options cho filesystem chứa log, dữ liệu ứng dụng và dữ liệu tạm theo nhu cầu khác nhau như thế nào?
Bạn sẽ giải thích bind mount tạo thêm một điểm truy cập đến cây thư mục hiện có ra sao?
Bạn sẽ phân biệt bind mount thông thường với recursive bind mount khi cây nguồn chứa các mount con như thế nào?
Bạn sẽ mô tả mount namespace giúp mỗi container hoặc tiến trình có góc nhìn cây mount riêng ra sao?
Bạn sẽ giải thích shared, private và slave mount propagation ảnh hưởng đến việc lan truyền mount event như thế nào?
Bạn sẽ kiểm tra vì sao một mount được tạo trong container không xuất hiện ở host hoặc container khác như thế nào?
Bạn sẽ phân biệt lazy unmount với unmount thông thường và đánh giá rủi ro của việc dùng lazy unmount ra sao?
Bạn sẽ xác định nguyên nhân umount báo target is busy bằng lsof, fuser hoặc thông tin mount namespace như thế nào?
Bạn sẽ giải thích tmpfs lưu dữ liệu trong bộ nhớ và swap khác với filesystem trên thiết bị block ra sao?
Bạn sẽ phân biệt procfs và sysfs với filesystem lưu dữ liệu bền vững như thế nào?
Bạn sẽ mô tả OverlayFS kết hợp lower, upper và work directory để tạo filesystem hợp nhất cho container ra sao?
Bạn sẽ giải thích copy-up của OverlayFS xảy ra khi container sửa một file thuộc lower layer như thế nào?
Bạn sẽ xác định vì sao thay đổi trong writable layer của container biến mất khi container bị xóa ra sao?
Bạn sẽ phân biệt bind mount dữ liệu bền vững với ghi dữ liệu vào writable layer của container như thế nào?
Bạn sẽ mô tả quá trình tạo filesystem trên block device từ phân vùng đến superblock và cấu trúc metadata ra sao?
Bạn sẽ phân biệt logical block, filesystem block và sector của thiết bị lưu trữ như thế nào?
Bạn sẽ giải thích filesystem cấp phát block dữ liệu và quản lý vùng trống bằng bitmap hoặc cấu trúc tương đương ra sao?
Bạn sẽ phân biệt inode exhaustion với hết dung lượng block khi tạo file mới thất bại như thế nào?
Bạn sẽ sử dụng df -h và df -i để xác định filesystem hết dung lượng hay hết inode ra sao?
Bạn sẽ giải thích vì sao một filesystem có thể còn dung lượng nhưng không thể tạo thêm file do hết inode như thế nào?
Bạn sẽ mô tả extents giúp quản lý các vùng block liên tiếp thay vì lưu từng block riêng lẻ ra sao?
Bạn sẽ phân tích ảnh hưởng của file fragmentation đến số lần truy cập thiết bị và hiệu năng đọc tuần tự như thế nào?
Bạn sẽ giải thích sparse file lưu các vùng chưa ghi mà không cấp phát block vật lý tương ứng ra sao?
Bạn sẽ phân biệt apparent size với disk usage khi dùng ls, stat và du trên sparse file như thế nào?
Bạn sẽ xác định vì sao file lớn có thể chiếm ít block thực tế hơn kích thước logic của nó ra sao?
Bạn sẽ mô tả journaling filesystem ghi lại metadata hoặc dữ liệu theo chế độ khác nhau để hỗ trợ phục hồi như thế nào?
Bạn sẽ phân biệt metadata journaling, ordered mode và data journaling về bảo đảm sau crash ra sao?
Bạn sẽ giải thích journal replay diễn ra khi filesystem được mount lại sau khi hệ thống tắt đột ngột như thế nào?
Bạn sẽ so sánh ext4 và XFS về cấu trúc cấp phát, khả năng mở rộng và công cụ phục hồi ra sao?
Bạn sẽ đánh giá Btrfs copy-on-write ảnh hưởng đến snapshot, fragmentation và hiệu năng ghi như thế nào?
Bạn sẽ phân biệt filesystem copy-on-write với journaling filesystem về cách bảo vệ metadata khi mất điện ra sao?
Bạn sẽ giải thích delayed allocation có thể cải thiện hiệu quả cấp phát block nhưng tạo hệ quả gì khi crash như thế nào?
Bạn sẽ xác định vai trò của filesystem UUID, label và superblock khi hệ thống nhận diện một filesystem ra sao?
Bạn sẽ phân tích tác động của block size và inode size đến file nhỏ, file lớn và chi phí metadata như thế nào?
Bạn sẽ lựa chọn filesystem phù hợp cho thư mục chứa hàng triệu file nhỏ so với kho file lớn theo tiêu chí nào?
Bạn sẽ giải thích page cache giúp giảm truy cập thiết bị khi đọc file lặp lại như thế nào?
Bạn sẽ mô tả quá trình buffered read sử dụng page cache trước khi lấy dữ liệu từ block device ra sao?
Bạn sẽ phân biệt cache hit và cache miss khi đo hiệu năng đọc file bằng những phép đo nào?
Bạn sẽ giải thích read-ahead giúp tăng tốc đọc tuần tự và khi nào nó có thể gây đọc thừa như thế nào?
Bạn sẽ mô tả dirty page được tạo ra khi ghi dữ liệu qua page cache và được writeback xuống thiết bị ra sao?
Bạn sẽ phân biệt thời điểm write system call trả về với thời điểm dữ liệu thực sự bền vững trên thiết bị như thế nào?
Bạn sẽ giải thích fsync và fdatasync khác nhau về phạm vi dữ liệu và metadata cần đồng bộ ra sao?
Bạn sẽ xác định khi nào cần fsync thư mục sau khi tạo hoặc đổi tên file để bảo đảm tên file bền vững qua crash như thế nào?
Bạn sẽ phân biệt sync toàn hệ thống với fsync trên một file về phạm vi và chi phí ra sao?
Bạn sẽ đánh giá rủi ro khi ứng dụng giả định write thành công đồng nghĩa dữ liệu đã được ghi bền vững như thế nào?
Bạn sẽ giải thích O_DIRECT bỏ qua hoặc hạn chế page cache và các yêu cầu căn chỉnh I/O như thế nào?
Bạn sẽ phân biệt buffered I/O, direct I/O và memory-mapped I/O theo cách dữ liệu đi qua kernel ra sao?
Bạn sẽ mô tả mmap ánh xạ file vào không gian địa chỉ tiến trình và xử lý page fault như thế nào?
Bạn sẽ phân tích vì sao SIGBUS có thể phát sinh khi file backing bị truncate trong lúc tiến trình truy cập vùng mmap ra sao?
Bạn sẽ xác định các trường hợp mmap phù hợp hơn read/write và những rủi ro đồng bộ dữ liệu như thế nào?
Bạn sẽ giải thích writeback throttling ảnh hưởng đến độ trễ của tiến trình ghi nhiều dữ liệu như thế nào?
Bạn sẽ phân biệt cache của filesystem với cache của thiết bị lưu trữ và controller như thế nào?
Bạn sẽ đánh giá vai trò của flush hoặc barrier khi cần bảo đảm thứ tự ghi dữ liệu và metadata ra sao?
Bạn sẽ giải thích vì sao ổ đĩa hoặc controller báo hoàn tất ghi nhưng dữ liệu vẫn có thể mất nếu cache không được bảo vệ như thế nào?
Bạn sẽ đo hiệu năng filesystem bằng throughput, IOPS và latency theo loại workload như thế nào?
Bạn sẽ phân biệt đọc tuần tự, đọc ngẫu nhiên, ghi đồng bộ và ghi bất đồng bộ khi thiết kế benchmark filesystem ra sao?
Bạn sẽ sử dụng iostat hoặc công cụ tương đương để phân biệt filesystem chậm do thiết bị bận với do ứng dụng phát sinh I/O nhỏ như thế nào?
Bạn sẽ xác định cache nóng làm sai lệch kết quả benchmark đọc file bằng phương pháp kiểm thử nào?
Bạn sẽ đánh giá ảnh hưởng của số lượng file trong một thư mục đến tra cứu, liệt kê và xóa file như thế nào?
Bạn sẽ phân tích vì sao tạo hoặc xóa hàng nghìn file nhỏ có thể chậm dù tổng dung lượng dữ liệu thấp ra sao?
Bạn sẽ lựa chọn kích thước buffer và chiến lược batching để giảm overhead syscall khi ghi nhiều file nhỏ như thế nào?
Bạn sẽ phân biệt filesystem latency với block device latency khi điều tra ứng dụng bị chậm do lưu trữ ra sao?
Bạn sẽ giải thích advisory file locks yêu cầu các tiến trình cùng tuân thủ và giới hạn của chúng trong việc ngăn ghi đè như thế nào?
Bạn sẽ phân biệt flock và fcntl record locks về phạm vi khóa, quan hệ giữa các tiến trình và vòng đời file descriptor ra sao?
Bạn sẽ thiết kế thao tác cập nhật file cấu hình an toàn bằng file tạm, fsync và atomic rename như thế nào?
Bạn sẽ xác định nguy cơ lost update khi nhiều tiến trình cùng ghi một file và cách phối hợp khóa ra sao?
Bạn sẽ giải thích inode locking và các cơ chế đồng bộ trong kernel giúp bảo vệ metadata filesystem như thế nào?
Bạn sẽ mô tả inotify theo dõi thay đổi file và những giới hạn khi queue sự kiện bị tràn ra sao?
Bạn sẽ phân biệt sự kiện inotify với trạng thái thực tế của filesystem khi nhiều thay đổi xảy ra nhanh như thế nào?
Bạn sẽ thiết kế ứng dụng theo dõi thư mục sao cho có thể phục hồi sau khi mất sự kiện inotify như thế nào?
Bạn sẽ phân tích hành vi cache và close-to-open consistency khi nhiều máy cùng truy cập filesystem NFS ra sao?
Bạn sẽ phân biệt lỗi permission tại NFS client với quyền và ánh xạ UID/GID ở NFS server như thế nào?
Bạn sẽ đánh giá ảnh hưởng của network partition đến thao tác đọc ghi trên NFS mount theo các tùy chọn mount ra sao?
Bạn sẽ lựa chọn NFS mount options và timeout phù hợp cho workload cần tính sẵn sàng và độ trễ như thế nào?
Bạn sẽ kiểm tra stale file handle và xác định nguyên nhân từ server export hoặc thay đổi inode như thế nào?
Bạn sẽ phân biệt quota theo user, group và project với giới hạn dung lượng của toàn filesystem ra sao?
Bạn sẽ xác định tình huống quota block còn nhưng quota inode đã hết khi ứng dụng tạo nhiều file nhỏ như thế nào?
Bạn sẽ thiết kế quota để một tenant không thể chiếm hết dung lượng hoặc inode của filesystem dùng chung ra sao?
Bạn sẽ sử dụng lsblk, blkid và findmnt để lần theo quan hệ giữa thiết bị, partition, filesystem và mount point như thế nào?
Bạn sẽ kiểm tra metadata inode, quyền và timestamp của một file bằng stat ra sao?
Bạn sẽ dùng namei để xác định thành phần đường dẫn nào gây Permission denied khi truy cập file như thế nào?
Bạn sẽ phân biệt df và du đo những gì khi tổng dung lượng sử dụng giữa hai công cụ không khớp nhau ra sao?
Bạn sẽ điều tra filesystem báo đầy nhưng du không tìm thấy file lớn bằng cách kiểm tra file đã xóa còn mở như thế nào?
Bạn sẽ sử dụng lsof và fuser để xác định tiến trình đang giữ file hoặc mount point bận ra sao?
Bạn sẽ kiểm tra filesystem read-only do lỗi thiết bị, lỗi metadata hoặc tùy chọn mount bằng log kernel như thế nào?
Bạn sẽ phân biệt lỗi I/O của block device với lỗi filesystem metadata corruption qua dmesg và công cụ chẩn đoán ra sao?
Bạn sẽ xác định khi nào cần chạy fsck và vì sao kiểm tra hoặc sửa chữa filesystem đang được mount read-write có thể nguy hiểm?
Bạn sẽ lựa chọn công cụ kiểm tra và sửa chữa phù hợp giữa ext4, XFS và Btrfs như thế nào?
Bạn sẽ phân biệt fsck.ext4 với xfs_repair về cách vận hành và điều kiện sử dụng ra sao?
Bạn sẽ thiết kế quy trình phục hồi sau filesystem corruption để bảo toàn dữ liệu trước khi chạy công cụ sửa chữa như thế nào?
Bạn sẽ đánh giá khả năng phục hồi dữ liệu từ snapshot, backup và journal theo từng loại sự cố ra sao?
Bạn sẽ xác minh tính toàn vẹn dữ liệu sau restore bằng checksum và kiểm tra ứng dụng như thế nào?
Bạn sẽ phân biệt snapshot filesystem với backup độc lập về khả năng bảo vệ trước lỗi thiết bị hoặc xóa nhầm ra sao?
Bạn sẽ thiết kế chính sách backup cho file đang được ứng dụng ghi liên tục để tránh bản sao không nhất quán như thế nào?
Bạn sẽ xác định tác động của filesystem encryption đến hiệu năng, quản lý khóa và khả năng khôi phục dữ liệu ra sao?
Bạn sẽ bảo vệ dữ liệu trên filesystem bằng encryption at rest, quyền truy cập và mount options như thế nào?
Bạn sẽ phân tích nguy cơ symlink attack trong thư mục tạm dùng chung và lựa chọn cách tạo file an toàn ra sao?
Bạn sẽ ngăn path traversal khi ứng dụng nhận đường dẫn file từ người dùng bằng những bước kiểm tra nào?
Bạn sẽ đánh giá rủi ro hard link attack khi một tiến trình đặc quyền ghi đè file do người dùng khác sở hữu như thế nào?
Bạn sẽ phân biệt quyền truy cập file ở host với quyền trong user namespace hoặc container như thế nào?
Bạn sẽ giải thích bind mount và mount namespace có thể làm lộ hoặc che khuất dữ liệu giữa host và container ra sao?
Bạn sẽ kiểm tra quyền truy cập file trong container khi UID/GID bên trong khác với quyền sở hữu trên host như thế nào?
Nếu ứng dụng nhận ENOSPC dù df vẫn báo còn dung lượng, bạn sẽ kiểm tra inode, quota, reserved blocks và filesystem metadata ra sao?
Nếu df báo filesystem đầy nhưng du tổng hợp nhỏ hơn nhiều, bạn sẽ tìm file đã xóa còn mở và các mount bị che khuất như thế nào?
Nếu file vừa ghi biến mất sau khi máy bị mất điện, bạn sẽ kiểm tra fsync, thứ tự rename và writeback như thế nào?
Nếu một tiến trình không thể xóa file trong thư mục chia sẻ dù có quyền ghi thư mục, bạn sẽ kiểm tra sticky bit và ACL ra sao?
Nếu một container thấy thư mục rỗng sau khi mount volume, bạn sẽ kiểm tra mount point, namespace và bind mount propagation như thế nào?
Nếu thao tác đọc file đầu tiên chậm nhưng các lần đọc sau nhanh, bạn sẽ dùng page cache và I/O metrics để kiểm chứng nguyên nhân ra sao?
Nếu NFS mount treo khi server mất kết nối, bạn sẽ phân tích hard hoặc soft mount, timeout và hành vi tiến trình như thế nào?
Nếu số inode tăng nhanh trong khi dung lượng đĩa gần như không đổi, bạn sẽ tìm nguồn tạo nhiều file nhỏ bằng công cụ nào?
Nếu một ứng dụng cập nhật file cấu hình trong lúc nhiều tiến trình đang đọc, bạn sẽ thiết kế atomic replacement và đồng bộ dữ liệu ra sao?
Nếu filesystem chuyển sang read-only sau lỗi I/O, bạn sẽ khoanh vùng thiết bị, kernel log và phương án phục hồi như thế nào?
Bạn sẽ xây dựng quy trình chẩn đoán filesystem từ đường dẫn, inode, quyền, mount, cache đến thiết bị block và xác minh phục hồi như thế nào?

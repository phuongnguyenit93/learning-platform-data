Virtual memory mang lại lợi ích cốt lõi nào cho mỗi process?
A. RAM vật lý được chia cố định riêng cho process.
B. Mọi process dùng chung địa chỉ ảo.
C. Không gian địa chỉ riêng, ánh xạ khi cần.
D. Process luôn được cấp một vùng RAM vật lý liên tục.
Đáp án đúng: C

Trong cơ chế paging, page và frame khác nhau ở điểm nào?
A. Page là RAM, frame là trang ảo.
B. Page và frame là hai tên gọi cho cùng đơn vị.
C. Page là trang ảo; frame là khung RAM.
D. Page là vùng đĩa, frame là vùng trong file.
Đáp án đúng: C

Page table dùng để thực hiện chức năng nào?
A. Chuyển địa chỉ file thành vị trí block trên đĩa.
B. Lưu nội dung page đã bị ghi ra thiết bị swap.
C. Ghi lịch sử page được CPU truy cập gần nhất.
D. Ánh xạ trang ảo sang frame và quyền truy cập.
Đáp án đúng: D

TLB giúp giảm chi phí nào khi truy cập bộ nhớ?
A. Tra cứu bản dịch địa chỉ ảo sang vật lý.
B. Đọc nội dung page từ thiết bị lưu trữ.
C. Chuyển dữ liệu giữa RAM và thiết bị bằng DMA.
D. Đồng bộ dữ liệu page cache xuống thiết bị.
Đáp án đúng: A

Điều gì thường xảy ra khi TLB miss nhưng page table có ánh xạ hợp lệ?
A. Process bị dừng vì địa chỉ ảo không hợp lệ.
B. Hệ thống tạo frame mới và sao chép toàn bộ page.
C. Kernel luôn đọc page từ swap vào RAM trước.
D. Tra page table rồi cập nhật bản dịch trong TLB.
Đáp án đúng: D

Khi một page fault hợp lệ do page chưa có trong RAM, hệ điều hành thường làm gì?
A. Nạp hoặc tạo page, cập nhật ánh xạ rồi tiếp tục.
B. Chuyển toàn bộ working set sang vùng swap.
C. Kết thúc process vì mọi page fault đều là lỗi truy cập.
D. Xóa page table của process rồi khởi chạy lại.
Đáp án đúng: A

Page fault major khác minor chủ yếu ở điểm nào?
A. Major do truy cập vùng nhớ sai quyền.
B. Major thường cần đọc page từ thiết bị lưu trữ.
C. Minor luôn phải đọc dữ liệu từ thiết bị lưu trữ.
D. Minor làm process kết thúc ngay sau khi phát sinh.
Đáp án đúng: B

Copy-on-write trì hoãn việc sao chép page đến thời điểm nào?
A. Khi page được đưa từ RAM sang swap.
B. Khi một bên ghi vào page đang được chia sẻ.
C. Khi TLB thay thế một bản dịch địa chỉ.
D. Ngay khi hai process cùng đọc một page.
Đáp án đúng: B

Thuật toán page replacement thường chọn page nào để thu hồi?
A. Page ít có khả năng được dùng lại theo chính sách.
B. Page vừa được truy cập gần nhất trong working set.
C. Page có địa chỉ ảo lớn nhất trong process.
D. Page mới được nạp gần nhất trong mọi trường hợp.
Đáp án đúng: A

Thrashing mô tả tình trạng nào của hệ thống bộ nhớ?
A. CPU chờ I/O thiết bị trong phần lớn thời gian.
B. Page cache chiếm RAM nhưng vẫn có thể thu hồi.
C. TLB miss tăng do bảng trang lớn hơn.
D. Paging liên tục làm giảm thời gian xử lý hữu ích.
Đáp án đúng: D

Page cache chủ yếu lưu loại dữ liệu nào trong RAM?
A. Nội dung file để tăng tốc những lần đọc sau.
B. Stack của thread đang chờ I/O hoàn tất.
C. Bản sao của mọi page anonymous trong swap.
D. Bản dịch địa chỉ ảo của mọi process.
Đáp án đúng: A

Anonymous memory khác file-backed memory ở đặc điểm nào?
A. Không gắn trực tiếp với nội dung của một file.
B. Luôn được chia sẻ giữa mọi process đang chạy.
C. Luôn nằm trong RAM và không thể bị swap.
D. Chỉ được dùng để lưu mã lệnh thực thi.
Đáp án đúng: A

Memory-mapped file cho phép ứng dụng thực hiện điều gì?
A. Gắn file vào page table mà không cần quyền truy cập.
B. Đọc toàn bộ file vào heap trước khi ánh xạ.
C. Truy cập file qua vùng địa chỉ ảo được ánh xạ.
D. Ghi file trực tiếp mà không qua bất kỳ page nào.
Đáp án đúng: C

Swap được hệ điều hành dùng chủ yếu để làm gì?
A. Thay thế page cache bằng vùng nhớ nhanh hơn.
B. Đưa page anonymous ít hoạt động ra vùng swap.
C. Tăng dung lượng RAM vật lý khả dụng của máy.
D. Giữ dữ liệu file đã đọc trong RAM để truy cập nhanh.
Đáp án đúng: B

Khi áp lực bộ nhớ nghiêm trọng và reclaim không đủ, OOM killer thường làm gì?
A. Xóa toàn bộ file cache trước khi dừng hệ thống.
B. Tự động tăng kích thước RAM vật lý cho máy.
C. Chọn process để kết thúc nhằm giải phóng RAM.
D. Chuyển mọi process sang trạng thái ngủ chờ.
Đáp án đúng: C

RSS của process biểu thị điều gì?
A. Không gian địa chỉ ảo đã reserve.
B. Dung lượng tối đa heap mà runtime cho phép dùng.
C. Tổng dung lượng file mà process đã đọc từ đĩa.
D. Bộ nhớ vật lý đang resident của process.
Đáp án đúng: D

Vì sao bộ nhớ page cache có thể làm số liệu RAM trống thấp?
A. Page cache luôn được tính vào RSS của mọi process.
B. Kernel đã chuyển toàn bộ page cache sang swap.
C. Có thể thu hồi khi hệ thống cần thêm RAM.
D. Không thể thu hồi ngay cả khi thiếu RAM.
Đáp án đúng: C

System call read() thường yêu cầu kernel thực hiện việc gì?
A. Tạo một thread để xử lý I/O bất đồng bộ.
B. Đọc từ file descriptor vào buffer của caller.
C. Ánh xạ file vào không gian địa chỉ của process.
D. Ghi dữ liệu trong buffer xuống thiết bị lưu trữ.
Đáp án đúng: B

Buffered file I/O thường tương tác với page cache ra sao?
A. Dữ liệu file thường đi qua page cache kernel.
B. Mọi file đều được đọc thẳng từ đĩa, bỏ cache.
C. Page cache chỉ được dùng cho dữ liệu của socket.
D. Ứng dụng phải tự quản lý page table cho file.
Đáp án đúng: A

Vì sao write() trả về thành công chưa chắc dữ liệu đã bền vững?
A. Lệnh write chỉ cập nhật metadata mà không nhận dữ liệu.
B. Kernel đã đồng bộ dữ liệu xuống thiết bị trước khi trả về.
C. Dữ liệu có thể mới nằm trong cache kernel.
D. write chỉ xác nhận file descriptor còn hợp lệ.
Đáp án đúng: C

Gọi fsync() trên file descriptor của tệp nhằm mục tiêu nào?
A. Chỉ đồng bộ metadata của thư mục chứa tệp.
B. Chờ process hoàn tất toàn bộ thread đang chạy.
C. Đồng bộ dữ liệu và metadata của tệp xuống storage.
D. Đồng bộ các file descriptor khác của process.
Đáp án đúng: C

Điểm khác biệt chính của synchronous và asynchronous I/O là gì?
A. Caller tiếp tục trước khi thao tác hoàn tất.
B. Sync luôn dùng DMA, còn async luôn dùng polling.
C. Async chỉ dùng cho thiết bị hỗ trợ DMA.
D. Sync chỉ áp dụng cho file, async chỉ áp dụng cho socket.
Đáp án đúng: A

Trong mô hình completion-based asynchronous I/O, ứng dụng thường nhận kết quả hoàn tất bằng cách nào?
A. Qua lần gọi read() đồng bộ tiếp theo trên descriptor.
B. Qua completion event hoặc queue theo API.
C. Qua lần kiểm tra thuộc tính file bằng fstat().
D. Qua giá trị trả về ngay khi gửi yêu cầu I/O.
Đáp án đúng: B

Polling khác interrupt-driven I/O ở cơ chế nào?
A. Polling chỉ hoạt động khi thiết bị hỗ trợ DMA.
B. Polling luôn dùng ít CPU hơn interrupt trong mọi tải.
C. Interrupt yêu cầu CPU kiểm tra thiết bị theo chu kỳ cố định.
D. Polling tự kiểm tra; interrupt báo khi có sự kiện.
Đáp án đúng: D

DMA giúp giảm công việc nào cho CPU?
A. Lập lịch thread chờ I/O hoàn tất.
B. Quản lý quyền truy cập trong page table.
C. Tính toán checksum của mọi dữ liệu được đọc.
D. Chuyển dữ liệu giữa thiết bị và RAM.
Đáp án đúng: D

Block device khác character device theo cách truy cập nào?
A. Character device luôn hỗ trợ truy cập ngẫu nhiên theo block.
B. Character device chỉ dùng để lưu trữ file lâu dài.
C. Block device truy cập dữ liệu theo khối có địa chỉ.
D. Block device chỉ truyền luồng byte tuần tự.
Đáp án đúng: C

IOPS, throughput và latency mô tả ba khía cạnh nào?
A. Số thao tác, lượng dữ liệu và độ trễ.
B. Số thread, tốc độ clock và thời gian khởi động máy.
C. Số process, dung lượng RAM và thời gian CPU rảnh.
D. Số page fault, tỷ lệ cache hit và kích thước swap.
Đáp án đúng: A

Queue depth quá cao có thể gây hệ quả nào khi thiết bị đã bão hòa?
A. Giảm latency vì mọi yêu cầu được xử lý đồng thời.
B. Tăng thời gian chờ khi throughput khó tăng thêm.
C. Loại bỏ hoàn toàn thời gian seek của thiết bị.
D. Giảm số I/O đang chờ xuống bằng không.
Đáp án đúng: B

Linux iowait thường phản ánh tình huống nào?
A. Process hiện tại dùng CPU để đọc file.
B. CPU idle khi có I/O đang chờ hoàn tất.
C. Thiết bị lưu trữ đã đạt mức throughput tối đa.
D. CPU đang xử lý dữ liệu file liên tục.
Đáp án đúng: B

Direct I/O thường có đặc điểm nào so với buffered I/O?
A. Chỉ hoạt động với file được ánh xạ bằng mmap.
B. Bỏ qua filesystem và ghi trực tiếp lên block device.
C. Truy cập dữ liệu file trực tiếp, tránh page cache.
D. Tự động cache mọi block trong heap của process.
Đáp án đúng: C

Read-ahead và write-back cache hỗ trợ I/O theo cách nào?
A. Đọc lại dữ liệu cũ và ghi ngay mọi thay đổi đồng bộ.
B. Đọc trước dữ liệu và trì hoãn một số lần ghi.
C. Nạp trước page của file và flush mọi ghi ngay lập tức.
D. Đọc page theo demand và ghi đồng bộ từng block.
Đáp án đúng: B

Working set giúp giải thích vấn đề nào khi cấp phát bộ nhớ?
A. Danh sách system call trong một chu kỳ CPU.
B. Các page được dùng trong cửa sổ thời gian gần đây.
C. Các page process đã truy cập kể từ khi khởi chạy.
D. Các block dữ liệu đang nằm trong queue của thiết bị.
Đáp án đúng: B

Khi hệ thống swap in/out liên tục, dấu hiệu nào đáng lo ngại nhất?
A. Thiết bị có queue depth thấp và latency ổn định.
B. Page cache đang phục vụ tốt các lần đọc lặp lại.
C. TLB hit tăng khi ứng dụng chạy nhiều thread.
D. Working set thiếu RAM, paging gây chậm kéo dài.
Đáp án đúng: D

Hai ánh xạ mmap dùng chung và riêng khác nhau thế nào khi ghi?
A. Cả hai luôn ghi thay đổi trực tiếp vào file gốc.
B. Private chia sẻ mọi thay đổi, shared luôn tạo bản sao.
C. Shared chỉ đọc, private luôn cấp phát toàn bộ file.
D. Shared phản ánh thay đổi; private dùng COW.
Đáp án đúng: D

Chỉ số nào giúp phân biệt áp lực bộ nhớ với memory leak trong ứng dụng?
A. Heap sau GC, allocation rate và object còn được giữ.
B. Số lượng file mở kết hợp số gói mạng nhận được.
C. Tỷ lệ CPU idle kết hợp tốc độ đọc tuần tự.
D. Tổng số system call kết hợp số lần context switch.
Đáp án đúng: A

Khi nghi ngờ I/O là nút thắt, nên xem nhóm số liệu nào cùng nhau?
A. Dung lượng swap, số user và thời gian khởi động.
B. Heap used, số class và số lần TLB hit.
C. Số thread, context switch và tỷ lệ cache hit CPU.
D. Latency, throughput, queue depth và I/O wait.
Đáp án đúng: D

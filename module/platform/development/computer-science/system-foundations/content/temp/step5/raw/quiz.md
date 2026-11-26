Câu 1. Giá trị lớn nhất biểu diễn bằng số nguyên không dấu 8 bit là gì?
A. 127, vì bit đầu dùng làm bit dấu của số
B. 255, vì có tổng cộng 2^8 giá trị khác nhau
C. 256, vì số trạng thái của 8 bit là 2^8
D. 128, vì nửa số trạng thái dành cho số âm
Đáp án đúng: B

Câu 2. Trong biểu diễn bù hai 8 bit, chuỗi nào thể hiện giá trị -1?
A. 10000000, với bit dấu được đặt lên một
B. 00000001, với một bit thấp nhất được đặt
C. 11111110, với hai bit thấp ở trạng thái 0
D. 11111111, với cả tám bit đều bằng một
Đáp án đúng: D

Câu 3. Kiểu little-endian lưu số nguyên nhiều byte như thế nào?
A. Byte có trọng số lớn nhất ở địa chỉ thấp
B. Bit có trọng số lớn nhất ở địa chỉ thấp
C. Byte có trọng số nhỏ nhất ở địa chỉ thấp
D. Bit có trọng số nhỏ nhất ở địa chỉ cao
Đáp án đúng: C

Câu 4. Cổng logic AND với hai đầu vào A và B xuất ra 1 khi nào?
A. Chỉ khi có ít nhất một đầu vào bằng 1
B. Chỉ khi cả hai đầu vào đều có giá trị 1
C. Chỉ khi hai đầu vào mang giá trị khác nhau
D. Chỉ khi cả hai đầu vào đều có giá trị 0
Đáp án đúng: B

Câu 5. Pipeline CPU chủ yếu tăng throughput bằng cách nào?
A. Chồng lấp các giai đoạn của nhiều lệnh CPU
B. Chạy toàn bộ một lệnh trong đúng một chu kỳ
C. Bỏ qua mọi hazard giữa các lệnh liên tiếp
D. Loại bỏ hoàn toàn thời gian truy cập bộ nhớ
Đáp án đúng: A

Câu 6. Với số lệnh, CPI và tần số CPU đã biết, công thức thời gian CPU gần đúng nào phù hợp?
A. Thời gian = số lệnh × tần số × CPI
B. Thời gian = số lệnh / (CPI × tần số)
C. Thời gian = CPI / (số lệnh × tần số)
D. Thời gian = số lệnh × CPI / tần số
Đáp án đúng: D

Câu 7. Truy cập tuần tự các phần tử gần nhau trong mảng khai thác đặc tính gì?
A. Tính cục bộ không gian của bộ nhớ đệm
B. Tính cô lập địa chỉ giữa các tiến trình
C. Tính nhất quán giao dịch của hệ thống tệp
D. Tính phân hoạch của vùng nhớ ảo giữa máy
Đáp án đúng: A

Câu 8. Trong bộ nhớ ảo có phân trang, bảng trang đảm nhiệm vai trò nào?
A. Ánh xạ địa chỉ tệp sang tên tiến trình đang chạy
B. Ánh xạ mã lệnh sang thanh ghi bên trong ALU
C. Ánh xạ trang ảo với frame vật lý và quyền truy cập
D. Ánh xạ cổng mạng sang địa chỉ tiến trình
Đáp án đúng: C

Câu 9. TLB trong hệ thống quản lý bộ nhớ thường lưu điều gì?
A. Bản sao toàn bộ dữ liệu nằm trong L1 cache
B. Danh sách process đã chờ CPU quá thời hạn
C. Bản ghi giao dịch ghi xuống thiết bị lưu trữ
D. Bản dịch địa chỉ trang ảo sang frame vật lý
Đáp án đúng: D

Câu 10. Trong cơ chế demand paging, page fault có thể phát sinh khi nào?
A. CPU truy cập một byte đang ở thanh ghi
B. Trang hợp lệ cần truy cập hiện chưa ở RAM
C. Cache hit trả dữ liệu từ L1 ngay tức thì
D. Trình liên kết xử lý xong các symbol ngoài
Đáp án đúng: B

Câu 11. Linker thường thực hiện nhiệm vụ nào trong quá trình build chương trình?
A. Phân tích biểu thức nguồn để tạo token đầu tiên
B. Điều phối các luồng khi chương trình đang thực thi
C. Ghép object file và giải quyết tham chiếu symbol
D. Theo dõi page fault trong không gian địa chỉ ảo
Đáp án đúng: C

Câu 12. System call giúp chương trình ở user mode làm gì?
A. Tự thực thi lệnh đặc quyền từ user mode
B. Yêu cầu kernel thực hiện một dịch vụ hệ thống
C. Bỏ qua lớp bảo vệ truy cập thiết bị ngoại vi
D. Thay đổi trực tiếp bảng trang của mọi tiến trình
Đáp án đúng: B

Câu 13. Cơ chế cách ly tiến trình thường dựa vào điều gì?
A. Không gian địa chỉ ảo và quyền truy cập riêng
B. Một vùng heap vật lý dùng chung cho mọi process
C. Một call stack thống nhất cho mọi tiến trình
D. Một bộ thanh ghi cố định cho mọi ứng dụng
Đáp án đúng: A

Câu 14. Hai thread trong cùng tiến trình thường chia sẻ và tách biệt tài nguyên nào?
A. Chia sẻ call stack; mỗi thread có heap riêng
B. Chia sẻ thanh ghi CPU; mỗi thread có process riêng
C. Chia sẻ địa chỉ ảo; mỗi thread có file system riêng
D. Chia sẻ heap; mỗi thread có call stack riêng
Đáp án đúng: D

Câu 15. Hai thread cập nhật biến đếm chung mà không đồng bộ có thể gây ra điều gì?
A. Lost update do thao tác đọc và ghi xen kẽ
B. TLB miss vì heap của mỗi thread tách biệt
C. Page fault bắt buộc ở mỗi phép cộng một đơn vị
D. Deadlock bắt buộc kể cả khi không dùng khóa
Đáp án đúng: A

Câu 16. Mutex phù hợp nhất khi cần đảm bảo điều kiện nào?
A. Tăng số lượng thread chạy đồng thời tối đa
B. Ghi mọi thao tác đồng bộ xuống hệ thống tệp
C. Chỉ một thread được vào vùng tới hạn một lúc
D. Mỗi thread luôn lấy nhiều khóa theo thứ tự tùy ý
Đáp án đúng: C

Câu 17. Trong các điều kiện gây deadlock, hold-and-wait nghĩa là gì?
A. Thread chờ CPU mà không nắm tài nguyên nào
B. Thread chỉ nắm khóa sau khi mọi khóa được giải phóng
C. Thread giữ tài nguyên và chờ thêm tài nguyên khác
D. Thread giải phóng toàn bộ khóa trước khi bắt đầu chờ
Đáp án đúng: C

Câu 18. Journaling filesystem thường cải thiện khả năng phục hồi bằng cách nào?
A. Ghi log thay đổi cấu trúc trước khi áp dụng chúng
B. Lưu vĩnh viễn mọi block dữ liệu vào bộ nhớ RAM
C. Tự sao lưu toàn bộ file sang máy chủ ở xa liên tục
D. Loại bỏ hoàn toàn khả năng mất dữ liệu khi mất điện
Đáp án đúng: A

Câu 19. Khác biệt phổ biến của TCP so với UDP là gì?
A. TCP truyền datagram không duy trì trạng thái
B. TCP không kiểm soát thứ tự byte nhận ở phía đích
C. TCP chỉ dùng để phân giải tên miền sang địa chỉ
D. TCP cung cấp luồng byte tin cậy và có thứ tự
Đáp án đúng: D

Câu 20. Khi cần gửi gói thời gian thực và tự xử lý mất gói, UDP có đặc điểm phù hợp nào?
A. Truyền datagram mà không cần thiết lập kết nối
B. Truyền byte stream tin cậy được giao thức đảm bảo
C. Tự phát lại mọi gói và xác nhận theo thứ tự
D. Tự cung cấp phân vùng địa chỉ ảo cho ứng dụng
Đáp án đúng: A

Câu 21. DNS thường cung cấp chức năng nào trong ngăn xếp mạng?
A. Mã hóa nội dung ứng dụng theo giao thức TLS
B. Phân giải tên miền thành bản ghi địa chỉ mạng
C. Đảm bảo luồng byte đến đúng thứ tự như TCP
D. Đặt lịch CPU cho socket kết nối đến máy chủ
Đáp án đúng: B

Câu 22. Hypervisor có vai trò nào trong công nghệ ảo hóa máy tính?
A. Biên dịch mã nguồn máy khách thành HTML
B. Gửi mọi gói mạng qua một cổng DNS duy nhất
C. Quản lý tài nguyên ảo cấp cho các máy khách
D. Thay mọi hệ điều hành khách bằng một process
Đáp án đúng: C

Câu 23. Namespace và cgroups trong Linux hỗ trợ container theo cách nào?
A. Namespace tăng xung CPU; cgroups thay thế kernel
B. Namespace ghi log I/O; cgroups quyết định DNS
C. Namespace tạo máy ảo; cgroups biên dịch bytecode
D. Namespace cô lập góc nhìn; cgroups giới hạn tài nguyên
Đáp án đúng: D

Câu 24. Khi client gửi lại yêu cầu sau timeout, idempotency giúp hệ phân tán ra sao?
A. Một request phải trả về đúng byte ở mọi lần gọi
B. Lặp cùng thao tác không tạo thêm tác dụng ngoài
C. Mọi request chỉ được phép thực hiện đúng một lần
D. Mỗi lần retry đều tạo thêm một giao dịch độc lập
Đáp án đúng: B

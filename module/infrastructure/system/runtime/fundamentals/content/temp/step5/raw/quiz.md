Khi nói một lỗi chỉ xuất hiện ở runtime, thời điểm xảy ra lỗi là khi nào?
A. Khi mã nguồn đang được đóng gói phát hành
B. Khi tệp thực thi đang được liên kết
C. Khi mã nguồn được phân tích cú pháp
D. Khi chương trình đang thực thi các lệnh
Đáp án đúng: D

Bộ nạp chương trình (loader) thường làm gì trước khi chương trình bắt đầu chạy?
A. Kiểm tra cú pháp các tệp nguồn trước khi chạy
B. Biên dịch các tệp nguồn thành mã máy khi xây dựng
C. Ánh xạ mã và dữ liệu vào bộ nhớ tiến trình
D. Đóng gói toàn bộ thư viện thành tệp triển khai
Đáp án đúng: C

Điểm khác biệt thường gặp giữa các thread trong cùng một process là gì?
A. Mỗi thread giữ một bản sao mã thực thi độc lập
B. Mỗi thread cần một tiến trình hệ điều hành riêng
C. Các thread chung địa chỉ nhưng giữ ngữ cảnh riêng
D. Mỗi thread sử dụng không gian địa chỉ tách biệt
Đáp án đúng: C

Địa chỉ bộ nhớ ảo của tiến trình giúp đạt điều gì?
A. Cấp cho mỗi tiến trình một vùng RAM vật lý cố định
B. Cho mọi tiến trình đọc trực tiếp bộ nhớ của nhau
C. Bỏ mọi cơ chế phân trang khi RAM còn dung lượng
D. Tạo không gian địa chỉ được ánh xạ và bảo vệ
Đáp án đúng: D

Trong nhiều môi trường thực thi, stack thường gắn với thành phần nào?
A. Bộ nhớ chung dành cho mọi lần cấp phát động
B. Khung gọi hàm và vị trí quay về sau lời gọi
C. Vùng dữ liệu tồn tại độc lập với chuỗi lời gọi
D. Vùng đệm hệ thống khi đọc ghi tệp qua ổ đĩa
Đáp án đúng: B

Heap thường được dùng cho nhu cầu nào khi chương trình chạy?
A. Lưu các khung gọi hàm theo thứ tự vào ra
B. Giữ bộ đệm lệnh bên trong bộ xử lý vật lý
C. Lưu địa chỉ của lệnh CPU kế tiếp cần chạy
D. Cấp phát vùng nhớ có vòng đời sử dụng linh hoạt
Đáp án đúng: D

Điều gì mô tả đúng hiện tượng rò rỉ bộ nhớ khi chương trình chạy?
A. Dữ liệu bộ đệm CPU bị thay thế bởi dữ liệu mới
B. Bộ nhớ hết cần dùng vẫn bị giữ và chưa giải phóng
C. Các trang bộ nhớ ảo được ánh xạ sang RAM vật lý
D. Tiến trình được cấp thêm RAM khi nhu cầu tăng
Đáp án đúng: B

Khi hai luồng cập nhật dữ liệu chung mà thiếu đồng bộ, lỗi nào có thể xuất hiện?
A. Hệ thống xếp thao tác theo lúc các luồng được tạo
B. Các luồng thấy cùng giá trị nhờ bộ đệm CPU
C. Mỗi lệnh ghi được coi như một giao dịch nguyên tử
D. Kết quả phụ thuộc vào thứ tự xen kẽ các thao tác
Đáp án đúng: D

Bế tắc (deadlock) thường xảy ra trong tình huống nào?
A. Hai luồng thay phiên lấy một khóa và hoàn tất
B. Một luồng ngủ chờ tín hiệu rồi tiếp tục chạy
C. Một luồng chờ khóa đến khi chủ khóa giải phóng
D. Hai luồng giữ khóa rồi chờ khóa của nhau
Đáp án đúng: D

Chuyển ngữ cảnh (context switch) là thao tác nào?
A. Chuyển mã nguồn thành mã máy trước khi khởi chạy
B. Lưu và phục hồi trạng thái khi đổi tác vụ
C. Chuyển dữ liệu từ RAM sang nơi lưu trữ phụ
D. Đổi tập thư viện mà chương trình đang sử dụng
Đáp án đúng: B

Bộ lập lịch (scheduler) quyết định điều gì khi nhiều luồng sẵn sàng chạy?
A. Mức ưu tiên lưu nhật ký của ứng dụng
B. Vị trí ánh xạ các thư viện trong RAM
C. Luồng sẵn sàng được sử dụng CPU tiếp theo
D. Thứ tự liên kết các tệp thực thi
Đáp án đúng: C

System call được dùng để làm gì?
A. Buộc CPU thực hiện mọi lệnh ở chế độ đặc quyền
B. Cho ứng dụng truy cập thiết bị mà không qua kernel
C. Yêu cầu kernel thực hiện dịch vụ có kiểm soát
D. Đổi thư viện tĩnh thành thư viện động lúc biên dịch
Đáp án đúng: C

Vì sao hệ điều hành thường phân biệt user mode và kernel mode?
A. Cấm các chương trình cùng chạy chia sẻ dữ liệu
B. Giữ cho mọi tiến trình đạt tốc độ xử lý như nhau
C. Cho mỗi chương trình một bộ lệnh CPU hoàn toàn khác
D. Giới hạn thao tác đặc quyền mà ứng dụng được làm
Đáp án đúng: D

Điều nào đúng về stdout và stderr của một tiến trình?
A. Luồng lỗi luôn phải đi qua luồng xuất chuẩn
B. Hai luồng xuất có thể được chuyển hướng độc lập
C. Luồng xuất chuẩn chỉ nhận dữ liệu dạng văn bản
D. Hai luồng chỉ xuất sau khi tiến trình kết thúc
Đáp án đúng: B

Mã thoát (exit code) thường phản ánh thông tin nào?
A. Số luồng được bộ lập lịch chạy trong tiến trình
B. Kết quả kết thúc do tiến trình báo về bên gọi
C. Thời gian CPU tích lũy lúc chương trình kết thúc
D. Số byte của tệp thực thi đã được nạp vào RAM
Đáp án đúng: B

Biến môi trường khi khởi chạy tiến trình thường cung cấp gì?
A. Cấu hình dạng cặp tên và giá trị cho tiến trình
B. Chuỗi lệnh điều khiển CPU của kernel
C. Mã máy mà tiến trình sẽ dùng để thực thi
D. Bố cục bộ nhớ vật lý của cả hệ thống
Đáp án đúng: A

Một đường dẫn tương đối thường được diễn giải theo đâu khi tiến trình mở tệp?
A. Thư mục làm việc hiện tại của tiến trình
B. Thư mục cài đặt hệ điều hành trên máy
C. Thư mục chứa tệp thực thi đã được nạp
D. Thư mục chứa mã nguồn của chương trình
Đáp án đúng: A

Liên kết động khác liên kết tĩnh ở điểm nào?
A. Mã thư viện luôn được chép vào tệp thực thi cuối
B. Tệp thực thi phải biên dịch lại mỗi lần khởi chạy
C. Bộ nạp chương trình bỏ qua mọi phụ thuộc lúc chạy
D. Thư viện có thể được nạp và giải quyết tham chiếu lúc chạy
Đáp án đúng: D

Nếu thiếu thư viện dùng để liên kết động, điều gì có thể xảy ra?
A. Chương trình không thể nạp vì thiếu phụ thuộc
B. Heap tự mở rộng để thay thế thư viện bị thiếu
C. Bộ lập lịch từ chối chạy các tiến trình khác
D. Hệ điều hành biên dịch lại thư viện từ mã nguồn
Đáp án đúng: A

Một luồng bị chặn khi chờ I/O đồng bộ thường làm gì?
A. Luồng kết thúc ngay nếu chưa có dữ liệu đầu vào
B. Luồng tiếp tục dùng CPU để xử lý tác vụ khác
C. Luồng chờ thao tác hoàn tất rồi mới tiếp tục
D. Luồng được cấp thêm RAM khi dữ liệu chưa sẵn
Đáp án đúng: C

Với I/O không chặn, lời gọi đọc khi chưa có dữ liệu thường cho kết quả gì?
A. Trả về ngay với báo hiệu chưa sẵn sàng
B. Tạo một luồng mới để xử lý lần đọc tiếp theo
C. Chuyển lời gọi thành I/O đồng bộ ở tầng kernel
D. Đợi cho tới khi dữ liệu đến rồi mới trả về
Đáp án đúng: A

I/O bất đồng bộ thường khác I/O đồng bộ ở đâu?
A. Yêu cầu luôn phải có một luồng riêng để xử lý
B. Yêu cầu được bắt đầu và nhận kết quả qua thông báo sau
C. Yêu cầu được thực hiện mà không qua hệ điều hành
D. Yêu cầu chỉ hoàn tất sau khi tiến trình đã thoát
Đáp án đúng: B

Một tiến trình thường truy cập tệp theo quyền nào?
A. Quyền của danh tính và ngữ cảnh bảo mật đang chạy
B. Quyền của tiến trình khác đang giữ cùng tệp dữ liệu
C. Quyền cao nhất được kernel hỗ trợ trên hệ thống
D. Quyền của tác giả đã tạo ra mã nguồn chương trình
Đáp án đúng: A

Khi tiến trình kết thúc, việc nào thường do hệ điều hành đảm nhiệm?
A. Thu hồi bộ nhớ và tài nguyên còn giữ
B. Hoàn tác mọi thay đổi đã ghi xuống các tệp dữ liệu
C. Hủy mọi giao dịch đã được hệ thống khác xác nhận
D. Xóa mọi bản ghi ứng dụng đã gửi tới máy chủ khác
Đáp án đúng: A

Tại sao dùng timeout khi chương trình gọi dịch vụ bên ngoài?
A. Bảo đảm phản hồi có đúng định dạng dữ liệu yêu cầu
B. Giới hạn thời gian đợi khi dịch vụ không đáp
C. Tự tăng tốc xử lý ở máy ngoài nhờ ưu tiên CPU
D. Loại bỏ nhu cầu thử lại khi có sự cố đường truyền
Đáp án đúng: B

Khi tác vụ chạy trong môi trường sandbox, giới hạn thường áp dụng lên gì?
A. Định dạng của các tệp nguồn ứng dụng được dùng
B. Tốc độ biên dịch chương trình trước khi triển khai
C. Quyền truy cập tài nguyên và hành động của tác vụ
D. Thuật toán chia thời gian CPU của cả hệ điều hành
Đáp án đúng: C

JIT compilation mô tả cách tạo mã máy nào?
A. Dịch một phần chương trình sang mã máy lúc đang chạy
B. Biên dịch toàn bộ mã trước khi phân phối ứng dụng
C. Kết nối các thư viện đã được biên dịch sẵn
D. Thực thi lệnh trung gian mà không sinh mã máy
Đáp án đúng: A

Runtime dựa trên virtual machine có thể đảm nhiệm vai trò nào?
A. Tạo phân vùng đĩa riêng cho từng tiến trình chạy
B. Phân phối xung nhịp CPU cho các lõi xử lý vật lý
C. Thực thi mã trung gian và quản lý ngữ cảnh chạy
D. Thay kernel điều khiển trực tiếp thiết bị hệ thống
Đáp án đúng: C

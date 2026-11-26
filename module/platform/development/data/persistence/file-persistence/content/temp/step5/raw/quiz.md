Câu 1: Trong Java NIO, kiểu nào biểu diễn vị trí tệp độc lập với nội dung?
A. FileChannel dùng để biểu diễn đường dẫn trong hệ thống file
B. ByteBuffer dùng để biểu diễn đường dẫn trong hệ thống file
C. Charset dùng để biểu diễn đường dẫn trong hệ thống file
D. Path dùng để biểu diễn đường dẫn trong hệ thống file
Đáp án đúng: D

Câu 2: Khi cần tạo cả các thư mục cha còn thiếu, API Java nào phù hợp?
A. Files.createDirectory(path) để tạo mọi thư mục cha
B. Files.createDirectories(path) để tạo theo cây thư mục
C. Files.newOutputStream(path) để tạo các thư mục cha
D. Files.createTempFile(path) để tạo mọi thư mục cha
Đáp án đúng: B

Câu 3: Muốn ghi chuỗi tiếng Việt xuống file có thể đọc ổn định, nên dùng gì?
A. Dùng charset mặc định từ mỗi tiến trình Java khác nhau
B. Mã hóa với charset của terminal bất kể file metadata
C. Đổi mọi ký tự không ASCII thành dấu hỏi trước khi ghi
D. Chỉ định UTF-8 nhất quán cho thao tác ghi và đọc
Đáp án đúng: D

Câu 4: Trong định dạng bản ghi theo dòng, trường có newline cần xử lý thế nào?
A. Xóa newline trên dữ liệu để bộ đọc không phải kiểm tra
B. Thêm newline tự do rồi coi mỗi dòng là một bản ghi
C. Escape hoặc đóng gói theo quy ước có thể đọc ngược
D. Bỏ trường có newline khỏi bản ghi để giữ định dạng
Đáp án đúng: C

Câu 5: Khi dùng Files.newOutputStream với CREATE_NEW, ý nghĩa chính là gì?
A. Mở file đích cũ và nối thêm dữ liệu vào cuối file
B. Mở file đích cũ và thay nội dung hiện tại bằng dữ liệu
C. Tạo file nếu thiếu và luôn đồng bộ xuống thiết bị
D. Lỗi nếu file đích đã tồn tại tại thời điểm tạo
Đáp án đúng: D

Câu 6: Vì sao nên ghi bản mới vào file tạm rồi mới publish file chính?
A. Giúp mọi thao tác ghi file trở thành giao dịch đa file
B. Tránh người đọc thấy file chính đang ghi dở
C. Giúp tự phục hồi toàn bộ dữ liệu dù không có backup
D. Giúp hệ thống xác minh checksum mà không đọc file
Đáp án đúng: B

Câu 7: Files.move với ATOMIC_MOVE trong Java có giới hạn nào?
A. Luôn hoạt động xuyên filesystem mà không cần fallback
B. Luôn đồng bộ dữ liệu file vào thiết bị lưu trữ vật lý
C. Có thể không được filesystem hỗ trợ và phải xử lý lỗi
D. Luôn tự động khóa file nguồn ở mọi hệ điều hành
Đáp án đúng: C

Câu 8: Để tăng khả năng rename atomically, file tạm nên đặt ở đâu?
A. Trên ổ đĩa mạng khác để tách thao tác ghi chính
B. Cùng filesystem với file đích, thường cùng thư mục
C. Trong thư mục hệ thống bất kỳ, không cần kiểm tra
D. Trong bộ nhớ heap để rename không cần I/O
Đáp án đúng: B

Câu 9: Trong Java, FileChannel.force(true) được dùng để làm gì?
A. Yêu cầu tiến trình khác nhả mọi file lock đang giữ
B. Yêu cầu chuyển file sang đường dẫn mới bằng thao tác atomic
C. Yêu cầu tự phục hồi bản ghi lỗi bằng checksum có sẵn
D. Yêu cầu đẩy nội dung và metadata file xuống thiết bị
Đáp án đúng: D

Câu 10: Sau khi rename file tạm thành file chính, độ bền khi mất điện còn phụ thuộc gì?
A. Việc gọi System.gc() để hủy mọi bộ đệm Java còn lại
B. Việc sắp xếp tên file theo thứ tự chữ cái trước khi đóng
C. Việc đồng bộ metadata thư mục khi môi trường hỗ trợ
D. Việc tăng độ ưu tiên của thread xử lý thao tác rename
Đáp án đúng: C

Câu 11: Sự khác nhau giữa close() và đảm bảo dữ liệu bền vững trên đĩa là gì?
A. Đóng tài nguyên luôn tương đương với sync toàn bộ thiết bị
B. Đóng tài nguyên không mặc nhiên bảo đảm flush xuống đĩa
C. Đóng tài nguyên khiến hệ thống tự tạo một bản backup
D. Đóng tài nguyên tự đồng bộ cả thư mục chứa file trên đĩa
Đáp án đúng: B

Câu 12: Vì sao phải kiểm tra đường dẫn file do người dùng cung cấp?
A. Để tránh mọi file có phần mở rộng khác .txt được lưu
B. Để tránh mọi tên file có dấu cách trong đường dẫn
C. Để tránh path traversal vượt khỏi thư mục được phép
D. Để tránh mọi file có dung lượng lớn hơn bộ nhớ heap
Đáp án đúng: C

Câu 13: Vì sao chỉ gọi normalize() có thể chưa đủ để chống traversal?
A. Symlink vẫn có thể trỏ ra ngoài cây thư mục tin cậy
B. Normalize() tự mở file nên gây xung đột lock trên máy
C. Normalize() tự mã hóa đường dẫn bằng charset hệ thống
D. Normalize() tự xóa file gốc khi gặp ký tự phân cách
Đáp án đúng: A

Câu 14: Khi nhiều tiến trình Java cùng ghi một file, cần cơ chế nào?
A. Chỉ dùng synchronized trên một object ở mỗi tiến trình
B. Chỉ đặt volatile cho biến chứa Path ở mỗi tiến trình
C. Phối hợp file lock hoặc single-writer theo thiết kế
D. Chỉ tăng kích thước buffer để các lần ghi không trùng
Đáp án đúng: C

Câu 15: Khi dùng FileChannel.lock() xuyên tiến trình, điều gì phải lưu ý?
A. Lock là giao dịch ACID cho mọi file cùng thư mục
B. Ngữ nghĩa lock tùy hệ điều hành và filesystem
C. Lock luôn áp dụng cho mọi reader mà không cần phối hợp
D. Lock tự xóa mọi file tạm của tiến trình bị crash
Đáp án đúng: B

Câu 16: Để phát hiện bản ghi bị ghi dở khi chương trình crash giữa chừng, nên dùng gì?
A. Tên trường dữ liệu đặt ngắn để giảm số byte phải ghi
B. Một ký tự phân tách bất kỳ không có quy tắc kiểm tra
C. Độ dài bản ghi và checksum hoặc dấu kết thúc hợp lệ
D. Giảm số lần gọi flush để loại bỏ mọi bản ghi dở
Đáp án đúng: C

Câu 17: Khi đọc file log append-only sau crash, xử lý phần đuôi hỏng ra sao?
A. Chấp nhận mọi byte cuối cùng làm một bản ghi hoàn chỉnh
B. Bỏ toàn bộ log cũ dù chỉ lỗi một bản ghi cuối
C. Tạo bản ghi mới từ nội dung hỏng mà không kiểm tra
D. Khôi phục tới bản ghi hợp lệ cuối cùng theo định dạng
Đáp án đúng: D

Câu 18: Mục đích của write-ahead log trước khi cập nhật file dữ liệu là gì?
A. Chỉ ghi log sau khi mọi file đã được cập nhật xong
B. Dùng log để tự nén dữ liệu mà không phải ghi file chính
C. Dùng log để tránh hoàn toàn mọi lần đồng bộ thiết bị
D. Ghi thay đổi đủ để phục hồi trước khi sửa dữ liệu chính
Đáp án đúng: D

Câu 19: Khi replay WAL nhiều lần sau sự cố, cần đảm bảo điều gì?
A. Mỗi lần replay phải cấp lại ID ngẫu nhiên cho bản ghi
B. Áp dụng thay đổi idempotent hoặc theo sequence/checkpoint
C. Mỗi lần replay phải tăng số dư thêm một lần mới
D. Mỗi lần replay phải thay thứ tự log để tránh trùng
Đáp án đúng: B

Câu 20: Nếu phải cập nhật nhất quán nhiều file, một lần rename có đủ không?
A. Cần giao thức commit vì rename chỉ xử lý được một file
B. Đủ vì một lần rename tự giao dịch mọi file trong thư mục
C. Đủ nếu các file đều có phần mở rộng giống nhau
D. Đủ nếu ghi các file theo thứ tự chữ cái tăng dần
Đáp án đúng: A

Câu 21: Với file nhị phân dùng chung giữa Java và hệ khác, phải quy định gì?
A. Thứ tự byte, độ dài trường và phiên bản định dạng
B. Thứ tự import Java, tên package và mức log của JVM
C. Thứ tự thread, kích thước heap và số core CPU
D. Thứ tự gọi constructor, tên getter và màu chữ
Đáp án đúng: A

Câu 22: Checksum giúp đánh giá đặc tính nào của dữ liệu lưu file?
A. Xác thực danh tính người ghi file trong mọi môi trường
B. Bảo đảm file luôn đúng schema mà không cần parse
C. Bảo đảm file không thể bị sửa sau lần ghi đầu tiên
D. Phát hiện thay đổi ngẫu nhiên nhưng không xác thực tác giả
Đáp án đúng: D

Câu 23: Khi đổi schema của bản ghi file, cách nào hỗ trợ đọc dữ liệu cũ?
A. Có version và đường nâng cấp/giải mã tương thích
B. Dùng class Java mới và bỏ trường version trong file
C. Chuyển mọi trường sang String không giới hạn độ dài
D. Đổi tên file cũ và yêu cầu người dùng nhập lại dữ liệu
Đáp án đúng: A

Câu 24: Nếu file backup được sao chép khi file chính đang thay đổi, nguy cơ nào có thật?
A. Backup sẽ tự động được filesystem biến thành snapshot atomic
B. Backup có thể chứa trạng thái không nhất quán giữa các bước
C. Backup sẽ tự động chặn mọi luồng ghi khác tới database
D. Backup sẽ luôn chứa đầy đủ bản ghi chưa commit của ứng dụng
Đáp án đúng: B

Câu 25: Khi thiết kế backup, phép kiểm thử quan trọng nhất là gì?
A. Thử restore và xác minh kết quả khôi phục
B. Đo kích thước backup và so với dung lượng file nguồn
C. Kiểm tra lịch chạy backup và phiên bản công cụ tạo file
D. Xác minh checksum bản backup mà chưa thử phục hồi
Đáp án đúng: A

Câu 26: Để bảo vệ dữ liệu nhạy cảm lưu bằng file, biện pháp nào phù hợp?
A. Đặt phần mở rộng lạ và ẩn tên file trong ứng dụng
B. Đổi tên thư mục lưu file và hạn chế đường dẫn công khai
C. Giới hạn quyền truy cập và mã hóa dữ liệu lưu file
D. Đưa file ra ổ đĩa khác mà không đổi chính sách quyền
Đáp án đúng: C

Câu 27: Nếu dung lượng đĩa hết lúc ghi file tạm, cách xử lý nào hợp lý?
A. Bắt lỗi, giữ file chính và dọn phần ghi tạm
B. Publish file tạm và đánh dấu đầu ra là đã hoàn thành
C. Đổi tên file chính rồi bổ sung nội dung thiếu trực tiếp
D. Coi file đã tồn tại là đã ghi đủ dữ liệu cần thiết
Đáp án đúng: A

Câu 28: Kiểm thử độ bền file nên mô phỏng những tình huống nào?
A. Lỗi ghi giữa chừng, crash trước rename và file bị hỏng
B. Đọc lặp nhiều lần các file nhỏ sau một lần ghi thành công
C. Đo tốc độ đọc tuần tự lúc không có tác vụ ghi song song
D. So sánh tên file trong thư mục sau các lần mở ứng dụng
Đáp án đúng: A

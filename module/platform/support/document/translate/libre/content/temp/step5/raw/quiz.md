Khi gọi dịch văn bản qua REST API, dữ liệu đầu vào cốt lõi là gì?
A. Chỉ mã ngôn ngữ và đường dẫn bản dịch
B. Chỉ loại MIME và mã hóa của tài liệu cần dịch
C. Nội dung nguồn và ngôn ngữ đích cần dịch
D. Chỉ tên engine dịch và mã ngôn ngữ nguồn
Đáp án đúng: C

Muốn giảm lỗi chọn sai ngôn ngữ nguồn khi tài liệu không rõ xuất xứ, nên làm gì?
A. Luôn chọn ngôn ngữ nguồn dựa trên tên file
B. Đoán ngôn ngữ chỉ qua bộ mã UTF-8 của tệp
C. Dùng ngôn ngữ đích làm nguồn cho mọi yêu cầu
D. Dò ngôn ngữ và kiểm tra kết quả trước khi dịch
Đáp án đúng: D

Ưu điểm thực tế của LibreTranslate tự quản đối với tài liệu nhạy cảm là gì?
A. Không còn phải quản lý quyền truy cập máy chủ
B. Mọi tài liệu được mã hóa dù không cấu hình TLS
C. Chất lượng dịch luôn cao hơn mọi dịch vụ khác
D. Kiểm soát nơi xử lý và chính sách lưu dữ liệu
Đáp án đúng: D

Dịch một tệp có tiêu đề, bảng và đoạn văn nên tổ chức xử lý thế nào?
A. Tách nội dung cần dịch rồi ghép lại đúng cấu trúc
B. Loại bỏ bố cục để chỉ còn đoạn văn thuần túy
C. Thay toàn bộ nội dung bảng bằng kết quả dò ngôn ngữ
D. Dịch trực tiếp mọi byte của tệp như chuỗi văn bản
Đáp án đúng: A

Khi dịch tài liệu HTML, cách nào giúp giữ khả năng hiển thị sau dịch?
A. Giữ thẻ HTML, chỉ dịch nội dung văn bản
B. Dịch toàn bộ tên thẻ và tên thuộc tính HTML
C. Thay mọi thẻ thành văn bản trước khi gửi dịch
D. Chỉ giữ CSS và bỏ nội dung nằm trong các thẻ
Đáp án đúng: A

Với Markdown có fenced code block, biện pháp nào bảo toàn mã nguồn?
A. Bỏ dấu Markdown để dịch toàn bộ như văn bản thuần
B. Bảo vệ khối code, chỉ dịch phần văn bản phù hợp
C. Dịch cả tên biến và cú pháp trong mọi khối code
D. Chuyển mọi khối code thành tiêu đề trước khi dịch
Đáp án đúng: B

Khi dịch nhiều đoạn lớn qua một dịch vụ, cách điều phối nào hợp lý?
A. Chạy tuần tự mọi câu mà không ghi nhận tiến độ
B. Gộp mọi tài liệu thành một chuỗi không đánh dấu
C. Chia lô và giới hạn số yêu cầu đồng thời
D. Gửi toàn bộ đoạn thành các request không giới hạn
Đáp án đúng: C

Khi máy chủ dịch báo quá tải tạm thời, client Java nên phản ứng ra sao?
A. Retry ngay liên tục cho đến khi máy chủ hồi phục
B. Retry có giới hạn với backoff và ghi nhận lỗi
C. Xem HTTP lỗi như bản dịch thành công và lưu
D. Tăng không giới hạn số kết nối để tăng throughput
Đáp án đúng: B

Bản dịch trả về HTTP thành công nhưng thiếu nội dung, cách xử lý nào phù hợp?
A. Kiểm tra payload và báo lỗi nếu thiếu dữ liệu
B. Thay nguyên văn nguồn nhưng ghi trạng thái đã dịch
C. Lưu chuỗi rỗng và coi đó là bản dịch hợp lệ
D. Tự đổi ngôn ngữ đích rồi gửi lại không kiểm tra
Đáp án đúng: A

Vì sao placeholder như `{customerName}` cần được bảo vệ khi dịch?
A. Để giữ nguyên biến nội suy trong bản dịch
B. Để engine đổi mọi tên biến sang ngôn ngữ đích
C. Để không cần kiểm tra kết quả dịch trước khi xuất
D. Để thuật toán tự đoán thông tin cá nhân của khách
Đáp án đúng: A

Kiểm soát chất lượng bản dịch tài liệu kỹ thuật cần chú trọng điều gì?
A. Chỉ kiểm số ký tự bằng đúng văn bản nguồn
B. Chỉ xác nhận engine trả lời trước thời hạn
C. Đổi tên file để người nhận tự kiểm tra chất lượng
D. So thuật ngữ, ngữ cảnh và cấu trúc với bản nguồn
Đáp án đúng: D

Trong Spring, khi gọi dịch vụ dịch từ xa, cấu hình nào tăng độ tin cậy?
A. Cố tạo client HTTP mới cho mỗi ký tự cần dịch
B. Timeout kết nối/đọc và xử lý HTTP lỗi rõ ràng
C. Giữ request chờ vô hạn để không bỏ kết quả
D. Bỏ log lỗi vì có thể tự retry ở tầng mạng
Đáp án đúng: B

Khi một máy chủ tự quản yêu cầu khóa API, cách quản lý nào thích hợp?
A. Ghi khóa đầy đủ trong log request để hỗ trợ
B. Lưu khóa trong secret config, không ghi vào source
C. Gửi khóa tới mọi client thông qua HTML tĩnh
D. Nhúng khóa vào tài liệu cần dịch để dễ kiểm tra
Đáp án đúng: B

Trước khi bắt đầu lô dịch nhiều ngôn ngữ, cần xác minh điều gì?
A. Tên file nguồn có cùng độ dài với bản đích
B. Tất cả câu có cùng số token trong tiếng Việt
C. Bộ nhớ máy khách luôn lớn hơn file nguồn
D. Cặp ngôn ngữ yêu cầu có được server hỗ trợ
Đáp án đúng: D

Khi nối lại lô dịch bị gián đoạn, cách lưu tiến độ nào hữu ích?
A. Bỏ kết quả các đoạn xong để bảo đảm tuần tự
B. Luôn dịch lại toàn bộ dữ liệu mà không kiểm tra
C. Gắn ID đoạn và trạng thái xử lý để tránh làm lại
D. Chỉ ghi tổng số file đã nhận, không lưu kết quả
Đáp án đúng: C

Sau dịch Markdown/HTML, kiểm thử tích hợp nên xác minh điều gì?
A. Mỗi request dịch phải tạo một tệp nhật ký riêng
B. Tên tất cả thẻ phải thay đổi theo ngôn ngữ đích
C. Giữ cấu trúc và đặt văn bản dịch đúng vị trí
D. Tất cả đoạn phải có cùng số từ như bản nguồn
Đáp án đúng: C

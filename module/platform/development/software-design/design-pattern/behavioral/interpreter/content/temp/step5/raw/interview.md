Bạn sẽ giải thích mục đích của mẫu Interpreter khi cần mô tả và thực thi một ngôn ngữ quy tắc nhỏ như thế nào?
Bạn sẽ xác định tình huống nào phù hợp với Interpreter thay vì viết trực tiếp nhiều điều kiện nghiệp vụ ra sao?
Bạn sẽ phân biệt câu lệnh trong ngôn ngữ miền nghiệp vụ với cấu trúc biểu thức được dùng để biểu diễn nó như thế nào?
Bạn sẽ xây dựng grammar đơn giản cho biểu thức số học có phép cộng, nhân và dấu ngoặc như thế nào?
Bạn sẽ giải thích vai trò của terminal expression và nonterminal expression trong một cây diễn giải ra sao?
Bạn sẽ thiết kế interface Expression để các nút trong AST có thể đánh giá theo cách nhất quán như thế nào?
Bạn sẽ biểu diễn hằng số, biến và phép cộng thành các lớp expression Java độc lập ra sao?
Bạn sẽ mô tả cách một biểu thức lồng nhau được đánh giá đệ quy từ nút gốc đến các nút con như thế nào?
Bạn sẽ phân biệt cây cú pháp trừu tượng với chuỗi token đầu vào và kết quả cuối cùng của evaluator ra sao?
Bạn sẽ thiết kế context chứa giá trị biến và các tham số cần thiết cho quá trình đánh giá như thế nào?
Bạn sẽ xác định dữ liệu nào nên thuộc context và dữ liệu nào nên là trạng thái riêng của từng nút expression ra sao?
Bạn sẽ kiểm soát việc một biểu thức làm thay đổi context và ảnh hưởng đến phép đánh giá khác như thế nào?
Bạn sẽ lựa chọn cách biểu diễn giá trị boolean, số và chuỗi khi một ngôn ngữ có nhiều kiểu dữ liệu ra sao?
Bạn sẽ xử lý tham chiếu đến một biến không tồn tại trong context bằng quy tắc lỗi nào?
Bạn sẽ tách quá trình phân tích cú pháp khỏi quá trình đánh giá để mỗi phần có thể được kiểm thử riêng như thế nào?
Bạn sẽ xây dựng tokenizer để nhận diện tên biến, toán tử, hằng số và dấu ngoặc trong một biểu thức ra sao?
Bạn sẽ phân biệt lỗi token không hợp lệ với lỗi cấu trúc grammar khi đọc dữ liệu đầu vào như thế nào?
Bạn sẽ thiết kế parser để tạo AST từ chuỗi biểu thức có nhiều cấp ưu tiên toán tử như thế nào?
Bạn sẽ xử lý tính kết hợp trái hoặc phải của toán tử khi tạo cây cú pháp ra sao?
Bạn sẽ phân biệt phương pháp phân tích đệ quy xuống với việc dùng thư viện parser cho một ngôn ngữ nhỏ như thế nào?
Bạn sẽ kiểm tra cú pháp của biểu thức mà không thực thi các thao tác nghiệp vụ bên trong ra sao?
Bạn sẽ thiết kế thông báo lỗi có vị trí ký tự hoặc token để người viết quy tắc sửa cú pháp dễ dàng như thế nào?
Bạn sẽ xác định khi nào cần bước kiểm tra kiểu dữ liệu trước khi evaluator chạy như thế nào?
Bạn sẽ xử lý phép so sánh giữa các giá trị khác kiểu mà không tự động chuyển đổi gây sai nghĩa nghiệp vụ ra sao?
Bạn sẽ thiết kế các phép toán AND và OR có cơ chế short-circuit mà vẫn bảo toàn ngữ nghĩa biểu thức như thế nào?
Bạn sẽ bổ sung phép phủ định và so sánh vào grammar mà không phá vỡ các biểu thức hợp lệ cũ ra sao?
Bạn sẽ thiết kế một quy tắc kiểm tra điều kiện giảm giá bằng cách kết hợp các biểu thức nhỏ như thế nào?
Bạn sẽ phân biệt ngữ nghĩa của ngôn ngữ biểu thức với cách parser sắp xếp các nút trong cây ra sao?
Bạn sẽ xử lý một biểu thức có nhiều dấu ngoặc và độ sâu lồng nhau lớn mà vẫn tránh tràn ngăn xếp như thế nào?
Bạn sẽ giới hạn độ dài chuỗi, số token và độ sâu AST khi nhận quy tắc từ nguồn không tin cậy ra sao?
Bạn sẽ xác định những phép toán hoặc hàm nào được phép xuất hiện trong ngôn ngữ để giảm nguy cơ thực thi ngoài ý muốn như thế nào?
Bạn sẽ thiết kế evaluator không cho phép gọi trực tiếp các API Java tùy ý từ biểu thức do người dùng nhập ra sao?
Bạn sẽ kiểm soát việc đọc dữ liệu nhạy cảm từ context để một quy tắc không truy cập vượt phạm vi được cấp phép như thế nào?
Bạn sẽ đặt giới hạn thời gian và tài nguyên để đánh giá những biểu thức rất lớn hoặc tốn nhiều phép tính như thế nào?
Bạn sẽ xử lý các phép toán sai như chia cho không hoặc vượt miền giá trị trong evaluator ra sao?
Bạn sẽ xác định yêu cầu về tính xác định khi cùng một AST và context phải luôn cho ra cùng kết quả như thế nào?
Bạn sẽ thiết kế các nút expression bất biến để một AST có thể được tái sử dụng giữa nhiều lần đánh giá ra sao?
Bạn sẽ cân nhắc cache AST sau khi parse nhiều lần cùng một quy tắc và chính sách loại bỏ cache như thế nào?
Bạn sẽ phân tích chi phí tạo nhiều đối tượng nút và duyệt AST đối với hiệu năng khi số lượng quy tắc tăng ra sao?
Bạn sẽ quyết định khi nào cần chuyển từ Interpreter sang cách biên dịch biểu thức hoặc dùng engine chuyên dụng như thế nào?
Bạn sẽ kiểm thử riêng từng terminal expression với hằng số, biến hợp lệ và biến không tồn tại ra sao?
Bạn sẽ thiết kế kiểm thử cho nonterminal expression khi có nhiều lớp lồng nhau và độ ưu tiên toán tử như thế nào?
Bạn sẽ dùng các biểu thức tương đương về mặt toán học để kiểm tra tính nhất quán của evaluator ra sao?
Bạn sẽ xác minh parser báo lỗi đúng khi có dấu ngoặc thiếu, toán tử liên tiếp hoặc ký tự không được hỗ trợ như thế nào?
Bạn sẽ thiết kế kiểm thử bảo mật với biểu thức cố ý rất dài hoặc có cấu trúc bất thường như thế nào?
Bạn sẽ tổ chức bộ quy tắc ví dụ làm tài liệu về ngữ nghĩa của ngôn ngữ và tránh khác biệt giữa tài liệu và thực thi ra sao?
Bạn sẽ ghi nhận lỗi đánh giá và cây biểu thức liên quan để chẩn đoán sự cố mà không làm lộ giá trị nhạy cảm như thế nào?
Bạn sẽ quản lý phiên bản grammar và thay đổi ý nghĩa toán tử khi các quy tắc cũ vẫn đang được sử dụng như thế nào?
Bạn sẽ so sánh mẫu Interpreter với Composite hoặc Visitor khi thiết kế và duyệt cây biểu thức như thế nào?
Bạn sẽ xử lý tình huống một quy tắc nghiệp vụ vừa được chỉnh sửa khiến evaluator trả kết quả khác dù cú pháp vẫn hợp lệ như thế nào?

Error Prone tích hợp vào quá trình biên dịch Java để phát hiện bug pattern theo cơ chế nào?
Error Prone khác các công cụ kiểm tra phong cách như Checkstyle ở mục tiêu và thời điểm phát hiện lỗi ra sao?
Error Prone khai thác AST, symbol và thông tin kiểu của javac để phân tích một lời gọi phương thức như thế nào?
Việc chạy checker ngay trong compilation có những ưu điểm và giới hạn nào so với quét bytecode sau build?
Bạn sẽ giải thích vòng đời của một checker từ lúc javac phân tích mã đến khi xuất diagnostic ra sao?
Bạn phân biệt mức ERROR, WARNING và việc tắt một checker trong Error Prone như thế nào?
Bạn sẽ lựa chọn các bug pattern cần bật trong dự án dựa trên rủi ro và độ chính xác ra sao?
Bạn sử dụng cờ cấu hình dạng -Xep để thay đổi mức nghiêm trọng của một checker như thế nào?
Khi một checker làm build thất bại, bạn xác định tên quy tắc và vị trí mã gây lỗi ra sao?
Bạn sẽ ghi lại lý do và phạm vi khi cần tắt tạm một checker đang gây cảnh báo sai như thế nào?
Bạn sử dụng @SuppressWarnings để miễn kiểm tra cho một trường hợp cụ thể theo nguyên tắc nào?
Bạn sẽ kiểm soát các suppression tồn tại lâu ngày để tránh che giấu lỗi mới ra sao?
Bạn cấu hình Maven Compiler Plugin để chạy Error Prone trong quá trình biên dịch như thế nào?
Khi dùng phiên bản JDK khác nhau, bạn kiểm tra tương thích giữa javac, Error Prone và plugin Maven ra sao?
Bạn sẽ tích hợp Error Prone vào Gradle thông qua plugin và task JavaCompile như thế nào?
Khi dự án dùng Java toolchain, bạn đảm bảo Error Prone chạy bằng đúng compiler như thế nào?
Bạn thiết lập pipeline CI để phát hiện bug pattern trong mỗi pull request và trình bày lỗi ra sao?
Khi kết quả Error Prone trên máy phát triển khác CI, bạn kiểm tra cờ compiler và dependency nào?
Bạn đánh giá ảnh hưởng của annotation processor đến quá trình chạy Error Prone như thế nào?
Trong dự án có Lombok hoặc mã sinh tự động, bạn điều tra xung đột phân tích và cách xử lý ra sao?
Bạn sẽ đọc thông điệp diagnostic để phân biệt lỗi biên dịch gốc với lỗi do checker phát hiện thế nào?
Một bug pattern về bỏ qua giá trị trả về có thể chỉ ra sai sót logic Java như thế nào?
Bạn sẽ đánh giá cảnh báo so sánh hai kiểu dữ liệu không tương thích trong equals bằng cách nào?
Khi checker nghi ngờ thao tác với null, bạn xác minh đường chạy có thể gây lỗi thực tế ra sao?
Bạn sẽ sử dụng checker để nhận diện thao tác trên collection hoặc Optional có nguy cơ lỗi như thế nào?
Các annotation như @CheckReturnValue và @CanIgnoreReturnValue có thể làm rõ hợp đồng API ra sao?
Bạn đánh giá việc áp dụng annotation liên quan đến đóng tài nguyên và sử dụng kết quả phương thức như thế nào?
Khi một checker đề xuất sửa mã tự động, bạn đánh giá tính an toàn của thay đổi bằng tiêu chí nào?
Bạn sẽ tạo bản vá bằng cơ chế patch của Error Prone và rà soát phần diff như thế nào?
Nếu bản vá tự động va chạm với quy tắc format hoặc convention khác, bạn sẽ xử lý ra sao?
Bạn sẽ quyết định khi nào dùng gợi ý sửa tự động và khi nào cần refactor thủ công như thế nào?
Một checker tùy biến của Error Prone cần những thành phần chính nào để nhận diện một bug pattern?
Bạn thiết kế lớp kế thừa BugChecker và chọn interface matcher phù hợp với node AST như thế nào?
Bạn sẽ dùng thông tin symbol hoặc type để checker tránh báo nhầm những phương thức trùng tên ra sao?
Khi một API có overload hoặc generic type, bạn thiết kế điều kiện phát hiện chính xác thế nào?
Bạn sẽ dùng @BugPattern để mô tả mức độ nghiêm trọng và thông điệp của checker tự viết ra sao?
Bạn tạo diagnostic với SuggestedFix để gợi ý sửa cú pháp Java như thế nào?
Bạn kiểm thử checker tùy biến bằng CompilationTestHelper với các ví dụ có và không có lỗi ra sao?
Bạn sẽ dùng BugCheckerRefactoringTestHelper để xác nhận output sau khi áp dụng SuggestedFix như thế nào?
Những trường hợp biên như lambda, method reference và anonymous class cần được kiểm thử ra sao?
Khi checker tự viết báo sai vị trí source, bạn truy vết AST node và phạm vi token như thế nào?
Bạn đánh giá nguy cơ false positive của checker khi mã dùng reflection hoặc cơ chế runtime linh hoạt ra sao?
Bạn sẽ giảm chi phí phân tích của checker tùy biến trong codebase lớn mà vẫn giữ độ chính xác thế nào?
Khi nâng cấp Error Prone làm xuất hiện diagnostic mới, bạn lập kế hoạch tiếp nhận và sửa dần ra sao?
Bạn lựa chọn baseline và ngưỡng fail CI thế nào khi dự án còn nhiều cảnh báo cũ?
Bạn sẽ đối chiếu kết quả Error Prone với SpotBugs và PMD để tránh yêu cầu sửa trùng lặp ra sao?
Khi một bug pattern có mức cảnh báo cao nhưng tái hiện khó, bạn thu thập bằng chứng kỹ thuật như thế nào?
Bạn quản lý phiên bản và phân phối checker tùy biến cho các module hoặc repository Java ra sao?
Bạn đo hiệu quả sử dụng Error Prone bằng số lỗi phát hiện sớm, thời gian sửa và tỉ lệ cảnh báo sai như thế nào?
Khi một bản phát hành bị chặn do checker mới, bạn sẽ quyết định sửa lỗi, điều chỉnh quy tắc hay hoãn triển khai ra sao?

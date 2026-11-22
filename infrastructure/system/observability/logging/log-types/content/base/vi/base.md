# Observability Logging: Log Types

Không phải dòng log nào cũng phục vụ cùng một mục đích. Log ứng dụng phản ánh các bước xử lý; log hệ thống cho biết tình trạng môi trường chạy; access log ghi nhận yêu cầu; còn log lỗi, bảo mật, kiểm toán và nghiệp vụ giúp nhìn sự cố từ những góc độ khác nhau. Module này giúp bạn nhận diện đúng loại log trước khi bắt đầu phân tích.

Lộ trình bắt đầu từ cách phân loại log và phân biệt **loại log** với **log level** hoặc định dạng. Tiếp đó, bạn lần lượt tìm hiểu sáu nhóm thông dụng: Application, System/Infrastructure, Access/Request, Error/Diagnostic, Security/Audit và Business/Event. Mỗi nhóm đi kèm mục đích, trường thông tin đặc trưng và tình huống sử dụng.

Nội dung phù hợp với lập trình viên và người vận hành đang học observability. Sau khi hoàn thành, bạn có thể chọn nguồn log phù hợp cho một câu hỏi vận hành, đối chiếu nhiều nhóm log để tìm nguyên nhân sự cố và tránh đưa thông tin nhạy cảm vào nhật ký.
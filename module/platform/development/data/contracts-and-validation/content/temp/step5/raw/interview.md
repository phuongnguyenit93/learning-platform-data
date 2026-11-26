Một data contract cần xác định những cam kết nào giữa bên tạo dữ liệu và bên tiêu thụ dữ liệu?
Bạn phân biệt ràng buộc cấu trúc, kiểu dữ liệu, ngữ nghĩa và chất lượng trong cùng một contract như thế nào?
Bạn sẽ nhận diện producer, consumer, owner và phạm vi áp dụng trước khi xây dựng data contract ra sao?
Khi hai hệ thống cùng dùng kiểu string nhưng hiểu khác nhau về một trường, contract nên mô tả điều gì?
Bạn sẽ diễn đạt ý nghĩa nghiệp vụ, đơn vị đo và miền giá trị của một thuộc tính dữ liệu như thế nào?
Bạn phân biệt trường vắng mặt, giá trị null và chuỗi rỗng trong hợp đồng JSON ra sao?
Khi một API cho phép dữ liệu chưa biết, bạn quyết định cho phép hay từ chối thuộc tính ngoài schema như thế nào?
Bạn sử dụng type, required và properties của JSON Schema để mô tả một payload như thế nào?
Những trường hợp nào khiến việc kiểm tra type trong JSON Schema vẫn chưa bảo đảm dữ liệu hợp lệ về nghiệp vụ?
Bạn lựa chọn minimum, maximum, minLength, pattern và enum theo tiêu chí nào?
Bạn sử dụng format trong JSON Schema thế nào và đánh giá sự khác biệt giữa annotation và validation thực tế ra sao?
Bạn sẽ viết ràng buộc cho mảng đối tượng, số lượng phần tử và tính duy nhất bằng JSON Schema như thế nào?
Bạn dùng $ref và $defs để tái sử dụng schema mà vẫn tránh phụ thuộc vòng khó quản lý ra sao?
Khi dữ liệu có nhiều biến thể hợp lệ, bạn lựa chọn oneOf, anyOf hoặc allOf như thế nào?
Bạn dùng if, then và else để diễn đạt trường chỉ bắt buộc trong một điều kiện nghiệp vụ ra sao?
Bạn sẽ kiểm tra một schema JSON qua tập dữ liệu hợp lệ và không hợp lệ bằng phương pháp nào?
Bạn thiết kế thông báo lỗi schema để chỉ rõ vị trí, giá trị và quy tắc vi phạm mà không lộ dữ liệu nhạy cảm ra sao?
Bạn sẽ phân biệt validation tại ranh giới API với kiểm tra bất biến trong domain như thế nào?
Các annotation @NotNull, @NotBlank và @NotEmpty trong Jakarta Validation khác nhau ở tình huống nào?
Bạn sẽ kết hợp @Size, @Min, @Max và @Pattern để kiểm tra DTO Java như thế nào?
Khi một field chứa danh sách đối tượng lồng nhau, bạn sử dụng @Valid và constraint trên phần tử ra sao?
Bạn dùng validation groups để áp dụng quy tắc khác nhau cho thao tác tạo mới và cập nhật như thế nào?
Bạn thiết kế custom ConstraintValidator để kiểm tra một quy tắc nghiệp vụ chưa có annotation sẵn ra sao?
Khi một quy tắc phụ thuộc hai field như ngày bắt đầu và ngày kết thúc, bạn lựa chọn validation cấp class như thế nào?
Bạn giải thích cách thông báo lỗi Jakarta Validation được tùy biến và bản địa hóa ra sao?
Bạn xử lý danh sách constraint violation tại API để trả mã lỗi ổn định cho client như thế nào?
Khi nhận dữ liệu từ bên ngoài, bạn phối hợp deserialize, normalize và validate theo thứ tự nào?
Bạn xác định ở đâu cần kiểm tra format, ở đâu cần kiểm tra trạng thái hiện hành trong database như thế nào?
Khi yêu cầu nghiệp vụ thay đổi, bạn phân biệt sửa data contract với sửa rule engine hoặc business service ra sao?
Bạn sẽ định nghĩa backward compatibility và forward compatibility cho thông điệp JSON như thế nào?
Việc thêm một trường optional có thể làm hỏng consumer cũ trong những điều kiện nào?
Bạn xử lý việc đổi tên, đổi kiểu hoặc xóa một trường mà vẫn duy trì tương thích phiên bản ra sao?
Khi một trường mới có default value, bạn đánh giá tác động tới dữ liệu lịch sử và consumer cũ như thế nào?
Bạn sẽ lên kế hoạch deprecate một field và chuyển consumer sang field thay thế như thế nào?
Khi một API có nhiều phiên bản schema, bạn quyết định thời điểm tăng major version dựa trên tiêu chí nào?
Bạn thiết kế contract test giữa consumer và provider cho một endpoint REST như thế nào?
Consumer-driven contract testing có thể phát hiện thay đổi phá vỡ kỳ vọng của client ra sao?
Khi producer có nhiều consumer với yêu cầu khác nhau, bạn quản lý các bộ contract test như thế nào?
Bạn kiểm thử tính tương thích cho event bất đồng bộ khi producer và consumer nâng cấp ở những thời điểm khác nhau ra sao?
Bạn mô tả các quy tắc về ordering, duplicate delivery và idempotency trong contract của message như thế nào?
Khi schema message được đăng ký tập trung, bạn lựa chọn quy tắc tương thích và cách kiểm soát phiên bản ra sao?
Bạn xây dựng data contract giữa hai bước của một pipeline ETL hoặc streaming như thế nào?
Khi pipeline nhận bản ghi không đạt contract, bạn quyết định reject, quarantine hay xử lý bù theo tiêu chí nào?
Bạn sẽ xác định ngưỡng chất lượng như tỷ lệ giá trị null hoặc độ trễ dữ liệu trong contract ra sao?
Bạn đưa kiểm tra schema và contract test vào CI để chặn thay đổi không tương thích như thế nào?
Bạn thiết kế quy trình phê duyệt thay đổi contract giữa các nhóm sở hữu dữ liệu ra sao?
Khi contract trong tài liệu khác với payload production, bạn thu thập bằng chứng và xử lý sai lệch thế nào?
Bạn kiểm tra contract để ngăn lộ thông tin định danh hoặc dữ liệu nhạy cảm trong response ra sao?
Bạn sẽ thiết kế bộ test biên cho dữ liệu số, thời gian và Unicode để phát hiện lỗi validation nào?
Khi một consumer báo lỗi sau khi producer triển khai schema mới, bạn truy tìm điểm phá vỡ và lập kế hoạch khôi phục như thế nào?

Bạn sẽ thu thập nhu cầu của các consumer trước khi định nghĩa hợp đồng API để tránh thiết kế theo cấu trúc database như thế nào?
Bạn sẽ xác định ranh giới tài nguyên và quan hệ giữa chúng khi thiết kế API cho hệ thống quản lý đơn hàng ra sao?
Bạn sẽ lựa chọn tên tài nguyên, cấu trúc URL và tham số định danh để hợp đồng dễ hiểu và ổn định như thế nào?
Bạn sẽ phân biệt thiết kế API hướng tài nguyên với API hướng thao tác dựa trên yêu cầu nghiệp vụ ra sao?
Bạn sẽ quyết định khi nào dùng GET, POST, PUT, PATCH hoặc DELETE theo ngữ nghĩa và tính idempotent như thế nào?
Bạn sẽ thiết kế request cho thao tác tạo tài nguyên để tránh client gửi các trường chỉ do server quản lý ra sao?
Bạn sẽ xác định những trường nào bắt buộc, tùy chọn hoặc chỉ đọc trong request và response như thế nào?
Bạn sẽ phân biệt ý nghĩa của trường vắng mặt, giá trị null và giá trị rỗng trong hợp đồng cập nhật một phần ra sao?
Bạn sẽ lựa chọn định dạng dữ liệu và kiểu số cho số tiền, tỷ lệ và mã định danh mà không làm mất ý nghĩa ra sao?
Bạn sẽ thiết kế quy tắc biểu diễn ngày giờ và múi giờ để các consumer ở nhiều khu vực hiểu thống nhất như thế nào?
Bạn sẽ định nghĩa schema cho đối tượng lồng nhau và collection để client biết trường hợp rỗng hoặc không có dữ liệu ra sao?
Bạn sẽ sử dụng JSON Schema để mô tả kiểu dữ liệu, giới hạn giá trị và ràng buộc cấu trúc của payload như thế nào?
Bạn sẽ giải thích giới hạn của kiểm tra schema khi nghiệp vụ cần các ràng buộc liên trường hoặc phụ thuộc trạng thái như thế nào?
Bạn sẽ dùng OpenAPI để mô tả endpoint, request, response, tham số và ví dụ mà không mâu thuẫn với triển khai ra sao?
Bạn sẽ xác định cách quản lý file đặc tả OpenAPI cùng phiên bản mã và phát hiện sai lệch hợp đồng trong CI như thế nào?
Bạn sẽ tạo ví dụ request/response đủ đại diện để consumer hiểu cả tình huống thành công và thất bại như thế nào?
Bạn sẽ lựa chọn status code cho thao tác tạo, đọc, cập nhật và xóa dựa trên kết quả thực tế ra sao?
Bạn sẽ định nghĩa định dạng lỗi thống nhất gồm mã lỗi máy đọc được, thông điệp và thông tin liên quan như thế nào?
Bạn sẽ phân biệt lỗi xác thực, thiếu quyền, dữ liệu sai, xung đột trạng thái và lỗi hạ tầng trong hợp đồng ra sao?
Bạn sẽ thiết kế trường hợp client gửi request lặp do timeout để tránh tạo hai giao dịch không mong muốn như thế nào?
Bạn sẽ xác định khi nào cần idempotency key và quy tắc lưu, hết hạn và tái sử dụng khóa ra sao?
Bạn sẽ thiết kế phân trang với cursor hoặc offset và giải thích các đánh đổi về tính ổn định dữ liệu như thế nào?
Bạn sẽ định nghĩa bộ lọc và thứ tự sắp xếp sao cho việc phân trang không làm mất hoặc lặp bản ghi như thế nào?
Bạn sẽ chọn giới hạn kích thước request, số phần tử trả về và cách xử lý vượt giới hạn để bảo vệ dịch vụ ra sao?
Bạn sẽ thiết kế các header về Content-Type, Accept và content negotiation để hai phía diễn giải payload đúng như thế nào?
Bạn sẽ kiểm soát cache và các request có điều kiện bằng ETag hoặc phiên bản tài nguyên trong hợp đồng như thế nào?
Bạn sẽ mô tả quy tắc xác thực và phạm vi quyền của từng thao tác mà không ràng buộc hợp đồng vào token thử nghiệm ra sao?
Bạn sẽ ngăn lộ thông tin nhạy cảm trong schema, ví dụ response và lỗi mà vẫn giữ đủ dữ liệu cho consumer như thế nào?
Bạn sẽ xác định thông tin nào cần được che giấu khi người dùng truy cập tài nguyên không thuộc quyền của họ như thế nào?
Bạn sẽ định nghĩa giới hạn tốc độ, tín hiệu 429 và gợi ý retry để client xử lý quá tải an toàn ra sao?
Bạn sẽ thiết kế thao tác bất đồng bộ có trạng thái công việc và cơ chế theo dõi tiến trình thay vì giữ kết nối lâu như thế nào?
Bạn sẽ cân nhắc hợp đồng bulk API khi consumer cần gửi nhiều thay đổi và một phần tác vụ có thể thất bại ra sao?
Bạn sẽ xác định thế nào là thay đổi tương thích ngược khi thêm trường tùy chọn vào response hoặc request như thế nào?
Bạn sẽ đánh giá tác động của việc đổi tên trường, đổi kiểu dữ liệu hoặc thêm trường request bắt buộc lên consumer hiện tại ra sao?
Bạn sẽ lựa chọn cơ chế versioning trong đường dẫn, header hoặc media type dựa trên khả năng vận hành của hệ thống như thế nào?
Bạn sẽ lập kế hoạch ngừng hỗ trợ một trường cũ để các phiên bản consumer đang chạy còn thời gian chuyển đổi ra sao?
Bạn sẽ xác định tiêu chí khi nào cần phiên bản API mới thay vì mở rộng tương thích phiên bản hiện tại như thế nào?
Bạn sẽ thiết kế hợp đồng RPC cho phương thức, kiểu request/response và lỗi khác gì so với API tài nguyên như thế nào?
Bạn sẽ kiểm soát khả năng tiến hóa schema của hợp đồng RPC khi client và server được triển khai độc lập ra sao?
Bạn sẽ mô tả message contract gồm loại sự kiện, payload, định danh, thời gian và phiên bản như thế nào?
Bạn sẽ xác định quy tắc xử lý thứ tự, gửi trùng và giao hàng ít nhất một lần trong hợp đồng message ra sao?
Bạn sẽ phân biệt một event mô tả sự việc đã xảy ra với một command yêu cầu hành động khi thiết kế message như thế nào?
Bạn sẽ dùng contract testing do consumer dẫn dắt để kiểm chứng provider còn đáp ứng những tương tác quan trọng như thế nào?
Bạn sẽ lựa chọn kiểm thử schema, contract test và end-to-end test theo những rủi ro tích hợp khác nhau ra sao?
Bạn sẽ tổ chức stub hoặc mock server từ hợp đồng để consumer phát triển sớm mà vẫn phát hiện sai lệch với provider ra sao?
Bạn sẽ quản lý trạng thái và dữ liệu kiểm thử để hợp đồng không phụ thuộc vào tài khoản hoặc bản ghi của môi trường thật như thế nào?
Bạn sẽ thiết kế quy trình review và phê duyệt thay đổi hợp đồng khi nhiều nhóm sở hữu các consumer khác nhau như thế nào?
Bạn sẽ kiểm soát sự khác biệt giữa hợp đồng công khai và khả năng thực tế của những phiên bản provider đang được triển khai ra sao?
Bạn sẽ theo dõi lỗi tích hợp, thay đổi phá vỡ tương thích và phản hồi consumer để cải thiện thiết kế hợp đồng như thế nào?
Bạn sẽ xử lý tình huống API đã đạt kiểm tra OpenAPI nhưng một consumer production vẫn gặp lỗi do giả định ngầm về thứ tự dữ liệu như thế nào?

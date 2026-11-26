Bạn sẽ giải thích High Cohesion bằng mối liên hệ giữa dữ liệu, hành vi và trách nhiệm của một thành phần như thế nào?
Bạn sẽ phân biệt cohesion bên trong một lớp với coupling giữa các lớp khi đánh giá thiết kế ra sao?
Khi nhìn vào một phương thức dài, bạn sẽ xác định các thao tác có cùng mục tiêu hay đang phục vụ nhiều mục tiêu khác nhau như thế nào?
Bạn sẽ đánh giá một lớp có nhiều phương thức nhưng vẫn có cohesion cao dựa trên những bằng chứng nào?
Bạn sẽ nhận diện lớp có cohesion thấp qua việc các nhóm phương thức sử dụng những tập thuộc tính tách biệt ra sao?
Khi một lớp có nhiều lý do thay đổi, bạn sẽ kiểm tra liệu các lý do ấy phản ánh nhiều trách nhiệm độc lập như thế nào?
Bạn sẽ phân biệt nhóm hành vi liên quan nghiệp vụ với việc chỉ được gom chung vì sử dụng cùng một thư viện ra sao?
Trong lớp quản lý đơn hàng, bạn sẽ quyết định hành vi tính tổng tiền, gửi email và xuất PDF nên được đặt ở đâu như thế nào?
Bạn sẽ nhận biết một lớp chứa cả logic nghiệp vụ và logic định dạng giao diện gây mất cohesion bằng cách nào?
Bạn sẽ đánh giá một service thực hiện xác thực, ghi dữ liệu và sinh báo cáo có thực sự cùng một trách nhiệm hay không như thế nào?
Khi hai phương thức cùng sử dụng một trường dữ liệu, bạn sẽ xác định đó có phải bằng chứng đủ mạnh về cohesion cao không như thế nào?
Bạn sẽ phân biệt cohesion chức năng với việc các thao tác chỉ cùng diễn ra trong một thời điểm xử lý ra sao?
Khi một module có nhiều package, bạn sẽ xác định tiêu chí gom nhóm theo năng lực nghiệp vụ thay vì chỉ theo loại lớp như thế nào?
Bạn sẽ phân tích tác động của việc nhóm các chức năng không liên quan vào một module chung đối với khả năng thay đổi ra sao?
Bạn sẽ lựa chọn phạm vi trách nhiệm ở cấp hàm, lớp và module để tránh một trách nhiệm bị phân mảnh quá mức như thế nào?
Bạn sẽ xác định sự khác biệt giữa một lớp điều phối use case và một lớp sở hữu quy tắc nghiệp vụ khi đánh giá cohesion ra sao?
Khi một phương thức cần nhiều nhánh xử lý cho các mục đích riêng, bạn sẽ tìm điểm tách Extract Method theo tiêu chí nào?
Bạn sẽ đặt tên phương thức được trích xuất sao cho phản ánh một ý định rõ ràng thay vì chỉ mô tả các câu lệnh bên trong như thế nào?
Bạn sẽ quyết định khi nào Extract Method làm mã dễ hiểu hơn và khi nào tạo ra quá nhiều hàm chuyển tiếp như thế nào?
Khi nhiều phương thức dùng một nhóm thuộc tính còn nhóm khác dùng thuộc tính riêng, bạn sẽ đề xuất Extract Class dựa trên ranh giới nào?
Bạn sẽ chọn những phương thức và trường dữ liệu nào cần chuyển cùng nhau để lớp mới không phụ thuộc ngược quá nhiều ra sao?
Bạn sẽ dùng Move Method khi một phương thức truy cập dữ liệu của đối tượng khác nhiều hơn chính lớp chứa nó như thế nào?
Bạn sẽ phân tích nguy cơ chuyển phương thức sang một lớp khác khiến quy tắc đóng gói hoặc bất biến bị phá vỡ ra sao?
Khi Extract Class làm phát sinh nhiều lời gọi qua lại, bạn sẽ đánh giá liệu trách nhiệm đã được tách đúng hay chưa bằng cách nào?
Bạn sẽ nhận diện một God Class từ số trách nhiệm, độ đa dạng dữ liệu và lịch sử thay đổi như thế nào?
Bạn sẽ xác định các nhóm phương thức thường sửa cùng nhau trong lịch sử commit để hỗ trợ quyết định tách lớp ra sao?
Khi một lớp chỉ có một phương thức nhưng phương thức ấy làm nhiều việc, bạn sẽ đánh giá cohesion ở cấp phương thức như thế nào?
Bạn sẽ xem xét độ cohesion của một component có rất ít dữ liệu nội bộ nhưng thực hiện một quy trình điều phối duy nhất ra sao?
Khi một utility class chứa nhiều hàm tĩnh không liên quan, bạn sẽ chọn tiêu chí phân tách các hàm ấy như thế nào?
Bạn sẽ đánh giá một interface chứa các thao tác dành cho nhiều client khác nhau có làm trách nhiệm module thiếu thống nhất ra sao?
Khi một service được chia thành nhiều class chỉ để giảm số dòng, bạn sẽ kiểm tra xem cohesion có thật sự được cải thiện không như thế nào?
Bạn sẽ cân nhắc mức cohesion của dịch vụ độc lập theo mục tiêu nghiệp vụ và các quy tắc sở hữu dữ liệu ra sao?
Khi hai dịch vụ cần thay đổi cùng lúc vì một chức năng nhỏ, bạn sẽ đánh giá lại ranh giới trách nhiệm như thế nào?
Bạn sẽ phân biệt cohesion cao với coupling chặt trong tình huống các thành phần nội bộ phối hợp liên tục ra sao?
Khi gom hành vi gần dữ liệu nó sử dụng, bạn sẽ tránh biến đối tượng thành nơi chứa mọi thao tác có liên quan gián tiếp như thế nào?
Bạn sẽ xác định chức năng dùng chung nào thật sự là abstraction ổn định và chức năng nào nên giữ riêng ở từng module như thế nào?
Bạn sẽ đo mức độ liên quan giữa các phương thức qua tập trường được dùng mà không phụ thuộc hoàn toàn vào một chỉ số như thế nào?
Khi chỉ số cohesion tự động báo thấp nhưng lớp có trách nhiệm rõ ràng, bạn sẽ kiểm chứng nhận định ấy bằng cách nào?
Bạn sẽ đánh giá tác động của việc tách lớp đến độ phức tạp của API công khai và số dependency mới phát sinh ra sao?
Bạn sẽ thiết kế bài kiểm thử trước refactor để bảo vệ các quy tắc nghiệp vụ đang nằm trong một lớp đa trách nhiệm như thế nào?
Bạn sẽ kiểm thử một lớp vừa trích xuất để xác minh các bất biến của nó mà không cần khởi chạy toàn hệ thống ra sao?
Khi dùng Move Method, bạn sẽ sửa các test đang phụ thuộc vào chi tiết triển khai để giữ chúng tập trung vào hành vi như thế nào?
Bạn sẽ đánh giá xem refactor đã cải thiện khả năng cô lập lỗi trong unit test bằng những quan sát nào?
Khi các test cần tạo rất nhiều dữ liệu không liên quan chỉ để gọi một phương thức, bạn sẽ suy ra điều gì về ranh giới trách nhiệm?
Bạn sẽ phân biệt một thay đổi API hợp lệ sau Extract Class với sự thay đổi không mong muốn trong hành vi nghiệp vụ như thế nào?
Bạn sẽ lập kế hoạch tách dần một lớp lớn trong Java mà vẫn giữ các caller hoạt động trong giai đoạn chuyển đổi ra sao?
Khi hai trách nhiệm luôn thay đổi cùng nhau trong thực tế, bạn sẽ quyết định giữ chung hay chia ra theo những đánh đổi nào?
Bạn sẽ cân nhắc tác động đến hiệu năng và tính nhất quán trạng thái trước khi di chuyển hành vi qua ranh giới module như thế nào?
Bạn sẽ xác định những tín hiệu nào trong review code cho thấy một phương thức mới không thuộc trách nhiệm của lớp hiện tại?
Bạn sẽ đánh giá thành công của High Cohesion qua khả năng hiểu mã, phạm vi sửa đổi, độ độc lập của test và chi phí bảo trì như thế nào?

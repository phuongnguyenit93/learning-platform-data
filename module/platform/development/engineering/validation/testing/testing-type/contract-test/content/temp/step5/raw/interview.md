Bạn sẽ giải thích kiểm thử hợp đồng giải quyết vấn đề nào khi consumer và provider triển khai hoặc phát hành độc lập như thế nào?
Bạn sẽ phân biệt kiểm thử hợp đồng với kiểm thử tích hợp đầu cuối và kiểm thử chức năng của từng dịch vụ ra sao?
Bạn sẽ xác định chính xác ai là consumer và ai là provider trong một luồng gọi API nhiều tầng như thế nào?
Khi nhiều consumer dùng chung một API, bạn sẽ thu thập kỳ vọng riêng của từng bên bằng cách nào?
Bạn sẽ quyết định những hành vi nào thuộc hợp đồng công khai và những chi tiết nào là triển khai nội bộ ra sao?
Bạn sẽ mô tả yêu cầu về đường dẫn, phương thức HTTP, tham số, header và body trong một hợp đồng REST như thế nào?
Bạn sẽ biểu diễn các mã trạng thái thành công và thất bại mà consumer thực sự cần xử lý trong hợp đồng ra sao?
Khi consumer chỉ đọc một số trường trong JSON, bạn sẽ xác định mức độ nghiêm ngặt của matcher cho các trường còn lại như thế nào?
Bạn sẽ so sánh kiểm tra ví dụ cụ thể với matcher theo kiểu dữ liệu hoặc cấu trúc để tránh hợp đồng quá cứng ra sao?
Bạn sẽ xác định trường nào bắt buộc, trường nào tùy chọn và trường nào có thể null khi thỏa thuận schema như thế nào?
Khi provider thêm thuộc tính mới vào phản hồi, bạn sẽ kiểm tra consumer có bị ảnh hưởng dựa trên những điều kiện nào?
Bạn sẽ nhận diện thay đổi tên trường, thay đổi kiểu hoặc thay đổi ý nghĩa giá trị có thể phá vỡ hợp đồng bằng cách nào?
Bạn sẽ xác định việc đổi mã trạng thái HTTP hoặc thông điệp lỗi có làm hỏng nhánh xử lý của consumer hay không như thế nào?
Khi provider mở rộng tập giá trị enum, bạn sẽ đánh giá consumer có thể chấp nhận giá trị chưa từng gặp ra sao?
Bạn sẽ thiết kế hợp đồng cho phân trang, sắp xếp và bộ lọc để bảo vệ các giả định về hành vi truy vấn như thế nào?
Bạn sẽ xác định mức độ cam kết đối với thứ tự phần tử trong danh sách phản hồi theo yêu cầu thực tế của consumer ra sao?
Khi API trả về kết quả theo thời gian, bạn sẽ xác định định dạng ngày giờ và múi giờ cần cố định trong hợp đồng như thế nào?
Bạn sẽ phân biệt hợp đồng cấu trúc dữ liệu với quy tắc nghiệp vụ cần được xác minh ở mức provider như thế nào?
Bạn sẽ xây dựng một consumer contract test để thể hiện đầu vào và phản hồi mà mã consumer dự kiến sử dụng ra sao?
Khi consumer sử dụng mock provider, bạn sẽ bảo đảm mock phản ánh đúng hợp đồng được công bố như thế nào?
Bạn sẽ lựa chọn dữ liệu ví dụ trong hợp đồng sao cho bao phủ trạng thái hợp lệ, vắng mặt và lỗi quan trọng như thế nào?
Bạn sẽ phân biệt test của consumer kiểm tra cách sử dụng API với bước provider verification kiểm tra khả năng đáp ứng ra sao?
Bạn sẽ chuẩn bị trạng thái dữ liệu của provider để xác minh những trường hợp có tài nguyên và không có tài nguyên như thế nào?
Bạn sẽ xác định cách cô lập dependency phía sau provider để provider verification ổn định và có ý nghĩa ra sao?
Khi provider verification thất bại, bạn sẽ phân biệt sai khác hợp đồng thực sự với lỗi cấu hình môi trường như thế nào?
Bạn sẽ quản lý phiên bản contract của nhiều nhánh phát triển mà không nhầm hợp đồng thử nghiệm với bản đang sản xuất ra sao?
Bạn sẽ mô tả quy trình công bố hợp đồng mới từ consumer để provider có thể kiểm tra sớm như thế nào?
Bạn sẽ quyết định ai chịu trách nhiệm rà soát và chấp nhận thay đổi hợp đồng giữa các nhóm bằng những nguyên tắc nào?
Khi thay đổi phía provider tương thích với consumer mới nhưng không tương thích với consumer cũ, bạn sẽ xây dựng chiến lược chuyển đổi ra sao?
Bạn sẽ xác định điều kiện để phát hành provider an toàn khi một số consumer chưa nâng cấp như thế nào?
Bạn sẽ dùng thông tin phiên bản consumer đang triển khai để quyết định mức độ bắt buộc của mỗi contract verification ra sao?
Bạn sẽ tổ chức cổng kiểm tra trước triển khai để tránh đưa phiên bản không thỏa các hợp đồng đang sử dụng vào sản xuất như thế nào?
Bạn sẽ đánh giá tác động của việc dùng semantic versioning đối với hợp đồng API và chính sách thay đổi lớn ra sao?
Bạn sẽ xây dựng kế hoạch loại bỏ trường cũ qua các giai đoạn thông báo, hỗ trợ song song và xác minh tương thích như thế nào?
Bạn sẽ xác định thời điểm có thể xóa một hợp đồng consumer không còn hoạt động dựa trên bằng chứng nào?
Bạn sẽ phân biệt tương thích ngược và tương thích xuôi của schema thông điệp bằng một tình huống triển khai lệch phiên bản ra sao?
Khi hai dịch vụ trao đổi sự kiện bất đồng bộ, bạn sẽ xác định vai trò producer và consumer trong hợp đồng như thế nào?
Bạn sẽ biểu diễn yêu cầu về tên sự kiện, trường khóa, kiểu dữ liệu và metadata của message trong hợp đồng ra sao?
Bạn sẽ xác định những kỳ vọng nào về thứ tự, trùng lặp hoặc giao lại thông điệp cần được kiểm tra ngoài schema như thế nào?
Khi producer thêm trường mới vào sự kiện, bạn sẽ xác minh consumer cũ có đọc được mà không mất dữ liệu quan trọng ra sao?
Bạn sẽ sử dụng schema registry hoặc quy tắc tiến hóa schema để kiểm tra thay đổi thông điệp trước phát hành như thế nào?
Bạn sẽ phân biệt một thông điệp hợp lệ về schema với thông điệp sai ý nghĩa nghiệp vụ bằng những kiểm tra nào?
Khi có nhiều consumer với kỳ vọng xung đột, bạn sẽ phân tích lựa chọn tách phiên bản API hoặc hỗ trợ nhiều dạng phản hồi ra sao?
Bạn sẽ thiết kế hợp đồng cho API được bảo vệ bằng xác thực mà không đưa thông tin đăng nhập nhạy cảm vào dữ liệu kiểm thử như thế nào?
Bạn sẽ đánh giá rủi ro của việc kiểm tra contract bằng snapshot toàn bộ phản hồi thay vì các trường có ý nghĩa như thế nào?
Bạn sẽ lựa chọn mức tự động hóa của contract test trong pull request, CI và trước phát hành dựa trên tốc độ phản hồi ra sao?
Bạn sẽ ghi nhận báo cáo hợp đồng thất bại thế nào để người sửa biết consumer, phiên bản, tương tác và điểm sai khác cụ thể?
Bạn sẽ xây dựng bài kiểm thử để phân biệt thay đổi tương thích với lỗi hồi quy phát sinh từ một bản nâng cấp dependency như thế nào?
Bạn sẽ xác định giới hạn của contract testing đối với hiệu năng, dữ liệu thực và sự cố xuyên nhiều dịch vụ ra sao?
Bạn sẽ đánh giá hiệu quả của quy trình contract test qua số thay đổi gây lỗi tích hợp, thời gian phát hiện và độ tin cậy khi phát hành như thế nào?

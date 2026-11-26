Bạn sẽ giải thích vì sao Test-Driven Development bắt đầu từ hành vi mong muốn thay vì bắt đầu viết mã triển khai như thế nào?
Bạn sẽ mô tả mục tiêu riêng của các bước Red, Green và Refactor trong một vòng TDD ra sao?
Bạn sẽ lựa chọn một hành vi nhỏ nhất có ý nghĩa để viết test đầu tiên cho chức năng tính phí như thế nào?
Bạn sẽ xác minh test mới thất bại ở bước Red vì hành vi chưa được triển khai chứ không phải do lỗi cấu hình ra sao?
Bạn sẽ phân biệt một assertion thất bại đúng kỳ vọng với test không chạy được do exception thiết lập môi trường như thế nào?
Bạn sẽ viết mã vừa đủ để qua bước Green mà không thêm trước những tính năng chưa có test như thế nào?
Bạn sẽ giải thích vì sao một cách triển khai đơn giản hoặc tạm thời ở bước Green vẫn có thể phù hợp với chu trình TDD ra sao?
Bạn sẽ chọn bước refactor đầu tiên khi cả test mới và những test trước đều đã xanh như thế nào?
Bạn sẽ tổ chức vòng lặp Red–Green–Refactor ngắn để nhanh chóng phát hiện một quyết định thiết kế sai ra sao?
Bạn sẽ xác định dấu hiệu đang viết quá nhiều mã giữa hai lần chạy test và điều chỉnh nhịp làm việc như thế nào?
Bạn sẽ dùng JUnit để diễn đạt một trường hợp đầu vào và kết quả mong đợi bằng assertion rõ ràng như thế nào?
Bạn sẽ chọn cách đặt tên test để người đọc biết hành vi, điều kiện và kết quả mà không đọc implementation ra sao?
Bạn sẽ dùng kiểm thử tham số hóa trong JUnit khi nhiều dữ liệu đầu vào cùng tuân theo một quy tắc như thế nào?
Bạn sẽ quyết định khi nào các trường hợp kiểm thử cần tách riêng thay vì gộp quá nhiều assertion trong một test ra sao?
Bạn sẽ xác định các giá trị biên quan trọng trước khi viết mã kiểm tra hạn mức hoặc khoảng giá trị như thế nào?
Bạn sẽ xây dựng test cho đầu vào không hợp lệ và làm rõ hành vi lỗi mà API cần cam kết ra sao?
Bạn sẽ kiểm thử một phương thức ném ngoại lệ có ý nghĩa mà không ràng buộc test vào thông điệp nội bộ dễ thay đổi như thế nào?
Bạn sẽ phân biệt test kiểm tra kết quả đầu ra với test kiểm tra tương tác với một dependency ra sao?
Bạn sẽ nhận diện tình huống mock quá nhiều lời gọi nội bộ khiến test dễ hỏng sau refactor như thế nào?
Bạn sẽ lựa chọn stub, fake hay mock cho một dependency cụ thể dựa trên mục tiêu kiểm thử như thế nào?
Bạn sẽ dùng constructor injection để thay dịch vụ ngoài bằng test double mà không sửa mã nghiệp vụ như thế nào?
Bạn sẽ đưa Clock vào đối tượng cần kiểm thử để kết quả không phụ thuộc vào thời điểm test chạy ra sao?
Bạn sẽ kiểm soát yếu tố ngẫu nhiên hoặc mã định danh được sinh ra để test vẫn có tính xác định như thế nào?
Bạn sẽ thiết kế test cho một đối tượng có trạng thái thay đổi qua nhiều thao tác mà không phụ thuộc thứ tự các test khác ra sao?
Bạn sẽ tổ chức fixture hoặc phương thức thiết lập test để giảm trùng lặp nhưng vẫn thấy rõ dữ liệu quan trọng như thế nào?
Bạn sẽ xử lý tình huống một test chỉ qua khi chạy riêng lẻ nhưng thất bại khi chạy cùng toàn bộ bộ test ra sao?
Bạn sẽ phân biệt unit test nhanh với integration test cần database thật và xác định nơi áp dụng TDD phù hợp như thế nào?
Bạn sẽ thiết kế fake repository để kiểm tra quy tắc nghiệp vụ nhưng không giả định fake thay thế được kiểm thử persistence thật ra sao?
Bạn sẽ quyết định khi nào một hành vi có nhiều bước bất đồng bộ cần test trạng thái cuối thay vì chờ thời gian cố định như thế nào?
Bạn sẽ tránh để test gửi email, thanh toán hoặc thay đổi dữ liệu thật khi kiểm tra logic của ứng dụng ra sao?
Bạn sẽ xử lý các trường hợp null, collection rỗng và dữ liệu trùng lặp theo hợp đồng nghiệp vụ như thế nào?
Bạn sẽ chọn thứ tự bổ sung test từ trường hợp đơn giản đến trường hợp phức tạp để thiết kế được dẫn dắt từng bước ra sao?
Bạn sẽ nhận diện sự xuất hiện của logic điều kiện quá nhiều nhánh trong mã Green và refactor như thế nào?
Bạn sẽ sử dụng Extract Method hoặc Introduce Parameter Object trong bước Refactor mà vẫn giữ toàn bộ test xanh ra sao?
Bạn sẽ biết khi nào cần tách một lớp do trách nhiệm tăng lên trong quá trình đáp ứng các test mới như thế nào?
Bạn sẽ phân biệt thay đổi cấu trúc sản phẩm với việc sửa hoặc làm rõ một test khó hiểu trong bước Refactor ra sao?
Bạn sẽ xác định một test đang kiểm tra chi tiết triển khai thay vì hành vi công khai và viết lại nó như thế nào?
Bạn sẽ dùng các test hiện có để bảo vệ hành vi khi chuyển từ một cấu trúc dữ liệu sang cấu trúc khác ra sao?
Bạn sẽ cân nhắc có nên thêm test trước khi sửa một bug được báo cáo và mô tả chính xác lỗi bằng test như thế nào?
Bạn sẽ tiếp cận TDD cho mã Java cũ có phụ thuộc tĩnh, singleton hoặc kết nối database trực tiếp theo các bước nào?
Bạn sẽ tạo điểm nối để thay dependency trong mã khó kiểm thử mà không phải viết lại toàn bộ ứng dụng ra sao?
Bạn sẽ đánh giá khi nào cần acceptance test hoặc contract test bổ sung vì unit test không bảo vệ đủ hành vi của hệ thống như thế nào?
Bạn sẽ sử dụng phản hồi từ test để phát hiện API của lớp quá khó khởi tạo hoặc sử dụng như thế nào?
Bạn sẽ phân biệt TDD với việc viết rất nhiều unit test sau khi đã xong toàn bộ chức năng ra sao?
Bạn sẽ xác định giới hạn của việc dùng chỉ số code coverage để đánh giá một nhóm thực hành TDD hiệu quả như thế nào?
Bạn sẽ đưa việc chạy test nhanh vào vòng phát triển cục bộ và CI để lỗi được phát hiện ở đúng thời điểm ra sao?
Bạn sẽ chẩn đoán và giảm test flaky do đồng thời, thời gian hoặc phụ thuộc môi trường mà không xóa những assertion có giá trị như thế nào?
Bạn sẽ thiết kế các bước commit theo chu trình TDD để có thể tìm lại lý do xuất hiện một quy tắc trong mã như thế nào?
Bạn sẽ chọn tiêu chí đánh giá tác động của TDD đối với khả năng thay đổi, tốc độ phản hồi và chất lượng mã như thế nào?
Bạn sẽ xử lý tình huống tất cả unit test đều xanh nhưng tính năng vẫn sai vì nhóm đã chọn những ví dụ đầu vào không đại diện ra sao?

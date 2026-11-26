Bạn sẽ giải thích mục tiêu tổ chức phần mềm theo kiến trúc phân tầng bằng một ví dụ ứng dụng cụ thể như thế nào?
Bạn sẽ xác định những trách nhiệm nào cần tách thành các tầng trong một ứng dụng quản lý đơn hàng ra sao?
Bạn sẽ phân biệt tầng trình bày, tầng nghiệp vụ và tầng truy cập dữ liệu theo loại công việc mỗi tầng thực hiện như thế nào?
Bạn sẽ mô tả luồng xử lý từ giao diện người dùng đến lưu trữ và trả kết quả trong hệ thống phân tầng ra sao?
Bạn sẽ lựa chọn số tầng phù hợp dựa trên quy mô, độ phức tạp và nhu cầu thay đổi của ứng dụng như thế nào?
Bạn sẽ xác định ranh giới một tầng dựa trên lý do thay đổi và sự phụ thuộc vào các phần khác ra sao?
Bạn sẽ phân biệt mô hình ba tầng logic với triển khai các tầng trên nhiều máy chủ vật lý như thế nào?
Bạn sẽ giải thích vì sao phân tầng không đồng nghĩa với mỗi tầng phải chạy trong một tiến trình riêng ra sao?
Bạn sẽ kiểm soát chiều phụ thuộc giữa các tầng để tránh một tầng thấp phụ thuộc ngược vào giao diện như thế nào?
Bạn sẽ so sánh kiểu phân tầng nghiêm ngặt chỉ gọi tầng kế tiếp với kiểu cho phép bỏ qua tầng trung gian ra sao?
Bạn sẽ đánh giá rủi ro khi controller trực tiếp truy vấn cơ sở dữ liệu thay vì đi qua tầng nghiệp vụ như thế nào?
Bạn sẽ quyết định logic xác thực dữ liệu đầu vào nên nằm ở tầng trình bày hay nghiệp vụ dựa trên tiêu chí nào?
Bạn sẽ xác định vị trí của quy tắc nghiệp vụ áp dụng cho nhiều giao diện khác nhau như thế nào?
Bạn sẽ thiết kế hợp đồng giữa tầng trình bày và tầng ứng dụng để giảm phụ thuộc vào cấu trúc giao diện ra sao?
Bạn sẽ phân biệt đối tượng truyền dữ liệu với đối tượng nghiệp vụ khi dữ liệu đi qua ranh giới tầng như thế nào?
Bạn sẽ tổ chức việc chuyển đổi dữ liệu giữa các tầng mà không lặp lại logic ánh xạ ở nhiều nơi ra sao?
Bạn sẽ lựa chọn cách chia package hoặc module nguồn để biểu diễn các tầng rõ ràng trong dự án Java như thế nào?
Bạn sẽ xác định các trách nhiệm của lớp service để tránh biến nó thành nơi chứa mọi logic của hệ thống ra sao?
Bạn sẽ thiết kế lớp repository để che giấu chi tiết truy vấn mà vẫn đáp ứng nhu cầu nghiệp vụ như thế nào?
Bạn sẽ nhận biết những dấu hiệu tầng nghiệp vụ bị phụ thuộc quá sâu vào chi tiết database như thế nào?
Bạn sẽ xử lý một quy tắc kiểm tra quyền truy cập cần được thực thi cho nhiều đường gọi khác nhau ra sao?
Bạn sẽ xác định ranh giới giao dịch khi một thao tác nghiệp vụ cập nhật nhiều bản ghi như thế nào?
Bạn sẽ kiểm soát việc tầng trình bày tự mở giao dịch hoặc thay đổi dữ liệu khiến trách nhiệm bị chồng chéo ra sao?
Bạn sẽ định nghĩa cách truyền lỗi nghiệp vụ và lỗi hạ tầng qua các tầng mà không làm lộ thông tin nội bộ như thế nào?
Bạn sẽ ánh xạ lỗi từ tầng nghiệp vụ sang thông báo phù hợp với người dùng ở tầng trình bày ra sao?
Bạn sẽ quyết định một bước xử lý dùng chung nên nằm trong tầng hiện có hay tách ra thành thành phần riêng như thế nào?
Bạn sẽ quản lý các mối quan tâm xuyên suốt như logging, bảo mật và đo hiệu năng mà không sao chép mã ở mọi tầng ra sao?
Bạn sẽ áp dụng dependency injection để các tầng kết nối qua hợp đồng rõ ràng như thế nào?
Bạn sẽ đánh giá việc sử dụng interface ở ranh giới tầng nào mang lại khả năng thay thế và kiểm thử thực tế ra sao?
Bạn sẽ nhận diện sự phụ thuộc vòng giữa các package thuộc các tầng và tìm nguyên nhân thiết kế như thế nào?
Bạn sẽ dùng quy tắc kiểm tra kiến trúc để ngăn lớp truy cập dữ liệu gọi trực tiếp mã giao diện ra sao?
Bạn sẽ thiết kế unit test cho tầng nghiệp vụ mà không cần khởi chạy giao diện hoặc cơ sở dữ liệu như thế nào?
Bạn sẽ lựa chọn integration test nào để xác minh tầng truy cập dữ liệu thực hiện đúng hợp đồng như thế nào?
Bạn sẽ thiết kế kiểm thử qua ranh giới giữa tầng trình bày và tầng nghiệp vụ để phát hiện sai lệch dữ liệu ra sao?
Bạn sẽ tránh việc mock toàn bộ các tầng làm một bài kiểm thử đi qua mã nhưng không kiểm chứng được hành vi thật như thế nào?
Bạn sẽ phân tích ảnh hưởng của nhiều lần chuyển tiếp giữa các tầng tới độ trễ của một yêu cầu ra sao?
Bạn sẽ xác định khi nào các tầng quá mỏng chỉ chuyển tiếp lời gọi và làm tăng chi phí bảo trì như thế nào?
Bạn sẽ đánh giá khả năng tái sử dụng tầng nghiệp vụ khi thêm giao diện web, dòng lệnh hoặc tác vụ nền ra sao?
Bạn sẽ phân biệt kiến trúc phân tầng với thiết kế chia hệ thống thành các module theo tính năng như thế nào?
Bạn sẽ phối hợp cách chia theo tầng và theo tính năng để người phát triển tìm đúng vị trí chỉnh sửa dễ dàng ra sao?
Bạn sẽ kiểm soát việc nhiều tính năng dùng chung một tầng truy cập dữ liệu khiến thay đổi nhỏ ảnh hưởng rộng như thế nào?
Bạn sẽ xác định khi nào một mô hình phân tầng phù hợp với ứng dụng CRUD có yêu cầu nghiệp vụ đơn giản ra sao?
Bạn sẽ phân tích hạn chế của kiến trúc phân tầng khi nghiệp vụ phức tạp và cần thử nghiệm nhiều cách tích hợp như thế nào?
Bạn sẽ so sánh cách kiểm soát phụ thuộc của kiến trúc phân tầng với hướng ports và adapters trong một tình huống thay database ra sao?
Bạn sẽ lập kế hoạch tách một ứng dụng nguyên khối có controller chứa cả truy vấn và logic nghiệp vụ thành các tầng như thế nào?
Bạn sẽ chọn thứ tự di chuyển các chức năng sang tầng phù hợp mà vẫn giữ kết quả hoạt động của hệ thống như thế nào?
Bạn sẽ dùng test hiện có và kiểm tra hồi quy để bảo vệ hành vi khi refactor ranh giới giữa các tầng ra sao?
Bạn sẽ đánh giá hiệu quả phân tầng qua khả năng kiểm thử, độ kết dính và mức độ phụ thuộc giữa các lớp như thế nào?
Bạn sẽ xử lý bất đồng khi hai nhóm đều muốn đặt một quy tắc quan trọng tại tầng của mình như thế nào?
Bạn sẽ xem xét lại thiết kế khi một thay đổi nhỏ phải sửa đồng thời controller, service, repository và nhiều kiểu dữ liệu trung gian ra sao?

Bạn sẽ giải thích Dependency Injection giải quyết vấn đề gì khi một lớp Java tự tạo các phụ thuộc của mình như thế nào?
Bạn sẽ phân biệt nguyên lý Inversion of Control với kỹ thuật Dependency Injection bằng một ví dụ cụ thể ra sao?
Bạn sẽ xác định những đối tượng nào là dependency của một service và trách nhiệm tạo chúng nên thuộc về đâu như thế nào?
Bạn sẽ so sánh constructor injection, setter injection và method injection theo yêu cầu về tính bắt buộc của phụ thuộc ra sao?
Bạn sẽ lựa chọn constructor injection để biểu diễn các bất biến của một đối tượng ngay khi khởi tạo như thế nào?
Bạn sẽ giải thích vì sao một class phụ thuộc vào interface thay vì implementation có thể dễ thay thế và kiểm thử hơn ra sao?
Bạn sẽ phân biệt Dependency Injection với nguyên tắc Dependency Inversion mà không coi chúng là cùng một khái niệm như thế nào?
Bạn sẽ thiết kế ví dụ Java thuần mà OrderService nhận PaymentGateway qua constructor thay vì tự new đối tượng như thế nào?
Bạn sẽ tạo một implementation giả của interface để kiểm thử nghiệp vụ mà không gọi dịch vụ bên ngoài ra sao?
Bạn sẽ xác định những phụ thuộc nào là dữ liệu của một lần gọi và không nên inject thành dependency sống lâu như thế nào?
Bạn sẽ phân biệt đối tượng mang trạng thái nghiệp vụ với một dependency cung cấp dịch vụ kỹ thuật khi xây dựng constructor ra sao?
Bạn sẽ đánh giá nguy cơ constructor có quá nhiều dependency như một dấu hiệu lớp đang gánh quá nhiều trách nhiệm như thế nào?
Bạn sẽ sử dụng composition root để tập trung việc tạo và lắp ghép các đối tượng khi ứng dụng Java khởi động ra sao?
Bạn sẽ xác định ranh giới composition root với lớp nghiệp vụ để việc khởi tạo không lan khắp mã nguồn như thế nào?
Bạn sẽ thiết kế một object graph từ controller đến service và repository rồi lắp ghép hoàn toàn bằng Java thuần như thế nào?
Bạn sẽ giải thích vì sao việc gọi container để lấy bean từ mọi lớp có thể trở thành Service Locator và che giấu phụ thuộc ra sao?
Bạn sẽ so sánh manual DI với container tự động về độ rõ ràng, chi phí cấu hình và khả năng kiểm soát như thế nào?
Bạn sẽ quyết định khi nào một factory có trách nhiệm tạo đối tượng runtime và khi nào cần inject factory đó như thế nào?
Bạn sẽ tránh việc lạm dụng interface cho các lớp không có nhu cầu thay thế hoặc cô lập khi kiểm thử ra sao?
Bạn sẽ tổ chức cấu hình để chọn implementation cho môi trường thử nghiệm và triển khai mà không sửa logic nghiệp vụ như thế nào?
Bạn sẽ thiết kế cách inject nhiều implementation của cùng một interface và chọn implementation phù hợp theo yêu cầu ra sao?
Bạn sẽ xác định khi nào dùng một Strategy được inject thay vì chuỗi if/else chọn implementation ngay trong service như thế nào?
Bạn sẽ xử lý dependency tùy chọn sao cho constructor không dễ tạo đối tượng ở trạng thái thiếu hợp lệ như thế nào?
Bạn sẽ xác định cách kiểm tra đối số constructor bị null để lỗi cấu hình xuất hiện sớm và dễ chẩn đoán ra sao?
Bạn sẽ kiểm soát thứ tự khởi tạo khi một đối tượng phụ thuộc vào nhiều tài nguyên cần mở kết nối như thế nào?
Bạn sẽ phân biệt vòng đời của dependency singleton, đối tượng theo request và đối tượng được tạo mới cho mỗi lần sử dụng ra sao?
Bạn sẽ phân tích rủi ro khi một singleton giữ tham chiếu trực tiếp tới dependency có scope ngắn hơn như thế nào?
Bạn sẽ quyết định có cần factory hoặc provider để tạo dependency theo từng lần gọi khi object sống lâu hơn ra sao?
Bạn sẽ bảo đảm dependency singleton an toàn khi được nhiều luồng gọi đồng thời như thế nào?
Bạn sẽ tổ chức việc đóng kết nối, thread pool và các tài nguyên khác khi composition root kết thúc vòng đời ra sao?
Bạn sẽ nhận diện phụ thuộc vòng giữa hai service và tìm cách tách trách nhiệm thay vì chỉ che giấu vòng lặp như thế nào?
Bạn sẽ phân biệt lỗi do thiếu binding, có nhiều binding khả dĩ và lỗi phát sinh trong constructor khi lắp ghép phụ thuộc ra sao?
Bạn sẽ xác định thông tin nào cần ghi lại để một lỗi cấu hình object graph dễ được tìm ra như thế nào?
Bạn sẽ đưa Clock hoặc nguồn tạo số ngẫu nhiên vào constructor để test không phụ thuộc vào thời gian thực như thế nào?
Bạn sẽ dùng fake, stub và mock ở những tình huống khác nhau để kiểm chứng hành vi của class có DI ra sao?
Bạn sẽ thiết kế unit test cho service bằng các dependency thủ công thay vì cần khởi chạy DI container như thế nào?
Bạn sẽ nhận biết test dùng quá nhiều mock tương tác nội bộ khiến refactor khó khăn dù có Dependency Injection ra sao?
Bạn sẽ lựa chọn kiểm thử tích hợp nào để bảo đảm composition root thực sự ghép đúng các implementation như thế nào?
Bạn sẽ kiểm tra một application context có khởi tạo đầy đủ và giải phóng tài nguyên đúng vòng đời mà không kiểm thử lặp logic nghiệp vụ ra sao?
Bạn sẽ so sánh cấu hình lắp ghép bằng mã Java với cấu hình khai báo và đánh giá khả năng truy vết phụ thuộc như thế nào?
Bạn sẽ xác định trường hợp inject đối tượng cấu hình đã được kiểm tra hợp lệ sẽ an toàn hơn đọc biến môi trường trong mọi service ra sao?
Bạn sẽ bảo vệ khóa và mật khẩu bằng cách giới hạn nơi cấu hình nhạy cảm được đọc và truyền qua object graph như thế nào?
Bạn sẽ thiết kế lớp adapter để che giấu SDK bên ngoài sau một interface được inject vào nghiệp vụ như thế nào?
Bạn sẽ đánh giá việc inject repository có làm domain phụ thuộc vào chi tiết persistence hay không bằng cách nào?
Bạn sẽ phân tích tác động của việc tạo dependency quá sớm đến thời gian khởi động và mức tiêu thụ tài nguyên như thế nào?
Bạn sẽ lựa chọn khởi tạo lười và khởi tạo sớm dựa trên khả năng phát hiện lỗi cấu hình và nhu cầu runtime ra sao?
Bạn sẽ chuyển một lớp Java đang dùng static global hoặc singleton tự quản lý sang constructor injection theo từng bước như thế nào?
Bạn sẽ giữ tính tương thích của public API khi bổ sung dependency mới vào constructor của một lớp đang được nhiều nơi sử dụng ra sao?
Bạn sẽ đo mức cải thiện về khả năng kiểm thử và thay thế implementation sau khi áp dụng DI như thế nào?
Bạn sẽ xử lý tình huống test chạy đúng với dependency giả nhưng ứng dụng thất bại khi được lắp ghép với dependency thật như thế nào?

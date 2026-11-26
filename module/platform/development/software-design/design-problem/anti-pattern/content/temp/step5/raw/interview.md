Bạn phân biệt anti-pattern với một code smell và với một quyết định thiết kế có chủ đích trong ngữ cảnh cụ thể như thế nào?
Những bằng chứng nào giúp bạn khẳng định một cách giải quyết lặp đi lặp lại đang tạo hậu quả bất lợi thay vì chỉ khác sở thích cá nhân?
Khi nhóm gọi một thiết kế là anti-pattern, bạn sẽ thu thập thông tin về yêu cầu và ràng buộc ban đầu ra sao?
Bạn phân tích chuỗi nguyên nhân, quyết định và hậu quả trước khi đề xuất refactor một anti-pattern như thế nào?
Trong một lớp God Object quản lý nhiều nghiệp vụ, bạn nhận diện các trách nhiệm có thể tách độc lập bằng cách nào?
Bạn sẽ tách từng phần khỏi God Object mà vẫn giữ hoạt động của các client hiện có ra sao?
Khi một hệ thống trở thành Big Ball of Mud, bạn xác định những phụ thuộc cần được kiểm soát trước tiên như thế nào?
Bạn phân biệt Spaghetti Code do luồng điều khiển rối với thiết kế có nhiều module nhưng ranh giới yếu ra sao?
Nếu một thay đổi nhỏ phải sửa nhiều lớp không liên quan, bạn điều tra nguyên nhân ghép nối dẫn đến Shotgun Surgery như thế nào?
Bạn xử lý một khối mã bị copy-paste nhiều nơi mà vẫn bảo toàn các khác biệt nghiệp vụ quan trọng như thế nào?
Khi một nhóm áp dụng cùng một công cụ thiết kế cho mọi tình huống, bạn phát hiện dấu hiệu Golden Hammer ra sao?
Bạn sẽ so sánh giải pháp đơn giản với framework phức tạp đang được ưa chuộng bằng những tiêu chí nào?
Nếu hệ thống dùng trừu tượng hóa cho các biến thể chưa từng xuất hiện, bạn đánh giá nguy cơ speculative generality như thế nào?
Bạn nhận ra những trường hợp lạm dụng kế thừa để tái sử dụng mã nhưng phá vỡ quan hệ is-a ra sao?
Khi lớp con liên tục override phương thức chỉ để ném lỗi, bạn phân tích hợp đồng kế thừa bị vi phạm như thế nào?
Bạn lựa chọn composition thay inheritance cho một chuỗi phân cấp lớp không còn phản ánh nghiệp vụ ra sao?
Khi một interface có hàng chục phương thức chỉ một số client dùng, bạn xác định gốc rễ của trừu tượng hóa cồng kềnh như thế nào?
Bạn phân biệt một domain model thiếu hành vi với quyết định cố ý dùng mô hình dữ liệu đơn giản ở tầng tích hợp ra sao?
Nếu các quy tắc miền bị phân tán trong controller và repository, bạn sẽ tập hợp chúng về đúng trách nhiệm bằng cách nào?
Bạn đánh giá nguy cơ của Service Locator khi dependency bị ẩn và khó thay thế trong kiểm thử như thế nào?
Một Singleton giữ trạng thái mutable dùng chung có thể tạo ra những phụ thuộc ngầm và lỗi đồng thời nào?
Khi nhiều module cùng chỉnh sửa một cấu trúc dữ liệu toàn cục, bạn thiết kế lại quyền sở hữu và hợp đồng truy cập ra sao?
Bạn nhận diện dấu hiệu cyclic dependencies giữa các module và xác định lý do chu kỳ hình thành như thế nào?
Bạn chọn cách cắt vòng phụ thuộc thông qua hợp đồng hoặc tổ chức lại trách nhiệm dựa trên tiêu chí nào?
Khi business logic phụ thuộc trực tiếp vào chi tiết database, bạn phân tích rủi ro Database-Centric Design như thế nào?
Bạn sẽ phát hiện mô hình domain bị ép theo cấu trúc bảng hiện có thay vì quy tắc nghiệp vụ ra sao?
Nếu một service vừa ghi database vừa gọi API ngoài trong transaction dài, bạn đánh giá anti-pattern giao dịch này như thế nào?
Bạn phân biệt distributed monolith với microservices có ranh giới triển khai độc lập qua những tín hiệu nào?
Khi một yêu cầu đòi triển khai đồng thời nhiều dịch vụ, bạn kiểm tra nguyên nhân hợp đồng và chia sẻ dữ liệu ra sao?
Bạn xác định rủi ro của chuỗi gọi đồng bộ dài trong hệ phân tán và lựa chọn điểm cắt phù hợp như thế nào?
Khi nhóm tối ưu hóa trước khi đo đạc, bạn phân biệt vấn đề hiệu năng thực sự với suy đoán dẫn tới premature optimization như thế nào?
Bạn dùng phép đo nào để chứng minh một tối ưu hóa phức tạp có làm tăng chi phí bảo trì nhiều hơn lợi ích?
Khi mã cũ chứa nhánh không ai biết còn được dùng, bạn thu thập bằng chứng để xử lý Lava Flow an toàn như thế nào?
Bạn đánh giá rủi ro của việc xóa mã tưởng như chết nhưng được gọi qua reflection hoặc cấu hình như thế nào?
Khi gặp các lớp trừu tượng giống hệt nhau chỉ khác tên, bạn sẽ xác định liệu chúng có thực sự đại diện các khái niệm riêng không?
Bạn phân tích việc truyền một đối tượng cấu hình khổng lồ qua mọi lớp như dấu hiệu ghép nối và rò rỉ trách nhiệm ra sao?
Bạn nhận diện anti-pattern xử lý ngoại lệ bằng cách bắt rồi bỏ qua lỗi qua những hệ quả vận hành nào?
Khi logic fallback che giấu lỗi dữ liệu, bạn cân nhắc bảo toàn tính đúng đắn so với độ sẵn sàng như thế nào?
Bạn sẽ kiểm tra nguy cơ do một utility class tĩnh chứa ngày càng nhiều quy tắc nghiệp vụ không liên quan ra sao?
Nếu refactor làm tăng số lớp nhưng không giảm thay đổi chéo, bạn dùng bằng chứng nào để đánh giá hiệu quả thực tế?
Bạn lựa chọn anti-pattern nào cần xử lý trước dựa trên tần suất thay đổi, số lỗi và tác động đến người dùng ra sao?
Khi mã chưa có kiểm thử, bạn xây dựng characterization test để ghi nhận hành vi trước khi tách trách nhiệm như thế nào?
Bạn thiết kế chuỗi refactor nhỏ có thể review và rollback để loại bỏ phụ thuộc rối như thế nào?
Khi refactor làm thay đổi thời gian phản hồi, bạn kiểm tra tính tương đương chức năng cùng ảnh hưởng phi chức năng ra sao?
Bạn dùng dependency graph, độ phức tạp và lịch sử commit để củng cố nhận định về một anti-pattern như thế nào?
Nếu hai nhóm có ý kiến trái ngược về việc tách module, bạn tạo thử nghiệm hoặc tiêu chí đánh giá chung ra sao?
Bạn kiểm tra những tác dụng phụ nào có thể bị bỏ sót khi di chuyển quy tắc nghiệp vụ khỏi một lớp lớn?
Khi một kiến trúc đang vận hành ổn định nhưng khó thay đổi, bạn lựa chọn thời điểm và phạm vi cải tiến dựa trên rủi ro nào?
Bạn thiết kế quy ước code review để phát hiện anti-pattern tái xuất hiện mà không biến review thành kiểm tra máy móc ra sao?
Sau một đợt refactor, bạn chứng minh sự cải thiện bằng tỷ lệ lỗi, độ dễ kiểm thử và chi phí thay đổi như thế nào?

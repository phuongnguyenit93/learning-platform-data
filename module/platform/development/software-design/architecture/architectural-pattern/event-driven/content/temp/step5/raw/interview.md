Bạn xác định những bài toán nào phù hợp với kiến trúc hướng sự kiện hơn giao tiếp yêu cầu–phản hồi đồng bộ?
Bạn phân biệt vai trò producer, broker và consumer trong một luồng xử lý nghiệp vụ như thế nào?
Bạn sẽ xác định ranh giới trách nhiệm của các dịch vụ để sự kiện không làm lộ chi tiết nội bộ ra sao?
Một domain event khác integration event ở phạm vi sử dụng và mức độ ổn định hợp đồng như thế nào?
Bạn phân biệt thông điệp command yêu cầu hành động với event thông báo sự việc đã xảy ra ra sao?
Bạn sẽ đặt tên sự kiện theo sự thật nghiệp vụ và mô tả thời điểm xảy ra như thế nào?
Những trường metadata nào như event ID, thời gian, phiên bản và correlation ID cần xuất hiện trong event envelope?
Bạn xác định payload sự kiện nên chứa dữ liệu cần thiết hay chỉ định danh đối tượng dựa trên yếu tố nào?
Bạn sẽ mô tả hợp đồng event để nhiều consumer hiểu cùng một ý nghĩa nghiệp vụ ra sao?
Khi event được gửi tới nhiều dịch vụ, bạn thiết kế quyền truy cập và giới hạn dữ liệu nhạy cảm như thế nào?
Bạn phân biệt queue theo mô hình cạnh tranh xử lý với topic pub/sub theo mô hình phát tán sự kiện ra sao?
Bạn lựa chọn ranh giới topic theo loại sự kiện, nguồn phát hay nhóm consumer bằng tiêu chí nào?
Khi một sự kiện cần được xử lý độc lập bởi nhiều nhóm, bạn thiết kế subscription và consumer group như thế nào?
Bạn đánh giá việc chia partition theo aggregate ID ảnh hưởng đến thứ tự và thông lượng ra sao?
Trong điều kiện có nhiều partition, bạn bảo đảm thứ tự tương đối cần thiết cho cùng một thực thể như thế nào?
Bạn phân biệt các bảo đảm giao hàng at-most-once, at-least-once và exactly-once trong bối cảnh nghiệp vụ ra sao?
Vì sao một consumer vẫn cần xử lý trùng lặp ngay cả khi broker hỗ trợ các cơ chế giao hàng nâng cao?
Bạn thiết kế khóa idempotency và nơi lưu dấu xử lý để một sự kiện không gây tác dụng phụ hai lần như thế nào?
Bạn sẽ quyết định thời điểm ack message để tránh mất dữ liệu hoặc xử lý trùng ngoài ý muốn ra sao?
Khi xử lý event thất bại do lỗi mạng tạm thời, bạn lựa chọn retry, backoff và giới hạn số lần ra sao?
Bạn phân biệt lỗi nghiệp vụ không thể phục hồi với lỗi hạ tầng có thể thử lại bằng cách nào?
Bạn tổ chức dead-letter queue và thông tin nguyên nhân để có thể kiểm tra sự kiện lỗi như thế nào?
Khi muốn phát lại các sự kiện đã xử lý, bạn bảo vệ side effect như gửi email hoặc thanh toán ra sao?
Bạn thiết kế checkpoint hoặc offset cho consumer để tiếp tục xử lý sau khi khởi động lại như thế nào?
Nếu database commit thành công nhưng tiến trình chết trước khi publish, hệ thống có thể khôi phục thông báo bằng cách nào?
Bạn mô tả cách transactional outbox liên kết việc ghi dữ liệu nghiệp vụ với ghi bản ghi sự kiện trong cùng transaction ra sao?
Bạn lựa chọn polling outbox hay cơ chế lấy thay đổi từ log dữ liệu dựa trên độ trễ và vận hành như thế nào?
Khi outbox publisher gửi lại một sự kiện do không nhận được xác nhận, consumer sẽ xử lý an toàn ra sao?
Bạn thiết kế lưu trữ và dọn dẹp outbox để không mất khả năng truy vết nhưng cũng không tăng dữ liệu vô hạn như thế nào?
Khi producer và consumer có độ trễ xử lý khác nhau, bạn xác định mức eventual consistency chấp nhận được ra sao?
Bạn thiết kế giao diện hiển thị trạng thái đang xử lý khi nghiệp vụ chưa hoàn tất trên các consumer như thế nào?
Event time và processing time khác nhau ra sao khi xây dựng báo cáo từ luồng sự kiện?
Khi một event cũ đến sau event mới, bạn sẽ cập nhật projection mà không ghi đè sai trạng thái như thế nào?
Bạn sẽ phát hiện và xử lý sự kiện thiếu hoặc sai thứ tự dựa trên phiên bản aggregate như thế nào?
Khi thêm trường mới vào event payload, bạn duy trì tương thích với consumer đang dùng phiên bản cũ ra sao?
Bạn quản lý thay đổi tên hoặc ý nghĩa của một sự kiện để không phá vỡ hợp đồng đang được nhiều dịch vụ sử dụng như thế nào?
Bạn phân biệt phối hợp Saga theo choreography và orchestration theo số lượng bước và mức độ kiểm soát ra sao?
Một quy trình đặt hàng liên quan đến thanh toán và tồn kho có thể dùng các sự kiện và hành động bù trừ như thế nào?
Khi một bước Saga thất bại sau nhiều bước đã thành công, bạn xác định thứ tự và điều kiện bù trừ ra sao?
Bạn sẽ tránh vòng phản hồi vô tận khi hai consumer liên tục phát sự kiện kích hoạt lẫn nhau bằng cách nào?
Khi một sự kiện được fan-out tới hàng chục consumer, bạn đánh giá tác động thay đổi hợp đồng lên toàn hệ thống ra sao?
Bạn thiết kế giới hạn đồng thời và backpressure để consumer không bị ngập bởi lưu lượng tăng đột biến như thế nào?
Khi broker không sẵn sàng, bạn lựa chọn cách tiếp nhận yêu cầu và phục hồi việc phát sự kiện như thế nào?
Bạn sẽ đo consumer lag, tỷ lệ retry, dead-letter count và thời gian hoàn tất nghiệp vụ để phát hiện sự cố ra sao?
Bạn dùng correlation ID và distributed tracing để tái dựng một hành trình xử lý bất đồng bộ qua nhiều dịch vụ như thế nào?
Bạn xây dựng contract test giữa producer và consumer để phát hiện sự kiện thay đổi không tương thích ra sao?
Bạn kiểm thử transactional outbox và consumer trong tình huống crash ở từng thời điểm của quá trình commit như thế nào?
Bạn xác định chính sách lưu giữ, phát lại và xóa sự kiện có dữ liệu cá nhân theo yêu cầu nghiệp vụ như thế nào?
Khi chuyển từ tích hợp đồng bộ sang kiến trúc hướng sự kiện, bạn sẽ di chuyển từng luồng và đối soát kết quả ra sao?
Bạn đánh giá có nên dùng kiến trúc hướng sự kiện cho một luồng đơn giản dựa trên chi phí broker, debugging và độ trễ nhất quán như thế nào?

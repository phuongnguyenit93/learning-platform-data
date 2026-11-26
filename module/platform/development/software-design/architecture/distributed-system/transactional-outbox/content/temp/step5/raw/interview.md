Khi một dịch vụ phải vừa lưu đơn hàng vừa phát sự kiện, tình huống lỗi nào khiến hai thao tác ghi độc lập trở nên không nhất quán?
Bạn sẽ giải thích vì sao Transactional Outbox giải quyết bài toán dual write mà không cần một giao dịch phân tán như thế nào?
Bạn sẽ xác định ranh giới giao dịch cục bộ để thay đổi nghiệp vụ và bản ghi outbox cùng commit hoặc rollback ra sao?
Nếu giao dịch tạo đơn hàng thất bại sau khi chuẩn bị sự kiện, kết quả mong đợi của bảng outbox là gì và bạn sẽ kiểm chứng thế nào?
Bạn sẽ thiết kế một bản ghi outbox gồm định danh, loại sự kiện, payload và metadata theo tiêu chí nào?
Bạn sẽ lựa chọn định danh duy nhất cho sự kiện sao cho bên nhận có thể phát hiện thông điệp được gửi lại như thế nào?
Vì sao nội dung outbox cần đại diện cho sự kiện nghiệp vụ đã được xác nhận thay vì trạng thái chưa commit?
Bạn sẽ quyết định lưu payload dưới dạng JSON hay các cột có cấu trúc dựa trên yêu cầu truy vấn và tiến hóa schema ra sao?
Bạn sẽ cân nhắc việc giữ phiên bản schema sự kiện ngay trong bản ghi outbox như thế nào?
Khi một giao dịch thay đổi nhiều aggregate, bạn sẽ xác định số lượng và thứ tự sự kiện phải ghi vào outbox ra sao?
Bạn sẽ so sánh polling publisher và Change Data Capture theo độ trễ, chi phí cơ sở dữ liệu và độ phức tạp vận hành như thế nào?
Một relay dùng polling sẽ chọn những bản ghi chưa gửi bằng điều kiện nào để không bỏ sót sự kiện?
Khi có nhiều relay polling chạy đồng thời, bạn sẽ tổ chức claim hoặc khóa bản ghi để giảm việc cùng xử lý một dòng ra sao?
Bạn sẽ lựa chọn kích thước batch và tần suất polling để cân bằng độ trễ công bố với tải lên cơ sở dữ liệu như thế nào?
Nếu relay bị dừng ngay sau khi gửi thông điệp nhưng trước khi đánh dấu đã gửi, hệ thống nên phục hồi theo cơ chế nào?
Vì sao Transactional Outbox không tự bảo đảm người tiêu thụ chỉ nhận đúng một bản sao của sự kiện?
Bạn sẽ thiết kế consumer idempotent để tránh ghi đè hoặc cộng trùng dữ liệu khi broker phát lại thông điệp ra sao?
Bạn sẽ đặt việc ghi nhận ID sự kiện đã xử lý trong cùng giao dịch với cập nhật nghiệp vụ phía consumer như thế nào?
Khi consumer nhận hai lần cùng một ID sự kiện với payload khác nhau, bạn sẽ phát hiện và xử lý bất thường này ra sao?
Bạn sẽ sử dụng khóa aggregate và số thứ tự phiên bản thế nào để bảo vệ thứ tự cập nhật của cùng một đối tượng?
Khi nhiều giao dịch trên cùng aggregate commit liên tiếp, bạn sẽ xác định thứ tự cần bảo toàn tại relay dựa trên yếu tố nào?
Bạn sẽ phân biệt yêu cầu giữ thứ tự toàn cục với giữ thứ tự theo từng aggregate và đánh đổi thông lượng ra sao?
Khi broker phân vùng thông điệp, bạn sẽ chọn partition key nào để những sự kiện liên quan đến cùng thực thể giữ được trật tự?
Nếu một sự kiện đến consumer trước sự kiện tiền nhiệm, bạn sẽ thiết kế cách trì hoãn, kiểm tra phiên bản hoặc đồng bộ lại như thế nào?
Bạn sẽ so sánh cách relay đánh dấu trạng thái đã gửi với cách xóa bản ghi sau công bố về tính an toàn và khả năng truy vết ra sao?
Bạn sẽ xây dựng cơ chế retry với backoff cho relay khi broker tạm thời không khả dụng như thế nào?
Khi một payload lỗi khiến relay luôn thất bại, bạn sẽ phân biệt lỗi dữ liệu cố định với lỗi hạ tầng tạm thời ra sao?
Bạn sẽ thiết kế nơi lưu sự kiện độc hại hoặc hàng đợi lỗi để vận hành có thể sửa và phát lại mà không chặn cả pipeline như thế nào?
Bạn sẽ giải thích cơ chế CDC đọc nhật ký thay đổi của cơ sở dữ liệu khác với việc truy vấn bảng outbox theo chu kỳ ra sao?
Khi sử dụng Debezium làm nguồn CDC, bạn sẽ xác định nguồn bảng, cấu trúc sự kiện và đường đi đến broker như thế nào?
Bạn sẽ xử lý giai đoạn khởi tạo CDC để dữ liệu lịch sử và sự kiện mới không bị thiếu hoặc phát trùng ngoài dự kiến ra sao?
Khi connector CDC khởi động lại từ offset cũ, bạn sẽ kiểm tra khả năng phát lại và tính đúng của consumer như thế nào?
Bạn sẽ xác định ảnh hưởng của thời gian giữ transaction log hoặc WAL đối với connector CDC bị ngừng lâu như thế nào?
Khi thay đổi schema bảng outbox, bạn sẽ lập kế hoạch tương thích cho relay polling và connector CDC đang chạy ra sao?
Bạn sẽ xác định cách giám sát độ trễ từ lúc giao dịch commit đến lúc sự kiện thực sự xuất hiện ở broker như thế nào?
Những số liệu nào cho thấy backlog outbox đang tăng, relay bị kẹt hoặc tốc độ gửi thấp hơn tốc độ tạo sự kiện?
Bạn sẽ phân biệt lỗi không ghi được outbox với lỗi relay không xuất bản được thông điệp thông qua những tín hiệu nào?
Khi số bản ghi outbox tăng lên rất lớn, bạn sẽ thiết kế chỉ mục và chiến lược phân vùng để không làm chậm giao dịch nghiệp vụ ra sao?
Bạn sẽ lựa chọn chính sách lưu giữ và dọn bản ghi đã xử lý mà không xóa nhầm sự kiện chưa được công bố như thế nào?
Khi cần phát lại một khoảng sự kiện để sửa dữ liệu phía consumer, bạn sẽ ngăn tác động nghiệp vụ bị thực thi trùng ra sao?
Bạn sẽ kiểm soát tính riêng tư của thông tin trong payload và thời hạn lưu dữ liệu sự kiện ở bảng outbox như thế nào?
Bạn sẽ thiết kế correlation ID và trace ID thế nào để truy vết từ HTTP request, giao dịch database đến thông điệp broker?
Trong quá trình triển khai nhiều phiên bản dịch vụ cùng lúc, bạn sẽ kiểm tra khả năng đọc schema sự kiện cũ và mới ra sao?
Bạn sẽ xây dựng kiểm thử tích hợp chứng minh rằng bản ghi nghiệp vụ và outbox được commit nguyên tử như thế nào?
Bạn sẽ thực hiện fault injection ở thời điểm ngay trước và sau bước publish để kiểm tra không mất sự kiện bằng cách nào?
Bạn sẽ kiểm thử hai relay đồng thời trên một tập outbox để phát hiện điều kiện tranh chấp và ghi nhận trùng ra sao?
Bạn sẽ xác minh thứ tự sự kiện dưới tải cao và nhiều phân vùng broker bằng loại dữ liệu thử nghiệm nào?
Khi cần chuyển từ polling sang CDC mà hệ thống vẫn đang hoạt động, bạn sẽ xây dựng giai đoạn chuyển tiếp không bỏ sót sự kiện như thế nào?
Bạn sẽ đánh giá chi phí vận hành của Transactional Outbox so với gọi trực tiếp broker trong trường hợp nghiệp vụ chấp nhận mất sự kiện như thế nào?
Khi phát hiện đơn hàng đã lưu nhưng không có sự kiện tương ứng ở hệ thống nhận, bạn sẽ điều tra chuỗi giao dịch, outbox, relay và consumer theo thứ tự nào?

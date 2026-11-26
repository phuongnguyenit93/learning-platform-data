Trong quy trình đặt hàng qua nhiều dịch vụ, những dấu hiệu nào cho thấy cần Saga thay vì một giao dịch cơ sở dữ liệu đơn lẻ?
Bạn sẽ mô tả ranh giới của từng giao dịch cục bộ trong một Saga đặt hàng, giữ hàng và thu tiền như thế nào?
Vì sao Saga không bảo đảm tính nguyên tử theo cách của một giao dịch ACID xuyên nhiều dịch vụ?
Bạn sẽ xác định những bước nghiệp vụ nào cần hành động bù trừ và những bước nào không thể đảo ngược hoàn toàn ra sao?
Khi thao tác hoàn tiền không thể khôi phục chính xác trạng thái trước đó, bạn sẽ thiết kế bù trừ theo ngữ nghĩa nghiệp vụ như thế nào?
Bạn sẽ so sánh choreography và orchestration theo mức độ phụ thuộc, khả năng quan sát và độ phức tạp điều phối ra sao?
Trong trường hợp nào một Saga dùng choreography trở nên khó theo dõi khi số dịch vụ tham gia tăng lên?
Bạn sẽ thiết kế trách nhiệm và dữ liệu trạng thái của một orchestrator để không biến nó thành nơi chứa mọi quy tắc nghiệp vụ như thế nào?
Khi chuyển từ choreography sang orchestration, bạn sẽ bảo toàn hợp đồng giữa các dịch vụ và tiến trình đang chạy ra sao?
Bạn sẽ lựa chọn cơ chế giao tiếp dựa trên command hoặc event cho các bước Saga dựa vào mục đích nghiệp vụ nào?
Trong một Saga, bạn sẽ đặt định danh tương quan ở đâu để liên kết mọi thông điệp với cùng một tiến trình?
Bạn sẽ thiết kế trạng thái chờ, thành công, thất bại và đang bù trừ để một Saga có thể tiếp tục sau khi tiến trình khởi động lại như thế nào?
Khi một bước đã commit giao dịch cục bộ nhưng sự kiện xác nhận chưa được gửi đi, bạn sẽ phát hiện và phục hồi trạng thái đó ra sao?
Bạn sẽ phối hợp ghi dữ liệu nghiệp vụ và thông điệp cần phát trong một bước Saga để tránh mất thông điệp như thế nào?
Khi message broker giao lại cùng một thông điệp, bạn sẽ thiết kế idempotency cho bước xử lý thế nào để tránh giữ hàng hai lần?
Bạn sẽ lưu kết quả xử lý theo khóa idempotency và xác định thời gian giữ khóa dựa trên những điều kiện nào?
Một bước Saga bị timeout nhưng thực tế đã hoàn tất ở dịch vụ đích, bạn sẽ xác minh trạng thái trước khi thử lại như thế nào?
Bạn sẽ phân biệt lỗi tạm thời đáng retry với lỗi nghiệp vụ phải bắt đầu bù trừ bằng tiêu chí nào?
Bạn sẽ chọn giới hạn số lần thử lại, khoảng chờ và backoff sao cho không tạo bão yêu cầu vào dịch vụ đang lỗi ra sao?
Khi bù trừ cũng thất bại, bạn sẽ thiết kế hàng đợi xử lý lại và cơ chế can thiệp vận hành như thế nào?
Bạn sẽ xác định thứ tự bù trừ khi các bước Saga có quan hệ phụ thuộc dữ liệu ra sao?
Nếu hai bước có thể thực hiện song song, bạn sẽ cân nhắc cách đồng bộ kết quả và bù trừ từng nhánh như thế nào?
Khi một sự kiện đến không đúng thứ tự, bạn sẽ ngăn trạng thái Saga quay về bước cũ bằng cơ chế nào?
Bạn sẽ xử lý thông điệp đến muộn sau khi Saga đã kết thúc hoặc bị hủy như thế nào?
Trong luồng thanh toán, bạn sẽ thiết kế chống thực hiện trùng giữa lệnh thu tiền và lệnh hoàn tiền ra sao?
Khi người dùng hủy đơn đúng lúc bước giao hàng bắt đầu, bạn sẽ giải quyết cạnh tranh giữa hai tiến trình nghiệp vụ như thế nào?
Bạn sẽ xác định mức độ cô lập cần thiết khi hai Saga đồng thời cùng đặt giữ một tài nguyên khan hiếm ra sao?
Bạn sẽ giải thích tình huống dirty read hoặc lost update có thể xuất hiện giữa các Saga và cách giảm rủi ro như thế nào?
Bạn sẽ áp dụng semantic lock hoặc trạng thái tạm giữ để ngăn thao tác khác can thiệp giữa chừng ra sao?
Khi một Saga sử dụng bước có tác dụng ngoài hệ thống như gửi email, bạn sẽ tránh gửi thông báo sai trước khi kết quả cuối cùng chắc chắn như thế nào?
Bạn sẽ thiết kế các bước pivot và retryable trong tiến trình có những hành động không thể bù trừ như thế nào?
Khi dịch vụ tham gia đổi schema sự kiện, bạn sẽ kiểm soát khả năng tương thích với các Saga đang dở dang ra sao?
Bạn sẽ xác định tổng thời hạn xử lý Saga và thời hạn của từng bước dựa trên cam kết trải nghiệm người dùng như thế nào?
Sau khi hết thời hạn, bạn sẽ phân biệt Saga cần bù trừ ngay với Saga được phép tiếp tục chờ như thế nào?
Bạn sẽ thiết kế API để người dùng biết giao dịch đang xử lý thay vì nhầm trạng thái trung gian là thành công cuối cùng ra sao?
Khi các màn hình đọc từ nhiều dịch vụ, bạn sẽ trình bày trạng thái nhất quán cuối cùng mà không đánh lừa người dùng như thế nào?
Bạn sẽ xác định những bất biến nghiệp vụ nào phải được giữ tức thời và bất biến nào chấp nhận nhất quán cuối cùng ra sao?
Bạn sẽ xây dựng bảng trạng thái hoặc lịch sử sự kiện để có thể tái dựng tiến trình Saga sau lỗi như thế nào?
Khi orchestrator gặp sự cố trong lúc phát command, bạn sẽ làm gì để tránh phát trùng hoặc bỏ sót bước khi hồi phục?
Bạn sẽ thiết kế correlation ID, trace ID và log theo bước để lần theo một Saga xuyên nhiều dịch vụ ra sao?
Những chỉ số nào giúp phát hiện Saga bị kẹt, bù trừ lặp lại hoặc thời gian hoàn thành tăng bất thường?
Bạn sẽ tổ chức cảnh báo và trang quản trị cho các Saga cần can thiệp thủ công mà vẫn tránh thao tác lặp gây hỏng dữ liệu như thế nào?
Bạn sẽ tạo test cho trường hợp mỗi bước trong Saga thất bại lần lượt và đánh giá kết quả bù trừ như thế nào?
Bạn sẽ dùng giả lập mạng hoặc dịch vụ để kiểm thử thông điệp trùng, mất kết nối và phản hồi muộn trong Saga ra sao?
Làm thế nào để kiểm tra cơ chế khôi phục khi process bị dừng ngay sau commit nhưng trước khi ghi nhận hoàn tất bước?
Bạn sẽ thiết kế thử nghiệm lỗi phối hợp khi hai dịch vụ cùng lỗi để xác minh tiến trình không rơi vào trạng thái không thể phục hồi ra sao?
Khi một Saga kéo dài nhiều ngày, bạn sẽ quản lý phiên bản logic, dữ liệu lưu giữ và dọn trạng thái cũ như thế nào?
Bạn sẽ so sánh chi phí vận hành, số bước bù trừ và nhu cầu theo dõi khi chọn giữa Saga và thiết kế nghiệp vụ ít phân tán hơn ra sao?
Bạn sẽ đánh giá tính đúng của một Saga bằng các bất biến cuối cùng nào ngoài việc tất cả bước trả về thành công?
Khi sự cố sản xuất làm hàng trăm Saga mắc kẹt, bạn sẽ xác định thứ tự ưu tiên khôi phục và ngăn tái diễn ra sao?

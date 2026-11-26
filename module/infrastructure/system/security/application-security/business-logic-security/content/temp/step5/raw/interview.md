Bạn giải thích business logic security khác gì với kiểm soát xác thực và kiểm soát đầu vào thông thường như thế nào?
Bạn xác định các quy tắc nghiệp vụ quan trọng cần được bảo vệ trước khi triển khai một tính năng như thế nào?
Bạn mô hình hóa business invariant để hệ thống luôn giữ trạng thái hợp lệ qua mọi luồng API ra sao?
Bạn phân biệt validation ở giao diện với enforcement invariant tại ranh giới tin cậy của backend như thế nào?
Bạn xác định những giả định nghiệp vụ mà kẻ tấn công có thể lợi dụng khi gọi API theo thứ tự hoặc cách thức khác dự kiến ra sao?
Bạn phân tích một luồng nghiệp vụ từ đầu đến cuối để tìm bước có thể bị bỏ qua hoặc thực hiện sai thứ tự như thế nào?
Bạn thiết kế state machine để chỉ cho phép các chuyển trạng thái hợp lệ của một đơn hàng hoặc yêu cầu phê duyệt ra sao?
Bạn xác định cách ngăn client tự gửi trạng thái đích để bỏ qua bước kiểm tra chuyển trạng thái như thế nào?
Bạn kiểm tra quyền thực hiện từng transition thay vì chỉ kiểm tra quyền truy cập endpoint ra sao?
Bạn phân biệt trạng thái hiện tại, trạng thái mong muốn và điều kiện cho phép chuyển trạng thái trong một workflow như thế nào?
Bạn xử lý một request chuyển đơn hàng trực tiếp từ Draft sang Approved dù quy trình yêu cầu Review như thế nào?
Bạn thiết kế cơ chế chống sửa hoặc gọi lại một transition đã hoàn tất để tránh thực hiện nghiệp vụ hai lần ra sao?
Bạn xác định những invariant nào phải được kiểm tra lại trong transaction ngay trước khi ghi thay đổi như thế nào?
Bạn đánh giá nguy cơ một invariant chỉ được kiểm tra ở tầng service nhưng bị bỏ qua ở một đường gọi khác ra sao?
Bạn tổ chức logic nghiệp vụ dùng chung để các API, job nền và message consumer không áp dụng quy tắc khác nhau như thế nào?
Bạn thiết kế quyền theo đối tượng để người dùng chỉ xem hoặc sửa tài nguyên thuộc phạm vi được phép ra sao?
Bạn phân biệt kiểm tra quyền theo role với kiểm tra quyền theo chủ sở hữu, tenant và quan hệ nghiệp vụ như thế nào?
Bạn ngăn IDOR khi API nhận object ID từ client nhưng không kiểm tra quyền trên chính đối tượng đó ra sao?
Bạn xử lý trường hợp người dùng có quyền xem đơn hàng nhưng không có quyền thay đổi giá hoặc trạng thái của đơn như thế nào?
Bạn thiết kế kiểm soát quyền theo từng thuộc tính để tránh mass assignment hoặc sửa field nhạy cảm ngoài ý muốn ra sao?
Bạn xác định những trường dữ liệu nào phải do server tính hoặc quyết định thay vì tin giá trị client gửi lên như thế nào?
Bạn kiểm tra quyền trên toàn bộ tập đối tượng trong bulk operation thay vì chỉ kiểm tra quyền đối với request tổng thể ra sao?
Bạn ngăn người dùng truy cập tài nguyên thuộc tenant khác khi ID hợp lệ nhưng tenant context không khớp như thế nào?
Bạn xác định cách xử lý quyền khi người dùng bị thu hồi vai trò trong lúc một workflow đang chờ phê duyệt ra sao?
Bạn đánh giá rủi ro confused deputy khi backend dùng quyền service account rộng để thực hiện hành động thay mặt người dùng như thế nào?
Bạn kiểm soát việc một người dùng tự phê duyệt yêu cầu do chính mình tạo ra dựa trên quy tắc phân tách nhiệm vụ ra sao?
Bạn thiết kế chính sách maker-checker hoặc dual control để các giao dịch có rủi ro cao cần nhiều người độc lập phê duyệt như thế nào?
Bạn ngăn việc thay đổi dữ liệu sau phê duyệt làm vô hiệu ý nghĩa của quyết định đã được đưa ra ra sao?
Bạn xác định những trường nào phải được đóng băng hoặc phê duyệt lại khi nội dung yêu cầu thay đổi như thế nào?
Bạn thiết kế audit trail để ghi nhận ai tạo, sửa, duyệt, từ chối và thực thi một hành động nghiệp vụ ra sao?
Bạn bảo đảm audit record không thể bị người dùng thông thường sửa hoặc xóa cùng giao dịch nghiệp vụ như thế nào?
Bạn phân biệt quyền phê duyệt với quyền thực thi sau phê duyệt trong quy trình có nhiều vai trò ra sao?
Bạn phát hiện việc lạm dụng quyền hợp lệ bằng chuỗi hành động riêng lẻ đều qua kiểm tra nhưng tổng thể vi phạm chính sách như thế nào?
Bạn xác định những giới hạn số lượng, giá trị, tần suất hoặc hạn mức cần enforce ở server ra sao?
Bạn ngăn người dùng sửa giá sản phẩm, phí vận chuyển hoặc thuế bằng cách gửi lại tổng tiền tự tính từ client như thế nào?
Bạn thiết kế kiểm tra giá tại thời điểm đặt hàng để tránh client dùng giá cũ hoặc giá đã bị thay đổi như thế nào?
Bạn xử lý coupon hoặc promotion bị áp dụng nhiều lần, kết hợp sai điều kiện hoặc vượt hạn mức ra sao?
Bạn xác định cách giới hạn số lần sử dụng khuyến mãi đồng thời để không vượt quota như thế nào?
Bạn bảo vệ tồn kho khi nhiều người mua cùng mặt hàng và tổng số lượng đặt vượt số lượng khả dụng ra sao?
Bạn thiết kế reservation và release inventory để xử lý thanh toán thất bại mà không bán vượt tồn kho như thế nào?
Bạn phân tích race condition khi hai request cùng đọc một số dư rồi cùng thực hiện giao dịch rút tiền như thế nào?
Bạn lựa chọn optimistic locking, pessimistic locking hoặc atomic update để bảo vệ invariant về số dư và số lượng như thế nào?
Bạn xác định nguy cơ TOCTOU khi quyền hoặc trạng thái đối tượng thay đổi giữa bước kiểm tra và bước cập nhật ra sao?
Bạn ngăn việc dùng lại dữ liệu kiểm tra cũ khi thực hiện thao tác nhạy cảm trong một transaction khác như thế nào?
Bạn thiết kế giới hạn rút tiền hoặc chuyển tiền theo cả từng giao dịch và tổng hạn mức trong một khoảng thời gian ra sao?
Bạn bảo đảm phép tính tiền tệ dùng kiểu dữ liệu và quy tắc làm tròn nhất quán để tránh lợi dụng sai số như thế nào?
Bạn xác định cách kiểm soát thay đổi currency, exchange rate và rounding mode để không làm sai giá trị giao dịch ra sao?
Bạn xử lý yêu cầu hủy hoặc hoàn tiền sau khi một phần nghiệp vụ đã được thực hiện như thế nào?
Bạn phân biệt thao tác bù trừ nghiệp vụ với rollback database khi quy trình đã phát sinh tác động bên ngoài ra sao?
Bạn xác định transaction boundary bao phủ những thay đổi nào để invariant không bị phá vỡ khi lỗi xảy ra giữa chừng như thế nào?
Bạn thiết kế transaction isolation hoặc constraint database để ngăn hai giao dịch đồng thời cùng vượt một hạn mức ra sao?
Bạn đánh giá khi nào cần unique constraint hoặc conditional update thay vì chỉ kiểm tra bằng code ứng dụng như thế nào?
Bạn xử lý deadlock hoặc serialization failure bằng retry có kiểm soát mà không lặp tác động nghiệp vụ ra sao?
Bạn thiết kế idempotency key cho thao tác tạo đơn hàng hoặc thanh toán để retry không tạo giao dịch trùng như thế nào?
Bạn xác định phạm vi, thời hạn lưu và cách ràng buộc idempotency key với người dùng cùng payload ra sao?
Bạn xử lý trường hợp cùng idempotency key được gửi lại với payload khác nội dung ban đầu như thế nào?
Bạn bảo đảm hai request đồng thời dùng cùng idempotency key không cùng thực thi nghiệp vụ như thế nào?
Bạn phân biệt idempotency của HTTP method với idempotency của nghiệp vụ thực tế như thế nào?
Bạn thiết kế cơ chế chống replay cho yêu cầu chuyển tiền hoặc phê duyệt có giá trị nhạy cảm ra sao?
Bạn xử lý webhook hoặc message giao đến nhiều lần mà vẫn bảo đảm một tác động nghiệp vụ duy nhất như thế nào?
Bạn phối hợp transaction database với message publishing bằng transactional outbox để tránh trạng thái cập nhật nhưng sự kiện không được gửi ra sao?
Bạn bảo vệ consumer bằng inbox hoặc deduplication record khi broker có thể redeliver message như thế nào?
Bạn xác định thứ tự xử lý message khi các sự kiện thay đổi trạng thái của cùng một đối tượng đến không đúng thứ tự ra sao?
Bạn thiết kế version hoặc sequence number để phát hiện sự kiện cũ và ngăn ghi đè trạng thái mới như thế nào?
Bạn xử lý workflow kéo dài qua nhiều service khi không thể dùng một transaction phân tán duy nhất ra sao?
Bạn phân biệt saga compensation với rollback và xác định giới hạn của hành động bù trừ như thế nào?
Bạn ngăn client gọi lại bước hoàn tất hoặc bước xác nhận của saga khi quy trình đã kết thúc ra sao?
Bạn kiểm tra tính toàn vẹn của workflow khi một service downstream thành công nhưng service tiếp theo timeout như thế nào?
Bạn thiết kế expiry và cleanup cho trạng thái pending để yêu cầu không bị treo hoặc được sử dụng lại sau thời gian dài ra sao?
Bạn phát hiện lạm dụng logic qua các chuỗi thao tác hợp lệ như tạo nhiều tài khoản, chia nhỏ giao dịch hoặc luân phiên coupon như thế nào?
Bạn xác định ngưỡng và quy tắc phát hiện hành vi bất thường mà không chặn nhầm hoạt động hợp lệ ra sao?
Bạn thiết kế kiểm thử adversarial cho việc bỏ qua phê duyệt, sửa giá, thao tác sai quyền và gửi request trùng như thế nào?
Bạn xây dựng test cho state transition bao gồm trạng thái hợp lệ, trạng thái không hợp lệ và các lần gọi lặp ra sao?
Bạn kiểm thử race condition bằng cách đồng bộ nhiều request cùng tác động lên một invariant như thế nào?
Bạn xác minh test concurrency thực sự tạo ra tranh chấp thay vì chỉ gửi request tuần tự như thế nào?
Bạn thiết kế property-based hoặc model-based tests để kiểm tra invariant trên nhiều chuỗi hành động nghiệp vụ ra sao?
Bạn kiểm thử quyền theo đối tượng với các tổ hợp owner, tenant, role và trạng thái khác nhau như thế nào?
Bạn xây dựng regression test cho lỗi logic đã từng cho phép người dùng vượt qua giới hạn nghiệp vụ ra sao?
Bạn kiểm tra audit trail và idempotency record cùng kết quả giao dịch sau các tình huống timeout, retry và rollback như thế nào?
Bạn thiết kế security test cho API bulk, batch job và message consumer để không bỏ sót các đường thực thi ngoài HTTP ra sao?
Bạn sử dụng threat modeling để xác định tài sản, tác nhân, mục tiêu và abuse case của một workflow như thế nào?
Bạn đánh giá một business rule có thể bị vô hiệu hóa bởi feature flag, cấu hình hoặc luồng quản trị nào ra sao?
Bạn kiểm soát thay đổi rule và quyền quản trị để không thể tự ý nới hạn mức hoặc bỏ bước phê duyệt như thế nào?
Bạn xây dựng cảnh báo và báo cáo audit để phát hiện dấu hiệu lạm dụng logic sau khi tính năng đã triển khai như thế nào?
Bạn xác định bằng chứng cần có để chứng minh một lỗ hổng business logic đã được khắc phục và không tái xuất hiện như thế nào?

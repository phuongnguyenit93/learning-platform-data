Một đơn hàng trực tuyến đã được dịch vụ Kho giữ sản phẩm và dịch vụ Thanh toán trừ tiền, nhưng dịch vụ Vận chuyển không tạo được vận đơn; khách hàng vẫn nhìn thấy đơn đã xác nhận dù chuỗi giao dịch chưa hoàn tất.
Trong nền tảng đặt phòng, dịch vụ Phòng xác nhận giữ chỗ thành công nhưng bước thanh toán thất bại; một số phòng vẫn bị đánh dấu hết chỗ sau khi yêu cầu đặt phòng bị hủy.
Hệ thống du lịch cần đồng thời đặt vé máy bay, khách sạn và xe đưa đón; bước đặt khách sạn từ chối sau khi vé máy bay đã phát hành với điều kiện không hoàn tiền.
Đội bán lẻ thiết kế giao dịch nhiều dịch vụ theo kiểu choreography; khi thêm bước kiểm tra chống gian lận, ba nhóm không thống nhất sự kiện nào kích hoạt bước mới và khi nào đơn thực sự hoàn tất.
Ứng dụng bảo hiểm dùng một bộ điều phối Saga để cấp hợp đồng, tạo kỳ phí và gửi chứng nhận; tiến trình bị dừng sau bước tạo kỳ phí nhưng trước khi lưu kết quả bước đó.
Một Saga đổi gói thuê bao cần cập nhật quyền truy cập rồi thu khoản chênh lệch; yêu cầu hoàn tác chỉ phát sinh sau khi người dùng đã sử dụng một tính năng thuộc gói mới.
Trong hệ thống tuyển sinh, ứng viên được cấp mã sinh viên và tài khoản học tập trước khi bước kiểm tra hồ sơ thất bại; hai dịch vụ tiếp tục hiển thị trạng thái đã kích hoạt.
Đơn đặt hàng đã đi qua bước trừ điểm thưởng và ghi nhận thanh toán, nhưng dịch vụ kiểm tra hạn mức không chấp thuận; số điểm trả lại khác số điểm đã trừ do chương trình khuyến mãi vừa kết thúc.
Dịch vụ giữ chỗ gửi thông báo hoàn tất rồi một bước phía sau cần bù trừ; khách hàng nhận email xác nhận trong khi màn hình ứng dụng cuối cùng hiển thị yêu cầu thất bại.
Một luồng hoàn tiền chạy qua thanh toán, điểm thưởng và kế toán; tác vụ bù trừ của điểm thưởng cũng báo lỗi, khiến Saga rơi vào trạng thái vừa không hoàn tất vừa chưa khôi phục được.
Nhóm triển khai choreography cho đơn hàng nhưng sự kiện OrderCancelled lại kích hoạt cả bộ hoàn kho và bộ gửi hàng do hai consumer diễn giải trạng thái theo cách khác nhau.
Trong orchestration, bộ điều phối gửi lệnh trừ tiền hai lần vì không nhận được phản hồi lần đầu; cổng thanh toán vẫn ghi nhận đủ cả hai lệnh trong khi Saga chỉ mong một khoản thu.
Dịch vụ vận chuyển hoàn tất lệnh tạo vận đơn nhưng thông điệp kết quả bị mất; Saga hết thời gian chờ và bắt đầu hoàn tác mặc dù vận đơn đã tồn tại ở đối tác.
Hệ thống thương mại sử dụng hàng đợi phát sự kiện ít nhất một lần; sau khi consumer khởi động lại, cùng sự kiện PaymentApproved được xử lý thêm lần nữa và tạo hai bước giao hàng.
Trong một Saga đặt vé, thông điệp xác nhận ghế tới chậm hơn thông điệp yêu cầu hủy; dịch vụ Ghế áp dụng xác nhận sau khi đã giải phóng ghế cho người khác.
Một quy trình mua hàng nhận hai yêu cầu hủy đồng thời từ người dùng và nhân viên hỗ trợ; các nhánh bù trừ cùng khởi động và mỗi nhánh đều đòi hoàn cùng khoản tiền.
Đội kỹ thuật thiết kế retry vô hạn cho bước tạo tài khoản đối tác; khi đối tác bị lỗi nhiều giờ, hàng nghìn Saga giữ trạng thái chờ và không tiến tới kết quả cuối.
Dịch vụ Thanh toán trả HTTP timeout nhưng giao dịch thực tế đã được chấp thuận; bộ điều phối không phân biệt kết quả chưa biết với kết quả thất bại khi quyết định bù trừ.
Trong chương trình đổi điểm lấy quà, quyền nhận quà hết hạn sau 15 phút; chuỗi Saga xử lý quá lâu khiến bước cuối thành công kỹ thuật nhưng vi phạm giới hạn thời gian nghiệp vụ.
Một hệ thống đặt lịch khám phân tán phải giữ chỗ bác sĩ và phòng thiết bị; hai Saga khác nhau cùng chọn một phòng trống và đều thông báo đã giữ trước khi đồng bộ trạng thái.
Ứng dụng đặt hàng cho phép chỉnh sửa địa chỉ khi Saga đang ở bước tạo vận đơn; địa chỉ mới được lưu nhưng bước vận chuyển nhận bản địa chỉ cũ từ thông điệp trước đó.
Trong luồng gia hạn thuê bao, sự kiện hoàn tiền đến sau sự kiện gia hạn thành công; dashboard hiển thị thuê bao còn hiệu lực mặc dù số dư đã được hoàn trả.
Một đơn hàng có ba mặt hàng từ hai kho; kho thứ nhất giữ được toàn bộ phần của mình nhưng kho thứ hai chỉ giữ được một sản phẩm, khiến bộ điều phối khó xác định trạng thái đơn hàng khi thiếu một phần.
Nhóm sản phẩm cho phép giao hàng một phần thay vì hủy toàn bộ; Saga cũ giả định mọi bước phải cùng thành công hoặc cùng bù trừ nên xử lý sai các đơn có nhiều kiện.
Trong quy trình mở tài khoản ngân hàng, bước gửi thông báo pháp lý qua đối tác đã hoàn thành; khi một bước xác minh sau đó lỗi, nhóm chưa thống nhất liệu thông báo đã gửi có thể xem là hành động bù trừ được.
Hệ thống bán vé tổ chức sự kiện cần giảm tồn kho và phát mã QR; sau khi khách dùng mã tại cổng, Saga nhận một yêu cầu hoàn vé đến muộn và kích hoạt logic hoàn tác cũ.
Đội triển khai một Saga có hai mươi bước nối tiếp cho đơn vay; bản vận hành không thể xác định bước nào gây thời gian chờ lớn khi khách hàng báo yêu cầu đứng yên.
Trong hệ thống nhiều tenant, hai Saga có cùng mã đơn cục bộ từ hai doanh nghiệp; công cụ theo dõi ghép nhật ký theo mã đơn mà không kèm tenant và hiển thị sai chuỗi giao dịch.
Bộ điều phối Saga được triển khai nhiều instance để chịu tải; sau một đợt failover, hai instance cùng tiếp tục một tiến trình đang chờ và phát lệnh bước kế tiếp hai lần.
Ứng dụng gửi thông điệp tiếp tục Saga rồi ghi trạng thái đã gửi vào cơ sở dữ liệu khác; tiến trình chết giữa hai thao tác khiến hệ thống lưu tiến độ không khớp với lệnh đã phát.
Trong luồng thanh toán quốc tế, một bước bù trừ hoàn ngoại tệ chịu tỷ giá mới; số tiền hoàn thực tế khác số tiền đã thu ban đầu khiến bộ phận tài chính khó đối soát.
Dịch vụ giao vận hoàn phí bằng API của đối tác, nhưng đối tác chỉ cho phép hủy trong năm phút sau khi tạo; các Saga chậm phải xử lý một bước bù trừ không còn được chấp nhận.
Nhóm đang lựa chọn choreography cho hành trình khách hàng gồm sáu service; mỗi nhóm chỉ biết sự kiện mình tiêu thụ nên không ai có bức tranh toàn bộ tiến độ và tiêu chí kết thúc.
Đội triển khai orchestration tập trung nhưng bộ điều phối không khả dụng trong giờ cao điểm; các service đã hoàn thành giao dịch cục bộ vẫn đợi lệnh tiếp theo và backlog tăng.
Một service phát sự kiện SagaSucceeded trước khi hệ thống báo cáo đọc được mọi cập nhật cục bộ; khách mở trang lịch sử ngay lập tức và thấy các trạng thái của cùng đơn hàng không khớp.
Trong hệ thống đăng ký dịch vụ viễn thông, khách nhấn hủy khi Saga đang ở bước kích hoạt SIM; lệnh hủy và sự kiện kích hoạt thành công tới hai service theo thứ tự khác nhau.
Nhóm kiểm thử chỉ mô phỏng lỗi ở bước đầu của Saga; khi lỗi phát sinh ở bước cuối sau nhiều giao dịch cục bộ, quá trình bù trừ lại bỏ sót một hệ thống đã cập nhật dữ liệu.
Một Saga có bước gửi SMS xác thực và bước trừ phí; để giảm thời gian chạy, nhóm đổi thứ tự hai bước nhưng chưa đánh giá tác động của việc trừ tiền trước khi khách xác thực.
Trong quy trình thay đổi địa chỉ giao hàng, yêu cầu retry sử dụng cùng sagaId nhưng payload địa chỉ đã bị người dùng sửa; service phụ thuộc không thống nhất lần nào là dữ liệu hợp lệ của tiến trình.
Khi kiểm tra sự cố sản xuất, đội vận hành chỉ có log riêng của từng microservice không chứa correlationId và trạng thái bù trừ; cùng một mã thanh toán xuất hiện trong nhiều luồng mà không xác định được tiến trình nào còn mắc kẹt.

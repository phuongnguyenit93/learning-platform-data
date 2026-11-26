Trong ứng dụng đặt hàng Java/Spring, khách nhập số điện thoại bắt đầu bằng 0 ở Việt Nam, nhưng SMS gateway yêu cầu dạng E.164; backend ghép trực tiếp mã +84 khiến nhiều số bị sai định dạng và không nhận tin.
Một hệ thống thương mại điện tử phục vụ nhiều quốc gia chỉ giả định mọi số điện thoại dài mười chữ số; người dùng nước ngoài bị từ chối nhận SMS xác nhận dù số của họ hợp lệ.
Đội hỗ trợ lưu số điện thoại dưới nhiều dạng có khoảng trắng, dấu ngoặc và mã quốc gia; cùng một khách hàng được hệ thống xem là ba người nhận khác nhau khi gửi thông báo.
Trong ứng dụng giao hàng, người dùng đổi số liên lạc sau khi đặt đơn; job gửi SMS trễ vẫn đọc số cũ từ hàng đợi và thông báo địa chỉ nhận hàng tới chủ thuê bao trước.
Một công ty đăng ký nhiều tài khoản dịch vụ SMS theo vùng; backend Java chọn gateway theo tiền tố số điện thoại nhưng một nhóm thuê bao chuyển mạng khiến chính sách định tuyến không còn phù hợp.
Nhóm xây mẫu tin nhắn thông báo giao hàng có mã đơn, tên khách và thời gian dự kiến; tên người nhận quá dài làm nội dung bị chia thành nhiều SMS và chi phí tăng ngoài dự kiến.
Ứng dụng thanh toán gửi SMS có dấu tiếng Việt và emoji; cấu hình mã hóa làm một tin ngắn trở thành nhiều phân đoạn và khách nhận nội dung không hoàn chỉnh trên một số thiết bị.
Đội marketing thay mẫu nội dung SMS nhưng không cập nhật các biến chèn dữ liệu; người dùng nhận tin chứa nguyên chuỗi placeholder thay vì tên hoặc mã đặt chỗ.
Trong hệ thống ngân hàng, mẫu OTP được dùng cả cho đăng nhập và xác nhận chuyển tiền nhưng nội dung không nói rõ hành động nào đang được xác minh; khách khó nhận biết yêu cầu bất thường.
Một ứng dụng đặt lịch gửi tên bệnh nhân và loại dịch vụ y tế trong nội dung SMS; điện thoại bị người khác cầm có thể đọc thông tin cá nhân trên màn hình khóa.
Nhóm lưu OTP và toàn bộ nội dung SMS vào log request để dễ debug; nhân viên có quyền xem log có thể nhìn thấy mã xác thực còn hiệu lực của người dùng.
Ứng dụng xác thực gửi OTP có hiệu lực hai phút nhưng queue bị kẹt năm phút; khi tin đến thiết bị, mã đã hết hạn và người dùng liên tục yêu cầu gửi lại.
Trong hệ thống đăng nhập, người dùng bấm 'Gửi lại mã' liên tiếp; backend tạo nhiều OTP và hàng đợi phân phối không theo thứ tự khiến mã vừa nhận không phải mã mới nhất.
Một hệ thống thay đổi mật khẩu cho phép nhập OTP sai nhiều lần mà không giới hạn theo phiên; những số điện thoại nhận tin bị thử đoán mã liên tục dù mỗi mã có thời gian tồn tại ngắn.
Đội phát triển dùng SMS OTP làm kênh duy nhất để xác nhận chuyển khoản giá trị lớn; khi số điện thoại bị chuyển quyền sử dụng, chủ số mới có nguy cơ nhận mã liên quan tài khoản cũ.
Ứng dụng giao hàng gửi thông báo qua HTTP API của nhà cung cấp SMS; môi trường production vẫn sử dụng thông tin xác thực thử nghiệm nên request bị từ chối sau khi go-live.
Một hệ thống Java/Spring lưu mật khẩu SMPP trong file cấu hình được commit vào repository; sau khi thay nhà cung cấp, các phiên bản cũ vẫn mang thông tin đăng nhập chưa được thu hồi.
Đội tích hợp SMS gateway qua HTTP nhận phản hồi request thành công và ngay lập tức đánh dấu tin đã đến máy người dùng; nhiều người khiếu nại chưa nhận dù nhà cung cấp mới chỉ nhận yêu cầu xử lý.
Trong kết nối SMPP, ứng dụng giữ một phiên gửi lâu dài nhưng không phát hiện phiên đã ngắt sau thay đổi mạng; hàng đợi tiếp tục rút tin và ghi lỗi liên tục trong giờ cao điểm.
Một service gửi SMS bằng nhiều phiên SMPP song song, nhưng kết quả gửi trả về không còn được ghép đúng với từng tin gốc; dashboard hiển thị nhầm mã giao dịch đã thành công.
Ứng dụng gửi SMS thành công qua gateway nhưng delivery receipt đến muộn vài giờ; job tự động thử lại vì chưa thấy trạng thái giao khiến khách nhận cùng tin hai lần.
Đội xử lý delivery receipt nhưng không phân biệt trạng thái chờ, đã giao và không giao được; nhân viên hỗ trợ báo tin đã thất bại trong khi nhà mạng vẫn đang phân phối.
Trong một hệ thống nhiều nhà cung cấp, mỗi SMS gateway trả mã trạng thái theo cách khác nhau; lớp theo dõi gộp tất cả thành SUCCESS và mất thông tin lỗi thực tế của nhà mạng.
Một thông báo quan trọng được gửi trước khi giao dịch database tạo đơn commit; transaction bị rollback nhưng khách vẫn nhận SMS xác nhận một đơn hàng không tồn tại.
Service xử lý queue gửi SMS chết sau khi gateway chấp nhận yêu cầu nhưng trước khi lưu dấu đã gửi; khi worker khởi động lại, cùng tin được phát thêm lần nữa.
Nhóm xây retry cho mọi lỗi SMS gateway mà không phân biệt số điện thoại không hợp lệ, tài khoản hết tiền và lỗi mạng tạm thời; những bản tin không thể gửi chiếm hàng đợi nhiều giờ.
Trong giờ cao điểm thương mại, gateway trả cảnh báo vượt lưu lượng gửi cho phép; worker lập tức retry mọi tin với tốc độ cao khiến lỗi kéo dài và tin OTP đến muộn.
Một hệ thống gửi tin OTP và tin khuyến mãi qua cùng một queue; đợt quảng cáo tạo backlog lớn khiến người dùng đăng nhập phải đợi mã quá thời gian hiệu lực.
Đội triển khai cơ chế chống gửi trùng theo nội dung text; hai khách cùng nhận mẫu 'Đơn đã giao' thì một tin bị loại bỏ dù đó là hai giao dịch độc lập.
Trong ứng dụng bán vé, một mã đơn tạo nhiều sự kiện thay đổi trạng thái; cơ chế chống trùng theo orderId khiến tin 'Đã hoàn tiền' bị bỏ vì trước đó đã gửi tin 'Đã thanh toán'.
Nhà cung cấp SMS chính ngừng phục vụ trong một giờ; service chuyển sang gateway dự phòng nhưng không xác định những tin nào đã được bên chính tiếp nhận nên khách nhận tin trùng khi dịch vụ hồi phục.
Một ứng dụng gửi qua hai gateway có giá khác nhau; cấu hình failover luôn chọn tuyến đắt hơn mỗi khi phản hồi chậm dù nhà cung cấp chính chưa báo thất bại.
Đội vận hành chỉ theo dõi số request API thành công mà không có dữ liệu số phân đoạn SMS, giá theo tuyến và quốc gia; hóa đơn cuối tháng tăng mạnh dù số sự kiện nghiệp vụ không đổi.
Một hệ thống quảng cáo gửi SMS theo lịch chiến dịch tại Việt Nam nhưng máy chủ dùng UTC; hàng nghìn khách nhận tin giữa đêm thay vì khung giờ đã chọn.
Trong ứng dụng thông báo đơn hàng, khách đã rút lại đồng ý nhận SMS quảng cáo nhưng danh sách số nhận chiến dịch vẫn lấy từ dữ liệu cache trước đó; họ tiếp tục nhận thông điệp không mong muốn.
Một chiến dịch SMS có sender ID thương hiệu được duyệt ở thị trường này nhưng chưa hợp lệ ở thị trường khác; nội dung cùng mẫu bị từ chối ở một phần quốc gia mà dashboard không tách nguyên nhân.
Nhóm QA kiểm thử SMS bằng số điện thoại thật của nhân viên và chạy lại suite nhiều lần; hàng trăm tin OTP và cảnh báo thử nghiệm gây chi phí và làm gián đoạn người nhận.
Ứng dụng hỗ trợ dùng môi trường giả lập SMS gateway cho unit test nhưng kiểm thử phát hành không có kịch bản delivery receipt lỗi, chậm hoặc lặp; trạng thái người nhận sai chỉ xuất hiện trong production.
Đội hỗ trợ khách báo không nhận SMS chỉ có số điện thoại và thời điểm ước lượng; hệ thống không lưu messageId, gateway được chọn hoặc lịch sử retry nên không thể truy vết quá trình phân phối.
Trong hệ thống gửi tin theo nhiều quốc gia, backend lấy cùng một mẫu tiếng Việt và áp cho mọi thuê bao; nội dung có dấu bị chia phân đoạn và người nhận ở thị trường khác không hiểu được hành động cần thực hiện.

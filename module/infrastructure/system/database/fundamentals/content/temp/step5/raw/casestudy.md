Một cửa hàng nhỏ dùng nhiều tệp bảng tính để quản lý hàng tồn kho; hai nhân viên cùng sửa số lượng sản phẩm trong ngày khiến số liệu ở các tệp không khớp khi chốt đơn.
Trung tâm đào tạo lưu thông tin học viên trong một bảng duy nhất, lặp lại tên khóa học và giảng viên trên từng dòng đăng ký; khi đổi giảng viên, một số dòng vẫn hiển thị thông tin cũ.
Nhóm xây dựng ứng dụng đặt lịch cần quyết định giữa cơ sở dữ liệu quan hệ và kho tài liệu JSON; lịch hẹn có khách hàng, nhân viên và tài nguyên phòng cần kiểm tra ràng buộc đồng thời.
Ứng dụng ghi log cảm biến tạo hàng triệu sự kiện dạng JSON mỗi ngày, với bộ thuộc tính thay đổi theo thiết bị; nhóm muốn dùng chung mô hình bảng quan hệ như dữ liệu giao dịch thanh toán.
Một đội phát triển lưu mạng lưới bạn bè dưới các cột chuỗi chứa danh sách ID; việc tìm bạn chung nhiều cấp và cập nhật quan hệ hai chiều trở nên phức tạp khi số người dùng tăng.
Công ty có dữ liệu đơn hàng, ảnh sản phẩm và nhật ký truy cập; nhóm hạ tầng muốn đưa toàn bộ vào một hệ quản trị duy nhất nhưng mỗi loại có cách truy vấn và thời gian lưu trữ khác nhau.
Ứng dụng quản lý bệnh viện có bảng bệnh nhân và lịch khám; nhà phát triển lưu tên bệnh nhân trực tiếp trên từng lịch hẹn khiến việc sửa tên không cập nhật nhất quán.
Hệ thống thương mại điện tử cho phép mỗi đơn hàng chứa nhiều sản phẩm và mỗi sản phẩm nằm trong nhiều đơn; nhóm ban đầu đặt một cột danh sách mã sản phẩm trong bảng đơn hàng.
Một công ty cho phép nhân viên tham gia nhiều dự án với vai trò và ngày bắt đầu khác nhau; dữ liệu hiện tại chỉ có bảng nhân viên chứa một cột mã dự án.
Ứng dụng quản lý sách dùng tiêu đề làm khóa chính; hai cuốn sách khác nhau có cùng tiêu đề, và tên sách có thể sửa trong các lần tái bản.
Cửa hàng có nhiều chi nhánh cùng quản lý mã hàng nội bộ; ràng buộc duy nhất chỉ theo mã hàng khiến hai chi nhánh không thể tạo mã giống nhau dù đại diện cho mặt hàng khác nhau.
Một bảng đơn hàng lưu customer_id nhưng không có khóa ngoại; sau khi khách hàng bị xóa bằng công cụ quản trị, báo cáo xuất hiện đơn không tìm được người mua.
Hệ thống đặt vé cho phép giá trị số ghế bằng số âm và ngày trả vé trước ngày đặt; giao diện có kiểm tra đầu vào nhưng dữ liệu sai vẫn xuất hiện từ quá trình nhập hàng loạt.
Ứng dụng cho phép người dùng tạo tài khoản không có email; báo cáo tìm các tài khoản thiếu email lại dùng phép so sánh thông thường với NULL và không tìm thấy đúng số bản ghi.
Cửa hàng lưu số điện thoại dưới dạng số nguyên; một số số điện thoại bắt đầu bằng số 0 bị mất chữ số đầu sau khi nhập dữ liệu.
Dịch vụ tính tiền lưu số tiền bằng kiểu số thực dấu phẩy động; sau khi cộng nhiều khoản thanh toán nhỏ, tổng hiển thị có sai số so với giá trị trong hóa đơn.
Nền tảng đặt phòng phục vụ khách ở nhiều múi giờ; một lịch đặt lúc gần nửa đêm được lưu bằng ngày giờ không kèm thông tin múi giờ, khiến lịch hiển thị lệch khi khách đi công tác.
Một bảng đăng ký môn học dùng khóa ghép gồm mã sinh viên và mã môn; nhóm thêm thuộc tính tên môn vào bảng này và nhận thấy tên có thể không nhất quán giữa các sinh viên.
Thông tin khách hàng gồm mã khách, địa chỉ và khu vực; khi một khu vực đổi tên, nhóm phải sửa hàng nghìn dòng khách hàng và vẫn bỏ sót một số dòng.
Đội sản phẩm gộp tất cả địa chỉ giao hàng vào một cột văn bản tự do; nghiệp vụ mới cần lọc theo tỉnh, quận và mã bưu điện nhưng không thể đối soát dữ liệu nhập thiếu chuẩn.
Nhóm dữ liệu tách bảng sản phẩm thành nhiều bảng liên quan để tránh trùng lặp; màn hình tra cứu thường xuyên cần ghép nhiều bảng và bắt đầu gặp giới hạn độ trễ khi lưu lượng tăng.
Ứng dụng bán hàng sao chép tên và giá sản phẩm vào từng dòng hóa đơn để lưu lịch sử; nhóm mới phụ trách muốn xóa các bản sao dữ liệu vì tưởng rằng tất cả đều là dư thừa.
Nhân viên chăm sóc khách hàng tra cứu số đơn hàng bằng SQL nhưng câu truy vấn không có điều kiện lọc đúng cột; hệ thống trả hàng trăm nghìn dòng khi chỉ cần một đơn.
Màn hình quản lý học viên cần hiển thị cả người chưa đăng ký khóa nào; sau khi dùng phép nối chỉ lấy hàng có cặp tương ứng, những học viên này biến mất khỏi báo cáo.
Báo cáo bán hàng nối đơn hàng với nhiều dòng sản phẩm và nhiều lần thanh toán; số tiền đơn bị cộng nhiều lần vì kết quả JOIN tạo thêm nhiều hàng trung gian.
Hệ thống tính tổng doanh thu theo tháng nhưng báo cáo lọc bản ghi theo điều kiện sau khi đã nhóm dữ liệu; nhóm phát triển nhầm lẫn điều kiện trên từng dòng và điều kiện trên tổng nhóm.
Màn hình danh sách sản phẩm dùng ORDER BY trên cột trạng thái có nhiều giá trị trùng nhau; khi chuyển trang, người dùng thấy một số sản phẩm xuất hiện lặp hoặc mất khỏi vị trí dự kiến.
API lấy danh sách đơn hàng có nút đi đến trang rất xa bằng OFFSET; trên bảng hàng triệu dòng, các trang sau chậm hơn rõ rệt và khách hàng bỏ dở thao tác.
Phòng kế toán muốn tìm khách có tổng chi tiêu cao hơn mức trung bình; truy vấn hiện tại trả sai vì điều kiện lọc được tính trên từng đơn thay vì toàn bộ đơn của từng khách.
Nhóm phát triển xây truy vấn tìm kiếm bằng cách nối chuỗi trực tiếp từ ô nhập tên người dùng; một giá trị chứa dấu nháy làm câu SQL lỗi và phát sinh lo ngại về SQL injection.
Hệ thống nhập file CSV chứa mã khách và ngày giao hàng; có dòng đảo vị trí ngày tháng theo hai định dạng khác nhau khiến dữ liệu sau nhập không đồng nhất với nguồn.
Hai nhân viên cùng điều chỉnh địa chỉ khách hàng; người đầu đọc bản cũ, người thứ hai lưu thay đổi mới, rồi người đầu ghi lại toàn bộ bản ghi và vô tình làm mất cập nhật vừa có.
Dịch vụ ví điện tử ghi giảm số dư tài khoản gửi rồi gặp lỗi khi ghi tăng số dư tài khoản nhận; cơ sở dữ liệu còn một nửa thao tác dù nghiệp vụ phải chuyển tiền nguyên vẹn.
Một tác vụ tạo đơn hàng gồm thêm đơn và nhiều dòng sản phẩm; khi thiếu hàng ở dòng cuối, phần đầu đã được lưu vì ứng dụng tự động commit từng câu SQL.
Ứng dụng chỉ kiểm tra số ghế còn lại trước khi bán, rồi ghi cập nhật bằng câu lệnh riêng; hai khách bấm mua ghế cuối cùng gần như đồng thời và cả hai đều được báo thành công.
Hệ thống xuất báo cáo chạy hai lần SELECT trong cùng một lượt xử lý; giữa hai câu truy vấn có người thêm đơn hàng, làm số liệu tổng và chi tiết trong cùng báo cáo không khớp.
Nhân viên kho mở giao dịch cập nhật nhưng để cửa sổ quản trị chờ lâu; các thao tác ghi khác trên cùng mặt hàng bắt đầu bị treo mặc dù máy chủ cơ sở dữ liệu còn nhiều CPU.
Hai luồng cập nhật tài khoản và đơn hàng theo thứ tự ngược nhau; trong giờ cao điểm xuất hiện deadlock và một giao dịch bị hủy dù các lệnh chạy riêng lẻ đều thành công.
Ứng dụng xử lý thông báo chuyển sang nhiều worker nhưng vẫn chọn công việc bằng cách đọc trạng thái chưa xử lý rồi cập nhật sau; một số thông báo được gửi lặp vì hai worker lấy cùng việc.
Truy vấn kiểm tra một email đã tồn tại chạy chậm dần khi bảng người dùng đạt hàng triệu bản ghi; đội phát triển chưa tạo index trên cột thường được tìm theo điều kiện chính xác.
Ứng dụng có chỉ mục trên cột giới tính với rất ít giá trị khác nhau; nhóm kỳ vọng mọi truy vấn lọc theo cột này đều chạy nhanh nhưng nhiều câu vẫn quét gần hết bảng.
Màn hình xem các đơn giao gần đây lọc theo mã cửa hàng rồi sắp xếp thời gian tạo; sau khi tạo nhiều index đơn cột, tốc độ vẫn kém trong giờ cao điểm.
Bảng sự kiện có nhiều chỉ mục do các nhóm thêm dần; tốc độ tra cứu ổn định nhưng việc ghi một lô dữ liệu lớn trở nên chậm hơn và chiếm thêm dung lượng đĩa.
Người vận hành nhìn thấy một truy vấn chạy lâu nhưng chỉ kiểm tra thời gian phản hồi API; nhóm chưa xem kế hoạch thực thi để biết thời gian nằm ở quét bảng, JOIN hay sắp xếp.
Một ứng dụng mới kết nối tới cơ sở dữ liệu bằng tài khoản quản trị có toàn quyền; khi thông tin đăng nhập bị lộ trong file cấu hình, phạm vi dữ liệu có thể bị thay đổi quá rộng.
Ứng dụng dùng một tài khoản cơ sở dữ liệu để cả đọc báo cáo và cập nhật đơn; nhóm nghiệp vụ yêu cầu phân quyền để nhân viên phân tích không thể sửa dữ liệu sản xuất.
Dịch vụ mở một kết nối cơ sở dữ liệu mới cho từng request HTTP và quên đóng ở nhánh lỗi; khi số người dùng tăng, máy chủ báo hết số kết nối mặc dù mỗi truy vấn rất ngắn.
API đặt hàng bắt đầu lỗi timeout khi số request đồng thời tăng; biểu đồ CPU của máy chủ thấp nhưng có nhiều câu SQL chờ khóa và nhiều request đang đợi kết nối.
Ứng dụng có cấu hình kết nối sử dụng hostname của cơ sở dữ liệu thử nghiệm trong môi trường production; sau lần phát hành, thao tác đọc và ghi đi vào kho dữ liệu sai môi trường.
Một nhóm xây dựng dịch vụ tìm kiếm và hệ thống giao dịch muốn dùng cùng cơ sở dữ liệu; kết quả tìm kiếm chấp nhận cập nhật chậm vài giây trong khi số dư thanh toán phải phản ánh giao dịch mới nhất.
Doanh nghiệp dùng cơ sở dữ liệu quan hệ cho thanh toán và một kho key-value làm bộ nhớ đệm; sau khi cập nhật giá sản phẩm, một số người dùng vẫn thấy giá cũ vì dữ liệu đệm chưa đồng bộ.
Hệ thống phân tán sao chép dữ liệu đọc sang nhiều bản sao; sau khi người dùng cập nhật hồ sơ, request đọc ngay sau đó đôi lúc trả giá trị cũ dù thao tác ghi đã thành công.
Nhóm kinh doanh truy vấn trực tiếp hàng trăm triệu dòng giao dịch trên hệ thống đặt hàng giờ cao điểm; các truy vấn phân tích kéo dài ảnh hưởng đến hoạt động giao dịch thời gian thực.
Quy trình sao lưu cơ sở dữ liệu báo chạy thành công mỗi đêm nhưng chưa từng kiểm thử khôi phục; khi máy chủ lưu trữ gặp sự cố, nhóm không chắc mất bao nhiêu dữ liệu hoặc cần bao lâu để phục hồi.
Bảng lịch sử truy cập tăng nhanh từng ngày khiến dung lượng đĩa còn rất ít; ứng dụng chưa có chính sách thời gian lưu, lưu trữ dữ liệu cũ hoặc cảnh báo mức sử dụng.
Khi dashboard chỉ theo dõi CPU và dung lượng ổ đĩa, người vận hành không thấy xu hướng tăng thời gian truy vấn, số kết nối đang chờ và giao dịch bị lỗi trước khi khách hàng phản ánh.
Nhóm triển khai thay đổi cấu trúc bảng ngay giờ cao điểm mà chưa rà soát ứng dụng phụ thuộc; phiên bản cũ vẫn đọc tên cột trước đó, dẫn tới lỗi sau khi migration hoàn tất.
Một công ty chuẩn bị chuyển dữ liệu khách hàng sang hệ quản trị mới; mẫu dữ liệu thử nghiệm khớp, nhưng dữ liệu thực tế có nhiều giá trị NULL, ký tự Unicode và ràng buộc khác nhau giữa hai hệ thống.

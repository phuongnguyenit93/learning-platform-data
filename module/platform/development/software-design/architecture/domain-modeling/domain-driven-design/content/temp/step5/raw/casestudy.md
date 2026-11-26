Trong công ty thương mại điện tử, nhóm Bán hàng gọi Order là đơn đã được khách xác nhận, còn nhóm Kho dùng Order cho yêu cầu lấy hàng chưa đủ tồn; một báo cáo chung hiển thị hai số lượng đơn không khớp.
Chuyên gia bảo hiểm dùng thuật ngữ hợp đồng có hiệu lực sau khi phí đầu tiên được thu, trong khi lập trình viên định nghĩa trạng thái ACTIVE ngay khi khách ký; màn hình chăm sóc khách hàng phản ánh sai quy tắc nghiệp vụ.
Nhóm phát triển ứng dụng y tế đặt từ Patient cho cả người đăng ký, người được bảo hiểm và người đang điều trị; thay đổi một trường trong lớp Patient gây lỗi ở ba quy trình có cách hiểu khác nhau.
Trong buổi event storming cho dịch vụ giao hàng, nhân viên điều phối nói 'bàn giao kiện' còn lập trình viên dùng sự kiện PackageShipped cho cả lúc kho đóng gói và lúc tài xế nhận; các đội không thống nhất mốc tính SLA.
Đội kinh doanh yêu cầu áp dụng phí hủy khi khách 'đã đặt', nhưng hệ thống có các trạng thái Draft, Reserved và Confirmed; các bên chưa thống nhất thuật ngữ tương ứng với nghĩa vụ thanh toán.
Công ty có các nhóm Định giá, Thanh toán và Chăm sóc khách hàng cùng dùng chữ Discount; cùng một mã ưu đãi mang ý nghĩa khác nhau khi tính giá trước thuế, hoàn tiền và giải thích hóa đơn.
Nhóm logistics đang phân loại năng lực định tuyến giao hàng là tính năng khác biệt cốt lõi, nhưng phần lớn ngân sách lại dành cho việc tự xây dịch vụ gửi email tiêu chuẩn.
Trong dự án ngân hàng số, quy tắc xếp hạng tín dụng thay đổi liên tục theo mô hình rủi ro, còn tính năng quản lý nhân viên ít thay đổi; mọi subdomain đều được xây bằng cùng một mức đầu tư và quy trình thiết kế.
Một ứng dụng đăng ký khóa học tự phát triển hệ thống xác thực danh tính phức tạp dù sản phẩm cạnh tranh bằng thuật toán ghép khóa học với lộ trình cá nhân hóa; nhóm cần xem lại ranh giới giữa năng lực cốt lõi và năng lực phổ thông.
Đội xây siêu ứng dụng gom mua sắm, giao hàng, ví điện tử vào một mô hình Customer khổng lồ; một thay đổi chính sách định danh ví khiến các tính năng mua sắm phải sửa theo.
Trong nền tảng tuyển dụng, bộ phận Đăng tuyển và bộ phận Tuyển chọn cùng dùng JobApplication nhưng hai bên có vòng đời và quy tắc hủy khác nhau; một bảng trạng thái chung ngày càng xuất hiện ngoại lệ.
Nhóm quản lý đơn hàng muốn tách Order Fulfillment khỏi Order Management; hai khu vực có quy tắc thay đổi địa chỉ trái nhau nhưng vẫn cùng cập nhật một entity Order dùng chung.
Dịch vụ thanh toán cần biết khách hàng đã xác minh danh tính hay chưa; đội xây tích hợp đọc trực tiếp bảng của bounded context Định danh thay vì dựa vào một hợp đồng trao đổi được thống nhất.
Trong công ty du lịch, context Đặt phòng dùng BookingId làm định danh, còn context Kế toán dùng InvoiceId; đội phát triển cố ép hai mã thành một khóa chung và làm phức tạp việc đối soát.
Nhóm xây context map cho hệ thống đơn hàng nhưng không xác định dịch vụ nào quyết định ý nghĩa trạng thái PAID; hai nhóm cùng thay đổi schema sự kiện khiến consumer xử lý sai.
Một dịch vụ downstream phải sử dụng API của nhà cung cấp vận chuyển và sao chép nguyên tên trạng thái DELIVERED_TO_HUB vào domain riêng; chính sách vận hành thay đổi theo thuật ngữ đối tác.
Trong quá trình tích hợp phần mềm kế toán cũ, dữ liệu khách hàng chứa trường ACCOUNT_TYPE với ý nghĩa không còn dùng; lớp domain mới giữ nguyên trường này và các quy tắc không liên quan bắt đầu phụ thuộc nó.
Hai đội cần chia sẻ khái niệm Money, nhưng một đội biểu diễn đồng bằng số nguyên VND còn đội khác hỗ trợ ngoại tệ và tỷ giá; module dùng chung được đề xuất trước khi ý nghĩa nghiệp vụ thống nhất.
Đội phát triển một nền tảng nhiều seller cho phép mỗi người bán xác định chính sách hoàn tiền; nhóm áp một quy tắc toàn hệ thống do thiếu phân biệt ranh giới trách nhiệm giữa Marketplace và Seller.
Một hệ thống CRM và hệ thống Billing cùng lưu địa chỉ khách hàng; CRM coi thay đổi địa chỉ có hiệu lực ngay, còn Billing cần địa chỉ tại thời điểm lập hóa đơn và hai bản dữ liệu liên tục bị ghi đè qua lại.
Trong miền ngân hàng, hai tài khoản có cùng số dư và loại tiền nhưng thuộc hai khách khác nhau; đội kỹ thuật coi chúng là hai đối tượng bằng nhau và làm mất danh tính khi lưu trong collection.
Một hệ thống kho biểu diễn tọa độ kệ hàng bằng chuỗi có thể thay đổi; khi vị trí được gán vào nhiều phiếu, sửa chuỗi vị trí của một phiếu làm thay đổi các phiếu lịch sử khác.
Nhóm dùng một value object Money nhưng cho phép cộng hai số tiền khác đơn vị USD và VND mà không xác định tỷ giá; kết quả tính tổng vẫn được ghi vào hóa đơn như một giá trị hợp lệ.
Trong ứng dụng giao hàng, địa chỉ gồm số nhà, đường, phường và tọa độ được lưu thành các field rời; nhiều đoạn code khác nhau tự quyết định thế nào là hai địa chỉ giống nhau.
Đội xây entity Product có các trường giá, tồn kho, mô tả và lịch sử giao nhận; một thao tác đổi mô tả buộc tải và khóa toàn bộ dữ liệu tồn kho của sản phẩm.
Trong hệ thống đơn hàng, một Order chứa nhiều OrderLine; API cho phép cập nhật số lượng dòng hàng trực tiếp mà không tính lại tổng tiền và giới hạn số lượng đặt.
Nhóm chọn toàn bộ Organization cùng hàng nghìn Employee làm một aggregate; thao tác cập nhật số điện thoại của một nhân viên gây xung đột version với thao tác sửa nhân viên khác.
Ứng dụng đặt phòng kiểm tra số chỗ trống khi đọc rồi tạo hai aggregate Booking độc lập; hai request đồng thời giữ cùng một ghế dù từng Booking đều hợp lệ riêng lẻ.
Một aggregate Invoice đang ở trạng thái PAID nhưng repository cho phép xóa một InvoiceLine mà không đi qua thao tác nghiệp vụ; tổng tiền và chi tiết hóa đơn không còn nhất quán.
Nhóm tính tồn kho bằng cách tải Product và tất cả Reservation của nhiều kho vào một transaction; mỗi lần giữ chỗ trở nên chậm khi quy mô cửa hàng tăng.
Trong hệ thống điểm thưởng, một giao dịch cộng điểm phải cập nhật ví và lịch sử phát sinh; nhóm chưa xác định dữ liệu nào cần nhất quán ngay bên trong cùng ranh giới aggregate.
Service giao hàng muốn giữ tham chiếu trực tiếp tới toàn bộ entity Order của context Bán hàng trong aggregate Shipment; một lần cập nhật Order làm thay đổi cả cấu trúc lưu trữ của Shipment.
Đội dùng repository chung trả và lưu mọi loại entity con trong aggregate; lớp xử lý bên ngoài có thể sửa từng phần mà không kích hoạt kiểm tra bất biến ở aggregate root.
Một ứng dụng nhiều tenant tìm tài khoản bằng email trong repository nhưng không truyền tenantId; hai khách hàng ở hai doanh nghiệp có cùng email bị trả nhầm bản ghi.
Nhóm đặt phép tính hạn mức tín dụng trong controller vì logic cần dữ liệu từ nhiều đối tượng; API thứ hai lặp lại phép tính với công thức khác dù đây là cùng quy tắc miền nghiệp vụ.
Một domain service xử lý quyết định cấp hạn mức trực tiếp gọi HTTP tới cơ quan tín dụng và gửi email; khi cần kiểm thử chính sách phê duyệt, nhóm phải dựng nhiều phụ thuộc hạ tầng.
Trong ứng dụng bán vé, domain event TicketIssued được phát ngay khi phương thức aggregate chạy, nhưng transaction sau đó bị rollback và hệ thống thông báo vẫn gửi vé cho khách.
Nhóm đặt sự kiện OrderPaid dưới dạng bản sao đầy đủ toàn bộ Order; khi thêm trường nội bộ mới, nhiều consumer ngoài bounded context phải thay đổi dù chỉ cần mã đơn và số tiền.
Một consumer nhận domain event CustomerAddressChanged từ CRM nhưng diễn giải thành lệnh thay đổi địa chỉ trên mọi hóa đơn lịch sử; dữ liệu kế toán đã phát hành bị sửa theo sự kiện mới.
Nhóm quyết định ghép nhiều bounded context trong cùng một modular monolith, nhưng các module vẫn import trực tiếp model và repository nội bộ của nhau; thay đổi nhỏ ở một miền kéo theo sửa hàng loạt miền khác.

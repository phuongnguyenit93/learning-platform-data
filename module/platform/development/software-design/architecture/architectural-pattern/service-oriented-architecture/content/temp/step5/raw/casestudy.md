Một doanh nghiệp bán lẻ muốn tách chức năng khách hàng, tích điểm và chăm sóc sau bán thành các dịch vụ, nhưng mỗi nhóm định nghĩa lại hồ sơ khách hàng khác nhau; kiến trúc sư cần xác định ranh giới năng lực và quyền sở hữu dữ liệu của từng service.
Ba hệ thống bán hàng, kho và kế toán gọi chung một service đặt hàng nhưng cũng tự truy cập trực tiếp vào bảng đơn hàng của nhau; sau thay đổi schema, nhiều ứng dụng phụ thuộc bị lỗi dù giao diện service không đổi.
Một nhóm chia mỗi thao tác CRUD thành một service mạng riêng và buộc luồng tạo đơn gọi hơn hai mươi service; độ trễ cao và khó xác định đơn vị nghiệp vụ nào thật sự có trách nhiệm xử lý.
Một service bảo hiểm cung cấp hợp đồng SOAP theo WSDL cho nhiều đối tác; nhóm đổi tên một phần tử trong thông điệp yêu cầu và client đã sinh mã từ WSDL cũ bắt đầu gửi dữ liệu không hợp lệ.
Hai dịch vụ SOAP sử dụng cùng tên phần tử XML nhưng namespace khác nhau; hệ thống tích hợp chấp nhận một thông điệp mà từ chối thông điệp còn lại dù con người đọc thấy nội dung giống nhau.
Một nhà cung cấp nâng cấp schema XML và biến một trường vốn không bắt buộc thành bắt buộc; các ứng dụng đối tác đã triển khai từ lâu không gửi trường đó nên không gọi được chức năng cũ.
Một API REST trả HTTP 200 cho cả trường hợp từ chối nghiệp vụ và lỗi hệ thống, chỉ thay nội dung trong body; các khách hàng khác nhau xử lý retry và cảnh báo theo cách không nhất quán.
Nhóm nâng phiên bản service khách hàng và thay một trường JSON từ chuỗi sang đối tượng; client web mới chạy được nhưng một ứng dụng nội bộ chưa cập nhật lại không giải mã được phản hồi.
Một doanh nghiệp tạo mô hình dữ liệu khách hàng chuẩn dùng chung cho mọi service; mỗi lần một hệ thống thay đổi trường nghiệp vụ, toàn bộ dịch vụ tích hợp phải nâng cấp dù không sử dụng trường đó.
Hệ thống ERP cũ chỉ có SOAP, còn ứng dụng đặt hàng mới gọi REST; đội tích hợp muốn chuyển đổi hợp đồng giữa hai bên nhưng đang đặt quy tắc tính giá vào lớp chuyển đổi thông điệp của ESB.
Một ESB trung tâm phải chuyển đổi, định tuyến và ghi log tất cả yêu cầu giữa hàng chục hệ thống; khi lưu lượng tăng hoặc ESB bảo trì, ngay cả các service độc lập cũng bị gián đoạn.
Một quy trình cấp tín dụng cần lấy thông tin khách hàng, đánh giá rủi ro rồi phát hành hợp đồng theo thứ tự; các nhóm chưa thống nhất bên nào điều phối tiến trình và theo dõi trạng thái giữa các service.
Một hệ thống xử lý hoàn tất đơn bằng cách phát sự kiện để kho, vận chuyển và thông báo tự phản ứng; khi một service bỏ lỡ sự kiện, không thành phần nào nắm được tình trạng chung của toàn bộ quy trình.
Luồng đặt phòng đã giữ phòng và thu tiền qua hai service, nhưng bước phát hành xác nhận bị lỗi; việc hoàn tác không thể dùng một giao dịch cơ sở dữ liệu duy nhất cho tất cả hệ thống tham gia.
Một service quản lý đơn gọi service thanh toán, gặp timeout và thử lại; thao tác đầu có thể đã thu tiền, khiến cùng đơn bị tính phí hai lần khi các bên chưa thống nhất mã yêu cầu lặp.
Ứng dụng nhận lỗi mạng ngay sau khi gửi yêu cầu tạo phiếu xuất kho, không biết service đối tác đã tạo phiếu hay chưa; quy trình xử lý lỗi hiện tạo yêu cầu mới mỗi lần thử lại.
Trong một trung tâm dữ liệu có nhiều instance service, endpoint của dịch vụ quản lý kho thay đổi khi triển khai nhưng ứng dụng gọi vẫn lưu địa chỉ máy cũ trong cấu hình cố định.
Một ngân hàng phải phục vụ đồng thời đối tác dùng hợp đồng SOAP phiên bản cũ và ứng dụng nội bộ dùng REST phiên bản mới; nhóm chưa có chính sách về thời gian duy trì phiên bản và cách ngừng hỗ trợ an toàn.
Đội thêm trường tùy chọn vào thông điệp xác nhận đơn hàng để phục vụ kênh mới, nhưng một client cũ từ chối toàn bộ phản hồi có trường không nhận diện; thiết kế hợp đồng đang giả định các client có cùng mức chịu thay đổi.
Hai đội cùng tuyên bố các bài unit test của service mình đều đạt, nhưng khi triển khai kết hợp lại phát hiện một bên hiểu mã trạng thái từ chối hợp đồng khác bên kia; nhóm cần xác minh kỳ vọng của bên cung cấp và bên tiêu thụ dịch vụ.
Một cổng dịch vụ xác thực người dùng ở đầu vào, rồi chuyển tiếp thông tin định danh sang các service nghiệp vụ; một service phía sau lại chấp nhận header danh tính do bất kỳ client nào gửi đến mà không kiểm tra nguồn tin cậy.
Nhiều service nội bộ dùng chứng chỉ để xác thực kết nối với nhau; sau đợt thay chứng chỉ, một nhóm service cũ vẫn tin chứng chỉ hết hạn và làm toàn bộ quy trình đặt hàng thất bại.
Một service báo cáo được nhiều hệ thống tiêu thụ nhưng chỉ một số vai trò được phép xem dữ liệu nhân sự; các team giả định việc phân quyền đã được xử lý ở service gọi trước nên endpoint báo cáo không kiểm tra lại phạm vi quyền.
ESB ghi đầy đủ payload để phục vụ kiểm toán, bao gồm số định danh và dữ liệu thanh toán; sau khi mở rộng quyền truy cập log cho đội vận hành, doanh nghiệp phát hiện rủi ro lộ thông tin nhạy cảm.
Hai service đặt hàng và kế toán dùng mã tiền tệ, đơn vị tiền và quy tắc làm tròn khác nhau; lớp tích hợp chuyển được định dạng nhưng số tiền trên hóa đơn không trùng số tiền khách đã thanh toán.
Một service tra cứu tồn kho cam kết phản hồi trong thời gian ngắn nhưng thường vượt giới hạn vào giờ cao điểm; nhiều hệ thống tiêu thụ không có thỏa thuận về timeout, lỗi và khả năng chấp nhận dữ liệu cũ.
Một trang đặt hàng đồng bộ gọi lần lượt dịch vụ khách hàng, khuyến mại, kho và thanh toán; khi một dịch vụ con chậm, toàn bộ trang chờ kéo dài mặc dù các dịch vụ còn lại vẫn khỏe mạnh.
Ứng dụng hiển thị hồ sơ khách hàng phải gọi riêng service địa chỉ, số điện thoại, mức thành viên và ưu đãi cho mỗi dòng trong danh sách; số yêu cầu mạng tăng mạnh khi có hàng trăm hồ sơ.
Một service quản lý đơn hàng gửi sự kiện đơn đã xác nhận, nhưng báo cáo ở hệ thống kế toán cập nhật muộn vài phút; nhân viên hỗ trợ hiểu nhầm việc nhìn thấy dữ liệu cũ là bằng chứng giao dịch đã bị mất.
Hai bộ phận đều cung cấp service khách hàng và cùng cho phép sửa địa chỉ; sau vài tháng dữ liệu giữa các nguồn chênh lệch, nhưng chưa có bên nào chịu trách nhiệm xác định bản ghi có thẩm quyền.
Khi một yêu cầu đi qua gateway, ESB và bốn service khác nhau, mỗi nơi ghi log theo mã riêng; lúc phát sinh lỗi hiếm, đội vận hành không thể nối các bản ghi để xác định bước nào làm mất thông tin.
Một tổ chức muốn đưa mọi biến đổi nội bộ vào ESB vì dễ giám sát tập trung, nhưng các đội phát triển phải chờ hội đồng chung phê duyệt cả thay đổi nhỏ; kiến trúc sư phải đánh giá đánh đổi giữa quản trị tích hợp, mức độ kết dính và khả năng tiến hóa độc lập.

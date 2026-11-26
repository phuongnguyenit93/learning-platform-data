Trong hệ thống bán lẻ, lớp InvoiceManager vừa tính thuế, tạo PDF, gửi email và đồng bộ kho; khi mẫu email đổi, đội phát hành phải kiểm thử lại toàn bộ tính toán hóa đơn dù hai trách nhiệm không liên quan trực tiếp.
Đội phát triển UserService phụ trách đăng nhập, thay ảnh đại diện, chấm điểm tín nhiệm và thống kê doanh thu; bốn nhóm sản phẩm cùng sửa một file và liên tục tạo xung đột merge.
Ứng dụng đặt hàng có lớp Order chỉ chứa dữ liệu dòng hàng, còn phép tính tổng nằm trong lớp FormattingUtils của giao diện; mỗi thay đổi quy tắc tổng tiền phải đi qua module trình bày.
Trong phần mềm nhân sự, logic tính tiền lương đọc trực tiếp các trường hợp đồng nhưng được đặt trong lớp tạo báo cáo PDF; khi cần chạy bảng lương dạng CSV, đội sao chép công thức.
Nhóm đặt hơn hai trăm phương thức xử lý chuỗi, tiền tệ, file và thông báo vào lớp CommonUtils; không có hai chức năng nào cùng sử dụng phần lớn các phương thức của lớp này.
Một phương thức processOrder dài hàng trăm dòng vừa xác minh giỏ, chọn phương thức giao hàng, trừ kho, lập hóa đơn và ghi log; khi lỗi ở cuối, nhóm khó xác định trạng thái trung gian nào thuộc trách nhiệm nào.
Trong ứng dụng quản lý kho, lớp WarehouseModel lưu vị trí và tồn kho nhưng thao tác thay đổi số lượng lại nằm ở ServiceHelper; quy tắc chống tồn âm bị lặp trong nhiều nơi gọi.
Đội xây CustomerProfile chứa địa chỉ giao hàng, lịch sử duyệt quảng cáo và cấu hình thanh toán; chỉ thay giao diện marketing vẫn buộc cập nhật class mà nghiệp vụ đặt hàng dùng hàng ngày.
Trong nền tảng học tập, hàm validateStudent nhận 15 tham số để đồng thời kiểm tra email, điều kiện học bổng và lịch thi; các màn hình chỉ cần một kiểm tra nhỏ vẫn phải chuẩn bị tất cả tham số.
Một lớp ReportService có nhóm phương thức thao tác riêng với database, email và vẽ biểu đồ; mỗi nhóm sử dụng các field khác nhau gần như hoàn toàn, nhưng cả lớp được giữ lại chỉ vì tất cả phục vụ 'báo cáo'.
Trong ứng dụng bán vé, định dạng mã QR đặt trong TicketRepository bên cạnh thao tác lưu trữ; nhóm thay bộ mã hóa QR phải xây dựng và chạy toàn bộ kiểm thử kết nối cơ sở dữ liệu.
Một lớp ShoppingCart có dữ liệu mặt hàng nhưng phương thức tính chiết khấu nằm trong DiscountController, nơi phải tự đọc cấu trúc nội bộ của giỏ để biết cách áp dụng ưu đãi.
Đội lưu danh sách quyền và phép kiểm tra người dùng có thể duyệt hồ sơ ở hai lớp khác nhau; một thay đổi role khiến một chức năng nhận quyền mới còn chức năng khác giữ quy tắc cũ.
Hệ thống chăm sóc khách hàng có lớp Ticket nhận thêm chức năng tự gửi SMS khi trạng thái đổi; việc cập nhật đơn thuần nội dung ticket bất ngờ phụ thuộc máy chủ SMS ngoài hệ thống.
Trong phần mềm kế toán, lớp TaxCalculator tính thuế và đồng thời quyết định màu hiển thị cảnh báo trên màn hình; khi thiết kế giao diện đổi theme, các test nghiệp vụ của lớp tính thuế bị hỏng.
Nhóm trích xuất lớp AddressNormalizer từ CustomerService nhưng vẫn giữ các phương thức xác minh định dạng địa chỉ ở cả hai nơi; các quy tắc địa chỉ thay đổi thường xuyên bị áp dụng khác nhau.
Đội đề xuất Move Method cho phép tính điểm trung bình từ một lớp tiện ích sang đối tượng bảng điểm; phép tính hiện cần truy cập trực tiếp nhiều trường private và quy tắc làm tròn của bảng điểm.
Trong hệ thống du lịch, phương thức isRoomAvailable đặt ở BookingController nhưng dùng dữ liệu sức chứa và lịch bảo trì của Room; nhiều đường gọi khác phải tạo controller để kiểm tra phòng trống.
Ứng dụng quản lý hội viên có lớp LoyaltyAccount chứa điểm thưởng nhưng việc trừ điểm nằm trong ReceiptService; các thao tác hoàn đơn và đổi quà đều viết cách giảm điểm riêng.
Một module Java tên Core chứa lớp gửi email, quy đổi tiền, phân quyền và tính tồn kho; nhóm nào muốn tái sử dụng một hàm cũng phải phụ thuộc cả module lớn và cùng lịch phát hành.
Trong backend thương mại, module CustomerManagement vừa xử lý hồ sơ khách hàng vừa kết xuất báo cáo doanh thu sản phẩm; thay đổi cách nhóm hóa báo cáo buộc redeploy nghiệp vụ hồ sơ.
Đội chia một quy trình tính giá thành mười microservice, mỗi service chỉ thực hiện một phép tính nhỏ; các phép tính vốn dùng cùng dữ liệu luôn phải gọi mạng nhiều lần để hoàn thành một báo giá.
Ứng dụng đặt lịch khám có module Booking chịu trách nhiệm cả lịch bác sĩ, kho vật tư và quản lý hợp đồng bảo hiểm; mỗi sprint mở rộng quy tắc vật tư đều làm các tính năng đặt lịch cần retest.
Nhóm tạo một lớp Validator chứa mọi kiểm tra từ mã bưu chính đến điều kiện hủy đơn; thay đổi quy tắc hủy đặt chỗ lại làm thư viện validation chung phải phát hành tới các dịch vụ không dùng đặt chỗ.
Trong service thanh toán, method createInvoice vừa làm phép tính, ghi dữ liệu và đọc file cấu hình; một test muốn xác minh quy tắc thuế phải chuẩn bị cả filesystem và database.
Đội đặt toàn bộ dữ liệu phiên người dùng và thông tin báo cáo vào một object SessionData; mỗi request chỉ dùng vài field và việc serialize dữ liệu phiên ngày càng tốn tài nguyên.
Trong ứng dụng logistics, một lớp RoutePlanner vừa xây tuyến đường vừa duy trì catalog địa điểm; cập nhật tên địa điểm có thể ảnh hưởng thuật toán định tuyến dù không thay quan hệ đường đi.
Nhóm có lớp Product chứa mô tả, giá bán và tồn kho của hàng trăm cửa hàng; một thao tác đổi mô tả bắt buộc tải và khóa toàn bộ dữ liệu tồn kho dù không sửa số lượng.
Trong phần mềm ngân hàng, lớp Account có các phương thức rút, nạp và kiểm tra số dư, nhưng quy tắc tính phí chuyển khoản lại đặt trong một class sinh báo cáo do cần dùng lại dữ liệu giao dịch.
Đội refactor một class lớn bằng Extract Class nhưng chuyển một nửa field sang lớp mới và để hai lớp liên tục gọi getter của nhau; mọi sửa đổi nhỏ vẫn phải điều chỉnh đồng thời cả hai lớp.
Ứng dụng gửi thông báo có lớp EmailTemplate chứa cả nội dung thông báo và logic thử lại mạng; mỗi lần chỉnh câu chữ, nhóm test phải mô phỏng cả lỗi kết nối SMTP.
Nhóm viết một hàm buildReport nhận cờ gửi email, cờ lưu file và cờ ghi database; các đường thực thi gần như độc lập nhưng nằm trong cùng một phương thức khó kiểm thử đủ tổ hợp.
Trong hệ thống CRM, các nghiệp vụ cập nhật hồ sơ, gửi chiến dịch và chấm điểm lead được gộp vào một service vì cùng làm việc với khách hàng; ba chính sách phát hành có tần suất thay đổi khác nhau.
Một đơn vị phát triển cho rằng mỗi lớp chỉ nên có một phương thức, nên tách xử lý đơn thành hàng chục lớp nhỏ; việc đọc luồng nghiệp vụ phải mở nhiều file và các lớp chia sẻ trạng thái qua tham số dài.
Trong công cụ quản lý công việc, class Project có các quy tắc trạng thái dự án nhưng các thao tác chuyển trạng thái nằm ở lớp tiện ích độc lập; cùng quy tắc bị bỏ qua khi cập nhật từ API batch.
Đội kiểm thử một lớp vừa tính tiền vừa gọi nhiều dịch vụ bên ngoài; phần lớn test thất bại vì cấu hình phụ thuộc dù mục tiêu chỉ kiểm tra phép tính tổng tiền tại các mốc biên.
Trong hệ thống lưu trữ tài liệu, module Documents bao gồm kiểm soát phiên bản, cấp quyền, tính phí và tìm kiếm; thay đổi bảng giá yêu cầu cả nhóm phụ trách kiểm soát phiên bản review.
Nhóm triển khai chức năng giao hàng mới đã sao chép tính toán phí từ OrderService sang ShippingService; hai vị trí cùng cần sửa khi khu vực ngoại thành thay đổi đơn giá, nhưng không rõ nơi nào sở hữu chính sách.
Trong ứng dụng tạo báo cáo, một class chứa nhiều phương thức chỉ được dùng khi xuất file CSV, còn số khác chỉ được dùng cho PDF; việc tăng hỗ trợ PDF làm các unit test CSV phải khởi tạo cả thư viện PDF.
Đội kiến trúc cân nhắc tách một service quản lý hóa đơn thành nhiều module; biểu đồ thay đổi cho thấy tính thuế và lập hóa đơn thường đổi cùng nhau, còn gửi thư và trình bày PDF có lịch thay đổi riêng.

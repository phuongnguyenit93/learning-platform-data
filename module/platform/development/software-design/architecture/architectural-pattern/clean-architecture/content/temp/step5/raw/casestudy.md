Trong hệ thống đặt hàng Java, lớp Order thuộc domain import trực tiếp EntityManager để kiểm tra tồn kho; khi chuyển sang kho dữ liệu khác, nhóm phải sửa mã quy tắc đặt hàng dù hành vi nghiệp vụ không thay đổi.
Đội thanh toán đặt annotation của Spring Web trên lớp use case xác nhận giao dịch; khi muốn chạy use case trong batch không có HTTP, việc khởi tạo thành phần nghiệp vụ vẫn phụ thuộc web framework.
Ứng dụng học tập lưu quy tắc đủ điều kiện mở khóa bài trong REST controller; yêu cầu thêm kênh xử lý qua hàng đợi khiến nhóm sao chép cùng một điều kiện sang consumer khác.
Một dịch vụ tính giá nhập trực tiếp repository của JPA vào lớp use case; khi kiểm thử không có database, người viết test phải khởi động toàn bộ Spring context chỉ để kiểm tra phép tính.
Nhóm chia thư mục thành domain, application và infrastructure nhưng interface truy cập khách hàng đặt trong infrastructure; lớp use case phải phụ thuộc package tầng ngoài để gọi interface đó.
Trong hệ thống giao hàng, adapter HTTP chuyển thẳng JSON request thành entity miền nghiệp vụ với các field được điều khiển bởi client; quy tắc bất biến của entity có thể bị bỏ qua khi tạo đối tượng.
Ứng dụng đặt vé có entity Seat giữ trạng thái AVAILABLE hoặc RESERVED; controller thay đổi trực tiếp trạng thái trong database mà không gọi quy tắc giới hạn thời gian giữ chỗ của domain.
Đội phát triển đặt công thức hoa hồng trong class repository để tận dụng truy vấn SQL; khi thêm trường hợp tính hoa hồng cho đơn chưa được lưu, chính sách nghiệp vụ không thể tái sử dụng.
Trong một hệ thống khách hàng, lớp domain dùng kiểu ResponseEntity làm kết quả xác thực; ứng dụng console mới muốn dùng cùng quy tắc nhưng phải hiểu mã HTTP và header để gọi đúng.
Nhóm thiết kế use case Đăng ký tài khoản trả về entity JPA đầy đủ; adapter giao diện vô tình truy cập thuộc tính lazy và lỗi khi persistence context đã đóng.
API REST, tác vụ nền và chương trình dòng lệnh đều cần chạy use case Kết toán cuối ngày; mỗi adapter đang tự mở transaction, tính tổng và ghi sổ theo cách hơi khác nhau.
Một use case xác thực đơn hàng nhận đối tượng HttpServletRequest để lấy userId và locale; các kiểm thử thuần Java phải tạo mô phỏng servlet dù chính sách chỉ cần hai giá trị đó.
Trong module đặt phòng, use case tự đọc thời gian hệ thống để xác định đặt chỗ hết hạn; test chạy lúc nửa đêm không tái hiện được tình huống hủy đúng ở ranh giới thời gian.
Chức năng hoàn tiền gọi trực tiếp SDK của cổng thanh toán bên ngoài từ use case; khi SDK đổi API hoặc bị sandbox chặn, logic xác nhận điều kiện hoàn tiền không còn dễ kiểm thử.
Trong service gửi thông báo, use case tạo instance SMTP client bằng constructor; nhóm không thể thử luồng lỗi gửi thư mà không cần kết nối tới máy chủ email.
Nhóm định nghĩa cổng lưu trữ CustomerRepository với hàm trả trực tiếp kiểu Page của framework; use case tìm khách hàng bị ràng buộc vào API phân trang của tầng truy cập dữ liệu.
Đội cố đưa mọi thao tác CRUD thành interface chung cho toàn bộ use case; quy tắc phê duyệt khoản vay có nhiều bước bị ẩn dưới phương thức save, khiến hợp đồng nghiệp vụ không rõ ràng.
Trong hệ thống kho, entity Product có method giảm tồn kho và bảo đảm không âm; service bên ngoài lại cập nhật trường quantity trực tiếp, làm bất biến bị phá vỡ trong một nhánh nhập hàng.
Nhóm đặt các giá trị enum trạng thái thanh toán trong module web để khớp response; use case phải import enum của web mỗi khi kiểm tra chuyển trạng thái.
Ứng dụng quản lý hồ sơ bệnh án sử dụng cùng một DTO cho input HTTP, kết quả use case và dữ liệu database; thêm một trường chỉ dành cho màn hình làm thay đổi hợp đồng cả ba lớp.
Đội định nghĩa output boundary của use case báo cáo doanh thu rồi trả về danh sách entity ORM cho presenter; việc dựng báo cáo trong background job vẫn đòi hỏi context persistence đang mở.
Trong một luồng tìm kiếm, presenter chứa phép tính chiết khấu để hiển thị giá cuối; ứng dụng mobile và web trình bày hai tổng tiền khác nhau dù truy vấn cùng đơn hàng.
Nhóm cho controller quyết định đơn hàng có thể hủy hay không trước khi gọi use case Hủy đơn; khi chạy từ message consumer, điều kiện chặn không còn được áp dụng.
Dịch vụ quản lý quyền cần xác minh vai trò người dùng trước thao tác xóa dữ liệu; nhóm phân tán kiểm tra quyền ở một số adapter và bỏ sót đường gọi thông qua batch import.
Use case Tạo đơn thành công ở mức nghiệp vụ nhưng adapter database chưa commit; adapter gửi thông báo thành công ngay và người dùng nhận email cho một đơn bị rollback sau đó.
Một use case chuyển khoản cần ghi hai bút toán atomically, nhưng mỗi adapter repository tự mở và đóng transaction riêng; lỗi ghi bút toán thứ hai để lại số dư sai.
Nhóm định nghĩa cổng thanh toán chỉ trả boolean thành công hoặc thất bại; khi đối tác trả kết quả PENDING, adapter phải ép thành thất bại và use case mất khả năng thể hiện trạng thái đang xử lý.
Trong ứng dụng bán hàng, adapter REST bắt mọi exception của use case rồi trả HTTP 200 với message lỗi; consumer không phân biệt lỗi nghiệp vụ và yêu cầu thành công dù các lớp phía trong có trạng thái rõ ràng.
Nhóm viết domain exception phụ thuộc vào mã trạng thái HTTP để phân loại lỗi; chuyển giao diện sang gRPC buộc sửa exception vốn thuộc quy tắc nghiệp vụ.
Ứng dụng tuyển dụng có nhiều adapter lưu trữ PostgreSQL và MongoDB; mỗi adapter diễn giải điều kiện tìm ứng viên khác nhau, khiến cùng use case cho kết quả không thống nhất theo môi trường.
Trong module báo giá, một adapter thực hiện tính toán phụ thu ngoài hợp đồng cổng; adapter mới cho API đối tác không có phụ thu đó nên hệ thống phát sinh khác biệt nghiệp vụ.
Nhóm cấu hình dependency injection để kết nối interface use case với implementation, nhưng một bean domain gọi constructor của adapter MongoDB trực tiếp, khiến composition root không còn kiểm soát lựa chọn hạ tầng.
Ứng dụng chuyển từ JDBC sang JPA; thành viên thêm adapter mới nhưng xóa implementation cũ trước khi kiểm tra các batch job vẫn dùng JDBC, gây lỗi sau triển khai.
Đội khởi tạo object graph tại nhiều controller thay vì một composition root rõ ràng; hai luồng dùng hai instance repository khác nhau và cấu hình cache không nhất quán.
Một module giao hàng đang được tách khỏi monolith; các use case mới gọi trực tiếp lớp tiện ích dùng chung có quyền truy cập mọi database, khiến ranh giới module vẫn phụ thuộc hệ thống cũ.
Trong kế hoạch refactor ứng dụng ba tầng sang Clean Architecture, nhóm chuyển toàn bộ class thành các package mới trong một pull request; hành vi ở luồng đặt hàng thay đổi nhưng diff không chỉ rõ nguyên nhân.
Đội chuyển business logic từ controller sang use case, song adapter cũ vẫn giữ một nhánh kiểm tra giá trị đơn hàng; cùng chính sách tồn tại ở hai nơi và dần sai khác sau các đợt sửa lỗi.
Nhóm tạo unit test cho use case Phê duyệt đơn hàng với fake repository; test xác minh được quyết định nghiệp vụ nhưng một adapter SQL mới vẫn vi phạm ánh xạ trạng thái khi ghi database.
Trong hệ thống Java nhiều module, bài kiểm thử kiến trúc cho phép domain tham chiếu mọi package application; một thay đổi thêm dependency framework thông qua interface ở application mà không bị cảnh báo.
Đội triển khai thay thế giao diện web bằng CLI cho dịch vụ tạo khách hàng; quy tắc nghiệp vụ từng được tưởng là độc lập lại cần session web, đối tượng response và thuộc tính framework để chạy.

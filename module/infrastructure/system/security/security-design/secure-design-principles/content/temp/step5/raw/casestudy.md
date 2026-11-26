Ứng dụng quản trị được triển khai công khai với một lớp đăng nhập bằng mật khẩu; nhóm kiến trúc cho rằng chỉ người biết URL mới tìm thấy giao diện quản trị nên không bổ sung kiểm soát truy cập theo vai trò.
Bản cài đặt mới tạo tài khoản quản trị với mật khẩu mặc định dùng chung; tài liệu triển khai yêu cầu đổi mật khẩu nhưng hệ thống vẫn cho phép đăng nhập trước khi hoàn tất bước này.
Một dịch vụ mới được cấu hình mặc định cho phép mọi principal trong cùng mạng gọi tất cả endpoint; nhóm triển khai dự định thu hẹp quyền sau khi đưa hệ thống vào production.
Toàn bộ microservice dùng chung một service account có quyền quản trị database; khi một dịch vụ ít quan trọng bị xâm nhập, kẻ tấn công có thể đọc và sửa dữ liệu của mọi miền nghiệp vụ.
Nhóm vận hành cấp quyền cluster-admin cho tài khoản CI để pipeline có thể triển khai mọi loại tài nguyên; pipeline build từ nhánh thử nghiệm cũng thừa hưởng quyền này.
API nhận tenant ID từ request và dùng trực tiếp để truy vấn dữ liệu; backend không xác minh người dùng hiện tại có thuộc tenant được chỉ định hay không.
Ứng dụng chỉ ẩn nút quản trị trên giao diện theo role nhưng endpoint tương ứng không kiểm tra quyền ở phía server; người dùng có thể gọi trực tiếp API.
Reverse proxy ghi nhận địa chỉ client qua header forwarded nhưng backend chấp nhận header do Internet gửi trực tiếp; chính sách allowlist IP có thể bị giả mạo.
Backend tin header `X-User-Role` do gateway chuyển tiếp nhưng gateway vẫn giữ nguyên header cùng tên từ request bên ngoài; client có thể tự khai báo role cao hơn.
Kiến trúc có firewall, WAF và IDS nhưng cả ba cùng dựa trên một danh sách allowlist lỗi thời; một thay đổi sai trong nguồn policy làm suy yếu đồng thời nhiều lớp phòng vệ.
Các phòng ban được chia VLAN nhưng router core cho phép mọi VLAN giao tiếp mặc định; nhóm thiết kế nhầm phân đoạn logic với kiểm soát luồng truy cập thực tế.
Rate limit chỉ được bật tại API gateway công khai; một đường gọi nội bộ và endpoint dự phòng không đi qua gateway nên vẫn có thể bị lạm dụng tài nguyên.
WAF được xem là biện pháp duy nhất chống injection; ứng dụng vẫn ghép chuỗi truy vấn database từ input và không có kiểm soát tại tầng xử lý dữ liệu.
Nhóm dự án cho rằng HTTPS bảo vệ toàn bộ dữ liệu nên lưu bản export chứa thông tin nhạy cảm trên bucket công khai để người dùng tải thuận tiện.
Dịch vụ authorization không phản hồi trong lúc sự cố mạng; ứng dụng chuyển sang mặc định Allow để giữ tính sẵn sàng và vô tình cấp quyền cho request chưa được đánh giá.
Cache quyết định quyền truy cập được dùng vô thời hạn khi policy service mất kết nối; một quyền vừa bị thu hồi vẫn có hiệu lực trên các node đang chạy.
Khi gặp lỗi không mong đợi, API trả stack trace, câu truy vấn và đường dẫn nội bộ cho client; thông tin chẩn đoán giúp người ngoài suy luận cấu trúc hệ thống.
Middleware bắt exception và trả HTTP 200 cùng dữ liệu rỗng để tránh làm gián đoạn client; hệ thống giám sát không nhận ra thao tác bảo mật đã thất bại.
Thiết kế coi mọi lỗi kiểm tra chữ ký là lỗi tạm thời và tiếp tục xử lý payload; request không xác thực vẫn có thể đi vào luồng nghiệp vụ.
Threat model chỉ xem xét kẻ tấn công Internet mà không xét nhân viên nội bộ, tài khoản dịch vụ hoặc nhà cung cấp có quyền truy cập từ xa.
Một ứng dụng giữ lại hàng chục endpoint thử nghiệm và API cũ không còn sử dụng; các endpoint vẫn được triển khai và không nằm trong quy trình kiểm tra bảo mật.
Trang debug cho phép xem biến môi trường và trạng thái hệ thống được bật trên production để đội hỗ trợ dễ xử lý sự cố; trang không yêu cầu quyền quản trị riêng.
Tài liệu API và giao diện khám phá endpoint được mở công khai trong production; các thao tác quản trị và tham số nội bộ cũng xuất hiện trong tài liệu.
Một endpoint quản trị phiên bản cũ bị ẩn khỏi menu nhưng vẫn hoạt động; endpoint mới đã kiểm tra MFA còn endpoint cũ chỉ kiểm tra session.
File upload được đưa vào vùng lưu trữ công khai ngay sau khi nhận; tiến trình quét malware chạy bất đồng bộ và chưa hoàn tất khi người dùng khác tải file.
Ứng dụng giải nén file do người dùng gửi ngay trong tiến trình xử lý chính; một file nén có cấu trúc bất thường có thể làm cạn tài nguyên hoặc ghi ra ngoài thư mục dự kiến.
Cache dùng khóa ghép từ object ID nhưng bỏ qua tenant ID; dữ liệu đã đọc của tenant này có thể được trả lại cho người dùng tenant khác.
Nhiều tenant dùng chung một encryption key và không có ràng buộc tenant trong metadata xác thực; sự cố lộ khóa làm tăng phạm vi dữ liệu bị ảnh hưởng.
Secret vận hành được đóng gói trong container image và image được chia sẻ qua registry cho nhiều nhóm; thay đổi quyền registry không thu hồi được bản secret đã phân phối.
Ứng dụng ghi access token và thông tin xác thực vào log debug khi lỗi xảy ra; log được sao chép sang môi trường phân tích có phạm vi người xem rộng hơn.
Quy trình rotation credential tạo khóa mới rồi xóa khóa cũ ngay lập tức; các consumer chưa cập nhật đồng loạt khiến dịch vụ gián đoạn và nhóm phải khôi phục bí mật cũ.
Backup database chứa dữ liệu nhạy cảm được lưu ở cùng tài khoản lưu trữ với production và không mã hóa độc lập; một credential bị lộ mở đường truy cập cả bản sao.
Ứng dụng có quyền sửa và xóa audit log của chính nó; khi tài khoản dịch vụ bị chiếm, kẻ tấn công có thể xóa dấu vết hoạt động.
Log bảo mật ghi username và kết quả đăng nhập nhưng không ghi principal thực hiện hành động, resource đích hoặc correlation ID; nhóm điều tra không thể dựng lại chuỗi sự kiện.
Build pipeline tải dependency theo phiên bản trôi nổi và tự động cập nhật không qua kiểm tra; một bản phát hành độc hại có thể đi vào sản phẩm mà không có bước phê duyệt.
Runner CI có quyền truy cập signing key production và quyền phát hành artifact; mã chạy trong bước kiểm thử có thể ký và phát hành gói ngoài quy trình.
Pipeline triển khai cho phép commit từ bất kỳ nhánh nào cập nhật production; không có yêu cầu review độc lập hoặc xác minh nguồn artifact.
Feature flag có thể tắt toàn bộ kiểm tra authorization để hỗ trợ debug; cờ được bật trên production và không có giới hạn thời gian hoặc người phê duyệt.
Quy trình rollback tự động khôi phục cả cấu hình bảo mật cũ; sau khi rollback, endpoint quản trị mở lại và chính sách MFA bị hạ cấp.
Người dùng bị hạ vai trò nhưng session và access token cũ vẫn còn hiệu lực; hệ thống chỉ cập nhật quyền trong directory mà không xử lý credential đã phát hành.
Luồng đăng ký MFA cho phép người dùng thêm yếu tố mới chỉ bằng session hiện tại; kẻ đã chiếm session có thể đăng ký thiết bị của chính mình.
Account recovery cho phép bỏ qua MFA bằng cách trả lời câu hỏi bí mật dễ đoán; kênh khôi phục trở thành đường vòng yếu hơn đăng nhập chính.
Cùng một người có thể yêu cầu và tự phê duyệt quyền truy cập production; quy trình không có separation of duties cho thao tác nhạy cảm.
Tài khoản break-glass được bật thường trực và dùng cho công việc hàng ngày; tổ chức không nhận cảnh báo khi tài khoản này được sử dụng.
API cho phép truy vấn báo cáo không giới hạn kích thước và thời gian; người dùng hợp lệ có thể tạo request tốn tài nguyên để làm suy giảm dịch vụ.
Máy chủ xử lý URL do người dùng cung cấp để lấy ảnh đại diện; thiết kế chỉ chặn domain công khai mà không ngăn truy cập metadata endpoint và địa chỉ nội bộ.
Ứng dụng dựa vào DNS nội bộ để xác định dịch vụ tin cậy nhưng không kiểm tra thay đổi địa chỉ sau khi resolve; DNS rebinding có thể chuyển request sang đích ngoài dự kiến.
Cơ chế cập nhật phần mềm tải gói từ máy chủ phân phối nhưng không xác minh chữ ký hoặc nguồn phát hành; kẻ kiểm soát đường truyền có thể thay gói cập nhật.
Quy trình xóa tài khoản chỉ xóa bản ghi chính mà không thu hồi token, API key, bản sao dữ liệu hoặc quyền ở hệ thống tích hợp; danh tính đã xóa vẫn có đường truy cập tồn tại.
Hệ thống dự phòng dùng cùng tài khoản quản trị và cùng secret với production; khi credential chính bị lộ, vùng dự phòng cũng bị xâm nhập.
Một kiến trúc mới được đánh giá bằng checklist thành phần bảo mật nhưng không xác định trust boundary, tài sản quan trọng và đường đi dữ liệu; các luồng liên dịch vụ bị bỏ sót trong threat model.

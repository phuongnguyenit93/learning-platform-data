Một nhân viên thuộc tenant North gọi GET /invoices/4821 và đổi ID thành hóa đơn của tenant South; API xác thực phiên đăng nhập nhưng chỉ truy vấn theo invoice_id, khiến nội dung và thông tin thanh toán của tenant khác có thể bị trả về.
Người dùng gọi PATCH /profiles/731 để sửa hồ sơ; hệ thống lấy user_id từ URL làm đối tượng cập nhật mà không đối chiếu với chủ thể đã xác thực, nên một tài khoản thường có thể thay email hoặc số điện thoại của người khác.
Người dùng có quyền xem bài viết A gửi DELETE /posts/A/comments/992, trong khi comment 992 thực tế thuộc bài viết B; endpoint kiểm tra quyền trên bài viết A nhưng xóa comment theo ID độc lập.
Quản trị viên dự án Alpha truy cập /teams/alpha/members/88; thành viên 88 thuộc team Beta nhưng API chỉ kiểm tra vai trò team-admin của người gọi mà không xác nhận quan hệ giữa member và team trên đường dẫn.
Một API GraphQL cung cấp trường node(id) trả về đối tượng theo global ID; resolver gốc kiểm tra đăng nhập nhưng các trường lồng nhau như billingDetails và privateNotes không kiểm tra quyền trên từng đối tượng.
Endpoint batch nhận danh sách 100 document ID; middleware kiểm tra quyền trên document đầu tiên rồi handler tải toàn bộ danh sách, trong đó có ID thuộc người dùng và tenant khác.
Chức năng bulk delete xử lý một tập ID gồm cả tài nguyên được phép và không được phép; hệ thống xóa một phần trước khi phát hiện ID trái quyền, khiến kết quả và trạng thái giao dịch không nhất quán.
Ứng dụng SaaS nhận tenant_id từ query parameter để giới hạn dữ liệu; người dùng thay tenant_id sang tổ chức khác và backend tin giá trị client gửi thay vì ràng buộc tenant từ danh tính đã xác thực.
Người có vai trò organization-admin trong công ty A sử dụng cùng vai trò đó để truy cập tài nguyên công ty B; chính sách chỉ kiểm tra role mà không kết hợp phạm vi tổ chức của chủ thể và tài nguyên.
Nhân viên hỗ trợ được phép xem hồ sơ khách hàng khi có ticket đang xử lý; endpoint chỉ kiểm tra nhóm support mà không xác minh ticket còn mở, khách hàng có liên quan hay quyền truy cập tạm thời đã hết hạn.
API tạo tài liệu cho phép client gửi owner_id; người dùng tạo tài liệu mới nhưng đặt owner_id thành tài khoản khác, sau đó tài liệu xuất hiện trong danh sách riêng tư của người bị mạo danh.
Endpoint PATCH /projects/54 chấp nhận cả owner_id và tenant_id trong payload; người dùng có quyền sửa tên dự án lén thay đổi các trường phân quyền để chuyển quyền sở hữu hoặc đưa dự án sang tenant khác.
Quy trình chuyển quyền sở hữu tài sản cho phép chủ hiện tại chỉ định bất kỳ account_id nào; hệ thống không xác minh người nhận có tồn tại, thuộc đúng tenant hay đủ điều kiện tiếp nhận tài sản.
API tải hóa đơn tạo URL tải xuống có thời hạn; URL được gửi tiếp cho người ngoài tenant và vẫn truy cập được vì quyền chỉ được kiểm tra lúc tạo liên kết, không gắn token với tài nguyên và phạm vi chia sẻ dự kiến.
Người dùng upload tệp vào object storage bằng đường dẫn do client chọn; họ sửa prefix từ thư mục cá nhân sang prefix của tenant khác và ghi đè tệp có cùng object key.
Thư mục dự án được chia sẻ cho nhóm cộng tác viên rồi quyền chia sẻ bị thu hồi; các tệp con vẫn giữ ACL cũ do quyền kế thừa không được tính lại, nên người cộng tác viên tiếp tục tải được tệp.
Chủ tài liệu thu hồi public share link nhưng CDN còn cache bản tải xuống; người giữ URL cũ vẫn nhận được nội dung riêng tư sau khi quyền chia sẻ đã bị thu hồi.
API trả response cá nhân hóa nhưng cache key chỉ gồm URL và query string; request của người dùng thứ hai nhận lại nội dung đã cache cho người dùng thứ nhất.
CDN được cấu hình cache phản hồi GET của endpoint /account/summary; header cache không phân biệt nội dung riêng tư theo session, dẫn đến dữ liệu tài khoản có thể được phục vụ chéo giữa các phiên.
Chức năng tìm kiếm chỉ lọc theo từ khóa và trạng thái tài liệu; bộ lọc ACL bị bỏ qua trong một nhánh truy vấn nên kết quả hiển thị tiêu đề và đoạn trích của tài liệu người dùng không có quyền xem.
Dashboard tổng hợp số liệu theo tenant nhưng một endpoint drill-down nhận report_id và trả các hàng chi tiết mà không kiểm tra tenant sở hữu báo cáo, làm lộ giao dịch của tổ chức khác.
Người dùng tạo yêu cầu export dữ liệu trong tenant của mình; worker nền thực thi bằng tài khoản dịch vụ có quyền toàn hệ thống và không mang theo tenant scope của người yêu cầu.
Một tác vụ tạo PDF được xếp hàng khi người dùng còn quyền đọc hợp đồng; trước khi worker xử lý, quyền bị thu hồi nhưng worker vẫn xuất tệp vì không đánh giá lại quyền tại thời điểm thực thi.
Webhook đăng ký theo workspace nhận sự kiện thay đổi đối tượng; khi cấu hình webhook bị chuyển workspace, bộ phát sự kiện vẫn gửi payload của workspace cũ tới endpoint thuộc workspace mới.
Người dùng đăng nhập hợp lệ rồi mở WebSocket room /private-project-17; server chỉ xác thực lúc bắt tay kết nối, không kiểm tra quyền tham gia room và không xử lý việc quyền bị thu hồi khi socket đang mở.
Endpoint đánh dấu notification là đã đọc nhận notification_id; người dùng thay ID thành thông báo của tài khoản khác và làm thay đổi trạng thái hoặc đọc nội dung thông báo riêng tư.
Tài liệu dự án có tệp đính kèm kế thừa quyền xem từ tài liệu cha; endpoint tải attachment chỉ kiểm tra attachment_id mà không xác minh quyền trên tài liệu cha.
API audit history cho phép lọc theo actor_id và object_id; người dùng tự thay hai tham số để đọc lịch sử thay đổi của đối tượng thuộc nhóm khác dù không có quyền xem đối tượng đó.
Endpoint xem version history kiểm tra quyền trên phiên bản hiện tại nhưng truy xuất revision theo revision_id độc lập; một revision cũ chứa dữ liệu trước khi tài liệu được chuyển sang chế độ riêng tư.
Hệ thống dùng chung một database và áp dụng row-level security theo tenant context của kết nối; connection được tái sử dụng nhưng tenant context của request trước không được xóa hoặc thiết lập lại đúng cách.
Ứng dụng truy vấn bảng có row-level security bằng một database role có quyền bypass policy; lớp API có lọc tenant nhưng một truy vấn báo cáo mới vô tình bỏ điều kiện lọc và trả dữ liệu toàn hệ thống.
Microservice báo cáo dùng service identity có quyền đọc mọi hóa đơn; API nội bộ nhận invoice_id từ caller và thực hiện truy vấn theo quyền rộng của service mà không kiểm tra quyền của người dùng cuối.
Một gateway truyền service credential tới backend nhưng bỏ mất danh tính và tenant scope của người dùng khởi tạo request; backend xem mọi lời gọi từ gateway là được phép truy cập mọi đối tượng.
Policy engine gặp lỗi hoặc thiếu thuộc tính resource.owner trong request; cơ chế fallback mặc định cho phép truy cập, khiến dữ liệu vẫn được trả khi không thể đưa ra quyết định phân quyền đầy đủ.
Chính sách ABAC dựa trên trạng thái thiết bị và vị trí đăng nhập; client tự gửi các thuộc tính này trong request và backend không xác minh nguồn tin cậy trước khi dùng chúng để cấp quyền.
Một người dùng thuộc nhiều nhóm có các quyền allow và deny chồng lấn trên cùng tài liệu; hệ thống không quy định thứ tự ưu tiên nên hai API khác nhau đưa ra quyết định trái ngược.
Người dùng bị gỡ khỏi workspace nhưng access token dài hạn vẫn chứa role cũ; các endpoint chỉ đọc role trong token mà không kiểm tra phiên bản quyền hoặc trạng thái thành viên mới nhất.
API kiểm tra người gọi có quyền sửa hồ sơ rồi mới thực hiện update ở câu lệnh riêng; giữa hai bước, quyền sở hữu được chuyển cho tài khoản khác nhưng update cũ vẫn hoàn tất.
Người dùng có quyền đọc một đối tượng nhưng không có quyền thay đổi trạng thái thanh toán; endpoint PATCH chỉ kiểm tra quyền đọc ở middleware và cho phép cập nhật trường nhạy cảm.
API trả 403 cho đối tượng tồn tại nhưng 404 cho ID không tồn tại; kẻ dò tìm có thể phân biệt ID hợp lệ và suy ra sự tồn tại của tài nguyên riêng tư qua mã trạng thái.
ID tài liệu được tạo tuần tự và endpoint trả thông báo khác nhau cho lỗi không tồn tại, sai tenant và thiếu quyền; người ngoài có thể dò ID và lập danh sách tài nguyên của tổ chức.
Cursor phân trang chứa offset và bộ lọc tenant do client giải mã được; người dùng sửa cursor để chuyển sang phạm vi tenant khác và tiếp tục đọc trang dữ liệu không thuộc mình.
Ứng dụng mobile đồng bộ thay đổi ngoại tuyến sau nhiều ngày; người dùng đã bị thu hồi quyền trên dự án nhưng các thao tác lưu cục bộ vẫn được chấp nhận khi thiết bị kết nối lại.
API phiên bản cũ /v1/documents/{id} vẫn được duy trì cho tích hợp đối tác; phiên bản mới có object-level policy nhưng route cũ chỉ xác thực token và trả tài liệu theo ID.
Trang xem trước ảnh và endpoint OCR được triển khai riêng với endpoint tải tệp; chúng nhận file_id và trả thumbnail hoặc văn bản trích xuất mà không áp dụng ACL của tệp gốc.
Nhân viên rời tổ chức và tài khoản được tái cấp cho người mới; một số quyền chia sẻ trực tiếp và token truy cập cũ vẫn gắn với account identifier, làm người mới thừa hưởng quyền của người trước.
Tenant chuyển một dự án sang tổ chức khác; bản ghi chính đã đổi tenant nhưng attachment, audit history và search index vẫn mang tenant cũ, tạo ra các đường truy cập không đồng nhất.
Quyền truy cập một hồ sơ được cấp thông qua quan hệ người chăm sóc có thời hạn; quan hệ đã kết thúc nhưng endpoint tải tài liệu vẫn kiểm tra role caregiver chung mà không xét thời hạn và đối tượng được ủy quyền.
Nhóm kiểm thử bảo mật chỉ xác minh người dùng không thể GET tài liệu của tenant khác; các thao tác list, search, export, update, delete, bulk và nested resource chưa được kiểm tra theo cùng ma trận chủ thể-tài nguyên-hành động.

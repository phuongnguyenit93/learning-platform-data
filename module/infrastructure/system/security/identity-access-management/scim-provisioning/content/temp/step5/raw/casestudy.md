Hệ thống nhân sự tạo hồ sơ cho nhân viên mới có ngày bắt đầu trong tương lai; ứng dụng đích cần nhận tài khoản trước ngày nhận việc nhưng không được cho phép đăng nhập sớm.
Một nhân viên nghỉ việc được cập nhật trạng thái inactive trong nguồn danh tính, nhưng phiên đăng nhập và refresh token của họ tại ứng dụng đích vẫn hoạt động sau khi SCIM đã phản hồi thành công.
Nhân viên chuyển từ phòng kinh doanh sang tài chính; đồng bộ thuộc tính department đã thành công nhưng các nhóm và quyền cũ vẫn còn trong ứng dụng đích.
Một ứng dụng đích tạo SCIM id riêng cho mỗi User, trong khi hệ thống danh tính dùng mã nhân sự làm externalId; sau lần đồng bộ đầu, connector lại dùng externalId như SCIM id để gọi PATCH.
Nhân viên đổi địa chỉ email và userName sau khi kết hôn; hệ thống nguồn cần cập nhật định danh đăng nhập mà vẫn liên kết đúng hồ sơ SCIM hiện hữu.
Một nhân viên quay lại công ty sau khi tài khoản cũ đã bị deprovision; hệ thống nhân sự cấp lại mã nhân viên cũ nhưng ứng dụng đích vẫn giữ bản ghi inactive có externalId đó.
Hai công ty con trong cùng tập đoàn có nhân viên dùng chung địa chỉ email liên hệ; ứng dụng đích yêu cầu userName duy nhất trong tenant nhưng connector chỉ dùng email làm khóa đối chiếu.
Một tài khoản đã tồn tại từ trước trong ứng dụng đích được ghép với hồ sơ nhân sự mới chỉ dựa trên email; email đó từng được cấp cho một nhân viên khác đã rời tổ chức.
Hệ thống danh tính là nguồn chuẩn của tên và phòng ban, nhưng quản trị viên ứng dụng đích sửa thủ công department; lần đồng bộ tiếp theo ghi đè thay đổi và gây sai lệch báo cáo.
Một nhân viên được đổi quản lý trực tiếp; connector gửi manager dưới dạng chuỗi tên hiển thị thay vì tham chiếu đến định danh User mà ứng dụng đích yêu cầu.
Ứng dụng đích hỗ trợ Enterprise User extension với department, division, costCenter và manager; connector chỉ gửi các thuộc tính lõi nên dữ liệu tổ chức không được cập nhật đầy đủ.
Nhà cung cấp ứng dụng thay đổi URN của custom schema extension sau một lần nâng cấp; các request cũ vẫn gửi URN trước đây và bị từ chối.
Connector gửi thuộc tính id hoặc meta.version trong request cập nhật User dù schema đánh dấu các thuộc tính này là readOnly; ứng dụng đích trả lỗi validation.
Một tích hợp SCIM mới cần xác định thuộc tính bắt buộc, khả năng lọc và hỗ trợ PATCH của ứng dụng đích trước khi bắt đầu đồng bộ dữ liệu thật.
Ứng dụng đích công bố nhiều ResourceType ngoài User và Group; nhóm tích hợp nhầm một resource tùy chỉnh với User vì chỉ dựa vào endpoint có tên gần giống.
ServiceProviderConfig của ứng dụng đích cho biết PATCH không được hỗ trợ; connector vẫn gửi PATCH để cập nhật một thuộc tính đơn lẻ và nhận lỗi method không được phép.
Một thuộc tính custom được gửi với kiểu dữ liệu không khớp schema, chẳng hạn số nguyên thay cho chuỗi; request bị từ chối và hàng đợi đồng bộ liên tục thử lại cùng payload.
Nhân viên xóa giá trị số điện thoại phụ trong nguồn nhân sự; connector bỏ qua thuộc tính rỗng nên số điện thoại cũ tiếp tục tồn tại tại ứng dụng đích.
Một thay đổi chỉ cập nhật active và department; connector dùng PATCH với path không hợp lệ cho thuộc tính lồng nhau và ứng dụng đích trả lỗi invalidPath.
Nhân viên rời một nhóm dự án; connector cần xóa đúng phần tử thành viên trong Group mà không thay thế toàn bộ danh sách members của nhóm.
Connector dùng PUT để cập nhật một User nhưng chỉ gửi các thuộc tính vừa thay đổi; những thuộc tính tùy chọn khác bị mất khỏi bản ghi tại ứng dụng đích.
Filter userName eq được gửi với giá trị chứa dấu cách và ký tự đặc biệt; connector không URL-encode filter nên ứng dụng đích phân tích sai hoặc trả lỗi cú pháp.
Hệ thống nguồn tìm User theo externalId nhưng ứng dụng đích áp dụng quy tắc caseExact khác với connector; cùng một giá trị định danh bị xem là hai bản ghi khác nhau.
Connector lấy danh sách User theo startIndex và count; trong lúc phân trang, nhiều tài khoản mới được tạo khiến một số bản ghi bị lặp hoặc bỏ sót giữa các trang.
Một yêu cầu Bulk chứa nhiều thao tác tạo User và thêm Group membership; một thao tác lỗi giữa chừng nhưng connector giả định toàn bộ batch đã rollback.
Quản trị viên và connector cùng sửa một User gần như đồng thời; request dùng ETag cũ và nhận HTTP 412 do điều kiện If-Match không còn khớp.
Connector gửi POST tạo User nhưng mất kết nối trước khi nhận response; lần retry tạo thêm một bản ghi trùng vì connector không tra cứu theo externalId trước khi thử lại.
Ứng dụng đích trả HTTP 409 khi tạo User do userName đã tồn tại; connector lặp lại POST cùng payload thay vì tìm bản ghi hiện có và đối chiếu định danh.
SCIM endpoint trả HTTP 429 khi đồng bộ số lượng lớn; connector bỏ qua Retry-After và tiếp tục gửi request khiến thời gian throttling kéo dài.
Ứng dụng đích tạm thời trả HTTP 503; connector retry liên tục với tần suất cố định làm tăng tải trong lúc dịch vụ đang phục hồi.
Nhóm có hàng nghìn thành viên cần đồng bộ; ứng dụng đích giới hạn kích thước response Group hoặc số thành viên có thể xử lý, nhưng connector vẫn gửi và nhận danh sách như thể không có giới hạn.
Một Group response chứa members với value, type và $ref; connector chỉ lưu display nên không thể xác định chính xác User cần xóa khỏi nhóm ở lần đồng bộ sau.
Ứng dụng đích không hỗ trợ nested Group membership nhưng nguồn danh tính có nhóm lồng nhau; việc flatten nhóm làm phát sinh quyền vượt quá phạm vi dự kiến.
Một nhóm nguồn được ánh xạ thành role quản trị trong ứng dụng đích; thành viên được thêm vào nhóm chỉ để nhận thông báo lại vô tình nhận quyền quản trị.
Connector chỉ gửi danh sách thành viên Group khi tạo nhóm lần đầu; các lần thêm hoặc xóa thành viên sau đó không được phát hiện vì không có cơ chế delta hoặc reconciliation.
Ứng dụng đích xóa một Group nhưng vẫn giữ liên kết membership ở các bản ghi User; những quyền kế thừa từ nhóm cũ tiếp tục có hiệu lực.
Một tổ chức vận hành nhiều tenant trên cùng nền tảng; connector dùng nhầm SCIM base URL hoặc bearer token của tenant khác và cập nhật tài khoản sai phạm vi.
Bearer token của connector hết hạn trong lúc một batch đang chạy; một số request đã thành công, số còn lại trả 401 và lần chạy lại không phân biệt được thao tác đã hoàn tất.
Token SCIM được cấp quyền đọc User nhưng không có quyền tạo Group; connector nhận 403 khi provision nhóm và ghi nhận nhầm đây là lỗi dữ liệu không thể sửa.
SCIM endpoint dùng chứng chỉ TLS sắp hết hạn; connector tắt kiểm tra chứng chỉ để tiếp tục đồng bộ, tạo nguy cơ lộ bearer token và dữ liệu nhân sự.
Log của connector lưu toàn bộ Authorization header và thuộc tính nhạy cảm trong request body; nhóm vận hành chia sẻ log để điều tra sự cố mà không che dữ liệu.
Kiểm toán viên cần biết ai đã kích hoạt thay đổi, thuộc tính nào đổi, nguồn nào gửi và request nào thực hiện; log hiện chỉ lưu trạng thái HTTP cuối cùng.
Một connector ngừng hoạt động nhiều giờ; sự kiện Joiner, Mover và Leaver tích tụ trong hàng đợi và cần được xử lý theo thứ tự để tránh cấp lại quyền cũ.
HR gửi hai sự kiện cập nhật liên tiếp nhưng mạng đảo thứ tự; payload cũ đến sau và ghi đè department mới nhất của nhân viên tại ứng dụng đích.
Hai nguồn danh tính cùng provision một tài khoản vào một ứng dụng; mỗi nguồn có quy tắc quản lý active và manager khác nhau nên trạng thái User thay đổi qua lại.
Một đợt tái cấu trúc tổ chức thay đổi hàng nghìn phòng ban và nhóm; nhóm vận hành cần đối chiếu toàn bộ tài khoản và membership để phát hiện bản ghi mồ côi hoặc sai lệch.
Ứng dụng đích đã có tài khoản không còn tồn tại ở nguồn danh tính; quy trình reconciliation cần quyết định cách xử lý tài khoản mồ côi mà không vô hiệu nhầm tài khoản dịch vụ.
Một nhân viên chuyển sang bộ phận đang bị điều tra; sự kiện rời nhóm cũ và thêm vào nhóm mới đến gần như đồng thời, trong khi ứng dụng đích xử lý bất đồng bộ.
Thuộc tính địa chỉ nhà và số định danh cá nhân không cần thiết cho mục đích cấp tài khoản; connector vẫn đồng bộ toàn bộ hồ sơ nhân sự sang ứng dụng đích.
Một ứng dụng đích yêu cầu lưu dữ liệu người dùng trong khu vực địa lý cụ thể; connector trung tâm đang gửi cùng payload đến endpoint ở khu vực khác mà không xét thuộc tính residency.
Nhóm bảo mật cần phát hiện tài khoản chưa bị vô hiệu sau khi nhân viên nghỉ việc; dashboard hiện chỉ theo dõi số request SCIM thành công chứ không đối chiếu thời gian hoàn tất deprovision.
Nhà cung cấp ứng dụng thay đổi giới hạn kích thước request và số thao tác Bulk; connector không cập nhật cấu hình nên các batch lớn thất bại trong khi batch nhỏ vẫn thành công.
Chính sách lưu trữ yêu cầu giữ hồ sơ nhân viên đã nghỉ để phục vụ kiểm toán; ứng dụng đích hỗ trợ cả active=false và DELETE nhưng connector luôn xóa vật lý User khi nhận sự kiện Leaver.

Một cổng API phát access token có thời hạn 24 giờ và không có cơ chế thu hồi khi nhân viên rời khỏi tổ chức.
Một dịch vụ dùng opaque token nhưng không lưu metadata về chủ thể, audience, scope và thời hạn nên khó kiểm soát quyền của từng token.
Một ứng dụng dùng JWT có chữ ký hợp lệ nhưng không kiểm tra claim audience, khiến token dành cho dịch vụ này được chấp nhận ở dịch vụ khác.
Máy chủ xác minh JWT chỉ kiểm tra chữ ký mà bỏ qua issuer, expiration và not-before, dẫn đến token sai ngữ cảnh vẫn được chấp nhận.
Một API chấp nhận JWT với thuật toán none do thư viện xác minh được cấu hình cho phép thuật toán không an toàn.
Token ký bất đối xứng được xác minh bằng khóa lấy từ header do client cung cấp mà không kiểm tra nguồn tin cậy.
Một hệ thống JWT chấp nhận nhiều thuật toán ký nhưng không ràng buộc thuật toán dự kiến với loại khóa tương ứng.
Ứng dụng lấy khóa xác minh từ JWKS endpoint nhưng không xử lý an toàn khi kid không tồn tại hoặc endpoint bị gián đoạn.
Nhà cung cấp danh tính xoay vòng signing key nhưng các dịch vụ tiêu thụ vẫn cache khóa cũ quá lâu và từ chối token mới hợp lệ.
Một khóa ký token bị lộ, nhưng tổ chức chưa có quy trình khẩn cấp để thay khóa, thu hồi token và cập nhật các dịch vụ xác minh.
Access token chứa thông tin cá nhân và quyền chi tiết trong payload, sau đó bị ghi vào log của proxy và hệ thống giám sát.
Ứng dụng truyền bearer token trong query string của URL, khiến token xuất hiện trong browser history, access log và header Referer.
Người dùng lưu access token dài hạn trong local storage của trình duyệt và token bị lấy cắp qua lỗ hổng XSS.
Một ứng dụng web đặt refresh token trong cookie nhưng thiếu thuộc tính bảo vệ phù hợp và không có biện pháp chống CSRF.
Mobile app lưu refresh token dạng plaintext trong vùng lưu trữ có thể bị trích xuất khi thiết bị bị root hoặc jailbreak.
Một nhân viên gửi token truy cập qua email để đồng nghiệp xử lý sự cố, và token tiếp tục có hiệu lực sau khi email bị chuyển tiếp.
Kẻ tấn công lấy được bearer token từ máy trạm bị nhiễm mã độc và sử dụng token từ một thiết bị khác mà hệ thống không phát hiện.
Một API chấp nhận cùng một token cho nhiều yêu cầu nhạy cảm lặp lại, dù giao dịch cần chống phát lại.
Webhook receiver xác minh chữ ký payload nhưng không kiểm tra timestamp hoặc event identifier, cho phép phát lại một sự kiện thanh toán.
Một hệ thống dùng JWT stateless và không có cơ chế denylist hoặc introspection, nên logout không vô hiệu hóa token đã phát hành.
Người dùng bị thu hồi quyền trong hệ thống nguồn nhưng access token cũ vẫn cho phép thao tác đến hết thời hạn.
Refresh token có thể được dùng nhiều lần và hệ thống không phát hiện việc token cũ bị sử dụng sau khi đã đổi token mới.
Một refresh token bị đánh cắp được dùng để tạo access token mới trong nhiều ngày vì không có rotation hoặc reuse detection.
Ứng dụng cấp refresh token với thời hạn không giới hạn và không yêu cầu xác thực lại sau thời gian dài không hoạt động.
Người dùng đăng xuất khỏi thiết bị hiện tại nhưng refresh token trên thiết bị thất lạc vẫn có thể tiếp tục tạo phiên mới.
Một hệ thống OAuth cấp scope rộng như admin cho ứng dụng bên thứ ba dù ứng dụng chỉ cần đọc một loại dữ liệu.
API chỉ kiểm tra token hợp lệ mà không kiểm tra scope cần thiết cho từng hành động và tài nguyên.
Token có claim tenant ID do client tự chọn và backend tin claim đó mà không đối chiếu với danh tính hoặc quyền được cấp.
Một dịch vụ nhận token hợp lệ từ service trung gian nhưng không xác minh audience, dẫn đến confused deputy và truy cập vượt quyền.
Token exchange giữa hai dịch vụ giữ nguyên mọi quyền của token gốc dù dịch vụ đích chỉ cần một tập quyền nhỏ hơn.
ID token được gửi trực tiếp đến API như access token, trong khi API không phân biệt mục đích và audience của hai loại token.
Ứng dụng chấp nhận token từ issuer thử nghiệm vì danh sách issuer tin cậy được cấu hình quá rộng.
Một hệ thống liên kết nhiều identity provider nhưng không ràng buộc issuer và subject, dẫn đến hai danh tính khác nhau bị gộp thành một tài khoản.
Máy chủ chấp nhận token đã hết hạn do đồng hồ giữa các hệ thống lệch nhau và khoảng clock skew được cấu hình quá rộng.
Token được cache ở gateway sau khi quyền đã bị thu hồi, nhưng cache không được làm mới hoặc vô hiệu hóa theo sự kiện.
API key dùng chung giữa nhiều khách hàng không có định danh riêng, hạn mức riêng hoặc khả năng thu hồi độc lập.
Personal access token của nhân viên có quyền quản trị và thời hạn dài, nhưng không có quy trình rà soát hoặc thay mới định kỳ.
Token của tài khoản dịch vụ được nhúng trong image container và vô tình xuất hiện trong registry mà nhiều người có thể đọc.
Một pipeline CI/CD in token vào log khi lệnh xác thực thất bại, và log được chia sẻ với nhiều nhóm bên ngoài dự án.
Token ký bằng khóa bí mật chung được phân phối đến nhiều nhóm, khiến không thể xác định dịch vụ nào đã phát hành token giả.
Ứng dụng chỉ mã hóa token trong cơ sở dữ liệu nhưng tất cả máy chủ đều dùng chung khóa giải mã lưu trong cùng cấu hình.
Một hệ thống dùng token tự chứa nhưng không có phiên bản schema hoặc key identifier rõ ràng, gây lỗi khi thay đổi claim và khóa.
Thiết bị IoT ngoại tuyến cần xác thực lâu dài bằng token nhưng không thể nhận thông tin thu hồi kịp thời khi bị mất hoặc bán lại.
Ứng dụng cấp token cho thiết bị qua device authorization flow nhưng trang xác nhận không hiển thị rõ thiết bị và tài khoản đang được liên kết.
Kẻ tấn công lừa người dùng nhập mã device authorization vào trang giả mạo và hoàn tất việc cấp token cho thiết bị của chúng.
Một API nhận token qua header nhưng không bắt buộc TLS trên toàn bộ đường truyền nội bộ, khiến token có thể bị nghe lén.
Hệ thống xác minh token tại gateway nhưng các endpoint nội bộ vẫn có thể được gọi trực tiếp mà không thực hiện kiểm tra tương đương.
Một token bị lộ trong sự cố nhưng đội vận hành chỉ đổi khóa ký mà không đánh giá token đang hoạt động, phiên, log và bản sao lưu.
Audit log chỉ ghi nhận request thành công mà không ghi token identifier, issuer, subject hoặc lý do từ chối ở mức an toàn.
Một tổ chức cần điều tra hành vi lạm dụng token nhưng không thể liên kết các lần sử dụng vì thiếu token ID hoặc correlation ID đã được bảo vệ.
Quy trình thu hồi token cập nhật ở identity provider nhưng các gateway, cache và dịch vụ downstream không nhận được sự kiện đồng bộ.
Nhóm vận hành phát hiện nhiều lần xác minh chữ ký thất bại và token sai audience nhưng không có cảnh báo hoặc giới hạn thử nghiệm.
Token có quyền đọc dữ liệu nhạy cảm được cấp cho ứng dụng phân tích bên ngoài mà không có thời hạn, giới hạn tài nguyên hoặc quy trình rà soát.
Ứng dụng hỗ trợ nhiều định dạng token nhưng không xác định rõ ưu tiên và quy tắc xác minh, dẫn đến cùng một request được diễn giải khác nhau giữa các thành phần.
Một hệ thống cần chuyển từ shared signing secret sang asymmetric signing nhưng chưa có kế hoạch tương thích, phân phối public key và thu hồi khóa cũ.

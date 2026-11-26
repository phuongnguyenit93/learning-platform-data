Một doanh nghiệp kết nối ứng dụng nhân sự với IdP của đối tác; hai bên cấu hình EntityID khác nhau giữa metadata và AuthnRequest nên SP không xác định được đúng đối tác phát hành phản hồi.
SP tiếp tục dùng metadata đã lưu từ nhiều tháng trước sau khi IdP thay chứng thư ký; các đăng nhập mới thất bại dù IdP đã phát hành assertion hợp lệ bằng chứng thư mới.
IdP công bố đồng thời chứng thư ký cũ và mới trong giai đoạn rollover nhưng một số SP chỉ tải chứng thư đầu tiên, khiến kết quả xác minh khác nhau giữa các ứng dụng.
Một SP tự động tải metadata từ URL do quản trị viên tenant nhập; URL bị thay đổi sang máy chủ nội bộ và tiến trình cập nhật metadata phát sinh yêu cầu tới địa chỉ ngoài dự kiến.
Đội tích hợp nhận metadata có chữ ký số nhưng tin cậy chứng thư ký metadata chỉ vì chứng thư nằm ngay trong tài liệu đó, không có bước xác lập trust độc lập.
SP xác minh chữ ký HTTP Redirect binding sau khi giải mã và tái tạo query string; cách chuẩn hóa tham số làm chữ ký hợp lệ của IdP bị từ chối không nhất quán.
IdP gửi SAML Response qua HTTP POST binding; SP chỉ kiểm tra chữ ký Response trong khi chính sách đối tác yêu cầu assertion được ký riêng.
SP chấp nhận assertion có chữ ký hợp lệ nhưng bỏ qua trạng thái chữ ký của Response và các trường liên quan nằm bên ngoài assertion, tạo khác biệt giữa dữ liệu được xác thực và dữ liệu được sử dụng.
Một thông điệp SAML chứa hai phần tử Assertion có cùng ID; thư viện xác minh chữ ký và bộ xử lý nghiệp vụ chọn hai phần tử khác nhau.
SP xác minh chữ ký trên một node XML nhưng sau bước parse lại, bộ xử lý chọn Assertion khác có cùng định danh logic do cấu trúc XML Signature Wrapping.
Hai thành phần trong SP áp dụng quy tắc canonicalization XML khác nhau; một thành phần xác minh chữ ký thành công trong khi thành phần kia diễn giải nội dung assertion khác.
IdP vẫn ký thông điệp bằng thuật toán chữ ký đã lỗi thời do cấu hình tương thích cũ; SP không có chính sách giới hạn thuật toán được chấp nhận.
Parser XML của SP cho phép external entity; một assertion được chế tạo khiến parser truy cập tài nguyên cục bộ trong môi trường xử lý.
Một SAML Response có cấu trúc XML lồng sâu và thực thể mở rộng lớn làm tiến trình xác minh tiêu thụ CPU và bộ nhớ vượt giới hạn trong giờ cao điểm.
SP xác minh chữ ký assertion thành công nhưng không kiểm tra AudienceRestriction; assertion phát hành cho một SP khác vẫn được dùng để tạo phiên.
SP bỏ qua Recipient trong SubjectConfirmationData; assertion gửi tới ACS của môi trường thử nghiệm được chấp nhận ở môi trường production.
IdP đặt Destination khác URL ACS đã đăng ký; SP chỉ dựa vào chữ ký mà không đối chiếu đích nhận với endpoint được cấu hình.
SP xây dựng ACS URL dựa trên Host header do request bên ngoài cung cấp; request giả mạo Host khiến URL đích được dùng trong kiểm tra SAML không còn là endpoint đã đăng ký.
Một SP xử lý phản hồi IdP-initiated nhưng vẫn yêu cầu InResponseTo khớp AuthnRequest nội bộ, khiến luồng đăng nhập không có request tương ứng bị lỗi.
Trong SP-initiated flow, InResponseTo của Response không khớp ID AuthnRequest đang chờ nhưng SP vẫn tạo phiên cho người dùng.
Hai instance SP dùng replay cache riêng; cùng một Assertion ID được gửi lặp qua hai instance và cả hai đều tạo phiên thành công.
SP giữ Assertion ID trong replay cache ngắn hơn thời hạn assertion; một assertion đã dùng được phát lại sau khi bản ghi chống replay hết hạn.
Đồng hồ IdP nhanh hơn SP vài phút; assertion có NotBefore ở tương lai bị từ chối hàng loạt dù thời gian thực của người dùng vẫn nằm trong cửa sổ hợp lệ.
SP đặt clock skew quá rộng để tránh lỗi đồng hồ; assertion đã hết hạn đáng kể vẫn vượt qua kiểm tra điều kiện thời gian.
SP dùng NotOnOrAfter của assertion làm thời hạn phiên cục bộ dù chính sách tổ chức quy định thời lượng phiên ngắn hơn, khiến phiên vượt giới hạn đã phê duyệt.
SP nhận RelayState là URL chuyển hướng từ trình duyệt và chuyển người dùng tới đích tùy ý sau khi đăng nhập thành công.
RelayState không được ràng buộc với luồng đăng nhập ban đầu; người dùng có thể bị đưa về một trạng thái ứng dụng khác với nơi họ đã bắt đầu xác thực.
Một IdP-initiated login không có request ID do SP tạo; hệ thống gặp khó khăn khi liên kết phản hồi với phiên trình duyệt đã bắt đầu quy trình.
SP hỗ trợ nhiều IdP cho nhiều tenant nhưng chỉ kiểm tra chữ ký, không ràng buộc Issuer với tenant đang đăng nhập, dẫn tới nguy cơ nhận assertion từ sai tổ chức.
SP bỏ qua Issuer trong Response vì chứng thư ký đã được tin cậy; một đối tác khác dùng cùng hạ tầng chứng thư khiến nguồn phát hành không được phân biệt đúng.
Ứng dụng dùng email làm khóa tài khoản SAML; sau khi nhân viên đổi email và địa chỉ cũ được cấp cho người khác, đăng nhập có thể gắn nhầm vào hồ sơ hiện hữu.
SP coi transient NameID là định danh bền vững; cùng một người nhận NameID khác ở lần đăng nhập sau và bị tạo thành nhiều tài khoản.
Hai tenant nhận cùng giá trị persistent NameID nhưng SP không đưa ngữ cảnh tổ chức vào khóa liên kết tài khoản, dẫn tới va chạm danh tính xuyên tenant.
IdP gửi thuộc tính email nhưng SP không xác minh mức độ tin cậy hoặc nguồn phát hành; thuộc tính bị dùng để tự động liên kết với tài khoản nội bộ.
SP ánh xạ trực tiếp giá trị group từ assertion thành vai trò quản trị; một thay đổi group ở IdP cấp quyền cao hơn dự kiến cho người dùng.
IdP gửi danh sách group cũ do đồng bộ chậm sau khi nhân viên chuyển phòng ban; SP tiếp tục cấp quyền theo nhóm trước đó.
SP nhận quá nhiều thuộc tính cá nhân trong assertion dù ứng dụng chỉ cần định danh và đơn vị; dữ liệu nhạy cảm bị sao chép vào log và phiên ứng dụng.
SP diễn giải AuthnContextClassRef ở mức xác thực mật khẩu như bằng chứng MFA; ứng dụng cho phép truy cập thao tác nhạy cảm mà không có xác thực tăng cường.
SP gửi AuthnRequest có ForceAuthn cho thao tác tài chính nhưng không kiểm tra AuthnInstant và AuthnContext trong assertion trả về, nên xác thực cũ hoặc yếu vẫn được chấp nhận.
SP giữ nguyên session ID trước đăng nhập sau khi nhận assertion hợp lệ; một session đã được thiết lập trước đó tiếp tục được nâng thành phiên đã xác thực.
Người dùng đăng xuất khỏi SP nhưng phiên tại IdP vẫn hoạt động; lần truy cập tiếp theo tự đăng nhập lại mà người dùng không thấy bước xác thực.
SP gửi LogoutRequest nhưng không xác minh chữ ký và SessionIndex; một thông điệp giả có thể kết thúc phiên của người dùng khác.
Chính sách trình duyệt hạn chế cross-site POST và cookie tương quan trong luồng Single Logout front-channel; một số SP không liên kết được thông điệp logout với phiên cục bộ.
Một người dùng có nhiều phiên SAML trên nhiều thiết bị; SP xử lý SessionIndex không đầy đủ nên chỉ một phần phiên bị kết thúc khi logout.
SP dùng cùng một chứng thư cho ký thông điệp và giải mã assertion; khi xoay vòng chứng thư, việc thu hồi một mục đích ảnh hưởng ngoài dự kiến tới mục đích còn lại.
IdP mã hóa assertion bằng chứng thư SP cũ sau khi SP đã thay khóa giải mã; một số đăng nhập thất bại trong giai đoạn chuyển đổi chứng thư.
SP tin assertion đã mã hóa là đáng tin mà không xác minh nguồn phát hành và chữ ký; nội dung bí mật được giải mã nhưng không có bảo đảm xác thực phù hợp.
SP sử dụng Artifact binding nhưng endpoint ArtifactResolution của IdP không được ràng buộc đúng với đối tác đã thiết lập trust.
Một SAML Artifact bị phát lại tới ArtifactResolution Service; SP không nhận diện artifact đã được tiêu thụ và xử lý assertion nhiều lần.
SP yêu cầu chữ ký AuthnRequest nhưng một số node gửi request không ký do cấu hình metadata không đồng nhất, khiến hành vi giữa các node khác nhau.
Private key ký của IdP bị lộ; tổ chức tiếp tục tin cậy chứng thư hiện tại trong metadata và chưa xác định được assertion giả mạo nào đã được phát hành.
Log chẩn đoán lưu nguyên SAML Response và assertion chứa NameID cùng thuộc tính nhân sự; nhiều nhóm vận hành có thể đọc dữ liệu vượt nhu cầu công việc.
SP duy trì phiên cục bộ dài hơn thời hạn và trạng thái tài khoản tại IdP; nhân viên đã bị vô hiệu hóa vẫn truy cập được ứng dụng qua phiên cũ.
Một SP có nhiều ACS endpoint cho các môi trường và vùng dữ liệu; Response hợp lệ về chữ ký nhưng được gửi tới ACS không thuộc tenant tương ứng.
Metadata của đối tác chứa nhiều endpoint và binding; SP chọn endpoint dựa trên thứ tự phần tử thay vì endpoint đã được phê duyệt cho dịch vụ.
Đội vận hành thay chứng thư TLS của endpoint metadata và nhầm chứng thư TLS với chứng thư ký SAML, dẫn tới trust bị cấu hình sai.
SP chỉ kiểm tra chữ ký assertion nhưng không kiểm tra trạng thái tài khoản và quyền hiện tại sau khi tài khoản bị khóa tại nguồn danh tính.
IdP thay đổi NameID format từ email sang persistent nhưng SP không có kế hoạch chuyển đổi ánh xạ, khiến người dùng hiện tại bị tạo tài khoản mới.
Một đối tác dùng IdP-initiated flow cho ứng dụng nhạy cảm; SP chấp nhận unsolicited response mà không có biện pháp chống login CSRF, khiến trình duyệt người dùng có thể bị đưa vào phiên của tài khoản do kẻ khác kiểm soát.
SP hỗ trợ nhiều chứng thư ký cùng lúc nhưng không ghi nhận key ID hoặc thời điểm rollover trong audit, khiến điều tra sự cố không xác định được khóa nào đã xác minh assertion.
Assertion được gửi qua POST binding và người dùng mở lại trang kết quả trong trình duyệt; SP xử lý lại payload đã dùng mà không có kiểm soát replay theo Assertion ID.
SP chấp nhận SubjectConfirmation có Method không thuộc loại đã cấu hình dù SubjectConfirmationData có Recipient đúng, làm luồng xác nhận chủ thể lệch chính sách liên kết.

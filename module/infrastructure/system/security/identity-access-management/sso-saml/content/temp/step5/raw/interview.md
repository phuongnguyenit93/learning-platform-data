Bạn sẽ mô tả vai trò của Identity Provider (IdP) và Service Provider (SP) trong một giao dịch SAML 2.0 như thế nào?
Bạn phân biệt SAML authentication assertion với authorization decision và các loại statement khác ra sao?
Bạn giải thích mối quan hệ giữa EntityID, metadata, endpoint và khóa ký của một IdP hoặc SP như thế nào?
Bạn thiết kế quy trình trao đổi metadata ban đầu giữa hai tổ chức như thế nào để xác minh đúng đối tác và thiết lập trust?
Bạn đánh giá những trường metadata nào cần kiểm tra trước khi chấp nhận cấu hình liên kết danh tính từ đối tác?
Bạn bảo vệ metadata được công bố hoặc trao đổi như thế nào để ngăn kẻ tấn công thay endpoint hay khóa tin cậy?
Bạn xác minh chữ ký của metadata hoặc metadata aggregate như thế nào, và quản lý trust anchor dùng để xác minh ra sao?
Bạn quản lý vòng đời metadata, thời hạn cập nhật và phát hiện metadata cũ hoặc bị thay đổi bất thường ra sao?
Bạn thiết kế quy trình rollover chứng thư ký SAML như thế nào để chuyển khóa mới mà không làm gián đoạn đăng nhập?
Bạn xử lý thế nào khi IdP và SP không đồng bộ thời điểm rollover hoặc một bên vẫn ký bằng chứng thư cũ?
Bạn phân biệt chứng thư X.509 dùng trong metadata SAML với việc xác minh danh tính website theo mô hình TLS PKI thông thường như thế nào?
Bạn lựa chọn và kiểm soát HTTP Redirect, HTTP POST, HTTP Artifact và các binding SAML khác theo yêu cầu triển khai ra sao?
Bạn giải thích cách HTTP Redirect binding dùng DEFLATE, Base64 và URL encoding, đồng thời ký các tham số query theo quy tắc binding ra sao?
Bạn đánh giá ưu điểm và đánh đổi của HTTP POST binding khi gửi response hoặc assertion qua trình duyệt như thế nào?
Bạn lựa chọn Artifact binding trong tình huống nào và bảo vệ kênh artifact resolution giữa các bên ra sao?
Bạn thiết kế luồng SP-initiated SSO từ lúc người dùng truy cập SP đến khi assertion được chấp nhận như thế nào?
Bạn phân tích các bước của IdP-initiated SSO và những rủi ro khác biệt so với luồng SP-initiated ra sao?
Bạn quyết định có cho phép IdP-initiated SSO hay không dựa trên threat model và nhu cầu nghiệp vụ nào?
Bạn sử dụng AuthnRequest ID và InResponseTo như thế nào để liên kết response với yêu cầu đăng nhập ban đầu?
Bạn bảo đảm AuthnRequest có tính khó đoán, không bị giả mạo và được kiểm tra đúng theo metadata của đối tác ra sao?
Bạn giải thích vai trò của Destination, AssertionConsumerServiceURL và ACS endpoint trong việc định tuyến response như thế nào?
Bạn kiểm tra Recipient và Destination ra sao để ngăn assertion hoặc response bị gửi tới endpoint không được tin cậy?
Bạn xử lý thế nào khi một IdP gửi response tới ACS URL khác với URL đã đăng ký trong metadata?
Bạn phân biệt Response, Assertion, Subject, NameID, Conditions, AuthnStatement và AttributeStatement trong thông điệp SAML như thế nào?
Bạn lựa chọn NameID format persistent, transient hoặc email address theo mục đích liên kết tài khoản ra sao?
Bạn xử lý thế nào khi email trong assertion thay đổi nhưng định danh ổn định của người dùng vẫn giữ nguyên?
Bạn thiết kế account linking để tránh liên kết nhầm hai tài khoản có cùng email hoặc thuộc hai tenant khác nhau như thế nào?
Bạn xác định thuộc tính nào được phép dùng làm định danh chính và thuộc tính nào chỉ nên dùng cho hiển thị hoặc nghiệp vụ ra sao?
Bạn xây dựng quy tắc mapping attribute từ IdP sang hồ sơ nội bộ như thế nào để tránh tin cậy quá mức vào dữ liệu do đối tác cung cấp?
Bạn kiểm soát việc ánh xạ group, role và entitlement từ assertion sang quyền truy cập theo nguyên tắc least privilege ra sao?
Bạn xử lý thuộc tính bị thiếu, trùng lặp, sai kiểu hoặc vượt kích thước mong đợi trong assertion như thế nào?
Bạn thiết kế quy trình xác minh chữ ký XML của SAML response và assertion như thế nào để chỉ chấp nhận chữ ký từ khóa đã tin cậy?
Bạn phân biệt trường hợp response được ký, assertion được ký và cả hai cùng được ký; SP cần xác định đối tượng nào đã được bảo vệ ra sao?
Bạn bảo đảm SP chỉ sử dụng đúng assertion element đã được xác minh chữ ký như thế nào?
Bạn giải thích XML Signature Wrapping attack và cách kiểm tra cấu trúc XML để ngăn việc ứng dụng đọc assertion khác với assertion đã ký ra sao?
Bạn lựa chọn canonicalization và signature transform an toàn như thế nào để tránh khác biệt diễn giải giữa các parser?
Bạn đánh giá rủi ro khi đối tác còn dùng thuật toán chữ ký yếu hoặc đã lỗi thời, và xây dựng kế hoạch loại bỏ ra sao?
Bạn xử lý KeyInfo trong XML Signature như thế nào để không vô tình tin một khóa do chính thông điệp không đáng tin cậy cung cấp?
Bạn thiết kế chính sách mã hóa assertion khi thông tin định danh hoặc thuộc tính nhạy cảm đi qua trình duyệt như thế nào?
Bạn phân biệt mục đích và thứ tự xử lý giữa ký và mã hóa assertion, đồng thời đánh giá tác động khi giải mã thất bại ra sao?
Bạn quản lý chứng thư mã hóa riêng với chứng thư ký như thế nào để giới hạn phạm vi ảnh hưởng khi một khóa bị lộ?
Bạn xác minh Issuer của response và assertion như thế nào khi một SP liên kết với nhiều IdP?
Bạn kiểm tra StatusCode của SAML response ra sao và xử lý các trạng thái lỗi hoặc trạng thái phụ như thế nào?
Bạn xác minh Conditions, NotBefore và NotOnOrAfter như thế nào để kiểm soát thời gian hiệu lực của assertion?
Bạn chọn clock skew tolerance ra sao khi các bên có sai lệch đồng hồ, và làm thế nào để tránh mở rộng cửa sổ replay quá mức?
Bạn kiểm tra AudienceRestriction như thế nào để assertion chỉ được chấp nhận bởi đúng SP dự kiến?
Bạn áp dụng các điều kiện OneTimeUse và ProxyRestriction như thế nào khi assertion có chứa những giới hạn này?
Bạn xác minh SubjectConfirmationData, Recipient, InResponseTo và thời hạn bearer confirmation ra sao?
Bạn xây dựng replay cache dựa trên Assertion ID hoặc message ID như thế nào để một assertion không thể được sử dụng nhiều lần?
Bạn xác định thời gian lưu replay cache phù hợp với cửa sổ hiệu lực assertion và độ lệch đồng hồ như thế nào?
Bạn xử lý response đến trễ, response lặp hoặc response đến sau khi phiên đăng nhập đã hết hạn ra sao?
Bạn bảo vệ RelayState như thế nào để duy trì điều hướng sau đăng nhập mà không tạo open redirect hoặc sửa đổi trạng thái?
Bạn liên kết RelayState với request hoặc phiên người dùng ban đầu như thế nào để giảm nguy cơ login CSRF?
Bạn phân tích nguy cơ unsolicited response và login CSRF trong IdP-initiated SSO, rồi lựa chọn biện pháp giảm thiểu ra sao?
Bạn bảo vệ ACS endpoint trước request giả mạo, flood và thông điệp SAML có kích thước bất thường như thế nào?
Bạn giới hạn kích thước XML, độ sâu cây, số phần tử và thời gian parse ra sao để giảm nguy cơ denial of service?
Bạn cấu hình bộ phân tích XML an toàn như thế nào để vô hiệu hóa DTD, external entity và truy cập tài nguyên ngoài?
Bạn kiểm soát schema validation, XInclude và tải schema từ xa trong quá trình xử lý thông điệp SAML như thế nào?
Bạn đánh giá rủi ro XML entity expansion và các kiểu parser exhaustion khác trong endpoint SAML ra sao?
Bạn bảo đảm lỗi xác minh chữ ký hoặc lỗi parse không làm lộ nội dung assertion, khóa, đường dẫn nội bộ hay chi tiết hạ tầng như thế nào?
Bạn thiết kế logging và audit cho giao dịch SAML như thế nào để hỗ trợ điều tra mà không ghi assertion hoặc thuộc tính nhạy cảm quá mức?
Bạn chọn correlation ID và dữ liệu log nào để nối một lần đăng nhập qua IdP, trình duyệt và SP mà không ghi lại bí mật?
Bạn xử lý sự cố khi signing key của IdP bị lộ như thế nào, từ xác định phạm vi ảnh hưởng đến thu hồi trust và buộc xác thực lại?
Bạn thiết kế quy trình ứng phó khi metadata hoặc endpoint của đối tác bị thay đổi trái phép như thế nào?
Bạn quản lý trust với nhiều IdP trong một SP ra sao để tránh nhầm issuer, dùng nhầm khóa hoặc chấp nhận assertion từ tenant khác?
Bạn thiết kế tenant discovery và lựa chọn IdP như thế nào để người dùng không thể tự ý chuyển sang một identity provider ngoài dự kiến?
Bạn xử lý thay đổi domain, đổi EntityID hoặc hợp nhất tổ chức ở phía IdP như thế nào để không chiếm đoạt liên kết tài khoản hiện hữu?
Bạn thiết kế SAML Single Logout (SLO) và phân biệt luồng front-channel với back-channel như thế nào?
Bạn xử lý tình huống một SP không nhận được LogoutRequest hoặc LogoutResponse trong quy trình SLO ra sao?
Bạn xác định phạm vi logout khi một người dùng có nhiều phiên, nhiều SP hoặc nhiều trình duyệt như thế nào?
Bạn xác minh chữ ký, Issuer, Destination và SessionIndex trong LogoutRequest như thế nào trước khi kết thúc phiên?
Bạn xử lý lỗi logout một phần như thế nào để người dùng hiểu trạng thái phiên còn tồn tại ở IdP hoặc SP nào?
Bạn quyết định thời điểm tạo phiên cục bộ và thời điểm cấp quyền truy cập sau khi assertion đã được xác minh như thế nào?
Bạn diễn giải AuthnInstant và SessionNotOnOrAfter như thế nào khi quyết định thời hạn phiên xác thực và phiên cục bộ của SP?
Bạn bảo vệ phiên SP sau SSO bằng timeout, thu hồi, xoay session identifier và kiểm soát liên kết với phiên IdP ra sao?
Bạn thiết kế quy trình step-up authentication hoặc ForceAuthn khi tài nguyên yêu cầu mức xác thực cao hơn như thế nào?
Bạn phân biệt ForceAuthn và IsPassive, đồng thời xác định trường hợp nào phù hợp với từng yêu cầu nghiệp vụ?
Bạn xử lý AuthnContextClassRef như thế nào để SP đánh giá mức độ xác thực mà IdP tuyên bố?
Bạn xác minh yêu cầu MFA hoặc mức assurance trong assertion ra sao thay vì chỉ dựa vào việc người dùng đã đăng nhập thành công?
Bạn xây dựng kiểm thử liên thông giữa các IdP và SP khác nhau như thế nào để phát hiện khác biệt binding, chữ ký, NameID và attribute?
Bạn kiểm thử các trường hợp assertion hết hạn, sai audience, sai recipient, issuer không khớp, chữ ký sai và replay như thế nào?
Bạn thiết kế kiểm thử bảo mật cho XML Signature Wrapping, RelayState manipulation, XXE, request tampering và login CSRF ra sao?
Bạn quản lý thay đổi cấu hình SAML theo môi trường như thế nào để tránh dùng nhầm EntityID, ACS URL hoặc chứng thư giữa staging và production?
Bạn đánh giá mức độ sẵn sàng của liên kết SAML khi IdP ngừng hoạt động, metadata không truy cập được hoặc chứng thư sắp hết hạn ra sao?
Bạn xây dựng giám sát cho tỷ lệ đăng nhập thành công, lỗi chữ ký, assertion hết hạn, replay bị chặn và lỗi SLO như thế nào?
Bạn xác định tiêu chí chấp nhận một tích hợp SAML mới và bằng chứng cần lưu để kiểm toán quan hệ tin cậy ra sao?
Bạn rà soát định kỳ quyền truy cập, attribute mapping, chứng thư và đối tác liên kết như thế nào để loại bỏ cấu hình không còn cần thiết?

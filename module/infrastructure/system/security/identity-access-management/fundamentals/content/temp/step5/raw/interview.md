Bạn định nghĩa danh tính số và phân biệt danh tính, tài khoản, principal và thông tin xác thực trong một hệ thống IAM như thế nào?
Bạn thiết kế quy trình identity proofing cho người dùng đăng ký từ xa như thế nào để cân bằng độ tin cậy, trải nghiệm và nguy cơ giả mạo?
Làm thế nào để xác định mức độ bảo đảm danh tính và mức độ bảo đảm xác thực phù hợp với từng loại giao dịch?
Bạn tổ chức quy trình cấp tài khoản cho nhân sự mới như thế nào để quyền ban đầu phù hợp với vai trò và được phê duyệt đúng thẩm quyền?
Khi nhân sự chuyển phòng ban hoặc thay đổi trách nhiệm, bạn cập nhật quyền và xử lý quyền cũ như thế nào để tránh tích lũy đặc quyền?
Bạn bảo đảm thu hồi tài khoản, phiên và credential khi nhân sự nghỉ việc hoặc hợp đồng kết thúc ra sao?
Bạn chọn nguồn dữ liệu danh tính có thẩm quyền nào và xử lý xung đột giữa HR, directory và hệ thống nghiệp vụ như thế nào?
Vì sao nên dùng định danh bất biến thay cho email hoặc username làm khóa liên kết danh tính giữa các hệ thống?
Bạn xử lý hai hồ sơ danh tính bị trùng hoặc một người có nhiều tài khoản như thế nào mà vẫn giữ được lịch sử kiểm toán?
Bạn phát hiện và xử lý orphaned account khi chủ sở hữu đã rời tổ chức hoặc không còn được xác định ra sao?
Bạn phân biệt authentication và authorization như thế nào trong một luồng truy cập từ lúc đăng nhập tới lúc thực hiện hành động?
Bạn đánh giá độ mạnh của các yếu tố xác thực dựa trên điều gì và kết hợp chúng thành MFA ra sao?
Bạn lựa chọn khi nào cần step-up authentication dựa trên độ nhạy của tài nguyên và rủi ro của giao dịch như thế nào?
Vì sao passkey hoặc security key có khả năng chống phishing tốt hơn OTP, và những điều kiện triển khai nào cần được bảo đảm?
Bạn giải thích cơ chế challenge-response của passkey/WebAuthn và cách relying party xác minh credential như thế nào?
TOTP hoạt động dựa trên yếu tố nào, và những rủi ro nào phát sinh từ việc chia sẻ hoặc lưu trữ seed bí mật?
Bạn phát hiện và giảm thiểu MFA fatigue hoặc push bombing như thế nào mà không làm gián đoạn người dùng hợp lệ?
Bạn lựa chọn password hashing algorithm, salt và work factor như thế nào để bảo vệ mật khẩu khi cơ sở dữ liệu bị lộ?
Bạn xây dựng chính sách mật khẩu dựa trên độ dài, mật khẩu phổ biến/bị lộ và khả năng sử dụng thay vì chỉ dựa vào quy tắc ký tự như thế nào?
Bạn chống credential stuffing và brute-force login bằng rate limiting, risk signal và kiểm soát theo tài khoản ra sao?
Bạn thiết kế quy trình account recovery như thế nào để người dùng hợp lệ lấy lại quyền truy cập mà kẻ tấn công không thể dễ dàng chiếm tài khoản?
Bạn xác minh danh tính khi đặt lại MFA hoặc thay đổi thông tin khôi phục như thế nào để tránh biến help desk thành đường vòng xác thực?
Bạn sử dụng adaptive authentication và risk-based access để đánh giá vị trí, thiết bị, hành vi và độ nhạy tài nguyên như thế nào?
Bạn xác định mức độ tin cậy của thiết bị trước khi cấp quyền truy cập và xử lý thiết bị không đạt posture policy ra sao?
Session fixation xảy ra trong tình huống nào và bạn ngăn kẻ tấn công tái sử dụng session identifier trước đăng nhập như thế nào?
Bạn cấu hình cookie session với Secure, HttpOnly và SameSite như thế nào cho từng luồng truy cập?
Khi xác thực thành công hoặc thay đổi đặc quyền, vì sao cần thay session identifier và bạn thực hiện việc đó ra sao?
Bạn lựa chọn idle timeout, absolute timeout và giới hạn thời gian phiên quản trị dựa trên mức rủi ro như thế nào?
Bạn thiết kế logout cục bộ và logout liên kết SSO như thế nào để phiên ở các hệ thống liên quan được xử lý nhất quán?
Bạn thu hồi session hoặc token đã cấp khi tài khoản bị xâm nhập mà không buộc toàn bộ người dùng đăng nhập lại như thế nào?
Bạn phân biệt access token và refresh token về mục đích, thời hạn sống và nơi lưu trữ như thế nào?
Bạn triển khai refresh token rotation và phát hiện reuse để hạn chế replay hoặc đánh cắp token ra sao?
Khi xác minh JWT, bạn kiểm tra chữ ký, thuật toán, issuer, audience và thời hạn như thế nào để tránh chấp nhận token sai ngữ cảnh?
Bạn lựa chọn opaque token hay self-contained token dựa trên nhu cầu introspection, thu hồi, khả năng mở rộng và độ trễ như thế nào?
Bạn phân biệt scope và audience, và làm thế nào để ngăn access token được dùng cho API ngoài dự kiến?
Bạn bảo vệ token trong ứng dụng trình duyệt như thế nào trước XSS, rò rỉ qua URL, log hoặc storage phía client?
OAuth 2.0 giải quyết bài toán ủy quyền nào, và vì sao không nên mặc định xem access token là bằng chứng đăng nhập người dùng?
Bạn thiết kế Authorization Code Flow với PKCE như thế nào cho public client để giảm nguy cơ interception và code injection?
Khi nào nên dùng Client Credentials Flow và làm thế nào để giới hạn quyền của client đại diện cho workload?
Device Authorization Grant phù hợp với loại thiết bị nào và bạn kiểm soát rủi ro phishing hoặc nhập sai user code ra sao?
Trong OpenID Connect, ID token khác access token ở mục đích sử dụng và đối tượng nhận như thế nào?
Bạn sử dụng state và nonce để bảo vệ các luồng OAuth/OIDC trước CSRF, login injection và replay như thế nào?
Bạn kiểm soát redirect URI trong OAuth/OIDC ra sao để ngăn open redirect và authorization code bị gửi tới địa chỉ không tin cậy?
SAML assertion chứa những thông tin nào và service provider cần xác minh điều gì trước khi tạo phiên đăng nhập?
Bạn thiết lập trust giữa identity provider và service provider như thế nào, bao gồm metadata, signing certificate và audience restriction?
Khi một người dùng bị vô hiệu hóa tại identity provider, bạn bảo đảm quyền truy cập liên kết ở các ứng dụng SaaS được thu hồi kịp thời ra sao?
Bạn sử dụng SCIM để tự động provisioning và deprovisioning danh tính giữa hệ thống nguồn và ứng dụng đích như thế nào?
Bạn xử lý sự cố SCIM khi một lần cập nhật thất bại giữa chừng hoặc retry tạo ra tài khoản trùng như thế nào?
Bạn thiết kế RBAC để ánh xạ trách nhiệm công việc thành role và permission mà không tạo quá nhiều role đặc thù ra sao?
Khi role explosion xuất hiện do nhiều ngoại lệ nghiệp vụ, bạn tái cấu trúc role và xử lý quyền tạm thời như thế nào?
Bạn sử dụng ABAC với subject, resource, action và environmental attributes để quyết định truy cập theo ngữ cảnh ra sao?
Trong trường hợp quyền phụ thuộc quan hệ như chủ sở hữu, thành viên nhóm hoặc người được chia sẻ, bạn áp dụng ReBAC như thế nào?
Bạn phân tách Policy Enforcement Point và Policy Decision Point trong kiến trúc authorization để các hệ thống thực thi chính sách nhất quán ra sao?
Bạn xác định quy tắc deny-by-default và xử lý xung đột giữa policy cho phép với policy từ chối như thế nào?
Bạn kiểm soát quyền kế thừa từ group, folder hoặc resource cha để tránh một thay đổi cấu trúc vô tình mở rộng truy cập ra sao?
Bạn áp dụng separation of duties cho các quy trình tạo, phê duyệt và thực hiện giao dịch nhạy cảm như thế nào?
Bạn triển khai just-in-time access để cấp quyền quản trị trong thời gian ngắn, có lý do và có phê duyệt như thế nào?
Bạn tổ chức Privileged Access Management để kiểm soát tài khoản admin, credential vault và phiên truy cập đặc quyền ra sao?
Bạn luân chuyển secret trong vault như thế nào để cập nhật credential ở workload mà không gây gián đoạn dịch vụ?
Bạn thiết kế tài khoản break-glass cho tình huống khẩn cấp như thế nào để vừa sẵn sàng sử dụng vừa được giám sát nghiêm ngặt?
Bạn ghi nhận và kiểm toán phiên quản trị đặc quyền như thế nào để có thể truy vết hành động mà vẫn bảo vệ dữ liệu nhạy cảm?
Bạn tổ chức access review định kỳ theo chủ sở hữu tài nguyên, mức độ rủi ro và thay đổi vai trò như thế nào?
Bạn quản lý danh tính của nhà thầu, đối tác và người dùng bên ngoài như thế nào để giới hạn phạm vi, thời hạn và sponsor chịu trách nhiệm?
Bạn thiết kế workload identity cho service, job và agent tự động như thế nào để tránh phụ thuộc vào tài khoản người dùng cá nhân?
Những rủi ro nào phát sinh khi workload dùng API key hoặc client secret tĩnh, và bạn thay thế chúng bằng cơ chế nào?
Bạn thiết lập workload identity federation giữa môi trường triển khai và cloud provider như thế nào để tránh lưu credential dài hạn?
Bạn quản lý machine identity và chứng thư số cho thiết bị, service hoặc workload như thế nào, bao gồm cấp phát, gia hạn và thu hồi?
Bạn kiểm kê non-human identities ra sao để phát hiện service account không còn chủ sở hữu, quyền dư thừa hoặc credential quá hạn?
Bạn giới hạn quyền và phạm vi token cho giao tiếp machine-to-machine như thế nào để một workload bị xâm nhập không thể truy cập lan rộng?
Bạn thiết kế audit trail cho thay đổi role, group membership, policy, MFA và đặc quyền như thế nào để điều tra được ai đã làm gì và khi nào?
Bạn tương quan sự kiện đăng nhập, thay đổi quyền và hành động trên tài nguyên trong SIEM như thế nào để phát hiện account takeover?
Bạn bảo vệ log IAM khỏi bị sửa hoặc xóa bởi chính tài khoản quản trị đang bị điều tra như thế nào?
Bạn cân bằng yêu cầu giám sát danh tính với quyền riêng tư khi log có IP, vị trí, thiết bị và hành vi người dùng như thế nào?
Zero Trust thay đổi quyết định cấp quyền theo danh tính, thiết bị, ngữ cảnh và tình trạng rủi ro trong suốt phiên ra sao?
Bạn cô lập danh tính và dữ liệu giữa các tenant trong môi trường SaaS như thế nào để ngăn truy cập chéo do lỗi policy hoặc cấu hình?
Bạn thiết kế quy trình yêu cầu, phê duyệt, cấp và tự động hết hạn quyền truy cập như thế nào để giảm thao tác thủ công?
Bạn đo lường hiệu quả chương trình IAM bằng các chỉ số như thời gian thu hồi quyền, quyền dư thừa, MFA coverage và tài khoản mồ côi ra sao?

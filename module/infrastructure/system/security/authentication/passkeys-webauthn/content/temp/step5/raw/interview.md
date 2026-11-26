Bạn sẽ giải thích passkey dùng mật mã khóa công khai để xác thực mà không cần chia sẻ mật khẩu với website như thế nào?
Bạn sẽ phân biệt WebAuthn, FIDO2 và CTAP về phạm vi chuẩn hóa cùng vai trò của từng thành phần ra sao?
Bạn sẽ mô tả quan hệ giữa relying party, client platform, authenticator và user agent trong một phiên WebAuthn như thế nào?
Bạn sẽ phân biệt platform authenticator với roaming authenticator theo nơi lưu khóa và cách người dùng tương tác ra sao?
Bạn sẽ so sánh passkey với mật khẩu, OTP và khóa bảo mật phần cứng về khả năng chống phishing và replay như thế nào?
Bạn sẽ xác định các trust boundary giữa website, browser, hệ điều hành, authenticator và hệ sinh thái đồng bộ passkey ra sao?
Bạn sẽ giải thích vì sao private key của passkey không được gửi tới relying party trong quá trình đăng ký hoặc đăng nhập như thế nào?
Bạn sẽ mô tả vòng đời credential từ tạo khóa, đăng ký public key, xác thực đến thu hồi như thế nào?
Bạn sẽ phân biệt credential WebAuthn với tài khoản người dùng và giải thích một tài khoản có thể gắn nhiều credential ra sao?
Bạn sẽ thiết kế chính sách passkey cho ứng dụng đa nền tảng mà không phụ thuộc framework hoặc backend cụ thể như thế nào?
Bạn sẽ giải thích RP ID xác định phạm vi website được phép sử dụng credential như thế nào?
Bạn sẽ phân biệt RP ID với origin và nêu cách hai giá trị này được kiểm tra trong ceremony ra sao?
Bạn sẽ xác định quy tắc chọn RP ID cho website có nhiều subdomain và các ranh giới tin cậy khác nhau như thế nào?
Bạn sẽ đánh giá rủi ro khi chọn RP ID quá rộng khiến nhiều subdomain cùng có khả năng yêu cầu xác thực credential ra sao?
Bạn sẽ mô tả origin gồm scheme, host và port được xác minh trong client data như thế nào?
Bạn sẽ xử lý yêu cầu WebAuthn từ iframe hoặc cross-origin context bằng các cơ chế cho phép và kiểm tra nào?
Bạn sẽ giải thích vì sao RP ID hash trong authenticator data phải khớp với RP ID mà server mong đợi như thế nào?
Bạn sẽ thiết kế quy tắc allowlist origin cho production, staging và môi trường phát triển mà không mở rộng trust ngoài ý muốn ra sao?
Bạn sẽ phân tích nguy cơ subdomain takeover đối với ứng dụng dùng chung RP ID như thế nào?
Bạn sẽ ngăn việc sử dụng credential trên domain giả mạo dù kẻ tấn công có thể sao chép giao diện đăng nhập ra sao?
Bạn sẽ mô tả registration ceremony từ yêu cầu tạo challenge đến khi server lưu public key như thế nào?
Bạn sẽ xác định các trường cần có trong PublicKeyCredentialCreationOptions và mục đích của từng trường ra sao?
Bạn sẽ tạo challenge ngẫu nhiên, gắn với phiên đăng ký và bảo đảm challenge chỉ được sử dụng một lần như thế nào?
Bạn sẽ giải thích user.id và user.name khác nhau ra sao, cùng yêu cầu user handle ổn định nhưng không chứa PII như thế nào?
Bạn sẽ lựa chọn authenticatorSelection và residentKey requirement theo nhu cầu discoverable credential ra sao?
Bạn sẽ phân biệt resident credential với non-resident credential và ảnh hưởng đến luồng đăng nhập không cần username như thế nào?
Bạn sẽ lựa chọn userVerification required, preferred hoặc discouraged dựa trên mức độ bảo đảm danh tính cần thiết ra sao?
Bạn sẽ giải thích attestation conveyance preference và lý do nhiều ứng dụng tiêu dùng có thể không cần attestation như thế nào?
Bạn sẽ phân biệt attestation statement, attestation object và credential public key trong phản hồi đăng ký ra sao?
Bạn sẽ xác minh clientDataJSON gồm type, challenge, origin và các thuộc tính liên quan trong registration response như thế nào?
Bạn sẽ kiểm tra authenticatorData gồm rpIdHash, flags và signCount trong registration response ra sao?
Bạn sẽ xác minh chữ ký attestation và certificate chain khi chính sách yêu cầu tin cậy authenticator cụ thể như thế nào?
Bạn sẽ đánh giá rủi ro quyền riêng tư khi yêu cầu attestation có thể tiết lộ model hoặc định danh thiết bị ra sao?
Bạn sẽ phân biệt packed, TPM, Android Key, Apple và none attestation formats theo cách xác minh như thế nào?
Bạn sẽ xử lý lỗi registration khi challenge hết hạn, origin không hợp lệ hoặc public key algorithm không được hỗ trợ ra sao?
Bạn sẽ mô tả authentication ceremony từ lúc server tạo challenge đến khi xác minh chữ ký assertion như thế nào?
Bạn sẽ phân biệt allowCredentials với discoverable credential khi xây dựng luồng đăng nhập có hoặc không yêu cầu username ra sao?
Bạn sẽ giải thích userHandle được trả về trong assertion có vai trò gì khi xác định tài khoản đăng nhập như thế nào?
Bạn sẽ xác minh clientDataJSON trong assertion bằng cách kiểm tra type, challenge, origin và crossOrigin ra sao?
Bạn sẽ kiểm tra rpIdHash, UP, UV, backup eligibility và backup state trong authenticatorData như thế nào?
Bạn sẽ giải thích assertion signature được tạo trên authenticatorData kết hợp hash của clientDataJSON như thế nào?
Bạn sẽ lựa chọn COSE public key algorithm và xác minh chữ ký theo thuật toán đã đăng ký như thế nào?
Bạn sẽ ngăn replay assertion bằng challenge dùng một lần, thời hạn ngắn và liên kết với phiên đăng nhập ra sao?
Bạn sẽ phân biệt user presence với user verification và xác định khi nào chính sách cần cờ UV như thế nào?
Bạn sẽ giải thích signCount có thể hỗ trợ phát hiện một số trường hợp clone authenticator nhưng không phải bằng chứng tuyệt đối ra sao?
Bạn sẽ xử lý signCount bằng không hoặc không tăng trong các hệ sinh thái passkey đồng bộ như thế nào?
Bạn sẽ xác minh user verification flag và đánh giá mức bảo đảm khi authenticator không thực hiện xác minh người dùng ra sao?
Bạn sẽ xử lý assertion thiếu userHandle khi request cho phép nhiều credential hoặc đăng nhập không cần username như thế nào?
Bạn sẽ thiết kế kiểm soát chống đăng nhập nhầm tài khoản khi nhiều credential hoặc nhiều user có dữ liệu định danh gần giống nhau ra sao?
Bạn sẽ phân biệt backup eligibility và backup state flags với việc credential có thực sự được đồng bộ thành công hay không như thế nào?
Bạn sẽ giải thích discoverable credential cho phép authenticator tìm tài khoản phù hợp mà không cần server gửi allowCredentials ra sao?
Bạn sẽ lựa chọn luồng username-first, usernameless và conditional mediation theo trải nghiệm đăng nhập như thế nào?
Bạn sẽ mô tả conditional UI hoặc passkey autofill hoạt động cùng trường username trong trình duyệt ra sao?
Bạn sẽ đánh giá tác động của credential discovery đến quyền riêng tư và nguy cơ lộ danh sách tài khoản trên thiết bị như thế nào?
Bạn sẽ giải thích CTAP2 kết nối client platform với authenticator qua USB, NFC hoặc BLE như thế nào?
Bạn sẽ phân biệt WebAuthn API trong browser với CTAP protocol giữa platform và authenticator ra sao?
Bạn sẽ so sánh khóa bảo mật USB/NFC với platform authenticator tích hợp trong điện thoại hoặc máy tính về khả năng sử dụng và khôi phục như thế nào?
Bạn sẽ thiết kế chính sách yêu cầu PIN hoặc biometric local verification trên authenticator mà không gửi dữ liệu sinh trắc học về server ra sao?
Bạn sẽ giải thích passkey đồng bộ khác với credential gắn thiết bị về cách sao lưu, di chuyển và mô hình tin cậy như thế nào?
Bạn sẽ đánh giá bảo vệ end-to-end encryption và account security của nhà cung cấp hệ sinh thái đồng bộ passkey ra sao?
Bạn sẽ phân biệt backup eligibility với backup state và xác định server nên dùng hai cờ này để quản lý rủi ro như thế nào?
Bạn sẽ xử lý việc người dùng mất quyền truy cập tài khoản đồng bộ passkey và cần khôi phục thiết bị ra sao?
Bạn sẽ mô tả cross-device authentication dùng QR code, Bluetooth proximity và kết nối giữa thiết bị mới với thiết bị có passkey như thế nào?
Bạn sẽ giải thích vai trò của hybrid transport và Bluetooth proximity trong giảm nguy cơ relay khi đăng nhập liên thiết bị ra sao?
Bạn sẽ xác định những tín hiệu nào cho biết ceremony đang diễn ra qua thiết bị khác và cách áp dụng chính sách rủi ro phù hợp như thế nào?
Bạn sẽ phân tích nguy cơ relay hoặc social engineering khi người dùng quét QR đăng nhập trên thiết bị lạ ra sao?
Bạn sẽ thiết kế trải nghiệm đăng nhập liên thiết bị an toàn khi thiết bị đích là máy công cộng hoặc máy không được tin cậy như thế nào?
Bạn sẽ tổ chức nhiều passkey cho một tài khoản để hỗ trợ nhiều thiết bị, khóa dự phòng và luồng đăng nhập doanh nghiệp ra sao?
Bạn sẽ thiết kế giao diện quản lý credential cho phép người dùng xem tên, thời điểm tạo và thu hồi passkey như thế nào?
Bạn sẽ xác định cách xử lý credential không còn sử dụng sau khi người dùng mất thiết bị hoặc nghi ngờ thiết bị bị xâm phạm ra sao?
Bạn sẽ thu hồi passkey ở cấp tài khoản khi hệ sinh thái đồng bộ không cung cấp cơ chế thu hồi từng bản sao tức thời như thế nào?
Bạn sẽ kết hợp passkey với quy trình account recovery để tránh email hoặc SMS yếu trở thành đường vòng vượt qua xác thực mạnh ra sao?
Bạn sẽ thiết kế quy trình thêm passkey mới yêu cầu xác thực bằng credential hiện có hoặc phương thức step-up nào?
Bạn sẽ xử lý trường hợp người dùng mất tất cả passkey và không còn thiết bị đáng tin cậy mà vẫn hạn chế social engineering như thế nào?
Bạn sẽ xác định khi nào cần kết hợp recovery code, xác minh danh tính bổ sung hoặc hỗ trợ thủ công trong khôi phục passkey ra sao?
Bạn sẽ thiết kế thông báo và audit event cho đăng ký, sử dụng, đổi tên và xóa passkey như thế nào?
Bạn sẽ giải thích vì sao passkey có khả năng chống phishing nhờ ràng buộc origin nhưng vẫn không loại bỏ mọi nguy cơ chiếm tài khoản như thế nào?
Bạn sẽ phân tích adversary-in-the-middle, malicious browser extension và compromised endpoint ảnh hưởng đến passkey ra sao?
Bạn sẽ đánh giá rủi ro khi attacker kiểm soát thiết bị đã mở khóa hoặc tài khoản đồng bộ passkey dù private key không bị xuất ra như thế nào?
Bạn sẽ xác định cách chống social engineering khiến người dùng đăng ký credential của kẻ tấn công vào tài khoản nạn nhân ra sao?
Bạn sẽ thiết kế rate limiting và risk signal cho registration, authentication và account recovery để giảm credential abuse như thế nào?
Bạn sẽ kiểm thử WebAuthn với sai origin, sai RP ID, challenge cũ, chữ ký sai và credential không thuộc tài khoản ra sao?
Bạn sẽ xây dựng test case cho user verification, user presence, signCount và backup flags trong các loại authenticator khác nhau như thế nào?
Bạn sẽ kiểm thử passkey đồng bộ và đăng nhập liên thiết bị trên nhiều trình duyệt, hệ điều hành và authenticator như thế nào?
Bạn sẽ đánh giá khả năng tương thích khi browser hoặc authenticator không hỗ trợ thuật toán, extension hay transport được yêu cầu ra sao?
Bạn sẽ thiết kế quy trình xử lý lỗi WebAuthn để phân biệt người dùng hủy, authenticator không sẵn sàng và server xác minh thất bại như thế nào?
Bạn sẽ giám sát tỷ lệ đăng ký thành công, assertion failure, lỗi challenge, lỗi origin và tỷ lệ sử dụng passkey theo nền tảng ra sao?
Bạn sẽ phát hiện bất thường khi một tài khoản đột ngột thêm nhiều credential hoặc xuất hiện luồng recovery đáng ngờ như thế nào?
Bạn sẽ xây dựng chiến lược triển khai passkey từng bước từ optional, ưu tiên đăng nhập đến passwordless mà không khóa người dùng hiện hữu ra sao?
Bạn sẽ đề xuất kiến trúc passkey độc lập nền tảng gồm registration, assertion, credential lifecycle, sync, cross-device, recovery và monitoring như thế nào?

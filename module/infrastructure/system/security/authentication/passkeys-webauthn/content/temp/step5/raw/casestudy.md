Một website xác minh chữ ký assertion thành công nhưng chỉ kiểm tra hostname gần đúng; request từ origin khác cùng chứa chuỗi tên miền được chấp nhận dù scheme hoặc port không thuộc origin tin cậy.
Máy chủ cấu hình RP ID là domain cha để dùng passkey trên nhiều subdomain; một subdomain cũ do bên thứ ba quản lý bị chiếm và trở thành bề mặt đăng nhập cho cùng RP ID.
Nhóm đặt RP ID thành public suffix như com để dùng chung passkey cho nhiều website; trình duyệt từ chối vì RP ID phải là domain hợp lệ gắn với origin và không thể mở rộng tùy ý tới public suffix.
Ứng dụng nằm sau reverse proxy và lấy host header do client gửi để tạo expected origin; attacker thay Host hoặc forwarded-host khiến server xác minh assertion theo origin do attacker kiểm soát.
Website chạy production qua HTTPS nhưng allowlist origin vẫn chấp nhận HTTP và nhiều port không cần thiết; assertion từ môi trường kém tin cậy có thể được ghép vào luồng xác thực.
Server tạo WebAuthn challenge bằng giá trị tuần tự hoặc timestamp; attacker dự đoán được challenge kế tiếp và có cơ hội chuẩn bị assertion ngoài phiên dự kiến.
Challenge được tạo ngẫu nhiên nhưng không gắn với phiên đăng nhập hoặc user đang thực hiện thao tác; assertion hợp lệ từ một phiên khác có thể bị ghép nhầm vào request hiện tại.
Một challenge đã được xác minh vẫn còn trong cache và có thể dùng lại; attacker phát lại assertion đã ghi nhận trước đó để tạo phiên mới.
Server so sánh challenge dạng base64url bằng cách decode một phía nhưng không chuẩn hóa padding và encoding; dữ liệu tương đương bị so sánh sai hoặc các biến thể không hợp lệ lọt qua.
Endpoint xác minh assertion chỉ kiểm tra chữ ký mà không kiểm tra type trong clientDataJSON; response cho thao tác đăng ký có thể bị đưa nhầm vào luồng đăng nhập.
Máy chủ xác minh challenge và chữ ký nhưng không kiểm tra origin trong clientDataJSON; assertion từ website giả mạo có thể bị chấp nhận nếu credential public key bị dùng sai ngữ cảnh.
Ứng dụng nhúng WebAuthn trong cross-origin iframe nhưng không kiểm tra chính sách Permissions Policy và top-level origin; luồng được nhúng ngoài website dự kiến có thể khởi tạo thao tác xác thực.
Server chỉ so sánh origin với RP ID mà bỏ qua quy tắc quan hệ giữa origin và RP ID; một origin không thuộc phạm vi RP vẫn có thể được xử lý sai.
Authenticator data có rpIdHash không khớp RP ID đã cấu hình sau khi đổi domain; server chỉ kiểm tra chữ ký và chấp nhận assertion cho relying party khác.
Server xác minh chữ ký bằng public key nhưng không kiểm tra algorithm được credential đăng ký cho phép; parser chấp nhận thuật toán hoặc key type ngoài chính sách.
Một verifier tự viết ghép sai authenticatorData và hash của clientDataJSON trước khi kiểm tra chữ ký; một số assertion hợp lệ bị từ chối và có nguy cơ tạo lỗ hổng nếu xác minh không đúng cấu trúc chuẩn.
Server chỉ kiểm tra chữ ký assertion mà bỏ qua cờ UP trong authenticatorData; response không chứng minh authenticator đã ghi nhận thao tác hiện diện của người dùng.
Chính sách yêu cầu xác minh người dùng nhưng server chỉ kiểm tra cờ UP, không kiểm tra UV; thao tác chỉ cần chạm khóa hoặc nhấn nút vẫn được coi như đã xác minh user.
RP gửi userVerification=required nhưng verifier vẫn chấp nhận assertion không có UV flag trong authenticatorData; chính sách FIDO2/CTAP2 yêu cầu PIN hoặc xác minh sinh trắc học tại authenticator bị vô hiệu hóa ở phía server.
Người dùng nghĩ biometric template được gửi lên website khi dùng passkey; đội sản phẩm thiết kế luồng thu thập dấu vân tay trong khi thao tác xác minh thường diễn ra cục bộ tại authenticator.
Ứng dụng chỉ hỗ trợ platform authenticator và không cho dùng security key roaming; nhân viên dùng thiết bị không có authenticator phù hợp không thể đăng nhập dù credential đã đăng ký ở khóa bảo mật ngoài.
Đội bảo mật yêu cầu attestation trực tiếp cho mọi người dùng nhưng không cân nhắc quyền riêng tư và tương thích; trình duyệt hoặc authenticator trả attestation none khiến đăng ký hợp lệ bị từ chối.
Server nhận attestation object nhưng chỉ kiểm tra định dạng CBOR, không xác minh chuỗi chứng chỉ hoặc trust anchor theo chính sách; thiết bị ngoài danh sách được chấp nhận như authenticator đáng tin.
Attestation được xác minh nhưng server không kiểm tra format-specific statement và chứng chỉ leaf đúng theo định dạng; dữ liệu giả mạo có thể qua một verifier tổng quát quá lỏng.
Nhóm lưu attestation certificate và AAGUID đầy đủ cho mọi tài khoản dù không có nhu cầu quản lý thiết bị; dữ liệu có thể tăng khả năng fingerprint người dùng và thiết bị.
Metadata service của authenticator được dùng để đánh giá trạng thái model nhưng danh sách metadata không được cập nhật; thiết bị đã bị cảnh báo hoặc thu hồi vẫn được coi là đạt chính sách.
Trong đăng ký, server tạo user ID từ email rồi tin userHandle client gửi lại; client có thể thay handle để gắn credential vào tài khoản khác nếu server không ràng buộc với phiên đăng ký.
Quy trình registration không yêu cầu phiên đã xác thực hoặc bằng chứng kiểm soát tài khoản; attacker có thể đăng ký passkey của mình vào tài khoản nạn nhân qua endpoint công khai.
Server lưu credential ID nhưng không áp dụng uniqueness constraint; một credential được gắn vào nhiều user record và kết quả đăng nhập có thể ánh xạ nhầm danh tính.
Ứng dụng dùng discoverable credentials nhưng không xử lý userHandle opaque do authenticator trả về; server giả định userHandle luôn là email và không tìm được đúng tài khoản.
Luồng đăng nhập có allowCredentials list nhưng server không kiểm tra credential ID trả về có nằm trong danh sách đã gửi; assertion từ credential khác có thể được dùng trong phiên.
Website đặt userVerification=preferred nhưng giao diện tuyên bố mọi lần đăng nhập đều yêu cầu biometric hoặc PIN; thiết bị chỉ thực hiện user presence vẫn được chấp nhận theo semantics của preferred.
Authenticator trả signCount bằng 0 hoặc counter không tăng sau mỗi lần dùng; server khóa tài khoản ngay lập tức dù một số passkey đồng bộ hoặc authenticator đa thiết bị không cung cấp counter đơn điệu đáng tin cậy.
Server không lưu signCount cuối cùng hoặc bỏ qua mọi bất thường; với authenticator có counter đáng tin cậy, việc credential bị clone có thể không được phát hiện qua dấu hiệu counter.
Assertion từ passkey đồng bộ có backup-eligible và backup-state flags; server bỏ qua hai cờ này nên không phân biệt được credential có thể sao lưu với credential đang ở trạng thái đã backup.
Chính sách doanh nghiệp yêu cầu credential device-bound nhưng verifier chỉ kiểm tra UV; passkey đồng bộ được chấp nhận dù mô hình rủi ro yêu cầu credential gắn với thiết bị quản lý.
Người dùng đồng bộ passkey qua cloud account cá nhân; tài khoản cloud bị chiếm và attacker khôi phục được passkey trên thiết bị khác, vượt kỳ vọng rằng credential chỉ nằm trên thiết bị ban đầu.
Nhóm coi passkey đồng bộ là bản sao lưu do website kiểm soát; khi nhà cung cấp hệ sinh thái mất tài khoản đồng bộ, website không thể tự khôi phục private key và người dùng cần phương án recovery khác.
Người dùng mất điện thoại đã chứa passkey device-bound và không đăng ký thiết bị hoặc authenticator dự phòng; tài khoản không thể truy cập dù mật khẩu cũ đã bị tắt.
Luồng cross-device authentication hiển thị QR code trên máy tính; attacker dụ người dùng quét QR từ phiên đăng nhập của attacker và xác nhận trên điện thoại mà không kiểm tra ngữ cảnh thiết bị.
Hybrid transport dùng QR và Bluetooth proximity để liên kết điện thoại với trình duyệt khác; đội vận hành bỏ qua bước xác nhận proximity và thông tin phiên, làm tăng nguy cơ relay hoặc nhầm phiên.
Người dùng được yêu cầu quét QR để đăng nhập vào website hỗ trợ nhưng trang đích có domain gần giống thương hiệu; passkey vẫn chống phishing theo RP ID, song người dùng có thể bị dụ xác nhận một giao dịch hoặc phiên khác.
Attacker chiếm quyền điều khiển trình duyệt sau khi người dùng đăng nhập bằng passkey; passkey chống giả mạo website nhưng không tự bảo vệ session cookie hoặc hành động sau xác thực.
Website triển khai passkey nhưng vẫn giữ password fallback không có MFA và cho phép reset bằng email yếu; attacker bỏ qua luồng chống phishing bằng đường đăng nhập dự phòng.
Trình duyệt không có secure context vì website chạy HTTP; WebAuthn API không hoạt động như production và nhóm cố khắc phục bằng cách tắt các kiểm tra bảo mật phía server.
Ứng dụng chạy trên nhiều subdomain và nhúng WebAuthn trong iframe; trình duyệt yêu cầu cấu hình cho phép public-key credentials qua Permissions Policy nhưng response bị lỗi do quyền delegation không đúng.
Server đặt timeout challenge dài nhiều giờ để người dùng có thời gian hoàn tất cross-device sign-in; challenge tồn tại quá lâu và tăng cửa sổ replay nếu phiên bị lộ.
Challenge hết hạn ở backend nhưng frontend vẫn cho gửi assertion; hệ thống trả lỗi chung và không phân biệt challenge expired với chữ ký không hợp lệ, khiến hỗ trợ khó chẩn đoán.
Người dùng mở đồng thời hai tab đăng nhập; server chỉ giữ một challenge hiện hành cho toàn tài khoản nên challenge ở tab sau ghi đè tab trước và tạo lỗi xác thực khó tái hiện.
Server lưu challenge trong cache theo user ID nhưng không ràng buộc với transaction hoặc tab; hai luồng registration và authentication song song có thể tiêu thụ nhầm challenge của nhau.
Credential được đổi tên hoặc xóa trong trang quản lý thiết bị nhưng server chỉ ẩn khỏi giao diện; public key vẫn còn trong kho xác minh và credential bị đánh cắp tiếp tục đăng nhập được.
Người dùng báo mất security key; đội hỗ trợ xóa session hiện tại nhưng không revoke credential ID đã đăng ký, nên khóa bị mất vẫn có thể tạo assertion mới.
Người dùng xóa passkey trên thiết bị nhưng relying party không nhận được thông báo xóa; server vẫn giữ credential và cần quy trình quản lý/revoke độc lập phía tài khoản.
Người dùng đăng ký passkey thứ hai từ một session đang mở nhưng session đó bị chiếm; attacker thêm credential của mình rồi dùng nó lâu dài dù chủ tài khoản đổi mật khẩu.
Quy trình thêm passkey mới không yêu cầu reauthentication hoặc step-up bằng credential hiện có; một session bị đánh cắp có thể thêm authenticator do attacker kiểm soát.
Khôi phục tài khoản cho người mất tất cả passkey chỉ dựa vào SMS OTP; SIM swap trở thành đường vòng yếu hơn cơ chế passkey vốn chống phishing.
Help desk cho phép thay email recovery và xóa toàn bộ passkey sau vài câu hỏi thông tin cá nhân công khai; social engineering có thể chiếm tài khoản mà không cần phá WebAuthn.
Ứng dụng không cung cấp recovery code hoặc phương thức dự phòng có kiểm soát; người dùng mất thiết bị đồng bộ và không thể khôi phục tài khoản dù danh tính ngoài đời đã được xác minh.
Doanh nghiệp yêu cầu attestation để chỉ chấp nhận authenticator được quản lý; chính sách không xác định rõ metadata, model và trạng thái firmware được phép nên kết quả khác nhau giữa các vùng.
Thiết bị được chấp nhận lúc đăng ký nhưng sau đó authenticator model bị đưa vào danh sách cảnh báo; hệ thống không đánh giá lại credential hiện có hoặc yêu cầu phương thức thay thế.
Ứng dụng log toàn bộ clientDataJSON, authenticatorData và attestation object để debug; challenge, origin, user handle hoặc thông tin thiết bị có thể bị lưu quá mức và làm tăng rủi ro riêng tư.
Verifier trả thông báo khác nhau cho tài khoản không có credential, credential không tồn tại và chữ ký sai; attacker có thể dùng endpoint để dò tài khoản hoặc trạng thái đăng ký passkey.
Thư viện xác minh được nâng cấp nhưng nhóm không kiểm thử vector chuẩn cho origin, RP ID hash, challenge, flags, attestation và signature; một thay đổi parser làm từ chối hàng loạt thiết bị hợp lệ.
Đội sản phẩm đánh giá passkey thành công chỉ bằng tỷ lệ đăng nhập; không đo lỗi theo browser, platform authenticator, roaming key, hybrid flow và recovery nên không phát hiện một nhóm thiết bị bị khóa ngoài.
Passkey được dùng cho thao tác nhạy cảm nhưng ứng dụng không hiển thị rõ tài khoản, RP và hành động cần xác nhận; người dùng có thể xác thực đúng website nhưng không nhận biết họ đang phê duyệt phiên hoặc giao dịch nào.

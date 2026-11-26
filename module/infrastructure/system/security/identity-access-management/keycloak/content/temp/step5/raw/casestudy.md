Một tập đoàn triển khai Keycloak cho 40 công ty thành viên và đang cân nhắc realm riêng cho từng tenant hoặc một realm dùng chung; yêu cầu về cô lập người dùng, quản trị và chi phí vận hành đang mâu thuẫn nhau.
Đội vận hành dùng master realm để đăng nhập cho ứng dụng nghiệp vụ vì cấu hình ban đầu đơn giản; sau khi một quản trị viên bị lộ tài khoản, phạm vi ảnh hưởng có thể vượt khỏi một realm.
Hai realm production và staging được tạo thủ công qua nhiều nhóm vận hành; client ID, redirect URI và identity provider mapper dần khác nhau khiến cùng một ứng dụng hoạt động không nhất quán.
Một client web được cấu hình valid redirect URI bằng wildcard quá rộng để hỗ trợ nhiều môi trường; một URL chuyển hướng ngoài dự kiến có thể nhận authorization response.
Một ứng dụng browser gọi API từ nhiều domain và cấu hình Web Origins cho phép mọi origin; nhóm bảo mật phát hiện trình duyệt có thể gửi request cross-origin với phiên đăng nhập đang tồn tại.
Access token của một client chứa quá nhiều user attributes, realm roles và client roles; token tăng kích thước, làm lộ dữ liệu và được nhiều API chấp nhận ngoài dự kiến.
Một API nhận access token do Keycloak phát hành nhưng không kiểm tra audience; token dành cho client khác vẫn được chấp nhận để gọi tài nguyên nhạy cảm.
Ứng dụng mobile dùng public client và lưu client secret nhúng trong gói cài đặt; secret xuất hiện trong bản phân tích ứng dụng và có thể bị tái sử dụng.
Một confidential client chia sẻ cùng client secret giữa development, staging và production; khi một môi trường thử nghiệm bị xâm nhập, toàn bộ môi trường có nguy cơ.
Sau khi chuyển Keycloak ra sau reverse proxy, issuer trong discovery metadata và token không khớp hostname mà ứng dụng tin cậy; đăng nhập OIDC thất bại ở bước xác minh.
Một service provider SAML đổi ACS URL sau khi di chuyển hạ tầng nhưng cấu hình client trong Keycloak vẫn giữ endpoint cũ; phản hồi đăng nhập bị gửi tới địa chỉ không còn hoạt động.
Chứng thư ký SAML của đối tác sắp hết hạn nhưng không có lịch phối hợp rollover; hai bên có thể mất khả năng xác minh assertion khi chứng thư cũ bị thay thế.
Một đối tác yêu cầu mã hóa SAML assertion nhưng chỉ cấu hình ký thông điệp; dữ liệu định danh vẫn có thể đọc được trên các điểm trung gian không được tin cậy.
Một authentication flow mới thêm MFA cho nhóm quản trị nhưng nhánh conditional được cấu hình sai; một số đường đăng nhập vẫn đi qua mà không thực hiện bước xác thực bổ sung.
Chính sách OTP được đổi sang thuật toán hoặc số chữ số mới trong khi người dùng hiện hữu vẫn có thiết bị đã đăng ký theo cấu hình cũ; tỷ lệ đăng nhập thất bại tăng mạnh.
Tổ chức bật WebAuthn cho tài khoản đặc quyền nhưng người dùng có nhiều thiết bị và không có quy trình đăng ký thiết bị dự phòng; mất thiết bị chính khiến quản trị viên bị khóa ngoài.
Help desk có quyền reset MFA sau khi xác minh danh tính qua email và vài câu hỏi cá nhân; kẻ tấn công chiếm email có thể lợi dụng quy trình recovery để vượt MFA.
Brute-force detection khóa tài khoản hàng loạt sau một đợt password spraying; nhóm vận hành phải phân biệt tấn công thực sự với lưu lượng hợp lệ từ NAT dùng chung.
Tổ chức yêu cầu hàng nghìn người dùng đổi mật khẩu trong một đợt triển khai chính sách mới; nhiều tài khoản dịch vụ và người dùng không tương tác không thể hoàn tất yêu cầu đúng hạn.
Required action xác minh email được bật nhưng email server bị lỗi; người dùng mới không thể hoàn tất đăng ký và hàng đợi gửi thư tăng liên tục.
User Profile cho phép người dùng tự sửa thuộc tính department và employeeNumber; các thuộc tính được dùng cho phân quyền bị thay đổi mà không qua nguồn nhân sự có thẩm quyền.
Một thuộc tính người dùng được đồng bộ từ LDAP nhưng đồng thời cho phép chỉnh sửa trong Keycloak; lần đồng bộ tiếp theo ghi đè dữ liệu do quản trị viên cập nhật.
Tổ chức bật LDAP federation với import users để giảm tải directory; dữ liệu người dùng trong Keycloak bị cũ khi thay đổi ở LDAP không được đồng bộ đúng lịch.
Một hệ thống cần tra cứu người dùng trực tiếp từ LDAP nhưng directory có độ trễ cao; login latency tăng và một sự cố LDAP khiến người dùng không thể đăng nhập.
Bind account LDAP dùng mật khẩu không hết hạn và kết nối không xác minh chứng thư máy chủ; credential có thể bị lộ hoặc kết nối bị giả mạo.
Full sync và changed-user sync chạy đồng thời trên directory lớn; tải LDAP tăng cao và một số cập nhật người dùng bị áp dụng lặp hoặc chậm.
Nhân viên bị vô hiệu hóa trong Active Directory nhưng phiên SSO tại Keycloak và các ứng dụng phụ thuộc vẫn còn; quyền truy cập cần được thu hồi theo thời hạn nghiệp vụ.
Keycloak đăng nhập qua một identity provider bên ngoài; email từ IdP trùng email với tài khoản nội bộ nhưng hệ thống tự liên kết tài khoản mà không có bước xác minh đủ mạnh.
First Broker Login Flow tạo user mới mỗi khi claim định danh từ IdP thay đổi định dạng; cùng một người dùng xuất hiện thành nhiều tài khoản nội bộ.
Identity Provider Mapper lấy group và role từ claim bên ngoài; một claim do IdP phát hành bị cấu hình sai khiến người dùng nhận quyền quản trị nội bộ.
Một người dùng đăng nhập qua hai identity provider khác nhau và được tạo hai tài khoản Keycloak; tổ chức cần hợp nhất danh tính nhưng vẫn bảo toàn audit trail và quyền.
Người dùng đăng xuất khỏi Keycloak nhưng phiên tại identity provider bên ngoài vẫn tồn tại; lần đăng nhập tiếp theo diễn ra tự động dù ứng dụng mong đợi đăng xuất hoàn toàn.
Quản trị viên gán realm role khi quyền chỉ cần áp dụng cho một API; token của người dùng mang quyền quá rộng tới các client khác.
Composite role gom nhiều role con và một role đặc quyền được thêm vào mà không rà soát người đang kế thừa; phạm vi quyền tăng ngoài dự kiến.
Default roles tự động cấp cho mọi user mới bao gồm quyền truy cập một client quản trị; tài khoản mới có đặc quyền trước khi được phê duyệt.
Một nhóm người dùng được gán đồng thời group, realm role và client role; khi chuyển phòng ban, quyền cũ không được loại bỏ và tạo ra tích lũy đặc quyền.
Keycloak Authorization Services có policy kết hợp role và điều kiện thuộc tính; đổi decision strategy từ Unanimous sang Affirmative khiến resource được phép khi chỉ một policy thành phần cho phép.
Quản trị viên realm được cấp quyền quản lý toàn bộ user, client và identity provider dù chỉ phụ trách một ứng dụng; tổ chức muốn phân quyền quản trị chi tiết hơn.
Service account của một client có quyền gọi Admin REST API với vai trò quản trị realm; secret của client bị lộ và attacker có thể thay đổi người dùng cùng cấu hình.
Người dùng bị disable trong Keycloak nhưng access token đã phát hành vẫn còn thời hạn; API tiếp tục chấp nhận token cho đến khi hết hạn hoặc có cơ chế thu hồi phù hợp.
Offline session tồn tại lâu hơn nhu cầu nghiệp vụ sau khi nhân viên rời tổ chức; offline token có thể tiếp tục cấp access token nếu không được thu hồi.
Realm bật Revoke Refresh Token và cấu hình Refresh Token Max Reuse; một refresh token đã được đổi vẫn bị gửi lại từ thiết bị cũ, buộc nhóm vận hành đánh giá cách xử lý reuse và thu hồi phiên liên quan.
Signing key của realm được luân chuyển nhưng một số resource server cache JWKS quá lâu; token ký bằng khóa mới bị từ chối hoặc khóa cũ tiếp tục được tin cậy.
Một tenant yêu cầu MFA bắt buộc trong khi tenant khác chỉ yêu cầu MFA cho quản trị viên; mô hình realm chung cần tránh để policy của tenant này tác động tenant khác.
Keycloak cluster có nhiều node nhưng login flow đôi lúc mất trạng thái khi request chuyển node; nhóm cần điều tra distributed cache, session affinity và cấu hình cluster.
Sau khi thêm node Keycloak, distributed cache phát sinh lỗi discovery và các node không nhìn thấy nhau; login và cập nhật session trở nên không ổn định.
Load balancer gửi traffic tới node đang khởi động nhưng chưa sẵn sàng phục vụ authentication; người dùng nhận lỗi ngẫu nhiên trong thời gian rollout.
Database phía sau Keycloak chạm giới hạn connection trong giờ cao điểm; login, refresh token và thao tác quản trị cùng tăng latency.
Một truy vấn database chậm khiến transaction giữ connection lâu; số request chờ tăng, thread và bộ nhớ của node Keycloak dần cạn.
Keycloak chạy sau ingress nhưng forwarded headers được tin cậy từ mọi nguồn; attacker có thể giả mạo scheme hoặc host và ảnh hưởng URL được tạo trong luồng đăng nhập.
TLS certificate của hostname công khai sắp hết hạn nhưng quy trình gia hạn không cập nhật đầy đủ ingress và endpoint quản trị; đăng nhập OIDC và tác vụ quản trị có thể gián đoạn.
Liveness probe kiểm tra cả database và identity provider bên ngoài; một sự cố dependency tạm thời khiến orchestrator restart liên tục các node Keycloak khỏe mạnh.
Logs và user events ghi toàn bộ thông tin định danh, IP và chi tiết lỗi đăng nhập; đội điều tra cần dữ liệu nhưng phải giới hạn dữ liệu cá nhân và bí mật bị ghi.
Một đợt password spraying tạo hàng nghìn event đăng nhập thất bại; dashboard không phân biệt được tấn công, lỗi người dùng và sự cố identity provider.
Một quản trị viên thay đổi redirect URI, mapper và role mapping ngoài quy trình phê duyệt; tổ chức không có audit alert để phát hiện thay đổi nhạy cảm kịp thời.
Backup database được tạo hằng ngày nhưng không kiểm thử restore; sau sự cố, nhóm phát hiện quy trình khôi phục chưa xác minh realm, user, credential và trạng thái phiên theo mô hình lưu trữ của phiên bản đang chạy.
Nhóm vận hành dùng realm export/import như phương án backup duy nhất cho production; khi khôi phục, một số trạng thái vận hành và dữ liệu không được tái tạo như kỳ vọng.
Một bản nâng cấp Keycloak yêu cầu migration database; nhóm triển khai rolling upgrade với các node phiên bản không tương thích theo hướng dẫn phát hành và phát sinh lỗi trong giai đoạn chuyển tiếp.
Sau khi nâng cấp, custom provider hoặc extension bên ngoài không còn tương thích; quá trình khởi động thất bại và kế hoạch rollback chưa xác định cách xử lý schema đã migration.
Một đợt tăng trưởng người dùng khiến login và refresh token đạt đỉnh cùng lúc; nhóm cần xác định giới hạn CPU, memory, database, cache và chiến lược scale phù hợp.
Tổ chức chuyển từ một identity provider sang nhà cung cấp khác; cần duy trì định danh người dùng, account linking, MFA enrollment và phiên đang hoạt động trong giai đoạn chuyển đổi.
Một ứng dụng quan trọng cần mức sẵn sàng cao nhưng chỉ có một Keycloak node và một database instance; một lần bảo trì gây gián đoạn đăng nhập toàn tổ chức.
Sau sự cố bảo mật, tổ chức cần xoay client secrets, signing keys và bootstrap administrator credentials trên nhiều realm; thứ tự triển khai và nguy cơ gián đoạn chưa được xác định.

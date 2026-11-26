1. Trong Keycloak, realm đại diện cho phạm vi quản lý nào?
A. Phạm vi riêng cho users, clients, roles và cấu hình.
B. Một máy chủ độc lập có database và cấu hình tách biệt.
C. Nhóm tài khoản gắn với một ứng dụng cụ thể.
D. Phiên đăng nhập riêng được tạo mỗi lần truy cập.
Đáp án đúng: A

2. Client trong realm Keycloak thường đại diện cho thành phần nào?
A. Một user hoặc group được tạo để cấp quyền trong realm.
B. Một IdP bên ngoài dùng để chuyển tiếp đăng nhập.
C. Một phiên SSO được chia sẻ giữa nhiều ứng dụng.
D. Ứng dụng hoặc dịch vụ tích hợp với Keycloak.
Đáp án đúng: D

3. Vì sao public client như ứng dụng chạy trong trình duyệt không thể giữ client secret an toàn?
A. Public client không được phép khai báo redirect URI.
B. Public client chỉ hỗ trợ SAML, không hỗ trợ OIDC.
C. Mã chạy trên thiết bị người dùng có thể bị quan sát.
D. Client secret luôn bị Keycloak thay đổi sau mỗi lần login.
Đáp án đúng: C

4. Với confidential client, cơ chế nào phù hợp để xác thực client tại token endpoint?
A. Dùng access token của user cuối làm credential cho client.
B. Xác thực client bằng shared secret hoặc private key.
C. Gửi client ID trong query string mà không xác minh.
D. Dùng redirect URI làm bằng chứng sở hữu client.
Đáp án đúng: B

5. Luồng OIDC Authorization Code thường hoàn tất việc lấy token ở đâu?
A. Client đổi authorization code tại token endpoint.
B. Trình duyệt đọc access token trực tiếp từ trang login.
C. Resource server phát token sau request API đầu tiên.
D. IdP gửi mật khẩu người dùng tới callback URL.
Đáp án đúng: A

6. PKCE bảo vệ Authorization Code flow chủ yếu bằng cách nào?
A. Mã hóa toàn bộ token bằng public key của trình duyệt.
B. Thay client ID bằng giá trị ngẫu nhiên trong URL.
C. Ký redirect URI bằng private key của người dùng.
D. Code verifier ràng buộc bước đổi authorization code.
Đáp án đúng: D

7. Cấu hình redirect URI của OIDC client nên theo nguyên tắc nào?
A. Cho phép mọi URI cùng hostname để giảm lỗi tích hợp.
B. Dùng wildcard cho toàn bộ domain của tổ chức.
C. Allowlist callback URI cụ thể, tránh wildcard rộng.
D. Tin redirect URI do trình duyệt gửi sau đăng nhập.
Đáp án đúng: C

8. Trong OIDC, state và nonce thường giúp chống kiểu tấn công nào?
A. State gắn callback; nonce gắn với ID token.
B. Dùng cả hai để thay việc kiểm tra chữ ký của token.
C. State mã hóa access token; nonce cấp quyền gọi API.
D. Cả hai dùng để gia hạn SSO session tự động.
Đáp án đúng: A

9. ID token trong OIDC chủ yếu mang thông tin gì?
A. Danh sách mọi quyền truy cập của resource server.
B. Claims xác thực về người dùng đã đăng nhập.
C. Bí mật client đã đăng ký trong cấu hình realm.
D. Payload nghiệp vụ mà API trả về sau khi xử lý.
Đáp án đúng: B

10. Resource server nhận JWT access token nên xác minh claim nào ngoài chữ ký và thời hạn?
A. Tên hiển thị của user phải khớp giao diện đăng nhập.
B. Client secret phải bằng giá trị lưu trong trình duyệt.
C. Realm phải có cùng tên với hostname resource server.
D. Issuer và audience phải phù hợp với API nhận token.
Đáp án đúng: D

11. Trong SAML, Assertion Consumer Service (ACS) URL có vai trò gì?
A. Địa chỉ Keycloak dùng để tải signing key của IdP.
B. Endpoint dùng để tạo user mới trong LDAP federation.
C. Điểm cuối SP nhận SAML response/assertion.
D. URL người dùng nhập mật khẩu khi bắt đầu đăng nhập.
Đáp án đúng: C

12. Entity ID trong cấu hình SAML dùng để làm gì?
A. Mật khẩu dùng chung giữa IdP và service provider.
B. Định danh IdP hoặc service provider trong quan hệ trust.
C. Thay thế chứng thư ký SAML response trong mọi trường hợp.
D. Chứa danh sách group ánh xạ vào access token.
Đáp án đúng: B

13. Client scope trong Keycloak hữu ích nhất khi nào?
A. Tạo realm riêng cho từng tập claim tùy chọn.
B. Lưu password riêng theo từng ứng dụng.
C. Thay thế toàn bộ role và group mapping.
D. Dùng lại scope và mapper cho nhiều client.
Đáp án đúng: D

14. Protocol mapper trong Keycloak được dùng để làm gì?
A. Mã hóa database realm bằng khóa riêng của client.
B. Định tuyến request đăng nhập tới LDAP server.
C. Đưa thuộc tính user hoặc role vào claim của token.
D. Tự động cấp quyền quản trị cho user vừa đăng nhập.
Đáp án đúng: C

15. Realm role và client role khác nhau chủ yếu ở phạm vi nào?
A. Realm role thuộc realm; client role gắn với client.
B. Realm role chỉ dùng cho SAML; client role cho OIDC.
C. Realm role thuộc user; client role chỉ thuộc service account.
D. Realm role không thể gán qua group hoặc composite role.
Đáp án đúng: A

16. Composite role trong Keycloak giúp quản lý quyền theo cách nào?
A. Một role bao gồm các role thành phần khác.
B. Mã hóa nhiều role thành claim không thể đọc.
C. Tự động tạo user khi role thành phần được gán.
D. Thay thế client scope và protocol mapper trong token.
Đáp án đúng: A

17. Group trong Keycloak thường hỗ trợ quản trị người dùng như thế nào?
A. Tạo realm mới cho từng phòng ban trong tổ chức.
B. Gom user để áp dụng role mapping và thuộc tính chung.
C. Là database schema riêng để lưu password người dùng.
D. Thay thế hoàn toàn user federation và identity broker.
Đáp án đúng: B

18. Việc gán role trong Keycloak có tự bảo vệ mọi endpoint của ứng dụng không?
A. Có; mọi token Keycloak đều được API tự thực thi.
B. Có; nếu role được tạo ở realm thay vì client.
C. Không; Keycloak chỉ hỗ trợ xác thực qua giao diện login.
D. Không; resource server vẫn phải kiểm tra quyền trên request.
Đáp án đúng: D

19. Identity brokering trong Keycloak giải quyết nhu cầu nào?
A. Đồng bộ password từ database ứng dụng vào realm.
B. Chuyển xác thực tới IdP ngoài rồi nhận kết quả.
C. Thay OIDC và SAML bằng giao thức nội bộ riêng.
D. Cấp quyền database cho người dùng sau khi login.
Đáp án đúng: B

20. User federation với LDAP/Active Directory khác identity brokering thế nào?
A. Federation chỉ dùng social login; brokering dành cho LDAP.
B. Cả hai đều đồng bộ password vào Keycloak mặc định.
C. Federation nối kho user; brokering chuyển tiếp đăng nhập.
D. Brokering chỉ đồng bộ group; federation chỉ đồng bộ role.
Đáp án đúng: C

21. Khi liên kết tài khoản brokered theo email, kiểm soát nào quan trọng?
A. Xác minh email và nguồn tin cậy trước khi link account.
B. Tự liên kết mọi email trùng mà không cần xác minh.
C. Chỉ kiểm tra display name của tài khoản bên ngoài.
D. Cho IdP ngoài tự chọn user ID nội bộ tùy ý.
Đáp án đúng: A

22. First Broker Login flow trong Keycloak thường xử lý việc gì?
A. Tạo signing key mới mỗi lần người dùng đăng nhập.
B. Đổi realm mặc định theo domain email người dùng.
C. Thay việc xác minh assertion từ identity provider.
D. Xử lý tạo user hoặc liên kết ở lần broker đầu.
Đáp án đúng: D

23. Khi triển khai MFA cho người dùng Keycloak, lựa chọn nào chống phishing tốt hơn OTP thông thường?
A. OTP gửi qua email có thời hạn sử dụng dài hơn.
B. Câu hỏi bảo mật dùng chung giữa nhiều ứng dụng.
C. WebAuthn/passkey gắn xác thực với origin và authenticator.
D. Mã PIN cố định được lưu trong user profile.
Đáp án đúng: C

24. Required Action trong Keycloak thường dùng để làm gì?
A. Định tuyến request API tới một client khác.
B. Thay role mapping sau khi người dùng đăng nhập.
C. Cấp quyền admin tự động cho user chưa có MFA.
D. Buộc user hoàn thành bước như cập nhật password hoặc OTP.
Đáp án đúng: D

25. Brute force detection trong Keycloak giúp giảm rủi ro nào?
A. Giả mạo chữ ký JWT của resource server.
B. Thử mật khẩu lặp lại trên tài khoản đăng nhập.
C. Truy cập database trực tiếp từ máy chủ ứng dụng.
D. Thay certificate TLS của reverse proxy.
Đáp án đúng: B

26. SSO session và client session trong Keycloak biểu diễn điều gì?
A. Hai loại access token có cùng audience.
B. Một session database và một phiên TCP của trình duyệt.
C. Phiên đăng nhập realm và trạng thái phiên theo client.
D. Hai bản sao độc lập của password người dùng.
Đáp án đúng: C

27. Offline token/session cần được quản lý ra sao?
A. Coi như access token ngắn hạn, không cần revoke.
B. Giới hạn scope, thời hạn và thu hồi khi không còn cần.
C. Dùng chung cho mọi user trong cùng một realm.
D. Chỉ lưu browser local storage để tự gia hạn.
Đáp án đúng: B

28. Service account của confidential client thường được dùng trong trường hợp nào?
A. Client gọi dịch vụ bằng client credentials khi được bật.
B. Người dùng cuối đăng nhập bằng mật khẩu cá nhân.
C. Thay thế mọi tài khoản quản trị của realm.
D. Cấp MFA cho người dùng không có authenticator.
Đáp án đúng: A

29. Cách nào giảm rủi ro khi cấp quyền cho service account?
A. Chỉ gán role cần thiết và giới hạn quyền quản trị.
B. Gán realm-admin để tránh thiếu quyền khi gọi API.
C. Dùng chung service account cho mọi tích hợp.
D. Lưu client secret trong source code để dễ rotate.
Đáp án đúng: A

30. Vì sao không nên dùng master realm như realm nghiệp vụ thông thường?
A. Master realm không hỗ trợ tạo client hoặc user.
B. Master realm chỉ dành cho SAML identity provider.
C. Master realm không thể dùng database hoặc cache cluster.
D. Master realm quản lý admin Keycloak, cần bảo vệ riêng.
Đáp án đúng: D

31. Muốn cách ly tenant mạnh hơn trong Keycloak, lựa chọn nào cần cân nhắc?
A. Tạo group riêng rồi coi group là ranh giới tuyệt đối.
B. Dùng chung admin account cho mọi tenant để dễ vận hành.
C. Tách realm khi cần ranh giới users, clients và sessions.
D. Đặt tenant ID trong display name mà không áp policy.
Đáp án đúng: C

32. Khi triển khai Keycloak sau reverse proxy, cấu hình nào cần được kiểm soát?
A. Tin mọi X-Forwarded-* header từ bất kỳ nguồn nào.
B. Tắt hostname và TLS validation để proxy tự xử lý.
C. Đặt hostname; chỉ tin forwarded header từ proxy tin cậy.
D. Dùng Host do client gửi làm địa chỉ public canonical.
Đáp án đúng: C

33. Trong production, bảo vệ kênh giữa reverse proxy và Keycloak nên làm gì?
A. Luôn dùng HTTP vì TLS đã kết thúc ở proxy.
B. Bảo vệ hop nội bộ theo trust boundary và threat model.
C. Dùng cookie đăng nhập làm chứng thư máy chủ.
D. Cho mọi backend truy cập cổng quản trị trực tiếp.
Đáp án đúng: B

34. Keycloak chạy nhiều node cần thành phần nền tảng nào được thiết kế sẵn sàng cao?
A. Chỉ nhân bản file cấu hình trên từng node.
B. Chỉ cần load balancer, không cần database bền vững.
C. Một node giữ session, các node khác không cần phối hợp.
D. Database, distributed cache và load balancing phù hợp.
Đáp án đúng: D

35. Khi Keycloak signing key được xoay vòng, resource server xác minh JWT nên làm gì?
A. Giữ public key cũ vĩnh viễn và bỏ qua kid trong token.
B. Refresh JWKS theo chính sách và hỗ trợ overlap key.
C. Tin mọi kid do client gửi mà không tra JWKS.
D. Giải mã JWT bằng client secret thay cho public key.
Đáp án đúng: B

36. Sự kiện đăng nhập và thay đổi quản trị trong Keycloak nên được dùng thế nào?
A. Bật audit events, bảo vệ log và giám sát bất thường.
B. Tắt event để giảm dung lượng database production.
C. Ghi password và token đầy đủ để tiện điều tra.
D. Chỉ ghi log khi người dùng báo lỗi đăng nhập.
Đáp án đúng: A

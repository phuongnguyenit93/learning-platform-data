1. Trong SAML 2.0, vai trò chính của Identity Provider (IdP) và Service Provider (SP) được phân chia thế nào?
A. SP xác thực người dùng và phát assertion; IdP kiểm tra quyền tài nguyên.
B. IdP lưu phiên ứng dụng; SP chỉ chuyển tiếp mật khẩu tới thư mục doanh nghiệp.
C. IdP xác thực và phát assertion; SP xác minh rồi tạo phiên dịch vụ.
D. SP ký metadata cho IdP; IdP chỉ định tuyến request tới các ứng dụng.
Đáp án đúng: C

2. Một SAML Response chứa Assertion; khác biệt khái niệm nào mô tả đúng hai đối tượng này?
A. Response bao thông điệp; Assertion chứa statement về chủ thể và xác thực.
B. Response chỉ chứa thuộc tính; Assertion chỉ chứa mã trạng thái của giao dịch.
C. Response là chứng thư ký; Assertion là metadata mô tả endpoint của SP.
D. Response là phiên cục bộ; Assertion là quyết định phân quyền của SP.
Đáp án đúng: A

3. EntityID trong metadata SAML chủ yếu dùng để làm gì?
A. Xác định người dùng cuối bằng mã nhân viên ổn định qua nhiều ứng dụng.
B. Chỉ định địa chỉ IP mà trình duyệt phải dùng khi gửi thông điệp SAML.
C. Mã hóa NameID để SP không thể đọc thuộc tính của người dùng.
D. Định danh thực thể SAML như IdP hoặc SP trong quan hệ tin cậy.
Đáp án đúng: D

4. Hai tổ chức trao đổi metadata lần đầu; cách nào thiết lập trust an toàn?
A. Xác minh nguồn và fingerprint khóa qua kênh tin cậy độc lập.
B. Tải metadata từ URL do email không xác thực gửi tới rồi tự động tin.
C. Chấp nhận khóa mới nếu tên EntityID giống với tên đối tác đã biết.
D. Tin mọi chứng thư trong KeyInfo vì metadata được trao đổi qua HTTPS.
Đáp án đúng: A

5. Chứng thư X.509 dùng để ký thông điệp SAML có ý nghĩa gì so với chứng thư TLS của website?
A. Nó tự động thay thế chứng thư TLS và xác thực mọi kết nối HTTPS của SP.
B. Xác minh chữ ký SAML theo trust cấu hình; không thay chứng thư TLS.
C. Nó mã hóa toàn bộ lưu lượng trình duyệt giữa người dùng và IdP.
D. Nó chứng minh danh tính pháp lý của tổ chức theo mọi CA công cộng.
Đáp án đúng: B

6. HTTP Redirect và HTTP POST binding thường chuyển SAML message qua trình duyệt theo cách nào?
A. Redirect gửi JSON trong cookie; POST đặt XML nén trong query string của GET.
B. Redirect mã hóa XML bằng TLS; POST truyền Artifact ID trong header của request.
C. Redirect dùng hash không khóa; POST chỉ gửi tên EntityID và ACS endpoint.
D. Redirect dùng DEFLATE, Base64 và URL encoding; POST gửi Base64 trong form.
Đáp án đúng: D

7. Khi nào Artifact binding hữu ích trong một tích hợp SAML?
A. Trình duyệt nhúng toàn bộ assertion plaintext vào URL để SP đọc trực tiếp.
B. Trình duyệt chuyển artifact; hai bên phân giải qua kênh back-channel.
C. SP không thể kết nối IdP và muốn xác minh người dùng bằng email.
D. SP bỏ qua metadata và lấy khóa ký từ artifact do trình duyệt gửi.
Đáp án đúng: B

8. Trong SP-initiated SSO, kiểm tra nào liên kết Response với AuthnRequest đã gửi?
A. So sánh NameID với EntityID của SP để suy ra request ban đầu.
B. So sánh Destination với IP trình duyệt để nhận diện phiên yêu cầu.
C. So InResponseTo với ID request còn hiệu lực phía SP.
D. Đối chiếu SessionIndex với mã nhân viên trong hồ sơ HR người dùng.
Đáp án đúng: C

9. Rủi ro đặc trưng của IdP-initiated SSO cần được xem xét là gì?
A. AuthnRequest luôn bị gửi lặp vì SP không tạo ID cho request đăng nhập.
B. IdP không thể ký assertion khi SP không gửi metadata trước mỗi lần đăng nhập.
C. Unsolicited Response có thể tạo login CSRF nếu thiếu ràng buộc ngữ cảnh.
D. Assertion luôn hết hạn ngay vì Response không có InResponseTo.
Đáp án đúng: C

10. SP nhận Response tại Assertion Consumer Service (ACS); kiểm tra endpoint nào giúp xác nhận đích nhận?
A. So Destination và Recipient với ACS đã đăng ký và request.
B. So khớp Issuer với địa chỉ email của người dùng cuối trong assertion.
C. So khớp SessionIndex với URL trang chủ mà người dùng mở đầu tiên.
D. So khớp NameID với EntityID để xác định endpoint nhận phản hồi.
Đáp án đúng: A

11. Một người đổi email nhưng vẫn đăng nhập qua cùng IdP; cách chọn NameID và liên kết tài khoản nào ổn định hơn?
A. Dùng NameID transient làm mã người dùng cố định cho mọi phiên và mọi SP.
B. Dùng email làm khóa chính vì IdP ký assertion nên email không thể đổi.
C. Dùng display name để ghép tài khoản vì tên thường ổn định hơn username.
D. Dùng NameID persistent, gắn với issuer IdP đã xác minh.
Đáp án đúng: D

12. SP ánh xạ AttributeStatement sang hồ sơ nội bộ; nguyên tắc nào giảm rủi ro cấp quyền quá mức?
A. Chấp nhận mọi attribute và group claim rồi tự chuyển thành quyền admin.
B. Tin thuộc tính do trình duyệt bổ sung nếu trùng tên claim trong assertion.
C. Chỉ nhận thuộc tính cần thiết từ issuer tin cậy và dùng mapping đã duyệt.
D. Dùng mọi giá trị NameID làm role vì IdP đã xác thực người dùng.
Đáp án đúng: C

13. Response được ký nhưng Assertion bên trong không ký; SP cần chú ý điều gì?
A. Xác minh Response; chỉ dùng Assertion nằm trong Response đó.
B. Bỏ kiểm tra chữ ký Response nếu Assertion có đủ NameID và Conditions.
C. Tin Assertion bất kỳ trong XML vì chữ ký Response bao phủ mọi tài liệu.
D. Chỉ tin khóa trong KeyInfo rồi chấp nhận mọi Assertion lồng nhau.
Đáp án đúng: A

14. XML Signature Wrapping có thể đánh lừa SP bằng cách nào?
A. Thay đổi thời gian hệ thống để NotOnOrAfter luôn nằm trong tương lai.
B. Mã hóa NameID bằng khóa SP để trình duyệt không đọc được định danh.
C. Gửi cùng một AuthnRequest nhiều lần để tạo hai phiên độc lập.
D. Đặt assertion khác vào node ứng dụng đọc, còn chữ ký bảo vệ node khác.
Đáp án đúng: D

15. Vì sao canonicalization quan trọng khi xác minh XML Signature?
A. Mã hóa XML thành ciphertext để bảo vệ bí mật của assertion.
B. Thay thế việc kiểm tra chữ ký bằng so sánh chuỗi XML thô.
C. Tự động loại bỏ mọi node không hợp lệ theo schema SAML.
D. Chuẩn hóa XML để hai bên tính chữ ký trên cùng biểu diễn.
Đáp án đúng: D

16. SP kiểm tra Conditions của Assertion; cách diễn giải NotBefore và NotOnOrAfter nào đúng?
A. NotBefore là hạn cuối và NotOnOrAfter là thời điểm bắt đầu hiệu lực.
B. Kiểm tra khoảng hiệu lực và cho phép clock skew có giới hạn.
C. Hai giá trị chỉ dùng để ghi log, không ảnh hưởng quyết định chấp nhận.
D. Chỉ cần một trong hai mốc hợp lệ là SP có thể chấp nhận assertion.
Đáp án đúng: B

17. AudienceRestriction trong Assertion bảo vệ điều gì?
A. Giới hạn assertion cho đúng trình duyệt đã gửi AuthnRequest ban đầu.
B. Giới hạn assertion cho đúng SP hoặc audience được chỉ định.
C. Xác định nhóm người dùng được phép truy cập từng chức năng của SP.
D. Chỉ định CA nào được phép phát hành chứng thư TLS cho IdP.
Đáp án đúng: B

18. Với bearer SubjectConfirmationData, SP cần kiểm tra tập điều kiện nào?
A. Recipient, thời hạn và InResponseTo nếu có request tương ứng.
B. Email, display name và nhóm người dùng do trình duyệt gửi kèm.
C. EntityID của IdP, địa chỉ IP và phiên bản trình duyệt người dùng.
D. KeyInfo, thuật toán nén và thời gian tạo file metadata của đối tác.
Đáp án đúng: A

19. Cơ chế nào ngăn một Assertion hợp lệ bị gửi lại để tạo thêm phiên đăng nhập?
A. Chỉ kiểm tra chữ ký mỗi lần vì chữ ký hợp lệ ngăn phát lại thông điệp.
B. Xóa Assertion ID ngay sau khi parse để giảm dung lượng bộ nhớ.
C. Lưu Assertion ID đã dùng trong replay cache suốt cửa sổ chấp nhận.
D. Dùng NameID làm nonce chung cho mọi assertion của cùng người dùng.
Đáp án đúng: C

20. RelayState được trả về sau SSO; cách nào hạn chế open redirect và sửa đổi trạng thái?
A. Chấp nhận URL tuyệt đối do trình duyệt gửi vì Response đã ký từ IdP.
B. Ràng buộc RelayState với phiên/request và đích điều hướng cho phép.
C. Dùng RelayState làm nơi chứa access token để SP khôi phục phiên.
D. Bỏ kiểm tra RelayState vì binding POST luôn bảo đảm tính toàn vẹn của nó.
Đáp án đúng: B

21. Cấu hình XML parser cho endpoint SAML nên làm gì để phòng XXE?
A. Bật external entity nhưng giới hạn số ký tự trong NameID.
B. Cho phép DTD nội bộ và chỉ chặn URL HTTP trong document.
C. Tắt DTD và external entity; chặn truy cập tài nguyên ngoài.
D. Tải schema từ URL trong XML rồi xác minh chữ ký sau khi parse.
Đáp án đúng: C

22. Một endpoint SAML nhận XML rất lớn với cây lồng sâu; kiểm soát nào giảm nguy cơ parser DoS?
A. Tăng timeout vô hạn để parser hoàn tất thông điệp của đối tác.
B. Tắt schema validation và signature verification để giảm CPU xử lý.
C. Chấp nhận mọi độ sâu XML nếu thông điệp có chứng thư ký hợp lệ.
D. Giới hạn kích thước, độ sâu, số node và thời gian xử lý XML.
Đáp án đúng: D

23. Metadata SAML được tải định kỳ từ đối tác; cách nào giảm nguy cơ trust bị thay đổi trái phép?
A. Tự động tin mọi metadata mới vì endpoint tải xuống vẫn dùng HTTPS.
B. Xác minh chữ ký metadata theo trust anchor đã thiết lập.
C. Chỉ so sánh EntityID và bỏ qua thay đổi khóa hoặc ACS endpoint.
D. Chấp nhận chứng thư mới nếu metadata có thời điểm cập nhật gần đây.
Đáp án đúng: B

24. Khi rollover signing certificate, cách chuyển đổi nào giảm gián đoạn SSO?
A. Xóa khóa cũ ngay khi tạo khóa mới rồi yêu cầu người dùng đăng nhập lại.
B. Đổi khóa ở SP trước và giữ IdP dùng khóa cũ đến hết quý tiếp theo.
C. Công bố khóa mới trước, cho phép chồng lấn và xác nhận hai bên đồng bộ.
D. Giữ nguyên khóa cũ vĩnh viễn để mọi assertion lịch sử luôn xác minh được.
Đáp án đúng: C

25. Encrypted Assertion thường được dùng để bảo vệ điều gì?
A. Thay thế chữ ký để SP không cần xác minh nguồn phát hành assertion.
B. Giữ bí mật assertion khỏi bên trung gian qua trình duyệt.
C. Ngăn SP đọc NameID sau khi đã giải mã assertion bằng khóa của mình.
D. Mã hóa metadata để trình duyệt không thể tìm ACS endpoint của SP.
Đáp án đúng: B

26. SP cần giải mã EncryptedAssertion; chứng thư nào thường được dùng cho mục đích này?
A. Dùng private key khớp encryption certificate của SP.
B. Khóa riêng của IdP dùng để ký Response gửi tới ACS endpoint.
C. Chứng thư TLS của trình duyệt dùng trong kết nối HTTPS tới SP.
D. Bất kỳ chứng thư ký nào của đối tác có cùng tên EntityID.
Đáp án đúng: A

27. Trong SAML Single Logout, front-channel, back-channel và SessionIndex liên quan thế nào?
A. Front-channel qua browser, back-channel trực tiếp; SessionIndex xác định phiên.
B. Front-channel dùng XML Signature, back-channel chỉ mã hóa; SessionIndex là Assertion ID.
C. Front-channel dành cho IdP-initiated, back-channel cho SP-initiated; SessionIndex là EntityID.
D. Cả hai đều xóa tài khoản; SessionIndex xác định group membership cần thu hồi.
Đáp án đúng: A

28. ForceAuthn trong AuthnRequest yêu cầu IdP làm gì?
A. Không tương tác với người dùng và chỉ trả kết quả nếu đã có phiên.
B. Bỏ qua MFA để hoàn tất đăng nhập nhanh cho ứng dụng SP.
C. Tự động đăng xuất mọi SP khác trước khi xác thực người dùng.
D. ForceAuthn yêu cầu IdP xác thực lại thay vì dùng phiên cũ.
Đáp án đúng: D

29. IsPassive khác ForceAuthn như thế nào?
A. IsPassive yêu cầu xử lý không tương tác; ForceAuthn yêu cầu xác thực mới.
B. IsPassive buộc xác thực mới; ForceAuthn cấm hiển thị giao diện đăng nhập.
C. Cả hai đều yêu cầu IdP bỏ qua phiên hiện có và chạy MFA mới.
D. IsPassive chỉ áp dụng cho logout; ForceAuthn chỉ áp dụng cho metadata.
Đáp án đúng: A

30. SP cần đánh giá mức xác thực được IdP tuyên bố; trường nào có ý nghĩa liên quan?
A. Attribute NameFormat trong AttributeStatement.
B. NameID Format trong SubjectConfirmationData.
C. AuthnContextClassRef trong AuthnStatement.
D. Destination trong Response header.
Đáp án đúng: C

31. SP yêu cầu MFA nhưng Assertion chỉ cho biết người dùng đã được xác thực; điều gì cần làm?
A. Suy ra MFA đã dùng vì IdP đã ký Assertion hợp lệ.
B. Dùng số lượng AttributeStatement để ước lượng số yếu tố xác thực.
C. Chấp nhận bất kỳ AuthnContext nào nếu NotOnOrAfter còn hiệu lực.
D. Đánh giá AuthnContext theo trust và assurance đã thỏa thuận.
Đáp án đúng: D

32. Một SP liên kết với nhiều IdP; kiểm tra nào ngăn assertion từ tenant khác được chấp nhận?
A. Chấp nhận mọi issuer đã ký bởi bất kỳ chứng thư nào trong hệ thống.
B. Chỉ kiểm tra email domain vì người dùng cùng domain thuộc một tenant.
C. Ràng buộc issuer, audience, khóa và tenant theo từng IdP.
D. Dùng một khóa chung cho mọi IdP và bỏ qua EntityID trong Response.
Đáp án đúng: C

33. SAML Response có StatusCode báo lỗi từ IdP; SP nên phản ứng thế nào?
A. Tạo phiên hạn chế vì chữ ký Response hợp lệ đã chứng minh người dùng.
B. Không tạo phiên và xử lý lỗi theo trạng thái đã xác minh.
C. Bỏ qua StatusCode nếu Assertion có NameID và AttributeStatement.
D. Thử dùng Assertion cũ trong replay cache để duy trì trải nghiệm đăng nhập.
Đáp án đúng: B

34. ACS endpoint cần chống flood và thông điệp SAML quá lớn; biện pháp nào phù hợp?
A. Cho phép mọi request Internet nếu Content-Type là application/samlresponse.
B. Tăng số worker không giới hạn để xử lý mọi burst từ trình duyệt.
C. Chỉ giới hạn số lần đăng nhập theo NameID sau khi parse XML hoàn tất.
D. Rate limit, giới hạn body và kiểm soát tài nguyên parse.
Đáp án đúng: D

35. Audit log SAML cần hỗ trợ điều tra mà không làm lộ dữ liệu nhạy cảm; nên ghi gì?
A. Toàn bộ assertion, NameID, thuộc tính và khóa riêng để tái hiện giao dịch.
B. Correlation ID, issuer, kết quả xác minh, thời điểm và mã lỗi.
C. Cookie phiên, RelayState thô và token đăng nhập để tìm nguyên nhân lỗi.
D. Mật khẩu người dùng cùng payload XML trước và sau khi giải mã.
Đáp án đúng: B

36. Một đội muốn kiểm thử phòng vệ SAML trước khi tích hợp production; bộ negative test nào có giá trị nhất?
A. Thử sai chữ ký, audience, recipient, hết hạn, replay và XML wrapping.
B. Chỉ kiểm tra đăng nhập đúng với một tài khoản và một trình duyệt.
C. Chỉ kiểm tra metadata tải thành công và ACS trả HTTP 200.
D. Chỉ kiểm tra logout sau khi người dùng đăng xuất khỏi trình duyệt.
Đáp án đúng: A

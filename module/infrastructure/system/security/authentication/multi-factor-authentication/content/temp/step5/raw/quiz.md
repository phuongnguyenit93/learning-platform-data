1. Một hệ thống yêu cầu mật khẩu rồi gửi mã OTP qua ứng dụng; điều kiện nào khiến quy trình này thực sự là MFA?
A. Hai bước phải dùng hai màn hình xác minh riêng biệt trong cùng một phiên.
B. Hai bí mật phải có độ dài khác nhau và được nhập theo thứ tự cố định.
C. Hai bước phải chứng minh các yếu tố thuộc ít nhất hai nhóm khác nhau.
D. Hai lần xác minh phải được xử lý bởi hai dịch vụ độc lập của tổ chức.
Đáp án đúng: C

2. Cách phân loại nào mô tả đúng ba nhóm yếu tố xác thực phổ biến?
A. Knowledge là thiết bị dùng; possession là mã nhớ; inherence là vị trí truy cập.
B. Knowledge là điều biết; possession là vật sở hữu; inherence là đặc điểm sinh học.
C. Knowledge là mật khẩu; possession là địa chỉ IP; inherence là thiết bị đã đăng ký.
D. Knowledge là câu hỏi bảo mật; possession là vị trí; inherence là hành vi sử dụng.
Đáp án đúng: B

3. Người dùng nhập mật khẩu và mã PIN khác nhau khi đăng nhập; vì sao đây chưa chắc là MFA?
A. Cả hai được nhập trong một phiên nên chỉ tính là một bước xác minh.
B. PIN luôn là possession factor nếu được nhập trên bàn phím thiết bị.
C. Mật khẩu và PIN chỉ là MFA khi được xác minh bởi hai nhà cung cấp.
D. Cả mật khẩu và PIN đều thuộc nhóm knowledge factor.
Đáp án đúng: D

4. Một hệ thống dùng vị trí GPS và địa chỉ IP để quyết định có yêu cầu MFA; hai dữ liệu này nên được xem là gì?
A. Hai possession factor độc lập vì chúng đến từ hai nguồn mạng khác nhau.
B. Một inherence factor vì chúng phản ánh đặc điểm riêng của người dùng.
C. Tín hiệu ngữ cảnh hỗ trợ đánh giá rủi ro, không tự thân là yếu tố xác thực.
D. Hai knowledge factor vì hệ thống có thể tra cứu chúng trong hồ sơ tài khoản.
Đáp án đúng: C

5. Người dùng nhận email OTP trên cùng điện thoại đang mở ứng dụng đăng nhập; rủi ro thiết kế nào cần xem xét?
A. Email OTP luôn được tính là yếu tố độc lập vì máy chủ gửi mã qua Internet.
B. Hai kênh có thể cùng phụ thuộc một thiết bị và một tài khoản bị chiếm.
C. Việc dùng chung thiết bị làm mã OTP có entropy thấp hơn khi được tạo.
D. Email và ứng dụng cùng thiết bị khiến thời hạn mã phải được đồng bộ thủ công.
Đáp án đúng: B

6. TOTP tạo mã xác thực dựa trên dữ liệu nào giữa authenticator và máy chủ?
A. Public key của máy chủ cùng bộ đếm request được lưu ở trình duyệt.
B. Mật khẩu người dùng cùng số lần đăng nhập thành công trong ngày.
C. Mã ngẫu nhiên do máy chủ tạo và đồng bộ liên tục qua push notification.
D. Shared secret cùng giá trị thời gian được chia thành các time-step.
Đáp án đúng: D

7. HOTP khác TOTP chủ yếu ở thành phần thay đổi nào được dùng để tạo mã?
A. HOTP dùng vị trí thiết bị thay cho shared secret được đăng ký.
B. HOTP ký challenge bằng private key thay vì tính mã OTP.
C. HOTP dùng thời gian UTC nhưng bỏ qua bộ đếm giữa hai lần xác minh.
D. HOTP sử dụng counter tăng theo sự kiện thay cho time-step.
Đáp án đúng: D

8. Một mã OTP đã xác minh thành công vẫn được chấp nhận lần thứ hai; kiểm soát nào xử lý trực tiếp lỗi này?
A. Đánh dấu mã hoặc time-step đã dùng và từ chối replay trong phạm vi hợp lệ.
B. Kéo dài thời hạn OTP để giảm số lần người dùng phải yêu cầu mã mới.
C. Tăng số chữ số OTP để cùng một mã khó bị đoán trong lần xác minh sau.
D. Chỉ ghi nhận IP của request đầu tiên và cho phép các request tiếp theo.
Đáp án đúng: A

9. Đồng hồ điện thoại lệch nhẹ so với máy chủ khiến TOTP hợp lệ bị từ chối; cách xử lý nào phù hợp?
A. Cho phép cửa sổ time-step giới hạn và theo dõi việc lệch đồng hồ.
B. Chấp nhận mọi time-step trong ngày để tránh từ chối người dùng hợp lệ.
C. Tắt kiểm tra thời gian và chỉ xác minh mã dựa trên shared secret.
D. Tự động đặt lại shared secret sau mỗi lần xác minh mã không thành công.
Đáp án đúng: A

10. Endpoint xác minh OTP bị thử hàng nghìn mã liên tiếp; kiểm soát nào giảm nguy cơ đoán mã hiệu quả?
A. Tăng thời hạn OTP để người dùng có thêm cơ hội nhập đúng mã.
B. Giới hạn tốc độ và số lần thử theo tài khoản cùng các tín hiệu rủi ro.
C. Chỉ giới hạn theo IP vì mọi lần thử của một tài khoản luôn cùng địa chỉ.
D. Ẩn thông báo lỗi nhưng tiếp tục xác minh không giới hạn ở phía máy chủ.
Đáp án đúng: B

11. Vì sao SMS OTP thường có mức chống phishing và chiếm đoạt thấp hơn authenticator chống phishing?
A. Mã SMS không thể được xác minh bằng shared secret ở phía máy chủ.
B. SMS luôn dùng mã ngắn hơn TOTP nên không thể đạt entropy tương đương.
C. Số điện thoại có thể bị chiếm qua SIM swap hoặc chuyển tiếp tin nhắn.
D. Tin nhắn SMS không có timestamp nên máy chủ không thể giới hạn thời hạn.
Đáp án đúng: C

12. Email OTP được dùng làm yếu tố thứ hai; điều kiện nào làm suy yếu tính độc lập của nó?
A. Email khôi phục và tài khoản chính cùng dựa trên một credential hoặc phiên.
B. Email được lưu trên máy chủ khác với máy chủ của ứng dụng đăng nhập.
C. Mã được gửi qua SMTP thay vì được tạo trực tiếp trên điện thoại.
D. Người dùng có thể truy cập email từ nhiều thiết bị trong ngày.
Đáp án đúng: A

13. Một người dùng liên tục nhận push approval mà không khởi tạo đăng nhập; cơ chế nào giúp giảm push fatigue?
A. Tự động chấp thuận push đầu tiên rồi yêu cầu xác minh lại ở lần sau.
B. Gửi nhiều push liên tiếp để người dùng chọn thông báo đến sớm nhất.
C. Number matching và hiển thị ngữ cảnh đăng nhập trước khi chấp thuận.
D. Kéo dài thời gian chờ push để người dùng không cần phản hồi ngay.
Đáp án đúng: C

14. Push MFA cần gắn yêu cầu xác minh với phiên đăng nhập đang chờ; dữ liệu nào nên được liên kết?
A. Request identifier cùng ngữ cảnh phiên, thiết bị và thời hạn của challenge.
B. Tên hiển thị của ứng dụng cùng số lần người dùng mở màn hình đăng nhập.
C. Địa chỉ IP hiện tại của máy chủ push cùng phiên bản hệ điều hành điện thoại.
D. Email tài khoản và thời gian gửi thông báo mà không cần mã challenge.
Đáp án đúng: A

15. Trong WebAuthn, thành phần nào giúp ràng buộc xác thực với đúng website?
A. Mã OTP được gửi tới số điện thoại đã xác minh trước khi ký challenge.
B. Địa chỉ IP của trình duyệt được đưa vào public key của authenticator.
C. Tên hiển thị của website được so sánh với email đăng ký của người dùng.
D. Challenge được ký cùng kiểm tra origin và relying party ID.
Đáp án đúng: D

16. Vì sao WebAuthn/passkey có khả năng chống phishing tốt hơn OTP nhập thủ công?
A. Mã xác thực luôn đổi mỗi giây nên trang giả không kịp thu thập mã.
B. Người dùng phải nhập cả mật khẩu lẫn mã PIN trên website thật.
C. Credential được ràng buộc với relying party nên không ký cho origin giả mạo.
D. Private key được gửi tới máy chủ để máy chủ so sánh với bản lưu trữ.
Đáp án đúng: C

17. Trong xác thực khóa công khai của WebAuthn, máy chủ thường lưu thành phần nào?
A. Private key credential để ký challenge thay cho thiết bị người dùng.
B. Mẫu sinh trắc học thô để so sánh mỗi lần người dùng đăng nhập.
C. Mã PIN của authenticator để máy chủ mở khóa private key từ xa.
D. Public key credential để xác minh chữ ký từ authenticator.
Đáp án đúng: D

18. Trong WebAuthn, user presence và user verification khác nhau như thế nào?
A. Presence xác minh sinh trắc học; verification chỉ kiểm tra thiết bị được kết nối.
B. Presence xác nhận có thao tác người dùng; verification xác minh người dùng cục bộ.
C. Presence xác nhận origin; verification xác nhận relying party ID của website.
D. Presence kiểm tra private key; verification kiểm tra public key ở máy chủ.
Đáp án đúng: B

19. Passkey được đồng bộ giữa các thiết bị và credential gắn với một thiết bị khác nhau chủ yếu ở đâu?
A. Khả năng chống phishing của credential đồng bộ luôn thấp hơn credential gắn thiết bị.
B. Cách sao lưu và khôi phục credential cùng ranh giới tin cậy của nhà cung cấp.
C. Credential đồng bộ không dùng public key; credential gắn thiết bị mới dùng chữ ký.
D. Credential gắn thiết bị không cần user verification khi tạo chữ ký đăng nhập.
Đáp án đúng: B

20. Khi dùng sinh trắc học để mở khóa passkey, dữ liệu sinh trắc học thường được xử lý ở đâu?
A. Authenticator xác minh cục bộ và không gửi mẫu sinh trắc học thô lên máy chủ.
B. Máy chủ lưu mẫu sinh trắc học rồi so khớp trực tiếp trong mỗi lần đăng nhập.
C. Identity provider gửi mẫu khuôn mặt qua TLS để relying party tự xác minh.
D. Trình duyệt chuyển mẫu sinh trắc học vào challenge để máy chủ giải mã.
Đáp án đúng: A

21. Một người dùng vừa đăng nhập bằng phiên hiện có vừa đăng ký thêm authenticator mới; kiểm soát nào quan trọng nhất?
A. Chỉ cần xác minh email vì phiên hiện tại đã được cấp sau khi đăng nhập.
B. Cho phép đăng ký ngay nếu địa chỉ IP trùng với lần đăng nhập trước.
C. Yêu cầu tái xác thực mạnh trước khi liên kết yếu tố mới với tài khoản.
D. Chờ tới lần đăng nhập tiếp theo mới kiểm tra quyền sở hữu authenticator.
Đáp án đúng: C

22. Recovery code được thiết kế để dùng khi mất authenticator; cách quản lý nào phù hợp?
A. Dùng một mã cố định cho tài khoản và cho phép tái sử dụng khi cần.
B. Tạo mã khó đoán, lưu an toàn và vô hiệu hóa từng mã sau khi sử dụng.
C. Tạo mã từ ngày sinh để người dùng dễ nhớ và có thể khôi phục nhanh.
D. Lưu mã ở dạng rõ trong hồ sơ người dùng để bộ phận hỗ trợ tra cứu.
Đáp án đúng: B

23. Help desk nhận yêu cầu reset MFA từ người gọi tự nhận là chủ tài khoản; quy trình nào phù hợp?
A. Xác minh danh tính bằng quy trình độc lập và lưu dấu vết phê duyệt reset.
B. Chỉ hỏi một số thông tin hồ sơ dễ nhớ rồi tắt MFA trong cuộc gọi.
C. Gửi OTP tới số điện thoại mới do người gọi cung cấp để xác nhận quyền sở hữu.
D. Dựa vào việc người gọi biết email đăng nhập và thời điểm tạo tài khoản.
Đáp án đúng: A

24. Một phiên đăng nhập đã hoàn thành MFA nhưng attacker đánh cắp session cookie; rủi ro chính là gì?
A. Session cookie tự chuyển thành possession factor mới và hết hiệu lực ngay.
B. MFA bảo vệ mọi request tiếp theo nên cookie bị đánh cắp không có giá trị.
C. Kẻ tấn công có thể sử dụng lại phiên đã xác thực mà không lặp MFA.
D. Máy chủ tự yêu cầu OTP mỗi lần cookie được gửi từ một trình duyệt khác.
Đáp án đúng: C

25. Khi người dùng đổi thông tin thanh toán hoặc thêm người thụ hưởng mới, chính sách nào phù hợp?
A. Yêu cầu step-up authentication theo mức nhạy cảm của hành động.
B. Chỉ xác minh MFA khi người dùng đăng xuất khỏi thiết bị hiện tại.
C. Giữ nguyên kết quả MFA của phiên dù thời gian và rủi ro đã thay đổi.
D. Bỏ qua MFA nếu request đến từ địa chỉ IP từng được dùng trước đây.
Đáp án đúng: A

26. Adaptive authentication dùng vị trí, thiết bị và hành vi đăng nhập để làm gì?
A. Thay thế toàn bộ yếu tố xác thực bằng điểm tin cậy của địa chỉ IP.
B. Điều chỉnh mức xác minh theo rủi ro kết hợp với yếu tố xác thực thực sự.
C. Biến vị trí và dấu vân tay thiết bị thành hai possession factor độc lập.
D. Bỏ qua xác minh danh tính khi người dùng ở trong mạng nội bộ quen thuộc.
Đáp án đúng: B

27. Một hệ thống muốn xác minh người dùng đã chấp thuận đúng số tiền chuyển khoản; cơ chế nào phù hợp?
A. Transaction signing gắn xác nhận mật mã với nội dung giao dịch cụ thể.
B. Push approval chung cho phiên đăng nhập mà không hiển thị chi tiết giao dịch.
C. OTP đăng nhập được chấp nhận lại cho mọi giao dịch trong cùng phiên.
D. Cookie phiên được ký lại sau khi người dùng mở trang chuyển tiền.
Đáp án đúng: A

28. Một ứng dụng liên kết đăng nhập qua identity provider và cần biết MFA đã được thực hiện; relying party nên kiểm tra gì?
A. Chỉ kiểm tra rằng người dùng đã có session cookie tại identity provider.
B. Chỉ kiểm tra địa chỉ IP của identity provider và thời gian phản hồi.
C. Dựa vào giao diện đăng nhập có hiển thị biểu tượng MFA hay không.
D. Issuer, thời điểm và phương thức hoặc mức đảm bảo trong assertion đáng tin cậy.
Đáp án đúng: D

29. Một hệ thống vẫn cho phép đăng nhập qua giao thức cũ không hỗ trợ MFA; rủi ro nào cần xử lý?
A. Giao thức cũ làm mã OTP có entropy cao hơn và khó đồng bộ hơn.
B. MFA chỉ áp dụng ở trình duyệt nên giao thức cũ không ảnh hưởng bảo mật.
C. Đăng nhập cũ tự kế thừa mức đảm bảo từ phiên MFA gần nhất của người dùng.
D. Legacy authentication tạo đường vòng bỏ qua chính sách MFA của tài khoản.
Đáp án đúng: D

30. Push request đã hết hạn nhưng người dùng vẫn bấm Approve; máy chủ nên xử lý thế nào?
A. Chấp nhận nếu tài khoản và thiết bị vẫn khớp với lần đăng nhập trước.
B. Gia hạn challenge cũ để tránh người dùng phải bắt đầu đăng nhập lại.
C. Từ chối challenge hết hạn hoặc đã bị hủy và yêu cầu phiên mới.
D. Chấp nhận rồi yêu cầu thêm OTP sau khi cấp session tạm thời.
Đáp án đúng: C

31. Endpoint gửi lại OTP bị lạm dụng để dò tài khoản và gây chi phí tin nhắn; kiểm soát nào phù hợp?
A. Cho phép gửi không giới hạn nhưng ẩn số điện thoại trên giao diện người dùng.
B. Giới hạn gửi theo tài khoản, đích nhận và nguồn, đồng thời tránh lộ trạng thái tài khoản.
C. Giới hạn riêng theo IP và trả thông báo khác nhau cho tài khoản tồn tại.
D. Chỉ giới hạn số lần xác minh OTP, không giới hạn số lần gửi mã mới.
Đáp án đúng: B

32. Khi ghi log sự kiện MFA, dữ liệu nào nên được loại khỏi log thông thường?
A. Thời điểm sự kiện, kết quả xác minh và mã định danh tương quan của request.
B. Loại authenticator, mức rủi ro và kết quả policy decision của phiên.
C. OTP, shared secret, recovery code và dữ liệu bí mật có thể tái sử dụng.
D. Danh tính actor đã được bảo vệ cùng lý do reset hoặc thu hồi yếu tố.
Đáp án đúng: C

33. Một người dùng không thể sử dụng smartphone hoặc sinh trắc học; chính sách MFA nên được thiết kế ra sao?
A. Tắt MFA vĩnh viễn cho nhóm người dùng không có thiết bị cá nhân.
B. Cho phép dùng câu hỏi bảo mật đơn giản làm phương thức thay thế mặc định.
C. Yêu cầu người dùng chia sẻ authenticator của đồng nghiệp trong thời gian dài.
D. Cung cấp phương thức thay thế an toàn với mức đảm bảo tương đương phù hợp.
Đáp án đúng: D

34. Khi kiểm thử quy trình WebAuthn, trường hợp nào kiểm tra trực tiếp khả năng chống replay?
A. Đăng nhập lại bằng cùng authenticator sau khi máy chủ cấp challenge mới.
B. Xác minh chữ ký hợp lệ với challenge mới do máy chủ vừa phát hành.
C. Đăng ký thêm credential trên cùng tài khoản sau khi xác thực lại.
D. Gửi lại assertion với challenge đã được xác minh và yêu cầu máy chủ từ chối.
Đáp án đúng: D

35. Một tổ chức đánh giá hiệu quả MFA sau triển khai; tập kiểm thử nào bao quát nhất?
A. Chỉ đo thời gian nhập OTP và tỷ lệ đăng nhập thành công trên trình duyệt.
B. Kiểm tra đăng ký, xác minh, replay, step-up, recovery, thu hồi và đường bypass.
C. Chỉ kiểm tra người dùng có thể đăng ký authenticator và nhận thông báo.
D. Chỉ kiểm tra đăng nhập bình thường bằng phương thức MFA phổ biến nhất.
Đáp án đúng: B

36. Người dùng báo security key đã mất nhưng vẫn còn đăng nhập trên một thiết bị; hành động nào phù hợp?
A. Thu hồi credential bị mất, đánh giá phiên liên quan và yêu cầu xác minh lại khi cần.
B. Giữ credential hoạt động đến lần đăng nhập kế tiếp để tránh khóa nhầm tài khoản.
C. Chỉ xóa thiết bị khỏi danh sách hiển thị, vì credential tự hết hạn theo phiên.
D. Tắt MFA trên toàn tổ chức rồi đăng ký lại các authenticator sau khi xử lý.
Đáp án đúng: A

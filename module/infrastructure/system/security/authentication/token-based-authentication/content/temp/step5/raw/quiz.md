1. Một API cần thu hồi quyền truy cập ngay cả khi token chưa hết hạn. Loại token nào thường phù hợp hơn?
A. Opaque token được introspect tại authorization server.
B. ID token được phát hành cho client sau lần đăng nhập gần nhất.
C. API key tĩnh được lưu trong cấu hình của ứng dụng gọi API.
D. JWT tự chứa claim và chỉ xác minh chữ ký tại resource server.
Đáp án đúng: A

2. Một JWT có chữ ký hợp lệ nhưng payload bị đọc được bởi bất kỳ ai có token. Kết luận nào đúng?
A. JWT luôn mã hóa payload bằng khóa riêng của issuer.
B. Chữ ký số tự động che nội dung claim khỏi người nhận token.
C. JWS bảo vệ tính toàn vẹn, không mặc định mã hóa payload.
D. Base64url trong JWT cung cấp tính bí mật cho các claim.
Đáp án đúng: C

3. Ứng dụng gửi ID token đến API để đọc dữ liệu tài khoản. API nên xử lý thế nào?
A. Chấp nhận ID token nếu client gửi thêm refresh token kèm theo.
B. Chấp nhận ID token nếu chữ ký và thời hạn còn hợp lệ.
C. Từ chối ID token và yêu cầu access token đúng audience.
D. Đổi ID token thành API key bằng cách băm subject claim.
Đáp án đúng: C

4. API nhận access token có aud trỏ tới một API khác. Hành vi nào đúng?
A. Chấp nhận token nếu scope chứa tên hành động mà endpoint cần.
B. Từ chối token vì audience không xác định API hiện tại.
C. Tự sửa audience trong bộ nhớ trước khi kiểm tra chữ ký token.
D. Chấp nhận token nếu issuer thuộc danh sách nhà cung cấp tin cậy.
Đáp án đúng: B

5. JWT có chữ ký hợp lệ nhưng iss không khớp issuer đã cấu hình. Resource server nên làm gì?
A. Từ chối token vì issuer không nằm trong trust configuration.
B. Chấp nhận token nếu sub khớp một tài khoản đang hoạt động.
C. Dùng JWKS của issuer bất kỳ để thử xác minh lại token.
D. Chỉ kiểm tra exp vì chữ ký đã chứng minh nguồn phát hành.
Đáp án đúng: A

6. Một access token chứa exp và nbf. Resource server cần diễn giải hai claim này thế nào?
A. Token chỉ hợp lệ sau nbf và trước exp theo thời gian kiểm tra.
B. exp áp dụng cho refresh token, còn nbf áp dụng cho access token.
C. nbf là thời điểm hết hạn còn exp là thời điểm phát hành token.
D. Hai claim chỉ dùng cho logging và không ảnh hưởng quyết định xác minh.
Đáp án đúng: A

7. JWT header khai báo alg=none. Cấu hình verifier nào ngăn việc chấp nhận token không chữ ký?
A. Chấp nhận none khi payload chứa issuer và audience hợp lệ.
B. Chỉ cho phép danh sách thuật toán ký đã cấu hình trước.
C. Chọn thuật toán theo độ dài chuỗi chữ ký do client cung cấp.
D. Tin thuật toán trong header nếu token được gửi qua HTTPS.
Đáp án đúng: B

8. JWT có kid chưa xuất hiện trong cache JWKS. Verifier nên làm gì?
A. Dùng khóa đầu tiên trong cache để thử xác minh chữ ký token.
B. Tải khóa từ URL bất kỳ được gửi kèm trong JWT header.
C. Bỏ qua chữ ký tạm thời và chỉ kiểm tra các claim thời gian.
D. Lấy JWKS từ issuer tin cậy, tìm kid và xử lý thất bại an toàn.
Đáp án đúng: D

9. Một hệ thống cần bảo vệ cả tính toàn vẹn và tính bí mật của token. Cơ chế nào phù hợp?
A. Băm payload bằng SHA-256 trước khi gửi token đến resource server.
B. Dùng JWE với thuật toán mã hóa được cấu hình an toàn.
C. Dùng JWS vì chữ ký số đồng thời mã hóa toàn bộ payload.
D. Base64url encode JWT rồi lưu trong cookie có thuộc tính Secure.
Đáp án đúng: B

10. Resource server dùng opaque token và introspection endpoint tạm thời không khả dụng. Cách vận hành nào phù hợp?
A. Áp dụng cache ngắn có giới hạn hoặc từ chối theo chính sách fail-closed.
B. Chuyển sang giải mã opaque token bằng khóa public của issuer.
C. Bỏ qua introspection cho tới khi endpoint hoạt động trở lại.
D. Chấp nhận mọi token chưa hết hạn theo dữ liệu client tự gửi.
Đáp án đúng: A

11. Một access token có scope orders:read. API cần cho phép đọc đơn hàng. Kiểm tra nào vẫn cần thiết?
A. Kiểm tra scope và quyền trên chính đối tượng đơn hàng.
B. Chỉ xác minh token có chữ ký hợp lệ và còn hạn sử dụng.
C. Chấp nhận mọi order ID vì scope đã giới hạn hành động đọc.
D. Kiểm tra user có đăng nhập qua giao diện trước khi trả dữ liệu.
Đáp án đúng: A

12. Ứng dụng nền không có người dùng tương tác cần lấy token để gọi API. Grant nào thường phù hợp?
A. Password grant bằng cách lưu mật khẩu người dùng trong job.
B. Authorization code với redirect về trình duyệt không có người dùng.
C. Implicit grant để token được trả trực tiếp trong fragment URL.
D. Client credentials với xác thực client phù hợp.
Đáp án đúng: D

13. Ứng dụng công khai dùng authorization code flow. Biện pháp nào giảm nguy cơ code interception?
A. Trả access token qua query của redirect URI.
B. Dùng redirect URI wildcard để chấp nhận mọi callback.
C. Dùng PKCE với verifier bí mật theo từng giao dịch.
D. Nhúng client secret vào mã ứng dụng công khai.
Đáp án đúng: C

14. Bearer access token cần được gửi đến API qua kênh nào?
A. Query string qua HTTPS để proxy dễ ghi nhận request.
B. Cookie không có thuộc tính bảo vệ qua HTTP nội bộ.
C. Authorization header qua kết nối TLS đã xác minh chứng thư.
D. Fragment URL để trình duyệt tự gửi token cùng request.
Đáp án đúng: C

15. Vì sao không nên truyền bearer token trong query string của URL?
A. URL có thể bị lưu trong history, log và header Referer.
B. TLS không mã hóa phần query string khi truyền qua mạng.
C. Query string luôn bị mã hóa yếu hơn body của HTTP request.
D. Token trong URL tự mất hiệu lực khi người dùng đóng tab trình duyệt.
Đáp án đúng: A

16. Một ứng dụng web lưu session token trong cookie. Tập thuộc tính nào giúp giảm nguy cơ lộ token và CSRF?
A. HttpOnly tắt same-origin policy và ngăn mọi request giả mạo.
B. SameSite=None kết hợp bỏ kiểm tra Origin cho mọi thao tác.
C. Domain rộng, Path / và Max-Age dài để giảm số lần đăng nhập.
D. Secure, HttpOnly, SameSite phù hợp và kiểm soát CSRF bổ sung.
Đáp án đúng: D

17. Ứng dụng web muốn giảm khả năng JavaScript đọc được session token. Cách lưu trữ nào phù hợp?
A. Local storage vì dữ liệu không tự gửi trong request cross-site.
B. Cookie HttpOnly, Secure và chính sách CSRF phù hợp.
C. Session storage vì script cùng origin không thể đọc giá trị lưu.
D. Biến JavaScript toàn cục vì chỉ tồn tại trong tab hiện tại.
Đáp án đúng: B

18. Ứng dụng di động cần lưu refresh token qua lần khởi động lại. Nơi lưu nào phù hợp?
A. Log ứng dụng cục bộ có quyền đọc giới hạn cho user hiện tại.
B. File cấu hình plaintext nằm trong thư mục dữ liệu ứng dụng.
C. Keychain hoặc Keystore được bảo vệ bởi hệ điều hành.
D. Shared preferences không mã hóa để dễ đồng bộ giữa thiết bị.
Đáp án đúng: C

19. Refresh token rotation được triển khai. Server nhận lại một refresh token cũ đã dùng trước đó. Hành động nào phù hợp?
A. Đánh dấu reuse và thu hồi token family theo chính sách.
B. Bỏ qua request mà không ghi nhận để tránh ảnh hưởng người dùng.
C. Gia hạn refresh token cũ và giữ nguyên các token con hiện có.
D. Phát hành access token mới vì refresh token cũ từng hợp lệ.
Đáp án đúng: A

20. Một ứng dụng cấp refresh token vô thời hạn cho thiết bị không hoạt động nhiều tháng. Cải tiến nào phù hợp?
A. Giữ token vô hạn nhưng yêu cầu TLS khi sử dụng lại.
B. Gia hạn token mỗi lần ứng dụng chạy nền dù không có hoạt động user.
C. Chuyển refresh token thành JWT để không cần quản lý thời hạn.
D. Đặt absolute lifetime và idle timeout theo mức rủi ro.
Đáp án đúng: D

21. Người dùng logout nhưng JWT access token tự chứa vẫn còn hạn. Cách nào hỗ trợ thu hồi sớm?
A. Chỉ xóa refresh token vì access token sẽ tự mất hiệu lực ngay.
B. Xóa token khỏi bộ nhớ client để resource server tự nhận biết logout.
C. Dùng denylist hoặc trạng thái phiên được kiểm tra trước khi cho phép.
D. Đổi claim iat trong token phía client sau khi logout hoàn tất.
Đáp án đúng: C

22. Một service gọi service khác thay mặt người dùng nhưng chỉ cần một phần quyền ban đầu. Token exchange nên làm gì?
A. Phát hành token mới với audience và scope được thu hẹp.
B. Tạo token mới với scope rộng hơn để tránh lỗi khi service mở rộng.
C. Đổi subject thành service account và giữ nguyên mọi quyền không giới hạn.
D. Chuyển tiếp nguyên token gốc để giữ nguyên toàn bộ quyền của user.
Đáp án đúng: A

23. Bearer token bị sao chép sang máy khác và được sử dụng thành công. Cơ chế nào ràng buộc token với client key?
A. DPoP yêu cầu proof được ký bằng khóa của client.
B. PKCE ràng buộc mọi API request với khóa TLS của trình duyệt.
C. JWE ràng buộc token với địa chỉ IP tại thời điểm phát hành.
D. HMAC trên payload bảo đảm token không thể được gửi từ thiết bị khác.
Đáp án đúng: A

24. Một API cần ràng buộc access token với chứng thư client trong kết nối TLS. Cơ chế nào phù hợp?
A. PKCE verifier được gửi trong TLS handshake để ràng buộc token.
B. Cookie SameSite yêu cầu client gửi cùng chứng thư trong mỗi request.
C. mTLS-bound token yêu cầu client trình chứng thư tương ứng.
D. JWT audience ràng buộc token với private key của máy khách.
Đáp án đúng: C

25. Một API nhạy cảm cần chống replay của request đã ký trong thời gian ngắn. Tổ hợp nào phù hợp?
A. Dùng user agent làm định danh duy nhất của từng request gửi đến.
B. Nonce hoặc jti dùng một lần cùng timestamp và cửa sổ chấp nhận.
C. Tăng thời hạn token để request retry không bị từ chối nhầm.
D. Chỉ kiểm tra chữ ký và cho phép request lặp trong suốt token lifetime.
Đáp án đúng: B

26. Một API key dùng chung giữa nhiều khách hàng bị lộ. Thiết kế nào giúp giới hạn tác động về sau?
A. Giữ một key chung nhưng đổi giá trị theo lịch cố định mỗi năm.
B. Mã hóa key trong response để các consumer không thể sao chép.
C. Dùng cùng key nhưng phân biệt khách hàng bằng User-Agent header.
D. Cấp key riêng theo consumer, scope, quota và khả năng thu hồi.
Đáp án đúng: D

27. Token ngẫu nhiên dạng opaque được lưu trong database phía server. Cách nào giảm rủi ro khi database bị đọc trái phép?
A. Băm token bằng checksum nhanh không khóa để khôi phục khi cần.
B. Lưu token plaintext nhưng ẩn cột khỏi các màn hình quản trị.
C. Lưu hash an toàn của token và chỉ trả token gốc một lần.
D. Mã hóa token bằng khóa đặt cùng bảng để thuận tiện truy vấn.
Đáp án đúng: C

28. Một hệ thống tạo bearer token ngẫu nhiên. Thuộc tính nào quan trọng nhất để chống đoán token?
A. UUID được tạo từ MAC address và thời gian hệ thống.
B. Entropy cao từ bộ sinh số ngẫu nhiên mật mã an toàn.
C. Giá trị tăng tuần tự nhưng được mã hóa Base64 trước khi gửi.
D. Chuỗi dài có tiền tố user ID và timestamp hiện tại.
Đáp án đúng: B

29. Issuer cần xoay signing key mà không làm gián đoạn xác minh token đang lưu hành. Quy trình nào phù hợp?
A. Xóa khóa cũ ngay khi tạo khóa mới rồi yêu cầu mọi token đăng nhập lại.
B. Dùng khóa mới để xác minh token cũ và bỏ qua kid trong header.
C. Công bố khóa mới sau khi tất cả token cũ đã hết hạn tự nhiên.
D. Công bố khóa mới trước, ký bằng khóa mới rồi giữ khóa cũ trong giai đoạn chuyển tiếp.
Đáp án đúng: D

30. Nhiều resource server cần xác minh token nhưng không nên chia sẻ bí mật ký. Mô hình khóa nào phù hợp?
A. Issuer công bố private key trong JWKS để mọi API xác minh trực tiếp.
B. Mọi resource server giữ chung secret HMAC để ký và xác minh token.
C. Mỗi resource server tạo một private key riêng rồi gửi issuer dùng ký.
D. Issuer giữ private key và resource server dùng public key xác minh.
Đáp án đúng: D

31. Private key ký access token cần được bảo vệ và kiểm soát quyền sử dụng. Giải pháp nào phù hợp?
A. Mã hóa private key bằng secret lưu cạnh ứng dụng gọi ký.
B. Sao chép private key lên mọi node để tránh phụ thuộc dịch vụ ngoài.
C. Dùng KMS hoặc HSM với policy giới hạn thao tác ký.
D. Đặt private key trong source repository riêng chỉ admin đọc được.
Đáp án đúng: C

32. Log hệ thống cần correlation để điều tra token bị lạm dụng. Cách ghi log nào phù hợp?
A. Ghi toàn bộ Authorization header để điều tra chính xác khi cần.
B. Ghi token ID hoặc fingerprint đã bảo vệ, không ghi bearer token.
C. Ghi refresh token đã mã hóa Base64 để đội vận hành tra cứu.
D. Ghi access token trong log debug nhưng xóa sau mỗi lần deploy.
Đáp án đúng: B

33. JWT chứa nhiều thông tin cá nhân và quyền chi tiết dù API chỉ cần subject và scope. Cách cải tiến nào phù hợp?
A. Nén payload để giảm kích thước nhưng không thay đổi nội dung claim.
B. Giảm claim xuống mức cần thiết và tra cứu dữ liệu nhạy cảm phía server.
C. Mã hóa mọi claim bằng JWE rồi giữ nguyên toàn bộ dữ liệu cá nhân.
D. Đưa thêm dữ liệu vào header để payload không hiển thị trực tiếp.
Đáp án đúng: B

34. Token có claim tenant_id do client tự chọn. Resource server nên xác định tenant thế nào?
A. Chọn tenant từ query string nếu claim và URL cùng có giá trị.
B. Dùng tenant đầu tiên trong danh sách mà user từng truy cập.
C. Tin tenant claim nếu JWT được ký bởi một issuer đã tin cậy.
D. Đối chiếu tenant claim với danh tính và quyền được cấp cho principal.
Đáp án đúng: D

35. Một verifier chấp nhận RSA public key ở cấu hình nhưng token khai báo thuật toán HMAC. Lỗi nào cần tránh?
A. Clock skew khiến thời điểm phát hành token bị đọc sai.
B. Algorithm confusion giữa khóa bất đối xứng và thuật toán đối xứng.
C. Audience mismatch giữa access token và ID token.
D. Replay do token được gửi nhiều lần từ cùng một client.
Đáp án đúng: B

36. Các máy chủ xác minh JWT có đồng hồ lệch vài giây. Cách xử lý nào phù hợp?
A. Dùng thời gian client gửi trong request làm nguồn thời gian chuẩn.
B. Bỏ kiểm tra expiration để tránh từ chối token hợp lệ.
C. Tăng token lifetime để bù cho mọi sai lệch đồng hồ.
D. Đồng bộ thời gian và đặt clock-skew tolerance nhỏ, có giới hạn.
Đáp án đúng: D

37. Một hệ thống cần kiểm thử xác minh token trước khi phát hành. Bộ test nào bao phủ tốt các trường hợp từ chối?
A. Chỉ kiểm tra token sai định dạng và token có payload rỗng.
B. Chỉ kiểm tra tốc độ xác minh và kích thước token trung bình.
C. Chỉ kiểm tra token hợp lệ qua một lần gọi API thành công.
D. Sai chữ ký, issuer, audience, thời hạn, thuật toán và token bị thu hồi.
Đáp án đúng: D

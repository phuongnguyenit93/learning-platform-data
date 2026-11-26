1. Một ứng dụng cần phát hành session identifier mới cho mỗi phiên; đặc tính nào quan trọng nhất để ngăn attacker đoán ID hợp lệ?
A. Tạo ID tăng tuần tự và thay prefix sau mỗi lần đăng nhập.
B. Tạo ID ngẫu nhiên bằng bộ sinh mật mã với entropy đủ lớn.
C. Mã hóa user ID bằng khóa cố định rồi dùng làm session ID.
D. Ghép timestamp với địa chỉ IP để tạo ID duy nhất.
Đáp án đúng: B

2. Vì sao session identifier nên là giá trị opaque và không chứa thông tin nhận dạng người dùng?
A. Browser cần đọc user ID trong cookie để tự xác minh phiên ở mỗi request.
B. Session ID phải chứa role để API quyết định quyền mà không tra cứu.
C. Server tra cứu trạng thái phiên từ ID, không cần nhúng PII vào cookie.
D. Mã hóa PII trong ID là đủ vì dữ liệu đã không còn ở dạng rõ.
Đáp án đúng: C

3. Ứng dụng lưu session ID trong cookie; tổ hợp thuộc tính nào phù hợp nhất cho phiên xác thực qua HTTPS?
A. Secure, HttpOnly và SameSite được chọn theo luồng điều hướng.
B. HttpOnly, Domain rộng và SameSite=None cho mọi ứng dụng.
C. Secure, Path hẹp và bỏ HttpOnly để script kiểm tra phiên.
D. SameSite=Strict và bỏ Secure vì cookie chỉ dùng trên cùng site.
Đáp án đúng: A

4. Cookie có tiền tố __Host- cần đáp ứng điều kiện nào để browser chấp nhận?
A. Có HttpOnly, Domain cụ thể và Path=/ cho mọi subdomain.
B. Có Secure, Domain wildcard và Path hẹp theo ứng dụng.
C. Có Secure, Path=/ và không có Domain attribute.
D. Có SameSite=Strict, Max-Age dài và Domain của parent.
Đáp án đúng: C

5. Vì sao không nên truyền session ID trong query string của URL?
A. Query string luôn được browser mã hóa bằng khóa riêng của website.
B. URL có thể xuất hiện trong history, log, bookmark và Referer.
C. Session ID trong URL chỉ được gửi qua POST nên không bị ghi log.
D. URL ngắn hơn cookie nên khó bị quan sát trên mạng.
Đáp án đúng: B

6. Sau khi người dùng đăng nhập thành công bằng session ẩn danh, ứng dụng nên làm gì?
A. Giữ nguyên ID để không mất giỏ hàng và trạng thái trước đăng nhập.
B. Thêm user ID vào session cũ rồi tiếp tục dùng ID do client gửi.
C. Đợi tới lần timeout đầu tiên mới đổi session identifier.
D. Phát hành session ID mới và vô hiệu hóa ID trước xác thực.
Đáp án đúng: D

7. Một attacker khiến nạn nhân dùng trước một session ID mà attacker đã biết; đây là kiểu tấn công nào?
A. Session fixation vì nạn nhân tiếp tục dùng định danh phiên đã bị cài.
B. Session hijacking vì attacker đã đánh cắp cookie xác thực từ browser của nạn nhân.
C. CSRF vì browser tự gửi cookie khi một trang khác kích hoạt request thay đổi trạng thái.
D. Replay attack vì attacker gửi lại request cũ đã ghi nhận để tái sử dụng phiên.
Đáp án đúng: A

8. Khi rotate session ID sau đăng nhập hoặc nâng quyền, cách xử lý ID cũ nào an toàn nhất?
A. Chấp nhận ID cũ vô thời hạn để các tab đang mở không bị gián đoạn.
B. Giữ ID cũ làm alias cho mọi client cho tới khi cookie tự hết hạn.
C. Chỉ đổi ID ở browser nhưng giữ nguyên mapping cũ phía server.
D. Vô hiệu hóa ID cũ sau khi chuyển trạng thái phiên cần giữ.
Đáp án đúng: D

9. Website đặt HttpOnly cho session cookie nhưng không bật Secure; người dùng truy cập qua mạng có thể bị rủi ro gì?
A. JavaScript có thể đọc cookie vì HttpOnly chỉ có hiệu lực trên HTTPS.
B. Browser sẽ không gửi cookie khi người dùng mở tab mới.
C. Cookie tự được mã hóa đầu cuối nên không thể bị nghe lén.
D. Cookie có thể bị gửi qua kết nối HTTP không an toàn.
Đáp án đúng: D

10. Ứng dụng chạy sau reverse proxy và dùng X-Forwarded-Proto để nhận biết HTTPS; cấu hình nào an toàn?
A. Tin mọi X-Forwarded-Proto từ client vì header này đã được proxy giữ nguyên.
B. Ưu tiên scheme do client gửi trong Host header để giữ tương thích.
C. Chỉ tin forwarded headers từ proxy đã xác thực và chặn truy cập trực tiếp.
D. Bỏ kiểm tra TLS ở proxy vì ứng dụng có thể suy ra scheme từ cookie.
Đáp án đúng: C

11. Idle timeout và absolute session lifetime khác nhau như thế nào?
A. Idle timeout giới hạn tổng tuổi phiên; absolute lifetime tính từ request gần nhất rồi tự gia hạn.
B. Cả hai đều được gia hạn mỗi khi browser tải một tài nguyên tĩnh, kể cả không có hoạt động người dùng.
C. Absolute lifetime chỉ áp dụng khi người dùng không có cookie hợp lệ và bị bỏ qua khi có hoạt động.
D. Idle timeout tính từ hoạt động gần nhất; absolute lifetime giới hạn tổng tuổi phiên.
Đáp án đúng: D

12. Một người dùng liên tục gửi request để giữ phiên hoạt động; kiểm soát nào ngăn phiên kéo dài vô hạn?
A. Gia hạn idle timeout sau mỗi request và bỏ giới hạn tổng tuổi phiên.
B. Tăng cookie Max-Age mỗi lần request để đồng bộ với server.
C. Áp dụng absolute lifetime độc lập với sliding idle timeout.
D. Chỉ kết thúc phiên khi browser đóng cửa sổ cuối cùng.
Đáp án đúng: C

13. Cookie còn trong browser nhưng session record đã hết hạn phía server; hệ thống nên xử lý ra sao?
A. Từ chối ID hết hạn và yêu cầu tạo phiên mới sau xác thực.
B. Tạo lại session state từ cookie vì cookie còn hạn là bằng chứng đủ.
C. Gia hạn record theo Max-Age của cookie mà không kiểm tra đăng nhập.
D. Chấp nhận phiên nếu user agent vẫn khớp lần truy cập trước.
Đáp án đúng: A

14. Khi người dùng logout, hành động nào cần thực hiện để kết thúc phiên thực sự?
A. Chỉ xóa cookie phía browser vì server tự biết người dùng đã logout.
B. Chuyển cookie sang SameSite=Strict và giữ session record để tái sử dụng.
C. Đặt idle timeout về 0 ở browser nhưng giữ session phía server.
D. Vô hiệu hóa session phía server và gửi cookie hết hạn về browser.
Đáp án đúng: D

15. Người dùng muốn logout tất cả thiết bị sau khi nghi ngờ tài khoản bị chiếm; ứng dụng cần khả năng nào?
A. Xóa cookie trên thiết bị hiện tại và chờ các thiết bị khác tự timeout.
B. Đổi User-Agent của tài khoản để các thiết bị khác mất phiên.
C. Xóa cache trình duyệt trên server để vô hiệu hóa cookie ở mọi nơi.
D. Liệt kê và thu hồi các session đang hoạt động theo tài khoản.
Đáp án đúng: D

16. Vì sao cookie session làm ứng dụng web cần kiểm soát CSRF cho thao tác thay đổi trạng thái?
A. Cookie session chỉ được gửi khi JavaScript của website đích ký request.
B. Browser tự động đính kèm cookie phù hợp vào request cross-site.
C. CSRF chỉ xảy ra khi session ID được lưu trong local storage.
D. TLS bảo vệ cookie nên attacker không thể khiến browser gửi request.
Đáp án đúng: B

17. Synchronizer token pattern bảo vệ request thay đổi trạng thái bằng cách nào?
A. Server kiểm tra token gắn với phiên và được gửi cùng request hợp lệ.
B. Browser mã hóa session cookie bằng khóa công khai của server rồi gửi kèm token.
C. Server chấp nhận mọi request có Origin header bất kỳ từ HTTPS.
D. Client gửi session ID thêm trong query string để chứng minh nguồn.
Đáp án đúng: A

18. Một hệ thống dùng double-submit cookie để chống CSRF; cách tăng khả năng chống cookie injection là gì?
A. Đặt CSRF cookie ở Domain parent để mọi subdomain có thể ghi.
B. Dùng cùng giá trị cho session ID và CSRF token để dễ đối chiếu.
C. Ký token và ràng buộc nó với session hoặc secret phía server.
D. Chỉ kiểm tra token có tồn tại mà không so sánh với request.
Đáp án đúng: C

19. SameSite=Lax hỗ trợ giảm CSRF nhưng vẫn có thể gửi cookie trong tình huống nào?
A. Cross-site POST, iframe và fetch vẫn luôn mang cookie theo mặc định của trình duyệt.
B. Một số top-level cross-site navigation dùng phương thức an toàn như GET.
C. Chỉ request XMLHttpRequest cùng origin mới được gửi cookie.
D. Cookie chỉ được gửi khi request có custom header do JavaScript đặt.
Đáp án đúng: B

20. Vì sao CORS không thay thế cơ chế chống CSRF cho ứng dụng dùng cookie phiên?
A. CORS buộc browser xóa cookie trước khi gửi request khác origin.
B. CORS xác minh người dùng đã đăng nhập trước khi server xử lý request.
C. CORS chủ yếu kiểm soát việc script đọc phản hồi, không ngăn mọi request cross-site.
D. CORS mã hóa request body và bảo đảm không thể bị giả mạo.
Đáp án đúng: C

21. Endpoint dùng GET để xóa tài khoản vì muốn đơn giản hóa liên kết; rủi ro nào phát sinh?
A. GET có thể bị kích hoạt ngoài ý muốn qua link, prefetch hoặc crawler.
B. GET không gửi cookie nên không thể thay đổi trạng thái phiên.
C. GET luôn yêu cầu CORS preflight trước khi server xử lý.
D. GET chỉ an toàn khi session cookie đặt SameSite=None.
Đáp án đúng: A

22. Một trang có XSS dù session cookie được đặt HttpOnly; attacker vẫn có thể làm gì?
A. Thực hiện request dưới quyền phiên vì browser vẫn tự gửi cookie.
B. Đọc trực tiếp giá trị HttpOnly cookie qua document.cookie.
C. Tạo cookie Secure mới trên mọi domain mà không cần quyền.
D. Giải mã session store phía server chỉ bằng JavaScript trên trang.
Đáp án đúng: A

23. Biện pháp nào giảm nguy cơ XSS dẫn tới hành động trái phép dưới phiên người dùng?
A. Chỉ bật HttpOnly vì thuộc tính này ngăn script độc hại chạy.
B. Output encoding theo ngữ cảnh, sanitization và CSP phù hợp.
C. Chuyển session ID sang URL để script không truy cập cookie.
D. Tắt CSRF token vì XSS đã có thể gửi request cùng cookie.
Đáp án đúng: B

24. Ứng dụng đặt cookie Domain=.example.com để dùng chung session cho mọi subdomain; rủi ro chính là gì?
A. Cookie sẽ chỉ được gửi tới host chính, không thể được subdomain nào khác nhận hoặc ghi.
B. Subdomain yếu hoặc bị chiếm có thể nhận hoặc ghi cookie trong phạm vi parent.
C. Browser tự cô lập cookie theo từng port nên không có chia sẻ.
D. Domain attribute buộc cookie chỉ dùng với request same-site an toàn.
Đáp án đúng: B

25. Vì sao ràng buộc session cứng vào IP address có thể gây khóa nhầm người dùng?
A. IP luôn được browser giữ ổn định trong toàn bộ phiên đăng nhập.
B. IP được mã hóa trong cookie nên không thể thay đổi giữa request.
C. IP chỉ thay đổi khi session ID đã bị đánh cắp.
D. IP có thể đổi do mạng di động, NAT, VPN hoặc proxy.
Đáp án đúng: D

26. Một ứng dụng có nhiều node và muốn chia sẻ trạng thái phiên; lựa chọn nào hỗ trợ failover tốt hơn?
A. Chỉ lưu session trong RAM từng node và dựa vào load balancer ngẫu nhiên.
B. Tạo session ID khác nhau ở mỗi node để tránh đồng bộ trạng thái.
C. Dùng session store dùng chung hoặc replication có kiểm soát.
D. Lưu toàn bộ session trong cookie và tin mọi giá trị client gửi lại.
Đáp án đúng: C

27. Session store phân tán tạm thời không truy cập được; cách xử lý nào an toàn?
A. Chấp nhận session dựa trên cookie chưa hết hạn để duy trì availability.
B. Tạo session mới với cùng quyền mà không xác minh người dùng.
C. Từ chối xác thực phiên không thể kiểm tra và phục hồi theo chính sách.
D. Bỏ qua kiểm tra session store cho request chỉ đọc dữ liệu.
Đáp án đúng: C

28. Logout đã xóa session ở node chính nhưng node khác vẫn chấp nhận bản cache cũ; vấn đề cốt lõi là gì?
A. Độ trễ lan truyền trạng thái thu hồi giữa các node.
B. Cookie Secure không được đồng bộ giữa các node ứng dụng.
C. Browser chưa nhận được SameSite attribute mới từ load balancer.
D. Session ID có entropy thấp nên cache không thể tìm được record.
Đáp án đúng: A

29. Hai request đồng thời rotate cùng một session trên hai node; kiểm soát nào giúp tránh hai phiên kế thừa hợp lệ?
A. Cho phép cả hai node tạo ID mới và giữ cả hai ID cũ trong alias.
B. Dùng thao tác cập nhật nguyên tử hoặc version check cho rotation.
C. Chỉ khóa cookie ở browser vì hai request không thể chạy song song.
D. Đặt idle timeout ngắn để một trong hai request tự hết hạn.
Đáp án đúng: B

30. Một WebSocket đã xác thực bằng session cookie nhưng kết nối tồn tại nhiều giờ; khi session bị thu hồi cần làm gì?
A. Kiểm tra trạng thái phiên định kỳ hoặc đóng kết nối theo sự kiện revoke.
B. Giữ kết nối tới khi browser đóng vì trạng thái xác thực ở handshake không thay đổi suốt kết nối.
C. Chỉ xóa cookie ở browser vì WebSocket sẽ gửi cookie lại cùng mỗi message sau handshake.
D. Tạo session mới cho WebSocket mà không kiểm tra danh tính hoặc quyền của kết nối đã mở.
Đáp án đúng: A

31. Đội vận hành cần điều tra session hijacking; dữ liệu log nào nên tránh ghi trực tiếp?
A. Thời điểm tạo phiên và mã sự kiện đã được che định danh, không chứa credential.
B. Raw session ID hoặc cookie xác thực có thể dùng lại để chiếm phiên.
C. Kết quả revoke cùng correlation ID không chứa credential.
D. Số lượng phiên theo tenant và trạng thái timeout tổng hợp.
Đáp án đúng: B

32. Một tài khoản có session đồng thời từ thiết bị và vị trí khác thường; cách phản ứng nào hợp lý?
A. Khóa vĩnh viễn tài khoản khi chỉ có một tín hiệu địa lý khác biệt, kể cả VPN.
B. Bỏ qua vì nhiều session luôn là hành vi bình thường của mọi người.
C. Ràng buộc mọi session vào cùng User-Agent để loại bỏ khác biệt.
D. Kết hợp tín hiệu rủi ro, step-up authentication và revoke khi cần.
Đáp án đúng: D

33. Response chứa dữ liệu riêng tư được cache ở CDN dùng chung; kiểm soát nào phù hợp?
A. Đặt cookie session thời hạn dài để CDN phân biệt người dùng.
B. Bật CORS wildcard để CDN không dùng cache key theo cookie.
C. Dùng Cache-Control phù hợp như private hoặc no-store cho nội dung nhạy cảm.
D. Chỉ đổi session ID mỗi request để nội dung cache tự mất hiệu lực.
Đáp án đúng: C

34. Session store chứa dữ liệu phiên nhạy cảm; nhóm vận hành cần bảo vệ cả đường truyền và quyền truy cập; lựa chọn nào phù hợp?
A. Bật TLS, xác thực, ACL tối thiểu và cô lập mạng cho session store.
B. Chỉ mã hóa cookie ở browser và mở session store trong mạng nội bộ.
C. Cho phép mọi node cùng subnet đọc toàn bộ key để tránh lỗi quyền.
D. Tắt xác thực session store nếu database đã bật mã hóa ổ đĩa.
Đáp án đúng: A

35. Một ứng dụng đa vùng địa lý cần thu hồi phiên trong vài giây; tiêu chí nào cần đánh giá khi chọn session store?
A. Dung lượng cookie tối đa và số lượng tab browser đang mở.
B. Thứ tự tải CSS, JavaScript và ảnh tĩnh trên trang đăng nhập.
C. Khả năng giữ IP người dùng cố định khi chuyển giữa các vùng.
D. Độ nhất quán, độ trễ replication và thời gian lan truyền revoke.
Đáp án đúng: D

36. Nhóm kiểm thử muốn xác minh session security toàn diện; ma trận nào có giá trị nhất?
A. Xác minh login/logout trên một browser và một node đang khỏe, không cần thêm ca khác.
B. Thử fixation, cookie flags, timeout, CSRF/XSS, revoke và failover đa node.
C. Đo thời gian tạo session khi không có request đồng thời hoặc tải nền.
D. Kiểm tra HTTPS và chứng thư còn hạn mà không thử timeout hay thu hồi.
Đáp án đúng: B

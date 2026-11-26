Bạn sẽ giải thích phiên đăng nhập duy trì trạng thái xác thực giữa nhiều HTTP request vốn độc lập như thế nào?
Bạn sẽ phân biệt xác thực danh tính, session management và authorization trong một ứng dụng web ra sao?
Bạn sẽ so sánh session lưu trạng thái phía server với mô hình token tự chứa về khả năng thu hồi, mở rộng và vận hành như thế nào?
Bạn sẽ xác định ranh giới tin cậy giữa browser, reverse proxy, ứng dụng và session store trong kiến trúc phiên ra sao?
Bạn sẽ thiết kế session identifier sao cho ngẫu nhiên, khó đoán, không chứa PII và không tiết lộ dữ liệu nghiệp vụ như thế nào?
Bạn sẽ lựa chọn độ dài và entropy của session ID dựa trên nguy cơ dò đoán, tốc độ request và thời hạn phiên ra sao?
Bạn sẽ giải thích vì sao session ID phải được coi như bearer secret và người nắm giữ nó có thể kế thừa quyền của phiên như thế nào?
Bạn sẽ lưu session state phía server theo nguyên tắc tối thiểu dữ liệu và phân tách metadata vận hành với thông tin nhạy cảm ra sao?
Bạn sẽ xác định những dữ liệu nào nên lưu trong session và dữ liệu nào nên truy vấn lại từ nguồn có thẩm quyền như thế nào?
Bạn sẽ lựa chọn cookie làm phương tiện vận chuyển session ID và giải thích vì sao không nên đưa session ID vào URL như thế nào?
Bạn sẽ thiết kế cookie session với thuộc tính Secure, HttpOnly và SameSite phù hợp theo ngữ cảnh ứng dụng ra sao?
Bạn sẽ phân biệt cookie host-only với cookie có Domain attribute và đánh giá phạm vi chia sẻ session giữa các subdomain như thế nào?
Bạn sẽ lựa chọn Path và Domain để giảm phạm vi cookie mà không tạo cảm giác bảo vệ sai về ranh giới bảo mật ra sao?
Bạn sẽ giải thích tiền tố __Host- và __Secure- áp đặt những điều kiện nào lên cookie trong trình duyệt như thế nào?
Bạn sẽ xác định khi nào dùng SameSite=Strict, Lax hoặc None dựa trên luồng điều hướng và tích hợp liên site như thế nào?
Bạn sẽ phân biệt SameSite cookie policy với CORS và giải thích vì sao CORS không thay thế cơ chế chống CSRF ra sao?
Bạn sẽ thiết kế cookie expiration và Max-Age sao cho phù hợp với chính sách hết hạn session phía server như thế nào?
Bạn sẽ đánh giá rủi ro cookie tồn tại sau khi session phía server đã hết hạn hoặc bị thu hồi ra sao?
Bạn sẽ bảo vệ session cookie qua TLS và xác định rủi ro khi TLS kết thúc tại reverse proxy hoặc load balancer như thế nào?
Bạn sẽ cấu hình trust proxy headers để ứng dụng nhận biết HTTPS đúng mà không cho client giả mạo trạng thái kết nối an toàn ra sao?
Bạn sẽ tạo session mới sau đăng nhập và tránh tái sử dụng session ẩn danh trước khi xác thực như thế nào?
Bạn sẽ giải thích session fixation xảy ra khi kẻ tấn công khiến nạn nhân tiếp tục dùng session ID mà attacker đã biết như thế nào?
Bạn sẽ ngăn session fixation bằng cách phát hành session ID mới sau đăng nhập và các lần thay đổi mức đặc quyền ra sao?
Bạn sẽ xử lý session ID do client tự cung cấp trước khi xác thực để tránh chấp nhận một giá trị đã bị cài đặt từ trước như thế nào?
Bạn sẽ xác định các sự kiện nào cần rotate session ID ngoài đăng nhập, chẳng hạn nâng quyền hoặc hoàn tất MFA như thế nào?
Bạn sẽ phân biệt session rotation với session renewal và xác định cách chuyển trạng thái an toàn giữa hai ID ra sao?
Bạn sẽ tránh session ID cũ tiếp tục được chấp nhận sau rotation bằng cách xử lý alias, grace period hoặc invalidation như thế nào?
Bạn sẽ giải thích session hijacking qua đánh cắp cookie, malware, thiết bị dùng chung hoặc kênh truyền không an toàn như thế nào?
Bạn sẽ giảm nguy cơ session hijacking bằng TLS, cookie flags, kiểm soát thiết bị và phát hiện hành vi bất thường ra sao?
Bạn sẽ đánh giá giới hạn của việc ràng buộc session với IP address hoặc User-Agent khi người dùng di chuyển mạng hay cập nhật browser như thế nào?
Bạn sẽ lựa chọn tín hiệu thiết bị và hành vi nào để phát hiện session bị chiếm đoạt mà không khóa nhầm người dùng hợp lệ ra sao?
Bạn sẽ phân biệt session ID với CSRF token và giải thích vì sao không nên dùng một giá trị cho cả hai mục đích như thế nào?
Bạn sẽ thiết kế idle timeout để phiên hết hạn sau thời gian không hoạt động theo chính sách rủi ro ra sao?
Bạn sẽ phân biệt idle timeout với absolute lifetime và giải thích vì sao hoạt động liên tục không nên kéo dài phiên vô hạn như thế nào?
Bạn sẽ triển khai sliding expiration mà vẫn bảo đảm absolute timeout và không tạo race condition khi nhiều request đồng thời ra sao?
Bạn sẽ lựa chọn timeout khác nhau cho phiên thường, phiên quản trị và phiên truy cập dữ liệu nhạy cảm như thế nào?
Bạn sẽ xử lý request đang chạy khi session hết hạn hoặc bị thu hồi giữa chừng như thế nào?
Bạn sẽ đồng bộ thời gian giữa các node để kiểm tra thời hạn session nhất quán ra sao?
Bạn sẽ thiết kế logout để vừa xóa cookie ở browser vừa vô hiệu hóa session tại server như thế nào?
Bạn sẽ phân biệt logout ở một thiết bị với logout toàn bộ thiết bị và thiết kế quản lý danh sách phiên ra sao?
Bạn sẽ thu hồi tất cả session khi người dùng đổi mật khẩu, mất thiết bị hoặc nghi ngờ tài khoản bị chiếm như thế nào?
Bạn sẽ xử lý session đã bị cache ở nhiều node để bảo đảm logout và revoke có hiệu lực trong thời gian mong muốn ra sao?
Bạn sẽ thiết kế thao tác revoke session có tính nhất quán khi nhiều request đang đồng thời sử dụng cùng một phiên như thế nào?
Bạn sẽ lựa chọn chính sách cho phép nhiều phiên đồng thời hoặc giới hạn một phiên theo tài khoản dựa trên rủi ro nào?
Bạn sẽ thông báo và cho phép người dùng xem, đặt tên hoặc thu hồi phiên trên thiết bị khác như thế nào?
Bạn sẽ yêu cầu xác thực lại trước thao tác nhạy cảm dù session hiện tại vẫn còn hiệu lực như thế nào?
Bạn sẽ thiết kế step-up authentication để nâng mức bảo đảm phiên trong một khoảng thời gian giới hạn ra sao?
Bạn sẽ xác định cách hạ mức đặc quyền hoặc rotate session sau khi quyền quản trị tạm thời kết thúc như thế nào?
Bạn sẽ giải thích CSRF khai thác việc browser tự động gửi cookie xác thực đến website đích như thế nào?
Bạn sẽ thiết kế synchronizer token pattern để server xác minh request thay đổi trạng thái đến từ luồng hợp lệ ra sao?
Bạn sẽ phân biệt synchronizer token với double-submit cookie và nêu điều kiện để double-submit an toàn như thế nào?
Bạn sẽ bảo vệ double-submit cookie trước cookie injection hoặc subdomain có thể ghi cookie cùng tên ra sao?
Bạn sẽ kết hợp SameSite, CSRF token và kiểm tra Origin hoặc Referer theo mức rủi ro của endpoint như thế nào?
Bạn sẽ sử dụng Fetch Metadata headers như Sec-Fetch-Site để bổ sung kiểm soát request cross-site ra sao?
Bạn sẽ xác định phương thức HTTP nào cần bảo vệ CSRF và vì sao GET không nên tạo thay đổi trạng thái như thế nào?
Bạn sẽ đánh giá nguy cơ CSRF trên endpoint nhận JSON, form data hoặc content type tùy biến ra sao?
Bạn sẽ giải thích preflight CORS có thể làm giảm một số request cross-origin nhưng không phải biện pháp CSRF tổng quát như thế nào?
Bạn sẽ thiết kế kiểm thử CSRF cho request chuyển tiền, thay đổi email, đổi mật khẩu và quản lý quyền ra sao?
Bạn sẽ phân tích XSS có thể thực hiện hành động dưới session của nạn nhân dù cookie được đặt HttpOnly như thế nào?
Bạn sẽ giải thích HttpOnly ngăn JavaScript đọc cookie nhưng không ngăn script độc hại gửi request cùng cookie ra sao?
Bạn sẽ kết hợp output encoding, HTML sanitization và Content Security Policy để giảm nguy cơ XSS chiếm quyền phiên như thế nào?
Bạn sẽ xác định những dữ liệu session hoặc thông tin xác thực tuyệt đối không được đưa vào DOM, local storage hay log trình duyệt ra sao?
Bạn sẽ phân biệt lưu session ID trong cookie với lưu bearer token trong localStorage về hành vi tự động gửi và bề mặt CSRF/XSS như thế nào?
Bạn sẽ thiết kế session store phân tán cho nhiều application instance mà không phụ thuộc vào sticky session như thế nào?
Bạn sẽ so sánh sticky sessions với shared session store về khả năng failover, mở rộng và thu hồi phiên ra sao?
Bạn sẽ lựa chọn Redis, database hoặc distributed cache làm session store theo yêu cầu độ bền, độ trễ và nhất quán nào?
Bạn sẽ bảo vệ session store bằng TLS, authentication, ACL, network isolation và giới hạn quyền truy cập như thế nào?
Bạn sẽ quyết định có cần mã hóa session payload khi lưu trữ và quản lý encryption key rotation ra sao?
Bạn sẽ kiểm soát TTL của session record và cookie để tránh dữ liệu phiên hết hạn vẫn tồn tại không cần thiết như thế nào?
Bạn sẽ xử lý cache eviction hoặc session store outage theo nguyên tắc fail-closed để không vô tình xác thực phiên không còn kiểm chứng được ra sao?
Bạn sẽ thiết kế replication và consistency cho session revocation để tránh node đọc bản sao cũ tiếp tục chấp nhận phiên như thế nào?
Bạn sẽ xử lý race condition khi nhiều request cùng gia hạn hoặc rotate một session trên các node khác nhau ra sao?
Bạn sẽ ngăn session fixation và replay khi session state được chia sẻ qua nhiều region hoặc availability zone như thế nào?
Bạn sẽ thiết kế session namespace theo tenant, ứng dụng và môi trường để tránh va chạm hoặc dùng nhầm phiên như thế nào?
Bạn sẽ phân biệt session của người dùng với service credential hoặc API token trong các luồng giao tiếp nền như thế nào?
Bạn sẽ xử lý WebSocket hoặc kết nối dài khi session bị logout, hết hạn hoặc thu hồi giữa thời gian kết nối ra sao?
Bạn sẽ thiết kế remember-me hoặc persistent login token để tiện sử dụng nhưng không kéo dài vô hạn quyền của session chính như thế nào?
Bạn sẽ phân biệt persistent login token với session cookie và lựa chọn cách lưu trữ, xoay vòng, thu hồi ra sao?
Bạn sẽ kiểm tra tính nguyên tử của token rotation để phát hiện việc sử dụng lại token cũ hoặc hai request đổi token đồng thời như thế nào?
Bạn sẽ xác định log và metric nào cần ghi để theo dõi tạo phiên, rotate, timeout, revoke và lỗi xác thực mà không ghi raw session ID ra sao?
Bạn sẽ thiết kế audit trail cho đăng nhập, logout, thay đổi đặc quyền và thu hồi session để phục vụ điều tra như thế nào?
Bạn sẽ phát hiện một session được dùng đồng thời từ vị trí hoặc thiết bị bất thường bằng tín hiệu nào và xử lý ra sao?
Bạn sẽ xây dựng kiểm thử session fixation, hijacking, cookie flags, timeout, logout và revoke trong nhiều browser như thế nào?
Bạn sẽ kiểm thử CSRF và XSS theo từng loại cookie, origin và luồng điều hướng thay vì chỉ kiểm tra một trang đăng nhập ra sao?
Bạn sẽ kiểm thử tính nhất quán của session trong môi trường nhiều node khi rotate, logout, failover và cache eviction như thế nào?
Bạn sẽ xây dựng quy trình ứng phó khi session cookie bị lộ gồm revoke, điều tra truy cập, thông báo và khôi phục tài khoản ra sao?
Bạn sẽ thiết kế kiến trúc session security đầu cuối cho ứng dụng web đa node gồm cookie, lifecycle, CSRF/XSS defense, distributed store, monitoring và testing như thế nào?

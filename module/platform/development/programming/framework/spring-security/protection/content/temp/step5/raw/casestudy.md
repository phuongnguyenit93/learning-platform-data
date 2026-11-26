Một ngân hàng dùng session cookie cho cổng chuyển tiền, nhưng thao tác POST chuyển khoản vẫn thực hiện được khi trình duyệt gửi yêu cầu từ trang web bên ngoài; hãy xây dựng tình huống kiểm chứng lớp bảo vệ CSRF.
Một SPA lấy CSRF token khi mở trang, sau đó người dùng đăng nhập lại trong tab khác khiến yêu cầu cập nhật hồ sơ bị trả 403; hãy đặt bài toán kiểm tra vòng đời token theo phiên.
Một API chấp nhận cả session cookie của trình duyệt và Bearer token của ứng dụng di động, nhưng nhóm phát triển muốn tắt CSRF cho toàn bộ đường dẫn; hãy xây dựng tình huống đánh giá từng cơ chế xác thực.
Một biểu mẫu thanh toán gửi POST từ website đối tác được cho phép về CORS, nhưng người dùng vẫn gặp lỗi CSRF khi thao tác; hãy yêu cầu phân tích khác biệt giữa quyền truy cập chéo nguồn và bảo vệ thay đổi trạng thái.
Một chức năng logout được triển khai qua liên kết GET trong email thông báo, khiến người dùng bị đăng xuất khi trình duyệt tự tải liên kết; hãy đặt tình huống kiểm tra hành vi logout và yêu cầu chống CSRF.
Một biểu mẫu cập nhật ảnh đại diện sử dụng multipart/form-data, nhưng khi thêm kiểm tra CSRF thì upload bị lỗi trước khi backend nhận được file; hãy xây dựng tình huống kiểm chứng luồng upload an toàn.
Một trang quản trị gửi CSRF token qua trường ẩn của form, trong khi client JavaScript lại lấy token từ cookie và đưa vào header; hãy đặt bài toán xác minh hai cách truyền có cùng chính sách.
Một endpoint tạo tài khoản cho khách chưa đăng nhập vẫn nhận dữ liệu qua form trình duyệt, và nhóm muốn miễn CSRF vì đây là chức năng công khai; hãy xây dựng tình huống đánh giá tác động của request giả mạo.
Một hệ thống có các endpoint GET, POST, PATCH và DELETE nhưng test chỉ kiểm tra CSRF cho POST; hãy xây dựng ca kiểm chứng các thao tác làm thay đổi dữ liệu ở nhiều phương thức HTTP.
Một đối tác dùng HTTP webhook ký chữ ký riêng để gửi thông báo thanh toán, nhưng endpoint webhook bị chặn bởi CSRF dùng cho trình duyệt; hãy đặt tình huống xác định phạm vi miễn trừ phù hợp.
Một yêu cầu AJAX cập nhật giỏ hàng liên tục thất bại sau khi hệ thống chuyển sang deferred CSRF token, dù HTML ban đầu vẫn hiển thị token; hãy xây dựng tình huống tìm nguyên nhân trong vòng đời token.
Một ứng dụng có hai SecurityFilterChain, một cho trang web và một cho API, nhưng đường dẫn đổi mật khẩu bị xử lý bởi chuỗi không áp dụng CSRF; hãy đặt bài toán kiểm chứng chính sách ở từng chuỗi lọc.
Một nhân viên mở hai tab chỉnh sửa cùng một hồ sơ, rồi đăng xuất và đăng nhập lại ở tab đầu tiên; hãy xây dựng tình huống kiểm thử các yêu cầu gửi từ tab còn giữ CSRF token cũ.
Một cổng đặt vé dùng CookieCsrfTokenRepository để phục vụ JavaScript, nhưng thuộc tính cookie khiến script không đọc được token và việc sửa thuộc tính lại mở rộng bề mặt tấn công; hãy đặt tình huống đánh giá tradeoff.
Một nhóm đang khắc phục lỗi CSRF token rò rỉ qua trang HTML được cache công khai tại CDN, khiến người dùng khác nhận nội dung phiên trước; hãy xây dựng tình huống kiểm tra cache và tính riêng tư của token.
Một biểu mẫu thay đổi email được cho phép qua API nội bộ lẫn giao diện web, nhưng lối gọi qua API vô tình bỏ qua kiểm tra CSRF cho session cookie; hãy đặt bài toán phát hiện khác biệt giữa hai đường gọi.
Một máy khách dùng cookie phiên để gửi POST qua proxy, nhưng proxy loại bỏ header chứa CSRF token khỏi request; hãy xây dựng tình huống chẩn đoán lỗi giữa trình duyệt, proxy và Spring Security.
Một cấu hình bỏ qua CSRF theo tiền tố đường dẫn webhook lại vô tình bao phủ cả trang quản trị có tên đường dẫn tương tự; hãy yêu cầu kiểm chứng độ chính xác của request matcher.
Một biểu mẫu đăng nhập được thiết kế cho trình duyệt nhưng không có CSRF token, khiến kẻ khác có thể thử ép nạn nhân đăng nhập vào tài khoản do họ kiểm soát; hãy đặt tình huống kiểm thử login CSRF.
Một ứng dụng triển khai luồng thay đổi địa chỉ bằng nút bấm liên tiếp, nhưng token trong form bị thay đổi giữa các bước và một số request bị từ chối; hãy xây dựng tình huống điều tra hành vi token theo phiên.
Một hệ thống hỗ trợ SockJS và gửi dữ liệu qua các request có tính thay đổi trạng thái, nhưng chính sách CSRF cho kênh tương tác không khớp cách client kết nối; hãy đặt bài toán kiểm chứng các điểm tiếp nhận.
Một API dành cho máy chủ khác xác thực bằng mTLS và không sử dụng cookie, nhưng cùng đường dẫn lại phục vụ form của trình duyệt ở môi trường cũ; hãy xây dựng tình huống đánh giá bối cảnh xác thực của request.
Một nhóm chuyển sang cấu hình CSRF cho WebFlux nhưng chỉ sao chép bài kiểm thử Servlet, khiến luồng POST qua WebFilter bị bỏ qua; hãy đặt tình huống kiểm chứng request giả mạo trên Reactive stack.
Một bài kiểm thử MockMvc cho thao tác xóa bài viết dùng tài khoản có quyền xóa nhưng thiếu CSRF token; hãy xây dựng tình huống phân biệt lỗi quyền truy cập và lỗi chống giả mạo.
Một phiên đăng nhập hợp lệ gửi request POST với CSRF token của một phiên người dùng khác, nhưng hệ thống chỉ kiểm tra token có mặt; hãy đặt tình huống xác minh tính ràng buộc giữa token và ngữ cảnh.
Một trang thay đổi mật khẩu chứa form mở từ trước khi người dùng được yêu cầu xác thực lại, dẫn tới token cũ không còn hợp lệ; hãy xây dựng tình huống kiểm tra trải nghiệm và an toàn sau xác thực lại.
Một ứng dụng sử dụng SameSite cookie và cho rằng thuộc tính này đã thay thế hoàn toàn kiểm tra CSRF, trong khi vẫn tồn tại các luồng gửi form từ những nguồn liên quan; hãy đặt bài toán đánh giá giới hạn phòng vệ.
Một dịch vụ cấp link thao tác một lần qua email nhưng endpoint tiêu thụ link thay đổi trạng thái bằng GET; hãy xây dựng tình huống phân tích nguy cơ request tự động từ trình duyệt hoặc trình quét liên kết.
Một portal React và backend Spring Boot chạy trên hai origin khác nhau, nhưng cookie đăng nhập chỉ hoạt động sau khi CORS được nới quá rộng; hãy đặt tình huống kiểm chứng cấu hình chia sẻ tài nguyên có thông tin xác thực.
Một API phản hồi Access-Control-Allow-Origin bằng dấu sao đồng thời cho phép credentials, khiến request hợp lệ từ SPA bị trình duyệt chặn; hãy xây dựng tình huống kiểm tra chính sách CORS.
Một request preflight OPTIONS tới API quản trị bị Spring Security trả 401 trước khi trình duyệt có thể gửi request thật; hãy đặt bài toán phân tích thứ tự xử lý CORS và xác thực.
Một cổng giao dịch có các origin theo tenant, nhưng API phản chiếu mọi giá trị Origin từ request thành nguồn được phép; hãy xây dựng tình huống kiểm chứng giới hạn danh sách origin tin cậy.
Một website ở subdomain do đối tác quản lý được thêm vào danh sách CORS bằng wildcard rộng, khiến nhiều subdomain không kiểm soát cũng có thể đọc dữ liệu; hãy đặt tình huống đánh giá phạm vi origin.
Một SPA gửi header Authorization và X-Request-Id, nhưng trình duyệt chỉ cho request đơn giản đi qua vì preflight không chấp nhận header mới; hãy xây dựng tình huống kiểm tra danh sách header.
Một client gọi DELETE từ origin khác nhưng preflight chỉ cho phép GET và POST, khiến tính năng hoạt động ở localhost nhưng thất bại khi triển khai; hãy yêu cầu xác minh phương thức CORS theo nghiệp vụ.
Một API phản hồi CORS đúng khi thành công nhưng thiếu các header cần thiết trên response 403, khiến nhóm frontend không đọc được thông tin lỗi; hãy đặt tình huống kiểm chứng chính sách CORS trên nhánh thất bại.
Một gateway thêm CORS header trong khi ứng dụng Spring cũng tự thêm header, tạo response có giá trị Access-Control-Allow-Origin trùng lặp; hãy xây dựng tình huống chẩn đoán lỗi trình duyệt.
Một dịch vụ dùng cache CDN cho response thay đổi theo Origin nhưng không tách biến thể cache, khiến trình duyệt nhận CORS header dành cho website khác; hãy đặt bài toán kiểm chứng tương tác giữa cache và CORS.
Một giao diện tại localhost được phép truy cập API thử nghiệm, nhưng sau khi lên production danh sách origin vẫn giữ cổng phát triển; hãy xây dựng tình huống rà soát cấu hình theo môi trường.
Một request có Origin là null từ môi trường chạy file hoặc iframe sandbox và được backend xem như origin thông thường; hãy đặt tình huống đánh giá quyết định cấp quyền truy cập chéo nguồn.
Một hệ thống đăng nhập nhiều bước dùng redirect trong quá trình gọi API xuyên origin, khiến trình duyệt báo lỗi CORS dù request trực tiếp thành công; hãy xây dựng tình huống xác định điểm phát sinh redirect.
Một đội phát triển mở CORS cho mọi origin để sửa lỗi tài nguyên tĩnh nhưng vô tình cho phép JavaScript bên ngoài đọc response API có cookie; hãy đặt bài toán kiểm chứng tác động thực tế.
Một ứng dụng React gọi API bằng credentials nhưng cookie phiên có SameSite không phù hợp, dẫn tới request vẫn không mang cookie dù preflight CORS thành công; hãy xây dựng tình huống phân biệt hai lớp bảo vệ.
Một endpoint SSE gửi dữ liệu trực tiếp tới trình duyệt từ origin khác, nhưng CORS chỉ được cấu hình cho REST controller; hãy yêu cầu kiểm chứng phạm vi các endpoint phát dữ liệu.
Một Spring WebFlux gateway cấu hình CorsWebFilter và SecurityWebFilterChain nhưng preflight đến một tuyến Reactive vẫn bị chặn; hãy xây dựng tình huống kiểm tra trình tự xử lý.
Một ứng dụng có hai cấu hình CORS độc lập tại controller và lớp bảo mật, khiến endpoint cùng nhóm trả header khác nhau; hãy đặt bài toán đánh giá chính sách hiệu lực sau khi ghép cấu hình.
Một nhà phát triển khẳng định bật CORS đã đủ để bảo vệ API khỏi người dùng không có quyền, trong khi ứng dụng native vẫn gọi endpoint được; hãy xây dựng tình huống chứng minh phạm vi của CORS.
Một cổng thanh toán chấp nhận request từ website đối tác bằng cookies và CORS, nhưng endpoint đổi thông tin ngân hàng thiếu biện pháp chống giả mạo; hãy đặt bài toán kiểm chứng đồng thời hai chính sách.
Một trang quản trị bắt đầu dùng thư viện biểu đồ tải script từ CDN, nhưng Content-Security-Policy chặn script khiến giao diện không hiển thị; hãy xây dựng tình huống đánh giá việc mở rộng nguồn thực thi.
Một đội frontend cần chạy script nội tuyến được tạo theo từng response, nhưng CSP hiện từ chối mọi inline script; hãy đặt tình huống kiểm tra cách triển khai script an toàn theo vòng đời response.
Một máy chủ tạo CSP nonce động nhưng reverse proxy cache nguyên trang HTML, khiến nonce trong tài liệu và nonce trong header không còn khớp; hãy xây dựng tình huống chẩn đoán.
Một ứng dụng dùng CSP Report-Only để thử chính sách mới và cho rằng các vi phạm đã bị chặn hoàn toàn; hãy đặt bài toán kiểm chứng sự khác nhau giữa ghi nhận và thực thi chính sách.
Một trang báo cáo nhúng iframe từ cổng nội bộ nhưng header X-Frame-Options hiện cấm mọi nhúng; hãy xây dựng tình huống đánh giá tính năng và phòng vệ clickjacking.
Một sản phẩm cho phép nhúng dashboard trên website đối tác, nhưng CSP frame-ancestors quá rộng cho phép các trang ngoài danh sách đã ký hợp đồng; hãy đặt tình huống kiểm tra ranh giới nguồn nhúng.
Một trang cấu hình tài khoản bị website tấn công đưa vào iframe trong suốt để dụ người dùng nhấp nút xóa; hãy xây dựng tình huống kiểm chứng chính sách chống clickjacking của response.
Một ứng dụng đặt đồng thời X-Frame-Options và frame-ancestors với phạm vi khác nhau, gây hành vi nhúng không thống nhất giữa các trình duyệt; hãy đặt bài toán đánh giá tính nhất quán của header.
Một nhóm muốn bật HSTS sau khi triển khai HTTPS, nhưng một số request đến Spring Boot vẫn có scheme HTTP do reverse proxy kết thúc TLS; hãy xây dựng tình huống kiểm tra header tại biên công khai.
Một tên miền dùng chung cho nhiều subdomain và một ứng dụng bật HSTS includeSubDomains, trong khi dịch vụ phụ vẫn chỉ có HTTP; hãy đặt tình huống đánh giá tác động khi triển khai.
Một ứng dụng chỉ phục vụ HTTPS ở production nhưng máy chủ vẫn trả HSTS theo thiết lập không phù hợp trên môi trường HTTP kiểm thử; hãy xây dựng tình huống xác minh hành vi ở từng môi trường.
Một quản trị viên muốn tham gia HSTS preload cho miền sản phẩm, nhưng hệ thống còn luồng chuyển hướng và subdomain chưa sẵn sàng; hãy đặt bài toán đánh giá điều kiện triển khai và khả năng hoàn tác.
Một trang chứa tài liệu bí mật trả header cache không nhất quán, khiến trình duyệt lưu dữ liệu sau khi người dùng đăng xuất; hãy xây dựng tình huống kiểm chứng chính sách cache trên response nhạy cảm.
Một endpoint tải JSON đặt Content-Type sai và thiếu X-Content-Type-Options, khiến trình duyệt xử lý tài nguyên khác với dự kiến; hãy đặt tình huống kiểm tra bảo vệ chống MIME sniffing.
Một hệ thống chia sẻ liên kết mời đăng ký có mã bí mật trong URL, nhưng Referrer-Policy mặc định làm lộ thông tin sang nguồn phân tích bên ngoài; hãy xây dựng tình huống đánh giá thông tin trong referrer.
Một trang quản trị có chức năng thu âm khi được người dùng cho phép, nhưng Permissions-Policy chặn microphone sau thay đổi cấu hình; hãy đặt tình huống kiểm chứng phạm vi quyền tính năng trình duyệt.
Một API công khai đặt CSP nhưng không áp dụng chính sách cho trang HTML lỗi do reverse proxy tạo, khiến màn hình lỗi hiển thị nội dung không mong muốn; hãy xây dựng bài toán kiểm tra response ngoài luồng chuẩn.
Một SPA tải font, ảnh và stylesheet từ các nguồn khác nhau nhưng CSP chỉ cho phép tài nguyên từ chính origin, gây lỗi từng phần khó tái hiện; hãy đặt tình huống kiểm tra những directive liên quan.
Một thư viện frontend dùng cơ chế đánh giá mã động khiến CSP nghiêm ngặt chặn một số chức năng sau bản nâng cấp, nhưng nhóm muốn thêm unsafe-eval toàn hệ thống; hãy đặt bài toán đánh giá tác động bảo mật.
Một module nhập nội dung HTML do người dùng tạo và hiển thị trên trang quản trị, trong khi đội phát triển muốn CSP là lớp bảo vệ duy nhất trước script độc hại; hãy xây dựng tình huống đánh giá giới hạn phòng vệ.
Một nhà cung cấp ảnh chuyển sang CDN mới, khiến CSP không cho tải ảnh nhưng log backend không có lỗi; hãy đặt tình huống thiết kế cách quan sát sự cố ở trình duyệt.
Một website bán hàng gửi CSP violation report tới endpoint riêng, nhưng endpoint công khai bị rate limit chung với trang đăng nhập và gây nghẽn khi có nhiều báo cáo; hãy xây dựng tình huống kiểm tra vận hành.
Một ứng dụng web được triển khai qua hai proxy, mỗi proxy thêm một bộ security headers khác nhau dẫn tới CSP xung đột khi browser áp dụng; hãy đặt bài toán xác định chính sách thực sự ở client.
Một tài nguyên tĩnh được cache trong CDN trước đợt thêm security headers, khiến người dùng nhận response mới và cũ với chính sách khác nhau; hãy xây dựng tình huống kiểm thử triển khai từng bước.
Một hệ thống cũ vẫn đặt header X-XSS-Protection trong khi chính sách CSP và cách xử lý của trình duyệt đã thay đổi; hãy đặt tình huống đánh giá tính phù hợp của bộ header hiện hành.
Một cổng truyền thông hiển thị thông tin hồ sơ trong trang được nhúng, nhưng các response redirect và response cuối có header bảo vệ không nhất quán; hãy xây dựng ca kiểm tra theo toàn bộ chuỗi điều hướng.
Một API tạo file CSV dùng Content-Disposition cho tên file nhập từ người dùng, và tên file chứa ký tự điều khiển gây lỗi header; hãy đặt tình huống kiểm tra cách phát sinh response header.
Một ứng dụng quản lý dữ liệu cấu hình header bảo vệ ở Spring Security nhưng một servlet riêng tạo file xuất không đi qua chuỗi lọc mong đợi; hãy đặt bài toán kiểm chứng độ bao phủ các kiểu response.
Một hệ thống dùng StrictHttpFirewall và bắt đầu từ chối URL chứa dấu gạch chéo được mã hóa sau khi đối tác thay đổi định dạng ID; hãy xây dựng tình huống đánh giá định tuyến và kiểm tra đầu vào.
Một dịch vụ mới cho phép dấu chấm phẩy trong đường dẫn để truyền matrix parameter, nhưng cấu hình firewall mặc định chặn request và đội phát triển muốn mở toàn cục; hãy đặt bài toán đánh giá phạm vi mở.
Một API nhận URL chứa hai dấu gạch chéo liên tiếp và trình cân bằng tải chuẩn hóa đường dẫn khác với Spring Security; hãy xây dựng tình huống kiểm chứng khả năng bỏ qua request matcher.
Một endpoint tải tài liệu chấp nhận path segment có backslash sau bước giải mã của proxy, khiến lớp bảo mật và controller nhìn thấy đường dẫn khác nhau; hãy đặt tình huống phát hiện sai lệch.
Một ứng dụng dùng cả dấu phân cách đường dẫn và đường dẫn mã hóa để xác định tài khoản, nhưng các tầng proxy, container và firewall diễn giải khác nhau; hãy xây dựng tình huống kiểm thử truy cập chéo tài khoản.
Một client cũ gửi tên HTTP method không chuẩn khiến firewall từ chối, trong khi nhóm tích hợp muốn cho mọi method để tránh lỗi; hãy đặt tình huống đánh giá tác động quyền truy cập.
Một gateway chuyển header HTTP tùy biến có ký tự xuống dòng không hợp lệ tới backend, và log hiển thị response bất thường; hãy xây dựng tình huống kiểm tra kiểm soát dữ liệu header.
Một request có nhiều tham số trùng tên được gateway xử lý theo giá trị đầu tiên, còn ứng dụng dùng giá trị cuối cùng để kiểm tra quyền; hãy đặt bài toán phân tích tính nhất quán của request.
Một endpoint bảo vệ tài nguyên theo tiền tố /admin nhưng ứng dụng nhận các biến thể mã hóa của đường dẫn từ proxy; hãy xây dựng tình huống kiểm thử matcher dưới các dạng biểu diễn URL.
Một hệ thống dùng HTTP method override do framework frontend cũ, nhưng việc chuyển POST thành DELETE làm chính sách kiểm tra method tại các tầng khác nhau; hãy đặt tình huống đánh giá luồng request.
Một nhóm bỏ qua toàn bộ firewall để cho phép ký tự đặc biệt trong URL tìm kiếm, khiến các endpoint khác chấp nhận đầu vào trước đây bị từ chối; hãy xây dựng tình huống kiểm chứng phạm vi thay đổi.
Một reverse proxy xử lý ký tự phần trăm trong đường dẫn khác với servlet container, khiến một URL bị cho phép ở gateway nhưng bị chặn ở ứng dụng; hãy đặt tình huống chẩn đoán trước khi thay đổi firewall.
Một API mới dùng path parameter chứa mã sản phẩm có ký tự đặc biệt, và nhóm dự định tắt cơ chế từ chối đường dẫn đáng ngờ thay vì đổi thiết kế URL; hãy đặt bài toán đánh giá quyết định.
Một request có chuỗi query rất dài hoặc lặp lại hàng nghìn tham số, khiến bước xử lý bảo mật tốn nhiều tài nguyên trước khi vào controller; hãy xây dựng tình huống đánh giá giới hạn đầu vào.
Một ứng dụng triển khai trên hai servlet container khác nhau và chỉ một môi trường chấp nhận đường dẫn có ký tự mã hóa bất thường; hãy đặt tình huống kiểm tra khác biệt giữa các tầng xử lý HTTP.
Một hệ thống có điểm truy cập qua gateway và điểm truy cập trực tiếp nội bộ, nhưng mỗi đường đi áp dụng chuẩn hóa URL khác nhau; hãy xây dựng tình huống đánh giá ranh giới tin cậy.
Một client gửi header Forwarded giả để đánh lừa ứng dụng về scheme và host, khiến URL chuyển hướng bảo mật được tạo với tên miền không mong đợi; hãy đặt tình huống kiểm chứng nguồn metadata của proxy.
Một ứng dụng Spring WebFlux xác thực request theo path matcher nhưng lớp gateway thay đổi path trước khi WebFilter chạy; hãy xây dựng tình huống kiểm tra khả năng khớp chính sách.
Một hệ thống vừa đăng nhập xong nhưng vẫn giữ nguyên session ID được cấp trước khi xác thực; hãy đặt tình huống kiểm chứng phòng vệ session fixation trên Servlet.
Một tài khoản quản trị mở phiên trên máy dùng chung rồi nhấn logout, nhưng session cũ vẫn có thể gọi API nhạy cảm; hãy xây dựng bài toán kiểm tra hiệu lực kết thúc phiên.
Một ứng dụng đăng nhập dùng session cookie thiếu Secure khi production chỉ truy cập qua HTTPS ở ngoài proxy, khiến cookie có thể gửi trong một số kết nối không an toàn; hãy đặt tình huống đánh giá thuộc tính cookie.
Một session cookie của cổng khách hàng thiếu HttpOnly và script chạy trong trang có thể đọc giá trị định danh phiên; hãy xây dựng tình huống kiểm chứng giới hạn truy cập cookie.
Một portal đa tên miền sử dụng cookie với Domain quá rộng, khiến các ứng dụng con không cùng mức tin cậy có thể tác động tới phiên đăng nhập; hãy đặt bài toán đánh giá phạm vi cookie.
Một khách hàng đăng nhập ở một ứng dụng rồi chuyển sang luồng thanh toán cross-site, nhưng cookie session không được gửi do SameSite khác với kỳ vọng; hãy xây dựng tình huống kiểm thử hành trình trình duyệt.
Một trình duyệt cũ và một trình duyệt mới xử lý SameSite=None khác nhau, khiến đăng nhập nhúng trong iframe lúc thành công lúc thất bại; hãy đặt tình huống xác định yêu cầu hỗ trợ.
Một hệ thống cho phép một tài khoản quản trị đăng nhập đồng thời từ nhiều thiết bị, nhưng chính sách doanh nghiệp giới hạn số phiên và chưa có ca kiểm thử; hãy xây dựng tình huống xác minh.
Một nhân viên thay mật khẩu sau khi nghi ngờ lộ tài khoản, nhưng các session trước đó vẫn có thể phê duyệt giao dịch; hãy đặt bài toán đánh giá yêu cầu thu hồi phiên theo sự kiện.
Một website chuyển từ lưu session tại bộ nhớ một node sang kho dùng chung cho nhiều replica, nhưng sau failover người dùng liên tục phải đăng nhập lại; hãy xây dựng tình huống kiểm tra tính liên tục phiên.
Một bản ghi session bị xóa do hết hạn nhưng tab trình duyệt vẫn hiển thị trang cũ và gửi yêu cầu thao tác tiếp theo; hãy đặt tình huống kiểm chứng phản hồi khi phiên hết hạn.
Một ứng dụng có hai SecurityFilterChain với chính sách tạo session khác nhau, khiến một API mong đợi stateless lại phát sinh session cookie; hãy xây dựng tình huống đánh giá đường đi thực tế.
Một client gửi Bearer token tới endpoint API nhưng ứng dụng vẫn tạo HttpSession để lưu SecurityContext, làm tăng tiêu thụ bộ nhớ theo tải; hãy đặt tình huống kiểm tra chính sách tạo phiên.
Một hệ thống hỗ trợ remember-me cho người dùng thường nhưng quản trị viên phải xác thực lại trước khi xuất dữ liệu nhạy cảm; hãy đặt tình huống kiểm tra mức độ tin cậy của phiên được khôi phục.
Một người dùng đăng nhập bằng remember-me cookie trên máy đã bị thu hồi quyền nhưng thông tin quyền cũ vẫn xuất hiện trong phiên khôi phục; hãy xây dựng tình huống đánh giá thời điểm cập nhật quyền.
Một phiên bị đánh dấu không hợp lệ sau khi đăng xuất, nhưng request tiếp theo bị chuyển vòng lặp giữa trang đăng nhập và invalid-session URL; hãy đặt tình huống chẩn đoán luồng chuyển hướng.
Một tài khoản dùng chung trong phòng hỗ trợ có nhiều tab đang thao tác khi chính sách concurrency đẩy một session khác ra ngoài; hãy xây dựng tình huống kiểm tra thông báo và trạng thái các tab.
Một ứng dụng cũ đưa session ID vào URL khi cookie bị tắt, làm định danh phiên xuất hiện trong log proxy và lịch sử trình duyệt; hãy đặt bài toán đánh giá nguy cơ từ URL rewriting.
Một dịch vụ giao dịch sử dụng session timeout tương đối ngắn nhưng nhân viên đang điền biểu mẫu dài và bị hết phiên trước khi gửi; hãy xây dựng tình huống kiểm chứng cả bảo mật lẫn xử lý dữ liệu chưa lưu.
Một ứng dụng lưu dữ liệu CSRF token trong session, nhưng hệ thống phân tán không đồng bộ bản ghi session đủ nhanh giữa các replica; hãy đặt tình huống chẩn đoán lỗi 403 ngẫu nhiên.
Một cổng quản lý cho phép nhân viên hỗ trợ giả lập phiên khách hàng theo quyền hạn, nhưng khi kết thúc chế độ hỗ trợ danh tính phiên vẫn là khách; hãy đặt tình huống kiểm tra phục hồi ngữ cảnh phiên.
Một hệ thống gán cùng tên session cookie cho hai ứng dụng chạy trên các context path chồng lấn, khiến đăng nhập ứng dụng này làm hỏng phiên ứng dụng kia; hãy đặt bài toán kiểm chứng phạm vi Path của cookie.
Một browser nhận session cookie mới sau xác thực nhưng một request AJAX đồng thời vẫn mang cookie cũ, khiến thao tác cập nhật bị từ chối không ổn định; hãy xây dựng tình huống điều tra race condition.
Một trang quản trị đã logout thành công nhưng nút Back vẫn hiện dữ liệu hồ sơ được cache và một số nút thao tác vẫn khả dụng; hãy đặt tình huống kiểm chứng giới hạn dữ liệu sau logout.
Một thiết bị dùng chung không có chức năng khóa màn hình, trong khi cổng quản lý giữ phiên đăng nhập nhiều giờ không hoạt động; hãy đặt tình huống đánh giá session timeout và hành vi đăng nhập lại.
Một ứng dụng Servlet chuyển trạng thái xác thực sau MFA nhưng không áp dụng chính sách thay đổi định danh phiên tương ứng; hãy xây dựng tình huống kiểm tra khả năng tái sử dụng phiên trước MFA.
Một frontend sử dụng fetch kèm credentials tới backend Reactive, nhưng WebSession không được khôi phục sau redirect qua gateway; hãy đặt tình huống kiểm chứng cookie và ngữ cảnh phiên WebFlux.
Một dịch vụ WebFlux dùng chuỗi SecurityWebFilterChain riêng cho REST API, nhưng đường dẫn đăng nhập được bao phủ bởi chuỗi khác với chính sách CSRF; hãy xây dựng tình huống xác minh cấu hình hiệu lực.
Một ứng dụng Reactive thực hiện logout qua request từ trình duyệt, nhưng bài test chỉ kiểm tra status 302 và chưa xác minh trạng thái WebSession sau đó; hãy đặt tình huống kiểm tra hủy phiên.
Một luồng WebFlux gửi form thay đổi hồ sơ nhưng token được lấy từ response trước đó không được chuyển đúng vào request tiếp theo; hãy xây dựng tình huống tái hiện lỗi CSRF bằng WebTestClient.
Một WebFlux gateway phục vụ nhiều ứng dụng frontend, nhưng CorsWebFilter chung cho phép origin của ứng dụng A truy cập API dành riêng cho ứng dụng B; hãy đặt tình huống đánh giá giới hạn theo route.
Một hệ thống Reactive triển khai session trên kho phân tán, nhưng khi node bị restart các request gần nhau đọc trạng thái phiên khác nhau; hãy xây dựng tình huống kiểm thử tính ổn định sau failover.
Một hệ thống có backend Servlet và gateway Reactive, nhưng mỗi lớp thêm CSP khác nhau vào cùng response khiến chỉ một số trang bị lỗi; hãy đặt bài toán kiểm chứng header xuyên các stack.
Một dự án chuyển từ Spring MVC sang WebFlux nhưng tiếp tục sử dụng bài kiểm thử MockMvc cho các luồng bảo vệ cần WebFilter; hãy xây dựng tình huống đánh giá độ bao phủ kiểm thử.
Một endpoint Reactive streaming nhận yêu cầu có cookie phiên từ trình duyệt nhưng chính sách cho phép origin không khớp origin thực tế của frontend; hãy đặt tình huống kiểm tra kết nối và header.
Một hệ thống WebFlux xử lý nhiều request song song trong cùng session, nhưng bộ test tuần tự không phát hiện lỗi lưu CSRF token hoặc trạng thái phiên; hãy xây dựng tình huống kiểm thử cạnh tranh.
Một nhóm chỉ kiểm chứng HTTP headers của response REST thành công trong Spring MVC, còn response lỗi từ endpoint Reactive lại không có header bảo vệ; hãy đặt tình huống đánh giá tính đồng nhất của chính sách.
Một cổng ứng dụng kết hợp servlet cho đăng nhập và WebFlux cho API, khiến hai hệ thống quản lý phiên có hành vi khác nhau sau logout; hãy xây dựng tình huống kiểm chứng kỳ vọng SSO và kết thúc phiên.
Một ứng dụng triển khai nhiều profile bảo mật, nhưng test CI chỉ chạy profile development với CSRF bị bỏ qua còn production có rule khác; hãy đặt bài toán thiết kế kiểm thử theo cấu hình.
Một đợt nâng cấp Spring Security thay đổi cách áp dụng request matcher và đường dẫn được phép, nhưng bộ test chỉ kiểm tra endpoint hợp lệ; hãy xây dựng tình huống kiểm thử các biến thể đường dẫn.
Một trang quản trị chạy sau CDN và WAF, trong khi kiểm thử tích hợp chỉ gọi trực tiếp embedded server nên bỏ sót header bị sửa trên đường truyền; hãy đặt tình huống đánh giá phạm vi kiểm thử.
Một sản phẩm cần kiểm chứng toàn bộ POST quản trị bị từ chối khi không có CSRF token, nhưng nhóm chỉ chạy một trường hợp trên endpoint đơn giản; hãy xây dựng tình huống tổ chức ca âm tính theo nghiệp vụ.
Một tổ chức mở thêm tên miền frontend cho đối tác, nhưng chưa cập nhật ma trận origin được phép và cookie cho từng môi trường; hãy đặt tình huống kiểm tra trước khi phát hành.
Một đội frontend báo lỗi CORS sau khi bật CSP mới, trong khi cùng thời điểm proxy thay đổi cookie attribute; hãy xây dựng tình huống thu thập bằng chứng để phân biệt nguyên nhân.
Một pipeline chỉ xác nhận security headers xuất hiện, không đối chiếu giá trị header với chính sách bảo mật đã phê duyệt; hãy đặt tình huống xây dựng tiêu chí QA cho các giá trị thực tế.
Một thay đổi cho phép URL mã hóa để hỗ trợ tìm kiếm được merge mà không chạy test firewall cho endpoint quản trị; hãy xây dựng tình huống xác định phạm vi kiểm thử hồi quy.
Một ứng dụng có các trang web đăng nhập bằng session và API stateless, nhưng ma trận kiểm thử bảo mật không phân biệt hai loại request; hãy đặt tình huống xây dựng tiêu chí chấp nhận cho CSRF và session.
Một hệ thống thử nghiệm không dùng HTTPS nên bài test HSTS luôn thiếu header, trong khi production sau proxy lại báo an toàn; hãy xây dựng tình huống xác minh bằng chứng theo scheme công khai.
Một ứng dụng từ chối request nghi ngờ ở HTTP firewall nhưng dashboard chỉ ghi lỗi 404 chung, khiến đội vận hành không phân biệt được truy cập lỗi và nỗ lực vượt matcher; hãy đặt tình huống quan sát sự cố.
Một đợt triển khai CSP nghiêm ngặt làm tính năng in hóa đơn không chạy ở một nhóm trình duyệt, còn test backend vẫn xanh; hãy đặt tình huống bổ sung kiểm chứng tại trình duyệt thật.
Một service sử dụng cấu hình bảo vệ chung nhưng endpoint tài nguyên tĩnh được chuyển sang máy chủ khác không có cùng security headers; hãy xây dựng tình huống kiểm tra bề mặt công khai sau khi tách hệ thống.
Một bản phát hành cập nhật chính sách cookie và session trên hai miền, nhưng quá trình rollout từng phần khiến người dùng bị logout khi chuyển qua lại giữa phiên bản; hãy đặt tình huống kiểm tra tương thích triển khai.
Một nhóm kiểm toán yêu cầu chứng minh CSRF, CORS, CSP, HSTS, firewall và session protection đều có ca kiểm thử âm tính phù hợp với từng loại ứng dụng; hãy xây dựng tình huống lập tiêu chí đánh giá độ bao phủ.

Một API tra cứu hồ sơ nhận đường dẫn chứa tên người dùng tiếng Việt có dấu; trên trình duyệt request thành công nhưng từ một HTTP client tự ghép URI lại nhận 404 do cách mã hóa percent-encoding khác nhau.
Ứng dụng lưu mã sản phẩm chứa dấu gạch chéo bên trong một đoạn path; khi đi qua reverse proxy, một số URI đã mã hóa dấu gạch chéo bị giải mã thành nhiều đoạn và chuyển đến Route khác.
Client gửi tham số truy vấn có dấu cộng trong mã khuyến mãi; backend diễn giải dấu cộng thành khoảng trắng nên mã không khớp dù chuỗi hiển thị trên màn hình người dùng giống dữ liệu gốc.
Một endpoint tìm kiếm nhận nhiều tham số tag cùng tên trong query string; sau khi nâng cấp thư viện HTTP, ứng dụng chỉ nhận giá trị cuối và kết quả lọc thiếu các thẻ đã chọn.
Nhóm gắn mã truy cập tạm thời vào query string của URL tải hóa đơn; khi người dùng bấm liên kết, mã xuất hiện trong lịch sử trình duyệt, log reverse proxy và một số bản ghi truy cập.
Người dùng gửi liên kết có fragment để mở một mục trong tài liệu; backend báo không nhận được giá trị nằm sau dấu thăng trong URL, còn trình duyệt vẫn cuộn đúng mục trên trang.
Hệ thống có API GET tra cứu đơn hàng nhưng mã backend đồng thời cập nhật số lần sử dụng voucher; sau khi bật crawler và bộ tối ưu tải trang, số lượt sử dụng voucher tăng dù khách hàng không thao tác thanh toán.
Frontend dùng HEAD để kiểm tra một file tồn tại trước khi tải; endpoint chỉ cài đặt GET và gateway trả 405, khiến UI báo file không có dù GET trực tiếp vẫn thành công.
Một client tự động thử lại POST tạo đơn hàng khi mất kết nối trước lúc nhận phản hồi; sau đợt mạng chập chờn, hệ thống có hai đơn trùng dù khách hàng chỉ bấm đặt hàng một lần.
Ứng dụng cập nhật toàn bộ thông tin người dùng bằng PUT nhưng request chỉ gửi các trường vừa sửa; backend thay thế cả tài nguyên và những trường không gửi bị mất sau mỗi lần cập nhật.
Hai thiết bị cùng đọc phiên bản hồ sơ rồi gửi PATCH thay đổi các trường khác nhau; vì endpoint ghi toàn bộ đối tượng từ trạng thái cũ, một thay đổi hợp lệ bị ghi đè sau khi cả hai request đều trả 200.
Dịch vụ xóa bản ghi bằng DELETE và trả 500 vì ghi audit thất bại sau khi dữ liệu đã bị xóa; client retry cùng URI và nhận 404, còn hệ thống theo dõi lại đánh dấu lần xóa thứ hai là một lỗi mới.
Trình duyệt gửi OPTIONS trước POST có header Authorization nhưng API chỉ xử lý GET và POST; trong công cụ kiểm thử POST hoạt động còn từ giao diện web request nghiệp vụ không bao giờ được gửi.
Máy chủ trả 201 cho yêu cầu tạo tài nguyên nhưng không gửi Location; client tạo thành công một báo cáo mà không biết URI nào để truy cập kết quả vừa tạo.
API xử lý yêu cầu xuất dữ liệu trong hàng chục giây và trả 202 ngay lập tức; frontend coi phản hồi đó là tệp đã sẵn sàng nên hiển thị nút tải về trước khi job hoàn tất.
Một endpoint cập nhật cấu hình trả 204 nhưng vẫn gửi body JSON mô tả kết quả; client HTTP và reverse proxy xử lý không nhất quán khiến một số màn hình chờ nội dung không bao giờ được đọc.
Dịch vụ tải video hỗ trợ Range nhưng trả 200 cùng toàn bộ file cho mọi yêu cầu lấy một đoạn; người dùng kéo thanh thời gian đến cuối video phải chờ tải lại lượng dữ liệu lớn.
Ứng dụng dùng status 200 cho cả kết quả lỗi xác thực và đóng gói lỗi vào JSON; hệ thống giám sát theo HTTP status báo gần như không có lỗi trong khi nhiều người dùng không thể truy cập.
API xác thực trả 403 cho request chưa có thông tin đăng nhập, còn client chỉ kích hoạt luồng đăng nhập lại khi thấy 401; người dùng bị kẹt ở màn hình lỗi dù phiên đã hết hạn.
Một API nhận dữ liệu JSON thiếu trường bắt buộc nhưng trả 500 thay vì phản hồi lỗi phía client; dashboard ghi nhận sự cố máy chủ tăng đúng khi ứng dụng di động bản cũ gửi payload không hợp lệ.
Trình duyệt gửi Content-Type là text/plain tới endpoint chỉ nhận application/json; backend báo 415, trong khi cùng nội dung được gửi bằng công cụ REST với media type đúng lại thành công.
Client gửi Accept chỉ cho phép application/xml tới endpoint chỉ xuất JSON; ứng dụng bỏ qua thương lượng nội dung nên phản hồi nhận được không đúng định dạng mà client có thể đọc.
Người dùng sửa thông tin sản phẩm theo phiên bản cũ nhưng API trả 200 và ghi đè bản mới; hệ thống không phân biệt xung đột thay đổi đồng thời với cập nhật hợp lệ.
Một endpoint tìm tài liệu trả 404 cả khi chưa từng có tài liệu và khi tài liệu đã bị gỡ vĩnh viễn; hệ thống thu thập dữ liệu tiếp tục yêu cầu các URI bị xóa qua nhiều tuần.
API trả 429 khi vượt giới hạn nhưng không cung cấp thời điểm có thể thử lại; SDK thực hiện retry ngay và khiến lưu lượng yêu cầu trong đợt nghẽn tăng mạnh.
Một backend đang bảo trì trả 503 có Retry-After nhưng client coi đó là lỗi vĩnh viễn và dừng tất cả công việc; ở hệ thống khác, client lại bỏ qua Retry-After và tiếp tục gửi với tốc độ cũ.
Gateway trả 502 khi không thể kết nối tới upstream, nhưng đội trực chỉ nhìn mã 5xx chung và nhầm lỗi kết nối với 500 phát sinh trong mã nghiệp vụ.
API tạo báo cáo thực thi 40 giây trong khi gateway chờ tối đa 10 giây và trả 504; log backend vẫn báo công việc hoàn tất, còn client không biết có cần tạo lại báo cáo hay không.
Ứng dụng đưa quá nhiều thông tin vào cookie và token, khiến các request tiếp theo gửi header Cookie và Authorization lớn hơn giới hạn của proxy; một số request nhận 431 trước khi đến backend.
Ứng dụng gửi biểu mẫu có ảnh nhúng thành body lớn và nhận 413 từ gateway; backend không ghi nhận request nên nhóm phát triển tìm lỗi trong xử lý upload mà không thấy dấu vết.
Backend kiểm tra mã lỗi từ dịch vụ khác rồi luôn trả 500; khi upstream trả 404 có ý nghĩa nghiệp vụ, API bên ngoài vẫn báo sự cố hệ thống khiến client retry một tài nguyên không tồn tại.
Khách hàng gọi cùng API qua api.example.test và địa chỉ IP của máy chủ; tên miền trả đúng nội dung nhưng khi gọi IP với Host khác, reverse proxy phục vụ virtual host mặc định.
Một HTTP client gửi JSON có Unicode nhưng khai báo sai charset và thư viện backend giải mã theo bộ ký tự khác; chỉ tên khách hàng chứa ký tự đặc biệt bị lỗi dữ liệu.
Máy chủ nhận body JSON với Content-Type hợp lệ nhưng Content-Length khai báo nhỏ hơn số byte thực gửi; một số proxy đóng kết nối còn backend ghi nhận payload bị cắt.
Thiết bị cũ gửi request HTTP/1.1 có cả Content-Length và Transfer-Encoding theo cách mâu thuẫn; hai thành phần trung gian xác định ranh giới request khác nhau và log cho thấy request kế tiếp bị xử lý sai.
Ứng dụng tải dữ liệu qua transfer encoding chunked, nhưng client tự viết giả định luôn có Content-Length nên chờ đến timeout dù response body đã được nhận đầy đủ.
API phản hồi JSON nén bằng gzip nhưng quên Content-Encoding; browser cố đọc byte nén như văn bản và báo lỗi parse dù status là 200.
Client gửi Accept-Encoding chỉ cho phép một số thuật toán nén, còn CDN trả brotli cho một client không hỗ trợ; người dùng nhận nội dung không thể giải mã trên thiết bị cũ.
Dịch vụ được tối ưu bằng nén gzip cho tệp JSON nhỏ dưới 200 byte; sau phát hành, độ trễ và CPU tăng nhẹ vì chi phí nén lớn hơn lợi ích băng thông của các payload rất nhỏ.
API trả Content-Disposition với tên tệp tiếng Việt được mã hóa không nhất quán; các trình duyệt khác nhau tải cùng báo cáo nhưng hiển thị tên tệp sai dấu hoặc bị cắt.
Hệ thống sử dụng Content-Language và Accept-Language để trả thông báo lỗi theo ngôn ngữ; CDN chỉ cache theo URL nên một số khách nhận thông báo bằng ngôn ngữ của khách trước đó.
API giá sản phẩm trả Cache-Control public với dữ liệu phụ thuộc quyền chiết khấu của từng khách; sau khi CDN lưu response, khách sau nhìn thấy giá dành cho tài khoản khác.
Trang tài khoản trả Cache-Control no-cache nhưng có nội dung cá nhân; một nhóm phát triển hiểu nhầm chỉ thị này có nghĩa tuyệt đối không lưu response nên không kiểm tra cơ chế revalidation của cache trung gian.
Một API cung cấp thông tin nhạy cảm và đặt max-age rất ngắn nhưng không có no-store; sau khi người dùng đăng xuất, nội dung vẫn có thể được tìm thấy trong bộ nhớ đệm trình duyệt.
Backend cập nhật giá sản phẩm nhưng CDN vẫn phục vụ bản cũ do response đặt max-age một giờ; nhóm chăm sóc khách hàng thấy kết quả gọi trực tiếp origin đúng còn URL công khai vẫn sai.
Endpoint danh mục trả ETag và xử lý If-None-Match; sau khi đổi dữ liệu ở backend, client tiếp tục nhận 304 vì bộ tạo ETag không phản ánh nội dung hiện tại.
Trình duyệt gửi If-Modified-Since dựa trên Last-Modified của tài liệu; hai cập nhật sát nhau trong cùng một giây khiến bộ kiểm tra thời điểm sửa không phân biệt được phiên bản mới.
Client chỉnh sửa tài nguyên và gửi If-Match với ETag đọc trước đó; giữa hai request có người khác cập nhật cùng tài nguyên, API trả 412 nhưng frontend lại hiển thị lỗi mất kết nối thay vì xung đột phiên bản.
API chỉ phục vụ tệp thay đổi khi client không có bản mới nhất, nhưng khi nhận If-None-Match lại trả 200 với toàn bộ payload; tổng băng thông tăng dù phần lớn client đã cache đúng phiên bản.
CDN lưu hai bản HTML có nội dung khác nhau tùy Accept-Encoding nhưng response không có Vary phù hợp; một nhóm client nhận representation nén không tương ứng với yêu cầu của họ.
Ứng dụng thêm query parameter theo dõi chiến dịch vào URL ảnh tĩnh; cache phân biệt từng URI nên tỷ lệ cache hit giảm mạnh dù byte ảnh phục vụ cho mọi chiến dịch giống hệt nhau.
Một API báo cáo cho phép cache dùng stale-while-revalidate để giảm độ trễ; trong đợt cao điểm, một nhóm khách thấy dữ liệu cũ hơn SLA mà dashboard chỉ ghi thời gian phản hồi nhanh.
Trình duyệt nhận Set-Cookie với Path chỉ là /account; khi người dùng gọi API /checkout, cookie phiên không được gửi dù cả hai endpoint dùng cùng host.
Một ứng dụng chuyển từ sub.example.test sang api.example.test; cookie host-only của phiên đăng nhập không được trình duyệt gửi sang host mới và người dùng liên tục bị đăng xuất.
Ứng dụng web chạy HTTPS nhưng cookie phiên thiếu thuộc tính Secure; khi một liên kết HTTP vẫn truy cập được trên cùng host, nhóm bảo mật phát hiện cookie có thể được gửi qua kết nối không mã hóa.
Một cookie đăng nhập không có HttpOnly và giao diện có lỗi script injection; sau sự cố, nhóm phát hiện mã chạy trong browser có thể đọc giá trị phiên từ cookie.
Frontend ở domain khác gọi API bằng fetch có credentials, nhưng cookie SameSite=Lax được cấu hình cho trường hợp yêu cầu cross-site; API luôn phản hồi như người dùng chưa đăng nhập trên trình duyệt.
Một ứng dụng thanh toán nhúng trong iframe của đối tác và dựa vào cookie bên thứ ba; sau cập nhật quyền riêng tư của trình duyệt, luồng xác thực thất bại ở một số thiết bị dù gọi trực tiếp vẫn thành công.
Ứng dụng nhận POST từ một trang ngoài với cookie đăng nhập hợp lệ và cập nhật địa chỉ nhận hàng; backend chỉ dựa vào cookie để xác thực và nhóm phát hiện các yêu cầu thay đổi có thể bị kích hoạt ngoài ý muốn.
Cookie phiên có thời hạn phía server là 15 phút nhưng Max-Age trong Set-Cookie là 24 giờ; khi người dùng quay lại sau một giờ, browser vẫn gửi cookie nhưng server trả 401.
Ứng dụng đặt nhiều cookie chứa dữ liệu giao diện khiến header Cookie vượt giới hạn của proxy; request đầu phiên hoạt động nhưng sau vài lần chuyển trang bắt đầu bị từ chối trước khi vào backend.
API nhận Authorization Bearer token nhưng frontend gửi token đồng thời trong query string để tiện debug; reverse proxy và dịch vụ analytics lưu lại URI chứa credential qua các lần thử nghiệm.
Một client dùng Basic Authentication qua HTTP không mã hóa trên mạng nội bộ; sau khi chuyển qua đường truyền không tin cậy, đội bảo mật phát hiện thông tin đăng nhập được gửi trong mỗi request.
API yêu cầu JWT với phạm vi read:orders nhưng nhận token chỉ có write:orders; hệ thống phân biệt được người dùng đã xác thực nhưng không đủ quyền, trong khi frontend lại hiện hộp thoại đăng nhập liên tục.
Browser gọi API từ origin khác với cookie phiên và server phản hồi Access-Control-Allow-Origin bằng dấu sao cùng Allow-Credentials true; request được backend xử lý nhưng JavaScript không đọc được phản hồi.
Frontend gửi custom header X-Trace-Id và Authorization nhưng preflight chỉ được server cho phép Content-Type; request từ browser thất bại với lỗi CORS còn công cụ dòng lệnh gửi cùng request vẫn thành công.
API phản hồi Access-Control-Allow-Origin bằng cách phản chiếu mọi Origin nhận được và cho phép credentials; một trang web bên thứ ba có thể đọc phản hồi cá nhân khi người dùng đang có phiên hợp lệ.
Frontend đổi từ GET đơn giản sang POST với Content-Type application/json; sau thay đổi, browser thực hiện preflight và chỉ môi trường production lỗi vì cache hoặc proxy không xử lý OPTIONS tương ứng.
Backend chỉ ghi log request POST nhưng CORS preflight bị lỗi ở gateway; đội hỗ trợ không tìm thấy request nghiệp vụ trong log và tưởng client chưa gửi yêu cầu.
Một API trả 302 chuyển người dùng từ form POST sang URL khác; các HTTP client thay đổi phương thức khi đi theo redirect khác nhau và thao tác ghi ở đích có kết quả không đồng nhất.
Ứng dụng di chuyển endpoint upload sang miền mới và trả 307, nhưng client cũ không tự gửi lại body khi theo redirect; chỉ request upload bị lỗi còn GET tiếp tục hoạt động.
Sau khi đổi URI của endpoint gửi biểu mẫu, API trả 308 để giữ nguyên phương thức và body khi chuyển hướng; một nhóm client HTTP cũ không tự theo redirect cho POST nên yêu cầu chỉ thành công trên các client mới.
Máy chủ đưa HSTS vào response HTTPS nhưng người dùng truy cập lần đầu bằng URL HTTP vẫn có nguy cơ đi qua redirect trước khi biết chính sách; nhóm bảo mật cần đánh giá hành vi kết nối ban đầu.
CDN kết thúc TLS phía ngoài còn kết nối tới origin dùng HTTP; trang web báo biểu tượng HTTPS nhưng thông tin đăng nhập đi qua chặng nội bộ không mã hóa và tiêu chuẩn nội bộ yêu cầu kiểm tra lại đường truyền.
Một tên miền API có nhiều backend sau reverse proxy; khi cấp chứng chỉ mới, trình duyệt báo tên chứng chỉ không khớp cho một số request do cấu hình SNI tại một tầng proxy không đúng.
Một ứng dụng chạy tốt khi gọi HTTPS bằng tên miền nhưng lỗi xác thực chứng chỉ khi truy cập qua địa chỉ IP; URI gọi từ batch job bỏ qua tên máy chủ mà chứng chỉ TLS được cấp.
Người dùng ở mạng doanh nghiệp nhìn thấy lỗi TLS sau khi máy chủ ngừng hỗ trợ phiên bản giao thức cũ; truy cập từ thiết bị hiện đại vẫn thành công và đội hỗ trợ cần phân biệt lỗi bắt tay với mã trạng thái HTTP.
Ứng dụng HTTPS nạp script và ảnh từ URL HTTP; browser chặn một số tài nguyên dạng active mixed content nên trang bị lỗi chức năng dù HTML trả status 200.
Reverse proxy đặt X-Forwarded-Proto từ phía client mà không giới hạn proxy tin cậy; ứng dụng tạo redirect và cookie Secure dựa vào giá trị này, dẫn tới các response khác thường cho request bị giả mạo header.
Một dịch vụ cần biết IP thật của client nhưng proxy trung gian chuyển tiếp chuỗi X-Forwarded-For nhiều địa chỉ; hệ thống giới hạn truy cập dựa vào địa chỉ đầu tiên mà không phân biệt phần nào do client tự gửi.
Ứng dụng sử dụng HTTP/1.1 keep-alive nhưng mở một kết nối mới cho mỗi ảnh nhỏ; khi trang chứa hàng trăm tài nguyên, thời gian thiết lập TCP và TLS chiếm phần lớn thời gian tải.
Một client HTTP/1.1 tải tuần tự nhiều đối tượng trên cùng kết nối, trong đó một response lớn đang được truyền; các response nhỏ phía sau phải chờ, khiến waterfall có độ trễ dài dù backend trả kết quả nhanh.
Nhóm chuyển API sang HTTP/2 để multiplex các request trên một kết nối nhưng khi có mất gói TCP, nhiều stream cùng chậm đồng thời; biểu đồ cho thấy thời gian xử lý server không thay đổi.
API streaming qua HTTP/2 bị ngừng khi client không đọc dữ liệu đủ nhanh; cửa sổ flow control còn khả dụng giảm về 0 và server phải chờ trước khi gửi thêm DATA dù kết nối TCP chưa đứt.
Trình duyệt tái sử dụng một kết nối HTTP/2 lâu dài nhưng server gửi GOAWAY trong lúc deploy; một nhóm request mới bị lỗi do thư viện client không xử lý việc chuyển sang kết nối khác đúng cách.
Một HTTP proxy cũ đứng giữa client HTTP/2 và backend chỉ hỗ trợ HTTP/1.1; sau khi triển khai, một số header và cơ chế stream hoạt động khác so với truy cập trực tiếp, khiến truy vấn dài bị hủy bất thường.
Dịch vụ gRPC được gọi qua HTTP/2 nhưng gateway trung gian chỉ chuyển tiếp như request HTTP/1.1; client nhận lỗi giao thức trước khi thông điệp RPC được backend xử lý.
Một thiết bị IoT dùng HTTP/1.1 trong khi server phát hành tính năng chỉ được kiểm thử trên HTTP/2; sau khi phát hành, request trên thiết bị cũ gặp lỗi do server phụ thuộc ngầm vào một header không phù hợp.
Website bật HTTP/3 nhưng mạng doanh nghiệp chặn UDP 443; trình duyệt chuyển sang HTTP/2 sau một khoảng trễ, còn hệ thống chỉ ghi nhận giao thức cuối cùng nên khó xác định nguyên nhân tải trang chậm.
Người dùng chuyển từ Wi-Fi sang mạng di động khi tải nội dung qua HTTP/3; phiên truyền có thể tiếp tục với connection ID của QUIC, nhưng ứng dụng giám sát dựa trên cặp IP và cổng coi đó là một phiên mới.
Một dịch vụ phát hành khả năng HTTP/3 qua Alt-Svc nhưng CDN ở một vùng chưa hỗ trợ UDP; client nhận thông tin thay thế từ response trước rồi liên tục thử kết nối không thành công trước khi quay lại HTTP/2.
API gửi lệnh thay đổi số dư bằng request có thể được phát lại trong giai đoạn TLS 0-RTT của HTTP/3; khi có request lặp ở tầng transport, ứng dụng thiếu cơ chế nhận diện lệnh nghiệp vụ đã xử lý.
Nhóm tối ưu tốc độ chỉ đo protocol HTTP/3 trên mạng ổn định; khi mô phỏng mất gói và RTT cao, p99 của một số endpoint khác HTTP/2 nhưng dashboard hiện chưa chia số liệu theo giao thức và điều kiện mạng.
Ứng dụng gửi request có X-Request-ID qua CDN, gateway và backend, nhưng mỗi tầng tự thay header bằng giá trị mới; khi khách báo lỗi 504, đội hỗ trợ không liên kết được request/response giữa các lớp.
Chỉ số client hiển thị request mất tám giây trong khi backend log xử lý 80 ms; phân tích HTTP timing cho thấy phần chờ DNS, TCP/TLS, TTFB và truyền body chưa được đo riêng.
Một SDK tự động retry mọi mã 5xx cho cả GET tra cứu và POST tạo giao dịch; khi gateway trả 503 sau khi backend đã nhận thao tác, số lượng giao dịch trùng tăng trong đợt gián đoạn.
Hệ thống ghi log body request và response để gỡ lỗi HTTP, bao gồm cookie phiên và Authorization; bản ghi phân tích được chia sẻ giữa nhiều nhóm và quá trình điều tra phải xem xét nguy cơ lộ thông tin xác thực.

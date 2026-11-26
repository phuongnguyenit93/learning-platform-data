Một hệ thống triển khai HAProxy trên cổng 80 và 443 để chuyển toàn bộ HTTP sang HTTPS; sau khi thêm một reverse proxy phía trước, trình duyệt liên tục nhận redirect dù URL ban đầu đã là HTTPS.
HAProxy được cấu hình một frontend nhận request trên cổng 443 nhưng một tiến trình cũ vẫn giữ cổng này; dịch vụ không khởi động được sau khi bảo trì dù tệp cấu hình vượt qua kiểm tra cú pháp.
Ứng dụng TCP thuần được đưa vào frontend chạy mode http; các client mở kết nối thành công nhưng dữ liệu nhị phân đầu tiên bị xử lý như HTTP request và phiên giao tiếp bị ngắt.
Một frontend phục vụ nhiều API có default_backend trỏ tới trang giới thiệu; request cho host mới chưa có ACL phù hợp được trả HTML 200 thay vì phản hồi JSON của dịch vụ mong đợi.
ACL định tuyến cho api.example.test chỉ so khớp giá trị Host không chứa cổng; một số client gửi Host kèm :443 nên được chuyển sang backend mặc định mặc dù tên miền đúng.
Frontend có quy tắc use_backend cho /api và /api/admin nhưng quy tắc tổng quát được đánh giá trước; một số lệnh quản trị đi vào backend công khai thay vì backend yêu cầu xác thực nội bộ.
HAProxy dùng ACL đường dẫn phân biệt chữ hoa chữ thường cho /Reports; người dùng gọi /reports từ ứng dụng di động nhận 404 trong khi request thử nghiệm với chữ hoa hoạt động.
Nhóm thay đổi đường dẫn /v1/orders thành /orders ở backend nhưng không cập nhật quy tắc http-request set-path tại HAProxy; một số endpoint trả 404 dù health check của backend vẫn thành công.
Đội triển khai dùng file map để chọn backend theo hostname; sau khi thêm khách hàng mới, thay đổi chỉ xuất hiện trên một node HAProxy vì các node đang dùng hai phiên bản file map khác nhau.
Backend dựa vào header Host để chọn tenant nhưng HAProxy ghi đè Host thành tên máy nội bộ; yêu cầu đi đúng địa chỉ IP backend vẫn hiển thị dữ liệu tenant mặc định.
Gateway đặt HTTP method ACL để chặn DELETE trên API công khai nhưng một số client gửi phương thức không nằm trong quy tắc dự kiến; log cho thấy backend nhận request nguy hiểm qua một frontend dự phòng.
Dịch vụ kết nối database dùng HAProxy TCP passthrough nhưng nhóm lại đặt quy tắc đọc HTTP header để phân tuyến; kết quả chọn backend không phù hợp vì dữ liệu trên kết nối không có định dạng HTTP.
HAProxy định tuyến TLS passthrough theo SNI từ ClientHello nhưng không chờ đủ dữ liệu khi thực hiện TCP content inspection; một số kết nối bị chuyển về backend mặc định chỉ khi mạng có độ trễ.
Ứng dụng dùng nhiều hostname trên cùng cổng TLS của HAProxy; sau khi thay bộ chứng chỉ, các trình duyệt truy cập một subdomain nhận chứng chỉ dành cho miền khác trong khi các miền còn lại bình thường.
File chứng chỉ TLS được cài vào node HAProxy mới chỉ chứa leaf certificate mà thiếu intermediate chain; thiết bị di động cũ báo lỗi xác thực còn một số trình duyệt máy tính vẫn truy cập được.
Đội vận hành bật HTTP/2 qua ALPN trên frontend TLS nhưng một lớp proxy trung gian ở phía sau vẫn chỉ hỗ trợ HTTP/1.1; sau triển khai, các request streaming và header dài có biểu hiện khác thường.
Một frontend yêu cầu xác thực chứng chỉ client để truy cập API đối tác; một đối tác thay chứng chỉ mTLS và bị từ chối ngay trong TLS handshake dù chứng chỉ server của HAProxy vẫn hợp lệ.
HAProxy kết thúc TLS ở biên rồi chuyển request HTTP không mã hóa tới backend đặt ở mạng riêng; sau khi luồng xử lý chuyển qua mạng liên vùng, bộ phận bảo mật phát hiện chặng nội bộ không còn đáp ứng yêu cầu mã hóa.
HAProxy mở kết nối HTTPS tới backend nhưng đặt tên SNI không khớp hostname trên chứng chỉ máy chủ; API qua proxy báo lỗi TLS trong khi curl gọi backend bằng tên DNS thật thành công.
Một đội nâng cấp chính sách TLS để loại bỏ cipher cũ; một nhóm máy quét kho chỉ hỗ trợ bộ thuật toán lỗi thời không thể kết nối, còn trình duyệt mới truy cập bình thường.
Sau khi bật TLS termination trên HAProxy, CPU của hai node biên tăng mạnh khi có nhiều kết nối mới mỗi giây; thời gian xử lý backend vẫn thấp nhưng người dùng thấy TTFB tăng.
Ứng dụng sử dụng cookie Secure để lưu phiên, nhưng backend chỉ nhìn thấy HTTP từ HAProxy và sinh URL chuyển hướng trở lại http; người dùng bị đưa qua lại giữa hai giao thức khi đăng nhập.
HAProxy dùng TCP health check chỉ xác nhận cổng backend còn mở; dịch vụ ứng dụng đã mất kết nối tới database và trả 500, nhưng Target vẫn được xem là khỏe mạnh.
Backend có endpoint /health trả 200 nhưng yêu cầu thực tế cần truy cập hệ thống thanh toán; một pod mất kết nối tới dịch vụ thanh toán vẫn được cân bằng tải như những pod khỏe mạnh khác.
HTTP health check của HAProxy gọi /health bằng Host mặc định, trong khi backend dùng virtual host và yêu cầu Host cụ thể; tất cả server bị đánh dấu DOWN mặc dù gọi trực tiếp bằng hostname đúng vẫn trả 200.
Một API đổi endpoint kiểm tra sức khỏe từ /ready sang /healthz; sau deploy, HAProxy vẫn gọi /ready và đánh dấu toàn bộ backend DOWN dù dịch vụ chính vẫn nghe trên cổng cũ.
Health check phản hồi 302 tới trang đăng nhập vì middleware xác thực áp dụng lên /health; HAProxy dùng điều kiện thành công chỉ chấp nhận 200 nên loại bỏ những máy thực tế vẫn xử lý request được.
Một backend có thời gian khởi động kéo dài 40 giây và health check bắt đầu quá sớm; trong rolling deployment, server bị chuyển UP/DOWN liên tục khiến người dùng gặp lỗi ngắt quãng.
Hai máy backend ở xa có RTT biến động, còn timeout kiểm tra sức khỏe đặt bằng giá trị dùng trong cùng rack; một máy thường bị đánh dấu lỗi dưới tải dù endpoint vẫn trả kết quả sau đó.
Đội vận hành đổi ngưỡng rise và fall để phát hiện lỗi nhanh hơn; khi backend có vài lần timeout ngắn, trạng thái của nhiều server dao động liên tục và số lần chuyển kết nối tăng đột biến.
HAProxy nhận tín hiệu health check TCP thành công nhưng ứng dụng vừa đóng chế độ tiếp nhận nghiệp vụ khi chuẩn bị bảo trì; request mới vẫn đi vào máy sẽ shutdown và có lúc bị mất giữa chừng.
Nhóm cho server rời khỏi backend bằng trạng thái drain khi triển khai phiên bản mới; các kết nối giữ phiên dài chưa kết thúc nên quá trình thu hồi máy vượt cửa sổ triển khai.
Một backend xử lý upload kéo dài hàng phút được cân bằng bằng roundrobin cùng các API ngắn; hai server bị chiếm bởi nhiều upload còn server khác rảnh, dẫn đến phân bố kết nối đang hoạt động rất không đều.
Đội đổi thuật toán từ roundrobin sang leastconn để phục vụ request thời gian dài; sau phát hành, thời gian phản hồi thay đổi theo loại request và nhóm chưa kiểm tra mối quan hệ giữa số connection với chi phí CPU mỗi request.
HAProxy cân bằng tải dựa trên địa chỉ IP nguồn nhưng phần lớn client truy cập qua một NAT của nhà mạng; một máy backend nhận quá nhiều phiên dù tổng số client thực tế phân bố rộng.
Một nhóm dùng thuật toán hash theo đường dẫn URL để giữ cache locality; endpoint /products phổ biến khiến một backend nhận gần hết tải trong khi các backend khác nhàn rỗi.
Backend có ba máy cấu hình tài nguyên khác nhau nhưng được khai báo weight bằng nhau; server nhỏ bắt đầu đạt CPU 100% trước server lớn, làm p99 của một phần request tăng.
Nhóm thử nghiệm thay đổi trọng số server qua Runtime API mà không đưa thay đổi vào cấu hình bền vững; sau lần reload, phân bố traffic quay lại như trước và lỗi nghẽn xuất hiện trở lại.
Một server vừa hồi phục sau bảo trì được đưa trở lại nhận đủ lưu lượng ngay lập tức; bộ nhớ cache và connection pool phía backend chưa kịp làm nóng nên độ trễ tăng trong vài phút đầu.
Ứng dụng giỏ hàng lưu session trong bộ nhớ tiến trình và HAProxy phân phối request không có persistence; khi khách chuyển trang, phiên bị chuyển sang máy khác và giỏ hàng trở về trống.
Nhóm bật sticky session bằng cookie của HAProxy để giữ người dùng trên một backend; khi backend đó DOWN, người dùng mất phiên vì trạng thái giỏ hàng không được chia sẻ giữa các máy.
Ứng dụng đặt cookie phiên và HAProxy cũng thêm cookie để chọn backend; trình duyệt giới hạn cookie hoặc cookie có Path không phù hợp làm hành vi bám phiên thay đổi giữa hai endpoint.
Hệ thống dùng stick-table để duy trì mối liên hệ giữa người dùng và backend trên hai node HAProxy; khi load balancer ngoài chuyển request sang node còn lại, người dùng bất ngờ đổi backend do trạng thái không được đồng bộ.
HAProxy dùng độ dài thời gian giữ bản ghi stick-table ngắn hơn thời gian phiên đăng nhập; khi khách ngừng thao tác rồi quay lại, request được gửi sang server khác và ứng dụng yêu cầu đăng nhập lại.
Một hệ thống dùng stickiness theo IP cho khách hàng doanh nghiệp đi qua proxy chia sẻ; hàng nghìn người được ghim vào cùng backend dù cụm còn đủ tài nguyên cho tất cả.
Backend bị lỗi và HAProxy thực hiện redispatch sang server còn sống; các request tiếp theo của cùng trình duyệt lại tìm về server trước đó theo cookie bám phiên và trải nghiệm người dùng không ổn định.
Frontend của HAProxy đạt giới hạn maxconn trong đợt quảng cáo; một phần client bị từ chối hoặc chờ thiết lập kết nối trong khi backend vẫn còn khả năng xử lý request.
Một server trong backend có maxconn thấp hơn số connection cần thiết để xử lý peak traffic; HAProxy đưa request vào hàng đợi và thời gian chờ tăng mặc dù CPU của server chưa cao.
Hệ thống có nhiều API cùng dùng một backend nhưng chỉ một API báo cáo tạo rất nhiều request giữ kết nối lâu; queue của backend tăng khiến API đăng nhập cũng bắt đầu timeout.
HAProxy cấu hình timeout connect quá thấp so với độ trễ thiết lập TCP qua WAN; những request đi tới backend vùng xa gặp lỗi nối kết rải rác, còn request đến backend trong vùng hoàn toàn bình thường.
Một endpoint xuất dữ liệu mất 30 giây nhưng timeout server ở HAProxy là 10 giây; client nhận lỗi gateway dù backend đã tạo xong file và ghi log thành công.
Ứng dụng WebSocket qua HAProxy hoạt động khi có message thường xuyên nhưng bị ngắt khi người dùng không gửi dữ liệu vài phút; cấu hình timeout của tunnel chưa phù hợp với phiên kết nối lâu dài.
Một client mạng yếu gửi HTTP headers rất chậm; số connection mở tăng mạnh và frontend dành nhiều tài nguyên chờ request chưa hoàn tất vì timeout http-request không phù hợp.
Ứng dụng giữ kết nối HTTP/1.1 keep-alive lâu giữa các request nhưng HAProxy đóng kết nối nhàn rỗi sớm hơn kỳ vọng; một SDK cũ báo lỗi socket khi tái sử dụng kết nối đã bị đóng.
Một client ngắt tải báo cáo giữa chừng trong lúc backend tiếp tục gửi dữ liệu qua HAProxy; biểu đồ request thất bại tăng nhưng log backend không có lỗi ứng dụng tương ứng.
Dịch vụ yêu cầu truyền video dạng streaming nhưng proxy có timeout áp cho khoảng im lặng giữa các chunk; trong các đoạn video ít dữ liệu, client bị mất kết nối mặc dù luồng chưa kết thúc.
HAProxy retry request khi mất kết nối tới backend; với POST tạo hóa đơn không có idempotency key, hệ thống ghi hai hóa đơn sau một đợt sự cố mà client chỉ nhận một response.
Một request POST được HAProxy chuyển tới backend vừa kịp ghi dữ liệu rồi mất kết nối trước khi trả response; hệ thống ngoài tự retry qua backend khác và kết quả thanh toán bị áp dụng hai lần.
Đội triển khai đặt retry cho các phản hồi lỗi từ upstream mà không phân biệt 503 do bảo trì với lỗi nghiệp vụ; trong giờ cao điểm, lượng request thực sự tới backend cao hơn nhiều so với lưu lượng người dùng.
Một API xác thực được bảo vệ bằng ACL chỉ cho phép dải IP văn phòng, nhưng HAProxy đứng sau CDN và chỉ nhìn thấy IP các máy CDN; nhân viên hợp lệ bị chặn trong khi quy tắc không còn phản ánh IP client.
Đội dùng X-Forwarded-For để kiểm tra địa chỉ IP người dùng nhưng cho phép client tự chèn header này trước HAProxy; log và quyết định giới hạn truy cập đôi khi dùng địa chỉ do client cung cấp.
Ứng dụng phía sau HAProxy cần biết scheme gốc để xây dựng callback URL; thiếu hoặc sai X-Forwarded-Proto khiến đăng nhập OAuth trả về URI HTTP dù trình duyệt bắt đầu từ HTTPS.
Một hệ thống TCP cần chuyển IP client thực qua PROXY protocol, nhưng backend được bật chế độ nhận PROXY protocol khi frontend chưa gửi dữ liệu này; backend đọc bytes đầu không đúng định dạng phiên.
Nhóm bật send-proxy tại HAProxy để truyền địa chỉ client cho dịch vụ TCP; backend cũ chưa hỗ trợ PROXY protocol và bắt đầu trả lỗi ngay khi nhận packet đầu tiên.
Một frontend TCP chỉ nên nhận PROXY protocol từ thiết bị cân bằng tải tin cậy nhưng được mở ra Internet; request do client tự gửi có thể làm sai thông tin nguồn mà dịch vụ phía sau dùng để ghi audit.
HAProxy ghi log HTTP nhưng không ghi tên frontend/backend và server đã chọn; khi chỉ một backend trả 502, nhóm trực không xác định được máy đích nào xử lý những request lỗi.
Dashboard chỉ theo dõi tổng tỷ lệ 5xx của HAProxy; trong đợt lỗi, đội vận hành không biết số lỗi phát sinh từ HAProxy khi không có server hay từ backend trả HTTP 500.
Log HAProxy ghi thời gian tổng request tăng đến 20 giây nhưng các chỉ số thời gian kết nối, chờ hàng đợi và phản hồi backend không được tách riêng; nhóm tối ưu nhầm vào CPU của ứng dụng.
Trong chiến dịch bán hàng, bộ nhận syslog dùng UDP bị quá tải khiến nhiều log truy cập HAProxy không tới nơi; dashboard báo lưu lượng thấp hơn thực tế dù bộ đếm request tại proxy vẫn tăng.
Trang thống kê HAProxy cho thấy backend UP nhưng có nhiều hàng đợi và lỗi kết nối; đội vận hành chỉ dựa vào trạng thái xanh của health check để kết luận không có sự cố.
Một request đi qua CDN, HAProxy và ba microservice; mỗi thành phần tự sinh request ID mới nên đội hỗ trợ không ghép được request lỗi trong log HAProxy với giao dịch thất bại ở backend.
Nhóm bật ghi đầy đủ Authorization và Cookie trong access log HAProxy để truy vết 401; file log được chuyển vào kho dùng chung khiến token và cookie phiên xuất hiện ở nơi nhiều nhóm có quyền đọc.
API đăng nhập nhận request qua HAProxy nhưng một ACL giới hạn tốc độ chỉ đếm theo IP; hàng trăm người dùng hợp lệ sau NAT của văn phòng bị từ chối khi một người thử sai mật khẩu liên tục.
Nhóm dùng stick-table đếm số request trong một cửa sổ thời gian để chặn abuse; sau khi scale từ một lên ba node HAProxy, cùng một client có thể gửi vượt ngưỡng tổng vì các bảng đếm không nhất quán giữa node.
Một khách tạo tải tăng vọt trong vài giây qua API công khai; giới hạn theo request rate trung bình trong thời gian dài không ngăn backend bị nghẽn khi đợt burst xuất hiện.
Một frontend đặt giới hạn số connection đồng thời theo địa chỉ nguồn; các bot sử dụng nhiều địa chỉ IP khác nhau làm tổng số connection đến backend vượt khả năng xử lý dù mỗi IP đều dưới ngưỡng.
Nhóm chặn request nếu header Host không nằm trong danh sách hợp lệ nhưng bỏ sót hostname có chữ hoa hoặc cổng; một số khách hàng hợp lệ nhận 403 chỉ trên một loại HTTP client.
API cho phép tải tệp lớn nhưng HAProxy thêm kiểm tra kích thước request mà không phân biệt đường dẫn; khách hàng không thể upload dù các request JSON nhỏ vẫn chạy bình thường.
HAProxy dùng ACL kiểm tra URL bắt đầu bằng /admin để giới hạn quyền; một số biến thể path có dấu gạch chéo hoặc ký tự mã hóa được backend chuẩn hóa khác cách proxy so khớp và đi đến endpoint không như mong đợi.
Một bản phát hành thay map định tuyến tại Runtime API trong khi file cấu hình trên đĩa vẫn giữ phiên bản cũ; sau khi HAProxy reload, đường dẫn khách hàng mới lại trỏ về backend trước đó.
Đội vận hành sửa haproxy.cfg rồi reload trực tiếp mà không chạy kiểm tra cú pháp; một ký tự sai trong quy tắc ACL khiến cấu hình mới không được áp dụng và thay đổi khẩn cấp thất bại.
Một đợt rolling reload HAProxy để thay chứng chỉ TLS diễn ra khi nhiều kết nối WebSocket và TCP lâu dài còn mở; số tiến trình cũ tồn tại lâu hơn dự kiến, khiến kế hoạch giải phóng tài nguyên gặp khó khăn.
HAProxy sử dụng hostname động của các backend, nhưng DNS thay IP pod sau khi triển khai; cấu hình không có cơ chế cập nhật phù hợp làm một phần traffic vẫn gửi tới địa chỉ đã không còn phục vụ.
Backend Kubernetes scale số pod liên tục nhưng HAProxy đang cân bằng trên danh sách IP viết cố định; các pod mới không nhận lưu lượng còn pod cũ đã bị xóa vẫn xuất hiện trong danh sách máy đích.
Hai node HAProxy kết hợp VIP failover để tránh điểm lỗi duy nhất; khi node chính mất kết nối tới mạng kiểm tra nhưng vẫn nhận được lưu lượng từ một nhánh khác, hệ thống có lúc quảng bá VIP không nhất quán.
Trang thống kê HAProxy được mở trên một port quản trị không có kiểm soát truy cập phù hợp; khi rà soát bảo mật, người ngoài có thể xem tên backend, số phiên và trạng thái hạ tầng.
Socket Runtime API của HAProxy được cấp quyền quá rộng trên máy chủ dùng chung; một tiến trình không thuộc nhóm vận hành có thể thay trạng thái server hoặc weight mà không đi qua quy trình phê duyệt.
HAProxy dùng ACL xác thực Basic cho trang nội bộ nhưng thông tin đăng nhập được chia sẻ giữa nhiều nhân viên; sau khi một người nghỉ việc, nhóm không truy được ai đã sử dụng tài khoản chung trong log.
Ứng dụng Java trả response nhỏ nhưng sử dụng rất nhiều kết nối ngắn; sau khi HAProxy chuyển từ cân bằng TCP sang HTTP với giữ kết nối, các chỉ số kết nối và độ trễ thay đổi nhưng nhóm chưa đo tác động tới pool của backend.
Trong đợt mất một rack, một nửa server backend cùng xuống trạng thái DOWN; HAProxy dồn toàn bộ lưu lượng vào các server còn lại, khiến chúng chạm giới hạn connection dù health check của từng server vẫn trả thành công.

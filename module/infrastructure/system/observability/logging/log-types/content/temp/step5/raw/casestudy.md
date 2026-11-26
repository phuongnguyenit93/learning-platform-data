Một dịch vụ đặt hàng ghi log INFO 'Order created' ngay trước khi gọi database; khi database timeout, dashboard đếm số đơn tạo thành công từ log cao hơn số hàng thực tế trong bảng orders.
Ứng dụng Java ghi log DEBUG cho toàn bộ payload thanh toán vào production để tiện điều tra; dung lượng log tăng 30 lần và nhiều bản ghi chứa số thẻ đã nhập trong request.
Một endpoint kiểm tra tồn kho ghi INFO cho từng lần đọc cache với 8.000 request mỗi giây; log của sự kiện cập nhật hàng tồn quan trọng bị chìm giữa hàng triệu dòng truy cập thông thường.
Ứng dụng ghi WARN khi khách nhập sai mã giảm giá và ERROR khi tiến trình thanh toán thực sự không thể hoàn thành; dashboard cộng cả hai nhóm thành lỗi hệ thống khiến tỷ lệ sự cố bị phóng đại.
Một service có log 'Request failed' nhưng không ghi operation, error code hay request ID; khi hai API khác nhau cùng lỗi, đội trực không phân biệt được chức năng nào bị ảnh hưởng.
Hệ thống batch ghi 'Job started' khi nhận lịch chạy nhưng không ghi kết quả cuối hoặc số lượng bản ghi xử lý; sau sự cố, các job đang treo và job đã hoàn tất xuất hiện giống nhau trong log.
Một luồng xử lý bất đồng bộ ghi 'Email sent' khi đưa message vào queue; broker mất kết nối sau đó và khách không nhận được email dù application log hiển thị gửi thành công.
Một ứng dụng chạy trên ba phiên bản JVM có logger ghi thời điểm theo múi giờ khác nhau; log của một giao dịch xuất hiện như thể phản hồi xảy ra trước yêu cầu.
Một nhóm phát triển tăng mức log từ INFO lên TRACE cho toàn bộ service để bắt một lỗi hiếm; CPU, I/O và độ trễ p99 tăng ngay trong giai đoạn quan sát.
Ứng dụng chuyển từ logger có phân cấp package sang một mức log chung; khi bật DEBUG cho một thư viện HTTP ồn ào, tất cả request của các thư viện khác cũng được ghi chi tiết không cần thiết.
Một service ghi message lỗi bằng cách nối chuỗi trước khi kiểm tra log level; dưới tải cao, CPU dành cho dựng chuỗi lớn dù level DEBUG đang tắt.
Phần mềm xử lý đơn ghi log INFO cho trạng thái thanh toán nhưng không phân biệt kết quả chấp thuận, từ chối nghiệp vụ và lỗi kết nối; báo cáo vận hành phải đọc nội dung tự do để xác định ý nghĩa.
API phục vụ 100.000 request mỗi phút nhưng access log tại Nginx chỉ ghi timestamp, method và status; khi xuất hiện nhiều 504, đội trực không biết host, route hoặc upstream nào xử lý request lỗi.
Khách hàng báo trang tải rất chậm, còn access log chỉ lưu mã 200; đội vận hành không có thời gian xử lý, số byte trả về và thông tin kết nối để phân biệt request chậm với response lớn.
Reverse proxy trả 502 cho một nhóm khách nhưng application log không có request tương ứng; access log thiếu trường upstream address nên chưa xác định được máy backend nào nhận kết nối thất bại.
Trong đợt triển khai canary, một số URL /checkout trả 404 chỉ trên phiên bản mới; access log không chứa nhãn deployment version nên lỗi của hai phiên bản bị trộn chung.
API nằm sau CDN và gateway, nhưng access log ứng dụng chỉ thấy địa chỉ IP của gateway; đội an ninh kết luận nhầm toàn bộ lưu lượng bất thường đến từ một máy nội bộ.
Một gateway ghi trực tiếp X-Forwarded-For do client gửi mà không ghi địa chỉ kết nối trực tiếp; khi điều tra gian lận, địa chỉ IP được trình bày như nguồn đáng tin cậy dù có thể bị giả mạo.
Trình duyệt liên tục thực hiện OPTIONS trước khi gửi POST; access log gộp mọi method khiến nhóm sản phẩm nghĩ số lần khách bấm đặt hàng tăng gấp đôi.
Một API upload được báo lỗi 413 tại load balancer trước khi tới service; application log trống còn access log ở tầng biên có mã trạng thái và số byte request lớn.
Đội trực so sánh số HTTP 200 tại gateway với số bản ghi business success tại database và phát hiện chênh lệch; access log tính cả request tra cứu, retry và tạo tài nguyên nhưng báo cáo chưa phân biệt.
Một backend trả HTTP 200 nhưng gateway ghi 504 do hết timeout chờ upstream; access log và application log không dùng chung request ID nên hai nhóm không biết đó là một giao dịch.
CDN cache phản hồi của API sản phẩm, khiến application access log ghi ít request hơn số lượt truy cập thực; báo cáo lưu lượng chỉ dựa vào log origin đánh giá sai nhu cầu người dùng.
Một reverse proxy không ghi User-Agent và client protocol; khi một SDK cũ gây lỗi HTTP/2 sau bản nâng cấp, đội hỗ trợ không khoanh vùng được loại client bị ảnh hưởng.
Access log ghi đầy đủ query string của URL tải hóa đơn, bao gồm mã xác thực tạm thời; hệ thống phân tích lưu lượng lưu lại những mã này vượt thời gian hiệu lực nghiệp vụ.
Một proxy ghi status 499 khi client ngắt kết nối nhưng dashboard gom tất cả mã khác 2xx vào lỗi server; đội vận hành tăng số pod dù lỗi xuất phát từ thao tác hủy trên trình duyệt.
Ứng dụng bắt một lỗi database ở tầng repository, service và controller rồi mỗi tầng ghi ERROR kèm stack trace; một request lỗi tạo ba bản ghi giống nhau, làm số sự cố bị đếm gấp ba.
Một worker Java chỉ ghi exception.getMessage mà bỏ stack trace và exception type; hai lỗi NullPointerException và lỗi mạng có message giống nhau trong khi đường xử lý hoàn toàn khác.
Ứng dụng ghi toàn bộ stack trace cho lỗi kiểm tra dữ liệu thường gặp với HTTP 400; mỗi ngày hàng triệu dòng ERROR khiến sự cố OutOfMemoryError hiếm bị chìm trong kết quả tìm kiếm.
Một exception bị thư viện thứ ba bọc qua nhiều lớp rồi log chỉ ghi lỗi ngoài cùng 'Processing failed'; thông tin nguyên nhân gốc và chuỗi exception không còn trong bản ghi.
Một ứng dụng retry giao dịch ba lần và log ERROR cho từng attempt dù attempt cuối thành công; cảnh báo hệ thống bùng phát trong khi tỷ lệ request thất bại cuối cùng không đổi.
API ném timeout sau khi database commit thành công và log ERROR 'payment failed'; đối chiếu với log nghiệp vụ cho thấy một số giao dịch đã chuyển trạng thái hoàn tất dù client nhận lỗi.
Ứng dụng Java phát sinh OutOfMemoryError rồi process bị kill trước khi flush log bất đồng bộ; log collector chỉ có các dòng trước sự cố và không có stack trace cuối cùng.
Một nền tảng ghi lỗi ERROR tại application log nhưng không kèm pod ID hoặc container name; khi Kubernetes restart các pod liên tiếp, đội trực không gắn được stack trace với lần chạy cụ thể.
Trong giờ cao điểm, lỗi kết nối Redis được ghi bằng WARN không có nhãn dependency; dashboard chỉ theo dõi ERROR nên không phát hiện tình trạng retry kéo dài gây tăng độ trễ.
Một job xử lý dữ liệu lỗi ở bản ghi thứ 300.000; log chỉ có tên file mà không có batch ID hoặc vị trí bản ghi, khiến việc tái hiện và xác nhận phạm vi ảnh hưởng rất khó.
Application log ghi 'Deadlock detected' trong khi database error log chứa transaction ID và tài nguyên khóa; hai nguồn không dùng chung thời điểm chuẩn và đội điều tra chưa xác định hai dòng có liên quan.
Một hệ thống xác thực ghi security log cho các lần đăng nhập thất bại nhưng không phân biệt mật khẩu sai, tài khoản bị khóa và token hết hạn; hệ thống SIEM đánh đồng lỗi sử dụng thông thường với dấu hiệu tấn công.
API đăng nhập có hàng nghìn phản hồi 401 từ một dải IP trong năm phút; nhóm chỉ xem application error log và chưa có security event chứa số lần thử, nguồn truy cập và danh tính bị nhắm tới.
Đội an ninh phát hiện một tài khoản đăng nhập từ hai quốc gia trong một khoảng thời gian ngắn, nhưng security log chỉ ghi địa chỉ IP đã qua NAT và không có thời điểm xác thực chính xác.
Một dịch vụ ghi SecurityEvent với username và trạng thái xác thực, nhưng khi bật MFA không ghi yếu tố thứ hai đã được xác minh hay thất bại; đội điều tra không xác định được bước nào bị vượt qua.
Nhóm phát hiện thay đổi quyền quản trị ngay trước khi dữ liệu bị tải hàng loạt; security log chỉ có lần đăng nhập và HTTP status, còn audit log về thay đổi role không được thu thập.
Gateway ghi sự kiện access denied do policy nhưng thiếu policy ID và identity của workload; một sự cố phân quyền Kubernetes bị chẩn đoán nhầm thành lỗi ứng dụng 403.
Ứng dụng đẩy toàn bộ giá trị Authorization header vào security log khi token bị từ chối; bộ phận bảo mật tìm thấy bearer token hợp lệ đã được lưu trong hệ thống SIEM có nhiều người truy cập.
Web application firewall tạo log cho mọi request bị chặn với rule ID nhưng không có URL path hoặc request ID; đội điều tra không biết rule mới có đang chặn nhầm khách hợp lệ.
Một tổ chức phát hiện nhiều lần đăng nhập thất bại nhưng không ghi nhận việc tài khoản đã được mở khóa hoặc reset mật khẩu; quá trình điều tra không phân biệt hành vi tự phục hồi với thay đổi của quản trị viên.
Đội vận hành gắn mọi response HTTP 403 vào security incident; một nhóm request bị chặn bởi quyền nghiệp vụ thông thường làm số cảnh báo xâm nhập tăng mà chưa có bằng chứng tấn công.
Trong một cuộc điều tra, security log từ identity provider cho biết đăng nhập thành công nhưng application log không có phiên tương ứng; hai hệ thống sử dụng session ID khác và không có khóa liên kết.
Ứng dụng phát hành API key mới cho đối tác nhưng không ghi security event khi khóa bị tạo hoặc thu hồi; sau một vụ lộ khóa, đội an ninh chỉ thấy các lần sử dụng mà không biết vòng đời credential.
Một hệ thống quản lý người dùng có nút đổi vai trò từ viewer thành admin; database lưu trạng thái mới nhưng audit log chỉ ghi 'User updated' và không chứa giá trị trước/sau của trường quyền.
Nhân viên hỗ trợ chỉnh sửa hạn mức thanh toán cho khách hàng; ứng dụng có log INFO về request thành công nhưng không có audit event thể hiện tác nhân, đối tượng, thời điểm và lý do thay đổi.
Một hệ thống kế toán yêu cầu chứng minh ai phê duyệt giao dịch; log HTTP chỉ cho thấy service account gọi endpoint, trong khi danh tính nhân viên cuối và hành động phê duyệt không được ghi.
Ứng dụng cho phép quản trị viên xem dữ liệu sức khỏe của khách hàng; audit log chỉ ghi thao tác chỉnh sửa mà không ghi hoạt động truy cập đọc hồ sơ nhạy cảm.
Audit log của một hệ thống lưu ở cùng database với dữ liệu nghiệp vụ và tài khoản quản trị có quyền xóa cả hai; sau sự cố, hồ sơ thao tác cũng biến mất cùng các bản ghi bị xóa.
Một dịch vụ ghi audit event trước khi transaction database commit; transaction sau đó rollback nhưng hệ thống kiểm toán vẫn ghi hành động 'đã thay đổi số dư' như sự kiện hoàn tất.
Ứng dụng chỉ ghi audit event sau khi commit nhưng message broker bị lỗi ngay trước khi nhận event; bản ghi nghiệp vụ đã thay đổi trong khi hệ thống audit không có sự kiện tương ứng.
Nhóm xây audit log bằng cách lưu toàn bộ JSON trước và sau của hồ sơ; khi hồ sơ chứa mật khẩu băm, số giấy tờ và địa chỉ cá nhân, kho audit trở thành nguồn dữ liệu nhạy cảm ngoài dự định.
Hai nhân viên cùng chỉnh sửa một hồ sơ và cả hai thao tác đều thành công; audit log không có version hoặc correlation ID nên không thể dựng lại thứ tự giá trị bị ghi đè.
Một nhân viên dùng chức năng impersonation để hỗ trợ khách; audit log chỉ ghi danh tính khách hàng cuối cùng, khiến nhóm kiểm toán không biết ai thực sự khởi tạo thao tác.
Hệ thống yêu cầu lưu bằng chứng về thay đổi chính sách bảo mật trong nhiều năm, nhưng các audit event bị xóa theo chính sách 30 ngày áp dụng chung cho access log.
Một ứng dụng đa tenant ghi audit log có user ID và action nhưng không có tenant ID; khi kiểm toán sự kiện của một khách hàng, kết quả tìm kiếm trộn hành động thuộc nhiều tenant.
Đội kiểm toán phát hiện một thay đổi dữ liệu xảy ra ngoài API thông thường qua script bảo trì; audit log ở tầng ứng dụng không ghi được thao tác do DBA chạy trực tiếp trong database.
Nhóm triển khai chữ ký số cho audit record nhưng bộ thu log có thể sửa timestamp và thứ tự event trước khi ký; trong kiểm toán, bằng chứng không chứng minh chính xác lịch sử đã xảy ra.
Chính sách quyền riêng tư yêu cầu xóa dữ liệu cá nhân đã hết mục đích xử lý, nhưng audit log được giữ dài hạn chứa email và số điện thoại trực tiếp trong từng event.
Ứng dụng ghi business event 'OrderPlaced' ngay khi nhận request nhưng sau bước giữ tồn kho lại từ chối đơn; dashboard kinh doanh tính cả những request chưa trở thành đơn hợp lệ.
Đội vận hành dùng số lượng access log HTTP 200 trên /checkout để tính doanh thu; endpoint có thể trả thành công sau khi tạo yêu cầu thanh toán chưa được ngân hàng xác nhận.
Một đơn hàng chuyển qua các trạng thái CREATED, PAID, CANCELLED và REFUNDED; business log chỉ ghi trạng thái cuối, khiến bộ phận chăm sóc khách hàng không dựng lại được chuỗi sự kiện.
Nhân viên mua hàng phản ánh đơn được tính hai lần; business event có cùng order ID nhưng không chứa event ID và idempotency key để phân biệt retry với thao tác đặt hàng mới.
Một quy trình hoàn tiền ghi 'RefundRequested' và 'RefundCompleted' cùng log level INFO; dashboard lọc theo chữ 'Refund' rồi báo số tiền đã trả cao hơn số tiền thực chi.
Ứng dụng ghi mỗi lần thêm sản phẩm vào giỏ là một business conversion; trong chương trình khuyến mãi, số conversion tăng gấp năm nhưng số thanh toán thực không tăng tương ứng.
Payment service ghi business event khi nhận webhook từ cổng thanh toán; cùng webhook được gửi lại ba lần khiến báo cáo giao dịch cộng ba sự kiện cho một khoản tiền đã xử lý.
Nhóm sản phẩm triển khai feature flag cho 10% người dùng nhưng business log không có variant; kết quả chiến dịch không thể so sánh nhóm thử nghiệm với nhóm đối chứng.
Một hệ thống đặt vé ghi business event 'SeatReserved' mà không có thời gian hết hạn giữ chỗ; bộ phận báo cáo nhầm ghế đang tạm khóa với ghế đã bán.
Quy trình saga giao hàng thực hiện bù trừ sau khi thanh toán thành công nhưng vận chuyển thất bại; business log chỉ có sự kiện thành công đầu tiên và không phản ánh thao tác bù trừ.
Một job cập nhật định mức tồn kho thành công ở database nhưng không tạo business event; dashboard kế hoạch sản xuất không phản ánh thay đổi dù application log báo thao tác thành công.
Ứng dụng thay đổi schema của business event bằng cách đổi trường amount từ số sang chuỗi có ký hiệu tiền tệ; consumer phân tích log phiên bản cũ không đọc được sự kiện mới.
Máy chủ Kubernetes báo OOMKilled cho pod, còn application log chỉ dừng đột ngột mà không có exception; đội trực chưa đối chiếu container event và memory limit với log của tiến trình.
API trả 503 sau khi một node Kubernetes mất kết nối mạng; ingress access log có lỗi upstream nhưng node log và kubelet event mới ghi nhận việc pod bị di chuyển.
Một pod Java khởi động chậm và readiness probe liên tục thất bại; infrastructure log của kubelet báo probe timeout còn application log chỉ ghi 'Application started' mà không có trạng thái phụ thuộc.
Ổ đĩa của node đạt 95% dung lượng do container stdout ghi quá nhiều; infrastructure log của container runtime báo lỗi ghi file trước khi ứng dụng bắt đầu mất log mới.
Trong giờ cao điểm, log hệ điều hành ghi nhiều network interface drops nhưng application log chỉ có socket timeout; đội vận hành chưa xác định mất gói diễn ra ở node, gateway hay mạng bên ngoài.
Một máy database ghi cảnh báo disk latency cao vào system log nhưng API chỉ bắt đầu trả timeout 20 phút sau; đội điều tra chưa đặt hai chuỗi sự kiện trên cùng timeline.
Hệ thống đa vùng ghi log kernel theo UTC và log load balancer theo thời gian địa phương; khi failover xảy ra, bản ghi chuyển tuyến có vẻ đến trước cảnh báo mất kết nối.
Một node bị reboot trong lúc deploy; Kubernetes event cho thấy NodeNotReady, cloud activity log ghi thay máy ảo, còn application log chỉ có hàng loạt lỗi kết nối tới dependency.
Nhóm thu mọi dòng stdout của container dưới loại application log nhưng lẫn cả thông báo health của service mesh proxy; báo cáo lỗi ứng dụng đếm cả lỗi cấu hình mạng ở sidecar.
Load balancer có access log về HTTP 502 và system log về backend health check DOWN; hai loại log không có trường backend pool thống nhất nên nhóm không liên kết được nguyên nhân.
Firewall cloud thay đổi rule và nhiều kết nối tới database bị drop; ứng dụng chỉ báo timeout, còn cloud audit log ghi người thay đổi rule nhưng chưa được đưa vào kho điều tra chung.
Một cơ sở dữ liệu PostgreSQL có server log ghi deadlock và transaction ID; application log chỉ báo 'Database error' nên nhóm chưa biết request nào giữ khóa gây chờ.
Một hệ thống chỉ giữ container logs, không thu thập DNS resolver log; sau đợt lỗi phân giải ngắt quãng, mọi ứng dụng đều ghi UnknownHostException nhưng nguyên nhân ở DNS nội bộ vẫn thiếu chứng cứ.
Một ứng dụng ghi log text với dấu phân cách dấu phẩy trong khi giá trị error message cũng chứa dấu phẩy; pipeline ingest tách nhầm cột và thông tin severity bị chuyển vào trường không đúng.
Nhóm chuyển sang structured JSON logging nhưng một số exception được in nhiều dòng không thuộc object JSON; collector tạo bản ghi rời khiến trace ID chỉ có ở dòng đầu.
Service A dùng trường requestId, service B dùng correlation_id và gateway dùng trace_id; khi điều tra giao dịch đa dịch vụ, truy vấn theo một trường không lấy đủ log liên quan.
Một pod ghi log JSON có trường timestamp theo epoch millisecond còn collector giả định epoch second; dashboard sắp xếp bản ghi vào tương lai rất xa dù service hoạt động bình thường.
Ứng dụng ghi lỗi với level='ERROR' nhưng pipeline log chuyển tất cả thành severity='INFO' do mapping sai; hệ thống cảnh báo chỉ theo severity không phát hiện sự cố.
Nhóm đưa toàn bộ stack trace vào một string nhưng dashboard chỉ hiển thị 1.024 ký tự đầu; phần 'Caused by' chứa nguyên nhân thực tế nằm ở cuối và không có trong kết quả tìm kiếm.
Một service gắn customer ID vào tên logger thay vì trường dữ liệu có cấu trúc; số tên logger phát sinh tăng nhanh và việc lọc theo khách hàng không nhất quán giữa phiên bản ứng dụng.
Trong một báo cáo, statusCode được lưu dưới dạng chuỗi ở service A và số nguyên ở service B; câu truy vấn điều tra các lỗi 5xx chỉ nhận một phần bản ghi.
Nhóm gắn log level FATAL cho mọi lỗi HTTP 400 vì muốn dễ tìm; dashboard ưu tiên xử lý thông báo nhập liệu bình thường hơn lỗi mất kết nối database đang được ghi WARN.
Một ứng dụng ghi ERROR cho lỗi hợp lệ mà người dùng có thể sửa, còn lỗi mất dữ liệu thanh toán chỉ ghi INFO; on-call phân loại độ nghiêm trọng dựa vào level và xử lý sai thứ tự.
Ứng dụng HTTP ghi đầy đủ request body vào trường message nhưng giới hạn kích thước một bản ghi của collector nhỏ hơn payload; các log lớn bị cắt và parser JSON không đọc được.
Nhóm gắn label user_id cho mọi luồng truy vấn log trên Elasticsearch; số lượng field và index tăng nhanh, làm truy vấn ngày hôm trước chậm dù lượng request không đổi.
Java service dùng MDC lưu tenant_id và request_id nhưng không xóa context khi thread trong pool được tái sử dụng; một số log của khách B mang mã khách A dù request khác nhau.
Luồng xử lý CompletableFuture chuyển sang executor riêng mà không truyền logging context; log tại controller có trace ID nhưng log ở bước thanh toán bất đồng bộ lại thiếu trường này.
Một ứng dụng nhận request qua HTTP rồi xuất message vào Kafka; consumer ghi log với message ID nhưng producer không ghi correlation ID, khiến hành trình yêu cầu bị đứt ở ranh giới bất đồng bộ.
Khách gửi một yêu cầu qua CDN, gateway, Java API và database; bốn loại log dùng đồng hồ và thời điểm ghi khác nhau nên số liệu duration không thể trừ trực tiếp giữa các timestamp.
Trong một trace có ba attempt HTTP client cho cùng request, application log chỉ ghi correlation ID chung mà không có attempt number; đội trực tưởng ba request độc lập đã xuất hiện.
Một service sử dụng thread pool nhưng log ghi thread name chung là worker-1 của nhiều tiến trình; khi điều tra deadlock, tên thread không đủ để xác định instance hoặc pod gây lỗi.
Một gateway sinh X-Request-ID mới thay vì chuyển tiếp ID từ client; các log ứng dụng và access log đều có ID hợp lệ nhưng không thể nối cùng một request.
Nhóm cố liên kết security log và business log bằng email người dùng, trong khi người dùng có thể đổi email; các giao dịch sau đổi địa chỉ bị tách thành hai danh tính trong báo cáo.
Ứng dụng cho phép thao tác hỗ trợ thay khách hàng nhưng log chỉ ghi subject user ID; không thể phân biệt hành động do chủ tài khoản thực hiện với hành động do nhân viên hỗ trợ.
Người dùng phản ánh số dư sai sau 20 phút, đội điều tra có application log và database audit log nhưng không có transaction ID chung; các ghi thay đổi số dư diễn ra cùng giây khó ghép đúng.
Đội sản phẩm muốn lưu access log 90 ngày để thống kê nhưng nhóm an ninh cần security log lâu hơn; một chính sách giữ 30 ngày dùng chung khiến dữ liệu phục vụ kiểm tra sự cố cũ không còn.
Một tổ chức giữ toàn bộ DEBUG log và HTTP request body trong hai năm nhưng chỉ xem lại vài ngày khi gỡ lỗi; chi phí lưu trữ tăng, trong khi dữ liệu nhạy cảm bị giữ lâu hơn mục đích ban đầu.
Chính sách log retention của hệ thống quy định xóa sau 60 ngày, nhưng các bản sao đã xuất sang object storage và kho tìm kiếm phụ không nằm trong lịch xóa; dữ liệu cũ vẫn truy xuất được.
Một cuộc điều tra gian lận cần giữ một nhóm audit record ngoài thời hạn thông thường; job tự động xóa log hằng đêm vẫn loại bỏ các bản ghi đang có yêu cầu bảo toàn bằng chứng.
Nhóm cho phép nhân viên hỗ trợ đọc mọi loại log để giải quyết ticket; cùng quyền đó mở cả security log chứa IP, audit log chứa thay đổi quyền và lỗi có dữ liệu cá nhân.
Một dịch vụ mã hóa log khi lưu nhưng truyền log bằng HTTP không mã hóa từ node tới collector; dữ liệu khách hàng xuất hiện trên đoạn mạng nội bộ mà thiết kế bảo mật chưa đánh giá.
Ứng dụng mask trường password trong JSON request nhưng không mask dữ liệu cùng ý nghĩa nằm trong query string và header; access log vẫn có credential dù application log đã được che.
Đội triển khai cơ chế ẩn token bằng biểu thức chính quy chỉ nhận chuỗi 'Bearer ' viết đúng hoa thường; các token ở header dạng khác lọt vào log khi xảy ra lỗi xác thực.
Một nghiệp vụ upload giấy tờ cá nhân tạo exception và ghi nguyên tên tệp, đường dẫn nội bộ cùng metadata người dùng; log ERROR được gửi sang nhà cung cấp giám sát bên ngoài.
Một log collector nhận thông điệp có nội dung do người dùng nhập và xuất trực tiếp vào trang quản trị log; chuỗi chứa ký tự điều khiển và markup làm giao diện hiển thị sai khi nhóm hỗ trợ mở bản ghi.
Một công cụ SIEM chỉ cấp quyền xóa cho quản trị viên nhưng không ghi lại thao tác chỉnh sửa index log; sau sự cố, nhóm không chứng minh được ai đã thay đổi thời gian lưu hoặc bộ lọc dữ liệu.
Nhóm cấu hình lấy mẫu 1% cho toàn bộ application log để tiết kiệm chi phí; khi có thanh toán thất bại hiếm, phần lớn log ERROR và audit event của giao dịch không còn được thu thập.
Trong đợt flash sale, pipeline log bị nghẽn và bắt đầu bỏ bản ghi INFO; log từ các request thành công thiếu một phần trong khi bộ đếm gateway vẫn đầy đủ, khiến báo cáo doanh thu từ log không chính xác.
Một ứng dụng dùng asynchronous logger và cấu hình queue nhỏ; khi đột biến lỗi xảy ra, hàng đợi đầy khiến log quan trọng bị drop hoặc thread xử lý request bị chặn trong lúc ghi.
Đội vận hành đặt giới hạn lưu trữ 10 GB cho log container nhưng không cấu hình rotation; sau một tuần, node đầy đĩa và ứng dụng không ghi được log mới khi đang có sự cố.
Log rotation đổi tên file đang được collector tail nhưng collector giữ offset cũ; một phần log bị đọc trùng hoặc bỏ sót sau khi file mới cùng tên được tạo.
Một ứng dụng serverless chỉ sống vài trăm mili giây cho mỗi invocation; log cuối cùng được ghi bất đồng bộ nhưng runtime kết thúc trước khi exporter hoàn thành, khiến sự kiện thất bại không xuất hiện trong kho log.
Một pipeline normalize log loại bỏ trường service_version để giảm kích thước; khi phát hành canary 10%, lỗi chỉ xảy ra ở phiên bản mới nhưng dữ liệu tập trung không còn cách phân biệt.
Một bộ collector bị cấu hình parse timestamp theo UTC trong khi log đầu vào mang timezone +07:00; các lỗi được đưa vào sai khung giờ và dashboard sự cố dường như bắt đầu bảy giờ trước thực tế.
Một hệ thống tập trung nhật ký chỉ cho phép truy vấn theo service name, còn sự cố đi qua API gateway, message broker và hai microservice; mỗi đội tìm log riêng mà không có cách tổng hợp theo giao dịch.
Một báo cáo post-incident kết luận lỗi do database chỉ vì application log có chữ 'database timeout'; infrastructure log ghi bão hòa network interface trước đó nhưng chưa được đối chiếu vào timeline.
Một khách hàng báo bị từ chối quyền truy cập sau khi nhóm quản trị đổi policy; access log ghi 403, security log ghi policy denial và audit log ghi policy update, nhưng ba nguồn chưa có khóa và mốc giờ để xác nhận quan hệ nhân quả.
Ứng dụng trả 500 khi gửi email thất bại, nhưng business event của đơn hàng đã commit; đội trực chỉ xem error log nên thông báo khách chưa đặt hàng dù dữ liệu order và audit chứng minh khác.

Một hệ thống thương mại điện tử đặt Spring Cloud Gateway trước ba microservice; sau khi thêm route mới cho /api/orders, request đặt hàng lại được chuyển sang dịch vụ danh mục vì hai Path predicate có phạm vi chồng nhau.
Đội vận hành cấu hình Path predicate cho /products/** nhưng URL có dấu gạch chéo cuối bị xử lý khác so với URL không có dấu đó, khiến một số phiên bản client nhận 404.
Một API Gateway có route cho cả GET và POST trên cùng đường dẫn; khi bổ sung Method predicate, chức năng cập nhật sản phẩm bằng PATCH không còn đi tới backend dù trước đó hoạt động.
Dịch vụ thanh toán nhận request theo tên miền pay.example.com; sau khi chuyển sang ingress mới, Host predicate ở Gateway không khớp với giá trị host mà load balancer chuyển tiếp.
Một tổ chức vận hành nhiều thương hiệu trên cùng gateway; khi khách gửi Host header của thương hiệu khác, route được chọn không đúng với dữ liệu tenant trong token xác thực.
Nhóm marketing dùng Query predicate để phân luồng các chiến dịch khuyến mãi; client gửi query parameter bị encode khác cách test nên request đi vào route mặc định.
Ứng dụng quản lý đơn hàng định tuyến theo Header predicate cho phiên bản API; một số client cũ không gửi header nên bất ngờ bị chuyển sang backend phiên bản mới.
Nhóm quản lý truy cập cấu hình Cookie predicate để thử nghiệm tính năng cho một nhóm người dùng; cookie được trình duyệt gửi nhiều giá trị khiến rule chọn route khác với khi gọi bằng Postman.
Đội phát hành dùng Between predicate để mở route trong khung giờ bảo trì; máy chạy Gateway có timezone khác với lịch nghiệp vụ khiến route được kích hoạt sớm hơn dự kiến.
Một hệ thống triển khai Weight predicate để chia 10% lưu lượng tới bản canary; số request rất ít của một khách hàng làm tỷ lệ thực tế lệch xa tỷ lệ mà nhóm sản phẩm mong chờ.
Nhóm hạ tầng dùng RemoteAddr predicate để chỉ cho phép gọi API quản trị từ mạng văn phòng; khi đặt Gateway sau reverse proxy, địa chỉ client được nhận thành IP của proxy nên quy tắc không còn hiệu lực.
Một dịch vụ có nhiều route cùng đạt các predicate nhưng khai báo độ ưu tiên khác nhau; sau khi chỉnh order của route, endpoint sức khỏe bị chuyển tới backend nghiệp vụ.
Hệ thống cổng thanh toán được truy cập cả từ Internet và mạng nội bộ; các route có Path predicate giống nhau nhưng điều kiện Host khác khiến request nội bộ đôi khi đi vòng qua public service.
Một nền tảng quản lý học tập định tuyến bằng route ID trùng giữa cấu hình tĩnh và route mới cấp từ cấu hình động; dashboard hiển thị một route nhưng lưu lượng thực tế tới đích khác.
Nhóm triển khai xóa route cũ của dịch vụ thống kê; một số request còn giữ kết nối và tiếp tục nhận kết quả từ backend đã được ngừng hỗ trợ trong thời gian thay đổi cấu hình.
Ứng dụng gateway áp dụng StripPrefix cho đường dẫn /api/v1/orders; backend lại kỳ vọng prefix /orders/v1 nên mọi request tạo đơn đều nhận 404 sau khi release.
Một ứng dụng dùng PrefixPath để thêm đường dẫn nội bộ cho dịch vụ tìm kiếm; request đã chứa prefix do mobile client gửi bị nhân đôi đường dẫn và không còn match controller.
Nhóm chuyển endpoint từ /customers/{id}/history sang /history/{id}; RewritePath hoạt động với ID số nhưng thất bại khi ID có dấu chấm hoặc ký tự được mã hóa trong URL.
Dịch vụ quản lý tệp nhận đường dẫn có khoảng trắng và ký tự tiếng Việt; một filter thay đổi URI làm phần path được encode hai lần khiến backend không tìm ra tệp.
Một backend nhận đường dẫn chứa encoded slash trong mã tài liệu; gateway viết lại path trước khi chuyển tiếp và tạo ra đường dẫn không tương thích với cách servlet container phía sau xử lý.
Nhóm bảo trì chuyển route từ SetPath sang RewritePath; các request có query parameter vẫn được chuyển nhưng một số biến path trong mẫu route không còn giữ đúng giá trị.
Ứng dụng bán hàng có thể gọi endpoint cũ qua redirect; Gateway đặt RedirectTo theo HTTP thay vì HTTPS, khiến trình duyệt gặp cảnh báo khi truy cập qua ingress TLS.
Dịch vụ danh mục sử dụng AddRequestHeader để truyền mã vùng; sau khi proxy phía trước thêm header cùng tên, backend nhận hai giá trị và không biết mã vùng nào là hợp lệ.
Nhóm vận hành dùng SetRequestHeader để gắn tenant ID theo route; dữ liệu trong header cũ do client gửi vẫn xuất hiện ở một số nhánh filter và tạo nguy cơ dùng sai tenant.
Ứng dụng dùng RemoveRequestHeader để xóa header nội bộ do client có thể giả mạo; một route mới không kế thừa filter nên backend chấp nhận X-User-Id từ Internet.
Dịch vụ xác thực qua gateway chuyển JWT tới backend; filter xóa Authorization để bảo vệ log nhưng vô tình làm service đích nhận request không có chứng thực.
Một backend cần header Host gốc để tạo URL callback OAuth; sau khi bật PreserveHostHeader, dịch vụ đích lại gửi traffic theo tên miền công khai thay vì virtual host nội bộ.
Nhóm đặt SetRequestHostHeader cho một route tới dịch vụ SaaS; chứng chỉ TLS của đích khớp SNI khác với Host header và các request bắt đầu lỗi ở một môi trường nhất định.
Một service trả đồng thời hai Access-Control-Allow-Origin do backend và Gateway cùng cấu hình CORS; trình duyệt từ chối response dù request thử bằng công cụ dòng lệnh trả 200.
Đội phát triển thêm DedupeResponseHeader nhưng vẫn có nhiều giá trị Vary và Cache-Control khác nhau; sau triển khai, cache CDN lưu sai biến thể nội dung cho các client.
Một Gateway gắn AddResponseHeader để đánh dấu tên môi trường; response lỗi do filter tạo sớm không mang header này nên đội QA khó xác định node phát sinh lỗi.
Ứng dụng có filter SetStatus để chuẩn hóa response 503 thành 200; hệ thống giám sát báo tỷ lệ thành công cao dù backend đang quá tải và không xử lý được giao dịch.
Dịch vụ hóa đơn trả header Location với hostname nội bộ; Gateway chỉ sửa path, khiến client nhận URL không thể truy cập để xem hóa đơn vừa tạo.
Nhóm phát triển dùng RewriteResponseHeader với biểu thức thay thế hostname; một URL chứa cả tên miền và tham số truy vấn bị thay đổi sai khiến liên kết tải tài liệu bị lỗi.
API quản trị dùng RemoveResponseHeader để loại Server và thông tin công nghệ; response được sinh trực tiếp từ Gateway trong một trường hợp lỗi vẫn lộ thông tin triển khai.
Một ứng dụng tạo GlobalFilter để gắn correlation ID cho mọi request; filter chạy trước route filter nhưng một số response bị lỗi sớm không có mã tương quan trong access log.
Nhóm khai báo thứ tự GlobalFilter và GatewayFilter không đúng như giả định; filter xác thực đọc header sau khi filter khác đã sửa nên request hợp lệ bị từ chối.
Một filter đo thời gian bắt đầu và kết thúc của request trong Spring Cloud Gateway; trên đường response, thứ tự chạy ngược làm metric thiếu khoảng thời gian chờ backend.
Đội phát triển đặt logic kiểm tra chữ ký HMAC trước filter rewrite body; chữ ký được tính trên payload gốc nhưng backend nhận nội dung đã biến đổi khiến việc kiểm chứng khác nhau.
Ứng dụng dùng ModifyRequestBody để chuyển JSON từ hợp đồng cũ sang mới; request có body rỗng hoặc loại content không phải JSON gây lỗi trước khi đến producer service.
Nhóm áp dụng ModifyResponseBody để ẩn trường dữ liệu nhạy cảm; response streaming hàng trăm MB bị gom vào bộ nhớ Gateway và pod bị OOM khi nhiều người dùng tải báo cáo.
Trợ lý hỗ trợ khách hàng nhận response gzip từ backend; filter sửa nội dung body mà không cập nhật cách nén và các header liên quan khiến trình duyệt không giải mã được dữ liệu.
Một dịch vụ trả dữ liệu video và hỗ trợ Range request; Gateway ghi lại response body để kiểm tra thông tin làm hỏng cơ chế tải tiếp và tăng bộ nhớ sử dụng.
Nhóm tích hợp dùng filter ghi log toàn bộ request và response; các endpoint đăng nhập làm token và dữ liệu cá nhân xuất hiện trong hệ thống nhật ký tập trung.
Một GlobalFilter thực hiện gọi JDBC đồng bộ trong luồng Reactor Netty; khi database kiểm tra quyền chậm, tất cả route trên cùng event-loop bị tăng độ trễ dù backend không có lỗi.
Một filter kiểm tra header dùng ThreadLocal để giữ trạng thái người dùng; khi processing bất đồng bộ đổi scheduler, request của hai tenant có lúc bị gắn sai thông tin.
Gateway tích hợp service discovery với đường dẫn lb://inventory-service; khi registry không còn instance khỏe mạnh, request nhận lỗi nhưng dashboard không phân biệt lỗi route với lỗi load balancing.
Nhóm triển khai DiscoveryClient Route Definition Locator để tự sinh route; một tên service có dấu gạch dưới làm URL dự đoán của client không khớp đường dẫn được công bố.
Một microservice được đổi tên trong service registry nhưng route thủ công vẫn dùng tên cũ; pod Gateway báo healthy trong khi toàn bộ request qua route đó đều lỗi.
Nhóm vận hành dùng nhiều instance của dịch vụ giao hàng qua load balancer; một instance đang khởi động vẫn được chọn và trả 503 cho nhiều request đầu tiên.
Hệ thống chạy dịch vụ ở hai availability zone; Gateway chọn instance không cùng zone làm p95 latency tăng mạnh khi traffic chuyển vùng trong giờ cao điểm.
Ứng dụng có nhiều route dùng cùng service ID nhưng áp dụng filter khác nhau; khi registry mất kết nối tạm thời, một route vẫn chọn được instance cũ còn route khác báo không có backend.
Một hệ thống microservices dùng service discovery theo metadata phiên bản; khi triển khai canary, Gateway chuyển request chưa có quyền thử nghiệm sang instance phiên bản mới.
Nhóm phát triển giả định round-robin sẽ giữ session trên cùng instance; người dùng có session lưu trong bộ nhớ backend liên tục bị yêu cầu đăng nhập lại khi request được chia tải.
Gateway định tuyến tới backend sử dụng HTTP/2 trong khi kênh kết nối thực tế chỉ hỗ trợ HTTP/1.1; một số endpoint streaming có độ trễ và hành vi không giống thử nghiệm.
Ứng dụng có route tới hostname nội bộ do DNS cung cấp; sau khi bản ghi DNS đổi địa chỉ, kết nối đã được pool giữ lại khiến request tiếp tục đi tới node cũ.
Gateway dùng connection pool Reactor Netty với giới hạn kết nối nhỏ; trong đợt flash sale, request xếp hàng chờ kết nối backend dù CPU và số pod dịch vụ đích còn dư.
Một route gọi backend lâu không trả response; timeout của Gateway ngắn hơn thời gian xử lý hợp lệ nên người dùng nhận lỗi trong khi backend vẫn tiếp tục thực hiện giao dịch.
Nhóm cấu hình connect timeout rất dài cho upstream không thể truy cập; request chiếm tài nguyên Gateway trong khi load balancer đang chờ failover sang dịch vụ khác.
Dịch vụ báo cáo có response timeout khác các API giao dịch nhanh; filter cấu hình timeout toàn cục làm những báo cáo hợp lệ bị cắt giữa chừng.
Một Gateway áp dụng timeout theo route nhưng không đồng nhất với timeout của ingress; request bị đóng ở proxy phía trước và trace phía Gateway chỉ ghi kết nối bị hủy.
Ứng dụng xử lý SSE qua gateway để cập nhật tiến độ đơn hàng; idle timeout của proxy hoặc Gateway đóng các kết nối không phát dữ liệu trong vài chục giây.
Một ứng dụng chat dùng WebSocket sau đường dẫn /ws; route HTTP hoạt động nhưng bước Upgrade không được chuyển đúng khiến client liên tục nhận lỗi handshake.
Nhóm đổi từ ws:// sang wss:// ở public ingress; Gateway vẫn kết nối tới websocket backend theo URI không phù hợp và các phiên realtime ngắt ngay sau khi mở.
Dịch vụ sử dụng Server-Sent Events và chunked transfer; một filter nhận body hoàn chỉnh trước khi gửi làm người dùng chỉ thấy tất cả sự kiện khi kết nối kết thúc.
Gateway trả dữ liệu tệp lớn từ object storage; một filter retry request khi upstream ngắt giữa chừng khiến dữ liệu đầu ra bị lặp sau khi một phần response đã gửi cho client.
Ứng dụng dùng token JWT do Identity Provider cấp để xác thực ở Gateway; sau khi nhà cung cấp xoay khóa ký, một số token hợp lệ bị từ chối vì bộ khóa công khai chưa được làm mới.
Nhóm bảo mật cấu hình OAuth2 Resource Server ở gateway; token có chữ ký hợp lệ nhưng thiếu scope cho endpoint chuyển tiền vẫn được chuyển tới backend.
Một API sử dụng TokenRelay để gửi access token tới microservice đích; khi đổi cấu hình client registration, backend nhận token không đúng audience và trả 401.
Doanh nghiệp dùng Gateway làm điểm xác thực tập trung; một route mới được thêm trực tiếp mà không áp dụng chính sách bảo mật nên endpoint nhạy cảm có thể truy cập ngoài ý muốn.
Một ứng dụng dựa vào header X-Authenticated-User do Gateway chèn để xác định người dùng; backend cũng có thể được gọi trực tiếp và tin header mà client tự tạo.
Nhóm phân quyền theo tenant ID trong token, nhưng route biến đổi header tenant dựa trên query parameter; người dùng gửi tenant khác vẫn đến được dữ liệu không thuộc quyền.
Gateway kiểm tra API key bằng backend xác thực; trong lúc hệ thống xác thực chậm, request tới cả endpoint công khai cũng bị giữ do filter áp dụng quá rộng.
Một đội triển khai cấu hình cho phép CORS từ nhiều origin; preflight OPTIONS bị bộ lọc JWT từ chối vì không có Authorization, khiến giao diện web không gọi API được.
Gateway có chức năng đăng nhập OAuth2 qua redirect; sau khi triển khai sau reverse proxy, redirect_uri được tạo bằng HTTP và hostname nội bộ nên Identity Provider từ chối.
Dịch vụ sử dụng cookie xác thực qua nhiều subdomain; Gateway rewrite cookie Domain không đồng nhất giữa route đăng nhập và route quản trị khiến trình duyệt không duy trì phiên.
Nhóm vận hành thêm Secure và SameSite cho cookie tại Gateway; callback đăng nhập từ một tên miền khác không mang cookie và người dùng phải xác thực lại liên tục.
Một Gateway chuyển tiếp thông tin user identity vào header cho backend; filter log request trước khi che dữ liệu làm token và mã định danh nhạy cảm lưu trong trace.
Một dịch vụ tải tài liệu có policy theo vai trò; Gateway xác thực đúng token nhưng vẫn cache response của người dùng quản trị và trả nội dung đó cho người dùng quyền thấp.
Hệ thống đa tenant có đường dẫn /tenant/{id}/api; Gateway chỉ kiểm token tồn tại nhưng không đối chiếu ID trên path với tenant trong claims nên xảy ra rò rỉ dữ liệu.
Nhóm chuyển việc kiểm tra quota từ backend lên API Gateway; một route nội bộ bypass quota nhưng vẫn được Internet truy cập qua host phụ không nằm trong danh sách hạn chế.
Gateway sử dụng RequestRateLimiter với Redis để giới hạn mỗi API key; khi KeyResolver trả giá trị trống cho request không đăng nhập, traffic không được áp hạn mức như dự kiến.
Một API miễn phí đặt giới hạn request theo IP; nhiều người dùng công ty đứng sau cùng NAT bị chia sẻ quota và bị trả 429 dù từng người dùng rất ít.
Nhóm cấu hình RedisRateLimiter cho các tenant có gói cước khác nhau; sau một thay đổi route ID, giới hạn cũ bị dùng cho gói trả phí và khách hàng liên tục bị chặn.
Đội vận hành cần cho phép đợt burst ngắn khi người dùng đăng nhập; cấu hình token bucket tại Gateway lại làm request bị chặn ngay sau vài lần gọi liên tiếp.
Một hệ thống có ba replica Gateway đều chia sẻ Redis; khi Redis quá tải, thời gian xác định rate limit tăng mạnh và các request API hợp lệ bị trễ trước khi tới backend.
Gateway áp dụng rate limiting theo user ID trong JWT; với các request dùng token service-account chung, nhiều ứng dụng đối tác bị dồn vào cùng một quota.
Nhóm thử nghiệm rate limit trên một pod Gateway; khi production có nhiều pod và kết nối tới Redis gián đoạn, kết quả cho phép hoặc chặn request khác nhau giữa các pod.
Một dịch vụ thanh toán cần phân biệt giới hạn traffic đọc và ghi; cấu hình rate limiter chung cho mọi HTTP method làm request đọc dữ liệu chiếm hết quota của giao dịch ghi.
Ứng dụng API Gateway trả 429 cho yêu cầu vượt hạn mức nhưng không có thông tin nhất quán về thời gian thử lại; các client tự động retry đồng loạt và tạo thêm tải.
Một tổ chức phân bổ quota theo plan khách hàng; dữ liệu plan thay đổi giữa kỳ nhưng KeyResolver và cấu hình rate limit chỉ lấy thông tin từ cache cũ.
Nhóm vận hành áp dụng circuit breaker cho route dịch vụ thanh toán; vài lỗi nghiệp vụ 400 bị coi là lỗi hệ thống khiến circuit mở dù backend vẫn khỏe.
Gateway gọi dịch vụ vận chuyển qua CircuitBreaker filter; khi backend lỗi liên tục, fallback endpoint trả dữ liệu dự phòng nhưng client không phân biệt được trạng thái từ nguồn thật và từ fallback.
Một API Gateway dùng fallbackUri nội bộ khi backend 503; fallback lại gọi một route của cùng backend đang lỗi, khiến nhiều request quay vòng qua Gateway.
Nhóm triển khai circuit breaker theo tên chung cho nhiều route; một dịch vụ thống kê lỗi liên tục kéo theo route đặt hàng bị ngắt do dùng chung trạng thái breaker.
Một hệ thống đối tác có latency dao động; ngưỡng slow-call của circuit breaker quá thấp khiến route tự ngắt vào giờ cao điểm dù đa số request cuối cùng vẫn thành công.
Gateway trả lỗi nhanh khi circuit breaker mở; dashboard của backend ghi giảm lỗi trong khi người dùng vẫn nhận nhiều response thất bại ngay tại gateway.
Nhóm dùng circuit breaker với timeout riêng nhưng timeout kết nối backend dài hơn; nhiều request vẫn chiếm connection pool ngay cả khi phía gateway đã trả lỗi.
Đội kỹ thuật định tuyến fallback tới một service trong cùng cluster; service dự phòng cũng phụ thuộc backend đã lỗi nên sự cố lan sang nhiều thành phần khác.
Một route cho phép Retry filter khi nhận 503; request tạo đơn qua POST được gửi lại sau timeout và backend tạo hai đơn vì lượt đầu thực tế đã commit.
Gateway dùng retry cho GET tra cứu sản phẩm; khi backend bị nghẽn, hàng nghìn request retry đồng thời làm hệ thống hồi phục chậm hơn.
Một dịch vụ có endpoint upload multipart; Retry filter cố phát lại request có body lớn sau lỗi upstream và bộ nhớ Gateway tăng vì dữ liệu phải được giữ để gửi lại.
Nhóm bật retry theo status 500 và 502; một lỗi validation trả 500 sai hợp đồng khiến request không hợp lệ bị thực hiện nhiều lần mà không thể thành công.
Dịch vụ đặt vé trả về 202 Accepted sau khi xếp hàng xử lý; Gateway hiểu sai tín hiệu này và một số client lại gửi yêu cầu vì tưởng giao dịch chưa hoàn tất.
Đội triển khai kết hợp retry với circuit breaker; sự cố ngắn làm số lần gọi backend tăng mạnh nhưng chỉ số request đến Gateway không phản ánh số lượt gọi thực tế.
Một route sử dụng backoff retry rất dài; timeout của client xảy ra trước khi các lần thử kết thúc khiến Gateway vẫn giữ request sau khi người dùng đã ngắt kết nối.
Nhóm bảo mật thêm circuit breaker fallback cho endpoint xác thực; khi nhà cung cấp danh tính lỗi, fallback trả response thành công mà không phản ánh trạng thái xác thực thực sự.
Gateway thêm Retry filter ở trước filter gắn idempotency key; mỗi lần retry nhận key khác nhau nên backend không nhận biết các request là cùng một thao tác.
Một dịch vụ truyền dữ liệu streaming trả được một phần response trước khi backend lỗi; Gateway không thể bắt đầu lại phản hồi mà không làm thay đổi nội dung client đã nhận.
Nhóm ứng dụng dùng TLS termination tại ingress và HTTP nội bộ tới Gateway; trong một số redirect, Gateway dùng scheme nội bộ và trình duyệt bị chuyển từ HTTPS sang HTTP.
Một API Gateway thiết lập TLS connector trực tiếp; sau khi đổi đường dẫn keystore được mount trong container, ứng dụng không thể bắt đầu phục vụ cổng HTTPS.
Dịch vụ thanh toán kết nối đến backend qua HTTPS với chứng chỉ CA nội bộ; một image mới không có truststore tương ứng khiến gateway trả 502 dù backend vẫn hoạt động.
Nhóm vận hành bắt buộc mutual TLS giữa Gateway và service tài chính; sau khi xoay client certificate, một số pod vẫn dùng chứng chỉ cũ và bị backend từ chối.
Một đối tác yêu cầu tên miền trong SNI phải trùng chứng chỉ backend; route dùng IP tĩnh nhưng Host header chứa tên khác khiến TLS handshake thất bại.
Gateway chạy sau hai lớp proxy và tin toàn bộ X-Forwarded-For do request cung cấp; một client cố ý sửa header làm hệ thống audit ghi sai IP nguồn.
Nhóm cấu hình Forwarded header để tạo URL công khai; khi proxy gửi cả Forwarded và X-Forwarded-Proto, phản hồi redirect đôi khi chứa hostname không được phép.
Đội vận hành giới hạn HTTP request body tại gateway để chống lạm dụng; một nhóm khách hàng gửi tệp hợp lệ nhận 413 trước khi đến backend có giới hạn lớn hơn.
Một API Gateway kiểm tra kích thước request theo Content-Length; client gửi body chunked không có độ dài khai báo làm hành vi giới hạn khác với các request thông thường.
Gateway đặt chính sách bảo mật cho header X-Frame-Options và Content-Security-Policy; một route tới ứng dụng web cũ gửi header mâu thuẫn khiến trang không hiển thị trong browser.
Nhóm triển khai HTTP/2 cho kết nối ngoài nhưng upstream chỉ nhận HTTP/1.1; khi tăng số stream đồng thời, người dùng thấy latency cao và dashboard không phân biệt hai tầng giao thức.
Một hệ thống yêu cầu dùng TLS 1.3 cho endpoint tài chính; policy của ingress khác policy tại Gateway khiến khách hàng cũ có thể kết nối ở lớp ngoài nhưng lỗi ở tầng kế tiếp.
Gateway phục vụ một số route WebSocket; sau khi bật TLS và proxy mới, kết nối wss được thiết lập nhưng ngắt khi có thời gian im lặng dài.
Một dịch vụ API Gateway phát metrics theo route ID; sau khi tự sinh route theo mỗi khách hàng, số lượng time series tăng nhanh và chi phí lưu metrics vượt dự toán.
Nhóm vận hành thấy p95 latency tăng trên route tìm kiếm; dashboard chỉ đo tổng thời gian Gateway mà không phân biệt thời gian xử lý filter, kết nối và xử lý downstream.
Một request đi qua Gateway và ba microservice; do header traceparent không được truyền đúng ở một route, traces bị tách thành nhiều chuỗi khó xác định nguyên nhân lỗi.
Đội tích hợp gắn correlation ID ở Gateway; một số request đi qua fallback hoặc timeout không có ID trong response khiến support không ghép được log với phản hồi khách hàng.
Một gateway ghi access log với URL đầy đủ; query parameter chứa token đăng nhập bị ghi nguyên dạng khiến thông tin bí mật xuất hiện trong hệ thống quan sát.
Nhóm giám sát chỉ có số HTTP 5xx từ backend; khi Gateway trả 429 hoặc mở circuit breaker, dashboard vẫn báo backend khỏe trong khi người dùng không truy cập được dịch vụ.
Một route dùng dynamic URI từ service discovery; khi backend đổi IP trong đợt rolling deployment, trace không ghi instance đích nên đội vận hành không xác định được pod trả lỗi.
Nhóm debug một request 404 bằng log của backend nhưng không thấy request; thực tế route predicate không khớp và Gateway trả response trước khi chuyển tiếp.
Một Gateway được cấu hình quan sát request body để điều tra lỗi; filter log gom dữ liệu streaming và tạo áp lực bộ nhớ khi nhiều request dung lượng lớn chạy đồng thời.
Đội phát triển thay đổi thứ tự filter thêm request ID và filter kiểm tra chữ ký; logs ghi chữ ký không hợp lệ nhưng không thể xem payload gốc hay header trước khi bị biến đổi.
Một gateway có actuator endpoint hiển thị route nhưng bị khóa sau deployment; nhóm vận hành không xác minh được cấu hình route đang áp dụng trong incident.
Ứng dụng cập nhật route động từ kho cấu hình; sau khi publish thay đổi, một số replica Gateway vẫn dùng định nghĩa route cũ khiến cùng request có kết quả khác nhau giữa pod.
Nhóm xóa route tới dịch vụ đã ngừng vận hành nhưng chưa làm mới route cache; request vẫn được chuyển tới service ID không còn instance và trả lỗi tải dịch vụ.
Đội phát hành thay route theo cấu hình profile production; staging test đạt nhưng production route khác do một biến môi trường có độ ưu tiên cao ghi đè đích upstream.
Nhóm thử nghiệm canary với Weight predicate; khi tăng trọng số lưu lượng lên phiên bản mới, lỗi chỉ tăng cho những request có header tùy chọn mà bộ test route chưa bao phủ.
Gateway dùng RouteDefinitionRepository để cập nhật định nghĩa khi chạy; một lần ghi cấu hình lỗi khiến một route biến mất tạm thời dù những route khác vẫn bình thường.
Một ứng dụng cần hỗ trợ cả HTTP và HTTPS tới upstream; cấu hình route cũ vẫn sử dụng scheme HTTP sau khi backend bật HTTPS bắt buộc và liên tục trả lỗi kết nối.
Nhóm triển khai custom GatewayFilterFactory cho API đối tác; sau khi nâng cấp Spring Cloud, tên tham số cấu hình filter bị thay đổi và một route không còn được áp dụng đúng.
Đội QA chỉ thử predicate Path bằng request thành công; khi thêm Host, Method và Header predicates, các request không khớp vẫn chưa được kiểm tra trong contract test Gateway.
Nhóm dùng WebTestClient với mock backend để kiểm RewritePath; bài test đạt nhưng khi chạy qua ingress thật, prefix bị thay đổi hai lần và backend trả 404.
Ứng dụng kiểm thử RequestRateLimiter bằng một instance Gateway; khi chạy nhiều replica với Redis thật, các khách hàng dùng chung quota bất ngờ bị từ chối dưới tải.
Nhóm mô phỏng circuit breaker với backend luôn trả 503; hành vi khi backend chậm dần nhưng vẫn trả 200 không được kiểm tra nên trạng thái breaker lệch dự kiến.
Đội phát triển kiểm thử Retry filter với GET an toàn nhưng không có test cho POST có side effect; một đợt timeout ở production tạo giao dịch trùng không được phát hiện trước release.
Nhóm QA chạy load test Gateway trên máy phát triển với kết nối keep-alive ổn định; ở production hàng nghìn kết nối mới liên tục làm lỗi connect timeout mà báo cáo test không phản ánh.
Ứng dụng chạy gateway sau load balancer có health probe chỉ gọi /actuator/health; route discovery đang lỗi nhưng pod vẫn được đánh dấu ready và tiếp tục nhận traffic.
Nhóm vận hành dùng liveness probe phụ thuộc vào một microservice phía sau; khi service này ngừng ngắn hạn, các pod Gateway bị restart hàng loạt dù gateway vẫn có thể phục vụ route khác.
Gateway nhận SIGTERM trong rolling deployment; load balancer tiếp tục gửi request mới tới pod đang đóng khiến một số giao dịch nhận connection reset dù backend không lỗi.
Ứng dụng có các kết nối WebSocket và SSE kéo dài; quá trình graceful shutdown chờ lâu hơn thời gian dừng pod làm phiên realtime bị cắt trước khi phát sự kiện cuối.
Nhóm đặt thời gian graceful shutdown nhỏ hơn response timeout hợp lệ của dịch vụ báo cáo; khi deploy bản mới, nhiều khách hàng nhận file tải xuống không đầy đủ.
Đội vận hành rollback phiên bản Gateway sau khi lỗi xác thực tăng; bản cũ dùng cấu hình routing tới service đã đổi tên khiến traffic vẫn không trở lại bình thường.

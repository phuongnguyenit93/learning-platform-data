Một dịch vụ đặt hàng Spring Boot đóng gói JAR chạy Tomcat nhúng tại cổng 8080; sau khi triển khai chung máy với ứng dụng khác, tiến trình không khởi động vì cổng HTTP đã bị chiếm.
Nhóm vận hành chuyển ứng dụng MVC từ JAR có máy chủ nhúng sang gói WAR chạy trên servlet container bên ngoài; đường dẫn context path thay đổi khiến các URL được đối tác lưu trước đó trả 404.
Một API nội bộ cấu hình server.address chỉ lắng nghe địa chỉ loopback; trong container, readiness probe cục bộ thành công nhưng request từ load balancer không thể kết nối.
Ứng dụng dùng hai cổng web và management riêng; sau khi bật firewall ở production, endpoint nghiệp vụ vẫn hoạt động nhưng hệ thống giám sát không truy cập được cổng Actuator.
Một dự án có cả Spring MVC và Spring WebFlux trên classpath; nhóm tưởng ứng dụng đã chạy theo reactive web server nhưng log khởi động lại cho thấy mô hình web runtime khác dự kiến.
Đội phát triển đổi embedded Tomcat sang Jetty để đáp ứng tiêu chí vận hành; một số servlet filter và cấu hình connector cũ không còn áp dụng như trước.
Một ứng dụng dùng embedded Undertow trong môi trường thử nghiệm nhưng image production vẫn chứa dependency Tomcat; số lượng thread và hành vi giới hạn request khác giữa hai môi trường.
Nhóm chuyển API WebFlux từ Netty sang một web runtime khác; cấu hình timeout và connection pool trước đây không còn phản ánh đúng đường xử lý request hiện tại.
Dịch vụ bán vé nhận lưu lượng đột biến ngay sau một chương trình khuyến mãi; web server mở cổng thành công nhưng accept queue đầy và nhiều kết nối mới bị từ chối.
Một API phục vụ báo cáo có connector HTTP giới hạn số kết nối quá thấp; khi tải tăng, kết nối chờ bị dồn lại dù mức CPU của ứng dụng vẫn còn thấp.
Nhóm triển khai đặt số worker thread trong thread pool Tomcat bằng một giá trị nhỏ để tiết kiệm bộ nhớ; các request đồng bộ gọi database lâu làm toàn bộ endpoint khác chờ thread.
Ứng dụng dùng servlet thread pool lớn hơn khả năng của database connection pool; khi nhiều request đến đồng thời, phần lớn thread bị chặn chờ lấy kết nối thay vì xử lý nghiệp vụ.
Dịch vụ đối soát tạo tác vụ CPU nặng trực tiếp trong controller MVC; khi đợt tính toán chạy, p99 latency của các request nhẹ tăng dù không có lỗi HTTP rõ ràng.
Một ứng dụng Spring MVC xử lý upload file trên servlet worker thread; khách gửi file qua mạng chậm làm các thread bị giữ lâu và request tra cứu thông thường bị trễ.
Nhóm cấu hình connector với keep-alive timeout rất ngắn; client di động thường bị ngắt kết nối khi tái sử dụng HTTP connection sau khoảng nghỉ.
Ứng dụng có giới hạn số request trên một keep-alive connection; sau khi đổi cấu hình proxy, client nhận nhiều lỗi đóng kết nối khi gửi các request liên tiếp.
Một dịch vụ HTTP đặt thời gian chờ nhận request header quá cao; hàng nghìn kết nối gửi header từng phần chiếm tài nguyên server trong thời gian dài.
Đội vận hành đặt giới hạn request header thấp để giảm rủi ro; request có cookie xác thực lớn bị từ chối trước khi đến controller trong khi request không đăng nhập vẫn thành công.
Máy chủ nhúng ghi access log ở thư mục tạm của container; sau khi chuyển sang filesystem chỉ đọc, ứng dụng khởi động được nhưng không ghi được nhật ký truy cập.
Nhóm bật HTTP response compression cho API trả dữ liệu lớn; CPU tăng khi nhiều client yêu cầu phản hồi nén dù băng thông mạng giảm đáng kể.
Một API streaming trả dữ liệu từng phần nhưng reverse proxy giữ buffer response; người dùng chỉ nhìn thấy nội dung sau khi luồng kết thúc, dù server đã gửi từng chunk.
Ứng dụng có nhiều filter xử lý xác thực, correlation ID và nén; trong một số request, filter ghi body để log khiến controller không còn đọc đủ request body.
Một filter servlet đo thời gian request bằng ThreadLocal; khi xử lý async dispatch, kết quả đo thiếu phần thời gian chờ và correlation ID đôi khi biến mất khỏi log.
Một ứng dụng thêm OncePerRequestFilter để cấp quyền; cùng request đi qua error dispatch nhưng bước kiểm tra không được thực thi như nhóm bảo mật kỳ vọng.
Dịch vụ dùng nhiều servlet filter có thứ tự khác nhau giữa test và production; bộ lọc ghi log quan sát body trước bộ lọc che thông tin nhạy cảm, khiến dữ liệu riêng tư xuất hiện trong nhật ký.
Một request HTTP đi qua servlet container, DispatcherServlet và controller; khi một filter từ chối request, nhóm hỗ trợ chỉ tìm log của controller nên không phát hiện nguyên nhân trả 403.
Nhóm đăng ký một servlet tùy biến với đường dẫn chồng lên DispatcherServlet; một số URL trước đây vào controller MVC nay đi qua servlet mới và trả định dạng không tương thích.
Ứng dụng dùng HandlerInterceptor để ghi thời gian xử lý MVC; sau khi controller chuyển sang xử lý bất đồng bộ, số lần callback và thời điểm hoàn tất khác với kết quả metric đang giả định.
Một API có hai handler mapping với pattern đường dẫn gần giống; request chứa dấu chấm trong mã sản phẩm được chuyển tới handler khác so với dự kiến.
Dịch vụ chuyển cấu hình path matching giữa các phiên bản Spring; endpoint có dấu gạch chéo cuối URL thay đổi cách match và nhiều client cũ bắt đầu nhận 404.
Một ứng dụng dùng servlet context path cho tất cả endpoint; sau khi triển khai sau gateway đã thêm path prefix, đường dẫn thực tế bị lặp hai lần prefix.
Một controller MVC nhận yêu cầu có tham số query được mã hóa URL; dữ liệu chứa dấu cộng và khoảng trắng được decode khác dự kiến, khiến bộ lọc tìm kiếm bỏ sót kết quả.
Dịch vụ thương mại điện tử nhận path variable có ký tự slash được percent-encode; servlet container từ chối hoặc chuẩn hóa URL trước khi request được chuyển đến controller.
Một API có ControllerAdvice xử lý lỗi nghiệp vụ nhưng lỗi vượt giới hạn request header xảy ra tại connector; khách hàng nhận response không giống mẫu lỗi chuẩn của ứng dụng.
Nhóm đổi bộ xử lý lỗi mặc định của Spring Boot; endpoint không tồn tại trả trang HTML cho một client chỉ chấp nhận JSON, khiến ứng dụng di động không hiển thị được thông báo.
Ứng dụng muốn ghi correlation ID cho mọi lỗi HTTP; các lỗi phát sinh trước khi DispatcherServlet chạy không đi qua cơ chế log đang đặt trong interceptor MVC.
Một controller trả ResponseEntity với status đúng nhưng body không được ghi xong vì client đóng kết nối; hệ thống chỉ đếm status 200 ở server mà không nhận ra tải xuống bị ngắt.
Dịch vụ trả file theo HTTP Range để hỗ trợ tải tiếp; sau khi đổi cấu hình reverse proxy, request có header Range bị bỏ qua và client tải lại toàn bộ file lớn.
Nhóm cấu hình cache header cho tệp tĩnh; khi deploy giao diện mới, trình duyệt vẫn dùng tài nguyên JavaScript cũ vì chính sách cache không phù hợp với cách đặt tên file.
Một ứng dụng có static resources và endpoint API cùng tên đường dẫn; sau khi thêm tài nguyên mới, một số request được phục vụ bởi resource handler thay vì controller.
Dịch vụ báo cáo chuyển MVC handler sang Callable để tránh giữ servlet request thread; TaskExecutor xử lý tác vụ bất đồng bộ hết khả năng nhận việc và những request đầu vào bắt đầu timeout.
Một controller MVC dùng DeferredResult để trả kết quả khi message đến từ broker; khi message không đến, request tồn tại quá lâu và timeout diễn ra ở tầng khác với thời gian chờ ứng dụng.
Ứng dụng trả ResponseBodyEmitter cho báo cáo nhiều phần; client ngắt giữa chừng nhưng tác vụ tạo dữ liệu vẫn tiếp tục tiêu tốn CPU và bộ nhớ.
Nhóm dùng SseEmitter phát cập nhật trạng thái đơn hàng; sau khi gateway có idle timeout ngắn, client liên tục reconnect dù server không phát hiện lỗi nghiệp vụ.
Một endpoint Spring MVC dùng CompletableFuture rồi truy cập request-scoped bean trong worker thread; dữ liệu request không có mặt ở luồng phụ như khi chạy đồng bộ.
Ứng dụng phát multipart response từ servlet khi xuất nhiều tệp; một exception xảy ra sau khi response đã commit khiến hệ thống không thể đổi sang mã lỗi JSON chuẩn.
Một dịch vụ WebFlux dùng Reactor Netty xử lý hàng nghìn kết nối đồng thời; một đoạn code chặn khi gọi API ngoài được đặt trên event-loop và làm thời gian phản hồi của nhiều request tăng mạnh.
Nhóm chuyển ứng dụng từ Spring MVC sang WebFlux nhưng vẫn gọi repository JDBC đồng bộ trong handler; dù endpoint trả Mono, tài nguyên event-loop vẫn bị giữ khi database chậm.
Một handler WebFlux gọi block để lấy kết quả của Mono trong luồng xử lý request; lỗi runtime chỉ xuất hiện dưới tải khi lời gọi này chạy trên non-blocking thread.
Ứng dụng trả Flux gồm nhiều bản ghi nhưng client chỉ đọc từng ít phần tử; một nguồn dữ liệu không tôn trọng backpressure làm bộ đệm phía server tăng liên tục.
Một API nhận upload lớn qua WebFlux DataBuffer; khi pipeline dừng vì lỗi kiểm tra dữ liệu, buffer chưa được giải phóng đúng cách và bộ nhớ trực tiếp tăng dần.
Nhóm xử lý WebFlux map các phần tử với flatMap gọi dịch vụ ngoài; thứ tự response thay đổi so với thứ tự yêu cầu trong batch và khách hàng ghi nhận bản cập nhật lệch trình tự.
Ứng dụng Netty có một handler tính toán mã hóa CPU nặng; khi nhiều request đến, số event-loop thread nhỏ trở thành nút thắt dù database và mạng chưa hết khả năng.
Một WebFlux handler trả Mono.empty khi không tìm thấy hồ sơ; sau khi đổi logic, client nhận status thành công với body rỗng thay vì hợp đồng API được ghi trong tài liệu.
Dịch vụ reactive chuyển lỗi từ publisher sang onErrorResume; kết quả fallback hợp lệ nhưng mã HTTP của lỗi hệ thống bị thay bằng phản hồi thành công, làm dashboard tỷ lệ lỗi sai lệch.
Một API WebFlux dùng Context để truyền trace ID qua nhiều operator; sau khi thêm adapter từ thư viện dùng ThreadLocal, ID có lúc bị mất khi scheduler chuyển luồng.
Một endpoint WebFlux dùng ServerSentEvent để phát thông báo; khi client rớt mạng, subscription upstream không được hủy và tiếp tục giữ tài nguyên từ nguồn dữ liệu.
Một ứng dụng xử lý HTTP streaming từ đối tác bằng WebClient; response được chuyển tiếp ngay nhưng gateway phía trước gom buffer khiến thời gian đến phần tử đầu tiên tăng đáng kể.
Nhóm dùng timeout của Netty cho request streaming tồn tại hàng phút; các kết nối hợp lệ bị đóng khi khoảng im lặng giữa hai sự kiện dài hơn cấu hình.
Một handler reactive tiêu thụ file bằng DataBuffer rồi chuyển sang API blocking; khi số lượng upload đồng thời tăng, boundedElastic scheduler đầy và hệ thống trả timeout.
Ứng dụng WebFlux kết hợp zip của hai Mono để tạo phản hồi; một nguồn hoàn tất rỗng khiến toàn bộ publisher không phát dữ liệu dù nguồn còn lại đã có thông tin.
Một dịch vụ có cả filter Servlet và WebFilter reactive; nhóm triển khai cấu hình xác thực trong servlet filter nhưng request WebFlux không đi qua thành phần họ đang theo dõi.
Nhóm dùng exception handler riêng của WebFlux nhưng cài đặt theo cách của Spring MVC; lỗi phát sinh trong publisher được chuyển thành response mặc định không như client mong đợi.
Một API REST gửi JSON có thuộc tính ngày giờ và múi giờ; Jackson serializer ở một môi trường cho ra timestamp khác định dạng mà ứng dụng di động đã tích hợp.
Dịch vụ nhận JSON có field mới từ đối tác; một thay đổi cấu hình Jackson khiến unknown property gây lỗi 400 thay vì được ứng dụng xử lý như trước.
Một API có DTO chứa số tiền Decimal; khi client gửi số rất lớn, quá trình deserialize thành kiểu số không phù hợp làm mất độ chính xác trước khi tới business service.
Nhóm triển khai sử dụng ObjectMapper tùy chỉnh; sau khi thêm cấu hình converter, định dạng ngày trong JSON của endpoint MVC và WebFlux khác nhau giữa hai đường xử lý.
Một client gọi API với Content-Type không được hỗ trợ; request bị từ chối ở bước chọn HttpMessageConverter trước khi logic xác thực dữ liệu trong controller chạy.
Ứng dụng hỗ trợ cả JSON và XML; một request gửi Accept có nhiều media type khiến server chọn định dạng phản hồi khác dự đoán của nhóm tích hợp.
Nhóm cài custom codec WebFlux cho payload nhị phân; dữ liệu nhỏ được giải mã đúng nhưng bản ghi lớn bị cắt do giới hạn bộ nhớ giải mã.
Một endpoint WebFlux dùng codec JSON để gom một mảng hàng chục nghìn phần tử; limit maxInMemorySize bị vượt và lỗi xảy ra trước khi dữ liệu được chuyển vào handler.
Ứng dụng tăng giới hạn codec để nhận request lớn; khi nhiều client gửi JSON khổng lồ đồng thời, lượng heap sử dụng tăng mạnh và tiến trình bị OOM.
Dịch vụ truyền văn bản chứa emoji và ký tự tiếng Việt; charset giữa Content-Type và cách client encode body không nhất quán khiến dữ liệu được lưu thành ký tự lỗi.
Một API trả lỗi bằng application/problem+json nhưng một client cũ chỉ chấp nhận application/json; sau khi thay exception handler, client không parse được thông tin lỗi.
Nhóm cấu hình HTTP message converter cho CSV; một số response chứa dấu phẩy trong trường dữ liệu nhưng không escape đúng, làm file tải về sai cột.
Ứng dụng bật CORS cho giao diện quản trị; preflight OPTIONS từ trình duyệt bị từ chối trước khi đến controller nên chức năng gọi API khác domain không hoạt động.
Một service dùng CORS wildcard với cookie xác thực; trình duyệt không gửi thông tin đăng nhập như thiết kế dù gọi API bằng công cụ dòng lệnh vẫn thành công.
Nhóm điều chỉnh thứ tự CORS filter và security filter; request preflight không có cookie bị xử lý như request chưa xác thực, khiến giao diện SPA báo lỗi ngẫu nhiên.
Ứng dụng chạy sau CDN và reverse proxy; URL và scheme dùng để tạo redirect được lấy từ kết nối HTTP nội bộ thay vì HTTPS bên ngoài, làm trình duyệt chuyển tới địa chỉ không an toàn.
Máy chủ Spring Boot đặt sau ingress có path prefix; URL tự tạo trong response thiếu phần prefix bên ngoài nên các đường dẫn callback OAuth không khớp cấu hình.
Nhóm bật xử lý forwarded headers từ mọi nguồn; client Internet có thể tự gửi X-Forwarded-Proto giả để làm thay đổi URL hoặc kiểm tra yêu cầu bảo mật.
Ứng dụng đặt sau hai lớp proxy; X-Forwarded-For chứa nhiều địa chỉ IP và bộ lọc giới hạn truy cập nhầm IP của proxy thành địa chỉ người dùng.
Một dịch vụ tạo absolute URL để gửi email xác nhận; khi TLS được terminate tại load balancer, link sinh ra dùng cổng 8080 nội bộ thay vì tên miền công khai.
Nhóm đổi cấu hình ForwardedHeaderFilter trong Spring MVC; một số request có header Forwarded chuẩn RFC và X-Forwarded-* đồng thời cho kết quả host khác nhau.
Một ứng dụng dùng HSTS và cookie Secure để bảo vệ đăng nhập; vì web server chỉ thấy HTTP từ ingress, cookie được đặt không đúng thuộc tính khi sinh phản hồi.
Dịch vụ Spring Boot phục vụ TLS trực tiếp trên connector; sau khi rotate keystore, máy chủ vẫn sử dụng chứng chỉ cũ trong những kết nối mới cho tới đợt triển khai tiếp theo.
Ứng dụng được cấu hình HTTPS bằng PKCS12 keystore; trong container mới, file chứng chỉ được mount vào đường dẫn khác làm connector TLS không khởi tạo được.
Nhóm vận hành bỏ phiên bản TLS lỗi thời trên ingress nhưng connector nội bộ vẫn cho phép protocol không phù hợp; báo cáo kiểm toán phát hiện hai tầng có chính sách khác nhau.
Một client doanh nghiệp chỉ hỗ trợ một nhóm cipher suite cũ; sau nâng cấu hình TLS của server, request tới API thất bại trong handshake trước khi có access log ở controller.
Ứng dụng yêu cầu mutual TLS cho một endpoint đối tác; nhóm chỉ đặt xác thực chứng chỉ ở load balancer nhưng service lại tin header định danh do client có thể giả mạo.
Đội kỹ thuật chuyển service từ HTTP sang HTTPS nhưng readiness probe vẫn gọi endpoint qua giao thức cũ; pod liên tục bị đánh dấu không sẵn sàng dù endpoint chính đã hoạt động.
Một hệ thống web bật HTTP/2 tại proxy nhưng backend Spring Boot chỉ nhận HTTP/1.1; dashboard gắn nhãn mọi kết nối là HTTP/2 nên nhóm hiểu sai đặc tính kết nối phía server.
Nhóm cấu hình HTTP/2 trên connector TLS của web server; một số client cũ lỗi khi thương lượng ALPN và không thể truy cập dù thiết bị mới chạy bình thường.
Ứng dụng có giới hạn body ở tầng proxy nhỏ hơn giới hạn multipart của Spring Boot; người dùng tải file lớn nhận 413 trước khi controller được gọi, khiến log nghiệp vụ không ghi nhận sự cố.
Dịch vụ nhận multipart upload gồm nhiều tệp; tổng dung lượng hợp lệ nhưng một phần riêng lẻ vượt giới hạn max-file-size khiến toàn request thất bại.
Nhóm giới hạn số lượng phần của multipart form để tránh lạm dụng; một biểu mẫu hợp lệ chứa nhiều trường nhỏ bị từ chối khi nâng phiên bản servlet container.
Một API nhận file tạm để xử lý; thư mục multipart temporary storage của container đầy ổ đĩa nên upload bị lỗi dù ổ chứa kết quả đầu ra vẫn còn dung lượng.
Dịch vụ đặt session người dùng trong bộ nhớ Tomcat; sau khi tăng replica và bật round-robin load balancing, người dùng phải đăng nhập lại khi request đến instance khác.
Ứng dụng sử dụng Spring Session lưu phiên trên Redis; Redis tạm thời mất kết nối khiến request HTTP lỗi ở bước đọc session trước khi vào controller nghiệp vụ.
Một cổng quản trị thay đổi session timeout giữa các profile; sau khi deploy production, phiên người dùng hết hạn sớm hơn hợp đồng vì đơn vị thời gian cấu hình không được hiểu như dự định.
Nhóm vận hành lưu một đối tượng lớn trong HttpSession cho mỗi người dùng; khi lượng đăng nhập tăng, heap của các pod bị chiếm nhiều dù lưu lượng request không thay đổi đáng kể.
Dịch vụ đăng nhập chuyển session ID sau khi xác thực; client dùng cookie từ phiên cũ cho các request song song và thỉnh thoảng nhận 401 ngay sau đăng nhập.
Một ứng dụng có cookie session với SameSite=Lax; khi tích hợp login bằng redirect từ tên miền đối tác, một số luồng callback không mang cookie như nhóm sản phẩm kỳ vọng.
Nhóm cấu hình session cookie domain cho nhiều subdomain; một lỗi cấu hình làm cookie được gửi tới dịch vụ khác không thuộc phạm vi xác thực dự kiến.
Ứng dụng dùng session affinity ở load balancer để giữ phiên trên một pod; khi pod được thay thế, người dùng bị mất phiên và thao tác đang thực hiện phải bắt đầu lại.
Một API stateless vẫn tạo HttpSession vì một thành phần web vô tình gọi getSession; nhiều phiên rỗng được lưu và cookie được trả về ở các endpoint không cần trạng thái.
Dịch vụ khách hàng xử lý request cùng session trên nhiều luồng; hai thao tác sửa giỏ hàng đồng thời đọc cùng trạng thái cũ và ghi đè kết quả của nhau.
Nhóm triển khai thiết lập max-http-request-header-size rất cao để giữ cookie lớn; kẻ gửi request với header dài làm connector tiêu tốn tài nguyên đáng kể khi tải tăng.
Một public API chưa giới hạn tốc độ request tại ingress; hàng nghìn kết nối ngắn từ một nguồn làm đầy hàng chờ connector và request hợp lệ bị chậm.
Ứng dụng cấu hình connection timeout phù hợp tải thường ngày; trong sự cố mạng di động, nhiều request body gửi dở dang giữ kết nối lâu khiến số socket khả dụng giảm.
Đội vận hành tăng max connections sau khi xảy ra timeout; database và downstream không mở rộng tương ứng nên số request đang xử lý tăng mà throughput thực không cải thiện.
Một API WebFlux phát dữ liệu streaming không giới hạn tốc độ; khách hàng có kết nối chậm khiến các bộ đệm phía gateway và server tăng trong giờ cao điểm.
Nhóm giám sát chỉ có metric HTTP request count và status code; khi p95 latency tăng sau thay đổi cấu hình connector, họ không biết thời gian tiêu tốn ở hàng đợi thread hay handler nghiệp vụ.
Ứng dụng ghi access log nhưng không có trace ID kết nối với log controller; khi lỗi 502 xảy ra tại proxy, đội vận hành không lần được request tương ứng qua nhiều tầng.
Một dịch vụ WebFlux chuyển scheduler giữa các operator; trace bị đứt sau đoạn xử lý bất đồng bộ nên dashboard xem một request thành nhiều đoạn không liên quan.
Nhóm theo dõi số lượng thread Tomcat nhưng không giám sát số kết nối đang chờ hoặc queue của executor; khi load test, throughput giảm dù chỉ số CPU thấp.
Một hệ thống chỉ đo thời gian hoàn tất response streaming; trải nghiệm chờ dữ liệu đầu tiên xấu đi sau đổi reverse proxy nhưng dashboard latency vẫn cho thấy các request nhanh.
Ứng dụng bật actuator readiness ngay khi server bind cổng; một callback nạp cache vẫn chạy và các request đến sớm nhận dữ liệu thiếu dù health trả UP.
Nhóm triển khai đặt liveness probe phụ thuộc vào một API đối tác; khi đối tác lỗi ngắn, Kubernetes restart nhiều pod Spring Boot dù web runtime bên trong không bị treo.
Một API đặt hàng chạy rolling deployment; load balancer vẫn gửi request mới tới pod vừa nhận SIGTERM và một số thao tác chưa hoàn tất bị ngắt kết nối.
Ứng dụng Spring MVC bật graceful shutdown với thời gian chờ ngắn; một request tải báo cáo kéo dài hơn khoảng chờ nên client nhận tệp thiếu sau khi deploy bản mới.
Dịch vụ WebFlux có các subscription streaming kéo dài hàng giờ; khi server shutdown, nhóm vận hành không biết cách phân biệt response đang hoạt động và subscription không còn client để quản lý thời hạn đóng.
Nhóm triển khai tăng thời gian graceful shutdown trong Spring Boot nhưng terminationGracePeriodSeconds của Kubernetes vẫn thấp hơn; tiến trình bị kill trước khi các HTTP request đang xử lý xong.
Một ứng dụng dùng executor riêng phục vụ request bất đồng bộ; khi đóng ApplicationContext, executor bị dừng trước khi response được ghi hết và nhiều client nhận connection reset.
Nhóm vận hành nhận thấy server báo không còn nhận request mới nhưng WebSocket và SSE connection cũ vẫn tồn tại; thời gian shutdown tăng không dự đoán được trong những đợt triển khai đông người dùng.
Ứng dụng hỗ trợ HTTP keep-alive qua proxy; sau khi bắt đầu shutdown, proxy tiếp tục gửi request mới trên kết nối đã tồn tại và phát sinh lỗi xen kẽ khó tái hiện.
Một dịch vụ phải flush dữ liệu audit sau mỗi request; khi container bị SIGKILL trước khi xử lý xong, log access ghi status thành công nhưng thao tác audit tương ứng không có ở hệ thống đích.
Nhóm kiểm thử Spring MVC bằng MockMvc với bộ điều khiển đơn lẻ; ở production, lỗi xảy ra tại connector khi header quá lớn nên các test controller đều đạt mà request thật bị từ chối.
Bộ test WebFlux dùng WebTestClient kết nối controller trong bộ nhớ; khi chạy server Netty thật, lỗi cấu hình TLS, idle timeout và codec giới hạn không xuất hiện trong bộ test này.
Đội QA so sánh hành vi MVC và WebFlux bằng cùng contract test; một endpoint lỗi trả status và content type khác nhau giữa hai runtime dù DTO nghiệp vụ giống nhau.
Ứng dụng load test chỉ gửi HTTP request ngắn với JSON nhỏ; sau khi chuyển sang production, các kết nối chậm, multipart lớn và response streaming gây quá tải ngoài kịch bản đã đo.
Nhóm kiểm thử tải với số virtual user cố định; kết quả thông lượng tốt nhưng không đo queue wait hay tỷ lệ lỗi kết nối khi số request đồng thời tăng đột biến.
Một dịch vụ API có cả endpoint nhanh và endpoint trả báo cáo chậm; test tổng hợp p95 che khuất tình trạng starvation của servlet worker thread khi hai loại traffic trộn vào nhau.
Ứng dụng Spring Boot có profile cấu hình connector khác nhau ở staging và production; bản build giống nhau nhưng một sai lệch max threads và timeout chỉ bộc lộ khi traffic production cao.
Đội vận hành rollback image web runtime sau khi tăng lỗi kết nối; phiên bản cũ dùng cấu hình forwarded headers khác với ingress mới nên redirect và cookie vẫn không đúng sau rollback.

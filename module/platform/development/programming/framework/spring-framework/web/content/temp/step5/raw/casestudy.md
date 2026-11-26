Một hệ thống thương mại điện tử dùng Spring MVC xử lý đơn hàng qua DispatcherServlet; sau khi thêm một servlet mapping mới, request API đôi khi không đi qua các controller đã đăng ký.
Nhóm chuyển một ứng dụng MVC từ cấu hình XML sang Java configuration; HandlerMapping của module cũ vẫn được tạo và cùng đường dẫn có hai handler ứng viên.
Ứng dụng bán vé dùng @RequestMapping ở class và @GetMapping ở method; một thay đổi tiền tố API khiến endpoint mobile cũ nhận 404 dù controller bean vẫn tồn tại.
Đội phát triển tạo hai @GetMapping cùng path nhưng khác tên tham số Java; Spring báo mapping mơ hồ khi khởi động và toàn bộ ứng dụng không ready.
Nhóm định nghĩa đường dẫn chứa biến orderId trong @PathVariable; một client gửi mã có dấu chấm và ký tự được mã hóa khiến giá trị controller nhận khác mã định danh ban đầu.
Một hệ thống giao vận dùng path pattern cho tuyến giao hàng; khi chuyển cách so khớp URL giữa các phiên bản Spring, một số đường dẫn có dấu gạch chéo cuối bị xử lý khác.
Đội tạo API phân cấp thư mục với wildcard path; đường dẫn gồm nhiều segment không đi tới handler cũ sau khi bật chiến lược PathPatternParser.
Ứng dụng xác định tenant từ subdomain bằng điều kiện Host ở gateway; controller vẫn dùng cùng @RequestMapping mà không kiểm tenant ở phía ứng dụng, dẫn tới truy cập nhầm dữ liệu.
Nhóm cấu hình @RequestMapping(params) để phân biệt hai thao tác tìm kiếm; khi request có cả hai tham số, Spring chọn handler khác thiết kế của hợp đồng API.
Ứng dụng có hai @PostMapping cùng URL nhưng consumes JSON và form data; đối tác gửi Content-Type không chính xác và nhận 415 dù body trông giống JSON.
Đội sử dụng produces trong @GetMapping để trả JSON và XML; client gửi Accept với nhiều media type khiến ContentNegotiation chọn định dạng ngoài dự tính.
Nhóm triển khai @RequestMapping(headers) để phân biệt phiên bản API; một reverse proxy bỏ header custom làm request rơi vào handler lỗi 404.
Ứng dụng quản lý đơn dùng @DeleteMapping nhưng client cũ gửi POST để xóa; endpoint trả 405 và monitoring nhầm thành sự cố database.
Đội tích hợp dựa vào HEAD để kiểm tài nguyên; bộ controller chỉ được test với GET nên header Content-Length của phản hồi HEAD không đúng như client mong đợi.
Một dịch vụ tệp đính kèm phải xử lý OPTIONS cho CORS; filter và controller cùng khai báo phản hồi khiến preflight nhận danh sách phương thức không chính xác.
Nhóm viết controller có tên path variable là id nhưng method argument được đổi thành productId; thiếu metadata ánh xạ làm binding thất bại ở request đầu tiên.
Ứng dụng hỗ trợ nhiều phiên bản API dưới /v1 và /v2; cùng một service bean nhận payload hai schema nhưng đường mapping chưa phân tách rõ các hành vi khác nhau.
Đội chuyển servlet context path từ gốc sang /platform; link Location trong response vẫn dùng path tuyệt đối cũ và client mở tài nguyên mới nhận 404.
Nhóm cấu hình ForwardedHeaderFilter sau proxy HTTPS; URL tự sinh trong response có scheme HTTP khiến ứng dụng mobile từ chối chuyển hướng.
Ứng dụng dùng @MatrixVariable để nhận nhiều lựa chọn sản phẩm; proxy và cấu hình path matching xử lý dấu chấm phẩy khác nhau nên một số tham số mất trên đường đi.
Đội triển khai controller nhận trạng thái bằng @RequestParam enum; client gửi giá trị khác chữ hoa và nhận 400 dù trước đó API cho phép kiểu viết không phân biệt.
Nhóm dùng @RequestParam cho page và size với defaultValue; khi client gửi chuỗi rỗng hoặc giá trị âm, truy vấn tạo offset không hợp lệ.
Ứng dụng dùng @RequestHeader để đọc correlation ID; một proxy thay đổi tên header khiến trace giữa HTTP request và database audit bị đứt.
Đội sử dụng @CookieValue để đọc mã giỏ hàng; trình duyệt mới hạn chế cookie bên thứ ba nên người dùng bị tạo giỏ hàng mới mỗi request.
Nhóm lưu thông tin lựa chọn ngôn ngữ trong @SessionAttributes; cùng session mở hai tab giao diện khiến trạng thái form tab trước bị ghi đè.
Ứng dụng có @ModelAttribute xây dữ liệu dùng chung cho mọi trang; method truy vấn database cho cả endpoint REST không cần view và làm tăng p95 latency.
Đội xây handler MVC trả tên logical view; sau khi thêm cùng tên template ở module khác, ViewResolver chọn nhầm nội dung cho một nhóm người dùng.
Một hệ thống dùng redirect từ controller sau khi POST; thông báo lỗi được giữ trong FlashMap nhưng load balancer chuyển request tiếp theo tới pod có session state khác.
Nhóm tạo API trả String làm response body nhưng quên @ResponseBody; Spring hiểu String là tên view và trả lỗi không tìm thấy template.
Ứng dụng dùng @RestController cho endpoint dữ liệu nhưng trả một đối tượng có tham chiếu hai chiều; JSON serializer đệ quy khi xây response đơn hàng.
Đội nhận JSON đặt hàng qua @RequestBody; một trường bắt buộc bị viết sai tên và Jackson bỏ qua, khiến dữ liệu được lưu với giá trị mặc định ngoài ý muốn.
Nhóm dùng @ModelAttribute để bind form đăng ký; client gửi thêm tham số role và thuộc tính nhạy cảm bị cập nhật dù không có trên giao diện.
Ứng dụng nhận hồ sơ bằng multipart/form-data gồm file và JSON metadata; controller dùng @RequestBody cho toàn bộ request nên không đọc được phần JSON.
Đội sử dụng @RequestPart cho file và metadata; một ứng dụng đối tác gửi JSON part không có Content-Type và nhận lỗi chuyển đổi media type.
Nhóm dùng @RequestParam LocalDate cho ngày bắt đầu; client gửi định dạng ngày địa phương khác với cấu hình conversion và API trả 400.
Ứng dụng có Converter tùy chỉnh từ String sang mã sản phẩm; một phiên bản mới hỗ trợ tiền tố ID khác nhưng Converter vẫn từ chối mã hợp lệ.
Đội khai báo Formatter cho số tiền theo Locale; request chạy bằng locale của máy chủ thay vì người dùng khiến dấu phẩy thập phân được diễn giải sai.
Nhóm dùng @DateTimeFormat cho khoảng thời gian; phía mobile gửi timezone offset trong khi DTO chỉ dùng LocalDateTime và dữ liệu hẹn bị lệch.
Ứng dụng dùng @InitBinder cho form khách hàng; binder áp trên nhiều controller khác dự kiến nên trường địa chỉ của form nội bộ không được chấp nhận.
Đội cấu hình allowedFields trong DataBinder cho dữ liệu công khai; một DTO mới thêm field hệ thống và binding mở rộng làm người dùng sửa được trường nhạy cảm.
Nhóm dùng WebDataBinder để cập nhật entity trực tiếp từ request; payload không cung cấp thuộc tính hiện có làm những trường không được chỉnh sửa bị thay đổi trạng thái.
Ứng dụng nhập danh sách item qua @RequestBody; một phần tử null hoặc thiếu SKU khiến bước mapping dữ liệu lỗi giữa chừng sau khi đã ghi phần trước.
Đội nhận danh sách enum trong query parameters; khách gửi cùng một tham số nhiều lần và bộ chuyển đổi chỉ lấy giá trị đầu ngoài ý định.
Nhóm thiết kế DTO immutable bằng Java record; constructor binding với một tham số không khớp tên JSON khiến API chỉ lỗi trên môi trường build thiếu metadata.
Ứng dụng dùng @RequestBody cho dữ liệu lớn; body được đọc và deserialize toàn bộ trước khi kiểm quota khiến một request tiêu tốn heap bất thường.
Đội phát triển bật validation @Valid trên DTO OrderRequest; constraint ở một object nested chưa được kiểm nên một đơn có địa chỉ rỗng vẫn qua controller.
Nhóm dùng @Validated với validation groups cho thao tác tạo và sửa; endpoint cập nhật áp nhầm nhóm tạo nên yêu cầu hợp lệ bị từ chối.
Ứng dụng có custom ConstraintValidator kiểm mã ưu đãi bằng database; validator thực hiện query cho từng line item và làm xử lý một đơn chậm đáng kể.
Đội muốn trả danh sách lỗi của nhiều trường qua BindingResult; chữ ký method đặt BindingResult sai vị trí làm Spring ném lỗi trước khi xử lý nghiệp vụ.
Nhóm kiểm @NotBlank cho email nhưng dữ liệu có khoảng trắng Unicode; một số địa chỉ không hợp lệ vẫn đi qua bước validation đầu vào.
Ứng dụng bật @Size trên danh sách item; client gửi số lượng vượt giới hạn nhưng method nhận type khác DTO đã gắn annotation và không kích hoạt kiểm tra.
Đội dùng @Pattern để kiểm mã đơn theo regex; một pattern có backtracking lớn chặn request thread khi input dài.
Nhóm cấu hình @Min cho page index nhưng để kiểu String ở request object; lỗi parse xảy ra trước validation và response trả định dạng không thống nhất.
Ứng dụng kiểm tính hợp lệ của file upload bằng phần mở rộng tên file; người dùng đổi extension làm file độc hại được nhận như ảnh.
Đội dùng MultipartFile để nhận video; giới hạn multipart của servlet container và cấu hình Spring khác nhau khiến file hợp lệ bị từ chối trên production.
Nhóm upload tệp với tên chứa đường dẫn tương đối; service lấy originalFilename để tạo đường dẫn ghi và tài liệu được lưu sai vị trí dự kiến.
Ứng dụng tải nhiều file đồng thời vào thư mục tạm; request bị hủy giữa chừng để lại nhiều tệp chưa được dọn và ổ đĩa đầy.
Đội tạo API streaming file tải xuống bằng Resource; tài nguyên bị đóng trước khi response được ghi hết nên client nhận file không đầy đủ.
Nhóm dùng ResponseEntity<Resource> để gửi báo cáo; header Content-Disposition không mã hóa filename tiếng Việt đúng và trình duyệt tải với tên lỗi.
Ứng dụng cần hỗ trợ range requests cho video; controller luôn trả 200 với toàn bộ file nên client không thể tiếp tục tải từ phần đang dở.
Đội gửi ảnh trong response với Content-Type mặc định application/octet-stream; một số trình duyệt hiển thị tải tệp thay vì render ảnh trực tiếp.
Nhóm phản hồi 201 Created sau POST tạo đơn; header Location trỏ tới URL nội bộ của container khiến client không thể mở tài nguyên vừa tạo.
Ứng dụng trả 204 No Content nhưng vẫn serialize body trạng thái; một client strict HTTP loại bỏ phần body và dữ liệu nghiệp vụ không được nhận.
Đội có endpoint tìm Order trả 404 khi không có bản ghi; một endpoint tương tự lại trả 200 với null nên client phải xử lý hai hợp đồng khác nhau.
Nhóm sử dụng ResponseEntity với ETag cho cập nhật sản phẩm; request đồng thời không gửi If-Match làm chỉnh sửa sau ghi đè thay đổi của người trước.
Ứng dụng dùng Last-Modified cho cache HTTP; đồng hồ giữa các node chênh nhau khiến client nhận 304 dù dữ liệu ở database đã thay đổi.
Đội tạo response JSON danh sách giao dịch với Page trực tiếp; sau nâng cấp Spring Data, cấu trúc metadata bị đổi và app mobile không phân tích được.
Nhóm cấu hình ObjectMapper serialize enum bằng tên; đối tác đang dựa vào mã số trạng thái nên response mới bị hiểu nhầm.
Ứng dụng xuất Instant thành timestamp dạng chuỗi; client cũ kỳ vọng epoch milliseconds và hiển thị thời gian giao dịch sai.
Đội bật Jackson default typing cho cấu trúc polymorphic từ JSON; dữ liệu không tin cậy mang thông tin kiểu khiến bề mặt deserialize mở rộng ngoài yêu cầu API.
Nhóm truyền entity JPA trực tiếp từ @RestController; serializer truy cập lazy relationship sau khi session đóng và phát LazyInitializationException.
Ứng dụng chạy Open Session in View để trả entity nested; response nhỏ vẫn tạo nhiều query N+1 và giữ kết nối database trong lúc serialize.
Đội dùng MappingJackson2HttpMessageConverter tùy biến; endpoint XML đang chạy bị chọn converter khác sau một thay đổi thứ tự đăng ký.
Nhóm khai báo HttpMessageConverter nhận một media type quá rộng; controller trả text/plain ở endpoint lẽ ra phải xuất JSON.
Ứng dụng xử lý Accept-Language để dịch thông báo lỗi; MessageSource thiếu key của một locale và phản hồi có mã lỗi đúng nhưng mô tả trống.
Đội tạo @ControllerAdvice áp cho tất cả controller; một handler lỗi của module quản trị ghi đè cách xử lý exception ở API công khai.
Nhóm dùng @ExceptionHandler cho hai exception liên quan kế thừa; handler rộng hơn được chọn làm mã HTTP bị ánh xạ không phù hợp lỗi thực.
Ứng dụng xử lý MethodArgumentNotValidException thành 500; người dùng nhập sai dữ liệu và hệ thống monitoring báo lỗi máy chủ tăng đột ngột.
Đội sử dụng ProblemDetail cho response lỗi HTTP; một endpoint vẫn trả JSON riêng nên khách không dựa được vào cùng contract trường type, title và detail.
Nhóm tích hợp ErrorResponse với mã lỗi nghiệp vụ; status và error code chưa thống nhất nên app mobile hiển thị thông báo lỗi chung sai ngữ cảnh.
Ứng dụng tạo ProblemDetail từ exception chứa SQL statement; thông tin bảng và giá trị cá nhân bị lộ trong chi tiết lỗi trả cho client.
Đội viết exception handler bắt mọi Throwable; một lỗi nghiêm trọng về tài nguyên cũng bị chuyển thành HTTP 400, khiến cảnh báo vận hành bị bỏ qua.
Nhóm xử lý AccessDeniedException trong @ControllerAdvice trước security filter; lỗi xác thực phát ra ở filter chain không đi qua handler như đội thiết kế mong đợi.
Ứng dụng gửi lỗi timeout từ downstream là 500; client không phân biệt lỗi của service nguồn với lỗi tạm thời của đối tác và retry không phù hợp.
Đội sử dụng ResponseStatusException cho order bị khóa; một filter toàn cục thay status trước khi trả làm khách nhận 200 dù nghiệp vụ thất bại.
Nhóm đưa traceId vào ProblemDetail response; exception xử lý trên thread khác không giữ MDC và support không ghép được log với request.
Ứng dụng có error handler thêm stack trace vào response chỉ khi profile debug; một deployment production kích hoạt nhầm profile và lộ thông tin nội bộ.
Đội quản trị chuẩn hóa thông báo validation ở HTTP 422; một số client đã xử lý 400 và báo sai khi API đổi status mà không đổi hợp đồng.
Nhóm sử dụng @RestControllerAdvice cho lỗi nghiệp vụ; exception xảy ra khi serialize response sau khi controller kết thúc không được chuyển thành body lỗi như dự tính.
Ứng dụng tạo API idempotent cho POST thanh toán; client retry khi timeout và endpoint tạo hai giao dịch vì chưa có khóa idempotency ổn định.
Đội đặt DELETE /orders/{id} làm thao tác xóa mềm; request lặp sau lần đầu trả mã khác ngoài hợp đồng, khiến client tưởng lần xóa lại đã thất bại.
Nhóm thiết kế PUT cập nhật đầy đủ Order; client gửi payload chỉ có một field và các field khác bị xóa ngoài ý định.
Ứng dụng dùng PATCH để cập nhật profile; sự khác biệt giữa field bị bỏ qua và field null chưa được xác định nên tên khách có thể bị xóa.
Đội công bố endpoint phân trang offset; dữ liệu mới được thêm khi client lật trang khiến một số giao dịch bị lặp hoặc bỏ sót.
Nhóm cho phép sort theo property do người dùng gửi; một field lồng nhau gây query JOIN nặng và endpoint bị chậm bất thường.
Ứng dụng tính tổng số trang cho một bảng lớn qua repository count; endpoint chỉ cần 20 bản ghi nhưng thời gian count làm p95 tăng mạnh.
Đội viết OpenAPI cho endpoint tạo voucher; hành vi error response thực tế khác tài liệu nên client sinh tự động không parse được lỗi.
Nhóm thay tên field JSON trong DTO nhưng không tăng version contract; các client cũ không cung cấp field mới và dữ liệu mặc định bị lưu sai.
Ứng dụng dùng API version trong path và header cùng lúc; một client gửi thông tin không tương ứng khiến backend áp schema sai phiên bản.
Đội đặt rate limit ở ingress nhưng controller vẫn cho phép download file khổng lồ; một khách làm bão hòa bandwidth mà request count không vượt ngưỡng.
Nhóm cấu hình CORS cho frontend nhiều domain; phản hồi Access-Control-Allow-Origin quá rộng cho endpoint dùng cookie xác thực và trình duyệt chặn request.
Ứng dụng nhận preflight OPTIONS đi qua authentication filter; trình duyệt không gửi token ở preflight và chức năng dùng API bị lỗi dù POST thủ công thành công.
Đội phát triển cấu hình allowCredentials trên CORS; danh sách origin từ request chưa được kiểm soát và một miền lạ có thể đọc response khi người dùng có session.
Nhóm đăng ký Interceptor kiểm tenantId; một API streaming hoặc async redispatch không đi qua cùng đường xử lý như yêu cầu MVC đồng bộ.
Ứng dụng có servlet Filter ghi body request để audit; việc đọc InputStream trước controller làm @RequestBody nhận body rỗng.
Đội triển khai OncePerRequestFilter lưu correlation ID; async dispatch khiến MDC bị xóa quá sớm và log ở worker không có traceId.
Nhóm dùng HandlerInterceptor để đo thời gian xử lý; request async kết thúc sau khi thread ban đầu giải phóng nên metric không bao gồm thời gian thực.
Ứng dụng đặt thông tin đăng nhập trong HttpSession; khi scale nhiều pod mà session không được chia sẻ, user liên tục bị đăng xuất.
Đội giữ trạng thái giỏ hàng trong @SessionAttributes; hai tab của cùng browser cập nhật đồng thời và làm mất lựa chọn mới nhất.
Nhóm đặt cookie SameSite không phù hợp cho luồng OAuth redirect; trình duyệt không gửi cookie và việc xác thực thất bại ở bước callback.
Ứng dụng yêu cầu xử lý X-Forwarded-For để lấy IP thật; một client tự gửi header này và vượt qua giới hạn theo IP của dịch vụ.
Đội trả redirect tới URL lấy từ tham số returnUrl; một giá trị do người dùng nhập chuyển khách sang miền không thuộc ứng dụng.
Nhóm cấu hình HTTP response security headers tại proxy và ứng dụng; một lần deploy xóa Content-Security-Policy ở cả hai tầng và kiểm thử chỉ nhìn status.
Ứng dụng nhận webhook có chữ ký HMAC; filter normalize JSON trước khi kiểm chữ ký khiến payload hợp lệ từ đối tác bị từ chối.
Đội sử dụng ContentCachingRequestWrapper để ghi log; body có thông tin thẻ thanh toán bị lưu vào log tập trung ngoài yêu cầu bảo mật.
Nhóm cấu hình SecurityFilterChain với HTTP Basic cho API nội bộ; một endpoint mới bị bỏ khỏi security matcher và public internet có thể gọi mà không xác thực.
Ứng dụng sử dụng request-scoped bean lấy userId; một luồng xử lý nền được khởi chạy sau request không còn scope và ném lỗi truy cập.
Đội thiết lập timeouts cho servlet connector nhưng không giới hạn thời gian xử lý database; request chậm giữ worker đến khi gateway trả 504.
Nhóm có controller @GetMapping gọi dịch vụ đối tác bằng RestTemplate đồng bộ; đối tác phản hồi chậm làm hết servlet worker và các request nhẹ cũng bị trì hoãn.
Ứng dụng chuyển controller sang Callable để xử lý truy vấn nặng; pool executor async không đủ worker và những request đã trả bước đầu chưa bao giờ hoàn tất đúng hạn.
Đội dùng WebAsyncTask có timeout ngắn hơn thời gian truy vấn; client nhận lỗi timeout nhưng tác vụ JDBC bên trong vẫn giữ connection sau đó.
Nhóm tạo DeferredResult cho quy trình xác nhận thanh toán; event kết quả đến trước khi DeferredResult được đăng ký và HTTP request bị treo.
Ứng dụng lưu DeferredResult của mỗi khách trong ConcurrentHashMap; client mất kết nối nhưng entry không được xóa khiến bộ nhớ tăng theo thời gian.
Đội dùng CompletionStage trong controller MVC; một future hoàn tất với exception sau khi request đã được chuyển async và exception mapping không giống synchronous flow.
Nhóm phát StreamingResponseBody từ một controller MVC; khi client đọc chậm, worker của executor bị giữ qua kết nối và số task chờ tăng liên tục.
Ứng dụng xuất CSV qua ResponseBodyEmitter; kết nối bị ngắt sau vài nghìn dòng nhưng tác vụ tạo dữ liệu vẫn tiếp tục chạy và chiếm tài nguyên.
Đội triển khai SseEmitter để thông báo trạng thái; client mất kết nối và server không dọn emitter cũ, làm tăng số listener giữ trong bộ nhớ.
Nhóm gửi các sự kiện SSE từ nhiều thread vào cùng SseEmitter; thứ tự cập nhật và xử lý exception không còn giống thời điểm sự kiện được tạo.
Ứng dụng cấu hình AsyncTaskExecutor dùng chung cho StreamingResponseBody và báo cáo PDF; request streaming dài làm hết worker xử lý báo cáo.
Đội có callback onTimeout cho DeferredResult; callback đánh dấu thất bại nhưng event đến muộn tiếp tục ghi trạng thái thành công ngoài ý muốn.
Nhóm gọi service @Transactional trong Callable sau khi controller tạo entity; thread async không chia sẻ transaction ban đầu và dữ liệu được đọc khác dự kiến.
Ứng dụng đặt principal và locale vào ThreadLocal; tác vụ Callable không tự kế thừa context nên email phản hồi dùng sai người và ngôn ngữ.
Đội muốn truyền MDC traceId sang async MVC; log của tác vụ không có correlation ID nên không nối được lỗi timeout với request gốc.
Nhóm chạy nhiều request với ResponseBodyEmitter trên một pod; các kết nối mở lâu chạm giới hạn file descriptor dù CPU vẫn còn thấp.
Ứng dụng phản hồi lỗi sau khi stream đã ghi dữ liệu đầu; HTTP status không còn đổi được như khi chưa commit response và client nhận file lỗi nửa chừng.
Đội kiểm thử async MVC bằng MockMvc; testcase chỉ assert trạng thái ban đầu mà không thực hiện async dispatch nên lỗi worker không được phát hiện.
Nhóm cài đặt timeout xử lý async khác trên servlet container và MVC; một deadline được kích hoạt sớm làm response bị đóng trong lúc dữ liệu vẫn đang ghi.
Ứng dụng sử dụng @Controller với method trả Mono trong Spring MVC; đội phát triển tưởng toàn bộ I/O của ứng dụng trở nên non-blocking dù repository vẫn chạy chặn thread.
Đội xây chức năng tìm kiếm bằng Spring WebFlux annotated controller; handler gọi repository JPA blocking trên event loop và làm các request khác tăng latency.
Nhóm khai báo RouterFunction cho /api/orders và một annotated route cùng URL; route được chọn khác với giả định sau khi tích hợp thêm module WebFlux.
Ứng dụng dùng ServerRequest.pathVariable trong functional endpoint; một route không có biến tương ứng và lỗi chỉ xuất hiện khi client gọi đường dẫn đặc biệt.
Đội xây WebFlux handler trả Mono<ServerResponse>; một nhánh không subscribe tới publisher ghi dữ liệu nên API trả thành công mà database không thay đổi.
Nhóm tạo Mono từ một giá trị được tính trước ngoài reactive chain; request đã bị hủy nhưng side effect xảy ra ngay khi controller tạo publisher.
Ứng dụng dùng Flux phát kết quả tìm kiếm lớn; một đoạn collectList ở cuối handler giữ toàn bộ kết quả trong heap thay vì gửi dần từng phần.
Đội dùng flatMap không giới hạn concurrency để gọi API định giá; hàng nghìn lời gọi chạy đồng thời và connection pool của đối tác bị cạn.
Nhóm áp concatMap cho mọi tác vụ I/O độc lập; chức năng trả 100 mục rất chậm vì từng request phải đợi request trước dù backend còn tài nguyên.
Ứng dụng xử lý Flux từ MongoDB rồi gọi block ở giữa pipeline; thao tác blocking trên event loop gây nghẽn và có thể phát lỗi trong runtime reactive.
Đội đặt publishOn boundedElastic cho một bước blocking; queue scheduler tăng trong thời gian database lỗi và response timeout hàng loạt.
Nhóm muốn truyền SecurityContext vào reactive flow; code đọc ThreadLocal trực tiếp thay vì Reactor Context nên userId biến mất sau khi đổi scheduler.
Ứng dụng giữ tenantId trong ThreadLocal ở WebFlux filter; các operator chạy trên thread khác và query tới tenant mặc định, có nguy cơ đọc sai dữ liệu.
Đội áp validation cho body JSON reactive với @Valid; publisher nhận DTO không hợp lệ nhưng một nhánh xử lý lỗi chuyển thành 500 thay vì lỗi client.
Nhóm dùng WebExchangeBindException để trả lỗi chi tiết; dữ liệu field nhạy cảm từ request bị phản chiếu nguyên văn trong response công khai.
Ứng dụng WebFlux có WebFilter xác thực; một RouterFunction được bind vào context khác không có filter và endpoint trả dữ liệu ngoài quyền.
Đội cấu hình SecurityWebFilterChain cho API reactive; thứ tự matcher sai làm route admin bị phủ bởi rule cho phép truy cập công khai.
Nhóm dùng ServerWebExchange.getRequest().getBody để ghi audit; WebFilter tiêu thụ DataBuffer mà không truyền nội dung tiếp khiến handler nhận payload rỗng.
Ứng dụng giữ DataBuffer sau khi request đã xử lý; reference counting không được quản lý phù hợp và direct memory tăng qua nhiều lượt tải.
Đội đọc multipart upload bằng WebFlux; client gửi hàng nghìn phần nhỏ khiến giới hạn bộ nhớ và kích thước phần không đúng cấu hình kiểm thử.
Nhóm xây API streaming file lớn bằng DataBuffer; một branch lỗi không release buffer và container hết direct memory sau nhiều request.
Ứng dụng trả Flux trên HTTP cho nhiều người đọc chậm; producer bỏ qua tín hiệu backpressure và bộ đệm ở gateway tăng không kiểm soát.
Đội hỗ trợ SSE qua WebFlux bằng Flux interval; khi client disconnect, nguồn tạo event vẫn tiếp tục và giữ tài nguyên của session cũ.
Nhóm nối nhiều nguồn Flux của sự kiện đơn hàng; các nguồn hoàn thành khác thứ tự khiến người dùng thấy trạng thái đã hoàn tất trước trạng thái đang xử lý.
Ứng dụng dùng onErrorResume để trả dữ liệu mặc định; lỗi xác thực từ downstream cũng bị nuốt và client nhận danh sách rỗng có vẻ hợp lệ.
Đội dùng retryWhen trên Mono tạo giao dịch; một request bị retry sau timeout và thao tác thanh toán không idempotent có thể chạy hai lần.
Nhóm áp timeout cho reactive chain; request kết thúc với lỗi nhưng lệnh ghi ngoài hệ thống không phản ứng cancellation và tiếp tục tạo đơn.
Ứng dụng dùng doOnError để ghi metric; callback ném exception mới và dấu vết lỗi gốc bị che khi chạy production.
Đội chia sẻ một hot Flux cho nhiều người dùng; cấu hình multicast không tách tenant và event riêng của khách A có thể hiện ở stream khách B.
Nhóm dùng Sinks.Many cho thông báo giao hàng; tốc độ producer lớn hơn client và chiến lược buffer gây tràn bộ nhớ hoặc mất sự kiện.
Ứng dụng phát dữ liệu qua Flux nhưng dùng cache không giới hạn; một luồng sự kiện chạy cả ngày khiến bộ nhớ tăng liên tục.
Đội khởi động một subscription thủ công trong @PostConstruct; khi ứng dụng shutdown, subscription không được dispose và tiếp tục gọi hạ tầng đã đóng.
Nhóm kiểm lỗi WebFlux trên WebTestClient bằng dữ liệu ít; khi production chịu tải nhiều kết nối SSE, giới hạn pending writes mới lộ ra.
Ứng dụng WebFlux chạy trên Reactor Netty nhưng nhóm áp cấu hình servlet Filter; cơ chế bảo mật mong muốn không hoạt động vì hai stack khác nhau.
Đội chuyển một endpoint MVC sang WebFlux nhưng giữ cùng module có spring-webmvc; ứng dụng vẫn chạy loại web application không đúng mong muốn của team.
Nhóm thêm WebClient vào ứng dụng MVC để gọi downstream; controller vẫn block để nhận kết quả nên servlet worker tiếp tục bị giữ khi đối tác chậm.
Ứng dụng tạo WebClient mới cho mỗi lần gọi HTTP; kết nối và tài nguyên client không được dùng lại hiệu quả khi lưu lượng tăng.
Đội cấu hình WebClient với baseUrl của production trong bean chung; testcase đổi URL qua property nhưng cached bean vẫn gọi backend thật.
Nhóm thiết lập WebClient.defaultHeader Authorization từ một token khởi tạo lúc startup; token hết hạn và tất cả request sau đó nhận 401.
Ứng dụng dùng WebClient filter để thêm bearer token theo SecurityContext; request sau khi chuyển scheduler không có context đúng và header gửi nhầm tài khoản.
Đội xây WebClient để gọi nhiều tenant; filter giữ tenantId trong biến mutable của singleton và request đồng thời có thể gửi header sai tenant.
Nhóm dùng retrieve để nhận dữ liệu đối tác; response 404 có ý nghĩa nghiệp vụ nhưng bị biến thành lỗi chung và API gốc trả 500.
Ứng dụng sử dụng exchangeToMono để xử lý nhiều mã trạng thái; nhánh 429 không tiêu thụ hoặc giải phóng response body phù hợp khiến connection pool bị áp lực.
Đội đọc một JSON rất lớn bằng bodyToMono; codec giới hạn bộ nhớ mặc định làm lỗi DataBufferLimitException ở production.
Nhóm gọi WebClient nhận tệp PDF bằng bodyToMono(byte array); file lớn khiến heap bị chiếm thay vì được xử lý theo dòng dữ liệu.
Ứng dụng đặt response timeout cho WebClient rất ngắn; request hợp lệ dưới tải cao bị cắt và client liên tục retry gây bão lưu lượng.
Đội chỉ cấu hình timeout operator cho WebClient; kết nối TCP và DNS vẫn có thời gian chờ riêng khiến socket kéo dài ngoài deadline dự kiến.
Nhóm cấu hình connection pool Reactor Netty cho WebClient; số kết nối tối đa nhỏ hơn số lời gọi đồng thời và pending acquire queue tăng.
Ứng dụng dùng một HttpClient connection pool chung cho nhiều downstream; một đối tác chậm giữ hết kết nối và tác động cả chức năng độc lập.
Đội thêm retryWhen cho tất cả HTTP method; POST không có idempotency key bị thực thi lặp sau response timeout và tạo giao dịch trùng.
Nhóm xử lý 503 bằng retry không có jitter; hàng trăm instance đồng loạt thử lại và đối tác vừa phục hồi bị quá tải lần nữa.
Ứng dụng gắn correlation ID trong WebClient filter; khi nhận redirect, ID không còn xuất hiện ở request tiếp và khó truy nguyên sự cố.
Đội cấu hình proxy HTTP cho WebClient; endpoint nội bộ trong no-proxy list chưa đầy đủ khiến dữ liệu nhạy cảm đi qua proxy bên ngoài.
Nhóm dùng WebClient gửi multipart với file từ đường dẫn tạm; file bị xóa trước lúc reactive publisher thực sự được subscribe và upload thất bại.
Ứng dụng gọi WebClient lấy dữ liệu giá rồi dùng onErrorReturn giá bằng không; lỗi kết nối được hiểu như giá hợp lệ và tạo đơn sai tiền.
Đội kiểm kết quả WebClient trên response có charset không được khai báo; tên khách tiếng Việt bị decode không đúng ở một nhà cung cấp.
Nhóm gửi request JSON qua WebClient với default Content-Type; đối tác yêu cầu vendor media type và trả 415 cho một số API.
Ứng dụng dùng WebClient hỗ trợ OAuth2 client credentials; token service trả lỗi nhưng filter vẫn gửi request không có token và ghi log dữ liệu ngoài mong muốn.
Đội gọi WebClient qua mTLS tới đối tác thanh toán; chứng chỉ client hết hạn trên một nhóm pod làm tỷ lệ lỗi chỉ tăng ở một phần traffic.
Nhóm dùng WebClient cho API trả SSE; client tải kết quả vào List rồi chờ luồng hoàn tất nên tác vụ không bao giờ trả dữ liệu.
Ứng dụng hủy subscription của WebClient khi người dùng đóng trang; một số yêu cầu bên đối tác đã xử lý xong nhưng backend vẫn báo bị hủy.
Đội sử dụng StepVerifier để kiểm WebClient reactive chain với mock response tức thì; không mô phỏng connection timeout và trạng thái connection pool khi tải thật.
Nhóm xây HTTP Service Client bằng @HttpExchange và @GetExchange để truy cập catalog; một thay đổi base URL trong môi trường test không được cập nhật vào proxy đã khởi tạo.
Ứng dụng khai báo HTTP interface bằng @PostExchange cho thanh toán; DTO request thiếu field bắt buộc nhưng việc serialize thành công làm lỗi chỉ xuất hiện khi gọi đối tác.
Đội thêm @RequestHeader vào HTTP Service Client method; phương thức bị refactor và header tenant không được truyền trên một đường gọi.
Nhóm khai báo @PathVariable trong HTTP interface với tên khác URI template; endpoint catalog trả 404 khi tạo URL chứa ID.
Ứng dụng dùng @RequestParam cho danh sách filter ở HTTP Service Client; đối tác diễn giải cách mã hóa repeated parameters khác và trả dữ liệu không đúng.
Đội định nghĩa method HTTP interface trả entity đồng bộ; team nghĩ client không chặn thread vì proxy dựng trên WebClient nhưng một caller vẫn đợi kết quả.
Nhóm xây HTTP Service Client trả Mono<Product>; endpoint MVC gọi block để lấy Product và không còn lợi ích non-blocking ở controller.
Ứng dụng dùng @HttpExchange với contentType mặc định cho form upload; đối tác mong multipart nhưng client gửi JSON và trả 415.
Đội cấu hình HttpServiceProxyFactory với adapter riêng; bộ test dùng WebClient adapter trong khi production dùng RestClient nên lỗi timeout và converter khác nhau.
Nhóm gọi đối tác từ HTTP interface và xử lý mọi ngoại lệ thành 404; lỗi 503 của downstream bị hiểu như tài nguyên không tồn tại và không kích hoạt cảnh báo.
Ứng dụng công bố interface client dùng cho cả API v1 và v2; một phương thức trong interface vẫn gọi path v1 và nhận schema không tương thích ở bản mới.
Đội sử dụng HTTP Service Client trong một job nền dài; thời gian chờ và retry nằm ở adapter phía dưới nhưng monitoring chỉ quan sát interface method.
Nhóm cập nhật thư viện Spring Framework và thay API adapter của HTTP Service Client; một loạt request dùng nội dung response mới nhưng test chỉ xác minh proxy được tạo.
Ứng dụng dùng interface client để gọi API bảo mật có cookie; phiên đăng nhập không được quản lý theo request và hành vi khác trình duyệt thực.
Đội thêm authorization bearer vào HTTP Service Client qua interceptor; token dùng chung cho nhiều tenant và một request có thể gọi thay tài khoản khác.
Nhóm xây contract test cho HTTP Service Client; stub chỉ xác nhận URL mà không kiểm header Accept và Content-Type nên request thật bị từ chối.
Ứng dụng gửi query có ký tự Unicode qua HTTP Service Client; URL encoding khác bên đối tác làm tìm kiếm tên tiếng Việt trả kết quả rỗng.
Đội làm WebSocket chat nội bộ bằng WebSocketHandler của Spring; mỗi kết nối giữ một session nhưng trạng thái người dùng bị lưu trong singleton mutable và lẫn giữa các phòng.
Nhóm triển khai STOMP over WebSocket với @MessageMapping; một client gửi destination không khớp prefix ứng dụng và handler không được kích hoạt.
Ứng dụng phát thông báo qua SimpMessagingTemplate tới /topic/orders; một client không thuộc tenant vẫn subscribe được topic chung và nhận trạng thái đơn của người khác.
Đội dùng user destinations để gửi thông báo cá nhân; Principal thiếu hoặc không ổn định giữa các kết nối và message đến sai session người dùng.
Nhóm bật SockJS fallback cho một số trình duyệt; chính sách CORS của transport fallback khác WebSocket handshake khiến chỉ một nhóm client không kết nối được.
Ứng dụng kiểm handshake WebSocket bằng cookie session; sau khi browser giới hạn cookie, kết nối được mở nhưng Principal chưa xác thực.
Đội đưa JWT trong query string của WebSocket handshake; token xuất hiện trong access log của proxy và tạo nguy cơ lộ credential.
Nhóm cần đóng kết nối WebSocket khi token hết hạn; session còn mở nhiều giờ dù quyền của tài khoản đã bị thu hồi ở hệ thống xác thực.
Ứng dụng dùng SimpleBroker để phát trạng thái tới hàng nghìn người xem; khi tăng thành nhiều pod, subscription ở pod A không tự nhận message từ pod B.
Đội chạy STOMP broker relay tới broker ngoài; kết nối broker relay bị ngắt nhưng WebSocket client vẫn còn mở và không nhận được sự kiện.
Nhóm bật heartbeat STOMP để phát hiện kết nối lỗi; proxy có idle timeout ngắn hơn chu kỳ heartbeat nên người dùng bị ngắt ngẫu nhiên.
Ứng dụng gửi payload JSON lớn qua WebSocket; giới hạn kích thước message của server làm một số sự kiện đơn hàng bị đóng kết nối.
Đội phát tin nhắn chat tới nhóm có client đọc chậm; outbound message buffer tăng và gây áp lực memory trong giờ cao điểm.
Nhóm dùng WebSocketSession.sendMessage từ nhiều thread; các lần gửi cạnh tranh làm thứ tự thông báo sai hoặc phát exception trên session.
Ứng dụng giữ danh sách WebSocketSession trong một Map; kết nối đóng không được xóa khỏi registry và bộ nhớ tăng sau nhiều ngày.
Đội quản lý phòng chat dựa vào sự kiện disconnect; mất mạng đột ngột không tạo notification kịp thời nên trạng thái online còn lâu sau khi khách rời đi.
Nhóm dùng @SendTo để phát sự kiện chat sau khi lưu database; transaction rollback nhưng thông báo đã tới client và hiển thị một tin nhắn không tồn tại.
Ứng dụng cho phép client gửi STOMP destination tùy ý; một người dùng thử publish trực tiếp lên kênh dành cho admin thay vì đi qua handler kiểm quyền.
Đội áp rate limit cho REST HTTP nhưng bỏ WebSocket message rate; một kết nối gửi hàng nghìn message mỗi giây làm executor outbound quá tải.
Nhóm lưu lịch sử chat ở database rồi chỉ phát sự kiện qua WebSocket; client bị mất kết nối giữa chừng và không biết đoạn tin nhắn nào cần đồng bộ lại.
Ứng dụng dựa vào WebSocket để chuyển yêu cầu thanh toán giữa microservices; khi pod restart, message chưa giao biến mất nhưng sản phẩm kỳ vọng cơ chế hàng đợi bền vững.
Đội kiểm thử WebSocket bằng một kết nối nội bộ; sự cố phân quyền subscribe và send giữa hai tenant không được tái hiện.
Nhóm tạo chat STOMP nhưng test không mô phỏng reconnect; client subscribe lặp sau khi reconnect và nhận mỗi thông báo hai lần.
Ứng dụng xây dashboard realtime dùng cả SSE và WebSocket; một user mở nhiều tab khiến số kết nối vượt quota dù chỉ một tài khoản đang hoạt động.
Đội deploy ứng dụng MVC và WebSocket qua gateway; ingress chưa hỗ trợ Upgrade header đúng nên REST chạy tốt còn WebSocket handshake trả lỗi.
Nhóm cấu hình WebSocket compression cho nội dung người dùng; với message chứa dữ liệu nhạy cảm và đầu vào được chọn, đội bảo mật cần đánh giá rủi ro khi nén chung nội dung.
Ứng dụng chạy WebSocket sau reverse proxy HTTPS; URL ws không được chuyển sang wss khi frontend chạy trên HTTPS và trình duyệt chặn mixed content.
Đội tạo endpoint chat có idle timeout quá ngắn; người dùng đang đọc tin nhắn bị ngắt dù phiên đăng nhập vẫn có hiệu lực.
Nhóm có WebSocket message interceptor kiểm role; một STOMP CONNECT hợp lệ nhưng SUBSCRIBE đến destination khác được kiểm không đủ chặt.
Ứng dụng dùng WebSocket để hiển thị kết quả job; server không lưu trạng thái cuối nên client reconnect bỏ lỡ sự kiện hoàn tất.
Đội tạo test MVC bằng MockMvc standaloneSetup; các filter bảo mật, converter và @ControllerAdvice thực tế không được áp, khiến contract test cho kết quả khác production.
Nhóm chạy MockMvc với Spring Security nhưng không kiểm CSRF; POST tạo tài nguyên được thử với token hợp lệ duy nhất và luồng thiếu token chưa được xác minh.
Ứng dụng test async MVC mà không thực hiện asyncDispatch; trạng thái response chỉ được quan sát trước khi tác vụ background ném exception.
Đội dùng WebTestClient.bindToController cho WebFlux handler; các WebFilter ứng dụng và cấu hình codec production chưa được kiểm trong testcase.
Nhóm triển khai WebTestClient.bindToServer qua cổng ngẫu nhiên; request chạy thread khác nên rollback của test không bao phủ những ghi chép HTTP thực.
Ứng dụng test WebClient bằng mock trả kết quả tức thì; timeout, retry và lỗi server trả partial body không xuất hiện trong test mà production thường gặp.
Đội dùng MockWebServer để kiểm HTTP Service Client; stub không xác nhận header bearer/tenant và contract có thể sai dù status 200.
Nhóm chạy integration test file upload với 1 KB; tệp thật hàng trăm MB gây lỗi cấu hình multipart và timeout chưa được phát hiện.
Ứng dụng dùng WebTestClient để kiểm Flux vô hạn; test chờ luồng hoàn tất thay vì kiểm một số event và liên tục timeout.
Đội test nội dung ProblemDetail với một locale; khi máy CI dùng locale khác, message và time format thay đổi làm assertion không ổn định.
Nhóm kiểm controller với JSON fixture không có trường đặc biệt; tên Unicode và mã sản phẩm có ký tự URL encoded chỉ gây lỗi trên production.
Ứng dụng chạy thử API với localhost không qua proxy; X-Forwarded-* và scheme HTTPS không được test nên link trả về cho khách ngoài mạng bị sai.
Đội sử dụng Testcontainers cho database và MockMvc; lỗi N+1 khi serializer truy cập entity nhiều quan hệ không lộ với fixture chỉ một đơn hàng.
Nhóm dùng StepVerifier cho reactive handler nhưng không subscribe publisher chứa side effect trong một nhánh; bài test vẫn xác nhận method đã gọi mà database không thay đổi.
Ứng dụng chạy load test endpoint WebFlux với mock repository; blocking JDBC trong tầng dữ liệu thật làm event loop nghẽn nhưng bộ test không tái hiện.
Đội có bộ kiểm thử streaming chỉ đọc response đầu; lỗi giữa stream và dọn tài nguyên lúc client disconnect không được xác minh.
Nhóm triển khai contract API mới đồng thời cho MVC và WebFlux; cùng một mã lỗi nghiệp vụ được serialize khác định dạng, buộc khách xử lý hai cấu trúc.
Ứng dụng gắn metric request ở HandlerInterceptor MVC; luồng WebFlux không đi qua interceptor nên dashboard thiếu lưu lượng của API reactive.
Đội dùng tracing cho WebClient và HTTP Service Client; một nhánh gửi request không truyền traceparent nên log downstream không nối được với request gốc.
Nhóm muốn đo p95 latency riêng cho stream và request thường; metric hiện kết thúc khi controller trả publisher, không phản ánh lúc client nhận dữ liệu cuối.
Ứng dụng gặp 502 ngẫu nhiên sau khi gateway cắt connection idle; WebClient tái sử dụng kết nối không còn khả dụng và đợt retry gây tăng tải.
Đội bật HTTP/2 tại reverse proxy nhưng backend servlet chỉ nhận HTTP/1.1; một nhóm client giả định hỗ trợ streaming và gặp hành vi buffer khác.
Nhóm cấu hình graceful shutdown cho HTTP server; pod ngừng nhận request mới nhưng WebSocket và SSE đang mở vẫn bị hủy trước khi client kịp đồng bộ trạng thái.
Ứng dụng áp giới hạn body HTTP theo ingress và WebFlux codec khác nhau; request lớn bị từ chối bằng hai status khác nhau khiến mobile app khó xử lý.
Đội dùng một service singleton để giữ currentUser trong controller MVC và WebFlux; dưới tải đồng thời, response có lúc chứa dữ liệu người dùng khác.
Nhóm cấu hình error logging ghi đầy đủ request headers; JWT, cookie phiên và dữ liệu cá nhân lọt vào hệ thống log dùng chung khi API bị lỗi.
Ứng dụng chạy multi-tenant có REST, WebClient và WebSocket; header tenant được kiểm ở REST nhưng không được truyền đúng sang outbound HTTP và các kênh realtime.
Đội chuyển từng endpoint từ MVC sang WebFlux; cả hai stack chưa có cùng quy ước timeout và retry nên các client nhìn thấy kết quả khác nhau cho cùng sự cố.
Nhóm kiểm tra bản phát hành Spring Framework mới; thay đổi path matching và message converter làm một số route với ký tự đặc biệt không tương thích phiên bản client cũ.
Ứng dụng triển khai canary cho bản HTTP API mới; request được chuyển giữa hai pod có contract JSON khác nhau và một khách nhận các response không nhất quán.
Đội vận hành thấy tỉ lệ HTTP 200 bình thường nhưng số thông báo WebSocket thất lạc tăng; hệ thống chỉ giám sát request/response và không đo vòng đời session/message.
Nhóm tạo API xuất dữ liệu từ query chạy lâu; khách hủy request nhưng truy vấn database tiếp tục và chiếm connection cho tới khi hoàn tất.
Ứng dụng cần hạn chế SSRF khi WebClient nhận URL callback từ khách; một endpoint cho phép truy cập địa chỉ nội bộ do URL không được kiểm giới hạn.
Đội áp chính sách CORS theo domain tenant từ database; cache cấu hình lỗi khiến origin của tenant này được dùng cho tenant khác và browser nhận response sai quyền.
Nhóm triển khai giới hạn số session WebSocket theo tài khoản; reconnect liên tiếp tạo race giữa connect và disconnect nên quota bị tính sai.
Ứng dụng trả lỗi API dạng ProblemDetail nhưng chưa chuẩn hóa correlation ID; bộ phận hỗ trợ không thể tìm log tương ứng khi khách gửi screenshot lỗi.
Đội có một endpoint HTTP Service Client dùng RestClient còn endpoint khác dùng WebClient; lỗi DNS và thời gian chờ khác nhau khiến cùng sự cố đối tác được báo thành hai loại lỗi.
Nhóm chuyển REST endpoint sang trả ResponseEntity<Flux<Order>>; client tự hủy kết nối giữa stream trong khi audit chỉ ghi số item dự kiến thay vì số thực đã gửi.
Ứng dụng dùng WebSocket gửi trạng thái cập nhật tồn kho ngay sau POST; REST transaction bị rollback trong khi event realtime đã tới trình duyệt, gây hiển thị số dư sai.

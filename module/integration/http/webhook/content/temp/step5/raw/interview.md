Trong những tình huống nào webhook phù hợp hơn cơ chế polling để thông báo thay đổi dữ liệu?
Bạn phân biệt webhook với lời gọi HTTP API thông thường về hướng khởi tạo request như thế nào?
Bạn so sánh webhook với message broker khi kết nối các hệ thống thuộc những tổ chức khác nhau ra sao?
Bạn xác định ranh giới trách nhiệm giữa bên phát và bên nhận webhook như thế nào?
Bạn thiết kế quy trình webhook để bên phát và bên nhận có thể triển khai độc lập ra sao?
Bạn đánh giá những giới hạn nào của webhook khi yêu cầu độ trễ thấp và độ tin cậy cao?
Bạn chọn những sự kiện nghiệp vụ nào để phát qua webhook và dựa trên tiêu chí gì?
Bạn phân biệt thông báo một sự kiện đã xảy ra với yêu cầu bên nhận thực hiện một lệnh ra sao?
Bạn xác định hợp đồng truyền nhận khi một sự kiện có nhiều bên đăng ký như thế nào?
Bạn tổ chức luồng từ thay đổi dữ liệu đến phát webhook sao cho không mất sự kiện ra sao?
Bạn xác định cách đặt tên sự kiện webhook để các ứng dụng khách dễ hiểu và mở rộng như thế nào?
Bạn lựa chọn cách tổ chức namespace của các loại sự kiện theo miền nghiệp vụ ra sao?
Bạn quyết định khi nào nên phát sự kiện ở mức tài nguyên và khi nào ở mức hành động nghiệp vụ?
Bạn xác định thời điểm sự kiện được xem là phát sinh khi một giao dịch cập nhật nhiều bảng như thế nào?
Bạn mô tả ngữ nghĩa at-least-once của webhook và hệ quả đối với bên nhận ra sao?
Vì sao webhook đã được xác nhận bằng HTTP vẫn có thể chưa được xử lý nghiệp vụ?
Bạn thiết kế hợp đồng webhook để chịu được việc bên nhận tạm thời không khả dụng ra sao?
Bạn đưa những điều kiện nào vào thỏa thuận mức dịch vụ của hệ thống webhook?
Bạn lựa chọn khả năng bảo đảm thứ tự sự kiện theo toàn hệ thống hay theo từng tài nguyên dựa trên tiêu chí nào?
Bạn phân biệt event delivery ID với business event ID khi thiết kế webhook như thế nào?
Bạn thiết kế event envelope chứa những trường chung nào để hỗ trợ định tuyến và truy vết?
Bạn chọn định dạng JSON hay định dạng nhị phân cho webhook dựa trên yêu cầu tương thích nào?
Bạn quyết định khi nào gửi toàn bộ trạng thái tài nguyên và khi nào chỉ gửi định danh hoặc thay đổi?
Bạn xử lý nguy cơ dữ liệu trong payload đã lỗi thời khi bên nhận xử lý chậm như thế nào?
Bạn định nghĩa event ID và tính duy nhất của nó qua các lần gửi lại như thế nào?
Bạn phân biệt thời điểm sự kiện xảy ra, được ghi nhận và được gửi trong payload ra sao?
Bạn thiết kế thuộc tính schema version để bên nhận nhận diện dữ liệu theo phiên bản như thế nào?
Bạn quản lý thay đổi các trường optional và required trong payload mà vẫn giữ tương thích ra sao?
Bạn xử lý việc thêm giá trị enum mới khi consumer cũ chưa biết giá trị đó như thế nào?
Bạn mô tả ý nghĩa của trường null và trường vắng mặt trong hợp đồng webhook ra sao?
Bạn định nghĩa kiểu số và thời gian để tránh sai khác giữa Java và ngôn ngữ phía consumer như thế nào?
Bạn đưa correlation ID hoặc trace ID vào event envelope để điều tra giao dịch liên dịch vụ ra sao?
Bạn chọn những thông tin nào cần đặt trong HTTP headers thay vì trong JSON payload?
Bạn thiết kế payload tránh làm lộ thông tin nhạy cảm không cần thiết như thế nào?
Bạn áp dụng các nguyên tắc tối thiểu hóa dữ liệu khi một sự kiện được gửi cho nhiều đối tác ra sao?
Bạn quản lý ví dụ payload và tài liệu sự kiện để chúng không lệch với code ra sao?
Bạn xác định giới hạn kích thước payload và hành vi khi sự kiện vượt giới hạn như thế nào?
Bạn xây dựng quy ước content type và charset cho webhook request ra sao?
Bạn sử dụng schema validation để phát hiện thông điệp không hợp lệ ở phía gửi và phía nhận như thế nào?
Bạn lựa chọn cách công bố và ngừng hỗ trợ một phiên bản event schema như thế nào?
Bạn thiết kế cơ chế cho phép bên nhận lấy trạng thái tài nguyên mới nhất khi payload chỉ chứa ID ra sao?
Bạn phân biệt idempotency key, event ID và delivery attempt ID trong hợp đồng như thế nào?
Bạn định nghĩa trạng thái một sự kiện khi nó đã được tạo nhưng chưa từng được giao như thế nào?
Bạn tổ chức danh mục sự kiện và tài liệu đăng ký để các tích hợp mới dễ triển khai ra sao?
Bạn thiết kế luồng đăng ký webhook endpoint cho một tài khoản hoặc tổ chức như thế nào?
Bạn xác định quyền được đăng ký từng loại sự kiện theo vai trò người dùng ra sao?
Bạn kiểm tra quyền sở hữu endpoint trước khi chấp nhận đăng ký webhook như thế nào?
Bạn thiết kế bước xác minh endpoint bằng challenge-response nếu nhà cung cấp yêu cầu ra sao?
Bạn phân biệt URL nhận webhook với URL quản trị subscription trong thiết kế hệ thống như thế nào?
Bạn quản lý một khách hàng có nhiều endpoint và nhiều bộ lọc sự kiện ra sao?
Bạn tổ chức lựa chọn các event types khi tạo mới subscription như thế nào?
Bạn định nghĩa bộ lọc theo tài nguyên hoặc đối tượng nghiệp vụ mà không tạo rò rỉ dữ liệu ra sao?
Bạn xử lý thay đổi URL endpoint khi các webhook cũ còn nằm trong hàng đợi như thế nào?
Bạn xác định lúc nào một subscription có hiệu lực sau khi cập nhật danh sách sự kiện ra sao?
Bạn quyết định xử lý các webhook đã được xếp hàng sau khi người dùng hủy subscription như thế nào?
Bạn thiết kế trạng thái active, paused và disabled của một subscription ra sao?
Bạn lựa chọn cơ chế tự tạm ngừng endpoint liên tục thất bại dựa trên những ngưỡng nào?
Bạn thông báo cho chủ sở hữu subscription khi endpoint bị vô hiệu hóa như thế nào?
Bạn thiết kế thao tác bật lại subscription và quyết định có gửi bù sự kiện cũ hay không ra sao?
Bạn xử lý nhiều subscription có URL giống nhau nhưng quyền và sự kiện khác nhau như thế nào?
Bạn áp dụng giới hạn số endpoint hoặc số subscription theo tenant bằng cơ chế nào?
Bạn cung cấp lịch sử delivery cho người quản trị subscription mà không lộ dữ liệu tenant khác ra sao?
Bạn thiết kế cơ chế thay đổi cấu hình subscription có thể kiểm toán được như thế nào?
Bạn phân biệt việc xác minh quyền quản trị subscription với xác thực yêu cầu webhook đến endpoint ra sao?
Bạn xây dựng hợp đồng cho webhook gửi bằng POST với headers và body như thế nào?
Bạn lựa chọn ý nghĩa của các mã HTTP 2xx khi xác nhận bên nhận đã tiếp nhận webhook ra sao?
Bạn dựa trên tiêu chí nào để xem một phản hồi 4xx là lỗi không thể sửa bằng retry?
Bạn xử lý mã 429 và header Retry-After từ endpoint nhận webhook ra sao?
Bạn phân biệt lỗi timeout, không kết nối được và lỗi HTTP 5xx khi phân loại delivery failure như thế nào?
Bạn quyết định thời gian connect timeout và response timeout cho webhook sender dựa trên yếu tố nào?
Bạn yêu cầu bên nhận trả HTTP response nhanh để giảm thời gian giữ kết nối như thế nào?
Bạn mô tả cách xử lý khi sender không nhận được response nhưng receiver có thể đã lưu sự kiện ra sao?
Bạn xác định ranh giới giữa xác nhận nhận request và hoàn tất nghiệp vụ trong giao thức webhook như thế nào?
Bạn cân nhắc điều gì khi sử dụng HTTP redirect từ webhook endpoint?
Bạn áp dụng giới hạn kích thước response để tránh sender tiêu tốn tài nguyên như thế nào?
Bạn xác định chính sách xử lý redirect sang host hoặc scheme khác khi sender có header nhạy cảm ra sao?
Bạn lựa chọn cách tạo một HTTP client riêng cho từng upstream hoặc endpoint webhook như thế nào?
Bạn giới hạn số request đồng thời đến một endpoint để tránh gây quá tải như thế nào?
Bạn thiết kế cơ chế kiểm soát DNS và địa chỉ IP khi endpoint do khách hàng cung cấp như thế nào?
Bạn ngăn webhook sender truy cập địa chỉ nội bộ, metadata service hoặc loopback nhằm giảm SSRF ra sao?
Bạn xác định cách xử lý endpoint chỉ chấp nhận các phiên bản TLS cũ như thế nào?
Bạn bảo đảm xác thực chứng chỉ và tên host khi gửi webhook HTTPS ra sao?
Bạn quản lý HTTP keep-alive và connection pool khi gửi tới hàng nghìn endpoint khác nhau như thế nào?
Bạn xác định khi nào một delivery attempt cần được ghi nhận là thất bại để lập lịch thử lại?
Bạn phân biệt HMAC với mã hóa dữ liệu khi bảo vệ nội dung webhook như thế nào?
Bạn giải thích vai trò của khóa bí mật dùng chung trong cơ chế ký HMAC như thế nào?
Bạn lựa chọn thuật toán HMAC phù hợp với yêu cầu bảo mật và khả năng tương thích như thế nào?
Bạn xác định những byte nào cần đưa vào phép tính HMAC cho một webhook?
Bạn thiết kế định dạng signature header để bên nhận nhận biết thuật toán và phiên bản ra sao?
Vì sao chữ ký webhook nên được tính trên các byte gốc của request body?
Bạn xử lý khác biệt giữa raw body và JSON đã được parse rồi serialize lại khi xác minh chữ ký ra sao?
Bạn kiểm soát encoding UTF-8 khi tính chữ ký để hai phía tạo cùng thông điệp đầu vào như thế nào?
Bạn lựa chọn đưa timestamp vào thông điệp được ký để giải quyết rủi ro nào?
Bạn chọn khoảng chấp nhận chênh lệch thời gian khi xác minh timestamp như thế nào?
Bạn xử lý đồng hồ hệ thống hai phía lệch nhau để tránh từ chối nhầm sự kiện hợp lệ ra sao?
Bạn kết hợp timestamp và event ID để phát hiện replay attack như thế nào?
Bạn lưu trữ khóa bí mật webhook ở phía gửi và phía nhận bằng cơ chế nào?
Bạn phân tách secret theo từng subscription hoặc tenant để giảm phạm vi ảnh hưởng khi lộ khóa ra sao?
Bạn xác định cách phân phối secret mới cho bên nhận mà không tiết lộ qua log như thế nào?
Bạn thiết kế quy trình xoay vòng HMAC secret với giai đoạn chấp nhận nhiều khóa như thế nào?
Bạn quy định hành vi khi secret hết hiệu lực nhưng vẫn còn retry của các sự kiện cũ ra sao?
Bạn lựa chọn dùng key ID trong signature header khi có nhiều khóa đang hoạt động ra sao?
Bạn kiểm tra HMAC bằng phép so sánh có thời gian tương đối cố định để giảm rủi ro nào?
Bạn xử lý signature header bị thiếu, sai định dạng hoặc không hỗ trợ thuật toán như thế nào?
Bạn xác định HTTP response phù hợp khi webhook không vượt qua bước xác minh chữ ký ra sao?
Bạn bảo đảm không xử lý nghiệp vụ trước khi hoàn tất xác minh chữ ký bằng cách nào?
Bạn thiết kế cách ghi log lỗi xác minh chữ ký mà không ghi secret hoặc dữ liệu nhạy cảm ra sao?
Bạn giải thích giới hạn của HMAC nếu một bên đã bị đánh cắp khóa bí mật như thế nào?
Bạn đánh giá sự khác nhau giữa HMAC và chữ ký bất đối xứng trong hệ thống webhook nhiều đối tác ra sao?
Bạn kiểm thử chữ ký HMAC với payload chứa Unicode, khoảng trắng và thứ tự field JSON khác nhau như thế nào?
Bạn xác minh timestamp chống replay khi nhiều delivery đến đồng thời như thế nào?
Bạn bảo vệ endpoint nhận webhook trước request giả mạo ngay cả khi URL bị công khai ra sao?
Bạn lựa chọn xác thực bổ sung như mTLS hoặc allowlist IP bên cạnh HMAC trong trường hợp nào?
Bạn quản lý việc thay đổi dải IP của bên gửi nếu sử dụng IP allowlist như thế nào?
Bạn áp dụng HTTPS và chính sách TLS cho endpoint webhook public như thế nào?
Bạn giới hạn dung lượng request body trước hoặc trong quá trình xác minh chữ ký ra sao?
Bạn giảm rủi ro từ Content-Type sai hoặc body chứa JSON không hợp lệ như thế nào?
Bạn xác định cách chống injection khi payload webhook được lưu vào database hoặc gửi sang hệ thống khác ra sao?
Bạn thiết kế chính sách bảo vệ dữ liệu cá nhân trong lịch sử webhook delivery như thế nào?
Bạn kiểm soát quyền truy cập dữ liệu webhook đã lưu tại dead-letter queue như thế nào?
Bạn quản lý thời gian lưu payload, log và thông tin chứng thực để đáp ứng yêu cầu bảo mật ra sao?
Bạn thiết kế một Spring Boot controller tiếp nhận webhook qua HTTP như thế nào?
Bạn lựa chọn @PostMapping và các điều kiện consumes để nhận đúng loại webhook ra sao?
Bạn nhận raw request body trong Spring MVC để phục vụ xác minh HMAC như thế nào?
Bạn sắp xếp filter, interceptor và controller để xác minh request trước khi xử lý nghiệp vụ ra sao?
Bạn kiểm soát trường hợp servlet input stream đã bị đọc trước khi verifier tính chữ ký như thế nào?
Bạn lựa chọn sử dụng byte[] hay String khi nhận body cần đối chiếu chữ ký HMAC như thế nào?
Bạn sử dụng thư viện mật mã Java để tính HMAC từ secret và raw body ra sao?
Bạn thiết kế lớp SignatureVerifier độc lập với controller để dễ kiểm thử như thế nào?
Bạn lấy secret theo subscription hoặc key ID trong lúc xác minh webhook như thế nào?
Bạn kiểm tra timestamp và định dạng signature header trong Spring controller ra sao?
Bạn sử dụng MessageDigest.isEqual hoặc cơ chế tương đương để so sánh chữ ký an toàn như thế nào?
Bạn xử lý các ngoại lệ phát sinh khi giải mã chữ ký hex hoặc Base64 ra sao?
Bạn tạo DTO và kiểm tra schema sau bước xác minh chữ ký như thế nào?
Bạn phân biệt lỗi chữ ký không hợp lệ với lỗi nghiệp vụ sau xác thực ra sao?
Bạn thiết kế API trả phản hồi 2xx khi sự kiện đã được ghi nhận bền vững như thế nào?
Bạn đưa webhook vào queue trước khi phản hồi để tránh request giữ kết nối lâu như thế nào?
Bạn lựa chọn cơ chế ghi bền sự kiện nhận được khi broker tạm thời không sẵn sàng ra sao?
Bạn tổ chức transaction giữa ghi inbox và enqueue công việc xử lý webhook như thế nào?
Bạn phân biệt dùng Spring MVC và WebFlux cho webhook receiver dựa vào mô hình tải như thế nào?
Bạn đọc raw DataBuffer trong Spring WebFlux mà vẫn quản lý bộ nhớ đúng cách ra sao?
Bạn bảo đảm không vô tình đọc body hai lần khi verify HMAC và deserialize trong WebFlux như thế nào?
Bạn áp dụng Bean Validation và xử lý lỗi schema payload trong controller như thế nào?
Bạn cấu hình giới hạn request size và timeout cho endpoint Spring tiếp nhận webhook như thế nào?
Bạn tách các thành phần controller, verifier, inbox repository và worker xử lý nghiệp vụ như thế nào?
Bạn xử lý propagation của correlation ID qua HTTP request, queue và background worker ra sao?
Bạn kiểm soát quyền truy cập vào actuator hoặc các endpoint quản trị khi mở webhook receiver ra Internet như thế nào?
Bạn tổ chức gửi webhook từ ứng dụng Spring bằng RestClient hoặc WebClient như thế nào?
Bạn lựa chọn cách tạo JSON payload trước khi ký và gửi để tránh thay đổi byte sau ký như thế nào?
Bạn xây dựng signature header cho một delivery attempt trong Spring như thế nào?
Bạn quyết định nên ký timestamp mới hay giữ timestamp cũ khi retry dựa vào hợp đồng nào?
Bạn truyền event ID cố định và delivery attempt ID khác nhau qua các lần gửi ra sao?
Bạn sử dụng timeout riêng cho từng endpoint nhận trong HTTP client như thế nào?
Bạn xử lý response HTTP trong Spring sender để quyết định thành công, retry hoặc bỏ qua ra sao?
Bạn cấu hình giới hạn connection pool khi sender gửi nhiều webhook đồng thời như thế nào?
Bạn chọn synchronous send hay enqueue trước khi gửi theo yêu cầu tính bền vững nào?
Bạn xây dựng outbox để sự kiện chỉ được phát sau khi giao dịch nghiệp vụ commit như thế nào?
Bạn xử lý trường hợp database commit thành công nhưng publisher không ghi được bản ghi delivery ra sao?
Bạn định nghĩa trạng thái queued, delivering, delivered và failed của từng delivery như thế nào?
Bạn lưu lịch sử từng attempt bao gồm thời gian, mã HTTP và nguyên nhân lỗi ra sao?
Bạn áp dụng cơ chế khóa hoặc claim job để nhiều worker không gửi trùng cùng attempt như thế nào?
Bạn xử lý worker gặp sự cố sau khi gửi nhưng trước khi lưu trạng thái delivered ra sao?
Bạn tối ưu hóa số lượng worker theo backlog và thời gian phản hồi của từng endpoint như thế nào?
Bạn lựa chọn cấu trúc queue riêng theo tenant hay dùng chung có giới hạn đồng thời ra sao?
Bạn thiết kế retry policy cho timeout, lỗi kết nối và HTTP 5xx như thế nào?
Bạn xử lý HTTP 408, 409, 410, 422 và 429 theo hợp đồng riêng của nhà cung cấp ra sao?
Bạn lựa chọn số lần gửi lại tối đa và khoảng thời gian retry dựa vào tiêu chí nào?
Bạn triển khai exponential backoff kèm jitter để tránh tăng tải đồng loạt như thế nào?
Bạn áp dụng Retry-After từ receiver mà vẫn tuân thủ thời hạn retry tối đa ra sao?
Bạn xác định hạn sử dụng của một webhook để không phát sự kiện đã quá cũ như thế nào?
Bạn tổ chức delayed queue hoặc scheduler để gửi lại mà không chiếm thread chờ như thế nào?
Bạn phát hiện và xử lý poison delivery liên tục thất bại như thế nào?
Bạn đưa delivery thất bại vĩnh viễn vào dead-letter queue với metadata nào?
Bạn xây dựng thao tác redrive hoặc replay webhook sau khi khắc phục sự cố như thế nào?
Bạn kiểm soát quyền thực hiện manual replay trong giao diện vận hành ra sao?
Bạn tránh phát lặp tác dụng phụ khi operator replay một sự kiện đã thành công như thế nào?
Bạn đánh giá lúc nào cần ngừng retry khi endpoint đã bị vô hiệu hóa hoặc subscription bị thu hồi?
Bạn xử lý sự cố toàn bộ đối tác trả HTTP 503 trong nhiều giờ mà không làm đầy hàng đợi ra sao?
Bạn giới hạn tốc độ gửi để một endpoint chậm không chiếm hết kết nối của các endpoint khác như thế nào?
Bạn phối hợp rate limiting, circuit breaker và retry cho webhook sender như thế nào?
Bạn phân biệt backpressure ở phía sender và giới hạn tải ở phía receiver ra sao?
Bạn thiết kế queue backlog alert khi tốc độ phát sự kiện vượt tốc độ gửi webhook như thế nào?
Bạn tính toán thời gian xả backlog dựa trên số worker, thời gian gửi và tỷ lệ lỗi ra sao?
Bạn xử lý event ID trùng lặp trong webhook receiver để bảo đảm nghiệp vụ chỉ thực thi một lần như thế nào?
Bạn chọn khóa idempotency theo event ID, event type và tenant dựa trên tiêu chí nào?
Bạn thiết kế unique constraint hoặc inbox table để chống xử lý trùng trong nhiều instance như thế nào?
Bạn xác định thời gian lưu khóa idempotency dựa vào cửa sổ retry và replay ra sao?
Bạn xử lý tình huống hai request trùng đến đồng thời trước khi bản ghi đầu tiên commit như thế nào?
Bạn phân biệt trạng thái received, processing, processed và failed của một event trong inbox như thế nào?
Bạn xử lý trường hợp công việc nghiệp vụ thành công nhưng chưa kịp ghi trạng thái processed ra sao?
Bạn xác định cách đáp lại sender khi nhận event ID đã xử lý trước đó như thế nào?
Bạn thiết kế xử lý webhook nhận sai thứ tự khi sự kiện cập nhật cùng một tài nguyên ra sao?
Bạn sử dụng version hoặc sequence number của tài nguyên để phát hiện sự kiện cũ như thế nào?
Bạn đánh giá giới hạn của việc dựa vào timestamp để khôi phục thứ tự sự kiện ra sao?
Bạn quyết định lúc nào cần giữ sự kiện chờ và lúc nào cần truy vấn trạng thái mới nhất từ provider?
Bạn xử lý một sự kiện xóa tài nguyên đến trước sự kiện tạo tài nguyên như thế nào?
Bạn bảo vệ tính nhất quán khi hai webhook cùng cập nhật một bản ghi trong database ra sao?
Bạn phân vùng công việc theo resource ID để giữ thứ tự cục bộ mà vẫn mở rộng consumer như thế nào?
Bạn xây dựng cơ chế đồng bộ lại dữ liệu khi phát hiện có khoảng trống trong sequence sự kiện như thế nào?
Bạn lựa chọn hành vi khi một sự kiện không thể xử lý nhưng các sự kiện sau vẫn đến ra sao?
Bạn thiết kế reconciliation job để kiểm tra dữ liệu nhận từ webhook so với hệ thống nguồn như thế nào?
Bạn sử dụng metrics nào để theo dõi tỷ lệ delivery thành công và thất bại theo event type?
Bạn đo delivery latency từ lúc event được tạo đến khi receiver xác nhận bằng cách nào?
Bạn phân biệt latency gửi HTTP và thời gian xử lý nghiệp vụ phía receiver trong dashboard như thế nào?
Bạn theo dõi số lần retry và độ tuổi của webhook lâu nhất chưa gửi thành công ra sao?
Bạn thiết kế dashboard hiển thị backlog, queue depth và trạng thái subscription như thế nào?
Bạn chọn những trường log nào để liên kết event, subscription, delivery và attempt mà không tiết lộ secret?
Bạn truyền trace ID qua webhook đến một hệ thống khác không cùng nền tảng tracing ra sao?
Bạn bảo vệ hệ thống giám sát khỏi nhãn metrics có cardinality cao như endpoint URL hay event ID ra sao?
Bạn thiết kế cảnh báo khi tỷ lệ signature verification failure đột ngột tăng như thế nào?
Bạn phân biệt lỗi HMAC do thay secret với lỗi do body bị biến đổi bằng các dấu hiệu nào?
Bạn điều tra tỷ lệ event trùng tăng cao sau một sự cố mạng như thế nào?
Bạn thiết kế runbook xử lý endpoint của đối tác liên tục timeout như thế nào?
Bạn kiểm soát retention của delivery log để vừa phục vụ kiểm toán vừa hạn chế lưu dữ liệu nhạy cảm ra sao?
Bạn kiểm thử Spring webhook receiver với request body và signature thật như thế nào?
Bạn tạo test vector HMAC cố định để xác nhận sender và receiver tương thích như thế nào?
Bạn kiểm thử signature không hợp lệ, timestamp quá hạn và header thiếu như thế nào?
Bạn kiểm thử raw body có khoảng trắng hoặc ký tự Unicode để phát hiện lỗi tính HMAC ra sao?
Bạn mô phỏng hai webhook trùng đến đồng thời để kiểm tra tính idempotent như thế nào?
Bạn kiểm thử sự kiện đến sai thứ tự khi cùng một tài nguyên thay đổi nhiều lần như thế nào?
Bạn kiểm thử receiver lưu inbox thành công nhưng worker xử lý nghiệp vụ thất bại như thế nào?
Bạn thiết kế integration test chứng minh HTTP 2xx chỉ trả sau khi nhận sự kiện bền vững ra sao?
Bạn mô phỏng webhook endpoint phản hồi 429 với Retry-After để kiểm tra lịch gửi lại như thế nào?
Bạn kiểm thử retry có backoff và jitter mà không cần chờ thời gian thực lâu như thế nào?
Bạn mô phỏng server nhận request rồi ngắt kết nối trước khi trả response để kiểm tra xử lý không chắc chắn ra sao?
Bạn kiểm thử sender không truy cập host nội bộ do subscription URL không đáng tin cậy bằng cách nào?
Bạn kiểm thử timeout và sự cố TLS khi kết nối tới endpoint webhook như thế nào?
Bạn thực hiện load test với lượng lớn event đồng thời và nhiều endpoint có tốc độ khác nhau ra sao?
Bạn kiểm thử redrive từ dead-letter queue để bảo đảm truy vết và quyền thao tác như thế nào?
Bạn kiểm tra schema compatibility khi nâng cấp payload webhook mà consumer cũ vẫn hoạt động ra sao?
Nếu webhook đã nhận HTTP 200 nhưng dữ liệu đích không được cập nhật, bạn sẽ truy nguyên theo các bước nào?
Nếu một đối tác báo chữ ký HMAC sai sau khi triển khai phiên bản mới, bạn sẽ kiểm tra đường đi của raw body như thế nào?
Nếu sender báo timeout nhưng receiver đã thực thi giao dịch, bạn sẽ thiết kế retry để tránh tác dụng phụ trùng ra sao?
Nếu nhiều bản sao Spring receiver cùng nhận một event ID, bạn sẽ xác minh cơ chế khóa và unique constraint nào?
Nếu subscription bị thu hồi khi queue còn hàng nghìn sự kiện chờ, bạn sẽ quyết định xử lý backlog ra sao?
Nếu một webhook cập nhật trạng thái cũ đến sau sự kiện mới, bạn sẽ bảo vệ dữ liệu cuối cùng như thế nào?
Nếu partner endpoint trả 503 trong sáu giờ, bạn sẽ bảo vệ tài nguyên sender và lên kế hoạch khôi phục ra sao?
Nếu webhook sender bị lợi dụng để gửi request đến địa chỉ metadata nội bộ, bạn sẽ sửa lớp kiểm tra endpoint như thế nào?
Nếu tỷ lệ HMAC failure tăng ngay sau khi xoay vòng khóa, bạn sẽ phân biệt lỗi cấu hình với tấn công ra sao?
Nếu retry scheduler gửi đồng thời hàng nghìn request khi đối tác phục hồi, bạn sẽ giảm đỉnh tải như thế nào?
Nếu backlog tăng dù HTTP delivery latency bình thường, bạn sẽ tìm nguyên nhân nghẽn trong pipeline ra sao?
Nếu receiver phải xử lý webhook chứa payload rất lớn, bạn sẽ giới hạn, xác minh và lưu dữ liệu thế nào?
Nếu một sự kiện không có schema version làm client cũ không deserialize được, bạn sẽ khôi phục hợp đồng như thế nào?
Nếu operator muốn replay toàn bộ webhook của một ngày, bạn sẽ bảo đảm lọc đúng phạm vi và ngăn xử lý trùng ra sao?
Nếu một webhook chứa dữ liệu khách hàng bị ghi vào log công khai, bạn sẽ khắc phục và ngăn tái diễn bằng cách nào?
Bạn thiết kế kế hoạch khôi phục toàn bộ luồng webhook sau khi cả queue và service nhận gặp sự cố như thế nào?

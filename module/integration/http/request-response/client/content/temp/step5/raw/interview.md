Bạn xác định tiêu chí nào khi lựa chọn HTTP request-response để tích hợp hai dịch vụ?
Bạn phân biệt trách nhiệm của HTTP client và HTTP server trong một giao dịch tích hợp như thế nào?
Bạn thiết kế một HTTP client dùng chung để nhiều thành phần ứng dụng tái sử dụng ra sao?
Bạn lựa chọn cách tách logic nghiệp vụ và logic gọi HTTP trong một ứng dụng Java như thế nào?
Bạn đánh giá những rủi ro nào khi ứng dụng phụ thuộc đồng bộ vào nhiều dịch vụ bên ngoài?
Bạn thiết kế giao diện client để che giấu chi tiết HTTP nhưng vẫn phản ánh đúng lỗi nghiệp vụ ra sao?
Bạn chọn hợp đồng API và các tiêu chuẩn nào trước khi bắt đầu hiện thực HTTP client?
Bạn phân biệt cơ chế request-response của HTTP với truyền sự kiện bất đồng bộ qua trường hợp nào?
Bạn cân nhắc những giới hạn gì khi dùng HTTP client cho một tác vụ chạy trong thời gian dài?
Bạn xác định mức độ tin cậy cần thiết cho từng lời gọi HTTP dựa trên tác động nghiệp vụ như thế nào?
Bạn phân biệt URI, URL và các thành phần scheme, authority, path, query, fragment như thế nào?
Bạn xây dựng URI có path parameter và query parameter mà không gây lỗi encoding ra sao?
Bạn xử lý các ký tự Unicode và ký tự đặc biệt trong query parameter như thế nào?
Bạn phân biệt percent-encoding của path và query với encoding của nội dung form như thế nào?
Bạn tránh lỗi double encoding khi truyền định danh đã chứa ký tự phần trăm ra sao?
Bạn áp dụng các nguyên tắc nào khi ghép base URI với đường dẫn tương đối?
Bạn chuẩn hóa cách xử lý trailing slash trong base URL và endpoint path như thế nào?
Bạn xác định khi nào query parameter được phép xuất hiện nhiều lần trong cùng một request?
Bạn xây dựng URI để bảo toàn dấu cộng, dấu cách và dấu gạch chéo trong giá trị đầu vào như thế nào?
Bạn kiểm soát độ dài URI khi gửi nhiều tiêu chí lọc hoặc danh sách định danh ra sao?
Bạn đánh giá những rủi ro bảo mật nào khi địa chỉ đích của HTTP client được lấy từ dữ liệu người dùng?
Bạn triển khai allowlist host và scheme để giảm nguy cơ SSRF như thế nào?
Bạn kiểm soát việc redirect sang host khác khi request mang thông tin xác thực ra sao?
Bạn xác định cách xử lý DNS rebinding khi HTTP client gọi các URL không đáng tin cậy ra sao?
Bạn quyết định sử dụng GET, POST, PUT, PATCH và DELETE dựa trên ngữ nghĩa thao tác nào?
Bạn phân biệt tính an toàn và tính idempotent của HTTP method như thế nào?
Bạn lựa chọn cách gửi lệnh có tác dụng phụ khi mạng có thể ngắt trước khi client nhận response ra sao?
Bạn thiết kế HTTP request body ở định dạng JSON để giữ hợp đồng dữ liệu ổn định như thế nào?
Bạn mô tả những khác biệt nào giữa request không có body và request có body rỗng?
Bạn lựa chọn Content-Type và Accept headers cho các endpoint trả nhiều định dạng như thế nào?
Bạn phân biệt request headers với response headers và trách nhiệm xử lý của mỗi bên ra sao?
Bạn sử dụng header Authorization, Accept và Content-Type đúng ngữ nghĩa như thế nào?
Bạn truyền correlation ID hoặc trace context để theo dõi một chuỗi request qua nhiều dịch vụ ra sao?
Bạn lựa chọn header tùy chỉnh cho hợp đồng tích hợp mà không trùng với tiêu chuẩn hiện có như thế nào?
Bạn đánh giá những rủi ro nào khi truyền dữ liệu nhạy cảm qua query string?
Bạn xử lý các giá trị header có ký tự xuống dòng hoặc dữ liệu không tin cậy như thế nào?
Bạn phân biệt cách sử dụng cookie và bearer token trong HTTP client dịch vụ với dịch vụ ra sao?
Bạn lựa chọn sử dụng request compression và response compression dựa trên những tiêu chí nào?
Bạn xử lý các phản hồi có Content-Encoding mà client cần giải nén như thế nào?
Bạn bảo đảm charset được xử lý nhất quán khi đọc văn bản từ response ra sao?
Bạn xác định giới hạn kích thước request và response để tránh dùng quá nhiều bộ nhớ như thế nào?
Bạn xử lý một response trả mã thành công nhưng Content-Type không phù hợp với hợp đồng ra sao?
Bạn phân biệt mã trạng thái 2xx, 3xx, 4xx và 5xx khi thiết kế quy tắc xử lý lỗi như thế nào?
Bạn giải thích trường hợp 200 OK, 201 Created, 202 Accepted và 204 No Content ảnh hưởng đến HTTP client ra sao?
Bạn thiết kế cách nhận Location header khi server tạo tài nguyên mới như thế nào?
Bạn xử lý response 204 không có body mà không gây lỗi giải mã như thế nào?
Bạn lựa chọn cách xử lý phản hồi 206 Partial Content cho dữ liệu tải theo khoảng byte ra sao?
Bạn phân biệt 400, 401, 403 và 404 để trả lỗi đúng tầng ứng dụng như thế nào?
Bạn xác định khi nào 409 Conflict hoặc 412 Precondition Failed cần được xử lý riêng trong client?
Bạn dùng 429 Too Many Requests và Retry-After để điều chỉnh tốc độ gọi API như thế nào?
Bạn phân biệt lỗi 502, 503 và 504 khi quyết định retry một request ra sao?
Bạn thiết kế bảng ánh xạ mã trạng thái HTTP sang exception hoặc kết quả nghiệp vụ như thế nào?
Bạn xử lý response có mã lỗi nhưng body rỗng hoặc không phải JSON như thế nào?
Bạn bảo vệ client khi server trả HTML error page thay cho cấu trúc lỗi dự kiến ra sao?
Bạn xác định những trường lỗi nào của response cần giữ để hỗ trợ chẩn đoán mà không lộ dữ liệu nhạy cảm?
Bạn xử lý nội dung phản hồi chứa trường không biết hoặc thiếu trường tùy chọn như thế nào?
Bạn thiết kế DTO riêng cho hợp đồng HTTP để tránh lệ thuộc mô hình dữ liệu nội bộ ra sao?
Bạn xử lý sai khác giữa null, field không có mặt và giá trị mặc định trong response như thế nào?
Bạn kiểm soát thay đổi enum value từ server mà client chưa nhận diện bằng cách nào?
Bạn phân biệt lỗi deserialization với lỗi nghiệp vụ được server trả về ra sao?
Bạn lựa chọn thời điểm kiểm tra schema phản hồi trước khi sử dụng dữ liệu dựa trên tiêu chí nào?
Bạn triển khai ETag và If-None-Match để giảm tải truy cập HTTP ra sao?
Bạn sử dụng If-Match để phòng tránh cập nhật đè lên dữ liệu đã thay đổi như thế nào?
Bạn mô tả cách HTTP caching ảnh hưởng đến tính mới của dữ liệu tích hợp như thế nào?
Bạn đánh giá nguy cơ lưu trữ response chứa thông tin cá nhân trong cache dùng chung ra sao?
Bạn chọn hành vi redirect của client dựa trên các mã 301, 302, 303, 307 và 308 như thế nào?
Bạn bảo toàn method và request body khi xử lý redirect trong những trường hợp nào?
Bạn giới hạn số lần redirect để ngăn vòng lặp và giảm rủi ro bảo mật ra sao?
Bạn lựa chọn cách xử lý HTTP version negotiation và fallback giữa HTTP/2 với HTTP/1.1 như thế nào?
Bạn giải thích lợi ích và giới hạn của HTTP/2 multiplexing đối với nhiều request đồng thời như thế nào?
Bạn xác định mức độ phụ thuộc của client vào tính năng riêng của một HTTP server như thế nào?
Bạn thiết lập xác thực Basic, bearer token hoặc mTLS theo đặc điểm hệ thống như thế nào?
Bạn lựa chọn OAuth 2.0 client credentials khi gọi API giữa hai dịch vụ trong trường hợp nào?
Bạn tổ chức lấy mới access token trước khi hết hạn mà không gây nhiều yêu cầu đồng thời ra sao?
Bạn xử lý tình huống access token bị từ chối trước thời điểm hết hạn dự kiến như thế nào?
Bạn kiểm soát phạm vi quyền của access token để mỗi HTTP client chỉ có quyền cần thiết ra sao?
Bạn bảo quản client secret và mật khẩu kết nối để tránh xuất hiện trong mã nguồn như thế nào?
Bạn triển khai xoay vòng secret mà vẫn duy trì các lời gọi đang chạy như thế nào?
Bạn cấu hình TLS trust store cho HTTP client Java theo yêu cầu triển khai ra sao?
Bạn kiểm tra chứng chỉ TLS của server và tên host để chống giả mạo như thế nào?
Bạn tổ chức client certificate cho mTLS và xử lý gia hạn chứng chỉ ra sao?
Bạn xử lý lỗi handshake TLS khác gì lỗi timeout hoặc kết nối bị từ chối?
Bạn lựa chọn mức TLS và cipher suite dựa trên yêu cầu tương thích và bảo mật nào?
Bạn thiết kế chính sách proxy cho HTTP client trong môi trường doanh nghiệp như thế nào?
Bạn xử lý xác thực proxy mà không để credentials rò rỉ sang server đích ra sao?
Bạn cấu hình DNS và chiến lược sử dụng nhiều địa chỉ IP của cùng một hostname ra sao?
Bạn đánh giá tác động của DNS cache tới hoạt động failover khi endpoint thay đổi địa chỉ như thế nào?
Bạn phân biệt lỗi DNS lookup với lỗi TCP connect và lỗi HTTP response như thế nào?
Bạn quyết định truyền tên host qua cấu hình thay vì hardcode trong Java code như thế nào?
Bạn lựa chọn JDK HttpClient thay cho thư viện bên ngoài dựa trên những tiêu chí nào?
Bạn xây dựng HttpClient bất biến và tái sử dụng qua nhiều request như thế nào?
Bạn dùng HttpRequest.Builder để thiết lập URI, method, headers và body ra sao?
Bạn lựa chọn BodyPublishers.ofString, ofFile hoặc ofInputStream cho các loại payload nào?
Bạn thiết kế cách phát lại request body khi một attempt được gửi lại như thế nào?
Bạn sử dụng BodyHandlers.ofString, ofByteArray và ofFile theo kích thước phản hồi ra sao?
Bạn lựa chọn BodyHandlers.ofInputStream khi xử lý phản hồi lớn như thế nào?
Bạn quản lý vòng đời InputStream của response để giải phóng tài nguyên đúng thời điểm ra sao?
Bạn phân biệt HttpClient.send và sendAsync trong mô hình xử lý yêu cầu như thế nào?
Bạn tổ chức CompletableFuture để phối hợp các lời gọi HTTP độc lập mà không chặn thread ra sao?
Bạn xử lý exception và cancellation trong chuỗi CompletionStage như thế nào?
Bạn quyết định sử dụng executor tùy chỉnh cho JDK HttpClient dựa trên yêu cầu tài nguyên nào?
Bạn phân biệt connectTimeout ở HttpClient với timeout cho mỗi HttpRequest như thế nào?
Bạn đánh giá những giới hạn của timeout trên JDK HttpClient khi muốn áp đặt ngân sách thời gian tổng thể ra sao?
Bạn cấu hình chính sách followRedirects của JDK HttpClient để tránh gửi lộ token như thế nào?
Bạn sử dụng Authenticator của JDK HttpClient cho các cơ chế hỗ trợ sẵn trong trường hợp nào?
Bạn cấu hình SSLContext riêng cho JDK HttpClient mà vẫn giữ kiểm tra danh tính peer ra sao?
Bạn truyền HTTP version preference trong JDK HttpClient và đánh giá kết quả thực tế như thế nào?
Bạn thiết kế cách hủy một lời gọi sendAsync khi request cấp trên đã kết thúc ra sao?
Bạn xử lý InterruptedException và bảo toàn interrupt flag khi gọi HttpClient.send như thế nào?
Bạn phân loại HttpTimeoutException, ConnectException và lỗi IO khác khi sử dụng JDK HttpClient như thế nào?
Bạn tổ chức đóng hoặc tái sử dụng các tài nguyên của HttpClient phù hợp với phiên bản JDK như thế nào?
Bạn thực hiện streaming dữ liệu với BodyPublisher và BodySubscriber khi không thể giữ toàn bộ payload trong RAM ra sao?
Bạn kiểm thử JDK HttpClient với server giả lập để xác minh header và body thực tế như thế nào?
Bạn lựa chọn RestClient của Spring thay cho JDK HttpClient khi ứng dụng dùng Spring Boot trong trường hợp nào?
Bạn sử dụng RestClient.Builder để cấu hình baseUrl, default headers và converters như thế nào?
Bạn quyết định tạo RestClient dùng chung hay client riêng cho từng dịch vụ phụ thuộc ra sao?
Bạn dùng RestClient để gửi GET kèm query parameter và nhận DTO như thế nào?
Bạn tạo request POST hoặc PATCH bằng RestClient và cấu hình content type ra sao?
Bạn phân biệt retrieve và exchange của RestClient khi cần tự xử lý trạng thái response như thế nào?
Bạn cấu hình defaultStatusHandler để phân loại lỗi HTTP theo quy tắc chung ra sao?
Bạn xử lý response 404 là kết quả không tìm thấy thay vì exception trong client adapter như thế nào?
Bạn sử dụng HttpMessageConverter của Spring để giải mã JSON theo cấu hình chung như thế nào?
Bạn lựa chọn request factory cho RestClient dựa trên khả năng quản lý kết nối và timeout nào?
Bạn thiết lập connect timeout và read timeout cho RestClient theo HTTP stack thực tế ra sao?
Bạn triển khai ClientHttpRequestInterceptor để gắn trace ID và token vào request như thế nào?
Bạn thiết kế interceptor để không vô tình đọc hoặc lưu toàn bộ body nhạy cảm ra sao?
Bạn phân biệt quan sát request ở interceptor và xử lý lỗi trong status handler như thế nào?
Bạn kiểm soát trạng thái client khi RestClient được dùng đồng thời từ nhiều luồng như thế nào?
Bạn sử dụng MockRestServiceServer để kiểm thử request được tạo bởi RestClient như thế nào?
Bạn quyết định giữ API trả kết quả đồng bộ khi gọi RestClient hay bọc bằng async adapter theo tiêu chí nào?
Bạn chọn WebClient của Spring WebFlux khi cần nhiều request I/O đồng thời như thế nào?
Bạn dùng WebClient.Builder để cấu hình baseUrl, default headers và codec như thế nào?
Bạn tạo WebClient theo từng upstream service để kiểm soát cấu hình độc lập như thế nào?
Bạn phân biệt retrieve với exchangeToMono trong WebClient khi đọc status và body ra sao?
Bạn ánh xạ một response thành Mono DTO và xử lý danh sách từ Flux như thế nào?
Bạn tổ chức onStatus để ánh xạ 4xx và 5xx thành lỗi nghiệp vụ thích hợp ra sao?
Bạn sử dụng ExchangeFilterFunction để bổ sung xác thực và quan sát request như thế nào?
Bạn giải thích tính lazy của WebClient Mono và ảnh hưởng của mỗi lần subscribe tới request như thế nào?
Bạn xử lý chuỗi WebClient không được subscribe nên không có request gửi đi ra sao?
Bạn tránh sử dụng block trong event loop của ứng dụng WebFlux như thế nào?
Bạn xử lý thư viện blocking bên trong pipeline reactive để không làm nghẽn scheduler quan trọng ra sao?
Bạn lựa chọn map, flatMap và zip khi phối hợp nhiều lời gọi WebClient theo quan hệ dữ liệu nào?
Bạn giới hạn mức đồng thời của flatMap để tránh dồn quá nhiều yêu cầu lên upstream như thế nào?
Bạn thiết kế timeout trên WebClient cho kết nối, nhận phản hồi và toàn bộ pipeline ra sao?
Bạn phân biệt timeout của Reactor với timeout tại tầng Netty HTTP client như thế nào?
Bạn thực hiện retryWhen có giới hạn theo loại lỗi và tính idempotent của operation ra sao?
Bạn truyền Reactor Context để giữ dữ liệu tracing và bảo mật qua các operator như thế nào?
Bạn kiểm soát vòng đời subscription để hủy network request khi downstream không còn cần kết quả ra sao?
Bạn xử lý response body lớn theo luồng với Flux<DataBuffer> mà không tạo rò rỉ bộ nhớ như thế nào?
Bạn xác định maxInMemorySize cho codec của WebClient dựa trên kích thước payload nào?
Bạn phân biệt cold publisher và shared publisher khi nhiều nơi cùng sử dụng kết quả HTTP như thế nào?
Bạn thiết lập Reactor Netty connection pool cho WebClient theo lưu lượng và giới hạn upstream ra sao?
Bạn lựa chọn HttpClient connector cho WebClient để hỗ trợ proxy, TLS và connection management như thế nào?
Bạn thiết kế luồng tải file lớn qua WebClient khi client có thể hủy giữa chừng ra sao?
Bạn dùng StepVerifier để kiểm thử kết quả và luồng lỗi của pipeline reactive như thế nào?
Bạn dùng MockWebServer hoặc server HTTP giả lập để xác nhận WebClient gửi request thực tế ra sao?
Bạn phân biệt connect timeout, response timeout và read timeout theo thời điểm phát sinh như thế nào?
Bạn xác định ngân sách thời gian tổng thể cho một lời gọi gồm DNS, connect, TLS, gửi và nhận ra sao?
Bạn phân bổ timeout cho từng dependency khi một tác vụ cần gọi nhiều HTTP API nối tiếp như thế nào?
Bạn quản lý thời gian chờ trên client khi upstream có queue nội bộ và xử lý chậm như thế nào?
Bạn đánh giá tác động của request timeout quá ngắn tới số lượng retry và tải lên server như thế nào?
Bạn xử lý socket timeout khi request có thể đã được server thực thi thành công ra sao?
Bạn xác định thời điểm có thể retry khi client nhận connection reset trong lúc gửi body như thế nào?
Bạn phân biệt lỗi connection refused và connection reset khi điều tra sự cố mạng như thế nào?
Bạn giải thích connection pooling giúp giảm chi phí thiết lập TCP và TLS như thế nào?
Bạn xác định kích thước connection pool dựa trên throughput, latency và số request đồng thời ra sao?
Bạn quan sát hàng đợi chờ connection và giới hạn pending acquire để tránh quá tải như thế nào?
Bạn điều chỉnh connection idle timeout để cân bằng tái sử dụng và kết nối stale như thế nào?
Bạn thiết kế cách phản ứng khi server đóng kết nối keep-alive mà client định tái sử dụng ra sao?
Bạn quản lý vòng đời connection pool khi ứng dụng shutdown hoặc reload cấu hình như thế nào?
Bạn xác định giới hạn đồng thời riêng cho từng upstream để một dịch vụ lỗi không chiếm hết tài nguyên như thế nào?
Bạn phân biệt giới hạn số TCP connection với giới hạn số stream đồng thời trong HTTP/2 ra sao?
Bạn đánh giá khả năng cạn ephemeral ports khi ứng dụng tạo kết nối mới liên tục như thế nào?
Bạn theo dõi DNS, TCP, TLS, time to first byte và đọc body để tìm nguyên nhân request chậm ra sao?
Bạn xử lý client bị treo vì chờ connection pool dù network và server đều hoạt động như thế nào?
Bạn thiết kế chính sách retry phù hợp với GET idempotent và POST tạo giao dịch như thế nào?
Bạn phân biệt lỗi tạm thời và lỗi vĩnh viễn dựa trên HTTP status và loại exception ra sao?
Bạn chọn số lần retry tối đa dựa trên ngân sách thời gian và nguy cơ quá tải nào?
Bạn triển khai exponential backoff và jitter để tránh nhiều client retry đồng thời ra sao?
Bạn sử dụng Retry-After để điều chỉnh lịch retry và xử lý các kiểu giá trị khác nhau như thế nào?
Bạn tính tổng thời gian của các attempt, delay và timeout sao cho không vượt deadline nghiệp vụ ra sao?
Bạn thiết kế idempotency key cho request tạo thanh toán khi phải gửi lại như thế nào?
Bạn xử lý trường hợp client mất response sau khi server đã commit dữ liệu mà không biết kết quả ra sao?
Trong những điều kiện nào response 500 không nên được retry dù thao tác có vẻ idempotent?
Bạn tránh retry chồng lên retry của gateway, client và service layer như thế nào?
Bạn xác định cách truyền cancellation và deadline từ request đầu vào sang các request downstream như thế nào?
Bạn thiết kế circuit breaker để giảm tải khi upstream thường xuyên lỗi hoặc chậm như thế nào?
Bạn chọn tiêu chí failure rate hoặc slow call rate cho circuit breaker ra sao?
Bạn phân biệt open, half-open và closed của circuit breaker và ảnh hưởng đến request như thế nào?
Bạn điều chỉnh bulkhead để giới hạn tài nguyên của từng lời gọi phụ thuộc ra sao?
Bạn áp dụng rate limiting ở HTTP client nhằm tôn trọng quota của upstream như thế nào?
Bạn phối hợp concurrency limit, retry và circuit breaker để không tạo phản ứng dây chuyền ra sao?
Bạn đánh giá trade-off của fallback trả dữ liệu cache khi upstream đang lỗi như thế nào?
Bạn phân biệt fallback an toàn với fallback có thể che giấu lỗi nghiệp vụ nghiêm trọng ra sao?
Bạn dùng hedged requests trong trường hợp nào và kiểm soát chi phí tăng tải như thế nào?
Bạn bảo đảm quá trình retry không tái sử dụng stream body đã bị tiêu thụ như thế nào?
Bạn thiết kế cơ chế bảo vệ khỏi thundering herd khi upstream vừa phục hồi ra sao?
Bạn lập kế hoạch khi một dịch vụ bên ngoài giới hạn quota theo phút và hệ thống có lưu lượng đột biến như thế nào?
Bạn cấu hình client theo từng upstream để khác nhau về timeout, retries và connection pool như thế nào?
Bạn đưa các tham số resilience vào cấu hình và kiểm soát thay đổi khi triển khai ra sao?
Bạn lựa chọn thông tin HTTP request và response nào để ghi log nhằm hỗ trợ điều tra sự cố?
Bạn che giấu Authorization header, cookie và dữ liệu cá nhân trong log HTTP như thế nào?
Bạn giữ correlation ID xuyên qua request đồng bộ và luồng xử lý async như thế nào?
Bạn tạo distributed tracing spans cho từng outbound HTTP call và liên kết với trace cha ra sao?
Bạn thiết kế metrics theo upstream, method, status và nhóm lỗi mà không tăng cardinality quá lớn như thế nào?
Bạn đo p50, p95 và p99 latency để phát hiện những loại suy giảm hiệu năng nào?
Bạn xây dựng dashboard về active connections, pending acquires, timeout và retries như thế nào?
Bạn phân biệt service latency với network latency khi phân tích trace của HTTP client ra sao?
Bạn thiết kế cảnh báo dựa trên tỷ lệ thành công, độ trễ và retry amplification như thế nào?
Bạn dùng structured logging để ghép request lỗi với cấu hình client và attempt number ra sao?
Bạn kiểm soát log của response body lớn hoặc body chứa dữ liệu nhạy cảm ra sao?
Bạn kiểm thử HTTP client với server mô phỏng thay vì chỉ mock trực tiếp phương thức Java như thế nào?
Bạn tạo tình huống server trả 401, 403 và 429 để xác minh quy tắc xử lý của client ra sao?
Bạn kiểm thử request builder để phát hiện lỗi encode ký tự Unicode và query parameter như thế nào?
Bạn mô phỏng response bị ngắt giữa chừng và xác định client xử lý dữ liệu dở như thế nào?
Bạn mô phỏng kết nối TCP được chấp nhận nhưng server không gửi response để kiểm tra timeout ra sao?
Bạn mô phỏng DNS failure hoặc connection refused trong integration test và xác minh exception ra sao?
Bạn kiểm thử retry có exponential backoff mà không phải chờ thời gian thực quá lâu như thế nào?
Bạn thiết kế test xác minh một POST không idempotent không bị tự động gửi lặp ra sao?
Bạn kiểm thử redirect sang host khác để xác minh header nhạy cảm không bị chuyển tiếp như thế nào?
Bạn kiểm thử certificate hết hạn hoặc hostname mismatch mà không tắt TLS verification ra sao?
Bạn mô phỏng nhiều request đồng thời để đo giới hạn connection pool và queue chờ như thế nào?
Bạn kiểm thử cancellation để xác minh các tài nguyên network và subscription được giải phóng ra sao?
Bạn so sánh số connection và throughput của JDK HttpClient, RestClient và WebClient bằng bài test nào?
Bạn thiết kế kiểm thử contract cho cấu trúc response của upstream khi schema thay đổi như thế nào?
Bạn kiểm thử khả năng giải mã response lỗi có body rỗng hoặc định dạng bất thường ra sao?
Bạn dùng fault injection để kiểm tra client khi mạng có packet loss hoặc latency biến động như thế nào?
Bạn thiết kế load test khi upstream trả 503 trong một khoảng thời gian để quan sát retry amplification ra sao?
Bạn xác định điều kiện pass/fail của bài kiểm thử HTTP client về độ trễ, độ tin cậy và sử dụng tài nguyên như thế nào?
Nếu yêu cầu thanh toán bị timeout sau khi server có thể đã xử lý, bạn sẽ điều tra và ngăn giao dịch trùng như thế nào?
Nếu hệ thống báo connection pool exhausted dù upstream trả rất nhanh, bạn sẽ kiểm tra những nguyên nhân nào?
Nếu WebClient tạo request nhưng không có lưu lượng mạng, bạn sẽ khoanh vùng nguyên nhân trong reactive pipeline ra sao?
Nếu RestClient nhận 200 nhưng không đọc được JSON, bạn sẽ phân biệt lỗi contract và lỗi cấu hình converter như thế nào?
Nếu một API vừa chuyển sang HTTPS và client báo lỗi chứng chỉ, bạn sẽ xử lý và xác minh thế nào?
Nếu latency p99 tăng mạnh sau khi bật retry, bạn sẽ phân tích số attempt và ngân sách thời gian ra sao?
Nếu server trả 429 kèm Retry-After nhưng client liên tục gọi lại, bạn sẽ sửa chính sách client như thế nào?
Nếu một đợt triển khai làm hàng nghìn client reconnect cùng lúc, bạn sẽ giảm tải lên upstream bằng cách nào?
Nếu DNS của upstream đổi địa chỉ trong khi client vẫn gọi IP cũ, bạn sẽ phân tích cache và vòng đời connection ra sao?
Nếu request được redirect từ HTTPS sang HTTP, bạn sẽ quyết định hành vi client theo quy tắc bảo mật nào?
Nếu một response streaming bị hủy giữa chừng, bạn sẽ xác minh tài nguyên đã được giải phóng ra sao?
Nếu endpoint có tỷ lệ 504 tăng nhưng 5xx ở service đích không tăng, bạn sẽ điều tra các lớp trung gian nào?
Nếu quá trình refresh access token bị lỗi, bạn sẽ ngăn đồng thời nhiều request gửi token đã hết hạn như thế nào?
Nếu cùng một thao tác chạy thành công qua JDK HttpClient nhưng thất bại qua WebClient, bạn sẽ so sánh cấu hình và wire behavior nào?
Nếu upstream trở lại sau sự cố dài, bạn sẽ khôi phục lưu lượng client từng bước như thế nào?
Bạn thiết kế runbook xử lý khi HTTP client liên tục timeout và lỗi retry tăng trong giờ cao điểm ra sao?

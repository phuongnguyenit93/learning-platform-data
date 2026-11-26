Bạn giải thích mục tiêu của Spring Cloud Function khi tách logic nghiệp vụ khỏi giao thức giao tiếp như thế nào?
Bạn phân biệt hàm nghiệp vụ tái sử dụng với REST controller hoặc message listener về trách nhiệm ra sao?
Bạn chọn Supplier, Function hay Consumer dựa trên số lượng đầu vào và đầu ra của một tác vụ như thế nào?
Bạn giải thích hợp đồng đầu vào và đầu ra của java.util.function.Supplier trong một ứng dụng Spring như thế nào?
Bạn thiết kế một Function chuyển đổi dữ liệu mà không phụ thuộc trực tiếp vào HTTP hoặc broker ra sao?
Bạn sử dụng Consumer cho một tác vụ có side effect nhưng không tạo kết quả trả về theo nguyên tắc nào?
Bạn phân biệt hàm thuần không có side effect với hàm cập nhật trạng thái khi thiết kế hệ thống tích hợp ra sao?
Bạn xác định thành phần nào nên chịu trách nhiệm validation trước khi gọi một Function nghiệp vụ như thế nào?
Bạn tổ chức package và module cho các hàm dùng chung giữa ứng dụng web và serverless như thế nào?
Bạn đánh giá trade-off khi dùng functional bean thay cho service interface truyền thống ra sao?
Bạn quản lý dependency của một functional bean thông qua constructor injection hoặc bean factory như thế nào?
Bạn định nghĩa một bean Function trong Spring Boot và bảo đảm tên bean dễ tra cứu ra sao?
Bạn lựa chọn trả về object có cấu trúc thay vì String từ một Function dựa trên yêu cầu contract nào?
Bạn lựa chọn kiểu dữ liệu bất biến cho đầu vào và đầu ra để hạn chế side effect như thế nào?
Bạn phân biệt lỗi dữ liệu đầu vào với lỗi nghiệp vụ trong một hàm tái sử dụng ra sao?
Bạn đánh giá khả năng kiểm thử một Function thuần Java mà không cần khởi động Spring context như thế nào?
Bạn thiết kế một hàm chuẩn hóa dữ liệu có thể chạy qua nhiều loại adapter mà không thay đổi code ra sao?
Bạn xác định ranh giới transaction của một hàm được gọi qua nhiều giao thức khác nhau như thế nào?
Bạn xử lý thông tin tenant và correlation ID khi một hàm không biết nguồn gọi là HTTP hay message broker ra sao?
Bạn so sánh một hàm đồng bộ với hàm trả về Mono hoặc Flux về quản lý tài nguyên như thế nào?
Bạn lựa chọn hàm xử lý một bản ghi hoặc một luồng bản ghi theo đặc điểm workload nào?
Bạn tổ chức functional core và imperative shell để dễ kiểm thử tính đúng đắn nghiệp vụ như thế nào?
Bạn xác định trường hợp không nên dùng Supplier để đại diện cho tác vụ cần một yêu cầu đầu vào cụ thể ra sao?
Bạn phân biệt chức năng của Function và cơ chế scheduling kích hoạt nó trong một ứng dụng như thế nào?
Bạn xây dựng hợp đồng lỗi thống nhất để adapter HTTP và adapter messaging diễn giải cùng một exception ra sao?
Bạn giải thích FunctionCatalog đóng vai trò gì trong Spring Cloud Function như thế nào?
Bạn phân biệt bean registry thông thường của Spring với FunctionCatalog về cách lookup và gọi hàm ra sao?
Bạn kiểm tra một Function bean đã được Spring Cloud Function phát hiện và đăng ký bằng cách nào?
Bạn lựa chọn quy ước đặt tên cho các functional beans để tránh trùng tên giữa nhiều module ra sao?
Bạn sử dụng FunctionCatalog.lookup để lấy hàm cần thực thi dựa trên tên logic như thế nào?
Bạn xử lý tình huống lookup một tên không tồn tại hoặc không phù hợp kiểu hàm dự kiến ra sao?
Bạn xác định điều gì xảy ra khi ứng dụng có nhiều Supplier, Function và Consumer nhưng chưa chọn function definition rõ ràng?
Bạn phân biệt tên bean của một hàm với tên route hoặc binding bên ngoài ứng dụng ra sao?
Bạn dùng configuration properties để quyết định hàm nào được expose trong một adapter như thế nào?
Bạn kiểm chứng FunctionCatalog trả về hàm có thể gọi với payload mong đợi theo cách nào?
Bạn đánh giá vai trò của generic type metadata trong việc chuyển đổi payload khi gọi hàm từ catalog ra sao?
Bạn xử lý trường hợp generic type bị mất thông tin runtime do type erasure như thế nào?
Bạn sử dụng FunctionRegistration khi cần đăng ký một hàm không được suy luận type đầy đủ như thế nào?
Bạn lựa chọn cách cung cấp Type hoặc parameterized type information cho một function registration theo phiên bản nào?
Bạn phân biệt hàm được đăng ký bằng Spring bean với hàm được đăng ký theo cách lập trình qua catalog ra sao?
Bạn thiết kế runtime selection của một hàm theo cấu hình mà không cho người dùng tự chọn bất kỳ bean nội bộ nào ra sao?
Bạn giới hạn tập các hàm có thể được gọi từ bên ngoài để tránh expose logic quản trị nhạy cảm như thế nào?
Bạn kiểm tra sự khác biệt giữa function name resolution trong local test và khi đóng gói serverless ra sao?
Bạn phân biệt tên hiển thị của một composite function với các tên thành phần trong catalog như thế nào?
Bạn xử lý lỗi startup khi functional bean phụ thuộc vào bean cấu hình chưa được tạo ra sao?
Bạn đánh giá khi nào việc đăng ký quá nhiều functional beans trong cùng một ứng dụng làm khó quản trị ra sao?
Bạn thiết kế versioning cho function names khi hai thế hệ contract phải chạy song song như thế nào?
Bạn xác định cách kiểm thử catalog sau khi refactor tên method hoặc tên bean mà không làm hỏng adapter cũ ra sao?
Bạn thiết kế fallback khi một tên function được cấu hình sai trong production như thế nào?
Bạn phân biệt FunctionCatalog với một hệ thống service discovery hoặc registry mạng như thế nào?
Bạn giải thích nguyên tắc composition giữa hai Function khi đầu ra hàm trước làm đầu vào hàm sau ra sao?
Bạn tạo một chuỗi hàm validate, transform và enrich bằng cấu hình composition như thế nào?
Bạn kiểm tra kiểu dữ liệu đầu ra của hàm đầu có tương thích đầu vào của hàm kế tiếp như thế nào?
Bạn đánh giá rủi ro khi composition dựa trên raw Object làm lỗi kiểu dữ liệu chỉ xuất hiện lúc chạy ra sao?
Bạn xác định trường hợp Supplier có thể tham gia một chuỗi composition theo quy tắc nào?
Bạn lựa chọn Consumer ở cuối pipeline composition khi không cần tạo output như thế nào?
Bạn xử lý thông tin lỗi khi một hàm giữa chuỗi composition ném exception ra sao?
Bạn thiết kế các hàm nhỏ để có thể ghép lại mà vẫn duy trì ranh giới nghiệp vụ rõ ràng như thế nào?
Bạn phân biệt composition khai báo trước với routing chọn hàm theo điều kiện runtime như thế nào?
Bạn quyết định khi nào cần một composite function thay vì một Function lớn duy nhất theo tiêu chí nào?
Bạn kiểm thử kết quả composite function độc lập với kiểm thử từng component function ra sao?
Bạn phát hiện một hàm trong composition làm biến đổi input object được dùng lại ở bước khác như thế nào?
Bạn quản lý transaction khi hai hàm được composition nhưng thao tác vào hai hệ thống dữ liệu khác nhau ra sao?
Bạn đánh giá ảnh hưởng của thứ tự composition lên validation và quyền truy cập dữ liệu như thế nào?
Bạn thiết kế cách truyền metadata qua nhiều hàm để không đánh mất context tracing ra sao?
Bạn kiểm soát số lần gọi HTTP bên ngoài khi một composite function có nhiều bước enrich như thế nào?
Bạn xử lý timeout tổng thể khi mỗi hàm trong chuỗi có deadline riêng ra sao?
Bạn xây dựng quy trình rollback một thay đổi composition khiến kiểu dữ liệu không còn tương thích như thế nào?
Bạn xác định khả năng tái sử dụng cùng một hàm trong nhiều composition khác nhau như thế nào?
Bạn phân biệt pipeline composition của Spring Cloud Function với IntegrationFlow của Spring Integration theo nhu cầu nào?
Bạn kiểm tra log và metrics để biết bước nào trong composite function gây lỗi hoặc chậm ra sao?
Bạn lựa chọn type-safe adapter khi ghép các hàm có DTO của hai bounded contexts ra sao?
Bạn thiết kế composite function có hành vi idempotent khi hệ thống gọi lại toàn bộ pipeline như thế nào?
Bạn quản lý version của một function component khi các composition khác nhau đang dùng nó như thế nào?
Bạn thử nghiệm một composition mới trên tập dữ liệu chuẩn trước khi đổi function definition ra sao?
Bạn giải thích mục đích của RoutingFunction khi một request có thể cần nhiều hàm xử lý như thế nào?
Bạn phân biệt routing dựa trên message header với routing dựa trên thuộc tính payload ra sao?
Bạn xác định phương án truyền route metadata từ HTTP adapter sang hàm xử lý theo cách nào?
Bạn kiểm soát function routing expressions để input không tin cậy không truy cập các chức năng không được phép như thế nào?
Bạn xây dựng allowlist function names trước khi cho phép route được chọn từ request như thế nào?
Bạn thiết kế hành vi khi route không tìm được hàm tương ứng trong FunctionCatalog ra sao?
Bạn phân biệt cấu hình routing cố định với lựa chọn route động cho từng message như thế nào?
Bạn đánh giá rủi ro routing một message vào Consumer có side effect khi chỉ định route sai như thế nào?
Bạn xử lý việc thay đổi quy tắc routing trong quá trình rolling deployment nhiều phiên bản như thế nào?
Bạn kiểm thử nhiều loại routing keys để không có nhánh nghiệp vụ bị bỏ sót như thế nào?
Bạn phân biệt payload thuần với Message<T> khi một function cần nội dung và headers như thế nào?
Bạn xác định khi nào một Function nên nhận Message<DTO> thay vì DTO trực tiếp ra sao?
Bạn bảo toàn correlation ID và tenant ID khi biến đổi Message payload qua nhiều bước như thế nào?
Bạn đánh giá rủi ro sao chép toàn bộ headers từ message bên ngoài sang message trả về như thế nào?
Bạn thiết kế danh sách headers được phép giữ hoặc thay đổi trong một transformer ra sao?
Bạn phân biệt business metadata trong payload với transport metadata ở headers như thế nào?
Bạn lựa chọn content type phù hợp khi payload là JSON, plain text hoặc binary như thế nào?
Bạn giải thích vai trò của MessageConverter khi adapter truyền byte[] nhưng hàm mong đợi DTO ra sao?
Bạn xử lý lỗi JSON deserialization trước khi logic của Function được gọi như thế nào?
Bạn kiểm tra generic type của Function ảnh hưởng đến conversion của List<DTO> hoặc collection như thế nào?
Bạn xây dựng adapter chuyển JSON field thiếu hoặc unknown field theo chính sách tương thích nào?
Bạn xác định khi nào cần validation bean trên DTO sau bước deserialization ra sao?
Bạn phân biệt lỗi schema không hợp lệ với lỗi nghiệp vụ có thể retry khi xử lý message như thế nào?
Bạn xử lý kiểu dữ liệu ngày giờ và múi giờ khi một payload đi qua HTTP và broker như thế nào?
Bạn thiết kế quy ước serialization cho số tiền hoặc decimal để không mất độ chính xác ra sao?
Bạn phân biệt null payload, empty payload và message vắng dữ liệu trong contract như thế nào?
Bạn kiểm thử function với Unicode tiếng Việt và ký tự đặc biệt khi adapter dùng JSON như thế nào?
Bạn thiết kế mapping giữa event schema từ bên ngoài và domain DTO nội bộ như thế nào?
Bạn tránh lưu raw secret hoặc access token trong message headers được chuyển qua nhiều adapter ra sao?
Bạn xử lý headers không tương thích giữa các adapter bằng quy tắc chuẩn hóa nào?
Bạn quyết định khi nào một Function cần trả Message<Output> để tùy biến headers đầu ra ra sao?
Bạn đánh giá cách Message headers được chuyển tiếp khi composite functions thay đổi kiểu payload như thế nào?
Bạn xây dựng contract test kiểm tra content type và payload conversion giữa producer và consumer như thế nào?
Bạn phân biệt chuyển đổi kiểu của Spring Cloud Function với serialization do broker client thực hiện ra sao?
Bạn thiết kế cơ chế version hóa message contract để client cũ vẫn gọi được function mới như thế nào?
Bạn xử lý input không mong đợi khi runtime function signature dùng kiểu tổng quát Object như thế nào?
Bạn kiểm tra dữ liệu đã được convert đúng trước khi thực hiện side effect không thể hoàn tác ra sao?
Bạn lựa chọn xử lý input batch trong một Function thay cho nhiều lời gọi đơn lẻ dựa trên tải nào?
Bạn thiết kế response DTO ổn định để không lộ entity persistence hoặc internal exception ra sao?
Bạn kiểm soát giới hạn kích thước payload trước khi chuyển đổi và thực thi function như thế nào?
Bạn giải thích cách Spring Cloud Function web adapter expose một function qua HTTP như thế nào?
Bạn cấu hình một ứng dụng Spring Boot có Spring Cloud Function web adapter theo điều kiện nào?
Bạn phân biệt một route HTTP được web adapter tạo ra với route do @RestController tự định nghĩa ra sao?
Bạn kiểm tra các function nào thực sự được expose qua web adapter sau khi ứng dụng khởi động như thế nào?
Bạn lựa chọn HTTP method và request body phù hợp cho một Function có input và output như thế nào?
Bạn đánh giá cách gọi Supplier không có input qua HTTP theo contract của adapter đang sử dụng ra sao?
Bạn phân biệt hành vi HTTP của Consumer không có output với Function có response như thế nào?
Bạn thiết kế mapping HTTP status cho validation failure và business failure khi tái sử dụng cùng một hàm ra sao?
Bạn quản lý Content-Type và Accept khi client gửi JSON hoặc text tới web function như thế nào?
Bạn kiểm soát CORS và CSRF cho các function endpoints được gọi từ trình duyệt ra sao?
Bạn cấu hình authentication cho web-exposed function mà không nhúng Spring Security vào functional core như thế nào?
Bạn áp dụng authorization trước khi một function có side effect được gọi qua HTTP như thế nào?
Bạn đánh giá nguy cơ cho phép bất kỳ HTTP client nào gọi tên function tùy ý ra sao?
Bạn kiểm tra hàm web có hoạt động đúng khi reverse proxy thêm path prefix như thế nào?
Bạn xử lý request ID và trace context ở HTTP boundary rồi truyền qua Function như thế nào?
Bạn quyết định khi nào cần API gateway hoặc REST controller bao ngoài function theo yêu cầu nào?
Bạn kiểm tra pagination và streaming HTTP khi Function trả về nhiều kết quả theo phiên bản adapter như thế nào?
Bạn thiết kế giới hạn request body để một function không phải deserialize payload quá lớn như thế nào?
Bạn đánh giá tác động của blocking Function trong HTTP reactive stack lên event loop ra sao?
Bạn giới hạn concurrency hoặc timeouts khi function gọi một downstream API chậm như thế nào?
Bạn kiểm tra lỗi một bean function không nhận được payload do URL path hoặc function name sai ra sao?
Bạn xây dựng smoke test gửi HTTP tới web adapter và kiểm tra end-to-end conversion như thế nào?
Bạn phân biệt hợp đồng HTTP error response với exception nội bộ của Function trong thiết kế test ra sao?
Bạn lựa chọn cách công bố OpenAPI contract cho một hàm expose qua web adapter như thế nào?
Bạn kiểm thử cùng một logic Function qua HTTP và qua lời gọi trực tiếp để xác nhận không phụ thuộc giao thức ra sao?
Bạn giải thích vai trò của Spring Cloud Stream binder khi một function được kích hoạt qua broker như thế nào?
Bạn phân biệt Spring Cloud Function với Spring Cloud Stream về trách nhiệm đăng ký hàm và nối broker như thế nào?
Bạn sử dụng spring.cloud.function.definition để chọn hàm xử lý trong ứng dụng Spring Cloud Stream như thế nào?
Bạn mô tả cách input binding và output binding liên hệ với function definition ra sao?
Bạn thiết kế Consumer nhận sự kiện từ Kafka hoặc RabbitMQ mà vẫn giữ logic nghiệp vụ độc lập với broker như thế nào?
Bạn lựa chọn Function cho một pipeline nhận message và phát message kết quả theo hợp đồng nào?
Bạn sử dụng Supplier khi một hệ thống cần xuất dữ liệu ra message broker như thế nào?
Bạn phân biệt Supplier được kích hoạt bằng polling với Supplier reactive phát stream theo khả năng binder như thế nào?
Bạn xác định chu kỳ polling và số lần tạo message từ Supplier dựa trên nhu cầu nào?
Bạn đánh giá nguy cơ Supplier tạo sự kiện trùng khi scheduler chạy lại hoặc ứng dụng có nhiều instances ra sao?
Bạn thiết kế sự kiện có event ID và correlation ID để hỗ trợ trace và deduplication như thế nào?
Bạn phân biệt consumer group với function definition khi muốn nhiều replicas chia nhau tiêu thụ message ra sao?
Bạn lựa chọn destination, group và partition key phù hợp với thứ tự xử lý nghiệp vụ như thế nào?
Bạn kiểm tra output destination đúng khi một Function tạo message mới ra sao?
Bạn quản lý content-type và codec giữa function signature và binding adapter ra sao?
Bạn đánh giá publisher acknowledgments và consumer acknowledgments khác nhau theo broker như thế nào?
Bạn xác định khi nào consumer nên acknowledge sau khi side effect database commit thành công ra sao?
Bạn xử lý message redelivery và at-least-once delivery bằng idempotent function như thế nào?
Bạn kiểm soát retry và dead-letter routing khi lỗi xuất hiện trước khi payload vào Function ra sao?
Bạn phân biệt lỗi conversion với lỗi xử lý nghiệp vụ trong pipeline Spring Cloud Stream như thế nào?
Bạn thiết kế replay dead-letter messages để tránh ghi trùng hoặc gọi thanh toán lại ra sao?
Bạn điều chỉnh consumer concurrency để tăng throughput nhưng vẫn giữ ordering theo key như thế nào?
Bạn đánh giá tác động của backlog broker khi Function phải gọi API đồng bộ có độ trễ cao ra sao?
Bạn kiểm tra cơ chế backpressure từ function reactive tới binder và broker theo phiên bản hỗ trợ như thế nào?
Bạn xử lý trường hợp một Function trả null hoặc không phát output trong luồng messaging theo contract nào?
Bạn thiết kế consumer có khả năng xử lý song song nhưng không làm xung đột dữ liệu theo aggregate ID ra sao?
Bạn xác định cách kết hợp Function composition với bindings đầu vào/đầu ra mà không tạo destinations thừa ra sao?
Bạn lựa chọn khi nào dùng StreamBridge để gửi sự kiện ngoài luồng function declaration theo nhu cầu nào?
Bạn kiểm tra rủi ro bind quá nhiều function names vào cùng một destination trong ứng dụng như thế nào?
Bạn thiết kế tracing xuyên consumer function và producer function bằng message headers như thế nào?
Bạn phân biệt broker delivery guarantee với khả năng business process đúng một lần như thế nào?
Bạn xây dựng integration test sử dụng binder thử nghiệm để kiểm tra routing và payload mà không cần broker thực như thế nào?
Bạn dùng Testcontainers Kafka hoặc RabbitMQ để kiểm thử hành vi thực của retries, ack và DLQ theo điều kiện nào?
Bạn giải thích reactive Function<Flux<Input>, Flux<Output>> khác gì Function<Input, Output> về hợp đồng xử lý?
Bạn quyết định dùng Mono hay Flux khi một hàm trả về kết quả bất đồng bộ ra sao?
Bạn thiết kế Supplier trả về Flux dữ liệu liên tục và xác định điều kiện hoàn tất như thế nào?
Bạn quản lý resource của nguồn dữ liệu khi subscriber hủy một reactive Supplier như thế nào?
Bạn sử dụng StepVerifier để kiểm tra các tín hiệu onNext, onError và onComplete như thế nào?
Bạn phân biệt lỗi phát sinh trước khi publisher được tạo với lỗi phát sau khi subscribe ra sao?
Bạn kiểm thử reactive function có delay bằng virtual time thay vì Thread.sleep như thế nào?
Bạn xác định cách giới hạn concurrency của flatMap khi mỗi bản ghi gọi upstream HTTP như thế nào?
Bạn thiết kế thứ tự xử lý khi cần giữ order nhưng vẫn có một mức độ song song ra sao?
Bạn kiểm soát backpressure khi Supplier phát sự kiện nhanh hơn downstream tiêu thụ như thế nào?
Bạn xử lý timeout của một bước asynchronous trong composite function như thế nào?
Bạn đánh giá rủi ro dùng block() bên trong reactive function chạy trên event loop ra sao?
Bạn chuyển một API blocking sang bounded elastic scheduler theo những giới hạn nào?
Bạn giữ Reactor Context và trace information khi pipeline chuyển scheduler như thế nào?
Bạn kiểm tra sự khác nhau giữa Publisher đơn lẻ và một reactive stream có nhiều elements khi kết nối adapter ra sao?
Bạn phân biệt retry operator của Reactor với broker redelivery để tránh double retry như thế nào?
Bạn ngăn một reactive function phát lặp side effect khi operator retry resubscribe như thế nào?
Bạn kiểm soát buffering và memory use khi reactive function gom batch dữ liệu như thế nào?
Bạn xử lý partial failure khi một Flux có nhiều records và chỉ một số records lỗi ra sao?
Bạn thiết kế cancellation test để bảo đảm HTTP call hoặc database query đang chạy được dừng đúng lúc như thế nào?
Bạn đo latency và throughput của reactive function mà không tính nhầm thời gian tạo Publisher ra sao?
Bạn so sánh imperative và reactive function về testability, observability và cognitive complexity như thế nào?
Bạn giải thích cách cùng một business Function có thể được triển khai lên serverless thông qua adapter như thế nào?
Bạn phân biệt responsibility của function business code và handler adapter đặc thù nhà cung cấp cloud ra sao?
Bạn lựa chọn API function entry point khi đóng gói Spring Cloud Function cho AWS Lambda theo phiên bản nào?
Bạn thiết kế mapping từ event JSON của API Gateway sang input DTO của Function ra sao?
Bạn xác định cách biểu diễn HTTP status và headers khi Lambda được gọi qua một API gateway như thế nào?
Bạn kiểm tra một event trigger không phải HTTP cần contract đầu vào khác thế nào?
Bạn chọn packaging JAR hay container image cho một serverless function theo yêu cầu triển khai nào?
Bạn kiểm tra dependency và runtime Java phù hợp với adapter serverless và nền tảng cloud như thế nào?
Bạn đánh giá tác động của Spring application context startup lên cold start latency ra sao?
Bạn tối ưu số bean và dependency cho một function triển khai độc lập để giảm cold start như thế nào?
Bạn lựa chọn mức memory và CPU serverless theo latency, throughput và chi phí ra sao?
Bạn phân biệt cold start và warm invocation khi đo thời gian thực thi một Function như thế nào?
Bạn quản lý ConnectionPool và HTTP client tái sử dụng giữa các lượt gọi serverless như thế nào?
Bạn đánh giá rủi ro mutable static state bị chia sẻ giữa các invocations trong một execution environment ra sao?
Bạn bảo vệ secret và cloud credentials mà không đưa vào function artifact ra sao?
Bạn giới hạn quyền IAM hoặc service account của function theo các downstream thực sự cần truy cập ra sao?
Bạn đánh giá yêu cầu outbound network và VPC khi Function serverless kết nối database private như thế nào?
Bạn xử lý timeout serverless khi downstream có thể đã thực hiện side effect dù invocation thất bại ra sao?
Bạn áp dụng idempotency key cho event-driven serverless function khi nền tảng có thể gọi lại ra sao?
Bạn thiết kế dead-letter hoặc failure destination cho function được trigger bất đồng bộ theo khả năng provider như thế nào?
Bạn quản lý event batch khi chỉ một record lỗi nhưng platform có cơ chế retry cả batch ra sao?
Bạn kiểm tra giới hạn payload size và time limit của nhà cung cấp cloud trước khi chọn phương án xử lý như thế nào?
Bạn xác định cách chuyển một Spring Cloud Function từ AWS Lambda sang provider serverless khác mà vẫn giữ business core ra sao?
Bạn thiết kế một adapter Azure Functions hoặc Google Cloud Functions mà không giả định mọi provider có cùng API như thế nào?
Bạn lựa chọn môi trường local emulator hoặc integration test trước khi deploy serverless theo tiêu chí nào?
Bạn đo chi phí mỗi invocation và xác định phần chi phí do cold start, network và business execution ra sao?
Bạn thiết kế concurrency limit để serverless scaling không làm cạn database connections ra sao?
Bạn lưu correlation ID và trace context khi event đi từ cloud trigger vào function như thế nào?
Bạn xác định chiến lược canary và rollback cho một serverless Function có nhiều phiên bản ra sao?
Bạn phân biệt cấu hình function name ở deployment platform với function bean name trong Spring Cloud Function như thế nào?
Bạn kiểm tra một deployment serverless báo handler not found bằng những bước nào?
Bạn lựa chọn cách tổ chức nhiều functions trong một artifact hay tách artifact theo chức năng ra sao?
Bạn giải thích điều kiện để cùng một business function chạy ở local HTTP, qua broker và trên serverless mà không đổi logic ra sao?
Bạn thiết kế contract tests dùng cùng một bộ input/output cho ba loại adapter như thế nào?
Bạn tách thông tin xác thực giao thức khỏi input DTO nghiệp vụ để không làm coupling ra sao?
Bạn lựa chọn cách chuyển đổi HTTP error, broker nack và serverless retry từ cùng loại business failure như thế nào?
Bạn xác định các khác biệt về serialization giữa HTTP JSON, broker byte messages và cloud events ra sao?
Bạn xử lý timezone, decimal precision và unknown fields nhất quán giữa ba môi trường như thế nào?
Bạn thiết kế versioned schemas khi một function được gọi bởi nhiều clients triển khai không đồng thời như thế nào?
Bạn quản lý timeout và retry policy của từng adapter mà không nhân đôi retry ở business core ra sao?
Bạn phân biệt handling transient dependency errors với permanent validation errors qua các transport ra sao?
Bạn lựa chọn giao diện trả result object có error model thay vì throw exception trong những tình huống nào?
Bạn xây dựng strategy để cùng một Function không tự đọc HTTP headers hoặc cloud environment variables ra sao?
Bạn đánh giá trường hợp function cần context người dùng hoặc tenant mà adapter phải xác minh trước như thế nào?
Bạn kiểm soát side effects và transaction khi cùng nghiệp vụ được kích hoạt qua API và event ra sao?
Bạn xác định cách chống một event bị xử lý hai lần từ hai adapter độc lập bằng business idempotency key như thế nào?
Bạn thiết kế log và metrics có chung business operation name bất kể adapter nào kích hoạt ra sao?
Bạn triển khai parallel run của adapter mới và adapter cũ để phát hiện khác biệt output như thế nào?
Bạn kiểm tra functional equivalence trên cùng input giữa JVM local và runtime serverless như thế nào?
Bạn xác định giới hạn của việc port function sang runtime có JDK, threading hoặc library constraints khác như thế nào?
Bạn tổ chức release promotion để cùng một version function được triển khai lên nhiều target nhất quán ra sao?
Bạn thiết kế rollback khi sửa code core làm cả HTTP, event và serverless integration bị ảnh hưởng như thế nào?
Bạn xây dựng unit test cho Supplier kiểm tra dữ liệu được tạo và trạng thái dependency theo cách nào?
Bạn kiểm thử Function với input hợp lệ, thiếu field, giá trị biên và unknown enum như thế nào?
Bạn dùng Mockito hoặc fake repository để kiểm tra side effect của Consumer mà không cần broker ra sao?
Bạn sử dụng ApplicationContextRunner hoặc SpringBootTest để xác minh chức năng đăng ký FunctionCatalog như thế nào?
Bạn kiểm thử lookup theo function name và composition definition sau khi thay bean naming như thế nào?
Bạn xác nhận generic type conversion với Message<DTO> và byte[] bằng integration test ra sao?
Bạn kiểm thử content-type sai làm converter từ chối payload trước khi Function được gọi như thế nào?
Bạn tạo contract test cho headers quan trọng như correlation ID và content type như thế nào?
Bạn kiểm thử routing expression chỉ chọn được functions cho phép và từ chối route lạ ra sao?
Bạn xác minh Consumer không bị thực thi nếu bước validation hoặc authorization thất bại như thế nào?
Bạn sử dụng MockMvc hoặc WebTestClient để kiểm thử web adapter theo stack thực tế nào?
Bạn kiểm tra một function HTTP được expose đúng path và status trong bản Spring Cloud Function đang dùng ra sao?
Bạn xây dựng integration test composition khi một function giữa pipeline trả kết quả sai loại như thế nào?
Bạn kiểm thử reactive function bằng StepVerifier trên cả success, failure và cancellation ra sao?
Bạn dùng clock giả lập hoặc virtual time để kiểm thử timeout và retry mà không làm CI chậm như thế nào?
Bạn kiểm thử HTTP adapter xử lý validation errors khác gì message broker binder cùng gọi một function như thế nào?
Bạn kiểm tra Cloud Stream bindings và consumer group được cấu hình đúng bằng môi trường test như thế nào?
Bạn dùng Testcontainers để phát hiện vấn đề thực tế của broker serializer và redelivery mà test binder không bắt được ra sao?
Bạn thiết kế integration test side effects idempotent khi cùng một event được gửi trùng và song song như thế nào?
Bạn tạo fixture cho AWS Lambda hoặc cloud event mà không gắn cố định secret hoặc resource id production ra sao?
Bạn kiểm thử packaging serverless bảo đảm handler adapter tải được function bean trong artifact như thế nào?
Bạn đánh giá chiến lược chạy thử trên môi trường cloud sandbox khi local emulator không mô phỏng đủ behavior ra sao?
Bạn tổ chức CI chạy unit tests nhanh và chọn integration tests theo rủi ro trước khi xuất bản như thế nào?
Bạn kiểm thử backward compatibility của function DTO trong giai đoạn nhiều adapter versions cùng hoạt động như thế nào?
Bạn xác định tiêu chí pass/fail về latency, memory, lỗi và conversion khi nâng cấp Spring Cloud Function như thế nào?
Bạn quản lý credentials cho web adapter, broker và serverless deployment theo các phương án nào?
Bạn xác định điểm thực hiện authentication và authorization trước khi Function nghiệp vụ được gọi ra sao?
Bạn đánh giá rủi ro dynamic routing cho phép gọi bean nội bộ không có kiểm soát như thế nào?
Bạn giới hạn dữ liệu nhạy cảm xuất hiện trong payload, headers, logs và traces như thế nào?
Bạn thiết kế message validation để chống payload quá lớn hoặc cấu trúc JSON quá sâu ra sao?
Bạn áp dụng least privilege cho Function gọi database, object storage hoặc external API như thế nào?
Bạn kiểm tra tenant ID do adapter xác minh không bị payload giả mạo ghi đè như thế nào?
Bạn thiết kế audit trail cho side effect của Consumer theo business key và invocation id ra sao?
Bạn bảo vệ serverless deployment khỏi cấu hình environment variables chứa secret bị lộ như thế nào?
Bạn xác định trường hợp nào cần TLS hoặc mTLS khi function gọi downstream qua mạng ra sao?
Bạn xây dựng metrics cho invocation count, failure rate và latency của từng function name như thế nào?
Bạn giới hạn cardinality metrics khi một header chứa user ID hoặc request ID ra sao?
Bạn phân biệt latency conversion, routing và business execution khi chẩn đoán một request chậm như thế nào?
Bạn sử dụng Micrometer Observation hoặc tracing để nối HTTP request với function execution ra sao?
Bạn theo dõi event được nhận nhưng không phát output do Consumer hoặc filtering theo cách nào?
Bạn đặt cảnh báo cho conversion errors và unknown function routing để phát hiện schema drift ra sao?
Bạn kiểm soát throughput và memory khi Supplier reactive phát stream kéo dài như thế nào?
Bạn xây dựng dashboard đối chiếu số event nhận, xử lý thành công và gửi ra broker như thế nào?
Bạn phát hiện connection pool hoặc serverless concurrency saturation gây tăng p99 latency bằng dấu hiệu nào?
Bạn thiết kế runbook khi FunctionCatalog không đăng ký một bean sau khi triển khai phiên bản mới như thế nào?
Bạn phân biệt lỗi startup do function signature với lỗi runtime do adapter conversion như thế nào?
Bạn xác định cách phát hiện một composite function bị lỗi ở bước nào khi chỉ có trace cuối ra sao?
Bạn giám sát hiệu quả retry để tránh một upstream lỗi gây retry storm từ HTTP và broker cùng lúc như thế nào?
Bạn đặt chính sách rate limiting cho web-exposed function và concurrency cho message consumer ra sao?
Bạn kiểm soát version labels và provenance cho một business Function đóng gói ở nhiều loại artifact như thế nào?
Bạn kiểm tra build reproducibility và dependency vulnerabilities trước khi triển khai function serverless ra sao?
Bạn đo cold-start và warm-invocation latency trong những điều kiện test nào để kết quả có ý nghĩa?
Bạn quyết định tách Function có side effect nặng thành workflow bất đồng bộ dựa trên những dấu hiệu vận hành nào?
Nếu FunctionCatalog.lookup trả null cho bean mới, bạn sẽ kiểm tra tên, registration và cấu hình Spring context ra sao?
Nếu composition chạy sai thứ tự và kết quả nghiệp vụ bị đổi, bạn sẽ kiểm tra function definition và kiểu dữ liệu như thế nào?
Nếu payload JSON được convert thành Map thay vì DTO, bạn sẽ phân tích generic type metadata như thế nào?
Nếu một route từ message header gọi nhầm Consumer quản trị, bạn sẽ thiết kế authorization và allowlist lại ra sao?
Nếu một Function hoạt động khi gọi trực tiếp nhưng HTTP endpoint báo 404, bạn sẽ kiểm tra web adapter và exposure như thế nào?
Nếu một Consumer qua HTTP trả phản hồi không như client mong đợi, bạn sẽ đối chiếu contract và adapter behavior ra sao?
Nếu Cloud Stream consumer nhận message nhưng không ghi dữ liệu, bạn sẽ kiểm tra binding, conversion và side effects như thế nào?
Nếu broker giao cùng message hai lần làm tăng số đơn hàng, bạn sẽ bổ sung business idempotency ở đâu?
Nếu một Supplier phát sự kiện lặp sau khi pod restart, bạn sẽ kiểm tra state, scheduling và checkpoint ra sao?
Nếu reactive Function bị nghẽn khi downstream chậm, bạn sẽ đo backpressure, buffering và concurrency như thế nào?
Nếu một reactive pipeline retry làm gọi thanh toán nhiều lần, bạn sẽ điều chỉnh side effects và retry boundary ra sao?
Nếu serverless function xuất hiện cold start tăng mạnh sau khi thêm dependency, bạn sẽ phân tích build size và context startup ra sao?
Nếu Lambda xử lý event thành công nhưng caller nhận timeout và gửi lại, bạn sẽ thiết kế deduplication như thế nào?
Nếu cùng Function có output khác nhau giữa HTTP và cloud event trigger, bạn sẽ so sánh conversion và contract như thế nào?
Nếu routing thay đổi sau deploy khiến messages vào wrong destination, bạn sẽ truy nguyên definition và bindings ra sao?
Nếu một function được đổi tên làm tất cả HTTP và broker adapters cùng lỗi, bạn sẽ triển khai compatibility alias như thế nào?
Nếu messages mang nội dung nhạy cảm bị in ra log khi conversion lỗi, bạn sẽ tổ chức xử lý sự cố và giảm rủi ro ra sao?
Nếu nhiều serverless invocations cùng tạo database connections khiến pool cạn, bạn sẽ giới hạn scale và tái sử dụng kết nối ra sao?
Nếu một function chỉ lỗi trên cloud provider mới, bạn sẽ kiểm tra runtime, handler adapter và event format theo thứ tự nào?
Nếu một Consumer thành công rồi publisher output thất bại ở bước tiếp theo, bạn sẽ kiểm soát transaction và replay như thế nào?
Nếu test binder chạy xanh nhưng message thực vẫn bị DLQ, bạn sẽ thiết kế integration test broker thực để tìm lỗi ra sao?
Nếu tracing HTTP có trace ID nhưng broker consumer không nối được trace, bạn sẽ kiểm tra propagation headers như thế nào?
Nếu một composite function vượt timeout tổng thể dù từng hàm nhanh, bạn sẽ phân tích waiting, conversion và backpressure ra sao?
Nếu service cần chuyển từ gọi HTTP trực tiếp sang event-driven mà giữ logic chính, bạn sẽ thiết kế adapters và contracts ra sao?
Bạn xây dựng runbook khôi phục khi function routing, broker binder và serverless adapter cùng gặp lỗi trong đợt phát hành như thế nào?

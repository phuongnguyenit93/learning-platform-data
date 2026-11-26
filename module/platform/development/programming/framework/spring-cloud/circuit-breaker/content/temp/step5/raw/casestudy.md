Một dịch vụ đặt hàng gọi hệ thống thanh toán đang mất kết nối, khiến các request HTTP giữ thread chờ đến timeout và cuối cùng cả API đặt hàng không còn khả năng phục vụ.
Một nền tảng bán vé có service kiểm tra tồn kho phản hồi thất thường, nhưng mọi request vẫn tiếp tục gọi dependency lỗi và làm connection pool của service chính cạn kiệt.
Một ứng dụng Spring Cloud có ba dịch vụ phụ thuộc nối tiếp, nhưng khi dịch vụ cuối chậm thì các request đầu chuỗi tích tụ và độ trễ lan sang những API không liên quan.
Một hệ thống tra cứu vận đơn muốn dùng circuit breaker quanh HTTP client, nhưng đội phát triển đặt cơ chế bảo vệ ở một tầng không bao phủ các lời gọi đi từ job nền.
Một service tổng hợp giá gọi nhiều nhà cung cấp cùng lúc, nhưng chỉ một nhà cung cấp mất kết nối đã khiến toàn bộ câu trả lời phải đợi đến hạn chờ lớn nhất.
Một ngân hàng áp dụng circuit breaker cho tất cả thao tác tới core banking, nhưng một lỗi tạm ở API tra cứu lại làm cả đường chuyển tiền bị từ chối dù hai endpoint độc lập.
Một hệ thống đặt lịch có nhiều instance cùng gọi một đối tác lỗi, nhưng cơ chế bảo vệ chỉ giảm lưu lượng trong từng instance và đối tác vẫn nhận đột biến request khi mở rộng cụm.
Một API tiếp nhận dữ liệu phụ thuộc vào dịch vụ phân tích không bắt buộc, nhưng khi dịch vụ phân tích chậm thì giao dịch chính vẫn bị treo thay vì hoàn thành trong thời gian cam kết.
Một dịch vụ gửi email dùng circuit breaker cho kết nối SMTP, nhưng khi kênh gửi hỏng ứng dụng vẫn báo thành công vì trạng thái gửi thực tế chưa được xác minh.
Một nhóm triển khai cơ chế ngắt mạch cho lời gọi tới database, nhưng lỗi lấy kết nối từ pool nội bộ và lỗi truy vấn nghiệp vụ đều bị tính chung như sự cố database bên ngoài.
Một ứng dụng theo dõi trạng thái giao hàng thấy nhiều HTTP 404 hợp lệ từ đối tác, nhưng cấu hình breaker lại coi chúng là lỗi hệ thống và ngắt cả những request hợp lệ.
Một hệ thống phân tán ghi lại trạng thái circuit breaker ở gateway, nhưng service nội bộ khác vẫn gọi thẳng dependency đang lỗi nên tổng tải lên đối tác không giảm.
Một dịch vụ đăng nhập gọi hệ thống xác minh OTP với hạn mức thấp, nhưng circuit breaker không phân biệt từ chối do rate limit với sự cố mất kết nối nên bảo vệ hoạt động khác dự kiến.
Một ứng dụng báo cáo dùng circuit breaker cho API chậm nhưng không có mục tiêu độ trễ rõ ràng, khiến đội vận hành không biết ở mức nào hành vi ngắt mạch là phù hợp.
Một nhóm tích hợp Resilience4j qua Spring Cloud CircuitBreaker nhưng vẫn để thư viện HTTP client tự retry quá lâu, khiến request tiếp tục chiếm tài nguyên trước khi breaker ghi nhận kết quả.
Một service quản lý hội viên luôn ở trạng thái CLOSED dù backend trả nhiều lỗi lặp lại, khiến đội phát triển nghi ngờ các lời gọi chưa đi qua đúng breaker instance.
Một hệ thống thương mại điện tử thấy breaker chuyển từ CLOSED sang OPEN sau đợt lỗi lớn, nhưng dashboard vẫn hiển thị phần lớn HTTP 200 vì các request bị trả fallback.
Một ứng dụng kế toán bị ngắt mạch trong trạng thái OPEN, khiến người dùng nhận phản hồi rất nhanh nhưng nhóm trực lại đánh giá nhầm sự cải thiện latency là backend đã phục hồi.
Một dịch vụ kiểm tra tín dụng giữ breaker OPEN quá lâu sau khi đối tác hoạt động lại, khiến các khoản vay mới tiếp tục bị từ chối do không có cơ hội thử kết nối.
Một hệ thống dùng cấu hình chuyển trạng thái tự động sang HALF_OPEN, nhưng khi lưu lượng giảm gần bằng không nhóm vận hành không nhìn thấy lần thử nào để đánh giá backend.
Một ứng dụng không bật tự động chuyển khỏi OPEN, nhưng đội trực kỳ vọng breaker sẽ tự khôi phục dù chưa có request mới nào tới endpoint để kích hoạt đánh giá.
Một nền tảng mua sắm cấu hình chỉ một lời gọi thử trong HALF_OPEN, nhưng request đó đến vùng mạng bất ổn khiến breaker quay lại OPEN dù đa số node đối tác đã khỏe.
Một dịch vụ đặt phòng cho phép quá nhiều request đồng thời ở HALF_OPEN, khiến backend vừa hồi phục nhận tải đột ngột và lại mất khả năng phục vụ.
Một hệ thống có hai breaker với cùng cấu hình nhưng khác mức traffic, khiến breaker của service ít yêu cầu ở CLOSED lâu hơn dù nhiều lời gọi gần nhất đều thất bại.
Một ứng dụng có breaker HALF_OPEN khi node đối tác phục hồi, nhưng một lời gọi test bị timeout sau tác vụ nặng làm toàn bộ giai đoạn kiểm tra thành công thất bại.
Một dịch vụ đặt vé dùng cùng breaker cho hai endpoint của một provider, khiến lỗi ở endpoint tìm kiếm làm các lần xác nhận đặt vé cũng bị từ chối ngay.
Một hệ thống cân bằng tải gọi hai vùng của đối tác qua cùng tên breaker, khiến lỗi ở một vùng làm mất cả khả năng sử dụng vùng còn hoạt động.
Một ứng dụng nhận lỗi CallNotPermittedException khi breaker đang OPEN, nhưng exception được log như lỗi kết nối mới và đội trực khó phân biệt từ chối chủ động với lỗi upstream.
Một nhóm kỳ vọng mọi breaker OPEN phải trở về CLOSED sau khoảng chờ, nhưng trên production các lời gọi trong HALF_OPEN liên tục thất bại và trạng thái lại chuyển sang OPEN.
Một hệ thống dùng trạng thái METRICS_ONLY trong một môi trường thử nghiệm, khiến số liệu lỗi tăng nhưng các lời gọi vẫn được phép đi tới backend dù nhóm nghĩ đang được bảo vệ.
Một dịch vụ chuyển breaker sang DISABLED để điều tra latency, nhưng dashboard tiếp tục hiển thị lỗi backend khiến đội vận hành tưởng ngắt mạch vẫn đang chặn request.
Một ứng dụng có breaker được chuyển sang FORCED_OPEN trong lúc bảo trì, nhưng đội hỗ trợ hiểu nhầm mọi lời gọi bị từ chối là dấu hiệu backend đang tiếp tục lỗi.
Một nền tảng ghi nhận cả trạng thái circuit breaker lẫn trạng thái deployment, nhưng khi deploy phiên bản mới breaker trên instance mới bắt đầu CLOSED và gây lưu lượng lại tới backend đang lỗi.
Một dịch vụ có nhiều replica và mỗi replica giữ trạng thái breaker riêng, khiến request của cùng khách lúc nhận fallback lúc lại được gửi tới đối tác tùy node được chọn.
Một hệ thống khởi động lại service giữa sự cố mạng, khiến lịch sử thống kê trong bộ nhớ của breaker bị mất và nhiều request mới vẫn được thử tới đối tác.
Một ứng dụng kiểm tra giá dùng count-based sliding window rất nhỏ, khiến hai lỗi ngẫu nhiên ở giờ ít traffic đã đủ làm trạng thái thay đổi liên tục.
Một dịch vụ được cấu hình count-based sliding window lớn, nhưng lượng traffic ban đêm ít nên các lỗi mới chưa đủ số mẫu để breaker quyết định ngắt mạch.
Một hệ thống đặt sliding window theo thời gian, nhưng đội phát triển so sánh số request tổng trong nhiều giờ và không hiểu vì sao lỗi cũ không còn ảnh hưởng đến tỷ lệ hiện tại.
Một ứng dụng dùng time-based sliding window nhưng traffic tăng mạnh theo chiến dịch, khiến số lời gọi trong mỗi cửa sổ thay đổi rất lớn dù khoảng thời gian đo cố định.
Một service dùng time-based sliding window với minimumNumberOfCalls cao hơn lượng request trong mỗi cửa sổ, khiến breaker của endpoint ít traffic không đánh giá ngưỡng failure rate.
Một hệ thống có failureRateThreshold thấp hơn tỷ lệ lỗi bình thường của API đối tác, khiến breaker thường xuyên OPEN vào giờ cao điểm dù đối tác đang đáp ứng hợp đồng.
Một ứng dụng ghi nhận một số lỗi độc lập trong cửa sổ nhỏ rồi ngắt mạch, khiến nhiều khách được trả fallback dù những lời gọi sau đó tới đối tác có thể đã thành công.
Một nhóm xem tổng số lỗi tích lũy trên dashboard thay vì số liệu trong sliding window của breaker, khiến họ dự đoán sai thời điểm ngắt mạch sau một đợt lỗi.
Một service phân tích đơn hàng cấu hình slidingWindowSize nhưng không phân biệt đơn vị request với đơn vị thời gian, khiến các môi trường đánh giá cùng traffic theo những cửa sổ khác nhau.
Một hệ thống có nhiều lời gọi nhanh thành công và ít lời gọi cực chậm, khiến failure rate vẫn thấp trong khi trải nghiệm người dùng thường xuyên vượt SLA.
Một ứng dụng bật slow-call detection nhưng ngưỡng slowCallDurationThreshold dài hơn timeout HTTP client, khiến lời gọi thường kết thúc lỗi trước khi được phân loại là chậm.
Một dịch vụ có slowCallRateThreshold rất thấp và traffic dao động, khiến breaker mở khi một số request hợp lệ tăng latency do batch định kỳ.
Một ứng dụng đánh giá slow-call rate cho cùng endpoint qua nhiều khu vực địa lý, nhưng độ trễ mạng nền khác nhau khiến vùng xa thường bị ngắt mạch không tương xứng.
Một hệ thống đo số request thành công qua breaker nhưng một middleware chuyển lỗi thành giá trị mặc định trước đó, khiến thống kê failure rate không phản ánh sự cố ban đầu.
Một service coi mọi HTTP 409 là lỗi cần ghi nhận vào breaker, khiến các xung đột cập nhật dữ liệu hợp lệ bị trộn với lỗi hệ thống đối tác.
Một ứng dụng cần nhận biết phản hồi JSON báo lỗi dù HTTP 200, nhưng breaker chỉ ghi nhận thành công vì kết quả được trả về như đối tượng bình thường.
Một hệ thống xem lỗi timeout và lỗi từ chối quyền đều có tác động tương đương, khiến breaker OPEN do token hết hạn thay vì lưu lượng quá tải hoặc mất kết nối.
Một dịch vụ dùng ignoreExceptions cho một loại lỗi nghiệp vụ, nhưng một subclass của lỗi đó cũng bị bỏ qua khiến những lỗi kỹ thuật mới không được tính như dự kiến.
Một nhóm cấu hình recordExceptions cho lỗi giao tiếp mạng nhưng ứng dụng bọc lỗi bằng một exception khác trước breaker, khiến thống kê không tăng khi đối tác mất kết nối.
Một hệ thống bật predicate dựa trên kết quả trả về để phân loại lỗi, nhưng giá trị đánh dấu lỗi nghiệp vụ khác nhau giữa hai phiên bản API làm tỷ lệ thất bại thay đổi sau nâng cấp.
Một ứng dụng có circuit breaker được cấu hình theo properties, nhưng một endpoint dùng tên instance khác tên trong file khiến cấu hình mặc định áp dụng ngoài ý muốn.
Một nhóm muốn tạo hai breaker riêng cho hai nhà cung cấp vận chuyển, nhưng gọi CircuitBreakerFactory với cùng ID và vô tình chia sẻ trạng thái ngắt mạch.
Một ứng dụng dùng Resilience4j trực tiếp ở một service và Spring Cloud CircuitBreaker ở service khác, khiến cách đặt tên instance, fallback và thống kê không nhất quán.
Một hệ thống thay đổi cấu hình threshold trên file runtime mà không khởi động lại thành phần, khiến đội vận hành kỳ vọng các breaker đã tạo trước đó tự cập nhật giá trị mới.
Một dịch vụ nâng cấp starter Resilience4j nhưng dependency mới không khớp phiên bản Spring Cloud hiện tại, khiến bean CircuitBreakerFactory không có mặt khi khởi động.
Một ứng dụng có circuit breaker cấu hình trong môi trường local nhưng production thiếu phần cấu hình provider, khiến lời gọi đi qua factory mà không có chính sách ngắt mạch mong đợi.
Một nhóm tạo breaker bằng ID động chứa mã khách hàng, khiến số instance trong registry tăng theo từng request và các cửa sổ thống kê không đủ mẫu.
Một hệ thống tạo breaker riêng cho từng URL có query parameter, khiến cùng API được chia thành nhiều instance và không tích lũy đủ dữ liệu nhận biết sự cố.
Một ứng dụng đăng ký customizer cho Resilience4j nhưng chỉ một tập breaker được tạo trước lúc cấu hình chạy, khiến các instance hoạt động với tham số khác nhau.
Một nhóm bật metrics cho circuit breaker ở môi trường test nhưng production thiếu dependency Actuator hoặc binder tương ứng, khiến dashboard trạng thái breaker trống dù fallback vẫn chạy.
Một service dùng Resilience4j CircuitBreaker và TimeLimiter theo hai bộ cấu hình có cùng tên, nhưng đội phát triển tưởng thay đổi timeout cũng đồng thời đổi failureRateThreshold.
Một ứng dụng tạo circuit breaker trong mỗi lần xử lý request thay vì tái sử dụng instance, khiến lịch sử lỗi không được tích lũy và trạng thái hiếm khi chuyển OPEN.
Một hệ thống định nghĩa fallback khi API xếp hạng sản phẩm lỗi, nhưng giá trị mặc định được xem như điểm thật và làm thay đổi thứ tự hiển thị trên website.
Một dịch vụ trả fallback từ cache cho dữ liệu giá, nhưng cache đã cũ nhiều giờ khiến khách thấy giá không còn hiệu lực khi phía đối tác mất kết nối.
Một ứng dụng đặt phòng dùng fallback trả phòng trống khi hệ thống tồn kho lỗi, khiến người dùng hiểu nhầm khách sạn đã hết phòng trong mùa cao điểm.
Một dịch vụ thanh toán dùng fallback báo thành công khi provider lỗi, khiến đơn hàng được xác nhận dù không có bằng chứng giao dịch đã được thực hiện.
Một hệ thống báo cáo có fallback sang dữ liệu hôm qua, nhưng câu trả lời không ghi thời điểm dữ liệu khiến bộ phận kế toán sử dụng số liệu cũ như bản đối soát mới.
Một ứng dụng thử fallback khi CallNotPermittedException được ném lúc OPEN, nhưng nhánh xử lý chỉ nhận một loại exception mạng nên client vẫn trả lỗi kỹ thuật.
Một nhóm cấu hình fallback áp dụng cho toàn bộ ngoại lệ, khiến lỗi validation của request nội bộ bị che giấu và các báo cáo chất lượng dữ liệu không còn chính xác.
Một dịch vụ tra cứu trạng thái thanh toán chuyển sang provider dự phòng khi lỗi, nhưng hai provider không chia sẻ định danh giao dịch nên phản hồi dự phòng mâu thuẫn với dữ liệu gốc.
Một nền tảng bán hàng dùng cache fallback cho profile khách hàng, nhưng khóa cache không có tenant ID khiến khi đối tác lỗi dữ liệu của khách hàng khác có thể xuất hiện.
Một hệ thống chuyển sang fallback tĩnh sau khi breaker OPEN, nhưng người dùng vẫn tiếp tục cập nhật dữ liệu cũ như thể nó được lấy từ hệ thống chính.
Một ứng dụng trả fallback ngay khi dịch vụ ngoài lỗi, nhưng đội trực không ghi dấu hiệu fallback trong metric nên latency tốt lên che giấu tỷ lệ lỗi thực tế.
Một dịch vụ gắn fallback ở controller thay vì tầng client, khiến các job nền gọi cùng đối tác không được bảo vệ bằng cách xử lý lỗi tương tự.
Một hệ thống chuyển sang dữ liệu mô phỏng cho chức năng không quan trọng, nhưng cấu hình profile sai khiến dữ liệu giả được trả trong môi trường production.
Một ứng dụng phản hồi fallback là danh sách trống cho kết quả tìm kiếm, khiến đội kinh doanh hiểu sự cố đối tác là nhu cầu thị trường giảm về không.
Một dịch vụ đăng nhập muốn fallback sang phương thức xác thực khác, nhưng phương thức dự phòng có chính sách an toàn yếu hơn và có thể phá vỡ yêu cầu bảo mật.
Một hệ thống gọi fallback từ một service khác cũng đang quá tải, khiến khi đường chính mất kết nối đường phụ đồng thời nhận nhiều request và tiếp tục lỗi.
Một ứng dụng ghép kết quả từ nhiều dependency, nhưng fallback của một dependency tạo đối tượng không tương thích với bước tổng hợp khiến lỗi lan sang những lời gọi đã thành công.
Một nhóm dùng fallback trả lỗi có chủ đích để giữ nguyên hợp đồng API, nhưng bộ giám sát đếm mọi phản hồi do fallback sinh là lỗi backend ban đầu.
Một nền tảng quản lý đơn trả fallback chứa trạng thái chưa xác minh, nhưng client di động không phân biệt với trạng thái giao hàng thật và cho phép khách hủy đơn sai thời điểm.
Một dịch vụ có fallback vừa log lỗi vừa ghi một sự kiện bù trừ, nhưng cùng request bị gọi lại sau timeout khiến sự kiện bù trừ được tạo nhiều lần.
Một ứng dụng dùng Spring Cloud CircuitBreaker bảo vệ lời gọi HTTP, nhưng thời gian chờ kết nối và thời gian đọc response lớn hơn SLA nên breaker chỉ thấy lỗi sau khi request đã chờ quá lâu.
Một nhóm thêm TimeLimiter cho lời gọi bất đồng bộ nhưng tác vụ thực thi ở đối tác vẫn chạy sau khi client nhận timeout, khiến kết quả ghi dữ liệu có thể xuất hiện muộn.
Một dịch vụ tạo phiếu giao hàng đặt timeout rất ngắn so với thời gian tạo vận đơn thực tế, khiến nhiều yêu cầu bị xem là lỗi dù đối tác đã tạo thành công.
Một ứng dụng có timeout ở HTTP client dài hơn timeout của TimeLimiter, khiến lời gọi bị cắt ở tầng bao ngoài nhưng kết nối phía dưới còn giữ tài nguyên một thời gian.
Một hệ thống đặt timeout ở gateway, Spring Cloud CircuitBreaker và HTTP client với các giá trị không thống nhất, khiến đội trực khó xác định tầng nào kết thúc request đầu tiên.
Một dịch vụ dùng TimeLimiter cho tác vụ blocking trên executor, nhưng khi tương lai được hủy thư viện bên dưới không hỗ trợ ngắt nên thread vẫn chờ I/O.
Một ứng dụng gửi batch request tới hệ thống kế toán và áp timeout chung cho cả batch, khiến vài bản ghi chậm làm tất cả kết quả bị coi là thất bại.
Một nhóm đánh giá timeout bằng thời gian HTTP response đơn lẻ, nhưng thời gian chờ trong bulkhead queue không được tính cùng cách nên request tổng vẫn vượt SLA.
Một ứng dụng bật slow-call threshold theo độ trễ đối tác, nhưng retry làm tổng thời gian request tăng gấp nhiều lần mà mỗi lần gọi riêng vẫn nằm dưới ngưỡng chậm.
Một hệ thống dùng timeout để kích hoạt fallback nhưng thiếu thông tin xác định tác vụ từ xa đã hoàn thành hay chưa, khiến lần gửi lại có thể gây tác dụng phụ lặp.
Một dịch vụ gọi API tìm kiếm sử dụng Future được hoàn thành bởi nhiều callback, nhưng một callback lỗi xảy ra sau timeout và được log như một sự cố mới không liên quan.
Một ứng dụng có TimeLimiter cho lời gọi reactive dài nhưng màn hình người dùng đã đóng kết nối, khiến nguồn tiếp tục làm việc nếu cancellation không được truyền xuống đúng điểm.
Một hệ thống tăng thời gian timeout để giảm tỷ lệ lỗi, nhưng nhiều request bắt đầu chiếm connection pool lâu hơn và làm backend tổng thể kém sẵn sàng.
Một nhóm dùng deadline của request gốc từ gateway nhưng không truyền giới hạn còn lại tới lời gọi dịch vụ con, khiến dịch vụ con tiếp tục thực hiện sau khi phía trên đã trả timeout.
Một dịch vụ đặt một timeout chung cho cả giai đoạn HALF_OPEN, nhưng những lời gọi thăm dò có đặc tính chậm khác nhau làm việc đánh giá phục hồi không công bằng.
Một nền tảng streaming giữ kết nối dài theo thiết kế, nhưng timeout dành cho unary call được áp vào stream khiến luồng dữ liệu hợp lệ bị hủy định kỳ.
Một API có nhiều request gọi sang provider lỗi cùng lúc, nhưng circuit breaker chỉ xét tỷ lệ lỗi và không giới hạn số lời gọi đang bay nên thread pool vẫn bị cạn trước khi OPEN.
Một dịch vụ gọi partner API được bảo vệ bằng semaphore bulkhead có rất ít permit, khiến giờ cao điểm nhiều request khỏe bị từ chối dù backend vẫn còn năng lực xử lý.
Một nhóm dùng thread-pool bulkhead cho thao tác đồng bộ chậm nhưng queue chờ quá lớn, khiến các request bị giữ lâu và độ trễ đầu cuối tăng dù không vượt số thread hoạt động.
Một ứng dụng chuyển sang thread-pool bulkhead để tách dependency lỗi, nhưng thao tác kiểm toán phụ thuộc ThreadLocal mất dữ liệu khi chạy trên executor khác.
Một service dùng cùng bulkhead instance cho hai nhà cung cấp có độ trễ khác nhau, khiến nhà cung cấp chậm chiếm hết permit và chặn cả lời gọi tới đối tác khỏe.
Một hệ thống tăng số permit của bulkhead để giảm số request bị từ chối, nhưng database phía sau có connection pool nhỏ hơn nên thời gian chờ kết nối tăng đáng kể.
Một ứng dụng triển khai circuit breaker và bulkhead quanh cùng lời gọi, nhưng đội trực chỉ đếm CallNotPermittedException và bỏ qua số request bị bulkhead từ chối vì hết chỗ.
Một service gọi database qua bulkhead dạng semaphore, nhưng code giữ permit trong một tác vụ bất đồng bộ không chờ đúng vòng đời nên số lượng xử lý song song vượt mức dự kiến.
Một nhóm bảo vệ API dự báo bằng bulkhead nhưng không phân biệt batch job và request tương tác, khiến tác vụ batch dài chiếm hầu hết tài nguyên trong khung giờ đông khách.
Một ứng dụng có worker pool chung cho nhiều bulkhead, nhưng công việc tải file kích thước lớn gây nghẽn và làm chậm cả các request có circuit breaker riêng.
Một hệ thống coi lỗi BulkheadFullException là lỗi backend trong thống kê breaker, khiến trạng thái OPEN xuất hiện dù đối tác không hề gặp sự cố thực tế.
Một dịch vụ phục vụ nhiều tenant sử dụng một bulkhead chung, khiến một tenant tạo tải cao có thể làm các tenant khác nhận fallback dù họ chỉ gửi vài request.
Một ứng dụng đặt queue capacity của thread-pool bulkhead theo lưu lượng trung bình, nhưng flash sale tạo hàng chờ quá lớn khiến request hết hạn ngay trong queue.
Một nhóm dùng bulkhead cho tác vụ đọc dữ liệu nhưng callback giải phóng permit chỉ thực thi khi thành công, khiến sau một đợt lỗi mọi request tiếp theo đều bị từ chối.
Một dịch vụ tăng số instance ứng dụng nhưng mỗi instance có bulkhead permit riêng, khiến tổng concurrency vào provider vượt hạn mức toàn cục mà đối tác cho phép.
Một ứng dụng dùng circuit breaker để giảm lỗi dây chuyền nhưng không có bulkhead, khiến trước khi đủ mẫu để OPEN hàng nghìn request vẫn chiếm executor và áp lực bộ nhớ.
Một hệ thống triển khai thread-pool bulkhead cho các thao tác cần giữ thứ tự, nhưng thứ tự hoàn tất thay đổi khiến các bước cập nhật cùng tài khoản bị ghi đè.
Một dịch vụ bán lẻ dùng retry để vượt qua lỗi mạng tạm thời nhưng mỗi request được thử lại ba lần, khiến backend đang quá tải nhận thêm lưu lượng đúng lúc khó phục hồi.
Một nhóm đặt retry ở ngoài circuit breaker, khiến số request nghiệp vụ và số lời gọi đi qua breaker khác nhau và tỷ lệ lỗi được tính theo từng attempt.
Một ứng dụng đặt circuit breaker ở ngoài retry, khiến breaker chỉ nhìn kết quả cuối sau nhiều attempt và ghi nhận ít lỗi hơn số lỗi mà hệ thống ngoài thực sự trả.
Một service trả fallback ngay khi circuit breaker OPEN nhưng tầng retry tiếp tục gọi lại lời gọi bị từ chối, khiến nhiều lần CallNotPermittedException xuất hiện cho cùng một request.
Một hệ thống retry khi HTTP 429 mà không xét thời gian nhà cung cấp yêu cầu đợi, khiến cả cụm đồng loạt thử lại và tiếp tục bị giới hạn tốc độ.
Một ứng dụng dùng exponential backoff giống nhau trên mọi instance, khiến sau sự cố nhiều request cùng dồn trở lại backend theo những nhịp trùng nhau.
Một nhóm dùng retry cho API tạo thanh toán không có khóa chống trùng, khiến một timeout phản hồi có thể tạo hai giao dịch trong lúc breaker vẫn chưa OPEN.
Một dịch vụ dự phòng gọi endpoint thứ hai khi breaker của endpoint đầu OPEN, nhưng cả hai endpoint trỏ về cùng cơ sở dữ liệu đang quá tải nên fallback không giảm áp lực.
Một ứng dụng tích hợp cache fallback bên ngoài retry, khiến request đầu tiên trả dữ liệu cũ trong khi những lần thử lại tiếp tục chạy sau đó và thay đổi dữ liệu.
Một nhóm tăng số lần retry để giảm lỗi ngẫu nhiên, nhưng độ trễ p99 vượt SLA và số connection đang dùng tăng nhanh khi đối tác chỉ chậm nhẹ.
Một hệ thống có retry ở service và retry khác trong SDK nhà cung cấp, khiến số attempt thực tế cao hơn nhiều so với cấu hình Spring Cloud mà đội trực đang kiểm tra.
Một ứng dụng triển khai retry trong job nền và breaker cho client, nhưng khi breaker HALF_OPEN các lượt thử lại chiếm gần hết số cuộc gọi thăm dò được phép.
Một dịch vụ dùng retry để xử lý lỗi nghiệp vụ không thể phục hồi, khiến cùng request sai được gửi lặp lại và làm nhiễu failure-rate sliding window.
Một nhóm thay đổi thứ tự áp dụng TimeLimiter, Retry và CircuitBreaker sau bản phát hành, khiến số lần lỗi được tính và thời điểm fallback xuất hiện khác rõ so với trước.
Một ứng dụng dùng retry trong một chuỗi giao dịch nhiều bước, nhưng khi một bước đã ghi thành công thì lỗi ở bước sau khiến cả workflow thử lại và tạo dữ liệu trùng.
Một dịch vụ nhận dữ liệu từ nhà cung cấp có giới hạn request theo phút, nhưng retry từ nhiều replica không được tính vào hạn mức vận hành nên tài khoản bị khóa tạm thời.
Một API xây trên WebFlux áp dụng circuit breaker cho Mono gọi đối tác, nhưng pipeline trả về Mono mà không ai subscribe nên lời gọi và việc ghi nhận breaker đều không diễn ra.
Một ứng dụng reactive tạo cùng một Mono nguồn lạnh rồi subscribe hai lần cho log và response, khiến API đối tác được gọi lặp lại và thống kê breaker tăng ngoài mong đợi.
Một nhóm wrap Mono bằng circuit breaker nhưng xử lý onErrorResume trước lớp bảo vệ, khiến lỗi dependency bị chuyển thành giá trị bình thường và breaker không tính thất bại.
Một service dùng Flux để stream dữ liệu liên tục, nhưng breaker chỉ nhìn tín hiệu terminal và nguồn không bao giờ hoàn tất nên metric thành công chưa được ghi như kỳ vọng.
Một ứng dụng phát nhiều giá trị từ Flux rồi bị lỗi cuối luồng, khiến người dùng đã nhận dữ liệu một phần trong khi circuit breaker ghi nhận toàn bộ lần subscribe thất bại.
Một hệ thống dùng fallback Flux sau khi nguồn lỗi, nhưng phần tử từ nguồn chính đã được gửi trước đó và dữ liệu fallback tạo thêm bản ghi trùng trên màn hình.
Một ứng dụng dùng subscribe thủ công bên trong controller WebFlux để gọi downstream, khiến circuit breaker xử lý lỗi ngoài chuỗi response và client vẫn nhận HTTP 200 quá sớm.
Một dịch vụ dùng ReactorResilience4JCircuitBreakerFactory cho lời gọi reactive, nhưng lại sử dụng factory kiểu đồng bộ ở nhánh khác và có hai bộ metric khó đối chiếu.
Một nhóm dùng publishOn chuyển scheduler sau khi tạo Observation và circuit breaker, nhưng log trong fallback không có trace ID do context chưa được truyền đúng cách.
Một ứng dụng dùng parallel Flux gọi nhiều đối tác và gom kết quả, nhưng một lỗi được circuit breaker trả fallback muộn làm việc ghép thứ tự kết quả không còn đúng yêu cầu.
Một dịch vụ reactive có bulkhead bảo vệ nguồn, nhưng khi subscriber hủy subscription sớm tài nguyên xử lý ở upstream không được giải phóng như kỳ vọng.
Một hệ thống dùng timeout reactive cho stream cập nhật dài, nhưng chính sách timeout kết thúc toàn bộ Flux khi có khoảng trống hợp lệ giữa hai sự kiện.
Một nhóm thử circuit breaker trên Mono nhưng mock chỉ phát onNext và onComplete, khiến nhánh lỗi và tình huống CallNotPermittedException chưa được kiểm tra.
Một API WebFlux có breaker OPEN và fallback trả Mono.empty, khiến caller hiểu là không có dữ liệu hợp lệ thay vì sự cố phụ thuộc đang được ngăn chặn.
Một ứng dụng ghép ba Mono qua zip và một nguồn trả kết quả rỗng, khiến các nguồn còn lại có thể bị hủy mà đội phát triển hiểu nhầm breaker đã xử lý lỗi.
Một dịch vụ dùng cache trên Mono bị lỗi trước đó, khiến nhiều subscriber sau tiếp tục nhận lỗi được cache dù breaker của provider đã về CLOSED.
Một ứng dụng reactive sử dụng onErrorContinue ở chuỗi xử lý từng item, khiến một số lỗi từ downstream không được tính vào breaker như đội vận hành giả định.
Một nhóm dùng Mono.defer để khởi tạo lời gọi khi subscribe nhưng đặt logic không an toàn ở đoạn tạo publisher, khiến mỗi subscription chạy với thông tin tenant không nhất quán.
Một API reactive có nhiều request đồng thời nhưng operator fallback chứa thao tác chặn thread, khiến event loop bị nghẽn dù circuit breaker phản hồi lỗi rất nhanh.
Một hệ thống trả kết quả qua Server-Sent Events nhưng circuit breaker mở giữa luồng, khiến client nhận kết nối thành công rồi stream bị kết thúc mà không có trạng thái lỗi rõ ràng.
Một dịch vụ thiết lập breaker cho HTTP endpoint vào thay vì lời gọi outbound, khiến lỗi validation của người dùng làm ngắt mạch các request không liên quan.
Một ứng dụng có circuit breaker cho service kho nhưng endpoint health của ứng dụng vẫn báo UP khi mọi lời gọi kho đều bị từ chối trong trạng thái OPEN.
Một nhóm đưa trạng thái OPEN vào readiness probe, khiến load balancer loại cả instance khi một dependency phụ bị lỗi dù những chức năng độc lập vẫn có thể phục vụ.
Một hệ thống chỉ theo dõi failure rate mà không theo dõi số cuộc gọi bị từ chối, khiến khi breaker OPEN tỷ lệ lỗi backend giảm nhưng khách vẫn không nhận được dữ liệu chính.
Một ứng dụng gắn metric breaker theo mã khách hàng, khiến số chuỗi thời gian tăng mạnh và bảng điều khiển Resilience4j khó dùng khi lượng người dùng mở rộng.
Một nhóm thay đổi tên breaker ID trong bản deploy mới nhưng dashboard vẫn truy vấn tên cũ, khiến đường biểu diễn trạng thái và failure rate đột nhiên trống.
Một dịch vụ nhận hàng nghìn CallNotPermittedException mỗi phút nhưng log mọi stack trace, khiến log collector quá tải và che giấu lỗi gốc đã làm breaker OPEN.
Một ứng dụng không ghi lại transition CLOSED sang OPEN, khiến đội trực chỉ thấy fallback tăng mà không biết thời điểm sự cố dependency bắt đầu.
Một hệ thống báo HALF_OPEN lâu bất thường nhưng không đo số permitted calls đã chạy, khiến đội vận hành không rõ đang thiếu traffic hay lời gọi thăm dò bị treo.
Một nhóm theo dõi số lần chuyển trạng thái breaker nhưng không lưu tên dependency và môi trường, khiến lỗi staging bị gộp vào biểu đồ production.
Một dịch vụ có slow-call rate tăng trong khi failure rate thấp, nhưng cảnh báo chỉ áp ngưỡng ngoại lệ nên bộ phận trực không phát hiện tình trạng suy giảm latency.
Một ứng dụng dùng Micrometer metrics cho breaker nhưng không expose endpoint metrics phù hợp với cấu hình scrape, khiến thông số có trong JVM nhưng Prometheus không lấy được.
Một hệ thống có circuit breaker per instance và mỗi node dùng cửa sổ số mẫu khác nhau, khiến gateway phân tải thấy một node từ chối request còn node khác vẫn gọi đối tác.
Một nhóm đặt cảnh báo trên số lần OPEN trong một giờ nhưng không xét lưu lượng, khiến endpoint hiếm dùng tạo cảnh báo nghiêm trọng như endpoint thanh toán chính.
Một ứng dụng ghi trạng thái fallback thành response HTTP 200 và không gắn nhãn fallback, khiến tỷ lệ HTTP success của gateway tăng dù mức chất lượng dữ liệu đang giảm.
Một dịch vụ xuất trace cho lời gọi phụ thuộc nhưng không ghi trạng thái CallNotPermitted vào span, khiến trace của request bị ngắt mạch trông như chưa từng thử gọi ra ngoài.
Một hệ thống ghi error event của breaker vào log với ID dạng động, khiến việc nhóm sự cố cùng một provider qua nhiều node trở nên khó khăn.
Một nhóm nâng ngưỡng breaker sau sự cố nhưng không lưu cấu hình tại thời điểm transition, khiến báo cáo hậu kiểm không giải thích được vì sao breaker đã mở.
Một ứng dụng đo latency trung bình sau khi bật circuit breaker và thấy giảm mạnh, nhưng không tách thời gian của request bị từ chối nhanh khỏi request thực sự thành công.
Một dịch vụ báo số thành công từ fallback như dữ liệu thật trong dashboard doanh thu, khiến lỗi đối tác kéo dài bị che bởi thống kê nghiệp vụ tăng giả.
Một nhóm chỉ kiểm thử logic fallback khi dependency ném exception mà không mô phỏng trạng thái breaker OPEN, khiến đường từ chối CallNotPermitted chưa được xác minh.
Một bài test ngắt mạch gửi quá ít lời gọi so với minimumNumberOfCalls, khiến breaker vẫn CLOSED và test thất bại dù cấu hình tỷ lệ lỗi đã được đặt thấp.
Một ứng dụng dùng count-based window trong production nhưng test mô phỏng thời gian bằng sleep, khiến bộ kiểm thử chậm mà không đo đúng điều kiện thay đổi trạng thái.
Một nhóm test time-based sliding window trên đồng hồ thật và chạy CI tải cao, khiến các request ở biên cửa sổ rơi sang giây khác và kết quả không ổn định.
Một hệ thống kiểm thử HALF_OPEN bằng một lời gọi thành công duy nhất, nhưng cấu hình cho phép nhiều cuộc thăm dò nên test chưa kiểm tra đủ quyết định trở về CLOSED.
Một bài test bật automatic transition mà không tạo request mới, nhưng bộ kiểm thử mặc định breaker luôn có traffic nên bỏ sót trường hợp không có lời gọi thăm dò.
Một dịch vụ kiểm thử kết quả HTTP 404 nhưng không xác minh cấu hình ignoreExceptions, khiến lỗi nghiệp vụ có thể làm tăng failure rate mà test vẫn pass.
Một nhóm mock fallback trả giá trị hợp lệ mà không kiểm tra metadata dữ liệu cũ, khiến client hiển thị thông tin cache hết hạn như kết quả vừa truy vấn.
Một ứng dụng chạy integration test với breaker ID khác production, khiến test không sử dụng đúng failureRateThreshold được cấu hình cho đường gọi thật.
Một bộ test dùng singleton breaker xuyên nhiều test case mà không đặt lại lịch sử, khiến một bài test lỗi làm bài sau nhận CallNotPermittedException ngoài dự kiến.
Một nhóm kiểm thử retry và circuit breaker riêng biệt, nhưng không chạy chung nên không phát hiện khác biệt số attempt khi thay đổi thứ tự decorator.
Một ứng dụng kiểm thử timeout bằng mock trả lỗi ngay lập tức, khiến tình huống tác vụ đã commit ở backend rồi client mới timeout hoàn toàn không được đánh giá.
Một bài test bulkhead chạy tất cả yêu cầu tuần tự, khiến cấu hình permit quá nhỏ không bị phát hiện cho đến khi traffic production có nhiều request đồng thời.
Một hệ thống chỉ kiểm thử thread-pool bulkhead khi queue rỗng, khiến lỗi request chờ hết hạn trong queue không được nhận ra trước deploy.
Một nhóm dùng StepVerifier test Mono thành công nhưng không kiểm tra cancellation và fallback, khiến tài nguyên upstream vẫn bị giữ khi người dùng đóng kết nối.
Một ứng dụng kiểm thử Flux bằng stream hoàn tất sớm, khiến behavior của breaker với nguồn không kết thúc không được đánh giá trong vận hành thực tế.
Một dịch vụ chỉ đánh giá chức năng endpoint khi đối tác khỏe, khiến lúc breaker OPEN hợp đồng HTTP và thông báo lỗi cho client không được xác nhận.
Một nhóm benchmarking circuit breaker chỉ nhìn throughput khi provider bình thường, khiến chi phí của event logging và fallback khi lỗi hàng loạt không nằm trong kết quả đo.
Một hệ thống chạy load test trên một instance và kết luận breaker bảo vệ đủ tốt, nhưng khi scale lên nhiều replica tổng số request thăm dò vượt hạn mức đối tác.
Một ứng dụng không mô phỏng rolling deployment giữa lúc breaker OPEN, khiến sau nâng cấp lưu lượng mới đổ trở lại provider đang hỏng và gây sự cố kéo dài.
Một nhóm diễn tập phục hồi backend sau thời gian OPEN nhưng không thử HALF_OPEN với lời gọi chậm, khiến cấu hình slow-call threshold không được đánh giá trước khi phát hành.
Một ứng dụng có nhiều circuit breaker cho các dependency quan trọng nhưng dashboard chỉ theo dõi trạng thái tổng thể, khiến lúc một dependency yếu dần đội trực không xác định được đường nghiệp vụ bị ảnh hưởng.

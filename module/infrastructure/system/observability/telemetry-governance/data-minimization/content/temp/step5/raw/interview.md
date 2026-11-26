Bạn giải thích mục tiêu tối thiểu hóa dữ liệu telemetry và phân biệt mục tiêu này với việc chỉ giảm chi phí lưu trữ như thế nào?
Bạn xác định dữ liệu quan sát tối thiểu cần thiết để phát hiện và giải thích một sự cố trước khi thiết kế instrumentation ra sao?
Bạn phân biệt dữ liệu cần cho vận hành hiện tại với dữ liệu thu thập theo thói quen nhưng không có mục đích rõ ràng như thế nào?
Bạn lập bản đồ các trường được tạo từ logs, metrics, traces và profiling đến các hệ thống nhận dữ liệu bằng cách nào?
Bạn xác định mục đích sử dụng cụ thể và người chịu trách nhiệm cho từng nhóm trường telemetry như thế nào?
Bạn xây dựng danh mục trường bắt buộc, trường tùy chọn và trường cấm thu thập dựa trên nhu cầu điều tra ra sao?
Bạn phân loại dữ liệu định danh trực tiếp, định danh gián tiếp, bí mật truy cập và dữ liệu vận hành thông thường như thế nào?
Việc kết hợp một giá trị thông thường với timestamp, địa chỉ IP và trace ID có thể làm lộ thông tin nhạy cảm theo những cách nào?
Bạn xác định những rủi ro tái định danh khi telemetry chứa nhiều thuộc tính kết hợp từ các dịch vụ như thế nào?
Bạn chọn phương pháp ghi nhận quyết định thu thập hoặc loại bỏ một trường để các nhóm có thể review về sau ra sao?
Bạn phân biệt việc không thu thập dữ liệu với việc thu thập rồi xóa hoặc che dữ liệu theo nguy cơ phơi lộ như thế nào?
Bạn đánh giá tác động của thu thập dữ liệu quá mức đến bảo mật, hiệu năng, khả năng truy vấn và chi phí hệ thống ra sao?
Bạn thiết kế quy trình thay đổi schema telemetry khi nhóm phát triển muốn thêm một thuộc tính mới như thế nào?
Bạn lựa chọn tiêu chí chấp nhận một trường telemetry dựa trên tính cần thiết, độ nhạy và giá trị chẩn đoán ra sao?
Bạn nhận diện các điểm phát sinh dữ liệu nhạy cảm trong ứng dụng, thư viện, runtime, proxy và hệ thống hạ tầng như thế nào?
Bạn so sánh cách tối thiểu hóa logs, metrics và traces khi mỗi loại tín hiệu có đơn vị dữ liệu và mục đích khác nhau như thế nào?
Bạn xác định những trường metadata nào cần giữ để ghép sự kiện giữa nhiều service mà không tiết lộ danh tính người dùng ra sao?
Bạn thiết kế cơ chế kiểm kê nơi lưu dữ liệu gốc và các bản sao như hàng đợi, Collector, backend, cache và bản xuất báo cáo như thế nào?
Bạn phân biệt dữ liệu telemetry tạm thời phục vụ xử lý với dữ liệu được lưu bền vững và truy cập lâu dài ra sao?
Những ranh giới tin cậy nào yêu cầu phải lọc dữ liệu trước khi chuyển telemetry sang thành phần khác?
Bạn thiết kế quy ước structured logging để ghi mã sự kiện, kết quả và ngữ cảnh mà không lưu nguyên request body ra sao?
Bạn chọn các trường nào trong access log HTTP để điều tra mã lỗi và độ trễ mà không ghi query string chứa dữ liệu cá nhân?
Bạn thay thế URL chứa định danh động bằng route template khi tạo log hoặc span attribute như thế nào?
Bạn xử lý Authorization header, cookie, API key và session token trước khi log HTTP request hoặc response ra sao?
Bạn kiểm soát các trường do thư viện HTTP hoặc database client tự động thêm vào log dù ứng dụng không chủ động ghi như thế nào?
Bạn thiết kế log lỗi để giữ exception type, error code và vị trí lỗi nhưng tránh đưa giá trị đầu vào nhạy cảm vào message ra sao?
Bạn xác định nguy cơ stack trace, nested exception và thông báo validation làm lộ nội dung người dùng như thế nào?
Bạn xây dựng quy tắc ghi log cho thao tác đăng nhập thất bại mà không lưu mật khẩu, token hoặc dữ liệu xác thực thô ra sao?
Bạn phân biệt event ID và account ID trong log khi cần lần vết một phiên xử lý nhưng phải hạn chế định danh cá nhân như thế nào?
Bạn dùng định danh giả hoặc mã tham chiếu cho đối tượng nghiệp vụ để vẫn ghép các bước xử lý mà không để lộ giá trị gốc ra sao?
Bạn lựa chọn hashing, tokenization hoặc masking theo nhu cầu đối chiếu nhiều sự kiện và mức độ bảo vệ cần thiết như thế nào?
Bạn đánh giá nguy cơ băm dữ liệu có không gian giá trị nhỏ vẫn cho phép suy đoán hoặc khôi phục thông tin ban đầu ra sao?
Bạn thiết kế quy trình xoay vòng khóa hoặc salt khi dùng định danh giả trong log mà vẫn giữ khả năng điều tra ra sao?
Những rủi ro nào khiến bạn quyết định loại bỏ hẳn trường dữ liệu thay vì chỉ che một phần giá trị?
Bạn xác định cách ngăn một object serializer ghi toàn bộ entity vào log khi developer chỉ muốn ghi trạng thái xử lý ra sao?
Bạn xử lý log chứa JSON lồng nhau, mảng hoặc dữ liệu tự do để các quy tắc lọc không bỏ sót thông tin nhạy cảm như thế nào?
Bạn lựa chọn chiến lược allowlist field thay vì blocklist pattern trong những loại sự kiện log nào?
Bạn thiết kế chính sách xử lý log DEBUG và TRACE trên production để tránh thu thập payload chi tiết ngoài mục đích vận hành ra sao?
Bạn kiểm soát việc bật log chi tiết tạm thời khi điều tra sự cố bằng phạm vi, thời hạn và người phê duyệt như thế nào?
Bạn thiết kế audit log đủ ghi nhận người thao tác, hành động và kết quả mà không lưu dư thông tin riêng tư như thế nào?
Bạn phân biệt nhu cầu giữ bằng chứng kiểm toán với việc sao chép toàn bộ dữ liệu giao dịch vào audit log ra sao?
Bạn đánh giá tác động của việc loại bỏ request body khỏi log đến khả năng tái hiện lỗi và đề xuất bằng chứng thay thế như thế nào?
Bạn thiết kế metric labels theo service, route, environment và status code để phục vụ SLI mà không dùng user ID hoặc session ID ra sao?
Bạn xác định khi nào một thuộc tính có cardinality cao vừa làm tăng chi phí vừa làm rò rỉ dữ liệu người dùng như thế nào?
Bạn lựa chọn gom nhóm hoặc chuẩn hóa giá trị label để thay thế định danh tài nguyên có thể tăng không giới hạn ra sao?
Bạn dùng histogram hoặc số liệu tổng hợp để theo dõi latency mà không ghi thời gian xử lý của từng người dùng như thế nào?
Bạn xác định mức phân tách tối thiểu theo tenant, zone hoặc version để vẫn phát hiện lỗi cục bộ từ metric ra sao?
Bạn phân biệt label cần thiết cho alert với thuộc tính nên giữ trong log hoặc trace khi thiết kế metric như thế nào?
Bạn đánh giá nguy cơ suy ra thông tin cá nhân từ metric có nhóm dữ liệu quá nhỏ hoặc thưa như thế nào?
Bạn lựa chọn ngưỡng tổng hợp hoặc hạn chế truy vấn để tránh việc công bố metric theo nhóm quá nhỏ ra sao?
Bạn sử dụng exemplar để dẫn từ điểm bất thường của metric sang trace mà không đưa trace ID thành label cho toàn bộ chuỗi thời gian như thế nào?
Bạn thiết kế metric cho request thất bại để giữ khả năng phân biệt nhóm lỗi mà không lưu thông báo lỗi thô ra sao?
Bạn chọn bộ span attributes tối thiểu để phân tích đường đi và độ trễ của request dựa trên tiêu chí nào?
Bạn lựa chọn cách ghi HTTP method, route, status code và peer service trong trace nhưng hạn chế URL hoặc header nhạy cảm ra sao?
Bạn xử lý database statement, query parameter và message payload trong trace để tránh lộ câu lệnh hoặc dữ liệu nghiệp vụ như thế nào?
Bạn phân biệt span event có ích cho chẩn đoán với bản sao log hoặc payload không cần thiết như thế nào?
Bạn kiểm soát trace baggage khi các thuộc tính được truyền qua nhiều service và có thể đến ranh giới tin cậy khác ra sao?
Bạn giảm số lượng và kích thước span attributes khi một trace đi qua nhiều service nhưng vẫn giữ khả năng xác định bottleneck như thế nào?
Bạn quyết định khi nào nên ghi mã lỗi vào trace thay vì nội dung exception message có thể chứa dữ liệu người dùng như thế nào?
Bạn thiết kế chiến lược correlation ID và trace ID để tìm chuỗi sự kiện mà không gắn trực tiếp danh tính cá nhân ra sao?
Bạn phân biệt việc lấy mẫu trace với việc loại bỏ thuộc tính nhạy cảm khỏi mọi trace được thu thập như thế nào?
Bạn xác định tình huống profiling hoặc heap dump có thể chứa chuỗi bí mật và đối tượng người dùng dù không phải log như thế nào?
Bạn lựa chọn phương pháp profiling ít xâm lấn để điều tra CPU hoặc bộ nhớ mà không tạo bản sao toàn bộ dữ liệu ứng dụng ra sao?
Bạn thiết kế giới hạn quyền truy cập, thời gian giữ và xử lý an toàn cho profile có thể chứa thông tin nhạy cảm như thế nào?
Bạn xác định lợi ích và giới hạn của việc lọc telemetry ngay tại ứng dụng so với lọc ở Collector ra sao?
Bạn lập thứ tự các bước drop, redact, transform, sample và export để giảm thời gian dữ liệu nhạy cảm tồn tại trong pipeline như thế nào?
Bạn thiết kế OpenTelemetry Collector processor để xóa thuộc tính không được phép trước khi gửi dữ liệu tới backend như thế nào?
Bạn kiểm tra những rủi ro khi một nhánh pipeline Collector có processor lọc dữ liệu nhưng nhánh khác lại bỏ qua như thế nào?
Bạn lựa chọn cách kiểm soát trường dữ liệu tại nguồn khi chúng đã có thể bị lộ trước khi đến Collector ra sao?
Bạn xử lý trường nhạy cảm nằm trong nội dung log tự do khi pipeline không thể phân tích cấu trúc ổn định như thế nào?
Bạn thiết kế cơ chế fallback khi parser không nhận diện định dạng log mới để không vô tình chuyển dữ liệu chưa được kiểm tra đi xa ra sao?
Trong trường hợp nào bạn từ chối toàn bộ bản ghi telemetry thay vì giữ bản ghi đã che một phần dữ liệu?
Bạn lựa chọn cách xử lý một giá trị không thể mask an toàn mà vẫn tránh làm ứng dụng ngừng phục vụ như thế nào?
Bạn kiểm tra khả năng một exporter gửi dữ liệu thô đến nhà cung cấp bên ngoài trước khi bộ lọc có hiệu lực bằng cách nào?
Bạn đánh giá quyền truy cập vào bộ nhớ đệm, queue tạm và log nội bộ của Collector trong bối cảnh dữ liệu chưa được lọc như thế nào?
Bạn quản lý bí mật cấu hình và quyền chỉnh sửa quy tắc lọc telemetry để tránh người vận hành vô tình vô hiệu hóa bảo vệ ra sao?
Bạn thiết kế các mẫu kiểm thử chứa secret giả lập để xác nhận dữ liệu bị loại bỏ ở cả log, metric và trace như thế nào?
Bạn kiểm tra hiệu quả che thông tin qua nhiều cách biểu diễn như URL encoding, JSON escaping, base64 hoặc chuỗi nhiều dòng ra sao?
Bạn xây dựng bộ dữ liệu kiểm thử có cấu trúc lồng nhau và trường tùy chọn để phát hiện quy tắc redaction bỏ sót như thế nào?
Bạn chọn cách kiểm tra dữ liệu sau processor và dữ liệu tại backend để chứng minh việc lọc thực sự có hiệu lực như thế nào?
Bạn xác định các chỉ số quan sát chính pipeline lọc như số bản ghi bị drop, số trường bị redact và số lỗi parse ra sao?
Bạn phát hiện sự thay đổi schema từ phiên bản ứng dụng mới khiến chính sách lọc telemetry không còn phù hợp bằng cách nào?
Bạn thiết kế quy trình review khi một thư viện tự động instrumentation được nâng cấp và bắt đầu sinh thêm thuộc tính như thế nào?
Bạn cân nhắc quyền truy cập và quy định xử lý dữ liệu khi telemetry phải chuyển qua nhiều vùng hoặc nhà cung cấp như thế nào?
Bạn xác định cách xử lý dữ liệu đã lọt vào backend và bản sao lưu trước khi quy tắc minimization được áp dụng ra sao?
Bạn phân biệt data minimization với retention ngắn và giải thích vì sao hai biện pháp cần phối hợp như thế nào?
Bạn lựa chọn thời hạn giữ log DEBUG, trace chi tiết và metric tổng hợp khác nhau dựa trên nhu cầu điều tra như thế nào?
Bạn thiết kế chính sách hạn chế tải xuống hoặc xuất dữ liệu telemetry để dữ liệu đã được tối thiểu hóa không bị sao chép không kiểm soát ra sao?
Bạn đánh giá rủi ro việc ghép dữ liệu từ dashboard và hệ thống log khác có thể tái tạo thông tin đã bị ẩn ở từng nguồn như thế nào?
Bạn so sánh head-based sampling và tail-based sampling khi muốn giữ đủ bằng chứng lỗi nhưng giảm lượng trace bình thường ra sao?
Bạn lựa chọn xác suất sampling cho giao dịch tần suất cao mà vẫn quan sát được độ trễ và tỷ lệ lỗi như thế nào?
Bạn thiết kế sampling có ưu tiên cho trace lỗi, trace chậm hoặc hành vi bất thường mà tránh thu thập toàn bộ request ra sao?
Bạn đánh giá nguy cơ một sự cố hiếm gặp bị bỏ sót do sampling và chọn cơ chế bảo toàn tín hiệu quan trọng như thế nào?
Bạn phân biệt sampling theo request, theo phiên và theo tenant về tính đại diện và rủi ro thiên lệch như thế nào?
Bạn lựa chọn chính sách giữ lại dấu vết của một giao dịch nhiều bước khi chỉ một phần span được thu thập ra sao?
Bạn đánh giá độ trễ và nhu cầu bộ nhớ của tail sampling trước khi đưa vào môi trường có lưu lượng lớn như thế nào?
Bạn thiết kế sampling thích ứng khi traffic tăng đột ngột nhưng vẫn ưu tiên sự kiện critical như thế nào?
Bạn xác định khi nào cần thu thập 100% một loại audit event thay vì cho phép sampling như thế nào?
Bạn xử lý log sampling để không làm sai cách diễn giải số lượng lỗi và xu hướng sự cố như thế nào?
Bạn tính toán tác động của sampling đến ước lượng throughput, latency và error rate khi tạo dashboard như thế nào?
Bạn kiểm tra xem tập trace được giữ có đại diện cho các route, instance và tenant quan trọng hay không bằng cách nào?
Bạn cân bằng chi phí lưu trữ và khả năng truy vấn khi giảm độ chi tiết telemetry theo thời gian như thế nào?
Bạn thiết kế phương pháp so sánh chất lượng chẩn đoán trước và sau khi loại bỏ một nhóm thuộc tính telemetry ra sao?
Bạn xây dựng bài kiểm thử xác nhận nhóm vận hành vẫn tìm được nguyên nhân của timeout sau khi cắt bớt log request như thế nào?
Bạn đánh giá sự khác biệt giữa tỷ lệ phát hiện sự cố qua metrics và khả năng giải thích sự cố qua logs hoặc traces như thế nào?
Bạn đặt tiêu chí chấp nhận cho chính sách minimization dựa trên độ phủ tín hiệu, tỷ lệ dữ liệu nhạy cảm và overhead ra sao?
Bạn đo tác động của chính sách filtering và redaction lên CPU, bộ nhớ, độ trễ và tỷ lệ mất telemetry như thế nào?
Bạn xây dựng dashboard theo dõi tổng lượng ingest, dữ liệu bị loại và chất lượng tín hiệu sau khi triển khai chính sách như thế nào?
Bạn phân biệt trường bị xóa đúng chính sách với lỗi instrumentation khiến trường quan trọng bị mất qua những kiểm chứng nào?
Bạn kiểm tra các alert hoặc truy vấn LogQL/PromQL bị ảnh hưởng khi loại bỏ label hoặc log field bằng cách nào?
Bạn tổ chức thay đổi chính sách minimization qua Git, review và kiểm thử tự động để dễ đối chiếu phiên bản như thế nào?
Bạn đặt yêu cầu phê duyệt nào khi một nhóm muốn tạm giữ thêm dữ liệu nhạy cảm để điều tra sự cố production?
Bạn xác định thời gian hiệu lực và phạm vi của một ngoại lệ thu thập telemetry để tránh biến ngoại lệ thành mặc định như thế nào?
Bạn thiết kế kế hoạch rollback khi chính sách mới khiến mất tín hiệu critical mà không khôi phục việc thu thập dữ liệu nhạy cảm vô điều kiện ra sao?
Bạn xây dựng runbook cho sự cố phát hiện token hoặc dữ liệu cá nhân xuất hiện trong log, trace hay metric như thế nào?
Bạn kiểm tra những nơi dữ liệu có thể đã được sao chép trước khi xóa hoặc khắc phục một sự cố lộ thông tin telemetry ra sao?
Bạn thiết kế cơ chế audit ghi lại ai sửa chính sách lọc, mục đích thay đổi và thời điểm áp dụng như thế nào?
Bạn phối hợp giữa nhóm phát triển, bảo mật và vận hành để giải quyết xung đột giữa khả năng chẩn đoán và yêu cầu bảo vệ dữ liệu như thế nào?
Bạn xác định những tiêu chí nghiệm thu end-to-end nào chứng minh pipeline thu thập đủ tín hiệu hữu ích nhưng không giữ secret hay dữ liệu cá nhân dư thừa?

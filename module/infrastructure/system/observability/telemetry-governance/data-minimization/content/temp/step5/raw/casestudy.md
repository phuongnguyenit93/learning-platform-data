Một ứng dụng thương mại điện tử ghi toàn bộ JSON request đặt hàng vào log để tiện debug; sau đợt mở rộng sản phẩm, log chứa cả địa chỉ giao hàng và số điện thoại dù đội vận hành chỉ cần mã lỗi và bước xử lý.
Đội SRE đưa metrics, logs và traces về một nền tảng chung nhưng chưa phân loại trường dữ liệu theo mức nhạy cảm; cùng một email khách hàng xuất hiện trong message log, span attribute và metric label.
Một nhóm sản phẩm đề nghị lưu mọi thuộc tính request trong telemetry để phòng sự cố tương lai; khi khối lượng khách hàng tăng, dữ liệu thu thập lớn nhưng phần lớn trường chưa từng được dùng trong các cuộc điều tra.
Ứng dụng chăm sóc khách hàng ghi thông tin hồ sơ vào log với lý do phục vụ truy vết; danh sách trường bắt buộc chưa được xác định nên các bản phát hành mới liên tục bổ sung dữ liệu cá nhân.
Đội vận hành đặt mục tiêu giảm 70% dung lượng telemetry mà không lập danh mục các câu hỏi điều tra quan trọng; một số tín hiệu cần thiết cho cảnh báo thanh toán có nguy cơ bị cắt cùng dữ liệu dư thừa.
Một công ty có log audit, application log và debug log ở cùng pipeline nhưng đều dùng chính sách giữ trường giống nhau; nhóm chưa phân biệt dữ liệu tối thiểu cần thiết cho từng mục đích.
Trong một sự cố, kỹ sư yêu cầu tăng logging toàn ứng dụng để tìm lỗi của một giao dịch; mọi request của các khách hàng khác cũng bị ghi thêm thông tin nhạy cảm trong nhiều giờ.
Doanh nghiệp tích hợp phần mềm của đối tác phát telemetry theo schema riêng; không ai xác định được các trường custom có chứa định danh cá nhân trước khi gửi tới Collector chung.
Một nhóm tạo danh sách trường cấm trong logs nhưng bỏ qua dữ liệu nhạy cảm được lưu ở traces và exemplars; cùng một thông tin vẫn được tìm thấy qua công cụ quan sát khác.
Hệ thống có nhiều môi trường dev, staging và production cùng dùng dữ liệu thử khác mức nhạy cảm; chính sách tối thiểu hóa hiện chỉ áp theo môi trường, không xét nguồn dữ liệu thật có mặt trong staging.
Một API đăng nhập Spring Boot ghi toàn bộ Authorization header trong DEBUG log khi xác thực thất bại; bản ghi được chuyển sang kho tập trung và một người trực phát hiện bearer token còn hiệu lực.
Gateway Nginx ghi nguyên query string trong access log; đường dẫn đặt lại mật khẩu chứa token một lần nên token xuất hiện ở nhiều hệ thống thu thập dù ứng dụng không chủ động ghi token.
Một dịch vụ ghi Cookie header vào log HTTP để tái hiện lỗi phiên đăng nhập; hệ thống quan sát lưu nhiều session ID có thể sử dụng lại cho tới khi chúng hết hạn.
Ứng dụng thanh toán đưa số thẻ và mã xác thực vào thông điệp exception của SDK đối tác; ngay cả khi request body đã bị chặn, nội dung nhạy cảm vẫn vào error log.
Một hệ thống tải hồ sơ khách hàng gặp lỗi parse JSON và ghi nguyên payload bị lỗi; trong payload có giấy tờ định danh và địa chỉ mà đội trực chỉ cần biết vị trí trường sai.
Nhóm dùng structured logging với các trường user.email và customer.phone; một service đổi tên thành emailAddress và mobileNo nên bộ lọc các trường đã biết không còn nhận diện dữ liệu nhạy cảm.
Một API tài chính ghi số tài khoản theo dạng có dấu cách và dấu gạch ngang; bộ quy tắc phát hiện dựa trên mẫu số liền nhau không nhận ra các biến thể trong log.
Ứng dụng Java xây thông báo lỗi bằng cách nối một object người dùng; phương thức toString tự động đưa tên, địa chỉ và thông tin liên hệ vào log mà lập trình viên không nhìn thấy ở chỗ gọi logger.
Một thư viện HTTP bật logging interceptor để chẩn đoán lỗi 400; request và response body chứa dữ liệu cá nhân được ghi ngay cả khi log nghiệp vụ của ứng dụng đã được làm sạch.
Ứng dụng gọi API thanh toán bên ngoài rồi ghi nguyên phản hồi lỗi của nhà cung cấp; response đôi khi chứa token giao dịch và thông tin người trả tiền không thuộc nhu cầu chẩn đoán.
Log xác thực ghi username đúng cả khi người dùng nhập sai mật khẩu; đội bảo mật muốn phân tích brute force nhưng nhà vận hành chưa xác định có cần lưu username đầy đủ cho tất cả lần thử.
Một dịch vụ có log sự kiện reset mật khẩu gồm email, mã xác minh và trạng thái gửi; khi nhân viên tìm lỗi SMTP, log để lộ cả thông tin mà người trực không cần đọc.
Ứng dụng bật Hibernate SQL logging và bind parameters để tìm truy vấn chậm; giá trị tham số chứa email và mã căn cước xuất hiện trong bản ghi database dù log HTTP đã được che.
Một hệ thống bắt exception khi lưu dữ liệu và ghi lại entity JPA hoàn chỉnh; entity chứa nhiều thuộc tính hồ sơ khách hàng không liên quan tới khóa chính gây xung đột.
Đội quản trị bật log toàn bộ gói request trên API gateway trong một giờ; lưu lượng bao gồm multipart upload hồ sơ, khiến dữ liệu tệp người dùng xuất hiện trong kho log tập trung.
Một dịch vụ upload ảnh ghi tên tệp gốc do người dùng đặt; nhiều tên tệp chứa họ tên hoặc mã bệnh án và được đưa vào nhãn sự kiện của dashboard.
Nhóm gửi log từ thiết bị IoT có tọa độ GPS chính xác từng giây; mục tiêu vận hành chỉ là phát hiện lỗi kết nối theo vùng nhưng kho lưu trữ giữ toàn bộ hành trình chi tiết.
Hệ thống chăm sóc y tế phát thông báo lỗi với mã bệnh nhân và phần mô tả tình trạng sức khỏe; đội nền tảng dùng cùng pipeline lưu log cho dịch vụ không xử lý dữ liệu y tế.
Một ứng dụng HR ghi số nhân viên vào log cho mỗi lần truy cập bảng lương; khi nhiều hệ thống phân tích kết hợp mã này với tổ chức và thời gian, dữ liệu vẫn có thể gắn với cá nhân.
Đội phát triển thay email bằng hàm băm không có bí mật và giữ nguyên kết quả ổn định giữa mọi hệ thống; người phân tích lo ngại các địa chỉ phổ biến có thể được đoán lại từ giá trị băm.
Nhóm dùng token giả danh có thể hoàn nguyên để theo dõi lỗi khách hàng; khóa ánh xạ token được cấp cho cùng người dùng có quyền truy vấn log, khiến hiệu quả tối thiểu hóa bị hạn chế.
Một hệ thống thay toàn bộ customer_id bằng chuỗi cố định REDACTED; khi điều tra một giao dịch thất bại nhiều bước, đội trực không phân biệt được sự kiện của các khách hàng khác nhau.
Đội muốn giữ khả năng nối các sự kiện của cùng một phiên mà không lưu session token thật; chính sách ẩn dữ liệu hiện thay giá trị khác nhau ở mỗi service khiến correlation bị đứt.
Một logger che số tài khoản trong message nhưng trường structured accountNumber vẫn giữ giá trị đầy đủ; trên Kibana người xem mở JSON gốc vẫn đọc được thông tin.
Nhóm lọc trường password ở cấp JSON object nhưng một service gửi nested object credentials.password; các bản ghi từ service này còn thông tin mật khẩu dù bộ lọc vẫn báo hoạt động.
Một bộ lọc regex che chuỗi có dạng số thẻ nhưng vô tình che cả trace_id và error_code có định dạng tương tự; người trực không thể liên kết lỗi giữa logs và traces.
Ứng dụng ghi URL có query parameter access_token, code và state; bộ lọc chỉ nhận tên parameter access_token nên các giá trị định danh khác vẫn xuất hiện trong access log.
Trong log lỗi GraphQL, query body có email và địa chỉ như các biến literal; bộ lọc áp lên JSON fields không nhận diện thông tin nằm trong chuỗi query.
Một dịch vụ phát thông điệp protobuf nhị phân kèm thông tin khách hàng; khi debug, nhóm chuyển payload sang base64 đưa vào log và qua được bộ lọc văn bản nhạy cảm.
Logstash che email ở trường message nhưng lưu bản sao event.original chưa được xử lý; API tải dữ liệu gốc vẫn trả thông tin cá nhân.
Một pipeline chuẩn hóa dữ liệu giữ nguyên trường http.request.body.content cho những request lỗi; dashboard chỉ hiển thị mã lỗi nhưng bản ghi thô vẫn có payload và PII.
Nhóm sử dụng cấu trúc log thay đổi theo phiên bản microservice, trong khi danh sách trường cần che cập nhật chậm; những thuộc tính mới vẫn đi vào production trước khi được phân loại.
Ứng dụng mobile gửi diagnostic logs có số điện thoại của danh bạ để hỗ trợ khách hàng; Collector đặt ở backend không có thông tin ngữ cảnh để xác định các trường này vốn không cần thu thập.
Đội triển khai chặn log nhạy cảm ở ứng dụng nhưng sidecar service mesh vẫn ghi nguyên URL và header; một giao dịch có thể để lại thông tin trong lớp hạ tầng khác.
Một reverse proxy ghi địa chỉ IP nguồn đầy đủ cho mọi request trong một năm; nhóm phân tích nhu cầu chỉ cần đếm lỗi theo vùng địa lý và không sử dụng IP riêng lẻ.
Nhóm chuyển sang chỉ lưu địa chỉ IP đã rút gọn để giảm khả năng nhận diện; đội chống gian lận lo ngại vẫn cần điều tra một số hành vi bất thường có phạm vi rất hẹp.
Ứng dụng khách hàng phát mã thiết bị ổn định trong mọi sự kiện debug; dù không chứa tên người, mã này cho phép ghép lịch sử hành vi lâu dài của một thiết bị.
Một dashboard dùng tên người dùng làm label của metric login_attempts_total; các tài khoản mới tạo hàng nghìn time series và backend lưu giữ định danh cá nhân dưới dạng nhãn.
Nhóm gắn email vào Histogram latency để phân tích khách hàng chậm; số chuỗi metric tăng nhanh và dữ liệu định danh xuất hiện trong endpoint /metrics không được bảo vệ như log.
Ứng dụng phát số điện thoại dưới dạng label lỗi SMS; tên chuỗi metric đi vào danh sách nhãn của backend ngay cả khi không có sự kiện lỗi mới trong nhiều ngày.
Một service lưu order_id làm nhãn Counter để đếm retry; lượng mã đơn lớn khiến cardinality tăng, còn đội vận hành chỉ muốn biết số lần thử lại theo loại lỗi.
Đội phát triển đề nghị dùng trace_id làm metric label để nhấp từ biểu đồ sang từng trace; mỗi request tạo chuỗi mới và chi phí lưu metrics trở nên không kiểm soát.
Một backend metrics có exemplars nối tới trace chứa thông tin cá nhân; người xem chỉ được phép truy cập số liệu tổng hợp nhưng liên kết dẫn tới dữ liệu chi tiết chưa được tối thiểu hóa.
Nhóm loại bỏ user_id khỏi metrics nhưng vẫn dùng tổ hợp postcode, tuổi và phân khúc nghề nghiệp làm labels; một số tổ hợp hiếm đủ cụ thể để suy ra cá nhân.
Dashboard chia error rate theo tenant và endpoint, trong đó một tenant chỉ có một người dùng hoạt động; biểu đồ tổng hợp vẫn có thể tiết lộ hành vi của cá nhân qua mốc thời gian.
Nhóm giữ label client_ip cho metrics request rate trên mỗi máy; số IP thay đổi liên tục tạo áp lực cardinality dù mục tiêu chính là theo dõi tốc độ lỗi theo vùng.
Một Counter phát nhãn error.message từ exception chứa mã khách hàng; cùng loại lỗi tạo hàng nghìn label khác nhau dù đã che trường customer_id trong log.
Nhóm đổi các nhãn có cardinality cao thành tập giá trị cố định nhưng đưa tất cả các lỗi lạ vào nhóm other; khi lỗi bất thường tăng, dashboard không còn phân biệt được các kiểu lỗi vận hành quan trọng.
Đội dùng sampling ở mức request để giảm dữ liệu metrics nghiệp vụ nhưng không ghi lại tỷ lệ được giữ; số đơn thành công trên dashboard thấp hơn số thực tế mà không có dấu hiệu điều chỉnh.
Một hệ thống tính SLO availability từ các Counter được thu thập đầy đủ nhưng loại bớt một số mã lỗi để giảm dữ liệu; báo cáo SLO đạt mục tiêu trong khi khách hàng gặp nhiều lỗi bị bỏ sót.
Nhóm cần theo dõi latency p99 của endpoint hiếm nhưng loại toàn bộ Histogram của endpoint có lưu lượng thấp; sự cố của nhóm khách hàng nhỏ không còn xuất hiện trên dashboard.
Một dịch vụ chọn bucket Histogram rất chi tiết theo mã đơn để dễ điều tra; mỗi bucket nhân với số label làm backend metrics lưu nhiều dữ liệu không mang thêm thông tin vận hành.
Một ứng dụng phát trace span cho HTTP request chứa user.email trong attributes; sau khi tắt log body, email vẫn được chuyển sang nền tảng tracing.
Instrumentation Java tự động ghi http.url đầy đủ vào span; URL có query token và thông tin tìm kiếm nhạy cảm khiến dữ liệu cá nhân xuất hiện dù request body không được ghi.
Nhóm đặt tên span bằng số đơn hàng để tìm nhanh giao dịch; kho tracing lưu hàng triệu tên operation riêng lẻ, nhiều tên còn chứa thông tin thuộc về khách hàng.
Một client HTTP ghi header Authorization vào span attributes để debug lỗi 401; nhiều token còn hiệu lực được gửi tới Collector dùng chung với các đội khác.
Ứng dụng gắn toàn bộ baggage chứa email và tenant name vào mọi span con; một thông tin chỉ cần ở đầu luồng lan sang hàng chục dịch vụ không có nhu cầu xử lý nó.
Một trace xuyên nhiều service giữ user_id đầy đủ trong resource attributes thay vì thuộc tính từng request; cùng định danh bị gắn nhầm vào các request khác trong tiến trình đa người dùng.
Nhóm dùng span.addEvent kèm toàn bộ đối tượng Order trước và sau cập nhật; trace cho một giao dịch chứa cả địa chỉ giao hàng và lịch sử giá dù mục tiêu chỉ đo thời gian ghi dữ liệu.
Ứng dụng ghi stack trace exception vào span event, trong đó exception message chứa SQL bind parameters; dữ liệu nhạy cảm vẫn được giữ dù các span attribute đã được lọc.
Một dịch vụ tích hợp bên thứ ba đưa response body lỗi vào span; đối tác đôi khi trả hồ sơ khách hàng trong thông điệp lỗi nên trace lưu nhiều dữ liệu ngoài quyền kiểm soát của ứng dụng.
Nhóm lấy mẫu 100% traces của các request trả 500, nhưng một số exception có message chứa token tạm; các sự cố bảo mật vô tình làm tăng lượng secret được thu thập.
Trong xử lý Kafka, producer ghi nguyên payload event vào span thay vì chỉ thông tin topic và thao tác; consumer tiếp tục tạo bản sao payload khiến dữ liệu nhạy cảm nhân lên theo số bước.
Một workflow bất đồng bộ có nhiều bước và span links; mỗi bước sao chép toàn bộ baggage dù chỉ cần correlation ID, làm tăng kích thước telemetry và phạm vi dữ liệu được lan truyền.
Đội điều tra muốn giữ trace_id để nối các service nhưng bộ lọc Collector loại bỏ cả trace_id như dữ liệu nhạy cảm; logs vẫn đến nơi nhưng không thể tìm luồng yêu cầu tương ứng.
Một hệ thống dùng transaction_id làm chìa khóa điều tra giao dịch; chính sách xóa mọi định danh ở Collector làm nhiều sự kiện khác nhau không thể được ghép để truy vết lỗi thanh toán.
Nhóm thay thông tin người dùng trong traces bằng mã giả danh nhưng mã thay đổi giữa các vùng; cuộc điều tra một request đi qua hai vùng không thể liên kết các bước cùng giao dịch.
Một collector xoá attribute http.route để giảm dữ liệu; dashboard truy vấn latency theo endpoint không còn phân biệt được route thanh toán với route health check.
Đội lọc toàn bộ db.statement khỏi traces vì có thể chứa tham số nhạy cảm; trong sự cố truy vấn chậm, span chỉ còn duration mà thiếu dấu hiệu phân biệt loại truy vấn.
Nhóm bỏ tất cả message exception khỏi tracing; số lượng error span không đổi nhưng đội trực không phân biệt được lỗi timeout, sai dữ liệu và vi phạm ràng buộc.
Một service tạo span cho mỗi vòng lặp xử lý 100 nghìn bản ghi; dung lượng tracing vượt ngân sách trong khi đội vận hành chủ yếu cần duration tổng và số lượng bản ghi lỗi.
Ứng dụng ghi toàn bộ HTTP headers thành span attributes để điều tra lỗi CORS; Cookie, Authorization và các header tùy chỉnh nhạy cảm bị xuất cùng các header chẩn đoán bình thường.
Một dự án thay mọi giá trị customer_id bằng chuỗi rỗng trong logs nhưng vẫn giữ request path chứa ID đó; công cụ quét chỉ kiểm tra tên trường nên không phát hiện định danh còn sót.
Collector dùng processor lọc dữ liệu nhạy cảm trước exporter chính nhưng một exporter debug vẫn gửi bản ghi nguyên vẹn tới một backend thử nghiệm không được đánh giá.
Một OpenTelemetry Collector nhận OTLP logs và traces rồi áp bộ lọc chỉ cho pipeline logs; thông tin PII vẫn tới kho traces do hai pipeline cấu hình khác nhau.
Nhóm khai báo attributes processor để xóa password nhưng dữ liệu xuất hiện trong body của log record, không nằm trong attributes; cấu hình chạy thành công mà dữ liệu nhạy cảm vẫn được lưu.
Đội phát triển dùng transform processor theo tên trường account.number, nhưng một nguồn JSON đặt tên khác sau nâng cấp schema; các bản ghi mới đi qua mà không bị che.
Trong Collector, các processor đổi tên và làm giàu attribute chạy trước bộ lọc PII; trường nhạy cảm được tạo ra bằng phép nối nhiều giá trị sau khi chính sách lọc ban đầu đã kiểm tra.
Một pipeline đưa dữ liệu vào batch processor trước khi áp quy tắc xóa trường nhạy cảm; dữ liệu chưa được lọc nằm trong bộ nhớ và hàng đợi của thành phần trung gian trong thời gian xử lý.
Collector gửi telemetry qua hai exporter tới kho chính và kho phân tích thử nghiệm; bộ lọc trên nhánh chính không được áp dụng giống nhánh phụ nên dữ liệu nguyên bản vẫn bị lưu.
Đội áp dụng danh sách allowlist fields ở Collector nhưng không tính đến các semantic conventions mới của OpenTelemetry; sau nâng cấp SDK, nhiều trường chẩn đoán quan trọng biến mất.
Nhóm dùng danh sách denylist tên trường nhạy cảm; một ứng dụng mới gửi thông tin bí mật trong nested JSON object khiến bộ lọc không nhận diện các khóa chưa biết.
Một hệ thống lọc token bằng regex trên dữ liệu văn bản, nhưng token được mã hóa URL trong path và base64 trong message; công cụ thử nghiệm báo qua khi dùng mẫu token thông thường.
Collector che mọi chuỗi 16 chữ số mà không xét ngữ cảnh; nhiều mã định danh không nhạy cảm và số liệu kỹ thuật cũng bị cắt, làm giảm khả năng tìm nguyên nhân sự cố.
Nhóm thay email bằng token trong Collector nhưng vẫn giữ bản gốc của log trong queue lưu bền vững ở agent; khi đĩa host được sao lưu, dữ liệu chưa che vẫn tồn tại.
Một ứng dụng lọc payload ngay tại nguồn, nhưng collector ở node khác tiếp tục làm giàu sự kiện bằng metadata nhạy cảm; phạm vi dữ liệu sau lọc không còn khớp thiết kế ban đầu.
Đội dựa vào Collector để che log nhạy cảm sau khi ứng dụng đã gửi dữ liệu qua mạng nội bộ không mã hóa; nội dung gốc vẫn hiện diện trên đoạn truyền trước điểm lọc.
Một ứng dụng chọn lọc trường trước khi tạo span nhưng Java agent tự động bổ sung URL và header; trace cuối cùng chứa dữ liệu không có trong custom instrumentation.
Nhóm phát hiện một plugin exporter ghi dữ liệu chưa lọc vào log debug của chính Collector; việc che dữ liệu ở pipeline chính không ngăn các bản sao ngoài dự kiến.
Một nguồn telemetry ghi JSON không hợp lệ, khiến processor lọc trường bỏ qua việc parse nhưng vẫn chuyển message gốc; các bản ghi lỗi parser có tỷ lệ chứa PII cao hơn log bình thường.
Nhóm thiết lập chính sách xóa attribute khi không có trong schema, nhưng vendor library bổ sung trường mới về mã phiên người dùng; collector giữ nguyên do policy được áp trước bước chuyển đổi.
Đội muốn tối thiểu hóa dữ liệu bằng cách lọc ở SDK Java, trong khi cùng ứng dụng vẫn chạy agent Logback gửi log gốc qua đường khác; hai đường thu thập không thống nhất.
Ứng dụng có health-check traffic chiếm phần lớn số span; nhóm muốn giảm telemetry không cần thiết nhưng vẫn cần biết tỷ lệ health check lỗi và các đợt sụt giảm khả dụng.
Trong giờ mở bán, hệ thống nhận 100 nghìn request mỗi giây; việc giữ 100% trace của request thành công tiêu tốn nhiều tài nguyên trong khi nhóm điều tra chủ yếu tìm lỗi và request chậm.
Nhóm dùng head-based sampling 1% cho mọi trace; một sự cố chỉ ảnh hưởng một khách hàng trong vài phút không có trace nào được giữ dù error log đã ghi nhận nhiều lỗi.
Một pipeline tail sampling ưu tiên trace lỗi và chậm nhưng không có trường outcome ổn định; request thất bại theo nghiệp vụ trả HTTP 200 bị loại như request thành công.
Collector lấy mẫu traces theo độ trễ nhưng một số transaction được xử lý bất đồng bộ sau khi HTTP response trả 202; chính sách chỉ nhìn duration HTTP và bỏ qua workflow chậm.
Nhóm cấu hình tail sampling để giữ toàn bộ trace của nhóm dịch vụ thanh toán; dữ liệu của các dịch vụ ít nhạy cảm được giảm mạnh nhưng tổng chi phí không đổi do traffic thanh toán quá lớn.
Đội điều chỉnh tỷ lệ sampling theo môi trường nhưng không ghi tỷ lệ áp dụng vào metadata; khi so sánh số lỗi qua traces giữa staging và production, kết quả không phản ánh tỷ lệ traffic thực.
Một nhóm chỉ giữ trace của request 5xx và bỏ phần lớn request thành công; khi muốn tính phân bố latency thực tế từ tập traces đã lưu, p99 bị thiên lệch về các request lỗi.
Trong một dịch vụ xử lý tài khoản, trace hiếm của request đăng nhập bất thường cần được giữ, nhưng chính sách sampling chỉ ưu tiên thời gian xử lý dài nên bỏ các request thất bại nhanh.
Một collector triển khai hai bước sampling ở gateway và backend lưu trữ mà không công bố tỷ lệ kết hợp; nhóm sản phẩm diễn giải số trace được lưu như tổng lưu lượng người dùng.
Nhóm áp xác suất sampling cố định cho mọi tenant; một tenant nhỏ chỉ có vài trăm request mỗi ngày không có trace hữu ích khi sự cố của họ xảy ra.
Đội chọn tăng sampling khi phát hiện alert nghiêm trọng, nhưng cấu hình được giữ nhiều ngày sau khi sự cố kết thúc; log và traces tăng đột ngột, bao gồm dữ liệu không cần thiết.
Một hệ thống dùng span events để lưu mọi lần retry và log lỗi cho cùng một request; khi upstream chập chờn, ba tín hiệu chứa cùng nội dung chi tiết được gửi lặp lại nhiều lần.
Nhóm loại hoàn toàn logs request thành công nhằm giảm dữ liệu; khi phát hiện hành vi lỗi chỉ xuất hiện sau một chuỗi bước thành công, đội điều tra thiếu bối cảnh thời gian và trạng thái.
Ứng dụng chỉ giữ các metric tổng hợp theo phút để giảm chi phí, nhưng sự cố kéo dài 10 giây bị hòa trong giá trị trung bình và không kích hoạt cảnh báo.
Đội giảm số label cho metrics bằng cách bỏ region; một vùng sản xuất gặp lỗi lặp lại mà dashboard toàn quốc vẫn hiển thị tốt do lưu lượng vùng khác lớn hơn nhiều.
Nhóm bỏ service.version khỏi resource attributes để tiết kiệm dung lượng; sau rolling deployment, độ trễ tăng nhưng không thể phân biệt ảnh hưởng giữa phiên bản cũ và mới.
Một hệ thống xóa toàn bộ tenant_id khỏi telemetry để giảm rủi ro; nhóm trực không thể cô lập sự cố chỉ xảy ra với một khách hàng doanh nghiệp dù các trường khác không đủ ngữ cảnh.
Ứng dụng giữ một mã correlation ngẫu nhiên theo request nhưng không giữ user_id; trong sự cố liên quan đến nhiều request của cùng một khách, các sự kiện không còn mối liên hệ hỗ trợ điều tra.
Nhóm chọn lưu dữ liệu chính xác cấp cá nhân để phân tích xu hướng hành vi, trong khi câu hỏi vận hành chỉ cần số lượng request theo giờ; khối lượng chi tiết vượt nhu cầu mà không cải thiện cảnh báo.
Đội tạo dashboard lỗi theo mã bưu chính với những khu vực chỉ có một khách; dù không lưu tên, tổ hợp vị trí và thời điểm có thể tiết lộ hoạt động của người đó.
Nhóm lưu histogram theo nhóm tuổi rất hẹp và khu vực nhỏ; một nhóm chỉ có một người dùng, khiến kết quả tổng hợp vẫn mang nguy cơ tái nhận diện.
Trong một cuộc điều tra, kỹ sư cần tạm tăng mức chi tiết log cho đúng một request; chính sách hiện chỉ hỗ trợ bật DEBUG cho toàn bộ pod và mọi khách hàng cùng thời điểm.
Nhóm tích hợp hệ thống kiểm tra chất lượng dữ liệu nhưng chỉ xác nhận bộ lọc không còn trường password; không có kiểm thử cho authorization token, email, số điện thoại hay payload lồng nhau.
Đội chạy kiểm thử dữ liệu giả với email theo mẫu cố định; trong production, PII nằm trong nhiều ngôn ngữ và biến thể định dạng nên bộ kiểm tra mẫu không phát hiện hết.
Một bộ thử nghiệm gửi canary secret qua HTTP và xác nhận không xuất hiện trong logs, nhưng secret vẫn hiện diện trong span error events của cùng request.
Nhóm đo hiệu quả tối thiểu hóa bằng tổng số byte giảm được sau Collector; số sự kiện lỗi được giữ cũng giảm mạnh nhưng không ai đánh giá tác động đến khả năng xác định nguyên nhân.
Trong một sự cố giả lập, đội điều tra cần tìm request giữa gateway, service và database; bộ lọc vừa triển khai đã xóa route và correlation ID nên thời gian khoanh vùng tăng gấp nhiều lần.
Đội QA chỉ kiểm tra output của một Collector replica; replica còn lại chạy cấu hình cũ và vẫn xuất dữ liệu chưa che cho một phần request production.
Nhóm sửa cấu hình redaction qua GitOps nhưng một Collector DaemonSet không được rollout; log thu thập trên vài node vẫn chứa dữ liệu nhạy cảm dù dashboard triển khai báo thành công.
Một phiên bản ứng dụng mới đưa thêm trường profile vào structured log; pipeline lọc vẫn hoạt động bình thường nhưng chính sách phân loại không nhận diện thuộc tính mới trước phát hành.
Đội vận hành kiểm tra số sự kiện log trước và sau giảm dữ liệu nhưng không đối chiếu các trường bắt buộc của runbook; cảnh báo vẫn firing nhưng thông báo thiếu service và error_code.
Một pipeline từ chối toàn bộ bản ghi khi phát hiện PII để tránh lưu dữ liệu nhạy cảm; vào ngày API lỗi, gần như mọi error log bị loại và đội trực thiếu bằng chứng về sự cố.
Nhóm chọn cắt message sau 500 ký tự để giảm dung lượng; mã lỗi và chi tiết stack trace thường nằm cuối chuỗi nên nhiều bản ghi không còn thông tin chẩn đoán.
Một ứng dụng che mọi địa chỉ IP trong log lỗi truy cập; sau khi xảy ra tấn công từ một mạng cụ thể, đội an ninh không còn tín hiệu tối thiểu để phân biệt nguồn request bất thường.
Đội thử giảm retention logs từ 30 xuống 3 ngày nhưng vẫn cần phân tích chu kỳ lỗi cuối tháng; sự cố được khách báo sau một tuần không còn đủ dấu vết để tái hiện.
Nhóm lưu dữ liệu debug thô lâu hơn dữ liệu lỗi đã chuẩn hóa; khi phát hiện dữ liệu nhạy cảm bị gửi nhầm, bản sao giữ lâu nhất lại là bản ít được kiểm soát nhất.
Một hệ thống sử dụng dữ liệu của khách châu Âu và khu vực khác, nhưng chính sách tối thiểu hóa chung bỏ qua loại dữ liệu và mục đích xử lý riêng của từng nguồn; dữ liệu không cần thiết bị chuyển qua nhiều vùng.
Nhóm xóa bản ghi nhạy cảm khỏi Elasticsearch sau khi phát hiện lỗi ingest, nhưng dữ liệu vẫn tồn tại trong snapshot và bản sao gửi sang môi trường thử nghiệm trước đó.
Trong một sự cố, đội phát hiện token đã bị ghi ra log vài giờ trước; thay đổi Collector chỉ ngăn log mới chứ không xử lý các bản sao trong buffer, queue và kho lưu trữ.
Chính sách phân loại dữ liệu được viết trong wiki nhưng không gắn owner, phiên bản schema hay bằng chứng phê duyệt; hai nhóm ứng dụng áp danh sách trường cần bỏ khác nhau.
Một nhóm xây policy-as-code cho phép các trường telemetry đã được duyệt, nhưng pipeline mới do vendor cung cấp chưa có test; bản phát hành thêm nhiều trường không rõ mục đích được lưu tự động.
Đội nền tảng quản lý cấu hình Collector bằng Git nhưng các ứng dụng tự bật log payload trong runtime; chính sách trung tâm không phát hiện thay đổi tại nguồn dữ liệu.
Một công ty đặt yêu cầu không thu thập secret, nhưng telemetry từ các hệ thống legacy không có hợp đồng schema; nhóm không biết trường message có thể chứa những dạng secret nào.
Nhóm bổ sung cảnh báo khi thấy chuỗi giống token trong output Collector; một đợt lỗi parser khiến nội dung không đọc được được bỏ qua kiểm tra và vẫn chuyển vào kho.
Đội định nghĩa chỉ tiêu giảm cardinality và byte ingest nhưng không ghi tỷ lệ false positive của bộ lọc PII; nhiều mã giao dịch cần thiết bị che sai mà không có tín hiệu chất lượng.
Nhóm đánh giá một sampling policy chỉ bằng mức giảm chi phí storage; không có bộ request lỗi giả lập và trace xuyên dịch vụ để kiểm chứng còn đủ tín hiệu điều tra.
Trong cuộc rà soát sau sự cố, đội trực phát hiện dấu hiệu bất thường có mặt trong log thô nhưng không tới dashboard do bộ lọc mới; cấu hình được đổi mà chưa có phép đo mức mất thông tin theo loại sự kiện.
Đội tạo đường thu thập chẩn đoán khẩn cấp có thể tạm bỏ qua quy tắc minimization để xử lý production; không có giới hạn thời gian, phạm vi dịch vụ hay dấu vết phê duyệt cho chế độ này.
Một ứng dụng tạo metric tổng hợp theo tenant và không chứa định danh cá nhân, nhưng trace liên kết qua exemplar vẫn giữ request payload đầy đủ; chính sách đánh giá từng tín hiệu riêng bỏ qua liên kết dữ liệu giữa chúng.
Nhóm kiểm tra data minimization qua dashboard và kết luận không có PII, trong khi raw search API vẫn trả các attributes bị ẩn ở giao diện; cùng tài liệu có hai cách xem khác nhau.
Một công ty giảm đáng kể log request thành công và dùng sampling có mục đích, nhưng sau ba tháng không đo được tỷ lệ sự cố được chẩn đoán thành công; giá trị vận hành của tín hiệu còn lại chưa được kiểm chứng.

Bạn sẽ giải thích những rủi ro nào khiến logs, metrics, traces và profiles cũng cần được quản trị như dữ liệu nghiệp vụ?
Bạn sẽ xác định mục tiêu của việc phân loại telemetry trước khi thiết kế pipeline thu thập dữ liệu ra sao?
Bạn sẽ phân biệt mức nhạy cảm của dữ liệu với mức độ quan trọng trong vận hành bằng những ví dụ nào?
Bạn sẽ xây dựng các cấp phân loại như công khai, nội bộ, mật và hạn chế truy cập theo tiêu chí nào?
Bạn sẽ thiết kế ma trận phân loại dựa trên loại dữ liệu, nguồn phát, đối tượng liên quan và hậu quả lộ lọt ra sao?
Bạn sẽ xác định chủ sở hữu dữ liệu và người chịu trách nhiệm phê duyệt chính sách telemetry ở từng hệ thống như thế nào?
Bạn sẽ phân biệt phân loại ở cấp luồng telemetry với phân loại ở cấp từng trường dữ liệu ra sao?
Bạn sẽ quyết định mức phân loại cho một sự kiện chứa đồng thời thông tin công khai và dữ liệu cá nhân như thế nào?
Bạn sẽ xác định nguyên tắc kế thừa mức nhạy cảm khi nhiều nguồn telemetry được hợp nhất vào cùng một bản ghi ra sao?
Bạn sẽ xây dựng quy trình rà soát lại phân loại khi schema ứng dụng hoặc mục đích sử dụng dữ liệu thay đổi như thế nào?
Bạn sẽ lựa chọn tiêu chí nào để đánh giá mức rủi ro từ khả năng nhận dạng, độ nhạy cảm và phạm vi truy cập?
Bạn sẽ phân biệt dữ liệu cá nhân trực tiếp, định danh gián tiếp và dữ liệu có thể tái nhận dạng qua kết hợp nhiều trường ra sao?
Bạn sẽ đánh giá địa chỉ IP, device ID hoặc user ID có khả năng nhận dạng cá nhân trong những ngữ cảnh nào?
Bạn sẽ phân loại email, số điện thoại và tên người dùng khi chúng xuất hiện trong log lỗi đăng nhập ra sao?
Bạn sẽ đánh giá nguy cơ lộ dữ liệu nhạy cảm khi exception message chứa nội dung request hoặc phản hồi từ bên thứ ba như thế nào?
Bạn sẽ phân biệt credential, access token, API key, session cookie và mã định danh vô hại trong telemetry như thế nào?
Bạn sẽ xây dựng danh sách thông tin xác thực bị cấm ghi vào logs và traces theo nguyên tắc bảo mật nào?
Bạn sẽ đánh giá rủi ro khi header Authorization hoặc Cookie bị middleware ghi vào log HTTP như thế nào?
Bạn sẽ phân loại query parameter của URL khi có thể chứa email, token hoặc mã khôi phục tài khoản ra sao?
Bạn sẽ kiểm tra dữ liệu cá nhân bị lồng trong chuỗi JSON, stack trace hoặc thông điệp lỗi chưa có cấu trúc như thế nào?
Bạn sẽ xác định khi nào tên tài khoản, tenant hoặc tổ chức được coi là thông tin nhạy cảm trong telemetry ra sao?
Bạn sẽ đánh giá khả năng một trace ID hoặc request ID bị dùng để liên kết hành vi của người dùng qua nhiều hệ thống như thế nào?
Bạn sẽ phân biệt mã định danh ngẫu nhiên phục vụ tương quan kỹ thuật với mã định danh người dùng bền vững ra sao?
Bạn sẽ xác định điều kiện nào khiến dữ liệu đã được băm vẫn có thể bị suy ra danh tính người dùng như thế nào?
Bạn sẽ phân biệt masking, redaction, tokenization, pseudonymization và anonymization theo mục đích bảo vệ ra sao?
Bạn sẽ lựa chọn biện pháp xóa hẳn, thay thế hoặc rút gọn dữ liệu nhạy cảm dựa trên nhu cầu điều tra nào?
Bạn sẽ xác định khi nào chỉ ẩn một phần email hoặc số thẻ vẫn tạo nguy cơ nhận dạng người dùng ra sao?
Bạn sẽ phân tích rủi ro của việc dùng hash không có khóa cho giá trị có không gian tìm kiếm nhỏ như thế nào?
Bạn sẽ cân nhắc dùng token ổn định để liên kết sự kiện giữa các dịch vụ mà không lưu định danh gốc như thế nào?
Bạn sẽ kiểm tra liệu dữ liệu sau khi đã che hoặc giả danh hóa còn đáp ứng yêu cầu phân tích vận hành nào?
Bạn sẽ xây dựng chính sách tối thiểu hóa dữ liệu để chỉ giữ những trường thực sự cần cho điều tra sự cố ra sao?
Bạn sẽ xác định cách ghi mục đích sử dụng hợp lệ cho từng nhóm telemetry và kiểm tra việc dùng lại ngoài mục đích ra sao?
Bạn sẽ phân loại thông tin cấu hình hạ tầng như tên host, địa chỉ nội bộ và đường dẫn filesystem trong log như thế nào?
Bạn sẽ đánh giá rủi ro khi stack trace làm lộ cấu trúc package, đường dẫn mã nguồn hoặc chi tiết hệ thống nội bộ ra sao?
Bạn sẽ phân biệt dữ liệu lỗi kỹ thuật với dữ liệu nghiệp vụ nhạy cảm có thể xuất hiện trong cùng thông báo như thế nào?
Bạn sẽ thiết kế một danh mục trường được phép thu thập và trường bị cấm cho log request/response ra sao?
Bạn sẽ đặt điều kiện, người phê duyệt và giới hạn thời gian nào cho ngoại lệ thu thập một trường nhạy cảm để điều tra sự cố?
Bạn sẽ thiết kế cơ chế hết hạn tự động cho quyền ngoại lệ thu thập dữ liệu nhạy cảm như thế nào?
Bạn sẽ đánh giá nguy cơ dữ liệu nhạy cảm bị sao chép sang log gỡ lỗi khi bật DEBUG trong production ra sao?
Bạn sẽ lập quy trình kiểm kê các nguồn telemetry chưa được quản lý do thư viện hoặc agent tự động phát sinh như thế nào?
Bạn sẽ phân loại structured logs và unstructured logs khác nhau về khả năng phát hiện trường nhạy cảm ra sao?
Bạn sẽ xác định các trường bắt buộc của một log bảo mật mà không cần ghi nguyên nội dung người dùng gửi lên như thế nào?
Bạn sẽ thiết kế mẫu log HTTP chỉ ghi route template thay vì URL đầy đủ để tránh lộ ID và query parameter ra sao?
Bạn sẽ cân nhắc có nên ghi request body hoặc response body khi điều tra lỗi API dựa trên những tiêu chí nào?
Bạn sẽ xác định cách loại bỏ dữ liệu nhạy cảm trước khi serialize một object nghiệp vụ thành log như thế nào?
Bạn sẽ xử lý log chứa dữ liệu nhiều dòng hoặc JSON lồng nhau để quy tắc phát hiện PII không bị bỏ sót ra sao?
Bạn sẽ phân biệt việc xóa trường nhạy cảm ở ứng dụng với việc lọc tại agent hoặc collector về độ an toàn như thế nào?
Bạn sẽ phát hiện secrets lộ trong log từ thư viện bên thứ ba dù mã ứng dụng không trực tiếp ghi các trường đó như thế nào?
Bạn sẽ xác định trường hợp nào log truy vấn cơ sở dữ liệu có thể chứa thông tin cá nhân trong tham số hoặc SQL literal?
Bạn sẽ thiết kế cách log lỗi xác thực mà không ghi mật khẩu, token hoặc câu trả lời bảo mật của người dùng ra sao?
Bạn sẽ bảo vệ log liên quan đến thanh toán khi cần giữ mã lỗi và trạng thái giao dịch nhưng không được lộ dữ liệu thẻ như thế nào?
Bạn sẽ phân loại access log tại reverse proxy khác với application log khi chúng chứa các trường nhận dạng khác nhau ra sao?
Bạn sẽ xác định nguy cơ log infrastructure chứa private key hoặc mật khẩu khi một lệnh triển khai thất bại như thế nào?
Bạn sẽ truy vết các bản sao log từ container stdout qua node agent để xác định dữ liệu nào đã được lưu trước khi redaction ra sao?
Bạn sẽ xác định nhãn metrics nào có nguy cơ lộ PII dù bản thân giá trị đo chỉ là số đếm như thế nào?
Bạn sẽ giải thích vì sao gắn email, user ID hoặc token làm metric label vừa gây rủi ro riêng tư vừa tăng cardinality ra sao?
Bạn sẽ lựa chọn nhãn route template, HTTP method và status để thay thế nhãn URL hoặc ID động như thế nào?
Bạn sẽ xác định khi nào nhãn tenant hoặc customer cần được phân nhóm thay vì giữ nguyên mã định danh ra sao?
Bạn sẽ đánh giá nguy cơ tổng hợp metric theo nhóm quá nhỏ khiến có thể suy ra hành vi của một người dùng như thế nào?
Bạn sẽ thiết kế chính sách giới hạn số giá trị của nhãn metrics để đồng thời quản trị bảo mật và hiệu năng ra sao?
Bạn sẽ phân biệt việc loại bỏ metric không cần thiết với việc giữ metric nhưng chuẩn hóa nhãn nguy hiểm như thế nào?
Bạn sẽ kiểm tra khả năng metric còn dữ liệu nhạy cảm trong tên series hoặc exemplars sau khi đã xóa các nhãn rõ ràng ra sao?
Bạn sẽ đánh giá trace attributes có thể chứa PII từ HTTP headers, URL hoặc thông tin người dùng như thế nào?
Bạn sẽ thiết kế danh sách các span attributes được phép ghi theo semantic conventions và nhu cầu điều tra ra sao?
Bạn sẽ xử lý trường hợp tracing tự động thu thập query string hoặc database statement chứa dữ liệu cá nhân như thế nào?
Bạn sẽ phân biệt dữ liệu trong span events, attributes, status message và baggage khi xây dựng quy tắc phân loại ra sao?
Bạn sẽ giải thích vì sao baggage cần được kiểm soát nghiêm ngặt khi được truyền qua nhiều dịch vụ và ranh giới tin cậy như thế nào?
Bạn sẽ lựa chọn cách truyền correlation ID thay cho dữ liệu người dùng trong trace context như thế nào?
Bạn sẽ phát hiện một service vô tình đưa access token vào span attribute thông qua instrumentation tự động ra sao?
Bạn sẽ cân nhắc việc ghi database query template thay cho câu SQL chứa tham số thực khi cần phân tích performance như thế nào?
Bạn sẽ phân loại trace liên kết nhiều bước giao dịch khi từng span riêng lẻ không chứa PII nhưng toàn bộ trace tiết lộ hành vi người dùng ra sao?
Bạn sẽ đánh giá nguy cơ liên kết logs và traces làm tăng khả năng tái nhận dạng dữ liệu đã được giả danh hóa như thế nào?
Bạn sẽ xác định khi nào phải tách quyền xem trace chi tiết khỏi quyền xem metric tổng hợp ra sao?
Bạn sẽ xác định thông tin nhạy cảm nào có thể xuất hiện trong CPU profile qua tên hàm, đường dẫn và metadata ra sao?
Bạn sẽ phân biệt rủi ro của CPU profile, heap profile và allocation profile khi dữ liệu bộ nhớ có thể chứa object nghiệp vụ như thế nào?
Bạn sẽ đánh giá nguy cơ heap dump hoặc memory snapshot làm lộ password, token và nội dung người dùng như thế nào?
Bạn sẽ xây dựng mức phân loại mặc định cho profile chưa được kiểm tra nội dung theo nguyên tắc thận trọng ra sao?
Bạn sẽ bảo vệ quá trình thu, tải xuống và chia sẻ profile khi cần hỗ trợ điều tra hiệu năng như thế nào?
Bạn sẽ xác định khi nào tên function hoặc package trong profile thuộc thông tin nội bộ cần hạn chế chia sẻ ra sao?
Bạn sẽ phân biệt thời gian lưu profiles với metrics tổng hợp dựa trên mức nhạy cảm và mục đích sử dụng như thế nào?
Bạn sẽ xây dựng danh mục phân loại chung để các hệ thống logs, metrics, traces và profiles không dùng tên mức nhạy cảm mâu thuẫn ra sao?
Bạn sẽ thiết kế nhãn classification cho telemetry mà không giả định mọi backend đều hỗ trợ cùng một cơ chế metadata như thế nào?
Bạn sẽ chọn nơi lưu metadata phân loại ở schema registry, policy catalog hay telemetry attributes theo yêu cầu nào?
Bạn sẽ xác định cách đánh dấu field chứa dữ liệu cá nhân và field chứa bí mật trong quy tắc schema như thế nào?
Bạn sẽ tổ chức mapping từ tên field khác nhau giữa các service về cùng nhóm dữ liệu nhạy cảm ra sao?
Bạn sẽ phân biệt classification theo mẫu trường, theo ngữ cảnh ứng dụng và theo kiểm tra giá trị thực tế như thế nào?
Bạn sẽ sử dụng quy tắc allowlist hoặc denylist trong pipeline và đánh giá điểm mạnh yếu của mỗi cách ra sao?
Bạn sẽ thiết kế chính sách mặc định khi một trường telemetry mới xuất hiện nhưng chưa được phân loại như thế nào?
Bạn sẽ xử lý trường có kiểu dữ liệu thay đổi hoặc chứa object lồng nhau mà chính sách lọc chưa nhận diện được ra sao?
Bạn sẽ duy trì version của taxonomy phân loại và quy tắc che dữ liệu qua nhiều phiên bản ứng dụng như thế nào?
Bạn sẽ xác định cách kiểm toán ai đã thay đổi nhãn phân loại hoặc cấp quyền truy cập cho một nhóm telemetry ra sao?
Bạn sẽ đánh giá tính nhất quán của phân loại khi một nguồn phát gửi cùng dữ liệu qua nhiều pipeline đến các đích khác nhau như thế nào?
Bạn sẽ mô tả các điểm kiểm soát dữ liệu từ SDK, agent, OpenTelemetry Collector đến exporter và backend như thế nào?
Bạn sẽ lựa chọn điểm kiểm soát sớm nhất để loại bỏ secrets trước khi dữ liệu được ghi xuống đĩa hoặc truyền qua mạng như thế nào?
Bạn sẽ lựa chọn attributes processor, transform processor hoặc filter processor trong OpenTelemetry Collector theo mục đích nào?
Bạn sẽ thiết kế bước lọc hoặc chuyển đổi trường nhạy cảm trong OpenTelemetry Collector mà vẫn giữ các attributes cần chẩn đoán như thế nào?
Bạn sẽ kiểm tra thứ tự các processor để tránh batch, log hoặc export dữ liệu gốc trước khi thực hiện redaction ra sao?
Bạn sẽ xác định giới hạn của việc chỉ lọc telemetry tại Collector khi ứng dụng đã ghi secrets vào file log cục bộ như thế nào?
Bạn sẽ phân biệt việc loại bỏ toàn bộ event có rủi ro với loại bỏ từng field để giữ tín hiệu vận hành ra sao?
Bạn sẽ xử lý sự kiện bị lỗi parse khiến quy tắc nhận diện PII không áp dụng được theo chính sách fail-safe như thế nào?
Bạn sẽ thiết kế quy tắc xử lý trường không được hỗ trợ hoặc không xác định mà không làm lộ dữ liệu theo nhánh fallback ra sao?
Bạn sẽ kiểm tra khả năng redaction cho các loại signal khác nhau theo phiên bản Collector và processor đang triển khai như thế nào?
Bạn sẽ tổ chức pipeline riêng cho telemetry có mức nhạy cảm cao và telemetry tổng hợp ít nhạy cảm ra sao?
Bạn sẽ lựa chọn Collector gateway hay Collector dạng agent để thực thi chính sách tại điểm phù hợp với ranh giới tin cậy như thế nào?
Bạn sẽ đánh giá nguy cơ các Collector trung gian lưu queue hoặc retry buffer chứa bản ghi chưa được che dữ liệu ra sao?
Bạn sẽ kiểm soát quyền truy cập file, volume và persistent queue nếu pipeline có khả năng lưu telemetry nhạy cảm trên đĩa như thế nào?
Bạn sẽ thiết kế cơ chế chuyển telemetry tới backend khác nhau theo mức phân loại mà không cho phép rẽ sang đích sai ra sao?
Bạn sẽ đảm bảo mọi exporter được cấu hình chỉ nhận bản telemetry đã qua chính sách kiểm soát phù hợp như thế nào?
Bạn sẽ xác định rủi ro khi bật logging exporter hoặc debug exporter trong Collector ở môi trường production ra sao?
Bạn sẽ bảo vệ dữ liệu OTLP khi truyền qua Collector bằng TLS, xác thực và kiểm soát nguồn gửi như thế nào?
Bạn sẽ lựa chọn mTLS hoặc cơ chế xác thực khác giữa collector và backend dựa trên ranh giới tin cậy ra sao?
Bạn sẽ kiểm soát cấu hình endpoint exporter và credential để tránh gửi telemetry sang tenant hoặc tài khoản nhầm như thế nào?
Bạn sẽ đánh giá trường hợp telemetry được chuyển qua một nhà cung cấp bên thứ ba theo yêu cầu hợp đồng và phân loại dữ liệu như thế nào?
Bạn sẽ thiết kế bước kiểm tra schema và phân loại trước khi một exporter mới được đưa vào production ra sao?
Bạn sẽ xác định cách giới hạn quyền sửa cấu hình Collector để một nhóm không thể vô hiệu hóa chính sách redaction ra sao?
Bạn sẽ phân biệt sampling traces với redaction PII và giải thích vì sao sampling không thay thế cơ chế bảo vệ ra sao?
Bạn sẽ kiểm tra nguy cơ telemetry nhạy cảm còn tồn tại trong queue, retry hoặc backup dù exporter chính đã ngừng gửi như thế nào?
Bạn sẽ xây dựng metric theo dõi số field bị che, event bị loại và lỗi thực thi chính sách trong Collector như thế nào?
Bạn sẽ thiết kế alert khi tỷ lệ redaction thất bại tăng bất thường mà không ghi lại giá trị nhạy cảm làm bằng chứng ra sao?
Bạn sẽ kiểm tra pipeline phát hiện PII để nó không vô tình tạo thêm bản sao dữ liệu nhạy cảm trong log hoặc báo cáo kiểm thử ra sao?
Bạn sẽ phân biệt mã hóa trên đường truyền, mã hóa lưu trữ và redaction nội dung theo nguy cơ mỗi biện pháp xử lý ra sao?
Bạn sẽ xây dựng mô hình quyền truy cập telemetry theo vai trò vận hành, phát triển, bảo mật và kiểm toán như thế nào?
Bạn sẽ xác định dữ liệu nào kỹ sư cần xem ở mức tổng hợp và dữ liệu nào chỉ nhóm được cấp quyền xem chi tiết ra sao?
Bạn sẽ thiết kế quyền truy cập theo môi trường, service, tenant và mức phân loại mà vẫn áp dụng nguyên tắc tối thiểu ra sao?
Bạn sẽ đánh giá rủi ro dashboard cho phép người dùng lọc quá chi tiết dẫn tới suy ra hành vi của cá nhân như thế nào?
Bạn sẽ phân biệt việc cho phép truy vấn log thô và cho phép xem dashboard đã tổng hợp về nguy cơ lộ dữ liệu ra sao?
Bạn sẽ kiểm soát quyền export, download, share link và API query của backend observability như thế nào?
Bạn sẽ xác định cách audit các lượt truy cập telemetry nhạy cảm và phát hiện truy vấn bất thường ra sao?
Bạn sẽ thiết kế quy trình cấp quyền khẩn cấp có giới hạn thời gian để điều tra sự cố production như thế nào?
Bạn sẽ quản lý quyền truy cập của tài khoản dịch vụ dùng cho dashboard, Collector và exporter theo nguyên tắc nào?
Bạn sẽ đánh giá nguy cơ dữ liệu nhạy cảm bị đưa vào công cụ tạo ticket hoặc chat qua chức năng chia sẻ log như thế nào?
Bạn sẽ thiết kế cơ chế xóa hoặc che giá trị nhạy cảm khi kỹ sư đính kèm dữ liệu điều tra vào báo cáo sự cố ra sao?
Bạn sẽ dựa trên yêu cầu data residency nào để quyết định phân tách nơi lưu telemetry theo vùng hoặc quốc gia?
Bạn sẽ xây dựng ma trận retention theo loại signal, mức phân loại, mục đích sử dụng và nhu cầu kiểm toán ra sao?
Bạn sẽ giải thích vì sao metrics tổng hợp có thể được giữ lâu hơn log chi tiết trong một chính sách lưu giữ phù hợp như thế nào?
Bạn sẽ thiết kế vòng đời xóa log chứa PII khác với log hạ tầng không chứa dữ liệu nhận dạng ra sao?
Bạn sẽ xác định cách thực thi yêu cầu xóa dữ liệu liên quan đến một cá nhân trong các hệ thống telemetry có index và backup ra sao?
Bạn sẽ kiểm tra sự khác nhau giữa xóa quyền truy cập dữ liệu và xóa bản sao dữ liệu khỏi nơi lưu trữ như thế nào?
Bạn sẽ đánh giá tác động của snapshot, replica và long-term storage tới khả năng thực hiện chính sách retention ra sao?
Bạn sẽ thiết kế quy trình giữ bằng chứng phục vụ điều tra theo ngoại lệ có phê duyệt thay vì kéo dài retention cho toàn bộ dữ liệu ra sao?
Bạn sẽ kiểm soát việc chuyển dữ liệu từ backend giám sát sang kho phân tích dữ liệu để tránh sử dụng ngoài mục đích ra sao?
Bạn sẽ xác định cách đánh giá nhà cung cấp backend telemetry về bảo mật, quyền truy cập và chính sách xóa dữ liệu như thế nào?
Bạn sẽ lựa chọn mức độ tổng hợp dữ liệu trước khi chia sẻ cho bên ngoài tổ chức dựa trên nguy cơ tái nhận dạng ra sao?
Bạn sẽ phân loại telemetry kết hợp từ nhiều tenant khi một dashboard hiển thị metric liên khách hàng như thế nào?
Bạn sẽ thiết kế bộ dữ liệu kiểm thử nhân tạo chứa email, token giả và định danh giả để kiểm chứng quy tắc redaction ra sao?
Bạn sẽ kiểm thử quy tắc lọc PII trên URL, header, body, log message và span attributes với những trường hợp biên nào?
Bạn sẽ xác định cách kiểm tra redaction trong một event có field lồng nhau, mảng và giá trị mã hóa khác thường như thế nào?
Bạn sẽ xây dựng kiểm thử hồi quy để bảo đảm pipeline mới không vô tình khôi phục trường nhạy cảm đã từng bị loại ra sao?
Bạn sẽ kiểm tra rằng metric labels không nhận giá trị động có chứa email hoặc user ID bằng phép thử nào?
Bạn sẽ đo tỷ lệ false positive và false negative của quy tắc phát hiện dữ liệu nhạy cảm trên bộ mẫu kiểm thử như thế nào?
Bạn sẽ xác định tín hiệu vận hành quan trọng nào bị mất sau khi redaction và cách bổ sung phép đo thay thế ra sao?
Bạn sẽ kiểm thử hiệu năng Collector khi bật transform, redaction và filter processors dưới tải telemetry cao như thế nào?
Bạn sẽ thiết kế canary deployment cho thay đổi chính sách dữ liệu telemetry trước khi áp dụng trên toàn hệ thống ra sao?
Bạn sẽ kiểm tra cấu hình Collector trước khi triển khai và so sánh đường đi dữ liệu thực tế với kiến trúc đã phê duyệt như thế nào?
Bạn sẽ xây dựng quy trình review thay đổi taxonomy, processor, exporter và retention theo mức rủi ro nào?
Bạn sẽ thiết kế dashboard tuân thủ theo số nguồn telemetry chưa được phân loại, quy tắc lỗi và quyền ngoại lệ ra sao?
Bạn sẽ xác định cách phát hiện một thư viện instrumentation mới tự động phát sinh attribute chứa thông tin nhạy cảm như thế nào?
Bạn sẽ phân biệt nguyên nhân telemetry bị thiếu do chính sách lọc với nguyên nhân pipeline mất dữ liệu vì lỗi mạng ra sao?
Bạn sẽ kiểm tra nguyên nhân một trace không còn đủ span sau khi bật filter nhưng log vẫn đầy đủ như thế nào?
Bạn sẽ lập kế hoạch rollback chính sách lọc khi làm hỏng khả năng giám sát mà không cho phép dữ liệu nhạy cảm phát tán trở lại ra sao?
Bạn sẽ xác định các bước ứng phó khi phát hiện access token đã đi qua Collector và được lưu trong backend telemetry như thế nào?
Bạn sẽ truy vết phạm vi phơi lộ secrets từ ứng dụng, collector, queue, exporter, backend đến bản sao dự phòng ra sao?
Bạn sẽ phối hợp thu hồi credential, khóa truy cập và rà soát audit log sau sự cố rò rỉ telemetry như thế nào?
Bạn sẽ đánh giá liệu việc xóa document khỏi backend đã đủ xử lý sự cố khi dữ liệu còn trong snapshot hoặc dashboard cache hay không?
Bạn sẽ xây dựng báo cáo sự cố rò rỉ telemetry có timeline, nguyên nhân gốc, phạm vi ảnh hưởng và biện pháp phòng ngừa ra sao?
Nếu span HTTP ghi toàn bộ Authorization header, bạn sẽ sửa instrumentation và chính sách Collector theo thứ tự nào để giảm rủi ro?
Nếu một metrics exporter tạo series theo email người dùng, bạn sẽ xử lý cardinality và rò rỉ dữ liệu đã lưu như thế nào?
Nếu trace không chứa tên người dùng nhưng có transaction ID liên kết với log chứa email, bạn sẽ đánh giá lại mức phân loại ra sao?
Nếu một Pod ghi stack trace có token ra stdout trước khi Elastic Agent hoặc OTel Collector che dữ liệu, bạn sẽ xác định các bản sao còn tồn tại như thế nào?
Nếu dashboard cross-tenant cho phép lọc tới một khách hàng duy nhất, bạn sẽ kiểm tra nguy cơ tiết lộ thông tin và sửa quyền truy cập ra sao?
Nếu một thay đổi OpenTelemetry Collector làm mất field chẩn đoán lỗi mà vẫn giữ được PII, bạn sẽ kiểm chứng và khôi phục chính sách an toàn như thế nào?
Nếu đội vận hành cần giữ traces lâu hơn để điều tra một sự cố nhưng chính sách retention sắp xóa, bạn sẽ xử lý ngoại lệ có kiểm toán như thế nào?
Nếu phát hiện cấu hình debug exporter đang gửi telemetry thô sang môi trường thử nghiệm, bạn sẽ ngăn phát tán và xác minh dữ liệu bị ảnh hưởng ra sao?
Bạn sẽ thiết kế chương trình quản trị phân loại telemetry cho nền tảng microservices với logs, metrics, traces, profiles, OpenTelemetry Collector, quyền truy cập và retention như thế nào?

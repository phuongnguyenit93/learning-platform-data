Một API đăng nhập Spring Boot ghi toàn bộ Authorization header khi xác thực thất bại; bearer token còn hiệu lực xuất hiện trong log tập trung dù thông điệp nghiệp vụ chỉ cần mã lỗi và loại xác thực.
Gateway ghi access log với toàn bộ query string; URL đặt lại mật khẩu chứa token dùng một lần nên token được sao chép vào nhiều hệ thống tìm kiếm và lưu trữ.
Ứng dụng ghi Cookie header để điều tra lỗi phiên đăng nhập; session ID có thể tái sử dụng vẫn còn nguyên trong log sau khi người dùng đã đăng xuất.
Một dịch vụ OAuth ghi request và response của token endpoint ở mức DEBUG; access token, refresh token và client secret xuất hiện trong cùng một bản ghi.
SDK thanh toán trả exception có chứa API key trong thông báo lỗi; ứng dụng ghi nguyên exception stack trace khiến thông tin xác thực bị lưu dù request body đã được che.
Ứng dụng ghi nguyên JSON payload khi validation thất bại; nested object chứa password, câu trả lời bảo mật và thông tin cá nhân mà đội hỗ trợ không cần để xác định trường sai.
Một logger ghi đối tượng JPA bằng toString(); phương thức này tự đưa email, số điện thoại và địa chỉ vào log khi phát sinh lỗi cập nhật hồ sơ.
Nhóm bật Hibernate SQL và bind parameter logging để tìm truy vấn chậm; giá trị tham số có số tài khoản và mã định danh cá nhân được ghi cùng câu SQL.
HTTP client interceptor ghi toàn bộ request và response để debug tích hợp; response từ đối tác đôi khi chứa dữ liệu khách hàng và token phiên trong header tùy chỉnh.
Một dịch vụ ghi URL đầy đủ vào span attribute http.url; tham số tìm kiếm chứa email và access token khiến dữ liệu nhạy cảm xuất hiện trong kho tracing.
Ứng dụng gắn request body vào span event khi lỗi 500; payload thanh toán có số thẻ và địa chỉ thanh toán được xuất qua OTLP tới Collector dùng chung.
Nhóm thêm toàn bộ baggage của request vào span con; baggage chứa email và tenant identifier được truyền qua nhiều dịch vụ không có nhu cầu xử lý các trường này.
Trace của một workflow có span attributes chứa Authorization header đã được sao chép từ context; token xuất hiện trong nhiều span dù chỉ một service thực hiện xác thực.
Ứng dụng ghi SQL statement có literal parameter vào span database; nội dung truy vấn chứa email khách hàng và mã giao dịch dù đội điều tra chỉ cần loại thao tác và tên bảng.
Một service gắn customer_id vào metric label để tìm lỗi theo khách; nhãn có giá trị riêng cho từng người làm lộ định danh và tăng cardinality của time series.
Counter lỗi SMS dùng phone_number làm label; danh sách số điện thoại xuất hiện trong API labels và dashboard ngay cả khi người xem không có quyền truy vấn log.
Metric HTTP tạo label từ URL thực tế gồm order_id; redaction ở log pipeline không áp dụng cho metrics exporter nên mã đơn vẫn được lưu dưới dạng nhãn.
Ứng dụng đưa exception message chứa tên khách hàng vào label error_type; mỗi lỗi tạo một chuỗi khác nhau và dữ liệu cá nhân đi vào kho metrics.
Exporter tự động gắn user.id vào mọi metric JVM; một tiến trình phục vụ nhiều người dùng khiến metric tài nguyên chứa định danh request không cần thiết.
Metric histogram có exemplar liên kết tới trace; label đã được làm sạch nhưng trace đích vẫn chứa request payload và thông tin định danh nguyên bản.
Ứng dụng Java ghi thông tin người dùng vào MDC; log pattern xuất MDC đầy đủ nên các trường như email và account number được thêm vào mọi dòng log của request.
Nhóm chỉ che trường password trong JSON nhưng ứng dụng có nested field credentials.password; các log từ nhánh đăng nhập phụ vẫn chứa mật khẩu rõ.
API dùng tên trường accessToken ở phiên bản mới thay cho authorization_token; bộ lọc chỉ nhận diện tên cũ nên dữ liệu token mới lọt vào kho.
Một service dùng camelCase, service khác dùng snake_case cho cùng trường số tài khoản; quy tắc redaction dựa trên một cách viết khiến một phần log không được xử lý.
Log message chứa email ở dạng văn bản tự do thay vì trường JSON; processor chỉ kiểm tra structured attributes nên PII trong message vẫn còn nguyên.
Thông báo lỗi được tạo bằng cách nối URL vào chuỗi văn bản; token trong query parameter không còn tách thành trường riêng để bộ lọc hiện tại nhận diện.
Một ứng dụng ghi số thẻ có dấu cách và dấu gạch ngang; pattern phát hiện chuỗi chữ số liên tiếp không nhận diện biến thể định dạng này.
Thông tin tài khoản được chia thành nhiều trường như bank_code và account_suffix; từng trường riêng không bị đánh dấu nhạy cảm nhưng kết hợp lại có thể nhận diện tài khoản cụ thể.
Log hỗ trợ có trường customer_name được che nhưng vẫn giữ ngày sinh đầy đủ và mã bưu chính; các thuộc tính kết hợp có thể xác định một người trong nhóm dân số nhỏ.
Một ứng dụng ghi địa chỉ IP IPv6 đầy đủ vào log; quy tắc chỉ che IPv4 nên thông tin thiết bị và mạng của người dùng vẫn được giữ.
Dịch vụ IoT ghi tọa độ GPS chính xác vào span event; nhóm vận hành chỉ cần biết vùng lỗi nhưng trace lưu hành trình chi tiết của thiết bị.
Hệ thống y tế ghi nội dung exception có chẩn đoán và mã hồ sơ bệnh nhân; pipeline che tên trường patient_name nhưng phần mô tả tự do vẫn chứa thông tin sức khỏe.
Ứng dụng HR ghi object nhân viên khi lỗi đồng bộ bảng lương; trường lương, mã nhân viên và tài khoản ngân hàng bị đưa vào log dù chỉ cần biết mã lỗi đồng bộ.
Log hỗ trợ khách hàng chứa nội dung chat tự do; người dùng thường tự nhập email, số điện thoại và thông tin định danh nên việc lọc theo tên trường không đủ.
Một dịch vụ ghi tên tệp do người dùng tải lên; tên file có thể chứa số hồ sơ hoặc họ tên nhưng pipeline chỉ kiểm tra nội dung tệp, không kiểm tra metadata.
Ứng dụng upload multipart ghi toàn bộ header và boundary; tên tệp, content-disposition và metadata biểu mẫu chứa thông tin cá nhân được lưu cùng access log.
Nhóm dùng regex che token có tiền tố cố định nhưng nhà cung cấp đổi định dạng API key; credential mới không còn khớp pattern cũ và được ghi nguyên.
Secret được URL-encode trước khi xuất hiện trong log; bộ phát hiện chỉ tìm chuỗi ký tự gốc nên không nhận ra dạng mã hóa phần trăm.
Token xuất hiện dưới dạng Base64 trong payload debug; quy tắc redaction văn bản không giải mã nội dung nên giá trị nhạy cảm vẫn tồn tại.
Một ứng dụng ghi nội dung JSON đã nén và mã hóa ở dạng chuỗi debug; pipeline không thể phân tích cấu trúc nhưng vẫn chuyển nguyên blob sang kho lưu trữ.
Log gRPC ghi metadata headers nhưng không xử lý trường binary metadata; một credential được mã hóa trong metadata nhị phân thoát khỏi quy tắc lọc header văn bản.
Dữ liệu nhạy cảm nằm trong protobuf Any payload; parser chỉ giải mã các message đã biết nên loại message mới được ghi nguyên dạng khi không thể parse.
Ứng dụng log một object chứa byte array bằng biểu diễn hex; secret không còn khớp regex token thông thường nhưng có thể khôi phục từ chuỗi hex.
Một trường chứa nhiều giá trị được phân tách bằng dấu phẩy; bộ lọc chỉ che giá trị đầu tiên nên token thứ hai vẫn xuất hiện trong log.
Thông tin xác thực bị chia qua hai trường trước khi được nối ở bước transform; redaction chạy trước bước nối nên chuỗi cuối cùng chứa secret không được che.
Collector parse log thành JSON rồi che trường password, nhưng exporter debug ghi lại event gốc trước processor; bản sao chưa làm sạch vẫn xuất hiện trong log nội bộ của Collector.
Một pipeline OpenTelemetry Collector áp dụng transform cho logs nhưng pipeline traces không dùng cùng quy tắc; PII đã biến mất khỏi log song vẫn có trong span attributes.
Collector có hai exporter gửi dữ liệu tới kho chính và kho phân tích; bộ lọc chỉ được gắn trên nhánh chính nên nhánh phụ vẫn lưu dữ liệu nguyên bản.
Nhóm triển khai redaction ở Collector gateway nhưng một số ứng dụng gửi trực tiếp tới backend lưu trữ qua endpoint cũ; đường đi bỏ qua chính sách trung tâm.
Agent tại node lọc log trước khi gửi nhưng một ứng dụng dùng exporter OTLP riêng; telemetry từ exporter này không đi qua agent và không được che.
Nhóm áp dụng processor xóa trường sensitive ở pipeline logs nhưng quên pipeline metrics và traces; dashboard metrics vẫn hiển thị định danh bị loại khỏi log.
Redaction processor được đặt sau batch và queue; dữ liệu gốc nằm trong bộ đệm trung gian lâu hơn chính sách cho phép trước khi được làm sạch.
Một Collector retry gửi dữ liệu sau khi backend tạm ngừng; hàng đợi persistent giữ bản ghi chưa redacted từ phiên bản cấu hình cũ và gửi lại sau khi pipeline mới hoạt động.
Nhóm nâng cấp Collector và đổi tên processor; cấu hình redaction không còn được nạp nhưng service vẫn khởi động do nhánh pipeline khác hợp lệ.
Một Collector chạy DaemonSet đã được cập nhật quy tắc nhưng một replica ở node cô lập không nhận cấu hình mới; một phần log production tiếp tục chứa PII.
Gateway nhận OTLP từ nhiều tenant nhưng chỉ có một policy redaction chung; trường nhạy cảm riêng của tenant tài chính không được xử lý vì schema của họ khác các tenant khác.
Ứng dụng thêm trường mới chứa refresh token trong bản phát hành; allowlist redaction ở Collector chưa cập nhật và trường mới được chuyển tiếp nguyên vẹn.
Nhóm dùng denylist tên trường để che dữ liệu; một vendor library bổ sung thuộc tính credential_value mà không có trong danh sách và secret bị lưu.
Pipeline đổi tên field trước redaction; chính sách chỉ tìm tên cũ nên thuộc tính đã đổi tên thoát khỏi bước che.
Collector làm giàu event bằng metadata từ Kubernetes sau khi redaction; metadata mới chứa annotation nhạy cảm và không được lọc trước khi export.
Processor xóa trường nhạy cảm nhưng không xóa bản sao trong event.original; người dùng có thể truy xuất giá trị gốc bằng API tìm kiếm.
Nhóm che nội dung message hiển thị trên Kibana nhưng giữ nguyên raw_message trong index; người dùng có quyền truy vấn trực tiếp đọc được dữ liệu nhạy cảm.
Ứng dụng ghi log đã được redaction tại source nhưng sidecar proxy ghi access log riêng có query string đầy đủ; nhóm bảo mật chỉ kiểm tra log ứng dụng và bỏ sót bản sao.
Service mesh tạo access log với header và URL trong khi application logger đã che; cùng request để lại dữ liệu nhạy cảm ở lớp proxy.
Gateway Nginx ghi request URI trước khi chuyển tới ứng dụng; ứng dụng redaction thành công nhưng token trong query string vẫn có mặt ở access log của gateway.
Logstash mutate filter che trường authorization nhưng pipeline Elasticsearch ingest cũng lưu event.original; truy vấn raw document vẫn trả lại token.
Một bộ lọc regex thay toàn bộ chuỗi giống số thẻ bằng [REDACTED], nhưng vô tình che cả mã lỗi và số phiên bản cần để xác định loại lỗi.
Redaction xóa toàn bộ URL để loại token query; đội trực mất route template và không phân biệt được lỗi ở endpoint đăng nhập với endpoint thanh toán.
Nhóm che toàn bộ exception message để tránh PII; thông tin SQLState, error code và loại exception cũng biến mất khiến việc phân loại lỗi database khó hơn.
Ứng dụng thay mọi giá trị account_id bằng chuỗi cố định [MASKED]; nhóm điều tra không thể biết nhiều sự kiện thuộc cùng một tài khoản hay các tài khoản khác nhau.
Đội dùng hash không khóa cho email để giữ khả năng đối chiếu; giá trị phổ biến có thể bị dò ngược bằng từ điển và vẫn tạo định danh ổn định xuyên hệ thống.
Nhóm dùng HMAC với một khóa chung để giả danh customer_id; khóa bị lộ ở môi trường staging khiến các định danh đã tạo ở production có thể bị liên kết.
Một ứng dụng thay email bằng token giả danh nhưng mỗi service dùng salt khác nhau; cùng người dùng có mã khác nhau giữa log gateway và log backend nên correlation bị đứt.
Đội che một phần số điện thoại bằng dấu sao nhưng vẫn giữ bốn số cuối; trong tenant nhỏ, kết hợp thời điểm và địa điểm vẫn đủ để nhận diện người dùng.
Nhóm giữ ngày sinh theo ngày/tháng/năm để phân tích sự cố; yêu cầu vận hành chỉ cần nhóm tuổi nhưng dữ liệu chính xác vẫn được xuất trong log.
Redaction thay tên người bằng mã ngẫu nhiên mới ở từng log event; dữ liệu giảm nhạy cảm nhưng không còn khả năng liên kết các bước của một phiên sự cố.
Ứng dụng giữ trace_id để nối các dịch vụ nhưng bộ lọc coi mọi UUID là định danh cá nhân và xóa chúng; log và trace không còn liên kết được.
Nhóm giữ user_id giả danh nhưng không có kiểm soát truy cập cho bảng ánh xạ; nhân viên hỗ trợ có thể khôi phục danh tính người dùng từ kho phụ.
Một API nhận Authorization header và cần biết loại scheme để chẩn đoán lỗi; chính sách xóa toàn bộ header làm mất dấu hiệu phân biệt Bearer, Basic và lỗi định dạng.
Nhóm muốn che token nhưng giữ phần tiền tố để phân loại nhà cung cấp; regex thay toàn bộ header khiến đội vận hành không biết lỗi thuộc hệ thống OAuth nào.
Redaction xóa toàn bộ db.statement để tránh lộ bind values; đội database mất tên bảng và loại thao tác cần thiết để phân tích truy vấn chậm.
Ứng dụng che mọi giá trị trong SQL nhưng cũng xóa tên cột và dấu hiệu JOIN; trace không còn đủ thông tin để nhận diện truy vấn gây lock.
Một log HTTP được làm sạch body nhưng không giữ status code và content length; sau redaction, nhóm không thể phân biệt lỗi payload lớn với lỗi xác thực.
Nhóm xóa địa chỉ IP khỏi mọi access log; đội mạng không thể xác định request lỗi tập trung ở một proxy hoặc một vùng nguồn cụ thể.
Ứng dụng chỉ giữ subnet đã rút gọn thay cho IP đầy đủ nhưng không ghi rõ cách rút gọn; dashboard địa lý và log security không thể so sánh nhất quán.
Redaction loại bỏ hostname và pod name vì cho rằng đó là metadata nhạy cảm; nhóm vận hành không thể khoanh vùng instance lỗi khi một replica bị cấu hình sai.
Nhóm che tên database trong connection string nhưng xóa luôn db.system và db.operation khỏi span; trace không phân biệt được PostgreSQL với Redis.
Ứng dụng che nội dung message nhưng giữ error.type, error.code và route template; đội bảo mật cần xác minh rằng các trường còn lại đủ chẩn đoán mà không tiết lộ payload.
Một bộ lọc thay các giá trị nhạy cảm bằng chuỗi rỗng; parser downstream hiểu trường rỗng là dữ liệu hợp lệ và dashboard thống kê số người dùng thiếu chính xác.
Redaction thay chuỗi bí mật bằng giá trị có độ dài khác biệt; log chứa kích thước đã thay đổi làm sai phép đo payload length trong một số dashboard.
Nhóm che trường password nhưng không loại bỏ trường xác nhận password; hai giá trị còn lại có thể được so sánh và tiết lộ mật khẩu mà người dùng nhập.
Một bản ghi có token ở trường nested array gồm nhiều thiết bị; processor chỉ duyệt object cấp đầu nên các phần tử trong mảng vẫn giữ credential.
Log chứa nhiều JSON object nối tiếp trong cùng message; parser chỉ đọc object đầu tiên và không phát hiện token trong object thứ hai.
Một ứng dụng ghi dữ liệu XML trong message; quy tắc redaction chỉ parse JSON và không che các thẻ chứa thông tin cá nhân.
Log được escape ký tự xuống dòng và dấu nháy; bộ lọc tìm PII chạy trước bước unescape nên không nhận ra giá trị bị chia bởi escape sequence.
Secret xuất hiện qua Unicode homoglyph hoặc ký tự zero-width trong chuỗi; regex phát hiện token không chuẩn hóa văn bản nên bỏ sót giá trị có thể sử dụng.
Ứng dụng ghi số thẻ dưới dạng chữ số Unicode; bộ lọc chỉ nhận chữ số ASCII và không phát hiện dữ liệu nhạy cảm trong bản ghi.
Một trường email được chia thành nhiều mảnh ở các log event khác nhau; từng bản ghi riêng không khớp pattern nhưng chuỗi ghép theo session có thể tái tạo địa chỉ.
Nhóm dùng regex để phát hiện private key PEM nhưng log chỉ chứa phần nội dung key đã bỏ dòng BEGIN/END; pattern hiện tại không nhận ra khóa bị cắt.
Một ứng dụng vô tình ghi file cấu hình có chứa private key vào log khi khởi động; quy tắc chỉ tìm chuỗi PEM đầy đủ nên không phát hiện dạng một dòng đã escape.
Cloud access key có tiền tố mới được nhà cung cấp phát hành; bộ quét secret chưa cập nhật pattern nên các key mới bị ghi vào log deploy.
Log CI/CD chứa lệnh shell với biến môi trường được mở rộng; secret xuất hiện ở command line dù ứng dụng không ghi credential trực tiếp.
Một service ghi exception từ thư viện kết nối database, trong đó connection string bao gồm username và password; redaction chỉ áp cho request log chứ không áp cho log khởi tạo kết nối.
Ứng dụng ghi URL signed download có chữ ký và thời hạn truy cập; bộ lọc xóa query parameter phổ biến nhưng bỏ sót chữ ký có tên vendor-specific.
Webhook callback URL chứa secret path segment thay vì query parameter; redaction chỉ kiểm tra query và header nên URL đầy đủ vẫn được lưu.
Một hệ thống lưu mã OTP trong span event để điều tra lỗi xác thực; OTP có thời hạn ngắn nhưng vẫn có thể được sử dụng trong thời gian log được truy vấn.
Log audit ghi câu hỏi và câu trả lời xác minh danh tính; đội vận hành chỉ cần kết quả pass/fail nhưng nội dung xác minh vẫn được giữ.
Ứng dụng ghi địa chỉ IP và user-agent đầy đủ; nhóm muốn giảm khả năng nhận diện nhưng vẫn cần phân biệt bot, browser và loại client để điều tra lỗi tương thích.
Redaction làm sạch email nhưng giữ tên miền và phần local-part đã che không đồng nhất; một số địa chỉ nội bộ vẫn có thể nhận diện phòng ban và người dùng.
Một dashboard hiển thị dữ liệu đã che nhưng tính năng CSV export trả các trường gốc; kiểm tra giao diện bằng mắt không phát hiện lỗ hổng ở đường xuất dữ liệu.
API truy vấn trace áp redaction khi trả response cho dashboard, nhưng endpoint export archive trả tài liệu gốc; cùng một quyền đọc có thể lấy dữ liệu chưa làm sạch.
Collector gửi dữ liệu đã redacted tới Elasticsearch nhưng đồng thời ghi event thô vào dead-letter queue khi lỗi parse; người quản trị đọc queue có thể thấy secret nguyên bản.
Pipeline redaction thất bại khi regex timeout; cấu hình hiện chuyển tiếp event gốc để tránh mất log, khiến dữ liệu nhạy cảm lọt qua trong điều kiện tải cao.
Một processor không xử lý được loại log mới và ghi warning rồi bỏ qua redaction; hệ thống vẫn báo ingest thành công nên không ai phát hiện dữ liệu thô đã được lưu.
Đội chọn fail-closed khi redaction lỗi và loại bỏ toàn bộ event; trong một đợt lỗi parser, audit log quan trọng cũng bị mất khiến việc điều tra bảo mật không đầy đủ.
Nhóm chọn fail-open để bảo toàn telemetry khi bộ lọc gặp sự cố; token và PII được gửi nguyên vẹn trong vài giờ trước khi có người khắc phục.
Một Collector nhận batch chứa cả event hợp lệ và event có PII; processor loại cả batch khi phát hiện một event không hợp lệ, làm mất nhiều tín hiệu chẩn đoán không nhạy cảm.
Redaction được thực hiện sau bước sampling; các span không được chọn vẫn tồn tại trong buffer trung gian chưa làm sạch và có thể bị ghi ra debug log khi exporter lỗi.
Sampling được quyết định dựa trên thuộc tính user_id trước khi redaction; giá trị định danh vẫn được dùng trong metadata của quyết định và có thể xuất hiện trong log nội bộ.
Nhóm tăng tỷ lệ lấy mẫu trace khi có lỗi 500; lỗi hiếm có payload chứa secret được giữ lại nhiều hơn bình thường và mức phơi lộ tăng đúng lúc điều tra.
Policy redaction mới chỉ áp dụng cho dữ liệu đi vào, không xử lý log lịch sử đã nằm trong snapshot; sau khi phát hiện secret, các bản sao cũ vẫn còn truy cập được.
Đội xóa index chứa log nhạy cảm nhưng bản sao vẫn tồn tại trong snapshot, searchable archive và bản export của nhóm hỗ trợ; quy trình xử lý sự cố dữ liệu chưa bao phủ các bản sao.
Một queue bền vững trên node giữ event chưa che qua lần restart; Collector mới có redaction policy nhưng dữ liệu cũ được replay từ queue theo pipeline cũ.
Ứng dụng đã redacted trước khi ghi file nhưng agent backup thư mục log thô cũ vẫn tiếp tục gửi dữ liệu tới kho thứ hai; đường thu thập dự phòng chưa áp chính sách mới.
Nhóm cập nhật regex redaction trong production nhưng chỉ một số Collector replica được reload; dữ liệu đi qua các replica khác nhau có mức làm sạch không đồng nhất.
Policy redaction được triển khai bằng GitOps nhưng một hotfix thủ công ở Collector bị ghi đè sau sync; nhóm không có metric cho biết phiên bản policy đang chạy ở từng replica.
Nhóm lưu version của redaction policy trong metadata nhưng không ghi vào audit log; khi phát hiện PII, không xác định được bản ghi nào đã đi qua phiên bản quy tắc nào.
Một vendor integration đổi schema mà không thông báo; field nhạy cảm mới được phát hành vào production và không có kiểm thử hợp đồng schema để chặn.
Đội bảo mật có danh sách từ khóa nhạy cảm bằng tiếng Anh nhưng ứng dụng ghi tên trường tiếng Việt và viết tắt nội bộ; bộ quét không nhận diện các biến thể.
Ứng dụng hỗ trợ nhiều locale, số định danh có dấu phân cách khác nhau; quy tắc phát hiện chỉ được thử với dữ liệu Việt Nam chuẩn nên bỏ sót định dạng quốc tế.
Một thư viện mới chuyển thông tin nhạy cảm từ header sang cookie; test redaction chỉ kiểm tra header và không phát hiện đường dữ liệu mới.
Nhóm kiểm thử redaction bằng vài giá trị giả cố định; dữ liệu thật có Unicode, escape, nested arrays và ký tự phân tách khác nên nhiều trường hợp lọt qua.
Một unit test xác nhận hàm mask email hoạt động nhưng không kiểm tra logger thực tế, appender, agent và Collector; production vẫn ghi email nguyên bản qua một nhánh khác.
Đội viết test kiểm tra log đã che bằng cách so sánh chuỗi chứa [REDACTED]; test không quét các trường khác trong cùng event nên token vẫn tồn tại ở raw body.
Pipeline có kiểm thử positive cho email và password nhưng không có negative test để đảm bảo route, error code và trace_id còn nguyên sau khi redaction.
Một thay đổi regex che số điện thoại thành công nhưng làm mất phần cuối của mã giao dịch có cùng định dạng; bộ test không xác minh trường chẩn đoán được bảo toàn.
Nhóm chạy canary secret qua ứng dụng và Collector rồi chỉ kiểm tra Elasticsearch index chính; secret vẫn xuất hiện trong debug logs, dead-letter queue và exporter phụ.
Đội kiểm thử chỉ xác minh dữ liệu ở một service; request qua gateway, worker Kafka và scheduled job dùng các logger khác nhau nên một số đường đi chưa được kiểm tra.
Một ứng dụng Spring Boot thay đổi cấu hình Logback theo profile production; test chạy profile test nên không phát hiện appender production ghi raw request body.
Collector pipeline có processor redaction nhưng config test chỉ khởi động receiver và kiểm tra endpoint health; không có event mẫu để xác minh dữ liệu đầu ra đã được làm sạch.
Nhóm dùng synthetic data để đo tỷ lệ phát hiện PII; dữ liệu tổng hợp không mô phỏng secret có khoảng trắng, prefix mới hoặc chuỗi bị chia nên kết quả đánh giá quá lạc quan.
Đội an ninh kiểm tra bằng cách tìm token canary trong kho log sau ingest; họ không kiểm tra metric labels, trace attributes, exemplars và metadata nên một số bản sao không được phát hiện.
Một chính sách redaction thay đổi từ xóa hoàn toàn sang tokenization; nhóm chỉ so sánh dung lượng log mà không đo khả năng liên kết các sự kiện cùng người dùng trong cuộc điều tra.
Nhóm đánh giá chất lượng sau redaction bằng số lượng trường còn lại; không có bài tập điều tra mẫu để xác nhận mã lỗi, route, service, thời gian và correlation ID vẫn đủ dùng.
Trong diễn tập incident, đội trực không thể xác định service gây lỗi vì redaction đã xóa service.name và deployment version cùng với các trường nhạy cảm.
Một lỗi database chỉ có thể phân biệt theo SQLState và tên operation; policy mới xóa toàn bộ exception detail khiến đội trực không xác định được lỗi deadlock hay vi phạm constraint.
Nhóm che toàn bộ URL path để tránh lộ mã khách hàng; route template cũng biến mất nên các lỗi theo endpoint không thể tổng hợp trên dashboard.
Ứng dụng loại bỏ toàn bộ header để tránh secret; thông tin content-type và request method cần cho chẩn đoán lỗi giao thức cũng không còn.
Redaction thay các trường nhạy cảm bằng giá trị cùng kiểu nhưng không ghi rõ trạng thái đã che; người phân tích nhầm [REDACTED] là giá trị người dùng thật và thống kê sai.
Nhóm thay dữ liệu nhạy cảm bằng token ổn định nhưng không ghi phiên bản thuật toán hoặc key ID; sau khi xoay khóa, cùng một người dùng có nhiều mã giả danh không thể đối chiếu.
Đội dùng mã giả danh có thể giải ngược trong dịch vụ riêng; quyền truy cập kho ánh xạ quá rộng khiến redaction không giảm được nguy cơ khi tài khoản vận hành bị lộ.
Một log có trường account_number được che một phần nhưng trường display_name chứa cả số tài khoản; policy chỉ xét schema chính và bỏ sót bản sao trong phần hiển thị.
Ứng dụng ghi object lỗi với cả trường public_message và internal_message; redaction che thông tin ở public_message nhưng internal_message vẫn chứa token và stack context nhạy cảm.
Nhóm xóa trường request.body khỏi logs nhưng hệ thống audit ghi cùng nội dung vào event.payload; hai loại sự kiện được lưu ở hai index và chỉ một index được kiểm tra.
Trong một trace, span đầu đã được redacted nhưng span con từ thư viện bên thứ ba chứa dữ liệu gốc; nhóm chỉ kiểm tra span server và bỏ qua client span.
Metric label được chuẩn hóa thành error_family nhưng exemplars và annotation dashboard vẫn giữ giá trị nguyên gốc từ exception; dữ liệu nhạy cảm còn ở đường liên kết.
Đội dùng một redaction policy chung cho tất cả dịch vụ; trường customer_ref là dữ liệu nội bộ không nhạy cảm ở hệ thống A nhưng là định danh cá nhân ở hệ thống B, dẫn tới xử lý không phù hợp theo ngữ cảnh.
Một chính sách cho phép giữ 4 ký tự cuối của mọi mã định danh; với mã ngắn hoặc nhóm người dùng ít, phần còn lại vẫn đủ để nhận diện đối tượng.
Ứng dụng log giá trị thời gian chính xác và vị trí chính xác; từng trường không phải tên hay email nhưng tổ hợp hiếm có thể tái nhận diện hành vi của cá nhân.
Nhóm redaction log nhưng không xử lý thông tin trong tên metric và label values; secret được dùng nhầm làm label xuất hiện trong metadata của time series.
Collector che secret trong nội dung log nhưng log nội bộ của processor ghi giá trị đầu vào khi phát hiện lỗi cấu hình; chính thành phần bảo vệ lại tạo bản sao nhạy cảm.
Đội bật tracing debug cho exporter để tìm lỗi gửi OTLP; debug output in toàn bộ span attributes trước bước redaction nên dữ liệu được ghi vào tệp trên node.
Ứng dụng có log rotation và agent đọc lại file cũ; redaction mới chỉ áp dụng cho dòng phát sinh sau triển khai, còn các tệp chưa đọc tiếp tục chứa dữ liệu thô.
Một pipeline redaction loại bỏ PII nhưng không đánh dấu loại trường đã xử lý; hệ thống downstream chạy thêm processor thứ hai và che nhầm correlation ID đã được pseudonymize.
Nhóm phát hiện token trong log đã lưu và chạy tác vụ xóa theo chuỗi khớp; truy vấn xóa quá rộng làm mất cả các bản ghi đã được redacted và cần giữ cho kiểm toán.
Đội vận hành cần chứng minh quy tắc redaction đã chạy trước khi dữ liệu rời mạng nội bộ; hiện chỉ có cấu hình trong repository mà không có bằng chứng kiểm tra đầu ra ở từng điểm xuất.
Một bản phát hành thay đổi parser, redaction và exporter cùng lúc; khi số log giảm, nhóm không biết do dữ liệu được lọc đúng hay pipeline bị lỗi và không có metric phân biệt hai trường hợp.
Nhóm xây cảnh báo khi phát hiện chuỗi giống secret ở output Collector nhưng không có cảnh báo khi processor ngừng chạy; sự cố cấu hình có thể khiến dữ liệu thô được gửi mà không tạo tín hiệu.
Đội đo tỷ lệ sự kiện bị redaction nhưng không ghi số lượng event đã xử lý và event bị drop; dashboard cho thấy tỷ lệ che cao mà không phát hiện mất dữ liệu hàng loạt.
Một quy tắc redaction mới che trường token trong log thành công nhưng không kiểm tra trace, metric, archive và bản sao; cuộc rà soát sau phát hành phát hiện cùng token ở các hệ thống phụ.
Trong quá trình điều tra, nhóm tạm vô hiệu hóa redaction cho một endpoint để xem payload lỗi; thay đổi không có phạm vi giới hạn, thời hạn tự phục hồi hay phê duyệt và để lại dữ liệu thô sau incident.
Một đội dùng mẫu dữ liệu sản xuất đã khử định danh để tái hiện lỗi; dữ liệu vẫn chứa các thuộc tính hiếm có thể ghép với nguồn công khai và nhận diện khách hàng.
Nhóm triển khai redaction theo allowlist trường được phép giữ nhưng một dịch vụ cũ gửi toàn bộ payload vào trường message; vì message được allowlist cho mục đích chẩn đoán, PII không bị loại.
Ứng dụng ghi log đã che ở logger chính nhưng một thư viện native ghi ra stderr; agent thu thập stdout và stderr như nhau nên secret từ thư viện vẫn tới Collector.
Đội cấu hình redaction tại Collector sau khi nhận telemetry qua TLS; dữ liệu đã được mã hóa trên đường truyền nhưng vẫn hiện nguyên trong buffer và memory dump khi Collector gặp sự cố.
Nhóm áp dụng chính sách che trên API trả dữ liệu cho người dùng nhưng không áp dụng khi tạo snapshot và backup; bản khôi phục sau sự cố đưa dữ liệu nhạy cảm trở lại môi trường tìm kiếm.
Một hệ thống dùng nhiều region và mỗi region có phiên bản Collector khác nhau; policy redaction mới được bật ở vùng chính nhưng vùng dự phòng vẫn xuất dữ liệu theo quy tắc cũ.
Đội phát triển muốn giữ một phần context để phân biệt lỗi do khách hàng, dịch vụ hay hạ tầng; policy hiện che mọi identifier cùng lúc và làm mất khả năng xác định phạm vi ảnh hưởng.
Trong bài kiểm thử cuối, nhóm gửi canary email, token, private key và số tài khoản qua logs, traces, metrics; một tín hiệu xuất hiện ở exporter phụ nên chưa thể chứng minh redaction đã bao phủ toàn bộ đường đi.
Một ứng dụng ghi JWT đầy đủ trong exception khi kiểm tra chữ ký thất bại; bộ lọc chỉ che access token dạng opaque nên header Authorization vẫn để lộ claim và chữ ký của token.
Regex redaction nhận diện số điện thoại nhưng tạo nhiều false positive trên mã đơn và error code; sau khi bật policy, đội vận hành mất các giá trị cần để nối log với ticket sự cố.
Nhóm nâng cấp OpenTelemetry semantic conventions làm đổi tên thuộc tính URL và user agent; quy tắc redaction vẫn kiểm tra tên trường cũ nên các span mới mang dữ liệu nhạy cảm qua Collector.

Một nhóm phát triển chỉ phân loại log ứng dụng theo mức nội bộ, nhưng access log của API lại chứa query string có email khách hàng; khi đưa cả hai nguồn vào kho quan sát chung, cùng một loại dữ liệu cá nhân bị áp dụng hai chính sách bảo vệ khác nhau.
Hệ thống thương mại điện tử gắn nhãn dữ liệu công khai cho toàn bộ metric vì chỉ có số liệu tổng hợp; sau đó một custom metric bắt đầu dùng customer_id làm label và được xuất ra dashboard dành cho đối tác.
Một trace thanh toán chỉ ghi tên service và duration ở span gốc, nhưng span HTTP con chứa URL có mã đặt chỗ và thông tin người mua; đội quản trị đã đánh giá độ nhạy cảm dựa trên span gốc thay vì toàn bộ trace.
Đội vận hành coi CPU profile là dữ liệu kỹ thuật không nhạy cảm, nhưng call stack ghi tên class chứa mã khách hàng được ghép động trong tên phương thức; profile được chia sẻ rộng hơn các log nghiệp vụ cùng tiến trình.
Một hệ thống đánh dấu toàn bộ telemetry của môi trường development là dữ liệu thấp rủi ro, trong khi môi trường đó được làm mới bằng bản sao dữ liệu production chưa được ẩn danh.
Ứng dụng tài chính ghi transaction_id vào log và trace; riêng lẻ mã này không chứa tên người dùng nhưng dịch vụ phân tích có thể liên kết với bảng giao dịch để xác định chủ tài khoản.
Một tổ chức phân loại dữ liệu chỉ theo tên trường password hoặc email; log lỗi của thư viện HTTP lại ghi nguyên Authorization header dưới trường message không có tên gợi ý nhạy cảm.
Một nhóm sản phẩm muốn giữ metric số lượng tài khoản bị khóa theo từng chi nhánh; tại chi nhánh chỉ có hai nhân viên, dashboard cho phép suy ra ai vừa bị khóa dù không ghi user_id trực tiếp.
Một dịch vụ bệnh viện xuất số lượt khám theo bác sĩ và bệnh hiếm; các nhãn tổng hợp có số lượng rất nhỏ khiến đối tác có thể suy đoán thông tin sức khỏe khi kết hợp với lịch hẹn công khai.
Nhóm thiết kế taxonomy gồm Public, Internal, Confidential và Restricted nhưng không thống nhất tiêu chí áp dụng; cùng trường địa chỉ IP được gắn hai mức khác nhau giữa access log và security log.
Một nhà cung cấp nhận telemetry đã được đánh dấu 'Internal' từ ứng dụng, nhưng hợp đồng chỉ cho phép chuyển dữ liệu mức Public; không có cơ chế kiểm tra sự khác biệt giữa mức phân loại nội bộ và quyền chia sẻ bên ngoài.
Đội vận hành gắn phân loại Restricted cho toàn bộ trace của hệ thống thanh toán dù đa số span chỉ có thời gian và status; chi phí lưu trữ tăng vì mọi trace đều bị chuyển tới kho bảo mật cao.
Một API quản trị ghi thông tin cấu hình cache vào log, trong đó có tên máy chủ nội bộ và sơ đồ kết nối; dù không phải PII, dữ liệu này có thể hỗ trợ người ngoài lập bản đồ hạ tầng.
Một tổ chức chỉ xem token và mật khẩu là bí mật, nhưng file log chứa khóa API đã được cắt bớt vài ký tự và vẫn đủ để đối chiếu với tên đối tác và thời điểm sử dụng.
Trace từ dịch vụ email có trường recipient chứa địa chỉ người nhận và trường template chứa loại thông báo; nếu chuyển trace tới dashboard dùng chung, người xem có thể suy ra hoạt động cá nhân của người nhận.
Một metric theo dõi tỷ lệ thất bại đăng nhập có nhãn username ở dạng hash ổn định; dù không thể đọc trực tiếp tên người dùng, cùng giá trị xuất hiện ở nhiều dịch vụ và cho phép liên kết hành vi xuyên hệ thống.
Nhóm phân loại log lỗi bằng severity ERROR rồi mặc định coi đây là thông tin nhạy cảm cao; trong khi log INFO ghi toàn bộ dữ liệu form đăng ký lại chưa được kiểm soát.
Một đội muốn đưa metadata về loại dữ liệu vào resource attributes của OpenTelemetry, nhưng các workload dùng nhiều nhãn phân loại tùy ý khiến truy vấn kiểm tra chính sách không nhận diện đủ các giá trị.
Ứng dụng Java tạo event ghi lỗi nghiệp vụ trong span của OpenTelemetry; event body chứa số điện thoại người dùng dù bộ phân loại hiện chỉ kiểm tra thuộc tính ở mức span.
Trong một ứng dụng hỗ trợ khách hàng, log chứa nội dung khách tự nhập vào ô mô tả; nhãn 'support_note' được xem là dữ liệu vận hành dù người dùng có thể đưa số giấy tờ, địa chỉ hoặc bí mật vào văn bản.
Một API ghi đường dẫn /users/18473/orders/812 vào span name thay vì route template; thông tin định danh bị đưa vào tên span và xuất hiện trong các bảng thống kê endpoint dùng chung.
Nhóm đưa mã phiên đăng nhập vào attribute session_id để nối trace nhưng chưa quyết định mã này có được xem là dữ liệu cá nhân có thể liên kết với người dùng hay không.
Một môi trường Kubernetes ghi giá trị tất cả environment variables vào diagnostic log khi pod khởi động; vài biến chứa credential tới database và hệ thống theo dõi chỉ áp dụng quy tắc lọc request bodies.
Ứng dụng dùng debug logging cho JDBC và ghi parameter binding; một truy vấn tìm khách hàng theo số định danh tạo log chứa dữ liệu nhạy cảm dù SQL statement chỉ chứa dấu hỏi.
Một HTTP client tự động ghi URL redirect trong log; đường dẫn callback của nhà cung cấp OAuth có query parameter chứa authorization code và được gửi tới hệ thống quan sát tập trung.
Nhóm có quy tắc không xuất body của request HTTP, nhưng exception serializer lại in toàn bộ object request vào trường stack_trace khi validation thất bại.
Một exporter thu log từ container stdout chứa header Cookie ở dạng chuỗi thô; collector đã ẩn trường http.request.header.cookie riêng nhưng không nhận ra cùng giá trị trong message.
Hệ thống ghi các dấu vết phân tích bằng baggage để chuyển tenant context qua nhiều service; một nhóm đặt số hồ sơ cá nhân vào baggage và giá trị lan tới cả những service không cần dữ liệu đó.
Nhân viên hỗ trợ sao chép toàn bộ trace của một khách vào ticket để nhờ nhà cung cấp xử lý; trace có baggage và span attributes chứa thông tin tài khoản vượt phạm vi được phép chia sẻ.
Ứng dụng gắn mã số thiết bị IoT làm metric label; bộ phận sản phẩm coi đó là dữ liệu phi cá nhân, nhưng thiết bị được đăng ký cố định với một hộ gia đình trong cơ sở dữ liệu khác.
Nhóm bảo mật cho phép lưu IP đã mask trong access log nhưng một trường x_forwarded_for khác vẫn giữ toàn bộ chuỗi địa chỉ gốc khi request đi qua nhiều proxy.
Một hệ thống thay email bằng mã hash không có salt trong telemetry; người có danh sách địa chỉ email khả dĩ có thể so sánh hash và liên kết một phần người dùng với bản ghi.
Đội phân tích muốn nhận diện người dùng quay lại bằng một identifier giả danh ổn định trong logs; chính sách quyền riêng tư cho phép đo lượt truy cập tổng hợp nhưng chưa cho phép theo dõi hành vi cá nhân lâu dài.
Một ứng dụng loại bỏ tên khách khỏi log nhưng vẫn giữ tổ hợp ngày sinh, mã bưu chính và giới tính; bộ phận kiểm soát dữ liệu phát hiện nguy cơ nhận diện lại từ các trường kết hợp.
Nhóm định nghĩa thông tin thanh toán chỉ gồm số thẻ, trong khi log còn ghi địa chỉ thanh toán, BIN và bốn số cuối cùng; bộ phận phân loại chưa đánh giá cách các trường kết hợp có thể ảnh hưởng đến mức nhạy cảm.
Đội vận hành cho rằng lỗi Java không chứa PII vì chỉ ghi stack trace; giá trị toString của object domain lại được đưa vào exception message khi thao tác thất bại.
API quản lý hồ sơ tạo log cho tất cả thay đổi bao gồm old_value và new_value; một trường được đổi thành mật khẩu khôi phục tài khoản và giá trị lịch sử vẫn được gửi tới Elasticsearch.
Nhóm chỉ lọc dữ liệu nhạy cảm ở log production, nhưng trace staging được thu từ hệ thống sử dụng tài khoản thử nghiệm có credential thật để truy cập đối tác.
Trong một ứng dụng bán vé, span attribute customer_category được coi là vô hại; khi kết hợp với nhãn event_id của sự kiện riêng tư, người xem dashboard có thể suy ra nhóm khách đã tham gia.
Một mobile SDK gửi device_id và advertising_id trong log chẩn đoán; ứng dụng backend lưu hai trường vào trace và chia sẻ với nhiều nhóm mà không đánh giá mục đích sử dụng ban đầu.
Thư viện gRPC bật tính năng log metadata khi kết nối lỗi; metadata chứa authorization token nhưng collector chỉ có bộ lọc theo tên header chuẩn của HTTP.
Đội vận hành muốn nhận biết giao dịch lỗi thông qua order_id trong metric; mỗi đơn tạo một chuỗi thời gian riêng và hệ thống giám sát không phân biệt đây là dữ liệu định danh với metric aggregate.
Một alert về số lượt giao dịch thất bại chuyển các giá trị metric labels vào thông báo chat công khai; label có customer_id mà người tạo metric tưởng chỉ xuất hiện trong Prometheus.
Người dùng tải file CSV qua API, tên file chứa họ tên và mã hợp đồng; access log và trace cùng ghi Content-Disposition khiến thông tin này xuất hiện trong công cụ quan sát.
Một service ghi chuỗi truy vấn cơ sở dữ liệu vào trace SQL statement; giá trị literal trong câu lệnh chưa được parameterize chứa số điện thoại mà quy tắc redaction chỉ nhận biết trường JSON.
JVM profiler ghi stack trace có tên thread được đặt theo email của khách hàng để thuận tiện debug; file profile được tải lên công cụ phân tích hiệu năng ngoài tổ chức.
Đội SRE xuất heap dump vào lúc điều tra leak và lưu cạnh CPU profiles trong bucket quan sát; heap dump chứa nội dung object trong bộ nhớ, bao gồm các token phiên đang hoạt động.
Một ứng dụng lưu dữ liệu nhạy cảm trong tên nhãn của span event thay vì giá trị attribute; bộ lọc OpenTelemetry chỉ kiểm tra giá trị nên không phát hiện nội dung không phù hợp ở tên trường.
Nhóm dùng service.instance.id có cấu trúc chứa số tài khoản khách hàng trong môi trường multi-tenant; nhãn này được chép thành resource attribute trên mọi metric và trace.
Một hệ thống phân loại raw telemetry là Restricted nhưng cho phép export các metric đã tổng hợp ở mức Internal; phép tổng hợp cho nhóm chỉ có một người dùng khiến mức bảo vệ của kết quả không còn phù hợp.
OpenTelemetry Collector nhận logs, metrics và traces từ nhiều service; cấu hình lọc PII được gắn vào logs pipeline nhưng traces pipeline vẫn chuyển nguyên http.request.header.authorization tới backend.
Một collector dùng attributes processor để xóa trường user.email trước khi export; log body dạng JSON vẫn chứa địa chỉ email với một tên trường khác và bộ lọc không quét nội dung body.
Nhóm thêm transform processor để mask session ID trong span attributes nhưng một collector khác ở tuyến egress vẫn gửi bản sao trace thô tới backend dự phòng trước bước mask.
Collector được cấu hình chạy batch processor trước bước lọc dữ liệu; khi batch queue bị dump ra log chẩn đoán trong sự cố, các record chưa được làm sạch xuất hiện trong log của collector.
Đội dùng tail sampling để giữ lại các trace lỗi; bộ đệm trong collector phải giữ trace đầu vào chưa được redaction và không có đánh giá về quyền truy cập hoặc vòng đời dữ liệu trong bộ đệm.
Một OpenTelemetry gateway dùng filter processor loại bỏ toàn bộ log chứa trường payment_card; hệ thống vẫn để lọt thông tin số thẻ khi thư viện ghi dưới dạng PAN trong trường message.
Nhóm dùng transform expression để xóa thuộc tính có tên khớp với một mẫu, nhưng một SDK gửi tên trường khác kiểu viết hoa; policy được coi là đang bảo vệ dữ liệu dù một số record không khớp.
Đội thiết kế quy tắc chỉ giữ allowlist span attributes, nhưng sau khi nâng cấp thư viện HTTP, tên route hợp lệ thay đổi và dashboard SLO thiếu các chiều cần thiết để theo dõi vận hành.
Một processor loại bỏ các thuộc tính chứa chuỗi token bất kể ngữ cảnh; tên 'token_bucket_size' của hệ thống rate limiting cũng bị xóa và nhóm không còn bằng chứng xác định nguyên nhân nghẽn.
Ứng dụng truyền bearer token trong http.url do client cũ; bộ lọc xóa header Authorization nhưng không xử lý URL query của span nên token vẫn còn trong trace.
Trong một cluster, collector agent thực hiện redaction còn collector gateway chỉ định tuyến telemetry; một service bỏ qua agent và gửi OTLP trực tiếp tới gateway, làm dữ liệu thô vượt qua lớp bảo vệ dự kiến.
Nhóm cấu hình telemetry phải được phân loại ở ứng dụng trước khi gửi đi, nhưng ứng dụng legacy không gắn nhãn phân loại; collector mặc định xem mọi record thiếu nhãn là Internal và gửi tới kho lưu trữ chung.
OpenTelemetry SDK có nhiều phiên bản khác nhau, một số gửi http.target còn phiên bản mới gửi url.full; bộ lọc đang viết cho semantic convention cũ không xử lý hết trường có dữ liệu trong bản mới.
Một collector được cấu hình drop mọi attribute user_id để tuân thủ chính sách; nhóm điều tra gian lận lại cần khả năng nối một giao dịch đã xác minh với log kiểm toán bảo vệ riêng và chưa phân định tuyến dữ liệu theo mục đích.
Đội loại bỏ các trace chứa dữ liệu nhạy cảm thay vì chỉ loại giá trị không cần thiết; sau khi policy có hiệu lực, các cuộc gọi tới API tài chính không còn trace để phân tích timeout.
Một ứng dụng ghi địa chỉ IP ở dạng IPv4 và IPv6; quy tắc mask chỉ nhận diện IPv4 nên các span từ client IPv6 tiếp tục tiết lộ địa chỉ đầy đủ.
Một pipeline dùng regex ẩn số thẻ trong log message; chuỗi số trong payload được chia thành nhiều phần bởi dấu cách hoặc dấu gạch ngang khiến một số bản ghi không khớp quy tắc.
Một nhóm áp dụng hashing cho user_id trước khi export traces nhưng không quản lý khóa băm theo từng tenant; có nguy cơ liên kết định danh của khách hàng giữa các tenant dù dữ liệu thô đã bị loại.
Pipeline telemetry đẩy dữ liệu tới hai exporter, một cho kho nội bộ và một cho nhà cung cấp ngoài; processor che PII chỉ có ở nhánh nội bộ, còn nhánh bên ngoài nhận cùng record chưa biến đổi.
Một collector sử dụng transform processor làm sạch mọi log body nhưng metrics pipeline không áp dụng giới hạn label; một custom metric có nhãn email vẫn vượt sang hệ thống quan sát bên ngoài.
Nhóm bật debug exporter trên collector để kiểm tra định dạng OTLP; log collector bắt đầu in nội dung span attributes và resource attributes trước khi qua bước che dữ liệu.
Trong một phiên bản mới, OpenTelemetry Collector fail startup do cấu hình transform không hợp lệ; nhóm triển khai chuyển tạm sang pipeline đơn giản không có redaction để giữ metrics mà không đánh giá rủi ro.
Một processor dùng action delete cho một số attribute khi được xác định thuộc Restricted; sau thay đổi upstream, trường đó chuyển sang log body và bộ lọc vẫn báo xử lý thành công cho những record nó thấy.
Nhóm ghi nhận metric số lượng record bị redaction nhưng không phân biệt loại trường hoặc nguồn phát; khi lượng record bị mask tăng vọt, họ không biết service nào bắt đầu xuất dữ liệu không phù hợp.
Một số span được drop vì không có nhãn data.classification; dashboard hiển thị trace completeness giảm nhưng đội vận hành nhầm nguyên nhân là network packet loss.
Collector memory limiter bắt đầu từ chối dữ liệu trong giờ cao điểm; hệ thống ưu tiên giữ audit/security telemetry theo yêu cầu nhưng cấu hình queue đang đối xử với mọi log thông thường và log kiểm toán giống nhau.
Đội dùng tail sampling để giữ 100% trace chứa lỗi 5xx; một endpoint lỗi thường ghi nội dung request chứa PII, khiến chính loại trace nhạy cảm nhất được giữ lại nhiều hơn các trace còn lại.
Nhóm thiết kế policy giữ trace có thanh toán thất bại 30 ngày nhưng trace thành công 3 ngày; collector không truyền nhãn kết quả nghiệp vụ đến storage nên hai loại trace được lưu cùng thời hạn.
Ứng dụng cho phép developer ghi custom span attribute tùy ý; một release mới thêm trường raw_request để debug và chính sách collector chưa có bước kiểm soát các trường không được khai báo.
Một API log chứa credential nhúng trong chuỗi connection string của exception; processor xóa trường db.password nhưng không nhận diện password trong thuộc tính exception.message.
Nhóm đặt nhãn sensitivity=confidential ở resource level cho toàn bộ service, nhưng một thư viện con gửi dữ liệu thuộc Restricted mà không có cơ chế nâng mức phân loại cho từng record.
Đội thay đổi chính sách từ giữ user_id dạng giả danh sang chỉ giữ user segment tổng hợp; các collector vùng khác nhau được cập nhật không đồng thời và cùng một giao dịch tạo ra dữ liệu ở hai mức bảo vệ.
Một triển khai multi-cluster dùng cùng tệp cấu hình collector nhưng vài cluster không bật processor bảo vệ do điều kiện môi trường; cùng một API tạo trace với cấu trúc khác nhau giữa các vùng.
Collector ghi dữ liệu sau khi scrub sang message broker chung, nhưng một sidecar log exporter khác vẫn đẩy bản ghi raw trực tiếp vào bucket dùng cho debug, nằm ngoài sơ đồ luồng dữ liệu được kiểm kê.
Một nhóm muốn dùng attribute classification để lọc theo mức nhạy cảm; attacker có thể đưa giá trị 'public' vào một trường do client kiểm soát và ứng dụng đang chuyển thẳng thành classification của span.
Ứng dụng gắn dữ liệu nhạy cảm vào trace baggage để theo dõi giữa các service; dù collector xóa baggage ở điểm export, các service trung gian đã nhận thông tin này qua request header.
Một cụm Kubernetes cấp quyền đọc Secret cho tài khoản của OpenTelemetry Collector nhằm cấu hình exporter; khi audit RBAC, quyền này bao gồm Secret của nhiều namespace không liên quan đến telemetry.
Collector agent chạy dưới quyền hệ điều hành cao để đọc log file của tất cả container; nhóm chỉ định export log của dịch vụ được phép nhưng agent vẫn có khả năng truy cập file của workload nhạy cảm.
Một vendor nhận traces qua OTLP HTTPS nhưng nhà phát triển muốn đổi tạm thành HTTP nội bộ để debug; đường đi hiện tại bao gồm một hop WAN không nằm trong ranh giới tin cậy.
Telemetry giữa ứng dụng và collector có TLS, nhưng collector đẩy dữ liệu tới kho object storage qua endpoint không mã hóa trong VPC; chính sách yêu cầu bảo vệ dữ liệu Confidential trên mọi chặng.
Nhóm chuyển từ collector nội bộ sang backend SaaS đặt tại vùng địa lý khác; traces chứa địa chỉ IP người dùng và mã hợp đồng vẫn được export như trước dù điều kiện xử lý dữ liệu đã thay đổi.
Nhà cung cấp monitoring cho phép nhân viên hỗ trợ của họ truy cập dashboard phục vụ sự cố; quyền xem trace details bao gồm cả thông tin khách hàng mà hợp đồng chỉ cho phép xử lý aggregate metrics.
Hệ thống đa tenant dùng chung một Prometheus để lưu metric; mỗi tenant có role đọc nhãn tenant của mình nhưng một số series thiếu tenant label và xuất hiện trong dashboard tổng của các khách hàng.
Một nền tảng tracing phân quyền theo project, còn collector chỉ gắn project vào resource attributes do ứng dụng tự gửi; service của một tenant cấu hình nhầm project và traces được đưa vào không gian khác.
Nhóm phát triển tạo Grafana dashboard public để chia sẻ latency với đối tác; query drill-down từ exemplars mở đến trace có email khách hàng trong span attributes.
Một alert gửi thông báo tới kênh chat nhiều đối tác; nhãn metric chứa mã người dùng và số điện thoại được tự động chèn vào phần description của cảnh báo.
Hệ thống lưu raw logs Restricted trong Elasticsearch nhưng cùng pipeline tạo bản sao để full-text search ở một cluster ít bảo vệ hơn mà không áp dụng phân loại lên bản sao.
Đội data science muốn nhận toàn bộ traces để nghiên cứu bottleneck; chính sách chỉ cho phép dùng dữ liệu hiệu năng tổng hợp, nhưng yêu cầu export đang bao gồm endpoint cá nhân và user context.
Một nhóm đối tác dùng API truy vấn telemetry có thể tìm kiếm theo trace ID do khách hàng cung cấp; endpoint không kiểm tra tenant ownership nên một ID hợp lệ từ tenant khác vẫn trả metadata.
Đội vận hành gửi heap dump tới công cụ profiler bên thứ ba; hợp đồng xử lý dữ liệu chỉ nêu metrics và traces, không nhắc tới dữ liệu bộ nhớ có thể chứa nội dung giao dịch.
Một bộ phận marketing muốn tận dụng log truy cập để phân tích hành trình người mua; dữ liệu ban đầu được thu để bảo trì và bảo mật, nhưng mục đích sử dụng mới chưa được đánh giá.
Nhóm dùng metadata service.name và cluster_name để phân loại telemetry; một số giá trị chứa tên dự án bảo mật nội bộ, nên bản thân tên nhãn cũng vượt phạm vi thông tin được phép chia sẻ.
Nhà cung cấp ghi nhận quyền truy cập của khách vào logs qua API nhưng không ghi thao tác export dữ liệu hàng loạt; đội kiểm toán chưa biết ai đã tải toàn bộ dữ liệu lịch sử ra ngoài.
Một engineer có quyền đọc traces để điều tra chậm API nhưng cũng thấy full exception stack chứa cấu hình mạng nội bộ; chính sách truy cập chỉ phân chia theo hệ thống chứ chưa theo loại dữ liệu trong một trace.
Một tổ chức áp dụng một thời hạn lưu 90 ngày cho tất cả telemetry; CPU metrics ít nhạy cảm và audit-related logs có nghĩa vụ khác nhau nhưng cùng bị xóa một lịch như nhau.
Đội thiết lập retention cho log dữ liệu cá nhân là 14 ngày, nhưng bản sao của log vẫn nằm trong snapshot Elasticsearch được giữ 180 ngày mà chưa có chính sách phù hợp.
Trong một đợt điều tra bảo mật, nhóm đặt legal hold cho security telemetry liên quan đến tài khoản bị xâm nhập; job xóa theo retention vẫn loại dữ liệu vì kho phụ không nhận thông tin hold.
Một yêu cầu xóa dữ liệu cá nhân đã được xử lý trong ứng dụng chính, nhưng các trace cũ có user_id và email vẫn còn trong hệ thống quan sát dài hạn mà quy trình chưa rà soát.
Nhóm xóa log theo thời hạn khỏi kho nóng nhưng chưa kiểm tra bản sao remote archive trên object storage; dữ liệu Confidential cũ vẫn có thể được tải qua link đã cấp trước đó.
Một hệ thống analytics chuyển metrics tổng hợp sang lưu trữ dài hạn, nhưng nhãn raw user_id đi kèm series vẫn được giữ 12 tháng dù các giá trị đo không cần định danh cá nhân.
Đội lưu profile CPU 30 ngày nhưng heap dump dùng để debug được upload vào cùng bucket mặc định giữ 365 ngày; hai loại dữ liệu có mức rủi ro khác nhau đang dùng chung lifecycle policy.
Service tracing ghi raw request body vào span event, sau đó bộ phận vận hành bật retention 7 ngày; những trace đã export từ trước sang kho khác vẫn có thời hạn lưu dài hơn.
Một kho dữ liệu quan sát phục vụ điều tra gian lận cần giữ audit trail nhiều năm, trong khi log truy cập cá nhân chỉ được phép giữ ngắn hạn; nhóm muốn xóa sớm một phần dữ liệu nhưng hệ thống dùng chung index.
Một cuộc điều tra yêu cầu giữ telemetry của 20 trace ID cụ thể, nhưng hệ thống lưu traces theo block chứa nhiều khách hàng; giữ cả block lâu hơn gây phát sinh phạm vi dữ liệu ngoài sự cố.
Nhóm đã mã hóa logs bằng khóa KMS riêng, nhưng sau khi xoay khóa không có hồ sơ ai được quyền giải mã dữ liệu lịch sử; nhân viên mới có thể đọc lại toàn bộ bản ghi Restricted.
Một archive chứa logs đã được redaction nhưng metadata tên file vẫn bao gồm account ID; quy tắc lưu trữ chỉ kiểm tra nội dung JSON và bỏ qua object keys.
Nhóm chia sẻ số liệu outage với đối tác dưới dạng CSV tổng hợp; một ô chứa danh sách trace IDs của các request lỗi để tiện drill-down và có thể dẫn tới dữ liệu khách khác.
Một hệ thống phân loại Unknown cho mọi telemetry thiếu nhãn, nhưng ở khâu export Unknown được gộp vào Public để tránh mất dữ liệu; sau đợt cập nhật SDK, nhiều bản ghi mới vượt qua ranh giới chia sẻ.
Đội thay đổi mapping data classification giữa log collector và storage: internal trở thành confidential; dashboard vẫn dùng quyền truy cập xây dựng theo mapping cũ và nhiều nhân viên không được thông báo.
Một business service gắn dấu phân loại Public cho metric total_revenue theo từng cửa hàng; tại những cửa hàng chỉ có một giao dịch trong giờ, tổng doanh thu có thể tiết lộ giá trị giao dịch cá nhân.
Ứng dụng sử dụng aggregate metrics để báo số người dùng có một bệnh lý hiếm theo từng địa phương; các ô thống kê rất nhỏ bị đưa vào dashboard dành cho người ngoài mà không có quy tắc kiểm soát suy luận.
Một SRE gắn ticket ID chứa tên khách hàng vào annotation của alert; thông tin này đi theo alert history và được export sang nhà cung cấp incident management ngoài tổ chức.
Nhóm bật recording rules để loại các nhãn PII khỏi metric trước khi đưa lên Grafana, nhưng mọi người có quyền truy cập datasource Prometheus vẫn có thể truy vấn metric raw chứa nhãn nhạy cảm.
Một trace chỉ ghi hash của user ID nhưng log ứng dụng ghi cùng hash và email; khi hai nguồn được hợp nhất trong data lake, bộ dữ liệu trace vốn đã hạ mức phân loại có thể được tái liên kết với người dùng.
Đội quản trị cho phép xuất anonymized metrics để nghiên cứu, nhưng nhóm nhận dữ liệu có thể nối các chuỗi timestamp rất hiếm với sự kiện được công bố trên mạng xã hội.
Một profile của ứng dụng chứa đường dẫn file có tên người dùng trong thư mục home; đội phát triển chia sẻ flamegraph dưới dạng ảnh nhưng chưa đánh giá liệu label có để lộ danh tính hay không.
Trong một CPU profile, biểu thức truy vấn SQL xuất hiện dưới dạng tên thread được sinh động; khi chia sẻ profile với vendor, thông tin tên bảng và schema thuộc hệ thống nội bộ cũng bị công bố.
Nhóm kiểm thử redaction bằng các trường test.email và test.phone nhưng không đưa vào mẫu số tài khoản, JWT, cookie, IPv6, UUID hoặc dạng ký tự Unicode; một release mới có nhiều trường không đi qua bộ lọc.
Một bài kiểm thử collector chỉ xác minh đường đi logs pipeline; khi service phát sinh span event và histogram exemplar chứa trace_id nhạy cảm, dữ liệu vẫn xuất sang dashboard bên ngoài.
Đội QA xác nhận trường authorization đã bị xóa sau khi ingest, nhưng exporter debug được bật trước bước bảo vệ nên output log của collector vẫn chứa token trong bản ghi chẩn đoán.
Nhóm kiểm thử chính sách phân loại trên một SDK version; sau cập nhật semantic conventions, thuộc tính có tên mới không được nhận diện nhưng pipeline vẫn hiển thị trạng thái healthy.
Trong một diễn tập, engineer tắt processor che thông tin để tăng tốc độ thu thập khi collector CPU cao; hiệu năng cải thiện nhưng không có quy trình đánh giá mức độ rủi ro và thời điểm bật lại.
Một alert thông báo số bản ghi bị redaction tăng đột ngột nhưng không chỉ ra loại trường và service gây ra; đội vận hành không biết đây là sai cấu hình instrumentation hay chiến dịch khai thác lỗ hổng.
Pipeline bỏ mọi dữ liệu không nhận diện được classification; khi ứng dụng Java mới lên production, hầu hết traces biến mất và nhóm chưa cân bằng yêu cầu tránh rò rỉ với khả năng chẩn đoán sự cố.
Một nhóm chuẩn hóa mức phân loại dựa vào environment và service, nhưng một service quản lý hồ sơ khách có endpoint public và private; phân loại toàn service không phản ánh độ nhạy cảm khác nhau của từng thao tác.
Đội đặt retention metric aggregate rất dài và cho phép chia sẻ rộng; về sau một thành viên thêm nhãn small_cohort vào metric, làm bộ dữ liệu cũ và mới không còn phù hợp cùng chính sách.
Người dùng yêu cầu thu hồi quyền chia sẻ trace với vendor sau khi kết thúc ticket; link truy cập đã được gửi vào email và bản export CSV vẫn nằm trong kho riêng của nhóm hỗ trợ.
Một nhân viên cũ bị thu hồi quyền truy cập dashboard nhưng API token cá nhân dùng trong script export logs vẫn còn hiệu lực; nhật ký truy cập hiển thị dữ liệu Restricted tiếp tục được tải về.
Trong một incident, đội trực chia sẻ log thô qua công cụ chat để giải quyết nhanh; quy tắc redaction của collector đã tồn tại nhưng người chia sẻ lấy dữ liệu trực tiếp từ file trên node trước collector.
Đội bảo mật muốn theo dõi những ai xem telemetry nhạy cảm, nhưng hệ thống audit chỉ ghi truy cập datasource chứ không ghi thao tác mở từng trace hay tải file profile.
Nhóm lưu telemetry phân loại Restricted trong một cluster có phân quyền chặt, nhưng backup tự động được sao sang tài khoản cloud khác với chính sách quyền đọc rộng hơn.
Một tenant xóa dữ liệu khỏi ứng dụng sau khi đóng tài khoản, song metrics time series mang tenant_id còn xuất hiện trong remote storage và các recording rules được lưu dài hạn.
Sau khi áp dụng quy tắc mask mới cho OpenTelemetry, số alert về HTTP 5xx giảm hẳn; dashboard cũng cho thấy các status_code và route labels bị xóa, khiến nhóm không biết lỗi thực giảm hay dữ liệu đo bị thiếu.
Trong một đợt thay đổi exporter, nhóm gửi telemetry từ môi trường thử nghiệm sang endpoint production của nhà cung cấp; một số log test chứa bản ghi được sao từ production và không có đánh dấu mục đích sử dụng.
Một tổ chức hợp nhất hai nhà cung cấp observability; dữ liệu cũ đã từng được chia sẻ theo hợp đồng khác, trong khi bản export mới chuyển cả logs, traces và profiles vào một hệ thống chưa có cùng quyền hạn.
Một kiến trúc dùng collector agent tại từng vùng và gateway trung tâm; chính sách dữ liệu phải lưu trong vùng được áp dụng tại gateway sau khi raw data đã rời vùng địa lý ban đầu.
Nhóm muốn dùng danh sách classification trên schema registry để kiểm tra trường telemetry trước khi phát hành; ứng dụng mới tạo custom attribute chưa đăng ký nhưng pipeline hiện tại vẫn cho phép xuất theo mặc định.
Một ứng dụng gửi giá trị age_group dưới dạng nhãn thống kê, nhưng một nhóm khách chỉ có một người trong nhóm tuổi hiếm; dashboard đã ẩn user_id mà vẫn có nguy cơ tái nhận diện qua số liệu nhóm nhỏ.
Trong review sau sự cố, đội vận hành chỉ kiểm tra dữ liệu không còn xuất hiện ở dashboard khi thêm filter; metric raw vẫn được lưu trong backend và tài khoản khác có thể truy vấn qua API trực tiếp.

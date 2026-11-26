Một cụm Logstash nhận log từ Filebeat qua Beats input nhưng sau khi đổi địa chỉ listener, các agent vẫn gửi tới cổng cũ; hàng đợi phía agent tăng trong khi pipeline Logstash không có sự kiện mới.
Ứng dụng gửi JSON log qua HTTP input nhưng Content-Type thay đổi giữa application/json và text/plain; một số event được parse thành object còn số khác nằm nguyên trong message.
Logstash nhận Syslog từ nhiều máy Linux nhưng không phân biệt được nguồn do NAT làm nhiều host có cùng địa chỉ quan sát; nhóm cần chuẩn hóa hostname và metadata nguồn trước khi định tuyến.
Một pipeline đọc file log legacy bằng file input nhưng glob chỉ khớp thư mục cũ; sau khi ứng dụng đổi vị trí file, Logstash vẫn chạy bình thường mà không nhận bản ghi mới.
Logstash đọc file log bằng sincedb trên ổ đĩa tạm của container; sau khi pod được tạo lại, file cũ bị đọc lại và hàng triệu event trùng xuất hiện trong Elasticsearch.
File input theo dõi file đang được logrotate đổi tên; Logstash giữ handle file cũ trong lúc ứng dụng tiếp tục ghi file mới, tạo khoảng trống ở thời điểm chuyển tệp.
Một ứng dụng ghi log nhiều dòng và Logstash đọc từng dòng qua file input; stack trace bị tách thành nhiều event do multiline được cấu hình ở filter thay vì tại nơi thu thập phù hợp.
Nhóm chuyển từ Filebeat sang Elastic Agent nhưng vẫn để Beats input cũ và agent gửi đồng thời; cùng một log event được ingest hai lần qua hai đường.
Kafka input của Logstash đọc topic có nhiều partition nhưng consumer group không cân bằng lại sau khi tăng số worker; một số partition bị xử lý chậm và consumer lag tăng.
Logstash Kafka input bị cấu hình sai bootstrap server sau khi cụm Kafka đổi DNS; tiến trình vẫn khởi động nhưng không nhận được event mới từ topic.
Một topic Kafka có message key dùng để giữ thứ tự theo order_id; Logstash xử lý song song và output không bảo toàn thứ tự sự kiện của cùng một đơn hàng.
Logstash nhận event từ RabbitMQ trong khi broker tạm ngừng; kết nối tự khôi phục nhưng các message chưa xác nhận được gửi lại và xuất hiện trùng trong kho log.
HTTP input của Logstash mở công khai trong mạng nội bộ và không có xác thực; một máy thử nghiệm gửi event giả với service.name của production làm sai dashboard.
Nhóm nhận log qua TCP input nhưng không có framing rõ ràng; nhiều bản ghi nối liền trên cùng kết nối bị ghép thành một event hoặc tách sai ranh giới.
Một nguồn gửi JSON có newline trong trường message qua TCP; codec line mặc định tách payload thành nhiều sự kiện và parser downstream báo lỗi.
Logstash pipeline nhận event từ Beats có metadata Kubernetes nhưng filter mutate ghi đè host và container fields; đội trực mất khả năng xác định pod nguồn.
Một pipeline dùng nhiều input plugins nhưng không thêm tag phân biệt nguồn; filter áp chung grok pattern khiến log audit bị parse như access log Nginx.
Logstash nhận event từ nhiều tenant qua cùng Beats input; metadata tenant do client tự gửi được tin cậy mà không kiểm tra danh tính nên một tenant có thể gắn nhãn dữ liệu sang tenant khác.
Một pipeline được cấu hình nhận log qua TLS nhưng client Beats vẫn dùng CA cũ; sau khi xoay chứng chỉ, kết nối từ một nhóm host thất bại trong khi các host khác hoạt động.
Logstash nhận log Syslog UDP trong đợt mất mạng ngắn; do UDP không có cơ chế xác nhận và retry ở tầng truyền, một phần event biến mất mà không có dấu hiệu trong pipeline.
Một access log Nginx có định dạng cố định được parse bằng Grok; sau khi thêm trường upstream_cache_status, pattern cũ không khớp và event bị gắn _grokparsefailure.
Grok pattern dùng nhiều nhánh regex backtracking trên message dài; một số event bất thường làm CPU Logstash tăng cao và worker filter bị chiếm trong thời gian dài.
Nhóm dùng Grok để parse log Java multiline nhưng pattern quá tham lam; một stack trace ghép nhầm sang log request tiếp theo và mất ranh giới sự kiện.
Ứng dụng đổi format timestamp từ ISO 8601 sang dạng ngày giờ địa phương; Grok vẫn trích xuất được chuỗi nhưng date filter không parse được nên @timestamp rơi về thời điểm ingest.
Pipeline Grok có nhiều pattern fallback nhưng không ghi nhận pattern nào đã khớp; khi định dạng log thay đổi, nhóm không biết nhánh parser nào đang xử lý dữ liệu production.
Log access chứa URI có dấu ngoặc vuông và ký tự mã hóa; Grok pattern tự viết không xử lý escape đúng nên trường request_uri bị cắt giữa chừng.
Nhóm dùng Dissect cho access log có delimiter cố định; một client gửi user-agent chứa khoảng trắng và dấu nháy khiến vị trí trường phía sau bị dịch.
Dissect pattern được viết theo thứ tự trường của phiên bản ứng dụng cũ; sau khi backend thêm trường request protocol, status và duration bị ánh xạ nhầm.
Một số log có tiền tố cố định, số khác có tiền tố tùy biến theo tenant; Dissect không khớp các bản ghi biến thể và nhóm chưa có nhánh fallback.
Đội thay Grok bằng Dissect để tăng throughput nhưng không đo tỷ lệ parse failure; tốc độ pipeline tăng song các trường quan trọng không còn được trích xuất từ log ngoại lệ.
Logstash dùng JSON filter để parse trường message; một số ứng dụng đã gửi event dạng object từ Beats nên filter parse lần hai và tạo lỗi type mismatch.
JSON filter được cấu hình target sai; trường gốc message bị ghi đè trước khi đội vận hành giữ bản sao raw, làm mất dữ liệu để điều tra parser.
Ứng dụng phát log JSON có trường duration lúc là số, lúc là chuỗi kèm đơn vị; Elasticsearch mapping conflict xuất hiện sau khi pipeline chuyển các kiểu dữ liệu không nhất quán.
Nhóm dùng KV filter để parse query string nhưng giá trị chứa dấu bằng được URL-encode; filter tách sai key/value và làm mất một phần nội dung tham số.
Log ứng dụng chứa CSV với dấu phẩy trong trường quoted; CSV filter không xử lý đúng dấu nháy và đẩy giá trị cột sang trường kế tiếp.
Mutate filter đổi kiểu status thành integer trước khi kiểm tra trường rỗng; event thiếu status bị lỗi chuyển kiểu và bị gắn tag lỗi.
Pipeline dùng mutate rename để chuyển user_agent sang user-agent nhưng một filter sau đó vẫn tham chiếu tên cũ; trường thiết bị không được phân loại trong output.
Date filter parse timestamp có timezone offset nhưng timezone mặc định được đặt thêm lần nữa; các event từ vùng khác bị lệch nhiều giờ trong Kibana.
Log cũ không có timezone và được phát từ nhiều quốc gia; date filter áp một timezone chung khiến timeline sự cố giữa các vùng không thể đối chiếu.
Nhóm dùng geoip filter trên địa chỉ IP của reverse proxy thay vì IP client; bản đồ lưu lượng hiển thị vị trí của proxy và không phản ánh nguồn request.
GeoIP database được cập nhật nhưng pipeline dùng trường client.ip đôi khi chứa danh sách X-Forwarded-For; filter không chọn được IP thực và kết quả vị trí không ổn định.
User agent filter chạy trên chuỗi đã bị cắt ngắn bởi parser; dashboard thống kê browser và hệ điều hành chuyển nhiều client thành Unknown.
Fingerprint filter dùng trường message đã được chuẩn hóa khác nhau giữa các phiên bản; cùng một sự kiện logic tạo document ID khác và không còn khả năng khử trùng lặp.
Nhóm dùng fingerprint làm document_id cho output Elasticsearch nhưng bỏ qua tenant và source; hai event khác nguồn có nội dung giống nhau ghi đè lên nhau.
Aggregate filter cần gom nhiều dòng log thành một giao dịch nhưng các event của cùng session đến lệch thứ tự; timeout của task quá ngắn khiến giao dịch bị chia thành nhiều nhóm.
Pipeline aggregate filter giữ state trong bộ nhớ; khi Logstash restart giữa lúc xử lý batch, các event chưa hoàn tất không được ghép với phần còn lại.
Đội dùng clone filter để tạo event audit và event phân tích; trường nhạy cảm đã bị nhân đôi trước khi redaction chạy ở một nhánh filter khác.
Drop filter loại bỏ health check nhưng điều kiện match quá rộng; log của endpoint nghiệp vụ có đường dẫn tương tự cũng bị loại khỏi Elasticsearch.
Nhóm dùng conditional routing theo environment nhưng nhiều event thiếu trường environment; các log production rơi vào nhánh mặc định có index retention ngắn.
Logstash định tuyến security audit sang index riêng, nhưng điều kiện if kiểm tra tag sai tên; dữ liệu audit được ghi chung với application log và quyền đọc rộng hơn dự kiến.
Một pipeline-to-pipeline output gửi event sang pipeline đích nhưng trường metadata cần thiết không được giữ; nhánh downstream không thể xác định nguồn và chọn index đúng.
Nhóm tách pipeline theo service để tăng song song; một event bị gửi tới cả pipeline chính và pipeline phụ rồi được output vào hai data stream không đồng bộ.
Nhóm chuẩn hóa log theo Elastic Common Schema (ECS) nhưng dùng source.ip cho IP của proxy thay vì client.ip; dashboard security phân tích sai nguồn kết nối.
Pipeline gán event.dataset theo tên ứng dụng không nhất quán giữa Beats và Logstash; các data stream cùng service bị chia thành nhiều dataset ngoài dự kiến.
Logstash đổi field timestamp sang @timestamp nhưng vẫn giữ trường cũ dạng chuỗi; Kibana data view chọn nhầm trường thời gian và truy vấn theo khoảng ngày bị sai.
Một nhóm dùng ECS error.code cho mã HTTP trong khi nhóm khác dùng http.response.status_code; dashboard chung không tổng hợp được tỷ lệ lỗi của toàn bộ dịch vụ.
Pipeline chuyển log Nginx sang ECS nhưng không chuẩn hóa event.category và event.type; rule phát hiện an ninh không khớp các sự kiện mới dù dữ liệu đã được index.
Đội thêm service.environment vào event nhưng index template mong đợi service.environment là keyword; mapping hiện tại đã tạo thành text khiến truy vấn filter chậm và không chính xác.
Logstash gửi trường bytes lúc integer và lúc string; Elasticsearch từ chối một phần bulk request do mapping conflict, trong khi pipeline chỉ đếm tổng số event đã xử lý.
Index template cho logs-* không áp dụng vào data stream mới vì priority thấp hơn template khác; các trường ECS được mapping sai ngay từ document đầu tiên.
Output Elasticsearch dùng index theo ngày nhưng ứng dụng tạo index mới mỗi lần thay tên service; số lượng index và shard tăng nhanh dù mỗi index chỉ có ít tài liệu.
Nhóm chuyển output sang data stream nhưng cấu hình document_id và action update không phù hợp kiểu ghi append; Elasticsearch từ chối thao tác ghi một số event.
Logstash output Elasticsearch dùng credential hết hạn sau khi đổi mật khẩu; bulk request nhận 401 và persistent queue tăng dần mà ứng dụng nguồn vẫn gửi bình thường.
Output Elasticsearch kết nối TLS tới cluster nhưng Logstash không tin CA nội bộ; lỗi certificate verify khiến worker output retry liên tục.
Elasticsearch trả HTTP 429 khi node quá tải; Logstash output tăng retry và hàng đợi phía trước phình to trong khi ingest latency tăng.
Bulk output gửi batch quá lớn khiến Elasticsearch từ chối một phần request do giới hạn payload; Logstash retry cả batch và một số event bị ghi lặp.
Elasticsearch output báo bulk request thành công ở cấp HTTP nhưng response có item-level errors; pipeline chỉ nhìn status tổng nên không phát hiện document mapping bị từ chối.
Output ghi vào nhiều index theo routing field nhưng một số event thiếu index target; pipeline gửi vào tên mặc định không được quản lý ILM và lưu trữ vô thời hạn.
Nhóm sử dụng action update với document_id không ổn định; mỗi lần retry tạo tài liệu mới thay vì cập nhật cùng bản ghi và số event trùng tăng.
Logstash ghi log audit và application vào cùng tài khoản Elasticsearch có quyền quản trị; một lỗi pipeline có thể xóa hoặc thay đổi index ngoài phạm vi output cần thiết.
Persistent Queue của Logstash chưa được bật; khi Elasticsearch ngừng nhận dữ liệu và Logstash restart, event đang nằm trong memory queue bị mất.
Nhóm bật Persistent Queue nhưng đặt queue.max_bytes quá nhỏ so với tốc độ ingest; outage vài phút làm queue đầy và input bắt đầu backpressure.
Persistent Queue lưu trên volume ephemeral của container; pod bị reschedule sang node khác khiến dữ liệu đang chờ gửi biến mất.
Đội bật checkpoint cho Persistent Queue quá thưa để giảm I/O; sau khi host mất điện, các event chưa được checkpoint bị mất dù queue được cấu hình persistent.
Persistent Queue tăng kích thước nhanh nhưng dashboard chỉ theo dõi JVM heap; node đầy đĩa trước khi có cảnh báo và Logstash không thể tiếp tục ghi queue.
Logstash restart trong lúc queue gần đầy; thời gian replay kéo dài và pipeline không kịp xử lý log mới, tạo thêm backlog từ các input.
Nhóm dùng một Persistent Queue chung cho pipeline nhiều nguồn; log debug lưu lượng cao chiếm hết queue và ngăn audit log quan trọng được tiếp nhận.
Dead Letter Queue được bật cho lỗi mapping nhưng không có tiến trình theo dõi dung lượng; các event bị từ chối tích lũy nhiều tuần và chiếm hết đĩa.
Elasticsearch từ chối event do mapping conflict; event vào DLQ nhưng đội vận hành không có quy trình phân loại, sửa mapping và replay dữ liệu.
DLQ chứa event có field sai kiểu; nhóm replay trực tiếp sau khi sửa output nhưng không sửa dữ liệu gốc nên event tiếp tục bị từ chối.
Đội chỉ kiểm tra DLQ của pipeline chính, trong khi pipeline phụ không bật DLQ; một phần event bị lỗi output biến mất mà không có bản sao phục hồi.
Một sự kiện bị từ chối bởi nhiều nguyên nhân nhưng DLQ chỉ giữ một metadata lỗi; đội điều tra không xác định được lỗi đầu tiên và nguyên nhân phát sinh ở filter hay output.
Logstash nhận event tốc độ cao nhưng filter Grok xử lý đơn luồng với pattern nặng; pipeline worker utilization đạt 100% trong khi input queue tăng.
Nhóm tăng pipeline.workers lên gấp đôi nhưng CPU đã bão hòa; context switching tăng và throughput giảm thay vì cải thiện.
Batch size của Elasticsearch output tăng để giảm overhead nhưng heap Logstash tăng theo kích thước event; Full GC xảy ra liên tục khi nhận log payload lớn.
Một pipeline có filter Ruby thực hiện tra cứu đồng bộ ra dịch vụ bên ngoài cho mỗi event; độ trễ mạng của dịch vụ đó làm nghẽn toàn bộ worker filter.
Nhóm bật nhiều grok pattern fallback để hỗ trợ format cũ; hầu hết event khớp pattern cuối cùng sau khi thử tất cả, khiến CPU tăng đáng kể.
Logstash có nhiều pipeline riêng nhưng pipeline.id và worker được phân bổ không theo tải; một pipeline audit nhỏ dùng quá nhiều worker trong khi pipeline access log thiếu tài nguyên.
Input Beats nhận dữ liệu nhanh hơn output Elasticsearch; không có backpressure phù hợp và agent nguồn tiếp tục gửi khiến bộ nhớ và queue của Logstash tăng liên tục.
Logstash chạy trong Kubernetes với memory limit thấp hơn heap cộng off-heap; container bị OOMKilled dù JVM heap chưa đạt Xmx.
JVM heap được đặt quá cao so với RAM máy; hệ điều hành thiếu bộ nhớ cho page cache và Persistent Queue, gây I/O chậm khi tải tăng.
Đội bật monitoring API của Logstash nhưng không thu thập pipeline events và queue metrics; dashboard chỉ biết tiến trình sống mà không phát hiện pipeline bị nghẽn.
Một pipeline có số event in và out khác nhau nhưng không theo dõi filter failures hoặc dropped events; nhóm không xác định được dữ liệu mất ở processor nào.
Nhóm bật debug logging của Logstash trong thời gian dài; log nội bộ chứa event payload và chiếm dung lượng đĩa trong khi hiệu năng xử lý giảm.
Logstash reload pipeline khi có cấu hình mới nhưng một pipeline không biên dịch được; pipeline cũ tiếp tục chạy và người vận hành tưởng thay đổi đã được áp dụng.
Đội sửa nhiều file pipeline cùng lúc rồi reload; một file có conditional sai cú pháp làm toàn bộ pipeline config không được nạp theo mong muốn.
Pipeline config được lưu trong nhiều thư mục và thứ tự nạp không rõ; một filter cũ được nạp sau filter mới, ghi đè hành vi chuẩn hóa ECS.
Nhóm triển khai pipeline qua GitOps nhưng một node Logstash vẫn chạy cấu hình thủ công cũ; cùng loại log được parse và định tuyến khác nhau tùy node.
Đội muốn kiểm thử Grok pattern trước production nhưng chỉ chạy vài event mẫu đơn giản; định dạng có stack trace, ký tự Unicode và field tùy chọn gây lỗi sau phát hành.
Test pipeline chỉ xác nhận event có trường message; không kiểm tra timestamp, ECS mapping, index target và tags lỗi nên nhiều sai lệch không bị phát hiện.
Một pipeline test dùng dữ liệu đã chuẩn hóa trong khi production nhận log thô; test pass nhưng Grok và Dissect không khớp dữ liệu thực tế.
Nhóm thay đổi thứ tự filter mutate và date; trường timestamp bị đổi tên trước khi date filter đọc, làm @timestamp không được thiết lập.
Date filter có tag _dateparsefailure nhưng pipeline output vẫn ghi event vào index production; dashboard dùng @timestamp ingest và không thể dựng lại thời điểm sự kiện.
Logstash nhận event với timestamp cũ hơn nhiều ngày; Elasticsearch output dùng index theo @timestamp và tạo index lịch sử ngoài dự kiến, làm ILM không áp dụng như mong muốn.
Nhóm routing event theo tag _grokparsefailure sang index quarantine nhưng quên giới hạn quyền đọc; event thô có dữ liệu nhạy cảm được lưu ở nơi nhiều người truy cập.
Pipeline che Authorization header sau khi Grok parse message nhưng trường event.original vẫn chứa header gốc; output Elasticsearch lưu cả bản đã che và bản nguyên.
Logstash cấu hình TLS cho Beats input nhưng tắt xác minh client certificate; mọi agent có thể kết nối nếu biết địa chỉ và cổng listener.
Credential Elasticsearch được khai báo trực tiếp trong file pipeline; repository cấu hình được chia sẻ rộng khiến thông tin truy cập backend có nguy cơ bị lộ.
Đội xoay mật khẩu output Elasticsearch nhưng quên cập nhật secret trong một node Logstash; lỗi 401 chỉ xảy ra ở một phần lưu lượng sau khi cân bằng tải.
Một Logstash pipeline gửi dữ liệu sang hai cluster Elasticsearch ở vùng khác nhau; một output có TLS và xác thực, output phụ vẫn gửi plaintext qua mạng liên vùng.
Nhóm sử dụng field tenant do log client gửi để chọn index; không xác thực nguồn field khiến một client có thể định tuyến event vào index của tenant khác.
Log audit có trường email và token được gửi vào DLQ không mã hóa; người có quyền đọc đĩa Logstash có thể lấy dữ liệu nhạy cảm từ event chưa xử lý.
Pipeline drop một số log thành công để giảm dung lượng nhưng điều kiện dựa trên status text; status '200 OK' và số 200 bị xử lý khác nhau giữa các nguồn.
Nhóm muốn loại health check khỏi index nhưng vẫn cần đếm số lần probe; drop filter xóa event trước khi metric đếm được cập nhật.
Một pipeline clone event cho mục đích audit và analytics; hai bản sao không có trường phân biệt nên người truy vấn cộng cả hai và báo cáo số lần giao dịch gấp đôi.
Logstash chuyển đổi timezone và chuẩn hóa @timestamp nhưng không lưu original timestamp; khi phát hiện sai lệch từ nguồn, không còn dữ liệu gốc để đối chiếu.
Đội phát triển đổi schema log mà không version hóa; Logstash phải duy trì nhiều nhánh Grok khó kiểm soát và một số field ECS thay đổi ý nghĩa giữa phiên bản.
Một ứng dụng gửi stack trace có hàng trăm dòng; multiline codec ghép nhiều exception của các thread khác nhau khi timestamp đầu dòng không ổn định.
Nhóm dùng Dissect cho log có delimiter thay đổi theo locale; dấu phẩy thập phân trong duration bị hiểu là ranh giới trường và làm sai giá trị.
Pipeline Logstash có filter mutate convert duration thành float nhưng giá trị '1,25' từ một locale không được parse; các event này bị chuyển sang nhánh lỗi.
Elasticsearch output dùng pipeline ingest phía server để enrich GeoIP thêm lần nữa sau Logstash; trường source.geo bị ghi đè và kết quả địa lý khác với dữ liệu đầu vào.
Nhóm không thiết lập document_id ổn định cho event được replay từ Kafka; khi khôi phục sau outage, cùng message được lưu thêm lần nữa và dashboard đếm sai.
Logstash input Kafka đã commit offset trước khi output Elasticsearch xác nhận ghi thành công; khi output lỗi, event bị mất dù consumer group đã tiến offset.
Đội cấu hình Kafka input ở chế độ xử lý at-least-once nhưng không thiết kế idempotency cho Elasticsearch output; retry tạo nhiều document trùng.
Một pipeline output sang S3 archive và Elasticsearch hot index; khi S3 chậm, worker output chung bị ảnh hưởng và ingest Elasticsearch cũng chậm theo.
Nhóm dùng pipeline-to-pipeline để tách log bảo mật và log ứng dụng nhưng một event có tag audit bị gửi nhầm cả hai nhánh; dữ liệu nhạy cảm vào index application.
Đội muốn ưu tiên audit event khi pipeline nghẽn; cấu hình chỉ dùng một queue FIFO nên log debug đến trước chiếm chỗ và audit event phải chờ.
Logstash monitoring báo pipeline throughput ổn định nhưng Elasticsearch indexing pressure tăng; nhóm chưa đối chiếu event rate, bulk rejection và queue growth giữa hai tầng.
Trong một outage, đội chỉ restart Logstash để xóa backlog; Persistent Queue chưa được bảo toàn và một phần dữ liệu đang chờ bị mất khi tiến trình dừng cưỡng bức.

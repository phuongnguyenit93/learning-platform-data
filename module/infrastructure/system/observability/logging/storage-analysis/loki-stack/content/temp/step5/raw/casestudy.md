Một công ty có 40 microservice Java trên Kubernetes đã triển khai Grafana Loki nhưng dashboard không có log từ dịch vụ thanh toán, trong khi truy cập trực tiếp pod vẫn xem được stdout; nhóm SRE cần khoanh vùng đoạn thu thập từ container tới kho log.
Đội hạ tầng cài Grafana Alloy dưới dạng DaemonSet để đọc log container; một số node mới được thêm vào cluster không có pod collector phù hợp nên log của workload trên các node này không xuất hiện trong Grafana.
Một ứng dụng Spring Boot ghi log vào tập tin trong filesystem của container thay vì stdout; sau khi pod được thay thế, các dòng lỗi quan trọng biến mất dù Alloy đang thu thập đúng đường log container mặc định.
Một hệ thống Java ghi log JSON vào stdout nhưng thư viện ghi thêm stack trace trên nhiều dòng; khi tra lỗi trong Loki, phần stack trace bị chia thành nhiều entry không có trace ID và thời điểm liên kết không rõ ràng.
Nhóm phát triển chuyển log ứng dụng sang JSON có trường level, timestamp, service và trace_id, nhưng dashboard cũ lọc theo chuỗi ERROR thuần nên bỏ sót những sự kiện lỗi mới sau phát hành.
Một service Java ghi thời gian log theo múi giờ máy chủ còn collector sử dụng thời điểm tiếp nhận; khi nhiều vùng cùng gửi dữ liệu, các sự kiện trong Grafana xuất hiện sai thứ tự so với thời điểm giao dịch thực tế.
Một microservice Java chạy qua nhiều thread và ghi trace_id trong MDC, nhưng một số dòng log từ CompletableFuture thiếu trường này; người trực không thể nối lỗi bất đồng bộ với request HTTP mặc dù trace đã được ghi.
Một ứng dụng dùng logger bất đồng bộ với hàng đợi giới hạn; khi phát sinh hàng nghìn exception trong một giây, số log nhận tại Loki ít hơn số lỗi thực tế dù service vẫn đang hoạt động.
Đội phát triển bật log DEBUG trên toàn bộ hệ thống trong giờ cao điểm để chẩn đoán lỗi; lưu lượng gửi log tăng hàng chục lần và collector bắt đầu tiêu thụ CPU lớn hơn chính ứng dụng cần theo dõi.
Một nhóm đặt toàn bộ payload HTTP request và response vào log JSON để kiểm tra lỗi đối tác; các bản ghi chứa token và thông tin khách hàng đi thẳng vào Loki và xuất hiện với mọi người có quyền xem datasource.
Ứng dụng Java có trường order_id và user_id khác nhau ở mỗi request; đội vận hành biến cả hai trường thành nhãn Loki để tìm kiếm nhanh, khiến số lượng stream tăng chóng mặt khi chiến dịch bán hàng bắt đầu.
Một API nhiều tenant sử dụng nhãn tenant_id trên từng stream trong khi hàng chục nghìn tenant có lưu lượng thấp; bộ nhớ phục vụ index và số lượng stream tăng nhanh hơn tổng lượng log, khiến chi phí vận hành vượt dự toán.
Nhóm SRE dùng Kubernetes pod UID làm label Loki; các pod được thay thế mỗi giờ làm nhãn đổi liên tục và stream cũ tồn tại dù service vẫn cùng chức năng, làm việc truy vấn lịch sử trở nên phân mảnh.
Một ứng dụng ghi trace_id như label để liên kết log với tracing; mỗi request tạo một stream gần như riêng biệt nên query theo service chậm hơn đáng kể mặc dù khối lượng log không tăng.
Doanh nghiệp muốn lọc log theo mã đơn hàng từ Grafana, nhưng nhóm bảo trì lo ngại đưa order_id vào index; dữ liệu hiện chỉ được lưu trong nội dung dòng log nên các truy vấn không có bộ lọc nhãn ban đầu rất tốn tài nguyên.
Một đội chọn label service, namespace và environment cho Loki nhưng bỏ sót cluster; log từ hai cluster production có các nhãn giống nhau nên kết quả truy vấn bị trộn khi nhân viên điều tra sự cố của một cluster cụ thể.
Trong mô hình đa vùng, mỗi collector tự ghi label region khác nhau về cách viết như ap-south và AP_SOUTH; Grafana hiển thị hai nhóm riêng cho cùng vùng nên dashboard tổng hợp không chính xác.
Một tổ chức dùng nhãn app lấy từ Kubernetes metadata nhưng nhiều nhóm triển khai không khai báo nhãn này nhất quán; một phần log bị gắn app=unknown và không xuất hiện trong trang vận hành theo từng service.
Đội SRE đổi tên label application thành service_name trong pipeline Alloy nhưng các dashboard và cảnh báo Loki vẫn lọc theo tên cũ; log vẫn được nhận đều nhưng biểu đồ hiển thị không có dữ liệu sau triển khai.
Một ứng dụng được chia thành nhiều container trong cùng pod gồm web, sidecar và worker; collector chỉ phân biệt pod mà không phân biệt container nên log lỗi network bị hiểu nhầm là do ứng dụng Java.
Nền tảng có batch job chạy vài giây rồi pod bị xóa; DaemonSet collector không đọc kịp log trước khi container runtime dọn tập tin khiến những lần chạy thất bại hiếm không để lại đủ bằng chứng.
Một dịch vụ chạy trên Kubernetes có pod CrashLoopBackOff; log của lần khởi động hiện tại được thu thập nhưng log ngay trước lần restart quan trọng lại không được tìm thấy, khiến đội SRE khó xác định lỗi khởi tạo.
Nhóm triển khai Alloy đọc log từ cả Kubernetes API và tệp trên node cho cùng một workload; mỗi dòng log được đẩy hai lần khiến số lỗi trong LogQL tăng gấp đôi so với số request thất bại thực tế.
Một cluster dùng nhiều DaemonSet thu thập log trong giai đoạn chuyển từ agent cũ sang Alloy; hai collector cùng đọc một vị trí và log xuất hiện lặp trong Loki mà không có dấu hiệu cho biết nguồn bị nhân đôi.
Doanh nghiệp triển khai Alloy dạng Deployment tập trung để đọc log pod trên toàn cluster, nhưng một số đường dẫn log chỉ tồn tại trên filesystem của từng node; collector trung tâm không thấy dữ liệu của nhiều workload.
Một worker xử lý dữ liệu ghi log vào thư mục được mount trên persistent volume; đội vận hành đổi collector sang đọc file tail nhưng sau khi xoay file, các dòng mới không được nhận dù file log trên volume vẫn tăng.
Một ứng dụng Java sử dụng log rotation đổi tên file mỗi giờ; cấu hình thu thập chỉ theo dõi một tên file cố định nên dữ liệu trong lúc chuyển file bị mất hoặc đọc lại nhiều lần sau restart collector.
Trong một lần node Kubernetes đầy đĩa, kubelet và container runtime xóa các tệp log cũ trước khi Alloy kịp gửi; đội quản trị phát hiện thiếu log ngay giai đoạn ứng dụng tăng lỗi 500.
Một nhóm cài Alloy và bắt đầu đẩy log qua HTTP tới Loki, nhưng Loki trả 429 khi ingestion chạm giới hạn; backlog trong collector tăng và dữ liệu hiển thị trễ so với thời điểm xảy ra lỗi.
Một cluster có kết nối tới Loki bị gián đoạn 20 phút; collector lưu được một phần log tạm thời nhưng sau khi phục hồi vẫn thiếu các dòng cuối, buộc SRE đánh giá bộ đệm và giới hạn tài nguyên của luồng thu thập.
Doanh nghiệp chạy Loki trong mạng riêng với chứng chỉ TLS tự cấp; Alloy không tin CA của endpoint ghi log nên kết nối push thất bại dù kiểm tra DNS và TCP từ pod vẫn thành công.
Một tổ chức chuyển Loki gateway sang hostname mới nhưng cấu hình Alloy vẫn giữ URL cũ; một số collector tiếp tục gửi vào cụm trước, khiến log truy vấn ở Grafana của cụm mới bị thiếu không theo quy luật.
Một nền tảng yêu cầu xác thực khi đẩy log; sau khi luân chuyển credential ở proxy trước Loki, các collector bắt đầu nhận 401 nhưng Grafana vẫn hiển thị log lịch sử và không có cảnh báo riêng cho mất ingest, gây chậm phát hiện gián đoạn thu thập.
Nhóm vận hành thêm cổng ghi log mới vào firewall nhưng chỉ mở từ namespace ứng dụng, không mở từ namespace collector; log của ứng dụng vẫn xuất stdout nhưng Alloy không kết nối được tới Loki.
Một service ghi log với timestamp từ thiết bị IoT bị lệch đồng hồ hai ngày; Loki từ chối nhiều dòng do thời gian quá cũ hoặc ngoài cửa sổ cho phép, khiến biểu đồ không phản ánh lượng sự kiện đã gửi.
Một pipeline nhận log từ nhiều node có đồng hồ không đồng bộ; các dòng thuộc cùng stream đến sai trật tự thời gian và một phần bị từ chối, khiến nhân viên trực không thể dựng chuỗi sự cố.
Đội phát triển chuyển định dạng timestamp từ ISO 8601 có timezone sang chuỗi không có timezone; collector phân tích thời gian theo mặc định khác làm log hiện lệch nhiều giờ trong Grafana.
Một ứng dụng phát log JSON nhưng vài dòng chứa dấu nháy không được escape do dữ liệu người dùng; stage parse JSON của Alloy không nhận các dòng đó và những trường quan trọng biến mất khỏi metadata.
Một nhóm cấu hình Alloy chỉ chuyển tiếp log có level WARN trở lên; trong lúc điều tra một lỗi retry, các dòng INFO mô tả chuyển trạng thái đã bị loại tại collector và không thể lấy lại từ Loki.
Một ứng dụng ghi thông tin giao dịch vào log multiline không theo mẫu bắt đầu thống nhất; parser gộp nhầm exception của request này với message của request khác làm việc điều tra nguyên nhân sai lệch.
Đội vận hành dùng pipeline redaction che giá trị access_token trong log JSON, nhưng token còn xuất hiện trong URL và stack trace dạng văn bản; dữ liệu nhạy cảm vẫn tới Loki sau khi chính sách bảo mật được công bố.
Một tập đoàn quy định bỏ trường email trước khi lưu log tập trung; ứng dụng cũ phát email trong message tự do nên pipeline chỉ xóa được trường JSON, khiến việc tuân thủ cần kiểm tra cả nội dung không cấu trúc.
Một service ghi log theo chuẩn logfmt, trong khi Alloy đang dùng stage xử lý JSON; các nhãn level và service lấy được từ ứng dụng Java mới nhưng biến mất ở service cũ, làm dashboard đánh giá sai tỷ lệ lỗi.
Một ứng dụng Kotlin ghi exception dưới dạng JSON có trường nested, nhưng pipeline chỉ trích xuất các trường cấp cao nhất; truy vấn lỗi theo mã exception không tìm ra những sự kiện thực sự chứa mã đó.
Một pipeline thu thập trích xuất nhãn HTTP path nguyên vẹn; path chứa UUID và mã khách hàng nên stream cardinality tăng mạnh dù đội thiết kế nghĩ route giữa các service chỉ có vài mẫu cố định.
Đội SRE muốn so sánh số lỗi theo HTTP route nhưng ứng dụng chỉ ghi URL thực tế chứa ID động; nếu dùng URL làm nhãn, lượng stream tăng bất thường và biểu đồ bị chia theo từng bản ghi.
Một nhóm thu thập Kubernetes labels từ tất cả nhãn pod một cách tự động; nhãn deployment revision và commit hash liên tục thay đổi, làm các stream được tái tạo nhiều lần qua từng rollout.
Nền tảng thêm label build_id và git_sha để tra lỗi theo phiên bản; với hàng trăm deployment mỗi ngày và nhiều service, số tổ hợp nhãn tăng nhanh khiến hiệu năng truy vấn lịch sử suy giảm.
Một đội vận hành dùng nhãn error_code có hàng nghìn giá trị từ hệ thống đối tác; dashboard truy vấn từng mã dễ dàng nhưng cluster Loki gặp áp lực index và truy vấn không còn theo kịp giờ cao điểm.
Một doanh nghiệp có nhiều cluster chia sẻ Loki; một cluster không gửi label namespace trong khi các cluster khác có, khiến quy tắc quyền truy cập và dashboard theo namespace bỏ sót một phần log.
Nhóm chuyển trace_id và request_id khỏi indexed labels sang structured metadata để giảm cardinality; các truy vấn Grafana cũ chỉ dùng selector label nên không tìm thấy log dù dữ liệu mới vẫn được lưu.
Đội phát triển lưu order_id trong structured metadata nhưng phiên bản pipeline cũ của một vài collector bỏ qua metadata này; truy vấn theo mã đơn chỉ thấy những pod mới và gây nghi ngờ mất log ở backend.
Một dịch vụ Java ghi log nhiều trường dưới dạng JSON, nhưng collector đưa tất cả trường vào label thay vì giữ ở nội dung; bộ nhớ ingester tăng mạnh dù tổng dung lượng log lưu trữ không khác trước.
Một hệ thống chọn nhãn namespace, app và level, nhưng một service có lưu lượng cực lớn đều là INFO; nhiều byte đổ vào ít stream nóng khiến một số ingester chịu tải không đều so với toàn cụm.
Một nhóm đặt label instance bằng địa chỉ IP để chia log theo máy; khi pod có nhiều replica được thay thường xuyên, biểu đồ phân tích dài hạn thiếu sự ổn định dù tên service không đổi.
Ứng dụng ghi log mức ERROR với stack trace dài vài chục kilobyte; sau khi chuyển sang JSON và bổ sung context, một số dòng vượt giới hạn kích thước ingestion, khiến log của lỗi nặng lại không vào Loki.
Một nhóm bổ sung dữ liệu debug chứa cả body của request cho mỗi event thanh toán; chi phí Loki tăng gấp mười trong một tuần mặc dù số giao dịch không đổi, khiến đội vận hành phải xác định nguồn tăng byte.
Một dịch vụ streaming ghi log mỗi lần nhận một phần dữ liệu nhỏ; một số pod tạo hàng triệu dòng mỗi giờ làm collector và Loki nghẽn, trong khi các dịch vụ khác không còn đủ tài nguyên gửi log.
Một công ty đặt mức sampling log INFO thấp để giảm chi phí; sau một sự cố hiếm, các dòng chuyển trạng thái quan trọng không được lưu nên đội SRE không thể tái dựng toàn bộ giao dịch.
Nhóm phát triển cho phép bật DEBUG từ cấu hình trung tâm trong 30 phút, nhưng khi kết thúc sự cố quên tắt tại một vài pod; lượng log tăng dai dẳng mà không có thông tin rõ service nào đang gây chi phí.
Một node Kubernetes chạy nhiều workload tạo log có tốc độ rất khác nhau; collector áp cùng một giới hạn CPU cho mọi node nên node tải lớn bị trễ hàng phút trong khi các node khác vẫn bình thường.
Đội vận hành nâng cấp Alloy đồng loạt trên cluster; quá trình restart làm gián đoạn đọc log trong một đợt lỗi sản xuất và nhóm cần phân biệt sự kiện thực sự không phát sinh với sự kiện chưa được thu thập.
Một cụm có Alloy agent gửi log sang hai hệ thống lưu trữ trong giai đoạn migration; luồng thứ hai chậm kéo theo bộ nhớ collector tăng và thời gian log xuất hiện ở Loki đầu tiên cũng tăng.
Một hệ thống dùng relabel trong Alloy để chuẩn hóa tên label của Kubernetes; sau thay đổi, label service rỗng trên một nhóm pod khiến Loki gom log vào stream chung và nhóm ứng dụng không còn truy vấn được log của mình.
Một platform team chuyển các collector sang cấu hình dùng chung qua GitOps; một namespace có yêu cầu giữ log audit đặc biệt nhưng bị pipeline chung loại bỏ mức INFO và mất các sự kiện bắt buộc.
Nền tảng ghi log ứng dụng Java xuống tệp lẫn stdout; do hai nguồn cùng được thu thập mà không có quy tắc loại trùng, một lỗi kinh doanh được đếm thành hai sự kiện và gây cảnh báo giả.
Một bộ log có nhiều dòng health-check lặp với tần suất cao; đội SRE muốn giảm dữ liệu không hữu ích nhưng chưa biết mức độ lọc nào vẫn giữ đủ bằng chứng khi health-check bất ngờ thất bại.
Một doanh nghiệp thu thập log từ cả máy ảo Linux và Kubernetes; format trường hostname và service không đồng nhất khiến Grafana Explore chỉ tìm được một phần lỗi theo cùng truy vấn LogQL.
Một ứng dụng trên máy ảo ghi systemd journal trong khi nhóm đã cài Alloy chỉ tail file; lỗi crash của service không xuất hiện trong Loki dù journal có đầy đủ thông tin.
Một hệ thống chạy Alloy trên node được bảo vệ bởi chính sách filesystem chỉ đọc; pipeline không lưu được trạng thái đọc file như dự kiến nên sau restart một số đoạn log bị phát lại hoặc bỏ sót.
Nhóm phát triển kiểm tra luồng bằng cách tìm một log vừa phát ra; dòng này hiển thị sau năm phút trong Grafana và người trực cần xác định độ trễ nằm ở ứng dụng, collector, ingest hay truy vấn.
Một kỹ sư truy vấn LogQL bằng cách quét toàn bộ log production rồi mới lọc chuỗi lỗi; truy vấn chạy nhiều phút trong khi cùng mã lỗi chỉ phát sinh ở một service, khiến đội SRE cần đánh giá phạm vi stream được chọn ban đầu.
Một đội dùng selector LogQL có label app nhưng nhãn thực tế ở Loki là service_name; dashboard không hiển thị log nào dù Grafana Explore vẫn tìm thấy sự kiện khi bỏ bộ lọc label.
Ứng dụng có cả log chứa từ ERROR trong message thông tin và log level=ERROR ở JSON; một truy vấn lọc chuỗi ERROR đếm sai số lỗi nghiệp vụ so với dashboard dựa trên trường level đã được parse.
Một dịch vụ thanh toán ghi log JSON với trạng thái lỗi nằm trong trường result.code; nhóm viết truy vấn LogQL lọc theo chuỗi 500 nhưng vô tình khớp cả mã đơn hàng chứa 500 và tạo biểu đồ sai.
Đội phát triển dùng bộ lọc regex LogQL trên mọi log để tìm endpoint có mã động; truy vấn vào dữ liệu 30 ngày rất chậm, trong khi phần lớn log cần phân tích chỉ thuộc một namespace nhất định.
Một truy vấn LogQL parse JSON từng dòng và tìm trace_id; một phần log cũ là văn bản thuần nên parser báo lỗi và kết quả chỉ chứa dữ liệu sau ngày thay đổi format.
Một nhóm sử dụng stage pattern để tách đường dẫn, status và độ trễ từ log access; khi reverse proxy đổi bố cục message, các trường bị trích xuất sai và histogram độ trễ trên dashboard mất dữ liệu.
Nền tảng Java ghi trường latency_ms là chuỗi có đơn vị ms, không phải số thuần; truy vấn LogQL unwrap để tính phân phối độ trễ không chuyển đổi được một phần log và nhóm SRE phải giải thích sự sai lệch giữa số request và số mẫu hợp lệ.
Một API ghi duration theo mili giây nhưng dashboard LogQL diễn giải thành giây; biểu đồ latency tăng gấp một nghìn lần sau khi nâng cấp parser dù phản hồi thực tế không chậm hơn.
Một ứng dụng có log thời gian xử lý cho từng request; đội vận hành dùng count_over_time trên các dòng log để ước lượng số request nhưng một request có thể tạo nhiều dòng, khiến tỷ lệ lỗi trên dashboard không đúng.
Nhóm SRE tính số lỗi mỗi phút từ log ERROR, nhưng một exception được ghi cả ở controller lẫn HTTP filter; count_over_time ghi nhận hai lỗi cho một request thất bại và cảnh báo bị kích hoạt sớm.
Một dịch vụ chỉ ghi log khi lỗi mà không ghi số request thành công; đội phát triển muốn dùng LogQL tính error rate phần trăm theo request nhưng không có dữ liệu mẫu số phù hợp trong cùng nguồn log.
Đội vận hành dùng rate trên dòng log để ước lượng tốc độ giao dịch; một release giảm log INFO làm biểu đồ traffic sụt 70% dù lượng request thật không thay đổi.
Một nhóm viết truy vấn sum by status trên trường status sau parse JSON, nhưng một số service ghi http_status; biểu đồ chỉ tính dữ liệu của một nửa ứng dụng và bỏ qua các dịch vụ còn lại.
Một hệ thống muốn xem p95 thời gian xử lý từ log JSON nhưng có vài dòng timeout không ghi duration; kết quả quantile_over_time loại bỏ những request xấu nhất nên tỷ lệ chậm thực tế bị đánh giá thấp.
Một dashboard Loki tính số lượt login theo username đã trích xuất từ log và nhóm theo từng username; trong chiến dịch có hàng triệu tài khoản, truy vấn tạo quá nhiều chuỗi kết quả và làm giao diện Grafana không phản hồi.
Nhóm phát triển muốn so sánh số lỗi theo từng route HTTP; log chỉ chứa path có ID động khiến kết quả group by tạo hàng chục nghìn chuỗi thay vì một danh sách route có ý nghĩa.
Một người trực tìm mã đơn bằng biểu thức LogQL có bộ lọc label order_id nhưng trường này chỉ nằm trong structured metadata; truy vấn không có kết quả và nhóm nghi ngờ sự kiện thanh toán đã bị mất.
Đội vận hành kết hợp selector và filter nội dung bằng nhiều điều kiện, nhưng thứ tự filter khiến lượng dòng phải parse quá lớn; cùng câu hỏi nghiệp vụ có thể mất vài giây hoặc vài phút tùy cách truy vấn.
Một kỹ sư muốn tìm stack trace chứa chuỗi NullPointerException; Loki lưu sự kiện trên nhiều dòng tách rời nên truy vấn chỉ thấy dòng ngoại lệ mà không có các frame và ngữ cảnh request cùng bản ghi.
Một công ty sử dụng LogQL để phát hiện lỗi theo chuỗi tiếng Việt có dấu; khi ứng dụng thay encoding hoặc chuẩn Unicode, truy vấn khớp ít kết quả hơn thực tế và nhân viên trực không xác định được lý do.
Một đội xây dashboard cho mười namespace, mỗi panel dùng truy vấn Loki riêng với khoảng thời gian 30 ngày; khi mở dashboard, nhiều truy vấn chạy đồng thời và các dịch vụ khác cũng bị chậm tìm kiếm log.
Một người dùng Grafana Explore chọn khoảng thời gian toàn bộ 90 ngày và chỉ tìm chuỗi ERROR không giới hạn app; Loki truy xuất lượng lớn object storage, khiến chi phí đọc và độ trễ tăng mạnh.
Một ứng dụng có log bị phát trễ do collector mất mạng; khi xem biểu đồ theo event timestamp và theo ingestion time, số sự kiện trong khoảng sự cố khác nhau khiến đội SRE khó đánh giá diễn biến.
Nhóm phân tích truy vấn lỗi ngay sau deploy nhưng bảng Grafana chọn timezone và range không tương ứng với thời điểm log được ghi; đội phát triển kết luận không có lỗi dù log đã ở Loki.
Một dashboard dùng biến namespace và service_name nhưng giá trị dropdown chỉ được lấy từ nhãn xuất hiện gần đây; một service ít hoạt động không hiện trong danh sách dù log lịch sử vẫn tồn tại.
Nền tảng đa tenant có nhiều tổ chức dùng chung datasource Loki; bộ lọc tenant trong biến dashboard chỉ ảnh hưởng giao diện, nhưng một người dùng đổi truy vấn thủ công và đọc được log tổ chức khác.
Một kỹ sư tạo link từ log Grafana sang trace bằng trace_id, nhưng các service ghi trường traceId hoặc trace_id khác nhau; chỉ một số dòng có khả năng mở trace trực tiếp mặc dù dữ liệu cùng một collector.
Đội sản phẩm muốn nhảy từ trace OpenTelemetry sang các log liên quan trong Grafana; log của service backend chứa trace_id ở nội dung nhưng datasource trace không biết cách dựng truy vấn Loki thích hợp.
Trong quá trình điều tra một lỗi Java, đội SRE thấy log ERROR nhưng không tìm thấy trace tương ứng; trace bị sampling loại bỏ trong khi log được giữ toàn bộ, tạo hiểu lầm rằng hệ thống propagation bị hỏng.
Một công ty cho phép nhiều team tự tạo dashboard LogQL; một truy vấn chưa tối ưu của một nhóm làm cluster Loki bị bão hòa và ảnh hưởng việc tìm log của team trực production.
Nhóm Grafana chia sẻ dashboard công khai chứa các panel log mẫu; một số message có email và mã giao dịch bị hiển thị cho người không có quyền xem log nguồn, khiến đội bảo mật phải đánh giá quyền truy cập dashboard.
Một ứng dụng ghi lỗi thanh toán bằng tiếng Anh nhưng service thông báo ghi cùng lỗi bằng tiếng Việt; dashboard đếm từ khóa error bỏ sót một bên và số liệu sự cố giữa hai dịch vụ không nhất quán.
Một tổ chức định tuyến cảnh báo từ LogQL khi xuất hiện chuỗi OUT_OF_STOCK; sau chiến dịch bán hàng, các yêu cầu hợp lệ hết hàng làm pager liên tục reo dù không có sự cố hệ thống.
Nền tảng thanh toán tạo cảnh báo khi số dòng ERROR vượt ngưỡng trong năm phút; một release thay đổi mức log từ WARN thành ERROR làm cảnh báo tăng mạnh dù tỷ lệ giao dịch thất bại thực tế không đổi.
Một đội SRE dùng log để cảnh báo chứng từ phát hành thất bại nhưng chỉ có rất ít giao dịch ban đêm; một lỗi đơn lẻ có giá trị lớn cần xử lý ngay nhưng rule theo số lượng tuyệt đối không kích hoạt.
Ứng dụng quản lý đơn hàng có log cảnh báo khi backfill thất bại; rule LogQL được tạo nhưng các bộ lọc nhãn không khớp dữ liệu production nên Alerting UI hiển thị trạng thái no data trong lúc lỗi vẫn xảy ra.
Đội phát triển viết rule ghi nhận số lần login thất bại từ log và kích hoạt theo user_id; trong giờ cao điểm, số lượng nhóm cảnh báo tăng đột biến khiến hệ thống thông báo và truy vấn Loki bị quá tải.
Một hệ thống dùng LogQL tạo metric suy ra từ log để cảnh báo tỷ lệ lỗi, nhưng đội SRE không có metric request tổng thể để làm mẫu số; cảnh báo từ log không thể phản ánh chính xác tỷ lệ thất bại khách hàng.
Nền tảng xuất một phần log audit sang Loki với độ trễ ingest vài phút; alert kiểm soát gian lận cần phát hiện dưới 30 giây nên đội kiến trúc phải đánh giá liệu nguồn log hiện tại đáp ứng được SLA cảnh báo hay không.
Một dashboard Grafana dùng truy vấn count_over_time cho tất cả lỗi từ mỗi tenant; khi một tenant gửi lượng log rất lớn, panel báo sự cố diện rộng dù các tenant khác hoạt động bình thường.
Một công ty tạo alert Loki về mất log từ payment service; service hoàn toàn ngừng hoạt động nên không có dòng log mới, nhưng rule chỉ tìm ERROR không vượt ngưỡng và không phát hiện tình trạng im lặng.
Một hệ thống LogQL truy vấn số lượng log mỗi phút để phát hiện mất collector; hoạt động nghiệp vụ vốn không có request vào đêm khuya nên cảnh báo sai khi log hợp lệ không phát sinh.
Một nền tảng muốn dùng log rate làm cảnh báo hiệu năng JVM; mức DEBUG tăng do thay đổi cờ log khiến log rate tăng đột biến mà CPU và độ trễ ứng dụng vẫn bình thường.
Đội vận hành tạo recording rule từ LogQL cho dashboard toàn công ty; biểu thức chưa hạn chế tenant và quét quá nhiều dữ liệu mỗi lần đánh giá, làm tăng tải nền liên tục trên cluster Loki.
Một service chạy trong cụm single-binary Loki cho môi trường nhỏ; khi doanh nghiệp mở rộng gấp mười, cả ingestion và query tranh chấp cùng CPU và RAM khiến người dùng mất khả năng tìm log trong giờ tải cao.
Một nền tảng chuyển Loki sang kiến trúc phân tán với distributor, ingester và querier; sau khi mở rộng nhóm querier, tốc độ tìm log không tăng vì object store và scheduler truy vấn đang là điểm nghẽn.
Đội SRE thấy chỉ một số ingester gần đầy bộ nhớ trong khi tổng cụm còn tài nguyên; các stream nóng từ một ứng dụng INFO lưu lượng lớn tạo tải mất cân đối và nguy cơ từ chối ingest.
Một doanh nghiệp triển khai nhiều Loki ingester có replication để tăng khả năng sẵn sàng; khi một node mất điện ngay sau đợt lỗi sản xuất, một phần log mới nhất không tìm thấy và nhóm cần điều tra cơ chế bền vững dữ liệu.
Trong lúc restart Loki ingester, dữ liệu log đang nằm trong bộ nhớ chưa được flush lên object storage; nhóm quản trị thấy khoảng trống log và phải kiểm tra WAL cùng quá trình khôi phục sau sự cố.
Một cluster Loki chạy filesystem local làm nơi chứa chunk nhưng các pod ingester được đặt trên node bất kỳ; sau lần thay node, nhiều log lịch sử không truy xuất được dù component vẫn báo Ready.
Nền tảng đặt dữ liệu Loki vào object storage có bucket policy chỉ cho phép ghi; quá trình ingest có vẻ thành công nhưng querier không thể đọc chunk khi người trực xem dữ liệu cũ.
Doanh nghiệp thay khóa truy cập object storage dùng cho Loki và chỉ cập nhật một nhóm component; ingestion tiếp tục nhận log nhưng truy vấn dữ liệu cũ trả lỗi, khiến đội SRE cần kiểm tra quyền của từng thành phần.
Một hệ thống chia nhiều bucket cho staging và production nhưng cấu hình object storage trỏ nhầm chung một bucket; chi phí tăng và đội tuân thủ lo ngại phạm vi lưu giữ, truy cập không còn tách biệt.
Đội vận hành triển khai Loki với backend object storage ở vùng xa cluster; request ghi log vẫn ổn nhưng tìm kiếm dữ liệu 30 ngày có độ trễ cao và chi phí truyền dữ liệu liên vùng đáng kể.
Một doanh nghiệp muốn giảm chi phí bằng cách dùng storage class lạnh cho toàn bộ object của Loki; truy vấn log tuần trước trở nên rất chậm và một số object không truy xuất ngay được theo yêu cầu điều tra.
Hệ thống log có lưu giữ 30 ngày theo chính sách, nhưng dữ liệu cũ hơn vẫn còn trong bucket; nhóm pháp chế cần xác định vì sao cấu hình retention trong Loki và vòng đời object storage chưa cùng có hiệu lực.
Một đội thiết lập retention một ngày để giảm chi phí nhưng log audit phải giữ 180 ngày; chính sách chung xóa cả dữ liệu cần kiểm toán và gây thiếu bằng chứng trong đợt đối soát.
Một nền tảng yêu cầu giữ log ERROR lâu hơn log DEBUG, nhưng log của cả hai loại nằm chung cấu trúc label không phù hợp với việc áp retention riêng; nhóm thiết kế phải đánh giá phân loại dữ liệu từ khi ingest.
Đội vận hành thấy compactor Loki gặp lỗi sau khi thay quyền bucket; dữ liệu mới vẫn truy vấn được nhưng các log đã quá thời hạn không được dọn, làm phí lưu trữ tăng âm thầm.
Một công ty đặt lifecycle policy xóa object theo tuổi ở tầng lưu trữ trước thời hạn mà Loki kỳ vọng; dashboard lịch sử bắt đầu báo lỗi đọc chunk và kết quả truy vấn không còn đầy đủ.
Một ứng dụng gửi nhiều triệu dòng log mỗi ngày và đội hạ tầng thay đổi kỳ hạn lưu từ 7 sang 90 ngày; tổng dung lượng tăng nhanh nhưng chưa có dự báo từ byte ingest, nén và khả năng sử dụng thực tế.
Một nền tảng chỉ yêu cầu log production lưu 60 ngày còn staging 7 ngày; collector không gắn nhãn môi trường ổn định nên việc áp retention riêng trở nên khó kiểm chứng.
Đội SRE kích hoạt retention theo tenant nhưng một số log bị gửi với tenant ID mặc định do lỗi gateway; dữ liệu của nhóm đó bị áp thời hạn lưu khác hợp đồng mà không có cảnh báo.
Một doanh nghiệp nhận yêu cầu xóa dữ liệu cá nhân theo luật nhưng log cũ đã được lưu trong object storage và cache truy vấn; nhóm phụ trách cần đánh giá quy trình xóa dữ liệu, thời gian hiệu lực và khả năng kiểm chứng.
Nền tảng lưu log bảo mật không được chỉnh sửa nhưng đội vận hành xem Loki như kho lưu trữ pháp lý bất biến; một thay đổi policy và thời hạn retention làm dữ liệu mất trước kỳ kiểm toán, khiến phạm vi đảm bảo của hệ thống bị đặt dấu hỏi.
Một cụm Loki sử dụng index và chunk trên object storage; sau khi cập nhật schema lưu trữ mà chưa đánh giá dữ liệu cũ, truy vấn lịch sử bị lỗi trong khi dữ liệu mới vẫn tìm được.
Nhóm vận hành tăng parallelism của truy vấn Loki để giảm độ trễ; khi nhiều người cùng mở Grafana Explore, số request tới object storage tăng đột biến và giới hạn backend bị chạm.
Một user truy vấn rộng trên 180 ngày và Loki trả lỗi vì vượt số lượng entry hay thời lượng truy vấn cho phép; người dùng nghĩ log đã bị xóa dù các khoảng thời gian ngắn vẫn trả dữ liệu đúng.
Đội SRE thấy querier CPU thấp nhưng truy vấn LogQL vẫn chậm; số lượng stream rất lớn khiến việc tìm và đọc các chunk phù hợp tốn thời gian trước khi xử lý lọc nội dung.
Một ứng dụng tạo hàng chục nghìn stream có rất ít byte mỗi stream; ingester flush các chunk nhỏ và lưu trữ tăng nhiều object, khiến chi phí thao tác object store lớn dù dung lượng nén không quá cao.
Một nhóm đặt cache kết quả truy vấn phía trước Loki nhưng dashboard cần hiển thị sự kiện mới trong vài giây; dữ liệu hiển thị chậm hơn thực tế vì cache được sử dụng trong khoảng truy vấn gần hiện tại.
Một hệ thống tăng số replica query frontend để phục vụ nhiều người dùng nhưng nghẽn vẫn nằm ở truy vấn LogQL quét dữ liệu không có selector hợp lý; thời gian phản hồi tiếp tục vượt SLA.
Một doanh nghiệp bật auto-scaling cho nhóm ingester theo CPU nhưng không theo bộ nhớ và số stream; trong đợt tăng cardinality, pod bị OOM trước khi HPA kịp mở rộng.
Một nền tảng có mức byte ingest tăng gấp đôi sau đợt phát hành Java mà không tăng số request; đội SRE phải tách chi phí log mức DEBUG, stack trace dài, labels và dữ liệu lặp để xác định nguyên nhân.
Đội quản trị muốn tính chi phí Loki theo namespace nhưng nhiều dòng log không mang nhãn namespace hợp lệ; bảng phân bổ chi phí dồn phần lớn byte vào nhóm unknown và các team phản đối báo cáo.
Một công ty giới hạn lượng log mỗi tenant để bảo vệ cụm dùng chung; khi tenant lớn vượt ngưỡng, các request đẩy log bị từ chối và nhóm SRE cần đánh giá tác động lên khả năng điều tra sự cố của chính tenant đó.
Nền tảng dùng một địa chỉ Loki chung cho nhiều khách hàng nhưng không có tầng xác thực và ánh xạ tenant đáng tin cậy; client tự cung cấp tenant header và có nguy cơ ghi hoặc đọc nhầm dữ liệu tổ chức khác.
Đội bảo mật triển khai reverse proxy xác thực trước Loki nhưng proxy chuyển tiếp tenant ID do client gửi mà không kiểm tra danh tính; một người dùng có thể thay tenant ID và truy vấn log thuộc tổ chức khác.
Một tổ chức đặt nhiều datasource Loki tương ứng từng tenant trong Grafana nhưng phân quyền datasource và folder dashboard không thống nhất; một dashboard được chia sẻ rộng chứa truy vấn log khách hàng khác, gây lo ngại về phạm vi dữ liệu người xem có thể truy cập.
Nền tảng mở API truy vấn Loki qua ingress công khai để đối tác đọc log; sau khi phát hành, các truy vấn không giới hạn khối lượng làm chi phí object storage tăng và có nguy cơ lộ log nội bộ.
Một công ty bật multi-tenancy nhưng quên cấu hình đúng tenant header ở một số Alloy agent; nhiều service bị trộn vào tenant mặc định và những tenant hợp lệ thấy thiếu log dù collector báo đã push thành công.
Trong một đợt thay đổi thông tin định danh khách hàng, cùng dịch vụ được gửi qua hai tenant ID khác nhau; truy vấn log cho một incident phải tìm ở hai không gian riêng khiến việc ghép lịch sử xử lý rất khó.
Một tổ chức có yêu cầu phân quyền đến mức namespace trong cùng tenant Loki; đội quản trị chỉ dựa vào bộ lọc dashboard mà không kiểm soát đường truy vấn dữ liệu, khiến nhân viên có thể xem log team khác.
Một khách hàng yêu cầu log của họ phải lưu tại vùng dữ liệu riêng, nhưng gateway định tuyến request ghi theo label region không được xác thực; log của một số tenant tới bucket nằm ngoài khu vực hợp đồng.
Nền tảng truyền dữ liệu nhạy cảm qua log JSON và cho phép LogQL parse trường email trong dashboard; bộ phận an ninh phát hiện một query không có kiểm soát quyền phù hợp đã trả dữ liệu cá nhân từ nhiều service.
Một tổ chức ghi log audit phải được bảo vệ trong quá trình truyền; sau khi cài Alloy, một nhánh gửi log đến gateway Loki qua HTTP rõ trên mạng chia sẻ, gây rủi ro quan sát trái phép trong lúc chuyển dữ liệu.
Nhóm vận hành bật TLS giữa Grafana và Loki nhưng quên bảo vệ kết nối giữa Alloy và gateway nhận log; kết quả dashboard vẫn bình thường nên kiểm tra hời hợt không phát hiện đoạn truyền không mã hóa.
Đội SRE xây alert nếu số lượng log ERROR tăng đột biến, nhưng lỗi đường ingest khiến log không tới Loki; dashboard vẫn hiển thị dữ liệu cũ và alert không thể đánh thức người trực khi ứng dụng thất bại.
Một hệ thống có exporter báo Alloy hoạt động nhưng hàng đợi gửi log ngày càng đầy; nhóm trực chưa có cảnh báo về lag hoặc drop của pipeline nên nghĩ mọi log đã được thu thập đúng hạn.
Nền tảng quan sát có cả metrics Prometheus và log Loki; khi log pipeline lỗi, metrics HTTP 5xx vẫn tăng nhưng dashboard log trống, khiến người trực cần phân biệt ứng dụng không ghi lỗi với collector bị hỏng.
Một service dùng Grafana alert rule dựa trên LogQL cho lỗi thanh toán; sau khi thay cấu trúc trường JSON, rule không còn đếm sự kiện dù Grafana Explore vẫn thấy log, và pipeline triển khai chưa có bài test nào phát hiện.
Một tổ chức kiểm thử Loki bằng cách phát một dòng canary log theo lịch trên từng cluster; một cluster không hiện canary sau đợt nâng cấp Alloy dù các metric tài nguyên đều khỏe, đòi hỏi điều tra toàn tuyến dữ liệu.
Đội nền tảng phát hành cấu hình log pipeline bằng GitOps nhưng thay đổi cùng lúc cả labels, drop rules và tenant routing; sau triển khai, số byte ingest giảm mạnh và không biết do tiết kiệm hợp lệ hay mất dữ liệu bắt buộc.
Một công ty sử dụng log giao dịch để điều tra số tiền hoàn trả; ứng dụng ghi cùng sự kiện tại producer và consumer nhưng không có event ID nhất quán, khiến đội phân tích nhầm hai log thành hai giao dịch.
Trong một sự cố Kubernetes, nhân viên trực chỉ tra log của pod đang Running và bỏ qua log của pod đã bị xóa; các dòng lỗi ở phiên bản trước có trong Loki nhưng dashboard mặc định không chọn được nhãn pod cũ.
Một nền tảng triển khai Java OpenTelemetry tracing song song với Loki; khi khách cung cấp trace ID để hỗ trợ, nhóm SRE phải quét log toàn cụm vì trace ID chưa được chuẩn hóa trong JSON và structured metadata.
Doanh nghiệp thu thập log dịch vụ liên quan tới tài khoản khách hàng trên nhiều vùng; cùng một yêu cầu xuất hiện dưới trace ID thống nhất nhưng timestamp bị lệch và thông tin region khác nhau khiến đội SRE khó xác định thứ tự sự kiện.
Một nền tảng đang cân nhắc chuyển hệ phân tích log toàn văn sang Loki; nhóm sản phẩm cần tìm kiếm tùy ý trong hàng trăm trường JSON của nhiều năm dữ liệu, trong khi nhóm vận hành chưa đánh giá mô hình index theo nhãn và chi phí quét.
Đội kỹ thuật triển khai Loki cho một ứng dụng nhỏ rồi mở rộng ra toàn doanh nghiệp mà không có giới hạn cardinality, ingestion hay truy vấn; một nhóm ứng dụng thử nghiệm có thể làm chậm việc điều tra sự cố production của mọi team.
Trong một cuộc diễn tập khôi phục thảm họa, bucket lưu chunk Loki còn nguyên nhưng thông tin cấu hình schema, index hoặc quyền truy cập không đầy đủ; cụm mới khởi động được nhưng không truy vấn lại log lịch sử để phục vụ điều tra.
Một công ty cần duy trì dashboard và alerting khi một vùng cloud ngừng hoạt động; Grafana đặt ở vùng dự phòng nhưng Loki và object storage đang ở vùng chính, khiến người trực không xem được log ngay khi cần nhất.

Một nhóm SRE đưa Prometheus và Alertmanager vào vận hành nhưng toàn bộ cảnh báo CPU, bộ nhớ và lỗi API đều gửi trực tiếp tới một kênh chung; trong giờ cao điểm, nhân viên trực không phân biệt được sự cố cần hành động ngay với cảnh báo ít khẩn cấp.
Prometheus hiển thị một alert đang ở trạng thái pending nhưng đội vận hành không thấy nó trong giao diện Alertmanager; người phụ trách kiểm tra receiver dù điều kiện cảnh báo chưa duy trì đủ thời gian để chuyển thành firing.
Một alert đã chuyển sang firing trong Prometheus nhưng không xuất hiện trên Alertmanager; Prometheus mới được chuyển sang môi trường khác và cấu hình địa chỉ Alertmanager chưa được cập nhật đồng bộ.
Hai Prometheus replica cùng đánh giá một rule cho cùng pod nhưng bộ external labels của chúng khác nhau ở nhãn replica; Alertmanager hiển thị hai bản cảnh báo tưởng như giống hệt nhau thay vì một bản đã được khử trùng lặp.
Đội hạ tầng định tuyến alert theo label team nhưng nhiều rule Prometheus cũ không có nhãn này; các cảnh báo rơi vào receiver mặc định và không đến người sở hữu dịch vụ.
Ứng dụng thanh toán đặt severity bằng giá trị critical còn một bộ rule cũ dùng mức page; route khẩn cấp chỉ khớp critical nên một nhóm lỗi nghiêm trọng bị chuyển tới kênh thông thường.
Một tổ chức dùng nhãn environment với giá trị prod, production và live trên các hệ thống khác nhau; route nhận cảnh báo production chỉ khớp một giá trị, khiến lịch trực nhận thông báo thiếu ổn định giữa các dịch vụ.
Alertmanager có route cha định tuyến theo team=payments và route con theo severity=critical; một thay đổi matcher ở cấp cha khiến cảnh báo critical của team khác không bao giờ được xét đến route con.
Nhóm vận hành thêm hai route con có điều kiện khớp chồng lấn cho cùng một alert; sau khi triển khai, cảnh báo chỉ đến một receiver dù đội phát triển tưởng cả hai kênh sẽ nhận.
Một cảnh báo sự cố bảo mật cần được gửi đồng thời đến đội an ninh và đội trực hạ tầng; cấu trúc cây route hiện tại khiến việc thêm receiver thứ hai làm kết quả định tuyến khác dự kiến.
Route được cấu hình bằng matcher regex cho nhiều team, nhưng tên team mới chứa dấu gạch ngang và không thuộc tập giá trị dự kiến; cảnh báo rơi vào nhánh mặc định dù nhãn team vẫn có mặt.
Một đội dùng matcher phủ định cho environment để bỏ cảnh báo môi trường thử nghiệm; các alert thiếu nhãn environment cũng được định tuyến theo cách không đúng giả định của người vận hành.
Alertmanager cấu hình receiver mặc định là hộp thư của quản trị viên đã nghỉ việc; khi một dịch vụ mới chưa có route riêng phát cảnh báo, không ai trong nhóm trực nhận được thông báo.
Công ty có ba vùng production, mỗi vùng có nhóm trực riêng; một route chỉ khớp service mà không xét region khiến lỗi ở vùng dự phòng được gửi đến đội ở vùng chính.
Trong giai đoạn đổi cơ cấu tổ chức, nhãn owner của nhiều alert được đổi từ team-platform sang team-infra; route cũ chưa chuyển đổi nên cùng loại sự cố được gửi sang hai quy trình xử lý khác nhau.
Một dịch vụ cần gửi warning qua email và critical qua kênh phân trang khẩn cấp; sau khi thêm route mới, một số cảnh báo warning cũng làm điện thoại người trực reo giữa đêm.
Trong đợt triển khai canary, alert từ phiên bản thử nghiệm và phiên bản ổn định có cùng alertname và service; đội vận hành không phân biệt được nhánh phát hành khi nhận thông báo tổng hợp.
Một người cập nhật cấu hình receiver ở route cha với kỳ vọng route con giữ người nhận riêng, nhưng sau reload các route con thiếu trường receiver bắt đầu dùng người nhận khác so với trước.
Nhóm dùng label pod trong group_by của Alertmanager; khi hàng trăm pod cùng lỗi, mỗi pod tạo một nhóm riêng và kênh chat nhận hàng trăm thông báo nối tiếp.
Một cảnh báo lỗi HTTP được gom theo alertname duy nhất trên toàn tổ chức; thông báo chỉ có tiêu đề chung và trộn lỗi của nhiều cluster, khiến người trực không biết sự cố thuộc khu vực nào.
Hệ thống gom alert theo service và cluster nhưng bỏ environment; các cảnh báo thử nghiệm và production xuất hiện chung một thông báo, làm người trực hiểu sai mức ảnh hưởng.
Nhóm chọn group_by bao gồm nhãn request_id biến đổi theo từng yêu cầu; số nhóm cảnh báo tăng mạnh cùng lưu lượng và tác dụng giảm nhiễu của Alertmanager gần như biến mất.
Một nhóm alerts có group_wait ngắn nên trong vài giây đầu sự cố, từng cảnh báo phụ thuộc được gửi ra riêng rẽ trước khi cảnh báo gốc xuất hiện trong cùng nhóm.
Đội trực chỉnh group_wait thành thời gian dài để giảm nhiễu; một cảnh báo ngừng nhận thanh toán nghiêm trọng chỉ được gửi sau nhiều phút dù đã firing ngay từ đầu.
Trong một sự cố vùng mạng, các alert mới cùng nhóm liên tục xuất hiện; nhóm chỉnh group_interval rất lớn khiến những vấn đề mới không được gửi tiếp trong khoảng người trực đang xử lý.
Một cảnh báo vẫn firing nhiều giờ nhưng không được nhắc lại như quy định on-call; repeat_interval và lịch trực chuyển ca chưa được đối chiếu với chu kỳ thông báo thực tế.
Đội vận hành giảm repeat_interval xuống vài phút cho tất cả receiver; một sự cố kéo dài làm kênh email nhận quá nhiều lời nhắc dù người trực đã xác nhận đang xử lý.
Vào giờ bảo trì, một alert biến mất trước khi hết group_wait và không có thông báo firing nào được gửi; nhóm trực cho rằng Alertmanager đã làm rơi dữ liệu vì vẫn thấy sự kiện ngắn ở Prometheus.
Nhóm thay group_by trong lúc đang có nhiều cảnh báo firing; người trực thấy các thông báo từ nhóm cũ và nhóm mới xuất hiện gần nhau sau reload, khó đối chiếu với trạng thái thực tế.
Các alert khác nhau chỉ ở phần annotation mô tả nhưng có cùng labelset; người trực tưởng đang có nhiều cảnh báo riêng biệt, trong khi Alertmanager hiển thị một alert với nội dung thay đổi.
Một rule Prometheus gắn pod UID vào labels của alert; sau mỗi lần pod được tạo lại, Alertmanager coi đây là cảnh báo mới và phát thêm thông báo dù vấn đề nghiệp vụ chưa thay đổi.
Trong đợt mất kết nối, cùng một alert được gửi lại qua nhiều lần batch từ Prometheus; đội vận hành muốn hiểu vì sao số lần nhận alert và số notification gửi tới receiver không tương ứng một-một.
Một alert đổi nhãn severity từ warning sang critical trong khi sự cố chưa khôi phục; Alertmanager ghi nhận thay đổi danh tính cảnh báo và quy trình trực nhận thông báo khác với lúc severity chỉ nằm trong annotation.
Alertmanager được đặt sau một load balancer chung nhưng hai instance có cấu hình route khác nhau; cùng một tập alert có lúc gửi tới Slack, lúc gửi email tùy instance tiếp nhận.
Khi nhiều node trong cùng rack mất điện, alert HostDown firing đồng thời với các alert mất kết nối ứng dụng; kênh trực nhận hàng trăm cảnh báo phụ thuộc dù nguyên nhân chung là mất nguồn điện.
Đội triển khai inhibition để alert ClusterDown che các alert ServiceUnavailable, nhưng hai alert có nhãn cluster không cùng giá trị nên cảnh báo phụ thuộc vẫn liên tục được gửi.
Một quy tắc inhibition giữa severity=critical và severity=warning đặt điều kiện equal theo service, nhưng nhiều warning thiếu nhãn service; kết quả che hoặc không che cảnh báo khiến đội vận hành bất ngờ.
Một nhóm tạo inhibition với source và target matcher có thể đồng thời khớp cùng một alert; các alert mức nghiêm trọng khác nhau không được che theo cách người viết chính sách dự kiến.
Đội đặt inhibition toàn cục giữa cảnh báo mất mạng và cảnh báo ứng dụng mà không đối chiếu region; khi một vùng mất mạng, cảnh báo ứng dụng ở vùng khác cũng không đến đúng người trực.
Ứng dụng thanh toán có alert DependencyDown và alert PaymentFailed cùng lúc; quy tắc inhibition che cả PaymentFailed dù mức ảnh hưởng tới khách hàng cần được thông báo riêng cho đội nghiệp vụ.
Nhóm thay đổi nhãn severity trong rule Prometheus nhưng quên cập nhật source matchers của inhibition; một đợt sự cố mới làm các thông báo phụ thuộc tràn ngập kênh trực.
Nhân viên trực tạo silence cho alert CPU cao trên một pod đang bảo trì; khi Deployment tạo pod mới, cảnh báo từ pod thay thế vẫn làm điện thoại reo vì matcher của silence gắn với tên pod cũ.
Một silence được tạo bằng matcher chỉ theo alertname, bỏ qua environment và team; trong lúc bảo trì staging, cảnh báo cùng tên trên production cũng không được chuyển tới receiver.
Nhóm trực tạo silence có thời hạn hai giờ nhưng quá trình bảo trì kéo dài qua đêm; thông báo bắt đầu xuất hiện trở lại khi silence hết hạn dù dịch vụ vẫn trong cửa sổ bảo trì.
Một silence dùng thời điểm bắt đầu theo múi giờ khác với lịch bảo trì địa phương; cảnh báo chỉ bị tắt sau khi ca bảo trì đã kết thúc.
Đội vận hành quên ghi lý do và người tạo cho nhiều silence; sau khi đổi ca, người trực mới không biết liệu cảnh báo bị ẩn do bảo trì hợp lệ hay do thao tác cũ chưa được dọn.
Một ca trực tạo nhiều silence có matcher chồng nhau cho cùng dịch vụ; sau khi hết hạn một silence, cảnh báo vẫn không được gửi và nhóm hiểu nhầm Alertmanager đang lỗi.
Trong lúc xử lý sự cố, nhân viên muốn tắt riêng cảnh báo nhiều nhiễu trong một giờ, nhưng thao tác silence nhầm vào cả alert ngừng thanh toán có severity=critical.
Đội phát triển cho rằng silence sẽ làm alert biến mất khỏi Prometheus; dashboard Prometheus vẫn hiển thị firing trong khi Alertmanager không gửi thông báo và hai nhóm đưa ra báo cáo trạng thái trái nhau.
Một hệ thống có cửa sổ bảo trì lặp mỗi cuối tuần; nhóm tạo silence thủ công mỗi lần và thường quên thao tác trong ca đêm, khiến các đợt bảo trì định kỳ vẫn gây báo động.
Đội áp dụng mute_time_intervals cho một nhánh route ngoài giờ làm việc; cảnh báo phát sinh trong khoảng đó vẫn xuất hiện trong Alertmanager nhưng không có thông báo mà nhân viên trực mong đợi.
Một route dành cho đội hỗ trợ ban ngày được cấu hình active_time_intervals, song sự cố phát sinh ngoài khung giờ không đi đến receiver khẩn cấp như quy trình vận hành mong muốn.
Trong tuần chuyển giờ mùa hè của đối tác nước ngoài, khoảng mute theo lịch định kỳ bị hiểu khác với giờ trực địa phương; một số alert bị im lặng ngoài cửa sổ bảo trì dự kiến.
Hệ thống dùng Slack làm receiver cho lỗi ứng dụng; sau khi webhook bị thay đổi, Alertmanager ghi nhận lỗi gửi thông báo dù alert vẫn có mặt và được nhóm đúng trong giao diện.
Một tổ chức chuyển sang Slack channel mới nhưng token tích hợp không có quyền đăng tin ở channel đó; cấu hình receiver được tải thành công song notification liên tục thất bại.
Receiver email dùng máy chủ SMTP nội bộ vừa thay chứng chỉ TLS; thông báo alert bắt đầu lỗi xác thực kết nối trong khi dịch vụ Prometheus và Alertmanager vẫn khỏe.
Đội cấu hình email để gửi các alert chứa nhiều pod và instance; một thông báo quá dài khiến người trực khó đọc và một số client email cắt mất phần mô tả quan trọng.
Trong một sự cố, receiver PagerDuty nhận nhiều sự kiện cho cùng alert group vì khóa định danh sự cố phía tích hợp không nhất quán; người trực phải xử lý các incident trùng lặp.
Một kênh trực nhận được thông báo firing nhưng không nhận thông báo resolved sau khi dịch vụ phục hồi; người nhận tưởng sự cố vẫn đang diễn ra dù giao diện Alertmanager đã chuyển trạng thái.
Nhóm bật gửi resolved cho một receiver dùng để thống kê sự cố, nhưng receiver khác chỉ cần trạng thái firing; sau cập nhật cấu hình, hai kênh có số lượng notification khác nhau khiến báo cáo khó đối soát.
Một Alertmanager gửi webhook đến ứng dụng tạo ticket; khi webhook trả HTTP 500, hệ thống liên tục thử lại và ứng dụng ticket tạo nhiều vé cho cùng một nhóm cảnh báo.
Webhook receiver phản hồi HTTP 200 trước khi lưu notification vào hàng đợi, nhưng ứng dụng đích đôi khi lỗi ngay sau đó; Alertmanager ghi nhận gửi thành công còn nhóm trực không thấy ticket.
Một receiver gửi notification ra Internet qua proxy doanh nghiệp, nhưng cấu hình mạng mới chặn tên miền dịch vụ thông báo; alert và routing vẫn hoạt động trong khi kênh nhận hoàn toàn im lặng.
Đội quản trị lưu webhook URL và thông tin SMTP dưới dạng chuỗi trực tiếp trong repository cấu hình; sau khi repository mở rộng quyền đọc, nhóm bảo mật đặt câu hỏi về phạm vi lộ bí mật tích hợp.
Một template thông báo sử dụng nhãn team và service trong tiêu đề, nhưng một số alert hệ thống không có các nhãn đó; thông báo xuất hiện với phần tiêu đề trống hoặc khó xác định chủ sở hữu.
Nhóm chỉnh mẫu thông báo bằng cú pháp Go template, nhưng cấu hình được triển khai với lỗi parse template; Alertmanager không tải cấu hình mới và các thông báo tiếp tục theo mẫu cũ.
Một alert có annotation chứa ký tự đặc biệt và đường dẫn URL dài; mẫu thông báo gửi sang kênh chat render nội dung khác so với preview và một phần liên kết bị sai.
Mẫu thông báo gộp nhiều alert chỉ hiển thị CommonLabels nên bỏ mất nhãn phân biệt instance ở từng alert; người trực không biết máy nào đang lỗi nếu không mở giao diện chi tiết.
Receiver on-call cần một liên kết tới dashboard tương ứng với cluster, nhưng template đang tạo URL dựa trên nhãn environment thiếu ở một số alert; liên kết trong thông báo dẫn đến dashboard không đúng.
Một nhóm dùng annotation runbook_url để hướng dẫn xử lý, nhưng các rule khác nhau đặt tên annotation không thống nhất; một số thông báo khẩn cấp đến người trực mà không có đường dẫn runbook.
Đội SRE nâng cấp phiên bản Alertmanager và thay đổi một phần template; bản thông báo mới mất tên dịch vụ và thời điểm bắt đầu, khiến việc đối chiếu log sự cố khó hơn.
Một nhóm muốn ưu tiên thông tin khách hàng bị ảnh hưởng lên đầu thông báo nhưng Alertmanager chỉ có các label kỹ thuật; đội trực đang cân nhắc phần dữ liệu nào thuộc rule alert và phần nào thuộc mẫu receiver.
Doanh nghiệp chạy ba replica Alertmanager để dự phòng; Prometheus chỉ gửi alert tới một replica qua địa chỉ cố định nên khi replica đó lỗi, thông báo không được phát dù các replica khác vẫn khỏe.
Prometheus gửi alert đến cả ba replica Alertmanager, nhưng các instance chưa cấu hình kết nối peer HA; cùng một sự cố tạo ba notification giống nhau trên kênh trực.
Cụm Alertmanager HA có các peer ở hai vùng Kubernetes; sau khi cập nhật network policy chặn cổng gossip, thành viên vẫn nhận alert nhưng không trao đổi được trạng thái silence và notification log như trước.
Đội vận hành quan sát thấy các Alertmanager instance có peer list không đồng nhất sau khi một node khởi động lại; thông báo duplicate tăng ở một số receiver trong lúc cluster tái hội nhập.
Hệ thống kỳ vọng Alertmanager HA loại bỏ hoàn toàn thông báo trùng, nhưng khi mạng bị phân vùng giữa các replica, hai nhóm instance cùng gửi thông báo sự cố tới receiver.
Nhóm triển khai Alertmanager bằng StatefulSet nhưng không cấp ổ đĩa bền vững cho dữ liệu cục bộ; sau khi toàn cụm restart, các silence đã tạo và lịch sử notification không còn như trước.
Một thành viên HA có đồng hồ hệ thống lệch đáng kể so với các peer; thời điểm kết thúc silence và lịch gửi lặp không nhất quán giữa các node trong giờ bảo trì.
Đội phát triển đổi cấu hình route trên một replica Alertmanager trước khi cập nhật các replica khác; các node nhận cùng alert nhưng chọn receiver khác nhau khiến nhiều nhóm trực bị đánh thức.
Trong quá trình rolling upgrade Alertmanager, một instance dùng phiên bản cũ vẫn chia sẻ trạng thái với các instance mới; nhóm chưa kiểm chứng tính tương thích cluster và hành vi gửi thông báo qua giai đoạn chuyển phiên bản.
Doanh nghiệp có Alertmanager ở hai vùng nhưng không có đường mạng tới dịch vụ Slack từ vùng dự phòng; khi failover, alert vẫn firing nhưng người trực không nhận được tin nhắn.
Dashboard theo dõi chỉ có trạng thái pod Alertmanager Running; sau sự cố, nhóm mới phát hiện metric về notification failures tăng nhiều giờ dù pod và endpoint /-/healthy vẫn phản hồi.
Đội triển khai một config YAML mới có matcher sai cú pháp; lệnh reload không áp dụng được cấu hình nhưng bản cũ vẫn chạy, khiến pipeline báo thành công dựa trên mã HTTP không đủ để kiểm tra.
Nhóm sửa routes và receivers trực tiếp trên môi trường production mà không chạy amtool check-config; sau reload, một lỗi cấu hình làm Alertmanager tiếp tục dùng bản trước và kênh mới không nhận alert.
Đội CI/CD kiểm tra cú pháp YAML nhưng chưa kiểm tra route matcher và receiver tồn tại thực tế; cấu hình hợp lệ về định dạng song cảnh báo của team mới lại rơi vào receiver mặc định.
Nhóm kiểm thử routing chỉ với alert severity=critical trong production; các alert severity=warning của cùng team chưa từng được thử nên một nhánh cấu hình sai không được phát hiện.
Đội SRE tạo cảnh báo thử nghiệm và xác nhận nó xuất hiện trong Alertmanager nhưng không kiểm tra receiver cuối; khi xảy ra sự cố thật, webhook đích đã bị vô hiệu hóa từ lâu.
Một đợt thử nghiệm end-to-end gửi cảnh báo giả lập trực tiếp đến Alertmanager và nhận notification thành công; trong production, rule Prometheus thật có labelset khác nên route tương ứng không được chọn.
Đội kiểm thử quy trình silence bằng cách tạo một alert giả lập nhưng không kiểm tra thời điểm hết hạn; sau ca bảo trì thật, alert bắt đầu được gửi trở lại sớm hơn quy trình xử lý dự kiến.
Một tổ chức có quy trình chuyển ca trực hằng ngày nhưng danh sách người nhận PagerDuty trong Alertmanager được cập nhật thủ công; đến ngày nghỉ lễ, cảnh báo khẩn cấp được gửi đến người không trực.
Prometheus và Alertmanager ở hai cụm khác nhau, khi một cụm gặp lỗi mạng hệ thống chỉ mất đường gửi alert; không có cảnh báo về chính đường ống cảnh báo nên đội trực không biết mình đang bị mù sự cố.
Một alert Watchdog luôn firing để kiểm tra đường đi thông báo; sau khi cấu hình nhóm và route thay đổi, kênh giám sát độc lập không còn nhận nhịp định kỳ dù Alertmanager vẫn chạy.
Một ứng dụng tạo hàng nghìn alert trên cùng cluster do cardinality nhãn tăng bất thường; Alertmanager tiêu thụ nhiều bộ nhớ và số lượng nhóm tăng mạnh trong khi số sự cố nghiệp vụ thực sự không đổi.
Trong đợt mất điện trung tâm dữ liệu, hàng loạt alert giải quyết đồng thời khi hệ thống phục hồi; receiver nhận một đợt thông báo resolved dồn dập, lấn át những cảnh báo mới phát sinh sau khôi phục.

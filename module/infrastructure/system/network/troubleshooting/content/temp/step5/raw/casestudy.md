Một ứng dụng bán hàng báo không kết nối được tới API trong giờ cao điểm, nhưng đội trực nhận thấy chỉ người dùng tại chi nhánh Đà Nẵng bị ảnh hưởng còn Hà Nội và TP.HCM vẫn giao dịch bình thường; dashboard toàn hệ thống chưa được phân tách theo địa điểm.
Nhân viên báo website nội bộ chậm sau khi thay đổi VPN; cùng máy tính truy cập bằng mạng văn phòng nhanh nhưng qua VPN mất hơn 12 giây và nhóm chưa ghi nhận thời điểm bắt đầu lỗi cùng phạm vi người dùng bị tác động.
Sau bản phát hành ứng dụng, các request tới một API tăng tỷ lệ timeout từ 0,1% lên 8%; log backend cho thấy thời gian xử lý trung bình vẫn 40 ms, trong khi thời gian kết nối từ client biến động mạnh.
Một nhà cung cấp thông báo dịch vụ không khả dụng nhưng hệ thống theo dõi của đội vận hành vẫn báo xanh; kiểm tra cho thấy hệ thống giám sát chỉ gọi endpoint /health từ cùng trung tâm dữ liệu với backend.
Người dùng không mở được ứng dụng và nhóm hỗ trợ khởi động lại router ngay; sau đó sự cố tự hết nhưng không còn dữ liệu về DNS, đường đi hay tình trạng kết nối tại thời điểm lỗi để xác định nguyên nhân.
Một lỗi kết nối chỉ xảy ra lúc 9 giờ sáng khi nhân viên đồng loạt đăng nhập; các lần thử từ máy quản trị vào buổi chiều đều thành công và không tái hiện được hiện tượng.
Hệ thống thanh toán thỉnh thoảng trả lỗi ở request đầu tiên sau khi pod khởi động; cùng request chạy lại thành công, còn dữ liệu đo latency chỉ thể hiện tổng thời gian chứ không có DNS, TCP và TLS riêng.
Người dùng báo API trả lỗi ngắt quãng và đổ lỗi cho Internet; đối chiếu theo mã request cho thấy các lỗi đều đi qua một máy gateway trong bốn máy, trong khi ba máy còn lại không có lỗi.
Sau khi mở rộng sang vùng cloud mới, chỉ các kết nối giữa hai vùng gặp timeout; kết nối nội vùng vẫn bình thường và nhóm mới đo ping chứ chưa có dữ liệu về hướng đi hoặc giao thức ứng dụng bị ảnh hưởng.
Một hệ thống có ba lớp CDN, reverse proxy và ứng dụng; khi xuất hiện mã HTTP 502, mỗi nhóm chỉ có log của lớp mình và không chia sẻ cùng correlation ID nên chưa xác định nơi sinh lỗi.
Người dùng phản ánh ứng dụng không hoạt động dù ping đến IP máy chủ thành công; kiểm tra TCP trên cổng 443 lại thất bại và nhóm chưa phân biệt tính sẵn sàng ICMP với khả năng phục vụ HTTPS.
Một máy chủ không trả lời ping nhưng HTTPS vẫn hoạt động bình thường từ trình duyệt; hệ thống giám sát kết luận máy đã mất mạng chỉ dựa trên ICMP echo, gây cảnh báo sai liên tục.
Một API hoạt động qua địa chỉ IP nhưng trả lỗi khi gọi bằng tên miền sau khi chuyển DNS sang nhà cung cấp mới; các máy trong cùng văn phòng cho kết quả truy vấn DNS khác nhau.
Nhóm đổi bản ghi A của api.example.test sang IP mới với TTL 3.600 giây; sau 15 phút, một số client vẫn gọi IP cũ còn client khác đã chuyển sang IP mới, khiến tỷ lệ lỗi thay đổi theo mạng truy cập.
Khi truy vấn api.example.test bằng dig tới DNS nội bộ nhận địa chỉ 10.0.8.20 nhưng truy vấn resolver công cộng nhận 203.0.113.20; ứng dụng trong VPN hoạt động còn nhân viên vừa ngắt VPN truy cập nhầm nơi.
Một ứng dụng đặt hàng có record CNAME trỏ qua ba tên miền; sau khi tên miền trung gian hết hạn, các truy vấn tới đích nhận NXDOMAIN dù bản ghi ở miền ứng dụng ban đầu chưa bị xóa.
Trình duyệt truy cập trang quản trị thất bại trong khi curl dùng cùng URL trên máy chủ khác thành công; cấu hình hệ điều hành ưu tiên bản ghi AAAA và kết nối IPv6 thất bại còn IPv4 hoạt động.
Một số pod Kubernetes trả lỗi tìm tên service trong giờ cao điểm; log resolver cho thấy nhiều lần query bị timeout nhưng không có NXDOMAIN, còn cùng tên DNS được truy vấn lại sau một giây thì thành công.
Ứng dụng dùng tên ngắn inventory để gọi dịch vụ trong cluster; sau khi chuyển pod sang namespace mới, truy vấn DNS trả một địa chỉ khác hoặc không tìm thấy dù inventory.default.svc.cluster.local vẫn tồn tại.
Một thiết bị có cache DNS cục bộ giữ kết quả NXDOMAIN trong thời gian dài; sau khi đội DNS tạo bản ghi mới, thiết bị khác truy cập thành công còn thiết bị này vẫn báo không tìm thấy tên miền.
DNS authoritative đã cập nhật bản ghi nhưng một resolver recursive chưa nhận thay đổi; hai lệnh dig tới hai máy resolver cho câu trả lời khác nhau, trong khi nhóm ứng dụng đang nhìn duy nhất kết quả của máy quản trị.
Sau khi bật DNSSEC cho tên miền, một số resolver trả SERVFAIL còn các resolver không xác thực vẫn trả IP; hệ thống bị lỗi theo nhà mạng dù máy chủ HTTPS vẫn hoạt động.
Client trong mạng doanh nghiệp truy vấn tên miền có phản hồi DNS lớn chứa nhiều record; các truy vấn UDP đôi khi timeout, nhưng truy vấn cùng tên qua TCP nhận được đáp án đầy đủ.
Một dịch vụ DNS nội bộ trả CNAME kèm nhiều bản ghi và phản hồi bị cắt khi dùng UDP; ứng dụng chạy sau firewall không cho TCP/53 có lúc không phân giải được tên dù truy vấn tên đơn giản vẫn tốt.
Client truy cập dịch vụ có DNS cân bằng hai địa chỉ IP; một địa chỉ trỏ tới máy backend đã ngừng phục vụ và lỗi chỉ xuất hiện khi resolver hoặc client chọn địa chỉ đó.
Một ứng dụng đa vùng dùng DNS trả địa chỉ khác theo vị trí resolver; người dùng ở Singapore bị điều hướng sang vùng châu Âu dù truy vấn từ máy trạm tại Singapore bình thường vì DNS resolver thực tế đặt ở địa điểm khác.
Resolver nội bộ có quy tắc phân giải split-horizon cho tên db.example.test; sau khi nhân viên kết nối VPN, kết quả vẫn là IP công cộng do cache của client chưa thay đổi theo mạng.
Một máy chủ gửi thư đổi địa chỉ IP nhưng bản ghi PTR của địa chỉ mới vẫn trỏ tới hostname cũ; TCP/25 mở được, song một hệ thống thư nhận từ chối phiên SMTP do chính sách kiểm tra danh tính máy gửi.
Hệ thống thư điện tử chậm gửi thư đi sau khi chuyển DNS; tra cứu MX thành công nhưng một số tên máy chủ trong danh sách MX không có địa chỉ A hoặc AAAA phù hợp để mở kết nối.
Một ứng dụng Java chạy trong container chỉ thấy lỗi UnknownHostException sau khi DNS nội bộ có sự cố ngắn; các container khác đã phục hồi trong khi tiến trình này vẫn giữ kết quả phân giải cũ theo cấu hình cache riêng.
Một máy tính vừa kết nối Wi-Fi văn phòng nhưng tự nhận địa chỉ 169.254.x.x, không có default gateway và không mở được intranet; các máy cùng điểm phát khác vẫn nhận địa chỉ từ dải cấp phát thông thường.
Nhân viên đặt IP tĩnh 192.168.20.15/24 cho máy kiểm thử, nhưng máy chủ đích 192.168.30.10 nằm ở VLAN khác; ARP hoạt động với host cùng mạng mà ping đến đích liên VLAN không thành công.
Hai máy cùng sử dụng IP 10.10.5.21 sau khi một máy được gán thủ công và máy khác nhận DHCP; bảng ARP của gateway thay đổi MAC liên tục và kết nối tới dịch vụ trên địa chỉ đó mất ngắt quãng.
Một VLAN được bổ sung vào cấu hình switch access nhưng không có trong danh sách VLAN được phép trên trunk đến router; các máy trong VLAN thấy nhau ở lớp 2 nhưng không liên lạc được sang mạng khác.
Máy tính được cấu hình subnet mask /16 thay vì /24 trong mạng văn phòng; khi gọi một địa chỉ thuộc dải 10.20.x.x ở VLAN khác, máy gửi ARP trên mạng cục bộ thay vì chuyển tới gateway.
Một máy có hai card mạng Wi-Fi và Ethernet cùng hoạt động; sau khi cắm cáp, request tới hệ thống nội bộ đôi khi ra đường Wi-Fi vì độ ưu tiên tuyến đường mặc định không đúng kỳ vọng.
Gateway của một subnet đổi địa chỉ nhưng DHCP option của một số client vẫn cấp default gateway cũ; kết nối đến máy cùng subnet bình thường còn lưu lượng đi ngoài subnet bị timeout.
Trong một hệ thống camera, switch báo nhiều CRC errors trên một cổng Ethernet và tốc độ truyền thực tế giảm mạnh; ứng dụng đổ lỗi cho TCP dù chỉ các camera đi qua cổng đó gặp sự cố.
Đường quang giữa hai switch bị chập chờn; log interface ghi link flap đúng lúc API nội bộ gián đoạn nhưng biểu đồ CPU server vẫn ổn định và không có lỗi trong ứng dụng.
Mạng của nhà máy dùng Jumbo Frame MTU 9000 trên một số máy nhưng switch ở giữa vẫn giới hạn 1500; truyền gói nhỏ thành công còn các phép thử với payload lớn có bật DF thường thất bại.
Một VPN qua Internet mang thêm header tunnel làm MTU hiệu dụng giảm; phiên SSH mở được và lệnh ngắn chạy bình thường, nhưng tải file lớn liên tục treo sau khi gửi một lượng dữ liệu đầu.
Thiết bị biên chặn thông báo ICMP cần thiết cho Path MTU Discovery; kết nối TCP bắt tay được nhưng phản hồi HTTP lớn đi qua tunnel không tới đủ, trong khi response JSON nhỏ vẫn hoạt động.
Một máy IPv6 nhận địa chỉ từ SLAAC nhưng không có default route IPv6 hợp lệ sau thay đổi router advertisement; ping tới địa chỉ link-local được nhưng truy cập dịch vụ IPv6 ngoài subnet không thành công.
Hai thiết bị IPv6 trong cùng VLAN không kết nối trực tiếp được dù có địa chỉ hợp lệ; log cho thấy Neighbor Solicitation gửi đi nhưng không nhận Neighbor Advertisement ở một cổng switch.
Ứng dụng dual-stack mở kết nối bằng IPv6 tới hostname có cả AAAA và A; chỉ một mạng khách hàng bị timeout IPv6, trong khi ép kết nối IPv4 trên chính mạng đó lại thành công.
Một kết nối mạng nội bộ chỉ lỗi khi đi qua router mới: traceroute từ client dừng sau hop thứ hai nhưng kết nối TCP tới đích đôi khi vẫn thành công; nhóm chưa phân biệt việc router không trả ICMP Time Exceeded với việc mất gói chuyển tiếp.
Client ở subnet 10.1.4.0/24 không truy cập được 10.2.8.0/24 sau thay đổi route; bảng định tuyến của router biên có tuyến tới đích, nhưng đường trả về từ router của subnet đích chưa được kiểm tra.
Một API có lưu lượng đi qua firewall trạng thái; khi request ra ngoài theo đường A và response quay về theo đường B, firewall trên đường B không có state của kết nối và bắt đầu drop gói trả về.
Hai nhà cung cấp WAN quảng bá tuyến đến hệ thống thanh toán; sau đợt chuyển hướng BGP, thời gian phản hồi tăng gấp năm lần và mtr hiển thị đường đi qua một quốc gia khác trước khi tới máy chủ.
Sau khi kỹ sư xóa nhầm route tĩnh /24, router chi nhánh chỉ còn tuyến tổng hợp /16 đi qua next-hop khác; các đích trong dải /24 trước đó mất kết nối dù những đích khác vẫn truy cập được.
Ứng dụng cố truy cập database ở dải private của đối tác qua VPN; hai bên cùng dùng mạng 10.0.0.0/16 nên kết nối đi vào subnet nội bộ thay vì đi qua tunnel như nhóm tích hợp mong đợi.
Một máy chủ cloud có security group cho phép TCP/443 nhưng network ACL của subnet không cho lưu lượng trả về trên dải cổng tạm; TCP handshake không hoàn tất dù port phía server vẫn đang lắng nghe.
Firewall văn phòng cho phép DNS và HTTPS nhưng chặn OCSP hoặc endpoint xác thực ngoài; website kết nối TLS có lúc bị trình duyệt cảnh báo hoặc chờ lâu trong khi truy vấn DNS và TCP/443 đều bình thường.
Một dịch vụ chỉ không kết nối được khi máy khách dùng mạng di động; địa chỉ IPv4 công cộng của nhóm người dùng đó nằm trong dải bị firewall ứng dụng chặn theo vùng, còn kết nối từ mạng văn phòng thành công.
NAT gateway của hệ thống có nhiều pod tạo hàng nghìn kết nối ra cùng IP:port ngoài; số phiên SNAT và lỗi cấp phát cổng tăng vào giờ cao điểm dù backend đối tác vẫn trả kết quả bình thường cho client khác.
Một ứng dụng mở nhiều kết nối ngắn từ cùng máy Linux tới một API nhưng không tái sử dụng socket; số kết nối ở TIME_WAIT tăng mạnh và lỗi kết nối chỉ xuất hiện khi số request mỗi giây đạt đỉnh.
Hệ thống giám sát báo tỷ lệ packet loss 40% ở một hop giữa đường mtr, nhưng các hop sau và máy đích vẫn có mất gói gần bằng 0; nhóm vận hành cân nhắc thay router chỉ dựa trên thống kê hop đó.
Trên một đường kết nối WAN, độ trễ trung bình 20 ms nhưng một số request tăng lên 500 ms đúng khi truyền file lớn; biểu đồ queue tại router tăng mạnh dù không thấy mất kết nối hoàn toàn.
Một client gửi TCP SYN tới backend nhưng không nhận SYN-ACK và retry nhiều lần; log ứng dụng backend không có request, còn firewall hiển thị lượt drop tăng trên chính tuple nguồn/đích đó.
Gói TCP SYN tới server và server trả SYN-ACK theo packet capture, nhưng client tiếp tục gửi lại SYN; hai điểm thu gói ở hai đầu cho thấy chiều trả lời chưa tới được client.
TCP handshake hoàn tất và client gửi dữ liệu, sau đó nhận RST ngay lập tức từ một thiết bị trên đường đi; log server ứng dụng không có dấu vết của request tương ứng.
Một API có nhiều request mất hơn 10 giây nhưng `ss` cho thấy số socket ESTABLISHED rất cao và bảng chờ accept của server bị đầy; CPU ứng dụng không cao như mức độ chậm của client.
Người dùng tải báo cáo qua TCP và Wireshark ghi nhiều Duplicate ACK cùng Retransmission liên tiếp; các lần tải nhỏ hoàn tất còn tệp lớn thường giảm throughput mạnh.
Một thiết bị tải dữ liệu qua mạng vệ tinh có RTT 400 ms nhưng không mất gói đáng kể; throughput của một kết nối TCP thấp hơn rất nhiều băng thông danh nghĩa và phép đo iperf với nhiều luồng lại cao hơn.
Phía client gửi TCP Zero Window trong lúc backend liên tục truyền dữ liệu; máy chủ tưởng đường truyền nghẽn nhưng metric ứng dụng client cho thấy tiến trình đọc socket đang bị chặn.
Một microservice dùng connection pool và gặp lỗi socket sau khi idle 15 phút; gói tin cho thấy middlebox đã đóng phiên nhàn rỗi nhưng client vẫn thử tái sử dụng kết nối trước đó.
Ứng dụng tạo nhiều request tới cùng endpoint và dùng keep-alive, nhưng reverse proxy có thời gian idle ngắn hơn client; những request đầu sau quãng nghỉ nhận EOF còn request thử lại thành công.
Thiết bị IoT gửi datagram UDP telemetry mỗi giây nhưng dashboard thu thập không có dữ liệu; ping tới máy thu thành công, còn packet capture tại máy thu không thấy datagram nào tới cổng UDP được cấu hình.
Ứng dụng thoại thời gian thực dùng UDP hoạt động tốt trong mạng LAN nhưng mất tiếng khi đi qua NAT của một đối tác; tín hiệu điều khiển qua HTTPS bình thường còn luồng RTP nhận rất ít packet.
Ứng dụng dùng QUIC qua UDP/443 tải trang nhanh tại nhà nhưng chuyển sang HTTP/2 qua TCP ở mạng công ty; firewall doanh nghiệp chặn UDP/443 và browser phải thử giao thức khác trước khi tải.
Nhóm phát hiện nhiều TCP retransmission trong capture tại card mạng client nhưng capture tại server không thấy mất gói tương ứng; việc offload của NIC và vị trí bắt gói chưa được tính đến khi kết luận lỗi mạng.
Trên một máy chủ có tài nguyên hạn chế, `tcpdump` bật lọc rộng làm tăng dropped packets trong chính công cụ capture; nhóm phân tích nhầm số gói bị mất khi bắt gói với số gói mất trên đường truyền.
Một API HTTPS chỉ lỗi trên Java 8 cũ sau khi nhà cung cấp nâng mức TLS tối thiểu; TCP/443 vẫn kết nối, nhưng trace TLS hiển thị handshake alert trước khi có bất kỳ HTTP response.
Một nhà cung cấp thay chứng chỉ mới và thiếu intermediate CA trong chuỗi chứng chỉ gửi từ server; một số client có cache intermediate truy cập được còn client mới báo certificate path validation failed.
Một API trả chứng chỉ đúng khi gọi bằng tên miền nhưng lỗi hostname mismatch khi batch job kết nối bằng địa chỉ IP; máy chủ dùng virtual host TLS dựa trên SNI để chọn chứng chỉ.
Một proxy doanh nghiệp thực hiện HTTPS inspection bằng chứng chỉ do CA nội bộ cấp; trình duyệt trên máy công ty tin cậy CA này nhưng ứng dụng Java trong container dùng truststore riêng và báo handshake failure.
Client kết nối mTLS tới API đối tác sau khi thay chứng chỉ client; máy chủ yêu cầu chứng chỉ hợp lệ nhưng trace cho thấy bên client không gửi certificate phù hợp với danh sách CA được yêu cầu.
Thiết bị IoT chạy đồng hồ chậm nhiều năm và từ chối kết nối HTTPS tới máy chủ có chứng chỉ còn hạn; error log thể hiện certificate not yet valid trên thiết bị trong khi laptop truy cập cùng URL bình thường.
Một tên miền dùng TLS với SNI khác tên được ghi trong URL ở proxy trung gian; các request tới miền A nhận chứng chỉ của miền B chỉ trên một đường kết nối có proxy.
Sau khi chỉnh ALPN trên reverse proxy, kết nối TLS được thương lượng dùng HTTP/2 nhưng một tầng trung gian chuyển dữ liệu thẳng đến backend chỉ hỗ trợ HTTP/1.1; handshake TLS thành công còn trao đổi HTTP đầu tiên thất bại.
Trong một mạng có captive portal, client nghĩ đã kết nối Internet vì nhận IP và DNS, nhưng yêu cầu HTTPS tới dịch vụ lại không thể xác thực chứng chỉ còn request HTTP thường bị chuyển tới trang đăng nhập Wi-Fi.
Một API thỉnh thoảng mất ba giây trước khi gửi request đầu; trace từ client cho thấy DNS và TCP nhanh nhưng bước TLS handshake có nhiều lần retransmit từ một mạng chi nhánh.
Gateway có chứng chỉ mới và OCSP stapling bị cấu hình không phù hợp; lỗi xác thực TLS chỉ xuất hiện trên một nhóm thiết bị có chính sách kiểm tra thu hồi nghiêm ngặt.
Người dùng báo lỗi SSL trên ứng dụng di động sau khi server kích hoạt TLS 1.3; truy cập bằng trình duyệt desktop vẫn ổn, còn log thiết bị cho thấy cipher suites và protocol version hỗ trợ không giao nhau.
Máy khách truy cập một website qua proxy HTTP với phương thức CONNECT; proxy trả 407 Proxy Authentication Required trước khi kết nối TLS tới đích, nhưng ứng dụng chỉ hiển thị lỗi chứng chỉ chung.
Frontend gửi GET tới API và nhận 404 qua CDN, nhưng curl trực tiếp tới origin trả 200; header phản hồi cho thấy CDN đang chuyển đường dẫn với tiền tố khác origin.
Backend ghi log đã tạo response HTTP 200, nhưng gateway trả 504 cho cùng request vì hết thời gian chờ đọc phản hồi từ upstream; hai log có cùng request ID song nhóm chưa đối chiếu timestamp và đường truyền giữa hai lớp.
Một API upload trả 413 Request Entity Too Large trước khi log ứng dụng xuất hiện; request cùng nội dung nhỏ hơn 5 MB thành công và nhóm chưa xác định lớp proxy nào giới hạn body.
Browser không gửi POST tới API dù backend nhận POST từ curl bình thường; tab Network cho thấy OPTIONS preflight nhận 403 tại reverse proxy vì quy tắc CORS không đầy đủ.
Ứng dụng nhận HTTP 401 từ API chỉ trên đường qua gateway; request trực tiếp backend với cùng Bearer token trả 200, và log phía backend không ghi nhận header Authorization trong trường hợp qua gateway.
Người dùng ở một văn phòng thấy trang web cập nhật giá cũ còn nơi khác thấy giá mới; response headers cho thấy Age và X-Cache khác nhau dù cùng URL và cùng phiên bản ứng dụng.
Web client liên tục bị redirect HTTP sang HTTPS rồi lại về HTTP sau khi đổi cấu hình load balancer; header Location trong chuỗi phản hồi xen kẽ hai scheme còn backend chỉ nhìn thấy HTTP nội bộ.
Một SDK gửi HTTP/1.1 có header Content-Length không phù hợp với số byte payload; reverse proxy đóng kết nối trước khi request tới backend, còn SDK báo lỗi connection reset không có status code.
API streaming qua HTTP/2 bị ngắt sau khi proxy gửi GOAWAY trong lúc deploy; các request ngắn qua kết nối mới thành công nhưng stream đang truyền dữ liệu không hoàn tất.
Một CDN trả 429 vào giờ cao điểm và SDK tự retry ngay lập tức; số lần gọi ghi trong client tăng gấp ba nhưng log backend lại thấy rất ít request do các lần bị giới hạn ngay ở CDN.
Website gọi tài nguyên tĩnh từ origin khác và gặp lỗi CORS chỉ trên trình duyệt; GET thử bằng dòng lệnh trả 200 nhưng header Access-Control-Allow-Origin không tương ứng với origin của trang.
Một endpoint gửi phản hồi HTTP có Content-Encoding gzip, còn client tích hợp tự viết báo JSON parse error; bản capture cho thấy body vẫn ở dạng nén nhưng thư viện client không giải nén trước khi parse.
Trang báo cáo có thời gian tải dài nhưng backend tạo JSON trong 60 ms; DevTools cho thấy phần Waiting for server response ngắn, còn thời gian tải nội dung và xử lý tài nguyên phía browser kéo dài.
Kubernetes Service có tên và ClusterIP hợp lệ nhưng pod trong namespace B không gọi được pod backend; `kubectl get endpoints` cho thấy danh sách endpoint trống sau khi label selector được thay đổi.
Một pod trong Kubernetes phân giải được tên dịch vụ nhưng kết nối TCP vào ClusterIP timeout; cùng pod gọi trực tiếp IP của backend thành công và log kube-proxy hoặc dataplane của node đang có lỗi đồng bộ.
Một Kubernetes NetworkPolicy mới chỉ cho phép namespace A gọi namespace B; DNS vẫn hoạt động nhưng TCP SYN bị timeout với các pod ở namespace khác, còn pod chạy trong namespace A kết nối bình thường.
Ứng dụng trong container truy cập được Internet qua địa chỉ IP nhưng không tra cứu được tên ngoài; file resolv.conf trỏ tới DNS nội bộ không phản hồi và host node vẫn phân giải bình thường.
Pod triển khai trên một node cụ thể không thể gọi dịch vụ ngoài cluster, nhưng khi di chuyển sang node khác thì hoạt động; packet capture cho thấy gói ra khỏi pod nhưng không đi qua interface egress của node lỗi.
Một ingress controller trả 503 dù Kubernetes Service vẫn có endpoint; probe backend kiểm tra TCP thành công nhưng endpoint thực tế trả 500 và controller đã đưa toàn bộ pod vào trạng thái không khỏe.
Ứng dụng tại văn phòng gọi API cloud qua proxy nhưng timeout chỉ khi payload lớn; capture cho thấy các gói nhỏ được ACK bình thường và các segment lớn liên tục bị retransmit trên đoạn VPN.
Một dịch vụ báo giá có p99 cao trong khi CPU mạng và backend đều dưới 40%; số liệu TCP RTT tăng mạnh theo từng đợt và kết quả traceroute giữa hai vùng thay đổi trong cùng khoảng thời gian.
Trong giờ bảo trì mạng, một kỹ sư thay đồng thời DNS, firewall và route cho ứng dụng; sau sự cố, không có baseline trước thay đổi hoặc log theo mốc thời gian để xác định yếu tố nào gây mất kết nối.
Một hệ thống chỉ gián đoạn khi chuyển đường truyền dự phòng; trạng thái giao thức định tuyến đã hội tụ nhưng các kết nối TCP đang mở vẫn bị reset, và việc thử kết nối mới cho kết quả khác phiên cũ.
Nhóm phát triển cho rằng lỗi 504 là do máy chủ chậm và tăng timeout liên tiếp; dữ liệu APM vẫn cho thấy xử lý 30 ms, còn packet capture ghi TCP SYN tới upstream không nhận SYN-ACK.
Máy chủ ứng dụng có hai interface và policy routing theo IP nguồn; các reply TCP đi ra interface khác với đường request tới, khiến kết nối thất bại chỉ với một nhóm subnet dù cùng dịch vụ trên localhost hoạt động.
Một dashboard dựa vào log HTTP kết luận không có request vào máy chủ trong thời gian lỗi, nhưng packet capture ở card mạng cho thấy TCP SYN tới liên tục; tiến trình server không lắng nghe cổng sau khi nâng cấp.
Khách hàng báo lỗi gián đoạn tại một ASN cụ thể trong khi kiểm thử từ máy chủ cloud luôn tốt; so sánh traceroute, DNS answer và thời điểm mất gói của nhiều điểm đo cho thấy vấn đề phụ thuộc đường mạng nguồn.
Một đội trực tính tỷ lệ packet loss từ ping đến firewall và đánh giá lỗi nặng, nhưng phép thử TCP/443 và giao dịch HTTP end-to-end đến máy chủ vẫn thành công ổn định; mức ưu tiên xử lý ICMP của firewall chưa được xét đến.
Trong một cuộc điều tra, các log mạng hiển thị thời gian UTC nhưng log ứng dụng dùng múi giờ địa phương và một máy bị lệch đồng hồ hai phút; cùng một giao dịch xuất hiện như đi ngược thứ tự các sự kiện.

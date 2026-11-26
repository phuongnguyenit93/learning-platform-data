Một cửa hàng có máy tính tiền, máy in hóa đơn và phần mềm bán hàng; sau khi đổi router, máy tính vẫn truy cập Internet nhưng không in được qua mạng nội bộ, khiến nhóm hỗ trợ phải khoanh vùng triệu chứng ở các tầng liên kết, mạng và ứng dụng theo mô hình OSI và TCP/IP.
Hệ thống quản lý kho nhận được lỗi timeout khi gọi API qua tên miền, nhưng thao tác truy cập bằng địa chỉ IP trong cùng mạng lại thành công; đội trực ca chưa xác định được bước phân giải tên hay tầng truyền tải gây lỗi.
Một văn phòng thay dây mạng cho máy trạm từ 1 Gbps xuống còn liên kết 100 Mbps; ứng dụng tải tệp lớn chậm đi rõ rệt trong khi việc mở trang web nhỏ vẫn gần như bình thường.
Một máy chủ liên tục ghi nhận lỗi CRC trên cổng switch và tỉ lệ truyền lại dữ liệu tăng khi sao chép tệp; độ dài cáp và chất lượng đầu nối vừa được thay đổi trong đợt đi lại hệ thống dây.
Hai máy tính ở cùng switch vật lý nhưng được gán sang hai VLAN khác nhau; cả hai đều có địa chỉ IP hợp lệ và không thể trao đổi trực tiếp dù đèn kết nối Ethernet vẫn sáng.
Nhóm vận hành nối switch mới bằng cổng trunk nhưng quên cho phép VLAN dành cho máy quét mã vạch; máy tính văn phòng vẫn hoạt động còn các máy quét không nhận được địa chỉ mạng.
Một cổng switch cấu hình ở chế độ access lại nhận các frame có VLAN tag từ thiết bị đầu cuối; thiết bị này chỉ mất kết nối sau khi được chuyển từ cổng cũ sang cổng mới.
Văn phòng cắm thêm đường kết nối giữa hai switch để dự phòng; ngay sau đó mạng nội bộ chậm toàn diện, các đèn cổng nhấp nháy liên tục và bảng địa chỉ MAC thay đổi bất thường.
Đội quản trị thấy nhiều frame được switch phát ra các cổng khác khi thiết bị đích vừa khởi động; lưu lượng tăng trong chốc lát dù máy gửi và nhận đều dùng giao tiếp unicast.
Một máy tính đổi sang địa chỉ IP tĩnh nhưng vẫn giữ bản ghi ARP cũ cho địa chỉ gateway; ngay sau đợt thay router dự phòng, nó không ra Internet trong khi các máy khác cùng mạng hoạt động.
Hệ thống có hai thiết bị được cấu hình trùng địa chỉ IPv4 trên cùng mạng LAN; người dùng quan sát thấy lúc kết nối tới máy in thành công, lúc lại tới một thiết bị khác.
Máy tính nhân viên dùng địa chỉ 192.168.10.130 với subnet mask /25, còn máy in dùng 192.168.10.25 với mask /24; hai thiết bị xử lý việc gửi gói qua gateway khác nhau dù cùng nối vào một switch.
Một phòng học có 280 thiết bị nhưng nhóm triển khai vẫn cấp một mạng IPv4 /24 cho tất cả thiết bị; một số máy không nhận được địa chỉ khi lớp học bắt đầu đông người.
Nhóm thiết kế chia mạng 10.20.0.0/24 thành các subnet cho ba phòng ban có quy mô khác nhau; phương án hiện tại cấp quá ít địa chỉ cho phòng nhiều thiết bị và lãng phí ở phòng nhỏ.
Máy trạm nhận địa chỉ IP, subnet mask và DNS từ DHCP nhưng không có default gateway; nó truy cập được máy chủ cùng subnet song không truy cập được dịch vụ ở mạng khác.
Một nhân viên vừa cắm cáp Ethernet vừa kết nối Wi-Fi và nhận hai default gateway; đường đi tới dịch vụ nội bộ thay đổi sau khi ngắt một trong hai kết nối.
Một điểm truy cập Wi-Fi mới có dịch vụ DHCP riêng ngoài ý muốn; một số laptop nhận gateway thuộc mạng khách trong khi các máy còn lại nhận cấu hình của mạng công ty.
Máy tính chuyển từ phòng họp sang phòng làm việc nhưng vẫn giữ địa chỉ DHCP cũ trong một khoảng thời gian; nó nhìn thấy Wi-Fi đã kết nối song không liên lạc được với gateway mới.
Hệ thống cấp phát DHCP gần hết địa chỉ trong giờ hội nghị; khách mới thường không truy cập mạng dù thiết bị cũ duy trì kết nối ổn định.
Mạng Wi-Fi 2,4 GHz của văn phòng đông người có mức tín hiệu mạnh nhưng tốc độ thực tế thấp; việc quét môi trường cho thấy nhiều mạng lân cận sử dụng các kênh chồng lấn.
Một laptop ở cuối hành lang kết nối được Wi-Fi 5 GHz nhưng thường rớt cuộc gọi video, trong khi đặt gần access point thì kết nối ổn định và tốc độ cao hơn.
Người dùng đang gọi video khi đi giữa hai tầng và bị gián đoạn âm thanh vài giây dù cả hai tầng đều có Wi-Fi; thiết bị chuyển vùng giữa hai access point vào thời điểm xảy ra lỗi.
Nhóm lắp thêm nhiều access point để tăng vùng phủ, nhưng trong phòng họp đông người độ trễ và tỉ lệ truyền lại frame Wi-Fi tăng đáng kể dù vạch tín hiệu đầy.
Nhân viên có thể kết nối Wi-Fi khách nhưng không truy cập máy chủ kế toán trên LAN; một số người nghĩ router hỏng dù chính sách phân tách mạng khách đã được bật gần đây.
Một thiết bị IoT chỉ hỗ trợ Wi-Fi 2,4 GHz và không kết nối được sau khi công ty chuyển mạng không dây sang cấu hình bảo mật và băng tần mới; laptop đời mới vẫn sử dụng bình thường.
Một ứng dụng nội bộ dùng địa chỉ IPv4 private 10.0.0.0/8; nhân viên kết nối VPN từ nhà có router dùng dải IP chồng lấn nên một số dịch vụ chỉ lỗi khi bật VPN.
Một trang web nội bộ chạy trên máy chủ trong LAN có thể truy cập từ văn phòng, nhưng đối tác ngoài Internet không kết nối được dù cổng dịch vụ đã lắng nghe và DNS trỏ đến IP công khai.
Nhóm mở port forwarding trên router gia đình để truy cập camera từ xa, nhưng địa chỉ WAN của router nằm trong dải địa chỉ private của nhà cung cấp; camera chỉ truy cập được từ trong nhà.
Một công ty dùng NAT để nhiều máy trạm đi Internet qua cùng một IP công khai; khi hệ thống đối tác giới hạn lưu lượng theo IP nguồn, nhiều nhân viên độc lập cùng bị chặn.
Một máy chủ có hai giao diện mạng đi qua hai router; request từ khách đi vào giao diện thứ nhất nhưng response đôi lúc thoát qua giao diện thứ hai rồi bị firewall chặn.
Sau khi thêm static route cho mạng chi nhánh, một số dải địa chỉ truy cập được và một số dải mất kết nối do route cụ thể hơn đang trỏ sang đường truyền cũ.
Nhóm thay đổi metric của hai đường ra Internet để ưu tiên đường dự phòng; lưu lượng tới một số đích đi qua tuyến có độ trễ cao hơn dù cả hai đường đều sẵn sàng.
Hệ thống kết nối hai trung tâm dữ liệu qua VPN; khi một đường truyền bị gián đoạn, kết nối tới mạng phía bên kia mất nhiều phút mới hồi phục dù đường dự phòng vẫn hoạt động.
Một máy khách kết nối qua IPv6 tới dịch vụ công cộng nhưng thất bại, trong khi buộc dùng IPv4 lại thành công; router vừa được bật cấp địa chỉ IPv6 tự động cho LAN.
Máy chủ có bản ghi DNS loại A và AAAA, nhưng ứng dụng của một nhóm người dùng gặp timeout trước khi kết nối thành công qua địa chỉ còn lại; mạng của nhóm đó không có đường IPv6 hoạt động đầy đủ.
Máy trạm đã nhận địa chỉ IPv6 và router advertisement nhưng không phân giải được địa chỉ lớp liên kết của thiết bị cùng mạng; lưu lượng Neighbor Discovery bị lọc trên một phân đoạn.
Một máy chủ trả lời ping từ chi nhánh nhưng truy cập ứng dụng HTTPS lại thường treo khi tải nội dung lớn; đường truyền VPN có MTU nhỏ hơn mạng nội bộ và các gói lớn gặp khó khăn trên đường đi.
Ứng dụng gửi datagram UDP lớn qua một đường truyền có MTU thấp; tại chi nhánh, một phần thông điệp không tới được dù các thông điệp nhỏ đều được nhận.
Nhóm chẩn đoán dùng ping thấy máy chủ không phản hồi ICMP nên kết luận máy chủ ngừng hoạt động; cùng thời điểm, kết nối TCP tới cổng ứng dụng vẫn thành công.
Khi chạy traceroute tới một dịch vụ đám mây, một số router trung gian không trả lời nhưng các hop tiếp theo và máy đích vẫn xuất hiện; nhóm đang phân tích liệu đường truyền thực sự bị gián đoạn.
Một API tại chi nhánh nhận timeout kết nối TCP từ xa; bản ghi gói tin cho thấy nhiều SYN gửi đi nhưng không nhận SYN-ACK, trong khi máy chủ tại trung tâm dữ liệu vẫn truy cập được từ mạng khác.
Ứng dụng desktop mở kết nối TCP thành công nhưng bị đóng ngay sau khi gửi request; log phía server ghi nhận reset từ một thiết bị mạng trung gian sau đợt cập nhật firewall.
Một khách hàng tải tệp lớn thấy tốc độ giảm từng đợt; packet capture ghi nhận nhiều TCP retransmission và duplicate ACK ngay khi đường truyền không dây có nhiễu.
Một dịch vụ gửi dữ liệu liên tục qua TCP nhưng phía nhận xử lý chậm và quảng bá cửa sổ nhận rất nhỏ; CPU phía gửi thấp dù throughput truyền dữ liệu không tăng.
Máy chủ API tiếp nhận nhiều kết nối TCP cùng lúc trong giờ mở bán; một phần khách không hoàn thành bắt tay kết nối dù quy trình nghiệp vụ chưa thực thi.
Một hệ thống giữ kết nối TCP lâu để cập nhật trạng thái thiết bị; firewall cắt các phiên ít hoạt động và lần gửi dữ liệu tiếp theo báo lỗi sau một khoảng thời gian nhàn rỗi.
Một ứng dụng giám sát dùng UDP để gửi số liệu theo giây; khi mạng bị nghẽn, một số bản tin bị mất nhưng ứng dụng không nhận được cơ chế xác nhận truyền thành công từ giao thức.
Ứng dụng thoại thời gian thực gặp tiếng giật và mất đoạn khi đường truyền biến động; các gói UDP đến không đúng thứ tự và thời gian đến giữa các gói khác nhau đáng kể.
Nhóm chuyển ứng dụng truyền thời gian thực từ UDP sang TCP với hy vọng không còn mất dữ liệu; trong lúc mạng chập chờn, độ trễ phát lại âm thanh tăng do phải chờ dữ liệu thiếu.
Một ứng dụng truy cập được dịch vụ bằng IP nhưng không truy cập được bằng tên miền; máy khách đang dùng DNS resolver khác với các thiết bị hoạt động bình thường.
Nhóm chuyển dịch vụ sang máy chủ mới và giảm TTL của bản ghi DNS ngay trước giờ cắt chuyển; một số người dùng vẫn truy cập địa chỉ cũ do bộ nhớ đệm đã lưu bản ghi với TTL trước đó.
Tên miền nội bộ của doanh nghiệp trả về địa chỉ private khi ở văn phòng nhưng địa chỉ khác khi dùng DNS công cộng; người dùng VPN chỉ gặp lỗi khi resolver ngoài được chọn.
Một máy trạm truy vấn tên máy chủ ngắn không có dấu chấm và kết quả khác với máy cùng phòng; hai máy đang sử dụng DNS search suffix không giống nhau.
Ứng dụng gửi yêu cầu tới tên miền chứa chuỗi CNAME nhiều lớp; sau khi đổi cấu hình một mắt xích, một số tên phân giải được còn các tên khác nhận lỗi từ resolver.
Một service mới được tạo trong DNS nhưng một số máy vẫn báo không tồn tại tên miền trong một khoảng thời gian dù phía DNS có bản ghi hợp lệ.
Một số truy vấn DNS trả dữ liệu lớn qua UDP rồi gặp mất gói hoặc bị giới hạn kích thước; máy khách tại một chi nhánh thường phân giải tên chậm hơn máy khách ở văn phòng chính.
Trang web vẫn mở được bằng HTTP nhưng khi đổi sang HTTPS thì trình duyệt báo chứng chỉ đã hết hạn; máy chủ ứng dụng và mạng IP bên dưới vẫn phản hồi kết nối.
Một dịch vụ được truy cập qua tên miền mới nhưng chứng chỉ TLS chỉ chứa tên miền cũ; kết nối mã hóa được thiết lập tới đúng IP song client từ chối xác thực danh tính máy chủ.
API được cài chứng chỉ máy chủ TLS nhưng thiếu chứng chỉ trung gian trong chuỗi tin cậy; trình duyệt của một số thiết bị vào được còn chương trình dòng lệnh trên thiết bị khác báo lỗi xác thực chứng chỉ.
Công ty bật proxy kiểm tra lưu lượng HTTPS, sau đó ứng dụng Java cũ báo lỗi chứng chỉ dù trình duyệt trên máy tính quản trị vẫn mở được cùng endpoint.
Một gateway dùng chung IP để phục vụ nhiều tên miền HTTPS; khi client không gửi đúng thông tin tên miền trong bước bắt tay TLS, máy chủ chọn chứng chỉ không khớp với tên đang truy cập.
Một thiết bị mới xuất xưởng có đồng hồ hệ thống sai nhiều tháng; nó không thiết lập được kết nối TLS tới máy chủ cập nhật dù có đường mạng và DNS hoạt động.
Người dùng phản ánh không thể truy cập HTTPS từ mạng công ty sau khi cấu hình firewall mới; kết nối TCP tới cổng 443 bị từ chối trong khi cổng 80 và truy vấn DNS vẫn hoạt động.
Firewall giữa hai subnet cho phép gói đi đến máy chủ nhưng chặn gói trả lời trên tuyến đi ngược; packet capture ở hai phía cho thấy request đến máy đích nhưng client vẫn timeout.
Một API có thể truy cập bằng localhost trên máy chủ nhưng từ máy khác trong LAN lại nhận lỗi kết nối; tiến trình dịch vụ hiện chỉ lắng nghe trên địa chỉ loopback.
Hệ thống quản lý thiết bị kết nối qua NAT có thể nhận request từ bên trong nhưng thiết bị bên ngoài không chủ động mở phiên về máy trong LAN nếu không có đường truy cập tương ứng.
Trong giờ cao điểm, biểu đồ sử dụng đường truyền chỉ khoảng 60% băng thông danh nghĩa nhưng cuộc gọi video vẫn có độ trễ rất cao khi có luồng sao lưu lớn đi qua cùng router.
Nhóm áp dụng chính sách ưu tiên gói thoại trên đường WAN; sau thay đổi, video call ổn định hơn nhưng việc truyền tệp của bộ phận thiết kế chậm rõ rệt vào giờ làm việc.
Một ứng dụng truy cập dịch vụ qua nhiều hop; packet capture tại máy khách ghi nhận retransmission nhưng capture ở cổng máy chủ không thấy nhiều gói tương ứng, khiến nhóm cần xác định vị trí mất gói.
Đội vận hành chỉ đo băng thông trung bình theo giờ trong khi ứng dụng giao dịch nhận timeout vài phút mỗi ngày; những đợt mất gói ngắn không hiện rõ trong biểu đồ đã tổng hợp.
Hai máy chủ ghi timestamp packet capture lệch nhau nhiều giây; khi phân tích độ trễ request và response giữa hai nơi, nhóm đưa ra kết quả thời gian truyền âm bất hợp lý.
Đội hỗ trợ tìm nguyên nhân hệ thống chậm bằng ping, traceroute và truy vấn DNS tại một thời điểm; sự cố chỉ xuất hiện dưới tải đồng thời cao nên các phép đo lúc nhàn rỗi đều bình thường.
Mạng văn phòng vẫn truy cập Internet nhưng dịch vụ nội bộ không hoạt động sau khi cập nhật quy tắc định tuyến và VLAN; nhật ký switch, router, DNS và ứng dụng ghi nhận những triệu chứng khác nhau vào cùng thời điểm.

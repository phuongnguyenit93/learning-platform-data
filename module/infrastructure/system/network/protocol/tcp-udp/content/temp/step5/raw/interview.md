Bạn giải thích sự khác nhau giữa dịch vụ truyền tải của TCP và UDP ở tầng transport như thế nào?
Bạn lựa chọn TCP hay UDP cho một ứng dụng dựa trên độ tin cậy, độ trễ và đặc điểm thông điệp ra sao?
Bạn phân biệt byte stream của TCP với datagram của UDP bằng một ví dụ truyền dữ liệu thực tế như thế nào?
Bạn mô tả vai trò của địa chỉ IP và cổng nguồn, cổng đích trong việc chuyển dữ liệu tới đúng tiến trình ra sao?
Bạn xác định một luồng TCP được nhận diện bằng những thông tin địa chỉ và cổng nào?
Bạn phân biệt một socket đang lắng nghe với socket của một kết nối TCP đã được thiết lập như thế nào?
Bạn giải thích vì sao TCP không giữ ranh giới thông điệp ứng dụng dù dữ liệu được gửi theo từng lần gọi send ra sao?
Bạn phân tích trường hợp hai lần gửi TCP được ứng dụng nhận thành một hoặc nhiều lần đọc bằng cách nào?
Bạn thiết kế cách đóng khung thông điệp trên TCP bằng độ dài, ký tự phân cách hoặc định dạng cố định ra sao?
Bạn đánh giá rủi ro khi ứng dụng giả định một lần recv TCP tương ứng với đúng một thông điệp như thế nào?
Bạn phân biệt thứ tự byte trên mạng với thứ tự byte của máy chủ khi mã hóa trường trong header ra sao?
Bạn giải thích ý nghĩa của cổng well-known, registered và ephemeral đối với kết nối client-server như thế nào?
Bạn nhận diện trách nhiệm của tầng ứng dụng khi sử dụng UDP mà vẫn cần thứ tự hoặc bảo đảm giao nhận ra sao?
Bạn cân nhắc chi phí header và thiết lập kết nối khi chọn giao thức cho bản tin nhỏ, gửi thường xuyên như thế nào?
Bạn xác định tác động của packet loss, jitter và độ trễ vòng đi về đến từng loại ứng dụng ra sao?
Bạn giải thích TCP three-way handshake qua các gói SYN, SYN-ACK và ACK như thế nào?
Bạn mô tả cách hai đầu kết nối chọn và xác nhận initial sequence number trong quá trình handshake ra sao?
Bạn phân tích thông tin MSS, window scale và SACK permitted được thương lượng trong SYN như thế nào?
Bạn giải thích vì sao TCP cần xác nhận hai chiều khi thiết lập phiên kết nối ra sao?
Bạn phân biệt timeout của thao tác connect với timeout khi đã kết nối và đang chờ dữ liệu như thế nào?
Bạn dùng bản bắt gói để nhận biết client đã gửi SYN nhưng chưa nhận SYN-ACK ra sao?
Bạn phân tích trường hợp server trả RST ngay sau SYN và xác định những nguyên nhân có thể xảy ra như thế nào?
Bạn nhận diện một SYN-ACK đến client nhưng không có ACK cuối cùng trong bản bắt gói như thế nào?
Bạn phân biệt hành vi khi cổng đích không có tiến trình lắng nghe với khi firewall âm thầm chặn SYN ra sao?
Bạn giải thích SYN backlog và accept queue có vai trò gì khi máy chủ nhận nhiều kết nối đồng thời?
Bạn xác định dấu hiệu hàng đợi kết nối đầy khi lưu lượng truy cập tăng đột biến như thế nào?
Bạn đánh giá tác dụng và giới hạn của SYN cookies khi phải xử lý nhiều SYN chưa hoàn tất ra sao?
Bạn kiểm tra lỗi kết nối chỉ xảy ra khi server chịu tải nặng bằng những chỉ số và bản bắt gói nào?
Bạn phân biệt kết nối được thiết lập ở tầng TCP với việc ứng dụng phía server đã accept và xử lý yêu cầu ra sao?
Bạn xác định ý nghĩa các trạng thái SYN-SENT, SYN-RECEIVED và ESTABLISHED khi điều tra handshake như thế nào?
Bạn giải thích hệ quả của việc mất gói SYN hoặc SYN-ACK lên thời gian thiết lập kết nối như thế nào?
Bạn lựa chọn connection timeout phù hợp cho dịch vụ qua mạng nội bộ so với qua Internet ra sao?
Bạn phân tích vai trò của load balancer khi một kết nối TCP tới địa chỉ dịch vụ cần được chuyển tới backend như thế nào?
Bạn nhận diện sự cố kết nối mới chỉ lỗi trên một backend sau load balancer bằng cách nào?
Bạn đánh giá số vòng trao đổi cần thiết trước khi truyền dữ liệu ứng dụng khi dùng TCP và TLS ra sao?
Bạn mô tả ý nghĩa của TCP sequence number trong luồng byte liên tục như thế nào?
Bạn đọc trường sequence number và acknowledgement number để xác định những byte đã được xác nhận ra sao?
Bạn giải thích cơ chế cumulative ACK và tác động của nó khi các segment đến không theo thứ tự như thế nào?
Bạn xác định sự khác biệt giữa kích thước TCP segment và số byte ứng dụng viết vào socket bằng cách nào?
Bạn phân biệt TCP segment, IP packet và Ethernet frame khi xem công cụ bắt gói ra sao?
Bạn giải thích tại sao TCP receiver phải sắp xếp lại dữ liệu đến sai thứ tự trước khi cung cấp byte stream cho ứng dụng như thế nào?
Bạn phân tích ví dụ một segment bị mất nhưng các segment sau vẫn đến để dự đoán ACK của receiver ra sao?
Bạn xác định ý nghĩa của duplicate ACK trong các tình huống mất gói hoặc đảo thứ tự gói như thế nào?
Bạn giải thích vai trò của selective acknowledgement trong việc báo các vùng dữ liệu đã nhận ngoài thứ tự ra sao?
Bạn so sánh cumulative ACK và SACK khi có nhiều segment bị mất trong cùng một cửa sổ truyền như thế nào?
Bạn phân biệt duplicate ACK xuất hiện do packet reordering với duplicate ACK do mất gói bằng những dấu hiệu nào?
Bạn giải thích delayed ACK có thể ảnh hưởng đến luồng gửi các bản tin nhỏ như thế nào?
Bạn kiểm tra độ trễ ứng dụng khi cơ chế delayed ACK tương tác với Nagle bằng cách nào?
Bạn nhận biết cách TCP xác nhận FIN và việc FIN chiếm một vị trí trong không gian sequence number ra sao?
Bạn đọc relative sequence number trong Wireshark và chuyển sang ý nghĩa byte offset thực tế như thế nào?
Bạn phân tích vì sao sequence number có thể quay vòng trong một kết nối truyền dữ liệu lớn mà vẫn hoạt động ra sao?
Bạn xác định khi nào một gói lặp lại trong trace là retransmission thực sự thay vì bản sao do vị trí capture như thế nào?
Bạn giải thích vì sao TCP phải phát lại dữ liệu trong môi trường IP không bảo đảm giao hàng như thế nào?
Bạn mô tả cách TCP ước lượng round-trip time để thiết lập retransmission timeout ra sao?
Bạn phân biệt retransmission do RTO với fast retransmit dựa trên sự kiện trong trace như thế nào?
Bạn giải thích exponential backoff tác động tới thời gian chờ khi nhiều lần retransmission liên tiếp thất bại ra sao?
Bạn xác định lý do retransmission tăng dù không thấy lỗi trên card mạng của server bằng cách nào?
Bạn phân tích tác động của packet loss nhỏ nhưng lặp lại lên thông lượng của một luồng TCP như thế nào?
Bạn phân biệt retransmission do mất gói trên đường truyền với retransmission khi ACK bị mất ra sao?
Bạn nhận diện khả năng có packet reordering trên đường đi nhiều tuyến bằng các chỉ số nào?
Bạn giải thích vì sao TCP không bảo đảm thời hạn giao dữ liệu dù cung cấp truyền dữ liệu tin cậy ra sao?
Bạn đánh giá ảnh hưởng của retransmission tới ứng dụng tương tác thời gian thực như thế nào?
Bạn thiết kế kiểm thử mạng có mất gói và jitter để đánh giá độ nhạy của ứng dụng TCP ra sao?
Bạn xác định khi nào phải thử lại thao tác nghiệp vụ ở tầng ứng dụng dù TCP đã xử lý retransmission như thế nào?
Bạn kiểm tra hậu quả khi ứng dụng tự retry một yêu cầu sau khi mất kết nối nhưng server đã xử lý xong ra sao?
Bạn phân biệt tính tin cậy của byte stream với tính đúng đắn và tính duy nhất của một giao dịch ứng dụng như thế nào?
Bạn giải thích TCP checksum có thể phát hiện dạng lỗi truyền dữ liệu nào và giới hạn của nó ra sao?
Bạn nhận diện checksum báo sai do checksum offload trên máy bắt gói bằng cách nào?
Bạn đánh giá tác động của việc bật selective acknowledgement tới phục hồi đường truyền nhiều mất gói như thế nào?
Bạn phân tích hiện tượng head-of-line blocking trong một luồng TCP khi segment ở giữa bị mất ra sao?
Bạn xác định cách một ứng dụng nhiều thông điệp chịu tác động khi dùng chung một kết nối TCP có mất gói như thế nào?
Bạn giải thích receiver advertised window thể hiện giới hạn bộ đệm nhận của TCP như thế nào?
Bạn phân biệt flow control với congestion control theo mục tiêu bảo vệ bên nhận và mạng truyền ra sao?
Bạn mô tả sliding window cho phép nhiều byte chưa được ACK cùng đang truyền như thế nào?
Bạn xác định số byte còn có thể gửi từ advertised window và lượng dữ liệu chưa được xác nhận ra sao?
Bạn giải thích window scaling giúp xử lý kết nối có bandwidth-delay product lớn như thế nào?
Bạn tính bandwidth-delay product để ước lượng bộ đệm cần thiết cho một đường truyền tốc độ cao như thế nào?
Bạn nhận diện receiver window giảm dần khi ứng dụng đọc socket quá chậm ra sao?
Bạn phân tích nguyên nhân xuất hiện zero window và hành vi TCP ở phía gửi như thế nào?
Bạn giải thích zero-window probe giúp bên gửi biết khi nào receiver có thể nhận thêm dữ liệu ra sao?
Bạn phân biệt window full, zero window và congestion window limiting trong một bản bắt gói như thế nào?
Bạn kiểm tra kích thước send buffer và receive buffer ảnh hưởng tới thông lượng như thế nào?
Bạn lựa chọn chiến lược đọc dữ liệu trong ứng dụng để tránh bộ đệm socket bị đầy ra sao?
Bạn nhận diện sự khác biệt giữa tốc độ ứng dụng tạo dữ liệu và tốc độ mạng cho phép gửi bằng cách nào?
Bạn phân tích tại sao tăng receive buffer không giúp ích nếu nghẽn thực tế nằm tại đường truyền ra sao?
Bạn giải thích congestion window và slow start threshold ảnh hưởng đến tốc độ gửi TCP như thế nào?
Bạn mô tả cơ chế slow start của TCP trong những round-trip đầu tiên của kết nối ra sao?
Bạn phân biệt slow start với congestion avoidance khi tốc độ truyền tăng theo thời gian như thế nào?
Bạn đánh giá ảnh hưởng của RTT cao tới tốc độ tăng cửa sổ tắc nghẽn ra sao?
Bạn phân tích cách TCP phản ứng khi phát hiện mất gói bằng RTO so với duplicate ACK như thế nào?
Bạn giải thích vì sao tốc độ truyền có thể giảm mạnh sau một đợt mất gói trên mạng như thế nào?
Bạn nhận diện tác động của queueing delay và bufferbloat lên ứng dụng tương tác như thế nào?
Bạn phân biệt congestion do thiết bị mạng quá tải với hạn chế do receive window nhỏ bằng những đo đạc nào?
Bạn xác định vì sao một kết nối TCP tải file lớn không đạt băng thông danh nghĩa của đường truyền ra sao?
Bạn đánh giá ảnh hưởng của số luồng TCP song song tới chia sẻ băng thông và công bằng tài nguyên như thế nào?
Bạn so sánh cách tiếp cận mất gói của các thuật toán congestion control như CUBIC và BBR ra sao?
Bạn kiểm tra congestion control algorithm đang được hệ điều hành sử dụng và giải thích lựa chọn đó như thế nào?
Bạn mô tả vai trò của ECN trong việc báo hiệu tắc nghẽn trước khi phải loại bỏ gói ra sao?
Bạn phân tích tác động của pacing lên việc giảm những đợt gửi dồn dập trong TCP như thế nào?
Bạn xác định khi nào throughput bị giới hạn bởi ứng dụng, CPU, socket buffer hay congestion control như thế nào?
Bạn thiết kế phép thử có kiểm soát để phân biệt nghẽn mạng với giới hạn xử lý của server ra sao?
Bạn mô tả trạng thái FIN-WAIT-1, FIN-WAIT-2, CLOSE-WAIT và LAST-ACK khi hai đầu đóng TCP như thế nào?
Bạn phân biệt đóng kết nối TCP bằng FIN với hủy kết nối bằng RST trong trường hợp nào?
Bạn giải thích ý nghĩa của half-close khi một bên đã ngừng gửi nhưng vẫn có thể nhận dữ liệu ra sao?
Bạn xác định nguyên nhân hàng nghìn socket ở CLOSE-WAIT vẫn tồn tại trong một dịch vụ như thế nào?
Bạn giải thích TIME-WAIT giúp xử lý segment cũ và quá trình đóng kết nối như thế nào?
Bạn phân tích vì sao client tạo quá nhiều kết nối ngắn có thể làm tăng số socket TIME-WAIT ra sao?
Bạn đánh giá rủi ro cạn ephemeral port khi cùng lúc có nhiều kết nối outbound như thế nào?
Bạn phân biệt giới hạn ephemeral port, file descriptor và giới hạn số kết nối đồng thời ra sao?
Bạn xác định khi nào nên tái sử dụng kết nối TCP thay vì mở mới cho mỗi yêu cầu ứng dụng như thế nào?
Bạn thiết kế idle timeout cho connection pool sao cho phù hợp với load balancer và firewall ra sao?
Bạn giải thích TCP keepalive giúp phát hiện kết nối chết ở điều kiện nào và độ trễ phát hiện ra sao?
Bạn phân biệt TCP keepalive với heartbeat do ứng dụng tự gửi theo yêu cầu nghiệp vụ như thế nào?
Bạn điều tra một kết nối nhàn rỗi bị NAT hoặc firewall xóa trạng thái mà hai đầu vẫn tưởng đang kết nối như thế nào?
Bạn phân tích nguyên nhân server gửi RST sau khi ứng dụng ghi vào kết nối đã bị đóng trước đó ra sao?
Bạn xác định ảnh hưởng của đóng kết nối bất thường tới dữ liệu đang nằm trong bộ đệm gửi ra sao?
Bạn kiểm tra trường hợp ứng dụng gọi close nhưng các tài nguyên socket không được giải phóng đúng lúc như thế nào?
Bạn lựa chọn timeout cho kết nối lâu dài khi client di động có thể mất mạng tạm thời ra sao?
Bạn giải thích cấu trúc header UDP và vai trò của source port, destination port, length và checksum như thế nào?
Bạn phân biệt datagram boundary của UDP với hành vi đọc byte stream trên TCP như thế nào?
Bạn mô tả điều gì xảy ra nếu ứng dụng nhận UDP cung cấp buffer nhỏ hơn kích thước datagram ra sao?
Bạn xác định các nghĩa vụ xử lý mất gói, trùng gói và sai thứ tự khi thiết kế giao thức ứng dụng trên UDP như thế nào?
Bạn lựa chọn UDP cho ứng dụng thoại hoặc game trực tuyến dựa trên yêu cầu độ trễ như thế nào?
Bạn phân biệt gửi UDP tới một host không lắng nghe với kết nối TCP tới cổng không có dịch vụ ra sao?
Bạn giải thích phản hồi ICMP Port Unreachable liên quan đến lỗi gửi UDP như thế nào?
Bạn phân tích khi nào một phép gửi UDP thành công tại socket vẫn không bảo đảm datagram tới đích ra sao?
Bạn đánh giá độ dài payload UDP so với MTU để tránh fragmentation trên đường truyền như thế nào?
Bạn nhận diện nguy cơ mất cả datagram khi chỉ một fragment IP không đến được đích ra sao?
Bạn thiết kế giới hạn kích thước datagram phù hợp với đường truyền IPv4, IPv6 và VPN như thế nào?
Bạn giải thích sự khác nhau giữa UDP checksum trong IPv4 và IPv6 theo phạm vi sử dụng thông thường ra sao?
Bạn đánh giá ảnh hưởng của packet loss và jitter lên chất lượng âm thanh trực tuyến như thế nào?
Bạn thiết kế jitter buffer khi ứng dụng cần phát dữ liệu gần thời gian thực ra sao?
Bạn xây dựng sequence number ở tầng ứng dụng để nhận diện datagram UDP bị mất hoặc đảo thứ tự như thế nào?
Bạn lựa chọn cơ chế ACK và retry ở tầng ứng dụng UDP cho những thông điệp thực sự phải đến đích ra sao?
Bạn xác định khi nào FEC phù hợp hơn retransmission cho luồng dữ liệu UDP có hạn chót xử lý như thế nào?
Bạn thiết kế cơ chế giới hạn tốc độ gửi UDP để tránh làm nghẽn mạng như thế nào?
Bạn xác định những rủi ro khi một ứng dụng gửi UDP quá nhanh mà không có flow control ra sao?
Bạn lựa chọn chính sách bỏ bản tin cũ khi ứng dụng nhận UDP không theo kịp tốc độ gửi như thế nào?
Bạn phân biệt unicast, multicast và broadcast UDP theo khả năng hỗ trợ của mạng ra sao?
Bạn đánh giá những điều kiện mạng cần có để ứng dụng sử dụng UDP multicast hoạt động đúng như thế nào?
Bạn phân biệt khả năng bắt đầu gửi dữ liệu không cần handshake của UDP với quy trình bắt tay riêng của ứng dụng ra sao?
Bạn giải thích cách QUIC sử dụng UDP nhưng tự cung cấp độ tin cậy, bảo mật và quản lý luồng như thế nào?
Bạn lựa chọn QUIC hay TCP khi triển khai kết nối có nhiều luồng tương tác dựa trên những đánh đổi nào?
Bạn đánh giá vì sao một firewall cho phép TCP/443 nhưng chặn UDP/443 có thể ảnh hưởng HTTP/3 ra sao?
Bạn giải thích vai trò của socket(), bind(), listen(), accept() và connect() trong lập trình TCP như thế nào?
Bạn mô tả vòng đời của TCP server từ khi bind cổng đến khi phục vụ nhiều client ra sao?
Bạn xử lý trường hợp recv trả về không byte để nhận biết đầu bên kia đã đóng luồng TCP như thế nào?
Bạn thiết kế vòng lặp gửi để xử lý việc send chỉ ghi được một phần buffer ra sao?
Bạn phân biệt blocking và non-blocking socket trong ứng dụng có nhiều kết nối đồng thời như thế nào?
Bạn sử dụng select, poll, epoll hoặc kqueue để xử lý sự kiện socket theo quy mô nào?
Bạn kiểm tra sự khác nhau giữa timeout do socket và timeout do logic xử lý yêu cầu ở tầng ứng dụng ra sao?
Bạn giải thích tác động của SO_REUSEADDR và các tùy chọn socket liên quan khi khởi động lại server như thế nào?
Bạn xác định khi nào bật TCP_NODELAY nhằm giảm độ trễ cho bản tin nhỏ ra sao?
Bạn đánh giá ảnh hưởng của Nagle algorithm lên kết nối có nhiều lần gửi dữ liệu kích thước nhỏ như thế nào?
Bạn phân biệt việc bind socket vào localhost với địa chỉ wildcard đối với khả năng nhận kết nối ra sao?
Bạn thiết kế cơ chế backpressure khi server TCP nhận yêu cầu nhanh hơn khả năng xử lý như thế nào?
Bạn xử lý kết nối bị ngắt giữa chừng khi ứng dụng đang truyền một payload lớn bằng cách nào?
Bạn thiết kế framing và xác thực độ dài thông điệp để tránh đọc sai khi dữ liệu TCP đến từng phần ra sao?
Bạn xác định khi nào ứng dụng UDP cần bind cổng cố định và khi nào có thể dùng cổng động như thế nào?
Bạn phân biệt UDP socket đã gọi connect với TCP socket đã kết nối về mặt bảo đảm giao thức ra sao?
Bạn dùng recvfrom và sendto để hỗ trợ nhiều địa chỉ peer trên cùng một UDP socket như thế nào?
Bạn đánh giá ảnh hưởng của concurrency lên tính đúng thứ tự xử lý các bản tin UDP ở tầng ứng dụng ra sao?
Bạn thiết kế logging và tracing ở ứng dụng để liên kết lỗi socket với địa chỉ peer và thời gian xảy ra như thế nào?
Bạn xác định các metric connection count, handshake failure và bytes in flight có ý nghĩa gì cho dịch vụ TCP?
Bạn sử dụng ping và traceroute để lấy bằng chứng hỗ trợ chẩn đoán TCP mà không suy diễn sai về trạng thái cổng dịch vụ như thế nào?
Bạn sử dụng ss hoặc netstat để kiểm tra các socket LISTEN, ESTABLISHED và TIME-WAIT trên máy chủ ra sao?
Bạn dùng tcpdump để bắt riêng lưu lượng TCP của một cổng và một địa chỉ nguồn như thế nào?
Bạn dùng Wireshark display filter để tách một TCP stream khỏi các kết nối khác ra sao?
Bạn đọc bản bắt gói để kiểm tra một handshake TCP đã hoàn tất trước khi TLS bắt đầu như thế nào?
Bạn dùng biểu đồ TCP stream trong Wireshark để phát hiện giai đoạn dừng truyền hoặc retransmission ra sao?
Bạn đối chiếu TCP sequence và ACK trong hai bản bắt gói ở client và server để định vị mất gói như thế nào?
Bạn phân biệt retransmission được ghi nhận bởi Wireshark với packet loss thực tế trên đường truyền như thế nào?
Bạn nhận diện ảnh hưởng của TSO, GSO, GRO hoặc LRO lên kích thước segment nhìn thấy khi capture ra sao?
Bạn xác định vì sao packet capture tại host có thể hiển thị checksum sai khi ứng dụng vẫn hoạt động bình thường như thế nào?
Bạn đo RTT từ trace TCP và phân biệt RTT mạng với thời gian xử lý ứng dụng như thế nào?
Bạn xác định dấu hiệu zero window, window update và window probe trong Wireshark ra sao?
Bạn phát hiện TCP out-of-order và duplicate ACK trong trace mà không vội kết luận mất gói như thế nào?
Bạn phân tích thời gian giữa SYN đầu tiên và SYN-ACK để tìm nơi phát sinh chậm kết nối ra sao?
Bạn xác định liệu RST được tạo bởi server, load balancer hay thiết bị trung gian dựa trên bằng chứng nào?
Bạn sử dụng tc hoặc công cụ mô phỏng mạng để thử mất gói, độ trễ và giới hạn băng thông như thế nào?
Bạn đánh giá rủi ro khi bắt toàn bộ payload mạng có thể chứa dữ liệu nhạy cảm và cách giới hạn phạm vi thu thập ra sao?
Bạn kiểm tra bằng iperf hoặc công cụ tương đương để ước lượng thông lượng TCP và UDP như thế nào?
Bạn phân biệt báo cáo băng thông gửi, băng thông nhận và packet loss trong phép thử UDP ra sao?
Bạn giải thích sự khác nhau giữa đo packet loss bằng ICMP và nhận định mất gói của ứng dụng TCP như thế nào?
Bạn xây dựng timeline từ log socket, metric hệ điều hành và packet capture để xác định sự kiện gây lỗi ra sao?
Bạn xác định nguyên nhân TCP connect timeout trong khi DNS vẫn phân giải đúng bằng cách nào?
Bạn điều tra tình huống client nhận ECONNREFUSED thay vì timeout khi gọi tới cùng dịch vụ như thế nào?
Bạn phân tích trường hợp kết nối TCP thành công nhưng ứng dụng không nhận được phản hồi trước read timeout ra sao?
Bạn xác định vì sao ứng dụng chạy trên máy chủ truy cập được TCP port nhưng trong container lại thất bại như thế nào?
Bạn điều tra tình huống chỉ có một hướng của phiên TCP đi qua firewall stateful bằng cách nào?
Bạn phân tích tác động của asymmetric routing lên trạng thái TCP và chính sách firewall như thế nào?
Bạn phát hiện NAT gateway cạn cổng nguồn khi nhiều client cùng kết nối một đích như thế nào?
Bạn xác định nguyên nhân server chỉ lỗi với yêu cầu có payload lớn dù handshake TCP thành công ra sao?
Bạn phân biệt lỗi Path MTU Discovery với lỗi cạn receive window dựa trên dấu hiệu nào?
Bạn điều tra tình huống kết nối TCP chạy nhanh trong LAN nhưng chậm rõ rệt trên WAN như thế nào?
Bạn đo ảnh hưởng của RTT, bandwidth-delay product và congestion window tới tốc độ tải file lớn ra sao?
Bạn phân tích nguyên nhân một kết nối TCP bị ngắt đều đặn sau khoảng thời gian không hoạt động ra sao?
Bạn xác định lý do một ứng dụng UDP chỉ mất gói khi số lượng client tăng cao như thế nào?
Bạn điều tra vì sao datagram UDP đến host nhưng không tới tiến trình nhận bằng cách nào?
Bạn phân biệt UDP packet loss ở mạng với packet bị ứng dụng hoặc kernel socket buffer loại bỏ như thế nào?
Bạn thiết kế kịch bản thử nghiệm một ứng dụng UDP chạy qua NAT và mạng di động có thay đổi địa chỉ ra sao?
Bạn đánh giá rủi ro packet reordering đối với đồng bộ trạng thái trong game thời gian thực như thế nào?
Bạn xác định nguyên nhân HTTP/3 thất bại nhưng trình duyệt vẫn kết nối được qua HTTP/2 ra sao?
Bạn xây dựng bộ kiểm thử cho chương trình TCP để bao phủ partial read, partial write và ngắt kết nối giữa chừng như thế nào?
Bạn xây dựng bộ kiểm thử cho chương trình UDP để bao phủ datagram trùng, sai thứ tự và mất gói ra sao?
Bạn tổ chức retry, timeout và idempotency ở tầng ứng dụng để tránh tạo hiệu ứng phụ khi truyền dữ liệu không chắc chắn như thế nào?
Bạn lựa chọn các chỉ số p95 latency, retransmission rate, RTT và packet loss để theo dõi chất lượng một dịch vụ ra sao?
Bạn phân biệt triệu chứng nghẽn CPU tại server với nghẽn mạng dựa trên throughput và socket metrics như thế nào?
Bạn lập runbook chẩn đoán TCP từ DNS, route, SYN, ACK đến đọc ghi ứng dụng theo thứ tự nào?
Bạn tổ chức kiểm tra hai chiều với packet capture ở client và server để xác minh kết nối UDP như thế nào?
Bạn xác định điều kiện nghiệm thu cho ứng dụng cần độ tin cậy cao khi lựa chọn TCP hoặc UDP như thế nào?
Bạn thiết kế phương án truyền dữ liệu đáp ứng mục tiêu độ trễ thấp nhưng vẫn biết khi nào cần xác nhận hoặc gửi lại như thế nào?
Bạn trình bày cách chọn TCP, UDP hoặc giao thức tầng trên dựa trên lỗi mạng có thể xảy ra, yêu cầu nghiệp vụ và giới hạn vận hành ra sao?

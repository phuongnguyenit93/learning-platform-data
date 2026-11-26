Bạn giải thích mục tiêu chính của traffic management đối với độ trễ, thông lượng và độ sẵn sàng của dịch vụ như thế nào?
Bạn phân biệt điều hướng lưu lượng, phân phối tải và điều tiết tốc độ dựa trên mục đích kỹ thuật ra sao?
Bạn xác định những loại traffic quan trọng nhất của một hệ thống từ yêu cầu nghiệp vụ bằng cách nào?
Bạn mô tả đường đi của một request từ client qua DNS, load balancer, proxy đến backend như thế nào?
Bạn nhận diện các điểm có thể điều khiển lưu lượng ở tầng mạng và tầng ứng dụng ra sao?
Bạn phân biệt điều khiển lưu lượng inbound, outbound và east-west trong một kiến trúc dịch vụ như thế nào?
Bạn xây dựng sơ đồ phụ thuộc giữa dịch vụ để đánh giá hậu quả của việc đổi tuyến ra sao?
Bạn lựa chọn các SLO cần bảo vệ trước khi xây dựng chính sách điều tiết traffic dựa trên tiêu chí nào?
Bạn phân biệt mục tiêu tối ưu chi phí với mục tiêu giảm độ trễ trong việc đặt chính sách định tuyến ra sao?
Bạn đánh giá các đánh đổi giữa throughput tối đa, tail latency và tỷ lệ lỗi khi tải tăng như thế nào?
Bạn dự đoán các đỉnh tải theo thời gian trong ngày và theo chiến dịch kinh doanh bằng cách nào?
Bạn xác định những workload có thể trì hoãn so với workload bắt buộc phản hồi tức thời ra sao?
Bạn chọn đơn vị đo lưu lượng theo request, connection, byte hay packet dựa trên ứng dụng như thế nào?
Bạn phân tích sự khác nhau giữa traffic burst ngắn và mức tải cao duy trì liên tục ra sao?
Bạn thiết kế chính sách traffic management có thể thay đổi mà không ảnh hưởng cấu hình không liên quan như thế nào?
Bạn xác định tiêu chí thành công và tiêu chí dừng triển khai trước khi thay đổi chính sách lưu lượng ra sao?
Bạn giải thích cách router chọn tuyến cho một gói tin dựa trên bảng định tuyến như thế nào?
Bạn kiểm tra sự khác nhau giữa route cụ thể và default route khi xác định đường đi thực tế ra sao?
Bạn sử dụng longest-prefix match để lý giải tại sao traffic chọn một tuyến nhất định như thế nào?
Bạn đánh giá vai trò của route metric khi có nhiều đường đi đến cùng mạng đích ra sao?
Bạn xác định khi nào dùng policy-based routing dựa trên nguồn, đích hoặc loại traffic như thế nào?
Bạn thiết kế tách tuyến giữa lưu lượng người dùng, sao lưu và quản trị để giảm tranh chấp tài nguyên ra sao?
Bạn kiểm tra tuyến đi và tuyến về của một kết nối khi routing không đối xứng như thế nào?
Bạn giải thích ảnh hưởng của stateful firewall đến kết nối khi traffic chuyển sang tuyến khác ra sao?
Bạn lựa chọn ECMP để phân tải trên nhiều tuyến có chi phí tương đương theo điều kiện nào?
Bạn phân biệt phân phối ECMP theo flow và phân phối theo packet về rủi ro đảo thứ tự gói ra sao?
Bạn xác định nguyên nhân một đường ECMP quá tải dù tổng băng thông còn dư bằng cách nào?
Bạn đánh giá tác động của hash theo địa chỉ và cổng khi phần lớn traffic thuộc một vài flow lớn như thế nào?
Bạn kiểm soát thay đổi route để tránh tạo loop hoặc làm rơi kết nối đang hoạt động ra sao?
Bạn xác định ảnh hưởng của BGP hoặc routing động tới quá trình chuyển tuyến khi một đường bị lỗi như thế nào?
Bạn đánh giá thời gian hội tụ định tuyến so với yêu cầu phục hồi của ứng dụng như thế nào?
Bạn lựa chọn route ưu tiên và tuyến dự phòng khi đường chính bị mất kết nối ra sao?
Bạn phát hiện một tuyến vẫn tồn tại nhưng chất lượng suy giảm bằng những phép đo nào?
Bạn thiết kế chuyển tuyến dựa trên packet loss, RTT và reachability thay vì chỉ trạng thái link như thế nào?
Bạn cân nhắc chi phí đường truyền liên vùng khi điều hướng traffic qua nhiều tuyến như thế nào?
Bạn xác định các trường hợp VRF hoặc phân đoạn mạng giúp tách chính sách lưu lượng ra sao?
Bạn kiểm tra tác động của NAT và địa chỉ nguồn sau khi đổi tuyến ra Internet như thế nào?
Bạn thiết kế chính sách egress routing cho ứng dụng cần địa chỉ IP nguồn ổn định ra sao?
Bạn phân biệt định tuyến ở tầng IP với định tuyến request ở tầng HTTP như thế nào?
Bạn lựa chọn L4 load balancing hay L7 load balancing theo loại giao thức và yêu cầu xử lý ra sao?
Bạn giải thích cách load balancer phân phối kết nối khác với phân phối từng request như thế nào?
Bạn thiết kế thuật toán round-robin cho nhiều backend có cấu hình tương đương trong trường hợp nào?
Bạn đánh giá giới hạn của round-robin khi request có thời gian xử lý chênh lệch lớn ra sao?
Bạn lựa chọn least connections khi tải được giữ bằng các kết nối dài dựa trên những rủi ro nào?
Bạn phân biệt least connections với least outstanding requests đối với HTTP keepalive và HTTP/2 như thế nào?
Bạn đặt trọng số cho các backend có năng lực xử lý khác nhau dựa trên dữ liệu tải nào?
Bạn kiểm chứng weighted round-robin thực sự phân phối lưu lượng theo tỷ lệ mong muốn như thế nào?
Bạn xác định khi nào cần weighted least connections thay vì chỉ dựa trên số kết nối ra sao?
Bạn dùng consistent hashing cho các yêu cầu có dữ liệu hoặc cache gắn với backend như thế nào?
Bạn đánh giá ảnh hưởng của việc thêm hoặc xóa backend đến phân phối khóa trong consistent hashing ra sao?
Bạn lựa chọn session affinity khi backend lưu trạng thái phiên và đánh giá các hạn chế như thế nào?
Bạn xác định rủi ro hot backend khi nhiều người dùng chia sẻ một địa chỉ IP dưới NAT như thế nào?
Bạn thiết kế loại bỏ phụ thuộc sticky session bằng cách chuyển trạng thái phiên ra kho lưu chung như thế nào?
Bạn phân biệt cân bằng tải nội bộ giữa service với cân bằng tải ở edge public ra sao?
Bạn xây dựng health check để phản ánh khả năng phục vụ nghiệp vụ thay vì chỉ kiểm tra cổng mở như thế nào?
Bạn xác định interval, timeout và ngưỡng lỗi liên tiếp cho health check theo tiêu chí nào?
Bạn phân biệt active health check với passive health check từ lỗi request thực tế như thế nào?
Bạn tránh tình trạng backend bị đánh dấu unhealthy vì chính health check tạo tải quá lớn như thế nào?
Bạn đánh giá nguy cơ health check đồng loạt chuyển trạng thái khi backend chỉ chậm tạm thời ra sao?
Bạn tổ chức cơ chế đưa backend mới vào phục vụ dần để tránh nhận quá nhiều request ngay khi khởi động như thế nào?
Bạn thiết kế connection draining khi backend cần bảo trì mà không cắt ngang các request đang xử lý ra sao?
Bạn xác định cách xử lý kết nối WebSocket dài khi muốn đưa một backend ra khỏi cụm như thế nào?
Bạn kiểm chứng failover của load balancer khi một backend chết giữa lúc xử lý request như thế nào?
Bạn xác định lúc nào nên retry sang backend khác và khi nào retry có thể gây tác dụng phụ trùng lặp ra sao?
Bạn thiết kế retry budget để tránh traffic tăng gấp nhiều lần khi backend lỗi hàng loạt như thế nào?
Bạn điều chỉnh connect timeout và response timeout của load balancer theo thời gian xử lý thực tế như thế nào?
Bạn giải thích vì sao timeout ở client, proxy và backend cần được thiết kế phối hợp ra sao?
Bạn xác định cách dùng outlier detection để tạm loại backend có lỗi cao hơn các backend khác như thế nào?
Bạn xử lý trường hợp toàn bộ backend đều báo unhealthy mà vẫn cần giới hạn thiệt hại như thế nào?
Bạn kiểm tra phân phối request theo từng backend để phát hiện lệch tải do thuật toán hoặc session affinity ra sao?
Bạn lựa chọn địa chỉ đích, hostname hoặc đường dẫn URL để định tuyến traffic ở tầng ứng dụng như thế nào?
Bạn thiết kế routing theo header hoặc cookie khi nhiều phiên bản ứng dụng cùng tồn tại như thế nào?
Bạn xác định ưu tiên và xung đột giữa các quy tắc route theo path, host và điều kiện khác ra sao?
Bạn xây dựng cơ chế phân luồng theo tenant để ngăn một tenant gây nghẽn toàn hệ thống như thế nào?
Bạn lựa chọn geo routing hoặc latency-based routing cho người dùng ở nhiều khu vực như thế nào?
Bạn đánh giá những hạn chế của định tuyến theo vị trí IP khi người dùng sử dụng VPN hoặc mạng di động ra sao?
Bạn thiết kế weighted DNS để dịch chuyển một phần traffic giữa hai cụm theo từng giai đoạn như thế nào?
Bạn xác định tác động của DNS TTL và cache resolver tới tốc độ thay đổi phân phối traffic ra sao?
Bạn kiểm tra lý do DNS đã chuyển tuyến nhưng nhiều client vẫn tiếp tục truy cập đích cũ như thế nào?
Bạn phân biệt điều hướng bằng DNS với cân bằng tải qua proxy ở mức độ kiểm soát kết nối ra sao?
Bạn thiết kế failover liên vùng khi vùng chính không đáp ứng SLO mà DNS vẫn phân giải bình thường như thế nào?
Bạn định nghĩa điều kiện chuyển vùng để tránh flip-flop giữa hai vùng khi tín hiệu sức khỏe dao động ra sao?
Bạn xác định những loại request không thể chuyển vùng an toàn vì dữ liệu hoặc session chưa đồng bộ như thế nào?
Bạn so sánh active-active với active-passive theo yêu cầu độ trễ, dữ liệu và năng lực dự phòng như thế nào?
Bạn xác định năng lực cần dự trữ để vùng dự phòng tiếp nhận traffic sau một lần failover như thế nào?
Bạn thiết kế canary routing để một tỷ lệ nhỏ request đi tới phiên bản mới như thế nào?
Bạn lựa chọn phân luồng canary theo request, user hoặc session để tránh trải nghiệm không nhất quán ra sao?
Bạn sử dụng blue-green routing để chuyển phiên bản với khả năng quay lại nhanh như thế nào?
Bạn kiểm chứng quá trình chuyển route không gây lỗi cho các kết nối hoặc giao dịch đang mở ra sao?
Bạn đánh giá khi nào nên chuyển traffic dựa trên độ trễ thay vì số request mỗi backend ra sao?
Bạn phân tích những vấn đề QoS giải quyết được mà việc tăng băng thông đơn thuần chưa xử lý được ra sao?
Bạn xác định các lớp traffic cần ưu tiên dựa trên mức nhạy cảm với latency, jitter và packet loss ra sao?
Bạn thiết kế phân loại lưu lượng theo IP, port, giao thức hoặc thuộc tính ứng dụng như thế nào?
Bạn phân biệt classification với marking và enforcement trong một chính sách QoS ra sao?
Bạn giải thích ý nghĩa DSCP trong trường IP và cách nó hỗ trợ phân loại dịch vụ như thế nào?
Bạn thiết kế miền tin cậy DSCP khi client có thể tự đánh dấu lưu lượng ưu tiên cao ra sao?
Bạn xác định khi nào cần remark hoặc xóa nhãn DSCP ở biên mạng như thế nào?
Bạn kiểm tra DSCP có được giữ nguyên qua router, tunnel hoặc nhà cung cấp dịch vụ không bằng cách nào?
Bạn cân nhắc khả năng các thiết bị trung gian xử lý DSCP khác nhau trong thiết kế QoS end-to-end như thế nào?
Bạn phân biệt class of service ở tầng liên kết với các chính sách QoS ở tầng IP ra sao?
Bạn xác định điểm nghẽn thực sự mà bộ xếp hàng QoS có thể tác động như thế nào?
Bạn giải thích cơ chế FIFO và rủi ro khi trộn traffic realtime với truyền file dung lượng lớn ra sao?
Bạn lựa chọn strict priority queueing khi có traffic quan trọng nhưng vẫn cần tránh bỏ đói lớp khác như thế nào?
Bạn so sánh weighted fair queueing với weighted round-robin trong phân chia băng thông như thế nào?
Bạn sử dụng deficit round robin khi kích thước packet khác nhau để giữ công bằng ra sao?
Bạn thiết kế nhiều class với băng thông đảm bảo và khả năng dùng băng thông nhàn rỗi như thế nào?
Bạn phân biệt bandwidth reservation với giới hạn băng thông tối đa áp dụng cho một class ra sao?
Bạn đánh giá tác động của kích thước queue lên latency và tỷ lệ mất gói như thế nào?
Bạn nhận diện bufferbloat khi throughput cao nhưng thời gian phản hồi tương tác tăng mạnh ra sao?
Bạn xác định khi nào áp dụng active queue management như RED hoặc CoDel thay vì chỉ tăng bộ đệm ra sao?
Bạn giải thích cách ECN có thể thông báo tắc nghẽn mà không cần loại bỏ packet như thế nào?
Bạn kiểm tra những điều kiện cần để ECN có hiệu quả từ thiết bị mạng đến endpoint ra sao?
Bạn đánh giá ảnh hưởng của QoS tới TCP congestion control và tốc độ phát lại packet như thế nào?
Bạn phân tích tác động của jitter đến cuộc gọi thoại hoặc video trong môi trường có traffic nền lớn ra sao?
Bạn xây dựng bài thử đối chiếu latency, jitter và loss cho từng class trước và sau khi áp dụng QoS như thế nào?
Bạn xác định trường hợp QoS ở một hop không giúp được gì khi nghẽn nằm ở hop khác như thế nào?
Bạn thiết kế QoS cho đường truyền VPN có overhead và MTU nhỏ hơn mạng vật lý như thế nào?
Bạn kiểm tra sự khác biệt giữa chính sách QoS theo chiều egress và chiều ingress trên một interface ra sao?
Bạn giải thích traffic shaping và traffic policing khác nhau ở cách xử lý lưu lượng vượt ngưỡng như thế nào?
Bạn lựa chọn shaping khi cần làm mượt burst nhưng vẫn giữ dữ liệu không bị rơi ngay như thế nào?
Bạn lựa chọn policing khi cần thực thi hợp đồng băng thông và chấp nhận drop hoặc remark ra sao?
Bạn giải thích cơ chế token bucket với token rate và bucket capacity bằng ví dụ lưu lượng thực tế như thế nào?
Bạn tính mức burst cho phép từ bucket size và tốc độ nạp token theo yêu cầu ứng dụng ra sao?
Bạn phân biệt token bucket với leaky bucket về hành vi xử lý burst như thế nào?
Bạn đánh giá hệ quả của bucket quá nhỏ với ứng dụng có traffic hợp lệ nhưng phát sinh từng đợt ra sao?
Bạn thiết kế hierarchy shaping để nhiều tenant dùng chung đường truyền mà vẫn bảo đảm công bằng như thế nào?
Bạn xác định thông số shaping phù hợp khi băng thông đường truyền thực thấp hơn tốc độ cổng mạng ra sao?
Bạn phân tích lý do shaping ở phía gửi có thể tránh packet loss tốt hơn policing tại phía nhận như thế nào?
Bạn kiểm tra vị trí áp dụng rate limit để không giới hạn hai lần trên cùng một luồng ra sao?
Bạn lựa chọn giới hạn theo byte/s hay packet/s khi bảo vệ thiết bị trước các loại traffic khác nhau như thế nào?
Bạn phát hiện trường hợp packet rate cao khiến CPU thiết bị quá tải dù bandwidth chưa đầy bằng cách nào?
Bạn đo hiệu quả policing bằng số packet conform, exceed và bị drop như thế nào?
Bạn tránh việc một lớp traffic bị starvation khi ưu tiên nghiêm ngặt trên đường truyền chật như thế nào?
Bạn xác định chính sách hạ ưu tiên traffic nền khi cuộc gọi trực tuyến bắt đầu như thế nào?
Bạn kiểm tra ảnh hưởng của burst và shaping đến TCP retransmission và goodput ra sao?
Bạn đánh giá khi nào giới hạn tốc độ tại edge sẽ hiệu quả hơn giới hạn ở từng backend như thế nào?
Bạn phân biệt rate limiting theo request với concurrency limiting theo số tác vụ đang xử lý ra sao?
Bạn thiết kế fixed-window rate limiter và xử lý khả năng vượt hạn mức ở ranh giới cửa sổ như thế nào?
Bạn lựa chọn sliding-window log hay sliding-window counter dựa trên độ chính xác và chi phí lưu trạng thái ra sao?
Bạn áp dụng token bucket để cho phép burst ngắn nhưng giữ tốc độ trung bình theo chính sách như thế nào?
Bạn sử dụng leaky bucket khi cần làm đều tốc độ request đi vào một backend có khả năng xử lý ổn định ra sao?
Bạn chọn khóa rate limiting theo IP, API key, user hoặc tenant theo trường hợp nào?
Bạn đánh giá sự thiếu công bằng khi hàng nghìn người dùng đi qua một NAT và bị giới hạn theo IP như thế nào?
Bạn thiết kế nhiều mức quota theo tenant, tài khoản và endpoint mà tránh xung đột chính sách ra sao?
Bạn xác định những endpoint cần rate limit chặt hơn vì có chi phí xử lý hoặc rủi ro abuse cao như thế nào?
Bạn kiểm tra hành vi rate limiter khi nhiều instance cùng nhận request cho một người dùng bằng cách nào?
Bạn lựa chọn state cục bộ hoặc state tập trung cho rate limiter phân tán dựa trên tradeoff nào?
Bạn xử lý clock skew và thao tác đồng thời khi triển khai sliding window phân tán như thế nào?
Bạn thiết kế cơ chế giới hạn toàn cục có thể tiếp tục hoạt động hợp lý khi kho quota gặp sự cố ra sao?
Bạn lựa chọn chính sách fail-open hay fail-closed cho rate limiting tùy độ quan trọng của dịch vụ như thế nào?
Bạn sử dụng HTTP 429 và Retry-After để hướng dẫn client điều chỉnh nhịp gửi request ra sao?
Bạn xác định những thông tin giới hạn còn lại có thể trả về client mà không lộ chính sách bảo vệ nhạy cảm như thế nào?
Bạn đánh giá rủi ro retry dồn dập sau mã 429 làm quá tải tăng thêm như thế nào?
Bạn thiết kế exponential backoff và jitter ở client để tránh nhiều request thử lại đồng thời ra sao?
Bạn kiểm tra sự khác nhau giữa rate limiter trước authentication và sau authentication như thế nào?
Bạn phối hợp giới hạn per-user với giới hạn tổng cho cụm backend theo nguyên tắc nào?
Bạn bảo vệ các endpoint sức khỏe và quản trị khi rate limiting đang kích hoạt dưới tải cao ra sao?
Bạn thiết kế chính sách giới hạn riêng cho request ghi và request đọc có chi phí khác nhau như thế nào?
Bạn tính toán tác động của tỷ lệ retry tới effective request rate trên backend như thế nào?
Bạn xác định tình huống giới hạn theo RPS chưa đủ vì mỗi request có mức tiêu thụ CPU khác nhau ra sao?
Bạn mô tả cơ chế admission control quyết định chấp nhận hoặc từ chối request trước khi backend quá tải như thế nào?
Bạn chọn giới hạn số request đang xử lý dựa trên concurrency, latency và thông lượng bằng cách nào?
Bạn sử dụng định luật Little để liên hệ request rate, thời gian đáp ứng và số request đang xử lý ra sao?
Bạn đánh giá khi nào tăng queue depth làm thời gian chờ tăng nhưng không cải thiện thông lượng như thế nào?
Bạn thiết kế queue giới hạn chiều dài với deadline để tránh xử lý những request đã hết giá trị ra sao?
Bạn phân biệt load shedding với rate limiting chủ động theo tín hiệu vận hành như thế nào?
Bạn lựa chọn tiêu chí loại bỏ request ít quan trọng trước khi hệ thống đạt điểm bão hòa như thế nào?
Bạn thiết kế circuit breaker để ngăn request mới tới backend đang lỗi liên tục ra sao?
Bạn xác định ngưỡng chuyển trạng thái mở và điều kiện half-open của circuit breaker như thế nào?
Bạn kiểm tra nguy cơ nhiều client đồng thời thử lại backend ngay khi circuit breaker đóng như thế nào?
Bạn phân biệt bulkhead isolation với circuit breaker trong bảo vệ tài nguyên giữa các workload ra sao?
Bạn phân chia worker pool hoặc connection pool để traffic nền không làm nghẽn request quan trọng như thế nào?
Bạn đánh giá tác động của retry storm khi nhiều lớp proxy và client cùng tự động retry ra sao?
Bạn thiết kế retry budget theo toàn bộ call chain để tránh nhân tải tại nhiều hop như thế nào?
Bạn phân biệt request có thể retry an toàn với thao tác không idempotent dựa trên semantics nghiệp vụ ra sao?
Bạn lựa chọn timeout cho từng hop để deadline end-to-end không bị vượt quá như thế nào?
Bạn thiết kế truyền deadline từ edge vào các dịch vụ phía sau để không xử lý công việc vô ích ra sao?
Bạn xác định tình huống hedged request giúp giảm tail latency và rủi ro tăng tải kèm theo như thế nào?
Bạn kiểm soát số lượng request dự phòng hoặc speculative request để không tạo quá tải như thế nào?
Bạn lựa chọn cơ chế giảm chất lượng dịch vụ có kiểm soát khi không đủ tài nguyên xử lý như thế nào?
Bạn quyết định ưu tiên giữ chức năng cốt lõi nào trong tình huống hệ thống bị quá tải nghiêm trọng ra sao?
Bạn phân biệt bảo vệ availability với tối đa hóa số request được chấp nhận tại mọi thời điểm như thế nào?
Bạn thiết kế overload control có xét sự khác nhau giữa lỗi tạm thời và lỗi do thiếu công suất kéo dài như thế nào?
Bạn đo tỷ lệ request bị từ chối có chủ đích so với tỷ lệ request lỗi do backend không đáp ứng như thế nào?
Bạn tính đến độ trễ khởi tạo instance khi xác định ngưỡng autoscale để điều tiết tải như thế nào?
Bạn kết hợp autoscaling với rate limiting để ứng phó burst nhanh hơn tốc độ scale như thế nào?
Bạn phân tích tác động của scale-out không đồng đều tới phân phối request và hiệu suất cache như thế nào?
Bạn xác định các nhóm traffic cần ưu tiên trong một hệ thống có SLA khác nhau như thế nào?
Bạn thiết kế chính sách ưu tiên cho request tương tác, batch job và đồng bộ dữ liệu ra sao?
Bạn phân biệt priority queue với hàng đợi công bằng khi nhiều lớp cùng tranh chấp năng lực xử lý như thế nào?
Bạn xử lý nguy cơ traffic ưu tiên thấp không bao giờ được phục vụ khi lớp ưu tiên cao luôn có tải như thế nào?
Bạn áp dụng weighted fairness để phân phối công suất cho nhiều khách hàng theo gói dịch vụ ra sao?
Bạn xác định mức băng thông hoặc năng lực xử lý tối thiểu bảo đảm cho một tenant như thế nào?
Bạn thiết kế chính sách mượn tài nguyên nhàn rỗi mà không làm mất cam kết cho các lớp khác ra sao?
Bạn lựa chọn admission control theo mức độ quan trọng của giao dịch thay vì chỉ dựa trên thứ tự đến như thế nào?
Bạn xử lý traffic không thể phân loại khi có metadata thiếu hoặc sai bằng một lớp mặc định ra sao?
Bạn đánh giá rủi ro khi cho phép client tự gắn header ưu tiên mà proxy tin tưởng tuyệt đối như thế nào?
Bạn thiết kế quy trình kiểm tra và phê duyệt thay đổi thứ tự ưu tiên của một dịch vụ như thế nào?
Bạn xác định cách ghi nhận lý do một request bị điều hướng, giới hạn hoặc từ chối như thế nào?
Bạn tổ chức quy tắc ưu tiên giữa tầng edge và backend để tránh hai lớp có chính sách trái ngược ra sao?
Bạn đo mức công bằng của hệ thống bằng latency và tỷ lệ thành công của từng nhóm người dùng ra sao?
Bạn kiểm tra trường hợp traffic ít quan trọng bị trì hoãn vượt thời hạn nghiệp vụ như thế nào?
Bạn thiết kế ưu tiên theo deadline cho các công việc có hạn xử lý cụ thể như thế nào?
Bạn đánh giá chi phí và độ phức tạp khi dùng nhiều mức ưu tiên thay vì vài lớp traffic rõ ràng như thế nào?
Bạn xác định dấu hiệu traffic ưu tiên cao đang gây ảnh hưởng tới toàn bộ hệ thống bằng cách nào?
Bạn thiết kế phân bổ băng thông cho mạng văn phòng có thoại, video, họp trực tuyến và tải file lớn ra sao?
Bạn thiết kế điều tiết traffic sao lưu database để không ảnh hưởng tới giao dịch trực tuyến như thế nào?
Bạn lựa chọn cách giới hạn các job đồng bộ giữa vùng để tránh nghẽn đường WAN trong giờ cao điểm ra sao?
Bạn kiểm soát traffic giữa microservices khi một service phụ thuộc bị chậm hoặc trả lỗi liên tục như thế nào?
Bạn đánh giá tác động của request fan-out lên tải downstream và giới hạn concurrency như thế nào?
Bạn thiết kế policy cho API public vừa bảo vệ hệ thống vừa giữ công bằng giữa khách hàng như thế nào?
Bạn áp dụng QoS trong mạng container hoặc Kubernetes khi nhiều pod dùng chung node như thế nào?
Bạn xác định giới hạn của QoS ở tầng IP khi traffic qua tunnel, overlay hoặc proxy mã hóa như thế nào?
Bạn lựa chọn điều khiển traffic bằng service mesh hay gateway dựa trên phạm vi và độ phức tạp ra sao?
Bạn phân biệt chức năng traffic splitting của service mesh với phân tải của load balancer bên ngoài ra sao?
Bạn kiểm tra ảnh hưởng của chính sách proxy sidecar lên số hop và độ trễ request như thế nào?
Bạn thiết kế canary cho một microservice sử dụng nhiều upstream có sự phụ thuộc phiên bản ra sao?
Bạn xây dựng cơ chế cô lập traffic thử nghiệm để không tranh tài nguyên với production như thế nào?
Bạn đánh giá việc định tuyến request theo vùng dữ liệu khi có yêu cầu data residency như thế nào?
Bạn kiểm soát chi phí egress khi cần chuyển một phần traffic từ một vùng sang vùng khác ra sao?
Bạn phân tích tình huống CDN hoặc cache tại edge làm thay đổi lượng traffic thực đi tới backend như thế nào?
Bạn thiết kế chính sách fallback khi CDN miss hoặc không thể truy cập origin như thế nào?
Bạn xác định nơi áp dụng rate limit phù hợp khi hệ thống có CDN, API gateway và service mesh ra sao?
Bạn lựa chọn lớp chống traffic bất thường để bảo vệ dịch vụ mà không chặn nhầm request hợp lệ như thế nào?
Bạn quan sát sự khác nhau giữa bandwidth, goodput, packet rate và request rate bằng các phép đo nào?
Bạn lựa chọn các chỉ số p50, p95 và p99 latency khi đánh giá chất lượng điều tiết lưu lượng như thế nào?
Bạn sử dụng request rate, error rate và duration để giám sát hiệu quả điều hướng ở tầng ứng dụng ra sao?
Bạn kết hợp CPU, bộ nhớ, queue depth và connection pool với metric traffic để nhận biết điểm nghẽn như thế nào?
Bạn xác định mức độ bão hòa của backend khi CPU chưa cao nhưng hàng đợi request đã dài ra sao?
Bạn phân tích thay đổi số active connections và connection establishment rate sau khi bật một chính sách mới như thế nào?
Bạn dùng flow logs để xác định nguồn, đích và mức tải của các luồng traffic như thế nào?
Bạn sử dụng packet capture để kiểm tra packet marking, drop hoặc retransmission khi nghi ngờ chính sách QoS ra sao?
Bạn kiểm tra phân phối DSCP trước và sau một thiết bị trung gian bằng cách nào?
Bạn xây dựng dashboard so sánh traffic theo tuyến, vùng, backend và lớp ưu tiên như thế nào?
Bạn quan sát tỷ lệ cache hit, request retry và traffic tới origin để giải thích tải backend như thế nào?
Bạn thiết kế metric cho các quyết định throttle, reject, queue và shed để xác định nguyên nhân request chậm ra sao?
Bạn sử dụng distributed tracing để xác định hop nào tạo thời gian chờ hoặc retry trong chuỗi dịch vụ như thế nào?
Bạn phân biệt traffic tăng thực từ người dùng với traffic tăng do retry nội bộ bằng những tín hiệu nào?
Bạn xác định sự thay đổi phân bố payload size ảnh hưởng đến throughput và chi phí như thế nào?
Bạn lựa chọn cảnh báo dựa trên SLO burn rate thay vì chỉ ngưỡng CPU hoặc băng thông ra sao?
Bạn phát hiện một nhóm tenant bị ảnh hưởng riêng lẻ dù SLO toàn hệ thống vẫn đạt bằng cách nào?
Bạn sử dụng baseline theo thời gian để nhận diện mất cân bằng traffic bất thường ra sao?
Bạn thiết kế log có thể giải thích backend được chọn và chính sách routing nào đã áp dụng ra sao?
Bạn phân biệt lỗi do client bị rate limit với lỗi do proxy hoặc backend overload trong log như thế nào?
Bạn xác định phương pháp lấy mẫu log và trace để tránh observability tự gây thêm tải như thế nào?
Bạn tổ chức đối chiếu số liệu tại router, load balancer, gateway và ứng dụng để kiểm chứng một giả thuyết ra sao?
Bạn lựa chọn công cụ tạo tải để tái hiện request burst, kết nối lâu và traffic đa vùng như thế nào?
Bạn xây dựng bộ workload đại diện có request nhanh, request nặng và luồng streaming như thế nào?
Bạn xác định những yếu tố trong môi trường thử nghiệm cần giống production để kết quả điều tiết đáng tin ra sao?
Bạn kiểm thử đường đi khi một tuyến mạng mất hoàn toàn và thời gian chuyển tuyến bằng cách nào?
Bạn mô phỏng một backend tăng latency nhưng chưa lỗi để kiểm tra thuật toán phân tải như thế nào?
Bạn kiểm tra health-check flapping và tác động lên quá trình đưa backend ra vào nhóm phục vụ ra sao?
Bạn đánh giá độ chính xác của phân phối weighted traffic trên từng cửa sổ thời gian như thế nào?
Bạn kiểm thử hành vi rate limiter ở ranh giới cửa sổ, khi burst và khi nhiều node cùng nhận traffic ra sao?
Bạn xác định mức tải khiến request queue bắt đầu tăng liên tục trong bài thử tải bằng cách nào?
Bạn kiểm thử QoS khi hai loại traffic cùng đẩy đường truyền đến bão hòa như thế nào?
Bạn so sánh loss, jitter và tail latency trước và sau khi áp dụng traffic shaping bằng cách nào?
Bạn xác định dữ liệu chứng minh strict priority đã gây starvation cho lớp ưu tiên thấp như thế nào?
Bạn thiết kế chaos test cắt một vùng hoặc backend trong lúc traffic tăng cao ra sao?
Bạn kiểm thử retry storm và circuit breaker khi một dependency trả lỗi hàng loạt như thế nào?
Bạn đo tác động của autoscaling delay tới khả năng bảo vệ SLO trong một đợt tăng tải bất ngờ ra sao?
Bạn thiết kế kiểm thử fail-open và fail-closed khi kho trạng thái rate limiter mất kết nối như thế nào?
Bạn xác định các trường hợp test phải xác nhận dữ liệu không bị ghi trùng sau failover hoặc retry ra sao?
Bạn chọn chỉ tiêu nghiệm thu về độ trễ, lỗi và tính công bằng trước khi triển khai chính sách traffic management như thế nào?
Bạn tổ chức canary rollout thay đổi traffic policy để chỉ tác động một phần người dùng như thế nào?
Bạn xác định tín hiệu nào kích hoạt rollback tự động khi một cấu hình mới làm giảm chất lượng dịch vụ ra sao?
Bạn thiết kế quy trình thay đổi route với khả năng phục hồi nếu mất kết nối quản trị như thế nào?
Bạn xác định các bước kiểm tra cấu hình và kiểm thử trong CI trước khi áp dụng thay đổi lên proxy hoặc router ra sao?
Bạn phân tích sự khác biệt giữa cấu hình hợp lệ về cú pháp và chính sách đúng theo nghiệp vụ như thế nào?
Bạn quản lý phiên bản, phê duyệt và lịch sử thay đổi của chính sách QoS và rate limiting ra sao?
Bạn kiểm tra xung đột giữa nhiều rule routing, shaping và throttling trước khi đưa vào production như thế nào?
Bạn xây dựng runbook xử lý khi một đường truyền bão hòa dù lưu lượng trung bình vẫn bình thường ra sao?
Bạn điều tra việc một backend bị quá tải dù load balancer còn nhiều backend khỏe như thế nào?
Bạn xác định nguyên nhân hệ thống trả nhiều mã 429 sau khi triển khai limiter mới ra sao?
Bạn phân tích vì sao tail latency tăng sau khi thêm queue dù tỷ lệ lỗi giảm như thế nào?
Bạn kiểm tra trường hợp người dùng một vùng bị định tuyến sang vùng xa sau thay đổi DNS ra sao?
Bạn xác định hướng xử lý khi hệ thống vừa bị tăng RPS vừa bị tăng chi phí mỗi request như thế nào?
Bạn thiết kế kế hoạch giảm tải khẩn cấp theo mức ưu tiên nghiệp vụ trong một sự cố lớn ra sao?
Bạn xác minh dịch vụ thực sự phục hồi theo trải nghiệm từng nhóm người dùng sau khi chuyển tuyến như thế nào?
Bạn tổ chức postmortem để cải thiện chính sách load balancing hoặc overload protection dựa trên số liệu ra sao?
Bạn xác định khi nào cần đầu tư tăng công suất thay vì liên tục siết rate limit và traffic shaping như thế nào?
Bạn cân đối chi phí, mức độ phức tạp và khả năng vận hành của các lớp traffic control trước khi đưa ra kiến trúc ra sao?
Bạn mô tả phương pháp chứng minh một hệ thống traffic management vừa giữ SLO vừa bảo đảm công bằng khi tải tăng như thế nào?

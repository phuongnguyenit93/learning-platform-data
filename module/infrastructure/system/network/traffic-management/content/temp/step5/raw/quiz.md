Câu 1. Khi IP đích khớp các route `10.0.0.0/8`, `10.20.0.0/16` và `10.20.3.0/24`, route nào được ưu tiên?
A. `10.20.3.0/24` vì khớp tiền tố dài nhất
B. `10.20.0.0/16` vì có số subnet nhỏ hơn
C. `10.0.0.0/8` vì có phạm vi mạng rộng hơn
D. `0.0.0.0/0` vì có thể khớp mọi IP đích
Đáp án đúng: A

Câu 2. Default route IPv4 được xét đến khi nào trong quyết định chuyển tiếp?
A. Khi đích được phân giải thành bản ghi DNS A
B. Khi đích đã có route trực tiếp trên cổng LAN
C. Khi đích khớp với route có tiền tố dài nhất
D. Khi không có tuyến nào khớp cụ thể hơn đích
Đáp án đúng: D

Câu 3. Vì sao ECMP thường dùng hash theo luồng thay vì round-robin từng packet?
A. Buộc mọi luồng dùng chung một next-hop cố định
B. Thay đổi địa chỉ IP nguồn theo mỗi gói được gửi
C. Giữ một luồng trên một đường để tránh đảo thứ tự
D. Chuyển mỗi gói tới một đường mới để tránh hàng đợi
Đáp án đúng: C

Câu 4. Policy-based routing có thể lựa chọn đường đi dựa vào dữ kiện nào ngoài IP đích?
A. Thứ tự câu lệnh SQL của ứng dụng đang kết nối
B. IP nguồn hoặc dấu gói dùng theo chính sách
C. Thời điểm cấp phát bộ nhớ của mỗi worker thread
D. Thông tin cookie của người dùng chưa giải mã
Đáp án đúng: B

Câu 5. Đường đi bất đối xứng có thể gây lỗi gì với stateful firewall?
A. Gói phản hồi luôn vượt quá giới hạn DNS TTL
B. Gói phản hồi không khớp trạng thái tại firewall
C. Gói phản hồi bắt buộc đổi từ TCP sang giao thức UDP
D. Gói phản hồi luôn bị giảm kích thước MTU xuống 0
Đáp án đúng: B

Câu 6. Khi next-hop mất kết nối, cơ chế failover routing cần làm gì?
A. Xóa tất cả các tuyến đang hoạt động trong hệ thống
B. Giữ tuyến lỗi nhưng tăng TTL cho gói đang chuyển
C. Loại tuyến lỗi và chuyển sang tuyến hợp lệ dự phòng
D. Giữ tuyến lỗi và tự đổi địa chỉ đích của request
Đáp án đúng: C

Câu 7. Bộ cân bằng tải tầng 4 thường dựa chủ yếu trên thông tin nào để chọn backend?
A. Thông tin mã HTML và nội dung body của phản hồi
B. Thông tin schema SQL và số bảng đang được truy vấn
C. Thông tin địa chỉ IP, cổng và giao thức transport
D. Thông tin đường dẫn URL, cookie và header HTTP
Đáp án đúng: C

Câu 8. Bộ cân bằng tải tầng 7 có thể chia request dựa trên trường nào?
A. Giá trị HTTP Host hoặc đường dẫn của request
B. Địa chỉ MAC của hop đầu tiên trên đường truyền
C. Giá trị TTL của từng IP packet tới backend
D. Số thứ tự TCP của packet đầu tiên trong phiên
Đáp án đúng: A

Câu 9. Weighted round-robin thường hữu ích khi hai backend có năng lực xử lý khác nhau vì sao?
A. Luôn bảo đảm thời gian xử lý giống nhau ở hai node
B. Luôn phân phối request theo số kết nối đang mở
C. Cho mỗi request đi qua mọi backend cùng lúc
D. Có thể phân phối tỷ lệ lượt chọn theo trọng số
Đáp án đúng: D

Câu 10. Thuật toán least-connections ưu tiên backend dựa trên thông số nào?
A. Số địa chỉ IP đang lưu trong bảng route
B. Số gói SYN đã bị drop tại từng backend
C. Số kết nối đang hoạt động tại từng backend
D. Số request đã xử lý trong toàn bộ lịch sử
Đáp án đúng: C

Câu 11. Vì sao least-connections không luôn tương đương lựa chọn backend ít tải nhất?
A. Mỗi kết nối luôn có cùng kích thước response body
B. Mỗi kết nối dùng lượng tài nguyên khác nhau
C. Mỗi kết nối chỉ tồn tại được trên một mạng con
D. Mỗi kết nối bắt buộc chỉ xử lý một request trong đời
Đáp án đúng: B

Câu 12. Consistent hashing hữu ích khi thay đổi số backend nhờ ưu điểm nào?
A. Tự động ngăn mọi backend lỗi trong khi deploy
B. Bảo đảm mỗi backend nhận số request bằng nhau
C. Thay thế hoàn toàn các bước health check
D. Giảm số khóa hoặc session phải ánh xạ lại
Đáp án đúng: D

Câu 13. Session affinity có rủi ro nào nếu dữ liệu phiên chỉ nằm trên một instance?
A. Phiên có thể mất khi instance đó ngừng hoạt động
B. Phiên luôn được di chuyển tức thời sang node mới
C. Phiên bắt buộc tồn tại trên mọi backend cùng lúc
D. Phiên tự chuyển thành dữ liệu cache DNS TTL
Đáp án đúng: A

Câu 14. Active health check của load balancer có đặc điểm nào?
A. Chỉ theo dõi dung lượng đĩa của máy load balancer
B. Chủ động gửi probe định kỳ đến backend để kiểm tra
C. Chỉ suy luận lỗi qua response của request người dùng
D. Chỉ dựa vào cache DNS mà không kết nối backend
Đáp án đúng: B

Câu 15. Passive health check nhận biết backend lỗi bằng cách nào?
A. Chỉ hỏi DNS authoritative để xác nhận uptime
B. Chỉ đọc trạng thái heartbeat của host cloud
C. Theo dõi timeout và phản hồi lỗi từ traffic thực
D. Luôn gửi request probe độc lập theo mỗi một giây
Đáp án đúng: C

Câu 16. Connection draining khi gỡ backend khỏi pool chủ yếu nhằm mục đích gì?
A. Ngắt tức thời mọi kết nối cũ để hạ tải nhanh nhất
B. Chuyển tất cả packet của kết nối cũ sang DNS
C. Buộc mỗi client mở thêm kết nối mới vào backend
D. Ngừng nhận kết nối mới nhưng cho kết nối cũ hoàn tất
Đáp án đúng: D

Câu 17. Retry tự động với request thanh toán không có idempotency key có nguy cơ nào?
A. Thực hiện nghiệp vụ hai lần khi phản hồi đầu bị mất
B. Giảm số lượng packet vì không phải gửi request mới
C. Luôn chuyển request thanh toán sang phương thức GET
D. Bảo đảm kết quả chỉ thực thi một lần theo mặc định
Đáp án đúng: A

Câu 18. Trong QoS mạng IP, DSCP thường được đặt tại đâu để đánh dấu lớp lưu lượng?
A. Trường cookie của HTTP request để nhận diện lớp
B. Trường source port trong TCP header để nhận diện lớp
C. Trường DSCP của IP header để phân lớp QoS
D. Trường TTL trong DNS response để nhận diện lớp
Đáp án đúng: C

Câu 19. Phân loại traffic theo QoS trước khi xếp hàng có tác dụng gì?
A. Loại bỏ hoàn toàn hàng đợi trên đường truyền bận
B. Thay địa chỉ IP đích theo ứng dụng đang sử dụng
C. Biến mọi packet thành cùng một tốc độ đường truyền
D. Gán gói vào lớp dịch vụ với chính sách xử lý phù hợp
Đáp án đúng: D

Câu 20. Hạn chế quan trọng của hàng đợi strict-priority khi luôn có lưu lượng ưu tiên cao là gì?
A. Lớp ưu tiên cao luôn bị loại bỏ khi tăng tốc độ
B. Lớp ưu tiên thấp luôn có cùng độ trễ với lớp cao
C. Lớp ưu tiên thấp có thể bị thiếu cơ hội truyền
D. Lớp ưu tiên cao bị giới hạn vào đúng một packet
Đáp án đúng: C

Câu 21. Weighted fair queuing giúp chia sẻ một đường truyền bận theo cách nào?
A. Phân bổ phần phục vụ giữa các lớp dựa trên trọng số
B. Chỉ phục vụ lớp ưu tiên cao cho tới khi rỗng hoàn toàn
C. Phân phối gói ngẫu nhiên không xét trọng số hay lớp
D. Xóa mọi lớp ưu tiên và chuyển sang FIFO duy nhất
Đáp án đúng: A

Câu 22. Nếu một lớp QoS được đặt trọng số cao hơn, điều nào thường đúng khi các lớp đều có traffic?
A. Lớp đó có thể được phục vụ tỷ phần lớn hơn
B. Lớp đó bắt buộc sử dụng IP public riêng biệt
C. Lớp đó luôn được bảo đảm không có packet loss
D. Lớp đó luôn nhận một cổng TCP riêng trên router
Đáp án đúng: A

Câu 23. Traffic shaping xử lý lưu lượng vượt tốc độ cấu hình thường theo cách nào?
A. Tự chuyển packet sang một giao thức mới nhanh hơn
B. Đổi DNS TTL để giảm tốc độ ứng dụng gửi request
C. Giữ trong hàng đợi để gửi trễ khi có khả năng
D. Drop ngay mọi packet vượt ngưỡng ở thời điểm đó
Đáp án đúng: C

Câu 24. Khác với shaping, traffic policing thường xử lý packet vượt giới hạn thế nào?
A. Luôn lưu vô hạn packet vượt mức để gửi trễ
B. Drop hoặc remark packet vượt mức chính sách
C. Tự thêm server mới để chuyển mọi packet vượt mức
D. Chuyển packet vượt mức thành bản ghi DNS
Đáp án đúng: B

Câu 25. Token bucket cho phép burst trong giới hạn nào khi token được tích lũy đầy?
A. Chỉ cho phép một packet trong mỗi một giây
B. Cho phép burst không giới hạn khi link đang rảnh
C. Từ chối mọi burst dù bucket còn nhiều token
D. Cho burst tới mức token đã tích lũy
Đáp án đúng: D

Câu 26. Bucket chứa tối đa 200 token, refill 100 token/giây, mỗi request tốn một token. Khi bucket đầy có thể nhận ngay tối đa bao nhiêu request?
A. 200 request trước khi cần chờ token nạp thêm
B. 400 request trước khi cần chờ token nạp thêm
C. 100 request trước khi cần chờ token nạp thêm
D. 300 request trước khi cần chờ token nạp thêm
Đáp án đúng: A

Câu 27. Leaky bucket ở mô hình hàng đợi đầu ra giúp đạt mục tiêu nào?
A. Làm đều tốc độ thoát lưu lượng qua một giới hạn
B. Thay thế mọi cơ chế xếp hàng của lớp QoS khác
C. Bảo đảm packet không bao giờ bị drop khi hàng đầy
D. Cho phép mọi burst lớn thoát ra tức thời không chờ
Đáp án đúng: A

Câu 28. Hiện tượng bufferbloat thường gây hậu quả nào trên đường truyền bị tải nặng?
A. Độ trễ giảm vì hàng đợi luôn làm rỗng packet
B. Tốc độ vật lý của đường truyền tăng theo queue
C. Giới hạn MTU tự động tăng khi hàng đợi đầy
D. Độ trễ tăng do packet nằm lâu trong hàng đợi lớn
Đáp án đúng: D

Câu 29. CoDel là cơ chế quản lý hàng đợi chủ động hướng đến mục tiêu nào?
A. Thay route theo DNS TTL của đích đã cache
B. Giảm trễ hàng đợi kéo dài bằng tín hiệu nghẽn
C. Tăng vô hạn dung lượng buffer trước khi drop
D. Bảo đảm mọi TCP connection có cùng throughput
Đáp án đúng: B

Câu 30. ECN cho phép bộ định tuyến hỗ trợ báo hiệu nghẽn như thế nào?
A. Giảm số hop được phép đi qua trong bảng định tuyến
B. Thay IP đích của mọi packet qua router bị bận
C. Xóa receive window của TCP bên nhận lập tức
D. Đánh dấu gói hỗ trợ ECN thay vì phải drop ngay
Đáp án đúng: D

Câu 31. Tại sao đánh dấu DSCP ở nguồn vẫn chưa bảo đảm QoS xuyên suốt?
A. Giá trị DSCP chỉ tồn tại trong bản ghi DNS của host
B. Các hop tiếp theo có thể bỏ qua hoặc remark DSCP
C. Router luôn ưu tiên DSCP cao nhất trên mọi mạng
D. Giá trị DSCP tự đổi theo số thứ tự TCP của packet
Đáp án đúng: B

Câu 32. API trả HTTP 429 thường biểu thị tình huống nào liên quan traffic management?
A. Backend bị lỗi cú pháp SQL trong database chính
B. Client thiếu chứng chỉ tin cậy khi bắt tay TLS
C. Client gửi vượt giới hạn request đang áp dụng
D. Gateway chuyển request thành công sang upstream
Đáp án đúng: C

Câu 33. Header `Retry-After` đi cùng HTTP 429 giúp client quyết định điều gì?
A. Thời điểm nên thử lại sau khi bị giới hạn tốc độ
B. Thời điểm cần xóa mọi credential đang lưu
C. Thời điểm load balancer phải restart backend
D. Thời điểm đổi DNS server cho các request sau
Đáp án đúng: A

Câu 34. Rate limit theo IP có thể thiếu công bằng với người dùng sau cùng NAT vì sao?
A. NAT luôn xóa header xác thực của HTTP client
B. Mỗi người luôn dùng địa chỉ public IP khác nhau
C. Nhiều người có thể chia sẻ một địa chỉ IP nguồn
D. NAT luôn chuyển request thành UDP mà không báo
Đáp án đúng: C

Câu 35. Trong hệ thống nhiều API gateway, rate limit toàn cục cần chú ý điều gì?
A. Chỉ cần tính số packet ICMP tại router ngoài cùng
B. Đồng bộ bộ đếm hoặc ngân sách giữa các gateway
C. Chỉ cần tăng DNS TTL để giữ một địa chỉ gateway
D. Mỗi gateway tự giữ hạn mức độc lập nhưng gọi là toàn cục
Đáp án đúng: B

Câu 36. Giới hạn số request đang xử lý đồng thời khác RPS limit ở điểm nào?
A. Khống chế riêng số request hoàn tất mỗi phút
B. Giới hạn request đang được xử lý cùng lúc
C. Khống chế trực tiếp số packet bị drop tại đường truyền
D. Khống chế riêng số DNS query đã được cache
Đáp án đúng: B

Câu 37. Admission control giúp ngăn quá tải bằng cơ chế nào?
A. Từ chối hoặc xếp hàng yêu cầu trước khi vượt khả năng
B. Cho mọi request đi vào backend kể cả khi đã đầy
C. Tăng số lần retry khi backend báo thiếu tài nguyên
D. Chuyển mọi request từ HTTPS thành HTTP thường
Đáp án đúng: A

Câu 38. Circuit breaker giúp hệ thống giảm lỗi lan truyền khi upstream liên tục thất bại bằng cách nào?
A. Thay thế toàn bộ health check bằng DNS TXT record
B. Buộc thử lại mọi request ngay khi upstream trả lỗi
C. Chặn tất cả các service khác dù còn hoạt động tốt
D. Fail fast thay vì tiếp tục gọi upstream lỗi nhiều lần
Đáp án đúng: D

Câu 39. Bulkhead isolation nhằm bảo vệ khả dụng bằng biện pháp nào?
A. Tách ngân sách tài nguyên giữa các dependency
B. Đẩy mọi request vào một hàng đợi không giới hạn
C. Tắt toàn bộ timeout cho các request đi qua gateway
D. Gộp mọi dependency vào một pool kết nối chung
Đáp án đúng: A

Câu 40. Backpressure trong hệ thống xử lý luồng cho biết điều gì?
A. Consumer chậm yêu cầu producer tăng gấp đôi tốc độ
B. Producer chuyển mọi message sang một DNS resolver
C. Producer tự phát lại mọi message cho mọi consumer
D. Consumer chậm báo producer giảm tốc độ phát dữ liệu
Đáp án đúng: D

Câu 41. Load shedding khi backend gần hết năng lực có thể áp dụng chiến lược nào?
A. Nhận mọi yêu cầu và tăng vô hạn hàng chờ
B. Vô hiệu mọi health check đến khi tải giảm
C. Buộc tất cả client liên tục retry không giới hạn
D. Từ chối một phần yêu cầu ít ưu tiên để giữ SLO
Đáp án đúng: D

Câu 42. Jitter kết hợp exponential backoff giúp hạn chế vấn đề nào khi nhiều client retry?
A. Chuyển request retry sang đường định tuyến khác
B. Giảm các đợt retry đồng loạt gây tăng tải đột biến
C. Đảm bảo tất cả client retry đúng cùng một thời điểm
D. Đảm bảo mọi request retry đều không có độ trễ
Đáp án đúng: B

Câu 43. Theo dõi p99 latency thay vì chỉ trung bình đặc biệt có ích khi nào?
A. Khi cần tính chính xác dung lượng đĩa của backend
B. Khi cần phát hiện request chậm ở đuôi phân bố
C. Khi chỉ cần liệt kê endpoint của load balancer
D. Khi chỉ cần biết tổng số instance đang hoạt động
Đáp án đúng: B

Câu 44. Trước khi áp dụng rule QoS/rate limit mới lên production, cách kiểm thử nào tốt nhất?
A. Chỉ thử một request khi hệ thống không có traffic
B. Chỉ đo CPU trung bình rồi bỏ qua lỗi và p99
C. Test tải đại diện, đo SLO, chuẩn bị rollback
D. Chỉ dựa trên benchmark của một thiết bị khác
Đáp án đúng: C

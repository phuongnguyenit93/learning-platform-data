Câu 1. TCP cung cấp kiểu dữ liệu nào cho ứng dụng ở tầng transport?
A. Chuỗi datagram luôn giữ nguyên ranh giới message
B. Các frame Ethernet được phân chia theo cổng
C. Luồng byte theo thứ tự, không giữ ranh giới message
D. Các bản ghi được tách riêng theo mỗi lệnh send
Đáp án đúng: C

Câu 2. Đặc điểm nào đúng khi ứng dụng nhận dữ liệu qua UDP socket?
A. Mỗi lần nhận luôn trả về một byte của luồng
B. Mỗi lần nhận luôn gom nhiều datagram thành luồng
C. Mỗi lần nhận một datagram, có thể bị cắt
D. Mỗi lần nhận chỉ trả dữ liệu sau ba bước bắt tay
Đáp án đúng: C

Câu 3. Cơ chế nào giúp TCP khôi phục dữ liệu bị mất trên đường truyền?
A. ACK và truyền lại segment chưa xác nhận
B. Checksum kết hợp tự tái tạo các byte bị mất
C. TTL kết hợp phát lại gói từ router gần nhất
D. DNS kết hợp gửi lại payload đến máy nguồn
Đáp án đúng: A

Câu 4. Phát biểu nào đúng về độ tin cậy mặc định của UDP?
A. Tự phát lại khi không nhận ACK từ phía đích
B. Tự sắp xếp lại datagram theo số sequence
C. Không tự bảo đảm phát lại datagram bị mất
D. Tự loại bỏ bản ghi trùng nhờ cửa sổ trượt
Đáp án đúng: C

Câu 5. Thứ tự bắt tay ba bước chuẩn khi mở kết nối TCP là gì?
A. Client SYN, server ACK, client SYN-ACK
B. Client SYN-ACK, server SYN, client ACK
C. Client SYN, server SYN-ACK, client ACK
D. Client ACK, server SYN-ACK, client SYN
Đáp án đúng: C

Câu 6. Trong TCP, cờ SYN ảnh hưởng ra sao đến sequence number?
A. SYN không liên quan đến sequence hoặc ACK number
B. SYN chiếm một vị trí trong không gian sequence
C. SYN tiêu thụ số byte bằng kích thước TCP header
D. SYN chỉ tăng ACK number ở server sau nhận dữ liệu
Đáp án đúng: B

Câu 7. Gói SYN-ACK của server trong handshake TCP thể hiện điều gì?
A. Vừa truyền toàn bộ dữ liệu vừa kết thúc kết nối
B. Vừa xác nhận SYN client vừa gửi SYN của server
C. Vừa giảm congestion window vừa mở lại phiên
D. Vừa đóng socket client vừa cho phép tái sử dụng port
Đáp án đúng: B

Câu 8. Khi TCP gửi ACK number bằng 501, giá trị đó thường có nghĩa gì?
A. Bên nhận đã gửi 501 ACK riêng biệt trong phiên
B. Bên nhận yêu cầu phía gửi phát lại toàn bộ 501 byte
C. Bên nhận đã nhận chính xác 501 segment dữ liệu
D. Bên nhận đang mong đợi byte có số thứ tự 501
Đáp án đúng: D

Câu 9. Sequence number trong TCP thông thường được tính theo đơn vị nào?
A. Vị trí byte trong luồng của mỗi chiều truyền
B. Số datagram UDP được nhận trong một socket
C. Số lượng gói IP đã đi qua mỗi router trung gian
D. Số request ứng dụng đã gửi trong một kết nối
Đáp án đúng: A

Câu 10. TCP nhận một segment đến sai thứ tự thường xử lý thế nào?
A. Tự chuyển luồng sang UDP để bỏ đoạn bị thiếu
B. Luôn đẩy payload sai thứ tự lên ứng dụng ngay
C. Có thể giữ tạm để tái lắp và giao byte đúng thứ tự
D. Tự đóng kết nối bất kể segment còn lại ra sao
Đáp án đúng: C

Câu 11. Các ACK lặp cùng giá trị trong TCP thường gợi ý điều gì?
A. Handshake TLS đã cấp chứng chỉ mới cho client
B. Có thể có một segment dữ liệu đang bị thiếu
C. Router đã đổi địa chỉ IP của TCP server
D. Ứng dụng đã hoàn thành việc đọc toàn bộ dữ liệu
Đáp án đúng: B

Câu 12. Tùy chọn TCP SACK hỗ trợ phía gửi xử lý mất gói như thế nào?
A. Báo thời gian TTL của packet tại router
B. Báo độ dài URL mà server vừa phản hồi
C. Báo port dự phòng khi connection bị từ chối
D. Báo các dải byte đã nhận ngoài thứ tự
Đáp án đúng: D

Câu 13. Khi TCP retransmission timer hết hạn, hành động thường gặp là gì?
A. Thay đổi IP đích của socket sang router khác
B. Gửi lại dữ liệu chưa được ACK theo cơ chế RTO
C. Đổi cổng UDP để tiếp tục cùng luồng dữ liệu
D. Xóa toàn bộ receive buffer trước lần gửi tiếp
Đáp án đúng: B

Câu 14. Fast retransmit TCP thường được kích hoạt bởi tín hiệu nào?
A. Nhận một HTTP response có status code lỗi
B. Nhận ICMP echo reply có thời gian RTT thấp
C. Nhận DNS answer với TTL nhỏ hơn một giây
D. Nhận đủ ACK trùng lặp gợi ý segment bị mất
Đáp án đúng: D

Câu 15. Ước lượng RTT có tác dụng trực tiếp nào trong TCP?
A. Giúp quyết định địa chỉ MAC của default gateway
B. Giúp xác định port mà DNS server đang mở
C. Giúp tính thời gian chờ retransmission phù hợp
D. Giúp tăng độ dài IPv4 address trong socket
Đáp án đúng: C

Câu 16. TCP MSS đại diện cho kích thước của thành phần nào?
A. Toàn bộ frame Ethernet gồm cả header
B. Toàn bộ datagram IP gồm cả IP header
C. Bộ nhớ đệm nhận TCP của một ứng dụng
D. Payload tối đa của một TCP segment
Đáp án đúng: D

Câu 17. Với Ethernet MTU 1500, IPv4 header 20 byte, TCP header 20 byte và không thêm option, MSS là bao nhiêu?
A. 1480 byte payload TCP mỗi segment
B. 1520 byte payload TCP mỗi segment
C. 1500 byte payload TCP mỗi segment
D. 1460 byte payload TCP mỗi segment
Đáp án đúng: D

Câu 18. Trong IPv4, thông báo ICMP Fragmentation Needed có thể giúp xử lý vấn đề nào?
A. Phát hiện DNS resolver trả về tên miền sai
B. Phát hiện MTU nhỏ trên đường đi khi bật DF
C. Phát hiện ứng dụng đã đọc hết socket buffer
D. Phát hiện listener TCP đã tắt trên server
Đáp án đúng: B

Câu 19. TCP receive window được phía nhận quảng bá chủ yếu để làm gì?
A. Đo số kết nối TCP đang chờ ở cổng lắng nghe
B. Xác định số route mà kernel có thể quản lý
C. Đo mức bão hòa router trên toàn đường truyền mạng
D. Báo bộ đệm còn trống để điều tiết bên gửi
Đáp án đúng: D

Câu 20. Khi bên nhận quảng bá TCP zero window, phía gửi thường làm gì?
A. Bỏ qua cửa sổ nhận và tăng tốc độ truyền dữ liệu
B. Chuyển dữ liệu mới sang UDP mà không hỏi ứng dụng
C. Tạm dừng dữ liệu mới và có thể gửi window probe
D. Đóng ngay kết nối bằng RST không cần xác nhận
Đáp án đúng: C

Câu 21. Congestion window (cwnd) trong TCP phản ánh giới hạn nào?
A. Giới hạn dữ liệu bay theo mức nghẽn mạng
B. Số bản ghi DNS được lưu lại trong cache
C. Lượng dữ liệu ứng dụng đã đọc khỏi receive buffer
D. Số cổng TCP đang sử dụng trên máy client
Đáp án đúng: A

Câu 22. Lượng dữ liệu TCP chưa được ACK thường bị giới hạn bởi điều gì?
A. Chỉ kích thước send buffer mà không có cửa sổ
B. Giá trị lớn hơn giữa cwnd và receive window
C. Chỉ tổng số port TCP trong dải ephemeral
D. Giá trị nhỏ hơn giữa cwnd và receive window
Đáp án đúng: D

Câu 23. Trong TCP slow start, congestion window thường tăng theo xu hướng nào?
A. Giảm một nửa sau mỗi ACK được xác nhận
B. Tăng chậm, chỉ một byte sau mỗi RTT khi đủ ACK
C. Tăng gần gấp đôi mỗi RTT khi đủ ACK
D. Giữ cố định cho đến khi kết nối bị đóng
Đáp án đúng: C

Câu 24. Trong congestion avoidance kiểu AIMD, khi không có nghẽn, cwnd thường tăng thế nào?
A. Tăng gần tuyến tính theo thời gian RTT
B. Giảm liên tục dù mạng không có dấu hiệu nghẽn
C. Tăng gần gấp đôi sau từng gói ACK
D. Giữ bằng 0 cho tới khi có gói bị mất
Đáp án đúng: A

Câu 25. Sau khi TCP phát hiện mất gói do timeout, phản ứng kiểm soát nghẽn thường là gì?
A. Tăng cwnd tối đa để gửi lại nhanh hơn
B. Giảm mạnh cwnd rồi phục hồi theo thuật toán
C. Giữ nguyên cwnd vì timeout chỉ thuộc DNS
D. Tắt flow control của receiver tới cuối phiên
Đáp án đúng: B

Câu 26. ECN được hỗ trợ trong TCP/IP có thể báo hiệu nghẽn mạng bằng cách nào?
A. Đánh dấu gói có nghẽn thay vì bắt buộc drop
B. Bắt buộc hủy mọi gói khi queue gần đầy
C. Thay địa chỉ IP bằng địa chỉ của router nghẽn
D. Tự tăng receive window ở phía ứng dụng
Đáp án đúng: A

Câu 27. Hiện tượng head-of-line blocking của một TCP byte stream xảy ra khi nào?
A. Byte đến sau phải chờ byte còn thiếu phía trước
B. Một datagram đến sau luôn vượt datagram đến trước
C. Mỗi ACK phải chờ DNS phân giải hostname xong
D. Mỗi socket chỉ cho phép một packet được gửi
Đáp án đúng: A

Câu 28. UDP cung cấp cam kết nào về thứ tự đến của các datagram?
A. Bảo đảm thứ tự bằng sequence number tích hợp
B. Không bảo đảm thứ tự datagram khi đến bên nhận
C. Bảo đảm thứ tự thông qua ACK bắt buộc của UDP
D. Bảo đảm thứ tự nhờ tự sắp xếp tại router
Đáp án đúng: B

Câu 29. Lý do nào khiến ứng dụng thoại thời gian thực có thể chọn UDP?
A. Luôn có congestion control TCP tích hợp
B. Tự sửa mọi lỗi bit nhờ checksum của UDP
C. Không bị UDP buộc chờ phát lại gói cũ
D. Luôn bảo đảm mọi gói đến đúng thời điểm
Đáp án đúng: C

Câu 30. QUIC sử dụng UDP nhưng vẫn có thể cung cấp tính năng nào?
A. ACK của TCP cho từng QUIC packet trực tiếp
B. Luồng UDP được tự bảo đảm thứ tự bởi kernel
C. Bắt tay ba bước TCP trước mọi UDP datagram
D. Luồng tin cậy và kiểm soát nghẽn ở tầng QUIC
Đáp án đúng: D

Câu 31. Kết nối TCP cùng lúc trên host được phân biệt chủ yếu bằng bộ nào?
A. Bộ bốn IP/port nguồn và IP/port đích
B. IP đích, subnet mask, số hop và TCP MSS
C. Hostname, địa chỉ gateway, DNS TTL và MSS
D. MAC nguồn, port nguồn, subnet và DNS TTL
Đáp án đúng: A

Câu 32. Khi TCP client kết nối đến server port 443, client port thường là gì?
A. Cổng 53 được chọn để truy vấn tên miền
B. Một cổng ephemeral được hệ điều hành chọn
C. Cổng 80 cố định cho toàn bộ TCP client
D. Cổng 443 được đồng bộ bắt buộc với server
Đáp án đúng: B

Câu 33. Khi ứng dụng dùng TCP `recv`, có thể xảy ra điều gì dù phía gửi gọi `send` một lần?
A. Một lần recv luôn đọc đúng một message ứng dụng
B. Một lần recv luôn trùng toàn bộ payload vừa send
C. Một lần recv chỉ nhận một phần payload đã gửi
D. Một lần recv luôn trả về ranh giới packet IP
Đáp án đúng: C

Câu 34. Với UDP, một lần `recvfrom` thông thường tương ứng với đơn vị nào?
A. Một datagram, có thể bị cắt nếu buffer nhỏ
B. Một thông điệp luôn được tự động truyền lại
C. Một luồng byte có thể chứa nhiều datagram
D. Một đoạn TCP được ghép lại từ nhiều segment
Đáp án đúng: A

Câu 35. Việc gọi `connect()` trên UDP socket thường tạo ra hiệu ứng gì?
A. Buộc server trả SYN-ACK trước mỗi lần send
B. Chọn peer mặc định mà không có handshake
C. Bắt đầu three-way handshake trước datagram
D. Chuyển UDP socket sang TCP stream tự động
Đáp án đúng: B

Câu 36. Lệnh TCP `connect()` trên client nhằm thực hiện bước gì?
A. Đặt UDP peer mặc định cho mọi datagram
B. Bắt đầu kết nối đến IP và port đích
C. Đặt socket vào trạng thái LISTEN như server
D. Đọc ngay dữ liệu từ receive buffer đã có
Đáp án đúng: B

Câu 37. Trên TCP server, `accept()` thành công thường tạo ra gì?
A. Một socket mới lắng nghe trên port khác
B. Một UDP datagram đã được nhận không kết nối
C. Một DNS lookup thành công từ hệ điều hành
D. Socket mới đại diện cho một kết nối đã nhận
Đáp án đúng: D

Câu 38. Cờ TCP FIN trong quá trình đóng kết nối thường biểu thị điều gì?
A. Kết thúc chiều gửi; FIN chiếm một số thứ tự
B. Hai phía lập tức xóa mọi dữ liệu chưa đọc trong socket
C. Một phía yêu cầu đổi sang UDP để giữ kết nối
D. Hai phía cùng gửi SYN mới để thay kết nối cũ
Đáp án đúng: A

Câu 39. Khi TCP nhận cờ RST hợp lệ, điều gì thường xảy ra?
A. Kết nối bị reset thay vì đóng tuần tự bằng FIN
B. Kết nối chuyển sang trạng thái ESTABLISHED mới
C. Kết nối tự phát lại toàn bộ dữ liệu bằng UDP
D. Kết nối thay đổi receive window mà không bị đóng
Đáp án đúng: A

Câu 40. Trạng thái TCP TIME_WAIT ở phía chủ động đóng có mục đích chính nào?
A. Giữ dữ liệu ứng dụng mãi trong bộ nhớ đệm nhận
B. Chờ DHCP cấp địa chỉ IP mới cho client
C. Chờ DNS tạo lại bản ghi cho server đã đóng
D. Chờ gói cũ qua đi và cho phép gửi lại ACK
Đáp án đúng: D

Câu 41. Checksum trong UDP và TCP có chức năng quan trọng nào?
A. Bảo đảm datagram đến đúng thứ tự đã gửi
B. Bảo đảm thời gian giao dữ liệu không đổi
C. Tự động phát lại tất cả gói bị mất trên mạng
D. Phát hiện bit lỗi trong header và payload
Đáp án đúng: D

Câu 42. Lệnh `tcpdump -i eth0 'tcp port 443'` lọc loại traffic nào?
A. Gói ICMP có source hoặc destination port 443
B. Gói ARP có source hoặc destination port 443
C. Gói TCP có source hoặc destination port 443
D. Gói UDP có source hoặc destination port 443
Đáp án đúng: C

Câu 43. Trong Wireshark, bộ lọc hiển thị nào giúp rà các TCP retransmission được suy luận?
A. `tcp.analysis.window_update`
B. `tcp.analysis.retransmission`
C. `tcp.analysis.duplicate_ack`
D. `tcp.analysis.bytes_in_flight`
Đáp án đúng: B

Câu 44. Khi client gửi SYN và server phản hồi ngay bằng RST vì không có listener, biểu hiện thường là gì?
A. Kết nối bị từ chối thay vì chờ hết hạn
B. Kết nối thành công vì RST là SYN-ACK
C. Kết nối chuyển sang UDP khi nhận RST
D. Kết nối chờ hết hạn do SYN luôn bị drop
Đáp án đúng: A

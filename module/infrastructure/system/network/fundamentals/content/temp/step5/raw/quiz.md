1. Thiết bị chọn next hop dựa trên địa chỉ IP để chuyển gói giữa các mạng hoạt động ở tầng OSI nào?
A. Data Link (tầng 2), chuyển frame bằng địa chỉ MAC nguồn.
B. Transport (tầng 4), gửi dữ liệu theo cổng TCP hoặc UDP.
C. Network (tầng 3), xử lý định tuyến gói IP qua các mạng.
D. Application (tầng 7), xử lý yêu cầu ứng dụng của người dùng.
Đáp án đúng: C

2. Switch Ethernet lớp 2 thường dựa vào thông tin gì để chọn cổng chuyển frame unicast?
A. Địa chỉ IP đích đối chiếu bảng định tuyến của router.
B. Tên miền đích đối chiếu bản ghi DNS trên máy chủ.
C. Địa chỉ MAC đích đối chiếu bảng MAC học trên switch.
D. Cổng TCP đích đối chiếu bảng phiên của ứng dụng.
Đáp án đúng: C

3. TCP và UDP được xếp vào tầng nào trong mô hình OSI, với vai trò chính gì?
A. Network, chuyển datagram dựa theo subnet mask và next hop.
B. Transport, phân phối dữ liệu theo port giữa các tiến trình.
C. Data Link, xác nhận và chuyển frame trong mạng Ethernet.
D. Session, mã hóa và xác minh chứng thư máy chủ từ xa.
Đáp án đúng: B

4. Khi gửi dữ liệu HTTP trên TCP/IP qua Ethernet, thứ tự đóng gói từ trong ra ngoài là gì?
A. HTTP → IP packet → TCP segment → Ethernet frame.
B. HTTP → TCP segment → IP packet → Ethernet frame.
C. HTTP → Ethernet frame → IP packet → TCP segment.
D. HTTP → TCP segment → Ethernet frame → IP packet.
Đáp án đúng: B

5. Switch L2 học địa chỉ MAC của thiết bị kết nối từ thành phần nào trên frame nhận được?
A. MAC đích và cổng egress của frame sắp chuyển.
B. IP nguồn và cổng TCP của segment bên trong frame.
C. MAC nguồn và cổng ingress của frame vừa nhận.
D. IP đích và trường TTL của packet bên trong frame.
Đáp án đúng: C

6. Máy A cần gửi gói IPv4 cho máy B cùng subnet nhưng chưa biết MAC của B. Máy A dùng gì?
A. ARP request để tìm MAC tương ứng địa chỉ IPv4 của B.
B. DNS query để tìm MAC tương ứng tên host của B.
C. DHCP discover để tìm MAC tương ứng địa chỉ của B.
D. ICMP Echo để tìm MAC tương ứng địa chỉ của B.
Đáp án đúng: A

7. Máy A gửi tới IPv4 ngoài subnet. Trong frame Ethernet đầu tiên, MAC đích thường là gì?
A. MAC của máy đích trên mạng từ xa qua Internet.
B. MAC của DNS resolver đã trả lời địa chỉ IP.
C. MAC của DHCP server đã cấp địa chỉ cho A.
D. MAC của default gateway trên liên kết cục bộ.
Đáp án đúng: D

8. Hai nhóm máy nằm trong hai VLAN khác nhau trên cùng switch L2. Muốn trao đổi IP giữa hai VLAN cần gì?
A. Switch L2 chỉ cần học thêm MAC ở hai VLAN.
B. Máy khách đổi TCP port cho phù hợp từng VLAN.
C. Bật ARP broadcast qua mọi VLAN mà không định tuyến.
D. Thiết bị hoặc giao diện định tuyến giữa các VLAN.
Đáp án đúng: D

9. Hai switch cần mang lưu lượng của nhiều VLAN qua một đường Ethernet. Cấu hình nào phù hợp?
A. Trunk 802.1Q mang VLAN ID trên frame được gắn thẻ.
B. Access port buộc mọi frame vào một VLAN duy nhất.
C. EtherChannel tự gom nhiều VLAN mà không có trunk.
D. Đặt mọi VLAN cùng một subnet để frame tự đi qua.
Đáp án đúng: A

10. Liên kết Ethernet full-duplex giữa hai thiết bị hoạt động bình thường. Nhận định nào về va chạm là đúng?
A. Vẫn dùng CSMA/CD để phát hiện va chạm khi gửi cùng lúc.
B. Dùng CSMA/CA với ACK ở mức truy cập môi trường dây.
C. Không dùng CSMA/CD để xử lý va chạm trên liên kết này.
D. Phải chia hai hướng gửi nhận thành hai collision domain.
Đáp án đúng: C

11. Trường FCS/CRC ở cuối frame Ethernet dùng để thực hiện mục đích chủ yếu nào?
A. Sửa chính xác các bit bị lỗi rồi chuyển frame đi.
B. Bảo đảm frame được ứng dụng nhận theo đúng thứ tự.
C. Mã hóa nội dung frame trước khi phát trên đường dây.
D. Phát hiện frame bị lỗi bit trong quá trình truyền.
Đáp án đúng: D

12. Khi một host phát Ethernet broadcast trong một VLAN, router thường xử lý frame đó ra sao?
A. Chuyển nguyên broadcast L2 tới mọi mạng có route.
B. Đổi broadcast thành TCP unicast để truyền qua WAN.
C. Tự gửi lại broadcast qua tất cả cổng trunk VLAN.
D. Không tự chuyển tiếp broadcast L2 sang subnet khác.
Đáp án đúng: D

13. Wi-Fi dùng phương pháp nào để giảm khả năng hai trạm cùng chiếm sóng vô tuyến?
A. CSMA/CD: phát hiện va chạm khi đang gửi trên sóng.
B. Full-duplex Ethernet: phát và nhận đồng thời cùng kênh.
C. CSMA/CA: nghe kênh, backoff và dùng ACK ở MAC.
D. Token passing: chờ được cấp token trước khi phát sóng.
Đáp án đúng: C

14. Khu vực có nhiều AP Wi-Fi 2,4 GHz dùng các kênh chồng lấn gây nhiễu. Bước tối ưu hợp lý?
A. Tăng công suất tất cả AP để loại bỏ nhiễu đồng kênh.
B. Đo phổ rồi chọn kênh ít chồng lấn, giảm tranh chấp.
C. Đặt tất cả AP cạnh nhau dùng cùng một kênh cố định.
D. Tắt cơ chế backoff để các máy phát gói không phải đợi.
Đáp án đúng: B

15. Máy báo sóng Wi-Fi mạnh nhưng thông lượng thấp và nhiều lần gửi lại. Nên đo gì để tìm nguyên nhân?
A. SNR, độ bận kênh và tỷ lệ retry của kết nối.
B. Bảng ARP của router và tổng số bản ghi DNS A.
C. TTL của gói IPv4 và số chặng khi traceroute.
D. Số entry trong bảng MAC của switch có dây.
Đáp án đúng: A

16. Khi dùng mạng Wi-Fi với WPA2/WPA3-Personal, yếu tố nào trực tiếp hỗ trợ bảo mật liên kết?
A. Xác thực và mã hóa lưu lượng radio theo khóa đã thiết lập.
B. Thay thế DNS để ẩn tên miền của mọi website đã truy cập.
C. Bỏ yêu cầu TLS vì kết nối HTTPS đã được mã hóa ở Wi-Fi.
D. Tự tạo VPN từ AP tới toàn bộ server ngoài Internet.
Đáp án đúng: A

17. Thiết bị đi giữa hai AP cùng SSID. Vai trò chính trong quyết định roaming của Wi-Fi client là gì?
A. DNS server chọn AP rồi đổi IP cho mỗi frame của máy khách.
B. Router Internet chọn AP dựa trên địa chỉ đích của gói IP.
C. Máy khách chọn AP dựa vào tín hiệu và chính sách roaming.
D. Switch lõi ấn định AP bằng bảng NAT của mọi thiết bị.
Đáp án đúng: C

18. Trong các địa chỉ IPv4 sau, địa chỉ nào thuộc dải private RFC 1918?
A. 172.20.5.10 thuộc dải private 172.16.0.0/12.
B. 172.32.5.10 thuộc dải private 172.16.0.0/12.
C. 169.254.5.10 thuộc dải private 172.16.0.0/12.
D. 100.64.5.10 thuộc dải private 172.16.0.0/12.
Đáp án đúng: A

19. Subnet IPv4 /26 có bao nhiêu địa chỉ host sử dụng được trong mô hình mạng thông thường?
A. 30 host sử dụng được trong 32 địa chỉ của subnet.
B. 126 host sử dụng được trong 128 địa chỉ của subnet.
C. 62 host sử dụng được trong 64 địa chỉ của subnet.
D. 254 host sử dụng được trong 256 địa chỉ của subnet.
Đáp án đúng: C

20. Với subnet 192.168.10.64/27, địa chỉ broadcast của subnet là địa chỉ nào?
A. 192.168.10.94 là broadcast của mạng /27 này.
B. 192.168.10.95 là broadcast của mạng /27 này.
C. 192.168.10.96 là broadcast của mạng /27 này.
D. 192.168.10.63 là broadcast của mạng /27 này.
Đáp án đúng: B

21. Hai host 192.168.5.17/27 và 192.168.5.29/27 có ở cùng một subnet IPv4 không?
A. Không, host thứ hai thuộc dải .32 đến .63.
B. Không, host thứ nhất thuộc dải .0 đến .15.
C. Có, cả hai thuộc dải 192.168.5.0 đến .31.
D. Có, nhưng chỉ vì cùng tiền tố /24 của lớp C.
Đáp án đúng: C

22. Tuyến mặc định 0.0.0.0/0 trong bảng định tuyến IPv4 có vai trò nào?
A. Luôn được ưu tiên hơn mọi tuyến /16 hoặc /24 đã có.
B. Chọn next hop khi không có tuyến cụ thể hơn khớp đích.
C. Chuyển mọi gói IPv4 thành broadcast trong LAN hiện tại.
D. Cho phép bỏ qua next hop và phát trực tiếp ra mọi cổng.
Đáp án đúng: B

23. Router có tuyến 10.5.0.0/16 và 10.5.8.0/24. Gói tới 10.5.8.20 thường theo tuyến nào?
A. Tuyến 10.5.8.0/24 do tiền tố khớp dài hơn.
B. Tuyến 10.5.0.0/16 do bao trùm phạm vi lớn hơn.
C. Tuyến mặc định 0.0.0.0/0 dù có cả hai tuyến.
D. Tuyến chọn ngẫu nhiên vì hai prefix đều khớp IP.
Đáp án đúng: A

24. Router giảm trường TTL của IPv4 packet khi chuyển tiếp để đạt mục đích gì?
A. Đảm bảo packet luôn đi qua đúng số router đã đặt.
B. Xác minh chữ ký số của gói tin trước khi định tuyến.
C. Ngăn gói lặp vô hạn; TTL về 0 thì bị loại bỏ.
D. Tăng độ ưu tiên QoS của packet qua từng chặng.
Đáp án đúng: C

25. Khi host dùng DHCPv4 cấp địa chỉ tự động, thứ tự trao đổi DORA thông thường là gì?
A. Discover → Offer → Request → Acknowledge.
B. Discover → Request → Offer → Acknowledge.
C. Request → Discover → Acknowledge → Offer.
D. Offer → Discover → Request → Acknowledge.
Đáp án đúng: A

26. Ngoài địa chỉ IPv4, DHCPv4 có thể cung cấp thông tin cấu hình nào cho client?
A. MAC của từng host từ xa và bảng route của mọi router.
B. Port TCP của ứng dụng và chứng thư TLS cho website.
C. Số sequence TCP và khóa mã hóa cho phiên HTTP.
D. Subnet mask, default gateway và địa chỉ DNS server.
Đáp án đúng: D

27. Đâu là điểm khác biệt cơ bản về độ dài địa chỉ giữa IPv4 và IPv6?
A. IPv4 dùng 48 bit, còn IPv6 có không gian địa chỉ 128 bit.
B. IPv4 dùng 32 bit, còn IPv6 có không gian địa chỉ 128 bit.
C. IPv4 dùng 32 bit, còn IPv6 có không gian địa chỉ 64 bit.
D. IPv4 dùng 128 bit, còn IPv6 có không gian địa chỉ 32 bit.
Đáp án đúng: B

28. Trong IPv6, cơ chế nào thường tìm địa chỉ lớp liên kết của một neighbor cùng mạng?
A. ARP request gửi trên IPv6 multicast để hỏi địa chỉ MAC.
B. DNS AAAA lookup lấy trực tiếp MAC của neighbor gần nhất.
C. DHCPv6 Request tự truy vấn MAC của neighbor theo từng packet.
D. Neighbor Discovery dựa trên ICMPv6 Neighbor Solicitation.
Đáp án đúng: D

29. Địa chỉ IPv6 thuộc dải fe80::/10 thường được dùng cho phạm vi nào?
A. Global unicast, router chuyển tiếp trên Internet công cộng.
B. Multicast, phát đến mọi router trên nhiều mạng WAN.
C. Link-local, giao tiếp trên cùng liên kết và không được route.
D. Loopback, chỉ xử lý lưu lượng trong một host cục bộ.
Đáp án đúng: C

30. NAT/PAT ở gateway thường làm gì với luồng IPv4 từ LAN ra Internet?
A. Đổi địa chỉ MAC đích ở mọi router mà giữ nguyên IP.
B. Đổi địa chỉ/cổng nguồn và giữ ánh xạ cho gói trả về.
C. Đổi DNS A record thành địa chỉ IP private cho mọi domain.
D. Đổi trường TTL thành port để thiết lập một kết nối TCP.
Đáp án đúng: B

31. Lệnh ping IPv4 thông thường dùng cặp thông điệp nào để kiểm tra host phản hồi?
A. TCP SYN và TCP SYN-ACK tới port đang mở trên host.
B. UDP Query và UDP Reply từ DNS server được cấu hình.
C. ARP Request và ARP Reply qua tất cả router trung gian.
D. ICMP Echo Request và ICMP Echo Reply giữa hai host.
Đáp án đúng: D

32. Traceroute thường khám phá các hop dọc đường đi bằng cơ chế nào?
A. Gửi truy vấn DNS A lặp lại rồi suy ra router trung gian.
B. Gửi gói với TTL/Hop Limit tăng dần và quan sát phản hồi.
C. Gửi ARP broadcast qua WAN để mỗi router phản hồi MAC.
D. Đọc chứng thư TLS để suy ra danh sách next hop trên mạng.
Đáp án đúng: B

33. Đường truyền có MTU nhỏ hơn kích thước IP packet và cấm phân mảnh. Dấu hiệu nào gợi ý cần xử lý PMTU?
A. Switch tự tăng MTU của mọi chặng để đủ chứa packet lớn.
B. DNS tự cắt packet IP thành nhiều response theo từng route.
C. Thiết bị báo cần giảm cỡ gói; ứng dụng cần dùng MTU phù hợp.
D. TCP bỏ checksum gói để giảm kích thước xuống dưới MTU.
Đáp án đúng: C

34. Thứ tự bắt tay ba bước của TCP khi phía client chủ động kết nối là gì?
A. Client SYN → Server ACK → Client SYN-ACK.
B. Client ACK → Server SYN-ACK → Client SYN.
C. Client SYN-ACK → Server SYN → Client ACK.
D. Client SYN → Server SYN-ACK → Client ACK.
Đáp án đúng: D

35. TCP bảo đảm dữ liệu đến tin cậy và đúng thứ tự nhờ nhóm cơ chế nào?
A. TTL trong IP header cùng bảng route của router giúp tái truyền.
B. MAC nguồn và MAC đích trong frame Ethernet giúp tái truyền.
C. DNS TTL và cache của recursive resolver giúp tái truyền.
D. Sequence number, ACK và retransmission khi cần thiết.
Đáp án đúng: D

36. TCP receive window chủ yếu hỗ trợ cơ chế điều khiển nào giữa hai đầu truyền?
A. Flow control, tránh gửi vượt khả năng đệm của bên nhận.
B. Congestion control, đo tỷ lệ nghẽn của mọi router trung gian.
C. Routing control, chọn next hop dựa theo tốc độ đường truyền.
D. Name resolution, chọn địa chỉ IP từ các DNS record.
Đáp án đúng: A

37. Khi mạng nghẽn làm tăng mất gói hoặc độ trễ, TCP congestion control thường thay đổi gì?
A. Điều chỉnh tốc độ gửi qua congestion window của phía gửi.
B. Tăng receive buffer của bên nhận bất kể khả năng bộ nhớ.
C. Thay địa chỉ IP đích thành router có RTT nhỏ hơn hiện tại.
D. Thay DNS TTL của tên miền để giảm lưu lượng phát lại.
Đáp án đúng: A

38. UDP khác TCP ở điểm cốt lõi nào đối với ứng dụng gửi datagram?
A. Luôn bảo đảm đúng thứ tự nhờ ACK của tầng transport.
B. Không tự bảo đảm giao hàng, thứ tự hay truyền lại dữ liệu.
C. Phải bắt tay ba bước trước khi gửi datagram đầu tiên.
D. Tự mã hóa các datagram bằng TLS trước khi đi vào mạng.
Đáp án đúng: B

39. Khi một hostname có cả DNS A và AAAA record, từng loại trả về thông tin nào?
A. A ánh xạ tới IPv4; AAAA ánh xạ tới IPv6.
B. A ánh xạ tới IPv6; AAAA ánh xạ tới IPv4.
C. A ánh xạ tới mail server; AAAA ánh xạ tới IPv6.
D. A ánh xạ tới alias; AAAA ánh xạ tới name server.
Đáp án đúng: A

40. DNS TTL ảnh hưởng trực tiếp thế nào đến kết quả được resolver lưu trong cache?
A. Giới hạn thời gian cache dùng lại bản ghi trước khi cần làm mới.
B. Ấn định thời gian tối đa một TCP session được giữ kết nối.
C. Quy định số chặng mạng gói tin DNS được đi qua Internet.
D. Quy định thời gian chứng thư TLS của website còn hiệu lực.
Đáp án đúng: A

41. Vai trò của recursive DNS resolver khác authoritative DNS server chủ yếu ở đâu?
A. Resolver giữ khóa TLS; authoritative chuyển tiếp TCP segment.
B. Resolver cấp DHCP lease; authoritative định tuyến gói tin IP.
C. Resolver đặt VLAN ID; authoritative lưu bảng MAC của switch.
D. Resolver tra cứu thay client; authoritative cung cấp bản ghi vùng.
Đáp án đúng: D

42. Trong DNS, CNAME record thường được dùng để làm gì?
A. Lưu địa chỉ IPv4 trực tiếp của tên DNS đang được hỏi.
B. Lưu địa chỉ IPv6 trực tiếp của tên DNS đang được hỏi.
C. Khai báo một tên DNS là alias của tên DNS khác.
D. Khai báo mail exchanger cho domain ở cùng một vùng.
Đáp án đúng: C

43. DNS truy vấn truyền thống dùng giao thức vận chuyển và port nào?
A. Chủ yếu TCP port 53; UDP chỉ khi TCP không thể kết nối.
B. Thường UDP port 53; TCP port 53 cũng được sử dụng.
C. Thường UDP port 67; TCP port 67 khi dữ liệu dài.
D. Chủ yếu UDP port 443; TCP port 443 khi cần fallback.
Đáp án đúng: B

44. Trình duyệt xác minh chứng thư TLS khi truy cập HTTPS. Kiểm tra nào quan trọng nhất?
A. Chuỗi tin cậy, thời hạn và hostname trong chứng thư.
B. Địa chỉ MAC router, địa chỉ subnet và VLAN của client.
C. TTL của gói IPv4, cổng ARP và số hop của phiên TCP.
D. Mức bận kênh Wi-Fi, RSSI và số lần thử lại frame.
Đáp án đúng: A

45. Trong kết nối HTTPS qua TCP, TLS cung cấp chức năng nào khác với TCP?
A. Định tuyến gói qua mạng và giảm TTL tại từng router.
B. Phân giải tên domain thành địa chỉ IPv4 hoặc IPv6.
C. Bảo đảm đúng thứ tự segment bằng ACK và retransmit.
D. Mã hóa, bảo vệ toàn vẹn và xác thực đầu xa theo chứng thư.
Đáp án đúng: D

46. Trình duyệt báo lỗi không tìm được hostname; cần phân biệt lỗi DNS với lỗi TCP. Nên kiểm tra gì đầu tiên?
A. Dùng traceroute tới domain rồi bỏ kiểm tra kết quả DNS.
B. Đổi TLS certificate ở server trước khi phân giải hostname.
C. Đo độ trễ TCP qua port 443 mà không cần địa chỉ IP.
D. Dùng dig/nslookup để kiểm tra phân giải tên và DNS server.
Đáp án đúng: D

47. Máy ping được default gateway nhưng ping IPv4 công cộng không được. Bước chẩn đoán tiếp theo phù hợp?
A. Kiểm tra cookie HTTP và thời gian sống của phiên trình duyệt.
B. Kiểm tra default route, next hop và traceroute tới IP đích.
C. Thay chứng thư TLS rồi kiểm tra lại thông báo trên browser.
D. Đổi bản ghi DNS A trước khi kiểm tra lưu lượng ra ngoài.
Đáp án đúng: B

48. DNS phân giải đúng IP, capture tại client chỉ thấy TCP SYN đi mà không có SYN-ACK về. Nên kiểm tra gì?
A. Tên hostname trong chứng thư TLS mà server đang gửi.
B. Listener, firewall và đường đi/chiều về tới server đích.
C. HTTP status code trong response của ứng dụng trên server.
D. DNS TTL của bản ghi A đã được resolver lưu trong cache.
Đáp án đúng: B

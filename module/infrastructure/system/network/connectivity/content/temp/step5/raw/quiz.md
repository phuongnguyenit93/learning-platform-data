Câu 1. Địa chỉ IPv4 được biểu diễn bằng bao nhiêu bit?
A. 32 bit cho mỗi địa chỉ IPv4
B. 64 bit cho mỗi địa chỉ IPv4
C. 96 bit cho mỗi địa chỉ IPv4
D. 128 bit cho mỗi địa chỉ IPv4
Đáp án đúng: A

Câu 2. Địa chỉ IPv6 có độ dài chuẩn bao nhiêu bit?
A. 32 bit cho mỗi địa chỉ IPv6
B. 64 bit cho mỗi địa chỉ IPv6
C. 128 bit cho mỗi địa chỉ IPv6
D. 96 bit cho mỗi địa chỉ IPv6
Đáp án đúng: C

Câu 3. Mạng IPv4 /24 thông thường có bao nhiêu địa chỉ host sử dụng được?
A. 252 địa chỉ host khả dụng
B. 254 địa chỉ host khả dụng
C. 255 địa chỉ host khả dụng
D. 256 địa chỉ host khả dụng
Đáp án đúng: B

Câu 4. Mạng IPv4 /26 thông thường có bao nhiêu địa chỉ host sử dụng được?
A. 60 địa chỉ host khả dụng
B. 64 địa chỉ host khả dụng
C. 66 địa chỉ host khả dụng
D. 62 địa chỉ host khả dụng
Đáp án đúng: D

Câu 5. Dải IPv4 nào thuộc vùng địa chỉ riêng RFC 1918?
A. `169.254.0.0/16` là mạng private
B. `198.51.100.0/24` là mạng private
C. `10.0.0.0/8` là mạng private
D. `100.64.0.0/10` là mạng private
Đáp án đúng: C

Câu 6. Tiền tố IPv6 nào dành cho địa chỉ link-local?
A. `fe80::/10` dùng cho link-local
B. `ff00::/8` dùng cho link-local
C. `2000::/3` dùng cho link-local
D. `fc00::/7` dùng cho link-local
Đáp án đúng: A

Câu 7. IPv6 sử dụng cơ chế nào để tìm MAC của hàng xóm trên cùng link?
A. Name Resolution thông qua DNS
B. Path Discovery thông qua TCP
C. Neighbor Discovery thông qua ICMPv6
D. Address Resolution thông qua ARP
Đáp án đúng: C

Câu 8. Khi IPv4 đích nằm ngoài subnet cục bộ, host thường gửi frame đầu tiên đến đâu?
A. MAC của DNS resolver trong mạng LAN
B. MAC của DHCP server trong mạng LAN
C. MAC của chính host đích ở mạng Internet
D. MAC của router next-hop trong mạng LAN
Đáp án đúng: D

Câu 9. Một bảng định tuyến có nhiều route cùng khớp IP đích, quy tắc phổ biến nào được ưu tiên?
A. Chọn route có subnet mask nhỏ nhất
B. Chọn route có tiền tố mạng ngắn nhất
C. Chọn route có tên interface ngắn nhất
D. Chọn route có tiền tố mạng dài nhất
Đáp án đúng: D

Câu 10. Mỗi lần router chuyển tiếp gói IPv4, trường TTL thường thay đổi như thế nào?
A. Đặt về giá trị mặc định ở mỗi hop
B. Giảm một đơn vị trên mỗi hop router
C. Tăng một đơn vị trên mỗi hop router
D. Giữ nguyên qua mọi hop router
Đáp án đúng: B

Câu 11. Trên Linux, lệnh nào xem các tuyến định tuyến hiện tại?
A. `ip link show` hiển thị bảng route
B. `ip addr show` hiển thị bảng route
C. `ip neigh show` hiển thị bảng route
D. `ip route show` hiển thị bảng route
Đáp án đúng: D

Câu 12. Trên Linux, lệnh nào xem địa chỉ IP được gán cho các interface?
A. `ip rule show` liệt kê địa chỉ IP
B. `ip route show` liệt kê địa chỉ IP
C. `ip neigh show` liệt kê địa chỉ IP
D. `ip addr show` liệt kê địa chỉ IP
Đáp án đúng: D

Câu 13. Trong DHCPv4, thứ tự trao đổi DORA chuẩn là gì?
A. Offer → Discover → Request → ACK
B. Discover → Offer → Request → ACK
C. Discover → Request → Offer → ACK
D. Request → Offer → Discover → ACK
Đáp án đúng: B

Câu 14. Bản ghi DNS loại A thường ánh xạ tên miền thành dữ liệu nào?
A. Một địa chỉ mạng IPv6 của máy đích
B. Một máy chủ thư nhận email tên miền
C. Một địa chỉ mạng IPv4 của máy đích
D. Một bí danh tên DNS trỏ sang tên khác
Đáp án đúng: C

Câu 15. Bản ghi DNS loại AAAA thường ánh xạ tên miền thành dữ liệu nào?
A. Một địa chỉ mạng IPv6 của máy đích
B. Một địa chỉ mạng IPv4 của máy đích
C. Một tên máy chủ thư cho tên miền
D. Một tên bí danh DNS cho tên miền
Đáp án đúng: A

Câu 16. Bản ghi DNS loại PTR thường phục vụ truy vấn nào?
A. Tra cứu địa chỉ IP từ một tên host
B. Tra cứu mail exchanger của domain
C. Tra cứu bí danh của một tên host
D. Tra cứu tên host từ một địa chỉ IP
Đáp án đúng: D

Câu 17. Recursive DNS resolver có vai trò nào khi chưa có câu trả lời trong cache?
A. Truy vấn các DNS server để tìm kết quả
B. Đóng kết nối TCP khi truy vấn gặp lỗi
C. Tạo tuyến route mới đến máy chủ đích
D. Phát DHCP lease để máy khách có IP
Đáp án đúng: A

Câu 18. DNS TTL trên một bản ghi chủ yếu quy định điều gì?
A. Thời gian DHCP client được phép giữ địa chỉ IP
B. Thời gian router giữ gói trong hàng đợi
C. Thời gian bản ghi được phép lưu trong cache
D. Thời gian socket TCP được giữ ở trạng thái mở
Đáp án đúng: C

Câu 19. Mã phản hồi DNS NXDOMAIN thường có ý nghĩa gì?
A. DNS server báo lỗi nội bộ khi xử lý
B. Truy vấn hoàn tất nhưng không có bản ghi A
C. Tên được hỏi không tồn tại trong DNS
D. DNS server từ chối truy vấn của client
Đáp án đúng: C

Câu 20. Thứ tự bắt tay TCP ba bước thường diễn ra thế nào?
A. SYN → SYN-ACK → ACK từ hai phía
B. SYN → ACK → SYN-ACK từ hai phía
C. SYN-ACK → SYN → ACK từ hai phía
D. ACK → SYN-ACK → SYN từ hai phía
Đáp án đúng: A

Câu 21. Điểm khác biệt cơ bản của UDP so với TCP là gì?
A. Gửi datagram kèm quy trình bắt tay ba bước
B. Gửi luồng byte có cơ chế xác nhận và truyền lại
C. Gửi datagram không bắt tay thiết lập kết nối
D. Gửi luồng byte có cơ chế sắp xếp theo thứ tự
Đáp án đúng: C

Câu 22. Một kết nối TCP thường được phân biệt bằng bộ thông tin nào?
A. IP đích, subnet mask, port đích, giao thức
B. IP nguồn, port nguồn, IP đích, port đích
C. IP nguồn, port nguồn, hostname, giao thức
D. IP nguồn, địa chỉ MAC, port đích, TTL
Đáp án đúng: B

Câu 23. Khi host đích trả TCP RST do không có dịch vụ lắng nghe, client thường nhận gì?
A. Lỗi kết nối bị từ chối (connection refused)
B. Lỗi tuyến mạng chưa có (network unreachable)
C. Lỗi hết thời gian chờ (connection timed out)
D. Lỗi tên DNS không tồn tại (NXDOMAIN)
Đáp án đúng: A

Câu 24. Khi firewall âm thầm drop SYN mà không phản hồi, biểu hiện nào thường gặp?
A. Kết nối TCP tự chuyển sang truyền qua UDP
B. Kết nối TCP bị timeout sau thời gian chờ
C. Kết nối TCP bị từ chối ngay bằng RST
D. Kết nối TCP được xác nhận bằng SYN-ACK
Đáp án đúng: B

Câu 25. Dịch vụ IPv4 chỉ bind `127.0.0.1` sẽ được truy cập từ đâu theo mặc định?
A. Các máy khác kết nối qua IP LAN của host
B. Các tiến trình kết nối qua loopback của host
C. Các máy khác kết nối qua public IP của host
D. Các container khác kết nối qua IP bridge
Đáp án đúng: B

Câu 26. Khi dịch vụ IPv4 bind `0.0.0.0`, hành vi lắng nghe nào đúng?
A. Lắng nghe riêng trên interface loopback IPv4
B. Lắng nghe riêng trên interface có default route
C. Lắng nghe trên các interface IPv4 cục bộ
D. Lắng nghe trên các interface IPv6 cục bộ
Đáp án đúng: C

Câu 27. Trên Linux, `ss -lntp` chủ yếu giúp kiểm tra thông tin nào?
A. Cổng UDP đang LISTEN cùng process liên quan
B. Cổng TCP đã kết nối cùng route tới đích
C. Cổng UDP đã kết nối cùng route tới đích
D. Cổng TCP đang LISTEN cùng process liên quan
Đáp án đúng: D

Câu 28. Công cụ nào phù hợp để thử phản hồi HTTP và xem quá trình kết nối chi tiết?
A. `curl -v` để kiểm tra request HTTP
B. `dig -v` để kiểm tra request HTTP
C. `ping -v` để kiểm tra request HTTP
D. `ip -v` để kiểm tra request HTTP
Đáp án đúng: A

Câu 29. Nếu `ping` thành công, điều nào vẫn chưa được đảm bảo?
A. Máy đích có thể trả ICMP Echo Reply
B. Gói echo có thể quay lại máy nguồn
C. Đường truyền ICMP tới máy đích có phản hồi
D. Cổng TCP 443 của máy đích đang mở
Đáp án đúng: D

Câu 30. `traceroute` hoặc `tracepath` thường hỗ trợ nhận diện điều gì?
A. Các bản ghi DNS còn hiệu lực trong cache
B. Các container đang chạy trên host đích
C. Các listener TCP trên máy chủ đích
D. Các hop router trên đường đi tới đích
Đáp án đúng: D

Câu 31. Lệnh `tcpdump -i eth0 'tcp port 443'` thường thực hiện điều gì?
A. Bắt các gói ICMP cổng 443 trên eth0
B. Bắt các gói TCP cổng 443 trên eth0
C. Bắt các gói ARP cổng 443 trên eth0
D. Bắt các gói UDP cổng 443 trên eth0
Đáp án đúng: B

Câu 32. Khi NAT thay đổi địa chỉ nguồn của gói tin đi ra ngoài, đó là gì?
A. SNAT thay địa chỉ nguồn khi chuyển tiếp
B. PAT chỉ thay địa chỉ đích khi chuyển tiếp
C. NAT64 chỉ thay địa chỉ MAC khi chuyển tiếp
D. DNAT thay địa chỉ nguồn khi chuyển tiếp
Đáp án đúng: A

Câu 33. Một rule chuyển lưu lượng đến public IP:443 vào private IP:8443 chủ yếu dùng cơ chế nào?
A. ARP đổi đích nhận gói đến từ bên ngoài
B. DNAT đổi đích nhận gói đến từ bên ngoài
C. SNAT đổi đích nhận gói đến từ bên ngoài
D. DNS đổi đích nhận gói đến từ bên ngoài
Đáp án đúng: B

Câu 34. Stateful firewall có thể cho phép gói phản hồi của kết nối đã thiết lập nhờ gì?
A. Duyệt bảng phân vùng của cơ sở dữ liệu
B. Theo dõi trạng thái các phiên kết nối
C. Tra cứu DNS TTL của tên máy chủ đích
D. Tra cứu subnet mask của host nguồn
Đáp án đúng: B

Câu 35. Chính sách firewall mặc định từ chối inbound có ý nghĩa gì?
A. Chỉ các lưu lượng không có port mới bị chặn
B. Mọi lưu lượng TCP đều được tự động cho vào
C. Chỉ lưu lượng khớp rule allow mới vào
D. Mọi gói từ cùng subnet đều được cho phép
Đáp án đúng: C

Câu 36. Forward proxy đặt giữa client và Internet thường xử lý luồng nào?
A. DNS server cấp IP cho client qua proxy
B. Internet gửi request vào backend qua proxy
C. Client gửi request ra ngoài qua proxy
D. Router gửi ICMP đến client qua proxy
Đáp án đúng: C

Câu 37. Reverse proxy trước nhiều backend thường thực hiện công việc nào?
A. Chuyển request của client tới backend
B. Nhận DHCP lease rồi phân phối cho client
C. Nhận bảng route rồi gửi sang router khác
D. Nhận packet capture rồi lưu vào DNS cache
Đáp án đúng: A

Câu 38. VPN site-to-site dùng IPsec thường bảo vệ dữ liệu mạng bằng cách nào?
A. Đổi hostname thành địa chỉ IP trên từng gateway
B. Mã hóa và xác thực lưu lượng giữa các gateway
C. Đánh số port TCP từ thấp lên cao mỗi gateway
D. Tạo bản ghi DNS khi client gửi lưu lượng
Đáp án đúng: B

Câu 39. Hiện tượng gói nhỏ đi được nhưng gói lớn bị treo có thể liên quan đến gì?
A. MTU đường đi hoặc cơ chế Path MTU Discovery
B. Cache DNS cũ hoặc thời gian TTL của tên miền
C. Checksum DNS hoặc quyền ghi của DHCP server
D. Định dạng URL hoặc cấu hình HTTP redirect
Đáp án đúng: A

Câu 40. Trong mạng bridge của container trên Linux, veth pair thường có vai trò gì?
A. Nối container vào bridge mạng trên host
B. Định tuyến tên DNS của container tới public resolver
C. Cấp phát chứng chỉ TLS cho các cổng đang publish
D. Ghi bản sao packet capture vào volume của container
Đáp án đúng: A

Câu 41. Khi chạy Docker với `-p 8080:80`, cổng được chuyển tiếp theo hướng nào?
A. Host port 8080 chuyển tới container port 8080
B. Host port 8080 chuyển tới container port 80
C. Host port 80 chuyển tới container port 80
D. Host port 80 chuyển tới container port 8080
Đáp án đúng: B

Câu 42. Trong Kubernetes, Service loại ClusterIP thường được thiết kế cho mục đích nào?
A. Cung cấp NAT của host thay cho mạng Pod trong cluster
B. Cung cấp cổng vật lý cố định trên mọi node trong cluster
C. Cung cấp IP public trực tiếp lên mọi Pod trong cluster
D. Cung cấp endpoint ổn định để truy cập nội bộ cluster
Đáp án đúng: D

Câu 43. Đối tượng Kubernetes nào dùng để giới hạn luồng mạng giữa các Pod khi CNI hỗ trợ?
A. `StatefulSet` thiết lập quy tắc lưu lượng
B. `PersistentVolume` thiết lập quy tắc lưu lượng
C. `ConfigMap` thiết lập quy tắc lưu lượng
D. `NetworkPolicy` thiết lập quy tắc lưu lượng
Đáp án đúng: D

Câu 44. Trong cloud VPC, khi một subnet không tới được đích khác mạng, thành phần nào nên kiểm tra sớm?
A. SQL index, schema database và connection pool
B. TLS certificate, HTML header và HTTP cookie
C. Route table, rule firewall và đường next hop
D. DNS cache, số tab browser và file log ứng dụng
Đáp án đúng: C

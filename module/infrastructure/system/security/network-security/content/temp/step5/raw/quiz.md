1. Mục tiêu chính của phân đoạn mạng (network segmentation) là gì?
A. Giới hạn luồng và giảm di chuyển ngang giữa các vùng.
B. Tăng tốc độ định tuyến bằng cách giảm số subnet.
C. Mã hóa toàn bộ gói tin giữa các máy cùng VLAN.
D. Thay thế xác thực người dùng bằng địa chỉ IP nội bộ.
Đáp án đúng: A

2. Firewall stateful khác firewall stateless ở điểm nào?
A. Chỉ lọc gói theo địa chỉ MAC ở tầng liên kết.
B. Luôn giải mã payload TLS trước khi áp dụng chính sách.
C. Tự cấp danh tính người dùng cho mọi kết nối được phép.
D. Theo dõi trạng thái phiên và gói thuộc kết nối.
Đáp án đúng: D

3. Chính sách default deny nên được hiểu như thế nào?
A. Cho phép mọi kết nối nội bộ rồi chặn kết nối Internet.
B. Chặn mọi gói tin kể cả luồng đã được phê duyệt.
C. Chặn lưu lượng không khớp quy tắc cho phép rõ ràng.
D. Chỉ chặn cổng không chuẩn và cho phép cổng phổ biến.
Đáp án đúng: C

4. Egress filtering giúp giảm rủi ro mạng nào?
A. Ngăn người ngoài quét cổng dịch vụ đang public.
B. Giới hạn kết nối đi ra và kênh exfiltration.
C. Mã hóa dữ liệu lưu trong ổ đĩa của máy chủ.
D. Thay thế kiểm tra quyền trên API nội bộ.
Đáp án đúng: B

5. Vì sao NAT không nên được xem là cơ chế bảo mật đầy đủ?
A. NAT dịch địa chỉ, không tự quyết định quyền truy cập.
B. NAT luôn cho phép mọi gói tin đi vào mạng private.
C. NAT mã hóa địa chỉ nguồn nên không thể kiểm toán.
D. NAT chỉ hoạt động khi mọi kết nối dùng TCP.
Đáp án đúng: A

6. Lưu lượng east-west trong trung tâm dữ liệu là gì?
A. Luồng từ người dùng Internet vào public endpoint.
B. Luồng quản trị đi từ laptop tới mạng văn phòng.
C. Luồng DNS giữa resolver công cộng và authoritative server.
D. Luồng trao đổi giữa workload hoặc dịch vụ nội bộ.
Đáp án đúng: D

7. Microsegmentation thường thực thi chính sách ở mức nào?
A. Chỉ theo ranh giới giữa các tòa nhà văn phòng.
B. Chỉ theo lớp địa chỉ IP public được nhà mạng cấp.
C. Áp chính sách theo workload hoặc danh tính dịch vụ.
D. Theo vị trí vật lý của switch trong phòng máy.
Đáp án đúng: C

8. Next-generation firewall thường mở rộng lọc mạng bằng khả năng nào?
A. Nhận diện ứng dụng và ngữ cảnh giao thức sâu hơn.
B. Tự động sửa mã nguồn của ứng dụng khi phát hiện lỗi.
C. Thay thế hệ thống quản lý danh tính và phân quyền.
D. Cấp chứng thư số cho mọi thiết bị nối vào mạng.
Đáp án đúng: A

9. Web application firewall phù hợp nhất để bảo vệ loại lưu lượng nào?
A. Mọi giao thức IP kể cả lưu lượng không đi qua HTTP.
B. HTTP(S) và các mẫu tấn công ở tầng ứng dụng web.
C. Tín hiệu vô tuyến giữa access point và thiết bị Wi-Fi.
D. Giao thức định tuyến giữa các router lõi.
Đáp án đúng: B

10. IDS khác IPS chủ yếu ở cách xử lý lưu lượng như thế nào?
A. IDS mã hóa lưu lượng; IPS chỉ giải mã lưu lượng.
B. IDS chỉ giám sát DNS; IPS chỉ giám sát HTTP.
C. IDS hoạt động inline; IPS luôn nhận bản sao thụ động.
D. IDS phát hiện và cảnh báo; IPS có thể chặn inline.
Đáp án đúng: D

11. Phát hiện dựa trên signature có hạn chế nào đáng chú ý?
A. Không thể phát hiện byte pattern đã biết trong gói tin.
B. Luôn cần giải mã mọi phiên TLS trước khi so khớp.
C. Khó nhận ra mẫu tấn công mới chưa có chữ ký phù hợp.
D. Không thể áp dụng cho lưu lượng mạng nội bộ.
Đáp án đúng: C

12. Một cảm biến IDS cần quan sát lưu lượng qua switch. SPAN port có rủi ro gì?
A. SPAN tự thay đổi payload trước khi gửi tới cảm biến.
B. Khi switch quá tải, bản sao mirror có thể bị mất gói.
C. SPAN chỉ sao chép gói multicast, bỏ qua unicast.
D. SPAN bắt buộc làm gián đoạn kết nối đang được giám sát.
Đáp án đúng: B

13. Khi IPS inline chặn nhầm lưu lượng hợp lệ, cách xử lý nào phù hợp?
A. Tắt toàn bộ kiểm tra để mọi luồng luôn được thông qua.
B. Tăng mức chặn cho mọi chữ ký có cảnh báo tương tự.
C. Bỏ qua phản hồi người dùng vì IPS không có false positive.
D. Xác minh mẫu, tinh chỉnh policy và kiểm soát ngoại lệ.
Đáp án đúng: D

14. VPN bảo vệ kết nối qua mạng không tin cậy bằng cách nào?
A. Làm cho thiết bị đầu cuối không thể bị malware xâm nhập.
B. Cấp quyền truy cập mọi subnet sau khi tunnel hình thành.
C. Tạo tunnel được xác thực và mã hóa giữa các đầu cuối.
D. Thay thế firewall và kiểm soát quyền ở từng dịch vụ.
Đáp án đúng: C

15. IPsec tunnel mode thường bảo vệ phần nào của gói IP gốc?
A. Đóng gói toàn bộ gói IP gốc bên trong gói mới.
B. Chỉ mã hóa payload TCP và giữ nguyên header IP gốc.
C. Chỉ xác thực địa chỉ MAC của hai router đầu cuối.
D. Chỉ bảo vệ gói DNS được gửi qua tunnel.
Đáp án đúng: A

16. Site-to-site VPN thường kết nối hai phạm vi nào?
A. Hai mạng hoặc gateway tại các địa điểm khác nhau.
B. Một trình duyệt cá nhân với một ứng dụng web public.
C. Một access point với các thiết bị không dây trong phòng.
D. Một user với tài khoản quản trị trên máy chủ database.
Đáp án đúng: A

17. Split tunneling trong VPN có nghĩa là gì?
A. Mã hóa mỗi gói tin bằng hai khóa độc lập cùng lúc.
B. Chỉ định tuyến một phần đích qua tunnel VPN.
C. Chia một kết nối TCP thành nhiều tunnel song song.
D. Tách khóa xác thực khỏi khóa mã hóa của IPsec.
Đáp án đúng: B

18. Trong WireGuard, cấu hình peer AllowedIPs thường có vai trò gì?
A. Chứa private key của mọi peer trong cùng tunnel.
B. Xác định thuật toán TLS mà trình duyệt phải sử dụng.
C. Thay thế xác minh public key của peer từ xa.
D. Gắn peer với các địa chỉ được định tuyến hoặc chấp nhận.
Đáp án đúng: D

19. DNSSEC cung cấp bảo đảm bảo mật nào cho dữ liệu DNS?
A. Mã hóa nội dung truy vấn để resolver không đọc được.
B. Xác thực nguồn gốc và tính toàn vẹn của bản ghi DNS.
C. Ẩn địa chỉ IP client khỏi authoritative name server.
D. Chặn mọi domain độc hại mà không cần chính sách lọc.
Đáp án đúng: B

20. DoH và DoT chủ yếu bảo vệ đoạn giao tiếp nào?
A. Toàn bộ đường đi DNS giữa mọi authoritative server.
B. Nội dung bản ghi DNS sau khi lưu trong cache công cộng.
C. Kênh từ client hoặc stub resolver tới DNS resolver.
D. Mọi truy vấn DNS khỏi chính resolver mà client đã chọn.
Đáp án đúng: C

21. Biện pháp nào giúp chống DNS cache poisoning hiệu quả?
A. Xác minh DNSSEC và dùng entropy truy vấn phù hợp.
B. Tắt cache trên mọi resolver và chấp nhận mọi response.
C. Chỉ cho phép truy vấn DNS qua UDP cổng bất kỳ.
D. Dùng cùng transaction ID cố định để dễ theo dõi truy vấn.
Đáp án đúng: A

22. DNS rebinding thường khai thác hành vi nào?
A. Resolver ký sai DNSSEC cho mọi bản ghi có TTL thấp.
B. Client gửi truy vấn DNS qua HTTPS thay vì UDP.
C. Máy chủ authoritative trả nhiều địa chỉ IP public hợp lệ.
D. Tên miền có thể trỏ tới IP nội bộ sau lần phân giải đầu.
Đáp án đúng: D

23. DNS filtering giúp tổ chức kiểm soát điều gì?
A. Mã hóa dữ liệu ứng dụng trước khi ghi vào database.
B. Ngăn mọi kết nối IP không dùng tên miền DNS.
C. Truy vấn tới domain độc hại hoặc trái chính sách.
D. Thay thế xác minh chứng thư TLS của website.
Đáp án đúng: C

24. WPA3-Personal cải thiện xác thực Wi-Fi chủ yếu bằng cơ chế nào?
A. Dùng một PSK công khai giống nhau cho mọi mạng.
B. Bỏ mã hóa liên kết để giảm độ trễ kết nối.
C. Thay xác thực Wi-Fi bằng DNSSEC trên resolver.
D. SAE làm giảm khả năng đoán mật khẩu offline.
Đáp án đúng: D

25. WPA-Enterprise thường dùng thành phần nào để xác thực từng người dùng?
A. Một PSK chung được chia sẻ cho mọi nhân viên.
B. 802.1X/EAP phối hợp với máy chủ RADIUS.
C. DNSSEC để xác minh tên access point nội bộ.
D. NAT để ánh xạ MAC của user sang tài khoản.
Đáp án đúng: B

26. Khi kết nối Wi-Fi doanh nghiệp bằng EAP-TLS, client cần kiểm tra gì?
A. SSID có giống tên mạng công ty được quảng bá.
B. Địa chỉ MAC của access point có nằm trong DHCP lease.
C. Chứng thư máy chủ xác thực thuộc CA và tên tin cậy.
D. Máy chủ RADIUS có dùng cùng subnet với client.
Đáp án đúng: C

27. Evil twin access point là tình huống nào?
A. AP hợp lệ phát nhiều beacon do cấu hình roaming.
B. AP giả mạo SSID hợp lệ để dụ thiết bị kết nối.
C. Client kết nối nhầm băng tần 2.4 GHz thay vì 5 GHz.
D. Router cấp hai địa chỉ DHCP cho cùng một thiết bị.
Đáp án đúng: B

28. Cách nào giúp phát hiện rogue access point trong văn phòng?
A. Đối chiếu AP phát hiện với inventory và policy.
B. Chỉ kiểm tra số lượng client đang dùng Wi-Fi mỗi ngày.
C. Tắt DHCP trên mọi switch access để ngăn AP mới.
D. Chỉ dựa vào SSID vì AP trái phép luôn có tên khác.
Đáp án đúng: A

29. Trong mô hình cloud phổ biến, security group stateful có nghĩa gì?
A. Luồng phản hồi được cho phép theo trạng thái kết nối.
B. Mỗi packet đều cần quy tắc ingress và egress riêng.
C. Quy tắc tự áp dụng cho mọi VPC trong cùng tài khoản.
D. Security group tự phát hiện malware trong payload ứng dụng.
Đáp án đúng: A

30. Network ACL stateless thường yêu cầu cấu hình nào?
A. Chỉ khai báo chiều vào vì chiều ra luôn được theo dõi.
B. Dùng identity user thay cho địa chỉ và protocol mạng.
C. Tự tạo state table dùng chung với mọi security group.
D. Quy tắc hai chiều phù hợp cho cả request và response.
Đáp án đúng: D

31. Đặt workload trong private subnet có ý nghĩa bảo vệ nào?
A. Mọi kết nối outbound tự động được mã hóa đầu cuối.
B. Workload không cần firewall vì subnet đã là private.
C. Không có route công khai cho kết nối vào trực tiếp.
D. Các dịch vụ trong subnet mặc định được xác thực lẫn nhau.
Đáp án đúng: C

32. Zero Trust Network Access nên đưa yếu tố nào vào quyết định truy cập?
A. Chỉ địa chỉ IP nội bộ mà thiết bị đang sử dụng.
B. Chỉ vị trí địa lý của người dùng khi đăng nhập lần đầu.
C. Xét danh tính, thiết bị, ngữ cảnh và tài nguyên.
D. Chỉ việc thiết bị đã kết nối VPN của tổ chức hay chưa.
Đáp án đúng: C

33. Với DDoS volumetric, biện pháp giảm thiểu nào thường cần đặt gần upstream?
A. Tăng kích thước log trên máy chủ ứng dụng bị tấn công.
B. Scrubbing lưu lượng upstream trước đường truyền.
C. Chỉ đổi cổng dịch vụ sang một số cổng ít phổ biến.
D. Chặn mọi request hợp lệ từ một quốc gia cố định.
Đáp án đúng: B

34. Network flow logs thường cho biết loại thông tin nào?
A. Toàn bộ plaintext của mọi phiên TLS đi qua router.
B. Mã nguồn và biến môi trường của workload gửi gói tin.
C. Nội dung file được truyền qua mọi kết nối TCP.
D. Metadata địa chỉ, port, protocol, byte và action.
Đáp án đúng: D

35. Khi phân tích packet capture của phiên HTTPS, điều gì thường đúng?
A. Toàn bộ nội dung HTTP luôn đọc được mà không cần khóa.
B. Payload mã hóa; metadata và một phần handshake vẫn thấy được.
C. TLS loại bỏ mọi thông tin IP và port khỏi packet capture.
D. Chỉ cần DNSSEC là có thể giải mã payload TLS đã bắt.
Đáp án đúng: B

36. Chính sách firewall cho IPv6 cần lưu ý điều gì?
A. Giữ kiểm soát tương đương và ICMPv6 cần thiết.
B. Chặn toàn bộ ICMPv6 vì IPv6 không cần thông điệp này.
C. Chỉ lọc IPv4 vì IPv6 không thể truy cập Internet.
D. Dùng NAT66 thay cho mọi quy tắc ingress và egress.
Đáp án đúng: A

Câu 1. Khi một nhóm người dùng báo ứng dụng chập chờn, bước điều tra đầu tiên nên là gì?
A. Thay DNS resolver của toàn bộ môi trường rồi đo kết quả.
B. Ghi thời điểm, bước tái hiện và phạm vi client bị ảnh hưởng.
C. Tăng mọi timeout trước khi xác nhận lỗi xảy ra ở tầng nào.
D. Khởi động lại gateway và tạm thời vô hiệu hóa access log.
Đáp án đúng: B

Câu 2. Một website lỗi trên mạng văn phòng nhưng chạy tốt qua mạng di động; phép thử nào hữu ích nhất?
A. So cùng URL, cùng thời điểm trên hai đường mạng khác nhau.
B. Chỉ xem CPU của backend mà không kiểm tra từng đường mạng.
C. Thử một URL khác trên mạng di động rồi suy ra nguyên nhân.
D. Đổi chứng chỉ TLS của website trước khi thu thập triệu chứng.
Đáp án đúng: A

Câu 3. Sau đợt triển khai, tỷ lệ request lỗi tăng; hành động nào dựa trên chứng cứ tốt nhất?
A. Mặc định do ứng dụng mới và xóa toàn bộ rule tường lửa.
B. Tăng số bản sao Pod rồi bỏ qua phép đo trước và sau deploy.
C. Khẳng định lỗi ở DNS khi chưa so sánh các request thành công.
D. Đối chiếu thời điểm deploy với log, metric và thay đổi liên quan.
Đáp án đúng: D

Câu 4. Vì sao nên kiểm tra DNS, đường IP, TCP, TLS rồi HTTP theo từng tầng?
A. Để chắc chắn mọi sự cố đều bắt đầu từ recursive DNS server.
B. Để áp dụng cùng một timeout cho tất cả protocol trên đường đi.
C. Để không cần đối chiếu log khi đã chạy một lệnh ping thành công.
D. Để xác định giai đoạn phát sinh lỗi thay vì đoán cấu hình.
Đáp án đúng: D

Câu 5. Lệnh `dig @1.1.1.1 example.com A` kiểm tra cụ thể điều gì?
A. Phản hồi bản ghi A từ recursive resolver được chỉ định.
B. Phản hồi HTTP khi truy cập máy chủ web bằng địa chỉ IPv4.
C. Bản ghi trong file hosts mà ứng dụng trên máy đang dùng.
D. Đường đi của TCP đến dịch vụ HTTPS trên máy đích.
Đáp án đúng: A

Câu 6. Khi truy vấn DNS nhận `NXDOMAIN`, cách diễn giải phù hợp nhất là gì?
A. DNS báo tên có tồn tại nhưng không chứa record A đang hỏi.
B. DNS báo chứng chỉ TLS của host đã hết hạn sử dụng.
C. DNS báo tên đang hỏi không tồn tại trong không gian tên.
D. DNS báo máy chủ web đang từ chối kết nối TCP.
Đáp án đúng: C

Câu 7. Phản hồi DNS `SERVFAIL` khác `NXDOMAIN` về ý nghĩa nào?
A. Resolver lỗi xử lý, chưa kết luận tên không tồn tại.
B. Tên miền chắc chắn chưa được đăng ký ở mọi DNS zone.
C. Tên miền tồn tại nhưng bản ghi AAAA chưa được công bố.
D. Đường truyền HTTPS đến web server đã bị proxy ngắt.
Đáp án đúng: A

Câu 8. Authoritative DNS đã cập nhật IP nhưng một số người dùng vẫn thấy IP cũ; vì sao?
A. Recursive resolver có thể còn giữ bản ghi cũ đến khi hết TTL.
B. Authoritative server bắt buộc chờ mọi trình duyệt khởi động lại.
C. TCP luôn cache địa chỉ IP bằng lifetime của TLS certificate.
D. Router bắt buộc đồng bộ A record mới cho mỗi bảng định tuyến.
Đáp án đúng: A

Câu 9. Muốn kiểm tra chuỗi ủy quyền DNS từ root đến zone có thẩm quyền, dùng gì?
A. `curl -v https://example.com` để kiểm tra HTTP response.
B. `dig +trace example.com` để theo dõi các referral DNS.
C. `ss -ltnp` để liệt kê các socket TCP đang lắng nghe.
D. `ip route get 203.0.113.10` để xem route của máy.
Đáp án đúng: B

Câu 10. Trên Linux, `getent hosts` có điểm khác biệt gì so với `dig` thông thường?
A. Luôn truy vấn root DNS trực tiếp và bỏ qua resolver cục bộ.
B. Luôn dùng DNS-over-HTTPS để xác minh tên được mã hóa.
C. Tra cứu theo cấu hình hệ, có thể gồm cả file hosts.
D. Chỉ đọc authoritative SOA và không thể trả địa chỉ IP.
Đáp án đúng: C

Câu 11. Một domain hoạt động qua IPv4 nhưng lỗi khi client ưu tiên IPv6; cặp phép thử nào phù hợp?
A. Chỉ chạy `curl -I` nhiều lần trên cùng kết nối IPv4.
B. Chỉ đổi TTL của bản ghi A và bỏ qua mọi bản ghi AAAA.
C. So `curl -4` với `curl -6` trên cùng URL để tách lỗi.
D. Chuyển hết request sang UDP 53 để kiểm tra đường HTTP.
Đáp án đúng: C

Câu 12. Nếu nghi máy Linux chưa được gán IP đúng trên interface, nên kiểm tra lệnh nào?
A. Xem các HTTP header phía server bằng `curl -I`.
B. Xem địa chỉ interface bằng lệnh `ip addr show`.
C. Xem bảng ARP của router từ lệnh `dig +trace`.
D. Xem chuỗi chứng chỉ từ lệnh `openssl version`.
Đáp án đúng: B

Câu 13. Lệnh Linux `ip route get 203.0.113.10` thường giúp xác định điều gì?
A. Bản ghi DNS A mà resolver trả về cho hostname đích.
B. Các HTTP header mà reverse proxy chuyển tới backend.
C. Chứng chỉ TLS mà trình duyệt nhận từ máy chủ đích.
D. Route, gateway và interface mà kernel chọn cho đích.
Đáp án đúng: D

Câu 14. Trên cùng subnet IPv4, bảng neighbor chứa thông tin quan trọng nào khi chẩn đoán?
A. Ánh xạ hostname sang certificate public key của TLS.
B. Ánh xạ IP lân cận sang địa chỉ MAC trên liên kết.
C. Ánh xạ URL path sang cổng của HTTP reverse proxy.
D. Ánh xạ DNS TTL sang thời gian chờ TCP handshake.
Đáp án đúng: B

Câu 15. Vì sao không thể kết luận web server chết chỉ vì lệnh `ping` thất bại?
A. ICMP bị chặn không chứng minh dịch vụ TCP cũng lỗi.
B. Ping luôn sử dụng HTTP nên mọi web server đều bỏ qua.
C. Ping chỉ chạy được trên IPv6 và không hỗ trợ mạng IPv4.
D. Ping chứng minh được server đã nhận TLS handshake.
Đáp án đúng: A

Câu 16. Trong `traceroute`, dấu `*` tại một hop có nhất thiết là hop đó làm mất traffic không?
A. Có; mọi dấu sao đều xác nhận router đã ngắt đường đi.
B. Có; mọi hop buộc phải phản hồi probe trong mọi điều kiện.
C. Không; dấu sao luôn cho biết server đã trả HTTP 200.
D. Không; hop có thể lọc hoặc giới hạn phản hồi probe.
Đáp án đúng: D

Câu 17. Traceroute thường tận dụng đặc tính nào của TTL/Hop Limit trong IP?
A. Giảm mỗi hop, để router báo khi gói hết giới hạn hop.
B. Tăng mỗi hop, để client phát hiện bản ghi DNS hết hạn.
C. Giữ nguyên mỗi hop, để đo cache HTTP ở proxy trung gian.
D. Đổi theo TLS SNI, để lọc request không đúng hostname.
Đáp án đúng: A

Câu 18. Khi `mtr` cho thấy loss ở hop giữa nhưng hop đích ổn, nên nhận định thế nào?
A. Mất gói ở hop giữa chắc chắn khiến toàn bộ TCP request lỗi.
B. Cần xem tới hop cuối; hop giữa có thể hạn chế phản hồi ICMP.
C. Tăng băng thông hop giữa là biện pháp cần làm ngay lập tức.
D. Hop cuối ổn chứng minh tất cả giao thức đều không lỗi.
Đáp án đúng: B

Câu 19. Request nhỏ chạy tốt nhưng request lớn bị treo qua VPN; nguyên nhân mạng nào nên nghi ngờ?
A. MTU hoặc Path MTU Discovery gặp vấn đề trên đường truyền.
B. DNS TTL quá thấp nên kết nối TCP tự động bị ngắt sau DNS.
C. HTTP cookie quá ngắn khiến bộ định tuyến loại gói TCP.
D. ALPN của trình duyệt không nhận ra địa chỉ IPv4 trên VPN.
Đáp án đúng: A

Câu 20. Bắt tay TCP thông thường thiết lập kết nối theo thứ tự nào?
A. Client ACK, server SYN rồi client FIN hoàn tất.
B. Client FIN, server ACK rồi client SYN hoàn tất.
C. Client SYN, server FIN rồi client RST hoàn tất.
D. Client SYN, server SYN-ACK, cuối cùng client ACK.
Đáp án đúng: D

Câu 21. Bắt gói thấy client gửi SYN lặp lại nhưng không có SYN-ACK về; nên kiểm tra gì?
A. Chứng chỉ TLS hết hạn vì TLS đã hoàn tất xác minh peer.
B. HTTP 404 vì web server đã xử lý request và từ chối path.
C. Cookie phiên vì trình duyệt đã nhận HTTP response đầu tiên.
D. Lọc gói, tuyến phản hồi hoặc endpoint không nhận được SYN.
Đáp án đúng: D

Câu 22. Khi SYN đến cổng TCP nhận ngay RST từ đích, điều đó gợi ý điều gì?
A. Đường truyền đã mất hết gói và không có response nào.
B. Tên DNS đang truy vấn không tồn tại trong zone.
C. Đích từ chối TCP, có thể do không có listener.
D. Client và server đã bắt tay TLS và trao đổi HTTP.
Đáp án đúng: C

Câu 23. Muốn biết tiến trình Linux đang lắng nghe cổng TCP 8080 tại địa chỉ nào, dùng gì?
A. `dig -t MX` để xem địa chỉ bind của web server.
B. `ss -ltnp` liệt kê địa chỉ nghe và tên tiến trình.
C. `ip route get` để liệt kê header HTTP của listener.
D. `openssl s_client` để xem các process trong kernel.
Đáp án đúng: B

Câu 24. Muốn bắt riêng gói liên quan host `203.0.113.7` và port 443 trên eth0, bộ lọc nào đúng?
A. `tcpdump -ni eth0 'net 443 and host example.com'`.
B. `tcpdump -ni eth0 'tcp ttl 443 and udp 53'`.
C. `tcpdump -ni eth0 'host 203.0.113.7 and port 443'`.
D. `tcpdump -ni eth0 'http status 443 and host 7'`.
Đáp án đúng: C

Câu 25. Trong packet capture, các TCP retransmission lặp lại cho thấy điều gì cần điều tra?
A. Chắc chắn có lỗi DNSSEC dù DNS query đã trả kết quả.
B. Chắc chắn backend đã trả HTTP 404 do URL không khớp.
C. Chắc chắn TLS certificate sai tên và bị trình duyệt từ chối.
D. Segment chưa được ACK kịp, có thể do mất gói hoặc trễ.
Đáp án đúng: D

Câu 26. TCP receiver quảng bá `Zero Window` trong capture thường phản ánh vấn đề nào?
A. Bên gửi đã hết DNS cache và phải làm lại phân giải.
B. Receive buffer bên nhận đầy, chưa nhận thêm dữ liệu.
C. Router đã giảm IP TTL của gói tin xuống đúng 0.
D. TLS client đang không hỗ trợ chứng chỉ phía server.
Đáp án đúng: B

Câu 27. Khi cần quan sát từng bước kết nối HTTPS từ phía client, `curl -v` hữu ích vì sao?
A. Luôn cho thấy mọi router chuyển tiếp giữa hai điểm.
B. Hiện bước kết nối, bắt tay TLS và HTTP phía client.
C. Tự ghi toàn bộ packet capture ở mọi interface mạng.
D. Tự thay đổi firewall rule khi phát hiện TLS bị lỗi.
Đáp án đúng: B

Câu 28. Lệnh `openssl s_client -connect example.com:443 -servername example.com` giúp xem gì?
A. Các DNS referral từ root cho đến nameserver của zone.
B. Các dòng iptables được áp dụng trong container backend.
C. Các HTTP access log trên reverse proxy ở port 443.
D. Chi tiết TLS handshake và chứng chỉ cho hostname SNI.
Đáp án đúng: D

Câu 29. Lỗi TLS hostname mismatch thường xảy ra trong tình huống nào?
A. Địa chỉ IPv4 trả về không nằm cùng subnet với client.
B. DNS resolver trả record AAAA thay vì record A khi hỏi.
C. Hostname truy cập không khớp tên ghi trong chứng chỉ.
D. HTTP server chỉ trả response qua keep-alive connection.
Đáp án đúng: C

Câu 30. Khi cần biết TLS chọn HTTP/2 hay HTTP/1.1, nên kiểm tra quá trình nào?
A. ARP resolution từ địa chỉ IPv4 sang địa chỉ MAC ở L2.
B. DNS negative caching ở recursive resolver của hệ thống.
C. TCP retransmission trên cổng UDP của dịch vụ HTTP.
D. Thỏa thuận ALPN trong TLS handshake giữa hai đầu.
Đáp án đúng: D

Câu 31. Dùng `curl --resolve example.com:443:203.0.113.10 https://example.com/` nhằm kiểm thử điều gì?
A. Buộc web server cập nhật A record trên authoritative DNS.
B. Thay chứng chỉ TLS của server bằng certificate từ client.
C. Ép trình duyệt bỏ qua Host header và dùng IP trong URL.
D. Chỉ định IP thử nghiệm, vẫn giữ hostname cho HTTP/TLS.
Đáp án đúng: D

Câu 32. Tùy chọn `curl -k` có ý nghĩa gì khi chẩn đoán HTTPS?
A. Tự xác nhận certificate hợp lệ trên mọi host truy cập.
B. Bắt buộc HTTPS client đàm phán ciphersuite mới nhất.
C. Tạm bỏ kiểm tra chứng chỉ TLS để khoanh vùng lỗi.
D. Tự sửa chuỗi chứng chỉ CA đang thiếu trên server.
Đáp án đúng: C

Câu 33. Khi reverse proxy trả HTTP 502, một nguyên nhân thường cần kiểm tra là gì?
A. Upstream trả lỗi hoặc proxy không giao tiếp được.
B. Ứng dụng đã trả HTTP 201 cho request tạo tài nguyên.
C. Trang web đã chuyển hướng thành công sang domain mới.
D. Client đã nhận HTTP 304 do cache còn hiệu lực.
Đáp án đúng: A

Câu 34. Khi gateway trả HTTP 503, dữ liệu nào nên kiểm tra trước trong cụm backend?
A. Endpoint khả dụng, health check và trạng thái quá tải.
B. Chỉ số record DNS TXT của domain dùng cho email.
C. Phiên bản TLS của trình duyệt nhưng bỏ qua trạng thái app.
D. Số lượng client đang dùng IPv6 nhưng bỏ qua log gateway.
Đáp án đúng: A

Câu 35. Với HTTP 504 từ gateway, biểu hiện nào thường phù hợp nhất?
A. Máy chủ đã trả về tài nguyên mới và HTTP 201.
B. Gateway timeout trong lúc chờ upstream phản hồi.
C. Trình duyệt không tìm thấy tên DNS và báo NXDOMAIN.
D. Server từ chối cổng TCP bằng gói RST tức thời.
Đáp án đúng: B

Câu 36. Khi nghi firewall hoặc NAT gây timeout một chiều, nên đối chiếu điều gì?
A. Chỉ bản ghi CNAME, bỏ qua kết quả handshake TCP.
B. So luồng đi và về, rule firewall cùng trạng thái NAT.
C. Chỉ nội dung JSON response từ ứng dụng đã trả 200.
D. Chỉ ngày hết hạn certificate khi cổng TCP còn đóng.
Đáp án đúng: B

Câu 37. DNS response UDP bị đặt cờ `TC` vì cắt bớt dữ liệu; bước xử lý tiếp theo là gì?
A. Chuyển truy vấn sang HTTP GET qua cổng 443 của web.
B. Xóa toàn bộ record NS vì delegation đã bị hỏng.
C. Gửi lại DNS query qua TCP để nhận phản hồi đầy đủ.
D. Buộc resolver trả NXDOMAIN dù tên còn tồn tại.
Đáp án đúng: C

Câu 38. Khi request đi qua gateway và nhiều service, cách nối log giữa các hệ thống là gì?
A. Chỉ so tên hostname của từng máy chủ đang chạy.
B. Chỉ xem log start-up mà bỏ qua nhật ký từng request.
C. Truyền cùng correlation ID qua gateway và từng service.
D. Chỉ lọc theo CPU tổng của toàn bộ Pod đang chạy.
Đáp án đúng: C

Câu 39. Vì sao chỉ số p95/p99 latency thường cần thiết ngoài latency trung bình?
A. Để thấy phần đuôi request chậm bị giá trị trung bình che.
B. Để thay hoàn toàn packet capture khi nghi có mất gói.
C. Để suy ra chính xác router nào gây lỗi từ một phép đo.
D. Để xác định ngay DNS record cần sửa mà không cần truy vấn.
Đáp án đúng: A

Câu 40. Sau khi hình thành giả thuyết về lỗi mạng, cách sửa và xác minh nào đáng tin cậy?
A. Đồng thời sửa DNS, firewall, proxy để tăng cơ hội hết lỗi.
B. Vô hiệu hóa toàn bộ log nhằm giảm nhiễu khi chạy thử.
C. Đổi một yếu tố có kiểm soát, đo lại và chuẩn bị rollback.
D. Chỉ dựa vào một lần request thành công để kết luận hết lỗi.
Đáp án đúng: C

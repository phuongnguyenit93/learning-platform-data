Câu 1. Stub resolver trên máy người dùng thường làm gì khi cần phân giải một tên miền?
A. Trực tiếp hỏi từng root và TLD cho mọi tên truy vấn.
B. Chuyển yêu cầu DNS đến recursive resolver đã cấu hình.
C. Đọc zone file cục bộ để quyết định tên miền hợp lệ.
D. Đóng vai authoritative server cho từng domain đã hỏi.
Đáp án đúng: B

Câu 2. Khi resolver không có cache, root server thường phản hồi gì cho tên dưới `.com`?
A. Chỉ dẫn đến nameserver TLD `.com` qua bản ghi NS.
B. Địa chỉ IP cuối cùng của host dù chưa hỏi `.com`.
C. Tên nameserver authoritative của mọi zone dưới `.com`.
D. Dữ liệu cache từ resolver thuộc cùng ISP với client.
Đáp án đúng: A

Câu 3. Máy chủ DNS authoritative khác recursive resolver ở điểm nào?
A. Phục vụ dữ liệu zone mà nó có thẩm quyền quản lý.
B. Luôn truy vấn root và TLD thay mặt mỗi người dùng.
C. Chỉ trả dữ liệu từ cache lấy ở authoritative khác.
D. Luôn gửi các yêu cầu DNS qua kết nối HTTP/2.
Đáp án đúng: A

Câu 4. Zone cha ủy quyền `dev.example.com` sang zone con bằng cách nào?
A. Chỉ tạo A record trên zone cha cho tên zone con.
B. Đặt NS record ủy quyền ở zone cha cho zone con.
C. Chỉ đặt TXT record thông báo IP của server con.
D. Tự xóa SOA record của zone con sau khi khai báo.
Đáp án đúng: B

Câu 5. Khi nameserver của zone con có tên nằm ngay trong zone đó, glue record giúp gì?
A. Lưu bản sao toàn bộ bản ghi của zone con ở zone cha.
B. Cung cấp IP nameserver để tránh vòng lặp phân giải.
C. Ký dữ liệu NS bằng khóa riêng của recursive resolver.
D. Chuyển DNS query qua TCP khi referral chứa nhiều NS.
Đáp án đúng: B

Câu 6. Trong SOA record, trường serial chủ yếu phục vụ hoạt động nào?
A. Đặt giá trị TTL bắt buộc cho mọi bản ghi trong zone.
B. Mã hóa nội dung zone trước khi sao chép đến secondary.
C. Xác nhận tính hợp lệ của DNSSEC key theo thời gian.
D. Giúp secondary so phiên bản zone để quyết định cập nhật.
Đáp án đúng: D

Câu 7. Phân biệt hai record `A` và `AAAA` trong DNS như thế nào?
A. `A` ánh xạ IPv6, còn `AAAA` ánh xạ IPv4.
B. `A` ánh xạ IPv4, còn `AAAA` ánh xạ IPv6.
C. `A` chỉ mail server, còn `AAAA` chỉ DNS server.
D. `A` ghi bí danh, còn `AAAA` ghi nameserver.
Đáp án đúng: B

Câu 8. Khi khai báo CNAME cho `www.example.com`, giá trị record biểu thị điều gì?
A. Tên alias được ánh xạ trực tiếp đến địa chỉ IPv4.
B. Tên alias chứa nhiều mail server theo thứ tự ưu tiên.
C. Tên alias dùng để xác thực chữ ký RRset của zone.
D. Tên alias tham chiếu đến tên DNS chuẩn khác.
Đáp án đúng: D

Câu 9. Vì sao không thể thêm CNAME đúng chuẩn trực tiếp tại apex `example.com` của zone?
A. Apex chỉ cho phép record A nên không thể đặt AAAA.
B. Apex cần có PTR trước khi có thể khai báo CNAME.
C. Apex có SOA/NS nên CNAME không thể cùng tồn tại.
D. Apex không được có bất kỳ bản ghi nào ngoài SOA.
Đáp án đúng: C

Câu 10. Với nhiều record MX, giá trị preference được sử dụng thế nào?
A. Giá trị preference lớn hơn được thử trước.
B. Giá trị preference nhỏ hơn được thử trước.
C. Giá trị TTL thấp hơn luôn được thử trước.
D. Giá trị priority phụ thuộc vào DNS resolver.
Đáp án đúng: B

Câu 11. Record TXT thường được dùng cho trường hợp nào?
A. Cung cấp địa chỉ IPv6 cho client web và mail.
B. Ủy quyền một zone con đến DNS nameserver khác.
C. Sắp xếp thứ tự mail exchanger theo mức ưu tiên.
D. Xuất bản dữ liệu văn bản như chính sách SPF.
Đáp án đúng: D

Câu 12. Trong reverse DNS, PTR record chủ yếu hỗ trợ việc gì?
A. Ánh xạ tên miền sang địa chỉ IPv6 của ứng dụng.
B. Ánh xạ alias sang một hostname canonical khác.
C. Ánh xạ địa chỉ IP về tên miền trong reverse DNS.
D. Ánh xạ domain sang danh sách NS của zone con.
Đáp án đúng: C

Câu 13. Nếu ứng dụng cần công bố hostname và port của một dịch vụ, record nào thích hợp?
A. A record chỉ định host và port qua dữ liệu IPv4.
B. MX record chỉ định host và port qua mail exchanger.
C. SRV chỉ định host và port cùng mức ưu tiên.
D. PTR record chỉ định host và port theo reverse lookup.
Đáp án đúng: C

Câu 14. CAA record thường được dùng để kiểm soát chính sách nào?
A. Chỉ định resolver được phép cache câu trả lời DNS.
B. Chỉ định CA được phép cấp chứng chỉ cho domain.
C. Chỉ định server được phép truy vấn mọi record TXT.
D. Chỉ định tên máy chủ trả lời qua cổng TCP 853.
Đáp án đúng: B

Câu 15. TTL của một DNS record chủ yếu biểu thị điều gì với resolver?
A. Thời lượng record có thể nằm trong cache resolver.
B. Thời lượng DNSSEC signature luôn còn hợp lệ.
C. Thời lượng zone transfer phải hoàn thành trên TCP.
D. Thời lượng client luôn phải dùng kết nối UDP.
Đáp án đúng: A

Câu 16. Khi chuẩn bị đổi IP website và muốn giảm thời gian cache cũ, biện pháp nào tốt?
A. Tăng TTL tại thời điểm đổi IP để mọi cache làm mới.
B. Xóa NS record để buộc mọi resolver hỏi lại ngay.
C. Giảm TTL trước, đợi cache cũ hết hạn rồi đổi IP.
D. Đổi SOA serial để ép toàn Internet bỏ dữ liệu cache.
Đáp án đúng: C

Câu 17. Sau khi đổi A record ở authoritative server, vì sao vài client vẫn đến IP cũ?
A. Resolver sẽ luôn hỏi lại authoritative cho mỗi truy vấn.
B. Resolver xóa cache ngay khi zone thay đổi SOA serial.
C. Resolver còn giữ bản ghi cũ cho đến khi TTL hết.
D. Resolver tự đồng bộ bản ghi mới qua mọi router mạng.
Đáp án đúng: C

Câu 18. Phân biệt NXDOMAIN với phản hồi NODATA trong DNS như thế nào?
A. NXDOMAIN: thiếu loại; NODATA: không có tên nào như vậy.
B. NXDOMAIN: lỗi server; NODATA: phiên bản DNSSEC hết hạn.
C. NXDOMAIN: kết nối timeout; NODATA: bị firewall chặn.
D. NXDOMAIN: không có tên; NODATA: có tên nhưng thiếu loại.
Đáp án đúng: D

Câu 19. Negative caching của recursive resolver lưu thông tin gì?
A. Giữ kết quả tên không tồn tại theo thông tin SOA.
B. Giữ mọi TCP connection mở theo refresh interval của NS.
C. Giữ mọi bản ghi A đến khi có một truy vấn DoH thành công.
D. Giữ các response cũ bất kể TTL được authoritative đặt.
Đáp án đúng: A

Câu 20. Trong DNS header, cờ RD thể hiện yêu cầu nào của client?
A. RD xác nhận response đã được DNSSEC kiểm chứng.
B. RD báo kết quả vừa bị cắt bớt vì quá dài.
C. RD cho biết máy chủ đang trả lời authoritative.
D. RD yêu cầu resolver thực hiện truy vấn đệ quy.
Đáp án đúng: D

Câu 21. Cờ AA trong một DNS response cho biết điều gì?
A. AA cho biết response đã qua DNSSEC validation.
B. AA cho biết client yêu cầu recursion qua resolver.
C. AA cho biết câu trả lời từ server có thẩm quyền.
D. AA cho biết DNS packet bị cắt bớt kích thước.
Đáp án đúng: C

Câu 22. Với DNS truyền thống không mã hóa, mô tả nào đúng về cổng và giao thức?
A. DNS thường dùng TCP 443; UDP 443 cũng có thể dùng.
B. DNS chỉ dùng UDP 53; TCP 53 dành riêng cho HTTP.
C. DNS dùng TCP 853 mặc định; UDP 53 chỉ dành cho DNSSEC.
D. DNS thường dùng UDP 53; TCP 53 cũng được hỗ trợ.
Đáp án đúng: D

Câu 23. Khi DNS response qua UDP có cờ TC báo bị cắt bớt, client có thể làm gì?
A. Đổi tên miền sang địa chỉ IPv6 để truy vấn tiếp.
B. Xóa toàn bộ cache DNS của mọi thiết bị để thử lại.
C. Tự bỏ qua phần response đã bị cắt rồi sử dụng.
D. Gửi lại truy vấn bằng TCP để nhận đủ response.
Đáp án đúng: D

Câu 24. EDNS(0) trong DNS mang lại khả năng nào?
A. Mã hóa DNS bằng certificate của web server.
B. Mở rộng DNS như kích thước UDP và các options.
C. Bỏ qua ủy quyền giữa root, TLD và zone con.
D. Tạo kết nối TCP cố định giữa resolver và zone.
Đáp án đúng: B

Câu 25. Trong vận hành primary/secondary DNS, AXFR được dùng để làm gì?
A. Chỉ gửi các thay đổi kể từ serial lần trước.
B. Tạo bản ghi mới dựa trên negative cache.
C. Chỉ thực hiện qua UDP để giảm độ trễ.
D. Chuyển toàn bộ zone, thông thường qua TCP.
Đáp án đúng: D

Câu 26. Trong DNSSEC, bản ghi RRSIG có chức năng nào?
A. Chứa khóa công khai của root cho mọi zone con.
B. Chứa bí mật để mã hóa truy vấn giữa client và DNS.
C. Chứa chữ ký số cho một tập bản ghi DNS (RRset).
D. Chứa địa chỉ IP nameserver khi delegation ở parent.
Đáp án đúng: C

Câu 27. Bản ghi DNSKEY trong zone đã ký DNSSEC có vai trò nào?
A. Công bố địa chỉ IPv6 dùng cho mọi endpoint của zone.
B. Công bố khóa TLS dùng để giải mã tất cả request DNS.
C. Công bố checksum nhằm xác nhận zone transfer hoàn tất.
D. Công bố khóa công khai dùng để kiểm tra chữ ký zone.
Đáp án đúng: D

Câu 28. Khi DNSSEC tạo chain of trust giữa parent và child zone, DS record nằm ở đâu và giúp gì?
A. DS trong parent liên kết tin cậy đến khóa của child.
B. DS trong child lưu khóa bí mật để parent giải mã.
C. DS trong parent ghi IPv4 cho authoritative của child.
D. DS trong child đặt TTL cho DNSKEY của parent zone.
Đáp án đúng: A

Câu 29. DNSSEC dùng NSEC hoặc NSEC3 chủ yếu để làm gì?
A. Chứng minh có xác thực rằng tên DNS không tồn tại.
B. Cung cấp mật khẩu để resolver kiểm tra truy vấn DNS.
C. Cung cấp địa chỉ Anycast cho mọi server trong zone.
D. Cung cấp alias từ domain đến host đang được truy cập.
Đáp án đúng: A

Câu 30. Khi DNSSEC signature không xác minh được, validating resolver có thể trả gì?
A. NXDOMAIN để báo tên DNS đã bị xóa khỏi zone.
B. NOERROR và bỏ qua mọi chữ ký DNSSEC lỗi.
C. SERVFAIL khi không xác thực được dữ liệu DNSSEC.
D. DNSKEY mới do resolver tự ký thay authoritative.
Đáp án đúng: C

Câu 31. Phát biểu nào đúng về ranh giới bảo mật của DNSSEC?
A. Mã hóa truy vấn DNS nhưng không xác thực bản ghi.
B. Buộc truy vấn dùng TLS qua cổng 853 mặc định.
C. Xác thực dữ liệu DNS nhưng không mã hóa câu hỏi.
D. Thay DoH bằng HTTPS qua các cổng DNS truyền thống.
Đáp án đúng: C

Câu 32. DNS over TLS (DoT) thường bảo vệ truy vấn DNS bằng cách nào?
A. Dùng HTTPS cho DNS, thường trên TCP cổng 443.
B. Dùng TLS cho DNS, thường trên TCP cổng 853.
C. Dùng UDP thuần cho DNS, thường trên cổng 53.
D. Dùng DNSSEC để mã hóa DNS trên UDP cổng 53.
Đáp án đúng: B

Câu 33. DNS over HTTPS (DoH) truyền dữ liệu DNS theo cách nào?
A. Mã hóa DNS qua TLS trực tiếp, thường qua TCP 853.
B. Đóng gói DNS trong HTTPS, thường qua cổng 443.
C. Dùng UDP 53 không mã hóa với mở rộng EDNS(0).
D. Ký RRset bằng DNSSEC rồi gửi qua UDP thông thường.
Đáp án đúng: B

Câu 34. QNAME minimization giúp recursive resolver giảm lộ thông tin ra sao?
A. Gửi toàn bộ tên truy vấn đến tất cả máy chủ cha.
B. Bắt buộc mọi DNS query luôn được mã hóa bằng TLS.
C. Chỉ hỏi nhãn DNS cần thiết ở từng mức phân giải.
D. Giảm TTL về 0 để xóa cache trong mọi resolver.
Đáp án đúng: C

Câu 35. Với private DNS zone trong cloud, split-horizon DNS thể hiện hành vi nào?
A. Trả bản ghi khác nhau theo view hoặc nguồn truy vấn.
B. Trả mọi DNS query đến cùng một public nameserver.
C. Trả bản ghi được mã hóa thay cho bản ghi TXT.
D. Trả duy nhất NXDOMAIN cho các truy vấn nội bộ.
Đáp án đúng: A

Câu 36. Anycast giúp tăng tính sẵn sàng của hạ tầng DNS theo cơ chế nào?
A. Nhiều DNS server quảng bá cùng IP ở nhiều vị trí.
B. Mỗi DNS server cần một IP riêng nhưng chung CNAME.
C. Một máy DNS tự sao chép toàn bộ bản ghi bằng AXFR.
D. Mỗi domain bắt buộc có recursive resolver riêng.
Đáp án đúng: A

Câu 37. Muốn theo dõi chuỗi ủy quyền DNS từ root đến authoritative, nên dùng lệnh nào?
A. `dig +short example.com` chỉ in câu trả lời cuối.
B. `dig +tcp example.com` dùng TCP với resolver mặc định.
C. `dig +dnssec example.com` yêu cầu bản ghi DNSSEC.
D. `dig +trace example.com` theo dõi các bước referral.
Đáp án đúng: D

Câu 38. Để hỏi trực tiếp một authoritative server mà không yêu cầu recursion, chọn lệnh nào?
A. `dig @ns1.example.net example.com A +norecurse`.
B. `dig example.com A +short` qua resolver mặc định.
C. `dig +tcp example.com A` qua resolver mặc định.
D. `dig example.com ANY` qua resolver mặc định.
Đáp án đúng: A

Câu 39. Trong Kubernetes, CoreDNS thường được dùng để thực hiện nhiệm vụ gì?
A. Giải tên Kubernetes Service trong nội bộ cluster.
B. Tự phát hành chứng chỉ TLS cho mọi Pod đang chạy.
C. Tự cài mạng overlay và IP của mọi worker node.
D. Tự chuyển HTTP request đến container theo Ingress.
Đáp án đúng: A

Câu 40. Khi Service Kubernetes là headless (`clusterIP: None`), DNS thường trả gì?
A. Duy nhất ClusterIP cho toàn bộ Pod của Service.
B. Địa chỉ các endpoint thay vì một ClusterIP cố định.
C. Địa chỉ NodePort của mọi máy chủ Kubernetes.
D. Địa chỉ CoreDNS thay cho mỗi endpoint của Service.
Đáp án đúng: B

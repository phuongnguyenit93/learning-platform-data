Những vấn đề nào được DNS giải quyết khi ứng dụng dùng tên miền thay cho địa chỉ IP để giao tiếp?
Bạn sẽ mô tả sự khác biệt giữa tên miền, hostname, nhãn DNS và fully qualified domain name qua một ví dụ như thế nào?
Bạn sẽ phân biệt cấu trúc không gian tên phân cấp của DNS với cách tổ chức dữ liệu trong một cơ sở dữ liệu tập trung ra sao?
Bạn sẽ giải thích vai trò của root zone, top-level domain và các miền con trong quá trình phân giải tên như thế nào?
Bạn sẽ mô tả hành trình phân giải một tên miền từ ứng dụng đến khi nhận được địa chỉ IP như thế nào?
Bạn sẽ phân biệt stub resolver, recursive resolver và authoritative name server dựa trên trách nhiệm của từng thành phần ra sao?
Bạn sẽ giải thích sự khác nhau giữa truy vấn recursive và iterative bằng cách theo dấu một tên miền chưa được cache như thế nào?
Bạn sẽ xác định điều kiện nào khiến recursive resolver phải truy vấn lên hệ thống phân cấp DNS thay vì trả lời từ cache?
Bạn sẽ giải thích vai trò của root hints trong việc khởi động phân giải khi resolver chưa biết đường đến miền cần tìm như thế nào?
Bạn sẽ phân tích khác biệt giữa DNS resolver của hệ điều hành, của trình duyệt và của mạng nội bộ ra sao?
Bạn sẽ kiểm tra hệ thống đang dùng resolver nào khi cấu hình DNS trên máy và trong ứng dụng cho kết quả khác nhau như thế nào?
Bạn sẽ xác định khi nào một máy chủ DNS đóng vai trò forwarder thay vì trực tiếp thực hiện phân giải đệ quy ra sao?
Bạn sẽ giải thích cấu trúc của một thông điệp DNS gồm header, question, answer, authority và additional như thế nào?
Bạn sẽ phân tích ý nghĩa của các cờ RD, RA và AA khi so sánh phản hồi từ resolver với máy chủ có thẩm quyền ra sao?
Bạn sẽ giải thích sự khác nhau giữa câu trả lời authoritative và câu trả lời lấy từ cache về nguồn gốc dữ liệu như thế nào?
Bạn sẽ phân biệt các mã phản hồi NOERROR, NXDOMAIN, SERVFAIL và REFUSED qua các nguyên nhân thực tế như thế nào?
Bạn sẽ phân biệt phản hồi NODATA với NXDOMAIN thông qua những ví dụ truy vấn nào?
Bạn sẽ điều tra một truy vấn DNS timeout khác với một truy vấn nhận được phản hồi SERVFAIL bằng các bước nào?
Bạn sẽ mô tả cơ chế delegation từ zone cha sang zone con và cách resolver nhận được danh sách name server như thế nào?
Bạn sẽ giải thích vai trò của bản ghi NS và glue record khi name server của zone nằm bên trong chính zone đó ra sao?
Bạn sẽ kiểm tra một delegation bị cấu hình sai giữa registrar, zone cha và máy chủ DNS có thẩm quyền như thế nào?
Bạn sẽ phân biệt zone, domain và vùng quản trị DNS được ủy quyền bằng một hệ thống có nhiều subdomain ra sao?
Bạn sẽ thiết kế cách phân chia zone và ủy quyền subdomain cho các nhóm vận hành độc lập như thế nào?
Bạn sẽ giải thích tác dụng của bản ghi SOA trong quản trị zone và các thông tin quan trọng cần kiểm tra như thế nào?
Bạn sẽ sử dụng serial của SOA để hỗ trợ đồng bộ zone và phát hiện bản cập nhật chưa đến secondary server ra sao?
Bạn sẽ phân biệt primary và secondary authoritative DNS về nguồn dữ liệu và cách cập nhật zone như thế nào?
Bạn sẽ giải thích khi nào dùng AXFR hoặc IXFR để truyền zone và cần giới hạn quyền truy cập ra sao?
Bạn sẽ ứng dụng TSIG để xác thực giao tiếp giữa các máy chủ DNS trong những hoạt động nào?
Bạn sẽ thiết kế mạng authoritative DNS có nhiều máy chủ để duy trì khả năng phục vụ khi một máy chủ ngừng hoạt động như thế nào?
Bạn sẽ chọn cách triển khai authoritative DNS độc lập với recursive resolver để giảm rủi ro bảo mật và vận hành ra sao?
Bạn sẽ giải thích sự khác nhau giữa bản ghi A và AAAA và cách client lựa chọn địa chỉ để kết nối như thế nào?
Bạn sẽ sử dụng CNAME để đặt bí danh tên miền và phân tích chi phí của một chuỗi CNAME nhiều bước ra sao?
Bạn sẽ phân tích xung đột giữa CNAME tại zone apex và các bản ghi bắt buộc, rồi lựa chọn cách xử lý theo nền tảng DNS ra sao?
Bạn sẽ phân biệt các bản ghi MX và địa chỉ máy chủ nhận thư khi cấu hình dịch vụ email cho một domain ra sao?
Bạn sẽ dùng TXT record trong những tình huống xác minh sở hữu domain hoặc công bố chính sách email nào?
Bạn sẽ giải thích ý nghĩa và giới hạn của bản ghi PTR khi thực hiện tra cứu DNS ngược như thế nào?
Bạn sẽ thiết kế reverse DNS cho một dải địa chỉ IPv4 hoặc IPv6 dưới quyền quản lý của tổ chức ra sao?
Bạn sẽ lựa chọn SRV record cho dịch vụ cần công bố host, cổng và mức ưu tiên truy cập như thế nào?
Bạn sẽ kiểm tra chính sách cấp chứng chỉ TLS thông qua bản ghi CAA trong một kịch bản thực tế ra sao?
Bạn sẽ đánh giá khi nào cần hỗ trợ bản ghi SVCB hoặc HTTPS và những giới hạn tương thích của client như thế nào?
Bạn sẽ giải thích cơ chế wildcard DNS và những tên miền nào vẫn cần bản ghi cụ thể như thế nào?
Bạn sẽ tổ chức bản ghi cho cùng một hostname có nhiều địa chỉ IP để hỗ trợ cân bằng tải đơn giản ra sao?
Bạn sẽ phân tích vì sao DNS round robin không bảo đảm các kết nối được phân phối đều giữa backend như thế nào?
Bạn sẽ quyết định khi nào nên kết hợp DNS với load balancer thay vì đưa toàn bộ địa chỉ backend trực tiếp cho client ra sao?
Bạn sẽ giải thích các giới hạn của DNS khi muốn ngừng gửi lưu lượng đến một backend đã hỏng như thế nào?
Bạn sẽ thiết kế cơ chế trả lời DNS khác nhau theo khu vực địa lý mà vẫn kiểm soát tính chính xác và khả năng chịu lỗi như thế nào?
Bạn sẽ đánh giá tác động của split-horizon DNS khi cùng một tên có địa chỉ khác nhau trong mạng nội bộ và Internet như thế nào?
Bạn sẽ xử lý xung đột tên miền giữa DNS nội bộ và DNS công khai khi doanh nghiệp kết nối hybrid cloud ra sao?
Bạn sẽ lựa chọn cách tổ chức tên miền cho môi trường phát triển, thử nghiệm và sản xuất để tránh định tuyến nhầm như thế nào?
Bạn sẽ xác định các quy tắc đặt tên và quản lý bản ghi nhằm tránh trùng lặp, bản ghi mồ côi và thay đổi ngoài kiểm soát ra sao?
Bạn sẽ giải thích TTL của một bản ghi DNS ảnh hưởng đến hiệu suất, tải máy chủ có thẩm quyền và độ mới dữ liệu như thế nào?
Bạn sẽ lựa chọn TTL cho tên miền dùng chung, API thường xuyên đổi địa chỉ và dịch vụ gần như cố định dựa trên những tiêu chí nào?
Nếu giảm TTL ngay lúc chuyển địa chỉ IP, các resolver đã cache bản ghi trước đó sẽ chịu ảnh hưởng gì và bạn sẽ xử lý ra sao?
Bạn sẽ lập kế hoạch thay đổi địa chỉ IP của dịch vụ có lưu lượng cao để hạn chế gián đoạn do DNS cache ra sao?
Bạn sẽ giải thích positive caching và negative caching giúp recursive resolver giảm số lượng truy vấn như thế nào?
Bạn sẽ xác định TTL của phản hồi NXDOMAIN dựa trên thông tin SOA và cơ chế negative caching ra sao?
Bạn sẽ chẩn đoán tình huống một hostname mới tạo chưa phân giải được do kết quả không tồn tại đã bị cache như thế nào?
Bạn sẽ giải thích vai trò của cache trên hệ điều hành, ứng dụng, trình duyệt và recursive resolver khi thay đổi DNS như thế nào?
Bạn sẽ xác định cache nào cần kiểm tra khi hai máy trong cùng mạng nhận hai kết quả DNS khác nhau ra sao?
Bạn sẽ đánh giá tác động của cơ chế serve-stale khi authoritative DNS tạm không khả dụng và dữ liệu trong cache đã quá TTL ra sao?
Bạn sẽ phân biệt TTL trong DNS record với timeout của một kết nối HTTP hoặc TCP sau khi địa chỉ đã được phân giải như thế nào?
Bạn sẽ thiết kế quy trình rollback thay đổi DNS khi một bản ghi mới gây lỗi nhưng cache còn lưu câu trả lời ra sao?
Bạn sẽ kiểm tra vì sao máy chủ trả TTL đúng nhưng một client vẫn tiếp tục kết nối đến địa chỉ cũ như thế nào?
Bạn sẽ mô tả quá trình gửi truy vấn DNS qua UDP và giải thích ưu điểm của phương thức truyền tải này ra sao?
Bạn sẽ phân biệt những tình huống DNS sử dụng TCP ngay từ đầu với trường hợp cần thử lại qua TCP sau UDP ra sao?
Bạn sẽ giải thích ý nghĩa của cờ TC khi câu trả lời DNS vượt kích thước cho phép và client cần thử lại như thế nào?
Bạn sẽ đánh giá tác động của EDNS(0) đến kích thước gói, khả năng gửi các tùy chọn mở rộng và tương thích mạng như thế nào?
Bạn sẽ phân tích nguy cơ IP fragmentation đối với phản hồi DNS lớn và lựa chọn biện pháp hạn chế ra sao?
Bạn sẽ chẩn đoán trường hợp truy vấn bản ghi nhỏ thành công nhưng câu trả lời DNSSEC lớn lại timeout như thế nào?
Bạn sẽ kiểm tra firewall và network policy khi truy vấn DNS qua UDP hoạt động còn TCP cổng 53 bị chặn ra sao?
Bạn sẽ đánh giá giới hạn kích thước UDP payload ảnh hưởng đến phân mảnh gói và độ ổn định DNS trên các đường truyền ra sao?
Bạn sẽ xác định nguyên nhân độ trễ DNS tăng khi resolver phải hỏi nhiều cấp authoritative server ra sao?
Bạn sẽ kiểm tra các giới hạn timeout, retransmission và số lần thử lại của resolver theo hành vi ứng dụng như thế nào?
Bạn sẽ giải thích DNSSEC bảo vệ tính xác thực và toàn vẹn của phản hồi DNS thông qua những cơ chế nào?
Bạn sẽ phân biệt DNSSEC với mã hóa lưu lượng DNS theo nguy cơ bảo mật mà mỗi cơ chế giải quyết ra sao?
Bạn sẽ mô tả vai trò của DNSKEY, RRSIG và DS trong chuỗi tin cậy DNSSEC từ zone cha đến zone con như thế nào?
Bạn sẽ giải thích cách validating resolver kiểm tra chữ ký DNSSEC và xử lý trường hợp xác thực thất bại ra sao?
Bạn sẽ phân biệt vai trò của KSK và ZSK trong quản lý khóa DNSSEC và lựa chọn quy trình thay khóa như thế nào?
Bạn sẽ lên kế hoạch bật DNSSEC cho zone đang hoạt động mà vẫn bảo đảm DS ở zone cha được cập nhật đúng thời điểm ra sao?
Bạn sẽ phát hiện và khôi phục tình huống DNSSEC bị lỗi sau khi thay khóa hoặc đổi nhà cung cấp DNS như thế nào?
Bạn sẽ giải thích NSEC và NSEC3 hỗ trợ xác thực phản hồi không tồn tại như thế nào?
Bạn sẽ phân tích các cờ DO, AD và CD khi dùng công cụ DNS để kiểm tra xác thực DNSSEC ra sao?
Bạn sẽ đánh giá rủi ro khi tắt kiểm tra DNSSEC chỉ để làm cho một tên miền đang lỗi phân giải trở lại như thế nào?
Bạn sẽ kiểm tra sự khác nhau giữa DNS poisoning, spoofing và việc thay đổi bản ghi hợp lệ tại máy chủ có thẩm quyền ra sao?
Bạn sẽ giải thích vì sao ngẫu nhiên hóa transaction ID và source port giúp giảm nguy cơ cache poisoning như thế nào?
Bạn sẽ thiết kế giới hạn recursion và kiểm soát truy cập để tránh biến DNS resolver thành open resolver ra sao?
Bạn sẽ phân tích cách DNS amplification lợi dụng phản hồi lớn và đề xuất biện pháp giảm thiểu cho authoritative DNS như thế nào?
Bạn sẽ xác định cơ chế DNS rebinding có thể ảnh hưởng đến ứng dụng web và mạng nội bộ như thế nào?
Bạn sẽ thiết kế ghi log truy vấn DNS phục vụ điều tra sự cố mà vẫn bảo vệ thông tin nhạy cảm của người dùng ra sao?
Bạn sẽ phân biệt DNS over TLS, DNS over HTTPS và DNS over QUIC theo kết nối, triển khai và khả năng quản trị như thế nào?
Bạn sẽ lựa chọn DoT hoặc DoH cho client doanh nghiệp dựa trên yêu cầu riêng tư, độ trễ và kiểm soát chính sách ra sao?
Bạn sẽ xác định phạm vi bảo vệ của DNS mã hóa trên kết nối client đến resolver và những đoạn truyền còn lại ra sao?
Bạn sẽ phát hiện tình huống trình duyệt sử dụng DoH riêng khiến chính sách phân giải DNS nội bộ bị bỏ qua ra sao?
Bạn sẽ lựa chọn cách quản lý resolver mã hóa trong mạng có chính sách lọc miền và yêu cầu giám sát truy cập như thế nào?
Bạn sẽ đánh giá các rủi ro về quyền riêng tư khi tập trung toàn bộ truy vấn DNS của người dùng vào một nhà cung cấp resolver như thế nào?
Bạn sẽ thiết kế giải pháp phát hiện truy vấn DNS bất thường mà không dựa hoàn toàn vào việc đọc nội dung của lưu lượng đã mã hóa ra sao?
Bạn sẽ phân tích sự khác biệt giữa DNSSEC, TLS certificate và xác minh HTTPS khi người dùng truy cập một website như thế nào?
Bạn sẽ thiết kế kiến trúc DNS public trên cloud có nhiều zone, tài khoản và nhóm chịu trách nhiệm ra sao?
Bạn sẽ phân biệt public DNS zone và private DNS zone trong cloud khi một tên miền có thể dùng cho cả Internet và mạng riêng như thế nào?
Bạn sẽ tổ chức phân giải DNS giữa mạng doanh nghiệp và cloud VPC/VNet qua forwarding rule hoặc resolver endpoint như thế nào?
Bạn sẽ kiểm tra nguy cơ vòng lặp DNS forwarding giữa on-premises và cloud khi hai phía cùng chuyển tiếp truy vấn cho nhau ra sao?
Bạn sẽ đánh giá ảnh hưởng của alias record hoặc tính năng tương đương do cloud cung cấp tới cấu hình tại zone apex như thế nào?
Bạn sẽ thiết kế health check, failover DNS và TTL cho dịch vụ chạy trên nhiều vùng cloud với yêu cầu phục hồi nhanh ra sao?
Bạn sẽ kiểm chứng một thay đổi DNS qua infrastructure as code trước khi áp dụng lên môi trường production như thế nào?
Bạn sẽ tổ chức quyền thay đổi zone và audit log trên cloud để tránh sửa nhầm bản ghi quan trọng như thế nào?
Bạn sẽ xử lý việc chuyển nhà cung cấp DNS có thay đổi danh sách authoritative name server mà vẫn giữ dịch vụ liên tục ra sao?
Bạn sẽ mô tả cách một Pod trong Kubernetes phân giải tên Service và gọi tới ứng dụng khác trong cluster như thế nào?
Bạn sẽ giải thích vai trò của CoreDNS và cấu hình DNS của Pod trong quá trình phân giải tên miền nội bộ như thế nào?
Bạn sẽ phân biệt tên ngắn, tên theo namespace và fully qualified service name trong Kubernetes như thế nào?
Bạn sẽ sử dụng Service thông thường và headless Service để thay đổi cách DNS trả lời cho client như thế nào?
Bạn sẽ mô tả vai trò của DNS đối với StatefulSet khi ứng dụng cần tìm từng Pod theo tên ổn định như thế nào?
Bạn sẽ kiểm tra bản ghi DNS cho một Service chưa có endpoint sẵn sàng và xác định hành vi mong đợi ra sao?
Bạn sẽ giải thích ý nghĩa của search domains và ndots trong resolv.conf của Pod đối với số lượng truy vấn và độ trễ như thế nào?
Bạn sẽ phân tích nguy cơ truy vấn DNS tăng đột biến khi ứng dụng liên tục gọi hostname bên ngoài từ Kubernetes như thế nào?
Bạn sẽ chọn sử dụng NodeLocal DNSCache trong Kubernetes dựa trên những chỉ số về độ trễ và tải CoreDNS nào?
Bạn sẽ chẩn đoán việc Pod phân giải được tên Service nội bộ nhưng không phân giải được tên miền Internet bằng những bước nào?
Bạn sẽ xử lý trường hợp DNS hoạt động trong một namespace nhưng thất bại ở namespace khác do tên gọi hoặc network policy ra sao?
Bạn sẽ phân biệt sự cố DNS với sự cố Service routing khi lookup trả địa chỉ thành công nhưng kết nối ứng dụng vẫn thất bại như thế nào?
Bạn sẽ dùng dig để truy vấn một loại bản ghi cụ thể và chỉ định máy chủ DNS cần kiểm tra ra sao?
Bạn sẽ đọc kết quả dig gồm status, flags, answer, authority, additional và query time để hình thành giả thuyết sự cố như thế nào?
Bạn sẽ sử dụng dig +trace để tìm vị trí trong chuỗi delegation nơi tên miền bắt đầu thất bại ra sao?
Bạn sẽ so sánh phản hồi trực tiếp từ authoritative DNS và từ recursive resolver để xác định dữ liệu bị cũ ở đâu như thế nào?
Bạn sẽ sử dụng dig +tcp và các tùy chọn kiểm tra DNSSEC để khoanh vùng lỗi do truyền tải hoặc xác thực ra sao?
Bạn sẽ kết hợp nslookup, resolvectl và công cụ hệ điều hành để kiểm tra cấu hình resolver đang được sử dụng như thế nào?
Bạn sẽ dùng packet capture để phân biệt DNS query bị chặn, DNS response bị mất và client retry nhiều lần ra sao?
Bạn sẽ thiết kế phép đo DNS lookup latency theo percentile và phân tách cache hit với cache miss như thế nào?
Bạn sẽ lựa chọn metric QPS, cache hit ratio, SERVFAIL, NXDOMAIN và timeout để giám sát recursive DNS ra sao?
Bạn sẽ phân tích tỷ lệ NXDOMAIN tăng cao là dấu hiệu tên miền cấu hình sai, retry từ ứng dụng hay lưu lượng bất thường như thế nào?
Bạn sẽ thiết kế cảnh báo cho authoritative DNS khi một hoặc nhiều name server không thể phản hồi từ các vị trí kiểm tra khác nhau ra sao?
Bạn sẽ xác định sự khác nhau giữa lỗi DNS, lỗi TCP connect và lỗi TLS khi người dùng báo website không truy cập được như thế nào?
Bạn sẽ kiểm tra trường hợp chỉ người dùng IPv6 gặp lỗi dù bản ghi A và IPv4 vẫn hoạt động bình thường ra sao?
Bạn sẽ điều tra tình huống cập nhật bản ghi A nhưng một số khu vực vẫn trả địa chỉ cũ sau nhiều giờ như thế nào?
Nếu recursive resolver trả SERVFAIL còn truy vấn authoritative trực tiếp thành công, bạn sẽ ưu tiên kiểm tra những nguyên nhân nào?
Nếu thay đổi DNSSEC khiến website không truy cập được với một số resolver, bạn sẽ chẩn đoán chuỗi tin cậy và lập phương án khôi phục ra sao?
Nếu dịch vụ Kubernetes truy cập bằng IP thành công nhưng gọi qua tên Service bị timeout, bạn sẽ khoanh vùng cấu hình DNS và mạng như thế nào?
Nếu hệ thống cloud phải chuyển dịch vụ giữa hai vùng trong thời gian ngắn, bạn sẽ thiết kế DNS failover và kiểm chứng tác động của cache ra sao?
Bạn sẽ đề xuất kiến trúc DNS cho doanh nghiệp có public website, private cloud, Kubernetes và yêu cầu bảo mật, sẵn sàng cao cùng khả năng chẩn đoán sự cố như thế nào?

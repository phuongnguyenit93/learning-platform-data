TLS giải quyết những rủi ro nào khi ứng dụng trao đổi dữ liệu qua mạng không đáng tin cậy?
Bạn sẽ phân biệt tính bí mật, toàn vẹn và xác thực trong một kết nối TLS bằng ví dụ nào?
TLS nằm ở đâu trong luồng giao tiếp giữa HTTP, TCP và IP khi trình duyệt truy cập HTTPS?
Bạn sẽ mô tả vai trò của client, server và các tổ chức cấp chứng chỉ trong một phiên TLS như thế nào?
Bạn sẽ giải thích vì sao mã hóa dữ liệu không tự nó chứng minh được danh tính của máy chủ?
Bạn sẽ so sánh TLS với việc mã hóa dữ liệu tại nơi lưu trữ theo những mục tiêu bảo vệ nào?
Bạn sẽ phân biệt bảo vệ kênh truyền bằng TLS với xác thực người dùng ở tầng ứng dụng như thế nào?
Bạn sẽ nhận diện những giới hạn của TLS khi endpoint hoặc ứng dụng đã bị xâm nhập ra sao?
Bạn sẽ mô tả các loại thông tin mà người quan sát mạng vẫn có thể suy ra dù nội dung kết nối được mã hóa như thế nào?
Bạn sẽ giải thích TLS hoạt động cùng các giao thức ứng dụng ngoài HTTPS trong những tình huống nào?
Bạn sẽ phân biệt mật mã đối xứng và bất đối xứng theo vai trò, chi phí và loại dữ liệu chúng xử lý ra sao?
Bạn sẽ giải thích vì sao TLS thường dùng mật mã bất đối xứng trong bắt tay và mật mã đối xứng cho dữ liệu ứng dụng?
Bạn sẽ mô tả khóa công khai, khóa riêng và điều kiện để không làm lộ khóa riêng trong quá trình sử dụng như thế nào?
Bạn sẽ dùng ví dụ nào để phân biệt mã hóa bằng khóa công khai với chữ ký số?
Bạn sẽ giải thích hàm băm mật mã hỗ trợ kiểm tra tính toàn vẹn trong các cấu trúc của TLS như thế nào?
Bạn sẽ phân biệt chữ ký số và mã xác thực thông điệp khi chứng minh nguồn gốc hoặc tính toàn vẹn dữ liệu ra sao?
Bạn sẽ mô tả vai trò của mã hóa có xác thực như AES-GCM hoặc ChaCha20-Poly1305 trong TLS như thế nào?
Bạn sẽ giải thích vì sao nonce phải được quản lý đúng cách khi dùng thuật toán mã hóa có xác thực?
Bạn sẽ mô tả trao đổi khóa Diffie-Hellman và cách hai bên tạo bí mật chung qua đường truyền không an toàn như thế nào?
Bạn sẽ phân biệt trao đổi khóa tạm thời và sử dụng khóa tĩnh xét theo khả năng bảo vệ các phiên cũ ra sao?
Bạn sẽ giải thích forward secrecy giúp hạn chế hậu quả khi khóa riêng của máy chủ bị lộ sau một phiên kết nối như thế nào?
Bạn sẽ đánh giá vai trò của nguồn sinh số ngẫu nhiên an toàn trong bắt tay và tạo khóa phiên ra sao?
Bạn sẽ phân tích hệ quả của việc sử dụng bộ thuật toán yếu hoặc khóa quá ngắn đối với kết nối TLS như thế nào?
Bạn sẽ mô tả cách các bên thỏa thuận bộ thuật toán và phiên bản giao thức được hỗ trợ như thế nào?
Bạn sẽ phân biệt khái niệm cipher suite giữa TLS 1.2 và TLS 1.3 khi đọc cấu hình kết nối ra sao?
Bạn sẽ xác định yếu tố nào quyết định độ an toàn của phiên TLS ngoài độ dài khóa mã hóa?
Bạn sẽ giải thích chứng chỉ X.509 liên kết khóa công khai với danh tính máy chủ bằng cơ chế nào?
Bạn sẽ tìm các trường thông tin quan trọng nào khi đọc một chứng chỉ X.509?
Bạn sẽ phân biệt Subject, Issuer và Subject Alternative Name trong quá trình xác thực máy chủ như thế nào?
Bạn sẽ đánh giá vai trò của SAN khi chứng chỉ được dùng cho nhiều tên DNS hoặc địa chỉ IP ra sao?
Bạn sẽ mô tả cách client kiểm tra tên miền truy cập có khớp với chứng chỉ máy chủ như thế nào?
Bạn sẽ phân tích trường hợp chứng chỉ hợp lệ về chữ ký nhưng không đúng hostname mà ứng dụng đang kết nối ra sao?
Bạn sẽ giải thích thời hạn Not Before và Not After ảnh hưởng đến quá trình kiểm tra chứng chỉ như thế nào?
Bạn sẽ phân biệt chứng chỉ máy chủ, chứng chỉ intermediate CA và root CA theo nhiệm vụ của từng loại ra sao?
Bạn sẽ mô tả cách một client xây dựng chuỗi chứng chỉ từ máy chủ đến trust anchor như thế nào?
Bạn sẽ xác định điều gì xảy ra khi server không gửi đủ chứng chỉ intermediate cần thiết ra sao?
Trust store ảnh hưởng như thế nào đến quyết định tin cậy chuỗi chứng chỉ của client?
Bạn sẽ phân biệt root CA được tin cậy với một chứng chỉ tự ký chưa được phê duyệt trong môi trường doanh nghiệp ra sao?
Bạn sẽ kiểm tra các trường Key Usage và Extended Key Usage để xác định chứng chỉ có phù hợp mục đích TLS như thế nào?
Bạn sẽ giải thích ý nghĩa của Basic Constraints và giới hạn CA khi xác minh chuỗi chứng chỉ ra sao?
Bạn sẽ đánh giá vai trò của chữ ký CA trong việc phát hiện chứng chỉ bị thay đổi nội dung như thế nào?
Bạn sẽ kiểm tra thuật toán chữ ký và độ dài khóa của chứng chỉ để nhận diện cấu hình yếu ra sao?
Bạn sẽ phân biệt các chứng chỉ dùng wildcard với chứng chỉ liệt kê SAN theo phạm vi tên miền và rủi ro vận hành như thế nào?
Bạn sẽ xác định khi nào chứng chỉ chứa IP cần thiết thay vì chỉ có DNS name ra sao?
Bạn sẽ giải thích yêu cầu chứng minh quyền kiểm soát tên miền khi một CA cấp chứng chỉ máy chủ như thế nào?
Bạn sẽ mô tả cách tạo khóa riêng và CSR, cùng những dữ liệu nào được đưa vào mỗi thành phần ra sao?
Bạn sẽ quản lý việc phát hành, phân phối, gia hạn và thu hồi chứng chỉ trong suốt vòng đời ứng dụng như thế nào?
Bạn sẽ phân biệt thu hồi chứng chỉ bằng CRL và kiểm tra trạng thái qua OCSP về phạm vi và khả năng vận hành ra sao?
Bạn sẽ đánh giá các giới hạn của việc kiểm tra trạng thái thu hồi khi dịch vụ OCSP không phản hồi như thế nào?
Bạn sẽ giải thích OCSP stapling giúp giảm phụ thuộc trực tiếp của client vào máy chủ OCSP ra sao?
Bạn sẽ xác định Certificate Transparency có thể hỗ trợ phát hiện việc cấp chứng chỉ ngoài dự kiến như thế nào?
Bạn sẽ xây dựng kế hoạch gia hạn chứng chỉ tự động để tránh dịch vụ ngừng hoạt động vì hết hạn ra sao?
Bạn sẽ mô tả các giai đoạn chính của một TLS handshake từ khi client kết nối tới lúc trao đổi dữ liệu ứng dụng như thế nào?
Bạn sẽ giải thích thông điệp ClientHello cung cấp những khả năng và tham số quan trọng nào cho server?
Bạn sẽ mô tả các lựa chọn mà server phản hồi để thống nhất phiên bản, khóa trao đổi và thuật toán bảo vệ như thế nào?
Bạn sẽ phân tích vai trò của key share trong quá trình bắt tay TLS 1.3 ra sao?
Bạn sẽ xác định HelloRetryRequest xuất hiện trong trường hợp nào và ảnh hưởng đến độ trễ bắt tay ra sao?
Bạn sẽ phân biệt cách TLS 1.2 và TLS 1.3 xác thực server và thiết lập khóa phiên như thế nào?
Bạn sẽ giải thích vai trò của chuỗi chứng chỉ máy chủ trong handshake TLS như thế nào?
Bạn sẽ mô tả cách CertificateVerify hỗ trợ chứng minh phía gửi sở hữu khóa riêng tương ứng với chứng chỉ ra sao?
Bạn sẽ giải thích thông điệp Finished kiểm chứng tính toàn vẹn của transcript bắt tay như thế nào?
Bạn sẽ nhận diện thời điểm dữ liệu ứng dụng bắt đầu được bảo vệ trong một kết nối TLS 1.3 như thế nào?
Bạn sẽ mô tả cách TLS record layer đóng gói, bảo vệ và truyền dữ liệu sau khi handshake hoàn tất ra sao?
Bạn sẽ đánh giá chi phí bắt tay đầy đủ đối với dịch vụ có nhiều kết nối ngắn như thế nào?
Bạn sẽ giải thích TLS session resumption khác một lần bắt tay đầy đủ về mục đích và yêu cầu bảo mật ra sao?
Bạn sẽ xác định các điều kiện cần để session ticket hoặc cơ chế tái sử dụng phiên hoạt động an toàn như thế nào?
Bạn sẽ phân tích lợi ích độ trễ và rủi ro replay của 0-RTT data trong TLS 1.3 ra sao?
Những loại request nào bạn sẽ loại khỏi 0-RTT để tránh tác động nghiệp vụ do replay, và vì sao?
Bạn sẽ mô tả vai trò của SNI khi nhiều tên miền dùng chung một địa chỉ IP và cổng TLS ra sao?
Bạn sẽ phân biệt SNI với bước kiểm tra hostname trên chứng chỉ trong xác thực máy chủ như thế nào?
Bạn sẽ giải thích ALPN giúp client và server chọn giao thức ứng dụng như HTTP/2 hoặc HTTP/1.1 ra sao?
Bạn sẽ xác định một lỗi cấu hình ALPN có thể ảnh hưởng việc đàm phán giao thức ứng dụng như thế nào?
Bạn sẽ mô tả sự khác nhau giữa TLS chạy trực tiếp trên TCP và QUIC sử dụng TLS 1.3 cho bắt tay như thế nào?
Bạn sẽ giải thích vì sao TLS downgrade cần được phòng tránh khi hai bên có hỗ trợ những phiên bản giao thức khác nhau?
Bạn sẽ kiểm tra bằng cách nào để máy chủ chỉ cho phép những phiên bản TLS đang được chính sách bảo mật phê duyệt?
Bạn sẽ giải thích mTLS bổ sung bước xác thực nào so với TLS chỉ xác thực máy chủ?
Bạn sẽ mô tả quá trình server yêu cầu và xác minh chứng chỉ client trong một phiên mTLS ra sao?
Bạn sẽ phân biệt định danh thiết bị hoặc dịch vụ bằng chứng chỉ client với phân quyền truy cập tài nguyên như thế nào?
Bạn sẽ xây dựng chính sách tin cậy CA khi nhiều dịch vụ nội bộ xác thực nhau bằng mTLS ra sao?
Bạn sẽ lựa chọn khi nào dùng mTLS trong kết nối giữa microservice, proxy hoặc API nội bộ theo tiêu chí nào?
Bạn sẽ xử lý vòng đời chứng chỉ client khi một thiết bị bị thay thế hoặc một service bị thu hồi quyền như thế nào?
Bạn sẽ kiểm chứng chứng chỉ client có đúng mục đích client authentication và danh tính được kỳ vọng ra sao?
Bạn sẽ chẩn đoán trường hợp server yêu cầu chứng chỉ client nhưng client không gửi chứng chỉ phù hợp như thế nào?
Bạn sẽ đánh giá sự khác nhau giữa trust store của client và trust store của server trong mTLS như thế nào?
Bạn sẽ giải thích cách ánh xạ danh tính chứng chỉ mTLS sang tài khoản và chính sách ủy quyền ở tầng ứng dụng ra sao?
Bạn sẽ thiết kế cơ chế xoay vòng chứng chỉ mTLS để các phiên bản dịch vụ cũ và mới có thể chuyển tiếp an toàn như thế nào?
Bạn sẽ cân nhắc cách xử lý mTLS khi lưu lượng đi qua API gateway hoặc service mesh như thế nào?
Bạn sẽ phân tích vị trí kết thúc TLS tại load balancer hoặc reverse proxy và đoạn đường truyền tiếp theo cần được bảo vệ ra sao?
Bạn sẽ lựa chọn giữa TLS passthrough và TLS termination tại proxy theo yêu cầu quan sát, định tuyến và bảo mật như thế nào?
Bạn sẽ bảo đảm các header định danh client chỉ được tin cậy từ proxy đã được xác thực và kiểm soát như thế nào?
Bạn sẽ tổ chức quyền truy cập private key trên máy chủ theo nguyên tắc tối thiểu quyền ra sao?
Bạn sẽ đánh giá khi nào cần dùng HSM hoặc dịch vụ quản lý khóa để tránh xuất khóa riêng ra máy chủ ứng dụng như thế nào?
Bạn sẽ xây dựng quy trình xoay vòng khóa riêng khi phát hiện nghi ngờ rò rỉ hoặc bị sao chép như thế nào?
Bạn sẽ phân biệt lưu trữ certificate chain, private key và trust store trên server để tránh cấu hình sai ra sao?
Bạn sẽ sử dụng các định dạng PEM, DER, PKCS#12 và JKS trong những tình huống tích hợp nào?
Bạn sẽ cấu hình ứng dụng Java truy cập keystore và truststore mà không đưa mật khẩu vào mã nguồn ra sao?
Bạn sẽ kiểm soát việc thay chứng chỉ đang chạy mà không làm gián đoạn các kết nối mới và các kết nối đang hoạt động như thế nào?
Bạn sẽ đánh giá giới hạn phân quyền và bảo vệ private key khi nhiều ứng dụng trên cùng máy chủ chia sẻ tài nguyên như thế nào?
Bạn sẽ thiết kế cảnh báo trước khi chứng chỉ hoặc chuỗi intermediate hết hạn dựa trên thông tin nào?
Bạn sẽ giải thích vì sao việc tắt hostname verification làm suy yếu xác thực máy chủ dù kết nối vẫn mã hóa?
Bạn sẽ phân tích rủi ro của việc vô hiệu hóa kiểm tra chuỗi tin cậy để khắc phục nhanh lỗi HTTPS ra sao?
Bạn sẽ lựa chọn các phiên bản TLS và cipher suite phù hợp chính sách bảo mật và khả năng tương thích client như thế nào?
Bạn sẽ kiểm tra và loại bỏ giao thức hoặc thuật toán yếu khỏi cấu hình máy chủ dựa trên những kết quả nào?
Bạn sẽ xử lý một nhóm client quá cũ không hỗ trợ chính sách TLS mới mà vẫn hạn chế rủi ro như thế nào?
Bạn sẽ nhận diện lỗi liên quan đến chứng chỉ self-signed, CA không tin cậy và chuỗi chứng chỉ thiếu qua thông báo nào?
Bạn sẽ phân biệt lỗi hostname mismatch với lỗi certificate expired khi phân tích thất bại bắt tay như thế nào?
Bạn sẽ xác minh đồng hồ hệ thống có ảnh hưởng đến kết quả kiểm tra hiệu lực chứng chỉ ra sao?
Bạn sẽ dùng OpenSSL để xem Subject, Issuer, SAN, hạn sử dụng và thuật toán của một chứng chỉ như thế nào?
Bạn sẽ dùng OpenSSL s_client để kiểm tra phiên bản TLS, cipher suite và chuỗi chứng chỉ server cung cấp ra sao?
Bạn sẽ kiểm tra SNI trong một phép thử OpenSSL để tránh đọc nhầm chứng chỉ mặc định của máy chủ như thế nào?
Bạn sẽ kiểm tra sự khác nhau giữa việc server gửi chain và việc client có đủ trust anchor khi dùng công cụ xác minh ra sao?
Bạn sẽ kiểm tra những kết quả nào khi OpenSSL s_client thiết lập được kết nối nhưng xác minh chứng chỉ hoặc hostname vẫn thất bại?
Bạn sẽ dùng công cụ OpenSSL để xác minh chứng chỉ và private key khớp nhau mà không công khai khóa riêng ra sao?
Bạn sẽ kiểm tra một máy chủ có chấp nhận TLS 1.2 hoặc TLS 1.3 bằng cách thử kết nối có kiểm soát như thế nào?
Bạn sẽ đọc các thông điệp handshake trong Wireshark để xác định client và server đàm phán những tham số nào?
Bạn sẽ phân biệt dấu hiệu lỗi ở tầng TCP với TLS alert khi phân tích một bản bắt gói như thế nào?
Bạn sẽ phân tích vì sao Wireshark có thể thấy nhiều thông điệp TLS nhưng không tự giải mã được nội dung ứng dụng như thế nào?
Bạn sẽ giải thích điều kiện cần để giải mã lưu lượng TLS của phiên thử nghiệm bằng session keys trong Wireshark ra sao?
Bạn sẽ xác định các dấu hiệu handshake thất bại trước khi server gửi chứng chỉ so với sau bước gửi chứng chỉ như thế nào?
Bạn sẽ dùng timestamp từ packet capture và log máy chủ để phân biệt thời gian chờ mạng với thời gian xử lý handshake ra sao?
Bạn sẽ chẩn đoán lỗi TLS handshake failure xuất hiện sau một lần cập nhật cipher suite hoặc phiên bản giao thức như thế nào?
Bạn sẽ tìm nguyên nhân kết nối TLS chỉ thất bại với một số tên miền nằm sau cùng một reverse proxy như thế nào?
Bạn sẽ xử lý trường hợp trình duyệt kết nối thành công nhưng Java client báo lỗi PKIX path building failed ra sao?
Bạn sẽ phân tích một kết nối HTTPS lúc được lúc không sau khi hệ thống cân bằng tải triển khai chứng chỉ không đồng nhất như thế nào?
Bạn sẽ chẩn đoán sự cố sau khi đổi CA hoặc intermediate certificate mà một số thiết bị vẫn không tin cậy như thế nào?
Bạn sẽ kiểm tra vì sao chỉ client mTLS của một nhóm dịch vụ không bắt tay được sau khi xoay vòng chứng chỉ ra sao?
Bạn sẽ nhận diện khi nào thời gian bắt tay TLS tăng do độ trễ mạng, trao đổi khóa hay kiểm tra chứng chỉ như thế nào?
Bạn sẽ sử dụng log của client, proxy và server để ghép một lần handshake lỗi thành chuỗi sự kiện như thế nào?
Bạn sẽ phân biệt sự cố TLS với lỗi HTTP 401 hoặc 403 xảy ra sau khi kênh bảo mật đã thiết lập như thế nào?
Bạn sẽ thiết kế bài kiểm thử tích hợp xác minh từ chối chứng chỉ hết hạn, sai hostname hoặc không thuộc CA được tin cậy ra sao?
Bạn sẽ xây dựng checklist xác nhận kết nối TLS an toàn trước khi mở dịch vụ ra Internet gồm những tiêu chí nào?
Bạn sẽ thiết kế quy trình giám sát hạn chứng chỉ, tỷ lệ handshake thất bại, phiên bản TLS và thay đổi cấu hình như thế nào?
Bạn sẽ xây dựng phương án ứng phó khi private key của máy chủ bị lộ và đánh giá phạm vi ảnh hưởng ra sao?
Bạn sẽ xác minh sau một đợt nâng cấp TLS rằng client còn tương thích, không xuất hiện downgrade và xác thực vẫn đúng như thế nào?

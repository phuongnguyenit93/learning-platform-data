PKI giải quyết những bài toán tin cậy nào trong hệ thống số, và các vai trò CA, RA, subscriber, relying party phối hợp với nhau ra sao?
Bạn sẽ thiết kế hệ thống phân cấp Root CA và Intermediate CA như thế nào để cân bằng khả năng bảo vệ trust anchor, vận hành và mở rộng cấp phát?
Vì sao Root CA thường được giữ offline, và một quy trình ceremony để khởi tạo hoặc ký Intermediate CA cần kiểm soát những bước nào?
Trong trường hợp nào tổ chức cần cross-sign một CA certificate, và làm thế nào đánh giá tác động của cross-signing đến đường dẫn tin cậy của client?
Trust anchor được phân phối và quản lý trong trust store của máy chủ, thiết bị đầu cuối và workload như thế nào để tránh tin cậy ngoài ý muốn?
Bạn sẽ giải thích quá trình xây dựng và xác minh certification path từ leaf certificate qua các intermediate đến trust anchor như thế nào?
Khi server chỉ gửi leaf certificate mà thiếu intermediate certificate, các loại client có thể phản ứng khác nhau ra sao và bạn sẽ chẩn đoán thế nào?
Basic Constraints và pathLenConstraint ảnh hưởng thế nào đến việc một CA được phép phát hành các CA cấp dưới?
Key Usage và Extended Key Usage giới hạn mục đích sử dụng khóa chứng thư ra sao, và điều gì xảy ra khi profile cấp phát đặt các extension này quá rộng?
Subject Alternative Name đóng vai trò gì trong xác minh danh tính TLS, và vì sao chỉ dựa vào Common Name có thể gây lỗi tương thích hoặc bảo mật?
Bạn sẽ thiết kế SAN cho một dịch vụ có nhiều DNS name, IP address và alias thay đổi theo môi trường như thế nào?
Wildcard certificate phù hợp với những mô hình tên miền nào, và rủi ro mở rộng phạm vi tin cậy xuất hiện khi wildcard bao phủ quá nhiều dịch vụ ra sao?
Name Constraints có thể giới hạn namespace của chứng thư CA cấp dưới như thế nào, và những tình huống tương thích nào cần kiểm thử trước khi áp dụng?
Certificate Policy OID và Policy Constraints có thể được dùng để biểu đạt hoặc giới hạn chính sách cấp phát trong một PKI doanh nghiệp ra sao?
CSR chứa những thông tin nào, và CA kiểm tra bằng cách nào để xác minh người yêu cầu thực sự nắm giữ private key tương ứng?
Khi nhận CSR có SAN hoặc thuộc tính Subject do client tự khai báo, bạn sẽ xác minh quyền sở hữu tên và quyền yêu cầu thuộc tính đó như thế nào?
Bạn sẽ xây dựng certificate profile riêng cho máy chủ TLS, client mTLS, người dùng và thiết bị như thế nào để giảm quyền sử dụng sai mục đích?
Quy trình xác minh domain control, tổ chức và danh tính người yêu cầu khác nhau ra sao giữa các mức xác thực chứng thư công khai?
CA cần bảo đảm tính duy nhất và khả năng truy vết của serial number, issuer identity và thông tin phát hành như thế nào?
Thời hạn Not Before và Not After nên được lựa chọn dựa trên những yếu tố nào, và bạn xử lý clock skew giữa CA, client và server ra sao?
Bạn sẽ đánh giá lựa chọn thuật toán chữ ký, kích thước khóa RSA hoặc đường cong elliptic theo yêu cầu tương thích và vòng đời mật mã như thế nào?
Những tiêu chí nào quyết định việc chuyển từ thuật toán hoặc độ dài khóa cũ sang cấu hình mật mã mạnh hơn mà không làm gián đoạn dịch vụ?
PEM, DER và PKCS#12 khác nhau ở cách biểu diễn và đóng gói chứng thư, private key, certificate chain như thế nào, và nên dùng chúng trong những tình huống nào?
Bạn sẽ bảo vệ file PKCS#12 hoặc bundle chứa private key khi lưu trữ, truyền tải và cấp cho hệ thống triển khai như thế nào?
Khi một trình duyệt hoặc client xác minh chứng thư máy chủ TLS, nó kiểm tra những yếu tố nào ngoài chữ ký số của CA?
SNI ảnh hưởng thế nào đến việc máy chủ chọn certificate khi nhiều hostname cùng dùng một địa chỉ IP, và bạn sẽ chẩn đoán lỗi chọn nhầm chứng thư ra sao?
Trong mTLS, client certificate được gửi và xác minh ở giai đoạn nào của TLS handshake, và server cần kiểm tra thêm điều gì sau khi chain hợp lệ?
Bạn sẽ ánh xạ danh tính từ Subject hoặc SAN của client certificate sang principal hay workload identity như thế nào để tránh chỉ dựa vào chuỗi DN dễ thay đổi?
Khi chứng thư client hợp lệ về mật mã nhưng đã hết quyền truy cập nghiệp vụ, kiến trúc nên tách xác minh certificate khỏi quyết định authorization ra sao?
Thu hồi chứng thư khác gì với để chứng thư hết hạn, và mỗi cơ chế phù hợp với những tình huống vận hành nào?
CRL Distribution Points và Authority Information Access cung cấp thông tin gì cho client khi kiểm tra trạng thái chứng thư?
Bạn sẽ vận hành CRL như thế nào để bảo đảm lịch phát hành, nextUpdate, kích thước danh sách và khả năng phân phối phù hợp với quy mô PKI?
Delta CRL giải quyết vấn đề gì so với CRL đầy đủ, và client cần kết hợp chúng như thế nào để xác định trạng thái thu hồi chính xác?
OCSP responder xử lý yêu cầu kiểm tra trạng thái chứng thư ra sao, và bạn sẽ bảo vệ tính xác thực cùng khả dụng của responder như thế nào?
OCSP stapling cải thiện quyền riêng tư và độ trễ kiểm tra thu hồi TLS như thế nào, và server cần quản lý thời hạn OCSP response ra sao?
Trong trường hợp CRL hoặc OCSP không truy cập được, bạn sẽ lựa chọn soft-fail hay hard-fail theo mức độ nhạy cảm của dịch vụ như thế nào?
Bạn sẽ giảm khoảng thời gian một chứng thư bị thu hồi nhưng vẫn được chấp nhận bởi client bằng những biện pháp kiến trúc và vận hành nào?
Quy trình gia hạn certificate nên bắt đầu trước ngày hết hạn bao lâu, và làm thế nào phối hợp thời gian phát hành, triển khai và kiểm tra sau gia hạn?
ACME tự động hóa việc chứng minh quyền kiểm soát tên miền và cấp phát chứng thư như thế nào, và những thành phần nào cần được bảo vệ trong luồng này?
Bạn sẽ chọn HTTP-01, DNS-01 hay TLS-ALPN-01 cho các mô hình triển khai khác nhau, đặc biệt khi cấp wildcard certificate hoặc dịch vụ không public?
DNS API credential dùng cho DNS-01 challenge có thể tạo ra rủi ro gì, và bạn sẽ giới hạn quyền cùng vòng đời của credential đó như thế nào?
Khi tự động gia hạn certificate cho hàng nghìn endpoint, bạn sẽ tổ chức scheduling, retry, jitter và rate limit ra sao để tránh tạo tải đột biến lên CA?
Bạn sẽ thiết kế certificate inventory tập trung như thế nào để phát hiện chứng thư không rõ chủ sở hữu, không rõ mục đích hoặc được cấp ngoài quy trình chuẩn?
Những chỉ số và cảnh báo nào giúp phát hiện sớm certificate sắp hết hạn, gia hạn thất bại, chain không hợp lệ hoặc trạng thái thu hồi không được cập nhật?
Một certificate đã được gia hạn thành công tại CA nhưng server vẫn phục vụ certificate cũ; bạn sẽ lần theo pipeline triển khai và reload như thế nào?
Bạn sẽ thực hiện thay thế certificate và private key theo cách atomic hoặc overlap như thế nào để tránh downtime khi nhiều instance đang chạy?
Private key cần được tạo và lưu giữ trong HSM hoặc thiết bị bảo vệ khóa ra sao để hạn chế việc khóa bí mật rời khỏi vùng kiểm soát?
HSM khác với dịch vụ quản lý khóa tập trung ở những khía cạnh nào, và tiêu chí nào quyết định nên dùng HSM on-premises hay dịch vụ HSM được quản lý?
Bạn sẽ bảo đảm entropy và tính ngẫu nhiên khi tạo private key cho CA, server và thiết bị đầu cuối như thế nào?
Quy trình backup và recovery private key của CA cần cân bằng khả năng khôi phục với nguy cơ sao chép hoặc lạm dụng khóa ra sao?
Bạn sẽ phân tách nhiệm vụ giữa người yêu cầu, người phê duyệt, RA operator và CA operator như thế nào để giảm nguy cơ cấp chứng thư trái phép?
Khi Intermediate CA cần thay khóa hoặc gia hạn CA certificate, bạn sẽ triển khai rollover để duy trì trust path cho client cũ và mới như thế nào?
Những dấu hiệu nào cho thấy Intermediate CA có thể đã bị lộ private key, và các bước containment, revocation cùng tái cấp phát cần được phối hợp ra sao?
Nếu Root CA private key bị nghi ngờ xâm phạm, bạn sẽ tổ chức ứng phó, thay trust anchor, thông báo relying party và khôi phục hệ thống tin cậy như thế nào?
Bạn sẽ điều tra một trường hợp CA cấp nhầm certificate cho hostname không thuộc quyền kiểm soát của requester như thế nào, từ bằng chứng đến thu hồi và ngăn tái diễn?
Certificate Transparency logs hỗ trợ phát hiện cấp phát chứng thư công khai ngoài dự kiến ra sao, và tổ chức nên giám sát những domain nào?
Bạn sẽ đánh giá lợi ích và rủi ro của certificate pinning so với việc dựa vào hệ thống CA và trust store được quản lý như thế nào?
Trong PKI riêng của doanh nghiệp, quy trình phân phối trust anchor đến máy chủ, container, thiết bị IoT và máy trạm nên được quản trị đồng nhất ra sao?
Khi một tổ chức vận hành nhiều môi trường cloud, on-premises và nhiều tenant, bạn sẽ phân vùng CA, namespace và certificate policy như thế nào?
Bạn sẽ cấp và luân chuyển certificate cho workload chạy trong container hoặc nền tảng điều phối mà không nhúng private key dài hạn vào image như thế nào?
Một dịch vụ mTLS đột ngột từ chối client certificate sau khi thay đổi CA bundle; bạn sẽ kiểm tra chain, trust store, EKU, SAN và cấu hình xác minh theo thứ tự nào?
Khi dùng OpenSSL để kiểm tra một endpoint TLS, bạn sẽ diễn giải thông tin chain, subject, SAN, issuer, validity và verification result như thế nào?
Client báo lỗi certificate verify failed nhưng server cho rằng certificate vẫn hợp lệ; bạn sẽ thu thập và so sánh những bằng chứng nào để xác định nguyên nhân?
Bạn sẽ quản lý việc loại bỏ SHA-1, khóa yếu hoặc certificate profile lỗi thời như thế nào khi vẫn phải hỗ trợ các hệ thống cũ?
Những sự kiện và thuộc tính nào cần được ghi trong audit trail để tái dựng ai yêu cầu, ai phê duyệt, CA nào phát hành, certificate nào bị thu hồi và vì sao?
Bạn sẽ thiết lập chính sách phân loại, lưu giữ và bảo vệ dữ liệu CSR, certificate, serial number cùng thông tin định danh trong hệ thống PKI như thế nào?

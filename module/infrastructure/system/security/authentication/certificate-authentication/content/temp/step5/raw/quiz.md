Câu 1. Chứng chỉ số chủ yếu cung cấp bảo đảm nào cho bên nhận?
A. Mã hóa mọi dữ liệu gửi tới chủ thể mà không cần giao thức khác.
B. Cấp quyền truy cập tài nguyên theo role của người sở hữu.
C. Bảo đảm public key luôn bí mật với các bên chưa xác thực.
D. Gắn danh tính với public key bằng chữ ký issuer.
Đáp án đúng: D

Câu 2. Certificate Authority (CA) có trách nhiệm chính nào trong PKI?
A. Xác minh thông tin theo chính sách và ký chứng chỉ để phát hành.
B. Tạo private key thay cho chủ thể và giữ bản sao dự phòng.
C. Tự động cấp quyền ứng dụng cho mọi subject trong chứng chỉ.
D. Mã hóa toàn bộ phiên giao tiếp thay cho giao thức TLS.
Đáp án đúng: A

Câu 3. Trust anchor trong kiểm tra chứng chỉ thường được xác định như thế nào?
A. Được tin cậy chỉ vì chứng chỉ tự ký có chữ ký hợp lệ.
B. Được chọn theo chứng chỉ có thời hạn dài nhất trong chain.
C. Được suy ra từ tên miền xuất hiện trong trường Subject.
D. Được cấu hình làm điểm tin cậy gốc của bên kiểm tra.
Đáp án đúng: D

Câu 4. Intermediate CA giúp cải thiện mô hình tin cậy ra sao?
A. Ủy quyền phát hành mà không dùng khóa root thường xuyên.
B. Lưu tất cả private key của người dùng để CA khôi phục.
C. Bỏ qua kiểm tra chain khi chứng chỉ được cấp nội bộ.
D. Thay thế trust store của client bằng danh sách hostname.
Đáp án đúng: A

Câu 5. Một chứng chỉ X.509 thường chứa nhóm thông tin nào?
A. Username, password, session cookie và quyền truy cập mặc định.
B. Private key, lịch sử đăng nhập và danh sách thiết bị đã tin cậy.
C. Địa chỉ mạng, firewall rule, port và trạng thái kết nối.
D. Subject, public key, issuer, validity, extensions và signature.
Đáp án đúng: D

Câu 6. Chữ ký số của CA trên chứng chỉ giúp xác minh điều gì?
A. Tính bí mật của dữ liệu ứng dụng gửi sau handshake.
B. Quyền của subject được truy cập mọi dịch vụ trong hệ thống.
C. Xác minh nội dung certificate do issuer ký không bị sửa.
D. Việc private key chưa từng được sao lưu hoặc xuất khỏi thiết bị.
Đáp án đúng: C

Câu 7. Kiểm tra certificate chain hợp lệ cần xem xét những yếu tố nào?
A. Chỉ tên Subject và việc mọi chứng chỉ đều ở định dạng PEM.
B. Chỉ số serial và độ dài khóa công khai của chứng chỉ leaf.
C. Chữ ký chain, thời hạn, trust anchor và constraints.
D. Chỉ hostname do ứng dụng gửi và trạng thái kết nối TCP.
Đáp án đúng: C

Câu 8. Khi xác thực danh tính máy chủ theo tên DNS, trường nào được ưu tiên kiểm tra?
A. Common Name (CN) luôn được ưu tiên hơn SAN trong mọi client.
B. Issuer name vì CA xác nhận danh tính hostname thay client.
C. Serial number vì mỗi hostname được cấp một serial riêng.
D. Subject Alternative Name (SAN) chứa DNS name hoặc IP phù hợp.
Đáp án đúng: D

Câu 9. Nếu tên host yêu cầu không khớp SAN trong chứng chỉ, client nên xử lý thế nào?
A. Chấp nhận nếu chữ ký CA hợp lệ và chứng chỉ còn hạn.
B. Bỏ qua mismatch nếu client đã tin root CA phát hành.
C. Từ chối kết nối vì danh tính endpoint chưa được xác minh.
D. Chỉ cảnh báo rồi tiếp tục gửi dữ liệu nhạy cảm.
Đáp án đúng: C

Câu 10. Trường `notBefore` và `notAfter` trong chứng chỉ thể hiện điều gì?
A. Thời gian còn lại của phiên TLS sau lần bắt tay đầu tiên.
B. Thời gian CA phải giữ bản sao private key của chủ thể.
C. Khoảng thời gian chứng chỉ được phép có hiệu lực.
D. Khoảng thời gian CRL được phép lưu trong cache trình duyệt.
Đáp án đúng: C

Câu 11. Trong TLS server authentication, client cần xác minh điều gì?
A. Chain tin cậy, hostname khớp và proof of private-key possession.
B. Chỉ kiểm tra server gửi certificate trước khi trao đổi dữ liệu.
C. Chỉ kiểm tra hostname xuất hiện trong URL có cùng tên Subject.
D. Xác minh server có quyền truy cập database mà client yêu cầu.
Đáp án đúng: A

Câu 12. Trong xác thực client bằng chứng chỉ, client cần chứng minh điều gì?
A. Biết private key của CA đã ký chứng chỉ client.
B. Chứng minh sở hữu private key tương ứng với certificate.
C. Gửi private key cho server để server so sánh với certificate.
D. Chỉ gửi Subject name qua HTTP header sau khi TLS hoàn tất.
Đáp án đúng: B

Câu 13. Mutual TLS (mTLS) khác TLS chỉ xác thực server ở điểm nào?
A. Chỉ client xác thực server nhưng dùng hai certificate server.
B. Cả client và server đều xác thực chứng chỉ của phía đối diện.
C. Hai bên trao đổi certificate nhưng không kiểm tra chữ ký chain.
D. Hai bên dùng chung một private key để mã hóa toàn bộ traffic.
Đáp án đúng: B

Câu 14. Private key được dùng thế nào để chứng minh chủ thể sở hữu chứng chỉ?
A. Gửi private key qua mạng trong trường dữ liệu đã mã hóa.
B. Gửi CSR mới trong mọi request để server kiểm tra chủ thể.
C. Dùng public key để giải mã challenge rồi trả lại private key.
D. Ký bằng private key để chứng minh sở hữu mà không tiết lộ khóa.
Đáp án đúng: D

Câu 15. Chứng chỉ client hợp lệ có tự động cấp quyền truy cập mọi tài nguyên không?
A. Có; certificate hợp lệ đồng nghĩa chủ thể là administrator.
B. Certificate nhận diện; authorization vẫn do policy quyết định.
C. Có; CA đã ký chứng chỉ nên đã duyệt mọi quyền nghiệp vụ.
D. Không; chứng chỉ chỉ dùng để mã hóa, không nhận diện chủ thể.
Đáp án đúng: B

Câu 16. Extended Key Usage (EKU) giới hạn điều gì?
A. Mục đích như clientAuth hoặc serverAuth.
B. Độ dài khóa tối thiểu và thuật toán ký mà CA phải dùng.
C. Danh sách hostname và IP được phép xuất hiện trong SAN.
D. Thời hạn tối đa mà chứng chỉ được phép tồn tại.
Đáp án đúng: A

Câu 17. Key Usage trong X.509 biểu thị điều gì?
A. Vai trò nghiệp vụ của người dùng trong từng ứng dụng.
B. Danh sách CA mà client đã cấu hình làm trust anchor.
C. Tên dịch vụ mà subject được phép gọi sau TLS handshake.
D. Các phép toán được phép theo public key certificate.
Đáp án đúng: D

Câu 18. Certificate Signing Request (CSR) thường chứa dữ liệu nào?
A. Private key để CA lưu trữ và dùng ký thay chủ thể.
B. Toàn bộ trust store của máy sẽ sử dụng chứng chỉ mới.
C. Danh sách password và token của các ứng dụng dùng certificate.
D. Public key, subject và chữ ký chứng minh sở hữu.
Đáp án đúng: D

Câu 19. Trước khi cấp chứng chỉ, CA nên xác minh điều gì theo chính sách?
A. Xác minh danh tính hoặc quyền kiểm soát theo policy CA.
B. Chỉ độ dài public key và định dạng file CSR được gửi lên.
C. Chỉ khả năng kết nối tới OCSP responder của người yêu cầu.
D. Chỉ việc subject đã có một chứng chỉ cũ còn trong trust store.
Đáp án đúng: A

Câu 20. Certificate Revocation List (CRL) cung cấp thông tin gì?
A. Danh sách chứng chỉ sắp hết hạn nhưng vẫn được xem là hợp lệ.
B. Danh sách public key được phép dùng để ký certificate mới.
C. Danh sách serial của chứng chỉ đã bị thu hồi do CA công bố.
D. Danh sách hostname đã được CA xác minh trong từng lần truy cập.
Đáp án đúng: C

Câu 21. OCSP được dùng để kiểm tra trạng thái chứng chỉ như thế nào?
A. Gửi truy vấn trạng thái cho chứng chỉ cụ thể tới OCSP responder.
B. Tải toàn bộ certificate chain mới mỗi khi client mở kết nối.
C. Kiểm tra chữ ký TLS của server bằng cách gửi private key tới CA.
D. Đọc danh sách role và permission gắn với subject của chứng chỉ.
Đáp án đúng: A

Câu 22. OCSP stapling giúp cải thiện quy trình kiểm tra thu hồi ra sao?
A. Client bỏ qua trạng thái thu hồi vì server đã gửi certificate.
B. CA gửi private key của responder cùng certificate chain cho client.
C. Server gửi kèm OCSP response đã ký để client kiểm tra trạng thái.
D. Server tự ký thông báo trạng thái mà không cần responder.
Đáp án đúng: C

Câu 23. Khi chính sách yêu cầu kiểm tra thu hồi nghiêm ngặt nhưng OCSP responder tạm thời không truy cập được, xử lý nào phù hợp?
A. Chấp nhận vĩnh viễn chứng chỉ vì lỗi responder nằm ngoài hệ thống client.
B. Dùng cache còn hiệu lực; từ chối nếu status đã stale.
C. Bỏ qua mọi kiểm tra thu hồi cho tới khi responder hoạt động lại.
D. Chỉ kiểm tra `notAfter` vì chứng chỉ chưa hết hạn không thể bị thu hồi.
Đáp án đúng: B

Câu 24. Vì sao chứng chỉ thời hạn ngắn vẫn cần quy trình quản lý vòng đời?
A. Chứng chỉ ngắn hạn tự gia hạn mà không cần CA hoặc chủ thể tham gia.
B. Không cần giám sát vì thời hạn ngắn loại bỏ mọi lỗi vận hành.
C. Vẫn phải theo dõi cấp mới, phân phối, thu hồi và thời điểm hết hạn.
D. Private key có thể dùng vô thời hạn sau khi certificate hết hạn.
Đáp án đúng: C

Câu 25. Khi nào nên bắt đầu renewal để tránh gián đoạn do chứng chỉ hết hạn?
A. Đúng thời điểm `notAfter` để tránh có hai chứng chỉ cùng hiệu lực.
B. Trước `notAfter` đủ sớm để phát hành, phân phối và chuyển đổi có kiểm soát.
C. Sau khi client bắt đầu báo lỗi để biết chắc chứng chỉ cũ đã hết hạn.
D. Chỉ khi CA root sắp hết hạn để đồng bộ toàn bộ PKI.
Đáp án đúng: B

Câu 26. Certificate rotation an toàn thường cần phối hợp những bước nào?
A. Thu hồi certificate hiện tại trước rồi mới bắt đầu tạo khóa thay thế.
B. Dùng lại private key cũ và chỉ đổi serial number trong certificate.
C. Cấp khóa mới, chuyển đổi có kiểm chứng rồi thu hồi khóa cũ.
D. Xóa trust anchor của mọi client rồi cài certificate mới cùng lúc.
Đáp án đúng: C

Câu 27. Khi private key của chứng chỉ bị nghi lộ, hành động ưu tiên nào phù hợp?
A. Chỉ gia hạn certificate hiện tại bằng cùng private key bị nghi lộ.
B. Thu hồi chứng chỉ, thay khóa, phát hành lại và điều tra phạm vi ảnh hưởng.
C. Xóa certificate khỏi máy chủ nhưng tiếp tục dùng private key cũ.
D. Đổi Subject name và giữ nguyên khóa để không gián đoạn kết nối.
Đáp án đúng: B

Câu 28. Biện pháp nào giúp bảo vệ private key có giá trị cao?
A. Đặt private key trong thư mục dùng chung để dễ sao lưu và triển khai.
B. Lưu trong HSM hoặc kho khóa bảo vệ, giới hạn truy cập và ghi audit.
C. Gửi khóa qua email nội bộ rồi xóa bản gửi sau khi cài đặt.
D. Nhúng khóa vào tài liệu cấu hình được phân phối cho mọi client.
Đáp án đúng: B

Câu 29. Vì sao root CA thường được giữ offline và dùng intermediate CA để cấp phát?
A. Giúp root CA trực tiếp ký mọi chứng chỉ mà không cần kiểm soát.
B. Cho phép intermediate bỏ qua path validation khi phát hành nội bộ.
C. Giữ root offline; dùng intermediate cho cấp phát thường ngày.
D. Loại bỏ nhu cầu thu hồi certificate của các chủ thể cuối.
Đáp án đúng: C

Câu 30. Quản trị trust store nên tuân theo nguyên tắc nào?
A. Thêm mọi CA có certificate hợp lệ để tránh lỗi tương thích.
B. Giữ mọi root CA đã từng cài để các chứng chỉ cũ luôn hoạt động.
C. Tin CA theo thứ tự alphabet để các client xử lý giống nhau.
D. Tối thiểu hóa CA tin cậy và rà soát trust anchor.
Đáp án đúng: D

Câu 31. PEM và DER khác nhau chủ yếu ở đặc điểm nào?
A. PEM chứa private key còn DER chỉ chứa public key.
B. PEM dùng cho root CA còn DER chỉ dùng cho client certificate.
C. PEM có chữ ký số còn DER không hỗ trợ chữ ký certificate.
D. PEM là dạng text armor Base64; DER là mã hóa nhị phân.
Đáp án đúng: D

Câu 32. PKCS#12 hoặc PFX thường được dùng để lưu trữ gì?
A. Danh sách thu hồi chứng chỉ dạng text được CA công bố định kỳ.
B. Container certificate/chain và private key được bảo vệ.
C. Chỉ chứa public key đã mã hóa và không thể có private key.
D. Gói chứa trust anchor mặc định của mọi hệ điều hành.
Đáp án đúng: B

Câu 33. Khi cấu hình server gửi certificate chain, nên gửi những chứng chỉ nào?
A. Chỉ gửi root certificate vì client có thể tự suy ra leaf.
B. Certificate leaf của server và các intermediate cần để xây dựng chain.
C. Gửi private key cùng leaf certificate để client xác minh nhanh.
D. Chỉ gửi intermediate certificate và bỏ leaf để giảm kích thước.
Đáp án đúng: B

Câu 34. Wildcard certificate có rủi ro phạm vi tin cậy nào?
A. Wildcard chỉ khớp một hostname cố định nên không có rủi ro thêm.
B. Wildcard làm mất hiệu lực SAN và khiến client bỏ kiểm tra hostname.
C. Wildcard tự cấp quyền truy cập cho mọi dịch vụ trong domain.
D. Một wildcard có thể mở rộng quyền xác thực cho nhiều hostname cùng phạm vi.
Đáp án đúng: D

Câu 35. Certificate pinning cần kế hoạch vận hành nào để tránh tự khóa client?
A. Có backup pin và kế hoạch rotation trước khi đổi.
B. Chỉ lưu một pin cố định để tránh client tin nhầm chứng chỉ mới.
C. Tắt xác minh chain khi pin cũ không còn khớp certificate.
D. Cập nhật pin sau khi client đã từ chối mọi kết nối mới.
Đáp án đúng: A

Câu 36. Khi gateway xác thực client certificate rồi chuyển request tới backend, backend nên tin danh tính được chuyển tiếp theo điều kiện nào?
A. Backend tin mọi identity header vì gateway đã kiểm tra client một lần.
B. Backend xác thực gateway và chỉ tin assertion qua kênh được bảo vệ.
C. Backend bỏ mTLS vì header do gateway gửi luôn không thể bị giả mạo.
D. Backend suy ra principal từ source IP mà không xác minh gateway.
Đáp án đúng: B

Câu 37. Khi nào endpoint nên yêu cầu client certificate bắt buộc?
A. Khi endpoint hoặc vùng mạng yêu cầu xác minh danh tính client ở tầng TLS.
B. Bắt buộc trên mọi endpoint công khai để thay thế authorization.
C. Chỉ khi client không gửi HTTP User-Agent trong request.
D. Chỉ khi server certificate dùng thuật toán chữ ký bất đối xứng.
Đáp án đúng: A

Câu 38. Certificate Transparency log hỗ trợ phát hiện vấn đề nào?
A. Mọi chứng chỉ đã hết hạn trong trust store nội bộ.
B. Private key của mọi client đã bị giải mã bởi CA công khai.
C. Phát hiện certificate phát hành sai hoặc ngoài dự kiến.
D. Các request TLS có hostname không khớp SAN trong runtime.
Đáp án đúng: C

Câu 39. Giám sát hệ thống certificate authentication nên theo dõi tín hiệu nào?
A. Theo dõi expiry, validation failures, revocation và renewal.
B. Chỉ số lượng certificate file trên đĩa và dung lượng trust store.
C. Chỉ số lần TLS handshake thành công, không cần log lỗi.
D. Chỉ số lượng client đã cài certificate mà không cần thời hạn.
Đáp án đúng: A

Câu 40. Khi client báo lỗi certificate validation, thứ tự kiểm tra ban đầu nào hữu ích?
A. Kiểm tra đồng hồ, SAN, chain/trust store, EKU và trạng thái thu hồi.
B. Đổi certificate ngay, sau đó kiểm tra hostname nếu lỗi vẫn còn.
C. Tắt xác minh chain và thử kết nối bằng HTTP không mã hóa.
D. Tạo CSR mới trước khi xác định chứng chỉ hiện tại sai ở đâu.
Đáp án đúng: A

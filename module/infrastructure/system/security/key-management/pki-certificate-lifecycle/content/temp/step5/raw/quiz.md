1. PKI giải quyết nhu cầu nào trong hệ thống số?
A. Mã hóa toàn bộ dữ liệu mà không cần quản lý danh tính.
B. Đồng bộ mật khẩu người dùng giữa các ứng dụng.
C. Thay thế kiểm soát truy cập bằng một kho khóa tập trung.
D. Thiết lập niềm tin giữa danh tính và public key qua chứng thư.
Đáp án đúng: D

2. Vì sao Root CA thường được giữ offline và dùng Intermediate CA để cấp phát?
A. Giảm phơi lộ trust anchor và giới hạn phạm vi khóa phát hành.
B. Giúp mọi leaf certificate tự động được client tin cậy.
C. Loại bỏ nhu cầu xác minh danh tính trước khi cấp chứng thư.
D. Cho phép bỏ qua kiểm tra chain khi xác minh TLS.
Đáp án đúng: A

3. Điều gì khiến một Root CA trở thành trust anchor của relying party?
A. Public key được cấu hình làm trust anchor trong trust store.
B. Chứng thư tự ký có chữ ký hợp lệ về toán học.
C. Root CA có Subject trùng với hostname của máy chủ.
D. Root certificate có thời hạn dài hơn leaf certificate.
Đáp án đúng: A

4. Khi xác minh certification path, relying party cần kiểm tra điều gì?
A. Chỉ kiểm tra chữ ký số của issuer trên leaf certificate.
B. Chữ ký, validity, constraints, policy và trust anchor.
C. Chỉ kiểm tra Subject của intermediate và Root CA.
D. Chỉ xác nhận server gửi đủ certificate trong handshake.
Đáp án đúng: B

5. CA certificate có Basic Constraints CA:TRUE và pathLenConstraint bằng 0 có ý nghĩa gì?
A. Chỉ được ký một leaf certificate duy nhất.
B. Không được phép ký bất kỳ chứng thư nào khác.
C. Được ký leaf, không được ký thêm CA trung gian bên dưới.
D. Có thể tạo CA con không giới hạn nếu Key Usage cho phép.
Đáp án đúng: C

6. Cách áp dụng Key Usage và Extended Key Usage nào phù hợp?
A. Dùng cùng mọi extension cho CA, TLS server và client.
B. Chỉ kiểm tra EKU, bỏ qua Key Usage khi xác minh.
C. Coi EKU là thông tin mô tả, không ảnh hưởng mục đích sử dụng.
D. Giới hạn keyCertSign cho CA; EKU theo vai trò server hoặc client.
Đáp án đúng: D

7. TLS client nên xác minh hostname của server dựa trên trường nào?
A. Common Name trong Subject của leaf certificate.
B. Tên Subject của Root CA trong trust chain.
C. So hostname với DNS hoặc IP SAN trong leaf certificate.
D. Tên hiển thị của chứng thư trong giao diện quản trị CA.
Đáp án đúng: C

8. Chữ ký trên CSR chủ yếu chứng minh điều gì?
A. CA đã xác minh tổ chức sở hữu mọi SAN được yêu cầu.
B. Requester được phép yêu cầu mọi thuộc tính trong Subject.
C. Requester nắm private key khớp với public key trong CSR.
D. Chứng thư được cấp sẽ được mọi trust store chấp nhận.
Đáp án đúng: C

9. Yêu cầu nào áp dụng cho serial number của certificate do một CA phát hành?
A. Serial duy nhất theo issuer để tra cứu và thu hồi chính xác.
B. Giống nhau cho mọi certificate cùng một certificate profile.
C. Trùng với serial number của public key trong CSR.
D. Dùng lại khi chứng thư cũ đã hết hạn hoặc bị thu hồi.
Đáp án đúng: A

10. Certificate profile cho TLS server nên xác định những yếu tố nào?
A. SAN, validity, algorithm và KU/EKU theo vai trò server.
B. Chỉ Subject CN và một thời hạn cố định cho mọi hệ thống.
C. Mọi EKU cùng một SAN wildcard để dễ tái sử dụng.
D. Private key của server và trust store của toàn tổ chức.
Đáp án đúng: A

11. Relying party đánh giá NotBefore và NotAfter như thế nào?
A. Chỉ kiểm tra NotAfter vì NotBefore không ảnh hưởng xác minh.
B. Dùng ngày phát hành trong audit log thay cho validity fields.
C. So thời gian hiện tại với khoảng hiệu lực và clock skew.
D. Chấp nhận chứng thư nếu CA vẫn đang hoạt động.
Đáp án đúng: C

12. Một TLS client xác minh server certificate đúng cách cần làm gì?
A. Xác minh chain, hostname, validity và EKU.
B. Chỉ kiểm tra chữ ký của CA trên leaf certificate.
C. Chỉ so sánh Common Name với tên máy chủ.
D. Chấp nhận mọi certificate nếu kết nối đã dùng TLS.
Đáp án đúng: A

13. Server thường cần gửi những certificate nào trong TLS handshake?
A. Gửi leaf và intermediate cần thiết; trust anchor thường có ở client.
B. Chỉ Root CA vì client có thể suy ra leaf từ public key.
C. Toàn bộ certificate trong trust store của server.
D. Chỉ leaf certificate và luôn dựa vào AIA để tải intermediate.
Đáp án đúng: A

14. Trong mTLS, chain hợp lệ của client certificate chứng minh điều gì?
A. Client tự động có quyền admin trên mọi API của server.
B. Client được miễn mọi bước authorization ở tầng ứng dụng.
C. Client có thể truy cập mọi tenant do cùng CA phát hành.
D. Chain xác minh danh tính; authorization vẫn được kiểm tra riêng.
Đáp án đúng: D

15. CRL được dùng để kiểm tra trạng thái certificate như thế nào?
A. Tra theo hostname trong danh sách các chứng thư đã hết hạn.
B. Tra issuer và serial trong danh sách chứng thư bị thu hồi.
C. Kiểm tra chữ ký CSR để xác định requester còn làm việc hay không.
D. So public key với trust anchor để phát hiện khóa yếu.
Đáp án đúng: B

16. Khi xác minh OCSP response, client cần kiểm tra những gì?
A. Xác minh chữ ký, responder, trạng thái và freshness của response.
B. Chỉ cần HTTP 200 từ responder, không cần chữ ký.
C. Chỉ trường thisUpdate, bỏ qua chữ ký và nextUpdate.
D. Chỉ serial number mà không cần kiểm tra issuer.
Đáp án đúng: A

17. OCSP stapling cải thiện việc kiểm tra thu hồi TLS ra sao?
A. Server tự ký leaf certificate thay cho CA.
B. Client không cần xác minh chain khi nhận stapled response.
C. Server đính kèm OCSP response đã ký trong TLS handshake.
D. OCSP responder được thay thế bằng một CRL cục bộ không hạn.
Đáp án đúng: C

18. Khi CRL hoặc OCSP không truy cập được, nên chọn soft-fail hay hard-fail thế nào?
A. Luôn soft-fail để không ảnh hưởng khả dụng dịch vụ.
B. Luôn hard-fail cho mọi hệ thống kể cả môi trường thử nghiệm.
C. Chọn theo rủi ro dịch vụ và chính sách tin cậy.
D. Bỏ kiểm tra thu hồi nếu certificate còn trong thời hạn.
Đáp án đúng: C

19. Muốn cấp wildcard certificate qua ACME, challenge nào phù hợp?
A. HTTP-01 với file challenge đặt ở mọi subdomain.
B. TLS-ALPN-01 với wildcard SAN trong mọi triển khai.
C. Email challenge gửi tới địa chỉ quản trị domain.
D. DNS-01 để chứng minh quyền kiểm soát DNS zone.
Đáp án đúng: D

20. PEM, DER và PKCS#12 khác nhau như thế nào?
A. PEM là định dạng khóa đối xứng; DER là giao thức enrollment.
B. PEM là Base64 text; DER là binary; PKCS#12 đóng gói credential.
C. DER chỉ chứa private key; PKCS#12 chỉ chứa certificate công khai.
D. PEM và DER là giao thức cấp phát; PKCS#12 là trust store online.
Đáp án đúng: B

21. Tự động hóa gia hạn certificate cho nhiều endpoint cần thiết kế gì?
A. Gia hạn tất cả cùng thời điểm để dễ theo dõi trạng thái.
B. Chỉ retry liên tục khi CA trả lỗi để không bỏ lỡ thời hạn.
C. Lập lịch sớm, retry có jitter và kiểm tra sau triển khai.
D. Coi phản hồi cấp certificate thành công là đủ, không cần kiểm tra server.
Đáp án đúng: C

22. HSM hỗ trợ bảo vệ private key CA hoặc TLS như thế nào?
A. Lưu private key dạng rõ để ứng dụng có thể sao chép nhanh.
B. Giữ private key trong HSM và ký theo policy được cấp.
C. Tự động xác minh mọi hostname mà không cần relying party.
D. Thay thế quy trình phân quyền và kiểm toán thao tác khóa.
Đáp án đúng: B

23. Root CA ceremony nên có kiểm soát nào?
A. Một quản trị viên giữ toàn bộ key và tự phê duyệt mọi thao tác.
B. Tạo key trên máy kết nối Internet để đồng bộ dễ dàng.
C. Lưu seed và private key trong cùng thư mục chia sẻ nội bộ.
D. Phân tách nhiệm vụ, dual control/quorum và biên bản kiểm toán.
Đáp án đúng: D

24. Khi rollover Root CA, cách chuyển đổi nào giảm gián đoạn?
A. Xóa trust anchor cũ trước khi phân phối root mới.
B. Phân phối root mới, kiểm thử path và duy trì overlap.
C. Chỉ thay root certificate trên CA, không cập nhật relying party.
D. Dùng private key mới để ký lại mọi certificate cũ mà không thông báo.
Đáp án đúng: B

25. Name Constraints trong CA certificate có tác dụng gì?
A. Giới hạn namespace mà CA cấp dưới được phép cấp chứng thư.
B. Bắt buộc mọi leaf certificate dùng cùng một public key.
C. Thay thế SAN bằng Common Name trong mọi TLS client.
D. Xác định số ngày tối đa một certificate được phép tồn tại.
Đáp án đúng: A

26. Certificate Transparency log giúp tổ chức làm gì?
A. Giám sát CT log để phát hiện certificate lạ cho domain.
B. Thu hồi tự động mọi certificate không được tạo bởi private CA.
C. Thay thế trust store của trình duyệt bằng danh sách domain.
D. Mã hóa certificate trước khi CA gửi cho relying party.
Đáp án đúng: A

27. Rủi ro vận hành chính của certificate pinning là gì?
A. Pinning tự động làm lộ private key khi CA đổi thuật toán.
B. Pinning khiến certificate không còn cần kiểm tra thời hạn.
C. Đổi key hoặc CA có thể khiến client cũ từ chối kết nối.
D. Pinning buộc mọi dịch vụ dùng chung một leaf certificate.
Đáp án đúng: C

28. Cross-signed intermediate có thể gây khác biệt nào giữa các TLS client?
A. Luôn làm mọi certificate leaf mất hiệu lực ngay khi phát hành.
B. Client có thể chọn path khác nhau tới trust anchor khác nhau.
C. Khiến public key trong leaf certificate tự động thay đổi.
D. Loại bỏ yêu cầu kiểm tra validity của CA certificate.
Đáp án đúng: B

29. Vì sao nên có certificate profile riêng cho server, client và code signing?
A. Mỗi loại certificate cần một Root CA công khai riêng.
B. KU, EKU, SAN, validity và policy cần khớp mục đích sử dụng.
C. Mọi loại certificate nên dùng cùng SAN wildcard để đơn giản hóa.
D. Profile riêng giúp bỏ qua việc kiểm tra chain của certificate.
Đáp án đúng: B

30. Một client không xây dựng được chain vì server thiếu intermediate. Cách khắc phục ưu tiên là gì?
A. Tắt xác minh certificate trên client trong thời gian chờ.
B. Thay leaf certificate bằng self-signed certificate.
C. Cấu hình server gửi intermediate còn thiếu trong chain.
D. Gia hạn leaf certificate mà không thay đổi chain.
Đáp án đúng: C

31. Intermediate CA bị nghi compromise private key. Hành động nào cần ưu tiên?
A. Chỉ gia hạn các leaf certificate do CA đó phát hành.
B. Tiếp tục phát hành trong khi chờ điều tra hoàn tất.
C. Xóa log issuance để ngăn attacker truy cập lịch sử.
D. Dừng cấp phát, cô lập CA và revoke chứng thư CA.
Đáp án đúng: D

32. Triển khai certificate và private key mới lên nhiều server nên làm gì?
A. Ghi đè từng file riêng lẻ trước khi kiểm tra key pair.
B. Cập nhật certificate trước, để key cũ cho tới khi có lỗi.
C. Reload từng node bất kỳ và bỏ qua kiểm tra handshake.
D. Kiểm tra key/chain, swap nguyên tử rồi xác minh reload.
Đáp án đúng: D

33. Khi chọn thuật toán và kích thước khóa cho PKI mới, nên dựa vào điều gì?
A. Chọn thuật toán cũ nhất để mọi thiết bị đều tương thích.
B. Theo chuẩn hiện hành, policy và khả năng tương thích client.
C. Dùng một thuật toán duy nhất mà không cần xét mục đích certificate.
D. Chọn theo tốc độ ký nhanh nhất bất kể mức an toàn.
Đáp án đúng: B

34. Server xác minh client certificate trong mTLS nên ánh xạ danh tính thế nào?
A. Coi mọi certificate cùng CA là cùng một principal.
B. Dùng Subject CN làm role quản trị mà không cần kiểm tra khác.
C. Chỉ dựa vào địa chỉ IP vì TLS đã xác minh certificate.
D. Map SAN/URI sang workload identity; authorize riêng.
Đáp án đúng: D

35. Certificate inventory và monitoring nên theo dõi những thông tin nào?
A. Chỉ đếm số certificate đã phát hành trong mỗi tháng.
B. Owner, issuer, SAN, expiry, renewal và validation.
C. Chỉ theo dõi certificate có thời hạn dưới bảy ngày.
D. Chỉ cảnh báo khi toàn bộ CA không còn phản hồi.
Đáp án đúng: B

36. Audit trail PKI cần lưu những thông tin nào để truy vết issuance và revocation?
A. Chỉ tên CA và tổng số certificate được phát hành.
B. Chỉ thời hạn certificate và địa chỉ máy chủ triển khai.
C. Chỉ lưu CSR để có thể tái tạo private key sau này.
D. Requester, approver, issuer, serial, profile, time và revoke reason.
Đáp án đúng: D

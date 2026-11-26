Câu 1. Trong ứng dụng Spring muốn đọc secret từ HashiCorp Vault, thành phần nào là API thao tác chính?
A. Dùng `VaultTemplate` để đọc và ghi secret qua Vault API.
B. Dùng `VaultEndpoint` để gọi trực tiếp REST API KV của Vault.
C. Dùng `VaultResponse` làm client gửi request đến Vault.
D. Dùng `SecretLeaseContainer` như KV client đồng bộ.
Đáp án đúng: A

Câu 2. Khi tạo `VaultTemplate`, cặp thành phần nào xác định nơi kết nối và cách lấy token?
A. `VaultResponse` cùng một `SecretLeaseContainer` để login.
B. `VaultEndpoint` cùng một `ClientAuthentication` phù hợp.
C. `VaultMappingContext` cùng một `PasswordEncoder` để login.
D. `VaultToken` cùng một `VaultTransitOperations` để chọn host.
Đáp án đúng: B

Câu 3. Với `VaultTemplate.read("secret/team/app")`, kết quả kiểu nào cung cấp phần dữ liệu phản hồi?
A. Đọc dữ liệu secret từ `VaultHealth.getStatus()` phản hồi.
B. Đọc dữ liệu secret từ `VaultEndpoint.getHost()` phản hồi.
C. Đọc dữ liệu secret từ `VaultToken.getToken()` phản hồi.
D. Đọc dữ liệu secret từ `VaultResponse.getData()`.
Đáp án đúng: D

Câu 4. Để truy cập KV version 2 tại mount `secret` mà không tự ghép `/data/`, API nào phù hợp?
A. Gọi `opsForKeyValue("secret", KeyValueBackend.KV_1)`.
B. Gọi `opsForPki("secret")` thay cho thao tác với KV.
C. Gọi `opsForTransit("secret")` thay cho thao tác với KV.
D. Gọi `opsForKeyValue("secret", KeyValueBackend.KV_2)`.
Đáp án đúng: D

Câu 5. Khác biệt chính giữa Vault KV version 1 và version 2 là gì?
A. KV v2 hỗ trợ version của secret và metadata phiên bản.
B. KV v2 phát lease động cho mỗi lần đọc giống DB engine.
C. KV v1 hỗ trợ lịch sử phiên bản, KV v2 ghi đè không lưu.
D. KV v1 tự cấp certificate mới mỗi khi client đọc secret.
Đáp án đúng: A

Câu 6. Khi một secret KV v2 bị soft delete, điều nào thường đúng?
A. Dữ liệu bị xóa vật lý như thao tác destroy version.
B. Vault tự tạo token mới khi application đọc secret.
C. Dùng undelete để khôi phục version chưa bị destroy của KV v2.
D. KV v2 chuyển secret sang Transit engine để giải mã.
Đáp án đúng: C

Câu 7. Muốn tránh ghi đè KV v2 khi version đã thay đổi, cần dùng cơ chế nào?
A. Dùng CAS kèm version đã đọc để tránh lost update trong KV v2.
B. Dùng PKI role để ghi secret kèm số serial certificate.
C. Dùng cùng token đăng nhập cho mọi update cùng một key.
D. Thay CSRF token cho mỗi lần ghi để khóa version.
Đáp án đúng: A

Câu 8. Policy cho phép đọc giá trị KV v2 ở mount `secret` nên nhắm path nào?
A. Path API `secret/metadata/app` với capability `read` giá trị.
B. Path API `secret/destroy/app` với capability `read` dữ liệu.
C. Path API `auth/token/lookup-self` với capability `read` KV.
D. Path API `secret/data/app` với capability `read`.
Đáp án đúng: D

Câu 9. App cần liệt kê key trong KV v2 nhưng không đọc giá trị; quyền nào sát nhu cầu nhất?
A. Capability `read` trên path `secret/data/...` của mọi nhóm.
B. Capability `update` trên path `secret/destroy/...` tương ứng.
C. Capability `sudo` trên path `sys/mounts` dành cho app.
D. Capability `list` trên path `secret/metadata/...` tương ứng.
Đáp án đúng: D

Câu 10. Khi viết Vault policy cho workload chỉ đọc secret của một service, nên giới hạn thế nào?
A. Cấp quyền đọc mọi KV mount để phòng thay đổi đường dẫn.
B. Cấp capability `sudo` cho toàn bộ mount chứa ứng dụng.
C. Cấp capability `read` tại đúng path secret mà workload cần.
D. Cấp root token cho workload để tránh lỗi thiếu quyền runtime.
Đáp án đúng: C

Câu 11. Trong Vault AppRole authentication, workload thường dùng thông tin nào để đăng nhập?
A. Dùng username và password từ JPA repository của ứng dụng.
B. Dùng authorization code và redirect URI của trình duyệt.
C. Dùng `role_id` và `secret_id` được phân phối theo kênh an toàn.
D. Dùng serial PKI và version của KV secret cần đọc.
Đáp án đúng: C

Câu 12. Một pod Kubernetes muốn xác thực với Vault mà không nhúng root token, hướng nào phù hợp?
A. Dùng CSRF token của session Spring MVC để nhận Vault token.
B. Dùng role ID của PKI mà không cần Kubernetes authentication.
C. Dùng JWT access token do frontend người dùng tự gửi tới pod.
D. Dùng Kubernetes auth với JWT ServiceAccount được pod cung cấp.
Đáp án đúng: D

Câu 13. Với Spring Vault, abstraction `ClientAuthentication` giải quyết nhiệm vụ nào?
A. Phát sự kiện tái tạo credential khi JVM bắt đầu shutdown.
B. Giải mã giá trị KV trong Java trước khi gửi HTTP request.
C. Gắn principal vào phương thức `@PreAuthorize` của ứng dụng.
D. Thực hiện Vault login để lấy token dùng xác thực API.
Đáp án đúng: D

Câu 14. Tại sao không nên gắn một Vault root token tĩnh trong source code production?
A. Token root quá quyền và dễ lộ khi nhúng vào mã nguồn.
B. Root token tự bị thu hồi khi ứng dụng mở kết nối HTTPS.
C. Root token bắt Vault đổi mount path ở mỗi lần khởi động.
D. Root token ngăn Spring Vault dùng lại HTTP connection.
Đáp án đúng: A

Câu 15. Thành phần nào của Spring Vault phù hợp quản lý vòng đời token cần làm mới theo thời hạn?
A. `VaultHealthIndicator` tự cấp lại root token cho ứng dụng.
B. `VaultEndpoint` tự đổi token theo số lần request được gửi.
C. `VaultResponse` tự gia hạn token mỗi khi `getData()` được gọi.
D. Dùng `LifecycleAwareSessionManager` để quản lý và renew token.
Đáp án đúng: D

Câu 16. Một Vault token đã hết TTL và không được gia hạn; request được xác thực bằng token đó ra sao?
A. Spring tự chuyển token hết hạn thành token root dài hạn.
B. Vault tự gia hạn token khi application gửi cùng token cũ.
C. Vault sẽ từ chối truy cập cho đến khi có token hợp lệ.
D. KV engine tiếp tục trả secret vì token đã từng được cấp.
Đáp án đúng: C

Câu 17. Trong Vault, lease của dynamic database credential có vai trò gì?
A. Quy định danh sách origin được CORS cho phép từ ứng dụng.
B. Lease xác định TTL và khả năng renew/revoke của credential.
C. Quy định thời gian tối đa của JWT access token OIDC.
D. Quy định số version được giữ lại trong KV v2 metadata.
Đáp án đúng: B

Câu 18. Spring Vault cung cấp thành phần nào theo dõi lease của secret động và phát sự kiện vòng đời?
A. `VaultResponse` giữ thread nền theo dõi mọi KV version.
B. Dùng `SecretLeaseContainer` để theo dõi và renew lease.
C. `VaultMappingContext` chạy lịch renew mọi certificate.
D. `VaultToken` phát sự kiện khi session có thay đổi credential.
Đáp án đúng: B

Câu 19. Khi database credentials do Vault cấp được rotate, application dùng connection pool nên làm gì?
A. Ghi credential mới vào source code để các pod dùng chung.
B. Tắt kiểm tra tài khoản tại database vì Vault đã xác thực.
C. Giữ các kết nối mới dùng password cũ để tránh gián đoạn.
D. Cập nhật credential và thay các kết nối cũ trong pool.
Đáp án đúng: D

Câu 20. Sự khác biệt quan trọng giữa secret KV thông thường và dynamic DB credential là gì?
A. Dynamic credential giữ một giá trị cố định đến khi deploy lại.
B. Dynamic credential có lease và có thể bị revoke khi hết hạn.
C. KV secret tự cấp lease mới cho mỗi lần đọc bằng `getData()`.
D. KV secret phát role database kèm lease trong mọi lần đọc.
Đáp án đúng: B

Câu 21. Muốn dùng Vault Transit mã hóa dữ liệu nhưng để khóa ở Vault, Spring Vault dùng API nào?
A. Dùng `VaultTemplate.opsForSys()` để lấy private key.
B. Dùng `VaultTemplate.opsForKeyValue(...)` kết hợp KV CAS.
C. Dùng `VaultTemplate.opsForTransit()` để gọi Transit API.
D. Dùng `VaultTemplate.opsForPki(...)` để ký ciphertext.
Đáp án đúng: C

Câu 22. Khi gọi Transit encrypt, ứng dụng nhận lại loại dữ liệu nào để lưu trữ?
A. Nhận Secret ID của AppRole để thay cho ciphertext.
B. Vault trả ciphertext, giữ key mã hóa trong engine.
C. Nhận private key Transit để mã hóa tiếp ở ứng dụng.
D. Nhận PKI certificate dùng như bản mã của dữ liệu.
Đáp án đúng: B

Câu 23. Vault policy muốn cho ứng dụng mã hóa bằng Transit key `pay-key` nhưng không giải mã, quyền nào phù hợp?
A. Cấp `read` trên path `transit/decrypt/pay-key` của Vault.
B. Cấp `update` cho `transit/encrypt/pay-key` trong policy.
C. Cấp `delete` trên path `transit/keys/pay-key` của Vault.
D. Cấp `sudo` trên path `auth/token/create` của Vault.
Đáp án đúng: B

Câu 24. Trong Vault Transit, thao tác `rewrap` có ích khi nào?
A. Rewrap ciphertext sang key version mới ngay phía Vault.
B. Phát lại chứng chỉ PKI sắp hết hạn bằng private key CA.
C. Gia hạn thời gian sống của Vault token bằng ciphertext cũ.
D. Đổi KV v1 thành KV v2 kèm lịch sử version của secret.
Đáp án đúng: A

Câu 25. Sau khi rotate Transit key, vì sao có thể vẫn giải mã ciphertext tạo bởi key version cũ?
A. Vault gửi bản sao master key trong HTTP header của ciphertext.
B. Vault giữ các phiên bản khóa để giải mã ciphertext cũ.
C. Ciphertext cũ tự được thay bằng plaintext khi đọc KV data.
D. Client tự tải bản private key cũ từ JWKS endpoint của Vault.
Đáp án đúng: B

Câu 26. Trong PKI secrets engine của Vault, role phát hành certificate thường kiểm soát điều gì?
A. Tên các KV version và cấu hình CAS của mỗi secret.
B. PKI role giới hạn domain, TTL và điều kiện cấp cert.
C. Quyền truy cập `/transit/decrypt` cho từng consumer group.
D. Danh sách HTTP response header của Spring Security.
Đáp án đúng: B

Câu 27. Khi ứng dụng nhận chứng chỉ mới qua Vault PKI, yếu tố nào vẫn cần quản lý tại ứng dụng?
A. Tải lại leaf cert và private key vào TLS context của app.
B. Chuyển PKI certificate thành token AppRole để đăng nhập.
C. Cập nhật mọi KV secret để đổi mount path sang PKI.
D. Bỏ xác minh hostname TLS vì certificate được Vault ký.
Đáp án đúng: A

Câu 28. Muốn thu hồi một leaf certificate đã phát hành bằng Vault PKI, thao tác nào phù hợp?
A. Dùng PKI revoke theo serial number của certificate.
B. Gọi KV v2 destroy với version của certificate trong Transit.
C. Gọi token lookup với role ID của PKI để xóa certificate.
D. Gọi Transit rewrap với ciphertext của private key ứng dụng.
Đáp án đúng: A

Câu 29. Kết nối Spring Vault với server qua HTTPS cần cấu hình gì để tránh lỗi giả mạo máy chủ?
A. Cho phép TLS hostname mismatch nếu ứng dụng dùng AppRole auth.
B. Chỉ kiểm tra token response, không xác minh server certificate.
C. Xác minh chứng nhận TLS từ CA tin cậy và hostname đúng.
D. Tắt kiểm tra chứng chỉ rồi dựa vào chính sách KV để bảo vệ.
Đáp án đúng: C

Câu 30. Khi Vault API trả 403 vì thiếu capability, hướng xử lý an toàn là gì?
A. Giảm xác minh TLS để Vault chấp nhận quyền truy cập của app.
B. Đổi yêu cầu sang root token và thử lại trước khi báo lỗi.
C. Rà Vault policy và path; tránh retry mù hoặc tự nâng quyền.
D. Xem mọi 403 là lỗi mạng thoáng qua rồi retry với cùng policy.
Đáp án đúng: C

Câu 31. Khi giám sát secret access trong production, nên ưu tiên tín hiệu nào?
A. Quan sát audit, lease, renewal errors mà không log secrets.
B. Lưu Secret ID của AppRole trong trace tag cho mọi request.
C. Ghi cả Vault token và giá trị secret để đối chiếu incident.
D. Log private key của Transit để xác nhận chính sách truy cập.
Đáp án đúng: A

Câu 32. Muốn integration test Spring Vault với KV và chính sách thật mà không dùng Vault production, cách nào phù hợp?
A. Chạy service với secret hardcode rồi bỏ qua integration Vault.
B. Test POJO rồi suy ra cấu hình Vault policy đã chính xác.
C. Chạy Vault cô lập bằng Testcontainers rồi test KV và ACL.
D. Mock VaultTemplate rồi khẳng định backend auth hoạt động.
Đáp án đúng: C

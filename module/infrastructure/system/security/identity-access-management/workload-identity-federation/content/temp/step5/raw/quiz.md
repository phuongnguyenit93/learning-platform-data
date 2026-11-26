1. Vì sao workload identity federation thường an toàn hơn việc lưu access key dài hạn trong pipeline CI/CD?
A. Credential được tạo từ tên repository nên không cần xác minh chữ ký.
B. Workload đổi assertion ngắn hạn lấy credential có thời hạn.
C. Federation tự động cấp quyền quản trị để tránh lỗi triển khai.
D. Workload không cần chứng minh nguồn gốc vì issuer đã được cấu hình.
Đáp án đúng: B

2. Một luồng OIDC federation điển hình nên diễn ra theo thứ tự nào?
A. Workload lấy assertion; STS xác minh rồi cấp credential tạm thời.
B. STS cấp credential trước, sau đó workload gửi assertion để ghi audit.
C. Workload tự ký JWT, cloud provider chỉ kiểm tra thời hạn của JWT.
D. Issuer cấp cloud credential trực tiếp mà không có bước kiểm tra trust.
Đáp án đúng: A

3. Claim iss trong OIDC assertion biểu thị điều gì?
A. Địa chỉ mạng của runner đang thực hiện pipeline.
B. Định danh issuer đã phát hành assertion.
C. Định danh tài nguyên cloud mà workload muốn truy cập.
D. Tên role nội bộ mà STS sẽ gán cho workload.
Đáp án đúng: B

4. Assertion có chữ ký hợp lệ nhưng aud không chứa audience được trust cấu hình. Relying party nên làm gì?
A. Từ chối assertion vì token không dành cho relying party này.
B. Tự thêm audience mong muốn vào token trước khi đổi credential.
C. Chỉ kiểm tra sub vì audience không ảnh hưởng token exchange.
D. Chấp nhận assertion vì chữ ký hợp lệ chứng minh issuer tin cậy.
Đáp án đúng: A

5. Claim sub nên được ràng buộc như thế nào trong trust policy?
A. Tên hiển thị của nhóm phát triển tạo ra pipeline.
B. Tin issuer và tổ chức phát hành mà không ràng buộc workload cụ thể.
C. Mã tài khoản cloud đích nhận credential từ STS.
D. Ràng buộc sub với repository, ref, workflow hoặc service account.
Đáp án đúng: D

6. Một trust policy chỉ kiểm tra iss mà bỏ qua sub và aud tạo ra rủi ro nào?
A. Credential tạm thời không thể được thu hồi khi job kết thúc.
B. Assertion hợp lệ sẽ tự hết hạn trước khi STS đọc được.
C. Workload khác cùng issuer vẫn có thể được chấp nhận.
D. Issuer không thể xoay khóa ký sau khi trust được tạo.
Đáp án đúng: C

7. Bộ kiểm tra assertion nào phù hợp trước khi token exchange?
A. Chỉ kiểm tra exp vì TLS đã xác minh nguồn gửi request.
B. Xác minh chữ ký và các claim iss, aud, sub, exp, nbf.
C. Chỉ so khớp sub và bỏ qua issuer cùng chữ ký.
D. Chỉ giải mã payload rồi tin các claim do token tự khai báo.
Đáp án đúng: B

8. Verifier nên xử lý header alg=none hoặc thuật toán ngoài chính sách ra sao?
A. Từ chối thuật toán không nằm trong allowlist đã cấu hình.
B. Chấp nhận thuật toán nếu token có kid và chữ ký không rỗng.
C. Chọn thuật toán theo giá trị do workload gửi trong request.
D. Thử lần lượt mọi thuật toán cho đến khi một phép kiểm tra thành công.
Đáp án đúng: A

9. JWT có kid chưa có trong cache JWKS. Verifier nên làm gì?
A. Bỏ xác minh chữ ký trong một khoảng thời gian để pipeline tiếp tục.
B. Dùng khóa bất kỳ trong cache vì issuer đã được xác minh trước đó.
C. Lấy khóa từ URL do JWT header tự cung cấp mà không kiểm tra nguồn.
D. Tải JWKS từ issuer tin cậy, tìm đúng kid và từ chối nếu thiếu.
Đáp án đúng: D

10. Issuer đang xoay signing key trong khi token cũ vẫn còn hiệu lực. Cách triển khai nào giảm gián đoạn?
A. Giữ khóa cũ vô thời hạn và ngừng cập nhật JWKS cache khi issuer xoay khóa.
B. Sửa kid của token cũ mà không tạo lại chữ ký assertion.
C. Xóa khóa cũ ngay khi tạo khóa mới và từ chối mọi token cũ.
D. Công bố khóa mới, giữ khóa cũ trong giai đoạn chuyển tiếp.
Đáp án đúng: D

11. OIDC discovery document và JWKS nên được tin cậy theo cách nào?
A. Tin mọi discovery URL do assertion hoặc workload cung cấp.
B. Chỉ xác minh TLS của JWKS nhưng bỏ kiểm tra issuer trong metadata.
C. Dùng issuer đã cấu hình để tải discovery metadata và xác minh JWKS.
D. Tải JWKS từ endpoint gần nhất để giảm độ trễ mà không cần kiểm tra issuer.
Đáp án đúng: C

12. Một issuer phát hành aud dưới dạng danh sách nhiều giá trị. Cách xác minh nào đúng?
A. Chỉ kiểm tra audience đầu tiên vì issuer luôn đặt giá trị ưu tiên ở đầu.
B. Kiểm tra audience yêu cầu có trong tập aud được phép.
C. So sánh cả danh sách với một chuỗi duy nhất bằng phép chứa một phần.
D. Chấp nhận token nếu danh sách audience không rỗng.
Đáp án đúng: B

13. Pipeline chỉ được phép nhận production role từ nhánh release đã bảo vệ. Trust policy nên kiểm tra gì?
A. Mọi ref bắt đầu bằng tiền tố refs/heads để dễ bảo trì.
B. Chỉ issuer và thời hạn token để tránh phụ thuộc cấu trúc CI.
C. Tên repository bất kỳ trong tổ chức, kể cả project chưa được bảo vệ.
D. Giới hạn repository, ref, workflow và environment được duyệt.
Đáp án đúng: D

14. Một pull request đến từ fork chạy test trong CI. Kiểm soát nào ngăn nó nhận production credential?
A. Cho phép job nhận token nhưng giảm thời hạn token xuống vài phút.
B. Cho phép token nếu pull request có ít nhất một reviewer.
C. Từ chối quyền OIDC triển khai cho job từ fork không tin cậy.
D. Chấp nhận token của fork nếu repository gốc là repository được tin cậy.
Đáp án đúng: C

15. Reusable workflow được sửa để chạy mã từ nhánh khác nhưng trust chỉ kiểm tra repository. Rủi ro chính là gì?
A. Credential tạm thời được cấp sẽ mất chữ ký khi workflow thay đổi.
B. OIDC issuer sẽ tự phát hiện mọi thay đổi workflow và từ chối token.
C. Audience của token sẽ tự đổi khi workflow file thay đổi.
D. Workflow ngoài allowlist có thể dùng identity của repository.
Đáp án đúng: D

16. Pipeline có job build, test và deploy với mức tin cậy khác nhau. Cách cấp identity nào phù hợp?
A. Cấp quyền deploy cho mọi job nhưng giới hạn số lần gọi STS.
B. Tách subject hoặc trust conditions và quyền riêng theo từng job.
C. Dùng một token dài hạn cho toàn pipeline để tránh đổi token giữa job.
D. Dùng một identity chung rồi dựa vào tên job trong log để phân quyền.
Đáp án đúng: B

17. Self-hosted runner được tái sử dụng giữa repository có mức tin cậy khác nhau. Kiểm soát nào quan trọng?
A. Chỉ xóa log console sau job vì token không thể lưu trên đĩa.
B. Chia sẻ runner nhưng dùng cùng một service account cho mọi repository.
C. Tách runner theo miền tin cậy và làm sạch workspace sau job.
D. Giữ workspace để tăng tốc build và dựa vào file permission mặc định.
Đáp án đúng: C

18. Job CI bật debug và in toàn bộ OIDC assertion ra log. Hành động nào phù hợp?
A. Không ghi assertion vào log; bảo vệ log và xử lý token đã lộ.
B. Tăng retention log để có đủ bằng chứng nếu token bị lạm dụng.
C. Giữ log vì assertion chỉ có thể dùng bởi runner đã tạo ra nó.
D. Chuyển token sang Base64 để người đọc log không nhận ra nội dung.
Đáp án đúng: A

19. Kubernetes Pod chỉ cần gọi cloud API và không cần Kubernetes API. Cấu hình nào giảm bề mặt tấn công?
A. Dùng service-account token dài hạn trong Secret để tránh rotation.
B. Cấp quyền cluster-admin rồi dựa vào network policy để giới hạn API.
C. Mount token mặc định cho mọi Pod để workload có thể tự chọn audience.
D. Tắt tự động mount service-account token nếu Pod không cần token đó.
Đáp án đúng: D

20. Projected service-account token cần dùng để đổi cloud credential. Audience nên được cấu hình thế nào?
A. Dùng audience mặc định của Kubernetes API cho mọi dịch vụ.
B. Dùng audience riêng cho cloud relying party và từng môi trường.
C. Để workload tự chọn audience bất kỳ trong mỗi lần token request.
D. Dùng cùng audience cho staging, production và Kubernetes API.
Đáp án đúng: B

21. Hai namespace có service account cùng tên. Subject mapping nào phân biệt đúng hai workload?
A. Dùng node name làm subject chung cho mọi Pod trên node.
B. Chỉ so khớp tên service account vì tên phải duy nhất trong cluster.
C. Ràng buộc cả namespace và service account trong subject.
D. So khớp image name của Pod thay cho danh tính service account.
Đáp án đúng: C

22. Người dùng có thể tạo Pod trong namespace chứa service account đặc quyền. Rủi ro nào cần kiểm soát?
A. Pod mới không thể nhận projected token nếu người tạo không phải cluster admin.
B. Kubernetes luôn yêu cầu quyền impersonate trước khi Pod dùng service account.
C. Họ có thể tạo Pod tham chiếu service account đó và thừa hưởng identity của nó.
D. Họ tự động có quyền đọc mọi Secret trong tất cả namespace.
Đáp án đúng: C

23. RBAC cho phép nhiều người tạo serviceaccounts/token cho service account đặc quyền. Cách nào phù hợp?
A. Giới hạn quyền tạo token cho service account cần thiết.
B. Giữ quyền rộng vì token được phát hành luôn có thời hạn ngắn.
C. Chỉ đổi tên service account để tránh người dùng tìm thấy nó.
D. Cấp quyền get Secret thay cho create token để giảm số API verb.
Đáp án đúng: A

24. Kubernetes xoay projected token file khi token sắp hết hạn. Ứng dụng nên làm gì?
A. Tắt rotation để tránh workload phải xử lý file token thay đổi.
B. Giữ token cũ trong memory đến khi tiến trình được khởi động lại.
C. Đọc lại token file mới trước các lần exchange tiếp theo.
D. Sao chép token sang biến môi trường một lần khi container khởi động.
Đáp án đúng: C

25. Pod không được cấp cloud identity vẫn lấy được credential qua node metadata endpoint. Biện pháp nào phù hợp?
A. Chỉ đổi tên node role vì metadata endpoint không thể bị gọi từ Pod.
B. Chặn Pod không tin cậy truy cập metadata endpoint của node.
C. Ẩn endpoint trong DNS nhưng giữ đường truy cập IP trực tiếp.
D. Cho phép mọi Pod truy cập metadata nhưng giảm quyền node role.
Đáp án đúng: B

26. STS nhận assertion đã được xác minh và ánh xạ vào cloud role. Quyền nên được quyết định thế nào?
A. Ánh xạ role theo trust condition và policy quyền tối thiểu.
B. Theo tên role mà workload tự gửi trong request exchange.
C. Theo mọi claim có trong token mà không cần allowlist mapping.
D. Theo quyền rộng nhất của issuer để tránh từ chối workload hợp lệ.
Đáp án đúng: A

27. Một workload chỉ cần đọc một bucket cụ thể. Cách cấp quyền nào thể hiện least privilege?
A. Dùng role chung cho mọi workload trong namespace và dựa vào tên Pod.
B. Cấp role quản trị storage để workload không gặp lỗi quyền.
C. Ánh xạ workload vào role chỉ đọc bucket đó với điều kiện cần thiết.
D. Cấp quyền đọc mọi bucket trong account rồi giám sát log.
Đáp án đúng: C

28. Session policy được hỗ trợ khi cấp temporary credential. Mục đích phù hợp là gì?
A. Thay thế việc xác minh issuer và audience trước token exchange.
B. Dùng session policy để thu hẹp quyền của phiên được cấp.
C. Kéo dài thời hạn credential mà không cần cập nhật trust policy.
D. Mở rộng role tạm thời để workload tự chọn tài nguyên khi chạy.
Đáp án đúng: B

29. Một workload có thể assume role A rồi dùng role A để assume role B. Cần kiểm soát điều gì?
A. Cho phép chaining tự do vì mỗi credential đều có thời hạn ngắn.
B. Chỉ kiểm tra issuer ở lần assume đầu và tin các role tiếp theo.
C. Bỏ audit các lần assume tiếp theo để tránh ghi log trùng.
D. Kiểm soát role chaining theo trust và quyền của từng role.
Đáp án đúng: D

30. Job deploy kéo dài hơn thời hạn cloud credential tạm thời. Thiết kế nào phù hợp?
A. Lấy credential mới qua federation khi cần, không lưu khóa tĩnh.
B. Gia hạn credential cũ bằng cách sửa expiration trong memory.
C. Lưu static key dự phòng trong workspace để job không bị gián đoạn.
D. Đặt credential không hết hạn cho các job có thời lượng khó dự đoán.
Đáp án đúng: A

31. STS hoặc issuer tạm thời không khả dụng. Hành vi fallback nào an toàn?
A. Bỏ xác minh assertion nếu JWKS endpoint timeout trong vài giây.
B. Dùng credential của node bất kể workload có được cấp quyền hay không.
C. Retry có giới hạn; fail closed nếu issuer hoặc STS không xác minh.
D. Âm thầm dùng static key đã lưu trong biến môi trường runner.
Đáp án đúng: C

32. Một workload bị compromise nhưng temporary credential còn hiệu lực. Hành động nào giảm tác động?
A. Siết trust, thu hẹp role và revoke phiên nếu provider hỗ trợ.
B. Chỉ xóa assertion ở runner vì credential đã phát hành tự hết hiệu lực ngay.
C. Giữ trust policy và chờ credential hết hạn dù có thể truy cập tài nguyên nhạy cảm.
D. Xoay tên role nhưng giữ nguyên policy và quan hệ trust cũ.
Đáp án đúng: A

33. Signing key của issuer bị nghi lộ. Việc ứng phó nào phù hợp?
A. Xóa cache JWKS ở một verifier và coi như mọi relying party đã an toàn.
B. Thu hồi khóa bị lộ, xoay khóa và rà soát token đã phát hành.
C. Giữ khóa trong JWKS cho đến khi mọi token hết hạn tự nhiên.
D. Chỉ đổi audience vì thay đổi audience sẽ vô hiệu hóa mọi chữ ký cũ.
Đáp án đúng: B

34. Một lần federation cần được điều tra về sau. Audit log nên ghi gì?
A. Chỉ tên role và thời gian vì các claim khác không giúp truy vết.
B. Payload ứng dụng đầy đủ cùng access token để liên kết hoạt động.
C. Toàn bộ JWT assertion và secret để có thể phát lại request.
D. Ghi issuer, subject, audience, role và trạng thái exchange.
Đáp án đúng: D

35. Một workload bắt đầu yêu cầu nhiều role lạ và truy cập account ngoài lịch triển khai. Kiểm soát nào phát hiện tốt?
A. Chỉ cảnh báo khi số lần đăng nhập của người dùng vượt ngưỡng.
B. Theo dõi CPU của runner vì assume role bất thường luôn làm CPU tăng.
C. Tắt audit event thành công để tập trung vào các lần exchange lỗi.
D. Phân tích audit theo workload, role, tài nguyên và baseline.
Đáp án đúng: D

36. Bộ negative test nào kiểm chứng trust policy hiệu quả?
A. Từ chối token sai issuer, audience, subject, chữ ký hoặc hạn.
B. Chỉ thử sai audience trong khi dùng cùng subject và khóa hợp lệ.
C. Chỉ kiểm thử một token hợp lệ và xác nhận exchange thành công.
D. Chỉ kiểm tra token hết hạn vì các claim khác do issuer đảm bảo.
Đáp án đúng: A

37. Khi JWKS endpoint tạm thời lỗi, verifier nên xử lý thế nào?
A. Tự tạo khóa xác minh thay thế dựa trên kid trong JWT header.
B. Bỏ qua kiểm tra chữ ký cho đến khi endpoint hoạt động trở lại.
C. Chấp nhận mọi token mới vì issuer đã từng được xác minh thành công.
D. Dùng khóa cache còn mới; hết freshness thì fail closed.
Đáp án đúng: D

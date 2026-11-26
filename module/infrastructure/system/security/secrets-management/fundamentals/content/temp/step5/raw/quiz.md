1. Trong ứng dụng, dấu hiệu nào giúp phân biệt secret với cấu hình thông thường?
A. Secret là mọi giá trị cấu hình được lưu trong file có phần mở rộng riêng.
B. Secret chỉ là dữ liệu được mã hóa; token và password không thuộc nhóm này.
C. Secret có thể cấp quyền truy cập hoặc ký; cần bảo vệ và kiểm soát chặt.
D. Secret là thông tin không thay đổi trong suốt vòng đời của ứng dụng.
Đáp án đúng: C

2. Khi tạo API key hoặc mật khẩu ngẫu nhiên cho service, nguồn nào nên được dùng?
A. Timestamp kết hợp tên service và mã môi trường để tránh trùng lặp.
B. UUID thông thường được tạo từ thời gian và địa chỉ mạng của máy.
C. Hàm băm tên ứng dụng cùng chuỗi cố định để tạo giá trị dễ tái lập.
D. Bộ sinh số ngẫu nhiên mật mã với entropy phù hợp mục đích sử dụng.
Đáp án đúng: D

3. Secret manager tập trung giảm rủi ro nào so với secret nằm rải rác trong file cấu hình?
A. Loại bỏ hoàn toàn nhu cầu xác thực workload khi ứng dụng khởi động.
B. Quản lý truy cập, version, audit và rotation theo chính sách thống nhất.
C. Đảm bảo secret không bao giờ xuất hiện trong bộ nhớ của tiến trình.
D. Tự động ngăn mọi credential bị lộ từ mã nguồn hoặc log ứng dụng.
Đáp án đúng: B

4. Trong envelope encryption, cặp khóa nào thường được dùng để bảo vệ một secret?
A. KEK mã hóa từng byte secret; DEK xác thực người gọi secret manager.
B. DEK ký audit log; KEK tạo nonce mới cho mỗi lần đọc secret.
C. DEK lưu danh tính workload; KEK quyết định quyền truy cập secret.
D. DEK mã hóa secret; KEK wrap DEK để bảo vệ khóa.
Đáp án đúng: D

5. Vì sao API key thường tách public identifier khỏi secret value?
A. Identifier giúp tra cứu key; secret value dùng chứng minh quyền sở hữu.
B. Identifier được dùng để mã hóa secret value trước khi gửi qua mạng.
C. Secret value có thể công khai; identifier mới là phần cần giữ bí mật.
D. Hai phần phải giống nhau để hệ thống xác minh credential nhanh hơn.
Đáp án đúng: A

6. Một workload cần truy cập secret mà không nhúng credential dài hạn; hướng nào phù hợp?
A. Dùng workload identity để đổi danh tính lấy credential ngắn hạn.
B. Lưu một service account key cố định trong image của workload.
C. Dùng chung API key của nhóm vận hành cho mọi workload trong môi trường.
D. Đọc mật khẩu từ biến môi trường được commit trong manifest triển khai.
Đáp án đúng: A

7. Policy secret manager nên giới hạn quyền đọc secret theo những yếu tố nào?
A. Chỉ địa chỉ IP nguồn vì mọi workload trong mạng đều đáng tin.
B. Tên ứng dụng trong request mà không xác minh danh tính gọi.
C. Principal, secret path, action và môi trường theo nhu cầu công việc.
D. Quyền admin chung để tránh lỗi khi workload cần rotate credential.
Đáp án đúng: C

8. Vì sao nên tách namespace hoặc path secret theo ứng dụng và môi trường?
A. Giúp mọi ứng dụng dùng chung một secret để giảm số lượng bản sao.
B. Giảm truy cập chéo và giới hạn phạm vi ảnh hưởng khi credential bị lộ.
C. Cho phép kế thừa quyền production sang staging mà không cần phê duyệt.
D. Tránh phải gắn owner vì tên namespace đã thể hiện người quản lý.
Đáp án đúng: B

9. Khi bootstrap workload mới cần lấy secret từ secret manager, cách nào tránh vòng phụ thuộc credential?
A. Nhúng root token của secret manager vào image để lấy credential đầu tiên.
B. Dùng danh tính nền tảng được cấp sẵn để xác thực lần đầu.
C. Dùng secret của chính workload để xác minh trước khi workload tồn tại.
D. Yêu cầu người vận hành gửi mật khẩu qua console mỗi lần khởi động.
Đáp án đúng: B

10. Dynamic secret cho database khác credential dùng chung lâu dài ở điểm nào?
A. Được tạo một lần rồi dùng chung cho mọi ứng dụng trong cùng tenant.
B. Không cần quyền database vì secret manager tự thực thi mọi truy vấn.
C. Được cấp theo yêu cầu với TTL và thường có thể thu hồi riêng.
D. Không có thời hạn và chỉ thay đổi khi quản trị viên xóa database.
Đáp án đúng: C

11. Lease của dynamic credential hết hạn; secret manager nên xử lý thế nào?
A. Giữ credential hoạt động đến khi workload tự xóa bản sao trong bộ nhớ.
B. Tự động gia hạn vô hạn nếu workload còn gửi health check định kỳ.
C. Xóa metadata lease nhưng giữ tài khoản database để tránh gián đoạn.
D. Thu hồi credential theo lease hoặc gia hạn khi có yêu cầu hợp lệ.
Đáp án đúng: D

12. Ứng dụng cache secret để giảm độ trễ; kiểm soát nào cần được thiết kế?
A. Cache vô thời hạn vì secret manager đã kiểm soát quyền ở lần đọc đầu.
B. Dùng cache dùng chung cho mọi tenant để giảm số lần gọi secret manager.
C. Ghi secret vào file cache lâu dài để phục hồi sau khi tiến trình dừng.
D. TTL ngắn phù hợp, giới hạn phạm vi cache và xử lý revoke.
Đáp án đúng: D

13. Khi chọn inject secret qua environment variable hay file mount, đánh giá nào phù hợp?
A. So sánh lộ qua process, quyền file, vòng đời và cách tiêu thụ.
B. Environment variable luôn an toàn hơn vì không tạo file trên filesystem.
C. File mount luôn an toàn hơn vì secret không thể đọc từ tiến trình khác.
D. Hai cách có rủi ro giống nhau nên chỉ cần chọn cách dễ triển khai.
Đáp án đúng: A

14. Làm thế nào giảm nguy cơ secret xuất hiện trong log, trace hoặc metric label?
A. Mã hóa toàn bộ log bằng cùng secret đang được ứng dụng sử dụng.
B. Redact tại điểm ghi và tránh đưa giá trị secret vào telemetry.
C. Chỉ ẩn tên trường nhạy cảm nhưng vẫn ghi giá trị để phục vụ điều tra.
D. Chuyển secret sang metric label để có thể lọc theo từng credential.
Đáp án đúng: B

15. Một CI job chạy từ pull request của fork không đáng tin; chính sách secret nào phù hợp?
A. Không cấp secret production cho workflow chưa được tin cậy hoặc phê duyệt.
B. Cấp mọi secret nhưng chỉ cho phép job chạy trên runner dùng chung.
C. Đưa secret vào artifact để maintainer tải xuống sau khi merge.
D. Cho phép fork đọc secret nếu pull request chỉ thay đổi file kiểm thử.
Đáp án đúng: A

16. Build container cần credential tải dependency riêng tư; cách nào giảm rò rỉ vào image layer?
A. Truyền credential qua build argument rồi xóa trong lệnh cuối cùng.
B. Copy file credential vào image và xóa ở stage runtime sau khi build.
C. Dùng cơ chế build secret mount tạm thời và không ghi vào layer.
D. Đặt credential trong URL dependency để cache build tự quản lý.
Đáp án đúng: C

17. Terraform state có thể chứa secret; biện pháp nào phù hợp để bảo vệ state?
A. Mã hóa backend, giới hạn quyền đọc và tránh lưu state ở nơi công khai.
B. Chỉ bật version control vì lịch sử Git giúp khôi phục mọi thay đổi state.
C. Đổi tên thuộc tính secret thành output để Terraform không lưu giá trị.
D. Bật lifecycle ignore_changes để loại secret khỏi toàn bộ state.
Đáp án đúng: A

18. Kubernetes Secret được encode Base64; điều đó bảo đảm điều gì?
A. Base64 mã hóa nội dung bằng khóa cluster và chỉ pod mới giải mã được.
B. Chỉ là biểu diễn dữ liệu; không cung cấp tính bí mật hay mã hóa.
C. Base64 bảo đảm tính toàn vẹn nên không cần kiểm soát quyền truy cập.
D. Base64 che nội dung khỏi người có quyền đọc object trong API server.
Đáp án đúng: B

19. Để bảo vệ Kubernetes Secret lưu trong etcd, lớp kiểm soát nào cần cấu hình?
A. Chỉ bật TLS giữa pod và service vì etcd tự mã hóa mọi object.
B. Dùng Base64 thêm một lần trước khi ghi Secret vào etcd.
C. Encryption at rest cho dữ liệu Secret và quản lý khóa mã hóa an toàn.
D. Đổi tên namespace định kỳ để ciphertext cũ không thể được đọc lại.
Đáp án đúng: C

20. RBAC Kubernetes nên được cấu hình thế nào để pod chỉ đọc secret cần thiết?
A. Gán cluster-admin cho service account để tránh lỗi quyền khi deploy.
B. Cấp get theo resourceNames cho Secret cần thiết trong namespace.
C. Cho mọi pod cùng namespace quyền đọc tất cả Secret trong cluster.
D. Cấp quyền secrets/* toàn cluster rồi dựa vào tên pod để phân biệt.
Đáp án đúng: B

21. Khi dùng external secret controller hoặc CSI driver, rủi ro nào vẫn cần quản lý?
A. Không cần xác thực tới secret manager vì controller đã cài trong cluster.
B. Secret được mount sẽ tự động biến mất khỏi mọi bộ nhớ khi unmount.
C. RBAC Kubernetes không còn cần thiết vì secret được lưu bên ngoài.
D. Quyền workload, đồng bộ, cache, mount và vòng đời secret tại node.
Đáp án đúng: D

22. Projected service account token trong Kubernetes nên được giới hạn thế nào?
A. Dùng token không hết hạn để mọi pod có thể tái sử dụng sau restart.
B. Đặt audience là mọi dịch vụ trong cluster để tránh lỗi xác thực.
C. Đặt audience phù hợp và thời hạn ngắn theo nhu cầu workload.
D. Lưu token trong image để pod mới có thể dùng lại cùng danh tính.
Đáp án đúng: C

23. Lịch rotation secret nên dựa trên tiêu chí nào?
A. Một chu kỳ cố định cho mọi secret bất kể loại credential hay mức rủi ro.
B. Chỉ số lần đăng nhập thành công vì credential ít dùng ít cần đổi.
C. Ngày tạo repository vì secret trong mã nguồn thường ít thay đổi.
D. Mức nhạy cảm, thời hạn, mức phơi nhiễm và yêu cầu vận hành.
Đáp án đúng: D

24. Làm thế nào rotate database credential mà hạn chế downtime cho ứng dụng?
A. Tạo credential mới, cập nhật consumer, xác nhận rồi thu hồi credential cũ.
B. Thu hồi credential cũ trước rồi mới tạo credential mới cho ứng dụng.
C. Đổi mật khẩu tại database và chờ mọi connection pool tự cập nhật.
D. Tạo credential mới nhưng giữ credential cũ không thời hạn để dự phòng.
Đáp án đúng: A

25. Khi nào nên revoke secret ngay thay vì đợi kỳ rotation định kỳ?
A. Khi secret đã qua một nửa thời hạn dù chưa có dấu hiệu rủi ro.
B. Khi workload có lần khởi động lại nhưng danh tính vẫn được xác minh.
C. Khi có bằng chứng lộ, lạm dụng hoặc mất kiểm soát credential.
D. Khi log ghi nhận một lần đọc secret hợp lệ từ service đã đăng ký.
Đáp án đúng: C

26. Inventory secret cần những thông tin nào để hỗ trợ rotation và thu hồi an toàn?
A. Chỉ tên secret và giá trị hiện tại để quản trị viên có thể tìm nhanh.
B. Chỉ ngày tạo và số lần đọc mà không cần xác định workload sử dụng.
C. Tên người tạo cùng vị trí file cấu hình ban đầu của credential.
D. Owner, consumer, mục đích, môi trường, hạn dùng và dependency.
Đáp án đúng: D

27. Secret scanning ở pre-commit, CI và repository server-side có vai trò gì?
A. Phát hiện sớm credential trong các điểm ghi mã và lưu trữ.
B. Thay thế việc revoke credential vì scanner tự làm secret mất hiệu lực.
C. Chỉ kiểm tra file mới, không cần quét lịch sử hoặc artifact phát hành.
D. Tự động cấp quyền cho secret hợp lệ nếu nhận diện được mẫu key.
Đáp án đúng: A

28. Entropy-based detection và pattern-based detection khác nhau thế nào?
A. Entropy tìm chuỗi ngẫu nhiên cao; pattern nhận diện định dạng đã biết.
B. Entropy xác minh quyền key; pattern kiểm tra chữ ký của secret manager.
C. Entropy chỉ tìm password ngắn; pattern chỉ tìm khóa mã hóa nhị phân.
D. Hai cách luôn phát hiện mọi secret mà không có false positive.
Đáp án đúng: A

29. Một API key đã bị commit rồi xóa ở commit sau; vì sao việc xóa file chưa đủ?
A. Git tự động vô hiệu key khi phát hiện file bị xóa khỏi nhánh chính.
B. Credential vẫn có thể nằm trong Git history, clone và artifact đã phát hành.
C. Xóa commit mới sẽ làm mất mọi bản sao của repository trên máy khác.
D. Secret chỉ tồn tại trong working tree nên không thể còn trong lịch sử.
Đáp án đúng: B

30. Phát hiện API key production bị công khai; hành động ưu tiên nào phù hợp?
A. Chỉ xóa bài đăng chứa key rồi tiếp tục dùng credential hiện tại.
B. Chờ scanner xác nhận lần sử dụng trái phép trước khi vô hiệu key.
C. Revoke hoặc disable key, đánh giá phạm vi và cấp credential thay thế an toàn.
D. Đổi tên biến chứa key trong mã nguồn để ngăn truy cập tiếp theo.
Đáp án đúng: C

31. Secret manager ghi nhận workload đọc secret tăng đột biến ngoài giờ; nên làm gì?
A. Tăng quota đọc secret để workload hoàn tất các request đang chờ.
B. Tắt audit trong thời gian cao điểm để tránh tạo thêm cảnh báo.
C. Đối chiếu principal, workload, thời điểm và baseline rồi điều tra bất thường.
D. Xóa toàn bộ secret của workload trước khi xác định nguyên nhân.
Đáp án đúng: C

32. Tài khoản quản trị secret manager bị chiếm quyền; bước containment nào nên được ưu tiên?
A. Giữ nguyên phiên để thu thập thêm dữ liệu mà không hạn chế truy cập.
B. Xóa audit log có thể chứa thông tin quản trị trước khi điều tra.
C. Chỉ đổi mật khẩu một người dùng và giữ nguyên token cùng API key.
D. Cô lập hoặc thu hồi phiên, credential và quyền quản trị bị xâm phạm.
Đáp án đúng: D

33. Audit log của secret manager nên ghi dữ liệu nào để điều tra mà không lộ secret?
A. Giá trị secret đầy đủ cùng token để điều tra có thể phát lại request.
B. Principal, secret ID, action, thời điểm, kết quả và request context.
C. Chỉ số lượng lần đọc theo ngày mà không lưu danh tính principal.
D. Mật khẩu cũ và mới để đối chiếu mọi lần rotate credential.
Đáp án đúng: B

34. Break-glass access cho secret manager nên có kiểm soát nào?
A. Tài khoản admin dùng chung luôn bật để xử lý mọi lỗi tức thời.
B. Quyền khẩn cấp giới hạn, phê duyệt hoặc giám sát và audit đầy đủ.
C. Lưu root token trong wiki nội bộ để mọi kỹ sư có thể truy cập.
D. Bỏ audit khi break-glass được kích hoạt để tránh chậm xử lý sự cố.
Đáp án đúng: B

35. Khi phục hồi secret manager từ backup sau sự cố, điều kiện nào quan trọng?
A. Khôi phục cả dữ liệu và khả năng truy cập khóa KMS cần thiết.
B. Chỉ khôi phục database vì khóa có thể suy ra từ ciphertext backup.
C. Dùng một master key plaintext chung để giải mã mọi bản backup.
D. Bỏ kiểm tra integrity nếu backup được tạo bởi lịch chạy tự động.
Đáp án đúng: A

36. Secret manager tạm thời không truy cập được; quyết định fail-closed hay dùng cache nên dựa trên điều gì?
A. Luôn dùng cache vô thời hạn để mọi ứng dụng duy trì hoạt động.
B. Luôn trả secret cũ cho mọi caller dù credential đã bị revoke.
C. Luôn fail-open vì gián đoạn truy cập secret ảnh hưởng mọi workload.
D. Mức rủi ro, TTL còn lại, tính sẵn sàng và chính sách cho từng secret.
Đáp án đúng: D

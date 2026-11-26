1. Mô hình ABAC đưa ra quyết định truy cập chủ yếu dựa trên yếu tố nào?
A. Vai trò cố định của người dùng trong một nhóm nghiệp vụ.
B. Thuộc tính chủ thể, tài nguyên, hành động và môi trường.
C. Quan hệ cha-con giữa tài khoản và tài nguyên được lưu sẵn.
D. Danh sách quyền tĩnh gán trực tiếp cho từng người dùng.
Đáp án đúng: B

2. Thuộc tính nào sau đây thuộc về tài nguyên trong một quyết định ABAC?
A. Nhãn phân loại và chủ sở hữu của tài liệu được yêu cầu.
B. Phòng ban và cấp độ truy cập của người gửi yêu cầu.
C. Hành động đọc hoặc sửa mà ứng dụng muốn thực hiện.
D. Thời gian truy cập và trạng thái thiết bị hiện tại.
Đáp án đúng: A

3. Bộ quyết định nhận clearance do client tự gửi để xác định mức truy cập. PIP nên làm gì?
A. Lấy clearance từ nguồn có thẩm quyền và xác minh nguồn gốc thuộc tính.
B. Tin giá trị client gửi nếu kết nối request đã được bảo vệ bằng TLS.
C. Dùng giá trị đầu tiên trong cache mà không kiểm tra thời điểm cập nhật.
D. Suy ra clearance từ tên người dùng để tránh truy vấn nguồn danh tính.
Đáp án đúng: A

4. Trách nhiệm nào mô tả đúng quan hệ giữa PEP, PDP và PIP?
A. PEP quản lý policy; PDP cung cấp thuộc tính; PIP ghi audit log.
B. PEP cấp tài khoản; PDP lưu session; PIP ký token truy cập.
C. PEP thi hành; PDP đánh giá policy; PIP cung cấp thuộc tính.
D. PEP phê duyệt policy; PDP thực thi tại tài nguyên; PIP tạo user.
Đáp án đúng: C

5. Một tổ chức cần PDP dùng chung cho nhiều dịch vụ nhưng tránh điểm lỗi đơn. Thiết kế nào phù hợp?
A. Đặt policy trong từng client và để mỗi ứng dụng tự diễn giải.
B. Chuyển quyền quyết định sang PIP để nguồn dữ liệu tự cấp quyền.
C. Chỉ kiểm tra tại gateway và bỏ enforcement trong backend.
D. Triển khai PDP có khả năng mở rộng, HA và cache được kiểm soát.
Đáp án đúng: D

6. Khi nhiều policy cùng áp dụng, deny-overrides có ý nghĩa gì?
A. Chọn kết quả của rule đầu tiên khớp theo thứ tự khai báo.
B. Deny được ưu tiên khi policy áp dụng có kết quả từ chối.
C. Ưu tiên Permit nếu có ít nhất một policy cho phép truy cập.
D. Chỉ trả kết quả khi đúng một policy khớp với request.
Đáp án đúng: B

7. Policy cần thuộc tính thiết bị nhưng PIP không thể truy xuất thuộc tính đó. Cách xử lý an toàn là gì?
A. Suy ra thuộc tính từ role gần nhất của chủ thể đang truy cập.
B. Trả Indeterminate và để PEP áp dụng mặc định từ chối.
C. Xem thuộc tính thiếu như wildcard để các điều kiện khác tiếp tục.
D. Cho phép truy cập nếu các thuộc tính còn lại thỏa policy.
Đáp án đúng: B

8. Vì sao không nên tin thuộc tính subject do client tự gửi trong request?
A. TLS bảo vệ đường truyền nên cũng chứng minh client khai báo đúng.
B. Chỉ cần kiểm tra kiểu dữ liệu mà không cần xác minh nguồn.
C. Client có thể sửa giá trị; cần đối chiếu với nguồn đáng tin cậy.
D. Thuộc tính client gửi luôn mới hơn dữ liệu trong directory.
Đáp án đúng: C

9. Context assertion được chuyển qua nhiều service cần được xác minh thế nào?
A. Đưa context vào query string để các service dễ chuyển tiếp.
B. Dùng timestamp đơn lẻ để chứng minh nguồn gốc và tính toàn vẹn.
C. Chỉ mã hóa payload mà không xác minh bên phát hành.
D. Kiểm tra chữ ký, issuer, audience và thời hạn của assertion.
Đáp án đúng: D

10. Cache thuộc tính subject có nguy cơ giữ dữ liệu cũ sau khi nhân sự đổi đơn vị. Cách thiết kế nào phù hợp?
A. Chọn TTL theo tốc độ thay đổi và hỗ trợ invalidation từ nguồn.
B. Dùng TTL dài giống nhau cho mọi thuộc tính để giảm tải hệ thống.
C. Chỉ xóa cache khi PDP khởi động lại sau mỗi lần triển khai.
D. Cache theo subject mà không xét resource hoặc action trong request.
Đáp án đúng: A

11. PEP nên được đặt ở đâu trong kiến trúc phân tán?
A. Chỉ ở API gateway vì backend nội bộ luôn được tin cậy.
B. Chỉ ở giao diện người dùng trước khi gửi request tới server.
C. Tại ranh giới tin cậy nơi truy cập tài nguyên được thực thi.
D. Chỉ trong PDP sau khi policy đã đưa ra quyết định cuối cùng.
Đáp án đúng: C

12. Khác biệt nào mô tả đúng obligation và advice trong mô hình policy?
A. Cả hai đều bắt buộc và PDP tự thực thi sau khi trả kết quả.
B. Advice là Deny bắt buộc, còn obligation chỉ mang tính gợi ý.
C. PEP phải thực hiện obligation; advice chỉ mang tính gợi ý.
D. PEP có thể bỏ qua obligation khi quyết định chính là Permit.
Đáp án đúng: C

13. Bộ kết quả nào thường được dùng để biểu diễn quyết định policy?
A. Allow, Block, Retry và Timeout cho mọi policy engine.
B. Success, Failure, Pending và Unknown theo trạng thái request.
C. Permit, Reject, Skip và Error theo kết quả của PEP.
D. Permit, Deny, NotApplicable và Indeterminate.
Đáp án đúng: D

14. Vai trò chính của Policy Administration Point (PAP) là gì?
A. Quản lý soạn thảo, duyệt và phát hành policy có version.
B. Thực thi quyết định truy cập tại API và kho dữ liệu đích.
C. Cung cấp thuộc tính runtime từ HR và inventory thiết bị.
D. Ghi lại session và token để phục vụ điều tra truy cập.
Đáp án đúng: A

15. Bộ kiểm thử nào bao phủ tốt một policy ABAC?
A. Chỉ kiểm tra role chính và endpoint được dùng thường xuyên.
B. Bao phủ bốn nhóm thuộc tính và các giá trị biên.
C. Chỉ đo thời gian PDP với một bộ dữ liệu cố định.
D. Chỉ kiểm thử request được Permit để giảm số test case.
Đáp án đúng: B

16. Property-based testing hữu ích cho policy ABAC vì lý do nào?
A. Chạy lại dữ liệu production mà không lưu kết quả quyết định.
B. So sánh tên policy và đếm số rule giữa các phiên bản.
C. Sinh nhiều tổ hợp thuộc tính để tìm quyết định bất thường.
D. Thay policy bằng mock để chỉ kiểm tra giao diện PEP.
Đáp án đúng: C

17. PDP không khả dụng trong lúc yêu cầu đọc hồ sơ tài chính nhạy cảm. PEP nên làm gì?
A. Permit mọi request để duy trì tính sẵn sàng của ứng dụng.
B. Dùng policy bất kỳ trong bộ nhớ mà không kiểm tra phiên bản.
C. Chuyển quyền quyết định sang client để tránh gián đoạn.
D. Từ chối thao tác khi không thể đánh giá policy tin cậy.
Đáp án đúng: D

18. PIP chậm khiến độ trễ quyết định tăng cao. Biện pháp nào cải thiện hiệu năng mà vẫn giữ freshness?
A. Tăng retry vô hạn và chờ PIP phục hồi trong mỗi request.
B. Nới timeout PEP để người dùng không thấy lỗi truy cập.
C. Bỏ truy vấn thuộc tính và dùng giá trị mặc định rộng hơn.
D. Tối ưu truy vấn, cache theo freshness và giới hạn timeout.
Đáp án đúng: D

19. Trước khi dùng claim trong token làm thuộc tính ABAC, PDP cần làm gì?
A. Giải mã Base64 payload rồi lấy claim theo tên trường nội bộ.
B. Xác minh chữ ký, issuer, audience và thời hạn của token.
C. Tin claim nếu subject đã tồn tại trong directory của tổ chức.
D. Chỉ kiểm tra tên trường vì token được truyền qua TLS.
Đáp án đúng: B

20. Cách nào giúp ngăn truy cập chéo tenant trong policy ABAC?
A. Dùng tenant_id client gửi làm điều kiện duy nhất của policy.
B. Ràng buộc tenant subject với tenant resource từ nguồn tin cậy.
C. Chỉ lọc tenant ở giao diện và tin backend không cần kiểm tra.
D. Permit nếu user có role chung ở bất kỳ tenant nào.
Đáp án đúng: B

21. Policy cần ngăn người tạo giao dịch tự phê duyệt giao dịch đó. Thuộc tính nào cần so sánh?
A. Danh tính initiator và approver của cùng giao dịch.
B. Thời điểm tạo giao dịch và thời gian đăng nhập gần nhất.
C. Phòng ban của người phê duyệt và chủ sở hữu tài nguyên.
D. Địa chỉ mạng của người tạo và thiết bị người phê duyệt.
Đáp án đúng: A

22. Khi kết hợp ReBAC với ABAC, cách thiết kế nào phù hợp?
A. Dùng role toàn cục để mô tả mọi quan hệ giữa các tài nguyên.
B. Chuyển mọi thuộc tính thành group để tránh truy vấn quan hệ.
C. Chỉ dùng ACL tĩnh, không xét thuộc tính môi trường.
D. Kiểm tra quan hệ liên quan rồi áp thêm điều kiện thuộc tính.
Đáp án đúng: D

23. Policy combining algorithm first-applicable hoạt động thế nào?
A. Tổng hợp mọi kết quả và luôn ưu tiên Deny trong mọi trường hợp.
B. Ưu tiên Permit khi có ít nhất một rule cho phép request.
C. Dùng kết quả của policy đầu tiên áp dụng theo thứ tự đánh giá.
D. Chỉ hợp lệ khi toàn bộ policy đều trả về cùng kết quả.
Đáp án đúng: C

24. Khi mọi lệnh cấm phải được giữ dù policy khác cho phép, nên chọn thuật toán nào?
A. First-applicable với policy Permit luôn được đặt ở đầu danh sách.
B. Permit-overrides để tránh từ chối nhầm người dùng hợp lệ.
C. Only-one-applicable để bỏ qua các policy cùng khớp request.
D. Deny-overrides để quyết định từ chối có độ ưu tiên cao.
Đáp án đúng: D

25. Một thuộc tính có giá trị khác nhau giữa HR và directory. Cách chọn nguồn nào phù hợp?
A. Chọn nguồn chuẩn theo từng thuộc tính và xác minh provenance.
B. Ưu tiên request mới nhất bất kể caller hoặc nguồn cung cấp.
C. Lấy nguồn phản hồi nhanh nhất làm nguồn chuẩn cho mọi trường.
D. Dùng nguồn đầu tiên trả lời thành công và bỏ qua xung đột.
Đáp án đúng: A

26. Làm thế nào để giảm nguy cơ confused deputy khi service có quyền rộng gọi thay caller?
A. Thay caller bằng service account rồi chỉ kiểm tra quyền service.
B. Xóa thông tin caller để tránh truyền dữ liệu qua service.
C. Chỉ ghi tên người dùng vào log mà không dùng trong quyết định.
D. Giữ caller gốc và giới hạn quyền ủy quyền của service.
Đáp án đúng: D

27. Trong kiến trúc ABAC, trách nhiệm nào thuộc về PIP?
A. Trả Permit hoặc Deny sau khi áp dụng policy cho request.
B. Soạn thảo và phê duyệt phiên bản policy trước khi phát hành.
C. Lấy thuộc tính từ các nguồn có thẩm quyền cho PDP đánh giá.
D. Thực thi quyết định cuối cùng tại ranh giới tài nguyên.
Đáp án đúng: C

28. Thuộc tính nào là ví dụ điển hình của environment?
A. Phòng ban và trạng thái nhân sự của người gửi request.
B. Thời gian, vị trí mạng và posture thiết bị hiện tại.
C. Nhãn phân loại và chủ sở hữu của tài liệu đích.
D. Hành động đọc, cập nhật hoặc xóa được yêu cầu.
Đáp án đúng: B

29. Làm thế nào để giảm dữ liệu nhạy cảm được chuyển tới policy engine?
A. Gửi toàn bộ thuộc tính sẵn có để PDP có nhiều lựa chọn.
B. Chỉ chuyển thuộc tính cần thiết, rồi giới hạn lưu giữ.
C. Ghi toàn bộ giá trị thuộc tính thô vào log để điều tra.
D. Sao chép dữ liệu nhạy cảm vào cache lâu dài của từng service.
Đáp án đúng: B

30. PEP nên xử lý thế nào nếu không thể thực hiện obligation bắt buộc đi kèm Permit?
A. Bỏ qua obligation vì PDP đã cho phép hành động chính.
B. Xem obligation như ghi chú dành riêng cho quản trị viên.
C. Thực hiện obligation trong PDP sau khi PEP đã trả response.
D. Từ chối thao tác nếu obligation không thực thi được.
Đáp án đúng: D

31. Những thành phần nào nên có trong cache key của quyết định truy cập?
A. Dùng subject, resource, action, context và policy version.
B. Chỉ user ID vì quyền của người dùng không đổi theo request.
C. Chỉ resource ID vì mọi hành động có cùng quyền truy cập.
D. IP và thời gian request làm khóa cho mọi quyết định.
Đáp án đúng: A

32. Cách rollout policy mới nào giúp phát hiện thay đổi quyết định ngoài dự kiến?
A. Thay policy production trực tiếp rồi theo dõi sự cố phát sinh.
B. Tắt policy cũ trước khi so sánh kết quả policy mới.
C. So sánh shadow/canary với quyết định hiện hành.
D. Áp dụng policy cho một user mà không lưu kết quả cũ.
Đáp án đúng: C

33. Decision log hữu ích cho kiểm toán mà vẫn bảo vệ dữ liệu thế nào?
A. Ghi subject, resource, outcome, policy version và che dữ liệu nhạy cảm.
B. Lưu credential và toàn bộ attribute payload để tái dựng request.
C. Chỉ lưu Permit hoặc Deny mà không ghi resource hay policy.
D. Gửi mọi quyết định tới dịch vụ log công khai để dễ truy cập.
Đáp án đúng: A

34. Cách nào bảo vệ audit log khỏi bị sửa bởi người quản trị policy?
A. Cho phép policy admin sửa sự kiện cũ khi phát hiện sai sót.
B. Dùng lưu trữ append-only và tách quyền quản trị audit.
C. Giữ log trong file tạm cục bộ của từng PDP node.
D. Xóa log cũ sau mỗi lần phát hành policy để giảm dung lượng.
Đáp án đúng: B

35. Nhóm chỉ số nào giúp phát hiện policy drift hoặc quyết định bất thường?
A. Theo dõi Permit/Deny, Indeterminate và latency theo policy version.
B. Đếm số file policy mà không đo kết quả hoặc lỗi thực thi.
C. Đếm tổng người dùng nhưng bỏ qua tài nguyên họ truy cập.
D. Chỉ cảnh báo khi toàn bộ PDP node dừng hoạt động đồng thời.
Đáp án đúng: A

36. Làm thế nào để ngăn backend bị gọi trực tiếp nhằm bypass PEP ở API gateway?
A. Đặt toàn bộ enforcement trong browser và ẩn nút không được phép.
B. Tin mạng riêng và cho phép truy cập trực tiếp vào data store.
C. Enforce tại service/resource boundary và hạn chế đường bypass.
D. Chỉ kiểm tra policy lúc login rồi cache Permit vô thời hạn.
Đáp án đúng: C

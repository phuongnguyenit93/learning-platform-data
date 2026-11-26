1. Một người dùng đăng nhập thành công nhưng gọi API đọc hồ sơ của người khác; kiểm soát nào quyết định request có được phép?
A. Authorization quyết định quyền thực hiện hành động trên tài nguyên cụ thể.
B. Authentication xác minh danh tính nhưng không tự cấp quyền trên mọi tài nguyên.
C. Session management kiểm tra cookie còn hạn rồi quyết định quyền đọc hồ sơ.
D. Firewall lọc kết nối mạng theo địa chỉ mà không xét quyền nghiệp vụ.
Đáp án đúng: A

2. Một quyết định truy cập cần mô tả ai đang làm gì trên đối tượng nào trong hoàn cảnh nào; bộ thành phần nào phù hợp?
A. User, password, session và authentication provider của người gọi.
B. Subject, action, resource và environment context của request.
C. Role, group, token và giao diện được hiển thị cho người dùng.
D. Request, response, status code và network route của kết nối.
Đáp án đúng: B

3. Một endpoint không có rule rõ ràng cho hành động nhạy cảm; chính sách mặc định nào an toàn hơn?
A. Cho phép nếu người dùng đã đăng nhập và token còn hiệu lực.
B. Cho phép tạm thời rồi ghi audit để quản trị viên xem lại sau.
C. Dùng quyết định gần nhất trong cache dù policy đã thay đổi.
D. Từ chối khi chưa có policy cho phép rõ ràng và hợp lệ.
Đáp án đúng: D

4. Trong RBAC, cách liên kết quyền phổ biến nào mô tả đúng mô hình?
A. Gán role vào tài nguyên rồi để client tự chọn permission cần dùng.
B. Gán người dùng vào role và gán permission cho từng role.
C. Gán permission vào session và suy ra role từ địa chỉ mạng.
D. Gán quyền trực tiếp cho nhóm rồi bỏ qua vai trò người dùng.
Đáp án đúng: B

5. Một policy cần xét phòng ban người dùng, mức phân loại tài liệu và thời điểm truy cập; mô hình nào phù hợp?
A. RBAC thuần túy chỉ xét role tĩnh được gán cho người dùng.
B. ACL chỉ xét danh sách principal được ghi trực tiếp trên tài liệu.
C. ABAC đánh giá thuộc tính subject, resource, action và environment.
D. DAC chỉ xét chủ sở hữu tài liệu và bỏ qua điều kiện môi trường.
Đáp án đúng: C

6. Một role cấp cao kế thừa quyền của role cấp thấp; rủi ro nào cần được đánh giá?
A. Role hierarchy khiến mọi permission trở thành quyền tạm thời theo phiên.
B. Quyền kế thừa tự động giới hạn theo tenant mà không cần policy.
C. Quyền kế thừa có thể mở rộng ngoài nhiệm vụ nếu hierarchy thiếu kiểm soát.
D. Role cấp cao không thể kiểm toán vì quyền được suy ra động.
Đáp án đúng: C

7. Một nhân viên có thể vừa tạo nhà cung cấp vừa phê duyệt thanh toán cho nhà cung cấp đó; kiểm soát nào giảm xung đột lợi ích?
A. Separation of duties tách nhiệm vụ xung đột giữa các chủ thể.
B. Role hierarchy gom hai nhiệm vụ vào một role để giảm số lần cấp quyền.
C. Session timeout buộc người dùng đăng nhập lại giữa hai thao tác.
D. Resource tagging đánh dấu giao dịch đã tạo trước khi phê duyệt.
Đáp án đúng: A

8. Một hệ thống có hàng trăm role chỉ khác nhau theo từng dự án và tài liệu; dấu hiệu thiết kế nào đang xuất hiện?
A. Role inheritance do role cấp cao gom quyền của nhiều nhóm.
B. Permission caching do hệ thống lưu quyết định truy cập quá lâu.
C. Federated identity do nhiều provider cùng phát hành assertion.
D. Role explosion do dùng role để biểu diễn quá nhiều biến thể thuộc tính.
Đáp án đúng: D

9. Một quyết định ABAC cần thuộc tính phân loại tài liệu nhưng nguồn thuộc tính không phản hồi; hành vi nào phù hợp?
A. Từ chối khi thiếu thuộc tính bắt buộc để đánh giá policy.
B. Bỏ qua thuộc tính thiếu và áp dụng giá trị mặc định ít hạn chế hơn.
C. Dùng giá trị cache gần nhất mà không xác minh độ mới dữ liệu.
D. Chuyển sang allow nếu principal có role đăng nhập hợp lệ.
Đáp án đúng: A

10. Hai policy cùng khớp request, một allow và một deny; quy tắc nào thường an toàn hơn?
A. Allow-overrides để một rule cho phép có thể chấp nhận request.
B. First-match theo thứ tự file mà không xét độ nhạy tài nguyên.
C. Deny-overrides để một rule từ chối có thể chặn request.
D. Last-match theo thứ tự chạy để policy sau thay thế policy trước.
Đáp án đúng: C

11. Client có thể tự gửi department=Finance trong request để vượt policy; cách xử lý nào đúng?
A. Chấp nhận thuộc tính client gửi nếu request được truyền qua TLS.
B. Dùng giá trị client gửi khi nó khớp tên role trong token.
C. Chỉ kiểm tra định dạng chuỗi trước khi đưa thuộc tính vào policy.
D. Lấy thuộc tính từ nguồn tin cậy phía server và kiểm tra nguồn gốc.
Đáp án đúng: D

12. API nhận documentId từ client và trả dữ liệu nếu người dùng đã đăng nhập; lỗ hổng nào có thể xảy ra?
A. BOLA/IDOR nếu server không kiểm tra quyền trên đúng document.
B. CSRF nếu server không mã hóa documentId trước khi truy vấn dữ liệu.
C. SSRF nếu documentId có dạng số và được gửi qua HTTPS.
D. Replay nếu người dùng gọi cùng endpoint nhiều lần trong một phiên.
Đáp án đúng: A

13. Tài liệu thuộc Alice nhưng được chia sẻ cho Bob theo ACL; server nên quyết định quyền đọc dựa trên điều gì?
A. Cho phép thành viên cùng nhóm với Bob đọc mọi tài liệu mặc định.
B. So sánh documentId với ID client gửi mà không kiểm tra quan hệ.
C. Xác minh ownership hoặc quyền chia sẻ được cấp cho đúng principal.
D. Cho phép nếu Bob có role đăng nhập và tài liệu còn tồn tại.
Đáp án đúng: C

14. Ứng dụng đa tenant nhận tenantId trong query parameter; kiểm soát nào ngăn người dùng đổi sang tenant khác?
A. Ràng buộc tenant context với danh tính đã xác thực ở server.
B. Mã hóa tenant ID ở client để người dùng khó đọc giá trị thật.
C. Ẩn tenant ID khỏi giao diện nhưng vẫn lấy từ request gửi lên.
D. Chỉ kiểm tra tenant ID tồn tại trước khi truy vấn dữ liệu.
Đáp án đúng: A

15. Endpoint trả danh sách hóa đơn cho người dùng; cách nào bảo đảm không lộ hóa đơn ngoài phạm vi quyền?
A. Tải mọi bản ghi rồi để giao diện ẩn dòng người dùng không được xem.
B. Lọc truy vấn hoặc kết quả ở server theo phạm vi được phép.
C. Trả toàn bộ ID và chỉ kiểm tra quyền khi người dùng mở từng bản ghi.
D. Giới hạn số trang mà không lọc dữ liệu theo principal hay tenant.
Đáp án đúng: B

16. Thao tác hàng loạt cập nhật 20 object nhưng người dùng chỉ có quyền với 18; hệ thống nên làm gì?
A. Cho phép cả batch vì principal có quyền trên phần lớn object.
B. Áp dụng policy cho từng object và xử lý kết quả theo quy tắc rõ.
C. Từ chối batch chỉ khi client tự khai báo object ngoài phạm vi.
D. Cập nhật tất cả rồi dựa vào audit để hoàn tác object không hợp lệ.
Đáp án đúng: B

17. Người dùng có quyền đọc project nhưng không mặc nhiên có quyền đọc mọi secret trong đó; nguyên tắc nào áp dụng?
A. Mọi quyền trên project luôn áp dụng cho tất cả secret trong project.
B. Cùng tenant đồng nghĩa mọi object con có cùng quyền truy cập.
C. Chỉ kiểm tra quyền tài nguyên con khi người dùng tạo object mới.
D. Không tự kế thừa quyền cha cho tài nguyên con nhạy cảm.
Đáp án đúng: D

18. Giao diện ẩn nút Delete với người dùng không có quyền nhưng API vẫn nhận lệnh xóa; lớp nào phải thực thi quyền?
A. Client-side rendering trước khi hiển thị nút Delete trên màn hình.
B. Ẩn đường dẫn trong menu và dựa vào router phía trình duyệt.
C. Server-side enforcement tại điểm xử lý hành động xóa.
D. Browser cache ghi nhớ lần từ chối để chặn lần gọi tiếp theo.
Đáp án đúng: C

19. Trong kiến trúc authorization, thành phần nào thường chặn request và thực thi quyết định allow hoặc deny?
A. Policy Information Point (PIP) cung cấp thuộc tính chủ thể và tài nguyên.
B. Policy Enforcement Point (PEP) chặn request và thực thi quyết định.
C. Policy Administration Point (PAP) quản lý vòng đời và phiên bản policy.
D. Identity Provider (IdP) xác minh danh tính người gọi trước đăng nhập.
Đáp án đúng: B

20. Trong kiến trúc policy-based access control, thành phần nào đưa ra quyết định dựa trên policy và thuộc tính?
A. Policy Enforcement Point (PEP) chặn request và thực thi allow hoặc deny.
B. Policy Administration Point (PAP) quản lý phiên bản và phê duyệt policy.
C. Policy Information Point (PIP) cung cấp thuộc tính từ nguồn dữ liệu.
D. Policy Decision Point (PDP) đánh giá policy và trả về quyết định.
Đáp án đúng: D

21. Hệ thống cần nơi quản trị viên tạo, sửa và phê duyệt policy; thành phần nào phù hợp?
A. Policy Information Point thu thập thuộc tính từ hồ sơ và tài nguyên.
B. Policy Enforcement Point chặn request tại điểm truy cập tài nguyên.
C. Policy Administration Point quản lý việc tạo, sửa và phê duyệt policy.
D. Policy Decision Point đánh giá rule đã cấu hình cho từng request.
Đáp án đúng: C

22. Một PDP cần biết chủ thể thuộc nhóm nào và tài liệu có nhãn gì; nguồn thuộc tính thường là thành phần nào?
A. Policy Enforcement Point lưu thuộc tính của mọi tài nguyên trong hệ thống.
B. Policy Administration Point tự tạo thuộc tính mới cho từng request.
C. Identity Provider thay thế mọi nguồn thuộc tính tài nguyên và môi trường.
D. Policy Information Point cung cấp thuộc tính cần cho việc đánh giá.
Đáp án đúng: D

23. Ứng dụng chỉ kiểm tra quyền ở REST controller nhưng GraphQL và RPC truy cập cùng dữ liệu; rủi ro nào phát sinh?
A. Các đường gọi khác nhau có thể bỏ qua enforcement và tạo lỗ hổng.
B. Các giao thức tự động chia sẻ cùng policy decision khi dùng chung token.
C. GraphQL và RPC không thể truy cập dữ liệu được quản lý qua REST.
D. Authorization chỉ cần đặt ở gateway vì service không truy cập trực tiếp.
Đáp án đúng: A

24. Database hỗ trợ row-level security; cách sử dụng nào tạo lớp bảo vệ phù hợp?
A. Áp dụng row policy ở database với context đã được xác minh an toàn.
B. Dùng row-level security thay toàn bộ authorization ở API và service.
C. Đặt tenant context từ client vào DB session mà không kiểm tra nguồn.
D. Bật row policy cho SELECT nhưng bỏ qua thao tác ghi dữ liệu.
Đáp án đúng: A

25. Background job chạy nhiều giờ sau khi người dùng khởi tạo; cách nào giữ quyết định quyền có thể kiểm soát?
A. Giữ access token ban đầu và tin cậy đến khi job kết thúc.
B. Giữ actor và delegation scope, rồi đánh giá quyền theo policy phù hợp.
C. Chạy job bằng tài khoản admin chung để tránh token người dùng hết hạn.
D. Bỏ qua authorization vì request khởi tạo đã được chấp nhận.
Đáp án đúng: B

26. Access token có scope orders.read nhưng ứng dụng có role BillingApprover; hai khái niệm nên được hiểu thế nào?
A. Scope và role luôn đồng nghĩa nên có thể thay thế trực tiếp.
B. Scope giới hạn quyền ủy quyền trong token; role nhóm quyền nội bộ.
C. Role chỉ xác thực danh tính, còn scope quyết định quyền database.
D. Scope mô tả thời hạn token, còn role mô tả loại người dùng.
Đáp án đúng: B

27. Nhân viên bị thu hồi quyền nhưng JWT cũ còn hiệu lực và chứa role trước đó; biện pháp nào giảm cửa sổ quyền cũ?
A. Tăng thời hạn JWT để client không phải xin token sau khi đổi quyền.
B. Xóa role khỏi giao diện vì claim đã ký không thể thay đổi.
C. Dùng token ngắn hạn và kiểm tra thu hồi khi cần thiết.
D. Tin claim cũ đến khi người dùng đóng trình duyệt hoặc đăng xuất.
Đáp án đúng: C

28. Permission vừa bị thu hồi nhưng cache authorization vẫn trả allow; kiểm soát nào cần thiết?
A. Tăng TTL cache để giảm tải cho policy decision point.
B. Cache theo URL mà không đưa principal hay resource vào cache key.
C. Giữ allow cho phiên hiện tại để tránh thay đổi giữa request.
D. Invalidation hoặc versioning để cache phản ánh quyền mới.
Đáp án đúng: D

29. Policy engine trả Indeterminate vì không đọc được thuộc tính bắt buộc; cách xử lý nào phù hợp?
A. Cho phép nếu chủ thể đã xác thực và có ít nhất một role hợp lệ.
B. Bỏ qua thuộc tính lỗi và dùng quyết định của lần truy cập trước.
C. Từ chối khi không thể đưa ra quyết định đáng tin cậy.
D. Chọn allow để duy trì sẵn sàng khi policy engine gặp lỗi.
Đáp án đúng: C

30. PDP timeout khi xử lý request đọc dữ liệu nhạy cảm; PEP nên phản ứng thế nào?
A. Allow request để duy trì sẵn sàng khi PDP không phản hồi.
B. Deny hoặc dùng cache còn hiệu lực theo giới hạn policy rõ ràng.
C. Chuyển kiểm tra quyền sang client khi server không gọi được PDP.
D. Lặp request vô hạn đến khi PDP trả lời mà không đặt timeout.
Đáp án đúng: B

31. Ứng dụng cấp signed URL để tải tài liệu riêng tư; URL nên được ràng buộc như thế nào?
A. Cho URL truy cập mọi object trong bucket đến khi user đăng xuất.
B. Ràng buộc URL với object, action và thời hạn sử dụng.
C. Chỉ ràng buộc URL với IP client mà không giới hạn hành động.
D. Dùng URL chung cho tenant để giảm chi phí ký từng tài nguyên.
Đáp án đúng: B

32. Quản trị viên cần quyền cao trong 30 phút để xử lý sự cố; mô hình nào kiểm soát tốt nhất?
A. Cấp quyền tạm thời có phê duyệt, phạm vi và thời hạn rõ.
B. Gán quyền admin vĩnh viễn rồi nhắc người dùng tự gỡ sau.
C. Chia sẻ tài khoản quản trị chung và đổi mật khẩu khi xử lý xong.
D. Tạo role đặc quyền không hết hạn để tránh xin duyệt nhiều lần.
Đáp án đúng: A

33. Một người quản lý ủy quyền cho trợ lý thực hiện một số thao tác; thông tin nào cần giữ trong quyết định?
A. Chỉ lưu danh tính trợ lý vì người ủy quyền không gọi API trực tiếp.
B. Chuyển toàn bộ quyền người quản lý sang trợ lý đến khi thu hồi.
C. Coi delegation là role cố định không cần giới hạn hành động.
D. Lưu actor, principal ủy quyền, phạm vi và thời hạn delegation.
Đáp án đúng: D

34. Một nhóm quản lý policy bằng code và cần triển khai thay đổi an toàn; quy trình nào phù hợp?
A. Version control, review, test và rollout policy có giám sát.
B. Sửa policy trực tiếp trên production để tránh lệch code và runtime.
C. Triển khai mọi policy cùng lúc rồi chỉ theo dõi lỗi máy chủ.
D. Cho từng service tự sửa policy cục bộ mà không đồng bộ phiên bản.
Đáp án đúng: A

35. Một đội kiểm thử muốn phát hiện truy cập ngang quyền và vượt tenant; cách kiểm thử nào có giá trị nhất?
A. Chỉ kiểm tra người dùng hợp lệ đọc được tài nguyên của chính họ.
B. Chỉ đo hiệu năng endpoint khi mọi request đều được cho phép.
C. Kiểm tra giao diện ẩn nút mà không gọi API trực tiếp.
D. Ma trận negative test giữa principal, resource, action và tenant.
Đáp án đúng: D

36. Tổ chức muốn phát hiện authorization drift sau nhiều lần thay đổi policy; tín hiệu vận hành nào hữu ích?
A. Chỉ theo dõi CPU và bộ nhớ của máy chủ xử lý request.
B. Chỉ đếm số người dùng đăng nhập thành công mỗi ngày.
C. Theo dõi allow, deny, policy change và truy cập bất thường theo phạm vi.
D. Đếm endpoint mà không phân biệt principal, resource hoặc action.
Đáp án đúng: C

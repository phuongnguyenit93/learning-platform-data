Câu 1. Trong PBAC, quyết định truy cập chủ yếu được xác định bằng cách nào?
A. Tra cứu một vai trò cố định rồi cấp mọi quyền gắn với vai trò
B. So khớp địa chỉ mạng với danh sách máy chủ được cho phép
C. Kiểm tra riêng chủ sở hữu tài nguyên mà không xét hành động
D. Đánh giá policy theo chủ thể, hành động, tài nguyên và ngữ cảnh
Đáp án đúng: D

Câu 2. Policy Decision Point (PDP) chịu trách nhiệm chính về việc gì?
A. Quản lý phiên đăng nhập và phát hành thông tin xác thực
B. Đánh giá policy theo request và trả Permit hoặc Deny
C. Thu thập thuộc tính từ nguồn dữ liệu bên ngoài
D. Chặn hoặc cho request đi qua tại điểm thực thi
Đáp án đúng: B

Câu 3. Policy Enforcement Point (PEP) thực hiện nhiệm vụ nào?
A. Phân tích xung đột giữa các chính sách trong bộ máy
B. Soạn thảo và phê duyệt phiên bản chính sách mới
C. Tổng hợp thuộc tính người dùng từ các hệ thống nguồn
D. Áp dụng Permit hoặc Deny tại điểm thực thi yêu cầu
Đáp án đúng: D

Câu 4. Policy Administration Point (PAP) thường được dùng để làm gì?
A. Đánh giá từng request và trả kết quả permit hoặc deny
B. Chặn request tại ranh giới dịch vụ theo quyết định PDP
C. Quản lý soạn thảo, phê duyệt và phân phối policy
D. Thu thập dữ liệu ngữ cảnh từ thiết bị và mạng
Đáp án đúng: C

Câu 5. Policy Information Point (PIP) cung cấp chức năng nào?
A. Truy xuất thuộc tính từ nguồn dữ liệu tin cậy
B. Áp dụng quyết định cuối cùng lên request đang xử lý
C. Quản lý lịch sử phiên bản và quy trình phê duyệt policy
D. Tạo danh tính và cấp credential cho principal mới
Đáp án đúng: A

Câu 6. Trong ABAC, quyết định thường dựa trên loại dữ liệu nào?
A. ACL liệt kê trực tiếp mọi người dùng được phép truy cập
B. Thuộc tính chủ thể, tài nguyên, hành động và môi trường
C. Địa chỉ IP của máy khách mà không xét dữ liệu khác
D. Danh sách vai trò được gán tĩnh cho từng tài khoản
Đáp án đúng: B

Câu 7. Lợi ích chính của việc tách policy khỏi mã nghiệp vụ là gì?
A. Đổi quy tắc truy cập mà ít sửa mã ứng dụng
B. Bảo đảm mọi yêu cầu hợp lệ đều được PDP tự động chấp thuận
C. Cho phép mọi dịch vụ tự định nghĩa quyền mà không đồng bộ
D. Loại bỏ nhu cầu kiểm thử quyền tại từng điểm thực thi
Đáp án đúng: A

Câu 8. Nếu không có chính sách nào cho phép một yêu cầu, hành vi mặc định an toàn là gì?
A. Cho phép nếu người dùng đã đăng nhập thành công
B. Dùng quyền của request gần nhất có cùng loại tài nguyên
C. Mặc định từ chối yêu cầu khi không có policy Permit rõ ràng
D. Chuyển sang quyền quản trị để tránh gián đoạn nghiệp vụ
Đáp án đúng: C

Câu 9. Thuộc tính nào thường mô tả chủ thể trong một quyết định PBAC?
A. Mức phân loại và chủ sở hữu của tài liệu đích
B. Phương thức HTTP và loại thao tác trên tài nguyên
C. Phòng ban, mức tin cậy và trạng thái nhân sự
D. Thời điểm trong ngày và mức rủi ro của mạng hiện tại
Đáp án đúng: C

Câu 10. Thuộc tính nào phù hợp để mô tả tài nguyên được truy cập?
A. Chủ sở hữu, tenant và mức phân loại dữ liệu
B. Địa chỉ IP, vị trí và mức độ tin cậy của thiết bị
C. Thời điểm đăng nhập và phương thức xác minh gần nhất
D. Vai trò, phòng ban và trạng thái xác thực của người dùng
Đáp án đúng: A

Câu 11. Ví dụ nào là thuộc tính môi trường có thể ảnh hưởng quyết định?
A. Loại hành động và định danh tài nguyên được yêu cầu
B. Chủ sở hữu tài liệu và nhãn phân loại của tài nguyên
C. Mã nhân viên, phòng ban và chức danh người yêu cầu
D. Thời gian truy cập, vùng mạng và mức rủi ro phiên
Đáp án đúng: D

Câu 12. Vì sao không nên tin trực tiếp tenant ID do client tự gửi trong request?
A. Tenant ID thường thay đổi theo từng request hợp lệ
B. Tenant ID chỉ có ý nghĩa khi được mã hóa bằng TLS
C. Client có thể giả mạo tenant bằng cách sửa giá trị này
D. Client luôn nhận tenant ID từ PDP nên không thể sửa
Đáp án đúng: C

Câu 13. Để bảo vệ ranh giới multi-tenant, policy nên kiểm tra điều gì?
A. Người dùng phải có cùng địa chỉ IP với máy chủ lưu dữ liệu
B. Mọi tenant phải dùng chung một vai trò quản trị toàn cục
C. Tên tài nguyên phải duy nhất trên toàn bộ hệ thống
D. Tenant của chủ thể phải phù hợp tenant của tài nguyên
Đáp án đúng: D

Câu 14. Một thuộc tính bắt buộc không lấy được từ nguồn tin cậy. Cách xử lý nào an toàn?
A. Bỏ qua điều kiện đó để các chính sách khác tiếp tục chạy
B. Từ chối quyền và ghi nhận thuộc tính không xác định
C. Dùng giá trị gần nhất từ client mà không kiểm tra nguồn
D. Thay thuộc tính thiếu bằng giá trị mặc định có quyền rộng
Đáp án đúng: B

Câu 15. Trong Cedar, nếu có policy permit phù hợp và policy forbid cũng phù hợp thì kết quả nào được áp dụng?
A. Kết quả phụ thuộc thứ tự ngẫu nhiên của bộ đánh giá
B. Forbid có hiệu lực ưu tiên và yêu cầu bị từ chối
C. Permit có hiệu lực ưu tiên nếu được khai báo trước
D. Policy được tạo gần nhất luôn ghi đè policy còn lại
Đáp án đúng: B

Câu 16. Schema của Cedar hỗ trợ kiểm tra điều gì khi xác thực policy?
A. Danh tính người dùng thật và quyền sở hữu thiết bị tại runtime
B. Tốc độ xử lý request và số lượng policy đang được nạp
C. Tính sẵn sàng của kho dữ liệu chứa thuộc tính bên ngoài
D. Kiểm tra kiểu entity, attribute và quan hệ action-resource
Đáp án đúng: D

Câu 17. Trong kiến trúc XACML, PDP và PEP phối hợp thế nào?
A. PEP soạn policy, PDP thu thập thuộc tính từ nguồn dữ liệu
B. PDP ghi audit, PEP phê duyệt thay đổi policy mới
C. PEP phát hành credential, PDP quản lý vòng đời tài khoản
D. PDP đánh giá policy, PEP thực thi quyết định trả về
Đáp án đúng: D

Câu 18. Với XACML deny-overrides, điều gì xảy ra khi một policy áp dụng trả Deny?
A. Kết quả tổng hợp là Deny theo quy tắc deny-overrides
B. Kết quả tổng hợp luôn là NotApplicable khi có xung đột
C. Kết quả tổng hợp lấy theo policy được đánh giá cuối cùng
D. Kết quả tổng hợp là Permit nếu một policy khác cho phép
Đáp án đúng: A

Câu 19. Với XACML permit-overrides, một Permit áp dụng ảnh hưởng kết quả ra sao?
A. Một Deny áp dụng luôn ghi đè mọi Permit trong nhóm
B. Mọi xung đột đều chuyển thành lỗi không xác định
C. Chỉ policy đầu tiên được đánh giá mới ảnh hưởng kết quả
D. Permit áp dụng có thể quyết định kết quả tổng hợp
Đáp án đúng: D

Câu 20. First-applicable combining algorithm có đặc điểm nào?
A. Ưu tiên mọi Deny bất kể thứ tự và phạm vi policy
B. Ưu tiên mọi Permit bất kể thứ tự và phạm vi policy
C. Chọn kết quả của policy đầu tiên có hiệu lực theo thứ tự đánh giá
D. Gộp tất cả kết quả bằng cách cộng trọng số quyền
Đáp án đúng: C

Câu 21. Trong XACML, obligation khác advice ở điểm nào?
A. Advice là hành động bắt buộc PEP phải hoàn tất trước response
B. Obligation là hành động PEP phải thực hiện theo quyết định
C. Obligation chỉ dùng để ghi log và không tác động thực thi
D. Advice luôn thay thế quyết định Permit hoặc Deny của PDP
Đáp án đúng: B

Câu 22. OPA thường đánh giá policy Rego dựa trên những đầu vào nào?
A. Dữ liệu input của yêu cầu cùng dữ liệu policy được nạp
B. Chỉ danh sách role đã đồng bộ từ hệ thống đăng nhập
C. Chỉ nội dung request HTTP mà không cần dữ liệu bổ sung
D. Chỉ biến môi trường của tiến trình đang chạy policy engine
Đáp án đúng: A

Câu 23. Trong Rego, nếu không rule nào tạo ra kết quả cho truy vấn quyết định thì điều gì có thể xảy ra?
A. Truy vấn có thể không trả giá trị và cho kết quả undefined
B. Mọi thuộc tính input được chuyển thành giá trị false
C. Bộ máy tự động cho phép để tránh làm gián đoạn dịch vụ
D. Bộ máy luôn chọn rule gần nhất với tên truy vấn
Đáp án đúng: A

Câu 24. Vì sao policy OPA nên định nghĩa rõ hành vi mặc định khi không có rule khớp?
A. Để mọi policy con tự động kế thừa quyền cao nhất
B. Để bỏ qua kiểm tra input khi policy không tìm thấy rule
C. Để kết quả undefined không bị hiểu nhầm là Permit
D. Để thay thế việc kiểm thử các trường hợp bị từ chối
Đáp án đúng: C

Câu 25. Khi đưa thuộc tính người dùng vào policy input, nguồn nào đáng tin cậy hơn?
A. Nguồn thuộc tính đã xác thực như identity provider
B. Header tùy ý do trình duyệt gửi mà không có chữ ký
C. Query parameter do người dùng tự chọn trên URL
D. Giá trị trong local storage mà client gửi kèm request
Đáp án đúng: A

Câu 26. Chính sách cần giới hạn truy cập tài liệu theo mức phân loại. Điều kiện nào hợp lý?
A. Clearance của chủ thể phải đáp ứng mức phân loại tài liệu
B. Người dùng phải truy cập từ cùng subnet với người tạo tài liệu
C. Tài liệu phải được tạo trong cùng ngày với phiên đăng nhập
D. Tên file phải chứa tên phòng ban của người yêu cầu
Đáp án đúng: A

Câu 27. Khi có nhiều policy cùng áp dụng, cách kiểm soát xung đột tốt nhất là gì?
A. Để từng PEP tự chọn cách diễn giải xung đột theo ý mình
B. Định nghĩa combining algorithm và kiểm thử policy giao nhau
C. Dựa vào thứ tự file policy mà không ghi lại quy ước
D. Cho phép policy mới nhất tự động ghi đè mọi quyết định cũ
Đáp án đúng: B

Câu 28. Nguyên tắc least privilege trong PBAC nên được thể hiện ra sao?
A. Cấp quyền đọc và ghi cho toàn bộ tài nguyên cùng tenant
B. Chỉ cấp hành động và phạm vi tài nguyên thật sự cần thiết
C. Cấp quyền quản trị tạm thời cho mọi phiên đã xác thực
D. Dùng một policy rộng để giảm số lượng quy tắc phải quản lý
Đáp án đúng: B

Câu 29. Separation of duties có thể được thực thi bằng policy như thế nào?
A. Ngăn cùng một chủ thể vừa tạo vừa phê duyệt giao dịch
B. Cho phép người tạo tự phê duyệt nếu đã có MFA
C. Chỉ kiểm tra vai trò của người dùng tại thời điểm đăng nhập
D. Bỏ kiểm tra người phê duyệt nếu giao dịch dưới hạn mức
Đáp án đúng: A

Câu 30. Delegated access an toàn cần giới hạn những yếu tố nào?
A. Toàn bộ quyền của người ủy quyền trong suốt vòng đời tài khoản
B. Chỉ địa chỉ IP hiện tại mà không giới hạn hành động
C. Chỉ tên người nhận ủy quyền và thời điểm bắt đầu
D. Giới hạn quyền, tài nguyên, thời hạn và quyền ủy quyền
Đáp án đúng: D

Câu 31. Break-glass access nên được thiết kế theo hướng nào?
A. Một tài khoản dùng chung không gắn với cá nhân cụ thể
B. Quyền quản trị thường trực cho nhóm trực vận hành
C. Ngoại lệ có hạn, được phê duyệt và ghi audit
D. Bỏ mọi ghi log để tránh chậm xử lý sự cố khẩn cấp
Đáp án đúng: C

Câu 32. Bộ kiểm thử policy tốt nên bao gồm những trường hợp nào?
A. Chỉ các request hợp lệ dự kiến sẽ được cho phép
B. Chỉ kiểm tra cú pháp policy khi biên dịch thành công
C. Chỉ kiểm tra hiệu năng với một chủ thể và một tài nguyên
D. Permit, deny, boundary, thiếu attribute và policy conflict
Đáp án đúng: D

Câu 33. Trước khi bật enforcement policy mới trên toàn hệ thống, cách rollout nào phù hợp?
A. Thay toàn bộ policy đồng thời và chỉ quan sát sau triển khai
B. Chạy shadow hoặc canary, so sánh kết quả trước khi mở rộng
C. Tắt audit trong lúc rollout để giảm lượng dữ liệu ghi nhận
D. Cho phép mặc định mọi request cho đến khi policy ổn định
Đáp án đúng: B

Câu 34. Cache quyết định truy cập cần chú ý điều gì?
A. Giữ kết quả Permit vô thời hạn để giảm tải cho PDP
B. Cache key gồm đủ thuộc tính quyết định và có invalidation
C. Bỏ tenant và context khỏi cache key để tăng tỷ lệ cache hit
D. Chỉ dùng subject ID làm key vì quyền không phụ thuộc tài nguyên
Đáp án đúng: B

Câu 35. Audit log cho quyết định PBAC nên ghi những dữ liệu nào?
A. Chỉ trạng thái Permit mà không lưu policy hoặc ngữ cảnh liên quan
B. Mật khẩu, secret và toàn bộ token xác thực của chủ thể
C. Ghi decision, policy version và subject-action-resource
D. Toàn bộ nội dung nhạy cảm của tài nguyên trong mỗi request
Đáp án đúng: C

Câu 36. Khi PDP tạm thời không khả dụng, PEP nên xử lý yêu cầu nhạy cảm thế nào?
A. Cho phép mọi request để duy trì tính sẵn sàng của ứng dụng
B. Bỏ qua policy và chỉ dựa vào trạng thái đăng nhập
C. Từ chối hoặc dùng cache còn hiệu lực theo chính sách
D. Tự tạo policy tạm với quyền rộng cho tới khi PDP phục hồi
Đáp án đúng: C

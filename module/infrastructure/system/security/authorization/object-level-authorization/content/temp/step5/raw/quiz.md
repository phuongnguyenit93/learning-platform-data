1. API đã xác thực người gọi. Trước khi trả một hồ sơ cụ thể, kiểm tra nào còn cần thiết?
A. Đối chiếu principal, action và object theo policy phía server.
B. Chỉ kiểm tra access token còn hạn và chữ ký token hợp lệ.
C. Kiểm tra ID hồ sơ có đúng định dạng mà API công bố.
D. Xác nhận request đến từ mạng nội bộ hoặc gateway đã biết.
Đáp án đúng: A

2. Một endpoint GET /orders/{id} trả đơn của người khác khi thay ID. Lỗi này là gì?
A. CSRF vì request đọc dữ liệu được gửi từ trình duyệt.
B. SSRF vì server truy cập tài nguyên theo địa chỉ do client chọn.
C. Broken authentication vì token của caller không được xác minh.
D. BOLA/IDOR vì thiếu kiểm tra quyền trên object được tham chiếu.
Đáp án đúng: D

3. Vì sao dùng UUID khó đoán cho resource ID vẫn không ngăn BOLA?
A. UUID không thể được dùng làm khóa chính trong hệ thống phân tán.
B. UUID có thể bị giải mã để suy ra trực tiếp owner của object.
C. ID khó đoán không thay quyết định quyền trên object.
D. UUID luôn tạo ra cùng một giá trị giữa các tenant khác nhau.
Đáp án đúng: C

4. Trong API đa tenant, tenant scope nên được lấy từ đâu khi truy vấn object?
A. Từ query parameter do client gửi trong mỗi request.
B. Từ principal hoặc context tin cậy đã được xác thực phía server.
C. Từ trường tenantId trong body để client chọn workspace mong muốn.
D. Từ header bất kỳ vì gateway sẽ tự động xác minh giá trị đó.
Đáp án đúng: B

5. Cách nào ngăn endpoint đọc object theo ID của tenant khác?
A. Đưa tenant và quyền caller vào điều kiện truy vấn.
B. Tải object trước rồi chỉ ẩn tên tenant trong response trả về.
C. Kiểm tra ID có tiền tố giống tenant hiện tại trước khi truy vấn.
D. Mã hóa ID trong URL rồi giải mã sau khi đọc bản ghi.
Đáp án đúng: A

6. Khi cập nhật object, điểm nào cần được kiểm tra trước khi ghi thay đổi?
A. Chỉ kiểm tra người dùng có role editor ở cấp ứng dụng.
B. Chỉ kiểm tra object tồn tại và chưa bị soft delete.
C. Kiểm tra owner sau khi lưu để có thể rollback nếu sai.
D. Kiểm tra quyền trên đúng object trước khi ghi.
Đáp án đúng: D

7. Với endpoint liệt kê object, cách áp dụng authorization nào phù hợp?
A. Lấy toàn bộ dữ liệu rồi lọc object bị cấm ở giao diện client.
B. Phân trang toàn bộ trước rồi bỏ các object không được phép.
C. Lọc tenant/ownership trong query trước phân trang.
D. Trả tổng số bản ghi toàn hệ thống để client tự lọc kết quả.
Đáp án đúng: C

8. Một invoice thuộc order của tenant A. User có quyền xem order nhưng không có quyền xem invoice. Cần làm gì?
A. Kiểm tra quyền invoice và quan hệ với order.
B. Cho phép vì quyền đọc order tự động bao gồm mọi invoice liên quan.
C. Chỉ kiểm tra user thuộc tenant của order cha là đủ.
D. Dựa vào việc invoice ID được gửi trong URL của order hợp lệ.
Đáp án đúng: A

9. Một batch update nhận 50 object ID. Cách kiểm tra quyền nào an toàn?
A. Chỉ kiểm tra object đầu tiên rồi xử lý toàn bộ batch.
B. Authorize từng object; quy định rõ xử lý partial.
C. Kiểm tra user có quyền update chung trên collection hay không.
D. Chỉ kiểm tra số lượng ID để giới hạn kích thước request.
Đáp án đúng: B

10. GraphQL query trả nested object từ resolver. Authorization nên được đặt ở đâu?
A. Chỉ ở giao diện trước khi gửi GraphQL query.
B. Chỉ ở gateway dựa trên tên operation của GraphQL.
C. Chỉ ở root resolver vì mọi field con đều kế thừa quyền.
D. Tại resolver hoặc policy layer cho từng object và field nhạy cảm.
Đáp án đúng: D

11. Endpoint export CSV cần xử lý quyền object thế nào?
A. Bỏ kiểm tra vì export là tác vụ nội bộ do user khởi tạo.
B. Chỉ kiểm tra role export mà không xét từng bản ghi được xuất.
C. Áp dụng cùng phạm vi object và field được phép như API đọc.
D. Dùng quyền của service account để xuất mọi tenant rồi lọc sau.
Đáp án đúng: C

12. Object-level authorization khác field-level authorization ở điểm nào?
A. Object-level chỉ áp dụng cho database, field-level chỉ áp dụng UI.
B. Object-level kiểm soát object; field-level giới hạn thuộc tính.
C. Object-level xác thực user; field-level xác thực chữ ký request.
D. Hai khái niệm giống nhau và có thể dùng thay thế hoàn toàn.
Đáp án đúng: B

13. Client gửi ownerId mới trong PATCH body. Server nên xử lý thế nào?
A. Chấp nhận nếu caller đã có quyền update object hiện tại.
B. Chấp nhận khi ownerId mới thuộc cùng tenant với caller.
C. Ghi ownerId trước rồi kiểm tra policy ở request tiếp theo.
D. Chỉ đổi owner qua luồng riêng có kiểm tra và audit.
Đáp án đúng: D

14. Cache response object dùng cho nhiều user nên chọn cache key ra sao?
A. Chỉ dùng object ID vì response luôn giống nhau với mọi caller.
B. Dùng URL path và thời điểm tạo response làm cache key.
C. Thêm principal/tenant vào key hoặc cache dữ liệu chung.
D. Bỏ cache key để mọi request dùng cùng một bản response mới nhất.
Đáp án đúng: C

15. Owner của object có thể đổi đồng thời với request update. Cách nào giảm TOCTOU?
A. Kiểm tra quyền và ghi trong cùng transaction.
B. Kiểm tra owner trước request rồi tin kết quả trong thời gian dài.
C. Đọc owner từ cache và ghi object ở một transaction khác.
D. Chỉ khóa giao diện khi có hai người cùng mở object.
Đáp án đúng: A

16. Khi nào API có thể trả 404 thay cho 403 với object ngoài quyền?
A. Khi policy không muốn tiết lộ object có tồn tại.
B. Khi object tồn tại nhưng caller cần biết chính xác owner.
C. Khi mọi lỗi authorization phải được hiển thị thành lỗi server.
D. Khi ID không đúng định dạng và chưa được truy vấn.
Đáp án đúng: A

17. Vì sao không nên coi resource ID là credential để cấp quyền?
A. ID thường được tạo từ hash và không thể thay đổi theo thời gian.
B. ID là tham chiếu; quyền phải dựa trên principal và policy.
C. ID luôn được công khai nên không thể dùng trong URL API.
D. ID chỉ phù hợp cho dữ liệu đọc và không dùng cho cập nhật.
Đáp án đúng: B

18. Khi chuyển quyền sở hữu một document, điều gì cần được đánh giá lại?
A. Chỉ cập nhật owner label trong giao diện người dùng.
B. Chỉ thay ID của document để tránh URL cũ còn hoạt động.
C. Chỉ xóa cache phía client mà không thay đổi ACL lưu trữ.
D. Đánh giá lại quyền của hai owner và quan hệ chia sẻ.
Đáp án đúng: D

19. Một tài liệu được chia sẻ qua ACL rồi chủ sở hữu thu hồi quyền. Hệ thống cần làm gì?
A. Chỉ ẩn tài liệu trong danh sách của người được chia sẻ.
B. Cập nhật ACL và vô hiệu cache/link còn hiệu lực.
C. Đổi document ID để các client không còn tìm thấy tài liệu.
D. Giữ quyền cũ tới khi người nhận đăng xuất khỏi hệ thống.
Đáp án đúng: B

20. Service A gọi Service B thay mặt user. B chỉ thấy service identity. Rủi ro nào cần tránh?
A. B coi mọi request nội bộ là request của administrator.
B. A tự ký lại request bằng một key mới cho mỗi endpoint.
C. B thực thi quyền service mà bỏ qua subject gốc.
D. B từ chối mọi request vì service identity không phải con người.
Đáp án đúng: C

21. Một background export được xếp hàng khi user còn quyền nhưng chạy sau khi quyền bị thu hồi. Worker nên làm gì?
A. Kiểm tra lại quyền khi worker thực thi job.
B. Luôn dùng quyền tại thời điểm enqueue dù quyền đã bị thu hồi.
C. Chạy bằng quyền admin để bảo đảm job không bị gián đoạn.
D. Chỉ kiểm tra user ID tồn tại mà không kiểm tra trạng thái quyền.
Đáp án đúng: A

22. Presigned URL cho object riêng tư nên được giới hạn như thế nào?
A. Cho phép URL dùng vô thời hạn để tránh lỗi tải lại.
B. Chỉ dựa vào độ dài URL để ngăn người khác đoán được.
C. Dùng cùng URL cho toàn bộ object thuộc một tenant.
D. Giới hạn object, action, expiry và khả năng thu hồi.
Đáp án đúng: D

23. Database row-level security hỗ trợ object authorization theo cách nào?
A. Thay thế mọi kiểm tra quyền ở API và các dịch vụ khác.
B. Tự xác định danh tính người dùng cuối từ địa chỉ IP.
C. Lọc tại tầng dữ liệu theo context tin cậy của request.
D. Mã hóa row để user chỉ đọc được bản ghi thuộc sở hữu.
Đáp án đúng: C

24. Vì sao tenantId trong request body không nên là nguồn quyết định duy nhất?
A. Client có thể gửi tenantId ở nhiều định dạng JSON khác nhau.
B. TenantId luôn thay đổi sau mỗi lần user đăng nhập.
C. Body chỉ chứa dữ liệu nghiệp vụ và không thể có context.
D. Caller có thể sửa giá trị để yêu cầu truy cập tenant khác.
Đáp án đúng: D

25. Một user thuộc group được chia sẻ tài liệu. Điều kiện nào cần kiểm tra?
A. Chỉ cần tên group xuất hiện trong token của user.
B. Kiểm tra membership và quyền tài liệu còn hiệu lực.
C. Chỉ cần tài liệu có cùng owner với group được chia sẻ.
D. Chỉ cần user đã từng mở tài liệu trong một phiên trước.
Đáp án đúng: B

26. Object đã soft delete nhưng API vẫn trả được khi biết ID. Cần kiểm tra gì?
A. Chỉ kiểm tra ID có còn trong cache của ứng dụng.
B. Chỉ kiểm tra object có file đính kèm hay không.
C. Kiểm tra lifecycle và policy của object đã xóa.
D. Chỉ kiểm tra user có role đọc collection hay không.
Đáp án đúng: C

27. WebSocket gửi event chứa object tới client đã mở kết nối từ trước. Cần làm gì?
A. Chỉ authorize lúc handshake và giữ quyền suốt kết nối.
B. Kiểm tra quyền event/object và khi quan hệ đổi.
C. Gửi mọi event rồi để client tự quyết định có hiển thị không.
D. Chỉ kiểm tra session còn sống, không cần xét resource.
Đáp án đúng: B

28. User được xem object nhưng không được xem trường internalNotes. Cách bảo vệ phù hợp?
A. Áp dụng field policy khi serialize hoặc truy xuất.
B. Ẩn trường bằng CSS nhưng vẫn gửi giá trị trong JSON response.
C. Đổi tên field để client không biết thuộc tính nhạy cảm.
D. Chỉ bỏ trường khỏi trang chi tiết, giữ nguyên ở API export.
Đáp án đúng: A

29. Search API chỉ trả object được phép nhưng tổng số kết quả là tổng toàn hệ thống. Rủi ro gì?
A. Metadata về số lượng vẫn có thể tiết lộ dữ liệu.
B. Không có rủi ro vì response không chứa object ngoài quyền.
C. Chỉ ảnh hưởng hiệu năng do count query chạy trên nhiều bảng.
D. Chỉ là lỗi giao diện vì số lượng không phải dữ liệu tài nguyên.
Đáp án đúng: A

30. API trả 403 cho ID tồn tại và 404 cho ID không tồn tại. Điều gì có thể bị lộ?
A. Loại database đang lưu trữ object được truy vấn.
B. Khóa mã hóa dùng để bảo vệ object trên storage.
C. Phiên bản HTTP mà client dùng để gửi request.
D. Sự tồn tại của object qua khác biệt phản hồi.
Đáp án đúng: D

31. Bộ kiểm thử BOLA nên ưu tiên trường hợp nào?
A. Chỉ kiểm tra admin truy cập object của chính admin.
B. Chỉ kiểm tra ID hợp lệ và response có schema đúng.
C. Thử user khác tenant/owner với từng action đọc và ghi.
D. Chỉ kiểm tra user chưa đăng nhập gọi endpoint công khai.
Đáp án đúng: C

32. Một batch endpoint cho phép xử lý thành công một phần. Điều gì cần được bảo đảm?
A. Nếu một ID bị cấm thì tự động cho phép các ID còn lại.
B. Chỉ trả tổng số thành công mà không lưu kết quả từng object.
C. Authorize từng object và không rò rỉ kết quả chéo.
D. Bỏ qua ID không hợp lệ và cập nhật mọi ID còn lại.
Đáp án đúng: C

33. Admin hỗ trợ có quyền truy cập object của khách hàng. Kiểm soát nào phù hợp?
A. Cho phép admin đọc mọi object mà không cần lưu dấu vết.
B. Áp dụng quyền hỗ trợ có phạm vi, lý do và audit phù hợp.
C. Dùng ID ngẫu nhiên để admin không thể truy cập nhầm object.
D. Chỉ cho phép admin truy cập qua giao diện và không qua API.
Đáp án đúng: B

34. Audit log cho quyết định object authorization nên ghi gì?
A. Chỉ ghi HTTP status để tránh lưu nhiều metadata.
B. Ghi toàn bộ secret và dữ liệu object để tái hiện request.
C. Chỉ ghi user agent vì có thể suy ra danh tính từ trình duyệt.
D. Ghi subject, action, resource, decision và context phù hợp.
Đáp án đúng: D

35. Authorization service tạm thời không phản hồi khi API cần quyết định truy cập. Hành vi nào an toàn?
A. Cho phép request để duy trì availability cho mọi người dùng.
B. Fail closed hoặc dùng fallback đã được kiểm soát.
C. Bỏ qua policy cho request GET và chỉ chặn request ghi.
D. Dùng kết quả allow gần nhất mà không xét thời hạn cache.
Đáp án đúng: B

36. Ma trận kiểm thử object authorization nên được tổ chức theo cách nào?
A. Kết hợp principal, action, owner, tenant và trạng thái.
B. Chỉ liệt kê endpoint và xác nhận mọi request trả mã 200.
C. Chỉ kiểm tra từng role riêng lẻ mà không thay object ID.
D. Chỉ kiểm tra UI theo từng nhóm người dùng đã đăng nhập.
Đáp án đúng: A

Bạn phân biệt xác thực danh tính và phân quyền truy cập như thế nào trong một ứng dụng web?
Trong một quyết định cấp quyền, chủ thể, hành động, tài nguyên và ngữ cảnh đại diện cho những yếu tố nào?
Bạn mô hình hóa principal và subject ra sao khi người dùng hành động thay mặt một dịch vụ hoặc tổ chức?
Những thuộc tính ngữ cảnh nào có thể làm thay đổi quyết định cấp quyền dù vai trò người dùng không đổi?
Vì sao hệ thống nên từ chối mặc định khi không có chính sách cho phép rõ ràng?
Bạn sẽ đặt ranh giới trách nhiệm giữa authentication middleware và authorization layer như thế nào?
Trong luồng đăng nhập thành công, những bước nào vẫn cần diễn ra trước khi cho phép truy cập một tài nguyên cụ thể?
Bạn phân biệt identity, role, permission và scope như thế nào khi thiết kế API?
Những rủi ro nào phát sinh nếu ứng dụng tin trực tiếp vào vai trò do client gửi lên?
Bạn xác định nguồn đáng tin cậy cho thuộc tính người dùng, tài nguyên và môi trường bằng cách nào?
Bạn thiết kế mô hình RBAC từ người dùng, vai trò và quyền thao tác như thế nào?
Khi nào nên dùng phân cấp vai trò và làm sao kiểm soát quyền được kế thừa?
Bạn sẽ xác định quyền tối thiểu cho từng vai trò dựa trên nhiệm vụ công việc ra sao?
Những dấu hiệu nào cho thấy hệ thống RBAC đang gặp role explosion?
Bạn xử lý yêu cầu một người dùng có nhiều vai trò chồng lấn như thế nào?
Bạn áp dụng separation of duties để ngăn một người vừa tạo vừa phê duyệt giao dịch ra sao?
Trong tình huống cần nâng quyền tạm thời, bạn sẽ thiết kế thời hạn và quy trình thu hồi như thế nào?
Bạn đánh giá việc gán vai trò theo nhóm tổ chức hoặc phòng ban có thể gây thừa quyền ở đâu?
Bạn mô hình hóa ABAC bằng thuộc tính subject, resource, action và environment như thế nào?
Bạn xác định nguồn gốc, độ tin cậy và độ mới của thuộc tính dùng trong chính sách ABAC ra sao?
Khi một thuộc tính bắt buộc bị thiếu, chính sách ABAC nên phản ứng thế nào và vì sao?
Bạn thiết kế thứ tự ưu tiên giữa các chính sách allow và deny khi nhiều rule cùng khớp ra sao?
Bạn xử lý xung đột giữa thuộc tính của người dùng và thuộc tính của tài nguyên như thế nào?
Trong trường hợp nào mô hình kết hợp RBAC và ABAC phù hợp hơn việc chỉ dùng một mô hình?
Bạn kiểm soát rủi ro giả mạo thuộc tính môi trường như địa chỉ IP, thiết bị hoặc vị trí bằng cách nào?
Bạn cân nhắc hiệu năng và khả năng cache khi đánh giá chính sách ABAC phức tạp ra sao?
Bạn kiểm tra quyền trên từng đối tượng dữ liệu như thế nào khi API nhận một object ID từ client?
Một lỗi BOLA hoặc IDOR có thể xuất hiện trong luồng đọc và cập nhật tài nguyên ra sao?
Vì sao kiểm tra người dùng đã đăng nhập vẫn chưa đủ để chứng minh họ được truy cập một bản ghi cụ thể?
Bạn xác minh quyền sở hữu tài nguyên và quyền được chia sẻ cho người khác như thế nào?
Bạn lấy tenant context từ nguồn nào để tránh client tự đổi tenant ID trong request?
Bạn thiết kế ranh giới cô lập dữ liệu giữa các tenant ở tầng API và tầng lưu trữ như thế nào?
Với endpoint trả về danh sách, bạn bảo đảm mọi bản ghi trong kết quả đều thuộc phạm vi được phép ra sao?
Bạn xử lý authorization cho thao tác hàng loạt khi một số object được phép và một số object bị từ chối như thế nào?
Bạn kiểm tra quyền trên tài nguyên con khi quyền truy cập tài nguyên cha đã được cấp ra sao?
Bạn mô hình hóa quyền chia sẻ theo quan hệ giữa người dùng, nhóm và tài nguyên như thế nào?
Vì sao giao diện ẩn nút hoặc menu không thể thay thế kiểm tra quyền ở server?
Bạn đặt enforcement point ở middleware, controller, service hay repository theo nguyên tắc nào?
Bạn giải thích vai trò của Policy Enforcement Point và Policy Decision Point trong một kiến trúc authorization như thế nào?
Policy Administration Point và Policy Information Point có thể tham gia quy trình quản lý chính sách ra sao?
Bạn bảo đảm mọi đường gọi API, gồm REST, GraphQL và RPC, đều thực thi cùng một chính sách như thế nào?
Bạn sử dụng row-level security ở cơ sở dữ liệu như một lớp phòng vệ bổ sung ra sao?
Với background job chạy thay mặt người dùng, bạn truyền và xác minh quyền gốc như thế nào?
Bạn thiết kế danh tính và quyền tối thiểu cho giao tiếp giữa các service như thế nào?
Cache quyết định authorization có thể tạo ra lỗi bảo mật nào khi quyền người dùng vừa bị thu hồi?
Bạn xử lý việc role hoặc permission trong JWT đã cũ trước thời điểm token hết hạn như thế nào?
Bạn phân biệt OAuth scope với role nội bộ của ứng dụng trong quyết định cấp quyền ra sao?
Khi cấp signed URL cho tải tệp, bạn giới hạn tài nguyên, hành động và thời hạn sử dụng như thế nào?
Bạn thiết kế hành vi fail-closed khi policy engine không phản hồi hoặc trả kết quả không xác định ra sao?
Bạn xử lý timeout hoặc lỗi kết nối tới dịch vụ quyết định chính sách mà vẫn bảo vệ tài nguyên như thế nào?
Bạn bảo đảm quyền được kiểm tra lại khi một tác vụ bất đồng bộ chạy lâu sau khi người dùng khởi tạo ra sao?
Bạn ánh xạ HTTP method và hành động nghiệp vụ thành permission như thế nào để tránh cấp quyền quá rộng?
Bạn quản lý policy-as-code qua review, version control và quy trình phê duyệt như thế nào?
Bạn triển khai thay đổi chính sách theo từng giai đoạn để phát hiện tác động ngoài dự kiến ra sao?
Bạn ghi audit event cho quyết định allow hoặc deny với những trường thông tin nào?
Bạn thiết kế audit log để hỗ trợ điều tra mà không vô tình lưu token hoặc dữ liệu nhạy cảm như thế nào?
Bạn tổ chức quy trình break-glass cho truy cập khẩn cấp và kiểm soát hậu kiểm ra sao?
Bạn thiết kế delegation để người dùng ủy quyền hành động cho người khác mà vẫn giữ được dấu vết trách nhiệm như thế nào?
Bạn thu hồi quyền khẩn cấp trên nhiều service và cache trong hệ thống phân tán ra sao?
Bạn tổ chức rà soát định kỳ quyền của nhân viên, service account và nhóm đặc quyền như thế nào?
Bạn xây dựng ma trận kiểm thử authorization theo chủ thể, hành động, tài nguyên và ngữ cảnh ra sao?
Bạn thiết kế negative test để phát hiện truy cập ngang quyền và leo thang đặc quyền như thế nào?
Bạn kiểm thử ranh giới tenant bằng dữ liệu và danh tính giả lập ra sao?
Bạn xác minh cache, token refresh và thu hồi quyền trong integration test như thế nào?
Bạn dùng property-based testing hoặc fuzzing để tìm các trường hợp vượt qua policy ngoài dự kiến ra sao?
Bạn theo dõi tỷ lệ allow, deny và các mẫu truy cập bất thường mà không tạo cardinality telemetry quá lớn như thế nào?

Đội kỹ thuật muốn biến một trang tổng hợp liên kết thành Internal Developer Platform thực thụ; thay đổi nào phản ánh đúng tư duy nền tảng như một sản phẩm nội bộ?
A. Ưu tiên thống nhất portal và hướng dẫn đăng ký tài nguyên qua kênh hỗ trợ.
B. Tập trung chuẩn hóa công cụ lập trình, còn mỗi đội tự xây quy trình cấp phát.
C. Cung cấp năng lực tự phục vụ có hợp đồng ổn định và cải tiến từ phản hồi.
D. Tái sử dụng một pipeline CI/CD chung làm giao diện trung tâm cho toàn tổ chức.
Đáp án đúng: C

Sau khi hai nhóm đổi trách nhiệm vận hành, service catalog vẫn hiển thị chủ sở hữu cũ; cách tổ chức dữ liệu nào giúp khắc phục tận gốc?
A. Duy trì định danh dịch vụ ổn định, nguồn owner có thẩm quyền và lịch đồng bộ.
B. Ưu tiên xác định owner từ người commit mới nhất, rồi đồng bộ theo lần build.
C. Đưa tên nhóm sở hữu vào dashboard và cập nhật khi có yêu cầu hỗ trợ.
D. Lấy owner từ pipeline triển khai cuối cùng, dùng thay thế metadata của repo.
Đáp án đúng: A

Một nhóm cần tạo dịch vụ mới theo golden path với ít thao tác thủ công; kết quả nào thể hiện template tự phục vụ đầy đủ nhất?
A. Cấp repository và để từng đội bổ sung kiểm thử, vận hành sau khi phát hành.
B. Cấp cluster và dashboard, còn cấu hình bảo mật do ứng dụng thiết lập riêng.
C. Sinh skeleton mã nguồn, còn service catalog được cập nhật bằng biểu mẫu.
D. Tạo repo, pipeline, catalog và quan sát theo template có chính sách kiểm chứng.
Đáp án đúng: D

API cấp phát cơ sở dữ liệu của IDP có thể nhận lại cùng một yêu cầu khi client timeout; thiết kế nào tránh tạo tài nguyên trùng lặp?
A. Dùng idempotency key, lưu trạng thái cấp phát và cung cấp API truy vấn tiến độ.
B. Giữ kết nối HTTP mở đến khi tài nguyên sẵn sàng, tự lặp request khi timeout.
C. Mỗi lần nhận retry tạo một tài nguyên mới, dọn trùng theo công việc định kỳ.
D. Trả mã thành công lúc tiếp nhận yêu cầu, ghi log khi quá trình cấp phát kết thúc.
Đáp án đúng: A

Khi một kỹ sư sửa cấu hình cloud trực tiếp khiến tài nguyên lệch khỏi cấu hình nền tảng đã phê duyệt, IDP nên xử lý drift ra sao?
A. Cho phép sửa console trước, đồng bộ IaC định kỳ sau khi kiểm tra chi phí.
B. Giữ snapshot cấu hình sau triển khai làm nguồn điều chỉnh cho lần tiếp theo.
C. Lưu cấu hình mong muốn trong IaC, kiểm tra drift và đối soát qua quy trình duyệt.
D. Để mỗi đội tự chọn công cụ cập nhật và chỉ tập hợp trạng thái cuối cùng.
Đáp án đúng: C

Một golden path cần tạo môi trường development và production từ cùng mẫu nhưng bảo đảm lỗi cấu hình không lan giữa hai môi trường; thiết kế nào phù hợp?
A. Chia tên resource theo môi trường nhưng giữ chung credential và backend state.
B. Cố định cùng hạn mức, tài khoản và pipeline để giảm khác biệt môi trường.
C. Tạo từng môi trường từ template độc lập nhưng chia sẻ toàn bộ secret.
D. Dùng template chung nhưng tách quyền, secret, state và quota theo môi trường.
Đáp án đúng: D

Một đội yêu cầu mở cơ sở dữ liệu production ra Internet qua self-service API, trái với chính sách an toàn mặc định; cơ chế kiểm soát nào phù hợp nhất?
A. Kiểm tra policy as code ở API lẫn bước cấp phát, từ chối hoặc xin ngoại lệ.
B. Cấp phát trước rồi đưa cấu hình cần xem xét vào báo cáo tuân thủ định kỳ.
C. Chỉ chạy rule kiểm tra trong template, cho phép gọi API trực tiếp ngoài rule.
D. Ghi log các cấu hình rủi ro và giao trách nhiệm khắc phục cho nhóm ứng dụng.
Đáp án đúng: A

Nhiều workflow tự phục vụ cần gọi API cloud để cấp tài nguyên cho các nhóm khác nhau; nền tảng nên quản lý danh tính thực thi thế nào?
A. Cấp token ngắn hạn theo workload, hạn chế phạm vi quyền và ghi audit trail.
B. Dùng một token quản trị chung trên runner, quay vòng theo lịch của nhóm.
C. Đặt credential cloud trong template rồi mã hóa repo bằng quyền truy cập nhóm.
D. Gắn quyền quản trị tài nguyên cho mọi người dùng đã đăng nhập portal.
Đáp án đúng: A

Golden path của một nhóm được nâng cấp với thay đổi không tương thích cho dịch vụ đã tạo trước đó; chiến lược tiến hóa template nào an toàn nhất?
A. Nâng template cho toàn bộ repo ngay khi có bản mới, xử lý lỗi theo ticket.
B. Phát hành bản template có version, kiểm thử tương thích và kế hoạch chuyển đổi.
C. Chỉ giữ một template đang phát triển, dự án cũ có thể tự sửa khi lỗi.
D. Đóng băng template của dịch vụ đã tạo và tránh thay đổi bản template gốc.
Đáp án đúng: B

Ban lãnh đạo hỏi IDP có thực sự cải thiện trải nghiệm phát triển thay vì chỉ tăng lượt dùng portal; bộ chỉ số nào trả lời sát nhất?
A. Đếm lượt truy cập portal và số biểu mẫu khởi tạo được hoàn thành.
B. Theo dõi CPU của portal và số lần gọi API để thay thế đánh giá trải nghiệm.
C. Kết hợp thời gian tạo dịch vụ, lead time, tỷ lệ tự phục vụ và phản hồi dev.
D. Đo số template đang có và tổng tài nguyên đã được hệ thống cấp phát.
Đáp án đúng: C

Một workflow Scaffolder đã tạo repository và service account nhưng thất bại khi cấp database; thiết kế khôi phục nào đáng tin cậy nhất?
A. Thử lại cả luồng cấp phát và tự tạo tài nguyên mới nếu bước trước timeout.
B. Đánh dấu thành công sau khi tạo repo, phần còn lại giao đội ứng dụng xử lý.
C. Lưu tiến độ từng bước, retry idempotent và bù trừ tài nguyên đã cấp sai.
D. Dừng workflow khi lỗi, để người dùng xóa các tài nguyên rồi chạy lại.
Đáp án đúng: C

Một tổ chức dùng chung IDP cho hàng trăm nhóm, có nhóm gửi số lượng lớn yêu cầu cấp phát và làm chậm nhóm khác; kiểm soát nào phù hợp?
A. Tăng quota mặc định cho mọi nhóm sau mỗi lần hệ thống từ chối yêu cầu.
B. Kiểm quota trên portal frontend và tin rằng mọi yêu cầu đều đi qua giao diện.
C. Để provider cloud kiểm soát quota chung mà không phân biệt nhóm sử dụng.
D. Kiểm quota và rate limit theo nhóm tại API và worker, có chỉ số sử dụng.
Đáp án đúng: D

Nền tảng cho phép nhiều nhóm sử dụng template và action có quyền tạo repository hoặc tài nguyên cloud; biện pháp nào giảm rủi ro chuỗi cung ứng?
A. Lấy template và plugin từ nhánh mặc định để nhận bản sửa mới tức thì.
B. Pin phiên bản template và dependency, kiểm chứng nguồn và quyền chạy action.
C. Dùng service token đặc quyền rộng cho mọi template nhằm hạn chế lỗi cấp phép.
D. Tăng tần suất scan tài nguyên đã chạy thay cho kiểm tra nguồn template.
Đáp án đúng: B

Người dùng báo thao tác tạo dịch vụ của IDP thường thất bại sau vài phút nhưng portal vẫn hoạt động; tín hiệu quan sát nào hữu ích nhất để tìm nguyên nhân?
A. Theo dõi số lượt đăng nhập portal và tổng số artifact lưu ở registry.
B. Đo thành công và độ trễ từng bước cấp phát, kèm correlation ID và lỗi.
C. Theo dõi chi phí node nền tảng mà không cần ghi trạng thái workflow.
D. Chỉ dùng log của provider cloud để suy ra mọi lỗi của quy trình tự phục vụ.
Đáp án đúng: B

Một nhóm có nhu cầu hạ tầng hợp lệ nhưng nằm ngoài golden path chuẩn; cách xử lý nào cân bằng tự phục vụ với quản trị rủi ro?
A. Buộc mọi ứng dụng dùng template nguyên trạng và chỉ xem xét yêu cầu khác biệt sau phát hành.
B. Cho phép đội ứng dụng tạm tắt policy, ghi chú nguyên nhân vào backlog.
C. Trao quyền admin tạm thời để đội ứng dụng tự vượt qua bước kiểm tra.
D. Tạo luồng ngoại lệ có phê duyệt, thời hạn và trách nhiệm, rồi cải tiến golden path.
Đáp án đúng: D

Khi self-service API cấp phát tài nguyên gặp lỗi quota từ nhà cung cấp, trách nhiệm vận hành IDP nên được thiết kế như thế nào?
A. Chuyển ticket lỗi cấp phát cho đội ứng dụng ngay khi provider trả lỗi.
B. Công bố SLO, chủ sở hữu, trạng thái lỗi và quy trình escalation của nền tảng.
C. Ẩn chi tiết lỗi từ API và hướng dẫn người dùng thao tác lại sau một lúc.
D. Giữ một kênh chat tự hỗ trợ, chỉ xử lý ticket nếu sự cố gây mất dữ liệu tài nguyên cloud.
Đáp án đúng: B

Trong hệ thống có hàng trăm máy ảo và dịch vụ cloud, cách tổ chức inventory nào hỗ trợ truy vết chủ sở hữu và vòng đời tài nguyên tốt nhất?
A. Duy trì danh sách địa chỉ IP và sửa tay khi có đợt thay đổi tài nguyên.
B. Ghi định danh, môi trường, chủ sở hữu và đối chiếu định kỳ với cloud.
C. Ghi hostname của mỗi nhóm vào tài liệu riêng và tổng hợp khi kiểm toán.
D. Lấy dữ liệu quét mạng làm danh sách chuẩn cho toàn bộ vòng đời máy chủ.
Đáp án đúng: B

Khi tổ chức hạ tầng staging và production bằng IaC, phương án nào cô lập quyền và trạng thái để tránh thay đổi nhầm môi trường?
A. Tách state, tài khoản triển khai và cấu hình cho từng môi trường độc lập.
B. Dùng state chung nhưng đặt thư mục mã khác nhau cho từng môi trường.
C. Dùng chung tài khoản cấp quyền cao và đổi biến môi trường khi chạy.
D. Dùng một workspace triển khai và đổi tiền tố tên tài nguyên theo môi trường.
Đáp án đúng: A

Điểm khác biệt cốt lõi của mô hình khai báo trạng thái mong muốn so với chuỗi lệnh tạo tài nguyên thuần túy là gì?
A. Mỗi lần chạy tạo lại tài nguyên để bảo đảm tất cả cấu hình được mới hóa.
B. Không cần đọc trạng thái hiện tại khi mã khai báo đã có đủ thuộc tính.
C. Thứ tự từng lệnh thực thi là nguồn quyết định duy nhất cho kết quả.
D. So sánh trạng thái thực với mục tiêu rồi áp dụng phần chênh lệch.
Đáp án đúng: D

Vì sao một bước quản lý cấu hình cần có tính idempotent khi được chạy lặp lại trên cùng máy chủ?
A. Tạo bản sao cấu hình ở mỗi lần chạy nhằm giữ toàn bộ lịch sử triển khai.
B. Bỏ qua kiểm tra trạng thái hiện có để mỗi lần thực thi nhanh hơn.
C. Chạy lại không tạo thay đổi thừa nếu hệ thống đã đạt trạng thái đích.
D. Luôn khởi động lại dịch vụ nhằm bảo đảm giá trị mới được tải lại.
Đáp án đúng: C

Một kế hoạch IaC bất ngờ dự kiến xóa volume chứa dữ liệu quan trọng, quy trình nào phù hợp nhất trước khi apply?
A. Giảm số tác vụ song song rồi apply lại để tránh xóa tài nguyên ngoài ý muốn.
B. Đổi tên volume trong cấu hình để áp dụng thay đổi với tài nguyên mới.
C. Tạm dừng, kiểm tra diff và phụ thuộc, sửa rồi duyệt kế hoạch mới.
D. Bỏ volume khỏi file state rồi apply lại để không phát sinh thao tác xóa.
Đáp án đúng: C

Vì sao cần bảo vệ và khóa thao tác ghi đồng thời trên state của một công cụ Infrastructure as Code?
A. State chỉ lưu nhãn tài nguyên nên cần khóa để tránh trùng tên khi build.
B. State nên được sao chép cục bộ rồi hợp nhất bằng tay sau mỗi lần apply.
C. State luôn được ghi đè để tránh phải so sánh với tài nguyên hiện hữu.
D. State có thể chứa bí mật; ghi đồng thời dễ làm sai lệch dữ liệu.
Đáp án đúng: D

Nếu có người chỉnh firewall trực tiếp trong cloud console khiến hạ tầng lệch so với IaC, cách xử lý drift nào phù hợp nhất?
A. Xóa rồi tạo lại ngay tài nguyên để bỏ mọi thay đổi không nằm trong mã.
B. Cập nhật state bằng tay và giữ nguyên mã khai báo để tránh chạy lại.
C. Chỉ ghi nhận drift và không điều chỉnh vì thay đổi trực tiếp thường an toàn.
D. Xác minh ý định thay đổi, đánh giá tác động rồi hòa giải qua mã được duyệt.
Đáp án đúng: D

Khi IaC tạo dịch vụ phụ thuộc vào cơ sở dữ liệu và subnet, cách thể hiện thứ tự triển khai nào đáng tin cậy nhất?
A. Chèn thời gian chờ cố định giữa các bước tạo từng thành phần liên quan.
B. Dùng tham chiếu giữa tài nguyên để công cụ lập đồ thị phụ thuộc.
C. Tạo tất cả tài nguyên song song rồi chạy lại những bước thất bại.
D. Sắp xếp các resource trong file theo thứ tự mong muốn khi thực thi.
Đáp án đúng: B

Một pipeline tự động cần cấp phát hạ tầng cloud, phương án xác thực nào phù hợp nguyên tắc đặc quyền tối thiểu?
A. Dùng danh tính ngắn hạn với quyền giới hạn trên tài nguyên cần tạo.
B. Dùng khóa quản trị dài hạn để pipeline không bị chặn bởi thiếu quyền.
C. Dùng tài khoản chung và kiểm soát quyền thông qua review của nhóm.
D. Dùng quyền toàn cục khi triển khai rồi thu hồi sau khi job kết thúc.
Đáp án đúng: A

Cách nào giúp đưa mật khẩu dịch vụ vào quá trình triển khai IaC mà hạn chế nguy cơ lộ thông tin?
A. Dùng mã hóa Base64 trước khi commit vào repository để pipeline đọc được.
B. Truyền trực tiếp qua biến và ghi giá trị ra log để kiểm tra trước khi apply.
C. Đọc từ kho secrets, phân quyền tối thiểu và bảo vệ cả log lẫn IaC state.
D. Đặt mật khẩu trong file cấu hình bên cạnh template để tiện dùng lại.
Đáp án đúng: C

Khi thay đổi cấu hình hạ tầng có nguy cơ gián đoạn dịch vụ, cách triển khai nào giúp giới hạn phạm vi ảnh hưởng?
A. Áp dụng đồng loạt để mọi vùng sẵn sàng dùng một cấu hình ngay lập tức.
B. Thử ở phạm vi nhỏ, theo dõi tín hiệu sức khỏe rồi mở rộng có kiểm soát.
C. Chạy ở production trước vì môi trường thử nghiệm không phản ánh tải thật.
D. Thực hiện theo thứ tự ngẫu nhiên để tránh nút thắt khi cập nhật hạ tầng.
Đáp án đúng: B

Trong kế hoạch sao lưu và phục hồi hệ thống quan trọng, ý nghĩa đúng của RPO và RTO là gì?
A. RPO là số bản backup cần giữ, còn RTO là chu kỳ tạo bản backup định kỳ.
B. RPO là thời gian chuyển đổi bản sao, còn RTO là số sự cố chấp nhận được.
C. RPO là thời gian hệ thống duy trì tải, còn RTO là thời hạn giữ snapshot.
D. RPO là mức mất dữ liệu tính theo thời gian, còn RTO là thời gian khôi phục.
Đáp án đúng: D

Khi đánh giá hạ tầng đang vận hành, bộ tín hiệu nào phù hợp nhất để phát hiện dịch vụ suy giảm trước người dùng?
A. Kết hợp độ trễ, lỗi, độ bão hòa và log theo trải nghiệm người dùng.
B. Theo dõi số lượng máy chủ vì hạ tầng nhiều máy thường ổn định hơn.
C. Dựa vào kết quả IaC apply vì áp dụng thành công là đủ để kết luận.
D. Theo dõi lưu lượng mạng tổng và bỏ qua các lỗi ứng dụng bên trong.
Đáp án đúng: A

Vì sao thay thế máy chủ từ image có phiên bản thường dễ kiểm soát hơn sửa cấu hình thủ công từng máy?
A. Không cần kiểm thử lại vì image được đóng gói từ một nguồn mã duy nhất.
B. Dùng cùng image đã kiểm thử giúp giảm khác biệt cấu hình giữa các máy.
C. Dữ liệu ứng dụng nằm sẵn trong image nên không cần tách volume lưu trữ.
D. Không cần theo dõi thay đổi vì phiên bản image luôn giữ nguyên ứng dụng.
Đáp án đúng: B

Khi nhóm phát triển tự tạo tài nguyên bằng IaC, cách áp dụng guardrail nào phù hợp nhất trước khi triển khai?
A. Chỉ kiểm tra chính sách sau khi áp dụng vì đó mới là cấu hình thực tế.
B. Tin mọi template nội bộ và bỏ qua việc đánh giá các tham số được truyền.
C. Kiểm tra plan với policy về quyền, mạng và nhãn trước khi cho phép apply.
D. Chỉ dùng bước review thủ công và không kiểm soát giới hạn tài nguyên.
Đáp án đúng: C

Khi một môi trường thử nghiệm hết hạn, quy trình hủy tài nguyên nào giảm rủi ro xóa nhầm dữ liệu?
A. Rà soát chủ sở hữu, phụ thuộc và dữ liệu cần giữ rồi duyệt kế hoạch hủy.
B. Xóa tất cả tài nguyên cùng prefix để nhanh chóng dọn hết phần dư thừa.
C. Thu hồi quyền người dùng rồi chờ hệ thống cloud tự xóa các tài nguyên.
D. Gỡ các tài nguyên khỏi state trước để thao tác destroy không bị cản.
Đáp án đúng: A

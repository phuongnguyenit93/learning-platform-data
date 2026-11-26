Câu 1: Khi cổng dịch vụ bị sửa thủ công khác với khai báo, mục tiêu của quản lý trạng thái mong muốn là gì?
A. Chỉ lưu lịch sử thay đổi để kiểm tra vào cuối tháng.
B. Khôi phục toàn bộ máy từ bản sao lưu gần nhất.
C. Phát hiện sai lệch rồi đưa cổng về giá trị khai báo.
D. Tạo ticket nhưng giữ nguyên cấu hình máy đang chạy.
Đáp án đúng: C

Câu 2: Chính sách đặt quyền file được chạy hai lần mà không có thay đổi bên ngoài. Điều gì thể hiện idempotency?
A. Mỗi lần chạy đều ghi lại file và cập nhật mốc thời gian sửa đổi.
B. Lần thứ hai đổi quyền file theo thời điểm thực thi.
C. Lần thứ hai bắt buộc khởi động lại dịch vụ liên quan.
D. Lần thứ hai không tạo thay đổi khi trạng thái đã đạt.
Đáp án đúng: D

Câu 3: Nhiều máy chủ ban đầu lệch cấu hình. Dấu hiệu nào cho thấy quá trình hội tụ hoạt động?
A. Số host trong inventory tăng lên theo từng đợt chạy.
B. Số tác vụ được thực thi luôn giữ nguyên qua mọi lần chạy.
C. Sai lệch so với trạng thái mong muốn giảm dần về không.
D. Thời gian chạy giảm dù cấu hình máy vẫn sai lệch.
Đáp án đúng: C

Câu 4: Nhóm có web và database ở cả staging lẫn production. Cách tổ chức inventory nào dễ kiểm soát nhất?
A. Phân nhóm host theo vai trò và môi trường triển khai.
B. Đặt toàn bộ host trong một nhóm có cấu hình chung.
C. Dựa duy nhất vào thứ tự địa chỉ IP khi chạy tác vụ.
D. Chỉ ghi tên host rồi suy luận môi trường từ hostname.
Đáp án đúng: A

Câu 5: Timeout có giá trị mặc định và giá trị riêng từng môi trường. Cách quản lý biến nào tránh ghi đè khó đoán?
A. Cho biến cùng tên tự lấy giá trị từ host bất kỳ trong inventory.
B. Quy định thứ tự ưu tiên và kiểm tra giá trị hiệu lực.
C. Đưa mọi giá trị vào một template không có biến.
D. Chỉ giữ giá trị mặc định rồi sửa tay trên từng máy.
Đáp án đúng: B

Câu 6: Nhiều máy dùng chung cấu hình web server nhưng khác domain và cổng. Nên tạo file cấu hình thế nào?
A. Sao chép file từ một host rồi sửa tay ở host kế tiếp.
B. Render cùng template bằng biến theo host và kiểm tra.
C. Ghi cố định domain và cổng vào một file chung.
D. Lưu file cấu hình xuất từ production và phân phối nguyên vẹn.
Đáp án đúng: B

Câu 7: Tác vụ cấu hình cần mật khẩu database để chạy. Cách quản lý bí mật nào phù hợp nhất?
A. Đặt mật khẩu trong inventory được commit vào Git.
B. Ghi mật khẩu vào log để dễ đối soát từng lần chạy.
C. Đưa mật khẩu vào tên file template rồi xóa sau đó.
D. Lấy từ kho bí mật, giới hạn quyền và tránh lộ log.
Đáp án đúng: D

Câu 8: Trước khi áp thay đổi firewall trên nhiều host, thao tác nào giúp đánh giá tác động mà chưa sửa máy?
A. Chạy chế độ kiểm tra và xem diff cấu hình dự kiến.
B. Áp cấu hình production rồi mới xem thay đổi thực tế.
C. Chỉ xem thời gian chạy của lần triển khai trước.
D. Xóa rule cũ trên một máy để kiểm tra cảnh báo.
Đáp án đúng: A

Câu 9: Một quản trị viên sửa cấu hình trực tiếp trên host ngoài quy trình. Cách phát hiện drift nào đúng?
A. So sánh cấu hình hiện tại với trạng thái đã khai báo.
B. Chỉ kiểm tra host còn kết nối SSH được hay không.
C. Dựa vào số lần pipeline đã chạy trong ngày hôm đó.
D. Xem dung lượng log mà không đối chiếu giá trị cấu hình.
Đáp án đúng: A

Câu 10: Thay đổi template dịch vụ cần reload, nhưng không muốn reload mỗi lần chạy. Cơ chế nào hợp lý?
A. Luôn reload dịch vụ ở đầu mỗi lần áp cấu hình để đơn giản hóa.
B. Reload theo lịch ngay cả khi file không thay đổi.
C. Chỉ kích hoạt reload khi file cấu hình thực sự đổi.
D. Chờ người vận hành reload trong mọi trường hợp.
Đáp án đúng: C

Câu 11: Khi ghi cấu hình mới cho reverse proxy, cách nào tránh kích hoạt cấu hình sai cú pháp?
A. Ghi file tạm, kiểm tra cú pháp rồi thay thế và reload.
B. Ghi thẳng file đang chạy rồi sửa nếu dịch vụ lỗi.
C. Bỏ qua kiểm tra cú pháp khi template render thành công.
D. Chỉ chạy test kết nối SSH trước khi ghi cấu hình mới.
Đáp án đúng: A

Câu 12: Đội phải đổi cấu hình cho cụm 80 máy có yêu cầu luôn còn máy phục vụ. Cách rollout nào hợp lý?
A. Áp đồng thời toàn bộ cụm để rút ngắn thời gian sửa.
B. Chỉ áp trên máy đầu rồi coi các máy còn lại tương tự.
C. Khởi động lại toàn cụm trước khi phân phối cấu hình.
D. Áp theo từng lô, kiểm sức khỏe trước khi tiếp tục.
Đáp án đúng: D

Câu 13: File private key được công cụ cấu hình phân phối lên máy. Thiết lập nào giảm nguy cơ lộ khóa?
A. Đặt quyền đọc chung để mọi tiến trình dùng dễ dàng.
B. Chỉ dựa vào việc đường dẫn file không được công bố.
C. Đưa bản sao private key vào thư mục log của dịch vụ.
D. Giới hạn chủ sở hữu và quyền đọc theo nhu cầu tối thiểu.
Đáp án đúng: D

Câu 14: Staging và production có khác biệt về endpoint nhưng cùng cấu trúc dịch vụ. Cách thiết kế nào phù hợp?
A. Nhân đôi mọi tác vụ cho từng môi trường để sửa và kiểm thử riêng.
B. Giữ logic/template chung, tách dữ liệu theo môi trường.
C. Dùng endpoint production cho cả hai để giảm cấu hình.
D. Chỉ sửa endpoint sau triển khai bằng lệnh thủ công.
Đáp án đúng: B

Câu 15: Trước khi rollout chính sách tạo user mới, kiểm thử nào kiểm chứng tính lặp lại của automation?
A. Chỉ kiểm tra file cấu hình có định dạng hợp lệ trước lần chạy.
B. Áp hai lần ở môi trường thử, xác nhận lần hai không đổi.
C. Chỉ chạy một lần trên production rồi xem log.
D. Thay đổi danh sách user thủ công sau lần chạy đầu.
Đáp án đúng: B

Câu 16: Sau sự cố do thay đổi cấu hình, dữ liệu nào giúp truy vết và phục hồi đáng tin cậy?
A. Chỉ lưu thời điểm chạy lệnh cuối trên mỗi máy.
B. Chỉ lưu hostname của máy có cảnh báo đầu tiên.
C. Lưu phiên bản khai báo, diff, lần áp và kết quả kiểm.
D. Chỉ lưu bản screenshot dashboard lúc triển khai.
Đáp án đúng: C

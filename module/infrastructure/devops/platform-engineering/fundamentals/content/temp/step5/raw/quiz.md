Một doanh nghiệp bắt đầu xây nền tảng cho các nhóm phát triển. Lựa chọn nào thể hiện đúng tư duy Platform Engineering?
A. Xem nền tảng là nhóm hạ tầng, ưu tiên số máy chủ được quản lý.
B. Xem nền tảng là bộ công cụ nội bộ, mở rộng khi có yêu cầu riêng.
C. Xem developer là khách hàng, cải tiến nền tảng theo phản hồi.
D. Xem nền tảng là nhóm vận hành, tiếp nhận mọi sự cố ứng dụng.
Đáp án đúng: C

Một nhóm muốn tự cấp phát môi trường thử nghiệm trong vài phút. Thiết kế self-service nào phù hợp nhất?
A. Gửi yêu cầu đến đội nền tảng để họ áp dụng cấu hình thủ công.
B. Cấp phát từ mẫu chuẩn cùng phân quyền, hạn mức và vòng đời.
C. Cho phép dùng tài khoản cluster-admin để tự tạo tài nguyên.
D. Dùng một môi trường chung và phân chia lịch truy cập theo nhóm.
Đáp án đúng: B

Một golden path dành cho dịch vụ backend nên được thiết kế theo nguyên tắc nào?
A. Ấn định cùng công nghệ và lịch phát hành cho mọi nhóm ứng dụng.
B. Đề xuất luồng chuẩn có mặc định tốt và ngoại lệ được quản lý.
C. Chỉ định đội nền tảng thực hiện tất cả thao tác triển khai và hỗ trợ.
D. Áp một pipeline duy nhất cho mọi dịch vụ để thống nhất quy trình.
Đáp án đúng: B

Làm thế nào để software catalog duy trì thông tin chủ sở hữu và quan hệ phụ thuộc đáng tin cậy khi dịch vụ liên tục thay đổi?
A. Đồng bộ metadata từ nguồn có chủ sở hữu và kiểm tra tự động.
B. Giao một nhân viên nhập thủ công toàn bộ dữ liệu vào wiki.
C. Suy ra người sở hữu từ repository và người commit gần nhất.
D. Chỉ ghi danh sách tài nguyên cloud vì nó được cập nhật liên tục.
Đáp án đúng: A

Ba nhóm đều cần pipeline, quan sát hệ thống và secrets. Platform team nên cung cấp năng lực dùng chung thế nào?
A. Để từng nhóm tự vận hành toàn bộ công cụ nhằm dễ tùy chỉnh.
B. Tập trung mọi vận hành ứng dụng về đội nền tảng cho nhất quán.
C. Cung cấp chung một tài khoản quản trị cho các nhóm sử dụng.
D. Cung cấp năng lực dùng chung với hợp đồng và trách nhiệm rõ.
Đáp án đúng: D

Chỉ số nào phản ánh trực tiếp việc cải thiện trải nghiệm khởi tạo dịch vụ mới?
A. Số lượng node thuộc cluster nền tảng đang được vận hành.
B. Số lần truy cập trang giới thiệu portal nội bộ mỗi tháng.
C. Tổng số template có thể chọn tại thời điểm tạo repository.
D. Thời gian đến deploy đầu giảm và lỗi khi tạo dịch vụ giảm.
Đáp án đúng: D

Khi nhiều nhóm dùng chung nền tảng cấp phát tài nguyên, giải pháp nào giúp giảm ảnh hưởng chéo giữa các nhóm?
A. Tách tài nguyên theo team, giới hạn quyền và hạn mức.
B. Sử dụng cùng service account có quyền rộng cho mọi thao tác.
C. Mở toàn bộ namespace để nhóm tự quản lý tài nguyên của nhau.
D. Gom các workload vào một không gian tên nhằm dễ quan sát.
Đáp án đúng: A

Với dịch vụ self-service cấp phát môi trường, SLO nào đo trực tiếp chất lượng người dùng nhận được?
A. Ít nhất 99% node của cluster luôn ở trạng thái Ready mỗi tháng.
B. Ít nhất 95% ticket hỗ trợ được phản hồi trong một ngày làm việc.
C. Trong 30 ngày, 99% yêu cầu hợp lệ hoàn tất trong năm phút.
D. Không triển khai thay đổi platform khi lượng yêu cầu tăng cao.
Đáp án đúng: C

Sau khi ra mắt developer portal, đa số nhóm vẫn chạy script cũ. Việc gì nên ưu tiên để hiểu nguyên nhân?
A. Đo độ trễ API của portal và mở rộng tài nguyên nếu cần.
B. So sánh số plugin tích hợp sẵn của portal với công cụ cũ.
C. Quan sát hành trình người dùng và phỏng vấn về điểm vướng.
D. Bổ sung thêm template để tăng số lựa chọn ngay trên portal.
Đáp án đúng: C

Một template tạo service mới cần giảm sai sót triển khai lặp lại. Nội dung nào nên có sẵn trong golden path?
A. Mã nguồn cơ bản và tài liệu để nhóm tự cấu hình CI về sau.
B. Kiểm thử, CI, healthcheck và các thiết lập bảo mật mặc định.
C. Các dashboard mẫu, còn quy trình build do từng nhóm quyết định.
D. Manifest triển khai chuẩn, còn kiểm thử thêm sau khi đưa vào chạy.
Đáp án đúng: B

Cách nào tích hợp self-service tạo ứng dụng với GitOps và giữ phát hiện drift hiệu quả?
A. Portal mở PR cấu hình, GitOps controller đối soát trạng thái.
B. Portal gọi trực tiếp API cluster, lưu trạng thái mong muốn ở cache.
C. Portal gửi ticket để người vận hành áp manifest từ nhánh phát hành.
D. Portal cập nhật manifest tại CI rồi không giữ vòng lặp đối soát.
Đáp án đúng: A

Nhóm phát triển báo lỗi logic thanh toán và yêu cầu platform team sửa trực tiếp. Cách phân chia trách nhiệm nào phù hợp?
A. Đội nền tảng lo năng lực chung, nhóm sản phẩm lo logic riêng.
B. Đội nền tảng xử lý mọi lỗi nghiệp vụ, nhóm sản phẩm chỉ viết mã.
C. Đội nền tảng sở hữu API ứng dụng, nhóm sản phẩm quản lý cluster.
D. Đội nền tảng chỉ cấp tài khoản, các nhóm tự vận hành toàn bộ CI.
Đáp án đúng: A

Một workload có yêu cầu đặc biệt không được golden path hiện tại hỗ trợ. Platform team nên xử lý ra sao?
A. Bắt buộc áp quy trình hiện có để giữ tỷ lệ chuẩn hóa cao.
B. Chuyển quyền sở hữu workload sang đội nền tảng để triển khai.
C. Hoãn toàn bộ các thay đổi cho đến khi template hỗ trợ xong.
D. Cho phép ngoại lệ sau đánh giá rủi ro và lưu nhu cầu cải tiến.
Đáp án đúng: D

Dịch vụ self-service tạo môi trường bị lỗi hàng loạt trong giờ cao điểm. Ưu tiên vận hành nào phù hợp?
A. Tập trung bổ sung tính năng tạo thêm loại môi trường mới.
B. Phục hồi self-service, giảm tác động và cập nhật tiến độ.
C. Nâng hạn mức cho mọi nhóm khi chưa biết nguyên nhân lỗi.
D. Chuyển yêu cầu hỗ trợ sang các nhóm ứng dụng tự xử lý.
Đáp án đúng: B

Nền tảng nội bộ vừa ra mắt portal mới. Bộ chỉ số nào giúp đánh giá giá trị thực thay vì mức độ hoạt động bề mặt?
A. Số dashboard do platform team tạo và lượng pod được quản lý.
B. Tổng số dòng mã template và số commit của đội nền tảng.
C. Lượt truy cập portal cùng số thông báo giới thiệu được gửi.
D. Thời gian onboarding, tỷ lệ tự phục vụ và lỗi triển khai.
Đáp án đúng: D

Khi developer được tự triển khai lên production, cơ chế nào giữ self-service an toàn và có thể truy vết?
A. Cấp quyền admin trực tiếp và yêu cầu mỗi nhóm tự lưu nhật ký.
B. Dùng một token chung cho portal và ghi lịch sử theo tên team.
C. Phân quyền theo vai trò, phê duyệt và lưu dấu vết cá nhân.
D. Cấp API key dài hạn riêng từng nhóm để ít phải xin quyền lại.
Đáp án đúng: C

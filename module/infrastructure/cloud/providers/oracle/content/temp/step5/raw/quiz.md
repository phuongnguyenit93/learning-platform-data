Câu 1: Trong một OCI tenancy, đội A chỉ được quản trị dự án A và đội B chỉ được quản trị dự án B. Thiết kế nào phù hợp?
A. Đặt cả hai dự án trong cùng compartment rồi phân quyền theo tag tự do.
B. Tạo hai VCN riêng rồi xem VCN là ranh giới IAM của dự án.
C. Tạo compartment riêng và cấp IAM policy theo từng nhóm dự án.
D. Tạo bucket riêng từng dự án rồi dùng ACL quản lý mọi dịch vụ.
Đáp án đúng: C

Câu 2: Ứng dụng trên OCI Compute cần đọc Object Storage mà không nhúng API signing key của người dùng. Cách nào phù hợp?
A. Lưu API signing key của quản trị viên trong biến môi trường VM.
B. Dùng instance principal, dynamic group và IAM policy giới hạn.
C. Gắn auth token của người dùng vào image của Compute instance.
D. Chuyển bucket sang public để bỏ xác thực từ Compute instance.
Đáp án đúng: B

Câu 3: Nhóm kiểm toán chỉ được đọc cấu hình Compute trong compartment Finance, không được sửa máy. Policy nào đáp ứng phạm vi này?
A. Cấp manage instance-family trong toàn tenancy cho cả nhóm kiểm toán.
B. Cấp use instance-family trong compartment Finance cho nhóm.
C. Cấp read instance-family trong tenancy cho nhóm kiểm toán.
D. Cấp read instance-family trong compartment Finance cho nhóm.
Đáp án đúng: D

Câu 4: VM tại private subnet có NSG gắn vào VNIC và chỉ được nhận SSH từ bastion 10.0.1.10. Nên cấu hình gì?
A. Mở NSG ingress TCP/22 từ 0.0.0.0/0 đến toàn bộ VNIC.
B. Dùng route table điều hướng TCP/22 vào private subnet.
C. Cho phép NSG ingress TCP/22 chỉ từ 10.0.1.10/32.
D. Mở NSG egress TCP/22 của máy đích tới IP bastion.
Đáp án đúng: C

Câu 5: Compute trong private subnet phải tải bản vá từ Internet, không có public IP và không nhận kết nối Internet đi vào. Cần gì?
A. Dùng NAT gateway với route table và egress rule phù hợp.
B. Gắn Internet gateway và public IP cho từng máy trong subnet.
C. Dùng service gateway để tới mọi website ngoài Internet.
D. Tạo local peering gateway để nối tới Internet trong region.
Đáp án đúng: A

Câu 6: Compute dùng private IP cần đọc OCI Object Storage trong cùng region mà lưu lượng không đi qua Internet. Phương án nào phù hợp?
A. Dùng Internet gateway và public IP cho các máy private.
B. Dùng service gateway và route tới Oracle Services Network.
C. Dùng NAT gateway qua public subnet cho truy cập OSS.
D. Dùng dynamic routing gateway để truy cập Object Storage cùng region.
Đáp án đúng: B

Câu 7: Website có instance pool phía sau OCI Load Balancer; tải tăng theo CPU và giảm ban đêm. Cách mở rộng nào phù hợp?
A. Gắn metric-based autoscaling vào instance pool sau Load Balancer.
B. Dùng Load Balancer tự tạo Compute VM khi lượng request tăng vượt ngưỡng.
C. Dùng fault domain tự tạo thêm VM khi CPU quá ngưỡng tải.
D. Tăng kích thước block volume của VM khi số request tăng.
Đáp án đúng: A

Câu 8: Hai Compute VM cùng availability domain cần chịu được lỗi phần cứng ảnh hưởng một nhóm host. Bố trí nào phù hợp?
A. Tăng memory của VM chính để tránh lỗi phần cứng máy chủ.
B. Đưa hai VM vào cùng fault domain để giảm độ trễ nội bộ.
C. Dùng cùng boot volume cho hai VM trên hai host khác nhau.
D. Đặt hai VM vào fault domain khác nhau trong một AD.
Đáp án đúng: D

Câu 9: Database tự quản lý trên OCI Compute cần đĩa dữ liệu block bền vững, có thể tách khỏi VM và sao lưu độc lập. Nên dùng gì?
A. Dùng Object Storage bucket rồi mount như đĩa block trực tiếp.
B. Dùng OCI Block Volume gắn vào Compute, sao lưu theo lịch.
C. Dùng File Storage nhưng yêu cầu kết nối block raw từ VM.
D. Dùng boot volume duy nhất và xóa khi thay thế instance.
Đáp án đúng: B

Câu 10: Đối tác cần tải một object thuộc bucket OCI private trong 30 phút, không có IAM user. Cách cấp quyền nào phù hợp?
A. Cấp IAM manage objects trên toàn tenancy cho người nhận.
B. Bật bucket public-read và tắt theo lịch sau 30 phút.
C. Gửi API signing key của chủ bucket qua kết nối HTTPS.
D. Tạo pre-authenticated request chỉ đọc với hạn 30 phút.
Đáp án đúng: D

Câu 11: Báo cáo trên Object Storage ít được đọc sau 90 ngày, có thể chờ khôi phục và cần lưu ba năm. Nên giảm chi phí thế nào?
A. Bật versioning và lưu mọi phiên bản đối tượng ở lớp Standard vĩnh viễn.
B. Di chuyển dữ liệu sang boot volume sau mỗi 90 ngày.
C. Dùng Object Storage lifecycle chuyển sang Archive theo tuổi.
D. Bật pre-authenticated request để giảm chi phí lưu trữ.
Đáp án đúng: C

Câu 12: Đội phát triển muốn dùng Oracle Database nhưng giảm tối đa công việc vá phần mềm và sao lưu định kỳ. Dịch vụ nào phù hợp?
A. Triển khai Oracle Database trên Compute và tự quản lý bản vá.
B. Triển khai Oracle Database trên Block Volume tự cấu hình.
C. Triển khai Oracle Database trên File Storage rồi sao lưu.
D. Dùng Autonomous Database để giảm việc vá và sao lưu thủ công.
Đáp án đúng: D

Câu 13: CPU của OCI Compute liên tục vượt 85% và đội trực cần nhận thông báo tự động. Thiết kế nào phù hợp?
A. Dùng Monitoring alarm trên CPU metric và gửi qua Notifications.
B. Dùng Audit để phát cảnh báo theo metric CPU vượt 85% trong năm phút.
C. Dùng Cost Analysis để phát hiện CPU tăng đột ngột.
D. Dùng Resource Manager chạy Terraform khi CPU tăng.
Đáp án đúng: A

Câu 14: Quản trị viên thay đổi ingress rule của NSG qua Console; cần biết danh tính và thời điểm thực hiện. Nên xem gì?
A. Dùng VCN Flow Logs để tìm người chỉnh NSG trong Console.
B. Dùng Monitoring Metrics để tra lịch sử API tạo NSG.
C. Dùng Audit để tra thời điểm, danh tính và API thay đổi NSG.
D. Dùng Object Storage lifecycle để tra ai cập nhật NSG.
Đáp án đúng: C

Câu 15: Nhóm cần triển khai VCN và Compute bằng Terraform, phát hiện cấu hình bị sửa tay so với stack. Dùng gì?
A. Chỉnh toàn bộ Terraform trực tiếp trên từng Compute instance.
B. Dùng Resource Manager stack để plan, apply và phát hiện drift.
C. Dùng Monitoring alarm để tái tạo hạ tầng khi có thay đổi.
D. Chạy Resource Manager như một bản sao lưu Object Storage.
Đáp án đúng: B

Câu 16: Bộ phận tài chính muốn theo dõi chi phí compartment và cảnh báo khi dự báo vượt ngân sách mà không tự dừng máy. Dùng gì?
A. Tạo budget cho compartment và cảnh báo chi phí dự báo.
B. Tạo quota để tự động dừng hóa đơn ngay khi vượt mức.
C. Dùng NSG giới hạn dung lượng lưu trữ của compartment.
D. Dùng Audit thay thế budget để chặn tạo tài nguyên mới.
Đáp án đúng: A

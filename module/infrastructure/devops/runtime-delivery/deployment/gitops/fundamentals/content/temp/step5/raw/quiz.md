Mô tả nào phản ánh đúng nguyên lý điều phối trạng thái mong muốn trong GitOps?
A. Pipeline CI trực tiếp cập nhật workload khi hoàn tất kiểm thử bản dựng.
B. Bản cấu hình đang chạy trên cluster được coi là nguồn sự thật duy nhất.
C. Người vận hành sửa tài nguyên trước rồi ghi lại thay đổi vào Git.
D. Git lưu khai báo; controller liên tục đối soát cluster để hội tụ theo Git.
Đáp án đúng: D

Trong mô hình GitOps pull-based, lợi ích bảo mật nào có được khi tách CI khỏi quyền triển khai cluster?
A. CI có thể dùng chung kubeconfig quản trị với controller để giảm số danh tính.
B. CI không giữ quyền quản trị cluster; controller sử dụng quyền đã giới hạn.
C. Quyền triển khai được chuyển cho mọi người có quyền đọc repository Git.
D. Git webhook cấp trực tiếp quyền truy cập Kubernetes cho từng job CI mới.
Đáp án đúng: B

Cách tổ chức manifest nào phù hợp khi hai môi trường staging và production chia sẻ phần lớn cấu hình?
A. Dùng một bộ manifest và sửa tham số trực tiếp trên cluster theo môi trường.
B. Tái sử dụng manifest cơ sở và review phần ghi đè riêng trong Git.
C. Sao chép mọi manifest rồi dùng dashboard để khắc phục từng điểm sai khác.
D. Đưa cấu hình production vào image để staging không cần manifest riêng.
Đáp án đúng: B

Sau khi kiểm thử một image ở staging, cách thăng cấp sang production nào giúp truy vết chính xác phiên bản?
A. Duyệt thay đổi Git của production trỏ tới đúng image digest đã kiểm thử.
B. Rebuild image từ nhánh chính trên máy production để có bản dựng mới.
C. Triển khai tag latest ở production sau khi tag này chạy được ở staging.
D. Sửa image bằng lệnh trực tiếp rồi cập nhật Git vào cuối kỳ phát hành.
Đáp án đúng: A

Nếu webhook từ Git không được gửi đến controller, cơ chế nào vẫn cho phép GitOps nhận ra trạng thái sai lệch?
A. Controller chỉ đối soát khi có commit mới được webhook gửi về cluster.
B. Controller chờ pipeline CI triển khai rồi đọc trạng thái đã được cập nhật.
C. Controller tiếp tục kiểm tra nguồn và trạng thái thực theo chu kỳ đã cấu hình.
D. Cluster tự ghi mọi thay đổi thực tế về Git trước khi controller so sánh.
Đáp án đúng: C

Một commit thay đổi cấu hình gây lỗi sau khi automated sync đã bật; cách rollback bền vững theo GitOps là gì?
A. Dùng lệnh sửa Deployment trên cluster và giữ nguyên commit lỗi trong Git.
B. Giảm số replica của bản mới để controller ngừng đối soát cấu hình lỗi.
C. Hoàn tác commit gây lỗi trên Git rồi để controller đồng bộ trạng thái cũ.
D. Tắt hệ thống GitOps và cập nhật workload thủ công tới lần phát hành sau.
Đáp án đúng: C

Một kỹ sư sửa cấu hình production trực tiếp qua console khiến controller báo drift; hướng xử lý nào phù hợp?
A. Giữ nguyên thay đổi trên cluster và để controller tự cập nhật ngược Git.
B. Tắt toàn bộ đối soát để tránh sửa lại các tài nguyên vừa được hotfix.
C. Bỏ qua mọi khác biệt của resource để controller không hiện lỗi trạng thái.
D. Đánh giá hotfix, cập nhật Git nếu hợp lệ hoặc khôi phục cluster theo Git.
Đáp án đúng: D

Đội vận hành muốn giảm rủi ro xóa nhầm volume khi manifest bị bỏ khỏi Git; cách kiểm soát nào thích hợp?
A. Review diff, bảo vệ tài nguyên dữ liệu khỏi prune không được phê duyệt.
B. Rút ngắn sync interval để các tài nguyên bị loại khỏi Git được xóa sớm.
C. Bật tự động prune toàn bộ workload nhằm tránh sót tài nguyên không quản lý.
D. Đánh dấu ignoreDifferences cho volume để tắt bước xóa tài nguyên.
Đáp án đúng: A

Khi ứng dụng cần mật khẩu từ một kho secrets, cách tích hợp GitOps nào tránh lưu plaintext vào Git?
A. Giữ tham chiếu tới kho secrets và cấp quyền lấy bí mật tại môi trường đích.
B. Commit Kubernetes Secret ở dạng base64 vì dữ liệu đó đã được mã hóa.
C. Đặt mật khẩu trong values file nhưng hạn chế quyền merge vào nhánh chính.
D. Lưu manifest có mật khẩu do pipeline kết xuất để controller đồng bộ nhanh.
Đáp án đúng: A

Cách cấp quyền nào phù hợp khi controller GitOps quản lý nhiều namespace do các nhóm khác nhau sở hữu?
A. Cấp cluster-admin cho mọi controller và tách nhóm theo tên repository.
B. Giới hạn danh tính controller, namespace và đích triển khai được phép.
C. Cho mọi controller ghi mọi namespace và dựa vào review để tránh nhầm lẫn.
D. Dùng kubeconfig của quản trị viên cho mọi đồng bộ để nhất quán quyền.
Đáp án đúng: B

Vì sao một Application có thể hiển thị trạng thái Synced nhưng đồng thời có sức khỏe Degraded?
A. Synced báo container còn sống, Degraded báo Git revision chưa được cập nhật.
B. Synced báo image kéo về xong, Degraded báo lượng replica chưa được tăng.
C. Synced báo cấu hình khớp Git, còn health phản ánh tình trạng workload.
D. Synced do CI xác nhận, Degraded là cảnh báo không đọc được registry image.
Đáp án đúng: C

Một admission webhook tự thêm trường vào tài nguyên khiến ứng dụng liên tục OutOfSync; cách xử lý nào an toàn?
A. Tắt webhook trên toàn cluster để tài nguyên không còn bị thay đổi sau apply.
B. Cho phép bỏ qua toàn bộ khác biệt của kind đó để giảm cảnh báo.
C. Xác minh trường được thêm rồi bỏ qua đúng phần khác biệt không nguy hại.
D. Xuất toàn bộ cấu hình đang chạy về Git sau mỗi lần webhook can thiệp.
Đáp án đúng: C

Trong GitOps đa cluster, biện pháp nào giảm nguy cơ đồng bộ nhầm workload production vào cluster thử nghiệm?
A. Cho phép controller tự chọn cluster theo context kubectl được dùng gần nhất.
B. Tạo namespace cùng tên trên các cluster để hệ thống suy ra đích triển khai.
C. Chọn đích theo nhãn image của phiên bản mới nhất trong registry.
D. Gắn rõ destination vào ứng dụng và giới hạn cluster/namespace theo quyền.
Đáp án đúng: D

Nếu repository Git tạm thời không truy cập được, tác động nào là kỳ vọng hợp lý đối với ứng dụng đã triển khai?
A. Các Pod phải dừng vì Git không còn cung cấp trạng thái mong muốn.
B. Controller tự triển khai lại revision cuối từ nhánh đang mở của CI.
C. Cluster bắt buộc rollback tất cả Deployment về image ban đầu.
D. Workload vẫn có thể chạy; nhận cập nhật mới từ Git bị trì hoãn.
Đáp án đúng: D

Vì sao tham chiếu image bằng digest giúp kiểm chứng việc thăng cấp ứng dụng tốt hơn chỉ dùng tag?
A. Tag luôn trỏ tới một nội dung duy nhất nên thay đổi tag cũng an toàn.
B. Digest nhận diện nội dung image cụ thể, tránh tag bị trỏ sang bản khác.
C. Chỉ cần trùng tên repository là Kubernetes sẽ lấy đúng image đã kiểm thử.
D. Thời điểm pipeline kết thúc đủ để chứng minh hai môi trường dùng một image.
Đáp án đúng: B

Sau khi controller GitOps bị mất cấu hình và quyền truy cập, phương án khôi phục nào giữ được nguồn sự thật đáng tin cậy?
A. Khôi phục controller và quyền giới hạn, nối lại Git rồi đối soát có kiểm soát.
B. Xóa workload đang chạy để cluster tạo lại toàn bộ trạng thái từ đầu.
C. Sao chép trạng thái cluster vào Git trước khi biết tài nguyên nào đã drift.
D. Triển khai bằng lệnh thủ công lâu dài để tránh phụ thuộc controller mới.
Đáp án đúng: A

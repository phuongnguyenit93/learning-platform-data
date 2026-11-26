Câu 1. Trong mô hình GitOps dùng Argo CD, nguồn nào biểu diễn trạng thái mong muốn của ứng dụng Kubernetes?
A. Dùng manifests trong Git làm chuẩn để đối soát trạng thái cluster.
B. Dùng đối tượng live trên cluster làm chuẩn rồi tự ghi ngược về Git.
C. Dùng image registry làm chuẩn rồi đối chiếu với Git tag.
D. Dùng kết quả job CI làm chuẩn và bỏ so sánh tài nguyên live.
Đáp án đúng: A

Câu 2. Một Argo CD Application triển khai manifests từ thư mục Git vào namespace của cluster đích. Cặp trường nào xác định nguồn và đích?
A. `source` chứa image registry và tag, `destination` chứa namespace Git.
B. `source` chứa SSH key, `destination` chứa branch và path.
C. `source` trỏ repo/path/revision, `destination` chọn cluster/namespace.
D. `source` chứa YAML đã apply, `destination` chứa commit SHA.
Đáp án đúng: C

Câu 3. Argo CD báo ứng dụng `Synced`, nhưng Deployment vẫn chưa có Pod sẵn sàng. Kết luận nào đúng?
A. Ứng dụng chắc chắn Healthy vì Git và cluster đã đồng nhất.
B. Ứng dụng bắt buộc OutOfSync khi bất kỳ Pod nào chưa Ready.
C. Ứng dụng không thể Synced nếu Deployment chưa đạt replicas.
D. Trạng thái sync có thể Synced dù health chưa Healthy.
Đáp án đúng: D

Câu 4. Nhóm xóa Service khỏi Git; Application đã bật automated sync nhưng chưa bật prune. Muốn xóa Service đang được quản lý trên cluster, cần gì?
A. Cho phép prune trong chính sách sync sau khi đánh giá rủi ro.
B. Chỉ bật selfHeal để xóa mọi tài nguyên bị loại khỏi Git.
C. Chỉ tăng số lần retry sync cho đến khi Service tự biến mất.
D. Chỉ refresh Application để tự xóa ngay tài nguyên không còn ở Git.
Đáp án đúng: A

Câu 5. Một kỹ sư dùng `kubectl` đổi số replica Deployment ngoài Git. Cấu hình Argo CD nào giúp tự đưa live state về số replica trong Git?
A. Bật `selfHeal` trong automated sync để hòa giải drift.
B. Bật `prune` mà không cần cấu hình tự sửa drift.
C. Chỉ tăng chu kỳ refresh Application để ghi đè replica.
D. Chỉ khóa nhánh Git để chặn thao tác `kubectl` trên cluster.
Đáp án đúng: A

Câu 6. Application dùng Helm chart làm nguồn. Argo CD sử dụng Helm thế nào trong quá trình phân phối?
A. Helm quản lý release riêng, Argo CD chỉ theo dõi release Secret.
B. Helm tự chạy `upgrade` trước rồi Argo CD kiểm tra sau.
C. Helm thay thế việc đối soát live state với Git của Argo CD.
D. Helm render chart và values; Argo CD đồng bộ manifests kết quả.
Đáp án đúng: D

Câu 7. Một nền tảng muốn cấp cùng ứng dụng vào mọi cluster đăng ký có label `team=alpha`. Cách khai báo nào phù hợp?
A. Tạo Application thủ công theo từng cluster, cập nhật khi có cluster mới.
B. Dùng một Application và đổi destination khi cluster được thêm.
C. Dùng ApplicationSet clusters generator có selector theo label.
D. Dùng Git tag làm tên cluster cho mỗi lần chạy đồng bộ.
Đáp án đúng: C

Câu 8. Tổ chức muốn một nhóm chỉ triển khai từ repo được duyệt vào namespace được phép. Cơ chế nào hạn chế ranh giới Application?
A. Giới hạn resource quota của argocd-server cho mọi người dùng.
B. Giới hạn nhãn Deployment trong template Kustomize duy nhất.
C. Cấu hình `sourceRepos` và `destinations` trong AppProject.
D. Chỉ đặt manual sync nhưng giữ mọi repo và cluster khả dụng.
Đáp án đúng: C

Câu 9. Một controller thêm annotation động vào Deployment khiến Argo CD liên tục báo OutOfSync. Cách giữ các kiểm tra drift khác vẫn hoạt động là gì?
A. Tắt mọi thông báo so sánh khác biệt trên toàn bộ tài nguyên của project.
B. Xóa các annotation trong Kubernetes sau mỗi lần deploy.
C. Bật prune để tự loại bỏ mọi annotation không có trong Git.
D. Chỉ cấu hình `ignoreDifferences` cho annotation do controller thêm.
Đáp án đúng: D

Câu 10. Application theo `targetRevision: main`, automated sync được bật. Khi commit mới thay đổi manifests trên nhánh main, Argo CD sẽ làm gì?
A. Chỉ cập nhật khi người dùng sửa `targetRevision` trong CR.
B. Biên dịch Docker image từ commit mới rồi push lên registry.
C. Phát hiện revision mới và đồng bộ manifests đã render.
D. Xóa tất cả Pod trước khi tải Git revision mới theo mặc định.
Đáp án đúng: C

Câu 11. Bản triển khai mới gây lỗi, Application đang tự đồng bộ từ Git. Cách rollback bền vững theo GitOps là gì?
A. Sửa image trực tiếp bằng `kubectl` và để Git không đổi.
B. Revert thay đổi trong Git về bản tốt rồi đồng bộ lại.
C. Xóa Application CR để Argo CD tự phục hồi release trước.
D. Tạm dừng refresh rồi chỉnh các Pod đang chạy bằng tay.
Đáp án đúng: B

Câu 12. Một CR chỉ có thể được tạo sau khi CRD tương ứng hiện diện. Muốn chủ động kiểm soát thứ tự trong một lần Argo CD sync, nên làm gì?
A. Đặt tên tệp CRD theo thứ tự chữ cái đứng trước tệp CR.
B. Chỉ thay Helm values để CR chờ CRD sau khi triển khai.
C. Tăng số lần retry để không cần khai báo thứ tự tài nguyên.
D. Gắn sync-wave thấp cho CRD và cao hơn cho CR phụ thuộc.
Đáp án đúng: D

Câu 13. Một Application cần dùng credential runtime nhưng repo Git không được chứa Secret plaintext. Phương án nào phù hợp?
A. Commit Kubernetes Secret dạng plaintext trong repo private có phân quyền.
B. Dùng External Secrets hoặc Sealed Secrets với quản lý khóa.
C. Mã hóa secret bằng Base64 rồi commit vào Helm values Git.
D. Đưa secret vào Git và ẩn log trên giao diện Argo CD.
Đáp án đúng: B

Câu 14. Argo CD sync thất bại với lỗi Kubernetes `Forbidden: cannot create configmaps` tại cluster đích. Nên kiểm tra điều gì trước?
A. Quyền RBAC của danh tính Argo CD sử dụng trên cluster đích.
B. Tăng phiên bản Helm chart để Kubernetes tự cấp thêm quyền.
C. Chỉ bật selfHeal để tài khoản triển khai được thêm quyền.
D. Tắt kiểm tra khác biệt để lỗi `Forbidden` không còn xuất hiện.
Đáp án đúng: A

Câu 15. Nhóm có manifests Kubernetes dùng chung nhưng staging và production khác namespace và replica. Dùng Kustomize thế nào cho phù hợp?
A. Sao chép toàn bộ manifest sang hai repository độc lập.
B. Dùng base chung cùng overlay riêng cho từng môi trường.
C. Sửa trực tiếp base bằng CI trước mỗi lần triển khai.
D. Dùng một overlay rồi sửa live state thủ công theo môi trường.
Đáp án đúng: B

Câu 16. Một image tag `latest` bị gắn lại với digest mới nhưng manifests Git không thay đổi. Muốn bản phát hành tái lập và truy vết được, nên làm gì?
A. Giữ tag `latest` và tăng tần suất refresh Application.
B. Pin image theo digest bất biến, cập nhật Git qua review.
C. Giữ image tag `latest` nhưng chỉ pin phiên bản Helm chart.
D. Chỉ bật selfHeal để Argo CD phát hiện registry đổi image.
Đáp án đúng: B

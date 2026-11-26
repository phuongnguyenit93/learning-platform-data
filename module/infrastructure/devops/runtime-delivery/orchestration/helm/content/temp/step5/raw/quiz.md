Câu 1: Nhóm đóng gói ứng dụng thành Helm chart mới, cần nơi khai báo metadata, giá trị mặc định và template tài nguyên Kubernetes. Bố cục nào đúng?
A. Dùng values.yaml cho metadata, Chart.yaml cho mặc định và charts/ chứa template.
B. Dùng Chart.lock cho metadata, charts/ cho mặc định và crds/ cho manifest.
C. Dùng Chart.yaml cho metadata, values.yaml cho mặc định và templates/ cho manifest.
D. Dùng .helmignore cho metadata, templates/ cho mặc định và Chart.lock cho manifest.
Đáp án đúng: C

Câu 2: Chart có replicaCount=1, tệp prod.yaml đặt replicaCount=2; lệnh cài đặt dùng cả -f prod.yaml và --set replicaCount=5. Giá trị nào được render?
A. Dùng replicaCount=5 vì --set ghi đè giá trị cùng khóa trong tệp.
B. Dùng replicaCount=2 vì tệp -f luôn ưu tiên hơn mọi cờ --set trong Helm.
C. Lệnh thất bại vì replicaCount không được xuất hiện ở hai nguồn.
D. Dùng replicaCount=1 từ values.yaml và bỏ qua cả hai ghi đè.
Đáp án đúng: A

Câu 3: Chart có helper định nghĩa trong _helpers.tpl để tạo tên resource. Template Deployment cần chèn tên và căn lề YAML qua pipeline. Cách nào phù hợp?
A. Dùng .Files.Get đọc nội dung _helpers.tpl rồi chèn thẳng vào manifest.
B. Dùng required gọi helper và tự động định dạng lề của tài nguyên.
C. Dùng toYaml .Chart để render helper với lề chuẩn trong template.
D. Dùng include gọi helper với context rồi truyền qua hàm nindent.
Đáp án đúng: D

Câu 4: Một namespace cần hai bản cài độc lập từ cùng một chart, mỗi bản dùng file values riêng. Nên triển khai như thế nào?
A. Gọi helm install hai lần với cùng tên release và hai tệp values riêng trong namespace.
B. Đặt tên chart khác nhau trong Chart.yaml mỗi khi cài thêm một bản.
C. Cài hai release có tên khác nhau, cùng chart nhưng dùng values riêng.
D. Gộp hai tệp values vào một release để Helm tự tạo hai bản cài.
Đáp án đúng: C

Câu 5: Pipeline chạy lần đầu khi release chưa tồn tại và các lần sau phải nâng cấp release đó từ chart mới. Lệnh nào đáp ứng cả hai trường hợp?
A. Dùng helm install với cùng tên release cho mọi lần triển khai.
B. Dùng helm upgrade --install với tên release và đường dẫn chart.
C. Dùng helm template để tự động cập nhật release trên cluster.
D. Dùng helm dependency update trước mỗi lần để cài lại release.
Đáp án đúng: B

Câu 6: Release payments trong namespace prod đang ở revision 5 bị lỗi; revision 3 đã chạy ổn định. Lệnh nào đưa release về cấu hình revision 3?
A. Chạy helm rollback payments 3 -n prod để phục hồi revision đó.
B. Chạy helm upgrade payments 3 -n prod để chọn revision cũ.
C. Chạy helm history payments 3 -n prod để triển khai lại manifest.
D. Chạy helm get values payments 3 -n prod để khôi phục ứng dụng.
Đáp án đúng: A

Câu 7: Sau nhiều lần nâng cấp release api ở namespace stage, nhóm muốn xem các revision và trạng thái từng lần phát hành trước khi rollback. Chạy gì?
A. Chạy helm show chart api -n stage để đọc danh sách revision.
B. Chạy helm get manifest api -n stage để xem lịch sử release.
C. Chạy helm repo list -n stage để tra lịch sử từng lần upgrade của release.
D. Chạy helm history api -n stage để xem revision và trạng thái.
Đáp án đúng: D

Câu 8: Trước khi đẩy chart vào registry, CI cần kiểm tra lỗi cấu trúc chart và nhiều lỗi template mà không cài lên cluster. Công cụ nào phù hợp?
A. Chạy helm test ./chart để kiểm tra biểu mẫu mà không có release.
B. Chạy helm lint ./chart để kiểm tra chart ngay trong pipeline.
C. Chạy helm rollback ./chart để thử khả năng phục hồi của chart.
D. Chạy helm uninstall ./chart để kiểm tra template bị sai cú pháp.
Đáp án đúng: B

Câu 9: Chart app khai báo Redis làm dependency trong Chart.yaml; nhóm thay đổi constraint phiên bản và cần cập nhật charts/ cùng Chart.lock. Lệnh nào phù hợp?
A. Chạy helm dependency update ./app để lấy phụ thuộc và cập nhật khóa.
B. Chạy helm repo update ./app để sinh Chart.lock theo danh sách phụ thuộc.
C. Chạy helm package ./app để tự tải lại mọi dependency đã thay đổi.
D. Chạy helm show values ./app để đồng bộ thư mục charts/ và Chart.lock.
Đáp án đúng: A

Câu 10: Chart cần tạo Ingress khi values.ingress.enabled=true và bỏ hẳn manifest này khi false. Cách viết template nào phù hợp?
A. Dùng .Release.IsInstall để quyết định Ingress có được render trong lần upgrade hay không.
B. Dùng .Chart.Version để bật tắt Ingress theo phiên bản chart.
C. Bọc manifest trong if .Values.ingress.enabled trong template Ingress.
D. Dùng .Files.Get để tự động bỏ file Ingress khi enabled=false.
Đáp án đúng: C

Câu 11: Sau khi cài release web, nhóm muốn chạy một Pod smoke test do chart cung cấp và nhận kết quả qua cơ chế Helm. Cách nào phù hợp?
A. Đặt Pod là pre-install hook và chỉ chạy helm lint để kiểm tra.
B. Đặt Pod trong templates/ rồi chỉ gọi helm show values web.
C. Đánh dấu Pod bằng hook test và chạy helm test với tên release.
D. Đặt Pod trong crds/ rồi dùng helm dependency build để kiểm tra.
Đáp án đúng: C

Câu 12: Người duyệt muốn xem manifest Kubernetes sẽ được Helm tạo từ chart và prod.yaml, nhưng không muốn thay đổi cluster hay release. Lệnh nào phù hợp?
A. Chạy helm get manifest app -n prod để tạo bản render mới.
B. Chạy helm template app ./chart -f prod.yaml để render ra stdout.
C. Chạy helm pull ./chart -f prod.yaml để render manifest cục bộ.
D. Chạy helm package ./chart -f prod.yaml để in manifest đã render.
Đáp án đúng: B

Câu 13: Release Deployment cần chờ workload đạt trạng thái sẵn sàng trước khi lệnh cài đặt được tính là thành công. Cờ nào phù hợp?
A. Dùng --timeout để tự bật kiểm tra Pod readiness khi cài đặt.
B. Dùng --history-max để yêu cầu Pod đạt trạng thái Ready trước.
C. Dùng --dependency-update để chờ container ứng dụng khởi chạy.
D. Dùng --wait và đặt --timeout phù hợp cho bước cài đặt.
Đáp án đúng: D

Câu 14: Nhóm dùng GitOps để triển khai Helm chart cho nhiều môi trường. Cách nào tạo trạng thái mong muốn có thể kiểm toán và tái lập?
A. Lưu chart version và values theo môi trường trong Git để controller reconcile.
B. Cho kỹ sư chỉnh values trực tiếp trên cluster rồi ghi lại khi cần kiểm tra bản deploy.
C. Chỉ lưu tên release trong Git, còn image tag luôn lấy latest.
D. Tự nâng cấp chart trên máy cá nhân, bỏ qua diff giữa các môi trường.
Đáp án đúng: A

Câu 15: Chart cần mật khẩu database nhưng nhóm không muốn secret lộ trong values.yaml, tham số CLI và lịch sử release. Phương án nào phù hợp?
A. Đưa mật khẩu vào --set trong pipeline và che log của bước cài.
B. Dùng Secret được quản lý bên ngoài chart và tham chiếu từ workload.
C. Mã hóa file chart bằng helm package rồi giữ mật khẩu trong values.
D. Đặt mật khẩu trong ghi chú NOTES.txt để chỉ người vận hành thấy.
Đáp án đúng: B

Câu 16: Sau upgrade, nhóm muốn xem bộ values đã được tính toán cho release billing trong namespace prod, gồm cả mặc định của chart. Lệnh nào đúng?
A. Chạy helm show values billing -n prod để xem toàn bộ values đã merge của release.
B. Chạy helm history billing -n prod để in values sau khi merge.
C. Chạy helm get manifest billing -n prod để chỉ xem values gốc.
D. Chạy helm get values billing --all -n prod để xem values tính toán.
Đáp án đúng: D

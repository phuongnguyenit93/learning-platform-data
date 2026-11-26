Câu 01. Trong Linkerd, data plane gồm thành phần chủ yếu nào?
A. Các controller lưu trạng thái rollout của Deployment Kubernetes.
B. Các dashboard tập hợp số liệu lịch sử và cấu hình cảnh báo.
C. Các proxy chạy cạnh ứng dụng để xử lý lưu lượng giữa các pod.
D. Các API server xác thực yêu cầu quản trị cụm Kubernetes.
Đáp án đúng: C

Câu 02. Proxy Linkerd thường bắt lưu lượng vào và ra pod nhờ cơ chế nào?
A. Thay thế thư viện TCP của ứng dụng bằng SDK Linkerd riêng.
B. Thêm HTTP middleware bắt buộc vào từng controller của ứng dụng.
C. Thay đổi DNS record của mọi Service để trỏ sang máy giám sát.
D. Chuyển hướng kết nối bằng quy tắc mạng như iptables hoặc CNI.
Đáp án đúng: D

Câu 03. Thành phần destination của Linkerd control plane chủ yếu cung cấp gì?
A. Trang dashboard quản trị và các file snapshot dùng cho backup.
B. Luồng log ứng dụng qua từng request và các bảng metrics tổng hợp.
C. Cung cấp endpoint, discovery và TLS identity cho proxy.
D. Chứng chỉ CA gốc và private key để từng ứng dụng tự ký chứng chỉ.
Đáp án đúng: C

Câu 04. Identity service của Linkerd đóng vai trò nào đối với mTLS?
A. Tạo access token HTTP dùng để thay thế service account của pod.
B. Ký chứng chỉ ngắn hạn cho proxy sau khi duyệt CSR.
C. Cân bằng các kết nối TCP giữa các node Kubernetes của cluster.
D. Chọn HTTP route được phép retry trước khi chuyển tới application.
Đáp án đúng: B

Câu 05. Proxy injector của Linkerd hoạt động theo cơ chế Kubernetes nào?
A. Scheduler plugin chạy lại ứng dụng khi service mới xuất hiện.
B. DaemonSet tự gắn proxy vào mọi container đang chạy trên node.
C. Admission webhook thêm proxy vào pod đủ điều kiện.
D. CoreDNS plugin thay địa chỉ IP pod bằng địa chỉ control plane.
Đáp án đúng: C

Câu 06. Annotation nào thường kích hoạt Linkerd proxy injection cho workload?
A. Đặt kubernetes.io/proxy: on trên mọi endpoint của Service.
B. Đặt linkerd.io/inject: enabled cho workload hoặc namespace.
C. Đặt service.beta.kubernetes.io/tls: true trên Ingress.
D. Đặt linkerd.io/mesh: secure trên ConfigMap của ứng dụng.
Đáp án đúng: B

Câu 07. Khi vừa bật injection trên namespace, pod đang chạy cần gì để nhận proxy?
A. Tạo pod mới qua rollout để proxy được inject.
B. Chờ webhook tự đưa sidecar mới vào container của pod hiện hữu.
C. Khởi động lại control plane để sao chép proxy vào pod hiện tại.
D. Chỉnh Service selector để tự thêm sidecar vào mọi pod cũ.
Đáp án đúng: A

Câu 08. Khi dùng Linkerd CLI cài đặt qua manifest, bước nào thường đi trước control plane?
A. Áp dụng manifest sinh bởi linkerd multicluster link.
B. Áp dụng các CRD sinh bởi linkerd install --crds.
C. Áp dụng dashboard sinh bởi linkerd viz dashboard.
D. Áp dụng traffic policy sinh bởi linkerd viz routes.
Đáp án đúng: B

Câu 09. Sau khi cài control plane, lệnh nào kiểm tra tình trạng Linkerd?
A. Chạy linkerd check để kiểm tra các thành phần và cấu hình.
B. Chạy linkerd viz tap để xác minh mọi certificate issuer.
C. Chạy linkerd multicluster link để kiểm tra pod đơn cụm.
D. Chạy linkerd inject để đo độ trễ của từng upstream hiện có.
Đáp án đúng: A

Câu 10. Khi muốn kiểm tra proxy trong các pod đã mesh, nên dùng lệnh nào?
A. Chạy linkerd install --crds để kiểm tra các sidecar đang chạy.
B. Chạy linkerd viz install để kiểm tra tên service account pod.
C. Chạy linkerd check --proxy để xác minh trạng thái data plane.
D. Chạy linkerd multicluster gateways để xác minh mọi sidecar.
Đáp án đúng: C

Câu 11. mTLS tự động của Linkerd áp dụng rõ nhất cho trường hợp nào?
A. Giao tiếp giữa mọi node Kubernetes không có proxy ứng dụng.
B. Giao tiếp từ mọi browser Internet tới ứng dụng qua Ingress.
C. Giao tiếp từ mọi pod chưa mesh tới cơ sở dữ liệu ngoài cụm.
D. Giao tiếp giữa hai workload đã mesh với proxy hai phía.
Đáp án đúng: D

Câu 12. Danh tính workload dùng trong Linkerd mTLS thường gắn với yếu tố nào?
A. Host header do client ngoài Internet tự gửi vào proxy ingress.
B. Địa chỉ DNS public của node chạy Deployment trong cluster.
C. Gắn với ServiceAccount và namespace của workload Kubernetes.
D. Địa chỉ IP tạm thời của pod đang xử lý một kết nối cụ thể.
Đáp án đúng: C

Câu 13. Trust anchor và identity issuer trong Linkerd có quan hệ nào?
A. Trust anchor làm gốc tin cậy; issuer ký chứng chỉ workload.
B. Trust anchor do từng pod tự tạo; issuer dùng để chọn route HTTP.
C. Trust anchor lưu metric proxy; issuer lưu access log của pod.
D. Trust anchor quyết định quota; issuer quyết định endpoint IP.
Đáp án đúng: A

Câu 14. Trong vận hành Linkerd mTLS, chứng chỉ issuer sắp hết hạn cần làm gì?
A. Chỉ thay mật khẩu dashboard vì chứng chỉ không ảnh hưởng proxy.
B. Xoay vòng issuer có kế hoạch trước khi hết hạn.
C. Chỉ tăng TTL cache ứng dụng để tránh phải gia hạn chứng chỉ.
D. Chỉ restart CoreDNS vì issuer được tự tạo theo địa chỉ DNS.
Đáp án đúng: B

Câu 15. Khi một workload đã mesh gọi tới workload chưa mesh, cần lưu ý gì?
A. Identity service sẽ tự inject proxy vào backend qua TCP.
B. Proxy sẽ từ chối mọi kết nối ngoài mesh bất kể chính sách.
C. Mọi kết nối vẫn được Linkerd mTLS do một bên có proxy.
D. Không thể mặc định chặng này được Linkerd mTLS cả hai phía.
Đáp án đúng: D

Câu 16. Với Linkerd authorization policy, phạm vi enforcement nào đúng?
A. Policy thực thi trên những pod đã được proxy inject.
B. Chính sách luôn có hiệu lực ở mọi pod dù không inject proxy.
C. Chính sách thay thế toàn bộ Kubernetes RBAC ở API server.
D. Chính sách chỉ áp dụng cho request tới dashboard giám sát.
Đáp án đúng: A

Câu 17. Kubernetes Server CRD của Linkerd chủ yếu xác định đối tượng nào?
A. Tập ConfigMap chứa khóa ký dành cho control plane.
B. Nhóm node và phiên bản kernel phải có proxy Linkerd.
C. Nhóm Ingress và DNS zone public để nhận client ngoài.
D. Chọn tập pod và cổng inbound cần bảo vệ bằng policy.
Đáp án đúng: D

Câu 18. MeshTLSAuthentication trong Linkerd giúp mô tả điều kiện nào?
A. Xác thực dựa trên cookie browser và session trên ứng dụng.
B. Xác thực dựa trên user đăng nhập giao diện dashboard.
C. Xác thực dựa trên danh tính mTLS của workload gọi tới.
D. Xác thực dựa trên địa chỉ IP nguồn không dùng certificate.
Đáp án đúng: C

Câu 19. NetworkAuthentication trong Linkerd dùng tiêu chí nào?
A. Subject của chứng chỉ client theo service account và namespace.
B. Đường dẫn HTTP request khớp với tên route được công bố.
C. Dải IP mạng của nguồn kết nối để mô tả điều kiện xác thực.
D. Nhóm HTTP method được đánh dấu là idempotent tại proxy.
Đáp án đúng: C

Câu 20. AuthorizationPolicy của Linkerd kết nối hai yếu tố nào?
A. HTTP response cache với thời hạn tồn tại của Service.
B. ConfigMap ứng dụng với số lượng pod cần scale trong cluster.
C. Định nghĩa scrape metrics với storage class chứa dữ liệu.
D. Kết nối target được bảo vệ với điều kiện authentication.
Đáp án đúng: D

Câu 21. Khi muốn giới hạn quyền theo đường dẫn HTTP, loại resource nào phù hợp?
A. Dùng HTTPRoute cùng các policy liên quan tới target cụ thể.
B. Dùng ServiceAccount để khai báo regex của các endpoint HTTP.
C. Dùng Secret TLS để chuyển các HTTP method thành whitelist.
D. Dùng NetworkAuthentication để liệt kê mọi HTTP path cho phép.
Đáp án đúng: A

Câu 22. Với Linkerd hiện đại, ServiceProfile có vị trí nào so với Gateway API?
A. ServiceProfile buộc thay Gateway API cho mọi policy mới.
B. ServiceProfile chỉ quản lý DNS và không có metric theo route.
C. ServiceProfile còn hỗ trợ tương thích; Gateway API là hướng mới.
D. ServiceProfile tự nâng cấp mọi HTTPRoute thành Secret Kubernetes.
Đáp án đúng: C

Câu 23. Nếu chưa áp chính sách hạn chế, Linkerd mặc định xử lý lưu lượng thế nào?
A. Chặn mọi TCP traffic đến khi có định nghĩa HTTPRoute.
B. Cho phép traffic qua mesh theo chính sách mặc định cởi mở.
C. Từ chối tất cả ingress tới mọi workload kể cả meshed.
D. Buộc tất cả client cấp certificate để mới có thể gọi.
Đáp án đúng: B

Câu 24. Tại sao Linkerd cần protocol detection với lưu lượng TCP?
A. Nhận diện HTTP để dùng tính năng Layer 7 của proxy.
B. Thay tất cả các giao thức TCP bằng giao thức HTTP/2.
C. Đổi địa chỉ Kubernetes Service thành địa chỉ public.
D. Giải mã TLS ứng dụng để đọc mọi request body bí mật.
Đáp án đúng: A

Câu 25. Với cổng dùng giao thức TCP không phải HTTP, cấu hình nào phù hợp?
A. Đặt appProtocol: http để Linkerd bỏ qua mọi HTTP parser.
B. Đặt appProtocol: linkerd.io/opaque trên Service port.
C. Đặt appProtocol: grpc để gửi byte TCP tùy ý qua HTTP.
D. Đặt appProtocol: tls để Linkerd tự đọc nội dung ứng dụng.
Đáp án đúng: B

Câu 26. Khi traffic bị coi là opaque TCP, hạn chế quan trọng nào?
A. Proxy không thể chuyển tiếp kết nối tới một Service nào.
B. Proxy bỏ hết mTLS vì mọi TCP opaque đều truyền plaintext.
C. Proxy tự chuyển mọi request thành HTTP để thống kê theo route.
D. Policy dựa trên HTTPRoute không áp dụng trên traffic opaque.
Đáp án đúng: D

Câu 27. Với service-to-service HTTP, Linkerd có thể cải thiện phân phối tải bằng gì?
A. Cân bằng bằng cách nhân bản mọi request tới tất cả backend.
B. Cân bằng Layer 7 dựa trên quan sát độ trễ của các endpoint.
C. Cân bằng bằng cách tự mở rộng CPU limit của mọi pod.
D. Cân bằng bằng cách cố định toàn bộ request vào IP của node.
Đáp án đúng: B

Câu 28. Khi cấu hình retry cho một route gọi API tạo thanh toán, cần cân nhắc gì?
A. Chỉ kích thước response vì HTTP POST luôn idempotent.
B. Chỉ thời hạn cert vì retry tự rollback giao dịch backend.
C. Chỉ số lượng pod vì mọi timeout chứng minh request chưa tới.
D. Khả năng idempotent và nguy cơ lặp tác dụng khi retry.
Đáp án đúng: D

Câu 29. Vì sao không nên cấu hình retry không giới hạn trong mesh?
A. Retry luôn đưa request tới chính một endpoint vừa lỗi.
B. Retry sẽ tự xóa policy mTLS của cả hai proxy kết nối.
C. Retry kéo dài có thể khuếch đại tải khi upstream đang lỗi.
D. Retry làm mọi container tự tăng số replica trong Deployment.
Đáp án đúng: C

Câu 30. Khi đặt timeout cho một HTTP route, mục tiêu chính nào?
A. Tắt kiểm tra chứng chỉ của peer khi yêu cầu kéo dài.
B. Đặt giới hạn thời gian chờ phù hợp cho route HTTP.
C. Buộc mọi backend thực thi xong cùng một thời điểm.
D. Giữ kết nối mở vô hạn để tránh mọi response 5xx.
Đáp án đúng: B

Câu 31. Linkerd Viz cung cấp công cụ nào cho người vận hành?
A. Tạo PVC sao lưu dữ liệu nghiệp vụ của mọi backend.
B. Cung cấp metrics, dashboard và quan sát traffic mesh.
C. Tự gán quota namespace dựa trên tốc độ các request.
D. Tự triển khai lại Deployment khi có HTTP status 404.
Đáp án đúng: B

Câu 32. Lệnh linkerd viz stat thường giúp xem điều gì?
A. Lịch sử thay đổi manifest Deployment trên Git repository.
B. Tình trạng tất cả node disk và dung lượng của containerd.
C. Giá trị nội dung Secret và chứng chỉ riêng của từng pod.
D. Thông số traffic, success rate và latency của workload.
Đáp án đúng: D

Câu 33. linkerd viz tap được sử dụng chủ yếu khi muốn gì?
A. Sửa policy truy cập và phát hành chứng chỉ CA ngay khi tap.
B. Cấu hình retry và timeout cho tất cả route của namespace.
C. Tải toàn bộ nội dung request body đã được lưu nhiều tháng.
D. Quan sát mẫu request đang đi qua các proxy theo thời gian thực.
Đáp án đúng: D

Câu 34. Trong telemetry của Linkerd, nhóm golden metrics gồm gì?
A. Thời gian deploy, số lượng replica và mã version Git.
B. Success rate, lưu lượng request và phân bố độ trễ.
C. CPU node, kích thước image và số lượng volume mount.
D. Tuổi certificate, số lượng ConfigMap và số lượng PVC.
Đáp án đúng: B

Câu 35. Khi p95 latency tăng còn median gần như ổn định, nên nhận định gì?
A. Một phần request ở đuôi phân phối đang chậm hơn đáng kể.
B. Client đồng loạt gửi ít request hơn dù chưa đo traffic.
C. Toàn bộ request có độ trễ tăng đều theo một tỷ lệ.
D. Success rate chắc chắn đã giảm xuống dưới ngưỡng 95%.
Đáp án đúng: A

Câu 36. Trong thiết lập Linkerd multicluster, điều kiện tin cậy nào quan trọng?
A. Các cluster liên kết có trust anchor chung hoặc bundle phù hợp.
B. Mọi cluster phải sử dụng chung một database của control plane.
C. Mọi cluster phải đặt toàn bộ workload trong một namespace.
D. Mọi cluster phải dùng cùng địa chỉ IP cho Kubernetes API server.
Đáp án đúng: A

Câu 37. Multicluster gateway của Linkerd thường phục vụ nhiệm vụ nào?
A. Thay thế Kubernetes API server cho tất cả cluster được link.
B. Chạy tất cả workload của cluster nguồn trên cluster đích.
C. Cung cấp điểm nối cho traffic từ cluster khác tới dịch vụ đích.
D. Tự xác thực người dùng Internet qua cookie ứng dụng.
Đáp án đúng: C

Câu 38. Muốn một Service được mirror sang cluster đã liên kết, cần xét gì?
A. Xóa selector của Service để proxy tự sao chép endpoint.
B. Đặt tất cả Service thành NodePort dù không có gateway.
C. Tạo một HTTPRoute trỏ tới pod IP của từng instance đích.
D. Gắn nhãn export để controller có thể mirror Service.
Đáp án đúng: D

Câu 39. Sau khi nâng cấp Linkerd control plane, sidecar cũ được cập nhật ra sao?
A. Rollout lại workload để pod mới nhận phiên bản proxy mới.
B. Chỉ sửa Service selector để proxy trong pod tự cập nhật.
C. Chỉ chạy kubectl get pods là image proxy được đổi mới.
D. Control plane tự thay binary trong các container đang chạy.
Đáp án đúng: A

Câu 40. Khi hoàn tất nâng cấp data plane, nên kiểm tra điều gì?
A. Chạy linkerd check --proxy và rà proxy còn phiên bản cũ.
B. Chạy linkerd inject --manual để xóa mọi policy của mesh.
C. Chạy linkerd viz tap để thay chứng chỉ issuer của cluster.
D. Chạy linkerd multicluster link để xóa các service mirror.
Đáp án đúng: A

1. Mục tiêu chính khi đưa dịch vụ Kubernetes vào Istio service mesh là gì?
A. Thay Kubernetes scheduler để quyết định node chạy từng Pod.
B. Điều phối traffic, áp bảo mật và quan sát giữa các dịch vụ.
C. Thay container runtime để thực thi code ứng dụng trong Pod.
D. Thay PersistentVolume để lưu trạng thái chung giữa dịch vụ.
Đáp án đúng: B

2. Trong kiến trúc Istio, thành phần nào phân phối cấu hình và hỗ trợ cấp chứng thư workload?
A. Envoy ingress gateway làm control plane và ký mọi manifest.
B. CoreDNS trực tiếp cấp chứng thư mTLS cho từng service.
C. istiod đảm nhiệm control plane, xDS và chức năng CA mesh.
D. kube-proxy làm control plane và gửi route theo giao thức xDS.
Đáp án đúng: C

3. Ở sidecar mode, Envoy được triển khai gần ứng dụng theo cách nào?
A. Proxy chạy duy nhất ở control plane cho mọi Pod ứng dụng.
B. Envoy chạy cùng Pod để xử lý traffic inbound/outbound.
C. Proxy chạy trong CoreDNS và chỉ thấy các truy vấn DNS.
D. Proxy chạy thay tiến trình ứng dụng ở container chính.
Đáp án đúng: B

4. Namespace đã gắn nhãn istio-injection=enabled nhưng Pod cũ chưa có sidecar. Thao tác nào hợp lý?
A. Tạo lại Pod để webhook injection tác động tới Pod mới.
B. Đợi istiod tự thêm container vào Pod đang hoạt động.
C. Chỉ khởi động lại CoreDNS để sidecar xuất hiện trong Pod.
D. Cấp thêm IP cho Service để kích hoạt injection trên Pod cũ.
Đáp án đúng: A

5. Trong sidecar mode, xDS chủ yếu dùng để làm gì?
A. Đồng bộ route, listener, cluster và endpoint tới Envoy.
B. Chuyển nội dung HTTP giữa hai ứng dụng qua cổng 443.
C. Tạo PersistentVolume cho từng container của ứng dụng.
D. Thay thuật toán scheduling của Kubernetes khi Pod bị evict.
Đáp án đúng: A

6. Muốn tham gia Istio ambient bằng nhãn namespace thông dụng, chọn gì?
A. istio-injection=enabled để bật dataplane không sidecar.
B. istio.io/rev=ambient để đặt chính sách ingress toàn cục.
C. sidecar.istio.io/inject=true để chạy ztunnel từng Pod.
D. Nhãn istio.io/dataplane-mode=ambient để tham gia mesh.
Đáp án đúng: D

7. Trong ambient mode, vai trò chính của ztunnel là gì?
A. Proxy theo Pod xử lý mọi HTTP header và route L7.
B. Proxy gateway ngoài cluster xử lý Internet ingress.
C. Proxy trong istiod xử lý toàn bộ TLS từ client công cộng.
D. Proxy theo node thực hiện mTLS, định tuyến và policy L4.
Đáp án đúng: D

8. HBONE trong Istio ambient được dùng chủ yếu cho tác vụ nào?
A. Tunnel mã hóa giữa các proxy dữ liệu trong mesh.
B. Mã hóa riêng file cấu hình của Kubernetes API server.
C. Phân giải DNS cho Service có nhiều endpoint khác nhau.
D. Phân phối container image tới node không có registry.
Đáp án đúng: A

9. Khi cần định tuyến HTTP và chính sách L7 trong ambient mode, thành phần nào cần thêm?
A. Ztunnel tự đọc HTTP path và áp chính sách L7 mặc định.
B. Waypoint Envoy xử lý route và policy HTTP ở Layer 7.
C. CoreDNS áp luật HTTP dựa trên hostname của request.
D. Kube-proxy áp luật HTTP dựa trên header và method.
Đáp án đúng: B

10. Workload ambient dùng ztunnel mà không gắn waypoint. Tính năng nào thường chưa có ở tầng đó?
A. Mã hóa mTLS giữa các workload đã gia nhập ambient mesh.
B. Xác thực danh tính peer ở đường truyền do ztunnel bảo vệ.
C. Route theo HTTP path và kiểm tra HTTP method tại L7.
D. Policy L4 dựa trên danh tính nguồn và port dịch vụ.
Đáp án đúng: C

11. Dịch vụ sidecar và dịch vụ ambient cùng thuộc một Istio mesh. Nhận định nào đúng?
A. Hai mode không thể giao tiếp trừ khi tắt mTLS toàn mesh.
B. Sidecar luôn phải đổi thành waypoint cho mọi Pod ambient.
C. Workload sidecar vẫn tương tác được với ambient trong cùng mesh.
D. Ambient chỉ hoạt động ở cluster không hề có sidecar.
Đáp án đúng: C

12. Service có waypoint cho HTTP, nhưng client gọi thẳng Pod IP, bỏ qua đường Service. Rủi ro nào cần xét?
A. Istiod sẽ tự thêm waypoint vào Pod đích ngay tức thì.
B. Ztunnel vẫn tự thực thi mọi kiểm tra HTTP header như waypoint.
C. Kube-proxy luôn viết lại Pod IP thành Service để giữ L7.
D. Đường đi có thể không qua waypoint nên bỏ qua L7 policy.
Đáp án đúng: D

13. Muốn chuyển 10% request từ reviews v1 sang v2 ở sidecar mesh dùng API Istio. Chọn cấu hình nào?
A. VirtualService route tới hai subset với weight 90/10.
B. DestinationRule chỉ định mỗi Pod dùng CPU theo tỷ lệ 90/10.
C. PeerAuthentication phân phối kết nối mTLS theo tỷ lệ 90/10.
D. RequestAuthentication chọn phiên bản dựa trên JWT issuer.
Đáp án đúng: A

14. DestinationRule khai báo subset v2 cho Service reviews dựa trên điều gì?
A. Dựa trên nhãn Pod như version: v2 để nhóm các endpoint.
B. Tên Deployment được ghép trực tiếp từ giá trị TLS SNI.
C. Tên namespace của client gọi tới service đích.
D. Số port trên Service để phân chia phiên bản ứng dụng.
Đáp án đúng: A

15. VirtualService định tuyến đến subset v2 nhưng DestinationRule chưa định nghĩa v2. Hệ quả nào khả dĩ?
A. Envoy sẽ tự tạo Deployment v2 để hoàn thành routing.
B. Istiod sẽ đổi v2 thành v1 mà không cần cập nhật policy.
C. Route thiếu subset hợp lệ nên có thể gặp lỗi 503.
D. Kubernetes tự đổi nhãn v1 sang v2 của toàn bộ Pod.
Đáp án đúng: C

16. Để gửi yêu cầu có HTTP header x-canary=yes đến v2, Istio dùng cơ chế nào?
A. DestinationRule tls.mode khớp x-canary rồi thay subset.
B. VirtualService match HTTP header rồi route tới v2.
C. PeerAuthentication mtls.mode khớp header rồi chọn Pod v2.
D. ServiceEntry endpoints khớp header để sửa nhãn Pod.
Đáp án đúng: B

17. Một VirtualService có nhiều quy tắc HTTP match cùng đúng với request. Istio chọn route nào?
A. Rule match đầu tiên theo thứ tự trong VirtualService.
B. Quy tắc khớp cuối cùng vì nó ghi đè quy tắc trước.
C. Quy tắc có trọng số lớn nhất bất kể thứ tự match.
D. Quy tắc được sắp lại theo tên Pod trước khi route.
Đáp án đúng: A

18. Muốn hạn chế số kết nối upstream mà Envoy tạo ra cho Service. Nên cấu hình phần nào?
A. VirtualService http.match.uri với tiền tố tên endpoint.
B. PeerAuthentication mtls.mode với giá trị STRICT.
C. RequestAuthentication jwtRules.audiences theo tên upstream.
D. DestinationRule connectionPool giới hạn kết nối upstream.
Đáp án đúng: D

19. Một Pod upstream liên tục trả 5xx; muốn tạm loại endpoint khỏi pool cân bằng. Dùng gì?
A. VirtualService http.rewrite để đổi URI lỗi thành URI khác.
B. DestinationRule outlierDetection tạm loại endpoint lỗi.
C. PeerAuthentication chuyển mTLS từ STRICT sang PERMISSIVE.
D. Telemetry customTags để thay nhãn metric cho endpoint lỗi.
Đáp án đúng: B

20. Retry tự động một POST tạo đơn không có idempotency key có nguy cơ nào?
A. Luôn an toàn vì Envoy chỉ retry khi chưa mở TCP connection.
B. Không bao giờ được Istio phép cấu hình retry cho HTTP POST.
C. Tự hoàn tác lần ghi đầu bằng transaction chung của mesh.
D. Có thể nhân đôi đơn nếu lần đầu đã ghi thành công nhưng response mất.
Đáp án đúng: D

21. Muốn giới hạn thời gian xử lý của một HTTP request khi dùng API Istio. Đặt ở đâu?
A. DestinationRule trafficPolicy.loadBalancer cho HTTP route.
B. VirtualService http.timeout cho route ứng dụng tương ứng.
C. PeerAuthentication mtls.mode cho workload được gọi.
D. ServiceEntry location để giới hạn thời gian chờ.
Đáp án đúng: B

22. Thử nghiệm độ bền khi backend phản hồi chậm, muốn chủ động thêm độ trễ một số request. Dùng gì?
A. VirtualService fault.delay với một tỷ lệ request.
B. DestinationRule subsets.labels để trì hoãn scheduler.
C. AuthorizationPolicy action DENY để tạo độ trễ từng request.
D. PeerAuthentication mtls.mode để giả lập delay HTTP.
Đáp án đúng: A

23. Bật HTTP traffic mirroring tới bản canary. Cách hoạt động chuẩn của mirror là gì?
A. Thay route chính bằng canary rồi trả response của mirror.
B. Chờ cả hai response và luôn chọn kết quả nhanh hơn.
C. Gửi bản sao best-effort, trả response từ route gốc.
D. Buộc canary trả ACK rồi mới thực hiện route ban đầu.
Đáp án đúng: C

24. Dùng Istio Gateway và VirtualService CRD để mở ingress cho app. Quan hệ chính là gì?
A. Gateway nhận traffic; VirtualService điều phối route đích.
B. DestinationRule trực tiếp mở cổng public mà không cần Gateway.
C. AuthorizationPolicy tạo LoadBalancer rồi tự chỉ route HTTP.
D. Sidecar annotation tự sinh DNS công cộng cho mọi workload.
Đáp án đúng: A

25. Ingress gateway cần kết thúc HTTPS để xem HTTP path. Cấu hình TLS phù hợp là gì?
A. Dùng TLS passthrough nhưng vẫn match HTTP path tại gateway.
B. Gateway terminate TLS bằng cert hợp lệ rồi định tuyến HTTP.
C. Gửi HTTP từ client lên cổng 443 mà không cấu hình TLS.
D. Chuyển chứng thư private key sang Pod client để giải mã.
Đáp án đúng: B

26. Muốn khai báo dịch vụ HTTPS ngoài cluster cho registry Istio. Sử dụng gì?
A. ServiceEntry thêm host ngoài cluster vào registry của Istio.
B. DestinationRule tạo namespace Kubernetes mới ngoài cluster.
C. RequestAuthentication khai báo IP router của Internet gateway.
D. PeerAuthentication tự import DNS record vào service registry.
Đáp án đúng: A

27. Muốn kiểm soát tập trung traffic outbound của mesh qua một điểm. Chọn thiết kế nào?
A. Đặt mọi Service thành NodePort để traffic ra qua ingress.
B. Đổi CoreDNS sang external DNS rồi bỏ chính sách route.
C. Định tuyến outbound qua egress gateway được quản lý.
D. Bật access log trên mọi Pod và coi như đã chặn egress.
Đáp án đúng: C

28. Sidecar mesh dùng outboundTrafficPolicy REGISTRY_ONLY. Vì sao chưa thể coi đó là tường lửa chắc chắn?
A. Có thể bypass proxy nếu không chặn egress tại mạng.
B. REGISTRY_ONLY tự tạo NetworkPolicy chặn toàn bộ egress.
C. REGISTRY_ONLY tự mã hóa mọi kết nối ra Internet bằng mTLS.
D. Mesh tự thu hồi quyền network của Pod sau khi bật tùy chọn.
Đáp án đúng: A

29. PeerAuthentication mtls.mode STRICT cho một workload yêu cầu điều gì ở kết nối đến?
A. Cho cả plaintext lẫn mTLS qua proxy để dễ chuyển đổi.
B. Vô hiệu xác thực peer và giữ mã hóa một chiều TLS.
C. Chuyển toàn bộ traffic sang ingress gateway trước khi chấp nhận.
D. Chỉ chấp nhận kết nối mTLS hợp lệ ở điểm thực thi policy.
Đáp án đúng: D

30. PeerAuthentication đặt PERMISSIVE trong sidecar mesh thường có hành vi nào?
A. Từ chối mọi plaintext vì chỉ mTLS được chấp nhận.
B. Cho phép cả mTLS và plaintext đối với kết nối đến.
C. Chỉ cho TCP có JWT, không xét chế độ mTLS của peer.
D. Bắt client dùng chứng thư TLS từ CA công cộng Internet.
Đáp án đúng: B

31. Danh tính workload trong Istio mTLS thường gắn với đối tượng Kubernetes nào?
A. Tên node đang chạy Pod, kèm dung lượng CPU của node.
B. Địa chỉ IP Pod và cổng HTTP được dùng để kết nối.
C. ServiceAccount cùng namespace tạo workload identity.
D. Tên ConfigMap chứa biến môi trường của Deployment.
Đáp án đúng: C

32. Việc cấp và xoay vòng chứng thư mTLS workload trong Istio thường được quản lý thế nào?
A. Mỗi request cần ứng dụng tự ký root CA và cập nhật DNS.
B. Istio hỗ trợ cấp và luân chuyển cert ngắn hạn cho proxy.
C. Các proxy tải private key chung từ Docker image của app.
D. Kube-proxy phát hành chứng thư để mọi namespace dùng chung.
Đáp án đúng: B

33. DestinationRule tls.mode ISTIO_MUTUAL cho kết nối upstream có tác dụng gì?
A. Tắt mTLS để cho phép kết nối thẳng đến workload HTTP.
B. Chọn certificate của browser để xác thực client Internet.
C. Buộc upstream dùng chứng thư public CA thay cho Istio CA.
D. Dùng chứng thư và danh tính mesh do Istio cấp cho mTLS.
Đáp án đúng: D

34. Có AuthorizationPolicy DENY và ALLOW cùng khớp một request. Kết quả mong đợi là gì?
A. Quy tắc ALLOW có ưu tiên và bỏ qua DENY đang khớp.
B. Hai quy tắc triệt tiêu nhau nên request luôn được cho qua.
C. Quy tắc DENY có ưu tiên và chặn request đang khớp.
D. Quy tắc tạo mới hơn sẽ thắng bất kể action.
Đáp án đúng: C

35. Không có AuthorizationPolicy ALLOW hay DENY áp dụng cho workload. Mặc định access thế nào?
A. Istio mặc định chặn mọi inbound cho tới khi có ALLOW.
B. Istio tự yêu cầu JWT cho mọi request nội bộ mesh.
C. Istio chỉ cho phép traffic từ ingress gateway bất kể policy.
D. Mặc định được phép nếu không có policy áp dụng.
Đáp án đúng: D

36. Một AuthorizationPolicy ALLOW được áp dụng cho workload với một rule có điều kiện. Request không khớp rule thì sao?
A. Request vẫn được cho qua vì ALLOW chỉ ghi log kiểm toán.
B. Request tự chuyển sang sidecar khác để thử rule mới.
C. Không khớp rule ALLOW nào thì request bị chặn.
D. Request được đổi principal thành anonymous rồi cho qua.
Đáp án đúng: C

37. RequestAuthentication cấu hình JWT ở chế độ mặc định, request không gửi token. Điều gì thường xảy ra?
A. Request bị chặn 401 vì thiếu JWT bất kể cấu hình khác.
B. Request được tự cấp JWT mới từ issuer trong policy.
C. Request luôn có principal từ service account của browser.
D. Có thể qua JWT authn nhưng không có request principal.
Đáp án đúng: D

38. Muốn buộc request HTTP có JWT hợp lệ, nên phối hợp hai chính sách nào?
A. PeerAuthentication STRICT và DestinationRule connectionPool.
B. ServiceEntry endpoints và VirtualService fault abort.
C. Dùng RequestAuthentication kiểm JWT và AuthorizationPolicy đòi principal.
D. RequestAuthentication kết hợp PeerAuthentication STRICT ở workload.
Đáp án đúng: C

39. Trong ambient mode, một policy kiểm tra HTTP path cần thực thi ở waypoint. Cách gắn policy phù hợp?
A. AuthorizationPolicy selector áp trên Pod để ztunnel đọc HTTP path.
B. PeerAuthentication STRICT tự kiểm tra tất cả HTTP path.
C. DestinationRule subsets đặt path vào nhãn phiên bản.
D. AuthorizationPolicy targetRefs tham chiếu Service dùng waypoint.
Đáp án đúng: D

40. Để tránh đường gọi Pod IP bỏ qua waypoint và né L7 policy, biện pháp nào phù hợp?
A. Policy L4 chỉ cho identity waypoint truy cập Pod đích.
B. Bỏ mọi L4 policy vì waypoint mặc định chặn đường Pod IP.
C. Đổi DNS TTL của Service để Pod IP tự trỏ về waypoint.
D. Tăng replica waypoint để ngăn mọi kết nối trực tiếp.
Đáp án đúng: A

41. Nhóm metrics nào hữu ích để xem chất lượng gọi giữa các dịch vụ qua Istio?
A. CPU idle, kích thước image và tuổi node không có request.
B. Request rate, error rate và latency kèm nhãn dịch vụ liên quan.
C. Số replica Deployment và thời gian chạy CronJob mỗi ngày.
D. Kích thước PersistentVolume và ngày gia hạn DNS domain.
Đáp án đúng: B

42. Các trace span ở hai microservice không nối thành một đường gọi. Cần kiểm tra gì?
A. Mesh có tự đồng bộ đồng hồ của mọi node bằng DNS không.
B. Workload có cùng phiên bản container image với nhau không.
C. Ứng dụng có truyền tiếp trace context giữa các hop hay không.
D. Gateway có bật certificate revocation check hay không.
Đáp án đúng: C

43. Muốn cấu hình thu thập access log hoặc tracing theo workload trong Istio, tài nguyên nào phù hợp?
A. ServiceEntry để cấu hình đường dẫn log nội bộ của container.
B. Telemetry resource để điều khiển logging, tracing và metrics.
C. DestinationRule chỉ định tên trace collector trong subset label.
D. PeerAuthentication định nghĩa mẫu log và định dạng span.
Đáp án đúng: B

44. Sau khi thay đổi nhiều manifest mesh, muốn dò lỗi cấu hình trước khi debug gói tin. Lệnh nào phù hợp?
A. istioctl proxy-status để tự sửa toàn bộ manifest thiếu.
B. kubectl rollout undo để phân tích conflict VirtualService.
C. istioctl dashboard để tự động sửa quy tắc AuthorizationPolicy.
D. istioctl analyze để kiểm tra và cảnh báo sai cấu hình Istio.
Đáp án đúng: D

45. Sidecar không nhận cấu hình mới từ istiod; nên xem lệnh nào trước để kiểm tra trạng thái đồng bộ xDS?
A. istioctl analyze để đọc HTTP body của request bị lỗi.
B. kubectl top nodes để hiển thị xDS route ở tất cả proxy.
C. istioctl proxy-status để kiểm tra đồng bộ xDS.
D. istioctl manifest generate để so sánh access log request.
Đáp án đúng: C

46. Muốn kiểm tra route HTTP thật sự đã được đẩy vào Envoy sidecar của Pod, dùng gì?
A. istioctl proxy-config secrets <pod> để xem endpoint HTTP.
B. istioctl proxy-status <pod> để sửa rule match trực tiếp.
C. istioctl analyze <pod> để đọc route runtime của Envoy.
D. istioctl proxy-config routes <pod> để xem route đã nạp.
Đáp án đúng: D

47. Envoy trả 503 vì không có upstream khỏe, bước kiểm tra nào trực tiếp nhất?
A. Chỉ tăng timeout VirtualService rồi coi endpoint đã tồn tại.
B. istioctl proxy-config endpoints để kiểm tra upstream.
C. Đổi tên Kubernetes namespace của Service bị trả mã lỗi.
D. Thay mtls STRICT bằng DISABLE mà không xem cluster.
Đáp án đúng: B

48. Request bị 403 RBAC: access denied qua sidecar mesh; nên kiểm tra gì đầu tiên?
A. Kiểm tra AuthorizationPolicy và principal ở đích.
B. Kích thước PVC và số lần restart của CoreDNS Pod.
C. Tên Deployment của istiod và TTL của Service DNS record.
D. Thứ tự init container và loại storage class đã gắn.
Đáp án đúng: A

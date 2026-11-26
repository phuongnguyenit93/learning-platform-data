# Danh sách kiểm tra thiết kế, bảo mật và vận hành

Trong chương **Lựa chọn kiến trúc** của module Spring Cloud Kubernetes (`SPRING_CLOUD_KUBERNETES`), bài học này cung cấp danh sách kiểm tra trước khi đưa ứng dụng Spring tích hợp Kubernetes vào vận hành hoặc thay đổi một thiết kế đang chạy.

Phạm vi gồm DiscoveryClient, ConfigMap, Secret, Spring Cloud LoadBalancer, Configuration Watcher, quyền RBAC và sức khỏe Pod. Mục tiêu là chứng minh từng tính năng cần thiết, được cấp đúng quyền và có hành vi đã biết khi cập nhật hoặc gặp sự cố.

Một manifest được API server chấp nhận chưa chứng minh ứng dụng vận hành đúng. Một Pod Ready cũng chưa chứng minh nó dùng đúng cấu hình, gọi đúng backend hoặc có thể quay lui.

Sau bài học, bạn cần:

- Chuyển một yêu cầu kiến trúc thành tiêu chí có thể kiểm chứng.
- Đánh giá quyền cần có và quyền phải bị từ chối theo từng thành phần.
- Phân biệt cập nhật resource, nhận cấu hình và thay đổi hành vi nghiệp vụ.
- Kiểm tra khả năng phục hồi, quan sát và quay lui của cả ứng dụng lẫn controller.
- Ghi nhận phần chưa kiểm chứng thay vì đánh dấu hoàn thành theo cảm tính.

## 1. Cách sử dụng danh sách

Áp dụng danh sách khi tạo ứng dụng mới, đổi starter/BOM, mở rộng namespace, bổ sung controller, thay cơ chế cập nhật cấu hình hoặc thay đổi quyền truy cập.

Với mỗi mục, ghi ít nhất:

| Trường | Nội dung |
| --- | --- |
| Mã mục | Ví dụ `TK01`, `RB03`, `VH02` |
| Phạm vi | Ứng dụng, controller, namespace và phiên bản đang xét |
| Người phụ trách | Người hoặc đội chịu trách nhiệm xử lý |
| Kết quả | `PASS`, `FAIL`, `NOT_RUN` hoặc `N/A` |
| Bằng chứng | Manifest có hiệu lực, dependency graph, phép thử, log hoặc số liệu đã khử dữ liệu nhạy cảm |
| Việc còn lại | Thay đổi cần thực hiện và tiêu chí kiểm tra lại |

Quy tắc đánh giá:

- `PASS`: có bằng chứng đúng phạm vi và đúng phiên bản được xét.
- `FAIL`: đã thấy hành vi trái yêu cầu hoặc quyền vượt phạm vi.
- `NOT_RUN`: chưa có phép kiểm tra hoặc chưa đủ bằng chứng.
- `N/A`: tính năng không được chọn; ghi rõ lý do và xác nhận nó không vô tình được bật.

Không dùng `N/A` cho một tính năng đang hoạt động nhưng chưa biết cách kiểm tra. Các ô trong bài là mẫu để người học áp dụng, không phải kết quả xác minh của một hệ thống cụ thể.

Tách ba câu hỏi xuyên suốt:

```text
Resource Kubernetes đã thay đổi chưa?
→ Tiến trình ứng dụng đã nhìn thấy thay đổi chưa?
→ Hành vi nghiệp vụ đã sử dụng trạng thái mới chưa?
```

Mỗi câu cần bằng chứng riêng, đặc biệt với cấu hình động và danh sách instance.

## 2. Kiểm tra thiết kế và tính năng thực sự cần

- [ ] **TK01 — Có yêu cầu cho từng tính năng.** Ghi rõ vì sao cần DiscoveryClient, LoadBalancer, Config PropertySource, Watcher hoặc leader election. Một đường gọi chỉ cần Service DNS không tự tạo ra nhu cầu đọc Kubernetes API.
- [ ] **TK02 — Có sơ đồ đường dữ liệu và đường điều khiển.** Chỉ ra caller, Service/Pod đích, tiến trình đọc API, nguồn cấu hình và nơi phát refresh. Đừng chỉ vẽ luồng HTTP nghiệp vụ rồi bỏ qua controller.
- [ ] **TK03 — Phạm vi namespace và tenant rõ ràng.** Liệt kê namespace được đọc, quy tắc tên Service, label lọc và cách xử lý Service ID trùng nhau. Không mặc định mở `all-namespaces`.
- [ ] **TK04 — Có người sở hữu thành phần dùng chung.** Nếu dùng Discovery Server, Configuration Watcher hoặc broker cho Spring Cloud Bus, ghi đội vận hành, cách nâng cấp và ngân sách lỗi của chúng.
- [ ] **TK05 — Các lựa chọn và hệ quả được ghi lại.** Có ADR giải thích điều kiện chọn, điều kiện xem xét lại và những giả định chưa được kiểm chứng.

Bảng kiểm kê tính năng nên đủ cụ thể để suy ra quyền:

| Tính năng | Tiến trình thực hiện | Dữ liệu hoặc endpoint cần truy cập |
| --- | --- | --- |
| Discovery trực tiếp | Ứng dụng consumer | Service và tài nguyên endpoint được implementation sử dụng |
| HTTP discovery | Discovery Server đọc API; consumer gọi HTTP | Catalog server và địa chỉ backend |
| ConfigMap qua file mount | Kubelet mount; ứng dụng đọc file | Đường dẫn file và quyền trong container |
| ConfigMap qua API | Client trong ứng dụng | ConfigMap đúng nguồn và namespace |
| Watcher refresh HTTP | Controller và ứng dụng đích | Resource được theo dõi, discovery và endpoint refresh |
| Leader election | Candidate tham gia điều phối | Resource khóa và các tài nguyên mà implementation cần |

Bảng này không thay thế việc kiểm tra implementation. Nó giúp phát hiện các quyền được thêm vào mà không có tính năng tương ứng.

## 3. Kiểm tra phiên bản và dependency

- [ ] **PB01 — Bộ phiên bản được chốt đầy đủ.** Ghi Spring Boot, Spring Cloud BOM, Spring Cloud Kubernetes, JDK, công cụ build và client Kubernetes thực sự được resolve.
- [ ] **PB02 — Không trộn hai họ starter.** Kiểm tra chỉ dùng họ Fabric8 hoặc Kubernetes Java Client theo thiết kế. Không thêm starter `-all` để chữa một lỗi thiếu bean chưa hiểu nguyên nhân.
- [ ] **PB03 — Không có override phiên bản bị bỏ sót.** Đọc effective build và dependency graph với cùng profile/tham số như CI; rà soát dependency hoặc BOM khác đang thay phiên bản.
- [ ] **PB04 — API và vòng đời hỗ trợ đã được xét.** Đối chiếu Boot/Cloud, tài liệu đúng dòng, client/cluster và các API dùng trong discovery, cấu hình hoặc leader election. `Stable` không đồng nghĩa còn được bảo trì vô thời hạn.

Các starter Fabric8 và Kubernetes Java Client không được dùng lẫn theo hướng dẫn Spring Cloud Kubernetes. [Starters](https://docs.spring.io/spring-cloud-kubernetes/reference/5.0/getting-started.html)

Tra thế hệ dự án tại [Spring Generations](https://spring.io/projects/generations/) và tiếp tục xác minh BOM cụ thể; không suy tương thích chỉ từ việc các số phiên bản trông gần nhau.

Với controller triển khai bằng image riêng, ghi phiên bản image thực tế. Thay Cloud BOM trong ứng dụng không tự thay image Discovery Server hoặc Watcher.

## 4. Kiểm tra discovery và chọn đích

- [ ] **DV01 — Biết chính xác ai phân giải và chọn backend.** Phân biệt HTTP client thường qua DNS, DiscoveryClient trả danh sách và HTTP client tích hợp LoadBalancer. Kiểm tra qualifier/bean để không dùng nhầm client.
- [ ] **DV02 — Danh sách instance đúng phạm vi.** Đối chiếu namespace, label trên Service, Service ID, trạng thái endpoint, host, port và thuộc tính secure với dữ liệu Kubernetes.
- [ ] **DV03 — Đã kiểm tra nhiều slice và nhiều port.** Không lấy slice đầu tiên, không ghép Pod IP với Service port một cách tùy ý; xét loại trùng, họ địa chỉ và primary port.
- [ ] **DV04 — Biết cache nằm ở đâu.** Ghi cơ chế đồng bộ của discovery, cache bổ sung và cache LoadBalancer; đo thời gian thêm/loại instance khi workload thay đổi.
- [ ] **DV05 — Có ngân sách timeout và retry.** Thử khi không có instance, backend không kết nối được và timeout. Xác định retry ở caller, LoadBalancer, mesh hoặc gateway để tránh nhân số lần thử.
- [ ] **DV06 — Đường mạng nghiệp vụ đã được thử.** Nếu dùng Discovery Server hoặc caller ngoài cluster, gọi được catalog chưa đủ; caller phải kết nối được tới địa chỉ instance trả về.

EndpointSlice có thể chia backend một Service thành nhiều object và có endpoint trùng trong thời gian cập nhật; consumer cần tổng hợp đúng tập endpoint. [EndpointSlices — Kubernetes](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/)

Với starter LoadBalancer riêng của Spring Cloud Kubernetes, kiểm tra chế độ `POD` hay `SERVICE`. Với LoadBalancer chung dùng DiscoveryClient, kiểm tra supplier thực tế; không áp một property của starter khác rồi cho rằng đường đi đã đổi. [LoadBalancer for Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/load-balancer.html)

**Bằng chứng tốt:** URI đầu vào, instance được chọn, Pod đã trả lời và request ID liên kết log. Một lần HTTP 200 không đủ chứng minh lọc namespace, port hay readiness đúng.

## 5. Kiểm tra nguồn và vòng đời cấu hình

- [ ] **CH01 — Mỗi thuộc tính quan trọng có nguồn rõ ràng.** Ghi file đóng gói, profile, biến môi trường, file mount, API PropertySource hoặc tham số khởi động. Kiểm tra nguồn nào ghi đè nguồn nào.
- [ ] **CH02 — Cấu hình bắt buộc được kiểm tra khi startup.** Thử thiếu nguồn, thiếu key, sai kiểu và giá trị ngoài miền hợp lệ. Nếu đọc qua API, có quyết định rõ về fail-fast và retry có giới hạn.
- [ ] **CH03 — Cách truyền dữ liệu khớp kỳ vọng cập nhật.** Phân biệt `env/envFrom`, file volume, `subPath` và đọc API; kiểm chứng hành vi của cách đang dùng.
- [ ] **CH04 — Mỗi nhóm thuộc tính có chiến lược áp dụng.** Xác định thuộc tính nào refresh được, thuộc tính nào cần tạo lại bean/tài nguyên và thuộc tính nào cần rollout tiến trình.
- [ ] **CH05 — Có mã phiên bản cấu hình không nhạy cảm.** Có thể đối chiếu revision hiệu lực ở từng Pod mà không đưa giá trị Secret hoặc toàn bộ Environment ra ngoài.
- [ ] **CH06 — Cấu hình và artifact quay lui được ghép đúng.** Ghi phiên bản image, tên/phiên bản ConfigMap và tham chiếu Secret tương ứng; không chỉ giữ một revision Deployment.

Kubernetes không tự thay biến môi trường của tiến trình đang chạy khi ConfigMap đổi. Volume được đồng bộ theo cơ chế của kubelet; mount bằng `subPath` không nhận cập nhật như volume thông thường. [ConfigMaps — Kubernetes](https://kubernetes.io/docs/concepts/configuration/configmap/)

File đã đổi chưa chứng minh Spring đã cập nhật bean. Tương tự, HTTP refresh thành công chưa chứng minh HTTP connector, connection pool hoặc một bean bất biến đã được tạo lại đúng.

Bảng quyết định nên gắn với từng thuộc tính:

| Nhóm thuộc tính | Điều cần kiểm chứng |
| --- | --- |
| Nội dung hiển thị hoặc cờ chức năng | Request mới quan sát giá trị mới theo cơ chế cập nhật đã chọn |
| Timeout của HTTP client | Client thực sự được tái cấu hình; không chỉ Environment đổi |
| Credential cơ sở dữ liệu | Kết nối mới sử dụng credential mới; pool cũ được xử lý theo kế hoạch |
| Port, địa chỉ bind hoặc cấu hình nền tảng startup | Có cần chạy lại tiến trình không? |
| Nguồn import và quyền đọc cấu hình | Được thiết lập trước khi cần đọc chính nguồn đó |

Nếu dùng `spring.cloud.kubernetes.config.fail-fast`, kiểm tra ý nghĩa và điều kiện retry theo phiên bản. Nó không thay thế validation cho mọi thuộc tính nghiệp vụ hoặc mọi nguồn file. [ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/configmap-propertysource.html)

## 6. Kiểm tra Secret và dữ liệu nhạy cảm

- [ ] **BM01 — Secret được phân loại đúng.** Không đặt credential, private key hoặc token trong ConfigMap, annotation, URL hoặc manifest mẫu chứa giá trị thật. Base64 không phải mã hóa bảo mật.
- [ ] **BM02 — Có lý do nếu ứng dụng đọc Secret qua API.** Với thiết kế chỉ đọc file mount, không cấp thêm `list/watch secrets` cho ứng dụng chỉ vì Secret đó được gắn vào Pod.
- [ ] **BM03 — Đã kiểm tra đường đọc và quyền file.** Xác nhận key, đường dẫn import, quyền đọc của user trong container và hành vi khi Secret bắt buộc thiếu; không in nội dung Secret để làm bằng chứng.
- [ ] **BM04 — Có phép thử rotation.** Kiểm tra credential mới, kết nối/pool đang tồn tại, cửa sổ chấp nhận credential cũ và phương án phục hồi nếu quá trình chuyển đổi lỗi.
- [ ] **BM05 — Đã kiểm tra rò rỉ qua quan sát.** Rà log startup/lỗi, stack trace, cấu hình debug, Actuator, thông tin discovery và tài liệu hỗ trợ; dữ liệu được che phải được kiểm tra thực tế.

Kubernetes Secret cần được bảo vệ cả ở quyền truy cập và lớp lưu trữ; ứng dụng không thể chỉ dựa vào tên loại resource để suy dữ liệu đã được bảo vệ đầy đủ. [Good Practices for Kubernetes Secrets](https://kubernetes.io/docs/concepts/security/secrets-good-practices/)

Quyền list Secret có thể cho phép đọc dữ liệu của nhiều Secret trong namespace. Chọn API hoặc volume dựa trên nhu cầu cụ thể và phạm vi quyền, không cấp quyền rộng để loại bỏ một lỗi cấu hình. [Secrets — Kubernetes](https://kubernetes.io/docs/concepts/configuration/secret/)

**Bằng chứng phù hợp:** tên nguồn, metadata phiên bản được phép chia sẻ, trạng thái validation và kết quả xác thực nghiệp vụ. Không lấy bản dump Secret, token hay một hash tự tạo từ mật khẩu làm mã phiên bản công khai.

## 7. Kiểm tra danh tính và RBAC

- [ ] **RB01 — Xác định ServiceAccount của Pod thực tế.** Đọc Pod đang chạy; đừng suy quyền ứng dụng từ tài khoản quản trị dùng `kubectl`.
- [ ] **RB02 — Mỗi quyền gắn với một thao tác.** Liệt kê API group, resource, verb, namespace và tiến trình cần nó. Bao gồm quyền đọc của controller và quyền ghi khóa nếu có leader election.
- [ ] **RB03 — Có cả kiểm tra được phép và bị từ chối.** Không chỉ kiểm tra discovery hoạt động; xác nhận các thao tác đọc Secret, ghi workload hoặc truy cập namespace khác bị từ chối khi không có nhu cầu.
- [ ] **RB04 — Tách identity của ứng dụng và controller.** RoleBinding cho Watcher hoặc Discovery Server không tự cấp quyền cho ứng dụng và ngược lại.
- [ ] **RB05 — Hiểu giới hạn của `resourceNames` và filter.** Đối chiếu client có dùng get theo tên hay list/watch; label filter không tự thu hẹp quyền RBAC đã cấp.
- [ ] **RB06 — Token chỉ được cung cấp theo nhu cầu.** Kiểm kê token mặc định, token projected hoặc danh tính workload đang dùng; chỉ tắt mount mặc định sau khi xác nhận các tính năng còn lại không cần nó.

RBAC dùng đúng API group và namespace. Với EndpointSlice, resource thuộc `discovery.k8s.io`; với ConfigMap/Secret, resource thuộc core API. Quyền `get` không tự bao gồm `list/watch`. [RBAC Authorization — Kubernetes](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)

Khả năng đọc một Secret được mount không đồng nghĩa ServiceAccount ứng dụng phải có quyền lấy Secret qua API. Ngược lại, không có token API mặc định chưa chứng minh mọi kết nối HTTP discovery hoặc refresh đã được bảo vệ. [Service Accounts — Kubernetes](https://kubernetes.io/docs/concepts/security/service-accounts/)

Một ma trận quyền giúp phát hiện việc cấp thừa:

| Danh tính | Có thể cần | Không tự phát sinh từ nhu cầu đó |
| --- | --- | --- |
| Ứng dụng chỉ gọi Service DNS | Quyền kết nối tới dịch vụ | List mọi Service/Secret |
| Consumer discovery trực tiếp | Read/watch tài nguyên discovery đúng phạm vi | Update/delete Deployment |
| Ứng dụng chỉ đọc Secret mount | Quyền đọc file trong container | List Secret qua API |
| Watcher đang theo dõi ConfigMap | Quyền đọc nguồn và thông báo đích | Theo dõi mọi Secret trên cluster |
| Candidate leader election | Quyền của implementation khóa đã chọn | Quyền quản trị toàn cluster |

Nếu cần ngoại lệ, ghi quyền cụ thể, lý do, chủ sở hữu và thời điểm xem xét lại.

## 8. Kiểm tra mạng, TLS, endpoint quản trị và container

- [ ] **AT01 — TLS và danh tính được xác minh.** Kiểm tra CA, hostname, hạn chứng chỉ và cơ chế xác thực cho API server, discovery HTTP, broker và endpoint quản trị; không dùng bỏ kiểm tra TLS để chữa lỗi lâu dài.
- [ ] **AT02 — Có ma trận kết nối.** Bao gồm DNS, API hoặc Discovery Server, backend nghiệp vụ, Watcher tới Actuator và broker nếu sử dụng.
- [ ] **AT03 — Actuator được mở và bảo vệ theo nhu cầu.** Kiểm tra exposure, authentication, authorization, port/path và hành vi POST; không mở `*` hoặc tắt toàn bộ security để làm refresh hết 403.
- [ ] **AT04 — Policy mạng có hiệu lực thực tế.** Kiểm tra plugin mạng có thực thi policy và thử cả đường được phép lẫn bị chặn. Một file NetworkPolicy được chấp nhận chưa chứng minh chính sách đã được thực thi.
- [ ] **AT05 — Image chạy được với chính sách container đã chọn.** Kiểm tra user không đặc quyền, khả năng tăng quyền, capabilities, seccomp, filesystem và volume ghi tạm theo yêu cầu môi trường.

NetworkPolicy không tự cung cấp phân quyền HTTP cho từng URL hoặc Service ID. Việc ai được gọi `/actuator/refresh` hay xem catalog discovery vẫn cần cơ chế thích hợp. [Network Policies — Kubernetes](https://kubernetes.io/docs/concepts/services-networking/network-policies/)

Với filesystem chỉ đọc hoặc user không phải root, chạy đúng image để chứng minh JVM có các đường ghi cần thiết và đọc được Secret. Không chỉ kiểm tra manifest có các field hardening. [Security Checklist — Kubernetes](https://kubernetes.io/docs/concepts/security/security-checklist/)

Đối với API quản trị, kiểm tra thêm việc dữ liệu được che, response lỗi không lộ cấu hình và chỉ chủ thể đã chọn được thay đổi trạng thái. Exposure và quyền truy cập là các lớp cấu hình khác nhau.

## 9. Kiểm tra Configuration Watcher nếu được chọn

- [ ] **WT01 — Nguồn được theo dõi là có chủ đích.** Đối chiếu namespace, nhãn nguồn, tên hoặc ánh xạ ứng dụng và quyền của controller theo đúng phiên bản.
- [ ] **WT02 — Chọn một cơ chế thông báo rõ ràng.** Nếu HTTP, kiểm tra discovery, port/path Actuator và bảo vệ endpoint; nếu Bus, kiểm tra broker, danh tính và tập ứng dụng có thể nhận sự kiện.
- [ ] **WT03 — Đã kiểm tra hiệu lực trên từng instance.** Sau thay đổi một giá trị không nhạy cảm, đối chiếu revision hiệu lực và request nghiệp vụ ở tất cả replica cần nhận.
- [ ] **WT04 — Tính đến dữ liệu mount cập nhật trễ.** Xác minh file đã có giá trị mới trước khi đánh giá refresh; không coi một khoảng delay cố định là bảo đảm cho mọi cluster.
- [ ] **WT05 — Hành vi với sự kiện lặp hoặc bỏ lỡ được biết.** Thử controller restart, thay đổi nhanh liên tiếp và lỗi gọi refresh. Không giả định mỗi thay đổi trung gian chắc chắn được áp dụng đúng một lần.
- [ ] **WT06 — Phạm vi HA và tác động được xét.** Với nhiều replica controller, kiểm tra tính năng HA thực sự được hỗ trợ và bật; không suy số replica thành cơ chế phối hợp tự động.

Configuration Watcher hỗ trợ thông báo HTTP hoặc Spring Cloud Bus. Nhãn chọn nguồn, theo dõi Secret và đường Actuator có điều kiện riêng; đối chiếu reference đúng phiên bản. [Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/5.0/spring-cloud-kubernetes-configuration-watcher.html)

Với HTTP, một cuộc gọi tới Service có thể chỉ đến một replica. Bằng chứng cập nhật toàn bộ cần xác định instance đích; gọi Service một lần rồi thấy giá trị mới không chứng minh mọi replica đã cập nhật.

Với Bus, ranh giới namespace Kubernetes chưa chắc trùng tập subscriber của broker. Kiểm kê đối tượng nhận sự kiện và quyền kết nối broker.

Nếu triển khai chỉ dùng cấu hình theo phiên bản và rollout, có thể đánh dấu nhóm Watcher `N/A` sau khi xác nhận không có controller, endpoint refresh hoặc auto-configuration cập nhật động ngoài thiết kế.

## 10. Kiểm tra probe, tài nguyên và vòng đời Pod

- [ ] **SK01 — Liveness phản ánh khả năng sống của tiến trình.** Không gộp mọi database, cache hoặc Kubernetes API vào liveness chỉ vì health tổng hợp tiện dùng.
- [ ] **SK02 — Readiness có ngữ nghĩa phục vụ rõ ràng.** Biết vì sao một instance bị loại khỏi traffic; cân nhắc tác động khi mọi replica cùng phụ thuộc một dịch vụ bên ngoài.
- [ ] **SK03 — Startup có ngân sách dựa trên đo đạc.** Tính cả thời gian đọc cấu hình, retry, khởi tạo cache và tác vụ startup; tăng probe budget không chữa được lỗi 403 hoặc sai kiểu cấu hình.
- [ ] **SK04 — Đúng port, path và security của probe.** Kiểm tra đường kubelet tới Pod; health ở management port riêng có thể không phản ánh cổng nghiệp vụ.
- [ ] **SK05 — Requests/limits phù hợp với JVM và tải.** Xét heap cùng bộ nhớ ngoài heap, thread, direct buffer, CPU throttling và startup dưới tài nguyên thực tế.
- [ ] **SK06 — Kết thúc tiến trình có giới hạn.** Thử graceful shutdown, request đang chạy, connection pool, loại endpoint và độ trễ client ngừng chọn Pod cũ.
- [ ] **SK07 — Tác vụ singleton có cơ chế riêng nếu cần.** Nếu dùng leader election, xác định implementation, khóa, role, thu hồi quyền và bảo vệ side effect; follower khỏe mạnh không nên bị coi là lỗi chỉ vì chưa là leader.

Ví dụ cấu hình health group tối thiểu cho ứng dụng Boot hỗ trợ Kubernetes probes:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true
        add-additional-paths: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState
```

Ví dụ này không tự kiểm tra đủ điều kiện nghiệp vụ của mọi ứng dụng. Nó làm rõ việc tách hai nhóm và cung cấp `/livez`, `/readyz` trên cổng ứng dụng; cần kiểm chứng cùng security chain và Pod spec thực tế. [Kubernetes Probes — Spring Boot](https://docs.spring.io/spring-boot/4.0/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)

Readiness thất bại không trực tiếp restart container. Khi restart tăng, đối chiếu liveness/startup Events, log trước đó, exit code và termination reason. `OOMKilled` là hướng điều tra khác với sai đường dẫn probe.

## 11. Kiểm tra quan sát và xử lý sự cố

- [ ] **VH01 — Có mục tiêu và ngân sách vận hành.** Chốt độ trễ gọi nghiệp vụ, lỗi chấp nhận được, độ trễ cập nhật instance/cấu hình và thời gian phục hồi phù hợp với yêu cầu.
- [ ] **VH02 — Có thể truy vết đúng tiến trình.** Log có Pod/UID hoặc thông tin liên kết tương đương, revision image/cấu hình không nhạy cảm và correlation ID khi cần.
- [ ] **VH03 — Có tín hiệu cho lỗi từng lớp.** Quan sát lỗi API, list/watch hoặc cache startup, danh sách rỗng, refresh thất bại, revision lệch giữa replica, restart và độ trễ gọi backend.
- [ ] **VH04 — Có runbook thực hiện được.** Từ cảnh báo, người trực biết kiểm tra context, Pod/container, Events, log hiện tại và log lần trước, identity và trạng thái dependency.
- [ ] **VH05 — Cảnh báo có chủ sở hữu và hành động.** Phân biệt lỗi lookup, không có backend và backend trả lỗi; tránh phản ứng mặc định bằng restart toàn bộ.

Số liệu cần có mẫu đo và ngữ cảnh. “Không có log lỗi” không chứng minh controller đang theo dõi hoặc ứng dụng đang dùng dữ liệu mới.

Giữ request ID trong log/tracing khi phù hợp; tránh biến mọi request ID, Pod UID hoặc revision thay đổi liên tục thành label metric không giới hạn.

Runbook nên tách các chuỗi điều tra:

```text
Gọi nghiệp vụ lỗi
→ DNS/discovery có dữ liệu đúng không?
→ client đã chọn host/port nào?
→ đường mạng và backend có phục vụ không?

Cấu hình chưa đổi hành vi
→ resource đã đổi?
→ file/API source đã cập nhật?
→ thông báo/refresh/rollout đã xảy ra?
→ từng instance đã dùng revision nào?
```

Không dùng response health `UP` của Discovery Server hoặc Watcher như bằng chứng duy nhất cho độ mới và tính đầy đủ của dữ liệu.

## 12. Kiểm tra triển khai và quay lui

- [ ] **TKH01 — Artifact có thể định danh.** Ghi image digest hoặc định danh artifact bất biến, dependency graph và cấu hình triển khai có hiệu lực.
- [ ] **TKH02 — Có kế hoạch tương thích khi nâng cấp một phần.** Thử ứng dụng mới với controller/client cũ trong phạm vi được hỗ trợ; quản lý image server và Watcher riêng.
- [ ] **TKH03 — Có năng lực cho rollout.** Kiểm tra replica, chiến lược cập nhật, phần tài nguyên tăng thêm, thời gian startup và giới hạn sẵn sàng trong quá trình thay Pod.
- [ ] **TKH04 — Hiểu phạm vi disruption.** PDB có thể hỗ trợ giới hạn gián đoạn tự nguyện qua eviction phù hợp; không coi nó là bảo đảm cho mọi sự cố hoặc thay thế cấu hình rollout.
- [ ] **TKH05 — Quay lui phục hồi cả bộ trạng thái cần thiết.** Bao gồm image, ConfigMap/Secret được tham chiếu, tương thích schema dữ liệu và controller liên quan.
- [ ] **TKH06 — Có tiêu chí dừng mở rộng canary.** Đặt điều kiện dựa trên lỗi, độ trễ, dữ liệu discovery/cấu hình và quyền; không chỉ dựa vào rollout đã báo hoàn tất.

Deployment revision chủ yếu theo Pod template. `rollout undo` không tự đưa nội dung một ConfigMap/Secret mutable bên ngoài template về giá trị cũ. [Deployments — Kubernetes](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)

PDB không ngăn mọi gián đoạn ngoài ý muốn và không phải cơ chế điều khiển cập nhật của Deployment. Phải xét riêng rollout, eviction và mất node. [Disruptions — Kubernetes](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/)

Với credential đã bị thu hồi, kế hoạch quay lui không thể chỉ khôi phục tên Secret cũ rồi giả định credential đó vẫn dùng được.

## 13. Thu thập một bộ bằng chứng tối thiểu

Các lệnh dưới đây minh họa quan sát một ứng dụng trong môi trường kiểm thử. Thay context, namespace và tên Pod bằng giá trị thực tế; các kết quả chưa được giả định là đạt.

```powershell
$reviewContext = 'my-test-context'
$reviewNamespace = 'commerce'

kubectl --context $reviewContext -n $reviewNamespace get pods -l app=orders -o wide
kubectl --context $reviewContext -n $reviewNamespace get service orders
kubectl --context $reviewContext -n $reviewNamespace get endpointslices -l kubernetes.io/service-name=orders

# Thay bằng tên Pod vừa quan sát.
$reviewPodName = 'orders-7c8d9f6b5d-abcde'
$reviewPod = kubectl --context $reviewContext -n $reviewNamespace get pod $reviewPodName -o json | ConvertFrom-Json
$reviewPod.metadata.uid
$reviewPod.spec.serviceAccountName
$reviewPod.status.containerStatuses |
    Select-Object name, restartCount, state, lastState
```

Kiểm tra quyền bằng ServiceAccount thật:

```powershell
$reviewIdentity = "system:serviceaccount:" + $reviewNamespace + ":" + $reviewPod.spec.serviceAccountName

# Ví dụ quyền cần có nếu ứng dụng đọc EndpointSlice trực tiếp.
kubectl --context $reviewContext auth can-i list services -n $reviewNamespace --as=$reviewIdentity
kubectl --context $reviewContext auth can-i list endpointslices.discovery.k8s.io -n $reviewNamespace --as=$reviewIdentity
kubectl --context $reviewContext auth can-i watch endpointslices.discovery.k8s.io -n $reviewNamespace --as=$reviewIdentity

# Ví dụ quyền không được có trong thiết kế chỉ discovery và đọc file mount.
kubectl --context $reviewContext auth can-i list secrets -n $reviewNamespace --as=$reviewIdentity
kubectl --context $reviewContext auth can-i delete pods -n $reviewNamespace --as=$reviewIdentity
kubectl --context $reviewContext auth can-i list services -n other-tenant --as=$reviewIdentity
```

Ba phép thử cuối dự kiến bị từ chối trong phạm vi thiết kế nêu trên. Với hệ thống khác, ghi rõ vì sao kết quả mong đợi khác. Không mở quyền chỉ để tất cả lệnh đều trả `yes`.

`--as` yêu cầu quyền impersonation của người chạy. Nếu impersonation bị từ chối, phép thử chưa xác nhận được quyền của ứng dụng.

Khi cần điều tra startup/restart:

```powershell
kubectl --context $reviewContext -n $reviewNamespace describe pod $reviewPodName
kubectl --context $reviewContext -n $reviewNamespace logs $reviewPodName -c app --timestamps --tail=200
kubectl --context $reviewContext -n $reviewNamespace logs $reviewPodName -c app --previous --timestamps --tail=200
kubectl --context $reviewContext -n $reviewNamespace rollout status deployment/orders --timeout=240s
```

Thay tên container `app` nếu khác. Log lần trước chỉ tồn tại khi có lần chạy trước tương ứng; khi Pod đã bị thay thế, cần nguồn log tập trung theo UID/thời gian cũ.

Trước khi đưa bằng chứng vào ticket hoặc báo cáo, khử dữ liệu nhạy cảm. Không cần xuất toàn bộ Secret, Environment hoặc manifest có credential literal để chứng minh một kiểm tra đã đạt.

## 14. Ma trận thử nghiệm theo rủi ro thực tế

Chọn các hàng tương ứng tính năng đang dùng và ghi kết quả:

| Kịch bản | Điều cần chứng minh |
| --- | --- |
| Thiếu cấu hình bắt buộc | Không đưa instance thiếu điều kiện vào phục vụ; lỗi chỉ rõ nguồn/thuộc tính phù hợp |
| Sai kiểu hoặc giá trị cấu hình | Validation ngăn trạng thái không hợp lệ trước side effect |
| Sai quyền API | Phân biệt 403 với thiếu resource; retry không che lỗi cố định |
| API tạm không truy cập được | Startup, cache và stale policy có hành vi đã chốt |
| Pod backend không Ready hoặc bị thay | Client ngừng chọn đích trong ngân sách đã đo |
| Backend không còn instance | Lỗi và fallback đúng ngữ nghĩa; không tự chuyển sang tenant/Service khác |
| Cập nhật ConfigMap | Resource, nguồn đọc và từng replica đều được đối chiếu |
| Rotation Secret | Credential mới thực sự được dùng; xử lý kết nối cũ và quay lui rõ |
| Refresh một phần bị lỗi | Phát hiện revision lệch giữa replica và phục hồi có kiểm soát |
| Controller restart hoặc phát lặp | Không tạo vòng cập nhật hoặc side effect ngoài dự kiến |
| Rollout và quay lui | Image, cấu hình, credential và dữ liệu vẫn tương thích |
| Leader mất quyền, nếu có | Dừng nhận việc mới, xử lý việc đang chạy và cơ chế chống tác động trùng |

Không đưa mọi phép thử phá lỗi vào production chỉ để hoàn thành danh sách. Dùng môi trường kiểm thử thích hợp; với production, chọn phép quan sát hoặc thử nghiệm đã có phạm vi và quy trình tương ứng.

Đánh giá cả cold start và trạng thái đã làm đầy cache. Shadow test discovery chỉ cần so dữ liệu chọn đích; không gửi lặp giao dịch có side effect để “so hai đường”.

## 15. Ví dụ rà soát một thiết kế cụ thể

Giả sử `orders` có ba replica trong `commerce`:

- Cần metadata instance của `inventory`, nên dùng DiscoveryClient trực tiếp và LoadBalancer chọn Pod.
- ConfigMap `orders-runtime-r12` và Secret `orders-db-r4` được mount thành file.
- Cập nhật cấu hình được áp dụng bằng rollout theo phiên bản.
- Chưa dùng Discovery Server, Watcher hoặc leader election.

Kết luận kiểm kê ban đầu:

| Nhóm | Quyết định phải phản ánh trong triển khai |
| --- | --- |
| Discovery | Một họ client; đọc đúng namespace và tài nguyên endpoint |
| Cấu hình | Đường dẫn import hợp lệ; validation và revision hiệu lực rõ |
| Secret | Ứng dụng đọc file; không tự phát sinh nhu cầu list Secret qua API |
| Quyền | Chỉ các thao tác thực tế cần; có phép thử từ chối quyền ngoài phạm vi |
| Watcher | `N/A` có lý do; không mở refresh hoặc thêm controller ngoài thiết kế |
| Quay lui | Image cũ tham chiếu đúng bộ cấu hình và credential còn hợp lệ |

Trong buổi review giả định, nhóm phát hiện:

| Phát hiện | Mục bị ảnh hưởng | Hướng xử lý |
| --- | --- | --- |
| Liveness dùng health tổng hợp có database | `SK01` | Tách health group và thử database gián đoạn |
| ServiceAccount được gắn quyền quản trị cluster | `RB02`, `RB03` | Thu hẹp quyền; thử lại thao tác cần có và phải bị từ chối |
| Người vận hành chỉ ghi “rollout undo” | `CH06`, `TKH05` | Ghi bộ image/config/credential và kiểm chứng quay lui |
| Chỉ gọi Service một lần để xác nhận revision | `CH05`, `VH03` | Đối chiếu từng Pod bằng thông tin không nhạy cảm |
| `/actuator/refresh` được mở dù không dùng Watcher | `AT03`, `WT01` | Đưa endpoint về đúng nhu cầu và kiểm tra quyền truy cập |

Đây là ví dụ cách liên kết phát hiện với tiêu chí, không phải báo cáo của một workload đã chạy. Sau sửa, mục tương ứng vẫn là `NOT_RUN` cho đến khi có bằng chứng kiểm tra lại.

## 16. Chốt kết quả review

Một bản kết quả ngắn nên có:

```text
Phạm vi:
  Ứng dụng, controller, namespace, artifact và cấu hình được xét.

Tính năng được chọn:
  Liệt kê tính năng cần dùng và lý do của các mục N/A.

Bằng chứng:
  Dependency graph, quyền, dữ liệu discovery, revision hiệu lực,
  probe và kết quả các phép thử trong phạm vi.

Tồn tại:
  FAIL và NOT_RUN còn lại, người phụ trách, tiêu chí xử lý.

Điều kiện triển khai:
  Mục nào bắt buộc đạt trước khi mở rộng; ngoại lệ nào được chủ sở hữu chấp nhận.

Theo dõi sau triển khai:
  Chỉ số, cửa sổ quan sát, người trực và điều kiện quay lui.
```

Không lấy tỷ lệ ô đã đánh dấu làm quyết định duy nhất. Một mục về quyền đọc Secret, namespace chọn đích hoặc khả năng quay lui có thể quan trọng hơn nhiều mục trình bày đã hoàn tất.

Danh sách có giá trị khi mỗi quyết định thiết kế dẫn tới **quyền đúng, cấu hình có hiệu lực, tín hiệu quan sát được và cách phục hồi đã kiểm chứng**. Khi phiên bản, phạm vi hoặc cơ chế triển khai thay đổi, rà lại những mục bị ảnh hưởng thay vì mặc định kết quả cũ vẫn còn đúng.

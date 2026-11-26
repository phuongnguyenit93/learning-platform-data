Istio service mesh giải quyết những khó khăn nào về giao tiếp giữa microservice mà thư viện ứng dụng hoặc Kubernetes Service chưa giải quyết đầy đủ?
Bạn phân biệt trách nhiệm của service mesh, API gateway và Kubernetes Ingress trong một kiến trúc microservice như thế nào?
Bạn mô tả đường đi của một request từ Pod nguồn đến Pod đích khi cả hai tham gia mesh ở chế độ sidecar như thế nào?
Bạn giải thích sự khác nhau giữa control plane và data plane của Istio bằng các tình huống cấu hình và xử lý lưu lượng như thế nào?
Vai trò của istiod trong khám phá dịch vụ, phân phối cấu hình proxy và quản lý danh tính workload được thể hiện ra sao?
Bạn phân biệt trách nhiệm của Envoy proxy với ứng dụng nghiệp vụ khi xử lý kết nối, retry, timeout và telemetry như thế nào?
Bạn xác định những điều kiện về hệ thống, quy mô và đội ngũ vận hành khiến việc triển khai Istio có lợi hơn chi phí bổ sung như thế nào?
Bạn đánh giá tác động của mesh lên độ trễ, CPU, bộ nhớ và độ phức tạp xử lý sự cố trước khi áp dụng như thế nào?
Bạn phân biệt các chế độ triển khai sidecar và ambient của Istio về vị trí xử lý lưu lượng và phạm vi tính năng như thế nào?
Bạn giải thích cơ chế cung cấp cấu hình cho data plane bằng xDS và hệ quả khi cấu hình chưa được đồng bộ ra sao?
Bạn kiểm tra điều kiện tiên quyết của cụm Kubernetes, CNI và quyền truy cập trước khi cài Istio như thế nào?
Bạn lựa chọn phương án cài đặt và quản lý cấu hình Istio bằng istioctl, Helm hoặc quy trình GitOps dựa trên yêu cầu nào?
Bạn xác định các thành phần cần triển khai trước khi bật mesh cho một namespace đang chạy ứng dụng production như thế nào?
Bạn đánh giá cách sử dụng label namespace và revision để kiểm soát nhóm workload tham gia sidecar mesh ra sao?
Bạn kiểm tra sidecar injection đã xảy ra đúng với các Pod mong muốn bằng những bằng chứng nào?
Khi Pod mới không có Envoy sidecar, bạn phân biệt lỗi cấu hình injection, webhook và vòng đời Pod như thế nào?
Bạn giải thích cách lưu lượng được chuyển hướng từ ứng dụng qua proxy sidecar và vai trò của cấu hình mạng trong quá trình đó như thế nào?
Những trường hợp nào cần loại trừ một cổng hoặc luồng kết nối khỏi việc chuyển hướng qua sidecar, và bạn đánh giá rủi ro của ngoại lệ đó ra sao?
Bạn xử lý tình huống sidecar chưa sẵn sàng khiến ứng dụng khởi động nhưng không kết nối được dịch vụ khác ra sao?
Bạn cân nhắc ảnh hưởng của sidecar đến resource request, resource limit và vòng đời Pod trong Kubernetes như thế nào?
Bạn lựa chọn sidecar mode hoặc ambient mode cho workload có mật độ Pod lớn dựa trên mục tiêu tính năng và chi phí như thế nào?
Trong ambient mode, ztunnel đảm nhận những chức năng mạng và bảo mật nào ở tầng xử lý lưu lượng?
Bạn mô tả đường đi của kết nối giữa hai workload trong ambient mesh khi chưa sử dụng waypoint proxy như thế nào?
Trong ambient mesh, những yêu cầu xử lý HTTP hoặc phân quyền nào khiến bạn cần waypoint proxy thay vì chỉ sử dụng ztunnel?
Bạn phân biệt mức quan sát và chính sách ở L4 của ztunnel với khả năng ở L7 của waypoint proxy như thế nào?
Bạn thiết kế cách đưa từng namespace hoặc workload vào ambient mesh mà không làm gián đoạn các phiên đang hoạt động ra sao?
Khi chính sách L7 không có hiệu lực trong ambient mesh, bạn kiểm tra waypoint và luồng chuyển tiếp theo trình tự nào?
Bạn xác định dấu hiệu một workload bị cấu hình tham gia đồng thời các cơ chế bắt lưu lượng không tương thích như thế nào?
Bạn đánh giá giới hạn tính năng và khả năng tương thích của sidecar và ambient trước khi chuyển đổi một ứng dụng như thế nào?
Bạn chọn chiến lược dịch chuyển từ sidecar sang ambient theo từng nhóm dịch vụ và tiêu chí rollback nào?
Kubernetes Service, endpoint và thông tin registry được Istio sử dụng để khám phá workload đích như thế nào?
Bạn phân biệt định tuyến cấp Kubernetes Service với định tuyến logic của Istio VirtualService như thế nào?
Bạn tạo các subset phiên bản của một backend qua DestinationRule dựa trên nhãn workload như thế nào?
Bạn thiết kế VirtualService để chia lưu lượng giữa phiên bản ổn định và phiên bản canary theo tỷ trọng như thế nào?
Bạn kiểm tra nguyên nhân một cấu hình weighted routing không phân phối request theo tỷ lệ kỳ vọng bằng cách nào?
Bạn dùng HTTP match theo header, URI hoặc method để gửi yêu cầu tới những phiên bản backend khác nhau ra sao?
Bạn chọn rewrite URI hay redirect trong VirtualService dựa trên mong đợi của client và backend như thế nào?
Bạn đánh giá cách áp dụng routing cho lưu lượng HTTP so với TCP thuần khi chọn các tài nguyên Istio như thế nào?
Bạn lựa chọn timeout ở mức route theo SLA của request và khả năng đáp ứng của backend ra sao?
Bạn cấu hình retry và retry budget theo loại thao tác để tránh nhân đôi tác dụng phụ nghiệp vụ như thế nào?
Bạn nhận diện retry storm khi mesh và client ứng dụng cùng tự động thử lại trong lúc backend quá tải ra sao?
Bạn phân biệt lỗi 5xx có thể thử lại với lỗi do logic nghiệp vụ để tránh cấu hình retry không phù hợp như thế nào?
Bạn thiết kế circuit breaking và giới hạn connection pool trong DestinationRule theo năng lực backend như thế nào?
Bạn sử dụng outlier detection để tránh các endpoint lỗi liên tiếp mà không khiến toàn bộ backend bị loại khỏi pool ra sao?
Những đặc điểm tải và thời gian xử lý request nào khiến bạn chọn least request thay vì thuật toán cân bằng tải khác?
Bạn lựa chọn session affinity hoặc consistent hashing cho một dịch vụ có trạng thái dựa trên những rủi ro nào?
Bạn giải thích tác động của locality-aware routing và failover giữa các zone đến độ trễ và khả năng chịu lỗi như thế nào?
Bạn dùng traffic mirroring để kiểm thử phiên bản mới mà tránh gây tác dụng phụ do ghi dữ liệu như thế nào?
Bạn thiết kế chiến lược canary có thể tăng giảm lưu lượng dựa trên tỷ lệ lỗi, latency và chỉ số nghiệp vụ ra sao?
Bạn phân biệt lỗi cấu hình VirtualService, DestinationRule và Kubernetes Service khi request đi sai đích như thế nào?
Bạn dùng fault injection để mô phỏng độ trễ hoặc lỗi dịch vụ và xác minh khả năng phục hồi của ứng dụng như thế nào?
Bạn đánh giá các rủi ro khi áp dụng fault injection trong namespace dùng chung hoặc môi trường production ra sao?
Bạn lựa chọn đường vào mesh qua Istio ingress gateway hoặc Kubernetes Gateway API theo kiến trúc cụm như thế nào?
Bạn phân biệt vai trò của Gateway và VirtualService trong mô hình ingress truyền thống của Istio như thế nào?
Bạn cấu hình truy cập nhiều hostname hoặc nhiều dịch vụ qua cùng một ingress gateway như thế nào?
Bạn xác định điểm kết thúc TLS ở ingress gateway và bảo vệ lưu lượng từ gateway tới backend ra sao?
Bạn kiểm tra các lỗi hostname, listener, certificate và route khi request từ ngoài cụm không tới được backend như thế nào?
Bạn cân nhắc sử dụng TLS passthrough thay vì TLS termination ở gateway trong trường hợp nào?
Bạn thiết kế chính sách giới hạn truy cập quản trị và cách công bố cổng ingress ra Internet như thế nào?
Bạn phân biệt lưu lượng egress tới dịch vụ ngoài cụm với lưu lượng giữa các workload đã tham gia mesh như thế nào?
Bạn dùng ServiceEntry để mô tả một đích ngoài Kubernetes và kiểm soát cách truy cập như thế nào?
Bạn lựa chọn egress gateway khi cần điểm thoát tập trung, kiểm soát chính sách hoặc ghi log theo yêu cầu nào?
Bạn kiểm tra nguyên nhân workload không gọi được một dịch vụ bên ngoài sau khi siết chính sách outbound như thế nào?
Bạn đánh giá rủi ro khi cho phép truy cập tùy ý tới các đích ngoài mesh so với duy trì danh sách đích được phép ra sao?
Bạn xử lý định tuyến và xác minh TLS cho kết nối tới dịch vụ ngoài cụm bằng những bước kiểm tra nào?
Bạn tổ chức kết nối tới dịch vụ legacy không có sidecar hoặc không thuộc mesh mà vẫn xác định rõ ranh giới bảo mật ra sao?
Bạn giải thích cách Istio nhận diện workload qua service account và danh tính gắn với Kubernetes như thế nào?
Bạn mô tả vai trò của chứng chỉ ngắn hạn và danh tính SPIFFE trong thiết lập kết nối bảo mật giữa các workload ra sao?
Bạn giải thích cách mTLS hỗ trợ xác thực hai chiều, mã hóa kết nối và nhận diện dịch vụ trong mesh như thế nào?
Bạn phân biệt PeerAuthentication với DestinationRule khi quy định mTLS phía nhận và phía gọi như thế nào?
Bạn lựa chọn chế độ mTLS STRICT hay PERMISSIVE dựa trên giai đoạn chuyển đổi và mức tương thích ứng dụng ra sao?
Bạn kiểm tra nguyên nhân một kết nối thất bại khi bên gọi sử dụng chế độ TLS khác với kỳ vọng của bên nhận như thế nào?
Bạn xác định những kết nối nào thực sự sử dụng mTLS trong mesh dựa trên telemetry hoặc trạng thái proxy ra sao?
Bạn quản lý vòng đời và sự luân chuyển chứng chỉ workload để tránh gián đoạn giao tiếp giữa các dịch vụ như thế nào?
Bạn đánh giá tác động của trust domain và cấu hình danh tính khi các workload ở nhiều cụm cần giao tiếp với nhau như thế nào?
Bạn phân biệt xác thực service-to-service bằng mTLS với xác thực người dùng cuối bằng JWT như thế nào?
Bạn sử dụng RequestAuthentication để kiểm tra JWT và xác định phạm vi workload áp dụng ra sao?
Bạn thiết kế AuthorizationPolicy cho phép chỉ một service account cụ thể gọi một API nhạy cảm như thế nào?
Bạn phân biệt chính sách ALLOW, DENY và CUSTOM khi diễn đạt quy tắc truy cập trong Istio như thế nào?
Bạn kiểm tra mức ưu tiên và phạm vi tác động của AuthorizationPolicy khi có nhiều policy đồng thời như thế nào?
Vì sao RequestAuthentication kiểm tra JWT không đồng nghĩa với việc bắt buộc mọi request phải mang JWT, và bạn bổ sung chính sách gì?
Bạn thiết kế chính sách zero-trust trong mesh bằng danh tính workload, quyền tối thiểu và kiểm soát ingress/egress ra sao?
Bạn phát hiện trường hợp AuthorizationPolicy chỉ kiểm tra được L4 nhưng yêu cầu nghiệp vụ lại cần điều kiện L7 như thế nào?
Bạn xác định vì sao một request được định tuyến đúng nhưng nhận phản hồi 403 sau khi áp dụng AuthorizationPolicy như thế nào?
Bạn triển khai thay đổi chính sách bảo mật theo từng namespace mà vẫn có phương án xác minh và rollback như thế nào?
Bạn cân nhắc những giới hạn bảo mật khi kết nối tới dịch vụ không tham gia mesh hoặc qua gateway trung gian ra sao?
Bạn giải thích Istio thu thập các tín hiệu metrics, access log và distributed tracing từ data plane như thế nào?
Bạn chọn những chỉ số về request rate, tỷ lệ lỗi và thời gian phản hồi để theo dõi sức khỏe giao tiếp giữa dịch vụ ra sao?
Bạn phân biệt thời gian chờ tại proxy với thời gian xử lý ứng dụng khi phân tích độ trễ một request như thế nào?
Bạn cấu hình hoặc điều chỉnh sampling tracing để cân bằng khả năng điều tra với chi phí lưu trữ như thế nào?
Bạn tổ chức lan truyền trace context qua HTTP hoặc gRPC để nhìn được đường đi của một request xuyên nhiều service ra sao?
Bạn xử lý trường hợp biểu đồ truy vết thiếu một đoạn service dù request vẫn thành công theo quy trình nào?
Bạn sử dụng Prometheus, Grafana hoặc Kiali để quan sát topology và tìm giao tiếp bất thường trong mesh như thế nào?
Bạn phân tích log Envoy, mã trạng thái response và thông tin upstream để tách lỗi proxy khỏi lỗi ứng dụng ra sao?
Bạn kiểm soát dữ liệu nhạy cảm hoặc nhãn có cardinality cao khi thu thập telemetry từ hàng trăm dịch vụ như thế nào?
Bạn đặt cảnh báo cho tăng tỷ lệ 5xx, p99 latency, kết nối bị từ chối hoặc lỗi mTLS dựa trên những ngưỡng nào?
Bạn lựa chọn các công cụ istioctl analyze và kubectl để phát hiện xung đột hoặc thiếu tham chiếu trong cấu hình như thế nào?
Bạn sử dụng istioctl proxy-status để phát hiện proxy chưa đồng bộ với control plane và kiểm tra nguyên nhân ra sao?
Bạn đọc cấu hình listener, route, cluster và endpoint của Envoy proxy bằng istioctl proxy-config như thế nào?
Khi lưu lượng không đi theo cấu hình mong đợi, bạn xác định route thực tế và endpoint đích từ cấu hình Envoy như thế nào?
Bạn phân biệt lỗi do endpoint không sẵn sàng, DNS, network policy, Envoy và ứng dụng từ log và metric ra sao?
Bạn xử lý tình huống Pod Ready nhưng không thể gọi service khác sau khi bật mesh theo trình tự kiểm tra nào?
Bạn kiểm tra tác động của Kubernetes NetworkPolicy và CNI khi luồng lưu lượng được chuyển qua Istio như thế nào?
Bạn chẩn đoán hiện tượng service trả 503 sau khi áp dụng mTLS hoặc DestinationRule mới bằng những dấu hiệu nào?
Bạn điều tra trường hợp proxy nhận cấu hình quá chậm hoặc tài nguyên istiod tăng mạnh khi số service lớn như thế nào?
Bạn lựa chọn phạm vi xuất cấu hình và khả năng hiển thị dịch vụ để giảm cấu hình không cần thiết trên proxy như thế nào?
Bạn xây dựng kế hoạch nâng cấp Istio bằng revision và chuyển workload từng đợt để giảm rủi ro như thế nào?
Bạn kiểm chứng khả năng tương thích của các phiên bản control plane, sidecar, ambient và CRD trước khi nâng cấp ra sao?
Bạn thiết kế cơ chế rollback khi bản Istio mới khiến lưu lượng hoặc policy bị ảnh hưởng trong production như thế nào?
Bạn đánh giá việc mở rộng và phân bố ingress gateway, ztunnel và waypoint theo lưu lượng và tài nguyên thực tế như thế nào?
Bạn chuẩn bị kịch bản kiểm thử failover cho service ở nhiều zone hoặc nhiều cluster trong mesh ra sao?
Bạn phân biệt mô hình giao tiếp đa cụm cùng mạng và khác mạng khi lựa chọn cổng kết nối, discovery và trust như thế nào?
Bạn thiết kế kiểm thử tải so sánh trước và sau khi bật sidecar hoặc ambient để đo latency, throughput và chi phí tài nguyên như thế nào?
Bạn xác lập tiêu chí hoàn tất triển khai Istio dựa trên kiểm thử định tuyến, bảo mật, telemetry, khả năng phục hồi và vận hành như thế nào?

Linkerd giải quyết những vấn đề gì trong giao tiếp giữa các microservice chạy trên Kubernetes?
Bạn sẽ phân biệt trách nhiệm của service mesh, Kubernetes Service, Ingress và API gateway trong một hệ thống như thế nào?
Bạn sẽ xác định điều kiện nào khiến một ứng dụng cần service mesh thay vì chỉ sử dụng thư viện mạng ở tầng ứng dụng?
Bạn sẽ giải thích khái niệm data plane và control plane của Linkerd bằng đường đi của một request như thế nào?
Bạn sẽ mô tả vai trò của Linkerd proxy đối với lưu lượng vào và ra của một Pod ra sao?
Bạn sẽ phân tích những công việc nào do control plane thực hiện và những công việc nào do proxy xử lý trực tiếp?
Bạn sẽ giải thích vì sao sidecar proxy có thể cải thiện bảo mật và telemetry mà không yêu cầu sửa toàn bộ mã ứng dụng?
Bạn sẽ đánh giá chi phí tài nguyên và độ phức tạp vận hành khi bổ sung sidecar proxy cho nhiều Pod như thế nào?
Bạn sẽ so sánh cách triển khai mesh theo từng namespace với việc áp dụng cho toàn bộ cluster ra sao?
Bạn sẽ xây dựng tiêu chí xác định dịch vụ nào nên được đưa vào mesh trước trong một quá trình triển khai từng bước như thế nào?
Bạn sẽ phân biệt luồng east-west giữa các dịch vụ với luồng north-south qua biên cluster ra sao?
Bạn sẽ mô tả một request đi từ ứng dụng nguồn qua proxy nguồn, mạng Kubernetes và proxy đích như thế nào?
Bạn sẽ giải thích cách Linkerd tương tác với Kubernetes Service và danh sách endpoint có thể thay đổi khi scale Pod ra sao?
Bạn sẽ phân biệt identity của workload với địa chỉ IP hoặc hostname của Pod trong mesh như thế nào?
Bạn sẽ đánh giá sự phụ thuộc của Linkerd vào Kubernetes API và DNS khi các thành phần hạ tầng gặp lỗi ra sao?
Bạn sẽ mô tả các thành phần chính trong control plane của Linkerd và mối quan hệ giữa chúng như thế nào?
Bạn sẽ giải thích vai trò của dịch vụ destination trong việc cung cấp thông tin endpoint cho proxy ra sao?
Bạn sẽ mô tả cách proxy nhận thông tin thay đổi endpoint khi một Deployment tăng hoặc giảm số Pod như thế nào?
Bạn sẽ phân tích vai trò của thành phần identity khi proxy cần thiết lập kết nối được xác thực trong mesh ra sao?
Bạn sẽ giải thích chức năng của proxy injector trong quá trình tạo Pod mới như thế nào?
Bạn sẽ kiểm tra mối liên hệ giữa admission webhook, cấu hình namespace và kết quả inject sidecar như thế nào?
Bạn sẽ phân biệt việc inject proxy tự động với việc chỉnh sửa manifest workload để inject có kiểm soát ra sao?
Bạn sẽ mô tả quá trình chuyển lưu lượng tới proxy sidecar trong Pod mà ứng dụng vẫn sử dụng cổng dịch vụ bình thường như thế nào?
Bạn sẽ giải thích vai trò của init container hoặc cơ chế CNI trong việc thiết lập chuyển hướng lưu lượng cho proxy ra sao?
Bạn sẽ so sánh lợi ích và rủi ro khi dùng Linkerd CNI so với mô hình cấu hình chuyển hướng lưu lượng qua init container như thế nào?
Bạn sẽ kiểm tra những đặc điểm của Pod và Kubernetes NetworkPolicy có thể ảnh hưởng đến khả năng proxy hoạt động ra sao?
Bạn sẽ lập kế hoạch cài đặt Linkerd lên cluster mới với các bước kiểm tra điều kiện tiên quyết nào?
Bạn sẽ sử dụng công cụ kiểm tra trạng thái Linkerd trước và sau khi cài đặt để xác nhận các thành phần sẵn sàng như thế nào?
Bạn sẽ đánh giá phiên bản Kubernetes, quyền RBAC và tài nguyên cluster trước khi cài Linkerd theo những tiêu chí nào?
Bạn sẽ tổ chức cấu hình và quản lý manifest cài đặt Linkerd trong quy trình GitOps như thế nào?
Bạn sẽ phân biệt các thành phần cốt lõi của Linkerd với những extension phục vụ telemetry hoặc multi-cluster ra sao?
Bạn sẽ giải thích vì sao một hệ thống đang chạy ổn định vẫn cần kiểm chứng khả năng tương thích trước khi cập nhật Linkerd?
Bạn sẽ lựa chọn thứ tự triển khai control plane, extension và proxy khi nâng cấp theo những phụ thuộc nào?
Bạn sẽ kiểm tra sự khác biệt giữa phiên bản CLI, control plane và proxy của Linkerd như thế nào?
Bạn sẽ xác định Pod nào đã được inject proxy và Pod nào chưa tham gia mesh bằng những dấu hiệu nào?
Bạn sẽ mô tả cách đưa một Deployment hiện có vào mesh mà không làm gián đoạn người dùng ra sao?
Bạn sẽ lựa chọn chiến lược rollout để thay thế Pod cũ bằng Pod có proxy trong khi vẫn duy trì mức khả dụng như thế nào?
Bạn sẽ thiết kế phép thử xác minh request giữa hai workload đã được đưa vào mesh như thế nào?
Bạn sẽ phân biệt trạng thái Pod Ready với trạng thái proxy có thể xử lý lưu lượng và kết nối tới control plane ra sao?
Bạn sẽ đánh giá cách startup, readiness và shutdown của proxy ảnh hưởng đến vòng đời Pod như thế nào?
Bạn sẽ mô tả các tình huống cần bỏ qua một cổng hoặc một loại lưu lượng khỏi cơ chế chuyển hướng proxy ra sao?
Bạn sẽ phân biệt cổng quản trị, cổng health check và cổng nghiệp vụ khi lựa chọn cấu hình đưa lưu lượng vào mesh như thế nào?
Bạn sẽ phân tích tác động của việc không inject proxy cho một bên của kết nối khi chỉ một phần hệ thống đã tham gia mesh ra sao?
Bạn sẽ mô tả cách ứng dụng nằm ngoài mesh truy cập một dịch vụ đã được mesh bảo vệ như thế nào?
Bạn sẽ xác định những lưu lượng nào không phù hợp để proxy tự nhận diện giao thức và cần cấu hình rõ ràng ra sao?
Bạn sẽ giải thích cơ chế phát hiện giao thức của Linkerd ảnh hưởng đến telemetry và cách xử lý request như thế nào?
Bạn sẽ so sánh hành vi proxy đối với HTTP/1.1, HTTP/2, gRPC và TCP thuần theo khả năng quan sát như thế nào?
Bạn sẽ phân tích các vấn đề có thể xảy ra khi một dịch vụ dùng giao thức tùy chỉnh trên cổng mà proxy đang cố phát hiện giao thức ra sao?
Bạn sẽ chẩn đoán tình huống kết nối TCP thành công nhưng metric HTTP không xuất hiện bằng cách nào?
Bạn sẽ phân biệt điều kiện để Linkerd cung cấp thống kê ở tầng kết nối với thống kê ở tầng request ra sao?
Bạn sẽ giải thích mTLS trong Linkerd bảo vệ kết nối giữa hai workload được đưa vào mesh như thế nào?
Bạn sẽ phân biệt mã hóa đường truyền với xác thực danh tính và kiểm soát quyền truy cập trong Linkerd ra sao?
Bạn sẽ mô tả vai trò của trust anchor và chứng chỉ trung gian trong quá trình xác thực mTLS như thế nào?
Bạn sẽ giải thích cách workload identity gắn với ServiceAccount và namespace Kubernetes ra sao?
Bạn sẽ kiểm chứng danh tính được ghi nhận của proxy có đúng workload mà nó đại diện hay không như thế nào?
Bạn sẽ mô tả chu trình cấp và sử dụng chứng chỉ ngắn hạn cho proxy mà không đưa private key vào mã ứng dụng ra sao?
Bạn sẽ đánh giá sự phụ thuộc của cơ chế tự động cấp chứng chỉ vào thành phần identity của control plane như thế nào?
Bạn sẽ xác định dấu hiệu nào cho thấy kết nối giữa hai workload đang dùng mTLS thay vì kết nối không xác thực ra sao?
Bạn sẽ giải thích vì sao chỉ bật mTLS không đồng nghĩa với mọi workload đều được phép gọi mọi workload khác?
Bạn sẽ thiết kế chính sách chỉ cho phép một số ServiceAccount gọi tới dịch vụ thanh toán như thế nào?
Bạn sẽ phân biệt xác thực danh tính mesh với phân quyền ở tầng ứng dụng khi yêu cầu bảo vệ dữ liệu nhạy cảm ra sao?
Bạn sẽ giải thích vai trò của tài nguyên Server khi xác định cổng hoặc lưu lượng đích cần được áp chính sách như thế nào?
Bạn sẽ mô tả cách các tài nguyên chính sách xác thực và ủy quyền phối hợp để cho phép hoặc từ chối kết nối ra sao?
Bạn sẽ cân nhắc sử dụng chính sách dựa trên MeshTLSAuthentication hoặc NetworkAuthentication theo bối cảnh nào?
Bạn sẽ thiết kế chính sách phân biệt caller trong mesh và caller ngoài mesh theo nguyên tắc ít quyền nhất như thế nào?
Bạn sẽ xác định ảnh hưởng của chính sách mặc định đối với dịch vụ chưa khai báo quy tắc truy cập rõ ràng ra sao?
Bạn sẽ tổ chức triển khai chính sách deny-by-default từng bước để không chặn nhầm lưu lượng hợp lệ như thế nào?
Bạn sẽ kiểm thử hành vi policy đối với nguồn gọi hợp lệ, nguồn gọi không hợp lệ và workload chưa được mesh hóa ra sao?
Bạn sẽ phân tích khi nào cần chính sách ở mức route HTTP thay vì chỉ mức cổng hoặc service như thế nào?
Bạn sẽ đánh giá rủi ro của việc gán ServiceAccount dùng chung cho nhiều Deployment khi cấp quyền truy cập ra sao?
Bạn sẽ kiểm tra nguyên nhân request bị từ chối do chính sách Linkerd so với lỗi 403 do ứng dụng trả về như thế nào?
Bạn sẽ thiết kế cách giám sát thay đổi policy, quyền sửa policy và dấu vết kiểm toán trong cluster ra sao?
Bạn sẽ mô tả quy trình xoay vòng chứng chỉ issuer mà không làm gián đoạn giao tiếp giữa các proxy như thế nào?
Bạn sẽ phân biệt thay thế issuer certificate với thay đổi trust anchor và những rủi ro liên quan như thế nào?
Bạn sẽ tổ chức cảnh báo về hạn dùng chứng chỉ và khả năng cấp mới trước khi có lỗi mTLS diện rộng ra sao?
Bạn sẽ chẩn đoán một lỗi mTLS xuất hiện sau khi cấu hình trust giữa các cluster thay đổi như thế nào?
Bạn sẽ đánh giá cách bảo vệ private key và quyền truy cập tài nguyên Kubernetes liên quan tới identity như thế nào?
Bạn sẽ phân tích nguy cơ khi một ServiceAccount được cấp quyền quá rộng hoặc token của workload bị lộ ra sao?
Bạn sẽ lựa chọn và diễn giải các chỉ số request volume, success rate và latency giữa các dịch vụ như thế nào?
Bạn sẽ giải thích sự khác nhau giữa chỉ số quan sát từ phía client proxy và từ phía server proxy ra sao?
Bạn sẽ sử dụng telemetry của Linkerd để xác định service nào có tỷ lệ lỗi tăng sau một rollout như thế nào?
Bạn sẽ phân biệt lỗi ở tầng TCP, lỗi phản hồi HTTP và lỗi do policy từ chối trong dữ liệu quan sát ra sao?
Bạn sẽ phân tích giới hạn của success rate khi một dịch vụ trả mã lỗi ứng dụng nhưng hệ thống vẫn hoạt động đúng theo nghiệp vụ như thế nào?
Bạn sẽ dùng histogram hoặc phân vị độ trễ để nhận biết tình huống chỉ một nhóm request chậm bất thường ra sao?
Bạn sẽ giải thích ý nghĩa của inbound và outbound metrics khi theo dõi một request đi qua nhiều service như thế nào?
Bạn sẽ mô tả cách Linkerd Viz và hệ thống thu thập metric như Prometheus hỗ trợ phân tích lưu lượng ra sao?
Bạn sẽ lựa chọn những dashboard và góc nhìn nào để quan sát mesh, control plane và ứng dụng khi tải tăng?
Bạn sẽ dùng công cụ quan sát lưu lượng theo thời gian thực của Linkerd để điều tra một endpoint bị lỗi như thế nào?
Bạn sẽ đánh giá rủi ro tiết lộ thông tin nhạy cảm khi bật quan sát request hoặc log chi tiết trong môi trường sản xuất ra sao?
Bạn sẽ phân biệt khả năng quan sát do sidecar cung cấp với distributed tracing có gắn trace ID trong ứng dụng như thế nào?
Bạn sẽ thiết kế cách kết hợp metric proxy, log ứng dụng và trace để khoanh vùng dịch vụ gây chậm như thế nào?
Bạn sẽ xác định nguyên nhân telemetry thiếu dữ liệu khi proxy vẫn hoạt động và request vẫn thành công ra sao?
Bạn sẽ giải thích sự khác biệt giữa cơ chế chọn endpoint trong mesh với Kubernetes Service load balancing như thế nào?
Bạn sẽ phân tích cách Linkerd phản ứng khi một endpoint đột ngột mất khả năng phục vụ trong khi các endpoint khác vẫn khỏe ra sao?
Bạn sẽ đánh giá vai trò của thông tin endpoint và đặc điểm kết nối trong việc phân phối tải qua proxy như thế nào?
Bạn sẽ xác định giới hạn của cân bằng tải phía proxy khi ứng dụng duy trì kết nối dài hoặc phiên giao tiếp đặc biệt ra sao?
Bạn sẽ thiết kế timeout của request sao cho giảm thời gian chờ nhưng không hủy các thao tác hợp lệ kéo dài như thế nào?
Bạn sẽ quyết định có nên retry một request khi gặp lỗi mạng dựa trên tính idempotent và các tác dụng phụ nào?
Bạn sẽ phân biệt retry do ứng dụng thực hiện với retry do cơ chế mesh hỗ trợ để tránh nhân số lần gọi ra sao?
Bạn sẽ đánh giá những khả năng cấu hình timeout và retry đang hỗ trợ trên phiên bản Linkerd sử dụng trước khi áp dụng như thế nào?
Bạn sẽ kiểm soát retry storm khi nhiều client cùng thử lại request vào một downstream đang quá tải ra sao?
Bạn sẽ mô tả cách giảm lưu lượng tới instance có hành vi lỗi mà không khiến toàn hệ thống mất khả dụng như thế nào?
Bạn sẽ kiểm chứng các thay đổi về định tuyến hoặc chính sách lưu lượng bằng phép thử tải và chỉ số nào?
Bạn sẽ so sánh rollout theo từng đợt với chiến lược canary khi có hỗ trợ chia lưu lượng theo phiên bản như thế nào?
Bạn sẽ xác định ranh giới giữa Linkerd, công cụ progressive delivery và Kubernetes Deployment trong việc điều phối canary ra sao?
Bạn sẽ phân tích ảnh hưởng của kết nối gRPC dài tới việc phân phối tải và chuyển Pod khi rolling update như thế nào?
Bạn sẽ thiết kế graceful shutdown cho dịch vụ nằm trong mesh để tránh mất request đang thực hiện ra sao?
Bạn sẽ phân biệt tín hiệu lỗi từ proxy với lỗi nghiệp vụ trong ứng dụng khi quan sát retry và latency như thế nào?
Bạn sẽ mô tả những vấn đề nảy sinh khi microservice cần gọi dịch vụ ở một Kubernetes cluster khác như thế nào?
Bạn sẽ giải thích khái niệm service mirroring và gateway trong giải pháp multi-cluster của Linkerd ra sao?
Bạn sẽ mô tả luồng request từ một workload ở cluster A đến dịch vụ ở cluster B qua các thành phần liên quan như thế nào?
Bạn sẽ kiểm tra các điều kiện mạng, DNS và cổng firewall cần thiết trước khi thiết lập liên kết giữa các cluster như thế nào?
Bạn sẽ thiết kế chính sách tin cậy danh tính giữa hai cluster để không chấp nhận workload giả mạo ra sao?
Bạn sẽ phân biệt trust domain chung với cơ chế xác thực và phân quyền ở từng cluster trong một kết nối multi-cluster như thế nào?
Bạn sẽ đánh giá rủi ro khi hai cluster dùng cấu hình identity hoặc trust anchor không tương thích như thế nào?
Bạn sẽ lập kế hoạch kết nối multi-cluster trong môi trường nhiều namespace và dịch vụ trùng tên ra sao?
Bạn sẽ xác định cách service được công bố và xuất hiện ở cluster đích trong quá trình service mirroring như thế nào?
Bạn sẽ phân tích các tình huống gateway không khả dụng hoặc đường truyền liên vùng bị phân hoạch ảnh hưởng đến request ra sao?
Bạn sẽ thiết kế hành vi fallback khi dịch vụ từ xa không truy cập được nhưng vẫn có instance trong cluster nội bộ như thế nào?
Bạn sẽ đánh giá độ trễ xuyên cluster, chi phí mạng và chính sách định tuyến trước khi mở rộng giao tiếp đa cụm ra sao?
Bạn sẽ kiểm chứng multi-cluster mTLS và identity bằng metric, log hoặc công cụ kiểm tra kết nối như thế nào?
Bạn sẽ lập kế hoạch triển khai Linkerd vào cluster sản xuất đang chạy ứng dụng có SLA nghiêm ngặt ra sao?
Bạn sẽ sử dụng các bước kiểm tra trước cài đặt để phát hiện quyền RBAC, webhook hoặc chứng chỉ chưa đáp ứng như thế nào?
Bạn sẽ xác định nguyên nhân một Pod không được inject proxy sau khi bật cấu hình tự động như thế nào?
Bạn sẽ chẩn đoán Pod có sidecar nhưng không Ready do proxy chưa khởi tạo hoặc chưa liên hệ được control plane ra sao?
Bạn sẽ phân tích nguyên nhân request bị timeout sau khi mesh hóa một service vốn hoạt động bình thường như thế nào?
Bạn sẽ kiểm tra việc chuyển hướng traffic, các port bị bỏ qua và protocol detection khi một kết nối không đi qua proxy ra sao?
Bạn sẽ dùng log của proxy và các thành phần control plane để phân biệt lỗi cấu hình với lỗi mạng như thế nào?
Bạn sẽ nhận biết và xác minh lỗi DNS hoặc endpoint discovery của Kubernetes đang biểu hiện qua proxy Linkerd bằng cách nào?
Bạn sẽ kiểm tra vì sao chỉ các kết nối tới một port cụ thể bị lỗi sau khi áp chính sách truy cập như thế nào?
Bạn sẽ chẩn đoán tình huống lưu lượng thành công nhưng không có mTLS vì một phía chưa được đưa vào mesh ra sao?
Bạn sẽ phân tích hiện tượng tỷ lệ lỗi tăng sau khi cấp mới chứng chỉ issuer và cách cô lập nguyên nhân như thế nào?
Bạn sẽ đánh giá tác động của control plane tạm thời không khả dụng đối với những kết nối đang tồn tại và kết nối mới ra sao?
Bạn sẽ mô tả quy trình kiểm tra sức khỏe control plane và các extension mà không chỉ dựa vào trạng thái Running của Pod như thế nào?
Bạn sẽ xác định mức CPU, bộ nhớ và độ trễ bổ sung do proxy bằng những phép đo trước và sau khi inject như thế nào?
Bạn sẽ thiết kế requests và limits phù hợp cho proxy khi workload có lưu lượng cao hoặc nhiều kết nối đồng thời ra sao?
Bạn sẽ kiểm tra dấu hiệu proxy bị giới hạn CPU hoặc thiếu bộ nhớ và ảnh hưởng tới thời gian phản hồi dịch vụ như thế nào?
Bạn sẽ chuẩn bị phương án rollback khi một đợt nâng cấp Linkerd làm thay đổi hành vi mạng hoặc chính sách truy cập ra sao?
Bạn sẽ lập kế hoạch cập nhật CRD, control plane và proxy sao cho giảm rủi ro không tương thích giữa các phiên bản như thế nào?
Bạn sẽ kiểm chứng sau nâng cấp rằng mTLS, telemetry, chính sách truy cập và multi-cluster vẫn hoạt động đúng như thế nào?
Bạn sẽ tổ chức sao lưu hoặc quản lý bằng Git các cấu hình policy, chứng chỉ và manifest Linkerd cần thiết để phục hồi như thế nào?
Bạn sẽ đặt các chỉ số cảnh báo nào cho tỷ lệ lỗi proxy, độ trễ, chứng chỉ sắp hết hạn và kết nối control plane ra sao?
Bạn sẽ xây dựng diễn tập xử lý sự cố mất một node, lỗi webhook hoặc ngừng cấp chứng chỉ để đo khả năng phục hồi của mesh như thế nào?
Bạn sẽ xác định những tiêu chí nghiệm thu nào về bảo mật, quan sát, độ tin cậy và khả năng vận hành trước khi mở rộng Linkerd toàn cluster?

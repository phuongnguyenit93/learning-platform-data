Một nền tảng thương mại điện tử có hơn 20 microservice trên Kubernetes và từng tự triển khai TLS, retry cùng log kết nối ở mỗi ngôn ngữ; khi bổ sung Linkerd, nhóm chưa thống nhất đâu là trách nhiệm của proxy sidecar và đâu là kiểm tra nghiệp vụ phải giữ trong ứng dụng.
Nhóm thử nghiệm Linkerd trên một namespace mới và thấy dashboard không ghi nhận request tới dịch vụ thanh toán; workload đã hoạt động trước khi namespace được bật injection và chưa có đợt tạo lại pod.
Một Deployment được đặt annotation bật Linkerd trên metadata của đối tượng nhưng không nằm trong pod template; các pod mới vẫn thiếu sidecar dù nhóm đã áp dụng cấu hình và rollout.
Namespace đã bật tự động inject nhưng một pod nhạy cảm có cấu hình loại trừ riêng; truy cập giữa pod đó và dịch vụ trong mesh không có các chỉ số mTLS như các workload khác.
Nhóm cài Linkerd trên cụm Kubernetes có nhiều admission webhook; khi proxy-injector webhook gặp lỗi TLS, một số pod ứng dụng không tạo được trong đợt scale-out dù các pod cũ vẫn phục vụ bình thường.
Một cụm có quy định không cho container khởi tạo chỉnh sửa quy tắc mạng bằng đặc quyền; pod được inject Linkerd nhưng container khởi tạo proxy không hoàn tất và pod liên tục ở trạng thái khởi tạo.
Đội nền tảng chuyển từ chế độ thiết lập quy tắc chuyển hướng lưu lượng trong pod sang Linkerd CNI; các node mới chưa có thành phần CNI phù hợp khiến pod ứng dụng không nhận được lưu lượng như ở các node cũ.
Một ứng dụng sử dụng hostNetwork chạy bình thường trước khi được đưa vào mesh; sau khi bật injection, nhóm nhận thấy đường truyền mạng của pod này không đi qua sidecar như các pod thông thường.
Một Job chạy rất ngắn chỉ gọi API rồi thoát, nhưng sau khi được inject Linkerd thì tiến trình chính đã hoàn tất mà vòng đời pod vẫn không kết thúc như hệ thống batch mong đợi.
Một pod chứa ứng dụng và một container hỗ trợ cùng dùng localhost; khi thêm sidecar Linkerd, nhóm thấy một số kết nối nội bộ cùng pod không xuất hiện trong thống kê giữa các service.
Application container bắt đầu gửi request ngay khi khởi động, trong khi proxy Linkerd còn chờ kết nối với control plane; vài request đầu tiên thất bại dù pod đạt trạng thái hoạt động sau đó.
Một dịch vụ được cấu hình probe readiness ở cổng ứng dụng nhưng sau khi inject Linkerd, pod sẵn sàng theo thời điểm khác với dự kiến; nhóm chưa phân biệt readiness của ứng dụng và của sidecar.
Đội vận hành tăng replica để đón giờ cao điểm; mỗi pod được thêm linkerd-proxy cùng giới hạn CPU và bộ nhớ, làm tổng yêu cầu tài nguyên vượt sức chứa node và hàng loạt pod chờ scheduling.
Một ứng dụng vốn tiêu thụ ít CPU nhưng tạo rất nhiều kết nối ngắn; sau khi bật Linkerd, CPU của sidecar trên một số pod chạm giới hạn, p99 tăng dù CPU của application container còn thấp.
Proxy sidecar liên tục bị hệ thống kết thúc do thiếu bộ nhớ khi nhiều kết nối streaming tồn tại đồng thời; ứng dụng vẫn có log nghiệp vụ bình thường nhưng client thấy kết nối bị cắt.
Một nhóm bật Linkerd cho toàn bộ namespace trong một lần phát hành; dịch vụ dữ liệu legacy không thể kết nối ổn định trong khi các API HTTP bình thường, khiến đội triển khai cần khoanh vùng theo giao thức và cổng.
Một client Redis trong pod mới được inject mất khoảng thời gian đáng kể ở lần thiết lập kết nối đầu; Redis gửi thông điệp khác với HTTP và proxy phải xác định cách xử lý lưu lượng TCP trên cổng đó.
Một hệ thống TCP do server gửi dữ liệu trước chậm kết nối sau khi bật Linkerd; proxy cố phân biệt giao thức ở đầu kết nối trước khi chuyển tiếp khiến client thấy delay không có ở lần gọi trực tiếp.
Dịch vụ nội bộ giao tiếp bằng giao thức nhị phân riêng qua một cổng cố định; sau khi bổ sung Linkerd, proxy không nhận diện được giao thức như HTTP và metrics theo route không xuất hiện.
Nhóm cấu hình một cổng của dịch vụ cơ sở dữ liệu theo chế độ opaque trong mesh; latency khởi tạo kết nối cải thiện nhưng dashboard không còn thấy thông tin request HTTP trên cổng đó như nhóm từng kỳ vọng.
Một microservice dùng HTTP/2 không mã hóa trong mạng nội bộ; sau khi đi qua sidecar, nhóm muốn đối chiếu kết quả nhận diện HTTP/2 với các kết nối TCP thường và số liệu thành công ở tầng ứng dụng.
Giao tiếp gRPC giữa hai pod được inject có một phần request dài kết thúc với lỗi ứng dụng, nhưng thống kê HTTP response không phản ánh đầy đủ mã trạng thái nghiệp vụ gRPC mà nhóm mong đợi.
Một dịch vụ sử dụng gRPC streaming liên tục hàng chục phút; sau khi nhóm áp dụng timeout cho lời gọi thông thường, luồng dữ liệu dài bị kết thúc không giống các request ngắn.
Ứng dụng WebSocket kết nối qua ingress rồi đi tiếp vào các pod được inject; kết nối được nâng cấp thành công nhưng các phiên tồn tại lâu có độ trễ và vòng đời khác với request HTTP thông thường.
Một nhóm cấu hình bỏ qua sidecar ở một cổng outbound vì tưởng đó là kết nối nội bộ không quan trọng; kết nối tới backend qua cổng đó không còn xuất hiện trong thống kê và chính sách mTLS của mesh.
Pod ứng dụng gọi một dịch vụ ngoài Internet nhưng team kỳ vọng mọi lưu lượng egress được xác thực bằng Linkerd identity; kết nối đến endpoint ngoài mesh không có đặc tính xác thực workload như luồng nội bộ.
Nhóm bật Linkerd cho một backend nhưng client vẫn ở ngoài mesh; các request của client hoạt động nhưng chỉ số kết nối có xác thực mTLS thấp hơn nhiều so với tổng số request backend nhận được.
Gateway công khai giải mã HTTPS của người dùng rồi chuyển HTTP tới Kubernetes Service trong mesh; nhóm bảo mật thấy luồng từ ingress chưa được inject tới backend và muốn xác định phạm vi TLS trên từng chặng.
Hai deployment cùng namespace dùng service account mặc định; sau khi thiết lập chính sách chỉ cho workload kế toán gọi dịch vụ thanh toán, nhiều pod ngoài nhóm vẫn có cùng danh tính mà policy đang tin cậy.
Ứng dụng nhận cấu hình serviceAccountName mới để tăng độ chi tiết quyền truy cập; sau rollout, các request từng được Linkerd cho phép bắt đầu bị từ chối vì workload identity không còn khớp chính sách cũ.
Một backend yêu cầu danh tính mTLS của service account dịch vụ giỏ hàng; một CronJob gọi cùng endpoint bằng service account khác bị proxy từ chối dù bearer token ứng dụng vẫn hợp lệ.
Đội bảo mật triển khai quy tắc chỉ cho namespace bán hàng truy cập dịch vụ kho; một ứng dụng xử lý báo cáo trong namespace khác bị chặn dù có chức năng đọc kho được nghiệp vụ phê duyệt.
Chính sách Linkerd được xây dựng dựa trên tên namespace nhưng hai môi trường có namespace giống nhau và service account khác nhau; nhóm gặp khó khăn khi phân biệt workload được ủy quyền trong bản thiết kế chính sách.
Đội phát triển thêm tài nguyên Server cho cổng HTTP của ứng dụng nhưng khai báo nhầm số port; request tiếp tục đi theo chính sách khác dự kiến và log backend không giải thích được kết quả.
Một nhóm triển khai AuthorizationPolicy cho API thanh toán nhưng đối tượng tham chiếu tới ServiceAccount không đúng namespace; sidecar từ chối yêu cầu dù pod gọi đã bật mTLS.
Chính sách mới chỉ cho phép GET trên đường dẫn tra cứu đơn hàng nhưng không cho phép POST tạo đơn; sau đợt áp dụng, người dùng xem được lịch sử mua hàng song không thể tạo đơn mới.
Ứng dụng Spring Boot có actuator health endpoint cùng cổng với API nghiệp vụ; sau khi nhóm siết policy bằng tài nguyên Server, kubelet probe không còn được chấp nhận và pod bị đánh dấu không sẵn sàng.
Prometheus ở namespace giám sát cần scrape metrics qua cổng đã áp policy; sau khi thu hẹp quyền truy cập, dashboard mất số liệu sidecar dù request của người dùng vẫn hoạt động.
Một dịch vụ có HTTPRoute để kiểm soát riêng nhóm endpoint quản trị; đường dẫn có và không có dấu gạch chéo cuối đi theo quy tắc khác nhau, làm kết quả kiểm tra quyền không nhất quán.
Ứng dụng gRPC dùng một kết nối HTTP/2 cho nhiều phương thức; đội phát triển chỉ muốn cấp quyền gọi một nhóm phương thức nhưng policy hiện áp theo cổng nên quyền rộng hơn nhu cầu.
Control plane Linkerd vẫn khỏe nhưng một pod phía nhận báo các kết nối bị policy từ chối; ứng dụng phía gửi chỉ thấy timeout hoặc lỗi kết nối nên nhóm trực ca tìm lỗi trong service code thay vì tại proxy.
Một dịch vụ chuyển sang chính sách chặn truy cập mặc định theo danh tính, trong khi tiến trình migration dữ liệu ở namespace khác không được khai báo; triển khai schema mới thất bại trước khi ứng dụng được phát hành.
Đội phát triển bật mTLS cho phần lớn lưu lượng nội bộ nhưng vẫn có các kết nối không xác thực; dashboard tổng hợp cho thấy tỉ lệ thấp và nhóm chưa phân biệt traffic từ ngoài mesh với traffic bỏ qua proxy.
Control plane identity của Linkerd không thể cấp chứng chỉ mới sau thay đổi cấu hình issuer; các pod đã chạy tiếp tục phục vụ một thời gian còn pod khởi động mới gặp lỗi xác thực hoặc identity.
Nhà vận hành xoay chứng chỉ identity issuer nhưng quên đồng bộ nội dung cần thiết giữa các replica control plane; một phần workload nhận lỗi mTLS ngắt quãng khi được cấp danh tính mới.
Một cụm chuẩn bị hết hạn chứng chỉ trust anchor của mesh; ứng dụng vẫn phản hồi nhưng đội vận hành chưa có kế hoạch chuyển đổi gốc tin cậy và kiểm thử khả năng các proxy cũ tin chứng chỉ mới.
Nhóm nâng cấp thành phần cấp chứng chỉ nhưng đồng hồ của một số node Kubernetes lệch đáng kể; các pod trên những node đó thường báo chứng chỉ chưa có hiệu lực.
Đội bảo mật phát hiện khóa riêng cấp chứng chỉ issuer từng được chia sẻ rộng trong quá trình cài đặt Linkerd; các chứng chỉ workload vẫn đang được chấp nhận và phạm vi ảnh hưởng chưa được xác định.
Một workload mới dùng danh tính Linkerd đúng nhưng thời gian kết nối mTLS tăng rõ sau khi số proxy kết nối đồng thời tăng; nhóm thiếu metrics tách thời gian kết nối tới identity service và request nghiệp vụ.
Sau khi đổi Kubernetes Service selector của backend, một số endpoint không được liệt kê đúng; pod gọi qua mesh báo không có backend hoặc lỗi kết nối dù các pod phía nhận vẫn chạy bình thường.
Một Service có endpoint chưa vượt readiness probe nhưng nhóm quan sát request thất bại trong lúc rollout; Linkerd và Kubernetes cùng cập nhật danh sách đích trong khoảng chuyển phiên bản.
Một ứng dụng gọi thẳng IP pod thay vì tên Kubernetes Service; sau khi chuyển sang Linkerd, telemetry và lựa chọn endpoint khác đáng kể so với lời gọi qua Service name.
Team cấu hình headless Service cho hệ thống lưu trữ phân tán; kết nối giữa các pod có hành vi khác lời gọi tới ClusterIP, khiến nhóm cần phân biệt khám phá endpoint và điều phối lưu lượng bởi mesh.
Một backend vừa scale từ 4 lên 20 pod nhưng một số client vẫn chỉ gọi tới các pod cũ trong vài phút; nhóm vận hành cần đối chiếu kết quả service discovery tại proxy với danh sách EndpointSlice của Kubernetes.
Đội phát triển bật cân bằng tải ở phía ứng dụng song Linkerd cũng chọn endpoint của Kubernetes Service; lưu lượng phân bố không đều và việc so sánh request theo từng pod gây hiểu nhầm.
Một upstream có pod xử lý nhanh và pod xử lý chậm rõ rệt; sau khi bật Linkerd, p95 khác nhau theo pod đích nhưng dashboard chỉ hiển thị số liệu ở cấp Service.
API tra cứu có thời gian phản hồi ngắn nhưng bắt đầu tăng lỗi khi backend vừa rollout; đội vận hành cân nhắc retry ở tầng mesh trong khi ứng dụng đã có cơ chế thử lại riêng.
Một endpoint POST ghi thanh toán bị mất kết nối sau khi backend đã commit, còn chính sách retry ở tầng giao tiếp và ứng dụng cùng thử lại; người dùng xuất hiện hai giao dịch giống nhau.
Nhóm điều chỉnh timeout request tại Linkerd để giảm thời gian chờ dịch vụ chậm; request xuất báo cáo dài vốn hợp lệ bắt đầu bị ngắt giữa chừng trong giờ cao điểm.
Một tác vụ nhập hàng xử lý lần lượt nhiều request tới cùng backend; số lần thử lại tự động tăng mạnh đúng lúc backend quá tải, làm throughput thực tế giảm dù proxy đang cố cải thiện độ tin cậy.
Ứng dụng chỉ định deadline gRPC ngắn hơn thời gian xử lý backend, trong khi proxy có timeout dài hơn; request thường kết thúc phía client trước khi metrics mesh ghi nhận được toàn bộ quá trình.
Một backend bị lỗi mạng trong vài phút nhưng các client ở cùng namespace vẫn báo tỉ lệ kết nối thành công cao; nhóm cần phân biệt request thực sự qua sidecar và request dùng đường dẫn bỏ qua mesh.
Traffic tới dịch vụ kho tăng đột ngột khi mở bán; Linkerd proxy của backend báo nhiều kết nối đang mở nhưng CPU ứng dụng thấp và một phần request đang chờ ở cơ sở dữ liệu.
Trang tổng quan Linkerd hiển thị success rate trên 99% còn người dùng báo tính năng thanh toán thất bại; backend trả HTTP 200 kèm mã lỗi nghiệp vụ khiến hai cách đo thành công khác nhau.
Biểu đồ Linkerd cho thấy p99 của Service tăng 3 giây sau triển khai, nhưng độ trễ ở ứng dụng backend vẫn quanh 200 ms; nhóm chưa tách các chặng proxy, mạng và thời gian chờ chọn endpoint.
Một dịch vụ nhận nhiều traffic TCP không nhận diện là HTTP; nhóm vận hành thấy bytes và connections tăng nhưng không có thống kê response code hoặc route-level latency như đối với API HTTP.
Nhóm dùng Linkerd Viz để xem thông tin service nhưng chỉ thấy traffic của một số namespace; một số workload chưa được inject còn Prometheus không scrape được metrics của vài sidecar.
Dashboard của Linkerd hiển thị lỗi tăng sau khi chính sách truy cập thay đổi, nhưng log ứng dụng không ghi nhận request đến; đội trực ca chưa có cách đối chiếu denied traffic ở proxy với tài nguyên policy vừa cập nhật.
Đội kỹ thuật muốn xem những request trực tiếp giữa hai service bằng công cụ quan sát live traffic của Linkerd, nhưng tài khoản vận hành không có quyền đọc tài nguyên cần thiết trong namespace đích.
Trong đợt debug, nhóm cấp quyền quan sát lưu lượng trực tiếp cho quá nhiều nhân viên; dữ liệu path và metadata request của dịch vụ nhạy cảm có thể bị xem vượt nhu cầu vận hành.
Một hệ thống gắn customer-id vào nhãn request telemetry do ứng dụng gửi; số lượng chuỗi thời gian metrics tăng mạnh khi traffic lên cao và bộ lưu trữ giám sát thiếu tài nguyên.
Một đội triển khai nhiều replica Linkerd control plane để tăng sẵn sàng; khi một node hỏng, các pod cũ vẫn có traffic nhưng một phần pod mới không inject hoặc không nhận danh tính kịp.
Trong quá trình khắc phục sự cố, nhóm chỉ kiểm tra các Deployment của control plane mà không kiểm tra proxy trong pod ứng dụng; thành phần điều khiển vẫn xanh nhưng data plane ở vài workload liên tục khởi động lại.
Một ứng dụng batch thực hiện hàng triệu request mỗi ngày; sau khi bật telemetry mức chi tiết cao, chi phí lưu metrics và thời gian truy vấn dashboard tăng đáng kể dù lưu lượng ứng dụng không đổi.
Hệ thống dùng Linkerd cho hai cụm Kubernetes ở hai vùng; Service ở cụm A muốn gọi Service ở cụm B nhưng tên mirrored service chưa xuất hiện trong cụm A dù gateway phía B đang chạy.
Cụm A nhìn thấy mirrored service của cụm B qua multicluster Linkerd, nhưng các request tới backend ở B liên tục timeout do hai vùng chưa mở đường mạng tới cổng gateway tương ứng.
Đội triển khai multicluster Linkerd giữa hai cụm dùng bộ trust anchor khác nhau; dịch vụ ở mỗi cụm hoạt động nội bộ nhưng kết nối qua gateway không thỏa điều kiện xác thực mesh.
Một ứng dụng gọi mirrored service ở cụm từ xa thành công khi dùng một service account, nhưng bị policy từ chối khi rollout sang service account mới vì quy tắc danh tính qua cụm chưa được cập nhật.
Nhóm chuyển traffic dự phòng sang cụm khác khi vùng chính suy giảm; backend từ xa trả dữ liệu cũ do kho dữ liệu chưa đồng bộ, dù mTLS và kết nối Linkerd đều hoạt động.
Hai cụm Kubernetes dùng dải địa chỉ pod chồng lấn; nhóm tích hợp đa cụm thấy một số tuyến đi thẳng đến IP pod không khả dụng ngoài cụm trong khi kết nối qua gateway vẫn có thể được định tuyến.
Sau khi thay thông tin truy cập Kubernetes của cụm đích, thành phần service mirror Linkerd ở cụm nguồn không cập nhật được danh sách dịch vụ; ứng dụng tiếp tục gọi endpoint cũ cho tới khi gặp lỗi.
Nhóm có ba cụm Linkerd và tên dịch vụ giống nhau ở nhiều cụm; dashboard theo tên service đơn thuần không giúp phân biệt traffic nội cụm với traffic đi qua gateway vùng khác.
Một số request qua multicluster có p95 cao hơn trong nội cụm hàng trăm mili giây; nhóm muốn đối chiếu độ trễ gateway, mạng liên vùng và backend thay vì quy toàn bộ cho sidecar.
Đội nền tảng chuẩn bị nâng cấp Linkerd nhưng cụm có nhiều phiên bản proxy sidecar do các workload được triển khai cách nhau nhiều tháng; một số tính năng chính sách mới không hoạt động đồng đều.
Control plane Linkerd đã được nâng cấp nhưng các Deployment ứng dụng chưa rollout lại để nhận phiên bản sidecar mới; metrics và hành vi data plane khác nhau giữa pod cũ và pod mới.
Nhóm thay phiên bản Linkerd và cập nhật CRD trong cùng quy trình CI/CD; các manifest policy cũ không còn được API server chấp nhận ở môi trường thử nghiệm nâng cấp.
Đợt nâng cấp Linkerd vô tình khiến proxy-injector không sẵn sàng trong vài phút; các ứng dụng đang chạy vẫn phục vụ nhưng các pod tạo mới của đợt autoscale bị chặn.
Đội vận hành định rollback control plane về bản cũ sau lỗi phát hành nhưng các proxy mới đã được inject vào workload; nhóm chưa kiểm chứng tổ hợp phiên bản điều khiển và data plane sau rollback.
Doanh nghiệp muốn gỡ Linkerd khỏi một namespace đang chạy nhiều dịch vụ; sau khi xóa annotation injection, pod cũ vẫn có sidecar và policy quan sát được không thay đổi cho đến khi workload được tạo lại.
Sau sự cố một node, các pod có proxy đã được đặt lịch lại nhưng một số replica không thể lấy danh tính hoặc đồng bộ chính sách lúc khởi động; nhóm cần phân biệt vấn đề Kubernetes, Linkerd control plane và ứng dụng.
Trong giờ cao điểm, pod Linkerd proxy bị giới hạn CPU khiến latency tăng, nhưng đội vận hành chỉ mở rộng số replica của ứng dụng; tổng số sidecar và tài nguyên phân bổ cũng tăng theo mà điểm nghẽn chưa được xác định.

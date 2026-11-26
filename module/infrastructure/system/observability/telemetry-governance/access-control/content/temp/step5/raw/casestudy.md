Một doanh nghiệp đưa metrics, logs và traces về cùng OpenTelemetry Collector, nhưng OTLP receiver được mở cho mọi pod trong cụm; một workload không thuộc đội vận hành vẫn có thể gửi telemetry mang tên dịch vụ khác vào hệ thống.
Nhóm triển khai Collector gateway trên địa chỉ có thể truy cập từ Internet để hỗ trợ chi nhánh; endpoint ingest chưa yêu cầu xác thực nên lượng dữ liệu lạ tăng đột ngột mà không có danh tính nguồn gửi.
Một ứng dụng Java gửi OTLP qua reverse proxy nhưng proxy chỉ kiểm tra đường dẫn, không kiểm tra API key; các tenant dùng chung endpoint có thể ghi sự kiện vào cùng pipeline mà không chứng minh được nguồn gốc.
Collector nhận telemetry từ ứng dụng sản xuất và thử nghiệm qua một receiver; một request thiếu metadata environment được xử lý như production và xuất hiện trên dashboard của đội trực.
Đội vận hành cấu hình xác thực ở Collector gateway nhưng các pod được phép truy cập trực tiếp Collector nội bộ qua Kubernetes Service khác; một phần dữ liệu đi vòng qua chính sách mới.
Một OpenTelemetry SDK gửi trace tới Collector bằng token nằm trong biến môi trường; bản sao cấu hình kiểm thử bị chia sẻ với bên ngoài trong khi token vẫn có quyền ghi vào production.
Đội phát triển dùng cùng một API key OTLP cho hàng trăm ứng dụng; khi một service bị xâm nhập, nhóm không xác định được ứng dụng nào đang dùng khóa bị lộ và phạm vi cần thu hồi.
Hệ thống xoay API key ingest hằng tháng nhưng một batch job chỉ chạy vào cuối quý; job mất khả năng gửi audit log ở lần chạy tiếp theo vì thông tin xác thực đã hết hạn.
Ứng dụng chuyển sang cơ chế xác thực mới của telemetry gateway nhưng một số pod trong rolling deployment vẫn dùng token cũ; tỷ lệ log bị thiếu thay đổi theo pod tiếp nhận request.
Một sidecar Collector đính kèm Authorization header vào yêu cầu OTLP; khi exporter retry qua proxy trung gian, header không được chuyển tiếp đồng nhất và một phần batch nhận 401.
Nhóm bật xác thực cho metrics scrape endpoint nhưng Prometheus chưa được cấp danh tính máy riêng; các target vẫn báo Running trong Kubernetes còn biểu đồ metrics mất dữ liệu.
Một exporter host-level công bố /metrics trên tất cả giao diện mạng và không yêu cầu xác thực; người dùng trong mạng khách đọc được tên máy, đường dẫn dịch vụ và thông tin tài nguyên nội bộ.
Đội cấu hình Collector nhận logs qua cổng Syslog nội bộ với giả định mạng là vùng tin cậy; một máy thử nghiệm gửi bản ghi giả mạo tên host production và các cảnh báo vận hành bị nhiễu.
Một ứng dụng gửi log trực tiếp đến kho lưu trữ ngoài Collector để giảm độ trễ; luồng này bỏ qua bước kiểm tra danh tính và chính sách loại bỏ trường nhạy cảm đã áp dụng ở gateway.
Trung tâm dữ liệu có hai telemetry gateway độc lập nhưng chỉ một gateway bật xác thực; sau khi cân bằng tải tự chuyển hướng, hành vi từ chối request phụ thuộc vào điểm nhận dữ liệu.
Collector dùng mTLS giữa ứng dụng và gateway, nhưng chứng chỉ client của nhiều pod được cấp chung tên danh tính; chính sách chỉ cho phép service thanh toán gửi log không phân biệt được pod của các nhóm khác.
Đội triển khai mTLS cho Collector nhưng chỉ kiểm tra CA ký chứng chỉ, không ánh xạ danh tính chứng chỉ vào quyền ingest của dịch vụ; một workload nội bộ được CA tin cậy có thể tự khai báo service.name khác.
Một certificate client của telemetry agent vừa hết hạn; backend ứng dụng vẫn khỏe nhưng metric về chính agent đột ngột biến mất và người trực không biết có phải lỗi dữ liệu hay lỗi xác thực.
Nhà vận hành xoay CA dành cho mTLS Collector; trong rolling update, một số node chưa nhận trust bundle mới nên log từ các node đó không được gửi sau khi agent kết nối lại.
Nhóm dùng chứng chỉ X.509 có SAN cho môi trường staging ở một ứng dụng production; gateway từ chối mTLS dù chứng chỉ còn hạn và được ký bởi CA nội bộ.
Đội phát triển sử dụng Kubernetes ServiceAccount mặc định cho nhiều ứng dụng; chính sách OTLP gateway phân quyền theo ServiceAccount nên không thể tách quyền gửi telemetry giữa các nhóm.
Một pod Collector được cấp Kubernetes RBAC cho phép liệt kê toàn bộ Secrets chỉ để làm giàu metadata pod; trong đợt rà soát bảo mật, quyền này vượt xa nhu cầu thu thập namespace và node.
Collector dùng k8sattributes processor để thêm namespace và pod vào resource metadata nhưng token ServiceAccount thiếu quyền đọc pod; các bản ghi không được gắn danh tính nguồn như chính sách truy cập dự kiến.
Nhóm cấp một token Kubernetes ServiceAccount dài hạn cho Collector chạy ngoài cụm; khi token được tìm thấy trong log debug, không ai biết các hệ thống nào còn giữ bản sao.
Telemetry gateway xác minh token ServiceAccount theo tên nhưng không kiểm tra audience dự kiến; một token dành cho API khác được trình tới gateway và hành vi kiểm tra quyền không đúng thiết kế.
Một collector chạy trên máy ảo đăng nhập bằng tài khoản người dùng của kỹ sư thay vì danh tính máy; khi kỹ sư nghỉ việc, toàn bộ logs của máy ảo ngừng được gửi.
Ứng dụng gửi telemetry đến dịch vụ đám mây bằng access key tĩnh trong image Docker; khi image được dùng để chạy môi trường đào tạo, khóa production cũng bị mang sang môi trường mới.
Đội nền tảng muốn cấp quyền ingest ngắn hạn bằng workload identity nhưng một service phụ thuộc file credential cố định; sau đợt thay cơ chế xác thực, chỉ service đó mất telemetry.
Một Collector vừa có quyền đọc metadata Kubernetes vừa có quyền ghi vào nhiều kho lưu trữ; một lỗi cấu hình output khiến telemetry môi trường thử nghiệm được xuất vào nơi lưu dữ liệu sản xuất.
Chứng chỉ mTLS cho máy gửi telemetry còn hạn nhưng máy chủ của gateway không trình đủ chuỗi chứng chỉ tin cậy; tất cả agent trên một phiên bản hệ điều hành báo lỗi kết nối còn các máy khác bình thường.
Một nhóm dùng cùng credential cho quyền ghi logs và quyền đọc logs; khi credential của collector bị lộ, đối tượng ngoài ý muốn còn có thể truy vấn dữ liệu vận hành đã lưu.
Đội cấu hình quyền Elasticsearch cho Logstash bằng tài khoản quản trị toàn cụm; một pipeline ghi log chỉ cần quyền tạo tài liệu nhưng đang có thể sửa chính sách lưu trữ và vai trò người dùng.
Kho metrics cho phép remote_write và query API bằng cùng token; một ứng dụng chỉ cần ghi metric lại có khả năng đọc chuỗi của các dịch vụ không liên quan.
Kho traces chấp nhận token có quyền truy vấn và xóa dữ liệu trong khi dashboard chỉ cần quyền xem; nhóm phát hiện sự kiện xóa trace không rõ nguồn khi rà soát.
Một dịch vụ nền chạy báo cáo SLO được cấp quyền đọc toàn bộ log và trace để lấy vài metric tổng hợp; nhóm pháp chế đặt câu hỏi về việc dịch vụ đọc được dữ liệu cá nhân không cần thiết.
Nhóm hỗ trợ chỉ được phép xem dashboard lỗi ứng dụng nhưng tài khoản Grafana còn có quyền sửa nguồn dữ liệu và thông tin truy cập backend; một thay đổi nhầm làm gián đoạn quan sát của đội khác.
Trong Elasticsearch, vai trò read-only với index logs-* bao gồm cả log kiểm toán bảo mật; nhân viên hỗ trợ sản phẩm nhìn được bản ghi không thuộc phạm vi công việc.
Một tổ chức áp role-based access control (RBAC) theo phòng ban cho kho telemetry, nhưng người trực liên nhóm cần xem dữ liệu một sự cố cụ thể; quyền toàn cục được cấp tạm rồi bị quên thu hồi.
Nhân viên mới được thêm vào nhóm người dùng SSO dành cho đọc dashboard nhưng group mapping vô tình gắn vai trò admin; tài khoản có thể sửa các quy tắc cảnh báo của toàn doanh nghiệp.
Đội nền tảng tạo vai trò chỉ đọc cho dashboard, nhưng một plugin hoặc data source cho phép chạy truy vấn backend qua tài khoản dịch vụ có quyền rộng hơn vai trò người dùng.
Trong kỳ nghỉ, một nhân viên được phân quyền tạm thời xem trace hệ thống thanh toán; sau kỳ trực, quyền vẫn tồn tại vì không có ngày hết hạn và quy trình thu hồi rõ ràng.
Kho observability có ba vai trò viewer, editor và admin nhưng không phân biệt môi trường dev và production; kỹ sư có quyền editor trong dự án thử nghiệm cũng sửa được dashboard production.
Một bảng phân quyền ghi nhóm Finance chỉ được đọc metric tổng hợp, nhưng API truy vấn phía dưới vẫn cho phép lấy log giao dịch thô; dashboard che thông tin không thực sự hạn chế dữ liệu.
Trên một hệ thống tracing, người dùng chỉ được phép tìm theo service của mình nhưng endpoint truy vấn trực tiếp không thực hiện cùng bộ lọc; họ có thể mở trace ID được nhóm khác gửi cho.
Team marketing được phép xem metric doanh thu theo giờ, nhưng tài khoản đọc có thể truy vấn labels chứa ID khách hàng trong series gốc; cơ chế phân quyền chưa tách dữ liệu tổng hợp và dữ liệu chi tiết.
Một công ty nhiều tenant lưu logs vào cùng cluster Elasticsearch và dựa vào tên Kibana Space để tách khách hàng; người dùng truy cập API tìm kiếm ngoài Kibana vẫn thấy tài liệu tenant khác.
Gateway nhận header X-Tenant-ID từ client và dùng nó để định tuyến OTLP; một ứng dụng tenant A gửi header tenant B và ghi trace vào kho của khách hàng khác.
Collector gắn tenant.id từ resource attributes do ứng dụng tự cung cấp; một service bị cấu hình nhầm phát tenant.id khác, khiến logs xuất hiện trong dashboard của khách hàng không liên quan.
Nhóm dùng mTLS để xác thực máy gửi nhưng không ràng buộc chứng chỉ với tenant.id khai báo trong payload; dữ liệu của hai tenant bị lẫn khi một agent dùng chung chứng chỉ.
Hai khách hàng dùng cùng tên service checkout và cùng mã trace ID do lỗi thư viện; khi kho trace không phân vùng theo tenant, kết quả tìm kiếm bị ghép hoặc hiển thị dữ liệu sai nguồn.
Hệ thống lấy tenant từ JWT tại telemetry gateway nhưng Collector downstream lại ưu tiên header tenant do ứng dụng gửi; hai điểm áp dụng chính sách không thống nhất khiến log bị định tuyến sai.
Một dịch vụ SaaS dùng chung process Java để phục vụ hàng nghìn tenant; nhóm gán tenant.id làm resource attribute toàn tiến trình nên request của nhiều khách hàng có thể mang nhãn cùng một tenant.
Nhóm tách metrics theo tenant bằng nhãn tenant_id nhưng giữ chúng trong một backend dùng token truy vấn chung; dashboard có bộ lọc tenant song API query vẫn có thể bỏ bộ lọc đó.
Một công ty dùng cùng bucket lưu object cho log của nhiều tenant và đặt prefix theo tên khách hàng; tài khoản truy xuất của một tenant được cấp quyền đọc cả bucket thay vì prefix của mình.
Dữ liệu của tenant A được nhân bản sang vùng dự phòng, nhưng chính sách truy cập ở vùng đó chỉ kiểm tra environment chứ không xét tenant; khi failover, quyền đọc thay đổi.
Một khách hàng được xóa khỏi hệ thống nhưng API key telemetry của họ vẫn còn hợp lệ; sau ngày chấm dứt hợp đồng, log và metric mới vẫn được chấp nhận.
Khi tenant được đổi tên miền và chuyển tài khoản quản trị, collector lưu thông tin tenant cũ trong cấu hình tĩnh; một phần traces tiếp tục gửi về tổ chức trước đây.
Nhóm chạy backfill logs từ kho lưu trữ cũ nhưng quên gắn tenant_id sau biến đổi định dạng; sự kiện được đưa vào vùng dữ liệu chung và được nhiều người dùng tìm thấy.
Tenant B có lưu lượng telemetry tăng đột ngột làm backend quá tải; quyền và quota ingest chưa được tách nên telemetry của tenant A cũng bị bỏ trong cùng hàng đợi.
Một nhà cung cấp SaaS cho mỗi tenant một quota lưu metrics nhưng chỉ kiểm soát tổng request của gateway; tenant gửi nhiều time series với cardinality lớn làm chi phí chung tăng bất thường.
Nhóm áp quyền xem trace theo tenant tại truy vấn đầu tiên, nhưng tính năng mở các span liên quan sử dụng endpoint khác không lọc tenant; người dùng nhìn thấy metadata của dịch vụ khách hàng khác.
Một người quản trị tạo dashboard dùng chung với biến tenant_id mặc định; link chia sẻ mang giá trị tenant cũ và người khác nhìn thấy các panel không thuộc tài khoản của mình.
Nhóm tách các namespace Kubernetes theo tenant nhưng Collector được chạy toàn cụm với cấu hình xuất về một index duy nhất; tài liệu không giữ nhãn tenant đủ tin cậy để lọc quyền.
Trong lúc chuyển dữ liệu metrics sang backend mới, pipeline sao chép bỏ nhãn tenant do quy tắc relabel; những chuỗi được ghi vào khu vực mặc định thay vì vùng dữ liệu tương ứng.
Truy vấn dashboard theo nhiều tenant sử dụng quyền hệ thống có thể đọc hết dữ liệu; một tham số tenant rỗng làm API trả toàn bộ kết quả thay vì một tập không có quyền.
Một nhóm cấp quyền đọc log bằng label environment=prod nhưng quên ràng buộc region; kỹ sư chi nhánh có thể xem log khách hàng thuộc vùng có chính sách dữ liệu riêng.
Đội phát triển bật SSO cho Grafana nhưng một số tài khoản local admin được tạo trước đó vẫn dùng mật khẩu cũ; nhóm bảo mật không đối soát được mọi con đường đăng nhập.
Một nhân viên bị thu hồi tài khoản SSO nhưng phiên dashboard đã đăng nhập từ trước còn hiệu lực dài ngày; người đó vẫn mở được log một thời gian sau khi bị khóa danh tính.
Dashboard được chia sẻ qua public link để giúp đối tác xem chỉ số sự cố; link được chuyển tiếp ngoài nhóm dự kiến và vẫn truy cập được sau khi sự cố kết thúc.
Một báo cáo KPI dùng snapshot dashboard chứa dữ liệu hạ tầng nội bộ được gửi bằng email; dù tài khoản người nhận không có quyền vào hệ thống, bản sao hình ảnh vẫn lộ thông tin.
Nhóm cấp quyền chỉnh sửa dashboard theo folder nhưng một panel sử dụng data source chứa thông tin tài chính; người chỉnh sửa có thể thay query để đọc thêm dữ liệu chưa dự định hiển thị.
Ứng dụng API truy vấn log dùng OAuth access token của người dùng, nhưng một endpoint nội bộ bỏ kiểm tra scope; cùng token chỉ có quyền metrics vẫn lấy được logs.
Đội xây proxy query metrics theo nhóm khách hàng nhưng cache key chỉ chứa câu truy vấn và thời gian, không có danh tính tenant; response được lưu từ khách hàng trước có thể được trả cho người khác.
Một dịch vụ hỗ trợ khách hàng sử dụng service account để truy vấn trace thay người dùng; không có cách truy vết yêu cầu truy cập tới nhân viên đã thực hiện thao tác.
Hệ thống dùng cơ chế xác thực Basic Auth cho API traces cũ, trong khi dashboard đã dùng OIDC; nhóm chưa xác định cách quản lý vòng đời thông tin đăng nhập giữa hai con đường truy cập.
Một API backend hỗ trợ điều tra chỉ cần đọc logs theo service, nhưng credential của API còn quyền sửa index template; một lần triển khai lỗi làm thay đổi mapping của dữ liệu thu thập mới.
Grafana được truy cập qua reverse proxy thêm header định danh người dùng; một đường mạng cho phép gọi thẳng vào Grafana và tự gửi header, khiến danh tính truy cập không còn đáng tin cậy.
Đội bật xác thực mTLS giữa dashboard và truy vấn backend nhưng dùng cùng một certificate cho tất cả ứng dụng nội bộ; log truy cập backend không phân biệt được ứng dụng nào đã đọc dữ liệu.
Một chương trình tạo báo cáo tự động dùng token dịch vụ có hạn sử dụng một ngày nhưng chỉ chạy mỗi tháng; lần thực thi tiếp theo không lấy được số liệu và bộ phận quản trị nghĩ dữ liệu đã mất.
Trong một môi trường air-gapped, dịch vụ xác minh JWT cần tải khóa công khai từ hệ thống danh tính bên ngoài; khi mạng không khả dụng, API truy vấn telemetry từ chối cả những request còn hợp lệ.
Một tenant được phép xem metric tổng quan nhưng không được phép xem trace chứa URL có tham số cá nhân; cùng một account vẫn có thể mở exemplars dẫn thẳng tới trace chi tiết.
Đội xây dashboard từ query có tham số service lấy trực tiếp từ URL; người dùng đổi giá trị thành service nhạy cảm và nhận dữ liệu dù giao diện không cho chọn service đó.
Một nguồn metrics lưu label user_email từ bản phát hành cũ; vai trò viewer bị giới hạn quyền xem logs nhưng vẫn có thể đọc email thông qua API labels của metrics.
Kho traces có span attributes chứa customer_id và payload lỗi; quyền tìm kiếm service được cấp rộng khiến người dùng có thể truy vấn thông tin không liên quan tới công việc.
Một hệ thống logging che email khi hiển thị trong dashboard, nhưng API export dữ liệu gốc không áp cùng chính sách ẩn trường; nhân viên có quyền tải CSV đọc được thông tin cá nhân.
Đội bảo mật cấm lưu token trong logs nhưng trong Collector chỉ kiểm tra trường Authorization ở cấp cao; token xuất hiện trong message dạng text và được ghi nguyên vào kho tập trung.
Một công cụ profiling lưu tên file và đường dẫn mã nguồn nhạy cảm; phân quyền truy cập profiler được dùng chung với quyền xem CPU metric và nhiều nhóm thấy thông tin không cần thiết.
Một đơn vị giữ log audit hoạt động người dùng dài hơn application logs, nhưng cả hai cùng vào một index và cùng chính sách xóa; người quản trị không thể áp retention theo phân loại bảo mật.
Nhóm đặt quy tắc giới hạn quyền ở dashboard, nhưng dữ liệu log chưa được đánh dấu mức độ nhạy cảm; API không phân biệt bản ghi vận hành thông thường và bản ghi chứa dữ liệu được bảo vệ.
Đội xây ABAC dựa trên nhãn sensitivity và owner_team nhưng nhiều sự kiện từ dịch vụ cũ không có hai nhãn này; các policy engine khác nhau cho phép hoặc chặn dữ liệu thiếu thuộc tính theo cách không thống nhất.
Một policy-as-code cho Collector chỉ cho phép gửi logs đến một số endpoint, nhưng pipeline khai báo exporter mới bằng tên khác vẫn vượt qua kiểm tra cấu hình hiện có.
Nhóm quản lý phân quyền observability bằng Terraform nhưng một quản trị viên sửa role trực tiếp trên giao diện; lần chạy GitOps sau ghi đè quyền và sự cố trực ca tái diễn.
Một pull request thay đổi policy-as-code để cho nhóm vận hành xem traces production; CI chỉ kiểm tra cú pháp YAML, không mô phỏng trường hợp người dùng khác team truy vấn dữ liệu nhạy cảm.
Đội cấp quyền rộng hơn cho một service qua chính sách Rego của OPA để xử lý sự cố tạm thời; sau khi incident kết thúc, thay đổi vẫn nằm trong repository vì không có thời hạn hiệu lực.
Một chính sách Cedar hoặc Rego lọc tenant theo user.claims.tenant_id nhưng token của vài tài khoản cũ không mang claim này; kết quả phân quyền không đồng nhất giữa dashboard và API.
Chính sách đặt mặc định cho phép khi dịch vụ PDP không phản hồi; trong outage hệ thống phân quyền, API truy vấn dữ liệu vận hành tiếp tục phục vụ mà không xác nhận quyền.
Nhóm đổi chính sách từ allowlist sang denylist để dễ vận hành; một vai trò mới không nằm trong danh sách cấm có thể đọc toàn bộ traces sản xuất.
Đội dùng regex trong policy-as-code để cho phép namespace dev-* nhưng biểu thức khớp cả một namespace production đặt tên tương tự; quyền đọc log rộng hơn chủ đích.
Trong một đợt nâng cấp, dashboard áp phiên bản policy mới còn proxy API đang dùng bản cũ; cùng người dùng có thể xem panel nhưng truy vấn API trực tiếp bị từ chối hoặc ngược lại.
Một tổ chức có nhiều cluster và đồng bộ policy bằng GitOps; một cluster mất kết nối kho cấu hình và tiếp tục dùng quyền cũ sau khi một nhân viên đã bị thu hồi.
Nhóm viết kiểm thử chính sách với vài người dùng mẫu nhưng không bao phủ người dùng thuộc nhiều team và tenant; một quy tắc ưu tiên matcher mở rộng quyền ngoài trường hợp dự kiến.
Đội vận hành không biết policy nào đã cho phép một request đọc log; response API chỉ trả dữ liệu hoặc 403, còn nhật ký quyết định phân quyền thiếu phiên bản policy và danh tính chủ thể.
Một tài khoản service có quyền ghi metrics và đọc traces được tái sử dụng trong nhiều pipeline; khi cần khóa quyền một pipeline, nhóm không thể thu hồi riêng mà không ảnh hưởng pipeline khác.
Nhóm dự định chấm dứt quyền truy cập cho một khách hàng, nhưng bản sao dữ liệu telemetry đã được đồng bộ sang một backend dự phòng với bộ role mapping cũ; quyền đọc vẫn tồn tại trên đường dự phòng.
Đội theo dõi chỉ số số lần đăng nhập dashboard nhưng không ghi lại từng truy vấn dữ liệu nhạy cảm; sau sự cố rò rỉ thông tin, không biết ai đã đọc trace nào và vào thời điểm nào.
Một API audit log ghi actor là 'system' cho mọi truy vấn do backend thay mặt người dùng; nhóm điều tra không phân biệt được hành động của ứng dụng với hành động do một kỹ sư yêu cầu.
Người quản trị xuất hàng nghìn log từ production sang máy cá nhân để điều tra; hệ thống chỉ lưu dấu hiệu đăng nhập thành công và không ghi sự kiện export dữ liệu.
Một thành viên thay đổi role viewer thành editor trong dashboard; sau vài ngày một rule cảnh báo bị sửa nhầm nhưng không có lịch sử ai đã cấp quyền và ai đã thay đổi rule.
Nhóm muốn kiểm tra quyền của credential truy vấn traces nhưng API key không có owner, mục đích sử dụng hoặc hạn hết hiệu lực; không ai biết có thể thu hồi khóa an toàn hay không.
Đội vận hành bật audit logging chi tiết mọi query trên kho metrics; khối lượng audit event quá lớn khiến log kiểm toán bị bỏ trong giờ cao điểm và hệ thống thiếu bằng chứng đúng lúc cần.
Log kiểm toán quyền truy cập được gửi về cùng Collector và kho lưu trữ mà tài khoản admin bị điều tra có quyền chỉnh sửa; tính toàn vẹn của bằng chứng bị đặt nghi vấn.
Một nhân viên được cấp quyền xem log production theo yêu cầu hỗ trợ khẩn, nhưng ticket phê duyệt và thời điểm thu hồi không được liên kết với nhật ký truy cập thực tế.
Đội bảo mật rà soát quyền mỗi quý nhưng nhóm SRE thường thay người trực hằng tuần; hàng chục tài khoản cũ tiếp tục có quyền truy vấn dữ liệu sau khi đổi lịch on-call.
Hệ thống chỉ phát cảnh báo khi có nhiều lần đăng nhập sai vào dashboard; một token đọc log hợp lệ bị lạm dụng để truy vấn hàng triệu bản ghi mà không có dấu hiệu bất thường nào được theo dõi.
Người trực chia sẻ credential admin để khắc phục lỗi lúc đêm khuya; sau sự cố, log cho biết tài khoản admin đã thay đổi policy nhưng không xác định được cá nhân thực hiện.
Nhóm kích hoạt quyền break-glass để khôi phục khả năng điều tra khi dịch vụ danh tính ngừng hoạt động; tài khoản khẩn cấp không có giới hạn thời gian và có thể được dùng tiếp sau khi hệ thống phục hồi.
Một yêu cầu hỗ trợ từ đối tác cần truy vấn trace thuộc tenant riêng trong một giờ; kỹ sư được cấp quyền toàn bộ cluster vì không có role tạm hạn chế theo tenant và thời gian.
Trong đợt diễn tập ứng phó sự cố, API metrics từ chối truy vấn của người trực dù dashboard vẫn mở được; quyền đọc chưa được kiểm thử end-to-end với tài khoản on-call thực tế.
Một nhóm kiểm thử khả năng cô lập tenant chỉ trên giao diện, nhưng chưa thử API labels, search, export và mở trace trực tiếp; kiểm toán sau phát hiện các đường truy cập chưa áp cùng policy.
Đội triển khai kiểm thử policy-as-code trên staging với dữ liệu giả không có trường nhạy cảm; production dùng logs và traces có thuộc tính khác, gây ra quyết định phân quyền ngoài dự kiến.
Trong lúc khôi phục Elasticsearch từ snapshot, role mappings và quyền trên index mới không được đồng bộ đầy đủ; một số người dùng mất quyền hợp lệ còn nhóm khác đọc được dữ liệu nhiều hơn trước.
Một dịch vụ observability thay backend lưu trữ metrics nhưng giữ nguyên dashboard và token cũ; backend mới diễn giải quyền ghi/đọc khác dẫn đến chênh lệch quyền sau chuyển đổi.
Doanh nghiệp mở thêm vùng dữ liệu theo yêu cầu cư trú dữ liệu; một Collector gateway vẫn xuất traces của khách hàng vùng A sang kho ở vùng B vì policy egress chỉ xét service, không xét region.
Đội ứng cứu nhận một loạt lỗi 403 từ Collector sau đợt thay quyền, nhưng ứng dụng nghiệp vụ vẫn khỏe; thiếu metric và alert cho chính tầng access control khiến họ không biết telemetry bị gián đoạn.
Trong một sự cố nghi ngờ lộ API key ingest, đội cần thu hồi và cấp lại danh tính máy cho hàng trăm agent mà không làm mất logs điều tra; hiện chưa có bản đồ credential tới pipeline và owner.
Một tổ chức gom metrics, logs và traces trong một cổng truy vấn thống nhất nhưng mỗi backend dùng bộ danh tính và quyền khác nhau; người dùng được cấp quyền vừa đủ ở backend này lại bị cấp quá rộng ở backend khác.

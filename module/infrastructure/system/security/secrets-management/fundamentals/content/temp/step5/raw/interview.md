Trong kiến trúc ứng dụng, làm thế nào để phân biệt secret với cấu hình thông thường và dữ liệu nhạy cảm khác?
Những trường thông tin nào nên có trong một inventory tập trung để theo dõi secret và các hệ thống đang sử dụng chúng?
Bạn sẽ thiết lập và duy trì trách nhiệm sở hữu secret như thế nào khi ứng dụng, nhóm phụ trách hoặc mục đích sử dụng thay đổi?
Quy trình tạo API key hoặc token cần sử dụng nguồn entropy và bộ sinh số ngẫu nhiên mật mã như thế nào để tránh giá trị dễ đoán, thiên lệch hoặc bị tái sử dụng?
Khi thiết kế API key, vì sao nên tách public identifier khỏi secret value và giới hạn phạm vi quyền của key?
Làm thế nào để xác định scope, audience và thời hạn hợp lý cho một credential dùng giữa các dịch vụ?
Bạn sẽ đánh giá entropy và độ dài cần thiết của secret dựa trên mô hình đe dọa và khả năng dò đoán như thế nào?
Những rủi ro nào xuất hiện khi secret được gửi qua email, chat hoặc ticket, và quy trình chia sẻ an toàn nên được tổ chức ra sao?
Secret manager tập trung giúp giảm những vấn đề nào so với việc lưu secret trong file cấu hình của từng ứng dụng?
Bạn sẽ so sánh dịch vụ secret manager do cloud cung cấp với giải pháp tự vận hành dựa trên tiêu chí nào?
Kiến trúc secret manager cần đáp ứng những yêu cầu nào về tính sẵn sàng, khả năng mở rộng và phục hồi khi lỗi?
Làm thế nào để bảo vệ secret khi lưu trữ bằng mã hóa envelope và phân tách trách nhiệm giữa các khóa?
Data Encryption Key và Key Encryption Key có vai trò khác nhau như thế nào trong kiến trúc quản lý secret?
Bạn phân biệt rotation của khóa mã hóa trong KMS với rotation của secret ứng dụng như thế nào?
Khi nào nên sử dụng HSM hoặc khóa riêng không thể export thay vì lưu private key dưới dạng secret thông thường?
Bạn sẽ thiết kế mã hóa, kiểm soát truy cập và kiểm tra tính toàn vẹn cho bản sao lưu của secret manager ra sao?
Làm thế nào để secret manager xác thực danh tính workload trước khi cấp phát secret?
Bạn sẽ áp dụng RBAC hoặc ABAC để giới hạn ai và workload nào được đọc, ghi, rotate hoặc revoke từng nhóm secret như thế nào?
Vì sao nên phân tách namespace, path hoặc project của secret theo ứng dụng và môi trường triển khai?
Workload identity giúp giảm rủi ro gì so với việc nhúng credential dài hạn vào cấu hình dịch vụ?
Bạn sẽ thiết kế xác thực workload bằng OIDC federation hoặc cloud identity để cấp credential ngắn hạn ra sao?
Trong một hệ thống mới khởi động, làm thế nào để bootstrap quyền truy cập secret mà không tạo vòng phụ thuộc credential?
Những rủi ro nào phát sinh từ service account key tĩnh và cách chuyển dần sang danh tính workload ngắn hạn là gì?
Dynamic secrets cho cơ sở dữ liệu hoạt động như thế nào và trong trường hợp nào chúng có lợi hơn credential dùng chung?
Bạn sẽ quản lý lease, TTL, gia hạn và tự động thu hồi dynamic credential như thế nào?
Khi ứng dụng cache secret để giảm độ trễ, làm thế nào để giới hạn thời gian lưu và xử lý khi secret bị thu hồi?
Secret có thể còn tồn tại ở những vị trí nào trong bộ nhớ, dump, swap hoặc crash report của tiến trình?
Bạn sẽ so sánh việc inject secret qua environment variable, file mount và sidecar theo rủi ro vận hành nào?
Làm thế nào để ngăn secret xuất hiện trong application log, trace, metric label và thông báo lỗi?
Pipeline CI/CD nên lấy secret ở thời điểm nào và giới hạn quyền của job build hoặc deploy ra sao?
Bạn sẽ bảo vệ secret khi workflow chạy từ pull request không đáng tin cậy hoặc mã nguồn do bên ngoài đóng góp như thế nào?
Những bề mặt nào trong pipeline build container như build argument, biến môi trường, cache, log và artifact có thể làm lộ secret, và bạn sẽ kiểm soát chúng ra sao?
State, plan và artifact của công cụ Infrastructure as Code có thể chứa secret ở đâu, và cần kiểm soát mã hóa, truy cập, lưu trữ và che giấu giá trị như thế nào?
Làm thế nào để tách secret giữa development, test, staging và production để tránh truy cập chéo môi trường?
Kubernetes Secret được encode Base64 có bảo đảm bí mật dữ liệu hay không, và cần bổ sung lớp bảo vệ nào?
Bạn sẽ cấu hình encryption at rest cho Kubernetes Secret trong etcd và quản lý khóa mã hóa đó như thế nào?
RBAC, namespace và service account trong Kubernetes cần phối hợp ra sao để pod chỉ đọc đúng secret cần thiết?
Bạn sẽ lựa chọn giữa CSI driver, external secret controller và cơ chế mount secret khác dựa trên tiêu chí nào?
Làm thế nào để dùng projected service account token có audience và thời hạn giới hạn cho workload trong Kubernetes?
Vì sao không nên bake secret vào image hoặc layer của container, và cách cung cấp credential tạm thời an toàn cho bước build là gì?
Bạn sẽ xây dựng lịch rotation secret dựa trên mức độ nhạy cảm, thời hạn, mức phơi nhiễm và yêu cầu vận hành như thế nào?
Làm thế nào để rotate database credential mà không gây downtime cho ứng dụng đang chạy?
Bạn sẽ tổ chức vòng đời cấp mới, phân phối, chồng lấn hiệu lực và thu hồi chứng thư TLS hoặc private key ra sao?
Trong tình huống nào cần revoke secret ngay lập tức thay vì chờ đến kỳ rotation tiếp theo?
Làm thế nào để lập bản đồ dependency giữa secret, workload, dịch vụ và nhà cung cấp nhằm đánh giá tác động khi rotate hoặc revoke?
Bạn sẽ triển khai secret scanning ở pre-commit, pull request, CI và repository server-side như thế nào?
Entropy-based detection và pattern-based detection có ưu nhược điểm gì khi tìm secret trong mã nguồn và log?
Khi secret scanner phát hiện một giá trị nghi là credential, quy trình xác minh và xử lý false positive nên diễn ra ra sao?
Vì sao xóa secret khỏi commit mới chưa đủ khi credential đã xuất hiện trong Git history hoặc artifact đã phát hành?
Mười phút đầu tiên khi phát hiện API key production bị công khai cần ưu tiên những hành động nào?
Làm thế nào để xác định phạm vi ảnh hưởng và các lần sử dụng trái phép sau khi một secret bị lộ?
Bạn sẽ phối hợp containment, revoke, rotate, điều tra và khôi phục dịch vụ khi credential bị xâm phạm như thế nào?
Nếu tài khoản quản trị secret manager bị chiếm quyền, những lớp kiểm soát và trình tự ứng phó nào cần được kích hoạt?
Audit log của secret manager nên ghi những sự kiện nào để hỗ trợ điều tra mà không ghi lại giá trị secret?
Làm thế nào để phát hiện hành vi truy cập secret bất thường theo workload, principal, thời điểm và khối lượng truy xuất?
Bạn sẽ thiết kế break-glass access cho tình huống secret manager gặp sự cố mà vẫn giữ được khả năng kiểm toán ra sao?
Separation of duties nên được áp dụng thế nào giữa người tạo secret, người phê duyệt quyền và người vận hành rotation?
Bạn sẽ quản lý policy as code cho quyền truy cập secret, review thay đổi và kiểm tra drift như thế nào?
Làm thế nào để bảo đảm cách ly secret giữa tenant khi nhiều khách hàng dùng chung secret manager hoặc hạ tầng?
Khi sử dụng SaaS hoặc nhà cung cấp bên thứ ba, bạn cần đánh giá những khía cạnh nào về quyền truy cập, lưu giữ và xóa secret?
Quy trình offboarding nhân viên cần cập nhật những quyền, token và secret nào để tránh credential còn hiệu lực sau khi nghỉ việc?
Khi một workload hoặc môi trường bị decommission, làm thế nào để xác nhận mọi secret liên quan đã được thu hồi và xóa đúng cách?
Bạn sẽ xây dựng kế hoạch disaster recovery cho secret manager khi mất vùng triển khai hoặc mất quyền truy cập KMS như thế nào?
Những bước kiểm thử nào chứng minh bản sao lưu secret manager có thể phục hồi và các workload có thể xác thực lại sau phục hồi?
Bạn sẽ đặt chính sách retention và deletion cho secret, version cũ, lease metadata và audit record dựa trên tiêu chí nào?
Làm thế nào để phát hiện và giảm shadow secrets do nhóm phát triển tự tạo ngoài quy trình quản trị tập trung?
Bạn sẽ quản lý việc cấp phát, phê duyệt và rà soát personal access token do nhà phát triển tự tạo như thế nào để tránh token dài hạn hoặc quyền truy cập vượt nhu cầu?
Bạn sẽ quản lý signing key cho JWT hoặc dữ liệu ký số, bao gồm key identifier, rollover và thu hồi khóa bị lộ ra sao?
Với ứng dụng chạy trên trình duyệt, làm thế nào để phân biệt giá trị cấu hình công khai với secret tuyệt đối không được gửi xuống client?
Bạn sẽ quyết định fail closed hay dùng cache có thời hạn khi secret manager tạm thời không truy cập được như thế nào?
Những chỉ số vận hành và bảo mật nào giúp đánh giá hiệu quả quản lý secret, rotation và phát hiện rò rỉ?
Làm thế nào để tổ chức diễn tập sự cố lộ credential và đánh giá thời gian phát hiện, thu hồi, rotation cùng khôi phục?

Khi hợp nhất CMDB, cloud inventory và scanner để tạo asset inventory, cách nào giảm bản ghi trùng mà vẫn giữ lịch sử?
A. Gộp bản ghi theo hostname hiện tại và xóa các hostname cũ khỏi danh mục.
B. Ghép theo ID tài nguyên ổn định và giữ alias lịch sử.
C. Dùng địa chỉ IP làm khóa duy nhất rồi ghi đè khi tài nguyên đổi mạng.
D. Chọn dữ liệu từ CMDB làm chuẩn và bỏ qua phát hiện từ các nguồn khác.
Đáp án đúng: B

Một subdomain chưa được quản lý xuất hiện trong passive DNS và certificate transparency; bước nào phù hợp để xác minh shadow asset?
A. Quét cổng một lần rồi coi hostname không phản hồi là tài sản đã đóng.
B. Thêm hostname vào danh sách chặn trước khi xác định dịch vụ đang dùng.
C. Đối chiếu DNS, endpoint đang phục vụ, cloud ownership và owner nghiệp vụ.
D. Chỉ kiểm tra hóa đơn cloud vì mọi hostname đều phải có tài nguyên tính phí.
Đáp án đúng: C

Khi phân loại tài sản để ưu tiên giảm attack surface, metadata nào có giá trị nhất?
A. Hostname, hệ điều hành, ngày tạo và số lượng gói phần mềm đã cài.
B. Địa chỉ IP, subnet, dung lượng đĩa và thời điểm quét gần nhất.
C. Tên nhóm kỹ thuật, vị trí rack và phiên bản công cụ giám sát đang chạy.
D. Owner, môi trường, độ nhạy dữ liệu, mức trọng yếu và exposure thực tế.
Đáp án đúng: D

Điểm khác biệt chính giữa external attack surface management và một lần quét lỗ hổng là gì?
A. Chỉ kiểm tra CVE đã công bố trên máy chủ có địa chỉ IP tĩnh.
B. Theo dõi tài sản lộ ra ngoài và thay đổi của chúng liên tục.
C. Thực hiện kiểm thử xâm nhập sâu theo kịch bản đã định trước mỗi năm.
D. Chỉ thu thập hostname từ CMDB rồi đối chiếu với bản vá hệ điều hành.
Đáp án đúng: B

Một DNS CNAME trỏ đến dịch vụ cloud đã bị xóa; kiểm soát nào giảm nguy cơ subdomain takeover?
A. Tạo thêm bản ghi wildcard để mọi hostname cũ trỏ về trang mặc định.
B. Giữ CNAME để bảo toàn liên kết và chỉ chặn truy cập bằng firewall.
C. Xác minh đích không còn được sở hữu rồi gỡ bản ghi DNS không dùng.
D. Đổi TTL xuống thấp nhưng vẫn giữ bản ghi trỏ đến tài nguyên đã xóa.
Đáp án đúng: C

Khi kiểm kê hostname public, cách nào giúp phát hiện subdomain bị bỏ sót?
A. Chỉ lấy danh sách hostname trong tài liệu kiến trúc đã được phê duyệt.
B. Chỉ chạy wordlist trên domain chính và bỏ qua tên miền của đối tác.
C. Kết hợp DNS zone, passive DNS, chứng thư và dữ liệu từ dịch vụ cloud.
D. Chỉ dùng kết quả quét cổng vì DNS không phản ánh dịch vụ đang chạy.
Đáp án đúng: C

Một máy chủ có IPv6 bật nhưng quy trình discovery chỉ quét IPv4; rủi ro nào cần xử lý?
A. IPv6 tự động mã hóa lưu lượng nên không cần kiểm kê thêm endpoint.
B. IPv6 không thể truy cập công khai nếu chưa có NAT.
C. Scanner IPv4 tự phát hiện listener IPv6 cùng hostname.
D. Endpoint IPv6 có thể lộ dịch vụ khi inventory chỉ quét IPv4.
Đáp án đúng: D

Khi lập bản đồ dịch vụ Internet-facing, dữ liệu nào giúp xác định đúng điểm vào?
A. Chỉ địa chỉ IP và số lượng kết nối trung bình của từng máy chủ.
B. Tên miền đăng ký, nhà cung cấp DNS và thời gian gia hạn chứng thư.
C. Chỉ phiên bản hệ điều hành và danh sách package trên máy chủ đích.
D. Ghi hostname, IP, port, protocol, service và owner.
Đáp án đúng: D

Để phát hiện API endpoint ngoài tài liệu, nên kết hợp nguồn nào?
A. Chỉ tài liệu OpenAPI do nhóm sản phẩm xuất bản ở đầu mỗi quý.
B. Chỉ log WAF vì mọi API request đều phải đi qua WAF của tổ chức.
C. API gateway, OpenAPI, route trong ứng dụng và lưu lượng runtime.
D. Chỉ danh sách DNS vì mỗi endpoint API cần một hostname riêng biệt.
Đáp án đúng: C

Một API version cũ được đánh dấu deprecated nhưng vẫn có client sử dụng; cách xử lý nào phù hợp?
A. Xóa route ngay khi có phiên bản mới để tránh duy trì bề mặt cũ.
B. Giữ route vô thời hạn vì client cũ không thể được phát hiện chính xác.
C. Chặn toàn bộ IP bên ngoài rồi yêu cầu mọi client chuyển sang phiên bản mới.
D. Đo telemetry người gọi, thông báo owner và đặt lịch ngừng có kiểm soát.
Đáp án đúng: D

GraphQL endpoint bật introspection trên production; đánh giá attack surface nên tập trung vào điều gì?
A. Tắt introspection trong mọi môi trường vì tính năng này luôn cho phép ghi dữ liệu.
B. Quyền truy cập object, giới hạn độ sâu, độ phức tạp và chi phí truy vấn.
C. Chỉ giới hạn kích thước HTTP body vì truy vấn sâu không ảnh hưởng tài nguyên.
D. Ẩn endpoint khỏi tài liệu public vì tên route là yếu tố bảo vệ chính.
Đáp án đúng: B

Webhook public nhận sự kiện từ đối tác; kiểm soát nào cần thể hiện trong data flow?
A. Chỉ kiểm tra IP nguồn vì địa chỉ đối tác không thay đổi theo thời gian.
B. Xác minh chữ ký, timestamp, chống replay và giới hạn payload đầu vào.
C. Chấp nhận mọi request rồi xác thực người gửi sau khi xử lý nghiệp vụ.
D. Dùng TLS phía server là đủ để chứng minh request đến từ đối tác hợp lệ.
Đáp án đúng: B

Một tính năng tải URL do người dùng cung cấp có thể truy cập metadata cloud; biện pháp nào giảm attack path SSRF?
A. Chỉ chặn hostname metadata trong giao diện nhập liệu của người dùng.
B. Chỉ kiểm tra URL bằng regex trước khi gửi request đến địa chỉ đích.
C. Cho phép mọi redirect miễn URL ban đầu dùng HTTPS và có chứng thư hợp lệ.
D. Giới hạn egress, chặn dải nhạy cảm và kiểm tra lại IP sau redirect.
Đáp án đúng: D

Khi lập data flow diagram để phân tích attack surface, yếu tố nào phải được thể hiện?
A. Tên service và ngôn ngữ triển khai của từng thành phần trong hệ thống.
B. Số lượng request mỗi giây và dung lượng CPU của từng tiến trình.
C. Ghi nguồn, đích, dữ liệu, danh tính và trust boundary.
D. Chỉ các luồng Internet công khai vì mạng nội bộ được xem là đáng tin.
Đáp án đúng: C

Ứng dụng nằm sau reverse proxy và tin header X-Forwarded-For; rủi ro nào cần đánh giá?
A. Header luôn được proxy ký mật mã nên backend không cần kiểm tra nguồn.
B. Header chỉ ảnh hưởng hiển thị log và không tác động quyết định truy cập.
C. Client có thể giả mạo header nếu proxy không xóa và đặt lại giá trị.
D. Backend tự động xác minh IP trong header bằng chứng thư TLS của client.
Đáp án đúng: C

Để xác định đường đi từ workload bị xâm nhập đến database nhạy cảm, nên phân tích gì?
A. Chỉ subnet của database vì mọi workload cùng subnet có quyền như nhau.
B. Chỉ firewall Internet-facing vì lưu lượng east-west không tạo attack path.
C. Chỉ danh sách cổng đang mở trên database mà không xét danh tính gọi.
D. Route, firewall, security group, identity và quyền truy cập ở từng hop.
Đáp án đúng: D

Một bucket chứa bản sao dữ liệu production bị public-read; đánh giá exposure nên kiểm tra gì?
A. Chỉ cấu hình mã hóa vì dữ liệu đã mã hóa không cần kiểm tra quyền đọc.
B. Kiểm tra policy, ACL và quyền truy cập object thực tế.
C. Chỉ kiểm tra website hosting vì bucket không bật hosting sẽ không public.
D. Chỉ kiểm tra quyền của owner vì policy và ACL không áp dụng cho object.
Đáp án đúng: B

Khi dựng attack path trong cloud IAM, yếu tố nào cần tính đến?
A. Chỉ policy gắn trực tiếp vào user vì role và resource policy độc lập.
B. Chỉ tên role và ngày tạo vì quyền được kế thừa từ tài khoản cloud.
C. Chỉ quyền console vì API credential không thể thay đổi cấu hình cloud.
D. Tính policy hiệu lực, role assumption và resource policy.
Đáp án đúng: D

Ứng dụng có SSRF trên VM cloud; kiểm soát metadata nào giúp giảm khả năng lấy credential?
A. Đổi tên metadata hostname để scanner không nhận diện được endpoint.
B. Bắt buộc chế độ metadata dùng token và giới hạn quyền instance role.
C. Đặt secret trong user data vì metadata service không đọc được trường này.
D. Chỉ bật TLS cho ứng dụng vì request metadata luôn được mã hóa sẵn.
Đáp án đúng: B

Một giao diện quản trị chỉ truy cập được qua mạng nội bộ; bước nào cần có trong attack surface review?
A. Kiểm tra VPN, bastion, route nội bộ, danh tính và endpoint thay thế.
B. Bỏ khỏi phạm vi vì không có địa chỉ public hoặc DNS public tương ứng.
C. Chỉ kiểm tra trang đăng nhập vì mạng nội bộ đã giới hạn người dùng.
D. Đưa subnet vào allowlist rộng để giảm lỗi kết nối từ công cụ vận hành.
Đáp án đúng: A

SSO đã triển khai nhưng ứng dụng vẫn giữ tài khoản local cũ; cách đánh giá phù hợp là gì?
A. Kiểm kê local account, luồng khôi phục và cơ chế xác thực dự phòng.
B. Xem SSO là điểm vào duy nhất vì người dùng thường ưu tiên đăng nhập tập trung.
C. Chỉ rà soát tài khoản nhân viên đang hoạt động trong nhà cung cấp danh tính.
D. Tắt audit của tài khoản local để tránh trùng với log từ SSO.
Đáp án đúng: A

Khi phân tích quyền của service account, cách nào phát hiện phạm vi truy cập thực tế?
A. Đếm số secret được lưu vì số lượng secret phản ánh mức đặc quyền.
B. Đối chiếu principal, policy gắn trực tiếp và quyền kế thừa trên tài nguyên.
C. Chỉ xem mô tả service account vì owner thường khai đúng mục đích sử dụng.
D. Chỉ kiểm tra quyền đăng nhập tương tác vì workload không dùng quyền API.
Đáp án đúng: B

Một nhóm lồng nhau cấp quyền qua nhiều tầng; cần tính toán gì khi dựng attack path?
A. Chỉ nhóm trực tiếp của người dùng vì nhóm lồng nhau không cấp quyền.
B. Tính group lồng nhau cùng quyền hiệu lực được kế thừa.
C. Chỉ role có tên quản trị vì các role còn lại không ảnh hưởng tài sản.
D. Chỉ danh sách thành viên hiện tại mà không xét policy gắn với group.
Đáp án đúng: B

Runner CI xử lý pull request không tin cậy có thể truy cập mạng nội bộ; kiểm soát nào giảm rủi ro?
A. Dùng runner dùng chung nhưng xóa workspace sau khi job hoàn tất.
B. Cho phép mọi job dùng chung credential nếu repository có branch protection.
C. Chỉ tắt log command vì mã pull request không thể truy cập môi trường runner.
D. Cô lập runner, mạng và secret khỏi job không tin cậy.
Đáp án đúng: D

Để xác minh nguồn gốc artifact trước khi triển khai, cần kiểm tra gì?
A. Chỉ tên tag và thời điểm push vì registry tự bảo đảm artifact không đổi.
B. Chỉ checksum do cùng pipeline build tạo mà không xác minh người ký.
C. Chỉ số phiên bản package vì artifact mới luôn được tạo từ source tin cậy.
D. Chữ ký, provenance, danh tính builder và liên kết với source revision.
Đáp án đúng: D

Package nội bộ có tên dễ trùng với package public; rủi ro nào cần đưa vào supply-chain review?
A. Kiểm tra dependency confusion giữa package public và nội bộ.
B. Package typosquatting chỉ xảy ra khi tên package dài hơn một ngưỡng cố định.
C. Dependency pinning làm mọi package public tự động bị từ chối khi build.
D. Package public không thể thay thế dependency nội bộ nếu version giống nhau.
Đáp án đúng: A

Secret bị commit vào repository rồi xóa ở commit mới; bước nào cần thực hiện?
A. Chỉ xóa file trong nhánh chính vì Git không giữ nội dung commit cũ.
B. Đổi tên biến môi trường để token cũ không còn được ứng dụng tìm thấy.
C. Thu hồi token và rà soát lịch sử cùng các bản sao.
D. Chỉ bật secret scanner từ lần commit sau mà không xử lý token hiện tại.
Đáp án đúng: C

Ứng dụng tích hợp SaaS qua OAuth; yếu tố nào giúp xác định exposure do tích hợp tạo ra?
A. Chỉ tên nhà cung cấp và số lượng người dùng được cấp tài khoản SaaS.
B. Chỉ vị trí datacenter vì scope OAuth không ảnh hưởng quyền dữ liệu.
C. Scope được cấp, dữ liệu chia sẻ, token lifetime và bên có thể sử dụng token.
D. Chỉ thời hạn hợp đồng vì token được cấp sẽ tự hết hiệu lực khi hợp đồng kết thúc.
Đáp án đúng: C

Một cluster Kubernetes có nhiều Service type LoadBalancer và NodePort; inventory cần làm gì?
A. Kiểm kê listener và đối chiếu route, ingress, owner.
B. Chỉ kiểm tra ingress controller vì Service khác không thể mở cổng ngoài.
C. Chỉ kiểm tra pod IP vì NodePort và LoadBalancer không tạo điểm vào riêng.
D. Chỉ dựa trên manifest Git vì cấu hình runtime luôn giống hoàn toàn source.
Đáp án đúng: A

Container có hostPath mount và chạy privileged; ranh giới nào đang bị mở rộng?
A. Workload có thể truy cập tài nguyên host vượt khỏi namespace cô lập.
B. Container được cô lập mạnh hơn vì hostPath không chia sẻ network namespace.
C. Chỉ filesystem trong container bị ảnh hưởng, không có quyền truy cập host.
D. Quyền privileged chỉ cho phép tăng CPU và memory, không thay đổi quyền kernel.
Đáp án đúng: A

Endpoint debug và metrics xuất hiện trên production; điều gì cần đánh giá trước?
A. Ẩn đường dẫn endpoint trong tài liệu là đủ để giảm exposure thực tế.
B. Chỉ kiểm tra kích thước response vì metrics không chứa thông tin vận hành.
C. Đánh giá dữ liệu lộ, xác thực và thao tác endpoint.
D. Chỉ giới hạn số request vì endpoint debug luôn ở chế độ chỉ đọc.
Đáp án đúng: C

Khi lập kế hoạch quét attack surface, cách nào bảo đảm phạm vi và an toàn?
A. Xác nhận tài sản, chủ sở hữu, cửa sổ kiểm thử và giới hạn tác động trước.
B. Quét mọi địa chỉ phát hiện được vì tài sản public mặc nhiên được phép thử.
C. Chỉ lấy danh sách IP từ scanner rồi tự mở rộng sang các mạng liên kết.
D. Bắt đầu kiểm tra khai thác trước và xin phê duyệt sau nếu có ảnh hưởng.
Đáp án đúng: A

Khi ưu tiên một exposure cần khắc phục, cách nào phản ánh rủi ro thực tế hơn?
A. Kết hợp khả năng khai thác, reachability, criticality và tác động dữ liệu.
B. Sắp xếp theo số CVE gắn với host rồi xử lý máy có nhiều CVE trước.
C. Ưu tiên mọi dịch vụ public hơn dịch vụ nội bộ bất kể dữ liệu và quyền.
D. Dùng thời điểm phát hiện làm tiêu chí chính để tránh bỏ sót finding cũ.
Đáp án đúng: A

Scanner báo package có CVE nhưng nhà cung cấp đã backport bản vá; cần xác minh thế nào?
A. Đóng finding theo số phiên bản hiển thị mà không cần kiểm tra nhà cung cấp.
B. Xác minh advisory và backport trên phiên bản đang chạy.
C. Quét lại cùng scanner nhiều lần cho đến khi cảnh báo tự biến mất.
D. Loại toàn bộ package khỏi inventory vì backport làm scanner không chính xác.
Đáp án đúng: B

Một chuỗi tấn công đi từ tài khoản developer qua CI runner đến cluster và database; cách mô hình hóa nào hữu ích?
A. Nối identity, quyền, network path và tài sản đích thành chuỗi khả thi.
B. Đánh giá riêng từng máy chủ rồi cộng điểm CVSS để suy ra đường tấn công.
C. Chỉ ghi bước cuối cùng vì các bước trung gian thuộc đội vận hành khác.
D. Xem mỗi trust boundary là độc lập nên không cần phân tích quan hệ giữa chúng.
Đáp án đúng: A

Attack surface cần được theo dõi sau mỗi thay đổi kiến trúc; cách nào phát hiện drift hiệu quả?
A. So sánh discovery định kỳ với baseline và gắn thay đổi cho owner cụ thể.
B. Chụp snapshot inventory mỗi năm rồi giữ nguyên đến kỳ audit tiếp theo.
C. Chỉ gửi cảnh báo khi số hostname public tăng, bỏ qua route và quyền mới.
D. Coi mọi thay đổi cấu hình là rủi ro cao mà không đối chiếu trạng thái trước.
Đáp án đúng: A

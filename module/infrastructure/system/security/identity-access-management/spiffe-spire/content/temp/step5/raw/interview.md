Bạn giải thích mục tiêu của SPIFFE trong việc cấp danh tính mật mã có thể xác minh cho workload trên các môi trường phân tán như thế nào?
Bạn phân biệt SPIFFE là đặc tả danh tính với SPIRE là triển khai cung cấp và xác minh danh tính workload ra sao?
Bạn mô tả cấu trúc SPIFFE ID dạng URI và ý nghĩa của trust domain cùng path như thế nào?
Bạn lựa chọn trust domain boundary theo tổ chức, môi trường, cụm hoặc miền tin cậy dựa trên tiêu chí nào?
Bạn xác định quy tắc đặt SPIFFE ID ổn định khi workload được tạo lại, di chuyển node hoặc đổi phiên bản như thế nào?
Bạn phân biệt danh tính workload với địa chỉ IP, hostname, pod name hoặc tên service trong hệ thống có autoscaling ra sao?
Bạn thiết kế naming convention cho SPIFFE ID để thể hiện service, môi trường và tenant mà không gắn danh tính với thuộc tính dễ thay đổi như thế nào?
Bạn giải thích trust domain và trust bundle liên hệ với nhau như thế nào trong việc xác minh danh tính SPIFFE?
Bạn phân biệt X.509-SVID và JWT-SVID về định dạng, cách trình bày danh tính và cơ chế xác minh ra sao?
Bạn mô tả các trường quan trọng trong X.509-SVID, đặc biệt URI SAN, public key, validity period và issuer như thế nào?
Bạn giải thích vì sao X.509-SVID thường được dùng cho xác thực workload qua mTLS như thế nào?
Bạn xác định cách một bên nhận kiểm tra X.509-SVID theo trust bundle và SPIFFE ID mong đợi ra sao?
Bạn mô tả JWT-SVID mang SPIFFE ID trong claim nào và vì sao bên xác minh cần kiểm tra audience như thế nào?
Bạn phân biệt xác thực bằng JWT-SVID với X.509-SVID về khả năng chống replay, thời hạn và cách truyền credential ra sao?
Bạn xác định khi nào nên chọn X.509-SVID và khi nào JWT-SVID phù hợp hơn cho một luồng giao tiếp cụ thể như thế nào?
Bạn giải thích giới hạn của JWT-SVID khi token bị đánh cắp trước khi hết hạn và cách giảm rủi ro replay ra sao?
Bạn phân biệt identity assertion với authorization policy và giải thích vì sao có SPIFFE ID hợp lệ chưa đủ để được phép truy cập tài nguyên như thế nào?
Bạn thiết kế policy ánh xạ SPIFFE ID hoặc thuộc tính workload sang quyền gọi API, đọc dữ liệu hay vận hành tài nguyên ra sao?
Bạn mô tả kiến trúc SPIRE gồm server, agent, datastore và các plugin chính như thế nào?
Bạn phân biệt trách nhiệm của SPIRE Server với SPIRE Agent trong cấp phát và phân phối SVID ra sao?
Bạn giải thích node attestation nhằm xác minh điều gì trước khi SPIRE Agent được tin cậy như thế nào?
Bạn so sánh node attestation dựa trên cloud instance identity, Kubernetes service account token và join token về mức bảo đảm tin cậy ra sao?
Bạn lựa chọn node attestation method cho bare metal, virtual machine, Kubernetes và cloud workload dựa trên đặc điểm môi trường nào?
Bạn giải thích rủi ro khi dùng join token tĩnh, dùng chung hoặc có thời hạn dài trong quá trình đăng ký node như thế nào?
Bạn thiết kế quy trình bootstrap để node mới chứng minh danh tính và tham gia trust domain mà không nhúng secret lâu dài vào image ra sao?
Bạn mô tả workload attestation xác định tiến trình hoặc workload nào đang yêu cầu SVID trên một node đã được attested như thế nào?
Bạn phân biệt node selector với workload selector trong SPIRE registration entry ra sao?
Bạn lựa chọn selector dựa trên namespace, service account, container image, process identity hoặc thuộc tính workload như thế nào?
Bạn đánh giá độ tin cậy của label và metadata do người dùng hoặc orchestrator cung cấp khi dùng làm workload selector ra sao?
Bạn thiết kế registration entry để một workload chỉ nhận đúng SPIFFE ID và parent identity cần thiết như thế nào?
Bạn ngăn một workload giả mạo selector của workload đặc quyền để nhận SVID có quyền rộng hơn ra sao?
Bạn quản lý registration entry khi workload đổi namespace, service account, image hoặc node mà vẫn giữ nguyên nguyên tắc least privilege như thế nào?
Bạn phân biệt selector-based registration với cấp phát SVID thủ công và đánh giá ưu nhược điểm vận hành của từng cách ra sao?
Bạn giải thích Workload API cho phép workload lấy SVID và trust bundle mà không cần tự quản lý private key như thế nào?
Bạn mô tả cách workload discovery hoặc workload API endpoint xác định workload caller dựa trên kết nối cục bộ ra sao?
Bạn bảo vệ Unix domain socket hoặc endpoint Workload API khỏi workload không được phép truy cập như thế nào?
Bạn đánh giá rủi ro khi mount SPIRE Agent socket vào container quá rộng hoặc chia sẻ giữa nhiều workload như thế nào?
Bạn mô tả luồng lấy X.509-SVID, private key và bundle qua Workload API như thế nào?
Bạn mô tả luồng lấy JWT-SVID qua Workload API và cách chỉ định audience theo mục tiêu sử dụng như thế nào?
Bạn giải thích streaming update của Workload API giúp workload nhận SVID và trust bundle mới trước khi bản cũ hết hạn như thế nào?
Bạn thiết kế workload client để xử lý reconnect, agent restart, update stream và trạng thái tạm thời không có SVID ra sao?
Bạn xác định cách workload thay certificate đang dùng mà không làm gián đoạn kết nối hoặc làm rơi request đang chạy như thế nào?
Bạn giải thích SPIRE Agent cache SVID và trust bundle nhằm phục vụ workload khi server hoặc upstream tạm thời không khả dụng ra sao?
Bạn đánh giá rủi ro stale credential khi agent mất kết nối server và cách giới hạn thời gian sử dụng SVID cũ như thế nào?
Bạn thiết kế trust bundle chứa CA material và xác định cách bên nhận dùng bundle để xác minh SVID ra sao?
Bạn phân biệt trust bundle với certificate chain của một SVID và giải thích vai trò của từng thành phần trong xác minh như thế nào?
Bạn mô tả SPIFFE federation cho phép hai trust domain trao đổi trust bundle và xác minh danh tính xuyên miền như thế nào?
Bạn xác định tiêu chí thiết lập federation với trust domain bên ngoài để tránh tin cậy quá rộng ra sao?
Bạn lựa chọn cơ chế phân phối bundle federation và bảo vệ endpoint lấy bundle khỏi bị giả mạo hoặc thay thế như thế nào?
Bạn xử lý việc một trust domain thay đổi CA hoặc trust bundle mà vẫn duy trì xác minh giữa các workload như thế nào?
Bạn lập kế hoạch bundle rotation theo giai đoạn overlap giữa CA cũ và mới để tránh gián đoạn mTLS ra sao?
Bạn phân biệt SVID rotation với trust bundle rotation và giải thích vì sao hai vòng đời này cần được điều phối như thế nào?
Bạn xác định thời hạn SVID phù hợp dựa trên khả năng cấp mới, tải hệ thống và cửa sổ rủi ro khi credential bị lộ ra sao?
Bạn xử lý SVID hết hạn khi workload không nhận được update do agent hoặc Workload API gặp sự cố như thế nào?
Bạn thu hồi hoặc vô hiệu hóa danh tính workload khi phát hiện node bị xâm nhập hoặc registration entry bị cấu hình sai ra sao?
Bạn đánh giá giới hạn của việc thu hồi certificate ngắn hạn trong môi trường phân tán và xác định cách giảm thời gian tin cậy còn lại như thế nào?
Bạn thiết kế quy trình thay CA gốc hoặc intermediate CA trong SPIRE mà không làm mất khả năng xác minh các workload đang chạy ra sao?
Bạn mô tả cách triển khai mTLS giữa hai workload dùng X.509-SVID và xác minh cả danh tính client lẫn server như thế nào?
Bạn phân biệt TLS server authentication thông thường với SPIFFE-based mutual authentication về danh tính được xác minh ra sao?
Bạn xác định cách ánh xạ SPIFFE ID từ peer certificate vào authorization policy tại service nhận request như thế nào?
Bạn thiết kế kiểm soát egress và ingress để workload chỉ thiết lập mTLS tới peer có SPIFFE ID được cho phép ra sao?
Bạn xử lý giao tiếp qua load balancer hoặc proxy khi cần giữ bằng chứng danh tính SPIFFE của workload đầu cuối như thế nào?
Bạn xác định khi nào TLS termination tại proxy làm thay đổi trust boundary và cách bảo vệ danh tính workload phía sau ra sao?
Bạn mô tả cách dùng JWT-SVID cho giao tiếp không duy trì kết nối TLS dài hạn và xác minh chữ ký qua public key tương ứng như thế nào?
Bạn thiết kế kiểm tra audience, issuer, thời hạn và SPIFFE ID khi một API nhận JWT-SVID như thế nào?
Bạn bảo vệ private key của SVID và đánh giá ranh giới giữa key do agent quản lý với key được workload nhận qua Workload API ra sao?
Bạn triển khai SPIRE trong Kubernetes và lựa chọn cách attestation node cùng workload dựa trên cluster identity, namespace và service account như thế nào?
Bạn vận hành SPIRE trên nhiều cluster hoặc nhiều cloud account mà vẫn giữ được ranh giới trust domain và quyền quản trị như thế nào?
Bạn thiết kế high availability cho SPIRE Server, datastore và agent để việc cấp mới danh tính không trở thành điểm lỗi đơn như thế nào?
Bạn đánh giá ảnh hưởng khi datastore SPIRE mất dữ liệu hoặc được restore từ backup cũ đối với registration entry và trust material ra sao?
Bạn quản lý upstream CA integration để SPIRE phát hành SVID từ một CA tin cậy mà không làm lộ signing key ra sao?
Bạn tách quyền quản trị SPIRE Server, registration API và hạ tầng CA để giảm nguy cơ một người có thể tự cấp danh tính đặc quyền như thế nào?
Bạn kiểm soát thay đổi registration entry bằng review, policy-as-code và audit để ngăn mở rộng trust ngoài ý muốn ra sao?
Bạn giám sát tỷ lệ cấp SVID, lỗi attestation, thời gian cấp phát, số lần rotation và tình trạng Workload API như thế nào?
Bạn phát hiện workload đột ngột yêu cầu SPIFFE ID mới hoặc xuất hiện selector không khớp baseline vận hành ra sao?
Bạn thiết kế audit trail để truy vết ai thay đổi registration entry, trust bundle, node join policy và quyền quản trị như thế nào?
Bạn điều tra lỗi mTLS khi hai workload đều có SVID hợp lệ nhưng không tin cậy bundle hoặc không khớp SPIFFE ID ra sao?
Bạn chẩn đoán lỗi workload không nhận được SVID bằng cách phân biệt node attestation, workload attestation, registration mismatch và Workload API connectivity như thế nào?
Bạn xử lý sự cố clock skew làm SVID bị coi là chưa có hiệu lực hoặc đã hết hạn trên một số node như thế nào?
Bạn kiểm thử federation và bundle rotation để chứng minh workload cũ, mới và workload giữa hai trust domain vẫn xác minh đúng như thế nào?
Bạn xây dựng threat model cho SPIFFE/SPIRE gồm compromise node, agent, server, upstream CA, workload và federation endpoint như thế nào?
Bạn thiết kế quy trình ứng phó khi private key hoặc SVID bị lộ để cô lập workload, xoay credential, cập nhật trust bundle và bảo toàn bằng chứng ra sao?
Bạn xác định các chỉ số và bằng chứng cần có để đánh giá SPIFFE/SPIRE đang cấp danh tính đúng workload, đúng thời hạn và đúng trust boundary như thế nào?

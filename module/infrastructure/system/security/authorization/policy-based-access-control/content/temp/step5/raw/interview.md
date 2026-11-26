Bạn phân biệt policy-based access control với RBAC và ABAC như thế nào về cách biểu diễn và đánh giá quyền?
Trong một quyết định PBAC, subject, action, resource và context liên hệ với nhau ra sao?
Bạn mô hình hóa một access request sao cho policy engine có đủ thông tin nhưng không nhận dữ liệu thừa như thế nào?
Bạn phân biệt policy, rule, permission và entitlement trong một hệ thống kiểm soát truy cập ra sao?
Những thuộc tính nào nên nằm trong định nghĩa policy và những thuộc tính nào nên được cung cấp ở thời điểm đánh giá?
Bạn xác định ranh giới giữa policy decision và policy enforcement như thế nào trong kiến trúc hệ thống?
Bạn thiết kế default-deny để bảo đảm request không khớp policy nào sẽ được xử lý an toàn ra sao?
Bạn phân biệt kết quả Permit, Deny, NotApplicable và Indeterminate trong một mô hình quyết định chính sách như thế nào?
Khi nhiều policy cùng áp dụng cho một request, bạn chọn và giải thích thuật toán kết hợp kết quả ra sao?
Bạn xử lý xung đột giữa một policy cho phép và một policy từ chối như thế nào để kết quả nhất quán?
Bạn quyết định khi nào một lỗi dữ liệu ngữ cảnh phải dẫn tới Deny và khi nào có thể trả Indeterminate ra sao?
Bạn thiết kế policy để thể hiện quyền theo thời gian, địa điểm, thiết bị và mức độ rủi ro như thế nào?
Bạn xác minh độ tin cậy, nguồn gốc và độ mới của các thuộc tính ngữ cảnh trước khi dùng chúng trong quyết định ra sao?
Bạn ngăn client giả mạo tenant, nhóm, vai trò hoặc thuộc tính thiết bị trong access request bằng cách nào?
Bạn mô hình hóa quan hệ giữa subject, resource và các thực thể liên quan để biểu diễn quyền truy cập phức tạp ra sao?
Bạn áp dụng nguyên tắc least privilege khi tạo policy cho người dùng, nhóm và workload như thế nào?
Bạn phát hiện policy quá rộng hoặc vô tình cấp quyền cho nhiều tài nguyên hơn dự kiến bằng cách nào?
Bạn thiết kế policy theo phạm vi tài nguyên cụ thể thay vì dựa trên tên hoặc ID do client tự cung cấp ra sao?
Bạn xử lý quyền truy cập chéo tenant và bảo đảm tenant context được xác minh ở đâu trong luồng request như thế nào?
Bạn biểu diễn quyền đọc, tạo, sửa, xóa và chia sẻ tài nguyên thành các action riêng biệt ra sao?
Bạn kiểm soát quyền trên từng object khi một endpoint nhận resource ID từ request như thế nào?
Bạn áp dụng policy cho truy vấn danh sách để tránh trả về các object nằm ngoài phạm vi được phép ra sao?
Bạn xử lý request hàng loạt khi một phần tài nguyên được phép và phần còn lại bị từ chối như thế nào?
Bạn đánh giá quyền kế thừa từ tài nguyên cha xuống tài nguyên con và kiểm soát ngoại lệ ra sao?
Bạn thiết kế policy cho quyền chia sẻ tạm thời, có thời hạn hoặc có thể thu hồi như thế nào?
Bạn phân biệt quyền của người dùng cuối với quyền của dịch vụ hành động thay mặt người dùng ra sao?
Bạn xử lý delegation và xác định danh tính chịu trách nhiệm cuối cùng cho một hành động như thế nào?
Bạn thiết kế policy cho workload identity và giao tiếp service-to-service theo least privilege ra sao?
Bạn tổ chức Policy Enforcement Point, Policy Decision Point, Policy Administration Point và Policy Information Point trong hệ thống như thế nào?
Bạn bảo đảm mọi giao thức và đường truy cập vào tài nguyên đều đi qua enforcement point phù hợp ra sao?
Bạn sử dụng policy engine tập trung trong khi vẫn duy trì khả năng thực thi quyền khi mạng bị gián đoạn như thế nào?
Bạn thiết kế giao thức trao đổi access request và decision giữa ứng dụng với policy engine như thế nào?
Bạn bảo đảm policy engine không trở thành điểm lỗi đơn hoặc nút thắt hiệu năng của hệ thống ra sao?
Bạn chọn giữa đánh giá policy trực tuyến và biên dịch hoặc phân phối policy đến điểm thực thi dựa trên tiêu chí nào?
Bạn thiết kế cache cho quyết định policy và xử lý invalidation khi quyền hoặc thuộc tính thay đổi như thế nào?
Bạn giới hạn thời gian sống của decision cache để cân bằng hiệu năng và tốc độ thu hồi quyền ra sao?
Bạn thiết kế hành vi fail-closed khi policy engine timeout, không khả dụng hoặc trả kết quả không xác định như thế nào?
Bạn xác định những dữ liệu nào cần được gửi vào OPA input và những dữ liệu nào nên nằm trong OPA data như thế nào?
Bạn tổ chức package, rule và dữ liệu trong Rego để policy dễ đọc, kiểm thử và tái sử dụng ra sao?
Bạn dùng test và công cụ kiểm tra policy Rego để phát hiện lỗi logic hoặc trường hợp quyền bị mở rộng ngoài dự kiến như thế nào?
Bạn quản lý OPA policy bundle, phiên bản, chữ ký và quá trình phân phối đến các điểm thực thi ra sao?
Bạn sử dụng partial evaluation hoặc policy decision logging trong OPA khi nào và cần cân nhắc điều gì?
Bạn mô hình hóa principal, action, resource và context trong Cedar để policy phản ánh đúng mô hình miền như thế nào?
Bạn dùng Cedar schema để phát hiện tham chiếu entity, action hoặc thuộc tính không hợp lệ ra sao?
Bạn phân tích ngữ nghĩa permit và forbid trong Cedar khi nhiều policy cùng khớp như thế nào?
Bạn kiểm soát việc tạo và cập nhật entity data để Cedar policy không dựa trên quan hệ hoặc thuộc tính sai lệch ra sao?
Bạn kiểm thử Cedar policy bằng các tình huống cho phép, từ chối và dữ liệu đầu vào không hợp lệ như thế nào?
Bạn phân biệt các thành phần PDP, PEP, PAP và PIP trong kiến trúc XACML và mô tả luồng xử lý request ra sao?
Bạn giải thích Target, Rule và PolicySet trong XACML được dùng để thu hẹp phạm vi áp dụng chính sách như thế nào?
Bạn lựa chọn deny-overrides, permit-overrides, first-applicable hoặc các combining algorithm khác theo yêu cầu bảo mật ra sao?
Bạn xử lý kết quả Indeterminate và NotApplicable trong XACML để tránh vô tình cấp quyền như thế nào?
Bạn dùng obligation và advice để truyền yêu cầu bổ sung cho điểm thực thi mà vẫn giữ rõ ranh giới trách nhiệm ra sao?
Bạn so sánh OPA/Rego, Cedar và XACML theo mô hình dữ liệu, ngữ nghĩa quyết định, khả năng kiểm tra và vận hành như thế nào?
Bạn lựa chọn policy language và engine dựa trên yêu cầu về độ phức tạp, latency, khả năng phân phối và năng lực đội vận hành ra sao?
Bạn tổ chức policy-as-code trong version control với review, phê duyệt và truy vết thay đổi như thế nào?
Bạn triển khai phiên bản policy mới theo canary hoặc shadow evaluation để phát hiện quyết định sai trước khi áp dụng rộng rãi ra sao?
Bạn xây dựng bộ dữ liệu kiểm thử đại diện cho subject, action, resource và context như thế nào?
Bạn thiết kế negative test để phát hiện quyền thừa, truy cập ngang quyền và vượt ranh giới tenant ra sao?
Bạn sử dụng property-based testing hoặc fuzzing để tìm tổ hợp thuộc tính có thể làm policy đưa ra quyết định không mong muốn như thế nào?
Bạn kiểm thử policy khi thuộc tính bị thiếu, sai kiểu, hết hạn hoặc mâu thuẫn giữa nhiều nguồn dữ liệu ra sao?
Bạn đánh giá tác động của thay đổi policy bằng cách so sánh quyết định cũ và mới trên cùng tập request như thế nào?
Bạn thiết kế audit record cho mỗi quyết định policy để có thể giải thích ai được phép hoặc bị từ chối và vì sao ra sao?
Bạn chọn mức chi tiết của policy decision log để hỗ trợ điều tra mà không làm lộ dữ liệu nhạy cảm như thế nào?
Bạn theo dõi tỷ lệ Permit, Deny, Indeterminate và độ trễ đánh giá policy bằng những chỉ số nào?
Bạn phát hiện các mẫu truy cập bất thường hoặc hành vi dò policy mà không tạo ra quá nhiều dữ liệu giám sát như thế nào?
Bạn tổ chức rà soát định kỳ policy không còn được dùng, policy chồng lấn và quyền đặc biệt như thế nào?
Bạn xử lý yêu cầu khẩn cấp cần cấp quyền tạm thời mà vẫn có thời hạn, phê duyệt và hậu kiểm ra sao?
Bạn thiết kế quy trình thu hồi quyền để cập nhật policy, cache, token và các điểm thực thi trong hệ thống phân tán như thế nào?
Bạn bảo vệ policy repository, policy bundle và kênh phân phối khỏi sửa đổi trái phép như thế nào?
Bạn quản lý bí mật và dữ liệu nhạy cảm được policy tham chiếu mà không nhúng trực tiếp credential vào policy ra sao?
Bạn xác định trách nhiệm giữa chủ sở hữu tài nguyên, người viết policy, người phê duyệt và đội vận hành như thế nào?
Bạn xử lý khác biệt giữa policy dự kiến và hành vi thực tế tại enforcement point bằng quy trình điều tra nào?
Bạn thiết kế quy trình rollback khi policy mới gây từ chối nhầm hoặc cấp quyền ngoài ý muốn như thế nào?
Bạn đánh giá một hệ thống PBAC đã đáp ứng least privilege, tính nhất quán, khả năng kiểm toán và vận hành an toàn bằng tiêu chí nào?

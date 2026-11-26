Bạn sẽ phân biệt authentication với authorization trong Spring Security khi thiết kế luồng truy cập một API như thế nào?
Bạn giải thích vai trò của GrantedAuthority trong việc biểu diễn quyền của người dùng như thế nào?
Bạn phân biệt role và authority khi xây dựng mô hình quyền cho một hệ thống nhiều nhóm người dùng ra sao?
Bạn lựa chọn giữa RBAC và chính sách dựa trên thuộc tính, ngữ cảnh khi thiết kế phân quyền theo những tiêu chí nào?
Bạn giải thích ý nghĩa của quy ước tiền tố ROLE_ trong các phép kiểm tra vai trò của Spring Security như thế nào?
Bạn xử lý việc dữ liệu vai trò ở hệ thống định danh không dùng quy ước ROLE_ để tránh cấp nhầm quyền ra sao?
Bạn thiết kế cách chuyển quyền từ hệ thống lưu trữ người dùng thành tập GrantedAuthority khi xác thực như thế nào?
Bạn phân biệt quyền thao tác theo hành động với vai trò theo chức danh để hạn chế bùng nổ số lượng role ra sao?
Bạn sẽ tổ chức một tập authority phục vụ nhiều ứng dụng mà vẫn tránh đưa chi tiết nghiệp vụ vào mọi token như thế nào?
Bạn phân tích ảnh hưởng của việc thay đổi vai trò người dùng trong lúc phiên đăng nhập còn hiệu lực đối với kết quả phân quyền ra sao?
Bạn xác định ranh giới tin cậy của authority lấy từ JWT, session hoặc dịch vụ định danh bên ngoài như thế nào?
Bạn lựa chọn cách ánh xạ scope OAuth2 thành quyền ứng dụng khi resource server nhận access token như thế nào?
Bạn sẽ thiết kế cấu trúc tên authority để phân biệt quyền đọc, sửa, phê duyệt và quản trị của các tài nguyên khác nhau ra sao?
Bạn nhận diện rủi ro khi một tài khoản có nhiều role cộng dồn quyền vượt quá nhu cầu thực tế như thế nào?
Bạn tổ chức quan hệ kế thừa role như thế nào để tránh vô tình mở rộng phạm vi quyền của một nhóm người dùng?
Bạn giải thích nguyên tắc deny by default và cách áp dụng nhất quán tại nhiều lớp của ứng dụng như thế nào?
Bạn so sánh ưu nhược điểm của việc lưu quyền trong database với việc tính quyền động theo dữ liệu và ngữ cảnh ra sao?
Bạn xây dựng chính sách least privilege cho tài khoản người dùng và tài khoản dịch vụ dựa trên những tiêu chí nào?
Bạn sẽ giải thích trách nhiệm của AuthorizationManager trong kiến trúc phân quyền hiện đại của Spring Security như thế nào?
Bạn xác định các dữ liệu đầu vào mà AuthorizationManager cần để ra quyết định truy cập như thế nào?
Bạn lựa chọn cấu hình kiểm soát truy cập HTTP tại SecurityFilterChain so với kiểm soát ở tầng phương thức theo tiêu chí nào?
Bạn tổ chức nhiều SecurityFilterChain cho các nhóm endpoint có cơ chế phân quyền khác nhau như thế nào?
Bạn xác định thứ tự ưu tiên của securityMatcher và requestMatchers để tránh một endpoint bị áp dụng nhầm chính sách ra sao?
Bạn thiết kế quy tắc authorizeHttpRequests cho các endpoint công khai, người dùng đã đăng nhập và chức năng quản trị như thế nào?
Bạn xử lý endpoint không khớp với bất kỳ quy tắc phân quyền cụ thể nào để bảo đảm chính sách mặc định như thế nào?
Bạn sẽ giải thích khác biệt giữa permitAll và việc loại một đường dẫn khỏi chuỗi lọc bảo mật như thế nào?
Bạn phân tích sự khác nhau giữa hasAuthority, hasAnyAuthority, hasRole và hasAnyRole trong chính sách request ra sao?
Bạn kiểm soát quyền riêng cho các HTTP method GET, POST, PUT và DELETE trên cùng đường dẫn tài nguyên như thế nào?
Bạn bảo vệ endpoint có biến đường dẫn chứa ID tài nguyên mà quyền truy cập phụ thuộc chủ sở hữu như thế nào?
Bạn xử lý sự khác nhau giữa URL được khai báo theo mẫu và URL thực tế sau chuẩn hóa đường dẫn để tránh bỏ qua phân quyền ra sao?
Bạn đánh giá tác động của việc bảo vệ endpoint theo đường dẫn khi reverse proxy hoặc servlet path thay đổi như thế nào?
Bạn cấu hình chính sách cho các dispatcher type cần thiết mà vẫn tránh để yêu cầu bất thường vượt qua kiểm soát truy cập ra sao?
Bạn phân biệt tình huống nên trả HTTP 401 với tình huống nên trả HTTP 403 trong cơ chế bảo vệ API như thế nào?
Bạn thiết kế AuthenticationEntryPoint và AccessDeniedHandler để phản hồi lỗi truy cập thống nhất cho client ra sao?
Bạn tránh tiết lộ sự tồn tại của tài nguyên nhạy cảm qua thông báo từ chối truy cập như thế nào?
Bạn sẽ áp dụng kiểm tra quyền khi API có cả thao tác đồng bộ và endpoint khởi tạo tác vụ chạy nền ra sao?
Bạn quản lý quyền truy cập tài liệu API, health endpoint và endpoint quản trị trong các môi trường triển khai khác nhau như thế nào?
Bạn thiết kế chính sách HTTP cho API nhiều phiên bản mà không vô tình cho phép đường dẫn cũ bỏ qua bảo mật ra sao?
Bạn kiểm thử và giải thích hậu quả của một quy tắc requestMatcher quá rộng che khuất các quy tắc hạn chế phía sau như thế nào?
Bạn sẽ quyết định đặt chính sách phân quyền ở gateway hay tại từng ứng dụng Spring Security dựa trên những rủi ro nào?
Bạn xác định những thao tác nào cần được bảo vệ ở tầng service ngay cả khi endpoint HTTP đã có kiểm tra quyền như thế nào?
Bạn giải thích vai trò của @EnableMethodSecurity trong việc kích hoạt phân quyền ở tầng phương thức ra sao?
Bạn sử dụng @PreAuthorize để kiểm tra authority và điều kiện nghiệp vụ trước khi gọi phương thức như thế nào?
Bạn phân tích trường hợp nào cần dùng @PostAuthorize để kiểm tra quyền dựa trên giá trị trả về của phương thức ra sao?
Bạn thiết kế biểu thức phân quyền sử dụng tham số phương thức và thông tin Authentication như thế nào?
Bạn lựa chọn cách tách logic phân quyền phức tạp khỏi biểu thức SpEL để giữ mã dễ kiểm thử ra sao?
Bạn xác định khi nào nên dùng @Secured hoặc @RolesAllowed so với @PreAuthorize trong một codebase có nhiều chuẩn annotation như thế nào?
Bạn thiết kế meta-annotation dùng chung cho các quy tắc quyền phổ biến mà vẫn tránh che giấu điều kiện nghiệp vụ như thế nào?
Bạn giải thích vì sao một lời gọi nội bộ giữa các phương thức trong cùng bean có thể ảnh hưởng đến việc áp dụng method security như thế nào?
Bạn xử lý việc phương thức được gọi từ tác vụ bất đồng bộ không còn cùng security context như luồng HTTP ban đầu ra sao?
Bạn đánh giá hậu quả của việc chỉ đặt phân quyền trên controller mà bỏ qua service được gọi từ scheduler hoặc message listener như thế nào?
Bạn sẽ kiểm soát quyền với phương thức được gọi qua interface hoặc class kế thừa khi các annotation nằm ở nhiều vị trí ra sao?
Bạn phân tích cách các interceptor phân quyền của Spring Security tương tác với proxy và transaction khi gọi phương thức như thế nào?
Bạn chọn thứ tự kiểm tra quyền và mở transaction để tránh truy cập dữ liệu nhạy cảm không cần thiết ra sao?
Bạn thiết kế một AuthorizationManager tùy biến cho method invocation có điều kiện phụ thuộc tham số như thế nào?
Bạn xác định cách trả về quyết định cho phép hoặc từ chối từ chính sách tùy biến mà vẫn dễ quan sát và kiểm thử như thế nào?
Bạn so sánh kiểm tra quyền trước khi đọc dữ liệu với kiểm tra sau khi nhận kết quả về chi phí truy vấn và nguy cơ rò rỉ thông tin ra sao?
Bạn sử dụng @PreFilter hoặc @PostFilter trong những tình huống nào và đánh giá giới hạn hiệu năng của chúng ra sao?
Bạn bảo đảm danh sách đối tượng trả về chỉ chứa dữ liệu được phép xem khi tầng repository có thể trả hàng nghìn bản ghi như thế nào?
Bạn tổ chức việc kiểm tra quyền của một thao tác batch khi người dùng có quyền trên một phần các đối tượng như thế nào?
Bạn xây dựng chính sách áp dụng đồng nhất cho REST API và các luồng gọi service nội bộ trong cùng ứng dụng như thế nào?
Bạn xác định cách kiểm thử method security mà không dựa vào việc controller đã từ chối truy cập từ trước ra sao?
Bạn giải thích vì sao quyền xem một loại tài nguyên không đồng nghĩa với quyền xem mọi bản ghi thuộc loại đó như thế nào?
Bạn thiết kế chính sách object-level authorization để chỉ chủ sở hữu được chỉnh sửa đối tượng của mình ra sao?
Bạn xử lý trường hợp người dùng được xem tài nguyên theo quan hệ nhóm nhưng chỉ người tạo được phép xóa như thế nào?
Bạn phân biệt việc kiểm tra quyền theo ID trong URL với việc xác thực quyền trên đối tượng thực tế đã tải từ database ra sao?
Bạn bảo vệ thao tác thay đổi chủ sở hữu tài nguyên để tránh người dùng tự cấp quyền qua dữ liệu request như thế nào?
Bạn thiết kế bảo vệ chống IDOR khi client tự thay ID tài nguyên trong request ra sao?
Bạn quyết định sử dụng PermissionEvaluator hoặc một dịch vụ chính sách riêng cho kiểm tra quyền trên đối tượng như thế nào?
Bạn giải thích mô hình ACL với principal, sid, đối tượng và permission khi phân quyền ở mức bản ghi ra sao?
Bạn sẽ tổ chức quyền kế thừa giữa tài nguyên cha và con trong ACL để tránh cấp quyền ngoài ý muốn như thế nào?
Bạn lựa chọn lưu ACL trong các bảng riêng hay gắn quyền trực tiếp vào mô hình dữ liệu dựa trên những đánh đổi nào?
Bạn thiết kế quy trình cấp và thu hồi quyền trên một đối tượng có chia sẻ cho nhiều người dùng như thế nào?
Bạn giải quyết tình huống ACL đã thay đổi nhưng cache quyền vẫn lưu quyết định cũ như thế nào?
Bạn đánh giá chi phí kiểm tra ACL riêng cho từng bản ghi khi hiển thị một trang danh sách lớn ra sao?
Bạn kết hợp lọc dữ liệu ở truy vấn repository với kiểm tra quyền trên đối tượng để tránh vừa chậm vừa bỏ sót dữ liệu như thế nào?
Bạn xác định quyền cần thiết cho thao tác xuất báo cáo chứa dữ liệu từ nhiều đối tượng có chính sách truy cập khác nhau ra sao?
Bạn tổ chức phân quyền theo tenant khi một người dùng có thể thuộc nhiều tổ chức với vai trò khác nhau như thế nào?
Bạn lựa chọn nguồn xác định tenant hiện tại từ request, token hoặc ngữ cảnh được xác thực theo nguyên tắc tin cậy nào?
Bạn ngăn người dùng sửa tenantId trong payload để truy cập dữ liệu của tổ chức khác ra sao?
Bạn kiểm chứng quyền vừa theo tenant vừa theo tài nguyên trong một thao tác cập nhật như thế nào?
Bạn đánh giá việc cách ly tenant ở tầng authorization so với tầng truy vấn dữ liệu hoặc database như thế nào?
Bạn sẽ xử lý trường hợp một quản trị viên hỗ trợ khách hàng cần truy cập nhiều tenant nhưng phải có phạm vi và thời hạn cụ thể ra sao?
Bạn thiết kế cơ chế ủy quyền tạm thời cho một người dùng thực hiện thao tác thay mặt người khác như thế nào?
Bạn xác định chính sách khi một tài nguyên được chuyển sang tenant khác nhưng các ACL cũ vẫn còn tồn tại ra sao?
Bạn sẽ kiểm soát truy cập dữ liệu có trạng thái draft, published hoặc archived với các điều kiện quyền khác nhau như thế nào?
Bạn xây dựng chính sách phê duyệt hai cấp để một người không thể tự phê duyệt chính giao dịch mình tạo ra ra sao?
Bạn mô hình hóa điều kiện theo thời gian, địa điểm hoặc mức rủi ro trong một quyết định phân quyền theo ngữ cảnh như thế nào?
Bạn xử lý quy tắc phân quyền có sự kết hợp giữa vai trò, thuộc tính người dùng và trạng thái tài nguyên như thế nào?
Bạn kiểm soát đặc quyền của thao tác hỗ trợ khẩn cấp để vừa đáp ứng vận hành vừa có khả năng kiểm toán ra sao?
Bạn thiết kế cách quản lý và phiên bản hóa chính sách quyền để thay đổi không làm gián đoạn các phiên đăng nhập ra sao?
Bạn xác định cách giải quyết xung đột giữa một quy tắc cho phép tổng quát và một quy tắc từ chối theo ngữ cảnh như thế nào?
Bạn xây dựng bộ kiểm tra chính sách để phát hiện một tập quyền vô tình cấp quyền truy cập vượt mục tiêu ra sao?
Bạn sẽ giới hạn quyền quản trị của tài khoản dịch vụ sử dụng client credentials khi gọi API giữa các hệ thống như thế nào?
Bạn quyết định nên tính quyết định phân quyền tại ứng dụng hay gọi một dịch vụ chính sách tập trung dựa trên độ trễ và khả dụng ra sao?
Bạn thiết kế hành vi fail closed khi dịch vụ phân quyền bên ngoài không sẵn sàng như thế nào?
Bạn cân nhắc dùng cache cho kết quả phân quyền của AuthorizationManager dựa trên những yếu tố nào về tính đúng đắn và độ mới dữ liệu?
Bạn ngăn cache phân quyền dùng lại kết quả giữa các user hoặc tenant do xây dựng cache key không đầy đủ như thế nào?
Bạn giảm số truy vấn database khi kiểm tra quyền trên danh sách tài nguyên lớn mà không làm suy yếu bảo mật ra sao?
Bạn sẽ ghi nhận lý do từ chối quyền trong log để hỗ trợ điều tra nhưng không tiết lộ dữ liệu nhạy cảm như thế nào?
Bạn tổ chức audit trail cho hành động cấp quyền, thu hồi quyền và thao tác bị từ chối như thế nào?
Bạn lựa chọn chỉ số và ngưỡng cảnh báo nào để phát hiện sự gia tăng bất thường của các yêu cầu bị từ chối truy cập?
Bạn áp dụng @WithMockUser và @WithAnonymousUser để kiểm thử các trường hợp method security như thế nào?
Bạn xây dựng kiểm thử MockMvc cho một endpoint yêu cầu authority cụ thể và xác minh cả trường hợp được phép lẫn bị từ chối ra sao?
Bạn tạo security context kiểm thử có các authority tùy biến và thông tin tenant để mô phỏng người dùng thực tế như thế nào?
Bạn sử dụng JWT giả lập trong kiểm thử Spring Security để kiểm chứng ánh xạ scope thành quyền truy cập như thế nào?
Bạn kiểm thử kết quả 401 và 403 cho một endpoint với các trạng thái xác thực khác nhau ra sao?
Bạn xây dựng test matrix bao phủ vai trò, hành động và trạng thái tài nguyên mà vẫn kiểm soát số lượng ca kiểm thử như thế nào?
Bạn kiểm tra các trường hợp thiếu quyền, sai tenant, không phải chủ sở hữu và tài nguyên không tồn tại mà không làm lộ thông tin như thế nào?
Bạn thiết kế test chứng minh user chỉ có quyền đọc không thể gọi API sửa hoặc xóa qua đường dẫn khác như thế nào?
Bạn kiểm thử phương thức được gọi từ luồng nội bộ để chắc chắn cơ chế phân quyền vẫn được thực thi ra sao?
Bạn tạo tình huống thay đổi ACL trong lúc người dùng đang thao tác để phát hiện lỗi thu hồi quyền chưa có hiệu lực như thế nào?
Bạn kiểm thử endpoint trả về danh sách để phát hiện bản ghi của tenant khác bị lẫn trong kết quả như thế nào?
Bạn kiểm chứng một thao tác batch chứa đối tượng hợp lệ lẫn không hợp lệ không tạo ra cập nhật trái phép như thế nào?
Bạn đánh giá sự phù hợp của integration test dùng cơ sở dữ liệu thật đối với các truy vấn lọc theo quyền như thế nào?
Bạn xây dựng quality gate trong CI để một thay đổi policy không làm hồi quy các kịch bản truy cập bị từ chối ra sao?
Một API đơn hàng chỉ kiểm tra hasRole('USER') nên người dùng xem được đơn hàng của người khác, bạn sẽ xác định lỗ hổng và thiết kế lại các lớp bảo vệ như thế nào?
Một endpoint quản trị bị truy cập qua biến thể đường dẫn không khớp requestMatcher dự kiến, bạn sẽ điều tra và khắc phục cấu hình như thế nào?
Sau khi người dùng bị thu hồi quyền, JWT cũ vẫn cho phép gọi một API nhạy cảm, bạn sẽ đánh giá cách giảm thời gian quyền cũ còn hiệu lực ra sao?
Một tác vụ chạy nền gọi được service mà request HTTP bị chặn, bạn sẽ kiểm tra và sửa phạm vi method security như thế nào?
Một người dùng có hai role thuộc hai tenant khác nhau và truy cập sai tổ chức, bạn sẽ truy tìm lỗi xây dựng authority và ngữ cảnh tenant ra sao?
Sau khi thêm @PreAuthorize, một lời gọi nội bộ trong cùng bean vẫn không bị từ chối, bạn sẽ giải thích nguyên nhân và thay đổi thiết kế như thế nào?
Khi số lượng đối tượng hiển thị lớn khiến kiểm tra PermissionEvaluator bị chậm, bạn sẽ tìm điểm nghẽn và tối ưu mà vẫn giữ đúng chính sách ra sao?
Một thay đổi chính sách cho phép nhân viên hỗ trợ sửa dữ liệu nhạy cảm ngoài thời gian được cấp quyền, bạn sẽ thiết kế kiểm thử hồi quy và giám sát như thế nào?

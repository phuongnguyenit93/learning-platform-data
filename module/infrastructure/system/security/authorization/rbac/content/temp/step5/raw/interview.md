Bạn giải thích mô hình RBAC kiểm soát quyền truy cập thông qua quan hệ giữa người dùng, vai trò và quyền như thế nào?
Bạn phân biệt user, role, permission và session trong mô hình RBAC ra sao?
Bạn mô hình hóa quan hệ nhiều-nhiều giữa người dùng và vai trò, cũng như giữa vai trò và quyền như thế nào?
Bạn xác định một permission cần mô tả tài nguyên, hành động và phạm vi áp dụng ở mức chi tiết nào?
Bạn phân biệt quyền xem, tạo, sửa, xóa, phê duyệt và quản trị đối với cùng một loại tài nguyên như thế nào?
Bạn thiết kế role theo chức năng công việc và trách nhiệm thực tế thay vì sao chép nguyên trạng sơ đồ tổ chức như thế nào?
Bạn phân biệt business role với technical role khi xây dựng danh mục vai trò như thế nào?
Bạn xác định ranh giới giữa quyền mặc định của một vai trò và quyền đặc biệt cần cấp riêng như thế nào?
Bạn đặt tên, mô tả và phân loại role để quản trị viên hiểu rõ mục đích cùng phạm vi của từng vai trò ra sao?
Bạn xác định một role nên chứa tập quyền ổn định nào và khi nào cần tách thành nhiều role nhỏ hơn như thế nào?
Bạn lựa chọn cách kết hợp nhiều role cho một người dùng để phản ánh nhiệm vụ mà không cấp dư quyền ra sao?
Bạn phân biệt role assignment với role activation trong hệ thống hỗ trợ kích hoạt vai trò theo phiên như thế nào?
Bạn thiết kế session role activation để người dùng chỉ sử dụng tập quyền cần thiết trong từng phiên làm việc ra sao?
Bạn xác định cách giới hạn thời gian và ngữ cảnh sử dụng của một role đặc quyền như thế nào?
Bạn phân biệt role hierarchy với việc gán trực tiếp cùng một tập quyền cho nhiều vai trò như thế nào?
Bạn thiết kế role hierarchy để vai trò cấp cao kế thừa quyền của vai trò cấp thấp mà không tạo vòng lặp ra sao?
Bạn xác định cách xử lý xung đột khi quyền được kế thừa từ nhiều nhánh role hierarchy khác nhau như thế nào?
Bạn đánh giá khi nào nên dùng role composition và khi nào cần một role độc lập để tránh kế thừa ngoài ý muốn ra sao?
Bạn kiểm soát thay đổi role hierarchy để một lần sửa role cha không vô tình mở rộng quyền cho quá nhiều người như thế nào?
Bạn phân biệt RBAC với DAC, MAC và ABAC về nguồn quyết định quyền truy cập ra sao?
Bạn xác định giới hạn của RBAC thuần túy khi quyết định còn phụ thuộc vào chủ sở hữu tài nguyên, tenant, địa điểm hoặc thời gian như thế nào?
Bạn kết hợp RBAC với điều kiện theo thuộc tính hoặc ngữ cảnh mà vẫn giữ được mô hình vai trò dễ quản trị như thế nào?
Bạn thiết kế role có phạm vi toàn hệ thống, theo tổ chức, theo dự án hoặc theo tenant như thế nào?
Bạn ngăn một role có quyền trong một đơn vị tổ chức bị sử dụng ngoài phạm vi đơn vị đó ra sao?
Bạn phân biệt quyền quản trị danh mục role với quyền thực hiện nghiệp vụ được cấp bởi role như thế nào?
Bạn thiết kế least privilege để người dùng chỉ nhận các vai trò và quyền cần thiết cho nhiệm vụ hiện tại ra sao?
Bạn lựa chọn role mặc định khi tạo tài khoản mới để tránh cấp quyền vượt quá nhu cầu như thế nào?
Bạn kiểm soát tài khoản quản trị và vai trò đặc quyền bằng nguyên tắc phân tách quyền quản trị với quyền sử dụng hằng ngày ra sao?
Bạn thiết kế cơ chế break-glass access cho tình huống khẩn cấp và kiểm soát việc sử dụng sau sự kiện như thế nào?
Bạn phân biệt Static Separation of Duties và Dynamic Separation of Duties trong việc ngăn xung đột vai trò ra sao?
Bạn xác định các cặp role không được phép cùng cấp cho một người dùng theo quy tắc phân tách nhiệm vụ như thế nào?
Bạn thiết kế ràng buộc số lượng hoặc cardinality để giới hạn số người giữ một vai trò nhạy cảm như thế nào?
Bạn ngăn một người vừa tạo vừa phê duyệt cùng giao dịch bằng cách kết hợp role constraint và kiểm tra quan hệ nghiệp vụ ra sao?
Bạn xử lý trường hợp một tổ chức nhỏ không đủ nhân sự để đáp ứng đầy đủ phân tách nhiệm vụ như thế nào?
Bạn thiết kế ngoại lệ SoD có thời hạn, lý do, người phê duyệt và kiểm soát bù trừ ra sao?
Bạn phát hiện toxic combination khi một người tích lũy nhiều vai trò riêng lẻ hợp lệ nhưng tổng hợp lại tạo quyền nguy hiểm như thế nào?
Bạn xây dựng quy trình yêu cầu cấp role có lý do nghiệp vụ, người bảo trợ và thời hạn sử dụng như thế nào?
Bạn xác định các cấp phê duyệt cần thiết khi yêu cầu một role có quyền truy cập dữ liệu nhạy cảm hoặc thao tác tài chính ra sao?
Bạn thiết kế quy trình cấp quyền tạm thời và tự động thu hồi khi hết thời hạn như thế nào?
Bạn phân biệt cấp quyền theo người dùng trực tiếp với cấp quyền thông qua nhóm hoặc đơn vị tổ chức ra sao?
Bạn quản lý role assignment khi người dùng chuyển phòng ban, đổi chức năng hoặc kiêm nhiệm nhiều vị trí như thế nào?
Bạn xác định những quyền cần thu hồi ngay khi nhân viên nghỉ việc hoặc hợp đồng đối tác kết thúc ra sao?
Bạn đồng bộ thay đổi nhân sự từ hệ thống nguồn để vòng đời role assignment luôn phản ánh trạng thái hiện tại như thế nào?
Bạn xử lý tài khoản bị vô hiệu hóa nhưng vẫn còn role assignment hoặc session đang hoạt động ra sao?
Bạn xác định cách thu hồi quyền nhanh trên nhiều hệ thống khi một role hoặc tài khoản bị phát hiện cấp sai như thế nào?
Bạn kiểm soát độ trễ của cache hoặc bản sao quyền để thay đổi role không tiếp tục có hiệu lực ngoài dự kiến ra sao?
Bạn phát hiện tài khoản mồ côi, role không còn chủ sở hữu và quyền không còn gắn với nhiệm vụ nào như thế nào?
Bạn thiết kế quản lý role cho tài khoản dịch vụ và danh tính máy để tránh dùng chung quyền rộng giữa nhiều workload ra sao?
Bạn phân biệt quyền của người dùng tương tác với quyền của service account, bot và workload identity như thế nào?
Bạn ánh xạ nhóm từ hệ thống danh tính hoặc nhà cung cấp liên kết sang role nội bộ mà không tin mù quáng tên nhóm bên ngoài như thế nào?
Bạn xử lý nested group và group membership thay đổi khi đồng bộ role giữa nhiều directory như thế nào?
Bạn xác định nguồn nào là authoritative cho user, group, role và permission trong một tổ chức có nhiều hệ thống danh tính ra sao?
Bạn thiết kế role mapping giữa nhiều ứng dụng hoặc nhiều miền tổ chức mà vẫn giữ được phạm vi quyền riêng biệt như thế nào?
Bạn quản lý role assignment khi một người có nhiều danh tính hoặc nhiều tài khoản trong các hệ thống khác nhau ra sao?
Bạn đánh giá nguyên nhân role explosion khi số lượng vai trò tăng theo từng phòng ban, địa điểm, dự án và ngoại lệ như thế nào?
Bạn sử dụng role mining để tìm các nhóm quyền thường xuất hiện cùng nhau và đề xuất role phù hợp ra sao?
Bạn phân tích dữ liệu sử dụng quyền để hợp nhất role trùng lặp hoặc loại bỏ permission không còn cần thiết như thế nào?
Bạn xác định role nào không còn được sử dụng hoặc có số người dùng quá ít để tiếp tục duy trì như thế nào?
Bạn cân bằng giữa role theo chức danh, role theo nhiệm vụ và role theo ứng dụng để giảm số lượng vai trò mà vẫn rõ trách nhiệm ra sao?
Bạn xác định khi nào một tổ hợp role riêng lẻ tốt hơn việc tạo role mới cho từng biến thể người dùng như thế nào?
Bạn quản lý role theo phạm vi tổ chức lớn có nhiều cấp kế thừa mà không làm quyền trở nên khó dự đoán ra sao?
Bạn thiết kế ủy quyền quản trị role cho từng đơn vị nhưng ngăn quản trị viên đơn vị tự cấp quyền vượt phạm vi được giao như thế nào?
Bạn xác định cách ủy quyền phê duyệt yêu cầu truy cập khi người phê duyệt vắng mặt mà vẫn bảo đảm SoD ra sao?
Bạn kiểm soát thay đổi permission trong một role đang được nhiều hệ thống và nhiều nhóm người dùng sử dụng như thế nào?
Bạn thiết kế versioning và quy trình phê duyệt thay đổi role để có thể đánh giá tác động trước khi áp dụng ra sao?
Bạn đánh giá ảnh hưởng của việc xóa role hoặc permission đang được gán cho người dùng và ứng dụng như thế nào?
Bạn xây dựng báo cáo access review để chủ sở hữu dữ liệu và quản lý xác nhận quyền của từng người dùng theo chu kỳ ra sao?
Bạn lựa chọn tần suất recertification dựa trên mức độ nhạy cảm và rủi ro của vai trò như thế nào?
Bạn thiết kế quy trình xử lý khi quản lý không phản hồi yêu cầu rà soát quyền đúng hạn như thế nào?
Bạn phân biệt quyền được cấp theo chính sách với quyền thực tế đang có hiệu lực trên từng hệ thống ra sao?
Bạn kiểm tra permission drift khi cấu hình trong hệ thống đích khác với danh mục role được phê duyệt như thế nào?
Bạn ghi nhận audit trail cho việc tạo role, sửa permission, cấp quyền, thu hồi và sử dụng quyền đặc quyền ra sao?
Bạn bảo vệ log kiểm toán để người quản trị role không thể tự sửa hoặc xóa dấu vết thay đổi quyền như thế nào?
Bạn xác định các trường thông tin cần lưu để truy vết ai cấp quyền, ai phê duyệt, lý do và thời điểm hiệu lực ra sao?
Bạn phát hiện hành vi sử dụng role khác thường so với nhiệm vụ hoặc lịch sử truy cập của người dùng như thế nào?
Bạn thiết kế cảnh báo khi một role nhạy cảm được cấp hàng loạt, thay đổi permission đột ngột hoặc được sử dụng ngoài giờ ra sao?
Bạn xác định cách đo hiệu quả RBAC qua số quyền dư thừa, toxic combination, thời gian thu hồi và kết quả access review như thế nào?
Bạn kiểm thử RBAC bằng ma trận user-role-permission để xác minh cả trường hợp được phép và bị từ chối ra sao?
Bạn thiết kế test cho role hierarchy, inheritance, scope và SoD để phát hiện quyền vô tình được kế thừa như thế nào?
Bạn kiểm thử thay đổi role assignment đồng thời với request đang chạy để xác minh thời điểm quyền mới có hiệu lực ra sao?
Bạn xây dựng quy trình điều tra khi người dùng truy cập được chức năng ngoài dự kiến hoặc bị từ chối dù đã có role phù hợp như thế nào?
Bạn xác định bằng chứng cần có để chứng minh mô hình RBAC đáp ứng least privilege, separation of duties, auditability và khả năng quản trị lâu dài như thế nào?

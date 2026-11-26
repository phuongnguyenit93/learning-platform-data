Một nhân viên mới được đồng bộ từ hệ thống nhân sự và tự động nhận role theo tên phòng ban, nhưng role của phòng ban đó bao gồm quyền xuất dữ liệu nhạy cảm mà vị trí công việc mới không cần.
Một chuyên viên vận hành được gán đồng thời role hỗ trợ khách hàng và role quản trị dữ liệu, khiến tổng hợp quyền cho phép họ vừa xem thông tin định danh vừa thay đổi trạng thái hồ sơ.
Doanh nghiệp thiết kế role trực tiếp theo từng chức danh trong sơ đồ tổ chức, nên mỗi lần đổi tên chức danh hoặc tái cơ cấu lại phải tạo hàng loạt role gần như giống nhau.
Một role `Project Viewer` được cấp quyền đọc mọi dự án trên hệ thống dù người dùng chỉ phụ trách một dự án cụ thể, dẫn đến truy cập vượt phạm vi công việc.
Role `Regional Manager` kế thừa role `Manager`, nhưng role cha vừa được bổ sung quyền xem lương toàn công ty khiến tất cả quản lý khu vực nhận quyền nhạy cảm ngoài dự kiến.
Hai role trong hệ thống phân cấp kế thừa lẫn nhau qua nhiều nhánh, làm tập quyền hiệu lực khó dự đoán và công cụ quản trị không phát hiện được vòng lặp kế thừa.
Một nhân viên có thể tạo yêu cầu thanh toán và tự phê duyệt yêu cầu đó vì hai quyền nằm trong hai role riêng biệt được cấp hợp lệ cho cùng tài khoản.
Hệ thống cho phép người dùng kích hoạt role `Requester` và `Approver` trong cùng một session, dù chính sách Dynamic Separation of Duties yêu cầu hai vai trò này không được hoạt động đồng thời.
Một người dùng có role `Tenant Administrator` tại công ty con A nhưng giao diện quản trị cho phép đổi tenant trên URL và xem người dùng của công ty con B.
Quản trị viên chi nhánh được phép tạo role cho đơn vị mình, nhưng có thể gán role mới quyền quản trị toàn tổ chức vì phạm vi ủy quyền không được ràng buộc theo organizational unit.
Role `Document Editor` cho phép sửa mọi tài liệu, trong khi quyết định truy cập thực tế còn cần xét chủ sở hữu tài liệu và mức phân loại bảo mật của từng hồ sơ.
Một role đặc quyền được phê duyệt trong 24 giờ nhưng job thu hồi bị lỗi, khiến assignment tiếp tục tồn tại nhiều tuần sau khi nhu cầu xử lý sự cố kết thúc.
Nhân viên chỉ cần quyền quản trị trong cửa sổ bảo trì nhưng role đặc quyền được gán cố định, khiến quyền có hiệu lực cả ngoài thời gian được phép.
Tài khoản break-glass được dùng khi hệ thống cấp quyền thông thường gặp sự cố, nhưng không có quy trình ghi lý do, thông báo người giám sát và rà soát các thao tác sau sự kiện.
Một tài khoản dịch vụ dùng chung cho nhiều tiến trình tích hợp được gán role `System Operator`, khiến audit log không thể phân biệt workload nào đã thực hiện thay đổi dữ liệu.
Nhiều workload tự động dùng chung một service identity và role có quyền đọc secret của toàn bộ môi trường, làm một workload bị xâm nhập có thể truy cập tài nguyên không liên quan.
Nhóm IAM ánh xạ trực tiếp mọi external group có tên chứa từ `admin` thành role quản trị nội bộ mà không xác minh issuer, nguồn tạo group hoặc chủ sở hữu.
Thành viên của nested group trong directory được thêm vào role nội bộ chậm hơn dự kiến, khiến nhân viên đã bị loại khỏi nhóm vẫn giữ quyền truy cập trong một khoảng thời gian.
Doanh nghiệp có nhiều nguồn danh tính cùng tạo tài khoản cho một người, dẫn đến các role được gán cho một identity nhưng không tự động thu hồi trên identity trùng lặp.
Tài khoản nhà thầu hết hạn hợp đồng trong hệ thống nhân sự nhưng vẫn còn role assignment trong hệ thống quản lý tài liệu và cổng vận hành.
Nhân viên chuyển từ bộ phận thanh toán sang kiểm toán nhưng các role cũ không bị thu hồi, khiến họ tiếp tục giữ quyền tạo giao dịch cùng với quyền kiểm tra giao dịch.
Tài khoản bị vô hiệu hóa nhưng các phiên đăng nhập và token đã phát hành vẫn được chấp nhận trong một số hệ thống đích, tạo cửa sổ truy cập sau khi nghỉ việc.
Role assignment đã bị thu hồi tại hệ thống trung tâm nhưng cache quyền ở một ứng dụng vệ tinh chưa hết hạn, khiến người dùng vẫn thực hiện được thao tác bị thu hồi.
Người dùng nhận role qua nhiều nhóm lồng nhau và qua assignment trực tiếp, nhưng báo cáo access review chỉ hiển thị assignment trực tiếp nên bỏ sót quyền hiệu lực.
Số lượng role tăng nhanh vì mỗi dự án, địa điểm, cấp bậc và ngoại lệ đều tạo một role mới, khiến quản trị viên không còn xác định được role chuẩn nào nên được tái sử dụng.
Phân tích role mining phát hiện nhiều role có tập permission gần như giống nhau nhưng tên gọi khác nhau theo từng phòng ban, trong khi chưa có chủ sở hữu chịu trách nhiệm hợp nhất.
Một role ít người dùng vẫn giữ quyền xóa dữ liệu production, nhưng không có thống kê usage hoặc access review để xác định role còn cần thiết hay không.
Role được tạo cho một chiến dịch ngắn hạn đã kết thúc từ lâu nhưng vẫn có người được gán và không có owner để xác nhận việc tiếp tục duy trì.
Yêu cầu cấp role `Finance Approver` chỉ ghi lý do chung chung và không nêu hệ thống, phạm vi dữ liệu, người bảo trợ hoặc thời hạn cần quyền.
Quyền truy cập tạm thời được cấp qua email khẩn cấp và không có ngày hết hạn trong hệ thống IAM, khiến người phê duyệt không thể theo dõi lúc cần thu hồi.
Quản lý xác nhận toàn bộ role của nhân viên trong đợt recertification mà không xem permission thực tế, mức nhạy cảm hoặc hoạt động sử dụng gần đây.
Một tổ chức nhỏ không đủ nhân sự để tách người tạo nhà cung cấp và người phê duyệt thanh toán, nên ngoại lệ SoD được áp dụng lâu dài mà không có kiểm soát bù trừ.
Role administrator có quyền sửa permission của role và tự gán role đó cho chính mình, tạo đường tự nâng quyền mà không cần phê duyệt độc lập.
Quản trị viên địa phương được ủy quyền cấp role cho nhân viên trong đơn vị, nhưng giao diện cho phép chọn user thuộc đơn vị khác do thiếu kiểm tra phạm vi ở phía máy chủ.
Người phê duyệt yêu cầu truy cập đang nghỉ phép và quyền ủy quyền phê duyệt được chuyển cho người thay thế cũng đang giữ role xung đột với người yêu cầu.
Một permission được thêm vào role `Operations` để xử lý sự cố của một hệ thống, nhưng role này đang được dùng ở nhiều ứng dụng khác nên thay đổi làm mở rộng quyền trên diện rộng.
Đội IAM triển khai phiên bản role mới trực tiếp lên production mà không mô phỏng user-role-permission assignments hiện tại, khiến hàng trăm người dùng nhận thêm quyền không dự kiến.
Quản trị viên xóa một role đã ngừng sử dụng nhưng các ứng dụng đích vẫn giữ entitlement được provision trước đó và không có đối soát để phát hiện quyền mồ côi.
Người có quyền quản trị RBAC cũng có thể chỉnh sửa hoặc xóa audit log ghi lại việc cấp role, khiến bằng chứng kiểm toán không còn độc lập.
Một tài khoản bình thường đột nhiên kích hoạt role đặc quyền vào ban đêm và truy cập nhiều tài nguyên ngoài khu vực phụ trách nhưng hệ thống không có cảnh báo theo hành vi sử dụng role.
Role được gán đúng theo ma trận phê duyệt nhưng một hệ thống đích diễn giải permission `manage` rộng hơn chính sách trung tâm, dẫn đến permission drift giữa các nền tảng.
Kiểm thử RBAC chỉ xác nhận người có role hợp lệ truy cập thành công mà không kiểm tra các trường hợp thiếu role, sai tenant, role xung đột hoặc assignment đã hết hạn.
Yêu cầu truy cập đang được xử lý đồng thời lúc quản trị viên thu hồi role, khiến một request mới vẫn được chấp nhận bằng trạng thái quyền cũ.
Một cuộc rà soát phát hiện user không còn nhiệm vụ nhưng vẫn có quyền thông qua role kế thừa từ group dự án, trong khi báo cáo chỉ liệt kê các role được cấp trực tiếp.
Doanh nghiệp muốn cấp role chuẩn giữa nhiều hệ thống nhưng tên role giống nhau lại đại diện cho tập quyền và phạm vi tài nguyên khác nhau ở từng nền tảng.

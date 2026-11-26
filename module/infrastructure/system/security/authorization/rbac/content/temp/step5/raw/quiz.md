Một tổ chức muốn quản lý quyền của nhân viên qua các chức năng công việc. Mô hình RBAC cơ bản nên biểu diễn quan hệ nào?
A. Gán người dùng vào vai trò và gán quyền cho vai trò.
B. Gán quyền trực tiếp cho từng người dùng và dùng vai trò để đặt tên nhóm.
C. Gán tài nguyên vào người dùng và dùng quyền để mô tả các nhóm chức năng.
D. Gán vai trò vào từng request và lưu quyền riêng trong phiên làm việc.
Đáp án đúng: A

Một ứng dụng nội bộ có nhiều nhân viên cùng thực hiện nhiệm vụ kế toán. Cách quản lý quyền nào giảm việc cấp phát lặp lại?
A. Cấp mọi quyền cho nhóm kế toán rồi dựa vào hướng dẫn sử dụng nội bộ.
B. Lưu quyền theo từng phiên đăng nhập và tạo lại khi nhân viên đổi máy.
C. Gán quyền cho vai trò rồi gán nhân viên vào vai trò.
D. Sao chép danh sách quyền vào từng tài khoản khi nhân viên được tuyển.
Đáp án đúng: C

Một người dùng được gán đồng thời hai vai trò hợp lệ trong RBAC cơ bản. Quyền hiệu lực thông thường được xác định ra sao?
A. Là quyền rộng nhất trong hệ thống, miễn người dùng có ít nhất một vai trò.
B. Là giao của các quyền để chỉ giữ phần giống nhau giữa hai vai trò.
C. Là quyền của vai trò được tạo gần nhất, còn vai trò cũ bị bỏ qua.
D. Hợp các quyền từ vai trò đang hiệu lực của người dùng.
Đáp án đúng: D

Trong phân cấp vai trò, vai trò Quản lý kế thừa vai trò Nhân viên. Điều này có nghĩa gì?
A. Nhân viên tự động nhận mọi quyền được cấp riêng cho Quản lý.
B. Hai vai trò đổi quyền cho nhau mỗi khi người dùng đăng nhập.
C. Quản lý chỉ nhận quyền Nhân viên khi được gán cả hai vai trò riêng.
D. Quản lý nhận quyền Nhân viên và có thể nhận thêm quyền riêng.
Đáp án đúng: D

Một mô hình có vai trò Quản lý cấp cao kế thừa Quản lý khu vực, còn Quản lý khu vực kế thừa Nhân viên. Cách tính quyền nào đúng?
A. Tính quyền kế thừa theo quan hệ bắc cầu của role hierarchy.
B. Người dùng phải được gán thủ công tất cả vai trò ở mọi cấp thấp hơn.
C. Quyền của vai trò cấp thấp thay thế quyền từ vai trò cấp cao hơn.
D. Chỉ quyền từ vai trò cha trực tiếp mới được tính vào quyền hiệu lực.
Đáp án đúng: A

Một nhân viên không được phép vừa tạo nhà cung cấp vừa phê duyệt thanh toán. Ràng buộc nào ngăn việc cấp đồng thời hai vai trò xung đột?
A. Role hierarchy cho phép vai trò phê duyệt kế thừa vai trò tạo dữ liệu.
B. Static separation of duties kiểm tra xung đột ngay lúc gán vai trò.
C. Dynamic separation of duties chỉ kiểm tra khi người dùng chạy báo cáo.
D. Cardinality constraint giới hạn tổng số quyền trong một vai trò.
Đáp án đúng: B

Một người dùng có hai vai trò riêng biệt nhưng không được kích hoạt chúng trong cùng một phiên nghiệp vụ. Cơ chế nào phù hợp?
A. Static separation of duties cấm người dùng được gán cả hai vai trò.
B. Dynamic separation of duties kiểm tra tổ hợp vai trò đang kích hoạt.
C. Role hierarchy tự động loại bỏ vai trò ít quyền hơn khi đăng nhập.
D. Permission review định kỳ phát hiện người dùng có nhiều vai trò cùng lúc.
Đáp án đúng: B

Một vai trò nhạy cảm chỉ được phép gán cho tối đa năm người tại cùng thời điểm. Đây là loại ràng buộc nào?
A. Session constraint giới hạn thời lượng phiên khi kích hoạt vai trò.
B. Hierarchy constraint giới hạn số cấp kế thừa giữa các vai trò.
C. Prerequisite constraint yêu cầu người dùng có vai trò nền trước đó.
D. Giới hạn số người dùng được gán vào một vai trò.
Đáp án đúng: D

Một vai trò Kiểm toán chỉ được gán cho người đã có vai trò Nhân viên chính thức. Ràng buộc này được mô hình hóa thế nào?
A. Role hierarchy khiến mọi người có vai trò Nhân viên tự nhận quyền Kiểm toán.
B. Dynamic separation of duties yêu cầu hai vai trò được bật cùng phiên.
C. Yêu cầu có vai trò điều kiện trước khi gán vai trò đích.
D. Cardinality constraint giới hạn số người được cấp vai trò Kiểm toán.
Đáp án đúng: C

Một nền tảng đa tenant có vai trò Analyst ở mỗi khách hàng, nhưng quyền đọc chỉ áp dụng trong tenant tương ứng. Thiết kế nào giữ đúng ranh giới?
A. Dùng một vai trò Analyst toàn cục và tin tenant ID do client gửi lên.
B. Tạo một tài khoản riêng cho mỗi bản ghi dữ liệu của từng khách hàng.
C. Ràng buộc tenant và resource scope trong quyết định truy cập.
D. Ẩn dữ liệu tenant khác ở giao diện nhưng dùng chung quyền đọc backend.
Đáp án đúng: C

Một tổ chức có hàng nghìn vai trò gần giống nhau do tạo riêng theo từng nhân viên. Cách xử lý nào giảm role explosion bền vững?
A. Hợp nhất vai trò tương đương theo chức năng và scope.
B. Gộp mọi vai trò thành một vai trò lớn rồi phân biệt bằng tài liệu hướng dẫn.
C. Chuyển tất cả quyền sang tài khoản cá nhân và ngừng sử dụng vai trò.
D. Tiếp tục tạo vai trò riêng nhưng rút ngắn tên để dễ tìm trong danh sách.
Đáp án đúng: A

Nhóm IAM dùng access log để đề xuất vai trò mới. Bước nào cần thiết trước khi triển khai các role mining result?
A. Tạo một vai trò cho mỗi tổ hợp quyền xuất hiện trong log.
B. Đối chiếu quyền với nhiệm vụ và least privilege.
C. Tự động cấp mọi quyền từng được sử dụng trong log cho cùng một nhóm.
D. Loại bỏ quyền ít được dùng mà không hỏi chủ sở hữu nghiệp vụ.
Đáp án đúng: B

Một nhân viên chuyển từ bộ phận mua hàng sang tài chính. Quy trình vòng đời quyền nào giảm permission creep?
A. Thu hồi assignment cũ rồi cấp vai trò mới theo nhiệm vụ và phê duyệt.
B. Giữ vai trò cũ để tránh gián đoạn rồi cộng thêm vai trò tài chính.
C. Chỉ đổi thuộc tính phòng ban trong hồ sơ và không thay đổi assignment.
D. Chuyển toàn bộ quyền cũ sang người thay thế trước khi cập nhật nhân sự.
Đáp án đúng: A

Một vai trò được thiết kế cho nhóm hỗ trợ nhưng chỉ một số thành viên cần xóa hồ sơ. Cách thiết kế nào phù hợp least privilege?
A. Tách quyền xóa thành quyền bổ sung, chỉ cấp khi được duyệt.
B. Cho mọi người quyền quản trị rồi yêu cầu họ tự giới hạn thao tác.
C. Ẩn nút xóa với phần lớn người dùng nhưng giữ quyền ở backend.
D. Cấp quyền xóa cho toàn bộ vai trò hỗ trợ để tránh quy trình ngoại lệ.
Đáp án đúng: A

Một API nhận request không có role assignment hợp lệ cho thao tác xóa. Hành vi mặc định nào an toàn?
A. Tự động gán vai trò gần nhất nếu request đến từ mạng nội bộ.
B. Từ chối thao tác nếu không có quyền được cấp rõ ràng.
C. Cho phép thao tác nếu người dùng đã xác thực thành công.
D. Cho phép thao tác khi giao diện không hiển thị nút xóa.
Đáp án đúng: B

Một tổ chức rà soát quyền hằng quý và phát hiện nhiều vai trò không còn phù hợp với nhiệm vụ hiện tại. Cách xử lý nào đúng?
A. Giữ nguyên mọi assignment để tránh thay đổi ảnh hưởng hoạt động.
B. Xóa toàn bộ vai trò cũ mà không kiểm tra hệ thống đang phụ thuộc.
C. Yêu cầu owner xác nhận và thu hồi assignment thừa.
D. Chỉ kiểm tra ngày tạo vai trò và giữ lại vai trò đã tồn tại lâu năm.
Đáp án đúng: C

Một quản lý được phép cấp vai trò cho nhân viên trong nhóm của mình nhưng không được tự cấp quyền quản trị toàn tổ chức. Cơ chế nào phù hợp?
A. Static separation of duties cho phép quản lý tự phê duyệt mọi yêu cầu.
B. Một vai trò chung có quyền gán role ở mọi tenant và mọi môi trường.
C. Delegated administration giới hạn đối tượng, vai trò và phạm vi quản lý.
D. Role hierarchy cho quản lý kế thừa mọi quyền của quản trị viên toàn cục.
Đáp án đúng: C

Một quy trình thanh toán yêu cầu người tạo lệnh không được là người phê duyệt cùng giao dịch. Kiểm soát nào trực tiếp thực thi nguyên tắc này?
A. Access review định kỳ thay thế kiểm tra xung đột ở thời điểm giao dịch.
B. Ràng buộc SoD kiểm tra người tạo và người phê duyệt của giao dịch.
C. Cardinality constraint giới hạn số người dùng có vai trò thanh toán.
D. Role hierarchy cho phép người phê duyệt kế thừa quyền người tạo lệnh.
Đáp án đúng: B

Một người dùng có nhiều vai trò nhưng chỉ cần kích hoạt vai trò Đọc báo cáo cho một phiên. Thiết kế session nào giảm quyền đang hoạt động?
A. Tự động kích hoạt mọi vai trò đã được gán để tránh thiếu quyền.
B. Kích hoạt vai trò có nhiều quyền nhất để giảm số lần kiểm tra policy.
C. Chỉ kích hoạt tập vai trò cần thiết cho phiên và thao tác hiện tại.
D. Chọn ngẫu nhiên một vai trò mỗi request để phân tán tải kiểm tra.
Đáp án đúng: C

Một nhân viên được cấp vai trò triển khai production trong hai giờ để xử lý sự cố. Kiểm soát nào bảo đảm quyền không tồn tại lâu hơn nhu cầu?
A. Người dùng tự gửi yêu cầu thu hồi khi hoàn tất công việc.
B. Chỉ giới hạn thời gian phiên đăng nhập mà không giới hạn role assignment.
C. Assignment có thời hạn và tự động hết hiệu lực sau cửa sổ được duyệt.
D. Vai trò được giữ lại đến kỳ access review tiếp theo của tổ chức.
Đáp án đúng: C

Một tài khoản khẩn cấp cần quyền quản trị khi hệ thống SSO gặp sự cố. Cách quản lý break-glass nào phù hợp?
A. Dùng tài khoản cá nhân của trưởng nhóm và chia sẻ mật khẩu khi cần.
B. Dùng tài khoản quản trị chung cho cả đội và lưu mật khẩu trong wiki nội bộ.
C. Cho phép tài khoản bỏ qua audit để tránh phụ thuộc hệ thống giám sát.
D. Bảo vệ credential, cảnh báo và rà soát mọi lần sử dụng.
Đáp án đúng: D

Một vai trò khẩn cấp có quyền rất rộng nhưng chỉ được dùng khi quy trình thường lệ không khả dụng. Cần kiểm soát bổ sung nào?
A. Ghi lý do, lưu bằng chứng và thu hồi ngay sau sự cố.
B. Cấp vai trò thường trực cho nhóm trực để họ không phải chờ phê duyệt.
C. Bỏ qua kiểm tra SoD vì tình huống khẩn cấp luôn được xem là hợp lệ.
D. Chỉ ghi nhận thời điểm đăng nhập mà không lưu các thao tác đã thực hiện.
Đáp án đúng: A

Một giao diện ẩn nút quản trị khi người dùng không có vai trò phù hợp. API vẫn nhận request trực tiếp từ client. Kiểm soát nào còn thiếu?
A. Client cần gửi tên vai trò trong header để backend tin cậy nhanh hơn.
B. Chỉ cần xác thực session một lần khi người dùng mở trang chính.
C. Giao diện cần ẩn thêm đường dẫn và đổi tên nút để khó phát hiện.
D. Kiểm tra authorization tại server cho từng thao tác nhạy cảm.
Đáp án đúng: D

Một người dùng sửa request để thay resource ID sang bản ghi thuộc phòng ban khác. Cách kiểm tra nào cần có trong RBAC?
A. Chỉ kiểm tra quyền ở màn hình danh sách trước khi mở chi tiết.
B. Đánh giá quyền trên thao tác và phạm vi tài nguyên được gán cho vai trò.
C. Chỉ kiểm tra người dùng có vai trò bất kỳ trong cùng hệ thống.
D. Tin resource ID nếu client gửi kèm tên vai trò hợp lệ.
Đáp án đúng: B

Một cloud operator có vai trò quản lý máy ảo nhưng không được sửa chính sách IAM. Cách biểu diễn quyền nào đúng?
A. Gộp hai loại quyền vào vai trò Operator vì đều thuộc vận hành cloud.
B. Tách quyền quản lý compute khỏi quyền quản trị identity và policy.
C. Cho phép quyền IAM nhưng chỉ ẩn màn hình cấu hình khỏi operator.
D. Dùng vai trò compute để kế thừa toàn bộ quyền quản trị subscription.
Đáp án đúng: B

Một cluster Kubernetes cần cho phép nhóm đọc pod trong namespace A nhưng không ở namespace B. Cấu hình nào phù hợp?
A. Dùng Role và RoleBinding riêng trong namespace A cho nhóm được phép.
B. Tạo service account mới cho từng pod và cấp cluster-admin cho account.
C. Ẩn namespace B trong kubeconfig nhưng giữ nguyên quyền API toàn cluster.
D. Dùng ClusterRoleBinding toàn cluster để gán quyền đọc pod cho nhóm.
Đáp án đúng: A

Một database có nhiều nhóm ứng dụng cần cùng tập quyền đọc báo cáo. Cách quản lý nào thể hiện RBAC rõ ràng?
A. Lưu danh sách bảng được đọc trong cấu hình ứng dụng thay cho quyền database.
B. Cấp quyền SELECT trực tiếp cho từng session khi mở kết nối database.
C. Dùng một tài khoản DBA chung và phân biệt ứng dụng qua tên client.
D. Tạo database role chứa quyền cần thiết rồi gán user hoặc group phù hợp.
Đáp án đúng: D

Một hệ điều hành dùng nhóm để gán quyền truy cập thư mục cho nhiều người. Điều gì cần lưu ý khi xem nhóm như một phần của RBAC?
A. Quản trị nhóm theo vai trò công việc và quyền tài nguyên được kiểm soát.
B. Chỉ cần tên nhóm trùng tên phòng ban là đủ để bảo đảm least privilege.
C. Mọi thành viên nhóm nên nhận quyền sở hữu toàn bộ thư mục hệ thống.
D. Quyền filesystem có thể bỏ qua vì người dùng đã được xác thực qua domain.
Đáp án đúng: A

Một nền tảng SaaS có cùng tên role Admin ở nhiều tenant. Một người dùng là Admin tenant X gửi request tới dữ liệu tenant Y. Kiểm soát nào cần thiết?
A. Chỉ kiểm tra người dùng có đăng nhập qua cùng một identity provider.
B. Ẩn tenant Y trong giao diện và dựa vào bộ lọc phía trình duyệt.
C. Ràng buộc role assignment và quyết định truy cập với tenant/resource context.
D. Tin role name Admin vì tên vai trò giống nhau giữa các tenant.
Đáp án đúng: C

Một tổ chức ánh xạ nhóm từ identity provider bên ngoài thành vai trò nội bộ. Cách nào giảm cấp quyền sai do group claim?
A. Ràng buộc issuer, group identifier và mapping đã được quản trị phê duyệt.
B. Dùng display name của nhóm làm khóa duy nhất cho quyết định truy cập.
C. Tin mọi group name trong token nếu chữ ký token được xác minh.
D. Tự động tạo vai trò mới cho mọi group xuất hiện lần đầu.
Đáp án đúng: A

Một yêu cầu cấp vai trò tài chính nhạy cảm được gửi bởi chính người sẽ nhận quyền. Workflow nào duy trì kiểm soát phê duyệt?
A. Người yêu cầu tự phê duyệt nếu đã hoàn thành khóa đào tạo nội bộ.
B. Quản lý trực tiếp tự động phê duyệt mọi vai trò trong nhóm mình.
C. Hệ thống cấp quyền ngay rồi gửi thông báo để kiểm tra sau.
D. Người có thẩm quyền độc lập phê duyệt dựa trên mục đích, phạm vi và thời hạn.
Đáp án đúng: D

Một cuộc điều tra cần xác định ai đã gán vai trò, cho ai, vào thời điểm nào và trong phạm vi nào. Audit event nên chứa gì?
A. Chỉ username của người nhận quyền và địa chỉ IP của request.
B. Toàn bộ nội dung phiên đăng nhập cùng mật khẩu được sử dụng.
C. Chỉ tên vai trò mới và tổng số người dùng đang được gán.
D. Actor, subject, role, scope, thời điểm, kết quả và tham chiếu phê duyệt.
Đáp án đúng: D

Một vai trò bị thu hồi nhưng ứng dụng cache quyết định authorization trong 30 phút. Rủi ro nào cần xử lý?
A. Chỉ cần xóa vai trò khỏi giao diện quản trị để chặn request tiếp theo.
B. Việc cache chỉ ảnh hưởng hiệu năng và không thay đổi quyền thực tế.
C. Quyền cũ có thể tiếp tục hiệu lực đến khi cache hết hạn hoặc bị vô hiệu.
D. Thu hồi role assignment tự động xóa mọi token và cache trên toàn hệ thống.
Đáp án đúng: C

Một vai trò sắp bị xóa nhưng đang được gán cho nhiều người dùng và được vai trò khác kế thừa. Bước nào nên thực hiện trước?
A. Xóa role ngay vì hệ thống sẽ tự suy ra quyền thay thế phù hợp.
B. Đổi tên role để các assignment cũ tự động chuyển sang role khác.
C. Xóa user assignment trước mà không kiểm tra các vai trò kế thừa.
D. Phân tích assignment và dependency, chuyển đổi hoặc thu hồi có kiểm soát.
Đáp án đúng: D

Một vai trò Báo cáo được cấp quyền wildcard trên mọi tài nguyên để tiện triển khai. Cách xử lý nào giảm rủi ro?
A. Ẩn tài nguyên nhạy cảm trong giao diện nhưng giữ quyền wildcard ở API.
B. Thay wildcard bằng tập quyền và phạm vi tài nguyên cần thiết đã xác nhận.
C. Tạo thêm vai trò con nhưng để wildcard ở vai trò cha cho tiện kế thừa.
D. Giữ wildcard nhưng chỉ cấp vai trò cho người dùng đã qua đào tạo.
Đáp án đúng: B

Một nhóm IAM muốn xác minh mô hình RBAC sau khi thay đổi role hierarchy và SoD constraints. Bộ kiểm thử nào phù hợp nhất?
A. Chỉ so sánh số lượng role trước và sau khi thay đổi mô hình.
B. Thử các trường hợp allow, deny, inheritance và tổ hợp vai trò xung đột.
C. Chỉ kiểm tra người dùng quản trị có thể truy cập mọi màn hình chính.
D. Chạy kiểm thử đăng nhập thành công và coi đó là bằng chứng authorization.
Đáp án đúng: B

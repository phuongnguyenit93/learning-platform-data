Một nền tảng thanh toán mở thêm kênh tích hợp đối tác nhưng hồ sơ đánh giá rủi ro vẫn dựa trên kiến trúc cũ, không bao gồm luồng dữ liệu và ranh giới tin cậy mới.
Đội an ninh lập risk register cho hệ thống trọng yếu nhưng nhiều rủi ro chỉ có mô tả chung, không gắn với tài sản, mối đe dọa, tác động kinh doanh hoặc chủ sở hữu.
Một rủi ro được đánh giá mức thấp vì xác suất xảy ra hiếm, dù nếu xảy ra sẽ làm ngừng dịch vụ thiết yếu nhiều ngày và gây nghĩa vụ thông báo theo hợp đồng.
Đơn vị kinh doanh chấp nhận rủi ro còn tồn tại sau đánh giá nhưng người phê duyệt không có thẩm quyền, không ghi thời hạn và không xác định điều kiện xem xét lại.
Một hệ thống mới được đưa vào production nhưng chưa có asset inventory đầy đủ, khiến nhóm assurance không xác định được máy chủ, dữ liệu, nhà cung cấp và endpoint nằm trong phạm vi đánh giá.
Phạm vi audit ghi rõ ứng dụng web nhưng bỏ sót pipeline triển khai, tài khoản cloud và dịch vụ SaaS có quyền thay đổi cấu hình production.
Nhóm kiến trúc đặt mục tiêu bảo mật là tuân thủ chính sách nội bộ nhưng không chuyển mục tiêu đó thành yêu cầu có thể kiểm chứng hoặc tiêu chí chấp nhận cụ thể.
Một control được ánh xạ đồng thời sang nhiều framework tuân thủ; các nhóm hiểu khác nhau về phạm vi và bằng chứng cần thiết nên cùng một kiểm soát được đánh giá không nhất quán.
Control owner thay đổi sau tái cơ cấu nhưng ma trận trách nhiệm chưa cập nhật; yêu cầu cung cấp bằng chứng bị chuyển vòng giữa nhiều bộ phận.
Một chính sách yêu cầu rà soát quyền truy cập định kỳ nhưng không quy định tần suất, phạm vi, người phê duyệt hoặc tiêu chí xử lý quyền không còn phù hợp.
Kiểm soát mã hóa dữ liệu được mô tả trong tài liệu thiết kế nhưng môi trường production có một kho dữ liệu cũ chưa bật mã hóa và không nằm trong lịch kiểm tra.
Nhóm assurance xác nhận control tồn tại dựa trên tài liệu quy trình nhưng chưa kiểm tra xem kiểm soát có thực sự vận hành trong kỳ được đánh giá hay không.
Một bằng chứng kiểm soát được chụp màn hình từ môi trường thử nghiệm nhưng báo cáo lại dùng để khẳng định cấu hình production đang đáp ứng yêu cầu.
Evidence repository lưu ảnh chụp cấu hình mà không có thời điểm thu thập, nguồn hệ thống, người thực hiện hoặc mã định danh tài sản nên không thể xác minh tính xác thực.
Nhóm audit nhận tệp xuất quyền truy cập từ quản trị viên hệ thống nhưng không đối chiếu tổng số bản ghi, bộ lọc và khoảng thời gian khiến tập bằng chứng có thể thiếu dữ liệu.
Bằng chứng gửi cho auditor chứa email, token truy cập và dữ liệu khách hàng; nhóm chia sẻ qua thư mục chung mà không phân loại hoặc giới hạn người xem.
Một kiểm soát được kiểm tra bằng mẫu nhỏ chỉ gồm các giao dịch thành công; các trường hợp thất bại, ngoại lệ và thao tác khẩn cấp không xuất hiện trong mẫu.
Quy trình lấy mẫu audit dựa trên danh sách tài khoản cũ trước khi có đợt tuyển dụng lớn, khiến nhiều tài khoản mới không được đưa vào phạm vi kiểm tra.
Người tự cấu hình firewall cũng là người tự xác nhận kiểm soát firewall đã hoạt động hiệu quả; tổ chức chưa có bước review độc lập.
Đội kiểm thử dự định chạy kiểm tra tải và khai thác lỗ hổng trên production nhưng chưa đánh giá nguy cơ gián đoạn, giới hạn phạm vi hoặc cơ chế dừng khẩn cấp.
Báo cáo penetration test ghi nhận không có phát hiện nghiêm trọng nhưng phạm vi kiểm thử loại trừ API nội bộ và tài khoản có đặc quyền được dùng trong vận hành thực tế.
Scanner phát hiện nhiều lỗ hổng trùng lặp ở các image cũ; nhóm kỹ thuật đóng toàn bộ finding theo trạng thái false positive mà không lưu lý do hoặc bằng chứng xác minh.
Một lỗ hổng có CVSS cao được xếp ưu tiên thấp vì tài sản không thể truy cập từ Internet, nhưng đường đi từ workload nội bộ bị xâm nhập chưa được đánh giá.
Nhóm remediation đánh dấu lỗ hổng đã khắc phục sau khi cập nhật package trên một máy mẫu, trong khi các replica và image triển khai trước đó vẫn chứa phiên bản dễ bị tấn công.
Một phát hiện audit được đóng sau khi chủ hệ thống gửi kế hoạch sửa chữa; không có kiểm thử lại để xác nhận thay đổi đã được triển khai và giảm rủi ro.
Đơn vị vận hành xin ngoại lệ kéo dài cho một control chưa đáp ứng vì phụ thuộc hệ thống cũ; hồ sơ ngoại lệ thiếu biện pháp bù trừ và ngày hết hạn.
Một biện pháp bù trừ được chấp thuận để thay thế kiểm soát MFA trên hệ thống cũ nhưng không có bằng chứng cho thấy biện pháp đó giảm được cùng loại rủi ro.
Phát hiện tái diễn qua ba kỳ audit dù các ticket trước đã đóng; nhóm assurance chưa phân tích nguyên nhân gốc hoặc đánh giá hiệu quả hành động khắc phục.
Pipeline CI/CD có bước kiểm tra bảo mật nhưng một số repository có thể bỏ qua gate bằng cách dùng nhánh hoặc workflow không nằm trong chính sách bắt buộc.
SAST tạo nhiều cảnh báo nhiễu khiến nhóm phát triển tắt rule quan trọng; chương trình assurance chưa theo dõi tỷ lệ false positive và thay đổi cấu hình scanner.
Dependency scanning không bao phủ thư viện được tải trực tiếp trong build script, nên báo cáo thành phần phần mềm thiếu các gói thực sự đi vào artifact phát hành.
Kiểm tra IaC được chạy trên pull request nhưng không kiểm tra cấu hình sau triển khai; một thay đổi thủ công trên cloud tạo public storage mà pipeline không phát hiện.
Một release khẩn cấp bỏ qua security review theo quy trình ngoại lệ nhưng sau triển khai không có bước hậu kiểm hoặc thời hạn hoàn tất các kiểm tra bị hoãn.
Quy trình quản lý thay đổi yêu cầu approval bảo mật nhưng không xác định thay đổi nào ảnh hưởng đến ranh giới tin cậy, quyền truy cập, dữ liệu hoặc cấu hình hạ tầng.
Control giám sát log được đánh giá đạt dựa trên việc log đã được gửi về hệ thống tập trung, nhưng không kiểm tra độ đầy đủ, đồng bộ thời gian và khả năng truy vấn khi điều tra.
Hệ thống cảnh báo có rule phát hiện truy cập đặc quyền bất thường nhưng không có người trực nhận cảnh báo ngoài giờ và không có bằng chứng xử lý theo SLA.
Diễn tập incident response hoàn thành theo lịch nhưng chỉ kiểm tra việc gửi thông báo; nhóm chưa thực hành cô lập tài sản, bảo toàn bằng chứng hoặc khôi phục dịch vụ.
Báo cáo backup compliance cho thấy mọi hệ thống đều có lịch sao lưu, nhưng chưa có bằng chứng restore thành công hoặc kiểm tra tính toàn vẹn dữ liệu sau khôi phục.
Kiểm thử disaster recovery đạt mục tiêu thời gian khôi phục trên môi trường mô phỏng nhưng không bao gồm phụ thuộc danh tính, DNS, khóa mã hóa và nhà cung cấp bên ngoài.
Nhà cung cấp SaaS gửi chứng nhận kiểm toán độc lập đã hết kỳ đánh giá; tổ chức vẫn dùng tài liệu đó làm bằng chứng hiện trạng mà không xem xét thay đổi dịch vụ.
Một nhà cung cấp thuê lại bên thứ ba xử lý dữ liệu nhạy cảm nhưng hồ sơ assurance chỉ đánh giá nhà cung cấp trực tiếp và bỏ qua chuỗi nhà thầu phụ.
Hợp đồng yêu cầu nhà cung cấp thông báo sự cố trong thời hạn ngắn nhưng quy trình giám sát assurance không kiểm tra điều khoản, đầu mối liên hệ hoặc bằng chứng diễn tập.
Dịch vụ cloud được đánh giá dựa trên chứng nhận của nhà cung cấp nhưng tổ chức chưa đánh giá cấu hình tenant, IAM, network và trách nhiệm bảo mật thuộc phía mình.
Dữ liệu khách hàng được chuyển sang khu vực địa lý mới để giảm độ trễ; đánh giá assurance chưa cập nhật yêu cầu residency, luồng dữ liệu và hợp đồng xử lý.
Đợt rà soát quyền truy cập hàng quý ghi nhận quản lý đã phê duyệt toàn bộ danh sách nhưng không có bằng chứng họ xem xét từng quyền hoặc xử lý tài khoản không còn cần thiết.
Tài khoản đặc quyền khẩn cấp được sử dụng trong một sự cố production nhưng log không liên kết được người yêu cầu, người phê duyệt, thời gian sử dụng và hành động thực hiện.
Quy trình onboarding và offboarding được kiểm tra qua chính sách nhân sự nhưng không đối chiếu thời điểm tài khoản thực tế được tạo, sửa quyền hoặc vô hiệu trên các hệ thống.
Chương trình đào tạo nhận thức bảo mật báo cáo tỷ lệ hoàn thành cao nhưng không đánh giá người học có nhận diện được phishing hoặc xử lý tình huống thực tế hay không.
Nhân viên ký xác nhận đã đọc chính sách bảo mật nhưng phiên bản chính sách đã thay đổi và hệ thống không lưu được người dùng đã xác nhận phiên bản nào.
Dashboard assurance hiển thị số lượng control đạt nhưng không phân biệt control chưa kiểm tra, thiếu bằng chứng, có ngoại lệ hoặc đã quá hạn đánh giá.
Chỉ số thời gian khắc phục lỗ hổng được tính từ lúc ticket đóng thay vì thời điểm bản vá có hiệu lực trên toàn bộ tài sản, làm báo cáo cải thiện sai lệch.
Continuous control monitoring lấy dữ liệu qua API nhưng credential kết nối hết hạn; dashboard tiếp tục hiển thị trạng thái xanh từ lần đồng bộ trước mà không báo dữ liệu đã cũ.
Một control tự động phát hiện cấu hình public storage nhưng rule bị thay đổi để loại trừ một bucket production mà không có review hoặc ghi nhận ngoại lệ.
Evidence automation thu thập cấu hình định kỳ nhưng đồng hồ hệ thống nguồn lệch nhiều giờ; báo cáo ghép nhầm bằng chứng trước và sau một thay đổi quan trọng.
Nhóm assurance xây dựng báo cáo tuân thủ từ nhiều công cụ có định nghĩa severity khác nhau; cùng một phát hiện được tính là high ở nơi này và medium ở nơi khác.
Một phát hiện audit được chuyển cho nhiều đội nhưng không có một chủ sở hữu chịu trách nhiệm cuối cùng, khiến thời hạn khắc phục liên tục bị gia hạn.
Ban lãnh đạo yêu cầu chứng minh hệ thống đáp ứng mục tiêu bảo mật trước khi ký hợp đồng lớn; hồ sơ hiện có gồm chính sách và chứng nhận nhưng thiếu kết quả kiểm thử, bằng chứng vận hành và ngoại lệ còn mở.
Một hệ thống được thay đổi kiến trúc sang microservices sau kỳ đánh giá; các control và bằng chứng cũ vẫn được tái sử dụng dù luồng dữ liệu, quyền truy cập và thành phần phụ thuộc đã thay đổi.
Đơn vị phát triển muốn đưa sản phẩm mới ra mắt nhưng threat model, security requirements và tiêu chí release assurance chưa được cập nhật sau khi thêm chức năng chia sẻ dữ liệu.
Một tổ chức cần duy trì assurance liên tục cho nhiều sản phẩm; mỗi nhóm tự chọn phương pháp kiểm tra và định dạng bằng chứng nên không thể so sánh mức độ bảo đảm giữa các hệ thống.
Kiểm toán nội bộ và kiểm toán bên ngoài cùng yêu cầu một loại bằng chứng trong thời gian gần nhau; nhóm vận hành tạo nhiều bản xuất khác nhau và không kiểm soát được tính nhất quán giữa các bản.
Chương trình assurance phát hiện một control quan trọng không hiệu quả nhưng bộ phận kinh doanh yêu cầu giữ nguyên ngày phát hành; quyết định tiếp tục cần được đánh giá theo rủi ro và thẩm quyền chấp nhận.
Kiểm tra sau triển khai cho thấy cấu hình bảo mật đã bị thay đổi bởi thao tác thủ công; hồ sơ change management không có ticket tương ứng và không xác định được người thực hiện.
Một sản phẩm đạt yêu cầu bảo mật trong môi trường staging nhưng production dùng dữ liệu, quyền và tích hợp bên ngoài khác biệt; kết quả đánh giá trước phát hành không phản ánh môi trường thực tế.

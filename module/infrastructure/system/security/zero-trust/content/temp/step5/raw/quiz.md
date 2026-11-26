Câu 1. Nguyên tắc cốt lõi nào định hướng kiến trúc Zero Trust?
A. Mọi request đều được đánh giá theo identity, thiết bị và resource.
B. Tin cậy mọi thiết bị thuộc mạng doanh nghiệp sau khi xác thực VPN.
C. Chỉ yêu cầu MFA khi người dùng truy cập từ Internet bên ngoài.
D. Dùng firewall biên để phân biệt người dùng nội bộ với người dùng bên ngoài.
Đáp án đúng: A

Câu 2. Một người dùng đã kết nối VPN vào mạng nội bộ; quyết định tin cậy nào phù hợp với Zero Trust?
A. Tin cậy phiên cho tới khi người dùng ngắt VPN hoặc đóng trình duyệt.
B. Cho phép mọi dịch vụ nội bộ vì kết nối đã đi qua VPN doanh nghiệp.
C. Xác minh lại identity, posture và quyền cho từng resource được yêu cầu.
D. Chỉ kiểm tra danh tính lại khi địa chỉ IP của người dùng thay đổi.
Đáp án đúng: C

Câu 3. Trong kiến trúc Zero Trust theo mô hình policy decision và enforcement, các thành phần PE, PA và PEP phối hợp thế nào?
A. PE thực thi lưu lượng, PA đánh giá rủi ro, PEP quản lý danh tính.
B. PE quyết định policy; PA cấu hình PEP; PEP áp dụng kiểm soát.
C. PE quản lý thiết bị, PA xác minh MFA, PEP phát hành chứng thư.
D. PE thu thập log, PA lưu trữ telemetry, PEP phân tích threat intelligence.
Đáp án đúng: B

Câu 4. Policy Engine chịu trách nhiệm chính cho hoạt động nào?
A. Thiết lập tunnel mạng giữa client và resource sau khi có yêu cầu.
B. Đánh giá policy và tín hiệu để cấp, từ chối hoặc thu hồi quyền.
C. Chuyển cấu hình enforcement tới PEP theo quyết định đã được tạo.
D. Thu thập log endpoint rồi lưu vào kho telemetry dùng chung.
Đáp án đúng: B

Câu 5. Policy Administrator đảm nhiệm vai trò nào trong luồng cấp quyền?
A. Chỉ đạo PEP thiết lập hoặc chấm dứt đường truy cập theo quyết định.
B. Đánh giá trực tiếp mọi tín hiệu và tự đưa ra quyết định cuối cùng.
C. Xác minh mật khẩu người dùng và đăng ký thiết bị mới trong directory.
D. Phân tích log bảo mật để phát hiện hành vi bất thường của workload.
Đáp án đúng: A

Câu 6. Policy Enforcement Point thực hiện chức năng gì?
A. Tính điểm rủi ro tổng thể và xây dựng policy cho toàn tổ chức.
B. Cấp danh tính cho người dùng và phát hành token truy cập dài hạn.
C. Đồng bộ thuộc tính thiết bị và nhóm người dùng giữa các directory.
D. Áp dụng quyết định cho phép hoặc từ chối tại điểm truy cập tới resource.
Đáp án đúng: D

Câu 7. Những tín hiệu nào nên được Policy Engine xem xét khi đánh giá một yêu cầu truy cập?
A. Địa chỉ IP nguồn và việc request có xuất phát từ mạng nội bộ hay không.
B. Identity, device posture, resource sensitivity, hành vi và context.
C. Tên miền của thiết bị và số lần người dùng đăng nhập trong tuần.
D. Nhóm phòng ban và vị trí văn phòng được khai báo khi tạo tài khoản.
Đáp án đúng: B

Câu 8. Đánh giá device posture nên dựa trên bằng chứng nào?
A. Địa chỉ IP, tên máy và hệ điều hành do client tự khai trong request.
B. Vị trí địa lý ước lượng và tên trình duyệt của người dùng cuối.
C. Số lượng ứng dụng cài đặt mà người dùng khai báo khi đăng ký thiết bị.
D. Tình trạng quản lý, bản vá, mã hóa, EDR và cấu hình bảo mật thiết bị.
Đáp án đúng: D

Câu 9. Workload identity nên được thiết kế theo nguyên tắc nào?
A. Dùng chung một API key dài hạn cho mọi dịch vụ cùng môi trường.
B. Tin cậy workload theo subnet triển khai mà không cần xác minh danh tính.
C. Danh tính workload riêng và credential ngắn hạn theo resource.
D. Lưu secret trong image để mọi replica có thể khởi động độc lập.
Đáp án đúng: C

Câu 10. Conditional access nên kết hợp những yếu tố nào khi quyết định cho phép truy cập?
A. Địa chỉ IP, thời gian trong ngày và tên trình duyệt đang sử dụng.
B. Danh tính, độ mạnh xác thực, device posture, rủi ro và độ nhạy tài nguyên.
C. Nhóm directory, vị trí văn phòng và trạng thái kết nối VPN hiện tại.
D. Loại mạng truy cập và số lần người dùng đã mở ứng dụng trong ngày.
Đáp án đúng: B

Câu 11. Least privilege trong Zero Trust được áp dụng như thế nào?
A. Cấp role rộng cho người dùng rồi dựa vào audit để phát hiện lạm dụng.
B. Cho phép mọi thao tác trong subnet nếu người dùng đã qua MFA.
C. Giới hạn principal theo resource, action và thời gian cần thiết.
D. Dùng cùng quyền mặc định cho mọi ứng dụng có mức độ nhạy cảm tương tự.
Đáp án đúng: C

Câu 12. Just-in-Time access giúp giảm rủi ro đặc quyền ra sao?
A. Cấp quyền quản trị thường trực cho nhóm vận hành để xử lý nhanh.
B. Chỉ yêu cầu người dùng ghi lý do sau khi hoàn tất thao tác đặc quyền.
C. Dùng tài khoản chia sẻ và luân phiên mật khẩu sau mỗi ca trực.
D. Cấp quyền cao tạm thời khi cần, sau phê duyệt và tự động hết hạn.
Đáp án đúng: D

Câu 13. Microsegmentation nhằm đạt mục tiêu bảo mật nào?
A. Chặn toàn bộ lưu lượng Internet nhưng giữ kết nối nội bộ mặc định.
B. Tách subnet theo phòng ban mà không kiểm soát luồng giữa các subnet.
C. Mã hóa mọi kết nối nội bộ nhưng không xét principal hoặc resource.
D. Giới hạn lưu lượng east-west theo workload và quan hệ cần thiết.
Đáp án đúng: D

Câu 14. Chính sách mặc định phù hợp cho luồng east-west giữa các workload là gì?
A. Allow mặc định giữa workload cùng cluster để giảm độ trễ ứng dụng.
B. Deny mặc định và chỉ mở các luồng đã được xác định, phê duyệt.
C. Cho phép theo dải IP nguồn và chỉ kiểm tra danh tính tại gateway biên.
D. Chỉ chặn port có dấu hiệu tấn công đã xuất hiện trong log.
Đáp án đúng: B

Câu 15. Khác biệt quan trọng giữa ZTNA và VPN truyền thống là gì?
A. ZTNA tạo tunnel mạng toàn phần; VPN chỉ cho phép từng ứng dụng riêng lẻ.
B. ZTNA chỉ mã hóa kết nối; VPN thực hiện xác minh danh tính liên tục.
C. ZTNA cấp quyền theo ứng dụng/resource; VPN thường mở kết nối ở mức mạng.
D. Hai công nghệ tương đương nếu cả hai đều yêu cầu MFA khi đăng nhập.
Đáp án đúng: C

Câu 16. Vì sao triển khai VPN không tự động đồng nghĩa với Zero Trust?
A. VPN luôn bỏ qua mã hóa nên không thể đáp ứng bất kỳ yêu cầu Zero Trust nào.
B. VPN chỉ phù hợp cho người dùng ẩn danh và không hỗ trợ xác thực danh tính.
C. VPN chỉ tạo tunnel, không tự đánh giá quyền từng resource liên tục.
D. VPN tự động phân đoạn workload và đánh giá device posture theo thời gian thực.
Đáp án đúng: C

Câu 17. Continuous evaluation có ý nghĩa gì sau khi phiên truy cập đã được cấp?
A. Chỉ xác minh một lần khi mở phiên rồi giữ quyền đến khi hết hạn.
B. Đánh giá lại tín hiệu và điều chỉnh hoặc thu hồi quyền trong suốt phiên.
C. Gia hạn session định kỳ mà không đánh giá thay đổi danh tính hoặc thiết bị.
D. Chỉ đánh giá lại khi người dùng thay đổi địa chỉ IP công khai.
Đáp án đúng: B

Câu 18. Thiết bị đang truy cập bị mất trạng thái compliant; hệ thống nên phản ứng thế nào?
A. Giữ nguyên quyền đến hết phiên vì posture chỉ có ý nghĩa lúc đăng nhập.
B. Chuyển thiết bị sang mạng nội bộ tin cậy để tránh gián đoạn công việc.
C. Hạ quyền hoặc chấm dứt phiên theo policy khi posture không còn đạt.
D. Bỏ qua tín hiệu thiết bị và chỉ đánh giá lại sau lần đăng nhập kế tiếp.
Đáp án đúng: C

Câu 19. Risk score nên được sử dụng ra sao trong quyết định truy cập động?
A. Kết hợp mức độ tin cậy, tác động resource và ngưỡng policy có thể giải thích.
B. Dùng điểm rủi ro làm quyền truy cập trực tiếp mà không xét resource.
C. Cộng mọi tín hiệu thành một điểm cố định dùng chung cho tất cả ứng dụng.
D. Chỉ dùng điểm rủi ro để gửi báo cáo, không ảnh hưởng quyết định truy cập.
Đáp án đúng: A

Câu 20. Policy decision cache cần được thiết kế thế nào để không giữ quyền đã lỗi thời?
A. Giữ quyết định Allow đến khi người dùng đăng xuất để giảm tải policy engine.
B. Giới hạn TTL, ràng buộc context và hỗ trợ invalidation khi policy thay đổi.
C. Cache theo địa chỉ IP để tái sử dụng quyền giữa các thiết bị cùng mạng.
D. Bỏ cache mọi quyết định để mỗi request phải gọi toàn bộ hệ thống directory.
Đáp án đúng: B

Câu 21. Telemetry nào hỗ trợ đánh giá liên tục trong kiến trúc Zero Trust?
A. IdP, EDR, posture, SIEM, threat intel và resource telemetry.
B. Chỉ firewall log và danh sách địa chỉ IP được phép truy cập.
C. Chỉ log đăng nhập thành công cùng số lượng request từ từng subnet.
D. Thông tin thiết bị do người dùng tự nhập trong biểu mẫu onboarding.
Đáp án đúng: A

Câu 22. Audit record cho một quyết định truy cập nên lưu những dữ liệu nào?
A. Principal, resource, action, context, policy version và kết quả.
B. Chỉ lưu địa chỉ IP và kết quả allow hoặc deny để giảm dung lượng log.
C. Chỉ lưu tên người dùng và thời gian đăng nhập gần nhất của họ.
D. Lưu toàn bộ payload ứng dụng thay cho thông tin về quyết định policy.
Đáp án đúng: A

Câu 23. Để tránh Policy Engine hoặc Policy Administrator trở thành điểm lỗi đơn, kiến trúc nên có đặc tính nào?
A. Đặt toàn bộ quyết định và enforcement trên một máy chủ duy nhất.
B. Tắt kiểm tra policy khi control plane quá tải để giữ mọi dịch vụ hoạt động.
C. Sao chép log sau mỗi ngày để có thể khôi phục policy khi cần.
D. Dự phòng, health check, state nhất quán và failover đã thử.
Đáp án đúng: D

Câu 24. Trong cloud, cách nào phù hợp để bảo vệ quyền truy cập giữa workload và tài nguyên?
A. Dùng chung một role quản trị cho mọi workload trong cùng cloud account.
B. Dùng workload identity và quyền IAM giới hạn theo resource, action.
C. Tin cậy mọi workload có private IP thuộc virtual network của tổ chức.
D. Lưu access key dài hạn trong image và chỉ giới hạn quyền ở firewall.
Đáp án đúng: B

Câu 25. Khi áp dụng Zero Trust cho môi trường hybrid, điều gì cần được thống nhất?
A. Identity, policy, resource classification, telemetry và enforcement.
B. Chỉ dải IP riêng và giao thức VPN giữa các trung tâm dữ liệu.
C. Cấu hình firewall biên và danh sách subnet được phép trao đổi dữ liệu.
D. Nhà cung cấp cloud và on-premises dùng cùng một dải địa chỉ mạng.
Đáp án đúng: A

Câu 26. Di chuyển ứng dụng legacy chưa hỗ trợ xác thực hiện đại nên bắt đầu như thế nào?
A. Thay toàn bộ ứng dụng cũ ngay lập tức trước khi phân tích phụ thuộc.
B. Cho phép ứng dụng cũ truy cập mọi mạng nội bộ để tránh thay đổi luồng.
C. Tắt xác minh người dùng tại gateway vì ứng dụng chưa hỗ trợ identity hiện đại.
D. Kiểm kê luồng, đặt gateway kiểm soát và áp dụng biện pháp bù có giới hạn.
Đáp án đúng: D

Câu 27. Khi dịch vụ điều khiển policy tạm thời mất kết nối, PEP nên xử lý ra sao?
A. Dùng policy cache có giới hạn và mức quyền an toàn theo độ nhạy resource.
B. Cho phép mọi request mới và giữ quyền cũ vô thời hạn khi policy lỗi.
C. Tắt PEP trên toàn hệ thống để các ứng dụng tự quyết định truy cập.
D. Chuyển mọi resource sang chế độ public cho đến khi control plane phục hồi.
Đáp án đúng: A

Câu 28. Phát hiện danh tính người dùng bị compromise trong lúc phiên vẫn hoạt động; hành động nào phù hợp?
A. Chờ phiên hết hạn tự nhiên để tránh tác động tới người dùng hợp lệ.
B. Chỉ đổi mật khẩu mà không đánh giá token hoặc session đã phát hành.
C. Thu hồi session/token, đánh giá lại risk và chặn các resource nhạy cảm.
D. Cho phép tiếp tục truy cập nếu request vẫn đi từ địa chỉ IP quen thuộc.
Đáp án đúng: C

Câu 29. Break-glass access nên được quản trị theo cách nào?
A. Dùng thường xuyên cho tác vụ quản trị để kiểm tra tài khoản còn hoạt động.
B. Chia sẻ credential khẩn cấp cho đội trực và không ghi log để bảo mật.
C. Bỏ MFA và mọi bước xác minh để giảm thời gian phản ứng sự cố.
D. Cô lập, phê duyệt nhiều bên, thời hạn ngắn và audit sau sử dụng.
Đáp án đúng: D

Câu 30. Truy cập của nhà thầu bên thứ ba nên được cấp theo mô hình nào?
A. Federated identity, quyền theo resource, expiry và monitoring.
B. Cấp VPN toàn mạng và tài khoản dùng chung cho toàn bộ nhà thầu.
C. Cho phép truy cập vĩnh viễn từ IP đối tác đã đăng ký ban đầu.
D. Dùng tài khoản nội bộ của nhân viên bảo trợ để mọi nhà thầu đăng nhập.
Đáp án đúng: A

Câu 31. Thiết bị BYOD không đạt đầy đủ posture có thể được xử lý ra sao?
A. Tin cậy thiết bị vì người dùng đã hoàn tất MFA trên thiết bị đó.
B. Cho phép truy cập mọi ứng dụng nội bộ nếu thiết bị có phần mềm diệt virus.
C. Cấp quyền giới hạn qua broker hoặc môi trường cách ly theo mức rủi ro.
D. Tắt đánh giá device posture cho BYOD để tránh phân biệt thiết bị cá nhân.
Đáp án đúng: C

Câu 32. Kiểm soát nào giúp ngăn truy cập chéo tenant trong kiến trúc Zero Trust?
A. Chỉ dùng tenant ID do client gửi lên để chọn dữ liệu cần truy cập.
B. Dùng chung cache authorization cho mọi tenant để giảm độ trễ.
C. Ẩn tenant ID trong giao diện để người dùng không thể thay đổi giá trị.
D. Ràng buộc principal, tenant, resource và policy ở mỗi lần truy cập.
Đáp án đúng: D

Câu 33. Một luồng east-west mới cần mở giữa hai workload; quy trình nào phù hợp?
A. Mở kết nối toàn bộ subnet trước rồi quan sát log để quyết định sau.
B. Cho phép mọi port giữa hai workload nếu cùng thuộc một namespace.
C. Thêm rule allow rộng và giữ vô thời hạn để tránh lỗi triển khai.
D. Xác định owner, mục đích, luồng cần thiết và kiểm thử policy tối thiểu.
Đáp án đúng: D

Câu 34. Lộ trình Zero Trust nên bắt đầu bằng hoạt động nào?
A. Triển khai agent enforcement đồng loạt rồi mới xác định tài sản cần bảo vệ.
B. Thay VPN bằng ZTNA trước khi kiểm kê ứng dụng và phụ thuộc mạng.
C. Kiểm kê danh tính, tài sản, luồng và mức độ rủi ro trước khi ưu tiên.
D. Bắt buộc MFA cho mọi tài khoản rồi xem như đã hoàn thành chuyển đổi.
Đáp án đúng: C

Câu 35. Chỉ số nào phản ánh tiến độ và hiệu quả triển khai Zero Trust tốt hơn?
A. Đếm số sản phẩm Zero Trust đã mua và số agent đã cài đặt.
B. Đo số lần người dùng đăng nhập và tổng số firewall rule hiện có.
C. Theo dõi tài nguyên được bảo vệ và chất lượng quyết định.
D. Đếm số subnet đã tạo mà không đánh giá luồng hoặc quyền thực tế.
Đáp án đúng: C

Câu 36. Kiểm chứng một policy Zero Trust mới nên thực hiện ra sao trước khi mở rộng?
A. Chỉ kiểm tra người dùng hợp lệ truy cập thành công trong mạng thử nghiệm.
B. Đánh giá policy qua tài liệu thiết kế mà không thực thi request thực tế.
C. Bật policy cho toàn bộ production rồi dùng số lượng alert làm tiêu chí.
D. Thử các tình huống hợp lệ và bị cấm, mô phỏng risk và xác minh log.
Đáp án đúng: D

Câu 37. Quản trị policy tập trung nên áp dụng kiểm soát nào để tránh drift và quyền ngoại lệ kéo dài?
A. Quản lý policy có lịch sử, người chịu trách nhiệm và hạn review.
B. Cho phép từng nhóm tự sửa policy production mà không lưu lịch sử.
C. Giữ ngoại lệ vô thời hạn nếu ban đầu được quản lý cấp cao phê duyệt.
D. Chỉ rà soát policy sau khi phát hiện một sự cố truy cập nghiêm trọng.
Đáp án đúng: A

Câu 38. Làm thế nào cân bằng bảo mật với trải nghiệm người dùng khi tín hiệu rủi ro thay đổi?
A. Dùng step-up hoặc hạn chế theo resource dựa trên risk và tín hiệu tin cậy.
B. Yêu cầu MFA lặp lại ở mọi request bất kể hành vi hoặc độ nhạy resource.
C. Bỏ qua tín hiệu rủi ro khi người dùng phản ánh có quá nhiều bước xác thực.
D. Cho phép truy cập rộng hơn khi người dùng gặp lỗi xác minh thiết bị.
Đáp án đúng: A

Câu 39. Khi một workload có dấu hiệu bị xâm nhập, biện pháp Zero Trust nào nên được phối hợp?
A. Chỉ chặn IP bên ngoài nhưng giữ mọi quyền east-west của workload.
B. Cô lập workload, thu hồi identity và đánh giá lại luồng liên quan.
C. Chờ EDR xác nhận malware rồi mới thu hồi credential dịch vụ.
D. Khởi động lại workload để xóa dấu hiệu bất thường trước khi điều tra.
Đáp án đúng: B

Câu 40. Vì sao cần lập bản đồ luồng dữ liệu và phụ thuộc trước khi phân đoạn mạng?
A. Tạo rule chặn theo subnet trước rồi điều chỉnh khi ứng dụng báo lỗi.
B. Xác định phụ thuộc thực tế để đặt policy không làm đứt luồng hợp lệ.
C. Chỉ lập sơ đồ thiết bị vật lý mà không cần mô tả dữ liệu trao đổi.
D. Dùng sơ đồ mạng cũ làm cơ sở vì luồng ứng dụng ít thay đổi theo thời gian.
Đáp án đúng: B

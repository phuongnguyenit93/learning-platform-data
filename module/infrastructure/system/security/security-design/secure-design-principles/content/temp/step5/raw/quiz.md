Câu 01. Nguyên tắc least privilege yêu cầu thiết kế quyền truy cập như thế nào?
A. Chỉ cấp quyền cần cho nhiệm vụ, phạm vi tài nguyên và thời hạn xác định.
B. Cho quyền đọc toàn bộ trước rồi giới hạn khi phát hiện lạm dụng.
C. Dùng một tài khoản dùng chung để giảm chi phí quản lý danh tính.
D. Cấp quyền theo chức danh chung và giữ nguyên khi nhiệm vụ hoặc phạm vi công việc thay đổi.
Đáp án đúng: A

Câu 02. Một kỹ sư cần quyền quản trị trong thời gian xử lý sự cố. Thiết kế nào phù hợp nhất?
A. Cấp quyền đúng phạm vi theo yêu cầu, có thời hạn và ghi nhận phê duyệt.
B. Giữ quyền quản trị thường trực để kỹ sư xử lý mọi sự cố mà không phải xin cấp lại.
C. Chia sẻ tài khoản quản trị giữa ca trực để luôn có người truy cập.
D. Cấp quyền quản trị toàn hệ thống rồi thu hồi theo lịch hàng quý.
Đáp án đúng: A

Câu 03. Thiết lập mặc định an toàn cho một dịch vụ mới nên ưu tiên điều gì?
A. Cho phép truy cập nội bộ mặc định để giảm bước khởi tạo.
B. Dùng cấu hình tương thích rộng rồi yêu cầu khách hàng gia cố.
C. Tắt chức năng không cần thiết và giới hạn truy cập ngay từ đầu.
D. Bật endpoint phổ biến rồi yêu cầu đội triển khai tự giới hạn quyền truy cập.
Đáp án đúng: C

Câu 04. Nguyên tắc default deny được thể hiện đúng nhất trong chính sách truy cập nào?
A. Chỉ kiểm tra quyền ở lần đăng nhập đầu tiên của phiên.
B. Cho phép yêu cầu nếu chưa có quy tắc từ chối tương ứng.
C. Từ chối yêu cầu trừ khi có quy tắc cho phép rõ ràng.
D. Cho phép mạng nội bộ và chặn riêng các địa chỉ Internet.
Đáp án đúng: C

Câu 05. Mục đích chính của defense in depth là gì?
A. Dùng nhiều lớp kiểm soát để lỗi một lớp không làm mất toàn bộ bảo vệ.
B. Chuyển mọi quyết định bảo mật sang một thiết bị trung tâm.
C. Đặt nhiều sản phẩm cùng loại tại một điểm vào nhưng dùng chung một quyết định.
D. Tăng số bước phê duyệt giống nhau cho mọi yêu cầu truy cập.
Đáp án đúng: A

Câu 06. Dịch vụ phân quyền tạm thời không khả dụng. Hành vi nào phù hợp với fail securely?
A. Từ chối thao tác nhạy cảm cho đến khi quyết định quyền được xác minh.
B. Cho phép thao tác khi dịch vụ phân quyền lỗi vì người dùng đã xác thực trước đó.
C. Dùng quyền quản trị mặc định để tránh gián đoạn nghiệp vụ.
D. Bỏ qua kiểm tra quyền trong thời gian ngắn để giữ khả dụng.
Đáp án đúng: A

Câu 07. Một hệ thống cần xử lý lỗi xác thực khi IdP mất kết nối. Thiết kế nào an toàn hơn?
A. Dùng header danh tính do client gửi để duy trì đăng nhập khi IdP mất kết nối.
B. Chấp nhận mọi danh tính đã gửi để tránh khóa người dùng.
C. Tạm tắt MFA và giữ nguyên các quyền sau khi đăng nhập.
D. Không tạo phiên mới và chỉ giữ phiên cũ còn hạn theo chính sách.
Đáp án đúng: D

Câu 08. Complete mediation yêu cầu hệ thống kiểm tra quyền vào thời điểm nào?
A. Khi vai trò thay đổi hoặc phiên được tạo mới.
B. Mỗi lần truy cập tài nguyên cần được bảo vệ.
C. Chỉ khi người dùng đăng nhập vào hệ thống lần đầu.
D. Chỉ khi request đến từ một mạng không tin cậy.
Đáp án đúng: B

Câu 09. Thiết kế separation of duties cho việc phát hành thay đổi nhạy cảm nên làm gì?
A. Tách người đề xuất và người phê duyệt bằng danh tính riêng.
B. Dùng một tài khoản nhóm để mọi thao tác có cùng quyền.
C. Yêu cầu hai người đăng nhập nhưng dùng chung một danh tính.
D. Cho người triển khai tự phê duyệt khi mọi thao tác đã được ghi audit.
Đáp án đúng: A

Câu 10. Nguyên tắc economy of mechanism khuyến khích lựa chọn thiết kế nào?
A. Ẩn logic phức tạp để người dùng không thể suy luận cách hoạt động.
B. Thêm nhiều lớp cấu hình để bao phủ mọi trường hợp hiếm gặp.
C. Giữ cơ chế bảo mật đơn giản để dễ hiểu, kiểm thử và rà soát.
D. Tạo cơ chế riêng cho từng request để tránh dùng thành phần chung.
Đáp án đúng: C

Câu 11. Nguyên tắc open design có ý nghĩa gì với kiến trúc bảo mật?
A. An toàn dựa vào khóa và bí mật cần giữ, không dựa vào giấu thiết kế.
B. Giữ kín sơ đồ kiến trúc và chi tiết thuật toán thay cho việc bảo vệ khóa bí mật.
C. Chỉ dùng thuật toán nội bộ để người ngoài không biết cách xử lý.
D. Dựa vào việc giữ kín sơ đồ và quy trình để hạn chế khả năng phân tích.
Đáp án đúng: A

Câu 12. Một kiểm soát bảo mật gây khó hiểu khiến nhân viên tìm cách né tránh. Nguyên tắc nào cần xem lại?
A. Ẩn thông báo lỗi để người dùng không biết cơ chế đang hoạt động.
B. Tăng số bước bắt buộc để người dùng không thể bỏ qua kiểm soát.
C. Cho phép bỏ qua kiểm soát khi người dùng báo bất tiện.
D. Thiết kế cần dễ sử dụng để người dùng có thể tuân thủ đúng.
Đáp án đúng: D

Câu 13. Tại ranh giới tin cậy giữa API gateway và backend, kiểm soát nào cần thiết?
A. Xác minh danh tính, quyền và dữ liệu ở phía nhận theo hợp đồng tin cậy.
B. Giả định request nội bộ luôn hợp lệ sau khi qua gateway.
C. Chỉ kiểm tra địa chỉ IP vì các dịch vụ nằm trong cùng mạng.
D. Tin header do gateway chuyển tiếp vì backend chỉ nhận request từ mạng nội bộ.
Đáp án đúng: A

Câu 14. Cách tiếp cận zero trust phù hợp nhất với nguyên tắc nào?
A. Chỉ xác minh người dùng ở biên mạng rồi tin toàn bộ phiên.
B. Cho phép dịch vụ nội bộ giao tiếp tự do trong cùng subnet.
C. Không cấp niềm tin mặc định; xác minh ngữ cảnh và quyền cho từng truy cập.
D. Tin thiết bị đã vào mạng doanh nghiệp và chỉ xác minh lại khi có cảnh báo.
Đáp án đúng: C

Câu 15. Biện pháp trực tiếp nào giúp giảm attack surface của một máy chủ?
A. Chặn truy cập giao diện nhưng giữ endpoint quản trị đang mở.
B. Gỡ dịch vụ, cổng và thành phần không cần cho nhiệm vụ của máy chủ.
C. Ẩn banner và đổi cổng mặc định nhưng vẫn giữ dịch vụ không cần thiết.
D. Ẩn banner phiên bản nhưng giữ mọi dịch vụ đang lắng nghe.
Đáp án đúng: B

Câu 16. Thông báo lỗi cho người dùng nên được thiết kế thế nào để hạn chế lộ thông tin?
A. Trả thông tin cấu hình đầy đủ nhưng mã hóa nội dung bằng Base64.
B. Ẩn mọi lỗi và không ghi lại chi tiết phục vụ điều tra.
C. Trả stack trace cùng tên bảng để người dùng tự xác định lỗi mà không cần hỗ trợ.
D. Hiển thị thông tin cần thiết và giữ chi tiết nội bộ trong log được bảo vệ.
Đáp án đúng: D

Câu 17. Một cơ chế xác thực mới gặp lỗi cấu hình. Hành vi dự phòng nào phù hợp?
A. Bỏ qua kiểm tra chữ ký để duy trì luồng đăng nhập.
B. Từ chối xác thực mới và báo lỗi an toàn để quản trị viên xử lý.
C. Chuyển sang mật khẩu mặc định đã dùng trong môi trường thử nghiệm.
D. Tin vào kết quả xác thực gần nhất cho mọi người dùng tiếp theo.
Đáp án đúng: B

Câu 18. Nguyên tắc least common mechanism gợi ý điều gì khi thiết kế hệ thống nhiều tenant?
A. Đặt mọi tenant trong cùng miền tin cậy để giảm cấu hình.
B. Chia sẻ cache toàn cục để các tenant luôn có dữ liệu đồng nhất.
C. Dùng một kho dữ liệu, cache và quyền quản trị chung để giảm chi phí vận hành.
D. Giảm tài nguyên và cơ chế dùng chung có thể tạo luồng rò rỉ giữa tenant.
Đáp án đúng: D

Câu 19. Tách chức năng đặc quyền khỏi tiến trình xử lý thông thường giúp ích gì?
A. Đảm bảo tiến trình đặc quyền không cần ghi log hoạt động.
B. Cho toàn bộ ứng dụng chạy với quyền cao để tránh chuyển đổi giữa các tiến trình.
C. Giảm số lần xác thực vì mọi thao tác dùng cùng quyền tiến trình.
D. Giới hạn phần mã và tài nguyên có thể bị ảnh hưởng khi tiến trình lỗi.
Đáp án đúng: D

Câu 20. Muốn ngăn truy cập chéo tenant, nơi nào nên thực thi kiểm tra quyền?
A. Trong báo cáo cuối cùng sau khi dữ liệu đã được truy vấn.
B. Chỉ ở gateway, dù backend có thể được gọi trực tiếp.
C. Tại điểm truy cập dữ liệu hoặc dịch vụ xử lý tài nguyên.
D. Chỉ tại giao diện để ẩn bản ghi của tenant khác.
Đáp án đúng: C

Câu 21. Một request mang theo tenant ID do client cung cấp. Backend nên làm gì?
A. Chỉ kiểm tra tenant ID ở giao diện trước khi gửi request.
B. Đối chiếu tenant với danh tính và quyền đã xác minh ở phía máy chủ.
C. Dùng tenant ID để tự chọn database mà không kiểm tra quyền.
D. Tin tenant ID nếu đúng định dạng và có trong danh sách tenant đã đăng ký.
Đáp án đúng: B

Câu 22. Cách thiết kế nào bảo vệ tốt hơn khi nhiều service gọi lẫn nhau?
A. Dùng một credential chung cho các service để đơn giản hóa việc tích hợp.
B. Cho mọi service quyền quản trị để tránh lỗi tích hợp.
C. Dùng danh tính dịch vụ riêng và quyền giới hạn theo từng quan hệ.
D. Tin mọi request từ subnet nội bộ và bỏ xác thực service.
Đáp án đúng: C

Câu 23. Một thành phần bị xâm nhập trong kiến trúc nhiều lớp. Defense in depth cần đạt điều gì?
A. Đặt mọi bí mật dùng chung để các thành phần còn lại tiếp tục chạy.
B. Cho thành phần bị xâm nhập truy cập rộng để các dịch vụ còn lại tiếp tục hoạt động.
C. Giới hạn khả năng truy cập tiếp và giảm phạm vi ảnh hưởng của thành phần đó.
D. Chỉ dựa vào firewall biên để ngăn mọi hoạt động sau xâm nhập.
Đáp án đúng: C

Câu 24. Khi một dependency bảo mật gặp lỗi, cách suy giảm dịch vụ nào hợp lý?
A. Cho phép thao tác đặc quyền bằng cache không giới hạn thời gian.
B. Chuyển request sang dependency không xác minh danh tính.
C. Tắt mọi kiểm soát bảo mật để giữ toàn bộ chức năng hoạt động như trước.
D. Tắt thao tác nhạy cảm nhưng duy trì chức năng ít rủi ro nếu được thiết kế.
Đáp án đúng: D

Câu 25. Thiết kế backup và restore an toàn nên bảo đảm điều gì?
A. Khôi phục dữ liệu trước rồi rà soát quyền và cấu hình sau khi dịch vụ hoạt động.
B. Khôi phục dữ liệu cùng kiểm soát truy cập, cấu hình và kiểm tra tính toàn vẹn.
C. Dùng tài khoản quản trị chung để đơn giản hóa quy trình phục hồi.
D. Giữ bản sao credential cũ để mọi dịch vụ có thể kết nối ngay.
Đáp án đúng: B

Câu 26. Một hệ thống cần giữ audit log nhưng không được lộ secret. Thiết kế nào phù hợp?
A. Không ghi sự kiện xác thực để tránh lưu dữ liệu nhạy cảm.
B. Chỉ mã hóa file log nhưng cho mọi analyst quyền giải mã.
C. Ghi nguyên request để giữ ngữ cảnh điều tra, kể cả credential và token.
D. Ghi sự kiện cần thiết và loại bỏ hoặc che credential trước khi lưu.
Đáp án đúng: D

Câu 27. Khi nào nên đặt kiểm soát bảo mật tại backend thay vì chỉ tại frontend?
A. Khi backend là nơi thực thi quyền và truy cập dữ liệu thực tế.
B. Khi frontend có thể ẩn nút thao tác khỏi người dùng thông thường.
C. Khi API chỉ được gọi từ ứng dụng do tổ chức phát hành.
D. Khi gateway đã kiểm tra định dạng request trước khi chuyển tiếp.
Đáp án đúng: A

Câu 28. Một chức năng quản trị không cần cho phần lớn triển khai. Mặc định nào hợp lý?
A. Mở cho mạng nội bộ và yêu cầu người dùng tự giới hạn.
B. Vô hiệu hóa và chỉ bật có chủ đích trong môi trường cần sử dụng.
C. Cho phép sẵn nhưng ẩn liên kết khỏi menu người dùng.
D. Bật trong mọi môi trường nhưng chỉ ghi log khi có truy cập.
Đáp án đúng: B

Câu 29. Một dịch vụ có thể chạy với quyền đọc hoặc quyền ghi. Thiết kế nào an toàn hơn?
A. Chỉ cấp quyền đọc ở giao diện và giữ quyền ghi trong backend.
B. Tách quyền theo chức năng và chỉ cấp quyền ghi cho luồng cần thiết.
C. Dùng quyền ghi chung rồi dựa vào kiểm thử của client.
D. Cấp cả đọc và ghi cho mọi tiến trình để tránh lỗi quyền.
Đáp án đúng: B

Câu 30. Nguyên tắc complete mediation có thể bị vi phạm trong tình huống nào?
A. Quyền được kiểm tra lúc tạo phiên nhưng không kiểm tra lại khi truy cập đối tượng.
B. Backend xác minh danh tính và quyền trước thao tác ghi dữ liệu.
C. Mỗi request đều xác minh quyền trên đối tượng đích trước khi xử lý.
D. Quyền được kiểm tra lại khi vai trò hoặc trạng thái tài khoản đổi.
Đáp án đúng: A

Câu 31. Một nhóm đề xuất chia sẻ thư mục chứa dữ liệu của nhiều nhóm để dễ vận hành. Rủi ro thiết kế chính là gì?
A. Thư mục chung không thể áp dụng quyền truy cập ở cấp tệp.
B. Việc chia sẻ khiến mọi bản sao lưu tự động bị công khai.
C. Cơ chế dùng chung có thể tạo truy cập ngoài ý muốn giữa các nhóm.
D. Chia sẻ thư mục luôn làm dữ liệu mất tính toàn vẹn khi ghi.
Đáp án đúng: C

Câu 32. Thiết kế xử lý exception trong một thao tác thanh toán nên ưu tiên điều gì?
A. Tiếp tục giao dịch với quyền rộng để tránh làm gián đoạn người dùng.
B. Giữ trạng thái nhất quán và không bỏ qua kiểm tra bảo mật khi lỗi.
C. Trả thành công mặc định nếu dịch vụ xác minh không phản hồi.
D. Thực hiện lại vô hạn cho tới khi có kết quả từ dependency.
Đáp án đúng: B

Câu 33. Một hệ thống có chế độ khẩn cấp khi dịch vụ xác thực gián đoạn. Cần thiết kế gì?
A. Dùng một mật khẩu cố định để toàn bộ nhóm vận hành đăng nhập.
B. Giới hạn rõ thao tác được phép, người phê duyệt và thời gian hiệu lực.
C. Tắt log trong chế độ khẩn cấp để giảm tải cho hệ thống.
D. Cho phép mọi người dùng đã biết URL truy cập chức năng khẩn cấp.
Đáp án đúng: B

Câu 34. Một kiến trúc dựa vào một firewall duy nhất để bảo vệ dữ liệu nhạy cảm. Đánh giá nào hợp lý?
A. Chỉ cần đổi địa chỉ IP của firewall theo định kỳ.
B. Firewall đủ nếu tất cả máy chủ đặt trong mạng riêng.
C. Nên chuyển firewall ra gần database để tăng số hop mạng.
D. Cần thêm kiểm soát độc lập ở danh tính, ứng dụng và lớp dữ liệu.
Đáp án đúng: D

Câu 35. Cách nào giúp kiểm tra một ranh giới tin cậy có được thực thi thật?
A. Đọc sơ đồ kiến trúc và xác nhận các vùng được đặt tên rõ ràng.
B. Kiểm tra giao diện có hiển thị biểu tượng ổ khóa hay không.
C. Xác nhận mọi request đều đi qua cùng một tên miền công khai.
D. Thử truy cập trực tiếp qua các đường gọi và xác minh kiểm soát ở phía nhận.
Đáp án đúng: D

Câu 36. Một thay đổi kiến trúc thêm luồng dữ liệu mới giữa hai vùng. Hành động nào nên làm trước triển khai?
A. Cho phép luồng mới mặc định rồi theo dõi cảnh báo sau triển khai.
B. Chỉ cập nhật tài liệu sau khi thay đổi đã chạy ổn định.
C. Đánh giá lại trust boundary, luồng dữ liệu và các giả định đe dọa.
D. Giữ nguyên threat model nếu không thay đổi giao diện người dùng.
Đáp án đúng: C

Câu 37. Một kiểm soát dự phòng dùng chung cùng credential với kiểm soát chính. Điểm yếu nào còn tồn tại?
A. Hai lớp cùng credential luôn làm tăng độ tin cậy khi failover.
B. Một lần lộ credential có thể làm mất hiệu lực cả hai lớp bảo vệ.
C. Credential dùng chung giúp tách biệt quyền giữa hai lớp tốt hơn.
D. Chỉ cần ghi log riêng thì hai lớp không còn phụ thuộc nhau.
Đáp án đúng: B

Câu 38. Cách đánh giá quyết định kiến trúc bảo mật trước khi triển khai hiệu quả nhất là gì?
A. Chọn phương án quen thuộc mà không cần ghi nhận giả định.
B. Chỉ xem xét chi phí triển khai và khả năng mở rộng hệ thống.
C. Đợi penetration test cuối dự án rồi mới xem xét kiến trúc.
D. Đối chiếu threat model, yêu cầu, giả định, trade-off và test evidence.
Đáp án đúng: D

Câu 39. Một yêu cầu bảo mật chưa có tiêu chí kiểm chứng rõ ràng. Nhóm nên làm gì?
A. Chuyển yêu cầu thành khuyến nghị để không cản trở tiến độ.
B. Đánh giá bằng cảm nhận của reviewer sau khi hoàn thành.
C. Xác định điều kiện đạt, hành vi bị từ chối và bằng chứng cần thu thập.
D. Đưa yêu cầu vào tài liệu và để nhóm triển khai tự diễn giải.
Đáp án đúng: C

Câu 40. Một kiểm soát có thể bị vô hiệu hóa bởi cấu hình thủ công sau triển khai. Cách thiết kế nào tốt hơn?
A. Quản lý cấu hình như mã, giới hạn quyền sửa và phát hiện drift.
B. Cho phép sửa tự do để đội vận hành phản ứng nhanh hơn.
C. Ẩn trang cấu hình khỏi giao diện nhưng giữ quyền sửa trực tiếp.
D. Chỉ ghi lại cấu hình ban đầu và không theo dõi thay đổi.
Đáp án đúng: A

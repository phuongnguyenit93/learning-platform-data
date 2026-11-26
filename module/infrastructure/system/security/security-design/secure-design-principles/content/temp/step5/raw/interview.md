Anh/chị giải thích các nguyên tắc secure design và cách chúng ảnh hưởng tới quyết định kiến trúc của một hệ thống như thế nào?
Anh/chị áp dụng nguyên tắc least privilege để xác định quyền tối thiểu cho người dùng, dịch vụ và workload ra sao?
Khi một thành phần cần quyền truy cập nhiều tài nguyên, anh/chị xác định phạm vi quyền thực sự cần thiết bằng cách nào?
Anh/chị thiết kế quy trình cấp, rà soát và thu hồi quyền để đặc quyền không tồn tại lâu hơn nhu cầu như thế nào?
Những rủi ro nào phát sinh khi tài khoản quản trị, tài khoản dịch vụ và tài khoản vận hành dùng chung một danh tính?
Anh/chị áp dụng separation of duties cho các thao tác nhạy cảm như phê duyệt, triển khai và quản trị khóa ra sao?
Trong tình huống khẩn cấp, anh/chị thiết kế quyền break-glass thế nào để vừa hỗ trợ phục hồi vừa bảo đảm khả năng kiểm toán?
Anh/chị xác định những cấu hình nào cần được xem là secure by default khi một dịch vụ hoặc sản phẩm mới được triển khai?
Làm thế nào để bảo đảm tính năng, cổng mạng, API và quyền truy cập không cần thiết ở trạng thái mặc định đều bị tắt?
Khi một tính năng bảo mật làm giảm tiện dụng, anh/chị đánh giá lựa chọn mặc định và cơ chế opt-in như thế nào?
Anh/chị thiết kế quy trình onboarding để môi trường mới không vô tình khởi chạy với mật khẩu mặc định hoặc cấu hình công khai ra sao?
Nguyên tắc fail securely được áp dụng thế nào khi xác thực, phân quyền hoặc kiểm tra chính sách gặp lỗi?
Trong trường hợp dịch vụ kiểm tra quyền không khả dụng, anh/chị quyết định fail closed hay hành vi dự phòng nào dựa trên tiêu chí gì?
Anh/chị xử lý lỗi nội bộ và thông báo cho người dùng như thế nào để không làm lộ dữ liệu, secret hoặc chi tiết kiến trúc?
Làm thế nào bảo đảm lỗi một thành phần không khiến hệ thống bỏ qua bước kiểm tra bảo mật ở thành phần kế tiếp?
Anh/chị áp dụng defense in depth cho một luồng truy cập dữ liệu nhạy cảm qua nhiều lớp hệ thống như thế nào?
Những lớp kiểm soát nào nên độc lập để một lỗi đơn lẻ không làm mất toàn bộ khả năng bảo vệ?
Anh/chị đánh giá khi nào nhiều lớp kiểm soát đang bổ trợ nhau và khi nào chúng chỉ lặp lại cùng một điểm yếu?
Nguyên tắc complete mediation ảnh hưởng ra sao tới việc kiểm tra quyền trên mỗi request và mỗi lần truy cập tài nguyên?
Anh/chị phát hiện và xử lý các đường truy cập có thể bỏ qua gateway, proxy hoặc lớp kiểm soát trung tâm như thế nào?
Anh/chị xác định trust boundary giữa người dùng, thiết bị, ứng dụng, dịch vụ nội bộ và nhà cung cấp ra sao?
Những dấu hiệu nào cho thấy một ranh giới tin cậy trong sơ đồ kiến trúc chưa được thực thi bằng cơ chế kỹ thuật?
Làm thế nào xác định dữ liệu hoặc lệnh nào cần được xem là không tin cậy khi đi qua nhiều thành phần?
Anh/chị thiết kế kiểm soát cho giao tiếp giữa các service để xác minh danh tính, quyền và ngữ cảnh của từng bên như thế nào?
Anh/chị giảm attack surface bằng cách loại bỏ endpoint, giao thức, dịch vụ và chức năng không cần thiết ra sao?
Khi một thành phần cũ không thể loại bỏ ngay, anh/chị thiết kế biện pháp cô lập và giới hạn khả năng truy cập như thế nào?
Anh/chị đánh giá tác động của các cổng quản trị, debug endpoint và giao diện hỗ trợ tới bề mặt tấn công ra sao?
Những tiêu chí nào giúp lựa chọn giữa việc đóng một điểm vào, giới hạn nguồn truy cập hoặc bổ sung lớp bảo vệ?
Anh/chị tổ chức threat modeling để tìm các đường tấn công và kiểm chứng giả định kiến trúc vào thời điểm nào?
Làm thế nào để threat model được cập nhật khi luồng dữ liệu, thành phần, quyền hoặc nhà cung cấp thay đổi?
Anh/chị đánh giá rủi ro của một điểm lỗi đơn lẻ trong kiến trúc bảo mật và khả năng kẻ tấn công vượt qua nhiều lớp kiểm soát như thế nào?
Nguyên tắc economy of mechanism giúp giảm lỗi bảo mật trong thiết kế phức tạp ra sao?
Khi có nhiều cách triển khai một kiểm soát, anh/chị cân nhắc tính đơn giản, khả năng kiểm chứng và nguy cơ cấu hình sai như thế nào?
Anh/chị áp dụng secure-by-design cho việc lựa chọn giao thức, thuật toán và cơ chế quản lý khóa ra sao?
Làm thế nào để bảo vệ dữ liệu nhạy cảm trong quá trình truyền, lưu trữ, xử lý và xóa theo đúng mục đích sử dụng?
Anh/chị xác định ranh giới giữa dữ liệu công khai, nội bộ, mật và dữ liệu cần kiểm soát đặc biệt như thế nào?
Những quyết định thiết kế nào giúp giảm lượng dữ liệu nhạy cảm được thu thập và thời gian dữ liệu được lưu giữ?
Anh/chị thiết kế logging và observability để hỗ trợ điều tra nhưng không làm lộ secret hoặc thông tin cá nhân ra sao?
Anh/chị áp dụng secure defaults cho xác thực, quản lý phiên và phục hồi tài khoản như thế nào?
Làm thế nào để tránh thiết kế một cơ chế xác thực mạnh nhưng lại có đường khôi phục hoặc hỗ trợ yếu hơn?
Anh/chị thiết kế authorization để kiểm tra quyền theo chủ thể, tài nguyên, hành động và ngữ cảnh như thế nào?
Những rủi ro nào xuất hiện khi ứng dụng tin vào vai trò hoặc thuộc tính do client tự gửi lên?
Anh/chị phân tách tenant và ngăn truy cập chéo dữ liệu ngay trong kiến trúc thay vì chỉ dựa vào giao diện như thế nào?
Anh/chị lựa chọn network segmentation và ranh giới vùng tin cậy dựa trên luồng nghiệp vụ và mức nhạy cảm ra sao?
Làm thế nào để một dịch vụ chỉ được phép giao tiếp với các dependency đã xác định thay vì toàn bộ mạng nội bộ?
Anh/chị thiết kế bảo vệ cho hệ thống khi một máy chủ, container hoặc workload bị chiếm quyền như thế nào?
Nguyên tắc resilience ảnh hưởng ra sao tới thiết kế rate limiting, isolation, circuit breaker và phục hồi sau sự cố?
Anh/chị cân nhắc tác động bảo mật khi một cơ chế dự phòng hoặc failover chuyển sang chế độ vận hành suy giảm như thế nào?
Làm thế nào bảo đảm backup, restore và disaster recovery không vô tình mở lại quyền truy cập hoặc cấu hình không an toàn?
Anh/chị áp dụng privacy by design và data minimization trong các quyết định kiến trúc có xử lý dữ liệu cá nhân ra sao?
Những cân nhắc nào giúp thiết kế giao diện và quy trình bảo mật dễ hiểu để người dùng không tìm cách né tránh kiểm soát?
Anh/chị đánh giá nguy cơ một kiểm soát bảo mật bị vô hiệu hóa bởi thao tác vận hành hoặc quy trình hỗ trợ như thế nào?
Làm thế nào để tài liệu kiến trúc thể hiện rõ giả định, trust boundary, luồng dữ liệu và trách nhiệm của từng thành phần?
Anh/chị tổ chức security architecture review trước khi triển khai thay đổi lớn dựa trên tiêu chí và bằng chứng nào?
Những trường hợp nào cần yêu cầu đánh giá độc lập hoặc phê duyệt ngoại lệ trước khi chấp nhận một quyết định thiết kế?
Anh/chị ghi nhận và theo dõi các trade-off bảo mật khi yêu cầu khả dụng, hiệu năng hoặc chi phí giới hạn lựa chọn kiến trúc như thế nào?
Làm thế nào để kiểm chứng một nguyên tắc secure design đã được hiện thực hóa trong cấu hình và hành vi chạy thực tế?
Anh/chị chọn test case nào để phát hiện việc bypass kiểm soát, leo thang đặc quyền hoặc truy cập ngoài trust boundary?
Những chỉ số nào giúp đánh giá bề mặt tấn công và mức độ tuân thủ secure design theo thời gian?
Anh/chị phát hiện configuration drift làm suy yếu secure defaults hoặc least privilege trong môi trường vận hành như thế nào?
Khi một thư viện, dịch vụ nền tảng hoặc nhà cung cấp thay đổi, anh/chị đánh giá tác động tới giả định bảo mật của kiến trúc ra sao?
Anh/chị tích hợp yêu cầu secure design vào tiêu chí hoàn thành công việc và quy trình phê duyệt thay đổi như thế nào?
Làm thế nào để các nhóm sản phẩm, phát triển, vận hành và bảo mật cùng chịu trách nhiệm về quyết định thiết kế an toàn?
Anh/chị xử lý một ngoại lệ thiết kế đã được chấp thuận nhưng rủi ro và bối cảnh hệ thống thay đổi như thế nào?
Những bài học nào từ incident hoặc penetration test nên dẫn tới thay đổi nguyên tắc, mẫu kiến trúc hoặc guardrail dùng chung?
Anh/chị đánh giá khi nào một hệ thống cần tái thiết kế thay vì tiếp tục bổ sung các biện pháp vá lỗi cục bộ như thế nào?
Anh/chị chứng minh với lãnh đạo rằng các nguyên tắc secure design đang giảm rủi ro thực tế chứ không chỉ được ghi trong tiêu chuẩn ra sao?

Bạn giải thích nguyên tắc tổ chức hệ thống quanh các năng lực nghiệp vụ trong SOA thay vì chia dịch vụ theo lớp kỹ thuật như thế nào?
Bạn xác định ranh giới của một service từ các nghiệp vụ có dữ liệu và quy tắc liên quan mật thiết ra sao?
Bạn phân biệt service có khả năng tự chủ với module dùng chung trong ứng dụng đơn khối theo những dấu hiệu nào?
Bạn lựa chọn độ hạt dịch vụ như thế nào để tránh một service quá lớn hoặc một tập dịch vụ quá nhỏ phải gọi nhau liên tục?
Bạn phân biệt SOA với microservices qua mục tiêu thiết kế, cách quản trị và mô hình triển khai như thế nào?
Bạn mô tả vai trò của service provider, service consumer và service contract trong một luồng tích hợp như thế nào?
Bạn xác định những cam kết nào về dữ liệu, lỗi, thời gian đáp ứng và khả năng tương thích cần xuất hiện trong service contract?
Bạn thiết kế hợp đồng dịch vụ dựa trên ngôn ngữ nghiệp vụ để không làm lộ mô hình lưu trữ của provider như thế nào?
Bạn phân biệt loose coupling với việc chỉ tách mã thành hai ứng dụng giao tiếp qua mạng ra sao?
Bạn nhận diện sự phụ thuộc ngầm giữa các dịch vụ khi một thay đổi nhỏ buộc nhiều consumer triển khai đồng thời như thế nào?
Bạn thiết kế cấu trúc request và response để consumer không phải hiểu chi tiết xử lý nội bộ của service như thế nào?
Bạn lựa chọn SOAP hay REST cho một kịch bản tích hợp dựa trên yêu cầu hợp đồng, hệ sinh thái và khả năng vận hành ra sao?
Bạn giải thích vai trò của WSDL và schema trong việc mô tả hợp đồng SOAP và kiểm tra khả năng tương thích như thế nào?
Bạn lựa chọn tài nguyên và phương thức HTTP trong REST theo các thao tác nghiệp vụ nhưng vẫn giữ ngữ nghĩa nhất quán ra sao?
Bạn xác định mã trạng thái HTTP và cấu trúc lỗi REST để consumer phân biệt lỗi dữ liệu, quyền hạn và lỗi tạm thời như thế nào?
Bạn thiết kế SOAP Fault để consumer xử lý lỗi có cấu trúc thay vì phải phân tích thông điệp văn bản như thế nào?
Bạn xử lý sự khác biệt về kiểu dữ liệu, thời gian và giá trị null giữa hai hệ thống khi trao đổi qua service contract ra sao?
Bạn thiết kế schema thông điệp dùng chung vừa nhất quán vừa không trở thành mô hình quá lớn ràng buộc mọi dịch vụ như thế nào?
Bạn lựa chọn cách xác thực và phân quyền giữa các service khi mỗi consumer có quyền sử dụng nghiệp vụ khác nhau ra sao?
Bạn bảo vệ giao tiếp dịch vụ bằng mã hóa đường truyền, quản lý danh tính và phân quyền tối thiểu như thế nào?
Bạn xác định những dữ liệu nhạy cảm nào không được đưa vào hợp đồng chung, log và hệ thống trung gian ra sao?
Bạn thiết kế chính sách timeout để một dịch vụ chậm không kéo dài vô hạn chuỗi lời gọi liên dịch vụ như thế nào?
Bạn xây dựng quy tắc retry cho lỗi mạng mà không khiến các yêu cầu có tác dụng phụ bị xử lý hai lần ra sao?
Bạn thiết kế idempotency key hoặc định danh giao dịch khi consumer không biết chắc provider đã xử lý request hay chưa như thế nào?
Bạn phân biệt orchestration và choreography khi nhiều dịch vụ cùng tham gia một quy trình nghiệp vụ như thế nào?
Bạn lựa chọn orchestration cho quy trình phê duyệt nhiều bước dựa trên nhu cầu quan sát và điều khiển tập trung ra sao?
Bạn thiết kế luồng choreography bằng các sự kiện nghiệp vụ mà không tạo vòng phụ thuộc giữa nhiều dịch vụ như thế nào?
Bạn nhận diện nguy cơ một orchestrator biến thành nơi chứa toàn bộ quy tắc nghiệp vụ của nhiều service như thế nào?
Bạn xử lý tình huống một bước của quy trình đa dịch vụ thành công nhưng bước sau thất bại bằng các hành động bù trừ ra sao?
Bạn xác định ranh giới transaction và dữ liệu thuộc quyền sở hữu của từng service để tránh ghi trực tiếp vào database của nhau như thế nào?
Bạn lựa chọn giao tiếp đồng bộ hay bất đồng bộ giữa các dịch vụ dựa trên yêu cầu phản hồi, độ bền và khả năng chịu lỗi ra sao?
Bạn thiết kế thông điệp sự kiện để consumer có đủ ngữ cảnh thực hiện nghiệp vụ nhưng không bị buộc dùng mô hình nội bộ của producer như thế nào?
Bạn xử lý việc message bị gửi lại hoặc đến sai thứ tự trong một quy trình phối hợp các service ra sao?
Bạn dựa trên những tiêu chí nào để quyết định dùng ESB cho chuyển đổi giao thức, định tuyến và tích hợp hệ thống kế thừa?
Bạn nhận diện dấu hiệu ESB đang tập trung quá nhiều logic nghiệp vụ và trở thành nút thắt thay đổi của toàn hệ thống ra sao?
Bạn phân biệt service registry hoặc discovery với hệ thống quản lý hợp đồng dịch vụ về nhiệm vụ và giá trị như thế nào?
Bạn thiết kế cơ chế định tuyến giữa các phiên bản service mà không bắt buộc mọi consumer cập nhật cùng lúc ra sao?
Bạn đặt quy tắc tương thích ngược khi thêm trường, đổi tên trường hoặc thay đổi ý nghĩa dữ liệu trong service contract như thế nào?
Bạn lập chiến lược loại bỏ một API cũ bằng thời gian thông báo, theo dõi người dùng và cơ chế chuyển đổi ra sao?
Bạn kiểm chứng hợp đồng SOAP hoặc REST giữa provider và nhiều consumer mà không cần chạy toàn bộ hệ thống như thế nào?
Bạn thiết kế contract test để phát hiện provider vô tình bỏ trường hoặc thay đổi mã lỗi đang được consumer sử dụng ra sao?
Bạn phân biệt kiểm thử hợp đồng với kiểm thử integration toàn luồng khi một dịch vụ phụ thuộc nhiều đối tác như thế nào?
Bạn tổ chức triển khai và rollback phiên bản dịch vụ mới để hạn chế rủi ro cho những consumer chưa được nâng cấp ra sao?
Bạn xây dựng quy trình quản trị service contract với người sở hữu, quy trình review và lịch sử thay đổi như thế nào?
Bạn lựa chọn những tiêu chuẩn dùng chung cho tên lỗi, định danh tương quan và thời gian mà không kìm hãm quyền tự chủ của service ra sao?
Bạn xây dựng tài liệu dịch vụ để một nhóm bên ngoài hiểu quyền truy cập, dữ liệu và giới hạn gọi mà không đọc mã nguồn như thế nào?
Bạn thiết kế cơ chế kiểm soát hạn mức và giới hạn tải khi nhiều consumer cùng gọi một service trọng yếu ra sao?
Bạn thu thập metric về latency, error rate và throughput theo từng consumer để đánh giá khả năng đáp ứng cam kết dịch vụ như thế nào?
Bạn truyền correlation ID qua chuỗi lời gọi SOAP, REST và thông điệp bất đồng bộ để truy vết một giao dịch như thế nào?
Bạn xử lý sự cố khi một provider ngừng hoạt động để consumer có thể suy giảm chức năng thay vì ngừng toàn bộ hệ thống ra sao?
Bạn phân biệt lỗi hợp đồng dịch vụ, lỗi tích hợp và lỗi nghiệp vụ từ bằng chứng log và trace như thế nào?
Bạn thiết kế cơ chế kiểm toán ai đã gọi dịch vụ và yêu cầu nào đã thay đổi dữ liệu quan trọng ra sao?
Bạn lập kế hoạch đưa một hệ thống kế thừa vào SOA thông qua lớp tích hợp mà không buộc sửa toàn bộ mô hình dữ liệu của nó như thế nào?
Bạn đánh giá chi phí vận hành, phụ thuộc tổ chức và lợi ích tái sử dụng trước khi tách một năng lực nghiệp vụ thành service riêng ra sao?
Bạn chọn các chỉ số nào để chứng minh SOA đã cải thiện khả năng thay đổi hợp đồng, tích hợp và độ tin cậy thay vì chỉ tăng số dịch vụ?

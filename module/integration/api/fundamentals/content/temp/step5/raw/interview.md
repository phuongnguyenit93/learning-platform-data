Bạn hiểu API như một hợp đồng giao tiếp giữa các hệ thống như thế nào và hợp đồng đó cần mô tả những điều gì?
Vì sao việc xác định người tiêu thụ API và mục tiêu tích hợp nên diễn ra trước khi thiết kế endpoint?
Bạn sẽ phân tích yêu cầu nghiệp vụ thành các khả năng API có ranh giới rõ ràng như thế nào?
Khi nào nên thiết kế API hướng tài nguyên và khi nào nên cân nhắc API hướng hành động?
Bạn đánh giá những đánh đổi nào khi chọn REST, RPC hoặc GraphQL cho một nhu cầu tích hợp?
Một API công khai và một API nội bộ thường khác nhau ở các yêu cầu thiết kế nào?
Bạn phân biệt hợp đồng API với cách hiện thực nghiệp vụ bên trong dịch vụ như thế nào?
Một API cần che giấu những chi tiết triển khai nào để các hệ thống có thể phát triển độc lập?
Bạn sẽ xác định quyền sở hữu dữ liệu và trách nhiệm của từng hệ thống tại ranh giới API ra sao?
Trong những trường hợp nào giao tiếp request-response đồng bộ phù hợp với luồng nghiệp vụ?
Khi nào mô hình request-response trở thành điểm nghẽn và cần cân nhắc cách tích hợp khác?
Bạn mô tả vòng đời một request từ ứng dụng gọi đến API và nhận response như thế nào?
Bạn xác định điều kiện thành công của một lời gọi API dựa trên kỹ thuật và nghiệp vụ ra sao?
Bạn sẽ thiết kế hợp đồng cho một thao tác có thể hoàn thành bất đồng bộ như thế nào?
Khi một API được nhiều nhóm sử dụng, bạn thu thập và ưu tiên yêu cầu của các nhóm ra sao?
Bạn quyết định mức độ chi tiết của một API dựa trên chi phí gọi mạng và tính dễ sử dụng như thế nào?
Bạn nhận diện các phụ thuộc không mong muốn giữa client và server từ một hợp đồng API bằng cách nào?
Những nguyên tắc nào giúp tên tài nguyên và đường dẫn API dễ hiểu, nhất quán và ổn định?
Bạn sẽ phân biệt định danh tài nguyên với vị trí hay cách lưu trữ dữ liệu của tài nguyên như thế nào?
Bạn chọn cấu trúc URI cho tài nguyên lồng nhau dựa trên mối quan hệ nghiệp vụ nào?
Bạn sẽ thiết kế thao tác tìm kiếm tài nguyên khi tiêu chí lọc rất phức tạp như thế nào?
Ý nghĩa của GET, POST, PUT, PATCH và DELETE ảnh hưởng thế nào đến thiết kế API?
Bạn phân biệt tính an toàn và tính idempotent của HTTP method khi thiết kế chức năng thay đổi dữ liệu như thế nào?
Bạn chọn PUT hay PATCH cho cập nhật một phần hoặc toàn bộ tài nguyên dựa trên tiêu chí nào?
Bạn sẽ xử lý tình huống client gửi lại cùng một POST sau khi mất response như thế nào?
Bạn quyết định đặt dữ liệu trong path, query string, header hay request body theo nguyên tắc nào?
Bạn sẽ tổ chức query parameters để hỗ trợ lọc, sắp xếp và phân trang nhất quán như thế nào?
Bạn phân tích sự khác biệt giữa offset pagination và cursor pagination trong một tập dữ liệu liên tục thay đổi ra sao?
Bạn thiết kế liên kết hoặc token cho trang tiếp theo mà không làm lộ chi tiết lưu trữ như thế nào?
Bạn sẽ chọn mã trạng thái HTTP cho thao tác tạo tài nguyên thành công theo những yếu tố nào?
Bạn phân biệt các tình huống nên trả 200, 201, 202 và 204 như thế nào?
Bạn dùng các mã trạng thái 400, 401, 403 và 404 để phản ánh lỗi của client như thế nào?
Bạn phân biệt xung đột trạng thái tài nguyên với lỗi dữ liệu không hợp lệ ra sao?
Trong tình huống nào một API nên trả 429 và client cần nhận thêm thông tin gì?
Bạn xử lý các mã lỗi 5xx như thế nào để phản ánh trách nhiệm của server mà vẫn hỗ trợ khắc phục sự cố?
Bạn thiết kế redirect trong API như thế nào để tránh làm mất phương thức hoặc nội dung request ngoài ý muốn?
HTTP headers giúp thể hiện ngữ cảnh và metadata của request-response theo những cách nào?
Bạn lựa chọn Content-Type và Accept như thế nào khi API hỗ trợ nhiều định dạng biểu diễn?
Content negotiation ảnh hưởng thế nào đến tương thích giữa các client sử dụng phiên bản và định dạng khác nhau?
Bạn sẽ xử lý một request gửi Content-Type hoặc Accept không được hỗ trợ như thế nào?
Bạn cân nhắc dùng JSON, XML hoặc Protocol Buffers cho dữ liệu trao đổi dựa trên tiêu chí nào?
Bạn thiết kế cấu trúc JSON để client dễ đọc, dễ xác thực và dễ mở rộng như thế nào?
Bạn lựa chọn kiểu dữ liệu và quy tắc đặt tên trường trong payload dựa trên yêu cầu liên thông nào?
Bạn phân biệt trường vắng mặt, trường null và trường có giá trị mặc định trong hợp đồng API ra sao?
Bạn sẽ biểu diễn ngày giờ và múi giờ như thế nào để tránh hiểu sai giữa các hệ thống?
Bạn xử lý độ chính xác của số tiền và các giá trị thập phân khi trao đổi dữ liệu như thế nào?
Bạn sẽ thiết kế enum trong API để client cũ không bị lỗi khi xuất hiện giá trị mới như thế nào?
Bạn dùng mã định danh, mã nghiệp vụ và tên hiển thị trong payload theo các mục đích nào?
Bạn sẽ biểu diễn quan hệ giữa các tài nguyên mà không khiến response trở nên quá lớn như thế nào?
Bạn quyết định nhúng dữ liệu liên quan hay chỉ trả về tham chiếu dựa trên yêu cầu nào?
Bạn quản lý quy tắc chuẩn hóa chuỗi, Unicode và ngôn ngữ trong dữ liệu trao đổi như thế nào?
Bạn thiết kế payload cho thao tác nhập danh sách lớn để kiểm soát kích thước và xử lý lỗi như thế nào?
Bạn kiểm tra dữ liệu đầu vào ở ranh giới API bằng những loại quy tắc nào?
Bạn phân chia trách nhiệm xác thực cấu trúc dữ liệu và xác thực quy tắc nghiệp vụ ra sao?
Bạn sẽ thiết kế thông điệp lỗi xác thực để client biết chính xác trường nào cần sửa như thế nào?
Bạn xử lý các trường không được nhận diện trong request sao cho vừa chặt chẽ vừa dễ mở rộng như thế nào?
Khi một trường mang thông tin nhạy cảm, bạn quyết định có đưa nó vào response hoặc log dựa trên yếu tố nào?
Bạn xây dựng tài liệu ví dụ request-response để giảm khả năng hiểu sai hợp đồng như thế nào?
Bạn xác định những trường bắt buộc và tùy chọn trong API dựa trên kịch bản sử dụng nào?
Bạn cân nhắc tính ổn định của cấu trúc response khi nhu cầu giao diện thay đổi thường xuyên ra sao?
Một mô hình lỗi thống nhất cho toàn bộ API nên truyền đạt những thông tin gì cho client?
Bạn sẽ tách mã lỗi có thể xử lý bằng chương trình khỏi thông điệp dễ đọc cho con người như thế nào?
Bạn quyết định khi nào trả lỗi tổng quát và khi nào trả chi tiết lỗi theo từng trường như thế nào?
Bạn thiết kế phản hồi lỗi khi một thao tác hàng loạt chỉ thành công một phần ra sao?
Bạn phân biệt lỗi do người dùng, lỗi trạng thái nghiệp vụ và lỗi hạ tầng trong hợp đồng API như thế nào?
Bạn sẽ giữ ổn định ý nghĩa của mã lỗi như thế nào khi server thay đổi cách hiện thực?
Bạn thiết kế thông tin tương quan request trong response lỗi để hỗ trợ điều tra sự cố ra sao?
Khi một API phụ thuộc dịch vụ khác gặp lỗi, bạn quyết định ánh xạ lỗi của dịch vụ đó về client như thế nào?
Bạn làm gì để ngăn thông báo lỗi tiết lộ cấu trúc hệ thống hoặc dữ liệu nhạy cảm?
Bạn giúp client xác định lỗi có thể thử lại hay phải thay đổi request bằng những tín hiệu nào?
Bạn xác định thế nào là một thay đổi phá vỡ tương thích đối với API đang có người sử dụng?
Những thay đổi nào ở field, kiểu dữ liệu hoặc ngữ nghĩa có thể gây lỗi dù endpoint và status code không đổi?
Bạn phân biệt tương thích ngược với tương thích tiến trong giao tiếp giữa client và server như thế nào?
Bạn sẽ bổ sung một trường response mới mà vẫn hạn chế rủi ro cho các client cũ như thế nào?
Bạn xử lý việc đổi tên hoặc xóa một trường đang được sử dụng bởi nhiều client như thế nào?
Bạn chọn cách quản lý phiên bản API qua URI, header hay cơ chế khác dựa trên các đánh đổi nào?
Bạn quyết định khi nào cần tạo phiên bản API mới thay vì mở rộng hợp đồng hiện tại như thế nào?
Bạn tổ chức giai đoạn deprecation và sunset của một API để các bên tích hợp có thời gian chuyển đổi ra sao?
Bạn thông báo thay đổi hợp đồng và hướng dẫn di chuyển client qua các phiên bản như thế nào?
Bạn đo lường mức sử dụng từng endpoint hoặc phiên bản để quyết định thời điểm ngừng hỗ trợ như thế nào?
Bạn thiết kế API theo hướng additive change để hạn chế thay đổi phá vỡ tương thích bằng cách nào?
Bạn sẽ kiểm chứng một thay đổi API trên các client đang sử dụng trước khi triển khai như thế nào?
Bạn giải quyết thế nào khi client cũ và client mới cần hai cách diễn giải dữ liệu khác nhau?
Bạn xác định đâu là nguồn sự thật của một hợp đồng API trong quá trình phát triển như thế nào?
Bạn sẽ dùng tài liệu hợp đồng có cấu trúc như OpenAPI vào thiết kế và phối hợp giữa các nhóm ra sao?
Bạn phân biệt authentication và authorization khi kiểm soát truy cập API như thế nào?
Bạn sẽ chọn hình thức xác thực API key, token hay xác thực hai chiều dựa trên bối cảnh nào?
Bạn thiết kế cơ chế cấp và kiểm tra quyền truy cập theo tài nguyên, người dùng và thao tác như thế nào?
Bạn sẽ kiểm tra quyền đối với từng đối tượng dữ liệu để tránh truy cập chéo tài khoản ra sao?
Bạn xử lý token hết hạn hoặc bị thu hồi sao cho client có thể khôi phục luồng làm việc như thế nào?
HTTPS và TLS bảo vệ giao tiếp API ở các tầng nào và còn những rủi ro gì cần xem xét?
Bạn quyết định dữ liệu nào cần mã hóa hoặc hạn chế lưu trữ ngoài việc bảo vệ kết nối như thế nào?
Bạn sẽ quản lý thông tin bí mật của client mà không đưa credential vào URL, mã nguồn hay log như thế nào?
Bạn phân biệt xác thực danh tính người dùng với xác thực danh tính dịch vụ trong các luồng tích hợp ra sao?
Bạn thiết kế cơ chế chống gọi API quá mức để bảo vệ hạ tầng mà vẫn công bằng giữa các client như thế nào?
Bạn xác định giới hạn rate limit và quota dựa trên năng lực hệ thống và nhu cầu người dùng ra sao?
Bạn sẽ cung cấp thông tin cho client để điều chỉnh tốc độ gọi khi bị rate limit như thế nào?
Bạn xử lý CORS như thế nào khi API được gọi từ ứng dụng chạy trên trình duyệt?
Bạn đánh giá nguy cơ injection, mass assignment và rò rỉ dữ liệu nhạy cảm ngay từ thiết kế API như thế nào?
Bạn thiết kế audit log cho các thao tác nhạy cảm mà vẫn bảo vệ quyền riêng tư của người dùng ra sao?
Bạn đặt giới hạn cho kích thước request, độ sâu JSON và thời gian xử lý để tránh lạm dụng tài nguyên như thế nào?
Bạn lựa chọn timeout ở client, gateway và server dựa trên đặc điểm một request như thế nào?
Bạn thiết kế retry cho client API sao cho không gây lặp hành động nghiệp vụ như thế nào?
Bạn quyết định khi nào một thao tác cần idempotency key và sẽ quản lý vòng đời khóa đó ra sao?
Bạn sử dụng backoff và jitter thế nào khi nhiều client đồng thời gặp lỗi tạm thời?
Bạn xác định giới hạn số lần retry và ngân sách thời gian để tránh khuếch đại sự cố như thế nào?
Bạn sẽ thiết kế cơ chế circuit breaker hoặc giảm tải khi API phụ thuộc hệ thống không ổn định ra sao?
Bạn phân biệt lỗi mạng, timeout và lỗi nghiệp vụ khi quyết định hành vi của client như thế nào?
Bạn duy trì tính nhất quán giữa các hệ thống khi một chuỗi request chỉ hoàn thành một phần bằng cách nào?
Bạn quản lý kết quả của một thao tác bất đồng bộ để client có thể hỏi trạng thái hoặc nhận thông báo như thế nào?
Bạn đánh giá những rủi ro nào khi thực hiện một giao dịch nghiệp vụ bằng nhiều lời gọi API?
Bạn sẽ thiết kế một API để chịu được request trùng lặp do client hoặc hạ tầng gửi lại như thế nào?
Bạn phân bổ giới hạn thời gian cho các lời gọi hạ nguồn khi server tổng hợp dữ liệu từ nhiều dịch vụ ra sao?
Bạn cân nhắc việc dùng caching cho API dựa trên tính cập nhật và mức độ nhạy cảm của dữ liệu như thế nào?
Bạn lựa chọn Cache-Control, ETag hoặc Last-Modified để giảm tải và duy trì tính đúng đắn ra sao?
Bạn sẽ tránh trả dữ liệu cache của người dùng này cho người dùng khác bằng cách nào?
Bạn thiết kế conditional request để tránh ghi đè cập nhật đồng thời như thế nào?
Bạn phát hiện và giải quyết mất cập nhật khi nhiều client cùng sửa một tài nguyên ra sao?
Bạn sẽ xác định kích thước payload và số request tối ưu trong một luồng tích hợp bằng cách nào?
Bạn phân tích nguyên nhân p95 hoặc p99 latency cao dù thời gian phản hồi trung bình vẫn thấp như thế nào?
Bạn cân nhắc nén response và chi phí xử lý CPU khi truyền payload lớn ra sao?
Bạn thiết kế chiến lược phân trang và lọc để giảm tải cơ sở dữ liệu dưới lưu lượng cao như thế nào?
Bạn sẽ theo dõi những chỉ số nào để đánh giá độ tin cậy, hiệu năng và mức sử dụng API?
Bạn truyền request ID hoặc trace context qua các dịch vụ để quan sát một yêu cầu đầu cuối như thế nào?
Bạn sẽ ghi log đủ phục vụ chẩn đoán mà không làm lộ token hoặc dữ liệu cá nhân ra sao?
Bạn thiết kế SLA hoặc SLO cho một API dựa trên nhu cầu tích hợp và tác động nghiệp vụ như thế nào?
Bạn kiểm thử hợp đồng API như thế nào để xác minh cấu trúc request, response và mã lỗi?
Bạn sẽ xây dựng kiểm thử tích hợp để phát hiện sai lệch giữa tài liệu API và triển khai thực tế ra sao?
Bạn kiểm thử cả trường hợp thành công, lỗi dữ liệu, thiếu quyền và phụ thuộc hạ nguồn lỗi như thế nào?
Bạn tạo môi trường sandbox và dữ liệu mẫu thế nào để nhóm khác có thể thử tích hợp an toàn?
Bạn sẽ sử dụng mock API ra sao để các nhóm client và server có thể phát triển song song?
Bạn kiểm tra khả năng tương thích khi triển khai phiên bản server mới cùng các client cũ như thế nào?
Bạn xác định trường hợp kiểm thử tải quan trọng cho một API có nhiều kiểu client ra sao?
Bạn tổ chức quy trình review thiết kế API để phát hiện vấn đề trước khi các bên triển khai như thế nào?
Bạn xây dựng quy ước nhất quán về đặt tên, pagination, lỗi và bảo mật giữa nhiều API như thế nào?
Nếu một đối tác báo cùng request đôi khi tạo hai đơn hàng, bạn sẽ điều tra và sửa hợp đồng hoặc cơ chế xử lý như thế nào?
Nếu một API phải cung cấp dữ liệu thời gian thực nhưng client thường xuyên mất mạng, bạn sẽ thiết kế cách lấy lại trạng thái như thế nào?
Nếu ứng dụng di động nhiều phiên bản vẫn gọi cùng API, bạn sẽ lên kế hoạch thay đổi dữ liệu response và ngừng hỗ trợ như thế nào?
Nếu một hệ thống tích hợp chịu lưu lượng tăng đột biến trong giờ cao điểm, bạn sẽ ưu tiên các biện pháp bảo vệ và tối ưu API nào?
Nếu một API trả lỗi 500 cho mọi trường hợp thất bại, bạn sẽ thiết kế lại cách phân loại và truyền lỗi như thế nào?
Nếu phải tích hợp một dịch vụ bên ngoài có giới hạn tốc độ, thời gian phản hồi không ổn định và hợp đồng hay thay đổi, bạn sẽ xây dựng lớp API trung gian như thế nào?

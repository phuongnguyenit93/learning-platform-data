Bạn giải thích Model Context Protocol giải quyết vấn đề gì khi tích hợp ứng dụng AI với các hệ thống bên ngoài như thế nào?
Bạn phân biệt vai trò của MCP host, MCP client và MCP server trong một luồng sử dụng công cụ ra sao?
Bạn sẽ xác định ranh giới trách nhiệm giữa ứng dụng Spring Boot và MCP server dựa trên yêu cầu nghiệp vụ như thế nào?
Bạn so sánh tích hợp qua MCP với việc tự xây dựng một adapter HTTP riêng cho từng công cụ như thế nào?
Bạn phân tích những lợi ích và đánh đổi khi đưa hợp đồng MCP vào kiến trúc nhiều ứng dụng AI như thế nào?
Bạn giải thích vì sao MCP không đồng nghĩa với một model hay một cơ chế gọi LLM cụ thể như thế nào?
Bạn sẽ lựa chọn khi nào nên dùng MCP thay vì gọi trực tiếp service Java từ cùng một ứng dụng ra sao?
Bạn mô tả vòng đời một yêu cầu từ ChatClient qua MCP client tới MCP server rồi trả kết quả như thế nào?
Bạn phân biệt phần suy luận của mô hình với phần thực thi hành động trong hệ thống khi dùng MCP như thế nào?
Bạn sẽ thiết kế các ranh giới tin cậy trong một kiến trúc có model, MCP client và nhiều MCP server ra sao?
Bạn xác định tiêu chí để tách một chức năng thành MCP server độc lập thay vì để trong backend hiện tại như thế nào?
Bạn so sánh ưu và nhược điểm của MCP server dùng chung với MCP server riêng theo miền nghiệp vụ như thế nào?
Bạn sẽ xây dựng sơ đồ phụ thuộc giữa ứng dụng AI, các MCP server và hệ thống dữ liệu gốc ra sao?
Bạn đánh giá những rủi ro vận hành phát sinh khi tăng số lượng MCP server tích hợp vào một host như thế nào?
Bạn sẽ định nghĩa tiêu chí thành công cho một tính năng MCP về chất lượng, độ trễ, an toàn và chi phí ra sao?
Bạn phân biệt khái niệm capability negotiation với danh sách tool hiện có trong một phiên MCP như thế nào?
Bạn mô tả các bước thiết lập phiên và khởi tạo giao thức giữa MCP client với server ra sao?
Bạn sẽ kiểm tra sự tương thích về phiên bản giao thức giữa một MCP client và MCP server như thế nào?
Bạn xác định cách xử lý khi server không công bố một capability mà ứng dụng cần như thế nào?
Bạn phân biệt lỗi khởi tạo phiên với lỗi thực thi một lời gọi tool sau khi phiên đã sẵn sàng ra sao?
Bạn sẽ quyết định khi nào client cần làm mới khả năng khám phá của một MCP server như thế nào?
Bạn giải thích cách MCP sử dụng thông điệp request, response và notification theo từng tình huống ra sao?
Bạn phân biệt một thông điệp JSON-RPC lỗi giao thức với kết quả tool báo lỗi nghiệp vụ như thế nào?
Bạn sẽ quản lý định danh request để liên hệ phản hồi khi có nhiều thao tác MCP đồng thời ra sao?
Bạn mô tả ảnh hưởng của timeout hoặc ngắt kết nối tới các request MCP đang chờ kết quả như thế nào?
Bạn phân biệt việc hủy một request ở phía client với bảo đảm tác vụ server đã dừng thực thi ra sao?
Bạn sẽ xây dựng quy tắc cho client khi một notification đến giữa các lời gọi tool như thế nào?
Bạn phân tích tác động của việc một server cung cấp capability mới sau khi ứng dụng đã khởi động như thế nào?
Bạn kiểm tra hợp đồng MCP có được mô tả đúng nhưng hành vi server lại không tương thích bằng cách nào?
Bạn sẽ tổ chức quản lý phiên để không dùng nhầm ngữ cảnh hoặc kết nối của người dùng khác như thế nào?
Bạn phân biệt tool, resource và prompt trong MCP dựa trên trách nhiệm và cách client sử dụng như thế nào?
Bạn sẽ quyết định một chức năng nên được công bố dưới dạng tool thay vì resource theo tiêu chí nào?
Bạn xác định khi nào một đoạn hướng dẫn nên được cung cấp dưới dạng prompt thay vì tool như thế nào?
Bạn giải thích vì sao mô tả tool có thể ảnh hưởng tới quyết định lựa chọn hành động của model ra sao?
Bạn sẽ thiết kế một bộ khả năng MCP nhỏ, rõ ràng thay vì công bố quá nhiều tool chồng chéo như thế nào?
Bạn xây dựng quy ước đặt tên tool để tránh xung đột giữa nhiều MCP server như thế nào?
Bạn thiết kế phần mô tả tool để mô hình hiểu mục đích và giới hạn sử dụng như thế nào?
Bạn phân tích rủi ro khi mô tả tool hứa hẹn khả năng mà implementation không thực sự cung cấp như thế nào?
Bạn sẽ phân biệt tool đọc dữ liệu với tool có tác dụng phụ để áp dụng mức kiểm soát khác nhau ra sao?
Bạn giải thích vai trò của input schema khi công bố một tool qua MCP như thế nào?
Bạn sẽ thiết kế JSON schema cho tham số tool gồm kiểu dữ liệu, trường bắt buộc và các giới hạn ra sao?
Bạn xử lý tham số tùy chọn, giá trị mặc định và null trong đầu vào tool như thế nào?
Bạn xây dựng bước xác thực dữ liệu đầu vào sau khi schema validation thành công ra sao?
Bạn phân biệt kiểm tra cú pháp đầu vào với kiểm tra quyền và quy tắc nghiệp vụ của tool như thế nào?
Bạn sẽ xử lý trường enum chưa biết hoặc định dạng ngày không hợp lệ khi model đề xuất gọi tool ra sao?
Bạn thiết kế kết quả trả về của tool để client dễ diễn giải mà không phải đoán cấu trúc như thế nào?
Bạn phân biệt nội dung văn bản, dữ liệu có cấu trúc và nội dung đa phương thức trong phản hồi tool như thế nào?
Bạn sẽ kiểm soát kích thước kết quả tool để tránh làm tràn context window của model ra sao?
Bạn quyết định khi nào tool nên trả bản tóm tắt và khi nào nên cung cấp dữ liệu chi tiết qua resource như thế nào?
Bạn mô tả cách công bố và khám phá danh sách tool của một MCP server như thế nào?
Bạn sẽ xử lý việc tên tool hoặc schema thay đổi khi client cũ vẫn đang kết nối ra sao?
Bạn đánh giá mức độ tương thích khi thêm tham số mới vào hợp đồng gọi tool như thế nào?
Bạn thiết kế phiên bản tool để không gây nhầm lẫn giữa nhiều implementation đang hoạt động như thế nào?
Bạn quyết định cách loại bỏ một tool cũ khỏi danh sách khả dụng theo lộ trình nào?
Bạn sẽ kiểm tra kết quả tool trước khi cho model dùng làm căn cứ cho câu trả lời ra sao?
Bạn phân biệt tool gọi thành công về mặt giao thức với tool trả dữ liệu không đáp ứng yêu cầu nghiệp vụ như thế nào?
Bạn xây dựng quy tắc phát hiện và xử lý một tool trả quá nhiều kết quả hoặc kết quả trùng như thế nào?
Bạn giải thích cơ chế resource trong MCP giúp ứng dụng truy cập ngữ cảnh bên ngoài như thế nào?
Bạn sẽ thiết kế URI của resource để phân biệt tài liệu và thực thể trong các miền nghiệp vụ khác nhau ra sao?
Bạn phân biệt resource tĩnh với resource được sinh động theo yêu cầu như thế nào?
Bạn đánh giá những trường hợp nên khai báo resource template thay vì liệt kê mọi resource cụ thể ra sao?
Bạn thiết kế tham số và quy tắc kiểm tra URI khi ứng dụng truy cập resource template như thế nào?
Bạn sẽ ngăn resource URI dẫn đến dữ liệu ngoài phạm vi được phép của người dùng ra sao?
Bạn phân biệt quyền xem resource với quyền gọi tool tác động lên cùng đối tượng như thế nào?
Bạn xác định cách biểu diễn MIME type và encoding của resource trong một phản hồi MCP ra sao?
Bạn sẽ xử lý resource có nội dung nhị phân hoặc kích thước lớn trước khi đưa vào prompt như thế nào?
Bạn thiết kế cache resource theo người dùng và phiên để tránh rò rỉ dữ liệu giữa các tenant như thế nào?
Bạn phân tích rủi ro khi một resource đã được cache nhưng quyền truy cập của người dùng bị thu hồi như thế nào?
Bạn sẽ đánh giá tính mới của resource khi dữ liệu nguồn thay đổi liên tục ra sao?
Bạn lựa chọn cơ chế tải lại resource thay vì dùng bản cũ theo yêu cầu nghiệp vụ nào?
Bạn giải thích vai trò của thông báo thay đổi resource nếu server có hỗ trợ khả năng này như thế nào?
Bạn xử lý resource tạm thời không tồn tại hoặc đã bị xóa sau khi được khám phá như thế nào?
Bạn sẽ tổ chức danh mục resource để mô hình không bị nhiễu bởi dữ liệu không liên quan như thế nào?
Bạn phân biệt dữ liệu của resource với chỉ dẫn có quyền ưu tiên cao của ứng dụng ra sao?
Bạn đánh giá nguy cơ prompt injection khi resource chứa văn bản mang tính chỉ dẫn như thế nào?
Bạn thiết kế bước trích lọc thông tin resource trước khi đưa vào ChatClient như thế nào?
Bạn sẽ bảo toàn thông tin nguồn gốc resource để người dùng có thể kiểm chứng câu trả lời ra sao?
Bạn giải thích mục đích của prompt capability trong MCP và các trường hợp sử dụng phù hợp như thế nào?
Bạn sẽ thiết kế một prompt được công bố bởi MCP server để nhận tham số từ client ra sao?
Bạn phân biệt prompt template do server công bố với system instruction do ứng dụng sở hữu như thế nào?
Bạn quyết định khi nào cho phép người dùng lựa chọn prompt và khi nào ứng dụng chọn tự động như thế nào?
Bạn sẽ kiểm tra tính hợp lệ của tham số trước khi yêu cầu nội dung prompt từ server ra sao?
Bạn phân tích rủi ro khi một prompt từ server ngoài xung đột với chính sách của host như thế nào?
Bạn thiết kế quy tắc sắp xếp và kết hợp các message từ MCP prompt với hội thoại hiện tại ra sao?
Bạn sẽ quản lý phiên bản prompt được công bố khi nhiều client nâng cấp không đồng thời như thế nào?
Bạn giải thích tại sao công bố prompt không có nghĩa server được phép thực thi các hành động nghiệp vụ ra sao?
Bạn xác định cách theo dõi nguồn gốc của prompt đã ảnh hưởng tới một lời gọi model như thế nào?
Bạn thiết kế fallback khi MCP server không còn cung cấp prompt ứng dụng từng sử dụng ra sao?
Bạn sẽ tránh để nội dung prompt chưa tin cậy trở thành chỉ dẫn hệ thống ngoài kiểm soát như thế nào?
Bạn đánh giá cách kiểm thử prompt MCP với tham số rỗng, sai kiểu và trường hợp biên như thế nào?
Bạn sẽ quyết định dùng transport stdio cho MCP server trong những tình huống triển khai nào?
Bạn mô tả cách client giao tiếp với một MCP server chạy như tiến trình con qua stdio như thế nào?
Bạn phân tích rủi ro khi log chẩn đoán được ghi nhầm vào stdout của giao thức stdio như thế nào?
Bạn sẽ tổ chức vòng đời khởi động và dừng tiến trình MCP server dùng stdio ra sao?
Bạn xác định cơ chế kiểm soát quyền thực thi đối với file nhị phân hoặc lệnh chạy MCP server cục bộ như thế nào?
Bạn so sánh stdio với transport MCP qua HTTP theo mô hình triển khai và vận hành ra sao?
Bạn sẽ lựa chọn Streamable HTTP khi cần truy cập MCP server từ nhiều ứng dụng ở xa như thế nào?
Bạn mô tả cách một MCP client xử lý kết nối HTTP và các luồng phản hồi theo khả năng của server ra sao?
Bạn phân tích các điểm cần cân nhắc khi di chuyển từ một transport MCP cũ sang transport mới như thế nào?
Bạn sẽ thiết kế proxy hoặc gateway cho MCP qua HTTP mà vẫn giữ đúng hành vi streaming ra sao?
Bạn xác định các timeout cần cấu hình tại client, server, reverse proxy và load balancer như thế nào?
Bạn kiểm tra tác động của buffering tại proxy tới các phản hồi MCP được stream như thế nào?
Bạn sẽ xử lý reconnect khi một phiên MCP dùng HTTP bị gián đoạn như thế nào?
Bạn phân biệt khả năng khôi phục kết nối với khả năng phát lại an toàn một tool call chưa rõ kết quả ra sao?
Bạn thiết kế cơ chế đóng kết nối và dọn dẹp tài nguyên khi client không còn sử dụng MCP server như thế nào?
Bạn sẽ quản lý số kết nối và giới hạn request đồng thời cho MCP server qua HTTP ra sao?
Bạn đánh giá ưu nhược điểm của đặt MCP server cùng mạng nội bộ với ứng dụng so với công khai qua Internet như thế nào?
Bạn sẽ kiểm soát endpoint URL và cấu hình transport trong Spring Boot cho từng môi trường ra sao?
Bạn mô tả các thành phần cần có khi tạo một Spring AI MCP Server trong ứng dụng Spring Boot như thế nào?
Bạn sẽ lựa chọn loại MCP server dựa trên transport và mô hình ứng dụng Spring hiện có như thế nào?
Bạn đánh giá việc dùng Spring MVC hoặc Spring WebFlux để phục vụ MCP qua HTTP theo nhu cầu tải ra sao?
Bạn tổ chức lớp khai báo tool và lớp xử lý nghiệp vụ ở phía MCP server như thế nào?
Bạn sẽ biến một phương thức service Java thành một khả năng tool MCP mà không lộ implementation nội bộ ra sao?
Bạn xác định các thông số cần mô tả để MCP server công bố hợp đồng tool cho client như thế nào?
Bạn thiết kế dependency injection cho MCP tool handler khi nó cần repository hoặc service khác ra sao?
Bạn giải thích tại sao logic xác thực và phân quyền không nên phụ thuộc vào mô tả tool cho model như thế nào?
Bạn sẽ tổ chức các resource MCP lấy dữ liệu từ service Java mà vẫn bảo vệ ranh giới nghiệp vụ ra sao?
Bạn thiết kế các prompt MCP có tham số và thông điệp hướng dẫn rõ ràng như thế nào?
Bạn sẽ cấu hình danh sách tool, resource và prompt mà server thực sự cung cấp ra sao?
Bạn phân biệt thông báo lỗi khởi động MCP server với lỗi do một handler tool tạo ra như thế nào?
Bạn đánh giá chi phí bộ nhớ và kết nối khi MCP server phục vụ nhiều client đồng thời như thế nào?
Bạn sẽ thiết kế MCP server stateless hoặc có trạng thái phiên theo điều kiện nào?
Bạn giải thích các rủi ro khi sử dụng mutable state chung giữa nhiều lời gọi tool như thế nào?
Bạn tổ chức shutdown an toàn cho MCP server khi có các lời gọi đang chạy như thế nào?
Bạn sẽ xây dựng health check cho MCP server mà không thực thi các tool có tác dụng phụ như thế nào?
Bạn mô tả quy trình cấu hình một Spring AI MCP Client kết nối tới MCP server như thế nào?
Bạn sẽ lựa chọn cấu hình client đồng bộ hay bất đồng bộ dựa trên loại tác vụ và giới hạn ứng dụng ra sao?
Bạn giải thích cách client khám phá tool từ một MCP server sau khi khởi tạo phiên như thế nào?
Bạn thiết kế một Spring Boot service sử dụng nhiều MCP client tới các server khác nhau như thế nào?
Bạn sẽ quyết định cách xác định danh tính từng MCP server trong cấu hình ứng dụng ra sao?
Bạn phân tích cách cách ly lỗi của một MCP server để không làm gián đoạn tất cả chức năng AI như thế nào?
Bạn tổ chức quản lý vòng đời MCP client trong Spring container để tránh tạo kết nối mới ở mỗi request như thế nào?
Bạn sẽ kiểm soát số client và kết nối khi nhiều người dùng cùng gọi một MCP server ra sao?
Bạn xác định phương án thay đổi danh sách MCP server mà không sửa logic nghiệp vụ ở mọi nơi như thế nào?
Bạn so sánh việc để Spring AI tự tích hợp tool MCP với việc tự chọn một tập tool cho từng ChatClient ra sao?
Bạn mô tả cách đưa các tool khám phá từ MCP client vào cơ chế tool calling của ChatClient như thế nào?
Bạn giải thích vai trò của lớp chuyển đổi MCP tools thành tool callbacks cho model như thế nào?
Bạn phân biệt việc model biết có tool với việc host thực sự cho phép gọi tool đó ra sao?
Bạn sẽ lựa chọn tập MCP tool được công bố cho từng trường hợp sử dụng của ChatClient như thế nào?
Bạn thiết kế luồng để model đề xuất tool call, ứng dụng xác thực và MCP client thực thi như thế nào?
Bạn phân tích cách kết quả từ MCP tool được đưa trở lại ngữ cảnh model để tạo câu trả lời như thế nào?
Bạn sẽ xử lý tình huống model đề xuất gọi tool với tham số không hợp lệ ra sao?
Bạn xác định khi nào cần bước xác nhận của người dùng trước khi ChatClient thực thi một tool có tác dụng phụ như thế nào?
Bạn thiết kế giới hạn số lượt gọi tool trong một câu hỏi để tránh vòng lặp tiêu tốn tài nguyên ra sao?
Bạn sẽ phát hiện trường hợp model gọi cùng một tool lặp đi lặp lại nhưng không tiến triển như thế nào?
Bạn so sánh cách để model chọn tool tự động với định tuyến tool bằng quy tắc nghiệp vụ như thế nào?
Bạn xác định khi nào một thao tác cần được thực hiện trực tiếp bởi Java service thay vì cho model lựa chọn tool ra sao?
Bạn sẽ thiết kế kết quả tool có thể được mô hình hiểu nhưng không vô tình tạo quyền chỉ dẫn cao hơn như thế nào?
Bạn phân biệt lỗi tool tạm thời với một kết quả nghiệp vụ hợp lệ nhưng không có dữ liệu như thế nào?
Bạn quyết định khi nào nên retry tool call và khi nào cần trả lỗi có kiểm soát cho người dùng như thế nào?
Bạn sẽ quản lý thứ tự các tool call phụ thuộc lẫn nhau trong một quy trình AI ra sao?
Bạn đánh giá nguy cơ hai tool call đồng thời cập nhật cùng một đối tượng nghiệp vụ như thế nào?
Bạn xử lý dữ liệu đầu ra quá dài của MCP tool trước khi đưa trở lại model như thế nào?
Bạn sẽ bảo đảm ChatClient không nhận tool nằm ngoài phạm vi quyền của người dùng hiện tại ra sao?
Bạn thiết kế kiểm tra xác thực khi MCP client dùng transport HTTP tới server bên ngoài như thế nào?
Bạn phân biệt xác thực ứng dụng MCP client với ủy quyền thay mặt người dùng cuối ra sao?
Bạn xác định những quyền nào nên cấp cho một MCP server khi nó truy cập cơ sở dữ liệu hoặc API nội bộ như thế nào?
Bạn sẽ áp dụng nguyên tắc quyền tối thiểu cho các tool đọc dữ liệu và tool thay đổi dữ liệu ra sao?
Bạn thiết kế cơ chế ánh xạ danh tính người dùng từ Spring Security đến quyền gọi tool như thế nào?
Bạn phân tích rủi ro khi MCP server tin vào username hoặc role do model tự tạo trong tham số tool như thế nào?
Bạn kiểm tra quyền truy cập tài nguyên theo tenant và đối tượng nghiệp vụ ở bước nào như thế nào?
Bạn sẽ xử lý việc quyền truy cập người dùng bị thu hồi trong lúc phiên MCP vẫn hoạt động ra sao?
Bạn xác định cách kiểm soát truy cập MCP server từ xa dựa trên OAuth hoặc cơ chế token phù hợp như thế nào?
Bạn tổ chức quản lý token, secret và chứng chỉ của MCP client trong các môi trường ra sao?
Bạn sẽ xoay vòng credential của MCP client mà không gây gián đoạn toàn bộ dịch vụ như thế nào?
Bạn phân tích rủi ro khi token của người dùng được chuyển tiếp đến MCP server không đáng tin cậy như thế nào?
Bạn thiết kế kiểm tra nguồn gốc và danh tính của MCP server trước khi thêm vào ứng dụng ra sao?
Bạn sẽ hạn chế rủi ro cài hoặc thực thi một MCP server stdio từ nguồn chưa được kiểm chứng như thế nào?
Bạn xác định các giới hạn filesystem, network và process cho MCP server cục bộ như thế nào?
Bạn thiết kế cơ chế chống path traversal khi tool nhận tham số là đường dẫn hoặc resource URI như thế nào?
Bạn sẽ ngăn tool gọi HTTP tới địa chỉ nội bộ không được phép hoặc metadata endpoint ra sao?
Bạn phân tích nguy cơ command injection khi MCP tool chạy câu lệnh hệ thống từ tham số model cung cấp như thế nào?
Bạn sẽ kiểm tra input và escape dữ liệu đúng ngữ cảnh khi MCP tool tạo câu truy vấn SQL ra sao?
Bạn thiết kế chính sách bảo vệ dữ liệu nhạy cảm trong payload request và response MCP như thế nào?
Bạn sẽ quyết định những trường nào được log khi tool trả dữ liệu cá nhân như thế nào?
Bạn phân biệt prompt injection từ resource, tool result và prompt do server ngoài công bố như thế nào?
Bạn thiết kế quy tắc ngăn nội dung tool result tự ý mở rộng quyền truy cập hoặc thay đổi system instruction như thế nào?
Bạn sẽ xác định cơ chế yêu cầu phê duyệt cho thao tác xóa dữ liệu, gửi email hoặc chuyển tiền qua tool ra sao?
Bạn giải thích vì sao mô tả tool không thể thay thế xác thực và kiểm tra quyền ở backend như thế nào?
Bạn thiết kế giới hạn tốc độ và quota gọi tool theo người dùng, client và server như thế nào?
Bạn sẽ xử lý một tool trả dữ liệu không an toàn để render thành HTML trong giao diện như thế nào?
Bạn đánh giá nguy cơ rò rỉ dữ liệu khi cùng một MCP client dùng cho nhiều tenant như thế nào?
Bạn thiết kế phương án audit cho thao tác MCP ghi dữ liệu để truy vết người gọi và kết quả như thế nào?
Bạn phân biệt timeout kết nối, timeout gọi tool và timeout tổng yêu cầu AI như thế nào?
Bạn sẽ phân bổ ngân sách thời gian giữa ChatClient, MCP client, MCP server và hệ thống hạ nguồn ra sao?
Bạn thiết kế chính sách retry khi lời gọi tool gặp lỗi mạng nhưng có thể đã hoàn tất thao tác như thế nào?
Bạn xác định cách dùng idempotency key cho tool tạo giao dịch nghiệp vụ như thế nào?
Bạn giải thích vì sao retry tool chỉ đọc thường ít rủi ro hơn retry tool có tác dụng phụ như thế nào?
Bạn sẽ thiết kế kết quả khi tool chạy lâu hơn deadline của một yêu cầu AI như thế nào?
Bạn phân biệt lỗi transport MCP với lỗi schema và lỗi nghiệp vụ của tool trong telemetry như thế nào?
Bạn xây dựng cơ chế circuit breaker cho MCP server liên tục lỗi như thế nào?
Bạn sẽ cách ly tài nguyên để một MCP server bị nghẽn không làm hỏng toàn bộ ChatClient ra sao?
Bạn quyết định khi nào trả dữ liệu dự phòng và khi nào cần dừng trả lời do thiếu nguồn đáng tin cậy như thế nào?
Bạn xử lý khi một MCP server mất kết nối giữa chuỗi nhiều tool call phụ thuộc nhau như thế nào?
Bạn sẽ thiết kế rollback hoặc bù trừ cho quy trình sử dụng nhiều tool cập nhật các hệ thống khác nhau ra sao?
Bạn xác định cách kiểm soát số lời gọi đồng thời để tránh quá tải MCP server như thế nào?
Bạn sẽ sử dụng caching cho resource hoặc tool chỉ đọc theo điều kiện tính mới và phân quyền nào?
Bạn đánh giá nguy cơ dùng kết quả cache cũ sau khi tool cập nhật dữ liệu nghiệp vụ như thế nào?
Bạn thiết kế phương án duy trì dịch vụ khi một MCP server được bảo trì hoặc nâng cấp phiên bản ra sao?
Bạn sẽ theo dõi các chỉ số độ trễ, tỷ lệ lỗi và thông lượng của từng MCP tool như thế nào?
Bạn phân biệt thời gian model lựa chọn tool với thời gian MCP client và server thực thi tool ra sao?
Bạn thiết kế distributed tracing từ HTTP request qua ChatClient tới MCP server và backend như thế nào?
Bạn sẽ gắn correlation ID cho các lời gọi MCP liên quan tới một tương tác người dùng như thế nào?
Bạn xác định cách ghi log tham số tool đã được làm sạch để không lộ secret như thế nào?
Bạn xây dựng dashboard phân biệt lỗi khởi tạo phiên, lỗi khám phá tool và lỗi gọi tool ra sao?
Bạn sẽ phát hiện một tool có tỷ lệ validation failure tăng do thay đổi model hoặc prompt như thế nào?
Bạn phân tích tác động của số lần gọi tool đến tổng token usage và chi phí của ứng dụng AI như thế nào?
Bạn sẽ giới hạn lượng dữ liệu resource đưa vào context để bảo vệ chi phí và hiệu năng ra sao?
Bạn xây dựng cảnh báo khi MCP server có thời gian phản hồi tăng đột biến như thế nào?
Bạn thiết kế kịch bản kiểm thử MCP server công bố đúng tên, mô tả và schema của các tool ra sao?
Bạn sẽ viết unit test cho handler tool mà không cần khởi chạy model thật như thế nào?
Bạn kiểm thử input schema của tool với trường thiếu, sai kiểu, giá trị biên và dữ liệu độc hại như thế nào?
Bạn xây dựng integration test cho MCP client kết nối tới server thử nghiệm như thế nào?
Bạn sẽ kiểm tra quy trình khởi tạo phiên và discovery khi server không hỗ trợ một capability như thế nào?
Bạn kiểm thử tool call trả kết quả thành công, lỗi nghiệp vụ và lỗi giao thức như thế nào?
Bạn sẽ mô phỏng server không phản hồi, kết nối bị đóng và request timeout ra sao?
Bạn kiểm thử MCP transport stdio khi tiến trình con thoát bất ngờ hoặc ghi sai dữ liệu lên stdout như thế nào?
Bạn xây dựng kiểm thử cho Streamable HTTP khi proxy buffer luồng hoặc đóng kết nối giữa chừng như thế nào?
Bạn sẽ kiểm thử tương thích phiên bản MCP giữa các client và server triển khai khác thời điểm ra sao?
Bạn kiểm thử ChatClient chọn đúng tool khi nhiều MCP server công bố mô tả gần giống nhau như thế nào?
Bạn xây dựng test để xác nhận ChatClient không gọi một tool chưa được cấp quyền như thế nào?
Bạn sẽ kiểm thử prompt injection chứa trong tool result hoặc resource mà model phải đọc ra sao?
Bạn kiểm tra hành vi xác nhận của người dùng trước khi tool có tác dụng phụ được thực thi như thế nào?
Bạn sẽ mô phỏng model phát lại cùng tool call để xác minh idempotency ra sao?
Bạn kiểm thử quyền truy cập resource giữa hai tenant để phát hiện rò rỉ dữ liệu như thế nào?
Bạn sẽ đánh giá tính ổn định của hợp đồng tool khi nâng cấp thư viện Spring AI như thế nào?
Bạn thiết kế kiểm thử tải với nhiều MCP client cùng gọi tool tốn tài nguyên như thế nào?
Bạn kiểm thử việc shutdown MCP server khi có request đang chạy và resource cần giải phóng như thế nào?
Bạn sẽ xác minh audit log ghi đúng người gọi, công cụ và kết quả mà không chứa dữ liệu nhạy cảm ra sao?
Bạn xác định tiêu chí nghiệm thu một MCP server trước khi cho ChatClient production sử dụng như thế nào?
Bạn sẽ thiết kế quy trình phát hành và rollback khi schema của một tool MCP thay đổi như thế nào?
Nếu một ChatClient không nhìn thấy tool mới của MCP server, bạn sẽ lần lượt kiểm tra kết nối, capability và discovery như thế nào?
Nếu model đề xuất tool call với tham số JSON sai kiểu, bạn sẽ xác định lỗi nằm ở hợp đồng hay cách model sử dụng như thế nào?
Nếu MCP server trả tool result chứa chỉ dẫn yêu cầu bỏ qua phân quyền, bạn sẽ xử lý nội dung đó như thế nào?
Nếu một MCP tool tạo đơn hàng bị timeout nhưng đơn đã được lưu, bạn sẽ thiết kế retry an toàn ra sao?
Nếu stdio server dừng bất ngờ giữa lời gọi, bạn sẽ phát hiện lỗi và quản lý tiến trình con như thế nào?
Nếu MCP qua HTTP hoạt động trực tiếp nhưng lỗi sau reverse proxy, bạn sẽ kiểm tra transport và timeout ra sao?
Nếu một người dùng chỉ được xem một số resource nhưng model đề xuất truy cập resource khác, bạn sẽ từ chối yêu cầu thế nào?
Nếu nhiều MCP server có tool trùng tên, bạn sẽ thiết kế định danh và giới hạn tool được chọn như thế nào?
Nếu ChatClient lặp lại một tool call không tiến triển, bạn sẽ phát hiện vòng lặp và trả kết quả có kiểm soát ra sao?
Nếu phải xây dựng tính năng Spring AI MCP từ đầu, bạn sẽ thiết kế Server, Client, ChatClient, bảo mật và kiểm thử theo các bước nào?

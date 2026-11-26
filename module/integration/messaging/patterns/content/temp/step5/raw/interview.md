Bạn giải thích mục đích của Enterprise Integration Patterns trong việc kết nối các hệ thống có vòng đời và công nghệ khác nhau như thế nào?
Bạn sẽ nhận diện những điểm ghép nối chặt trong một quy trình tích hợp và dùng messaging để giảm phụ thuộc ra sao?
Bạn phân biệt giao tiếp đồng bộ với giao tiếp bất đồng bộ theo độ trễ, khả năng phục hồi và trải nghiệm nghiệp vụ như thế nào?
Bạn mô tả vai trò của message, channel và endpoint trong một luồng tích hợp từ hệ thống đặt hàng đến kho vận ra sao?
Bạn phân biệt Pipes and Filters với một khối xử lý tích hợp duy nhất về khả năng thay đổi và kiểm thử như thế nào?
Bạn thiết kế ranh giới của từng filter khi luồng cần xác thực, chuẩn hóa, làm giàu và định tuyến thông điệp ra sao?
Bạn chọn Point-to-Point Channel hay Publish-Subscribe Channel dựa trên số lượng bên nhận và ngữ nghĩa xử lý như thế nào?
Bạn phân biệt Command Message, Event Message và Document Message bằng các tình huống nghiệp vụ cụ thể ra sao?
Bạn quyết định nội dung và mức độ chi tiết của một Event Message để giảm phụ thuộc vào cấu trúc dữ liệu bên phát như thế nào?
Bạn xác định một message envelope nên chứa những metadata nào để hỗ trợ định tuyến, truy vết và xử lý lại ra sao?
Bạn thiết kế Message Channel theo loại dữ liệu, nhóm tiêu thụ hoặc mục đích nghiệp vụ bằng những tiêu chí nào?
Bạn phân biệt Datatype Channel và kênh dùng chung khi nhiều loại thông điệp cần được xử lý như thế nào?
Bạn lựa chọn kênh riêng cho thông điệp lỗi nhằm tránh chúng cản trở luồng thông thường ra sao?
Bạn giải thích Dead Letter Channel khác Invalid Message Channel về nguyên nhân và cách xử lý thông điệp như thế nào?
Bạn thiết kế Guaranteed Delivery trong điều kiện broker, mạng và consumer có thể lỗi vào các thời điểm khác nhau ra sao?
Bạn xác định điều kiện cần Durable Subscriber để bên tiêu thụ nhận được sự kiện sau thời gian ngừng hoạt động ra sao?
Bạn phân biệt Competing Consumers với nhiều subscriber độc lập cùng nhận sự kiện theo tác động đến dữ liệu và throughput ra sao?
Bạn lựa chọn số lượng consumer đồng thời theo giới hạn tài nguyên, thứ tự xử lý và yêu cầu độ trễ như thế nào?
Bạn giải thích vai trò của Channel Adapter khi tích hợp một hệ thống cũ không hỗ trợ messaging trực tiếp ra sao?
Bạn sẽ xây dựng Messaging Gateway để ứng dụng nghiệp vụ gọi vào hạ tầng message mà không phụ thuộc API broker như thế nào?
Bạn phân biệt Polling Consumer và Event-Driven Consumer theo mức tải, độ trễ và cách kiểm soát luồng như thế nào?
Bạn đánh giá tác động của Selective Consumer khi nhiều bên cùng đọc một kênh có lượng thông điệp lớn ra sao?
Bạn lựa chọn Content-Based Router để chuyển thông điệp theo trạng thái đơn hàng hoặc loại khách hàng như thế nào?
Bạn thiết kế default route khi Content-Based Router nhận một thông điệp không khớp quy tắc nào ra sao?
Bạn phân biệt Message Filter với Content-Based Router khi cần loại bỏ message hoặc chuyển message đến đích phù hợp như thế nào?
Bạn giải thích Recipient List khác Publish-Subscribe Channel trong việc quyết định danh sách bên nhận ra sao?
Bạn thiết kế Dynamic Router để thay đổi quy tắc chuyển tiếp mà không phải sửa từng service tích hợp như thế nào?
Bạn cân nhắc dùng Routing Slip khi một thông điệp phải đi qua chuỗi bước xử lý linh hoạt theo trường hợp nghiệp vụ ra sao?
Bạn phân biệt Process Manager với Routing Slip khi quyết định bước tiếp theo phụ thuộc kết quả và trạng thái đã tích lũy như thế nào?
Bạn sẽ tránh vòng lặp định tuyến và luồng message chạy vô hạn trong một sơ đồ router phức tạp bằng cách nào?
Bạn thiết kế Message Translator khi hệ thống nguồn và đích dùng tên trường, kiểu dữ liệu và đơn vị đo khác nhau ra sao?
Bạn phân biệt Message Translator, Content Enricher và Content Filter theo thay đổi mà mỗi pattern tạo ra trên payload như thế nào?
Bạn xác định khi nào nên xây dựng Canonical Data Model thay vì viết nhiều phép biến đổi trực tiếp giữa các hệ thống như thế nào?
Bạn quản lý phiên bản của Canonical Data Model để không gây lỗi cho các luồng tích hợp đang hoạt động ra sao?
Bạn thiết kế Content Enricher khi cần gọi một dịch vụ ngoài có thể chậm hoặc không sẵn sàng như thế nào?
Bạn chọn cách xử lý thông tin làm giàu bị thiếu để luồng message vẫn thỏa mãn hợp đồng dữ liệu ra sao?
Bạn dùng Content Filter để loại bỏ trường nhạy cảm trước khi gửi cho đối tác mà vẫn giữ dữ liệu nghiệp vụ cần thiết như thế nào?
Bạn phân biệt Normalizer với Message Translator khi có nhiều định dạng đầu vào cần đưa về một hợp đồng chung ra sao?
Bạn xác định vị trí Validate Message trong pipeline để ngăn dữ liệu lỗi lan sang các bước xử lý tiếp theo như thế nào?
Bạn thiết kế Splitter để tách một đơn hàng nhiều dòng thành các message xử lý độc lập như thế nào?
Bạn xác định khóa tương quan và thông tin thứ tự cho các message con do Splitter tạo ra sao?
Bạn lựa chọn cách xử lý khi một message con thất bại nhưng các message còn lại đã hoàn tất như thế nào?
Bạn giải thích mục đích của Aggregator khi thu kết quả từ nhiều message và điều kiện nào cho phép xuất kết quả cuối cùng?
Bạn thiết kế Aggregator khi không biết trước số lượng message cần nhận và không có tín hiệu kết thúc rõ ràng như thế nào?
Bạn xử lý timeout, message trùng và message đến muộn khi Aggregator chờ kết quả từ nhiều dịch vụ ra sao?
Bạn sẽ lưu trạng thái Aggregator ở đâu để có thể phục hồi khi tiến trình xử lý bị khởi động lại?
Bạn phân biệt Aggregator với Resequencer khi phải nhận lại các message sai thứ tự như thế nào?
Bạn thiết kế Resequencer cho các message có sequence number bị thiếu hoặc đến muộn ra sao?
Bạn xử lý việc một message đã được phát ra khỏi Aggregator nhưng sau đó nhận thêm kết quả bổ sung như thế nào?
Bạn cân nhắc dùng Composed Message Processor thay cho một filter lớn khi vừa cần chia nhỏ vừa cần tổng hợp kết quả ra sao?
Bạn mô tả luồng Request-Reply bất đồng bộ và những lợi ích cũng như chi phí so với HTTP request-response trực tiếp như thế nào?
Bạn xác định Correlation Identifier và Reply Address để phản hồi quay đúng về request ban đầu bằng cách nào?
Bạn thiết kế temporary reply channel hay shared reply channel khi có nhiều instance client cùng gửi request ra sao?
Bạn giữ trạng thái request đang chờ và xử lý phản hồi khi client đã khởi động lại như thế nào?
Bạn giải quyết trường hợp một request nhận nhiều reply hoặc một reply đến sau timeout như thế nào?
Bạn phân biệt timeout giao tiếp với thất bại nghiệp vụ khi diễn giải kết quả Request-Reply bất đồng bộ ra sao?
Bạn xử lý việc bên nhận hoàn thành xử lý nhưng reply bị mất để bên gửi không thực hiện lại nghiệp vụ nguy hiểm như thế nào?
Bạn thiết kế quy tắc retry cho request bất đồng bộ khi chưa xác định được bên nhận đã xử lý hay chưa ra sao?
Bạn xác định lúc nào cần Return Address trong header và lúc nào nên dùng kênh phản hồi cố định như thế nào?
Bạn sẽ tránh lẫn reply giữa các tenant hoặc phiên xử lý trong một shared reply channel bằng cách nào?
Bạn chọn Request-Reply hay Publish-Subscribe cho yêu cầu cần một kết quả xác nhận nghiệp vụ dựa trên những yếu tố nào?
Bạn giải thích vai trò của Saga khi một quy trình nghiệp vụ trải qua nhiều dịch vụ không dùng chung giao dịch dữ liệu như thế nào?
Bạn phân biệt Saga orchestration và choreography theo mức độ điều phối, phụ thuộc và quan sát luồng như thế nào?
Bạn thiết kế Saga đặt hàng gồm đặt chỗ tồn kho, trừ tiền và xác nhận đơn theo các bước nào?
Bạn xác định compensation cho từng bước Saga khi một thao tác không thể đảo ngược hoàn toàn như thế nào?
Bạn sẽ xử lý việc compensation thất bại hoặc chỉ hoàn thành một phần trong Saga ra sao?
Bạn phân biệt retry hành động tiến tới với compensation khi một bước Saga gặp lỗi tạm thời như thế nào?
Bạn thiết kế trạng thái Saga và mã tương quan để có thể truy vết một tiến trình kéo dài nhiều phút ra sao?
Bạn chống việc một sự kiện Saga bị tiêu thụ hai lần khiến cùng một bước nghiệp vụ chạy lặp như thế nào?
Bạn xử lý thông điệp đến sai thứ tự giữa các bước Saga khi các service triển khai độc lập ra sao?
Bạn quyết định khi nào một Saga nên chuyển sang xử lý thủ công thay vì tự động bù trừ như thế nào?
Bạn phân biệt eventual consistency với atomic transaction và giải thích cách thông báo trạng thái tạm thời cho người dùng ra sao?
Bạn xây dựng quy tắc bất biến nghiệp vụ nào để phát hiện sai lệch giữa các service tham gia Saga?
Bạn lựa chọn Process Manager hay Saga orchestrator cho một workflow nhiều nhánh và có các bước chờ dài như thế nào?
Bạn giải thích vì sao messaging với at-least-once delivery cần Idempotent Receiver ngay cả khi producer chỉ gửi một lần?
Bạn thiết kế khóa idempotency dựa trên message ID hay business ID trong các tình huống nào?
Bạn lưu và kiểm tra dấu vết xử lý để tránh ghi trùng dữ liệu khi consumer nhận lại một message như thế nào?
Bạn kết hợp lưu dấu vết idempotency và cập nhật nghiệp vụ trong một transaction để tránh trạng thái nửa vời ra sao?
Bạn xác định thời hạn giữ khóa idempotency để cân bằng khả năng replay với chi phí lưu trữ như thế nào?
Bạn xử lý hai message có cùng idempotency key nhưng payload hoặc ý nghĩa nghiệp vụ khác nhau ra sao?
Bạn phân biệt duplicate delivery, duplicate business event và duplicate processing trong điều tra dữ liệu trùng như thế nào?
Bạn giải thích Transactional Outbox giải quyết khoảng trống nào giữa ghi database và phát message ra broker?
Bạn thiết kế outbox table và publisher để sự kiện nghiệp vụ được gửi sau khi transaction dữ liệu được commit như thế nào?
Bạn quản lý outbox publisher khi gửi thành công nhưng tiến trình chết trước khi đánh dấu message đã phát như thế nào?
Bạn so sánh polling outbox với CDC outbox theo độ trễ, chi phí và khả năng vận hành như thế nào?
Bạn phân biệt Outbox với Inbox pattern khi cần bảo đảm việc ghi nhận và xử lý message ở cả hai đầu ra sao?
Bạn xác định thứ tự các sự kiện phát từ Outbox khi nhiều transaction cùng cập nhật một thực thể bằng cách nào?
Bạn thiết kế xử lý lỗi với retry và Dead Letter Channel để không làm kẹt toàn bộ luồng thông điệp ra sao?
Bạn phân biệt lỗi tạm thời, lỗi dữ liệu và lỗi nghiệp vụ để lựa chọn retry hay chuyển kênh lỗi như thế nào?
Bạn chọn exponential backoff, giới hạn số lần thử và khoảng chờ giữa các lần retry theo những tiêu chí nào?
Bạn giải thích tác động của retry topic hoặc delayed delivery lên thứ tự xử lý của những message cùng business key như thế nào?
Bạn thiết kế Poison Message handling để một bản ghi không hợp lệ không bị xử lý vô hạn ra sao?
Bạn xác định quy trình kiểm tra, sửa và replay message trong Dead Letter Channel để tránh gây tác dụng phụ trùng lặp như thế nào?
Bạn phân biệt cách giữ thứ tự toàn cục với giữ thứ tự theo một thực thể nghiệp vụ khi thiết kế kênh message ra sao?
Bạn lựa chọn partition key hoặc routing key để duy trì thứ tự thay đổi của cùng một đơn hàng như thế nào?
Bạn xử lý việc message đến muộn có phiên bản cũ hơn trạng thái hiện tại của hệ thống đích ra sao?
Bạn thiết kế phiên bản thực thể hoặc sequence number để phát hiện message thiếu, trùng hoặc đảo thứ tự như thế nào?
Bạn cân nhắc trì hoãn, bỏ qua hay bù trừ khi phát hiện thiếu một message trong chuỗi theo thứ tự như thế nào?
Bạn giải thích tác động của parallel consumers lên khả năng giữ thứ tự và độ trễ xử lý như thế nào?
Bạn dùng Wire Tap và Message History để quan sát luồng message mà không thay đổi hành vi xử lý chính ra sao?
Bạn xác định metadata cần ghi trong Message History để truy vết hành trình qua nhiều router và transformer như thế nào?
Bạn bảo vệ dữ liệu nhạy cảm trong nội dung message, header và log quan sát mà vẫn đủ thông tin điều tra ra sao?
Bạn giải thích vai trò của Control Bus trong việc điều chỉnh cấu hình hoặc theo dõi các thành phần tích hợp như thế nào?
Bạn thiết kế giám sát cho queue depth, message age, tỷ lệ retry và dead-letter để phát hiện lỗi tích hợp sớm ra sao?
Bạn phân biệt độ trễ hàng đợi, độ trễ xử lý và độ trễ nghiệp vụ từ đầu đến cuối khi đo chất lượng tích hợp như thế nào?
Bạn phân tích nguyên nhân backlog tăng bằng cách liên hệ producer rate, consumer throughput và thời gian xử lý ra sao?
Bạn xác định điểm đặt circuit breaker hoặc giới hạn đồng thời khi một Content Enricher gọi dịch vụ ngoài không ổn định như thế nào?
Bạn chọn cơ chế backpressure hoặc giới hạn lưu lượng để tránh bộ nhớ của Aggregator bị tăng không kiểm soát ra sao?
Bạn xây dựng kiểm thử contract cho message envelope và schema khi nhiều service sử dụng cùng một kênh như thế nào?
Bạn kiểm thử Content-Based Router bằng các trường hợp biên, route mặc định và nội dung sai định dạng ra sao?
Bạn thiết kế integration test cho Splitter/Aggregator với message thiếu, trùng, đến muộn và timeout như thế nào?
Bạn kiểm thử một Saga với lỗi ở từng bước và lỗi trong compensation để phát hiện trạng thái nghiệp vụ sai ra sao?
Bạn thiết kế thử nghiệm khởi động lại consumer giữa lúc xử lý để kiểm chứng idempotency và thứ tự như thế nào?
Bạn mô phỏng mất kết nối broker hoặc dịch vụ đích để kiểm tra retry, phục hồi và đối soát bằng cách nào?
Bạn lựa chọn những chỉ số nào để đánh giá một thiết kế messaging đáp ứng yêu cầu độ tin cậy và tính nhất quán?
Khi đơn hàng bị trừ tiền hai lần do phát lại message, bạn sẽ điều tra idempotency, inbox và transaction theo trình tự nào?
Khi Aggregator không bao giờ xuất kết quả dù các service con đã hoàn tất, bạn sẽ kiểm tra correlation ID, completion condition và timeout ra sao?
Khi các thông báo thay đổi trạng thái đơn hàng xuất hiện sai thứ tự, bạn sẽ khoanh vùng lỗi ở router, broker và consumer như thế nào?
Khi một bước Saga đã bù trừ nhưng bước khác tiếp tục chạy, bạn sẽ sửa luồng điều phối và xử lý sự kiện đến muộn ra sao?
Nếu cần tích hợp hệ thống bán hàng, thanh toán và giao hàng với yêu cầu chịu lỗi và đối soát, bạn sẽ kết hợp những pattern nào và kiểm chứng thiết kế ra sao?

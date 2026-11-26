Bạn giải thích messaging bất đồng bộ giải quyết những hạn chế nào của giao tiếp request-response giữa các hệ thống?
Bạn sẽ xác định mục tiêu nghiệp vụ trước khi lựa chọn một kiến trúc trao đổi thông điệp như thế nào?
Bạn phân biệt vai trò của producer, consumer, broker và kênh truyền thông điệp trong một hệ thống tích hợp ra sao?
Bạn sẽ mô tả vòng đời của một message từ khi được tạo cho tới khi hoàn tất xử lý như thế nào?
Những dấu hiệu nào cho thấy giao tiếp qua message phù hợp hơn lời gọi API đồng bộ?
Bạn đánh giá những đánh đổi về độ trễ, độ phức tạp và khả năng quan sát khi chuyển sang messaging ra sao?
Bạn phân biệt thông điệp mang lệnh và thông điệp thông báo sự kiện nghiệp vụ như thế nào?
Bạn sẽ xác định ranh giới trách nhiệm giữa producer và consumer để giảm phụ thuộc vào nhau ra sao?
Bạn giải thích tách biệt theo thời gian giữa producer và consumer có lợi ích và giới hạn nào?
Bạn phân tích tác động của việc thêm message broker vào hệ thống đối với tính sẵn sàng và vận hành như thế nào?
Bạn xác định hệ thống nào sở hữu dữ liệu và hệ thống nào chỉ tiêu thụ bản sao dữ liệu ra sao?
Bạn sẽ lựa chọn mức độ bất đồng bộ cho một quy trình vừa có bước cần phản hồi ngay vừa có bước xử lý nền như thế nào?
Bạn thiết kế trải nghiệm người dùng ra sao khi một lệnh được nhận nhưng kết quả nghiệp vụ chưa hoàn tất?
Bạn làm rõ sự khác nhau giữa gửi message thành công và hoàn tất tác vụ nghiệp vụ như thế nào?
Bạn xây dựng sơ đồ luồng message giữa nhiều dịch vụ để phát hiện vòng phụ thuộc hoặc điểm nghẽn ra sao?
Bạn phân biệt queue và topic theo cách phân phối message đến consumer như thế nào?
Bạn sẽ chọn mô hình competing consumers cho một hàng đợi công việc dựa trên tiêu chí nào?
Bạn thiết kế publish-subscribe khi nhiều hệ thống cần phản ứng độc lập với cùng một sự kiện như thế nào?
Bạn phân biệt điểm mạnh của point-to-point với fan-out khi số lượng hệ thống nhận thay đổi ra sao?
Bạn giải thích ảnh hưởng của consumer group tới cách chia tải và phạm vi nhận message như thế nào?
Bạn sẽ quyết định cách đặt tên queue, topic hoặc channel để phản ánh miền nghiệp vụ ra sao?
Bạn đánh giá sự khác nhau giữa message broker lưu trữ công việc và hệ thống log sự kiện có khả năng replay như thế nào?
Bạn xác định khi nào một sự kiện cần được giữ lại lâu hơn thời gian xử lý của consumer ra sao?
Bạn so sánh việc đẩy message chủ động và consumer chủ động lấy message theo nhu cầu nào?
Bạn thiết kế kênh xử lý riêng cho công việc nền và sự kiện nghiệp vụ để tránh ảnh hưởng lẫn nhau như thế nào?
Bạn cân nhắc việc định tuyến message bằng khóa hoặc thuộc tính nghiệp vụ trong những tình huống nào?
Bạn xác định quyền truy cập cần thiết cho producer và consumer trên từng kênh như thế nào?
Bạn sẽ thiết kế kênh dự phòng hoặc phương án chuyển tuyến khi một broker mất khả năng phục vụ ra sao?
Bạn lựa chọn giữa truyền payload đầy đủ và truyền tham chiếu tới tài nguyên theo những yếu tố nào?
Bạn xác định cấu trúc envelope của message gồm ID, metadata, thời gian và payload như thế nào?
Bạn thiết kế message ID khác với business transaction ID để phục vụ mục đích gì?
Bạn sẽ xây dựng correlation ID để liên kết nhiều message thuộc cùng một quy trình nghiệp vụ như thế nào?
Bạn phân biệt correlation ID, causation ID và trace ID trong việc truy vết thông điệp ra sao?
Bạn quyết định sử dụng JSON, XML, Avro hoặc Protocol Buffers dựa trên các yêu cầu tương thích nào?
Bạn định nghĩa hợp đồng payload để producer và consumer hiểu thống nhất kiểu dữ liệu, ý nghĩa và ràng buộc như thế nào?
Bạn thiết kế quy tắc đặt tên trường và các giá trị enum để dễ mở rộng hợp đồng message ra sao?
Bạn sẽ phân biệt một trường vắng mặt, trường null và trường có giá trị mặc định trong thông điệp như thế nào?
Bạn lựa chọn cách biểu diễn thời gian, múi giờ và độ chính xác số khi trao đổi dữ liệu giữa nhiều nền tảng ra sao?
Bạn xử lý việc consumer nhận message có trường chưa biết từ phiên bản producer mới như thế nào?
Bạn thiết kế thay đổi schema theo hướng bổ sung để hạn chế làm hỏng consumer cũ ra sao?
Bạn đánh giá những thay đổi payload nào tuy tương thích về kiểu dữ liệu nhưng phá vỡ ý nghĩa nghiệp vụ?
Bạn quyết định khi nào cần tăng phiên bản message và khi nào có thể mở rộng phiên bản hiện tại như thế nào?
Bạn tổ chức quy trình thông báo và ngừng hỗ trợ schema cũ khi nhiều consumer triển khai độc lập ra sao?
Bạn sẽ lưu và phân phối schema trong một tổ chức để các đội phát triển cùng kiểm soát hợp đồng như thế nào?
Bạn phân biệt xác thực cú pháp message với kiểm tra điều kiện nghiệp vụ tại consumer như thế nào?
Bạn quyết định cách xử lý message hợp lệ về schema nhưng vi phạm quy tắc nghiệp vụ ra sao?
Bạn thiết kế hợp đồng cho một message chứa danh sách nhiều đối tượng mà chỉ một phần hợp lệ như thế nào?
Bạn bảo đảm payload đủ thông tin cần thiết mà không làm lộ dữ liệu không thuộc quyền của consumer như thế nào?
Bạn sẽ thiết kế chiến lược tương thích tiến và tương thích ngược khi producer và consumer nâng cấp lệch thời điểm ra sao?
Bạn xác định trách nhiệm kiểm tra chất lượng dữ liệu ở phía producer và consumer như thế nào?
Bạn sẽ chuẩn bị message trước khi publish để tránh phát thông tin chưa được xác thực hoặc chưa hoàn chỉnh ra sao?
Bạn phân biệt lỗi serialization, lỗi kết nối broker và lỗi broker từ chối nhận message như thế nào?
Bạn quyết định khi nào producer cần chờ broker xác nhận đã nhận hoặc lưu message ra sao?
Bạn thiết kế chính sách timeout và retry của producer dựa trên khả năng broker đã nhận message như thế nào?
Bạn sẽ quản lý message ID khi producer gửi lại cùng một message sau lỗi mạng ra sao?
Bạn đánh giá rủi ro mất message khi producer ghi dữ liệu nghiệp vụ thành công nhưng publish thất bại như thế nào?
Bạn sẽ sử dụng transactional outbox để giải quyết khoảng trống giữa commit cơ sở dữ liệu và publish message ra sao?
Bạn cân nhắc dùng change data capture để chuyển dữ liệu từ outbox sang broker theo điều kiện nào?
Bạn sẽ thiết kế cơ chế xóa hoặc lưu trữ bản ghi outbox sau khi phát thành công như thế nào?
Bạn phân biệt bảo đảm broker nhận message và bảo đảm consumer đã hoàn thành nghiệp vụ như thế nào?
Bạn thiết kế việc gửi message theo lô để cân bằng throughput, độ trễ và khả năng kiểm soát lỗi ra sao?
Bạn sẽ đặt giới hạn kích thước message và payload nhị phân theo năng lực của broker như thế nào?
Bạn xử lý trường hợp producer tạo message nhanh hơn broker có thể tiếp nhận ra sao?
Bạn quyết định cách giảm tải producer khi broker bị lỗi hoặc chậm kéo dài như thế nào?
Bạn xây dựng cơ chế xác định thông điệp nào cần phát lại sau khi producer khởi động lại như thế nào?
Bạn sẽ thiết kế consumer sao cho việc xử lý một message có thể thử lại mà không tạo tác dụng phụ ngoài ý muốn ra sao?
Bạn giải thích khác biệt giữa nhận message, bắt đầu xử lý, commit kết quả và gửi acknowledgment như thế nào?
Bạn quyết định thời điểm gửi acknowledgment dựa trên rủi ro mất hoặc xử lý trùng message ra sao?
Bạn phân biệt auto-acknowledgment với manual acknowledgment theo yêu cầu độ tin cậy như thế nào?
Bạn xử lý consumer bị crash sau khi ghi dữ liệu nhưng trước khi xác nhận message ra sao?
Bạn thiết kế chính sách tạm dừng tiêu thụ khi một phụ thuộc hạ nguồn đang mất khả năng phục vụ như thế nào?
Bạn chọn số lượng consumer song song theo tải, giới hạn hạ nguồn và yêu cầu thứ tự ra sao?
Bạn phân biệt consumer stateless với consumer cần lưu trạng thái phục vụ xử lý message như thế nào?
Bạn bảo vệ consumer trước message bị lỗi cấu trúc mà không làm dừng toàn bộ hàng đợi như thế nào?
Bạn sẽ phân tách bước deserialize, validate và xử lý nghiệp vụ trong một consumer để dễ kiểm thử như thế nào?
Bạn thiết kế cách giải phóng tài nguyên khi consumer ngắt kết nối hoặc nhận yêu cầu dừng như thế nào?
Bạn giải thích at-most-once, at-least-once và exactly-once trong bối cảnh giao nhận message như thế nào?
Bạn phân biệt cam kết exactly-once của hạ tầng với hiệu ứng nghiệp vụ chỉ xảy ra một lần ra sao?
Bạn sẽ lựa chọn delivery semantics phù hợp cho thông báo, cập nhật kho và giao dịch tài chính như thế nào?
Bạn xác định những điểm có thể tạo message trùng từ producer tới consumer ra sao?
Bạn thiết kế idempotency key cho một hành động nghiệp vụ qua message như thế nào?
Bạn quyết định phạm vi và thời gian lưu dấu message đã xử lý để phục vụ deduplication ra sao?
Bạn phân biệt deduplication theo message ID và theo định danh nghiệp vụ trong trường hợp nào?
Bạn xử lý việc hai bản sao cùng message được hai consumer xử lý đồng thời ra sao?
Bạn sẽ dùng ràng buộc duy nhất hoặc giao dịch cơ sở dữ liệu để bảo vệ chống ghi trùng như thế nào?
Bạn giải thích vì sao việc kiểm tra đã xử lý và thực hiện cập nhật cần có tính nguyên tử ra sao?
Bạn xử lý trường hợp message được retry sau khi dấu idempotency đã hết hạn như thế nào?
Bạn thiết kế dữ liệu kết quả lưu kèm idempotency key để trả lại kết quả nhất quán ra sao?
Bạn sẽ xử lý tác dụng phụ ngoài cơ sở dữ liệu như gửi email hoặc gọi hệ thống thanh toán khi message bị phát lại như thế nào?
Bạn phân biệt việc loại trùng event với việc ngăn áp dụng lại thao tác cập nhật trạng thái như thế nào?
Bạn chọn mức bảo đảm giao nhận dựa trên tác hại của message mất, trễ và trùng như thế nào?
Bạn giải thích thứ tự publish, thứ tự lưu tại broker và thứ tự hoàn tất xử lý có thể khác nhau ra sao?
Bạn lựa chọn khóa partition theo thực thể nghiệp vụ để giữ thứ tự cho từng đối tượng như thế nào?
Bạn đánh giá đánh đổi giữa bảo toàn thứ tự toàn cục và tăng throughput của consumer ra sao?
Bạn xử lý message cập nhật trạng thái đến trước message tạo thực thể như thế nào?
Bạn thiết kế cơ chế bỏ qua hoặc chờ message cũ khi số thứ tự nghiệp vụ có khoảng trống ra sao?
Bạn sẽ dùng version của thực thể để tránh event cũ ghi đè trạng thái mới như thế nào?
Bạn phân biệt thứ tự dựa trên thời gian hệ thống với thứ tự dựa trên sequence number như thế nào?
Bạn xử lý clock skew khi producer trên nhiều máy cung cấp timestamp cho message ra sao?
Bạn quyết định khi nào có thể xử lý message độc lập ngoài thứ tự mà vẫn đúng nghiệp vụ như thế nào?
Bạn tổ chức replay message lịch sử mà không làm sai trạng thái hiện tại ra sao?
Bạn xử lý việc phân bổ lại partition giữa các consumer mà vẫn giảm sai lệch thứ tự như thế nào?
Bạn xây dựng quy tắc kiểm tra tính hợp lệ của chuyển trạng thái nghiệp vụ khi event đến muộn như thế nào?
Bạn phân biệt lỗi tạm thời có thể retry với lỗi dữ liệu hoặc nghiệp vụ không thể retry như thế nào?
Bạn thiết kế exponential backoff và jitter cho retry message để tránh cùng lúc gây quá tải như thế nào?
Bạn sẽ đặt giới hạn số lần retry và thời gian tồn tại của message dựa trên yêu cầu nghiệp vụ ra sao?
Bạn đánh giá tác động của retry ngay trong consumer đến việc chặn các message phía sau như thế nào?
Bạn sẽ lựa chọn giữa retry trong tiến trình, hàng đợi retry và lịch xử lý lại theo điều kiện nào?
Bạn thiết kế dead-letter queue cho message không thể xử lý để phục vụ điều tra ra sao?
Bạn quyết định những metadata lỗi nào cần lưu cùng dead-letter message mà vẫn bảo vệ thông tin nhạy cảm như thế nào?
Bạn thiết kế quy trình sửa dữ liệu và phát lại message từ dead-letter queue như thế nào?
Bạn ngăn việc phát lại hàng loạt dead-letter message làm quá tải hệ thống vừa phục hồi ra sao?
Bạn phân biệt poison message với lỗi do dependency tạm thời không sẵn sàng như thế nào?
Bạn xử lý thông điệp hết hạn nhưng đã được nhận vào hàng đợi trong một nghiệp vụ có giới hạn thời gian ra sao?
Bạn lựa chọn hành vi khi message không còn phù hợp vì trạng thái thực thể đã thay đổi như thế nào?
Bạn đánh giá khi nào cần cách ly một consumer hoặc một partition thay vì dừng toàn bộ kênh ra sao?
Bạn xây dựng circuit breaker và cơ chế tạm dừng tiêu thụ khi nhiều message cùng gặp một lỗi hạ nguồn như thế nào?
Bạn sẽ kiểm soát retry storm khi producer và consumer đều có cơ chế thử lại ra sao?
Bạn giải thích khả năng phục hồi sau mất kết nối broker ảnh hưởng tới việc xác nhận message như thế nào?
Bạn phân biệt tính nhất quán mạnh và eventual consistency khi nhiều dịch vụ trao đổi thông điệp như thế nào?
Bạn sẽ xác định mức độ trễ nhất quán chấp nhận được cho từng quy trình nghiệp vụ ra sao?
Bạn thiết kế cơ chế đối soát khi hai hệ thống tiêu thụ message nhưng có trạng thái khác nhau như thế nào?
Bạn lựa chọn cơ chế xử lý xung đột khi nhiều consumer cập nhật cùng một thực thể ra sao?
Bạn sẽ thiết kế saga để phối hợp một chuỗi thao tác bất đồng bộ giữa nhiều dịch vụ như thế nào?
Bạn phân biệt choreography và orchestration trong phối hợp thông điệp của một saga ra sao?
Bạn xây dựng hành động bù trừ khi một bước nghiệp vụ trong saga thất bại như thế nào?
Bạn xử lý lỗi trong chính hành động bù trừ để hệ thống vẫn có khả năng hồi phục ra sao?
Bạn sẽ thiết kế trạng thái trung gian và thời hạn xử lý khi một quy trình có message đến muộn như thế nào?
Bạn xác định ranh giới giao dịch ở consumer để việc ghi dữ liệu và xác nhận message nhất quán nhất có thể ra sao?
Bạn cân nhắc dùng inbox pattern kết hợp outbox pattern trong trường hợp nào?
Bạn thiết kế audit trail để giải thích nguyên nhân một nghiệp vụ hoàn thành hoặc thất bại qua nhiều message ra sao?
Bạn giải thích backpressure trong một hệ thống messaging khi tốc độ producer vượt khả năng consumer như thế nào?
Bạn sẽ phân biệt backlog tăng do consumer chậm với backlog tăng do broker bị nghẽn như thế nào?
Bạn xác định concurrency, batch size và prefetch dựa trên năng lực của consumer và dependency như thế nào?
Bạn đánh giá tác động của việc tăng số consumer lên thứ tự, thông lượng và tài nguyên ra sao?
Bạn thiết kế giới hạn in-flight message để tránh consumer cạn bộ nhớ như thế nào?
Bạn xử lý trường hợp hạ nguồn chỉ cho phép số lượng request đồng thời thấp hơn năng lực đọc message ra sao?
Bạn cân nhắc throttling producer khi broker đạt gần giới hạn lưu trữ như thế nào?
Bạn sẽ tính toán khả năng lưu message trong thời gian consumer ngừng hoạt động dựa trên tải và thời gian khôi phục ra sao?
Bạn phân tích tradeoff giữa latency, throughput và khả năng chịu lỗi khi tăng kích thước batch như thế nào?
Bạn xác định điều kiện nào nên dùng cơ chế ưu tiên message để bảo vệ tác vụ quan trọng ra sao?
Bạn thiết kế chiến lược mở rộng broker hoặc phân vùng để tránh một điểm nóng xử lý như thế nào?
Bạn đánh giá tác động của việc một consumer quá chậm lên các consumer khác cùng kênh như thế nào?
Bạn sẽ thiết kế consumer graceful shutdown để không bỏ dở hoặc xử lý trùng message ngoài kiểm soát ra sao?
Bạn phân biệt tính bền vững của message với tính sẵn sàng của broker khi lập kế hoạch chịu lỗi như thế nào?
Bạn lựa chọn chiến lược replication hoặc dự phòng broker theo yêu cầu độ tin cậy như thế nào?
Bạn sẽ xác định các cơ chế bảo mật cần có trên kết nối producer, broker và consumer như thế nào?
Bạn lựa chọn xác thực bằng tài khoản, token hoặc chứng chỉ cho các thành phần messaging theo bối cảnh nào?
Bạn phân quyền publish và consume trên queue, topic hoặc channel theo nguyên tắc quyền tối thiểu như thế nào?
Bạn xử lý dữ liệu nhạy cảm trong message payload và metadata để hạn chế rò rỉ ra sao?
Bạn xác định khi nào cần mã hóa message ở mức ứng dụng ngoài TLS như thế nào?
Bạn quản lý khóa và secret của producer và consumer trong các môi trường triển khai ra sao?
Bạn thiết kế xoay vòng credential mà không phải dừng toàn bộ luồng xử lý như thế nào?
Bạn ngăn producer giả mạo phát sự kiện nghiệp vụ không hợp lệ vào broker ra sao?
Bạn sẽ kiểm tra quyền truy cập khi nhiều tenant dùng chung hệ thống message broker như thế nào?
Bạn xác định chính sách lưu giữ và xóa message để phù hợp yêu cầu dữ liệu cá nhân ra sao?
Bạn ghi log lỗi xử lý message thế nào để phục vụ gỡ lỗi mà không ghi lộ payload nhạy cảm?
Bạn thiết kế giới hạn kích thước và tần suất message để phòng tránh lạm dụng tài nguyên broker ra sao?
Bạn chọn các chỉ số nào để theo dõi publish rate, consume rate, backlog và thời gian xử lý message?
Bạn phân biệt message age và queue depth khi đánh giá độ trễ nghiệp vụ như thế nào?
Bạn xác định dấu hiệu consumer lag tăng kéo dài và các nguyên nhân thường gặp ra sao?
Bạn sẽ xây dựng distributed tracing qua producer, broker và consumer bằng cách truyền context như thế nào?
Bạn dùng correlation ID và causation ID để tái dựng chuỗi message của một giao dịch ra sao?
Bạn phân biệt cảnh báo tạm thời khi broker chậm với dấu hiệu mất khả năng xử lý kéo dài như thế nào?
Bạn thiết kế dashboard để phân biệt lỗi deserialize, lỗi nghiệp vụ và lỗi kết nối broker ra sao?
Bạn xác định ngưỡng cảnh báo cho retry, dead-letter message và tỷ lệ giao nhận thất bại như thế nào?
Bạn xây dựng runbook xử lý backlog tăng nhanh hoặc broker mất kết nối ra sao?
Bạn sẽ xác định các bước khôi phục consumer sau downtime mà không tạo tải đột biến như thế nào?
Bạn thiết kế kiểm thử hợp đồng giữa producer và consumer khi thay đổi schema message ra sao?
Bạn kiểm thử consumer khi nhận payload thiếu trường, sai kiểu hoặc enum chưa biết như thế nào?
Bạn sẽ mô phỏng việc broker xác nhận publish nhưng producer mất response để kiểm tra chống trùng ra sao?
Bạn kiểm thử trường hợp consumer crash sau khi commit dữ liệu nhưng trước khi gửi acknowledgment như thế nào?
Bạn thiết kế kiểm thử retry với lỗi tạm thời và lỗi không thể xử lý để xác minh chính sách dead-letter ra sao?
Bạn kiểm thử thông điệp đến sai thứ tự hoặc đến muộn để đánh giá tính nhất quán dữ liệu như thế nào?
Bạn kiểm chứng cơ chế idempotency khi nhiều bản sao cùng message được xử lý đồng thời ra sao?
Bạn xây dựng integration test giữa producer, broker và consumer mà vẫn có thể tái hiện kết quả như thế nào?
Bạn thiết kế kiểm thử tải để đo giới hạn throughput, lag và mức dùng bộ nhớ của hệ thống như thế nào?
Bạn sẽ mô phỏng broker bị ngắt và khôi phục để kiểm tra tính bền vững và khả năng phục hồi của message ra sao?
Bạn kiểm thử việc rollout phiên bản consumer mới cùng producer cũ để phát hiện lỗi hợp đồng như thế nào?
Bạn đánh giá những tiêu chí nào trước khi đưa một luồng messaging vào production?
Nếu hai consumer cùng xử lý một lệnh thanh toán do message trùng, bạn sẽ thiết kế lớp chống ghi nhận trùng như thế nào?
Nếu consumer xử lý chậm khiến backlog tăng hàng triệu message, bạn sẽ điều tra và ưu tiên những biện pháp nào?
Nếu producer đã commit đơn hàng nhưng broker chưa nhận event, bạn sẽ khôi phục việc phát thông điệp bằng cách nào?
Nếu một message bị lỗi schema liên tục và chặn partition, bạn sẽ cách ly, sửa và phát lại nó ra sao?
Nếu event cập nhật đơn hàng đến trước event tạo đơn hàng, bạn sẽ bảo toàn trạng thái chính xác như thế nào?
Nếu một dịch vụ nhận event cũ sau khi dữ liệu đã được cập nhật mới hơn, bạn sẽ xử lý xung đột ra sao?
Nếu broker mất kết nối giữa lúc hàng nghìn producer đồng loạt publish, bạn sẽ thiết kế retry và giới hạn tải như thế nào?
Nếu một message cần kích hoạt ba hệ thống độc lập, bạn sẽ thiết kế phân phối và theo dõi lỗi của từng bên ra sao?
Nếu dữ liệu trong hai hệ thống lệch nhau sau nhiều ngày, bạn sẽ đối soát và sửa lại luồng messaging như thế nào?
Nếu phải thiết kế messaging cho quy trình đặt hàng từ đầu, bạn sẽ trình bày các quyết định về kênh, hợp đồng, delivery semantics, bảo mật và kiểm thử như thế nào?

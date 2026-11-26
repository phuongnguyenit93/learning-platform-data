Bạn định nghĩa độ tin cậy của một hệ thống messaging dựa trên những kết quả nghiệp vụ nào?
Bạn sẽ lập bản đồ các điểm có thể xảy ra lỗi từ producer qua broker tới consumer như thế nào?
Bạn phân biệt mất thông điệp, trùng thông điệp, sai thứ tự và xử lý trễ theo mức độ ảnh hưởng nghiệp vụ ra sao?
Bạn sẽ xác định mức bảo đảm giao nhận cần thiết cho từng loại thông điệp dựa trên rủi ro nào?
Bạn giải thích vì sao gửi thông điệp thành công chưa đồng nghĩa với nghiệp vụ đã hoàn tất như thế nào?
Bạn phân biệt tính bền vững của message với tính sẵn sàng của broker như thế nào?
Bạn sẽ xác định mục tiêu RPO và RTO cho một luồng messaging quan trọng ra sao?
Bạn đánh giá những đánh đổi giữa độ trễ, throughput và độ tin cậy khi thiết kế messaging như thế nào?
Bạn phân biệt các lớp lỗi mạng, lỗi ứng dụng và lỗi dữ liệu trong quá trình giao nhận thông điệp như thế nào?
Bạn thiết kế vòng đời trạng thái của một message để các bước tiếp nhận, xử lý và hoàn tất có thể kiểm chứng ra sao?
Bạn xác định trách nhiệm của producer, broker và consumer khi một giao dịch không xuất hiện ở hệ thống đích như thế nào?
Bạn sẽ thiết kế cách đối soát số message phát đi và số nghiệp vụ được ghi nhận thành công ra sao?
Bạn giải thích semantics at-most-once và điều kiện chấp nhận mất message theo nghiệp vụ như thế nào?
Bạn phân tích semantics at-least-once và các tình huống gây phát lại thông điệp ra sao?
Bạn phân biệt exactly-once delivery với exactly-once processing effect khi dữ liệu được ghi vào hệ thống bên ngoài như thế nào?
Bạn sẽ lựa chọn delivery guarantees cho thông báo, đơn hàng và thanh toán dựa trên những đánh đổi nào?
Bạn giải thích cách acknowledgment ảnh hưởng tới việc message được phát lại khi consumer dừng đột ngột như thế nào?
Bạn phân biệt xác nhận đã nhận message với xác nhận đã commit kết quả nghiệp vụ ra sao?
Bạn quyết định khi nào consumer gửi acknowledgment để hạn chế cả mất dữ liệu lẫn xử lý trùng như thế nào?
Bạn phân tích rủi ro khi consumer bật auto-ack trước khi xử lý nghiệp vụ như thế nào?
Bạn xử lý tình huống consumer đã ghi dữ liệu thành công nhưng mất kết nối trước khi ack ra sao?
Bạn thiết kế hành vi khi consumer ack thành công nhưng ứng dụng chưa lưu kết quả nghiệp vụ như thế nào?
Bạn sẽ chọn cơ chế negative acknowledgment, requeue hoặc retry queue theo loại lỗi ra sao?
Bạn đánh giá tác động của thời hạn acknowledgment hoặc visibility timeout tới message xử lý lâu như thế nào?
Bạn sẽ điều chỉnh thời hạn chờ ack để tránh hai consumer cùng xử lý một công việc kéo dài ra sao?
Bạn phân tích khác biệt giữa tín hiệu ack ở mức broker và một biên nhận nghiệp vụ từ hệ thống đích như thế nào?
Bạn sẽ kiểm tra trạng thái một thông điệp khi producer timeout trong lúc chờ broker xác nhận như thế nào?
Bạn mô tả trường hợp broker đã lưu message nhưng producer không nhận được xác nhận ra sao?
Bạn thiết kế retry của producer để xử lý việc không biết broker đã nhận message hay chưa như thế nào?
Bạn sẽ cấp định danh ổn định cho thông điệp khi producer phải gửi lại cùng nội dung như thế nào?
Bạn chọn chế độ durable hoặc persistent message theo yêu cầu bảo toàn dữ liệu ra sao?
Bạn phân biệt việc message đã nằm trong bộ nhớ và đã được ghi bền vững khi đánh giá xác nhận từ broker như thế nào?
Bạn sẽ xác định chính sách replication của broker dựa trên nguy cơ mất node và mất vùng ra sao?
Bạn phân tích rủi ro khi broker leader mất khả năng phục vụ ngay sau khi phản hồi producer như thế nào?
Bạn thiết kế cách chuyển quyền giữa các broker mà vẫn giới hạn mất hoặc trùng message ra sao?
Bạn sẽ xử lý tình trạng broker hết dung lượng lưu trữ trước khi làm mất các message đang chờ như thế nào?
Bạn quyết định khi nào producer nên dừng gửi thay vì giữ message vô hạn ở bộ nhớ ứng dụng ra sao?
Bạn thiết kế local buffering hoặc outbox của producer khi broker tạm thời không truy cập được như thế nào?
Bạn đánh giá nguy cơ phát lại hàng loạt message khi broker phục hồi sau nhiều giờ gián đoạn ra sao?
Bạn sẽ xây dựng cơ chế giới hạn publish rate khi nhiều producer đồng thời kết nối lại như thế nào?
Bạn phân biệt retry ở tầng kết nối broker với retry ở tầng gửi message nghiệp vụ như thế nào?
Bạn thiết kế theo dõi và cảnh báo publish thất bại để biết chắc message nào cần gửi lại ra sao?
Bạn đánh giá khi nào cần dừng nhận yêu cầu nghiệp vụ mới vì hệ thống chưa bảo đảm phát được message như thế nào?
Bạn mô tả vòng đời một consumer từ nhận message đến commit và ack ra sao?
Bạn sẽ thiết kế consumer có thể khởi động lại ở bất kỳ thời điểm nào mà vẫn xử lý đúng nghiệp vụ như thế nào?
Bạn phân biệt lỗi consumer do code, dữ liệu đầu vào và dịch vụ phụ thuộc không sẵn sàng ra sao?
Bạn chọn phương án xử lý khi consumer mất kết nối broker giữa lúc đang thực thi giao dịch như thế nào?
Bạn thiết kế giới hạn số message đang xử lý đồng thời để tránh hết tài nguyên consumer ra sao?
Bạn đánh giá tác động của prefetch và concurrency tới rủi ro mất kiểm soát message đang xử lý như thế nào?
Bạn sẽ xác định tình huống nào cần bảo toàn thứ tự xử lý hơn là tối đa hóa throughput ra sao?
Bạn lựa chọn cách lưu tiến độ xử lý hoặc offset để consumer phục hồi an toàn như thế nào?
Bạn phân tích sự khác nhau giữa commit offset và ack từng message khi xử lý lỗi ra sao?
Bạn sẽ kiểm tra các thao tác bất đồng bộ còn dang dở trước khi consumer shutdown như thế nào?
Bạn thiết kế graceful shutdown để bảo toàn trạng thái những message đang xử lý ra sao?
Bạn xử lý consumer bị crash giữa lúc ghi hai bản ghi thuộc một giao dịch như thế nào?
Bạn sẽ triển khai consumer an toàn với các tác dụng phụ ngoài cơ sở dữ liệu như gửi email hoặc gọi API thanh toán ra sao?
Bạn xây dựng lớp xử lý lỗi chung mà không che mất ngữ cảnh riêng của từng message như thế nào?
Bạn thiết kế chính sách retry khác nhau cho lỗi mạng tạm thời và lỗi nghiệp vụ cố định ra sao?
Bạn lựa chọn retry ngay trong consumer hay đưa message sang retry queue dựa trên tiêu chí nào?
Bạn sẽ cấu hình exponential backoff và jitter để giảm nguy cơ retry storm như thế nào?
Bạn xác định giới hạn số lần thử lại và thời gian sống của một message theo yêu cầu nghiệp vụ ra sao?
Bạn sẽ phân bổ retry budget qua nhiều tầng producer, broker, consumer và dịch vụ hạ nguồn như thế nào?
Bạn phân tích rủi ro khi nhiều lớp cùng retry một giao dịch thất bại ra sao?
Bạn thiết kế cơ chế phân biệt lỗi có thể thử lại với lỗi không thể thử lại mà không phụ thuộc thông báo lỗi dạng chuỗi như thế nào?
Bạn xác định tình huống nào cần giữ nguyên thứ tự message dù một message đang retry như thế nào?
Bạn sẽ hạn chế việc một poison message chặn các thông điệp hợp lệ ở cùng kênh ra sao?
Bạn xây dựng dead-letter queue để phục vụ điều tra, sửa lỗi và phát lại như thế nào?
Bạn xác định thông tin nguyên nhân lỗi và lịch sử retry nào cần đi kèm dead-letter message ra sao?
Bạn thiết kế chính sách lưu giữ và xóa dead-letter message để không mất khả năng điều tra như thế nào?
Bạn sẽ xác định trách nhiệm xử lý thủ công những message đã vượt giới hạn retry ra sao?
Bạn thiết kế công cụ phát lại message từ dead-letter queue có giới hạn tốc độ và kiểm tra quyền như thế nào?
Bạn xử lý tình huống message được sửa rồi phát lại nhưng schema hoặc trạng thái nghiệp vụ đã thay đổi ra sao?
Bạn kiểm tra dữ liệu trước khi phát lại hàng loạt dead-letter message để tránh tác dụng phụ nào?
Bạn đánh giá ảnh hưởng của message hết hạn đối với thao tác vẫn đang có giá trị nghiệp vụ như thế nào?
Bạn quyết định khi nào bỏ qua một message cũ thay vì tiếp tục retry ra sao?
Bạn thiết kế cảnh báo để phát hiện dead-letter queue tích tụ mà người vận hành chưa xử lý như thế nào?
Bạn giải thích idempotency có vai trò gì khi broker bảo đảm at-least-once delivery như thế nào?
Bạn xác định khóa idempotency cho từng loại lệnh nghiệp vụ dựa trên trường dữ liệu nào?
Bạn phân biệt message ID và business operation ID khi chống xử lý trùng như thế nào?
Bạn sẽ lưu trạng thái đã xử lý message trong cơ sở dữ liệu theo cách nào để chịu được khởi động lại?
Bạn thiết kế TTL của bản ghi deduplication dựa trên thời gian replay tối đa như thế nào?
Bạn xử lý một message quay lại sau khi bản ghi chống trùng đã hết hạn ra sao?
Bạn bảo đảm bước kiểm tra trùng và cập nhật nghiệp vụ diễn ra nguyên tử như thế nào?
Bạn sẽ dùng unique constraint hoặc optimistic locking để ngăn hai consumer ghi trùng đồng thời ra sao?
Bạn phân tích điều gì xảy ra nếu consumer lưu dấu đã xử lý trước khi thực hiện nghiệp vụ như thế nào?
Bạn xử lý trường hợp cùng idempotency key được gửi kèm hai payload khác nhau ra sao?
Bạn thiết kế cơ chế trả lại kết quả đã xử lý cho một command bị gửi lại như thế nào?
Bạn sẽ tránh gửi cùng một email, gọi lại webhook hoặc thu tiền hai lần khi message lặp lại ra sao?
Bạn phân biệt xử lý trùng sự kiện với áp dụng lặp lại phép tăng giảm số dư như thế nào?
Bạn thiết kế một consumer nhận event cập nhật trạng thái sao cho phát lại không tạo tác dụng phụ ra sao?
Bạn giải quyết tình huống consumer xử lý trùng nhưng kết quả ở cơ sở dữ liệu đã bị thay đổi bởi thao tác mới hơn như thế nào?
Bạn đánh giá ranh giới mà exactly-once semantics của một nền tảng không thể bảo đảm cho API bên ngoài ra sao?
Bạn sẽ thiết kế transactional inbox kết hợp idempotency để quản lý quá trình xử lý message như thế nào?
Bạn mô tả vấn đề dual write khi vừa cập nhật cơ sở dữ liệu vừa publish message như thế nào?
Bạn giải thích vì sao commit dữ liệu và publish event riêng lẻ có thể làm mất tính nhất quán như thế nào?
Bạn thiết kế transactional outbox để lưu thay đổi nghiệp vụ và bản ghi message trong cùng giao dịch ra sao?
Bạn xác định những trường metadata cần có trong bảng outbox phục vụ retry, routing và audit như thế nào?
Bạn sẽ tổ chức tiến trình đọc outbox và chuyển message sang broker như thế nào?
Bạn so sánh outbox polling và change data capture theo độ trễ, độ phức tạp và khả năng vận hành ra sao?
Bạn sẽ thiết kế khóa đọc outbox để nhiều worker không cùng phát một message không cần thiết như thế nào?
Bạn phân tích trường hợp message được broker nhận nhưng outbox relay crash trước khi đánh dấu đã gửi ra sao?
Bạn thiết kế consumer idempotent để xử lý bản sao message do outbox relay phát lại như thế nào?
Bạn xác định thời điểm đánh dấu outbox đã phát dựa trên loại xác nhận nào từ broker?
Bạn sẽ xử lý bản ghi outbox lỗi kéo dài mà không làm chậm toàn bộ các bản ghi khác ra sao?
Bạn thiết kế cách dọn dẹp bản ghi outbox mà vẫn duy trì khả năng truy vết và phục hồi như thế nào?
Bạn sẽ giám sát độ trễ từ commit giao dịch đến thời điểm message outbox được phát ra sao?
Bạn phân biệt thứ tự commit giao dịch với thứ tự publish message từ outbox như thế nào?
Bạn xử lý sự kiện bị phát không đúng thứ tự khi nhiều outbox relay chạy song song ra sao?
Bạn sẽ lựa chọn một partition key bảo đảm thứ tự theo thực thể nghiệp vụ như thế nào?
Bạn phân tích giới hạn của việc cố giữ thứ tự toàn cục khi hệ thống tăng số partition như thế nào?
Bạn thiết kế sequence number hoặc version cho message để consumer phát hiện event cũ ra sao?
Bạn phân biệt event timestamp và business sequence khi so sánh thứ tự xử lý như thế nào?
Bạn xử lý clock skew giữa các producer mà không dựa mù quáng vào thời gian máy chủ ra sao?
Bạn giải quyết trường hợp thông điệp cập nhật đơn hàng đến trước thông điệp tạo đơn như thế nào?
Bạn thiết kế phương án chờ message còn thiếu khi phát hiện khoảng trống trong dãy thứ tự như thế nào?
Bạn quyết định khi nào có thể bỏ qua event cũ dựa trên version của thực thể ra sao?
Bạn xử lý message đến muộn nhưng vẫn chứa hành động nghiệp vụ cần thực hiện như thế nào?
Bạn sẽ sử dụng khóa nghiệp vụ để tuần tự hóa xử lý các message liên quan mà vẫn cho phép xử lý song song đối tượng khác ra sao?
Bạn phân tích tác động của việc rebalance consumer group đến in-flight message và thứ tự ra sao?
Bạn thiết kế replay nhiều ngày message lịch sử mà không ghi đè dữ liệu hiện tại như thế nào?
Bạn sẽ phân biệt thứ tự giao nhận và thứ tự hoàn tất khi nhiều tác vụ chạy bất đồng bộ ra sao?
Bạn xác định ranh giới giao dịch của một consumer xử lý message và cập nhật nhiều bảng như thế nào?
Bạn giải thích vì sao acknowledgment của broker thường không nằm trong cùng giao dịch ACID với cơ sở dữ liệu nghiệp vụ như thế nào?
Bạn xử lý trường hợp commit cơ sở dữ liệu thành công nhưng ack broker thất bại ra sao?
Bạn lựa chọn cách bảo toàn tính nhất quán giữa hai dịch vụ mà không dùng giao dịch phân tán toàn cục như thế nào?
Bạn phân biệt strong consistency và eventual consistency trong một quy trình xử lý message ra sao?
Bạn sẽ xác định độ trễ nhất quán có thể chấp nhận đối với từng luồng nghiệp vụ như thế nào?
Bạn thiết kế saga cho quy trình có nhiều bước bất đồng bộ và nhiều hệ thống độc lập ra sao?
Bạn phân biệt choreography và orchestration khi thiết kế điều phối saga qua message như thế nào?
Bạn xác định hành động bù trừ nào cần thực hiện khi một bước trong saga thất bại ra sao?
Bạn xử lý lỗi phát sinh trong chính hành động bù trừ để quy trình có thể tiếp tục phục hồi như thế nào?
Bạn thiết kế trạng thái trung gian để người dùng biết tiến độ của nghiệp vụ phân tán như thế nào?
Bạn sẽ tránh phát command trùng khi orchestrator khởi động lại giữa một saga ra sao?
Bạn phân biệt lỗi xử lý nghiệp vụ với một giao dịch cần được hủy hoặc bù trừ như thế nào?
Bạn xây dựng cơ chế đối soát khi một hệ thống báo thành công nhưng hệ thống khác chưa nhận message như thế nào?
Bạn đánh giá khả năng khôi phục tính nhất quán từ audit log và message history ra sao?
Bạn xác định tiêu chí chuyển một giao dịch sang xử lý thủ công khi saga bị kẹt như thế nào?
Bạn sẽ thiết kế thông tin correlation ID và causation ID để tái dựng luồng giao dịch qua các message ra sao?
Bạn chọn các chỉ số nào để giám sát publish failure, ack timeout, retry và dead-letter queue?
Bạn phân biệt queue depth với tuổi của message cũ nhất khi đánh giá backlog như thế nào?
Bạn sẽ đo end-to-end processing latency từ lúc nghiệp vụ commit đến lúc consumer hoàn thành ra sao?
Bạn thiết kế cảnh báo khi outbox relay chậm hoặc không còn phát message như thế nào?
Bạn xác định dấu hiệu retry storm, poison message và consumer crash loop trong dashboard ra sao?
Bạn sẽ đặt giới hạn concurrency và prefetch để bảo vệ hệ thống khỏi quá tải khi phát lại message như thế nào?
Bạn phân tích ảnh hưởng của việc tăng số consumer đến yêu cầu thứ tự và tính idempotent ra sao?
Bạn thiết kế khả năng thoát tải khi downstream chậm mà vẫn giữ message quan trọng như thế nào?
Bạn xây dựng runbook khôi phục sau khi broker mất node hoặc cả cụm không hoạt động ra sao?
Bạn xác định khi nào cần ngừng producer để tránh tích tụ công việc vượt khả năng phục hồi như thế nào?
Bạn sẽ phân quyền thao tác phát lại dead-letter message để tránh can thiệp sai vào dữ liệu nghiệp vụ ra sao?
Bạn bảo vệ message payload và các khóa chống trùng chứa thông tin nhạy cảm như thế nào?
Bạn thiết kế audit trail cho thao tác retry thủ công, replay và bù trừ giao dịch ra sao?
Bạn kiểm thử at-least-once delivery bằng cách mô phỏng lỗi trước và sau acknowledgment như thế nào?
Bạn tạo kịch bản producer mất phản hồi xác nhận từ broker nhưng message đã được lưu để kiểm chứng điều gì?
Bạn kiểm thử consumer crash ngay sau database commit nhưng trước ack như thế nào?
Bạn xây dựng kiểm thử hai consumer nhận bản sao cùng message để xác minh tính idempotent ra sao?
Bạn kiểm tra hiệu quả của transactional outbox khi database commit và broker publish gặp lỗi ở các thời điểm khác nhau như thế nào?
Bạn sẽ kiểm thử outbox relay bị dừng ngay sau khi publish rồi được khởi động lại ra sao?
Bạn thiết kế kiểm thử retry và dead-letter cho cả lỗi tạm thời lẫn lỗi cố định như thế nào?
Bạn mô phỏng message sai thứ tự, đến trễ và được replay để kiểm tra trạng thái nghiệp vụ như thế nào?
Bạn kiểm thử rollback và hành động bù trừ trong saga khi một bước hoặc một dependency thất bại như thế nào?
Bạn thực hiện kiểm thử tải khi backlog lớn để xác minh khả năng mở rộng mà không tăng xử lý trùng như thế nào?
Bạn đánh giá tiêu chí nghiệm thu độ tin cậy trước khi đưa một luồng messaging vào môi trường production ra sao?
Nếu producer timeout sau khi broker đã lưu message thanh toán, bạn sẽ xác minh và gửi lại an toàn như thế nào?
Nếu consumer ghi nhận đơn hàng rồi crash trước ack, bạn sẽ bảo đảm đơn hàng không được tạo hai lần ra sao?
Nếu outbox relay phát sự kiện hai lần sau khi restart, bạn sẽ kiểm soát hiệu ứng nghiệp vụ ở bên nhận như thế nào?
Nếu message lỗi schema liên tục ngăn các message sau được xử lý, bạn sẽ triển khai retry và dead-letter ra sao?
Nếu các sự kiện thay đổi tồn kho đến consumer sai thứ tự, bạn sẽ duy trì số tồn kho đúng như thế nào?
Nếu hệ thống bị mất kết nối broker nhiều giờ, bạn sẽ bảo đảm phục hồi backlog mà không tạo retry storm ra sao?
Nếu một bước thu tiền trong saga thành công nhưng bước tạo vận đơn thất bại, bạn sẽ thiết kế trạng thái và bù trừ như thế nào?
Nếu cần phát lại toàn bộ lịch sử event để xây dựng lại hệ thống đích, bạn sẽ tránh kích hoạt tác dụng phụ trùng như thế nào?
Nếu số lượng dead-letter message tăng cao sau khi thay đổi hợp đồng payload, bạn sẽ xác định nguyên nhân và khôi phục như thế nào?
Nếu phải thiết kế từ đầu một pipeline messaging đáng tin cậy cho đơn hàng, bạn sẽ lựa chọn delivery semantics, giao dịch, retry, thứ tự và cách kiểm thử như thế nào?

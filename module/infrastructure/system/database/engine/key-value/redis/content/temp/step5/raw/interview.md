Bạn giải thích Redis là hệ thống dữ liệu khóa–giá trị theo những đặc điểm nào?
Bạn dựa trên yêu cầu độ trễ, thông lượng và độ bền nào để quyết định dùng Redis?
Bạn phân biệt vai trò Redis làm cache với vai trò kho dữ liệu chính trong hệ thống như thế nào?
Bạn xác định những trường hợp nào không phù hợp để lưu toàn bộ dữ liệu bằng Redis?
Bạn mô tả cơ chế xử lý lệnh và các nguyên nhân có thể làm Redis bị chậm ra sao?
Bạn ước lượng bộ nhớ cần cho một bộ dữ liệu Redis dựa vào những yếu tố nào?
Bạn thiết kế quy ước đặt tên khóa để hỗ trợ nhiều dịch vụ và môi trường như thế nào?
Bạn cân nhắc độ dài khóa với khả năng quan sát và chi phí bộ nhớ ra sao?
Bạn tổ chức namespace và phiên bản khóa khi cấu trúc dữ liệu của ứng dụng thay đổi như thế nào?
Bạn chọn thời điểm tạo, cập nhật và xóa khóa dựa trên vòng đời của dữ liệu ra sao?
Bạn xác định cấu trúc Redis phù hợp từ những truy vấn mà ứng dụng cần thực hiện bằng cách nào?
Bạn đánh giá tác động của một khóa quá lớn đến độ trễ và việc vận hành như thế nào?
Bạn phát hiện và xử lý khóa nhận lưu lượng cao bất thường bằng cách nào?
Bạn thiết kế cơ chế tra cứu khi Redis không hỗ trợ truy vấn tùy ý như cơ sở dữ liệu quan hệ ra sao?
Bạn chọn String cho giá trị nguyên tử, văn bản hoặc dữ liệu nhị phân theo tiêu chí nào?
Bạn triển khai bộ đếm bằng các phép tăng giảm nguyên tử của String như thế nào?
Bạn kiểm soát tràn số hoặc giá trị không hợp lệ khi dùng Redis làm bộ đếm ra sao?
Bạn đánh giá có nên lưu một đối tượng dưới dạng chuỗi JSON trong Redis hay không bằng cách nào?
Bạn xử lý cập nhật một trường của đối tượng được lưu dưới dạng String như thế nào?
Bạn sử dụng thao tác đặt giá trị có điều kiện để tránh ghi đè ngoài ý muốn ra sao?
Bạn chọn Hash thay cho nhiều String riêng lẻ khi lưu thuộc tính của một đối tượng như thế nào?
Bạn cập nhật một phần Hash mà vẫn giữ tính nhất quán của các thuộc tính liên quan ra sao?
Bạn kiểm tra sự hiện diện và kiểu dữ liệu của một field trong Hash bằng cách nào?
Bạn cân nhắc số lượng field, kích thước giá trị và chi phí bộ nhớ của Hash như thế nào?
Bạn thiết kế TTL cho đối tượng được lưu trong Hash khi các field có vòng đời khác nhau ra sao?
Bạn lựa chọn List cho hàng đợi hoặc lịch sử thao tác theo những tiêu chí nào?
Bạn xử lý tình huống nhiều consumer cùng lấy phần tử khỏi List như thế nào?
Bạn phân biệt cách dùng List cho công việc cần xác nhận xử lý với một hàng đợi đơn giản ra sao?
Bạn giới hạn độ dài List để tránh tăng bộ nhớ không kiểm soát bằng cách nào?
Bạn dùng Set để biểu diễn quan hệ thành viên duy nhất trong bài toán nào?
Bạn triển khai kiểm tra thành viên và loại trùng bằng Set như thế nào?
Bạn tính giao, hợp và hiệu của nhiều tập hợp khi dữ liệu lớn bằng cách nào?
Bạn cân nhắc chi phí của phép toán tập hợp trước yêu cầu độ trễ thực tế như thế nào?
Bạn duy trì tính đồng bộ giữa Set thành viên và dữ liệu chi tiết tương ứng ra sao?
Bạn chọn Sorted Set để thiết kế bảng xếp hạng theo tiêu chí nào?
Bạn tổ chức điểm số và quy tắc xử lý trường hợp đồng điểm trong Sorted Set như thế nào?
Bạn truy vấn top N và vị trí của một phần tử trong Sorted Set ra sao?
Bạn thiết kế leaderboard theo ngày, tuần và toàn thời gian như thế nào?
Bạn cập nhật và loại bỏ điểm số đã hết hiệu lực trong bảng xếp hạng bằng cách nào?
Bạn dùng Sorted Set để lập lịch công việc theo thời điểm đến hạn ra sao?
Bạn đánh giá việc dùng Sorted Set cho hàng đợi ưu tiên có nhiều worker như thế nào?
Bạn phân biệt Streams với Pub/Sub khi yêu cầu hệ thống phải xử lý thông điệp sau khi consumer tạm ngừng ra sao?
Bạn thiết kế trường và ID của một entry trong Redis Streams như thế nào?
Bạn tổ chức consumer group để chia tải xử lý sự kiện giữa nhiều worker ra sao?
Bạn giải thích vòng đời một thông điệp từ khi được đọc đến khi được xác nhận trong consumer group như thế nào?
Bạn xử lý thông điệp chưa được ACK khi consumer gặp sự cố ra sao?
Bạn thu hồi các thông điệp bị treo trong pending entries để worker khác tiếp tục xử lý như thế nào?
Bạn thiết kế xử lý idempotent khi một thông điệp Streams có thể được giao lại ra sao?
Bạn xác định điều kiện retry, giới hạn số lần thử và hàng đợi lỗi cho Streams như thế nào?
Bạn giám sát độ trễ xử lý và lượng backlog của consumer group bằng cách nào?
Bạn giới hạn độ dài Streams và xác định rủi ro đối với consumer còn chậm như thế nào?
Bạn quyết định khi nào dùng Redis Streams và khi nào cần hệ thống message broker chuyên dụng ra sao?
Bạn giải thích sự khác nhau giữa khóa hết hạn theo TTL và khóa bị loại bỏ do chính sách bộ nhớ như thế nào?
Bạn đặt TTL theo loại dữ liệu và giá trị nghiệp vụ bằng những tiêu chí nào?
Bạn xác định tác động của việc gia hạn TTL ở mỗi lần truy cập lên vòng đời dữ liệu ra sao?
Bạn kiểm tra và thay đổi thời hạn hết hạn của khóa mà tránh làm mất giá trị như thế nào?
Bạn xử lý trường hợp nhiều khóa quan trọng hết hạn cùng lúc như thế nào?
Bạn áp dụng TTL có độ ngẫu nhiên để giảm tải đột biến lên hệ thống nguồn ra sao?
Bạn phân biệt cơ chế loại bỏ khóa hết hạn chủ động và thụ động ở Redis như thế nào?
Bạn chọn chính sách maxmemory và eviction theo mẫu truy cập của ứng dụng như thế nào?
Bạn đánh giá hậu quả của việc dùng noeviction với một workload ghi liên tục ra sao?
Bạn xây dựng kịch bản ứng dụng khi Redis hết bộ nhớ hoặc không còn nhận ghi như thế nào?
Bạn xử lý dữ liệu không được phép tự biến mất trong môi trường Redis có eviction như thế nào?
Bạn mô tả luồng cache-aside từ lần đọc trượt cache đến khi cập nhật dữ liệu ra sao?
Bạn so sánh cache-aside, write-through và write-behind theo yêu cầu tính nhất quán như thế nào?
Bạn quyết định nội dung nào cần cache theo tần suất đọc, chi phí tính toán và tốc độ thay đổi ra sao?
Bạn thiết kế khóa cache chứa tham số lọc và phân trang để tránh va chạm như thế nào?
Bạn xử lý cache miss đối với dữ liệu thực sự không tồn tại nhằm tránh truy vấn lặp về nguồn ra sao?
Bạn ngăn hiện tượng cache stampede khi một khóa phổ biến hết hạn như thế nào?
Bạn hạn chế cache penetration khi truy vấn các khóa không hợp lệ hàng loạt ra sao?
Bạn ngăn cache avalanche khi một số lượng lớn khóa đồng loạt bị xóa hoặc hết hạn như thế nào?
Bạn xây dựng cơ chế làm mới cache trước hạn cho dữ liệu có lưu lượng truy cập cao ra sao?
Bạn đảm bảo quá trình invalidation khi nhiều đường ghi cùng sửa một bản ghi gốc như thế nào?
Bạn xử lý cuộc đua giữa thao tác đọc dữ liệu cũ và thao tác làm mới cache như thế nào?
Bạn chấp nhận mức stale data nào trong cache và đo lường mức độ đó bằng cách nào?
Bạn phân biệt mục tiêu cache hit rate với tác động thực tế đến độ trễ và tải hệ thống nguồn ra sao?
Bạn thiết kế fallback khi Redis không khả dụng mà ứng dụng vẫn cần trả lời yêu cầu như thế nào?
Bạn áp dụng cơ chế chống truy cập đồng thời quá mức đến nguồn khi cache gặp sự cố như thế nào?
Bạn đánh giá việc dùng Redis cho session người dùng khi có yêu cầu đăng xuất và thu hồi phiên như thế nào?
Bạn phân biệt snapshot RDB và append-only file AOF dựa trên khả năng phục hồi dữ liệu như thế nào?
Bạn lựa chọn cấu hình lưu bền Redis dựa trên giới hạn mất dữ liệu cho phép ra sao?
Bạn giải thích những loại mất dữ liệu nào có thể xảy ra giữa hai lần ghi bền xuống đĩa như thế nào?
Bạn kiểm chứng khả năng khôi phục dữ liệu sau khi tiến trình Redis bị dừng bất ngờ ra sao?
Bạn đánh giá ảnh hưởng của quá trình tạo snapshot đến bộ nhớ và độ trễ như thế nào?
Bạn theo dõi việc ghi và rewrite AOF khi dữ liệu thay đổi liên tục ra sao?
Bạn lập kế hoạch sao lưu và kiểm tra bản sao lưu Redis bằng cách nào?
Bạn thực hiện kiểm tra phục hồi trên môi trường riêng mà không ghi đè dữ liệu đang hoạt động ra sao?
Bạn thiết kế kế hoạch khởi động lại Redis sau sự cố với dữ liệu lớn như thế nào?
Bạn lựa chọn mức độ bền của Redis so với cơ sở dữ liệu nguồn cho từng loại bản ghi ra sao?
Bạn sử dụng MULTI và EXEC khi cần thực thi một nhóm lệnh mà không bị xen ngang như thế nào?
Bạn phân biệt tính nguyên tử của một lệnh Redis với tính nguyên tử của chuỗi thao tác nhiều lệnh ra sao?
Bạn nêu rủi ro khi dùng MULTI và EXEC với kỳ vọng rollback tương tự cơ sở dữ liệu quan hệ như thế nào?
Bạn áp dụng WATCH để thực hiện cập nhật có điều kiện khi nhiều client cạnh tranh ra sao?
Bạn xử lý retry sau xung đột optimistic locking bằng WATCH như thế nào?
Bạn quyết định dùng Lua script hoặc Redis Functions cho nghiệp vụ nhiều bước dựa trên tiêu chí nào?
Bạn giới hạn thời gian và khối lượng xử lý của script để tránh chặn các lệnh khác ra sao?
Bạn thiết kế khóa phân tán với điều kiện chiếm quyền và thời hạn tự giải phóng như thế nào?
Bạn tránh việc một worker xóa nhầm khóa mà worker khác vừa gia hạn hoặc chiếm lại ra sao?
Bạn đánh giá những giới hạn của distributed lock khi xảy ra dừng dài, phân vùng mạng hoặc failover như thế nào?
Bạn dùng fencing token hoặc kiểm tra phiên bản ở hệ thống đích để ngăn ghi cũ như thế nào?
Bạn thiết kế rate limiter dùng Redis để xử lý nhiều yêu cầu đồng thời ra sao?
Bạn lựa chọn fixed window, sliding window hoặc token bucket theo yêu cầu hạn mức như thế nào?
Bạn quản lý sự sai lệch thời gian và việc reset bộ đếm trong cơ chế rate limiting ra sao?
Bạn phân biệt mục tiêu của Redis replication và cơ chế lưu bền dữ liệu ra sao?
Bạn giải thích luồng đồng bộ ban đầu và đồng bộ gia tăng giữa primary và replica như thế nào?
Bạn đánh giá độ trễ replication khi ứng dụng cần đọc dữ liệu vừa ghi ra sao?
Bạn chọn đọc từ primary hoặc replica theo yêu cầu nhất quán của từng truy vấn như thế nào?
Bạn xử lý tình huống ghi đã được chấp nhận nhưng chưa xuất hiện trên replica khi failover ra sao?
Bạn giải thích vai trò của Redis Sentinel đối với giám sát và failover như thế nào?
Bạn kiểm thử tác động của Sentinel failover đến kết nối và thao tác ghi đang diễn ra ra sao?
Bạn thiết kế retry và idempotency khi client mất kết nối trong thời điểm chuyển primary như thế nào?
Bạn phân biệt Redis Cluster với mô hình primary-replica đơn lẻ theo cách phân phối dữ liệu ra sao?
Bạn sử dụng hash slot và hash tag để bố trí các khóa cần thao tác cùng nhau như thế nào?
Bạn đánh giá giới hạn của thao tác đa khóa trong Redis Cluster và xử lý cross-slot ra sao?
Bạn chọn số shard, replica và chiến lược mở rộng Cluster dựa trên dữ liệu và lưu lượng như thế nào?
Bạn xác định nguy cơ tạo hot slot khi nhiều khóa chia sẻ cùng hash tag ra sao?
Bạn kiểm thử hoạt động của client khi Cluster di chuyển slot giữa các node như thế nào?
Bạn thiết kế phương án giảm tải Redis khi tải ghi và tải đọc phát triển không cân xứng ra sao?
Bạn chọn Lettuce, Jedis hoặc Spring Data Redis cho dịch vụ Java dựa trên tiêu chí nào?
Bạn cấu hình kết nối, timeout và retry trong Java client để tránh gây tải lặp khi Redis chậm ra sao?
Bạn phân biệt kết nối đồng bộ, bất đồng bộ và reactive khi truy cập Redis từ Java như thế nào?
Bạn đánh giá khi nào nên dùng connection pool và khi nào có thể tái sử dụng kết nối Java client ra sao?
Bạn xử lý serialize và deserialize dữ liệu Java theo cách hỗ trợ tiến hóa phiên bản như thế nào?
Bạn phòng tránh lỗi kiểu dữ liệu Redis khi các phiên bản ứng dụng dùng chung khóa như thế nào?
Bạn dùng pipelining trong Java để giảm round trip mà vẫn quản lý kích thước batch ra sao?
Bạn phân biệt pipelining với transaction về thứ tự thực thi và bảo đảm nguyên tử như thế nào?
Bạn mô hình hóa thao tác Redis trong Spring Data Redis mà không che mất các giới hạn vận hành ra sao?
Bạn thiết kế kiểm thử tích hợp cho repository hoặc Java client khi có TTL, failover và mất kết nối như thế nào?
Bạn chọn cách cấu hình ACL, xác thực và TLS cho kết nối Redis trong môi trường nhiều dịch vụ như thế nào?
Bạn giới hạn quyền truy cập khóa và lệnh theo từng ứng dụng bằng ACL ra sao?
Bạn ngăn lộ thông tin nhạy cảm qua tên khóa, lệnh quan sát và log vận hành như thế nào?
Bạn bảo vệ Redis khỏi các lệnh gây tải lớn hoặc thao tác nhầm trong môi trường sản xuất như thế nào?
Bạn xác định những chỉ số bộ nhớ, kết nối, lỗi và độ trễ cần giám sát trên Redis ra sao?
Bạn dùng SLOWLOG và quan sát latency để tìm nguyên nhân chậm theo từng nhóm lệnh như thế nào?
Bạn phát hiện big keys và đánh giá phương án chia tách chúng bằng cách nào?
Bạn sử dụng SCAN để duyệt khóa an toàn hơn so với việc truy xuất toàn bộ khóa cùng lúc như thế nào?
Bạn phân tích chi phí của các lệnh phụ thuộc số phần tử trong cấu trúc dữ liệu ra sao?
Bạn sử dụng benchmark và mẫu tải thực để đặt mục tiêu độ trễ Redis như thế nào?
Bạn nhận diện tác động của network round trip, payload và serialization lên thời gian phản hồi ra sao?
Bạn thiết kế ngưỡng cảnh báo khi bộ nhớ tăng nhanh nhưng hit rate không cải thiện như thế nào?
Bạn xây dựng quy trình xử lý sự cố Redis khi ứng dụng báo tăng timeout đột ngột ra sao?
Bạn phân biệt triệu chứng quá tải CPU, cạn bộ nhớ và nghẽn mạng từ các chỉ số vận hành như thế nào?
Bạn chẩn đoán sự khác biệt giữa keyspace hit rate tốt và độ trễ người dùng vẫn cao ra sao?
Bạn lập kế hoạch đổi cấu trúc khóa Redis đang sử dụng mà các phiên bản ứng dụng cùng hoạt động như thế nào?
Bạn xây dựng tiêu chí kiểm thử và chấp nhận trước khi đưa giải pháp Redis mới vào production ra sao?
Bạn thiết kế hệ thống giỏ hàng dùng Redis với yêu cầu tồn tại giỏ hàng, chỉnh sửa đồng thời và hết hạn như thế nào?
Bạn lựa chọn cấu trúc và chiến lược TTL cho một bảng xếp hạng có hàng triệu thành viên ra sao?
Bạn thiết kế hệ thống xử lý sự kiện đặt hàng dựa trên Streams với yêu cầu giao lại và chống trùng như thế nào?
Bạn quyết định khi nào nên bỏ Redis khỏi đường xử lý bắt buộc để giảm rủi ro toàn hệ thống ra sao?

Bạn sẽ dựa vào yêu cầu nghiệp vụ nào để quyết định một hệ thống cơ sở dữ liệu cần sao chép dữ liệu?
Bạn sẽ phân biệt replication và sharding qua mục tiêu, cách phân bố dữ liệu và những rủi ro vận hành như thế nào?
Bạn sẽ giải thích sự khác nhau giữa sao chép dữ liệu, sao lưu dữ liệu và khôi phục sau thảm họa như thế nào?
Bạn sẽ đánh giá ảnh hưởng của replication đến khả năng sẵn sàng, thông lượng đọc và độ bền dữ liệu ra sao?
Bạn sẽ xác định những giới hạn của replication khi hệ thống cần mở rộng khả năng ghi như thế nào?
Bạn sẽ chọn các chỉ số nào để đánh giá độ trễ sao chép, tính nhất quán và khả năng chịu lỗi của cụm dữ liệu?
Bạn sẽ mô tả đường đi của một lệnh ghi và một lệnh đọc trong kiến trúc single-leader như thế nào?
Bạn sẽ lựa chọn đồng bộ, bất đồng bộ hoặc bán đồng bộ giữa leader và follower dựa trên yêu cầu nào?
Bạn sẽ phân tích những tình huống dữ liệu đã được leader xác nhận nhưng vẫn có thể mất khi leader gặp sự cố ra sao?
Bạn sẽ đánh đổi độ trễ ghi và mức bảo vệ dữ liệu như thế nào khi yêu cầu một hoặc nhiều replica xác nhận?
Bạn sẽ phân biệt physical replication và logical replication về dữ liệu truyền đi, khả năng tương thích và mục đích sử dụng ra sao?
Bạn sẽ giải thích vai trò của write-ahead log hoặc change log trong việc đưa thay đổi từ leader đến follower như thế nào?
Bạn sẽ thiết kế cơ chế follower bắt kịp leader sau khi mất kết nối trong một khoảng thời gian như thế nào?
Bạn sẽ phân biệt sao chép theo snapshot ban đầu và truyền thay đổi liên tục trong quá trình bổ sung replica như thế nào?
Bạn sẽ nhận diện nguy cơ replica đọc dữ liệu cũ khi ứng dụng vừa ghi lên leader như thế nào?
Bạn sẽ thiết kế read-your-writes consistency trong ứng dụng đọc từ replica bằng những cơ chế nào?
Bạn sẽ giải quyết trường hợp người dùng đọc trên nhiều replica và thấy dữ liệu quay về phiên bản cũ ra sao?
Bạn sẽ giải thích tính chất monotonic reads và cách duy trì nó khi chuyển giữa các replica như thế nào?
Bạn sẽ lựa chọn định tuyến truy vấn đọc sang leader hoặc follower dựa trên yêu cầu độ mới của dữ liệu ra sao?
Bạn sẽ hạn chế ảnh hưởng của replica lag đối với một dashboard vận hành thời gian gần thực như thế nào?
Bạn sẽ đo độ trễ sao chép bằng log position, thời điểm commit hoặc các chỉ số sẵn có trong hệ thống ra sao?
Bạn sẽ phân biệt lag do mạng, do follower xử lý chậm và do lượng ghi tăng đột biến như thế nào?
Bạn sẽ xác định giới hạn cần áp dụng khi một follower chậm không thể theo kịp tốc độ cập nhật từ leader ra sao?
Bạn sẽ tổ chức bổ sung replica mới mà không gây quá tải leader hoặc làm gián đoạn truy vấn như thế nào?
Bạn sẽ mô tả những bước cần thực hiện khi leader ngừng hoạt động để chọn leader mới an toàn như thế nào?
Bạn sẽ đánh giá lợi ích và rủi ro của failover tự động so với failover thủ công trong một dịch vụ quan trọng ra sao?
Bạn sẽ giải thích split-brain và các điều kiện có thể khiến hai node cùng tin mình là leader như thế nào?
Bạn sẽ thiết kế cơ chế fencing để ngăn leader cũ tiếp tục ghi sau khi cụm đã chuyển quyền như thế nào?
Bạn sẽ quản lý term, epoch hoặc generation number để nhận biết quyền lãnh đạo đã thay đổi như thế nào?
Bạn sẽ phát hiện và xử lý tình trạng leader cũ quay trở lại với dữ liệu chưa được replica mới xác nhận ra sao?
Bạn sẽ kiểm tra điều kiện nào trước khi tự động chuyển hướng kết nối ứng dụng sang leader mới?
Bạn sẽ xây dựng kịch bản thử failover để xác minh RPO, RTO và mức gián đoạn dịch vụ như thế nào?
Bạn sẽ mô tả đường đi của lệnh ghi trong kiến trúc multi-leader khi hai trung tâm dữ liệu nhận ghi đồng thời như thế nào?
Bạn sẽ lựa chọn multi-leader cho những trường hợp địa lý hoặc làm việc ngoại tuyến nào?
Bạn sẽ dự đoán những loại xung đột nào phát sinh khi cùng một bản ghi được cập nhật trên hai leader ra sao?
Bạn sẽ giải quyết xung đột last-write-wins và đánh giá nguy cơ mất cập nhật hợp lệ như thế nào?
Bạn sẽ sử dụng version vector hoặc thông tin nguyên nhân kết quả để nhận biết các bản cập nhật đồng thời như thế nào?
Bạn sẽ thiết kế quy tắc hòa giải xung đột cho giỏ hàng, hồ sơ người dùng và số dư tài khoản ra sao?
Bạn sẽ chứng minh giới hạn của đồng hồ vật lý khi dùng timestamp để xếp thứ tự cập nhật trong môi trường phân tán như thế nào?
Bạn sẽ tận dụng Lamport clock hoặc logical clock để mô tả quan hệ xảy ra trước giữa các sự kiện như thế nào?
Bạn sẽ lựa chọn cách phát hiện và loại bỏ vòng lặp sao chép trong một cấu hình multi-leader như thế nào?
Bạn sẽ thiết kế khả năng ghi khi hai vùng mạng bị tách rời và sau đó đồng bộ trở lại ra sao?
Bạn sẽ đánh giá chi phí đồng bộ giữa các vùng địa lý khi người dùng được phép ghi cục bộ như thế nào?
Bạn sẽ mô tả cách leaderless replication phân phối yêu cầu ghi đến nhiều replica như thế nào?
Bạn sẽ lựa chọn replication factor theo yêu cầu chịu lỗi của hệ thống leaderless ra sao?
Bạn sẽ giải thích ý nghĩa của N, R và W trong cơ chế đọc ghi quorum bằng một ví dụ cụ thể như thế nào?
Bạn sẽ kiểm tra điều kiện R + W lớn hơn N và phân tích những giả định khiến kết quả thực tế vẫn có thể khác mong đợi ra sao?
Bạn sẽ chọn quorum đọc và ghi cho ứng dụng ưu tiên độ trễ thấp nhưng chấp nhận đọc dữ liệu cũ như thế nào?
Bạn sẽ thay đổi R và W để ưu tiên xác nhận ghi bền vững hơn trong hệ thống nhiều replica ra sao?
Bạn sẽ giải thích sloppy quorum và hinted handoff giúp duy trì khả năng phục vụ khi replica mục tiêu không sẵn sàng như thế nào?
Bạn sẽ phân tích giới hạn của sloppy quorum đối với bảo đảm đọc được bản ghi mới nhất ra sao?
Bạn sẽ phát hiện và hòa giải các phiên bản xung đột khi một lượt đọc trả về nhiều giá trị từ các replica như thế nào?
Bạn sẽ phân biệt read repair và anti-entropy repair trong việc đồng bộ dữ liệu giữa các replica ra sao?
Bạn sẽ giải thích cách Merkle tree hỗ trợ xác định những vùng dữ liệu khác nhau cần sửa chữa như thế nào?
Bạn sẽ thiết kế cơ chế retry an toàn khi client không nhận được phản hồi cho một yêu cầu ghi nhưng nhiều replica đã lưu dữ liệu như thế nào?
Bạn sẽ nhận biết và xử lý bản ghi đã xóa xuất hiện trở lại khi một replica vắng mặt quá lâu ra sao?
Bạn sẽ giải thích vai trò của tombstone và thời gian giữ tombstone trong cơ chế sao chép leaderless như thế nào?
Bạn sẽ phân tích ảnh hưởng của thiết bị hoặc node có đồng hồ lệch đến cơ chế giải quyết xung đột ghi như thế nào?
Bạn sẽ so sánh consistency mạnh, eventual consistency và các bảo đảm nhất quán theo phiên làm việc như thế nào?
Bạn sẽ phân biệt linearizability và serializability thông qua hành vi đọc ghi mà ứng dụng có thể quan sát ra sao?
Bạn sẽ giải thích causal consistency và các quan hệ nhân quả cần bảo toàn trong một ứng dụng cộng tác như thế nào?
Bạn sẽ thiết kế giao diện người dùng chịu được eventual consistency mà không tạo cảm giác dữ liệu bị mất như thế nào?
Bạn sẽ đánh giá mức nhất quán cần thiết cho thông tin sản phẩm, giỏ hàng và quyết toán giao dịch ra sao?
Bạn sẽ kiểm tra một hệ thống có bảo đảm read-your-writes và monotonic reads bằng thử nghiệm như thế nào?
Bạn sẽ lựa chọn consistency model cho dữ liệu cấu hình hiếm khi thay đổi nhưng cần được đọc chính xác dựa trên tiêu chí nào?
Bạn sẽ áp dụng định lý CAP để phân tích hành vi của một hệ thống khi có phân hoạch mạng như thế nào?
Bạn sẽ giải thích giới hạn của cách gọi một hệ thống là CP hoặc AP nếu không xét hoạt động cụ thể và điều kiện lỗi như thế nào?
Bạn sẽ lựa chọn hành vi trả lỗi, chờ hoặc tiếp tục phục vụ khi replica bị chia tách mạng dựa trên nhu cầu nghiệp vụ ra sao?
Bạn sẽ dùng mô hình PACELC để đánh giá đánh đổi giữa độ trễ và nhất quán ngay cả khi mạng hoạt động bình thường như thế nào?
Bạn sẽ phân biệt vai trò của availability trong CAP với chỉ số uptime mà nhóm vận hành thường báo cáo ra sao?
Bạn sẽ xác định ngưỡng timeout và retry phù hợp để tránh nhầm một node chậm với node đã hỏng như thế nào?
Những dấu hiệu nào giúp bạn phân biệt network partition với tình trạng một node bị tắt hoàn toàn trong hệ thống phân tán?
Bạn sẽ thiết kế thí nghiệm phân hoạch mạng để kiểm chứng cam kết consistency và availability của sản phẩm như thế nào?
Bạn sẽ phân tích trường hợp lỗi mạng bất đối xứng khiến các node quan sát trạng thái khác nhau ra sao?
Bạn sẽ kết hợp cơ chế phát hiện lỗi và consensus để giảm nguy cơ bầu nhầm leader như thế nào?
Bạn sẽ mô tả vai trò của majority quorum trong thuật toán consensus khi một số node không thể liên lạc như thế nào?
Bạn sẽ tính số lỗi mà các cụm consensus gồm ba, bốn và năm node có thể chịu được như thế nào?
Bạn sẽ đối chiếu consensus với replication dữ liệu thông thường về mục đích và bảo đảm đạt được như thế nào?
Bạn sẽ mô tả cách Raft sử dụng log replication và leader election để thống nhất thứ tự lệnh như thế nào?
Bạn sẽ đánh giá ảnh hưởng của việc thêm node hoặc đổi thành viên nhóm consensus đến tính sẵn sàng ra sao?
Bạn sẽ phân biệt quorum trong consensus và quorum dữ liệu của mô hình leaderless như thế nào?
Bạn sẽ phân tích thời điểm một giao dịch ghi được coi là committed trong hệ thống dựa trên consensus như thế nào?
Bạn sẽ thiết kế giải pháp xử lý split-brain trong môi trường nhiều data center có giới hạn độ trễ như thế nào?
Bạn sẽ dùng những chỉ số và giới hạn nào để quyết định mở rộng hệ thống bằng sharding sau khi đã có replication?
Bạn sẽ lựa chọn giữa hash sharding và range sharding theo phân bố khóa và mẫu truy vấn ra sao?
Bạn sẽ thiết kế shard key để phân phối tải ghi đều và hỗ trợ các truy vấn quan trọng như thế nào?
Bạn sẽ phát hiện shard nóng khi một nhóm khách hàng hoặc một khoảng khóa nhận quá nhiều truy cập ra sao?
Bạn sẽ dự đoán tác động của shard key tăng dần theo thời gian lên cân bằng tải trong range sharding như thế nào?
Bạn sẽ dùng consistent hashing để giảm lượng dữ liệu phải di chuyển khi bổ sung node như thế nào?
Bạn sẽ phân biệt dữ liệu của một shard và các replica của shard đó trong sơ đồ triển khai ra sao?
Bạn sẽ lựa chọn số shard và replication factor theo tăng trưởng dữ liệu, dung lượng node và khả năng chịu lỗi như thế nào?
Bạn sẽ thiết kế quy trình resharding để di chuyển dữ liệu và lưu lượng truy vấn mà không bỏ sót cập nhật như thế nào?
Bạn sẽ kiểm tra độ đúng của dữ liệu sau khi tách hoặc gộp shard bằng cơ chế đối chiếu nào?
Bạn sẽ xử lý một truy vấn cần tổng hợp dữ liệu trên nhiều shard để cân bằng tốc độ và tính nhất quán ra sao?
Bạn sẽ phân biệt scatter-gather query và truy vấn định tuyến đúng một shard về chi phí tài nguyên như thế nào?
Bạn sẽ triển khai định tuyến truy vấn đến đúng shard khi ứng dụng chưa biết node đang giữ khóa dữ liệu ra sao?
Bạn sẽ cập nhật metadata phân vùng và xử lý cache định tuyến cũ trong quá trình di chuyển shard ra sao?
Bạn sẽ xác định những rủi ro của cross-shard JOIN và chọn cách tổ chức dữ liệu thay thế như thế nào?
Bạn sẽ quản lý uniqueness của khóa định danh khi dữ liệu trải trên nhiều shard như thế nào?
Bạn sẽ chọn chiến lược cấp phát ID phân tán đáp ứng yêu cầu duy nhất, thứ tự và thông lượng ra sao?
Bạn sẽ giải thích vấn đề của giao dịch cập nhật nhiều shard khi không có một cơ chế commit chung như thế nào?
Bạn sẽ mô tả các pha và trạng thái lỗi của two-phase commit trong một giao dịch phân tán ra sao?
Bạn sẽ xử lý tình huống coordinator lỗi sau khi các participant đã chuẩn bị commit nhưng chưa biết quyết định cuối cùng như thế nào?
Bạn sẽ đánh giá nhược điểm blocking của two-phase commit và tác động lên khả năng sẵn sàng ra sao?
Bạn sẽ phân biệt vai trò của consensus với two-phase commit khi yêu cầu vừa chịu lỗi vừa giữ tính nguyên tử như thế nào?
Bạn sẽ lựa chọn giữa giao dịch phân tán đồng bộ và eventual consistency cho các nghiệp vụ nhiều dịch vụ dựa trên tiêu chí nào?
Bạn sẽ thiết kế saga với các bước bù trừ cho quy trình đặt hàng, thanh toán và giữ chỗ như thế nào?
Bạn sẽ xử lý trường hợp thao tác bù trừ trong saga cũng thất bại và phải thử lại nhiều lần ra sao?
Bạn sẽ thiết kế idempotency key để ngăn phát sinh giao dịch trùng khi hệ thống gửi lại yêu cầu như thế nào?
Bạn sẽ sử dụng transactional outbox để đồng bộ thay đổi cơ sở dữ liệu và phát hành sự kiện như thế nào?
Bạn sẽ giải thích vì sao việc nhận một sự kiện đúng một lần khó bảo đảm xuyên nhiều hệ thống và bạn sẽ thiết kế xử lý ra sao?
Bạn sẽ quản lý thứ tự sự kiện và phiên bản thực thể khi các bản cập nhật được truyền bất đồng bộ qua nhiều dịch vụ như thế nào?
Những loại dữ liệu nào phù hợp với CRDT và bạn sẽ giải thích cơ chế hợp nhất cập nhật đồng thời giữa các replica ra sao?
Bạn sẽ phân biệt phương án merge tự động và hòa giải thủ công theo mức độ quan trọng của dữ liệu ra sao?
Bạn sẽ thiết kế cơ chế thay đổi schema hoặc version message trong một hệ thống replication đang chạy liên tục như thế nào?
Bạn sẽ bảo đảm tính nhất quán của metadata cấu hình cụm khi node mới được thêm hoặc node cũ bị loại bỏ như thế nào?
Bạn sẽ lựa chọn vị trí đặt replica giữa các availability zone và vùng địa lý dựa trên khả năng chịu lỗi và độ trễ ra sao?
Bạn sẽ tính toán ảnh hưởng của độ trễ liên vùng đến thời gian commit của replication đồng bộ như thế nào?
Bạn sẽ đưa ra chính sách read routing cho người dùng ở nhiều khu vực trong khi cập nhật chỉ đến từ một leader ra sao?
Bạn sẽ thiết kế chiến lược sao lưu và khôi phục khi các replica có thể chưa đồng bộ cùng một thời điểm như thế nào?
Bạn sẽ kết hợp snapshot với change log để khôi phục hoặc tạo lại replica đến một mốc nhất quán ra sao?
Bạn sẽ xác định mục tiêu RPO và RTO trong kiến trúc phân tán nhiều vùng bằng những giả định nào?
Bạn sẽ giám sát replica lag, quorum availability, leader changes và shard imbalance bằng những chỉ số nào?
Bạn sẽ xây dựng cảnh báo cho tình trạng liên tục bầu leader mới hoặc failover lặp lại như thế nào?
Bạn sẽ thiết kế thử nghiệm chaos engineering nhằm đo tác động của lỗi mạng, mất node và chậm đĩa lên dữ liệu ra sao?
Bạn sẽ điều tra nguyên nhân số liệu trên hai replica khác nhau dù luồng replication vẫn hiển thị đang hoạt động như thế nào?
Bạn sẽ đánh giá tác động của replication đến lưu lượng mạng, dung lượng lưu trữ và chi phí vận hành ra sao?
Bạn sẽ lập kế hoạch nâng cấp từng node khi hệ thống cần duy trì quorum và tránh ngắt toàn bộ dịch vụ như thế nào?
Bạn sẽ xử lý tình huống leader bị cô lập khỏi phần lớn cụm nhưng ứng dụng vẫn tiếp tục gửi yêu cầu ghi đến node đó ra sao?
Nếu vùng A và vùng B cùng sửa thông tin tài khoản trong thời gian mất kết nối, bạn sẽ chọn cơ chế phát hiện và giải quyết xung đột như thế nào?
Nếu replica mới lên thay leader nhưng thiếu các bản ghi vừa được xác nhận, bạn sẽ phân tích nguy cơ mất dữ liệu và hướng khôi phục ra sao?
Nếu một shard nhận phần lớn truy vấn còn các shard khác gần như nhàn rỗi, bạn sẽ tìm nguyên nhân và cân bằng lại dữ liệu như thế nào?
Nếu giao dịch chuyển tiền qua hai shard bị gián đoạn giữa chừng, bạn sẽ đề xuất cơ chế giữ tính đúng đắn và phục hồi ra sao?
Nếu dashboard đọc từ replica trễ 30 giây trong khi thao tác thanh toán cần đọc ngay dữ liệu mới, bạn sẽ thiết kế đường đọc cho từng chức năng như thế nào?
Bạn sẽ đề xuất kiến trúc replication và sharding cho nền tảng thương mại điện tử đa khu vực với yêu cầu độ trễ thấp, khôi phục nhanh và tránh ghi trùng như thế nào?

Bạn sẽ dựa trên những yêu cầu nào để quyết định sử dụng Apache Cassandra cho một hệ thống dữ liệu phân tán?
Những đặc điểm nào của tải đọc, tải ghi và khả năng sẵn sàng khiến Cassandra phù hợp hoặc không phù hợp với một ứng dụng?
Bạn sẽ giải thích mô hình wide-column của Cassandra và sự khác biệt với bảng quan hệ thông thường như thế nào?
Kiến trúc peer-to-peer của Cassandra giúp phân phối dữ liệu và loại bỏ điểm lỗi đơn như thế nào?
Bạn sẽ mô tả vai trò của coordinator node trong một yêu cầu đọc hoặc ghi từ ứng dụng ra sao?
Gossip protocol hỗ trợ các node trao đổi trạng thái của cụm Cassandra như thế nào?
Bạn sẽ phân biệt vai trò của token, partitioner và token ring trong việc tìm vị trí lưu dữ liệu ra sao?
Bạn sẽ giải thích cách virtual node ảnh hưởng đến phân phối token và cân bằng dữ liệu khi thêm hoặc thay node như thế nào?
Bạn sẽ xác định những rủi ro nào khi một cụm có node với dung lượng hoặc cấu hình phần cứng không đồng nhất?
Bạn sẽ phân biệt keyspace, table và partition khi thiết kế lưu trữ dữ liệu trong Cassandra như thế nào?
Bạn sẽ giải thích partition key quyết định vị trí dữ liệu và đường đi của truy vấn ra sao?
Bạn sẽ chọn partition key cho bảng có hàng triệu người dùng để tránh phân vùng nóng như thế nào?
Bạn sẽ sử dụng composite partition key khi nào để cân bằng phân phối dữ liệu và truy xuất theo điều kiện?
Bạn sẽ thiết kế clustering columns để sắp xếp và lấy các bản ghi mới nhất trong một partition như thế nào?
Bạn sẽ phân tích ảnh hưởng của thứ tự clustering columns đối với điều kiện WHERE và ORDER BY ra sao?
Bạn sẽ ước tính kích thước của một partition dựa trên tốc độ phát sinh dữ liệu và thời gian lưu giữ như thế nào?
Bạn sẽ phát hiện và khắc phục partition quá lớn làm tăng độ trễ đọc hoặc compaction như thế nào?
Bạn sẽ dùng time bucketing để thiết kế bảng sự kiện tăng trưởng liên tục mà không tạo partition vô hạn ra sao?
Bạn sẽ điều chỉnh độ dài bucket theo ngày, tuần hoặc tháng dựa trên mẫu truy vấn và lượng dữ liệu như thế nào?
Bạn sẽ chọn khóa phân vùng như thế nào khi phần lớn yêu cầu tra cứu chỉ có mã khách hàng và khoảng thời gian?
Bạn sẽ mô hình hóa bảng theo các truy vấn ứng dụng trước khi xác định khóa chính như thế nào?
Bạn sẽ thiết kế nhiều bảng phục vụ các cách truy xuất khác nhau trên cùng một thực thể ra sao?
Bạn sẽ duy trì dữ liệu phi chuẩn hóa nhất quán khi một thay đổi cần ghi vào nhiều bảng Cassandra như thế nào?
Bạn sẽ xử lý yêu cầu JOIN hoặc truy vấn tùy biến vốn không phù hợp với mô hình truy vấn của Cassandra ra sao?
Bạn sẽ thiết kế bảng lưu tin nhắn theo hội thoại để lấy trang tin nhắn gần nhất hiệu quả như thế nào?
Bạn sẽ tổ chức dữ liệu số đo cảm biến theo thiết bị và thời gian để vừa ghi liên tục vừa truy vấn theo khoảng ra sao?
Bạn sẽ thiết kế bảng phục vụ tra cứu đơn hàng theo người mua và bảng tra cứu theo mã đơn như thế nào?
Bạn sẽ nhận biết các dấu hiệu data skew khi một partition key xuất hiện thường xuyên hơn các giá trị khác ra sao?
Bạn sẽ cân nhắc việc bổ sung shard nhân tạo vào partition key để phân tán truy cập cho một khách hàng rất lớn như thế nào?
Bạn sẽ dự đoán số truy vấn cần thực hiện khi một yêu cầu trải qua nhiều partition thời gian ra sao?
Bạn sẽ lựa chọn kiểu dữ liệu UUID, timeuuid, timestamp và các kiểu số cho từng loại dữ liệu như thế nào?
Bạn sẽ giải thích khác biệt giữa khóa chính của bảng Cassandra và ràng buộc khóa ngoại trong cơ sở dữ liệu quan hệ ra sao?
Bạn sẽ sử dụng list, set, map hoặc user-defined type cho cấu trúc dữ liệu nào và giới hạn cần lưu ý là gì?
Bạn sẽ dựa vào tiêu chí nào để tách một collection lớn thành nhiều hàng dữ liệu riêng biệt?
Bạn sẽ thiết kế TTL cho sự kiện ngắn hạn mà vẫn đảm bảo truy vấn các dữ liệu còn hiệu lực ra sao?
Bạn sẽ kiểm soát tác động của việc ghi giá trị null hoặc xóa dữ liệu đến số lượng tombstone như thế nào?
Bạn sẽ tạo keyspace với chính sách replication phù hợp cho môi trường nhiều trung tâm dữ liệu như thế nào?
Bạn sẽ sử dụng CQL để tạo bảng có partition key tổng hợp và clustering order theo yêu cầu truy vấn ra sao?
Bạn sẽ viết truy vấn CQL lấy các bản ghi của một partition theo khoảng clustering key như thế nào?
Những giới hạn nào thường xuất hiện khi truy vấn CQL không có điều kiện trên partition key, và bạn sẽ giải thích nguyên nhân như thế nào?
Bạn sẽ đánh giá rủi ro của ALLOW FILTERING và đề xuất thiết kế bảng thay thế như thế nào?
Bạn sẽ so sánh khả năng dùng secondary index hoặc Storage-Attached Index với bảng truy vấn riêng trên phiên bản Cassandra đang triển khai ra sao?
Bạn sẽ kiểm tra khả năng hỗ trợ và giới hạn của index hoặc materialized view theo phiên bản Cassandra trước khi áp dụng như thế nào?
Bạn sẽ phân trang kết quả truy vấn CQL trên một partition lớn mà vẫn kiểm soát độ trễ và bộ nhớ ra sao?
Bạn sẽ xử lý thứ tự kết quả khi truy vấn nhiều partition mà không thể sắp xếp toàn cục trực tiếp như thế nào?
Bạn sẽ phân biệt INSERT, UPDATE và hành vi upsert trong Cassandra qua một trường hợp ghi lại cùng khóa ra sao?
Bạn sẽ sử dụng IF NOT EXISTS hoặc điều kiện IF trong CQL cho tình huống nghiệp vụ nào?
Bạn sẽ giải thích vì sao lightweight transaction có chi phí khác với thao tác ghi CQL thông thường như thế nào?
Bạn sẽ xử lý bài toán tăng bộ đếm bằng counter table và đánh giá giới hạn của nó ra sao?
Bạn sẽ chọn BATCH cho những cập nhật nào và lý do không nên coi BATCH là cách tăng thông lượng ghi hàng loạt là gì?
Bạn sẽ kiểm tra tính nguyên tử và giới hạn bảo đảm khi một batch ghi qua nhiều partition như thế nào?
Bạn sẽ thiết kế thao tác ghi có thể thử lại an toàn khi client không biết yêu cầu trước đã thành công hay chưa ra sao?
Bạn sẽ phân tích cơ chế xác định phiên bản ghi thắng khi nhiều bản ghi cùng partition và key được cập nhật đồng thời như thế nào?
Bạn sẽ quản lý đồng hồ giữa các client và node để tránh tác động không mong muốn của timestamp ghi như thế nào?
Bạn sẽ kiểm tra kết quả INSERT, UPDATE và DELETE bằng truy vấn CQL sao cho phân biệt đúng dữ liệu vắng mặt với dữ liệu hết TTL ra sao?
Bạn sẽ mô tả luồng ghi qua commit log, memtable và SSTable trong Cassandra như thế nào?
Commit log hỗ trợ độ bền dữ liệu sau sự cố node như thế nào và bạn sẽ kiểm chứng khả năng khôi phục ra sao?
Bạn sẽ giải thích cơ chế ghi bất biến của SSTable khi ứng dụng sửa một bản ghi như thế nào?
Bạn sẽ mô tả luồng đọc dữ liệu từ memtable và SSTable đến kết quả trả về như thế nào?
Bloom filter giúp tránh những thao tác đọc SSTable không cần thiết trong trường hợp nào?
Bạn sẽ đánh giá tác động của cache, số lượng SSTable và số partition được đọc lên độ trễ truy vấn ra sao?
Bạn sẽ lựa chọn giữa SizeTieredCompactionStrategy, LeveledCompactionStrategy và TimeWindowCompactionStrategy dựa trên mẫu ghi đọc như thế nào?
Bạn sẽ xác định tiêu chí nào khiến TimeWindowCompactionStrategy phù hợp với dữ liệu chỉ thêm mới và có TTL?
Bạn sẽ phân tích chi phí write amplification, read amplification và sử dụng đĩa khi chọn chiến lược compaction như thế nào?
Bạn sẽ nhận diện một backlog compaction và quyết định thứ tự xử lý khi hiệu năng cụm bắt đầu giảm ra sao?
Bạn sẽ giải thích quá trình tạo tombstone khi xóa bản ghi hoặc dữ liệu hết TTL như thế nào?
Bạn sẽ tìm nguyên nhân một truy vấn đọc quá nhiều tombstone và thay đổi mô hình dữ liệu để khắc phục ra sao?
Bạn sẽ xác định vai trò của gc_grace_seconds đối với nguy cơ dữ liệu đã xóa xuất hiện trở lại như thế nào?
Bạn sẽ phối hợp chính sách TTL, lịch repair và thời gian giữ tombstone để giảm nguy cơ dữ liệu phục hồi ngoài ý muốn ra sao?
Bạn sẽ đánh giá khi nào nên thay đổi compression và compaction settings để đáp ứng giới hạn CPU, I/O và dung lượng ra sao?
Bạn sẽ chọn replication factor theo số node, fault domain và yêu cầu chịu lỗi của ứng dụng như thế nào?
Bạn sẽ mô tả vai trò của NetworkTopologyStrategy trong một cụm có nhiều data center ra sao?
Bạn sẽ phân bố replica giữa các rack hoặc availability zone để giảm ảnh hưởng của lỗi hạ tầng như thế nào?
Bạn sẽ so sánh các consistency level ONE, QUORUM và ALL theo độ trễ, khả năng sẵn sàng và độ tin cậy ra sao?
Bạn sẽ lựa chọn LOCAL_ONE và LOCAL_QUORUM cho các truy vấn trong một data center như thế nào?
Bạn sẽ giải thích mối quan hệ giữa replication factor, số replica đọc và số replica ghi khi cần tính nhất quán như thế nào?
Bạn sẽ đánh giá điều kiện R + W lớn hơn RF và những giả định cần thận trọng khi suy luận kết quả đọc như thế nào?
Bạn sẽ chọn consistency level cho ghi telemetry không quan trọng bằng ghi số dư nghiệp vụ ra sao?
Bạn sẽ xử lý yêu cầu đọc dữ liệu vừa ghi khi các replica có thể chưa đồng bộ như thế nào?
Bạn sẽ đánh giá vai trò và giới hạn của hinted handoff khi một replica tạm thời không khả dụng như thế nào?
Bạn sẽ mô tả vai trò của read repair và anti-entropy repair trong việc giảm sai lệch giữa các replica như thế nào?
Bạn sẽ xác định những trường hợp nào cần chủ động chạy repair dù hệ thống vẫn phục vụ truy vấn bình thường?
Bạn sẽ xử lý một yêu cầu ghi bị timeout khi không biết có bao nhiêu replica đã lưu dữ liệu như thế nào?
Bạn sẽ lựa chọn consistency level cho truy vấn qua nhiều data center khi đường truyền liên vùng không ổn định ra sao?
Bạn sẽ phân biệt normal consistency level và serial consistency level trong thao tác điều kiện như thế nào?
Bạn sẽ giải thích cơ chế Paxos trong lightweight transaction và những tác động đến độ trễ ra sao?
Bạn sẽ phân tích trạng thái đọc có thể khác nhau như thế nào khi một replica bị lỗi nhưng nhiều replica khác vẫn hoạt động?
Bạn sẽ thiết kế kiểm thử cạnh tranh như thế nào để quyết định có cần lightweight transaction cho một luồng cập nhật?
Bạn sẽ theo dõi nodetool status, trạng thái node và phân bổ token để phát hiện node bất thường như thế nào?
Bạn sẽ xác định nguyên nhân một node liên tục rời rồi tham gia lại cụm dựa trên log và metrics ra sao?
Bạn sẽ đánh giá những bước cần chuẩn bị trước khi bootstrap một node mới vào cluster như thế nào?
Bạn sẽ xử lý tình huống thay thế node hỏng và bảo đảm dữ liệu được stream về node mới ra sao?
Bạn sẽ kiểm tra mức lệch dữ liệu và phân bổ tải sau khi bổ sung node hoặc thay đổi topology như thế nào?
Bạn sẽ phân biệt nodetool cleanup, repair và rebuild để dùng đúng trong từng tình huống vận hành như thế nào?
Bạn sẽ lập lịch repair phù hợp với thời gian lưu tombstone, lượng dữ liệu và tải hệ thống ra sao?
Bạn sẽ lựa chọn incremental repair hoặc full repair theo điều kiện và giới hạn của phiên bản Cassandra hiện dùng như thế nào?
Bạn sẽ điều tra một tác vụ repair chạy quá lâu hoặc không hoàn thành mà vẫn giữ được khả năng phục vụ truy vấn như thế nào?
Bạn sẽ theo dõi số tombstone, pending compactions, disk usage và read latency để phát hiện vấn đề sớm ra sao?
Bạn sẽ chẩn đoán tình trạng một node hết dung lượng đĩa khi compaction và streaming vẫn đang diễn ra như thế nào?
Bạn sẽ kiểm soát các tác vụ backup snapshot và xóa snapshot cũ để không làm đầy đĩa như thế nào?
Bạn sẽ lên kế hoạch sao lưu và khôi phục một keyspace trên nhiều node mà vẫn xác minh được tính toàn vẹn dữ liệu ra sao?
Bạn sẽ đặt mục tiêu RPO và RTO cho Cassandra và kiểm thử kịch bản mất toàn bộ data center như thế nào?
Bạn sẽ thiết kế chiến lược nâng cấp rolling upgrade có xét đến tương thích giữa các phiên bản Cassandra và driver như thế nào?
Bạn sẽ quản lý quyền truy cập theo role và hạn chế quyền ghi schema cho từng nhóm người dùng ra sao?
Bạn sẽ triển khai xác thực, mã hóa đường truyền client-to-node và node-to-node theo chính sách bảo mật như thế nào?
Bạn sẽ xác định cấu hình Java driver nào phải khớp với phiên bản Cassandra và khả năng hỗ trợ CQL hiện tại ra sao?
Bạn sẽ cấu hình contact points, local datacenter và phương thức xác thực khi kết nối Java tới cụm Cassandra như thế nào?
Bạn sẽ quản lý vòng đời CqlSession trong ứng dụng Java nhiều luồng để tránh tạo quá nhiều kết nối ra sao?
Bạn sẽ sử dụng prepared statement và bound statement để ghi dữ liệu có tham số một cách an toàn như thế nào?
Bạn sẽ tổ chức mapper hoặc lớp truy cập dữ liệu để giữ câu truy vấn CQL phù hợp với từng bảng nghiệp vụ như thế nào?
Bạn sẽ giải thích token-aware routing và chính sách ưu tiên node gần ứng dụng ảnh hưởng đến hiệu năng như thế nào?
Bạn sẽ sử dụng phân trang của Java driver để đọc nhiều dòng mà không giữ toàn bộ kết quả trong bộ nhớ ra sao?
Bạn sẽ lựa chọn API bất đồng bộ hoặc reactive của Java driver trong một luồng ghi nhiều sự kiện như thế nào?
Bạn sẽ cấu hình timeout, consistency level và execution profile riêng cho từng loại truy vấn Java như thế nào?
Bạn sẽ phân biệt retry an toàn và retry có thể gây ghi lặp khi Java driver gặp lỗi mạng như thế nào?
Bạn sẽ chỉ định tính idempotent của statement để driver quyết định retry hoặc speculative execution phù hợp ra sao?
Bạn sẽ thiết kế giới hạn concurrency và cơ chế backpressure trong Java để không làm quá tải Cassandra như thế nào?
Bạn sẽ giám sát metrics phía Java driver để phân biệt thời gian chờ kết nối, timeout và truy vấn chậm trên node như thế nào?
Bạn sẽ kiểm thử tích hợp Java với Cassandra bằng dữ liệu và topology gần môi trường thực tế như thế nào?
Nếu một partition của tài khoản lớn chiếm phần lớn tài nguyên cụm, bạn sẽ xác định nguyên nhân và sửa thiết kế khóa ra sao?
Nếu truy vấn CQL gặp lỗi khi thiếu điều kiện trên partition key, bạn sẽ đề xuất bảng phục vụ mẫu truy vấn đó như thế nào?
Nếu hệ thống xuất hiện nhiều tombstone sau chiến dịch xóa dữ liệu, bạn sẽ chọn bước chẩn đoán và khắc phục nào?
Nếu một data center mất kết nối nhưng ứng dụng vẫn phải phục vụ truy vấn, bạn sẽ chọn replication và consistency như thế nào?
Nếu ứng dụng Java liên tục gặp WriteTimeoutException khi tải tăng đột biến, bạn sẽ lần theo nguyên nhân và xác định cách retry an toàn ra sao?
Nếu hai replica trả về giá trị khác nhau sau một thời gian node bị lỗi, bạn sẽ xác minh và sửa sai lệch dữ liệu như thế nào?
Bạn sẽ đề xuất kiến trúc Cassandra cho nền tảng ghi sự kiện quy mô lớn có hai data center, dữ liệu lưu 90 ngày và ứng dụng Java yêu cầu độ trễ thấp như thế nào?

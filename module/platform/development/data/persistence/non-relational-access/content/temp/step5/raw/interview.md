Bạn dựa vào đặc điểm dữ liệu và mẫu truy cập nào để quyết định dùng cơ sở dữ liệu NoSQL thay vì cơ sở dữ liệu quan hệ?
Bạn so sánh mô hình document, key-value, wide-column và graph theo cách biểu diễn quan hệ dữ liệu và kiểu truy vấn thường gặp như thế nào?
Bạn xác định ranh giới aggregate và đơn vị cập nhật nguyên tử khi thiết kế dữ liệu phi quan hệ ra sao?
Khi một ứng dụng có nhiều kiểu truy vấn trái ngược nhau, bạn lựa chọn một mô hình lưu trữ hay kết hợp nhiều hệ như thế nào?
Bạn phân tích đánh đổi giữa tính nhất quán, độ sẵn sàng và khả năng chịu phân vùng mạng trong tình huống thực tế ra sao?
Bạn phân biệt tính nhất quán mạnh, nhất quán cuối cùng và các mức bảo đảm đọc ghi mà ứng dụng cần như thế nào?
Bạn lựa chọn driver Java đồng bộ, bất đồng bộ hoặc reactive dựa trên mô hình tải và khả năng kiểm soát luồng xử lý ra sao?
Bạn cấu hình địa chỉ kết nối, xác thực, TLS và bí mật truy cập của NoSQL driver cho nhiều môi trường như thế nào?
Bạn xác định kích thước connection pool, thời gian chờ và giới hạn số yêu cầu đồng thời để tránh nghẽn ứng dụng ra sao?
Bạn quản lý chuyển đổi kiểu dữ liệu, thời gian và giá trị null khi ánh xạ đối tượng Java sang bản ghi NoSQL như thế nào?
Bạn thiết kế chiến lược phát triển schema khi tài liệu cũ và mới cùng tồn tại trong một hệ thống đang hoạt động ra sao?
Bạn quyết định nhúng tài liệu hay tham chiếu tài liệu trong MongoDB dựa trên kích thước và tần suất cập nhật dữ liệu như thế nào?
Bạn ánh xạ định danh MongoDB và các kiểu BSON sang model Java để tránh lỗi so sánh hoặc tuần tự hóa ra sao?
Bạn tổ chức các thao tác tạo, đọc, cập nhật và xóa MongoDB để giữ đúng điều kiện cập nhật và chống ghi đè ngoài ý muốn như thế nào?
Bạn thiết kế thứ tự trường trong compound index của MongoDB dựa trên điều kiện lọc và sắp xếp ra sao?
Khi một truy vấn MongoDB chậm, bạn đọc kế hoạch thực thi và thống kê quét bản ghi để quyết định thay đổi chỉ mục như thế nào?
Bạn dùng aggregation pipeline của MongoDB khi nào và đánh giá ảnh hưởng của từng giai đoạn đến bộ nhớ như thế nào?
Bạn xác định trường hợp nào thực sự cần transaction nhiều tài liệu trong MongoDB thay vì thiết kế lại ranh giới tài liệu ra sao?
Bạn lựa chọn read concern và write concern của MongoDB theo nhu cầu bền vững dữ liệu và độ trễ như thế nào?
Bạn thiết kế xử lý thay đổi dữ liệu bằng MongoDB change streams để ứng dụng tiếp tục sau gián đoạn mà không bỏ sót sự kiện ra sao?
Bạn lựa chọn Redis làm cache, bộ đếm, hàng đợi hay kho khóa-giá trị chính dựa trên giới hạn bền vững và truy vấn như thế nào?
Bạn phân biệt cache-aside, write-through và write-behind theo thời điểm cập nhật cache và khả năng mất đồng bộ ra sao?
Bạn thiết kế TTL, quy tắc làm mới và chính sách eviction để giảm dữ liệu lỗi thời mà không gây quá tải nguồn dữ liệu như thế nào?
Bạn chọn String, Hash, Set, Sorted Set hoặc Stream của Redis theo những yêu cầu truy cập cụ thể nào?
Bạn khai thác tính nguyên tử của lệnh Redis và nhận diện trường hợp nào cần transaction hoặc script Lua như thế nào?
Bạn phân biệt Redis Pub/Sub với Redis Streams theo yêu cầu lưu vết, xử lý lại và xác nhận tiêu thụ ra sao?
Nếu Redis gặp sự cố khi ứng dụng đang dùng cache, bạn tổ chức fallback và giới hạn tải về cơ sở dữ liệu gốc như thế nào?
Bạn đặt quy ước tên khóa và phiên bản dữ liệu Redis để tránh xung đột giữa nhiều dịch vụ như thế nào?
Bạn nhận diện hot key hoặc cache stampede và xử lý ảnh hưởng đến độ trễ hay thông lượng Redis ra sao?
Bạn phân tích giới hạn của distributed lock sử dụng Redis khi có timeout, trễ mạng hoặc tiến trình tạm dừng như thế nào?
Bạn xác định partition key của Cassandra theo phân phối dữ liệu và các truy vấn cần hỗ trợ như thế nào?
Bạn dùng clustering columns của Cassandra để tổ chức thứ tự dữ liệu trong partition và giới hạn truy vấn theo khoảng như thế nào?
Bạn lựa chọn replication factor và consistency level của Cassandra để cân bằng khả năng chịu lỗi với độ trễ ra sao?
Bạn thiết kế bảng Cassandra bắt đầu từ truy vấn thay vì chuẩn hóa thực thể và xử lý dữ liệu lặp lại như thế nào?
Bạn giải thích ảnh hưởng của tombstone, TTL và xóa dữ liệu đến hiệu năng đọc của Cassandra như thế nào?
Bạn phân biệt batch nhằm gom thay đổi liên quan với batch nhằm tăng tốc ghi trong Cassandra và đánh giá rủi ro ra sao?
Bạn cấu hình phân trang, giới hạn số kết quả và xử lý bất đồng bộ trong Java Cassandra driver như thế nào?
Bạn thiết kế thao tác ghi có thể thử lại an toàn khi kết nối Cassandra lỗi giữa chừng như thế nào?
Bạn xử lý xung đột cập nhật và dữ liệu ghi trễ khi mô hình Cassandra phụ thuộc vào timestamp như thế nào?
Bạn mô hình hóa node, relationship và thuộc tính trong Neo4j từ các câu hỏi nghiệp vụ cần truy vấn như thế nào?
Bạn viết truy vấn Cypher có tham số trong Java để tránh injection và dễ tái sử dụng như thế nào?
Bạn thiết lập constraint và index Neo4j nhằm bảo đảm tính duy nhất và tăng tốc điểm bắt đầu của truy vấn ra sao?
Bạn giới hạn độ sâu và số lượng kết quả khi duyệt đồ thị lớn để tránh truy vấn Neo4j phát triển ngoài kiểm soát như thế nào?
Bạn thiết kế transaction trong Neo4j Java driver để nhiều thay đổi node và relationship thành một đơn vị nhất quán ra sao?
Khi truy vấn Cypher chậm, bạn sử dụng EXPLAIN hoặc PROFILE để tìm nguyên nhân và điều chỉnh mô hình truy vấn như thế nào?
Bạn quản lý đơn vị công việc và khả năng thử lại transaction ở các driver NoSQL khi có lỗi tạm thời như thế nào?
Khi một thao tác nghiệp vụ cập nhật đồng thời MongoDB và Redis, bạn xử lý tính nhất quán giữa hai hệ thống như thế nào?
Bạn thiết kế cơ chế idempotency và chống thực hiện trùng khi ứng dụng không biết chắc yêu cầu ghi trước đã thành công hay chưa ra sao?
Bạn phân loại lỗi xác thực, timeout, quá tải, lỗi ràng buộc và lỗi dữ liệu để đưa ra chính sách retry hay trả lỗi như thế nào?
Bạn thiết kế kiểm thử tích hợp Java với cơ sở dữ liệu NoSQL thực để phát hiện khác biệt so với mock như thế nào?
Bạn giám sát p95 latency, lỗi kết nối, mức dùng pool và truy vấn đắt đỏ để nhận diện điểm nghẽn truy cập NoSQL ra sao?
Bạn áp dụng phân quyền tối thiểu, mã hóa và che dữ liệu nhạy cảm trong truy vấn cũng như log của hệ NoSQL như thế nào?
Bạn xây dựng kế hoạch sao lưu, khôi phục và thử phục hồi dữ liệu NoSQL để đáp ứng yêu cầu mất dữ liệu và thời gian gián đoạn ra sao?

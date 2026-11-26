Khi các trường của đơn hàng thường được đọc cùng nhau, thiết kế document nào phù hợp?
A. Tách tất cả trường sang collection riêng rồi nối khi đọc
B. Nhúng dữ liệu liên quan theo vòng đời truy cập chung
C. Chỉ lưu khóa ngoại và lấy phần còn lại qua cache
D. Lưu bản sao toàn bộ cơ sở dữ liệu vào mỗi document
Đáp án đúng: B

Redis phù hợp lưu session có thời hạn vì hỗ trợ tính năng nào?
A. Khóa ghép nhiều cột với index dạng B-tree
B. Quan hệ đồ thị với truy vấn nhiều bước đi
C. TTL cho khóa và thao tác tra cứu theo khóa
D. Join giữa nhiều collection ở thời điểm đọc
Đáp án đúng: C

Partition key trong Cassandra có vai trò chính nào?
A. Xác định partition để phân bố và tìm dữ liệu
B. Sắp xếp toàn cục mọi hàng trong một cluster
C. Quy định thứ tự thực thi mọi câu ghi đồng thời
D. Chỉ định bộ ánh xạ dữ liệu JSON của driver
Đáp án đúng: A

Ứng dụng hỏi các mối quan hệ nhiều bước giữa người dùng; mô hình nào trực tiếp phù hợp?
A. Graph với đỉnh, cạnh và truy vấn theo quan hệ
B. Key-value với mỗi khóa lưu một số lượng truy vấn
C. Wide-column với mỗi row dùng một cột tổng hợp
D. Document với mỗi thuộc tính ở một collection khác
Đáp án đúng: A

Khi cân nhắc nhúng hay tham chiếu tài liệu trong MongoDB, yếu tố nào cần ưu tiên?
A. Luôn nhúng nếu hai tài liệu có cùng trường tên
B. Luôn tham chiếu nếu cần đọc cả hai trong một request
C. Luôn nhúng toàn bộ dù một tập con tăng không giới hạn
D. Cân nhắc tần suất đọc cùng, kích thước và cập nhật
Đáp án đúng: D

Index phụ trên trường lọc trong MongoDB thường có đánh đổi nào?
A. Giảm chi phí ghi và không dùng thêm bộ nhớ
B. Tăng tốc truy vấn phù hợp, tốn thêm ghi và lưu trữ
C. Đảm bảo mọi truy vấn đều đọc đúng một tài liệu
D. Giúp transaction đa tài liệu luôn chạy song song
Đáp án đúng: B

Nhiều client cần tăng chung một biến đếm trong Redis, hướng nào phù hợp?
A. Đọc GET, tăng trong Java rồi SET ở mỗi client
B. Dùng nhiều khóa riêng rồi chọn giá trị lớn nhất
C. Dùng phép tăng nguyên tử trên một khóa phù hợp
D. Lưu giá trị trong file và tải lại sau mỗi request
Đáp án đúng: C

Thiết kế partition key Cassandra có một giá trị quá phổ biến sẽ gặp rủi ro nào?
A. Mọi node đều nhận cùng số dữ liệu từ mọi partition
B. Mọi row được phân chia đều dù có cùng partition key
C. Driver luôn bật transaction đa partition cho khóa đó
D. Partition nóng gây tải lệch và truy vấn chậm
Đáp án đúng: D

Tăng mức consistency cho truy vấn Cassandra thường tạo đánh đổi nào?
A. Tăng bảo đảm đọc nhưng có thể tăng độ trễ
B. Tăng throughput mà không ảnh hưởng thời gian chờ
C. Giảm mức đồng thuận vì chỉ cần một replica trả lời
D. Thay thế hoàn toàn nhu cầu chọn partition key
Đáp án đúng: A

Muốn tìm đường liên kết giữa các thực thể trong Neo4j, cách nào tự nhiên nhất?
A. Quét toàn bộ khóa Redis rồi ghép dữ liệu ở Java
B. Tạo bảng SQL tạm từ mọi node trước khi tìm
C. Lấy document MongoDB rồi tìm theo nested array
D. Dùng Cypher MATCH diễn tả mẫu đỉnh và quan hệ
Đáp án đúng: D

Java gọi NoSQL server qua mạng cần xử lý lỗi tạm thời ra sao?
A. Thử lại mọi lệnh ghi dù có thể tạo tác dụng lặp
B. Giới hạn timeout, retry có điều kiện và ghi nhận lỗi
C. Bỏ timeout để chờ đến khi server tự phục hồi
D. Xóa tất cả kết nối khi một truy vấn chậm bất thường
Đáp án đúng: B

Khi retry một lần ghi sau khi mất phản hồi, tại sao cần xét tính idempotent?
A. Vì mọi retry đều tự hủy lần ghi đã được xác nhận
B. Vì yêu cầu có thể đã thành công trước khi mất phản hồi
C. Vì driver luôn tự chuyển lần ghi sang transaction mới
D. Vì việc retry bảo đảm không có thao tác ghi trùng
Đáp án đúng: B

Trong MongoDB, khi nào cần transaction đa tài liệu?
A. Khi ghi một field trong một document đơn lẻ
B. Khi đọc một document bằng khóa đã đánh index
C. Khi nhiều document cần cùng thành công hoặc rollback
D. Khi truy vấn aggregation chỉ tính tổng không ghi
Đáp án đúng: C

Khi dùng Redis làm cache cho dữ liệu cập nhật ở nơi khác, vấn đề nào cần xử lý?
A. Dữ liệu cache cũ và chính sách làm mới/xóa cache
B. Mọi khóa cache luôn đồng bộ ngay với dữ liệu gốc
C. Redis bắt buộc tạo join giữa cache và database
D. Mọi truy vấn cache phải thực thi trong transaction SQL
Đáp án đúng: A

Index trong Neo4j thường giúp cải thiện bước nào của truy vấn?
A. Biến mọi quan hệ thành trường JSON không có cạnh
B. Bỏ hoàn toàn chi phí đi qua mọi cạnh của đồ thị
C. Lưu thứ tự cập nhật của tất cả node trong cluster
D. Tìm nhanh node khởi đầu qua thuộc tính phù hợp
Đáp án đúng: D

Khi chọn document, key-value, wide-column hoặc graph, căn cứ nào quan trọng nhất?
A. Chỉ dựa số lượng driver Java có thể cài đặt
B. Chỉ dựa kích thước của file cấu hình kết nối
C. Dựa mẫu truy cập, quan hệ dữ liệu và yêu cầu nhất quán
D. Dựa tốc độ khởi động ứng dụng khi chưa chạy query
Đáp án đúng: C

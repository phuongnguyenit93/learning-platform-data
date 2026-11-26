Bạn sẽ giải thích phạm vi chuẩn Jakarta Persistence và vai trò của nhà cung cấp triển khai ORM như thế nào?
Bạn sẽ xác định trường hợp nào nên sử dụng JPA thay vì truy cập cơ sở dữ liệu trực tiếp bằng SQL như thế nào?
Bạn sẽ thiết kế entity đầu tiên với khóa chính và ánh xạ bảng sao cho danh tính đối tượng nhất quán ra sao?
Bạn sẽ lựa chọn giữa khóa tự nhiên và khóa thay thế cho một entity theo những tiêu chí nào?
Bạn sẽ so sánh các chiến lược sinh giá trị khóa chính của JPA và ảnh hưởng của chúng tới thao tác ghi như thế nào?
Khi một khóa chính gồm nhiều cột, bạn sẽ cân nhắc dùng EmbeddedId hay IdClass dựa trên yếu tố nào?
Bạn sẽ phân biệt entity, embeddable và mapped superclass khi thiết kế mô hình miền như thế nào?
Bạn sẽ kiểm soát ánh xạ tên cột, độ dài, khả năng null và ràng buộc duy nhất giữa mã Java và cơ sở dữ liệu ra sao?
Bạn sẽ đánh giá cách ánh xạ enum để tránh sai lệch dữ liệu khi danh sách giá trị thay đổi như thế nào?
Bạn sẽ lựa chọn chiến lược ánh xạ kế thừa nào khi các lớp con có cấu trúc và yêu cầu truy vấn khác nhau?
Bạn sẽ phân biệt các trạng thái mới, managed, detached và removed của một entity qua tình huống thực tế ra sao?
Bạn sẽ giải thích cơ chế bảo đảm một thể hiện managed duy nhất cho cùng một định danh trong persistence context như thế nào?
Khi sửa thuộc tính entity managed mà không gọi phương thức update, bạn sẽ giải thích điều kiện để thay đổi được ghi xuống cơ sở dữ liệu ra sao?
Bạn sẽ phân biệt flush và commit trong JPA, kể cả trường hợp flush thành công nhưng transaction thất bại, như thế nào?
Bạn sẽ xem xét chế độ flush của persistence context khi truy vấn cần nhìn thấy các thay đổi chưa commit ra sao?
Khi gọi persist trên một đối tượng mới, bạn sẽ phân tích thời điểm sinh khóa và phát lệnh INSERT dựa trên điều gì?
Bạn sẽ giải thích việc merge một entity detached trả về đối tượng managed khác với đối tượng đầu vào như thế nào?
Khi gọi remove trên một entity, bạn sẽ phân tích trạng thái đối tượng và thời điểm hàng dữ liệu thực sự bị xóa ra sao?
Bạn sẽ xác định ranh giới transaction và thời gian sống của persistence context trong một luồng xử lý nghiệp vụ như thế nào?
Bạn sẽ so sánh transaction do ứng dụng quản lý và transaction do môi trường Jakarta EE quản lý như thế nào?
Khi một thao tác ghi gồm nhiều entity liên quan, bạn sẽ bảo đảm tính nguyên tử và xử lý rollback bằng cách nào?
Bạn sẽ phân biệt quan hệ ManyToOne, OneToMany, OneToOne và ManyToMany khi chuyển mô hình dữ liệu quan hệ sang entity ra sao?
Bạn sẽ xác định phía sở hữu quan hệ hai chiều và vai trò của mappedBy trong việc ghi khóa ngoại như thế nào?
Khi thêm một phần tử vào collection quan hệ hai chiều, bạn sẽ giữ hai phía của mô hình đối tượng đồng bộ ra sao?
Bạn sẽ phân biệt cascade persist, merge và remove với quy tắc ràng buộc khóa ngoại của cơ sở dữ liệu như thế nào?
Bạn sẽ lựa chọn sử dụng orphanRemoval khi vòng đời đối tượng con thuộc quyền sở hữu của đối tượng cha dựa trên điều gì?
Bạn sẽ xác định khi nào nên dùng bảng nối thay vì khóa ngoại trực tiếp cho một quan hệ như thế nào?
Bạn sẽ giải thích rủi ro N+1 query khi duyệt một tập entity có quan hệ lazy bằng ví dụ nào?
Bạn sẽ cân nhắc giữa fetch eager và lazy theo đặc điểm truy vấn và chi phí tải dữ liệu như thế nào?
Bạn sẽ dùng JOIN FETCH trong JPQL để giải quyết một trường hợp N+1 và đánh giá rủi ro nhân bản dòng kết quả ra sao?
Bạn sẽ lựa chọn entity graph cho những tình huống cần kế hoạch tải dữ liệu khác nhau như thế nào?
Khi cần phân trang qua quan hệ một-nhiều, bạn sẽ kiểm tra hệ quả của việc fetch collection cùng truy vấn phân trang ra sao?
Bạn sẽ viết một truy vấn JPQL theo quan hệ entity thay vì theo tên bảng và cột như thế nào?
Bạn sẽ xác định khi nào nên dùng truy vấn projection hoặc DTO thay vì lấy toàn bộ entity ra sao?
Bạn sẽ sử dụng tham số truy vấn để bảo đảm giá trị đầu vào được xử lý đúng và tránh nối chuỗi truy vấn như thế nào?
Bạn sẽ chọn Criteria API thay cho JPQL viết trực tiếp khi các điều kiện lọc được xây dựng động dựa trên yêu cầu nào?
Bạn sẽ xây dựng truy vấn động bằng Criteria API mà vẫn kiểm soát kiểu dữ liệu và liên kết quan hệ ra sao?
Bạn sẽ phân tích sự khác nhau giữa truy vấn đọc thông thường và bulk UPDATE hoặc DELETE đối với persistence context như thế nào?
Sau một lệnh bulk update, bạn sẽ xử lý dữ liệu entity đã được quản lý nhưng có thể cũ bằng cách nào?
Bạn sẽ thiết kế cơ chế khóa lạc quan với trường phiên bản và giải quyết xung đột cập nhật đồng thời ra sao?
Bạn sẽ so sánh optimistic locking và pessimistic locking theo tần suất xung đột, thời gian giữ khóa và độ trễ như thế nào?
Khi truy vấn sử dụng khóa bi quan có nguy cơ chờ lâu hoặc deadlock, bạn sẽ đánh giá và xử lý tình huống ra sao?
Bạn sẽ xem xét tác động của equals và hashCode đối với entity có khóa được cấp sau khi persist như thế nào?
Bạn sẽ xác định khi nào cần chuyển đổi kiểu dữ liệu bằng AttributeConverter và kiểm tra tính nhất quán lưu trữ ra sao?
Bạn sẽ dùng callback vòng đời entity cho mục đích nào và giới hạn logic nghiệp vụ đưa vào callback như thế nào?
Khi một entity detached được chuyển qua tầng API, bạn sẽ tránh phụ thuộc vào việc tải quan hệ lazy ngoài persistence context ra sao?
Bạn sẽ điều tra trường hợp số câu SQL phát sinh nhiều bất thường trong một thao tác nghiệp vụ bằng cách nào?
Bạn sẽ kiểm tra tính đúng của ánh xạ entity và transaction bằng loại kiểm thử tích hợp nào?
Bạn sẽ phân biệt hành vi được chuẩn JPA bảo đảm với tính năng riêng của nhà cung cấp khi đánh giá tính di động của ứng dụng như thế nào?
Khi nâng cấp Jakarta Persistence hoặc thay nhà cung cấp ORM, bạn sẽ lập kế hoạch xác minh các ánh xạ và truy vấn trọng yếu ra sao?

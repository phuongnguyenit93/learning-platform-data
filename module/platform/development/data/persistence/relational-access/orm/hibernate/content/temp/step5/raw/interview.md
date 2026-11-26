Bạn phân biệt Hibernate ORM với đặc tả JPA và JDBC thuần khi lựa chọn công nghệ truy cập dữ liệu Java như thế nào?
Bạn giải thích vai trò của SessionFactory, Session và EntityManager trong vòng đời một yêu cầu nghiệp vụ như thế nào?
Bạn xác định một entity, thuộc tính định danh và bảng tương ứng trong Hibernate dựa trên mô hình nghiệp vụ ra sao?
Bạn thiết kế chiến lược sinh khóa chính như IDENTITY, SEQUENCE hoặc khóa do ứng dụng tạo và đánh giá ảnh hưởng đến batching như thế nào?
Bạn lựa chọn kiểu dữ liệu cho thuộc tính entity để ánh xạ chính xác các cột số, tiền tệ và thời gian ra sao?
Bạn tổ chức mapping cho value object bằng embeddable hoặc converter thay vì tách thành entity khi nào?
Bạn xác định ranh giới aggregate và tránh để entity chứa quá nhiều quan hệ phụ thuộc như thế nào?
Bạn lựa chọn giữa quan hệ một chiều và hai chiều khi ánh xạ @OneToMany hoặc @ManyToOne theo nhu cầu truy vấn ra sao?
Bạn giải thích phía sở hữu quan hệ trong mapping hai chiều và cách cập nhật cả hai phía trong mã Java như thế nào?
Bạn phân biệt cascade persist, merge, remove và orphan removal về tác động đến dữ liệu liên quan ra sao?
Bạn ngăn việc xóa nhầm dữ liệu khi áp dụng cascade trên quan hệ many-to-many như thế nào?
Bạn ánh xạ quan hệ nhiều-nhiều có thuộc tính bổ sung bằng entity liên kết như thế nào?
Bạn lựa chọn các chiến lược kế thừa entity và đánh giá ảnh hưởng đến schema cùng truy vấn ra sao?
Bạn xử lý equals và hashCode của entity có ID được sinh sau khi lưu để tránh lỗi trong collection như thế nào?
Bạn giải thích vòng đời transient, managed, detached và removed của entity bằng những thao tác điển hình như thế nào?
Bạn phân biệt persist và merge khi làm việc với entity mới hoặc detached, đặc biệt giá trị đối tượng trả về ra sao?
Bạn lý giải cơ chế dirty checking và cách Hibernate xác định thay đổi cần phát SQL UPDATE như thế nào?
Bạn xác định phạm vi persistence context để bảo đảm cùng một bản ghi được quản lý nhất quán trong một transaction ra sao?
Bạn phân biệt flush với commit và giải thích thời điểm Hibernate gửi SQL xuống cơ sở dữ liệu như thế nào?
Bạn lựa chọn flush mode và quyết định khi nào cần flush tường minh mà không làm suy giảm hiệu năng ra sao?
Bạn phân tích thứ tự các lệnh INSERT, UPDATE và DELETE trong action queue khi dữ liệu có ràng buộc khóa ngoại như thế nào?
Bạn thiết kế transaction ở tầng service để nhiều thao tác Hibernate cùng thành công hoặc cùng rollback như thế nào?
Bạn xử lý trạng thái Session và entity sau khi một transaction ném ngoại lệ để tránh sử dụng tiếp dữ liệu không còn tin cậy ra sao?
Bạn phân biệt optimistic locking bằng @Version với pessimistic locking khi nhiều yêu cầu cùng cập nhật một entity như thế nào?
Khi xảy ra OptimisticLockException, bạn quyết định thử lại hay yêu cầu người dùng giải quyết xung đột theo tiêu chí nào?
Bạn giải thích sự khác biệt giữa transaction isolation của cơ sở dữ liệu và các bảo đảm mà Hibernate cung cấp như thế nào?
Bạn lựa chọn LAZY hoặc EAGER cho từng association dựa trên đường truy cập dữ liệu của use case như thế nào?
Bạn nhận diện N+1 query từ log SQL hoặc thống kê Hibernate và truy tìm quan hệ gây ra nó ra sao?
Bạn sử dụng fetch join, EntityGraph hoặc batch fetching để xử lý N+1 trong những tình huống khác nhau như thế nào?
Bạn phân tích rủi ro cartesian product khi fetch nhiều collection cùng lúc và điều chỉnh truy vấn ra sao?
Khi cần phân trang danh sách cha và nạp nhiều con, bạn thiết kế truy vấn để không phân trang sai do fetch join như thế nào?
Bạn giải thích nguyên nhân LazyInitializationException và thiết kế lớp service hoặc DTO để xử lý đúng ranh giới Session ra sao?
Bạn đánh giá mặt lợi và chi phí của Open Session in View khi view có thể truy cập association chưa được tải như thế nào?
Bạn lựa chọn projection DTO thay vì nạp đầy đủ entity để tạo API trả dữ liệu chỉ đọc trong trường hợp nào?
Bạn phân biệt HQL với SQL và cách HQL tham chiếu entity cùng thuộc tính thay vì tên bảng như thế nào?
Bạn dùng tham số có tên trong HQL để phòng ngừa SQL injection và xử lý bộ lọc động ra sao?
Bạn lựa chọn Criteria API hoặc HQL khi phải kết hợp nhiều điều kiện truy vấn tùy chọn như thế nào?
Bạn thiết kế bulk update hoặc delete bằng HQL và xử lý sự lệch trạng thái của persistence context sau đó ra sao?
Bạn phân biệt cache cấp một, cache cấp hai và query cache theo phạm vi, vòng đời và điều kiện vô hiệu ra sao?
Bạn lựa chọn entity nào được cache cấp hai và thiết lập chính sách nhất quán khi dữ liệu thay đổi thường xuyên như thế nào?
Bạn phân tích nguy cơ dữ liệu cũ khi ứng dụng khác cập nhật trực tiếp bảng đang được Hibernate cache ra sao?
Bạn thiết kế cơ chế ghi hàng loạt với JDBC batching của Hibernate và kiểm tra tác động của khóa sinh tự động như thế nào?
Bạn giới hạn kích thước persistence context khi nhập hàng chục nghìn bản ghi để tránh tăng bộ nhớ do entity được quản lý ra sao?
Bạn cân nhắc sử dụng StatelessSession hoặc truy vấn streaming cho tác vụ xử lý dữ liệu lớn dựa trên giới hạn tính năng nào?
Bạn giải thích cách Hibernate sử dụng connection pool, thời điểm lấy kết nối và rủi ro của transaction kéo dài như thế nào?
Bạn thiết lập timeout, read-only và cơ chế hủy công việc để tránh truy vấn Hibernate chiếm tài nguyên quá lâu ra sao?
Bạn đánh giá tác động của lazy proxy và bytecode enhancement đối với khả năng truy cập thuộc tính cũng như kiểm thử như thế nào?
Bạn dùng AttributeConverter hoặc kiểu mapping tùy chỉnh để lưu enum và giá trị nghiệp vụ ổn định khi mã thay đổi ra sao?
Bạn thiết kế chiến lược thay đổi schema khi một phiên bản entity mới phải hoạt động cùng ứng dụng đang chạy phiên bản cũ như thế nào?
Khi Hibernate báo lỗi mapping lúc khởi động, bạn kiểm tra annotation, quan hệ, tên cột và kiểu dữ liệu theo thứ tự nào?
Bạn cấu hình log SQL, bind parameter và thống kê Hibernate để chẩn đoán hiệu năng mà không để lộ dữ liệu nhạy cảm như thế nào?
Bạn kết hợp số câu SQL do Hibernate phát sinh với EXPLAIN của cơ sở dữ liệu để tối ưu truy vấn và index ra sao?
Bạn thiết kế kiểm thử tích hợp Hibernate để phát hiện lỗi flush, cascade, lazy loading và transaction bằng cơ sở dữ liệu thực như thế nào?
Bạn bảo đảm điều kiện lọc tenant được áp dụng nhất quán cho truy vấn entity trong ứng dụng đa khách hàng như thế nào?
Bạn đo số lần tải entity, cache hit, số câu SQL, p95 latency và bộ nhớ để đánh giá một thay đổi tối ưu Hibernate như thế nào?

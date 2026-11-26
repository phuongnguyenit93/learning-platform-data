Câu 1. Một lớp được đánh dấu @Entity nhưng chưa có khóa định danh; cần bổ sung gì để ánh xạ JPA hợp lệ?
A. Khai báo @Version cho một thuộc tính đếm phiên bản
B. Khai báo @Table để chỉ tên bảng của thực thể
C. Khai báo @Id hoặc @EmbeddedId cho định danh
D. Khai báo @Transient cho mọi thuộc tính dữ liệu
Đáp án đúng: C

Câu 2. Trong quan hệ hai chiều @OneToMany và @ManyToOne dùng khóa ngoại, phía nào thường sở hữu quan hệ?
A. Phía @ManyToOne quản lý cột khóa ngoại
B. Phía @OneToMany dùng thuộc tính mappedBy
C. Phía có getter được khai báo trước trong mã
D. Phía entity có nhiều trường dữ liệu hơn
Đáp án đúng: A

Câu 3. Thuộc tính mappedBy trên phía không sở hữu quan hệ trỏ tới thành phần nào?
A. Tên bảng chứa khóa ngoại trong cơ sở dữ liệu
B. Tên cột khóa chính ở entity phía không sở hữu
C. Tên constraint của quan hệ trong schema SQL
D. Tên thuộc tính quan hệ ở entity phía sở hữu
Đáp án đúng: D

Câu 4. Khi EntityManager.flush() được gọi trong transaction, điều gì được đảm bảo?
A. Đồng bộ thay đổi đang chờ xuống cơ sở dữ liệu
B. Transaction được commit và kết thúc ngay lập tức
C. Mọi entity đã quản lý bị chuyển sang detached
D. Persistence context bị xóa khỏi bộ nhớ tức thì
Đáp án đúng: A

Câu 5. Một entity managed được sửa trường basic trong transaction; JPA có thể ghi thay đổi bằng cách nào?
A. Chỉ ghi khi gọi persist() lại trên entity đó
B. Phát hiện thay đổi và đồng bộ khi flush
C. Luôn yêu cầu gọi merge() trên entity managed
D. Chỉ ghi khi lập trình viên chạy câu UPDATE SQL
Đáp án đúng: B

Câu 6. Gọi EntityManager.detach(entity) với entity đang managed dẫn đến trạng thái nào?
A. Entity bị xóa khỏi mọi bảng trong cơ sở dữ liệu
B. Entity được tự động ghi vĩnh viễn vào transaction
C. Entity không còn được context theo dõi thay đổi
D. Entity bắt đầu một transaction độc lập mới
Đáp án đúng: C

Câu 7. Khi gọi merge(detachedEntity), đối tượng nào là bản managed để tiếp tục thao tác?
A. Đối tượng detached ban đầu luôn trở lại managed
B. Đối tượng được merge() trả về trong context
C. Tất cả đối tượng cùng ID đều chuyển managed
D. Mọi tham chiếu của ứng dụng tự đổi sang bản mới
Đáp án đúng: B

Câu 8. Với entity mới chưa được quản lý, EntityManager.persist() có tác dụng nào?
A. Đánh dấu entity là detached để xử lý sau
B. Đọc lại entity đang tồn tại từ cơ sở dữ liệu
C. Thực thi ngay commit của toàn bộ transaction
D. Đưa entity vào context để quản lý và ghi mới
Đáp án đúng: D

Câu 9. Trong cùng persistence context, gọi find() hai lần cho một entity và khóa chính thường có tính chất gì?
A. Trả cùng instance managed theo định danh đó
B. Luôn tạo hai instance detached tách biệt nhau
C. Luôn đọc hai bản dữ liệu riêng biệt từ đĩa
D. Trả một proxy mới dù entity đã được quản lý
Đáp án đúng: A

Câu 10. Trong JPQL, câu SELECT e FROM Employee e tham chiếu Employee dưới dạng gì?
A. Tên bảng SQL có trong schema của database
B. Tên entity được JPA khai báo trong mô hình
C. Tên file Java do bộ biên dịch tạo ra lúc build
D. Tên cột chứa mã định danh của bảng dữ liệu
Đáp án đúng: B

Câu 11. Truy vấn JPQL có biến điều kiện nhận input người dùng nên được xây dựng thế nào?
A. Ghép chuỗi input trực tiếp vào biểu thức WHERE
B. Tự bao input bằng dấu nháy rồi nối vào JPQL
C. Dùng parameter binding thay cho nối chuỗi
D. Thay mọi ký tự đặc biệt bằng khoảng trắng
Đáp án đúng: C

Câu 12. Khi truy cập association LAZY cho từng entity cha gây N+1, hướng khắc phục phù hợp là gì?
A. Bắt buộc đổi toàn bộ association thành EAGER
B. Chọn JOIN FETCH hoặc entity graph đúng nhu cầu
C. Gọi flush() sau mỗi lần lấy collection con
D. Tắt transaction rồi truy cập lần lượt từng cha
Đáp án đúng: B

Câu 13. Vì sao không nên mặc định gán EAGER cho tất cả quan hệ giữa các entity?
A. EAGER không thể dùng cùng khóa ngoại trong JPA
B. EAGER luôn khiến mọi truy vấn trả dữ liệu sai
C. EAGER cấm đồng bộ entity trong một transaction
D. EAGER có thể tải thêm dữ liệu không cần dùng
Đáp án đúng: D

Câu 14. Khi điều kiện truy vấn được ghép động theo bộ lọc, Criteria API hữu ích ở điểm nào?
A. Tạo cây biểu thức truy vấn bằng API đối tượng
B. Bỏ hoàn toàn bước biên dịch truy vấn sang SQL
C. Tự động bảo đảm mọi truy vấn dùng cùng index
D. Thay thế mọi thao tác khóa và transaction JPA
Đáp án đúng: A

Câu 15. Với hai thao tác ghi cần thành công hoặc thất bại cùng nhau, nên áp dụng điều gì?
A. Gọi flush() ngay sau từng thao tác ghi riêng
B. Gọi detach() để cả hai entity độc lập hơn
C. Đặt cả hai thao tác ngoài transaction hiện tại
D. Bao cả hai thao tác trong cùng transaction
Đáp án đúng: D

Câu 16. Entity có @Version bị cập nhật đồng thời; optimistic locking nhằm phát hiện trường hợp nào?
A. Hai session đọc cùng một entity chưa đổi
B. Hai truy vấn chỉ đọc chạy song song không khóa
C. Bản cập nhật dựa trên version đã lỗi thời
D. Một giao dịch đọc entity từ cache cấp một
Đáp án đúng: C

Câu 17. Khi dùng LockModeType.PESSIMISTIC_WRITE trong transaction, mục tiêu thường là gì?
A. Tránh tải entity liên quan theo chiến lược LAZY
B. Xin khóa ghi phía database để phối hợp cập nhật
C. Tự động tăng version khi chỉ thực hiện SELECT
D. Buộc mọi truy vấn về entity thành câu JPQL
Đáp án đúng: B

Câu 18. CascadeType.REMOVE trên quan hệ entity có ý nghĩa nào?
A. Lan truyền thao tác remove sang entity liên quan
B. Tự xóa mọi entity không còn trong persistence context
C. Ngăn transaction xóa entity nếu có collection con
D. Đổi trạng thái các entity liên quan sang managed
Đáp án đúng: A

Câu 19. orphanRemoval=true trên quan hệ cha-con thường được dùng để làm gì?
A. Chỉ chuyển entity con sang detached khi bỏ khỏi cha
B. Chỉ xóa association nhưng luôn giữ bản ghi con
C. Xóa entity con mồ côi khi bị gỡ khỏi quan hệ
D. Tự đánh dấu cha là removed khi xóa một entity con
Đáp án đúng: C

Câu 20. @GeneratedValue trên khóa @Id thường giao trách nhiệm nào cho provider và database?
A. Sinh khóa chính theo chiến lược đã cấu hình
B. Tự chọn khóa ngoại cho các quan hệ @ManyToOne
C. Sinh luôn giá trị cho mọi trường dữ liệu cơ bản
D. Chuyển mọi khóa tổng hợp thành chuỗi tự tăng
Đáp án đúng: A

Câu 21. Sự khác biệt đúng giữa @Embeddable và @Entity trong mô hình JPA là gì?
A. @Embeddable bắt buộc có @Id duy nhất riêng
B. @Entity không thể tham chiếu tới @Embeddable
C. @Embeddable luôn được lưu trong bảng độc lập
D. @Embeddable là value type không có identity riêng
Đáp án đúng: D

Câu 22. Sau JPQL bulk UPDATE, vì sao có thể cần refresh() hoặc clear() persistence context?
A. Bulk UPDATE luôn tự xóa tất cả entity khỏi cache
B. Bulk UPDATE không đồng bộ từng instance managed
C. Bulk UPDATE mặc định đóng EntityManager ngay
D. Bulk UPDATE luôn chuyển các entity sang removed
Đáp án đúng: B

Câu 23. Khi đọc một danh sách entity cha rồi truy cập collection LAZY của từng cha, dấu hiệu N+1 là gì?
A. Một query đầu luôn đủ dữ liệu mọi quan hệ
B. Mọi lần truy cập collection chỉ dùng cache cấp hai
C. Nhiều query bổ sung phát sinh theo từng cha
D. Mỗi entity con tạo riêng một transaction mới
Đáp án đúng: C

Câu 24. Callback @PrePersist trên entity được gọi trong giai đoạn nào?
A. Ngay sau khi transaction của entity được commit
B. Sau khi entity bị xóa khỏi persistence context
C. Ngay trước khi EntityManager đóng hẳn session
D. Trước khi thực hiện lệnh INSERT của entity mới
Đáp án đúng: D

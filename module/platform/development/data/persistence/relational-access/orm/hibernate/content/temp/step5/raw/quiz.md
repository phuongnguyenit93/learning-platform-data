Mối quan hệ chính giữa JPA và Hibernate ORM là gì?
A. JPA là đặc tả ORM; Hibernate cung cấp triển khai
B. JPA là driver SQL; Hibernate là cơ sở dữ liệu
C. JPA là bộ nhớ cache; Hibernate là giao thức mạng
D. JPA là schema vật lý; Hibernate là connection pool
Đáp án đúng: A

Entity Java vừa tạo bằng new, chưa lưu hay gắn Session, ở trạng thái nào?
A. Managed: đang được Session theo dõi thay đổi
B. Detached: từng managed nhưng đã rời Session
C. Removed: đã được đánh dấu xóa trong Session
D. Transient: chưa được quản lý bởi Session
Đáp án đúng: D

Gọi persist() trên entity mới trong một Session phù hợp thường dẫn đến điều gì?
A. Entity lập tức bị detach và không thể ghi thay đổi
B. Entity trở thành managed; INSERT có thể đợi flush
C. Entity chỉ được lưu nếu gọi merge lần thứ hai
D. Entity được đưa vào cache cấp hai không cần SQL
Đáp án đúng: B

Khi merge() entity detached, hiểu đúng về đối tượng trả về là gì?
A. Entity gốc tự đổi thành managed trong mọi trường hợp
B. Entity gốc bị xóa khỏi DB trước khi được cập nhật
C. Một proxy chưa có state được trả về bất kể dữ liệu
D. Bản managed nhận state sao chép từ entity detached
Đáp án đúng: D

Dirty checking của Hibernate được dùng cho nhiệm vụ nào?
A. Chỉ phát hiện lỗi cú pháp SQL khi biên dịch
B. Chỉ đối chiếu tên bảng và trường từ JDBC metadata
C. Theo dõi thay đổi entity managed để flush
D. Tự đánh lại version database sau mỗi lần SELECT
Đáp án đúng: C

Sự khác biệt quan trọng giữa flush và commit trong Hibernate là gì?
A. Flush luôn hoàn tất giao dịch, commit chỉ ghi log
B. Commit chỉ làm mới cache mà không chạm database
C. Flush gửi SQL nhưng transaction chưa commit
D. Flush chỉ xảy ra sau khi toàn bộ Session đóng lại
Đáp án đúng: C

Cache cấp một của Hibernate thường nằm trong phạm vi nào?
A. Persistence context gắn với một Session
B. Toàn bộ các Session trên mọi máy chạy ứng dụng
C. Một cache riêng dùng chung bởi mọi Java process
D. Tất cả transaction ở cùng database instance
Đáp án đúng: A

Trong HQL, tên xuất hiện trong FROM và đường dẫn thuộc tính thường là gì?
A. Tên bảng vật lý và tên cột trong schema SQL
B. Entity và các thuộc tính đã mapping trong Java
C. Tên file XML và tên bean của Spring context
D. Tên index vật lý và con trỏ ResultSet JDBC
Đáp án đúng: B

Truy cập lazy association của từng entity trong vòng lặp dễ gây hiệu ứng nào?
A. Mọi dữ liệu được tải trước bởi một SELECT lớn
B. Mọi entity được cache trong bộ nhớ toàn hệ thống
C. Mọi association được cập nhật ngay vào database
D. N+1 SELECT do từng liên kết phát sinh truy vấn
Đáp án đúng: D

Khi cần tải một quan hệ cho tập entity, cách nào có thể giảm N+1?
A. Chuyển mọi association sang EAGER vô điều kiện
B. Dùng join fetch cho quan hệ cần tải cùng
C. Vô hiệu hóa mọi index trong bảng liên kết
D. Gọi flush trước mỗi lần truy cập collection
Đáp án đúng: B

LazyInitializationException thường xảy ra trong tình huống nào?
A. Chỉ gọi persist với entity chưa có ID database
B. Gọi commit trước khi flush một phiên làm việc
C. Đọc thuộc tính lazy sau khi Session đóng
D. Một transaction đọc dữ liệu đã được đánh index
Đáp án đúng: C

Cache cấp hai Hibernate, khi được cấu hình, có đặc điểm nào?
A. Luôn thay thế cache cấp một của mọi Session
B. Chỉ sống trong một method gọi Session.get()
C. Dữ liệu có thể được cache qua nhiều Session
D. Bắt buộc lưu mọi object có trong bảng SQL
Đáp án đúng: C

Cơ chế optimistic locking bằng trường version giúp xử lý điều gì?
A. Phát hiện cập nhật cạnh tranh dựa trên version
B. Buộc mọi thread lấy lock trước khi truy vấn
C. Cho phép sửa đè dữ liệu mà không kiểm tra version
D. Ngăn mọi truy vấn SELECT khi có UPDATE đồng thời
Đáp án đúng: A

Khi cấu hình JDBC batching trong Hibernate, mục tiêu nào phù hợp?
A. Tự thay đổi isolation của mọi transaction ghi
B. Chạy toàn bộ SQL không cần connection pool
C. Bảo đảm mọi lệnh ghi vượt qua kiểm tra ràng buộc
D. Gom lệnh tương thích để giảm lượt gửi đến DB
Đáp án đúng: D

Trong mapping entity, quan hệ nhiều bản ghi trỏ đến một đối tượng thường dùng gì?
A. `@OneToOne` cho mỗi bản ghi trỏ đến cùng một đối tượng
B. `@ManyToOne` cho khóa ngoại đến entity đích
C. `@ElementCollection` để ánh xạ sang bảng cha
D. `@Transient` để giữ nguyên quan hệ trong database
Đáp án đúng: B

Để chẩn đoán query Hibernate chậm, cần xem bộ bằng chứng nào?
A. Xem SQL chạy thật, tham số và execution plan
B. Chỉ tên lớp entity nằm trong Java package
C. Chỉ thứ tự khai báo annotation trong source
D. Chỉ số lượng method getter trong lớp DTO
Đáp án đúng: A

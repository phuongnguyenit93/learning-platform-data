Hai nhóm chạy các stack Compose có service trùng tên trên cùng một máy. Cách nào giúp tách tài nguyên do Compose tự quản lý?
A. Đưa các service vào chung external network để chia sẻ DNS.
B. Đặt tên project riêng để tách network và volume mặc định.
C. Đổi thứ tự khai báo service giữa các tệp Compose của nhóm.
D. Giữ một project name nhưng đổi tag image của từng service.
Đáp án đúng: B

Service api và db dùng chung network mặc định của Compose, database nghe cổng 5432. API nên kết nối bằng địa chỉ nào?
A. Dùng localhost:5432 vì các container chia sẻ loopback của host.
B. Dùng host.docker.internal:5432 dù cổng db chưa publish.
C. Dùng db:5432 vì service name được phân giải trong network.
D. Dùng 127.0.0.1:5432 vì Compose nối các loopback với nhau.
Đáp án đúng: C

Một service API khai báo depends_on dạng danh sách để phụ thuộc vào db. Điều gì được Compose bảo đảm khi khởi động?
A. Database đã hoàn tất khởi tạo schema trước khi API chạy.
B. Cổng TCP của database đã được xác nhận kết nối thành công.
C. Container db được khởi động trước, chưa chắc đã sẵn sàng.
D. API được khởi động lại nếu database chuyển sang unhealthy.
Đáp án đúng: C

Muốn API chỉ bắt đầu khởi động sau khi db vượt qua kiểm tra sức khỏe, cấu hình Compose nào phù hợp?
A. Thêm healthcheck cho db và đặt depends_on condition: service_healthy.
B. Dùng depends_on dạng danh sách và tăng timeout cho API.
C. Chỉ đặt restart: always cho db và bỏ qua healthcheck.
D. Publish cổng db lên host trước khi tạo container API.
Đáp án đúng: A

PostgreSQL trong Compose phải giữ dữ liệu sau khi container bị xóa rồi tạo lại. Cách nào phù hợp nhất?
A. Gắn named volume vào thư mục dữ liệu của PostgreSQL.
B. Gắn tmpfs vào thư mục dữ liệu của PostgreSQL.
C. Giữ dữ liệu trong writable layer của container.
D. Đóng gói dữ liệu cần lưu vào image PostgreSQL lúc build.
Đáp án đúng: A

Bạn cần gỡ container và network mặc định của stack kiểm thử nhưng vẫn giữ named volume của PostgreSQL. Lệnh nào phù hợp?
A. docker compose down -v, xóa cả stack và các volume đã khai báo.
B. docker compose rm -v, xóa container dừng và volume gắn.
C. docker compose stop, dừng container nhưng giữ network cũ.
D. docker compose down, bỏ container và network, giữ named volume.
Đáp án đúng: D

Một tệp .env nằm cạnh compose.yaml có biến DB_PASSWORD, nhưng service không dùng environment hoặc env_file để truyền biến. Kết luận nào đúng?
A. Compose tự động đưa DB_PASSWORD vào mọi container của project.
B. Compose dùng .env cho nội suy, không tự đưa biến vào container.
C. Compose mặc định mount DB_PASSWORD như tệp secret trong service.
D. Compose ghi DB_PASSWORD vào image dù không có tham chiếu.
Đáp án đúng: B

Service khai báo MODE=staging trong env_file nhưng MODE=production trong environment. Container sẽ nhận giá trị nào?
A. MODE=staging vì env_file được ưu tiên hơn environment.
B. MODE=production vì environment được ưu tiên hơn env_file.
C. Không nhận MODE vì Compose bỏ biến xuất hiện ở hai nơi.
D. MODE tùy theo thứ tự các service được khai báo trong compose.yaml.
Đáp án đúng: B

Ứng dụng có thể đọc mật khẩu từ tệp thay vì biến môi trường. Cách nào phù hợp để cấp bí mật bằng Docker Compose?
A. Đưa mật khẩu vào environment và đặt giá trị trong dấu nháy.
B. Đưa mật khẩu vào env_file được commit cùng compose.yaml.
C. Truyền mật khẩu qua build.args rồi lưu lại vào image lúc build.
D. Khai báo Compose secret và cho ứng dụng đọc tệp được mount.
Đáp án đúng: D

Stack có service adminer chỉ phục vụ debug; khi chạy bình thường không muốn khởi động adminer. Nên dùng cơ chế nào?
A. Khai báo depends_on của adminer tới db để hoãn việc adminer chạy.
B. Khai báo restart: no để adminer chỉ chạy khi được yêu cầu.
C. Đặt adminer trong profile debug và chỉ bật profile khi cần.
D. Khai báo healthcheck thất bại để adminer không khởi chạy.
Đáp án đúng: C

Bạn muốn xem cấu hình sau khi gộp nhiều tệp -f và nội suy biến, nhưng không tạo container. Lệnh nào phù hợp?
A. docker compose ps để xem danh sách container đang chạy.
B. docker compose images để xem image của từng service.
C. docker compose logs để xem đầu ra của service sau khi khởi động.
D. docker compose config để xem cấu hình đã gộp và nội suy.
Đáp án đúng: D

Một lập trình viên sửa Dockerfile rồi chạy docker compose restart nhưng code vẫn cũ. Giải pháp nào đúng?
A. restart chỉ đổi network; chạy docker compose down để áp mã.
B. restart tự kéo image mới; kiểm tra kết nối tới registry.
C. restart không đọc env_file; chạy docker compose config.
D. restart không build image; chạy docker compose up --build.
Đáp án đúng: D

Service api đang chạy và bạn muốn mở shell ngay bên trong container đó. Lệnh nào đúng?
A. docker compose exec api sh để vào container đang chạy.
B. docker compose run api sh để vào chính container đang chạy.
C. docker compose up api sh để mở shell trong service hiện có.
D. docker compose logs api sh để mở shell kèm nhật ký ứng dụng.
Đáp án đúng: A

Service web được scale lên ba replica nhưng khai báo ports: 8080:80. Vì sao không thể cùng khởi chạy cả ba trên một host?
A. Compose không hỗ trợ quá một container cho bất kỳ service.
B. Mỗi replica phải có Dockerfile riêng để khởi động ổn định.
C. Các replica tranh nhau cổng 8080 cố định trên cùng host.
D. Số replica cần bằng số network được định nghĩa trong project.
Đáp án đúng: C

Nhiều CI job chạy cùng một stack Compose, chỉ dùng mạng nội bộ và không publish cổng host. Cách nào giúp cô lập chúng?
A. Gán project name riêng từng job và dọn tài nguyên sau kiểm thử.
B. Gán chung project name để các job dùng lại cùng container.
C. Gắn chung named volume database để tái sử dụng dữ liệu giữa các job.
D. Nối chung external network để các job truy cập service nhau.
Đáp án đúng: A

Container database liên tục báo unhealthy trong stack đang có dữ liệu quan trọng. Bước đầu xử lý nào an toàn nhất?
A. Chạy docker compose down -v rồi dựng lại và xóa toàn bộ dữ liệu cũ.
B. Kiểm tra ps, logs, healthcheck và kết nối trước khi thay đổi.
C. Xóa named volume database vì dữ liệu có thể gây unhealthy.
D. Đổi cổng host của database trước khi xem log container.
Đáp án đúng: B

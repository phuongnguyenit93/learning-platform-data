Singleton giải quyết yêu cầu gì khi một hệ thống cần kiểm soát số lượng instance của một thành phần?
Bạn phân biệt một instance duy nhất trong JVM với một tài nguyên duy nhất trên toàn hệ thống phân tán như thế nào?
Bạn đánh giá những ví dụ nào thực sự cần Singleton và những ví dụ nào chỉ đang dùng chung cấu hình?
Bạn thiết kế constructor và điểm truy cập instance để hạn chế việc tạo đối tượng ngoài ý muốn ra sao?
Bạn so sánh eager initialization với lazy initialization về thời điểm cấp phát và xử lý lỗi như thế nào?
Khi một Singleton tốn nhiều tài nguyên để khởi tạo, bạn quyết định có nên khởi tạo trễ dựa trên tiêu chí nào?
Bạn sẽ giải thích cơ chế tải và khởi tạo class trong Java giúp tạo Singleton an toàn luồng ra sao?
Initialization-on-demand holder idiom đạt lazy initialization mà không phải đồng bộ mọi lần truy cập như thế nào?
Bạn sử dụng enum Singleton để giảm rủi ro tạo thêm instance bằng cách nào?
Bạn so sánh enum Singleton với lớp thường có private constructor về khả năng mở rộng và vòng đời như thế nào?
Vì sao lazy initialization không đồng bộ có thể tạo ra nhiều instance khi các luồng gọi đồng thời?
Bạn đánh giá việc dùng synchronized trên accessor của Singleton ảnh hưởng tới hiệu năng như thế nào?
Trong double-checked locking, từ khóa volatile đóng vai trò gì đối với tính hiển thị và thứ tự khởi tạo?
Bạn sẽ kiểm thử khả năng nhiều luồng nhận cùng một instance dưới áp lực khởi tạo đồng thời như thế nào?
Khi quá trình khởi tạo Singleton ném ngoại lệ, bạn xác định hành vi của các lần truy cập tiếp theo ra sao?
Bạn xử lý trường hợp Singleton phụ thuộc vào cấu hình chỉ có sẵn sau khi ứng dụng khởi động như thế nào?
Bạn phân biệt thread-safe initialization với thread-safe behavior của các phương thức trên Singleton ra sao?
Khi Singleton lưu một HashMap mutable, bạn ngăn race condition và lost update trong truy cập đồng thời như thế nào?
Bạn lựa chọn cấu trúc dữ liệu bất biến hoặc đồng bộ cho trạng thái được chia sẻ trong Singleton dựa trên yếu tố nào?
Khi nhiều luồng cùng cập nhật một bộ đếm trong Singleton, bạn kiểm tra tính nguyên tử của thao tác bằng cách nào?
Bạn đánh giá rủi ro deadlock khi Singleton giữ lock và gọi sang thành phần khác ra sao?
Nếu hai Singleton phụ thuộc lẫn nhau khi khởi tạo, bạn phát hiện và giải quyết vòng phụ thuộc như thế nào?
Bạn phân biệt Singleton với biến static và utility class không lưu trạng thái theo những mục tiêu nào?
Trong tình huống nào một service stateless nên được dùng chung qua dependency injection thay vì tự triển khai Singleton?
Khi ứng dụng dùng dependency injection, bạn so sánh singleton scope của container với Singleton tự quản lý như thế nào?
Bạn phân biệt singleton scope, request scope và prototype scope trong việc quản lý dependency của một service ra sao?
Vì sao một bean có singleton scope không bảo đảm toàn hệ thống chỉ có một instance khi chạy nhiều application context?
Khi một Singleton phụ thuộc vào đối tượng theo request, bạn tránh giữ sai tham chiếu hoặc dữ liệu người dùng như thế nào?
Bạn thiết kế cách thay thế implementation của Singleton trong unit test mà không sửa trạng thái toàn cục ra sao?
Khi nhiều unit test chạy song song, bạn ngăn trạng thái dùng chung của Singleton khiến test phụ thuộc thứ tự như thế nào?
Bạn phân biệt reset Singleton trong test với thiết kế dependency injection giúp cô lập trạng thái bằng cách nào?
Nếu constructor Singleton đọc biến môi trường, bạn sẽ xây dựng kiểm thử cho các cấu hình khác nhau như thế nào?
Bạn kiểm tra một Singleton có tạo điểm ghép nối ẩn giữa các module thông qua phương thức truy cập toàn cục ra sao?
Bạn xác định dấu hiệu code smell khi mọi lớp đều gọi Singleton thay vì khai báo dependency rõ ràng như thế nào?
Khi một component không còn cần instance duy nhất, bạn lập kế hoạch refactor để bỏ Singleton ra sao?
Bạn phân biệt mục tiêu tạo duy nhất một đối tượng với mục tiêu kiểm soát một tài nguyên như connection pool như thế nào?
Khi ứng dụng chạy nhiều classloader, bạn giải thích vì sao có thể xuất hiện nhiều instance của cùng một lớp Singleton?
Bạn đánh giá tác động của hot reload hoặc cơ chế nạp plugin đối với danh tính Singleton ra sao?
Khi triển khai ứng dụng trên nhiều JVM hoặc container, bạn sẽ dùng cơ chế nào nếu thực sự cần một leader duy nhất?
Bạn so sánh Singleton với khóa phân tán hoặc leader election khi điều phối một tác vụ toàn hệ thống ra sao?
Bạn đánh giá những rủi ro nào khi dùng Singleton để giữ session người dùng trong ứng dụng đa tenant?
Nếu Singleton quản lý một kết nối mạng cần tái thiết lập, bạn thiết kế vòng đời và xử lý reconnect như thế nào?
Khi cấu hình phải thay đổi lúc chạy, bạn phân biệt thay instance với cập nhật trạng thái bên trong Singleton ra sao?
Bạn kiểm tra tác động của serialization và deserialization đến tính duy nhất của Singleton lớp thường như thế nào?
Bạn sử dụng readResolve hoặc lựa chọn thiết kế khác để kiểm soát danh tính sau deserialization ra sao?
Khi reflection hoặc cloning có thể tạo thêm đối tượng, bạn đánh giá những giới hạn thực tế của biện pháp bảo vệ Singleton như thế nào?
Bạn xác định thứ tự đóng tài nguyên do Singleton sở hữu khi ứng dụng shutdown bằng cách nào?
Bạn thiết kế log, metrics và kiểm tra sức khỏe cho một Singleton có trạng thái để phát hiện lỗi vận hành ra sao?
Khi một Singleton trở thành điểm nghẽn vì mọi request truy cập chung lock, bạn lựa chọn phương án cải tiến nào?
Bạn dùng những tiêu chí nào để quyết định áp dụng Singleton, dùng scope do DI container quản lý hay chuyển sang thành phần có vòng đời tường minh?

Câu 1: Trong ứng dụng web phân tầng, trách nhiệm chính của presentation layer là gì?
A. Thực thi truy vấn SQL và quản lý schema trực tiếp
B. Tính phí giao hàng trong từng template HTML
C. Nhận request, ánh xạ dữ liệu và trả response
D. Quyết định chiến lược replication của database
Đáp án đúng: C

Câu 2: Với chức năng đặt hàng, application/service layer thường đảm nhiệm gì?
A. Lưu HTTP session vào bảng orders của database
B. Service điều phối use case và các thành phần
C. Render HTML template từ dữ liệu JDBC ResultSet
D. Định nghĩa chi tiết kết nối pool của PostgreSQL
Đáp án đúng: B

Câu 3: Domain layer có vai trò nổi bật nào trong mô hình phân tầng?
A. Chỉ quản lý địa chỉ IP và HTTP header đầu vào
B. Giữ quy tắc và bất biến nghiệp vụ của hệ thống
C. Chỉ lưu cấu hình datasource và transaction pool
D. Chỉ sinh CSS cho các màn hình ứng dụng
Đáp án đúng: B

Câu 4: Trong kiến trúc phân tầng, persistence layer thường chịu trách nhiệm gì?
A. Định dạng JSON trả về từ mọi REST controller
B. Xác thực việc nhấn nút của trình duyệt khách
C. Quyết định chính sách giá cho toàn bộ domain
D. Đọc/ghi dữ liệu thông qua cơ chế lưu trữ
Đáp án đúng: D

Câu 5: Với quy tắc strict layering, hướng gọi tầng thường nên thế nào?
A. Tầng trình bày gọi thẳng bất kỳ tầng dữ liệu nào
B. Tầng lưu trữ gọi ngược trực tiếp vào giao diện web
C. Mỗi tầng gọi tầng kề dưới theo thứ tự thiết kế
D. Mọi tầng tham chiếu lẫn nhau để giảm số interface
Đáp án đúng: C

Câu 6: Controller gọi thẳng JPA repository và tự tính chiết khấu gây vấn đề gì?
A. Logic bị dàn trải, vượt qua ranh giới service
B. Giảm tối đa rủi ro thay đổi schema dữ liệu
C. Tăng khả năng kiểm thử domain mà không cần web
D. Bảo đảm mọi giao dịch được quản lý nhất quán
Đáp án đúng: A

Câu 7: Vì sao nên dùng DTO tại ranh giới controller và service khi cần?
A. Buộc response phải sao chép toàn bộ thuộc tính JPA
B. Cho controller trực tiếp quyết định schema database
C. Giới hạn dữ liệu trao đổi, tránh lộ entity lưu trữ
D. Thay mọi nghiệp vụ domain bằng quá trình serialize
Đáp án đúng: C

Câu 8: Khi unit test quy tắc tính giá, nên cô lập thành phần nào?
A. Khởi động mọi service ngoài để đo phản hồi network
B. Dùng dữ liệu production rồi đối chiếu bản ghi thật
C. Kiểm thử HTML để suy ra quy tắc tính giá nội bộ
D. Test domain không cần khởi động web và DB
Đáp án đúng: D

Câu 9: Để xác nhận repository ánh xạ dữ liệu chính xác, kiểm thử gì phù hợp?
A. Integration test truy cập database thử nghiệm
B. Chỉ unit test controller với mock mọi repository
C. Chỉ kiểm thử màu sắc nút Save trên trình duyệt
D. Chỉ kiểm tra sự tồn tại của interface Repository
Đáp án đúng: A

Câu 10: Khi service phải cập nhật đơn và tồn kho như một giao dịch, nên đặt ranh giới ở đâu?
A. Trong mỗi response DTO để tự commit transaction
B. Trong giao diện web để bảo đảm đúng giao dịch SQL
C. Transaction bao lấy thao tác service cần nguyên tử
D. Trong class cấu hình router của frontend JavaScript
Đáp án đúng: C

Câu 11: Quy tắc nghiệp vụ kiểm tra hạn mức tín dụng phù hợp đặt ở tầng nào?
A. Template view chỉ dựa vào màu thông báo lỗi
B. Class JDBC driver để kiểm tra trước khi mở kết nối
C. Servlet filter chỉ đọc Content-Type của request
D. Domain giữ quy tắc kiểm tra hạn mức tín dụng
Đáp án đúng: D

Câu 12: Layered Architecture và triển khai nhiều tier khác nhau thế nào?
A. Layer luôn đòi mỗi tầng chạy ở một máy riêng
B. Layer tổ chức logic, tier là chỗ triển khai vật lý
C. Tier chỉ là cách chia package trong source Java
D. Layer chỉ dùng cho hệ thống có giao diện desktop
Đáp án đúng: B

Câu 13: Khi thay REST controller bằng giao diện dòng lệnh, cách tổ chức nào hiệu quả?
A. Thay presentation, tái dùng service hiện tại
B. Sao chép toàn bộ nghiệp vụ vào parser CLI mới
C. Đổi mọi entity database thành command-line DTO
D. Đưa mọi quyết định vào repository cho CLI đọc
Đáp án đúng: A

Câu 14: Vì sao để database entity trực tiếp làm API response có thể nguy hiểm?
A. Tự động xóa dữ liệu private trước khi trả response
B. Giúp schema độc lập hoàn toàn với mọi API client
C. Có thể lộ field nội bộ và làm API dính schema
D. Bảo đảm API không bao giờ thay đổi qua phiên bản
Đáp án đúng: C

Câu 15: Nếu application service phụ thuộc chi tiết JDBC cụ thể, hệ quả thường gặp là gì?
A. Service tự trở thành pure domain function ngay
B. Khó thay hạ tầng và kiểm thử service độc lập
C. Controller không còn cần ánh xạ request DTO
D. Data layer có thể bỏ hoàn toàn transaction
Đáp án đúng: B

Câu 16: Phụ thuộc vòng A→B→C→A giữa các layer thường cho thấy gì?
A. Kiến trúc đã bảo đảm mọi lớp có thể thay độc lập
B. Có vòng phụ thuộc, ranh giới đang bất hợp lý
C. Số request HTTP tối thiểu của hệ thống đã được giảm
D. Database transaction được đảm bảo xuyên các module
Đáp án đúng: B

Câu 17: Khi nào relaxed layering khác strict layering một cách rõ nhất?
A. Cấm mọi tầng cao dùng service của tầng kề dưới
B. Buộc presentation phụ thuộc trực tiếp vào database
C. Cho phép tầng cao bỏ qua tầng trung gian để gọi dưới
D. Không cho phép sử dụng interface giữa hai tầng
Đáp án đúng: C

Câu 18: Interface của repository giúp tầng service điều gì?
A. Service phụ thuộc interface, không phụ thuộc DB
B. Tự động giảm số lần truy vấn mà không đổi mã
C. Tự động bỏ qua mọi lỗi giao dịch cơ sở dữ liệu
D. Chạy controller mà không cần ánh xạ request
Đáp án đúng: A

Câu 19: Khi yêu cầu thay đổi schema bảng customer, vùng nào nên chịu ảnh hưởng trước?
A. Mọi view template phải đổi SQL ở từng biểu mẫu
B. Tầng truy cập dữ liệu và ánh xạ persistence
C. Toàn bộ domain rule phải đổi theo tên cột vật lý
D. Mọi HTTP middleware phải gắn thêm tên bảng mới
Đáp án đúng: B

Câu 20: Với yêu cầu không cho đặt hàng số lượng âm, biện pháp nào bền vững?
A. Domain chặn số lượng âm ở mọi đường gọi
B. Chỉ ẩn nút submit bằng JavaScript ở trình duyệt
C. Chỉ kiểm tra JSON syntax bằng bộ chuyển đổi DTO
D. Chỉ dựa vào thông báo lỗi từ giao diện CSS
Đáp án đúng: A

Câu 21: Khi validation của form khác kiểm tra nghiệp vụ, cách chia nào phù hợp?
A. Presentation quyết định tồn kho còn domain chỉ format JSON
B. Repository xử lý toàn bộ input và render lỗi giao diện
C. Presentation kiểm tra input; domain bảo vệ bất biến
D. View làm validation nghiệp vụ, service chỉ truy cập bảng
Đáp án đúng: C

Câu 22: Khi service ném lỗi OrderNotFound, HTTP status nên được ánh xạ ở đâu?
A. Entity domain tự tạo ResponseEntity để trả về web
B. Repository JDBC tự render trang lỗi theo locale
C. Ứng dụng service tự gửi header trực tiếp qua socket
D. Controller advice đổi lỗi domain sang 404
Đáp án đúng: D

Câu 23: Cache kết quả truy vấn gắn Redis thường thích hợp đặt ở đâu?
A. HTML template lưu thuật toán cache thay database
B. Thành phần hạ tầng hoặc data access theo hợp đồng
C. Domain entity tự cấu hình địa chỉ Redis mỗi lần tạo
D. Controller quyết định toàn bộ chính sách SQL cache
Đáp án đúng: B

Câu 24: Khi package dự án theo layer, cách nào hạn chế truy cập vượt ranh giới?
A. Kiểm soát dependency và API giữa các module/tầng
B. Đặt mọi class thành public để giảm lỗi import
C. Đặt repository vào cùng package với view template
D. Tự động nhập tất cả module vào một lớp tiện ích
Đáp án đúng: A

Câu 25: Nếu service chứa HTML rendering lẫn SQL và nghiệp vụ, nên xử lý ra sao?
A. Giữ nguyên vì tên lớp Service đã đủ phân tầng
B. Chuyển toàn bộ mã thành một controller khổng lồ
C. Chỉ đổi tên package mà không đổi lời gọi trực tiếp
D. Tách UI, nghiệp vụ và DB ra thành các lớp
Đáp án đúng: D

Câu 26: Việc dùng mock repository trong unit test service giúp xác nhận gì?
A. Mọi SQL query của driver đã đúng với database thật
B. Trang HTML hiển thị chính xác trên từng trình duyệt
C. Connection pool tự hồi phục khi máy chủ mất mạng
D. Luồng nghiệp vụ và tương tác dữ liệu theo hợp đồng
Đáp án đúng: D

Câu 27: Ứng dụng nhỏ có cần số tầng cố định cho mọi trường hợp không?
A. Không; số tầng tùy quy mô và độ phức tạp
B. Có; mọi ứng dụng luôn phải có đúng bảy tầng
C. Có; mỗi bảng database cần một tầng độc lập
D. Không; mọi nghiệp vụ nên đặt trong controller
Đáp án đúng: A

Câu 28: Khi chuyển controller quá tải sang kiến trúc phân tầng, bước nào hợp lý?
A. Chuyển tất cả SQL sang view template để giảm service
B. Đưa validation và xử lý giao diện vào database driver
C. Sao chép cùng quy tắc xử lý ở nhiều REST controller
D. Tách use case và repository khỏi controller
Đáp án đúng: D

Câu 1. Hai nhóm gọi “khách hàng” nhưng một nhóm nói người mua, nhóm kia nói người nhận. DDD khuyến nghị gì?
A. Làm rõ thuật ngữ trong từng bounded context
B. Gộp cả hai nghĩa thành một bảng duy nhất
C. Dùng một DTO chung cho mọi màn hình và luồng
D. Bỏ hội thoại nghiệp vụ và đặt tên theo database
Đáp án đúng: A

Câu 2. Ubiquitous Language trong DDD được xây dựng chủ yếu từ đâu?
A. Tên class mà framework tự sinh trong quá trình build
B. Trao đổi nhất quán giữa chuyên gia và đội phát triển
C. Chỉ danh sách thuật ngữ do database vendor đưa ra
D. Chỉ tên endpoint trong hệ thống API đang triển khai
Đáp án đúng: B

Câu 3. Subdomain nào thường là core domain đối với doanh nghiệp có lợi thế nhờ thuật toán tối ưu tuyến giao?
A. Dịch vụ lưu file chung không tạo khác biệt
B. Chức năng đăng nhập phổ thông dùng thư viện sẵn
C. Trang quản trị tài khoản với quy tắc CRUD cơ bản
D. Bài toán tối ưu tuyến tạo lợi thế kinh doanh
Đáp án đúng: D

Câu 4. Bounded context trong DDD xác định ranh giới nào quan trọng nhất?
A. Ranh giới nơi mô hình và thuật ngữ có nghĩa nhất quán
B. Ranh giới vật lý của từng container được triển khai
C. Ranh giới bắt buộc giữa các schema của một database
D. Ranh giới tương ứng chính xác với mỗi service đang chạy
Đáp án đúng: A

Câu 5. Vì sao không nên ép một mô hình Order duy nhất cho bán hàng và giao vận?
A. Vì các context bắt buộc dùng hai ngôn ngữ lập trình
B. Vì cùng tên entity không thể có hai khóa chính
C. Vì hai nghiệp vụ có thể có quy tắc Order khác nhau
D. Vì một bảng luôn chỉ được phép có một khóa ngoại
Đáp án đúng: C

Câu 6. Context map hỗ trợ nhóm phát triển hiểu điều gì?
A. Chỉ thứ tự các câu SQL ở mỗi bounded context
B. Quan hệ, phụ thuộc và cách tích hợp giữa các context
C. Danh sách toàn bộ field trong database production
D. Chỉ cấu hình network của từng service được deploy
Đáp án đúng: B

Câu 7. Một entity thay đổi địa chỉ nhưng vẫn là cùng khách hàng; yếu tố nào giúp xác định tính liên tục?
A. Mọi trường dữ liệu của khách hàng đều bất biến
B. Số lượng property trong class giữ nguyên sau sửa
C. Danh tính ổn định, không chỉ trạng thái thuộc tính
D. Cùng địa chỉ giao hàng với khách hàng trước đó
Đáp án đúng: C

Câu 8. Hai đối tượng Money cùng số tiền và đơn vị tiền tệ; trong mô hình Value Object, so sánh nào phù hợp?
A. So địa chỉ vùng nhớ của từng đối tượng mới
B. So thời điểm khởi tạo lần đầu của từng instance
C. So khóa định danh riêng do database cấp
D. So giá trị các thuộc tính có ý nghĩa nghiệp vụ
Đáp án đúng: D

Câu 9. Một Value Object như Money được thiết kế bất biến nhằm đạt lợi ích nào?
A. Không cần kiểm tra hợp lệ khi nhận dữ liệu
B. Tránh việc đổi giá trị âm thầm sau khi tạo
C. Có thể thay mọi entity bằng class không ID
D. Tự động commit nhiều aggregate trong transaction
Đáp án đúng: B

Câu 10. Aggregate root có trách nhiệm gì trong aggregate?
A. Điều phối truy cập và bảo vệ bất biến nội bộ
B. Lưu toàn bộ sự kiện của mọi bounded context
C. Chứa cấu hình framework và tất cả adapter ngoài
D. Thực thi mọi phép truy vấn qua các database khác
Đáp án đúng: A

Câu 11. Đơn hàng có tổng tiền phải bằng tổng các dòng; cách cập nhật aggregate nào bảo vệ invariant?
A. Cho UI sửa tổng tiền độc lập với danh sách dòng
B. Cho database ghi từng dòng và tổng bằng hai API
C. Để mỗi OrderLine tự sửa mọi aggregate khác
D. Cập nhật qua root để kiểm soát tổng tiền và các dòng
Đáp án đúng: D

Câu 12. Repository trong tactical DDD nên cung cấp abstraction chính gì?
A. Truy xuất và lưu aggregate theo ngôn ngữ domain
B. Giao diện dựng màn hình HTML cho mọi ứng dụng
C. Danh sách câu SQL chi tiết cho mọi controller
D. Dịch vụ gửi HTTP request tới từng bounded context
Đáp án đúng: A

Câu 13. Vì sao repository thường thao tác qua aggregate root?
A. Vì entity con không thể có thuộc tính có giá trị
B. Vì mọi entity con luôn phải nằm trong một bảng
C. Vì root là cổng kiểm soát các quy tắc nhất quán
D. Vì repository tự động xóa mọi entity không được đọc
Đáp án đúng: C

Câu 14. Tên domain event nào diễn đạt đúng một sự kiện nghiệp vụ đã xảy ra?
A. CreateOrder vì đây là lệnh yêu cầu tạo đơn
B. OrderPlaced vì đơn đã được đặt thành công
C. ValidateOrder vì đây là bước kiểm tra dữ liệu
D. CancelOrder vì đây là lệnh yêu cầu hủy đơn
Đáp án đúng: B

Câu 15. Domain event thường nên mô tả nội dung nào?
A. Ý định thử thực hiện tác vụ trong tương lai
B. Chi tiết framework dùng để khởi tạo transaction
C. Sự kiện nghiệp vụ đã xảy ra, có dữ kiện cần thiết
D. Mọi tham số của các service không liên quan
Đáp án đúng: C

Câu 16. Một context dùng khái niệm “subscriber”, context khác dùng “customer”; khi tích hợp nên làm gì?
A. Đổi toàn bộ database hai context thành cùng một schema
B. Bắt cả hai context dùng một entity và logic chung
C. Đưa thẳng đối tượng hạ tầng bên ngoài vào domain
D. Dùng lớp chuyển đổi để giữ ngữ nghĩa từng context
Đáp án đúng: D

Câu 17. Quan hệ giữa subdomain và bounded context trong DDD được hiểu thế nào?
A. Chúng luôn đồng nghĩa theo cấu trúc tổ chức code
B. Mỗi subdomain bắt buộc tương ứng với một bảng SQL
C. Mỗi bounded context bắt buộc chứa toàn bộ doanh nghiệp
D. Đây là hai góc nhìn nghiệp vụ và ranh giới mô hình
Đáp án đúng: D

Câu 18. Trong chiến lược DDD, vì sao cần dành nhiều sự chú ý cho core domain?
A. Vì core domain luôn đơn giản nhất để thuê ngoài
B. Vì core domain luôn được tạo bằng CRUD framework
C. Vì đây là nơi tạo lợi thế và khác biệt chính
D. Vì core domain không chứa các quy tắc nghiệp vụ
Đáp án đúng: C

Câu 19. Một bounded context thay đổi định nghĩa trạng thái Paid; biện pháp phối hợp nào phù hợp?
A. Đổi ngầm model nội bộ mà không báo context khác
B. Rà context map và hợp đồng trao đổi liên quan
C. Buộc tất cả context dùng chung class PaidStatus
D. Đổi tên dịch vụ triển khai để không cần cập nhật
Đáp án đúng: B

Câu 20. Hai aggregate Order và Inventory cần trao đổi kết quả; thiết kế nào giúp giữ ranh giới?
A. Cho Order trực tiếp sửa collection nội bộ của Inventory
B. Dùng một transaction SQL xuyên mọi hệ thống liên quan
C. Trao đổi qua định danh và xử lý phối hợp phù hợp
D. Đưa tất cả thông tin tồn kho vào aggregate Order
Đáp án đúng: C

Câu 21. Khi nào nên gộp hai entity vào cùng một aggregate?
A. Khi invariant của chúng cần được giữ nhất quán cùng lúc
B. Khi cả hai có tên bắt đầu bằng cùng một tiền tố
C. Khi repository có thể trả về danh sách của cả hai
D. Khi hai class đều được dùng trên cùng một giao diện
Đáp án đúng: A

Câu 22. Một aggregate quá lớn khiến nhiều thao tác không liên quan tranh chấp ghi; hướng cải thiện nào phù hợp?
A. Gộp tiếp nhiều entity để giảm số repository
B. Cho entity bên trong bị sửa trực tiếp ngoài root
C. Thay mọi invariant bằng validation ở UI
D. Xem lại ranh giới theo invariant thực sự cần đồng bộ
Đáp án đúng: D

Câu 23. Trường Address gồm đường, phường và mã bưu chính, không cần danh tính riêng; mô hình nào hợp lý?
A. Entity với ID bất biến riêng cho mọi lần nhập địa chỉ
B. Value Object so bằng thuộc tính có ý nghĩa
C. Aggregate root quản lý toàn bộ khách hàng toàn quốc
D. Repository độc lập cho từng chuỗi địa chỉ
Đáp án đúng: B

Câu 24. Khi một domain event dẫn đến cập nhật ở bounded context khác, điều gì cần chấp nhận trong thiết kế?
A. Kết quả có thể nhất quán cuối cùng giữa các context
B. Sự kiện chỉ được nhận sau khi hai context đồng bộ
C. Một aggregate được phép sửa trực tiếp aggregate khác
D. Hai context luôn cập nhật atomic trong cùng database
Đáp án đúng: A

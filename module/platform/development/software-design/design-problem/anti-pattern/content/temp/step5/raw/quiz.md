Câu 1: Trong thiết kế phần mềm, anti-pattern là gì?
A. Quy tắc compiler cấm sử dụng một từ khóa Java
B. Một kiểu dữ liệu trừu tượng có vòng đời ngắn
C. Một phép kiểm thử luôn cần chạy trước khi build
D. Giải pháp lặp lại nhưng gây hệ quả xấu
Đáp án đúng: D

Câu 2: Một class chứa cả tính giá, lưu đơn và gửi mail đang dần trở thành kiểu anti-pattern nào?
A. Flyweight chia sẻ object bất biến để tiết kiệm RAM
B. God Object với quá nhiều trách nhiệm và phụ thuộc
C. Bridge tách hai biến thể triển khai độc lập
D. Composite thao tác nhất quán trên cấu trúc cây
Đáp án đúng: B

Câu 3: Dấu hiệu đặc trưng của Spaghetti Code là gì?
A. Các module có interface ổn định và hướng gọi rõ
B. Các method ngắn thực hiện một quy tắc đồng nhất
C. Luồng điều khiển và phụ thuộc rối rắm
D. Mọi component có unit test độc lập với hạ tầng
Đáp án đúng: C

Câu 4: Golden Hammer thể hiện sai lầm nào khi chọn công nghệ?
A. Áp dụng một công cụ cho cả bài toán không phù hợp
B. Đánh giá nhiều giải pháp theo điều kiện triển khai
C. Thử giải pháp nhỏ trước khi ràng buộc kiến trúc
D. Tách rõ rủi ro thay đổi và năng lực đội phát triển
Đáp án đúng: A

Câu 5: Một dự án lập 20 interface cho luồng CRUD đơn giản chưa có biến thể là rủi ro gì?
A. Interface Segregation vì client chỉ dùng thứ nó cần
B. Dependency Inversion vì mã cấp cao dựa hợp đồng
C. Encapsulation vì dữ liệu nội bộ được che giấu
D. Speculative Generality do trừu tượng hóa sớm
Đáp án đúng: D

Câu 6: Vì sao copy-paste cùng một rule giảm giá vào năm service gây rủi ro?
A. Mỗi service có thể kiểm thử unit riêng biệt
B. Biên dịch Java vẫn kiểm tra đúng kiểu tham số
C. Mỗi API có thể tự xác thực dữ liệu đầu vào
D. Các bản sao dễ lệch khi chính sách được sửa
Đáp án đúng: D

Câu 7: Hai module A và B import lẫn nhau khiến thay đổi kéo theo nhau là vấn đề gì?
A. Đảo ngược phụ thuộc thông qua hợp đồng ổn định
B. Kết dính cao vì hai module cùng một use case
C. Phụ thuộc vòng khiến module khó thay đổi
D. Đóng gói tốt vì không lộ concrete class
Đáp án đúng: C

Câu 8: Dùng biến static để lưu currentUser cho mọi HTTP request gây nguy cơ gì?
A. Đảm bảo session của mỗi client được cô lập
B. Trạng thái dùng chung rò rỉ giữa các request
C. Bảo vệ dữ liệu khi nhiều thread cùng cập nhật
D. Cho phép thay identity provider mà không sửa code
Đáp án đúng: B

Câu 9: Service dùng ServiceLocator.get() ở mọi method thường khó test vì sao?
A. Constructor thể hiện quá rõ các dependency cần dùng
B. Interface tách biệt theo từng năng lực đang sử dụng
C. Dependency ẩn trong lời gọi và khó thay bằng fake
D. Mọi dependency được tiêm tường minh qua tham số
Đáp án đúng: C

Câu 10: Khi tạo chuỗi kế thừa sâu và sửa base làm hỏng nhiều subclass, rủi ro gì?
A. Fragile Base Class do phụ thuộc hành vi kế thừa
B. Cohesion cao vì mọi class dùng chung parent
C. Loose Coupling vì thay base không ảnh hưởng client
D. Composition ưu tiên ủy quyền qua interface
Đáp án đúng: A

Câu 11: Nếu lớp Penguin bị ép triển khai fly() rồi ném lỗi runtime, vấn đề gốc là gì?
A. Một lớp đã tách interface theo năng lực nhỏ
B. Một adapter đã ánh xạ lỗi theo API mục tiêu
C. Kế thừa sai hợp đồng thay thế của kiểu cha
D. Một service đã đặt validation ở ranh giới
Đáp án đúng: C

Câu 12: Một object domain chỉ có getter/setter, mọi rule đặt ở service có thể là dấu hiệu gì?
A. Rich Domain Model khi entity bảo vệ bất biến chính
B. Command Pattern khi thao tác gói thành object
C. Observer Pattern khi subscriber nhận trạng thái
D. Anemic Domain Model khi entity chỉ chứa dữ liệu
Đáp án đúng: D

Câu 13: Tại sao lạm dụng Singleton cho dữ liệu thay đổi là lựa chọn nguy hiểm?
A. Global state làm tăng coupling và race
B. Constructor injection tạo dependency tường minh
C. Immutable value object giảm trạng thái chia sẻ
D. Interface chỉ mô tả năng lực mà client cần
Đáp án đúng: A

Câu 14: Khi cùng một thay đổi nghiệp vụ buộc chỉnh hàng chục file không liên quan, nên nghi vấn gì?
A. Feature Envy vì một method gọi object khác
B. Middle Man vì lớp chỉ chuyển tiếp lời gọi
C. Shotgun Surgery do trách nhiệm bị phân tán
D. Primitive Obsession vì dùng quá nhiều kiểu cơ bản
Đáp án đúng: C

Câu 15: Mã legacy không ai hiểu vẫn giữ nguyên vì sợ xóa, dù không có người dùng, thường gọi là gì?
A. Lava Flow: phần mã cũ khó xác minh còn cần
B. Strangler Fig: thay chức năng cũ từng phần
C. Facade: tạo điểm gọi đơn giản cho subsystem
D. Adapter: đổi interface cho ứng dụng khách
Đáp án đúng: A

Câu 16: Một hệ thống không có ranh giới module rõ, mọi phần truy cập lẫn nhau giống anti-pattern nào?
A. Hexagonal có cổng vào/ra và dependency rõ
B. Big Ball of Mud với phụ thuộc rối
C. Layered có giao diện qua tầng trung gian
D. Microkernel có plugin gắn với core ổn định
Đáp án đúng: B

Câu 17: Tách thành microservice nhưng mọi service phải deploy đồng thời vì phụ thuộc chặt là dấu hiệu gì?
A. Distributed Monolith thay vì dịch vụ tự chủ
B. Eventual Consistency với cập nhật bất đồng bộ
C. Loose Coupling vì thay một service không ảnh hưởng
D. Bounded Context với sở hữu domain độc lập
Đáp án đúng: A

Câu 18: Tối ưu thuật toán không đo đạc trước rồi làm mã phức tạp lên là rủi ro nào?
A. Performance Profiling bằng dữ liệu đo tải thật
B. Capacity Planning dựa trên nhu cầu hiện tại
C. Benchmarking so sánh trước và sau có kiểm soát
D. Premature Optimization thiếu bằng chứng nút thắt
Đáp án đúng: D

Câu 19: Dùng kế thừa chỉ để tái sử dụng một helper mà không có quan hệ is-a có thể gây gì?
A. Ràng buộc subtype sai với khái niệm domain
B. Cho phép client thay subtype mà không đổi hành vi
C. Giảm coupling vì subclass không phụ thuộc base
D. Củng cố LSP vì contract không bị ảnh hưởng
Đáp án đúng: A

Câu 20: Một facade hàng trăm method che toàn bộ hệ thống có thể trở thành gì?
A. Interface Segregation cho từng năng lực nhỏ
B. Encapsulation vì component chỉ lộ API thiết yếu
C. Abstraction ổn định vì luôn có một entry point
D. God Interface khiến client phụ thuộc quá nhiều
Đáp án đúng: D

Câu 21: Nếu đội ngũ viết thêm framework riêng chỉ để giải bài toán đơn giản, câu hỏi đánh giá tốt là gì?
A. Có thể thêm nhiều lớp trừu tượng hơn nữa không
B. Có thể bỏ toàn bộ test để hoàn thành sớm không
C. Có thể đổi tất cả package sang tên framework không
D. Lợi ích thực tế có vượt chi phí bảo trì lâu dài không
Đáp án đúng: D

Câu 22: Một anti-pattern phổ biến có luôn sai trong mọi ngữ cảnh không?
A. Có, tên anti-pattern tự chứng minh mọi trường hợp
B. Không, cần xem quy mô, rủi ro và lý do thiết kế
C. Có, bất kỳ singleton nào cũng gây race condition
D. Không, vì mọi kiến trúc đều có chất lượng như nhau
Đáp án đúng: B

Câu 23: Nếu muốn sửa God Class nhưng không đủ test bảo vệ hành vi, bước đầu nào an toàn?
A. Xóa class rồi thay bằng 20 lớp mới ngay lập tức
B. Thêm characterization tests cho luồng quan trọng
C. Đổi mọi chữ ký public để ép client cập nhật
D. Dời toàn bộ SQL sang controller trong cùng commit
Đáp án đúng: B

Câu 24: Khi tách trách nhiệm của một lớp rất lớn, chiến lược nào giảm rủi ro regression?
A. Thay luôn database, API và ngôn ngữ lập trình
B. Tách tất cả method sang static utility một lần
C. Extract Class từng phần với kiểm thử sau mỗi bước
D. Chuyển mọi field sang public để giảm dependency
Đáp án đúng: C

Câu 25: Với hệ thống phụ thuộc legacy, cách thay từng luồng thay vì viết lại tất cả có tên gì?
A. Big Bang Rewrite: thay toàn bộ trong một release
B. Strangler Fig: chuyển dần chức năng sang hệ mới
C. Golden Hammer: dùng một giải pháp cho mọi bài toán
D. Lava Flow: giữ lại code chưa được kiểm chứng
Đáp án đúng: B

Câu 26: Lớp điều phối chỉ forward hầu hết method mà không có logic đáng kể gợi ý gì?
A. Facade luôn sai nếu cung cấp một API gọi xuống
B. Middle Man có thể là abstraction không có giá trị
C. Bridge luôn tạo ra thêm một lớp chỉ forward
D. Adapter không được phép gọi các object khác
Đáp án đúng: B

Câu 27: Để xác nhận refactor anti-pattern không đổi hành vi, nên dùng bằng chứng nào?
A. Regression tests và đối chiếu output trên case thật
B. Số class tăng lên sau khi tách một lớp lớn
C. Số package giảm dù API đổi không tương thích
D. Lượng code format lại trong cùng một commit
Đáp án đúng: A

Câu 28: Khi phát hiện smell ở một đoạn mã ổn định, không có nhu cầu thay đổi, quyết định nào hợp lý?
A. Luôn rewrite ngay vì smell là lỗi runtime
B. Bỏ mọi code review để tránh sửa quá nhiều
C. Đánh giá chi phí, rủi ro rồi mới ưu tiên sửa
D. Tự động thêm design pattern vào mọi phương thức
Đáp án đúng: C

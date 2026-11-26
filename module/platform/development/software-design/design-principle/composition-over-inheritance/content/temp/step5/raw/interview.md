Bạn sẽ giải thích nguyên tắc ưu tiên composition over inheritance và điều kiện nào khiến nó có ích trong thiết kế Java?
Khi phân tích hai lớp có quan hệ với nhau, bạn sẽ phân biệt is-a với has-a bằng những câu hỏi về nghiệp vụ nào?
Bạn sẽ nhận biết một quan hệ kế thừa chỉ nhằm tái sử dụng mã thay vì biểu diễn sự thay thế hợp lệ ra sao?
Bạn sẽ đánh giá liệu lớp con có thực sự giữ được hợp đồng hành vi của lớp cha trong các tình huống biên như thế nào?
Khi một lớp cơ sở thay đổi phương thức protected, những loại tác động dây chuyền nào có thể xảy ra trong hệ phân cấp?
Bạn sẽ xác định dấu hiệu fragile base class khi lớp con phụ thuộc vào thứ tự gọi phương thức nội bộ của lớp cha ra sao?
Trong thiết kế nhiều tầng kế thừa, bạn sẽ đánh giá chi phí hiểu luồng điều khiển và tìm nguyên nhân lỗi như thế nào?
Bạn sẽ chọn kế thừa hay composition khi các biến thể cần kết hợp nhiều hành vi độc lập theo những tiêu chí nào?
Khi hai hành vi cần thay đổi độc lập, bạn sẽ thiết kế các đối tượng cộng tác để tránh bùng nổ số lượng lớp con ra sao?
Bạn sẽ diễn giải delegation khác với việc chỉ lưu một tham chiếu đối tượng trong lớp như thế nào?
Bạn sẽ quyết định phương thức nào của component cần được Context ủy quyền và phương thức nào nên giữ trong Context ra sao?
Bạn sẽ thiết kế interface cho đối tượng được ủy quyền dựa trên nhu cầu của client thay vì tất cả phương thức của lớp hiện có như thế nào?
Khi các component có yêu cầu đầu vào khác nhau, bạn sẽ giữ hợp đồng cộng tác gọn gàng mà không đẩy kiểm tra kiểu xuống client ra sao?
Bạn sẽ truyền component vào constructor hay cho phép thay thế trong lúc chạy dựa trên bất biến và vòng đời đối tượng như thế nào?
Khi component bị thay giữa một thao tác đang xử lý, bạn sẽ bảo đảm tính nhất quán của hành vi và dữ liệu ra sao?
Bạn sẽ đánh giá nguy cơ một đối tượng bị gắn quá nhiều component khiến trách nhiệm của nó trở nên mơ hồ như thế nào?
Khi hai component cần chia sẻ trạng thái, bạn sẽ tránh tạo kết dính ngầm qua dữ liệu có thể thay đổi bằng cách nào?
Bạn sẽ xác định ai chịu trách nhiệm tạo, sở hữu và giải phóng tài nguyên của các component được ghép vào một đối tượng ra sao?
Bạn sẽ lựa chọn component bất biến hay có trạng thái trong môi trường nhiều luồng theo các điều kiện nào?
Bạn sẽ dùng Strategy để thay thế một nhánh lựa chọn thuật toán bằng delegation mà không làm thay đổi kết quả nghiệp vụ như thế nào?
Trong hệ thống tính phí với nhiều chính sách, bạn sẽ xác định ranh giới interface Strategy và đối tượng chọn chính sách ra sao?
Bạn sẽ kiểm soát một Strategy được chọn sai hoặc không tồn tại mà không âm thầm sử dụng kết quả mặc định như thế nào?
Bạn sẽ sử dụng Decorator để bổ sung hành vi như ghi log hoặc đo thời gian mà không tạo thêm subclass cho mọi tổ hợp ra sao?
Bạn sẽ phân biệt Decorator với wrapper chỉ chuyển tiếp lời gọi theo mục tiêu mở rộng hành vi như thế nào?
Khi có nhiều Decorator xếp chồng, bạn sẽ xem xét thứ tự áp dụng và tác động đến kết quả như thế nào?
Bạn sẽ đánh giá rủi ro Decorator thay đổi ngoại lệ, trạng thái hoặc các tiền điều kiện của component được bọc ra sao?
Bạn sẽ vận dụng Bridge để tách một abstraction khỏi nhiều implementation nhằm ngăn hai chiều biến thể tạo quá nhiều lớp như thế nào?
Khi hệ thống hỗ trợ nhiều loại thông báo và nhiều kênh gửi, bạn sẽ xác định hai chiều biến thể cho Bridge ra sao?
Bạn sẽ phân biệt Bridge với Strategy khi thiết kế gồm hai hệ phân cấp có thể tiến hóa độc lập theo những tiêu chí nào?
Bạn sẽ chọn interface nhỏ cho các component ra sao để giảm ảnh hưởng khi thêm hành vi mới vào một nhóm đối tượng?
Khi composition làm phát sinh nhiều tầng chuyển tiếp lời gọi, bạn sẽ đo độ phức tạp và quyết định đơn giản hóa như thế nào?
Bạn sẽ nhận biết một mô hình composition đang che giấu chuỗi phụ thuộc quá dài thay vì giảm kết dính bằng cách nào?
Bạn sẽ xác định trường hợp kế thừa vẫn thích hợp khi lớp con thật sự chuyên biệt hóa một abstraction ổn định như thế nào?
Bạn sẽ phân biệt inheritance dùng để mở rộng một framework với composition dùng để ghép hành vi ở cấp ứng dụng ra sao?
Khi một thư viện buộc phải kế thừa lớp cơ sở, bạn sẽ hạn chế phạm vi phụ thuộc vào lớp ấy bằng thiết kế nào?
Bạn sẽ phân tích vì sao chuyển toàn bộ quan hệ kế thừa sang composition một cách máy móc có thể gây hại như thế nào?
Bạn sẽ thiết kế phép thử để xác nhận đối tượng sử dụng đúng hành vi của component được tiêm thay vì tự triển khai lại logic ra sao?
Bạn sẽ sử dụng test double để kiểm tra delegation mà không phụ thuộc vào implementation thật như thế nào?
Bạn sẽ thiết lập bộ kiểm thử hợp đồng chung cho nhiều component thay thế nhau nhằm bảo đảm tính tương thích ra sao?
Khi một component ném lỗi, bạn sẽ xác định trách nhiệm chuyển tiếp, chuyển đổi hoặc xử lý lỗi của đối tượng ủy quyền như thế nào?
Bạn sẽ kiểm thử các tổ hợp Strategy và Decorator để phát hiện tương tác sai mà không thử mọi hoán vị không cần thiết ra sao?
Khi một subclass cũ ghi đè nhiều phương thức, bạn sẽ tách các trách nhiệm thành component theo trình tự refactor nào?
Bạn sẽ chọn điểm đặt interface khi chuyển một hệ phân cấp Java hiện hữu sang composition mà vẫn giữ API đang được dùng như thế nào?
Bạn sẽ dùng kiểm thử hồi quy để chứng minh việc thay override bằng delegation không làm đổi hành vi quan sát được ra sao?
Khi việc refactor ảnh hưởng đến constructor của nhiều lớp con, bạn sẽ chuyển cách khởi tạo sang truyền dependency an toàn như thế nào?
Bạn sẽ đánh giá cách composition hỗ trợ thay thế implementation trong kiểm thử và tác động tới tốc độ phản hồi của nhóm ra sao?
Khi bổ sung biến thể hành vi mới, bạn sẽ xác định những lớp cần sửa để đánh giá mức độ mở rộng của thiết kế như thế nào?
Bạn sẽ so sánh hướng phụ thuộc và mức coupling của thiết kế kế thừa cũ với thiết kế composition mới bằng bằng chứng nào?
Trong trường hợp delegation gây chi phí hiệu năng, bạn sẽ đo và cân nhắc đánh đổi trước khi tối ưu như thế nào?
Bạn sẽ nhận biết thời điểm nên dừng tái cấu trúc vì mô hình composition đã đủ rõ, dễ kiểm thử và phù hợp với mức thay đổi dự kiến ra sao?

Bạn sẽ giải thích Loose Coupling và cách nó làm giảm phạm vi ảnh hưởng của một thay đổi triển khai như thế nào?
Bạn sẽ nhận biết một thành phần đang phụ thuộc vào chi tiết nội bộ của thành phần khác bằng những dấu hiệu nào trong mã Java?
Bạn sẽ phân biệt phụ thuộc cần thiết vào hợp đồng với phụ thuộc không cần thiết vào cách triển khai ra sao?
Khi sửa một lớp khiến nhiều lớp không liên quan phải biên dịch lại hoặc đổi theo, bạn sẽ phân tích nguyên nhân coupling như thế nào?
Bạn sẽ xác định những điểm cộng tác quan trọng cần được biểu diễn bằng hợp đồng tường minh thay vì trao đổi dữ liệu tùy ý ra sao?
Bạn sẽ thiết kế interface theo nhu cầu của bên sử dụng để giảm số phương thức mà client phải biết như thế nào?
Khi một interface thay đổi thường xuyên theo thư viện hạ tầng, bạn sẽ đặt ranh giới abstraction ở đâu để bảo vệ nghiệp vụ?
Bạn sẽ dùng encapsulation để ngăn client đọc hoặc sửa trực tiếp trạng thái bên trong một đối tượng cộng tác như thế nào?
Bạn sẽ đánh giá tác động của việc trả về một cấu trúc dữ liệu mutable nội bộ đối với mức coupling giữa các thành phần ra sao?
Khi client phải gọi nhiều phương thức theo đúng thứ tự để hoàn thành tác vụ, bạn sẽ cải tiến hợp đồng để giảm phụ thuộc quy trình như thế nào?
Bạn sẽ phân biệt coupling về kiểu dữ liệu với coupling về thời gian hoặc thứ tự thực hiện trong một quy trình như thế nào?
Bạn sẽ nhận biết sự phụ thuộc ngầm qua biến toàn cục, singleton có trạng thái hoặc cấu hình chung bằng cách nào?
Khi nhiều lớp cùng truy cập một cấu trúc lưu trữ, bạn sẽ giới hạn sự phụ thuộc vào schema bên trong như thế nào?
Bạn sẽ dùng Dependency Inversion để logic nghiệp vụ không import trực tiếp implementation của repository ra sao?
Bạn sẽ quyết định interface nên nằm ở module nào để hướng phụ thuộc đi về chính sách ổn định thay vì chi tiết thay đổi như thế nào?
Bạn sẽ phân biệt nguyên tắc Dependency Inversion với việc chỉ tạo một interface cho mọi class như thế nào?
Bạn sẽ chọn constructor injection thay cho việc tự new dependency trong class dựa trên những lý do nào?
Khi một dependency là tùy chọn, bạn sẽ thiết kế hợp đồng khởi tạo để không tạo ra trạng thái thiếu nhất quán như thế nào?
Bạn sẽ xác định vòng đời dependency được tiêm để tránh chia sẻ sai trạng thái giữa các lời gọi hoặc các luồng ra sao?
Khi một component cần nhiều dependency, bạn sẽ đánh giá đó là nhu cầu hợp lệ hay dấu hiệu trách nhiệm bị gom quá mức như thế nào?
Bạn sẽ tổ chức composition root để quyết định các implementation cụ thể mà không để mã nghiệp vụ biết bộ khung DI ra sao?
Khi triển khai một hệ thống bằng dependency injection framework, bạn sẽ tránh rò rỉ annotation hoặc container API vào miền nghiệp vụ như thế nào?
Bạn sẽ giải quyết việc nhiều implementation cùng đáp ứng một interface mà vẫn chọn đúng dependency theo cấu hình ra sao?
Bạn sẽ phân biệt coupling của client với interface và coupling của hệ thống với cơ chế tạo đối tượng bằng những cách nào?
Khi một service gọi trực tiếp API bên thứ ba, bạn sẽ đặt adapter như thế nào để cô lập giao thức và thay đổi của nhà cung cấp?
Bạn sẽ thiết kế dữ liệu đi qua ranh giới adapter sao cho không làm lộ các kiểu lỗi hoặc DTO riêng của thư viện bên ngoài như thế nào?
Bạn sẽ kiểm soát hợp đồng lỗi giữa hai thành phần để caller không phải kiểm tra ngoại lệ triển khai cụ thể ra sao?
Khi một implementation thêm tham số bắt buộc, bạn sẽ đánh giá liệu hợp đồng chung có cần thay đổi hay chỉ adapter cần điều chỉnh như thế nào?
Bạn sẽ nhận biết interface quá tổng quát làm giảm khả năng mô tả cộng tác và tăng coupling về ngữ nghĩa ra sao?
Bạn sẽ chia một interface lớn theo các nhóm client để giảm ảnh hưởng khi thêm một phương thức mới như thế nào?
Khi hai module liên tục gọi qua lại, bạn sẽ tìm ranh giới trách nhiệm nào để hạn chế phụ thuộc vòng tròn ra sao?
Bạn sẽ phát hiện và loại bỏ vòng phụ thuộc giữa các package Java mà vẫn giữ khả năng cộng tác cần thiết như thế nào?
Bạn sẽ phân biệt coupling giữa các lớp ở thời điểm biên dịch với coupling giữa dịch vụ ở thời điểm chạy như thế nào?
Bạn sẽ phân tích vì sao đổi từ lời gọi trực tiếp sang sự kiện không tự động xóa bỏ phụ thuộc về dữ liệu và ý nghĩa nghiệp vụ ra sao?
Khi các dịch vụ chia sẻ cùng bảng dữ liệu, bạn sẽ đánh giá mức phụ thuộc và lựa chọn cách tách quyền sở hữu như thế nào?
Bạn sẽ thiết kế hợp đồng cộng tác sao cho dữ liệu đầu vào đủ rõ ràng nhưng không buộc caller biết chi tiết quy trình bên trong ra sao?
Bạn sẽ so sánh cách truyền toàn bộ entity với truyền đối tượng dữ liệu tối thiểu qua boundary theo những rủi ro nào?
Khi cần thay đổi implementation mà giữ nguyên hợp đồng, bạn sẽ chứng minh khả năng thay thế bằng kiểm thử nào?
Bạn sẽ sử dụng test double để cô lập một dependency và kiểm tra hành vi client mà không mô phỏng quá mức chi tiết nội bộ như thế nào?
Bạn sẽ xây dựng bộ kiểm thử hợp đồng chung cho nhiều implementation để ngăn chúng diễn giải interface khác nhau ra sao?
Khi unit test thường phải khởi tạo nửa hệ thống, bạn sẽ xem đó là tín hiệu coupling chặt và chọn điểm tách nào như thế nào?
Bạn sẽ thiết kế kiểm thử tích hợp tại ranh giới thực để phát hiện giả định sai mà mock không thể bắt được ra sao?
Khi dependency bị timeout hoặc mất kết nối, bạn sẽ xác định trách nhiệm xử lý lỗi và giới hạn retry của caller như thế nào?
Bạn sẽ kiểm tra việc thêm một adapter mới có làm thay đổi code nghiệp vụ hay không để đánh giá mức coupling ra sao?
Khi refactor một class đang gọi trực tiếp thư viện hạ tầng, bạn sẽ đưa abstraction vào từng bước mà không làm gián đoạn chức năng như thế nào?
Bạn sẽ sử dụng kiểm thử hồi quy để kiểm chứng hành vi trước và sau khi thay khởi tạo trực tiếp bằng dependency injection ra sao?
Bạn sẽ đánh giá ảnh hưởng của abstraction mới đến số lớp, mức gián tiếp và khả năng tìm hiểu luồng xử lý như thế nào?
Bạn sẽ phân tích tình huống coupling chặt có chủ đích giữa hai thành phần luôn thay đổi cùng nhau và khi nào nên chấp nhận nó ra sao?
Bạn sẽ xác định dấu hiệu loose coupling bị lạm dụng thành quá nhiều interface, adapter và cấu hình gây khó bảo trì như thế nào?
Bạn sẽ đo hiệu quả sau khi giảm coupling bằng phạm vi thay đổi, khả năng kiểm thử độc lập và mức ổn định của hợp đồng như thế nào?

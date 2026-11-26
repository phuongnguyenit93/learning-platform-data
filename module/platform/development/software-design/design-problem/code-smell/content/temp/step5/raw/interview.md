Code smell là tín hiệu gì về rủi ro bảo trì và vì sao không thể kết luận có lỗi thiết kế chỉ từ tên smell?
Bạn phân biệt một code smell với bug đang gây sai kết quả và với anti-pattern ở mức kiến trúc như thế nào?
Bạn dùng lịch sử thay đổi và phản hồi của người bảo trì để xác minh một smell có gây vấn đề thực tế ra sao?
Khi một phương thức dài hàng trăm dòng, bạn tìm những nhóm thao tác có thể tách bằng Extract Method như thế nào?
Bạn sẽ phát hiện các mức trừu tượng bị trộn trong Long Method qua tên biến và lời gọi hàm ra sao?
Một phương thức dài nhưng tuyến tính và ít thay đổi có thể chấp nhận được trong ngữ cảnh nào?
Bạn tạo kiểm thử bảo vệ hành vi gì trước khi chia một phương thức chứa nhiều điều kiện nghiệp vụ?
Khi Extract Method tạo ra quá nhiều tham số, bạn xác định dữ liệu và trách nhiệm cần di chuyển như thế nào?
Bạn phân tích Large Class dựa trên số lý do thay đổi, nhóm trường và hành vi thay vì chỉ đếm dòng mã ra sao?
Bạn sẽ dùng Extract Class để tách hai nhóm trách nhiệm trong một lớp nhưng vẫn giữ API tương thích như thế nào?
Khi một lớp nhỏ chỉ ủy quyền mọi thao tác cho lớp khác, bạn đánh giá dấu hiệu Middle Man ra sao?
Bạn chọn Inline Class hoặc giữ lớp trung gian khi nó đang bảo vệ hợp đồng ổn định theo tiêu chí nào?
Bạn phân biệt Duplicate Code thực sự mang cùng một quy tắc với hai đoạn mã giống cú pháp nhưng khác ý nghĩa nghiệp vụ như thế nào?
Khi mã tính thuế bị sao chép ở nhiều vị trí, bạn tìm nơi sở hữu quy tắc chung trước khi gộp như thế nào?
Bạn lựa chọn Extract Method, Pull Up Method hoặc một abstraction mới để giảm trùng lặp dựa trên hoàn cảnh nào?
Nếu hai đoạn mã giống nhau đang thay đổi độc lập, bạn đánh giá nguy cơ tạo ghép nối mới khi hợp nhất ra sao?
Bạn nhận diện Feature Envy khi một phương thức thường xuyên đọc dữ liệu của đối tượng khác và bỏ qua trách nhiệm của chính nó như thế nào?
Bạn sử dụng Move Method để đưa hành vi về đối tượng sở hữu dữ liệu mà không tạo phụ thuộc vòng ra sao?
Khi một phương thức cần dữ liệu từ nhiều đối tượng, bạn quyết định Feature Envy có thực sự tồn tại bằng cách nào?
Bạn phát hiện Shotgun Surgery qua những thay đổi gần đây chạm tới nhiều lớp cho cùng một quy tắc ra sao?
Bạn phân biệt Shotgun Surgery với Divergent Change khi đánh giá ranh giới trách nhiệm của lớp như thế nào?
Khi một lớp thay đổi vì nhiều lý do không liên quan, bạn sẽ nhóm các thay đổi để đề xuất tách lớp như thế nào?
Một Long Parameter List làm tăng rủi ro nhầm tham số ở những trường hợp nào?
Bạn thiết kế Introduce Parameter Object để gom những tham số có quan hệ miền mà không tạo cấu trúc dữ liệu vô nghĩa như thế nào?
Bạn nhận biết Data Clumps qua các trường thường xuất hiện cùng nhau ở nhiều lớp bằng cách nào?
Khi nhóm trường ngày bắt đầu, ngày kết thúc và múi giờ lặp lại, bạn xác định invariant nào cần đóng gói trong value object?
Bạn đánh giá Primitive Obsession ở những chỗ dùng String hoặc int để biểu diễn tiền tệ, trạng thái và định danh ra sao?
Bạn lựa chọn enum, value object hoặc kiểu dữ liệu riêng để tránh nhầm đơn vị và miền giá trị như thế nào?
Khi mã có nhiều câu lệnh switch theo cùng một loại, bạn xác định nhu cầu Replace Conditional with Polymorphism ra sao?
Những trường hợp nào một switch đơn giản, ổn định lại rõ ràng hơn hệ phân cấp lớp trừu tượng?
Bạn sử dụng Decompose Conditional để làm rõ điều kiện nghiệp vụ phức tạp mà vẫn bảo toàn thứ tự đánh giá ra sao?
Khi chuỗi lời gọi dạng a.getB().getC().getD() xuất hiện rộng rãi, bạn đánh giá smell Message Chains như thế nào?
Bạn thiết kế một hành vi ở đối tượng trung gian để giảm Message Chains nhưng tránh che giấu dependency ra sao?
Bạn nhận diện Temporary Field khi một thuộc tính chỉ có ý nghĩa trong vài thao tác và xác định hướng xử lý như thế nào?
Khi một lớp chứa nhiều trường mutable cùng bị thay đổi ở các nơi khác nhau, bạn dùng kỹ thuật đóng gói nào để hạn chế trạng thái không hợp lệ?
Bạn phân biệt Data Class chỉ chứa getter/setter với DTO chủ đích không có hành vi như thế nào?
Nếu hai lớp truy cập sâu vào trường nội bộ của nhau, bạn xác định dấu hiệu Inappropriate Intimacy và ranh giới cần bảo vệ ra sao?
Bạn xử lý Dead Code bằng bằng chứng sử dụng nào khi mã có thể được gọi qua reflection hoặc cấu hình?
Bạn đánh giá vai trò của comment giải thích mã khó hiểu so với việc cải thiện tên và cấu trúc code như thế nào?
Khi một giá trị số xuất hiện lặp lại trong nhiều phép tính, bạn phân biệt magic number với hằng số có ý nghĩa rõ ràng ra sao?
Bạn sử dụng chỉ số cyclomatic complexity, độ dài phương thức và mức ghép nối để ưu tiên vùng mã cần xem xét như thế nào?
Vì sao một cảnh báo từ công cụ phân tích tĩnh chưa đủ để quyết định refactor mà không xem bối cảnh?
Bạn kết hợp phân tích lịch sử commit và tần suất sửa lỗi để xác định hot spot có smell cần ưu tiên như thế nào?
Trước khi refactor mã cũ thiếu kiểm thử, bạn viết characterization test để ghi nhận hành vi hiện tại ra sao?
Bạn xác định các giá trị biên, trạng thái lỗi và side effect phải được bảo vệ khi refactor như thế nào?
Bạn chia một đợt refactor lớn thành các thay đổi nhỏ có thể review và rollback bằng cách nào?
Sau khi Move Method hoặc Extract Class, bạn kiểm chứng phạm vi transaction và phân quyền không vô tình thay đổi ra sao?
Khi refactor làm tăng số lớp hoặc lượng mã, bạn so sánh lợi ích đọc hiểu với chi phí điều hướng như thế nào?
Bạn đánh giá xem smell được sửa ở một vị trí có tái xuất hiện dưới dạng phụ thuộc hoặc trùng lặp ở vị trí khác ra sao?
Bạn sẽ sử dụng những bằng chứng nào từ test, review và thời gian thay đổi để kết luận refactor đã cải thiện khả năng bảo trì?

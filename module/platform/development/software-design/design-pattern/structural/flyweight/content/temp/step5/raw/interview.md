Bạn giải thích Flyweight giảm mức sử dụng bộ nhớ như thế nào khi ứng dụng cần biểu diễn rất nhiều đối tượng có phần trạng thái giống nhau?
Bạn phân biệt intrinsic state và extrinsic state của một đối tượng bằng ví dụ các ký tự trong trình soạn thảo văn bản ra sao?
Bạn dựa vào tiêu chí nào để tách các trường dữ liệu thành intrinsic state lưu trong Flyweight và extrinsic state truyền từ bên ngoài?
Bạn thiết kế các đối tượng cây trong một bản đồ trò chơi sao cho hình ảnh và đặc điểm chung được chia sẻ nhưng vị trí vẫn độc lập ra sao?
Bạn phân biệt Flyweight với việc tạo một đối tượng Singleton dùng chung cho mọi yêu cầu theo cách nào?
Bạn đánh giá khi nào sự trùng lặp dữ liệu đủ lớn để lợi ích chia sẻ đối tượng vượt chi phí tra cứu qua factory?
Bạn giải thích vai trò của Flyweight Factory trong việc trả lại instance đã tồn tại thay vì khởi tạo đối tượng mới như thế nào?
Bạn thiết kế giao diện factory để client yêu cầu Flyweight theo khóa ngữ nghĩa mà không biết cơ chế lưu trữ bên trong ra sao?
Bạn xây dựng khóa tra cứu từ nhiều thuộc tính của intrinsic state để tránh trả nhầm một Flyweight không tương đương như thế nào?
Bạn xác định yêu cầu đối với equals và hashCode của khóa trong kho Flyweight để bảo đảm đối tượng được dùng chung đúng ra sao?
Bạn xử lý trường hợp khóa là đối tượng mutable có thể bị sửa sau khi đưa vào map như thế nào?
Bạn lựa chọn record hoặc value object bất biến làm khóa tra cứu Flyweight trong Java dựa trên những lợi ích nào?
Bạn phân biệt trùng lặp đối tượng theo địa chỉ bộ nhớ với sự tương đương về giá trị nội tại khi quyết định tái sử dụng ra sao?
Bạn thiết kế một lớp Flyweight bất biến để nhiều client đọc cùng instance mà không ảnh hưởng lẫn nhau như thế nào?
Bạn giải thích vì sao đặt tọa độ hoặc trạng thái chọn hiện tại vào một Flyweight dùng chung có thể gây lỗi giữa các client?
Bạn truyền extrinsic state vào phương thức thao tác thay vì gắn vào biến thành viên của Flyweight như thế nào?
Bạn quyết định có nên lưu một phần extrinsic state tại đối tượng ngữ cảnh riêng hay truyền trực tiếp từng lần gọi theo tiêu chí nào?
Bạn thiết kế một lớp Context kết hợp tham chiếu Flyweight với vị trí riêng để client thấy một thực thể hoàn chỉnh như thế nào?
Bạn lựa chọn chia sẻ một tập ảnh, font hoặc cấu hình chỉ đọc trong hàng nghìn thực thể dựa trên những ranh giới sở hữu nào?
Bạn phân biệt Flyweight với cache kết quả tính toán khi cả hai có thể dùng map để tái sử dụng dữ liệu ra sao?
Bạn phân biệt object pooling cho đối tượng mutable với Flyweight bất biến về mục đích và bảo đảm chia sẻ ra sao?
Bạn nhận diện nguy cơ kho Flyweight giữ tham chiếu đến tất cả đối tượng từng được tạo và làm tăng bộ nhớ không giới hạn ra sao?
Bạn lựa chọn kho không giới hạn, LRU có giới hạn hay tham chiếu yếu dựa trên cách phân bố và thời gian sử dụng khóa như thế nào?
Bạn đánh giá việc sử dụng WeakReference cho Flyweight ảnh hưởng đến khả năng tái sử dụng và chi phí tạo lại đối tượng ra sao?
Bạn thiết kế chính sách dọn dẹp kho đối tượng sao cho Flyweight đang được sử dụng không bị thay đổi hoặc đóng tài nguyên bất ngờ như thế nào?
Bạn xử lý khóa ít lặp lại trong dữ liệu đầu vào để tránh chi phí map lớn hơn lượng bộ nhớ tiết kiệm được ra sao?
Bạn phân tích trade-off giữa một factory tập trung và nhiều factory theo vùng dữ liệu hoặc phiên làm việc như thế nào?
Bạn xác định trường hợp nào hai tenant không nên dùng chung Flyweight dù intrinsic state có vẻ giống nhau?
Bạn thiết kế cách ngăn dữ liệu nhạy cảm của một người dùng bị đưa nhầm vào intrinsic state dùng chung như thế nào?
Bạn quyết định có đưa tham số ngôn ngữ, phiên bản hoặc cấu hình môi trường vào khóa Flyweight để tránh dùng nhầm biến thể ra sao?
Bạn xử lý nhu cầu cập nhật một thuộc tính nội tại đang được nhiều đối tượng chia sẻ mà không làm thay đổi các đối tượng cũ như thế nào?
Bạn lựa chọn tạo Flyweight phiên bản mới thay vì sửa tại chỗ một instance bất biến trong trường hợp nào?
Bạn kiểm soát tính nhất quán của kho khi hai luồng đồng thời yêu cầu cùng một khóa nhưng chưa có Flyweight như thế nào?
Bạn dùng computeIfAbsent trong ConcurrentHashMap và cân nhắc những giới hạn nào về hàm khởi tạo cũng như tác dụng phụ?
Bạn xử lý trường hợp hàm tạo Flyweight ném ngoại lệ để không giữ lại một entry chưa được khởi tạo hoàn chỉnh ra sao?
Bạn phân biệt việc đảm bảo chỉ có một instance cho mỗi khóa với tính đúng đắn nghiệp vụ khi nhiều bản sao bằng giá trị vẫn tồn tại như thế nào?
Bạn đánh giá tác động của khóa đồng bộ quanh factory đối với throughput khi số luồng và tần suất tra cứu tăng ra sao?
Bạn lựa chọn đồng bộ hóa theo toàn kho hay theo từng khóa khi việc khởi tạo Flyweight tốn nhiều thời gian như thế nào?
Bạn thiết kế Flyweight chứa dữ liệu lớn chỉ được tải khi cần và làm rõ rủi ro giữ tài nguyên lâu dài ra sao?
Bạn quản lý các tài nguyên như hình ảnh hoặc buffer được Flyweight chia sẻ để không giải phóng khi một client đơn lẻ kết thúc sử dụng như thế nào?
Bạn xác định ai chịu trách nhiệm đóng tài nguyên của Flyweight dùng chung khi factory hoặc ứng dụng kết thúc vòng đời ra sao?
Bạn lập kế hoạch đo bộ nhớ trước và sau khi dùng Flyweight bằng số lượng đối tượng, retained heap và kích thước kho như thế nào?
Bạn phân biệt số lần gọi constructor giảm với mức giảm bộ nhớ thực tế khi đánh giá hiệu quả của Flyweight ra sao?
Bạn kiểm tra ảnh hưởng của truy vấn map, băm khóa và cấp phát Context tới latency sau khi áp dụng Flyweight như thế nào?
Bạn xây dựng thử nghiệm với số lượng khóa lặp lại cao và thấp để tìm ngưỡng Flyweight thực sự có lợi ra sao?
Bạn đánh giá tác động tới garbage collection khi dùng một kho chứa ít đối tượng sống lâu thay cho nhiều đối tượng ngắn hạn như thế nào?
Bạn thiết kế unit test xác minh hai yêu cầu có cùng intrinsic state được factory trả về cùng một instance trong phạm vi đã cam kết ra sao?
Bạn kiểm thử hai khóa khác nhau để bảo đảm factory không chia sẻ nhầm đối tượng có trạng thái nội tại khác nhau như thế nào?
Bạn kiểm thử tính bất biến bằng cách thay đổi extrinsic state của một client rồi quan sát client còn lại không bị ảnh hưởng như thế nào?
Bạn kiểm thử đồng thời hàng trăm yêu cầu cho cùng một khóa để phát hiện việc tạo dư hoặc hỏng trạng thái kho như thế nào?
Bạn xác minh việc loại bỏ một Flyweight khỏi cache không làm sai kết quả của các đối tượng vẫn giữ tham chiếu tới nó ra sao?
Bạn thiết kế test cho chính sách giới hạn kích thước kho và tạo lại đối tượng khi entry đã bị loại như thế nào?
Bạn so sánh phương án lưu giá trị nội tại trực tiếp trên từng đối tượng với dùng Flyweight về độ phức tạp mã và khả năng debug ra sao?
Bạn quyết định không áp dụng Flyweight trong những trường hợp nào dù vẫn có một số thuộc tính trùng lặp giữa các đối tượng?
Bạn dùng bằng chứng về bộ nhớ, độ trễ, tỷ lệ tái sử dụng và tính an toàn đồng thời để đánh giá Flyweight có đáng được duy trì không?

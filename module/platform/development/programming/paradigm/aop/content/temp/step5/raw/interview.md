Bạn giải thích lập trình hướng khía cạnh (AOP) giải quyết loại mối quan tâm nào và quan hệ của nó với lập trình hướng đối tượng như thế nào?
Bạn nhận diện hiện tượng mã xử lý mối quan tâm cắt ngang bị rải rác ở nhiều nơi trong một hệ thống bằng những dấu hiệu nào?
Bạn phân biệt code scattering và code tangling trong một ứng dụng thực tế như thế nào?
Khi nào việc tách ghi log, đo hiệu năng hoặc kiểm soát truy cập thành aspect thực sự cải thiện tính mô đun của hệ thống?
Bạn phân biệt aspect, join point, pointcut, advice và weaving bằng một luồng thực thi cụ thể như thế nào?
Bạn giải thích join point model của một hệ AOP quy định những điểm nào trong chương trình có thể được can thiệp ra sao?
Bạn phân biệt join point là sự kiện thực thi với pointcut là quy tắc lựa chọn các join point như thế nào?
Bạn đánh giá một yêu cầu nghiệp vụ có nên được triển khai bằng aspect hay nên giữ trong mô hình miền dựa trên các tiêu chí nào?
Bạn so sánh AOP với decorator, interceptor, proxy và lời gọi hàm tường minh về cách biểu đạt mối quan tâm cắt ngang như thế nào?
Bạn giải thích sự khác biệt giữa việc can thiệp tĩnh vào mã và việc quyết định can thiệp dựa trên trạng thái khi chạy như thế nào?
Bạn mô tả ảnh hưởng của một aspect đến cấu trúc phụ thuộc và khả năng đọc luồng điều khiển của chương trình ra sao?
Bạn xác định ranh giới trách nhiệm giữa logic nghiệp vụ và khía cạnh kiểm toán hoặc đo lường như thế nào?
Bạn lựa chọn những mối quan tâm cắt ngang nào cần được áp dụng nhất quán trên nhiều mô đun, và quản lý sự thay đổi chính sách của chúng ra sao?
Bạn thiết kế tài liệu kỹ thuật như thế nào để người bảo trì biết hành vi nào được aspect bổ sung tại mỗi điểm thực thi?
Bạn xây dựng tiêu chí đánh giá khi AOP gây thêm độ phức tạp ẩn thay vì đem lại lợi ích tách biệt mối quan tâm như thế nào?
Bạn thiết kế pointcut tái sử dụng được cho nhiều advice mà vẫn giữ phạm vi lựa chọn rõ ràng như thế nào?
Bạn lựa chọn điều kiện dựa trên tên, chữ ký, gói hoặc metadata để tránh pointcut khớp quá rộng như thế nào?
Bạn so sánh join point tại lúc gọi phương thức với join point tại lúc thực thi phương thức trong trường hợp hai mô đun gọi nhau ra sao?
Bạn đánh giá ý nghĩa của join point liên quan đến constructor và thao tác truy cập thuộc tính trong các mô hình AOP có hỗ trợ chúng như thế nào?
Bạn phân biệt điều kiện pointcut dựa trên vị trí khai báo mã với điều kiện dựa trên đối tượng ở thời điểm thực thi ra sao?
Bạn xác định cách ràng buộc tham số và giá trị ngữ cảnh của join point cho advice mà vẫn duy trì tính an toàn kiểu như thế nào?
Bạn đánh giá chi phí và tính đúng đắn của pointcut có điều kiện kiểm tra động trên mỗi lần gọi phương thức ra sao?
Bạn thiết kế pointcut phủ nhiều đường gọi khác nhau mà không vô tình thu thập phương thức nội bộ hoặc hàm trợ giúp như thế nào?
Bạn áp dụng phép kết hợp, loại trừ và đặt tên pointcut để biểu đạt các quy tắc lựa chọn phức tạp như thế nào?
Bạn kiểm tra pointcut có tiếp tục khớp đúng sau khi đổi tên phương thức, tách lớp hoặc di chuyển gói bằng cách nào?
Bạn giải thích vì sao kiểu khai báo, kiểu thực tế của đối tượng và quan hệ kế thừa có thể làm thay đổi kết quả khớp pointcut ra sao?
Bạn phân tích khác biệt giữa metadata được kế thừa và metadata chỉ gắn trực tiếp tại phương thức khi xây dựng pointcut dựa trên annotation như thế nào?
Bạn thiết kế điều kiện lựa chọn join point cho các lời gọi lồng nhau nhằm tránh ghi nhận trùng lặp như thế nào?
Trong một hệ AOP hỗ trợ điều kiện theo luồng điều khiển, bạn sử dụng ngữ cảnh chuỗi lời gọi để giới hạn phạm vi can thiệp ra sao?
Bạn xây dựng cách kiểm chứng danh sách join point thực sự được chọn bởi pointcut trước khi đưa thay đổi lên môi trường chạy như thế nào?
Bạn phân biệt before, after returning, after throwing và after dạng finally qua thứ tự thực thi và thông tin mỗi advice quan sát được như thế nào?
Bạn xác định thời điểm phù hợp để dùng around advice thay vì những loại advice chỉ quan sát sự kiện như thế nào?
Bạn giải thích hợp đồng tiếp tục thực thi join point gốc trong around advice và những điều cần bảo toàn khi chuyển tiếp lời gọi ra sao?
Bạn phân tích điều gì có thể xảy ra khi around advice không cho phép lời gọi gốc tiếp tục hoặc thực hiện nó nhiều lần như thế nào?
Bạn xử lý giá trị trả về của phương thức được can thiệp như thế nào để around advice không làm sai hợp đồng kiểu và hành vi?
Bạn phân biệt ngoại lệ xuất phát từ lời gọi gốc với ngoại lệ do advice phát sinh khi thiết kế cơ chế ghi log và lan truyền lỗi như thế nào?
Bạn giải thích sự khác nhau giữa after returning, after throwing và finally khi lời gọi gốc kết thúc bất thường ra sao?
Bạn tổ chức advice để đo thời gian xử lý của phương thức mà vẫn ghi nhận được cả trường hợp thành công và thất bại như thế nào?
Bạn lựa chọn nguồn đo thời gian đơn điệu và vị trí bắt đầu kết thúc đo trong advice để tránh số liệu sai lệch ra sao?
Bạn đánh giá rủi ro khi advice thay đổi tham số đầu vào, kết quả trả về hoặc ngoại lệ của phương thức gốc như thế nào?
Bạn phát hiện và ngăn lời gọi đệ quy ngoài ý muốn khi chính advice gọi tới phương thức cũng khớp pointcut ra sao?
Bạn thiết kế hành vi của advice để bản thân lỗi ghi log hoặc xuất số liệu không làm gián đoạn xử lý nghiệp vụ như thế nào?
Bạn phân tích cách nhiều advice cùng tác động vào một join point và vì sao thứ tự của chúng có thể thay đổi kết quả ra sao?
Bạn thiết lập và kiểm chứng quy tắc precedence giữa các aspect phụ thuộc nhau bằng những cách nào?
Bạn giải thích cấu trúc lồng nhau của nhiều around advice và thời điểm lời gọi gốc được tiếp tục như thế nào?
Bạn giải quyết xung đột khi hai aspect cùng thay đổi giá trị trả về hoặc cùng xử lý một ngoại lệ ra sao?
Bạn xây dựng nguyên tắc thiết kế để các aspect quan sát độc lập hạn chế phụ thuộc vào thứ tự thực thi như thế nào?
Bạn so sánh cách quản lý trạng thái của aspect dùng chung với trạng thái gắn theo đối tượng hoặc ngữ cảnh thực thi ra sao?
Bạn xác định và kiểm soát nguy cơ rò rỉ trạng thái khi một aspect giữ dữ liệu liên quan đến từng lần gọi như thế nào?
Bạn thiết kế chính sách xử lý ngoại lệ trong advice có tính đến ngoại lệ phát sinh khi giải phóng tài nguyên như thế nào?
Bạn so sánh compile-time weaving, post-compile weaving và load-time weaving về thời điểm biến đổi chương trình như thế nào?
Bạn phân tích ưu điểm và chi phí vận hành của weaving khi biên dịch so với weaving khi nạp lớp ra sao?
Bạn giải thích khác biệt giữa sửa đổi bytecode và can thiệp qua đối tượng trung gian tại thời điểm chạy như thế nào?
Bạn nhận diện những join point mà cơ chế dựa trên proxy không thể quan sát đầy đủ nhưng cơ chế weaving vào bytecode có thể hỗ trợ ra sao?
Bạn phân tích ảnh hưởng của lời gọi nội bộ giữa các phương thức trong cùng đối tượng đến phạm vi can thiệp của các cơ chế AOP khác nhau như thế nào?
Bạn đánh giá cách visibility của phương thức, phương thức static và phương thức final ảnh hưởng đến tính khả thi của từng cơ chế can thiệp ra sao?
Bạn kiểm tra tương tác giữa aspect và các phương thức bridge hoặc synthetic do trình biên dịch sinh ra như thế nào?
Bạn giải thích tại sao thứ tự tải lớp và sự phân tách giữa các class loader có thể ảnh hưởng đến load-time weaving như thế nào?
Bạn tổ chức quy trình build sao cho bản mã đã được weaving có thể tạo lại nhất quán từ cùng nguồn và cùng cấu hình như thế nào?
Bạn xác nhận một lớp đã được weaving đúng và không bị weaving hai lần bằng những phương pháp kiểm tra nào?
Bạn phân tích rủi ro tương thích khi công cụ weaving biến đổi bytecode được biên dịch bởi phiên bản ngôn ngữ mới ra sao?
Bạn đánh giá ảnh hưởng của weaving tới thông tin gỡ lỗi, stack trace và khả năng liên hệ bytecode với mã nguồn như thế nào?
Bạn kiểm tra việc can thiệp vào lớp thư viện bên thứ ba có làm thay đổi những giả định về hành vi hoặc hợp đồng API như thế nào?
Bạn xác định các giới hạn khi AOP phối hợp với module boundary, reflection hoặc chính sách đóng gói của runtime ra sao?
Bạn phân tích tương tác giữa instrumentation của AOP với công cụ coverage, profiler và các tác nhân quan sát khác như thế nào?
Bạn lựa chọn cách xử lý phù hợp khi cần nạp hoặc cập nhật aspect trong lúc hệ thống đang chạy nhưng môi trường có giới hạn thay đổi lớp ra sao?
Bạn phân biệt việc bổ sung hành vi qua advice với việc bổ sung thành viên hoặc quan hệ kiểu qua cơ chế introduction trong các hệ AOP hỗ trợ như thế nào?
Bạn đánh giá lợi ích và rủi ro của inter-type declaration đối với hợp đồng kiểu và khả năng bảo trì mã như thế nào?
Bạn sử dụng cơ chế kiểm tra quy tắc kiến trúc tại các join point để phát hiện việc gọi API không được phép như thế nào?
Bạn thiết kế aspect kiểm toán sao cho có đủ thông tin truy vết nhưng không ghi nhận dữ liệu nhạy cảm vượt quá nhu cầu ra sao?
Bạn đặt khía cạnh kiểm soát quyền truy cập tại đâu để giảm nguy cơ bỏ sót những đường thực thi quan trọng như thế nào?
Bạn giải thích vì sao kiểm tra truy cập bằng aspect cần được đối chiếu với các ranh giới tin cậy và điểm vào thực tế của hệ thống ra sao?
Bạn sử dụng AOP để đo số lần gọi và độ trễ phương thức mà không tạo số lượng nhãn metric quá lớn như thế nào?
Bạn thiết kế cơ chế lấy mẫu trace trong advice để hạn chế overhead nhưng vẫn giữ khả năng điều tra lỗi ra sao?
Bạn xây dựng aspect ghi nhận correlation ID cho nhiều lời gọi lồng nhau và ngăn trộn ngữ cảnh giữa các yêu cầu như thế nào?
Bạn thiết kế cơ chế truyền ngữ cảnh quan sát khi luồng xử lý đổi thread hoặc tiếp tục bất đồng bộ ra sao?
Bạn phân biệt thời điểm một phương thức trả về kết quả bất đồng bộ với thời điểm tác vụ thực sự hoàn tất khi áp dụng advice đo thời gian như thế nào?
Bạn đánh giá rủi ro khi dùng aspect để retry một thao tác có side effect và quyết định điều kiện idempotency cần thiết ra sao?
Bạn thiết kế pointcut và advice cho cache kết quả mà vẫn giữ đúng chính sách tạo khóa, hết hạn và vô hiệu hóa dữ liệu như thế nào?
Bạn phân tích quan hệ giữa aspect quản lý giao dịch và các điểm phát sinh ngoại lệ hoặc lời gọi lồng nhau như thế nào?
Bạn phát hiện trường hợp aspect bảo vệ tài nguyên hoặc quản lý giao dịch vô tình thay đổi thứ tự cleanup như thế nào?
Bạn đánh giá khi nào việc tạo audit event hoặc domain event từ aspect có thể khiến hành vi nghiệp vụ trở nên khó hiểu ra sao?
Bạn thiết kế chính sách bật tắt hoặc cấu hình aspect theo môi trường mà không làm thay đổi bất ngờ kết quả nghiệp vụ như thế nào?
Bạn kiểm soát race condition khi nhiều luồng đồng thời gọi advice dùng chung trạng thái mutable bằng cách nào?
Bạn phân tích nguy cơ deadlock khi advice lấy khóa trước hoặc sau các khóa của nghiệp vụ và cách kiểm chứng thứ tự khóa ra sao?
Bạn phát hiện rò rỉ ngữ cảnh do ThreadLocal trong aspect khi thread được tái sử dụng hoặc thực thi chuyển sang thread khác như thế nào?
Bạn thiết kế advice có thể tái nhập mà không làm sai số đếm, depth tracking hoặc trạng thái của lần gọi trước như thế nào?
Bạn lập kế hoạch benchmark để tách chi phí của pointcut matching, advice và logic nghiệp vụ gốc ra sao?
Bạn đánh giá overhead do allocation, tra cứu metadata hoặc ghi log trong advice ở những đường gọi có tần suất cao như thế nào?
Bạn giải thích cách instrumentation có thể ảnh hưởng đến tối ưu JIT, inlining và biểu đồ độ trễ ở tải production ra sao?
Bạn xác định ngân sách hiệu năng và điều kiện vô hiệu hóa một aspect khi độ trễ vượt ngưỡng cho phép như thế nào?
Bạn xây dựng unit test cho pointcut để chứng minh cả những join point phải khớp và không được khớp như thế nào?
Bạn xây dựng kiểm thử cho từng loại advice trong cả đường đi thành công, ném ngoại lệ và thực thi lồng nhau ra sao?
Bạn kiểm thử thứ tự can thiệp của nhiều aspect để phát hiện thay đổi precedence ngoài dự kiến bằng cách nào?
Bạn kiểm tra hành vi của around advice khi phương thức gốc có side effect hoặc được gọi lại nhiều lần như thế nào?
Bạn thiết kế integration test xác nhận hành vi trên mã đã được weaving trong đúng cấu hình runtime mà ứng dụng sử dụng ra sao?
Bạn chẩn đoán nguyên nhân khi một pointcut từng khớp nhưng ngừng khớp sau refactor hoặc nâng cấp trình biên dịch như thế nào?
Bạn điều tra một lỗi chỉ xuất hiện khi bật nhiều aspect đồng thời mà không xuất hiện khi chạy riêng từng aspect bằng cách nào?
Bạn lập bản đồ quan hệ giữa aspect và những phương thức chúng can thiệp để hỗ trợ code review và đánh giá tác động thay đổi ra sao?
Bạn tổ chức thử nghiệm bật aspect theo phạm vi nhỏ và theo dõi tín hiệu rollback khi phát hành một chính sách can thiệp mới như thế nào?
Bạn đánh giá tính phù hợp lâu dài của AOP trong một hệ thống có nhiều mô đun dựa trên tính quan sát, khả năng kiểm thử và chi phí bảo trì ra sao?

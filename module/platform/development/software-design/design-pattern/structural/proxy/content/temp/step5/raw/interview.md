Bạn giải thích mục đích của Proxy khi client cần tương tác với đối tượng thật thông qua một đối tượng đại diện cùng hợp đồng như thế nào?
Bạn phân biệt vai trò Subject, RealSubject và Proxy trong một ví dụ truy cập tài liệu có phân quyền ra sao?
Những dấu hiệu nào cho thấy nên đặt Proxy trước một đối tượng thay vì cho client gọi trực tiếp vào RealSubject?
Bạn phân biệt Proxy với Decorator khi cả hai đều bọc đối tượng nhưng một bên chủ yếu kiểm soát truy cập còn bên kia mở rộng hành vi ra sao?
Bạn so sánh Proxy và Adapter theo khả năng giữ nguyên giao diện mà client đang sử dụng như thế nào?
Bạn xác định khi nào một Proxy cần khởi tạo sẵn RealSubject và khi nào nên trì hoãn đến lời gọi đầu tiên?
Bạn thiết kế virtual proxy cho tài nguyên có chi phí khởi tạo cao mà vẫn giữ cho client cảm nhận một giao diện nhất quán như thế nào?
Bạn phân tích rủi ro khởi tạo lặp RealSubject nếu nhiều luồng gọi đồng thời vào một lazy proxy chưa được khởi tạo ra sao?
Bạn lựa chọn đồng bộ hóa, khởi tạo sớm hoặc cấu trúc bất biến để bảo đảm lazy initialization an toàn theo những tiêu chí nào?
Bạn quyết định có thử lại việc tạo RealSubject sau lỗi khởi tạo hay không dựa trên những yếu tố nào?
Bạn thiết kế protection proxy để từ chối thao tác không đủ quyền trước khi phát sinh bất kỳ thay đổi dữ liệu nào ra sao?
Bạn xác định danh tính và ngữ cảnh quyền hạn của người gọi được truyền tới Proxy qua cơ chế nào để tránh dùng nhầm quyền của yêu cầu khác?
Bạn bảo đảm Proxy không trở thành lớp kiểm tra quyền duy nhất nếu RealSubject còn được gọi qua những đường khác như thế nào?
Bạn thiết kế remote proxy sao cho sự khác biệt giữa lỗi mạng và lỗi nghiệp vụ của đối tượng từ xa vẫn được thể hiện rõ với client ra sao?
Bạn đánh giá sự khác nhau về latency, timeout và độ sẵn sàng giữa gọi một đối tượng trong tiến trình và gọi qua remote proxy như thế nào?
Bạn đặt giới hạn timeout và retry của remote proxy ở đâu để tránh lặp lại những thao tác không idempotent?
Bạn phân tích tình huống remote proxy không nhận được phản hồi dù server có thể đã xử lý yêu cầu như thế nào?
Bạn thiết kế cơ chế idempotency hoặc định danh yêu cầu để remote proxy hỗ trợ retry an toàn ra sao?
Bạn lựa chọn những kết quả nào có thể cache tại Proxy mà không vi phạm tính cập nhật hoặc quyền truy cập của dữ liệu?
Bạn xác định khóa cache, TTL và quy tắc vô hiệu cache của Proxy khi RealSubject có phương thức đọc và ghi như thế nào?
Bạn xử lý cache stampede khi nhiều yêu cầu đồng thời truy cập một giá trị chưa có trong cache của Proxy ra sao?
Bạn phân biệt Proxy cache với một lớp cache độc lập về trách nhiệm và phạm vi sử dụng như thế nào?
Bạn thiết kế một Proxy ghi log hoặc đo thời gian mà không làm rò rỉ tham số chứa bí mật hoặc dữ liệu nhạy cảm ra sao?
Bạn bảo đảm Proxy giữ đúng kiểu kết quả, hợp đồng ngoại lệ và những tác dụng phụ được phép của Subject như thế nào?
Bạn kiểm chứng nguyên tắc thay thế khi RealSubject và Proxy đều được truyền vào cùng một client như thế nào?
Bạn xây dựng JDK Dynamic Proxy từ một interface và một InvocationHandler theo các bước khái niệm nào?
Bạn giải thích cơ chế InvocationHandler nhận đối tượng proxy, Method và danh sách tham số của lời gọi ra sao?
Bạn thiết kế một InvocationHandler chung cho nhiều phương thức nhưng vẫn áp dụng đúng chính sách riêng theo từng method như thế nào?
Bạn phân biệt xử lý lời gọi method khai báo trong interface với các method của Object như equals, hashCode và toString như thế nào?
Bạn tránh gọi lại method trên chính đối tượng proxy trong InvocationHandler dẫn tới đệ quy vô hạn bằng cách nào?
Bạn xử lý giá trị trả về của phương thức void hoặc phương thức trả về kiểu nguyên thủy khi viết InvocationHandler ra sao?
Bạn bảo toàn nguyên nhân ngoại lệ gốc khi lời gọi phản chiếu qua Method.invoke sinh ra InvocationTargetException như thế nào?
Bạn quyết định sử dụng JDK Dynamic Proxy hay một proxy dựa trên subclass khi lớp cần bọc không có interface ra sao?
Bạn giải thích tác động của final class hoặc final method đối với kỹ thuật tạo proxy dựa trên kế thừa như thế nào?
Bạn lựa chọn ClassLoader phù hợp khi tạo JDK Dynamic Proxy trong môi trường có nhiều module hoặc class loader ra sao?
Bạn quản lý danh tính đối tượng khi code thực hiện so sánh tham chiếu giữa Proxy và RealSubject như thế nào?
Bạn xác định trường hợp nào client cần biết đây là Proxy và trường hợp nào nên giữ sự trong suốt của đối tượng đại diện?
Bạn phân biệt Spring AOP proxy với một Proxy được tạo thủ công về cơ chế lắp ghép và phạm vi chặn lời gọi ra sao?
Vì sao lời gọi từ một method tới method khác trên cùng instance có thể bỏ qua interceptor của Spring proxy?
Bạn xử lý self-invocation khi cần chính sách transaction hoặc caching được thực thi qua Spring proxy bằng cách tổ chức lại ranh giới lớp ra sao?
Bạn đánh giá tác động của @Transactional hoặc @Cacheable với method không được đi qua proxy trong ứng dụng Spring như thế nào?
Bạn xác định các ràng buộc về mức truy cập và đặc tính method có thể ảnh hưởng đến khả năng interceptor hoạt động ra sao?
Bạn kiểm soát thứ tự nhiều interceptor hoặc advice cùng áp dụng lên một method để hành vi logging, phân quyền và transaction không mâu thuẫn như thế nào?
Bạn phân biệt proxy được khởi tạo trong Spring container với đối tượng tự tạo bằng new khi kiểm tra vì sao advice không chạy ra sao?
Bạn thiết kế cấu hình dependency injection để client sử dụng đúng Spring proxy mà không vô tình giữ RealSubject chưa được bọc như thế nào?
Bạn nhận diện vòng phụ thuộc hoặc lỗi khởi tạo bean khi một proxy tham chiếu ngược đối tượng đang được tạo ra sao?
Bạn xác định vòng đời và trách nhiệm giải phóng tài nguyên khi Proxy trì hoãn tạo RealSubject đến lúc sử dụng như thế nào?
Bạn kiểm soát trạng thái dùng chung trong Proxy khi nhiều request đồng thời truy cập cùng một RealSubject như thế nào?
Bạn thiết kế cơ chế giới hạn số lời gọi đồng thời qua Proxy để bảo vệ RealSubject khỏi quá tải ra sao?
Bạn đo overhead do phản chiếu, interceptor, cache lookup và chuyển tiếp lời gọi để đánh giá tác động hiệu năng của Proxy như thế nào?
Bạn phân biệt chi phí của Proxy với chi phí nghiệp vụ thực của RealSubject bằng phương án benchmark hoặc tracing nào?
Bạn thiết kế unit test cho protection proxy để chứng minh lời gọi trái quyền bị chặn trước khi RealSubject được gọi như thế nào?
Bạn kiểm thử virtual proxy để xác nhận RealSubject chỉ được khởi tạo khi cần và không bị tạo dư khi nhiều luồng cùng gọi ra sao?
Bạn kiểm thử một InvocationHandler với method có tham số, kiểu trả về và ngoại lệ khác nhau mà không phụ thuộc quá mức vào chi tiết reflection như thế nào?
Bạn xác minh hành vi thực tế của @Transactional hoặc @Cacheable qua Spring proxy bằng một integration test phù hợp ra sao?
Bạn kiểm thử remote proxy khi mạng timeout, phản hồi lỗi hoặc bị ngắt kết nối để xác nhận việc chuyển đổi lỗi và retry đúng hợp đồng như thế nào?
Những dấu hiệu nào cho thấy Proxy đang làm luồng gọi khó debug hoặc tăng coupling hơn lợi ích kiểm soát truy cập, cache và khởi tạo trễ?
Bạn dựa trên chỉ số về chi phí lời gọi, khả năng kiểm thử, an toàn dữ liệu và vòng đời để quyết định nên giữ, thay đổi hay bỏ Proxy?

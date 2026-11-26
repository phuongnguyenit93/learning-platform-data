Một dịch vụ nhập dữ liệu từ hệ thống cũ trả về List không khai báo kiểu, khiến ClassCastException chỉ xuất hiện khi xử lý đơn hàng; hãy xác định cách thiết kế hợp đồng kiểu an toàn và chiến lược chuyển đổi từng bước.
Một thư viện dùng chung cần lưu và truy vấn Customer, Invoice và Shipment với các loại khóa định danh khác nhau; hãy thiết kế giao diện repository generic để không thể truyền nhầm khóa giữa các loại thực thể.
Một phương thức nhận List<Order> để đọc báo cáo nhưng bên gọi có List<PriorityOrder> và không thể truyền trực tiếp; hãy phân tích ràng buộc kiểu và điều chỉnh hợp đồng đọc dữ liệu mà vẫn bảo toàn an toàn kiểu.
Hệ thống xuất báo cáo nhận dữ liệu từ nhiều danh sách con của Product và chỉ duyệt phần tử; hãy xác định cách thiết kế tham số generic để nhận được các danh sách này mà không cho phép thêm sai loại.
Bộ nhập kho cần thêm đối tượng PremiumItem vào các collection chấp nhận Item hoặc lớp cha; hãy đề xuất hợp đồng generic cho thao tác ghi và nêu các giới hạn khi đọc lại phần tử.
Nhóm nền tảng xây công cụ chuyển đổi một Map khóa chuỗi thành danh sách giá trị thuộc nhiều kiểu thực thể; hãy xác định tham số kiểu và kiểm tra các trường hợp trình biên dịch không suy luận được kiểu mong muốn.
Một thư viện sắp xếp các đối tượng nghiệp vụ theo thứ tự tự nhiên nhưng chỉ một số loại đối tượng có khả năng so sánh; hãy thiết kế giới hạn kiểu generic để loại bỏ đối số sai ngay khi biên dịch.
Nhóm API định nghĩa hai phương thức nạp chồng chỉ khác nhau bởi List<String> và List<Integer> rồi gặp lỗi biên dịch; hãy phân tích cơ chế type erasure và thiết kế lại API không gây trùng chữ ký.
Bộ giải mã JSON cần tái tạo List<Customer> và List<Invoice> theo cấu hình ở runtime nhưng chỉ có Class đối tượng gốc; hãy phân tích trở ngại type erasure và xác định thông tin kiểu cần bảo toàn.
Một bộ nhớ đệm tổng quát muốn tạo mảng đối tượng chứa kiểu T bất kỳ và gặp hạn chế biên dịch; hãy đánh giá các cách biểu diễn dữ liệu thay thế để tránh unchecked cast gây lỗi ngầm.
Lớp adapter kết nối API raw type của bên thứ ba với các service đã dùng generics, gây hàng loạt cảnh báo unchecked; hãy xác định ranh giới kiểm tra dữ liệu và cách cô lập chuyển đổi kiểu nguy hiểm.
Một helper generic nhận hai collection từ các nguồn khác nhau, nhưng kiểu suy luận rộng hơn dự kiến và làm mất ràng buộc miền nghiệp vụ; hãy phân tích chữ ký và trường hợp cần cung cấp kiểu tường minh.
Ứng dụng tích hợp có lớp con ghi đè một phương thức generic của lớp cha nhưng mã reflection nhìn thấy thêm phương thức cầu nối; hãy phân tích cách xác định phương thức nghiệp vụ thực sự khi lập bộ đăng ký handler.
Một cache dùng chung lưu giá trị thuộc nhiều lớp dưới cùng một khóa String, dẫn đến lấy nhầm kiểu ở module khác; hãy thiết kế khóa cache mang thông tin kiểu và cách kiểm soát tương thích lúc đọc.
Hệ thống thanh toán đang dùng chuỗi tự do cho trạng thái giao dịch, khiến cùng một trạng thái bị ghi dưới nhiều cách viết; hãy thiết kế mô hình enum và quy tắc chuyển trạng thái có thể kiểm thử.
Một cổng đối tác gửi tên trạng thái mới chưa có trong enum của hệ thống; hãy xác định hành vi khi ánh xạ dữ liệu ngoài vào miền nghiệp vụ mà vẫn theo dõi được giá trị chưa nhận diện.
Dịch vụ thống kê cần đếm số đơn theo từng trạng thái enum với tần suất cập nhật lớn; hãy so sánh đặc tính của EnumMap với các cấu trúc Map khác cho trường hợp này.
Hệ thống phân quyền cho phép mỗi tài khoản sở hữu nhiều quyền thuộc một enum cố định; hãy thiết kế biểu diễn tập quyền và thao tác hợp, giao, loại trừ có khả năng mở rộng.
Một bản phát hành bổ sung giá trị enum mới nhưng một số nhánh switch ở các service vẫn theo quy tắc cũ; hãy lập phương án kiểm tra tác động và phát hiện luồng nghiệp vụ chưa xử lý.
Ứng dụng dùng enum gắn metadata về mã nghiệp vụ, nhãn và độ ưu tiên, sau đó một nhóm muốn thay đổi metadata tùy người dùng; hãy đánh giá thiết kế enum để tránh trạng thái dùng chung bị sửa ngoài ý muốn.
Một API công khai truyền tên enum qua JSON và phải hỗ trợ khách hàng đang dùng phiên bản cũ; hãy xác định cách tách định danh ổn định khỏi nhãn hiển thị và quản lý thay đổi tương thích.
Nền tảng khai báo annotation kiểm tra quyền truy cập trên phương thức nhưng bộ lọc runtime không tìm thấy annotation; hãy truy vết cấu hình retention và cơ chế đọc metadata.
Một nhóm đặt annotation dành cho phương thức lên trường dữ liệu và nhận lỗi biên dịch; hãy xác định ranh giới áp dụng annotation và cách biểu đạt phạm vi hợp lệ.
Một thư viện dùng annotation để mô tả trường bắt buộc trong DTO, nhưng công cụ tạo tài liệu chỉ đọc lớp mà bỏ sót thông tin trên phương thức; hãy thiết kế cách quét annotation theo đúng nơi khai báo.
Một lớp nghiệp vụ kế thừa lớp cha có annotation đánh dấu cấu hình, nhưng annotation gắn trên method override không được kế thừa như mong đợi; hãy phân tích quy tắc kế thừa metadata cần kiểm chứng.
Framework plugin định nghĩa annotation có tham số tùy chọn và giá trị mặc định; hãy thiết kế cách diễn giải cấu hình để phân biệt giá trị mặc định với giá trị người phát triển khai báo.
Một cơ chế audit chỉ dựa vào annotation rồi có tuyến gọi không đi qua bộ chặn, khiến sự kiện quan trọng bị bỏ ghi; hãy xác định các đường gọi cần kiểm thử và ranh giới bảo đảm của cơ chế xử lý annotation.
Trong lúc nâng cấp thư viện raw type cũ, nhóm phát triển thêm SuppressWarnings trên mọi lớp để làm sạch build; hãy đề xuất phạm vi xử lý cảnh báo thích hợp và cách kiểm chứng tính an toàn của phần chuyển đổi.
Một tác vụ định kỳ xóa phần tử hết hạn trong ArrayList ngay bên trong vòng for-each và gặp ConcurrentModificationException; hãy phân tích nguyên nhân và cách thiết kế quy trình loại bỏ phần tử an toàn.
Một lớp truy cập dữ liệu muốn cung cấp Iterable để bộ xử lý duyệt lần lượt hàng triệu bản ghi từ nguồn I/O; hãy làm rõ hợp đồng iterator, thời điểm đọc dữ liệu và quản lý tài nguyên khi dừng giữa chừng.
Ứng dụng cần cập nhật các ô mảng theo chỉ số gốc nhưng mã for-each chỉ có bản sao giá trị phần tử; hãy phân tích khác biệt giữa biến lặp và vị trí phần tử khi chỉnh sửa mảng.
Một tác vụ xử lý danh sách giỏ hàng có vòng for-each lồng nhau và đôi khi bổ sung mặt hàng vào collection đang duyệt; hãy thiết kế cách tách đọc và thay đổi dữ liệu để tránh kết quả phụ thuộc thứ tự.
Hệ thống tính phí đọc số lượng kiểu Integer từ dữ liệu có thể thiếu và bất ngờ gặp NullPointerException ở phép tính số học; hãy phân tích đường đi của autounboxing và xây chính sách xử lý giá trị thiếu.
Bộ kiểm tra cache so sánh hai đối tượng Integer bằng toán tử đồng nhất tham chiếu, nên một số giá trị có kết quả khác nhau giữa môi trường; hãy thiết kế kiểm thử và quy tắc so sánh giá trị số đúng đắn.
Một pipeline xử lý hàng chục triệu số đo liên tục tạo đối tượng wrapper trong vòng lặp và gây áp lực GC; hãy đánh giá chi phí boxing và chọn biểu diễn dữ liệu phù hợp cho đường nóng.
Ứng dụng dùng Boolean nullable để mô tả tùy chọn ba trạng thái nhưng logic rẽ nhánh tự động unbox khi giá trị chưa có; hãy xác định cách thể hiện rõ ba trạng thái và tránh lỗi runtime.
Bảng tổng hợp lưu số lượng bằng Long trong Map và mã cộng dồn giả định khóa nào cũng có giá trị; hãy phân tích trường hợp khóa chưa xuất hiện, autoboxing và khả năng tràn số khi tích lũy.
Thư viện logging có overload nhận Object đơn và overload varargs, khiến lời gọi với null hoặc mảng gây chọn phương thức khó đoán; hãy xác định cách thiết kế API và trường hợp cần kiểm thử lúc biên dịch.
Một helper nhận varargs của các danh sách generic và bị cảnh báo heap pollution khi ghi vào mảng tham số; hãy phân tích nguồn mất an toàn kiểu và thiết kế giao diện giảm rủi ro.
Một hàm tiện ích varargs giữ lại mảng đối số do caller truyền rồi thay đổi phần tử sau khi trả về; hãy phân tích vấn đề aliasing và quy ước về quyền sở hữu dữ liệu đầu vào.
Trong đường xử lý giao dịch có độ trễ thấp, một lời gọi varargs diễn ra hàng triệu lần mỗi giây; hãy xây kế hoạch đo chi phí cấp phát mảng, khả năng tối ưu và ảnh hưởng đến tính dễ đọc API.
Một HashSet dùng để loại trùng mã khách hàng vẫn chứa hai đối tượng có cùng mã nghiệp vụ; hãy phân tích hợp đồng equals/hashCode và thiết kế bộ kiểm thử tính nhất quán.
Hệ thống dùng đối tượng chứa trường có thể sửa làm khóa HashMap, sau khi sửa mã định danh thì không tìm lại được bản ghi; hãy truy vết nguyên nhân và xác định quy tắc bất biến cho khóa.
Hàng đợi ưu tiên xử lý sự cố dựa trên mức khẩn cấp nhưng bộ phận vận hành duyệt trực tiếp PriorityQueue và thấy thứ tự hiển thị bất thường; hãy phân tích hợp đồng ordering và cách xây báo cáo tuần tự.
Một báo cáo phải duy trì thứ tự bản ghi xuất hiện trong dữ liệu đầu vào, đồng thời loại bản ghi trùng; hãy lựa chọn cấu trúc collection dựa trên yêu cầu thứ tự, độ phức tạp và quy tắc trùng lặp.
Một TreeSet có Comparator chỉ xét độ ưu tiên, khiến hai tác vụ khác ID bị coi là một phần tử; hãy phân tích sự tương thích giữa ordering và equality trong thiết kế khóa sắp xếp.
Một hệ thống giới hạn số sự kiện chưa xử lý nhưng dùng queue không giới hạn khi tốc độ vào tăng đột biến; hãy phân tích rủi ro bộ nhớ và cách chọn cấu trúc hàng đợi cho producer/consumer.
Lớp tiện ích trả về collection chỉ đọc bọc quanh danh sách nội bộ, nhưng nội dung báo cáo vẫn đổi khi tác vụ khác sửa nguồn; hãy phân tích khác biệt giữa view không cho sửa và ảnh chụp dữ liệu.
Một ứng dụng chia sẻ synchronized collection giữa nhiều thread rồi gặp dữ liệu lệch khi duyệt và cập nhật phức hợp; hãy phân tích phạm vi đồng bộ cần thiết cho cả thao tác nhiều bước.
Máy chủ nội bộ tạo một Thread mới cho mỗi yêu cầu đồng bộ và mất ổn định khi tải tăng; hãy thiết kế mô hình điều phối bằng ExecutorService dựa trên khả năng giới hạn tài nguyên.
Một dịch vụ đã ngừng nhận yêu cầu nhưng các worker của thread pool vẫn giữ tiến trình JVM sống; hãy xác định quy trình đóng pool và xử lý công việc chưa hoàn thành khi shutdown.
Dịch vụ gọi ba nhà cung cấp để định giá rồi chờ Future.get không có timeout, dẫn tới request treo vô hạn khi một bên ngừng phản hồi; hãy thiết kế cơ chế giới hạn chờ và quản trị kết quả một phần.
Một Future đã bị cancel với yêu cầu ngắt nhưng tác vụ vẫn tiếp tục xử lý I/O và ghi dữ liệu; hãy phân tích ngữ nghĩa của cancellation và cách xây nhiệm vụ hợp tác với interruption.
Tác vụ Callable ném ngoại lệ khi truy vấn dữ liệu, nhưng tầng gọi chỉ ghi nhận lỗi chung từ Future.get và mất nguyên nhân gốc; hãy thiết kế luồng xử lý và quan sát lỗi giữa thread.
Hệ thống cần trả kết quả từ nhiều dịch vụ con theo thứ tự hoàn tất để cập nhật giao diện sớm; hãy đánh giá cách phối hợp các Future khi thứ tự xong khác thứ tự gửi.
Một tác vụ nền vừa thực hiện công việc vừa cần trả thống kê về số bản ghi và số lỗi; hãy thiết kế giao diện task để nơi gọi lấy được kết quả và thông tin thất bại rõ ràng.
Nhóm vận hành không phân biệt được nguồn của stack trace từ nhiều worker cùng tên mặc định; hãy thiết kế chính sách đặt tên, bắt lỗi và quản lý luồng do Executor tạo.
Công việc đồng bộ dữ liệu được lên lịch chạy định kỳ nhưng đôi khi một lần thực hiện kéo dài hơn chu kỳ dự kiến; hãy phân tích khác biệt giữa lịch cố định và khoảng nghỉ sau lần chạy.
Thread pool dùng hàng đợi công việc không giới hạn trong khi downstream xử lý chậm, dẫn đến tăng heap và độ trễ; hãy thiết kế giới hạn tiếp nhận, hàng đợi và cách phản hồi khi quá tải.
Một hệ thống gồm producer thu thập log và consumer ghi đĩa đang dùng vòng lặp bận kiểm tra danh sách chung; hãy thiết kế phối hợp qua BlockingQueue và chính sách tạo áp lực ngược.
Hai worker cùng kiểm tra xem khóa session có trong ConcurrentHashMap chưa rồi tự thêm, dẫn đến khởi tạo trùng; hãy phân tích race giữa kiểm tra và cập nhật và xác định thao tác đồng bộ phù hợp.
Trang quản trị duyệt ConcurrentHashMap trong khi các thread khác cập nhật phiên đăng nhập, nhưng báo cáo không phải ảnh chụp nhất quán; hãy đánh giá mức nhất quán cần thiết trước khi chọn cách lấy dữ liệu.
Hệ thống đăng ký listener có rất nhiều lần phát sự kiện nhưng hiếm khi thêm hoặc gỡ listener; hãy cân nhắc CopyOnWriteArrayList và chi phí ghi/đọc khi tải thay đổi.
Hai luồng chuyển tiền cần lấy lock của nhiều tài khoản, nhưng một luồng không được phép chờ vượt quá deadline; hãy thiết kế chính sách khóa với ReentrantLock và cách xử lý khi không lấy đủ lock.
Một hàng đợi có nhiều consumer bị kẹt vì tín hiệu Condition đến trước khi thread vào trạng thái chờ; hãy thiết kế điều kiện trạng thái và vòng kiểm tra khi await/signal.
Kho dữ liệu cấu hình có hàng nghìn lượt đọc nhưng ít lần cập nhật; hãy phân tích khi nào ReadWriteLock cải thiện throughput và khi nào tranh chấp khiến lợi ích giảm.
Dịch vụ gọi API đối tác bị giới hạn chỉ cho một số request đồng thời, nhưng tác vụ lỗi đôi khi không trả permit; hãy thiết kế cơ chế cấp phát và hoàn trả Semaphore có xử lý exception.
Nhiều worker phải hoàn tất bước khởi tạo trước khi hệ thống bắt đầu nhận traffic; hãy chọn cơ chế phối hợp một lần và xác định hành vi nếu worker bị lỗi hoặc timeout.
Một bài mô phỏng chạy qua nhiều vòng tính toán, mỗi vòng chỉ được tiếp tục khi mọi thread đã hoàn thành vòng trước; hãy đánh giá cơ chế barrier tái sử dụng và xử lý trường hợp thread rời nhóm.
Bảng thống kê lượt truy cập dùng biến đếm chia sẻ với phép tăng không đồng bộ nên kết quả thiếu dưới tải lớn; hãy xây phương án kiểm chứng tính nguyên tử và thiết kế cập nhật bằng công cụ atomic phù hợp.
Một dịch vụ thay đổi trạng thái Job từ PENDING sang RUNNING bằng AtomicReference nhưng có nhiều thread cạnh tranh; hãy phân tích cách bảo đảm chuyển trạng thái hợp lệ và tránh cập nhật bị ghi đè.
Hệ thống giữ hai biến atomic cho số dư đầu và cuối trong cùng giao dịch, nhưng reader đôi lúc thấy tổng không nhất quán; hãy xác định ranh giới của tính nguyên tử khi invariant trải qua nhiều trường.
Một worker chạy nền liên tục kiểm tra cờ dừng do thread điều khiển cập nhật, nhưng không phản ứng trên một số máy; hãy phân tích yêu cầu visibility theo Java Memory Model và cách xác lập quan hệ happens-before.
Nhóm phát triển thay counter dùng synchronized bằng volatile int vì cho rằng volatile bảo đảm phép tăng nguyên tử; hãy thiết kế tình huống cạnh tranh để kiểm chứng giả định này.
Một dịch vụ tạo đối tượng cấu hình mutable rồi xuất bản tham chiếu cho các thread đọc trước khi hoàn thành khởi tạo; hãy đánh giá nguy cơ nhìn thấy trạng thái chưa đủ và xây cơ chế safe publication.
Một mô hình dữ liệu khai báo trường tham chiếu final nhưng object được tham chiếu có các collection mutable; hãy phân tích các bảo đảm của final field và ranh giới của bất biến sâu.
Một singleton sử dụng double-checked locking nhưng trường lưu instance không bảo đảm visibility; hãy phân tích thứ tự khởi tạo đối tượng và điều kiện để thiết kế này an toàn.
Một tác vụ được thread A chuẩn bị dữ liệu, submit vào Executor, rồi thread B đọc kết quả sau Future.get; hãy vẽ các quan hệ happens-before cần kiểm tra để bảo đảm dữ liệu được công bố đúng.
Hai giao dịch chuyển tiền khóa hai tài khoản theo thứ tự đảo nhau và thỉnh thoảng ngừng tiến triển; hãy xây phương pháp tái hiện deadlock và thiết kế quy ước thứ tự lấy lock.
Một tác vụ đang chờ trên BlockingQueue bị interrupt khi dịch vụ shutdown nhưng catch exception rồi tiếp tục vòng lặp; hãy đánh giá tác động đến hủy tác vụ và thiết kế chính sách xử lý tín hiệu ngắt.

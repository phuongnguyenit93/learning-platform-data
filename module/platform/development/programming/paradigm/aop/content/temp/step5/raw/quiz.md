Câu 1: Đặc trưng cốt lõi của AOP khi xây dựng ứng dụng nhiều thành phần là gì?
A. Tách mối quan tâm cắt ngang khỏi phần logic nghiệp vụ chính.
B. Chuyển mọi quy tắc nghiệp vụ sang một lớp điều phối duy nhất.
C. Thay mọi lời gọi hàm bằng các sự kiện phát không đồng bộ.
D. Buộc mỗi đối tượng phải kế thừa một lớp base aspect.
Đáp án đúng: A

Câu 2: Một hệ thống lặp lại mã ghi thời gian chạy ở nhiều dịch vụ; yếu tố nào khiến đây là ứng viên cho AOP?
A. Chỉ có một hàm xử lý cần in log khi được gọi thủ công.
B. Mỗi chức năng dùng một thuật toán độc lập không có mã chung.
C. Hành vi đo đạc lặp xuyên nhiều điểm xử lý nghiệp vụ.
D. Mỗi dịch vụ có kết quả tính toán và cấu trúc dữ liệu khác nhau.
Đáp án đúng: C

Câu 3: Trong AOP, aspect thường đại diện cho loại trách nhiệm nào?
A. Quản lý bảng dữ liệu và thực hiện mọi giao dịch lưu trữ.
B. Định nghĩa dữ liệu miền và toàn bộ vòng đời của thực thể.
C. Thay thế mọi đối tượng nghiệp vụ bằng hàm không có trạng thái.
D. Đóng gói hành vi cắt ngang cùng quy tắc chọn điểm áp dụng.
Đáp án đúng: D

Câu 4: Join point được hiểu đúng nhất trong mô hình AOP là gì?
A. Một điểm được nhận diện trong luồng thực thi của chương trình.
B. Một điều kiện Boolean luôn được viết bên trong aspect.
C. Một loại đối tượng chứa duy nhất metadata của file nguồn.
D. Một cấu hình bắt buộc chỉ tồn tại trong pipeline đóng gói.
Đáp án đúng: A

Câu 5: Pointcut khác join point ở đặc điểm nào?
A. Pointcut là đoạn xử lý bổ sung được thực thi trước hàm.
B. Pointcut là thao tác sửa bytecode để gắn logic vào mã.
C. Pointcut là lần chạy cụ thể của phương thức khi có request.
D. Tiêu chí chọn những join point cần áp dụng advice tương ứng.
Đáp án đúng: D

Câu 6: Trong mô hình lập trình hướng khía cạnh, advice có vai trò nào?
A. Cung cấp object graph của mọi dependency được khởi tạo.
B. Liệt kê toàn bộ những lớp phải biên dịch lại khi phát hành.
C. Xác định kiểu trả về của tất cả phương thức trong chương trình.
D. Cung cấp hành vi chạy tại những join point đã được chọn.
Đáp án đúng: D

Câu 7: Thuật ngữ weaving trong AOP nói đến thao tác nào?
A. Tách cơ sở dữ liệu thành nhiều phân vùng xử lý độc lập.
B. Tự chuyển mọi phương thức đồng bộ thành tác vụ async.
C. Gắn logic aspect vào những điểm thực thi cần tác động.
D. Nạp cấu hình log khi server hoàn thành giai đoạn khởi động.
Đáp án đúng: C

Câu 8: Lợi ích bảo trì nào có thể đạt được khi dùng AOP cho logging?
A. Bỏ nhu cầu kiểm thử các đường lỗi của ứng dụng đã được log.
B. Đảm bảo mọi message log đều giống nhau ở toàn bộ dự án.
C. Điều chỉnh logging tập trung mà không sửa từng service.
D. Mỗi hàm tự xây bộ log độc lập để kiểm soát thứ tự riêng.
Đáp án đúng: C

Câu 9: Nguy cơ thiết kế nào xuất hiện khi pointcut quá rộng?
A. Mọi exception nghiệp vụ tự động biến thành unchecked.
B. Advice chạy cả ở vị trí ngoài phạm vi mong muốn ban đầu.
C. Các class không liên quan tự biến thành các interface mới.
D. Các hàm được match luôn bị compiler xóa khỏi module.
Đáp án đúng: B

Câu 10: Khi nào AOP ít phù hợp hơn thao tác gọi hàm tường minh?
A. Khi xử lý nghiệp vụ cần hiện rõ từng bước trong luồng code.
B. Khi có nhiều module cùng ghi những metric theo mẫu thống nhất.
C. Khi cần thêm dấu vết thống nhất tại biên API của hệ thống.
D. Khi cùng một quy tắc audit áp dụng xuyên nhiều dịch vụ.
Đáp án đúng: A

Câu 11: Điều gì đúng khi dùng AOP để kiểm soát truy cập?
A. Đặt kiểm tra quyền trên mọi đường thực thi cần bảo vệ.
B. Ghi log hành vi bị từ chối đã đủ để chặn request trái phép.
C. Có aspect kiểm soát quyền thì không cần kiểm thử đường gọi khác.
D. Một pointcut khớp vài hàm có nghĩa toàn hệ thống đã được bảo vệ.
Đáp án đúng: A

Câu 12: Một ứng dụng có metric, audit và logic đặt hàng; cách tổ chức nào phản ánh AOP?
A. Yêu cầu mọi lớp đặt hàng gọi trực tiếp mọi advice theo thứ tự.
B. Giữ đặt hàng ở service; đưa audit và metric sang aspect.
C. Đưa cả nghiệp vụ đặt hàng và truy cập dữ liệu vào một advice.
D. Biến entity đơn hàng thành pointcut để thay thế toàn bộ service.
Đáp án đúng: B

Câu 13: Trong cơ chế AOP hỗ trợ method execution join point, điểm nào được chọn?
A. Chỉ lúc caller tạo tham chiếu tới phương thức trong source.
B. Việc thực thi thân phương thức phù hợp điều kiện pointcut.
C. Lúc JVM nạp file class mà phương thức đó được khai báo.
D. Lúc compiler suy ra kiểu của tham số mà không gọi phương thức.
Đáp án đúng: B

Câu 14: Khi so method call với method execution join point, khác biệt quan trọng là gì?
A. Call nằm tại vị trí gọi; execution nằm nơi thân hàm được chạy.
B. Call luôn match constructor; execution chỉ match việc đọc field.
C. Call chọn đối tượng trả về; execution chọn biến cục bộ của caller.
D. Call chỉ có ở lúc nạp class; execution chỉ có ở lúc biên dịch.
Đáp án đúng: A

Câu 15: Hai overload cùng tên nhưng khác kiểu tham số cần được chọn riêng; pointcut nên xét gì?
A. Xét cả chữ ký method và kiểu tham số được khai báo.
B. Số lần lời gọi xuất hiện trong từng phương thức caller.
C. Tên lớp của đối tượng trả về sau khi phương thức chạy xong.
D. Nội dung comment ở đầu khai báo của các overload đó.
Đáp án đúng: A

Câu 16: Một pointcut chọn mọi method trong package bằng wildcard gặp thay đổi gì khi thêm class?
A. Wildcard cố định danh sách class từ lần chạy test đầu tiên.
B. Class mới luôn được loại trừ cho đến khi gọi explicit import.
C. Wildcard chỉ chọn những method có tên xuất hiện trong aspect.
D. Class mới hợp mẫu có thể bị advice lựa chọn thêm.
Đáp án đúng: D

Câu 17: Trong cơ chế AOP hỗ trợ annotation pointcut, cách chọn nào ít phụ thuộc tên hàm?
A. Match các join point gắn annotation nghiệp vụ đã định nghĩa.
B. Match theo thứ tự khai báo method trong nguồn Java hiện hành.
C. Match mọi lời gọi tạo một String có cùng nội dung.
D. Match tất cả class có tên file dài hơn một giới hạn cố định.
Đáp án đúng: A

Câu 18: Nếu pointcut có điều kiện xét giá trị tham số lúc chạy, điều gì cần lưu ý?
A. Một khi match đúng thì không thể trở lại false ở lần gọi mới.
B. Kết quả match có thể khác theo đối số ở từng lần gọi.
C. Kết quả match chỉ được quyết định một lần lúc biên dịch source.
D. Pointcut sẽ bỏ mọi kiểm tra kiểu để tăng tốc khi runtime chạy.
Đáp án đúng: B

Câu 19: Một advice cần biết tham số được truyền tới method vừa match; khả năng nào phù hợp?
A. Pointcut tự sửa mọi tham số thành một object dùng chung cho advice.
B. Advice chỉ nhận thông tin class name, không có ngữ cảnh lời gọi.
C. Cơ chế weaving luôn ghi tham số vào một file log trung gian.
D. Binding ngữ cảnh join point cho phép đọc đối số theo hợp đồng.
Đáp án đúng: D

Câu 20: Với pointcut dựa trên control flow, khi nào một join point có thể được chọn?
A. Khi file .class của hàm được biên dịch cùng một máy tính.
B. Chỉ khi lời gọi nằm cùng thư mục nguồn với aspect.
C. Chỉ khi tên phương thức giống hệt tên class của người gọi.
D. Khi lời gọi thuộc control flow đang được pointcut quan tâm.
Đáp án đúng: D

Câu 21: Trong cơ chế có static và dynamic pointcut checks, khác biệt nào đúng?
A. Static không có điều kiện; dynamic buộc phải đổi classpath.
B. Static chỉ áp dụng cho constructor; dynamic chỉ áp dụng cho field.
C. Static dựa metadata ổn định; dynamic có thể xét ngữ cảnh lúc chạy.
D. Static luôn dùng reflection; dynamic chỉ hoạt động khi build offline.
Đáp án đúng: C

Câu 22: Muốn loại các lớp nội bộ của bộ ghi log khỏi pointcut logging, cần mục tiêu gì?
A. Buộc tất cả class ghi log thành sealed type để tăng tốc.
B. Thay mọi lỗi logging bằng lỗi cấu hình tại lúc build.
C. Giảm số phương thức nghiệp vụ bằng cách gộp package.
D. Tránh match method dùng để ghi log ngay trong advice.
Đáp án đúng: D

Câu 23: Khi advice không chạy dù pointcut đã khai báo, kiểm tra nào nên thực hiện trước?
A. Chỉ đổi tên biến cục bộ trong hàm được instrument.
B. Thay đổi kiểu dữ liệu trả về để compiler sinh bytecode khác.
C. Tăng dung lượng heap vì pointcut luôn cần thêm bộ nhớ.
D. Kiểm tra join point có được hỗ trợ và thực sự match.
Đáp án đúng: D

Câu 24: Khi triển khai pointcut theo tên method, thay đổi refactor nào dễ làm phạm vi match lệch?
A. Đổi tên method hoặc package có thể làm mẫu match không còn đúng.
B. Thêm một dòng trắng trước method sẽ thay đổi kết quả pointcut.
C. Sắp xếp lại các comment trong cùng file có thể đổi runtime match.
D. Đổi tên tham số local luôn làm method execution bị loại.
Đáp án đúng: A

Câu 25: Một before advice nên chạy ở thời điểm nào so với join point được chọn?
A. Trước khi phần thực thi chính của join point được bắt đầu.
B. Sau khi phương thức đã hoàn tất và trả về giá trị bình thường.
C. Chỉ khi phương thức ném ngoại lệ ra caller của nó.
D. Sau khi toàn bộ lời gọi lồng nhau của request kết thúc.
Đáp án đúng: A

Câu 26: After-returning advice trong AOP thường gắn với tình huống nào?
A. Join point còn chưa bắt đầu thực hiện logic nghiệp vụ.
B. Join point được định nghĩa trong class nhưng chưa từng chạy.
C. Join point ném exception không được xử lý ở tầng gọi.
D. Join point hoàn thành bình thường và có kết quả thành công.
Đáp án đúng: D

Câu 27: After-throwing advice phù hợp để xử lý thời điểm nào?
A. Khi caller khai báo throws nhưng chưa xuất hiện lỗi.
B. Khi method trả về bình thường nhưng giá trị là null.
C. Khi join point kết thúc bằng ngoại lệ phát ra bên ngoài.
D. Khi class được nạp vào JVM trước lời gọi đầu tiên.
Đáp án đúng: C

Câu 28: Loại advice nào có ý nghĩa chạy cả khi join point trả về và khi ném lỗi?
A. After-returning advice tự bao gồm cả các trường hợp ném lỗi.
B. Before advice luôn chạy lại sau khi method trả về.
C. After-finally chạy khi method trả về hoặc ném ngoại lệ.
D. After-throwing advice chạy cho mọi phương thức thành công.
Đáp án đúng: C

Câu 29: Around advice khác before advice ở quyền điều khiển nào?
A. Chỉ có thể chạy sau phương thức không có giá trị trả về.
B. Tự động bỏ qua mọi tham số của lời gọi đã được match.
C. Chỉ có thể đọc tên method mà không biết kết quả gọi.
D. Around có thể quyết định gọi tiếp join point hay không.
Đáp án đúng: D

Câu 30: Khi around advice không gọi proceed trong mô hình hỗ trợ proceed, điều gì có thể xảy ra?
A. Thao tác gốc chỉ bị hoãn đến khi garbage collector chạy.
B. Thao tác gốc có thể không được thực hiện ở lần gọi đó.
C. Thao tác gốc bắt buộc chạy vì around không đổi luồng xử lý.
D. Thao tác gốc sẽ tự chạy hai lần khi advice kết thúc.
Đáp án đúng: B

Câu 31: Một around advice gọi proceed hai lần cho thao tác trừ tiền; rủi ro nào cần đánh giá?
A. Hai lời proceed luôn tự gộp thành đúng một giao dịch thực.
B. Lời proceed thứ hai chỉ chạy logging mà không chạy nghiệp vụ.
C. Logic trừ tiền có thể được thực thi lặp lại ngoài ý muốn.
D. Weaver luôn từ chối mọi around advice có hơn một proceed.
Đáp án đúng: C

Câu 32: Around advice cần giữ kết quả của phương thức có giá trị trả về; nguyên tắc nào đúng?
A. Kiểu trả về được thay thành void khi có around advice.
B. Advice phải trả null cho mọi method có kiểu tham chiếu.
C. Kết quả trả về phải phù hợp kiểu và hợp đồng của join point.
D. Advice có thể trả bất kỳ kiểu nào rồi JVM tự đổi về kiểu gốc.
Đáp án đúng: C

Câu 33: Một quanh-advice đo độ trễ cả khi hàm ném exception; cấu trúc nào đáng tin cậy?
A. Dùng finally để đo kết thúc ngay cả khi lời gọi có lỗi.
B. Bỏ việc propagate exception để bộ đo luôn kết thúc.
C. Chỉ ghi thời gian sau lệnh proceed thành công.
D. Chỉ đặt bộ đo trong before advice trước khi gọi hàm.
Đáp án đúng: A

Câu 34: Nếu before advice từ chối quyền bằng cách ném lỗi, kết quả thông thường là gì?
A. Ném lỗi trong before có thể ngăn join point được chạy.
B. Lỗi chỉ được ghi log, còn hàm gốc luôn tiếp tục bình thường.
C. Lỗi tự được chuyển thành giá trị trả về rỗng cho caller.
D. Tất cả các advice khác đều bị xóa khỏi cấu hình weaving.
Đáp án đúng: A

Câu 35: Khi advice bắt exception rồi trả kết quả giả thành công, nguy cơ nào tăng?
A. Mọi phương thức được match tự đổi thành asynchronous.
B. Pointcut sẽ không match nữa ở các lần gọi về sau.
C. Caller có thể hiểu sai trạng thái thất bại thành hoàn tất.
D. Compiler bắt buộc phát hiện và hủy build trong mọi trường hợp.
Đáp án đúng: C

Câu 36: Một after-returning advice cần truy cập kết quả lời gọi; kỹ thuật nào phù hợp?
A. Gọi lại method đã hoàn tất để lấy kết quả như ban đầu.
B. Binding giá trị trả về nếu hệ thống AOP có hỗ trợ.
C. Đọc giá trị trả về từ biến cục bộ tùy ý của caller.
D. Sửa chữ ký của tất cả method được match thành Object.
Đáp án đúng: B

Câu 37: Compile-time weaving áp dụng khía cạnh ở giai đoạn nào?
A. Khi proxy chuyển tiếp mọi lời gọi sau lúc service chạy.
B. Khi người dùng nhấn nút gọi một chức năng bất kỳ.
C. Khi biên dịch mã thành artifact đã chứa logic aspect.
D. Khi thread pool được JVM tạo lần đầu ở runtime.
Đáp án đúng: C

Câu 38: Post-compile weaving tác động lên loại đầu vào nào?
A. Chỉ object đã khởi tạo và đang nằm trên heap.
B. Chỉ HTTP request khi nó đi qua bộ chuyển tiếp.
C. Thay đổi bytecode đã compile, trước khi artifact chạy.
D. Chỉ các dòng comment trong file source code gốc.
Đáp án đúng: C

Câu 39: Load-time weaving thường cần khả năng nào từ môi trường chạy?
A. Buộc compiler chạy lại trước từng lần tạo object.
B. Sửa mọi source file mỗi lần người dùng gọi method.
C. Tái biên dịch dự án ngay sau mỗi lần thực thi advice.
D. Can thiệp vào định nghĩa lớp khi JVM đang nạp class.
Đáp án đúng: D

Câu 40: Với dynamic proxy AOP, join point thường bị giới hạn ở đâu?
A. Mọi phép truy cập field private bên trong object gốc.
B. Mọi constructor của thư viện JDK được chạy trong chương trình.
C. Mọi instruction trong method body không đi qua proxy.
D. Các lời gọi đi qua proxy và bề mặt intercept được nó hỗ trợ.
Đáp án đúng: D

Câu 41: Trong thiết kế proxy-based AOP, lời gọi nội bộ qua this có thể gặp gì?
A. Bắt buộc gọi before advice hai lần trước method nội bộ.
B. Bỏ qua advice vì lời gọi không đi qua proxy bên ngoài.
C. Luôn kích hoạt load-time weaving dù không cấu hình.
D. Tự động tạo proxy thứ hai cho mỗi method được gọi.
Đáp án đúng: B

Câu 42: Một proxy dựa trên interface cần chặn method không xuất hiện trên interface; hạn chế nào đúng?
A. Interface proxy sẽ tự sửa bytecode class đích khi chạy.
B. Lời gọi qua this có thể bỏ qua proxy và advice.
C. Method tự được thêm vào interface ngay khi proxy được tạo.
D. Proxy vẫn luôn chặn mọi private method bên trong class.
Đáp án đúng: B

Câu 43: Vì sao bytecode weaving có thể quan sát điểm mà proxy thông thường bỏ lỡ?
A. Bytecode weaving buộc mọi lời gọi chạy qua remote service.
B. Bytecode weaving chỉ đổi đối tượng đứng trước method call.
C. Bytecode weaving tự mở toàn bộ private API của mọi module.
D. Method ngoài interface không thuộc bề mặt interface proxy.
Đáp án đúng: D

Câu 44: Sau khi thêm weaving, framework gặp VerifyError khi nạp class; nên xem gì?
A. Thời điểm ghi log của before advice có đúng locale.
B. Số lượng source imports của lớp đích có thay đổi.
C. Weaver chèn bytecode tại những join point được hỗ trợ.
D. Tên file README đi kèm artifact có khác bản cũ.
Đáp án đúng: C

Câu 45: Một ứng dụng có nhiều class loader dùng load-time weaving; điểm nào cần kiểm chứng?
A. Kiểm tra tính hợp lệ của bytecode và stack metadata.
B. Mọi class được load đều có cùng tên và cùng module.
C. Weaver chỉ cần chạy ở loader đầu tiên là đủ cho mọi lớp.
D. Mọi loader tự dùng chung một định nghĩa class đã woven.
Đáp án đúng: A

Câu 46: Nếu bản build woven không tái lập giữa CI và máy dev, cần so yếu tố nào?
A. Chỉ tên người chạy build và số dòng tài liệu README.
B. Chỉ kích thước bộ nhớ heap khi compiler chạy.
C. Chỉ thời điểm user cuối cùng đăng nhập ứng dụng.
D. Xác minh weaving áp dụng đúng tới từng class loader.
Đáp án đúng: D

Câu 47: Khi hai aspect cùng chọn một join point, điều nào quyết định thứ tự đáng tin cậy?
A. Thứ tự các file được liệt kê trong thư mục source.
B. So input, cấu hình weaving và phiên bản weaver giữa hai build.
C. Số lượng tham số của method quyết định toàn bộ ưu tiên.
D. Thứ tự ngẫu nhiên của object trên heap khi JVM chạy.
Đáp án đúng: B

Câu 48: Với hai around advice lồng nhau, đặc điểm nào nên quan sát khi đổi precedence?
A. Advice ở trong tự gọi tiếp trước khi advice ngoài bắt đầu.
B. Dựa vào quy tắc precedence mà cơ chế AOP đã xác minh.
C. Precedence chỉ đổi thứ tự log, không đổi phạm vi thực thi.
D. Mọi around advice luôn chạy song song không lồng nhau.
Đáp án đúng: B

Câu 49: Một aspect retry nằm ngoài transaction aspect; ranh giới transaction dễ bị ảnh hưởng thế nào?
A. Mỗi lần retry có thể tạo một transaction độc lập.
B. Một transaction luôn bao trùm mọi lần retry bất kể precedence.
C. Thứ tự aspect chỉ tác động câu log, không ảnh hưởng transaction.
D. Transaction tự được commit khi pointcut match trước khi gọi.
Đáp án đúng: A

Câu 50: Khi dùng caching và authorization aspects, vì sao thứ tự can thiệp cần thiết?
A. Caching làm mọi kết quả trở thành dữ liệu công khai mặc định.
B. Cache hit không được vượt qua bước kiểm tra quyền.
C. Mọi lời gọi cache đều phát sinh cùng context xác thực.
D. Authorization chỉ kiểm tra trong giai đoạn biên dịch ra bytecode.
Đáp án đúng: B

Câu 51: Hai aspect A và B đều có around advice; nếu A bao B, thứ tự nào có thể đúng?
A. Cả hai advice chạy hết trước khi target được bắt đầu.
B. Phần sau của A luôn chạy trước phần trước của B.
C. A chạy phần trước B; phần sau A chạy sau B.
D. A và B phải chạy trên hai platform threads khác nhau.
Đáp án đúng: C

Câu 52: Một cơ chế AOP hỗ trợ introductions hoặc inter-type declarations có thể làm gì?
A. Chỉ gắn log tĩnh vào một cấu hình runtime không có class.
B. Thay đổi toàn bộ lược đồ cơ sở dữ liệu khi application chạy.
C. Tự động làm mọi class trở thành superclass của aspect.
D. Có thể bổ sung interface hoặc thành viên cho kiểu đích.
Đáp án đúng: D

Câu 53: Trong cơ chế hỗ trợ aspect per-target instance, hệ quả nào có thể có?
A. State aspect có thể gắn với từng đối tượng target riêng.
B. Mỗi method call sẽ tự tạo một class loader hoàn toàn mới.
C. State của aspect chỉ tồn tại trong lúc JVM compile source.
D. Mọi join point buộc chia sẻ đúng một state global.
Đáp án đúng: A

Câu 54: Một singleton aspect lưu requestId vào field mutable khi xử lý request song song; rủi ro gì?
A. Field sẽ tự chuyển thành ThreadLocal ở lần gọi đầu.
B. Singleton bảo đảm mỗi request có một bản sao của field.
C. Request song song có thể ghi đè state dùng chung.
D. Weaver tự khóa toàn bộ field ngay khi aspect được tạo.
Đáp án đúng: C

Câu 55: Một logging advice tự match cả method nội bộ ghi log, lỗi nào có thể phát sinh?
A. Pointcut tự động bỏ method được gọi trong mọi advice.
B. Aspect chắc chắn chỉ được chạy một lần cho mỗi JVM.
C. Advice có thể tái nhập hoặc gọi lặp gây vòng đệ quy.
D. Runtime tự xóa lời gọi thứ hai khi phát hiện cùng aspect.
Đáp án đúng: C

Câu 56: Một around advice chỉ đo lúc method trả về Future, nhưng task hoàn tất sau đó; kết quả là gì?
A. Around advice tự động chờ Future bằng cơ chế weaving.
B. Thời gian đo có thể chưa bao gồm lúc task thực sự hoàn tất.
C. Method trả Future luôn có cùng thời gian với task đã chạy.
D. Mọi Future bắt buộc hoàn tất trước khi method trả về.
Đáp án đúng: B

Câu 57: Một aspect lưu context trong ThreadLocal cho thread pool; thiếu cleanup gây hệ quả gì?
A. Thread tái dùng có thể thấy context từ request trước.
B. Weaver tự đưa context sang mọi luồng bất đồng bộ liên quan.
C. ThreadLocal tự xóa ngay khi method bất kỳ kết thúc.
D. Mỗi lần pointcut match đều tạo thread không thể tái dùng.
Đáp án đúng: A

Câu 58: Một pointcut chỉ match HTTP handler nhưng công việc batch cũng gọi nghiệp vụ nhạy cảm; nguy cơ gì?
A. Weaver tự mở rộng mọi pointcut tới các entrypoint mới.
B. Batch task mặc định luôn đi qua interceptor dành cho HTTP.
C. Nếu một handler đã được bảo vệ thì mọi helper đều được bảo vệ.
D. Batch có thể không đi qua pointcut kiểm soát quyền.
Đáp án đúng: D

Câu 59: Hai aspects có logic gọi lẫn nhau qua các method được match; vấn đề nào nên kiểm tra?
A. Precedence tự xóa hẳn một aspect để tránh vòng lặp.
B. Mỗi aspect chỉ được phép gọi đúng một method đích.
C. Có thể tái nhập advice và sinh vòng gọi không kết thúc.
D. Pointcut tự phát hiện mọi chu trình gọi và bỏ qua chúng.
Đáp án đúng: C

Câu 60: Một aspect đo metric chạy ở phương thức được gọi hàng triệu lần; rủi ro nào cần đo?
A. Cần đo overhead advice trên đường thực thi tần suất cao.
B. Pointcut chỉ chạy một lần nên không ảnh hưởng latency.
C. Weaving luôn loại mọi overhead của lời gọi bổ sung.
D. Metric luôn được JVM gộp theo method để tránh cấp phát.
Đáp án đúng: A

Câu 61: Để kiểm thử pointcut chỉ chọn đúng API công khai, ca nào cần có?
A. Chỉ method chắc chắn match và chạy đúng một lần.
B. Thử cả method được chọn và method lân cận không được chọn.
C. Chỉ kiểm tra rằng source của aspect đã biên dịch xong.
D. Chỉ xem tên pointcut có đúng quy ước đặt tên không.
Đáp án đúng: B

Câu 62: Unit test gọi trực tiếp target thay vì qua proxy rồi không thấy advice; cần lưu ý gì?
A. Pointcut tự mở rộng khi chạy trong unit test runner.
B. Test gọi target trực tiếp có thể đã bỏ qua proxy.
C. Target trực tiếp luôn kích hoạt mọi advice như proxy.
D. Weaver bắt buộc ném lỗi nếu test gọi object thật.
Đáp án đúng: B

Câu 63: Một bài kiểm thử chỉ xác nhận business result dù yêu cầu audit aspect; thiếu gì?
A. Cần xác nhận event audit phát khi advice thực sự chạy.
B. Chỉ tăng timeout để mọi lời gọi test chắc chắn kết thúc.
C. Chỉ đối chiếu tên class test với tên aspect được tạo.
D. Chỉ kiểm tra JAR có chứa các file source của aspect.
Đáp án đúng: A

Câu 64: Khi thử after-throwing advice, đường kiểm tra quan trọng nào cần có?
A. Chỉ tạo exception object nhưng không ném khi method chạy.
B. Chỉ kiểm tra phương thức trả về một giá trị hợp lệ.
C. Chỉ đổi tên exception class trong test mà không chạy target.
D. Cho method ném exception và xác nhận advice nhận lỗi.
Đáp án đúng: D

Câu 65: Một after-finally advice cần thu hồi tài nguyên khi target thất bại; nên kiểm tra gì?
A. Chỉ kiểm tra giá trị truyền vào của một method chưa gọi.
B. Kiểm tra dọn tài nguyên khi thành công và khi có lỗi.
C. Chỉ xem số dòng code trong phần thân của aspect.
D. Chỉ chạy đường trả về thành công để xác nhận advice match.
Đáp án đúng: B

Câu 66: Để biết weaving có thực sự xảy ra ở production artifact, kiểm chứng nào phù hợp?
A. Chạy artifact thật và kiểm chứng advice được thực thi.
B. Chỉ so kích thước JAR trước và sau khi thêm pointcut.
C. Chỉ thấy file aspect trong repository mà coi đã woven.
D. Chỉ bật logging compiler khi chưa chạy binary phát hành.
Đáp án đúng: A

Câu 67: Khi đánh giá overhead của AOP, cách benchmark nào đáng tin cậy?
A. Chỉ so một lời gọi khi JVM chưa warm up ở máy phát triển.
B. Đo workload tương đương qua nhiều lượt, có và không aspect.
C. Chỉ đếm số pointcut trong source rồi suy ra latency.
D. Chỉ đo startup và xem nó bằng throughput ổn định.
Đáp án đúng: B

Câu 68: Một pointcut logging vô tình ghi token xác thực trong arguments; hướng kiểm thử nào đúng?
A. Chỉ kiểm tra advice đã match đủ bốn tham số đầu vào.
B. Chỉ nâng mức log để bỏ việc kiểm soát dữ liệu nhạy cảm.
C. Kiểm tra log không lộ secret ở nhánh lỗi và thành công.
D. Chỉ kiểm tra log có tên method và timestamp dễ đọc.
Đáp án đúng: C

Câu 69: Trong hệ thống dùng AOP cho kiểm soát quyền, ca hồi quy nào đặc biệt quan trọng?
A. Chỉ kiểm tra kiểu trả về của một method không có quyền.
B. Chỉ kiểm tra một method đã được advice match từ trước.
C. Chỉ kiểm tra logging của chính aspect khi khởi động.
D. Thử đường gọi không qua proxy hoặc không match pointcut.
Đáp án đúng: D

Câu 70: Một refactor đổi package của service; cần test pointcut kiểu tên như thế nào?
A. Chỉ kiểm tra số lượng import trong source có giảm không.
B. Kiểm tra tập join point match sau khi đổi tên package.
C. Chỉ chạy test hiển thị thông báo startup của ứng dụng.
D. Chỉ kiểm tra class metadata trước khi chạy một method.
Đáp án đúng: B

Câu 71: Khi kiểm tra thứ tự hai around advice, cách xác minh nào chính xác?
A. Chỉ đo số object đã tạo trong heap trước khi gọi.
B. Ghi thứ tự các sự kiện trước và sau proceed.
C. Chỉ suy từ thứ tự file source khi compiler duyệt JAR.
D. Chỉ xem các aspect có cùng tên package hay không.
Đáp án đúng: B

Câu 72: Khi một aspect vô tình đếm metric hai lần vì retry, giải pháp kiểm chứng nào phù hợp?
A. Chỉ quan sát kết quả của một request không có retry.
B. Chỉ xác nhận method gốc đã trả về đúng dữ liệu.
C. Đối chiếu số lần ghi metric theo request và mỗi retry.
D. Chỉ so kích thước class file trước và sau weaving.
Đáp án đúng: C

Một dịch vụ Java tăng CPU đột ngột vào giờ cao điểm nhưng biểu đồ chỉ hiển thị mức sử dụng trung bình năm phút, khiến nhóm vận hành không biết luồng nào tiêu thụ tài nguyên; hãy xây dựng tình huống thu thập bằng chứng đúng thời điểm.
Một tiến trình JVM chạy trong Kubernetes liên tục bị restart trước khi đội vận hành kịp truy cập, trong khi hệ thống chỉ lưu log ứng dụng sau khởi động; hãy đặt bài toán bảo toàn dữ liệu chẩn đoán của lần chạy lỗi.
Một tổ chức triển khai nhiều phiên bản Java trên cùng máy chủ và đội hỗ trợ dùng nhầm PID khi thu thập thông tin JVM, dẫn tới phân tích dữ liệu của service khác; hãy xây dựng tình huống xác minh danh tính tiến trình.
Một dịch vụ thanh toán chạy bằng tài khoản hệ thống riêng và công cụ jcmd của kỹ sư không thể gắn vào tiến trình dù PID đã đúng; hãy đặt tình huống đánh giá điều kiện quyền truy cập và môi trường.
Một ứng dụng chạy trong container nhưng lệnh jcmd được thực hiện từ host hiển thị PID khác với PID trong container, khiến thao tác chẩn đoán thất bại; hãy xây dựng tình huống kiểm chứng không gian định danh tiến trình.
Một image runtime Java tối giản không có jcmd trong lúc production xảy ra sự cố, còn đội phát triển chỉ từng chẩn đoán trên máy có đầy đủ JDK; hãy đặt bài toán đánh giá khả năng thu thập bằng chứng.
Một đội vận hành bật khả năng attach động trong môi trường thử nghiệm nhưng vô hiệu hóa trong production, khiến quy trình thu thập dữ liệu đang chạy không thể áp dụng; hãy xây dựng tình huống kiểm tra ranh giới chẩn đoán.
Một service đang quá tải và đội hỗ trợ muốn lấy đồng thời heap dump, thread dump và JFR mà chưa đánh giá tác động tới độ trễ nghiệp vụ; hãy đặt bài toán ưu tiên phép đo theo rủi ro.
Một ứng dụng Java sau khi nâng JDK trả kết quả jcmd khác trước và script vận hành không còn phân tích được thông tin VM flags; hãy xây dựng tình huống kiểm chứng tính tương thích công cụ.
Một ứng dụng chạy trên node Linux bị giới hạn quyền ptrace và namespace, khiến công cụ phân tích tiến trình không truy cập được dù tài khoản có quyền vào Pod; hãy đặt tình huống phân biệt giới hạn hệ điều hành và JVM.
Một quy trình ứng cứu chọn nhầm thời điểm lấy thread dump sau khi toàn bộ request đã timeout, khiến các luồng gây tắc đã biến mất; hãy xây dựng tình huống xác định thời điểm thu thập dữ liệu.
Một nhóm điều tra sự cố kéo dài nhiều giờ nhưng chỉ lưu một ảnh chụp trạng thái JVM, khiến không thể phân biệt vấn đề nhất thời với xu hướng tăng dần; hãy đặt tình huống xây dựng chuỗi bằng chứng.
Một ứng dụng được giám sát bằng metric JVM tổng quát nhưng không lưu ID bản deploy, phiên bản JDK hoặc cấu hình GC đi kèm thời điểm lỗi; hãy xây dựng tình huống đảm bảo khả năng đối chiếu.
Một đội vận hành thấy CPU sử dụng cao sau release nhưng không biết là CPU của thread ứng dụng, collector hay compiler thread; hãy đặt tình huống thu thập dữ liệu đủ để phân loại nguồn tải.
Một công cụ tự động định kỳ lấy thông tin jcmd từ mọi service nhưng gây thêm độ trễ cho các JVM có heap lớn, khiến chi phí quan sát tăng khi mở rộng hệ thống; hãy xây dựng tình huống đánh giá tác động.
Một ứng dụng dùng JDK phân phối khác với JDK cài trên máy chẩn đoán, khiến thao tác thu thập dữ liệu báo không tương thích; hãy đặt tình huống kiểm chứng lựa chọn công cụ theo runtime.
Một dịch vụ đã bị kill do hết bộ nhớ container và không còn tiến trình để attach, nhưng nhóm vẫn cố chạy lệnh chẩn đoán như khi JVM sống; hãy đặt bài toán tìm nguồn chứng cứ còn khả dụng.
Một công ty yêu cầu lưu bằng chứng sự cố JVM tối thiểu trong bảy ngày, nhưng các Pod ephemeral xóa toàn bộ file dump khi bị thay thế; hãy xây dựng tình huống kiểm tra vòng đời artifact.
Một kỹ sư bật verbose logging toàn hệ thống ngay trong giờ cao điểm để tìm nghẽn CPU, khiến lượng I/O và chi phí ghi log tăng đột biến; hãy đặt tình huống đánh giá phương pháp quan sát.
Một tập đoàn có hai tenant dùng chung cluster, nhưng công cụ vận hành cho phép người hỗ trợ tải heap dump của cả service không thuộc phạm vi quyền; hãy đặt tình huống kiểm chứng kiểm soát truy cập vào dữ liệu chẩn đoán.
Một ứng dụng có nhiều process Java giống tên nhau và chạy trên cùng máy, khiến script tìm PID theo tên tiến trình có thể thu thập nhầm báo cáo; hãy đặt tình huống kiểm tra xác định process đích.
Một hệ thống chỉ cho phép điều tra sự cố qua API quản trị nội bộ nhưng kết quả jcmd chứa thông tin môi trường nhạy cảm có thể được trả nguyên văn; hãy xây dựng tình huống đánh giá dữ liệu được phép công bố.
Một dịch vụ tăng CPU theo chu kỳ nhưng thread dump thu thập được cho thấy nhiều thread ở trạng thái RUNNABLE mà không rõ thread nào thực sự tiêu thụ CPU; hãy xây dựng tình huống kết hợp các loại bằng chứng.
Một ứng dụng ghi nhận một CPU core bị sử dụng gần tối đa trong khi tổng CPU của máy chỉ ở mức thấp, khiến đội vận hành cho rằng không có nút nghẽn; hãy đặt tình huống đánh giá thước đo theo lõi.
Một nhóm quan sát thread có stack trace cố định ở cùng đoạn mã trong nhiều lần lấy dump, nhưng chưa biết đó là vòng lặp CPU hay chờ I/O; hãy xây dựng tình huống xác minh hành vi thực thi.
Một service Java chạy vòng lặp xử lý retry khi backend trả lỗi, khiến CPU tăng và log lỗi liên tục trong khi số request thành công giảm; hãy đặt tình huống phân biệt nguyên nhân ứng dụng với hành vi JVM.
Một API sử dụng thuật toán nén CPU-intensive và độ trễ tăng khi nhiều người đồng thời tải file, nhưng GC log không cho thấy pause đáng kể; hãy xây dựng tình huống lựa chọn bằng chứng về CPU.
Một ứng dụng mở tính năng mã hóa mới và JFR ghi nhận nhiều sự kiện CPU sampling ở thư viện mật mã, nhưng đội vận hành vẫn nghi ngờ kết nối database; hãy đặt tình huống kiểm chứng giả thuyết bằng dữ liệu.
Một tiến trình JVM chạy trên node có CPU quota thấp và liên tục bị throttling, nhưng thread dump không cho thấy deadlock hay thread BLOCKED; hãy đặt tình huống phân biệt scheduler hệ điều hành với tranh chấp khóa.
Một ứng dụng có CPU thấp trong lúc request latency rất cao, khiến nhóm phát triển kết luận backend đang rảnh mà chưa xem xét thread chờ khóa hoặc I/O; hãy xây dựng tình huống điều tra nguyên nhân tắc nghẽn.
Một dịch vụ mới tăng số worker nhưng thông lượng không tăng và CPU ở mức cao, trong khi profiler cho thấy nhiều luồng cùng chạy một method đồng bộ; hãy đặt bài toán đánh giá lock contention.
Một service bị chiếm CPU bởi công việc background sau mỗi lần refresh cache, nhưng dữ liệu đo chỉ có trung bình theo process chứ không có nhãn tác vụ; hãy xây dựng tình huống thu thập bằng chứng theo luồng.
Một đợt deploy bổ sung Java agent tracing làm CPU tăng 30 phần trăm, nhưng nhóm chỉ so sánh response latency mà không đối chiếu overhead của agent; hãy đặt tình huống đánh giá hiệu năng chẩn đoán.
Một ứng dụng có nhiều phương thức được JIT biên dịch trong vài phút đầu và CPU cao sau restart, khiến cảnh báo lầm tưởng là vòng lặp vô hạn; hãy đặt tình huống phân biệt warmup với sự cố thực.
Một batch job dùng parallel stream chiếm common pool khiến API phục vụ người dùng chậm dù hệ thống không có lỗi GC; hãy đặt bài toán tìm bằng chứng về cạnh tranh CPU.
Một profiler CPU sampling chỉ chạy vài giây đúng lúc ứng dụng ít tải, trong khi lỗi CPU cao xảy ra sau batch lúc nửa đêm; hãy xây dựng tình huống xác định thời gian ghi mẫu.
Một ứng dụng được tối ưu dựa trên flame graph từ staging nhưng workload production có cấu trúc dữ liệu khác và vẫn chậm; hãy đặt tình huống đánh giá tính đại diện của profile.
Một hệ thống có mã native thông qua JNI chiếm nhiều CPU, nhưng báo cáo Java method sampling không xác định được khối lượng chạy ngoài JVM; hãy xây dựng tình huống kiểm chứng giới hạn công cụ.
Một dịch vụ có tỷ lệ CPU system tăng cao khi xử lý hàng nghìn kết nối mạng, trong khi Java method profile chủ yếu cho thấy luồng chờ; hãy đặt tình huống điều tra chi phí kernel và syscall.
Một ứng dụng liên tục tạo exception để điều khiển luồng xử lý khi dữ liệu sai, làm tăng CPU ở thời gian cao điểm; hãy đặt bài toán đối chiếu stack trace, sự kiện exception và chi phí thực thi.
Một nhóm tối ưu dựa trên một hot method trong JFR nhưng không kiểm soát phiên bản JDK, cấu hình profiler và khoảng thời gian thu mẫu; hãy xây dựng tình huống kiểm chứng độ tin cậy kết luận.
Một dịch vụ xử lý khoảng một nghìn giao dịch mỗi giây nhưng đội vận hành chỉ có CPU sử dụng tổng hợp, khiến khó nhận biết thao tác nghiệp vụ có chi phí tăng theo thời gian; hãy đặt tình huống thiết kế chỉ số kết hợp.
Một ứng dụng bị nghẽn khi nhiều request truy cập vùng synchronized duy nhất, khiến số thread BLOCKED tăng mạnh trong thread dump; hãy xây dựng tình huống xác định đối tượng khóa và chủ sở hữu.
Một hệ thống quản lý giao dịch có hai luồng giữ khóa theo thứ tự ngược nhau, khiến request không hoàn tất và JVM vẫn sử dụng CPU thấp; hãy đặt tình huống thu thập bằng chứng deadlock.
Một nhóm lấy thread dump sau khi phát hiện timeout nhưng chỉ tìm từ khóa deadlock tự động, trong khi nhiều luồng bị kẹt vì chờ một lock do công việc dài chiếm giữ; hãy xây dựng tình huống phân tích ngoài deadlock cổ điển.
Một thread dump cho thấy nhiều worker WAITING tại hàng đợi tác vụ và một số worker RUNNABLE, nhưng nhóm kết luận toàn bộ hệ thống đang bị treo; hãy đặt tình huống diễn giải trạng thái luồng trong ngữ cảnh.
Một ứng dụng có hàng nghìn thread TIMED_WAITING do polling định kỳ, nhưng số luồng vẫn tăng liên tục sau mỗi request; hãy đặt tình huống xác định nguy cơ rò rỉ luồng.
Một API dùng thread pool cố định và queue không giới hạn, khiến nhiều request timeout dù toàn bộ worker đều bận xử lý công việc hợp lệ; hãy đặt tình huống đánh giá bão hòa hàng đợi.
Một hệ thống bị starve khi thread pool dành cho xử lý request đồng thời bị dùng để chạy tác vụ con đang chờ kết quả của chính pool; hãy đặt tình huống kiểm tra vòng phụ thuộc executor.
Một ứng dụng sử dụng CompletableFuture và lỗi hiếm khi tác vụ điều phối chờ kết quả của công việc không được cấp thread chạy; hãy xây dựng tình huống kiểm chứng thread starvation.
Một dịch vụ có một thread giữ monitor trong lúc gọi dịch vụ bên ngoài rất chậm, khiến hàng trăm request khác BLOCKED ở cùng khóa; hãy đặt bài toán xác định nguyên nhân gốc từ dump.
Một nhóm nhận thread dump tại hai thời điểm cách nhau vài giây nhưng không đối chiếu stack của cùng thread, khiến khó phân biệt tiến triển với kẹt cố định; hãy xây dựng tình huống phân tích chuỗi ảnh.
Một request báo timeout phía client trong khi server thread vẫn đang xử lý và giữ transaction, gây tăng số kết nối đang dùng; hãy đặt tình huống đối chiếu thread dump và connection pool.
Một hệ thống dùng read-write lock nhưng thao tác ghi dài khiến các request đọc chờ hàng loạt dù CPU còn trống; hãy xây dựng tình huống xác minh tranh chấp theo loại khóa.
Một ứng dụng sử dụng StampedLock nhưng một số luồng chờ cập nhật nhiều giây, khiến metric phản hồi xấu đi và thread dump khó giải thích; hãy đặt tình huống kết hợp quan sát lock và thời gian xử lý.
Một dịch vụ dùng ReentrantLock với điều kiện chờ nhưng hệ thống không phát tín hiệu trong một nhánh lỗi, khiến consumer ở trạng thái WAITING; hãy xây dựng tình huống kiểm tra nguồn tín hiệu.
Một hệ thống nhận cảnh báo thread count tăng sau mỗi đợt import dữ liệu, nhưng bộ đếm active request đã về 0; hãy đặt tình huống xác minh các executor chưa được đóng.
Một ứng dụng dùng virtual threads cho I/O và số lượng thread trong dashboard tăng lên hàng chục nghìn, nhưng CPU thấp và throughput bình thường; hãy đặt tình huống đánh giá metric thread thích hợp.
Một service dùng virtual threads nhưng bị nghẽn khi một thư viện native giữ tài nguyên trong thời gian dài, khiến nhóm cần phân biệt vấn đề carrier thread và tác vụ ảo; hãy xây dựng tình huống chẩn đoán.
Một ứng dụng có thread local chứa tenant context và một request được xử lý bằng thread pool tái sử dụng, khiến dữ liệu tenant bị lẫn giữa các giao dịch; hãy đặt tình huống thu thập dấu vết ngữ cảnh luồng.
Một hệ thống yêu cầu kiểm tra liveness của luồng tiêu thụ message nhưng thread dump chỉ ghi trạng thái WAITING mà không biết còn message trong broker hay không; hãy xây dựng tình huống đối chiếu nhiều nguồn.
Một dịch vụ gặp deadlock hiếm mỗi vài ngày, nhưng cơ chế lấy thread dump thủ công chỉ được kích hoạt sau khi Kubernetes restart Pod; hãy đặt tình huống thiết kế bằng chứng trước restart.
Một JMX exporter báo nhiều thread BLOCKED nhưng dữ liệu thread dump được thu sau giờ cao điểm lại không còn tranh chấp; hãy xây dựng tình huống đồng bộ thời điểm đo.
Một ứng dụng có vài thread JNI ở trạng thái RUNNABLE lâu bất thường và thiếu stack Java đầy đủ, khiến nhóm không thể kết luận chỉ dựa trên thread dump; hãy đặt tình huống đánh giá giới hạn quan sát.
Một hệ thống xử lý batch bị treo nhưng health endpoint vẫn trả 200 từ thread riêng, khiến đội vận hành bỏ qua tín hiệu tắc nghẽn nghiệp vụ; hãy xây dựng tình huống xác minh health và thực thi thực tế.
Một ứng dụng sử dụng scheduler chạy tác vụ hàng giờ nhưng sau nâng phiên bản một thread background đã chết vì exception và không còn chạy lần tiếp theo; hãy đặt tình huống phát hiện bằng thông tin runtime.
Một module có nhiều pool riêng cho HTTP, database và xử lý ảnh, nhưng thread names không phân biệt được nhiệm vụ khiến báo cáo sự cố khó quy trách nhiệm; hãy đặt bài toán thiết kế tín hiệu quan sát.
Một JVM có hàng chục ngàn thread dump records nhưng công cụ hiển thị bị cắt bớt nội dung, khiến nhóm không nhìn thấy thread đang giữ khóa; hãy đặt tình huống kiểm chứng độ đầy đủ artifact.
Một dịch vụ chỉ tạo ra tranh chấp khóa khi chạy đa core và dữ liệu thread dump ở máy phát triển một core không tái hiện vấn đề; hãy xây dựng tình huống đánh giá môi trường tái hiện.
Một ứng dụng Java báo OutOfMemoryError Java heap space trong giờ cao điểm nhưng nhóm chỉ tăng Xmx mà không xác minh object nào bị giữ lại; hãy đặt tình huống xác định đối tượng cần điều tra.
Một dịch vụ có heap usage sau GC tăng đều theo từng giờ, trong khi số request và tải không thay đổi, khiến nghi vấn memory leak xuất hiện; hãy xây dựng tình huống thiết kế thu thập chuỗi dữ liệu.
Một ứng dụng xây dựng cache không có giới hạn và heap dump cho thấy nhiều entry thuộc các key đã lâu không được truy cập; hãy đặt bài toán phân tích retained size và trách nhiệm lưu giữ.
Một module sử dụng ThreadLocal trên các worker sống lâu, khiến mỗi request để lại dữ liệu cá nhân trong heap dù request đã kết thúc; hãy đặt tình huống kiểm tra đường tham chiếu GC root.
Một service xử lý ảnh tạo byte array cực lớn theo request và đôi khi OOM dù sau đó memory usage giảm nhanh; hãy xây dựng tình huống phân biệt đột biến cấp phát với rò rỉ kéo dài.
Một nhóm lưu một heap dump duy nhất ở thời điểm tiến trình sắp OOM nhưng không có baseline từ trước khi tải tăng; hãy đặt tình huống xác định phương pháp so sánh.
Một ứng dụng sử dụng weak cache và nhiều đối tượng trong heap dump được giữ bởi cấu trúc tham chiếu yếu, khiến nhóm nhầm mọi object xuất hiện là leak; hãy xây dựng tình huống kiểm tra reachability.
Một hệ thống có danh sách listener tăng sau mỗi lần người dùng tạo phiên, nhưng lệnh heap histogram chỉ cho biết số object mà không thấy quan hệ giữ chúng; hãy đặt tình huống phân tích dominator và retention.
Một service có class loader leak sau mỗi lần triển khai plugin, khiến metaspace tăng nhưng heap của các đối tượng nghiệp vụ khá ổn định; hãy đặt bài toán xác định chuỗi tham chiếu giữ class loader.
Một ứng dụng dùng ByteBuffer.allocateDirect cho tải file lớn và bị lỗi thiếu direct memory dù heap dump nhỏ; hãy đặt tình huống phân biệt bộ nhớ trực tiếp với Java heap.
Một tiến trình bị OOM kill bởi container mà không in Java OutOfMemoryError, trong khi biểu đồ heap chỉ dùng một nửa giới hạn; hãy xây dựng tình huống xác minh RSS và native memory.
Một dịch vụ tăng native memory sau mỗi lần gọi JNI xử lý video, nhưng histogram Java không cho thấy số object tăng; hãy đặt tình huống đánh giá thu thập bằng chứng ngoài heap.
Một ứng dụng có hàng nghìn platform thread với stack lớn, khiến tổng bộ nhớ native tăng và vượt memory limit mặc dù Xmx không đổi; hãy đặt tình huống phân tích ngân sách bộ nhớ.
Một nhóm bật Native Memory Tracking sau khi tiến trình đã chạy lâu và muốn suy ra nguyên nhân tăng từ thời điểm trước khi bật; hãy xây dựng tình huống đánh giá dữ liệu baseline.
Một service báo Metaspace OutOfMemoryError sau nhiều lần load class động, nhưng đội hỗ trợ chỉ tìm object lớn trong heap dump; hãy đặt tình huống chọn dữ liệu theo loại lỗi bộ nhớ.
Một ứng dụng bị cạn code cache sau khi tạo nhiều proxy động và hiệu năng chậm lại, trong khi nhóm chỉ kiểm tra heap và GC; hãy xây dựng tình huống đánh giá vùng nhớ mã máy.
Một API giữ một danh sách kết quả hàng triệu bản ghi trong memory dù chỉ trả vài trăm bản ghi cho client, khiến heap dump chứa nhiều object giống nhau; hãy đặt tình huống tìm nguồn tạo và retention.
Một hệ thống xử lý lô dữ liệu lớn với nhiều object ngắn hạn, khiến allocation rate tăng cao nhưng live heap sau GC vẫn thấp; hãy xây dựng tình huống đánh giá có thực sự là leak hay không.
Một dịch vụ truyền file lớn sử dụng buffer pooling, nhưng pool chỉ mở rộng và không thu hẹp sau thời điểm cao tải, khiến bộ nhớ được giữ dài hạn; hãy đặt tình huống phân biệt thiết kế pool với lỗi leak.
Một ứng dụng thu heap dump ngay khi chứa token truy cập và thông tin cá nhân trong bộ nhớ, sau đó upload artifact lên kho chia sẻ chung; hãy đặt tình huống đánh giá an toàn dữ liệu chẩn đoán.
Một heap dump có kích thước lớn gần bằng dung lượng còn trống của volume, khiến việc tạo dump có nguy cơ làm đầy ổ và dừng service; hãy đặt bài toán lựa chọn cách thu thập phù hợp.
Một dịch vụ cấu hình tự động tạo heap dump khi OOM nhưng path nằm trong lớp filesystem không có quyền ghi hoặc không còn dung lượng; hãy xây dựng tình huống kiểm chứng khả năng giữ bằng chứng.
Một hệ thống nhận nhiều lỗi OOM từ các replica cùng thời điểm và tất cả ghi heap dump vào một volume chung khiến dung lượng bị cạn; hãy đặt tình huống đánh giá giới hạn tài nguyên chẩn đoán.
Một ứng dụng có bộ cache mang dữ liệu cũ nhưng heap dump được lấy sau full GC và đối tượng nghi ngờ đã biến mất, khiến đội vận hành bỏ sót pha tăng bộ nhớ; hãy đặt tình huống xác định thời điểm chụp.
Một tiến trình Java có heap usage tăng sau rollout nhưng dữ liệu histogram từ hai lần lấy dùng các điều kiện GC khác nhau, khiến việc so sánh số object bị sai lệch; hãy đặt bài toán đánh giá tính nhất quán phép đo.
Một ứng dụng có object được giữ bởi static map và số lượng tăng theo tenant mới, nhưng không có nhãn tenant trong dữ liệu đo thông thường; hãy xây dựng tình huống tìm mối liên hệ nghiệp vụ.
Một hệ thống có nhiều chu trình tham chiếu giữa object nhưng không còn GC root giữ chúng, trong khi nhóm quy kết mọi chu trình là nguyên nhân rò rỉ; hãy đặt tình huống đánh giá đường sống của object.
Một service dùng custom class loader nạp script động, và sau khi script ngừng hoạt động các Class object vẫn còn trong heap; hãy đặt tình huống kiểm tra điều kiện unload lớp.
Một ứng dụng ghi nhận số lượng object trong histogram giảm nhưng RSS không giảm tương ứng, khiến đội hỗ trợ cho rằng GC không hoạt động; hãy đặt tình huống diễn giải heap committed và bộ nhớ hệ điều hành.
Một API có heap dump ghi nhận một object graph rất lớn do bộ nhớ đệm, nhưng công cụ chỉ sắp xếp theo shallow size và không thấy owner thực sự; hãy xây dựng tình huống đánh giá retained size.
Một hệ thống có lỗi OutOfMemoryError do yêu cầu tạo mảng lớn liên tục, nhưng nhóm cố kết luận heap leak từ một ảnh chụp tại thời điểm sau crash; hãy đặt tình huống kiểm chứng loại sự cố.
Một ứng dụng theo dõi chỉ số GC collection count nhưng p99 latency tăng rõ rệt mỗi giờ, khiến nhóm không biết thời gian dừng đã thay đổi ra sao; hãy xây dựng tình huống phân tích GC pause.
Một dịch vụ dùng G1 và GC log ghi nhận humongous allocation liên tục khi xử lý file upload, khiến thời gian đáp ứng tăng dưới tải; hãy đặt tình huống đánh giá loại đối tượng và vùng cấp phát.
Một ứng dụng có old generation tăng nhanh cùng nhiều lần promotion nhưng chỉ theo dõi young GC count, khiến nguy cơ thiếu heap không được cảnh báo sớm; hãy đặt bài toán xác định tín hiệu GC.
Một service có full GC kéo dài sau khi cache tăng đột biến, nhưng thread dump lấy sau đó không có dấu hiệu tranh chấp; hãy xây dựng tình huống đối chiếu timestamp của GC và request.
Một nhóm bật GC log ở môi trường thử nghiệm nhưng không có dữ liệu production khi phát sinh pause dài, khiến khó so sánh thực tế; hãy đặt tình huống thiết kế mức ghi nhận phù hợp.
Một hệ thống chạy nhiều JVM trên node và tất cả ghi GC log vào cùng file chia sẻ, khiến timestamp và sự kiện bị trộn; hãy đặt tình huống kiểm tra định danh artifact.
Một ứng dụng dùng GC log rolling nhưng cấu hình giữ quá ít file nên chỉ lưu vài phút trước sự cố OOM, khiến mất diễn biến dẫn tới lỗi; hãy đặt tình huống đánh giá chính sách lưu giữ.
Một dịch vụ khởi động với collector khác ở production so với staging, nhưng dashboard gộp metric pause của hai môi trường làm kết luận sai; hãy xây dựng tình huống so sánh tương ứng.
Một ứng dụng thay đổi mức Xmx để giảm tần suất GC nhưng container bắt đầu bị OOM kill dù số lần GC giảm; hãy đặt tình huống đánh giá tổng ngân sách bộ nhớ.
Một đội hỗ trợ kết luận CPU cao hoàn toàn do GC từ GC log, nhưng JFR lại ghi nhận hot method ứng dụng trong cùng khoảng thời gian; hãy xây dựng tình huống đánh giá bằng chứng mâu thuẫn.
Một service có nhiều young GC ngắn trong lúc allocation rate tăng nhưng p99 vẫn đạt SLO, khiến nhóm muốn tối ưu GC dù chưa xác định tác động nghiệp vụ; hãy đặt bài toán xác định ưu tiên điều tra.
Một hệ thống có mixed collection dài khi nhiều object sống lâu được giữ trong cache, khiến thời gian phản hồi vượt ngưỡng; hãy đặt tình huống kiểm tra tương quan live set và pause.
Một ứng dụng sử dụng collector đồng thời để giảm pause nhưng CPU tổng tăng và throughput giảm dưới cùng workload, khiến nhóm chưa rõ tradeoff; hãy đặt tình huống thiết kế so sánh.
Một nhóm đọc GC log thấy heap occupancy vẫn cao ngay sau collection nhưng chưa xác định được heap có chứa dữ liệu sống hợp lệ hay không; hãy đặt tình huống kết hợp dữ liệu bộ nhớ.
Một service bị container kill tại thời điểm heap còn khoảng trống lớn và GC log không ghi OutOfMemoryError, khiến đội vận hành nghi ngờ native memory vượt giới hạn; hãy đặt bài toán xác minh giả thuyết.
Một ứng dụng bị tăng thời gian tới safepoint nhưng log GC không báo pause dài, khiến nhóm quy kết mọi sự kiện dừng là do collector; hãy đặt tình huống phân biệt các nguyên nhân tại safepoint.
Một hệ thống batch có khoảng dừng dài do explicit GC ngay sau khi hoàn tất từng lô, nhưng dashboard chỉ cho thấy heap giảm đột ngột; hãy xây dựng tình huống kiểm tra nguyên nhân kích hoạt collection.
Một dịch vụ có cảnh báo GC overhead limit exceeded trong khi số lượng object sống tăng dần, khiến việc đổi collector có nguy cơ che khuất vấn đề lưu giữ dữ liệu; hãy đặt tình huống đánh giá nguyên nhân.
Một tổ chức muốn thay cấu hình GC dựa trên log từ JDK cũ nhưng các tag, thuật ngữ và cách ghi log đã khác ở bản JDK mới; hãy đặt tình huống kiểm tra tính tương thích cách phân tích.
Một dịch vụ giao dịch có độ trễ cao khi code cache đầy, nhưng log GC không bất thường và nhóm chỉ có dữ liệu collector; hãy xây dựng tình huống tìm bằng chứng về runtime ngoài GC.
Một ứng dụng theo dõi JMX MBean của memory pool nhưng tên pool thay đổi theo collector mới, làm dashboard không nhận được dữ liệu đúng; hãy đặt tình huống kiểm chứng tính khả chuyển của metric.
Một service công bố heap used qua JMX nhưng chỉ số retained heap trên biểu đồ được tính bằng snapshot không cùng thời điểm, khiến báo cáo dung lượng bị hiểu sai; hãy xây dựng tình huống xác định ngữ nghĩa metric.
Một hệ thống dùng JMX remote để lấy thông tin JVM nhưng không thể kết nối qua firewall vì cổng RMI động khác với cổng đăng ký; hãy đặt tình huống chẩn đoán luồng kết nối.
Một nhóm mở JMX remote trên toàn bộ interface mạng để phục vụ giám sát và vô tình cho phép tài khoản ngoài vận hành xem thông tin nhạy cảm của JVM; hãy đặt bài toán đánh giá ranh giới truy cập.
Một ứng dụng bật JMX authentication nhưng credential giám sát được đưa vào file cấu hình có quyền đọc quá rộng, khiến dữ liệu giám sát trở thành điểm rò rỉ; hãy xây dựng tình huống kiểm tra.
Một tổ chức vận hành nhiều JVM trên cùng host và JMX exporter có nhãn instance không duy nhất, khiến metric thread của service này được gắn cho service khác; hãy đặt tình huống đánh giá nhãn dữ liệu.
Một nhóm triển khai JMX exporter như Java agent nhưng quá trình scrape thường xuyên gây overhead khi có hàng nghìn MBean động; hãy đặt tình huống phân tích chi phí quan sát.
Một dịch vụ có số lượng active thread tăng nhưng JMX chỉ hiển thị tổng số thread và không phân biệt worker nghiệp vụ với executor nền; hãy đặt tình huống thiết kế chỉ số chẩn đoán.
Một ứng dụng liên tục tạo và hủy class loader nhưng MBean chỉ hiển thị cumulative classes loaded, khiến đội vận hành nhầm tốc độ tải lớp với số lớp còn sống; hãy xây dựng tình huống đánh giá chỉ số class loading.
Một service cấu hình health check dựa vào JMX heap usage nhưng vẫn trả healthy khi toàn bộ request bị kẹt do lock contention; hãy đặt tình huống kiểm tra độ bao phủ tín hiệu.
Một bộ giám sát thu GC time qua JMX nhưng không thể phân biệt pause do collector với độ trễ mạng tới exporter khi scrape chậm; hãy đặt tình huống xác minh timestamp và nguồn số liệu.
Một hệ thống dùng JMX để đọc các giá trị VM options nhưng một cờ có nguồn từ container và khác giá trị mà đội phát triển nghĩ đã áp dụng; hãy đặt tình huống xác nhận cấu hình thực thi.
Một ứng dụng mở rộng từ một lên nhiều replica nhưng hệ thống giám sát vẫn cộng mọi giá trị heap used như thể đây là một tiến trình duy nhất, khiến cảnh báo sai ngưỡng; hãy đặt tình huống đánh giá aggregation.
Một bộ phận hỗ trợ cần đo thời gian chờ khóa qua JMX nhưng ứng dụng chưa bật các khả năng thống kê tương ứng, làm một số số đo không có dữ liệu; hãy đặt tình huống kiểm tra điều kiện đo.
Một service dùng JMX notification để phát cảnh báo memory threshold nhưng chuỗi cảnh báo chỉ phát ra sau khi người dùng đã gặp lỗi, khiến đội vận hành cần đánh giá tín hiệu sớm hơn; hãy xây dựng tình huống.
Một ứng dụng đang chạy production với overhead thấp nhưng nhóm muốn khởi động Java Flight Recorder sau khi xuất hiện spike latency, cần lưu lại ngữ cảnh trước và sau sự kiện; hãy đặt tình huống xác định chế độ ghi.
Một dịch vụ sử dụng JFR liên tục nhưng dung lượng file ghi ngày càng tăng vì chưa có chính sách giới hạn và lưu trữ, khiến ổ đĩa container gần đầy; hãy xây dựng tình huống đánh giá vòng đời recording.
Một nhóm thu JFR trong vài giây và chỉ thấy CPU samples trong lúc lỗi I/O kéo dài diễn ra sau đó, khiến báo cáo không có bằng chứng phù hợp; hãy đặt tình huống chọn cửa sổ quan sát.
Một ứng dụng gặp tranh chấp monitor nhưng profile CPU sampling không chỉ ra nguyên nhân, trong khi các sự kiện JFR về lock có thể bổ sung ngữ cảnh; hãy xây dựng tình huống lựa chọn loại sự kiện.
Một service mất nhiều thời gian xử lý request nhưng JFR cho thấy luồng chủ yếu chờ socket read; hãy đặt tình huống đánh giá quan hệ giữa thời gian tường và thời gian CPU.
Một nhóm thu JFR nhưng chỉ xem danh sách hot methods mà không đối chiếu thread, thời điểm, allocation và I/O theo request lỗi; hãy đặt tình huống xây dựng điều tra đa chiều.
Một ứng dụng có kết nối database chậm ngẫu nhiên, nhưng JFR bật sự kiện socket mà không có dữ liệu gọi JDBC phù hợp nên khó gắn sự cố với nghiệp vụ; hãy đặt tình huống xác định giới hạn bằng chứng.
Một dịch vụ sử dụng JFR với mức cấu hình chi tiết cao trong giờ cao tải và thấy throughput giảm, khiến nhóm cần đánh giá chi phí từng loại sự kiện; hãy đặt bài toán kiểm chứng overhead.
Một recording JFR được tạo trước khi Pod restart nhưng file chưa được dump hoặc lưu bên ngoài filesystem Pod, khiến toàn bộ dữ liệu trước crash bị mất; hãy xây dựng tình huống bảo toàn dữ liệu.
Một nhóm triển khai JFR trên nhiều replica nhưng tất cả sử dụng cùng tên file và upload vào một đường dẫn chung, khiến artifact của các node bị ghi đè; hãy đặt tình huống kiểm tra định danh dữ liệu.
Một ứng dụng có memory leak xuất hiện qua nhiều giờ, nhưng JFR chỉ ghi allocation samples rất ngắn và không đủ bằng chứng về object retention; hãy đặt tình huống đánh giá khả năng và giới hạn recording.
Một service có nhiều exceptions được JFR ghi nhận sau phát hành, nhưng phần lớn là lỗi nghiệp vụ có thể dự đoán và không gây sự cố; hãy đặt tình huống phân biệt tín hiệu cần ưu tiên.
Một hệ thống liên tục chạy JFR ở cấu hình mặc định nhưng một loại sự kiện native I/O đặc biệt không được ghi, khiến đội vận hành kết luận sai là không có I/O; hãy đặt tình huống đánh giá độ phủ.
Một nhóm so sánh hai recording JFR trước và sau release nhưng các recording dùng cấu hình sự kiện và ngưỡng thu mẫu khác nhau; hãy xây dựng tình huống kiểm chứng tính so sánh.
Một ứng dụng ghi JFR trong container giới hạn CPU và kết quả có ít CPU sample hơn khi JVM bị throttling, khiến hot method bị đánh giá sai; hãy đặt tình huống xem xét đặc điểm môi trường.
Một dịch vụ bị lỗi latency khi đồng thời nhiều request chờ database nhưng đội hỗ trợ chỉ mở tab Garbage Collections trong JFR và không thấy bất thường; hãy đặt tình huống tìm sự kiện chờ phù hợp.
Một hệ thống cần liên hệ trace ID của request lỗi với dữ liệu JFR, nhưng các thread được tái sử dụng và tên thread không đủ định danh giao dịch; hãy đặt tình huống đánh giá cách đối chiếu bằng chứng.
Một JVM có thời gian GC pause ngắn nhưng JFR cho thấy nhiều allocation từ một parser JSON, khiến nhóm cần phân biệt chi phí cấp phát và chi phí thu gom; hãy đặt tình huống kiểm chứng bottleneck.
Một bộ phận bảo mật phát hiện recording JFR chứa path, tên thread và tham số có dữ liệu nhạy cảm, nhưng artifact được lưu vào kho hỗ trợ không kiểm soát truy cập; hãy đặt bài toán đánh giá an toàn bằng chứng.
Một ứng dụng có nhiều virtual thread và việc phân tích JFR theo platform thread làm nhóm hiểu sai hoạt động đồng thời; hãy đặt tình huống lựa chọn thông tin tương quan phù hợp.
Một hệ thống nâng JDK làm danh sách sự kiện JFR thay đổi nhưng dashboard vẫn dùng giả định cũ về ý nghĩa từng event; hãy xây dựng tình huống kiểm tra khả năng tương thích dữ liệu.
Một dịch vụ có JFR file lớn không thể chuyển ra ngoài qua mạng hạn chế trong thời gian xử lý sự cố, khiến đội hỗ trợ cần cân nhắc phạm vi dữ liệu cần lấy; hãy đặt tình huống đánh giá chi phí artifact.
Một ứng dụng báo lỗi I/O timeout khi gọi API phụ trợ, nhưng thread dump chỉ hiển thị socket read và không có dữ liệu endpoint được gọi; hãy xây dựng tình huống kết hợp stack và log request.
Một hệ thống sử dụng connection pool JDBC và request chờ mượn kết nối dù database CPU thấp, khiến đội vận hành nhầm lỗi với truy vấn SQL chậm; hãy đặt tình huống kiểm chứng thời gian chờ pool.
Một service lưu lượng thấp nhưng mỗi lần upload file lớn đều bị treo ở ghi đĩa, trong khi CPU và heap ổn định; hãy đặt tình huống thu thập bằng chứng về I/O.
Một API gọi endpoint bên ngoài bị chậm sau thay đổi DNS, nhưng JVM vẫn lưu địa chỉ đã resolve từ trước và log chỉ hiển thị hostname; hãy đặt tình huống kiểm tra nguyên nhân định tuyến.
Một dịch vụ giao tiếp TLS với hệ thống thanh toán và thời gian handshake tăng sau rotation chứng chỉ, trong khi số request thành công không đổi; hãy đặt bài toán điều tra độ trễ kết nối.
Một ứng dụng dùng NIO selector và đôi khi vòng xử lý event không tiến triển dù socket còn dữ liệu, khiến thread dump chỉ cho thấy phương thức select; hãy đặt tình huống xác định thêm bằng chứng.
Một service gửi nhiều request tới downstream qua HTTP client pool, nhưng kết nối đang bận không được trả lại sau một nhánh lỗi, khiến request mới phải chờ; hãy xây dựng tình huống kiểm tra rò rỉ kết nối.
Một hệ thống bị chậm do NFS volume latency tăng nhưng thread dump chỉ có nhiều luồng chờ file write, khiến nhóm nghi ngờ JVM GC; hãy đặt tình huống phân biệt nguồn nghẽn.
Một ứng dụng ghi log đồng bộ trên disk có tốc độ thấp và request latency tăng theo kích thước log, trong khi CPU không quá tải; hãy đặt tình huống đánh giá đường ghi I/O.
Một batch job chậm bất thường vì đọc dữ liệu hàng triệu lần từ cùng file nhỏ, nhưng JFR chỉ ghi một phần hoạt động do ngưỡng sự kiện; hãy xây dựng tình huống đánh giá phép đo.
Một dịch vụ mở hàng chục nghìn socket sau khi bật keep-alive nhưng gặp lỗi too many open files dù heap còn dư; hãy đặt tình huống kiểm chứng giới hạn file descriptor.
Một ứng dụng nhận nhiều kết nối client nhưng số request được xử lý giảm khi backlog tăng, trong khi JVM thread count chưa chạm ngưỡng; hãy xây dựng tình huống phối hợp dữ liệu JVM và mạng.
Một service cần xác minh lỗi HTTP timeout đến từ DNS, bắt tay TLS, chờ connection pool hay đọc response, nhưng log hiện chỉ ghi một thời gian tổng; hãy đặt bài toán phân loại giai đoạn I/O.
Một API tải dữ liệu từ object storage và thỉnh thoảng gặp socket reset khi xử lý file lớn, nhưng bộ test chỉ tải file nhỏ trong môi trường nội bộ; hãy đặt tình huống xác định nguồn quan sát tại runtime.
Một ứng dụng dùng async HTTP client nhưng một callback thực thi công việc blocking trong event loop, khiến toàn bộ kết nối mới chậm mà CPU vẫn không cao; hãy xây dựng tình huống chẩn đoán luồng I/O.
Một service gọi DNS resolver và timeout tăng ở một AZ duy nhất, trong khi báo cáo JFR tổng hợp nhiều AZ làm mất khác biệt; hãy đặt tình huống đánh giá phạm vi so sánh.
Một hệ thống xuất file CSV đồng thời làm đầy volume tạm khiến các tác vụ khác báo I/O error, trong khi JVM chỉ ghi exception chung; hãy đặt tình huống thu thập dấu vết tài nguyên filesystem.
Một ứng dụng xử lý log asynchronous có hàng đợi đầy khi đĩa chậm, khiến thread nghiệp vụ bị block để chờ ghi log; hãy đặt bài toán đối chiếu event queue, thread dump và I/O.
Một service dùng WebClient hoặc HttpClient nhiều kết nối và sau thời gian dài số socket CLOSE_WAIT tăng, khiến node gần hết file descriptor; hãy đặt tình huống đánh giá vòng đời kết nối.
Một ứng dụng gRPC có nhiều stream kéo dài nhưng nhóm chỉ nhìn request count HTTP thông thường và không biết stream nào giữ tài nguyên; hãy đặt tình huống thiết kế chẩn đoán I/O theo luồng.
Một JVM báo SIGSEGV trong thư viện JNI khi xử lý ảnh nhưng không có Java exception trước khi thoát, khiến chỉ còn file báo lỗi fatal của HotSpot; hãy xây dựng tình huống điều tra native crash.
Một dịch vụ Java tự động restart sau native crash và file hs_err_pid bị xóa cùng container, khiến đội phát triển không có thông tin frame hay thư viện gây lỗi; hãy đặt tình huống bảo toàn artifact.
Một ứng dụng báo JVM fatal error sau khi triển khai một native agent mới, nhưng đội vận hành chỉ kiểm tra stack trace Java thường; hãy đặt tình huống xác minh lớp lỗi native.
Một tiến trình bị kill bởi kernel OOM killer nhưng hệ thống giám sát gán nhãn JVM crash, khiến nhóm tìm sai nguyên nhân trong GC logs; hãy xây dựng tình huống phân biệt tác nhân kết thúc.
Một chương trình phát sinh StackOverflowError khi xử lý biểu thức đệ quy sâu nhưng heap vẫn trống và nhóm định tăng Xmx; hãy đặt bài toán phân tích loại giới hạn tài nguyên.
Một ứng dụng thi thoảng ném OutOfMemoryError unable to create native thread, trong khi số đối tượng Java không tăng; hãy xây dựng tình huống kiểm chứng tài nguyên thread và bộ nhớ native.
Một dịch vụ gặp lỗi direct buffer memory sau khi tải file lớn liên tục nhưng cơ chế tự động tạo heap dump không giúp xác định vùng bị cạn; hãy đặt tình huống đánh giá loại bằng chứng.
Một hệ thống chạy êm ở staging nhưng production bị JIT compilation chậm và code cache đầy, khiến các method mới chuyển sang thực thi kém hiệu quả; hãy đặt tình huống chẩn đoán compiler/code cache.
Một ứng dụng gặp sự cố khi load plugin và báo LinkageError, nhưng đội hỗ trợ nhầm với lỗi heap do process đồng thời đang sử dụng nhiều bộ nhớ; hãy đặt tình huống phân loại bằng chứng.
Một JVM gặp lỗi trong quá trình class initialization khiến endpoint chỉ thất bại ở lần gọi đầu tiên, còn các lần sau trả lỗi khác; hãy đặt tình huống đối chiếu chuỗi exception runtime.
Một dịch vụ phát sinh các sự cố native memory trên vài node có kernel khác nhau, trong khi chỉ một node có core dump được giữ lại; hãy xây dựng tình huống so sánh môi trường.
Một Java agent instrumentation làm thay đổi bytecode khiến một lớp báo VerifyError ở production nhưng không xuất hiện trong staging; hãy đặt bài toán thu thập thông tin class loading và agent.
Một hệ thống sử dụng thư viện mã hóa native và sau nâng JDK xảy ra crash hiếm, nhưng báo cáo incident không lưu phiên bản binary và cờ JVM; hãy đặt tình huống đánh giá dữ liệu nền tảng.
Một tổ chức cần chẩn đoán lỗi JVM trong Pod giới hạn quyền, nhưng đề xuất bật mọi quyền đặc biệt để lấy core dump có thể làm tăng rủi ro bảo mật; hãy đặt tình huống đánh giá phương án thu thập.
Một đợt release làm service thoát đột ngột với exit code khác nhau giữa container bị OOM và ứng dụng gọi System.exit, nhưng nhóm chỉ có trạng thái restart; hãy đặt tình huống kiểm tra nguyên nhân kết thúc.
Một tiến trình Java báo native crash sau khi thay phiên bản libc trong base image, trong khi ứng dụng Java và JAR không đổi; hãy đặt tình huống xác minh tương thích môi trường.
Một ứng dụng gặp IllegalAccessError khi nạp thư viện plugin mới, nhưng bộ chẩn đoán chỉ thu CPU và heap mà không lấy classpath/module information; hãy đặt tình huống điều tra lỗi liên kết.
Một hệ thống cần phân biệt lỗi OOM Java heap, metaspace, direct memory và container kill để xác định hành động phù hợp, nhưng mọi cảnh báo đều ghi chung memory high; hãy xây dựng tình huống phân loại.
Một ứng dụng gặp p99 latency tăng ngay sau thay đổi JVM flags, nhưng artifact triển khai không ghi lại giá trị cờ thực tế đang được dùng; hãy đặt tình huống kiểm chứng cấu hình runtime.
Một dịch vụ có chỉ số GC pause tốt nhưng health check thất bại vì thread pool chặn bởi dependency, trong khi dashboard gom mọi lỗi dưới nhãn JVM unhealthy; hãy xây dựng tình huống kết hợp bằng chứng.
Một nhóm sử dụng jcmd GC.class_histogram định kỳ trên production và không biết có thể gây chi phí quan sát khi heap lớn, khiến request latency biến động đúng giờ thu mẫu; hãy đặt tình huống đánh giá mức ảnh hưởng.
Một ứng dụng thu heap dump để điều tra leak nhưng process bị dừng phục vụ lâu hơn SLO, khiến nhóm phải cân nhắc phương pháp kiểm tra ít xâm lấn hơn; hãy đặt bài toán chọn bằng chứng.
Một tổ chức dùng JFR như bằng chứng điều tra nhưng chưa kiểm tra thời gian đồng hồ giữa host, container và hệ thống log, khiến sự kiện không ghép đúng với trace; hãy đặt tình huống đồng bộ thời gian.
Một ứng dụng có CPU spike ngắn dưới một giây mà hệ thống giám sát lấy mẫu mỗi phút, khiến alert không ghi nhận sự cố dù khách hàng đã thấy timeout; hãy đặt tình huống xác định độ phân giải dữ liệu.
Một service chạy trên nhiều Pod và chỉ một Pod có memory leak do request theo tenant đặc biệt, nhưng biểu đồ tổng hợp toàn deployment che khuất xu hướng; hãy xây dựng tình huống phân tích theo instance.
Một đội vận hành chỉ lưu metric sau khi JVM đã khởi động lại nên đường biểu diễn heap reset về thấp, khiến chu kỳ tăng trước OOM không được nhìn thấy; hãy đặt tình huống giữ lịch sử qua restart.
Một hệ thống tập trung dữ liệu jcmd, JFR và GC logs nhưng không gắn cùng deployment ID, khiến các artifact từ hai phiên bản ứng dụng bị trộn; hãy đặt tình huống kiểm chứng truy vết.
Một ứng dụng có log thời gian UTC, metric theo múi giờ địa phương và JFR theo thời gian của host, khiến dữ liệu một sự cố bị xem như ba sự kiện khác nhau; hãy xây dựng tình huống xác minh mốc thời gian.
Một service Java được triển khai trên hai kiến trúc CPU khác nhau nhưng report CPU profiler dùng cùng baseline và nhóm đưa ra kết luận tối ưu không phù hợp; hãy đặt tình huống đánh giá tính so sánh.
Một nhóm tự động thu thập heap dump khi memory usage vượt ngưỡng nhưng không có giới hạn dung lượng upload, khiến đường truyền vận hành bị nghẽn trong giờ cao điểm; hãy xây dựng tình huống kiểm thử cơ chế thu thập.
Một ứng dụng bị tăng độ trễ sau khi bật JMX exporter và JFR với cấu hình chi tiết cùng lúc, khiến đội phát triển khó phân biệt overhead của hai nguồn quan sát; hãy đặt tình huống thiết kế phép đo.
Một đội hỗ trợ nhận yêu cầu cung cấp thread dump cho khách hàng nhưng file chứa tên tài khoản và URL nội bộ từ stack trace, trong khi chưa có quy trình kiểm duyệt dữ liệu; hãy đặt tình huống bảo vệ artifact.
Một hệ thống lưu heap dump tại thư mục chung với log ứng dụng mà không mã hóa, khiến các bí mật trong heap có thể bị đọc bởi nhóm không có quyền truy cập dữ liệu gốc; hãy đặt bài toán đánh giá lưu trữ.
Một pipeline CI sao chép toàn bộ bản JFR từ production sang môi trường kiểm thử để phân tích hiệu năng, nhưng bản ghi có metadata người dùng thật; hãy xây dựng tình huống kiểm chứng giới hạn dữ liệu.
Một tổ chức muốn giữ quyền attach vào JVM cho nhóm vận hành nhưng không cấp quyền thực thi các lệnh chẩn đoán gây thay đổi trạng thái ngoài ý muốn; hãy đặt tình huống đánh giá ranh giới quyền.
Một dịch vụ có lỗi hiệu năng xuất hiện khi bật tracing ở mức chi tiết, nhưng đội chẩn đoán quên so sánh với baseline không có instrumentation; hãy đặt tình huống kiểm tra chi phí quan sát.
Một ứng dụng gặp sự cố sau nâng cấp JDK và một số tên JMX MBean cùng cấu trúc GC log thay đổi, khiến dashboard cũ không nhận đúng tín hiệu; hãy đặt tình huống kiểm chứng khả năng tương thích.
Một nhóm vận hành định thu toàn bộ thread dump mỗi giây khi số request tăng, nhưng heap và I/O của service đã sát ngưỡng; hãy đặt bài toán đánh giá tần suất thu mẫu an toàn.
Một hệ thống không ghi nhận giá trị CPU quota và memory limit container lúc sự cố, khiến nhóm không xác định được JVM quá tải do ứng dụng hay do giới hạn triển khai; hãy xây dựng tình huống thu thập môi trường.
Một dịch vụ có nhiều instance chia sẻ host và JFR ghi nhận CPU samples khi máy bị quá tải bởi process khác, nhưng nhóm chỉ phân tích code Java của instance; hãy đặt tình huống phân biệt tranh chấp host.
Một API có request latency tăng cùng lúc các luồng chờ connection pool và GC pause nhỏ, nhưng báo cáo tổng kết chỉ lấy sự kiện GC đầu tiên làm nguyên nhân; hãy đặt tình huống đánh giá chuỗi nhân quả.
Một lỗi sản xuất được tái hiện ở staging khi tăng tải nhưng đội phát triển không xác định được mức CPU, heap và các bộ cấu hình khác biệt giữa hai môi trường; hãy xây dựng tình huống kiểm chứng tính đại diện.
Một công ty muốn chứng minh thay đổi timeout kết nối giải quyết được lỗi I/O nhưng chỉ nhìn tỷ lệ request thành công mà không so sánh thread wait time và JFR socket events; hãy đặt tình huống thiết kế tiêu chí.
Một tổ chức xây dựng playbook cho sự cố JVM nhưng chưa tách các nhánh CPU cao, ứng dụng treo, heap leak, native memory, lỗi I/O và native crash; hãy xây dựng tình huống xác định bằng chứng ưu tiên.
Một team nhận phản ánh rằng Java service tự phục hồi sau vài phút nhưng muốn thu chứng cứ mà không làm tăng tải hệ thống đang nhạy cảm, trong khi chỉ có quyền vận hành hạn chế; hãy đặt tình huống lựa chọn mức quan sát.
Một sản phẩm cần đánh giá bản phát hành giảm p99 latency mà không làm tăng allocation, GC pause, lock contention và memory footprint, nhưng pipeline hiện chỉ đo thời gian trung bình; hãy xây dựng tình huống xác định ma trận chỉ số.
Một hệ thống có nhiều sự cố JVM độc lập qua vài tuần nhưng file dump, log GC và JFR được lưu rời rạc không có nhãn incident hoặc mốc deploy, khiến việc đối chiếu khó khăn; hãy đặt tình huống thiết kế lưu trữ.
Một tổ chức cần chứng minh quy trình chẩn đoán runtime có thể hoạt động cả khi JVM đang sống, khi container vừa bị kill và khi không có quyền attach, nhưng thử nghiệm hiện chỉ chạy trên máy phát triển; hãy đặt tình huống xây dựng kiểm thử diễn tập.

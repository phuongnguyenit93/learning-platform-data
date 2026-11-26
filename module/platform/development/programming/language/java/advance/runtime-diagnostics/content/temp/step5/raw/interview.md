Bạn xác định mục tiêu của chẩn đoán runtime Java khác với debug bằng breakpoint trong môi trường phát triển như thế nào?
Bạn xây dựng quy trình điều tra một sự cố Java production từ triệu chứng, giả thuyết đến bằng chứng kỹ thuật ra sao?
Bạn lựa chọn chỉ số nào để phân biệt ứng dụng phản hồi chậm, sử dụng CPU cao và gần cạn bộ nhớ trước khi thu thập dump?
Bạn lựa chọn những mốc thời gian và định danh instance nào để đối chiếu dữ liệu JVM với log ứng dụng?
Bạn giải thích những rủi ro về chi phí CPU, I/O và độ trễ khi kích hoạt công cụ chẩn đoán trên hệ thống đang có tải ra sao?
Bạn ưu tiên thu thập loại bằng chứng nào khi thời gian xử lý sự cố rất ngắn và việc khởi động lại có thể làm mất trạng thái?
Bạn phân biệt dữ liệu quan sát tại một thời điểm với dữ liệu theo chuỗi thời gian khi phân tích nguyên nhân gốc như thế nào?
Bạn thiết kế bộ thông tin tối thiểu cần lưu cho một báo cáo sự cố JVM mà không làm lộ dữ liệu người dùng ra sao?
Bạn đánh giá tính nhất quán giữa thời gian trên máy chủ, container, hệ thống metrics và file dump bằng cách nào?
Bạn xác định thời điểm cần chụp nhiều mẫu liên tiếp thay vì dựa trên một lần đo để tránh kết luận sai như thế nào?
Bạn giải thích vai trò của jcmd trong việc gửi lệnh chẩn đoán đến JVM đang chạy như thế nào?
Bạn xác định đúng Java process cần điều tra khi một máy chủ có nhiều JVM dựa trên PID, command line và thông tin triển khai ra sao?
Bạn dùng jcmd để xem danh sách tiến trình Java và kiểm tra command line của tiến trình mục tiêu như thế nào?
Bạn kiểm tra các diagnostic command mà một JVM cụ thể hỗ trợ trước khi thực thi như thế nào?
Bạn lựa chọn VM.flags và VM.command_line để đối chiếu tham số JVM thực tế với cấu hình triển khai ra sao?
Bạn dùng VM.system_properties để tìm sai lệch runtime mà vẫn tránh đưa giá trị thuộc tính nhạy cảm vào báo cáo như thế nào?
Bạn phân biệt tham số JVM được khai báo lúc khởi động với giá trị hiệu lực của một tùy chọn khi phân tích sự cố ra sao?
Bạn giải thích những giới hạn của cơ chế attach khi chạy jcmd từ tài khoản hệ điều hành hoặc container khác như thế nào?
Bạn sẽ kiểm tra những nguyên nhân nào khi jcmd không attach được dù Java process vẫn hoạt động?
Bạn đánh giá tác động của quyền truy cập file hệ thống và không gian PID trong container lên việc kết nối công cụ chẩn đoán ra sao?
Bạn phân biệt khả năng lấy dữ liệu qua jcmd với khả năng quan sát qua JMX khi JVM không cho phép attach như thế nào?
Bạn dùng GC.heap_info để đánh giá nhanh sức chứa heap và các vùng bộ nhớ mà JVM đang quản lý như thế nào?
Bạn lựa chọn GC.class_histogram để kiểm tra thay đổi phân bố đối tượng trước khi yêu cầu heap dump toàn phần ra sao?
Bạn phân tích sự khác nhau giữa class histogram và heap dump về khả năng xác định đối tượng đang giữ tham chiếu như thế nào?
Bạn đánh giá nguy cơ làm thay đổi trạng thái heap hoặc tạm dừng ứng dụng của các biến thể lệnh tạo histogram như thế nào?
Bạn thiết kế chuỗi thu thập jcmd Thread.print tại nhiều thời điểm để phát hiện nghẽn luồng kéo dài như thế nào?
Bạn xác định những trường hợp nên dùng jcmd GC.heap_dump và những điều kiện phải kiểm tra trước khi tạo file dump ra sao?
Bạn xử lý việc jcmd báo không đủ quyền hoặc không thể ghi file dump trong container theo cách nào?
Bạn phân tích những rủi ro khi lưu heap dump trên filesystem có dung lượng giới hạn hoặc dùng chung với dữ liệu production như thế nào?
Bạn kiểm chứng rằng kết quả của jcmd thực sự thuộc đúng PID và đúng lần khởi động ứng dụng như thế nào?
Bạn giải thích kiến trúc JMX và vai trò của MBeanServer trong việc cung cấp dữ liệu quản trị JVM như thế nào?
Bạn phân biệt standard MBean, MXBean và các MBean do ứng dụng tự đăng ký trong hoạt động giám sát ra sao?
Bạn sử dụng MemoryMXBean để đọc mức sử dụng heap và non-heap tại runtime như thế nào?
Bạn dùng GarbageCollectorMXBean để theo dõi số lần thu gom và thời gian GC tích lũy theo từng collector ra sao?
Bạn lựa chọn dữ liệu từ ThreadMXBean để đánh giá số lượng thread, trạng thái và mức sử dụng CPU như thế nào?
Bạn xác định điều kiện cần để kích hoạt thread CPU time hoặc contention monitoring khi triển khai các phép đo qua JMX ra sao?
Bạn dùng ClassLoadingMXBean để điều tra tăng số lượng class đang được nạp và nghi vấn class loader leak như thế nào?
Bạn đánh giá những giới hạn của các chỉ số JMX được lấy theo chu kỳ khi cần giải thích sự cố rất ngắn như thế nào?
Bạn mô tả cách đăng ký một MBean nghiệp vụ chỉ cung cấp thông tin chẩn đoán mà không làm lộ secret ra sao?
Bạn lựa chọn JMX local connector hay remote connector theo yêu cầu truy cập và bảo mật vận hành như thế nào?
Bạn thiết kế cấu hình xác thực, TLS và kiểm soát mạng khi bắt buộc bật remote JMX như thế nào?
Bạn phân tích nguyên nhân remote JMX kết nối được vào cổng ban đầu nhưng thất bại ở bước RMI tiếp theo ra sao?
Bạn xác định các rủi ro bảo mật khi công khai remote JMX ra mạng không tin cậy như thế nào?
Bạn tổ chức phân quyền cho thao tác JMX chỉ đọc và thao tác có thể thay đổi trạng thái JVM ra sao?
Bạn so sánh dữ liệu từ JMX với metrics xuất qua Micrometer hoặc OpenTelemetry khi điều tra cùng một hiện tượng như thế nào?
Bạn giải thích các trạng thái NEW, RUNNABLE, BLOCKED, WAITING, TIMED_WAITING và TERMINATED trong thread dump như thế nào?
Bạn phân biệt thread ở RUNNABLE nhưng đang chờ I/O ở tầng native với thread đang thực sự tiêu thụ CPU ra sao?
Bạn đọc stack trace của một thread để xác định phương thức nghiệp vụ nào đang chờ khóa hoặc I/O như thế nào?
Bạn phân biệt việc chờ synchronized monitor với chờ ReentrantLock hoặc các synchronizer khác từ thông tin thread dump ra sao?
Bạn xác định thread nào đang sở hữu monitor khiến nhiều thread khác rơi vào trạng thái BLOCKED bằng cách nào?
Bạn phân tích các dấu hiệu deadlock giữa nhiều thread và cách xác minh vòng chờ bằng thông tin khóa như thế nào?
Bạn sử dụng ThreadMXBean hoặc công cụ chụp thread dump để phát hiện deadlock dựa trên monitor và ownable synchronizer ra sao?
Bạn so sánh một deadlock thực sự với tình trạng nhiều thread xếp hàng chờ cùng một lock được giữ lâu như thế nào?
Bạn phát hiện tình trạng thread starvation trong executor khi các tác vụ phải chờ nhau hoàn tất bằng dấu hiệu nào?
Bạn xác định sự khác nhau giữa WAITING do Object.wait, LockSupport.park và Future.get khi điều tra nghẽn như thế nào?
Bạn đọc nhiều thread dump cách nhau vài giây để phân biệt thread đang tiến triển với thread bị kẹt như thế nào?
Bạn lựa chọn khoảng cách và số mẫu thread dump để nhận diện sự cố không thường xuyên mà không tạo overhead quá lớn ra sao?
Bạn đối chiếu thread name với executor, request trace và tên tác vụ để xác định luồng nghiệp vụ gặp sự cố như thế nào?
Bạn ánh xạ native thread ID trong thread dump với luồng tiêu thụ CPU cao ở hệ điều hành theo những bước nào?
Bạn kết hợp mức CPU theo thread với stack trace để phân biệt vòng lặp tính toán và lock contention ra sao?
Bạn xác định tác động của số lượng platform thread tăng liên tục đến stack memory và tài nguyên hệ điều hành như thế nào?
Bạn điều tra dấu hiệu thread leak khi ứng dụng tạo executor mới nhưng không đóng các thread sau khi hoàn thành tác vụ ra sao?
Bạn phân biệt số lượng virtual thread lớn là hoạt động bình thường với tình trạng virtual thread bị giữ hoặc nghẽn ra sao?
Bạn lựa chọn JFR hay công cụ quan sát khác để phát hiện virtual thread pinning tùy theo phiên bản JDK như thế nào?
Bạn phân tích tình huống virtual thread chờ tài nguyên backend quá lâu mặc dù CPU JVM không cao ra sao?
Bạn xác định những giới hạn nào của thread dump thông thường khi phân tích scheduling và blocking của virtual thread?
Bạn kiểm tra độ đầy của queue executor và số thread bận để phân biệt nghẽn do thiếu worker với nghẽn I/O như thế nào?
Bạn xác định tác động của synchronized trong một đoạn mã nóng đến thông lượng dưới tải đồng thời bằng dữ liệu nào?
Bạn giải thích heap dump có thể trả lời những câu hỏi gì về object retention mà thread dump không thể trả lời ra sao?
Bạn phân biệt memory leak theo nghĩa object không còn hữu ích nhưng vẫn reachable với mức sử dụng heap tăng do tải hợp lệ như thế nào?
Bạn lựa chọn thời điểm chụp heap dump trước và sau một đợt tải để kiểm chứng giả thuyết rò rỉ bộ nhớ ra sao?
Bạn xác định cách bảo đảm đủ dung lượng đĩa và bộ nhớ phụ trợ trước khi tạo heap dump trên production như thế nào?
Bạn đánh giá nguy cơ heap dump chứa mật khẩu, token hoặc thông tin cá nhân và thiết kế quy trình bảo vệ file như thế nào?
Bạn phân biệt shallow size và retained size khi đánh giá mức độ ảnh hưởng của một đối tượng trong heap dump ra sao?
Bạn sử dụng dominator tree để tìm đối tượng hoặc collection đang giữ lại phần lớn heap như thế nào?
Bạn truy vết đường tham chiếu từ một object bị giữ đến GC root để xác định nguồn giữ bộ nhớ ra sao?
Bạn phân biệt object count lớn với retained size lớn khi quyết định vùng dữ liệu cần ưu tiên phân tích như thế nào?
Bạn phát hiện một cache không có chính sách giới hạn dung lượng từ heap dump và dấu vết sử dụng ứng dụng bằng cách nào?
Bạn điều tra rò rỉ liên quan đến ThreadLocal khi thread pool giữ các thread tồn tại lâu như thế nào?
Bạn kiểm chứng nghi vấn class loader leak khi Metaspace tăng sau mỗi lần tải lại plugin hoặc module ra sao?
Bạn phân tích ảnh hưởng của các listener, callback hoặc static collection giữ tham chiếu đến object đã hết vòng đời như thế nào?
Bạn sử dụng class histogram chụp nhiều lần để xác định kiểu đối tượng tăng bất thường trước khi phân tích heap dump ra sao?
Bạn đánh giá một lượng lớn String và byte array trong heap dump để phân biệt payload hợp lệ với dữ liệu bị giữ quá lâu như thế nào?
Bạn nhận diện object được giữ bởi hàng đợi message hoặc request đang chờ xử lý khi heap tăng theo tải như thế nào?
Bạn phân biệt heap usage sau GC với heap committed và RSS của tiến trình khi đọc biểu đồ bộ nhớ ra sao?
Bạn xác định trường hợp Java heap gần ổn định nhưng bộ nhớ native tăng mạnh cần thu thập thêm dữ liệu gì?
Bạn sử dụng Native Memory Tracking để phân tích các nhóm bộ nhớ ngoài heap mà HotSpot có thể báo cáo như thế nào?
Bạn kiểm tra điều kiện kích hoạt Native Memory Tracking và giới hạn của nó đối với những cấp phát không được theo dõi ra sao?
Bạn đánh giá đóng góp của direct ByteBuffer và memory-mapped file vào mức sử dụng bộ nhớ ngoài Java heap như thế nào?
Bạn phân biệt OutOfMemoryError: Java heap space với lỗi Metaspace, direct buffer hoặc không thể tạo native thread ra sao?
Bạn kiểm tra bằng chứng cho thấy container bị OOM killer kết thúc thay vì JVM tự ném OutOfMemoryError như thế nào?
Bạn thiết kế quy trình thu thập dump tự động khi xảy ra OutOfMemoryError mà vẫn kiểm soát dung lượng và dữ liệu nhạy cảm ra sao?
Bạn giải thích những thông tin cần đọc trong GC log để đánh giá tần suất, nguyên nhân và thời lượng của các lần thu gom như thế nào?
Bạn thiết kế cấu hình unified GC logging kèm timestamp, rotation và dung lượng giới hạn cho ứng dụng Java ra sao?
Bạn phân biệt allocation rate, live set và promotion rate khi giải thích áp lực garbage collection như thế nào?
Bạn so sánh GC pause time với tổng thời gian thu gom đồng thời để đánh giá ảnh hưởng thực sự đến request latency ra sao?
Bạn phân tích dấu hiệu heap tăng nhanh nhưng giảm sâu sau GC để xác định khả năng cấp phát lớn thay vì memory leak như thế nào?
Bạn xác định thời điểm GC overhead tăng do thiếu heap hay do quá nhiều object được giữ sống bằng những chỉ số nào?
Bạn đối chiếu GC log và p99 latency để chứng minh một đợt dừng JVM ảnh hưởng đến request như thế nào?
Bạn đánh giá nguyên nhân một ứng dụng có GC pause ngắn nhưng tail latency vẫn cao dựa trên dữ liệu nào?
Bạn phân biệt hiện tượng allocation stall với stop-the-world pause trong một collector hỗ trợ thu gom đồng thời ra sao?
Bạn điều tra full GC lặp lại trong G1 dựa trên heap occupancy, humongous allocation và khả năng thu hồi region như thế nào?
Bạn đọc các chỉ số liên quan đến remembered set và concurrent marking của G1 để giải thích chi phí GC ra sao?
Bạn xác định những dấu hiệu cho thấy cấu hình heap hoặc GC threads không phù hợp giới hạn CPU của container như thế nào?
Bạn so sánh xu hướng GC logs trước và sau thay đổi Xmx để đánh giá điều chỉnh có giải quyết nguyên nhân hay chỉ trì hoãn lỗi ra sao?
Bạn phân biệt safepoint pause với GC pause khi phân tích các khoảng dừng phản hồi của ứng dụng như thế nào?
Bạn sử dụng dữ liệu từ jcmd hoặc JFR để điều tra vấn đề safepoint kéo dài mà GC log không giải thích đầy đủ ra sao?
Bạn giải thích mục tiêu của Java Flight Recorder và sự khác biệt giữa ghi sự kiện JVM với log ứng dụng như thế nào?
Bạn quyết định khi nào dùng cấu hình JFR mặc định và khi nào cần cấu hình profiling chi tiết dựa trên giới hạn overhead ra sao?
Bạn khởi tạo một phiên JFR cho JVM đang chạy bằng jcmd và xác định thời lượng ghi phù hợp như thế nào?
Bạn kiểm tra phiên ghi JFR đang hoạt động và xuất dữ liệu ra file để phân tích sau sự cố ra sao?
Bạn đánh giá ảnh hưởng của sampling interval, stack depth và số nhóm sự kiện được bật đến overhead JFR như thế nào?
Bạn lựa chọn các sự kiện JFR nào để phân tích CPU execution, object allocation và lock contention, và vì sao?
Bạn sử dụng các sự kiện Thread Park và Java Monitor Enter để phân biệt thread chờ đồng bộ với thread đang xử lý công việc như thế nào?
Bạn phân tích sự kiện Socket Read hoặc File Read trong JFR để tìm các lời gọi I/O chậm như thế nào?
Bạn dùng JFR để xác định những đoạn mã có allocation rate cao dù chúng không tạo ra object được giữ lâu ra sao?
Bạn phân biệt allocation sampling với đếm đầy đủ từng lần cấp phát để tránh suy luận sai từ số liệu JFR như thế nào?
Bạn phân tích các sự kiện GC, safepoint và CPU load trong cùng một bản ghi JFR để dựng lại diễn biến sự cố ra sao?
Bạn sử dụng Java Mission Control để tìm các call stack tiêu thụ CPU lớn và kiểm tra chúng theo mốc thời gian như thế nào?
Bạn tổ chức ghi JFR theo kiểu vòng đệm và giữ lại khoảng thời gian trước sự cố để giảm nhu cầu tái hiện lỗi như thế nào?
Bạn xác định cách đặt tên, lưu trữ và giới hạn thời gian giữ file JFR khi triển khai cho nhiều JVM như thế nào?
Bạn kiểm tra khả năng ghi JFR khi JVM đang chịu tải nặng và file đích nằm trên storage chậm như thế nào?
Bạn lựa chọn giữa JFR, sampling profiler và thread dump khi nghi ngờ CPU bận trong một phương thức Java như thế nào?
Bạn kết hợp CPU flame graph với call tree trong JFR để phân biệt chi phí trực tiếp và chi phí tích lũy của phương thức ra sao?
Bạn xác định những tình huống profiler bỏ sót công việc native hoặc kernel và ảnh hưởng của chúng đến kết luận CPU ra sao?
Bạn dùng dữ liệu hệ điều hành để phân biệt tiến trình bị CPU throttling với tiến trình thực sự tiêu thụ toàn bộ CPU được cấp như thế nào?
Bạn xác định dấu hiệu busy loop so với một tác vụ tính toán hợp lệ khi CPU gần 100% trên một core ra sao?
Bạn thiết kế kế hoạch lấy mẫu khi CPU spike chỉ kéo dài vài giây và khó chụp thread dump đúng thời điểm như thế nào?
Bạn phân biệt thread đang chờ network I/O với thread bị nghẽn ở connection pool dựa trên stack trace và metrics như thế nào?
Bạn kết hợp số lượng kết nối đang sử dụng, thời gian chờ pool và thread dump để điều tra độ trễ JDBC như thế nào?
Bạn phân tích dấu hiệu DNS lookup kéo dài hoặc TLS handshake treo trong lời gọi HTTP client bằng dữ liệu nào?
Bạn xác định cách phân biệt socket timeout do backend không phản hồi với request queueing trong ứng dụng như thế nào?
Bạn điều tra tình trạng nhiều thread chờ Future.get khi tác vụ phụ thuộc đã bị kẹt ở downstream service ra sao?
Bạn phối hợp log có correlation ID với JFR và thread dump để truy vết một request chậm xuyên qua các tầng xử lý như thế nào?
Bạn kiểm chứng giả thuyết lỗi I/O gây tăng heap do request backlog trước khi quyết định tăng Xmx như thế nào?
Bạn xây dựng dashboard kết hợp heap usage, GC pause, thread count, CPU và I/O latency để phát hiện bất thường sớm ra sao?
Bạn thiết lập ngưỡng cảnh báo dựa trên baseline của từng workload thay vì áp một ngưỡng JVM cố định cho mọi dịch vụ như thế nào?
Bạn phân loại những bằng chứng cần thu thập trước restart và những dữ liệu có thể bổ sung sau khi dịch vụ phục hồi dựa trên tiêu chí nào?
Bạn thiết kế runbook yêu cầu xác nhận phạm vi ảnh hưởng và rủi ro trước khi thực thi lệnh jcmd tạo heap dump như thế nào?
Bạn kiểm soát quyền truy cập jcmd, remote JMX, heap dump và JFR trong một hệ thống nhiều nhóm vận hành như thế nào?
Bạn thiết kế quy trình mã hóa, chuyển giao và xóa an toàn các file dump có thể chứa dữ liệu sản xuất như thế nào?
Bạn xác định thông tin cần ẩn khi chia sẻ thread dump hoặc JFR với bên thứ ba để không tiết lộ endpoint và thông tin nội bộ ra sao?
Bạn lựa chọn phương pháp chẩn đoán ít xâm lấn khi một JVM đang ở trạng thái gần cạn CPU hoặc dung lượng đĩa như thế nào?
Bạn so sánh dấu hiệu JVM crash do lỗi native với trường hợp ứng dụng chủ động thoát bằng mã trạng thái lỗi như thế nào?
Bạn đọc các phần quan trọng của file hs_err_pid để xác định thread gây crash, native frame và thông tin runtime ra sao?
Bạn phân biệt sự cố Java exception thông thường với fatal error khiến JVM tạo crash report như thế nào?
Bạn xác định khi nào core dump ở cấp hệ điều hành cần thiết để điều tra vấn đề native mà heap dump không thể giải thích ra sao?
Bạn đánh giá giới hạn của việc phân tích core dump so với thread dump trong tình huống runtime đã kết thúc như thế nào?
Bạn xây dựng quy trình so sánh dữ liệu chẩn đoán trước và sau khi triển khai bản sửa để xác nhận nguyên nhân gốc như thế nào?
Bạn kiểm tra nguy cơ thay đổi JVM flags hoặc kích hoạt profiling đã tự làm thay đổi thời gian thực thi của ứng dụng ra sao?
Một API có p99 latency tăng mạnh nhưng CPU và heap vẫn thấp, bạn sẽ dùng thread dump và JFR để điều tra nghẽn nào?
Một service dùng CPU cao liên tục sau khi triển khai phiên bản mới, bạn sẽ đối chiếu OS thread ID, thread dump và JFR như thế nào?
Một ứng dụng có hàng nghìn thread ở WAITING nhưng throughput bình thường, bạn sẽ tránh kết luận sai về thread starvation ra sao?
Một dịch vụ xuất hiện nhiều thread BLOCKED trên cùng một monitor, bạn sẽ xác minh chủ khóa và đoạn mã gây contention như thế nào?
Heap usage tăng sau mỗi giờ nhưng giảm rất ít sau full GC, bạn sẽ dùng histogram và dominator tree để kiểm tra nghi vấn nào?
Một container bị OOMKilled dù -Xmx thấp hơn giới hạn memory, bạn sẽ điều tra native memory và thread stacks như thế nào?
Sau khi tăng heap, thời gian full GC tăng nhưng lỗi OOM không biến mất, bạn sẽ xem lại bằng chứng về object retention ra sao?
Một ứng dụng có tốc độ cấp phát object tăng nhưng retained heap không tăng, bạn sẽ chọn dữ liệu JFR và GC nào để phân tích?
Một Java process thỉnh thoảng treo trong vài chục giây nhưng không có GC pause tương ứng, bạn sẽ điều tra safepoint và I/O như thế nào?
Một hệ thống dùng remote JMX hoạt động ở máy local nhưng không kết nối được qua Kubernetes Service, bạn sẽ kiểm tra địa chỉ RMI và chính sách mạng ra sao?
Một file JFR không ghi lại được thời điểm xảy ra CPU spike, bạn sẽ điều chỉnh lịch ghi và cấu hình sự kiện như thế nào?
Một ứng dụng tăng số thread theo mỗi request và dần không tạo được thread mới, bạn sẽ xác định nguồn tạo thread và cách chứng minh leak ra sao?
Khi thread dump cho thấy nhiều thread chờ JDBC connection, bạn sẽ kiểm tra pool saturation và truy vấn chậm như thế nào?
Sau khi một bản vá được triển khai, bạn sẽ chọn những tiêu chí nào từ GC log, JFR, thread dump và metrics để xác nhận sự cố đã được giải quyết?

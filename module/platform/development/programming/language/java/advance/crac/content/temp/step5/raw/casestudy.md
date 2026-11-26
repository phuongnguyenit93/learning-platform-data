Một dịch vụ Spring Boot đã khởi động đầy đủ trong môi trường chuẩn bị nhưng sau khi restore từ checkpoint lại mất kết nối cơ sở dữ liệu; hãy xây dựng tình huống xác định các tài nguyên phải kiểm tra ở hai thời điểm.
Một nhóm muốn tạo checkpoint ngay sau khi JVM khởi động nhưng trước khi tải cấu hình nghiệp vụ, khiến thời gian restore chưa đáp ứng kỳ vọng; hãy đặt bài toán xác định mốc checkpoint phù hợp với mục tiêu khởi động.
Một ứng dụng xử lý đơn hàng có tác vụ đang ghi cơ sở dữ liệu đúng lúc yêu cầu checkpoint xuất hiện, dẫn đến trạng thái dữ liệu khó xác định khi restore; hãy xây dựng tình huống kiểm chứng tính nhất quán giao dịch.
Một service Java đăng ký nhiều tài nguyên CRaC nhưng callback chuẩn bị checkpoint của một thành phần thất bại, khiến ảnh trạng thái không được tạo; hãy đặt tình huống đánh giá tác động đến các thành phần còn lại.
Một hệ thống có resource dùng chung giữa nhiều thư viện, trong đó hai callback beforeCheckpoint giả định thứ tự thực thi trái ngược nhau; hãy xây dựng tình huống xác minh phụ thuộc vòng đời.
Một ứng dụng đã đóng pool kết nối trong giai đoạn chuẩn bị checkpoint nhưng gặp lỗi trước khi checkpoint hoàn thành, khiến tiến trình còn sống không thể phục vụ request; hãy đặt tình huống kiểm tra đường thất bại.
Một JVM restore thành công nhưng health check báo sẵn sàng trước khi callback afterRestore khôi phục xong các kết nối bên ngoài; hãy xây dựng tình huống kiểm chứng điều kiện nhận lưu lượng.
Một service lưu cờ initialized trong singleton trước checkpoint và dùng cờ này để bỏ qua bước khởi tạo sau restore, khiến tài nguyên môi trường mới không được mở; hãy đặt tình huống kiểm tra trạng thái nội bộ.
Một ứng dụng đăng ký callback CRaC cho nhiều bean nhưng một bean được khởi tạo muộn sau thời điểm checkpoint, khiến thành phần đó không được xử lý như mong đợi; hãy đặt bài toán kiểm chứng thời điểm đăng ký.
Một thư viện bên thứ ba giữ tài nguyên hệ điều hành nhưng không cung cấp callback cho CRaC, khiến checkpoint của toàn JVM bị từ chối; hãy xây dựng tình huống điều tra tài nguyên không tương thích.
Một ứng dụng hỗ trợ hai chế độ khởi động thường và khôi phục CRaC nhưng luồng restore vô tình chạy lại bước tạo dữ liệu mẫu chỉ dành cho khởi động lần đầu; hãy đặt tình huống kiểm chứng tính idempotent.
Một service khởi tạo cache rất tốn thời gian trước khi lưu checkpoint, nhưng dữ liệu cache này chỉ hợp lệ trong vài phút; hãy xây dựng tình huống xác định giá trị và độ mới của snapshot.
Một chương trình xử lý tác vụ theo lịch tạo checkpoint vào thời điểm hàng đợi còn nhiều công việc, rồi restore trên nhiều instance và cùng thực thi các tác vụ đã giữ; hãy đặt tình huống kiểm chứng xử lý trùng.
Một hệ thống ghi lại trạng thái tiến độ xử lý trong bộ nhớ trước checkpoint nhưng offset đã được commit ra message broker ở thời điểm khác; hãy xây dựng tình huống đánh giá khả năng xử lý lặp hoặc bỏ sót.
Một thư viện sử dụng native thread riêng và báo tiến trình chưa thể checkpoint dù các Java thread đã ở trạng thái chờ; hãy đặt bài toán xác minh các thành phần ngoài Java heap.
Một dịch vụ dùng callback CRaC để tạm dừng tiếp nhận request nhưng request đang xử lý kéo dài hơn thời hạn checkpoint cho phép; hãy xây dựng tình huống kiểm tra cách chuyển sang trạng thái an toàn.
Một tiến trình Java có nhiều tài nguyên phụ thuộc nhau và cần phục hồi theo trình tự sau restore, nhưng một thành phần được sử dụng trước khi tài nguyên nền sẵn sàng; hãy đặt tình huống đánh giá thứ tự callback.
Một nhóm muốn tạo checkpoint ngay trong môi trường production khi còn request người dùng, trong khi quy trình thử nghiệm trước đó chỉ thực hiện trên instance chưa nhận tải; hãy xây dựng bài toán kiểm chứng điều kiện an toàn.
Một ứng dụng cần phân biệt thao tác chuẩn bị trước checkpoint với thao tác khởi tạo sau restore nhưng đội phát triển đặt toàn bộ logic trong constructor; hãy đặt tình huống đánh giá giới hạn thiết kế.
Một ứng dụng có singleton ghi nhận số lần khởi động JVM, nhưng sau restore thông số vẫn phản ánh tiến trình đã khởi tạo ảnh checkpoint chứ không phản ánh instance mới; hãy xây dựng tình huống xác minh ngữ nghĩa trạng thái.
Một hệ thống chạy Java trên Windows khi phát triển nhưng cần checkpoint trong Linux container khi triển khai, khiến quy trình tạo ảnh không thể sao chép trực tiếp; hãy đặt bài toán đánh giá giới hạn hệ điều hành.
Một nhóm tạo ảnh checkpoint với bản JDK hỗ trợ CRaC ở môi trường build nhưng chạy restore bằng một bản phân phối JDK khác tại production; hãy xây dựng tình huống kiểm chứng tương thích runtime.
Một ứng dụng được checkpoint trên một kiểu kiến trúc CPU nhưng đội triển khai dự định phục hồi ảnh trên máy có kiến trúc khác; hãy đặt tình huống đánh giá tính di động của ảnh JVM.
Một container chứa ảnh checkpoint được tạo với thư viện native khác phiên bản so với container chạy restore, khiến tiến trình khôi phục không ổn định; hãy xây dựng tình huống kiểm tra tính đồng nhất thư viện.
Một nhóm đổi base image Linux sau khi tạo checkpoint và chỉ giữ lại thư mục ảnh JVM cũ, khiến restore gặp lỗi phụ thuộc môi trường; hãy đặt bài toán xác định những thành phần phải kiểm chứng.
Một ứng dụng tạo checkpoint trong môi trường có quyền hệ thống cao nhưng chạy restore trong Pod hạn chế capability, khiến các thao tác hệ điều hành bị từ chối; hãy xây dựng tình huống đánh giá quyền tối thiểu.
Một pipeline tạo checkpoint bên trong container nhưng hạ tầng không hỗ trợ thao tác cần thiết từ kernel, khiến công đoạn build image thất bại dù ứng dụng Java bình thường vẫn chạy; hãy đặt tình huống chẩn đoán.
Một hệ thống Kubernetes triển khai nhiều node với kernel và runtime container khác nhau, trong khi ảnh CRaC chỉ được thử trên một node; hãy xây dựng tình huống xác định ma trận tương thích.
Một ứng dụng sử dụng volume tạm ở đường dẫn chỉ tồn tại trong Pod tạo checkpoint, nhưng restore sang Pod mới không còn đường dẫn đó; hãy đặt bài toán kiểm tra phụ thuộc filesystem.
Một nhóm lưu ảnh checkpoint trong layer container và phát hiện dung lượng image tăng vượt giới hạn registry, làm thời gian kéo ảnh lâu hơn thời gian khởi động tiết kiệm được; hãy xây dựng tình huống đánh giá chi phí.
Một đội vận hành muốn dùng một ảnh checkpoint trên nhiều khu vực địa lý nhưng mỗi khu vực có hostname, vùng thời gian và endpoint khác nhau; hãy đặt tình huống kiểm tra dữ liệu phụ thuộc môi trường.
Một cluster dùng cơ chế phân phối checkpoint qua object storage, nhưng ảnh bị tải chưa hoàn chỉnh trước khi restore và lỗi chỉ xuất hiện ngẫu nhiên; hãy xây dựng bài toán kiểm chứng tính toàn vẹn artifact.
Một pipeline đóng gói ảnh CRaC sau mỗi lần thay dependency nhưng không thay đổi nhãn phiên bản artifact, khiến các Pod nhận ảnh của lần build trước; hãy đặt tình huống kiểm tra truy vết ảnh.
Một nền tảng chạy ứng dụng bằng autoscaling muốn dùng checkpoint chung cho nhiều replica nhưng mỗi replica cần danh tính và cấu hình riêng; hãy xây dựng tình huống kiểm chứng dữ liệu được mang sang restore.
Một nhóm thêm Java agent theo dõi hiệu năng vào môi trường production sau khi tạo checkpoint ở CI, khiến quá trình phục hồi không còn phản ánh cùng trạng thái JVM; hãy đặt tình huống đánh giá tương thích agent.
Một service dùng JNI để truy cập thư viện nén và lưu con trỏ native trong đối tượng Java, nhưng sau restore hoạt động xử lý dữ liệu bị lỗi; hãy xây dựng tình huống kiểm chứng vòng đời native resource.
Một ứng dụng có bộ thư viện mã hóa native chỉ khởi tạo một lần trong quá trình checkpoint, nhưng môi trường restore cần thiết lập lại một số ngữ cảnh hệ điều hành; hãy đặt bài toán đánh giá an toàn tài nguyên.
Một chương trình Java dùng file mapping bộ nhớ để tra cứu dữ liệu, nhưng tệp đã bị thay đổi giữa checkpoint và restore; hãy xây dựng tình huống kiểm tra tính hợp lệ của vùng nhớ ánh xạ.
Một dịch vụ Java giữ socket TCP tới cơ sở dữ liệu khi checkpoint, nhưng địa chỉ và trạng thái mạng của bản restore khác với tiến trình tạo ảnh; hãy đặt tình huống xác định điểm đứt kết nối.
Một ứng dụng vẫn giữ HTTP keep-alive connection tới dịch vụ bên ngoài trong thời gian đóng băng, rồi tái sử dụng kết nối đã bị server đóng; hãy xây dựng tình huống kiểm tra request đầu tiên sau restore.
Một hệ thống dùng connection pool HikariCP và sau restore nhiều kết nối trong pool không còn hoạt động, nhưng phép kiểm tra khởi động chỉ xác nhận bean đã tồn tại; hãy đặt tình huống kiểm chứng khả năng truy vấn.
Một dịch vụ dùng Redis connection pool để giữ session, nhưng endpoint Redis đổi địa chỉ trong giai đoạn lưu checkpoint; hãy xây dựng tình huống đánh giá khả năng kết nối đúng môi trường.
Một client Kafka đã tham gia consumer group trước checkpoint, nhưng khi restore group đã cân bằng lại và assignment cũ không còn hợp lệ; hãy xây dựng tình huống kiểm tra trạng thái consumer.
Một producer Kafka dùng bộ nhớ đệm bản ghi đang chờ xác nhận lúc checkpoint, rồi sau restore không xác định được bản ghi nào đã gửi thành công; hãy đặt tình huống đánh giá trùng lặp thông điệp.
Một RabbitMQ consumer đang giữ thông điệp chưa ack lúc checkpoint, khiến broker giao lại thông điệp trong thời gian tiến trình bị đóng băng; hãy xây dựng tình huống kiểm chứng xử lý lại.
Một ứng dụng duy trì WebSocket với khách hàng trong lúc checkpoint, rồi restore instance mới nhưng trạng thái phiên trong heap vẫn xem kết nối là đang mở; hãy đặt bài toán kiểm thử phiên realtime.
Một server gRPC có luồng streaming lâu dài khi chuẩn bị checkpoint, khiến file descriptor mạng vẫn còn hoạt động; hãy xây dựng tình huống xác định các kết nối cần kết thúc.
Một ứng dụng dùng Java NIO Selector quản lý hàng nghìn socket và sau restore vòng lặp sự kiện không nhận thông báo như trước; hãy đặt tình huống kiểm tra tài nguyên hệ điều hành gắn với selector.
Một service sử dụng HTTP client bất đồng bộ, nhưng callback sau restore xử lý phản hồi của request gửi từ trước khi checkpoint; hãy xây dựng tình huống đánh giá vòng đời request.
Một hệ thống lưu DNS cache trong JVM trước checkpoint rồi restore ở VPC có địa chỉ DNS khác, khiến các request vẫn trỏ tới dịch vụ cũ; hãy đặt bài toán kiểm chứng dữ liệu định tuyến.
Một ứng dụng chạy sau service mesh dùng proxy sidecar, nhưng sau restore proxy khởi động chậm hơn client Java khiến request đầu tiên thất bại; hãy xây dựng tình huống kiểm tra thứ tự sẵn sàng.
Một client kết nối tới MongoDB đã khám phá topology cụm trước checkpoint, nhưng sau restore cụm đổi primary và thông tin topology trong heap không còn đúng; hãy đặt tình huống kiểm chứng khả năng tự phục hồi.
Một ứng dụng cần mở file log trong container mới sau restore nhưng logger vẫn tham chiếu file descriptor từ môi trường tạo checkpoint; hãy xây dựng tình huống xác minh đường ghi log.
Một service đang giữ file tạm trong thư mục hệ thống khi checkpoint, nhưng thư mục bị dọn trong container restore và thao tác ghi tiếp không báo lỗi rõ ràng; hãy đặt tình huống kiểm tra tính tồn tại tệp.
Một ứng dụng đọc file cấu hình thông qua FileChannel mở sẵn, sau đó người vận hành đổi file giữa checkpoint và restore; hãy xây dựng bài toán kiểm tra tính mới của cấu hình.
Một tiến trình đã chiếm file lock trước checkpoint nhưng khi restore ở host khác giả định lock cũ vẫn có hiệu lực; hãy đặt tình huống đánh giá quyền sở hữu khóa hệ điều hành.
Một JVM ghi vào memory-mapped file dùng chung với tiến trình khác, trong khi dữ liệu thực tế đã thay đổi khi JVM bị đóng băng; hãy xây dựng tình huống kiểm tra tính nhất quán sau restore.
Một ứng dụng gọi một tiến trình con bên ngoài JVM để xử lý ảnh rồi tạo checkpoint, nhưng tiến trình con không còn cùng vòng đời khi khôi phục container; hãy đặt tình huống đánh giá sự phụ thuộc.
Một service lưu PID tiến trình của chính nó trong file trạng thái và dùng lại giá trị này để quản lý tín hiệu sau restore, khiến thao tác điều khiển sai tiến trình; hãy xây dựng tình huống xác minh định danh runtime.
Một ứng dụng dùng tên host làm khóa đăng ký service và tên host của Pod đã thay đổi sau restore, nhưng registry vẫn giữ đăng ký cũ; hãy xây dựng tình huống kiểm chứng cập nhật định danh.
Một dịch vụ giữ địa chỉ IP của interface mạng trong singleton từ trước checkpoint, rồi restore trên node khác làm thông tin công bố dịch vụ sai; hãy đặt tình huống kiểm tra thuộc tính máy chủ.
Một client dùng TLS session được khởi tạo trước checkpoint nhưng backend đã luân chuyển chứng chỉ trong thời gian đóng băng; hãy xây dựng bài toán kiểm chứng lần bắt tay và truststore sau restore.
Một ứng dụng dùng certificate file từ volume gắn vào container và sau restore file đã được cập nhật, nhưng SSLContext vẫn sử dụng chứng chỉ đã nạp trong heap; hãy đặt tình huống đánh giá rotation.
Một service phục vụ HTTPS bằng private key giữ trong bộ nhớ tại thời điểm checkpoint, rồi ảnh được phân phối tới nhiều máy ở môi trường khác nhau; hãy xây dựng tình huống kiểm tra phạm vi lộ vật liệu khóa.
Một ứng dụng tạo checkpoint sau khi đăng nhập Vault và lưu token còn hiệu lực trong heap, nhưng bản restore được triển khai cho một workload có quyền khác; hãy đặt tình huống đánh giá danh tính và đặc quyền.
Một client OAuth2 có access token được nạp vào bộ nhớ trước checkpoint và hết hạn trong lúc chờ restore, khiến request đầu tiên sau phục hồi bị trả 401; hãy đặt tình huống kiểm tra vòng đời token.
Một service tạo checkpoint sau khi đã nhận refresh token của người dùng thử nghiệm, rồi phát hành ảnh đó sang production; hãy xây dựng tình huống đánh giá dữ liệu người dùng không được có trong snapshot.
Một ứng dụng lưu mật khẩu cơ sở dữ liệu trong đối tượng cấu hình trước checkpoint, nhưng đội vận hành luân chuyển mật khẩu sau khi tạo ảnh; hãy đặt bài toán kiểm tra credential tại restore.
Một hệ thống dùng mTLS để kết nối dịch vụ phụ trợ và chứng chỉ máy khách có thời hạn ngắn, nhưng thời điểm restore diễn ra sau hạn chứng chỉ; hãy xây dựng tình huống kiểm chứng xử lý chứng chỉ hết hạn.
Một ứng dụng lưu session đăng nhập người dùng trong bộ nhớ tại checkpoint, khiến nhiều replica mới được restore với cùng trạng thái phiên; hãy đặt tình huống đánh giá tính riêng tư và cô lập.
Một module dùng SecureRandom đã được khởi tạo trước checkpoint, và các replica mới cùng phục hồi trạng thái bộ sinh số ngẫu nhiên; hãy xây dựng tình huống kiểm tra nguy cơ lặp dữ liệu mật mã.
Một dịch vụ tạo UUID dựa trên bộ đếm trong heap trước checkpoint, khiến nhiều instance restore từ cùng ảnh sinh ID trùng nhau khi nhận tải; hãy xây dựng tình huống kiểm chứng tính duy nhất.
Một ứng dụng sử dụng bộ sinh khóa phiên được cache trong singleton, rồi restore trên nhiều Pod với cùng giá trị đã giữ; hãy đặt bài toán đánh giá phạm vi và vòng đời khóa tạm.
Một nhóm phân phối ảnh checkpoint qua registry container nhưng không giới hạn quyền đọc như đối với secret, dù ảnh chứa trạng thái JVM đã khởi tạo; hãy xây dựng tình huống đánh giá bảo mật artifact.
Một đội vận hành lưu checkpoint vào volume dùng chung và người dùng hệ thống khác có thể đọc file ảnh, trong khi heap chứa thông tin xác thực; hãy đặt tình huống kiểm tra quyền truy cập tệp.
Một pipeline tạo checkpoint trên máy build có biến môi trường chứa token CI, và sau restore biến đó vẫn hiện diện trong cấu hình đã nạp; hãy xây dựng tình huống đánh giá rò rỉ giữa môi trường.
Một ứng dụng log toàn bộ môi trường lúc afterRestore để chẩn đoán lỗi, khiến giá trị secret được đưa vào hệ thống tập trung; hãy đặt bài toán kiểm tra dữ liệu trong nhật ký.
Một service lưu kết quả kiểm tra quyền người dùng trong cache tại checkpoint, rồi restore sau khi chính sách phân quyền thay đổi; hãy xây dựng tình huống kiểm chứng cập nhật trạng thái bảo mật.
Một ứng dụng đọc danh sách tenant được phép trong giai đoạn tạo ảnh, nhưng restore ở môi trường có tập tenant khác; hãy đặt tình huống đánh giá nguy cơ truy cập chéo tenant.
Một tiến trình lập lịch dùng thời gian tuyệt đối đã tính trước checkpoint, khiến hàng loạt tác vụ hết hạn kích hoạt ngay khi restore sau nhiều giờ; hãy xây dựng tình huống kiểm chứng lịch chạy.
Một ứng dụng kiểm tra TTL cache bằng thời gian monotonic, nhưng các phép đo khoảng thời gian sau restore khác với giả định trước checkpoint; hãy đặt tình huống đánh giá đồng hồ trong quá trình đóng băng.
Một service tạo token có hạn dùng tính theo Instant trước khi checkpoint và tiếp tục sử dụng sau restore, khiến token phát ra đã hết hạn; hãy xây dựng tình huống kiểm tra các giá trị thời gian lưu trong heap.
Một chương trình dùng ScheduledExecutorService để làm mới dữ liệu mỗi phút, nhưng sau restore nhiều tác vụ quá hạn chạy gần như cùng lúc; hãy đặt tình huống đánh giá tác động tăng tải.
Một ứng dụng dùng cron theo múi giờ của host tạo ảnh, nhưng bản restore chạy ở khu vực địa lý có múi giờ khác; hãy đặt bài toán kiểm tra lịch nghiệp vụ theo môi trường.
Một hệ thống tính hạn thanh toán trong bộ nhớ trước checkpoint nhưng restore vào ngày mới, khiến màn hình vẫn hiển thị số ngày còn lại cũ; hãy xây dựng tình huống kiểm tra dữ liệu dẫn xuất.
Một ứng dụng đo thời gian xử lý bằng đồng hồ bắt đầu trước checkpoint và kết thúc sau restore, khiến báo cáo latency phình to bất thường; hãy đặt tình huống kiểm chứng ranh giới phép đo.
Một thư viện cache dùng TTL khởi tạo khi JVM nóng, nhưng checkpoint được lưu hàng tuần trước khi instance mới được restore; hãy xây dựng tình huống đánh giá độ cũ dữ liệu ngay sau khôi phục.
Một dịch vụ giữ kết quả khám phá dịch vụ trong cache với thời hạn ngắn nhưng server đích đã đổi topology trong thời gian ảnh được lưu; hãy đặt tình huống kiểm tra cơ chế làm mới.
Một hệ thống dùng circuit breaker với trạng thái mở ở lúc checkpoint do backend lỗi tạm thời, rồi restore khi backend đã phục hồi nhưng vẫn từ chối request; hãy xây dựng tình huống đánh giá trạng thái điều khiển.
Một ứng dụng đã tích lũy thống kê rate limiter trước checkpoint và phát hành hàng chục instance từ cùng ảnh, khiến mỗi instance bắt đầu với lượng quota không phù hợp; hãy đặt tình huống kiểm chứng trạng thái giới hạn.
Một dịch vụ giữ local cache phân quyền theo người dùng nhưng phục hồi vào thời điểm danh sách vai trò đã thay đổi, khiến request đầu tiên có quyết định sai; hãy xây dựng tình huống đánh giá yêu cầu refresh.
Một ứng dụng dùng thread pool cố định và đóng băng lúc các worker đang chờ trên hàng đợi nội bộ, nhưng sau restore hàng đợi chứa tác vụ đã không còn hợp lệ; hãy đặt tình huống kiểm chứng trạng thái tác vụ.
Một chương trình đang thực thi virtual thread có thao tác I/O khi checkpoint, nhưng cơ chế khôi phục tài nguyên của thư viện chưa được kiểm chứng; hãy đặt tình huống đánh giá các điểm chờ và tiến trình.
Một dịch vụ dùng CompletableFuture có callback chờ phản hồi bên ngoài, rồi restore khi request gốc đã timeout trên server; hãy xây dựng tình huống kiểm tra kết quả bất đồng bộ còn treo.
Một ứng dụng dùng ThreadLocal để giữ tenant của request gần nhất và tạo checkpoint ngay sau xử lý, khiến instance mới có nguy cơ dùng dữ liệu ngữ cảnh cũ; hãy đặt tình huống kiểm chứng cô lập request.
Một chương trình sử dụng executor dành cho kiểm tra health và executor dành cho nghiệp vụ, nhưng callback CRaC vô tình dừng cả hai khiến quá trình restore không thể tự báo sẵn sàng; hãy xây dựng tình huống đánh giá phụ thuộc.
Một service sử dụng JMX để xuất metric và agent giám sát giữ kết nối từ lúc tạo checkpoint, nhưng endpoint JMX sau restore không truy cập được; hãy đặt tình huống kiểm thử quan sát JVM.
Một ứng dụng khởi tạo telemetry exporter trước checkpoint và giữ kết nối HTTP tới hệ thống trace cũ, khiến span của bản restore không được gửi đi; hãy xây dựng tình huống kiểm tra vòng đời exporter.
Một chương trình tạo thread nền để cập nhật dữ liệu tham chiếu nhưng thread bị tạm dừng ở checkpoint và sau restore không còn thực hiện chu kỳ cập nhật; hãy đặt tình huống kiểm chứng khôi phục scheduler.
Một service dùng cơ chế khóa trong bộ nhớ để tránh xử lý lặp khi checkpoint, nhưng restore nhiều replica từ cùng ảnh khiến mỗi replica tin mình đang giữ khóa; hãy đặt tình huống đánh giá phối hợp phân tán.
Một ứng dụng giữ cấu hình feature flag đã đọc trước checkpoint, nhưng nhóm vận hành bật tính năng mới ngay trước khi khôi phục Pod; hãy đặt tình huống kiểm chứng thời điểm cập nhật cấu hình.
Một service khởi tạo Spring ApplicationContext trước khi tạo ảnh, nhưng các bean có logic lấy cấu hình từ môi trường mới chỉ được chạy khi khởi tạo lần đầu; hãy xây dựng tình huống kiểm tra hành vi restore.
Một ứng dụng Spring sử dụng @PostConstruct để mở kết nối Redis và @PreDestroy để đóng kết nối, nhưng restore không có vòng đời bean tương đương lần khởi động mới; hãy đặt bài toán đánh giá điểm quản lý tài nguyên.
Một dự án khởi tạo Flyway migration trước checkpoint, rồi triển khai bản restore vào cơ sở dữ liệu đã đổi schema mà tiến trình không chạy lại migration; hãy xây dựng tình huống kiểm chứng tương thích.
Một service chạy Hibernate có metadata ánh xạ được khởi tạo trước checkpoint, nhưng sau restore ứng dụng kết nối đến cơ sở dữ liệu khác version; hãy đặt tình huống đánh giá tính phù hợp của trạng thái ORM.
Một hệ thống dùng client HTTP có resolver và pool được cấu hình từ properties trước checkpoint, nhưng biến môi trường tại restore đổi proxy và timeout; hãy xây dựng tình huống kiểm tra cấu hình hiệu lực.
Một ứng dụng thiết lập hostname cho log ở startup và giữ giá trị này trong MDC hoặc logger, rồi khôi phục trên Pod khác với định danh mới; hãy đặt tình huống đánh giá log attribution.
Một service cấp chứng chỉ mới qua API ngoài trong vòng đời startup, nhưng sau restore không khởi tạo lại bước cấp phát và dùng certificate đã hết hạn; hãy xây dựng tình huống kiểm chứng trạng thái tài nguyên.
Một chương trình xử lý ảnh nạp model machine learning lớn trước checkpoint, nhưng sau restore đường dẫn file model không tồn tại tại node đích; hãy đặt tình huống đánh giá phụ thuộc giữa heap và artifact ngoài.
Một dịch vụ tìm kiếm làm nóng index trong cache trước checkpoint, nhưng dữ liệu index trên disk đã được cập nhật trong khoảng thời gian ảnh chờ triển khai; hãy đặt tình huống kiểm tra tính nhất quán.
Một ứng dụng khởi tạo client trả phí với tenant ID mặc định từ môi trường tạo checkpoint, rồi restore vào tenant khác và tiếp tục gửi request theo tenant cũ; hãy xây dựng tình huống kiểm chứng ranh giới cấu hình.
Một API phát hiện ảnh checkpoint bị tạo với profile development và sau restore ở production vẫn giữ một số bean dành cho thử nghiệm; hãy đặt tình huống đánh giá phạm vi snapshot.
Một hệ thống tự động scaling từ 0 lên nhiều Pod nhưng ảnh checkpoint có cờ đánh dấu instance leader từ lần khởi tạo trước, khiến nhiều bản restore cùng nhận vai trò chủ; hãy đặt tình huống kiểm chứng leader election.
Một ứng dụng dùng local in-memory queue để đệm request trước checkpoint và sau restore hàng đợi còn chứa dữ liệu gửi cho node tạo ảnh; hãy đặt bài toán xác định cách xử lý phần việc dở dang.
Một batch ETL lưu checkpoint khi đang giữ transaction trạng thái trung gian, rồi restore để chạy tiếp nhưng database đã có tiến trình khác cập nhật dữ liệu; hãy xây dựng tình huống đánh giá phục hồi tác vụ.
Một nhóm tạo checkpoint trên node có sẵn warm page cache và sau restore đo startup nhanh nhưng độ trễ truy vấn đầu tiên tăng mạnh; hãy đặt tình huống so sánh thời gian khởi động và độ trễ phục vụ.
Một ứng dụng ghi nhận thời gian khởi động từ lúc main bắt đầu nhưng không tách thời điểm restore JVM, chuẩn bị resource và nhận request đầu tiên; hãy xây dựng tình huống định nghĩa chỉ số hiệu năng.
Một đội đo CRaC trên máy phát triển có dữ liệu nằm trong filesystem cache, rồi so sánh với cold start trong Kubernetes với điều kiện I/O khác; hãy đặt tình huống đánh giá tính công bằng của phép đo.
Một dịch vụ có startup giảm đáng kể sau CRaC nhưng bộ nhớ RSS cao hơn vì giữ nhiều trang heap đã làm nóng, khiến node Kubernetes không chứa được nhiều Pod như trước; hãy đặt tình huống so sánh chi phí.
Một ứng dụng có checkpoint image lớn làm giảm thời gian khởi tạo Java nhưng kéo dài quá trình tải artifact từ registry, khiến tổng thời gian scale từ 0 đến sẵn sàng tăng; hãy xây dựng tình huống đánh giá hiệu quả đầu cuối.
Một nhóm chỉ đo thời gian để port HTTP mở sau restore mà không thử truy vấn database hoặc gọi API nghiệp vụ đầu tiên, khiến readiness được công bố quá sớm; hãy đặt bài toán kiểm chứng thời điểm sử dụng được.
Một chương trình tạo ảnh sau khi JIT đã biên dịch các hot method, nhưng workload thực tế sau restore khác với workload làm nóng, khiến hiệu năng ổn định kém hơn dự kiến; hãy xây dựng tình huống đánh giá kịch bản benchmark.
Một ứng dụng trước checkpoint làm nóng dữ liệu mẫu bằng thông tin khách hàng thật, khiến ảnh CRaC chứa dữ liệu không được phép lưu trong artifact; hãy đặt tình huống kiểm tra tính an toàn của workload warmup.
Một hệ thống thử CRaC và so sánh với startup chuẩn nhưng không lặp phép đo hoặc kiểm soát mức tải host, khiến số liệu thay đổi lớn giữa các lần; hãy đặt tình huống thiết kế phép đo tái lập.
Một nhóm thay đổi cấu hình heap khi restore và phát hiện độ trễ GC bất thường trong vài phút đầu, nhưng benchmark chỉ đo request đầu tiên; hãy xây dựng tình huống đánh giá cả giai đoạn ổn định.
Một dịch vụ cần mở rộng nhanh khi tải tăng đột biến nhưng mỗi Pod restore cùng lúc tạo hàng loạt kết nối mới tới database, gây lỗi connection limit; hãy xây dựng tình huống kiểm tra thác kết nối.
Một hệ thống serverless chạy Java có mục tiêu cold-start thấp nhưng restore phải đợi kho secret và dịch vụ discovery, khiến lợi ích CRaC phụ thuộc mạng; hãy đặt tình huống đánh giá các thành phần độ trễ.
Một ứng dụng tạo checkpoint chứa heap lớn nhưng tần suất cập nhật code cao, khiến chi phí xây lại ảnh vượt lợi ích khởi động nhanh cho môi trường preview; hãy xây dựng tình huống tính toán tính khả thi.
Một dịch vụ bật CRaC trong pipeline nhưng sau thay đổi cấu hình JVM, ảnh cũ vẫn được dùng và không phản ánh flags GC của bản phát hành mới; hãy đặt tình huống kiểm chứng tính tái tạo artifact.
Một nhóm so sánh số request/giây giữa fresh JVM và restored JVM nhưng không kiểm soát mức độ làm nóng JIT và cache, dẫn đến kết luận sai; hãy xây dựng tình huống lựa chọn chỉ số và điều kiện.
Một ứng dụng phục vụ API theo thời gian thực đạt startup nhanh nhưng xuất hiện spike latency ở request đầu do khởi tạo lại TLS và HTTP pools, khiến SLO vẫn bị vi phạm; hãy đặt tình huống đánh giá p95/p99 sau restore.
Một hệ thống autoscale dùng ảnh checkpoint được tạo nhiều ngày trước và bộ nhớ heap chứa cấu trúc tham chiếu không còn hiệu quả, gây tăng áp lực GC; hãy đặt tình huống kiểm tra chất lượng trạng thái lưu.
Một đội triển khai restore trên node có giới hạn CPU thấp hơn node tạo ảnh, khiến khoảng thời gian khôi phục và callback sau restore kéo dài; hãy xây dựng tình huống đánh giá nguồn lực tối thiểu.
Một service áp dụng CRaC để tăng mật độ Pod nhưng snapshot mang theo nhiều cache ít dùng, khiến bộ nhớ thực tế của replica vượt resource limit và bị OOM; hãy đặt tình huống kiểm chứng giới hạn bộ nhớ.
Một bộ kiểm thử chỉ xác nhận tạo được checkpoint và restore thành công, nhưng không chạy các nghiệp vụ đọc, ghi và phát sự kiện sau restore; hãy xây dựng tình huống xác định phạm vi kiểm thử chức năng.
Một dự án mock toàn bộ kết nối trong unit test CRaC nên không phát hiện socket và file descriptor thực sự cản trở checkpoint trên Linux; hãy đặt tình huống đánh giá kiểm thử tích hợp.
Một pipeline tạo ảnh CRaC bằng profile test nhưng phát hành bản restore với profile production khác, khiến một bean hạ tầng chưa từng được checkpoint đúng cách; hãy đặt tình huống xác định ma trận cấu hình.
Một môi trường CI không cấp quyền kernel cần thiết để checkpoint nên nhóm đánh dấu bỏ qua toàn bộ test CRaC, trong khi production vẫn dùng ảnh; hãy đặt bài toán đánh giá quality gate phù hợp.
Một nhóm muốn kiểm tra callback trước và sau restore nhưng test hiện chỉ gọi trực tiếp method callback trên đối tượng Java, chưa thực hiện checkpoint thật; hãy xây dựng tình huống phân biệt mức độ tin cậy.
Một chương trình tích hợp dịch vụ bên ngoài trả timeout giữa bước chuẩn bị checkpoint, khiến pipeline có lúc tạo được ảnh có lúc thất bại; hãy đặt tình huống kiểm tra tính xác định của quá trình chụp.
Một service dùng cơ sở dữ liệu thử nghiệm không có cơ chế giới hạn lease như production, khiến kiểm thử restore không phát hiện credential đã hết hạn; hãy xây dựng tình huống thiết kế môi trường đại diện.
Một ứng dụng chạy trên ba phiên bản kernel được hỗ trợ nhưng chỉ một phiên bản có bài kiểm thử restore sau khi nâng JDK; hãy đặt tình huống xác định tiêu chí tương thích phát hành.
Một pipeline CI chạy lại ảnh checkpoint cũ để giảm thời gian thử nghiệm, nhưng thay đổi thư viện native của bản build khiến kiểm thử vẫn xanh trong khi artifact mới chưa được tạo; hãy đặt tình huống kiểm chứng tính truy vết.
Một nhóm kiểm thử restore trên một instance nhưng chưa kiểm tra hai mươi replica cùng restore và khởi tạo đồng thời các kết nối; hãy xây dựng tình huống kiểm tra khả năng mở rộng.
Một hệ thống yêu cầu ảnh checkpoint không chứa secret nhưng hiện chưa có bước đánh giá nội dung bộ nhớ hoặc quy trình cấp phát credential tại restore; hãy xây dựng tình huống xác định bằng chứng an toàn.
Một dịch vụ được phục hồi từ ảnh cũ sau khi có bản vá bảo mật của thư viện Java, nhưng quy trình vận hành chưa bắt buộc tạo lại checkpoint; hãy đặt tình huống đánh giá quản trị phiên bản ảnh.
Một bản rollback ứng dụng khôi phục code cũ nhưng vẫn dùng checkpoint image của code mới, khiến trạng thái heap và classpath không đồng nhất; hãy đặt tình huống kiểm thử phục hồi phiên bản.
Một hệ thống triển khai blue-green với ảnh CRaC được tạo sẵn nhưng hai môi trường có cấu hình DNS và certificate khác nhau; hãy đặt tình huống kiểm chứng chuyển lưu lượng an toàn.
Một bộ điều phối tự động restart Pod từ ảnh checkpoint nhiều lần khi restore lỗi, làm cạn tài nguyên node và gây lặp sự cố; hãy đặt tình huống đánh giá đường khởi động dự phòng.
Một đội vận hành chỉ giám sát thời gian JVM restore mà chưa đo thời gian callback tái tạo kết nối và thời điểm readiness của Pod; hãy xây dựng tình huống thiết kế dashboard khả dụng.
Một service sau restore đôi khi thất bại khi mở lại socket nhưng metric chỉ ghi một lỗi khởi động chung, khiến nhóm không biết thành phần nào cần được xử lý; hãy đặt tình huống cải thiện chẩn đoán.
Một hệ thống ghi thời gian tạo checkpoint vào log nhưng không gắn ID ảnh và bản JDK, khiến sự cố trên một replica khó đối chiếu với artifact đã triển khai; hãy xây dựng tình huống kiểm chứng khả năng truy vết.
Một nhóm muốn tích hợp CRaC vào quy trình rolling update nhưng chưa xác định khi nào tạo ảnh, khi nào đóng băng phiên và khi nào cho phép Pod nhận tải; hãy đặt tình huống đánh giá thứ tự triển khai.
Một dịch vụ Java chạy CRaC kết hợp cơ chế tự động di trú dữ liệu, nhưng tại thời điểm restore database schema đã nâng phiên bản không tương thích với trạng thái heap; hãy xây dựng tình huống đánh giá ranh giới tương thích.
Một ứng dụng khôi phục nhanh trong thử nghiệm đơn lẻ nhưng khi cả cụm mất điện và đồng loạt restore thì Vault, database và service discovery đều bị quá tải; hãy đặt tình huống kiểm tra phục hồi thảm họa.
Một sản phẩm yêu cầu chứng minh CRaC giảm thời gian scale-out mà không thay đổi độ đúng của thanh toán, thông điệp, phân quyền và bảo vệ secret; hãy xây dựng tình huống xác định bộ tiêu chí nghiệm thu.
Một đội kiến trúc cân nhắc CRaC cho nhiều ứng dụng Java, trong đó có tác vụ batch ngắn, server HTTP lâu dài và dịch vụ giữ kết nối streaming; hãy đặt bài toán đánh giá mức độ phù hợp theo loại workload.

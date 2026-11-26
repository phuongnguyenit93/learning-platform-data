Một dịch vụ Spring WebFlux trả Mono chứa thông tin đơn hàng, nhưng controller tạo Publisher rồi không có subscriber ở luồng xử lý nền nên thao tác ghi nhật ký nghiệp vụ chưa bao giờ diễn ra.
Nhóm phát triển cho rằng Mono được thực thi ngay khi phương thức service trả về, khiến việc đo thời điểm gọi database lệch với lúc WebFlux thực sự subscribe vào chuỗi.
Ứng dụng gọi subscribe thủ công trong một handler WebFlux để lưu thay đổi rồi trả response ngay, khiến client nhận thành công trước khi lệnh lưu thực tế hoàn tất.
Đội vận hành phát hiện cùng một lệnh gọi đối tác được thực hiện hai lần vì một Mono cold được subscribe riêng bởi logger và controller mà không nhận ra tác động phụ lặp.
Một API dùng Flux cold để tạo báo cáo từ database nhưng hai subscriber lấy dữ liệu ở các thời điểm khác nhau, khiến bảng tổng hợp và file xuất không có cùng snapshot.
Nhóm dùng Mono.just để bọc kết quả của một hàm tốn CPU và mong giá trị chỉ được tính khi subscribe, khiến tác vụ nặng thực hiện ngay trên thread nhận request.
Ứng dụng xây chuỗi Mono.defer cho mỗi lần yêu cầu nhưng một đối tượng mutable được tạo bên ngoài và chia sẻ, khiến các subscription ảnh hưởng cùng một trạng thái.
Đội phát triển trả Mono.empty cho trường hợp không có đơn nhưng frontend phân biệt response rỗng với đơn trả về null, khiến trạng thái giao diện không khớp hợp đồng API.
Một service dùng Mono từ giá trị nullable nhưng một luồng dữ liệu nguồn trả null bất thường, khiến publisher kết thúc rỗng và lỗi thiếu dữ liệu không được phát hiện.
Nhóm phát hành một Mono<Void> sau thao tác xóa nhưng đoạn xử lý sau đó phụ thuộc onNext để gửi sự kiện, khiến sự kiện không được phát khi Mono chỉ hoàn tất.
Ứng dụng kết hợp hai Mono bằng zip để dựng DTO nhưng một nguồn hợp lệ trả Mono.empty, khiến bước dựng DTO không chạy dù nguồn còn lại có dữ liệu.
Đội dùng Mono.when cho hai tác vụ và mong nhận cả hai kết quả để tạo response, nhưng tín hiệu hoàn tất không chứa những giá trị cần cho phần tổng hợp.
Một dịch vụ dùng Flux.fromIterable để phát danh sách người dùng nhưng collection bị cập nhật bởi thread khác giữa lúc tiêu thụ, khiến stream lỗi hoặc trả dữ liệu thiếu ổn định.
Nhóm dùng Flux.range để mô phỏng hàng nghìn tác vụ nhưng bước downstream có side effect ghi database, khiến test chỉ kiểm tra số phần tử không phản ánh an toàn của thao tác thật.
Ứng dụng có publisher kết thúc sớm sau tín hiệu complete nhưng producer còn cố gửi dữ liệu, khiến các sự kiện phát sau terminal signal không được người nhận xử lý.
Đội dự kiến một Flux đại diện nhiều kết quả nhưng chuyển đổi sang Mono bằng next, khiến chỉ bản ghi đầu được xử lý và phần còn lại bị hủy subscription.
Một service dùng collectList trước khi trả một endpoint xuất dữ liệu lớn, khiến toàn bộ stream phải được gom vào bộ nhớ thay vì giải phóng từng phần tử.
Nhóm đặt block ở controller để lấy kết quả Mono đồng bộ, khiến thread sự kiện Netty bị giữ khi database hoặc API đối tác đáp ứng chậm.
Ứng dụng gọi toIterable trên Flux trong một WebFilter, khiến yêu cầu phải chờ toàn bộ stream và khả năng xử lý đồng thời giảm mạnh.
Đội tạo Mono lồng trong map và trả object chứa Mono thay vì giá trị nghiệp vụ đã được làm phẳng, khiến JSON response không chứa thông tin đơn hàng như mong đợi.
Một dịch vụ gọi flatMap nhưng bỏ Publisher do hàm callback tạo ra trong một nhánh, khiến thao tác cập nhật tồn kho không bao giờ được thực hiện khi khách đặt hàng.
Nhóm dùng concatWith để ghép hai danh sách sự kiện nhưng nguồn đầu không bao giờ hoàn tất, khiến các sự kiện từ nguồn sau không được chuyển đến subscriber.
Ứng dụng dùng merge để hợp nhất cập nhật từ hai kênh nhưng yêu cầu sản phẩm phải giữ thứ tự sự kiện, khiến trạng thái cuối cùng đôi khi bị ghi lùi.
Đội dùng concatMap để gọi API kiểm tra từng khách theo thứ tự nhưng một request chậm kéo dài thời gian xử lý mọi khách đứng sau.
Một service tăng flatMap concurrency để giảm latency nhưng hệ thống downstream có giới hạn kết nối, khiến lượng request đồng thời vượt sức chịu tải của đối tác.
Nhóm dùng flatMapSequential để duy trì thứ tự xuất dữ liệu nhưng các tác vụ không đồng đều khiến nhiều kết quả hoàn tất phải chờ và chiếm bộ nhớ.
Ứng dụng xử lý nhiều sự kiện theo accountId bằng flatMap không ràng buộc, khiến hai thay đổi trên cùng tài khoản được áp dụng sai thứ tự.
Đội dùng switchMap cho stream yêu cầu tìm kiếm đang thay đổi liên tục, nhưng một tác vụ được switch bỏ đã thực hiện side effect bên ngoài trước khi cancellation tới nơi.
Một service gọi zip từ hai hệ thống có SLA khác nhau, khiến response luôn đợi nguồn chậm dù dữ liệu nguồn nhanh đã có thể được hiển thị riêng.
Nhóm sử dụng combineLatest trên hai stream cấu hình nhưng một stream chưa phát giá trị đầu, khiến trang dashboard không có kết quả cho tới khi nguồn đó phát lần đầu.
Ứng dụng dùng zip với một Flux có ít phần tử hơn nguồn còn lại, khiến dữ liệu dư của nguồn dài không còn trong danh sách tổng hợp.
Đội gọi defaultIfEmpty sau một luồng giá sản phẩm không phát gì nhưng giá mặc định không phân biệt được trường hợp sản phẩm chưa tồn tại và lỗi dữ liệu thiếu.
Một service dùng switchIfEmpty với phương án dự phòng được dựng nóng, khiến request đối tác phụ vẫn chạy dù cache chính đã có dữ liệu.
Nhóm xử lý một luồng không có phần tử như trường hợp thành công nhưng nghiệp vụ yêu cầu báo thiếu tài nguyên, khiến API âm thầm trả mã thành công khi không tìm thấy đơn.
Ứng dụng dùng distinct trên stream chứa hàng triệu ID mà không giới hạn thời gian sống, khiến bộ nhớ giữ tập giá trị đã thấy tăng theo toàn bộ thời gian subscription.
Đội dùng groupBy theo userId trên dòng sự kiện có hàng trăm nghìn người dùng nhưng không tiêu thụ đủ các group, khiến upstream bị giữ lại và bộ nhớ tăng không kiểm soát.
Một service dùng buffer để gom giao dịch thành các lô nhưng không tính đến việc upstream dừng phát, khiến những bản ghi cuối của lô không được xử lý đúng vòng đời.
Nhóm dùng windowTimeout để tạo cửa sổ xử lý nhưng một downstream tiêu thụ cửa sổ quá chậm, khiến hàng đợi và nhu cầu bộ nhớ tăng bất ngờ.
Ứng dụng dùng sample cho tín hiệu vị trí tài xế nhưng nghiệp vụ cần biết mọi lần chuyển trạng thái online/offline, khiến sự kiện quan trọng bị bỏ sót.
Đội dùng debounce cho tìm kiếm gợi ý tên sản phẩm nhưng khi khách gõ rồi rời trang, request cuối bị hủy và công cụ phân tích hành vi không nhận được tín hiệu mong đợi.
Một service dùng take để lấy vài sự kiện đầu rồi dừng subscription, nhưng nguồn có side effect cập nhật vị trí cuối nên quá trình xử lý chưa hoàn tất như dự kiến.
Nhóm dùng skipUntilOther để chờ tín hiệu mở khóa hệ thống nhưng tín hiệu điều khiển xảy ra trước khi luồng bắt đầu subscribe, khiến job tiếp tục đứng chờ.
Ứng dụng dùng repeat cho truy vấn kiểm tra trạng thái nhưng không có khoảng nghỉ, khiến kết quả hoàn tất nhanh tạo hàng nghìn lời gọi database mỗi giây.
Đội dùng expand để duyệt cây quan hệ công ty nhưng dữ liệu có chu trình tham chiếu, khiến stream phát phần tử liên tục và không kết thúc theo hợp đồng.
Một service dùng parallel để tính toán giá trên nhiều phần tử nhưng bước cập nhật tổng cộng dùng một đối tượng mutable không an toàn, khiến kết quả dao động theo tải.
Nhóm ghép các stream bằng mergeWith rồi dựa vào thứ tự hoàn tất ban đầu, khiến báo cáo tài chính thay đổi thứ tự các dòng giữa hai lần chạy.
Ứng dụng có Flux chỉ phát một giá trị trong test nhưng thực tế phát nhiều bản ghi, khiến việc dùng single gây lỗi runtime khi xuất hiện hồ sơ thứ hai.
Đội chuyển một Flux sang Mono bằng last nhưng nguồn là stream SSE không kết thúc, khiến client chờ mãi mà không nhận kết quả cuối.
Một service áp dụng onBackpressureBuffer cho luồng giá thị trường nhưng không đặt giới hạn backlog, khiến JVM tăng heap khi phía nhận bị ngắt quãng.
Nhóm chọn onBackpressureDrop cho stream thanh toán nhưng từng sự kiện đều có ý nghĩa nghiệp vụ, khiến những thanh toán bị bỏ khỏi xử lý khi consumer chậm.
Ứng dụng dùng onBackpressureLatest cho vị trí xe nhưng tác vụ đối soát yêu cầu toàn bộ hành trình, khiến điểm trung gian bị mất và báo cáo lộ trình không đầy đủ.
Đội cấu hình onBackpressureError cho luồng nhập dữ liệu và chỉ kiểm thử với consumer nhanh, khiến sự cố overload đầu tiên làm subscription lỗi giữa lô mà không có checkpoint.
Một service dùng BaseSubscriber tự quản lý request nhưng chỉ request phần tử đầu tiên và quên yêu cầu tiếp, khiến stream đang hoạt động bề ngoài bị đứng sau một message.
Nhóm tạo Flux bằng Flux.create từ callback bên ngoài phát nhanh hơn downstream, khiến queue nội bộ tích lũy hàng triệu sự kiện khi client xử lý chậm.
Ứng dụng dùng Flux.push với nguồn callback có nhiều thread phát cùng lúc, khiến giả định về producer tuần tự không còn đúng dưới tải cao.
Đội tích hợp thư viện Reactive Streams khác nhưng Publisher upstream bỏ qua demand của Subscriber, khiến giới hạn requested không bảo vệ bộ nhớ ở consumer.
Một service dùng request(Long.MAX_VALUE) cho mọi subscription để đơn giản hóa code, khiến luồng xử lý chậm không còn kiểm soát lượng phần tử được gửi tới.
Nhóm trả HTTP response dạng streaming nhưng client mobile đọc chậm, khiến server phải giữ connection và backlog dài hơn khả năng của máy chủ.
Ứng dụng nhận Flux lớn từ WebClient nhưng một operator buffer không giới hạn đã gom các payload trước khi xử lý, khiến backpressure phía sau không ngăn được OOM.
Đội dùng limitRate với batch lớn hơn năng lực ghi database, khiến số message đang in-flight tăng mạnh trong đợt traffic đỉnh.
Một service dùng limitRequest để giới hạn số event nhận nhưng hệ thống upstream không có cơ chế tiếp tục từ offset đã dừng, khiến dữ liệu còn lại bị bỏ sót.
Nhóm áp dụng publishOn để chuyển scheduler nhưng prefetch mặc định làm nhiều phần tử được lấy trước, khiến bộ nhớ tăng khi downstream xử lý từng event rất chậm.
Ứng dụng dùng onBackpressureBuffer với kích thước tối đa nhưng không xử lý overflow, khiến một lần spike chuyển thành lỗi stream mà hệ thống theo dõi chỉ thấy request hủy.
Đội vận hành tăng số thread downstream để giải phóng backlog nhưng producer còn giới hạn demand sai, khiến throughput vẫn thấp mà không rõ nút thắt.
Một service nối Flux từ queue và Flux từ database theo cùng Subscriber, nhưng hai nguồn có cơ chế backpressure khác nhau khiến thứ tự xử lý thực tế không như kỳ vọng.
Nhóm thiết kế handler dùng map với thao tác ghi blocking mỗi phần tử, khiến downstream báo request ít nhưng thread Netty vẫn bị khóa ở một bước không có tính bất đồng bộ.
Ứng dụng dùng Sinks.many().multicast để phát tình trạng đơn tới nhiều người xem nhưng client chậm gây áp lực bộ đệm lên các subscriber khác.
Đội chọn Sinks.many().unicast cho kênh thông báo nhưng dashboard thứ hai subscribe cùng kênh, khiến cách phân phối sự kiện không đáp ứng yêu cầu nhiều người xem.
Một service dùng sink replay để hiển thị sự kiện mới nhất nhưng mỗi subscriber mới cần một khoảng lịch sử khác, khiến bộ nhớ cache replay tăng ngoài ngân sách.
Nhóm gọi sink.emitNext đồng thời từ nhiều thread trong đợt tải cao, khiến tín hiệu phát gặp lỗi cạnh tranh mà một phần event không được chuyển tiếp.
Ứng dụng dùng hot Flux chia sẻ thông báo đơn nhưng subscriber kết nối sau sự kiện đầu tiên, khiến màn hình không biết trạng thái đã thay đổi trước lúc kết nối.
Đội dùng publish().refCount() cho WebSocket feed nhưng subscriber cuối rời đi khiến upstream bị hủy, rồi người mới kết nối làm nguồn được subscribe lại với side effect ngoài ý muốn.
Một service dùng share cho kết quả đọc đơn hàng mà dữ liệu có thể thay đổi theo user, khiến subscriber khác nhận kết quả được tính trong ngữ cảnh của người đầu tiên.
Nhóm sử dụng cache operator cho một Mono tra giá nhưng không định thời hạn làm mới, khiến mọi subscription sau cùng nhận giá cũ dù database đã cập nhật.
Ứng dụng đặt replay cho luồng lỗi kết nối đối tác, khiến client mới nhận lại tín hiệu lỗi đã cũ thay vì có cơ hội thiết lập nguồn dữ liệu mới.
Đội chuyển từ cold Flux sang hot Flux trong module notification, nhưng integration test chỉ có một subscriber nên tình huống người đến muộn mất event không được phát hiện.
Một service dùng multicast sink với queue giới hạn nhưng không xử lý khi không có subscriber, khiến các tín hiệu publish lúc khởi động không xuất hiện trên dashboard.
Nhóm đóng sink bằng tín hiệu complete khi người dùng đầu tiên logout, khiến mọi subscriber còn lại không nhận thêm cập nhật dù WebSocket vẫn kết nối.
Ứng dụng dùng replay buffer chứa object lớn cho hàng nghìn subscriber, khiến mỗi lần có khách kết nối lượng dữ liệu replay làm tăng CPU và băng thông đột ngột.
Đội cần truyền event đến hai downstream xử lý độc lập nhưng dùng một cold source tạo payment side effect, khiến mỗi subscription kích hoạt thanh toán thêm một lần.
Một service dùng một hot Flux chia sẻ giữa các tenant nhưng không lọc theo tenant trước khi publish, khiến subscriber tenant A có thể nhận thông báo của tenant B.
Nhóm thêm doOnNext để ghi audit nhưng coi callback như bước nghiệp vụ bảo đảm hoàn thành, khiến audit lỗi không được thể hiện đúng như giao dịch chính.
Ứng dụng dùng doOnError để gửi email cảnh báo nhưng callback tạo Mono gửi email mà không tích hợp vào chuỗi, khiến cảnh báo không được gửi khi luồng lỗi.
Đội dùng doFinally để giải phóng tài nguyên nhưng phân biệt sai tín hiệu CANCEL và ON_COMPLETE, khiến báo cáo nhiệm vụ thành công cả khi khách đã ngắt kết nối.
Một service dùng doOnCancel để cập nhật trạng thái hủy đơn nhưng việc client đóng socket không luôn tương đương yêu cầu hủy nghiệp vụ, khiến đơn hợp lệ bị thay đổi.
Nhóm dùng using để quản lý kết nối stream nhưng resource cleanup có lỗi khi subscription bị hủy giữa chừng, khiến pool connections giảm dần.
Ứng dụng dùng usingWhen cho transaction resource nhưng luồng trả về bị cancel và đường cleanup riêng không được đánh giá, khiến connection còn giữ sau khi client ngắt.
Đội tích hợp file upload streaming nhưng giữ reference tới ByteBuf ngoài vòng đời tiêu thụ, khiến leak detector ghi nhận tài nguyên Netty không được giải phóng.
Một service đặt log chi tiết trong doOnEach với payload từng tín hiệu, khiến token và dữ liệu nhạy cảm bị đưa vào log khi bật debug production.
Nhóm dùng checkpoint cho chuỗi lỗi phức tạp nhưng không gắn định danh nghiệp vụ phù hợp, khiến stack trace lắp ráp vẫn khó chỉ ra operator lỗi.
Ứng dụng bật Reactor debug hooks toàn cục trên production tải cao, khiến CPU và kích thước stack trace tăng mạnh sau khi nhóm trực bật chế độ chẩn đoán.
Đội dùng materialize để biến onError thành dữ liệu báo cáo nhưng một consumer khác mong stream phát error signal thật, khiến cơ chế cảnh báo không được kích hoạt.
Một service dùng dematerialize để phục hồi tín hiệu nhưng input chứa sequence không hợp lệ, khiến một lần dữ liệu lỗi làm subscription dừng ngoài dự kiến.
Nhóm dùng onErrorReturn với giá mặc định 0 cho lỗi truy vấn số dư, khiến màn hình coi khách hết tiền thay vì thấy rằng nguồn dữ liệu đang gặp sự cố.
Ứng dụng dùng onErrorResume trả Mono.empty cho mọi exception từ WebClient, khiến timeout tới đối tác bị nhầm với tài khoản không tồn tại.
Đội retryWhen cho thao tác POST tạo đơn sau timeout nhưng upstream có thể đã xử lý yêu cầu đầu, khiến khách có hai đơn sau khi chuỗi retry thành công.
Một service đặt retry vô giới hạn cho kết nối broker đang lỗi xác thực, khiến hàng nghìn lần thử không có ích và tài khoản bị khóa.
Nhóm cấu hình Retry.backoff cho WebClient nhưng không giới hạn tổng thời gian của request, khiến gateway đã timeout trong khi chuỗi tiếp tục retry nền.
Ứng dụng dùng timeout cho toàn bộ quá trình xử lý đơn nhưng chưa phân biệt thời gian chờ network và CPU mapping, khiến log chỉ báo TimeoutException chung.
Đội dùng onErrorContinue cho dữ liệu nhập lô nhưng operator phía sau không có hỗ trợ phù hợp, khiến phạm vi bỏ qua bản ghi lỗi thay đổi ngoài dự kiến.
Một service dùng onErrorMap đổi mọi lỗi thành ngoại lệ nghiệp vụ, khiến mã lỗi mất kết nối được trình bày như yêu cầu khách không hợp lệ.
Nhóm đặt onErrorResume ở cuối chuỗi có nhiều nguồn, khiến tất cả lỗi từ database, thanh toán và audit đều bị fallback chung dù mức độ nghiêm trọng khác nhau.
Ứng dụng dùng retryWhen sau khi một bước ghi database đã thành công trong cùng pipeline, khiến khi bước audit lỗi toàn bộ tác vụ ghi được thực thi lại.
Đội áp dụng retryWhen trước map parse dữ liệu trả về nhưng payload sai cấu trúc không thể được sửa bằng retry, khiến đối tác bị gọi liên tục vì cùng lỗi không tạm thời.
Một service dùng onErrorComplete để không chặn luồng xử lý thông báo nhưng vô tình nuốt lỗi gửi hóa đơn, khiến dashboard báo đã hoàn tất dù không lưu hóa đơn.
Nhóm dùng delayError để tổng hợp nhiều nguồn nhưng một hệ thống ngoài bị lỗi sớm và pipeline vẫn thực hiện các side effects khác trước khi báo failure.
Ứng dụng dùng firstWithSignal giữa cache và database nhưng cache trả tín hiệu empty rất nhanh, khiến database bị hủy trước khi có kết quả hữu ích.
Đội dùng firstWithValue cho hai endpoint cùng cung cấp dữ liệu nhưng chúng có chính sách quyền khác nhau, khiến kết quả từ nguồn nhanh nhất không phản ánh vùng dữ liệu được phép.
Một service xử lý WebClient 404 như lỗi bất thường và kích hoạt retry, khiến mỗi lần tra mã sản phẩm không tồn tại tạo nhiều HTTP requests vô ích.
Nhóm muốn fallback sang bản cache cũ khi đối tác lỗi nhưng không gắn thông tin tuổi dữ liệu, khiến khách quyết định giao dịch dựa trên giá đã quá hạn.
Ứng dụng dùng timeout rồi phát event hủy giao dịch, nhưng yêu cầu upstream vẫn tiếp tục tại dịch vụ ngoài sau cancellation nên trạng thái hai bên không nhất quán.
Đội gắn doOnError gửi metric rồi bắt lỗi phía sau, khiến dashboard đếm mọi transient error như một thất bại cuối cùng dù request đã được phục hồi.
Một service có Flux từ Kafka bridge và lỗi xử lý một message làm cả subscription terminate, khiến những message mới không được tiếp tục tiêu thụ sau bản ghi lỗi.
Nhóm xử lý lỗi từng record bên trong flatMap nhưng không giữ khóa idempotency, khiến record bị retry sau reconnect gây thêm side effect ngoài dự kiến.
Ứng dụng dùng onErrorResume để chuyển sang một Flux dự phòng vô hạn, khiến subscription không bao giờ hoàn tất trong khi caller đang đợi báo cáo có điểm kết thúc.
Đội dùng repeatWhen cho luồng đơn hàng đã kết thúc thành công nhưng không có điều kiện dừng, khiến cùng dữ liệu cũ được đọc và phát lại liên tục.
Một service kết hợp checkpoint và lỗi được wrap nhiều lớp, khiến trace thiếu correlation ID và nhóm trực không xác định bước nào gây timeout.
Nhóm dùng Reactor Context lưu tenantId trong WebFlux request, nhưng bước đọc tenantId vẫn dựa vào ThreadLocal từ ứng dụng MVC cũ khiến dữ liệu có thể gắn nhầm tenant.
Ứng dụng dùng contextWrite ở vị trí không đúng kỳ vọng trong chuỗi, khiến operator đọc Context từ upstream không nhìn thấy requestId cần để ghi audit.
Đội xây WebFilter gắn correlation ID vào Reactor Context nhưng một service tạo subscription độc lập, khiến luồng làm việc nền không còn context của HTTP request.
Một service tạo Mono.deferContextual cho truy vấn theo tenant nhưng context tenant được cập nhật trong callback khác, khiến giá trị thực tế được đọc không như thứ tự nhóm dự kiến.
Nhóm di trú SecurityContext từ servlet sang WebFlux nhưng code kiểm tra quyền dựa trên biến thread-local, khiến các bước được chạy ở scheduler khác không thấy danh tính người dùng.
Ứng dụng đưa dữ liệu cá nhân vào Reactor Context rồi log toàn bộ context ở operator chung, khiến token và thông tin khách bị lưu vào công cụ quan sát.
Đội áp dụng MDC qua custom hook cho nhiều subscriber nhưng một luồng không dọn trạng thái cũ trên thread được tái sử dụng, khiến log request sau mang trace ID của request trước.
Một service truyền locale trong Context để định dạng email nhưng tác vụ scheduled không có Context từ HTTP, khiến một số thông báo được gửi bằng ngôn ngữ mặc định.
Nhóm chạy parallel xử lý danh sách đơn rồi dùng ThreadLocal tính thời điểm batch, khiến kết quả đo không khớp giữa các rails do dữ liệu ngữ cảnh không được chuyển.
Ứng dụng lấy userId từ Reactor Context trong một nhánh flatMap nhưng nhánh fallback dùng một Publisher được dựng từ trước, khiến quyền được áp dụng khác đường chính.
Đội tạo pipeline reactive bên trong CompletableFuture bên ngoài mà không chuyển Reactor Context, khiến tracing của tác vụ nền không liên kết được với yêu cầu gốc.
Một service dùng Context làm kho mutable map các lỗi validation của nhiều phần tử, khiến xử lý song song tạo tranh chấp ghi và phản hồi lỗi không ổn định.
Nhóm sử dụng contextWrite để thêm thông tin tên dịch vụ ở một nhánh, nhưng các nhánh zip được tạo riêng không có cùng ngữ cảnh như dashboard mong đợi.
Ứng dụng có WebFilter gắn tenantId từ JWT nhưng một route public không đi qua cùng logic xác định tenant, khiến operator downstream trả thiếu thông tin thay vì lỗi có kiểm soát.
Đội cần truyền thông tin audit across WebClient calls nhưng chỉ giữ correlation ID trong Reactor Context phía server, khiến HTTP headers ra đối tác không chứa định danh để nối trace.
Một service chạy scheduled Flux dùng chung với WebFlux request nhưng phụ thuộc Context có requestId, khiến job chạy không có HTTP request thì bị lỗi khi ghi log.
Nhóm dùng Micrometer context propagation sau nâng phiên bản nhưng không kiểm tra ranh giới scheduler, khiến trace của cùng tác vụ bị chia thành nhiều span không liên quan.
Ứng dụng triển khai subscriberContext theo API Reactor cũ trong thư viện nội bộ, khiến nâng dependency làm đường truyền context cần được đánh giá lại khi migrate.
Đội đưa object session mutable vào Context để tái sử dụng giữa các bước xác thực, khiến các nhánh xử lý song song thay đổi session trong lúc người dùng đăng xuất.
Một service gắn role vào Reactor Context sau khi kiểm tra token nhưng một middleware đọc role trước bước xác thực hoàn tất, khiến quyền truy cập bị đánh giá với giá trị mặc định.
Nhóm muốn chia sẻ request-scoped metadata trong chuỗi reactive nhưng lưu nó ở singleton bean, khiến yêu cầu của khách A có thể ghi đè metadata của khách B.
Ứng dụng dùng publishOn(Schedulers.parallel()) trước một lời gọi JDBC blocking, khiến thread pool dành cho tác vụ không chặn bị giữ lâu và request WebFlux xếp hàng.
Đội đưa thao tác gọi REST đồng bộ trong map trên Netty event loop, khiến một đối tác chậm làm tăng latency của nhiều kết nối HTTP không liên quan.
Một service dùng subscribeOn ở phần cuối pipeline và kỳ vọng chỉ một đoạn blocking được chuyển thread, khiến toàn bộ quá trình lập lịch khác thiết kế ban đầu.
Nhóm chèn publishOn trước bước parse JSON lớn nhưng không theo dõi số lần chuyển thread, khiến overhead scheduling tăng mà throughput không cải thiện.
Ứng dụng dùng Schedulers.boundedElastic cho những lệnh blocking nhưng mỗi request tạo một scheduler mới, khiến số thread và tài nguyên ứng dụng tăng theo traffic.
Đội đưa mọi phép tính CPU-bound sang boundedElastic vốn dùng cho blocking I/O, khiến queue các tác vụ đọc file bị trì hoãn trong giờ cao điểm.
Một service cấu hình shared boundedElastic với giới hạn queue thấp hơn tải thực, khiến yêu cầu mới bị từ chối khi hàng nghìn tác vụ JDBC đang chờ.
Nhóm sử dụng Schedulers.single cho một bước xử lý ảnh CPU nặng, khiến tất cả request phải lần lượt chờ cùng thread dù hệ thống còn CPU rảnh.
Ứng dụng bật parallel scheduler cho tính toán chính sách giá nhưng hàm dùng một bộ nhớ đệm mutable không đồng bộ, khiến kết quả khác nhau giữa các lần chạy.
Đội gọi blockOptional bên trong một reactive service được gọi từ WebFlux handler, khiến thread event loop bị chặn dù chữ ký public vẫn trả Mono.
Một service gọi Thread.sleep để chờ trạng thái job trong flatMap, khiến reactive stream mất khả năng phục vụ nhiều kết nối đồng thời khi lưu lượng tăng.
Nhóm thay delayElement bằng một vòng chờ bận để giảm dependency, khiến CPU tăng cao và cancellation không dừng vòng xử lý ngay.
Ứng dụng sử dụng Schedulers.immediate trong luồng dự tính xử lý việc blocking, khiến mọi tác vụ vẫn chạy trên thread thực hiện subscription và gây nghẽn.
Đội dùng publishOn cho bước gửi email blocking nhưng một operator trước đó đã gọi thư viện PDF đồng bộ trên event loop, khiến sự cố vẫn xảy ra trước ranh giới scheduler.
Một service chuyển từ JdbcTemplate sang R2DBC nhưng một helper xác thực vẫn gọi JDBC blocking trong WebFilter, khiến cải thiện hiệu năng không xuất hiện như kỳ vọng.
Nhóm đặt timeout cho Mono.fromCallable gọi thư viện blocking nhưng thư viện không phản ứng tốt với interrupt, khiến công việc tiếp tục giữ tài nguyên sau khi request bị hủy.
Ứng dụng nhận blocking call warning từ BlockHound trong bài test nhưng bỏ qua vì kết quả API đúng, khiến production sau đó tăng độ trễ khi nhiều khách đồng thời.
Đội chạy BlockHound với whitelist quá rộng cho module tích hợp, khiến thao tác đồng bộ hóa file trên event loop không được phát hiện trước release.
Một service gọi API encryption CPU nặng trong handle ở WebFlux, khiến event loop xử lý chậm dù không có lệnh I/O blocking truyền thống.
Nhóm dùng parallel() cho một Flux có side effect cập nhật chung tổng tiền, khiến thứ tự phần tử và kết quả aggregate thay đổi khi tăng số rails.
Ứng dụng chèn publishOn giữa transaction reactive và bước ghi dữ liệu, khiến nhóm nhầm thread switch với việc transaction context bị mất dù lỗi thực nằm ở Publisher không tham gia chuỗi.
Đội cố đặt một @Transactional kiểu imperative trên phương thức trả Mono nhưng dùng transaction manager JDBC, khiến vòng đời giao dịch không trùng với lúc thực tế Publisher được subscribe.
Một service lấy kết quả Mono bằng block ở boundary chuyển đổi API MVC cũ nhưng lượng gọi tăng mạnh, khiến thread pool phía MVC hết tài nguyên trong khi WebFlux downstream vẫn khỏe.
Nhóm mở hàng nghìn WebClient requests bằng flatMap concurrency không hạn chế, khiến connection pool HTTP bị cạn và tác vụ chờ acquiring connection.
Ứng dụng dùng Reactor Netty event loop chung cho server và WebClient, nhưng callback nhận response làm phép tính nặng, khiến cả inbound và outbound traffic có độ trễ tăng.
Đội set Schedulers.parallel làm scheduler cho mọi tác vụ gồm query JDBC và parse file, khiến các bước blocking chiếm hết thread vốn cần cho việc xử lý tín hiệu.
Một service xây Spring WebFlux endpoint trả Mono từ một repository reactive nhưng tự subscribe để ghi audit, khiến kết quả audit và response không được đồng bộ theo completion.
Nhóm sử dụng annotation controller với Mono<RequestDto> nhưng lại đọc trực tiếp body ở kiểu đồng bộ, khiến việc parse dữ liệu lớn được thực hiện trước khi reactive validation chạy.
Ứng dụng có handler trả Flux<OrderDto> và API gateway muốn nhận JSON array, nhưng client kỳ vọng từng bản ghi xuất hiện tức thì nên đánh giá luồng bị chậm.
Đội tạo endpoint Server-Sent Events từ Flux nhưng proxy trung gian bật buffering HTTP response, khiến client chỉ nhận một loạt sự kiện sau nhiều phút.
Một service phát SSE heartbeat nhưng không giới hạn số kết nối dài hạn, khiến khi người dùng mở nhiều tab số connection và memory vượt ngân sách.
Nhóm dùng response SSE cho sự kiện đơn hàng nhưng không có định danh event để client tiếp tục sau reconnect, khiến khách bỏ lỡ trạng thái đã thay đổi trong thời gian mất mạng.
Ứng dụng đưa payload cá nhân trong luồng SSE được chia sẻ nhiều subscriber, khiến client tenant khác nhận nội dung của đơn không thuộc tổ chức mình.
Đội chạy WebFlux sau ingress có timeout ngắn hơn thời gian phản hồi streaming, khiến kết nối SSE bị đóng đều đặn mặc dù publisher vẫn đang phát dữ liệu.
Một service dùng WebSocket để nhận vị trí tài xế liên tục nhưng không kiểm soát client gửi nhanh hơn khả năng ghi, khiến server phải giữ backlog message tăng mãi.
Nhóm chia sẻ một Flux cho nhiều WebSocket sessions nhưng khi session cuối hủy thì nguồn upstream kết thúc và khách kết nối mới không còn nhận dữ liệu.
Ứng dụng xử lý WebSocket receive qua flatMap gọi database nhưng một lỗi record làm toàn bộ subscription đóng, khiến kết nối ngắt dù các message sau hợp lệ.
Đội trả ServerResponse từ functional route nhưng một nhánh lỗi không trả Publisher hoàn tất, khiến kết nối HTTP treo cho đến khi gateway timeout.
Một service dùng RouterFunction với thứ tự route quá rộng trước route cụ thể, khiến yêu cầu WebFlux tới đường dữ liệu riêng bị xử lý bởi handler mặc định.
Nhóm xử lý form upload multipart trong WebFlux nhưng lưu toàn bộ file vào byte array trước khi gửi storage, khiến một upload lớn làm JVM tăng heap đột biến.
Ứng dụng stream DataBuffer từ request sang file nhưng một nhánh validation ném lỗi mà DataBuffer chưa được release, khiến Netty báo buffer leak khi tải cao.
Đội trả Flux<DataBuffer> cho file download nhưng client đóng socket giữa chừng và resource cleanup không được kích hoạt như thiết kế, khiến file descriptor còn mở.
Một service dùng bodyToFlux cho NDJSON nhưng client gửi JSON array chuẩn, khiến parser chỉ trả dữ liệu sau khi nhận đủ payload thay vì stream từng phần tử.
Nhóm thiết kế HTTP API upload theo Flux<DataBuffer> nhưng antivirus yêu cầu xem toàn bộ nội dung, khiến việc gom dữ liệu làm mất lợi ích backpressure của đường nhận.
Ứng dụng dùng WebFilter đọc request body để ghi log rồi downstream controller không đọc được body như kỳ vọng, khiến các request POST có payload bị báo thiếu dữ liệu.
Đội thêm WebExceptionHandler chuyển lỗi thành 200 với payload lỗi chung, khiến client không phân biệt lỗi hạ tầng với response nghiệp vụ đã thành công.
Một service xử lý lỗi khi publisher đã bắt đầu ghi HTTP response streaming, khiến logic muốn đổi mã trạng thái không còn tương thích vì headers đã được commit.
Nhóm triển khai WebFlux route trả Mono<ResponseEntity> nhưng body được tính ở Publisher khác chưa được liên kết, khiến response được hoàn tất trước khi side effect cần thiết kết thúc.
Ứng dụng sử dụng annotation @RestController cho endpoint streaming nhưng API documentation chỉ mô tả một JSON object, khiến SDK đối tác không tiêu thụ đúng Flux.
Đội bật CORS cho Spring WebFlux nhưng WebSocket handshake được kiểm tra khác route HTTP thông thường, khiến chỉ kết nối từ browser production bị từ chối.
Một service có WebFilter xác thực JWT nhưng hệ thống kiểm tra quyền nằm trên ThreadLocal, khiến một nhánh WebClient callback chạy ở scheduler khác không nhận user.
Nhóm gọi reactive authorization sau khi đã tạo Publisher tải dữ liệu nhạy cảm có side effect, khiến hệ thống nguồn bị truy vấn ngay cả khi request cuối cùng bị từ chối.
Ứng dụng phát thông báo lỗi nghiệp vụ qua Flux SSE nhưng client chỉ nhận onError và tự reconnect, khiến cùng yêu cầu được gửi lại nhiều lần ngoài thiết kế.
Đội tạo endpoint trả vô hạn dòng log qua WebFlux nhưng một proxy đặt response size limit, khiến connection bị cắt trong lúc người dùng điều tra.
Một service dùng WebClient.responseSingle cho nguồn trả nhiều nội dung dữ liệu chunked, khiến cách chuyển response khác hợp đồng streaming mà frontend đang chờ.
Nhóm sử dụng WebClient retrieve cho API đối tác trả 429 nhưng không xử lý riêng rate limit, khiến retry vô điều kiện làm đối tác tiếp tục từ chối request.
Ứng dụng dùng WebClient exchangeToMono để đọc lỗi HTTP nhưng một nhánh không tiêu thụ hoặc giải phóng response body đúng cách, khiến connection pool giảm khả năng tái sử dụng.
Đội cấu hình WebClient connect timeout nhưng quên giới hạn thời gian đọc response, khiến một đối tác giữ kết nối mở lâu và request không hoàn tất.
Một service dùng WebClient gọi đồng thời ba nhà cung cấp để tính phí nhưng một nguồn timeout làm toàn bộ zip thất bại dù có dữ liệu đủ dùng từ hai nguồn khác.
Nhóm triển khai retry cho WebClient POST đăng ký tài khoản mà không có idempotency key, khiến một response bị mất làm đối tác tạo nhiều tài khoản trùng.
Ứng dụng gọi WebClient từ mỗi bản ghi của một Flux không giới hạn concurrency, khiến lượng connection pending lớn hơn hạn mức máy chủ đối tác.
Đội bật connection pooling Reactor Netty với thời gian idle dài nhưng proxy phía trước đóng socket sớm, khiến những request tái sử dụng connection cũ gặp lỗi ngẫu nhiên.
Một service không đọc/tiêu thụ hết body response lỗi khi gọi WebClient, khiến kết nối không được tái sử dụng hiệu quả và latency tăng sau đợt lỗi đối tác.
Nhóm xử lý dữ liệu streaming qua WebClient nhưng gọi bodyToMono với payload hàng trăm MB, khiến codec buffer vượt giới hạn được cấu hình.
Ứng dụng tăng maxInMemorySize cho codec để tránh lỗi payload lớn nhưng không kiểm tra tác động khi nhiều request đồng thời, khiến heap tăng mạnh trong giờ cao điểm.
Đội nhận WebClient 200 với JSON sai schema và dùng onErrorResume trả object rỗng, khiến dữ liệu nguồn không hợp lệ bị lưu như một kết quả bình thường.
Một service gọi WebClient bằng bearer token lấy từ Reactor Context nhưng khi retry chuỗi được tạo ở subscription khác, khiến request thử lại thiếu token ở header.
Nhóm đặt log request/response đầy đủ cho WebClient trong thời gian xử lý lỗi nhưng payload chứa dữ liệu tài chính, khiến thông tin nhạy cảm bị ghi vào log tập trung.
Ứng dụng đọc cookies từ ServerWebExchange để gọi dịch vụ ngoài nhưng không giới hạn danh sách headers được chuyển tiếp, khiến credential nội bộ có thể bị gửi sang domain không liên quan.
Đội thử WebClient qua địa chỉ localhost trong integration test nhưng production có proxy DNS và TLS khác, khiến lỗi handshake chỉ xuất hiện sau triển khai.
Một service dùng WebClient để nhận stream sự kiện từ đối tác nhưng khi đối tác reconnect, luồng cũ chưa được cancel khiến cùng event được xử lý từ hai kết nối.
Nhóm đo thời gian API thành công bằng lúc Mono được lắp ghép thay vì lúc onComplete, khiến số liệu latency WebClient thấp giả so với thời gian người dùng chờ.
Ứng dụng dùng reactive MongoDB repository trả Flux nhưng handler lại gọi collectList với dữ liệu quá lớn, khiến việc sử dụng driver reactive không loại bỏ memory pressure.
Đội kết hợp dữ liệu từ R2DBC và một repository JPA blocking trong cùng Mono, khiến bước JPA làm tắc Netty thread dù đường truy cập R2DBC không chặn.
Một service dùng ReactiveCrudRepository trong WebFlux rồi gọi block để lấy entity cập nhật trạng thái, khiến request bị blocking và không tận dụng khả năng xử lý đồng thời.
Nhóm áp @Transactional cho phương thức trả Mono nhưng dùng transaction manager không hỗ trợ reactive, khiến hai lệnh R2DBC không tham gia cùng giao dịch khi được subscribe.
Ứng dụng sử dụng R2dbcTransactionManager và TransactionalOperator nhưng một nhánh ghi dữ liệu tách subscription, khiến cập nhật phụ nằm ngoài transaction đã được mở.
Đội dùng reactive transaction bao quanh stream rất dài từ database, khiến connection bị giữ trong suốt thời gian client đọc từng phần tử và pool cạn khi client chậm.
Một service mở transaction reactive để trừ tồn kho rồi gửi WebClient request trong cùng pipeline, khiến network timeout kéo dài thời gian giữ connection và lock.
Nhóm gọi hai R2DBC update theo trình tự nhưng một lệnh được dựng ra rồi bỏ khỏi chuỗi, khiến transaction commit chỉ ghi một bảng dù service báo đã xử lý hai bước.
Ứng dụng dùng onErrorResume bên trong transactional chain để biến lỗi ràng buộc thành empty, khiến transaction nhìn thấy tín hiệu hoàn tất thay vì rollback như nghiệp vụ kỳ vọng.
Đội dùng retryWhen cho toàn bộ transaction R2DBC có gọi dịch vụ email ngoài, khiến retry sau deadlock có thể gửi nhiều email dù chỉ một transaction commit.
Một service dùng WebFlux kết nối hệ thống JDBC qua adapter blocking nhưng context transaction reactive không bao phủ giao dịch JDBC, khiến hai nguồn dữ liệu commit không đồng bộ.
Nhóm đọc dữ liệu trực tiếp từ R2DBC sau khi ghi rồi truy cập replica khác, khiến một số yêu cầu nhận bản ghi cũ do replication lag mặc dù cùng luồng reactive.
Ứng dụng chạy kiểm thử R2DBC với một câu SQL nhanh nhưng production có lock contention, khiến những Publisher giữ connection quá lâu và pool chờ tăng.
Đội có database reactive client hỗ trợ backpressure nhưng query đã tải quá nhiều hàng vào driver buffer trước khi downstream tiêu thụ, khiến heap tăng trên bảng lớn.
Một service kết hợp Flux từ R2DBC với Flux từ cache nhưng dữ liệu được đọc tại thời điểm khác nhau, khiến danh sách cuối có sản phẩm vừa hết hàng vẫn được đánh dấu còn.
Nhóm dùng Mono.zip để ghép các truy vấn vào nhiều nguồn nhưng một truy vấn không trả dòng, khiến các kết quả hợp lệ của nguồn khác không được lưu vào báo cáo.
Ứng dụng nhận timeout từ R2DBC connection pool nhưng onErrorReturn trả giá mặc định, khiến khách nhìn thấy số dư 0 thay vì thông báo không đọc được dữ liệu.
Đội tối ưu throughput bằng cách tăng số consumer của Flux R2DBC nhưng truy vấn cùng bảng cập nhật tài khoản cạnh tranh khóa, khiến rollback và retry tăng theo tải.
Một service lưu giá trị do WebFlux handler nhận vào cache Redis reactive nhưng TTL được tính ngoài chuỗi ở thời điểm assembly, khiến các subscription muộn đặt hạn sử dụng sai.
Nhóm dùng Redis Pub/Sub như nguồn Flux cập nhật quyền nhưng subscriber mất mạng, khiến các API instance chưa nhận sự kiện tiếp tục giữ cache phân quyền cũ.
Ứng dụng bridge Kafka records thành Flux nhưng một consumer cancel khi HTTP client rời đi, khiến offset của message cần xử lý không được xác nhận theo vòng đời nghiệp vụ.
Đội tạo reactive pipeline nhận sự kiện từ broker có at-least-once delivery nhưng không có idempotency key, khiến khi retry hoặc resubscribe phát sinh xử lý trùng.
Một service dùng flatMap xử lý nhiều Kafka records mà vẫn commit offset theo thứ tự nhận, khiến message sau được xác nhận trước khi message trước hoàn tất ghi database.
Nhóm dùng Flux.interval để chạy đồng bộ tồn kho định kỳ nhưng một lượt đồng bộ lâu hơn chu kỳ, khiến những lượt sau được kích hoạt trước khi lượt cũ kết thúc.
Ứng dụng tạo tác vụ scheduled bằng reactive Publisher được tái sử dụng nhưng không đánh giá khi scheduler subscribe nhiều lần, khiến tác vụ có side effect được chạy trùng.
Đội dùng Flux.interval ở scheduler mặc định cho hàm blocking, khiến tick tiếp theo bị chậm khi hệ thống nguồn mất kết nối.
Một service khởi chạy nhiều interval streams theo từng tenant mà không giải phóng chúng khi tenant ngừng hoạt động, khiến số tác vụ và subscriptions tăng mãi.
Nhóm tạo luồng xử lý sự kiện dùng Sinks.Many nhưng không quan sát tín hiệu emit thất bại, khiến một đợt quá tải có bản ghi không vào hàng đợi mà producer vẫn báo thành công.
Ứng dụng chuyển từ imperative message listener sang Flux nhưng nguồn callback không có cơ chế dừng đọc khi downstream chậm, khiến hệ thống không bảo đảm demand như mong đợi.
Đội xử lý hàng nghìn sự kiện qua groupBy theo accountId nhưng không giới hạn số group sống, khiến dịch vụ giữ trạng thái của các tài khoản đã không còn sự kiện.
Một service chia stream thành các nhóm xử lý theo thời gian nhưng một số job không bao giờ phát completion, khiến transaction và resources của window bị giữ lâu.
Nhóm dùng takeUntilOther để dừng cập nhật trong giờ bảo trì nhưng tín hiệu dừng bị phát trước khi subscription bắt đầu, khiến process không dừng theo lịch.
Ứng dụng phát trạng thái job bằng hot Flux nhưng một công cụ trực mở sau sự cố không nhận trạng thái hiện tại, khiến dashboard đánh dấu không rõ thay vì job đã hoàn tất.
Đội triển khai reactive batch job với concurrency rất cao nhưng hệ thống downstream chỉ có một nhóm kết nối database, khiến pipeline tăng số pending requests thay vì throughput.
Một service muốn trả response nhanh khi background event được nhận nhưng dùng Mono.delay để mô phỏng xác nhận, khiến client tưởng công việc đã được lưu bền dù mới nằm trong memory.
Nhóm gửi audit trong doFinally cho cả COMPLETE và CANCEL nhưng không phân loại trạng thái, khiến những yêu cầu bị khách hủy vẫn được thống kê thành công.
Ứng dụng báo onComplete khi tất cả Flux records đã được subscribe mà không chờ side effects bên ngoài hoàn thành, khiến thông báo kết thúc batch không đúng thực tế.
Đội đặt retry cho một Flux hot nhận sự kiện từ nguồn không replay, khiến sau lỗi subscription được nối lại nhưng những sự kiện phát trong lúc ngắt không thể khôi phục.
Một service bật các logs trong Reactor bằng operator log cho từng phần tử chứa nội dung tin nhắn, khiến thông tin nhạy cảm xuất hiện trong hệ thống logging ngoài quyền truy cập.
Nhóm gắn metrics theo từng userId trong Reactor pipeline, khiến cardinality của time series tăng nhanh khi số người dùng vượt hàng triệu.
Ứng dụng dùng Micrometer Observation quanh phương thức dựng Mono chứ không quanh subscription thực tế, khiến thời gian gọi đối tác và database không hiện trong trace.
Đội theo dõi số request HTTP thành công nhưng không tính luồng SSE bị hủy trước khi phát đủ message, khiến dashboard che khuất việc client thường xuyên mất kết nối.
Một service mất correlation ID sau publishOn trong chuỗi Reactor và log thông báo lỗi không gắn được với request ban đầu, khiến điều tra production khó nối sự kiện.
Nhóm dùng doOnNext để đo thời gian xử lý nhưng không có metric riêng cho empty completion, khiến lỗi tìm khách không tồn tại bị gộp vào sự cố không phát dữ liệu.
Ứng dụng có retryWhen với backoff nhưng chỉ đếm response HTTP cuối, khiến một endpoint báo 200 vẫn tạo hàng chục lời gọi thất bại ở backend mà dashboard không thể hiện.
Đội đặt tag exception với full message chứa userId vào metric Reactor, khiến dashboard bùng nổ cardinality và có nguy cơ lộ dữ liệu cá nhân.
Một service lưu toàn bộ operator assembly stack trong lỗi xử lý trên production, khiến log payload tăng đáng kể sau khi lượng request lên cao.
Nhóm quan sát Reactor Netty connection metrics nhưng không đo pending acquire, khiến cache CPU bình thường mà yêu cầu WebClient vẫn bị timeout do hết connection.
Ứng dụng kiểm tra CPU/heap của WebFlux server nhưng không xem event-loop blocked time, khiến lỗi gọi JDBC đồng bộ chỉ được phát hiện khi khách phản ánh độ trễ.
Đội dùng trace sampler rất thấp cho các stream lỗi hiếm, khiến các bước subscribe/cancel/retry không được ghi lại khi điều tra gián đoạn.
Một service chạy benchmark reactive với subscriber vô hạn demand nhưng production client di động đọc chậm, khiến kết quả benchmark không thể dự báo memory pressure thật.
Nhóm cho rằng p95 giảm khi chuyển sang WebFlux nhưng số request đang mở tăng mạnh do timeout chưa được cấu hình, khiến connection usage vượt ngưỡng trước lúc hết CPU.
Ứng dụng dùng WebFlux với các endpoint GET nhanh nhưng endpoint export CSV vẫn gom dữ liệu trong memory, khiến một loại tác vụ làm toàn server OOM.
Đội kiểm thử Mono bằng cách gọi một method rồi assert rằng database đã ghi, nhưng chưa subscribe nên bài test không thực sự kích hoạt tác vụ lưu.
Một service unit test map/flatMap trên Flux ít phần tử nhưng không thử trường hợp upstream trả empty, khiến một lần zip với Mono.empty làm response biến mất trong production.
Nhóm kiểm thử code reactive bằng block trên mọi Publisher và dữ liệu nhỏ, khiến vấn đề blocking trên Netty event loop không được phát hiện trước release.
Ứng dụng sử dụng StepVerifier chỉ assert onNext đầu tiên rồi cancel, khiến lỗi xảy ra sau phần tử đầu không được kiểm chứng trong suite.
Đội test onErrorResume với lỗi 404 nhưng không kiểm tra lỗi timeout kết nối, khiến fallback che mất sự cố hạ tầng khi gọi WebClient.
Một service dùng StepVerifier.withVirtualTime cho luồng có delay nhưng Publisher được tạo trước khi virtual scheduler được thiết lập, khiến bài kiểm thử thời gian không hành xử như kỳ vọng.
Nhóm dùng StepVerifier.withVirtualTime nhưng không xác minh khoảng backoff của retry, khiến sự cố retry dồn dập dưới tải thực không được phát hiện.
Ứng dụng có bài test nhận Flux SSE bằng WebTestClient nhưng chỉ kiểm tra HTTP 200, khiến sự kiện không đến hoặc mất thứ tự không làm suite thất bại.
Đội thử WebSocket handler với một session luôn online nhưng không kiểm tra trường hợp client cancel giữa lúc server gửi event, khiến tài nguyên không được dọn khi mất mạng.
Một service dùng TestPublisher để mô phỏng upstream nhưng test không phát hành error hoặc complete, khiến operator kết thúc sai vòng đời vẫn PASS ở dữ liệu thường.
Nhóm dùng StepVerifier cho stream có giới hạn request nhưng không assert demand, khiến Publisher bỏ qua backpressure vẫn được coi là đúng chức năng.
Ứng dụng chạy integration test với WebTestClient không bật timeout phù hợp cho một nguồn vô hạn, khiến CI có lúc treo khi thử endpoint SSE.
Đội test Reactor Context bằng cách gọi service không thông qua WebFilter, khiến thiếu tenantId trong các request WebFlux thật chưa được phát hiện.
Một service chỉ kiểm tra SecurityContext ở đường gọi HTTP tuần tự, khiến role propagation khi publishOn đổi scheduler chưa được kiểm chứng trong CI.
Nhóm dùng BlockHound trong một số unit tests nhưng không tích hợp test đường chạy WebFlux thực, khiến thao tác JDBC blocking trong WebFilter vẫn qua kiểm thử.
Ứng dụng tạo benchmark với upstream phát chậm hơn subscriber nhưng production producer nhanh gấp nhiều lần, khiến trường hợp overflow và backlog không xuất hiện trong test.
Đội chỉ kiểm tra một subscription của cold Mono có side effect, khiến việc hai subscribers thực thi lặp thao tác thanh toán chưa được test.
Một service dùng virtual time cho Flux.interval nhưng test không kiểm tra cancellation, khiến khi client rời endpoint tác vụ định kỳ vẫn tiếp tục trong production.
Nhóm thử flatMap xử lý 10 events độc lập nhưng không kiểm tra hai sự kiện cùng accountId, khiến lỗi xử lý sai thứ tự trên cùng tài khoản chưa bị phát hiện.
Ứng dụng kiểm thử reactive transaction với một lệnh R2DBC thành công nhưng không tạo lỗi ở bước thứ hai, khiến rollback nhiều bước chỉ lỗi khi xử lý giao dịch thật.
Đội dùng MockWebServer trả response nhanh liên tục nhưng không mô phỏng WebClient connection pool exhaustion, khiến retry và timeout chưa được đánh giá với downstream chậm.
Một service test streaming file với payload nhỏ và client đọc hết, khiến vấn đề DataBuffer release khi download bị hủy ở giữa chưa được kiểm chứng.
Nhóm chạy integration test trên một scheduler duy nhất với tải thấp, khiến race condition của object mutable trong parallel rail chưa xuất hiện.
Ứng dụng có TestPublisher chỉ phát onNext đúng hợp đồng nhưng không thử misbehaving upstream gửi null hoặc phát sau completion, khiến operator không được kiểm tra tính bền vững.
Đội test onBackpressureDrop bằng subscriber yêu cầu không giới hạn, khiến chính sách bỏ bớt message chưa bao giờ được kích hoạt trong suite.
Một service dùng WebTestClient kiểm thử response JSON bình thường nhưng không kiểm tra NDJSON chunked và SSE flush, khiến client production phải chờ hết stream mới nhận dữ liệu.
Nhóm nâng Reactor phiên bản mới nhưng test chỉ dùng Mono.just và Flux.range, khiến thay đổi về context propagation và async operator không được kiểm chứng trên workflow nghiệp vụ.
Ứng dụng chạy nhiều unit tests với hooks Reactor toàn cục mà không reset hooks sau test, khiến suite khác hành xử phụ thuộc thứ tự chạy và tạo lỗi khó tái hiện.
Đội kiểm thử reactive cache với một subscriber nhưng không mô phỏng hai subscriber đăng ký trước lúc nguồn phát, khiến behavior của share/cache trong production khác bài test.
Một service có bộ kiểm thử error handling chỉ assert kiểu exception mà không xác minh side effects đã commit hay chưa, khiến retry gây ghi trùng mà suite vẫn xanh.
Nhóm đánh giá khả năng xử lý overload bằng throughput trung bình nhưng không đo phần tử bị drop và cancellation khi consumer chậm, khiến báo cáo hiệu năng quá lạc quan.
Ứng dụng phát triển API streaming theo Reactive Streams nhưng tài liệu tích hợp không nêu cách client yêu cầu dữ liệu và hủy subscription, khiến đối tác xử lý sai vòng đời nguồn.
Đội cần chứng minh sự kiện thanh toán không bị mất khi subscriber chậm hoặc restart, nhưng hệ thống hiện chỉ có Flux hot trong bộ nhớ và dashboard không lưu checkpoint nào.

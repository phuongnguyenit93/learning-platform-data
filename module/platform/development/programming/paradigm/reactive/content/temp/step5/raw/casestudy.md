Một dịch vụ đặt hàng xây Mono để ghi đơn vào cơ sở dữ liệu nhưng không có thành phần nào subscribe; controller trả thông báo thành công trong khi không có bản ghi mới được lưu.
Một ứng dụng nhận dữ liệu từ cảm biến dùng Flux lạnh cho mỗi phiên theo dõi; khi hai dashboard subscribe riêng, quá trình truy vấn nguồn được thực hiện hai lần và lượng tải tăng bất ngờ.
Một nền tảng truyền thông chuyển Flux nguồn sang luồng chia sẻ nóng; người dùng vào xem muộn chỉ nhận các sự kiện mới và thiếu phần lịch sử mà giao diện yêu cầu.
Một hệ thống gửi mã xác thực tạo Mono.just từ lời gọi phát mã có tác dụng phụ; mã đã được gửi ngay khi dựng pipeline, trước cả thời điểm người dùng thực sự xác nhận.
Một cổng nhập tài liệu dùng Mono.defer để dựng pipeline theo từng subscription; khi cơ chế retry đăng ký lại, một bước lấy dữ liệu không ổn định được chạy thêm lần và cho nội dung khác.
Một dịch vụ hồ sơ dùng Mono.justOrEmpty với đối tượng tra cứu có thể vắng mặt; phía nhận nhầm việc hoàn thành không có giá trị với lỗi truy vấn và bỏ qua trạng thái chưa tìm thấy.
Một nền tảng kiểm tra tín dụng trả Mono.empty khi không có hồ sơ; toán tử map xử lý kết quả không được gọi nên bước ghi dấu kiểm tra mà nhóm kiểm toán mong đợi không xuất hiện.
Một API quản lý phòng họp chuyển Mono<Void> hoàn tất thành tín hiệu xác nhận thao tác; bộ phận giao diện lại chờ onNext có payload nên không cập nhật trạng thái sau khi tác vụ kết thúc.
Một ứng dụng lập lịch tạo Publisher riêng cho mỗi cuộc hẹn nhưng gửi cùng một yêu cầu qua hai subscription; bên đối tác nhận hai lịch hẹn trùng do quy trình không phân biệt hiệu ứng theo lần đăng ký.
Một thư viện streaming tự xây Publisher và bắt đầu gửi sự kiện ngay trong subscribe mà chưa nhận request dương từ Subscriber; consumer chậm bị nhận dữ liệu vượt khả năng xử lý.
Một hệ thống giám sát nhận Subscription rồi gọi request với giá trị bằng không để tạm ngừng; Publisher phát tín hiệu lỗi theo hợp đồng thay vì tiếp tục chờ như bộ phận vận hành dự tính.
Một cổng dữ liệu đặt demand ban đầu là một phần tử nhưng Publisher tùy biến vẫn phát cả batch trong cùng lượt gọi; subscriber ghi nhận vi phạm số lượng tín hiệu được yêu cầu.
Một ứng dụng có Subscriber gọi request thêm từ nhiều luồng và tính tổng demand bằng biến thường; khi tải cao, một số lượt cấp quyền bị mất nên luồng sự kiện dừng không đúng lúc.
Một hệ thống thông báo tự triển khai Publisher nhưng gọi onNext đồng thời cho cùng Subscriber từ hai tác vụ; dữ liệu trong bộ tích lũy bị cập nhật tranh chấp và kết quả hiển thị sai thứ tự.
Một dịch vụ xử lý đơn gửi onComplete rồi vẫn phát thêm một sự kiện cập nhật trạng thái; phía Subscriber đã kết thúc và bản cập nhật quan trọng không được quan sát.
Một nền tảng giao dịch dùng onError để báo nguồn dữ liệu hỏng rồi cố gửi một giá trị dự phòng bằng onNext; Subscriber không nhận được giá trị do luồng đã kết thúc với lỗi.
Một hệ thống thu thập telemetry nhận onNext chứa null từ Publisher tự viết; luồng vi phạm hợp đồng và các consumer của Reactor không thể diễn giải null thành một sự kiện hợp lệ.
Một cổng báo cáo giữ Subscription sau khi khách hủy yêu cầu HTTP; nguồn tiếp tục đọc dữ liệu tốn tài nguyên vì tín hiệu cancel không được truyền xuống thành phần tạo sự kiện.
Một dịch vụ theo dõi đơn hàng hiểu cancel như sự kiện xác nhận đã xử lý xong; trong khi đó nguồn bị hủy giữa chừng và một số sự kiện kinh doanh chưa được tiêu thụ.
Một ứng dụng tạo luồng phản hồi vô hạn rồi dùng bộ xử lý chỉ gọi request một lần; sau khi nhận đủ số phần tử ban đầu, phần còn lại ngừng đến dù nguồn vẫn hoạt động.
Một nền tảng giao tiếp realtime dùng Flux.create để đưa callback từ hệ thống cũ sang Reactor; nguồn callback phát nhanh hơn khả năng đọc khiến hàng đợi nội bộ tăng liên tục.
Một dịch vụ nhập sự kiện dùng Flux.push mặc dù callback có thể đến đồng thời từ nhiều thread; khi tải cao, giả định nguồn phát một luồng không còn được đáp ứng.
Một hệ thống cảm biến tích hợp Sinks.Many và gọi tryEmitNext khi dữ liệu đến dồn dập; kết quả phát thất bại bị bỏ qua nên dashboard thiếu sự kiện nhưng bộ đếm đầu vào vẫn tăng.
Một cổng cảnh báo phát sự kiện tới Sink sau khi tín hiệu hoàn tất đã được gửi; một nhóm cảnh báo quan trọng bị từ chối mà bộ phận vận hành không ghi nhận được lý do.
Một dịch vụ theo dõi giá dùng luồng multicast không lưu lịch sử; Subscriber thứ hai đến sau giai đoạn giá thay đổi không thấy giá hiện hành và hiển thị giá trị trống.
Một hệ thống giao dịch dùng replay sink giữ toàn bộ lịch sử sự kiện để phục vụ khách mới; sau nhiều ngày hoạt động, bộ nhớ tăng liên tục vì không có giới hạn lưu giữ phù hợp.
Một nền tảng telemetry dùng onBackpressureBuffer cho nguồn cao tần; consumer bị chậm kéo dài khiến bộ đệm tích lũy đến mức tiến trình thiếu bộ nhớ.
Một ứng dụng thu thập chỉ số dùng onBackpressureDrop để bảo vệ downstream; dữ liệu mất đúng lúc tải đột biến nên biểu đồ tổng hợp không thể dùng cho kiểm toán số lượng sự kiện.
Một dịch vụ hiển thị nhiệt độ dùng onBackpressureLatest; bộ phận báo cáo lại cần mọi phép đo liên tiếp nên số liệu trung bình được tính từ chuỗi đã mất mẫu.
Một cổng quản lý thiết bị chuyển sang chiến lược phát lỗi khi vượt demand; khi thiết bị gửi dồn dập, cả pipeline kết thúc thay vì chỉ giảm tốc theo kỳ vọng của giao diện.
Một ứng dụng dùng limitRate để điều chỉnh mức request theo lô; nhóm phát triển tưởng thao tác này tự giới hạn tốc độ sự kiện theo giây nên nguồn vẫn tạo đỉnh tải lớn.
Một hệ thống cảnh báo đặt buffer lớn giữa Publisher và dịch vụ ghi database; khi database chậm, biểu đồ độ trễ đầu vào vẫn tốt nhưng thời gian sự kiện nằm chờ tăng khó phát hiện.
Một nền tảng xử lý video giới hạn số request ở Subscriber cuối nhưng flatMap phía trước có prefetch; các tác vụ tải ảnh vẫn được khởi động nhiều hơn con số mà nhóm vận hành dự đoán.
Một dịch vụ quản lý khách hàng dùng map để biến đổi DTO nhưng hàm biến đổi có lời gọi HTTP đồng bộ; event loop bị chặn mỗi khi đối tác phản hồi chậm.
Một hệ thống định tuyến dùng flatMap để truy vấn thông tin vận đơn đồng thời; kết quả về khác thứ tự đầu vào nên bước ghi file theo chỉ số ghép nhầm thông tin khách hàng.
Một nền tảng tính cước dùng concatMap để giữ thứ tự phản hồi từ đối tác; khi một yêu cầu bị treo, các yêu cầu phía sau cũng chưa được xử lý và hàng chờ tăng.
Một ứng dụng đề xuất sản phẩm dùng flatMapSequential để giữ thứ tự đầu ra nhưng tạo nhiều tác vụ bên trong; áp lực bộ nhớ tăng khi một tác vụ đầu phản hồi muộn hơn các tác vụ sau.
Một cổng tìm kiếm dùng switchMap theo từ khóa người dùng nhập; phản hồi của truy vấn cũ không còn được chuyển tới giao diện khi từ khóa mới xuất hiện nhưng backend vẫn ghi nhận chi phí của tác vụ đang chạy.
Một hệ thống đặt vé dùng merge để kết hợp các nguồn trạng thái mà không có khóa liên hệ; thứ tự sự kiện xen kẽ làm bộ xử lý hiểu nhầm cùng một giao dịch đã chuyển trạng thái hai lần.
Một ứng dụng phân tích dùng concat để ghép nguồn sự kiện liên tục với luồng cảnh báo tiếp theo; luồng đầu không hoàn tất nên cảnh báo ở luồng sau không bao giờ được subscribe.
Một nền tảng tổng hợp dùng zip để ghép danh sách mã sản phẩm và giá theo từng phần tử; một nguồn phát ít bản ghi hơn làm các phần tử dư của nguồn còn lại không xuất hiện trong kết quả.
Một cổng xem tồn kho dùng combineLatest để tạo báo cáo từ giá và số lượng; khi một nguồn chưa phát giá trị đầu tiên, báo cáo không cập nhật dù nguồn còn lại đã thay đổi nhiều lần.
Một hệ thống đối soát lấy giá trị đầu từ Mono.zip của thông tin khách và ưu đãi; một nguồn hoàn tất rỗng khiến phép kết hợp không tạo kết quả như màn hình đang kỳ vọng.
Một dịch vụ ghi chú dùng filter để loại sự kiện không hợp lệ rồi đặt doOnNext phía sau nhằm kiểm đếm toàn bộ đầu vào; số liệu giám sát chỉ phản ánh những sự kiện đã qua bộ lọc.
Một ứng dụng lưu trữ dùng distinct trên Flux chứa nhiều mã tài khoản khác nhau theo thời gian; trạng thái theo dõi khóa đã thấy tăng mạnh khi luồng chạy lâu mà không kết thúc.
Một nền tảng theo dõi lô hàng dùng distinctUntilChanged để loại cập nhật lặp; hai trạng thái giống nhau nhưng cách xa nhau trong thời gian vẫn được xử lý, trái với giả định chỉ có một sự kiện cho mỗi trạng thái.
Một cổng bán lẻ dùng groupBy theo mã cửa hàng để xử lý hàng triệu sự kiện; chỉ một số group được subscribe nên upstream bị kẹt khi bộ đệm các group không có consumer tăng.
Một dịch vụ tổng hợp log dùng collectList cho Flux không giới hạn số phần tử; yêu cầu xuất báo cáo chờ mãi không hoàn tất và bộ nhớ tăng cùng lượng log.
Một hệ thống báo cáo dùng window theo khoảng thời gian để gom sự kiện; cửa sổ không có phần tử và các khoảng bị trễ khiến bộ phận nghiệp vụ hiểu sai khoảng dữ liệu nào đã được xét.
Một ứng dụng giám sát dùng bufferTimeout để gửi theo lô; khối lượng sự kiện thay đổi khiến kích thước lô không cố định, nhưng downstream lại giả định mọi lô có số phần tử bằng nhau.
Một nền tảng đặt phòng dùng take để chỉ nhận một số sự kiện đầu; subscription của màn hình kết thúc sau khi đủ số phần tử nên màn hình không còn thấy các thay đổi trạng thái tiếp theo.
Một dịch vụ so sánh hai nguồn bằng sequenceEqual trên Flux có tốc độ khác nhau; khi một nguồn không bao giờ hoàn tất, tác vụ kiểm chứng chưa thể trả kết luận cuối cùng.
Một cổng dữ liệu dùng scan để tính tổng tích lũy rồi lưu từng số dư trung gian; sau khi subscription được tái tạo, biến trạng thái tích lũy bắt đầu lại làm báo cáo nối các phiên sai.
Một ứng dụng đo đạc dùng reduce để tính tổng trên luồng cảm biến chạy liên tục; màn hình không nhận giá trị tổng vì phép giảm chỉ phát khi nguồn hoàn tất.
Một hệ thống hiển thị tiến độ dùng share cho Flux lấy từ database; khi subscriber cuối rời đi, nguồn có thể bị hủy và người đăng ký sau lại kích hoạt truy vấn từ đầu.
Một cổng tra cứu chuyển Mono lấy dữ liệu thành cache không thời hạn; sau khi thông tin khách hàng đổi, các subscription sau vẫn nhận bản ghi cũ trong khi nghiệp vụ cần dữ liệu mới.
Một nền tảng thanh toán dùng Mono.fromCallable để bọc truy vấn JDBC đồng bộ nhưng không đổi scheduler; thao tác chờ I/O vẫn chạy trên thread tiếp nhận và làm tăng độ trễ các request khác.
Một dịch vụ tải file gọi subscribeOn với boundedElastic cho nguồn blocking; sau khi thêm publishOn ở giữa pipeline, nhóm đo đạc hiểu nhầm toàn bộ toán tử đều thực thi trên cùng một scheduler.
Một ứng dụng phân tích đặt publishOn sau hàm biến đổi tốn CPU; phần xử lý đắt đỏ ở phía trước vẫn chạy trên scheduler nguồn và làm nghẽn event loop.
Một hệ thống gửi email đặt subscribeOn hai lần ở các vị trí khác nhau; thread thực thi subscription và các toán tử không giống kỳ vọng của nhóm phát triển khi đọc pipeline từ trái sang phải.
Một cổng xử lý ảnh dùng parallel và runOn để chuyển tác vụ CPU sang worker; bước lưu ảnh cuối vẫn truy cập danh sách mutable dùng chung khiến kết quả bị mất một số ảnh.
Một nền tảng báo cáo đặt nhiều lời gọi blocking trong pipeline chạy trên Schedulers.parallel; dưới tải, pool dành cho tính toán bị chiếm và các phép tính khác phản hồi chậm.
Một dịch vụ WebFlux gọi block bên trong chuỗi xử lý request trên event-loop thread; request thất bại hoặc làm nghẽn hệ thống khi lượng truy cập tăng.
Một công cụ đồng bộ dùng boundedElastic cho nhiều thao tác đọc file chậm; số tác vụ chờ xếp hàng tăng dù số thread hoạt động có giới hạn và người dùng không thấy nguyên nhân độ trễ.
Một cổng thanh toán trộn thư viện HTTP bất đồng bộ với JDBC đồng bộ; bộ điều phối tin rằng toàn bộ đường gọi là nonblocking nên không đo thời gian các câu truy vấn khóa thread.
Một ứng dụng lấy dữ liệu từ nhiều khu vực bằng flatMap với mức đồng thời được đặt quá lớn; khi số khu vực tăng đột biến, số kết nối mở tới đối tác vượt quota.
Một nền tảng theo dõi cấu hình tenant dùng ThreadLocal lưu mã khách hàng; khi Reactor đổi thread qua publishOn, log của một số bước mất hoặc dùng nhầm thông tin tenant.
Một dịch vụ bảo mật lưu thông tin người dùng trong Reactor Context; một publisher được subscribe thủ công tách khỏi chuỗi request nên thông tin ngữ cảnh xác thực không có như dự kiến.
Một ứng dụng tổng hợp log dùng doOnEach để ghi correlation ID từ Context; khi chia luồng sang thư viện callback không truyền ngữ cảnh, một số bản ghi không liên kết được với request.
Một cổng vận hành dùng timeout cho Mono gọi API đối tác; lỗi timeout được trả cho client nhưng việc xử lý bên ngoài có thể vẫn tiếp tục và tạo trạng thái khó đối soát.
Một hệ thống chứng từ áp retry cho bước gửi yêu cầu ký số khi gặp lỗi mạng; đối tác có thể đã chấp nhận lần gửi đầu khiến một số tài liệu nhận nhiều chữ ký hoặc sự kiện trùng.
Một ứng dụng đặt vé retryWhen sau lỗi kết nối cơ sở dữ liệu; pipeline chứa bước trừ tiền phía trước nên đăng ký lại khiến giao dịch tài chính bị thực hiện thêm lần.
Một dịch vụ hồ sơ dùng onErrorResume để phát dữ liệu mặc định bất kể loại lỗi; lỗi xác thực bị che giấu và giao diện hiển thị dữ liệu khách hàng như thể request hợp lệ.
Một cổng bán hàng dùng onErrorReturn với sản phẩm rỗng khi nguồn lỗi; báo cáo không còn phân biệt cửa hàng hết hàng thật với dịch vụ kho đang gián đoạn.
Một hệ thống kiểm toán đặt doOnError để ghi log rồi kỳ vọng lỗi đã được xử lý; Subscriber cuối vẫn nhận terminal error và tác vụ bị đánh dấu thất bại.
Một thư viện kiểm tra giá dùng onErrorMap để đổi exception nhưng hàm chuyển đổi không giữ cause gốc; khi phát sinh lỗi hiếm, đội vận hành không thể xác định dịch vụ nguồn gây hỏng.
Một nền tảng xử lý batch sử dụng onErrorContinue để bỏ qua phần tử gây lỗi; khi một toán tử không hỗ trợ đúng cách tiếp tục xử lý, số dòng bị bỏ và trạng thái trung gian khác dự đoán.
Một cổng thanh toán dùng retry với số lần không giới hạn trên lỗi validation vĩnh viễn; hệ thống liên tục gửi cùng payload sai và chiếm hết tài nguyên đối tác.
Một dịch vụ truy vấn thêm delayElements trước bước ghi dữ liệu; khi request bị hủy trong thời gian chờ, nhóm phát triển không xác định được có thao tác nào đã thực sự chạy.
Một hệ thống gửi thông báo đặt doFinally để ghi trạng thái đã hoàn tất; khi người dùng hủy luồng, tín hiệu cancel cũng kích hoạt callback và số lượt xử lý thành công bị đếm dư.
Một ứng dụng quản lý phiên dùng usingWhen để giữ kết nối trong vòng đời publisher; một nhánh bị hủy trước khi đọc hết dữ liệu và thao tác cleanup bất đồng bộ không được quan sát đầy đủ.
Một nền tảng tải tệp ghi chunk bằng Flux rồi kết thúc request khi nhận tín hiệu onComplete; một bước lưu metadata nằm ngoài pipeline thất bại nên file và bản ghi quản lý không khớp.
Một cổng báo cáo nối nhiều Mono bằng then; nhóm phát triển cần kết quả trung gian nhưng downstream chỉ thấy kết quả của publisher sau nên một trường thông tin bị mất.
Một hệ thống phê duyệt dùng flatMap trả về Mono.empty ở trường hợp không đủ quyền; API vẫn hoàn tất bình thường và bên gọi không nhận biết hồ sơ bị từ chối.
Một dịch vụ xử lý kết quả tải ảnh dùng onErrorResume ở cấp toàn pipeline; lỗi ở một ảnh khiến các ảnh phía sau không được xử lý thay vì chỉ một bản ghi bị loại.
Một hệ thống dashboard gắn thêm một subscribe vào pipeline Flux lạnh để bật ghi log; hai subscription độc lập làm gọi lại HTTP và ghi dữ liệu hai lần.
Một ứng dụng kiểm thử dùng StepVerifier.create nhưng không kích hoạt verify trong một số test; pipeline không được subscribe và bài kiểm thử vẫn được báo hoàn tất.
Một dịch vụ Stream phát một lỗi sau ba sự kiện nhưng test chỉ kiểm tra ba giá trị đầu; phiên bản mới thêm sự kiện kết thúc sai mà bộ kiểm thử chưa xác nhận hợp đồng terminal.
Một nền tảng dùng StepVerifier.withVirtualTime để thử timeout; publisher được tạo trước lúc thiết lập virtual scheduler nên bài kiểm thử vẫn phải chờ thời gian thật.
Một bộ kiểm thử pipeline debounce dùng đồng hồ thực và sleep cố định; trên CI chịu tải, kết quả đôi khi mất sự kiện hoặc sai thứ tự dù quy tắc xử lý không đổi.
Một ứng dụng kiểm thử backpressure tạo Subscriber yêu cầu một phần tử mỗi lần; khi nguồn dùng buffer trung gian, test chỉ xác nhận dữ liệu cuối mà bỏ qua số tín hiệu upstream thực phát.
Một dự án dùng TestPublisher để mô phỏng nguồn phá vỡ hợp đồng Reactive Streams; pipeline tự viết có hành vi khác nhau khi gặp onNext đồng thời hoặc terminal signal lặp lại.
Một nền tảng thanh toán mô phỏng lỗi HTTP bằng mock Mono đã được cache; kiểm thử retry không thực sự tạo các lần gọi mới nên không phản ánh cơ chế đăng ký lại khi production gặp lỗi.
Một dịch vụ đo hiệu năng so sánh pipeline Flux tuần tự và song song nhưng không xác nhận dữ liệu đầu ra tương đương; benchmark nhanh hơn nhờ bỏ sót một số tác vụ.
Một cổng thống kê dùng log của operator để theo dõi sự kiện; dưới tải hàng triệu phần tử, lượng log lớn làm độ trễ tăng và che khuất vấn đề backpressure ban đầu.
Một nền tảng giao dịch ghi metric số phần tử ở đầu Flux và coi đó là số bản ghi đã lưu; khi downstream filter hoặc retry, các chỉ số đầu vào và kết quả cuối lệch nhau.
Một dịch vụ tích hợp phát hàng trăm request đồng thời bằng flatMap; hệ thống kiểm thử chỉ xác nhận mã HTTP thành công mà chưa kiểm tra cancel, timeout và giới hạn kết nối.
Một ứng dụng gửi sự kiện từ hàng đợi vào Flux; khi consumer hủy giữa batch, trạng thái xác nhận bên broker và các phần tử đã xử lý trong bộ nhớ không khớp.
Một hệ thống chuyển tác vụ từ callback truyền thống sang Mono; callback có thể gọi thành công và lỗi gần như đồng thời, làm adapter cố phát hai tín hiệu terminal cho một subscription.
Một cổng WebSocket dùng Flux để đẩy trạng thái realtime; khi client mạng yếu, hàng đợi chờ gửi tăng trong khi lớp phát vẫn coi mọi subscriber tiêu thụ nhanh như nhau.
Một nền tảng API dùng WebFlux từ đầu đến cuối nhưng middleware tùy chỉnh gọi hàm đọc file đồng bộ trên event loop; khi tăng lưu lượng, throughput và p99 latency suy giảm bất thường.
Một dịch vụ nghiệp vụ dùng transaction imperative gắn theo thread quanh phương thức trả về Flux R2DBC; khi SQL chỉ chạy lúc subscription ở thread khác, các lần ghi không nằm trong transaction như dự tính.
Một ứng dụng chuyển dữ liệu qua Reactor chạy song song nhiều request và dùng mutable HashMap làm bộ đệm chung; các tác vụ quan sát giá trị cũ hoặc ghi đè khi scheduler thay đổi.
Một hệ thống tìm kiếm đánh dấu đã xử lý một yêu cầu ngay khi dựng Mono; khi client hủy subscription trước thao tác lưu, yêu cầu vẫn bị đánh dấu hoàn tất dù dữ liệu chưa được ghi.
Một nhóm vận hành nâng phiên bản Reactor và điều chỉnh số thread scheduler; kết quả stress test khác trước nhưng bộ đo chưa tách chi phí kết nối, nguồn blocking và hành vi backpressure.
Một nền tảng thương mại chuyển từ imperative loop sang Flux để hợp nhất dữ liệu; kết quả tương tự ở dữ liệu nhỏ nhưng các trường hợp nguồn rỗng, lỗi, hủy và thứ tự phát chưa được kiểm thử.

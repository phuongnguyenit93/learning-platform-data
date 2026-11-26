Một dịch vụ xác thực trả về Mono chứa hồ sơ người dùng khi token hợp lệ; sau một lần refactor, luồng phát ra đúng hồ sơ nhưng không hoàn tất, khiến các bài kiểm thử chỉ đối chiếu giá trị vẫn báo đạt.
API tra cứu sản phẩm trả về Mono rỗng khi không tìm thấy mã hàng; bộ test hiện giả định luôn có một giá trị và khó phân biệt luồng hoàn tất không có dữ liệu với luồng phát lỗi.
Một hàm đặt hàng trả Mono báo hoàn tất sau khi lưu đơn; tại môi trường kiểm thử, thao tác ghi được gọi nhưng publisher không phát tín hiệu complete nên request phía client treo vô thời hạn.
Dịch vụ tính phí trả Mono chứa số tiền bằng không cho đơn miễn phí; bộ test đang nhầm một giá trị bằng không với Mono.empty và bỏ sót khác biệt nghiệp vụ.
Hệ thống tài khoản chuyển lỗi khóa người dùng thành một signal onError của Mono; bài kiểm thử chỉ xác minh không phát giá trị nên cũng chấp nhận nhầm luồng hoàn tất bình thường.
Một API đọc hồ sơ có thể phát lỗi nghiệp vụ với message cụ thể; sau khi thêm tầng ánh xạ ngoại lệ, loại lỗi còn đúng nhưng mã lỗi và nội dung giải thích đến client bị thay đổi ngoài ý muốn.
Dịch vụ đặt lịch dùng onErrorResume để trả dữ liệu dự phòng khi hệ thống lịch chính lỗi; bộ test chỉ kiểm tra kết quả cuối mà không nhận ra trường hợp nguồn chính vẫn hoạt động bình thường cũng đi nhầm nhánh fallback.
Một luồng Mono sử dụng switchIfEmpty để gọi nguồn dữ liệu thứ hai khi nguồn đầu không có bản ghi; bài kiểm thử hiện chỉ chạy trường hợp có dữ liệu, khiến nhánh rỗng mới bổ sung chưa được kiểm chứng.
Dịch vụ tạo hóa đơn trả về Mono lỗi khi thông tin thuế không hợp lệ; một operator xử lý lỗi vô tình thay thế lỗi bằng dữ liệu mặc định và ứng dụng tiếp tục phát hành hóa đơn.
Ứng dụng ngân hàng ghép hai Mono để tạo bản tóm tắt tài khoản; một nguồn có thể hoàn tất rỗng, khiến publisher kết hợp không phát giá trị mặc dù nguồn còn lại đã trả dữ liệu.
Luồng Flux tải lịch sử đơn hàng theo trang và phát các bản ghi theo thứ tự thời gian; một lần đổi sang xử lý bất đồng bộ làm các bản ghi đến consumer không còn theo đúng thứ tự mong đợi.
Nhà bán lẻ chuyển đổi Flux mã sản phẩm sang chi tiết sản phẩm bằng flatMap; yêu cầu đến các dịch vụ ngoài có độ trễ khác nhau khiến kiểm thử so sánh thứ tự cố định liên tục thất bại.
Pipeline xuất dữ liệu báo cáo dùng concatMap cho các tác vụ theo lô; bộ test chỉ kiểm tra tập giá trị nên không phát hiện khi một thay đổi khiến thứ tự phát bản ghi bị đảo.
Một Flux đọc dữ liệu cảm biến có bộ lọc bỏ giá trị bất thường; bài kiểm thử chỉ chứa mẫu hợp lệ nên bản cập nhật gần đây vô tình giữ lại nhiều giá trị lẽ ra cần loại.
Dịch vụ gợi ý sản phẩm dùng distinct trên luồng sản phẩm theo mã hàng; sau khi thay kiểu khóa, cùng sản phẩm xuất hiện nhiều lần nhưng test chỉ kiểm số bản ghi trước khi khử trùng.
Ứng dụng phân tích đơn hàng dùng take để lấy số giao dịch mới nhất; bộ test kiểm đúng số phần tử nhưng không phát hiện upstream tiếp tục thực hiện công việc tốn tài nguyên sau khi downstream hủy đăng ký.
Dịch vụ báo cáo ghép nhiều Flux bằng merge; thời điểm phản hồi của các nguồn thay đổi giữa các lần chạy, khiến một bài test khẳng định thứ tự tuyệt đối bị flaky dù nội dung kết hợp vẫn đầy đủ.
Luồng gửi thông báo ưu tiên ghép các publisher bằng concat; một publisher đầu tiên không hoàn tất làm các thông báo từ publisher kế tiếp không bao giờ được phát.
Một Flux sử dụng buffer để gộp bản ghi theo nhóm nhỏ trước khi ghi đích; khi nguồn kết thúc với nhóm cuối chưa đủ kích thước, bộ test không phát hiện các bản ghi cuối bị bỏ sót.
Ứng dụng tính tổng số lượng giao dịch bằng reduce trên Flux; khi nguồn rỗng, hợp đồng đầu ra không giống kỳ vọng của nhóm báo cáo và test hiện chưa kiểm trường hợp này.
Dịch vụ gợi ý phát các kết quả bằng Flux rồi lỗi sau phần tử thứ ba; bộ test chỉ kiểm onError mà không xác nhận ba giá trị đã phát trước lỗi nên bỏ qua sai lệch dữ liệu từng phần.
Pipeline WebFlux nhận nguồn Flux đôi khi báo lỗi sau khi xử lý một phần tệp; nhóm vận hành cần phân biệt trường hợp lỗi giữa dòng với luồng hoàn tất bình thường để tránh xuất báo cáo thiếu.
Một dịch vụ đồng bộ phát Flux từ nguồn có tín hiệu onComplete sớm hơn dự kiến; test chỉ kiểm các phần tử đầu nên không phát hiện hàng chục bản ghi cuối không bao giờ xuất hiện.
Luồng xử lý ảnh chuyển ngoại lệ tại một item thành fallback rồi tiếp tục Flux; khi sửa operator, luồng lại kết thúc ngay sau lỗi đầu tiên khiến các ảnh còn lại không được xử lý.
Ứng dụng cập nhật tồn kho gửi Flux gồm nhiều giao dịch và sử dụng onErrorContinue; sau lỗi chuyển đổi ở một bản ghi, bài test không xác minh liệu các bản ghi còn lại được xử lý như hợp đồng.
API tra cứu trạng thái vận đơn dùng Mono có side effect khi được subscribe; bài test vô tình subscribe hai lần làm gọi dịch vụ đối tác hai lần dù bản thân publisher chỉ mô tả một yêu cầu.
Một nhà cung cấp dữ liệu trả Flux được xây dựng từ nguồn có trạng thái; việc tạo StepVerifier khác thời điểm làm các bài test dùng chung nguồn ảnh hưởng lẫn nhau và cho kết quả không ổn định.
Một luồng cập nhật bảng giá là hot publisher phát sự kiện trước khi StepVerifier subscribe; bài test kỳ vọng nhận đầy đủ lịch sử và thỉnh thoảng thiếu bản tin đầu.
Ứng dụng đọc trạng thái cảm biến từ nguồn lạnh tạo dữ liệu cho mỗi lần subscribe; bộ test dùng nhiều subscriber nhưng lại giả định mọi subscriber sẽ dùng chung một lần đọc dữ liệu.
Một nhóm phát triển dùng TestPublisher giả lập nguồn thanh toán, chủ động phát một số sự kiện rồi hoàn tất; bộ test không phát hiện operator trung gian bỏ qua sự kiện được phát ngay trước onComplete.
Bộ test dùng TestPublisher phát lỗi sau một giá trị thành công; sau khi thay đổi logic recover, downstream không còn nhận đúng loại exception nhưng kiểm thử hiện chỉ đếm số signal.
Một API nhận dữ liệu từ thiết bị cũ đôi khi phát hai terminal signal trái giao thức; nhóm kỹ thuật muốn thử phản ứng của chuỗi operator trước nguồn Publisher không tuân thủ hợp đồng Reactive Streams.
Hệ thống xử lý thanh toán sử dụng TestPublisher để phát sự kiện trước khi downstream có request; bộ test hiện không mô phỏng tình huống nguồn vi phạm backpressure nên bỏ qua lỗi phát quá nhu cầu.
Dịch vụ đăng ký sự kiện chịu lỗi từ upstream trả onError sau khi đã onComplete; nhóm phát triển cần xác minh tín hiệu bất thường không làm tạo thêm tác động nghiệp vụ trong downstream.
Một luồng Flux có consumer yêu cầu từng phần tử thay vì toàn bộ danh sách; sau khi tối ưu buffering, publisher phát quá số lượng đã request khiến giao thức backpressure không còn đúng.
Ứng dụng ghi dữ liệu IoT giới hạn tốc độ tiêu thụ, chỉ request hai bản ghi mỗi lần; bài test mặc định nhận toàn bộ ngay nên không tái hiện được áp lực từ subscriber chậm.
Dịch vụ lấy danh sách hàng nghìn giao dịch sử dụng StepVerifier với initial request rất nhỏ; một operator mới không chuyển tiếp nhu cầu downstream khiến luồng đứng yên dù upstream còn dữ liệu.
Luồng tổng hợp sự kiện dùng limitRate để chia nhỏ số lượng yêu cầu upstream; bộ test chỉ kiểm kết quả cuối nên không phát hiện thay đổi bất thường trong mẫu request gây quá tải nguồn.
Ứng dụng xử lý sự kiện ngoài thời gian thực dùng onBackpressureBuffer; khi consumer chậm, bộ đệm tăng và test hiện không kiểm hành vi lúc giới hạn bộ đệm bị vượt.
Hệ thống gửi thông báo dùng onBackpressureDrop khi lượng sự kiện vượt sức xử lý; nhóm sản phẩm phát hiện một số thông báo ít quan trọng biến mất nhưng bộ test không ghi nhận những sự kiện đã bị drop.
Luồng cập nhật vị trí xe chỉ cần dữ liệu mới nhất khi client không theo kịp; sau khi đổi chính sách backpressure, test không phân biệt sự kiện cũ bị bỏ và sự kiện mới nhất được giữ lại.
Một ứng dụng theo dõi đơn hàng có subscriber hủy sau khi nhận giá trị đầu; operator doFinally vẫn được gọi nhưng metric ghi nhận đây là completion thay vì cancellation.
Worker xử lý yêu cầu qua Flux và giải phóng một tài nguyên khi subscription bị cancel; bài kiểm thử chỉ mô phỏng hoàn tất bình thường nên rò rỉ tài nguyên sau khi client ngắt kết nối không được phát hiện.
Một API dùng Flux.usingWhen để mở và đóng phiên làm việc bất đồng bộ; khi upstream thất bại, bài test chưa kiểm tra tín hiệu cuối và số lần đóng tài nguyên.
Ứng dụng lấy cấu hình từ PublisherProbe để biết có đăng ký vào nhánh fallback hay không; sau refactor, kết quả trả về đúng nhưng một nhánh dự phòng tốn phí lại bị subscribe không cần thiết.
Dịch vụ tính tỷ giá chỉ gọi backend dự phòng khi nguồn chính rỗng; bộ test nhận đúng kết quả nhưng không biết publisher dự phòng đã bị subscribe trước khi thực sự cần dùng.
Luồng thanh toán có nhánh xác thực và nhánh rút gọn khi dữ liệu người dùng thiếu; kết quả cuối giống nhau trong một số ca nên bộ test cần phân biệt nhánh publisher nào thực tế được yêu cầu.
Ứng dụng dự trữ kho dùng PublisherProbe để quan sát cancel và request khi một tác vụ bị timeout; nhóm kiểm thử chỉ xác minh giá trị trả về mà bỏ sót subscription vẫn hoạt động sau timeout.
Pipeline định tuyến lỗi có fallback Mono không bao giờ được sử dụng ở đường thành công; sau thay đổi, fallback bị subscribe dù giá trị của nguồn chính vẫn được trả ra.
Dịch vụ xác minh mã giảm giá sử dụng Mono.delay để chờ trạng thái đối tác; test dựa vào đồng hồ thật phải đợi vài giây mỗi lần, khiến bộ kiểm thử chậm và đôi khi thất bại khi CI quá tải.
Một luồng Flux dùng interval để tạo dữ liệu định kỳ trong một giờ; bộ test cần xác nhận đúng số sự kiện và thời điểm logic mà không mất một giờ chạy thật.
Chức năng gia hạn phiên tự động dùng timeout nếu upstream không phát dữ liệu sau một khoảng chờ; test có thể nhận lỗi quá sớm hoặc quá muộn khi scheduler trên máy CI bận.
Dịch vụ gửi thông báo có retryWhen với các khoảng backoff tăng dần; bộ test chạy trên đồng hồ thật mất nhiều thời gian và khó kiểm số lần thử trước khi phát thành công.
Một quy trình giao hàng dùng delayElements trước khi phát các trạng thái tiếp theo; bài kiểm thử dùng virtual time nhưng vẫn bị treo khi publisher được tạo trước lúc scheduler ảo được kích hoạt.
Nhóm kỹ thuật kiểm thử luồng sử dụng StepVerifier.withVirtualTime; một publisher phụ tạo timer trên scheduler cố định bên ngoài virtual scheduler làm một phần bài test vẫn phụ thuộc thời gian thực.
Ứng dụng phát dữ liệu thời gian thực dùng window theo khoảng thời gian; khi sự kiện đến đúng ranh giới cửa sổ, bài test thỉnh thoảng phân loại khác nhau vì nguồn thời gian và scheduler không nhất quán.
Dịch vụ tra cứu đặt timeout rồi chuyển sang fallback; khi phản hồi chính đến sát thời hạn, kiểm thử có lúc nhận dữ liệu thật và có lúc nhận dữ liệu dự phòng tùy lịch chạy thread.
Ứng dụng cảnh báo phát sự kiện đầu tiên sau khoảng im lặng kéo dài; StepVerifier dùng thời gian ảo nhưng không xác minh được rằng không có onNext nào xuất hiện trước mốc cảnh báo.
Nhóm phát triển thêm delaySubscription cho một truy vấn Mono; bộ test chỉ kiểm kết quả và bỏ qua việc upstream bị subscribe quá sớm trước khi hết thời gian chờ.
Một Flux có retry với giới hạn số lần gọi nguồn ngoài; sau khi thay logic, nguồn được subscribe thêm một lần nhưng test chỉ kiểm rằng cuối cùng có dữ liệu trả về.
Dịch vụ xử lý giao dịch chậm chạy trên boundedElastic scheduler còn một bước map tốn CPU; khi test sử dụng thứ tự cứng giữa các tác vụ độc lập, kết quả thay đổi theo số luồng CI.
Một Mono sử dụng publishOn để đổi ngữ cảnh thực thi; bộ test chỉ xác minh giá trị mà không nhận ra một thao tác vốn phải chạy ngoài event-loop đã chuyển lại chạy trên thread không phù hợp.
Ứng dụng truyền trace ID qua Reactor Context cho các bước xử lý một request; sau khi thêm operator bất đồng bộ, log downstream mất trace ID nhưng dữ liệu trả về vẫn chính xác.
Dịch vụ thanh toán đọc tenant ID từ Reactor Context để chọn cấu hình; bài test chỉ kiểm giá trị kết quả và không phát hiện tenant ID bị thiếu khi contextWrite được đặt sai vị trí trong chuỗi.
Một Flux xử lý yêu cầu của hai người dùng đồng thời dựa vào Reactor Context; các bài test chia sẻ biến ThreadLocal làm dữ liệu tenant của một người lẫn sang người còn lại.
Nhóm bảo mật muốn kiểm thử nhánh deferContextual trong Mono; khi không có khóa phân quyền trong Reactor Context, luồng phải biểu hiện khác với trường hợp khóa có mặt nhưng các test hiện chưa phân biệt.
Một API WebFlux ghi correlation ID vào Context khi có subscriber; một helper test subscribe trực tiếp ngoài request chain làm các tín hiệu thiếu context dù logic nghiệp vụ có thể chạy đúng trong ứng dụng.
Ứng dụng gọi dịch vụ downstream bằng Flux rồi đổi scheduler nhiều lần; thông tin locale trong Reactor Context vẫn cần đi qua luồng bất đồng bộ, nhưng test chỉ chạy một luồng đơn giản trên cùng thread.
Thư viện kiểm thử dùng StepVerifier.expectAccessibleContext để kiểm metadata từ upstream; sau refactor, một Context key bị đổi tên nhưng các assert chỉ tập trung vào các phần tử onNext.
Pipeline phân quyền phụ thuộc một Context key do tầng gateway cấp; test có context mẫu hợp lệ nên chưa phát hiện trường hợp publisher bị subscribe trực tiếp mà không có thông tin quyền.
Một service sử dụng verifyThenAssertThat để kiểm tra các giá trị bị drop và sự kiện bị discard; sau tối ưu operator, dữ liệu hiển thị đúng nhưng các phần tử bị bỏ không được quan sát như trước.
Luồng xác thực người dùng phát lỗi do token sai và do backend tạm ngừng; bộ test nhận thông báo lỗi giống nhau nên không kiểm tra đúng loại exception đi qua từng nhánh xử lý.
Một ứng dụng gom dữ liệu Flux với timeout và fallback dùng nguồn TestPublisher có tín hiệu không ổn định; kiểm thử hiện lúc thất bại do thời gian, lúc do bản tin đến chậm, khiến nguyên nhân khó chẩn đoán.
Nhóm triển khai một thay đổi trong Reactor pipeline có side effect doOnNext; kiểm thử subscribe lại cùng publisher để quan sát metric, vô tình kích hoạt side effect thêm lần nữa và tạo kết quả không lặp lại.
Một API đọc tệp lớn thành Flux các khối dữ liệu, nhưng client hủy giữa chừng; bài test chỉ kiểm kết quả đọc hết tệp nên không phát hiện việc subscription nguồn và bộ đọc tệp vẫn tiếp tục hoạt động.
Luồng gửi thông báo tích hợp nhiều publisher với nhánh lỗi và nhánh hoàn tất; khi một lỗi upstream bị chuyển thành onComplete, bộ test tập trung vào dữ liệu phát ra không phân biệt được hai tín hiệu kết thúc.
Ứng dụng phân tích sử dụng TestPublisher tạo nguồn phát record quá nhanh so với nhu cầu downstream; trong một số cấu hình, operator lập tức từ chối chuỗi tín hiệu vi phạm trong khi bộ test trước chỉ dùng nguồn hợp lệ.

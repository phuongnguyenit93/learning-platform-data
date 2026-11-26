Bạn giải thích lập trình reactive khác lập trình đồng bộ tuần tự ở cách mô hình hóa dữ liệu và thời gian như thế nào?
Bạn sẽ lựa chọn Reactor Core thay vì CompletableFuture hoặc Java Stream trong những tình huống nào?
Bạn mô tả vai trò của Project Reactor trong hệ sinh thái Reactive Streams của Java như thế nào?
Bạn phân biệt sự khác nhau giữa khai báo pipeline và thực sự thực thi pipeline trong Reactor ra sao?
Bạn giải thích lý do một publisher thường chưa phát tín hiệu trước khi có subscription như thế nào?
Bạn phân tích vai trò của Publisher, Subscriber, Subscription và Processor trong Reactive Streams như thế nào?
Bạn mô tả chuỗi tín hiệu onSubscribe, onNext, onError và onComplete của một subscription hợp lệ ra sao?
Bạn giải thích vì sao một subscription chỉ được kết thúc bởi một tín hiệu terminal như thế nào?
Bạn sẽ phân biệt tín hiệu dữ liệu với tín hiệu điều khiển trong một pipeline Reactor ra sao?
Bạn đánh giá khả năng phối hợp giữa thư viện reactive khác và Reactor dựa trên hợp đồng nào?
Bạn phân biệt Mono và Flux theo số lượng phần tử và ngữ nghĩa hoàn tất như thế nào?
Bạn sẽ chọn Mono thay vì Flux để biểu diễn một thao tác bất đồng bộ dựa trên tiêu chí nào?
Bạn giải thích cách Mono biểu diễn kết quả rỗng so với một giá trị null như thế nào?
Bạn thiết kế API trả về Flux khi dữ liệu có thể xuất hiện dần theo thời gian ra sao?
Bạn phân biệt Mono<Void> với Mono chứa giá trị nghiệp vụ khi biểu diễn một thao tác chỉ cần tín hiệu hoàn tất như thế nào?
Bạn sẽ mô tả tác động của việc trả về Mono.empty() đối với các toán tử downstream ra sao?
Bạn phân biệt Flux.empty(), Flux.never() và Flux.error() theo hành vi tín hiệu như thế nào?
Bạn giải thích cách Flux.just và Flux.fromIterable tạo nguồn dữ liệu ra sao?
Bạn lựa chọn Mono.just, Mono.defer và Mono.fromSupplier dựa trên thời điểm tính toán giá trị như thế nào?
Bạn giải thích vì sao Mono.justOrEmpty thích hợp khi dữ liệu đầu vào có thể vắng mặt như thế nào?
Bạn sẽ dùng Flux.range, Flux.generate hoặc Flux.create cho các kiểu nguồn dữ liệu nào?
Bạn phân biệt Flux.generate và Flux.create về mô hình phát phần tử và trạng thái nguồn như thế nào?
Bạn thiết kế nguồn dữ liệu bằng Flux.defer để mỗi subscription nhận trạng thái riêng như thế nào?
Bạn sẽ chuyển đổi một CompletionStage sang Mono mà vẫn quản lý lỗi và hủy tác vụ ra sao?
Bạn giải thích khi nào một hàm trả Publisher không nên tự gọi subscribe bên trong như thế nào?
Bạn sẽ mô tả hậu quả của việc gọi block trong một luồng xử lý reactive như thế nào?
Bạn phân tích sự khác biệt giữa subscribe với callback và sử dụng một Subscriber tùy chỉnh ra sao?
Bạn xác định lúc nào một pipeline Reactor thực sự bắt đầu tạo tác dụng phụ như thế nào?
Bạn giải thích sự khác nhau giữa subscription và sự kiện phát dữ liệu đầu tiên như thế nào?
Bạn sẽ kiểm soát vòng đời một Disposable khi trực tiếp subscribe vào một nguồn lâu dài ra sao?
Bạn phân biệt onComplete và cancel trong vòng đời một subscription như thế nào?
Bạn giải thích cách Subscription.request tác động đến nhu cầu nhận phần tử của Subscriber ra sao?
Bạn sẽ mô tả ý nghĩa của request(n) trong giao thức backpressure như thế nào?
Bạn phân biệt backpressure với buffering và rate limiting trong một hệ thống reactive ra sao?
Bạn sẽ đánh giá rủi ro khi upstream phát nhanh hơn downstream có thể xử lý như thế nào?
Bạn giải thích vì sao request không có giới hạn có thể gây áp lực tài nguyên cho downstream như thế nào?
Bạn sẽ áp dụng BaseSubscriber để điều khiển demand thủ công trong tình huống nào?
Bạn thiết kế quy tắc request theo lô để cân bằng throughput và bộ nhớ như thế nào?
Bạn giải thích tác động của prefetch trên các toán tử có nguồn con đến lượng dữ liệu đang chờ ra sao?
Bạn phân tích cách limitRate thay đổi nhịp yêu cầu upstream như thế nào?
Bạn xác định khi nào onBackpressureBuffer là lựa chọn phù hợp và cần giới hạn bộ đệm ra sao?
Bạn so sánh onBackpressureDrop và onBackpressureLatest khi xử lý một nguồn cập nhật liên tục như thế nào?
Bạn làm thế nào để không làm mất sự kiện nghiệp vụ quan trọng khi downstream bị quá tải?
Bạn giải thích những trường hợp một nguồn push bất đồng bộ không thể tuân thủ demand ngay lập tức như thế nào?
Bạn lựa chọn chiến lược xử lý overflow cho một nguồn Flux.create theo đặc điểm nghiệp vụ nào?
Bạn sẽ đo đạc backpressure trong pipeline thông qua backlog và thời gian chờ như thế nào?
Bạn xác định đâu là ranh giới cần chủ động giảm tải thay vì tiếp tục tăng bộ đệm ra sao?
Bạn phân biệt toán tử map và flatMap khi biến đổi một giá trị thành publisher như thế nào?
Bạn sẽ chọn concatMap thay cho flatMap khi cần bảo đảm thứ tự xử lý ra sao?
Bạn phân tích những đánh đổi giữa flatMap, flatMapSequential và concatMap về concurrency, latency và thứ tự như thế nào?
Bạn giải thích cách switchMap phản ứng khi nguồn phát một giá trị mới trong lúc publisher cũ chưa hoàn tất như thế nào?
Bạn sẽ thiết kế pipeline tra cứu bất đồng bộ theo từng phần tử mà không tạo blocking call ra sao?
Bạn phân biệt filter, handle và mapNotNull khi biến đổi hoặc loại bỏ phần tử như thế nào?
Bạn sử dụng doOnNext và map khác nhau thế nào khi cần ghi log và thay đổi dữ liệu?
Bạn giải thích vì sao các toán tử doOn không nên mang logic nghiệp vụ có tác dụng phụ khó lặp lại như thế nào?
Bạn lựa chọn take, skip, takeWhile và skipWhile theo điều kiện dừng đọc dữ liệu ra sao?
Bạn phân biệt takeUntil và takeWhile trong cách xác định phần tử cuối cùng được phát như thế nào?
Bạn giải thích tác động của distinct và distinctUntilChanged đến trạng thái và sử dụng bộ nhớ ra sao?
Bạn sẽ sắp xếp dữ liệu với sort trong Flux và đánh giá chi phí bộ nhớ của thao tác này như thế nào?
Bạn phân biệt reduce, scan và collectList ở cách phát kết quả tích lũy như thế nào?
Bạn lựa chọn buffer, window và groupBy theo mục tiêu xử lý nhóm dữ liệu ra sao?
Bạn giải thích vì sao groupBy có thể gặp vấn đề khi nhóm được tạo quá nhiều nhưng không được tiêu thụ như thế nào?
Bạn thiết kế xử lý từng batch bằng bufferTimeout để cân bằng kích thước lô và độ trễ ra sao?
Bạn xử lý dữ liệu có tính cửa sổ thời gian bằng windowTimeout theo những rủi ro nào?
Bạn sẽ tránh tích lũy toàn bộ Flux vào bộ nhớ khi nguồn dữ liệu rất lớn như thế nào?
Bạn phân biệt zip, combineLatest và merge khi kết hợp nhiều publisher ra sao?
Bạn sẽ xử lý một Mono.empty() nằm trong Mono.zip để không làm mất kết quả ngoài ý muốn như thế nào?
Bạn giải thích cách concat và merge khác nhau về thứ tự subscription và thứ tự dữ liệu như thế nào?
Bạn lựa chọn mergeSequential khi cần subscription đồng thời nhưng vẫn giữ thứ tự kết quả như thế nào?
Bạn sẽ dùng zipWith để kết hợp hai luồng có tốc độ phát khác nhau ra sao?
Bạn phân tích ảnh hưởng của publisher hoàn tất sớm đối với các toán tử kết hợp như thế nào?
Bạn phân biệt then, thenReturn và thenMany khi quan tâm đến tín hiệu hoàn tất hơn là giá trị trước đó như thế nào?
Bạn giải thích cách ignoreElements thay đổi ý nghĩa của một Flux như thế nào?
Bạn lựa chọn defaultIfEmpty và switchIfEmpty khi cần phương án dự phòng cho nguồn rỗng ra sao?
Bạn giải thích vì sao switchIfEmpty kết hợp defer có thể giúp tránh thực thi fallback quá sớm như thế nào?
Bạn sẽ xử lý nhánh dữ liệu rỗng trong một chuỗi flatMap mà vẫn giữ ngữ nghĩa nghiệp vụ ra sao?
Bạn phân biệt delayElements, delaySubscription và timeout về vị trí tác động đến luồng như thế nào?
Bạn sẽ dùng interval để tạo các tick định kỳ và kiểm soát vòng đời subscription ra sao?
Bạn mô tả rủi ro tích tụ tác vụ khi dùng interval phát nhanh hơn khả năng downstream tiêu thụ như thế nào?
Bạn phân biệt debounce, sample và throttle trong xử lý một luồng tương tác có tần suất cao như thế nào?
Bạn lựa chọn retry và repeat dựa trên điểm khác nhau giữa lỗi và hoàn tất bình thường như thế nào?
Bạn giải thích sự khác biệt giữa onErrorReturn và onErrorResume khi phục hồi sau lỗi ra sao?
Bạn dùng onErrorMap để chuyển đổi lỗi kỹ thuật thành lỗi miền nghiệp vụ theo tiêu chí nào?
Bạn phân tích tác động của onErrorComplete đối với khả năng phát hiện lỗi hệ thống như thế nào?
Bạn đánh giá những rủi ro khi dùng onErrorContinue trong một pipeline có trạng thái ra sao?
Bạn xác định vị trí đặt toán tử xử lý lỗi để chỉ phục hồi một phần thay vì toàn bộ pipeline như thế nào?
Bạn sẽ áp dụng retryWhen với backoff và jitter để tránh quá tải hệ thống phụ thuộc ra sao?
Bạn phân biệt lỗi tạm thời với lỗi không thể retry trong một chuỗi thao tác bất đồng bộ như thế nào?
Bạn giới hạn số lần retry và ngân sách thời gian xử lý đầu cuối như thế nào?
Bạn giải thích vì sao retry có thể chạy lại nguồn và tạo tác dụng phụ nhiều lần như thế nào?
Bạn sẽ bảo vệ một thao tác thay đổi dữ liệu khỏi lỗi xử lý trùng khi áp dụng retry ra sao?
Bạn phân tích ảnh hưởng của timeout tới publisher đang chạy và các tác vụ hạ nguồn như thế nào?
Bạn lựa chọn fallback khi timeout nhưng vẫn cần biết thao tác trước có thể đã thành công như thế nào?
Bạn sẽ ghi nhận và phân loại lỗi terminal trong một Flux dài hạn ra sao?
Bạn giải thích cách doOnError khác với onErrorResume về tác dụng lên dòng tín hiệu như thế nào?
Bạn chọn checkpoint để xác định vị trí lỗi trong chuỗi toán tử như thế nào?
Bạn giải thích tác động của lỗi trong một inner publisher đối với flatMap đang xử lý nhiều phần tử ra sao?
Bạn thiết kế xử lý lỗi riêng cho từng phần tử mà không làm ngừng toàn bộ luồng như thế nào?
Bạn phân biệt delayError trong các toán tử ghép với hành vi dừng ngay khi lỗi như thế nào?
Bạn sẽ xử lý việc hủy các tác vụ đang chạy khi downstream không còn cần kết quả ra sao?
Bạn phân biệt Scheduler và thread trong Reactor ở mức trừu tượng lập lịch như thế nào?
Bạn giải thích hành vi thực thi mặc định của một pipeline khi không có subscribeOn hoặc publishOn ra sao?
Bạn dùng subscribeOn để chuyển thời điểm và môi trường subscription theo những mục đích nào?
Bạn phân biệt ảnh hưởng của publishOn và subscribeOn đối với các toán tử trước và sau chúng như thế nào?
Bạn lý giải vì sao thêm nhiều publishOn có thể tăng chi phí chuyển ngữ cảnh như thế nào?
Bạn chọn Schedulers.boundedElastic cho lời gọi blocking không thể loại bỏ dựa trên tiêu chí nào?
Bạn phân tích rủi ro dùng Schedulers.parallel cho tác vụ blocking kéo dài ra sao?
Bạn so sánh Schedulers.single, parallel và boundedElastic theo loại công việc và khả năng mở rộng như thế nào?
Bạn sẽ chuyển lời gọi JDBC blocking sang Mono.fromCallable kết hợp scheduler phù hợp ra sao?
Bạn xác định vị trí bọc một thư viện blocking để tránh chiếm dụng event loop như thế nào?
Bạn giải thích cách parallel và runOn phân phối xử lý dữ liệu CPU-bound trong ParallelFlux ra sao?
Bạn sẽ quyết định khi nào parallelization cải thiện throughput và khi nào làm tăng overhead như thế nào?
Bạn làm thế nào để bảo toàn thứ tự kết quả khi một pipeline xử lý đồng thời trên nhiều scheduler?
Bạn phân tích sự khác nhau giữa subscribeOn ở nhiều vị trí và publishOn nối tiếp trong một pipeline như thế nào?
Bạn sẽ tránh tạo scheduler mới không cần thiết ở mỗi request bằng cách nào?
Bạn kiểm soát vòng đời của scheduler tùy chỉnh để không rò rỉ thread như thế nào?
Bạn giải thích cách cancellation đi qua một ranh giới scheduler và tác động tới công việc đang chạy ra sao?
Bạn đánh giá hiện tượng nghẽn scheduler dựa trên số tác vụ đang chờ và độ trễ như thế nào?
Bạn sử dụng Reactor Context để mang dữ liệu theo subscription thay vì ThreadLocal như thế nào?
Bạn giải thích vì sao ThreadLocal không luôn đáng tin cậy sau khi pipeline đổi scheduler ra sao?
Bạn sẽ truyền correlation ID hoặc thông tin truy vết qua Context bằng những thao tác nào?
Bạn phân biệt contextWrite và deferContextual trong việc ghi và đọc Context như thế nào?
Bạn giải thích hướng truyền Context trong chuỗi toán tử và hệ quả khi đặt contextWrite sai vị trí ra sao?
Bạn xác định loại dữ liệu nào phù hợp để lưu trong Context và loại nào không nên lưu như thế nào?
Bạn sẽ kết hợp Reactor Context với logging MDC mà không làm rò rỉ thông tin giữa các request ra sao?
Bạn xử lý sự khác biệt giữa trạng thái theo subscription và trạng thái chia sẻ trên toàn bộ service như thế nào?
Bạn phân biệt cold publisher với hot publisher theo cách mỗi subscriber nhìn thấy dữ liệu ra sao?
Bạn giải thích hành vi khi hai subscriber đăng ký độc lập vào một cold Flux như thế nào?
Bạn sẽ chia sẻ một nguồn phát đắt đỏ cho nhiều subscriber mà vẫn kiểm soát vòng đời nguồn ra sao?
Bạn phân tích sự khác biệt giữa publish().autoConnect và publish().refCount trong việc khởi động và dừng nguồn như thế nào?
Bạn so sánh share và cache về việc chia sẻ nguồn và phát lại dữ liệu cũ như thế nào?
Bạn lựa chọn replay để phục vụ subscriber đến muộn theo nhu cầu giữ lịch sử nào?
Bạn phân biệt hot publisher mất dữ liệu trước subscription và nguồn có khả năng replay ra sao?
Bạn sẽ quản lý số subscriber tối thiểu trước khi kết nối tới một ConnectableFlux như thế nào?
Bạn xử lý subscriber quá chậm khi cùng nhận dữ liệu từ một hot source như thế nào?
Bạn đánh giá các rủi ro của cache không giới hạn đối với một Flux có thời gian sống dài như thế nào?
Bạn giải thích lý do Sinks được dùng để kết nối nguồn imperative với pipeline Reactor như thế nào?
Bạn phân biệt Sinks.One, Sinks.Empty và Sinks.Many theo kiểu tín hiệu cần phát ra sao?
Bạn chọn Sinks.many().multicast, unicast hoặc replay theo yêu cầu về subscriber như thế nào?
Bạn đánh giá hệ quả của một multicast sink khi chưa có subscriber sẵn sàng nhận dữ liệu như thế nào?
Bạn thiết kế phương án phát tín hiệu bằng tryEmitNext và xử lý EmitResult như thế nào?
Bạn phân biệt tryEmitNext và emitNext với EmissionFailureHandler trong việc đối phó xung đột phát tín hiệu ra sao?
Bạn giải thích nguy cơ nhiều thread đồng thời gọi emit tới một sink mà không xử lý kết quả như thế nào?
Bạn giới hạn buffer của sink để không tăng sử dụng bộ nhớ vô hạn như thế nào?
Bạn xác định khi nào nên phát terminal signal vào sink và ngăn việc phát tiếp sau đó ra sao?
Bạn sẽ tránh dùng Sinks làm bộ lưu thông điệp bền vững cho nghiệp vụ quan trọng bằng cách nào?
Bạn phân tích cách một sink có thể phát tín hiệu tới nhiều downstream với nhu cầu nhận khác nhau như thế nào?
Bạn sẽ kiểm soát việc tạo sink theo từng session để tránh dùng chung sai phạm vi ra sao?
Bạn dùng Flux.using hoặc Mono.using để gắn vòng đời tài nguyên với subscription như thế nào?
Bạn phân biệt using và usingWhen khi quá trình mở hoặc đóng tài nguyên là bất đồng bộ như thế nào?
Bạn đảm bảo cleanup tài nguyên khi publisher hoàn tất, lỗi hoặc bị hủy ra sao?
Bạn phân biệt doFinally với doOnComplete, doOnError và doOnCancel về các trường hợp được gọi như thế nào?
Bạn sẽ thiết kế thao tác đóng tài nguyên để tránh rò rỉ khi downstream gọi cancel giữa chừng ra sao?
Bạn lý giải việc subscribe thủ công trong tầng service có thể gây mất kiểm soát cancellation như thế nào?
Bạn kiểm soát giới hạn kết nối hoặc handle khi một request tạo nhiều inner publishers như thế nào?
Bạn xử lý giao dịch bất đồng bộ để cleanup nhất quán khi flatMap bị lỗi ra sao?
Bạn lựa chọn toán tử nào để tránh tạo tác dụng phụ mới sau khi subscription đã hủy?
Bạn sẽ phối hợp doOnSubscribe và doFinally để đo thời gian xử lý từng subscription như thế nào?
Bạn dùng Hooks.onOperatorDebug trong giai đoạn chẩn đoán và cân nhắc tác động hiệu năng ra sao?
Bạn giải thích lý do stack trace của pipeline reactive có thể khó theo dõi hơn code tuần tự như thế nào?
Bạn chọn cách đặt checkpoint có mô tả để khoanh vùng lỗi mà không tăng overhead quá mức như thế nào?
Bạn sẽ ghi log tín hiệu Reactor để điều tra luồng demand và cancellation như thế nào?
Bạn phân biệt log dữ liệu nghiệp vụ với log tín hiệu điều khiển của một publisher ra sao?
Bạn xây dựng metric đo số subscriber, thời gian xử lý và lỗi theo từng pipeline như thế nào?
Bạn thiết kế phương án truyền trace context qua các thao tác bất đồng bộ như thế nào?
Bạn phát hiện và xử lý các tác vụ bị giữ lại do subscription không được dispose như thế nào?
Bạn sẽ nhận diện một pipeline bị treo do Flux.never hoặc nguồn không phát terminal signal ra sao?
Bạn phân tích nguyên nhân Mono.zip không phát kết quả khi một nguồn con hoàn tất rỗng như thế nào?
Bạn dùng StepVerifier để kiểm chứng chuỗi onNext, onComplete và onError như thế nào?
Bạn sẽ viết kiểm thử một Flux có nhiều phần tử mà không phụ thuộc thời gian thực như thế nào?
Bạn sử dụng StepVerifier.withVirtualTime để kiểm thử delay và retry backoff ra sao?
Bạn giải thích tại sao việc tạo publisher bên trong supplier của withVirtualTime quan trọng như thế nào?
Bạn dùng TestPublisher để giả lập nguồn dữ liệu và điều khiển tín hiệu bất thường ra sao?
Bạn lựa chọn PublisherProbe khi cần xác minh nhánh fallback có được subscribe như thế nào?
Bạn sẽ kiểm thử demand thủ công của Subscriber để xác nhận backpressure được tôn trọng ra sao?
Bạn kiểm thử cancellation khi một Flux đang có nhiều inner publishers hoạt động như thế nào?
Bạn xây dựng bài kiểm thử xác nhận tài nguyên được cleanup trên cả complete, error và cancel ra sao?
Bạn viết kiểm thử trường hợp fallback trả về Mono.empty và ảnh hưởng đến zip hoặc flatMap như thế nào?
Bạn sẽ kiểm tra retry chỉ chạy lại với những loại lỗi được cho phép ra sao?
Bạn mô phỏng luồng dữ liệu vượt tốc độ tiêu thụ để kiểm thử overflow của buffer hoặc sink như thế nào?
Bạn dùng verifyThenAssertThat để kiểm tra những đặc điểm thực thi sau khi StepVerifier hoàn tất như thế nào?
Bạn thiết kế kiểm thử concurrency để phát hiện race condition khi nhiều thread phát tín hiệu vào sink ra sao?
Bạn sẽ kiểm thử thời điểm subscribe của một cold publisher để phát hiện tác dụng phụ ngoài ý muốn như thế nào?
Bạn kiểm tra sự khác biệt hành vi giữa hai subscriber vào hot publisher và cold publisher ra sao?
Bạn thiết kế kiểm thử timeout và cancellation không để lại tác vụ hoặc scheduler tồn đọng như thế nào?
Bạn xác định kịch bản stress test phù hợp cho pipeline Reactor có nhiều request đồng thời như thế nào?
Bạn đo throughput, latency p95 và mức dùng heap của pipeline Reactor trong một tình huống thực tế ra sao?
Bạn sẽ phân biệt điểm nghẽn CPU-bound với blocking I/O trong một pipeline reactive như thế nào?
Bạn phân tích hiệu ứng khi flatMap concurrency quá cao làm quá tải dịch vụ phụ thuộc ra sao?
Bạn chọn giới hạn concurrency, prefetch và timeout theo năng lực downstream như thế nào?
Bạn đánh giá khi nào một pipeline reactive trở nên khó duy trì hơn cách xử lý tuần tự như thế nào?
Bạn sẽ tổ chức các hàm biến đổi nhỏ để một pipeline Reactor dễ đọc và dễ kiểm thử ra sao?
Bạn thiết kế hợp đồng phương thức trả Mono hoặc Flux để tránh caller phải đoán lúc thực thi như thế nào?
Bạn cân nhắc cách phối hợp Reactor với mã Java legacy blocking mà vẫn giữ ranh giới an toàn ra sao?
Bạn sẽ phân biệt xử lý song song với xử lý không blocking khi trình bày kiến trúc Reactor như thế nào?
Nếu một API reactive bị tăng latency sau khi thêm lời gọi JDBC, bạn sẽ tìm nguyên nhân và di chuyển tác vụ ra sao?
Nếu một Flux phát hàng nghìn sự kiện mỗi giây nhưng client đọc chậm, bạn sẽ chọn chiến lược backpressure như thế nào?
Nếu kết quả tra cứu phải giữ đúng thứ tự đầu vào dù gọi dịch vụ ngoài song song, bạn sẽ chọn toán tử nào và vì sao?
Nếu một Mono trong zip có thể rỗng, bạn sẽ thiết kế fallback hoặc cấu trúc ghép dữ liệu ra sao?
Nếu một pipeline retry tạo hai giao dịch thanh toán, bạn sẽ thay đổi thiết kế idempotency và vị trí retry như thế nào?
Nếu một hot Flux cần hỗ trợ subscriber kết nối muộn, bạn sẽ đánh đổi giới hạn replay, bộ nhớ và tính cập nhật ra sao?
Nếu một sink bị lỗi FAIL_NON_SERIALIZED khi nhiều thread phát dữ liệu, bạn sẽ khắc phục như thế nào?
Nếu một ứng dụng rò rỉ tài nguyên sau khi client hủy request, bạn sẽ kiểm tra cancellation và cleanup ở những vị trí nào?
Nếu trace ID biến mất sau khi dùng publishOn, bạn sẽ kiểm tra cách lưu và đọc Reactor Context như thế nào?
Nếu phải triển khai và kiểm thử một pipeline Reactor Core chịu tải cao, bạn sẽ mô tả các bước thiết kế, giám sát và kiểm thử nào?

Bạn giải thích mô hình lập trình reactive giải quyết hạn chế nào của xử lý đồng bộ khi ứng dụng có nhiều I/O chờ đợi?
Bạn phân biệt reactive programming với lập trình bất đồng bộ dùng CompletableFuture về cách biểu diễn luồng dữ liệu như thế nào?
Bạn xác định những workload nào được hưởng lợi từ non-blocking I/O trong Spring theo tiêu chí nào?
Bạn đánh giá lý do reactive không tự làm cho phép tính CPU-bound chạy nhanh hơn như thế nào?
Bạn phân biệt concurrency với parallelism trong một ứng dụng Spring dùng Project Reactor ra sao?
Bạn giải thích vai trò của Publisher, Subscriber, Subscription và Processor trong Reactive Streams specification như thế nào?
Bạn mô tả các tín hiệu onSubscribe, onNext, onError và onComplete trong vòng đời một Subscription ra sao?
Bạn giải thích cơ chế request(n) của Subscriber biểu diễn nhu cầu nhận dữ liệu từ Publisher như thế nào?
Bạn phân biệt giới hạn số tín hiệu onNext của Mono và Flux theo ngữ nghĩa nào?
Bạn lựa chọn Mono<Void> thay cho Mono chứa kết quả khi thiết kế API không có response body dựa trên tiêu chí nào?
Bạn xác định sự khác nhau giữa Flux.empty, Mono.empty và một Publisher phát ra giá trị null ra sao?
Bạn giải thích vì sao null không được phép phát trực tiếp như tín hiệu onNext trong Reactive Streams?
Bạn phân biệt tín hiệu hoàn thành bình thường với tín hiệu lỗi kết thúc stream như thế nào?
Bạn mô tả một pipeline Reactor được lắp ghép trước khi có subscription thực sự ra sao?
Bạn giải thích vì sao gọi một method trả Mono nhưng không có subscriber có thể khiến thao tác I/O chưa chạy?
Bạn giải thích vai trò của WebFlux trong việc subscribe vào Publisher được trả về từ controller như thế nào?
Bạn đánh giá rủi ro gọi subscribe thủ công bên trong service method đã trả một Mono ra sao?
Bạn phân biệt một Publisher chỉ mô tả công việc với kết quả đã materialize của công việc đó như thế nào?
Bạn thiết kế method signature trả Mono hoặc Flux để caller tiếp tục compose và kiểm soát lỗi ra sao?
Bạn lựa chọn reactive API end-to-end hay imperative API theo dependency bên dưới và yêu cầu vận hành nào?
Bạn giải thích vì sao non-blocking không đồng nghĩa mọi đoạn code trong reactive pipeline đều tự động an toàn?
Bạn mô tả tác động của backpressure đối với tốc độ phát và nhận dữ liệu giữa các thành phần trong pipeline ra sao?
Bạn phân biệt cold Publisher với hot Publisher về thời điểm tạo dữ liệu và tác động của nhiều subscribers như thế nào?
Bạn đánh giá khả năng retry một cold stream có side effect khác với resubscribe một hot stream ra sao?
Bạn xác định giới hạn của mô hình reactive khi thư viện database hoặc HTTP client chỉ cung cấp API blocking như thế nào?
Bạn thiết kế boundary giữa domain service và transport layer để không làm lộ chi tiết Subscription cho nghiệp vụ ra sao?
Bạn phân biệt Reactor với Spring WebFlux về vai trò thư viện reactive và framework HTTP như thế nào?
Bạn xác định thời điểm nào cần Reactive Streams thay vì một kết quả đồng bộ đơn giản để tránh tăng độ phức tạp không cần thiết?
Bạn giải thích Mono.just khác Mono.defer về thời điểm lấy giá trị và thực thi logic ra sao?
Bạn chọn Mono.fromCallable để bọc một phép tính có thể ném exception theo tình huống nào?
Bạn phân biệt Mono.fromSupplier, Mono.fromRunnable và Mono.fromFuture theo nguồn tín hiệu như thế nào?
Bạn xử lý trường hợp Callable trả null khi tạo Mono.fromCallable bằng ngữ nghĩa nào?
Bạn thiết kế Flux.fromIterable cho dữ liệu có sẵn mà không giả định iterable được tạo lazily như thế nào?
Bạn phân biệt Flux.range với Flux.generate khi cần tạo dữ liệu có trạng thái và kiểm soát demand ra sao?
Bạn lựa chọn Flux.create để bọc callback API phát nhiều tín hiệu bất đồng bộ dựa trên yêu cầu nào?
Bạn phân biệt Flux.push với Flux.create theo mô hình nguồn phát một hay nhiều thread như thế nào?
Bạn kiểm soát việc phát onNext sau onComplete trong adapter callback sang Flux bằng cách nào?
Bạn lựa chọn Sinks.One, Sinks.Many và Sinks.Empty dựa trên số tín hiệu và số subscribers theo yêu cầu nào?
Bạn xử lý kết quả tryEmitNext khi Sink không nhận tín hiệu do backpressure hoặc đã kết thúc như thế nào?
Bạn phân biệt multicast, replay và unicast sink về lưu lịch sử và khả năng nhận của subscribers ra sao?
Bạn đánh giá rủi ro giữ dữ liệu vô hạn khi dùng replay sink cho stream có tuổi thọ dài như thế nào?
Bạn thiết kế adapter từ event listener sang Flux có cơ chế hủy đăng ký khi subscriber cancel như thế nào?
Bạn phân biệt Mono.never với Mono.empty về tín hiệu completion và hậu quả đối với HTTP response ra sao?
Bạn tạo Flux từ timer hoặc interval và xác định cách xử lý subscriber chậm như thế nào?
Bạn giải thích vì sao Flux.interval có thể phát lỗi liên quan demand khi downstream không theo kịp ra sao?
Bạn lựa chọn Mono.deferContextual để truy cập Reactor Context lúc subscription thay vì lúc assembly dựa trên yêu cầu nào?
Bạn thiết kế một Publisher sao cho mỗi subscriber có transaction hoặc request state riêng ra sao?
Bạn phân biệt side effect chạy khi tạo Publisher với side effect chạy khi subscription xuất hiện như thế nào?
Bạn kiểm tra vì sao một cold Publisher bị subscribe hai lần có thể gửi hai HTTP requests tới downstream ra sao?
Bạn lựa chọn cache hoặc share stream khi cần tránh khởi tạo lại một nguồn dữ liệu theo các yêu cầu nào?
Bạn phân biệt Mono.cache với lưu kết quả trong cache phân tán về phạm vi và thời hạn hiệu lực như thế nào?
Bạn đánh giá ảnh hưởng của Flux.share tới người đăng ký đến muộn khi dữ liệu nguồn đang phát ra sao?
Bạn phân biệt publish, refCount và autoConnect khi chuyển cold stream thành nguồn chia sẻ như thế nào?
Bạn lựa chọn cơ chế multicast khi nhiều subscribers cần xem cùng một chuỗi events theo tiêu chí nào?
Bạn xác định cách kiểm thử hot Publisher khi người đăng ký thứ hai chỉ nhận dữ liệu từ thời điểm tham gia như thế nào?
Bạn giải thích toán tử map của Reactor biến đổi từng phần tử mà không tự tạo một subscription mới cho mỗi giá trị như thế nào?
Bạn phân biệt map và flatMap khi hàm ánh xạ trả về một Mono từ thao tác I/O như thế nào?
Bạn lựa chọn flatMap, concatMap hoặc flatMapSequential dựa trên mức đồng thời và thứ tự kết quả như thế nào?
Vì sao flatMap có thể phát kết quả theo thứ tự khác đầu vào khi các inner Publishers hoàn tất không đồng thời?
Bạn thiết kế flatMap với tham số concurrency để bảo vệ downstream có giới hạn kết nối ra sao?
Bạn đánh giá ảnh hưởng của prefetch đến số phần tử được yêu cầu và bộ nhớ trong flatMap ra sao?
Bạn phân biệt switchMap với concatMap khi các truy vấn tìm kiếm mới phải hủy yêu cầu cũ như thế nào?
Bạn sử dụng filter và filterWhen cho điều kiện đồng bộ hoặc bất đồng bộ theo tình huống nào?
Bạn thiết kế pipeline phân trang dùng expand hoặc repeat mà không tải toàn bộ các trang vào bộ nhớ như thế nào?
Bạn phân biệt defaultIfEmpty và switchIfEmpty khi xử lý một Mono không có phần tử ra sao?
Vì sao defer giúp tránh khởi tạo sớm fallback Publisher trong switchIfEmpty khi nguồn chính có dữ liệu?
Bạn dùng zip để kết hợp kết quả của hai Mono và xác định hành vi khi một nguồn empty như thế nào?
Bạn phân biệt zip với combineLatest đối với các nguồn phát nhiều giá trị có tốc độ khác nhau ra sao?
Bạn thiết kế Mono.when khi chỉ cần biết nhiều tác vụ đã hoàn thành nhưng không cần giá trị trả về như thế nào?
Bạn đánh giá khi nào lỗi ở một nguồn trong zip có thể làm các nguồn còn lại bị cancel ra sao?
Bạn phân biệt merge với concat trong cách kết hợp nhiều Flux và giữ thứ tự phát ra như thế nào?
Bạn lựa chọn mergeSequential để giữ thứ tự nguồn trong khi vẫn subscribe sớm theo nhu cầu nào?
Bạn thiết kế luồng xử lý batch bằng buffer, window hoặc groupBy dựa trên cách downstream tiêu thụ như thế nào?
Bạn phân biệt buffer trả collection với window trả Publisher con về quản lý bộ nhớ và subscription ra sao?
Bạn đánh giá nguy cơ groupBy có nhiều groups không được consume làm pipeline bị treo như thế nào?
Bạn lựa chọn collectList hoặc reduce theo kích thước nguồn và mục tiêu tính toán nào?
Bạn xác định vì sao collectList trên Flux vô hạn có thể gây cạn bộ nhớ ra sao?
Bạn thiết kế distinct với bộ nhớ có giới hạn khi nguồn stream có cardinality rất cao như thế nào?
Bạn phân biệt take, takeUntil và takeWhile trong điều kiện dừng sớm một stream ra sao?
Bạn sử dụng skip và take cho dữ liệu có thứ tự và đánh giá giới hạn khi phân trang dữ liệu lớn như thế nào?
Bạn phân biệt sample, throttleFirst và debounce theo ngữ nghĩa lọc sự kiện người dùng ra sao?
Bạn lựa chọn debounce cho trường nhập tìm kiếm mà vẫn đảm bảo hủy request cũ bằng cơ chế nào?
Bạn đánh giá sự khác nhau giữa delayElements và delaySubscription về thời gian và demand ra sao?
Bạn thiết kế xử lý các tín hiệu cuối cùng bằng doOnComplete, doOnError và doFinally như thế nào?
Bạn phân biệt doOnNext với map khi chỉ muốn ghi nhận sự kiện mà không sửa dữ liệu ra sao?
Bạn đánh giá nguy cơ đặt side effects không idempotent trong doOnNext rồi retry cả pipeline ra sao?
Bạn sử dụng transform và transformDeferred để tái sử dụng nhóm operators theo ngữ nghĩa nào?
Bạn kiểm tra operator fusion làm thay đổi tối ưu thực thi nhưng không làm đổi contract kết quả ra sao?
Vì sao việc nối nhiều operators trong Reactor không đồng nghĩa mỗi operator chạy trên thread riêng?
Bạn phân biệt subscribeOn và publishOn về vị trí tác động đến lịch thực thi như thế nào?
Bạn xác định khi nào subscribeOn ảnh hưởng quá trình subscription và upstream source ra sao?
Bạn thiết kế vị trí publishOn để chuyển những công đoạn CPU-bound sang scheduler phù hợp như thế nào?
Bạn phân biệt Schedulers.parallel với Schedulers.boundedElastic theo loại công việc được phép chạy như thế nào?
Bạn đánh giá rủi ro đưa JDBC blocking call lên Schedulers.parallel làm cạn tài nguyên worker ra sao?
Bạn sử dụng Mono.fromCallable kết hợp subscribeOn(boundedElastic) để cách ly một API blocking như thế nào?
Bạn xác định giới hạn của boundedElastic về số threads và hàng đợi theo phiên bản Reactor đang dùng ra sao?
Bạn phân biệt Schedulers.single và một Scheduler tự tạo dành cho workload tuần tự theo yêu cầu nào?
Bạn thiết kế một Scheduler riêng cho thao tác blocking nặng để không ảnh hưởng các tác vụ khác như thế nào?
Bạn đánh giá vì sao subscribeOn đặt nhiều lần không đồng nghĩa mỗi operator chạy trên scheduler khác nhau ra sao?
Bạn kiểm tra tên thread thực thi từng công đoạn bằng các hook chẩn đoán nào?
Bạn phân tích thread thực thi của WebFlux trên event loop và các điều kiện khiến công việc được chuyển sang worker pool ra sao?
Bạn phân biệt Reactor Netty event loop với thread pool của servlet container ở hành vi xử lý I/O ra sao?
Bạn đánh giá tác động của CPU-bound loop dài chạy trong event loop tới nhiều connections đồng thời ra sao?
Bạn thiết kế giới hạn concurrency khi dùng WebClient gọi nhiều downstream endpoints song song như thế nào?
Bạn xác định cách bảo đảm thread confinement khi một mutable accumulator được nhiều flatMap branches cập nhật ra sao?
Bạn phân biệt thread-local context với Reactor Context khi pipeline chuyển scheduler như thế nào?
Bạn xử lý MDC logging khi request tiếp tục trên thread khác mà không được phép dùng cùng ThreadLocal cố định ra sao?
Bạn so sánh khả năng xử lý blocking I/O của virtual threads với reactive non-blocking theo mức dùng tài nguyên và cách lập trình ra sao?
Bạn thiết kế benchmark có cùng tải I/O để so sánh reactive và thread-per-request mà không kết luận chỉ từ số thread ra sao?
Bạn mô tả cách Publisher nhận demand từ Subscriber theo cơ chế backpressure của Reactive Streams như thế nào?
Bạn phân biệt downstream demand với upstream prefetch và số lượng dữ liệu đang buffer ra sao?
Bạn giải thích vì sao subscriber chỉ gọi request(1) nhưng upstream vẫn có thể được yêu cầu trước nhiều phần tử ra sao?
Bạn đánh giá giới hạn backpressure khi một Publisher adapter nhận dữ liệu từ callback source không điều tiết được tốc độ phát như thế nào?
Bạn thiết kế adapter khi nguồn phát nhanh hơn người nhận và không thể điều khiển tốc độ phát ra sao?
Bạn so sánh onBackpressureBuffer, onBackpressureDrop, onBackpressureLatest và onBackpressureError theo chính sách mất dữ liệu nào?
Bạn xác định cách đặt giới hạn buffer và xử lý overflow để tránh hết bộ nhớ như thế nào?
Bạn lựa chọn cơ chế drop sự kiện nào phù hợp với giá trị telemetry nhưng không phù hợp với thanh toán như thế nào?
Bạn thiết kế thông số limitRate để điều chỉnh request chunks cho upstream theo yêu cầu nào?
Bạn phân biệt backpressure với rate limiting ở API gateway về phạm vi bảo vệ ra sao?
Bạn đánh giá tác động của concatMap khi downstream chậm khiến hàng đợi upstream tăng như thế nào?
Bạn xử lý slow subscriber trong hot multicast stream theo chiến lược của Sink đang dùng như thế nào?
Bạn xác định khi nào operator bufferTimeout giúp cân bằng batch size với độ trễ xử lý ra sao?
Bạn thiết kế stream đến database có giới hạn số lệnh ghi đồng thời và hàng đợi đang chờ như thế nào?
Bạn phân biệt TCP flow control với Reactive Streams demand trong đường truyền HTTP streaming ra sao?
Bạn kiểm tra server WebFlux có truyền tín hiệu cancel hoặc demand ngược tới publisher khi client đọc chậm như thế nào?
Bạn đánh giá tác động của JSON serialization trên event loop tới throughput dù network I/O đã non-blocking như thế nào?
Bạn thiết kế giám sát số phần tử được request, dropped và buffered mà không làm logging gây chậm pipeline ra sao?
Bạn xác định những giới hạn của publisher không hỗ trợ backpressure khi kết hợp với downstream Reactive Streams như thế nào?
Bạn dùng StepVerifier.create với initialRequest và thenRequest để kiểm chứng Publisher tuân thủ demand như thế nào?
Bạn xác minh một source xử lý cancel đúng mà không tiếp tục phát tín hiệu vô hạn ra sao?
Bạn thiết kế cách chọn sampling, aggregation hoặc buffering cho stream sự kiện có traffic đột biến như thế nào?
Bạn phân biệt tín hiệu onError terminal với giá trị lỗi được biểu diễn như data trong pipeline ra sao?
Bạn sử dụng onErrorResume để chọn fallback Publisher theo loại exception như thế nào?
Bạn phân biệt onErrorReturn với onErrorResume khi fallback cần logic bất đồng bộ ra sao?
Bạn đánh giá nguy cơ onErrorComplete che giấu lỗi downstream và khiến API trả dữ liệu không đầy đủ ra sao?
Bạn thiết kế onErrorMap để chuyển lỗi kỹ thuật thành domain exception mà giữ nguyên nguyên nhân như thế nào?
Bạn xác định cách dùng doOnError để ghi log mà vẫn giữ nguyên đường lan truyền lỗi ra sao?
Bạn phân biệt retry và retryWhen về điều kiện, backoff và khả năng giới hạn số lần thử như thế nào?
Bạn lựa chọn Retry.backoff kết hợp jitter để ngăn retry storm trong giờ cao điểm như thế nào?
Bạn xác định những lỗi nào không nên retry vì phản hồi 4xx hoặc validation failure là lỗi cố định ra sao?
Bạn đánh giá nguy cơ retry một POST không idempotent làm lặp side effect của downstream như thế nào?
Bạn thiết kế retry dựa trên idempotency key và transaction boundary theo yêu cầu nào?
Bạn phân biệt repeat với retry khi một Publisher complete bình thường hoặc kết thúc bằng lỗi ra sao?
Bạn xử lý timeout của một Mono chờ HTTP response và phân biệt timeout với kết quả Mono.empty như thế nào?
Bạn lựa chọn đặt timeout ở WebClient, reactive pipeline và ingress theo một ngân sách deadline thống nhất ra sao?
Bạn xác định cancellation khi timeout có đảm bảo lệnh đã gửi tới hệ thống ngoài chưa gây side effect hay không như thế nào?
Bạn sử dụng onErrorResume sau timeout để trả fallback mà vẫn ghi nhận nguyên nhân lỗi ra sao?
Bạn thiết kế circuit breaker cho WebClient không làm mất ngữ nghĩa cancellation và retry budget như thế nào?
Bạn phân biệt bulkhead giới hạn concurrent requests với backpressure nội bộ của stream như thế nào?
Bạn đánh giá khi nào fallback sang cache stale có thể chấp nhận và khi nào phải fail-closed vì dữ liệu nhạy cảm ra sao?
Bạn thiết kế pipeline không chuyển mọi lỗi thành HTTP 200 với body rỗng như thế nào?
Bạn phân biệt lỗi xuất hiện trước khi HTTP response commit với lỗi sau khi streaming response đã bắt đầu ra sao?
Bạn đánh giá cách client phát hiện lỗi giữa chừng trong Server-Sent Events stream như thế nào?
Bạn xác định cách propagate lỗi bên trong flatMap mà không vô tình bỏ mất stack trace hữu ích ra sao?
Bạn sử dụng checkpoint để thêm ngữ cảnh chẩn đoán cho một chuỗi operators như thế nào?
Bạn đánh giá overhead của Hooks.onOperatorDebug và cách chỉ bật nó trong môi trường phù hợp như thế nào?
Bạn phân biệt assembly traceback với runtime exception stack trace khi phân tích Reactor lỗi ra sao?
Bạn thiết kế cleanup tài nguyên trong doFinally để xử lý complete, error và cancel như thế nào?
Bạn phân biệt doOnCancel và doFinally về các tín hiệu kết thúc mà chúng quan sát ra sao?
Bạn dùng using hoặc usingWhen để đóng tài nguyên khi reactive work hoàn tất hoặc bị cancel như thế nào?
Bạn xác định cách xử lý lỗi xảy ra trong asynchronous cleanup của usingWhen ra sao?
Bạn thiết kế resource acquisition lazily để không mở kết nối trước khi có subscriber như thế nào?
Bạn phân biệt onErrorContinue với onErrorResume về khả năng tạo hành vi khó dự đoán ở upstream như thế nào?
Bạn đánh giá rủi ro dùng onErrorContinue ở pipeline chứa nhiều operators hoặc business side effects ra sao?
Bạn giải thích Reactor Context là gì và khác biến local hoặc ThreadLocal ở phạm vi nào?
Bạn phân biệt Context và ContextView về khả năng đọc, ghi và tính bất biến như thế nào?
Bạn sử dụng contextWrite để bổ sung correlation ID cho subscription như thế nào?
Vì sao vị trí contextWrite trong chuỗi operators quyết định những thành phần upstream nào đọc được dữ liệu Context?
Bạn dùng deferContextual để đọc thông tin gắn với subscriber khi thực thi một reactive operation ra sao?
Bạn thiết kế truyền tenant ID qua Reactor Context mà không tin dữ liệu tenant do client tự nhập như thế nào?
Bạn phân biệt propagation của Context theo subscription với propagation tự động của HTTP headers như thế nào?
Bạn xử lý Reactor Context khi dùng flatMap tạo các inner Publishers có nhiều subscription như thế nào?
Bạn kiểm tra Context có được giữ khi pipeline chuyển từ publishOn sang scheduler khác như thế nào?
Bạn lựa chọn đặt trace ID trong Reactor Context thay vì field của singleton service dựa trên yêu cầu cách ly nào?
Bạn tích hợp MDC với Reactor Context để logs có correlation ID dù thread thực thi thay đổi ra sao?
Bạn đánh giá giới hạn của cơ chế automatic context propagation tùy phiên bản Reactor và Spring đang chạy như thế nào?
Bạn phân biệt Reactor Context với ServerWebExchange attributes về vòng đời và phạm vi truy cập ra sao?
Bạn thiết kế cách truyền security principal từ reactive authentication context tới downstream service như thế nào?
Bạn xác định khi nào contextWrite đặt trong một inner Mono không làm thay đổi Context của sibling stream ra sao?
Bạn ngăn một library dùng cùng Context key với thành phần khác bằng quy ước định danh nào?
Bạn đánh giá nguy cơ giữ đối tượng lớn hoặc dữ liệu nhạy cảm trong Reactor Context quá lâu như thế nào?
Bạn kiểm thử tenant ID không bị lẫn giữa hai concurrent subscribers trên cùng một pipeline ra sao?
Bạn sử dụng StepVerifier.expectAccessibleContext để kiểm chứng dữ liệu context trong test như thế nào?
Bạn xác định dấu hiệu một thao tác imperative đọc ThreadLocal thất bại sau scheduler switch như thế nào?
Bạn thiết kế adapter đưa request-scoped metadata vào Context theo boundary của WebFlux như thế nào?
Bạn phân biệt context propagation của Reactor với transaction context gắn ThreadLocal trong JDBC như thế nào?
Bạn đánh giá ảnh hưởng của context loss khi kết hợp thư viện reactive của bên thứ ba theo nguyên nhân nào?
Bạn giải thích WebFlux cung cấp mô hình xử lý HTTP không chặn dựa trên Publisher như thế nào?
Bạn phân biệt Spring WebFlux với Spring MVC ở kiểu return value và mô hình request processing ra sao?
Bạn lựa chọn @RestController reactive hoặc functional routing theo đặc điểm API nào?
Bạn giải thích vai trò của HandlerFunction, RouterFunction và ServerResponse trong functional endpoints như thế nào?
Bạn phân biệt ServerRequest trong WebFlux functional API với ServerWebExchange ở tầng web infrastructure ra sao?
Bạn thiết kế route xử lý GET trả Mono<ResponseEntity<DTO>> theo yêu cầu kết quả nào?
Bạn lựa chọn Flux<DTO> cho streaming response thay vì Mono<List<DTO>> theo kích thước dữ liệu nào?
Bạn phân biệt streaming NDJSON và một JSON array về thời điểm client nhận dữ liệu ra sao?
Bạn xây dựng Server-Sent Events endpoint trong WebFlux và quản lý vòng đời kết nối như thế nào?
Bạn đánh giá tác động của proxy buffering hoặc gateway timeout tới một SSE stream dài ra sao?
Bạn xác định lúc nào nên trả HTTP 404 khi Mono của repository hoàn tất rỗng ra sao?
Bạn sử dụng switchIfEmpty để tạo HTTP response not found mà không chặn thread như thế nào?
Bạn thiết kế validation của request body bất đồng bộ trong WebFlux theo các ràng buộc nào?
Bạn phân biệt lỗi JSON decoding với Bean Validation failure ở HTTP status và error body như thế nào?
Bạn xử lý controller trả Mono lỗi trước response commit bằng global exception handler theo cách nào?
Bạn xác định hành vi khi controller trả Mono<Void> nhưng không gửi body cho một thao tác bất đồng bộ ra sao?
Bạn đánh giá rủi ro tự gọi block() trong WebFlux controller để lấy một giá trị từ Mono như thế nào?
Bạn lựa chọn WebFlux trên Reactor Netty hay servlet runtime hỗ trợ non-blocking I/O theo điều kiện nào?
Bạn phân biệt non-blocking request body consumption với việc buffer toàn bộ body trong bộ nhớ như thế nào?
Bạn thiết kế giới hạn kích thước HTTP request body cho payload lớn để tránh DataBufferLimitException ra sao?
Bạn xác định khi nào cần chuyển sang xử lý streaming request body thay vì decode toàn bộ JSON thành collection ra sao?
Bạn xử lý upload file reactive bằng FilePart và không giữ toàn bộ file trong heap như thế nào?
Bạn quản lý DataBuffer khi xử lý byte stream thủ công để tránh memory leak như thế nào?
Bạn phân biệt các APIs DataBufferUtils join, write và release trong các bước xử lý payload như thế nào?
Bạn đánh giá rủi ro giữ reference tới pooled Netty ByteBuf sau khi request đã kết thúc ra sao?
Bạn thiết kế response có cancel khi người dùng ngắt kết nối và giải phóng nguồn dữ liệu phía sau ra sao?
Bạn xác định cách truyền backpressure qua WebFlux response tới publisher đọc database hoặc message source ra sao?
Bạn phân biệt streaming endpoint với long-polling hoặc WebSocket ở cách giao tiếp và lifecycle ra sao?
Bạn lựa chọn WebSocket cho giao tiếp hai chiều khi SSE một chiều không đáp ứng yêu cầu nào?
Bạn thiết kế WebFilter đưa correlation ID vào Reactor Context mà không ghi state vào field dùng chung như thế nào?
Bạn phân biệt HandlerFilterFunction và WebFilter về phạm vi áp dụng ở WebFlux như thế nào?
Bạn xác định thứ tự các WebFilter ảnh hưởng authentication, tracing và error handling ra sao?
Bạn quản lý HTTP response commit khi upstream streaming Flux phát lỗi sau khi đã gửi nhiều chunks như thế nào?
Bạn giải thích WebClient thực hiện HTTP I/O không chặn và trả Mono hoặc Flux như thế nào?
Bạn phân biệt WebClient.retrieve với exchangeToMono trong việc xử lý response status và body ra sao?
Bạn thiết kế onStatus để ánh xạ HTTP 404, 429 và 5xx từ downstream thành kết quả hoặc lỗi phù hợp như thế nào?
Bạn xác định khi nào cần exchangeToFlux để xử lý response streaming với metadata riêng ra sao?
Bạn kiểm tra WebClient response body có được consume hoặc release trong custom exchange handling như thế nào?
Bạn sử dụng WebClient.Builder để tái sử dụng cấu hình base URL, headers và filters theo service như thế nào?
Bạn đánh giá rủi ro tạo Reactor Netty HttpClient hoặc WebClient mới cho mỗi request ra sao?
Bạn thiết kế timeout gồm connect timeout, response timeout và pipeline deadline trong lời gọi WebClient như thế nào?
Bạn phân biệt connection pool queue timeout với timeout do downstream xử lý chậm như thế nào?
Bạn kiểm soát connection pool size và pending acquire khi một service gọi hàng trăm HTTP requests đồng thời ra sao?
Bạn lựa chọn giới hạn flatMap concurrency song song với kích thước WebClient connection pool như thế nào?
Bạn tổ chức WebClient filters cho logging và tracing mà không ghi access token hay request body nhạy cảm như thế nào?
Bạn truyền bearer token theo Reactive SecurityContext mà không dùng một global mutable header như thế nào?
Bạn xử lý API downstream trả 204 No Content khác với 200 có JSON object theo contract nào?
Bạn xác định cách truyền cancellation khi caller hủy request WebFlux đang chờ nhiều WebClient calls như thế nào?
Bạn so sánh dùng Mono.zip cho nhiều HTTP calls song song với concatMap cho các bước có phụ thuộc dữ liệu như thế nào?
Bạn đánh giá tác động của retryWhen đặt sau toàn bộ zip so với retry riêng từng downstream call ra sao?
Bạn thiết kế circuit breaker và rate limiter cho WebClient khi downstream liên tục trả 503 như thế nào?
Bạn xác định nguy cơ lỗi timeout sau khi downstream đã ghi dữ liệu khi retry POST không idempotent ra sao?
Bạn tổ chức fallback hoặc partial response khi một trong nhiều downstream services không khả dụng như thế nào?
Bạn kiểm thử WebClient decoder khi response lớn vượt maxInMemorySize theo cách nào?
Bạn lựa chọn bodyToFlux thay cho bodyToMono<List<DTO>> dựa trên response streaming và yêu cầu bộ nhớ nào?
Bạn đánh giá nguy cơ hủy đọc response giữa chừng khiến connection không được tái sử dụng như thế nào?
Bạn phân biệt WebClient reactive với RestClient blocking về hợp đồng method và mô hình thread ra sao?
Bạn lựa chọn MockWebServer hoặc HTTP stub server để kiểm thử WebClient status mapping, timeout và retry như thế nào?
Bạn xác định các điểm có thể xảy ra blocking khi ghép JPA, JDBC hoặc filesystem I/O vào reactive pipeline như thế nào?
Bạn đánh giá rủi ro đặt Thread.sleep trong map hoặc doOnNext của WebFlux chạy trên event loop ra sao?
Bạn dùng BlockHound ở môi trường test để phát hiện blocking calls trên non-blocking threads như thế nào?
Bạn kiểm tra kết quả BlockHound bị ảnh hưởng bởi cấu hình thread hoặc thư viện bên thứ ba theo điều kiện nào?
Bạn thiết kế adapter cho một thư viện legacy blocking với Mono.fromCallable và boundedElastic như thế nào?
Bạn phân biệt cách ly blocking call bằng boundedElastic với chuyển toàn bộ hệ thống thành non-blocking I/O thực sự ra sao?
Bạn giới hạn số blocking tasks đang chạy để boundedElastic không trở thành hàng đợi vô hạn như thế nào?
Vì sao JDBC transaction gắn với thread không tự tham gia cùng một reactive transaction qua R2DBC?
Bạn phân biệt TransactionalOperator trong reactive data access với @Transactional dựa trên thread-bound transaction ở JDBC như thế nào?
Bạn thiết kế service dùng R2DBC để thực hiện nhiều database operations trong một reactive transaction ra sao?
Bạn đánh giá rủi ro dùng multiple subscriptions bên trong một reactive transaction làm tách transactional scope như thế nào?
Bạn xác định khi nào kết hợp blocking JPA với WebFlux không đem lại lợi ích về tài nguyên như mong đợi ra sao?
Bạn xử lý password hashing hoặc JSON transformation CPU-bound mà không làm nghẽn event loop như thế nào?
Bạn kiểm soát số lần chuyển Scheduler để tránh context switching overhead không cần thiết ra sao?
Bạn thiết kế các điểm đo thread usage để chứng minh request pipeline không chặn Reactor Netty worker ra sao?
Bạn phân biệt tình huống cần API imperative riêng với việc bọc mọi thứ trong Mono một cách hình thức như thế nào?
Bạn đánh giá chi phí ngữ nghĩa và kiểm thử khi trộn blocking service và reactive HTTP adapter như thế nào?
Bạn phân tích những giới hạn của cancellation và timeout đối với blocking call đã chạy trên boundedElastic ra sao?
Bạn thiết kế cleanup cho resource blocking ngay cả khi reactive subscriber đã cancel như thế nào?
Bạn lựa chọn caching một Mono result hay dùng Spring Cache abstraction theo phiên bản Spring hiện tại dựa trên tiêu chí nào?
Bạn đánh giá rủi ro sử dụng ThreadLocal cho request data trong Reactor pipeline chạy trên nhiều threads ra sao?
Bạn nhận diện lỗi sử dụng thread-bound transaction synchronization trong reactive pipeline đổi Scheduler qua các dấu hiệu nào?
Bạn dùng StepVerifier để kiểm thử thứ tự onNext, onComplete và onError của một Mono hoặc Flux như thế nào?
Bạn phân biệt verifyComplete và verifyError khi kiểm thử hợp đồng của Publisher ra sao?
Bạn thiết kế StepVerifier với expectNextMatches để kiểm tra dữ liệu mà không phụ thuộc reference equality như thế nào?
Bạn sử dụng StepVerifier.withVirtualTime để kiểm thử retry backoff hoặc timeout mà không phải chờ thời gian thực như thế nào?
Bạn xác định khi nào pipeline phải được tạo lazily bên trong withVirtualTime để virtual scheduler có hiệu lực ra sao?
Bạn thiết kế test một Flux phát sự kiện theo khoảng thời gian với thenAwait và expectNoEvent như thế nào?
Bạn sử dụng TestPublisher để mô phỏng Publisher phát nhanh hoặc vi phạm protocol nhằm kiểm tra adapter như thế nào?
Bạn kiểm thử xử lý cancel với doFinally khi subscriber dừng nhận dữ liệu trước completion ra sao?
Bạn xác nhận một WebClient call không bị gửi trước khi service Publisher được subscribe bằng test nào?
Bạn thiết kế test cho flatMap có cạnh tranh để xác minh thứ tự kết quả không bị giả định sai như thế nào?
Bạn kiểm thử concatMap giữ thứ tự đầu vào trong lúc tác vụ bất đồng bộ hoàn thành khác thứ tự ra sao?
Bạn kiểm chứng giới hạn concurrency của flatMap bằng bộ đếm concurrent operations trong test như thế nào?
Bạn thiết kế test backpressure khi Subscriber chỉ request một phần số events được phát ra sao?
Bạn xác minh buffer overflow được xử lý theo đúng policy bằng test nào?
Bạn kiểm thử một hot Sinks.Many khi subscriber mới không được nhận dữ liệu đã phát trước đó như thế nào?
Bạn kiểm tra nguồn callback được dọn listener sau khi Flux subscription bị cancel như thế nào?
Bạn kiểm thử Context truyền tenant và correlation ID đúng khi pipeline dùng publishOn như thế nào?
Bạn xác minh ReactiveSecurityContextHolder không bị rò identity giữa hai concurrent requests bằng test nào?
Bạn dùng WebTestClient để kiểm thử WebFlux controller trả Mono, Flux và mã HTTP phù hợp như thế nào?
Bạn thiết kế integration test cho functional RouterFunction và HandlerFunction mà không khởi động server thật ra sao?
Bạn kiểm thử SSE endpoint có nhiều events rồi bị client cancel bằng WebTestClient như thế nào?
Bạn xác minh streaming response bắt đầu gửi dữ liệu trước khi toàn bộ upstream hoàn tất ra sao?
Bạn kiểm thử DataBuffer release sau upload hoặc cancel bằng leak detection phù hợp như thế nào?
Bạn mô phỏng downstream 429, timeout và lỗi kết nối để kiểm tra WebClient retry/backoff ra sao?
Bạn kiểm tra pipeline không retry vô hạn khi gặp lỗi validation hoặc 4xx bằng StepVerifier như thế nào?
Bạn thiết kế load test để đo p50/p95/p99 latency và throughput khi số HTTP connections đồng thời tăng ra sao?
Bạn đánh giá cách phát hiện tác vụ blocking trong event loop bằng BlockHound, thread dumps và latency metrics như thế nào?
Bạn xây dựng integration test cho reactive transaction rollback khi một Mono bên trong chuỗi ném lỗi ra sao?
Bạn kiểm tra behavior khi WebFlux client hủy stream giữa lúc database còn đang phát rows bằng cách nào?
Bạn xác định quality gates cho production reactive API gồm correctness, backpressure, cancellation, resource cleanup và SLO nào?
Bạn thiết kế Micrometer metrics cho số subscription, onError, cancellation và thời gian xử lý stream như thế nào?
Bạn phân biệt thời gian từ lúc tạo Publisher tới subscribe với thời gian xử lý subscription thực tế ra sao?
Bạn dùng những tín hiệu nào để phát hiện event loop bị chặn khi CPU chưa bão hòa?
Bạn đánh giá rủi ro metric tag chứa raw user ID, URL path variables hoặc tenant ID có cardinality cao ra sao?
Bạn thiết kế tracing trải qua WebFlux, WebClient và R2DBC mà không mất trace context giữa schedulers như thế nào?
Bạn kiểm tra trace span bị đứt khi Reactor Context không được truyền đúng bằng công cụ nào?
Bạn lựa chọn checkpoint hoặc operator debug chỉ bật khi điều tra lỗi để tránh overhead theo tiêu chí nào?
Bạn phân biệt error rate theo HTTP status với onError signals bên trong pipeline khi fallback biến lỗi thành response thành công ra sao?
Bạn thiết kế dashboard quan sát số requests đang chờ WebClient pool và mức sử dụng boundedElastic ra sao?
Bạn theo dõi pending requests, buffer size và dropped events để phát hiện backpressure không hiệu quả như thế nào?
Bạn đánh giá nguyên nhân p99 latency tăng khi flatMap concurrency không giới hạn và downstream pool bão hòa ra sao?
Bạn quyết định bổ sung rate limiting ở ingress cho reactive endpoint thay vì chỉ dựa vào backpressure theo tiêu chí nào?
Bạn thiết kế cache cho reactive API mà không chia sẻ nhầm response riêng tư giữa các principals ra sao?
Bạn kiểm tra output của WebFlux response có chứa thông tin nhạy cảm từ Reactor Context do log hoặc serializer không như thế nào?
Bạn đánh giá rủi ro WebClient filter log toàn bộ bearer token trong quá trình tracing ra sao?
Bạn áp dụng Spring Security WebFlux authentication và authorization trên chuỗi reactive theo nguyên tắc nào?
Bạn phân biệt ServerHttpSecurity và HttpSecurity trong cấu hình WebFlux so với Servlet stack như thế nào?
Bạn thiết kế authorization ở service và downstream để bổ sung cho kiểm tra quyền tại WebFlux controller như thế nào?
Bạn thiết kế propagation của deadline, correlation ID và principal sang WebClient mà không trust header tùy ý ra sao?
Bạn đánh giá bảo vệ reactive endpoints trước slow-client attacks bằng các giới hạn kết nối và timeout như thế nào?
Bạn xác định cách bảo vệ SSE/WebSocket dài hạn khi token của client hết hạn giữa session như thế nào?
Bạn lựa chọn trả stale data, fail fast hay queue request khi một reactive downstream quan trọng bị outage dựa trên rủi ro nào?
Bạn thiết kế runbook cho tình huống Reactor Netty event loop blocked, WebClient pool cạn và retry storm cùng lúc như thế nào?
Nếu controller trả Mono nhưng service đã gọi block(), bạn sẽ tìm nguyên nhân và chuyển thành pipeline non-blocking ra sao?
Nếu một Mono HTTP call bị thực thi hai lần, bạn sẽ kiểm tra số subscription và việc dùng cold Publisher như thế nào?
Nếu Flux phát không có dữ liệu khi controller quên trả Publisher, bạn sẽ kiểm tra subscription ownership ra sao?
Nếu một API trả 200 với body rỗng khi repository Mono.empty, bạn sẽ chuyển thành HTTP 404 đúng contract như thế nào?
Nếu flatMap trả kết quả khác thứ tự đầu vào khiến UI hiển thị sai, bạn sẽ chọn toán tử thay thế nào và kiểm thử ra sao?
Nếu một Mono trong zip hoàn tất rỗng khiến không có kết quả tổng hợp, bạn sẽ xử lý empty branch như thế nào?
Nếu cache một Mono chứa kết quả phụ thuộc tenant làm rò dữ liệu giữa requests, bạn sẽ điều chỉnh key và Publisher lifecycle ra sao?
Nếu Sinks.Many báo FAIL_OVERFLOW khi subscriber chậm, bạn sẽ thiết kế buffer, drop policy và metrics như thế nào?
Nếu Flux.interval gây lỗi khi downstream không request đủ nhanh, bạn sẽ kiểm tra backpressure policy và nhu cầu sự kiện ra sao?
Nếu memory tăng không ngừng trong stream collectList, bạn sẽ chuyển sang window hoặc streaming response như thế nào?
Nếu gọi Thread.sleep trong map làm tất cả requests chậm, bạn sẽ kiểm tra thread và chuyển việc phù hợp sang scheduler nào?
Nếu boundedElastic bị bão hòa vì nhiều JDBC calls blocking, bạn sẽ giới hạn concurrency và đánh giá R2DBC như thế nào?
Nếu publishOn chuyển thread nhưng log mất trace ID, bạn sẽ kiểm tra Context và MDC propagation ra sao?
Nếu một pipeline bị treo sau groupBy, bạn sẽ kiểm tra việc tiêu thụ groups và backpressure ra sao?
Nếu request WebFlux bị cancel nhưng nguồn callback vẫn phát events, bạn sẽ đặt cleanup ở đâu để hủy đăng ký nguồn phát?
Nếu retryWhen lặp POST tạo bản ghi trùng, bạn sẽ bảo vệ idempotency và giới hạn retry như thế nào?
Nếu onErrorResume trả fallback che khuất lỗi database kéo dài, bạn sẽ thiết kế metrics và fail policy ra sao?
Nếu lỗi từ Flux xảy ra sau khi HTTP response commit, bạn sẽ xử lý stream termination và thông báo client như thế nào?
Nếu SSE qua gateway bị buffering nên client nhận sự kiện trễ, bạn sẽ kiểm tra content type, proxy và flush behavior ra sao?
Nếu WebClient nhận lỗi 429 liên tục, bạn sẽ thiết lập retry budget, jitter và giới hạn số lời gọi đồng thời như thế nào?
Nếu WebClient timeout mà downstream đã hoàn tất giao dịch, bạn sẽ xác định kết quả và tránh retry không an toàn ra sao?
Nếu WebClient connection pool đang chờ dài nhưng event loop khỏe, bạn sẽ điều chỉnh pooling và concurrency như thế nào?
Nếu request upload DataBuffer làm memory leak, bạn sẽ rà sở hữu buffer và chỗ cần release ra sao?
Nếu WebFlux trả DataBufferLimitException cho JSON lớn, bạn sẽ xem lại giới hạn codec và mô hình streaming như thế nào?
Nếu R2DBC transaction mất hiệu lực do một phần xử lý subscribe riêng, bạn sẽ tái cấu trúc chain và test ra sao?
Nếu một StepVerifier timeout test chạy quá lâu, bạn sẽ kiểm tra VirtualTimeScheduler và cách tạo Publisher như thế nào?
Nếu Context chứa security principal sai giữa hai requests chạy đồng thời, bạn sẽ kiểm tra shared state và subscription boundary như thế nào?
Nếu pipeline xử lý lỗi tốt ở unit test nhưng production thất bại vì blocking thư viện thứ ba, bạn sẽ bổ sung loại kiểm thử nào?
Nếu hệ thống reactive tăng threads nhưng throughput không tăng, bạn sẽ đo contention, blocking và downstream saturation như thế nào?
Bạn xây dựng quy trình điều tra khi API WebFlux bị latency cao, nhiều cancellations và mất trace context trong giờ cao điểm như thế nào?

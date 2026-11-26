Bạn giải thích tư duy lập trình reactive khác với luồng xử lý đồng bộ gọi hàm rồi chờ kết quả như thế nào?
Bạn phân biệt luồng dữ liệu bất đồng bộ với việc đơn thuần tạo thêm nhiều thread để xử lý cùng một danh sách ra sao?
Bạn xác định những đặc điểm nào khiến một API thực sự có hợp đồng reactive thay vì chỉ trả về một callback như thế nào?
Bạn so sánh cách xử lý sự kiện dạng push với pull truyền thống và giải thích vấn đề xuất hiện khi tốc độ producer vượt consumer ra sao?
Bạn phân biệt tính bất đồng bộ, tính không chặn và tính song song khi đánh giá một pipeline reactive như thế nào?
Bạn giải thích cách reactive pipeline mô tả chuỗi biến đổi dữ liệu tách khỏi thời điểm thực thi như thế nào?
Bạn đánh giá khi nào reactive programming phù hợp với ứng dụng I/O nhiều request và khi nào mã tuần tự đơn giản dễ bảo trì hơn ra sao?
Bạn mô tả các tín hiệu dữ liệu, hoàn tất và lỗi trong một luồng reactive và vì sao cần phân biệt chúng như thế nào?
Bạn giải thích ý nghĩa của subscription đối với vòng đời của một pipeline được khai báo trước đó ra sao?
Bạn phân biệt phần cấu hình pipeline với phần tạo side effect lúc subscription khi đánh giá tính đúng của mã reactive như thế nào?
Bạn giải thích lý do một đoạn mã tạo `Flux` không nhất thiết thực hiện phép truy vấn trước khi có subscriber ra sao?
Bạn phân biệt lazy evaluation trong Reactor với việc mọi công việc đều được thực hiện trên một thread khác như thế nào?
Bạn xác định trạng thái mutable được đóng qua lambda có thể gây lỗi gì nếu một Publisher được subscribe nhiều lần ra sao?
Bạn đánh giá ảnh hưởng của non-blocking I/O lên mức sử dụng thread khi nhiều request chờ mạng cùng lúc như thế nào?
Bạn phân biệt event stream hữu hạn với stream có thể phát dữ liệu liên tục trong cả đời ứng dụng như thế nào?
Bạn thiết kế ranh giới giữa phần biến đổi thuần dữ liệu và phần tạo side effect trong một pipeline reactive ra sao?
Bạn giải thích lợi ích và chi phí của việc bảo toàn khả năng quan sát lỗi, hủy và tiến độ trong code reactive như thế nào?
Bạn so sánh mô hình reactive với `CompletableFuture` về nhiều giá trị, yêu cầu dữ liệu và vòng đời subscription ra sao?
Bạn trình bày bốn interface `Publisher`, `Subscriber`, `Subscription` và `Processor` của Reactive Streams phối hợp với nhau như thế nào?
Bạn giải thích trình tự `onSubscribe`, `onNext` và một tín hiệu kết thúc hợp lệ theo hợp đồng Reactive Streams như thế nào?
Bạn xác định vì sao Publisher phải cung cấp `Subscription` trước khi phát các phần tử tới Subscriber ra sao?
Bạn mô tả ý nghĩa của `Subscription.request(n)` và cách nó biểu diễn nhu cầu nhận thêm dữ liệu như thế nào?
Bạn giải thích vì sao Subscriber yêu cầu số phần tử không dương là vi phạm hợp đồng và Publisher cần xử lý theo giao thức ra sao?
Bạn phân biệt số phần tử được yêu cầu tích lũy với số phần tử đã phát và đánh giá rủi ro phát vượt demand như thế nào?
Bạn thiết kế Subscriber yêu cầu từng phần tử theo tiến độ xử lý thực tế mà vẫn tránh vòng điều khiển demand không hợp lệ ra sao?
Bạn giải thích ý nghĩa của `Subscription.cancel()` và những bảo đảm giới hạn về thời điểm Publisher ngừng phát tín hiệu như thế nào?
Bạn xác định vì sao không thể giả định cancel lập tức hủy hoàn toàn một thao tác I/O bên ngoài đã bắt đầu như thế nào?
Bạn phân biệt `onComplete` với `onError` theo việc một luồng đã kết thúc thành công hay thất bại như thế nào?
Bạn giải thích vì sao `onError` và `onComplete` là tín hiệu kết thúc loại trừ nhau và sau đó không còn `onNext` hợp lệ ra sao?
Bạn xử lý tình huống Subscriber phát sinh exception trong callback mà không phá vỡ vòng đời reactive hoặc che mất nguyên nhân lỗi như thế nào?
Bạn phân tích yêu cầu tín hiệu tới một Subscriber phải được tuần tự hóa ngay cả khi producer sử dụng nhiều thread ra sao?
Bạn giải thích vì sao Reactive Streams không cho truyền giá trị `null` trong `onNext` và cách biểu diễn sự vắng mặt phù hợp như thế nào?
Bạn xác định trách nhiệm của `Processor` vừa làm Subscriber của upstream vừa làm Publisher cho downstream như thế nào?
Bạn đánh giá cách một processor truyền demand ngược upstream khi phép biến đổi có thể tạo ra nhiều phần tử cho một đầu vào ra sao?
Bạn phân biệt compliance với Reactive Streams và việc một framework hỗ trợ nhiều toán tử tiện dụng như thế nào?
Bạn thiết kế một Subscriber test để phát hiện Publisher phát quá số lượng yêu cầu hoặc phát sai thứ tự tín hiệu ra sao?
Bạn giải thích cách backpressure truyền từ consumer về producer qua subscription khác với cơ chế producer tự đoán tốc độ consumer như thế nào?
Bạn phân biệt backpressure tại ranh giới dữ liệu reactive với giới hạn concurrency của các tác vụ I/O bên trong một toán tử ra sao?
Bạn đánh giá những điều kiện một nguồn push không kiểm soát được tốc độ sẽ cần chính sách buffer, drop hoặc báo lỗi ra sao?
Bạn mô tả vì sao Reactive Streams không bảo đảm dữ liệu trên hệ thống ngoài được phát lại nếu subscriber hủy subscription như thế nào?
Bạn phân biệt `Mono` và `Flux` theo số phần tử hợp lệ và cách biểu diễn một tác vụ bất đồng bộ như thế nào?
Bạn lựa chọn `Mono` cho truy vấn một bản ghi và `Flux` cho nhiều bản ghi theo hợp đồng API như thế nào?
Bạn phân biệt `Mono.empty()` với `Mono.just(value)` và trường hợp phát lỗi khi thiết kế kết quả tìm kiếm như thế nào?
Bạn xác định vì sao `Mono.just(null)` không phù hợp với hợp đồng Reactor và cách dùng `Mono.justOrEmpty` ra sao?
Bạn phân biệt `Mono.fromCallable` với `Mono.just` theo thời điểm thực thi phép tính và xử lý exception như thế nào?
Bạn sử dụng `Mono.defer` để trì hoãn việc tạo một Mono cho từng subscription và so sánh với tạo Publisher trước như thế nào?
Bạn giải thích điểm khác giữa `Flux.fromIterable` và `Flux.defer` khi danh sách nguồn có thể thay đổi giữa những lần subscribe ra sao?
Bạn đánh giá rủi ro đọc trạng thái shared mutable tại thời điểm assembly thay vì tại thời điểm subscription như thế nào?
Bạn phân biệt Publisher cold với hot theo việc mỗi subscriber có quan sát lại dữ liệu từ nguồn hay không như thế nào?
Bạn giải thích vì sao hai lần subscribe vào cold `Flux` có thể làm hai lần gọi API hoặc đọc cơ sở dữ liệu ra sao?
Bạn phân biệt `share` với `cache` theo vòng đời chia sẻ dữ liệu và cách subscriber đến sau nhận sự kiện như thế nào?
Bạn đánh giá tác động của `Flux.replay` hoặc replaying sink khi cần cung cấp lại lịch sử sự kiện cho subscriber mới ra sao?
Bạn lựa chọn `publish().refCount(...)` hoặc `autoConnect(...)` để điều khiển thời điểm kết nối vào nguồn hot như thế nào?
Bạn xác định rủi ro lặp lại side effect khi code gọi `subscribe` nhiều lần mà không kiểm soát subscription như thế nào?
Bạn giải thích chức năng của `Sinks.One`, `Sinks.Many` và lựa chọn phù hợp với loại sự kiện đầu ra ra sao?
Bạn phân biệt multicast sink với replay sink khi một subscriber bắt đầu nghe muộn hơn các subscriber khác như thế nào?
Bạn xác định cách xử lý kết quả `tryEmitNext` khi sink không thể phát sự kiện theo trạng thái hiện tại như thế nào?
Bạn đánh giá nhu cầu tuần tự hóa phát sự kiện từ nhiều thread khi sử dụng sink trong một service nhận sự kiện đồng thời ra sao?
Bạn giải thích vì sao một hot source có thể làm mất sự kiện đối với subscriber chưa đăng ký và cách xác lập hợp đồng dữ liệu ra sao?
Bạn mô hình hóa vòng đời kết nối nguồn sự kiện bên ngoài để các subscriber chia sẻ hợp lý mà không mở kết nối trùng lặp như thế nào?
Bạn lựa chọn `map` khi một phần tử đầu vào tạo đúng một giá trị biến đổi đồng bộ và xác định giới hạn của nó ra sao?
Bạn phân biệt `flatMap` với `map` khi hàm ánh xạ trả về một `Mono` hoặc `Flux` bất đồng bộ như thế nào?
Bạn giải thích vì sao `flatMap` có thể phát kết quả không theo thứ tự nguồn nếu các Publisher con hoàn thành khác nhau như thế nào?
Bạn lựa chọn `concatMap` khi cần xử lý lần lượt từng phần tử và bảo toàn thứ tự, đồng thời đánh giá ảnh hưởng lên throughput ra sao?
Bạn so sánh `flatMapSequential` với `concatMap` về khả năng thực hiện việc bên trong đồng thời và thứ tự kết quả như thế nào?
Bạn xác định cách cấu hình concurrency của `flatMap` để không mở quá nhiều request tới dịch vụ phụ thuộc ra sao?
Bạn đánh giá rủi ro tăng concurrency quá mức khiến hàng đợi nội bộ hoặc số connection tăng không kiểm soát như thế nào?
Bạn phân biệt `filter` với `filterWhen` khi predicate cần gọi một tác vụ bất đồng bộ để xác định điều kiện như thế nào?
Bạn giải thích vì sao side effect trong `filter` có thể bị gọi lại khi một publisher được retry hoặc subscribe lại ra sao?
Bạn lựa chọn `zip` khi nhiều Mono độc lập cùng cần kết quả và mô tả trường hợp một nguồn hoàn tất rỗng như thế nào?
Bạn phân biệt `zip` với `combineLatest` khi các luồng phát nhiều giá trị theo thời gian ra sao?
Bạn sử dụng `merge` để kết hợp nhiều nguồn sự kiện và xác định vì sao thứ tự giữa các nguồn không được bảo đảm như thế nào?
Bạn lựa chọn `concat` thay cho `merge` khi yêu cầu một nguồn hoàn tất trước khi bắt đầu nguồn tiếp theo như thế nào?
Bạn phân biệt `switchMap` với `flatMap` khi chỉ giữ kết quả của request mới nhất trong một luồng tìm kiếm ra sao?
Bạn kiểm chứng cancellation của Publisher con khi `switchMap` chuyển sang một đầu vào mới như thế nào?
Bạn thiết kế pipeline dùng `distinctUntilChanged` để giảm thông báo trạng thái lặp liên tiếp và xác định cách so sánh như thế nào?
Bạn phân biệt `distinct` với `distinctUntilChanged` về bộ nhớ và phạm vi loại các phần tử trùng lặp ra sao?
Bạn đánh giá chi phí của `sort` trên một `Flux` lớn hoặc vô hạn và xác định khi nào phải giới hạn nguồn như thế nào?
Bạn lựa chọn `buffer`, `window` hoặc `groupBy` để phân chia dòng dữ liệu và giải thích sự khác nhau về kiểu kết quả ra sao?
Bạn dùng `bufferTimeout` để gửi batch theo số lượng hoặc thời gian và kiểm soát batch cuối khi nguồn kết thúc như thế nào?
Bạn xác định rủi ro tích tụ nhiều nhóm chưa được tiêu thụ khi dùng `groupBy` trên khóa có cardinality cao như thế nào?
Bạn so sánh `sample`, `throttleFirst` và `debounce` theo cách lựa chọn sự kiện trong một luồng phát nhanh ra sao?
Bạn thiết kế luồng tìm kiếm giao diện dùng `debounce` và `switchMap` để tránh hiển thị kết quả request cũ như thế nào?
Bạn phân biệt `take`, `takeUntil` và `takeWhile` theo điều kiện dừng xử lý và ảnh hưởng tới upstream ra sao?
Bạn giải thích vì sao `collectList` buộc phải tích lũy các phần tử và có thể tốn bộ nhớ lớn với một nguồn không giới hạn như thế nào?
Bạn lựa chọn `reduce` hoặc `scan` khi chỉ cần kết quả tổng cuối hay cần quan sát các giá trị tích lũy trung gian như thế nào?
Bạn xác định điều kiện để một phép reduce giữ đúng kết quả khi upstream được phát song song theo nhiều nhánh ra sao?
Bạn phân biệt `then`, `thenReturn` và `thenMany` về việc bỏ qua dữ liệu upstream và chuyển sang công việc tiếp theo như thế nào?
Bạn thiết kế pipeline xử lý chuỗi thao tác mà bước sau chỉ chạy khi bước trước hoàn tất thành công như thế nào?
Bạn phân biệt `defaultIfEmpty` và `switchIfEmpty` khi một Publisher không phát phần tử nào nhưng vẫn hoàn tất thành công như thế nào?
Bạn xác định vì sao nguồn dự phòng tạo quá sớm có thể gây side effect trước khi `switchIfEmpty` thật sự cần dùng như thế nào?
Bạn dùng `handle` khi cần lọc và ánh xạ trong một bước và bảo đảm không phát `null` ra sao?
Bạn giải thích cách `transform` hoặc `transformDeferred` giúp tái sử dụng một chuỗi toán tử và kiểm soát trạng thái theo subscription như thế nào?
Bạn phân biệt việc tái sử dụng toán tử thuần với tái sử dụng callback giữ trạng thái mutable giữa các subscriber ra sao?
Bạn xác định điều gì xảy ra khi một hàm trong `map` ném exception và cách lỗi truyền tới downstream như thế nào?
Bạn mô tả vai trò của `doOnNext`, `doOnError`, `doOnComplete` và `doFinally` trong việc quan sát vòng đời mà không thay đổi dữ liệu như thế nào?
Bạn xác định vì sao `doOnNext` không phù hợp để biểu diễn thao tác ghi bắt buộc phải được xác nhận hoàn tất như thế nào?
Bạn phân biệt `doOnCancel` với `doFinally` khi muốn dọn dẹp tài nguyên ở các kiểu kết thúc khác nhau ra sao?
Bạn giải thích vai trò của backpressure khi người xử lý dữ liệu chậm hơn nguồn phát trong thời gian dài như thế nào?
Bạn mô tả sự khác nhau giữa demand không giới hạn và request theo từng batch khi Subscriber tiêu thụ dữ liệu như thế nào?
Bạn sử dụng `BaseSubscriber` để điều khiển `request(n)` thủ công và xác định khi nào cần yêu cầu thêm phần tử ra sao?
Bạn phân biệt giới hạn request của downstream với số phần tử một toán tử có thể prefetch từ upstream như thế nào?
Bạn giải thích cách prefetch của `flatMap` hoặc `concatMap` tác động đến hàng đợi nội bộ và tài nguyên như thế nào?
Bạn lựa chọn `limitRate` để điều tiết lượng yêu cầu upstream mà không nhầm nó với giới hạn số phần tử đầu ra như thế nào?
Bạn phân biệt `limitRequest` với `limitRate` về tổng lượng dữ liệu và cách phân chia demand ra sao?
Bạn đánh giá rủi ro một bộ đệm không giới hạn che lấp vấn đề producer quá nhanh nhưng gây tăng heap như thế nào?
Bạn thiết kế `onBackpressureBuffer` với giới hạn bộ nhớ và chiến lược xử lý tràn phù hợp như thế nào?
Bạn phân biệt `onBackpressureDrop`, `onBackpressureLatest` và `onBackpressureError` theo mức độ chấp nhận mất sự kiện ra sao?
Bạn xác định trường hợp dữ liệu đo nhiệt độ cho phép chỉ giữ giá trị mới nhất nhưng sự kiện thanh toán tuyệt đối không được bỏ như thế nào?
Bạn giải thích vì sao việc drop một phần tử không thể được sử dụng tùy tiện khi kết quả cần bảo đảm tính đầy đủ của nghiệp vụ như thế nào?
Bạn mô hình hóa cơ chế backpressure cho nguồn nhận sự kiện từ message broker khi broker có cơ chế prefetch và acknowledgment riêng như thế nào?
Bạn phân biệt backpressure trong bộ nhớ của ứng dụng với kiểm soát tốc độ của producer qua giao thức mạng như thế nào?
Bạn đánh giá ý nghĩa của `Flux.create` và các overflow strategy khi kết nối một API callback có thể phát dữ liệu nhanh như thế nào?
Bạn phân biệt `Flux.push` với `Flux.create` theo giả định về số thread phát dữ liệu từ nguồn như thế nào?
Bạn xác định cách unregister callback và ngừng nguồn phát khi Subscriber hủy subscription từ một `Flux.create` như thế nào?
Bạn giải thích vì sao `Flux.generate` phù hợp với cách phát đồng bộ từng phần tử theo yêu cầu thay vì callback push bất đồng bộ như thế nào?
Bạn lựa chọn chính sách cấp phát buffer khi dữ liệu được tạo theo burst và downstream có tốc độ tiêu thụ biến thiên ra sao?
Bạn thiết kế phép đo số phần tử đang chờ, độ trễ xử lý và tỷ lệ drop để biết pipeline có đáp ứng backpressure đúng như thiết kế như thế nào?
Bạn phân biệt `buffer` theo số lượng phần tử với backpressure thực sự ở nguồn khi đánh giá khả năng chịu tải như thế nào?
Bạn đánh giá trường hợp mô hình backpressure chỉ dời điểm nghẽn sang database pool hoặc hàng đợi bên ngoài ra sao?
Bạn xác định cách thiết lập giới hạn concurrency và timeout phối hợp để tránh tình trạng tăng số request tồn đọng khi backend chậm như thế nào?
Bạn thiết kế một nguồn dữ liệu có thể tạm dừng đọc khi downstream chưa có demand thay vì tiếp tục nhận dữ liệu vào một danh sách vô hạn như thế nào?
Bạn giải thích vì sao `publishOn` thay đổi ngữ cảnh thực thi của các toán tử phía sau trong một pipeline như thế nào?
Bạn phân biệt `subscribeOn` với `publishOn` theo ảnh hưởng tới quá trình subscription và các đoạn pipeline thực thi ra sao?
Bạn xác định tác động khi một pipeline có nhiều `publishOn` liên tiếp và cân nhắc chi phí chuyển thread như thế nào?
Bạn giải thích cách Reactor `Scheduler` phối hợp thực thi công việc mà không đồng nghĩa mỗi phần tử luôn có một thread mới như thế nào?
Bạn lựa chọn `Schedulers.parallel()` khi có phép tính CPU-bound ngắn và xác định giới hạn số công việc phù hợp ra sao?
Bạn sử dụng `Schedulers.boundedElastic()` để cô lập lời gọi blocking mà không chặn event-loop thread như thế nào?
Bạn đánh giá rủi ro chuyển toàn bộ pipeline sang `boundedElastic` rồi coi đó là cách giải quyết triệt để blocking I/O như thế nào?
Bạn phân biệt `Schedulers.single()` với `Schedulers.immediate()` theo cách lập lịch và phạm vi thread ra sao?
Bạn thiết kế đoạn xử lý gọi SDK blocking được bọc bằng `Mono.fromCallable` kết hợp scheduler phù hợp như thế nào?
Bạn xác định cách nhận biết một lời gọi blocking đang chạy trên Netty event loop và tác động tới latency toàn hệ thống ra sao?
Bạn sử dụng profiling hoặc công cụ phát hiện blocking để truy tìm thao tác `block()` không phù hợp trong luồng reactive như thế nào?
Bạn phân biệt `block()` ở ranh giới tích hợp đồng bộ với `block()` ở bên trong một pipeline hoặc request handler reactive như thế nào?
Bạn đánh giá khi nào việc chuyển qua scheduler khác giúp xử lý CPU-bound công việc và khi nào nên dùng worker service riêng ra sao?
Bạn mô tả lý do không nên giả định một toán tử Reactor luôn thực thi trên cùng thread với nơi pipeline được tạo như thế nào?
Bạn kiểm soát tác động của scheduler dùng chung khi một tác vụ dài chiếm tài nguyên và làm chậm các subscription khác ra sao?
Bạn xác định chính sách quản lý vòng đời scheduler tùy chỉnh để tránh rò rỉ thread sau khi ứng dụng dừng như thế nào?
Bạn giải thích vì sao Reactor `Context` phù hợp với metadata theo subscription hơn `ThreadLocal` trong pipeline đổi thread như thế nào?
Bạn truyền correlation ID qua `contextWrite` và truy cập bằng `deferContextual` để thực hiện tracing như thế nào?
Bạn phân biệt thông tin trong Reactor Context với dữ liệu đi qua `onNext` khi thiết kế API reactive như thế nào?
Bạn thiết kế cơ chế truyền thông tin xác thực qua các bước bất đồng bộ mà không sử dụng biến global mutable ra sao?
Bạn đánh giá rủi ro sao chép hoặc ghi log thông tin nhạy cảm khi đưa metadata của request vào Context như thế nào?
Bạn giải thích vì sao thứ tự áp dụng `contextWrite` có thể ảnh hưởng tới toán tử nào quan sát được một giá trị Context ra sao?
Bạn phân tích ảnh hưởng của cancellation đối với công việc đã được schedule nhưng chưa bắt đầu chạy như thế nào?
Bạn thiết kế kiểm thử quan sát scheduler và Context trong pipeline có hai nhánh `flatMap` chạy đồng thời ra sao?
Bạn phân biệt lỗi được phát bằng `onError` với trạng thái luồng hoàn tất rỗng và cách API báo mỗi trường hợp như thế nào?
Bạn giải thích vì sao `onError` chấm dứt luồng gốc và một toán tử fallback thường chuyển sang luồng thay thế như thế nào?
Bạn lựa chọn `onErrorReturn` khi cần giá trị mặc định và xác định trường hợp giá trị đó có thể che giấu lỗi quan trọng ra sao?
Bạn dùng `onErrorResume` để chuyển sang nguồn dự phòng theo loại lỗi và giữ ngữ nghĩa nghiệp vụ như thế nào?
Bạn phân biệt `onErrorMap` với `onErrorResume` khi muốn chuyển đổi exception nhưng không thay đổi đường đi thành công ra sao?
Bạn xác định cách dùng `onErrorComplete` an toàn khi một loại lỗi có thể bỏ qua mà không làm sai lệch dữ liệu như thế nào?
Bạn giải thích vì sao `onErrorContinue` có ngữ nghĩa phụ thuộc toán tử và cần được cân nhắc kỹ thay vì xem là cách bỏ qua lỗi chung như thế nào?
Bạn thiết kế cách xử lý lỗi từng phần tử bên trong `flatMap` để một bản ghi hỏng không làm dừng toàn bộ luồng khi nghiệp vụ cho phép như thế nào?
Bạn phân biệt `retry` với `repeat` về điều kiện chạy lại Publisher sau lỗi hay sau hoàn tất thành công như thế nào?
Bạn đánh giá nguy cơ retry một thao tác ghi không idempotent làm trùng giao dịch hoặc tác dụng phụ như thế nào?
Bạn sử dụng `retryWhen` với backoff và lọc loại lỗi để tránh retry vô hạn khi backend gặp lỗi vĩnh viễn như thế nào?
Bạn giải thích vì sao retry thường tạo subscription mới tới cold source và có thể thực thi lại các side effect như thế nào?
Bạn thiết kế timeout ở một thao tác con khác với timeout cho toàn bộ request để giữ ngân sách độ trễ như thế nào?
Bạn phân biệt timeout do không có sự kiện kế tiếp với deadline tổng của một workflow nhiều bước như thế nào?
Bạn xác định chính sách kết hợp timeout, retry và fallback để không làm tăng độ trễ vượt thời hạn request ra sao?
Bạn xử lý lỗi hủy và lỗi timeout khi một Publisher phụ thuộc vào một request HTTP bên ngoài mà hủy không bảo đảm request đã dừng như thế nào?
Bạn thiết kế cleanup cho tài nguyên bất đồng bộ bằng `usingWhen` khi source hoàn tất, lỗi hoặc bị hủy như thế nào?
Bạn phân biệt `Flux.using` với `usingWhen` theo yêu cầu đóng tài nguyên đồng bộ hoặc bất đồng bộ ra sao?
Bạn đánh giá rủi ro một cleanup publisher cũng phát lỗi và ảnh hưởng đến tín hiệu lỗi được downstream quan sát như thế nào?
Bạn xác định cách chuyển đổi exception sang mã phản hồi nghiệp vụ tại ranh giới WebFlux mà không làm mất thông tin lỗi gốc như thế nào?
Bạn thiết kế logging bằng `doOnError` nhưng tránh ghi cùng một lỗi nhiều lần qua các tầng pipeline ra sao?
Bạn giải thích vì sao callback `subscribe` không có xử lý error phù hợp có thể khiến lỗi trở nên khó quan sát như thế nào?
Bạn thiết kế cơ chế phân loại lỗi transient và permanent trước khi quyết định retry trong một service reactive như thế nào?
Bạn phân biệt hủy subscription do client ngắt kết nối với lỗi nghiệp vụ của server để xây dựng số liệu giám sát như thế nào?
Bạn mô hình hóa một endpoint Spring WebFlux trả về `Mono` hoặc `Flux` và xác định nơi thực sự bắt đầu subscription như thế nào?
Bạn phân biệt controller WebFlux trả Publisher với việc tự gọi `subscribe()` bên trong controller về vòng đời request như thế nào?
Bạn đánh giá vì sao tự gọi `subscribe()` trong service để thực hiện ghi dữ liệu có thể làm mất phối hợp lỗi và cancellation ra sao?
Bạn thiết kế đường đi của dữ liệu từ WebClient đến bước biến đổi và response mà không sử dụng `block()` trong handler reactive như thế nào?
Bạn phân biệt thao tác HTTP client có non-blocking I/O với thư viện HTTP đồng bộ được bọc trong `Mono` như thế nào?
Bạn kiểm soát số kết nối đồng thời và thời gian chờ khi `flatMap` tạo nhiều request WebClient tới cùng một backend ra sao?
Bạn thiết kế pipeline fan-out/fan-in gọi hai dịch vụ độc lập nhưng xử lý chính xác khi một kết quả không tồn tại như thế nào?
Bạn phân biệt ghi dữ liệu qua R2DBC với thao tác JDBC blocking trong ứng dụng WebFlux về cơ chế I/O và thread như thế nào?
Bạn xác định phạm vi transaction khi nhiều bước truy cập database reactive được compose thành cùng một Publisher như thế nào?
Bạn thiết kế cơ chế xử lý sự kiện từ Kafka hoặc RabbitMQ để acknowledgment xảy ra sau khi công việc nghiệp vụ hoàn tất như thế nào?
Bạn phân biệt demand của Reactive Streams với bảo đảm giao hàng và acknowledgment của message broker ra sao?
Bạn đánh giá việc retry sự kiện từ broker có thể gây xử lý trùng và thiết kế idempotency ở consumer như thế nào?
Bạn tổ chức thứ tự xử lý theo khóa nghiệp vụ khi nhiều sự kiện cần đi qua một pipeline có concurrency như thế nào?
Bạn lựa chọn chiến lược xử lý các bản ghi lỗi bằng dead-letter queue thay vì bỏ mất sự kiện từ stream ra sao?
Bạn giải thích ý nghĩa của backpressure khi phát Server-Sent Events từ một nguồn có thể nhanh hơn client tiêu thụ như thế nào?
Bạn thiết kế luồng SSE hoặc WebSocket giữ kết nối dài và quản lý tình huống client hủy subscription như thế nào?
Bạn đánh giá việc gom toàn bộ `Flux` vô hạn thành danh sách trước khi trả response sẽ ảnh hưởng tài nguyên như thế nào?
Bạn xây dựng quy tắc kiểm soát số bản ghi tối đa và phân trang khi endpoint dữ liệu có thể trả khối lượng lớn ra sao?
Bạn xác định ranh giới API nào nên trả kết quả theo reactive Publisher và ranh giới nào cần adapter đồng bộ theo nhu cầu hệ thống ra sao?
Bạn thiết kế cơ chế bulkhead cho một downstream chậm để tránh một nhóm request sử dụng hết connection hoặc scheduler chung như thế nào?
Bạn đánh giá ưu nhược điểm của Reactor so với xử lý request theo virtual thread khi phần lớn dependency có API blocking như thế nào?
Bạn phân biệt tính đúng của nghiệp vụ với mô hình thực thi reactive khi quyết định chuyển từ ứng dụng đồng bộ sang WebFlux như thế nào?
Bạn thiết kế chiến lược migration từ API callback hoặc `CompletableFuture` sang `Mono` mà vẫn bảo toàn lỗi và khả năng hủy như thế nào?
Bạn đánh giá điểm nghẽn do CPU-bound conversion khi một dịch vụ reactive tiêu thụ ít thread I/O nhưng vẫn có độ trễ cao ra sao?
Bạn xác định các chỉ số theo dõi số subscription hoạt động, latency, buffer occupancy, error và cancellation trong production như thế nào?
Bạn thiết kế cơ chế gắn trace ID qua nhiều Publisher bất đồng bộ để có thể liên kết log của một request như thế nào?
Bạn phân biệt metric theo tín hiệu onNext với metric theo request hoàn tất để không đếm sai số giao dịch thành công như thế nào?
Bạn xây dựng kiểm thử Reactor bằng `StepVerifier` để xác nhận thứ tự phần tử và tín hiệu hoàn tất như thế nào?
Bạn sử dụng `StepVerifier` để kiểm tra Publisher phát đúng một lỗi với loại exception và nội dung phù hợp ra sao?
Bạn thiết kế test phân biệt `Mono.empty()` với một Mono trả về giá trị mặc định khi không có dữ liệu như thế nào?
Bạn kiểm tra Publisher phát nhiều phần tử hơn nhu cầu bằng bước yêu cầu demand có kiểm soát trong `StepVerifier` ra sao?
Bạn sử dụng `thenRequest` trong `StepVerifier` để xác minh pipeline chỉ phát tiếp khi Subscriber cấp thêm demand như thế nào?
Bạn kiểm thử cancellation giữa luồng bằng `thenCancel` và xác minh tài nguyên hoặc callback được giải phóng như thế nào?
Bạn xác định cách dùng `StepVerifier.withVirtualTime` để kiểm tra `delayElements`, timeout hoặc retry backoff mà không chờ thời gian thực ra sao?
Bạn giải thích vì sao Publisher dùng scheduler thời gian cần được tạo đúng thời điểm trong test virtual time để kiểm thử có hiệu lực như thế nào?
Bạn phân biệt việc điều khiển virtual time với dùng thời gian hệ thống thực khi kiểm tra một phép timeout phụ thuộc clock bên ngoài ra sao?
Bạn sử dụng `TestPublisher` để mô phỏng nguồn phát chủ động và kiểm thử những trường hợp dữ liệu đến theo thứ tự bất thường như thế nào?
Bạn thiết kế kiểm thử một Publisher phụ thuộc được giả lập bằng `PublisherProbe` để xác nhận fallback có thực sự được subscribe hay không như thế nào?
Bạn kiểm tra thứ tự kết quả của `flatMap`, `concatMap` và `flatMapSequential` bằng các nguồn con có độ trễ khác nhau ra sao?
Bạn xây dựng kiểm thử cho trường hợp một toán tử `zip` gặp nguồn rỗng và xác minh tác động tới Publisher còn lại như thế nào?
Bạn kiểm chứng `retryWhen` không chạy lại với lỗi không được phép retry và dừng đúng số lần khi lỗi liên tục như thế nào?
Bạn mô phỏng backend chậm rồi kiểm thử giới hạn concurrency để bảo đảm không phát sinh quá nhiều request đang chạy ra sao?
Bạn dùng một test subscriber để đo demand và phát hiện toán tử prefetch quá nhiều dữ liệu so với ngân sách bộ nhớ như thế nào?
Bạn tạo test cho chính sách `onBackpressureDrop` và xác nhận tập sự kiện bị bỏ là đúng theo hợp đồng ứng dụng như thế nào?
Bạn kiểm tra một hot Publisher khi subscriber thứ hai đến muộn và xác định dữ liệu có được replay hay không như thế nào?
Bạn xây dựng test cho việc một sink nhận tín hiệu đồng thời từ nhiều thread và xử lý trường hợp emit thất bại ra sao?
Bạn kiểm tra Reactor Context được truyền qua thay đổi scheduler và không rò rỉ metadata sang subscription khác như thế nào?
Bạn thiết kế test đảm bảo `usingWhen` giải phóng tài nguyên cả khi hoàn tất, lỗi và cancellation ra sao?
Bạn phân biệt kiểm thử logic của từng toán tử với kiểm thử tích hợp dùng WebClient và database thực khi xác nhận một workflow reactive như thế nào?
Bạn phân tích vì sao test chỉ gọi `subscribe()` rồi kết thúc có thể bỏ qua lỗi bất đồng bộ và chưa chứng minh điều kiện kỳ vọng ra sao?
Bạn xây dựng bộ test property-based cho pipeline biến đổi dữ liệu để so sánh kết quả với thuật toán tham chiếu trên nhiều input như thế nào?
Bạn đánh giá cách mô phỏng các tình huống subscriber xử lý chậm, ngắt mạng và backend trả lỗi để kiểm chứng resilience của hệ reactive ra sao?
Bạn thiết kế benchmark throughput và p99 latency cho pipeline reactive mà vẫn kiểm soát số request đồng thời và dữ liệu thử nghiệm như thế nào?
Bạn phân biệt nguyên nhân latency do hàng đợi backpressure, blocking trên event loop và pool kết nối khi phân tích log hoặc tracing như thế nào?
Bạn đánh giá chi phí của việc dùng quá nhiều toán tử và scheduler boundary trong hot path so với phép biến đổi đơn giản như thế nào?
Bạn xác định trường hợp nào nên tối ưu số request từ upstream thay vì chỉ tăng buffer hoặc thread count cho downstream ra sao?
Bạn thiết kế quy tắc code review cho pipeline reactive về tác dụng phụ, giới hạn concurrency, backpressure và đường truyền lỗi như thế nào?
Bạn lập kế hoạch refactor một service reactive lồng nhiều lời gọi `subscribe()` thành một pipeline có vòng đời thống nhất như thế nào?
Bạn giải thích những điều kiện cần kiểm tra trước khi tuyên bố một hệ thống reactive có khả năng mở rộng tốt hơn phiên bản đồng bộ như thế nào?
Bạn lựa chọn các tiêu chí để quyết định dùng `Mono`/`Flux` hay code đồng bộ cho một nghiệp vụ có I/O, CPU và yêu cầu bảo trì khác nhau như thế nào?

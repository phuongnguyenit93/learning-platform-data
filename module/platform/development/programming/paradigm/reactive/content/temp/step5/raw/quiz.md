Câu 1. Mục tiêu của mô hình reactive khi xử lý luồng sự kiện là gì?
A. Buộc mọi tác vụ chạy tuần tự trên một thread cố định
B. Xử lý tín hiệu sự kiện bằng pipeline bất đồng bộ
C. Biến mọi phép đọc I/O thành thao tác đồng bộ chặn luồng
D. Hoãn mọi phép tính cho tới khi chương trình kết thúc
Đáp án đúng: B

Câu 2. Trong Reactive Streams, giao diện `Publisher<T>` cung cấp thao tác cốt lõi nào?
A. Cho `Subscriber` đăng ký nhận các tín hiệu từ nguồn
B. Trả ngay một danh sách chứa mọi giá trị đã phát
C. Chỉ cho phép đọc dữ liệu sau khi stream hoàn tất
D. Tự chọn số thread thực thi mọi tác vụ trong pipeline
Đáp án đúng: A

Câu 3. Trong hợp đồng Reactive Streams, `onSubscribe` cung cấp cho subscriber thứ gì?
A. Một `Iterator` tự đọc hết dữ liệu không cần demand
B. Một `Scheduler` để chỉ định thread xử lý tín hiệu
C. `Subscription` để điều khiển demand và hủy
D. Một `CompletableFuture` chứa toàn bộ kết quả cuối
Đáp án đúng: C

Câu 4. Ý nghĩa của `Subscription.request(n)` với `n > 0` là gì?
A. Buộc producer phát đúng `n` phần tử ngay lập tức
B. Yêu cầu chạy đồng thời đúng `n` worker cho subscriber
C. Thông báo nhu cầu nhận thêm tối đa `n` phần tử
D. Đặt giới hạn cố định cho mọi đăng ký trong tương lai
Đáp án đúng: C

Câu 5. Theo Reactive Streams, yêu cầu `request(0)` nên dẫn đến điều gì?
A. Đặt demand về không và xóa dữ liệu đã nhận trước đó
B. Hoàn thành bình thường mà không gửi thêm dữ liệu nào
C. Tạm dừng vô thời hạn nhưng không phát tín hiệu lỗi
D. Phát tín hiệu lỗi do số phần tử yêu cầu không hợp lệ
Đáp án đúng: D

Câu 6. Khi chưa có đủ demand, `Publisher` tuân thủ Reactive Streams phải làm gì?
A. Tự gửi dữ liệu rồi để subscriber bỏ phần vượt giới hạn
B. Chuyển mọi tín hiệu `onNext` thành `onComplete` sớm
C. Không gửi số tín hiệu `onNext` vượt quá tổng demand
D. Buộc subscriber tăng demand bằng một thread phụ mới
Đáp án đúng: C

Câu 7. Sau `onComplete`, một Publisher hợp lệ có thể phát tiếp tín hiệu nào?
A. Không phát thêm `onNext` hay tín hiệu kết thúc khác
B. Phát `onError` để xác nhận lần hoàn thành trước đó
C. Phát thêm một `onSubscribe` trên cùng subscription
D. Tiếp tục `onNext` nếu subscriber còn demand chưa dùng
Đáp án đúng: A

Câu 8. Khi subscriber gọi `Subscription.cancel()`, tác dụng mong muốn là gì?
A. Đảm bảo xóa sạch mọi tác dụng phụ đã xảy ra trước đó
B. Phát `onComplete` ngay cho mọi subscriber khác của nguồn
C. Yêu cầu ngừng phát; tín hiệu đang đua vẫn có thể tới
D. Đặt demand về vô hạn để xả toàn bộ phần tử còn lại
Đáp án đúng: C

Câu 9. Nếu Publisher phát `onError`, hợp đồng tín hiệu yêu cầu điều gì?
A. Tự đăng ký lại Subscriber và tiếp tục luồng ban đầu
B. Xem đó là tín hiệu kết thúc, không phát `onComplete` sau
C. Phát `onComplete` ngay sau lỗi để xác nhận đã xử lý
D. Đổi lỗi thành một phần tử thông thường ở lần `onNext` kế
Đáp án đúng: B

Câu 10. Trong Reactive Streams, `Processor<T,R>` kết hợp vai trò nào?
A. Vừa là `Publisher<T>`, vừa là `ExecutorService`
B. Vừa là `Subscription`, vừa là `Scheduler` của JVM
C. Vừa là `Subscriber<T>`, vừa là `Publisher<R>`
D. Vừa là `Subscriber<R>`, vừa là `ThreadFactory`
Đáp án đúng: C

Câu 11. Đặc điểm của một nguồn cold trong lập trình reactive là gì?
A. Mọi subscriber đều bắt buộc nhận đúng một nguồn phát chung
B. Nguồn tự chạy trước lúc tồn tại subscriber đầu tiên
C. Mỗi subscription có thể kích hoạt việc tạo dữ liệu riêng
D. Subscriber mới chỉ có thể nhận dữ liệu sau cùng đã phát
Đáp án đúng: C

Câu 12. Nguồn hot khác nguồn cold ở điểm nào thường gặp?
A. Mọi subscriber đều nhận đầy đủ dữ liệu lịch sử của nguồn
B. Nguồn có thể phát độc lập với thời điểm subscriber tham gia
C. Nguồn chỉ phát sau khi subscriber gọi `block()` để nhận
D. Mỗi lần subscribe luôn chạy lại toàn bộ phép tính từ đầu
Đáp án đúng: B

Câu 13. Trong Project Reactor, `Mono<T>` biểu diễn số phần tử kết quả nào?
A. Có thể hoàn tất với không hoặc một giá trị kiểu `T`
B. Bắt buộc phát đúng một giá trị rồi mới được hoàn tất
C. Bắt buộc phát từ hai giá trị trở lên trước khi hoàn tất
D. Có thể phát vô hạn giá trị khác nhau qua cùng subscription
Đáp án đúng: A

Câu 14. Trong Project Reactor, `Flux<T>` thường được dùng cho trường hợp nào?
A. Luồng có thể phát không, một hoặc nhiều phần tử kiểu `T`
B. Chỉ đại diện cho một tín hiệu lỗi mà không có phần tử dữ liệu
C. Chỉ tạo nguồn đồng bộ từ mảng, không hỗ trợ sự kiện bất đồng bộ
D. Chỉ một kết quả duy nhất được cung cấp theo dạng blocking
Đáp án đúng: A

Câu 15. Trong `Mono.just(compute())`, khi nào `compute()` được thực thi?
A. Chỉ khi một terminal operator hoàn tất và trả về giá trị
B. Chỉ sau khi subscriber gọi `request(1)` lần đầu tiên
C. Khi đánh giá lời gọi `Mono.just(...)`, trước subscription
D. Mỗi lần có subscriber mới đăng ký vào Mono hiện có
Đáp án đúng: C

Câu 16. Khi dùng `Mono.defer(() -> createMono())`, điều gì được trì hoãn?
A. Việc gọi supplier để tạo Mono tới lúc có subscription
B. Việc đóng scheduler cho đến khi toàn bộ ứng dụng dừng
C. Việc kiểm tra lỗi biên dịch của supplier tới lúc runtime
D. Việc gửi `onSubscribe` đến sau khi mọi dữ liệu được phát
Đáp án đúng: A

Câu 17. Toán tử `map(f)` trên `Flux<T>` thực hiện vai trò nào?
A. Biến đổi từng phần tử thành một giá trị qua hàm `f`
B. Đổi tín hiệu hoàn tất thành một lỗi để retry pipeline
C. Ghép các Publisher con đồng thời thành một luồng mới
D. Lọc các phần tử dựa trên kết quả boolean của hàm `f`
Đáp án đúng: A

Câu 18. Khi dùng `flatMap(f)` với các Publisher con bất đồng bộ, điều gì đúng?
A. Bảo đảm mỗi Publisher con hoàn thành theo thứ tự nguồn
B. Chỉ nhận phần tử cuối của mỗi Publisher con được tạo
C. Buộc mọi Publisher con chạy trên cùng một thread gọi
D. Có thể ghép đồng thời và thay đổi thứ tự giá trị nhận
Đáp án đúng: D

Câu 19. Điểm khác của `concatMap(f)` so với `flatMap(f)` thường là gì?
A. Giữ duy nhất luồng con mới nhất và hủy luồng trước
B. Bỏ qua mọi lỗi từ luồng con và tự động tiếp tục
C. Xử lý luồng con lần lượt, duy trì thứ tự nguồn
D. Chạy mọi luồng con đồng thời rồi sắp xếp kết quả
Đáp án đúng: C

Câu 20. `switchMap(f)` xử lý các Publisher con thế nào khi nguồn phát giá trị mới?
A. Chỉ chọn Publisher con đầu và bỏ mọi giá trị nguồn sau
B. Chờ tất cả Publisher con cũ hoàn tất rồi mới tạo mới
C. Gộp mọi Publisher con đã tạo để phát hết từng giá trị
D. Chuyển sang Publisher mới và hủy Publisher con trước
Đáp án đúng: D

Câu 21. Với `Flux.filter(predicate)`, phần tử nào được phát xuống downstream?
A. Phần tử có kết quả `predicate` là `true`
B. Mọi phần tử được ánh xạ sang kiểu `Boolean`
C. Chỉ phần tử xuất hiện cuối trong toàn bộ luồng
D. Phần tử có kết quả `predicate` là `false`
Đáp án đúng: A

Câu 22. `Flux.take(3)` trên nguồn có nhiều phần tử thường có tác dụng nào?
A. Chờ ba subscriber cùng đăng ký rồi bắt đầu phát
B. Lấy ba phần tử đầu rồi hủy đăng ký upstream
C. Chỉ phát các phần tử có giá trị số lớn hơn ba
D. Luôn lấy ba phần tử cuối sau khi nguồn hoàn tất
Đáp án đúng: B

Câu 23. Với `Flux.distinct()`, lưu ý tài nguyên nào cần quan tâm?
A. Phải lưu dấu khóa đã gặp nên có thể tăng bộ nhớ
B. Luôn giữ toàn bộ phần tử gốc trên ổ đĩa tạm
C. Luôn cấp một thread mới cho từng phần tử trùng
D. Chỉ hoạt động sau khi đã chuyển Flux thành Mono
Đáp án đúng: A

Câu 24. `flux.collectList()` chuyển pipeline thành kết quả kiểu nào?
A. Mono phát số lượng phần tử đã nhận từ nguồn
B. Flux phát một phần tử sau mỗi lần gọi `request`
C. Flux phát từng `List` gồm đúng một phần tử
D. Mono phát một `List` chứa các phần tử đã gom
Đáp án đúng: D

Câu 25. `Flux.zip(a,b)` kết hợp hai Flux dựa trên nguyên tắc nào?
A. Phát ngay từng phần tử của nguồn nào tới trước
B. Ghép phần tử tương ứng theo thứ tự từ hai nguồn
C. Chỉ giữ phần tử mới nhất khi một nguồn phát thêm
D. Nối hết phần tử của nguồn a rồi mới tới nguồn b
Đáp án đúng: B

Câu 26. Với `combineLatest(a,b)`, khi nào có thể tạo giá trị kết hợp đầu tiên?
A. Chỉ khi cả hai nguồn đều đã phát `onComplete`
B. Chỉ sau khi một nguồn phát tín hiệu lỗi đầu tiên
C. Khi một nguồn vừa phát giá trị đầu tiên của nó
D. Khi cả hai nguồn đã phát ít nhất một giá trị
Đáp án đúng: D

Câu 27. Với `Flux.merge(a,b)`, kết quả từ các nguồn bất đồng bộ có thứ tự thế nào?
A. Luôn sắp các phần tử theo thứ tự tăng dần của giá trị
B. Luôn lấy hết phần tử của a trước khi nhận phần tử b
C. Thứ tự giữa hai nguồn phụ thuộc thời điểm tín hiệu tới
D. Luôn xen kẽ chính xác một phần tử a rồi một phần tử b
Đáp án đúng: C

Câu 28. Đặc điểm của `Flux.concat(a,b)` khi hai nguồn thành công là gì?
A. Subscribe đồng thời hai nguồn và trộn theo thời gian tới
B. Chỉ giữ phần tử cuối cùng của nguồn a rồi chuyển sang b
C. Phát hết nguồn a trước khi subscribe và phát nguồn b
D. Chọn nguồn có dữ liệu đến trước, bỏ nguồn còn lại
Đáp án đúng: C

Câu 29. Khi upstream phát lỗi, `onErrorReturn(value)` thực hiện điều gì?
A. Phát giá trị thay thế rồi kết thúc bình thường
B. Chuyển lỗi thành một exception mới và tiếp tục
C. Chạy lại subscription upstream cho tới khi thành công
D. Gửi lỗi nguyên gốc tới downstream rồi phát value
Đáp án đúng: A

Câu 30. `onErrorResume(f)` khác `onErrorReturn` ở khả năng nào?
A. Chỉ thay lỗi bằng một giá trị đã cố định tại assembly
B. Chuyển sang một Publisher dự phòng được chọn từ lỗi
C. Chỉ ghi log lỗi rồi chuyển tiếp cùng tín hiệu lỗi cũ
D. Luôn đăng ký lại Publisher nguồn sau mỗi lần lỗi
Đáp án đúng: B

Câu 31. `onErrorMap(f)` dùng để làm gì trong Reactor?
A. Phát giá trị mặc định rồi chuyển sang luồng bình thường
B. Ánh xạ lỗi thành exception khác và vẫn kết thúc lỗi
C. Bỏ lỗi khỏi pipeline mà không phát terminal signal
D. Khôi phục Flux bằng Publisher thay thế rồi hoàn tất
Đáp án đúng: B

Câu 32. Với `retry(2)`, cần chú ý điều gì khi upstream có side effect?
A. Tự hoàn tác mọi side effect trước mỗi lần thử lại
B. Chỉ gọi lại handler xử lý lỗi mà không chạy upstream
C. Thay lỗi bằng đúng hai phần tử kết quả mặc định
D. Có thể subscribe lại tối đa hai lần nên tác vụ bị lặp
Đáp án đúng: D

Câu 33. `doOnNext(action)` thường phục vụ mục đích nào?
A. Bắt và chuyển mọi `onError` thành `onComplete`
B. Quan sát hay tạo side effect mà không đổi giá trị phát
C. Tạo một subscription mới mỗi lần phần tử được phát
D. Ánh xạ trực tiếp mỗi phần tử thành giá trị trả về action
Đáp án đúng: B

Câu 34. Reactor `Context` phù hợp để mang thông tin nào?
A. Dữ liệu chỉ được truy cập trước lúc gọi `subscribe()`
B. Metadata theo subscriber, không lệ thuộc thread cố định
C. Biến global mutable dùng chung cho tất cả subscription
D. Tham chiếu `ThreadLocal` được tự động lưu lên database
Đáp án đúng: B

Câu 35. `subscribeOn(scheduler)` chủ yếu đặt ranh giới thực thi ở đâu?
A. Chỉ đổi thread cho các toán tử nằm sau `subscribeOn`
B. Chỉ định một worker cho từng tín hiệu `onComplete`
C. Điều phối quá trình đăng ký và đoạn nguồn upstream
D. Ép mọi tác vụ trong ứng dụng dùng một thread duy nhất
Đáp án đúng: C

Câu 36. `publishOn(scheduler)` chủ yếu ảnh hưởng phạm vi nào trong pipeline?
A. Tự thay nguồn cold thành nguồn hot nhiều subscriber
B. Buộc mọi upstream operator thực thi trên scheduler mới
C. Chỉ tác động tới bước tạo Publisher trước khi subscribe
D. Chuyển xử lý tín hiệu downstream sang Scheduler chỉ định
Đáp án đúng: D

Câu 37. Khi cần tích hợp API blocking cũ vào Reactor, scheduler nào phù hợp nhất?
A. Dùng `parallel` vì luôn cấp vô hạn thread riêng mới
B. Dùng `immediate` vì mặc định tách tác vụ khỏi caller
C. Dùng `single` vì có thể chặn không giới hạn an toàn
D. Dùng `boundedElastic` để chạy API blocking
Đáp án đúng: D

Câu 38. Trong `parallel().runOn(Schedulers.parallel())`, `runOn` có vai trò gì?
A. Chỉ định scheduler thực thi công việc trên các rail
B. Bảo đảm mọi kết quả có cùng thứ tự với nguồn đầu
C. Loại bỏ hoàn toàn việc gửi yêu cầu backpressure
D. Biến mỗi rail thành nguồn cold không cần subscriber
Đáp án đúng: A

Câu 39. Vì sao cần tránh gọi `block()` trên thread non-blocking của Reactor?
A. Thao tác chặn tự tăng demand của mọi subscription khác
B. Thao tác chặn sẽ tự chuyển thành một lần subscribeAsync
C. Thao tác chặn có thể bị Reactor từ chối bằng lỗi
D. Thao tác chặn luôn chạy xong ngay mà không dùng thread
Đáp án đúng: C

Câu 40. `mono.timeout(Duration.ofSeconds(2))` mặc định phản ứng thế nào khi quá hạn?
A. Phát lỗi timeout nếu chưa có tín hiệu đúng hạn
B. Phát `null` rồi hoàn thành vì không có phần tử
C. Đăng ký lại nguồn vô hạn lần cho tới khi thành công
D. Tạm dừng timer và giữ subscription cho tới khi phát
Đáp án đúng: A

Câu 41. `onBackpressureBuffer()` cần thận trọng với rủi ro nào?
A. Chỉ chạy khi nguồn đã phát tín hiệu `onComplete`
B. Đệm phần tử khi downstream chậm có thể tăng bộ nhớ
C. Tự loại mọi phần tử thừa mà không dùng bộ nhớ đệm
D. Luôn giảm số request upstream xuống đúng bằng một
Đáp án đúng: B

Câu 42. `onBackpressureDrop()` thường áp dụng chiến lược nào?
A. Tạm dừng vô hạn mọi request cho đến khi có demand
B. Tự lưu mọi phần tử bị chậm vào bộ nhớ không giới hạn
C. Gửi mọi phần tử bất kể demand và bỏ qua hợp đồng
D. Bỏ phần tử chưa thể chuyển vì thiếu demand downstream
Đáp án đúng: D

Câu 43. `limitRate(10)` của Reactor chủ yếu dùng để điều chỉnh điều gì?
A. Chỉ cho tối đa mười subscriber cùng chạy trong JVM
B. Chặn các phần tử thứ mười một dù nguồn còn demand
C. Giới hạn chính xác mười phần tử mỗi giây thời gian thực
D. Điều tiết demand gửi về upstream theo những đợt
Đáp án đúng: D

Câu 44. Trong kiểm thử `StepVerifier.create(publisher)`, có thể xác nhận điều gì?
A. Kích thước heap chính xác sau khi publisher hoàn tất
B. Thứ tự tín hiệu phát và tín hiệu kết thúc dự kiến
C. Số thread tối đa được hệ điều hành cấp cho Reactor
D. Toàn bộ lịch thực thi của JVM qua nhiều process
Đáp án đúng: B

Câu 45. Vì sao `StepVerifier.withVirtualTime(...)` hữu ích khi kiểm thử `delayElements`?
A. Buộc tất cả tín hiệu `onNext` xuất hiện trong một giây
B. Tự suy luận kết quả của pipeline mà không cần assert
C. Tự biến mọi Publisher hot thành Publisher cold vĩnh viễn
D. Điều khiển đồng hồ giả để không cần chờ thời gian thật
Đáp án đúng: D

Câu 46. `TestPublisher` của Reactor Test thường dùng trong tình huống nào?
A. Thay toàn bộ scheduler bằng một ExecutorService thật
B. Tự tạo một server HTTP thật cho pipeline cần kiểm thử
C. Tự tối ưu pipeline giống bộ biên dịch của JVM
D. Chủ động phát tín hiệu để kiểm thử hành vi subscriber
Đáp án đúng: D

Câu 47. Khi Reactor pipeline dùng tài nguyên cần cleanup bất đồng bộ, `usingWhen` giúp gì?
A. Ép tài nguyên chỉ được đóng trên thread tạo nguồn
B. Gắn xử lý resource và dọn dẹp theo tín hiệu kết thúc
C. Chỉ tạo resource sau khi pipeline đã phát onComplete
D. Tự lưu mọi resource còn sống vào bộ nhớ đệm toàn cục
Đáp án đúng: B

Câu 48. Khi đo hiệu năng pipeline reactive, kết quả throughput cao có bảo đảm gì?
A. Không tự bảo đảm latency tốt nếu downstream bị quá tải
B. Luôn chứng minh mọi toán tử đều chạy non-blocking
C. Luôn chứng minh không còn race condition giữa các thread
D. Luôn chứng minh hệ thống không cần giới hạn demand
Đáp án đúng: A

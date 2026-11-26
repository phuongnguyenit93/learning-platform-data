Câu 01. Mục đích chính của `StepVerifier` trong `reactor-test` là gì?
A. Khởi chạy mọi publisher trên một thread cố định
B. Đo mức sử dụng CPU của từng operator trong pipeline
C. Kiểm tra thứ tự onNext và các tín hiệu kết thúc
D. Thay broker bằng một hàng đợi khi chạy unit test
Đáp án đúng: C

Câu 02. Với `Mono.just("OK")`, kịch bản StepVerifier nào thành công?
A. `expectNext("OK").verifyComplete()`
B. `expectNext("NO").verifyComplete()`
C. `expectNext("OK").verifyError()`
D. `expectNextCount(2).verifyComplete()`
Đáp án đúng: A

Câu 03. Đối với `Mono.empty()`, kịch bản kiểm thử nào đúng?
A. `expectNextCount(1).verifyComplete()`
B. `expectError().verify()` để kiểm tra giá trị rỗng
C. `expectComplete().verify()` khi không có onNext
D. `expectNext((String) null).verifyComplete()`
Đáp án đúng: C

Câu 04. Với `Flux.just(1, 2, 3)`, kỳ vọng nào kiểm tra đúng cả giá trị lẫn thứ tự?
A. `expectNext(1, 2, 3).verifyError()`
B. `expectNext(3, 2, 1).expectComplete().verify()`
C. `expectNext(1, 2, 3).verifyComplete()`
D. `expectNext(1, 3, 2).verifyComplete()`
Đáp án đúng: C

Câu 05. Publisher phát `IllegalStateException` rồi kết thúc; cách kỳ vọng tín hiệu nào phù hợp?
A. `expectComplete().verify()` sau khi nhận lỗi từ nguồn
B. `expectNext(IllegalStateException.class).verify()`
C. `expectNextCount(1).verifyComplete()`
D. `expectError(IllegalStateException.class).verify()`
Đáp án đúng: D

Câu 06. `expectNextMatches(v -> v > 0)` kiểm tra điều gì ở tín hiệu kế tiếp?
A. Giá trị lỗi onError được chuyển thành số dương
B. Kiểm giá trị onNext tiếp theo bằng predicate
C. Thời gian chờ tín hiệu kế tiếp phải lớn hơn không
D. Số phần tử onNext còn lại phải lớn hơn không
Đáp án đúng: B

Câu 07. Khi muốn kiểm nhiều trường của DTO nhận từ Mono, thao tác StepVerifier nào thích hợp?
A. `assertNext(dto -> assertEquals(42, dto.id()))`
B. `thenRequest(dto -> assertEquals(42, dto.id()))`
C. `expectNextCount(dto -> dto.id() == 42)`
D. `expectErrorMatches(dto -> dto.id() == 42)`
Đáp án đúng: A

Câu 08. `expectNextCount(3)` khác `expectNext(a,b,c)` chủ yếu ở điểm nào?
A. Đếm ba giá trị onNext mà không so nội dung
B. Chỉ xác nhận đã request ba phần tử từ upstream
C. Chỉ xác nhận có đúng ba subscriber đang hoạt động
D. Chỉ xác nhận ba giây đã trôi qua khi tạo publisher
Đáp án đúng: A

Câu 09. Nếu dùng `verifyComplete()` ở cuối kịch bản, phương thức này làm gì?
A. Chấp nhận cả onError lẫn onComplete làm kết thúc
B. Gửi tín hiệu cancel thay cho xác nhận hoàn tất
C. Chỉ khai báo điều kiện onComplete mà chưa chạy test
D. Bắt đầu xác minh và đòi hỏi tín hiệu onComplete
Đáp án đúng: D

Câu 10. Vì sao nên gọi `verify(Duration.ofSeconds(2))` khi test luồng bất đồng bộ?
A. Buộc tất cả operator chạy trên scheduler hai thread
B. Đặt giới hạn chờ để test không treo vô thời hạn
C. Giới hạn tổng số tín hiệu onNext tối đa là hai
D. Tăng số lượng request ban đầu tới publisher lên hai
Đáp án đúng: B

Câu 11. Khi kiểm thử `Flux.never()`, cách kết thúc StepVerifier nào phù hợp?
A. `expectSubscription().thenCancel().verify()`
B. `expectSubscription().expectComplete().verify()`
C. `expectSubscription().expectNext(1).verify()`
D. `expectSubscription().expectError().verify()`
Đáp án đúng: A

Câu 12. Một Mono dùng `onErrorResume` trả `"fallback"` khi lỗi; StepVerifier nên kỳ vọng gì?
A. Nhận onError gốc rồi mới đến onNext fallback
B. Nhận onComplete trước khi có giá trị fallback
C. Nhận `fallback` bằng onError rồi nhận onComplete
D. Nhận `fallback` bằng onNext rồi nhận onComplete
Đáp án đúng: D

Câu 13. Trong StepVerifier, `.as("đã đọc dữ liệu")` hữu ích chủ yếu khi nào?
A. Gắn nhãn bước kỳ vọng để dễ tìm lỗi assertion
B. Chuyển lỗi của publisher thành tín hiệu onComplete
C. Đưa nhãn vào Reactor Context của publisher
D. Thay thế giá trị onNext bằng chuỗi mô tả bước
Đáp án đúng: A

Câu 14. Sau khi kịch bản kết thúc, muốn kiểm tra tín hiệu bị drop, API nào phù hợp?
A. `verifyComplete()` trả danh sách tín hiệu sau terminal
B. `verifyThenAssertThat()` trả đối tượng assertion bổ sung
C. `expectNextCount()` trả danh sách tín hiệu đã discard
D. `thenRequest()` trả bộ metadata về tín hiệu bị drop
Đáp án đúng: B

Câu 15. Khi dùng `StepVerifier.withVirtualTime`, vì sao nên tạo publisher trong lambda?
A. Để StepVerifier tự chuyển nguồn nóng thành replay
B. Để các ngoại lệ lập lịch được đổi thành onComplete
C. Để nguồn khởi tạo sau khi scheduler ảo được cài
D. Để mọi phần tử được biến thành một Mono lạnh mới
Đáp án đúng: C

Câu 16. Trong test virtual time, `thenAwait(Duration.ofHours(1))` thường có tác dụng gì?
A. Buộc publisher gửi tín hiệu hoàn tất ngay lập tức
B. Tiến đồng hồ ảo để chạy các tác vụ đã lập lịch
C. Chờ thật một giờ trên thread đang gọi kiểm thử
D. Tăng số lượng phần tử đã request thêm một đơn vị
Đáp án đúng: B

Câu 17. Vì sao thường đặt `expectSubscription()` trước `expectNoEvent(Duration)`?
A. Vì no-event chỉ chạy trước khi có subscriber đầu tiên
B. Vì onSubscribe cũng là tín hiệu được no-event kiểm tra
C. Vì expectSubscription tự cấp yêu cầu cho mọi onNext
D. Vì no-event tự chuyển completion thành tín hiệu mới
Đáp án đúng: B

Câu 18. Với `Flux.interval(Duration.ofSeconds(1)).take(2)`, cặp giá trị nào được phát?
A. Hai giá trị `0L` rồi `2L` sau các lần tick
B. Hai giá trị `2L` rồi `3L` sau các lần tick
C. Hai giá trị `0L` và `1L` theo thứ tự
D. Hai giá trị `1L` rồi `2L` sau các lần tick
Đáp án đúng: C

Câu 19. Trong StepVerifier virtual time, khác biệt chính giữa `expectNoEvent(d)` và `thenAwait(d)` là gì?
A. `expectNoEvent` phát onNext; `thenAwait` chặn mọi tín hiệu
B. `expectNoEvent` kiểm sự im lặng; `thenAwait` chỉ chờ
C. `expectNoEvent` cấp demand; `thenAwait` hủy subscription
D. `expectNoEvent` đòi onComplete; `thenAwait` đòi onError
Đáp án đúng: B

Câu 20. Muốn test `delayElements` nhanh và ít phụ thuộc thời gian máy chạy, nên làm gì?
A. Dùng Thread.sleep cố định trước mỗi bước expectNext
B. Dùng polling real-time vòng lặp tới khi nhận đủ dữ liệu
C. Dùng timestamp hệ điều hành làm kết quả kỳ vọng
D. Dùng virtual time rồi xác minh sự kiện theo đồng hồ ảo
Đáp án đúng: D

Câu 21. Lệnh `StepVerifier.create(source, 0)` khởi tạo demand thế nào?
A. Chưa request phần tử cho đến khi test yêu cầu thêm
B. Chỉ nhận một phần tử rồi tự động gửi tín hiệu cancel
C. Yêu cầu nguồn phát đúng không phần tử rồi hoàn tất
D. Yêu cầu mọi phần tử của source ngay khi subscribe
Đáp án đúng: A

Câu 22. Trong StepVerifier, `thenRequest(2)` có tác dụng nào?
A. Yêu cầu upstream phát đúng hai phần tử rồi hoàn tất
B. Tăng demand thêm hai phần tử qua Subscription
C. Buộc publisher tạo hai giá trị onNext đồng bộ
D. Đặt giới hạn hai giây cho toàn bộ kịch bản test
Đáp án đúng: B

Câu 23. Với `Flux.range(1,3)` và initial request bằng 1, bước nào cho phép kiểm hết ba phần tử?
A. Đọc `1`, đợi onComplete, rồi kiểm `2` và `3`
B. Đọc `1`, request 2, rồi kiểm tiếp `2` và `3`
C. Đọc `1`, gọi thenCancel, rồi kiểm `2` và `3`
D. Đọc `1`, gửi onError, rồi kiểm `2` và `3`
Đáp án đúng: B

Câu 24. Nếu initial request bằng 0 và không thêm demand, điều gì xảy ra với nguồn tuân thủ backpressure?
A. Chưa phát onNext dù đã nhận được subscription
B. Bắt buộc kết thúc bằng onError ngay lập tức
C. Bắt buộc gửi onComplete trước khi có demand
D. Luôn phát một onNext bất kể demand hiện tại
Đáp án đúng: A

Câu 25. Muốn mô phỏng publisher phát quá demand để thử xử lý sai chuẩn, TestPublisher hỗ trợ gì?
A. Dùng PublisherProbe ghi đè số lượng đã request
B. Đặt initial request bằng 0 trong StepVerifier
C. Dùng virtual time để publisher phát nhanh hơn
D. Bật `Violation.REQUEST_OVERFLOW` trong TestPublisher
Đáp án đúng: D

Câu 26. Trong `TestPublisher`, cặp thao tác nào cho phép tự điều khiển luồng giá trị và kết thúc?
A. `assertSubscribers(1)` để phát và `flux()` để kết thúc
B. `assertMinRequested(1)` để phát và `mono()` để kết thúc
C. `next(value)` phát onNext; `complete()` phát onComplete
D. `wasSubscribed()` để phát và `assertCancelled()` kết thúc
Đáp án đúng: C

Câu 27. Khi cần đưa TestPublisher vào pipeline như một Flux, nên lấy nguồn bằng cách nào?
A. Gọi `testPublisher.error()` để lấy Flux kiểm thử
B. Gọi `testPublisher.complete()` để lấy Flux kiểm thử
C. Gọi `testPublisher.next()` để lấy Flux kiểm thử
D. Gọi `testPublisher.flux()` để lấy Flux kiểm thử
Đáp án đúng: D

Câu 28. Trong `TestPublisher`, `assertSubscribers(1)` dùng để xác minh điều gì?
A. Có đúng một lần retry đã diễn ra trên publisher
B. Có đúng một subscriber đang đăng ký tại thời điểm kiểm
C. Có đúng một giá trị đã được phát tới mọi subscriber
D. Có đúng một lần onComplete đã gửi về cho mọi subscriber
Đáp án đúng: B

Câu 29. Khi gọi `TestPublisher.complete()`, tín hiệu nào được phát tới subscriber?
A. Tín hiệu `onError` với ngoại lệ mặc định
B. Tín hiệu `onNext` với một phần tử rỗng
C. Tín hiệu `cancel` để hủy nguồn từ phía nhận
D. Tín hiệu `onComplete` để kết thúc publisher
Đáp án đúng: D

Câu 30. Khi gọi `TestPublisher.error(ex)`, terminal signal nào được kiểm trong StepVerifier?
A. `onError` chứa ngoại lệ được cung cấp
B. `onNext` chứa đối tượng exception được gửi
C. `cancel` do TestPublisher tự yêu cầu khi lỗi
D. `onComplete` dù exception đã được truyền
Đáp án đúng: A

Câu 31. `PublisherProbe.empty()` đặc biệt hữu ích khi kiểm thử nhánh nào?
A. Nhánh dự phòng được thực thi sau mọi source có giá trị
B. Nhánh retry bị lỗi được ép thành chuỗi onNext mới
C. Nhánh timeout chuyển đồng hồ thực sang đồng hồ ảo
D. Nhánh fallback rỗng được chọn trong `switchIfEmpty`
Đáp án đúng: D

Câu 32. Nguồn `Mono.empty()` và `switchIfEmpty(probe.mono())` đã hoàn tất; xác minh nào chứng tỏ nhánh phụ được dùng?
A. `probe.assertWasNotSubscribed()` xác nhận nhánh bị bỏ qua
B. `probe.assertWasCancelled()` xác nhận nhánh bị hủy
C. `probe.assertWasSubscribed()` xác nhận nhánh được đăng ký
D. `probe.assertWasNotRequested()` xác nhận nhánh không demand
Đáp án đúng: C

Câu 33. Nguồn `Mono.just("x")` có `switchIfEmpty(probe.mono())`; điều gì đúng về probe sau khi thành công?
A. `probe.assertWasCancelled()` vì nhánh chính phát onNext
B. `probe.assertWasNotSubscribed()` do nguồn chính có dữ liệu
C. `probe.assertWasRequested()` vì Mono đã phát thành công
D. `probe.assertWasSubscribed()` vì mọi fallback đều chạy
Đáp án đúng: B

Câu 34. Nếu StepVerifier hủy subscription đến `PublisherProbe.of(Flux.never())`, assertion nào nên đạt?
A. `probe.assertWasCancelled()` xác nhận đã nhận cancel
B. `probe.assertWasNotRequested()` xác nhận không có demand
C. `probe.assertWasNotCancelled()` xác nhận chưa bị hủy
D. `probe.assertWasNotSubscribed()` xác nhận không subscribe
Đáp án đúng: A

Câu 35. `PublisherProbe.assertWasRequested()` xác minh điều gì, không suy diễn quá mức?
A. Payload nghiệp vụ đã được xử lý thành công ở database
B. Dữ liệu đã được ghi bền xuống hàng đợi trung gian
C. Probe đã nhận request demand từ subscriber
D. Subscriber đã nhận onComplete sau khi đủ dữ liệu
Đáp án đúng: C

Câu 36. API nào đọc Reactor Context tại thời điểm subscription trong một Mono?
A. Dùng `Mono.deferContextual` đọc ContextView khi subscribe
B. Dùng `Mono.fromRunnable` ghi Context vào trường static
C. Dùng `Mono.map` chụp Context tại thời điểm assembly
D. Dùng `Mono.just` đọc Context từ thread tạo publisher
Đáp án đúng: A

Câu 37. Khi gắn `contextWrite(Context.of("trace", "t1"))`, hướng lan truyền Context là gì?
A. Từ Context mới sang một biến toàn cục tĩnh
B. Từ upstream tới downstream khi onNext được phát
C. Từ thread hiện tại sang mọi thread của JVM
D. Từ downstream lên upstream khi subscribe
Đáp án đúng: D

Câu 38. Muốn cấp Context ban đầu cho StepVerifier mà không sửa publisher, dùng gì?
A. `StepVerifierOptions.create().initialRequest(ctx)`
B. `StepVerifierOptions.create().scenarioName(ctx)`
C. `StepVerifierOptions.create().checkUnderRequesting(ctx)`
D. `StepVerifierOptions.create().withInitialContext(ctx)`
Đáp án đúng: D

Câu 39. Trong StepVerifier, cặp thao tác nào giúp kiểm Context đang truy cập được?
A. Dùng `expectErrorContext().contains(...).then()`
B. Dùng `thenRequestContext().contains(...).then()`
C. Dùng `expectAccessibleContext().contains(...).then()`
D. Dùng `expectNextContext().matches(...).then()`
Đáp án đúng: C

Câu 40. Với Reactor `Context`, `ctx.put("k","v")` có tác dụng nào?
A. Phát tín hiệu onNext chứa cặp khóa và giá trị
B. Sửa trực tiếp Context cũ trên mọi subscriber
C. Trả một Context mới; Context gốc không đổi
D. Ghi giá trị vào ThreadLocal chung của ứng dụng
Đáp án đúng: C

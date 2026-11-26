Câu 1. Trong Project Reactor, `Mono<T>` biểu diễn dạng luồng nào?
A. Phát lại cùng giá trị sau từng request từ subscriber.
B. Phát 0 hoặc 1 giá trị rồi kết thúc hoặc phát lỗi.
C. Phát nhiều giá trị cho đến khi subscriber hủy.
D. Phát từ hai giá trị trở lên rồi mới complete.
Đáp án đúng: B

Câu 2. Trong Project Reactor, `Flux<T>` khác `Mono<T>` chủ yếu ở điểm nào?
A. Flux phát từ 0 tới nhiều phần tử trước khi kết thúc.
B. Flux phát đúng một phần tử và có thể trả về null.
C. Flux chỉ phát terminal signal, không phát dữ liệu.
D. Flux cần ít nhất một phần tử để hoàn thành thành công.
Đáp án đúng: A

Câu 3. Trong Reactive Streams, lệnh `Subscription.request(5)` thể hiện điều gì?
A. Publisher lập tức phát tất cả phần tử đang còn.
B. Subscriber yêu cầu bộ đệm có kích thước năm byte.
C. Publisher cấp thêm năm thread để xử lý subscription.
D. Subscriber tăng demand thêm năm phần tử từ Publisher.
Đáp án đúng: D

Câu 4. Với `Flux.fromIterable(items).map(transform)`, khi nào hàm `transform` thường được gọi?
A. Khi có subscription và downstream yêu cầu phần tử.
B. Ngay khi gọi `map`, trước lúc tạo Publisher hoàn chỉnh.
C. Khi gọi `toString()` trên Flux để kiểm tra pipeline.
D. Ngay khi Spring tạo bean mà không cần subscribe.
Đáp án đúng: A

Câu 5. Muốn trì hoãn thực thi hàm blocking `load()` cho tới khi subscribe, cách tạo Mono nào đúng?
A. Dùng `Mono.empty().thenReturn(load())` để hoãn load.
B. Dùng `Mono.just(load())` để hoãn việc gọi hàm load.
C. Dùng `Mono.fromCallable(this::load)` gọi hàm khi subscribe.
D. Dùng `Mono.justOrEmpty(load())` để hoãn tính toán.
Đáp án đúng: C

Câu 6. Với một cold Publisher gọi HTTP khi được subscribe, hai subscription độc lập thường dẫn tới gì?
A. Một request được cache và chia sẻ dù không có cấu hình.
B. Mỗi subscription sẽ kích hoạt nguồn HTTP riêng.
C. Subscription thứ hai chỉ nhận dữ liệu từ lần đầu.
D. Hai subscriber tự tạo consumer group trên cùng nguồn.
Đáp án đúng: B

Câu 7. Muốn phát sự kiện cho nhiều subscriber theo kiểu hot source, API Reactor nào phù hợp?
A. Dùng `Sinks.Many` rồi expose luồng qua `asFlux()`.
B. Dùng `Flux.defer` để cache các event đã phát trước đó.
C. Dùng `Mono.fromCallable` để broadcast event mới.
D. Dùng `Flux.fromIterable` để phát event đang cập nhật.
Đáp án đúng: A

Câu 8. Khi hàm `findAsync(id)` trả `Mono<Book>`, operator nào biến `Mono<String>` id thành `Mono<Book>`?
A. Dùng `flatMap(id -> findAsync(id))` để lấy Book.
B. Dùng `filter(id -> findAsync(id))` để chờ Mono nội.
C. Dùng `doOnNext(id -> findAsync(id))` để thay value.
D. Dùng `map(id -> findAsync(id))` để flatten publisher.
Đáp án đúng: A

Câu 9. Cần gọi nhiều nguồn bất đồng bộ theo từng ID nhưng vẫn giữ thứ tự ID, operator nào phù hợp?
A. Dùng `flatMap` với concurrency cao để giữ thứ tự phát.
B. Dùng `merge` để bảo đảm các inner hoàn thành tuần tự.
C. Dùng `concatMap` để giữ thứ tự các kết quả.
D. Dùng `switchMap` để giữ kết quả của mọi ID đầu vào.
Đáp án đúng: C

Câu 10. `Mono.zip(loadUser(), loadProfile())` thường phát giá trị khi nào?
A. Khi nguồn đầu tiên phát dữ liệu, bỏ qua nguồn còn lại.
B. Khi cả hai Mono có giá trị để ghép thành Tuple.
C. Khi cả hai Mono đều empty và trả Tuple chứa null.
D. Khi một Mono phát error nhưng Mono kia có dữ liệu.
Đáp án đúng: B

Câu 11. Muốn đánh dấu vị trí luồng Reactor khi điều tra lỗi mà không bật debug toàn cục, dùng gì?
A. Dùng `Hooks.onOperatorDebug()` chỉ trên một operator.
B. Dùng `doOnError()` để thay đổi assembly trace của nguồn.
C. Đặt `checkpoint("orders")` tại vị trí cần truy vết.
D. Dùng `log()` để gắn assembly checkpoint vào lỗi downstream.
Đáp án đúng: C

Câu 12. Khi `Mono<Book>` hoàn thành rỗng, muốn gọi nguồn Mono dự phòng, operator nào phù hợp?
A. Dùng `retryWhen(fallbackMono)` để tạo kết quả rỗng.
B. Dùng `onErrorReturn(fallbackBook)` cho Mono empty.
C. Dùng `doOnSuccess(fallbackMono)` để thay kết quả.
D. Dùng `switchIfEmpty(fallbackMono)` để đổi nguồn.
Đáp án đúng: D

Câu 13. Khi nguồn reactive trả lỗi và cần fallback `Mono` khác, nên dùng operator nào?
A. Dùng `onErrorResume` để chuyển sang fallback Mono.
B. Dùng `doOnError` để thay giá trị được phát bởi Mono.
C. Dùng `doFinally` để thay exception bằng kết quả.
D. Dùng `onErrorMap` để chuyển lỗi thành giá trị Mono.
Đáp án đúng: A

Câu 14. Muốn chuyển lỗi `SQLException` thành lỗi nghiệp vụ trong luồng reactive, dùng gì?
A. Dùng `doOnError` để thay terminal error của luồng.
B. Dùng `onErrorReturn` để ném exception mới.
C. Dùng `onErrorComplete` để giữ lại nguyên exception.
D. Dùng `onErrorMap` để đổi exception mà vẫn giữ error signal.
Đáp án đúng: D

Câu 15. Để giải phóng hoặc ghi nhận tài nguyên khi luồng complete, error hay cancel, hook nào phù hợp?
A. Dùng `doOnComplete` để xử lý cả error và cancel.
B. Dùng `doFinally` để nhận signal complete, error hoặc cancel.
C. Dùng `doOnNext` để xử lý terminal signal.
D. Dùng `doOnSubscribe` để chạy khi luồng kết thúc.
Đáp án đúng: B

Câu 16. Khi một WebClient request không phát signal trong thời hạn cho phép, operator nào áp timeout?
A. Dùng `limitRate(3)` để đặt ngưỡng ba giây.
B. Dùng `elapsed()` để tự hủy sau ba giây.
C. Dùng `timeout(Duration.ofSeconds(3))` trên Publisher.
D. Dùng `delaySubscription(Duration.ofSeconds(3))`.
Đáp án đúng: C

Câu 17. Khi dùng `retryWhen(Retry.backoff(...))` cho request ghi, vấn đề nào cần lưu ý?
A. Retry bảo đảm các lần ghi được rollback khi lỗi.
B. Retry chuyển request ghi thành transaction nguyên tử.
C. Retry chỉ chạy lại phép map, không thực thi lại nguồn ghi.
D. Retry tái subscribe; thao tác ghi cần idempotency.
Đáp án đúng: D

Câu 18. Nếu producer nhanh hơn consumer, chọn `onBackpressureBuffer(maxSize)` có hệ quả nào?
A. Chặn producer ở tầng mạng đến khi có request.
B. Bỏ qua các phần tử tới khi consumer bắt đầu đọc.
C. Đệm có giới hạn; cần xử lý overflow nếu buffer đầy.
D. Tăng demand vô hạn nhưng vẫn giữ bộ nhớ cố định.
Đáp án đúng: C

Câu 19. Muốn đưa lời gọi JDBC blocking vào chuỗi Reactor, mẫu nào phù hợp?
A. `Mono.fromCallable(this::queryJdbc).publishOn(Schedulers.boundedElastic())`.
B. `Mono.fromCallable(this::queryJdbc).subscribeOn(Schedulers.boundedElastic())`.
C. `Mono.fromCallable(this::queryJdbc).subscribeOn(Schedulers.parallel())`.
D. `Mono.just(queryJdbc()).subscribeOn(Schedulers.boundedElastic())`.
Đáp án đúng: B

Câu 20. Trong Reactor, `publishOn(scheduler)` thường tác động thế nào?
A. Ép các operator upstream chạy trên event loop gốc.
B. Chuyển xử lý downstream sang scheduler đã chọn.
C. Tạo cache kết quả trên scheduler cho subscriber khác.
D. Thay scheduler nguồn bất kể vị trí được gọi trong pipeline.
Đáp án đúng: B

Câu 21. Trong Reactor, `subscribeOn(scheduler)` chủ yếu ảnh hưởng phần nào?
A. Ảnh hưởng bước subscribe và thực thi nguồn upstream.
B. Chia một subscription thành các nhánh chạy song song.
C. Chỉ chuyển operator downstream ngay sau `subscribeOn`.
D. Chuyển tín hiệu lỗi thành kết quả theo scheduler.
Đáp án đúng: A

Câu 22. Vì sao không nên gọi `.block()` trong handler WebFlux chạy trên Netty event loop?
A. Khiến Mono lưu kết quả vào cache của ứng dụng.
B. Chặn event loop có thể gây lỗi hoặc nghẽn xử lý.
C. Biến WebClient thành HTTP client đồng bộ lâu dài.
D. Giúp WebFlux tăng số event loop để bù blocking.
Đáp án đúng: B

Câu 23. Muốn gắn correlation ID cho một reactive subscription mà không dựa vào ThreadLocal, dùng gì?
A. Gắn ID vào `Schedulers.parallel()` bằng tên thread.
B. Đặt ID trong `doOnNext` rồi suy ra Context tự có.
C. Lưu ID vào biến static của controller trong mỗi request.
D. Ghi correlation ID vào Reactor Context qua `contextWrite`.
Đáp án đúng: D

Câu 24. Trong một operator cần lấy correlation ID từ Reactor Context, API nào phù hợp?
A. Đọc ContextView bằng `Mono.deferContextual(...)`.
B. Khởi tạo `Mono.just(Context.of(...))` để đọc subscriber Context.
C. Lấy `Context.empty()` thay vì Context của subscription.
D. Đọc tên thread bằng `Mono.defer` để lấy Context hiện tại.
Đáp án đúng: A

Câu 25. Tại sao ThreadLocal không đáng tin làm nguồn duy nhất của request metadata trong luồng Reactor?
A. WebFlux dùng ThreadLocal làm cache kết quả của request.
B. ThreadLocal được truyền qua process khác khi gọi WebClient.
C. Reactor giữ một subscription trên cùng thread cố định.
D. Thread có thể đổi ở async boundary và scheduler.
Đáp án đúng: D

Câu 26. Trong Spring WebFlux, controller muốn trả danh sách sự kiện bất đồng bộ nên khai báo gì?
A. Trả `Mono<Flux<Event>>` rồi controller tự gọi `subscribe()`.
B. Trả `Flux<Event>` để WebFlux xử lý publisher reactive.
C. Trả `List<Event>` sau `collectList().block()` trên event loop.
D. Trả `ResponseEntity<Thread>` và tự push từ Netty worker.
Đáp án đúng: B

Câu 27. Với Spring `WebClient`, lệnh nào đọc JSON response thành `Mono<Book>`?
A. Dùng `exchangeToMono().block(Book.class)` trong handler.
B. Dùng `getForEntity(url, Book.class)` trên WebClient.
C. Dùng `retrieve().bodyToMono(Book.class)` trong pipeline.
D. Dùng `retrieve().bodyToObject(Book.class)` để nhận Mono.
Đáp án đúng: C

Câu 28. Trong WebFlux functional endpoint, thành phần nào liên kết request predicate với handler?
A. Dùng `HandlerFilterFunction` thay routing cho từng URI.
B. Dùng `WebFilter` đăng ký `HandlerFunction` theo URI.
C. Dùng `HandlerMapping` thay predicate khi đọc request.
D. Dùng `RouterFunction` gắn predicate với `HandlerFunction`.
Đáp án đúng: D

Câu 29. Để WebFlux trả dữ liệu theo Server-Sent Events từ `Flux<Event>`, media type nào phù hợp?
A. Chọn `MediaType.APPLICATION_OCTET_STREAM_VALUE` cho response.
B. Chọn `MediaType.APPLICATION_NDJSON_VALUE` cho response.
C. Chọn `MediaType.TEXT_EVENT_STREAM_VALUE` cho response.
D. Chọn `MediaType.APPLICATION_JSON_VALUE` cho response.
Đáp án đúng: C

Câu 30. Trong WebFlux, thành phần nào phù hợp áp logic cross-cutting cho toàn bộ HTTP exchange?
A. Dùng `WebFilter` xử lý exchange qua `WebFilterChain`.
B. Dùng `WebExceptionHandler` với request không có lỗi.
C. Dùng `HandlerInterceptor` của MVC cho WebFlux handler.
D. Dùng `HandlerFilterFunction` áp cho annotated controller.
Đáp án đúng: A

Câu 31. Muốn kiểm thử `Flux` phát hai phần tử rồi complete, công cụ Reactor nào phù hợp?
A. Dùng `WebClient` để gửi POST và đọc mọi Flux trong JVM.
B. Dùng `Hooks.onOperatorDebug()` để đếm phần tử phát ra.
C. Dùng `StepVerifier` với `expectNext` rồi `verifyComplete`.
D. Dùng `Schedulers.immediate()` để xác nhận complete signal.
Đáp án đúng: C

Câu 32. Muốn kiểm thử luồng dùng `delayElements` mà không đợi thời gian thực, cách nào phù hợp?
A. Dùng `retryWhen` để tăng tốc virtual scheduler mặc định.
B. Dùng `Thread.sleep` để scheduler chạy nhanh hơn thời gian thật.
C. Dùng `publishOn(Schedulers.parallel())` để bỏ delay của luồng.
D. Dùng `StepVerifier.withVirtualTime` và `thenAwait` phù hợp.
Đáp án đúng: D

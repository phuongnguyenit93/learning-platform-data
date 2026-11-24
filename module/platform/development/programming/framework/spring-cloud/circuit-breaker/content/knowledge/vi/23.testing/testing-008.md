# Kiểm thử fallback, timeout và tác vụ vẫn chạy sau khi hết hạn

## Mục tiêu của bài học

Khi một dịch vụ phụ thuộc chậm hoặc không khả dụng, ứng dụng thường phải trả fallback hoặc kết thúc request bằng timeout. Nhưng việc caller đã nhận timeout không chứng minh công việc ở phía dưới đã dừng. Một HTTP client có thể vẫn đang đọc socket, một tác vụ blocking có thể vẫn chiếm worker, hoặc server từ xa có thể đã thực hiện lệnh ghi trước khi kết nối bị ngắt.

Kiểm thử circuit breaker vì vậy cần quan sát nhiều lớp: kết quả trả về cho caller, trạng thái breaker, việc fallback có được gọi, số lần request thực sự được gửi và trạng thái của tác vụ nền sau khi timeout.

Sau bài học, bạn có thể:

- Kiểm thử fallback khi lời gọi thất bại và khi breaker đang OPEN.
- Phân biệt timeout của HTTP client, TimeLimiter và Reactor timeout.
- Kiểm tra thứ tự kết hợp TimeLimiter với CircuitBreaker để timeout được ghi nhận đúng.
- Dùng latch và tín hiệu đồng bộ để kiểm thử tác vụ blocking còn chạy sau khi caller hết hạn.
- Xác minh cancellation đã được gửi và xác định liệu công việc thực tế đã kết thúc hay chưa.
- Kiểm tra fallback không che giấu lỗi lập trình hoặc ghi dữ liệu dự phòng vào cache chính.
- Thiết kế bài kiểm thử ổn định, có cleanup và không phụ thuộc vào thời gian chờ tùy tiện.

## 1. Một lần timeout có nhiều kết quả cần kiểm tra

Giả sử order-service gọi inventory-service để kiểm tra tồn kho. Lời gọi vượt quá deadline 800 ms. Caller có thể nhận một trong các kết quả sau:

1. HTTP client timeout và kết thúc thao tác I/O ở phía client.
2. TimeLimiter hoàn tất CompletionStage bằng TimeoutException và yêu cầu hủy Future.
3. Reactor timeout phát tín hiệu lỗi và gửi cancellation lên publisher nguồn.
4. Caller nhận timeout nhưng tác vụ blocking bên dưới vẫn tiếp tục chạy.
5. Server từ xa đã nhận và xử lý request, nhưng response về muộn nên caller không nhận được kết quả.

Những kết quả này không tương đương nhau. Một test chỉ kiểm tra response trả về trong 800 ms chưa đủ để chứng minh tài nguyên đã được giải phóng.

| Điều cần xác minh | Câu hỏi kiểm thử |
| --- | --- |
| Kết quả caller | Caller nhận dữ liệu chính, fallback hay timeout exception? |
| Circuit breaker | Lời gọi thành công, thất bại, slow call hay bị từ chối? |
| Fallback | Fallback được gọi đúng một lần và trả trạng thái phù hợp không? |
| HTTP client | Kết nối hoặc response có bị timeout theo cấu hình không? |
| Tác vụ nền | Callable, Future hoặc request thực tế đã kết thúc chưa? |
| Tác dụng phụ | Server có thể đã ghi dữ liệu dù caller nhận timeout không? |

Một bài kiểm thử tốt cần xác định rõ đang kiểm tra hợp đồng ở tầng nào. Unit test có thể kiểm tra quyết định fallback; integration test kiểm tra HTTP timeout và circuit breaker; test có kiểm soát thread kiểm tra tác vụ còn chạy sau khi caller hết hạn.

## 2. Tách chính sách fallback để kiểm thử độc lập

Fallback thường có logic phân loại nguyên nhân: breaker đang OPEN, phụ thuộc timeout, lỗi HTTP 5xx hoặc lỗi không được phép phục hồi. Nên đưa quyết định này vào một thành phần nhỏ để có thể kiểm thử độc lập.

Ví dụ:

    public class InventoryFallbackPolicy {

        public InventoryResponse apply(String sku, Throwable error) {
            if (hasCause(error, CallNotPermittedException.class)) {
                return InventoryResponse.unavailable(sku);
            }

            if (hasCause(error, TimeoutException.class)
                    || hasCause(error, ResourceAccessException.class)) {
                return InventoryResponse.unknown(sku);
            }

            throw new InventoryLookupException(
                "Cannot determine inventory for " + sku,
                error
            );
        }

        private boolean hasCause(Throwable error, Class<?> type) {
            Throwable current = error;
            while (current != null) {
                if (type.isInstance(current)) {
                    return true;
                }
                current = current.getCause();
            }
            return false;
        }
    }

Các kiểu InventoryResponse và InventoryLookupException là thành phần do ứng dụng định nghĩa. Việc phân loại exception phải khớp HTTP client và phiên bản thư viện đang dùng. Không nên bắt mọi Throwable rồi trả về một giá trị mặc định, vì lỗi lập trình hoặc lỗi dữ liệu có thể bị che giấu.

Unit test cho policy nên bao gồm:

- CallNotPermittedException tạo trạng thái UNAVAILABLE.
- TimeoutException tạo trạng thái UNKNOWN.
- ResourceAccessException được xử lý theo chính sách lỗi kết nối.
- IllegalArgumentException hoặc lỗi validation không bị biến thành kết quả tồn kho giả.
- Exception được bọc trong CompletionException hoặc ExecutionException vẫn được phân loại qua cause chain.

Ví dụ JUnit:

    class InventoryFallbackPolicyTest {

        private final InventoryFallbackPolicy policy =
            new InventoryFallbackPolicy();

        @Test
        void breakerOpenReturnsUnavailable() {
            CircuitBreaker breaker = CircuitBreaker.ofDefaults("inventory");
            Throwable error =
                CallNotPermittedException.createCallNotPermittedException(breaker);

            InventoryResponse result = policy.apply("SKU-42", error);

            assertEquals(Availability.UNAVAILABLE, result.availability());
        }

        @Test
        void timeoutReturnsUnknown() {
            InventoryResponse result =
                policy.apply("SKU-42", new TimeoutException("deadline exceeded"));

            assertEquals(Availability.UNKNOWN, result.availability());
        }

        @Test
        void programmingErrorIsNotConvertedToFallback() {
            assertThrows(
                InventoryLookupException.class,
                () -> policy.apply("SKU-42", new IllegalArgumentException("bad input"))
            );
        }
    }

Nếu API của phiên bản Resilience4j dùng factory method hoặc constructor khác cho CallNotPermittedException, điều chỉnh phần tạo exception theo dependency thực tế. Mục tiêu của unit test là kiểm tra chính sách của ứng dụng, không khóa test vào một cách khởi tạo exception không ổn định.

## 3. Kiểm thử breaker OPEN không gọi phụ thuộc

Khi breaker OPEN, lời gọi mới cần bị từ chối trước khi Supplier thực thi. Đây là thuộc tính quan trọng để xác nhận circuit breaker bảo vệ được phụ thuộc.

Có thể kiểm tra trực tiếp với Resilience4j:

    @Test
    void openBreakerRejectsCallBeforeSupplierRuns() {
        CircuitBreaker breaker = CircuitBreaker.ofDefaults("inventory");
        breaker.transitionToOpenState();

        AtomicBoolean supplierInvoked = new AtomicBoolean(false);

        assertThrows(
            CallNotPermittedException.class,
            () -> breaker.executeSupplier(() -> {
                supplierInvoked.set(true);
                return "inventory";
            })
        );

        assertFalse(supplierInvoked.get());
        assertEquals(
            CircuitBreaker.State.OPEN,
            breaker.getState()
        );
    }

Test này kiểm tra hành vi của Resilience4j breaker. Ở integration test của ứng dụng, cần xác minh factory hoặc Feign integration đang dùng cùng instance/cấu hình breaker mà test đã mở; không nên mở một registry riêng rồi kết luận bean trong ứng dụng cũng đã OPEN.

Với gateway dùng Spring Cloud CircuitBreaker, hãy kiểm tra thêm:

- Fallback được gọi khi breaker từ chối lời gọi.
- HTTP server giả lập không nhận thêm request khi breaker đã OPEN.
- Kết quả fallback có trạng thái UNKNOWN hoặc UNAVAILABLE theo hợp đồng.
- Metric hoặc event ghi nhận số lần bị từ chối tăng.
- Khi breaker chuyển HALF_OPEN, chỉ số lời gọi thử được phép chạy theo cấu hình.

Để test không phụ thuộc thời gian và ngưỡng ngẫu nhiên, có thể cấu hình breaker test với minimumNumberOfCalls nhỏ và threshold rõ ràng, hoặc điều khiển trạng thái qua registry trong test. Không dùng cấu hình production quá dài khiến test phải chờ nhiều giây mới mở breaker.

## 4. Kiểm thử fallback sau lỗi HTTP

Dùng HTTP server giả lập như WireMock hoặc MockWebServer để điều khiển response. Với một lời gọi đọc tồn kho, tạo các tình huống:

| Response giả lập | Kết quả cần xác minh |
| --- | --- |
| HTTP 200 với JSON hợp lệ | Trả dữ liệu chính; fallback không được gọi. |
| HTTP 500 | Xử lý theo chính sách lỗi server; fallback được gọi nếu lỗi này thuộc nhóm cho phép. |
| Kết nối bị đóng | Client phát sinh lỗi kết nối; fallback hoặc exception được xử lý đúng. |
| Response chậm hơn deadline | Timeout xảy ra; fallback hoặc timeout error được trả theo hợp đồng. |
| HTTP 404 | Xử lý theo semantics của API; không tự động trả cache cũ nếu 404 có nghĩa tài nguyên không tồn tại. |

Ví dụ kiểm thử gateway có server giả lập:

    @Test
    void serverErrorUsesFallback() {
        wireMock.stubFor(
            get(urlEqualTo("/inventory/SKU-42"))
                .willReturn(aResponse().withStatus(503))
        );

        InventoryResponse result = inventoryGateway.find("SKU-42");

        assertEquals(Availability.UNKNOWN, result.availability());

        wireMock.verify(
            1,
            getRequestedFor(urlEqualTo("/inventory/SKU-42"))
        );
    }

Đoạn test giả định gateway được cấu hình để dùng fallback UNKNOWN cho lỗi 503. Nếu gateway trả CompletionStage hoặc Mono, hãy chờ kết quả bằng API tương ứng trong test thay vì gọi block tùy tiện trên event loop. Trong test reactive, dùng StepVerifier.

Cần kiểm tra số request ở server giả lập. Fallback thành công không chứng minh chỉ có một request đã được gửi; retry có thể đã tạo nhiều attempt. Nếu đang kiểm tra circuit breaker, hãy ghi nhận cả số lần gọi logic và số HTTP attempt.

## 5. Phân biệt timeout của HTTP client, TimeLimiter và Reactor

Các timeout khác nhau kiểm soát những phạm vi khác nhau:

| Timeout | Phạm vi | Điều cần kiểm thử |
| --- | --- | --- |
| Connect timeout | Thiết lập kết nối đến server. | Kết nối không hoàn thành trong giới hạn thì client báo lỗi. |
| Response/read timeout | Chờ response hoặc dữ liệu theo khả năng HTTP client. | Client dừng chờ theo cấu hình; kiểm tra socket/request có được giải phóng không. |
| Resilience4j TimeLimiter | CompletionStage/Future được bọc. | Caller nhận timeout; kiểm tra cancelRunningFuture và trạng thái tác vụ thật. |
| Reactor timeout | Publisher không phát tín hiệu trong thời gian quy định. | Publisher phát TimeoutException và gửi cancellation upstream. |
| CircuitBreaker slowCallDurationThreshold | Phân loại lời gọi chậm trong thống kê. | Breaker ghi nhận slow call; không mặc định hủy lời gọi. |

Không dùng một test duy nhất để chứng minh tất cả timeout hoạt động. Ví dụ, Mono.timeout có thể làm publisher phát lỗi trong khi HTTP connector có cấu hình timeout riêng. Ngược lại, TimeLimiter có thể kết thúc CompletionStage phía caller nhưng công việc blocking trong executor vẫn tiếp tục.

Với mỗi timeout, ghi rõ thời gian bắt đầu, thời điểm caller nhận kết quả và thời điểm tác vụ thực tế hoàn tất. Ba mốc này giúp phát hiện công việc bị bỏ lại sau deadline.

## 6. Kiểm thử TimeLimiter và tác vụ blocking vẫn chạy

Một trường hợp quan trọng là TimeLimiter hết hạn nhưng công việc blocking không dừng. CompletableFuture.cancel(true) không bảo đảm interrupt được tác vụ đang chạy; nhiều API blocking cũng không phản ứng với interrupt hoặc chỉ dừng khi socket timeout.

Có thể kiểm tra bằng CountDownLatch thay vì Thread.sleep. Latch giúp test điều khiển chính xác thời điểm tác vụ bắt đầu và khi nào được phép kết thúc.

Ví dụ JUnit với Resilience4j TimeLimiter:

    @Test
    void callerTimesOutWhileBlockingTaskIsStillRunning() throws Exception {
        ExecutorService ioExecutor = Executors.newSingleThreadExecutor();
        ScheduledExecutorService timeoutScheduler =
            Executors.newSingleThreadScheduledExecutor();

        CountDownLatch taskStarted = new CountDownLatch(1);
        CountDownLatch allowTaskToFinish = new CountDownLatch(1);
        CountDownLatch taskFinished = new CountDownLatch(1);

        TimeLimiter limiter = TimeLimiter.of(
            TimeLimiterConfig.custom()
                .timeoutDuration(Duration.ofMillis(100))
                .cancelRunningFuture(true)
                .build()
        );

        try {
            Supplier<CompletionStage<String>> source = () ->
                CompletableFuture.supplyAsync(() -> {
                    taskStarted.countDown();
                    try {
                        allowTaskToFinish.await();
                        return "completed";
                    } catch (InterruptedException error) {
                        Thread.currentThread().interrupt();
                        throw new CompletionException(error);
                    } finally {
                        taskFinished.countDown();
                    }
                }, ioExecutor);

            CompletionStage<String> result =
                limiter.executeCompletionStage(timeoutScheduler, source);

            assertTrue(taskStarted.await(1, TimeUnit.SECONDS));

            ExecutionException timeout = assertThrows(
                ExecutionException.class,
                () -> result.toCompletableFuture().get(1, TimeUnit.SECONDS)
            );

            assertTrue(timeout.getCause() instanceof TimeoutException);
            assertEquals(1L, taskFinished.getCount());

        } finally {
            allowTaskToFinish.countDown();
            assertTrue(taskFinished.await(1, TimeUnit.SECONDS));
            ioExecutor.shutdownNow();
            timeoutScheduler.shutdownNow();
        }
    }

Trong test này:

- taskStarted xác nhận công việc đã thực sự chạy trước khi kiểm tra timeout.
- TimeLimiter hoàn tất stage phía caller bằng timeout sau 100 ms.
- allowTaskToFinish vẫn chưa được mở, nên tác vụ đang chờ và chưa kết thúc.
- Test xác nhận taskFinished chưa được đếm xuống tại thời điểm caller đã timeout.
- finally giải phóng latch để không để lại worker bị treo.

Ví dụ giả định executor và scheduler được tạo cho test rồi đóng trong finally. Trong ứng dụng Spring, hãy quản lý executor như bean dùng chung với giới hạn thread và queue phù hợp. Không tạo executor mới cho mỗi request.

Kết quả này minh họa một điểm quan trọng: TimeLimiter có thể kết thúc kết quả chờ của caller, nhưng việc hủy Future không đồng nghĩa công việc blocking đã dừng. Một số Future hoặc thư viện có khả năng hủy tốt hơn; hãy kiểm tra hành vi cụ thể của client đang dùng.

## 7. Kiểm tra tác vụ có thật sự dừng sau cancellation

Khi test timeout, nên ghi nhận ít nhất ba tín hiệu:

1. Caller đã nhận timeout.
2. Cancellation đã được yêu cầu hoặc phát ra.
3. Công việc ở tầng thực thi đã kết thúc và giải phóng tài nguyên.

Với Reactor, có thể ghi nhận tín hiệu cancel bằng doFinally:

    Mono<String> task = Mono.fromCallable(() -> blockingClient.call())
        .subscribeOn(Schedulers.boundedElastic())
        .doFinally(signal -> {
            if (signal == SignalType.CANCEL) {
                cancellationCounter.increment();
            }
        })
        .timeout(Duration.ofMillis(200));

doFinally với SignalType.CANCEL cho biết publisher nhận tín hiệu hủy. Nó không chứng minh phương thức blockingClient.call đã ngừng thực thi. Để xác minh điều đó, cần một tín hiệu riêng ở cuối tác vụ, chẳng hạn CountDownLatch, AtomicBoolean hoặc metric số công việc đang chạy.

Nếu thư viện blocking hỗ trợ interrupt, test có thể ghi nhận InterruptedException. Nhưng đừng yêu cầu mọi thư viện phải phản ứng với interrupt. Một số API chỉ kết thúc khi socket timeout, transaction hoàn tất hoặc thao tác bên dưới trả về.

Khi công việc vẫn chạy sau timeout, hãy kiểm tra:

- Worker thread còn bị chiếm bao lâu?
- HTTP connection có được giải phóng hay vẫn nằm trong pool?
- Bulkhead permit được giữ đến khi nào?
- Tác vụ có tiếp tục ghi database hoặc tạo side effect không?
- Có thể đặt timeout ở chính client hoặc API thấp hơn để dừng công việc thật không?
- Có cần giới hạn concurrency để các tác vụ hết hạn không tích tụ?

Không chỉ đếm số timeout ở caller. Hãy quan sát số tác vụ đang chạy thực tế sau deadline.

## 8. Kiểm thử Reactor timeout với StepVerifier

Với pipeline reactive, StepVerifier giúp kiểm tra timeout mà không cần chờ thời gian thực dài. Dùng virtual time cho publisher dựa trên scheduler thời gian của Reactor:

    @Test
    void reactorTimeoutEmitsTimeoutException() {
        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofSeconds(5))
                    .thenReturn("inventory")
                    .timeout(Duration.ofSeconds(1))
            )
            .thenAwait(Duration.ofSeconds(1))
            .expectError(TimeoutException.class)
            .verify();
    }

Virtual time giúp test hoàn tất nhanh và ổn định. Publisher Mono.delay dùng scheduler có thể được điều khiển bởi StepVerifier. Với một HTTP client thật, không nên mặc định virtual time điều khiển socket hoặc thời gian phản hồi mạng. Hãy dùng server giả lập với delay có kiểm soát và timeout connector thực tế cho integration test.

Có thể kiểm tra fallback ở sau timeout:

    @Test
    void timeoutUsesFallbackAfterProtectedPublisher() {
        StepVerifier.withVirtualTime(() ->
                Mono.<InventoryResponse>never()
                    .timeout(Duration.ofSeconds(1))
                    .onErrorResume(
                        TimeoutException.class,
                        error -> Mono.just(InventoryResponse.unknown("SKU-42"))
                    )
            )
            .thenAwait(Duration.ofSeconds(1))
            .assertNext(response ->
                assertEquals(Availability.UNKNOWN, response.availability())
            )
            .verifyComplete();
    }

Trong ứng dụng thật, CircuitBreakerOperator cần nằm trước fallback để ghi nhận timeout. Ví dụ thứ tự:

    Mono<InventoryResponse> protectedCall = primary
        .timeout(Duration.ofMillis(800))
        .transformDeferred(CircuitBreakerOperator.of(inventoryBreaker))
        .onErrorResume(
            TimeoutException.class,
            error -> Mono.just(InventoryResponse.unknown(sku))
        );

Nếu fallback được đặt trước breaker và chuyển lỗi thành giá trị thành công, breaker có thể không thấy timeout. Hãy có test kiểm tra failure count hoặc event tương ứng sau khi timeout.

## 9. Kiểm thử thứ tự TimeLimiter và CircuitBreaker

Khi dùng CompletionStage, hãy bọc nguồn bằng TimeLimiter trước, rồi để CircuitBreaker quan sát CompletionStage đã được giới hạn thời gian:

    Supplier<CompletionStage<InventoryResponse>> source = () ->
        CompletableFuture.supplyAsync(
            () -> blockingClient.find(sku),
            ioExecutor
        );

    Supplier<CompletionStage<InventoryResponse>> timedSource = () ->
        timeLimiter.executeCompletionStage(timeoutScheduler, source);

    Supplier<CompletionStage<InventoryResponse>> protectedCall =
        CircuitBreaker.decorateCompletionStage(circuitBreaker, timedSource);

    return protectedCall.get();

Với composition này, timeout do TimeLimiter phát ra là kết quả lỗi mà CircuitBreaker quan sát. Test cần xác nhận:

- Caller nhận TimeoutException trong thời gian dự kiến.
- Failure metric của breaker tăng theo cấu hình exception.
- Sau đủ số mẫu, breaker có thể chuyển OPEN.
- Khi breaker OPEN, source không khởi chạy thêm tác vụ.
- Fallback được gọi sau khi kết quả được xác định là timeout hoặc call not permitted.

Nếu TimeLimiter được đặt ngoài breaker, caller vẫn có thể nhận timeout nhưng breaker có thể không ghi nhận timeout theo cách mong muốn. Hãy xác định rõ wrapper nào quan sát kết quả nào và kiểm thử bằng event/metric thay vì chỉ kiểm tra response.

Cấu hình Resilience4j minh họa:

    resilience4j:
      circuitbreaker:
        instances:
          inventory:
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 4
            minimumNumberOfCalls: 2
            failureRateThreshold: 50
            waitDurationInOpenState: 2s
      timelimiter:
        instances:
          inventory:
            timeoutDuration: 300ms
            cancelRunningFuture: true

Đây là cấu hình dành cho test, với cửa sổ nhỏ để có thể mở breaker nhanh. Không sao chép nguyên các giá trị này sang production nếu chưa đánh giá lưu lượng, SLO và đặc điểm phụ thuộc.

## 10. Kiểm thử fallback không che giấu lỗi và không làm sai cache

Fallback chỉ nên xử lý những lỗi mà nghiệp vụ cho phép phục hồi. Cần có test khẳng định lỗi lập trình và dữ liệu không hợp lệ vẫn được truyền lên.

Nếu dùng cache làm fallback, hãy kiểm tra riêng:

- Cache hit bình thường không gọi dịch vụ chính nếu chính sách cho phép.
- Khi dịch vụ chính timeout, chỉ dùng cache còn trong stale window.
- Khi cache hết hạn, lỗi hoặc trạng thái unavailable được trả theo hợp đồng.
- Kết quả fallback không ghi đè cache authoritative.
- Khi dịch vụ phục hồi, dữ liệu chính mới được ghi cache.
- Cache key không làm lộ dữ liệu giữa tenant hoặc người dùng.

Ví dụ test kiểm tra không ghi fallback vào cache chính:

    @Test
    void fallbackValueIsNotStoredAsAuthoritativeData() {
        InventoryResponse fallback =
            InventoryResponse.unknown("SKU-42");

        InventoryResponse result = gateway.applyFallback(
            "SKU-42",
            new TimeoutException("deadline exceeded")
        );

        assertEquals(fallback.availability(), result.availability());
        verify(productCache, never()).putAuthoritative(any());
    }

Ví dụ giả định việc ghi cache authoritative nằm ở nhánh thành công của nguồn chính, còn fallback là nhánh riêng. Nếu code hiện tại đặt cache write sau khi đã hợp nhất primary và fallback, test này sẽ giúp phát hiện dữ liệu dự phòng bị lưu nhầm.

## 11. Kiểm thử timeout với thao tác ghi và idempotency

Timeout không cho biết server đã thực hiện thao tác ghi hay chưa. Ví dụ order-service gửi lệnh giữ hàng. Inventory-service có thể đã cập nhật số lượng, nhưng response bị mất hoặc về sau deadline. Caller nhận timeout và không biết kết quả cuối cùng.

Không nên tự động gửi lại lệnh ghi chỉ vì caller nhận timeout. Test cần mô phỏng trường hợp:

1. Server nhận request và ghi nhận thao tác.
2. Server trì hoãn response vượt deadline.
3. Caller nhận timeout.
4. Client thử lại cùng idempotency key.
5. Server trả lại kết quả của thao tác trước hoặc không thực hiện tác dụng phụ lần hai.

Các điều cần xác minh:

- Cùng một idempotency key không tạo hai lần giữ hàng.
- Trạng thái thao tác có thể được tra cứu sau timeout.
- Fallback không khẳng định thao tác thất bại nếu kết quả thực tế chưa xác định.
- Retry chỉ nằm trong giới hạn và semantics đã định nghĩa.
- Log/trace có cùng operation ID để nối request đầu và lần thử lại.

Đây là bài kiểm thử quan trọng với thanh toán, tạo đơn, giữ hàng, gửi email hoặc các thao tác có side effect.

## 12. Làm test ổn định và dọn dẹp tài nguyên

Test timeout dễ flaky nếu dùng Thread.sleep và giả định scheduler luôn chạy đúng một thời điểm. Hãy ưu tiên:

- CountDownLatch hoặc Phaser để điều khiển điểm bắt đầu và kết thúc của tác vụ.
- StepVerifier.withVirtualTime cho operator thời gian của Reactor.
- HTTP server giả lập để điều khiển response delay và số request.
- Timeout chờ trong test để tránh test treo vô hạn.
- finally để mở latch, đóng server và shutdown executor.
- Clock hoặc scheduler có thể điều khiển nếu code ứng dụng cho phép inject.
- Cấu hình breaker test riêng, tránh phụ thuộc trạng thái từ test khác.

Không dùng chung CircuitBreakerRegistry mutable giữa các test nếu không reset trạng thái. Một test mở breaker có thể làm test kế tiếp nhận CallNotPermittedException dù test đó mong đợi gọi server. Tạo instance riêng cho mỗi test hoặc reset rõ ràng trong teardown.

Khi test song song, không dùng cùng một cổng server, cùng breaker name trong registry dùng chung hoặc cùng cache key nếu các test có thể ảnh hưởng lẫn nhau. Hãy tạo fixture cô lập và dọn dẹp ngay cả khi assertion thất bại.

## 13. Ma trận kiểm thử đề xuất

Có thể dùng ma trận sau làm checklist cho gateway inventory:

| Trường hợp | Caller nhận gì? | Supplier/server có chạy? | Breaker cần ghi nhận |
| --- | --- | --- | --- |
| Thành công nhanh | Dữ liệu chính | Có | Success |
| HTTP 503 | Fallback hoặc lỗi theo policy | Có | Error nếu exception được record |
| Breaker OPEN | Fallback unavailable | Không | Call not permitted |
| HTTP client timeout | Fallback unknown hoặc timeout error | Request đã được gửi; client kết thúc theo khả năng | Error/timeout theo policy |
| TimeLimiter hết hạn, tác vụ không interrupt | Caller timeout | Tác vụ có thể vẫn chạy | Timeout error |
| Reactor timeout | Timeout hoặc fallback | Publisher nhận cancellation; nguồn blocking có thể vẫn tiếp tục | Error nếu breaker bao quanh timeout |
| Bulkhead hết permit | Busy/fallback | Tác vụ mới không được chạy | Bulkhead rejection; không nhầm với breaker OPEN |
| Cache stale được dùng | Dữ liệu có metadata STALE | Có thể đã gọi nguồn chính và thất bại | Breaker ghi nhận lỗi trước fallback |
| Server ghi dữ liệu rồi response timeout | Kết quả không xác định hoặc trạng thái tra cứu | Side effect có thể đã xảy ra | Timeout/error; retry cần idempotency |

Ma trận giúp người viết test không dừng ở response cuối. Hãy xác minh cả số lần gọi, trạng thái breaker và công việc còn tồn tại sau timeout.

## 14. Bài thực hành tổng hợp

Xây dựng InventoryGateway có lời gọi HTTP đến inventory-service, CircuitBreaker, TimeLimiter và fallback. Thực hiện:

1. Viết unit test cho InventoryFallbackPolicy với CallNotPermittedException, TimeoutException và lỗi lập trình.
2. Dùng breaker test riêng, chuyển breaker sang OPEN và xác nhận Supplier không được thực thi.
3. Dùng HTTP server giả lập để trả 200, 503, connection close và response delay.
4. Cấu hình HTTP client timeout, sau đó xác nhận caller nhận đúng loại lỗi.
5. Tạo CompletionStage chạy tác vụ blocking bằng executor riêng và bọc bằng TimeLimiter.
6. Dùng CountDownLatch xác nhận caller đã timeout trong khi taskFinished vẫn chưa xảy ra.
7. Giải phóng latch trong finally và xác nhận worker kết thúc để test không rò rỉ thread.
8. Bọc timed CompletionStage bằng CircuitBreaker và kiểm tra failure metric tăng.
9. Làm đủ số timeout để breaker OPEN; xác nhận request tiếp theo không khởi chạy tác vụ mới.
10. Với pipeline WebClient, dùng StepVerifier kiểm tra Mono.timeout và fallback sau CircuitBreakerOperator.
11. Thử thao tác ghi có idempotency key và mô phỏng server hoàn tất trước khi response timeout.
12. Kiểm tra log, metric, số request và số tác vụ còn chạy sau deadline.

Khi hoàn thành, bạn cần trả lời được caller đã nhận timeout chưa, cancellation đã được gửi chưa, tác vụ thực tế đã dừng chưa và breaker có ghi nhận timeout không. Đây là bốn câu hỏi khác nhau. Kiểm thử đầy đủ giúp phát hiện tình trạng request đã kết thúc nhưng worker, connection hoặc side effect vẫn tiếp tục tồn tại phía sau deadline.

## Tài liệu tham khảo

- Resilience4j TimeLimiter: https://resilience4j.readme.io/docs/timeout
- Resilience4j CircuitBreaker: https://resilience4j.readme.io/docs/circuitbreaker
- Reactor Reference — Handling Errors and Cancellation: https://projectreactor.io/docs/core/release/reference/
- Spring Cloud CircuitBreaker — Resilience4J: https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html


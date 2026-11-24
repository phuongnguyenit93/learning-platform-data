# Hủy đăng ký theo thời gian chờ, yêu cầu HTTP hoặc vòng đời ứng dụng

Một subscription reactive có thể kéo dài lâu hơn thời gian mà bên tiêu thụ còn cần dữ liệu. Người dùng rời trang, kết nối HTTP bị đóng, một thao tác vượt quá thời hạn hoặc ứng dụng bắt đầu dừng đều có thể khiến việc tiếp tục phát dữ liệu trở nên lãng phí. Reactive Streams cung cấp cơ chế hủy thông qua Subscription.cancel(); Reactor mở rộng cách quản lý này bằng Disposable, các toán tử timeout và những hook vòng đời.

Hủy subscription là một phần của thiết kế luồng dữ liệu. Nó giúp ngừng công việc không còn cần thiết, giải phóng tài nguyên và tránh tiếp tục gọi dịch vụ downstream. Để dùng đúng, cần phân biệt cancellation với hoàn tất bình thường và lỗi, hiểu timeout tác động lên upstream ra sao, đồng thời gắn việc hủy với vòng đời của request hoặc ứng dụng.

## 1. Cancellation trong Reactive Streams

Khi subscriber nhận onSubscribe(subscription), nó có thể gọi request(n) để yêu cầu dữ liệu hoặc cancel() để yêu cầu dừng subscription. request điều khiển số phần tử được phép phát; cancel biểu thị rằng subscriber không muốn nhận thêm dữ liệu từ subscription đó.

Cancellation là tín hiệu điều khiển đi từ subscriber về publisher. Nó không phải một tín hiệu terminal gửi từ publisher đến subscriber. Vì vậy, sau khi subscriber gọi cancel():

- Publisher phải tôn trọng yêu cầu và cuối cùng ngừng phát tín hiệu đến subscriber đó.
- Publisher không cần gửi onComplete để xác nhận việc hủy.
- Publisher không gửi onError chỉ vì subscriber đã hủy.
- Subscriber không nhận một callback onCancelled trong hợp đồng Reactive Streams.
- Tài nguyên và tác vụ liên quan cần được dọn dẹp theo cơ chế của publisher hoặc ứng dụng.

Một subscription chỉ có thể kết thúc một lần bằng onComplete hoặc onError nếu kết thúc theo luồng tín hiệu. Cancellation là một con đường dừng khác: subscriber chủ động yêu cầu publisher ngừng. Việc gọi cancel nhiều lần phải an toàn; các lần gọi lặp không được làm subscription hoạt động trở lại.

Cancellation có tính bất đồng bộ. Lúc cancel() được gọi, một tín hiệu hoặc thao tác có thể đang chạy. Vì vậy, không nên giả định mọi công việc dừng tức thì tại đúng dòng lệnh đó. Publisher cần ngừng phát tiếp sau khi xử lý yêu cầu hủy, còn ứng dụng cần thiết kế tác vụ và phần dọn dẹp để chịu được tình huống đang thực thi dở.

## 2. Phân biệt hủy, hoàn tất và lỗi

Ba kiểu kết thúc thường gặp có ý nghĩa khác nhau:

| Trường hợp | Nguyên nhân | Điều subscriber downstream quan sát |
|---|---|---|
| Hoàn tất | Publisher phát xong dữ liệu bình thường | onComplete |
| Lỗi | Publisher không thể tiếp tục luồng bình thường | onError(error) |
| Hủy | Subscriber không còn muốn nhận dữ liệu | Không có tín hiệu terminal mới chỉ để xác nhận cancel |

Ví dụ, một Flux đọc hết danh sách sẽ gọi onComplete. Một Flux gặp lỗi khi truy vấn dữ liệu sẽ gọi onError. Nếu người dùng đóng màn hình và subscriber gọi cancel(), publisher được yêu cầu dừng; không có onComplete giả tạo chỉ để biểu thị người dùng đã rời đi.

Trong Reactor, có thể quan sát sự khác biệt bằng doFinally:

    import reactor.core.publisher.Flux;
    import reactor.core.publisher.SignalType;

    Flux<Integer> source = Flux.range(1, 100)
        .doFinally(signal -> {
            if (signal == SignalType.CANCEL) {
                log.info("Subscription was cancelled");
            } else if (signal == SignalType.ON_COMPLETE) {
                log.info("Subscription completed");
            } else if (signal == SignalType.ON_ERROR) {
                log.warn("Subscription failed");
            }
        });

doFinally được gọi khi pipeline kết thúc bằng complete, error hoặc cancel. Nó phù hợp để ghi nhận metric, log và thực hiện hành động đồng bộ ngắn. Nếu cần giải phóng tài nguyên bất đồng bộ hoặc bảo đảm đóng tài nguyên theo từng nhánh kết thúc, hãy dùng cơ chế quản lý tài nguyên chuyên dụng như usingWhen.

## 3. Hủy theo thời gian chờ

Một request có thể mất quá lâu vì dịch vụ phụ thuộc bị chậm, kết nối mạng không ổn định hoặc nguồn dữ liệu ngừng phát. Nếu consumer tiếp tục chờ vô hạn, request có thể giữ tài nguyên, chiếm slot trong connection pool và làm tăng độ trễ của các công việc khác.

Trong Reactor, timeout đặt giới hạn thời gian chờ tín hiệu. Nếu thời hạn hết trước khi nguồn phát tín hiệu tiếp theo, toán tử timeout hủy upstream và phát lỗi TimeoutException xuống downstream. Với Mono, điều này thường có nghĩa là nguồn không phát kết quả trong khoảng thời gian quy định. Với Flux, timeout có thể áp dụng cho thời gian chờ tín hiệu đầu tiên và khoảng thời gian giữa các tín hiệu tiếp theo.

Ví dụ đặt thời hạn cho một lời gọi WebClient:

    import java.time.Duration;
    import java.util.concurrent.TimeoutException;
    import reactor.core.publisher.Mono;

    Mono<Profile> profile =
        webClient.get()
            .uri("/profiles/{id}", profileId)
            .retrieve()
            .bodyToMono(Profile.class)
            .timeout(Duration.ofSeconds(2))
            .onErrorResume(
                TimeoutException.class,
                error -> loadCachedProfile(profileId)
            );

Nếu dịch vụ không trả kết quả trong hai giây, timeout yêu cầu hủy nguồn upstream. Downstream nhận lỗi timeout; onErrorResume sau đó chuyển lỗi thành publisher lấy dữ liệu cache. Subscriber cuối có thể nhận profile từ cache và hoàn tất bình thường. Việc fallback không làm cho request ban đầu tiếp tục chạy.

Có thể cung cấp fallback trực tiếp cho timeout:

    Mono<Profile> profile =
        loadProfile(profileId)
            .timeout(
                Duration.ofSeconds(2),
                loadCachedProfile(profileId)
            );

Hai cách trên thể hiện cùng ý định: nếu nguồn chính không đáp ứng thời hạn, chuyển sang kết quả dự phòng. Chọn fallback theo ngữ nghĩa nghiệp vụ; không nên biến mọi timeout thành dữ liệu giả nếu điều đó có thể làm sai trạng thái nghiệp vụ.

### 3.1. timeout khác với take(Duration)

Không phải mọi giới hạn thời gian đều phải trở thành lỗi. Reactor có toán tử take(Duration) để chỉ giữ dữ liệu trong một khoảng thời gian rồi kết thúc luồng bằng onComplete. Khi hết khoảng thời gian, toán tử dừng upstream vì downstream đã nhận đủ phần dữ liệu trong cửa sổ thời gian.

Ví dụ:

    Flux<Event> recentEvents =
        eventSource.events()
            .take(Duration.ofSeconds(10));

Khi hết mười giây, recentEvents hoàn tất bình thường và nguồn upstream được yêu cầu dừng. Ngược lại, timeout(Duration) báo lỗi khi thời hạn chờ một tín hiệu bị vượt quá. Hãy chọn theo ý nghĩa:

- Dùng timeout khi kết quả phải đến trong một thời hạn, nếu không đó là tình huống lỗi hoặc cần fallback.
- Dùng take(Duration) khi chỉ muốn thu thập dữ liệu trong một cửa sổ thời gian rồi hoàn tất bình thường.

### 3.2. Timeout của pipeline và timeout ở tầng HTTP

Toán tử timeout áp dụng lên tín hiệu của publisher. HTTP client hoặc connector còn có thể có các giới hạn riêng cho thời gian kết nối, thời gian chờ phản hồi hoặc thời gian đọc dữ liệu. Các giới hạn này bảo vệ những giai đoạn mạng khác nhau.

Một timeout ở tầng mạng có thể làm request HTTP thất bại; một timeout ở tầng reactive có thể hủy publisher đang chờ kết quả. Trong ứng dụng thực tế, hãy thiết kế các giới hạn nhất quán với deadline nghiệp vụ và tránh đặt một timeout tổng thể dài hơn nhiều so với thời hạn mà caller chấp nhận.

## 4. Hủy khi request HTTP không còn được quan tâm

Trong ứng dụng Spring WebFlux, controller có thể trả về Mono hoặc Flux để framework đăng ký và ghi kết quả vào HTTP response. Nếu client đóng kết nối hoặc ngừng nhận response, server có thể nhận biết việc truyền dữ liệu bị hủy và cancellation được truyền vào pipeline reactive đang phục vụ request đó.

Ví dụ một endpoint trả về luồng sự kiện:

    import reactor.core.publisher.Flux;
    import reactor.core.publisher.SignalType;
    import org.springframework.web.bind.annotation.GetMapping;
    import org.springframework.web.bind.annotation.RestController;

    @RestController
    class EventController {
        private final EventService eventService;

        EventController(EventService eventService) {
            this.eventService = eventService;
        }

        @GetMapping(value = "/events", produces = "text/event-stream")
        Flux<Event> events() {
            return eventService.streamEvents()
                .doFinally(signal -> {
                    if (signal == SignalType.CANCEL) {
                        log.info("HTTP event stream was cancelled");
                    }
                });
        }
    }

Controller trả publisher trực tiếp cho framework. Khi client ngắt kết nối trong lúc response đang được ghi, framework và connector có thể hủy subscription của response stream; cancellation đi ngược qua các toán tử đến nguồn nếu nguồn hỗ trợ. Hook doFinally giúp quan sát trường hợp đó để ghi log hoặc cập nhật số liệu.

Với lời gọi HTTP đi ra ngoài qua WebClient, cancellation cũng quan trọng. Nếu request phía gọi bị hủy hoặc timeout, pipeline WebClient không còn cần kết quả và connector có thể hủy thao tác mạng tương ứng. Điều này tránh tiếp tục tiêu tốn kết nối và xử lý response không còn ai sử dụng.

Không nên gọi subscribe() thủ công bên trong controller chỉ để khởi chạy công việc rồi trả về một kết quả khác. Khi tự tách một subscription ra khỏi publisher mà framework quản lý, cancellation của HTTP request không còn tự động kiểm soát subscription độc lập đó. Nếu công việc phải tiếp tục sau khi client ngắt kết nối, hãy đưa nó vào một cơ chế xử lý nền có vòng đời và lưu trữ rõ ràng, chẳng hạn hàng đợi hoặc outbox.

### 4.1. Cancellation không phải bảo đảm công việc nghiệp vụ bị đảo ngược

Client ngắt kết nối chỉ có nghĩa client không còn nhận response. Nó không tự động hoàn tác giao dịch đã commit, hủy thông điệp đã gửi đến broker hoặc đảo ngược lời gọi dịch vụ bên ngoài đã hoàn thành.

Ví dụ, một request tạo đơn hàng có thể đã ghi đơn vào cơ sở dữ liệu trước khi kết nối bị đóng. Hủy phần response không đồng nghĩa đơn hàng bị xóa. Nếu nghiệp vụ cần tiếp tục hoàn thành sau khi client rời đi, hãy ghi nhận công việc bền vững và cung cấp cơ chế tra cứu trạng thái bằng request khác.

Ngược lại, nếu công việc chỉ phục vụ response hiện tại, như truy vấn gợi ý hoặc tạo luồng sự kiện tạm thời, cancellation nên được truyền đến nguồn để dừng truy vấn hoặc ngừng đăng ký lắng nghe khi có thể.

## 5. Hủy theo vòng đời ứng dụng

Một subscription nền có thể sống lâu hơn một HTTP request. Ví dụ, một component đăng ký nhận sự kiện từ message broker, theo dõi thay đổi cấu hình hoặc nghe một nguồn dữ liệu liên tục. Khi ứng dụng dừng, các subscription này cần được dispose để ngừng nhận dữ liệu và giải phóng tài nguyên.

Reactor cung cấp Disposable từ các overload subscribe. Gọi dispose() trên Disposable sẽ hủy subscription tương ứng. Có thể lưu nhiều subscription trong một Disposable.Composite để quản lý cùng vòng đời:

    import jakarta.annotation.PreDestroy;
    import reactor.core.Disposable;
    import reactor.core.Disposables;

    class EventMonitor {
        private final Disposable.Composite subscriptions =
            Disposables.composite();

        void start() {
            Disposable subscription =
                eventSource.events()
                    .subscribe(
                        this::handleEvent,
                        error -> log.error("Event stream failed", error)
                    );

            subscriptions.add(subscription);
        }

        @PreDestroy
        void stop() {
            subscriptions.dispose();
        }
    }

Khi component bị hủy trong quá trình shutdown, phương thức stop dispose composite và hủy các subscription đã đăng ký. Composite cũng cho phép quản lý tập hợp subscription tại một nơi thay vì để chúng tồn tại ngoài tầm kiểm soát.

Trong ứng dụng Spring, hãy gắn việc khởi tạo và dừng subscription vào lifecycle của bean, chẳng hạn SmartLifecycle hoặc @PostConstruct/@PreDestroy tùy yêu cầu. Nếu dùng SmartLifecycle, cần phối hợp thứ tự dừng giữa consumer, broker connection và các tài nguyên mà consumer phụ thuộc.

### 5.1. Hủy khi component không còn hoạt động

Một component có thể bị vô hiệu hóa trong lúc ứng dụng vẫn chạy, chẳng hạn người quản trị tắt một tính năng hoặc một tenant bị ngừng xử lý. Khi đó, giữ subscription hoạt động sẽ tiếp tục nhận dữ liệu dù không còn nơi sử dụng.

Hãy lưu Disposable tại component sở hữu subscription và gọi dispose khi trạng thái chuyển sang inactive. Nếu cần bật lại, tạo subscription mới theo lifecycle mới. Không nên tái sử dụng một subscription đã bị dispose như thể nó có thể tiếp tục từ vị trí cũ.

Khi có nhiều nguồn độc lập, có thể lưu từng Disposable để hủy riêng hoặc dùng Composite để hủy cả nhóm. Chủ sở hữu subscription cần rõ ràng: component tạo subscription chịu trách nhiệm dừng nó, trừ khi quyền sở hữu đã được chuyển giao rõ ràng.

## 6. Dọn dẹp tài nguyên khi subscription bị hủy

Một pipeline có thể giữ file handle, connection, cursor, listener hoặc tài nguyên bên ngoài. Khi cancellation xảy ra, tài nguyên cần được giải phóng để tránh rò rỉ.

### 6.1. doOnCancel và doFinally

doOnCancel chạy hành động khi nhận yêu cầu hủy. Nó phù hợp cho một hành động ngắn như ghi nhận metric hoặc phát tín hiệu dừng cho một thành phần khác. doFinally quan sát cả complete, error và cancel; callback nhận SignalType để phân biệt nguyên nhân kết thúc.

    Flux<Data> data =
        remoteFeed()
            .doOnCancel(() -> log.info("Stopping remote feed"))
            .doFinally(signal -> metrics.recordTermination(signal));

Không dùng callback đồng bộ này để thực hiện một quy trình cleanup bất đồng bộ kéo dài. Nếu cần đóng tài nguyên bằng publisher, dùng usingWhen để định nghĩa riêng đường cleanup khi hoàn tất, khi lỗi và khi hủy.

### 6.2. usingWhen cho tài nguyên bất đồng bộ

usingWhen quản lý tài nguyên được cấp phát bằng một publisher và chọn publisher cleanup tùy theo cách luồng kết thúc. Ví dụ sau minh họa một kết nối được mở bất đồng bộ, dùng để truy vấn, rồi đóng khi hoàn tất, lỗi hoặc bị hủy:

    Mono<Result> result =
        Mono.usingWhen(
            connectionFactory.create(),
            connection -> connection.query("select status"),
            connection -> connection.close(),
            (connection, error) -> connection.close(),
            connection -> connection.close()
        );

Trong ví dụ, ba hàm cleanup tương ứng với complete, error và cancel. Nếu API đóng kết nối trả về Mono<Void>, các hàm này có thể dùng trực tiếp. Ở ứng dụng thực tế, cần xử lý cả lỗi trong quá trình cleanup và chọn chính sách phù hợp nếu việc đóng tài nguyên thất bại.

Nếu tài nguyên được tạo bên ngoài pipeline và không được đăng ký với cơ chế quản lý vòng đời, cancellation có thể không biết cách giải phóng nó. Hãy tạo và sở hữu tài nguyên bên trong using/usingWhen hoặc gắn một callback cleanup rõ ràng với subscription.

## 7. Giới hạn của cancellation với tác vụ blocking

Cancellation hoạt động tốt nhất khi nguồn và các toán tử hợp tác với nó. Một lời gọi I/O bất đồng bộ có thể được hủy thông qua connector; một publisher tùy chỉnh có thể dừng producer khi nhận cancel. Nhưng một đoạn mã blocking tự chạy không nhất thiết dừng ngay chỉ vì subscription đã bị dispose.

Ví dụ, nếu một hàm đang chạy vòng lặp tính toán dài và không kiểm tra trạng thái hủy, việc hủy subscription không thể tự động làm cho logic nghiệp vụ dừng an toàn. Tương tự, một thư viện JDBC đồng bộ có thể không hỗ trợ hủy truy vấn theo cách mà pipeline mong muốn.

Với tác vụ do ứng dụng tự quản lý:

- Dùng API có hỗ trợ cancellation hoặc timeout nếu có.
- Với vòng lặp tính toán, kiểm tra cờ dừng tại các điểm an toàn.
- Với tác vụ blocking, xác định rõ khả năng interrupt/cancel của thư viện và xử lý interruption đúng cách.
- Không giả định dispose luôn đảo ngược được side effect đã xảy ra.
- Đặt timeout ở tầng phù hợp và bảo đảm tài nguyên được đóng trong mọi nhánh.

Chuyển tác vụ blocking sang Schedulers.boundedElastic() giúp không chặn event loop, nhưng tự nó không biến thư viện blocking thành một API có khả năng hủy hoàn toàn. Vẫn cần hiểu hành vi hủy của thư viện được gọi.

## 8. Cancellation và backpressure phối hợp ra sao?

Backpressure và cancellation đều là cơ chế điều khiển từ subscriber đến publisher, nhưng chúng có mục tiêu khác nhau:

| Cơ chế | Tác động |
|---|---|
| request(n) | Cho phép phát thêm tối đa n phần tử |
| Không request thêm | Tạm thời không cấp thêm nhu cầu; subscription vẫn có thể còn hoạt động |
| cancel() | Yêu cầu kết thúc việc phát dữ liệu cho subscription |
| dispose() trong Reactor | Hủy subscription thông qua handle Disposable |
| timeout(Duration) | Khi quá hạn, hủy upstream và phát lỗi timeout hoặc dùng fallback |

Nếu consumer chỉ đang bận xử lý, nó có thể ngừng yêu cầu thêm để tạo backpressure. Nếu consumer không còn quan tâm đến luồng nữa, nó nên cancel. Không nên dùng cancellation như cách tạm dừng vì subscription đã bị hủy không thể được tiếp tục; muốn nhận lại dữ liệu, phải tạo subscription mới và xác định cách khôi phục vị trí đọc nếu cần.

## 9. Kiểm thử cancellation

StepVerifier hỗ trợ kiểm tra việc hủy bằng thenCancel(). Có thể kết hợp doOnCancel để xác nhận nguồn nhận được yêu cầu hủy:

    import java.util.concurrent.atomic.AtomicBoolean;
    import reactor.core.publisher.Flux;
    import reactor.test.StepVerifier;

    AtomicBoolean cancelled = new AtomicBoolean();

    Flux<Long> source =
        Flux.<Long>never()
            .doOnCancel(() -> cancelled.set(true));

    StepVerifier.create(source)
        .thenCancel()
        .verify();

    assert cancelled.get();

Flux.never() không phát dữ liệu và không tự kết thúc. StepVerifier hủy subscription; doOnCancel ghi nhận việc đó. Trong bài kiểm thử JUnit thực tế, hãy dùng assertion của thư viện kiểm thử thay cho Java assert nếu cấu hình chạy không bật assertions.

Có thể kiểm tra timeout với thời gian ảo để tránh chờ thật:

    import java.time.Duration;
    import reactor.core.publisher.Mono;
    import reactor.test.StepVerifier;

    StepVerifier.withVirtualTime(
            () -> Mono.<String>never()
                .timeout(Duration.ofSeconds(5))
        )
        .thenAwait(Duration.ofSeconds(5))
        .expectError(java.util.concurrent.TimeoutException.class)
        .verify();

Nguồn không bao giờ phát tín hiệu. Khi đồng hồ ảo đi qua năm giây, timeout hủy upstream và downstream nhận TimeoutException. Nếu thêm doOnCancel vào nguồn, bài kiểm thử cũng có thể xác nhận nhánh upstream đã nhận cancellation.

## 10. Những lỗi thường gặp khi hủy subscription

**Chờ onComplete sau cancel.** Cancellation không phải tín hiệu hoàn tất. Nếu cần quan sát việc hủy, dùng doOnCancel hoặc doFinally với SignalType.CANCEL.

**Chỉ đặt timeout ở một tầng và cho rằng mọi giai đoạn đều được bảo vệ.** Timeout của publisher, timeout kết nối và timeout đọc HTTP có phạm vi khác nhau. Hãy đặt deadline cho các giai đoạn thực sự cần giới hạn.

**Tự subscribe trong controller hoặc service rồi quên quản lý Disposable.** Subscription độc lập có thể tiếp tục sau khi request HTTP đã kết thúc. Chỉ tạo subscription thủ công khi component có quyền sở hữu và quản lý vòng đời của nó.

**Giả định cancel đảo ngược side effect.** Hủy response không xóa giao dịch đã commit, không thu hồi thông điệp đã gửi và không hoàn tác lời gọi bên ngoài đã hoàn tất.

**Giải phóng tài nguyên chỉ trong nhánh complete.** Luồng có thể lỗi hoặc bị hủy. Hãy dùng usingWhen hoặc cơ chế cleanup bao phủ cả ba nhánh.

**Cho rằng tác vụ blocking dừng ngay khi dispose.** Cancellation cần sự hợp tác của nguồn và thư viện. Với mã tự viết, hãy cung cấp điểm kiểm tra dừng và xử lý tài nguyên an toàn.

## 11. Checklist thiết kế vòng đời subscription

Trước khi đưa một pipeline vào ứng dụng, hãy xác định:

1. Ai tạo subscription và component nào sở hữu quyền hủy?
2. Điều kiện nào kích hoạt cancellation: timeout, client disconnect, thao tác người dùng hay shutdown?
3. Hủy chỉ dừng việc gửi response hay còn phải dừng một tác vụ nền?
4. Nguồn upstream có hỗ trợ cancellation và giải phóng tài nguyên không?
5. Các tài nguyên được đóng trong nhánh complete, error và cancel như thế nào?
6. Tác vụ blocking có điểm dừng hợp tác hay API hủy phù hợp không?
7. Side effect nào đã commit và không thể hoàn tác khi subscription bị hủy?
8. Có kiểm thử xác nhận cancellation được truyền đến nguồn và timeout được xử lý đúng không?

Khi quyền sở hữu subscription, điều kiện hủy và chính sách cleanup được xác định rõ, pipeline reactive sẽ tránh tiếp tục làm việc sau khi không còn người tiêu thụ. Timeout, HTTP cancellation và shutdown khi đó trở thành những phần có thể dự đoán và kiểm thử của vòng đời ứng dụng.

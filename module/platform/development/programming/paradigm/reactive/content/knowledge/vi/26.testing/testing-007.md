# TestPublisher: chủ động phát tín hiệu và tình huống vi phạm

Khi kiểm thử một pipeline reactive, nguồn dữ liệu thật thường khó điều khiển. Database, HTTP client hoặc message broker có thể phát dữ liệu theo lịch riêng, làm test phụ thuộc vào mạng, thời gian hoặc trạng thái môi trường. Với nhiều operator, ta cần chủ động quyết định lúc nào nguồn phát phần tử, lúc nào hoàn tất, lúc nào báo lỗi và lúc nào nhận cancellation.

TestPublisher trong Reactor Test là một publisher kiểm thử cho phép test chủ động gửi các tín hiệu đó. Nó giúp tạo nguồn dữ liệu có thể điều khiển, quan sát subscriber và kiểm tra cách pipeline phản ứng với demand. Ngoài chế độ tuân thủ Reactive Streams, TestPublisher còn có chế độ không tuân thủ một số quy tắc để kiểm tra adapter hoặc operator trước nguồn phát sai hợp đồng.

TestPublisher thường kết hợp với StepVerifier: TestPublisher điều khiển phía upstream, còn StepVerifier kiểm tra những tín hiệu downstream quan sát được. Phân chia hai vai trò này giúp test tập trung vào hành vi của pipeline thay vì phụ thuộc vào một nguồn bên ngoài.

## 1. TestPublisher giải quyết vấn đề gì?

Một publisher kiểm thử có thể cho test quyết định chính xác:

- Khi nào subscriber được đăng ký.
- Khi nào nguồn phát một hoặc nhiều phần tử.
- Khi nào nguồn hoàn tất bằng onComplete.
- Khi nào nguồn kết thúc bằng onError.
- Subscriber đã yêu cầu dữ liệu hay chưa.
- Subscriber đã hủy subscription hay chưa.
- Pipeline có phản ứng đúng khi nguồn phát sai hợp đồng hay không.

Ví dụ, một pipeline lọc sự kiện có thể cần kiểm tra rằng nó không phát kết quả trước khi nguồn thực sự gửi dữ liệu. Nếu dùng Flux.just, tất cả phần tử được định nghĩa sẵn và test khó tách thời điểm subscribe khỏi thời điểm phát tín hiệu. TestPublisher cho phép giữ nguồn ở trạng thái chờ rồi phát dữ liệu đúng lúc test yêu cầu.

TestPublisher không thay thế StepVerifier. Hai công cụ giải quyết hai phía của cùng một test:

| Công cụ | Vai trò chính |
|---|---|
| TestPublisher | Điều khiển tín hiệu upstream và quan sát yêu cầu/cancellation |
| StepVerifier | Đăng ký subscriber và xác minh tín hiệu downstream theo thứ tự |
| PublisherProbe | Kiểm tra publisher nhánh có được subscribe, request hoặc cancel hay không |
| VirtualTimeScheduler | Điều khiển thời gian ảo cho delay, interval và timeout |

Khi test cần tự phát dữ liệu theo từng bước, chọn TestPublisher. Khi test chỉ cần kiểm tra một publisher đã có sẵn, dùng StepVerifier trực tiếp.

## 2. Dependency và import

Trong dự án dùng Reactor, thêm module reactor-test ở scope test. Nếu Spring Boot dependency management đang quản lý version Reactor, nên để BOM đồng bộ version:

    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>

Các import thường dùng:

    import reactor.core.publisher.Flux;
    import reactor.core.publisher.Mono;
    import reactor.test.StepVerifier;
    import reactor.test.publisher.TestPublisher;
    import java.util.ArrayList;
    import java.util.List;
    import java.util.concurrent.atomic.AtomicInteger;

    import static org.junit.jupiter.api.Assertions.assertEquals;

Không đưa reactor-test vào dependency runtime của ứng dụng chỉ để tạo nguồn kiểm thử. TestPublisher thuộc hạ tầng test.

## 3. Tạo TestPublisher và lấy publisher view

Tạo một nguồn kiểm thử:

    TestPublisher<String> source =
        TestPublisher.create();

    Flux<String> events = source.flux();

source là đối tượng điều khiển được giữ trong test. events là publisher mà production pipeline sẽ tiêu thụ. Tách hai biến giúp test chỉ tác động đến nguồn thông qua API TestPublisher.

Nếu pipeline chỉ nhận tối đa một phần tử, có thể dùng view Mono:

    TestPublisher<User> source =
        TestPublisher.create();

    Mono<User> user = source.mono();

Không phát nhiều giá trị cho một Mono. Dùng next(value) để phát một giá trị và complete() để kết thúc, hoặc dùng emit(value) để phát rồi hoàn tất.

TestPublisher.create() tạo nguồn hot: tín hiệu chỉ đến những subscriber đã đăng ký tại thời điểm phát. Nếu test phát trước khi pipeline subscribe, phần tử không tự được lưu để phát lại cho subscriber đăng ký sau.

Một nguồn cold có thể được tạo bằng TestPublisher.createCold(). Nguồn cold lưu các tín hiệu đã phát để từng subscriber có thể nhận lại chuỗi đó khi đăng ký. Chọn hot hoặc cold theo semantics mà pipeline cần kiểm thử; đừng vô tình dựa vào replay của cold source nếu production source là hot.

## 4. Điều khiển thời điểm phát tín hiệu

Ví dụ kiểm thử pipeline chuyển chữ hoa:

    TestPublisher<String> source =
        TestPublisher.create();

    Flux<String> upperCase =
        source.flux()
            .map(String::toUpperCase);

    StepVerifier.create(upperCase)
        .then(() -> source.next("reactor"))
        .expectNext("REACTOR")
        .then(() -> source.next("publisher"))
        .expectNext("PUBLISHER")
        .then(source::complete)
        .verifyComplete();

StepVerifier đăng ký trước. Mỗi bước then thực hiện một hành động trên TestPublisher, rồi các bước expectNext kiểm tra kết quả tương ứng. Nguồn chỉ hoàn tất khi test gọi complete().

Có thể phát nhiều phần tử trong một lần:

    TestPublisher<String> batchSource =
        TestPublisher.create();

    StepVerifier.create(
            batchSource.flux().map(String::trim)
        )
        .then(() -> batchSource.next(" one ", " two ", " three "))
        .expectNext("one", "two", "three")
        .then(batchSource::complete)
        .verifyComplete();

next phát phần tử nhưng không tự kết thúc nguồn. emit phát các phần tử được truyền vào rồi hoàn tất:

    TestPublisher<String> emitSource =
        TestPublisher.create();

    StepVerifier.create(emitSource.flux())
        .then(() -> emitSource.emit("A", "B", "C"))
        .expectNext("A", "B", "C")
        .verifyComplete();

Phân biệt hai cách gọi này rất quan trọng khi test operator chờ nguồn hoàn tất, như collectList, reduce hoặc then.

## 5. Kiểm thử demand và backpressure

Reactive Streams yêu cầu subscriber gọi request(n) trước khi publisher phát tối đa n phần tử. StepVerifier có thể bắt đầu với demand bằng 0 để test chính xác thời điểm yêu cầu dữ liệu:

    TestPublisher<Integer> source =
        TestPublisher.create();

    StepVerifier.create(source.flux(), 0)
        .expectSubscription()
        .then(() -> source.assertWasNotRequested())
        .thenRequest(1)
        .then(() -> source.assertWasRequested())
        .then(() -> source.next(10))
        .expectNext(10)
        .thenRequest(1)
        .then(() -> source.next(20))
        .expectNext(20)
        .then(source::complete)
        .verifyComplete();

Luồng kiểm thử:

1. StepVerifier đăng ký nhưng chưa yêu cầu phần tử.
2. Test xác nhận TestPublisher chưa nhận demand.
3. StepVerifier yêu cầu một phần tử.
4. Test xác nhận nguồn đã nhận request.
5. Nguồn phát một phần tử và verifier nhận đúng một phần tử.
6. Verifier yêu cầu thêm một phần tử rồi test phát giá trị tiếp theo.

TestPublisher tuân thủ demand trong chế độ mặc định. Nếu test gọi next vượt quá số phần tử được yêu cầu, TestPublisher có thể báo assertion failure ngay tại nơi phát. Đây là tín hiệu hữu ích cho thấy test đang vi phạm giao thức.

Demand được truyền qua cả pipeline. Nếu operator có prefetch hoặc buffer nội bộ, số request quan sát tại TestPublisher có thể lớn hơn số phần tử StepVerifier yêu cầu trực tiếp. Khi kiểm thử một operator như flatMap, cần hiểu prefetch và concurrency của operator trước khi khẳng định số request chính xác.

## 6. Kiểm tra cancellation

Cancellation là một phần của hợp đồng. Khi downstream không cần dữ liệu nữa, yêu cầu hủy phải truyền ngược upstream để giải phóng tài nguyên nếu nguồn hỗ trợ.

Ví dụ take(1) phải hủy nguồn sau phần tử đầu:

    TestPublisher<Integer> source =
        TestPublisher.create();

    StepVerifier.create(
            source.flux().take(1)
        )
        .then(() -> source.next(7))
        .expectNext(7)
        .verifyComplete();

    source.assertCancelled();

take(1) hoàn tất downstream sau một phần tử và hủy subscription upstream. assertCancelled() xác nhận TestPublisher đã quan sát cancellation.

Có thể kiểm tra cancellation khi verifier chủ động hủy:

    TestPublisher<String> source =
        TestPublisher.create();

    StepVerifier.create(source.flux())
        .thenCancel()
        .verify();

    source.assertCancelled();

Trong test thực tế, hãy xác định đúng ai sở hữu subscription và thời điểm cancellation xảy ra. Một operator có thể hủy upstream khi downstream hoàn tất, timeout hoặc chuyển sang nhánh khác; không nên chỉ kiểm tra cancellation trong trường hợp thenCancel().

## 7. Kiểm tra lỗi và tín hiệu kết thúc

TestPublisher có thể chủ động kết thúc bằng lỗi:

    TestPublisher<String> source =
        TestPublisher.create();

    Flux<Integer> lengths =
        source.flux()
            .map(String::length);

    StepVerifier.create(lengths)
        .then(() ->
            source.error(
                new IllegalStateException("source failed")
            )
        )
        .expectErrorMessage("source failed")
        .verify();

Có thể xác minh chính xác loại lỗi:

    TestPublisher<String> typedErrorSource =
        TestPublisher.create();

    StepVerifier.create(typedErrorSource.flux())
        .then(() -> typedErrorSource.error(
            new IllegalArgumentException("invalid event")
        ))
        .expectError(IllegalArgumentException.class)
        .verify();

Một publisher chỉ có một tín hiệu terminal hợp lệ: onComplete hoặc onError. Sau khi terminal đã được phát, nguồn không được phát onNext hay một terminal khác tới cùng subscriber.

Để kiểm tra operator phục hồi lỗi, phát lỗi từ TestPublisher rồi xác minh publisher thay thế:

    TestPublisher<String> source =
        TestPublisher.create();

    Flux<String> recovered =
        source.flux()
            .onErrorResume(error ->
                Flux.just("fallback")
            );

    StepVerifier.create(recovered)
        .then(() -> source.error(
            new IllegalStateException("offline")
        ))
        .expectNext("fallback")
        .verifyComplete();

Ví dụ này kiểm tra tín hiệu quan sát được downstream. Nếu cần xác nhận nhánh fallback đã được subscribe, có thể kết hợp PublisherProbe để quan sát publisher nhánh.

## 8. Kiểm thử operator cần chờ nguồn hoàn tất

Một số operator không phát kết quả cuối cùng cho đến khi nguồn hoàn tất. TestPublisher cho phép giữ nguồn mở để xác nhận pipeline chưa phát sớm:

    TestPublisher<Integer> source =
        TestPublisher.create();

    Mono<List<Integer>> collected =
        source.flux().collectList();

    StepVerifier.create(collected)
        .then(() -> source.next(1, 2, 3))
        .then(source::assertWasRequested)
        .then(source::complete)
        .expectNext(List.of(1, 2, 3))
        .verifyComplete();

collectList giữ các phần tử cho đến khi nguồn hoàn tất. Test chỉ nhận danh sách sau lệnh complete(). Ví dụ này phù hợp với nguồn hữu hạn; không dùng collectList cho stream vô hạn.

Với reduce, có thể kiểm tra accumulator chỉ được phát sau terminal:

    TestPublisher<Integer> source =
        TestPublisher.create();

    Mono<Integer> total =
        source.flux().reduce(0, Integer::sum);

    StepVerifier.create(total)
        .then(() -> source.next(2, 3, 5))
        .then(source::complete)
        .expectNext(10)
        .verifyComplete();

## 9. TestPublisher không tuân thủ hợp đồng

Publisher production nên tuân thủ Reactive Streams. Tuy nhiên, adapter hoặc operator của ứng dụng đôi khi phải kết nối với thư viện bên ngoài mà chất lượng publisher chưa được bảo đảm. TestPublisher có chế độ non-compliant để tạo một số tình huống phát sai giao thức có chủ đích.

Tạo nguồn non-compliant bằng createNoncompliant và chỉ bật violation mà test cần:

    TestPublisher<Integer> source =
        TestPublisher.createNoncompliant(
            TestPublisher.Violation.REQUEST_OVERFLOW
        );

Chế độ này cho phép test phát nhiều phần tử hơn demand đã cấp. Nó hữu ích để kiểm tra adapter hoặc lớp bảo vệ trước nguồn phát vượt yêu cầu.

Các violation có sẵn phụ thuộc version reactor-test. Những tình huống thường cần kiểm thử gồm:

| Violation | Hành vi cần mô phỏng |
|---|---|
| REQUEST_OVERFLOW | Nguồn phát phần tử vượt số lượng đã được request |
| ALLOW_NULL | Nguồn cố phát null, trái quy tắc Reactive Streams |
| DEFER_CANCELLATION | Nguồn trì hoãn phản ứng với cancellation để mô phỏng tác vụ không dừng tức thì |

Hãy kiểm tra enum của version Reactor mà dự án đang dùng trước khi chọn violation. Không tự đặt tên violation không tồn tại trong version đó.

Chế độ non-compliant cố ý phá vỡ một phần hợp đồng. Không dùng nó làm nguồn thông thường cho các test thành công và không diễn giải hành vi sau vi phạm như một bảo đảm của Reactive Streams. Mục tiêu là xác nhận adapter hoặc operator của ứng dụng xử lý tình huống bất thường theo chính sách đã chọn.

## 10. Kiểm thử buffer khi downstream chưa có demand

Operator onBackpressureBuffer có thể yêu cầu dữ liệu upstream rồi giữ một lượng phần tử trong buffer khi downstream chưa có demand. TestPublisher compliant có thể kiểm soát nguồn trong tình huống này:

    TestPublisher<Integer> source =
        TestPublisher.create();

    Flux<Integer> guarded =
        source.flux()
            .onBackpressureBuffer(4);

    StepVerifier.create(guarded, 0)
        .expectSubscription()
        .then(() -> source.next(1, 2))
        .thenRequest(2)
        .expectNext(1, 2)
        .then(() -> source.complete())
        .verifyComplete();

Operator onBackpressureBuffer yêu cầu upstream theo chính sách của nó rồi giữ các phần tử cho downstream khi demand chưa có. Ví dụ này kiểm tra buffering theo demand downstream; nguồn vẫn nhận demand từ operator nên đây không phải phép thử publisher phát vượt request.

Để kiểm tra nguồn thực sự phát vượt demand, dùng createNoncompliant với REQUEST_OVERFLOW ở ranh giới adapter đang được kiểm thử. Ví dụ, nếu adapter của ứng dụng cam kết chuyển hành vi đó thành IllegalStateException, hãy đặt adapter giữa TestPublisher và StepVerifier rồi xác minh đúng exception đó. Kết quả cụ thể thuộc hợp đồng của adapter; Reactive Streams không quy định một cách phục hồi chung cho publisher đã vi phạm request(n).

Nếu đang kiểm thử một adapter tự viết, hãy xác định hợp đồng đầu ra mong muốn khi nguồn phát vượt demand: từ chối, phát lỗi domain, ghi metric hoặc áp dụng một chính sách buffer hữu hạn. Sau đó viết assertion cho chính hợp đồng đó. Không khẳng định một kết quả chung cho mọi pipeline vì hành vi khi upstream vi phạm đặc tả không được Reactive Streams bảo đảm.

## 11. Kiểm thử nguồn phát null

Reactive Streams cấm null trong onNext. Trong Java, null có thể lọt vào từ API cũ hoặc adapter không kiểm tra đầu vào. TestPublisher có thể mô phỏng tình huống này:

    TestPublisher<String> source =
        TestPublisher.createNoncompliant(
            TestPublisher.Violation.ALLOW_NULL
        );

    Flux<String> pipeline =
        source.flux()
            .map(String::trim);

    StepVerifier.create(pipeline)
        .then(() -> source.next((String) null))
        .expectError(NullPointerException.class)
        .verify();

Ví dụ trên minh họa một mapper dereference giá trị null. Trong adapter thực tế, nên kiểm tra và chuyển dữ liệu null thành lỗi có ngữ nghĩa rõ ở ranh giới tích hợp thay vì để null lan sâu vào pipeline.

Không dùng ALLOW_NULL để hợp thức hóa null trong ứng dụng reactive. Violation này chỉ phục vụ test nguồn sai hợp đồng.

## 12. Kiểm thử cancellation bị trì hoãn

Một thư viện ngoài có thể nhận yêu cầu hủy nhưng không dừng công việc ngay lập tức. Điều đó có thể xảy ra khi tác vụ đang trong đoạn xử lý không thể interrupt hoặc API chỉ kiểm tra cờ hủy ở một thời điểm sau.

DEFER_CANCELLATION cho phép mô phỏng một nguồn trì hoãn việc thực hiện cancellation. Dùng nó để kiểm tra adapter có:

- Ngừng phát kết quả vào phần nghiệp vụ không còn subscriber.
- Không giải phóng tài nguyên quá sớm khi công việc vẫn đang sử dụng.
- Ghi nhận trạng thái cancellation để ngăn xử lý tiếp theo khi nguồn kiểm tra cờ.
- Hoàn tất cleanup đúng lifecycle dù thao tác bên ngoài chưa dừng tức thì.

Khi test loại tình huống này, không nên giả định cancel() có thể hoàn tác một request đã gửi đến server hoặc một side effect đã được thực hiện. Cancellation là tín hiệu điều khiển vòng đời subscription; khả năng dừng công việc vật lý phụ thuộc nguồn.

## 13. Kiểm tra số subscriber và request

TestPublisher có các assertion để xác nhận subscriber đã kết nối và demand đã được gửi:

    TestPublisher<String> source =
        TestPublisher.create();

    Flux<String> pipeline =
        source.flux().filter(value -> !value.isBlank());

    StepVerifier.create(pipeline, 0)
        .expectSubscription()
        .then(() -> source.assertSubscribers(1))
        .then(() -> source.assertWasNotRequested())
        .thenRequest(1)
        .then(() -> source.assertWasRequested())
        .then(() -> source.next("ready"))
        .expectNext("ready")
        .then(source::complete)
        .verifyComplete();

Các assertion hữu ích khác tùy version gồm kiểm tra không có subscriber, đã bị cancel, đã terminate hoặc có overflow. Chọn assertion phản ánh đúng điều test cần chứng minh; không kiểm tra nội bộ implementation nếu hợp đồng công khai không yêu cầu.

Ví dụ, nếu một operator chỉ nên subscribe nguồn khi có subscriber downstream, hãy kiểm tra assertSubscribers(1) sau bước subscribe. Nếu pipeline có share() hoặc retry, số subscriber upstream có thể khác với số subscriber downstream; cần mô tả rõ ranh giới đang quan sát.

## 14. Kiểm thử retry với nguồn điều khiển được

TestPublisher có thể phát lỗi rồi kiểm tra operator retry đăng ký lại upstream. Vì TestPublisher mặc định là hot và một nguồn có thể không cho phép subscribe nhiều lần tùy cấu hình, nên dùng publisher factory tạo nguồn mới cho mỗi subscription khi test retry.

Ví dụ dùng Flux.defer để cấp một TestPublisher mới theo từng lần subscribe:

    AtomicInteger attempts = new AtomicInteger();
    List<TestPublisher<String>> sources =
        new ArrayList<>();

    Flux<String> retried =
        Flux.defer(() -> {
            attempts.incrementAndGet();
            TestPublisher<String> source =
                TestPublisher.create();
            sources.add(source);
            return source.flux();
        })
        .retry(1);

    StepVerifier.create(retried)
        .then(() -> sources.get(0)
            .error(new IllegalStateException("temporary")))
        .then(() -> {
            assertEquals(2, attempts.get());
            sources.get(1).next("recovered");
            sources.get(1).complete();
        })
        .expectNext("recovered")
        .verifyComplete();

Mẫu này cho thấy retry tạo subscription mới và factory cấp một nguồn mới. Trong test thực tế, cần điều phối các bước theo thời điểm nguồn mới được tạo; nếu pipeline retry trên scheduler bất đồng bộ, dùng tín hiệu đồng bộ hoặc hook kiểm thử phù hợp để tránh truy cập danh sách trước khi publisher mới được tạo.

Với chính sách retry có backoff hoặc delay, có thể kết hợp StepVerifier.withVirtualTime và VirtualTimeScheduler. TestPublisher điều khiển tín hiệu, còn virtual time điều khiển thời gian chờ.

## 15. Kết hợp TestPublisher với operator có buffer

Khi kiểm thử buffer, window, onBackpressureBuffer hoặc publishOn, hãy phân biệt:

- Demand downstream mà StepVerifier gửi.
- Prefetch mà operator yêu cầu upstream.
- Số phần tử đang được giữ trong queue nội bộ.
- Số phần tử TestPublisher đã phát.

Ví dụ, một operator có thể request trước một batch để tăng throughput. Vì vậy, việc StepVerifier chưa yêu cầu phần tử không nhất thiết đồng nghĩa TestPublisher chưa nhận request; operator trung gian có thể đã prefetch.

Nếu muốn kiểm tra hợp đồng demand ở chính ranh giới subscriber, test publisher trực tiếp với StepVerifier và không đặt operator có prefetch ở giữa. Nếu muốn kiểm tra operator, hãy xác nhận semantics của operator và đặt assertion ở ranh giới phù hợp.

Không dùng assertWasNotRequested sau khi một operator đã chủ động prefetch rồi kết luận operator sai. Trước hết hãy xác định operator có quyền yêu cầu trước theo thiết kế hay không.

## 16. TestPublisher và publisher được chia sẻ

Khi kiểm thử share, publish().refCount() hoặc replay, cần chú ý thời điểm subscriber kết nối. TestPublisher hot chỉ gửi tín hiệu cho subscriber hiện tại; subscriber đến sau sẽ không nhận lại tín hiệu cũ trừ khi operator downstream có replay/buffer.

Ví dụ kiểm tra subscriber nhận tín hiệu sau khi đã đăng ký:

    TestPublisher<Integer> source =
        TestPublisher.create();

    Flux<Integer> shared =
        source.flux().share();

    StepVerifier.create(shared)
        .then(() -> source.assertSubscribers(1))
        .then(() -> source.next(1))
        .expectNext(1)
        .thenCancel()
        .verify();

Trong test nhiều subscriber, có thể dùng hai verifier hoặc một publisher kiểm thử downstream thích hợp để xác nhận cả hai đã subscribe trước khi phát. Không phát tín hiệu ngay sau khi tạo shared, vì lúc đó chưa chắc đã có subscriber.

Khi kiểm thử replay, phát tín hiệu theo thứ tự, hoàn tất nguồn nếu cần, rồi đăng ký subscriber thứ hai và xác minh đúng chính sách replay của operator.

## 17. Tổ chức test rõ ràng và tránh phụ thuộc thời gian

Một test tốt nên thể hiện được trình tự:

1. Tạo TestPublisher.
2. Xây dựng pipeline production cần kiểm thử.
3. Đăng ký StepVerifier.
4. Chủ động phát tín hiệu tại các bước then.
5. Xác minh phần tử, lỗi hoặc complete.
6. Xác minh request/cancel ở nguồn nếu đó là hợp đồng cần kiểm tra.

Ví dụ:

    @Test
    void mapsEventsAndCompletesOnlyAfterSourceCompletes() {
        TestPublisher<String> source =
            TestPublisher.create();

        Flux<Integer> pipeline =
            source.flux().map(String::length);

        StepVerifier.create(pipeline)
            .then(() -> source.next("one", "four"))
            .expectNext(3, 4)
            .then(source::complete)
            .verifyComplete();
    }

Không dùng Thread.sleep để chờ nguồn phát. Nó làm test chậm và dễ chập chờn. Dùng then, thenAwait khi thực sự kiểm tra thời gian, hoặc virtual time nếu operator hỗ trợ scheduler ảo.

Mỗi test nên tạo TestPublisher mới. Không dùng chung một publisher mutable giữa nhiều test vì trạng thái subscriber, terminal và cancellation có thể làm test sau phụ thuộc test trước.

## 18. Những nhầm lẫn thường gặp

**Phát tín hiệu trước khi subscribe vào hot TestPublisher.** Subscriber đến sau không tự nhận lại tín hiệu đã phát. Đăng ký verifier trước rồi mới gọi next hoặc emit.

**Nhầm next với emit.** next chỉ phát phần tử; emit phát các phần tử rồi hoàn tất nguồn.

**Quên phát terminal signal.** Test chờ complete nhưng nguồn không gọi complete, hoặc chờ lỗi nhưng nguồn không gọi error.

**Gọi next vượt demand trong nguồn compliant.** TestPublisher mặc định kiểm tra demand. Hãy điều khiển request bằng StepVerifier hoặc dùng non-compliant mode chỉ trong test chuyên biệt.

**Dùng non-compliant source như publisher bình thường.** Nó cố ý phá một quy tắc. Kết quả sau vi phạm không phải bảo đảm chung của Reactive Streams.

**Cho rằng TestPublisher thay thế StepVerifier.** TestPublisher điều khiển nguồn; StepVerifier xác minh hành vi subscriber.

**Cho rằng cancellation luôn dừng công việc bên ngoài tức thì.** Test cancellation của subscription và kiểm tra riêng khả năng dừng tài nguyên của adapter.

**Kiểm tra request chính xác qua operator có prefetch mà không tính đến prefetch.** Operator có thể yêu cầu upstream trước khi downstream yêu cầu trực tiếp.

**Dùng TestPublisher để kiểm thử database driver thật.** TestPublisher phù hợp với logic publisher/operator. Hành vi cursor, transaction và connection pool cần integration test với driver hoặc database phù hợp.

## 19. Checklist kiểm thử bằng TestPublisher

Trước khi hoàn thành test, hãy xác định:

1. Test cần nguồn hot hay cold?
2. Subscriber đã đăng ký trước khi nguồn phát tín hiệu chưa?
3. Test có điều khiển riêng next, complete và error không?
4. Demand ban đầu có cần bằng 0 để kiểm tra backpressure không?
5. Có cần xác minh upstream nhận request hoặc cancellation không?
6. Operator ở giữa có prefetch hoặc buffer làm thay đổi request không?
7. Test có kiểm tra lỗi và tín hiệu terminal đúng thứ tự không?
8. Có cần tạo non-compliant source để kiểm tra adapter trước nguồn sai hợp đồng không?
9. Violation được dùng có tồn tại trong version Reactor Test của dự án không?
10. Kết quả sau vi phạm có được kiểm tra theo hợp đồng riêng của ứng dụng thay vì giả định của Reactive Streams không?
11. Test có tránh Thread.sleep và tạo nguồn mới cho từng lần chạy không?
12. Các hành vi của driver hoặc broker có cần integration test riêng không?

TestPublisher giúp kiểm thử pipeline reactive theo từng tín hiệu: test quyết định lúc phát dữ liệu, lúc hoàn tất, lúc báo lỗi và quan sát request/cancellation ở upstream. Ở chế độ compliant, nó giúp xác minh pipeline theo hợp đồng Reactive Streams. Ở chế độ non-compliant, nó tạo các đầu vào sai hợp đồng để kiểm tra lớp tích hợp có phòng vệ đúng mức. Khi kết hợp TestPublisher với StepVerifier và chỉ dùng violation có chủ đích, test trở nên xác định, nhanh và tập trung vào hành vi thật sự cần bảo vệ.

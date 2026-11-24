# Quan sát vòng đời bằng các điểm móc trước và sau tín hiệu

Một pipeline reactive có thể phát dữ liệu, hoàn tất, lỗi hoặc bị hủy. Khi vận hành ứng dụng, ta thường cần ghi log, đo thời gian, đếm phần tử, theo dõi nhu cầu và giải phóng tài nguyên ở những thời điểm cụ thể của vòng đời đó. Project Reactor cung cấp các toán tử quan sát (side-effect hooks) để thực hiện những công việc này ngay tại vị trí mong muốn trong pipeline.

Bài học thuộc chương **Đăng ký nhận** của module **REACTIVE_PROGRAMMING**. Module tập trung vào tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; các kỹ thuật quan sát vòng đời ở đây sẽ hỗ trợ việc sử dụng Mono, Flux, toán tử, scheduler, xử lý lỗi và kiểm thử pipeline Java.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Xác định thời điểm các hook được gọi so với tín hiệu mà chúng quan sát.
- Chọn đúng hook để theo dõi subscription, demand, phần tử, lỗi, hoàn tất và hủy.
- Phân biệt hook chạy trước khi tín hiệu đi xuống với hook chạy sau khi tín hiệu kết thúc đã được truyền xuống.
- Giải thích vì sao vị trí của hook trong pipeline làm thay đổi dữ liệu và tín hiệu mà nó quan sát.
- Dùng doFinally để ghi nhận trạng thái kết thúc, kể cả khi subscription bị hủy.
- Kiểm thử hành vi của hook bằng StepVerifier và tránh đưa tác dụng phụ nặng vào đường xử lý reactive.

## 1. Hook quan sát là gì?

Các toán tử như map, filter và flatMap biến đổi dữ liệu hoặc cách kết hợp các Publisher. Ngược lại, những toán tử bắt đầu bằng doOn, cùng doAfterTerminate và doFinally, chủ yếu thêm một hành động phụ khi một sự kiện xảy ra. Hành động phụ thường dùng cho logging, metrics, tracing, audit hoặc dọn dẹp trạng thái quan sát.

Ví dụ:

~~~java
Flux<Integer> numbers =
    Flux.range(1, 3)
        .doOnNext(value -> log.info("Nguồn phát {}", value))
        .map(value -> value * 10)
        .doOnNext(value -> log.info("Sau map: {}", value));
~~~

Hai hook doOnNext không quan sát cùng một giá trị. Hook trước map nhìn thấy 1, 2, 3; hook sau map nhìn thấy 10, 20, 30. Cả hai đều quan sát phần tử tại vị trí của chúng trong chuỗi.

Một hook không tự tạo subscription. Publisher chỉ thực thi pipeline khi có subscriber đăng ký, và một hook chỉ được kích hoạt khi tín hiệu đi qua vị trí mà hook được đặt. Vì vậy, việc khai báo một Flux rồi không subscribe hoặc không có subscriber nào khác kích hoạt nó sẽ không làm các hook của pipeline đó chạy.

Các hook thường không thay thế xử lý nghiệp vụ. Chúng phù hợp để quan sát và ghi nhận. Nếu cần biến đổi giá trị, hãy dùng toán tử biến đổi; nếu cần khôi phục từ lỗi, hãy dùng các toán tử xử lý lỗi như onErrorResume hoặc onErrorReturn.

Các đoạn mã dưới đây minh họa cách dùng Reactor. Những tên như log, customerRepository, Customer và remoteSource đại diện cho logger hoặc thành phần thuộc ứng dụng; hãy thay bằng kiểu và bean thực tế của dự án.

## 2. Quan sát lúc đăng ký và lúc có yêu cầu dữ liệu

### doOnSubscribe: khi Subscription đi qua pipeline

doOnSubscribe nhận Subscription tại vị trí hook khi một subscriber đăng ký:

~~~java
Flux<Integer> source =
    Flux.range(1, 3)
        .doOnSubscribe(subscription ->
            log.info("Có subscription mới: {}", subscription)
        );
~~~

Hook này hữu ích để đếm số lần đăng ký, gắn thông tin trace hoặc ghi nhận một lượt tiêu thụ mới. Nó không phải là nơi phù hợp để xử lý từng phần tử vì chỉ liên quan đến sự kiện đăng ký.

Một Publisher có thể được subscribe nhiều lần. Với nguồn lạnh như Flux.range, mỗi subscription thường khởi tạo một lượt thực thi mới và hook doOnSubscribe tương ứng được gọi cho lượt đó. Nếu một toán tử như retry làm upstream được đăng ký lại, hook nằm phía upstream của retry có thể chạy lại theo từng lần thử.

Không nên kết luận rằng doOnSubscribe luôn chỉ chạy một lần trong toàn bộ vòng đời của đối tượng Flux. Số lần chạy phụ thuộc vào số subscription thực tế và vị trí của hook so với các toán tử có thể đăng ký lại upstream.

### doOnRequest: quan sát demand

doOnRequest được gọi khi vị trí đó nhận một yêu cầu dữ liệu từ phía downstream:

~~~java
Flux<Integer> source =
    Flux.range(1, 10)
        .doOnRequest(n -> log.info("Demand nhận được: {}", n));
~~~

Tham số n là số phần tử được yêu cầu trong lần request đó. Mỗi lần request có thể được quan sát riêng; nhiều yêu cầu tạo thành demand tích lũy theo hợp đồng Subscription. Nếu subscriber yêu cầu Long.MAX_VALUE, đó là yêu cầu không giới hạn.

Cần phân biệt demand ở subscriber cuối với request mà từng toán tử trung gian gửi upstream. Các toán tử có thể yêu cầu trước (prefetch), lưu đệm hoặc điều chỉnh nhu cầu để thực hiện công việc. Do đó, doOnRequest đặt ở các vị trí khác nhau có thể ghi nhận các giá trị khác nhau.

Ví dụ sau chủ động điều khiển demand bằng BaseSubscriber:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

Flux.range(1, 5)
    .doOnRequest(n -> log.info("Nguồn nhận request: {}", n))
    .subscribe(new BaseSubscriber<Integer>() {
        @Override
        protected void hookOnSubscribe(Subscription subscription) {
            request(2);
        }

        @Override
        protected void hookOnNext(Integer value) {
            log.info("Đã xử lý {}", value);
            request(1);
        }
    });
~~~

Subscriber yêu cầu hai phần tử ban đầu, sau đó yêu cầu thêm một phần tử sau mỗi lần xử lý. Hook doOnRequest giúp quan sát các lần yêu cầu tại điểm đặt hook. Trong ví dụ này, nguồn hữu hạn có năm phần tử nên subscription hoàn tất sau khi tất cả phần tử được tiêu thụ.

Nếu dùng overload subscribe với Consumer đơn giản, Reactor thường yêu cầu dữ liệu không giới hạn. Khi cần học hoặc đo backpressure, hãy dùng BaseSubscriber hoặc StepVerifier với initial request được kiểm soát để quan sát demand có ý nghĩa.

## 3. Quan sát các phần tử được phát

### doOnNext: trước khi onNext đi xuống

doOnNext chạy khi một phần tử được phát tại vị trí của hook. Hành động phụ được thực hiện trước khi tín hiệu onNext tương ứng được truyền tiếp xuống downstream:

~~~java
Flux<Integer> result =
    Flux.range(1, 3)
        .doOnNext(value -> log.info("Nhận từ nguồn: {}", value))
        .map(value -> value * 10)
        .doOnNext(value -> log.info("Giá trị sau biến đổi: {}", value));
~~~

Hook đầu tiên ghi nhận giá trị từ nguồn. Hook thứ hai ghi nhận giá trị sau map. Điều này giúp đặt metrics hoặc log ở ranh giới cụ thể: trước khi biến đổi, sau khi lọc, hoặc sau khi kết hợp dữ liệu.

doOnNext không làm thay đổi phần tử được phát. Nếu cần sửa giá trị, dùng map; nếu cần bỏ phần tử theo điều kiện, dùng filter. Tránh dùng hook để âm thầm thay đổi trạng thái nghiệp vụ, vì điều đó làm pipeline khó hiểu và khó kiểm thử.

### doOnEach: quan sát tín hiệu dưới dạng Signal

doOnEach cho phép nhận một đối tượng Signal đại diện cho tín hiệu mà pipeline phát ra. Nó hữu ích khi muốn gom việc quan sát onNext, onError và onComplete vào cùng một điểm:

~~~java
Flux<String> names =
    Flux.just("An", "Bình")
        .doOnEach(signal -> {
            if (signal.isOnNext()) {
                log.info("Giá trị: {}", signal.get());
            } else if (signal.isOnError()) {
                log.error("Luồng lỗi", signal.getThrowable());
            } else if (signal.isOnComplete()) {
                log.info("Nguồn hoàn tất");
            }
        });
~~~

Signal cung cấp loại tín hiệu và dữ liệu tương ứng. Chỉ gọi get() khi Signal là onNext; chỉ đọc getThrowable() khi Signal là onError. Tín hiệu hoàn tất không có phần tử dữ liệu. Không nên giả định mọi Signal đều chứa giá trị.

Signal cũng có thể cung cấp ContextView của Reactor để quan sát dữ liệu ngữ cảnh gắn với subscription, chẳng hạn correlation ID. Context thuộc về subscription và có quy tắc truyền riêng; nó không phải một biến ThreadLocal thông thường. Khi ghi log hoặc tracing, hãy đọc context ở đúng vị trí và tránh đưa dữ liệu nhạy cảm vào log.

## 4. Quan sát lỗi và hoàn tất

Một pipeline có thể kết thúc bình thường bằng onComplete hoặc kết thúc bất thường bằng onError. Hai tín hiệu này loại trừ nhau cho một subscription.

### doOnError: ghi nhận lỗi trước khi truyền tiếp

doOnError chạy khi pipeline gặp lỗi tại vị trí hook. Nó phù hợp để ghi log, tăng bộ đếm lỗi hoặc gắn thông tin chẩn đoán:

~~~java
Mono<Customer> customer =
    customerRepository.findById(customerId)
        .doOnError(error ->
            log.error("Không tải được khách hàng {}", customerId, error)
        );
~~~

doOnError chỉ quan sát lỗi. Nó không biến lỗi thành kết quả thành công và không khôi phục pipeline. Lỗi vẫn tiếp tục đi xuống downstream nếu không có toán tử xử lý lỗi khác.

Nếu muốn chuyển sang giá trị mặc định hoặc nguồn dự phòng, hãy dùng toán tử phục hồi:

~~~java
Mono<Customer> customer =
    customerRepository.findById(customerId)
        .doOnError(error -> log.warn("Dùng dữ liệu dự phòng", error))
        .onErrorResume(error -> customerCache.findById(customerId));
~~~

Hook ghi nhận lỗi ban đầu. onErrorResume quyết định thay thế nhánh lỗi bằng một Publisher khác. Nếu Publisher dự phòng thành công, subscriber cuối có thể nhận giá trị dự phòng và onComplete thay vì nhận onError ban đầu.

### doOnComplete: quan sát hoàn tất bình thường của Flux

doOnComplete được gọi khi Flux hoàn tất bình thường, trước khi tín hiệu hoàn tất được truyền xuống downstream:

~~~java
Flux<Integer> values =
    Flux.range(1, 3)
        .doOnComplete(() -> log.info("Đã phát hết dữ liệu"));
~~~

Hook này không chạy khi luồng kết thúc bằng lỗi và cũng không chạy chỉ vì subscriber hủy subscription. Nó phù hợp để ghi nhận một lượt xử lý hoàn tất bình thường.

Với Mono, thường dùng doOnSuccess để quan sát hoàn tất thành công. Consumer của doOnSuccess nhận giá trị nếu Mono phát một phần tử; nếu Mono hoàn tất rỗng, tham số được truyền là null. Giá trị null này chỉ là cách biểu diễn trạng thái rỗng trong callback doOnSuccess, không phải một phần tử null được phát qua onNext.

~~~java
Mono<Customer> customer =
    customerRepository.findById(customerId)
        .doOnSuccess(value -> {
            if (value == null) {
                log.info("Không tìm thấy khách hàng");
            } else {
                log.info("Đã tải khách hàng {}", value.id());
            }
        });
~~~

### doAfterTerminate: sau khi tín hiệu kết thúc đã đi xuống

doAfterTerminate chạy sau khi tín hiệu onComplete hoặc onError đã được truyền xuống subscriber:

~~~java
Flux<Integer> values =
    Flux.range(1, 3)
        .doAfterTerminate(() -> log.info("Tín hiệu kết thúc đã được truyền xuống"));
~~~

Tên gọi nhấn mạnh thời điểm sau khi kết thúc đã được chuyển tiếp. Hook này không được gọi khi subscription chỉ bị cancel. Vì vậy, nếu cần quan sát cả hoàn tất, lỗi và hủy, doFinally phù hợp hơn.

## 5. doFinally: quan sát mọi kiểu kết thúc

doFinally là hook tổng quát để quan sát trạng thái kết thúc của một subscription. Callback nhận SignalType, cho biết chuỗi kết thúc bằng onComplete, onError hay cancel:

~~~java
Flux<Integer> values =
    Flux.range(1, 10)
        .doFinally(signalType ->
            log.info("Subscription kết thúc với {}", signalType)
        );
~~~

Các loại thường cần phân biệt:

| SignalType | Ý nghĩa |
|---|---|
| ON_COMPLETE | Nguồn hoàn tất bình thường |
| ON_ERROR | Nguồn kết thúc do lỗi |
| CANCEL | Downstream hủy subscription |

doFinally chạy sau khi tín hiệu kết thúc đã được truyền xuống downstream. Với trường hợp cancel, hook được gọi sau khi thao tác hủy được thực hiện tại vị trí đó. Điều này khiến doFinally hữu ích để dừng bộ đếm thời gian, kết thúc span tracing hoặc ghi nhận kết quả cuối của một lượt tiêu thụ.

Ví dụ, đo thời gian một subscription tồn tại:

~~~java
AtomicLong startedAt = new AtomicLong();

Flux<Integer> measured =
    Flux.range(1, 100)
        .doOnSubscribe(subscription -> startedAt.set(System.nanoTime()))
        .doFinally(signalType -> {
            long elapsed = System.nanoTime() - startedAt.get();
            log.info("Kết thúc với {}, thời gian {} ns", signalType, elapsed);
        });
~~~

Ví dụ minh họa cách đo đơn giản cho một subscription. Nếu cùng một đối tượng Publisher được nhiều subscriber dùng đồng thời, không nên lưu thời điểm bắt đầu vào một AtomicLong dùng chung như trên vì các subscription có thể ghi đè dữ liệu của nhau. Hãy tạo trạng thái riêng cho từng subscription, chẳng hạn dùng Flux.defer hoặc Mono.defer để khởi tạo biến đo trong mỗi lượt đăng ký.

doFinally là hook quan sát. Nếu cần quản lý vòng đời một tài nguyên gắn với publisher, hãy cân nhắc các toán tử chuyên dụng như using hoặc usingWhen để việc cấp phát và giải phóng được gắn với subscription, hoàn tất, lỗi và hủy theo đúng hợp đồng tài nguyên.

## 6. So sánh các hook theo thời điểm

Bảng sau giúp chọn hook theo sự kiện cần quan sát:

| Nhu cầu | Hook phù hợp | Thời điểm và giới hạn |
|---|---|---|
| Đếm lượt đăng ký | doOnSubscribe | Khi Subscription đi qua vị trí hook |
| Theo dõi lượng dữ liệu được yêu cầu | doOnRequest | Khi request đi qua vị trí hook |
| Ghi nhận mỗi phần tử | doOnNext | Khi phần tử đến hook, trước khi onNext đi xuống |
| Quan sát nhiều loại tín hiệu | doOnEach | Khi onNext, onError hoặc onComplete đi qua hook |
| Ghi log lỗi | doOnError | Trước khi onError được truyền xuống |
| Ghi nhận Flux hoàn tất bình thường | doOnComplete | Trước khi onComplete được truyền xuống |
| Ghi nhận Mono thành công | doOnSuccess | Khi Mono thành công; giá trị null nếu hoàn tất rỗng |
| Hành động sau complete hoặc error | doAfterTerminate | Sau khi tín hiệu kết thúc được truyền xuống; không bao gồm cancel |
| Ghi nhận việc hủy | doOnCancel | Khi downstream hủy subscription |
| Ghi nhận mọi kiểu kết thúc | doFinally | Sau complete, error hoặc cancel; nhận SignalType |

Một số hook có tên gần nhau nhưng thời điểm khác nhau. doOnComplete và doOnError chạy trước khi tín hiệu kết thúc đi xuống. doAfterTerminate chạy sau khi tín hiệu complete hoặc error đã đi xuống. doFinally cũng chạy sau khi kết thúc nhưng còn nhận biết được cancel. Chọn sai hook có thể làm metrics thiếu lượt hủy hoặc ghi nhận thời gian trước khi downstream hoàn tất xử lý tín hiệu.

## 7. Vị trí hook quyết định phạm vi quan sát

Mỗi hook chỉ quan sát tín hiệu tại vị trí được đặt trong chuỗi. Hãy xem ví dụ:

~~~java
Flux<Integer> pipeline =
    Flux.range(1, 3)
        .doOnNext(value -> log.info("A - nguồn: {}", value))
        .map(value -> value * 10)
        .doOnNext(value -> log.info("B - sau map: {}", value))
        .filter(value -> value >= 20)
        .doOnNext(value -> log.info("C - sau filter: {}", value));
~~~

Kết quả quan sát:

| Điểm móc | Giá trị được quan sát |
|---|---|
| A - trước map | 1, 2, 3 |
| B - sau map | 10, 20, 30 |
| C - sau filter | 20, 30 |

Hook A nhìn thấy cả ba phần tử nguồn. Hook B nhìn thấy giá trị đã nhân mười. Hook C chỉ nhìn thấy các phần tử vượt qua filter. Khi điều tra dữ liệu bị mất hoặc bị biến đổi ngoài dự kiến, đặt hook ở hai phía của toán tử nghi vấn sẽ giúp xác định ranh giới thay đổi.

Với request, luồng tín hiệu điều khiển đi theo hướng ngược với dữ liệu: request được truyền từ downstream lên upstream. Vì thế, vị trí doOnRequest cũng có ý nghĩa. Một hook đặt trước publishOn hoặc flatMap có thể quan sát demand khác hook đặt sau chúng do các toán tử có thể prefetch hoặc điều chỉnh số lượng yêu cầu.

## 8. Retry và nhiều lượt đăng ký

retry có thể tạo thêm subscription đến phần upstream để thử lại khi gặp lỗi. Vị trí hook quyết định nó quan sát từng lần thử hay toàn bộ lượt tiêu thụ bên ngoài:

~~~java
Flux<Integer> retried =
    remoteSource()
        .doOnSubscribe(s -> log.info("Đăng ký upstream"))
        .doOnError(error -> log.warn("Một lượt upstream gặp lỗi", error))
        .retry(2)
        .doOnSubscribe(s -> log.info("Subscriber đăng ký pipeline retry"));
~~~

Hook đặt trước retry nằm trong phần upstream mà retry đăng ký lại, nên có thể được gọi ở mỗi lần thử. Hook đặt sau retry quan sát subscription của pipeline bên ngoài. Khi đọc log, cần phân biệt số lần đăng ký upstream với số lượt subscriber cuối đăng ký.

Tương tự, doFinally đặt trước retry có thể quan sát kết thúc của từng lượt upstream, bao gồm lỗi khiến retry thực hiện lại. doFinally đặt sau retry quan sát kết quả cuối của pipeline sau khi retry đã hết hoặc thành công. Nếu không xác định vị trí, metrics số lượt hoàn tất và số lỗi có thể bị đếm khác với điều mà người vận hành mong đợi.

## 9. Giữ hook nhẹ và an toàn

Hook chạy trên luồng thực thi mà pipeline đang dùng tại thời điểm tín hiệu đi qua. Vì vậy, hành động phụ trong hook cần nhanh, không chặn và không tạo thêm độ trễ đáng kể.

Một số nguyên tắc thực tế:

- Dùng logger và bộ đếm metrics có chi phí thấp; tránh gọi HTTP hoặc truy vấn cơ sở dữ liệu đồng bộ ngay trong doOnNext.
- Không dùng hook để thực hiện công việc nghiệp vụ bắt buộc mà kết quả phụ thuộc vào việc hook có chạy hay không. Hook là công cụ quan sát, còn nghiệp vụ nên nằm trong các toán tử xử lý dữ liệu.
- Không ném exception từ callback hook. Lỗi phát sinh trong side effect có thể làm thay đổi kết quả pipeline và che khuất lỗi gốc.
- Không giữ trạng thái mutable dùng chung cho nhiều subscription nếu chưa có đồng bộ. Dùng defer để tạo trạng thái riêng theo từng lượt đăng ký.
- Không giả định cancel sẽ gọi doOnComplete hoặc doAfterTerminate. Dùng doOnCancel hoặc doFinally để ghi nhận hủy.
- Không ghi dữ liệu cá nhân, token hoặc nội dung nhạy cảm vào log chỉ vì hook có thể nhìn thấy phần tử.

Ví dụ tạo đồng hồ riêng cho mỗi subscription:

~~~java
Flux<Long> measured =
    Flux.defer(() -> {
        AtomicLong startedAt = new AtomicLong();

        return Flux.interval(Duration.ofMillis(100))
            .doOnSubscribe(subscription ->
                startedAt.set(System.nanoTime())
            )
            .doFinally(signalType -> {
                long elapsed = System.nanoTime() - startedAt.get();
                log.info("Lượt đăng ký kết thúc: {}, {} ns",
                    signalType, elapsed);
            });
    });
~~~

Mỗi lần subscribe, defer tạo một AtomicLong mới. Các subscriber độc lập vì vậy không ghi đè mốc thời gian của nhau. Flux.interval là nguồn vô hạn; khi muốn kết thúc ví dụ, downstream có thể dùng take hoặc cancel.

## 10. Kiểm thử hành vi hook

Hook là một phần hành vi quan sát được của pipeline, nên có thể kiểm thử bằng cách ghi nhận số lần gọi hoặc loại tín hiệu. StepVerifier cho phép điều khiển demand và hủy subscription một cách xác định.

### Kiểm thử hook theo dõi phần tử

~~~java
AtomicInteger observed = new AtomicInteger();

Flux<Integer> source =
    Flux.range(1, 3)
        .doOnNext(value -> observed.incrementAndGet());

StepVerifier.create(source)
    .expectNext(1, 2, 3)
    .verifyComplete();

assertEquals(3, observed.get());
~~~

Kiểm thử xác nhận pipeline phát ba phần tử và hook được gọi ba lần.

### Kiểm thử hook nhận biết hủy

~~~java
AtomicReference<SignalType> finalSignal = new AtomicReference<>();

Flux<Integer> source =
    Flux.range(1, 5)
        .doFinally(finalSignal::set);

StepVerifier.create(source)
    .expectNext(1)
    .thenCancel()
    .verify();

assertEquals(SignalType.CANCEL, finalSignal.get());
~~~

Sau khi nhận phần tử đầu tiên, StepVerifier hủy subscription. doFinally ghi nhận SignalType.CANCEL. Kiểm thử này giúp phát hiện trường hợp dùng doOnComplete để đếm tất cả lượt kết thúc, dẫn đến bỏ sót các lượt bị hủy.

### Kiểm thử demand

~~~java
AtomicLong requested = new AtomicLong();

Flux<Integer> source =
    Flux.range(1, 3)
        .doOnRequest(requested::addAndGet);

StepVerifier.create(source, 0)
    .thenRequest(2)
    .expectNext(1, 2)
    .thenCancel()
    .verify();

assertEquals(2L, requested.get());
~~~

Trong ví dụ nguồn đồng bộ đơn giản này, subscriber bắt đầu với demand bằng không, sau đó yêu cầu hai phần tử rồi hủy. Hook ở nguồn ghi nhận lượng request được gửi đến vị trí đó. Với pipeline có toán tử prefetch hoặc điều chỉnh demand, giá trị quan sát có thể khác lượng request mà StepVerifier gửi; khi kiểm thử, hãy đặt hook ở đúng ranh giới cần xác nhận.

## 11. Bài tập vận dụng

Một API trả về Flux<Order> từ dịch vụ đơn hàng. Pipeline lọc đơn đã hủy, chuyển đổi dữ liệu sang OrderSummary, rồi gửi kết quả đến subscriber HTTP. Đội vận hành cần theo dõi số lượt đăng ký, số phần tử đi qua từng bước, lỗi từ dịch vụ, thời điểm hoàn tất và lượt hủy khi client ngắt kết nối.

Hãy thiết kế vị trí các hook và giải thích lựa chọn:

1. Đặt doOnSubscribe ở đâu để đếm lượt đăng ký vào pipeline?
2. Đặt doOnNext trước và sau filter/map thế nào để phân biệt số đơn nhận từ nguồn, số đơn còn lại và số OrderSummary được tạo?
3. Dùng doOnError để ghi nhận lỗi nguồn. Nếu nghiệp vụ có thể trả về danh sách rỗng khi dịch vụ lỗi, dùng toán tử nào để phục hồi?
4. Dùng doOnComplete để đếm lượt hoàn tất bình thường và doFinally để ghi nhận cả ON_COMPLETE, ON_ERROR lẫn CANCEL.
5. Đặt doOnRequest ở vị trí nào để quan sát demand từ subscriber HTTP? Những toán tử nào ở giữa có thể làm thay đổi lượng request quan sát được?
6. Viết một kiểm thử StepVerifier xác nhận hook doFinally nhận CANCEL khi client hủy sau một phần tử.

Một thiết kế tốt phải phân biệt rõ dữ liệu đi qua pipeline, demand được truyền ngược lên nguồn và trạng thái kết thúc của subscription. Hãy giữ hook ngắn, đặt chúng tại ranh giới cần quan sát và kiểm thử cả trường hợp hoàn tất, lỗi lẫn hủy.

## Kết luận

Các hook của Reactor cho phép quan sát vòng đời một pipeline tại những điểm cụ thể. doOnSubscribe và doOnRequest theo dõi đăng ký cùng nhu cầu; doOnNext và doOnEach quan sát dữ liệu và tín hiệu; doOnError, doOnComplete ghi nhận hai kiểu kết thúc; doAfterTerminate chạy sau complete hoặc error; doFinally còn bao gồm cancel. Khi đặt hook đúng vị trí, hiểu thứ tự truyền tín hiệu và giữ side effect nhẹ, bạn có thể xây dựng logging, metrics và tracing đáng tin cậy mà vẫn giữ được luồng xử lý reactive rõ ràng.

# Sự kiện rời rạc và giá trị biến thiên theo thời gian

Lập trình phản ứng hàm (Functional Reactive Programming, FRP) mô tả cách dữ liệu và phép tính thay đổi theo thời gian. Một hệ thống có thể nhận những sự kiện rời rạc như lần nhấn nút, đơn hàng được tạo hoặc số đo cảm biến mới; đồng thời duy trì những giá trị luôn có ý nghĩa tại thời điểm hiện tại như trạng thái đơn hàng, nhiệt độ mới nhất hoặc số dư tài khoản. Hai khái niệm này liên quan nhưng không giống nhau: sự kiện là một lần xảy ra, còn giá trị biến thiên theo thời gian mô tả trạng thái hoặc kết quả tại những thời điểm khác nhau.

Trong Java Reactive Programming, Reactor cung cấp Mono và Flux để biểu diễn các kết quả bất đồng bộ và chuỗi tín hiệu. Flux thường được dùng cho một chuỗi sự kiện hoặc các lần cập nhật trạng thái. Tuy nhiên, Flux tự nó không phải một ô trạng thái luôn chứa giá trị hiện tại. Nếu consumer đăng ký muộn và cần biết trạng thái mới nhất, ứng dụng phải xác định cách tạo snapshot, tích lũy trạng thái hoặc replay giá trị gần nhất. Hiểu ranh giới này giúp thiết kế pipeline dễ dự đoán và tránh nhầm lẫn giữa lịch sử sự kiện với trạng thái hiện tại.

## 1. Sự kiện rời rạc là một lần xảy ra

Sự kiện (event) biểu diễn một việc đã xảy ra tại một thời điểm. Ví dụ:

- Người dùng nhấn nút gửi biểu mẫu.
- Một đơn hàng chuyển sang trạng thái đã thanh toán.
- Một cảm biến gửi số đo mới.
- Một message được nhận từ broker.
- Một request hoàn tất hoặc thất bại.

Mỗi sự kiện thường có dữ liệu mô tả điều đã xảy ra, có thể kèm mã định danh, thời điểm và nguồn phát. Sự kiện thường được xem là dữ kiện bất biến: nếu một đơn hàng đã được tạo, việc trạng thái hiện tại của đơn hàng thay đổi không làm cho sự kiện OrderCreated trong quá khứ biến thành một sự kiện khác.

Trong Reactor, một chuỗi sự kiện có thể được biểu diễn bằng Flux:

~~~java
record OrderCreated(String orderId, Instant occurredAt) {}

Flux<OrderCreated> orderEvents = eventSource.orderCreated();
~~~

Mỗi phần tử mà publisher phát là một lần xảy ra riêng. Flux có thể phát không phần tử nào, một số hữu hạn phần tử hoặc tiếp tục phát trong thời gian dài. Các tín hiệu được tiêu thụ theo thứ tự mà publisher phát ra; nếu nguồn có nhiều producer hoặc xử lý đồng thời, thứ tự đó không nhất thiết trùng với thứ tự thời gian nghiệp vụ nếu nguồn không bảo đảm.

Sự kiện rời rạc thường phù hợp với những câu hỏi như:

- Điều gì đã xảy ra?
- Sự kiện nào đến tiếp theo?
- Có bao nhiêu lần một hành động được thực hiện?
- Có sự kiện nào cần kích hoạt một quy trình?

Một luồng sự kiện không tự động cho biết trạng thái hiện tại của thực thể. Nếu consumer chỉ đăng ký từ thời điểm hiện tại, nó có thể bỏ lỡ sự kiện đã phát trước đó. Nếu cần dựng trạng thái từ đầu, consumer cần lịch sử đủ đầy, snapshot ban đầu hoặc một nguồn có khả năng replay.

## 2. Giá trị biến thiên theo thời gian mô tả trạng thái

Một giá trị biến thiên theo thời gian (time-varying value) mô tả một đại lượng có thể thay đổi theo thời gian. Ví dụ:

- Nhiệt độ hiện tại của một thiết bị.
- Số dư hiện tại của tài khoản.
- Số lượng sản phẩm còn trong kho.
- Trạng thái hiện tại của một đơn hàng.
- Tốc độ hiện tại của một phương tiện.

Khác với event, trạng thái thường trả lời câu hỏi “giá trị hiện tại là bao nhiêu?”. Nó có thể được cập nhật bởi nhiều sự kiện trong quá khứ. Ví dụ, trạng thái số dư được hình thành từ số dư ban đầu và các giao dịch cộng/trừ.

Trong FRP cổ điển, một số tài liệu phân biệt:

- **Event:** một tập hợp các lần xảy ra rời rạc tại những thời điểm cụ thể.
- **Behavior hoặc Signal:** một giá trị được xác định theo thời gian; trong mô hình toán học, nó có thể được xem là một hàm từ thời gian sang giá trị.

Các thư viện hiện đại dùng thuật ngữ không hoàn toàn giống nhau. Trong Reactor, Flux biểu diễn chuỗi tín hiệu rời rạc. Một Flux phát các snapshot nhiệt độ có thể được dùng để mô hình hóa các lần cập nhật của một giá trị biến thiên, nhưng nó không tự cung cấp một phép đọc đồng bộ giá trị hiện tại ở mọi thời điểm, cũng không nội suy giá trị giữa hai lần phát. Nếu ứng dụng coi giá trị cuối cùng vẫn có hiệu lực cho đến khi có cập nhật mới, đó là một quy tắc trạng thái do ứng dụng xác định.

Ví dụ một nguồn nhiệt độ phát các snapshot:

~~~java
record Temperature(double celsius, Instant measuredAt) {}

Flux<Temperature> temperatureUpdates = sensor.temperatureReadings();
~~~

Mỗi phần tử là một lần cập nhật. Consumer có thể giữ giá trị gần nhất để hiển thị nhiệt độ hiện tại. Nhưng nếu consumer đăng ký sau khi nguồn đã phát nhiều phần tử, nó chỉ nhận dữ liệu theo semantics của publisher. Muốn consumer mới có snapshot gần nhất ngay khi đăng ký, nguồn cần hỗ trợ replay hoặc ứng dụng cần đọc snapshot từ một nơi lưu trạng thái.

## 3. Đừng nhầm luồng sự kiện với luồng trạng thái

Một luồng sự kiện và một luồng trạng thái có thể cùng dùng Flux nhưng biểu diễn ý nghĩa khác nhau.

| Tiêu chí | Luồng sự kiện | Luồng cập nhật trạng thái |
| --- | --- | --- |
| Ý nghĩa mỗi phần tử | Một việc vừa xảy ra | Một snapshot hoặc giá trị mới |
| Ví dụ | OrderPaid, ButtonClicked, PaymentFailed | OrderState, CurrentTemperature, AccountBalance |
| Có thể bỏ phần tử không? | Thường không, nếu cần lịch sử đầy đủ | Có thể bỏ snapshot trung gian nếu chỉ cần giá trị mới nhất |
| Consumer đến muộn | Có thể cần replay lịch sử hoặc offset | Thường cần snapshot hiện tại hoặc replay giá trị mới nhất |
| Cách tích lũy | Dùng sự kiện để dựng trạng thái | Giá trị mới thường đã là trạng thái sau cập nhật |

Ví dụ, một luồng giao dịch có thể phát:

~~~text
Deposited(100) -> Withdrawn(30) -> Deposited(20)
~~~

Đây là các sự kiện. Trạng thái số dư được tính bằng cách áp dụng lần lượt các sự kiện:

~~~text
100 -> 70 -> 90
~~~

Nếu chỉ giữ giá trị mới nhất là 90, ứng dụng có trạng thái hiện tại nhưng không còn toàn bộ lịch sử để giải thích vì sao số dư thành 90. Nếu chỉ giữ sự kiện, consumer phải có số dư ban đầu và áp dụng lại các sự kiện theo đúng thứ tự để dựng trạng thái. Hệ thống thường cần quyết định có lưu cả event log và snapshot hay không.

## 4. Dùng scan để biến chuỗi sự kiện thành chuỗi trạng thái

Một cách phổ biến để dựng trạng thái từ sự kiện là dùng toán tử scan. Scan giữ một accumulator và phát ra giá trị tích lũy sau mỗi phần tử. Với một accumulator bất biến, mỗi sự kiện tạo ra một trạng thái mới mà không sửa trạng thái trước đó.

Ví dụ bộ đếm được cập nhật bởi các sự kiện tăng hoặc giảm:

~~~java
record CounterEvent(long delta, Instant occurredAt) {}

record CounterState(long value, Instant updatedAt) {
    CounterState apply(CounterEvent event) {
        return new CounterState(
            value + event.delta(),
            event.occurredAt()
        );
    }
}

CounterState initial = new CounterState(0, Instant.EPOCH);

Flux<CounterState> states = counterEvents
    .scan(initial, CounterState::apply);
~~~

Nếu các sự kiện lần lượt có delta là +1, +1 và -1, chuỗi trạng thái gồm trạng thái ban đầu rồi các trạng thái có giá trị 1, 2 và 1. Scan phát các trạng thái trung gian; consumer có thể quan sát cách trạng thái thay đổi qua từng event.

Điểm quan trọng là hàm apply trả về một CounterState mới. Nó không thay đổi một đối tượng mutable được dùng chung. Cách viết bất biến giúp mỗi trạng thái có ý nghĩa rõ ràng, dễ kiểm thử và ít gặp race condition khi nhiều consumer quan sát cùng một pipeline.

### Scan khác reduce

scan phát ra accumulator sau từng phần tử, còn reduce chỉ phát kết quả tích lũy cuối cùng khi nguồn hoàn tất.

~~~java
Flux<Long> runningTotals = Flux.just(5L, 3L, -2L)
    .scan(0L, Long::sum);

Mono<Long> finalTotal = Flux.just(5L, 3L, -2L)
    .reduce(0L, Long::sum);
~~~

runningTotals phát 0, 5, 8, 6 vì scan có seed và phát trạng thái ban đầu cùng các giá trị tích lũy. finalTotal chỉ phát 6 khi nguồn hoàn tất. Nếu nguồn là luồng vô hạn, reduce không phát kết quả cuối cùng cho đến khi nguồn kết thúc; scan vẫn có thể phát trạng thái mới khi từng event đến.

## 5. Kết hợp các trạng thái mới nhất

Một giá trị trạng thái thường phụ thuộc vào nhiều nguồn cập nhật độc lập. Ví dụ, dashboard môi trường cần nhiệt độ và độ ẩm mới nhất. Mỗi nguồn phát snapshot riêng; khi một trong hai thay đổi, ứng dụng cần tạo snapshot kết hợp từ giá trị mới của nguồn đó và giá trị gần nhất của nguồn còn lại.

~~~java
Flux<ClimateSnapshot> climate = Flux.combineLatest(
    temperatureUpdates,
    humidityUpdates,
    ClimateSnapshot::new
);
~~~

combineLatest chờ mỗi nguồn phát ít nhất một giá trị. Sau đó, mỗi lần một nguồn phát giá trị mới, toán tử kết hợp giá trị mới đó với giá trị gần nhất từ các nguồn còn lại. Đây là cách mô hình hóa trạng thái tổng hợp.

Không nên dùng zip cho bài toán này nếu các nguồn cập nhật độc lập. zip ghép phần tử thứ n của nguồn này với phần tử thứ n của nguồn kia. Nếu nhiệt độ phát ba lần trong khi độ ẩm chỉ phát một lần, zip chờ các phần tử độ ẩm tương ứng; combineLatest có thể tạo nhiều snapshot dùng cùng giá trị độ ẩm gần nhất.

Nếu một nguồn chưa phát giá trị ban đầu, combineLatest chưa thể tạo snapshot đầy đủ. Có thể cung cấp giá trị khởi tạo hợp lệ, đọc snapshot từ kho trạng thái hoặc dùng publisher đảm bảo phát giá trị ban đầu. Không dùng giá trị giả tùy tiện nếu nó có thể bị hiểu là số đo thật.

## 6. Giữ giá trị mới nhất cho consumer đến muộn

Một nguồn hot có thể phát trạng thái mới trước khi consumer đăng ký. Nếu consumer mới cần biết trạng thái hiện tại ngay khi bắt đầu, một multicast stream không replay có thể không đủ. Reactor có thể dùng replay sink chỉ giữ giá trị mới nhất:

~~~java
Sinks.Many<Temperature> stateSink = Sinks.many()
    .replay()
    .latest();

stateSink.tryEmitNext(initialTemperature).orThrow();

Flux<Temperature> currentTemperature = stateSink.asFlux();
~~~

Khi ứng dụng phát một nhiệt độ mới vào sink, subscriber hiện tại nhận cập nhật; subscriber đăng ký sau có thể nhận giá trị gần nhất đã lưu. Ví dụ giả định producer phát tuần tự và xử lý kết quả emission rõ ràng. Trong ứng dụng đa luồng, cần xử lý các kết quả tryEmitNext như FAIL_NON_SERIALIZED hoặc dùng cơ chế serialize/điều phối phù hợp.

Replay latest giữ một giá trị gần nhất, không phải toàn bộ lịch sử. Nó phù hợp với trạng thái hiện tại nhưng không thay thế event store hoặc message broker khi cần phát lại mọi sự kiện. Nếu sink chưa nhận giá trị ban đầu, subscriber mới vẫn phải chờ lần phát đầu tiên.

Một lựa chọn khác là lưu trạng thái trong một kho dữ liệu và tạo snapshot khi consumer bắt đầu. Cách này có thể phù hợp khi trạng thái phải tồn tại qua restart, cần truy vấn theo khóa hoặc cần kiểm soát quyền truy cập. Replay sink trong bộ nhớ chỉ có vòng đời của process.

## 7. Biến đổi trạng thái bằng các hàm thuần

FRP khuyến khích mô tả dữ liệu bằng các hàm biến đổi và kết hợp, thay vì thay đổi trạng thái ẩn ở nhiều vị trí. Một hàm thuần (pure function) với cùng đầu vào luôn tạo cùng đầu ra và không gây side effect bên ngoài.

Ví dụ:

~~~java
Flux<Temperature> fahrenheit = temperatureUpdates
    .map(value -> new Temperature(
        value.celsius() * 9.0 / 5.0 + 32.0,
        value.measuredAt()
    ));
~~~

Phép chuyển đổi nhiệt độ chỉ dựa trên phần tử đầu vào. Nó không ghi database, gửi message hoặc thay đổi biến dùng chung. Điều này làm mapper dễ kiểm thử và giúp pipeline có thể được compose lại.

Một cách viết khó dự đoán hơn là thay đổi một biến mutable bên trong mapper:

~~~java
AtomicLong total = new AtomicLong();

Flux<Long> totals = payments.map(payment ->
    total.addAndGet(payment.amountInCents())
);
~~~

Kết quả phụ thuộc vào thứ tự và số lần subscription. Nếu pipeline được subscribe hai lần, biến total vẫn giữ giá trị từ lần đầu; nếu có nhiều subscription đồng thời, chúng cùng sửa một trạng thái. Hãy dùng scan với accumulator bất biến nếu cần tạo chuỗi trạng thái riêng cho từng subscription:

~~~java
Flux<Long> totals = payments
    .scan(0L, (sum, payment) ->
        sum + payment.amountInCents()
    );
~~~

Các side effect vẫn có chỗ đứng trong hệ thống reactive, nhưng nên đặt ở ranh giới phù hợp và có chính sách retry, lỗi, cancellation rõ ràng. Không dùng mapper để âm thầm ghi dữ liệu hoặc gửi request.

## 8. Thời gian là một phần của dữ liệu

Khi mô hình hóa giá trị biến thiên theo thời gian, cần xác định timestamp có ý nghĩa gì. Một event có thể chứa:

- **Event time:** thời điểm sự kiện thực sự xảy ra tại nguồn.
- **Arrival time:** thời điểm sự kiện đến adapter hoặc ứng dụng.
- **Processing time:** thời điểm pipeline xử lý sự kiện.

Ba thời điểm có thể khác nhau. Ví dụ, thiết bị ghi nhận nhiệt độ lúc 10:00:00 nhưng mất mạng và gửi dữ liệu lúc 10:00:08. Nếu hệ thống nhóm theo processing time, số đo có thể được tính vào cửa sổ lúc 10:00:08. Nếu nghiệp vụ cần báo cáo theo thời điểm đo, cần dùng event time và chính sách xử lý sự kiện đến trễ.

Các toán tử timer như Flux.interval hoặc window(Duration) làm việc theo scheduler và thời gian xử lý của pipeline. Chúng không tự hiểu timestamp nghiệp vụ bên trong event. Reactor cung cấp công cụ để compose các luồng và timer, nhưng bài toán event-time phức tạp với watermark, late arrival và trạng thái phân tán có thể cần một stream-processing engine chuyên dụng.

Một ví dụ về tick thời gian:

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1));
~~~

Tick là những sự kiện rời rạc do scheduler phát theo chu kỳ. Chúng không phải một đồng hồ liên tục có độ chính xác thời gian thực tuyệt đối. Tải hệ thống và scheduler có thể làm thời điểm xử lý trễ; không dùng tick để thay thế một nguồn thời gian có yêu cầu chính xác hoặc đồng bộ cao.

## 9. Sampling trạng thái và đánh đổi dữ liệu

Không phải consumer nào cũng cần mọi lần cập nhật. Một biểu đồ có thể chỉ cần giá trị mới nhất mỗi 250 mili giây, trong khi bộ xử lý giao dịch cần mọi event. Reactor có thể dùng sample để phát giá trị gần nhất theo chu kỳ:

~~~java
Flux<Temperature> chartPoints = temperatureUpdates
    .sample(Duration.ofMillis(250));
~~~

Sampling phù hợp khi mục tiêu là hiển thị xu hướng hoặc giảm tần suất cập nhật giao diện. Nó có thể bỏ qua các giá trị trung gian. Nếu một cảnh báo chỉ xuất hiện trong thời gian rất ngắn giữa hai lần sample, hệ thống có thể không quan sát được nó. Với cảnh báo ngưỡng, nên phát hiện điều kiện trên luồng đầy đủ trước khi sampling dữ liệu hiển thị.

Có thể phân biệt:

- Luồng sự kiện đầy đủ dùng cho xử lý nghiệp vụ và lưu lịch sử.
- Luồng trạng thái dùng cho snapshot hoặc giá trị hiện tại.
- Luồng sample dùng cho hiển thị hoặc phân tích gần đúng.

Không nên dùng một luồng đã sample làm nguồn duy nhất nếu hệ thống cần kiểm toán, phát hiện mọi chuyển trạng thái hoặc phục hồi chính xác.

## 10. Xử lý trạng thái khởi tạo, cập nhật trùng và không thay đổi

Một luồng trạng thái thường cần quy tắc cho giá trị ban đầu. Consumer có thể đăng ký trước khi nguồn phát lần đầu; nếu không có seed hoặc snapshot, nó chưa biết trạng thái hiện tại. Các lựa chọn gồm:

- Phát một trạng thái khởi tạo hợp lệ trước các cập nhật.
- Đọc snapshot từ database hoặc state store rồi nối với stream cập nhật.
- Dùng replay latest nếu trạng thái gần nhất được giữ trong cùng process.
- Để consumer biểu diễn trạng thái “chưa biết” cho đến khi nhận giá trị đầu tiên.

Nguồn cũng có thể phát cùng một giá trị nhiều lần. Nếu cập nhật trùng không có ý nghĩa, có thể dùng distinctUntilChanged() để chỉ phát khi giá trị thay đổi:

~~~java
Flux<Temperature> meaningfulChanges = temperatureUpdates
    .distinctUntilChanged();
~~~

Toán tử so sánh theo equality mặc định của kiểu dữ liệu hoặc comparator được cung cấp. Với record, equality thường xét các thành phần của record. Nếu dữ liệu có timestamp khác nhau nhưng giá trị đo giống nhau, equality toàn record có thể vẫn xem chúng là khác nhau. Nếu chỉ muốn so sánh nhiệt độ, hãy cung cấp key selector hoặc comparator phù hợp.

Không loại bỏ cập nhật trùng nếu mỗi lần phát vẫn đại diện cho một sự kiện cần kiểm toán, heartbeat hoặc xác nhận nguồn còn hoạt động. Quyết định này phụ thuộc vào ý nghĩa dữ liệu.

## 11. Kiểm thử luồng sự kiện và trạng thái

Reactor Test cung cấp StepVerifier để xác minh thứ tự, giá trị và terminal signal. Với chuỗi sự kiện được chuyển thành trạng thái bằng scan:

~~~java
CounterState initial = new CounterState(0, Instant.EPOCH);

Flux<CounterState> states = Flux.just(
        new CounterEvent(1, Instant.parse("2026-01-01T00:00:01Z")),
        new CounterEvent(1, Instant.parse("2026-01-01T00:00:02Z")),
        new CounterEvent(-1, Instant.parse("2026-01-01T00:00:03Z"))
    )
    .scan(initial, CounterState::apply);

StepVerifier.create(states)
    .expectNext(initial)
    .expectNextMatches(state -> state.value() == 1)
    .expectNextMatches(state -> state.value() == 2)
    .expectNextMatches(state -> state.value() == 1)
    .verifyComplete();
~~~

Test xác minh trạng thái ban đầu và trạng thái sau từng sự kiện. Nếu không muốn phát seed ban đầu cho consumer, có thể bỏ phần tử đầu tiên bằng một bước rõ ràng, nhưng cần bảo đảm semantics đó phù hợp với subscriber mới.

Với nguồn thời gian, dùng virtual time thay vì chờ bằng Thread.sleep:

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1)).take(3)
    )
    .thenAwait(Duration.ofSeconds(3))
    .expectNext(0L, 1L, 2L)
    .verifyComplete();
~~~

Các test nên bao phủ:

1. Không có event và trạng thái khởi tạo.
2. Một event tạo một cập nhật trạng thái.
3. Nhiều event được áp dụng đúng thứ tự.
4. Event lỗi hoặc dữ liệu không hợp lệ được xử lý theo chính sách.
5. Subscriber đăng ký muộn nhận snapshot hay chỉ nhận cập nhật mới, tùy hợp đồng.
6. Giá trị trùng được giữ hoặc loại bỏ theo yêu cầu.
7. Sampling không bỏ lỡ điều kiện cảnh báo quan trọng vì cảnh báo được kiểm tra trên luồng đầy đủ.
8. Cancellation dừng nguồn và giải phóng listener khi API nguồn hỗ trợ.

## 12. Những lỗi thường gặp

- **Coi mỗi event là trạng thái hiện tại:** event mô tả việc đã xảy ra; cần tích lũy hoặc đọc snapshot để có trạng thái.
- **Coi Flux là một ô giá trị luôn có thể đọc:** Flux là publisher phát tín hiệu; subscriber đến muộn có thể không nhận giá trị trước đó.
- **Dùng zip cho các nguồn trạng thái cập nhật độc lập:** zip ghép theo vị trí, còn combineLatest ghép các giá trị gần nhất.
- **Dùng combineLatest cho lịch sử sự kiện cần đầy đủ:** toán tử chỉ giữ giá trị mới nhất của từng nguồn để tạo snapshot, không thay thế event log.
- **Dùng scan với accumulator mutable dùng chung:** nhiều subscription có thể chia sẻ và thay đổi cùng trạng thái; ưu tiên accumulator bất biến.
- **Dùng reduce cho luồng vô hạn khi cần cập nhật liên tục:** reduce chỉ phát kết quả khi nguồn hoàn tất; scan phát trạng thái sau từng phần tử.
- **Sampling trước khi phát hiện cảnh báo:** có thể bỏ qua một chuyển trạng thái ngắn; phát hiện điều kiện trên luồng đầy đủ trước.
- **Nhầm processing time với event time:** timer của pipeline không tự phân loại theo timestamp nghiệp vụ.
- **Replay latest thay cho lưu lịch sử bền vững:** replay trong bộ nhớ chỉ giữ giá trị theo vòng đời process và không bảo đảm phục hồi mọi event sau restart.
- **Bỏ qua trạng thái khởi tạo:** combineLatest có thể chưa phát gì cho đến khi mọi nguồn có giá trị đầu tiên.
- **Đưa side effect vào map hoặc scan:** phép biến đổi trở nên khó kiểm thử và có thể lặp khi subscribe nhiều lần.

## 13. Cách chọn mô hình dữ liệu

Trước khi xây pipeline, hãy xác định dữ liệu đang biểu diễn điều gì:

| Câu hỏi | Mô hình nên cân nhắc |
| --- | --- |
| Mỗi phần tử là một lần xảy ra cần giữ lịch sử? | Event stream |
| Mỗi phần tử là snapshot mới của một trạng thái? | State update stream |
| Trạng thái được tính từ nhiều sự kiện trước đó? | Event stream kết hợp scan và accumulator bất biến |
| Consumer mới cần biết giá trị hiện tại ngay? | Snapshot, replay latest hoặc state store |
| Cần kết hợp trạng thái mới nhất từ nhiều nguồn? | combineLatest |
| Chỉ cần một mẫu định kỳ cho biểu đồ? | sample sau khi xử lý các điều kiện quan trọng |
| Cần xử lý theo thời điểm sự kiện xảy ra và event đến trễ? | Event-time model với timestamp và chính sách late event rõ ràng |
| Cần replay đầy đủ sau restart? | Event store hoặc broker có retention và offset |

FRP giúp mô tả quan hệ giữa sự kiện, trạng thái và phép biến đổi theo thời gian. Trong Reactor, Flux là nền tảng để biểu diễn các chuỗi tín hiệu rời rạc; scan có thể chuyển sự kiện thành chuỗi trạng thái; combineLatest tạo snapshot từ các trạng thái mới nhất; replay latest giúp consumer đến muộn nhận giá trị gần nhất; sample giảm tần suất cập nhật khi nghiệp vụ cho phép. Những công cụ này không tự biến một stream thành trạng thái bền vững hay một tín hiệu liên tục. Hãy xác định rõ dữ liệu là event hay state, thời gian nào có ý nghĩa, consumer đến muộn cần gì và có được phép bỏ cập nhật hay không. Khi hợp đồng dữ liệu được định nghĩa rõ, pipeline reactive sẽ dễ kết hợp, kiểm thử và vận hành hơn.

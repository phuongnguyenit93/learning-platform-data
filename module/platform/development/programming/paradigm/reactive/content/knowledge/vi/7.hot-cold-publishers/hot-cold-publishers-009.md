# Nguồn nóng và lạnh

## Lựa chọn nguồn nóng hoặc lạnh cho sự kiện, I/O và trạng thái

Trong mô-đun **REACTIVE_PROGRAMMING**, ta học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams. Với Reactor, `Mono` và `Flux` giúp mô tả nguồn dữ liệu, kết hợp toán tử, điều khiển scheduler, xử lý lỗi và kiểm thử pipeline. Khi thiết kế một nguồn dữ liệu, một quyết định có ảnh hưởng lớn đến hành vi toàn hệ thống là chọn **Publisher cold (nguồn lạnh)** hay **Publisher hot (nguồn nóng)**.

Nguồn cold thường tạo một lần thực thi độc lập cho mỗi Subscriber. Nguồn hot thường chia sẻ một quá trình phát tín hiệu giữa nhiều Subscriber; người đăng ký muộn có thể chỉ nhận phần sự kiện phát từ thời điểm họ tham gia, trừ khi nguồn có cơ chế lưu hoặc phát lại. Không có lựa chọn nào luôn đúng. Ta cần xem xét ý nghĩa của dữ liệu, thời điểm Subscriber xuất hiện, chi phí I/O, yêu cầu không bỏ lỡ sự kiện, hành vi khi retry và cách quản lý trạng thái dùng chung.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt cold và hot Publisher dựa trên vòng đời phát dữ liệu và hành vi khi có nhiều Subscriber.
- Chọn nguồn phù hợp cho tác vụ I/O, luồng sự kiện trực tiếp và trạng thái mới nhất.
- Dự đoán ảnh hưởng của nhiều subscription đối với truy vấn, tác dụng phụ và chi phí tài nguyên.
- Sử dụng `share`, `replay`, `cache` và `Sinks.Many` đúng mục đích.
- Chọn chính sách cho Subscriber đến muộn, Subscriber xử lý chậm và sự kiện không được phép mất.
- Kiểm thử hành vi cold/hot, chia sẻ, phát lại và cancellation bằng Reactor Test.

## 1. Cold và hot mô tả vòng đời của nguồn

Điểm khác biệt quan trọng nhất là mối quan hệ giữa subscription và quá trình phát dữ liệu.

**Cold Publisher** thường bắt đầu một lần thực thi mới khi mỗi Subscriber đăng ký. Mỗi Subscriber nhận một luồng riêng, thường bắt đầu từ đầu nguồn. Ví dụ quen thuộc là `Flux.fromIterable(list)`, `Mono.fromCallable(...)` hoặc một Publisher truy vấn dữ liệu được tạo theo từng subscription.

**Hot Publisher** chia sẻ một nguồn phát đang diễn ra hoặc một quá trình phát chung giữa các Subscriber. Nguồn có thể đã phát trước khi một Subscriber đăng ký. Subscriber mới thường chỉ quan sát những tín hiệu từ thời điểm tham gia, trừ khi nguồn có chính sách replay hoặc lưu lịch sử.

| Đặc điểm | Cold Publisher | Hot Publisher |
|---|---|---|
| Quan hệ với subscription | Mỗi subscription thường khởi động một lần thực thi riêng | Các Subscriber có thể cùng quan sát một quá trình phát |
| Subscriber đến muộn | Thường nhận luồng từ đầu | Có thể bỏ lỡ phần đã phát trước khi đăng ký |
| Tác dụng phụ ở nguồn | Có thể lặp lại theo số subscription | Thường thuộc một quá trình phát chung |
| Demand và cancellation | Mỗi subscription có nhu cầu và vòng đời riêng | Nguồn cần chính sách phối hợp nhiều Subscriber |
| Trường hợp thường gặp | Truy vấn, tính toán, request/response | Sự kiện trực tiếp, cập nhật trạng thái chung, nguồn dùng chung |
| Điều cần quyết định | Có chấp nhận chạy lại công việc cho mỗi Subscriber không? | Cần replay, buffer, drop hay lưu bền vững không? |

Cold/hot là đặc tính hành vi của Publisher, không chỉ là tên của một lớp. Một nguồn có thể bắt đầu cold rồi được chia sẻ bằng toán tử để nhiều Subscriber dùng chung một subscription upstream. Một nguồn hot cũng có thể cung cấp replay để Subscriber đến muộn nhận lại một phần lịch sử.

## 2. Chọn nguồn cho tác vụ I/O

Với một thao tác request/response, cold Publisher thường là lựa chọn tự nhiên. Mỗi subscription biểu diễn một lần thực hiện yêu cầu. Điều này phù hợp khi mỗi lần gọi cần kết quả độc lập hoặc cần đọc trạng thái mới nhất từ hệ thống bên ngoài.

Ví dụ, một request WebClient được mô tả bằng Publisher:

~~~java
Mono<Customer> customer =
    webClient.get()
        .uri("/customers/{id}", customerId)
        .retrieve()
        .bodyToMono(Customer.class);
~~~

Với cách dùng thông thường, HTTP request được thực hiện khi Publisher được subscribe. Nếu cùng biến `customer` được subscribe hai lần, ứng dụng có thể gửi hai HTTP request. Vì thế, không nên giả định một biến `Mono` chỉ chạy một lần.

Một nguồn repository reactive cũng thường được tiêu thụ theo subscription:

~~~java
Flux<Order> pendingOrders =
    orderRepository.findByStatus(OrderStatus.PENDING);
~~~

Mỗi subscription có thể mở một lần truy vấn hoặc một lần đọc mới tùy adapter và cách triển khai repository. Điều này hữu ích nếu hai tác vụ cần đọc dữ liệu độc lập, nhưng có thể gây tải lặp nếu vô tình subscribe nhiều lần.

### Khi cần chia sẻ một lần gọi I/O

Giả sử hai thành phần cần cùng một kết quả cấu hình và việc gọi dịch vụ cấu hình tốn kém. Có thể chia sẻ kết quả bằng `cache()`:

~~~java
Mono<Configuration> configuration =
    Mono.defer(configClient::load)
        .cache();
~~~

Trong ví dụ, nguồn được tạo khi subscription đầu tiên đến; `cache()` lưu tín hiệu đã phát để các Subscriber sau dùng lại kết quả đã cache. Điều này thay đổi ngữ nghĩa từ việc mỗi Subscriber thực hiện nguồn độc lập sang việc chia sẻ một kết quả.

Trước khi dùng cache, cần xác định:

- Dữ liệu có thay đổi thường xuyên không và thời gian hiệu lực là bao lâu?
- Kết quả rỗng hoặc lỗi có được lưu lại không?
- Cache có được làm mới khi có thay đổi hay chỉ tồn tại trong vòng đời đối tượng?
- Có chấp nhận dùng cùng một kết quả cho nhiều request không?

Không nên cache một thao tác có tác dụng phụ như thanh toán hoặc ghi nhận giao dịch chỉ để tránh nhiều subscription. Cần thiết kế idempotency và chính sách nghiệp vụ riêng. Chia sẻ kết quả không thay thế bảo đảm chống thực hiện trùng ở phía dịch vụ.

### Khi cần chia sẻ một request đang chạy

Đôi khi nhiều Subscriber đến gần như cùng lúc và cần cùng theo dõi một lần gọi đang diễn ra. Các toán tử chia sẻ có thể giúp tránh tạo nhiều subscription upstream. Tuy nhiên, phải phân biệt chia sẻ một lần thực thi đang hoạt động với cache kết quả trong thời gian dài. Hãy chọn chính sách dựa trên số lượng Subscriber, thời điểm tham gia, hành vi khi tất cả Subscriber rời đi và việc có cần phát lại kết quả cho người đến sau hay không.

## 3. Chọn nguồn cho sự kiện trực tiếp

Sự kiện từ giao diện, cảm biến, WebSocket, callback hệ thống hoặc một luồng thông báo đang chạy thường có đặc tính hot. Nguồn phát sự kiện theo thời gian, còn Subscriber có thể tham gia hoặc rời đi ở những thời điểm khác nhau.

Ví dụ, một bộ phát sự kiện trong ứng dụng có thể dùng `Sinks.Many`:

~~~java
Sinks.Many<OrderEvent> sink =
    Sinks.many().multicast().onBackpressureBuffer();

Flux<OrderEvent> liveEvents = sink.asFlux();

liveEvents.subscribe(event ->
    auditService.record(event)
);

liveEvents.subscribe(event ->
    dashboard.update(event)
);

Sinks.EmitResult result = sink.tryEmitNext(
    new OrderEvent(orderId, "PAID")
);

if (result.isFailure()) {
    log.warn("Event was not accepted: {}", result);
}
~~~

Với sink multicast, các Subscriber đang tham gia cùng quan sát những sự kiện được phát. `tryEmitNext` trả về kết quả để ứng dụng có thể nhận biết trường hợp phát không thành công, chẳng hạn do trạng thái sink hoặc quy tắc phát đồng thời. Trong ứng dụng thực tế, cần xử lý kết quả phát thay vì bỏ qua.

Một Subscriber đăng ký sau khi sự kiện đã phát thường không nhận lại sự kiện cũ từ multicast sink này. Nếu dashboard cần trạng thái hiện tại ngay khi mở màn hình, chỉ dùng một luồng sự kiện trực tiếp có thể chưa đủ. Ta cần gửi thêm snapshot trạng thái hoặc chọn nguồn có replay giá trị mới nhất.

### Không phải mọi sự kiện hot đều không thể phát lại

Hot không đồng nghĩa dữ liệu chắc chắn mất khi Subscriber đến muộn. Một message broker có thể lưu sự kiện trong thời gian dài và cho consumer đọc lại từ offset hoặc vị trí đã lưu. Một nguồn có thể replay một số phần tử gần nhất. Một adapter có thể tạo Publisher cold cho mỗi consumer dù dữ liệu gốc đến từ broker.

Vì vậy, khi tích hợp Kafka, message broker, WebSocket hoặc event bus, cần đọc rõ hợp đồng của adapter: subscription mới bắt đầu từ đâu, offset được quản lý thế nào, sự kiện có retention không, ack xảy ra lúc nào và Subscriber chậm sẽ ảnh hưởng đến nguồn ra sao. Nhãn hot/cold một mình không trả lời được các câu hỏi về độ bền và giao nhận.

## 4. Chọn nguồn cho trạng thái dùng chung

Trạng thái và sự kiện có mục đích khác nhau:

- **Sự kiện** cho biết một điều gì đó đã xảy ra: đơn hàng được thanh toán, cảm biến phát hiện thay đổi, người dùng nhấn nút.
- **Trạng thái** mô tả tình hình hiện tại: đơn hàng đang ở trạng thái nào, nhiệt độ hiện tại là bao nhiêu, cấu hình hiện đang áp dụng.

Nếu Subscriber mới cần biết giá trị hiện tại, ta thường cần một nguồn trạng thái có thể phát lại giá trị mới nhất. Trong Reactor, có thể minh họa bằng replay sink chỉ giữ giá trị gần nhất:

~~~java
Sinks.Many<DeviceState> stateSink =
    Sinks.many().replay().latest();

Flux<DeviceState> stateUpdates = stateSink.asFlux();

stateSink.tryEmitNext(initialState);

// Subscriber đến sau cũng nhận trạng thái gần nhất.
stateUpdates.subscribe(state ->
    dashboard.showState(state)
);

// Khi trạng thái thay đổi:
stateSink.tryEmitNext(updatedState);
~~~

`replay().latest()` giữ tín hiệu mới nhất để Subscriber đến sau nhận được snapshot gần nhất rồi tiếp tục theo dõi cập nhật mới. Đây là cách phù hợp cho trạng thái mà giá trị mới thay thế giá trị cũ.

Nếu cần giữ nhiều giá trị gần nhất, có thể cân nhắc replay với giới hạn kích thước. Nếu cần lịch sử đầy đủ, một replay sink trong bộ nhớ không thay thế kho lưu trữ bền vững hoặc event log. Cần cân nhắc dung lượng, thời hạn lưu và hành vi khi ứng dụng khởi động lại.

Không nên dùng chính sách latest cho sự kiện mà mỗi phần tử đều có ý nghĩa nghiệp vụ. Ví dụ, bỏ qua một cập nhật nhiệt độ trung gian có thể chấp nhận được nếu màn hình chỉ cần giá trị mới nhất; bỏ qua một lệnh hoàn tiền hoặc một sự kiện kiểm toán thì có thể không chấp nhận được.

## 5. Chuyển một nguồn cold thành nguồn chia sẻ

Một nguồn cold có thể được chia sẻ để tránh thực hiện lại upstream cho mỗi Subscriber. Reactor cung cấp các toán tử như `share()`, `publish()` và `replay()`.

### `share()`: chia sẻ tín hiệu giữa Subscriber đang tham gia

~~~java
Flux<Price> sharedPrices =
    priceClient.streamPrices()
        .share();
~~~

`share()` chia sẻ một subscription upstream giữa các Subscriber cùng tham gia. Nguồn thường được kết nối khi Subscriber đầu tiên đăng ký; Subscriber đến sau nhận tín hiệu từ thời điểm tham gia, không được phát lại lịch sử đã đi qua. Vòng đời kết nối phụ thuộc số Subscriber và chính sách ref-count của toán tử.

Dùng `share()` khi nhiều thành phần cần quan sát cùng luồng trực tiếp và không cần replay lịch sử. Ví dụ, hai thành phần cùng theo dõi giá thị trường trong thời gian chúng đang hoạt động.

### `replay()`: chia sẻ và phát lại một phần lịch sử

~~~java
Flux<Price> latestPrices =
    priceClient.streamPrices()
        .replay(1)
        .autoConnect(1);
~~~

Ví dụ tạo một nguồn chia sẻ có replay một phần tử gần nhất. Subscriber mới có thể nhận giá trị đã phát gần nhất rồi tiếp tục nhận dữ liệu mới. `autoConnect(1)` bắt đầu kết nối khi có ít nhất một Subscriber và giữ kết nối sau khi đã được thiết lập. Do đó, nếu tất cả Subscriber rời đi, nguồn upstream vẫn có thể tiếp tục chạy. Cần có chủ sở hữu vòng đời và chính sách dừng rõ ràng cho kiểu kết nối này.

Các chính sách cần phân biệt:

| Cách dùng | Subscriber mới nhận gì? | Vòng đời nguồn |
|---|---|---|
| Cold Publisher gốc | Thường nhận luồng mới từ đầu | Mỗi subscription có thực thi riêng |
| `share()` | Tín hiệu từ lúc tham gia | Chia sẻ kết nối theo ref-count |
| `replay(1).autoConnect(1)` | Giá trị gần nhất và tín hiệu mới | Kết nối sau Subscriber đầu tiên, tiếp tục chạy |
| `cache()` trên Mono | Tín hiệu đã cache | Giữ kết quả theo chính sách cache |

Các toán tử này thay đổi số lần subscription upstream, cách phát lại và vòng đời kết nối. Chúng không tự tạo ra bảo đảm lưu trữ bền vững hoặc xử lý exactly-once.

## 6. Backpressure và Subscriber xử lý chậm

Với cold Publisher, mỗi Subscriber thường có demand riêng và nguồn có thể tạo dữ liệu theo nhu cầu của Subscriber đó. Với nguồn hot, tốc độ phát có thể do bên ngoài quyết định. Một cảm biến hoặc callback UI có thể phát sự kiện mà không chờ Subscriber yêu cầu thêm.

Khi nguồn hot nhanh hơn khả năng tiêu thụ, cần chọn chính sách rõ ràng:

- **Buffer:** giữ sự kiện để Subscriber xử lý sau. Cần giới hạn dung lượng và quy tắc khi đầy.
- **Drop:** bỏ một số phần tử khi Subscriber không theo kịp. Chỉ dùng khi nghiệp vụ cho phép mất phần tử.
- **Latest:** chỉ giữ giá trị mới nhất. Phù hợp với trạng thái hoặc dữ liệu cập nhật liên tục mà giá trị cũ không còn cần thiết.
- **Error:** báo lỗi khi không thể tiếp nhận thêm dữ liệu, để tầng gọi xử lý quá tải.
- **Durable queue/log:** lưu sự kiện bền vững để consumer có thể tiếp tục hoặc đọc lại sau lỗi, phù hợp với yêu cầu giao nhận quan trọng.

Không nên chọn buffer vô hạn chỉ để tránh lỗi phát. Nếu tốc độ đầu vào luôn cao hơn tốc độ xử lý, hàng đợi sẽ tăng cho tới khi tiêu thụ hết bộ nhớ hoặc làm độ trễ vượt giới hạn. Với nguồn hot multicast, cần xem xét cả Subscriber chậm nhất và cách sink phân phối demand/buffer giữa các Subscriber.

Ví dụ, nếu dashboard chỉ cần trạng thái mới nhất thì có thể dùng latest. Nếu audit phải ghi mọi sự kiện, không nên dùng drop/latest cho nhánh audit. Có thể tách hai nhu cầu: lưu sự kiện vào một cơ chế bền vững cho audit, đồng thời phát snapshot/latest cho dashboard.

## 7. Bảng quyết định theo loại dữ liệu

| Tình huống | Lựa chọn khởi đầu | Lý do và điểm cần kiểm tra |
|---|---|---|
| Đọc hồ sơ khách hàng theo request | Cold `Mono` | Mỗi request cần kết quả độc lập; cân nhắc cache nếu có yêu cầu dùng chung |
| Truy vấn danh sách đơn chờ xử lý | Cold `Flux` | Mỗi lần chạy job có thể cần một lần đọc riêng; kiểm soát số subscription |
| Gọi dịch vụ thanh toán | Cold Publisher theo từng lệnh | Mỗi lệnh là tác vụ riêng; bảo vệ bằng idempotency, timeout và retry có giới hạn |
| Giá thị trường trực tiếp cho nhiều màn hình | Hot shared `Flux` | Tránh mở nhiều kết nối upstream; quyết định Subscriber đến muộn cần replay hay không |
| Trạng thái thiết bị mới nhất | Hot replay latest | Subscriber mới cần snapshot hiện tại và các thay đổi tiếp theo |
| Sự kiện kiểm toán không được mất | Durable event log/queue | Cần retention, offset/ack và khả năng đọc lại; chỉ hot in-memory không đủ |
| Tính toán thuần túy trên mỗi request | Cold `Mono`/`Flux` | Mỗi Subscriber có kết quả độc lập, dễ kiểm thử |
| Một lần tải cấu hình dùng chung | Cold upstream kết hợp cache có TTL | Tránh gọi lặp nhưng cần xác định thời hạn và cách làm mới |

Bảng này là điểm xuất phát. Một hệ thống có thể kết hợp nhiều kiểu: một nguồn cold thực hiện truy vấn, sau đó chia sẻ luồng kết quả; một event log bền vững cung cấp dữ liệu cho worker cold riêng; một trạng thái hot replay snapshot mới nhất.

## 8. Rủi ro khi lựa chọn sai

### Lặp tác dụng phụ do nhiều subscription

~~~java
Mono<Receipt> receipt =
    paymentClient.charge(command);

receipt.subscribe(this::recordReceipt);
receipt.subscribe(this::sendConfirmation);
~~~

Nếu `charge` là cold Publisher, hai subscription có thể gửi hai lệnh thanh toán. Việc hai Subscriber cần cùng kết quả không có nghĩa họ nên thực hiện hai giao dịch. Có thể ghép các bước trong một pipeline:

~~~java
Mono<Void> workflow =
    paymentClient.charge(command)
        .flatMap(result ->
            Mono.when(
                receiptRepository.save(result),
                notificationService.sendConfirmation(result)
            )
        );
~~~

Nếu hai thành phần thực sự cần quan sát cùng một kết quả, có thể chia sẻ hoặc cache kết quả với chính sách phù hợp. Với thao tác thanh toán, vẫn cần idempotency key ở phía dịch vụ để bảo vệ trước retry, timeout và request trùng.

### Subscriber đến muộn bỏ lỡ dữ liệu

Nếu dùng `share()` cho luồng sự kiện và dashboard chỉ subscribe sau khi nguồn đã phát một số phần tử, dashboard không tự nhận lịch sử. Hãy xác định liệu nó cần snapshot, replay một số sự kiện hay đọc lại từ event log.

### Hot source sống lâu hơn thành phần sử dụng

Một nguồn kết nối bằng `autoConnect` có thể tiếp tục chạy sau khi Subscriber cuối cùng rời đi. Nếu không quản lý vòng đời, ứng dụng có thể giữ kết nối mạng hoặc tài nguyên nền lâu hơn dự kiến. Dùng cơ chế ref-count hoặc giữ handle kết nối ở thành phần có trách nhiệm shutdown.

### Dùng latest cho sự kiện cần xử lý đầy đủ

Chính sách latest có thể làm mất các phần tử trung gian. Điều này phù hợp khi chỉ quan tâm trạng thái mới nhất, nhưng không phù hợp với giao dịch, kiểm toán, lệnh hoặc thông điệp cần xử lý từng phần tử.

## 9. Kiểm thử để xác nhận hành vi cold và hot

Không nên chỉ kiểm tra giá trị cuối. Hãy kiểm tra số lần nguồn được thực thi và những gì Subscriber mới nhận.

### Cold Publisher chạy riêng theo subscription

~~~java
AtomicInteger executions = new AtomicInteger();

Flux<Integer> cold =
    Flux.defer(() -> {
        executions.incrementAndGet();
        return Flux.just(1, 2, 3);
    });

StepVerifier.create(cold)
    .expectNext(1, 2, 3)
    .verifyComplete();

StepVerifier.create(cold)
    .expectNext(1, 2, 3)
    .verifyComplete();

assertThat(executions.get()).isEqualTo(2);
~~~

Hai subscription tạo hai lần thực thi nguồn. Đây là hành vi mong đợi của ví dụ cold Publisher.

### Hot multicast không phát lại sự kiện đã qua

~~~java
Sinks.Many<Integer> sink =
    Sinks.many().multicast().onBackpressureBuffer(16, false);

Flux<Integer> hot = sink.asFlux();

StepVerifier.create(hot)
    .then(() -> sink.tryEmitNext(1))
    .expectNext(1)
    .thenCancel()
    .verify();

StepVerifier.create(hot)
    .then(() -> sink.tryEmitNext(2))
    .expectNext(2)
    .thenCancel()
    .verify();
~~~

Ví dụ minh họa hai subscription lần lượt tham gia nguồn multicast. Subscriber thứ hai không nhận lại phần tử 1 đã phát trước đó. Trong kiểm thử thực tế, cần kiểm tra `EmitResult` của sink và thiết kế tín hiệu hoàn tất/hủy theo vòng đời nguồn.

### Replay giá trị gần nhất cho Subscriber mới

~~~java
Sinks.Many<String> state =
    Sinks.many().replay().latest();

Flux<String> states = state.asFlux();

state.tryEmitNext("READY");

StepVerifier.create(states)
    .expectNext("READY")
    .thenCancel()
    .verify();
~~~

Subscriber đăng ký sau khi trạng thái đã được phát vẫn nhận giá trị mới nhất. Đây là khác biệt cần xác minh khi thiết kế nguồn trạng thái.

Khi kiểm thử nguồn theo thời gian, có thể dùng `StepVerifier.withVirtualTime` để tiến thời gian ảo mà không phải chờ thực tế. Với nguồn hot có vòng đời dài, hãy xác định rõ lúc kết nối, lúc subscribe, lúc hủy và lúc kết thúc để test không bị phụ thuộc thứ tự chạy ngẫu nhiên.

## 10. Quy trình chọn nguồn

Khi bắt đầu thiết kế một Publisher, hãy lần lượt trả lời các câu hỏi sau:

1. **Dữ liệu là gì?** Một kết quả request/response, một chuỗi sự kiện hay trạng thái mới nhất?
2. **Subscriber đến lúc nào?** Có cần nhận dữ liệu từ đầu, từ thời điểm đăng ký hay cần snapshot hiện tại?
3. **Có bao nhiêu Subscriber?** Mỗi người cần một lần thực thi riêng hay tất cả cần cùng một nguồn?
4. **Tác dụng phụ có được phép lặp lại không?** Nếu không, phải kiểm soát số subscription và dùng idempotency khi cần.
5. **Subscriber chậm thì sao?** Nguồn có thể giảm tốc, buffer, drop, giữ latest, báo lỗi hay phải lưu bền vững?
6. **Cancellation có ý nghĩa gì?** Một Subscriber rời đi có được dừng nguồn chung không, hay các Subscriber khác vẫn cần nó?
7. **Lỗi và phục hồi được quản lý ở đâu?** Cần retry nguồn, đọc lại offset, tái kết nối hay phát snapshot mới?
8. **Cần kiểm thử điều gì?** Số lần thực thi, dữ liệu phát lại, hành vi khi Subscriber muộn, overflow và vòng đời kết nối.

Chỉ sau khi trả lời các câu hỏi này mới chọn `defer`, `share`, `replay`, `cache`, `Sinks.Many` hoặc adapter nguồn bên ngoài. Cú pháp tạo Publisher nên phản ánh chính sách dữ liệu mà nghiệp vụ yêu cầu.

## 11. Những nhầm lẫn thường gặp

- **Cold luôn tốt hơn hot:** cold phù hợp với thực thi độc lập; hot phù hợp với sự kiện hoặc trạng thái chia sẻ. Chọn theo ngữ nghĩa dữ liệu.
- **Hot nghĩa là không thể replay:** hot source vẫn có thể giữ và phát lại một phần lịch sử hoặc giá trị mới nhất.
- **Một biến `Mono` chỉ thực hiện một lần:** cold Mono có thể thực hiện lại theo từng subscription.
- **`share()` tương đương cache:** share phân phối tín hiệu đang diễn ra; cache lưu tín hiệu theo chính sách cache.
- **`replay(1)` là kho lịch sử bền vững:** replay giữ tín hiệu theo bộ nhớ và vòng đời của Publisher, không thay thế event log hoặc database.
- **Hot multicast tự xử lý mọi Subscriber chậm:** cần chọn buffer, drop, latest, error hoặc lưu bền vững và theo dõi overflow.
- **Mọi nguồn từ message broker đều hot theo cùng một cách:** hành vi phụ thuộc adapter, offset, retention và cách tạo consumer.
- **Dùng cache sẽ ngăn mọi tác dụng phụ trùng:** cache chỉ thay đổi hành vi trong phạm vi Publisher instance và chính sách cache; nó không thay thế idempotency ở ranh giới nghiệp vụ.

## 12. Bài tập vận dụng

Một hệ thống theo dõi thiết bị có hai yêu cầu:

- Màn hình quản trị cần hiển thị trạng thái nhiệt độ hiện tại và các thay đổi tiếp theo. Khi người vận hành mở màn hình muộn, họ vẫn cần thấy giá trị mới nhất.
- Dịch vụ kiểm toán cần lưu mọi cảnh báo nhiệt độ vượt ngưỡng. Không được bỏ mất cảnh báo khi dịch vụ kiểm toán tạm thời xử lý chậm.

Hãy đề xuất cách tổ chức nguồn:

1. Phần nào nên được mô hình hóa như luồng sự kiện, phần nào là trạng thái?
2. Màn hình quản trị nên dùng multicast trực tiếp, replay latest hay đọc snapshot từ kho trạng thái?
3. Vì sao chính sách latest có thể phù hợp với màn hình nhưng không phù hợp với kiểm toán?
4. Nếu kiểm toán chậm, cần buffer có giới hạn hay hàng đợi bền vững? Điều gì xảy ra khi dung lượng đầy?
5. Làm sao để hai Subscriber không vô tình tạo hai kết nối cảm biến hoặc hai lần đọc cùng một nguồn upstream?
6. Hãy đề xuất các kiểm thử xác nhận Subscriber muộn nhận được trạng thái mới nhất và mọi cảnh báo được lưu đúng một lần theo khóa sự kiện.

**Gợi ý:** có thể dùng một nguồn sự kiện được quản lý tập trung cho các cập nhật trực tiếp, một Publisher replay latest hoặc snapshot cho trạng thái màn hình, và một event log/queue bền vững cho cảnh báo kiểm toán. Dùng `share()` hoặc cơ chế kết nối phù hợp nếu cần chia sẻ một subscription upstream; kiểm tra vòng đời, demand, overflow và idempotency ở từng nhánh.

## Kết luận

Cold Publisher phù hợp khi mỗi subscription cần một lần thực thi độc lập, thường gặp ở truy vấn và request/response. Hot Publisher phù hợp khi nhiều Subscriber cùng quan sát một quá trình phát sự kiện hoặc trạng thái đang thay đổi. Khi chọn nguồn, cần xác định Subscriber đến muộn nhận gì, Subscriber chậm được xử lý ra sao, tác dụng phụ có thể lặp lại không và ai sở hữu vòng đời kết nối. `share`, `replay`, `cache` và `Sinks.Many` cung cấp những chính sách khác nhau; chúng cần được chọn theo yêu cầu dữ liệu, kết hợp với backpressure, lưu trữ bền vững và kiểm thử hành vi nhiều subscription để pipeline Reactor vận hành đúng.

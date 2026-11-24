# Bỏ phần tử, giữ phần tử mới nhất hoặc kết thúc bằng lỗi

Trong một pipeline reactive, tốc độ phát dữ liệu của nguồn có thể cao hơn tốc độ xử lý của Subscriber. Reactive Streams giải quyết sự chênh lệch này bằng cơ chế backpressure: Subscriber thông báo nhu cầu bằng `Subscription.request(n)`, còn Publisher và các toán tử phối hợp để phát dữ liệu theo nhu cầu đó. Tuy nhiên, có những nguồn sự kiện nóng hoặc nguồn tích hợp bên ngoài không thể chậm lại theo yêu cầu của Subscriber. Khi đó, pipeline cần một chính sách rõ ràng cho phần tử đến trong lúc downstream chưa sẵn sàng.

Bài học này thuộc chương **Áp lực ngược** của module **REACTIVE_PROGRAMMING**. Module hướng dẫn tư duy theo các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; người học thực hành `Mono`, `Flux`, toán tử, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Với Project Reactor, ba chính sách thường dùng là `onBackpressureDrop`, `onBackpressureLatest` và `onBackpressureError`.

## Khi downstream chưa có nhu cầu

Một Subscriber không nhất thiết yêu cầu phần tử ngay khi đăng ký. Nó có thể xử lý một phần tử, thực hiện công việc tốn thời gian rồi mới gọi `request(1)` để nhận phần tử tiếp theo. Trong thời gian đó, nguồn có thể tiếp tục phát sự kiện.

Hình dung một hệ thống nhận số đo nhiệt độ mỗi mili giây, trong khi màn hình chỉ cập nhật được mỗi giây. Nếu giữ mọi số đo để xử lý tuần tự, dữ liệu có thể trở nên cũ trước khi được hiển thị. Nếu mục tiêu là hiển thị nhiệt độ hiện tại, giữ lại số đo mới nhất có thể hữu ích hơn việc xử lý toàn bộ lịch sử. Ngược lại, với sự kiện thanh toán, bỏ một sự kiện có thể làm sai trạng thái nghiệp vụ.

Ba chính sách dưới đây giải quyết tình huống downstream không có demand theo những cách khác nhau:

| Chính sách | Khi phần tử đến mà downstream chưa yêu cầu | Kết quả |
|---|---|---|
| `onBackpressureDrop()` | Bỏ phần tử mới đến | Luồng tiếp tục; các phần tử bị bỏ không được phát lại |
| `onBackpressureLatest()` | Giữ phần tử mới nhất, thay thế phần tử đang chờ trước đó | Khi downstream yêu cầu, nó nhận giá trị mới nhất đang được giữ |
| `onBackpressureError()` | Báo lỗi khi phần tử đến mà không có demand | Luồng kết thúc bằng lỗi thay vì âm thầm bỏ phần tử |

Các chính sách này thường hữu ích với `Flux`, vì `Flux` có thể phát nhiều phần tử trong một khoảng thời gian. `Mono` chỉ phát tối đa một phần tử nên ít gặp tình huống tích lũy nhiều phần tử chưa được tiêu thụ.

## Một điểm quan trọng: các toán tử này không làm nguồn chậm lại

Trong Reactor, các toán tử `onBackpressure...` chủ động yêu cầu upstream phát không giới hạn (`Long.MAX_VALUE`) rồi áp dụng chính sách khi downstream chưa có nhu cầu. Vì vậy, chúng quản lý tình trạng quá tải tại ranh giới của pipeline; chúng không tự tạo ra cơ chế điều tiết để nguồn phát chậm lại.

~~~mermaid
flowchart LR
    A["Nguồn sự kiện"] -->|"request không giới hạn"| B["onBackpressure..."]
    B --> C{"Downstream có demand?"}
    C -->|"Có"| D["Chuyển phần tử"]
    C -->|"Không"| E["Drop / Latest / Error"]
    D --> F["Subscriber"]
    E --> F
~~~

Điều này tạo ra khác biệt thực tế:

- Nếu nguồn tôn trọng backpressure và có thể được điều tiết, hãy ưu tiên thiết kế demand phù hợp để tránh tạo quá nhiều dữ liệu.
- Nếu nguồn không thể điều tiết, chẳng hạn callback từ thiết bị, luồng sự kiện nóng hoặc adapter nhận thông điệp từ hệ thống bên ngoài, hãy chọn chính sách xử lý phần tử đến khi downstream chưa sẵn sàng.
- Nếu dữ liệu không được phép mất, việc chỉ chọn một toán tử backpressure là chưa đủ. Cần cân nhắc buffer có giới hạn, lưu trữ bền vững, xác nhận thông điệp hoặc cơ chế đọc lại từ nguồn.

## Bỏ phần tử bằng onBackpressureDrop

`onBackpressureDrop()` bỏ mỗi phần tử đến trong lúc downstream chưa có demand. Khi downstream yêu cầu trở lại, các phần tử mới tiếp tục được chuyển bình thường. Toán tử không giữ một phần tử chờ để phát bù, vì vậy dữ liệu đã bị bỏ sẽ không xuất hiện lại.

~~~java
Flux<Metric> displayMetrics = incomingMetrics
    .onBackpressureDrop();
~~~

Chính sách này phù hợp khi một số mẫu dữ liệu có thể mất mà không làm sai mục tiêu của ứng dụng, ví dụ:

- Dữ liệu telemetry tần suất cao, trong đó một vài mẫu không ảnh hưởng đến xu hướng tổng thể.
- Sự kiện di chuyển con trỏ hoặc vị trí giao diện, khi vị trí cũ nhanh chóng mất ý nghĩa.
- Cập nhật trạng thái tạm thời mà ứng dụng chỉ cần tiếp tục xử lý các giá trị mới.

Reactor cũng cho phép nhận biết phần tử bị bỏ thông qua callback:

~~~java
AtomicLong droppedCount = new AtomicLong();

Flux<Metric> displayMetrics = incomingMetrics
    .onBackpressureDrop(metric -> droppedCount.incrementAndGet());
~~~

Callback này hữu ích để đếm số phần tử bị bỏ, ghi nhận chỉ số vận hành hoặc thực hiện một thao tác quan sát nhẹ. Không nên thực hiện công việc blocking hoặc xử lý nặng trong callback, vì nó chạy trên luồng thực thi phát phần tử và có thể làm nguồn bị chậm.

`onBackpressureDrop` không có nghĩa là bỏ mọi phần tử. Nếu downstream đang có demand, phần tử được chuyển tiếp bình thường. Chỉ phần tử đến khi không còn demand mới bị bỏ.

## Giữ phần tử mới nhất bằng onBackpressureLatest

`onBackpressureLatest()` giữ lại tối đa một phần tử đang chờ: mỗi phần tử mới đến sẽ thay thế phần tử cũ chưa được downstream tiêu thụ. Khi downstream yêu cầu thêm, giá trị mới nhất đang được giữ sẽ được chuyển tiếp.

~~~java
Flux<Temperature> latestTemperature = incomingTemperatures
    .onBackpressureLatest();
~~~

Giả sử downstream chưa yêu cầu phần tử trong khi nguồn lần lượt phát `21`, `22`, `23`. Toán tử không tích lũy cả ba giá trị. Nó giữ `23`; khi downstream yêu cầu một phần tử, Subscriber nhận `23`.

Chính sách này phù hợp với dữ liệu mô tả **trạng thái hiện tại**, chẳng hạn:

- Nhiệt độ hoặc độ ẩm mới nhất của một cảm biến.
- Giá trị vị trí hiện tại của một thiết bị.
- Trạng thái tiến trình mới nhất trên bảng điều khiển.
- Giá trị mới nhất của một phép đo mà các mẫu trung gian không bắt buộc phải xử lý.

Không nên dùng `onBackpressureLatest()` cho một event log cần giữ mọi chuyển đổi. Ví dụ, chuỗi `ORDER_CREATED`, `PAYMENT_ACCEPTED`, `ORDER_SHIPPED` mô tả các sự kiện riêng biệt. Nếu Subscriber chậm và chỉ nhận sự kiện cuối cùng, nó có thể không biết các bước trước đã xảy ra.

Hãy phân biệt “trạng thái mới nhất” với “mọi sự kiện đã xảy ra”. Nếu yêu cầu nghiệp vụ là đồng bộ trạng thái hiện tại, thay thế các giá trị cũ có thể hợp lý. Nếu yêu cầu là kiểm toán, tính tiền hoặc thực hiện side effect cho từng sự kiện, việc thay thế sẽ làm mất thông tin cần thiết.

## Kết thúc bằng lỗi với onBackpressureError

`onBackpressureError()` chuyển tình trạng upstream phát phần tử khi downstream không có demand thành lỗi. Trong Reactor, tình huống này được báo bằng `IllegalStateException`. Luồng kết thúc bằng `onError`, vì vậy bên tiêu thụ có thể nhận biết rằng pipeline không đáp ứng được tốc độ phát dữ liệu.

~~~java
Flux<Command> commands = incomingCommands
    .onBackpressureError()
    .doOnError(IllegalStateException.class,
        error -> metrics.incrementBackpressureFailures());
~~~

Chính sách này phù hợp khi việc âm thầm bỏ hoặc thay thế phần tử không được chấp nhận, và ứng dụng muốn phát hiện quá tải ngay lập tức. Ví dụ, nếu một pipeline xử lý lệnh cần được thực hiện tuần tự, báo lỗi có thể an toàn hơn việc bỏ lệnh hoặc chỉ giữ lệnh cuối cùng.

Tuy nhiên, `onBackpressureError()` không lưu phần tử gây quá tải để thử lại sau. Sau khi lỗi xảy ra, pipeline đã kết thúc. Nếu cần xử lý lại, ứng dụng phải có nguồn dữ liệu có thể phát lại, chẳng hạn message broker có offset, hàng đợi bền vững hoặc một cơ chế retry có thể khôi phục đúng thông điệp. Chỉ thêm `retry()` vào một nguồn nóng không có lưu trữ không đảm bảo lấy lại được phần tử đã gây lỗi.

## Chọn chính sách theo ý nghĩa nghiệp vụ

Ba toán tử không phải ba mức độ của cùng một giải pháp. Chúng thể hiện ba quyết định khác nhau về giá trị của dữ liệu:

| Câu hỏi nghiệp vụ | Chính sách phù hợp để cân nhắc | Lý do |
|---|---|---|
| Có thể bỏ một số mẫu trung gian không? | `onBackpressureDrop()` | Giữ luồng tiếp tục mà không tích lũy phần tử |
| Chỉ cần giá trị hiện tại mới nhất? | `onBackpressureLatest()` | Loại bỏ giá trị chờ cũ khi có giá trị mới |
| Không chấp nhận mất dữ liệu âm thầm và cần phát hiện quá tải? | `onBackpressureError()` | Kết thúc bằng lỗi để tầng gọi xử lý rõ ràng |
| Phải xử lý mọi sự kiện, kể cả khi downstream chậm? | Buffer có giới hạn hoặc lưu trữ bền vững | Cần giữ dữ liệu và có chính sách khi dung lượng đầy |

Ví dụ, một hệ thống giám sát có thể dùng chính sách khác nhau cho từng loại luồng:

~~~java
Flux<Temperature> temperatureForDashboard =
    sensor.temperatures().onBackpressureLatest();

Flux<PointerPosition> pointerUpdates =
    ui.pointerPositions().onBackpressureDrop();

Flux<PaymentCommand> paymentCommands =
    paymentGateway.commands().onBackpressureError();
~~~

Các lựa chọn trên chỉ hợp lý nếu phù hợp với hợp đồng nghiệp vụ tương ứng. `onBackpressureDrop` không tự bảo đảm độ chính xác của thống kê; `onBackpressureLatest` không thay thế được event log; `onBackpressureError` chỉ làm quá tải trở nên rõ ràng, không tự phục hồi dữ liệu.

## Kết hợp với xử lý lỗi

Với `onBackpressureError()`, lỗi được truyền xuống như một tín hiệu `onError`. Có thể dùng các toán tử xử lý lỗi của Reactor để ghi nhận hoặc chuyển lỗi thành kết quả phù hợp với hợp đồng của ứng dụng:

~~~java
Flux<CommandResult> results = incomingCommands
    .onBackpressureError()
    .onErrorResume(IllegalStateException.class, error -> {
        auditService.recordOverload(error);
        return Flux.empty();
    });
~~~

Ví dụ này minh họa việc chuyển lỗi quá tải thành luồng rỗng sau khi ghi nhận sự cố. Đây chỉ là lựa chọn phù hợp nếu tầng gọi chấp nhận kết thúc phần xử lý hiện tại mà không có kết quả. Với lệnh cần được thực thi, nên chuyển thông tin về hệ thống điều phối hoặc hàng đợi có khả năng phát lại, thay vì xem `Flux.empty()` là đã xử lý thành công.

Không nên dùng `onErrorResume` để che giấu lỗi backpressure mà không ghi nhận. Làm như vậy khiến hệ thống có vẻ vẫn chạy nhưng có thể đã bỏ qua công việc. Hãy xác định rõ ai chịu trách nhiệm phục hồi, dữ liệu nào được phát lại và điều kiện nào cho phép tiếp tục.

## Kiểm thử ba chính sách bằng StepVerifier

Có thể dùng `TestPublisher` để điều khiển thời điểm phát và `StepVerifier` để tạo Subscriber ban đầu không yêu cầu phần tử. Các ví dụ sau tập trung vào hành vi khi nguồn phát trong lúc downstream chưa có demand.

### Kiểm thử drop

~~~java
TestPublisher<Integer> dropSource = TestPublisher.create();

StepVerifier.create(
        dropSource.flux().onBackpressureDrop(), 0)
    .then(() -> dropSource.next(1, 2, 3))
    .then(() -> dropSource.complete())
    .verifyComplete();
~~~

Subscriber bắt đầu với demand bằng 0. Ba phần tử được phát trong thời gian đó bị bỏ; publisher sau đó hoàn tất bình thường mà không phát phần tử nào cho Subscriber.

### Kiểm thử latest

~~~java
TestPublisher<Integer> latestSource = TestPublisher.create();

StepVerifier.create(
        latestSource.flux().onBackpressureLatest(), 0)
    .then(() -> latestSource.next(1, 2, 3))
    .thenRequest(1)
    .expectNext(3)
    .then(() -> latestSource.complete())
    .verifyComplete();
~~~

Trong khi demand bằng 0, các giá trị `1` và `2` bị thay thế bởi giá trị mới hơn. Khi Subscriber yêu cầu một phần tử, nó nhận `3`.

### Kiểm thử error

~~~java
TestPublisher<Integer> errorSource = TestPublisher.create();

StepVerifier.create(
        errorSource.flux().onBackpressureError(), 0)
    .then(() -> errorSource.next(1))
    .expectError(IllegalStateException.class)
    .verify();
~~~

Nguồn phát một phần tử trong khi downstream chưa yêu cầu. Toán tử báo lỗi thay vì chuyển phần tử đó hoặc âm thầm bỏ nó.

Những kiểm thử này làm rõ sự khác nhau giữa ba hợp đồng: drop hoàn tất mà không phát phần tử đã đến khi không có demand; latest giữ lại giá trị mới nhất; error kết thúc bằng lỗi khi phần tử đến ngoài nhu cầu. Trong kiểm thử ứng dụng thực tế, nên bổ sung kiểm tra callback drop, chỉ số quá tải và hành vi phục hồi của tầng nghiệp vụ.

## Nguyên tắc thiết kế khi downstream chậm

Trước khi chọn một toán tử, hãy trả lời các câu hỏi sau:

1. Dữ liệu là trạng thái có thể thay thế hay là sự kiện phải được xử lý đầy đủ?
2. Nguồn có hỗ trợ điều tiết bằng demand hay vẫn phát theo nhịp riêng?
3. Nếu bỏ phần tử, ứng dụng có cần đếm, ghi log hoặc cảnh báo không?
4. Nếu giữ phần tử mới nhất, các giá trị trung gian có thực sự không còn ý nghĩa không?
5. Nếu kết thúc bằng lỗi, thành phần nào sẽ phục hồi và nguồn có thể phát lại dữ liệu không?
6. Nếu phải giữ mọi phần tử, giới hạn bộ nhớ và chính sách khi buffer đầy là gì?

`onBackpressureDrop`, `onBackpressureLatest` và `onBackpressureError` là các chính sách kiểm soát hành vi của pipeline khi downstream không theo kịp upstream. Chọn đúng chính sách đòi hỏi hiểu dữ liệu đang biểu diễn điều gì và hậu quả của việc bỏ, thay thế hoặc kết thúc luồng. Khi kết hợp quyết định đó với demand, lưu trữ bền vững và kiểm thử tín hiệu, ứng dụng reactive có thể xử lý tình trạng quá tải một cách có chủ đích.

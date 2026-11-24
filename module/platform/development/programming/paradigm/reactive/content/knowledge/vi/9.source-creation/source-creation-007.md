# Tiếp nhận dữ liệu từ nhiều nơi qua bộ phát có kiểm soát

Một ứng dụng reactive thường phải tiếp nhận sự kiện từ nhiều hệ thống: kho hàng, thanh toán, vận chuyển, cảm biến hoặc các API callback. Mỗi nguồn có thể có tốc độ, cách phát và vòng đời riêng. Nếu nối trực tiếp tất cả callback vào cùng một nơi mà không quản lý việc phát tín hiệu, ứng dụng dễ gặp tranh chấp giữa các luồng, mất sự kiện, hàng đợi tăng không giới hạn hoặc kết thúc luồng sai thời điểm.

Trong module `REACTIVE_PROGRAMMING`, người học thực hành các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; đồng thời sử dụng `Mono`, `Flux`, operator, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Bài học này tập trung vào cách đưa dữ liệu từ nhiều nguồn vào một luồng reactive thông qua cơ chế hợp nhất hoặc một bộ phát có kiểm soát, đồng thời giữ rõ chính sách về thứ tự, lỗi, demand và vòng đời.

## 1. Hai kiểu đầu vào cần phân biệt

Trước khi tạo một nguồn tổng hợp, hãy xác định dữ liệu từ các hệ thống đã được biểu diễn thành `Publisher` hay vẫn đến qua callback thông thường.

- **Nguồn đã là Publisher:** có thể kết hợp trực tiếp bằng các operator như `merge`, `concat` hoặc `mergeSequential`.
- **Nguồn callback hoặc API imperative:** cần một adapter để chuyển callback thành `Flux`, hoặc một điểm phát chung để các thành phần chủ động gửi sự kiện vào.

Hai cách tiếp cận này có thể cùng xuất hiện trong một ứng dụng, nhưng giải quyết hai bài toán khác nhau. Khi nguồn đã là `Flux`, ưu tiên kết hợp chúng bằng operator. Khi dữ liệu đến từ callback bên ngoài, cần một cầu nối có kiểm soát để chuyển callback thành tín hiệu reactive.

## 2. Hợp nhất các Publisher bằng `Flux.merge`

Nếu mỗi hệ thống đã cung cấp một `Flux<Event>`, `Flux.merge` có thể đăng ký các nguồn và phát phần tử của chúng xuống một subscriber chung khi phần tử đến. Ví dụ:

```java
Flux<Event> allEvents = Flux.merge(
    warehouseClient.events(),
    paymentClient.events(),
    deliveryClient.events()
);

allEvents
    .doOnNext(event -> log.info("Received {}", event.type()))
    .subscribe(this::handleEvent, this::handleFailure);
```

`merge` cho phép các nguồn hoạt động đồng thời. Phần tử được chuyển xuống theo thời điểm chúng đến, vì vậy thứ tự giữa các nguồn không được bảo đảm. Các tín hiệu đến cùng subscriber vẫn tuân theo hợp đồng tuần tự của Reactive Streams.

Chọn operator dựa trên yêu cầu thứ tự:

| Operator | Cách đăng ký nguồn | Thứ tự phát ra downstream |
|---|---|---|
| `merge` | Đăng ký các nguồn để chúng hoạt động đồng thời. | Xen kẽ theo thời điểm phần tử đến. |
| `concat` | Đăng ký nguồn tiếp theo sau khi nguồn trước hoàn tất. | Phát hết nguồn trước rồi mới đến nguồn sau. |
| `mergeSequential` | Có thể đăng ký nguồn con đồng thời. | Giữ thứ tự theo thứ tự nguồn được cung cấp; kết quả đến sớm có thể phải chờ trong bộ đệm. |

Ví dụ, nếu cần đọc dữ liệu từ ba tệp theo thứ tự xác định, `concat` có thể phù hợp. Nếu cần gọi ba dịch vụ độc lập để giảm thời gian chờ, `merge` thường phù hợp hơn. Nếu muốn thực hiện các tác vụ đồng thời nhưng phát kết quả theo thứ tự đầu vào, cân nhắc `mergeSequential`.

### Thứ tự đến không phải thứ tự nghiệp vụ

Khi `merge` kết hợp sự kiện từ nhiều nguồn, subscriber nhận được một chuỗi tuần tự, nhưng thứ tự đó phản ánh lịch đến của các sự kiện tại điểm hợp nhất. Nó không tự xác định sự kiện nào xảy ra trước trong nghiệp vụ.

Nếu thứ tự quan trọng, mỗi sự kiện nên mang metadata có thể dùng để đối chiếu, chẳng hạn:

- `source`: hệ thống phát sự kiện.
- `eventId`: mã định danh duy nhất để phát hiện trùng lặp.
- `sequence`: số thứ tự do nguồn cấp nếu nguồn hỗ trợ.
- `occurredAt`: thời điểm nghiệp vụ xảy ra.
- `receivedAt`: thời điểm adapter tiếp nhận sự kiện.
- `correlationId`: mã liên kết các sự kiện thuộc cùng một quy trình.

Không nên chỉ dựa vào timestamp để sắp xếp nếu đồng hồ giữa các hệ thống không đồng bộ hoặc độ chính xác thời gian không đủ. Sequence number, version của aggregate hoặc quy tắc thứ tự do nghiệp vụ định nghĩa thường đáng tin cậy hơn.

## 3. Chuyển API callback thành `Flux` bằng `Flux.create`

Nhiều thư viện Java phát dữ liệu qua callback, listener hoặc event handler. Chúng không nhất thiết hỗ trợ `request(n)`. `Flux.create` giúp tạo một `Flux` từ callback và cho phép chọn chính sách overflow khi nguồn phát nhanh hơn downstream.

Giả sử hai hệ thống kho và thanh toán cung cấp API đăng ký listener:

```java
interface Registration {
    void dispose();
}

interface EventSource<T> {
    Registration register(Consumer<? super T> listener);
}
```

Có thể kết nối hai nguồn vào cùng một sink của `Flux.create`:

```java
Flux<Event> events = Flux.create(sink -> {
    Registration warehouseRegistration =
        warehouseSource.register(sink::next);

    Registration paymentRegistration =
        paymentSource.register(sink::next);

    sink.onDispose(() -> {
        warehouseRegistration.dispose();
        paymentRegistration.dispose();
    });
}, FluxSink.OverflowStrategy.BUFFER);
```

Khi subscriber đăng ký, callback của cả hai hệ thống được kết nối với sink. Mỗi callback gửi sự kiện bằng `sink.next`. `Flux.create` hỗ trợ nhiều producer gọi sink từ các luồng khác nhau và tuần tự hóa tín hiệu đi xuống subscriber theo hợp đồng reactive.

Khi subscription bị hủy hoặc nguồn kết thúc, `onDispose` giúp tháo đăng ký listener và giải phóng tài nguyên. Nếu adapter mở socket, đăng ký consumer hoặc tạo timer, cần đóng chúng tại đây để tránh rò rỉ tài nguyên.

### Chọn `push` hay `create`

Reactor cung cấp hai API thường gặp để tạo `Flux` từ callback:

- `Flux.push` phù hợp khi chỉ có một luồng producer gọi sink.
- `Flux.create` phù hợp khi nhiều luồng producer có thể gọi sink.

Nếu API callback bảo đảm mọi sự kiện đến trên cùng một luồng, `push` có thể biểu đạt ràng buộc đó. Nếu nhiều listener hoặc nhiều luồng có thể gọi callback đồng thời, `create` là lựa chọn phù hợp hơn. Không nên chọn `push` rồi để nhiều luồng cùng gọi sink vì điều đó vi phạm giả định về producer của API.

### Chọn overflow strategy theo ý nghĩa dữ liệu

Nguồn callback bên ngoài có thể không biết subscriber đang có bao nhiêu demand. Khi đó, adapter cần quyết định cách xử lý phần tử đến lúc downstream chưa sẵn sàng.

| Chiến lược | Hành vi | Trường hợp phù hợp |
|---|---|---|
| `BUFFER` | Giữ phần tử chờ cho đến khi có demand. | Cần giữ sự kiện và có thể kiểm soát tốc độ hoặc dung lượng dữ liệu. |
| `DROP` | Bỏ phần tử mới không thể chuyển xuống. | Có thể bỏ một số mẫu mà không ảnh hưởng nghiệp vụ. |
| `LATEST` | Giữ giá trị mới nhất, thay thế giá trị cũ đang chờ. | Dữ liệu trạng thái như nhiệt độ hoặc vị trí hiện tại. |
| `ERROR` | Báo lỗi khi không thể tiếp nhận phần tử. | Muốn thể hiện quá tải để tầng trên xử lý. |
| `IGNORE` | Bỏ qua demand và tiếp tục phát. | Chỉ dùng khi một cơ chế khác đã kiểm soát tải và chấp nhận rủi ro downstream bị quá tải. |

`BUFFER` có thể giữ nhiều phần tử khi nguồn liên tục phát nhanh hơn tốc độ xử lý. Với nguồn vô hạn, buffer không giới hạn có nguy cơ tiêu thụ hết bộ nhớ. Nếu dùng buffer, cần xác định giới hạn, giám sát lượng phần tử chờ và quy định hành vi khi tràn. `DROP` và `LATEST` làm mất dữ liệu theo chủ đích nên chỉ dùng khi nghiệp vụ cho phép.

## 4. Dùng `Sinks.Many` làm điểm phát sự kiện chung

Trong một số ứng dụng, các thành phần không chỉ đăng ký callback mà còn cần chủ động gửi sự kiện vào một luồng chung. Reactor cung cấp `Sinks` để tạo một điểm phát có API rõ ràng. `Sinks.Many` có thể phát nhiều phần tử và cung cấp một `Flux` cho các subscriber quan sát.

Ví dụ một dịch vụ cần hợp nhất sự kiện từ kho và vận chuyển:

```java
Sinks.Many<OrderEvent> eventBus = Sinks.many()
    .multicast()
    .onBackpressureBuffer();

Flux<OrderEvent> orderEvents = eventBus.asFlux();

orderEvents
    .doOnNext(event -> log.info("{} from {}", event.type(), event.source()))
    .subscribe(this::updateOrderProjection);
```

Các adapter có thể gửi sự kiện vào `eventBus`:

```java
void onWarehouseUpdate(WarehouseUpdate update) {
    publish(new OrderEvent("warehouse", update.orderId(), update));
}

void onDeliveryUpdate(DeliveryUpdate update) {
    publish(new OrderEvent("delivery", update.orderId(), update));
}

void publish(OrderEvent event) {
    Sinks.EmitResult result = eventBus.tryEmitNext(event);
    if (result != Sinks.EmitResult.OK) {
        handleEmitFailure(event, result);
    }
}
```

Điểm phát chung giúp các thành phần gửi sự kiện qua một API thống nhất. Subscriber chỉ cần đăng ký một lần trên `orderEvents`, thay vì biết tất cả callback nguồn. Tuy nhiên, ứng dụng phải xác định rõ cách xử lý khi sink từ chối một lần emit.

### Hiểu kết quả từ `tryEmitNext`

`tryEmitNext` trả về `Sinks.EmitResult`, cho biết thao tác phát đã được chấp nhận hay thất bại. Các trường hợp thường cần quan tâm:

| Kết quả | Ý nghĩa | Hướng xử lý |
|---|---|---|
| `OK` | Phần tử đã được chấp nhận. | Không cần xử lý thêm. |
| `FAIL_NON_SERIALIZED` | Một lần emit khác đang cạnh tranh với thao tác hiện tại. | Đưa sự kiện qua hàng đợi hoặc cơ chế phát tuần tự rồi thử lại. |
| `FAIL_OVERFLOW` | Không thể tiếp nhận vì bộ đệm hoặc khả năng nhận đã đầy. | Áp dụng chính sách quá tải: lưu bền vững, từ chối, retry có giới hạn hoặc báo lỗi. |
| `FAIL_ZERO_SUBSCRIBER` | Không có subscriber phù hợp để nhận sự kiện theo chính sách sink. | Xem xét vòng đời subscriber, replay hoặc hàng đợi lưu trữ nếu cần giữ sự kiện. |
| `FAIL_TERMINATED` | Sink đã kết thúc. | Không phát tiếp; kiểm tra vòng đời nguồn và nơi quản lý terminal signal. |
| `FAIL_CANCELLED` | Sink hoặc subscription liên quan đã bị hủy. | Dừng gửi hoặc tạo nguồn mới theo chính sách vòng đời. |

Khi nhiều luồng gọi `tryEmitNext` đồng thời, sink phát hiện cạnh tranh và có thể trả về `FAIL_NON_SERIALIZED`. Sự kiện chưa được chấp nhận trong trường hợp này; không được bỏ qua kết quả rồi coi như đã phát thành công.

Một cách xử lý là đưa mọi sự kiện qua hàng đợi MPSC (*multi-producer, single-consumer*) và để đúng một consumer gọi `tryEmitNext`:

```text
Producer kho ---------+
                      |
Producer thanh toán --+--> Hàng đợi MPSC --> Một vòng drain --> Sinks.Many
                      |
Producer vận chuyển --+
```

Mỗi producer chỉ thêm sự kiện vào hàng đợi an toàn luồng. Một vòng drain duy nhất lấy từng sự kiện và gọi sink, nhờ vậy các lần emit được tuần tự hóa tại một điểm. Vòng drain cần có cơ chế đánh thức khi hàng đợi chuyển từ rỗng sang có phần tử, xử lý cancel và lỗi, đồng thời không được để hàng đợi tăng không giới hạn.

Nếu chọn retry trực tiếp khi gặp `FAIL_NON_SERIALIZED`, hãy giới hạn số lần và thời gian retry. Vòng lặp bận vô hạn có thể chiếm CPU và làm tình trạng tranh chấp nghiêm trọng hơn. Với tải nhiều producer liên tục, một hàng đợi và một consumer thường dễ kiểm soát hơn.

### Chọn loại sink theo số subscriber

`Sinks.Many` có các biến thể phù hợp với những cách phân phối khác nhau:

| Loại sink | Đặc điểm | Khi sử dụng |
|---|---|---|
| `unicast()` | Chỉ cho phép một subscriber. | Một luồng xử lý duy nhất nhận sự kiện từ nhiều producer. |
| `multicast()` | Phát sự kiện đến các subscriber đang tham gia theo chính sách multicast. | Nhiều thành phần cần quan sát cùng luồng sự kiện trực tiếp. |
| `replay()` | Lưu và phát lại một phần hoặc toàn bộ lịch sử theo cấu hình. | Subscriber đến muộn cần nhận lại các sự kiện trước đó. |

Với replay, hãy giới hạn số phần tử hoặc thời gian lưu khi nguồn có thể chạy lâu dài. Nếu giữ toàn bộ lịch sử của một nguồn vô hạn, bộ nhớ có thể tăng liên tục. Với multicast, cần hiểu subscriber đến muộn nhận phần dữ liệu nào và subscriber chậm ảnh hưởng đến nguồn ra sao.

## 5. Hợp nhất bằng operator hay dùng một sink chung?

Hai cách có thể tạo ra một luồng đầu ra, nhưng quyền sở hữu vòng đời và cách quản lý lỗi khác nhau.

| Tiêu chí | `Flux.merge` | `Flux.create` | `Sinks.Many` |
|---|---|---|---|
| Đầu vào | Các `Publisher` đã có. | Callback hoặc API imperative. | Các thành phần chủ động emit. |
| Điểm bắt đầu | Khi subscriber đăng ký vào luồng tổng hợp. | Khi subscriber đăng ký và callback được nối. | Theo vòng đời sink và các subscriber của `asFlux()`. |
| Nhiều producer | Mỗi publisher quản lý nguồn của nó. | Hỗ trợ nhiều producer gọi sink. | Phát hiện emit cạnh tranh; cần xử lý kết quả emit. |
| Hủy | Hủy subscription của các nguồn con theo vòng đời operator. | `onDispose` dùng để tháo callback và tài nguyên. | Do ứng dụng quản lý sink và subscription. |
| Lịch sử | Không tự phát lại phần tử đã qua cho subscriber mới. | Không tự lưu lịch sử ngoài chính sách nguồn. | Có thể chọn multicast hoặc replay. |

Nếu các đầu vào đã là `Flux`, `merge` thường đơn giản và để Reactor quản lý demand, hủy và tín hiệu lỗi của các nguồn con. Nếu cần chuyển listener thành `Flux`, dùng `create` để gắn và tháo callback theo subscription. Nếu nhiều thành phần cần một API phát sự kiện chủ động và có thể có nhiều subscriber quan sát, `Sinks.Many` là một lựa chọn phù hợp.

Không nên tạo sink chỉ để thay thế một phép `merge` đơn giản. Một sink chủ động kéo theo trách nhiệm quản lý terminal signal, cạnh tranh khi emit, overflow và vòng đời. Chỉ dùng nó khi ứng dụng thực sự cần một điểm phát sự kiện tách biệt với subscription downstream.

## 6. Quản lý lỗi từ nhiều nguồn

Khi kết hợp nhiều publisher, cần xác định một nguồn lỗi sẽ ảnh hưởng thế nào đến các nguồn còn lại.

- `Flux.merge` mặc định chuyển lỗi từ một nguồn xuống downstream và hủy các nguồn còn lại.
- `Flux.mergeDelayError` trì hoãn việc phát lỗi cho đến khi các nguồn đã hoàn tất hoặc lỗi theo chính sách của operator.
- Nếu lỗi của một nguồn không nên kết thúc toàn bộ luồng, có thể xử lý lỗi riêng tại nguồn đó bằng `onErrorResume`, ghi nhận trạng thái nguồn hoặc chuyển lỗi thành một kiểu sự kiện riêng.

Ví dụ, lỗi tạm thời từ một nguồn telemetry có thể được ghi log và cho phép các nguồn khác tiếp tục:

```java
Flux<Event> telemetry = telemetryClient.events()
    .onErrorResume(error -> {
        log.warn("Telemetry source stopped", error);
        return Flux.empty();
    });

Flux<Event> allEvents = Flux.merge(
    orderClient.events(),
    telemetry,
    deliveryClient.events()
);
```

`onErrorResume` trong ví dụ thay nguồn telemetry lỗi bằng một publisher rỗng, nên luồng tổng hợp vẫn có thể nhận sự kiện từ hai nguồn còn lại. Cách này chỉ phù hợp khi nghiệp vụ cho phép tiếp tục mà không có telemetry. Với nguồn thanh toán hoặc đơn hàng, bỏ qua lỗi có thể khiến trạng thái tổng hợp thiếu dữ liệu; cần chính sách phục hồi hoặc lưu lỗi rõ ràng.

Với sink chung, `tryEmitError` là terminal signal của luồng. Sau khi sink nhận lỗi hoặc hoàn tất, không thể tiếp tục dùng sink đó để phát các sự kiện mới. Nếu một nguồn con gặp lỗi nhưng các nguồn khác cần tiếp tục, hãy xử lý lỗi ở adapter của nguồn con thay vì kết thúc sink chung ngay lập tức.

## 7. Quản lý vòng đời và thứ tự kết thúc

Một nguồn tổng hợp cần biết khi nào các đầu vào được đăng ký, khi nào chúng dừng và ai có quyền gửi terminal signal.

Với `Flux.merge`, operator theo dõi trạng thái hoàn tất của các nguồn con. Luồng tổng hợp hoàn tất khi các nguồn hoàn tất theo quy tắc của operator; nếu lỗi xảy ra, hành vi phụ thuộc operator và cách xử lý lỗi đã chọn.

Với `Flux.create`, callback đăng ký listener khi có subscription. Khi subscriber hủy, `onDispose` tháo listener. Nếu các nguồn callback có thể kết thúc tự nhiên, adapter cần đếm số nguồn đã kết thúc và chỉ gọi `sink.complete()` khi tất cả nguồn cần thiết đã kết thúc. Nếu một nguồn lỗi nghiêm trọng, adapter có thể gọi `sink.error(error)` sau khi áp dụng chính sách nghiệp vụ.

Với `Sinks.Many`, nên có một thành phần sở hữu vòng đời và quyết định lúc nào gọi `tryEmitComplete()` hoặc `tryEmitError()`. Không để mỗi adapter tự ý kết thúc sink chung vì nguồn đầu tiên hoàn tất có thể khiến các nguồn còn lại không thể gửi dữ liệu. Trạng thái kết thúc cần được điều phối một lần và nhất quán.

## 8. Kiểm soát backpressure và hàng đợi khi hợp nhất nhiều nguồn

Khi nhiều nguồn cùng phát vào một luồng, tổng tốc độ đầu vào có thể lớn hơn tốc độ subscriber xử lý. Ví dụ, ba nguồn mỗi nguồn phát 300 sự kiện mỗi giây có thể tạo tổng cộng 900 sự kiện mỗi giây. Nếu downstream chỉ xử lý được 500 sự kiện mỗi giây, số sự kiện chờ có thể tăng khoảng 400 mỗi giây trong thời gian quá tải.

Hãy xem xét các điểm sau:

1. **Demand:** nếu nguồn hỗ trợ Reactive Streams, để demand truyền ngược và tránh yêu cầu trước quá nhiều dữ liệu.
2. **Prefetch:** giới hạn lượng phần tử operator lấy trước, đặc biệt ở `publishOn`, `flatMap` và các ranh giới bất đồng bộ.
3. **Overflow:** với callback không thể giảm tốc độ, chọn buffer có giới hạn, drop, latest hoặc error theo ngữ nghĩa dữ liệu.
4. **Concurrency:** giới hạn số tác vụ xử lý đồng thời để không làm cạn kết nối, thread hoặc tài nguyên downstream.
5. **Quan sát:** đo số sự kiện nhận được, số phần tử bị loại bỏ, số lần emit thất bại, kích thước hàng đợi và độ trễ xử lý.

Một hàng đợi MPSC dùng để tuần tự hóa emit cũng cần có giới hạn. Nếu consumer không theo kịp producer, hàng đợi đó trở thành điểm tích tụ dữ liệu. Hãy quy định hành vi khi hàng đợi đầy: từ chối sự kiện, ghi vào kho bền vững, pause nguồn nếu có thể, hoặc phát lỗi quá tải.

## 9. Kiểm thử nguồn tổng hợp

Với các nguồn đã là `Publisher`, `StepVerifier` có thể xác minh số lượng phần tử và terminal signal của luồng tổng hợp:

```java
Flux<String> first = Flux.just("warehouse", "warehouse-update");
Flux<String> second = Flux.just("payment", "payment-update");

Flux<String> combined = Flux.merge(first, second);

StepVerifier.create(combined)
    .expectNextCount(4)
    .verifyComplete();
```

Kiểm thử chỉ xác minh có bốn phần tử và luồng hoàn tất. Không nên ràng buộc thứ tự xen kẽ giữa hai nguồn khi dùng `merge`, vì thứ tự phụ thuộc lịch phát của chúng.

Với adapter callback hoặc sink, nên kiểm tra thêm:

- Nhiều nguồn có thể phát đồng thời mà callback downstream không bị chồng lấn.
- Mỗi sự kiện được phát thành công hoặc được ghi nhận rõ nếu emit thất bại.
- Hủy subscription tháo tất cả listener và giải phóng tài nguyên.
- Một nguồn lỗi tuân theo chính sách đã chọn và không vô tình kết thúc các nguồn khác.
- Terminal signal chỉ được gửi một lần, sau khi các nguồn cần thiết đã dừng.
- Buffer hoặc hàng đợi xử lý đúng khi đầy; không âm thầm bỏ sự kiện bắt buộc.
- Subscriber đến muộn nhận đúng hành vi live hoặc replay đã thiết kế.

Khi kiểm thử tranh chấp, có thể cho nhiều producer phát một số lượng sự kiện đã biết, sau đó xác minh số lượng nhận được, số lượng thất bại và không có callback chạy đồng thời. Không dựa vào `Thread.sleep` để khẳng định thứ tự; hãy dùng latch, barrier, scheduler ảo hoặc tín hiệu đồng bộ hóa để điều khiển điểm bắt đầu và kết thúc của các producer.

## 10. Tình huống áp dụng: hợp nhất sự kiện đơn hàng

Một dịch vụ theo dõi đơn hàng nhận ba loại sự kiện: kho xác nhận đóng gói, cổng thanh toán xác nhận giao dịch và đơn vị vận chuyển cập nhật hành trình. Mỗi hệ thống có API riêng và phát sự kiện độc lập.

Một thiết kế có thể đi theo các bước:

1. Nếu các client đã trả về `Flux<OrderEvent>`, kết hợp chúng bằng `Flux.merge`.
2. Nếu client chỉ cung cấp listener, bọc listener bằng `Flux.create` và tháo đăng ký trong `onDispose`.
3. Nếu nhiều module nội bộ cần chủ động phát sự kiện vào một luồng chung, dùng `Sinks.Many` và xử lý kết quả emit.
4. Chuẩn hóa sự kiện thành một envelope có `source`, `eventId`, `orderId`, `sequence` và thời điểm tiếp nhận.
5. Giới hạn concurrency khi cập nhật projection hoặc gọi dịch vụ ngoài; chọn buffer/overflow theo mức độ quan trọng của sự kiện.
6. Xử lý lỗi theo từng nguồn và chỉ kết thúc luồng chung khi quy tắc vòng đời yêu cầu.

Với sự kiện thanh toán, không nên dùng `DROP` hoặc `LATEST` vì có thể làm mất giao dịch. Cần đảm bảo sự kiện được lưu bền vững hoặc nguồn có thể phát lại khi downstream gián đoạn. Với cập nhật vị trí xe, có thể chỉ cần vị trí mới nhất nếu nghiệp vụ không cần lưu toàn bộ hành trình; nếu cần lịch sử hành trình, phải lưu riêng tất cả điểm dữ liệu.

## 11. Checklist khi tạo nguồn từ nhiều nơi

- Xác định đầu vào đã là `Publisher` hay còn là callback imperative.
- Dùng `merge`, `concat` hoặc `mergeSequential` theo yêu cầu về đồng thời và thứ tự.
- Dùng `Flux.create` cho callback có thể phát từ nhiều luồng; dùng `Flux.push` khi chỉ có một producer.
- Dùng `Sinks.Many` khi cần một điểm phát chủ động cho nhiều thành phần.
- Kiểm tra mọi `Sinks.EmitResult`; không coi emit thất bại là thành công.
- Tuần tự hóa các lần emit cạnh tranh bằng hàng đợi hoặc cơ chế điều phối có giới hạn.
- Gắn metadata nguồn, định danh sự kiện và quy tắc thứ tự nghiệp vụ.
- Chọn overflow strategy theo mức độ quan trọng của dữ liệu và giới hạn bộ nhớ.
- Quản lý listener, subscription và terminal signal theo một chủ sở hữu vòng đời rõ ràng.
- Kiểm thử đồng thời, cancel, lỗi từng nguồn, buffer đầy và subscriber đến muộn.

Khi nhiều đầu vào được hợp nhất qua một nguồn có kiểm soát, các phần còn lại của pipeline chỉ cần làm việc với một luồng sự kiện nhất quán. Thiết kế tốt phải làm rõ ai phát, ai nhận, thứ tự nào được bảo đảm, điều gì xảy ra khi quá tải và lúc nào luồng kết thúc. Những quyết định đó giúp pipeline `Flux` giữ được hợp đồng reactive trong khi vẫn tiếp nhận dữ liệu từ nhiều hệ thống độc lập.

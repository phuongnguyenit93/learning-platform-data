# Dọn dẹp tài nguyên khi hoàn thành, lỗi hoặc hủy

## Bối cảnh: mỗi stream có thể giữ tài nguyên lâu hơn một request thông thường

RSocket hỗ trợ các tương tác bất đồng bộ qua TCP hoặc WebSocket, trong đó request-stream và request-channel có thể tồn tại trong thời gian dài. Một stream theo dõi telemetry có thể giữ một subscription tới message broker; một route truy vấn dữ liệu có thể giữ cursor hoặc connection tới database; một phiên điều khiển thiết bị có thể giữ listener, timer hoặc trạng thái phiên.

Khi tương tác kết thúc, các tài nguyên này cần được giải phóng đúng lúc. Việc dọn dẹp phải diễn ra trong cả ba trường hợp:

- **Hoàn thành bình thường:** publisher phát hết dữ liệu và gửi tín hiệu complete.
- **Kết thúc do lỗi:** publisher phát error và kết thúc.
- **Bị hủy:** subscriber không còn cần dữ liệu và gửi tín hiệu cancel ngược lên upstream.

Nếu chỉ dọn dẹp khi complete, ứng dụng có thể rò rỉ tài nguyên khi stream lỗi hoặc client rời màn hình. Nếu chỉ dọn dẹp khi error, các stream bị hủy vẫn có thể giữ subscription và kết nối. Trong ứng dụng RSocket, cancellation là tình huống bình thường của vòng đời realtime, vì vậy cần được xem là một nhánh kết thúc chính thức.

Bài học này tập trung vào cách xác định quyền sở hữu tài nguyên, hiểu tín hiệu vòng đời Reactive Streams, dùng các toán tử Reactor để giải phóng tài nguyên đồng bộ và bất đồng bộ, và kiểm thử để bảo đảm cleanup xảy ra trong mọi nhánh.

## 1. Phân biệt vòng đời connection, stream và publisher

Một kết nối RSocket có thể mang nhiều interaction đồng thời. Mỗi interaction lại có publisher và tài nguyên riêng. Cần xác định tài nguyên thuộc phạm vi nào trước khi quyết định nơi đóng nó.

| Phạm vi | Ví dụ tài nguyên | Thời điểm giải phóng |
|---|---|---|
| Ứng dụng/process | Connection pool, scheduler, client dùng chung, thread pool | Khi ứng dụng shutdown |
| RSocket connection/session | Trạng thái xác thực phiên, bộ theo dõi connection, tài nguyên riêng của peer | Khi connection/session đóng hoặc hết hạn |
| Stream/interaction | DB cursor, subscription broker, listener, timer, file stream | Khi stream complete, error hoặc cancel |
| Một lần xử lý payload | Buffer tạm, đối tượng giải mã, tài nguyên ngắn hạn | Khi xử lý payload kết thúc |

Ví dụ, một server có thể dùng chung ConnectionFactory hoặc database connection pool cho hàng nghìn stream. Pool thuộc phạm vi ứng dụng; mỗi stream chỉ mượn một connection từ pool và trả connection về pool khi xong. Nếu mỗi stream gọi thao tác đóng toàn bộ pool, những stream khác sẽ bị ảnh hưởng.

Ngược lại, một subscription tới topic chỉ phục vụ một client nên thường thuộc phạm vi stream. Khi client hủy stream, server cần hủy subscription đó. Nếu không, broker vẫn tiếp tục gửi sự kiện dù không còn consumer nhận dữ liệu.

### Quy tắc quyền sở hữu

Mỗi tài nguyên nên có một chủ sở hữu rõ ràng:

- Thành phần tạo hoặc mượn tài nguyên chịu trách nhiệm kết thúc vòng đời của nó.
- Tài nguyên dùng chung chỉ được đóng bởi thành phần quản lý vòng đời dùng chung.
- Tài nguyên riêng của stream được giải phóng khi stream kết thúc.
- Việc cleanup phải an toàn khi được kích hoạt ở nhánh complete, error hoặc cancel.
- Không giải phóng một tài nguyên dùng chung chỉ vì một subscriber riêng lẻ rời đi.

Cần phân biệt **đóng tài nguyên** với **trả tài nguyên về pool**. Ví dụ, Connection.close() trong R2DBC thường trả connection về pool nếu connection được lấy từ pool; nó không nhất thiết đóng socket vật lý của pool.

## 2. Ba tín hiệu kết thúc trong Reactive Streams

Reactive Streams truyền dữ liệu từ Publisher tới Subscriber bằng các tín hiệu:

- onNext(value): publisher phát một phần tử.
- onComplete(): publisher kết thúc bình thường.
- onError(error): publisher kết thúc do lỗi.

Subscriber cũng có thể gọi Subscription.cancel() để báo rằng nó không còn muốn nhận dữ liệu. Cancel đi theo chiều ngược lại, từ downstream lên upstream; nó không phải một tín hiệu terminal được phát xuống như onComplete hoặc onError.

~~~mermaid
flowchart TD
    A["Publisher đang hoạt động"] --> B{"Điều gì kết thúc stream?"}
    B -->|Hết dữ liệu| C["onComplete"]
    B -->|Có lỗi| D["onError"]
    B -->|Subscriber không cần nữa| E["cancel"]
    C --> F["Giải phóng tài nguyên"]
    D --> F
    E --> F
~~~

Ba nhánh đều cần dẫn tới cleanup. Khác biệt là nguyên nhân kết thúc và tín hiệu mà downstream quan sát được.

### Complete: dữ liệu đã phát xong

Ví dụ server phát danh sách kết quả hữu hạn. Khi phần tử cuối cùng được phát và publisher hoàn tất, tài nguyên stream cần được giải phóng.

### Error: xử lý không thể tiếp tục

Lỗi có thể xảy ra khi đọc database, giải mã payload, gọi dịch vụ phụ thuộc hoặc truy cập broker. Khi publisher phát error, cleanup cần chạy trước khi tài nguyên bị bỏ lại.

### Cancel: consumer chủ động dừng

Ví dụ client đóng dashboard hoặc người dùng chuyển sang thiết bị khác. Client dispose subscription hoặc toán tử downstream hủy upstream. Server nhận cancellation và cần dừng nguồn phát nếu nguồn hỗ trợ.

Cancel không phải rollback. Nếu một tác vụ đã ghi dữ liệu hoặc gửi lệnh ra thiết bị, hủy stream không tự hoàn tác tác dụng phụ đã xảy ra. Nếu nghiệp vụ cần bù trừ, phải có quy trình riêng.

## 3. doFinally, doOnCancel và các hook quan sát vòng đời

Reactor cung cấp các hook để quan sát tín hiệu kết thúc. Chúng hữu ích cho metrics, log và theo dõi tài nguyên.

| Toán tử | Được gọi khi | Mục đích thường dùng |
|---|---|---|
| doOnComplete | Complete | Ghi nhận stream kết thúc bình thường |
| doOnError | Error | Ghi log và metrics lỗi |
| doOnCancel | Cancel | Ghi nhận client hủy hoặc upstream bị hủy |
| doFinally | Complete, error hoặc cancel | Quan sát mọi nhánh kết thúc |

Ví dụ:

~~~java
Flux<Reading> readings =
    sensorService.readings(sensorId)
        .doOnComplete(() ->
            metrics.streamCompleted(sensorId))
        .doOnError(error ->
            metrics.streamFailed(sensorId, error))
        .doOnCancel(() ->
            metrics.streamCancelled(sensorId))
        .doFinally(signal ->
            metrics.streamTerminated(sensorId, signal));
~~~

doFinally nhận SignalType, thường là ON_COMPLETE, ON_ERROR hoặc CANCEL. Nó phù hợp để ghi nhận một lần kết thúc chung mà không phải lặp logic ở từng nhánh.

### doFinally không phải cơ chế cleanup bất đồng bộ

Callback của doFinally là một hàm đồng bộ trả về void. Nó không nhận một Mono cleanup để Reactor chờ hoàn tất. Vì vậy, không nên dùng doFinally để khởi chạy một thao tác đóng tài nguyên bất đồng bộ rồi giả định thao tác đó đã xong trước khi stream kết thúc.

Ví dụ sau chỉ minh họa quan sát; closeAsync() bị gọi mà publisher cleanup không được nối vào vòng đời:

~~~java
source.doFinally(signal -> resource.closeAsync());
~~~

Nếu việc đóng tài nguyên trả về Mono hoặc Publisher, hãy dùng usingWhen để Reactor quản lý thứ tự cleanup.

### Hook quan sát không thay thế quyền sở hữu tài nguyên

doOnCancel chỉ được gọi khi có cancel. Nếu stream hoàn thành hoặc lỗi, callback này không chạy. doOnComplete và doOnError cũng không bao phủ cancel. Nếu dùng ba hook riêng để giải phóng tài nguyên, rất dễ bỏ sót nhánh hoặc thực hiện cleanup nhiều lần.

Dùng doFinally cho metrics và quan sát. Dùng using hoặc usingWhen cho tài nguyên mà publisher sở hữu.

## 4. using: quản lý tài nguyên có cleanup đồng bộ

Flux.using và Mono.using phù hợp với tài nguyên có thao tác giải phóng đồng bộ, ví dụ một InputStream, reader hoặc đối tượng có phương thức close() không trả publisher.

Reactor tạo tài nguyên khi có subscription, dùng tài nguyên để tạo publisher nguồn, rồi gọi cleanup khi nguồn complete, error hoặc bị cancel.

~~~java
Flux<String> lines = Flux.using(
    () -> Files.lines(path),
    Flux::fromStream,
    Stream::close
);
~~~

Ví dụ trên mở một Java Stream đọc file, chuyển nó thành Flux<String> và đóng stream khi subscription kết thúc. Mỗi subscriber có resource riêng do supplier được gọi trong vòng đời subscription.

Điểm quan trọng:

- Không mở file ngay lúc lắp ráp pipeline nếu resource chỉ cần tồn tại khi có subscriber.
- Resource supplier được gọi theo từng subscription.
- Cleanup được thực hiện khi publisher kết thúc hoặc bị hủy.
- Không dùng using cho thao tác đóng bất đồng bộ cần Reactor chờ.

### Ví dụ với listener đồng bộ

Một API callback có thể đăng ký listener và cần gỡ listener khi subscriber rời đi. Có thể bọc tài nguyên đăng ký trong using:

~~~java
Flux<DeviceEvent> events = Flux.using(
    () -> eventSource.registerListener(),
    listener -> listener.events(),
    listener -> eventSource.removeListener(listener)
);
~~~

Đây là phác thảo API: registerListener() tạo handle đăng ký; listener.events() trả publisher các sự kiện; removeListener() gỡ đăng ký. Nếu thao tác gỡ listener trả về publisher hoặc cần chờ I/O, hãy chuyển sang usingWhen.

## 5. usingWhen: cleanup bất đồng bộ theo từng kết quả

Nhiều tài nguyên hiện đại có thao tác giải phóng bất đồng bộ. Ví dụ, connection R2DBC có close() trả về Publisher<Void>, một lease từ service từ xa cần gọi API release, hoặc một subscription broker cần gửi lệnh unsubscribe.

usingWhen cho phép cung cấp cleanup riêng cho ba nhánh:

1. Cleanup khi publisher hoàn thành bình thường.
2. Cleanup khi publisher kết thúc bằng lỗi.
3. Cleanup khi subscriber hủy.

Với complete hoặc error, tín hiệu kết thúc downstream được trì hoãn cho đến khi publisher cleanup tương ứng hoàn tất. Với cancel, Reactor kích hoạt publisher cleanup dành riêng cho nhánh hủy sau khi nhận tín hiệu cancel. Đây là lựa chọn phù hợp khi thao tác giải phóng cũng là một phần của pipeline bất đồng bộ.

### Ví dụ mượn connection R2DBC

~~~java
Flux<Row> rows = Flux.usingWhen(
    connectionFactory.create(),
    connection -> queryRows(connection),
    connection -> connection.close(),
    (connection, error) -> connection.close(),
    connection -> connection.close()
);
~~~

Trong ví dụ:

- connectionFactory.create() cấp một connection khi có subscription.
- Hàm thứ hai dùng connection để tạo luồng đọc.
- Cleanup thứ ba chạy khi đọc hoàn tất.
- Cleanup thứ tư chạy khi đọc lỗi.
- Cleanup thứ năm chạy khi subscriber hủy.

Ví dụ giả định queryRows(connection) trả về Flux<Row> và connection.close() trả về publisher theo API R2DBC. Khi dùng transaction, cần tích hợp commit/rollback với transaction manager hoặc cung cấp cleanup phù hợp: complete có thể commit; error/cancel thường cần rollback trước khi trả connection về pool.

### Cleanup khi lỗi có thể cần nhiều bước

Với transaction, rollback và close là hai bước riêng. Cần bảo đảm connection vẫn được đóng nếu rollback thất bại. Có thể viết hàm cleanup riêng để quy định rõ thứ tự và cách ghi nhận lỗi:

~~~java
Mono<Void> rollbackAndClose(Connection connection) {
    return Mono.from(connection.rollbackTransaction())
        .onErrorResume(rollbackError -> {
            log.warn("Rollback failed", rollbackError);
            return Mono.empty();
        })
        .then(Mono.from(connection.close()));
}
~~~

Đây là ví dụ minh họa chính sách cleanup best-effort: lỗi rollback được ghi nhận, sau đó vẫn cố gắng đóng/trả connection. Với hệ thống cần bảo toàn lỗi gốc, hãy lưu cả lỗi xử lý ban đầu lẫn lỗi cleanup vào log hoặc telemetry. Không âm thầm bỏ qua cleanup error trong production.

### Cleanup có thể thất bại

Cleanup cũng là một thao tác có thể lỗi: socket đóng không thành công, broker từ chối unsubscribe hoặc connection pool báo lỗi. Ứng dụng cần xác định:

- Có retry cleanup được không?
- Có thể đóng cưỡng bức tài nguyên không?
- Lỗi cleanup có được trả về caller hay chỉ ghi nhận?
- Có cần cảnh báo khi tài nguyên không được giải phóng?
- Có timeout riêng cho cleanup hay không?

Nếu cleanup thất bại, không nên đánh dấu tài nguyên là đã giải phóng một cách giả tạo. Hãy ghi nhận trạng thái, metrics và áp dụng biện pháp phục hồi phù hợp với loại tài nguyên.

Với usingWhen, nếu publisher cleanup phát lỗi, lỗi cleanup có thể trở thành lỗi kết thúc downstream và che lấp lỗi ban đầu của nguồn. Nếu cần giữ cả hai nguyên nhân, hãy ghi nhận lỗi nguồn trước khi cleanup và ghi riêng lỗi cleanup; đừng chỉ dựa vào exception cuối cùng mà caller nhận được.

## 6. Hủy stream từ client và giải phóng tài nguyên ở server

Với request-stream, client có thể ngừng nhận dữ liệu bất cứ lúc nào. Ví dụ client đăng ký route rồi hủy subscription khi người dùng rời màn hình.

~~~java
Flux<Reading> readings = requester
    .route("sensor.readings")
    .data(new SensorQuery("sensor-01"))
    .retrieveFlux(Reading.class);

Disposable subscription = readings.subscribe(
    this::renderReading,
    this::showStreamError
);

// Khi component hoặc màn hình bị đóng:
subscription.dispose();
~~~

dispose() hủy subscription local. Với một RSocket stream còn hoạt động, runtime chuyển cancellation thành tín hiệu hủy ở cấp giao thức để peer dừng interaction tương ứng. Server không cần đóng toàn bộ RSocket connection chỉ vì một client hủy một stream.

Server có thể quan sát cancel:

~~~java
@MessageMapping("sensor.readings")
Flux<Reading> readings(SensorQuery query) {
    return sensorService.openReadings(query.sensorId())
        .doOnCancel(() ->
            logger.info("Reading stream cancelled: {}", query.sensorId()))
        .doFinally(signal ->
            metrics.streamEnded(query.sensorId(), signal));
}
~~~

doOnCancel hữu ích để quan sát. Nếu openReadings sở hữu tài nguyên như broker subscription hoặc cursor, service nên trả về publisher được bọc bằng using hoặc usingWhen để cleanup được gắn vào đúng vòng đời.

### Không gọi subscribe() tùy tiện trong controller

Với Spring RSocket, một phương thức @MessageMapping thường trả Mono hoặc Flux cho framework. Framework quản lý subscription và liên kết vòng đời publisher với interaction.

Không nên tự gọi subscribe() bên trong controller rồi trả về một publisher khác. Subscription tự tạo có vòng đời riêng; khi client hủy request, công việc đã subscribe thủ công có thể vẫn chạy và giữ tài nguyên.

~~~java
// Nên: trả publisher để framework quản lý.
@MessageMapping("sensor.readings")
Flux<Reading> readings(SensorQuery query) {
    return sensorService.readings(query.sensorId());
}
~~~

Nếu ứng dụng thực sự cần một tác vụ nền độc lập với request, hãy chuyển nó sang một thành phần sở hữu vòng đời riêng, lưu trạng thái công việc và cung cấp API hủy/tra cứu rõ ràng. Đừng để một request-stream vô tình trở thành tác vụ nền không thể quản lý.

## 7. Cleanup trong request-channel và các tương tác hai chiều

Request-channel cho phép client gửi nhiều payload và server cũng phát nhiều payload. Hai hướng có thể kết thúc ở những thời điểm khác nhau. Cần phân biệt việc một phía hoàn tất gửi dữ liệu với việc toàn bộ interaction bị hủy.

Ví dụ server nhận command stream:

~~~java
@MessageMapping("device.control")
Flux<DeviceEvent> control(Flux<DeviceCommand> commands) {
    return commands
        .concatMap(deviceService::handle)
        .doFinally(signal ->
            metrics.channelEnded(signal));
}
~~~

concatMap xử lý command theo thứ tự. Khi luồng command hoàn tất, server có thể hoàn thành phần xử lý đầu vào và tiếp tục phát các event còn lại nếu publisher còn dữ liệu. Nếu client hủy toàn bộ subscription channel, cancellation cần được truyền tới cả pipeline xử lý command và nguồn event tương ứng.

Một channel có thể sở hữu nhiều tài nguyên:

- Subscription nhận command từ client.
- Subscription lắng nghe trạng thái thiết bị.
- Timer theo dõi timeout phiên.
- Buffer giữ các event đang chờ xử lý.

Khi interaction bị hủy, mỗi tài nguyên riêng của channel cần được dừng. Nếu một nguồn được chia sẻ giữa nhiều channel, chỉ gỡ subscriber hiện tại; không đóng nguồn dùng chung.

### Hoàn tất một chiều và hủy toàn bộ interaction

Trong request-channel, một phía có thể gửi tín hiệu complete để báo rằng nó không gửi thêm payload. Phía kia vẫn có thể tiếp tục gửi dữ liệu theo giao thức. CANCEL thể hiện requester không muốn duy trì interaction và yêu cầu hủy stream.

Vì vậy, cleanup phải gắn với đúng phạm vi:

- Kết thúc publisher đầu vào chỉ giải phóng tài nguyên riêng cho hướng đầu vào nếu tài nguyên đó không còn cần.
- Kết thúc publisher đầu ra giải phóng tài nguyên riêng cho hướng đầu ra.
- Hủy toàn bộ channel giải phóng mọi tài nguyên được sở hữu bởi interaction.
- Đóng connection giải phóng tất cả interaction thuộc connection đó.

Không dùng một callback hoàn tất của một hướng để đóng tài nguyên vẫn đang được hướng còn lại sử dụng.

## 8. Kết nối RSocket đóng và vòng đời ứng dụng

Hủy một stream và đóng connection là hai sự kiện khác nhau. Một connection RSocket có thể mang nhiều stream; một stream bị cancel không được làm các stream còn lại dừng theo.

Khi connection đóng do peer disconnect, lỗi transport hoặc ứng dụng shutdown, các stream phụ thuộc connection đó không thể tiếp tục truyền dữ liệu trên connection cũ. Publisher liên quan thường kết thúc hoặc bị hủy theo implementation. Ứng dụng cần để các tín hiệu này đi tới nguồn upstream và giải phóng tài nguyên riêng của từng stream.

Ở cấp ứng dụng, connection pool, scheduler, client dùng chung và server listener có vòng đời dài hơn từng stream. Khi shutdown, một trình tự thường dùng là:

1. Ngừng nhận tương tác mới hoặc ngừng quảng bá instance sắp shutdown.
2. Cho các request đang chạy một khoảng thời gian drain có giới hạn.
3. Hoàn tất hoặc hủy các stream còn hoạt động theo chính sách.
4. Đóng các connection, listener và pool thuộc quyền sở hữu của ứng dụng.
5. Kết thúc scheduler và executor do ứng dụng tạo.

Không đóng connection pool ngay khi một stream kết thúc. Ngược lại, cũng không giữ pool vô thời hạn sau khi ứng dụng shutdown.

Cleanup reactive chỉ chạy khi runtime còn cơ hội thực thi pipeline. Nếu process bị kill cưỡng bức, máy chủ mất điện hoặc container bị dừng ngay lập tức, callback cleanup trong ứng dụng có thể không chạy. Với tài nguyên có lease hoặc subscription tồn tại bên ngoài process, nên kết hợp graceful shutdown với lease timeout, heartbeat hoặc cơ chế hết hạn ở phía hệ thống cấp tài nguyên.

### Network disconnect không luôn giống cancellation có chủ đích

Khi client chủ động dispose subscription, tín hiệu cancel có thể được truyền qua connection còn sống. Khi transport bị ngắt đột ngột, peer có thể chỉ phát hiện sau khi lỗi mạng hoặc keepalive timeout xảy ra. Tài nguyên phía server có thể tồn tại cho đến khi runtime phát hiện connection đã đóng và kết thúc các stream.

Vì vậy, cần có timeout và cơ chế phát hiện connection chết. Không dựa hoàn toàn vào việc client luôn gửi CANCEL một cách sạch sẽ trước khi rời mạng.

### Không dùng connection close để thay thế stream cleanup

Connection close có thể kết thúc nhiều stream cùng lúc, nhưng mỗi stream vẫn cần sở hữu và giải phóng tài nguyên của nó. usingWhen hoặc resource scope tương đương giúp cleanup được gắn với publisher, bất kể stream kết thúc vì complete, error hay cancellation do connection đóng.

## 9. Tránh blocking trong quá trình cleanup

Cleanup thường chạy trên đường xử lý reactive. Nếu callback cleanup thực hiện thao tác blocking lâu trên event loop, các stream khác có thể bị chậm.

Ví dụ, gọi Thread.sleep, chờ Future.get() hoặc đóng một API blocking trực tiếp trong doFinally có thể chặn thread xử lý nhiều kết nối.

Nếu tài nguyên có API blocking:

- Ưu tiên dùng driver/client có cleanup non-blocking.
- Nếu chưa thể thay thế, chuyển thao tác blocking sang scheduler phù hợp như boundedElastic.
- Không gọi block() trên event loop.
- Đặt timeout và theo dõi thời gian cleanup.
- Giới hạn số tác vụ cleanup chạy đồng thời để shutdown không tạo tải đột biến.

Ví dụ chuyển thao tác đóng blocking thành publisher:

~~~java
Mono<Void> closeBlockingResource(Resource resource) {
    return Mono.fromRunnable(() -> {
        try {
            resource.close();
        } catch (IOException error) {
            throw new UncheckedIOException(error);
        }
    }).subscribeOn(Schedulers.boundedElastic());
}
~~~

Khi dùng hàm này trong usingWhen, Reactor có thể chờ publisher cleanup hoàn tất. Đây là cách biểu diễn cleanup blocking trong pipeline; về lâu dài nên ưu tiên API giải phóng bất đồng bộ nếu thư viện cung cấp.

## 10. Cleanup phải an toàn khi cạnh tranh và gọi lặp

Trong hệ thống realtime, complete, error, cancel và connection close có thể xảy ra gần nhau. Framework và publisher cần tuân thủ quy tắc terminal của Reactive Streams, nhưng tài nguyên do ứng dụng tự quản lý vẫn cần được bảo vệ.

Một số nguyên tắc:

- Cleanup nên idempotent: gọi nhiều lần không làm hỏng trạng thái.
- Đánh dấu trạng thái đã đóng một cách thread-safe nếu nhiều callback cùng có thể chạm tới resource.
- Không phát dữ liệu mới sau terminal signal.
- Không giữ tham chiếu tới subscriber hoặc resource sau khi stream đã kết thúc.
- Cleanup lỗi phải được ghi nhận, không làm mất lỗi nghiệp vụ gốc.
- Không để cleanup của stream này giải phóng resource dùng chung của stream khác.

Ví dụ một handle có thể dùng AtomicBoolean để bảo đảm thao tác đóng vật lý chỉ thực hiện một lần:

~~~java
final class ListenerHandle implements AutoCloseable {

    private final AtomicBoolean closed = new AtomicBoolean();
    private final EventSource source;
    private final Listener listener;

    ListenerHandle(EventSource source, Listener listener) {
        this.source = source;
        this.listener = listener;
    }

    @Override
    public void close() {
        if (closed.compareAndSet(false, true)) {
            source.removeListener(listener);
        }
    }
}
~~~

AtomicBoolean chỉ bảo vệ thao tác close của handle này. Nó không thay thế quản lý thread-safety của EventSource hoặc listener. Nếu removeListener là bất đồng bộ, hãy dùng một handle có phương thức trả Mono<Void> và quản lý bằng usingWhen.

## 11. Kiểm thử cleanup khi complete, error và cancel

Một bài kiểm thử chỉ xác nhận dữ liệu được phát đúng là chưa đủ. Cần kiểm tra resource disposer được gọi trong mọi nhánh kết thúc.

### Kiểm thử với using

~~~java
@Test
void closesResourceWhenFluxCompletes() {
    AtomicInteger closes = new AtomicInteger();

    Flux<Integer> source = Flux.using(
        () -> new Object(),
        resource -> Flux.just(1, 2, 3),
        resource -> closes.incrementAndGet()
    );

    StepVerifier.create(source)
        .expectNext(1, 2, 3)
        .verifyComplete();

    assertEquals(1, closes.get());
}
~~~

Bài test xác nhận cleanup chạy khi publisher hoàn tất bình thường. Có thể tạo nguồn lỗi để kiểm tra nhánh error.

~~~java
@Test
void closesResourceWhenFluxErrors() {
    AtomicInteger closes = new AtomicInteger();

    Flux<Integer> source = Flux.using(
        () -> new Object(),
        resource -> Flux.<Integer>error(new IllegalStateException("read failed")),
        resource -> closes.incrementAndGet()
    );

    StepVerifier.create(source)
        .expectErrorMessage("read failed")
        .verify();

    assertEquals(1, closes.get());
}
~~~

### Kiểm thử cancel với usingWhen

~~~java
@Test
void runsAsyncCleanupWhenSubscriberCancels() {
    AtomicInteger cancelCleanups = new AtomicInteger();

    Mono<TestResource> acquire = Mono.fromSupplier(TestResource::new);

    Flux<Integer> source = Flux.usingWhen(
        acquire,
        resource -> Flux.range(1, 10),
        resource -> Mono.fromRunnable(resource::close),
        (resource, error) -> Mono.fromRunnable(resource::close),
        resource -> Mono.fromRunnable(() -> {
            resource.close();
            cancelCleanups.incrementAndGet();
        })
    );

    StepVerifier.create(source.take(1))
        .expectNext(1)
        .verifyComplete();

    assertEquals(1, cancelCleanups.get());
}
~~~

take(1) nhận một phần tử rồi hủy upstream. usingWhen thực hiện cleanup dành cho cancellation. Trong test thực tế, TestResource.close() nên đếm số lần đóng để xác nhận resource chỉ được giải phóng một lần.

### Ma trận kiểm thử tối thiểu

| Kịch bản | Tín hiệu | Điều cần xác nhận |
|---|---|---|
| Nguồn phát hết dữ liệu | Complete | Cleanup hoàn tất một lần |
| Nguồn phát lỗi | Error | Cleanup lỗi được gọi và lỗi gốc được quan sát |
| Client dispose subscription | Cancel | Subscription upstream và resource riêng được dừng |
| take(n) đạt giới hạn | Cancel upstream, complete downstream | Resource được giải phóng dù consumer nhận đủ dữ liệu |
| Connection bị đóng | Error hoặc cancel tùy implementation | Các stream phụ thuộc giải phóng tài nguyên |
| Cleanup tự phát sinh lỗi | Cleanup error | Có metrics/log và chính sách báo lỗi rõ ràng |
| Hai callback cạnh tranh | Terminal/cancel race | Resource không bị đóng vật lý nhiều lần |
| Nhiều stream dùng chung pool | Nhiều interaction | Hủy một stream không đóng pool của stream khác |

Với RSocket integration test, hãy mở request-stream, nhận một vài payload rồi cancel client. Kiểm tra server đã gỡ broker listener, trả connection về pool hoặc dừng timer. Sau đó xác nhận một stream khác trên cùng connection vẫn hoạt động.

## 12. Những lỗi thường gặp

| Cách làm | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ cleanup trong doOnComplete | Resource bị giữ khi error hoặc cancel | Dùng using hoặc usingWhen |
| Chỉ cleanup trong doOnError | Stream hoàn tất bình thường hoặc bị hủy sẽ rò rỉ | Bao phủ cả ba nhánh |
| Dùng doFinally để chạy async cleanup | Publisher không chờ cleanup hoàn tất | Dùng usingWhen |
| Gọi subscribe() trong controller | Công việc tách khỏi vòng đời request | Trả Mono/Flux cho framework |
| Gọi block() trong cleanup trên event loop | Làm nghẽn các stream khác | Dùng cleanup reactive hoặc boundedElastic |
| Đóng connection pool khi một stream kết thúc | Các stream khác mất kết nối | Trả connection mượn về pool; đóng pool khi shutdown |
| Không xử lý cancellation | Broker listener, cursor hoặc timer vẫn chạy | Propagate cancel và kiểm tra disposer |
| Coi cancel là rollback | Tác dụng phụ đã commit vẫn tồn tại | Dùng transaction/compensation theo nghiệp vụ |
| Đóng resource dùng chung từ mỗi subscriber | Một client làm hỏng các client khác | Xác định rõ ownership và scope |
| Bỏ qua lỗi cleanup | Rò rỉ tài nguyên khó phát hiện | Ghi log, metrics, timeout và cơ chế phục hồi |
| Giả định network luôn gửi CANCEL | Resource có thể tồn tại đến khi timeout phát hiện disconnect | Dùng keepalive, timeout và xử lý connection close |
| Không kiểm thử nhánh cancel | Lỗi chỉ xuất hiện khi người dùng rời stream | Kiểm thử complete, error và cancel riêng |

## Kết luận

Trong ứng dụng RSocket, tài nguyên có thể thuộc phạm vi ứng dụng, connection hoặc từng stream. Hãy xác định rõ ai sở hữu tài nguyên và thời điểm vòng đời của nó kết thúc. Với một publisher, cleanup phải chạy khi complete, error và cancel; ba nhánh này đều là kết quả hợp lệ của một tương tác realtime.

Dùng using cho tài nguyên có thao tác đóng đồng bộ và usingWhen khi cleanup trả về publisher bất đồng bộ. Dùng doFinally để quan sát mọi nhánh kết thúc, doOnCancel để theo dõi cancellation và các hook lỗi/hoàn tất cho metrics. Tránh subscribe hoặc block tùy tiện trong controller, không đóng tài nguyên dùng chung từ một stream riêng, và kiểm thử việc giải phóng trong cả ba trường hợp.

Một stream được dọn dẹp đúng cách sẽ giải phóng connection, listener, cursor, timer và buffer khi không còn cần thiết. Điều này giúp hệ thống realtime duy trì ổn định khi client thường xuyên đăng ký, hủy, reconnect hoặc gặp lỗi mạng.
